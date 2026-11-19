"""dq4npccheck --part: 장면 목록을 몫으로 나누는 틀(롬·에뮬레이터 없이)."""
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4npccheck as npc  # noqa: E402


def job(kind, name):
    return kind, name, '37/00', '37/00,2,3', 'up', False, (0x123, None)


JOBS = [job('table', 'table-3700-day'), job('table', 'table-3700-night')] + \
    [job('talk', f'talk-3700-{i}') for i in range(7)] + [job('talk', 'talk-3700-3-foot'), job('shop', 'shop-3700-8'),
                                                         job('inn', 'talk-3700-9')] + \
    [job(kind, f'talk-3701-{i}') for i, kind in enumerate(npc.SKIPPED_KINDS)]


class PartTest(unittest.TestCase):
    def parts(self, n):
        return [npc.part_jobs(JOBS, (k, n)) for k in range(1, n + 1)]

    def test_parts_cover_jobs_once_in_order(self):
        for n in (1, 2, 4, len(JOBS), len(JOBS) + 3):
            parts = self.parts(n)
            self.assertEqual(sorted(j[1] for p in parts for j in p), sorted(j[1] for j in JOBS), n)
            for p in parts:
                self.assertEqual(p, [j for j in JOBS if j in p])

    def test_skipped_scenes_weigh_nothing(self):
        # 결과만 적는 장면은 한 몫에만 적히고, 에뮬레이터를 띄우는 장면 수는 몫마다 고르다
        parts = self.parts(4)
        run = sorted(sum(j[0] not in npc.SKIPPED_KINDS for j in p) for p in parts)
        self.assertEqual(run, [3, 3, 3, 3])
        self.assertEqual(sorted(j[1] for p in parts for j in p if j[0] in npc.SKIPPED_KINDS),
                         sorted(j[1] for j in JOBS if j[0] in npc.SKIPPED_KINDS))

    def test_none_is_every_job_and_label(self):
        self.assertEqual(npc.part_jobs(JOBS, None), JOBS)
        self.assertIsNone(npc.part_label(None))
        self.assertEqual(npc.part_label((2, 5)), '2/5')


class PassedTest(unittest.TestCase):
    def test_needs_a_judged_scene(self):
        skipped = {"talk-3701-1": {"ok": True, "skipped": "map with no exit, entered only by an event"}}
        self.assertFalse(npc.passed({}))
        self.assertFalse(npc.passed(skipped))
        self.assertTrue(npc.passed({**skipped, "talk-3700-1": {"ok": True, "want": "123"}}))
        self.assertFalse(npc.passed({**skipped, "talk-3700-1": {"ok": False, "want": "123"}}))


if __name__ == '__main__':
    unittest.main()
