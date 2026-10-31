"""Walk into every door of the prologue and chapter 1 maps (groups 36-3C) in MesenCE and expect dq4door's opening.

For each FC door block (fx, fy) (dq4environmentrom.objects: entry (2fx, 2fy-1)) and each walkable FC neighbour, the
hero warps (dq5warp.lua) onto the cell it stands on there (dq4groupbuild.cell: the FC block's bottom-left cell) and
holds the direction into the door (lua/dq4doorwalk.lua):

  below  (2fx, 2fy+3) up      above  (2fx, 2fy-1) down     left  (2fx-2, 2fy+1) right     right  (2fx+2, 2fy+1) left

and below and above half a block to the right (+half). Half a block up beside a door in a side wall the hero is not
stopped at all (the object blocks only its bottom row; the ROM before dq4door does the same), so that is not walked.

A door of lock 0 must open (a bit of 7E:21C2-21C5 set). A locked door must stay shut without a key, and open from
below with the thieves' key level (2199.1, as 01:DCFC reads it).

  MESENCE=… LIBDIR=… python sfc/dq4/tools/dq4doorcheck.py --rom work/ch1/dq4-ch1.sfc \\
      --state work/ch1walk/throne_out/end.mss --out work/doorcheck
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
import dq4mesen  # noqa: E402
from dq4environmentrom import DOOR_KIND, objects  # noqa: E402
from dq4groupbuild import placement  # noqa: E402
from dq4groupcheck import walkable  # noqa: E402
from kr_patch.fc import ines  # noqa: E402

WARP = DQ5_TOOLS / "lua" / "dq5warp.lua"
WALK = TOOLS / "lua" / "dq4doorwalk.lua"
GROUPS = range(0x36, 0x3D)
KEY = "2199|02"
HOLD = 100
# (name, FC neighbour of the door block, hero cell from the door entry (ex, ey), direction into the door)
APPROACHES = (
    ("below", (0, 1), (0, 4), "up"),
    ("below+half", (0, 1), (1, 4), "up"),
    ("above", (0, -1), (0, 0), "down"),
    ("above+half", (0, -1), (1, 0), "down"),
    ("left", (-1, 0), (-2, 2), "right"),
    ("right", (1, 0), (2, 2), "left"),
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
            for name, (dx, dy), (hx, hy), press in APPROACHES:
                if not walkable(source, fx + dx, fy + dy):
                    continue
                base = {"map": f"{g:02X}/{n:02X}", "door": [ex, ey], "lock": lock, "from": name,
                        "cell": [ex + hx, ey + hy], "press": press}
                out.append({**base, "key": False, "open": lock == 0})
                if lock and name == "below":
                    out.append({**base, "key": True, "open": True})
    return out


def run(mesence, rom, script, dest, env):
    dest.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, SHOT_DIR=str(dest), **env)
    with (dest / "mesen.log").open("w") as log:
        dq4mesen.run(mesence, rom, script, folder=dest, tag="door", cwd=dest, env=env, stdout=log, stderr=log,
                     timeout=300)


def warp(mesence, rom, state, dest, map_, x, y):
    """dq5warp steps down onto the cell below TO (or up first when that is blocked)."""
    run(mesence, rom, WARP, dest, {"STATE": str(state), "TO": f"{map_},{x},{y - 1}", "ANYWHERE": "1",
                                   "SAVE": "end.mss", "SETTLE": "60"})
    return dest / "end.mss" if (dest / "end.mss").exists() else None


def one(mesence, rom, state, out, k, case, hop):
    dest = out / f"{k:02d}-{case['map'].replace('/', '')}-{case['from']}{'-key' if case['key'] else ''}"
    x, y = case["cell"]
    start = warp(mesence, rom, state, dest / "warp", case["map"], x, y)
    if start is None and hop:
        # dq5warp does not see an arrival on the map it starts on: go by another map.
        via = warp(mesence, rom, state, dest / "hop", hop["map"], *hop["cell"])
        start = via and warp(mesence, rom, via, dest / "warp", case["map"], x, y)
    if start is None:
        return {**case, "ok": False, "problem": "순간이동 실패"}
    run(mesence, rom, WALK, dest, {"STATE": str(start), "INPUT": f"wait:20,{case['press']}:{HOLD}",
                                   "SET": KEY if case["key"] else ""})
    text = (dest / "door.txt").read_text() if (dest / "door.txt").exists() else ""
    rows = dict(line.split(" ", 1) for line in text.splitlines())
    if not {"start", "end", "seen"} <= rows.keys():
        return {**case, "ok": False, "problem": "결과 없음"}
    begin, flags0 = rows["start"].split()
    end = rows["end"].split()[0]
    opened = int(rows["seen"], 16) & ~int(flags0, 16) != 0
    result = {**case, "start": begin, "end": end, "opened": opened, "ok": opened == case["open"]}
    if begin != f"{x},{y}":
        result.update(ok=False, problem=f"시작 칸이 {begin}")
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rom", required=True, type=Path)
    ap.add_argument("--state", required=True, type=Path, help="조작할 수 있는 1장 세이브스테이트")
    ap.add_argument("--dq4", type=Path, default=Path("rom/dq4.nes"))
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--jobs", type=int, default=6)
    args = ap.parse_args()
    prg = ines.prg(args.dq4.read_bytes())
    mesence = os.environ["MESENCE"]
    args.out = args.out.resolve()
    args.out.mkdir(parents=True, exist_ok=True)
    todo = cases(prg)
    with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
        hops = {c["map"]: next((h for h in todo if h["map"] != c["map"]), None) for c in todo}
        results = list(pool.map(lambda kc: one(mesence, args.rom.resolve(), args.state.resolve(), args.out, *kc,
                                               hops[kc[1]["map"]]), enumerate(todo)))
    report = {"status": "passed" if all(r["ok"] for r in results) else "failed", "cases": results}
    (args.out / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n")
    for r in results:
        print(f"{'ok  ' if r['ok'] else 'FAIL'} {r['map']} {r['door']} 잠금{r['lock']} {r['from']}"
              f"{' 열쇠' if r['key'] else ''}: {r.get('start')} -> {r.get('end')} 열림={r.get('opened')} "
              f"{r.get('problem', '')}")
    print(report["status"])
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
