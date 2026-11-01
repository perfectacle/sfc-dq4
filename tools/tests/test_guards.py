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

    def test_unset_env_only_checks_env_names(self):
        needs = ['rom', 'MESENCE', 'LIBDIR', 'dq4cores.py 로 빌드한 코어']
        self.assertEqual(guards.unset_env(needs, {'MESENCE': '/x'}), ['LIBDIR'])
        self.assertEqual(guards.unset_env(needs, {'MESENCE': '/x', 'LIBDIR': ''}), ['LIBDIR'])
        self.assertEqual(guards.unset_env(needs, {'MESENCE': '/x', 'LIBDIR': '/y'}), [])

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


class RunTest(unittest.TestCase):
    def test_rom_of_and_out_dirs(self):
        walk = 'uv run a.py && uv run b.py walk --rom work/ch1/x.sfc --out work/compat-walk'
        self.assertEqual(guards.rom_of(walk), 'work/ch1/x.sfc')
        self.assertEqual(guards.out_dirs(walk), ['work/compat-walk'])
        built = 'uv run build.py --out work/ch1 && uv run c.py --rom work/ch1/x.sfc --out work/hb --jobs 6'
        self.assertIsNone(guards.rom_of(built))
        self.assertEqual(guards.out_dirs(built), ['work/hb'])
        self.assertTrue(guards.builds(built))
        self.assertFalse(guards.builds(walk))
        self.assertEqual(guards.out_dirs('c.py --out /elsewhere --out work/../x'), [])

    def test_review_cases(self):
        window = ('X=$PWD/work/wc/wn.sym uv run m.py build --rom work/ch1/o.sfc --out work/wc/menu.sfc'
                  ' && uv run w.py --rom work/wc/menu.sfc --out work/wc/out')
        self.assertIsNone(guards.rom_of(window))
        self.assertEqual(guards.out_dirs('c.py --out work --out work/cache/guards --out work/ok'), ['work/ok'])
        self.assertEqual(guards.env_names(['rom', '코어(또는 LIBRETRO_BSNES·LIBRETRO_SNES9X)', 'MESENCE']),
                         ['LIBRETRO_BSNES', 'LIBRETRO_SNES9X', 'MESENCE'])

    def test_key_follows_input_files(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'work').mkdir()
            (root / 'work' / 'a.sfc').write_bytes(b'1')
            (root / 'tool').write_bytes(b'v1')
            check = {'run': 'x.py --rom work/a.sfc --out work/o', 'needs': ['TOOL_BIN']}
            env = {'TOOL_BIN': str(root / 'tool')}
            k1 = guards.input_key(check, root, env)
            (root / 'work' / 'o').mkdir()
            (root / 'work' / 'o' / 'junk').write_bytes(b'z')
            self.assertEqual(guards.input_key(check, root, env), k1)
            (root / 'tool').write_bytes(b'v2')
            k2 = guards.input_key(check, root, env)
            self.assertNotEqual(k2, k1)
            (root / 'work' / 'a.sfc').write_bytes(b'2')
            self.assertNotEqual(guards.input_key(check, root, env), k2)

    def test_run_check_caches_passes_only(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            old = guards.cache_dir
            guards.cache_dir = lambda: Path(tmp) / 'cache'
            try:
                logs = Path(tmp)
                ok = {'name': 'ok', 'run': 'true', 'needs': []}
                self.assertEqual(guards.run_check(ok, 30, logs)[0], 'passed')
                status, detail = guards.run_check(ok, 30, logs)
                self.assertEqual(status, 'passed')
                self.assertIn('캐시', detail)
                bad = {'name': 'bad', 'run': 'exit 3', 'needs': []}
                self.assertEqual(guards.run_check(bad, 30, logs)[0], 'failed')
                self.assertEqual(guards.run_check(bad, 30, logs)[0], 'failed')
                slow = {'name': 'slow', 'run': 'sleep 30', 'needs': []}
                self.assertIn('끝나지 않음', guards.run_check(slow, 1, logs)[1])
                manual = {'name': 'm', 'run': 'x.py --party <일행.mss>', 'needs': []}
                self.assertEqual(guards.run_check(manual, 30, logs)[0], 'skipped')
                env = {'name': 'e', 'run': 'true', 'needs': ['GUARDS_TEST_UNSET_VAR']}
                self.assertEqual(guards.run_check(env, 30, logs)[0], 'skipped')
            finally:
                guards.cache_dir = old
