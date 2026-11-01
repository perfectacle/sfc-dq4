import os
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

import dq4battlemsg
import dq4nameentry as ne
import dq4windowname as wn
import dq4windowtext

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'dq5' / 'tools'))
import dq5text  # noqa: E402

ASM = Path(__file__).resolve().parent / 'dq4windowname.asm'
CANVAS = range(0x096, 0x180)     # 메시지 캔버스: 9줄 × 26칸
OFF_CANVAS = range(0x1D0, 0x200)
ROW = 26
HIDDEN = range(6, 19)            # 가게 팔기·맡기기 목록 창(화면 9~21열)이 덮는 캔버스 줄 안의 칸
HIDDEN_ROWS = 8                  # 캔버스 마지막 줄(화면 26줄)은 가게 사기의 장비 비교 창이 덮지 않음
COLS = {0: 4, 1: 7, 2: 10}
HIDDEN_SLOTS = {4: 3, 7: 3, 10: 1}   # 열 수마다 목록 창 밑에 가리는 앞쪽 캔버스 슬롯 수


def table(name):
    text = ASM.read_text()
    body = re.search(rf'^{name}:\n((?:    dw .*\n)+)', text, re.M).group(1)
    return [int(v.replace('$', '0x'), 16) for v in re.findall(r'\$?[0-9A-Fa-f]+', body.replace('dw', ''))]


def hidden(first, n):
    return all((t - CANVAS.start) % ROW in HIDDEN and (t - CANVAS.start) // ROW < HIDDEN_ROWS
               for t in range(first, first + n))


class FieldSlotTest(unittest.TestCase):
    def setUp(self):
        # 캔버스 밖 1D0~1FF 슬롯($20)은 위 줄이 글자 줄 바로 뒤(WtUpperF = 0)
        rows = [(lo, up, c) for lo, up, c in zip(table('WtSlotF'), table('WtUpperF'), table('WtClassF')) if c != 0xFF]
        self.slots = [(lo, up or lo + COLS[c & 0x0F], COLS[c & 0x0F]) for lo, up, c in rows]

    def test_runs_stay_in_place_and_do_not_overlap(self):
        used = []
        for (lo, up, n), c in zip(self.slots, [c for c in table('WtClassF') if c != 0xFF]):
            for first in (lo, up):
                area = OFF_CANVAS if c & 0x20 else CANVAS
                self.assertTrue(first in area and first + n - 1 in area, f'{first:03X}')
                used += range(first, first + n)
        self.assertEqual(len(used), len(set(used)))

    def test_same_slot_count_and_classes_as_battle(self):
        battle = [c & 0x0F for c in table('WtClass') if c != 0xFF]
        self.assertEqual(sorted(battle), sorted(c & 0x0F for c in table('WtClassF') if c != 0xFF))

    def test_off_canvas_slots_match_battle_table(self):
        battle = [(t, c & 0x2F) for t, c in zip(table('WtSlot'), table('WtClass')) if c != 0xFF and c & 0x20]
        field = [(t, c) for t, c in zip(table('WtSlotF'), table('WtClassF')) if c != 0xFF and c & 0x20]
        self.assertEqual(battle, field)
        # 메시지 창에 비치지 않는 캔버스 밖 슬롯을 먼저 고른다
        self.assertEqual(field, [(t, c) for t, c in zip(table('WtSlotF'), table('WtClassF')) if c != 0xFF][:len(field)])
        self.assertEqual([u for u, c in zip(table('WtUpperF'), table('WtClassF')) if c != 0xFF and c & 0x20],
                         [0] * len(field))

    def test_first_slots_of_each_size_are_hidden_under_the_list(self):
        for n, count in HIDDEN_SLOTS.items():
            for lo, up, _ in [s for s in self.slots if s[2] == n and s[0] in CANVAS][:count]:
                self.assertTrue(hidden(lo, n) and hidden(up, n), f'{lo:03X}/{up:03X}')

    def test_hidden_large_slots_come_before_visible_medium_ones(self):
        order = [(n, hidden(lo, n) and hidden(up, n)) for lo, up, n in self.slots if lo in CANVAS]
        medium_visible = order.index((7, False))
        self.assertLess(max(i for i, s in enumerate(order) if s == (10, True)), medium_visible)


def lorom(a):
    return ((a >> 16) & 0x7F) * 0x8000 + (a & 0x7FFF)


WINDOWS = 0x04EB48
LIST_PREV = 0x6123AB
PREFIX_PREV = 0x608000
NAME_LIST = bytes.fromhex('0502080500d0fe01ff80')


def base_windows():
    out = {
        wn.STATUS_WINDOW: bytes.fromhex('0000060500010180'),
        0x03: bytes.fromhex('0000060500' '8b0180'),
        0x04: bytes.fromhex('0000060500' '890180'),
        wn.SPELL_WINDOW: bytes.fromhex('020208050081fed6ff80'),
        wn.SHOP_MEMBERS: bytes.fromhex('020f1c050001feefccff80'),
        0x46: bytes.fromhex('42040e050001fe01ff80'),
        0x45: bytes.fromhex('10840e050001fe01ff80'),
        wn.TACTIC_WINDOW: bytes.fromhex('17820605000101ff80'),
        wn.SHOP_BUY: bytes.fromhex('020214090001') + wn.SHOP_BUY_ROW[0] + b'\x80',
        wn.SHOP_SELL_ALIAS: bytes((0x89, 0x02, wn.SHOP_SELL_ITEMS)),
        wn.SHOP_SELL_ITEMS: bytes.fromhex('4f0308b90081fed3ff8380'),
        wn.QTY_WINDOW: bytes.fromhex('16050823000101fdfdfdfdfdff5280'),
    }
    out.update({w: NAME_LIST for w in wn.NAME_LISTS})
    return out


def base_rom(windows=None):
    """dq4windowname.apply 가 원래 롬에서 확인하는 바이트만 채운 4MB 롬."""
    d = bytearray(0x400000)

    def put(addr, raw):
        d[lorom(addr):lorom(addr) + len(raw)] = raw

    at = 0x8000
    for n, rec in (windows or base_windows()).items():
        put(0x040000 | at, rec)
        put(WINDOWS + 2 * n, at.to_bytes(2, 'little'))
        at += len(rec)
    for a in wn.SHOP_RESOLVE:
        put(a, bytes.fromhex('bd48eb'))
    put(wn.CODE_TABLE + (wn.SHOP_SELL_CODE - 0xB0) * 2, bytes.fromhex('46b9'))
    for a in wn.BUY_SITES:
        put(a, wn.BUY_ORIG + bytes.fromhex('20e9f5'))
    for a, want in ((0x06F602, '008849'), (0x06DC2F, 'a90120c4df'), (0x06DFC4, 'c904')):
        put(a, bytes.fromhex(want))
    for a, orig in ((wn.SELL_QTY_SITE, wn.SELL_QTY_ORIG), (wn.SELL_GIVE_SITE, wn.SELL_GIVE_ORIG),
                    (wn.SELL_NO_SITE, wn.SELL_NO_ORIG), (wn.SELL_ASK_SITE, wn.SELL_ASK_ORIG),
                    (wn.QTY_UP_SITE, wn.QTY_UP_ORIG), (wn.QTY_DOWN_SITE, wn.QTY_DOWN_ORIG)):
        put(a, orig)
    put(wn.GIVE_SITE, wn.GIVE_ORIG + bytes.fromhex('00898030'))
    for a in wn.HELD_SITES:
        rel = lorom(0x04C440) - (lorom(a) + 6)
        put(a, bytes.fromhex('a00a0082') + rel.to_bytes(2, 'little', signed=True))
    put(wn.EMPTY_SLOT_HOOK, bytes.fromhex('a20900bdfbb92035b2ca10f7'))
    put(wn.PREFIX_HOOK, b'\x22' + PREFIX_PREV.to_bytes(3, 'little'))
    put(wn.LIST_HOOK, b'\x5c' + LIST_PREV.to_bytes(3, 'little'))
    return d


def jump(op, target, size):
    return bytes((op,)) + (target & (0xFFFFFF if size == 3 else 0xFFFF)).to_bytes(size, 'little')


def good_asar(rom):
    """asar 가 asm 을 넣은 뒤 apply 가 확인하는 자리만 흉내 낸다."""
    def put(addr, raw):
        rom[lorom(addr):lorom(addr) + len(raw)] = raw
    put(wn.CODE, b'\xea')
    put(wn.SHOP_SPOT, b'\xea')
    for a in (wn.SELL_QTY_SITE, wn.SELL_GIVE_SITE):
        put(a, jump(0x22, wn.SELL_SPOT, 3))
    put(wn.SELL_NO_SITE, jump(0x4C, wn.QTY_SPOT + 4, 2))
    put(wn.BUY_SITES[0], jump(0x20, wn.QTY_SPOT, 2))
    put(wn.BUY_SITES[1], jump(0x20, wn.BUY_SPOT + 1, 2))
    put(wn.GIVE_SITE, jump(0x20, wn.QTY_SPOT + 8, 2))
    for a in wn.SHOP_RESOLVE:
        put(a, jump(0x20, wn.SHOP_SPOT, 2))
    put(wn.CODE_TABLE + (wn.SHOP_SELL_CODE - 0xB0) * 2, (wn.SHOP_SPOT + 0x10 & 0xFFFF).to_bytes(2, 'little'))


class FakeAsar:
    def __init__(self, edit=good_asar, code=0):
        self.edit, self.code, self.asm, self.rom = edit, code, None, None

    def __call__(self, cmd, **kw):
        asm, path = Path(cmd[-2]), Path(cmd[-1])
        self.asm, self.rom = asm.read_text(), path.read_bytes()
        rom = bytearray(self.rom)
        self.edit(rom)
        path.write_bytes(bytes(rom))
        return mock.Mock(returncode=self.code, stdout='', stderr='boom' if self.code else '')


TEXT = b'\x5a' * 0x40
RECORD_AT = lorom(0x04F000)
NUMBERS = {**{k: 0x40 + i for i, k in enumerate(dq4windowtext.HELD_COUNT)},
           dq4windowtext.EMPTY_SLOT: 0x21, dq4windowtext.CANNOT_SELL: 0x22}


def run(rom, asar=None, numbers=NUMBERS, columns=2):
    asar = asar or FakeAsar()
    with mock.patch.object(dq4windowtext, 'build', return_value=(TEXT, {})), \
            mock.patch.object(dq4windowtext, 'fixed_records', return_value=([(RECORD_AT, b'\x9e\x21')], numbers)), \
            mock.patch.object(dq4windowtext, 'columns', return_value=[b''] * columns), \
            mock.patch.object(wn, 'kana_glyphs', return_value={'か': 1}), \
            mock.patch.object(dq4battlemsg, 'apply', return_value='!bm_test = 1\n'), \
            mock.patch.object(wn.subprocess, 'run', asar):
        return wn.apply(bytes(rom), object(), 'asar'), asar


def window(d, n):
    return lorom(0x040000 | int.from_bytes(d[lorom(WINDOWS + 2 * n):lorom(WINDOWS + 2 * n) + 2], 'little'))


class ApplyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom = base_rom()
        cls.out, cls.asar = run(cls.rom)
        cls.defs = dict(re.findall(r'^(!\w+)\s*=\s*(.+)$', cls.asar.asm, re.M))

    def head(self, n, rom=None):
        d = self.asar.rom if rom is None else rom
        o = window(d, n)
        return d[o:o + 4]

    def test_windows_widen_for_five_name_cells(self):
        before, after = self.rom, self.asar.rom
        self.assertEqual(self.head(wn.STATUS_WINDOW)[2], 7)
        for w in wn.HP_WINDOWS:
            self.assertEqual(self.head(w)[2], 7)
        for w in wn.NAME_LISTS + (wn.SHOP_MEMBERS, wn.TACTIC_WINDOW):
            b, a = self.head(w, before), self.head(w, after)
            self.assertEqual((a[0], a[2]), (b[0] - 1, b[2] + 1), f'{w:02X}')
        self.assertEqual(self.head(wn.SPELL_WINDOW)[2], 8 + 2)
        for w, h, left in wn.FORMATION:
            self.assertEqual(self.head(w)[:3], bytes((h[0] - left, h[1], h[2] + 1)))

    def test_shop_buy_row_gets_gold_mark(self):
        o = window(self.asar.rom, wn.SHOP_BUY)
        self.assertEqual(self.asar.rom[o + 6:o + 13], wn.SHOP_BUY_ROW[1])

    def test_text_bank_and_records_reach_asar(self):
        t = lorom(dq4windowtext.TEXT_BANK << 16 | dq4windowtext.INDEX)
        self.assertEqual(self.asar.rom[t:t + len(TEXT)], TEXT)
        self.assertEqual(self.asar.rom[RECORD_AT:RECORD_AT + 2], b'\x9e\x21')

    def test_defs_carry_previous_hooks_and_numbers(self):
        self.assertEqual(int(self.defs['!wn_list_prev'][1:], 16), LIST_PREV)
        self.assertEqual(int(self.defs['!wt_prefix_prev'][1:], 16), PREFIX_PREV)
        self.assertEqual(int(self.defs['!wt_held_first']), NUMBERS[dq4windowtext.HELD_COUNT[0]])
        self.assertEqual(int(self.defs['!wt_empty_slot']), NUMBERS[dq4windowtext.EMPTY_SLOT])
        self.assertEqual(int(self.defs['!wt_cannot_sell']), NUMBERS[dq4windowtext.CANNOT_SELL])
        self.assertEqual(int(self.defs['!shop_sell_w']), 0x14)
        sell = window(self.rom, wn.SHOP_SELL_ALIAS)
        self.assertEqual(lorom(0x040000 | int(self.defs['!shop_sell_alias'][1:], 16)), sell)
        self.assertEqual(int(self.defs['!wn_hi_count']), -(-len(ne.GLYPHS) // ne.CODE_RADIX))
        self.assertEqual(self.defs['!bm_test'], '1')
        # 창 이름 asm 과 전투 글 asm 을 이 정의 뒤에 붙인다
        self.assertTrue(self.asar.asm.index('!bm_test') < self.asar.asm.index(
            (Path(wn.__file__).parent / 'dq4windowname.asm').read_text()[:200]))

    def test_output_is_what_asar_wrote(self):
        self.assertEqual(self.out[lorom(wn.CODE)], 0xEA)


class ApplyRejectTests(unittest.TestCase):
    def test_needs_asar(self):
        with mock.patch.dict(os.environ, {}, clear=True), self.assertRaises(SystemExit):
            wn.apply(bytes(base_rom()), object())

    def test_code_area_must_be_empty(self):
        rom = base_rom()
        rom[lorom(wn.CODE_END - 1)] = 1
        with self.assertRaisesRegex(ValueError, '비어 있지 않음'):
            run(rom)

    def test_window_shape_checks(self):
        for n, bad in ((wn.STATUS_WINDOW, bytes.fromhex('0000070500010180')),
                       (wn.SPELL_WINDOW, bytes.fromhex('020208050081fed5ff80')),
                       (0x45, bytes.fromhex('10840f050001fe01ff80')),
                       (wn.SHOP_SELL_ALIAS, bytes((0x89, 0x02, 0x10)))):
            with self.subTest(n=hex(n)):
                with self.assertRaisesRegex(ValueError, f'^창 {n:02X} '):
                    run(base_rom({**base_windows(), n: bad}))

    def test_held_site_must_branch_to_the_label_picker(self):
        rom = base_rom()
        rom[lorom(wn.HELD_SITES[1]) + 4] ^= 1
        with self.assertRaisesRegex(ValueError, '소지 중'):
            run(rom)

    def test_cannot_sell_must_fit_the_price_cells(self):
        with self.assertRaisesRegex(ValueError, '값 칸'):
            run(base_rom(), columns=wn.SHOP_PRICE_COLS + 1)

    def test_held_numbers_must_be_consecutive(self):
        numbers = {**NUMBERS, dq4windowtext.HELD_COUNT[3]: 0x7F}
        with self.assertRaisesRegex(ValueError, '이어지지 않음'):
            run(base_rom(), numbers=numbers)

    def test_asar_failure(self):
        with self.assertRaises(SystemExit):
            run(base_rom(), FakeAsar(code=1))

    def test_code_past_its_area(self):
        def spill(rom):
            good_asar(rom)
            rom[lorom(wn.CODE_END)] = 1
        with self.assertRaisesRegex(ValueError, '벗어남'):
            run(base_rom(), FakeAsar(spill))

    def test_hooks_must_land_in_their_spots(self):
        def outside(site, raw):
            def edit(rom):
                good_asar(rom)
                rom[lorom(site):lorom(site) + len(raw)] = raw
            return edit
        for site, raw in ((wn.SELL_QTY_SITE, jump(0x22, wn.SELL_SPOT_END, 3)),
                          (wn.SELL_NO_SITE, jump(0x4C, wn.QTY_SPOT_END, 2)),
                          (wn.BUY_SITES[0], jump(0x20, wn.QTY_SPOT + 1, 2)),
                          (wn.BUY_SITES[1], jump(0x20, wn.BUY_SPOT, 2)),
                          (wn.SHOP_RESOLVE[2], jump(0x20, wn.SHOP_SPOT - 1, 2))):
            with self.subTest(site=hex(site)):
                with self.assertRaises(ValueError):
                    run(base_rom(), FakeAsar(outside(site, raw)))


KANA = 'あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをん'


class KanaGlyphTests(unittest.TestCase):
    def rom(self):
        d = bytearray(0x400000)

        def put(addr, raw):
            d[lorom(addr):lorom(addr) + len(raw)] = raw
        for i, ch in enumerate(KANA):
            put(dq5text.STRING_CODES + (0x10 + i) * 2, dq5text.CHARS.index(ch).to_bytes(2, 'little'))
        # 탁점 열쇠: 84 는 0 부터, 83 은 28 부터 찾으므로 두 자리 모두 10~7F 를 차례로 둔다
        put(dq5text.MARK_KEYS, bytes(range(0x10, 0x80)))
        put(dq5text.MARK_KEYS + 0x28, bytes(range(0x10, 0x80)))
        put(dq5text.MARK_CODES + (KANA.index('か')) * 2, dq5text.CHARS.index('が').to_bytes(2, 'little'))
        put(dq5text.MARK_CODES + (0x28 + KANA.index('は')) * 2, dq5text.CHARS.index('ぱ').to_bytes(2, 'little'))
        return d

    def render(self, font, ch, tight):
        return [[[1] * 8 for _ in range(16)]]

    def test_table_maps_bytes_to_new_glyphs_after_name_glyphs(self):
        d = self.rom()
        numbers = wn.kana_glyphs(d, object(), self.render)
        self.assertEqual(set(numbers), set(KANA) | {'が', 'ぱ'})
        self.assertEqual(sorted(numbers.values()), list(range(len(ne.GLYPHS), len(ne.GLYPHS) + len(numbers))))
        t = lorom(wn.KANA_TABLE)

        def entry(page, b):
            return int.from_bytes(d[t + page * 0x100 + b * 2:t + page * 0x100 + b * 2 + 2], 'little')
        self.assertEqual(entry(0, 0x10 + KANA.index('か')), numbers['か'])
        self.assertEqual(entry(1, 0x10 + KANA.index('か')), numbers['が'])
        self.assertEqual(entry(2, 0x10 + KANA.index('は')), numbers['ぱ'])
        self.assertEqual(entry(1, 0x10 + KANA.index('は')), 0xFFFF)
        self.assertEqual(entry(0, 0x0F), 0xFFFF)
        for ch, n in numbers.items():
            o = lorom((ne.GLYPH_BANK + n // 1024) << 16 | 0x8000 + n % 1024 * 32)
            self.assertEqual(d[o:o + 32], b'\xff' * 16 + bytes(16), ch)

    def test_glyph_spot_must_be_empty(self):
        d = self.rom()
        n = len(ne.GLYPHS)
        d[lorom((ne.GLYPH_BANK + n // 1024) << 16 | 0x8000 + n % 1024 * 32) + 31] = 1
        with self.assertRaisesRegex(ValueError, '비어 있지 않음'):
            wn.kana_glyphs(d, object(), self.render)

    def test_kana_wider_than_two_columns(self):
        with self.assertRaisesRegex(ValueError, '두 열'):
            wn.kana_glyphs(self.rom(), object(), lambda f, ch, t: [[[0] * 8] * 16] * 3)


if __name__ == '__main__':
    unittest.main()
