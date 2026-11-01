import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import guards  # noqa: E402

GOOD = '''
[[check]]
name = "dq4-walk"
why = "1장 걷기"
paths = ["sfc/dq4/tools/dq4ch*event.py"]
run = "uv run python x.py"
needs = ["rom"]
'''
FILES = ['sfc/dq4/guards.toml', 'sfc/dq4/tools/dq4ch1event.py', 'sfc/dq4/tools/dq4ch2event.py', 'README.md']


def load(text, files=FILES):
    return guards.load(files, read=lambda f: text)


class GuardsTest(unittest.TestCase):
    def test_good_list_loads(self):
        checks, problems = load(GOOD)
        self.assertEqual(problems, [])
        self.assertEqual(checks[0]['name'], 'dq4-walk')

    def test_bad_entries_are_reported(self):
        _, problems = load(GOOD.replace('dq4-walk', 'Bad_Name').replace('dq4ch*event.py', 'gone.py')
                           .replace('needs = ["rom"]', 'extra = 1'))
        text = '\n'.join(problems)
        self.assertIn('소문자', text)
        self.assertIn('맞는 추적 파일이 없음', text)
        self.assertIn('needs', text)
        self.assertIn('모르는 키 extra', text)

    def test_duplicate_names_across_tracks(self):
        files = FILES + ['sfc/dq5/guards.toml']
        _, problems = guards.load(files, read=lambda f: GOOD)
        self.assertTrue(any('에도 있음' in p for p in problems))

    def test_triggered_by_glob(self):
        checks, _ = load(GOOD)
        self.assertEqual(len(guards.triggered(checks, ['sfc/dq4/tools/dq4ch2event.py'])), 1)
        self.assertEqual(guards.triggered(checks, ['README.md']), [])

    def test_pr_body_lines(self):
        checks, _ = load(GOOD)
        self.assertEqual(guards.body_problems(checks, '- [x] dq4-walk: 통과 (bsnes 27/27)'), [])
        self.assertEqual(guards.body_problems(checks, '- [x] `dq4-walk`: 해당 없음 — 주석만 고침'), [])
        self.assertTrue(guards.body_problems(checks, '본문'))
        self.assertTrue(guards.body_problems(checks, '- [ ] dq4-walk: 통과'))
        self.assertTrue(guards.body_problems(checks, '- [x] dq4-walk: 실패 (snes9x 멈춤)'))
        self.assertTrue(guards.body_problems(checks, '- [x] dq4-walk: 해당 없음'))
        self.assertTrue(guards.body_problems(checks, '- [x] dq4-walk: 아직'))
        self.assertEqual(guards.body_problems(checks, '- [x] dq4-walk: 통과 (실패 0건)'), [])
        self.assertEqual(guards.body_problems(checks, '- [x] dq4-walk: 통과'), [])
        self.assertTrue(guards.body_problems(checks, '- [x] dq4-walk: 통과하지 못함'))
        self.assertTrue(guards.body_problems(checks, '- [x] dq4-walk: 통과 못 함'))
        self.assertTrue(guards.body_problems(checks, '- [x] dq4-walk:\n통과'))
        # 통과 줄과 실패 줄이 함께 있으면 실패
        self.assertTrue(guards.body_problems(checks, '- [x] dq4-walk: 통과\n- [x] dq4-walk: 실패'))

    def test_malformed_lists_are_reported_not_raised(self):
        for text in ('[check]\nname = "x"', 'check = [1, 2]', '[[check]]\nwhy = "no name"'):
            checks, problems = load(text)
            self.assertEqual(checks, [])
            self.assertTrue(problems, text)

    def test_double_star_glob(self):
        self.assertTrue(guards.matches('a/b/x.py', '**/x.py'))
        self.assertTrue(guards.matches('x.py', '**/x.py'))
        self.assertTrue(guards.matches('sfc/dq4/tools/dq4ch1event.py', 'sfc/dq4/**/*.py'))
        self.assertFalse(guards.matches('sfc/dq5/tools/a.py', 'sfc/dq4/**'))


if __name__ == '__main__':
    unittest.main()
