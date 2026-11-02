"""Without a ROM, the 4bpp tile coding, the colour choice and the sea frame check; with rom/dq5.sfc, the generated
tiles change only free DQ5 slots and the blocks keep DQ5's terrain and attributes, and the sea takes DQ5's sea colours."""

import sys
import unittest
from pathlib import Path

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
