import unittest
from unittest import mock

import dq4menumsg
import dq4signs as signs
import dq4sysmsg
from dq5map import lorom

FC_SIGNS = [
    {'table': 0, 'x': 0x16, 'y': 0x0F, 'msg': [0x3D0, 0x3D4, 0x391]},
    {'table': 1, 'x': 0xA6, 'y': 0x2F, 'msg': [0x3D9]},
    {'table': 1, 'x': 0x6C, 'y': 0x62, 'msg': [0x3DA]},
    {'table': 1, 'x': 0x35, 'y': 0x3B, 'msg': [0x3DB]},
    {'table': 1, 'x': 0x9E, 'y': 0x16, 'msg': [0x3DC]},
    {'table': 1, 'x': 0x38, 'y': 0xCB, 'msg': [0x3FE]},
]


def rom():
    d = bytearray(0x100000)
    o = lorom(signs.TABLE)
    d[o:o + len(signs.TABLE_ORIG)] = signs.TABLE_ORIG
    d[lorom(signs.READ_BRANCH)] = signs.READ_BRANCH_ORIG[0]
    return bytes(d)


class SignTests(unittest.TestCase):
    def test_table_is_field_signs_at_lower_right_cell(self):
        with mock.patch('dq4block.signs', return_value=FC_SIGNS):
            body, slots = signs.table(b'')
        self.assertEqual(body[:6], (2 * 0xA6 + 1).to_bytes(2, 'little') + (2 * 0x2F + 1).to_bytes(2, 'little')
                         + (0x17F).to_bytes(2, 'little'))
        self.assertEqual(len(body), 5 * 6 + 2)
        self.assertEqual(body[-2:], b'\xff\xff')
        self.assertEqual(tuple(slots.values()), signs.ORDER)

    def test_apply_writes_table_and_always_reads(self):
        with mock.patch('dq4block.signs', return_value=FC_SIGNS):
            out = signs.apply(rom(), b'')
        self.assertEqual(out[lorom(signs.READ_BRANCH)], 0x80)
        o = lorom(signs.TABLE)
        self.assertEqual(out[o:o + 4], bytes.fromhex('4d015f00'))

    def test_apply_refuses_changed_rom(self):
        with mock.patch('dq4block.signs', return_value=FC_SIGNS), self.assertRaises(SystemExit):
            signs.apply(bytes(0x100000), b'')

    def test_texts_fit_and_do_not_clash(self):
        texts = signs.texts()
        self.assertEqual(set(texts), set(signs.SLOTS))
        self.assertFalse(set(texts) & set(dq4sysmsg.TEXTS))
        known = set(dq4menumsg.CHARS) | {' '}
        for parts in texts.values():
            for p in parts:
                if isinstance(p, str):
                    self.assertLessEqual(set(p), known, p)


if __name__ == '__main__':
    unittest.main()
