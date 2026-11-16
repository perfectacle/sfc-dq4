import json
import os
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
            ctx = {'logs': Path(d), 'dir': Path(d), 'rehearse': False}
            with mock.patch.object(rc, 'measure', side_effect=[(91.0, []), (80.5, [])]), \
                    mock.patch.object(rc.guards, 'git', return_value=''):
                self.assertEqual(rc.stage_coverage(ctx)['status'], 'passed')
            with mock.patch.object(rc, 'measure', side_effect=[(89.9, []), (85.0, ['tools/tests'])]), \
                    mock.patch.object(rc.guards, 'git', return_value=''):
                r = rc.stage_coverage(ctx)
            self.assertEqual(r['status'], 'failed')
            self.assertIn('로컬 89.9%', r['detail'])
            self.assertIn('tools/tests 시험이 실패함', r['detail'])

    def test_coverage_with_ci_records_measures_only_local_units(self):
        """--ci-report 면 로컬 수에는 CI 빌드 줄을, CI 와 같게에는 CI 단위 줄을 더한다. unit 단계가 coverage 로
        돌았으면 단위를 다시 돌지 않는다."""
        got = {'unit': {'failed': [], 'lines': {'u.py': [1]}}, 'build': {'failed': [], 'lines': {'b.py': [2]}}}
        with tempfile.TemporaryDirectory() as d:
            ctx = {'logs': Path(d), 'dir': Path(d), 'rehearse': False, 'ci': {'coverage': got}, 'unit_covered': True,
                   'unit_failed': []}
            with mock.patch.object(rc, 'coverage_result', side_effect=[(91.0, {}), (80.5, {})]) as res, \
                    mock.patch.object(rc, 'covered_units') as units, mock.patch.object(rc, 'measure') as measure:
                r = rc.stage_coverage(ctx)
            self.assertEqual(r['status'], 'passed', r)
            units.assert_not_called()
            measure.assert_not_called()
            self.assertEqual([(c.args[2], c.kwargs['extra']) for c in res.call_args_list],
                             [('local', {'b.py': [2]}), ('ci', {'u.py': [1]})])
            got['build']['failed'] = ['build']
            with mock.patch.object(rc, 'coverage_result', side_effect=[(91.0, {}), (80.5, {})]):
                self.assertIn('CI build 시험이 실패함', rc.stage_coverage(ctx)['detail'])
            ctx['ci'] = {'coverage': {'unit': got['unit']}}
            r = rc.stage_coverage(ctx)
        self.assertEqual(r['status'], 'failed')
        self.assertIn('CI 커버리지 기록 없음(build', r['detail'])

    def test_coverage_result_merges_ci_lines_by_repo_path(self):
        import coverage
        with tempfile.TemporaryDirectory() as d:
            root, logs = Path(d) / 'repo', Path(d) / 'logs'
            (root / 'pkg').mkdir(parents=True)
            logs.mkdir()
            mod = root / 'pkg' / 'm.py'
            mod.write_text('a = 1\nb = 2\nc = 3\nd = 4\n')
            data, _ = rc.coverage_paths(logs, 't')
            local = coverage.CoverageData(basename=str(data), suffix='local')
            local.add_lines({os.path.realpath(mod): [1]})
            local.write()
            with mock.patch.object(rc, 'build_path_files', return_value=[str(mod)]):
                percent, lines = rc.coverage_result(root, logs, 't', extra={'pkg/m.py': [2, 3], 'gone.py': [1]})
                self.assertEqual((percent, lines), (75.0, {'pkg/m.py': [1, 2, 3]}))
                self.assertEqual(rc.coverage_result(root, logs, 'none')[0], 0.0)

    def test_ci_coverage_records_lines_and_fails_only_on_build(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            out = root / 'up' / 'cov.json'
            with mock.patch.object(rc, 'covered_units', return_value=['tools/tests']), \
                    mock.patch.object(rc, 'covered_build', return_value=['build']) as build, \
                    mock.patch.object(rc, 'coverage_result', return_value=(42.0, {'a.py': [1]})), \
                    mock.patch.object(rc.guards, 'git', return_value='abc\n'), \
                    mock.patch('builtins.print'):
                self.assertEqual(rc.ci_coverage('unit', out, root=root), 0)
                rec = json.loads(out.read_text(encoding='utf-8'))
                self.assertEqual(rec, {'format': rc.COVERAGE_FORMAT, 'commit': 'abc', 'kind': 'unit', 'percent': 42.0,
                                       'failed': ['tools/tests'], 'lines': {'a.py': [1]}})
                self.assertEqual(rc.ci_coverage('build', out, Path('work/x'), root=root), 1)
                self.assertEqual(build.call_args.args[4], Path('work/x'))
            self.assertEqual(rc.load_coverage(root, 'abc')['build']['failed'], ['build'])
            with self.assertRaisesRegex(ValueError, '커밋'):
                rc.load_coverage(root, 'other')

    def test_unit_stage_runs_under_coverage_when_coverage_follows(self):
        cmds = []

        def ok(cmd, log, env):
            cmds.append(cmd)
            log.write_text('Ran 2 tests')
            return (1 if 'no/such' in cmd else 0), 1
        with tempfile.TemporaryDirectory() as d:
            ctx = {'dir': Path(d), 'logs': Path(d), 'rehearse': True, 'cover': True}
            with mock.patch.object(rc, 'UNIT_DIRS', ('tools/tests',)), mock.patch.object(rc, 'sh', side_effect=ok):
                rc.stage_unit(ctx)
            self.assertIn(f'coverage run --rcfile={Path(d) / "coverage-local.ini"} -m unittest', cmds[0])
            self.assertEqual((ctx['unit_covered'], ctx['unit_failed']), (True, []))

    def test_build_path_files_are_python_sources(self):
        files = rc.build_path_files()
        self.assertTrue(files)
        self.assertTrue(all(f.endswith('.py') and '/test_' not in f for f in files))
        self.assertIn(str(rc.ROOT / 'sfc/dq4/tools/dq4build.py'), files)

    def test_publish_checks_the_same_stages(self):
        """배포판(dq4publish.check_report)이 보는 단계가 관문 단계와 같아야 한다."""
        rc.build_path_files()  # dq4publish 를 import 할 경로를 넣는다
        import dq4publish
        self.assertEqual(tuple(dq4publish.GATE_STAGES), rc.STAGES)

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
        for k, v in (('DQ4_READSET', 'off'), ('DQ4_BUILD_CACHE', 'off'),
                     ('DQ4_STATES_CACHE', str(rc.ROOT / 'work' / 'release-test' / 'states'))):
            self.assertEqual(ran[0][1][k], v, k)

    def test_failed_seeds_file(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'sfc/dq4').mkdir(parents=True)
            (root / 'sfc/dq4/seeds.json').write_text(json.dumps({'x': [{'seed': 5, 'fixed': 'abc'}]}))
            with mock.patch.object(rc, 'ROOT', root):
                self.assertEqual(rc.failed_seeds({'file': 'sfc/dq4/release.toml', 'name': 'x'}), [5])
                self.assertEqual(rc.failed_seeds({'file': 'sfc/dq4/release.toml', 'name': 'z'}), [])
                self.assertEqual(rc.failed_seeds({'file': 'sfc/dq5/release.toml', 'name': 'x'}), [])

    def test_gate_env_turns_every_cache_off_and_rehearse_keeps_it(self):
        ctx = {'dir': Path('/r/run-1'), 'rehearse': False}
        env = rc.env_for(ctx, {'X': '1'})
        self.assertEqual((env['DQ4_READSET'], env['DQ4_BUILD_CACHE'], env['DQ4_STATES_CACHE'], env['X']),
                         ('off', 'off', '/r/run-1/states', '1'))
        self.assertIsNone(rc.env_for({**ctx, 'rehearse': True}))
        self.assertEqual(rc.env_for({**ctx, 'rehearse': True}, {'X': '1'}), {'X': '1'})

    def test_build_stage_envs_cache_only_the_gated_build(self):
        run = Path('/r/run-1')
        cold = rc.cold_env(run, {'X': '1', 'DQ4_BUILD_CACHE': '/c'})
        self.assertEqual((cold['DQ4_BUILD_CACHE'], cold['DQ4_SOUND_CACHE'], cold['DQ4_NATIVE'], cold['DQ4_READSET']),
                         ('off', 'off', 'off', 'off'))
        self.assertEqual(rc.cached_env(run, {'DQ4_BUILD_CACHE': '/c'})['DQ4_BUILD_CACHE'], '/c')
        cached = rc.cached_env(run, {'X': '1'})
        self.assertNotIn('DQ4_BUILD_CACHE', cached)
        self.assertEqual((cached['DQ4_READSET'], cached['X']), ('off', '1'))

    def _work(self):
        """stage_build 는 실행 폴더를 저장소 기준 상대 경로로 넘기므로 저장소 안 work/ 에 둔다."""
        (rc.ROOT / 'work').mkdir(exist_ok=True)
        return rc.ROOT / 'work'

    def _fake_build(self, differ):
        """sh 대신: --out 폴더에 롬과 ledger 를 쓴다. differ 면 무캐시 빌드의 1장 롬이 다르다."""
        def sh(cmd, log, env=None, timeout=None):
            out = rc.ROOT / cmd.split('--out ')[1].split()[0]
            out.mkdir(parents=True, exist_ok=True)
            cold = env and env.get('DQ4_NATIVE') == 'off'
            (out / rc.ROM_NAME).write_bytes(b'rom')
            (out / 'dq4-ch1.sfc').write_bytes(b'ch1-other' if cold and differ else b'ch1')
            (out / 'ledger.json').write_text('{}')
            log.write_text('ok')
            return 0, 1
        return sh

    def test_build_stage_fails_when_the_cached_build_differs_from_the_cold_one(self):
        for differ in (False, True):
            with tempfile.TemporaryDirectory(dir=self._work()) as d, \
                    mock.patch.object(rc, 'sh', self._fake_build(differ)):
                run = Path(d)
                (run / 'logs').mkdir()
                got = rc.stage_build({'dir': run, 'logs': run / 'logs', 'rehearse': False})
                self.assertEqual(got['status'], 'failed' if differ else 'passed', got)
                if differ:
                    self.assertIn('캐시 키', got['detail'])
                    self.assertIn('chapter1 build', (run / 'logs' / 'build-verify.md').read_text(encoding='utf-8'))
                else:
                    self.assertTrue((run / 'build-cold' / rc.ROM_NAME).is_file())
                    self.assertIn('무캐시 빌드와 바이트 같음', got['detail'])

    def test_rehearsal_build_skips_the_cold_build(self):
        with tempfile.TemporaryDirectory(dir=self._work()) as d, \
                mock.patch.object(rc, 'sh', self._fake_build(True)):
            run = Path(d)
            (run / 'logs').mkdir()
            got = rc.stage_build({'dir': run, 'logs': run / 'logs', 'rehearse': True})
            self.assertEqual(got['status'], 'passed')
            self.assertFalse((run / 'build-cold').exists())

    def test_stage_exception_is_recorded_not_raised(self):
        def boom(ctx):
            raise RuntimeError('worktree add 실패')
        with mock.patch.dict(rc.RUN, {'build': boom, 'unit': lambda ctx: {'status': 'passed', 'seconds': 0}}), \
                mock.patch.object(rc.Load, 'SAMPLE', 0.01):
            got = rc.run_stages({}, ['build', 'unit'])
        self.assertEqual(got['build']['status'], 'failed')
        self.assertIn('worktree add 실패', got['build']['detail'])
        self.assertEqual(got['unit']['status'], 'passed')

    def test_dirty_counts_untracked_files(self):
        with mock.patch.object(rc.guards, 'git', side_effect=lambda *a: 'abc\n' if a[0] == 'rev-parse' else '?? new.py\n'):
            self.assertEqual(rc.commit(), ('abc', True))
        with mock.patch.object(rc.guards, 'git', side_effect=lambda *a: 'abc\n' if a[0] == 'rev-parse' else ''):
            self.assertEqual(rc.commit(), ('abc', False))

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

    def test_no_checks_or_sweeps_is_not_passed(self):
        ctx = {'dir': rc.ROOT / 'work' / 'release-test', 'logs': Path('/nonexistent'), 'rehearse': False,
               'seeds_n': 2, 'timeout': 10, 'parallel': 1, 'rom': rc.ROOT / 'work' / 'release-test' / 'r.sfc'}
        with mock.patch.object(rc.guards, 'load', return_value=([], [])), \
                mock.patch.object(rc.guards, 'tracked', return_value=[]), \
                mock.patch.object(rc.guards, 'run_many', return_value=[]):
            self.assertEqual(rc.stage_guards(ctx)['status'], 'failed')
        with mock.patch.object(rc, 'sweeps', return_value=[]):
            self.assertEqual(rc.stage_sweep(ctx)['status'], 'failed')

    def test_guards_stage_runs_every_check_whatever_its_tier_or_groups(self):
        """배포 관문은 PR 에서 빠지는 검사(tier = "release", 묶음으로만 걸리는 것)까지 모든 실행 검사를 돌린다."""
        checks, problems = rc.guards.load(rc.guards.tracked())
        self.assertEqual(problems, [])
        self.assertTrue(any(c.get('tier') == 'release' for c in checks))
        ctx = {'logs': Path('/nonexistent'), 'rehearse': False, 'timeout': 10, 'parallel': 1}
        with mock.patch.object(rc.guards, 'run_many', return_value=[]) as run, \
                mock.patch.object(rc, 'env_for', return_value={}):
            rc.stage_guards(ctx)
        self.assertEqual([c['name'] for c in run.call_args[0][0]], [c['name'] for c in checks])

    def _ci(self, d, parts, commit='c' * 40):
        for i, (shard, rows, local) in enumerate(parts):
            sub = Path(d) / f'release-gate-shard-{i}'
            sub.mkdir()
            (sub / f'shard-{i}.json').write_text(json.dumps({'commit': commit, 'shard': shard, 'rows': rows,
                                                             'local': [{'name': n, 'file': 'g', 'needs': []} for n in local]}))
            (sub / 'logs').mkdir()

    def test_load_ci_needs_every_shard_of_one_commit(self):
        row = {'name': 'a', 'file': 'g', 'status': 'passed', 'detail': '9초'}
        with tempfile.TemporaryDirectory() as d:
            self._ci(d, [([1, 2], [row], ['m']), ([2, 2], [], ['m'])])
            ci = rc.load_ci(d)
            self.assertEqual((ci['shards'], ci['local'], [r['name'] for r in ci['rows']]), (2, ['m'], ['a']))
        with tempfile.TemporaryDirectory() as d:
            self._ci(d, [([1, 3], [row], []), ([3, 3], [], [])])
            with self.assertRaisesRegex(ValueError, '받은 것'):
                rc.load_ci(d)
        with tempfile.TemporaryDirectory() as d:
            self._ci(d, [([1, 2], [row], []), ([2, 2], [row], [])])
            with self.assertRaisesRegex(ValueError, '두 조각'):
                rc.load_ci(d)
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, '없음'):
                rc.load_ci(d)

    def test_load_ci_merges_guard_parts(self):
        def row(k, status='passed'):
            return {'name': 'p', 'file': 'g', 'status': status, 'detail': f'{k}0초', 'part': [k, 2]}
        with tempfile.TemporaryDirectory() as d:
            self._ci(d, [([1, 2], [row(1)], []), ([2, 2], [row(2)], [])])
            ci = rc.load_ci(d)
            self.assertEqual([(r['name'], r['status']) for r in ci['rows']], [('p', 'passed')])
        with tempfile.TemporaryDirectory() as d:
            self._ci(d, [([1, 2], [row(1)], []), ([2, 2], [row(2, 'failed')], [])])
            self.assertFalse(rc.ci_summary(rc.load_ci(d))[1])

    def test_load_ci_marks_cached_runs_and_skips_pass_records(self):
        """캐시를 쓴 조각(release-gate rehearse)이 하나라도 있으면 cached. 조각이 함께 올리는 통과 기록(results/)은 결과로 읽지 않는다."""
        row = {'name': 'a', 'file': 'g', 'status': 'passed', 'detail': '9초'}
        with tempfile.TemporaryDirectory() as d:
            self._ci(d, [([1, 1], [row], [])])
            self.assertFalse(rc.load_ci(d)['cached'])
            res = Path(d) / 'release-gate-shard-0' / 'results'
            (res / 'built').mkdir(parents=True)
            (res / 'a-0123.json').write_text(json.dumps({'when': '2026-11-16 01:00', 'detail': '9초'}))
            (res / 'built' / 'a-0123.json').write_text(json.dumps([{'when': 'x', 'detail': 'y', 'trace': {}}]))
            self.assertEqual([r['name'] for r in rc.load_ci(d)['rows']], ['a'])
            f = Path(d) / 'release-gate-shard-0' / 'shard-0.json'
            f.write_text(json.dumps(dict(json.loads(f.read_text()), cached=True)))
            ci = rc.load_ci(d)
        self.assertTrue(ci['cached'])
        text, ok = rc.ci_summary(ci)
        self.assertTrue(ok)
        self.assertIn('연습 통과', text)

    def test_ci_summary_fails_on_skipped(self):
        ci = {'commit': 'c', 'shards': 1, 'local': ['m'],
              'rows': [{'name': 'a', 'status': 'passed', 'detail': '1초'}]}
        text, ok = rc.ci_summary(ci)
        self.assertTrue(ok)
        self.assertIn('로컬 몫', text)
        ci['rows'].append({'name': 'b', 'status': 'skipped', 'detail': '설정 안 된 환경 변수 ASAR'})
        self.assertFalse(rc.ci_summary(ci)[1])
        self.assertFalse(rc.ci_summary(dict(ci, rows=[]))[1])

    def _digests(self, d, cold_rom=b'r', with_cold=True, commit='c' * 40):
        """CI artifact 꼴의 빌드 대조 파일: rom 잡(cached)·조각(shard-1)·무캐시(cold)."""
        sub = Path(d) / 'build-digest'
        sub.mkdir(exist_ok=True)
        kinds = [('cached', b'r'), ('shard-1', b'r')] + ([('cold', cold_rom)] if with_cold else [])
        for v in ('ch1', 'ch2'):
            for kind, rom in kinds:
                f = sub / f'{kind}-{v}.json'
                f.write_text(json.dumps({'format': 'dq4-build-digest/1', 'variant': v, 'kind': kind, 'commit': commit,
                                         'files': {'dq4-ch1-full.sfc': rom.hex(), 'ledger.json': '00'}}))

    def test_ci_summary_needs_the_cached_build_to_match_the_cold_build(self):
        row = {'name': 'a', 'file': 'g', 'status': 'passed', 'detail': '9초'}
        with tempfile.TemporaryDirectory() as d:
            self._ci(d, [([1, 1], [row], [])])
            self.assertIsNone(rc.load_ci(d)['build'])
            self.assertTrue(rc.ci_summary(rc.load_ci(d))[1])
            text, ok = rc.ci_summary(rc.load_ci(d), require_build=True)
            self.assertFalse(ok)
            self.assertIn('무캐시 빌드 결과가 없음', text)
            commit = json.loads(next(Path(d).rglob('shard-*.json')).read_text())['commit']
            self._digests(d, commit=commit)
            text, ok = rc.ci_summary(rc.load_ci(d), require_build=True)
            self.assertTrue(ok, text)
            self.assertIn('ch2: 같음', text)
            self._digests(d, cold_rom=b'x', commit=commit)
            text, ok = rc.ci_summary(rc.load_ci(d), require_build=True)
            self.assertFalse(ok)
            self.assertIn('캐시 키에 빠진 입력', text)
            self._digests(d, commit='d' * 40)
            self.assertFalse(rc.ci_summary(rc.load_ci(d), require_build=True)[1])

    def test_guards_stage_keeps_ci_verdicts_and_runs_only_the_local_share(self):
        """CI 결과가 있으면 로컬은 로컬 몫만 돈다. CI 가 판정한 검사는 다시 돌리지 않고(실패를 덮지 않음), CI 에서
        돌리지 않음·결과 없음인 검사도 로컬 에뮬레이터로 메우지 않고 통과가 아닌 것으로 남긴다."""
        checks, _ = rc.guards.load(rc.guards.tracked())
        a, b, c, d = checks[0], checks[1], checks[2], checks[3]
        ci = {'commit': 'x', 'shards': 1, 'local': [c['name']],
              'rows': [{'name': a['name'], 'file': a['file'], 'status': 'failed', 'detail': '종료 코드 1'},
                       {'name': b['name'], 'file': b['file'], 'status': 'skipped', 'detail': '설정 안 된 환경 변수'}]
              + [{'name': x['name'], 'file': x['file'], 'status': 'passed', 'detail': '1초'} for x in checks[4:]]}
        ctx = {'logs': Path('/nonexistent'), 'rehearse': False, 'timeout': 10, 'parallel': 1, 'ci': ci}
        with mock.patch.object(rc.guards, 'run_many', side_effect=lambda hit, *a, **k: [(x, 'passed', '1초') for x in hit]) as run, \
                mock.patch.object(rc, 'env_for', return_value={}):
            st = rc.stage_guards(ctx)
        self.assertEqual([x['name'] for x in run.call_args[0][0]], [c['name']])
        self.assertEqual(st['status'], 'failed')
        rows = {r['name']: r for r in st['rows']}
        self.assertEqual(rows[a['name']]['detail'], 'CI: 종료 코드 1')
        self.assertEqual(rows[b['name']]['status'], 'skipped')
        self.assertEqual((rows[d['name']]['status'], rows[d['name']]['detail']), ('skipped', 'CI 결과 없음'))
        self.assertEqual(len(st['rows']), len(checks))
        ci['rows'] = [dict(r, status='passed') for r in ci['rows']] + [
            {'name': d['name'], 'file': d['file'], 'status': 'passed', 'detail': '1초'}]
        with mock.patch.object(rc.guards, 'run_many', side_effect=lambda hit, *a, **k: [(x, 'passed', '1초') for x in hit]), \
                mock.patch.object(rc, 'env_for', return_value={}):
            self.assertEqual(rc.stage_guards(ctx)['status'], 'passed')

    def test_ci_sweeps_are_judged_from_ci_without_running(self):
        """--ci-report 의 sweep 단계는 CI 결과만 받는다. 스윕 하나라도 실패·없음이면 실패, 실패 글에 시드."""
        wanted = [{'file': 'sfc/dq4/release.toml', 'name': 'x'}, {'file': 'sfc/dq4/release.toml', 'name': 'y'}]
        rows = rc.guards.merge_parts([
            {'name': 'x', 'file': 'sfc/dq4/release.toml', 'status': 'passed', 'detail': '10초', 'part': [1, 2],
             'seeds': [0], 'sweep': True},
            {'name': 'x', 'file': 'sfc/dq4/release.toml', 'status': 'failed', 'detail': '종료 코드 1', 'part': [2, 2],
             'seeds': [1], 'sweep': True}])
        ci = {'commit': 'c', 'shards': 1, 'local': [], 'rows': [{'name': 'g', 'status': 'passed', 'detail': '1초'}],
              'sweeps': rows}
        ctx = {'ci': ci}
        with mock.patch.object(rc, 'sweeps', return_value=wanted), \
                mock.patch.object(rc, 'sh', side_effect=AssertionError('로컬에서 돌림')):
            st = rc.stage_sweep(ctx)
        self.assertEqual(st['status'], 'failed')
        got = {r['name']: r for r in st['rows']}
        self.assertEqual(got['x']['seeds'], [0, 1])
        self.assertIn('시드 1: 종료 코드 1', got['x']['detail'])
        self.assertEqual(got['y']['status'], 'skipped')
        text, ok = rc.ci_summary(ci, wanted=wanted)
        self.assertFalse(ok)
        self.assertIn('## 시드 스윕', text)
        self.assertIn('CI 결과 없음', text)
        ci['sweeps'] = rc.guards.merge_parts([dict(r, status='passed', detail='5초') for r in (
            {'name': n, 'file': 'f', 'part': [1, 1], 'seeds': [0], 'sweep': True} for n in ('x', 'y'))])
        with mock.patch.object(rc, 'sweeps', return_value=wanted):
            self.assertEqual(rc.stage_sweep(ctx)['status'], 'passed')
        self.assertTrue(rc.ci_summary(ci, wanted=wanted)[1])

    def test_load_ci_keeps_sweeps_apart(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 's.json').write_text(json.dumps({'commit': 'c', 'shard': [1, 1], 'local': [], 'rows': [
                {'name': 'g', 'file': 'f', 'status': 'passed', 'detail': '1초'},
                {'name': 'x', 'file': 'r', 'status': 'passed', 'detail': '2초', 'part': [1, 1], 'seeds': [0],
                 'sweep': True}]}))
            ci = rc.load_ci(d)
        self.assertEqual([r['name'] for r in ci['rows']], ['g'])
        self.assertEqual([(r['name'], r['status']) for r in ci['sweeps']], [('x', 'passed')])

    def test_missing_unit_dir_fails(self):
        def ok(cmd, log, env):
            log.write_text('Ran 2 tests')
            return 0, 1
        with tempfile.TemporaryDirectory() as d:
            ctx = {'dir': Path(d), 'logs': Path(d), 'rehearse': True}
            with mock.patch.object(rc, 'UNIT_DIRS', ('tools/tests', 'no/such/dir')), \
                    mock.patch.object(rc, 'sh', side_effect=ok):
                r = rc.stage_unit(ctx)
        self.assertEqual(r['status'], 'failed')
        self.assertEqual([(x['dir'], x['status']) for x in r['rows']],
                         [('tools/tests', 'passed'), ('no/such/dir', 'failed')])
        self.assertIn('no/such/dir', r['detail'])

    def test_coverage_measure_counts_missing_dir_as_failed(self):
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(rc, 'UNIT_DIRS', ('no/such/dir',)), \
                mock.patch.object(rc, 'build_path_files', return_value=[]), \
                mock.patch('coverage.Coverage') as cov:
            cov.return_value.report.return_value = 100.0
            _, failed = rc.measure(Path(d), Path(d), 't', None)
        self.assertEqual(failed, ['no/such/dir(폴더 없음)'])

    def test_markdown_with_empty_seeds_and_report_survives_a_bad_table(self):
        report = {'verdict': 'failed', 'commit': 'abc', 'dirty': False, 'rom_sha1': None, 'when': 'now',
                  'stages': {'sweep': {'status': 'failed', 'seconds': 0, 'detail': '',
                                       'rows': [{'name': 'x', 'status': 'failed', 'seeds': [], 'seconds': 0}]}}}
        self.assertIn('| x | 실패 | 0개 | 0초 | - |', rc.markdown(report))
        with tempfile.TemporaryDirectory() as d:
            broken = {'verdict': 'failed', 'stages': {'unit': {'status': 'passed'}}}
            rc.write_report(Path(d), broken)
            self.assertEqual(json.loads((Path(d) / 'report.json').read_text(encoding='utf-8'))['verdict'], 'failed')
            md = (Path(d) / 'report.md').read_text(encoding='utf-8')
        self.assertIn('판정: **failed**', md)
        self.assertIn('표를 만들지 못함', md)


if __name__ == '__main__':
    unittest.main()
