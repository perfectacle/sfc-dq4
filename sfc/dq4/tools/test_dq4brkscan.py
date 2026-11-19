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

    def test_chapter3_code_writes_reserved_cells_by_long_address(self):
        # BRK 받침을 JSL 로 부르면 DB 가 받침 뱅크로 바뀐 채 돌아온다. 3장 모듈이 7E:2000 이상 예약 칸을 절대 주소로 쓰면
        # WRAM 에 닿지 않는다(#1216 의 네네 보기 표지 7E:2824). 모든 3장 덩어리에서 그런 쓰기가 0 이어야 한다
        cells = scan.reserved_cells()
        self.assertIn(0x2824, cells)
        self.assertIn(0x2190 + 0x79, cells)
        blobs = [b for b in scan.blobs() if b[0].startswith('ch3')]
        self.assertTrue(blobs)
        for name, base, blob, entries in blobs:
            with self.subTest(name):
                _, problems, _ = scan.scan(base, blob, entries, (), cells)
                self.assertEqual([p for p in problems if '절대 주소' in p], [])

    def test_abs_write_after_stub_call_is_caught(self):
        cells = {0x2824}
        enter = bytes((0x08, 0xF4, 0x7E, 0x7E, 0xAB, 0xAB))               # PHP / PEA $7E7E / PLB / PLB
        stub = bytes((0x22, 0x80, 0xFF, 0x29))                            # JSL 29:FF80(BRK 받침)
        sta_abs, sta_long = bytes((0x8D, 0x24, 0x28)), bytes((0x8F, 0x24, 0x28, 0x7E))
        tail = bytes((0x28, 0x6B))
        for body, bad in ((sta_abs, False), (stub + sta_abs, True), (stub + sta_long, False),
                          (stub + bytes((0xA9, 0x7E, 0x48, 0xAB)) + sta_abs, False),
                          (stub + bytes((0xA9, 0x00, 0x8E, 0x24, 0x28)), True)):
            with self.subTest(body.hex()):
                blob = enter + body + tail
                _, problems, _ = scan.scan(0x4E8000, blob, [0x4E8000], [(0x290000, 0x2A0000)], cells)
                self.assertEqual(any('절대 주소' in p for p in problems), bad, problems)

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
