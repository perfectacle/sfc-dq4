"""FC field 0 as DQ5 world 0: block numbers for dq5fieldwrite.py, and the field cells of FC entrances.

FC block (x, y) of field 0 is DQ5 block (x, y) of world 0, so a DQ5 field cell ($B6, $B8, 8 px) is FC block
(x >> 1, y >> 1). FC field 0 is 250x250 blocks read at 3..252 (fc/dq4/tools/dq4field.py: rows and columns 0-2
read as sea); the DQ5 world is 256x256, and the rest is sea except a mountain island in the far corner where the
original DQ5 entrances of world 0 are parked (sfc/dq4/docs/dq4-field-format.md).

The blocks are DQ5's own field blocks with the terrain of the FC block (walk, ship, encounter terrain); their
art stays DQ5's until the DQ4 art replaces it.

  python sfc/dq4/tools/dq4fieldport.py map -o work/field/w0.bin
  python sfc/dq4/tools/dq4fieldport.py patch -o work/field/field.dq5patch.json --at 3A:8000
"""

import argparse
import functools
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
DQ5_TOOLS = TOOLS.parents[1] / "dq5" / "tools"
FC_TOOLS = TOOLS.parents[2] / "fc" / "dq4" / "tools"
for path in (TOOLS, DQ5_TOOLS, FC_TOOLS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

SIZE = 256
SEA = 0
MOUNTAIN = 9
# FC field block -> DQ5 world-0 block of the same terrain (DQ5 tile attribute 2A:D512 for walking, terrain nibble
# 03:CC48 for encounters and battle backgrounds). See the block table in sfc/dq4/docs/dq4-field-format.md.
BLOCKS = {
    0x00: SEA,       # sea: attribute 80, ship only, terrain 0
    0x01: 8,         # hill: 43, terrain 2
    0x02: 2,         # grass: 4A, terrain 6
    0x03: 366,       # bush: 4B, terrain B (DQ5's small trees)
    0x04: 354,       # forest: 4B, terrain 7
    0x05: 5,         # desert: 4C, terrain 1
    0x06: MOUNTAIN,  # mountain: 82, terrain 3
    0x07: 7,         # poison swamp: 4D, terrain 4
    0x08: 10,        # cave mouth, left half: 45, terrain C
    0x09: 10,        # cave mouth, right half
    0x0A: 1,         # reef: 81, terrain 8
    0x0B: 10,        # cave mouth
    0x0C: 17,        # shrine
    0x0D: 13,        # tower art (no entrance)
    0x0E: 5,         # rocky path
    0x0F: 5,
    0x10: 18,        # town
    0x11: 13,        # tower
    0x12: 153,       # castle, left half
    0x13: 154,       # castle, right half
    0x14: 5,         # dark rocky path (field 3)
    0x15: 21,        # signboard: 96-98
    0x16: 22,        # bridge: 4E, terrain 6
    0x17: 5,
    0x1D: 5,
    0x1E: 5,
}
# The original DQ5 entrances of world 0 move inside a 3x3 mountain island beyond the FC map: no walk or ship
# reaches it, so DQ5 towns are never entered from FC ground.
ISLAND = (253, 253)
PARK = (2 * ISLAND[0] + 3, 2 * ISLAND[1] + 3)
# FC exit block properties: 06 is an entrance, 07 the right half of a two-block entrance, which the game takes as
# the block to its left ($42 one less, measured on 02's castle and 41's cave).
ENTRANCE, RIGHT_HALF = 0x06, 0x07
# FC neighbour to leave a town onto: below first, as the party usually walks out downwards.
LEAVE_ORDER = ((0, 1), (-1, 0), (1, 0), (0, -1))
# 04:FD97 main entrance table: the operand of 2A:F24F (LDA long,X) points at it, also after dq5fieldtables moves it.
MAIN_TABLE_REF = 0x2AF250
WARP_GROUP = 0x01


def world(fc_grid):
    """DQ5 world-0 block numbers (row-major 256x256) of an FC field grid (rows of FC blocks, as dq4field.decode)."""
    unknown = sorted({v for row in fc_grid for v in row} - BLOCKS.keys())
    if unknown:
        raise ValueError(f"FC field blocks without a DQ5 block: {[f'{v:02X}' for v in unknown]}")
    if len(fc_grid) > ISLAND[1] or any(len(row) > ISLAND[0] for row in fc_grid):
        raise ValueError("the FC field reaches the parking island")
    grid = [SEA] * (SIZE * SIZE)
    for y, row in enumerate(fc_grid):
        for x, v in enumerate(row):
            grid[y * SIZE + x] = BLOCKS[v]
    for y in range(ISLAND[1], ISLAND[1] + 3):
        for x in range(ISLAND[0], ISLAND[0] + 3):
            grid[y * SIZE + x] = MOUNTAIN
    return grid


def pack(grid):
    """dq5fieldwrite.py map file: 16-bit little-endian block numbers, y*256+x."""
    if len(grid) != SIZE * SIZE:
        raise ValueError(f"{len(grid)} blocks, not {SIZE * SIZE}")
    return b"".join(v.to_bytes(2, "little") for v in grid)


def cells(x, y):
    """The four DQ5 field cells of FC block (x, y): DQ5 walks 8 px a step, so any of them can be stepped on."""
    return [(2 * x + dx, 2 * y + dy) for dy in (0, 1) for dx in (0, 1)]


def stand(x, y):
    """DQ5 cell to stand on FC block (x, y): its bottom-left cell, as dq4groupbuild.cell."""
    return 2 * x, 2 * y + 1


def entrance_blocks(props, blocks):
    """The FC blocks that enter by `blocks`: each one and the right half (property 07) next to it.
    props(x, y) is the FC block property. An entrance needs no entrance art: 古井戸 (1C) is a forest block."""
    out = []
    for x, y in blocks:
        out.append((x, y))
        if props(x + 1, y) == RIGHT_HALF:
            out.append((x + 1, y))
    return out


def door(props, blocks):
    """(DQ5 entrance cells, DQ5 cell the party leaves onto) of an FC group entered by FC blocks `blocks`. The party
    leaves onto the first walkable non-entrance FC neighbour (LEAVE_ORDER) of the first block, as FC leaves onto
    the block next to the entrance."""
    found = entrance_blocks(props, blocks)
    x, y = blocks[0]
    for dx, dy in LEAVE_ORDER:
        n = (x + dx, y + dy)
        if n not in found and not props(*n) & 0x80 and props(*n) not in (ENTRANCE, RIGHT_HALF):
            return [c for b in found for c in cells(*b)], stand(*n)
    raise ValueError(f"FC field ({x:02X},{y:02X}): no walkable neighbour to leave onto")


def world_of(group, arrivals):
    """World ($1949) an entrance of `group` enters in (2A:FEF5): 0 for group 05 and 50 up, else the group's
    arrival world code − 1; None when it never enters (54, or no world)."""
    if group == 0x54:
        return None
    if group == 0x05 or group >= 0x50:
        return 0
    code = arrivals.get(group, {}).get("world_code", 0)
    return code - 1 if code else None


def park(entries, arrivals):
    """Entrance table rows ({group, x, y}) with those entering in world 0 moved onto PARK. The rows stay, so
    every ルーラ group still has one (dq5fieldtables RULER_GROUPS)."""
    out = []
    for e in entries:
        row = {k: e[k] for k in ("group", "x", "y")}
        if world_of(e["group"], arrivals) == 0:
            row["x"], row["y"] = PARK
        out.append(row)
    return out


def warp_patch(rom, x, y):
    """dq5warp.lua ROMPATCH that puts FIELD=x,y into the entrance table the ROM reads. dq5warp writes the group-01
    row of 04:FD97, which dq5fieldtables moved; this writes the same row of the moved table."""
    from dq5map import lorom
    o = lorom(MAIN_TABLE_REF)
    table = rom[o] | rom[o + 1] << 8 | rom[o + 2] << 16
    a = table
    while rom[lorom(a)] != 0xFF:
        if rom[lorom(a)] == WARP_GROUP:
            at = lorom(a + 1)
            return f"{at:X}=" + (x.to_bytes(2, "little") + y.to_bytes(2, "little")).hex().upper()
        a += 5
    raise ValueError(f"no group {WARP_GROUP:02X} row in the entrance table at {table:06X}")


@functools.cache
def fc_field(prg):
    """(FC field 0 grid, property lookup) from the FC PRG."""
    import dq4block
    source = dq4block.Map(prg, field=0)
    grid = source.field
    return grid, lambda x, y: source.blocks["prop"].get(source.cell(x, y) & 0x1F, 0)


def write_map(prg, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pack(world(fc_field(prg)[0])))
    return path


def patch(dq5, prg, path, at):
    """dq5fieldwrite.py patch of world 0. Every block is below 512, so dq5fieldwrite needs no planes and never reads
    the glow cell a chest patch moves: the original ROM makes the same patch as the ROM with the chest patch."""
    grid = path.with_suffix(".bin")
    write_map(prg, grid)
    proc = subprocess.run([sys.executable, str(DQ5_TOOLS / "dq5fieldwrite.py"), str(dq5), "patch", "--world", "0",
                           str(grid), "-o", str(path), "--at", at, "--name", "dq4-field"], capture_output=True, text=True)
    if proc.returncode:
        raise RuntimeError(f"dq5fieldwrite.py: {proc.stderr[-1500:]}")
    return path


def main():
    from kr_patch.fc import ines
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("map", "patch"))
    ap.add_argument("--dq5", default="rom/dq5.sfc", type=Path)
    ap.add_argument("--dq4", default="rom/dq4.nes", type=Path)
    ap.add_argument("-o", "--out", required=True, type=Path)
    ap.add_argument("--at", default="3A:8000")
    args = ap.parse_args()
    prg = ines.prg(args.dq4.read_bytes())
    if args.cmd == "map":
        print(write_map(prg, args.out))
    else:
        print(patch(args.dq5, prg, args.out, args.at))


if __name__ == "__main__":
    main()
