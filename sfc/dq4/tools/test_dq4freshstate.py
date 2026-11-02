import ast
import tempfile
import unittest
from pathlib import Path

import dq4freshstate as fs

HERE = Path(__file__).resolve().parent

# 출발 상태를 dq4freshstate 로 만들거나 같은 빌드인지 보는 장면 검사. 옛 work/state/*.mss 를 불러 폭주한 결과를
# 검사 결과로 믿은 적이 있어, 이 목록의 검사가 dq4freshstate 를 거치지 않으면 실패한다.
FRESH = ['dq4bg3slotcheck', 'dq4chestcheck', 'dq4dungeonencountercheck', 'dq4environmentromcheck', 'dq4fieldcheck',
         'dq4fieldencountercheck', 'dq4fieldtravelcheck', 'dq4groupcheck', 'dq4namegamecheck', 'dq4npccheck',
         'dq4signcheck', 'dq4wellresetcheck', 'dq4battlemsgcheck']
# 아직 손으로 고른 세이브스테이트를 받는 도구(같은 빌드인지 보지 않음). 줄이기만 한다
LEGACY_STATE = {'dq4doorcheck', 'dq4doorstandcheck', 'dq4sparfx'}


def tools():
    return sorted(p for p in HERE.glob('dq4*.py') if not p.name.startswith('test_'))


def state_args(tree):
    """--state add_argument 호출들."""
    return [n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, 'attr', '') == 'add_argument'
            and n.args and isinstance(n.args[0], ast.Constant) and n.args[0].value == '--state']


def uses_fresh(tree):
    return any(isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == 'dq4freshstate'
               and n.attr in ('resolve', 'make', 'require_same_build', 'add_argument') for n in ast.walk(tree))


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

    def test_kind_by_header(self):
        rom = bytearray(0x10000)
        self.assertEqual(fs.kind_of(rom), 'ship')
        rom[fs.HEADER:fs.HEADER + 21] = b'DRAGONQUEST4'.ljust(21, b' ')
        self.assertEqual(fs.kind_of(rom), 'chapter1')


class NoStaleStateTests(unittest.TestCase):
    def test_fresh_checks_go_through_freshstate(self):
        for name in FRESH:
            tree = ast.parse((HERE / f'{name}.py').read_text(encoding='utf-8'))
            with self.subTest(name):
                self.assertTrue(uses_fresh(tree), '출발 상태를 dq4freshstate 로 만들거나 확인해야 함')

    def test_no_tool_reads_a_state_it_did_not_check(self):
        for path in tools():
            if path.stem in LEGACY_STATE or path.stem == 'dq4freshstate':
                continue
            tree = ast.parse(path.read_text(encoding='utf-8'))
            with self.subTest(path.name):
                if state_args(tree):
                    self.assertTrue(uses_fresh(tree), '--state 를 받으면 dq4freshstate.resolve 로 같은 빌드인지 봐야 함')
                old = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)
                       and 'work/state/' in n.value]
                self.assertEqual(old, [], '옛 work/state 세이브스테이트를 가리킴')

    def test_legacy_list_is_current(self):
        for name in LEGACY_STATE:
            with self.subTest(name):
                self.assertTrue((HERE / f'{name}.py').is_file(), '지운 도구는 목록에서도 뺀다')


if __name__ == '__main__':
    unittest.main()
