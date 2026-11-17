"""엔돌 네네 가게(dq4neneshop): 날 바뀜 매상 루틴을 w65816 로 돌려 FC 15:$9F79 의 식과 견주고, 대화·받침 꼴을 본다."""
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4ch3event as ch3  # noqa: E402
import dq4ch3slots as slots  # noqa: E402
import dq4neneshop as shop  # noqa: E402
from w65816 import Cpu  # noqa: E402

VARS2 = slots.VARS2_AT + slots.SLOTS['E'].vars2[0]
FAR = slots.SLOTS['E'].far[0]
# 물건 번호: (값 바이트, 배율). 값 = 바이트 × 10^배율
PRICES = {0x01: (100, 0), 0x0C: (200, 1), 0x20: (25, 2)}


def lorom(a):
    return ((a >> 16 & 0x7F) << 15) | (a & 0x7FFF)


def value(item):
    b, k = PRICES[item]
    return b * 10 ** k


def fc_day(stock, rolls):
    """FC 식: 칸마다 r < C0 이면 값 × (96 + ⌊r × 33/256⌋)/64 를 더하고 칸을 비운다. (매상, 남은 칸)."""
    rolls, sales, left = iter(rolls), 0, []
    for item in stock:
        if item is None:
            left.append(None)
            continue
        if next(rolls) < 0xC0:
            sales += value(item) * (96 + next(rolls) * 33 // 256) // 64
            left.append(None)
        else:
            left.append(item)
    return sales, left


class DayTest(unittest.TestCase):
    def run_day(self, stock, rolls, sales=0):
        rom = bytearray(0x280000)
        code = shop._day(VARS2)
        rom[lorom(FAR):lorom(FAR) + len(code)] = code
        for item, (b, k) in PRICES.items():
            rom[lorom(shop.PRICE_BASE + item)] = b
            rom[lorom(shop.PRICE_SCALE + item)] = k
        w = bytearray(0x20000)
        for i, item in enumerate(stock):
            w[(VARS2 & 0xFFFF) + shop.STOCK + i] = 0 if item is None else item + 1
        for k in range(3):
            w[(VARS2 & 0xFFFF) + shop.SALES + k] = sales >> 8 * k & 0xFF
        c = Cpu(bytes(rom), w)
        rolls = iter(rolls)

        def random(cpu):
            cpu.a = (cpu.a & 0xFF00) | (next(rolls) * (cpu.a & 0xFF)) >> 8
            cpu.rtl()
            return True
        c.hooks[shop.RANDOM] = random
        c.jsl(FAR, max_steps=200000)
        got = c.wram
        base = (VARS2 & 0xFFFF)
        left = [None if got[base + shop.STOCK + i] == 0 else got[base + shop.STOCK + i] - 1 for i in range(len(stock))]
        return int.from_bytes(got[base + shop.SALES:base + shop.SALES + 3], 'little'), left

    def test_day_matches_the_fc_formula(self):
        cases = [
            ([0x0C, 0x0C, 0x01], [0, 0, 0, 0xFF, 0x10, 0x80]),
            ([0x0C, None, 0x20, 0x01], [0xBF, 0x40, 0xC0, 0x00, 0x22]),
            ([0x20] * 3, [0xFF, 0xFF, 0x00, 0xFF]),
        ]
        for stock, rolls in cases:
            want = fc_day(stock + [None] * (shop.STOCK_SLOTS - len(stock)), rolls)
            self.assertEqual(self.run_day(stock + [None] * (shop.STOCK_SLOTS - len(stock)), rolls), want, stock)

    def test_sales_add_to_what_is_left(self):
        sales, _ = self.run_day([0x0C] + [None] * (shop.STOCK_SLOTS - 1), [0, 0], sales=0xFFFF)
        self.assertEqual(sales, 0xFFFF + 3000)

    def test_empty_stock_rolls_nothing(self):
        self.assertEqual(self.run_day([None] * shop.STOCK_SLOTS, []), (0, [None] * shop.STOCK_SLOTS))


class ShapeTest(unittest.TestCase):
    def test_stock_fits_the_second_vars(self):
        self.assertLessEqual(shop.STOCK + shop.STOCK_SLOTS, slots.SLOTS['E'].vars2[1] - slots.SLOTS['E'].vars2[0])

    def test_low_stubs(self):
        # 뱅크 4E 의 코드는 BRK 를 받침으로만 부른다(BRK 는 놓인 뱅크를 DB 로 둠)
        code, where = shop.low_stubs(slots.LOW_STUBS[0])
        self.assertLessEqual(slots.LOW_STUBS[0] + len(code), slots.LOW_STUBS[1])
        for name, args in shop.BRKS.items():
            at = where[name] - slots.LOW_STUBS[0]
            self.assertEqual(code[at:at + len(args) + 2], bytes((0x00, *args, 0x6B)), name)
        stock = shop._stock(VARS2, {k: 0x1234 for k in shop.MESSAGES}, where)
        jsl = {bytes((0x22, a & 0xFF, a >> 8 & 0xFF, a >> 16)) for a in where.values()}
        self.assertTrue(all(j in stock for j in jsl), '받침을 모두 씀')

    def test_number_and_item_codes(self):
        self.assertIn(0x1004, shop.MESSAGES['nene_sales'])
        self.assertIn(0x100A, shop.MESSAGES['nene_item'])
        self.assertIn(0x1004, shop.MESSAGES['nene_offer'])
        self.assertNotIn(0x100A, shop.MESSAGES['nene_precious'])

    def test_counter_talk_falls_back(self):
        ctx = next(c for c in ch3.contexts(0x1000) if c.key == 'E')
        body = shop.counter_talk(ctx, [{'op': 'marker'}])
        self.assertEqual(body[1]['else'], [{'op': 'marker'}])


if __name__ == '__main__':
    unittest.main()
