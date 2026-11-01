"""가게 표(종류별 목록 경계·못 찾으면 다음 종류로 넘어감·덧붙임 품목)·여관 값·가격 갈래·가게 인물 찾기를
합성 PRG 로 검사한다."""
import unittest

import dq4map
import dq4shop as s
import dq4talk

PRG_SIZE = 32 * 0x4000


def put(prg, bank, addr, data):
    o = bank * 0x4000 + (addr & 0x3FFF)
    prg[o:o + len(data)] = bytes(data)


def word(v):
    return [v & 0xFF, v >> 8]


def shop_prg():
    prg = bytearray(PRG_SIZE)
    put(prg, s.TABLE_BANK, s.LIST_PTRS, word(0xA000) + word(0xA100) + word(0xA007))
    # 무기(1): 02/00, 03/01 두 줄. 다음 종류(방어구 A007) 시작에서 끊긴다
    put(prg, s.TABLE_BANK, 0xA000, [0x02, 0x00, 0x01, 0x82, 0x03, 0x01, 0x85])
    # 방어구(3): 무기 표 바로 뒤. 04/00 한 줄, 그리고 FF 기본 줄
    put(prg, s.TABLE_BANK, 0xA007, [0x04, 0x00, 0x20, 0xA1, 0xFF, 0x30, 0xB1])
    # 도구(2): 05/00
    put(prg, s.TABLE_BANK, 0xA100, [0x05, 0x00, 0x40, 0xC1, 0xFF, 0xC2])
    put(prg, s.TABLE_BANK, s.INN_TABLE, [0x02, 0x00, 6, 0x03, 0x01, 12, 0xFF])
    put(prg, s.CODE_BANK, s.EXTRA_16, [0x11, 0x12, 0x13])
    put(prg, *dq4map.GROUPS, [0xFF, 0xFF])
    return prg


class ListTests(unittest.TestCase):
    def setUp(self):
        self.prg = shop_prg()

    def test_lists_stop_at_next_kind_start(self):
        self.assertEqual(s.shop_lists(self.prg, 1), [(0x02, 0x00, [0x01, 0x02]), (0x03, 0x01, [0x05])])
        self.assertEqual(s.shop_lists(self.prg, 3), [(0x04, 0x00, [0x20, 0x21]), (0xFF, None, [0x30, 0x31])])

    def test_lookup_falls_through_to_later_lists(self):
        self.assertEqual(s.lookup(self.prg, 1, 0x03, 0x01), [0x05])
        self.assertEqual(s.lookup(self.prg, 1, 0x04, 0x00), [0x20, 0x21])   # 무기 표에 없으면 방어구 표의 줄
        self.assertEqual(s.lookup(self.prg, 1, 0x09, 0x00), [0x30, 0x31])   # FF 줄이 받는다
        self.assertEqual(s.lookup(self.prg, 2, 0x09, 0x00), [0x42])          # 도구 표는 맨 뒤라 자기 FF 줄

    def test_extras(self):
        sram = bytearray(0x2000)
        sram[s.FLAGS_16 - 0x6000 + 1] = 1
        self.assertEqual(s.with_extras(self.prg, 1, 0x16, 0x00, [0x01], sram), [0x01, 0x12])
        sram[s.TIME - 0x6000] = 0x10
        self.assertEqual(s.with_extras(self.prg, 1, 0x09, 0x00, [0x01], sram), list(s.DAY_09))
        sram[s.TIME - 0x6000] = 0x80
        self.assertEqual(s.with_extras(self.prg, 1, 0x09, 0x00, [0x01], sram), [0x01])
        self.assertEqual(s.with_extras(self.prg, 3, 0x16, 0x00, [0x01], sram), [0x01])

    def test_inns(self):
        self.assertEqual(s.inns(self.prg), [(0x02, 0x00, 6), (0x03, 0x01, 12)])
        self.assertEqual(s.inn_price(self.prg, 0x03, 0x01), 12)
        self.assertEqual(s.inn_price(self.prg, 0xFE, 0x00), s.INN_10_PRICE)
        self.assertIsNone(s.inn_price(self.prg, 0x07, 0x00))

    def test_offer_texts(self):
        self.assertIn('10G', s.offer(self.prg, 0x10, 0x00, 6, y=0x12))
        self.assertEqual(s.offer(self.prg, 0x02, 0x00, 6, y=0x30), '1인 6G')
        self.assertEqual(s.offer(self.prg, 0x46, 0x00, 5), '되살리기·해독·저주')
        self.assertEqual(s.offer(self.prg, 0x02, 0x00, s.FREE_INN), '값 없음')


class PriceTests(unittest.TestCase):
    def setUp(self):
        self.prg = shop_prg()
        rows = [(0x10, 100), (0x11, 2500)] + [(0xFE, 0)] * 4 + [(0, 777)]
        put(self.prg, s.CODE_BANK, s.CASINO_TABLE, [v for it, p in rows for v in [it] + word(p)])

    def test_casino_rows_and_default(self):
        self.assertEqual(s.price(self.prg, 0x04, 0x01, 0x11), 2500)
        self.assertEqual(s.price(self.prg, 0x04, 0x01, 0x55), 777)

    def test_medal_king(self):
        self.assertEqual(s.price(self.prg, 0x22, 0x00, 0x4E), 4)
        self.assertEqual(s.price(self.prg, 0x22, 0x00, 0x50), s.PRICE_22_OTHER)

    def test_group_18_falls_into_later_compares_with_item(self):
        self.assertEqual(s.price(self.prg, 0x18, 0x00, 0x06), 10)
        self.assertEqual(s.price(self.prg, 0x18, 0x00, 0x22), s.PRICE_22_OTHER)   # A 가 아이템 22 라 メダル 왕 값


class ServiceTests(unittest.TestCase):
    def test_adb7_kind(self):
        self.assertEqual([s.adb7_kind(x, y) for x, y in ((0x1C, 0), (0x1D, 0x12), (0x1D, 0x13), (0x05, 0))], [5, 2, 3, 1])

    def test_services_collect_conditions(self):
        tree = [('if', True, 0x14, [], [('service', [6])], [('call', [0xB7, 0xAD])])]
        got = s.services(tree, 0x1D, 0x12)
        self.assertEqual(got, [(6, ['not day'], '스크립트'),
                               (2, ['아님(not day)', '인물 자리 (1D,12)'], '호출 15:ADB7')])

    def test_possible(self):
        self.assertTrue(s.possible(['not day'], True))
        self.assertFalse(s.possible(['not day'], False))
        self.assertTrue(s.possible(['기타'], False))


class MerchantTests(unittest.TestCase):
    def test_day_and_night_records(self):
        prg = shop_prg()
        g, k = 0x02, 0x00
        put(prg, dq4map.NPC_BANK, 0x8000 + 2 * g, word(0x9000))
        tid = 0x010
        # 낮·밤 둘 다 있는 레코드: 대화 번호(낮 010)는 스크립트, 밤은 서비스 6(여관)
        rec = [0x18 | 0x01, tid >> 8 << 2 | 0x00, 0, 0, tid & 0xFF, 0x05, 0x06, 0x06, 0x08, 0x09, 0, 0]
        put(prg, dq4map.NPC_BANK, 0x9000, rec + [0x00])
        put(prg, *dq4map.EVENT_LISTS, word(0x9800))
        put(prg, 0x1C, 0x9800, [0xFF])
        put(prg, dq4talk.BANK, dq4talk.SCRIPTS + 2 * (tid - dq4talk.SCRIPT_FIRST), word(0x9000))
        put(prg, dq4talk.BANK, 0x9000, [0x07, 0x14, 0x12, 0x01, 0x3F])     # if day: service 1(무기점)
        out = s.merchants(prg, g, k)
        self.assertEqual(out, [(5, 6, tid, 1, ['day', '낮'], '스크립트'), (8, 9, 6, 6, ['밤'], '직접')])


if __name__ == '__main__':
    unittest.main()
