import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dq4queuerace as q  # noqa: E402

A = (0x1000, 0x01, 0x18, b'\x11' * 16)
B = (0x1010, 0x00, 0x18, b'\x22' * 8)
B_FF = (0x1010, 0x08, 0x19, b'\xff' * 8)
NEW = (0x1200, 0x01, 0x18, b'\x33' * 16)
STASH = (0, 0, b'')


class JudgeTests(unittest.TestCase):
    def test_clean_runs_pass(self):
        ref = ([A, NEW], STASH, 0)
        self.assertEqual(q.judge([A], ref, [(0, ([NEW, A], STASH, 0)), (5, ([A, NEW], STASH, 0))], False), [])

    def test_lost_entry_at_one_boundary_fails(self):
        ref = ([A, NEW], STASH, 0)
        problems = q.judge([A], ref, [(0, ([A, NEW], STASH, 0)), (7, ([NEW], STASH, 0))], False)
        self.assertEqual(len(problems), 1)
        self.assertIn('경계 7', problems[0])
        self.assertIn('버려짐', problems[0])

    def test_entry_sent_twice_fails(self):
        ref = ([A, NEW], STASH, 0)
        problems = q.judge([A], ref, [(3, ([A, NEW, NEW], STASH, 0))], False)
        self.assertTrue(any('경계 3' in p and '더 나감 1' in p for p in problems))

    def test_half_written_entry_fails(self):
        half = (0x1200, 0x01, 0x18, b'\x33' * 8 + b'\x00' * 8)
        problems = q.judge([], ([NEW], STASH, 0), [(2, ([half], STASH, 0))], False)
        self.assertTrue(any('경계 2' in p for p in problems))

    def test_reference_that_drops_pending_entry_fails_without_any_race(self):
        # 옛 차례(rd 검사가 WhStash 뒤): 끼어들기가 없어도 남은 앞 항목을 버리고 묶은 이름을 보냈다
        problems = q.judge([A], ([NEW], (1, 8, b'x'), 0), [], True)
        self.assertTrue(any('끼어들기 없이도' in p for p in problems))
        self.assertTrue(any('묶음으로 뺀 이름' in p for p in problems))

    def test_stash_mismatch_and_leftover_fail(self):
        ref = ([A], (1, 8, b'x'), 0)
        problems = q.judge([A], ref, [(4, ([A], (0, 0, b''), 2))], True)
        self.assertTrue(any('묶음 버퍼' in p for p in problems))
        self.assertTrue(any('비지 않음' in p for p in problems))


class PendingTests(unittest.TestCase):
    def test_reads_entries_from_read_position(self):
        wram = bytearray(0x20000)
        wram[q.WQ_COUNT] = 2
        wram[q.WQ_RD:q.WQ_RD + 2] = (0x10, 0x00)
        at = q.WQ_BUF + 0x10
        wram[at:at + 4] = (0x00, 0x10, 0x00, 0x01)          # 방식 0, 한 칸: 16바이트
        wram[at + 4:at + 20] = b'\x11' * 16
        at += 20
        wram[at:at + 4] = (0x10, 0x10, 0x01, 0x01)          # 방식 1, 한 칸: 평면 0 8바이트 + 평면 1 FF
        wram[at + 4:at + 12] = b'\x22' * 8
        self.assertEqual(q.pending(wram), [A, B, B_FF])


class CpuTests(unittest.TestCase):
    def test_scanline_reads_inside_vblank_and_nmi_flag_follows_4200(self):
        c = q.RaceCpu(bytes(0x8000), bytes(0x20000))
        c.read(0x00213F)
        self.assertEqual((c.read(0x00213D), c.read(0x00213D)), (q.VBLANK_LINE, 0))
        self.assertEqual([c.read(0x004212) & 0x80 for _ in range(3)], [0x80, 0, 0x80])
        c.write(0x004200, 0x01)
        self.assertFalse(c.nmi_on)
        c.write(0x004200, 0x81)
        self.assertTrue(c.nmi_on)


if __name__ == '__main__':
    unittest.main()
