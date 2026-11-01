"""FC fields 0, 1 and 3 as DQ5 worlds 0, 1 and 2: block numbers for dq5fieldwrite.py, and the field cells of FC
entrances.

FC block (x, y) of a field is DQ5 block (x, y) of its world (WORLDS), so a DQ5 field cell ($B6, $B8, 8 px) is FC
block (x >> 1, y >> 1). FC field 0 is 250x250 blocks read at 3..252 (fc/dq4/tools/dq4field.py: rows and columns
0-2 read as sea); the DQ5 world is 256x256, of which worlds 1 and 2 show only the top-left 128x128. The rest is sea
except a mountain island in the far corner of each world where its original DQ5 entrances are parked
(sfc/dq4/docs/dq4-field-format.md).

Each FC block kind has a DQ5 block of its own (OWN_BLOCKS, from 511) drawn with the DQ4 art (dq4fieldgfx.py) and
taking the terrain of the DQ5 field block BLOCKS borrows (walk, ship, encounter terrain). The sea is DQ5's block 0.

  python sfc/dq4/tools/dq4fieldport.py map -o work/field/w0.bin [--field 1]
  python sfc/dq4/tools/dq4fieldport.py patch -o work/field/field.dq5patch.json --at 3A:8000
"""

import argparse
import functools
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
# FC field -> DQ5 world ($1949).
WORLDS = {0: 0, 1: 1, 3: 2}
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
# Per FC field, kinds whose terrain differs from BLOCKS. Field 3 makes its hills impassable (08:$8A34 gives block 01
# property 80), so they take the mountain's terrain and keep the hill art.
FIELD_BLOCKS = {3: {0x01: MOUNTAIN}}
# Places of the field blocks and planes, free in both the dq4groupbuild ROM and the chapter-1 ROM (dq4chapter1.py).
# The planes take the bank of "planes" (hooks and the 1-bit planes) and one bank per world after it; the chapter-1
# menu ROM already uses bank 58. The tiles need no place: they stay 512 and go back in place (dq4fieldgfx.free_slots).
GFX_AT = {"blocks": "54:C000", "planes": "50:8000"}
# First DQ5 block dq5fieldtables --blocks-at adds: 511 shares its slot with upper-layer block 0 in the original table.
FIRST_BLOCK = 511


def borrowed(field, kind):
    return FIELD_BLOCKS.get(field, {}).get(kind, BLOCKS[kind])


@functools.cache
def _numbers():
    """(FIELD_ART asset, borrowed block) -> own DQ5 block, numbered from FIRST_BLOCK: field 0's kinds in FC kind
    order (BLOCKS), then the FIELD_BLOCKS ones, so field 0 keeps its numbers when a field adds a block."""
    from dq4environmentmap import FIELD_ART
    numbers = {}
    pairs = [(kind, BLOCKS[kind]) for kind in sorted(BLOCKS)]
    pairs += [(kind, m) for field in sorted(FIELD_BLOCKS) for kind, m in sorted(FIELD_BLOCKS[field].items())]
    for kind, m in pairs:
        if m != SEA:
            numbers.setdefault((FIELD_ART[kind][0], m), FIRST_BLOCK + len(numbers))
    return numbers


def own_blocks(field=0):
    """FC block kind -> its own DQ5 block on FC field `field`: one per FIELD_ART asset and borrowed block. The sea
    keeps DQ5's block 0, drawn with the DQ4 moving water (dq4fieldgfx)."""
    from dq4environmentmap import FIELD_ART
    out = {}
    for kind in sorted(BLOCKS):
        m = borrowed(field, kind)
        out[kind] = SEA if m == SEA else _numbers()[FIELD_ART[kind][0], m]
    return out


def new_blocks():
    """[(own DQ5 block, an FC kind drawn on it, borrowed DQ5 block)] of every own block, by number."""
    from dq4environmentmap import FIELD_ART
    kinds = {}
    for field in [0, *sorted(FIELD_BLOCKS)]:
        for kind in sorted(BLOCKS):
            m = borrowed(field, kind)
            if m != SEA:
                kinds.setdefault(_numbers()[FIELD_ART[kind][0], m], (kind, m))
    return [(n, *kinds[n]) for n in sorted(kinds)]


OWN_BLOCKS = own_blocks()
# The original DQ5 entrances of each world move inside a 3x3 mountain island beyond the FC map: no walk or ship
# reaches it, so DQ5 towns are never entered from FC ground. Worlds 1 and 2 show only their top-left 128x128.
ISLANDS = {0: (253, 253), 1: (125, 125), 2: (125, 125)}
PARKS = {w: (2 * x + 3, 2 * y + 3) for w, (x, y) in ISLANDS.items()}
ISLAND, PARK = ISLANDS[0], PARKS[0]
# FC exit block properties: 06 is an entrance, 07 the right half of a two-block entrance, which the game takes as
# the block to its left ($42 one less, measured on 02's castle and 41's cave).
ENTRANCE, RIGHT_HALF = 0x06, 0x07
# FC neighbour to leave a town onto: below first, as the party usually walks out downwards.
LEAVE_ORDER = ((0, 1), (-1, 0), (1, 0), (0, -1))
# 04:FD97 main entrance table: the operand of 2A:F24F (LDA long,X) points at it, also after dq5fieldtables moves it.
MAIN_TABLE_REF = 0x2AF250
WARP_GROUP = 0x01


def world(fc_grid, field=0):
    """DQ5 block numbers (row-major 256x256) of the world of FC field `field` from its grid (rows of FC blocks, as
    fc_field)."""
    own = own_blocks(field)
    unknown = sorted({v for row in fc_grid for v in row} - own.keys())
    if unknown:
        raise ValueError(f"FC field blocks without a DQ5 block: {[f'{v:02X}' for v in unknown]}")
    island = ISLANDS[WORLDS[field]]
    if len(fc_grid) > island[1] or any(len(row) > island[0] for row in fc_grid):
        raise ValueError("the FC field reaches the parking island")
    grid = [SEA] * (SIZE * SIZE)
    for y, row in enumerate(fc_grid):
        for x, v in enumerate(row):
            grid[y * SIZE + x] = own[v]
    for y in range(island[1], island[1] + 3):
        for x in range(island[0], island[0] + 3):
            grid[y * SIZE + x] = own[0x06]
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
    """Entrance table rows ({group, x, y}) with each moved onto the PARKS cell of the world it enters in (group 54
    never enters and stays). The rows stay, so every ルーラ group still has one (dq5fieldtables RULER_GROUPS)."""
    out = []
    for e in entries:
        row = {k: e[k] for k in ("group", "x", "y")}
        w = world_of(e["group"], arrivals)
        if w is not None:
            row["x"], row["y"] = PARKS[w]
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
def fc_field(prg, field=0):
    """(FC field grid, property lookup) from the FC PRG. The grid stops where the row data does
    (dq4field.extent): field 3's width and height bytes are code (250x164) and past its 62x54 the game reads the
    next rows' data, all beyond its impassable hills."""
    import dq4block
    import dq4field
    source = dq4block.Map(prg, field=field)
    w, h = dq4field.extent(prg, field)
    grid = [row[:w] for row in source.field[:h]]
    return grid, lambda x, y: source.blocks["prop"].get(source.cell(x, y) & 0x1F, 0)


def write_map(prg, path, field=0):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pack(world(fc_field(prg, field)[0], field)))
    return path


def _run(tool, *args):
    import dq4buildcache
    dq4buildcache.run(DQ5_TOOLS / tool, *args)


def patch(dq5, prg, path, at, gfx_at=GFX_AT):
    """Patch lists of the field, in build order: the DQ4 tiles (dq5fieldgfxwrite.py), their blocks (dq5fieldtables.py
    --blocks-at, made from a ROM with the tiles) and the three worlds
    (dq5fieldwrite.py, made from a ROM with both: blocks from 511 need the moved block table; one call, as the
    plane hook is shared). path names the map's
    list; the others sit next to it. The original ROM's cells that 00:CF50 changes are all sea (block 0) on the FC
    map, and the chest patch does not move them, so the ROMs need no chest patch."""
    import dq4fieldgfx
    folder = path.parent / "fieldgfx"
    gfx, table = dq4fieldgfx.gfx_doc(dq5, folder)
    lists = [path.with_name("field-gfx.dq5patch.json"), path.with_name("field-blocks.dq5patch.json"), path]
    _run("dq5fieldgfxwrite.py", dq5, "patch", gfx, "-o", lists[0], "--name", "dq4-field-gfx")
    with_gfx = folder / "gfx.sfc"
    _run("dq5build.py", dq5, "build", lists[0], "--size", 4, "-o", with_gfx)
    _run("dq5fieldtables.py", with_gfx, "patch", table, "-o", lists[1], "--blocks-at", gfx_at["blocks"],
         "--name", "dq4-field-blocks")
    with_blocks = folder / "blocks.sfc"
    _run("dq5build.py", dq5, "build", *lists[:2], "--size", 4, "-o", with_blocks)
    grids = [write_map(prg, path.with_name(f"{path.stem}-w{w}.bin"), field) for field, w in WORLDS.items()]
    worlds = [a for w in WORLDS.values() for a in ("--world", w)]
    _run("dq5fieldwrite.py", with_blocks, "patch", *grids, *worlds, "-o", path, "--at", at,
         "--planes-at", gfx_at["planes"], "--name", "dq4-field")
    return lists


def main():
    from kr_patch.fc import ines
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("map", "patch"))
    ap.add_argument("--dq5", default="rom/dq5.sfc", type=Path)
    ap.add_argument("--dq4", default="rom/dq4.nes", type=Path)
    ap.add_argument("-o", "--out", required=True, type=Path)
    ap.add_argument("--at", default="3A:8000")
    ap.add_argument("--field", type=int, default=0, choices=sorted(WORLDS))
    args = ap.parse_args()
    prg = ines.prg(args.dq4.read_bytes())
    if args.cmd == "map":
        print(write_map(prg, args.out, args.field))
    else:
        print(*patch(args.dq5, prg, args.out, args.at))


if __name__ == "__main__":
    main()
