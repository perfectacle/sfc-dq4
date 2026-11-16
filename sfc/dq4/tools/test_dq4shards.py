"""dq4shards: 기본 병렬 수가 HEADLESS_SLOTS 를 따르고, 결과가 끝난 순서와 상관없이 넣은 순서인지."""
import argparse
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


class PartTests(unittest.TestCase):
    def test_parts_cover_items_once_in_order(self):
        items = [f's{i:02}' for i in range(23)]
        for n in (1, 2, 3, 5, 23, 30):
            got = [dq4shards.part_of(items, (k, n)) for k in range(1, n + 1)]
            self.assertEqual(sorted(x for g in got for x in g), items)
            for g in got:
                self.assertEqual(g, [x for x in items if x in g])

    def test_none_is_everything_and_weights_balance(self):
        self.assertEqual(dq4shards.part_of([3, 1, 2], None), [3, 1, 2])
        w = {'a': 10, 'b': 6, 'c': 4, 'd': 1}
        got = [dq4shards.part_of('abcd', (k, 2), weight=w.get) for k in (1, 2)]
        self.assertEqual(got, [['a', 'd'], ['b', 'c']])

    def test_same_split_whatever_the_input_order(self):
        items = [f'm{i}' for i in range(17)]
        a = dq4shards.part_of(items, (2, 4))
        b = dq4shards.part_of(list(reversed(items)), (2, 4))
        self.assertEqual(sorted(a), sorted(b))

    def test_duplicate_keys_and_bad_part(self):
        with self.assertRaises(ValueError):
            dq4shards.part_of(['a', 'a'], (1, 2))
        import argparse
        for bad in ('0/2', '3/2', 'x'):
            with self.assertRaises(argparse.ArgumentTypeError):
                dq4shards.parse_part(bad)
        self.assertIsNone(dq4shards.parse_part(''))

    def test_part_sets_are_unions_of_parts(self):
        items = [f'u{i}' for i in range(11)]
        one = {k: dq4shards.part_of(items, (k, 4)) for k in range(1, 5)}
        part = dq4shards.parse_part('3,1/4')
        self.assertEqual(part, ((1, 3), 4))
        self.assertEqual(f'{part[0]}/{part[1]}', '1,3/4')
        self.assertEqual(dq4shards.parse_part('2/4'), (2, 4))
        self.assertEqual(sorted(dq4shards.part_of(items, part)), sorted(one[1] + one[3]))
        self.assertEqual(dq4shards.part_of(items, part), [x for x in items if x in one[1] + one[3]])
        for bad in ('1,1/4', '1,5/4', '0,1/4', ',1/4'):
            with self.assertRaises(argparse.ArgumentTypeError):
                dq4shards.parse_part(bad)

    def test_part_arg_reads_env_once(self):
        import argparse
        ap = argparse.ArgumentParser()
        with mock.patch.dict(os.environ, {dq4shards.PART_ENV: '2/3'}):
            dq4shards.add_part_arg(ap)
            self.assertNotIn(dq4shards.PART_ENV, os.environ)
        self.assertEqual(ap.parse_args([]).part, (2, 3))
        self.assertEqual(ap.parse_args(['--part', '1/4']).part, (1, 4))
