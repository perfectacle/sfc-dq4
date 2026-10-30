"""DQ4 art for the FC field in DQ5 world 0: field tiles, tile palettes and blocks from the dq4environmentart assets.

Each FC field art (dq4environmentmap.FIELD_ART) becomes a DQ5 block of its own from 511 (dq4fieldport.OWN_BLOCKS),
so DQ5's blocks stay as they are for worlds 1 and 2. A new block keeps the terrain nibble of the DQ5 block
dq4fieldport.BLOCKS borrows, and each of its tiles the attribute of that block's tile in the same quarter, so
walking, ship and encounters stay those of the borrowed block. The art is drawn on the lower layer; the upper layer
is empty (tile 0, 00:BCA8 then reads the lower tile's attribute).

Colours are DQ5's own world-0 field palette: each 8x8 tile takes palette line 2 or 3 (nibble 0 or 1) and colours
1-13 of it, whichever is nearer to the art. The time-of-day sets of DQ5 (01:A16B) then darken the field at night as
they do DQ5's. Colours 14 and 15 are cycled by 02:ABEF, so they are left out.

The sea stays DQ5's block 0 and its moving water: the game turns tiles 4, 5, 20 and 21 a pixel at a time from an
uncompressed copy at 01:A719 (01:C5C8 points [$A5] there, 01:C746 makes 16 turns into 7E:C000), not from the field
tiles, and dq5fieldgfxwrite.py does not write that copy. The reef is the DQ4 rocks on the upper layer over that sea.

  python sfc/dq4/tools/dq4fieldgfx.py preview -o work/fieldgfx/preview.png
"""

import argparse
import functools
import json
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
DQ5_TOOLS = TOOLS.parents[1] / "dq5" / "tools"
for path in (TOOLS, DQ5_TOOLS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import dq4fieldport  # noqa: E402

TILES = 512
# World-0 palette set of the day: 01:A16B picks set 2 for $075E 2-237 (sfc/dq5/docs/dq5-field-format.md 「팔레트」).
DAY_SET = 2
LINES = (0, 1)  # nibble n is palette line n + 2
COLOURS = range(1, 14)
SEA_TILES = (4, 5, 20, 21)
REEF = 0x0A
# Art colours (drawn for town maps) moved onto DQ5 field colours before the nearest colour is taken; key None is for
# every asset. The green ramp (dq4environmentart bank 1) goes one step darker onto DQ5's four field greens, so grass
# has DQ5's mid-green ground with light specks instead of a neon one. The sand's cream (bank 4) is nearest to DQ5's
# pale grey and reads as snow, so the sand takes DQ5's sand ramp.
TONES = {None: {"102900": "003800", "054600": "003800", "007200": "006800", "0ba100": "006800",
                "3fb800": "00a000", "2dff39": "00a000", "20e30e": "00f818", "9cff8c": "00f818"},
         "dirt": {"f7f7d6": "d8c068", "e2cd7a": "b09848", "cda23c": "907020"}}


def _rgb(colour):
    return tuple((colour >> s & 31) << 3 | (colour >> s & 31) >> 2 for s in (0, 5, 10))


def line_colours(palettes):
    """{nibble: {colour index: RGB}} of the world-0 day set (palettes as dq5fieldgfxwrite: 30 colours, lines 2 and 3
    colours 1-15)."""
    day = palettes["world0"][DAY_SET]
    return {n: {i: _rgb(day[n * 15 + i - 1]) for i in COLOURS} for n in LINES}


def _distance(a, b):
    # Weighted RGB ("redmean"): closer to how far apart two colours look than plain RGB.
    r = (a[0] + b[0]) / 2
    return (2 + r / 256) * (a[0] - b[0]) ** 2 + 4 * (a[1] - b[1]) ** 2 + (2 + (255 - r) / 256) * (a[2] - b[2]) ** 2


def quantize(pixels, lines):
    """(nibble, colour indices) of 64 RGB pixels (None = transparent, index 0) on the line that is nearest overall.
    lines: {nibble: {index: RGB}}."""
    best = None
    for nibble, colours in lines.items():
        out, error = [], 0
        for p in pixels:
            if p is None:
                out.append(0)
                continue
            i = min(colours, key=lambda k: _distance(p, colours[k]))
            out.append(i)
            error += _distance(p, colours[i])
        if best is None or error < best[0]:
            best = (error, nibble, out)
    return best[1], best[2]


def encode(indices):
    """SNES 4bpp tile (32 bytes) of 64 colour indices, row-major."""
    out = bytearray(32)
    for r in range(8):
        for c in range(8):
            v = indices[r * 8 + c]
            for p in range(4):
                if v >> p & 1:
                    out[(p >> 1) * 16 + r * 2 + (p & 1)] |= 0x80 >> c
    return bytes(out)


def decode(tile):
    return [sum((tile[(p >> 1) * 16 + r * 2 + (p & 1)] >> (7 - c) & 1) << p for p in range(4))
            for r in range(8) for c in range(8)]


def quarters(image):
    """Four 8x8 pixel lists (top-left, top-right, bottom-left, bottom-right) of a 16x16 RGB grid (rows of pixels)."""
    return [[image[y][x] for y in range(oy, oy + 8) for x in range(ox, ox + 8)] for oy in (0, 8) for ox in (0, 8)]


@functools.cache
def assets():
    from dq4environmentart import create_assets
    return create_assets()


@functools.cache
def tones(name):
    """{art RGB: RGB} of TONES for an asset."""
    from dq4environmentart import _rgb as art_rgb
    rgb = lambda v: tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))  # noqa: E731
    return {art_rgb(k): rgb(v) for key in (None, name) for k, v in TONES.get(key, {}).items()}


def _pixels(image, name=None):
    palette, tone = image.getpalette(), tones(name)
    out = [[None if not (v := image.getpixel((x, y))) else tuple(palette[v * 3:v * 3 + 3]) for x in range(16)]
           for y in range(16)]
    return [[tone.get(p, p) for p in row] for row in out]


def art(name):
    """16x16 RGB of a field asset in TONES; its transparent pixels show grass, as dq4environmentmap.render_fields
    draws it."""
    found = assets()
    grass, top = _pixels(found["grass"], "grass"), _pixels(found[name], name)
    return [[t if t is not None else g for t, g in zip(trow, grow)] for trow, grow in zip(top, grass)]


def rocks():
    """The reef's rocks alone: the pixels where the shoal asset differs from the water it was drawn on."""
    shoal, water = (_pixels(assets()[name], name) for name in ("shoal", "water0"))
    return [[s if s != w else None for s, w in zip(srow, wrow)] for srow, wrow in zip(shoal, water)]


def generate(rom):
    """(tiles, tile palette nibbles, tile attributes, dq5fieldtables blocks) for a DQ5 ROM: its 512 field tiles,
    then the new tiles; and the DQ5 blocks of dq4fieldport.OWN_BLOCKS."""
    from dq5field import BLOCK_LOWER, BLOCK_UPPER, block_tiles, terrain
    from dq5fieldgfxwrite import original
    from dq5map import Rom
    from dq4environmentmap import FIELD_ART
    r = Rom(rom)
    o = original(r)
    lines = line_colours(o["palettes"])
    tiles = bytearray(o["tiles"])
    nibbles, attrs = list(o["tile_palettes"]), list(o["tile_attributes"])
    found = {}

    def tile(pixels, attr):
        nibble, indices = quantize(pixels, lines)
        key = (encode(indices), nibble, attr)
        if key not in found:
            found[key] = TILES + len(found)
        return found[key]

    blocks, done = [], set()
    for kind, number in sorted(dq4fieldport.OWN_BLOCKS.items(), key=lambda kv: kv[1]):
        if number in done or number < dq4fieldport.FIRST_BLOCK:
            continue
        done.add(number)
        borrowed = dq4fieldport.BLOCKS[kind]
        lower, upper = block_tiles(r, BLOCK_LOWER, borrowed), block_tiles(r, BLOCK_UPPER, borrowed)
        quarter_attrs = [o["tile_attributes"][u or lo] for lo, u in zip(lower, upper)]
        if kind == REEF:
            new_lower = list(SEA_TILES)
            new_upper = [tile(p, a) for p, a in zip(quarters(rocks()), quarter_attrs)]
        else:
            new_lower = [tile(p, a) for p, a in zip(quarters(art(FIELD_ART[kind][0])), quarter_attrs)]
            new_upper = [0, 0, 0, 0]
        blocks.append({"index": number, "lower": new_lower, "upper": new_upper, "terrain": terrain(r, borrowed)})
    for (raw, nibble, attr), _ in sorted(found.items(), key=lambda kv: kv[1]):
        tiles += raw
        nibbles.append(nibble)
        attrs.append(attr)
    return bytes(tiles), nibbles, attrs, blocks


def gfx_doc(dq5, folder):
    """dq5fieldgfx/1 document in folder (DQ5's dump with the tiles, nibbles and attributes of generate) and the
    dq5fieldtables/1 document of the new blocks. -> (gfx document path, blocks document path)."""
    folder.mkdir(parents=True, exist_ok=True)
    _run("dq5fieldgfxwrite.py", dq5, "dump", "-o", folder)
    tiles, nibbles, attrs, blocks = generate(Path(dq5).read_bytes())
    doc = json.loads((folder / "fieldgfx.json").read_text(encoding="utf-8"))
    (folder / "tiles.bin").write_bytes(tiles)
    # dq5fieldgfxwrite takes 1,024 attributes once tiles grow; past the tiles, those of tile − 512, as it fills them.
    doc.update(tile_palettes=nibbles, tile_attributes=attrs + attrs[len(attrs) - TILES:TILES])
    gfx = folder / "fieldgfx.json"
    gfx.write_text(json.dumps(doc) + "\n", encoding="utf-8")
    table = folder / "blocks.json"
    table.write_text(json.dumps({"format": "dq5fieldtables/1", "blocks": blocks}, indent=1) + "\n", encoding="utf-8")
    return gfx, table


def _run(tool, *args):
    proc = subprocess.run([sys.executable, str(DQ5_TOOLS / tool), *map(str, args)], capture_output=True, text=True)
    if proc.returncode:
        raise RuntimeError(f"{tool} {' '.join(map(str, args[:2]))}: {proc.stderr[-1500:]}")
    return proc.stdout


def render(rom, fc_grid, x0, y0, w, h):
    """RGB image of FC blocks (x0, y0)-(x0+w, y0+h) drawn from generate in the day colours, the way the field shows
    them (upper layer over lower, colour 0 of the upper layer transparent)."""
    from PIL import Image
    from dq5fieldgfxwrite import original
    from dq5map import Rom
    tiles, nibbles, _, blocks = generate(rom)
    lines = line_colours(original(Rom(rom))["palettes"])
    by_number = {b["index"]: b for b in blocks}
    sea = {"lower": list(SEA_TILES), "upper": [0] * 4}
    image = Image.new("RGB", (w * 16, h * 16))
    for by in range(h):
        for bx in range(w):
            kind = fc_grid[y0 + by][x0 + bx]
            block = by_number.get(dq4fieldport.OWN_BLOCKS[kind], sea)
            for layer in ("lower", "upper"):
                for q, t in enumerate(block[layer]):
                    if layer == "upper" and not t:
                        continue
                    for i, v in enumerate(decode(tiles[t * 32:t * 32 + 32])):
                        if v:
                            image.putpixel((bx * 16 + q % 2 * 8 + i % 8, by * 16 + q // 2 * 8 + i // 8),
                                           lines[nibbles[t]][v])
    return image


def main():
    from kr_patch.fc import ines
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("preview",))
    ap.add_argument("--dq5", default="rom/dq5.sfc", type=Path)
    ap.add_argument("--dq4", default="rom/dq4.nes", type=Path)
    ap.add_argument("--at", default="140,30", help="FC block x,y of the top-left corner (10진)")
    ap.add_argument("--size", default="40,30", help="blocks across, down")
    ap.add_argument("-o", "--out", required=True, type=Path)
    args = ap.parse_args()
    grid, _ = dq4fieldport.fc_field(ines.prg(args.dq4.read_bytes()))
    x0, y0 = map(int, args.at.split(","))
    w, h = map(int, args.size.split(","))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    render(args.dq5.read_bytes(), grid, x0, y0, w, h).resize((w * 32, h * 32)).save(args.out)
    print(args.out)


if __name__ == "__main__":
    main()
