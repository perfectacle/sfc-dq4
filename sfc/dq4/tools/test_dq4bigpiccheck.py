"""롬 없이: 전투 큰 그림 길 검사의 기록 읽기·덩어리 나누기·판정."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dq4bigpiccheck as bp  # noqa: E402

LOG = '\n'.join([
    '10 8952 00 0', '11 8952 0A 0', '11 msg 05E', '12 8952 08 -1', '13 8952 0A 2', '14 8952 00 0',
    '15 inj 4 6', '16 8926 00 0', '17 8952 04 0', '18 8952 00 0',
])


class ParseTest(unittest.TestCase):
    def test_reads_battle_nmis_messages_and_injections(self):
        nmis, msgs, injects = bp.parse(LOG)
        self.assertEqual(nmis, [(10, 0, 0), (11, 0x0A, 0), (12, 0x08, -1), (13, 0x0A, 2), (14, 0, 0), (17, 4, 0), (18, 0, 0)])
        self.assertEqual(msgs, [(11, 0x5E)])
        self.assertEqual(injects, [(4, 6)])

    def test_runs_split_on_the_normal_path(self):
        nmis, msgs, _ = bp.parse(LOG)
        found = bp.runs(nmis, msgs)
        self.assertEqual([(r['frame'], r['length'], r['kinds'], r['queued'], r['message']) for r in found],
                         [(11, 3, ['0A', '08', '0A'], 1, '05E'), (17, 1, ['04'], 0, '05E')])

    def test_a_run_at_the_end_is_kept(self):
        self.assertEqual(len(bp.runs([(1, 0x0A, 0)], [])), 1)


class JudgeTest(unittest.TestCase):
    def found(self, *lengths):
        return [{'length': n, 'frame': i, 'message': None} for i, n in enumerate(lengths)]

    def test_passes_within_the_limit(self):
        injects = [(0, 1)] * bp.INJECT
        self.assertEqual(bp.judge(self.found(1, bp.LIMIT), injects), (bp.LIMIT, 1, []))

    def test_fails_on_a_long_run_or_a_late_item(self):
        injects = [(0, 1)] * bp.INJECT
        self.assertTrue(bp.judge(self.found(bp.LIMIT + 1), injects)[2])
        self.assertTrue(bp.judge(self.found(1), [(0, bp.LIMIT + 1)] + injects[1:])[2])

    def test_fails_when_items_did_not_go_out(self):
        self.assertTrue(bp.judge(self.found(1), [(0, 1)])[2])


class SamePrefixTest(unittest.TestCase):
    def test_compares_before_the_last_frame_every_run_has(self):
        # the last shared frame may be cut mid-write in one run, so it is left out
        a = '1 x\n2 y\n3 z'
        self.assertEqual(len(set(bp.same_prefix([a, '1 x\n2 q']))), 1)
        self.assertEqual(len(set(bp.same_prefix([a, '1 q\n2 y']))), 2)


if __name__ == '__main__':
    unittest.main()
