import os
from pathlib import Path
import unittest
from unittest import mock

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


class FakeFont:
    """칸마다 테두리 점만 있는 글꼴. 한글은 10×10, 부호·숫자는 4×5."""

    def __init__(self):
        box = {'bbx': (10, 10, 1, 0), 'rows': [[1] * 10] + [[1] + [0] * 8 + [1]] * 8 + [[1] * 10], 'adv': 12}
        sign = {'bbx': (4, 5, 0, 0), 'rows': [[1, 0, 0, 1]] * 5, 'adv': 5}
        self.glyphs = {**{ch: box for ch in ne.GLYPHS}, **{ch: sign for ch in mm.SIGNS}}


def synthetic_rom():
    """apply 가 원래 롬에서 읽는 자리(디코더·폰트 묶음 표·피연산자·색인 읽기)만 채운 4MB 롬."""
    from dq5hangul import DECODER, DECODER_END, WALK_INDEX_CALL, WALK_INDEX_STUB, cpu_to_bytes
    from dq5map import lorom
    from dq5text import FONT_GROUPS, FONT_TABLE_OPERANDS, GLYPHS
    from dq5textwrite import INDEX_LOAD, INDEX_LOAD_CODE
    d = bytearray(0x400000)

    def put(addr, raw):
        d[lorom(addr):lorom(addr) + len(raw)] = raw
    put(DECODER, bytes(range(1, DECODER_END - DECODER)) + b'\x60')
    put(DECODER, bytes.fromhex('088b4bab'))
    put(WALK_INDEX_STUB, bytes.fromhex('20c21064f4a2ba07e220'))
    put(WALK_INDEX_CALL, bytes.fromhex('8d8c'))
    # 원래 글자 0~3DA 를 한 묶음(8×8, 07:8000)으로
    put(FONT_GROUPS, bytes((GLYPHS & 0xFF, 8 << 4 | GLYPHS >> 8, 0x00, 0x80, 8 << 2)))
    for a, k in FONT_TABLE_OPERANDS:
        put(a, cpu_to_bytes(FONT_GROUPS + k))
    put(INDEX_LOAD, INDEX_LOAD_CODE)
    return d


def original(rom, m):
    return [m % 40 + 1, mm.END]


class SyntheticApplyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.font = FakeFont()
        cls.rom = bytes(synthetic_rom())
        with mock.patch.object(mm, 'message', original):
            cls.out, cls.info = mm.apply(cls.rom, cls.font)

    def test_messages_round_trip_through_new_tree(self):
        from dq5hangul import decode_check
        msgs = decode_check(self.out, mm.HEAD, mm.INDEX_BANK)
        self.assertEqual(len(msgs), mm.MESSAGES)
        for m, parts in mm.TEXTS.items():
            self.assertEqual(msgs[m], mm.codes(parts))
        for m in (0, 0x1CD, 0x1D1, mm.MESSAGES - 1):
            self.assertEqual(msgs[m], original(None, m))

    def test_glyphs_read_back_through_new_group_table(self):
        from dq5map import Rom
        from dq5text import FONT_TABLE_OPERANDS, glyph
        rom = Rom(self.out)
        table = rom.u24(FONT_TABLE_OPERANDS[0][0])
        for a, k in FONT_TABLE_OPERANDS:
            self.assertEqual(rom.u24(a), table + k)
        groups, start = [], 0
        while start <= mm.code(mm.SIGNS[-1]):
            count, b4 = rom.u16(table) & 0xFFF, rom.u8(table + 4)
            groups.append((start, count, rom.u8(table + 1) >> 4, b4 >> 2 & 0xF, ((b4 & 3) + 7) << 16 | rom.u16(table + 2)))
            start += count
            table += 5
        self.assertEqual(groups[0][:2], (0, 0x3DB))
        for ch in ('ㄱ', ne.GLYPHS[1023], ne.GLYPHS[1024], ne.GLYPHS[-1], '.', ',', '0', 'Z'):
            w, h, rows = glyph(rom, mm.code(ch), groups)
            pic = [''.join('#' if v else '.' for v in r) for r in rows]
            want = mm.punct_rows(self.font, ch) if ch in mm.SIGNS else (w, mm.hangul_rows(self.font, ch))
            self.assertEqual((w, pic), want, ch)

    def test_hooks_point_at_new_decoder(self):
        from dq5hangul import DECODER, WALK_INDEX_CALL, WALK_INDEX_STUB
        from dq5map import lorom
        o = lorom(DECODER)
        self.assertEqual(self.out[o:o + 5], bytes((0x22, 0x00, 0x80, mm.HEAD >> 16, 0x60)))
        o = lorom(WALK_INDEX_STUB)
        self.assertEqual(self.out[o + 5:o + 7], bytes((0x09, mm.INDEX_BANK)))
        o = lorom(WALK_INDEX_CALL)
        self.assertEqual(self.out[o:o + 2], (WALK_INDEX_STUB & 0xFFFF).to_bytes(2, 'little'))
        h = lorom(mm.HEAD)
        # 사본 디코더는 끝 RTS 를 RTL 로
        self.assertEqual(self.out[h + DECODER_LEN - 1], 0x6B)

    def test_appended_messages_move_the_index(self):
        from dq5hangul import decode_check
        from dq5map import lorom
        from dq5textwrite import INDEX_LOAD
        extra = {0xC80: [mm.PAUSE, '가', mm.END], 0xC81: [mm.PAUSE, '나', mm.END]}
        with mock.patch.object(mm, 'message', original):
            out, _ = mm.apply(self.rom, self.font, extra)
        load = out[lorom(INDEX_LOAD):lorom(INDEX_LOAD) + 17]
        self.assertEqual(load[1], mm.INDEX_AT >> 16)
        self.assertEqual([int.from_bytes(load[o:o + 2], 'little') for o in (5, 10, 15)],
                         [(mm.INDEX_AT & 0xFFFF) + k for k in range(3)])
        msgs = decode_check(out, mm.HEAD, mm.INDEX_BANK, index=mm.INDEX_AT, count=mm.MESSAGES + 16)
        self.assertEqual(msgs[0xC81], mm.codes(extra[0xC81]))
        self.assertEqual(msgs[0xC82], [mm.END])

    def test_rejects(self):
        from dq5hangul import WALK_INDEX_CALL
        from dq5map import lorom
        with self.assertRaisesRegex(ValueError, '겹치는 번호'):
            mm.apply(self.rom, self.font, {0x1CE: ['가']})
        bad = bytearray(self.rom)
        bad[lorom(WALK_INDEX_CALL)] = 0
        with mock.patch.object(mm, 'message', original), self.assertRaisesRegex(ValueError, '예상한 원래 바이트'):
            mm.apply(bytes(bad), self.font)
        full = bytearray(self.rom)
        full[lorom(mm.HEAD) + 0x40] = 1
        with mock.patch.object(mm, 'message', original), self.assertRaisesRegex(ValueError, '비어 있지 않음'):
            mm.apply(bytes(full), self.font)


DECODER_LEN = 0x249E47 - 0x249E02


if __name__ == '__main__':
    unittest.main()
