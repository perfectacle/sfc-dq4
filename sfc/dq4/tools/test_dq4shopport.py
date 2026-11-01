"""With both ROMs, the FC shops, inns and sellers of the new groups as DQ5 data."""

import json
import sys
import tempfile
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


class KeysTest(unittest.TestCase):
    def test_one_key_per_fc_group_split_where_a_kind_repeats(self):
        # FC 그룹 40 의 맵 0·1·2 가 DQ5 45/00~02: 맵 2 가 갑옷을 또 팔아 거기서 키를 나눈다. FC 41 은 같은 DQ5 그룹의
        # 다른 줄, 파는 것 없는 FC 42 는 키를 받지 않는다.
        place = {(0x40, 0): (0x45, 0), (0x40, 1): (0x45, 1), (0x40, 2): (0x45, 2), (0x41, 0): (0x45, 3),
                 (0x42, 0): (0x46, 0)}
        kinds = {(0x45, 0): {3}, (0x45, 1): {6}, (0x45, 2): {3, 1}, (0x45, 3): {6}}
        rows = shopport.keys(place, kinds)
        first = shopport.dq4shopkey.KEY_FIRST
        self.assertEqual(rows, [(0x45, 0, 1, first), (0x45, 2, 2, first + 1), (0x45, 3, 3, first + 2)])
        # 키 줄이 겹치면 훅이 앞 줄만 찾으므로 dq4shopkey 가 받아들이는 줄이어야 한다
        shopport.dq4shopkey.table(rows)


class FakeRom:
    """여관 값 표 자리에 0, 1, 2, … 를 둔 DQ5 롬."""

    def u8(self, addr):
        return (addr - shopport.INN_TABLE) & 0xFF


class SyntheticPortTest(unittest.TestCase):
    """롬 없이 port 가 FC 가게 목록·여관 값을 DQ5 목록·여관 표로 엮는 것을 본다. FC·DQ5 표 읽기는 바꿔 끼운다."""
    PLACE = {(0x10, 0): (0x36, 0), (0x10, 1): (0x36, 1), (0x11, 0): (0x37, 0)}
    NAMES = ["やくそう", "こんぼう", "いばらのむち", "うまのふん", "かわのよろい", "どくけしそう", "てつのやり"]
    ITEMS = {"ヤクソウ": 0x60, "コンボウ": 0x02, "イバラノムチ": 0x06, "カワノヨロイ": 0x40, "ドクケシソウ": 0x61,
             "テツノヤリ": 0x01}

    def run_port(self, services=None, lookup=None, prices=None, inn=None, inn_at=0x3CF000):
        from unittest import mock
        services = services or {(0x10, 0): {(1, 1, False): 1, (1, 1, True): 1, (2, 2, False): 6, (2, 2, True): 6},
                                (0x10, 1): {(3, 3, False): 3}, (0x11, 0): {(4, 4, False): 2, (5, 5, False): 6}}
        lookup = lookup or {(1, 0x10, 0): [0x81, 0x02, 0x03], (3, 0x10, 1): [0x04], (2, 0x11, 0): [0x00, 0x05]}
        prices = prices or {}
        inn = inn or {(0x10, 0): 4, (0x11, 0): 6}
        groups = {f"m{g:02X}{n:02X}": (g, n) for g, n in self.PLACE.values()}
        progress = {"shops": [{"kind": 0}, {"kind": 2}, {"kind": 2}]}
        fc_of = {v: k for k, v in self.PLACE.items()}
        self.itemwrites = mock.Mock(return_value=[{"at": "23:B000", "hex": "00"}])
        with tempfile.TemporaryDirectory() as t, \
                mock.patch.multiple(shopport, GROUPS=groups, placement=lambda prg: self.PLACE,
                                    fc_map=lambda prg, g, n: fc_of[g, n], has_people=lambda g, w: w,
                                    merchants=lambda prg, g, n, items: services.get((g, n), {}),
                                    dq5_items=lambda rom: self.ITEMS,
                                    _dump_progress=lambda path: json.dumps(progress)), \
                mock.patch.object(shopport.ines, "prg", lambda data: b"prg"), \
                mock.patch.object(shopport.dq5item, "Rom", lambda data: FakeRom()), \
                mock.patch.object(shopport.dq5item, "item_name", lambda rom, i: f"item{i:02X}"), \
                mock.patch.object(shopport.dq4shop, "item_names", lambda prg: (self.NAMES, None)), \
                mock.patch.object(shopport.dq4shop, "lookup", lambda prg, k, g, n: lookup[k, g, n]), \
                mock.patch.object(shopport.dq4shop, "price", lambda prg, g, n, i: prices.get((g, n, i), 10 * i + 5)), \
                mock.patch.object(shopport.dq4shop, "inn_price", lambda prg, g, n: inn.get((g, n))), \
                mock.patch.object(shopport.dq4itemport, "writes", self.itemwrites):
            dq5, dq4 = Path(t) / "dq5.sfc", Path(t) / "dq4.nes"
            dq5.write_bytes(b"")
            dq4.write_bytes(b"")
            return shopport.port(str(dq5), str(dq4), inn_at, 0x3CFE00)

    def test_lists_follow_the_existing_ones_of_their_kind(self):
        services, shops, writes, report = self.run_port()
        first = shopport.dq4shopkey.KEY_FIRST
        self.assertEqual(report["keys"], {"36/00-01": f"{first:02X}", "37/00-00": f"{first + 1:02X}"})
        # DQ5 의 무기 목록 둘 뒤에 이어 붙고(index 2), 갑옷·도구도 제 종류의 개수부터
        self.assertEqual(shops, [{"kind": 2, "index": 2, "key": first, "items": [0x02, 0x06]},
                                 {"kind": 1, "index": 0, "key": first, "items": [0x40]},
                                 {"kind": 0, "index": 1, "key": first + 1, "items": [0x60, 0x61]}])
        # bit7 이 붙은 FC 항목 번호는 그 아래 7비트의 이름이고, DQ5 에 없는 うまのふん 은 빠진 것으로 남긴다
        self.assertEqual(report["missing_items"], ["36/00 うまのふん"])
        self.assertEqual(services["36/00"][1, 1, True], 1)

    def test_inn_table_keeps_the_original_entries_and_adds_the_new_keys(self):
        _, _, writes, report = self.run_port(inn_at=0x3CF123)
        first = shopport.dq4shopkey.KEY_FIRST
        table, bank, addr = writes[:3]
        data = bytes.fromhex(table["hex"])
        self.assertEqual(data[:shopport.INN_ENTRIES * 2], bytes(range(shopport.INN_ENTRIES * 2)))
        self.assertEqual(data[shopport.INN_ENTRIES * 2:], bytes((first, 4, first + 1, 6)))
        self.assertEqual((table["at"], bank["at"], addr["at"]), ("3C:F123", "06:F568", "06:F56E"))
        # 06:F56D 의 LDA 피연산자는 낮은 바이트부터
        self.assertEqual((bank["hex"], addr["hex"]), ("3C", "23 F1"))
        self.assertEqual(report["inns"], {"36/00": 4, "37/00": 6})

    def test_second_inn_of_an_fc_group_gets_its_own_key_and_price(self):
        services = {(0x10, 0): {(2, 2, False): 6}, (0x10, 1): {(3, 3, False): 6}}
        _, _, writes, report = self.run_port(services=services, inn={(0x10, 0): 4, (0x10, 1): 5})
        first = shopport.dq4shopkey.KEY_FIRST
        self.assertEqual(report["keys"], {"36/00-00": f"{first:02X}", "36/01-01": f"{first + 1:02X}"})
        self.assertEqual(bytes.fromhex(writes[0]["hex"])[shopport.INN_ENTRIES * 2:], bytes((first, 4, first + 1, 5)))

    def test_item_prices_go_to_the_item_writes(self):
        _, _, writes, report = self.run_port()
        prices = self.itemwrites.call_args.args[2]
        self.assertEqual(prices, {0x02: 15, 0x06: 25, 0x40: 45, 0x60: 5, 0x61: 55})
        self.assertEqual(writes[-1], {"at": "23:B000", "hex": "00"})
        self.assertEqual(report["prices"]["02 item02"], 15)

    def test_refusals(self):
        with self.assertRaisesRegex(ValueError, "bank 40"):
            self.run_port(inn_at=0x40F000)
        with self.assertRaisesRegex(ValueError, "inn price"):
            self.run_port(inn={(0x10, 0): 0x80, (0x11, 0): 6})
        # 같은 DQ5 도구를 두 가게가 다른 FC 값으로 팔면 값 하나를 고를 수 없다
        with self.assertRaisesRegex(ValueError, "FC prices"):
            self.run_port(prices={(0x10, 0, 1): 15, (0x11, 0, 1): 20},
                          lookup={(1, 0x10, 0): [0x01], (3, 0x10, 1): [0x04], (2, 0x11, 0): [0x01]})
        with self.assertRaisesRegex(ValueError, "more than"):
            self.run_port(lookup={(1, 0x10, 0): [0x01] * 7, (3, 0x10, 1): [0x04], (2, 0x11, 0): [0x00]})


class HasGoodsTest(unittest.TestCase):
    def test_a_list_counts_only_items_dq5_has(self):
        from unittest import mock
        shopport._names.cache_clear()
        self.addCleanup(shopport._names.cache_clear)
        names = ["うまのふん", "いばらのむち"]
        with mock.patch.object(shopport.dq4shop, "item_names", lambda prg: (names, None)), \
                mock.patch.object(shopport.dq4shop, "lookup", lambda prg, k, g, n: {(1, 0): [0x80], (1, 1): [0x00, 0x81]}[k, n]):
            items = {"イバラノムチ": 6}
            self.assertFalse(shopport.has_goods(b"x", 1, 0x10, 0, items))
            # 항목 bit7 은 이름 번호가 아니고, 히라가나 이름도 DQ5 의 가타카나 이름에 맞는다
            self.assertTrue(shopport.has_goods(b"x", 1, 0x10, 1, items))
            # 목록이 없는 여관·교회는 늘 있다
            self.assertTrue(shopport.has_goods(b"x", 6, 0x10, 0, {}))


class Dq5ItemsTest(unittest.TestCase):
    def test_borrowed_slot_takes_the_fc_name_and_duplicates_are_refused(self):
        from unittest import mock
        names = {i: f"item{i:02X}" for i in range(216)}
        with mock.patch.object(shopport.dq5item, "item_name", lambda rom, i: names[i]):
            items = shopport.dq5_items(None)
            for slot, name in shopport.dq4itemport.BORROWED.items():
                self.assertEqual(items[shopport._fold(name)], slot)
            names[0x30] = names[0x31]
            with self.assertRaisesRegex(ValueError, "share the name"):
                shopport.dq5_items(None)


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
                                               "45/05-05": "6B", "45/00-02": "6C", "45/03-04": "6D", "45/06-0B": "6E",
                                               "46/00-03": "6F"})
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
        self.assertEqual(len(data), (shopport.INN_ENTRIES + 12) * 2)
        self.assertEqual(data[-24:], bytes((0x60, 4, 0x61, 6, 0x62, 3, 0x65, 10, 0x66, 6, 0x67, 8, 0x68, 3, 0x6A, 6,
                                            0x6B, 6, 0x6C, 2, 0x6E, 6, 0x6F, 3)))
        self.assertEqual(self.report["inns"], {"36/00": 4, "37/00": 6, "3D/03": 3, "3F/01": 10, "40/00": 6, "40/0E": 8,
                                               "41/00": 3, "43/00": 6,
                                               "45/00": 2, "45/05": 6, "45/0A": 6, "46/00": 3})
        self.assertEqual((shop_site["at"], inn_site["at"]), ("06:DC37", "06:F576"))
        self.assertEqual((bank["hex"], addr["hex"]), ("3C", "00 F0"))


if __name__ == "__main__":
    unittest.main()
