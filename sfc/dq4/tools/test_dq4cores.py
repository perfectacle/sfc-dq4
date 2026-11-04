import contextlib
import io
import json
import os
import re
import sys
import tempfile
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


class RomTraceTest(unittest.TestCase):
    def test_bsnes_carries_the_trace_patch(self):
        """bsnes 는 읽은 롬 바이트 패치를 얹어 빌드한다. 롬을 다시 잡거나 놓으면 추적을 끈다(다음 게임이 앞 게임 크기의
        비트맵에 쓰지 않게). 크기만 묻는 것은 추적을 켜지 않는다."""
        self.assertEqual(dq4cores.CORES['bsnes']['patch'], 'dq4cores-bsnes-romtrace.patch')
        self.assertIsNone(dq4cores.CORES['snes9x']['patch'])
        patch = (dq4cores.HERE / dq4cores.CORES['bsnes']['patch']).read_text(encoding='utf-8')
        for f in ('bsnes/sfc/memory/readable.hpp', 'bsnes/sfc/cartridge/cartridge.cpp',
                  'bsnes/target-libretro/libretro.cpp'):
            self.assertIn(f'+++ b/{f}', patch)
        self.assertIn(f'ROM_TRACE_ID = 0x{dq4libretro.ROM_TRACE:04X};', patch)
        readable = patch.split('+++ b/bsnes/sfc/memory/readable.hpp')[1].split('diff --git')[0]
        for fn in ('reset() -> void override {', 'allocate(uint size, uint8 fill = 0xff) -> void override {'):
            self.assertRegex(readable, re.escape(fn) + r'\n\+    trace = nullptr;', fn)
        size = patch.split('retro_get_memory_size')[1]
        self.assertIn('romTraceSize()', size)
        self.assertNotIn('romTraceStart', size)

    def test_stamp_carries_patch_hash(self):
        """도장의 패치 해시가 지금 패치와 같을 때만 있는 코어를 쓰고, 다르면 다시 빌드한다. --check 도 패치를 본다."""
        self.assertEqual(dq4cores.patch_sha('bsnes'), dq4cores.sha256(dq4cores.HERE / 'dq4cores-bsnes-romtrace.patch'))
        self.assertIsNone(dq4cores.patch_sha('snes9x'))
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ):
            os.environ.pop('LIBRETRO_BSNES', None)
            folder = Path(d)
            out = folder / f'bsnes_libretro.{dq4cores.suffix()}'
            out.write_bytes(b'core')
            spec = dq4cores.CORES['bsnes']

            def put(patch):
                (folder / 'bsnes.json').write_text(json.dumps(
                    {'commit': spec['commit'], 'patch': patch, 'sha256': dq4cores.sha256(out)}), encoding='utf-8')

            put(dq4cores.patch_sha('bsnes'))
            with mock.patch.object(dq4cores.subprocess, 'run', side_effect=AssertionError('빌드함')):
                self.assertEqual(dq4cores._build('bsnes', folder, 1), out)
            put('0' * 64)
            with mock.patch.object(dq4cores.subprocess, 'run', side_effect=RuntimeError('빌드 시작')) as run:
                with self.assertRaisesRegex(RuntimeError, '빌드 시작'):
                    dq4cores._build('bsnes', folder, 1)
            run.assert_called()
            for patch, want in ((dq4cores.patch_sha('bsnes'), 0), ('0' * 64, 1)):
                put(patch)
                with mock.patch.object(dq4cores, 'cores_dir', return_value=folder), \
                        mock.patch.object(sys, 'argv', ['dq4cores.py', '--check', '--core', 'bsnes']), \
                        contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(dq4cores.main(), want, patch)

    def test_bit_ranges(self):
        self.assertEqual(dq4libretro.bit_ranges(bytes(4)), [])
        # 바이트 0 의 비트 1·2, 바이트 1 의 비트 7, 바이트 2 의 비트 0 → 오프셋 1,2 / 15,16
        self.assertEqual(dq4libretro.bit_ranges(bytes([0b110, 0x80, 0x01, 0])), [(1, 2), (15, 2)])

    def test_trace_enabled_at_open(self):
        """Core(trace=True) 는 게임을 불러온 바로 뒤 비트맵을 켠다. 켜지지 않는 코어면 연 것을 놓고 멈춘다."""
        core = dq4libretro.Core.__new__(dq4libretro.Core)
        core.lib = mock.Mock()
        core.lib.retro_get_memory_size.return_value = 0
        self.assertFalse(core.trace_start())
        slot = mock.Mock()
        with mock.patch.object(dq4libretro.headless_slots, 'acquire', return_value=slot), \
                mock.patch.object(dq4libretro.Core, '_open', lambda self, *a: setattr(self, 'lib', core.lib)):
            with self.assertRaisesRegex(RuntimeError, '비트맵이 없음'):
                dq4libretro.Core('x.dylib', 'r.sfc', '/tmp', trace=True)
        slot.release.assert_called_once()


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
