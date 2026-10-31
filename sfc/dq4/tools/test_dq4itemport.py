"""FC prices on the DQ5 item table and the borrowed てつのやり slot."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dq4itemport  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
DQ4 = ROOT / "rom" / "dq4.nes"
DQ5 = ROOT / "rom" / "dq5.sfc"


class PriceTest(unittest.TestCase):
    def test_smallest_scale(self):
        self.assertEqual(dq4itemport.encode_price(30), (30, 0))
        self.assertEqual(dq4itemport.encode_price(880), (88, 1))
        self.assertEqual(dq4itemport.encode_price(9800), (98, 2))
        self.assertEqual(dq4itemport.encode_price(15000), (150, 2))
        self.assertEqual(dq4itemport.encode_price(35000), (35, 3))

    def test_unencodable(self):
        with self.assertRaises(ValueError):
            dq4itemport.encode_price(1234)

    def test_korean_name(self):
        self.assertEqual(dq4itemport.korean_names(), {0x01: "철 창"})


@unittest.skipUnless(DQ4.is_file() and DQ5.is_file(), "local source ROMs not present")
class RomTest(unittest.TestCase):
    def test_borrowed_name_reads_back(self):
        import dq5chest
        import dq5item
        from kr_patch.fc import ines
        rom = dq5item.Rom(DQ5.read_bytes())
        writes = dq4itemport.writes(rom, ines.prg(DQ4.read_bytes()), {})
        data = bytearray(DQ5.read_bytes())
        for w in writes:
            bank, addr = (int(v, 16) for v in w["at"].split(":"))
            o = bank * 0x8000 + (addr & 0x7FFF)
            new = bytes.fromhex(w["hex"])
            self.assertEqual(bytes(data[o:o + len(new)]), bytes.fromhex(w["orig"]))
            data[o:o + len(new)] = new
        patched = dq5item.Rom(bytes(data))
        self.assertEqual(dq5chest.item_name(patched, 0x01), "てつのやり")
        self.assertEqual(dq5item.price(patched, 0x01), 880)
        self.assertEqual(dq5item.field(patched, 5, 0x01), 28)


if __name__ == "__main__":
    unittest.main()
