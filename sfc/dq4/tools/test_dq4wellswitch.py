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

    def test_clear_hooks(self):
        writes = well.writes(0x3CFF00, self.prg, self.place)
        data = bytes.fromhex(writes[0]["hex"])
        load, wipe = writes[2:]
        self.assertEqual((load["at"], load["orig"]), ("25:8278", "E2 30 A9 50 8D 5E 07"))
        self.assertEqual((wipe["at"], wipe["orig"]), ("01:88EF", "22 9A FE 24"))
        clear = "AF E1 21 7E 29 FD 8F E1 21 7E"
        at = int.from_bytes(bytes.fromhex(load["hex"])[1:4], "little") - 0x3CFF00
        self.assertEqual(data[at:at + 18].hex(" ").upper(), f"E2 30 {clear} A9 50 8D 5E 07 6B")
        at = int.from_bytes(bytes.fromhex(wipe["hex"])[1:4], "little") - 0x3CFF00
        self.assertEqual(data[at:at + 20].hex(" ").upper(), f"08 E2 20 48 {clear} 68 28 5C 9A FE 24")


if __name__ == "__main__":
    unittest.main()
