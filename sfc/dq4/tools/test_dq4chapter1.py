import unittest

import dq4chapter1 as ch
import dq4menumsg as mm


class MessageTests(unittest.TestCase):
    def test_every_glyph_is_in_the_message_font(self):
        known = set(mm.CHARS) | {' '}
        for m, parts in ch.TEXTS.items():
            for p in parts:
                if isinstance(p, str):
                    self.assertLessEqual(set(p), known, f'{m:03X}')

    def test_lines_and_pages_fit_the_window(self):
        # 줄 너비는 _wrap 이 막는다. 여기서는 쪽마다 4줄을 넘지 않는지 본다.
        for m, parts in ch.TEXTS.items():
            lines = 1
            for p in parts:
                if p == ch.LINE:
                    lines += 1
                elif p in (ch.PAGE, ch.END):
                    self.assertLessEqual(lines, ch.PAGE_LINES, f'{m:03X}')
                    lines = 1

    def test_messages_do_not_touch_menu_messages(self):
        self.assertFalse(set(ch.TEXTS) & set(mm.TEXTS))
        self.assertTrue(all(0 <= m < mm.MESSAGES for m in ch.TEXTS))

    def test_talk_numbers_show_their_message(self):
        # 대화 번호 26D 이상은 메시지 T + 3C6
        for t in range(ch.TALK_BASE, ch.TALK_BASE + len(ch._talks)):
            self.assertGreaterEqual(t, 0x26D)
            self.assertIn(t + 0x3C6, ch.TEXTS)

    def test_name_is_spliced_as_a_code(self):
        self.assertEqual(ch._codes('@ 공.'), [ch.HERO, ' 공.'])
        self.assertEqual(ch._codes('하자고, @.'), ['하자고, ', ch.HERO, '.'])
        self.assertEqual(ch._codes('걸까요……'), ['걸까요', ch.DOTS, ch.DOTS])

    def test_too_long_line_is_refused(self):
        with self.assertRaises(ValueError):
            ch.say('가' * (ch.LINE_COLS + 1))


class LayoutTests(unittest.TestCase):
    def test_scripts_fit_a_length_byte(self):
        doc = ch.npc_doc({'overrides': []})
        for s in doc['scripts']:
            size = sum(1 + len(c['args']) for c in s['commands'])
            self.assertLess(size, 256, s['address'])

    def test_lineup_walks_out_in_two_lanes(self):
        self.assertEqual(ch.EXIT_LEFT[-1], (0x0F, 0x23))
        self.assertEqual(ch.EXIT_RIGHT[-1], (0x10, 0x23))

    def test_guards_stand_off_the_exit_lanes(self):
        # 인물끼리는 가로 2칸(FC 1블록) 안으로 다가가지 못해, 문지기 줄을 지나는 줄과 한 블록 떨어져야 한다
        guards = [x for x, y, g, _, _ in ch.STAFF if g == ch.GUARD and y == 0x1F and 0x0D <= x <= 0x12]
        lanes = {ch.EXIT_LEFT[-1][0], ch.EXIT_RIGHT[-1][0]}
        self.assertEqual(len(guards), 2)
        for gx in guards:
            self.assertTrue(all(gx != x for x in lanes))

    def test_override_comes_first(self):
        doc = ch.npc_doc({'overrides': [{'map': '01/00', 'flag': 0, 'when': 'on', 'mask': 128, 'list': '10:8674'}]})
        self.assertEqual(doc['overrides'][0]['map'], ch.THRONE)
        self.assertEqual(doc['overrides'][0]['list'], 'new:after')


if __name__ == '__main__':
    unittest.main()
