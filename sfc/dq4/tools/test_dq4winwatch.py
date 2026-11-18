"""dq4winwatch 판정을 지어 낸 테두리 그림과 타일맵으로 본다(롬 없이)."""
import struct
import tempfile
import unittest
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
        return sorted({(r, c, rule) for r, c, rule, _ in ww.check(shot(self.m), self.ref)})

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

    def test_other_screen_is_skipped(self):
        # 테두리 칸 그림이 롬과 다르면 창 화면이 아니다
        draw(self.m, 4, 4, 8, 12)
        self.m[6 * 32 + 13] = 0x2000 | TEXT
        chr_ = bytearray(vram_chr())
        chr_[0x8C * 16:0x8C * 16 + 16] = bytes(16)
        self.assertEqual(ww.check(ww.Shot(1, 0, tuple(self.m), bytes(chr_), 0, 0), self.ref), [])


def record_s(id_, frame, cells, tiles):
    out = struct.pack('<cIIHHHHHH', b'S', id_, frame, 0x1C00, 0x1000, 0, 0, len(cells), len(tiles))
    out += b''.join(struct.pack('<HH', i, w) for i, w in cells)
    out += b''.join(struct.pack('<H', t) + a for t, a in tiles)
    return out


def record_e(frame, id_):
    return struct.pack('<cIi', b'E', frame, id_)


class FileTest(unittest.TestCase):
    def test_parse_applies_deltas_and_steady_frames(self):
        m = [0x2C00] * 1024
        draw(m, 15, 1, 25, 29)
        broken = list(m)
        broken[18 * 32 + 29] = 0x2001
        chr_ = vram_chr()
        used = sorted({w & 0x3FF for w in m} | set(range(0x8B, 0x96)) | {1})
        data = record_s(1, 10, list(enumerate(m)), [(t, chr_[t * 16:t * 16 + 16]) for t in used]) + record_e(10, 1)
        # 깨진 모습이 한 프레임만(전환 중) 보였다가, 다시 깨진 채 길게 보인다
        data += record_s(2, 20, [(18 * 32 + 29, 0x2001)], []) + record_e(20, 2) + record_e(21, 1) + record_e(40, 2)
        data += record_e(41, 1)
        shots, events = ww.parse(data)
        self.assertEqual(shots[2].map[18 * 32 + 29], 0x2001)
        self.assertEqual(shots[2].map[18 * 32 + 30], m[18 * 32 + 30])
        self.assertEqual(shots[2].chr, shots[1].chr)
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / ww.DATA).write_bytes(data)
            found = ww.analyze(d, fake_rom())
            self.assertEqual([(s.id, first, n) for s, first, n, _ in found], [])
            (Path(d) / ww.DATA).write_bytes(data.replace(record_e(41, 1), record_e(44, 1)))
            found = ww.analyze(d, fake_rom())
            self.assertEqual([(s.id, first, n) for s, first, n, _ in found], [(2, 20, 4)])
            self.assertEqual([b[:3] for b in found[0][3]], [(18, 29, '테두리')])

    def test_broken_file_is_an_error(self):
        with self.assertRaises(ValueError):
            ww.parse(b'X')


if __name__ == '__main__':
    unittest.main()
