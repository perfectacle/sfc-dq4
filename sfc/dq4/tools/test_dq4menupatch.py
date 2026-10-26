import hashlib
import os
from pathlib import Path
import unittest

import dq4menupatch as mp
import dq4nameentry as ne

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / 'work' / 'base' / 'dq4-title-overture.sfc'


class FakeAtlas:
    def __init__(self, widths):
        self.widths, self.runs = widths, {}

    def run(self, text):
        if text not in self.runs:
            self.runs[text] = (self.widths[text], 2 + len(self.runs))
        return self.runs[text]


class RecordTests(unittest.TestCase):
    def test_item_record_sizes_window_to_longest_row(self):
        atlas = FakeAtlas({'가나': 3, '다': 2})
        head = bytes.fromhex('02040ea30001')
        rec = mp.item_record(atlas, head, [['가나'], ['다', b'\x01\x03']])
        # 커서 FE 1 + 열 2 + 공백·숫자 2 = 5, 테두리 2 → 7. 높이는 3 → 4
        self.assertEqual(rec[:6], bytes.fromhex('020407a40001'))
        self.assertEqual(rec[6:], bytes.fromhex('fe9f0302ff fe9f020301 03ff 80'.replace(' ', '')))

    def test_speed_record_keeps_digit_items(self):
        old = bytes.fromhex('070f122800061419282f28012a411284ffff'
                            'ff293311' + '01' * 10 + '141e11ffff' + 'fe03fe04fe05fe06fe07fe08fe09fe0aff80')
        atlas = FakeAtlas({mp.SPEED_TEXT[0]: 15, mp.SPEED_TEXT[1]: 3, mp.SPEED_TEXT[2]: 3})
        rec = mp.speed_record(atlas, old)
        self.assertTrue(rec.endswith(bytes.fromhex('fe03fe04fe05fe06fe07fe08fe09fe0aff80')))
        self.assertIn(b'\x01' * 10, rec)

    def test_hook_loop_branch_lands_on_loop_start(self):
        code = mp.hook_code()
        bne = code.index(bytes((0xA3, 0x04, 0x3A, 0x83, 0x04, 0xD0))) + 5
        start = bne + 2 + (code[bne + 1] - 0x100)
        self.assertEqual(code[start:start + 4], bytes((0x8A, 0x99, 0x00, 0x00)))

    def test_b_check_branches_reach_ignore_and_keep(self):
        code = mp.b_check()
        ignore = code.index(bytes((0x68, 0x68, 0x60)))
        for i in range(len(mp.TOP_MENUS) - 1):
            at = 8 + i * 4
            self.assertEqual(code[at + 2], 0xF0)
            self.assertEqual(at + 4 + code[at + 3], ignore)
        last = 8 + (len(mp.TOP_MENUS) - 1) * 4
        self.assertEqual(last + 4 + code[last + 3], ignore + 3)
        self.assertEqual(code[ignore + 3:], bytes.fromhex('ade80a60'))

    def test_tiles_leave_bg12_tile_zero_empty(self):
        atlas = mp.Atlas.__new__(mp.Atlas)
        atlas.cols = [None] * mp.Atlas.FIRST + [[[1] * 8] * mp.BAND]
        tiles = atlas.tiles()
        self.assertEqual(len(tiles), 0x2000)
        self.assertEqual(tiles[:32], bytes(32))      # BG1·BG2 4bpp 타일 0 = BG3 타일 200·201
        self.assertEqual(tiles[32:34], b'\xff\xff')


@unittest.skipUnless(BASE.exists() and os.environ.get('DQ4_GALMURI') and os.environ.get('ASAR'),
                     'work/base 의 서곡 채택본 롬과 DQ4_GALMURI(Galmuri BDF), ASAR 가 필요')
class BuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom = BASE.read_bytes()
        cls.out, cls.atlas, cls.records = mp.build(cls.rom, mp.Font('galmuri11'), mp.Font('galmuri11c'))

    def test_base_is_overture_build(self):
        self.assertEqual(hashlib.sha1(self.rom).hexdigest(), mp.BASE_SHA1)

    def test_static_atlas_leaves_list_and_input_name_tiles_empty(self):
        self.assertLessEqual(len(self.atlas.cols), 0xD0)
        self.assertGreaterEqual(ne.FIELD_COL, 0xD0 + 3 * 8)
        self.assertLessEqual(ne.FIELD_COL + 8, mp.COLUMNS)
        start = mp.lorom(mp.TILES)
        for row in (0, 0x1000):
            reserved = self.out[start + row + 0xD0 * 16:start + row + 0x1000]
            self.assertEqual(reserved, bytes(0x30 * 16))

    def test_name_padding_glyph_is_blank_in_built_rom(self):
        start = mp.lorom((ne.GLYPH_BANK << 16) | 0x8000)
        blank = start + ne.GLYPHS.index('　') * 32
        star = start + ne.GLYPHS.index('＊') * 32
        self.assertEqual(self.out[blank:blank + 32], bytes(32))
        self.assertNotEqual(self.out[star:star + 32], bytes(32))

    def test_shared_windows_keep_rom_records(self):
        for n in mp.SHARED:
            a, old, _ = self.records[n]
            self.assertEqual(mp.window_addr(self.out, n) & 0xFFFF, a & 0xFFFF)
            offset = mp.lorom(mp.window_addr(self.rom, n))
            self.assertEqual(self.out[offset:offset + len(old)], old)
            self.assertEqual(mp.window_span(self.rom, n), old)

    def test_cursor_tramps_call_original_movers(self):
        for site, target in mp.CURSOR_MOVES.items():
            o = mp.lorom(site)
            self.assertEqual(self.out[o], 0x20)
            t = mp.lorom(0x040000 | int.from_bytes(self.out[o + 1:o + 3], 'little'))
            self.assertEqual(self.out[t + 4:t + 7], bytes((0x20, target & 0xFF, target >> 8)))

    def test_records_fit_and_keep_window_terminators(self):
        for n, (a, old, new) in self.records.items():
            self.assertEqual(new[-1], 0xFF if n == 0x6B else 0x80, f'{n:02X}')
            if n not in mp.SHARED:
                self.assertEqual(mp.window_record(self.out, a), new, f'{n:02X}')


if __name__ == '__main__':
    unittest.main()
