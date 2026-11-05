"""맵 풀이의 명령줄(list·check·exits·npcs·lists·격자·비교)과 덤프 읽기를 합성 롬과 임시 파일로 검사한다."""
import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import dq4map as m
from test_dq4map import PRG_SIZE, Writer, decode, end, grid, put


def ines(prg):
    return b'NES\x1a' + bytes((len(prg) // 0x4000, 0, 0x10, 0)) + bytes(8) + bytes(prg)


def run_main(*argv):
    out = io.StringIO()
    with mock.patch('sys.argv', ['dq4map.py', *argv]), contextlib.redirect_stdout(out):
        try:
            m.main()
            code = 0
        except SystemExit as e:
            code = e.code
    return code, out.getvalue().splitlines()


def two_map_stream(second_ptr):
    """2×2 맵 둘: 첫 맵은 블록 1 로, 둘째는 3 으로 채운다. 둘째 시작은 첫 맵 해제 끝(0x9005)이어야 맞다."""
    prg = bytearray(PRG_SIZE)
    put(prg, *m.GROUPS, [0x00, 0xA0, 0xFF, 0xFF])
    put(prg, 0x17, 0xA000, [0x10, 0x00, 0x90, 0x11, second_ptr & 0xFF, second_ptr >> 8, 0xFF])
    for ptr, base in ((0x9000, 1), (0x9005, 3)):
        w = end(Writer()(base, 2), 2)(0, 2)
        put(prg, 0x09, ptr, [2, 2, 0x00] + list(w.bytes()))
    return prg


class DecodeExtraTests(unittest.TestCase):
    def test_attribute_rectangle_writes_one_cell_at_a_time(self):
        w = Writer()(0x1F, 5)
        end(w, 5)
        w(1, 2)
        w(0, 2)(1, 1)(1, 2)(0, 3)(5, 3)           # 위 비트 1, 사각형 (0,0)-(1,1)
        end(w, 1)
        self.assertEqual(decode(w, 4, 2, 5), grid([[0x3F, 0x3F, 0x1F, 0x1F]] * 2))

    def test_path_turns_left(self):
        w = Writer()(0, 2)(0, 2)(1, 2)
        w(2, 2)(5, 4)(1, 2)                       # 5 에서 오른쪽
        w(1, 1)(1, 2)(0, 1)                       # 왼쪽으로 돌아(위) 한 칸 → 1
        w(1, 1)(3, 2)(1, 1)
        end(w, 2)(0, 2)
        out = decode(w, 4, 4, 2)
        self.assertEqual([i for i, v in enumerate(out) if v], [1, 5])

    def test_endless_stream_is_rejected(self):
        b = m.Bits(bytearray(PRG_SIZE), 0x00, 0x8000)
        with self.assertRaises(ValueError):
            for _ in range((1 << 17) + 1):
                b.bit()

    def test_ram_flags_index_from_flag_base(self):
        ram = bytearray(0x8000)
        ram[m.FLAGS + 5] = 0x42
        self.assertEqual(m.ram_flags(ram)(5), 0x42)


class CpuDumpTests(unittest.TestCase):
    def test_file_is_read_as_is_and_folder_is_joined(self):
        with tempfile.TemporaryDirectory() as d:
            f = os.path.join(d, 'x.bin')
            Path(f).write_bytes(b'\x01\x02')
            self.assertEqual(m.cpu_dump(f), b'\x01\x02')
            sub = os.path.join(d, 'end')
            os.mkdir(sub)
            open(os.path.join(sub, 'end.ram'), 'wb').write(b'\xAB')
            open(os.path.join(sub, 'end.sram'), 'wb').write(b'\xCD' + bytes(0x1FFF))
            dump = m.cpu_dump(sub)
        self.assertEqual(len(dump), 0x8000)
        self.assertEqual((dump[0], dump[1], dump[0x5FFF], dump[0x6000]), (0xAB, 0, 0, 0xCD))


class MapCliTests(unittest.TestCase):
    def rom(self, prg):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        p = os.path.join(tmp.name, 'r.nes')
        Path(p).write_bytes(ines(prg))
        self.dir = tmp.name
        return p

    def test_list_prints_one_line_per_map(self):
        _, out = run_main(self.rom(two_map_stream(0x9005)), 'list')
        self.assertEqual(out, ['00/00 맵번호 10 09:9000   2x2   블록 2비트 0520=00',
                               '00/01 맵번호 11 09:9005   2x2   블록 2비트 0520=00'])

    def test_check_passes_when_boundaries_match(self):
        code, out = run_main(self.rom(two_map_stream(0x9005)), 'check')
        self.assertEqual((code, out), (0, ['맵 2개, 경계 1곳 중 0곳 다름']))

    def test_check_reports_wrong_next_start(self):
        code, out = run_main(self.rom(two_map_stream(0x9006)), 'check')
        self.assertEqual(code, 1)
        self.assertEqual(out[0], '00/00: 끝 09:9004 다음 시작 09:9006')
        self.assertEqual(out[1], '맵 2개, 경계 1곳 중 1곳 다름')

    def test_grid_is_hex_rows(self):
        _, out = run_main(self.rom(two_map_stream(0x9005)), '0', '1')
        self.assertEqual(out, ['03 03', '03 03'])

    def test_grid_compare_counts_differences(self):
        rom = self.rom(two_map_stream(0x9005))
        p = os.path.join(self.dir, 'at.bin')
        Path(p).write_bytes(bytes(m.BUF) + bytes((1, 1, 1, 1)))
        code, out = run_main(rom, '0', '0', '--compare', p)
        self.assertEqual((code, out), (0, ['00/00: 4 바이트 중 0 차이']))
        Path(p).write_bytes(bytes(m.BUF) + bytes((1, 1, 9, 1)))
        code, out = run_main(rom, '0', '0', '--compare', p)
        self.assertEqual((code, out), (1, ['00/00: 4 바이트 중 1 차이, 처음 (0,1)']))

    def test_exits_and_ram_compare(self):
        prg = bytearray(PRG_SIZE)
        put(prg, *m.LINKS_PTR, [0x00, 0x90])
        put(prg, 0x1B, 0x9000, [0, 0, 5, 6, 0x00, 0, 1, 7, 8, 0x00, 0xFF])
        rom = self.rom(prg)
        _, out = run_main(rom, 'exits', '0', '0')
        self.assertEqual(out, ['출구 (05,06) → 00/01 도착 (07,08) 플래그 00'])
        ram = bytearray(0x800)
        ram[0x5A0:0x5A7] = bytes((5, 6, 0, 1, 7, 8, 0))
        ram[0x5A7] = 0xFF
        p = os.path.join(self.dir, 'end.ram')
        Path(p).write_bytes(ram)
        code, out = run_main(rom, 'exits', '0', '0', '--compare', p)
        self.assertEqual((code, out[-1]), (0, 'RAM $05A0 과 같음'))
        ram[0x5A4] = 9
        Path(p).write_bytes(ram)
        code, out = run_main(rom, 'exits', '0', '0', '--compare', p)
        self.assertEqual((code, out[-1]), (1, 'RAM $05A0 과 다름'))


class NpcCliTests(unittest.TestCase):
    DAY = [0x10, 1, 2, 0x02, 4, 0x85, 0x06, 1, 0x55]

    def setUp(self):
        prg = bytearray(PRG_SIZE)
        put(prg, m.NPC_BANK, 0x8000 + 2 * 3, [0x00, 0x90])
        put(prg, m.NPC_BANK, 0x9000, [0x00] + self.DAY + [0x00])
        put(prg, *m.EVENT_LISTS, [0x00, 0x98])
        put(prg, m.EVENT_LISTS[0], 0x9800, [3, 1, 0x02, 5, 0x00, 0xA0, 4, 1, 0x10, 7, 0x00, 0xA0, 0xFF])
        put(prg, m.EVENT_LISTS[0], 0xA000, self.DAY + [0x00])
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = tmp.name
        self.rom = os.path.join(tmp.name, 'r.nes')
        Path(self.rom).write_bytes(ines(prg))

    def test_plain_day_list(self):
        _, out = run_main(self.rom, 'npcs', '3', '1')
        self.assertEqual(out, ['03/01 낮 보통 목록', ' 0: (05,06) 방향 2  머리 10 01 02 02 04 85 06  9바이트'])

    def test_night_skips_day_only_records(self):
        _, out = run_main(self.rom, 'npcs', '3', '1', '--night')
        self.assertEqual(out, ['03/01 밤 보통 목록'])

    def test_set_flag_picks_progress_list(self):
        _, out = run_main(self.rom, 'npcs', '3', '1', '--set', '6280=02')
        self.assertEqual(out[0], '03/01 낮 진행 목록 1C:A000')
        self.assertEqual(len(out), 2)

    def test_ram_compare_against_npc_table(self):
        ram = bytearray(0x8000)
        for base in (0x6F66, 0x6F86, 0x7006):
            ram[base:base + 26] = b'\xFF' * 26
        ram[0x6F66], ram[0x6F86], ram[0x7006] = 5, 6, 2
        p = os.path.join(self.dir, 'dump.bin')
        Path(p).write_bytes(ram)
        code, out = run_main(self.rom, 'npcs', '3', '1', '--compare', p)
        self.assertEqual(code, 0)
        self.assertEqual(out[-1], '인물 표(슬롯 6~) 와 1명 중 0 다름, 인물 표에서 FF 가 아닌 슬롯 1(그중 숨은 80 0)')
        ram[0x7006] = 3
        Path(p).write_bytes(ram)
        code, out = run_main(self.rom, 'npcs', '3', '1', '--ram', p, '--compare', p)
        self.assertEqual(code, 1)
        self.assertIn('1명 중 1 다름', out[-1])

    def test_ram_night_threshold(self):
        ram = bytearray(0x8000)
        ram[0x62ED] = m.NIGHT
        p = os.path.join(self.dir, 'dump.bin')
        Path(p).write_bytes(ram)
        _, out = run_main(self.rom, 'npcs', '3', '1', '--ram', p)
        self.assertEqual(out[0], '03/01 밤 보통 목록')

    def test_lists_all_and_filtered(self):
        _, out = run_main(self.rom, 'lists')
        self.assertEqual(out, ['03/01 $6280 & 02 → 1C:A000 레코드 1',
                               '04/01 $6282 & 10 → 1C:A000 레코드 1 (1C:$9C6F 가 되돌릴 수 있음)'])
        _, out = run_main(self.rom, 'lists', '3', '1')
        self.assertEqual(out, ['03/01 $6280 & 02 → 1C:A000 레코드 1'])


if __name__ == '__main__':
    unittest.main()
