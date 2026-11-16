"""실내 출구(dq5exit): 출구 셀 세기, 목적지 표 걷기와 설명, 맵별 루틴 고르기·쓰기 읽기·셀 버퍼 반영.
합성 롬으로 보고, 롬이 있으면 명령줄(도착 칸, 루틴이 바꾼 셀)도 본다."""
import io
import sys
import unittest
from contextlib import redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import dq5exit as X  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402
from test_dq5spc import run_main  # noqa: E402

ROM = Path(__file__).resolve().parents[4] / 'rom' / 'dq5.sfc'

ROUTINE = bytes.fromhex('E2 20 A9 12 8F 04 C0 7E A9 7E 48 AB A9 34 8D 0C C0 EA 8F 00 00 7E 22 00 B0 15 00 0B 01 02'
                        ' C2 20 A9 78 56 8F 10 C0 7E 6B')
SUB = bytes.fromhex('A9 99 8F 20 C0 7E 22 00 A0 15 6B')
DEST = bytes.fromhex('01 C0 05 FF 02 20 01 07 80 E0 02 03 01 09 FF FF')


def put(d, addr, raw):
    d[lorom(addr):lorom(addr) + len(raw)] = raw


def hook_entry(bc, bd, flag, routine):
    return bytes([bc, bd, flag, 0x01]) + routine.to_bytes(3, 'little') + bytes(3)


def exit_rom():
    d = bytearray(0x200000)
    put(d, 0x15A000, ROUTINE)
    put(d, 0x15B000, SUB)
    put(d, X.DEST_TABLE, DEST)
    put(d, X.EXIT_ATTRS, bytes([0x10, 0x11, 0xFF]))
    put(d, 0x15C000, bytes.fromhex('E2 20 A9 00 8F 04 C0 7E A9 10 8F 0C C0 7E A9 55 8F 00 D0 7E 6B'))
    table = (hook_entry(3, 0xFF, 0xFF, 0x15C000) + hook_entry(4, 2, 0x05, 0x15A000) + hook_entry(4, 2, 0x85, 0x15B000)
             + b'\xff')
    put(d, X.HOOK_TABLE, table)
    return Rom(d)


class CellTest(unittest.TestCase):
    def test_exit_cells_in_buffer_order(self):
        buf = bytearray(8 * 6)
        buf[1 * 8 + 4] = 0x10
        buf[4 * 8 + 7] = 0x11
        buf[5 * 8 + 4] = 0x22
        self.assertEqual(X.exit_cells(buf, 3, 2, [0x10, 0x11]), [(1, 0), (1, 1)])
        self.assertEqual(X.exit_attrs(exit_rom()), [0x10, 0x11])


class DestTest(unittest.TestCase):
    def setUp(self):
        self.rom = exit_rom()

    def test_group_start(self):
        self.assertEqual(X.group_start(self.rom, 1), X.DEST_TABLE + 1)
        self.assertEqual(X.group_start(self.rom, 2), X.DEST_TABLE + 5)
        self.assertIsNone(X.group_start(self.rom, 9))

    def test_map_exits_walk_entry_sizes(self):
        a = X.DEST_TABLE + 5
        self.assertEqual(X.map_exits(self.rom, 2, 0), [(a, b'\x20\x01\x07'), (a + 3, b'\x80')])
        self.assertEqual(X.map_exits(self.rom, 2, 1), [(a + 4, b'\xe0\x02\x03\x01\x09')])
        self.assertEqual(X.map_exits(self.rom, 1, 0), [(X.DEST_TABLE + 1, b'\xc0\x05')])
        self.assertEqual(X.map_exits(self.rom, 9, 0), [])

    def test_describe(self):
        self.assertEqual(X.describe(2, b'\x41\x02'), '02/01 의 출구 2')
        self.assertEqual(X.describe(2, b'\x20\x01\x07'), '07/00 의 출구 1')
        self.assertEqual(X.describe(2, b'\xe3\x02\x03\x01\x09'), '09/03 (2,3) 층 1')
        self.assertEqual(X.describe(2, b'\x80'), '특수(2A:F7B2)')


class HookTest(unittest.TestCase):
    def setUp(self):
        self.rom = exit_rom()

    def test_map_hook_picks_first_flag_free_match(self):
        self.assertEqual(X.map_hook(self.rom, 3, 7), 0x15C000)
        self.assertEqual(X.map_hook(self.rom, 4, 2), 0x15B000)
        self.assertEqual(X.map_hook(self.rom, 4, 3), X.HOOK_NONE)

    def test_hook_writes_follow_db_jsl_and_brk(self):
        self.assertEqual(X.hook_writes(self.rom, 0x15A000),
                         [(0x7EC004, b'\x12'), (0x7EC00C, b'\x34'), (0x7EC020, b'\x99'), (0x7EC010, b'\x78\x56')])
        # 따라간 루틴 안의 JSL 은 더 따라가지 않는다.
        self.assertEqual(X.hook_writes(self.rom, 0x15B000),
                         [(0x7EC020, b'\x99'), (0x7EC004, b'\x12'), (0x7EC00C, b'\x34'), (0x7EC010, b'\x78\x56')])

    def test_unknown_brk_stops_and_scan_limit_warns(self):
        d = bytearray(self.rom.d)
        put(d, 0x15D000, bytes.fromhex('A9 01 00 02 8F 00 C0 7E'))
        self.assertEqual(X.hook_writes(Rom(d), 0x15D000), [])
        put(d, 0x15E000, b'\xea' * (X.HOOK_SCAN_LIMIT + 1))
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(X.hook_writes(Rom(d), 0x15E000), [])
        self.assertIn(f'{X.HOOK_SCAN_LIMIT} 명령을 읽고도', err.getvalue())

    def test_apply_hook_reports_changed_exit_cells(self):
        buf = bytearray(16)
        buf[4] = 0x10
        self.assertEqual(X.apply_hook(self.rom, 3, 0, buf, 2), [(0, 0, False), (1, 0, True)])
        self.assertEqual((buf[4], buf[12]), (0x00, 0x10))
        self.assertEqual(X.apply_hook(self.rom, 4, 3, bytearray(16), 2), [])


@unittest.skipUnless(ROM.exists(), '롬이 없음(rom/dq5.sfc)')
class RomTest(unittest.TestCase):
    def test_main_lists_cells_entries_and_arrivals(self):
        code, out = run_main(X, [str(ROM), '01', '0A'])
        self.assertEqual(code, 0)
        lines = out.splitlines()
        rom = Rom(ROM.read_bytes())
        cells, _ = X.map_exit_cells(rom, 1, 0x0A, X.exit_attrs(rom))
        exits = X.map_exits(rom, 1, 0x0A)
        self.assertEqual(lines[0], f'map 01/0A: exit cells {len(cells)}, table entries {len(exits)}')
        self.assertEqual(len(lines), 1 + len(exits))
        self.assertEqual(sum('→ 도착' in ln for ln in lines), sum(e[0] & 0x60 in (0x20, 0x40) for _, e in exits))
        k = next(i for i, (_, e) in enumerate(exits) if e[0] & 0x60 == 0x20)
        e = exits[k][1]
        x, y = X.map_exit_cells(rom, e[2], e[0] & 0x1F, X.exit_attrs(rom))[0][e[1]]
        self.assertIn(f'→ 도착 {(x - 1, y)}', lines[1 + k])

    def test_main_reports_hooked_cells(self):
        _, out = run_main(X, [str(ROM), '01', '05'])
        self.assertIn('(51, 20) 를 출구 셀로 만듦', out)
        _, out = run_main(X, [str(ROM), '04', '07'])
        self.assertIn('(15, 20) 를 출구 셀로 지움', out)


if __name__ == '__main__':
    unittest.main()
