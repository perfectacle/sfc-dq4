"""커서 규칙이 장비 비교 창의 능력치 화살표(숫자 사이의 07C)를 ▶ 로 세지 않는지."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dq4winrule_cursor as rule  # noqa: E402
from test_dq4winrule_cursor import LETTER, TRIANGLE, Screen, fake_rom  # noqa: E402

FIVE = [0x00, 0x7C, 0x40, 0x78, 0x04, 0x78, 0x00, 0x00]
ONE = [0x00, 0x10, 0x30, 0x10, 0x10, 0x38, 0x00, 0x00]
ZERO = [0x00, 0x38, 0x44, 0x44, 0x44, 0x38, 0x00, 0x00]
GLYPHS = {0x07: FIVE, 0x03: ONE, 0x02: ZERO}
WINDOW = (15, 2, 25, 29)


def digit_rom():
    rom = bytearray(fake_rom())
    for t, rows in GLYPHS.items():
        o = rule.lorom(rule.ROM_FONT) + (t - 1) * 8
        rom[o:o + 8] = bytes(rows)
    return bytes(rom)


def compare(s, r, c):
    """「5▶ 10」: 숫자, 07C, 빈칸, 숫자 둘."""
    s.put(r, c, 0x07, FIVE)
    s.put(r, c + 1, rule.CURSOR, TRIANGLE)
    s.put(r, c + 3, 0x03, ONE)
    s.put(r, c + 4, 0x02, ZERO)


class StatArrowTest(unittest.TestCase):
    def screen(self):
        s = Screen([WINDOW])
        s.ref.rom = digit_rom()
        return s

    def test_two_stat_arrows_in_one_window_are_not_cursors(self):
        s = self.screen()
        compare(s, 18, 6)
        compare(s, 18, 18)
        self.assertEqual(rule.check(s), [])

    def test_two_real_cursors_still_fail(self):
        s = self.screen()
        for r in (17, 19):
            s.put(r, 3, rule.CURSOR, TRIANGLE)
            s.put(r, 4, 0x194, LETTER)
        self.assertIn('2개', rule.check(s)[0][2])

    def test_arrow_after_a_letter_is_still_a_cursor(self):
        s = self.screen()
        compare(s, 18, 6)
        s.put(18, 6, 0x194, LETTER)
        s.put(19, 3, rule.CURSOR, TRIANGLE)
        s.put(19, 4, 0x194, LETTER)
        self.assertIn('2개', rule.check(s)[0][2])


if __name__ == '__main__':
    unittest.main()
