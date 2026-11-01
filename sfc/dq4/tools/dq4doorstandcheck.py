"""Stand the hero in every door of the prologue and chapter 1 maps (groups 36-3C) and expect it drawn in front.

The hero warps (dq5warp.lua) next to a door as dq4doorcheck does, walks in (dq4door opens it), and stops on the
door's cells (lua/dq4doorstand.lua). 50 frames later the OAM priority 2B:B815 picks for every row of the hero
(person 0, as it stores it to 7E:1AB1) must be 30. Priority 20 puts the hero under the upper-layer wall over the door: in the side doors
(FC wall above and below) only the legs showed.

  side door, from the left   (ex-2, ey+2) right -> (ex, ey+2)    from the right (ex+2, ey+2) left -> (ex, ey+2)
  door with floor above/below, from below (ex, ey+4) up -> (ex, ey+2), (ex, ey+1)
                               from above (ex, ey)   down -> (ex, ey+1), (ex, ey+2)

(ex, ey) is the door object entry (dq4environmentrom.objects); the FC door block is cells ey+1, ey+2. A locked door
is walked with the thieves' key level (2199.1). Format: sfc/dq4/docs/dq4-environment-format.md 「문과 성문」.

  MESENCE=… LIBDIR=… python sfc/dq4/tools/dq4doorstandcheck.py --rom work/ch1/dq4-ch1-full.sfc --out work/doorstand
  (--state 를 주지 않으면 dq4heroblockcheck 의 성 마을 출발 상태를 롬 SHA-1 캐시에서 쓰거나 만든다)
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

import dq4block  # noqa: E402
import dq4ch1walkcheck as wc  # noqa: E402
import dq4heroblockcheck as hb  # noqa: E402
from dq4doorcheck import GROUPS, KEY, WARP, run  # noqa: E402
from dq4environmentrom import DOOR_KIND, objects  # noqa: E402
from dq4groupbuild import placement  # noqa: E402
from dq4groupcheck import walkable  # noqa: E402
from kr_patch.fc import ines  # noqa: E402

STAND = TOOLS / "lua" / "dq4doorstand.lua"
FRONT = 0x30
# (name, FC neighbour of the door block, hero cell to warp to from the entry, direction, cells to stop on)
APPROACHES = (
    ("left", (-1, 0), (-2, 2), "right", ((0, 2),)),
    ("right", (1, 0), (2, 2), "left", ((0, 2),)),
    ("below", (0, 1), (0, 4), "up", ((0, 2), (0, 1))),
    ("above", (0, -1), (0, 0), "down", ((0, 1), (0, 2))),
)


def cases(prg):
    out = []
    for (fg, fn), (g, n) in sorted(placement(prg).items(), key=lambda kv: kv[1]):
        if g not in GROUPS:
            continue
        source = dq4block.Map(prg, fg, fn)
        for ex, ey, kind, lock in objects(source):
            if kind != DOOR_KIND:
                continue
            fx, fy = ex // 2, (ey + 1) // 2
            for name, (dx, dy), (hx, hy), press, stops in APPROACHES:
                if not walkable(source, fx + dx, fy + dy):
                    continue
                out.append({"map": f"{g:02X}/{n:02X}", "door": [ex, ey], "lock": lock, "from": name,
                            "cell": [ex + hx, ey + hy], "press": press,
                            "stops": [[ex + sx, ey + sy] for sx, sy in stops]})
    return out


def warp(mesence, rom, state, dest, map_, x, y):
    """dq4doorcheck.warp with the chapter 1 flag on: the start state is before the throne room, and entering the
    castle 36/01 without it starts the chapter's opening narration."""
    run(mesence, rom, WARP, dest, {"STATE": str(state), "TO": f"{map_},{x},{y - 1}", "ANYWHERE": "1",
                                   "SAVE": "end.mss", "SETTLE": "60", "SET": wc.setup(wc.SEGMENTS, 1)[0]})
    return dest / "end.mss" if (dest / "end.mss").exists() else None


def one(mesence, rom, state, out, k, case, hop):
    dest = out / f"{k:02d}-{case['map'].replace('/', '')}-{case['door'][0]}-{case['door'][1]}-{case['from']}"
    x, y = case["cell"]
    start = warp(mesence, rom, state, dest / "warp", case["map"], x, y)
    if start is None and hop:
        via = warp(mesence, rom, state, dest / "hop", hop["map"], *hop["cell"])
        start = via and warp(mesence, rom, via, dest / "warp", case["map"], x, y)
    if start is None:
        return [{**case, "ok": False, "problem": "순간이동 실패"}]
    results = []
    for sx, sy in case["stops"]:
        stand = dest / f"stand-{sx}-{sy}"
        run(mesence, rom, STAND, stand, {"STATE": str(start), "PRESS": case["press"], "STOPAT": f"{sx},{sy}",
                                         "SET": KEY if case["lock"] else ""})
        text = (stand / "stand.txt").read_text() if (stand / "stand.txt").exists() else ""
        rows = dict(line.split(" ", 1) for line in text.splitlines())
        result = {**case, "stop": [sx, sy]}
        if not {"map", "hero", "prio"} <= rows.keys():
            results.append({**result, "ok": False, "problem": "결과 없음"})
            continue
        prio = [int(v, 16) if v != "--" else None for v in rows["prio"].split()]
        result.update(hero=rows["hero"], prio=rows["prio"], ok=all(p == FRONT for p in prio))
        if rows["map"] != case["map"] or rows["hero"] != f"{sx},{sy}" or rows.get("at") != rows["hero"]:
            result.update(ok=False, problem=f"{rows['map']} {rows['hero']} 에 섬")
        results.append(result)
    return results


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rom", required=True, type=Path)
    ap.add_argument("--state", type=Path, help="조작할 수 있는 1장 세이브스테이트(없으면 dq4heroblockcheck 의 성 마을 출발 상태)")
    ap.add_argument("--dq4", type=Path, default=Path("rom/dq4.nes"))
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--jobs", type=int, default=2)
    args = ap.parse_args()
    prg = ines.prg(args.dq4.read_bytes())
    mesence = os.environ["MESENCE"]
    args.out = args.out.resolve()
    args.out.mkdir(parents=True, exist_ok=True)
    state = args.state.resolve() if args.state else \
        hb.make_base(mesence, args.rom.resolve(), args.out, wc.StateCache(args.rom.read_bytes()))[0]
    todo = cases(prg)
    # dq5warp does not see an arrival on the map it starts on, and stepping down from 36/01's start cell leaves by
    # the castle's exit, so hop by a map of another group.
    hops = {c["map"]: next((h for h in todo if h["map"][:2] != c["map"][:2]), None) for c in todo}
    with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
        results = [r for rs in pool.map(lambda kc: one(mesence, args.rom.resolve(), state, args.out,
                                                        *kc, hops[kc[1]["map"]]), enumerate(todo)) for r in rs]
    report = {"status": "passed" if results and all(r["ok"] for r in results) else "failed", "cases": results}
    (args.out / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n")
    for r in results:
        print(f"{'ok  ' if r['ok'] else 'FAIL'} {r['map']} {r['door']} 잠금{r['lock']} {r['from']} -> {r.get('stop')}: "
              f"우선순위 {r.get('prio')} {r.get('problem', '')}")
    print(f"{report['status']} {sum(r['ok'] for r in results)}/{len(results)}")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
