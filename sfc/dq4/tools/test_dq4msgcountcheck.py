import tempfile
import unittest
from pathlib import Path

import dq4msgcountcheck as C

LOG = 'f1 msg 101\nf2 wait\nf3 close 00\nf4 msg 102\nf5 close 01\n'


class VerdictTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.prologue = self.dir / 'p.txt'
        self.king = self.dir / 'k.txt'
        self.prologue.write_text(LOG)
        self.king.write_text(LOG)
        self.pages = {0x101: 2, 0x102: 1}

    def test_full_records_within_pages_pass(self):
        r = C.verdict(0, self.prologue, self.king, self.pages)
        self.assertEqual(r['status'], 'passed')
        self.assertEqual(r['scenes']['king'], {'messages': 2, 'over': []})

    def test_failed_king_walk_fails_even_with_a_partial_record(self):
        r = C.verdict(1, self.prologue, self.king, self.pages)
        self.assertEqual(r['status'], 'failed')
        self.assertEqual(r['walk'], '왕 구간 걷기 종료 1')

    def test_missing_or_empty_record_fails(self):
        self.assertEqual(C.verdict(0, self.prologue, None, self.pages)['scenes']['king'], '기록 없음')
        self.king.write_text('')
        self.assertEqual(C.verdict(0, self.prologue, self.king, self.pages)['status'], 'failed')

    def test_more_presses_than_pages_fails(self):
        r = C.verdict(0, self.prologue, self.king, {0x101: 1, 0x102: 1})
        self.assertEqual(r['status'], 'failed')
        self.assertEqual(r['scenes']['prologue']['over'], ['101 A2 > 1쪽'])


if __name__ == '__main__':
    unittest.main()
