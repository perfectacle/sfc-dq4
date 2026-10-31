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


class SellerConditionTest(unittest.TestCase):
    def test_story_flag_sellers_at_chapter_start(self):
        # Made-up sellers of one cell: a church that needs a story flag off stays, an inn that needs it on is not
        # there yet, a weapon seller on a story-flag list is not the base list; the day-only item shop stays by day.
        from unittest import mock
        flag = shopport.STORY_FLAG + "06 10"
        rows = [(0x03, 0x04, 0x20, 0, [f"아님({flag})"], ""), (0x03, 0x04, 0x21, 6, [flag], ""),
                (0x03, 0x04, 0x22, 2, [shopport.FLAG_LIST + " 1"], ""), (0x05, 0x06, 0x23, 1, ["낮"], "")]
        with mock.patch.object(shopport.dq4shop, "merchants", return_value=rows):
            found = shopport.merchants(b"", 0x0E, 0)
            self.assertEqual(found, {(0x03, 0x04, False): 5, (0x03, 0x04, True): 5, (0x05, 0x06, False): 1})
            rows.append((0x07, 0x08, 0x24, 1, ["unknown"], ""))
            with self.assertRaises(ValueError):
                shopport.merchants(b"", 0x0E, 0)


@unittest.skipUnless(DQ4.is_file() and DQ5.is_file(), "local source ROMs not present")
class PortTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.services, cls.shops, cls.writes, cls.report = shopport.port(str(DQ5), str(DQ4), 0x3CF000, 0x3CFC00)

    def test_sellers(self):
        # Burland's armor seller opens across the counter through talk script 00D; Imuru's inn through 011.
        self.assertEqual(self.services["36/00"][(0x1F, 0x16, False)], 3)
        self.assertEqual(self.services["37/00"][(0x11, 0x12, False)], 6)

    def test_story_flag_sellers_at_chapter_start(self):
        # テンペ (0C,18): the church needs flag 06 10 off and is kept; the version that needs it on is not there.
        found = shopport.merchants(shopport.ines.prg(DQ4.read_bytes()), 0x0E, 0)
        self.assertEqual(found[0x0C, 0x18, False], 5)

    def test_lists_keyed_by_fc_group(self):
        # 3D holds three FC groups: テンペ (inn, church) and フレノール (item shop) get keys of their own.
        # エンドール (40) sells armour on 40/00 and 40/09 and has inns on 40/00 and 40/0E: two keys, split at 40/09.
        # レイクナバ's 16/01 seller has only うまのふん, which DQ5 lacks, so 3E keeps one key.
        self.assertEqual(self.report["keys"], {"36/00-03": "60", "37/00-02": "61", "3D/03-03": "62", "3D/04-05": "63",
                                               "3E/00-02": "64", "3F/00-01": "65", "40/00-08": "66", "40/09-0E": "67",
                                               "41/00-03": "68", "42/00-01": "69", "43/00-05": "6A",
                                               "45/05-05": "6B", "45/00-02": "6C", "45/03-04": "6D", "45/06-0B": "6E"})
        weapons = next(s for s in self.shops if s["key"] == 0x60 and s["kind"] == 2)
        self.assertEqual(weapons["items"], [0x02, 0x06, 0x1C, 0x07])  # いばらのむち = DQ5 いばらのムチ
        # てつのやり sells in DQ5 slot 01 (dq4itemport.BORROWED), after くさりがま as in FC.
        imle = next(s for s in self.shops if s["key"] == 0x61 and s["kind"] == 2)
        self.assertEqual(imle["items"], [0x06, 0x1C, 0x21, 0x07, 0x01])
        self.assertNotIn("37/00 てつのやり", self.report["missing_items"])

    def test_fc_prices(self):
        prices = self.report["prices"]
        self.assertEqual((prices["02 こんぼう"], prices["06 どうのつるぎ"], prices["07 くさりがま"], prices["01 てつのやり"]),
                         (30, 100, 550, 880))
        at = {w["at"]: w["hex"] for w in self.writes}
        self.assertEqual((at["23:B083"], at["23:B15B"]), ("1E", "00"))  # こんぼう 30 x 1
        self.assertEqual((at["23:B082"], at["23:B15A"], at["23:B4BA"]), ("58", "01", "1C"))  # てつのやり 88 x 10, power 28

    def test_inn_table_and_operands(self):
        table, bank, addr, _, shop_site, inn_site = self.writes[:6]
        data = bytes.fromhex(table["hex"].replace(" ", ""))
        self.assertEqual(len(data), (shopport.INN_ENTRIES + 11) * 2)
        self.assertEqual(data[-22:], bytes((0x60, 4, 0x61, 6, 0x62, 3, 0x65, 10, 0x66, 6, 0x67, 8, 0x68, 3, 0x6A, 6,
                                            0x6B, 6, 0x6C, 2, 0x6E, 6)))
        self.assertEqual(self.report["inns"], {"36/00": 4, "37/00": 6, "3D/03": 3, "3F/01": 10, "40/00": 6, "40/0E": 8,
                                               "41/00": 3, "43/00": 6,
                                               "45/00": 2, "45/05": 6, "45/0A": 6})
        self.assertEqual((shop_site["at"], inn_site["at"]), ("06:DC37", "06:F576"))
        self.assertEqual((bank["hex"], addr["hex"]), ("3C", "00 F0"))


if __name__ == "__main__":
    unittest.main()
