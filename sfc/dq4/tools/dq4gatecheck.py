"""Walk into the FC 2x2 doors that become DQ5 gates (dq4environmentrom.GATES other than the plain gate A0) in
MesenCE and expect FC's key rules.

Each such door is a 4x4 gate object (kind 48) at (2gx, 2gy) over the FC door's 2x2 blocks (gx, gy). For each side
with a walkable FC block next to the door the hero warps (dq5warp.lua, from the ROM's dq4freshstate start) onto the
cell it stands on there and holds the direction into the door (lua/dq4doorwalk.lua, dq4door's walk-in opening):

  below  (2gx, 2gy+5) up      above  (2gx, 2gy-1) down
  left   (2gx-2, 2gy+1 or 2gy+3) right                 right  (2gx+4, 2gy+1 or 2gy+3) left

A door of lock 0 must open (a bit of 7E:21C2-21C5 set) and let the hero walk on past its far edge (or onto another
map). A locked door must stay shut and keep the hero on its side without a key, and with one key level too few;
with the key of its level it must open and let the hero past. Key levels as 01:DCFC reads them: 2199.1 (カギの技法,
FC とうぞくのカギ) for lock 1, まほうのカギ (B8) in the hero's first item slot for lock 2.

  MESENCE=… LIBDIR=… python sfc/dq4/tools/dq4gatecheck.py --rom work/dq4-groups/groups.sfc --out work/gatecheck
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
import dq4freshstate  # noqa: E402
from dq4doorcheck import WALK, run, warp  # noqa: E402
from dq4environmentmap import all_maps, block_prop  # noqa: E402
from dq4environmentrom import GATE, GATE_KIND, GATES, MAPS, objects  # noqa: E402
from dq4groupcheck import walkable  # noqa: E402
from kr_patch.fc import ines  # noqa: E402

HOLD = 140
# WRAM writes (dq4doorwalk SET) that give the party each key level of 01:DCFC. 7E:2056 is the hero's first item
# slot (party record 7E:2040 + 16).
KEYS = {0: "", 1: "2199|02", 2: "2056=B8"}


def cases(prg):
    where = {name: (g, k) for g, k, _, name in all_maps(prg)}
    out = []
    for name, (g, n) in MAPS.items():
        source = dq4block.Map(prg, *where[name])
        for ex, ey, kind, lock in objects(source):
            gx, gy = ex // 2, ey // 2
            prop = block_prop(source, source.cell(gx, gy) & 31)
            if kind != GATE_KIND or prop == GATE:
                continue
            sides = [("below", (gx, gy + 2), (ex, ey + 5), "up"), ("above", (gx, gy - 1), (ex, ey - 1), "down")]
            for row in (0, 1):
                sides.append((f"left{row}", (gx - 1, gy + row), (ex - 2, ey + 1 + 2 * row), "right"))
                sides.append((f"right{row}", (gx + 2, gy + row), (ex + 4, ey + 1 + 2 * row), "left"))
            for side, (fx, fy), cell, press in sides:
                if not walkable(source, fx, fy):
                    continue
                base = {"name": name, "map": f"{g:02X}/{n:02X}", "prop": f"{prop:02X}", "door": [ex, ey],
                        "lock": lock, "from": side, "cell": list(cell), "press": press}
                for level in sorted({0, lock - 1, lock} - {-1}):
                    out.append({**base, "key": level, "open": level >= lock})
    return out


def past(case, end, map_):
    """Whether the hero got beyond the door's far edge (or left the map)."""
    if map_ != case["map"]:
        return True
    x, y = end
    ex, ey = case["door"]
    return {"up": y < ey, "down": y > ey + 3, "right": x > ex + 3, "left": x < ex}[case["press"]]


def one(mesence, rom, state, out, k, case):
    dest = out / f"{k:02d}-{case['map'].replace('/', '')}-{case['from']}-key{case['key']}"
    x, y = case["cell"]
    start = warp(mesence, rom, state, dest / "warp", case["map"], x, y)
    if start is None:
        return {**case, "ok": False, "problem": "순간이동 실패"}
    p = case["press"]
    # A held with the direction closes the locked-door message, so the hero pushes on afterwards.
    press = f"{p}:60,{p}+a:8,{p}:{HOLD}" if not case["open"] else f"{p}:{HOLD}"
    run(mesence, rom, WALK, dest, {"STATE": str(start), "INPUT": f"wait:20,{press}", "SET": KEYS[case["key"]]})
    text = (dest / "door.txt").read_text() if (dest / "door.txt").exists() else ""
    rows = dict(line.split(" ", 1) for line in text.splitlines())
    if not {"start", "end", "seen", "map"} <= rows.keys():
        return {**case, "ok": False, "problem": "결과 없음"}
    begin, flags0 = rows["start"].split()
    end = rows["end"].split()[0]
    opened = int(rows["seen"], 16) & ~int(flags0, 16) != 0
    beyond = past(case, [int(v) for v in end.split(",")], rows["map"])
    result = {**case, "start": begin, "end": end, "end_map": rows["map"], "opened": opened, "past": beyond,
              "ok": opened == case["open"] and beyond == case["open"]}
    if begin != f"{x},{y}":
        result.update(ok=False, problem=f"시작 칸이 {begin}")
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rom", required=True, type=Path, help="dq4groupbuild.py 로 만든 롬")
    ap.add_argument("--dq4", type=Path, default=Path("rom/dq4.nes"))
    dq4freshstate.add_argument(ap)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--jobs", type=int, default=2)
    args = ap.parse_args()
    prg = ines.prg(args.dq4.read_bytes())
    mesence = os.environ["MESENCE"]
    args.out = args.out.resolve()
    args.out.mkdir(parents=True, exist_ok=True)
    rom = args.rom.resolve()
    state = dq4freshstate.resolve(args.state, mesence, rom, args.out / "start")
    todo = cases(prg)
    if not {f"{p:02X}" for p in GATES if p != GATE} <= {c["prop"] for c in todo}:
        raise SystemExit("a converted 2x2 door has no case")
    with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
        results = list(pool.map(lambda kc: one(mesence, rom, state, args.out, *kc), enumerate(todo)))
    report = {"status": "passed" if all(r["ok"] for r in results) else "failed", "cases": results}
    (args.out / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n")
    for r in results:
        print(f"{'ok  ' if r['ok'] else 'FAIL'} {r['name']} {r['map']} {r['prop']} 잠금{r['lock']} {r['from']} "
              f"열쇠{r['key']}: {r.get('start')} -> {r.get('end')} {r.get('end_map', '')} 열림={r.get('opened')} "
              f"지나감={r.get('past')} {r.get('problem', '')}")
    print(report["status"])
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
