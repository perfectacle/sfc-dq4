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
                self.assertFalse(any("S" in row for row in classes), f"18/{block:02X}")

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

    def test_water_blocks_stay_water(self):
        for t in em.SHAPES:
            art = em.sheet_art(self.prg, t)
            for block, d in em.dq4block.defs(self.prg, t).items():
                if block < 32 and d and d["prop"] == 0x83:
                    self.assertEqual(art[block][0], "water0", f"{t:02X}/{block:02X}")


if __name__ == "__main__":
    unittest.main()
