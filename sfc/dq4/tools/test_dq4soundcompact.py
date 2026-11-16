"""dq4soundcompact 의 Go 도구(dq4repeats)와 파이썬 _repeats_py 가 목록 조각 정렬(옛 파이썬 구현)과 같은 것을 같은 차례로 내는지,
묶기를 캐시 없이 되풀이할 때 프로세스 안에서 한 번만 묶는지 본다."""
import os
import random
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import dq4native
import dq4soundcompact as compaction


def native_or_skip(test):
    path = dq4native.binary('dq4repeats')
    if path is None:
        if shutil.which('go') is None:
            test.skipTest('go 가 없고 dq4repeats 도 만들지 않음')
        tmp = tempfile.mkdtemp()
        test.addCleanup(shutil.rmtree, tmp, True)
        with mock.patch.dict(os.environ, {'DQ4_NATIVE': tmp}):
            path = dq4native.build('dq4repeats')
    native = compaction._Native(path)
    test.addCleanup(native.close)
    return native


def walled(rng, n, alphabet):
    arr = []
    for _ in range(n):
        arr.append(-len(arr) - 1 if rng.random() < 0.05 else rng.randrange(alphabet))
    return arr


def slice_sorted_repeats(arr, max_tokens):
    """목록 조각으로 정렬하는 옛 _repeats_py. 바이트 정렬·numpy LCP 로 바꾼 것이 같은 차례인지 견주는 기준."""
    n = len(arr)
    order = sorted(range(n), key=lambda i: arr[i:i + max_tokens])
    lcp = [0] * n
    for k in range(1, n):
        a, b = order[k - 1], order[k]
        m = 0
        while m < max_tokens and a + m < n and b + m < n and arr[a + m] == arr[b + m] and arr[a + m] >= 0:
            m += 1
        lcp[k] = m
    stack = [(0, 0)]
    for k in range(1, n + 1):
        value = lcp[k] if k < n else 0
        left = k - 1
        while value < stack[-1][0]:
            length, left = stack.pop()
            if length >= 2:
                yield length, order[left:k]
        if value > stack[-1][0]:
            stack.append((value, left))


class NativeRepeatsTests(unittest.TestCase):
    def test_python_repeats_match_the_slice_sort(self):
        rng = random.Random(9)
        cases = [[], [1], [1, 1], [-1, -2], [0, 1, 0, 1, 0, 1, -7, 0, 1], [5] * 600]
        cases += [walled(rng, n, a) for n, a in ((50, 2), (300, 3), (2000, 6), (3000, 40))]
        cases.append([x * 30000 if x >= 0 else x for x in walled(rng, 500, 4)])   # 2바이트를 넘는 토큰
        for arr in cases:
            for max_tokens in (1, 2, 7, 256):
                self.assertEqual(list(compaction._repeats_py(arr, max_tokens)),
                                 list(slice_sorted_repeats(arr, max_tokens)), (len(arr), max_tokens))

    def test_uncached_compaction_runs_once_per_input(self):
        phrase = ['  instrument 01', '  note 30 len 0C', '  note 32', '  pan 10', '  note 34', '  tie len 18']
        lines = ['tempo 40', 'Lvoice0:', *(phrase * 4), '  rest len 30', '  end']
        compaction._COMPACTED.clear()
        first = compaction.compact(lines)
        first.append('바꿔도 다음 결과는 그대로')
        with mock.patch.object(compaction, '_compact', side_effect=AssertionError('다시 묶음')):
            again = compaction.compact(list(lines))
        self.assertEqual(again, first[:-1])

    def test_same_groups_in_the_same_order(self):
        native = native_or_skip(self)
        rng = random.Random(4)
        cases = [[], [1], [1, 1], [-1, -2], [0, 1, 0, 1, 0, 1, -7, 0, 1]]
        cases += [walled(rng, n, a) for n, a in ((50, 2), (300, 3), (2000, 6), (5000, 40))]
        cases.append(([3, 4, 5] * 400) + [-1201] + [3, 4, 5] * 10)
        for arr in cases:
            for max_tokens in (2, 7, 256):
                self.assertEqual(native.repeats(arr, max_tokens), list(compaction._repeats_py(arr, max_tokens)),
                                 (len(arr), max_tokens))

    def test_compact_is_the_same_with_and_without_the_tool(self):
        native = native_or_skip(self)
        phrase = ['  instrument 01', '  note 30 len 0C', '  note 32', '  pan 10', '  note 34', '  tie len 18']
        other = ['  pan F0', '  note 20 len 0C', '  note 24', '  volume2 60', '  note 27', '  note 2C len 18']
        lines = ['tempo 40', 'Lvoice0:', *(phrase * 3 + other + phrase + other * 2), '  rest len 30', '  end',
                 'Lvoice1:', *(other + phrase * 2 + other), '  rest len 30', '  end']
        with mock.patch.object(compaction, '_native', return_value=None):
            plain = compaction._compact(list(lines))
        with mock.patch.object(compaction, '_native', return_value=native):
            fast = compaction._compact(list(lines))
        self.assertEqual(fast, plain)
        self.assertTrue(any('call' in x for x in fast))

    def test_falls_back_to_python_without_the_tool(self):
        with mock.patch.dict(os.environ, {'DQ4_NATIVE': 'off'}):
            dq4native.binary.cache_clear()
            try:
                self.assertIsNone(dq4native.binary('dq4repeats'))
            finally:
                dq4native.binary.cache_clear()
        with mock.patch.object(compaction, '_native', return_value=None):
            self.assertEqual(list(compaction._repeats([1, 2, 1, 2], 256)), list(compaction._repeats_py([1, 2, 1, 2], 256)))

    def test_source_hash_names_the_binary(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {'DQ4_NATIVE': d}):
            self.assertEqual(dq4native.target('dq4repeats'),
                             Path(d) / f'dq4repeats-{dq4native.source_hash("dq4repeats")}')


if __name__ == '__main__':
    unittest.main()
