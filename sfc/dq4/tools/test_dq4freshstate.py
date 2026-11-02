import ast
import tempfile
import unittest
from pathlib import Path

import dq4freshstate as fs

HERE = Path(__file__).resolve().parent

# 출발 세이브스테이트를 dq4freshstate 로 만들거나 같은 빌드인지 보고, 받은 상태를 장면에 쓰는 검사
FRESH = ['dq4bg3slotcheck', 'dq4chestcheck', 'dq4dungeonencountercheck', 'dq4environmentromcheck', 'dq4fieldcheck',
         'dq4fieldencountercheck', 'dq4fieldtravelcheck', 'dq4groupcheck', 'dq4namegamecheck', 'dq4npccheck',
         'dq4signcheck', 'dq4wellresetcheck', 'dq4battlemsgcheck', 'dq4doorcheck', 'dq4doorstandcheck']
# --state 가 SFC 세이브스테이트가 아닌 도구
NOT_SFC_STATE = {'dq4sparfx': 'NDS 롬을 DeSmuME 로 돌리는 상태 파일이라 SFC 빌드와 상관없음'}
FRESH_CALLS = ('resolve', 'make')


def tools():
    return sorted(p for p in HERE.glob('dq4*.py') if not p.name.startswith('test_'))


def tree_of(name):
    return ast.parse((HERE / f'{name}.py').read_text(encoding='utf-8'))


def is_fresh_call(node, names=FRESH_CALLS + ('require_same_build',)):
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in names
            and isinstance(node.func.value, ast.Name) and node.func.value.id == 'dq4freshstate')


def state_args(tree):
    return [n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, 'attr', '') == 'add_argument'
            and n.args and isinstance(n.args[0], ast.Constant) and n.args[0].value == '--state']


def fresh_values_used(tree):
    """(dq4freshstate.resolve/make 를 담은 대입의 이름, 그 이름을 대입 밖에서 읽는 횟수) 목록."""
    out = []
    for fn in (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)):
        for node in ast.walk(fn):
            if not isinstance(node, ast.Assign) or not any(is_fresh_call(c, FRESH_CALLS) for c in ast.walk(node.value)):
                continue
            names = {t.id for target in node.targets for t in ast.walk(target) if isinstance(t, ast.Name)}
            inside = {id(n) for n in ast.walk(node)}
            for name in names:
                reads = [n for n in ast.walk(fn) if isinstance(n, ast.Name) and n.id == name
                         and isinstance(n.ctx, ast.Load) and id(n) not in inside]
                out.append((name, len(reads)))
    return out


def raw_state_reads(tree):
    """dq4freshstate 호출 밖에서 읽은 <인자>.state(검사 없이 넘긴 --state)의 줄."""
    inside = {id(n) for c in ast.walk(tree) if is_fresh_call(c) for n in ast.walk(c)}
    return [n.lineno for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr == 'state'
            and isinstance(n.value, ast.Name) and n.value.id in ('args', 'a') and id(n) not in inside]


def path_parts(node):
    """경로 식을 이루는 글자 조각들(Path('work') / 'state', os.path.join('work', 'state'), 'work/state/x')."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value.replace('\\', '/').split('/')
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return path_parts(node.left) + path_parts(node.right)
    if isinstance(node, ast.Call) and getattr(node.func, 'id', getattr(node.func, 'attr', '')) in ('Path', 'join'):
        return [p for a in node.args for p in path_parts(a)]
    return ['?']


def work_state_paths(tree):
    hits = set()
    for node in ast.walk(tree):
        parts = path_parts(node)
        if any(a == 'work' and b == 'state' for a, b in zip(parts, parts[1:])):
            hits.add(getattr(node, 'lineno', 0))
    return sorted(hits)


class SameBuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.state = self.dir / 'start.mss'
        self.state.write_bytes(b'MSS')

    def tearDown(self):
        self.tmp.cleanup()

    def test_state_without_rom_tag_fails(self):
        with self.assertRaises(SystemExit):
            fs.require_same_build(self.state, b'rom')

    def test_state_of_another_build_fails(self):
        fs.stamp(self.state, b'old build')
        with self.assertRaises(SystemExit):
            fs.require_same_build(self.state, b'new build')

    def test_state_replaced_after_stamp_fails(self):
        fs.stamp(self.state, b'rom')
        self.state.write_bytes(b'MSS of another build')
        with self.assertRaises(SystemExit):
            fs.require_same_build(self.state, b'rom')

    def test_state_of_same_build_passes(self):
        fs.stamp(self.state, b'rom')
        self.assertEqual(fs.require_same_build(self.state, b'rom'), self.state)

    def test_given_state_is_checked_not_rebuilt(self):
        rom = self.dir / 'x.sfc'
        rom.write_bytes(b'new build')
        fs.stamp(self.state, b'old build')
        with self.assertRaises(SystemExit):
            fs.resolve(self.state, 'mesence', rom, self.dir / 'out')
        self.assertFalse((self.dir / 'out').exists())

    def test_built_state_is_stamped_with_the_rom(self):
        rom = self.dir / 'x.sfc'
        rom.write_bytes(b'new build')

        def build(mesence, r, out):
            (out / 'hub.mss').write_bytes(b'MSS hub')
            return out / 'hub.mss'
        state = fs.resolve(None, 'mesence', rom, self.dir / 'out', build)
        self.assertEqual(fs.require_same_build(state, b'new build'), state)
        with self.assertRaises(SystemExit):
            fs.require_same_build(state, b'old build')

    def test_kind_by_header(self):
        rom = bytearray(0x10000)
        self.assertEqual(fs.kind_of(rom), 'ship')
        rom[fs.HEADER:fs.HEADER + 21] = b'DRAGONQUEST4'.ljust(21, b' ')
        self.assertEqual(fs.kind_of(rom), 'chapter1')


class AstHelperTests(unittest.TestCase):
    def test_joined_work_state_paths_are_found(self):
        for src in ("Path('work') / 'state' / 'ship.mss'", "os.path.join('work', 'state', 'x.mss')",
                    "ROOT / 'work/state' / 'x.mss'", "'work/state/ship.mss'", "Path('work', 'state')"):
            with self.subTest(src):
                self.assertTrue(work_state_paths(ast.parse(src)))
        self.assertFalse(work_state_paths(ast.parse("ROOT / 'work' / 'cache' / 'states'")))

    def test_unused_fresh_state_is_found(self):
        unused = ast.parse('def main():\n    state = dq4freshstate.resolve(args.state, m, rom, out)\n'
                           '    run(args.state)\n')
        self.assertEqual(fresh_values_used(unused), [('state', 0)])
        self.assertEqual(raw_state_reads(unused), [3])


class NoStaleStateTests(unittest.TestCase):
    def test_fresh_checks_use_the_state_they_built(self):
        for name in FRESH:
            tree = tree_of(name)
            with self.subTest(name):
                used = fresh_values_used(tree)
                self.assertTrue(used, '출발 상태를 dq4freshstate.resolve/make 로 만들어야 함')
                self.assertTrue(all(n for _, n in used), f'만든 상태를 장면에 넘기지 않음: {used}')
                self.assertEqual(raw_state_reads(tree), [], '--state 를 dq4freshstate 를 거치지 않고 씀')

    def test_state_tools_check_the_build(self):
        for path in tools():
            if path.stem in NOT_SFC_STATE or path.stem == 'dq4freshstate':
                continue
            tree = ast.parse(path.read_text(encoding='utf-8'))
            if state_args(tree):
                with self.subTest(path.name):
                    self.assertTrue(any(is_fresh_call(n) for n in ast.walk(tree)),
                                    '--state 를 받으면 dq4freshstate 로 같은 빌드인지 봐야 함')
                    self.assertEqual(raw_state_reads(tree), [])

    def test_no_tool_points_at_work_state(self):
        for path in tools():
            with self.subTest(path.name):
                self.assertEqual(work_state_paths(ast.parse(path.read_text(encoding='utf-8'))), [],
                                 '손으로 고른 work/state 세이브스테이트를 가리킴')

    def test_door_checks_pick_their_start(self):
        # 문 칸에 서는 검사는 성 마을 출발 상태를 build 로 만들고, 문 열기 검사는 서장 끝(build 없음)에서 떠난다
        for name, want in (('dq4doorstandcheck', True), ('dq4doorcheck', False)):
            calls = [n for n in ast.walk(tree_of(name)) if is_fresh_call(n, ('resolve',))]
            with self.subTest(name):
                self.assertEqual(len(calls), 1)
                self.assertEqual(len(calls[0].args), 4)
                self.assertEqual(any(k.arg == 'build' for k in calls[0].keywords), want)

    def test_exception_lists_are_current(self):
        for name in NOT_SFC_STATE:
            with self.subTest(name):
                self.assertTrue(state_args(tree_of(name)), '--state 를 받지 않으면 목록에서 뺀다')


if __name__ == '__main__':
    unittest.main()
