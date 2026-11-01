import unittest
from unittest import mock

import dq4brkscan as scan
import dq4prologue


class BrkScanTest(unittest.TestCase):
    def test_high_bank_event_code_calls_only_allowed_brk(self):
        for name, base, blob, entries in scan.blobs():
            with self.subTest(name):
                self.assertTrue(entries)
                _, problems = scan.scan(base, blob, entries)
                self.assertEqual(problems, [])

    def test_old_spar_effect_brk16_is_caught(self):
        # #904 이전처럼 칼 효과음을 BRK 16 으로 부르면 잡혀야 한다(snes9x 에서 서장이 멈춘 원인)
        with mock.patch.object(dq4prologue, '_effect', lambda se, branch: bytes((0x00, 0x16, se, branch))):
            base_blob = [(n, b, blob, e) for n, b, blob, e in scan.blobs() if n == 'prologue'][0]
        _, problems = scan.scan(*base_blob[1:])
        self.assertTrue(any('BRK 16 금지' in p for p in problems), problems)

    def test_unknown_brk_needs_review(self):
        code = bytes((0x08, 0x00, 0x77, 0x28, 0x6B))      # PHP / BRK 77 / PLP / RTL
        _, problems = scan.scan(0x5E0000, code, [0x5E0000])
        self.assertTrue(any('BRK 77' in p and '확인되지 않은' in p for p in problems), problems)

    def test_lists_do_not_overlap(self):
        self.assertFalse(set(scan.ALLOWED) & set(scan.FORBIDDEN))


if __name__ == '__main__':
    unittest.main()
