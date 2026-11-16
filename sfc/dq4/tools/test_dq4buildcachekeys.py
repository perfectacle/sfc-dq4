"""빌드 단계 캐시 키가 단계가 실제로 읽는 것을 모두 담는가(dq4buildkeys). 추적기 자체는 가짜 도구로, 실제 빌드는
롬·ASAR·DQ4_GALMURI 가 있을 때 1장→2장 출하 롬의 캐시 단계 전부(하위 호출 포함)로 본다."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import dq4buildcache
import dq4buildkeys as keys

ROOT = Path(__file__).resolve().parents[3]

# 인자 파일을 -o 에 베낀다. EXTRA 자리에 몰래(인자 밖) 읽는 줄을 넣는다
TOOL = '''import os, sys
from pathlib import Path
src, out = Path(sys.argv[1]), Path(sys.argv[sys.argv.index("-o") + 1])
data = src.read_text()
{extra}
out.write_text(data)
'''

# 하위 호출을 dq4buildcache.run 으로 부르는 도구: 그 하위 호출만 몰래 읽는다
OUTER = '''import sys
from pathlib import Path
sys.path.insert(0, {tools!r})
import dq4buildcache
src, out = Path(sys.argv[1]), Path(sys.argv[sys.argv.index("-o") + 1])
dq4buildcache.run({inner!r}, src, "-o", out)
'''


def without_coverage(test):
    """coverage 로 돌면 자식 Python 도 coverage 를 싣고 출력 자리 밖에 기록 파일을 써 추적기가 문제로 적는다. 시험이 그
    환경에 기대지 않게 자식에게 넘기지 않는다."""
    env = mock.patch.dict(os.environ)
    env.start()
    test.addCleanup(env.stop)
    for k in ('COVERAGE_PROCESS_CONFIG', 'COVERAGE_PROCESS_START'):
        os.environ.pop(k, None)


class TracerTests(unittest.TestCase):
    def setUp(self):
        without_coverage(self)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.tool = self.root / 'tool.py'
        self.tool.write_text(TOOL.format(extra=''))
        self.src = self.root / 'in.txt'
        self.src.write_text('in')
        self.site = keys.tracer(self.root)
        for f in (dq4buildcache._tool_hash, dq4buildcache._refs, dq4buildcache._digest, dq4buildcache._resolve):
            f.cache_clear()

    def problems(self, tool):
        keys.traced_run(tool, [self.src, '-o', self.root / 'out.txt'], self.root / 'logs', self.site)
        return keys.check_calls(self.root / 'logs')[1]

    def sneaky(self, extra):
        self.tool.write_text(TOOL.format(extra=extra))
        return self.tool

    def test_tool_reading_only_its_arguments_is_clean(self):
        self.assertEqual(self.problems(self.tool), [])
        self.assertEqual((self.root / 'out.txt').read_text(), 'in')

    def test_file_read_outside_the_key_is_reported(self):
        sneak = self.root / 'sneak.txt'
        sneak.write_text('s')
        found = self.problems(self.sneaky(f'data += Path({str(sneak)!r}).read_text()'))
        self.assertTrue(any('키에 없는 입력 파일' in p and 'sneak.txt' in p for p in found), found)

    def test_environment_variable_outside_the_key_is_reported(self):
        with mock.patch.dict(os.environ, {'SNEAK_ENV': '1'}):
            found = self.problems(self.sneaky('data += os.environ.get("SNEAK_ENV", "")'))
        self.assertIn('tool.py ' + str(self.src) + ': 키에 없는 환경 변수: SNEAK_ENV', found)

    def test_nested_build_cache_call_is_checked_on_its_own(self):
        outer = self.root / 'outer.py'
        outer.write_text(OUTER.format(tools=str(Path(dq4buildcache.__file__).parent), inner=str(self.tool)))
        sneak = self.root / 'sneak.txt'
        sneak.write_text('s')
        self.sneaky(f'data += Path({str(sneak)!r}).read_text()')
        found = self.problems(outer)
        # 하위 호출(tool.py)도, 그것을 부른 바깥 호출(outer.py)도 빠진 입력을 낸다
        self.assertTrue(any(p.startswith('tool.py') and 'sneak.txt' in p for p in found), found)
        self.assertTrue(any(p.startswith('outer.py') and 'sneak.txt' in p for p in found), found)
        self.assertEqual((self.root / 'out.txt').read_text(), 'ins')


ROMS = all((ROOT / 'rom' / n).is_file() for n in ('dq5.sfc', 'dq4.nes'))
TOOLS = all(os.environ.get(n) for n in ('ASAR', 'DQ4_GALMURI'))


@unittest.skipUnless(ROMS and TOOLS, '롬(rom/dq5.sfc·dq4.nes)과 ASAR·DQ4_GALMURI 가 있어야 함')
class ShipBuildKeyTests(unittest.TestCase):
    def setUp(self):
        without_coverage(self)

    def test_every_cached_stage_key_holds_what_the_stage_reads(self):
        with tempfile.TemporaryDirectory() as d:
            names, problems = keys.build_traced(Path(d) / 'out', ROOT / 'rom' / 'dq5.sfc', ROOT / 'rom' / 'dq4.nes',
                                                True, Path(d))
        self.assertGreater(len(names), 6)
        self.assertEqual(problems, [])


if __name__ == '__main__':
    unittest.main()
