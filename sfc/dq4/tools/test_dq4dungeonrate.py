import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

import dq4dungeonrate as rate  # noqa: E402

ROOT = TOOLS.parents[2]
DQ4 = ROOT / "rom" / "dq4.nes"
ZONE = 0x50


class CodeTest(unittest.TestCase):
    def test_tables_first(self):
        zones = [(ZONE, [1, 3, 7, 15]), (0x54, [2, 4, 9, 18])]
        maps = [(0x3B, 0, 4, [(2, 0), (6, 1)])]
        at = 0x578000
        data, labels = rate.code(at, zones, maps)
        region_at, chance_at = rate.chance_offsets(at, zones)
        base = 0x57 * 0x8000
        self.assertEqual(region_at, base)
        self.assertEqual(data[0], rate.REGION_CHANCE)
        self.assertEqual([data[o - base:o - base + rate.STEPS] for o in chance_at],
                         [bytes((1, 3, 7, 15)), bytes((2, 4, 9, 18))])
        self.assertEqual(data[1:3], (ZONE * rate.ZONE_RECORD).to_bytes(2, "little"))
        self.assertGreater(labels["hook"], labels["maps"])
        rom = bytes(base) + data
        self.assertEqual(rate.rom_patch(rom, at, [0xFF] * rate.STEPS, 0),
                         f"{base:X}=00;{chance_at[0]:X}=FFFFFFFF;{chance_at[1]:X}=FFFFFFFF")

    def test_walk(self):
        # Every second cell is a step; a step onto a block of another region is 55. Walking to and fro across a
        # block edge (cells 4 to 7) is still one step a second cell.
        walk = rate.Walk([(ZONE, [1, 3, 7, 15])], [(0x3B, 0, 4, [(2, 0), (6, 1)])])
        got = [walk.step(0x3B, 0, cells, x, 1, ZONE * rate.ZONE_RECORD)
               for cells, x in enumerate([0, 1, 2, 3, 4, 3, 4, 5, 6, 7], 1)]
        self.assertEqual(got, [0, 1, 0, 3, 0, 7, 0, rate.REGION_CHANCE, 0, 15])
        # A fight (the cells drop) starts the count over.
        self.assertEqual(walk.step(0x3B, 0, 1, 8, 1, ZONE * rate.ZONE_RECORD), 0)
        self.assertEqual(walk.step(0x3B, 0, 2, 10, 1, ZONE * rate.ZONE_RECORD), 1)
        self.assertIsNone(walk.step(0x3B, 0, 3, 12, 1, 0))


@unittest.skipUnless(DQ4.exists(), "rom/dq4.nes")
class RomTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from kr_patch.fc import ines
        cls.prg = ines.prg(DQ4.read_bytes())

    def test_chances(self):
        # 18:$A33D 2, 4, 8 then 16, terrain 0F: base 16 is 1, 3, 7, 15 and base 20 2, 4, 9, 18.
        self.assertEqual(rate.chances(self.prg, 16), [1, 3, 7, 15])
        self.assertEqual(rate.chances(self.prg, 20), [2, 4, 9, 18])

    def test_regions(self):
        # FC 1C/01 is one region; FC 3A/00 (the well bottom's first map) has two.
        self.assertIsNone(rate.region_runs(self.prg, 0x1C, 1))
        width, runs = rate.region_runs(self.prg, 0x3A, 0)
        self.assertEqual(width, 28)
        self.assertEqual(sum(n for n, _ in runs), 28 * 52)
        self.assertEqual({r for _, r in runs}, {0, 1})


if __name__ == "__main__":
    unittest.main()
