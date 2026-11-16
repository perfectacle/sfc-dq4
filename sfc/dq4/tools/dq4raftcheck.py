"""3장 여신상 동굴 배(dq4raft)를 탄 채 걸음 전투를 하고 돌아와도 배에 탄 채인지 MesenCE 헤드리스로 본다.

검사 롬으로 만든 출발 상태(dq4freshstate)에서 3장 flag 를 켜고 단추 flag 를 끈 채 배 옆에 순간이동해 배 칸으로 걸어
탄다(조우 없음). 그 상태에서 물 쪽으로 한 걸음 내디뎌 전투를 붙이고(dq4battlecheck.force_patch, 이기기만 하는 무리)
돌아온 뒤 같은 쪽으로 더 걷는다. 배에서 내렸거나 물 칸 표시(셀 +1 bit1)가 지워졌으면 물로 더 걷지 못한다.

  entry  48/02(FC 40/00) 배 (16,05)를 타고 오른쪽으로
  lake   48/06(FC 40/04) 배 (1D,1B)를 타고 (1D,1A)에서 오른쪽으로

본다: 전투가 걸린 맵·칸으로 돌아옴, 돌아온 뒤 같은 쪽으로 걸어 다른 FC 물 칸에 닿음.

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
import dq4ch1walkcheck as wc  # noqa: E402
import dq4ch3endor as endor  # noqa: E402
import dq4ch3event as ch3  # noqa: E402
import dq4freshstate  # noqa: E402

GROUP = [(0x03, 1)]
START = (f"{0x2190 + ch3.CHAPTER3[0]:04X}|{ch3.CHAPTER3[1]:02X};"
         f"{0x2190 + endor.BUTTON[0]:04X}&{~endor.BUTTON[1] & 0xFF:02X}")
# (이름, 순간이동 TO(한 셀 아래에 내림), 배에 타는 걸음, 배 셀, 전투 쪽)
SCENES = {"entry": (f"{endor.CAVE_ENTRY},42,10", "44,11;wait:30", (44, 11), "right"),
          "lake": (f"{endor.CAVE_LOW_DRY},60,56", "60,55;58,55;58,53;wait:30", (58, 53), "right")}


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
        results = dict(f.result() for f in [pool.submit(run, mesence, rom, data, state, out, n) for n in SCENES])
    ok = all(r["ok"] for r in results.values())
    result = {"status": "passed" if ok else "failed", "scenes": results}
    (out / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
