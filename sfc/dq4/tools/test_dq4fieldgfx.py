"""Without a ROM, the 4bpp tile coding, the colour choice and the sea frame check; with rom/dq5.sfc, the generated
tiles change only free DQ5 slots and the blocks keep DQ5's terrain and attributes, and the sea takes DQ5's sea colours."""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dq4fieldcheck as check  # noqa: E402
import dq4fieldgfx as gfx  # noqa: E402
import dq4fieldport as port  # noqa: E402

ROM = Path(__file__).resolve().parents[3] / "rom" / "dq5.sfc"
LINES = {0: {1: (0, 0, 0), 2: (0, 160, 0), 3: (0, 0, 200)}, 1: {1: (200, 0, 0), 2: (0, 160, 0), 3: (250, 250, 250)}}


class PaletteTest(unittest.TestCase):
    def test_world1_takes_the_day_colours(self):
        palettes = {"world0": [[0] * 30, [0] * 30, list(range(30))], "world1": [list(range(100, 130))]}
        got = gfx.world1_set(palettes)
        self.assertEqual(got[0:13] + got[15:28], list(range(13)) + list(range(15, 28)))
        self.assertEqual(got[13:15] + got[28:30], [113, 114, 128, 129])


class TileTest(unittest.TestCase):
    def test_encode_decode(self):
        indices = [(i * 7) % 16 for i in range(64)]
        raw = gfx.encode(indices)
        self.assertEqual(len(raw), 32)
        self.assertEqual(gfx.decode(raw), indices)
        # Row 0 pixel 0 is bit 7 of plane bytes 0, 1, 16 and 17.
        self.assertEqual(gfx.encode([15] + [0] * 63)[0:2] + gfx.encode([15] + [0] * 63)[16:18], b"\x80" * 4)

    def test_quantize_picks_the_nearer_line(self):
        nibble, indices = gfx.quantize([(210, 10, 10)] * 32 + [None] * 32, LINES)
        self.assertEqual((nibble, indices), (1, [1] * 32 + [0] * 32))
        nibble, indices = gfx.quantize([(0, 10, 190)] * 64, LINES)
        self.assertEqual((nibble, indices), (0, [3] * 64))

    def test_tones(self):
        from dq4environmentart import _rgb
        # Every asset takes the darker greens; only the sand takes DQ5's sand.
        self.assertEqual(gfx.tones("grass")[_rgb("2dff39")], (0x00, 0xA0, 0x00))
        self.assertEqual(gfx.tones("dirt")[_rgb("f7f7d6")], (0xD8, 0xC0, 0x68))
        self.assertNotIn(_rgb("f7f7d6"), gfx.tones("signboard"))
        self.assertNotIn(_rgb("2dff39"), {p for row in gfx.art("grass") for p in row})

    def test_quarters(self):
        image = [[(x, y, 0) for x in range(16)] for y in range(16)]
        q = gfx.quarters(image)
        self.assertEqual((q[0][0], q[1][0], q[2][0], q[3][63]), ((0, 0, 0), (8, 0, 0), (0, 8, 0), (15, 15, 0)))

    def test_sea_frame(self):
        sys.path.insert(0, str(gfx.DQ5_TOOLS))
        from dq5gfx import water_frames
        src = b"".join(gfx.encode([(i + q) % 16 for i in range(64)]) for q in range(4))
        for world in (0, 1, 2):
            frames = water_frames(src, world)
            self.assertEqual(check.sea_frame(frames[4], frames), 4)
        self.assertIsNone(check.sea_frame(bytes(128), water_frames(src, 0)))


def synthetic_palettes():
    day = [0x7FFF] + [(i * 0x0421) & 0x7FFF for i in range(1, 30)]
    return {"world0": [[0] * 30, [0] * 30, day], "world1": [list(range(100, 130))], "world2": [[0x001F] * 30]}


class ColourTest(unittest.TestCase):
    def test_line_colours_unpack_555_into_the_two_lines(self):
        palettes = synthetic_palettes()
        lines = gfx.line_colours(palettes)
        self.assertEqual(sorted(lines), [0, 1])
        self.assertEqual(sorted(lines[0]), list(gfx.COLOURS))
        # 선 2 의 색 1 은 낮 벌의 첫 칸(7FFF = 흰색), 선 3 의 색 1 은 열여섯째 칸
        self.assertEqual(lines[0][1], (255, 255, 255))
        day = palettes["world0"][gfx.DAY_SET]
        self.assertEqual(lines[1][1], gfx._rgb(day[15]))
        self.assertEqual(gfx._rgb(0x001F), (255, 0, 0))
        self.assertEqual(gfx._rgb(0x03E0), (0, 255, 0))
        self.assertEqual(gfx._rgb(0x7C00), (0, 0, 255))

    def test_distance_is_zero_only_for_equal_colours(self):
        self.assertEqual(gfx._distance((9, 9, 9), (9, 9, 9)), 0)
        self.assertGreater(gfx._distance((0, 0, 0), (255, 255, 255)), gfx._distance((0, 0, 0), (10, 10, 10)))

    def test_water_is_four_tiles_of_one_colour_when_the_line_is_flat(self):
        palettes = synthetic_palettes()
        palettes["world0"][gfx.DAY_SET] = [0x2108] * 30
        raw = gfx.water(palettes)
        self.assertEqual(len(raw), 128)
        used = {v for q in range(4) for v in gfx.decode(raw[q * 32:q * 32 + 32])}
        self.assertEqual(used, {1})


class AssetTest(unittest.TestCase):
    def test_art_shows_grass_where_the_asset_is_transparent(self):
        from dq4environmentmap import FIELD_ART
        grass = gfx.art("grass")
        self.assertEqual((len(grass), len(grass[0])), (16, 16))
        for kind in (0x01, 0x04, 0x0C):
            name = FIELD_ART[kind][0]
            top = gfx._pixels(gfx.assets()[name], name)
            got = gfx.art(name)
            for y in range(16):
                for x in range(16):
                    self.assertIsNotNone(got[y][x])
                    self.assertEqual(got[y][x], top[y][x] if top[y][x] is not None else grass[y][x])

    def test_rocks_keep_only_pixels_that_differ_from_the_water(self):
        rocks = gfx.rocks()
        shoal = gfx._pixels(gfx.assets()["shoal"], "shoal")
        water = gfx._pixels(gfx.assets()["water0"], "water0")
        flat = [p for row in rocks for p in row]
        self.assertIn(None, flat)
        self.assertTrue(any(p is not None for p in flat))
        for y in range(16):
            for x in range(16):
                self.assertEqual(rocks[y][x], None if shoal[y][x] == water[y][x] else shoal[y][x])


KEPT = (0, 0x02, 0x71, 0xA7, 0xCA)


def fake_block_tiles(rom, table, m):
    from dq5field import BLOCK_LOWER
    base = 300 + m + (0 if table == BLOCK_LOWER else 4)
    return [base + q for q in range(4)]


def synthetic_tiles():
    tiles = bytearray(gfx.TILES * 32)
    tiles[200 * 32 + 0] = tiles[200 * 32 + 4] = 0xFF   # 플레인 0 의 0·2번 줄
    tiles[50 * 32 + 0] = 0xFF
    tiles[100 * 32 + 0] = 0xFF
    return bytes(tiles)


class FreeSlotsTest(unittest.TestCase):
    def test_busiest_free_tiles_go_first_and_kept_tiles_never(self):
        from dq5gfx import FIELD_ANIM_COUNT, FIELD_ANIM_TILE
        with mock.patch("dq5field.block_tiles", fake_block_tiles):
            slots = gfx.free_slots(None, synthetic_tiles())
        kept = {0, *gfx.SEA_TILES, *range(FIELD_ANIM_TILE, FIELD_ANIM_TILE + FIELD_ANIM_COUNT)}
        for m in KEPT:
            kept.update(range(300 + m, 304 + m))
            kept.update(range(304 + m, 308 + m))
        self.assertEqual(len(slots), gfx.TILES - len(kept))
        self.assertTrue(kept.isdisjoint(slots))
        # 200 은 바뀐 바이트 4, 50 과 100 은 2(같으면 번호순), 나머지는 0
        self.assertEqual(slots[:6], [200, 50, 100, 1, 2, 3])
        self.assertEqual(slots[6:], sorted(slots[6:]))


def synthetic_original():
    return {"tiles": synthetic_tiles(), "palettes": synthetic_palettes(),
            "tile_palettes": [t % 2 for t in range(gfx.TILES)],
            "tile_attributes": [(t * 3) % 251 for t in range(gfx.TILES)]}


def fake_terrain(rom, m):
    return m % 16


def upper_zero(rom, table, m):
    from dq5field import BLOCK_UPPER
    return [0, 0, 0, 0] if table == BLOCK_UPPER else [(m * 4 + q) % 400 + 20 for q in range(4)]


class GenerateSyntheticTest(unittest.TestCase):
    def setUp(self):
        for target, value in (("dq5fieldgfxwrite.original", lambda r: synthetic_original()),
                              ("dq5map.Rom", lambda raw: raw), ("dq5field.block_tiles", upper_zero),
                              ("dq5field.terrain", fake_terrain)):
            patcher = mock.patch(target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.tiles, self.nibbles, self.attrs, self.blocks = gfx.generate(b"rom")
        self.orig = synthetic_original()

    def test_sizes_and_block_numbers(self):
        self.assertEqual(len(self.tiles), gfx.TILES * 32)
        self.assertEqual((len(self.nibbles), len(self.attrs)), (gfx.TILES, gfx.TILES))
        self.assertEqual([b["index"] for b in self.blocks], [n for n, _, _ in port.new_blocks()])

    def test_blocks_keep_borrowed_terrain_and_quarter_attributes(self):
        for block, (number, kind, borrowed) in zip(self.blocks, port.new_blocks()):
            self.assertEqual(block["terrain"], borrowed % 16)
            if kind == gfx.REEF:
                self.assertEqual(block["lower"], list(gfx.SEA_TILES))
                quarters_attr = [self.orig["tile_attributes"][t] for t in upper_zero(None, "lower", borrowed)]
                got = [self.attrs[t] for t in block["upper"]]
            else:
                self.assertEqual(block["upper"], [0, 0, 0, 0])
                quarters_attr = [self.orig["tile_attributes"][t] for t in upper_zero(None, "lower", borrowed)]
                got = [self.attrs[t] for t in block["lower"]]
            self.assertEqual(got, quarters_attr, f"{number} kind {kind:02X}")

    def test_only_free_slots_change(self):
        with mock.patch("dq5field.block_tiles", upper_zero):
            free = set(gfx.free_slots(None, self.orig["tiles"]))
        changed = [t for t in range(gfx.TILES)
                   if (self.tiles[t * 32:t * 32 + 32], self.nibbles[t], self.attrs[t])
                   != (self.orig["tiles"][t * 32:t * 32 + 32], self.orig["tile_palettes"][t],
                       self.orig["tile_attributes"][t])]
        self.assertTrue(changed)
        self.assertTrue(set(changed) <= free)

    def test_identical_quarters_share_a_tile(self):
        flat = {**synthetic_original(), "tile_attributes": [7] * gfx.TILES}
        ink = (200, 40, 40)
        # 위 두 4분면은 같은 투명, 좌하는 전부 색, 우하는 한 칸 걸러 색
        image = [[None if y < 8 else ink if x < 8 or x % 2 == 0 else None for x in range(16)] for y in range(16)]
        with mock.patch("dq5fieldgfxwrite.original", lambda r: flat), mock.patch.object(gfx, "art", lambda name: image):
            _, _, _, blocks = gfx.generate(b"rom")
        painted = [b["lower"] for b in blocks if b["lower"] != list(gfx.SEA_TILES)]
        self.assertTrue(painted)
        for lower in painted:
            self.assertEqual(lower[0], lower[1])
            self.assertEqual(len({lower[0], lower[2], lower[3]}), 3)
            self.assertEqual(lower, painted[0])

    def test_running_out_of_slots_is_an_error(self):
        with mock.patch.object(gfx, "free_slots", lambda r, tiles: [1, 2]):
            with self.assertRaisesRegex(ValueError, "more new field tiles than the 2 free"):
                gfx.generate(b"rom")


class DocTest(unittest.TestCase):
    def test_gfx_doc_writes_tiles_water_and_both_documents(self):
        palettes = synthetic_palettes()
        base = {"palettes": {"world0": palettes["world0"], "world1": palettes["world1"]},
                "water_files": {"0": "a.bin", "1": "b.bin"}}
        tiles, nibbles, attrs = bytes(range(32)), [0, 1], [5, 6]
        blocks = [{"index": 511, "lower": [1, 2, 3, 4], "upper": [0] * 4, "terrain": 2}]

        def fake_run(tool, dq5, command, flag, folder):
            self.assertEqual((tool, command, flag), ("dq5fieldgfxwrite.py", "dump", "-o"))
            (Path(folder) / "fieldgfx.json").write_text(json.dumps(base), encoding="utf-8")

        with tempfile.TemporaryDirectory() as tmp:
            dq5 = Path(tmp) / "dq5.sfc"
            dq5.write_bytes(b"sfc")
            folder = Path(tmp) / "a" / "b"
            with mock.patch.object(gfx, "_run", fake_run), \
                    mock.patch.object(gfx, "generate", lambda raw: (tiles, nibbles, attrs, blocks)):
                gfx_path, table_path = gfx.gfx_doc(dq5, folder)
            doc = json.loads(gfx_path.read_text(encoding="utf-8"))
            self.assertEqual((folder / "tiles.bin").read_bytes(), tiles)
            self.assertEqual(len((folder / gfx.WATER_FILE).read_bytes()), 128)
            self.assertEqual(json.loads(table_path.read_text(encoding="utf-8")),
                             {"format": "dq5fieldtables/1", "blocks": blocks})
        self.assertEqual((doc["tile_palettes"], doc["tile_attributes"]), (nibbles, attrs))
        self.assertEqual(doc["water_files"], {"0": gfx.WATER_FILE, "1": gfx.WATER_FILE})
        self.assertEqual(doc["palettes"]["world1"], [gfx.world1_set(palettes)])


class RenderTest(unittest.TestCase):
    def render(self, field, kind, grid_kind=None):
        own = port.own_blocks(field)
        solid = gfx.encode([1] * 64)
        tiles = bytes(gfx.TILES * 32)
        tiles = tiles[:10 * 32] + solid + tiles[11 * 32:]
        blocks = [{"index": own[kind], "lower": [10] * 4, "upper": [0] * 4, "terrain": 0}]
        nibbles = [0] * gfx.TILES
        grid = [[kind, 0]]
        with mock.patch.object(gfx, "generate", lambda rom: (tiles, nibbles, [0] * gfx.TILES, blocks)), \
                mock.patch("dq5fieldgfxwrite.original", lambda r: {"palettes": synthetic_palettes()}), \
                mock.patch("dq5map.Rom", lambda raw: raw):
            return gfx.render(b"rom", grid, 0, 0, 2, 1, field)

    def test_block_is_painted_with_the_world_colours(self):
        image = self.render(0, 2)
        self.assertEqual(image.size, (32, 16))
        self.assertEqual({image.getpixel((x, y)) for x in range(16) for y in range(16)}, {(255, 255, 255)})

    def test_world_two_uses_its_own_dark_line(self):
        image = self.render(3, 2)
        self.assertEqual(image.getpixel((0, 0)), (255, 0, 0))

    def test_world_one_takes_world_zero_day_colours(self):
        image = self.render(1, 2)
        self.assertEqual(image.getpixel((15, 15)), (255, 255, 255))

    def test_sea_block_is_drawn_from_the_water_tiles(self):
        image = self.render(0, 2)
        sea = {image.getpixel((x, y)) for x in range(16, 32) for y in range(16)}
        lines = gfx.line_colours(synthetic_palettes())
        self.assertTrue(sea <= {(0, 0, 0), *lines[0].values()})
        self.assertGreater(len(sea), 1)


class MainTest(unittest.TestCase):
    def test_preview_saves_a_scaled_image(self):
        from PIL import Image
        seen = {}

        def fake_render(rom, grid, x0, y0, w, h, field):
            seen.update(rom=rom, grid=grid, box=(x0, y0, w, h), field=field)
            return Image.new("RGB", (w * 16, h * 16))

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "dq4.nes").write_bytes(b"nes")
            (tmp / "dq5.sfc").write_bytes(b"sfc")
            out = tmp / "sub" / "preview.png"
            argv = ["dq4fieldgfx.py", "preview", "--dq4", str(tmp / "dq4.nes"), "--dq5", str(tmp / "dq5.sfc"),
                    "--at", "3,4", "--size", "5,6", "--field", "1", "-o", str(out)]
            buf = io.StringIO()
            with mock.patch("sys.argv", argv), mock.patch("kr_patch.fc.ines.prg", lambda raw: raw), \
                    mock.patch.object(port, "fc_field", lambda prg, field: ([[7]], None)), \
                    mock.patch.object(gfx, "render", fake_render), contextlib.redirect_stdout(buf):
                gfx.main()
            self.assertEqual(Image.open(out).size, (5 * 32, 6 * 32))
        self.assertEqual(seen, {"rom": b"sfc", "grid": [[7]], "box": (3, 4, 5, 6), "field": 1})
        self.assertEqual(buf.getvalue().strip(), str(out))


@unittest.skipUnless(ROM.is_file(), "local source ROM not present")
class GenerateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(gfx.DQ5_TOOLS))
        from dq5field import BLOCK_LOWER, BLOCK_UPPER, block_tiles, terrain
        from dq5fieldgfxwrite import original
        from dq5map import Rom
        cls.rom = Rom(ROM.read_bytes())
        cls.original = original(cls.rom)
        cls.tiles, cls.nibbles, cls.attrs, cls.blocks = gfx.generate(ROM.read_bytes())
        cls.dq5 = lambda self, m: (block_tiles(cls.rom, BLOCK_LOWER, m), block_tiles(cls.rom, BLOCK_UPPER, m),
                                   terrain(cls.rom, m))

    def test_new_tiles_stay_in_dq5_free_slots(self):
        # Tile 512 and up is VRAM 4000~, which the battle backdrop overwrites while the field shows above and below it.
        self.assertEqual(len(self.tiles), gfx.TILES * 32)
        self.assertEqual(len(self.nibbles), gfx.TILES)
        self.assertEqual(len(self.attrs), gfx.TILES)
        free = set(gfx.free_slots(self.rom, self.original["tiles"]))
        o = self.original
        for t in range(gfx.TILES):
            old = (o["tiles"][t * 32:t * 32 + 32], o["tile_palettes"][t], o["tile_attributes"][t])
            new = (self.tiles[t * 32:t * 32 + 32], self.nibbles[t], self.attrs[t])
            if new != old:
                self.assertIn(t, free, f"tile {t}")
                self.assertIn(self.nibbles[t], gfx.LINES, f"tile {t}")

    def test_blocks_keep_the_borrowed_terrain_and_attributes(self):
        by_number = {b["index"]: b for b in self.blocks}
        self.assertEqual(sorted(by_number), [n for n, _, _ in port.new_blocks()])
        for field in port.WORLDS:
            self.assertTrue(set(port.own_blocks(field).values()) - {port.SEA} <= set(by_number))
        for number, kind, borrowed in port.new_blocks():
            lower, upper, ground = self.dq5(borrowed)
            block = by_number[number]
            self.assertEqual(block["terrain"], ground)
            want = [self.original["tile_attributes"][u or lo] for lo, u in zip(lower, upper)]
            got = [self.attrs[u or lo] for lo, u in zip(block["lower"], block["upper"])]
            self.assertEqual(got, want, f"{kind:02X}")

    def test_sea_takes_dq5_sea_colours(self):
        raw = gfx.water(self.original["palettes"])
        self.assertEqual(len(raw), 128)
        used = {v for q in range(4) for v in gfx.decode(raw[q * 32:q * 32 + 32])}
        sea = {v for t in gfx.SEA_TILES for v in gfx.decode(self.original["tiles"][t * 32:t * 32 + 32])}
        self.assertEqual(used, sea)

    def test_sea_frames_move_and_differ_from_dq5(self):
        # sea_frame accepts any of the 16 frames, so a frozen or unpatched sea must be ruled out here.
        sys.path.insert(0, str(gfx.DQ5_TOOLS))
        from dq5gfx import water_frames
        raw = gfx.water(self.original["palettes"])
        at = 1 << 15 | 0xA719 & 0x7FFF
        dq5 = ROM.read_bytes()[at:at + 128]
        for world in (0, 1, 2):
            frames = water_frames(raw, world)
            self.assertEqual(len(set(frames)), 16, f"world {world}")
            self.assertIsNone(check.sea_frame(dq5, frames), f"world {world}")

    def test_reef_is_rocks_over_the_sea(self):
        block = next(b for b in self.blocks if b["index"] == port.OWN_BLOCKS[gfx.REEF])
        self.assertEqual(block["lower"], list(gfx.SEA_TILES))
        self.assertTrue(set(block["upper"]) <= set(gfx.free_slots(self.rom, self.original["tiles"])))
        self.assertTrue(any(gfx.decode(self.tiles[t * 32:t * 32 + 32]).count(0) for t in block["upper"]))


if __name__ == "__main__":
    unittest.main()
