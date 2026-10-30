"""SHAPES drawing: slope geometry without ROMs; with rom/dq4.nes, traced water and palette banks."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DQ4 = ROOT / "rom" / "dq4.nes"
sys.path.insert(0, str(Path(__file__).resolve().parent))

import dq4environmentmap as em  # noqa: E402


class SlopeTests(unittest.TestCase):
    def test_floor_triangle_and_diagonal(self):
        left = em._shape_classes(None, 0x11, 0x02, "slope", "cave_rock_brown")
        right = em._shape_classes(None, 0x11, 0x03, "slope_r", "cave_rock_brown")
        self.assertEqual((left[0][0], left[0][15], left[15][15]), ("F", "O", "A"))
        self.assertEqual((right[0][15], right[0][0], right[15][0]), ("F", "O", "A"))
        for rows in (left, right):
            self.assertEqual(sum(row.count("O") for row in rows), 16)
            self.assertEqual(sum(row.count("F") for row in rows), sum(row.count("A") for row in rows))

    def test_stripes_continue_across_stacked_blocks(self):
        rows = em._shape_classes(None, 0x11, 0x07, "stripes", "cave_rock_brown")
        # Bands run down to the right, and the pattern of the next block's row 0 follows this block's row 15.
        self.assertEqual(rows[0][0], "F")
        self.assertEqual(rows[1][1], "F")
        for x in range(16):
            below = (x - 16) % 8
            self.assertEqual(rows[0][x], "F" if below in (0, 1) else "O" if below == 2 else "A")


class LidTests(unittest.TestCase):
    def test_lid_tiles_are_two_tiles_of_the_chest_left_half(self):
        from dq4environmentart import create_assets
        import dq4environmentrom as rom
        assets = create_assets()
        data = rom.lid_tiles(assets)
        self.assertEqual(len(data), 64)
        image = assets["chest_open"]
        # Transparent pixels stay colour 0; every drawn pixel gets a colour of line 6 (1-15).
        for half, y in enumerate((0, 8)):
            tile = image.crop((0, y, 8, y + 8)).tobytes()
            planar = data[half * 32:(half + 1) * 32]
            for i, v in enumerate(tile):
                row, x = divmod(i, 8)
                got = sum((planar[(p >> 1) * 16 + row * 2 + (p & 1)] >> (7 - x) & 1) << p for p in range(4))
                self.assertEqual(got == 0, v == 0, f"tile {half} pixel {x},{row}")


@unittest.skipUnless(DQ4.is_file(), "local source ROM not present")
class TraceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from kr_patch.fc import ines
        from dq4environmentart import create_assets
        cls.prg = ines.prg(DQ4.read_bytes())
        cls.assets = create_assets()
        cls.palette = next(iter(cls.assets.values())).getpalette()

    def test_water_base_keeps_fc_blues(self):
        for block, shape in em.SHAPES[0x18].items():
            kind, _, base = shape.partition(":")
            if base.startswith("water"):
                classes = em._shape_classes(self.prg, 0x18, block, kind, base)
                self.assertFalse(any("S" in row or "D" in row for row in classes), f"18/{block:02X}")

    def test_sky_kinds(self):
        def kinds(t, block):
            art = em.sheet_art(self.prg, t)[block][0]
            kind, _, base = art.partition(":")
            return {c for row in em._shape_classes(self.prg, t, block, kind, base) for c in row}
        self.assertIn("D", kinds(0x22, 0x12))
        self.assertNotIn("S", kinds(0x22, 0x12))
        self.assertIn("S", kinds(0x32, 0x15))
        self.assertNotIn("D", kinds(0x32, 0x15))
        self.assertIn("S", kinds(0x1C, 0x0A))

    def test_one_bank_per_tile(self):
        for t, blocks in em.SHAPES.items():
            art = em.sheet_art(self.prg, t)
            for block in blocks:
                image, _ = em._shape_tile(self.prg, self.assets, art[block][0], self.palette, t, block)
                for y in (0, 8):
                    for x in (0, 8):
                        banks = {v >> 4 for v in image.crop((x, y, x + 8, y + 8)).tobytes()}
                        self.assertEqual(len(banks), 1, f"{t:02X}/{block:02X} at {x},{y}")
                        self.assertNotIn(0, banks)

    def test_water_edges_stay_blue(self):
        art = em.sheet_art(self.prg, 0x18)
        for block, shape in em.SHAPES[0x18].items():
            if shape.endswith("water0"):
                image, _ = em._shape_tile(self.prg, self.assets, art[block][0], self.palette, 0x18, block)
                self.assertTrue(all(v >> 4 == 7 and 1 <= v & 15 <= 7 for v in image.tobytes()), f"18/{block:02X}")

    def test_water_blocks_stay_water(self):
        for t in em.SHAPES:
            art = em.sheet_art(self.prg, t)
            for block, d in em.dq4block.defs(self.prg, t).items():
                if block < 32 and d and d["prop"] == 0x83:
                    self.assertEqual(art[block][0], "water0", f"{t:02X}/{block:02X}")


if __name__ == "__main__":
    unittest.main()
