import re
import unittest
from pathlib import Path

ASM = Path(__file__).resolve().parent / 'dq4windowname.asm'
CANVAS = range(0x096, 0x180)     # 메시지 캔버스: 9줄 × 26칸
OFF_CANVAS = range(0x1D0, 0x200)
ROW = 26
HIDDEN = range(6, 19)            # 가게 팔기·맡기기 목록 창(화면 9~21열)이 덮는 캔버스 줄 안의 칸
HIDDEN_ROWS = 8                  # 캔버스 마지막 줄(화면 26줄)은 가게 사기의 장비 비교 창이 덮지 않음
COLS = {0: 4, 1: 7, 2: 10}
HIDDEN_SLOTS = {4: 3, 7: 3, 10: 1}   # 열 수마다 목록 창 밑에 가리는 앞쪽 캔버스 슬롯 수


def table(name):
    text = ASM.read_text()
    body = re.search(rf'^{name}:\n((?:    dw .*\n)+)', text, re.M).group(1)
    return [int(v.replace('$', '0x'), 16) for v in re.findall(r'\$?[0-9A-Fa-f]+', body.replace('dw', ''))]


def hidden(first, n):
    return all((t - CANVAS.start) % ROW in HIDDEN and (t - CANVAS.start) // ROW < HIDDEN_ROWS
               for t in range(first, first + n))


class FieldSlotTest(unittest.TestCase):
    def setUp(self):
        # 캔버스 밖 1D0~1FF 슬롯($20)은 위 줄이 글자 줄 바로 뒤(WtUpperF = 0)
        rows = [(lo, up, c) for lo, up, c in zip(table('WtSlotF'), table('WtUpperF'), table('WtClassF')) if c != 0xFF]
        self.slots = [(lo, up or lo + COLS[c & 0x0F], COLS[c & 0x0F]) for lo, up, c in rows]

    def test_runs_stay_in_place_and_do_not_overlap(self):
        used = []
        for (lo, up, n), c in zip(self.slots, [c for c in table('WtClassF') if c != 0xFF]):
            for first in (lo, up):
                area = OFF_CANVAS if c & 0x20 else CANVAS
                self.assertTrue(first in area and first + n - 1 in area, f'{first:03X}')
                used += range(first, first + n)
        self.assertEqual(len(used), len(set(used)))

    def test_same_slot_count_and_classes_as_battle(self):
        battle = [c & 0x0F for c in table('WtClass') if c != 0xFF]
        self.assertEqual(sorted(battle), sorted(c & 0x0F for c in table('WtClassF') if c != 0xFF))

    def test_off_canvas_slots_match_battle_table(self):
        battle = [(t, c & 0x2F) for t, c in zip(table('WtSlot'), table('WtClass')) if c != 0xFF and c & 0x20]
        field = [(t, c) for t, c in zip(table('WtSlotF'), table('WtClassF')) if c != 0xFF and c & 0x20]
        self.assertEqual(battle, field)
        # 메시지 창에 비치지 않는 캔버스 밖 슬롯을 먼저 고른다
        self.assertEqual(field, [(t, c) for t, c in zip(table('WtSlotF'), table('WtClassF')) if c != 0xFF][:len(field)])
        self.assertEqual([u for u, c in zip(table('WtUpperF'), table('WtClassF')) if c != 0xFF and c & 0x20],
                         [0] * len(field))

    def test_first_slots_of_each_size_are_hidden_under_the_list(self):
        for n, count in HIDDEN_SLOTS.items():
            for lo, up, _ in [s for s in self.slots if s[2] == n and s[0] in CANVAS][:count]:
                self.assertTrue(hidden(lo, n) and hidden(up, n), f'{lo:03X}/{up:03X}')

    def test_hidden_large_slots_come_before_visible_medium_ones(self):
        order = [(n, hidden(lo, n) and hidden(up, n)) for lo, up, n in self.slots if lo in CANVAS]
        medium_visible = order.index((7, False))
        self.assertLess(max(i for i, s in enumerate(order) if s == (10, True)), medium_visible)


if __name__ == '__main__':
    unittest.main()
