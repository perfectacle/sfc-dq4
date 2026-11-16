"""인물 목록: 인라인 스크립트 명령 읽기·표기, 플래그 덮어쓰기 표, 인물 표 값, CLI(덤프 비교 포함)."""
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dq5npc as N  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402

ROM = Path(__file__).resolve().parents[4] / 'rom' / 'dq5.sfc'


def rom_with(pieces, size=0x200000):
    data = bytearray(size)
    for at, raw in pieces:
        data[lorom(at):lorom(at) + len(raw)] = raw
    return Rom(data)


def entry(talk=0x12, misc=0, x=5, y=6, gfx=0x2C, move=0, extra=0x44, b0=0x80):
    return bytes([b0, talk, misc, x, y, gfx, move, extra])


class ScriptOpTests(unittest.TestCase):
    def test_lengths_and_walk(self):
        ops = N.script_ops(bytes.fromhex('85 03 13 02 04 21 34 12 00'))
        self.assertEqual([(off, raw.hex(), name) for off, raw, name in ops],
                         [(0, '8503', '걸어가 도착 대기 X Y'), (2, '130204', '걸어가기 X Y'),
                          (5, '213412', '메시지(창 열고 닫음)'), (8, '00', '그 자리')])

    def test_rejects_unknown_and_truncated(self):
        with self.assertRaisesRegex(ValueError, r'\+1: 모르는 명령 59'):
            N.script_ops(bytes([0x00, 0x59]))
        with self.assertRaisesRegex(ValueError, '길이 2 를 넘음'):
            N.script_ops(bytes([0x13, 0x01]))

    def test_format_op(self):
        def fmt(code, off=0):
            ((_, raw, name),) = N.script_ops(bytes.fromhex(code))
            return N.format_op(off, raw, name)

        self.assertTrue(fmt('85 03').endswith('(5,3)'))
        self.assertTrue(fmt('2b 07 08').endswith('순간이동 X Y (7,8)'))
        self.assertTrue(fmt('41 01 02 0a').endswith('(1,2) 0A'))
        self.assertTrue(fmt('09 85 10').endswith('7E:2195 & 10 켜짐'))
        self.assertTrue(fmt('09 05 10').endswith('꺼짐'))
        self.assertTrue(fmt('06 05 10 fe', 4).endswith('7E:2195 & 10 켜짐 → +02'))
        self.assertTrue(fmt('06 85 10 02').endswith('꺼짐 → +02'))
        self.assertTrue(fmt('10 01 80').endswith('7E:2191 & 80'))
        self.assertTrue(fmt('08 81 02 03 04').endswith('(1,2)-(3,4) 안이 될 때까지'))
        self.assertTrue(fmt('08 01 02 03 04').endswith('밖이 될 때까지'))
        self.assertTrue(fmt('07 01 02 03 04 06').endswith('(1,2)-(3,4) 안이면 → +06'))
        self.assertTrue(fmt('07 81 02 03 04 fa', 6).endswith('밖이면 → +00'))
        self.assertTrue(fmt('03 fd', 5).endswith('→ +03'))
        self.assertTrue(fmt('05 34 12 01').endswith('01:1234'))
        self.assertTrue(fmt('37 00 80 03').endswith('03:8000'))
        self.assertTrue(fmt('20 05 00').endswith('0005'))
        self.assertTrue(fmt('30 cd 0a').endswith('0ACD'))
        self.assertTrue(fmt('1d 04').endswith('이동 간격 04'))
        self.assertEqual(fmt('16', 0x1F), '+1F 16           멈춤(이동 간격 0)')
        self.assertEqual(N.s8(0xFF), -1)


class OverrideTests(unittest.TestCase):
    def map_rom(self):
        lists = entry() + b'\x00' + entry(talk=0x34, b0=0x40) + b'\x00'
        override = entry(talk=0x56) + b'\x00'
        return rom_with([(N.NPC_GROUPS, (0x8000).to_bytes(2, 'little')), (0x058000, lists),
                         (0x109000, override),
                         (N.OVERRIDE_LISTS, bytes([0x00, 0x01, 0x81, 0x04]) + (0x9000).to_bytes(2, 'little') + b'\xff'),
                         (N.NO_NPC, bytes([0x00, 0x00, 0x02, 0x80, 0x00, 0x01, 0x83, 0x01, 0xff]))])

    def test_flag_on(self):
        self.assertTrue(N.flag_on({N.FLAGS + 1: 0x04}, 0x01, 0x04))
        self.assertFalse(N.flag_on({}, 0x01, 0x04))
        self.assertTrue(N.flag_on({}, 0x81, 0x04))

    def test_list_address_order(self):
        rom = self.map_rom()
        self.assertEqual(N.no_npc_rules(rom, 0, 0), [(0x02, 0x80)])
        self.assertEqual(N.overrides(rom, 0, 1), [(0x81, 0x04, 0x109000)])
        self.assertEqual(N.list_address(rom, 0, 0, {}), 0x058000)
        self.assertIsNone(N.list_address(rom, 0, 0, {N.FLAGS + 2: 0x80}))
        # 00/01: 플래그 03 bit0 가 꺼져 있으면 인물 없음, 켜져 있으면 01 bit2 가 꺼진 동안 덮어쓰기 목록.
        on = {N.FLAGS + 3: 0x01}
        self.assertEqual(N.list_address(rom, 0, 1, on), 0x109000)
        self.assertEqual(N.list_address(rom, 0, 1, on | {N.FLAGS + 1: 0x04}), 0x058009)
        self.assertEqual(N.map_list(rom, 0, 1), 0x058009)
        self.assertEqual(N.map_entries(rom, 0, 1), [(0x058009, 8)])
        self.assertEqual(N.list_entries(rom, 0x109000), [(0x109000, 8)])


class TableValueTests(unittest.TestCase):
    def test_gfx_32a0(self):
        rom = rom_with([(N.GFX_TABLE + 0x2F, b'\x80'), (N.GFX_TABLE + 0x10, b'\x80')])
        self.assertEqual(N.gfx_32a0(rom, 0x10, {}), 0x41)
        self.assertEqual(N.gfx_32a0(rom, 0x11, {}), 0x01)
        self.assertEqual(N.gfx_32a0(rom, 0x10, {0x7E21D1: 0x40}), 0x01)
        self.assertEqual(N.gfx_32a0(rom, 0x9A, {0x7E21B3: 0x08}), 0x41)
        self.assertEqual(N.gfx_32a0(rom, 0x9A, {}), 0x01)

    def test_long_intervals_take_turns(self):
        rom = rom_with([])
        f = {'talk': 0x123, 'misc': 0x80 | 0x40 | 0x30 | 2, 'x': 0x85, 'y': 0x86, 'gfx': 0x84, 'move': 8 << 2 | 3,
             'extra': 0x5A, 'script': 0x058010}
        g = dict(f, gfx=0, move=9 << 2, misc=0, script=None, x=5, y=6)
        rows = N.table_values(rom, [(0, f), (0, f), (0, g)])
        self.assertEqual([r[0x3300] for r in rows], [0x81, 0x82, 0x91])
        first, last = rows[0], rows[2]
        self.assertEqual((first[0x3020], first[0x3080], first[0x31E0]), (5, 5, 0x22))
        self.assertEqual((first[0x36E0], first[0x3700], first[0x31C0]), (0x23, 0x01, 1))
        self.assertEqual((first[0x3320], first[0x32C0], first[0x32E0]), (0x04, 0x50, 0xA0))
        self.assertEqual((first[0x33A0], first[0x3380], first[0x31A0]), (0x80 | 0x30 | 0x80 | 0x09, 0, 0x01))
        self.assertEqual((first[0x3480], first[0x34A0], first[0x32A0]), (0x11, 0x80, 0x31))
        self.assertEqual((last[0x3380], last[0x3480], last[0x34A0], last[0x31E0]), (0x80, 0, 0, 0x88))
        self.assertTrue(N.decode(g)['hidden'])


@unittest.skipUnless(ROM.exists(), '롬이 없음(rom/dq5.sfc)')
class RomTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom = Rom(ROM.read_bytes())

    def run_main(self, *args):
        out = io.StringIO()
        with mock.patch.object(sys, 'argv', ['dq5npc.py', str(ROM), *args]), redirect_stdout(out):
            code = N.main()
        return code, out.getvalue()

    def test_check_scripts(self):
        code, out = self.run_main('--check-scripts')
        self.assertEqual((code, out.strip()), (0, 'scripts 1034, mismatch 0'))

    def test_map_listing(self):
        code, out = self.run_main('02', '00')
        lines = out.splitlines()
        self.assertEqual(code, 0)
        self.assertTrue(next(line for line in lines if line.startswith('list at ')).startswith('list at 05'))
        self.assertTrue(lines[0].startswith('override: flag 00 mask 80 -> 10'))
        self.assertEqual(sum(1 for line in lines if ' talk=' in line), 7)
        self.assertEqual(sum(1 for line in lines if line.startswith('  스크립트 ')), 4)
        code, out = self.run_main('04', '00')
        self.assertEqual(out.count('(낮에는 없음)'), 5)
        code, out = self.run_main('04', '00', '--night')
        self.assertEqual(out.count(' talk='), 5)

    def test_flags_pick_override_and_no_npc(self):
        code, out = self.run_main('17', '00', '--flags', '2192=80')
        self.assertIn('no-NPC rule: flag 02 mask 80', out)
        self.assertEqual(out.strip().splitlines()[-1], '인물을 놓지 않음')
        code, plain = self.run_main('01', '00')
        code, out = self.run_main('01', '00', '--flags', '2190=80')
        self.assertIn('override: flag 00 mask 80', out)
        self.assertNotEqual(plain.splitlines()[-1], out.splitlines()[-1])
        alt = [line for line in out.splitlines() if line.startswith('list at ')]
        self.assertTrue(alt[0].startswith('list at 10'))

    def test_list_option(self):
        code, out = self.run_main('--list', '108BBD')
        self.assertEqual(out.splitlines()[0], 'list at 108BBD')

    def test_compare_dump(self):
        base = N.list_address(self.rom, 2, 0, {})
        placed = [(a, f) for a, _ in N.list_entries(self.rom, base) for f in [N.parse(self.rom, a)] if f]
        w = bytearray(0x20000)
        for slot, t in enumerate(N.table_values(self.rom, placed, {}), 8):
            for k, v in t.items():
                w[k + slot] = v
        with tempfile.TemporaryDirectory() as d:
            good, bad = Path(d, 'good.bin'), Path(d, 'bad.bin')
            good.write_bytes(w)
            w[0x3220 + 8] ^= 0x01
            bad.write_bytes(w)
            code, out = self.run_main('02', '00', '--compare', str(good))
            self.assertEqual(code, 0)
            self.assertEqual(out.count(' OK'), len(placed))
            code, out = self.run_main('02', '00', '--compare', str(bad))
        self.assertEqual(code, 1)
        self.assertEqual(out.count('DIFF 3220 ours'), 1)


if __name__ == '__main__':
    unittest.main()
