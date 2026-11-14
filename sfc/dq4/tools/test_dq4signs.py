import unittest
from pathlib import Path
from unittest import mock

import dq4menumsg
import dq4signs as signs
import dq4sysmsg
from dq5map import lorom

DQ4 = Path(__file__).resolve().parents[3] / 'rom' / 'dq4.nes'
# 옮긴 맵의 실내 팻말(map_signs 꼴)
MAP_SIGNS = [(0x3E, 0x00, 0x0E, 0x0F, 0x3D7), (0x40, 0x00, 0x16, 0x0F, 0x3D0), (0x42, 0x00, 0x13, 0x05, 0x3D8),
             (0x45, 0x00, 0x08, 0x01, 0x3D6), (0x45, 0x00, 0x0C, 0x12, 0x3D5), (0x45, 0x05, 0x05, 0x09, 0x3D3),
             (0x45, 0x05, 0x1E, 0x0A, 0x3D3)]

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
    o = lorom(signs.MAP_TABLE)
    d[o:o + len(signs.MAP_TABLE_ORIG)] = signs.MAP_TABLE_ORIG
    return bytes(d)


def patched():
    return mock.patch('dq4block.signs', return_value=FC_SIGNS), mock.patch.object(signs, 'map_signs', return_value=MAP_SIGNS)


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
        a, b = patched()
        with a, b:
            out = signs.apply(rom(), b'')
        self.assertEqual(out[lorom(signs.READ_BRANCH)], 0x80)
        o = lorom(signs.TABLE)
        self.assertEqual(out[o:o + 4], bytes.fromhex('4d015f00'))

    def test_apply_refuses_changed_rom(self):
        a, b = patched()
        with a, b, self.assertRaises(SystemExit):
            signs.apply(bytes(0x100000), b'')

    def test_map_table_puts_three_search_cells_per_sign(self):
        with mock.patch.object(signs, 'map_signs', return_value=MAP_SIGNS):
            body, slots = signs.map_table(b'')
        self.assertEqual(len(body), 6 * 3 * len(MAP_SIGNS) + 2)
        self.assertLessEqual(len(body), len(signs.MAP_TABLE_ORIG))
        self.assertEqual(body[-2:], b'\xff\xff')
        self.assertEqual(tuple(slots[s] for s in signs.MAP_SLOTS), signs.MAP_ORDER)
        # 사란 (0C,12): (24,36)·(25,36)·(25,37), 메시지는 3D5 의 자리
        slot = signs.MAP_SLOTS[signs.MAP_ORDER.index(0x3D5)].to_bytes(2, 'little')
        for cell in ((24, 36), (25, 36), (25, 37)):
            self.assertIn(bytes((0x45, 0x00, *cell)) + slot, body)
        a, b = patched()
        with a, b:
            out = signs.apply(rom(), b'')
        o = lorom(signs.MAP_TABLE)
        self.assertEqual(out[o:o + len(body)], body)

    def test_sign_blocks_get_the_indoor_sign_attribute(self):
        # 12:EB53 은 위층 속성(+7)만 본다(dq4environmentrom: 마지막 줄이 위층인 블록의 속성이 +7 로 감)
        import dq4environmentrom as er
        self.assertEqual(er.FURNITURE[signs.SIGN_PROP], (er.FRONT, er.UPPER, 0x97))

    @unittest.skipUnless(DQ4.exists(), 'rom/dq4.nes 없음')
    def test_map_signs_are_the_ported_fc_signs(self):
        from kr_patch.fc import ines
        prg = ines.prg(DQ4.read_bytes())
        self.assertEqual(signs.map_signs(prg), MAP_SIGNS)
        signs.map_table(prg)

    def test_texts_fit_and_do_not_clash(self):
        texts = signs.texts()
        self.assertEqual(set(texts), set(signs.SLOTS) | set(signs.MAP_SLOTS))
        self.assertFalse(set(texts) & set(dq4sysmsg.TEXTS))
        known = set(dq4menumsg.CHARS) | {' '}
        for parts in texts.values():
            for p in parts:
                if isinstance(p, str):
                    self.assertLessEqual(set(p), known, p)


if __name__ == '__main__':
    unittest.main()
