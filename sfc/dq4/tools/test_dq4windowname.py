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


class MessageCellTest(unittest.TestCase):
    def test_message_cells_match_slot_tiles(self):
        # 메시지 창은 화면 18~26줄·3~28열에 캔버스를 한 줄 26칸씩 차례로 가리킨다
        def cell(t):
            d = t - CANVAS.start
            return 0x5000 + ((18 + d // ROW) * 32 + 3 + d % ROW) * 2
        cells = table('WtMsgCellF')
        for i, (lo, up, c) in enumerate(zip(table('WtSlotF'), table('WtUpperF'), table('WtClassF'))):
            row = cells[8 * i:8 * i + 8]
            if c == 0xFF or c & 0x20:
                self.assertEqual(row, [0] * 8)
                continue
            n = COLS[c & 0x0F]
            up = up or lo + n
            self.assertEqual(row, [cell(lo), lo, cell(lo + n - 1), lo + n - 1, cell(up), up, cell(up + n - 1), up + n - 1])


def define(name):
    return int(re.search(rf'^!{name} *= *\$([0-9A-Fa-f]+)', ASM.read_text(), re.M).group(1), 16)


class HoldAreaTest(unittest.TestCase):
    # 7F:8300~FFFF 는 1장 이어 걷기·창 검사 장면에서 읽는 곳이 없고, 월드 필드 밖에서는 맵을 불러올 때 지우기만 한다(접근
    # 카운터·쓰기 추적 실측). 묶음 버퍼의 머리·후보 표·버퍼가 그 안에서 겹치지 않아야 한다
    FREE = range(0x7F8300, 0x800000)

    def test_hold_parts_do_not_overlap_and_stay_in_the_free_area(self):
        parts = [(define('wh_magic'), 0x10), (define('wt_stc'), 16), (define('wh_buf'), define('wh_size'))]
        for (a, n), (b, _) in zip(parts, parts[1:]):
            self.assertLessEqual(a + n, b)
        for a, n in parts:
            self.assertIn(a, self.FREE)
            self.assertIn(a + n - 1, self.FREE)

    def test_counters_sit_in_the_head(self):
        for name in ('wh_count', 'wh_off', 'wh_rd', 'wh_go'):
            self.assertIn(define(name), range(define('wh_magic') + 2, define('wt_stc')))

    def test_send_tables_stay_after_the_buffer_in_the_free_area(self):
        # WhReq 가 짜는 DMA 표·임시 칸은 묶음 버퍼 뒤, 실측으로 비어 있던 7F:A33F 안. 표는 가장 많이 찼을 때
        # (DMA !wh_ndma 칸 × 8바이트, 끝 표시 2바이트)도 다음 자리를 덮지 않아야 한다
        text = ASM.read_text()

        def count(name):
            return int(re.search(rf'^!{name} *= *(\d+)', text, re.M).group(1))
        end = define('wh_buf') + define('wh_size')
        parts = sorted([(define('wh_dma'), count('wh_ndma') * 8 + 2)]
                       + [(define(n), 2) for n in ('wh_snap', 'wh_snapn', 'wh_tmpn', 'wh_tmpl', 'wh_tmpb', 'wh_tmpr',
                                                   'wh_tmps')])
        self.assertGreaterEqual(parts[0][0], end)
        for (a, n), (b, _) in zip(parts, parts[1:]):
            self.assertLessEqual(a + n, b, hex(a))
        self.assertLessEqual(parts[-1][0] + parts[-1][1], 0x7FA340)

    def test_with_sends_no_tilemap_cells_of_its_own(self):
        # 메시지 창 칸을 001 로 가리던 장치는 지웠다: 메시지가 새로 그리는 칸까지 가렸고, 푸는 $0BEC 재요청은 WhWith 가 NMI
        # 작업을 8CEF 로 둔 뒤라 소비되지 않아 글이 빠진 채 남았다. 다시 넣으려면 푸는 쪽(버퍼 값 되쓰기)부터 만든다
        text = ASM.read_text()
        body = re.search(r'^WhWith:\n(.*?)^[A-Za-z]\w*:', text, re.M | re.S).group(1)
        self.assertNotIn('$002118', body)
        self.assertNotIn('WhCellOf', text)

    def test_head_flags_sit_before_the_stale_table(self):
        for name in ('wh_msgwin', 'wh_pend'):
            self.assertIn(define(name), range(define('wh_go') + 2, define('wt_stc')))

    def test_stale_slot_numbers_leave_bit7_free(self):
        # 후보 바이트는 슬롯 × 2 + 1 이고 bit7 은 「지금 버퍼에선 메시지 창이 안 가리킴」 표시
        self.assertLess((int(re.search(r'^!wt_nslot = (\d+)', ASM.read_text(), re.M).group(1)) - 1) * 2 + 1, 0x80)


class WramTest(unittest.TestCase):
    # DQ5 의 움직이는 타일 종류 14 사본(03:D9A0 의 원본 7E:3D14, 11칸 × 32바이트). 1E/00·20/06·32/00 등에 들어가면
    # 03:D3E9 가 채운다. 창 글자 변수가 여기 있으면 대기열 항목 수가 덮여 NMI 가 BG3 타일맵에 쓰레기를 보냈다
    ANIM14 = range(0x3D14, 0x3D14 + 11 * 32)

    def test_no_window_variable_in_the_dq5_anim_copy(self):
        for name, value in re.findall(r'^!(w[a-z_0-9]+) *= *\$([0-9A-Fa-f]{4})\b', ASM.read_text(), re.M):
            a = int(value, 16)
            size = 0xA0 if name == 'wn_stage' else 2
            self.assertFalse(set(range(a, a + size)) & set(self.ANIM14), name)

    # 7E:A9xx·AAxx 에 둔 변수마다 바이트 수(정의 주석의 크기). 없는 이름은 워드
    SIZES = {'wn_stage': 0xA0, 'wt_ages': 60, 'wt_keys': 60, 'wt_vis': 30, 'wt_kbase': 12, 'wt_klen': 12, 'wt_occ': 13,
             'wt_dirty': 4, 'wt_xfer': 1, 'wt_stale': 1, 'wt_stale2': 1, 'wt_ecsave': 1, 'wq_defer': 1}

    def test_moved_block_stays_in_the_free_area_without_overlap(self):
        # 앞은 전투 글 엔진(!bm_sfx 가 마지막, 2바이트), 끝은 7E:AC00
        bm_end = int(re.search(r'^!bm_sfx *= *\$([0-9A-F]{4})', dq4battlemsg.WRAM, re.M).group(1), 16) + 2
        parts = sorted((int(v, 16), self.SIZES.get(n, 2), n) for n, v in
                       re.findall(r'^!(w[a-z_0-9]+) *= *\$(A[0-9A-F]{3})\b', ASM.read_text(), re.M))
        self.assertGreater(len(parts), 30)
        for a, size, name in parts:
            self.assertGreaterEqual(a, bm_end, name)
            self.assertLessEqual(a + size, 0xAC00, name)
        for (a, size, name), (b, _, nxt) in zip(parts, parts[1:]):
            self.assertLessEqual(a + size, b, f'{name} {nxt}')


class NmiHookTest(unittest.TestCase):
    # 전투 작업의 큰 그림 길(00:895D~896E, 00:FD4A 의 0B00바이트 DMA)은 원래 롬에서도 VBlank 끝 직전에 끝난다. 그 앞에
    # 명령을 더하면 DMA 꼬리가 버려져 전투 배경에 검은 칸이 생겼다. 공통 입구 00:887C 와 그 길은 고치지 않는다
    def test_heavy_battle_path_and_common_entry_untouched(self):
        orgs = [int(a, 16) for a in re.findall(r'^org \$([0-9A-F]{6})\b', ASM.read_text(), re.M)]
        self.assertNotIn(0x00887C, orgs)
        self.assertFalse([a for a in orgs if 0x008952 <= a < 0x00896F])
        self.assertIn(0x00896F, orgs)

def lorom(a):
    return ((a >> 16) & 0x7F) * 0x8000 + (a & 0x7FFF)


WINDOWS = 0x04EB48
LIST_PREV = 0x6123AB
PREFIX_PREV = 0x608000
# 창 레코드는 apply 가 보는 바이트만 맞추고 나머지는 5A 로 채운 합성 값
F = 0x5A
NAME_LIST = bytes((0x05, F, 0x08, F, F, 0xD0, F, 0x80))


def base_windows():
    out = {
        wn.STATUS_WINDOW: bytes((F, F, 0x06, F, F, 0x80)),
        **{w: bytes((0x02, F, 0xE6, F)) + wn.BATTLE_STATUS_BODY + b'\x80' for w in wn.BATTLE_STATUS},
        **{w: bytes((F, F, 0x06, F)) + wn.HP_BODY[w] + b'\x80' for w in wn.HP_WINDOWS},
        wn.SPELL_WINDOW: bytes((F, F, 0x08, F)) + wn.SPELL_BODY + b'\x80',
        wn.SHOP_MEMBERS: wn.SHOP_MEMBERS_HEAD + bytes((F, F)) + wn.SHOP_MEMBERS_ROW + b'\x80',
        **{w: head + bytes((F, F, 0x80)) for w, head, _ in wn.FORMATION},
        wn.TACTIC_WINDOW: wn.TACTIC_HEAD + bytes((F, 0x80)),
        wn.SHOP_BUY: bytes((F, F, 0x14, F, F, F)) + wn.SHOP_BUY_ROW[0] + b'\x80',
        wn.SHOP_SELL_ALIAS: wn.SHOP_SELL_ALIAS_RECORD,
        wn.SHOP_SELL_ITEMS: wn.SHOP_SELL_ITEMS_SHAPE[:2] + b'\x08' + wn.SHOP_SELL_ITEMS_SHAPE[2:] + b'\x80',
        wn.QTY_WINDOW: wn.QTY_RECORD + b'\x80',
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
        put(a, wn.SHOP_RESOLVE_ORIG)
    put(wn.CODE_TABLE + (wn.SHOP_SELL_CODE - 0xB0) * 2, wn.SHOP_SELL_CODE_ORIG)
    for a in wn.BUY_SITES:
        put(a, wn.BUY_ORIG + wn.BUY_CALL)
    for a, want in wn.BUY_CONFIRM_ORIG:
        put(a, want)
    for a, orig in ((wn.SELL_QTY_SITE, wn.SELL_QTY_ORIG), (wn.SELL_GIVE_SITE, wn.SELL_GIVE_ORIG),
                    (wn.SELL_NO_SITE, wn.SELL_NO_ORIG), (wn.SELL_ASK_SITE, wn.SELL_ASK_ORIG),
                    (wn.QTY_UP_SITE, wn.QTY_UP_ORIG), (wn.QTY_DOWN_SITE, wn.QTY_DOWN_ORIG),
                    (wn.QP_FRAME_SITE, wn.QP_FRAME_ORIG), *((a, wn.QP_OPEN_ORIG) for a in wn.QP_OPEN_SITES)):
        put(a, orig)
    put(wn.GIVE_SITE, wn.GIVE_ORIG + wn.GIVE_TAIL)
    for a in wn.HELD_SITES:
        rel = lorom(wn.HELD_PICKER) - (lorom(a) + 6)
        put(a, wn.HELD_ORIG + rel.to_bytes(2, 'little', signed=True))
    put(wn.EMPTY_SLOT_HOOK, wn.EMPTY_SLOT_ORIG)
    put(wn.WH_REQ_SITE, wn.WH_REQ_ORIG)
    put(wn.NENE_SPOT, b'\xff' * (wn.NENE_SPOT_END - wn.NENE_SPOT))
    for a, orig in wn.NMI_SITES:
        put(a, orig)
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


class WindowListTest(unittest.TestCase):
    """asm 이 창 번호로 가르는 목록이 dq4windowname 상수(정적 검사 dq4windowlint 도 읽음)와 같아야 한다."""

    def test_nine_column_windows_match(self):
        text = ASM.read_text()
        body = re.search(r'^WtNineWins:\n    db (.*)$', text, re.M).group(1)
        self.assertEqual(tuple(int(v, 16) for v in re.findall(r'\$([0-9A-Fa-f]{2})', body)), wn.NINE_WINDOWS)

    def test_name_step_windows_match(self):
        text = ASM.read_text()
        body = text[text.index('WnList:'):text.index('WnKorean:')]
        block = body[body.index('LDA.w $0A00'):body.index('\n++\n')]
        self.assertEqual(sorted(int(v, 16) for v in re.findall(r'CMP #\$([0-9A-F]{2})', block)), sorted(wn.NAME_STEP5_WINDOWS))


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
        # 전투 상태 창은 맨 오른쪽 사람의 이름 다섯째 칸이 테두리 열을 덮지 않게 한 칸 넓힌다(위치·위쪽 비트는 그대로)
        for w in wn.BATTLE_STATUS:
            self.assertEqual(self.head(w)[:3], bytes((0x02, F, 0xE7)), f'{w:02X}')
        for w in wn.NAME_LISTS + (wn.TACTIC_WINDOW,):
            b, a = self.head(w, before), self.head(w, after)
            self.assertEqual((a[0], a[2]), (b[0] - 1, b[2] + 1), f'{w:02X}')
        # 가게 동료 창은 아래 메시지 창과 좌우 변이 맞는 원래 자리·너비 그대로(한 사람 몫을 이름 5 + 상태 8 로 나눔)
        o, p = window(before, wn.SHOP_MEMBERS), window(after, wn.SHOP_MEMBERS)
        self.assertEqual(after[p:p + 5], before[o:o + 5])     # 제목 가로 자리(+4)도 그대로
        self.assertEqual(self.head(wn.SPELL_WINDOW)[2], 8 + 2)
        for w, h, left in wn.FORMATION:
            self.assertEqual(self.head(w)[:3], bytes((h[0] - left, h[1], h[2] + 1)))

    def test_shop_members_cells_fill_the_window(self):
        inner = (wn.SHOP_MEMBERS_HEAD[2] & 0x1F) - 2
        self.assertEqual(2 * (wn.SHOP_NAME_CELLS + wn.SHOP_STATE_CELLS), inner)
        self.assertLess(wn.SHOP_STATE_COLS, wn.SHOP_STATE_CELLS)
        self.assertEqual(self.defs['!shop_members'], f'${wn.SHOP_MEMBERS:02X}')
        self.assertEqual(int(self.defs['!shop_state_cells']), wn.SHOP_STATE_CELLS)
        # 이름 다섯 칸(Y 10)은 WnList, 상태 여덟 칸은 WnMonster 가 이 창일 때 고른다
        asm = ASM.read_text(encoding='utf-8')
        monster = asm[asm.index('\nWnMonster:'):asm.index('\nWnText:')]
        self.assertIn('CMP #!shop_members', monster)
        self.assertIn('LDA #!shop_state_cells', monster)
        # 가나 글자(장비 비교 값)는 앞 빈칸을 건너 $02 부터 여덟 칸: 뒤 빈칸이 다음 사람 이름과 띄우는 칸으로 남는다
        text = asm[asm.index('\nWnText:'):asm.index('\nWtAlloc:')]
        self.assertIn('CMP #!shop_members\n    BNE +\n    INX\n+\n    JML $04B7A3', text)
        self.assertEqual(len(wn.shop_states()), 4 + 12)
        for key in wn.shop_states():
            self.assertIn(key, dq4windowtext.FIXED)

    def test_shop_state_must_fit_its_cells(self):
        def wide(font, text):
            return [b''] * (wn.SHOP_STATE_COLS + 1 if text == dq4windowtext.FIXED['　そうびできない'] else 2)
        with mock.patch.object(dq4windowtext, 'columns', side_effect=wide), \
                self.assertRaisesRegex(ValueError, '가게 동료 창 상태'):
            with mock.patch.object(dq4windowtext, 'build', return_value=(TEXT, {})), \
                    mock.patch.object(wn.subprocess, 'run', FakeAsar()):
                wn.apply(bytes(base_rom()), object(), 'asar')

    @unittest.skipUnless(os.environ.get('DQ4_GALMURI'), 'DQ4_GALMURI 가 필요')
    def test_shop_states_fit_in_galmuri9(self):
        import dq4menupatch
        font = dq4menupatch.Font('galmuri9')
        cols = {dq4windowtext.FIXED[k]: len(dq4windowtext.columns(font, dq4windowtext.FIXED[k])) for k in wn.shop_states()}
        # Galmuri9 v2.40.4 실측. 문구나 글꼴이 바뀌면 이 표를 다시 재고, 일곱 열(SHOP_STATE_COLS)을 넘지 않는지 본다
        want = {' 장비 중': 5, ' 소지 중': 5, ' 장비 불가': 7, ' 없음': 4,
                **{f' {n}개 소지': 6 for n in range(1, 10)}, ' 10개 소지': 7, ' 11개 소지': 6, ' 12개 소지': 7}
        self.assertEqual(cols, want)
        self.assertLessEqual(max(cols.values()), wn.SHOP_STATE_COLS, cols)

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
        for n, at, value in ((wn.STATUS_WINDOW, 2, 0x07), (0x17, 2, 0xE7), (0x26, 5, 0x13),
                             (wn.SPELL_WINDOW, 7, 0xD5), (0x45, 2, 0x0F),
                             (wn.SHOP_SELL_ALIAS, 2, 0x10)):
            with self.subTest(n=hex(n)):
                bad = bytearray(base_windows()[n])
                bad[at] = value
                with self.assertRaisesRegex(ValueError, f'^창 {n:02X} '):
                    run(base_rom({**base_windows(), n: bytes(bad)}))

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

    def test_nene_spot_must_be_left_empty_by_the_titles(self):
        rom = base_rom()
        rom[lorom(wn.NENE_SPOT) + 3] = 0x01
        with self.assertRaisesRegex(ValueError, '빈자리'):
            run(rom)

    def test_code_past_its_area(self):
        def spill(rom):
            good_asar(rom)
            rom[lorom(wn.CODE_END)] = 1
        with self.assertRaisesRegex(ValueError, '벗어남'):
            run(base_rom(), FakeAsar(spill))

    def test_window_request_site_must_be_the_original(self):
        rom = base_rom()
        rom[lorom(wn.WH_REQ_SITE)] = 0xEA
        with self.assertRaises(ValueError):
            run(rom, FakeAsar(good_asar))

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



class CodeRoomTests(unittest.TestCase):
    def test_room_counts_tail_per_region(self):
        rom = bytearray(0x400000)
        rom[lorom(wn.CODE):lorom(wn.CODE) + 0x100] = b'\x01' * 0x100
        rom[lorom(wn.CODE2)] = 0x60
        left = wn.room(rom)
        self.assertEqual(left[(wn.CODE, wn.CODE_END)], wn.CODE_END - wn.CODE - 0x100)
        self.assertEqual(left[(wn.CODE2, wn.CODE2_END)], wn.CODE2_END - wn.CODE2 - 1)
        self.assertEqual(left[(wn.WH_EXTRA, wn.KANA_TABLE)], wn.KANA_TABLE - wn.WH_EXTRA)
        self.assertEqual(left[(dq4battlemsg.CODE_AT, wn.CODE2)], wn.CODE2 - dq4battlemsg.CODE_AT)

    def test_regions_do_not_overlap_and_stay_in_one_bank(self):
        regions = sorted([(wn.CODE, wn.CODE_END), (wn.CODE_END, wn.CODE_END + 0x100), (wn.WH_EXTRA, wn.KANA_TABLE),
                          (dq4battlemsg.CODE_AT, wn.CODE2), (wn.CODE2, wn.CODE2_END)])
        for (a, b), (c, _) in zip(regions, regions[1:]):
            self.assertLessEqual(b, c)
        self.assertEqual({a >> 16 for a, _ in regions} | {(b - 1) >> 16 for _, b in regions}, {wn.CODE >> 16})

    def test_each_region_ends_with_an_assert(self):
        """넘치면 asar 가 멈춘다. 첫 구역은 빌드 뒤 E000~E0FF 검사도 있다."""
        asm = ASM.read_text(encoding='utf-8')
        self.assertIn('assert pc() <= !wn_code_end\norg !wn_code2', asm)
        self.assertIn('assert pc() <= !wn_code2_end', asm)
        self.assertIn('assert pc() <= !wn_kana_table', asm)
        self.assertIn('assert pc() <= !wn_code2', (ASM.parent / 'dq4battlemsg.asm').read_text(encoding='utf-8'))


class NameSlotTest(unittest.TestCase):
    """WnSlot: 이름 자리 여덟을 돌려 쓰되, 버퍼에서 아직 제 첫 이름 칸(180 + 자리 × 10)을 가리키는 자리는 건너뛴다.
    뒤에 어둡게 남은 상태 창 이름 자리를 「누구」 창 이름이 덮어 이름이 바뀌고 위 테두리 합성이 사라졌다."""

    def test_reuse_skips_positions_still_on_screen(self):
        asm = ASM.read_text(encoding='utf-8')
        body = asm[asm.index('\nWnSlot:'):]
        body = body[:body.index('\n.found')]
        self.assertIn('.pick', body)
        self.assertIn('ADC #$0180', body)
        self.assertIn('AND #$03FF', body)
        self.assertIn('BEQ .pick', body)
        self.assertIn('LDA #$0008\n    STA.w !wn_r', body)     # 모두 쓰이면 차례대로
class VisibleTest(unittest.TestCase):
    """WtVis: 슬롯은 키 줄의 열 칸 가운데 하나라도 그 슬롯 그림이면 보인다(앞 창이 이름 앞부분만 덮은 뒤 창)."""

    def body(self, name):
        asm = ASM.read_text(encoding='utf-8')
        start = asm.index(f'\n{name}:')
        return asm[start:asm.index('\n; ', start + 1)]

    def test_any_cell_of_the_key_row_counts(self):
        vis = self.body('WtVis')
        self.assertIn('JSR WtColsOf', vis)
        self.assertIn('INC.w !wq_left\n    INY\n    INY\n    BRA -', vis)
        # 전용 칸 문구도 첫 칸만이 아니라 !wt_fix_scan 칸을 본다(16비트 즉값이어야 함)
        self.assertIn('LDA.w #!wt_fix_scan', vis)

    def test_cols_of_a_slot(self):
        """가나 항목은 칸 수의 반, 캔버스 슬롯은 크기 묶음 4·7·10(dq4windowcheck.slot_table 과 같음)."""
        cols = self.body('WtColsOf')
        self.assertIn('LDA.w !wt_klen,X', cols)
        found = [int(v, 16) for v in re.findall(r'LDA #\$([0-9A-F]{4})\n    RTS', cols)]
        self.assertEqual(found, [4, 7, 10, 0])

if __name__ == '__main__':
    unittest.main()
