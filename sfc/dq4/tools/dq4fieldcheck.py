"""Check the FC field in a groups ROM of dq4groupbuild.py (MesenCE headless, dq5warp.lua FIELD).

  map      stand on the field: WRAM 7F:0000 (block numbers' low 8 bits) and 7E:E000 (9th bits) equal the map of
           dq4fieldport.world, byte for byte
  terrain  for FC block kinds near バトランド: stand on a walkable FC neighbour and press towards a block of that
           kind for two DQ5 cells; a walkable kind is entered, a blocked one (sea without a ship, mountain, reef,
           signboard) keeps the party on the neighbour
  gfx      stand at VIEWS, save and dump VRAM and CGRAM: the BG tilemap of both layers around the party is the
           blocks of dq4fieldport.world with dq4fieldgfx's tiles and palette nibbles; the field tiles in VRAM are
           dq4fieldgfx's (the sea pairs 4·5 and 20·21 turned by the same pixels, as 01:C790 turns them; the
           animated 454-459 left out); CGRAM lines 2 and 3 colours 1-13 are one of DQ5's world-0 sets

  MESENCE=… LIBDIR=… python sfc/dq4/tools/dq4fieldcheck.py --rom work/dq4-groups/groups.sfc --out work/dq4-fieldcheck

Each gfx view leaves its screen in <out>/gfx-<name>/end.png.
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

import dq4fieldgfx  # noqa: E402
import dq4fieldport  # noqa: E402
from dq4environmentromcheck import dump  # noqa: E402
from dq4groupcheck import field_scene  # noqa: E402
from dq5fieldwrite import split  # noqa: E402
from kr_patch.fc import ines  # noqa: E402

# FC block kind -> whether the party walks onto it from land.
KINDS = {0x02: True, 0x01: True, 0x03: True, 0x04: True, 0x05: True, 0x07: True, 0x16: True,
         0x00: False, 0x06: False, 0x0A: False, 0x15: False}
CENTER = (0xA4, 0x2E)
# Two DQ5 cells, whether or not the party first turns (measured from field (341,56): right, up and down).
PRESS = 18
# The press starts at the frame before the field reads input ($7F & 7 = 0, dq5warp.lua idle): how long the field
# takes to load shifts that phase, and from another phase 18 frames reach one cell into the poison swamp, not two.
ALIGN = "idle:16"
TOWARDS = {(1, 0): "right", (-1, 0): "left", (0, -1): "up", (0, 1): "down"}
MAP_SCENE_CELL = (2 * 0xA4, 2 * 0x2F + 1)
# Field cells to look at the art from: below バトランド castle, outside イムル, on a bridge, in the desert south of
# the castle, by a reef of the western sea.
VIEWS = {"castle": MAP_SCENE_CELL, "imuru": (308, 47), "bridge": (400, 145), "desert": (328, 149), "reef": (80, 49)}
# Cells around the party compared with the BG tilemap (the screen is 32x28 cells).
AROUND = (range(-12, 12), range(-14, 16))
LOWER, UPPER, TILES_AT, EXTRA_AT = 0x0000, 0x0800, 0x2000, 0x4000  # VRAM words (sfc/dq5/docs/dq5-field-format.md)
ANIMATED = range(454, 460)


def _word(vram, base, col, row):
    """BG tilemap word of 64x32 tiles: two 32x32 screens side by side."""
    i = base + (col >= 32) * 1024 + row * 32 + col % 32
    return vram[i * 2] | vram[i * 2 + 1] << 8


def _rows(tile):
    pixels = dq4fieldgfx.decode(tile)
    return [pixels[r * 8:r * 8 + 8] for r in range(8)]


def rotation(got, want):
    """Pixels k (0-15) by which every 16-pixel row of the tile pairs in got is turned from want (lists of (left,
    right) 32-byte tiles); None when no k fits them all."""
    rows = [(g1 + g2, w1 + w2) for (ga, gb), (wa, wb) in zip(got, want)
            for g1, g2, w1, w2 in zip(_rows(ga), _rows(gb), _rows(wa), _rows(wb))]
    return next((k for k in range(16) if all(g == w[k:] + w[:k] for g, w in rows)), None)


def compare_gfx(vram, cgram, cell, world, generated, palettes):
    """Results of a gfx view: tilemap cells that match, field tiles that match, sea turn, CGRAM set."""
    tiles, nibbles, _, blocks = generated
    defs = {b["index"]: b for b in blocks}
    defs[dq4fieldport.SEA] = {"lower": list(dq4fieldgfx.SEA_TILES), "upper": [0] * 4}

    def want(x, y, layer):
        """Tilemap word of a cell: tile and palette line (nibble + 2). Every upper-layer word, tile 0 too, had the BG
        priority bit (2000) set in the game."""
        t = defs[world[(y >> 1) * 256 + (x >> 1)]][layer][(x & 1) + (y & 1) * 2]
        return t | ((nibbles[t] & 7) + 2) << 10 | (0x2000 if layer == "upper" else 0)

    px, py = cell
    cells = [(px + dx, py + dy) for dy in AROUND[0] for dx in AROUND[1]]
    # The tilemap scrolls with the party: take the cell -> tilemap offset where most lower-layer cells fit.
    best = max((sum(_word(vram, LOWER, (x + ox) % 64, (y + oy) % 32) == want(x, y, "lower") for x, y in cells), ox, oy)
               for ox in range(64) for oy in range(32))
    _, ox, oy = best
    upper = sum(_word(vram, UPPER, (x + ox) % 64, (y + oy) % 32) == want(x, y, "upper") for x, y in cells)

    def vtile(t):
        at = TILES_AT * 2 + t * 32 if t < 512 else EXTRA_AT * 2 + (t - 512) * 32
        return vram[at:at + 32]

    fixed = [t for t in range(len(tiles) // 32) if t not in dq4fieldgfx.SEA_TILES and t not in ANIMATED]
    same = sum(vtile(t) == tiles[t * 32:t * 32 + 32] for t in fixed)
    pairs = ((4, 5), (20, 21))
    turned = rotation([tuple(vtile(t) for t in p) for p in pairs], [tuple(tiles[t * 32:t * 32 + 32] for t in p) for p in pairs])
    lines = [cgram[(16 * line + i) * 2] | cgram[(16 * line + i) * 2 + 1] << 8 for line in (2, 3) for i in range(1, 14)]
    sets = [k for k, row in enumerate(palettes) if row[0:13] + row[15:28] == lines]
    return {"lower": [best[0], len(cells)], "upper": [upper, len(cells)], "tiles": [same, len(fixed)],
            "sea_turn": turned, "world0_set": sets[0] if sets else None,
            "ok": best[0] == upper == len(cells) and same == len(fixed) and turned is not None and bool(sets)}


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
    ap.add_argument("--dq5", default="rom/dq5.sfc", type=Path)
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

    from dq5fieldgfxwrite import original
    from dq5map import Rom
    generated = dq4fieldgfx.generate(args.dq5.read_bytes())
    palettes = original(Rom(args.dq5.read_bytes()))["palettes"]["world0"]
    world = dq4fieldport.world(grid)

    def run_view(name, cell):
        scene = f"gfx-{name}"
        got = field_scene(mesence, rom, state, out, scene, *cell, "wait:30", SAVE="field.mss")
        if got != {"field": list(cell)}:
            return scene, {"got": got, "ok": False}
        _, vram, cgram = dump(mesence, rom, out / scene / "field.mss", out / scene / "dump")
        return scene, {"got": got, **compare_gfx(vram, cgram, cell, world, generated, palettes)}

    def run_probe(kind, target, start, d):
        name = f"terrain-{kind:02X}-{d}"
        got = field_scene(mesence, rom, state, out, name, *dq4fieldport.stand(*start), f"{ALIGN},{d}:{PRESS},wait:60")
        want = list(target if KINDS[kind] else start)
        block = [v // 2 for v in got.get("field", ())]
        return name, {"got": got, "block": block, "want_block": want, "target": list(target), "ok": block == want}

    with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
        futures = [pool.submit(run_map)] + [pool.submit(run_probe, *p) for p in probes(grid, props, taken)] + \
            [pool.submit(run_view, *v) for v in VIEWS.items()]
        results = dict(f.result() for f in futures)
    ok = all(r["ok"] for r in results.values())
    report = {"status": "passed" if ok else "failed", "scenes": dict(sorted(results.items()))}
    (out / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
