"""dq4warp.sh·dq4state.sh 가 에뮬레이터에 넘기는 LIBDIR 을 가짜 MESENCE 로 본다. SFC 툴킷 Lua 폴더가 넘어가면 FC 상태가
실리지 않아 「진입 루틴이 돌지 않음」 만 남았다(형식은 fc/dq4/docs/dq4-warp.md 「한계」)."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FAKE = '#!/bin/sh\nprintf "LIBDIR=%s\\n" "$LIBDIR" > "$SHOT_DIR/warp.txt"\n'


def toolkit(kind):
    return subprocess.run(['uv', 'run', '--locked', 'krpatch', kind, 'lua'], cwd=ROOT, check=True,
                          capture_output=True, text=True).stdout.strip()


class WarpLibdirTests(unittest.TestCase):
    def warp(self, libdir):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / 'mesen'
            fake.write_text(FAKE)
            fake.chmod(0o755)
            env = dict(os.environ, MESENCE=str(fake))
            env.pop('LIBDIR', None)
            if libdir is not None:
                env['LIBDIR'] = libdir
            got = subprocess.run(['sh', 'fc/dq4/tools/dq4warp.sh', str(Path(tmp) / 'out'), '40/00', '03', '13'],
                                 cwd=ROOT, env=env, capture_output=True, text=True, check=True)
            return got.stdout.strip(), got.stderr

    def test_sfc_libdir_is_replaced_with_the_fc_toolkit(self):
        out, err = self.warp(toolkit('sfc'))
        self.assertEqual(out, f'LIBDIR={toolkit("fc")}')
        self.assertIn('FC 툴킷 폴더로 바꿉니다', err)

    def test_fc_or_unset_libdir_is_kept(self):
        fc = toolkit('fc')
        self.assertEqual(self.warp(fc), (f'LIBDIR={fc}', ''))
        self.assertEqual(self.warp(None)[0], f'LIBDIR={fc}')

    def test_an_fc_wrapper_folder_is_kept(self):
        with tempfile.TemporaryDirectory() as lib:
            (Path(lib) / 'lib.lua').write_text('M.mem = emu.memType.nesMemory\n')
            self.assertEqual(self.warp(lib), (f'LIBDIR={lib}', ''))


if __name__ == '__main__':
    unittest.main()
