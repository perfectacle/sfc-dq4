import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import main_guard_issue as mgi  # noqa: E402


def report(root, rows, logs=None):
    d = Path(root) / 'guard-shard-pr-1'
    (d / 'logs').mkdir(parents=True)
    (d / 'shard-1.json').write_text(json.dumps({'rows': rows}), encoding='utf-8')
    for name, text in (logs or {}).items():
        (d / 'logs' / f'{name}.log').write_text(text, encoding='utf-8')


def fake(responses):
    calls = []

    def call(a):
        calls.append(a)
        return responses.get(' '.join(a[:2]), '')
    call.calls = calls
    return call


class FailuresTest(unittest.TestCase):
    def test_only_failed_rows_with_their_log_tail(self):
        with tempfile.TemporaryDirectory() as d:
            report(d, [{'name': 'dq4-a', 'status': 'passed', 'detail': '1초'},
                       {'name': 'dq4-b', 'status': 'failed', 'detail': '장면 x 어긋남'}],
                   {'dq4-b': '\n'.join(f'줄{i}' for i in range(100))})
            got = mgi.failures(d)
        self.assertEqual(list(got), ['dq4-b'])
        self.assertEqual(got['dq4-b']['details'], ['장면 x 어긋남'])
        self.assertEqual(got['dq4-b']['log'].splitlines()[-1], '줄99')
        self.assertEqual(len(got['dq4-b']['log'].splitlines()), mgi.LOG_TAIL)


class RangeTest(unittest.TestCase):
    def test_last_green_and_cancelled_between(self):
        runs = [{'headSha': 'd', 'conclusion': ''}, {'headSha': 'c', 'conclusion': 'cancelled'},
                {'headSha': 'b', 'conclusion': 'cancelled'}, {'headSha': 'a', 'conclusion': 'success'},
                {'headSha': 'z', 'conclusion': 'success'}]
        self.assertEqual(mgi.range_from_runs(runs, 'd'), ('a', ['c', 'b']))

    def test_no_green(self):
        self.assertEqual(mgi.range_from_runs([{'headSha': 'd', 'conclusion': ''}], 'd'), (None, []))

    def test_merged_prs(self):
        self.assertEqual(mgi.merged_prs(['Merge pull request #12 from o/x', 'Merge branch main', 'Merge pull request #7 from o/y']),
                         [12, 7])


class RunTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        report(self.tmp.name, [{'name': 'dq4-b', 'status': 'failed', 'detail': '어긋남'}])
        self.runs = json.dumps([{'headSha': 'new' * 3, 'conclusion': ''}, {'headSha': 'mid', 'conclusion': 'cancelled'},
                                {'headSha': 'old', 'conclusion': 'success'}])

    def test_new_guard_failure_opens_an_issue_with_the_range(self):
        gh = fake({'run list': self.runs, 'issue list': '[]', 'issue create': 'https://github.com/o/r/issues/41\n'})
        git = fake({'log --merges': 'Merge pull request #9 from o/a\nMerge pull request #8 from o/b\n'})
        got = mgi.run(gh, git, self.tmp.name, 'new' * 3, 'https://x/run/1')
        self.assertEqual(got, [('dq4-b', 'created', 41)])
        create = next(c for c in gh.calls if c[:2] == ['issue', 'create'])
        self.assertEqual(create[3], '[main 가드] dq4-b 실패')
        text = create[5]
        self.assertIn('#9, #8', text)
        self.assertIn('`mid`', text)
        self.assertIn('https://x/run/1', text)
        self.assertEqual(git.calls[0], ['log', '--merges', '--format=%s', 'old..newnewnew'])

    def test_same_guard_gets_a_comment_on_the_open_issue(self):
        gh = fake({'run list': self.runs, 'issue list': json.dumps([{'number': 5, 'title': '[main 가드] dq4-b 실패'},
                                                                     {'number': 6, 'title': '[main 가드] dq4-bb 실패'}])})
        got = mgi.run(gh, fake({'log --merges': ''}), self.tmp.name, 'new' * 3, 'u')
        self.assertEqual(got, [('dq4-b', 'commented', 5)])
        self.assertTrue(any(c[:3] == ['issue', 'comment', '5'] for c in gh.calls))
        self.assertFalse(any(c[:2] == ['issue', 'create'] for c in gh.calls))

    def test_no_failed_row_still_reports_the_failed_guard_job(self):
        with tempfile.TemporaryDirectory() as d:
            report(d, [{'name': 'dq4-a', 'status': 'passed', 'detail': ''}])
            gh = fake({'run list': self.runs, 'issue list': '[]', 'issue create': 'https://github.com/o/r/issues/3\n'})
            got = mgi.run(gh, fake({'log --merges': ''}), d, 'new' * 3, 'u')
            self.assertEqual(got, [('pr-guards', 'created', 3)])

    def test_dry_run_writes_nothing(self):
        gh = fake({'run list': self.runs, 'issue list': '[]'})
        got = mgi.run(gh, fake({'log --merges': ''}), self.tmp.name, 'new' * 3, 'u', dry=True)
        self.assertEqual(got, [('dq4-b', 'created', None)])
        self.assertFalse(any(c[:2] in (['issue', 'create'], ['issue', 'comment']) for c in gh.calls))


if __name__ == '__main__':
    unittest.main()
