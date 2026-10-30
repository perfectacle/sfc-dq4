import json
import tempfile
import unittest
from pathlib import Path

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

    def test_narration_repeats_code_after_each_page(self):
        parts = ch.TEXTS[ch.MSG_NARRATION]
        self.assertEqual(parts[0], ch.NARR)
        for i, p in enumerate(parts):
            if p == ch.PAGE:
                self.assertEqual(parts[i + 1], ch.NARR)

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

    def test_king_calls_box_then_reveal(self):
        import dq4chapterbox
        doc = ch.npc_doc({'overrides': []})
        ops = [(c['op'], c['args']) for c in doc['scripts'][0]['commands']]
        calls = [a for op, a in ops if op == '37']
        want = dq4chapterbox.entry_points(ch.scenes(False))
        self.assertEqual(calls, [[v & 0xFF, v >> 8 & 0xFF, v >> 16] for v in (want['box'], want['reveal'])])
        self.assertLess(ops.index(('37', calls[0])), ops.index(('21', [ch.MSG_NARRATION & 0xFF, ch.MSG_NARRATION >> 8])))

    def test_override_comes_first(self):
        doc = ch.npc_doc({'overrides': [{'map': '01/00', 'flag': 0, 'when': 'on', 'mask': 128, 'list': '10:8674'}]})
        self.assertEqual(doc['overrides'][0]['map'], ch.THRONE)
        self.assertEqual(doc['overrides'][0]['list'], 'new:after')


ROOT = Path(__file__).resolve().parents[3]


@unittest.skipUnless((ROOT / 'rom' / 'dq5.sfc').is_file() and (ROOT / 'rom' / 'dq4.nes').is_file(),
                     'local source ROMs not present')
class GroupBuildTests(unittest.TestCase):
    def test_group_build_at_integrated_places_does_not_overlap(self):
        # dq5build inside dq4groupbuild.build refuses overlapping writes (new-map records, field map, prologue room).
        import dq4groupbuild
        saved = dq4groupbuild.NEWMAP_AT, dq4groupbuild.FIELD_AT
        try:
            with tempfile.TemporaryDirectory() as out:
                summary = ch.group_build(ROOT / 'rom' / 'dq5.sfc', ROOT / 'rom' / 'dq4.nes', Path(out))
                writes = json.loads((Path(out) / 'field.dq5patch.json').read_text(encoding='utf-8'))['writes']
        finally:
            dq4groupbuild.NEWMAP_AT, dq4groupbuild.FIELD_AT = saved
        self.assertTrue(summary['rom'])
        talk = int(dq4groupbuild.TALK_AT[1].replace(':', ''), 16)
        import dq4fieldport
        planes = int(dq4fieldport.GFX_AT['planes'][:2], 16)
        for w in writes:
            at = int(w['at'].replace(':', ''), 16)
            if at >> 16 >= 0x40:
                # The block number planes, outside the 30-3F the field loader's DB needs: the hook bank and one
                # bank per world.
                self.assertIn(at >> 16, range(planes, planes + 1 + len(dq4fieldport.WORLDS)))
            elif at >> 16 >= 0x30:
                self.assertEqual(at >> 16, 0x34)
                self.assertLessEqual(at + len(bytes.fromhex(w['hex'])), 0x350000)
                self.assertNotEqual(at >> 16, talk >> 16)



class Chapter1TalkTests(unittest.TestCase):
    def test_talk_texts_fit_and_use_known_glyphs(self):
        import dq4ch1talk
        known = set(mm.CHARS) | {' '}
        for key, parts in dq4ch1talk.TEXTS.items():
            lines = 1
            for p in parts:
                if isinstance(p, str):
                    self.assertLessEqual(set(p), known, key)
                elif p == ch.LINE:
                    lines += 1
                elif p in (ch.PAGE, ch.END):
                    self.assertLessEqual(lines, ch.PAGE_LINES, key)
                    lines = 1
            self.assertEqual(parts[-1], ch.END)
            self.assertEqual(parts.count(ch.END), 1, key)

    def test_talk_keys_do_not_overlap_the_front(self):
        import dq4ch1talk
        self.assertFalse(set(dq4ch1talk.TEXTS) & set(ch.FRONT_TEXTS))


if __name__ == '__main__':
    unittest.main()
