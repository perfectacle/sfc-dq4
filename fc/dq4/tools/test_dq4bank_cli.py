"""BRK 뱅크 풀이의 기록 비교·덮개 집계·표시 서식·명령줄을 합성 롬과 임시 파일로 검사한다."""
import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import dq4bank as bank
from test_dq4bank import PRG_SIZE, put_brk, put_entry


def ines(prg):
    return b'NES\x1a' + bytes((len(prg) // 0x4000, 0, 0x10, 0)) + bytes(8) + bytes(prg)


def run_main(*argv):
    out = io.StringIO()
    with mock.patch('sys.argv', ['dq4bank.py', *argv]), contextlib.redirect_stdout(out):
        try:
            bank.main()
            code = 0
        except SystemExit as e:
            code = e.code
    return code, out.getvalue().splitlines()


class FmtTests(unittest.TestCase):
    def test_message_sound_flag_and_x3_forms(self):
        base = {'site': 0x8000, 'b1': 0x34, 'b2': 0xBB}
        self.assertEqual(bank.fmt(base | {'kind': 'message', 'msg': 0xB34, 'bank': 0x16, 'func': 4, 'target': 0x9000}),
                         '8000: 00 34 BB message msg=0B34 bank=16 func=04 -> 16:9000')
        self.assertEqual(bank.fmt({'site': 0x8000, 'b1': 0x22, 'b2': 0xFB, 'kind': 'sound', 'sound': 0x22,
                                   'bank': 0x19, 'func': 3, 'target': 0x8100}),
                         '8000: 00 22 FB sound sound=22 bank=19 func=03 -> 19:8100')
        self.assertEqual(bank.fmt({'site': 0x8000, 'b1': 0x10, 'b2': 0xCB, 'kind': 'flag-set', 'flag': 0x628B,
                                   'mask': 0x40}),
                         '8000: 00 10 CB flag-set $628B mask=40')
        x3 = {'site': 0x8000, 'b1': 0, 'b2': 0xF3, 'kind': 'x3', 'bank': 0x10, 'func': 1, 'target': 0x8002}
        self.assertTrue(bank.fmt(x3 | {'length': None}).endswith(' len=?'))
        self.assertTrue(bank.fmt(x3 | {'length': 4}).endswith(' len=4'))


class CoverTests(unittest.TestCase):
    def test_offsets_are_merged_across_files_and_counted_per_bank(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = os.path.join(d, 'a.txt'), os.path.join(d, 'b.txt')
            Path(a).write_text('0000 x\n4001 x\n4002 x\n')
            Path(b).write_text('4001 y\n7C000 z\n')
            counts = bank.cover_counts([a, b])
        self.assertEqual(len(counts), 32)
        self.assertEqual((counts[0], counts[1], counts[0x1F]), (1, 2, 1))
        self.assertEqual(sum(counts), 4)


class CompareTests(unittest.TestCase):
    def setUp(self):
        self.prg = bytearray(PRG_SIZE)
        put_entry(self.prg, 0x15, 0x07, 0x8123)
        put_brk(self.prg, 0x02, 0x9000, 0x07, 0x5A)

    def trace(self, d, got_bank):
        p = os.path.join(d, 't.txt')
        rec = (f'1 C446 x 0023={got_bank:02X} 0024=07 0025=00 0026=01 0027=90 0507=02\n'
               '2 C3CD x 0023=00 0024=23 0025=81 0026=00 0027=00 0507=02\n')
        Path(p).write_text('헤더\n---\n' + rec)
        return p

    def test_matching_record_counts_ok(self):
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(out):
            self.assertTrue(bank.compare(self.prg, self.trace(d, 0x15)))
        lines = out.getvalue().splitlines()
        self.assertEqual(lines[0], '1 호출 중 0 다름, 호출 위치 1 곳')
        self.assertIn('9000: 00 07 5A call bank=15 func=07 -> 15:8123', lines[1])

    def test_mismatch_is_reported(self):
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(out):
            self.assertFalse(bank.compare(self.prg, self.trace(d, 0x14)))
        lines = out.getvalue().splitlines()
        self.assertTrue(lines[0].startswith('다름:'))
        self.assertIn('기록 bank=14 func=07', lines[0])
        self.assertEqual(lines[1], '1 호출 중 1 다름, 호출 위치 1 곳')


class MainTests(unittest.TestCase):
    def setUp(self):
        prg = bytearray(b'\xEA' * PRG_SIZE)
        put_entry(prg, 0x15, 0x07, 0x8123)
        put_brk(prg, 0x02, 0x9000, 0x07, 0x5A)
        o = 0x03 * 0x4000
        prg[o:o + 0x20] = b'\xFF' * 0x20
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.rom = os.path.join(self.tmp.name, 'r.nes')
        Path(self.rom).write_bytes(ines(prg))
        self.prg = prg

    def test_call_with_and_without_bank(self):
        code, out = run_main(self.rom, 'call', '9000', '--bank', '02')
        self.assertEqual(out, ['9000: 00 07 5A call bank=15 func=07 -> 15:8123'])

    def test_table_default_and_limited(self):
        _, out = run_main(self.rom, 'table', '15')
        self.assertEqual(len(out), 16)
        self.assertEqual(out[7], '15[07] = 8123')
        _, out = run_main(self.rom, 'table', '15', '2')
        self.assertEqual(out, ['15[00] = EAEA', '15[01] = EAEA'])

    def test_free_lists_runs_and_total(self):
        _, out = run_main(self.rom, 'free', '16')
        self.assertTrue(any(ln.startswith('03 ') and '8000+32(FF)' in ln for ln in out))
        self.assertTrue(out[-1].startswith('# 16바이트 이상 연속 구간 합 '))
        _, out = run_main(self.rom, 'free')
        self.assertEqual(len(out), 33)

    def test_cover_prints_per_bank_counts(self):
        p = os.path.join(self.tmp.name, 'c.txt')
        Path(p).write_text('4000 a\n4001 a\n')
        _, out = run_main(self.rom, 'cover', p)
        self.assertEqual(out[0], '00 0')
        self.assertEqual(out[1], '01 2')

    def test_compare_exit_code(self):
        p = os.path.join(self.tmp.name, 't.txt')
        Path(p).write_text('---\n1 C446 x 0023=15 0024=07 0025=00 0026=01 0027=90 0507=02\n'
                           '2 C3CD x 0023=00 0024=23 0025=81 0026=00 0027=00 0507=02\n')
        code, _ = run_main(self.rom, 'compare', p)
        self.assertEqual(code, 0)
        Path(p).write_text('---\n1 C446 x 0023=15 0024=06 0025=00 0026=01 0027=90 0507=02\n')
        code, _ = run_main(self.rom, 'compare', p)
        self.assertEqual(code, 1)


if __name__ == '__main__':
    unittest.main()
