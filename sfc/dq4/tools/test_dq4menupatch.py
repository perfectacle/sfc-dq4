import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock

import dq4bg3slot
import dq4menumsg
import dq4menupatch as mp
import dq4namegame
import dq4nameentry as ne
import dq4windowname

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
        head = bytes((0x5A, 0x5A, 0x4E, 0xA3, 0x5A, 0x5A))
        rec = mp.item_record(atlas, head, [['가나'], ['다', b'\x01\x03']])
        # 커서 FE 1 + 열 2 + 공백·숫자 2 = 5, 테두리 2 → 7. 높이는 3 → 4
        self.assertEqual(rec[:6], bytes((0x5A, 0x5A, 0x47, 0xA4, 0x5A, 0x5A)))   # 너비 위 두 비트는 그대로
        self.assertEqual(rec[6:], bytes.fromhex('fe9f0302ff fe9f020301 03ff 80'.replace(' ', '')))

    def test_speed_record_keeps_digit_items(self):
        digits = b''.join(bytes((0xFE, k)) for k in range(3, 11)) + b'\xff\x80'
        old = bytes((0x5A, 0x5A, 0x28, 0x5A, 0x5A, 0x5A)) + b'\x5a' * 12 + b'\xff\xff' + b'\x01' * 10 + b'\xff\xff' + digits
        atlas = FakeAtlas({mp.SPEED_TEXT[0]: 15, mp.SPEED_TEXT[1]: 3, mp.SPEED_TEXT[2]: 3})
        rec = mp.speed_record(atlas, old)
        self.assertTrue(rec.endswith(digits))
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
        self.assertEqual(code[ignore + 3:], mp.B_CANCEL_ORIG + b'\x60')    # keep: 원래 LDA 를 하고 RTS

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
        cls.out, cls.atlas, cls.records = mp.build(cls.rom, mp.Font('galmuri9'), mp.Font('galmuri7'))

    def test_base_is_overture_build(self):
        self.assertIsNone(mp.base_problem(self.rom))
        self.assertIsNotNone(mp.base_problem(self.out))

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


class FakeFont:
    """글자마다 8점, 점 하나. 문자열 n 자는 n + 1 열."""
    name = 'fake'

    def char(self, ch):
        return 8, [(1, 1)]


TABLE = 0x04EB48
COUNT = 0x87
ALIAS = 0x70            # 5E 와 같은 레코드를 가리키는 창(표에서 함께 고쳐야 함)
FIELD, BOARD = b'\x46' * 10 + b'\x80', b'\x42' * 12 + b'\x80'


def record(head, size):
    return bytes.fromhex(head) + b'\x01' * (size - 7) + b'\x80'


def menu_rom(small=0x5E, spare=0x40):
    """창 표와 메뉴 패치가 덮어쓰는 자리의 원래 바이트만 채운 4MB 롬. small 창 레코드는 한글보다 짧다."""
    d = bytearray(0x400000)
    at = (TABLE & 0xFFFF) + 2 * COUNT
    recs = {n: record('020304030001', 9 if n == small else spare) for n in mp.WINDOWS}
    recs[mp.SPEED_WINDOW] = (bytes.fromhex('020214060003') + b'\x01' * 20 + b'\xff\xff'
                             + b''.join(bytes((0xFE, k)) for k in range(3, 11)) + b'\xff\x80')
    for n in (0x32, 0x62):
        recs[n] = record('040406030002', 0x10)
    recs[0x6B], recs[0x6C] = bytes.fromhex('0101080200') + b'\x01' * 6, record('01010c0600', 0x20)
    recs[0x7F] = record('000004010000', 8)
    addr = {}
    for n in range(COUNT):
        if n in recs:
            mp.put(d, 0x040000 | at, recs[n])
            addr[n] = 0x040000 | at
            at += len(recs[n])
    dummy = addr[0x7F]
    for n in range(COUNT):
        a = addr.get(n, addr[small] if n == ALIAS else dummy)
        mp.put(d, TABLE + 2 * n, (a & 0xFFFF).to_bytes(2, 'little'))
    mp.put(d, mp.B_CANCEL, mp.B_CANCEL_ORIG)
    for site, target in mp.CURSOR_MOVES.items():
        mp.put(d, site, bytes((0x20, target & 0xFF, target >> 8)))
    mp.put(d, mp.MAP_LOAD, mp.MAP_LOAD_ORIG)
    mp.put(d, mp.WIN_DISPATCH, mp.WIN_DISPATCH_ORIG)
    mp.put(d, mp.FADEOUT_EXIT, mp.FADEOUT_EXIT_ORIG)
    return d, recs, addr


def identity(data, *args, **kw):
    return data


def build_menu(rom):
    """뒤 단계(이름 입력·메시지·창 이름 등)는 그대로 돌려주게 막고 메뉴 창 단계만 돌린다."""
    seen = {}

    def ne_apply(data, keys, blob, bridges):
        seen.update(keys=keys, bridges=bridges)
        return data
    with mock.patch.object(ne, 'field_record', return_value=FIELD), \
            mock.patch.object(ne, 'board_record', return_value=(BOARD, 'keys')), \
            mock.patch.object(ne, 'glyph_blob', return_value=b''), \
            mock.patch.object(ne, 'apply', ne_apply), \
            mock.patch.object(dq4menumsg, 'apply', lambda data, font, messages: (data, ['info'])), \
            mock.patch.object(dq4namegame, 'apply', identity), \
            mock.patch.object(dq4bg3slot, 'apply', identity), \
            mock.patch.object(dq4windowname, 'apply', identity), \
            mock.patch.object(mp, 'set_checksum', identity):
        return mp.build(bytes(rom), FakeFont(), FakeFont(), FakeFont()), seen


class MenuBuildTests(unittest.TestCase):
    def build(self, rom):
        return build_menu(rom)

    @classmethod
    def setUpClass(cls):
        cls.rom, cls.recs, cls.addr = menu_rom()
        (cls.out, cls.atlas, cls.records), seen = build_menu(cls.rom)
        cls.bridges, cls.keys = seen['bridges'], seen['keys']

    def test_board_keys_reach_name_entry(self):
        self.assertEqual(self.keys, 'keys')

    def ptr(self, n):
        return mp.window_addr(self.out, n)

    def test_records_fit_in_place_or_move_with_every_alias(self):
        for n in mp.WINDOWS:
            a, old, new = self.records[n]
            self.assertEqual(mp.window_record(self.out, self.ptr(n)), new, f'{n:02X}')
            if n == 0x5E:
                self.assertGreater(len(new), len(old))
                self.assertNotEqual(a, self.addr[n])
            else:
                self.assertEqual(a, self.addr[n])
        self.assertEqual(self.ptr(ALIAS), self.ptr(0x5E))

    def spans(self):
        out = []
        for n in list(mp.WINDOWS) + [mp.SPEED_WINDOW]:
            a, _, new = self.records[n]
            out.append((mp.lorom(a), mp.lorom(a) + len(new), f'{n:02X}'))
        return out

    def test_moved_record_and_code_do_not_overlap_live_records(self):
        spans = self.spans()
        check = mp.lorom(0x040000 | int.from_bytes(self.out[mp.lorom(mp.B_CANCEL) + 1:mp.lorom(mp.B_CANCEL) + 3], 'little'))
        spans.append((check, check + len(mp.b_check()), 'b_check'))
        for site in mp.CURSOR_MOVES:
            t = mp.lorom(0x040000 | int.from_bytes(self.out[mp.lorom(site) + 1:mp.lorom(site) + 3], 'little'))
            spans.append((t, t + len(mp.cursor_tramp(0, 0)), f'{site:06X}'))
        for name, b in self.bridges.items():
            spans.append((mp.lorom(b), mp.lorom(b) + 4, name))
        spans.sort()
        for (_, end, x), (start, _, y) in zip(spans, spans[1:]):
            self.assertLessEqual(end, start, f'{x} / {y}')

    def test_hooks_reach_their_code(self):
        o = mp.lorom(mp.B_CANCEL)
        self.assertEqual(self.out[o], 0x20)
        check = mp.lorom(0x040000 | int.from_bytes(self.out[o + 1:o + 3], 'little'))
        self.assertEqual(self.out[check:check + len(mp.b_check())], mp.b_check())
        commons = set()
        for site, target in mp.CURSOR_MOVES.items():
            t = mp.lorom(0x040000 | int.from_bytes(self.out[mp.lorom(site) + 1:mp.lorom(site) + 3], 'little'))
            tramp = self.out[t:t + 10]
            self.assertEqual(tramp[4:7], bytes((0x20, target & 0xFF, target >> 8)))
            commons.add(int.from_bytes(tramp[8:10], 'little'))
        self.assertEqual(len(commons), 1)
        c = mp.lorom(0x040000 | commons.pop())
        self.assertEqual(self.out[c:c + len(mp.cursor_common())], mp.cursor_common())
        for name, target in {'wait': 0x9D35, 'erase': 0xD1B9}.items():
            b = mp.lorom(self.bridges[name])
            self.assertEqual(self.out[b:b + 4], bytes((0x20, target & 0xFF, target >> 8, 0x6B)))
        o = mp.lorom(mp.WIN_DISPATCH)
        self.assertEqual(self.out[o:o + 4], bytes((0x22, mp.HOOK & 0xFF, mp.HOOK >> 8 & 0xFF, mp.HOOK >> 16)))
        self.assertEqual(self.out[mp.lorom(mp.HOOK):mp.lorom(mp.HOOK) + len(mp.hook_code())], mp.hook_code())

    def test_shared_windows_get_wram_slots_and_both_copies(self):
        kr, jp = mp.lorom(mp.SHARED_KR), mp.lorom(mp.SHARED_JP)
        slot = mp.SHARED_WRAM
        for n in sorted(mp.SHARED):
            a, old, new = self.records[n]
            self.assertEqual(self.ptr(n) & 0xFFFF, slot, f'{n:02X}')
            off = slot - mp.SHARED_WRAM
            self.assertEqual(self.out[kr + off:kr + off + len(new)], new)
            self.assertEqual(self.out[jp + off:jp + off + len(old)], old)
            slot += max(len(old), len(new))
        self.assertEqual(self.records[0x6B][2], FIELD)
        self.assertEqual(self.records[0x6C][2], BOARD)
        flag = mp.MENU_FLAG - mp.SHARED_WRAM
        self.assertEqual((self.out[kr + flag], self.out[jp + flag]), (0xA5, 0x00))
        copy = self.out[mp.lorom(mp.COPY_KR):mp.lorom(mp.COPY_KR) + len(mp.copy_code(0, 1))]
        self.assertEqual(int.from_bytes(copy[14:16], 'little'), flag)

    def test_original_bytes_are_checked(self):
        rom, _, _ = menu_rom()
        mp.put(rom, mp.WIN_DISPATCH, b'\x00')
        with self.assertRaisesRegex(ValueError, '예상한 원래 바이트'):
            self.build(rom)

    def test_no_room_for_a_grown_record(self):
        rom, _, _ = menu_rom(spare=0x16)
        with self.assertRaisesRegex(ValueError, '창 5E: 옮길 자리가 없음'):
            self.build(rom)


BDF = """STARTFONT 2.1
FONT test
CHARS 3

STARTCHAR hangul
ENCODING 54620
SWIDTH 500 0
DWIDTH 9 0
BBX 8 8 0 -1
BITMAP
80
40
20
10
08
04
02
01
ENDCHAR
STARTCHAR small
ENCODING 65
DWIDTH 5 0
BBX 4 2 1 3
BITMAP
F0
90
ENDCHAR
ENDFONT
"""


class FontTests(unittest.TestCase):
    def font(self, file, text=BDF, sha=None):
        sha = sha or hashlib.sha256(text.encode('latin-1', 'replace')).hexdigest()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        (Path(tmp.name) / file).write_text(text, encoding='latin-1')
        galmuri = {**mp.GALMURI, 'galmuri9': (file, sha)}
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(mock.patch.dict(os.environ, {'DQ4_GALMURI': tmp.name}))
        stack.enter_context(mock.patch.object(mp, 'GALMURI', galmuri))
        return mp.Font('galmuri9')

    def test_missing_folder_variable_stops(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(SystemExit, 'DQ4_GALMURI'):
                mp.Font('galmuri9')

    def test_file_with_another_hash_is_refused(self):
        with self.assertRaisesRegex(SystemExit, 'Galmuri v2.40.4'):
            self.font('Galmuri9.bdf', sha='0' * 64)

    def test_blank_lines_are_skipped_and_codes_become_characters(self):
        font = self.font('Galmuri9.bdf')
        self.assertEqual(sorted(font.glyphs), ['A', '한'])
        self.assertEqual(font.glyphs['A']['rows'], [[1, 1, 1, 1], [1, 0, 0, 1]])
        self.assertEqual(font.glyphs['한']['adv'], 9)

    def test_hangul_top_row_sits_on_band_row_one(self):
        font = self.font('Galmuri9.bdf')
        self.assertEqual(font.top, 7)
        adv, pts = font.char('한')
        self.assertEqual(adv, 9)
        self.assertEqual(pts, [(i, 1 + i) for i in range(8)])

    def test_other_glyphs_are_placed_by_their_bounding_box(self):
        # A: 높이 2, 아래 오프셋 3 → 윗줄 y = 7 - (3 + 2 - 1 - 0) = 3, 가로는 x 오프셋 1 부터
        adv, pts = self.font('Galmuri9.bdf').char('A')
        self.assertEqual(adv, 5)
        self.assertEqual(pts, [(1, 3), (2, 3), (3, 3), (4, 3), (1, 4), (4, 4)])


class RenderTests(unittest.TestCase):
    def test_columns_are_eight_dots_wide_with_one_dot_of_margin(self):
        cols = mp.render(FakeFont(), 'ab')
        # 점은 글자마다 (1, 1) → 띠 x 2 와 10. 진행 폭 1 + 16 = 17 → 3열
        self.assertEqual(len(cols), 3)
        self.assertEqual(cols[0][1][2], 1)
        self.assertEqual(cols[1][1][2], 1)
        self.assertEqual(sum(v for col in cols for row in col for v in row), 2)
        self.assertEqual([len(col) for col in cols], [mp.BAND] * 3)

    def test_tight_width_ends_at_the_last_dot(self):
        self.assertEqual(len(mp.render(FakeFont(), 'ab', tight=True)), 2)
        self.assertEqual(len(mp.render(FakeFont(), 'a', tight=True)), 1)

    def test_dot_outside_the_band_is_an_error(self):
        class Low:
            def char(self, ch):
                return 8, [(0, mp.BAND)]
        with self.assertRaisesRegex(ValueError, '띠 밖'):
            mp.render(Low(), 'a')


class AtlasTests(unittest.TestCase):
    def test_same_text_is_drawn_once_and_columns_follow_the_reserved_ones(self):
        atlas = mp.Atlas(FakeFont())
        self.assertEqual(atlas.run('ab'), (3, mp.Atlas.FIRST))
        self.assertEqual(atlas.run('ab'), (3, mp.Atlas.FIRST))
        self.assertEqual(atlas.run('c'), (2, mp.Atlas.FIRST + 3))
        self.assertEqual(len(atlas.cols), mp.Atlas.FIRST + 5)

    def test_other_font_is_cached_apart_and_drawn_tight(self):
        atlas = mp.Atlas(FakeFont())
        other = SimpleNamespace(name='other', char=FakeFont().char)
        self.assertEqual(atlas.run('ab', other), (2, mp.Atlas.FIRST))
        self.assertEqual(atlas.run('ab'), (3, mp.Atlas.FIRST + 2))

    def test_columns_past_the_name_area_are_refused(self):
        atlas = mp.Atlas(FakeFont())
        with self.assertRaisesRegex(ValueError, '넘음'):
            atlas.run('가' * 210)

    def test_tiles_hold_upper_then_lower_halves(self):
        atlas = mp.Atlas(FakeFont())
        atlas.run('a')
        tiles = atlas.tiles()
        self.assertEqual(len(tiles), 2 * mp.COLUMNS * 16)
        # 점은 글자 줄 1행 x 2 → 열 2 의 첫 평면 1행 = 0x20, 둘째 평면은 FF
        first = mp.Atlas.FIRST * 16
        self.assertEqual(tiles[first + 2:first + 4], bytes((0x20, 0xFF)))
        self.assertEqual(tiles[mp.COLUMNS * 16 + first:mp.COLUMNS * 16 + first + 2], bytes((0x00, 0xFF)))
        self.assertEqual(tiles[:16], bytes(16))


class RecordErrorTests(unittest.TestCase):
    def test_item_record_too_wide_is_an_error(self):
        atlas = FakeAtlas({'가': 0x3F})
        with self.assertRaisesRegex(ValueError, '너비'):
            mp.item_record(atlas, bytes((0x5A, 0x5A, 0x4E, 0xA3, 0x5A, 0x5A)), [['가']])

    def test_item_record_without_height_left_is_an_error(self):
        atlas = FakeAtlas({'가': 2})
        with self.assertRaises(ValueError):
            mp.item_record(atlas, bytes((0x5A, 0x5A, 0x4E, 0xAF, 0x5A, 0x5A)), [['가']])

    def test_speed_text_longer_than_its_line_is_an_error(self):
        q, fast, slow = mp.SPEED_TEXT
        old = bytes((2, 2, 0x14, 6, 0, 3)) + bytes((0xFE, 3, 0xFF))
        with self.assertRaisesRegex(ValueError, '표시 속도'):
            mp.speed_record(FakeAtlas({q: 4, fast: 9, slow: 9}), old)
        with self.assertRaisesRegex(ValueError, '표시 속도'):
            mp.speed_record(FakeAtlas({q: 0x20, fast: 3, slow: 3}), old)

    def test_place_needs_a_slack_big_enough(self):
        data = bytearray(0x100000)
        with self.assertRaisesRegex(ValueError, '빈자리가 모자람'):
            mp.place(data, [[0x040000, 0x040002]], b'abc')
        slack = [[0x040010, 0x040020]]
        self.assertEqual(mp.place(data, slack, b'abc'), 0x040010)
        self.assertEqual(slack, [[0x040013, 0x040020]])
        self.assertEqual(bytes(data[mp.lorom(0x040010):mp.lorom(0x040010) + 3]), b'abc')

    def test_put_checks_the_original_bytes(self):
        data = bytearray(0x10000)
        with self.assertRaisesRegex(ValueError, '원래 바이트'):
            mp.put(data, 0x040000, b'x', b'y')

    def test_grown_record_missing_from_the_window_table_is_an_error(self):
        # 표 첫 칸이 표 바로 뒤를 가리키면 칸 수가 10 으로 읽혀, 5E 를 가리키는 칸을 찾지 못한다
        rom, _, _ = menu_rom()
        mp.put(rom, TABLE, (0xEB48 + 20).to_bytes(2, 'little'))
        with self.assertRaisesRegex(ValueError, '창 5E: 창 표에서 레코드를 찾지 못함'):
            build_menu(rom)

    def test_shared_windows_must_fit_before_the_menu_flag(self):
        rom, _, _ = menu_rom()
        with mock.patch.object(mp, 'MENU_FLAG', mp.SHARED_WRAM + 4):
            with self.assertRaisesRegex(ValueError, '공용 창'):
                build_menu(rom)


class SheetTests(unittest.TestCase):
    def test_sheet_draws_one_white_dot_per_column_dot_at_triple_scale(self):
        from PIL import Image
        atlas = mp.Atlas(FakeFont())
        atlas.run('a')
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'sheet.png'
            mp.sheet(atlas, out)
            image = Image.open(out).convert('RGB')
        self.assertEqual(image.size, (len(atlas.cols) * 8 * 3, mp.BAND * 3))
        x = (mp.Atlas.FIRST * 8 + 2) * 3 + 1
        self.assertEqual(image.getpixel((x, 3 + 1)), (255, 255, 255))
        self.assertEqual(image.getpixel((1, 1)), (40, 40, 40))
        whites = [(px, py) for px in range(image.width) for py in range(image.height) if image.getpixel((px, py)) == (255, 255, 255)]
        self.assertEqual(len(whites), 9)


class LoadMessagesTests(unittest.TestCase):
    def load(self, doc):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'messages.json'
            path.write_text(json.dumps(doc), encoding='utf-8')
            return mp.load_messages(path)

    def test_numbers_are_hex_keys_and_parts_pass_through(self):
        from dq4menumsg import CHARS
        text = CHARS[0] + ' ' + CHARS[1]
        self.assertEqual(self.load({'format': 'dq4messages/1', 'messages': {'1F': [text, 3], '0A': [' ']}}),
                         {0x1F: [text, 3], 0x0A: [' ']})

    def test_other_format_is_refused(self):
        with self.assertRaisesRegex(SystemExit, 'dq4messages/1'):
            self.load({'format': 'x', 'messages': {}})

    def test_characters_outside_the_font_are_refused(self):
        with self.assertRaisesRegex(SystemExit, '넣을 수 없는 부분'):
            self.load({'format': 'dq4messages/1', 'messages': {'01': ['\u0001']}})
        with self.assertRaisesRegex(SystemExit, '넣을 수 없는 부분'):
            self.load({'format': 'dq4messages/1', 'messages': {'01': [1.5]}})


class MainTests(unittest.TestCase):
    def run_main(self, *argv):
        buf = io.StringIO()
        with mock.patch('sys.argv', ['dq4menupatch.py', *argv]), mock.patch.object(mp, 'Font', lambda name: FakeFont()), \
                contextlib.redirect_stdout(buf):
            mp.main()
        return buf.getvalue()

    def test_sheet_draws_every_window_text(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'sheet.png'
            self.run_main('sheet', '--out', str(out))
            width = Image.open(out).width
        # 문구마다 글자 수 + 1 열(FakeFont): 아무 문구도 안 그렸다면 예약 열 둘뿐이다
        self.assertGreater(width, mp.Atlas.FIRST * 8 * 3 * 10)

    def test_build_writes_rom_and_ips_and_lists_records(self):
        rom = bytes(16)
        built = bytearray(rom)
        built[3] = 9
        atlas = SimpleNamespace(cols=[1, 2, 3], messages=['메시지 줄'])
        records = {0x5E: (0x040100, b'\x01', b'\x02\x03')}
        seen = {}

        def fake_build(data, font, jamo, messages=None):
            seen.update(data=data, messages=messages)
            return bytes(built), atlas, records

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / 'in.sfc').write_bytes(rom)
            (tmp / 'messages.json').write_text(json.dumps({'format': 'dq4messages/1', 'messages': {'01': [' ']}}))
            out = tmp / 'sub' / 'out.sfc'
            with mock.patch.object(mp, 'base_problem', lambda data: None), mock.patch.object(mp, 'build', fake_build):
                text = self.run_main('build', '--rom', str(tmp / 'in.sfc'), '--out', str(out),
                                     '--messages', str(tmp / 'messages.json'))
            self.assertEqual(out.read_bytes(), bytes(built))
            ips = out.with_suffix('.ips').read_bytes()
        self.assertTrue(ips.startswith(b'PATCH') and ips.endswith(b'EOF'))
        self.assertEqual(seen["data"], rom)
        self.assertEqual(seen["messages"], {1: [' ']})
        lines = text.splitlines()
        self.assertEqual(lines[0], f'{out} sha1={hashlib.sha1(built).hexdigest()} 열=3 바뀐 구간=1')
        self.assertEqual(lines[1], '메시지 줄')
        self.assertEqual(lines[2], '창 5E 040100 1→2 02 03')

    def test_unfit_base_rom_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'in.sfc').write_bytes(bytes(16))
            with self.assertRaisesRegex(SystemExit, '4MB 가 아님'):
                self.run_main('build', '--rom', str(Path(tmp) / 'in.sfc'), '--out', str(Path(tmp) / 'o.sfc'))


class BaseProblemTests(unittest.TestCase):
    def rom(self):
        d = bytearray(0x400000)
        mp.put(d, mp.OVERTURE_STUB, b'\x6b')
        mp.put(d, 0x108000, mp.OVERTURE_CALL)
        return d

    def test_overture_build_is_accepted(self):
        self.assertIsNone(mp.base_problem(bytes(self.rom())))

    def test_rejects_other_roms(self):
        self.assertIn('4MB', mp.base_problem(bytes(0x200000)))
        d = self.rom()
        mp.put(d, mp.OVERTURE_STUB, b'\x00')
        self.assertIn('서곡 스텁', mp.base_problem(bytes(d)))
        d = self.rom()
        mp.put(d, dq4menumsg.BASE + 0xFF, b'\x01')
        self.assertIn('이미 메뉴', mp.base_problem(bytes(d)))


class BdfTests(unittest.TestCase):
    def test_rows_use_bbx_width_not_padded_bits(self):
        import tempfile
        bdf = (
            'STARTFONT 2.1\nCHARS 2\n'
            'STARTCHAR a\nENCODING 44032\nDWIDTH 10 0\nBBX 9 2 1 -1\nBITMAP\nFF80\n8080\nENDCHAR\n'
            'STARTCHAR skip\nENCODING -1\nDWIDTH 4 0\nBBX 1 1 0 0\nBITMAP\n80\nENDCHAR\nENDFONT\n')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'f.bdf'
            path.write_text(bdf, encoding='latin-1')
            glyphs = mp.load_bdf(path)
        self.assertEqual(list(glyphs), ['가'])
        g = glyphs['가']
        self.assertEqual((g['adv'], g['bbx']), (10, (9, 2, 1, -1)))
        self.assertEqual(g['rows'], [[1] * 9, [1] + [0] * 7 + [1]])


if __name__ == '__main__':
    unittest.main()
