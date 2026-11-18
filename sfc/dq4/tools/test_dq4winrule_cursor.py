"""dq4winrule_cursor 단위 테스트: 칸 그림을 직접 넣은 가짜 화면."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dq4winrule_cursor as rule  # noqa: E402

BG, INK = 1, 3
TRIANGLE = [0x00, 0x20, 0x30, 0x38, 0x30, 0x20, 0x00, 0x00]
# 글자는 앞 1점을 비우고 그린다. 왼쪽 첫 열에 잉크가 든 칸은 ▶ 가 앞 글자를 덮은 꼴
LETTER = [0x00, 0x3C, 0x24, 0x3C, 0x24, 0x3C, 0x00, 0x00]
CUT = [0x00, 0xBC, 0xA4, 0xBC, 0xA4, 0xBC, 0x00, 0x00]


def fake_rom():
    rom = bytearray(rule.lorom(rule.ROM_FONT) + 0x400)
    o = rule.lorom(rule.ROM_FONT) + (rule.CURSOR - 1) * 8
    rom[o:o + 8] = bytes(TRIANGLE)
    return bytes(rom)


def pixels(rows):
    return [[INK if (b >> (7 - x)) & 1 else BG for x in range(8)] for b in rows]


class Screen:
    def __init__(self, rects, tops=None):
        self.rects = rects
        self.tops = tops or {}
        self.ref = SimpleNamespace(rom=fake_rom())
        self.cells = {}
        for r1, c1, r2, c2 in rects:
            for r in range(r1, r2 + 1):
                for c in range(c1, c2 + 1):
                    self.cells[(r, c)] = (0x001, pixels([0] * 8))

    def put(self, r, c, tile, rows):
        self.cells[(r, c)] = (tile, pixels(rows))

    def word(self, r, c):
        return self.cells.get((r, c), (0, None))[0]

    def shown(self, r, c):
        return self.cells.get((r, c), (0, None))[1]

    def visible(self, r):
        return True


WINDOW = (2, 2, 8, 12)


def listing():
    s = Screen([WINDOW])
    s.put(4, 3, rule.CURSOR, TRIANGLE)
    for c in range(4, 8):
        s.put(4, c, 0x190 + c, LETTER)
    return s


class CursorRuleTest(unittest.TestCase):
    def test_cursor_before_text_passes(self):
        self.assertEqual(rule.check(listing()), [])

    def test_cursor_covering_first_letter(self):
        s = listing()
        s.put(4, 4, 0x194, CUT)
        self.assertIn('덮음', rule.check(s)[0][2])

    def test_rom_glyph_inked_from_first_column_passes(self):
        s = listing()
        s.put(4, 4, 0x1E, CUT)
        self.assertEqual(rule.check(s), [])

    def test_cursor_on_empty_line(self):
        s = listing()
        s.put(6, 3, rule.CURSOR, TRIANGLE)
        s.put(4, 3, 0x001, [0] * 8)
        self.assertEqual([(6, 3)], [(r, c) for r, c, _ in rule.check(s)])

    def test_cursor_on_border(self):
        s = listing()
        s.put(4, 2, rule.CURSOR, TRIANGLE)
        s.put(4, 3, 0x001, [0] * 8)
        self.assertIn('테두리', rule.check(s)[0][2])

    def test_two_cursors_in_one_window(self):
        s = listing()
        s.put(6, 3, rule.CURSOR, TRIANGLE)
        s.put(6, 4, 0x1A0, LETTER)
        self.assertIn('2개', rule.check(s)[0][2])

    def test_line_covered_by_upper_window_is_not_judged(self):
        upper = (3, 5, 7, 12)
        s = Screen([WINDOW, upper], {WINDOW: [upper]})
        s.put(4, 3, rule.CURSOR, TRIANGLE)
        self.assertEqual(rule.check(s), [])

    def test_same_window_drawn_twice_does_not_hide_itself(self):
        s = listing()
        s.rects = [WINDOW, WINDOW]
        s.tops = {WINDOW: [WINDOW]}
        self.assertEqual(rule.check(s), [])

    def test_tile_7c_with_other_picture_is_not_a_cursor(self):
        s = listing()
        s.put(6, 3, rule.CURSOR, LETTER)
        self.assertEqual(rule.check(s), [])


if __name__ == '__main__':
    unittest.main()
