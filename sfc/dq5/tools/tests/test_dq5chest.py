"""보물상자·タンス 류(dq5chest): 내용물 값 설명, 맵별 상자 번호 표와 FFFF 로 끝나는 항목 표, 명령줄.
표 걷기는 합성 롬으로, 상자 셀 세기와 명령줄은 롬이 있으면 본다."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import dq5chest as C  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402
from test_dq5spc import run_main  # noqa: E402

ROM = Path(__file__).resolve().parents[4] / 'rom' / 'dq5.sfc'


def put(d, addr, raw):
    d[lorom(addr):lorom(addr) + len(raw)] = raw


def table_rom():
    d = bytearray(0x200000)
    put(d, C.CHEST_MAPS, bytes([1, 2, 3, 4, 0, 2, 0xFF, 0xFF]))
    put(d, C.SEARCH_TABLE, bytes([5, 1, 10, 11, 9, 0x34, 0x12, 3, 0x40, 0xFF, 0xFF]))
    put(d, C.FOOT_TABLE, bytes([6, 0, 1, 2, 1, 0xFF, 0xFF, 4, 0x01]) * 2 + b'\xff\xff')
    put(d, C.AHEAD_TABLE, bytes([7, 3, 4, 5, 0x00, 0xD0, 0x05, 0x80, 0xFF, 0xFF]))
    put(d, C.LOWER_TABLE, b'\xff\xff')
    return Rom(d)


class DescribeTest(unittest.TestCase):
    def test_values(self):
        rom = Rom(bytearray(0x200000))
        self.assertEqual(C.describe(rom, 0xFFFF), '빈 상자')
        self.assertEqual(C.describe(rom, 0xFFFC, chest=False), '잠김')
        self.assertEqual(C.describe(rom, 0xFFFE), 'ミミック')
        self.assertEqual(C.describe(rom, 0xFFFE, chest=False), 'ツボック')
        self.assertEqual(C.describe(rom, 0xFFFD, chest=False), 'あくまのツボ')
        self.assertEqual(C.describe(rom, 0x100 + 250), '250G')
        self.assertEqual(C.describe(rom, 0xD006), 'D006 おりる階段(150)')
        self.assertEqual(C.describe(rom, 0xD0FF), 'D0FF ?')


class TableTest(unittest.TestCase):
    def setUp(self):
        self.rom = table_rom()

    def test_chest_maps_number_chests_in_order(self):
        self.assertEqual(C.chest_maps(self.rom), [(1, 2, 0, 3), (4, 0, 3, 2)])

    def test_entry_tables(self):
        self.assertEqual(C.search_entries(self.rom), [(5, 1, 10, 11, 9, 0x1234, 3, 0x40)])
        self.assertEqual(C.foot_entries(self.rom), [(6, 0, 1, 2, 1, 0xFFFF, 4, 1)] * 2)
        self.assertEqual(C.ahead_entries(self.rom), [(7, 3, 4, 5, 0xD000, 0x7E2190 + 0x85, 0x80)])
        self.assertEqual(C.lower_entries(self.rom), [])


@unittest.skipUnless(ROM.exists(), '롬이 없음(rom/dq5.sfc)')
class RomTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom = Rom(ROM.read_bytes())

    def test_chest_cells_match_table_counts(self):
        maps = C.chest_maps(self.rom)
        mismatched = [(bc, bd) for bc, bd, start, count in maps if len(C.chests(self.rom, bc, bd, start)) != count]
        self.assertEqual(mismatched, [])
        bc, bd, start, count = maps[0]
        got = C.chests(self.rom, bc, bd, start)
        self.assertEqual([n for n, _, _ in got], list(range(start, start + count)))
        self.assertEqual(got[0][2], self.rom.u16(C.CHEST_ITEMS + start * 2))

    def test_item_name_is_text(self):
        self.assertTrue(C.describe(self.rom, 0x01).startswith('물건 01 '))
        self.assertGreater(len(C.item_name(self.rom, 1)), 0)

    def test_main_all_and_one_map(self):
        code, out = run_main(C, [str(ROM)])
        self.assertEqual(code, 0)
        lines = out.splitlines()
        maps = C.chest_maps(self.rom)
        self.assertEqual(sum(ln.split()[1] == '상자' for ln in lines), sum(c for _, _, _, c in maps))
        for label, entries in (('タンス류', C.search_entries), ('발밑', C.foot_entries), ('두 칸 앞', C.ahead_entries),
                               ('아래층 상자', C.lower_entries)):
            self.assertEqual(sum(f' {label} (' in ln for ln in lines), len(entries(self.rom)), label)
        bc, bd, start, count = maps[0]
        _, one = run_main(C, [str(ROM), f'{bc:X}', f'{bd:X}'])
        mine = [ln for ln in lines if ln.startswith(f'{bc:02X}/{bd:02X} ')]
        self.assertEqual(one.splitlines(), mine)
        self.assertIn(f'7E:{(C.CHEST_FLAGS + (start >> 3)) & 0xFFFF:04X}&{C.BIT_MASKS[start & 7]:02X}', mine[0])


if __name__ == '__main__':
    unittest.main()
