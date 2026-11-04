import unittest

import dq4build
import dq4guardpaths as gp


class GuardPathsTest(unittest.TestCase):
    def test_every_check_covers_what_its_command_reaches(self):
        """guards.toml 의 모든 실행 검사: paths 와 묶음이 명령의 스크립트에서 닿는 저장소 파일(전이 import, 띄우는
        Lua, asar 에 넣는 asm, dq4build 단계)을 모두 덮고, 묶음은 그 뿌리에서 닿는 파일을 모두 덮는다.
        빠진 것은 `uv run --locked python sfc/dq4/tools/dq4guardpaths.py` 가 찍는다."""
        checks, groups = gp.load()
        by_check, by_group = gp.missing(checks, groups)
        self.assertEqual(by_group, {})
        self.assertEqual(by_check, {})

    def test_closure_follows_every_kind_of_reach(self):
        """뿌리에서 닿는 길: 함수 안 import(dq4ch1walkcheck → dq4readset), 저장소 tools/ 모듈(headless_slots),
        띄우는 Lua(dq4walkstate.lua, 머리말 dq4readset.lua), asar 에 넣는 asm(dq4titlelayers.asm·dq4windowname.asm),
        하위 프로세스로 부르는 dq4build 단계. asm 의 incsrc 는 지금 추적 파일끼리는 없다(빌드가 만든 파일만 넣음)."""
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

    def test_docstrings_and_help_text_are_not_followed(self):
        """docstring 과 빈칸이 든 글에 나오는 스크립트 이름은 닿는 것으로 보지 않는다."""
        self.assertIsNone(gp.FILE_NAME.fullmatch('dq4ch1walkcheck.py prologue/end.mss'))
        self.assertIsNotNone(gp.FILE_NAME.fullmatch('lua/dq4walkstate.lua'))

    def test_entries_come_from_the_command(self):
        run = ('uv run --locked python sfc/dq4/tools/dq4build.py --out work/ch1 && '
               'uv run --locked python sfc/dq4/tools/dq4heroblockcheck.py --rom work/ch1/dq4-ch1-full.sfc')
        self.assertEqual(gp.entries(run), ['sfc/dq4/tools/dq4build.py', 'sfc/dq4/tools/dq4heroblockcheck.py'])
