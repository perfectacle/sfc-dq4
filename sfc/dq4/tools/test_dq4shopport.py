"""With both ROMs, the FC shops, inns and sellers of the new groups as DQ5 data."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dq4shopport as shopport  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
DQ4 = ROOT / "rom" / "dq4.nes"
DQ5 = ROOT / "rom" / "dq5.sfc"


class FoldTest(unittest.TestCase):
    def test_hiragana_folds_to_katakana(self):
        self.assertEqual(shopport._fold("いばらのむち"), shopport._fold("いばらのムチ"))


@unittest.skipUnless(DQ4.is_file() and DQ5.is_file(), "local source ROMs not present")
class PortTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.services, cls.shops, cls.writes, cls.report = shopport.port(str(DQ5), str(DQ4), 0x3CF000, 0x3CFC00)

    def test_sellers(self):
        # Burland's armor seller opens across the counter through talk script 00D; Imuru's inn through 011.
        self.assertEqual(self.services["36/00"][(0x1F, 0x16, False)], 3)
        self.assertEqual(self.services["37/00"][(0x11, 0x12, False)], 6)

    def test_lists_keyed_by_fc_group(self):
        self.assertEqual(self.report["keys"], {"36/00-03": "60", "37/00-02": "61"})
        weapons = next(s for s in self.shops if s["key"] == 0x60 and s["kind"] == 2)
        self.assertEqual(weapons["items"], [0x02, 0x06, 0x1C, 0x07])  # いばらのむち = DQ5 いばらのムチ
        self.assertIn("37/00 てつのやり", self.report["missing_items"])

    def test_inn_table_and_operands(self):
        table, bank, addr, _, shop_site, inn_site = self.writes
        data = bytes.fromhex(table["hex"].replace(" ", ""))
        self.assertEqual(len(data), (shopport.INN_ENTRIES + 2) * 2)
        self.assertEqual(data[-4:], bytes((0x60, 4, 0x61, 6)))
        self.assertEqual(self.report["inns"], {"36/00": 4, "37/00": 6})
        self.assertEqual((shop_site["at"], inn_site["at"]), ("06:DC37", "06:F576"))
        self.assertEqual((bank["hex"], addr["hex"]), ("3C", "00 F0"))


if __name__ == "__main__":
    unittest.main()
