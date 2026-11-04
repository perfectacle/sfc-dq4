"""dq4kind14check: 기록 읽기, 변수 자리와 창 글자 코드 정의의 일치, 지금 변수가 종류 14 사본 밖인지(롬 없이)."""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dq4kind14check as k  # noqa: E402

ASM = Path(__file__).resolve().parent / 'dq4windowname.asm'
DQ5 = Path(__file__).resolve().parents[3] / 'rom' / 'dq5.sfc'
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

    def test_copy_range_from_tables(self):
        rom = bytearray(0x200000)
        o = k.lorom(k.SLOT_TABLE) + k.KIND * 2
        rom[o:o + 2] = b'\x14\x3D'
        rom[k.lorom(k.COUNT_TABLE) + k.KIND * 2] = 11
        self.assertEqual(k.copy_range(bytes(rom)), (0x3D14, 0x3E73))
        rom[k.lorom(k.COUNT_TABLE) + k.KIND * 2] = 12
        self.assertNotEqual(k.copy_range(bytes(rom)), k.COPY)

    @unittest.skipUnless(DQ5.exists(), 'rom/dq5.sfc 없음')
    def test_copy_range_matches_dq5(self):
        # 사본 범위나 자리 표가 바뀌면 COPY·LAYOUT 의 판단을 다시 해야 한다
        self.assertEqual(k.copy_range(DQ5.read_bytes()), k.COPY)

    def test_parse(self):
        text = '\n'.join([
            '316 w03=352 wother=0 wport=0 pb= vars=3D62:FF,3D5C:FFFF',
            '317 unseen',
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
        self.assertEqual(rec['unseen'], [317])
        self.assertEqual(rec['frames'][0]['wport'], 0)

    def test_judge(self):
        ok = {'copies': [(316, b'')], 'unseen': [],
              'frames': [{'frame': 316, 'w03': 352, 'wother': 0, 'wport': 0, 'vars': {}}]}
        self.assertEqual(k.judge(ok), [])
        self.assertEqual(k.judge({'copies': [], 'unseen': [], 'frames': []}), ['뱅크 03 이 종류 14 사본을 쓰지 않음'])
        # 사본 앞의 포트 쓰기(맵을 불러오며 지우는 DMA)는 덮이므로 괜찮다
        early = {'copies': [(316, b'')], 'unseen': [300],
                 'frames': [{'frame': 313, 'w03': 0, 'wother': 0, 'wport': 352, 'vars': {}}]}
        self.assertEqual(k.judge(early), [])
        bad = {'copies': [(316, b'')], 'unseen': [500],
               'frames': [{'frame': 401, 'w03': 0, 'wother': 20, 'wport': 3, 'vars': {}}]}
        got = k.judge(bad)
        self.assertEqual(len(got), 3)
        self.assertIn('$2180', got[1])
        self.assertIn('500', got[2])

    def test_same_runs_ignores_one_tail_frame(self):
        a = '1 x\n2 y\n648 z\n'
        self.assertTrue(k.same_runs([a, '1 x\n2 y\n']))
        self.assertFalse(k.same_runs([a, '1 x\n2 q\n']))


if __name__ == '__main__':
    unittest.main()
