import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import release_check as rc  # noqa: E402


class ReleaseCheckTest(unittest.TestCase):
    def test_seed_list_keeps_order_and_adds_failed(self):
        self.assertEqual(rc.seed_list(3), [0, 1, 2])
        self.assertEqual(rc.seed_list(3, [7, 1, 9]), [0, 1, 2, 7, 9])

    def test_unit_counts(self):
        self.assertEqual(rc.unit_counts('...\nRan 12 tests in 1.0s\n\nOK (skipped=2)\n'), (12, 2))
        self.assertEqual(rc.unit_counts('Ran 1 test in 0s\nOK\n'), (1, 0))
        self.assertEqual(rc.unit_counts('Traceback'), (0, 0))

    def test_verdict_needs_every_stage_without_cache(self):
        ok = {s: {'status': 'passed'} for s in rc.STAGES}
        self.assertEqual(rc.verdict(ok, False, rc.STAGES), 'passed')
        self.assertEqual(rc.verdict(ok, True, rc.STAGES), 'rehearsal')
        self.assertEqual(rc.verdict({'build': ok['build']}, False, ['build']), 'partial')
        self.assertEqual(rc.verdict({**ok, 'coverage': {'status': 'failed'}}, False, rc.STAGES), 'failed')
        self.assertEqual(rc.verdict(ok, False, rc.STAGES, dirty=True), 'dirty')

    def test_coverage_thresholds(self):
        with tempfile.TemporaryDirectory() as d:
            ctx = {'logs': Path(d), 'dir': Path(d)}
            with mock.patch.object(rc, 'measure', side_effect=[(91.0, []), (80.5, [])]), \
                    mock.patch.object(rc.guards, 'git', return_value=''):
                self.assertEqual(rc.stage_coverage(ctx)['status'], 'passed')
            with mock.patch.object(rc, 'measure', side_effect=[(89.9, []), (85.0, ['tools/tests'])]), \
                    mock.patch.object(rc.guards, 'git', return_value=''):
                r = rc.stage_coverage(ctx)
            self.assertEqual(r['status'], 'failed')
            self.assertIn('로컬 89.9%', r['detail'])
            self.assertIn('tools/tests 시험이 실패함', r['detail'])

    def test_build_path_files_are_python_sources(self):
        files = rc.build_path_files()
        self.assertTrue(files)
        self.assertTrue(all(f.endswith('.py') and '/test_' not in f for f in files))
        self.assertIn(str(rc.ROOT / 'sfc/dq4/tools/dq4build.py'), files)

    def test_repo_sweeps_take_seeds(self):
        """저장소의 release.toml 스윕은 {rom}·{out}·{seeds} 를 모두 쓰고 이름이 겹치지 않는다."""
        got = rc.sweeps()
        self.assertTrue(got)
        self.assertEqual(len({s['name'] for s in got}), len(got))
        for s in got:
            for k in ('{rom}', '{out}', '{seeds}'):
                self.assertIn(k, s['run'], s['name'])
            self.assertTrue(s.get('why'), s['name'])

    def test_sweep_stage_formats_commands(self):
        ran = []
        with tempfile.TemporaryDirectory() as d:
            ctx = {'dir': rc.ROOT / 'work' / 'release-test', 'logs': Path(d), 'rehearse': False, 'seeds_n': 2,
                   'timeout': 10, 'rom': rc.ROOT / 'work' / 'release-test' / 'build' / 'r.sfc'}
            sw = [{'file': 'sfc/dq4/release.toml', 'name': 'x', 'run': 'echo {rom} {out} {seeds}'},
                  {'file': 'sfc/dq4/release.toml', 'name': 'y', 'run': 'echo {seeds}', 'seeds': 3}]
            with mock.patch.object(rc, 'sweeps', return_value=sw), \
                    mock.patch.object(rc, 'failed_seeds', side_effect=lambda s: [9] if s['name'] == 'y' else []), \
                    mock.patch.object(rc, 'sh', side_effect=lambda cmd, log, env, t: ran.append((cmd, env)) or (0, 1)):
                r = rc.stage_sweep(ctx)
        self.assertEqual(r['status'], 'passed')
        self.assertEqual(ran[0][0], 'echo work/release-test/build/r.sfc work/release-test/sweep/x 0,1')
        self.assertEqual(ran[1][0], 'echo 0,1,2,9')
        self.assertEqual(ran[0][1]['DQ4_READSET'], 'off')

    def test_failed_seeds_file(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'sfc/dq4').mkdir(parents=True)
            (root / 'sfc/dq4/seeds.json').write_text(json.dumps({'x': [{'seed': 5, 'fixed': 'abc'}]}))
            with mock.patch.object(rc, 'ROOT', root):
                self.assertEqual(rc.failed_seeds({'file': 'sfc/dq4/release.toml', 'name': 'x'}), [5])
                self.assertEqual(rc.failed_seeds({'file': 'sfc/dq4/release.toml', 'name': 'z'}), [])
                self.assertEqual(rc.failed_seeds({'file': 'sfc/dq5/release.toml', 'name': 'x'}), [])

    def test_load_counts_mesence_by_worktree(self):
        parent = Path('/w')
        ps = '\n'.join(['/a/MesenCE.app/Contents/MacOS/Mesen -r /w/sfc-dq4-x/work/a/c.sfc s.lua',
                        '/a/MesenCE.app/Contents/MacOS/Mesen -r /w/sfc-dq4-x/work/b/c.sfc s.lua',
                        '/a/MesenCE.app/Contents/MacOS/Mesen -r /w/sfc-dq4-release-check/work/c.sfc s.lua',
                        '/usr/bin/python3 /w/sfc-dq4-x/tools/guards.py', '/a/MacOS/Mesen -r /tmp/r.sfc'])
        self.assertEqual(rc.Load.count(ps, parent), {'sfc-dq4-x': 2, 'sfc-dq4-release-check': 1, '?': 1})

    def test_state_note(self):
        self.assertEqual(rc.state_note('{"state_cache": "hit"} {"state_cache": "miss"} {"state_cache": "hit"}'),
                         ['hit', 'miss'])

    def test_markdown_lists_stages(self):
        report = {'verdict': 'failed', 'commit': 'abc', 'dirty': False, 'rom_sha1': 'f' * 40, 'when': 'now',
                  'states': '새로 만듦',
                  'stages': {'unit': {'status': 'passed', 'seconds': 3, 'detail': '2개',
                                      'load': {'samples': 2, 'others_max': 3, 'others_avg': 1.5,
                                               'peak_by_tree': {'sfc-dq4-x': 3}},
                                      'rows': [{'dir': 'tools/tests', 'status': 'passed', 'tests': 2, 'skipped': 0,
                                                'seconds': 3}]},
                             'coverage': {'status': 'failed', 'seconds': 0, 'detail': '없음'}}}
        md = rc.markdown(report)
        self.assertIn('판정: **실패**', md)
        self.assertIn('| coverage | 실패 | 0초 | 없음 |', md)
        self.assertIn('`tools/tests`', md)
        self.assertIn('상태 캐시: 새로 만듦', md)
        self.assertIn('| unit | 3 | 1.5 | sfc-dq4-x 3 |', md)


if __name__ == '__main__':
    unittest.main()
