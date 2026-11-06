import unittest

import dq4build
import dq4guardpaths as gp


class GuardPathsTest(unittest.TestCase):
    def test_every_check_covers_what_its_command_reaches(self):
        """guards.toml 의 모든 실행 검사: paths 와 묶음이 명령의 스크립트에서 dq4guardpaths 의 길(전이 import, 띄우는
        Lua, asar 에 넣는 asm, dq4build 단계)로 닿는 저장소 파일을 덮고, 묶음은 그 뿌리에서 닿는 파일을 덮는다.
        빠진 것은 `uv run --locked python sfc/dq4/tools/dq4guardpaths.py` 가 찍는다."""
        checks, groups = gp.load()
        self.assertEqual(set(groups), set(gp.GROUP_ROOTS), '[groups] 의 묶음마다 dq4guardpaths.GROUP_ROOTS 에 뿌리를 적는다')
        by_check, by_group = gp.missing(checks, groups)
        self.assertEqual(by_group, {})
        self.assertEqual(by_check, {})

    def test_closure_follows_every_kind_of_reach(self):
        """뿌리에서 닿는 길: 함수 안 import(dq4ch1walkcheck → dq4readset), 저장소 tools/ 모듈(headless_slots),
        띄우는 Lua(dq4walkstate.lua, 머리말 dq4readset.lua), asar 에 넣는 asm(dq4titlelayers.asm·dq4windowname.asm),
        하위 프로세스로 부르는 dq4build 단계."""
        build = gp.closure(gp.GROUP_ROOTS['ch1-build'])
        for name in dq4build.STAGES:
            self.assertIn(f'sfc/dq4/tools/{name}', build)
        for f in ('sfc/dq4/tools/dq4titlelayers.asm', 'sfc/dq4/tools/dq4windowname.asm'):
            self.assertIn(f, build)
        walk = gp.closure(gp.GROUP_ROOTS['ch1-walk'])
        for f in ('sfc/dq4/tools/dq4readset.py', 'sfc/dq4/tools/lua/dq4readset.lua', 'sfc/dq4/tools/lua/dq4walkstate.lua',
                  'tools/lua/walk.lua'):
            self.assertIn(f, walk)
        self.assertIn('tools/headless_slots.py', gp.closure(['sfc/dq4/tools/dq4libretroreadsetcheck.py']))

    def test_data_files_named_by_literals_are_followed(self):
        """글자 상수로 이름을 적어 읽는 자료 파일(빌드가 넘기는 dq4sound-game.args, 걷기 검사의 HERE.parent 아래
        ch1-walk-messages.toml)도 닿는 것으로 본다. 검사 결과 캐시 키([cache] key = "paths")가 paths 밖 자료 파일을
        빼므로, 이런 파일이 paths 에 빠지면 바뀌어도 옛 결과로 건너뛴다."""
        self.assertIn('sfc/dq4/tools/dq4sound-game.args', gp.closure(gp.GROUP_ROOTS['ch1-build']))
        self.assertIn('sfc/dq4/ch1-walk-messages.toml', gp.closure(gp.GROUP_ROOTS['ch1-walk']))
        self.assertIsNone(gp.DATA_NAME.fullmatch('guards.toml 의 paths'))

    def test_docstrings_and_help_text_are_not_followed(self):
        """docstring 과 빈칸이 든 글에 나오는 스크립트 이름은 닿는 것으로 보지 않는다."""
        self.assertIsNone(gp.FILE_NAME.fullmatch('dq4ch1walkcheck.py prologue/end.mss'))
        self.assertIsNotNone(gp.FILE_NAME.fullmatch('lua/dq4walkstate.lua'))

    def test_unittest_discover_picks_its_test_files(self):
        """`unittest discover -s 폴더 -p 패턴` 꼴의 검사는 그 패턴에 맞는 시험 파일이 진입점이다(그 import 를 따라간다)."""
        run = ('uv run --locked python -m unittest discover -s sfc/dq4/tools -p test_dq4environment.py -k CounterTests '
               '2>&1 | tail -1 | grep -qx OK')
        self.assertEqual(gp.entries(run), ['sfc/dq4/tools/test_dq4environment.py'])
        self.assertIn('sfc/dq4/tools/dq4environment.py', gp.closure(gp.entries(run)))
        many = gp.entries('python -m unittest discover -s sfc/dq4/tools -p "test_dq4env*.py"'.replace('"', ''))
        self.assertIn('sfc/dq4/tools/test_dq4environment.py', many)

    def test_entries_come_from_the_command(self):
        run = ('uv run --locked python sfc/dq4/tools/dq4build.py --out work/ch1 && '
               'uv run --locked python sfc/dq4/tools/dq4heroblockcheck.py --rom work/ch1/dq4-ch1-full.sfc')
        self.assertEqual(gp.entries(run), ['sfc/dq4/tools/dq4build.py', 'sfc/dq4/tools/dq4heroblockcheck.py'])
