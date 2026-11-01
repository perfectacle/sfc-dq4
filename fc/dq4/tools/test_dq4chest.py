"""보물상자·발밑 아이템 표(전체 순번·내용 바이트 갈래·주웠음 플래그)와 대화 루틴의 주는 것 찾기를 합성 PRG 로 검사한다."""
import unittest

import dq4chest as c
import dq4map

PRG_SIZE = 32 * 0x4000


def put(prg, bank, addr, data):
    o = bank * 0x4000 + (addr & 0x3FFF)
    prg[o:o + len(data)] = bytes(data)


def word(v):
    return [v & 0xFF, v >> 8]


def chest_prg():
    prg = bytearray(PRG_SIZE)
    put(prg, *dq4map.GROUPS, [0xFF, 0xFF])              # 맵이 없으면 상자 칸은 개수 표로만
    put(prg, c.CHEST_BANK, c.COUNT_PTR, word(0xA000) + word(0xA100))
    put(prg, c.CHEST_BANK, 0xA000, [0x01, 0x00, 2, 0x01, 0x02, 3, 0x05, 0x00, 1, 0xFF])
    put(prg, c.CHEST_BANK, 0xA100, [0x10, 0x11, 0x12, 0xFF, 0xFE, 0x85, 0x03])
    put(prg, c.CHEST_BANK, c.SPECIAL_CHEST, [2, 0xFF, 0xFE])
    return prg


class ChestTests(unittest.TestCase):
    def setUp(self):
        self.prg = chest_prg()

    def test_base_sums_earlier_maps_and_missing_map_takes_next(self):
        self.assertEqual([c.chest_base(self.prg, *gk) for gk in ((0x01, 0x00), (0x01, 0x02), (0x01, 0x01), (0x05, 0x00))],
                         [0, 2, 2, 5])

    def test_chests_read_content_by_global_number(self):
        out = c.chests(self.prg, 0x01, 0x02)
        self.assertEqual([(n, x, b) for n, x, _, b, _ in out], [(2, None, 0x12), (3, None, 0xFF), (4, None, 0xFE)])
        self.assertEqual(out[1][4], c.CHEST_SPECIAL[0xFF])

    def test_content_names(self):
        special = c.special_codes(self.prg, c.SPECIAL_CHEST)
        self.assertEqual(special, {0xFF, 0xFE})
        self.assertEqual(c.content_name(self.prg, 0x85, special), '200G')
        self.assertEqual(c.content_name(self.prg, 0x03, special), '아이템 03')

    def test_opened_flag_bits(self):
        sram = bytearray(0x2000)
        sram[c.OPENED - 0x6000 + 1] = 0x20
        self.assertTrue(c.opened(sram, 10))
        self.assertFalse(c.opened(sram, 9))


class FeetTests(unittest.TestCase):
    def test_feet_flag_items_and_special(self):
        prg = chest_prg()
        put(prg, c.CHEST_BANK, c.FEET_TABLE, [0x02, 0x81, 3, 4, 0xA9,
                                               0x02, 0x01, 5, 6, 0xE5,
                                               0x02, 0x01, 7, 8, 0xF0, 0xFF])
        put(prg, c.CHEST_BANK, c.FLAG_ITEMS + 9, [0x82])
        put(prg, c.CHEST_BANK, c.SPECIAL_FEET, [1, 0xE5])
        out = c.feet_items(prg)
        self.assertEqual(out[0], (0x02, 0x01, 3, 4, 0xA9, '80G', (c.FEET_FLAGS + 1, 0x40)))
        self.assertEqual(out[1][5], c.FEET_SPECIAL[0xE5])
        self.assertEqual(out[2][5], '모름 F0')


class GiftScanTests(unittest.TestCase):
    def scan(self, code, at=0x9000):
        prg = bytearray(PRG_SIZE)
        put(prg, 0x15, at, code)
        return prg, c.gift_scan(prg, at)

    def test_give_take_gold_and_flag(self):
        _, out = self.scan([0xA9, 0x10, 0x00, 0x2E, 0x73,          # LDA #10; 넣기
                            0xA9, 0x22, 0x00, 0x66, 0x73,          # LDA #22; 찾기
                            0x00, 0x30, 0x73,                      # 빼기(찾은 아이템)
                            0xA9, 0x01, 0x85, 0x70, 0xA9, 0x00, 0x85, 0x71, 0xA9, 0xF4, 0x00, 0x4B, 0x73,  # 500G
                            0x00, 0x05, 0xCB, 0x40,                # 플래그 05 |= 40
                            0x60])
        self.assertEqual(out, [('give', 0x10), ('take', 0x22), ('gold', 0x1F4), ('flag', (0x05, 0x40))])

    def test_branches_and_jsr_are_followed(self):
        _, out = self.scan([0xD0, 0x05,                            # BNE +5 → $9007(RTS)
                            0xA9, 0x01, 0x20, 0xB1, 0xB0,          # LDA #1; JSR 주기
                            0x60,
                            0x20, 0x00, 0x91,
                            0x60], at=0x9000)
        self.assertEqual(out, [('give', 0x01)])
        prg = bytearray(PRG_SIZE)
        put(prg, 0x15, 0x9000, [0xF0, 0x03, 0x60, 0x00, 0x00, 0x20, 0x00, 0x91, 0x60])
        put(prg, 0x15, 0x9100, [0xA9, 0x07, 0x4C, 0xC2, 0xB0])
        self.assertEqual(c.gift_scan(prg, 0x9000), [('take', 0x07)])

    def test_shop_entry_is_not_followed(self):
        _, out = self.scan([0x20, 0xBF, 0x9C, 0xA9, 0x05, 0x20, 0xB1, 0xB0, 0x60])
        self.assertEqual(out, [('give', 0x05)])

    def test_prize_and_routine_check(self):
        _, out = self.scan([0x20, 0x88, 0xA9, 0xA9, 0x09, 0x20, 0x94, 0xA7, 0x60])
        self.assertEqual(out, [('prize', None), ('check', 'item 09')])


if __name__ == '__main__':
    unittest.main()
