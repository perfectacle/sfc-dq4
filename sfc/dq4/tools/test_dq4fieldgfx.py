"""Without a ROM, the 4bpp tile coding, the colour choice and the sea turn check; with rom/dq5.sfc, the generated
tiles and blocks keep DQ5's tiles, terrain and attributes."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dq4fieldcheck as check  # noqa: E402
import dq4fieldgfx as gfx  # noqa: E402
import dq4fieldport as port  # noqa: E402

ROM = Path(__file__).resolve().parents[3] / "rom" / "dq5.sfc"
LINES = {0: {1: (0, 0, 0), 2: (0, 160, 0), 3: (0, 0, 200)}, 1: {1: (200, 0, 0), 2: (0, 160, 0), 3: (250, 250, 250)}}


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

    def test_sea_turn(self):
        left, right = gfx.encode(list(range(16)) * 4), gfx.encode([0] * 64)
        rows = [list(range(8)) + [0] * 8, list(range(8, 16)) + [0] * 8] * 4

        def turned(k):
            out = [r[k:] + r[:k] for r in rows]
            return gfx.encode([v for r in out for v in r[:8]]), gfx.encode([v for r in out for v in r[8:]])

        self.assertEqual(check.rotation([turned(3)], [(left, right)]), 3)
        self.assertIsNone(check.rotation([(right, left[::-1])], [(left, right)]))


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

    def test_dq5_tiles_stay(self):
        self.assertEqual(self.tiles[:gfx.TILES * 32], self.original["tiles"])
        self.assertEqual(self.nibbles[:gfx.TILES], self.original["tile_palettes"])
        self.assertEqual(self.attrs[:gfx.TILES], self.original["tile_attributes"])
        self.assertLessEqual(len(self.tiles) // 32, 1024)
        self.assertEqual(len(self.tiles) // 32, len(self.nibbles))
        self.assertTrue(set(self.nibbles[gfx.TILES:]) <= set(gfx.LINES))

    def test_blocks_keep_the_borrowed_terrain_and_attributes(self):
        by_number = {b["index"]: b for b in self.blocks}
        self.assertEqual(sorted(by_number), sorted(set(port.OWN_BLOCKS.values()) - {port.SEA}))
        for kind, number in port.OWN_BLOCKS.items():
            if number == port.SEA:
                continue
            lower, upper, ground = self.dq5(port.BLOCKS[kind])
            block = by_number[number]
            self.assertEqual(block["terrain"], ground)
            want = [self.original["tile_attributes"][u or lo] for lo, u in zip(lower, upper)]
            got = [self.attrs[u or lo] for lo, u in zip(block["lower"], block["upper"])]
            self.assertEqual(got, want, f"{kind:02X}")

    def test_reef_is_rocks_over_the_sea(self):
        block = next(b for b in self.blocks if b["index"] == port.OWN_BLOCKS[gfx.REEF])
        self.assertEqual(block["lower"], list(gfx.SEA_TILES))
        self.assertTrue(all(t >= gfx.TILES for t in block["upper"]))
        self.assertTrue(any(gfx.decode(self.tiles[t * 32:t * 32 + 32]).count(0) for t in block["upper"]))


if __name__ == "__main__":
    unittest.main()
