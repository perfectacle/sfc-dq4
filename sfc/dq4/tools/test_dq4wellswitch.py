import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

import dq4wellswitch as well  # noqa: E402

ROOT = TOOLS.parents[2]
DQ4 = ROOT / "rom" / "dq4.nes"


class CodeTest(unittest.TestCase):
    def test_site_branches_to_no_zone(self):
        rows = [(0, 4, 48, well.FLAG[1]), (0, 4, 50, 0)]
        data, labels = well.code(0x3CFF00, 0x3B, rows)
        self.assertEqual(labels["hook"], 0x3CFF00)
        self.assertEqual(data[:4], bytes((0xA5, 0xBC, 0xC9, 0x3B)))
        self.assertTrue(data.endswith(bytes((0, 4, 48, well.FLAG[1], 0, 4, 50, 0, 0xFF))))
        # The table index is 8-bit X.
        with self.assertRaises(ValueError):
            well.code(0x3CFF00, 0x3B, [(0, 0, 0, 0)] * 32)


@unittest.skipUnless(DQ4.exists(), "rom/dq4.nes")
class RomTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from kr_patch.fc import ines
        import dq4groupbuild
        cls.prg = ines.prg(DQ4.read_bytes())
        cls.place = dq4groupbuild.placement(cls.prg)

    def test_cells(self):
        # FC 3A/00 table C2 18: (02,18)(03,18) on and (02,19)(03,19) off; DQ5 3B/00 cells X & FE, (Y-1) & FE.
        rows = well.cells(self.prg, self.place)
        self.assertEqual(len(rows), 28)
        self.assertIn((0, 4, 0x30, well.FLAG[1]), rows)
        self.assertIn((0, 4, 0x32, 0), rows)
        self.assertIn((3, 0x2A, 0x20, well.FLAG[1]), rows)
        self.assertEqual(well.group(self.place), 0x3B)

    def test_writes(self):
        site = well.writes(0x3CFF00, self.prg, self.place)[1]
        self.assertEqual(site["at"], "01:8518")
        # BEQ from 01:851E back onto 01:854B (LDY #0 / PLP / RTL), as the original BEQ.
        self.assertEqual(site["hex"], "22 00 FF 3C F0 2D EA")


if __name__ == "__main__":
    unittest.main()
