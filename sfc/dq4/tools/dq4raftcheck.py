"""3장 여신상 동굴 배(dq4raft)를 탄 채 걸음 전투를 하고 돌아와도 배에 탄 채인지 MesenCE 헤드리스로 본다.

검사 롬으로 만든 출발 상태(dq4freshstate)에서 3장 flag 를 켜고 단추 flag 를 끈 채 배 옆에 순간이동해 배 칸으로 걸어
탄다(조우 없음). 그 상태에서 물 쪽으로 한 걸음 내디뎌 전투를 붙이고(dq4battlecheck.force_patch, 이기기만 하는 무리)
돌아온 뒤 같은 쪽으로 더 걷는다. 배에서 내렸거나 물 칸 표시(셀 +1 bit1)가 지워졌으면 물로 더 걷지 못한다.

  entry  48/02(FC 40/00) 배 (16,05)를 타고 오른쪽으로
  lake   48/06(FC 40/04) 배 (1D,1B)를 타고 (1D,1A)에서 오른쪽으로

본다: 전투가 걸린 맵·칸으로 돌아옴, 돌아온 뒤 같은 쪽으로 걸어 다른 FC 물 칸에 닿음.

배가 화면에 보이는지도 본다(lua/dq4raftview.lua). 48/02 배 왼쪽 위 칸 (42,9)에 서서 30프레임 뒤:
  shown    단추 전: 배 칸 (44,11)에 그림 A1 슬롯, 주인공 오른쪽 아래 16점 자리에 우선순위 3 OAM 6칸(물 BG 위)
  removed  단추 뒤(FC 1C:$A55B 처럼 배를 치움): 그 슬롯·OAM 이 없음

탄 동안 주인공이 보이는지(dq4raft 가 탄 동안 주인공 OBJ 속성 바탕 33A0 을 B0 으로 둠). 48/02 배를 타고 물로 두 칸
나아간 뒤, 화면 가운데 주인공 자리 OAM 가운데 색인이 가장 앞선 것이 우선순위 3 이고(앞선 화소가 우선순위를 정하므로)
우선순위 3 칸이 주인공·배 합쳐 12 칸 이상:
  ride0    일행 없음
  ride1    로렌스(따라 걷는 용병 하나)
  ride2    스콧·로렌스(둘)
  ride_dog   개 토마스(따라 걷는 그림 하나)
  ride_dog1  로렌스·개
따라 걷는 칸(걷는 줄 칸 1~)은 탄 동안 안 보이게(7E:3380 bit7) 숨고, 왼쪽 땅으로 돌아와 내리면 다시 보여야 한다(FC 40/00
실측: 탄 뒤 개 칸 $7021 = 81, 배만 보임).

  MESENCE=… LIBDIR=… python sfc/dq4/tools/dq4raftcheck.py --rom work/ch3/dq4-ch1-full.sfc --out work/raftcheck
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

import dq4battlecheck as bc  # noqa: E402
import dq4raft  # noqa: E402
import dq4ch1walkcheck as wc  # noqa: E402
import dq4ch3endor as endor  # noqa: E402
import dq4ch3event as ch3  # noqa: E402
import dq4freshstate  # noqa: E402

GROUP = [(0x03, 1)]
VIEW = TOOLS / "lua" / "dq4raftview.lua"
START = (f"{0x2190 + ch3.CHAPTER3[0]:04X}|{ch3.CHAPTER3[1]:02X};"
         f"{0x2190 + endor.BUTTON[0]:04X}&{~endor.BUTTON[1] & 0xFF:02X}")
# (이름, 순간이동 TO(한 셀 아래에 내림), 배에 타는 걸음, 배 셀, 전투 쪽)
SCENES = {"entry": (f"{endor.CAVE_ENTRY},42,10", "44,11;wait:30", (44, 11), "right"),
          "lake": (f"{endor.CAVE_LOW_DRY},60,56", "60,55;58,55;58,53;wait:30", (58, 53), "right")}


VIEW_TO = f"{endor.CAVE_ENTRY},42,8"
RAFT_CELL = (0x2C, 0x0B)
HERO_OAM = (0x78, 0x67)            # (42,9)에 선 주인공 OBJ 왼쪽 위 점(화면 가운데)
VIEWS = {"shown": "", "removed": f"{0x2190 + endor.BUTTON[0]:04X}|{endor.BUTTON[1]:02X}"}


def raft_view(text):
    """view.txt → (배 칸의 A1 슬롯 수, 배 자리의 우선순위 3·화면 안 OAM 칸 수)."""
    slots = oams = 0
    x0, y0 = HERO_OAM[0] + 16, HERO_OAM[1] + 16
    for line in text.splitlines():
        f = line.split()
        if f[0] == "slot" and (int(f[2], 16), int(f[3], 16), int(f[4], 16)) == (*RAFT_CELL, 0xA1):
            slots += 1
        elif f[0] == "oam":
            x, y, attr, hi = int(f[2], 16), int(f[3], 16), int(f[5], 16), int(f[6])
            if not hi & 1 and attr & 0x30 == 0x30 and x0 <= x < x0 + 16 and y0 <= y < y0 + 24:
                oams += 1
    return slots, oams


def view(mesence, rom, state, out, name):
    dest = out / name
    seg = (f"{name}_warp", "warp", VIEW_TO, {"map": endor.CAVE_ENTRY})
    r = wc.segment(mesence, rom, state, dest / seg[0], seg, wc.NO_ENCOUNTERS,
                   ";".join(v for v in (START, VIEWS[name]) if v))
    if r["status"] != "passed":
        return name, {"ok": False, "error": f"{seg[0]}: {r['problems']}"}
    wc.run(mesence, rom, VIEW, dest / "view", {"STATE": str(dest / seg[0] / "end.mss"), "WAIT": "30"}, 120)
    log = dest / "view" / "view.txt"
    slots, oams = raft_view(log.read_text(encoding="utf-8")) if log.exists() else (None, None)
    want = (1, 6) if name == "shown" else (0, 0)
    return name, {"ok": (slots, oams) == want, "slots": slots, "oam": oams, "want": want}


# (용병들, 개 토마스가 따라옴)
RIDES = {"ride0": ((), False), "ride1": (("lawrence",), False), "ride2": (("scott", "lawrence"), False),
         "ride_dog": ((), True), "ride_dog1": (("lawrence",), True)}
RIDE_WALK = "42,11;44,11;48,11;wait:30"
# 탄 뒤 물에서 왼쪽 땅으로 돌아가 내린다(배는 마지막 물 칸에 남음)
LAND_WALK = "44,11;42,11;wait:30"
# 걷는 줄 칸 1·2 의 안 보이게 비트(dq4raft._followers_shown)
HIDE_FLAGS = {"HIDE1": (dq4raft.SLOT_HIDE + 1, 0x80), "HIDE2": (dq4raft.SLOT_HIDE + 2, 0x80)}


def party_set(data, whos):
    """용병들을 일행 기록 1~ 에 두고 걷는 일행으로(dq4ch3walkcheck.effects 와 같은 꼴)."""
    import dq4mercenary as merc
    out = []
    for k, who in enumerate(whos, 1):
        base = ch3.PARTY_ITEMS - 0x16 + k * ch3.RECORD
        out += [f"{base + i & 0xFFFF:04X}={b:02X}" for i, b in enumerate(merc.record(data, who))]
        out += [f"{merc.ORDERS[0] + k & 0xFFFF:04X}={k:02X}", f"{merc.ORDERS[1] + k & 0xFFFF:04X}={k:02X}"]
    n = len(whos) + 1
    out += [f"{a & 0xFFFF:04X}={n:02X}" for a in (merc.COUNT, merc.WALKERS, merc.COUNT_COPY)]
    return ";".join(out)


def hero_view(text):
    """view.txt → (화면 가운데 주인공 자리 OAM 가운데 색인이 가장 앞선 칸의 우선순위, 그 자리 우선순위 3 칸 수)."""
    x0, y0 = HERO_OAM
    first, front = None, 0
    for line in text.splitlines():
        f = line.split()
        if f[0] != "oam":
            continue
        x, y, attr, hi = int(f[2], 16), int(f[3], 16), int(f[5], 16), int(f[6])
        if hi & 1 or not (x0 <= x < x0 + 16 and y0 <= y < y0 + 24):
            continue
        if first is None:
            first = attr >> 4 & 3
        front += attr & 0x30 == 0x30
    return first, front


def ride(mesence, rom, data, state, out, name):
    """배를 타고 물로 두 칸 나아가 주인공이 보이는지, 따라 걷는 칸(용병·개)이 숨는지 보고, 땅으로 돌아와 다시 보이는지."""
    dest = out / name
    whos, dog = RIDES[name]
    followers = len(whos) + dog
    dog_set = f"{0x2190 + ch3.DOG[0]:04X}|{ch3.DOG[1]:02X}" if dog else ""
    flags = {**wc.FLAGS, **HIDE_FLAGS}
    segs = ((f"{name}_warp", "warp", VIEW_TO, {"map": endor.CAVE_ENTRY}),
            (f"{name}_board", "walk", RIDE_WALK, {"map": endor.CAVE_ENTRY, "cell": (48, 11)}))
    hidden = None
    for seg in segs:
        extra = ";".join(v for v in (START, dog_set, party_set(data, whos)) if v) if seg[1] == "warp" else ""
        r = wc.segment(mesence, rom, state, dest / seg[0], seg, wc.NO_ENCOUNTERS, extra, flags=flags)
        if r["status"] != "passed":
            return name, {"ok": False, "error": f"{seg[0]}: {r['problems']}"}
        state = dest / seg[0] / "end.mss"
        hidden = [f"HIDE{k}" in r.get("flags", ()) for k in range(1, followers + 1)]
    wc.run(mesence, rom, VIEW, dest / "view", {"STATE": str(state), "WAIT": "30"}, 120)
    log = dest / "view" / "view.txt"
    first, front = hero_view(log.read_text(encoding="utf-8")) if log.exists() else (None, None)
    land = (f"{name}_land", "walk", LAND_WALK, {"map": endor.CAVE_ENTRY, "cell": (42, 11)})
    r = wc.segment(mesence, rom, state, dest / land[0], land, wc.NO_ENCOUNTERS, "", flags=flags)
    shown = [f"HIDE{k}" not in r.get("flags", ()) for k in range(1, followers + 1)]
    ok = first == 3 and front >= 12 and all(hidden) and r["status"] == "passed" and all(shown)
    return name, {"ok": ok, "first": first, "front": front, "hidden_riding": hidden, "shown_landed": shown,
                  **({} if r["status"] == "passed" else {"land": r["problems"]})}


def fc_cell(cell):
    x, y = map(int, cell.split(","))
    return x // 2, (y - 1) // 2


def run(mesence, rom, data, state, out, name):
    to, walk, cell, way = SCENES[name]
    dest = out / name
    for seg in ((f"{name}_warp", "warp", to, {"map": to.split(",")[0]}),
                (f"{name}_board", "walk", walk, {"map": to.split(",")[0], "cell": cell})):
        r = wc.segment(mesence, rom, state, dest / seg[0], seg, wc.NO_ENCOUNTERS, START if seg[1] == "warp" else "")
        if r["status"] != "passed":
            return name, {"ok": False, "error": f"{seg[0]}: {r['problems']}"}
        state = dest / seg[0] / "end.mss"
    patch = ";".join((bc.force_patch(GROUP), bc.weak_patch(data, [m for m, _ in GROUP])))
    fight = dest / "battle"
    wc.run(mesence, rom, bc.BATTLE, fight, {"STATE": str(state), "ROMPATCH": patch, "AFTERPATCH": wc.NO_ENCOUNTERS,
                                            "SET": f"{wc.rng_for(0)};{wc.DAY_SET}", "POKE": wc.HERO_HP, "STEP": way,
                                            "KEYS": "a", "MOVE": way, "MOVEF": "48", "MAXF": "6000"}, 300)
    log = fight / "battle.txt"
    st = bc.parse(log.read_text(encoding="utf-8") if log.exists() else "")
    problems = [f"{k} 단계 없음" for k in ("start", "after", "moved") if k not in st]
    if not problems:
        if (st["after"]["map"], st["after"]["cell"]) != (st["start"]["map"], st["start"]["cell"]):
            problems.append(f"돌아온 자리 {st['after']['map']} {st['after']['cell']}, 전투 때 {st['start']['map']} {st['start']['cell']}")
        if fc_cell(st["moved"]["cell"]) == fc_cell(st["after"]["cell"]):
            problems.append(f"전투 뒤 {way} 로 물을 지나가지 못함({st['after']['cell']})")
    return name, {"ok": not problems, "problems": problems, "start": st.get("start"), "after": st.get("after"),
                  "moved": st.get("moved")}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rom", required=True, type=Path)
    dq4freshstate.add_argument(ap)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--jobs", type=int, default=2)
    args = ap.parse_args()
    mesence = Path(os.environ["MESENCE"])
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} is not empty")
    out.mkdir(parents=True, exist_ok=True)
    rom = args.rom.resolve()
    state = dq4freshstate.resolve(args.state, mesence, rom, out / "start")
    data = rom.read_bytes()
    with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
        jobs = [pool.submit(run, mesence, rom, data, state, out, n) for n in SCENES]
        jobs += [pool.submit(view, mesence, rom, state, out, n) for n in VIEWS]
        jobs += [pool.submit(ride, mesence, rom, data, state, out, n) for n in RIDES]
        results = dict(f.result() for f in jobs)
    ok = all(r["ok"] for r in results.values())
    result = {"status": "passed" if ok else "failed", "scenes": results}
    (out / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
