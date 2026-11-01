"""필드 줄 RLE 풀기(앞·뒤로 읽기, X=80·줄 끝 기준점, 좌표 −3 범위)와 입구·ルーラ 표를 합성 PRG 로 검사한다."""
import contextlib
import io
import unittest

import dq4field as f

PRG_SIZE = 32 * 0x4000

# 한 줄 256칸: X=80 에서 런이 끊기도록 앞·뒤 절반을 따로 둔다. (타일, 칸 수)
FIRST = [(1, 0x30), (3, 0x10), (9, 1), (7, 5), (2, 0x3A)]
SECOND = [(4, 0x20), (0x0C, 1), (6, 0x5F)]


def put(prg, bank, addr, data):
    o = bank * 0x4000 + (addr & 0x3FFF)
    prg[o:o + len(data)] = bytes(data)


def encode(runs):
    """테스트 쪽 독립 인코더: 0~6 은 32칸까지, 7 은 8칸까지 한 바이트, 8 이상은 한 칸 한 바이트."""
    out = []
    for tile, n in runs:
        while n:
            if tile >= 8:
                out.append(0xE0 | tile)
                n -= 1
                continue
            k = min(n, 8 if tile == 7 else 32)
            out.append(tile << 5 | (k - 1))
            n -= k
    return out


def expand(runs):
    return [t for t, n in runs for _ in range(n)]


def field_prg(rows=5):
    prg = bytearray(PRG_SIZE)
    put(prg, 0x0F, f.SIZE_W, [0xFD])
    put(prg, 0x0F, f.SIZE_H, [rows - 3])
    put(prg, f.BANK, 0x8000, [0x00, 0x90])
    a, mid = 0x9100, len(encode(FIRST))
    row = encode(FIRST) + encode(SECOND)
    for y in range(rows + 1):
        put(prg, f.BANK, 0x9000 + 4 * y, [a & 0xFF, a >> 8, mid, len(row)])
        put(prg, f.BANK, a, row)
        a += len(row)
    return prg


class CellTests(unittest.TestCase):
    def setUp(self):
        self.prg = field_prg()
        self.want = expand(FIRST) + expand(SECOND)

    def test_every_x_matches_from_all_four_reading_points(self):
        got = [f.cell(self.prg, 0, x, 3) for x in range(0x100)]
        self.assertEqual(got[3:], self.want[3:])

    def test_minus_three_range(self):
        self.assertEqual([f.cell(self.prg, 0, x, 3) for x in range(3)], [0, 0, 0])
        self.assertEqual(f.cell(self.prg, 0, 0x10, 2), 0)
        self.assertEqual(f.cell(self.prg, 0, 0x10, 5), 0)

    def test_decode_row_reference_points(self):
        out, rec, at80, end = f.decode_row(self.prg, 0, 3)
        self.assertEqual(out, self.want)
        self.assertEqual((at80, end), (rec[2], rec[3]))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(f.check(self.prg))

    def test_decode_and_lookup(self):
        grid = f.decode(self.prg, 0)
        self.assertEqual((len(grid), len(grid[0])), (5, 0x100))
        self.assertEqual(grid[4][0x80:0x82], [4, 4])
        self.assertEqual(f.lookup(grid, 0xFD, 2, 0x84, 4), 0x04)
        self.assertEqual(f.lookup(grid, 0xFD, 2, 0x84, 2), 0)

    def test_extent_counts_contiguous_rows(self):
        self.assertEqual(f.extent(self.prg, 0), (0x100, 5))

    def test_cpu_window_read(self):
        put(self.prg, 0x0F, 0xC123, [0x77])
        self.assertEqual(f.read(self.prg, 0xC123), 0x77)
        self.assertIsNone(f.read(self.prg, 0x7FFF))

    def test_rom_outside_is_none(self):
        put(self.prg, f.BANK, 0x8002, [0x00, 0x10])   # 필드 1 의 줄 표가 RAM 을 가리킴
        put(self.prg, 0x0F, f.SIZE_W + 1, [0x10])
        put(self.prg, 0x0F, f.SIZE_H + 1, [0x10])
        self.assertIsNone(f.cell(self.prg, 1, 5, 5))
        self.assertEqual(f.decode(self.prg, 1)[5][5], 0)


class EntranceTests(unittest.TestCase):
    def setUp(self):
        self.prg = prg = bytearray(PRG_SIZE)
        put(prg, *f.ARRIVE_PTR, [0x00, 0xA0])
        put(prg, 0x08, 0xA000, [0x05, 0x23, 0x10, 0x11, 0x02,
                                0x05, 0x40, 0x00, 0x00, 0x00,     # 같은 그룹 둘째는 무시
                                0xFF])
        put(prg, *f.ENTRANCE_PTR, [0x00, 0xA0])
        put(prg, 0x0E, 0xA000, [0x05, 0x30, 0x31, 0x06, 0x40, 0x41, 0xFF])

    def test_entrances_join_first_arrival(self):
        self.assertEqual(f.entrances(self.prg), [(0x05, 0x30, 0x31, 0x03, 0x10, 0x11, 0x02, 1),
                                                 (0x06, 0x40, 0x41, None, None, None, None, None)])

    def test_entrances_on_field(self):
        ents = f.entrances(self.prg)
        self.assertEqual([e[0] for e in f.entrances_on(ents, 0)], [0x06])
        self.assertEqual([e[0] for e in f.entrances_on(ents, 1)], [0x05])


if __name__ == '__main__':
    unittest.main()
