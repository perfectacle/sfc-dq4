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
    """FC 식: 칸마다 r < C0 이면 값 × (96 + ⌊r × 33/256⌋)/64 를 더하고 목록에서 뺀다(뒤가 앞으로 당겨짐). (매상, 남은 칸)."""
    rolls, sales, left = iter(rolls), 0, []
    for item in stock:
        if item is None:
            continue
        if next(rolls) < 0xC0:
            sales += value(item) * (96 + next(rolls) * 33 // 256) // 64
        else:
            left.append(item)
    return sales, left + [None] * (len(stock) - len(left))


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
            w[shop.stock_addr(i) & 0xFFFF] = 0 if item is None else item + 1
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
        cells = [got[shop.stock_addr(i) & 0xFFFF] for i in range(len(stock))]
        left = [None if v == 0 else v - 1 for v in cells]
        return int.from_bytes(got[base + shop.SALES:base + shop.SALES + 3], 'little'), left

    def test_day_matches_the_fc_formula(self):
        cases = [
            ([0x0C, 0x0C, 0x01], [0, 0, 0, 0xFF, 0x10, 0x80]),
            ([0x0C, None, 0x20, 0x01], [0xBF, 0x40, 0xC0, 0x00, 0x22]),
            ([0x20] * 3, [0xFF, 0xFF, 0x00, 0xFF]),
            # 덩어리 경계(칸 23·24)와 마지막 칸 119
            ([None] * 23 + [0x0C, 0x01] + [None] * 94 + [0x20], [0x00, 0x00, 0x00, 0x80, 0x00, 0x40]),
        ]
        for stock, rolls in cases:
            want = fc_day(stock + [None] * (shop.STOCK_SLOTS - len(stock)), rolls)
            self.assertEqual(self.run_day(stock + [None] * (shop.STOCK_SLOTS - len(stock)), rolls), want, stock)

    def test_sales_add_to_what_is_left(self):
        sales, _ = self.run_day([0x0C] + [None] * (shop.STOCK_SLOTS - 1), [0, 0], sales=0xFFFF)
        self.assertEqual(sales, 0xFFFF + 3000)

    def test_empty_stock_rolls_nothing(self):
        self.assertEqual(self.run_day([None] * shop.STOCK_SLOTS, []), (0, [None] * shop.STOCK_SLOTS))


class ViewTest(unittest.TestCase):
    """nene_view: 창(BRK 95 37)이 열릴 때마다 톨네코 물건 칸 = 비지 않은 가게 물건 8개씩(나머지는 FF), 장비 비트 0,
    가게 종류 $0F20 = 다음 쪽이 있으면 VIEW_MORE, 마지막 쪽이면 +1. 끝나면 톨네코 칸·장비·$0F20 이 그대로이고 가게 칸은
    바뀌지 않는다."""

    def run_view(self, stock, items, equip, answers=()):
        rom = bytearray(0x280000)
        stubs, where = shop.low_stubs(slots.LOW_STUBS[0])
        code = shop._view(VARS2, where)
        rom[lorom(FAR):lorom(FAR) + len(code)] = code
        w = bytearray(0x20000)
        it = ch3.PARTY_ITEMS & 0xFFFF
        for i, item in enumerate(stock):
            w[shop.stock_addr(i) & 0xFFFF] = 0 if item is None else item + 1
        w[it:it + 12] = bytes(items)
        w[it - 2], w[it - 1] = equip & 0xFF, equip >> 8
        w[shop.SHOP_KIND] = 0x05
        before = [w[shop.stock_addr(i) & 0xFFFF] for i in range(shop.STOCK_SLOTS)]
        c = Cpu(bytes(rom), w)
        seen, kinds, lines, answers = [], [], [], iter(answers)
        self.kinds, self.lines = kinds, lines

        def rtl(cpu):
            cpu.rtl()
            return True

        # BRK 받침(BRK … / RTL)은 BRK 처리기가 DB 를 받침 뱅크로 둔 채 돌아온다(헤드리스 쓰기 감시: 보기 동안 절대 주소
        # STA $2824 가 WRAM 에 닿지 않았음). 받침 뒤의 절대 주소 쓰기가 7E:2000 이상을 놓치면 표지 시험이 실패한다
        def stub(cpu):
            cpu.rtl()
            cpu.dbr = slots.LOW_STUBS[0] >> 16
            return True

        def window(cpu):
            seen.append((bytes(cpu.wram[it:it + 12]), cpu.wram[it - 2] | cpu.wram[it - 1] << 8))
            kinds.append(cpu.wram[shop.SHOP_KIND])
            lines.append(cpu.wram[shop.VIEW_COUNT])
            self.assertEqual(cpu.wram[shop.VIEW_MARK], cpu.wram[shop.SHOP_KIND])
            cpu.wram[0xE8] = next(answers, 0)            # 0 = A(다음 쪽), 80 = B(그만둠)
            return stub(cpu)
        for a in (shop.SHOP_ENTER, shop.PICKER_RESET):
            c.hooks[a] = rtl
        for a in where.values():
            c.hooks[a] = stub
        c.hooks[where['pick']] = window
        gold = []

        def gold_window(cpu):
            gold.append(1)
            return stub(cpu)
        c.hooks[where['window']] = gold_window
        c.jsl(FAR, max_steps=500000)
        result = bool(c.wram[(0x2190 + ch3.RESULT[0])] & ch3.RESULT[1])
        after = (bytes(c.wram[it:it + 12]), c.wram[it - 2] | c.wram[it - 1] << 8)
        self.assertEqual([c.wram[shop.stock_addr(i) & 0xFFFF] for i in range(shop.STOCK_SLOTS)], before, '가게 칸')
        self.assertEqual(c.wram[shop.SHOP_KIND], 0x05, '가게 종류 되돌림')
        self.assertEqual(c.wram[shop.VIEW_MARK], 0, '표지 지움')
        self.assertEqual(gold, [], 'FC 처럼 골드 창을 열지 않음')
        return result, seen, after

    def test_pages_of_eight_skip_holes(self):
        # 15개(사이에 빈 칸, 덩어리 경계 23·24 를 넘음) → 8 + 7
        stock = [None] * shop.STOCK_SLOTS
        filled = [0, 2, 5, 9, 11, 20, 22, 23, 24, 25, 40, 60, 80, 100, 119]
        for n, k in enumerate(filled):
            stock[k] = n + 1
        items = [0x42, 0xBB, 0x0C] + [0xFF] * 9
        result, seen, after = self.run_view(stock, items, 0x0001)
        self.assertTrue(result)
        self.assertEqual(seen, [(bytes(range(1, 9)) + b'\xff' * 4, 0), (bytes(range(9, 16)) + b'\xff' * 5, 0)])
        self.assertEqual(self.kinds, [shop.VIEW_MORE, shop.VIEW_MORE + 1])
        self.assertEqual(self.lines, [8, 7])
        self.assertEqual(after, (bytes(items), 0x0001))

    def test_b_stops_after_the_first_page(self):
        stock = [7] * 30 + [None] * (shop.STOCK_SLOTS - 30)
        result, seen, after = self.run_view(stock, [0x42] + [0xFF] * 11, 0x0001, answers=(0x80,))
        self.assertEqual(len(seen), 1)
        self.assertEqual(after, (bytes([0x42] + [0xFF] * 11), 0x0001))

    def test_full_stock_is_fifteen_pages(self):
        stock = [k % 0xD0 for k in range(shop.STOCK_SLOTS)]
        _, seen, _ = self.run_view(stock, [0xFF] * 12, 0)
        self.assertEqual(len(seen), shop.STOCK_SLOTS // shop.VIEW_LINES)
        self.assertEqual(b''.join(p[:shop.VIEW_LINES] for p, _ in seen), bytes(stock))
        self.assertEqual(self.kinds, [shop.VIEW_MORE] * 14 + [shop.VIEW_MORE + 1])

    def test_exactly_one_page_has_no_arrow(self):
        stock = [3] * shop.VIEW_LINES + [None] * (shop.STOCK_SLOTS - shop.VIEW_LINES)
        _, seen, _ = self.run_view(stock, [0xFF] * 12, 0)
        self.assertEqual(len(seen), 1)
        self.assertEqual(self.kinds, [shop.VIEW_MORE + 1])
        self.assertEqual(self.lines, [8])

    def test_view_marker_matches_the_window_patch(self):
        import dq4windowname
        self.assertEqual(shop.VIEW_MORE, dq4windowname.NENE_VIEW_MORE)
        self.assertEqual(shop.VIEW_MARK, VARS2 + shop.MARK & 0xFFFF)
        self.assertEqual(0x7E0000 | shop.VIEW_MARK, dq4windowname.NENE_MARK)
        self.assertEqual(0x7E0000 | shop.VIEW_COUNT, dq4windowname.NENE_LINES)
        self.assertEqual(shop.VIEW_COUNT, VARS2 + shop.LINES & 0xFFFF)

    def test_empty_stock_opens_nothing(self):
        result, seen, after = self.run_view([None] * shop.STOCK_SLOTS, [0x42] + [0xFF] * 11, 0x0001)
        self.assertFalse(result)
        self.assertEqual(seen, [])
        self.assertEqual(after, (bytes([0x42] + [0xFF] * 11), 0x0001))


class ShapeTest(unittest.TestCase):
    def test_save_area_fits_the_second_vars(self):
        self.assertLessEqual(shop.SAVE + shop.ITEM_SLOTS + 2, slots.SLOTS['E'].vars2[1] - slots.SLOTS['E'].vars2[0])
        self.assertGreaterEqual(shop.SAVE, shop.SALES + 3)

    def test_low_stubs(self):
        # 뱅크 4E 의 코드는 BRK 를 받침으로만 부른다(BRK 는 놓인 뱅크를 DB 로 둠)
        code, where = shop.low_stubs(slots.LOW_STUBS[0])
        self.assertLessEqual(slots.LOW_STUBS[0] + len(code), slots.LOW_STUBS[1])
        for name, args in shop.BRKS.items():
            at = where[name] - slots.LOW_STUBS[0]
            self.assertEqual(code[at:at + len(args) + 2], bytes((0x00, *args, 0x6B)), name)
        stock = shop._stock(VARS2, {k: 0x1234 for k in shop.MESSAGES}, where) + shop._view(VARS2, where)
        # window(골드 창 95 34)는 네네가 쓰지 않고(FC 에 골드 창 없음) dq4ch3towns 가 빌려 쓴다
        jsl = {bytes((0x22, a & 0xFF, a >> 8 & 0xFF, a >> 16)) for n, a in where.items() if n != 'window'}
        self.assertTrue(all(j in stock for j in jsl), '받침을 모두 씀')

    def test_picker_is_the_field_item_window(self):
        # FC 036E 의 창처럼 값이 보이지 않게, 고르기는 팔기 창(BRK 95 37, 값 칸이 있음)이 아니라 필드 도구 창(95 0F)
        _, where = shop.low_stubs(slots.LOW_STUBS[0])
        stock = shop._stock(VARS2, {k: 0x1234 for k in shop.MESSAGES}, where)
        jsl = lambda name: bytes((0x22, *(where[name]).to_bytes(3, 'little')))  # noqa: E731
        self.assertIn(jsl('items'), stock)
        self.assertNotIn(jsl('pick'), stock)

    def test_number_and_item_codes(self):
        self.assertIn(0x1004, shop.MESSAGES['nene_sales'])
        self.assertIn(0x100A, shop.MESSAGES['nene_item'])
        self.assertIn(0x1004, shop.MESSAGES['nene_offer'])
        self.assertNotIn(0x100A, shop.MESSAGES['nene_precious'])

    def test_stock_is_the_fc_size(self):
        # FC $61DB 의 칸 수(119개면 036E, 120개면 0377)
        self.assertEqual(shop.STOCK_SLOTS, 120)
        self.assertEqual(len({shop.stock_addr(k) for k in range(shop.STOCK_SLOTS)}), 120)

    def test_counter_talk_falls_back(self):
        ctx = next(c for c in ch3.contexts(0x1000) if c.key == 'E')
        body = shop.counter_talk(ctx, [{'op': 'marker'}])
        self.assertEqual(body[1]['else'], [{'op': 'marker'}])


if __name__ == '__main__':
    unittest.main()
