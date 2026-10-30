"""Check the FC encounter zones of dq4fieldencounter.py in a groups ROM of dq4groupbuild.py (MesenCE headless,
dq5warp.lua FIELD with dq5warptrace.lua).

  zone   stand in an FC zone (ZONES) on two walkable FC blocks side by side and walk right and left with every
         DQ5 rate coefficient at FF (23:EA44, so nearly every step fights): every step 23:E7C2 gets the DQ5 zone
         of that FC zone, and every group 23:E7C2 picks is made of the monsters that zone's record weighs. The
         walk stops at the first fight, so each zone is walked after three different waits (DELAYS)
  rate   the same walk at the ROM's own rates: per step, the DQ5 chance (23:EA44[coefficient] x 00:82AF's Y >> 6)
         is FC's (base rate x 16 x the day or night terrain factor of the FC block >> 8)

  MESENCE=… LIBDIR=… python sfc/dq4/tools/dq4fieldencountercheck.py --rom work/dq4-groups/groups.sfc \\
      --out work/dq4-encountercheck
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

import dq4encounter  # noqa: E402
import dq4fieldencounter  # noqa: E402
import dq4fieldport  # noqa: E402
import dq4groupcheck  # noqa: E402
from kr_patch.fc import ines  # noqa: E402

# Scene -> (FC field, FC zone-map cell (column, row) to stand in). The first two have DQ5 namesakes (スライム,
# バブルスライム), 0E is a zone-map row past grid 0's seven, the last two are fields 1 and 3.
ZONES = {"castle-04": (0, (0x0A, 0x02)), "imuru-05": (0, (0x09, 0x01)), "south-0E": (0, (0x03, 0x0C)),
         "w1-34": (1, (0x01, 0x02)), "w2-36": (3, (0x02, 0x02))}
RATE_SCENES = ("castle-04", "imuru-05")
# Frames waited before the walk: each starts the random numbers elsewhere, for another fight.
DELAYS = (0, 7, 13)
RATES = "11EA44=FFFFFFFFFFFFFFFF"
# Five cells each way keeps the party on its two blocks' neighbours, inside the zone-map cell.
WALK = "idle:16," + ",".join(["right:40,left:40"] * 8)
TRACE = "23E7C2,23E9B0,23EA40,23E98F"
LOG = "7E1001,7E1003,7E1005,7E1007,7E00B6,7E00B8"
RATE_TRACE = "0082AF"
EXITS = {"23E9B0": "single", "23EA40": "mixed", "23E98F": "fixed"}
TERRAIN_DAY, TERRAIN_NIGHT = dq4encounter.TERRAIN_DAY, dq4encounter.TERRAIN_NIGHT
GRASS = 0x02


def stand(grid, props, cell):
    """(x, y) FC blocks: a walkable block and its walkable right neighbour inside zone-map cell (column, row),
    grass first, nearest the cell's centre."""
    c, r = cell
    best = None
    for y in range(16 * r, 16 * r + 16):
        for x in range(16 * c, 16 * c + 15):
            if y >= len(grid) or x + 1 >= len(grid[y]):
                continue
            if any(props(x + d, y) & 0x80 or props(x + d, y) in (dq4fieldport.ENTRANCE, dq4fieldport.RIGHT_HALF)
                   for d in (0, 1)):
                continue
            score = (grid[y][x] != GRASS or grid[y][x + 1] != GRASS, abs(x - 16 * c - 7) + abs(y - 16 * r - 8))
            if best is None or score < best[0]:
                best = (score, (x, y))
    if best is None:
        raise ValueError(f"zone-map cell {cell}: no two walkable blocks side by side")
    return best[1]


def lines(path):
    for line in path.read_text().splitlines():
        f = line.split()
        if len(f) >= 3:
            yield int(f[0]), f[1], dict(x.split("=") for x in f[2:] if "=" in x)


def groups(kv):
    b = b"".join(int(kv[k], 16).to_bytes(2, "little") for k in ("7E1001", "7E1003", "7E1005", "7E1007"))
    return [(m, c) for m, c in zip(b[:4], b[4:]) if m != 0xFF]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rom", required=True, type=Path)
    ap.add_argument("--dq4", default="rom/dq4.nes", type=Path)
    ap.add_argument("--dq5", default="rom/dq5.sfc", type=Path)
    ap.add_argument("--state", default="work/state/ship.mss", type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--jobs", type=int, default=4)
    args = ap.parse_args()
    mesence = Path(os.environ["MESENCE"])
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} is not empty")
    rom, state = args.rom.resolve(), args.state.resolve()
    data = rom.read_bytes()
    prg = ines.prg(args.dq4.read_bytes())
    import subprocess
    out.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, str(DQ5_TOOLS / "dq5encounterwrite.py"), args.dq5, "dump", "-o",
                    out / "encounter-orig.json"], check=True, capture_output=True)
    _, _, report = dq4fieldencounter.docs(prg, args.dq5.read_bytes(),
                                          json.loads((out / "encounter-orig.json").read_text(encoding="utf-8")))
    dq4groupcheck.WARP = DQ5_TOOLS / "lua" / "dq5warptrace.lua"

    def place(field, cell):
        grid, props = dq4fieldport.fc_field(prg, field)
        x, y = stand(grid, props, cell)
        if field == 0:
            _, rows = dq4encounter.zone_map(prg, 0)
            fc = rows[cell[1]][cell[0]] & 0x3F
        else:
            fc = dq4fieldencounter.FIELD3 if field == 3 else \
                dq4fieldencounter.FIELD1_TOP if cell[1] == 0 else dq4fieldencounter.FIELD1
        return (x, y), grid, props, fc

    def run(name, rates, delay=0):
        field, cell = ZONES[name]
        (x, y), grid, props, fc = place(field, cell)
        world = dq4fieldport.WORLDS[field]
        extra = {"POKE": f"7E1949={world:02X}"} if world else {}
        patch = dq4fieldport.warp_patch(data, *dq4fieldport.stand(x, y))
        scene = f"{name}-rate" if rates else f"{name}-zone{delay}"
        got = dq4groupcheck.scene(mesence, rom, state, out, scene, FIELD="{},{}".format(*dq4fieldport.stand(x, y)),
                                  ROMPATCH=patch if rates else f"{patch};{RATES}", TEST=f"wait:{delay},{WALK}" if delay else WALK, MAXF="2600",
                                  TRACE=RATE_TRACE if rates else TRACE, LOG=LOG, **extra)
        ram = (out / scene / "final.wram").read_bytes()
        want = report[f"{fc:02X}"]
        rows = list(lines(out / scene / "trace.txt"))
        base = {"fc_zone": f"{fc:02X}", "dq5_zone": want["zone"], "blocks": [[x, y], [x + 1, y]], "got": got,
                "1948": ram[0x1948]}
        if rates:
            return scene, {**base, **rate_report(data, prg, grid, fc, want["zone"], rows)}
        zones_seen = sorted({int(kv["A"], 16) & 0xFF for _, pc, kv in rows if pc == "23E7C2"})
        fights = [(EXITS[pc], groups(kv)) for _, pc, kv in rows if pc in EXITS]
        allowed = set(want["monsters"])
        return scene, {**base, "zones": zones_seen, "fights": fights,
                       "ok": zones_seen == [want["zone"]] and bool(fights)
                       and all(kind != "fixed" and {m for m, _ in g} <= allowed for kind, g in fights)}

    def rate_report(data, prg, grid, fc, zone, rows):
        """Per walked FC block kind: DQ5's chance of a fight per step (/256, the zone's coefficient x 00:82AF's Y
        >> 6) and FC's (base x 16 x the kind's day or night factor >> 8)."""
        import dq5encounter
        from dq5map import Rom
        coef = dq5encounter.area(Rom(data), zone)["coef"]
        base = dq4encounter.zone(prg, fc)["rate"]
        seen = {}
        for _, pc, kv in rows:
            if pc != RATE_TRACE or int(kv["A"], 16) & 0xFF != zone:
                continue
            kind = grid[int(kv["7E00B8"], 16) >> 1][int(kv["7E00B6"], 16) >> 1]
            y = int(kv["Y"], 16) & 0xFF
            fc_day, fc_night = (base * 16 * dq4encounter.rd(prg, t + kind) >> 8 for t in (TERRAIN_DAY, TERRAIN_NIGHT))
            row = seen.setdefault(f"{kind:02X}", {"y": y, "dq5": coef * y >> 6, "fc_day": fc_day,
                                                  "fc_night": fc_night, "steps": 0})
            row["steps"] += 1
        return {"coefficient": coef, "fc_base": base, "chances": seen,
                "ok": bool(seen) and all(v["dq5"] in (v["fc_day"], v["fc_night"]) for v in seen.values())}

    jobs = [(name, False, d) for name in ZONES for d in DELAYS] + [(name, True) for name in RATE_SCENES]
    with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
        results = dict(f.result() for f in [pool.submit(run, *j) for j in jobs])
    ok = all(r["ok"] for r in results.values())
    result = {"status": "passed" if ok else "failed", "scenes": dict(sorted(results.items()))}
    (out / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
