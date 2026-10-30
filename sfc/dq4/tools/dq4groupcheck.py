"""Walk the links of the new DQ4 groups built by dq4groupbuild.py in MesenCE.

  stairs  every FC stair: warp onto a walkable FC neighbour, step onto the stair, expect the destination
          map and the cell of the linked stair (dq4groupbuild.cell), or for a stair to the field the cell the
          group leaves onto (dq4groupbuild.doors)
  area    02/00 gate (open flags) up into 02/01, and 02/01 down off the bottom edge back to the gate.
          The bottom edge is one cell away, so a short press: a held key walks on after landing
  exit    from each group's field arrival, the way out (LINKS "out") to the field: the cell it leaves onto
  stay    the field arrival with no input: the party stays (an arrival off the map leaves at once)
  enter   on FC field 0: warp (dq5warp.lua FIELD) onto each walkable FC neighbour of each entrance block, on
          either DQ5 row or column of it, and step onto the block: the group arrival

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
import dq4fieldport  # noqa: E402
import dq4talk  # noqa: E402
from dq4environmentmap import block_prop  # noqa: E402
from dq4environmentrom import GATE_KIND, objects  # noqa: E402
from dq4groupbuild import LINKS, cell, doors, entrance_doors, exit_order, fc_numbers, placement, tag  # noqa: E402
from dq5exitcheck import dp86_allowed, warp_exit  # noqa: E402
from dq5progresscheck import environment  # noqa: E402
from kr_patch.fc import ines  # noqa: E402

WARP = DQ5_TOOLS / "lua" / "dq5warp.lua"
DIRS = {(0, -1): "up", (1, 0): "right", (0, 1): "down", (-1, 0): "left"}
END = re.compile(r"end map (\w\w)/(\w\w) (cell|field) (\d+),(\d+)")
# Frames a direction is held: the party first turns, then moves 8 px (one cell) per 8 frames; an FC cell
# is two cells.
PRESS = 32
# FC door block property 97, the highest lock of the doors 94-97 (fc/dq4/docs/dq4-block-format.md). The port draws
# it as a barred door and never opens it, so a stair
# reached only through one (エンドール 04/01 (04,06)·(0C,06)) has no start; it is reported as skipped.
LAST_KEY_DOOR = 0x97


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


def field_scene(mesence, rom, state, out, name, x, y, test, **extra):
    """scene from field cell (x, y): dq5warp.lua FIELD with the row of the moved entrance table it walks out by."""
    return scene(mesence, rom, state, out, name, FIELD=f"{x},{y}",
                 ROMPATCH=dq4fieldport.warp_patch(rom.read_bytes(), x, y), TEST=test, **extra)


def enter_starts(props, blocks):
    """(DQ5 start cell, direction) for each walkable FC neighbour of each FC entrance block in `blocks` that is not
    itself one, twice: from either DQ5 row or column of the neighbour, so every DQ5 cell of the block is stepped on."""
    for bx, by in blocks:
        for (dx, dy), d in DIRS.items():
            nx, ny = bx - dx, by - dy
            if (nx, ny) in blocks or props(nx, ny) & 0x80:
                continue
            for k in (0, 1):
                # DQ5 cells of the neighbour on the line through cell k of the entrance block's row or column.
                sx = 2 * nx + (k if dx == 0 else (1 if dx > 0 else 0))
                sy = 2 * ny + (k if dy == 0 else (1 if dy > 0 else 0))
                yield (sx, sy), d


def same_place(got, want):
    """Same map and FC cell: after landing, a held key or the engine's extra step (2A:F69F) can move the
    party within the FC cell, so DQ5 cells are compared as FC cells."""
    if "field" in want:
        return got == want
    return got.get("map") == want["map"] and "cell" in got and \
        [v // 2 for v in got["cell"]] == [v // 2 for v in want["cell"]]


def walkable(source, x, y):
    return 0 <= x < source.w and 0 <= y < source.h and not block_prop(source, source.cell(x, y) & 31) & 0x80


def stair_scenes(prg, groups):
    place = placement(prg)
    found = doors(prg)
    each = entrance_doors(prg)
    for group, link in ((g, part) for g, parts in LINKS.items() if g in groups for part in parts):
        fc_group = link["fc"]
        cache = {}
        for fc_number in fc_numbers(prg, fc_group):
            number = place[fc_group, fc_number][1]
            order = exit_order(prg, fc_group, fc_number)
            source = dq4block.Map(prg, fc_group, fc_number)
            to = {(e["x"], e["y"]): e["to"] for e in dq4block.exit_links(prg, fc_group, fc_number, cache)}
            for i, (x, y) in enumerate(order):
                # Every walkable neighbour, then later starts: a wandering person can stand on the stair or in
                # the way (FC starts some walking people on a stair).
                starts = [(f"{group:02X}/{number:02X},{','.join(map(str, cell(x - dx, y - dy)))}",
                           f"wait:{late},{d}:{PRESS},wait:400" if late else f"{d}:{PRESS},wait:400")
                          for late in range(0, 1200, 120) for (dx, dy), d in DIRS.items()
                          if walkable(source, x - dx, y - dy) and (x - dx, y - dy) not in order]
                if not starts:
                    if any(0 <= x - dx < source.w and 0 <= y - dy < source.h
                           and block_prop(source, source.cell(x - dx, y - dy) & 31) == LAST_KEY_DOOR for dx, dy in DIRS):
                        yield f"stair-{group:02X}{number:02X}-{i}", None, "behind a door 97, never opened in this port"
                        continue
                    raise ValueError(f"{fc_group:02X}/{fc_number:02X} ({x:02X},{y:02X}): no walkable cell next to the stair")
                dest = to[x, y]
                if "field" in dest:
                    # The special exit 0 leaves by the FC group's aux entrance. Without one there is no field
                    # cell to expect (dq4groupbuild.exit_rows refuses it in a group of several FC groups).
                    if not link["field"]:
                        continue
                    by_stair = {s: b for b, s in link.get("stairs", {}).items()}
                    leave = each[(fc_group, *by_stair[x, y])][1] if (x, y) in by_stair else found[fc_group][1]
                    yield f"stair-{group:02X}{number:02X}-{i}", starts, {"field": list(leave)}
                    continue
                there_group, there_number = place[dest["group"], dest["index"]]
                yield (f"stair-{group:02X}{number:02X}-{i}", starts,
                       {"map": f"{there_group:02X}/{there_number:02X}", "cell": list(cell(dest["x"], dest["y"]))})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rom", required=True, type=Path)
    ap.add_argument("--dq4", default="rom/dq4.nes", type=Path)
    ap.add_argument("--state", default="work/state/ship.mss", type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--groups", type=lambda v: {int(g, 16) for g in v.split(",")}, default=set(LINKS),
                    help="DQ5 groups to walk (hex, comma-separated); all by default")
    args = ap.parse_args()
    mesence = Path(os.environ["MESENCE"])
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} is not empty")
    rom, state = args.rom.resolve(), args.state.resolve()
    prg = ines.prg(args.dq4.read_bytes())

    stairs = list(stair_scenes(prg, args.groups))
    skipped = {name: why for name, starts, why in stairs if starts is None}
    jobs = [(name, [{"TO": to, "TEST": test} for to, test in starts], want) for name, starts, want in stairs
            if starts is not None]
    found = doors(prg)
    _, props = dq4fieldport.fc_field(prg)
    for group, link in ((g, part) for g, parts in LINKS.items() if g in args.groups for part in parts):
        if not link["field"]:
            continue
        x, y = cell(*link["arrival"])
        leave = list(found[link["fc"]][1])
        arrival = f"{group:02X}/{placement(prg)[link['fc'], link.get('map', 0)][1]:02X}"
        to = f"{arrival},{x},{y}"
        out_test = f"{link['out']},wait:400"
        jobs.append((f"exit-{tag(group, link)}", [{"TO": to, "TEST": out_test}], {"field": leave}))
        # Without input the party stays: an arrival off the map steps onto the edge exit at once, and the exit
        # scene would pass without its inputs.
        jobs.append((f"stay-{tag(group, link)}", [{"TO": to, "TEST": "wait:400"}], {"map": arrival, "cell": [x, y]}))
        # Every start must enter: each is a scene of its own, not a retry.
        stairs = link.get("stairs", {})
        for part in [[b] for b in link["field"]] if stairs else [link["field"]]:
            blocks = dq4fieldport.entrance_blocks(props, part)
            ex, ey = cell(*stairs[part[0]]) if stairs else (x, y)
            for (sx, sy), d in enter_starts(props, blocks):
                jobs.append((f"enter-{tag(group, link)}-{sx},{sy}-{d}", [{"field": (sx, sy), "TEST": f"{d}:{PRESS},wait:400"}],
                             {"map": arrival, "cell": [ex, ey]}))
    results = {}
    def tries(name, starts, want):
        for n, extra in enumerate(starts):
            sub = f"{name}-{n}" if n else name
            if "field" in extra:
                got = field_scene(mesence, rom, state, out, sub, *extra["field"], extra["TEST"])
            else:
                got = scene(mesence, rom, state, out, sub, **extra)
            if same_place(got, want):
                break
        return got, n

    with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
        futures = {pool.submit(tries, name, starts, want): (name, want) for name, starts, want in jobs}
        for future in concurrent.futures.as_completed(futures):
            name, want = futures[future]
            got, n = future.result()
            results[name] = {"got": got, "want": want, "ok": same_place(got, want), "start": n}
    if placement(prg)[0x02, 0][0] in args.groups:
        area_scenes(mesence, rom, prg, state, out, results)
    ok = all(r["ok"] for r in results.values())
    report = {"status": "passed" if ok else "failed", "scenes": dict(sorted(results.items())), "skipped": skipped}
    (out / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if ok else 1


def area_scenes(mesence, rom, prg, state, out, results):
    """The only FC exit-table cells of the ported groups: 02/00's gate into 02/01 and back."""
    # Area moves: the gate's open flag is cleared on a group change, so set it from another map of the group.
    # FC 02 バトランド: the gate (02/00) and the area moves between 02/00 and 02/01.
    castle = 0x02
    front, throne, side_map = (f"{g:02X}/{n:02X}" for g, n in (placement(prg)[castle, k] for k in (0, 1, 3)))
    source = dq4block.Map(prg, castle, 0)
    gx, gy, _, _ = next(o for o in objects(source) if o[2] == GATE_KIND)
    # The hop cell needs a free cell below: the warp steps down from it, or up when that is blocked (off the
    # top row of the map that is the field).
    other = dq4block.Map(prg, castle, 3)
    people = {dq4talk.pos(r, n) for n in (False, True) for r in dq4talk.npc_list(prg, castle, 3, n)}
    hx, hy = cell(*next((x, y) for y in range(1, other.h) for x in range(other.w)
                        if all(walkable(other, x + dx, y + dy) and (x + dx, y + dy) not in people
                               for dx, dy in ((0, 0), (1, 0), (0, 1), (1, 1)))))
    side = scene(mesence, rom, state, out, "area-hop", TO=f"{side_map},{hx},{hy}", SAVE="hop.mss")
    hop = out / "area-hop" / "hop.mss"
    area = [("area-up", {"TO": f"{front},{gx},{gy + 5}", "SET": "21C2=FF", "TEST": f"up:{PRESS},wait:400"},
             {"map": throne, "cell": list(cell(0x0F, 0x23))}),
            # The right end of the three-cell rect maps to the right end of the arrival (2A:F650).
            ("area-up-right", {"TO": f"{front},{gx + 2},{gy + 5}", "SET": "21C2=FF", "TEST": f"up:{PRESS},wait:400"},
             {"map": throne, "cell": list(cell(0x10, 0x23))}),
            ("area-down", {"TO": f"{throne},{','.join(map(str, cell(0x0F, 0x23)))}", "TEST": "down:8,wait:400"},
             {"map": front, "cell": list(cell(0x12, 0x0B))})]
    for name, extra, want in area:
        got = scene(mesence, rom, hop if hop.exists() else state, out, name, ANYWHERE=1, **extra)
        results[name] = {"got": got, "want": want, "ok": same_place(got, want)}
    results["area-hop"] = {"got": side, "ok": "map" in side}


if __name__ == "__main__":
    sys.exit(main())
