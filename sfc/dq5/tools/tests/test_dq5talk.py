"""인물 대화 해석: 대화 번호 갈래, 스크립트 명령·분기 읽기, 덧붙인 스크립트 훅, 네이티브 호출 요약, CLI."""
import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dq5talk as T  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402

ROM = Path(__file__).resolve().parents[4] / 'rom' / 'dq5.sfc'

# 메시지·조건·06 블록·else·special·call 을 거쳐 3F 로 끝나는 스크립트 하나와, bit5 메시지 하나만 있는 스크립트.
SCRIPT0 = bytes.fromhex('41 23 07 05 06 18 01 02 3e 0b 12 07 00 34 12 3f')
SCRIPT1 = bytes.fromhex('61 00 3f')


def rom_with(pieces, size=0x200000):
    data = bytearray(size)
    for at, raw in pieces:
        data[lorom(at):lorom(at) + len(raw)] = raw
    return Rom(data)


def script_rom(*extra):
    return rom_with([(T.BLOCKS, (0x8000).to_bytes(2, 'little')), (0x068000, SCRIPT0 + SCRIPT1), *extra])


class KindTests(unittest.TestCase):
    def test_talk_kind_boundaries(self):
        self.assertEqual([T.talk_kind(t) for t in (0, 0x10, 0x11, 0x24E, 0x24F, 0x26C, 0x26D, 0x8FF, 0x900)],
                         ['special', 'special', 'script', 'script', 'special2', 'special2', 'message', 'message', 'extra'])

    def test_message_number(self):
        self.assertEqual(T.message_number(0x41, 0x23), 0x123 + T.MESSAGE_BASE)
        self.assertEqual(T.message_number(0x61, 0x00), 0x100)
        self.assertEqual(T.message_number(0x7F, 0xFF), 0x1FFF)

    def test_brk_args(self):
        rom = rom_with([(T.BRK_QUERY_BITS, bytes([0x92]))])
        self.assertEqual((T.brk_args(rom, 0x04), T.brk_args(rom, 0x0E), T.brk_args(rom, 0x10)), (3, 0, 2))
        self.assertEqual((T.brk_args(rom, 0x80), T.brk_args(rom, 0x81)), (3, 4))
        self.assertEqual((T.brk_args(rom, 0x94), T.brk_args(rom, 0xA3)), (1, 1))


class ScriptTests(unittest.TestCase):
    def test_parse_script_branches(self):
        ops, end = T.parse_script(script_rom(), 0x068000)
        self.assertEqual(end, 0x068000 + len(SCRIPT0))
        self.assertEqual([(a - 0x068000, depth, name) for a, depth, name, _, _ in ops],
                         [(0, 0, 'msg'), (2, 0, 'if cond05 (はい/いいえ 창에서 はい)'), (5, 1, 'flag-on'), (8, 1, 'end-block'),
                          (9, 0, 'else'), (10, 1, 'special'), (12, 0, 'call'), (15, 0, 'end')])
        self.assertEqual(ops[0][4], 0x123 + T.MESSAGE_BASE)

    def test_script_address_skips_like_game(self):
        rom = script_rom()
        self.assertEqual(T.script_address(rom, 0), 0x068000)
        self.assertEqual(T.script_address(rom, 1), 0x068000 + len(SCRIPT0))
        ops, _ = T.parse_script(rom, T.script_address(rom, 1))
        self.assertEqual([(name, msg) for _, _, name, _, msg in ops], [('msg', 0x100), ('end', None)])

    def test_negated_condition_ending_inside_branch(self):
        rom = rom_with([(0x068000, bytes.fromhex('07 85 06 12 01 3f'))])
        ops, end = T.parse_script(rom, 0x068000)
        self.assertEqual(ops[0][2], 'if not cond05 (はい/いいえ 창에서 はい)')
        self.assertEqual(ops[-1][2], 'end')
        self.assertEqual(end, 0x068006)

    def test_unknown_op(self):
        rom = rom_with([(0x068000, bytes.fromhex('13 3f'))])
        with self.assertRaisesRegex(ValueError, '068000: 모르는 명령 13'):
            T.parse_script(rom, 0x068000)


class ExtraTests(unittest.TestCase):
    HOOK, END, TABLE = 0x06F000, 0x910, 0x06E000

    def extra_rom(self):
        code, starts = T.extra_hooks(self.HOOK, self.END, self.TABLE, 0x06)
        sites = T.site_bytes(starts)
        rom = rom_with([(self.HOOK, code), (self.TABLE, (0x8000).to_bytes(2, 'little')),
                        (0x068000, bytes.fromhex('18 01 02 3f 19 03 04 3f')),
                        *((T.SITES[n], sites[n]) for n in T.SITES)])
        return rom, starts

    def test_hooks_are_contiguous_and_jsr(self):
        code, starts = T.extra_hooks(self.HOOK, self.END, self.TABLE, 0x06)
        self.assertEqual(list(starts), ['lookup', 'run', 'bank', 'call'])
        self.assertEqual(starts['lookup'], self.HOOK)
        self.assertEqual(starts['call'] + 9, self.HOOK + len(code))
        sites = T.site_bytes(starts)
        self.assertEqual(sites['bank'][-1], 0xEA)
        self.assertEqual(sites['run'], bytes([0x20, starts['run'] & 0xFF, starts['run'] >> 8 & 0xFF]))

    def test_config_round_trip_and_talk(self):
        rom, _ = self.extra_rom()
        cfg = T.extra_config(rom)
        self.assertEqual(cfg, {'hook': self.HOOK, 'end': self.END, 'table': self.TABLE, 'bank': 0x06})
        self.assertEqual(T.extra_address(rom, 1, cfg), 0x068004)
        lines = T.talk(rom, 0x901)
        self.assertEqual(lines[0], 'talk 901: 덧붙인 스크립트 001 at 068004')
        self.assertEqual([line.split()[-1] for line in lines[1:]], ['flag-set', 'end'])
        self.assertIn('덧붙인 스크립트가 없는 번호', T.talk(rom, self.END)[0])

    def test_config_refuses_broken_hooks(self):
        self.assertIsNone(T.extra_config(rom_with([(T.SITES[n], bytes.fromhex(T.ORIGINAL_SITES[n])) for n in T.SITES])))
        rom, _ = self.extra_rom()
        rom.d[lorom(self.HOOK) + 2] ^= 0xFF
        with self.assertRaisesRegex(ValueError, '형식과 다름'):
            T.extra_config(rom)
        rom, _ = self.extra_rom()
        rom.d[lorom(T.SITES['lookup'])] = 0xEA
        with self.assertRaisesRegex(ValueError, '원본도 JSR 도 아님'):
            T.extra_config(rom)


class NativeSummaryTests(unittest.TestCase):
    def summary(self, code, limit=80):
        return T.native_summary(rom_with([(0x068000, bytes.fromhex(code))]), 0x068000, limit)

    def test_kinds(self):
        self.assertEqual(self.summary('22 77 d9 04 60'), ('가게', ['JSL 04:D977']))
        self.assertEqual(self.summary('22 d8 c6 00 00 0e 6b'), ('장면', ['JSL 00:C6D8']))
        self.assertEqual(self.summary('00 0d 01 02 9c 00 10 60'), ('값 쓰기', ['flag 02&01', 'STZ $1000']))
        self.assertEqual(self.summary('60'), ('빈 루틴', []))
        self.assertEqual(self.summary('20 00 90 4c 00 90'), ('호출', ['JSR 9000']))
        self.assertEqual(self.summary('22 00 80 30 00 0c 01 02 60'), ('호출', ['JSL 30:8000', 'flag 02|01']))

    def test_messages_and_queries(self):
        kind, ev = self.summary('00 97 05 00 95 07 00 0b 01 02 00 81 05 22 77 d9 04 60')
        self.assertEqual(kind, '메시지')
        self.assertEqual(ev, ['msg 005', 'win 07', 'flag? 02&01', 'query 81 05', 'JSL 04:D977'])

    def test_limit_stops_straight_line(self):
        kind, ev = self.summary('8d 00 10 ' * 4 + '60', limit=2)
        self.assertEqual((kind, len(ev)), ('값 쓰기', 2))


@unittest.skipUnless(ROM.exists(), '롬이 없음(rom/dq5.sfc)')
class RomTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom = Rom(ROM.read_bytes())

    def run_main(self, *args):
        out = io.StringIO()
        with mock.patch.object(sys, 'argv', ['dq5talk.py', str(ROM), *args]), redirect_stdout(out):
            code = T.main()
        return code, out.getvalue()

    def test_talk_kinds(self):
        self.assertEqual(T.talk(self.rom, 0x005), ['talk 005: 06:DBD2 특수 기능 05 -> 06:E03E'])
        script = T.talk(self.rom, 0x012)
        self.assertEqual(script[0], 'talk 012: 스크립트 001 at 06812D')
        self.assertTrue(script[1].startswith('  06812D 07 1b 01 01'))
        ask = T.talk(self.rom, 0x250)
        self.assertEqual((ask[0], len(ask)), ('talk 250: 06:B34F 묻기 616, はい 617, いいえ 618', 4))
        msg = T.talk(self.rom, 0x300)
        self.assertEqual((msg[0], len(msg)), ('talk 300: 메시지 6C6', 2))
        self.assertTrue(msg[1].endswith('{end}'))
        self.assertIn('3,200개 밖', T.talk(self.rom, 0x900)[0])
        self.assertIsNone(T.extra_config(self.rom))

    def test_check_and_calls(self):
        code, out = self.run_main('--check')
        self.assertEqual((code, out.strip()), (0, 'scripts 574, mismatch 0'))
        calls = T.native_calls(self.rom)
        self.assertEqual(len(calls), 142)
        code, out = self.run_main('--calls')
        lines = out.splitlines()
        self.assertEqual(code, 0)
        self.assertEqual(len(lines), 143)
        self.assertEqual(lines[-1], f'targets 142, calls {sum(calls.values())}')
        self.assertTrue(all(line[2] == ':' for line in lines[:-1]))

    def test_main_field_one_and_map(self):
        code, out = self.run_main('--field', '3E')
        self.assertEqual(out.strip(), 'field 3E: 묶음 0 (7E2040, 42바이트) +1 길이 1 후처리 21:99AA')
        code, out = self.run_main('012')
        self.assertEqual(out.splitlines()[0], 'talk 012: 스크립트 001 at 06812D')
        for night in ((), ('--night',)):
            code, out = self.run_main('02', '00', *night)
            self.assertEqual(code, 0)
            people = [line for line in out.splitlines() if line.startswith('(')]
            self.assertTrue(people)
            self.assertTrue(all(' gfx=' in line for line in people))
            self.assertEqual(out.count('  talk '), len(people))


if __name__ == '__main__':
    unittest.main()
