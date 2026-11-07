import json
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import ship  # noqa: E402


def run(cwd, *a):
    return subprocess.run(['git', *a], cwd=cwd, check=True, capture_output=True, text=True).stdout


def args(body, **kw):
    a = dict(title='t', body=Path(body), dry_run=False, watch=True, skip_guards=False, rerun=None, only=None,
             full=False, auto_lists=False, load_wait=0, watch_timeout=100)
    a.update(kw)
    return types.SimpleNamespace(**a)


class Repo:
    """origin(bare) ← 원래 체크아웃 main ← 작업 워크트리 feat/x. 커밋은 서명하지 않는다."""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.origin, self.main, self.wt = t / 'origin.git', t / 'main', t / 'wt'
        run(t, 'init', '-q', '--bare', '-b', 'main', str(self.origin))
        run(t, 'clone', '-q', str(self.origin), str(self.main))
        for k, v in (('user.name', 'u'), ('user.email', 'u@x'), ('commit.gpgsign', 'false'),
                     ('merge.conflictStyle', 'merge')):
            run(self.main, 'config', k, v)
        self.body = t / 'body.md'
        self.body.write_text('본문\n', encoding='utf-8')

    def commit(self, where, files, msg='c'):
        for f, text in files.items():
            p = Path(where) / f
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding='utf-8')
        run(where, 'add', '-A')
        run(where, 'commit', '-q', '-m', msg)

    def start(self, base_files):
        self.commit(self.main, base_files)
        run(self.main, 'push', '-q', 'origin', 'main')
        run(self.main, 'worktree', 'add', '-q', '-b', 'feat/x', str(self.wt), 'origin/main')

    def land(self, files):
        """다른 PR 이 main 에 들어온 것처럼: 원래 체크아웃에서 커밋해 push."""
        self.commit(self.main, files, 'main')
        run(self.main, 'push', '-q', 'origin', 'main')

    def ship(self, gh=None, **kw):
        out = []
        s = ship.Ship(self.wt, args(self.body, **kw), gh=gh, sleep=lambda s: None, out=out.append)
        s.branch = 'feat/x'
        s.token = 'tok'
        return s, out


def fake_gh(responses):
    """명령 앞 두 낱말 → 응답(리스트면 차례로). 부른 명령은 calls 에."""
    calls = []

    def gh(a, env):
        calls.append(a)
        key = ' '.join(a[:2])
        r = responses.get(key, '')
        if isinstance(r, list):
            r = r.pop(0) if len(r) > 1 else r[0]
        code, out = r if isinstance(r, tuple) else (0, r)
        return subprocess.CompletedProcess(a, code, out if isinstance(out, str) else json.dumps(out), '')
    gh.calls = calls
    return gh


class UnionTest(unittest.TestCase):
    def test_list_lines_keep_both_sides(self):
        text = 'a\n<<<<<<< HEAD\n- main 줄\n=======\n- 내 줄\n- main 줄\n>>>>>>> c\nb\n'
        self.assertEqual(ship.union_conflicts(text), 'a\n- main 줄\n- 내 줄\nb\n')

    def test_prose_is_not_resolved(self):
        self.assertIsNone(ship.union_conflicts('<<<<<<< HEAD\n문단 하나\n=======\n문단 둘\n>>>>>>> c\n'))

    def test_diff3_base_is_dropped(self):
        text = '<<<<<<< HEAD\n| a |\n||||||| base\n| 옛 |\n=======\n| b |\n>>>>>>> c\n'
        self.assertEqual(ship.union_conflicts(text), '| a |\n| b |\n')

    def test_unclosed_block(self):
        self.assertIsNone(ship.union_conflicts('<<<<<<< HEAD\n- a\n'))


class RebaseTest(unittest.TestCase):
    def setUp(self):
        self.r = Repo()
        self.addCleanup(self.r.tmp.cleanup)
        self.r.start({'notes.txt': '하나\n', 'README.md': '# 목록\n\n- 첫 줄\n'})

    def test_conflict_stops_and_leaves_rebase(self):
        self.r.commit(self.r.wt, {'notes.txt': '내 것\n'})
        self.r.land({'notes.txt': 'main 것\n'})
        s, out = self.r.ship()
        with self.assertRaises(ship.Stop) as e:
            s.rebase()
        self.assertEqual(e.exception.step, 'rebase')
        self.assertIn('notes.txt', e.exception.reason)
        self.assertIn('  충돌: notes.txt', out)
        gitdir = Path(run(self.r.wt, 'rev-parse', '--absolute-git-dir').strip())
        self.assertTrue((gitdir / 'rebase-merge').exists() or (gitdir / 'rebase-apply').exists())

    def test_list_conflict_needs_auto_lists(self):
        self.r.commit(self.r.wt, {'README.md': '# 목록\n\n- 첫 줄\n- 내 줄\n'})
        self.r.land({'README.md': '# 목록\n\n- 첫 줄\n- main 줄\n'})
        s, _ = self.r.ship()
        with self.assertRaises(ship.Stop):
            s.rebase()
        run(self.r.wt, 'rebase', '--abort')
        s, out = self.r.ship(auto_lists=True)
        s.rebase()
        text = (self.r.wt / 'README.md').read_text(encoding='utf-8')
        self.assertEqual(text, '# 목록\n\n- 첫 줄\n- main 줄\n- 내 줄\n')
        self.assertEqual(run(self.r.wt, 'rev-list', '--count', 'HEAD..origin/main').strip(), '0')
        self.assertIn('README.md', out[-1])

    def test_auto_lists_refuses_prose_in_readme(self):
        self.r.commit(self.r.wt, {'README.md': '# 목록\n\n내 문단\n'})
        self.r.land({'README.md': '# 목록\n\nmain 문단\n'})
        s, _ = self.r.ship(auto_lists=True)
        with self.assertRaises(ship.Stop) as e:
            s.rebase()
        self.assertIn('README.md', e.exception.reason)

    def test_leftover_marker_is_caught(self):
        self.r.commit(self.r.wt, {'a.md': 'x\n<<<<<<< HEAD\ny\n'})
        s, _ = self.r.ship()
        with self.assertRaises(ship.Stop) as e:
            s.rebase()
        self.assertIn('충돌 표시', e.exception.reason)

    def test_dry_run_predicts_conflict_without_moving(self):
        self.r.commit(self.r.wt, {'notes.txt': '내 것\n'})
        self.r.land({'notes.txt': 'main 것\n'})
        before = run(self.r.wt, 'rev-parse', 'HEAD')
        s, out = self.r.ship(dry_run=True)
        s.rebase()
        self.assertIn('충돌 예상: notes.txt', out[-1])
        self.assertEqual(run(self.r.wt, 'rev-parse', 'HEAD'), before)


class JournalTest(unittest.TestCase):
    def test_renames_against_main_and_branch(self):
        main = ['sfc/dq4/journal/2026-11-07-01-a.md', 'sfc/dq4/journal/2026-11-07-02-b.md',
                'sfc/dq5/journal/2026-11-07-05-z.md']
        added = ['sfc/dq4/journal/2026-11-07-02-mine.md', 'sfc/dq4/journal/2026-11-07-NN-later.md',
                 'sfc/dq5/journal/2026-11-07-01-ok.md', 'sfc/dq4/journal/2026-11-08-01-new-day.md']
        self.assertEqual(ship.journal_renames(added, main), [
            ('sfc/dq4/journal/2026-11-07-02-mine.md', 'sfc/dq4/journal/2026-11-07-03-mine.md'),
            ('sfc/dq4/journal/2026-11-07-NN-later.md', 'sfc/dq4/journal/2026-11-07-04-later.md')])

    def test_fc_and_sfc_dq4_share_numbers(self):
        main = ['fc/dq4/journal/2026-11-07-01-a.md']
        self.assertEqual(ship.journal_renames(['sfc/dq4/journal/2026-11-07-01-b.md'], main),
                         [('sfc/dq4/journal/2026-11-07-01-b.md', 'sfc/dq4/journal/2026-11-07-02-b.md')])

    def test_number_past_99(self):
        main = [f'nds/dq4/journal/2026-11-07-{n:02d}-a.md' for n in range(1, 100)]
        self.assertEqual(ship.journal_renames(['nds/dq4/journal/2026-11-07-01-b.md'], main)[0][1],
                         'nds/dq4/journal/2026-11-07-100-b.md')

    def test_sort_lists(self):
        text = ('x\n- [2026-11-07-02: b](journal/2026-11-07-02-b.md)\n'
                '- [2026-11-07-01: a](journal/2026-11-07-01-a.md)\ny\n')
        self.assertEqual(ship.sort_journal_lists(text), 'x\n- [2026-11-07-01: a](journal/2026-11-07-01-a.md)\n'
                         '- [2026-11-07-02: b](journal/2026-11-07-02-b.md)\ny\n')

    def test_repo_rename_after_rebase(self):
        r = Repo()
        self.addCleanup(r.tmp.cleanup)
        r.start({'sfc/dq4/README.md': '# dq4\n\n## 해킹 일지\n\n'})
        r.commit(r.wt, {'sfc/dq4/journal/2026-11-07-01-mine.md': '# 2026-11-07-01: 내 것\n\n본문\n',
                        'sfc/dq4/README.md': '# dq4\n\n## 해킹 일지\n\n'
                                             '- [2026-11-07-01: 내 것](journal/2026-11-07-01-mine.md)\n'})
        r.land({'sfc/dq4/journal/2026-11-07-01-other.md': '# 2026-11-07-01: 남의 것\n',
                'sfc/dq4/README.md': '# dq4\n\n## 해킹 일지\n\n'
                                     '- [2026-11-07-01: 남의 것](journal/2026-11-07-01-other.md)\n'})
        s, out = r.ship(auto_lists=True)
        s.rebase()
        s.journal()
        new = r.wt / 'sfc/dq4/journal/2026-11-07-02-mine.md'
        self.assertTrue(new.is_file())
        self.assertFalse((r.wt / 'sfc/dq4/journal/2026-11-07-01-mine.md').exists())
        self.assertTrue(new.read_text(encoding='utf-8').startswith('# 2026-11-07-02: 내 것'))
        self.assertEqual((r.wt / 'sfc/dq4/README.md').read_text(encoding='utf-8'),
                         '# dq4\n\n## 해킹 일지\n\n- [2026-11-07-01: 남의 것](journal/2026-11-07-01-other.md)\n'
                         '- [2026-11-07-02: 내 것](journal/2026-11-07-02-mine.md)\n')
        self.assertIn('일지 순번', run(r.wt, 'log', '-1', '--format=%s'))
        self.assertEqual(run(r.wt, 'status', '--porcelain').strip(), '')


class BodyTest(unittest.TestCase):
    LINES = ['- [x] dq4-a: 통과 (10초)']

    def test_append_section_and_robot(self):
        out = ship.build_body('## 무엇\n\n바꿈\n', self.LINES)
        self.assertEqual(out, f'## 무엇\n\n바꿈\n\n## 가드\n\n- [x] dq4-a: 통과 (10초)\n\n{ship.ROBOT}\n')

    def test_replace_existing_section_in_place(self):
        body = f'## 무엇\n\n바꿈\n\n## 가드\n\n가드: 전체\n- [x] old: 통과\n\n## 남은 것\n\n없음\n\n{ship.ROBOT}\n'
        out = ship.build_body(body, self.LINES)
        self.assertEqual(out, '## 무엇\n\n바꿈\n\n## 가드\n\n가드: 전체\n\n- [x] dq4-a: 통과 (10초)\n\n'
                              f'## 남은 것\n\n없음\n\n{ship.ROBOT}\n')
        self.assertEqual(ship.build_body(out, self.LINES), out)

    def test_no_guards(self):
        self.assertIn('## 가드\n\n걸리는 실행 검사 없음.\n', ship.build_body('x\n', []))


class PushTest(unittest.TestCase):
    def test_decision(self):
        self.assertEqual(ship.remote_decision(True, []), 'force')
        self.assertEqual(ship.remote_decision(True, [{'number': 1, 'state': 'OPEN'}]), 'force')
        self.assertEqual(ship.remote_decision(True, [{'number': 1, 'state': 'MERGED'}]), 'rename')
        self.assertEqual(ship.remote_decision(False, [{'number': 1, 'state': 'OPEN'}]), 'rename')
        self.assertEqual(ship.remote_decision(False, []), 'rename')
        self.assertEqual(ship.free_name('feat/x', {'feat/x': 1, 'feat/x-2': 1}), 'feat/x-3')

    def setUp(self):
        self.r = Repo()
        self.addCleanup(self.r.tmp.cleanup)
        self.r.start({'a.txt': 'a\n'})
        self.r.commit(self.r.wt, {'b.txt': 'b\n'})

    def test_someone_elses_merged_branch_gets_new_name(self):
        run(self.r.main, 'push', '-q', 'origin', 'main:refs/heads/feat/x')
        s, out = self.r.ship(gh=fake_gh({'pr list': [[{'number': 7, 'state': 'MERGED'}]]}))
        s.push()
        self.assertEqual(s.branch, 'feat/x-2')
        self.assertEqual(run(self.r.wt, 'rev-parse', '--abbrev-ref', 'HEAD').strip(), 'feat/x-2')
        self.assertIn('feat/x-2', run(self.r.origin, 'branch', '--list', 'feat/x-2'))

    def test_own_branch_after_rebase_is_force_pushed(self):
        run(self.r.wt, 'push', '-q', 'origin', 'feat/x')
        self.r.land({'c.txt': 'c\n'})
        run(self.r.wt, 'fetch', '-q', 'origin')
        run(self.r.wt, 'rebase', '-q', 'origin/main')
        s, out = self.r.ship(gh=fake_gh({'pr list': [[{'number': 7, 'state': 'OPEN'}]]}))
        s.push()
        self.assertEqual(s.branch, 'feat/x')
        self.assertIn('--force-with-lease', out[-1])
        self.assertEqual(run(self.r.origin, 'rev-parse', 'feat/x'), run(self.r.wt, 'rev-parse', 'HEAD'))


class GuardsPickTest(unittest.TestCase):
    HIT = [{'name': 'dq4-a', 'paths': ['sfc/dq4/tools/a.py'], 'full_paths': ['uv.lock']},
           {'name': 'dq4-b', 'paths': ['sfc/dq4/tools/b*.py'], 'full_paths': []}]
    STORED = {'dq4-a': '- [x] dq4-a: 통과 (1초)', 'dq4-b': '- [x] dq4-b: 통과 (2초)'}

    def test_md_only_rebase_skips(self):
        self.assertEqual(ship.guards_to_run(self.HIT, self.STORED, ['README.md', 'docs/todo.md']), [])

    def test_touched_paths_rerun(self):
        self.assertEqual(ship.guards_to_run(self.HIT, self.STORED, ['sfc/dq4/tools/b2.py']), ['dq4-b'])
        self.assertEqual(ship.guards_to_run(self.HIT, self.STORED, ['uv.lock']), ['dq4-a'])

    def test_missing_or_failed_rerun(self):
        stored = {'dq4-a': '- [ ] dq4-a: 실패 (종료 코드 1)'}
        self.assertEqual(ship.guards_to_run(self.HIT, stored, []), ['dq4-a', 'dq4-b'])

    def test_edited_run_line(self):
        self.assertEqual(ship.guards_to_run(self.HIT, self.STORED, ['sfc/dq4/guards.toml'], {'dq4-a'}), ['dq4-a'])

    def test_parse_output(self):
        out = ('검사 2개를 2개씩 돌림\n  dq4-a: passed (3초)\n\nPR 본문 결과 줄:\n'
               '- [x] dq4-a: 통과 (3초)\n- [ ] dq4-b: 실패 (종료 코드 1, 로그 work/guards/dq4-b.log)\n')
        lines = ship.parse_guards(out)
        self.assertTrue(ship.passed(lines['dq4-a']))
        self.assertFalse(ship.passed(lines['dq4-b']))
        self.assertTrue(ship.STATUS.match('  dq4-a: passed (3초)'))

    def test_skip_guards_refused_when_hit(self):
        r = Repo()
        self.addCleanup(r.tmp.cleanup)
        r.start({'a.txt': 'a\n'})
        s, _ = r.ship(skip_guards=True)
        s.hit = lambda full: self.HIT
        with self.assertRaises(ship.Stop) as e:
            s.guards()
        self.assertIn('dq4-a', e.exception.reason)
        s.hit = lambda full: []
        s.guards()
        self.assertEqual(s.lines, {})

    def test_state_reused_across_md_only_change(self):
        r = Repo()
        self.addCleanup(r.tmp.cleanup)
        r.start({'a.txt': 'a\n'})
        s, out = r.ship()
        s.hit = lambda full: self.HIT
        s.save_state(s.head(), self.STORED)
        r.commit(r.wt, {'README.md': 'x\n'})
        s.guards()
        self.assertEqual(s.lines, self.STORED)
        self.assertIn('앞 결과', out[-1])


class TestsForTest(unittest.TestCase):
    SOURCES = {
        'sfc/dq4/tools/a.py': 'import b\n',
        'sfc/dq4/tools/b.py': 'X = open("tbl.toml")\n',
        'sfc/dq4/tools/c.py': 'pass\n',
        'sfc/dq4/tools/test_a.py': 'import a\n',
        'sfc/dq4/tools/test_c.py': 'subprocess.run(["c.py"])\n',
        'sfc/dq5/tools/m.py': '',
        'sfc/dq5/tools/tests/test_m.py': 'import m\n',
    }
    DIRS = ['sfc/dq4/tools', 'sfc/dq5/tools/tests']

    def test_transitive_import(self):
        self.assertEqual(ship.tests_for({'sfc/dq4/tools/b.py'}, self.DIRS, self.SOURCES), {'sfc/dq4/tools': ['test_a']})

    def test_data_file_and_script_name(self):
        self.assertEqual(ship.tests_for({'sfc/dq4/tools/tbl.toml', 'sfc/dq4/tools/c.py'}, self.DIRS, self.SOURCES),
                         {'sfc/dq4/tools': ['test_a', 'test_c']})

    def test_tests_folder_sees_parent_modules(self):
        self.assertEqual(ship.tests_for({'sfc/dq5/tools/m.py'}, self.DIRS, self.SOURCES), {'sfc/dq5/tools/tests': ['test_m']})

    def test_lock_runs_everything_and_md_nothing(self):
        self.assertEqual(ship.tests_for({'uv.lock'}, self.DIRS, self.SOURCES),
                         {'sfc/dq4/tools': ['test_a', 'test_c'], 'sfc/dq5/tools/tests': ['test_m']})
        self.assertEqual(ship.tests_for({'README.md'}, self.DIRS, self.SOURCES), {})

    def test_ci_matrix_dirs(self):
        ci = (Path(__file__).resolve().parents[2] / '.github' / 'workflows' / 'ci.yml').read_text(encoding='utf-8')
        dirs = ship.test_dirs(ci)
        self.assertIn('tools/tests', dirs)
        self.assertIn('sfc/dq4/tools', dirs)


class WatchTest(unittest.TestCase):
    def setUp(self):
        self.r = Repo()
        self.addCleanup(self.r.tmp.cleanup)
        self.r.start({'a.txt': 'a\n'})

    def view(self, **kw):
        v = {'state': 'OPEN', 'mergeable': 'MERGEABLE', 'mergeStateStatus': 'BLOCKED', 'statusCheckRollup': []}
        v.update(kw)
        return v

    def test_ci_failure_prints_log_tail(self):
        bad = {'name': 'test (common)', 'status': 'COMPLETED', 'conclusion': 'FAILURE',
               'detailsUrl': 'https://github.com/o/r/actions/runs/1/job/42'}
        gh = fake_gh({'pr view': [self.view(), self.view(statusCheckRollup=[bad])],
                      'run view': 'a\nAssertionError: 틀림\n'})
        s, out = self.r.ship(gh=gh)
        s.pr = 5
        with self.assertRaises(ship.Stop) as e:
            s.watch()
        self.assertIn('test (common)', e.exception.reason)
        self.assertIn(['run', 'view', '--job', '42', '--log-failed'], gh.calls)
        self.assertIn('    AssertionError: 틀림', out)

    def test_conflict_reruns_cycle_then_merged(self):
        gh = fake_gh({'pr view': [self.view(mergeable='CONFLICTING'), self.view(state='MERGED')]})
        s, out = self.r.ship(gh=gh)
        s.pr = 5
        cycles = []
        s.cycle = lambda: cycles.append(1)
        s.watch()
        self.assertEqual(cycles, [1])
        self.assertIn('[watch] MERGED', out)

    def test_merges_by_hand_when_auto_off(self):
        ok = {'name': 'ci-ok', 'status': 'COMPLETED', 'conclusion': 'SUCCESS'}
        gh = fake_gh({'pr view': [self.view(mergeStateStatus='CLEAN', statusCheckRollup=[ok]), self.view(state='MERGED')],
                      'pr merge': ''})
        s, _ = self.r.ship(gh=gh)
        s.pr, s.auto = 5, False
        s.watch()
        self.assertIn(['pr', 'merge', '5', '--merge'], gh.calls)

    def test_cleanup_refuses_dirty_worktree(self):
        (self.r.wt / 'a.txt').write_text('바뀜\n', encoding='utf-8')
        s, _ = self.r.ship()
        with self.assertRaises(ship.Stop) as e:
            s.cleanup()
        self.assertIn('a.txt', e.exception.reason)
        self.assertTrue(self.r.wt.is_dir())

    def test_cleanup_removes_worktree_and_branch(self):
        s, out = self.r.ship(gh=fake_gh({}))
        s.cleanup()
        self.assertFalse(self.r.wt.exists())
        self.assertEqual(run(self.r.main, 'branch', '--list', 'feat/x').strip(), '')


if __name__ == '__main__':
    unittest.main()
