"""[tier] release 표와 main push 계획(--with-release): 긴 검사는 PR 에서 걸리지 않고 main 머지 뒤에만 돈다."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import guards  # noqa: E402

CHECK = '''
[[check]]
name = "{name}"
why = "w"
paths = ["sfc/dq4/tools/dq4ch*event.py"]
run = "uv run python x.py"
needs = ["rom"]
'''
FILES = ['sfc/dq4/guards.toml', 'sfc/dq4/guards.d/main-tier.toml', 'sfc/dq4/tools/dq4ch1event.py']


def load(tier_text, main_extra=''):
    texts = {'sfc/dq4/guards.toml': CHECK.format(name='dq4-short') + CHECK.format(name='dq4-long') + main_extra,
             'sfc/dq4/guards.d/main-tier.toml': tier_text}
    return guards.load(FILES, read=lambda f: texts[f])


class TierTableTest(unittest.TestCase):
    def test_tier_table_moves_a_check_out_of_the_pr(self):
        checks, problems = load('[tier]\nrelease = ["dq4-long"]\n')
        self.assertEqual(problems, [])
        self.assertEqual({c['name']: c.get('tier', 'pr') for c in checks}, {'dq4-short': 'pr', 'dq4-long': 'release'})
        changed = ['sfc/dq4/tools/dq4ch1event.py']
        self.assertEqual([c['name'] for c in guards.triggered(checks, changed)], ['dq4-short'])
        self.assertEqual([c['name'] for c in guards.pending(checks, changed)], ['dq4-short', 'dq4-long'])

    def test_unknown_name_and_bad_shape_are_reported(self):
        _, problems = load('[tier]\nrelease = ["dq4-gone"]\n')
        self.assertTrue(any('dq4-gone' in p for p in problems), problems)
        _, problems = load('[tier]\nnightly = ["dq4-long"]\n')
        self.assertTrue(any('[tier]' in p for p in problems), problems)

    def test_full_paths_skip_release_but_the_body_line_includes_it(self):
        main = '[full]\npaths = ["sfc/dq4/tools/dq4ch1event.py"]\n'
        checks, problems = load('[tier]\nrelease = ["dq4-long"]\n', main)
        self.assertEqual(problems, [])
        changed = ['sfc/dq4/tools/dq4ch1event.py']
        self.assertEqual([c['name'] for c in guards.triggered(checks, changed)], ['dq4-short'])
        self.assertEqual([c['name'] for c in guards.triggered(checks, [], full=True)], ['dq4-short', 'dq4-long'])

    def test_real_main_tier_names_exist_and_are_release(self):
        checks, problems = guards.load(guards.tracked())
        self.assertEqual(problems, [])
        tier = {c['name']: c.get('tier', 'pr') for c in checks}
        import tomllib
        names = tomllib.loads((guards.ROOT / 'sfc/dq4/guards.d/main-tier.toml').read_text(encoding='utf-8'))['tier']['release']
        self.assertEqual({n: tier[n] for n in names}, {n: 'release' for n in names})
        self.assertEqual(len(names), len(set(names)))


class WithReleasePlanTest(unittest.TestCase):
    def plan(self, *extra):
        tool = str(guards.ROOT / 'tools' / 'guards.py')
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / 'out'
            r = subprocess.run([sys.executable, tool, '--base', 'HEAD', '--plan', str(out), *extra],
                               capture_output=True, text=True, cwd=guards.ROOT)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            return dict(line.split('=', 1) for line in out.read_text(encoding='utf-8').split('\n') if line)

    def test_without_the_flag_nothing_changed_means_nothing_runs(self):
        self.assertEqual(self.plan()['guards'], '')

    def test_main_push_runs_every_release_check(self):
        plan = self.plan('--with-release')
        names = set(plan['guards'].split(','))
        checks, _ = guards.load(guards.tracked())
        release = {c['name'] for c in checks if c.get('tier') == 'release'}
        self.assertTrue(release)
        self.assertEqual(names, release)
        self.assertGreater(int(plan['shards']), guards.PR_SHARDS_MAX - 1)

    def test_with_release_needs_plan(self):
        tool = str(guards.ROOT / 'tools' / 'guards.py')
        r = subprocess.run([sys.executable, tool, '--base', 'HEAD', '--with-release'], capture_output=True, text=True,
                           cwd=guards.ROOT)
        self.assertNotEqual(r.returncode, 0)

    def test_main_shards_cap(self):
        cs = [{'name': f'g{i}'} for i in range(40)]
        w = {c['name']: 600.0 for c in cs}
        self.assertEqual(guards.pr_shards(cs, w, most=guards.MAIN_SHARDS_MAX), guards.MAIN_SHARDS_MAX)
        self.assertEqual(guards.pr_shards(cs, w), guards.PR_SHARDS_MAX)


if __name__ == '__main__':
    unittest.main()
