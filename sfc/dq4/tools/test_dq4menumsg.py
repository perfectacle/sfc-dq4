import os
from pathlib import Path
import unittest

import dq4menumsg as mm
import dq4nameentry as ne

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / 'work' / 'base' / 'dq4-title-overture.sfc'


class LayoutTests(unittest.TestCase):
    def test_codes_follow_name_glyph_numbers(self):
        self.assertEqual(mm.code('ㄱ'), 0x3DB)
        self.assertEqual(mm.code('가'), 0x3DB + len(ne.JAMO))
        self.assertEqual(mm.code(' '), 0)
        self.assertLess(mm.code(mm.SIGNS[-1]), 0x1000)       # 24:81B0 은 1000 미만만 글자로 봄

    def test_texts_keep_slot_variable_and_end(self):
        for parts in mm.TEXTS.values():
            self.assertEqual(parts[0], mm.PAUSE)
            self.assertEqual(parts.count(mm.SLOT), 1)
            self.assertEqual(parts[-1], mm.END)

    def test_groups_stay_inside_one_bank_with_read_slack(self):
        groups = mm.plan_groups([(len(ne.GLYPHS), mm.CELL_W, mm.CELL_H), (1, 4, mm.CELL_H)])
        self.assertEqual(sum(g[0] for g in groups), len(ne.GLYPHS) + 1)
        for n, w, h, at in groups:
            end = at + (n * w * h + 7) // 8 + mm.READ_SLACK
            self.assertEqual(at >> 16, (end - 1) >> 16)
            self.assertIn(at >> 16, mm.GLYPH_BANKS)
            self.assertGreaterEqual(at & 0xFFFF, 0x8000)

    def test_group_split_keeps_read_slack_at_bank_end(self):
        # 8×1 글자 하나 = 1바이트. 뱅크 끝까지 6바이트 중 읽기 여유 2바이트를 뺀 넷만 들어감
        groups = mm.plan_groups([(5, 8, 1)], start=0x07FFFA)
        self.assertEqual([(n, at) for n, _, _, at in groups], [(4, 0x07FFFA), (1, 0x088000)])

    def test_group_skips_full_bank(self):
        self.assertEqual(mm.plan_groups([(1, 8, 1)], start=0x07FFFE)[0][3], 0x088000)

    def test_groups_refuse_bad_start_and_size(self):
        with self.assertRaises(ValueError):
            mm.plan_groups([(1, 8, 1)], start=0x077FFF)
        with self.assertRaises(ValueError):
            mm.plan_groups([(1, 16, 11)])

    def test_index_entry_crosses_lorom_bank(self):
        from dq5map import lorom
        o = lorom(mm.BASE & 0xFF8000)
        start = ((mm.BASE >> 16) - mm.INDEX_BANK) << 16 | 0x8000
        self.assertEqual(mm.index_entry(o, 0), (start << 3).to_bytes(3, 'little'))
        self.assertEqual(mm.index_entry(o, 0x8000 * 8 + 5), ((start + 0x10000) << 3 | 5).to_bytes(3, 'little'))

    def test_groups_refuse_overflow(self):
        with self.assertRaises(ValueError):
            mm.plan_groups([(0x8000, 12, 11)])

    def test_place_moves_whole_groups_to_the_next_segment(self):
        from dq5map import lorom
        # 묶음 셋(메시지 48개): 비트 0~82, 83~162(첫 바이트를 앞 묶음과 나눔), 163~239. 첫 자리 20바이트에는 첫 묶음만
        # 들어가고(둘째 묶음이 바이트 21 까지), 나머지는 둘째 묶음의 첫 바이트(10)부터 다음 자리로 간다.
        starts = [0] * 16 + [83] * 16 + [163] * 16
        blob = bytes(range(1, 31))
        d = bytearray(0x400000)
        a, b = lorom(0x618000), lorom(0x619000)
        origin = mm.place(d, blob, starts, 48, ((0x618000, 0x618014), (0x619000, 0x619100)))
        self.assertEqual(origin, [a, b - 10, b - 10])
        self.assertEqual(bytes(d[a:a + 11]), blob[:11])
        self.assertEqual(bytes(d[b:b + 20]), blob[10:])
        for k, g in enumerate((0, 16, 32)):
            self.assertEqual(d[origin[k] + (starts[g] >> 3)], blob[starts[g] >> 3])
        with self.assertRaises(ValueError):
            mm.place(bytearray(0x400000), blob, starts, 48, ((0x618000, 0x618014),))

    def test_message_count_appends_gap_free_in_blocks_of_16(self):
        self.assertEqual(mm.message_count({0x1CE: []}), mm.MESSAGES)
        self.assertEqual(mm.message_count({0xC80: [], 0xC81: []}), mm.MESSAGES + 16)
        self.assertEqual(mm.message_count({m: [] for m in range(0xC80, 0xC90)}), mm.MESSAGES + 16)
        self.assertEqual(mm.message_count({m: [] for m in range(0xC80, 0xC91)}), mm.MESSAGES + 32)
        with self.assertRaises(ValueError):
            mm.message_count({0xC81: []})
        with self.assertRaises(ValueError):
            mm.message_count({m: [] for m in range(0xC80, 0x2001)})


@unittest.skipUnless(BASE.exists() and os.environ.get('DQ4_GALMURI') and os.environ.get('ASAR'),
                     'work/base 의 서곡 채택본 롬과 DQ4_GALMURI(Galmuri BDF), ASAR 가 필요')
class BuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import dq4menupatch as mp
        cls.mp = mp
        cls.font = mp.Font('galmuri11')
        cls.out, _, _ = mp.build(BASE.read_bytes(), mp.Font('galmuri9'), mp.Font('galmuri7'), cls.font)

    def test_new_glyphs_read_back_through_group_table(self):
        from dq5map import Rom
        from dq5text import FONT_TABLE_OPERANDS, glyph
        rom = Rom(self.out)
        table, groups, start = rom.u24(FONT_TABLE_OPERANDS[0][0]), [], 0
        while start <= mm.code(mm.SIGNS[-1]):
            count, b4 = rom.u16(table) & 0xFFF, rom.u8(table + 4)
            groups.append((start, count, rom.u8(table + 1) >> 4, b4 >> 2 & 0xF, ((b4 & 3) + 7) << 16 | rom.u16(table + 2)))
            start += count
            table += 5
        for ch in ('ㄱ', ne.GLYPHS[627], ne.GLYPHS[628], '힝', ne.GLYPHS[-1], *mm.SIGNS):
            w, h, rows = glyph(rom, mm.code(ch), groups)
            pic = [''.join('#' if v else '.' for v in r) for r in rows]
            want = mm.punct_rows(self.font, ch) if ch in mm.SIGNS else (w, mm.hangul_rows(self.font, ch))
            self.assertEqual((w, pic), (want[0], want[1]), ch)

    def test_messages_decode_from_new_bank(self):
        from dq5hangul import decode_check
        msgs = decode_check(self.out, mm.HEAD, mm.INDEX_BANK)
        for m, parts in mm.TEXTS.items():
            self.assertEqual(msgs[m], mm.codes(parts))

    def test_appended_messages_read_through_moved_index(self):
        from dq5textwrite import decoded_messages
        extra = {0xC80: [mm.PAUSE, '가', mm.END], 0xC81: [mm.PAUSE, '나', mm.END]}
        out, _ = mm.apply(BASE.read_bytes(), self.font, extra)
        msgs = decoded_messages(out)
        self.assertEqual(len(msgs), mm.MESSAGES + 16)
        self.assertEqual(msgs[0xC81], mm.codes(extra[0xC81]))
        self.assertEqual(msgs[0xC82], [mm.END])
        for m, parts in mm.TEXTS.items():
            self.assertEqual(msgs[m], mm.codes(parts))


if __name__ == '__main__':
    unittest.main()
