"""dq4kind14check: 기록 읽기, 변수 자리와 창 글자 코드 정의의 일치, 지금 변수가 종류 14 사본 밖인지(롬 없이)."""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dq4kind14check as k  # noqa: E402

ASM = Path(__file__).resolve().parent / 'dq4windowname.asm'
ASM_NAME = {'defer': 'wq_defer', 'rd': 'wq_rd', 'count': 'wq_count', 'off': 'wq_off', 'left': 'wq_left',
            'head': 'wq_head', 'len': 'wq_len', 'stale': 'wt_stale', 'stale2': 'wt_stale2'}


class Kind14Check(unittest.TestCase):
    def test_new_layout_matches_asm(self):
        text = ASM.read_text()
        for name, sym in ASM_NAME.items():
            got = re.search(rf'^!{sym}\s*=\s*\$([0-9A-F]+)', text, re.M)
            self.assertIsNotNone(got, sym)
            self.assertEqual(int(got.group(1), 16), k.LAYOUT['new'][name][0], sym)

    def test_new_layout_is_outside_copy(self):
        copy = bytes(range(256)) + bytes(96)
        self.assertEqual(k.at_copy('new', copy), {})
        for a, n in k.LAYOUT['new'].values():
            self.assertFalse(k.COPY[0] <= a + n - 1 and a <= k.COPY[1])

    def test_old_layout_reads_copy_offsets(self):
        copy = bytearray(352)
        copy[0x3D62 - 0x3D14] = 0xFF
        copy[0x3D5C - 0x3D14:0x3D5E - 0x3D14] = b'\x34\x12'
        got = k.at_copy('old', bytes(copy))
        self.assertEqual(got['count'], 0xFF)
        self.assertEqual(got['rd'], 0x1234)
        self.assertEqual(set(got), set(k.NAMES))

    def test_parse(self):
        text = '\n'.join([
            '316 w03=352 wother=0 vars=3D62:FF,3D5C:FFFF',
            '316 copy ' + 'AB' * 352,
            '403 vmadd 002C@D843,002C@D8B7',
            '403 entry 002C:00B7:002C',
            '480 tmdiff 1155 0168',
        ])
        rec = k.parse(text)
        self.assertEqual(rec['frames'][0]['vars'], {'3D62': 0xFF, '3D5C': 0xFFFF})
        self.assertEqual(k.named('old', rec['frames'][0]['vars'])['count'], 0xFF)
        self.assertEqual(rec['copies'][0][1], b'\xAB' * 352)
        self.assertEqual(rec['vmadd'], [(403, [(0x2C, 0xD843), (0x2C, 0xD8B7)])])
        self.assertEqual(rec['entries'], [(403, [(0x2C, 0xB7, 0x2C)])])
        self.assertEqual(rec['tmdiff'], [(480, 1155, 0x168)])

    def test_judge(self):
        ok = {'copies': [(316, b'')], 'frames': [{'frame': 316, 'w03': 352, 'wother': 0, 'vars': {}}]}
        self.assertEqual(k.judge(ok), [])
        bad = {'copies': [], 'frames': [{'frame': 401, 'w03': 0, 'wother': 20, 'vars': {}}]}
        self.assertEqual(len(k.judge(bad)), 2)


if __name__ == '__main__':
    unittest.main()
