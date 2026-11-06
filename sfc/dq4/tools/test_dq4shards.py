"""dq4shards: 기본 병렬 수가 HEADLESS_SLOTS 를 따르고, 결과가 끝난 순서와 상관없이 넣은 순서인지."""
import os
import threading
import unittest
from unittest import mock

import dq4shards


class ShardTests(unittest.TestCase):
    def test_jobs_follows_headless_slots(self):
        with mock.patch.dict(os.environ, HEADLESS_SLOTS='5'):
            self.assertEqual(dq4shards.jobs(), 5)
        with mock.patch.dict(os.environ, HEADLESS_SLOTS='off'):
            self.assertEqual(dq4shards.jobs(), max(1, (os.cpu_count() or 2) // 2))

    def test_pmap_keeps_input_order_whatever_finishes_first(self):
        # 마지막 항목이 먼저 끝나고 앞 항목을 하나씩 풀어 준다
        gates = [threading.Event() for _ in range(4)]
        finished = []

        def work(i):
            if i < 3:
                self.assertTrue(gates[i].wait(5))
            finished.append(i)
            if i > 0:
                gates[i - 1].set()
            return i * 10

        self.assertEqual(dq4shards.pmap(work, [0, 1, 2, 3], 4), [0, 10, 20, 30])
        self.assertEqual(finished, [3, 2, 1, 0])

    def test_pmap_runs_items_together_up_to_n(self):
        barrier = threading.Barrier(3, timeout=5)
        self.assertEqual(dq4shards.pmap(lambda i: barrier.wait() >= 0, range(3), 3), [True] * 3)

    def test_pmap_empty_and_error(self):
        self.assertEqual(dq4shards.pmap(lambda i: i, [], 4), [])
        with self.assertRaises(ZeroDivisionError):
            dq4shards.pmap(lambda i: 1 // i, [1, 0], 2)


if __name__ == '__main__':
    unittest.main()
