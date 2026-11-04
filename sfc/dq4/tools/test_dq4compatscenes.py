"""dq4compatscenes: 장부로 우리 코드 가리기, io 기록 판정, 장면 명령, dq4mesen 의 프로브 붙이기(롬 없이)."""
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dq4compatscenes as cs  # noqa: E402
import dq4mesen  # noqa: E402

LEDGER = {'stages': [{'name': 'menu', 'ranges': [{'cpu': '00:FF9E~00:FFA4'}, {'cpu': '01:FF00~01:FFAD'}]}]}


class CompatScenes(unittest.TestCase):
    def test_ours(self):
        patched = cs.patched_ranges(LEDGER)
        self.assertEqual(patched, [(0x00, 0xFF9E, 0xFFA4), (0x01, 0xFF00, 0xFFAD)])
        self.assertTrue(cs.ours(0x60, 0x8000, patched))
        self.assertTrue(cs.ours(0x01, 0xFF62, patched))
        self.assertFalse(cs.ours(0x01, 0xDCFC, patched))
        self.assertFalse(cs.ours(0x25, 0x8071, patched))

    def test_cross_bank_ledger_range_is_split(self):
        ledger = {'stages': [{'name': 'chapter1', 'ranges': [{'cpu': '3C:FFEA~3D:8000'}, {'cpu': '64:FD0A~66:8135'}]}]}
        patched = cs.patched_ranges(ledger)
        self.assertEqual(patched, [(0x3C, 0xFFEA, 0xFFFF), (0x3D, 0x8000, 0x8000), (0x64, 0xFD0A, 0xFFFF),
                                   (0x65, 0x8000, 0xFFFF), (0x66, 0x8000, 0x8135)])
        self.assertTrue(cs.ours(0x3C, 0xFFF0, patched))
        self.assertTrue(cs.ours(0x3D, 0x8000, patched))
        self.assertFalse(cs.ours(0x3D, 0x8001, patched))

    def test_io_problems(self):
        patched = cs.patched_ranges(LEDGER)
        lines = ['R pc=01:FF62 bank=00 at=4380', 'R pc=06:F53D bank=3D at=6000', 'R pc=06:F53D bank=3D at=6000',
                 'R pc=06:F536 bank=3D at=4380', 'W pc=25:8071 bank=00 at=6000', 'R pc=06:F53D bank=3C at=6000',
                 'R pc=60:D843 bank=3F at=2184', 'BRK pc=5E:C00F op=09', 'BRK pc=5E:C010 op=16', 'R pc=01:FF62 bank=00',
                 'junk']
        problems, dq5 = cs.io_problems(lines, patched)
        self.assertEqual(problems, ['5E:C010 이 BRK 16 를 부름(dq4brkscan.ALLOWED 밖)',
                                    '해석하지 못한 기록 줄: R pc=01:FF62 bank=00', '01:FF62 이 00:4380 를 읽음',
                                    '06:F53D 이 3C:6000 를 읽음(원래 DQ5 코드, DQ5_ALLOWED 밖)',
                                    '60:D843 이 3F:2184 를 읽음',
                                    '25:8071 이 00:6000 를 씀(원래 DQ5 코드, DQ5_ALLOWED 밖)', '해석하지 못한 기록 줄: junk'])
        self.assertEqual(dq5, ['06:F536 이 3D:4380 를 읽음', '06:F53D 이 3D:6000 를 읽음'])

    def test_high_unparsed_line_fails(self):
        self.assertEqual(cs.cc.probe_problems(['R pc=25:8071 bank=70']), [])
        self.assertEqual(cs.cc.probe_problems(['R pc=25:8071 bank=70 at=0000']),
                         ['해석하지 못한 기록 줄: R pc=25:8071 bank=70 at=0000'])

    def test_window_reached(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            self.assertEqual(cs.window_reached(d), ['창 검사 readset.json 없음'])
            (d / 'readset.json').write_text(json.dumps({'a': {'returncode': 0, 'timed_out': False},
                                                        'b': {'returncode': 1, 'timed_out': False},
                                                        'c': {'returncode': 0, 'timed_out': False}}))
            (d / 'a').mkdir()
            (d / 'a' / 'v00100.bin').write_bytes(b'')
            (d / 'c').mkdir()
            got = cs.window_reached(d)
        self.assertEqual(got, ['창 장면 b: 종료 1, 시간 초과 False', '창 장면 c: 잰 프레임 없음'])

    def test_io_ranges_skip_real_registers(self):
        # 진짜 레지스터(PPU 2100~2183, 조이패드 4016·4017, CPU 4200~421F, DMA 4300~437F)는 범위 밖이어야 한다
        spans = [tuple(int(v, 16) for v in r.split(':')[1].split('-')) for r in cs.IO_RANGES.split(',')]
        for reg in (0x2100, 0x2180, 0x2183, 0x4016, 0x4017, 0x4200, 0x421F, 0x4300, 0x437F):
            self.assertFalse(any(lo <= reg <= hi for lo, hi in spans), f'{reg:04X}')
        for hole in (0x2000, 0x2184, 0x3FFF, 0x4000, 0x4018, 0x4220, 0x4380, 0x6000, 0x7FFF):
            self.assertTrue(any(lo <= hole <= hi for lo, hi in spans), f'{hole:04X}')
        self.assertTrue(cs.IO_RANGES.startswith('00-3F:'))

    def test_commands(self):
        a = SimpleNamespace(rom=Path('/r/full.sfc'), jobs=3, window_rom=Path('/r/ch1.sfc'), symbols=Path('/w/wn.sym'),
                            symbols_rom=Path('/w/menu.sfc'))
        pre, cmd = cs.commands('battle', 'io', a, Path('/o'))
        self.assertEqual(pre, [])
        self.assertIn('dq4battlecheck.py', cmd[1])
        self.assertIn('/o/battle-io', cmd)
        pre, cmd = cs.commands('save', 'high', a, Path('/nonexistent-out'))
        self.assertIn('dq4ch1walkcheck.py', pre[0][1])
        self.assertIn('dq4ch1savecheck.py', cmd[1])
        pre, cmd = cs.commands('window', 'high', a, Path('/o'))
        self.assertIn('--every', cmd)
        self.assertIn('/r/ch1.sfc', cmd)

    def test_mesen_wraps_script_only_with_log(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop('DQ4_OPENBUS_LOG', None)
            self.assertEqual(dq4mesen.with_openbus('a.lua', {'env': {'X': '1'}}), ('a.lua', {'env': {'X': '1'}}))
        with mock.patch.dict(os.environ, {'DQ4_OPENBUS_LOG': '/l.txt', 'DQ4_OPENBUS_RANGES': cs.IO_RANGES}):
            script, kw = dq4mesen.with_openbus('a.lua', {'env': {'X': '1'}, 'cwd': '/d'})
        self.assertEqual(script, dq4mesen.OPENBUS)
        self.assertEqual(kw['cwd'], '/d')
        self.assertEqual((kw['env']['X'], kw['env']['PROBE_TARGET'], kw['env']['OPENBUS_LOG']), ('1', 'a.lua', '/l.txt'))
        self.assertEqual(kw['env']['OPENBUS_RANGES'], cs.IO_RANGES)
        self.assertTrue(dq4mesen.OPENBUS.exists())


if __name__ == '__main__':
    unittest.main()
