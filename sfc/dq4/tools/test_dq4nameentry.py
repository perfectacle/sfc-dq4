import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import dq4nameentry as ne


class CompositionTests(unittest.TestCase):
    def assert_composed(self, keys, expected):
        actual = ''.join(ne.GLYPHS[n] for n in ne.compose(keys))
        self.assertEqual(actual, expected)

    def test_character_names(self):
        for keys, expected in [('ㄹㅏㅇㅣㅇㅏㄴ', '라이안'), ('ㅇㅏㄹㅣㄴㅏ', '아리나'),
                               ('ㅌㅗㄹㄴㅔㅋㅗ', '톨네코')]:
            with self.subTest(name=expected):
                self.assert_composed(keys, expected)

    def test_compound_vowels(self):
        for keys, expected in [('ㄱㅗㅏㄴ', '관'), ('ㅇㅜㅓㄴ', '원'), ('ㅇㅡㅣ', '의'),
                               ('ㅗㅏ', 'ㅘ'), ('ㅜㅔ', 'ㅞ')]:
            with self.subTest(keys=keys):
                self.assert_composed(keys, expected)

    def test_final_consonant_moves_to_next_syllable(self):
        for keys, expected in [('ㄱㅏㄴㅏ', '가나'), ('ㄷㅏㄹㄱㅏ', '달가'),
                               ('ㅇㅏㄴㅎㅏ', '안하'), ('ㄱㅏㅆㅏ', '가싸')]:
            with self.subTest(keys=keys):
                self.assert_composed(keys, expected)

    def test_fourth_character_can_still_take_a_final_consonant(self):
        self.assert_composed('ㄱㅏㄴㅏㄷㅏㄹㅏㄱ', '가나다락')

    def test_fifth_character_rejection_preserves_fourth_syllable(self):
        self.assert_composed('ㄱㅏㄴㅏㄷㅏㄹㅏㄱㅏ', '가나다락')

    def test_unsupported_syllable_keeps_previous_composition(self):
        self.assertNotIn('뺴', ne.KS)
        self.assert_composed('ㅃㅒ', 'ㅃ')
        self.assert_composed('ㅃㅒㅏ', '빠')

    def test_consonant_after_lone_jamo_starts_a_new_character(self):
        self.assert_composed('ㅏㄱ', 'ㅏㄱ')
        self.assert_composed('ㄱㄴ', 'ㄱㄴ')

    def test_vowel_without_compound_starts_a_new_character(self):
        self.assert_composed('ㄱㅏㅏ', '가ㅏ')

    def test_vowel_that_cannot_follow_a_final_is_rejected(self):
        self.assertNotIn('꺠', ne.KS)
        self.assert_composed('ㅂㅏㄲㅒ', '밖')

    def test_empty_input(self):
        self.assertEqual(ne.compose(''), [])


class NameEncodingTests(unittest.TestCase):
    def test_known_saved_name(self):
        encoded = b''.join(ne.code_bytes(n) for n in ne.compose('ㄹㅏㅇㅣㅇㅏㄴ'))
        self.assertEqual(encoded, bytes.fromhex('8b 2f 93 3c 91 5a'))
        self.assertEqual(ne.decode_name(encoded + b'\x01\x01'), '라이안')

    def test_legacy_untagged_name_decodes_only_as_legacy(self):
        legacy = bytes.fromhex('16 2f 1e 3c 1c 5a 01 01')
        self.assertEqual(ne.decode_name(legacy, ne.LEGACY_HI_BASE), '라이안')
        with self.assertRaises(ValueError):
            ne.decode_name(legacy)

    def test_every_supported_character_round_trips_without_control_bytes(self):
        self.assertEqual(len(ne.KS), 2350)
        codes = set()
        for char in ne.JAMO + ne.KS:
            with self.subTest(char=char):
                encoded = ne.code_bytes(ne.GLYPHS.index(char))
                self.assertEqual(len(encoded), 2)
                # 첫 바이트는 원래 이름에 없는 85~9A, 둘째는 가나 범위. 이름 끝 01·탁점 83/84·창 접두 9F·자리 표시 B0~ 와 안 겹침
                self.assertTrue(0x85 <= encoded[0] <= 0x9A)
                self.assertTrue(0x10 <= encoded[1] <= 0x7E)
                self.assertEqual(ne.decode_name(encoded + b'\x01' * 6), char)
                self.assertNotIn(encoded, codes)
                codes.add(encoded)

    def test_full_name_uses_all_eight_bytes(self):
        encoded = b''.join(ne.code_bytes(ne.GLYPHS.index(ch)) for ch in '가나다라')
        self.assertEqual(len(encoded), 8)
        self.assertEqual(ne.decode_name(encoded), '가나다라')

    def test_terminator_ignores_unused_name_slots(self):
        self.assertEqual(ne.decode_name(b'\x01' * 8), '')
        encoded = ne.code_bytes(ne.GLYPHS.index('가'))
        self.assertEqual(ne.decode_name(encoded + b'\x01\x01' + b'\xff' * 4), '가')


class FakeAtlas:
    """한 글자는 한 칸(1, 7), 문구는 칸 수만큼(len // 3 + 1, 9)."""

    def __init__(self, jamo_width=1):
        self.jamo_width = jamo_width

    def run(self, text, font=None):
        if font is not None:
            return self.jamo_width, 7
        return len(text) // 3 + 1, 9


class BoardTests(unittest.TestCase):
    def setUp(self):
        self.record, self.keys = ne.board_record(FakeAtlas(), b'\x00' * 6, 'jamo', 0x9F)

    def test_every_grid_row_has_eleven_keys(self):
        self.assertEqual(len(self.keys), 4 * ne.ROW_CELLS)
        self.assertEqual(self.keys[:ne.ROW_CELLS],
                         [ne.JAMO.index(c) for c in 'ㅃㅉㄸㄲㅆ'] + [ne.NONE] * 3 + [ne.JAMO.index('ㅒ'), ne.JAMO.index('ㅖ'), ne.NONE])
        self.assertEqual(self.keys[ne.ROW_CELLS + 10], ne.BACK)
        self.assertEqual(self.keys[2 * ne.ROW_CELLS + 10], ne.DONE)

    def test_head_gives_width_and_height(self):
        # 머리: 01, 창 번호(old[1]), 너비+2, 높이 니블 = 줄 수(제목+빈 줄+4줄×2) + 2, 00, 줄 수
        rows = 2 + 4 * 2
        self.assertEqual(self.record[:6], bytes((1, 0, self.record[2], rows + 2, 0, rows)))
        self.assertEqual(self.record[-1], 0x80)

    def test_title_row_uses_title_text_width(self):
        n = len(ne.TITLE) // 3 + 1
        self.assertEqual(self.record[6:6 + 9], b'\x01' * 6 + bytes((0x9F, n, 9)))

    def test_wide_jamo_is_rejected(self):
        with self.assertRaises(ValueError):
            ne.board_record(FakeAtlas(jamo_width=2), b'\x00' * 6, 'jamo', 0x9F)


class FieldRecordTests(unittest.TestCase):
    def test_widens_name_field_and_adds_a_row(self):
        old = bytes((1, 2, 3, 0x25, 4, 5, 0xF3, 0xFF))
        self.assertEqual(ne.field_record(old, 0x9F),
                         bytes((1, 2, 12, 0x26, 4, 5, 0x9F, 8, ne.FIELD_COL, 0xFF)))

    def test_other_record_is_rejected(self):
        with self.assertRaises(AssertionError):
            ne.field_record(bytes(8), 0x9F)


class GlyphBlobTests(unittest.TestCase):
    def test_columns_are_packed_row_by_row(self):
        ink = [[1, 0, 0, 0, 0, 0, 0, 1]] * 16
        blob = ne.glyph_blob('f', lambda font, ch, narrow: [ink])
        self.assertEqual(len(blob), len(ne.GLYPHS) * 32)
        self.assertEqual(blob[:32], bytes([0x81] * 16 + [0] * 16))

    def test_two_columns_fill_both_halves(self):
        left, right = [[1] * 8] * 16, [[0, 1] * 4] * 16
        blob = ne.glyph_blob('f', lambda font, ch, narrow: [left, right])
        self.assertEqual(blob[:32], bytes([0xFF] * 16 + [0x55] * 16))

    def test_three_columns_are_rejected(self):
        col = [[0] * 8] * 16
        with self.assertRaises(ValueError):
            ne.glyph_blob('f', lambda font, ch, narrow: [col, col, col])


class NavigationTests(unittest.TestCase):
    def setUp(self):
        none = ne.NONE
        self.keys = [1, 2] + [none] * 9 + [3, none, 4] + [none] * 8
        table = ne.navigation(self.keys)
        n = len(self.keys)
        self.up, self.down, self.left, self.right = (table[i * n:(i + 1) * n] for i in range(4))

    def test_vertical_moves_skip_empty_and_stop_at_edges(self):
        self.assertEqual(self.down[0], 11)
        self.assertEqual(self.up[11], 0)
        self.assertEqual(self.up[0], 0)
        self.assertEqual(self.down[11], 11)
        self.assertEqual(self.down[1], 1)

    def test_horizontal_moves_wrap_within_the_row(self):
        self.assertEqual(self.right[0], 1)
        self.assertEqual(self.right[1], 0)
        self.assertEqual(self.left[0], 1)
        self.assertEqual(self.right[11], 13)
        self.assertEqual(self.left[13], 11)

    def test_empty_cells_stay_put(self):
        for table in (self.up, self.down, self.left, self.right):
            self.assertEqual(table[2], 2)


class DataAsmTests(unittest.TestCase):
    def setUp(self):
        _, keys = ne.board_record(FakeAtlas(), b'\x00' * 6, 'jamo', 0x9F)
        self.defs, self.tables = ne.data_asm(keys, {'bridge': 0x123456})

    def test_defs_carry_counts_and_bridges(self):
        self.assertIn(f'!ne_ks_count = {len(ne.KS)}\n', self.defs)
        self.assertIn('!ne_bridge = $123456\n', self.defs)
        self.assertIn(f'!ne_done = ${ne.DONE:02X}\n', self.defs)
        self.assertIn(f'!ne_cursor = {ne.GRID[1].index("ㅂ") + ne.ROW_CELLS}\n', self.defs)

    def test_syllable_table_starts_at_ga(self):
        self.assertIn('NeKsSyl:\n    dw $0000,$0001,', self.tables)

    def test_final_consonant_pairs_split_into_rest_and_move(self):
        # ㄱ ㄲ ㄳ → 남는 받침 0 0 ㄱ(1), 다음 글자로 옮길 첫소리 ㄱ ㄲ ㅅ
        self.assertIn('NeJongRest:\n    db $00,$00,$00,$01,', self.tables)
        self.assertIn('NeJongMove:\n    db $FF,$00,$01,$09,', self.tables)

    def test_long_tables_wrap_at_sixteen_values(self):
        lines = self.tables.split('NeKsSyl:\n')[1].split('\n')
        self.assertEqual(lines[0].count('$'), 16)


class ApplyTests(unittest.TestCase):
    def stub(self, tmp, code, body=''):
        path = Path(tmp) / 'asar'
        path.write_text(f'#!/bin/sh\n{body}exit {code}\n')
        path.chmod(path.stat().st_mode | stat.S_IEXEC)
        return str(path)

    def test_missing_asar_stops(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(SystemExit):
                ne.apply(b'', [], b'', {})

    def test_failed_asar_reports_output(self):
        _, keys = ne.board_record(FakeAtlas(), b'\x00' * 6, 'jamo', 0x9F)
        with tempfile.TemporaryDirectory() as tmp:
            asar = self.stub(tmp, 1, 'echo broken\n')
            with mock.patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(SystemExit) as raised:
                    ne.apply(b'rom', keys, bytes(0x18000), {}, asar=asar)
        self.assertIn('broken', str(raised.exception))

    def test_asar_gets_split_glyphs_and_patched_rom_comes_back(self):
        _, keys = ne.board_record(FakeAtlas(), b'\x00' * 6, 'jamo', 0x9F)
        with tempfile.TemporaryDirectory() as tmp:
            # asar 대신 쓰는 스크립트: 마지막 인자(롬)에 글리프 조각 크기를 덧붙이고, 목록 파일이 있어야 통과
            body = ('rom=$(eval echo \\${$#}); dir=$(dirname "$rom")\n'
                    'test -f "$dir/dq4nameentry-defs.asm" || exit 3\n'
                    'test -f "$dir/dq4nameentry-tables.asm" || exit 4\n'
                    'printf "%s" "$(wc -c < "$dir/glyphs2.bin" | tr -d " ")" >> "$rom"\n')
            asar = self.stub(tmp, 0, body)
            blob = bytes(range(256)) * 384
            with mock.patch.dict(os.environ, {}, clear=True):
                out = ne.apply(b'ROM', keys, blob, {}, asar=asar)
        self.assertEqual(out, b'ROM' + str(len(blob) - 0x10000).encode())


if __name__ == '__main__':
    unittest.main()
