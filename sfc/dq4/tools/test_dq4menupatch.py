import os
from pathlib import Path
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
    mp.put(d, mp.B_CANCEL, bytes.fromhex('ade80a'))
    for site, target in mp.CURSOR_MOVES.items():
        mp.put(d, site, bytes((0x20, target & 0xFF, target >> 8)))
    mp.put(d, mp.MAP_LOAD, bytes.fromhex('a91c8d2507'))
    mp.put(d, mp.WIN_DISPATCH, bytes.fromhex('c901f0052035b280c6c8c8'))
    mp.put(d, mp.FADEOUT_EXIT, bytes.fromhex('5c5cfe03'))
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


class BaseProblemTests(unittest.TestCase):
    def rom(self):
        d = bytearray(0x400000)
        mp.put(d, mp.OVERTURE_STUB, b'\x6b')
        mp.put(d, 0x108000, bytes.fromhex('2200ff70'))
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
