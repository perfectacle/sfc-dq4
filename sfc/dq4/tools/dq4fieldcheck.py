"""Check the FC fields in a groups ROM of dq4groupbuild.py (MesenCE headless, dq5warp.lua FIELD).

For each FC field (FIELDS) in its DQ5 world (dq4fieldport.WORLDS); worlds 1 and 2 hold $1949 by POKE, as the warp
walks out of 01/00 into world 0:
  map      stand on the field: WRAM 7F:0000 (block numbers' low 8 bits) and 7E:E000 (9th bits) equal the map of
           dq4fieldport.world, byte for byte
  terrain  for FC block kinds near the field's centre: stand on a walkable FC neighbour and press towards a block
           of that kind for two DQ5 cells; a walkable kind is entered, a blocked one (sea without a ship, mountain,
           reef, signboard, field 3's hills) keeps the party on the neighbour
  gfx      stand at the views, save and dump VRAM and CGRAM: the BG tilemap of both layers around the party is the
           blocks of dq4fieldport.world with dq4fieldgfx's tiles and palette nibbles; the field tiles in VRAM are
           dq4fieldgfx's (the animated 454-459 left out); the sea tiles 4·5·20·21 are one of the 16 frames
           01:C5C8 makes of dq4fieldgfx.water in that world (dq5gfx.water_frames); CGRAM lines 2 and 3 colours
           1-13 are one of the world's sets

  MESENCE=… LIBDIR=… python sfc/dq4/tools/dq4fieldcheck.py --rom work/dq4-groups/groups.sfc --out work/dq4-fieldcheck

Scenes of worlds 1 and 2 are named w1-…, w2-…. Each gfx view leaves its screen in <out>/[wN-]gfx-<name>/end.png.
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
from dq5gfx import water_frames  # noqa: E402
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
# Per FC field: the centre the terrain probes are chosen near, the kinds probed (whether the party walks onto them),
# and the views, as FC entrance blocks whose leaving cell (dq4fieldport.door) the party stands on; the first is
# also the map scene. Field 1: ゴットサイド town (1A), the tower (2C), the cave (3C). Field 3: the castle (45), the
# western shrine (29) and the palace in the middle (43). The FC groups behind them are not ported yet.
FIELDS = {
    0: {"centre": CENTER, "kinds": KINDS},
    1: {"centre": (0x20, 0x1C), "kinds": {0x01: True, 0x02: True, 0x03: True, 0x04: True, 0x05: True, 0x07: True,
                                         0x00: False, 0x06: False},
        "views": {"town": (0x20, 0x1C), "tower": (0x17, 0x2F), "cave": (0x11, 0x10)}},
    # Field 3's hills (01) touch only mountains and sea, so no walk reaches them to probe.
    3: {"centre": (0x23, 0x24), "kinds": {0x02: True, 0x03: True, 0x04: True, 0x07: True, 0x00: False, 0x06: False},
        "views": {"castle": (0x23, 0x1F), "shrine": (0x11, 0x12), "palace": (0x23, 0x19)}},
}
# Cells around the party compared with the BG tilemap (the screen is 32x28 cells).
AROUND = (range(-12, 12), range(-14, 16))
LOWER, UPPER, TILES_AT, EXTRA_AT = 0x0000, 0x0800, 0x2000, 0x4000  # VRAM words (sfc/dq5/docs/dq5-field-format.md)
ANIMATED = range(454, 460)


def _word(vram, base, col, row):
    """BG tilemap word of 64x32 tiles: two 32x32 screens side by side."""
    i = base + (col >= 32) * 1024 + row * 32 + col % 32
    return vram[i * 2] | vram[i * 2 + 1] << 8


def sea_frame(got, frames):
    """Index of the frame (128 bytes: tiles 4, 5, 20, 21) the VRAM sea tiles got show; None when none."""
    return frames.index(got) if got in frames else None


def compare_gfx(vram, cgram, cell, world, generated, palettes, frames):
    """Results of a gfx view: tilemap cells that match, field tiles that match, sea frame, CGRAM set."""
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
    sea = sea_frame(b"".join(vtile(t) for t in dq4fieldgfx.SEA_TILES), frames)
    lines = [cgram[(16 * line + i) * 2] | cgram[(16 * line + i) * 2 + 1] << 8 for line in (2, 3) for i in range(1, 14)]
    sets = [k for k, row in enumerate(palettes) if row[0:13] + row[15:28] == lines]
    return {"lower": [best[0], len(cells)], "upper": [upper, len(cells)], "tiles": [same, len(fixed)],
            "sea_frame": sea, "palette_set": sets[0] if sets else None,
            "ok": best[0] == upper == len(cells) and same == len(fixed) and sea is not None and bool(sets)}


def probes(grid, props, entrances, kinds=KINDS, centre=CENTER):
    """(kind, FC target block, FC start block, direction) nearest centre per kind of kinds."""
    out = []
    for kind in kinds:
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
                    score = abs(x - centre[0]) + abs(y - centre[1])
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
    from dq4field import entrances
    taken = {(fx, fy) for _, fx, fy, *_ in entrances(prg)}

    from dq5fieldgfxwrite import original
    from dq5map import Rom
    generated = dq4fieldgfx.generate(args.dq5.read_bytes())
    palettes = original(Rom(args.dq5.read_bytes()))["palettes"]
    world_sets = {0: palettes["world0"], 1: [dq4fieldgfx.world1_set(palettes)], 2: palettes["world2"]}
    sea = dq4fieldgfx.water(palettes)

    def scenes(field):
        """(callable, args) of the scenes of an FC field."""
        w = dq4fieldport.WORLDS[field]
        grid, props = dq4fieldport.fc_field(prg, field)
        world = dq4fieldport.world(grid, field)
        conf = FIELDS[field]
        prefix = f"w{w}-" if w else ""
        extra = {"POKE": f"7E1949={w:02X}"} if w else {}
        views = VIEWS if "views" not in conf else \
            {name: dq4fieldport.door(props, [block])[1] for name, block in conf["views"].items()}
        map_cell = MAP_SCENE_CELL if not w else next(iter(views.values()))

        def run_map():
            scene = f"{prefix}map"
            got = field_scene(mesence, rom, state, out, scene, *map_cell, "wait:30", **extra)
            ram = (out / scene / "final.wram").read_bytes()
            low, high = split(world)
            same = {"7F:0000": ram[0x10000:0x20000] == low, "7E:E000": ram[0xE000:0x10000] == high}
            return scene, {"got": got, "want": {"field": list(map_cell)}, "wram": same,
                           "ok": got == {"field": list(map_cell)} and all(same.values())}

        def run_view(name, cell):
            scene = f"{prefix}gfx-{name}"
            got = field_scene(mesence, rom, state, out, scene, *cell, "wait:30", SAVE="field.mss", **extra)
            if got != {"field": list(cell)}:
                return scene, {"got": got, "ok": False}
            _, vram, cgram = dump(mesence, rom, out / scene / "field.mss", out / scene / "dump")
            return scene, {"got": got, **compare_gfx(vram, cgram, cell, world, generated, world_sets[w],
                                                     water_frames(sea, w))}

        def run_probe(kind, target, start, d):
            name = f"{prefix}terrain-{kind:02X}-{d}"
            got = field_scene(mesence, rom, state, out, name, *dq4fieldport.stand(*start),
                              f"{ALIGN},{d}:{PRESS},wait:60", **extra)
            want = list(target if conf["kinds"][kind] else start)
            block = [v // 2 for v in got.get("field", ())]
            return name, {"got": got, "block": block, "want_block": want, "target": list(target), "ok": block == want}

        return [(run_map, ())] + [(run_probe, p) for p in probes(grid, props, taken, conf["kinds"], conf["centre"])] + \
            [(run_view, v) for v in views.items()]

    with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
        futures = [pool.submit(f, *a) for field in FIELDS for f, a in scenes(field)]
        results = dict(f.result() for f in futures)
    ok = all(r["ok"] for r in results.values())
    report = {"status": "passed" if ok else "failed", "scenes": dict(sorted(results.items()))}
    (out / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
