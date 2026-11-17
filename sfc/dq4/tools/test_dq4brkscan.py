import unittest
from unittest import mock

import dq4brkscan as scan
import dq4prologue


class BrkScanTest(unittest.TestCase):
    def test_high_bank_event_code_calls_only_allowed_brk(self):
        blobs = scan.blobs()
        spans = [(b, b + len(blob)) for _, b, blob, _ in blobs]
        for name, base, blob, entries in blobs:
            with self.subTest(name):
                self.assertTrue(entries)
                _, problems, _ = scan.scan(base, blob, entries, spans)
                self.assertEqual(problems, [])

    def test_unknown_non_php_label_is_reported(self):
        _, problems = scan.entries_of('t', 0x5E0000, bytes((0xA9, 0x00, 0x6B)), {'mystery': 0x5E0000})
        self.assertTrue(problems)

    def test_leaving_into_unscanned_high_bank_is_reported(self):
        code = bytes((0x08, 0x22, 0x00, 0x90, 0x5E, 0x28, 0x6B))     # PHP / JSL 5E:9000 / PLP / RTL
        _, problems, exits = scan.scan(0x5E0000, code, [0x5E0000])
        self.assertIn(0x5E9000, exits)
        self.assertTrue(any('훑지 않은' in p for p in problems))
        low = bytes((0x08, 0x22, 0x9A, 0xFE, 0x24, 0x28, 0x6B))      # JSL 24:FE9A 는 낮은 뱅크라 괜찮음
        self.assertEqual(scan.scan(0x5E0000, low, [0x5E0000])[1], [])

    def test_chapter3_monster_hooks_are_scanned_with_their_widths(self):
        # 뱅크 4E 의 3장 조우·전투 뒤 물건·떠돌이 상인 훅. X 16비트로 들어오는 밤 갈래(LDX #$0000)를 8비트로 읽으면
        # 어긋나므로 진입점마다 폭을 준다. 전투 뒤 물건 갈래에 창 열기 BRK 95 를 넣으면 잡힌다
        name, base, blob, entries = next(b for b in scan.blobs() if b[0] == 'ch3monsters')
        self.assertEqual(scan.scan(base, blob, entries)[1], [])
        drop = next(e[0] for e in entries if (e[1], e[2]) == (True, True) and blob[e[0] - base] != 0x08)
        bad = bytearray(blob)
        bad[drop - base:drop - base + 2] = bytes((0x00, 0x95))
        self.assertTrue(any('BRK 95 금지' in p for p in scan.scan(base, bytes(bad), entries)[1]))

    def test_brk_at_blob_end(self):
        self.assertTrue(scan.scan(0x5E0000, bytes((0x08, 0x00)), [0x5E0000])[1])

    def test_old_spar_effect_brk16_is_caught(self):
        # #904 이전처럼 칼 효과음을 BRK 16 으로 부르면 잡혀야 한다(snes9x 에서 서장이 멈춘 원인)
        with mock.patch.object(dq4prologue, '_effect', lambda se, branch: bytes((0x00, 0x16, se, branch))):
            base_blob = [(n, b, blob, e) for n, b, blob, e in scan.blobs() if n == 'prologue'][0]
        _, problems, _ = scan.scan(*base_blob[1:])
        self.assertTrue(any('BRK 16 금지' in p for p in problems), problems)

    def test_unknown_brk_needs_review(self):
        code = bytes((0x08, 0x00, 0x77, 0x28, 0x6B))      # PHP / BRK 77 / PLP / RTL
        _, problems, _ = scan.scan(0x5E0000, code, [0x5E0000])
        self.assertTrue(any('BRK 77' in p and '확인되지 않은' in p for p in problems), problems)

    def test_lists_do_not_overlap(self):
        self.assertFalse(set(scan.ALLOWED) & set(scan.FORBIDDEN))


if __name__ == '__main__':
    unittest.main()
