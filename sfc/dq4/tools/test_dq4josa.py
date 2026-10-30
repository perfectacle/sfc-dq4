import unittest

import dq4josa as josa
import dq4menumsg as mm
import dq4sysmsg as sysmsg


def target(code, at):
    d = code[at + 1]
    return at + 2 + (d - 256 if d > 127 else d)


class TableTests(unittest.TestCase):
    def setUp(self):
        self.first, self.run = josa.syllables()
        self.table = josa.jong_table(self.run)

    def jong(self, ch):
        return self.table[self.run.index(ch)]

    def test_run_matches_glyph_codes(self):
        self.assertEqual(self.first, josa.GLYPH0 + mm.CHARS.index('ㄱ'))
        self.assertEqual(self.first + self.run.index('가'), josa.GLYPH0 + mm.CHARS.index('가'))
        self.assertEqual(len(self.run), 51 + 2350)

    def test_final_consonants(self):
        self.assertEqual([self.jong(c) for c in '가각갈'], [0, 1, 2])
        self.assertEqual([self.jong(c) for c in 'ㅂㄹㅏ'], [1, 2, 0])


class CodeTests(unittest.TestCase):
    def test_handler_branches_land_on_lists(self):
        lay = josa.Layout()
        for code, (has, none, _) in josa.JOSA.items():
            h = josa.handler(code, lay.table_at, lay.first, lay.count)
            with_, without = josa.queue_write(has), josa.queue_write(none)
            w_at, n_at = h.index(with_), h.index(without)
            bcs = h.index(bytes((0xB0,)), 14)
            self.assertEqual(target(h, bcs), n_at, f'{code:04X} BCS')
            self.assertEqual(target(h, w_at - 2), n_at, f'{code:04X} 받침 판정')
            self.assertEqual(target(h, w_at + len(with_)), n_at + len(without), f'{code:04X} BRA')

    def test_dispatch_keeps_original_range(self):
        lay = josa.Layout()
        d = lay.dispatch(lay.handler_at)
        self.assertEqual(d[:8], bytes.fromhex('29 ff 00 c9 1e 00 b0 04'))
        self.assertEqual(d[8:12], bytes((0x5C, *josa.le(josa.DISPATCH_BACK, 3))))
        self.assertEqual(d[-4:], bytes((0x5C, *josa.le(josa.DISPATCH_BAD, 3))))

    def test_codes_follow_the_table(self):
        self.assertEqual(min(josa.JOSA), 0x1000 + josa.TABLE_COUNT)


class MessageTests(unittest.TestCase):
    def test_glyphs_exist(self):
        known = set(mm.CHARS) | {' '}
        for m, parts in sysmsg.TEXTS.items():
            for p in parts:
                if isinstance(p, str):
                    self.assertLessEqual(set(p), known, f'{m:03X}')

    def test_no_clash_with_menu_messages(self):
        self.assertFalse(set(sysmsg.TEXTS) & set(mm.TEXTS))

    def test_josa_tokens_become_codes(self):
        self.assertEqual(sysmsg.parts('{L}{은} 발밑')[0], [0x1011, 0x101E, ' 발밑'])
        self.assertEqual(sysmsg.parts('{I}{로}')[0], [0x100A, 0x1021])

    def test_too_long_line_is_refused(self):
        with self.assertRaises(ValueError):
            sysmsg.message('{P}{은} {I}{을}')


if __name__ == '__main__':
    unittest.main()
