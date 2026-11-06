import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import unitshard  # noqa: E402

CI = Path(__file__).resolve().parents[2] / '.github' / 'workflows' / 'ci.yml'


class ShardTest(unittest.TestCase):
    def test_shards_cover_every_file_once_and_balance(self):
        files = ['a', 'b', 'c', 'd', 'e']
        times = {'a': 10, 'b': 6, 'c': 4, 'd': 1}
        parts = unitshard.shards(files, 2, times)
        self.assertEqual(sorted(f for p in parts for f in p), files)
        self.assertEqual(parts, unitshard.shards(list(reversed(files)), 2, times))
        loads = [sum(times.get(f, 21 / 4) for f in p) for p in parts]
        self.assertLessEqual(max(loads) - min(loads), 10)
        self.assertEqual(unitshard.shards(files, 1, {}), [files])

    def test_ci_shards_together_run_what_discover_runs(self):
        """CI test 매트릭스의 폴더마다 1..n 조각을 모으면 그 폴더의 test_*.py 전부다(조각을 나눠도 빠지는 테스트가 없게)."""
        text = CI.read_text(encoding='utf-8')
        rows = re.findall(r'\{track: [\w-]+, dir: (\S+), k: (\d+), n: (\d+)\}', text)
        self.assertTrue(rows)
        by_dir = {}
        for d, k, n in rows:
            by_dir.setdefault((d, int(n)), set()).add(int(k))
        times = unitshard.load_times()
        for (d, n), ks in by_dir.items():
            self.assertEqual(ks, set(range(1, n + 1)), d)
            files = unitshard.test_files(d)
            self.assertTrue(files, d)
            parts = unitshard.shards(files, n, times)
            self.assertTrue(all(parts), d)
            self.assertEqual(sorted(f for p in parts for f in p), files, d)


if __name__ == '__main__':
    unittest.main()
