"""dq4soundcompact 의 Go 도구(dq4repeats)가 파이썬 _repeats_py 와 같은 것을 같은 차례로 내는지 대조한다."""
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


class NativeRepeatsTests(unittest.TestCase):
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
