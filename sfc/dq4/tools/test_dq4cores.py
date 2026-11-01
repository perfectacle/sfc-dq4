import os
import unittest
from pathlib import Path
from unittest import mock

import dq4cores
import dq4libretro


class CoresTest(unittest.TestCase):
    def test_pinned_full_commits(self):
        for name, spec in dq4cores.CORES.items():
            with self.subTest(name):
                self.assertRegex(spec['commit'], r'^[0-9a-f]{40}$')
                self.assertTrue(spec['repo'].startswith('https://github.com/libretro/'))
                self.assertIn(name, dq4cores.ENV)

    def test_env_overrides_built_core(self):
        with mock.patch.dict(os.environ, {'LIBRETRO_SNES9X': '/x/s.dylib'}):
            self.assertEqual(dq4cores.core_path('snes9x'), Path('/x/s.dylib'))
        with mock.patch.dict(os.environ, {'DQ4_CORES': '/c'}, clear=False):
            os.environ.pop('LIBRETRO_BSNES', None)
            self.assertEqual(dq4cores.core_path('bsnes'), Path(f'/c/bsnes_libretro.{dq4cores.suffix()}'))


class CheatCaseTest(unittest.TestCase):
    def test_cheat_codes_go_lowercase(self):
        # bsnes(63ee22f7) decodeSNES 는 16진 소문자만 받는다. 대문자면 아무 일도 하지 않았다
        core = dq4libretro.Core.__new__(dq4libretro.Core)
        core.lib = mock.Mock()
        core.set_cheats(['7E1F005A', '2AD812FF'])
        sent = [c.args[2] for c in core.lib.retro_cheat_set.call_args_list]
        self.assertEqual(sent, [b'7e1f005a', b'2ad812ff'])


if __name__ == '__main__':
    unittest.main()
