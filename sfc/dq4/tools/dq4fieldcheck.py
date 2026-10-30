"""Check the FC field in a groups ROM of dq4groupbuild.py (MesenCE headless, dq5warp.lua FIELD).

  map      stand on the field: WRAM 7F:0000 (block numbers' low 8 bits) and 7E:E000 (9th bits) equal the map of
           dq4fieldport.world, byte for byte
  terrain  for FC block kinds near バトランド: stand on a walkable FC neighbour and press towards a block of that
           kind for two DQ5 cells; a walkable kind is entered, a blocked one (sea without a ship, mountain, reef,
           signboard) keeps the party on the neighbour

  MESENCE=… LIBDIR=… python sfc/dq4/tools/dq4fieldcheck.py --rom work/dq4-groups/groups.sfc --out work/dq4-fieldcheck
"""

import argparse
import concurrent.futures
import json
import os
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
DQ5_TOOLS = TOOLS.parents[1] / "dq5" / "tools"
for path in (TOOLS, DQ5_TOOLS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import dq4fieldport  # noqa: E402
from dq4groupcheck import field_scene  # noqa: E402
from dq5fieldwrite import split  # noqa: E402
from kr_patch.fc import ines  # noqa: E402

# FC block kind -> whether the party walks onto it from land.
KINDS = {0x02: True, 0x01: True, 0x03: True, 0x04: True, 0x05: True, 0x07: True, 0x16: True,
         0x00: False, 0x06: False, 0x0A: False, 0x15: False}
CENTER = (0xA4, 0x2E)
# Two DQ5 cells: the first press turns the party, then 8 frames a cell.
PRESS = 18
# Directions the party has to turn for (it faces down after the warp), so that PRESS is two cells.
TOWARDS = {(1, 0): "right", (-1, 0): "left", (0, -1): "up"}
MAP_SCENE_CELL = (2 * 0xA4, 2 * 0x2F + 1)


def probes(grid, props, entrances):
    """(kind, FC target block, FC start block, direction) nearest CENTER per KINDS kind."""
    out = []
    for kind in KINDS:
        best = None
        for y, row in enumerate(grid):
            for x, v in enumerate(row):
                if v != kind:
                    continue
                for (dx, dy), d in TOWARDS.items():
                    n = (x - dx, y - dy)
                    if not 0 <= n[1] < len(grid) or not 0 <= n[0] < len(row) or n in entrances:
                        continue
                    if props(*n) & 0x80 or props(*n) in (dq4fieldport.ENTRANCE, dq4fieldport.RIGHT_HALF):
                        continue
                    score = abs(x - CENTER[0]) + abs(y - CENTER[1])
                    if best is None or score < best[0]:
                        best = (score, (x, y), n, d)
        if best is None:
            raise ValueError(f"no FC block {kind:02X} with a walkable neighbour")
        out.append((kind, *best[1:]))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rom", required=True, type=Path)
    ap.add_argument("--dq4", default="rom/dq4.nes", type=Path)
    ap.add_argument("--state", default="work/state/ship.mss", type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--jobs", type=int, default=4)
    args = ap.parse_args()
    mesence = Path(os.environ["MESENCE"])
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} is not empty")
    rom, state = args.rom.resolve(), args.state.resolve()
    prg = ines.prg(args.dq4.read_bytes())
    grid, props = dq4fieldport.fc_field(prg)
    from dq4field import entrances
    taken = {(fx, fy) for _, fx, fy, *_ in entrances(prg)}

    def run_map():
        got = field_scene(mesence, rom, state, out, "map", *MAP_SCENE_CELL, "wait:30")
        ram = (out / "map" / "final.wram").read_bytes()
        low, high = split(dq4fieldport.world(grid))
        same = {"7F:0000": ram[0x10000:0x20000] == low, "7E:E000": ram[0xE000:0x10000] == high}
        return "map", {"got": got, "want": {"field": list(MAP_SCENE_CELL)}, "wram": same,
                       "ok": got == {"field": list(MAP_SCENE_CELL)} and all(same.values())}

    def run_probe(kind, target, start, d):
        name = f"terrain-{kind:02X}-{d}"
        got = field_scene(mesence, rom, state, out, name, *dq4fieldport.stand(*start), f"{d}:{PRESS},wait:60")
        want = list(target if KINDS[kind] else start)
        block = [v // 2 for v in got.get("field", ())]
        return name, {"got": got, "block": block, "want_block": want, "target": list(target), "ok": block == want}

    with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
        futures = [pool.submit(run_map)] + [pool.submit(run_probe, *p) for p in probes(grid, props, taken)]
        results = dict(f.result() for f in futures)
    ok = all(r["ok"] for r in results.values())
    report = {"status": "passed" if ok else "failed", "scenes": dict(sorted(results.items()))}
    (out / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
