"""상자·발밑·タンス·대화로 받는 물건 표와 명령줄 출력을 합성 맵·인물·스크립트로 검사한다."""
import json
import os
import tempfile
import unittest

import dq4block
import dq4chest as c
import dq4map
import dq4talk
from test_dq4datamore import cli_prg, run_cli
from test_dq4map import Writer, end

B15 = 0x15


def put(prg, bank, addr, data):
    o = bank * 0x4000 + (addr & 0x3FFF)
    prg[o:o + len(data)] = bytes(data)


def word(v):
    return [v & 0xFF, v >> 8]


def chest_world():
    """맵 01/00(상자 칸 2개), 개수 표에만 있는 맵 01/02·05/00, 발밑 둘, タンス 하나, 대화로 주는 인물 셋."""
    prg = cli_prg()                                            # 아이템 0 = ア, 1 = イ
    put(prg, *dq4map.GROUPS, word(0xA000) + word(0xA001) + [0xFF, 0xFF])
    put(prg, 0x17, 0xA000, [0xFF, 0x01, 0x00, 0x90, 0xFF])
    bank = dq4map.data_bank(1, 0)
    w = Writer()(0, 2)(0, 2)(1, 2)(3, 2)(2, 4)(3, 2)(5, 4)    # 바탕 0, 블록 1, 점 2·5
    end(w, 2)(0, 2)
    put(prg, bank, 0x9000, [4, 3, 0x00] + list(w.bytes()))
    put(prg, dq4block.B08, dq4block.PATCH_G, [0x01, 0x80])      # 맵 01/00 에서 블록 1 의 속성을 04(상자)로
    put(prg, dq4block.B08, dq4block.PATCH_K, [0x00])
    put(prg, dq4block.B08, dq4block.PATCH_B, [0x01])
    put(prg, dq4block.B08, dq4block.PATCH_V, [0x04])
    put(prg, c.CHEST_BANK, c.COUNT_PTR, word(0xA000) + word(0xA100))
    put(prg, c.CHEST_BANK, 0xA000, [0x01, 0x00, 2, 0x01, 0x02, 3, 0x05, 0x00, 1, 0xFF])
    put(prg, c.CHEST_BANK, 0xA100, [0x01, 0x85, 0x00, 0xFF, 0xFE, 0x85])
    put(prg, c.CHEST_BANK, c.SPECIAL_CHEST, [2, 0xFF, 0xFE])
    put(prg, c.CHEST_BANK, c.FEET_TABLE, [0x01, 0x80, 3, 2, 0x00, 0x01, 0x00, 4, 3, 0xA9, 0xFF])
    put(prg, c.CHEST_BANK, c.FLAG_ITEMS + 9, [0x82])
    put(prg, c.CHEST_BANK, c.SPECIAL_FEET, [0])
    put(prg, c.CHEST_BANK, dq4block.POTS, [0x01, 0x00, 7, 4, 0x01, 0x03, 0x10, 0xFF])
    put(prg, 0x05, 0x8002, word(0x9000))
    npc = lambda tid, x, y: [0x10, 0, 0, 0, tid, x, y, 1, 0x2A]
    put(prg, 0x05, 0x9000, npc(0x10, 5, 6) + npc(0x11, 6, 8) + npc(0x12, 9, 10) + [0])
    put(prg, *dq4map.EVENT_LISTS, word(0x9800))
    put(prg, 0x1C, 0x9800, [0xFF])
    put(prg, B15, 0x9F00, [0x3F])
    for tid in range(dq4talk.SCRIPT_FIRST, dq4talk.YESNO_FIRST):
        put(prg, B15, dq4talk.SCRIPTS + 2 * (tid - dq4talk.SCRIPT_FIRST), word(0x9F00))
    script = lambda tid, code, at: (put(prg, B15, at, code),
                                    put(prg, B15, dq4talk.SCRIPTS + 2 * (tid - dq4talk.SCRIPT_FIRST), word(at)))
    script(0x10, [0x07, 0x14, 0x00, 0x00, 0xA0, 0x3F], 0x9000)         # 낮이면 A000 부름
    script(0x11, [0x00, 0x00, 0xA1, 0x3F], 0x9010)
    script(0x12, [0x00, 0x00, 0xA2, 0x3F], 0x9020)
    put(prg, B15, 0xA000, [0xA9, 0x01, 0x20, 0xB1, 0xB0, 0x60])          # イ 받음
    put(prg, B15, 0xA100, [0xA9, 0x00, 0x85, 0x70, 0xA9, 0x00, 0x85, 0x71, 0xA9, 0x64, 0x00, 0x4B, 0x73,
                           0x00, 0x05, 0xCB, 0x40, 0x60])                 # 100G, 플래그 05 |= 40
    put(prg, B15, 0xA200, [0x20, 0xC9, 0x9A, 0xA9, 0x01, 0x20, 0xB1, 0xB0, 0x60])   # 예/아니오 검사 뒤 받음
    return prg


class MapCellTests(unittest.TestCase):
    def setUp(self):
        self.prg = chest_world()

    def test_chest_cells_come_from_block_kind_in_raster_order(self):
        self.assertEqual(c.chest_cells(self.prg, 1, 0), [(2, 0), (1, 1)])
        self.assertIsNone(c.chest_cells(self.prg, 1, 2))

    def test_load_returns_none_for_unknown_map(self):
        self.assertIsNone(c.load(self.prg, 9, 9))
        m, w, h, buf = c.load(self.prg, 1, 0)
        self.assertEqual((m[:2], w, h, bytes(buf)), ((1, 0), 4, 3, bytes([0, 0, 1, 0, 0, 1, 0, 0, 0, 0, 0, 0])))

    def test_chests_use_cells_and_global_number(self):
        out = c.chests(self.prg, 1, 0)
        self.assertEqual([(n, x, y, b) for n, x, y, b, _ in out], [(0, 2, 0, 0x01), (1, 1, 1, 0x85)])
        self.assertEqual([d for *_, d in out], ['イ', '200G'])

    def test_check_counts_mismatch_and_unlisted_places(self):
        out = run_cli(c.main, self.prg, 'check')
        self.assertEqual(out, ['맵 1개, 개수 표 3줄(상자 6개), 다름 0, 맵 목록에 없는 장소 01/02 05/00'])
        put(self.prg, c.CHEST_BANK, 0xA000, [0x01, 0x00, 3])
        out = run_cli(c.main, self.prg, 'check')
        self.assertEqual(out[0], '01/00: 상자 칸 2, 표 3')
        self.assertTrue(out[1].startswith('맵 1개, 개수 표 3줄(상자 7개), 다름 1'))

    def test_check_hints_when_map_missing_from_count_table(self):
        put(self.prg, c.CHEST_BANK, 0xA000, [0x01, 0x02, 3, 0xFF])
        out = run_cli(c.main, self.prg, 'check')
        self.assertEqual(out[0], '01/00: 상자 칸 2, 표 0 — 표에 없어 01/02 와 같은 순번')


class ShowTests(unittest.TestCase):
    def setUp(self):
        self.prg = chest_world()

    def test_show_one_map_lists_chests_and_feet(self):
        out = run_cli(c.main, self.prg, '01', '00')
        self.assertEqual(out[0], '상자 #  0 (02,00) 01 イ  플래그 $625D 비트 80')
        self.assertEqual(out[1], '상자 #  1 (01,01) 85 200G  플래그 $625D 비트 40')
        self.assertEqual(out[2], '발밑 (03,02) 00 ア')
        self.assertEqual(out[3], '발밑 (04,03) A9 80G  플래그 $6273 비트 40')
        self.assertEqual(len(out), 4)

    def test_compare_marks_opened_chests(self):
        sram = bytearray(0x2000)
        sram[c.OPENED - 0x6000] = 0x80
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'end.sram')
            with open(path, 'wb') as f:
                f.write(sram)
            out = run_cli(c.main, self.prg, '01', '00', '--compare', path)
        self.assertTrue(out[0].endswith('  열었음'))
        self.assertTrue(out[1].endswith('  닫힘'))

    def test_all_lists_every_counted_map_and_feet(self):
        out = run_cli(c.main, self.prg, 'all')
        self.assertEqual(out[0], '# 01/00')
        self.assertIn('# 01/02', out)
        self.assertIn('상자 #  3 (?? ??) FF 빈 상자(메시지 0297, 1E:$B4CE)', out)
        self.assertEqual(out[-3], '# 발밑')
        self.assertEqual(out[-2], '01/00 (03,02) 00 ア')
        self.assertEqual(out[-1], '01/00 (04,03) A9 80G  플래그 $6273 비트 40')


class LootTests(unittest.TestCase):
    def setUp(self):
        self.prg = chest_world()
        self.rows = c.loot(self.prg)

    def test_row_order_and_kinds(self):
        got = [(r['map'], r['how']) for r in self.rows if r['map'] == (1, 0)]
        self.assertEqual([h for _, h in got], ['상자', '상자', '발밑', '발밑', 'タンス·つぼ',
                                                '대화 010 15:A000', '대화 011 15:A100', '대화 012 15:A200'])

    def test_pot_and_feet_rows(self):
        by_how = {r['how']: r for r in self.rows if r['map'] == (1, 0) and r['how'] in ('발밑', 'タンス·つぼ')}
        pot = by_how['タンス·つぼ']
        self.assertEqual((pot['x'], pot['y'], pot['what'], pot['flag']), (7, 4, 'イ', '$6276&10'))

    def test_talk_gift_conditions(self):
        talk = {r['how'].split()[1]: r for r in self.rows if r['how'].startswith('대화')}
        self.assertEqual(talk['010']['what'], '받음 イ(01)')
        self.assertEqual(talk['010']['cond'], ['day', '낮'])
        self.assertEqual((talk['010']['x'], talk['010']['y']), (5, 6))
        self.assertEqual(talk['011']['what'], '골드 100')
        self.assertEqual((talk['011']['cond'], talk['011']['flag']), (['낮'], '$6280|=40'))
        self.assertEqual(talk['012']['cond'], ['낮', '루틴 안 yes'])
        self.assertEqual(talk['012']['what'], '받음 イ(01)')

    def test_unlisted_maps_have_no_position(self):
        row = next(r for r in self.rows if r['map'] == (5, 0))
        self.assertEqual((row['x'], row['y'], row['what']), (None, None, '200G'))

    def test_show_loot_text_and_summary(self):
        out = run_cli(c.main, self.prg, 'loot')
        self.assertIn('01/00 (05,06) 대화 010 15:A000 [day & 낮] → 받음 イ(01)', out)
        self.assertIn('01/00 (06,08) 대화 011 15:A100 [낮] → 골드 100  플래그 $6280|=40', out)
        self.assertEqual(out[-1], '12줄: 상자 6, 발밑 2, タンス·つぼ 1, 대화 3')
        self.assertEqual(len(self.rows), 12)

    def test_show_loot_json(self):
        data = json.loads('\n'.join(run_cli(c.main, self.prg, 'loot', '--json')))
        self.assertEqual(len(data), 12)
        self.assertEqual(data[0]['map'], '01/00')
        self.assertEqual(data[0]['what'], 'イ')

    def test_flag_text(self):
        self.assertEqual(c.flag_text(5, 0x40), '$6280|=40')

    def test_gift_paths_collects_branch_conditions_and_same_block_flags(self):
        tree = [('flag|=', [5, 0x40]),
                ('if', False, 0x14, [], [('call', [0x00, 0xA0])], [('call', [0x00, 0xA1])])]
        self.assertEqual(c.gift_paths(tree, {0xA000: [], 0xA100: []}),
                         [(0xA000, ['day'], [(5, 0x40)]), (0xA100, ['아님(day)'], [(5, 0x40)])])
        self.assertEqual(c.gift_paths(tree, {}), [])


if __name__ == '__main__':
    unittest.main()
