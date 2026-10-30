import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import dq4buildcache as cache

# 입력 파일과 그 JSON 이 가리키는 파일을 이어 -o 에 쓰고, 돌 때마다 RUNS 파일에 한 줄 더한다
TOOL = '''import json, os, sys
from pathlib import Path
src, out = Path(sys.argv[1]), Path(sys.argv[sys.argv.index("-o") + 1])
data = src.read_text()
if src.suffix == ".json":
    data += (src.parent / json.loads(data)["source"]).read_text()
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(data)
with open(os.environ["RUNS"], "a") as f:
    f.write("run\\n")
print("done")
'''


class BuildCacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.tool = self.root / 'tool.py'
        self.tool.write_text(TOOL)
        self.runs = self.root / 'runs'
        env = {'DQ4_BUILD_CACHE': str(self.root / 'cache'), 'RUNS': str(self.runs)}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)
        for f in (cache._tool_hash, cache._refs, cache._digest):
            f.cache_clear()

    def call(self, src, out):
        return cache.run(self.tool, src, 'patch', '-o', out)

    def count(self):
        return len(self.runs.read_text().splitlines()) if self.runs.exists() else 0

    def test_hit_restores_output_and_stdout_without_running(self):
        src = self.root / 'in.txt'
        src.write_text('a')
        self.assertEqual(self.call(src, self.root / 'one' / 'out.txt'), 'done\n')
        self.assertEqual(self.call(src, self.root / 'two' / 'out.txt'), 'done\n')
        self.assertEqual(self.count(), 1)
        self.assertEqual((self.root / 'two' / 'out.txt').read_text(), 'a')

    def test_input_content_change_runs_again(self):
        src = self.root / 'in.txt'
        src.write_text('a')
        self.call(src, self.root / 'out.txt')
        src.write_text('b')
        self.call(src, self.root / 'out.txt')
        self.assertEqual(self.count(), 2)
        self.assertEqual((self.root / 'out.txt').read_text(), 'b')

    def test_file_named_inside_json_input_is_part_of_the_key(self):
        (self.root / 'part.txt').write_text('x')
        src = self.root / 'in.json'
        src.write_text(json.dumps({'source': 'part.txt'}))
        self.call(src, self.root / 'out.txt')
        (self.root / 'part.txt').write_text('y')
        self.call(src, self.root / 'out.txt')
        self.assertEqual(self.count(), 2)
        self.assertTrue((self.root / 'out.txt').read_text().endswith('y'))

    def test_tool_source_change_runs_again(self):
        src = self.root / 'in.txt'
        src.write_text('a')
        self.call(src, self.root / 'out.txt')
        self.tool.write_text(TOOL + '# changed\n')
        for f in (cache._tool_hash, cache._refs, cache._digest):
            f.cache_clear()
        self.call(src, self.root / 'out.txt')
        self.assertEqual(self.count(), 2)

    def test_off_never_stores(self):
        src = self.root / 'in.txt'
        src.write_text('a')
        with mock.patch.dict(os.environ, {'DQ4_BUILD_CACHE': 'off'}):
            self.call(src, self.root / 'out.txt')
            self.call(src, self.root / 'out.txt')
        self.assertEqual(self.count(), 2)
        self.assertFalse((self.root / 'cache').exists())

    def test_failure_raises_with_stderr(self):
        bad = self.root / 'bad.py'
        bad.write_text('import sys\nsys.exit("boom")\n')
        with self.assertRaisesRegex(RuntimeError, 'boom'):
            cache.run(bad, '-o', self.root / 'out.txt')


if __name__ == '__main__':
    unittest.main()
