"""dq4winwatch 판정을 지어 낸 테두리 그림과 타일맵으로 본다(롬 없이)."""
import struct
import tempfile
import unittest
from unittest import mock
from pathlib import Path

import dq4winwatch as ww

# 지어 낸 테두리 그림(색 번호 0 투명, 1 흰 선, 2 바탕). 모서리·위 변·옆 변만 판정에 닿는다
CORNER = ['02222222', '22111111', '21111111', '21122222', '21122222', '21122222', '21122222', '21122222']
EDGE = ['22222222', '11111111', '11111111', '22222222', '22222222', '22222222', '22222222', '22222222']
SIDE = ['21122222'] * 8
FILL = ['22222222'] * 8
GLYPH = ['22222222', '22122222', '22122222', '21212222', '22222222', '22222222', '22222222', '22222222']
HOLE = ['22222222', '22000222', '22222222', '22222222', '22222222', '22222222', '22222222', '22222222']
BLANK = ['00000000'] * 8
TEXT, HOLE_T = 0x40, 0x41


def planes(rows):
    p0 = bytes(int(''.join('1' if int(ch) & 1 else '0' for ch in r), 2) for r in rows)
    p1 = bytes(int(''.join('1' if int(ch) & 2 else '0' for ch in r), 2) for r in rows)
    return p0, p1


def fake_rom():
    rom = bytearray(0x30000)
    o = ww.lorom(ww.BORDER_ROM)
    for i, t in enumerate(range(ww.BORDER_FIRST, ww.BORDER_LAST + 1)):
        art = {0x8B: CORNER, 0x8C: CORNER, 0x8D: EDGE, 0x8E: SIDE}.get(t, FILL)
        p0, p1 = planes(art)
        rom[o + i * 16:o + i * 16 + 16] = p0 + p1
    return bytes(rom)


def vram_chr():
    chr_ = bytearray(ww.TILES * 16)
    for t, art in ((0, BLANK), (1, FILL), (0x8B, CORNER), (0x8C, CORNER), (0x8D, EDGE), (0x8E, SIDE), (TEXT, GLYPH),
                   (HOLE_T, HOLE), (ww.PROMPT, GLYPH)):
        p0, p1 = planes(art)
        chr_[t * 16:t * 16 + 16] = bytes(x for pair in zip(p0, p1) for x in pair)
    return bytes(chr_)


H, V = 0x4000, 0x8000


def draw(m, r1, c1, r2, c2):
    """m(32 × 32 낱말 목록)에 창을 그린다."""
    for r in range(r1, r2 + 1):
        for c in range(c1, c2 + 1):
            if (r, c) == (r1, c1):
                w = 0x8C
            elif (r, c) == (r1, c2):
                w = 0x8C | H
            elif (r, c) == (r2, c1):
                w = 0x8C | V
            elif (r, c) == (r2, c2):
                w = 0x8C | H | V
            elif r in (r1, r2):
                w = 0x8D | (V if r == r2 else 0)
            elif c in (c1, c2):
                w = 0x8E | (H if c == c2 else 0)
            else:
                w = 1
            m[r * 32 + c] = 0x2000 | w


def shot(m):
    return ww.Shot(1, 0, tuple(m), vram_chr(), 0, 0)


class CheckTest(unittest.TestCase):
    def setUp(self):
        self.ref = ww.Ref(fake_rom())
        self.m = [0x2C00] * 1024

    def rules(self):
        return sorted({(b[0], b[1], b[2]) for b in ww.check(shot(self.m), self.ref)})

    def test_whole_window_passes(self):
        draw(self.m, 15, 1, 25, 29)
        self.m[18 * 32 + 5] = 0x2000 | TEXT
        self.assertEqual(self.rules(), [])

    def test_right_border_cell_overwritten(self):
        # 가게 동료 창 3A: 줄 끝 빈칸이 오른쪽 테두리 열을 덮음
        draw(self.m, 15, 1, 25, 29)
        self.m[18 * 32 + 29] = 0x2001
        self.assertEqual(self.rules(), [(18, 29, '테두리')])

    def test_window_on_top_hides_lower_border(self):
        draw(self.m, 17, 2, 27, 29)
        draw(self.m, 2, 2, 26, 21)
        self.assertEqual(self.rules(), [])

    def test_lower_border_erased_outside_top_window(self):
        draw(self.m, 17, 2, 27, 29)
        draw(self.m, 2, 2, 26, 21)
        self.m[22 * 32 + 29] = 0x2C00
        self.assertEqual(self.rules(), [(22, 29, '테두리')])

    def test_text_outside_window(self):
        draw(self.m, 4, 4, 8, 12)
        self.m[6 * 32 + 13] = 0x2000 | TEXT
        self.assertEqual(self.rules(), [(6, 13, '창 밖')])

    def test_hole_inside_window(self):
        draw(self.m, 4, 4, 8, 12)
        self.m[6 * 32 + 6] = 0x2000 | HOLE_T
        self.assertEqual(self.rules(), [(6, 6, '깨짐')])

    def test_prompt_on_bottom_edge(self):
        draw(self.m, 17, 2, 27, 29)
        self.m[27 * 32 + 15] = 0x2000 | V | ww.PROMPT
        self.assertEqual(self.rules(), [])

    def test_closed_window_fragment(self):
        draw(self.m, 4, 4, 8, 12)
        self.m[20 * 32 + 3] = 0x2000 | 0x8E
        self.assertEqual(self.rules(), [(20, 3, '잔상')])

    def test_window_off_screen(self):
        draw(self.m, 24, 4, 29, 12)
        self.assertEqual(self.rules(), [(27, 4, '화면 밖')])

    def test_overlapping_windows_one_cell_apart(self):
        # 가게 동료 창 3A(1~30)와 뒤의 메시지 창(2~29)
        draw(self.m, 17, 2, 27, 29)
        draw(self.m, 15, 1, 25, 30)
        self.assertEqual(self.rules(), [(15, 1, '변 어긋남'), (15, 30, '변 어긋남')])

    def test_other_screen_is_skipped(self):
        # 테두리 칸 그림이 롬과 다르면 창 화면이 아니다
        draw(self.m, 4, 4, 8, 12)
        self.m[6 * 32 + 13] = 0x2000 | TEXT
        chr_ = bytearray(vram_chr())
        chr_[0x8C * 16:0x8C * 16 + 16] = bytes(16)
        self.assertEqual(ww.check(ww.Shot(1, 0, tuple(self.m), bytes(chr_), 0, 0), self.ref), [])


def record_s(id_, frame, cells, tiles):
    out = struct.pack('<cIIHHHHHHHH', b'S', id_, frame, 0x1C00, 0x1000, 0, 0, len(cells), len(tiles), 0, 0)
    out += b''.join(struct.pack('<HH', i, w) for i, w in cells)
    out += b''.join(struct.pack('<H', t) + a for t, a in tiles)
    return out


def record_e(frame, id_):
    return struct.pack('<cIi', b'E', frame, id_)


class EngineWindowsTest(unittest.TestCase):
    def setUp(self):
        self.ref = ww.Ref(fake_rom())
        self.m = [0x2C00] * 1024

    def test_repaint_after_close_rebuilds_the_stack(self):
        status, command, sub = (19, 16, 27, 28), (4, 2, 12, 13), (6, 1, 16, 10)
        draws = [(34, 2, status), (37, 1, command), (134, 0x0B, sub), (386, 2, status), (388, 1, command)]
        self.assertEqual(ww.stacks(draws)[-1][:2], (388, [status, command]))
        self.assertEqual(ww.stacks(draws)[-1][2][sub], 0x0B)
        self.assertEqual(ww.stacks(draws)[2][:2], (134, [status, command, sub]))

    def test_engine_order_decides_which_window_is_on_top(self):
        # 위 창의 테두리가 끊겨 겹친 곳의 테두리 셈으로는 위아래를 못 가르는 꼴도 엔진 그린 차례로 가른다
        draw(self.m, 17, 2, 27, 29)
        draw(self.m, 15, 1, 25, 29)
        self.m[18 * 32 + 29] = 0x2001
        bad = ww.check(shot(self.m), self.ref, engine=[(17, 2, 27, 29), (15, 1, 25, 29)])
        self.assertEqual(sorted({(b[0], b[1], b[2]) for b in bad}), [(15, 1, '변 어긋남'), (18, 29, '테두리')])

    def test_closed_engine_window_is_dropped(self):
        draw(self.m, 4, 4, 8, 12)
        bad = ww.check(shot(self.m), self.ref, engine=[(4, 4, 8, 12), (10, 10, 20, 20)])
        self.assertEqual(bad, [])


class RuleFilesTest(unittest.TestCase):
    def test_every_rule_file_has_the_contract(self):
        names = [m.NAME for m in ww.rules()]
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue({'테두리', '창 밖', '잔상', '화면 밖', '깨짐'} <= set(names))

    def test_allow_needs_a_reason_and_matches_scene_and_cells(self):
        a = ww.Allow('*/towns_slot_*', '슬롯 화면은 BG3 를 릴 그림에 씀', frozenset({(3, 4)}))
        self.assertTrue(a.matches('work/ch3walk/towns_slot_win', 3, 4))
        self.assertFalse(a.matches('work/ch3walk/towns_slot_win', 3, 5))
        self.assertFalse(a.matches('work/ch3walk/towns_prize', 3, 4))


class FileTest(unittest.TestCase):
    def test_parse_applies_deltas_and_steady_frames(self):
        m = [0x2C00] * 1024
        draw(m, 15, 1, 25, 29)
        broken = list(m)
        broken[18 * 32 + 29] = 0x2001
        chr_ = vram_chr()
        used = sorted({w & 0x3FF for w in m} | set(range(0x8B, 0x96)) | {1})
        data = b'V' + struct.pack('<H', ww.VERSION) + struct.pack('<cH', b'R', 0) + record_s(1, 10, list(enumerate(m)), [(t, chr_[t * 16:t * 16 + 16]) for t in used]) + record_e(10, 1)
        # 깨진 모습이 한 프레임만(전환 중) 보였다가, 다시 깨진 채 길게 보인다
        data += record_s(2, 20, [(18 * 32 + 29, 0x2001)], []) + record_e(20, 2) + record_e(21, 1) + record_e(40, 2)
        data += record_e(41, 1)
        data += struct.pack('<cIBBBBB', b'D', 5, 0x3A, 1, 15, 29, 11)
        rec = ww.parse(data)
        shots, events = rec.shots, rec.events
        self.assertEqual(shots[2].map[18 * 32 + 29], 0x2001)
        self.assertEqual(shots[2].map[18 * 32 + 30], m[18 * 32 + 30])
        self.assertEqual(shots[2].chr, shots[1].chr)
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / ww.DATA).write_bytes(data)
            found = ww.analyze(d, fake_rom())
            self.assertEqual([(s.id, first, n) for s, first, n, _ in found], [])
            (Path(d) / ww.DATA).write_bytes(data.replace(record_e(41, 1), record_e(44, 1)))
            found = ww.analyze(d, fake_rom())
            self.assertEqual([(s.id, first, n) for s, first, n, _ in found], [(2, 40, 4)])
            self.assertEqual([b[:3] for b in found[0][3]], [(18, 29, '테두리')])

    def test_sprite_scene_and_wram_records(self):
        head = b'V' + struct.pack('<H', ww.VERSION)
        spec = b'201D:1,2040:2'
        ospec = b'3020:2'
        data = head + struct.pack('<cH', b'R', len(spec)) + spec + struct.pack('<cH', b'Q', len(ospec)) + ospec
        data += record_s(1, 10, [], []) + struct.pack('<cH', b'W', 2) + struct.pack('<HB', 0, 3) + struct.pack('<HB', 2, 0x41)
        data += struct.pack('<cIH', b'O', 11, 1) + struct.pack('<HH', 0, 0x1234)
        data += struct.pack('<cH', b'P', 1) + struct.pack('<HB', 1, 0x77)
        data += struct.pack('<cIHHBBBBBBB', b'B', 11, 0x6000, 0x1000, 0, 15, 0, 1, 1, 0x17, 0x17)
        data += struct.pack('<cIBBBBBB', b'M', 12, 0x37, 0x00, 0, 0, 0x50, 2)
        data += struct.pack('<cIB', b'F', 13, 3)
        data += struct.pack('<cIHHH', b'J', 42, 0x6000, 0x1000, 1) + struct.pack('<H', 3) + bytes(range(32)) + bytes(512)
        rec = ww.parse(data)
        self.assertEqual(rec.shots[1].wram, {0x201D: 3, 0x2041: 0x41})
        self.assertEqual(rec.oam[0][0], 11)
        self.assertEqual(rec.oam[0][1][:2], b'\x34\x12')
        self.assertEqual(rec.oam[0][2], {0x3021: 0x77})
        self.assertEqual(rec.obj, [(11, 0x6000, 0x1000, 0, 15, 0, 1, 1, 0x17, 0x17)])
        self.assertEqual(rec.maps, [(12, 0x37, 0x00, 0, 0, 0x50, 2)])
        self.assertEqual(len(rec.objvram[0][4]), 512)
        self.assertEqual(rec.overs, [(13, True, True)])
        self.assertEqual(rec.objvram[0][3][96:128], bytes(range(32)))
        self.assertEqual(ww.Screen(rec.shots[1], None).wram(0x2040, 2), [None, 0x41])

    def test_run_rule_reports_frames(self):
        import types
        rule = types.SimpleNamespace(NAME='스프라이트', MODE='report', ALLOW=(),
                                     check_run=lambda run: [(f, '맵 바뀜') for f, *_ in run.record.maps])
        data = b'V' + struct.pack('<H', ww.VERSION) + struct.pack('<cH', b'R', 0)
        data += struct.pack('<cIBBBBBB', b'M', 12, 0x37, 0x00, 0, 0, 0x50, 1)
        with tempfile.TemporaryDirectory() as d, mock.patch.object(ww, 'rules', return_value=[rule]):
            (Path(d) / ww.DATA).write_bytes(data)
            self.assertEqual(ww.run_hits(d, fake_rom()), [(12, '스프라이트', '맵 바뀜', 'report')])
            self.assertEqual(ww.report(d, fake_rom()), (1, 0))
            self.assertIn('프레임 12 스프라이트: 맵 바뀜', (Path(d) / ww.LOG).read_text(encoding='utf-8'))

    def test_wram_ranges_merge(self):
        import types
        rules = [types.SimpleNamespace(WRAM=[(0x2040, 30), (0x201D, 1)]), types.SimpleNamespace(WRAM=[(0x2050, 30)])]
        rules.append(types.SimpleNamespace(OAM_WRAM=[(0x3020, 64)]))
        with mock.patch.object(ww, 'rules', return_value=rules):
            self.assertEqual(ww.wram_ranges(), [(0x201D, 1), (0x2040, 0x2050 + 30 - 0x2040)])
            self.assertEqual(ww.wram_env(attr='OAM_WRAM'), '3020:64')
            self.assertEqual(ww.wram_env(), '201D:1,2040:46')

    def test_readset_keeps_judgement_out_of_cache(self):
        # 판정 글은 규칙 코드로 다시 만들므로 캐시 출력·재검증에서 빼고, 기록하는 WRAM 조각 목록은 캐시 키에 든다
        import dq4readset
        self.assertIn(ww.LOG, dq4readset.SKIP)
        with tempfile.TemporaryDirectory() as d, mock.patch.object(ww, 'wram_env', side_effect=lambda ranges=None, attr='WRAM': attr):
            parts = dq4readset.key_parts(__file__, b'rom', __file__, Path(d), {}, ())
        self.assertEqual(parts['winwatch'], ['WRAM', 'OAM_WRAM'])

    def test_flicker_with_the_same_broken_cell_is_caught(self):
        # 이름이 프레임마다 바뀌어 모습이 한 프레임씩만 보여도, 같은 칸이 계속 깨져 있으면 건다
        m = [0x2C00] * 1024
        draw(m, 15, 1, 25, 29)
        m[18 * 32 + 29] = 0x2001
        other = list(m)
        other[18 * 32 + 5] = 0x2000 | TEXT
        chr_ = vram_chr()
        used = sorted({w & 0x3FF for w in m} | set(range(0x8B, 0x96)) | {1, TEXT})
        data = b'V' + struct.pack('<H', ww.VERSION) + struct.pack('<cH', b'R', 0)
        data += record_s(1, 10, list(enumerate(m)), [(t, chr_[t * 16:t * 16 + 16]) for t in used])
        data += record_s(2, 11, [(18 * 32 + 5, other[18 * 32 + 5])], [])
        data += b''.join(record_e(10 + k, 1 + k % 2) for k in range(6)) + record_e(16, -1)
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / ww.DATA).write_bytes(data)
            found = ww.analyze(d, fake_rom())
        self.assertTrue(found)
        self.assertEqual({(b[0], b[1], b[2]) for _, _, _, bad in found for b in bad}, {(18, 29, '테두리')})

    def test_broken_file_is_an_error(self):
        with self.assertRaises(ValueError):
            ww.parse(b'X')
        with self.assertRaises(ValueError):
            ww.parse(b'V\x01\x00')
        # 판 4 기록은 그대로 읽는다
        self.assertEqual(ww.parse(b'V\x04\x00').overs, [])


if __name__ == '__main__':
    unittest.main()
