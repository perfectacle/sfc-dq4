"""맵·필드에 들어선 뒤 울리는 곡(지금 곡 7E:1D8B)이 장면마다 기대한 곡인지 MesenCE 헤드리스로 본다.

장면마다 검사 롬으로 만든 출발 상태(dq4freshstate)에서 dq5warp.lua 로 순간이동하고(TO 는 실내 셀, 필드는 그룹 3D 성의
필드 입구 옆 칸), WAIT 프레임 쉰 뒤 끝 WRAM 의 $1D8B 를 읽는다. 밤 장면은 시각 7E:075E 를 00F0 으로 붙들고(POKE, 매 프레임),
장 flag 는 SET 으로 맵을 불러오기 전에 켠다. 난수·조우는 쓰지 않는다(맵에 선 채 걷지 않음). 같은 롬·같은 입력이면
dq4readset 캐시가 결과를 펼친다. 곡 고르기 장치는 sfc/dq4/docs/dq4-chapter2-format.md 의 「곡」.

  MESENCE=… LIBDIR=… uv run --locked python sfc/dq4/tools/dq4mapsongcheck.py --rom work/ch1/dq4-ch1-full.sfc \\
      --out work/mapsong [--scenes castle-night,field-ch2]
"""

import argparse
import concurrent.futures
import json
import os
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
DQ5_TOOLS = TOOLS.parents[1] / "dq5" / "tools"
FC_TOOLS = TOOLS.parents[2] / "fc" / "dq4" / "tools"
for path in (TOOLS, DQ5_TOOLS, FC_TOOLS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import dq4ch2endor  # noqa: E402
import dq4ch2event  # noqa: E402
import dq4fieldport  # noqa: E402
import dq4freshstate  # noqa: E402
import dq4groupcheck  # noqa: E402
from dq4groupbuild import LINKS  # noqa: E402
from kr_patch.fc import ines  # noqa: E402

SONG_NOW, TIME, CHAPTER_FLAGS = 0x1D8B, 0x075E, 0x2190
NIGHT = "7E075E=F0;7E075F=00"         # 밤의 첫 값(21:8000 의 문턱)
CH2 = "{:04X}|{:02X}".format(CHAPTER_FLAGS + dq4ch2event.CHAPTER2[0], dq4ch2event.CHAPTER2[1])
# 들어선 뒤 쉬는 프레임. 지금 곡 묶음에서 맵 곡은 요청 뒤 100프레임 안에 울린다(sfc/dq4/docs/dq4-sound-port-format.md
# 「지금 롬으로 다시 잰 지연」). 곡 앞 자료가 큰 성 곡도 넉넉히 들도록 세 배쯤 둔다
WAIT = 300
CASTLE, VILLAGE, FIELD, TOWER, CAVE = 0x01, 0x06, 0x02, 0x0A, 0x09
NIGHT_CASTLE, NIGHT_VILLAGE, FIELD_CH2 = 0x30, 0x31, 0x05
EVENT_SONG = 0x23                    # インテルメッツォ
BATTLE, MIDBOSS = 0x17, 0x16         # 무리 등급 0·1 의 전투 곡(26:8F96, dq4ch2battle.NO_FLEE)
ENDOR_CASINO, ENDOR_STAND, ENDOR_ROOM = 0x07, 0x22, 0x1E

# 텐페: 대신 감 flag 를 켜고 들어가면 신부의 스크립트가 제단 flag 를 켜고 바구니 이벤트(서술 뒤 시각을 00F8 로 두고
# 맵 이동)를 건다(dq4ch2event). A 를 눌러 서술을 넘기면 제단 위에서 곧 보스 전투(dq4ch2tempe)라 300프레임 뒤에는
# 보스 곡이 울린다
TEMPE_GONE = "{:04X}|{:02X}".format(CHAPTER_FLAGS + dq4ch2event.TEMPE_GONE[0],
                                    dq4ch2event.CHAPTER2[1] | dq4ch2event.TEMPE_HEARD[1] | dq4ch2event.TEMPE_GONE[1])
BASKET_TEST = ",".join(["a:8,wait:40"] * 16)

# 엔돌 투기장: 대회 중(IN, 일행 하나)으로 링 아래 길 (28,27)에 내려 위로 링에 들면 링 인물이 이긴 수 번째 상대와
# 싸운다(dq4ch2endor). 우승 장면은 다섯째와 싸우는 판(이긴 수 4)에서 그 몬스터를 약하게 덮고(dq4ch2walkcheck.battle_patch
# weak) A 로 넘긴다. 이 입력에서 팡파르는 A 31~39번째 사이에 울기 시작해 55번째 뒤까지 울리고 75번째 앞에 끝나
# 관중석 곡으로 돌아왔다(실측). 45번째 뒤는 팡파르 가운데, 80번째 뒤는 돌아온 뒤다
ENDOR_RING = f"{dq4ch2endor.ARENA},28,26"


def endor_in(stage):
    joined = "{:04X}|{:02X}".format(CHAPTER_FLAGS + dq4ch2event.JOINED[0], dq4ch2event.JOINED[1])
    counts = ";".join(f"{c & 0xFFFF:04X}=01" for c in dq4ch2endor.COUNTS)
    return (f"{CH2};{joined};{dq4ch2endor.FLAG_AT & 0xFFFF:04X}={dq4ch2endor.IN[1]:02X};"
            f"{dq4ch2endor.STAGE_AT & 0xFFFF:04X}={stage:02X};{counts}")


ENDOR_FIGHT_TEST = "up:40,wait:30," + ",".join(["a:8,wait:40"] * 6)
FANFARE_TAPS, AFTER_TAPS = 45, 80
ENDOR_WEAK = "weak:{:02X}".format(dq4ch2endor.OPPONENTS[-1][1])


def endor_final_test(taps):
    return "up:40,wait:30," + ",".join(["a:8,wait:40"] * taps)


# 장면 이름 → (TO 셀 또는 "field", SET, 밤인지, 기대한 곡[, 입력[, battle_patch 종류]])
SCENES = {
    "castle-day": ("3D/00,28,49", CH2, False, CASTLE),
    "castle-night": ("3D/00,28,49", CH2, True, NIGHT_CASTLE),
    "tempe-day": ("3D/03,42,77", CH2, False, VILLAGE),
    "tempe-night": ("3D/03,42,77", CH2, True, NIGHT_VILLAGE),
    "frenol-day": ("3D/04,44,5", CH2, False, VILLAGE),
    "frenol-night": ("3D/04,44,5", CH2, True, NIGHT_VILLAGE),
    "saran-day": ("45/00,24,47", CH2, False, VILLAGE),
    "saran-night": ("45/00,24,47", CH2, True, NIGHT_VILLAGE),
    "tempe-basket": ("3D/03,42,77", TEMPE_GONE, False, MIDBOSS, BASKET_TEST),
    # 이벤트 곡(7E:21DF bit7, 00:CE75 가 맵 곡 루틴 가운데 CE9D 로 뜀)은 맵 곡 대신 그 곡이고 고르지 않는다
    "event-song-night": ("3D/03,42,77", f"{CH2};21DF=A3", True, EVENT_SONG),
    "bazaar-day": ("45/05,62,23", CH2, False, VILLAGE),
    "tower-night": ("45/09,42,59", CH2, True, TOWER),
    "cave-night": ("45/0D,70,17", CH2, True, CAVE),
    "endor-day": ("40/00,52,23", CH2, False, CASTLE),
    "endor-night": ("40/00,52,23", CH2, True, NIGHT_CASTLE),
    "endor-casino": ("40/01,20,20", CH2, False, ENDOR_CASINO),
    "endor-stand": (ENDOR_RING, CH2, False, ENDOR_STAND),
    "endor-stand-night": (ENDOR_RING, CH2, True, ENDOR_STAND),
    "endor-room": (f"{dq4ch2endor.BEDROOM},{dq4ch2endor.BED_CELL[0]},{dq4ch2endor.BED_CELL[1]}", CH2, False, ENDOR_ROOM),
    "endor-fight": (ENDOR_RING, endor_in(0), False, BATTLE, ENDOR_FIGHT_TEST),
    "endor-fanfare": (ENDOR_RING, endor_in(dq4ch2endor.ROUNDS - 1), False, dq4ch2endor.CHAMPION_SONG,
                      endor_final_test(FANFARE_TAPS), ENDOR_WEAK),
    "endor-champion": (ENDOR_RING, endor_in(dq4ch2endor.ROUNDS - 1), False, ENDOR_STAND,
                       endor_final_test(AFTER_TAPS), ENDOR_WEAK),
    "bataland-day": ("36/00,10,45", "", False, CASTLE),
    "bataland-night": ("36/00,10,45", "", True, NIGHT_CASTLE),
    "imuru-night": ("37/00,50,9", "", True, NIGHT_VILLAGE),
    "field-ch1": ("field", "", False, FIELD),
    "field-ch1-night": ("field", "", True, FIELD),
    "field-ch2": ("field", CH2, False, FIELD_CH2),
    "field-ch2-night": ("field", CH2, True, FIELD_CH2),
}


def field_start(prg):
    """그룹 3D 성의 첫 필드 입구 블록 옆, 걸을 수 있는 FC 칸의 DQ5 셀."""
    _, props = dq4fieldport.fc_field(prg)
    blocks = dq4fieldport.entrance_blocks(props, [LINKS[0x3D][0]["field"][0]])
    (x, y), _ = next(dq4groupcheck.enter_starts(props, blocks))
    return x, y


def run_scene(mesence, rom, state, out, name, start):
    where, sets, night, want, *rest = SCENES[name]
    test, battle = (rest + [None, None])[:2]
    test = f"{test + ',' if test else ''}wait:{WAIT}"
    extra = {**({"SET": sets} if sets else {}), **({"POKE": NIGHT} if night else {})}
    if battle:
        import dq4ch2walkcheck
        extra["ROMPATCH"] = dq4ch2walkcheck.battle_patch(rom.read_bytes(), battle)
        extra["MAXF"] = 6000
    if where == "field":
        got = dq4groupcheck.field_scene(mesence, rom, state, out, name, *start, test, **extra)
    else:
        got = dq4groupcheck.scene(mesence, rom, state, out, name, TO=where, TEST=test, **extra)
    final = out / name / "final.wram"
    if "error" in got or not final.is_file():
        return {"want": f"{want:02X}", "error": got.get("error", "final.wram 없음"), "passed": False}
    wram = final.read_bytes()
    song = wram[SONG_NOW]
    return {"want": f"{want:02X}", "song": f"{song:02X}", "where": got,
            "time": f"{wram[TIME] | wram[TIME + 1] << 8:04X}",
            "chapter2": bool(wram[CHAPTER_FLAGS + dq4ch2event.CHAPTER2[0]] & dq4ch2event.CHAPTER2[1]),
            "passed": song == want and ("field" in got if where == "field" else got.get("map") == where[:5])}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rom", required=True, type=Path)
    ap.add_argument("--dq4", default="rom/dq4.nes", type=Path)
    dq4freshstate.add_argument(ap)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--scenes", help="comma-separated SCENES names to run (default: all)")
    args = ap.parse_args()
    names = args.scenes.split(",") if args.scenes else list(SCENES)
    unknown = [n for n in names if n not in SCENES]
    if unknown:
        ap.error(f"unknown scenes: {unknown}")
    mesence = Path(os.environ["MESENCE"])
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} is not empty")
    out.mkdir(parents=True, exist_ok=True)
    rom = args.rom.resolve()
    state = dq4freshstate.resolve(args.state, mesence, rom, out / "start")
    start = field_start(ines.prg(args.dq4.read_bytes()))
    with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
        futures = {n: pool.submit(run_scene, mesence, rom, state, out, n, start) for n in names}
        results = {n: f.result() for n, f in futures.items()}
    for name, r in results.items():
        mark = "통과" if r["passed"] else "실패"
        print(f"{mark} {name}: 곡 {r.get('song', '--')}(기대 {r['want']})" + (f" {r['error']}" if "error" in r else ""))
    ok = all(r["passed"] for r in results.values())
    (out / "report.json").write_text(json.dumps({"status": "passed" if ok else "failed", "scenes": results},
                                                ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
