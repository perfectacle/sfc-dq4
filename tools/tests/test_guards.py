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

    def test_groups_add_named_paths(self):
        text = GOOD.replace('paths = ["sfc/dq4/tools/dq4ch*event.py"]', 'paths = []\ngroups = ["events"]') + \
            '\n[groups]\nevents = ["sfc/dq4/tools/dq4ch1event.py"]\n'
        checks, problems = load(text)
        self.assertEqual(problems, [])
        self.assertEqual(len(guards.triggered(checks, ['sfc/dq4/tools/dq4ch1event.py'])), 1)
        self.assertEqual(guards.triggered(checks, ['sfc/dq4/tools/dq4ch2event.py']), [])
        _, problems = load(text.replace('groups = ["events"]', 'groups = ["nope"]'))
        self.assertTrue(any('nope' in p for p in problems), problems)
        _, problems = load(text.replace('events = ["sfc/dq4/tools/dq4ch1event.py"]', 'events = ["gone.py"]'))
        self.assertTrue(any('gone.py' in p for p in problems), problems)
        _, problems = load(text.replace('groups = ["events"]', ''))
        self.assertTrue(any('paths 가 비어 있음' in p for p in problems), problems)

    def test_edited_run_or_needs_triggers_the_check(self):
        """guards.toml 에서 그 검사의 run·needs 가 바뀌거나 새로 생기면 paths 와 상관없이 걸린다. why 만 바뀌면 걸리지 않는다."""
        other = GOOD.replace('dq4-walk', 'dq4-other')
        base = GOOD + other
        self.assertEqual(guards.edited_checks(base, base), set())
        self.assertEqual(guards.edited_checks(base, base.replace('x.py', 'x.py --maps 1', 1)), {'dq4-walk'})
        self.assertEqual(guards.edited_checks(base, GOOD + other.replace('["rom"]', '["rom", "MESENCE"]')),
                         {'dq4-other'})
        self.assertEqual(guards.edited_checks(base, base.replace('1장 걷기', '설명만 바꿈')), set())
        self.assertEqual(guards.edited_checks(GOOD, base), {'dq4-other'})
        self.assertEqual(guards.edited_checks(base, GOOD), set())
        self.assertEqual(guards.edited_checks('', GOOD), {'dq4-walk'})
        checks, _ = load(base)
        self.assertEqual([c['name'] for c in guards.triggered(checks, ['README.md'], {'dq4-other'})], ['dq4-other'])

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

    def test_key_leaves_out_files_that_cannot_change_the_result(self):
        """추적 파일 가운데 문서·검사 목록·에이전트·CI 설정·일지·단위 테스트는 검사 명령의 결과에 닿지 않아 키에서 뺀다.
        도구 코드는 넣는다. 명령이 단위 테스트를 부르면 테스트가 무엇을 읽을지 몰라 .md 만 뺀다."""
        from unittest import mock
        base = {'sfc/dq4/tools/dq4x.py': 'a1', 'sfc/dq4/guards.toml': 'b1', 'sfc/dq4/journal/x.png': 'c1',
                '.github/workflows/ci.yml': 'd1', '.agents/skills/x/y.txt': 'e1', 'sfc/dq4/tools/test_dq4x.py': 'f1',
                'tools/tests/test_x.py': 'g1', 'README.md': 'h1', 'sfc/dq4/images/x.png': 'i1'}

        def key(files, run='uv run python sfc/dq4/tools/dq4x.py --out work/o'):
            listing = ''.join(f'100644 {sha} 0\t{f}\n' for f, sha in files.items())
            with mock.patch.object(guards, 'git', lambda *a: listing if a[0] == 'ls-files' else ''):
                return guards.input_key({'run': run, 'needs': []}, Path('/nonexistent'), {})
        k = key(base)
        for f in ('sfc/dq4/guards.toml', 'sfc/dq4/journal/x.png', '.github/workflows/ci.yml', '.agents/skills/x/y.txt',
                  'sfc/dq4/tools/test_dq4x.py', 'tools/tests/test_x.py', 'README.md'):
            self.assertEqual(key(dict(base, **{f: 'zz'})), k, f)
        for f in ('sfc/dq4/tools/dq4x.py', 'sfc/dq4/images/x.png'):
            self.assertNotEqual(key(dict(base, **{f: 'zz'})), k, f)
        tests = 'uv run --locked python -m unittest discover -s sfc/dq4/tools -p test_dq4x.py'
        kt = key(base, tests)
        for f in ('sfc/dq4/tools/test_dq4x.py', 'sfc/dq4/guards.toml', 'sfc/dq4/journal/x.png'):
            self.assertNotEqual(key(dict(base, **{f: 'zz'}), tests), kt, f)
        self.assertEqual(key(dict(base, **{'README.md': 'zz'}), tests), kt)

    def test_key_follows_mesence_settings(self):
        """MESENCE 를 쓰는 검사는 MesenCE 사용자 설정 파일이 바뀌면(콜백 시간 제한 등) 옛 통과를 쓰지 않는다. 설정 파일을
        못 찾으면 키가 없다(None): 캐시를 읽지도 쓰지도 않는다."""
        import tempfile
        from unittest import mock
        import mesence_settings
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'Mesen').write_bytes(b'emu')
            settings = root / 'settings.json'
            settings.write_text('{"ScriptTimeout": 1}')
            check = {'run': 'x.py --out work/o', 'needs': ['MESENCE']}
            env = {'MESENCE': str(root / 'Mesen')}
            with mock.patch.object(guards, 'git', lambda *a: ''), \
                    mock.patch.object(mesence_settings, 'settings_path', lambda m: settings), \
                    mock.patch.object(guards, 'settings_digest', mesence_settings.settings_digest):
                k1 = guards.input_key(check, root, env)
                self.assertEqual(guards.input_key(check, root, env), k1)
                settings.write_text('{"ScriptTimeout": 10}')
                k2 = guards.input_key(check, root, env)
                self.assertNotEqual(k2, k1)
                settings.unlink()
                self.assertIsNone(guards.input_key(check, root, env))
                self.assertEqual(guards.input_key({'run': 'x.py', 'needs': []}, root, env),
                                 guards.input_key({'run': 'x.py', 'needs': []}, root, {}))

    def test_no_key_means_no_cache(self):
        """키를 만들 수 없는 검사(MESENCE 설정 파일 없음)는 통과해도 캐시에 적지 않고, 다음에도 다시 돈다."""
        import tempfile
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            cache, logs = Path(tmp) / 'cache', Path(tmp) / 'logs'
            logs.mkdir()
            check = {'name': 'x', 'run': 'true', 'needs': []}
            with mock.patch.object(guards, 'input_key', return_value=None), \
                    mock.patch.object(guards, 'cache_dir', return_value=cache):
                for _ in range(2):
                    result, detail = guards.run_check(check, 60, logs)
                    self.assertEqual(result, 'passed')
                    self.assertNotIn('캐시', detail)
            self.assertFalse(cache.exists())

    def test_runs_tests(self):
        """명령이 단위 테스트를 부르는지: unittest·pytest, 또는 test_*.py·tests/ 의 파일을 바로 돌림."""
        for run in ('uv run python -m unittest discover -s sfc/dq4/tools -p test_x.py', 'uv run pytest sfc',
                    'uv run python sfc/dq4/tools/test_dq4x.py', 'python tools/tests/run_all.py',
                    'cd sfc && python test_y.py -v'):
            self.assertTrue(guards.runs_tests(run), run)
        for run in ('uv run python sfc/dq4/tools/dq4build.py --out work/ch1', 'python sfc/dq4/tools/dq4latest.py',
                    'python my_tests_helper.py'):
            self.assertFalse(guards.runs_tests(run), run)
        self.assertTrue(guards.is_input('sfc/dq4/tools/test_dq4x.py', 'uv run python sfc/dq4/tools/test_dq4x.py'))
        self.assertFalse(guards.is_input('sfc/dq4/tools/test_dq4x.py', 'uv run python sfc/dq4/tools/dq4x.py'))

    def test_mesence_checks_watch_the_settings_module(self):
        """needs 에 MESENCE 가 있는 실행 검사는 paths 에 tools/mesence_settings.py 가 있다. 그 파일만 고친 PR 도 그 검사들을
        고르게 한다(설정 자리를 잘못 고치면 키가 설정을 놓친다)."""
        import tomllib
        root = Path(__file__).resolve().parents[2]
        found = 0
        for toml in sorted(root.glob('*/*/guards.toml')):
            for c in tomllib.loads(toml.read_text(encoding='utf-8'))['check']:
                if 'MESENCE' in guards.env_names(c.get('needs', [])):
                    found += 1
                    self.assertIn('tools/mesence_settings.py', c['paths'], f'{toml}: {c["name"]}')
        self.assertGreater(found, 0)

    def test_hash_path_dirs_by_stat_and_big_files_by_stat(self):
        import hashlib
        import os
        import tempfile

        def key(p):
            h = hashlib.sha256()
            guards.hash_path(h, p)
            return h.hexdigest()

        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / 'assets'
            (d / 'sub').mkdir(parents=True)
            f = d / 'sub' / 'a.bin'
            f.write_bytes(b'abc')
            os.utime(f, ns=(1, 1_000_000_000))
            k1 = key(d)
            f.write_bytes(b'xyz')                       # 같은 크기, 다른 내용
            os.utime(f, ns=(1, 1_000_000_000))
            self.assertEqual(key(d), k1)                # 폴더는 내용을 읽지 않음
            os.utime(f, ns=(1, 2_000_000_000))
            self.assertNotEqual(key(d), k1)
            k2 = key(d)
            (d / 'b.bin').write_bytes(b'')
            self.assertNotEqual(key(d), k2)
            small = key(f)
            f.write_bytes(b'abc')
            os.utime(f, ns=(1, 2_000_000_000))
            self.assertNotEqual(key(f), small)          # 작은 파일은 내용
            old = guards.BIG_FILE
            guards.BIG_FILE = 2
            try:
                big = key(f)
                f.write_bytes(b'xyz')
                os.utime(f, ns=(1, 2_000_000_000))
                self.assertEqual(key(f), big)           # 큰 파일은 크기·mtime
                os.utime(f, ns=(1, 3_000_000_000))
                self.assertNotEqual(key(f), big)
            finally:
                guards.BIG_FILE = old

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
                # --no-cache: 통과 캐시를 건너뛰고, 검사 안의 캐시도 모두 끈다(장면·빌드 단계, 상태는 로그 폴더 아래 빈 곳)
                self.assertNotIn('캐시', guards.run_check(ok, 30, logs, no_cache=True)[1])
                gate = {'name': 'gate', 'needs': [],
                        'run': f'test "$DQ4_READSET" = off && test "$DQ4_BUILD_CACHE" = off && '
                               f'test "$DQ4_STATES_CACHE" = "{logs / "states"}"'}
                self.assertEqual(guards.run_check(gate, 30, logs, no_cache=True)[0], 'passed')
                self.assertEqual(guards.run_check({**gate, 'name': 'plain'}, 30, logs)[0], 'failed')
            finally:
                guards.cache_dir = old



class BuiltCacheTest(unittest.TestCase):
    """입력 키가 빗나가도 빌드 결과와 검사 단계가 실행한 함수·연 파일이 같으면 검사 단계를 건너뛴다."""

    HELPER = "def used():\n    return 1\n\n\ndef unused():\n    return 'a'\n"
    CHECK = ("import helper, sys\nfrom pathlib import Path\n\n\n"
             "def main():\n    assert helper.used() == 1\n    return 0 if Path(sys.argv[2]).read_text() else 1\n\n\n"
             "sys.exit(main())\n")

    def setUp(self):
        import subprocess
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'repo'
        self.root.mkdir()
        self.files = {
            'src.txt': 'A',
            'build.py': "import sys; open(sys.argv[2] + '/out.txt', 'w').write(open('src.txt').read())\n",
            'helper.py': self.HELPER,
            'check.py': self.CHECK,
            'other.py': 'X = 1\n',
        }
        for name, text in self.files.items():
            (self.root / name).write_text(text)
        run = lambda *a: subprocess.run(a, cwd=self.root, check=True, capture_output=True)
        run('git', 'init', '-q')
        run('git', 'add', '.')
        run('git', '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-qm', 'x')
        self.old = guards.ROOT, guards.cache_dir, guards.CHECK_STAGE
        guards.ROOT = self.root
        guards.cache_dir = lambda: Path(self.tmp.name) / 'cache'
        # 시험은 uv 없이 지금 Python 으로 검사 단계를 돌린다
        py = sys.executable
        guards.CHECK_STAGE = __import__('re').compile(r'^\s*' + __import__('re').escape(py) + r'\s+(?P<script>[^\s-]\S*\.py)(\s|$)')
        self.logs = Path(self.tmp.name) / 'logs'
        self.logs.mkdir()
        (self.root / 'work').mkdir()
        self.check = {'name': 'c', 'needs': [],
                      'run': f'mkdir -p work/b && {py} build.py --out work/b && {py} check.py --rom work/b/out.txt'}

    def tearDown(self):
        guards.ROOT, guards.cache_dir, guards.CHECK_STAGE = self.old
        self.tmp.cleanup()

    def edit(self, name, text):
        (self.root / name).write_text(text)

    def detail(self, check=None):
        status, detail = guards.run_check(check or self.check, 60, self.logs)
        self.assertEqual(status, 'passed', detail)
        return detail

    def skipped(self):
        return '빌드 결과와 검사 코드가 같아' in self.detail()

    def test_split_needs_a_build_stage_plain_and_a_uv_python_check(self):
        guards.CHECK_STAGE = self.old[2]
        self.assertEqual(guards.split_built({'run': 'a --out work/x && X=$PWD/y uv run --locked python b.py --rom r'}),
                         ('a --out work/x ', ' X=$PWD/y uv run --locked python b.py --rom r'))
        self.assertEqual(guards.CHECK_STAGE.match(' uv run --locked python b.py --rom r')['script'], 'b.py')
        for run in ('uv run --locked python b.py --rom rom/r', 'a --out work/x && cd y && uv run --locked python b',
                    'a --out work/x; uv run --locked python b', 'a --out work/x && uv run --locked python b || c',
                    'a --out work/x && uv run --locked python b | tee l', 'a --out work/x & uv run --locked python b',
                    'a --out work/x\nexport A=1 && uv run --locked python b', 'a --out work/x && grep x b.py',
                    'a --out work/x && uv run --locked python $(echo b)', 'a --out work/x && python -m unittest',
                    'a --out work/x && uv run --locked python -I b.py', 'a --out "work/x y" && uv run --locked python b.py'):
            self.assertIsNone(guards.split_built({'run': run}), run)

    def test_unexecuted_function_or_unrelated_file_change_skips_the_check(self):
        self.assertFalse(self.skipped())
        self.edit('other.py', 'X = 2\n')
        self.assertTrue(self.skipped())
        self.edit('helper.py', self.HELPER.replace("'a'", "'b'"))
        self.assertTrue(self.skipped())
        # 줄만 밀려도 지문은 같다
        self.edit('helper.py', '\n\n' + self.HELPER)
        self.assertTrue(self.skipped())
        # 빌드 도구를 고쳐도 결과가 같으면 건너뛴다
        self.edit('build.py', self.files['build.py'] + '# 같은 결과\n')
        self.assertTrue(self.skipped())

    def test_executed_code_change_runs_the_check(self):
        self.detail()
        self.edit('helper.py', self.HELPER.replace('return 1', 'return int(1)'))
        self.assertFalse(self.skipped())
        self.edit('other.py', 'X = 9\n')
        self.assertTrue(self.skipped())
        # 모듈 수준 코드(함수 정의 꼴·기본값 포함)
        self.edit('helper.py', self.HELPER.replace('def unused():', 'def unused(x=2):'))
        self.assertFalse(self.skipped())

    def test_build_output_or_data_read_change_runs_the_check(self):
        self.detail()
        self.edit('src.txt', 'B')
        self.assertFalse(self.skipped())
        self.edit('src.txt', 'A')
        self.edit('other.py', 'X = 10\n')
        self.assertTrue(self.skipped())

    def test_non_python_tracked_input_or_new_py_name_runs_the_check(self):
        import subprocess
        self.detail()
        self.edit('data.toml', 'a = 1\n')
        subprocess.run(['git', 'add', 'data.toml'], cwd=self.root, check=True)
        self.assertFalse(self.skipped())
        self.edit('json.py', 'X = 1\n')
        subprocess.run(['git', 'add', 'json.py'], cwd=self.root, check=True)
        self.assertFalse(self.skipped())

    def test_data_read_of_a_py_file_tracks_its_whole_content(self):
        self.edit('check.py', self.CHECK.replace('assert helper.used() == 1', "assert Path('helper.py').read_text()"))
        self.detail()
        self.edit('helper.py', self.HELPER.replace("'a'", "'b'"))
        self.assertFalse(self.skipped())

    def test_listed_folder_change_runs_the_check(self):
        import os
        os.mkdir(self.root / 'd')
        self.edit('check.py', self.CHECK.replace('assert helper.used() == 1', "assert not sorted(Path('d').iterdir())"))
        self.detail()
        self.edit('other.py', 'X = 8\n')
        self.assertTrue(self.skipped())
        self.edit('d/new.txt', '')
        status, _ = guards.run_check(self.check, 60, self.logs)
        self.assertEqual(status, 'failed')

    def test_children_the_tracer_cannot_see_keep_no_entry(self):
        py = sys.executable
        for child in ([py, '-I', '-c', 'pass'], ['env', py, '-c', 'pass'], ['grep', '-q', 'x', 'helper.py']):
            with self.subTest(child=child):
                self.edit('check.py', f"import subprocess\nsubprocess.run({child!r})\n")
                self.detail()
                self.assertIn('?', (self.logs / 'c.reads').read_text().split())
                self.assertFalse(self.skipped())

    def test_reads_of_the_check_output_folder_are_not_inputs(self):
        py = sys.executable
        self.edit('check.py', "import os, sys\nos.makedirs('work/o', exist_ok=True)\n"
                              "open('work/o/r.txt', 'w').write(str(os.getpid()))\nopen('work/o/r.txt').read()\n")
        check = {**self.check, 'run': self.check['run'].replace('--rom work/b/out.txt', '--rom work/b/out.txt --out work/o')}
        self.detail(check)
        self.assertNotIn('work/o', (self.logs / 'c.reads').read_text())
        self.edit('other.py', 'X = 11\n')
        self.assertIn('빌드 결과와 검사 코드가 같아', self.detail(check))

    def test_swapping_same_name_bodies_runs_the_check(self):
        self.edit('helper.py', "OPS = {'add': lambda a: a + 1, 'mul': lambda a: a * 2}\n\n\ndef used():\n"
                               "    return OPS['add'](0)\n")
        self.detail()
        self.edit('helper.py', "OPS = {'add': lambda a: a * 2, 'mul': lambda a: a + 1}\n\n\ndef used():\n"
                               "    return OPS['add'](0)\n")
        status, _ = guards.run_check(self.check, 60, self.logs)
        self.assertEqual(status, 'failed')

    def test_existence_checks_are_inputs(self):
        self.edit('check.py', self.CHECK.replace('assert helper.used() == 1',
                                                 "assert not __import__('os').path.exists('flag.txt')"))
        self.detail()
        self.edit('other.py', 'X = 12\n')
        self.assertTrue(self.skipped())
        self.edit('flag.txt', '')
        self.assertEqual(guards.run_check(self.check, 60, self.logs)[0], 'failed')

    def test_reads_from_other_threads_are_all_kept(self):
        for i in range(200):
            self.edit(f'd{i}.txt', str(i))
        (self.root / 'big.bin').write_bytes(b'x' * (8 << 20))
        self.edit('check.py', "import sys, threading\nfrom pathlib import Path\n"
                              "t = threading.Thread(target=lambda: [Path(f'd{i}.txt').read_text() for i in range(200)])\n"
                              "t.start()\nfor _ in range(5):\n    Path('big.bin').read_bytes()\nt.join()\n")
        self.detail()
        reads = (self.logs / 'c.reads').read_text().splitlines()
        self.assertEqual(sum(1 for r in reads if r.startswith('F\td')), 200)

    def test_top_level_python_without_the_tracer_keeps_no_entry(self):
        py = sys.executable
        self.edit('check.py', 'import sys\nsys.exit(0)\n')
        check = {**self.check, 'run': self.check['run'].replace(f'{py} check.py', f'{py} -I check.py')}
        guards.CHECK_STAGE = __import__('re').compile(r'^\s*\S+(\s+-I)?\s+(?P<script>[^\s-]\S*\.py)(\s|$)')
        self.detail(check)
        self.edit('other.py', 'X = 13\n')
        self.assertNotIn('캐시', self.detail(check))

    def test_read_write_handles_and_folder_args_are_inputs(self):
        self.edit('data.txt', 'a')
        self.edit('check.py', "import sys\nwith open('data.txt', 'r+') as f:\n    sys.exit(0 if f.read() == 'a' else 1)\n")
        self.detail()
        self.edit('other.py', 'X = 14\n')
        self.assertTrue(self.skipped())
        self.edit('data.txt', 'b')
        self.assertEqual(guards.run_check(self.check, 60, self.logs)[0], 'failed')
        import os
        os.mkdir(self.root / 'd')
        self.edit('check.py', "import subprocess\nsubprocess.run(['ls', 'd'], check=True)\n")
        self.detail()
        self.assertIn('?', (self.logs / 'c.reads').read_text().split())

    def test_stale_pyc_of_a_same_size_same_mtime_edit_is_not_used(self):
        import os
        import py_compile
        self.edit('helper.py', 'X = 2\n')
        py_compile.compile(str(self.root / 'helper.py'))
        st = (self.root / 'helper.py').stat()
        self.edit('helper.py', 'X = 1\n')
        os.utime(self.root / 'helper.py', ns=(st.st_atime_ns, st.st_mtime_ns))
        self.edit('check.py', 'import helper, sys\nsys.exit(0 if helper.X == 1 else 1)\n')
        py = sys.executable
        for check in (self.check, {'name': 'plain', 'needs': [], 'run': f'{py} check.py'}):
            with self.subTest(run=check['run']):
                self.assertEqual(guards.run_check(check, 60, self.logs)[0], 'passed')

    def test_os_open_read_write_is_an_input(self):
        self.edit('data.txt', 'a')
        self.edit('check.py', "import os, sys\nfd = os.open('data.txt', os.O_RDWR)\n"
                              "sys.exit(0 if os.read(fd, 1) == b'a' else 1)\n")
        self.detail()
        self.edit('other.py', 'X = 15\n')
        self.assertTrue(self.skipped())
        self.edit('data.txt', 'b')
        self.assertEqual(guards.run_check(self.check, 60, self.logs)[0], 'failed')

    def test_failed_check_keeps_no_entry(self):
        self.edit('check.py', 'import sys; sys.exit(3)\n')
        self.assertEqual(guards.run_check(self.check, 60, self.logs)[0], 'failed')
        self.edit('other.py', 'X = 5\n')
        self.assertEqual(guards.run_check(self.check, 60, self.logs)[0], 'failed')

    def test_no_cache_runs_everything(self):
        self.detail()
        self.edit('other.py', 'X = 6\n')
        status, detail = guards.run_check(self.check, 60, self.logs, no_cache=True)
        self.assertEqual(status, 'passed')
        self.assertNotIn('캐시', detail)

    def test_broken_cache_entry_is_a_miss(self):
        self.detail()
        for f in (Path(self.tmp.name) / 'cache' / 'built').iterdir():
            f.write_text('{broken')
        self.edit('other.py', 'X = 7\n')
        self.assertFalse(self.skipped())


class GuardPrintTest(unittest.TestCase):
    def test_prints_ignore_lines_and_nested_bodies(self):
        sys.path.insert(0, str(Path(guards.__file__).parent / 'guardtrace'))
        from guardprint import module_prints
        a = module_prints('def f():\n    def g():\n        return 1\n    return g\n', 'm.py')
        b = module_prints('\n\ndef f():\n    def g():\n        return 2\n    return g\n', 'm.py')
        self.assertEqual(a['f'], b['f'])
        self.assertEqual(a['<module>'], b['<module>'])
        self.assertNotEqual(a['f.<locals>.g'], b['f.<locals>.g'])
        self.assertNotEqual(module_prints('X = frozenset({"a", "b"})\n', 'm.py'),
                            module_prints('X = frozenset({"a", "c"})\n', 'm.py'))
        self.assertIsNone(module_prints('def (:\n', 'm.py'))


class HashDirTest(unittest.TestCase):
    def test_cache_folders_inside_a_needs_dir_are_left_out(self):
        import hashlib
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'sfx').mkdir()
            (root / 'sfx' / 'a.wav').write_bytes(b'1')
            (root / 'x' / 'cache' / 'brr').mkdir(parents=True)
            (root / 'x' / 'cache' / 'brr' / 'b.wav').write_bytes(b'2')

            def key():
                h = hashlib.sha1()
                guards.hash_path(h, root)
                return h.hexdigest()
            k = key()
            os.utime(root / 'x' / 'cache' / 'brr' / 'b.wav', ns=(1, 1))
            self.assertEqual(key(), k)
            os.utime(root / 'sfx' / 'a.wav', ns=(1, 1))
            self.assertNotEqual(key(), k)
