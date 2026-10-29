"""Walk the links of the new DQ4 groups built by dq4groupbuild.py in MesenCE.

  stairs  every FC stair: warp onto a walkable FC neighbour, step onto the stair, expect the destination
          map and the cell of the linked stair (dq4groupbuild.cell)
  area    02/00 gate (open flags) up into 02/01, and 02/01 down off the bottom edge back to the gate.
          The bottom edge is one cell away, so a short press: a held key walks on after landing
  exit    the map edge from each group's field arrival out to the field: the aux entrance (X, Y+1)
  enter   from the field state (341,56) walk to each group's entrance, expect the group's arrival cell

  MESENCE=… LIBDIR=… python sfc/dq4/tools/dq4groupcheck.py --rom work/dq4-groups/groups.sfc \\
      --state work/state/ship.mss --out work/dq4-groups/check
"""

import argparse
import concurrent.futures
import json
import os
import re
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
DQ5_TOOLS = TOOLS.parents[1] / "dq5" / "tools"
FC_TOOLS = TOOLS.parents[2] / "fc" / "dq4" / "tools"
for path in (TOOLS, DQ5_TOOLS, FC_TOOLS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import dq4block  # noqa: E402
import dq4talk  # noqa: E402
from dq4environmentmap import block_prop  # noqa: E402
from dq4environmentrom import GATE_KIND, objects  # noqa: E402
from dq4groupbuild import LINKS, cell, exit_order, fc_numbers  # noqa: E402
from dq5exitcheck import dp86_allowed, warp_exit  # noqa: E402
from dq5progresscheck import environment  # noqa: E402
from kr_patch.fc import ines  # noqa: E402

WARP = DQ5_TOOLS / "lua" / "dq5warp.lua"
WALK = DQ5_TOOLS / "lua" / "dq5tablecheck.lua"
FIELD_START = (341, 56)
DIRS = {(0, -1): "up", (1, 0): "right", (0, 1): "down", (-1, 0): "left"}
END = re.compile(r"end map (\w\w)/(\w\w) (cell|field) (\d+),(\d+)")
# Frames a direction is held: the party first turns, then moves 8 px (one cell) per 8 frames; an FC cell
# is two cells.
PRESS = 32


def scene(mesence, rom, state, out, name, **extra):
    dest = out / name
    dest.mkdir(parents=True)
    env = environment(os.environ["LIBDIR"], state, dest)
    env.update({"MAXF": "2400", "WARPEXIT": f"{warp_exit(rom):X}", "DP86OK": dp86_allowed(rom),
                **{k: str(v) for k, v in extra.items()}})
    subprocess.run([str(mesence), "--testrunner", str(rom), str(WARP), "--Snes.DisableFrameSkipping=true"],
                   env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=300, check=False)
    text = (dest / "warp.txt").read_text(encoding="utf-8") if (dest / "warp.txt").exists() else ""
    found = END.findall(text)
    if not found:
        return {"error": text[-300:]}
    g, m, kind, x, y = found[-1]
    where = {"map": f"{g}/{m}"} if kind == "cell" else {}
    where[kind] = [int(x), int(y)]
    return where


def walk(mesence, rom, state, out, name, pre):
    """Play inputs from a saved state (dq5tablecheck.lua with the dq5msg.lua driver) and read where the
    party ends from the final WRAM."""
    dest = out / name
    dest.mkdir(parents=True)
    env = environment(os.environ["LIBDIR"], state, dest)
    env.update(DRIVER=str(DQ5_TOOLS / "lua" / "dq5msg.lua"), MAXF="900", PRE=pre)
    subprocess.run([str(mesence), "--testrunner", str(rom), str(WALK), "--Snes.DisableFrameSkipping=true"],
                   env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=300, check=False)
    ram = (dest / "final.wram").read_bytes()
    if ram[0xBE] & 0x80:
        return {"map": f"{ram[0xBC]:02X}/{ram[0xBD]:02X}", "cell": [ram[0x3020], ram[0x3080]]}
    return {"field": [int.from_bytes(ram[0xB6:0xB8], "little"), int.from_bytes(ram[0xB8:0xBA], "little")]}


def same_place(got, want):
    """Same map and FC cell: after landing, a held key or the engine's extra step (2A:F69F) can move the
    party within the FC cell, so DQ5 cells are compared as FC cells."""
    if "field" in want:
        return got == want
    return got.get("map") == want["map"] and "cell" in got and \
        [v // 2 for v in got["cell"]] == [v // 2 for v in want["cell"]]


def walkable(source, x, y):
    return 0 <= x < source.w and 0 <= y < source.h and not block_prop(source, source.cell(x, y) & 31) & 0x80


def stair_scenes(prg):
    for group, link in LINKS.items():
        fc_group = link["fc"]
        numbers = fc_numbers(group)
        order = {n: exit_order(prg, fc_group, n) for n in numbers}
        cache = {}
        for number in numbers:
            source = dq4block.Map(prg, fc_group, number)
            to = {(e["x"], e["y"]): e["to"] for e in dq4block.exit_links(prg, fc_group, number, cache)}
            for i, (x, y) in enumerate(order[number]):
                # Every walkable neighbour, then later starts: a wandering person can stand on the stair or in
                # the way (FC starts some walking people on a stair).
                starts = [(f"{group:02X}/{number:02X},{','.join(map(str, cell(x - dx, y - dy)))}",
                           f"wait:{late},{d}:{PRESS},wait:400" if late else f"{d}:{PRESS},wait:400")
                          for late in range(0, 1200, 120) for (dx, dy), d in DIRS.items()
                          if walkable(source, x - dx, y - dy) and (x - dx, y - dy) not in order[number]]
                if not starts:
                    raise ValueError(f"{fc_group:02X}/{number:02X} ({x:02X},{y:02X}): no walkable cell next to the stair")
                dest = to[x, y]
                yield (f"stair-{group:02X}{number:02X}-{i}", starts,
                       {"map": f"{group:02X}/{dest['index']:02X}", "cell": list(cell(dest["x"], dest["y"]))})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rom", required=True, type=Path)
    ap.add_argument("--dq4", default="rom/dq4.nes", type=Path)
    ap.add_argument("--state", default="work/state/ship.mss", type=Path)
    ap.add_argument("--field-state", default="work/state/field-free.mss", type=Path, help="field (341,56)")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--jobs", type=int, default=4)
    args = ap.parse_args()
    mesence = Path(os.environ["MESENCE"])
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} is not empty")
    rom, state = args.rom.resolve(), args.state.resolve()
    prg = ines.prg(args.dq4.read_bytes())

    jobs = [(name, [{"TO": to, "TEST": test} for to, test in starts], want) for name, starts, want in stair_scenes(prg)]
    for group, link in LINKS.items():
        x, y = cell(*link["arrival"])
        fx, fy = link["field"]
        jobs.append((f"exit-{group:02X}", [{"TO": f"{group:02X}/00,{x},{y}", "TEST": f"{link['out']}:{PRESS * 2},wait:400"}],
                     {"field": [fx, fy + 1]}))
    results = {}
    # Entering from the field starts on the free field cell (341,56) of --field-state: dq5warp's FIELD
    # rewrites the entrance table that this build moves.
    for group, link in LINKS.items():
        fx, fy = link["field"]
        if fy != FIELD_START[1]:
            raise ValueError("field entrances must be on the start row")
        step = "right" if fx > FIELD_START[0] else "left"
        x, y = cell(*link["arrival"])
        got = walk(mesence, rom, args.field_state.resolve(), out, f"enter-{group:02X}",
                   f"{step}:{abs(fx - FIELD_START[0]) * 16},wait:400")
        want = {"map": f"{group:02X}/00", "cell": [x, y]}
        results[f"enter-{group:02X}"] = {"got": got, "want": want, "ok": same_place(got, want)}
    def tries(name, starts, want):
        for n, extra in enumerate(starts):
            got = scene(mesence, rom, state, out, f"{name}-{n}" if n else name, **extra)
            if same_place(got, want):
                break
        return got, n

    with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
        futures = {pool.submit(tries, name, starts, want): (name, want) for name, starts, want in jobs}
        for future in concurrent.futures.as_completed(futures):
            name, want = futures[future]
            got, n = future.result()
            results[name] = {"got": got, "want": want, "ok": same_place(got, want), "start": n}

    # Area moves: the gate's open flag is cleared on a group change, so set it from another map of the group.
    source = dq4block.Map(prg, LINKS[0x36]["fc"], 0)
    gx, gy, _, _ = next(o for o in objects(source) if o[2] == GATE_KIND)
    # The hop cell needs a free cell below: the warp steps down from it, or up when that is blocked (off the
    # top row of the map that is the field).
    other = dq4block.Map(prg, LINKS[0x36]["fc"], 3)
    people = {dq4talk.pos(r, n) for n in (False, True) for r in dq4talk.npc_list(prg, LINKS[0x36]["fc"], 3, n)}
    hx, hy = cell(*next((x, y) for y in range(1, other.h) for x in range(other.w)
                        if all(walkable(other, x + dx, y + dy) and (x + dx, y + dy) not in people
                               for dx, dy in ((0, 0), (1, 0), (0, 1), (1, 1)))))
    side = scene(mesence, rom, state, out, "area-hop", TO=f"36/03,{hx},{hy}", SAVE="hop.mss")
    hop = out / "area-hop" / "hop.mss"
    area = [("area-up", {"TO": f"36/00,{gx},{gy + 5}", "SET": "21C2=FF", "TEST": f"up:{PRESS},wait:400"},
             {"map": "36/01", "cell": list(cell(0x0F, 0x23))}),
            # The right end of the three-cell rect maps to the right end of the arrival (2A:F650).
            ("area-up-right", {"TO": f"36/00,{gx + 2},{gy + 5}", "SET": "21C2=FF", "TEST": f"up:{PRESS},wait:400"},
             {"map": "36/01", "cell": list(cell(0x10, 0x23))}),
            ("area-down", {"TO": "36/01,30,71", "TEST": "down:8,wait:400"},
             {"map": "36/00", "cell": list(cell(0x12, 0x0B))})]
    for name, extra, want in area:
        got = scene(mesence, rom, hop if hop.exists() else state, out, name, ANYWHERE=1, **extra)
        results[name] = {"got": got, "want": want, "ok": same_place(got, want)}
    results["area-hop"] = {"got": side, "ok": "map" in side}
    ok = all(r["ok"] for r in results.values())
    report = {"status": "passed" if ok else "failed", "scenes": dict(sorted(results.items()))}
    (out / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
