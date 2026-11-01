"""대사 텍스트 풀기(6비트 부호 순서·뱅크 넘김·가나 전환·사전 단어·메시지 경계·기호 왕복)를 합성 롬으로 검사한다."""
import contextlib
import io
import unittest

import dq4text as t

PRG_SIZE = 32 * 0x4000
CODE_A, CODE_B, CODE_C = 0x01, 0x02, 0x03
DICT_ADDR_GAP = 0


def ines(prg):
    return b'NES\x1a' + bytes((len(prg) // 0x4000, 0, 0x10, 0)) + bytes(8) + bytes(prg)


def put(prg, bank, addr, data):
    o = t.off(bank, addr)
    prg[o:o + len(data)] = bytes(data)


def word(v):
    return v.to_bytes(2, 'little')


def pack(codes, phase=0):
    """롬 순서(앞 부호가 높은 비트)로 6비트 부호를 잇는다. 테스트 쪽 독립 구현."""
    bits = '0' * (6 * phase % 8) + ''.join(f'{c:06b}' for c in codes)
    bits += '0' * (-len(bits) % 8)
    return [int(bits[i:i + 8], 2) for i in range(0, len(bits), 8)]


def base_prg():
    prg = bytearray(PRG_SIZE)
    chars = [0] * 128
    for c in range(64):
        chars[c] = 0x01 + c if c < 0x30 else 0x00
        chars[64 + c] = 0x40 + c if c < 0x2A else 0x00
    chars[t.END] = chars[64 + t.END] = 0xF9
    chars[0x30] = 0xF0           # F0 은 사전 0번 단어로 바뀐다
    chars[0x31] = 0xFC
    put(prg, *t.CHARS, chars)
    return prg


# 메시지 셋: 0 은 가나 전환, 1 은 사전 단어(그룹 1 의 둘째), 2 는 F0 과 줄바꿈
MESSAGES = [
    [CODE_A, 0x3C, CODE_B, t.END],
    [CODE_C, 0x3D, 0x21, t.END],
    [0x30, 0x31, CODE_A, t.END],
]
WORDS = {0: [[0x10, 0x11]], 1: [[0x20], [0x21, 0x22]]}


def message_rom():
    """모든 메시지를 1B:A500 에 두고, 바로 뒤에 사전을 둔다(본문 끝 = 사전 시작)."""
    prg = base_prg()
    put(prg, *t.BANK_BOUNDS, [0, 0, 0, 0, 0, 0xFF])
    text = pack([c for m in MESSAGES for c in m])
    put(prg, t.WORD_BANK, 0xA500, text)
    dict_at = 0xA500 + len(text)
    a = dict_at
    groups = []
    for g in range(2):
        groups.append(a)
        for w in WORDS[g]:
            put(prg, t.WORD_BANK, a, w + [t.WORD_END])
            a += len(w) + 1
    put(prg, *t.WORDS, b''.join(word(g) for g in groups))
    blocks = [0xA500] + [dict_at] * (t.block_count() - 1)
    put(prg, *t.BLOCKS, b''.join(word(b) for b in blocks))
    return t.Rom(ines(prg))


class TextTests(unittest.TestCase):
    def test_marks_move_after_their_glyph(self):
        self.assertEqual(t.text([0x3D, 0x10]), 'が')
        self.assertEqual(t.text([0x3E, 0x24, 0xFC, 0x01]), 'ぱ\n0')

    def test_unknown_byte_is_hex(self):
        self.assertEqual(t.text([0x90]), '[90]')

    def test_shown_adds_period_only_after_plain_glyph(self):
        self.assertEqual(t.shown([0x06, 0xF9]), [0x06, 0x3F, 0xF9])
        self.assertEqual(t.shown([0x6E, 0xF9]), [0x6E, 0xF9])
        self.assertEqual(t.shown([0xF9]), [0xF9])

    def test_auto_quote(self):
        self.assertTrue(t.auto_quote(0x0500, [0x06]))
        self.assertFalse(t.auto_quote(0x0500, [0xF1]))
        self.assertFalse(t.auto_quote(0x04FF, [0x06]))


class CodesTests(unittest.TestCase):
    def test_four_codes_per_three_bytes_at_every_phase(self):
        codes = [0x3F, 0x00, 0x2A, 0x15, 0x01, 0x39, 0x22]
        for phase in range(4):
            prg = bytearray(PRG_SIZE)
            put(prg, 0x01, 0x9000, pack([0] * phase + codes))
            c = t.Codes(t.Rom(ines(prg)), 0x01, 0x9000)
            got = [c.next() for _ in range(phase + len(codes))][phase:]
            self.assertEqual(got, codes, f'phase {phase}')

    def test_bank_end_continues_in_next_bank(self):
        prg = bytearray(PRG_SIZE)
        data = pack([0x11, 0x22, 0x33, 0x01, 0x02, 0x03, 0x04, 0x05])
        put(prg, 0x02, 0xBFD8 - 3, data[:3])
        put(prg, 0x03, 0x8000, data[3:])
        c = t.Codes(t.Rom(ines(prg)), 0x02, 0xBFD8 - 3)
        self.assertEqual([c.next() for _ in range(8)], [0x11, 0x22, 0x33, 0x01, 0x02, 0x03, 0x04, 0x05])
        self.assertEqual(c.bank, 0x03)

    def test_bank_four_overflows_into_dictionary_bank(self):
        prg = bytearray(PRG_SIZE)
        data = pack([0x11, 0x22, 0x33, 0x01, 0x02])
        put(prg, 0x04, 0xBFD8 - 3, data[:3])
        put(prg, t.WORD_BANK, 0xA500, data[3:])
        c = t.Codes(t.Rom(ines(prg)), 0x04, 0xBFD8 - 3)
        self.assertEqual([c.next() for _ in range(5)], [0x11, 0x22, 0x33, 0x01, 0x02])
        self.assertEqual((c.bank, c.ptr), (t.WORD_BANK, 0xA500))

    def test_pack_matches_the_reader(self):
        for phase in range(4):
            codes = [0x3B, 0x04, 0x39]
            packed = t._pack(codes, phase)
            prg = bytearray(PRG_SIZE)
            put(prg, 0x01, 0x8000, [p for p, _ in packed])
            c = t.Codes(t.Rom(ines(prg)), 0x01, 0x8000)
            c.phase = phase
            self.assertEqual([c.next() for _ in codes], codes)
            self.assertEqual(packed[0][1] >> (8 - 6 * phase % 8) if phase else packed[0][1], 0 if phase else 0xFF)


class StartTests(unittest.TestCase):
    def test_bank_comes_from_bound_table(self):
        prg = bytearray(PRG_SIZE)
        put(prg, *t.BANK_BOUNDS, [2, 5, 7, 9, 11, 0xFF])
        put(prg, *t.BLOCKS, b''.join(word(0x8000 + b) for b in range(t.block_count())))
        rom = t.Rom(ines(prg))
        self.assertEqual(rom.start(0x00), (0, 0x8000))
        self.assertEqual(rom.start(3 << 5 | 7), (1, 0x8003))   # 블록 번호는 메시지 >> 5
        self.assertEqual(rom.start(11 << 5), (t.WORD_BANK, 0x800B))


class MessageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom = message_rom()

    def test_kana_toggle_switches_table_half(self):
        self.assertEqual(t.message_bytes(self.rom, 0), [0x02, 0x40 + CODE_B, 0xF9])

    def test_dictionary_word_by_group_and_index(self):
        self.assertEqual(t.message_bytes(self.rom, 1), [0x04, 0x21, 0x22, 0xF9])

    def test_f0_inserts_word_zero(self):
        self.assertEqual(t.message_bytes(self.rom, 2), [0x10, 0x11, 0xFC, 0x02, 0xF9])

    def test_message_start_phase_follows_previous_codes(self):
        (bank, addr, phase), codes = t.message_codes(self.rom, 1)
        self.assertEqual((bank, addr, phase), (t.WORD_BANK, 0xA503, 0))
        (bank, addr, phase), _ = t.message_codes(self.rom, 2)
        n = len(MESSAGES[0]) + len(MESSAGES[1])
        self.assertEqual((addr, phase), (0xA500 + n * 6 // 8, n % 4))

    def test_valid_messages_stop_at_dictionary(self):
        self.assertEqual(t.valid_messages(self.rom), [0, 1, 2])

    def test_export_round_trips(self):
        msgs = t.export_messages(self.rom)
        self.assertEqual([m['id'] for m in msgs], ['0000', '0001', '0002'])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(t.check_export(self.rom, msgs, [], []))

    def test_check_export_catches_wrong_codes(self):
        msgs = t.export_messages(self.rom)
        msgs[1]['codes'] = '03 3D 20 39'
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertFalse(t.check_export(self.rom, msgs, [], []))
        self.assertIn('메시지 0001', out.getvalue())


class SymbolTests(unittest.TestCase):
    def test_round_trip_with_marks_and_args(self):
        bs = [0x3D, 0x10, 0xEE, 0x12, 0xF6, 0xF7, 0x66, 0xF9]
        s = t.symbolize(bs)
        self.assertEqual(s, 'が{SOUND:12}{NAME:0}{ITEM:1}{66}{END}')
        self.assertEqual(t.unsymbolize(s), bs)

    def test_mark_before_tile_that_has_no_composed_char_stays_hex(self):
        bs = [0x3D, 0x01]
        self.assertEqual(t.unsymbolize(t.symbolize(bs)), bs)

    def test_slot_numbers_must_be_in_order(self):
        with self.assertRaises(ValueError):
            t.unsymbolize('{NAME:1}')

    def test_unknown_symbol_and_stray_arg(self):
        with self.assertRaises(ValueError):
            t.unsymbolize('{NOPE}')
        with self.assertRaises(ValueError):
            t.unsymbolize('{END:3}')


class WindowTests(unittest.TestCase):
    def setUp(self):
        prg = bytearray(PRG_SIZE)
        put(prg, *t.WINDOW_GROUPS, word(0xA578) + word(0xA600))
        put(prg, *t.WINDOW_LIMITS, [2, 0])          # 그룹 0: 항목 0 만 루틴
        put(prg, 0x16, 0xA578, word(0xB000) + word(0xA700) + word(0xA703) + word(0xA707))
        put(prg, 0x16, 0xA700, [0x01, 0x82, 0x02])           # 항목 1: 「0」+항목 2+「1」
        put(prg, 0x16, 0xA703, [0x10, 0x80, 0x11, 0x81])     # 항목 2: 안의 80 이상은 건너뜀
        self.rom = t.Rom(ines(prg))

    def test_entry_kinds_and_lengths(self):
        self.assertEqual(t.window_entry(self.rom, 0, 0), ('code', 0xB000))
        self.assertEqual(t.window_entry(self.rom, 0, 1), ('str', 0xA700, [0x01, 0x82, 0x02]))

    def test_nested_string_drops_its_own_calls(self):
        self.assertEqual(t.window_bytes(self.rom, 0, 1), [0x01, 0x10, 0x11, 0x02])
        self.assertEqual(t.window_bytes(self.rom, 0, 0), [('code', 0)])

    def test_layout_alias_head_and_tokens(self):
        rom = self.rom
        rec = [0x34, 0x25, 0x40, 0x01, 0x81, 0xA2, 0x02, 0xC6, 0xC0, 0x05, 0xD3, 0xE1]
        put(prg := bytearray(rom.prg), 0x16, 0xA800, [0x13] + rec)
        put(prg, *t.WINDOW_RECORDS, word(0xA800) + word(0xA801) + word(0xA801 + len(rec)))
        rom.prg = bytes(prg)
        lay = t.window_layout(rom, 0)
        self.assertEqual((lay['record'], lay['alias']), (0xA801, [(0, 3)]))   # 첫 바이트 1x 면 다음 창 레코드
        self.assertEqual((lay['x'], lay['y'], lay['w'], lay['cols'], lay['cursor']), (8, 4, 6, 1, 0x40))
        self.assertTrue(lay['inset'])
        self.assertEqual(lay['frame'], (9, 4, 4))
        kinds = [tk[0] for tk in lay['tokens']]
        self.assertEqual(kinds, ['item', 'cond', 'condtable', 'item', 'newline', 'side', 'list', 'mode'])
        self.assertEqual(lay['tokens'][1], ('cond', 1, 2))      # 묶음은 뒤에서부터 읽혀 뒤의 표 고르기가 걸린다
        self.assertEqual(lay['tokens'][5], ('side', 0x05))

    def test_window_symbols_round_trip(self):
        e = t.window_entry(self.rom, 0, 2)
        s = t.symbolize(e[2], t._window_ref(self.rom, 0))
        self.assertEqual(s, 'か{CALL:00}き{INS:01}')
        self.assertEqual(t.unsymbolize(s, t._window_unref(self.rom, 0)), e[2])
        with self.assertRaises(ValueError):
            t.unsymbolize('{INS:00}', t._window_unref(self.rom, 0))


class BufferTests(unittest.TestCase):
    def test_lines_merge_marks_and_trim(self):
        ram = bytearray(0x800)
        ram[t.WIDTH], ram[t.LINE_NO] = t.FIELD_W, 3
        w = t.FIELD_W
        ram[t.LINE_BUF + w + 1] = 0x06                 # 줄 0 글자 행
        ram[t.LINE_BUF + 1] = 0x3D                     # 줄 0 탁점 행
        ram[t.LINE_BUF + 3 * w:t.LINE_BUF + 3 * w + 2] = bytes((0x01, 0x02))
        self.assertEqual(t.buffer_lines(ram), [[0x3D, 0x06], [0x01, 0x02]])

    def test_battle_width(self):
        ram = bytearray(0x800)
        ram[t.WIDTH] = t.BATTLE_W
        self.assertEqual(t.line_width(ram), t.BATTLE_W)
        ram[t.WIDTH] = 0x10
        self.assertEqual(t.line_width(ram), t.FIELD_W)

    def test_screen_lines_reject_frame_tiles(self):
        ram, nt = bytearray(0x800), bytearray(0x400)
        ram[t.WIDTH], ram[t.ORIGIN_X], ram[t.LINE_NO] = 4, 2, 1
        y = t.SCREEN_ROW + 1
        nt[y * 32 + 2:y * 32 + 4] = bytes((0x01, 0x02))
        self.assertEqual(t.screen_lines(ram, nt), [[0x01, 0x02]])
        nt[y * 32 + 3] = 0x80
        self.assertEqual(t.screen_lines(ram, nt), [])

    def test_match_lets_substitution_take_any_glyphs(self):
        self.assertEqual(t._match([1, 2, 3], [1, 0xF6], 0, 0), 2)
        self.assertIsNone(t._match([1, 2], [1, 3], 0, 0))
        self.assertIsNone(t._match([1, 2], [3, 0xF6], 0, 0))


if __name__ == '__main__':
    unittest.main()
