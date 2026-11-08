import os
import tempfile
import unittest
from pathlib import Path

import dq4monartcheck as mc
import dq4monport

ROOT = Path(__file__).resolve().parents[3]


def snapshot(ppu):
    """PPU 블록 앞뒤에 다른 블록을 둔 snes9x 꼴 직렬화 상태."""
    def block(name, data):
        return name + b':' + b'%06d' % len(data) + b':' + data
    return b'#!s9xsnp:0014\n' + block(b'NAM', b'Removed\x00') + block(b'CPU', bytes(48)) + block(b'PPU', ppu) + \
        block(b'VRA', bytes(16))


def screen(x, y, tile_pixels, palette):
    """OBJ 하나(8x8, 타일 0, 팔레트 palette)를 (x, y) 에 둔 (OAM, VRAM). tile_pixels 는 8x8 색 번호."""
    oam = bytearray(544)
    for i in range(128):
        oam[i * 4 + 1] = 0xF0                  # 화면 밖
    oam[0:4] = bytes((x, y - 1, 0, palette << 1))
    vram = bytearray(0x10000)
    t = 0xC000
    for r, row in enumerate(tile_pixels):
        for c, v in enumerate(row):
            bit = 0x80 >> c
            for plane, at in ((0, 2 * r), (1, 2 * r + 1), (2, 16 + 2 * r), (3, 17 + 2 * r)):
                if v >> plane & 1:
                    vram[t + at] |= bit
    return bytes(oam), bytes(vram)


PICTURE = [[(x + y) % 4 if 2 <= x < 6 else 0 for x in range(8)] for y in range(8)]


class SnapshotTests(unittest.TestCase):
    def test_reads_cgram_big_endian_and_oam_from_ppu_block(self):
        ppu = bytearray(mc.PPU_SIZE)
        ppu[mc.PPU_CGRAM + 2 * 129:mc.PPU_CGRAM + 2 * 129 + 2] = b'\x12\x34'
        ppu[mc.PPU_OAM] = 0x56
        ppu[mc.PPU_OAM + 543] = 0x78
        oam, cgram = mc.ppu_dump(snapshot(bytes(ppu)))
        self.assertEqual(cgram[129], 0x1234)
        self.assertEqual((len(oam), oam[0], oam[543]), (544, 0x56, 0x78))

    def test_rejects_other_ppu_block_size(self):
        # 코어가 바뀌어 블록 꼴이 달라지면 엉뚱한 자리를 OAM 으로 읽지 않고 멈춘다
        with self.assertRaises(ValueError):
            mc.ppu_dump(snapshot(bytes(mc.PPU_SIZE + 2)))
        with self.assertRaises(ValueError):
            mc.ppu_dump(b'not a state')


class ScreenTests(unittest.TestCase):
    def test_finds_picture_and_palette_colors(self):
        oam, vram = screen(40, 60, PICTURE, 3)
        colors = [0x1111, 0x2222, 0x3333]
        cgram = [0] * 256
        cgram[mc.OBJ_PALETTES + 16 * 3 + 1:mc.OBJ_PALETTES + 16 * 3 + 4] = colors
        s, problems = mc.judge_screen(oam, vram, cgram, PICTURE, colors)
        self.assertEqual(problems, [])
        self.assertEqual((s['hit'], s['at'], s['palettes'], s['extra']), (s['opaque'], [40, 60], [3], 0))

    def test_wrong_pixel_and_wrong_color_fail(self):
        broken = [row[:] for row in PICTURE]
        broken[3][3] = 0 if broken[3][3] else 1
        oam, vram = screen(40, 60, broken, 3)
        colors = [0x1111, 0x2222, 0x3333]
        cgram = [0] * 256
        cgram[mc.OBJ_PALETTES + 16 * 3 + 1:mc.OBJ_PALETTES + 16 * 3 + 4] = [0x1111, 0x2222, 0x7FFF]
        _, problems = mc.judge_screen(oam, vram, cgram, PICTURE, colors)
        self.assertEqual(len(problems), 2, problems)

    def test_grid_diff(self):
        self.assertEqual(mc.grid_diff(PICTURE, PICTURE), 0)
        self.assertIsNone(mc.grid_diff(PICTURE, PICTURE[:4]))


@unittest.skipUnless((ROOT / 'rom' / 'dq5.sfc').is_file() and os.environ.get('DQ4_ASSETS'),
                     'local source ROM or DQ4_ASSETS not present')
class StaticRomTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from dq5map import Rom
        cls.Rom = Rom
        cls.dq5 = Rom((ROOT / 'rom' / 'dq5.sfc').read_bytes())
        cls.folder = tempfile.TemporaryDirectory()
        cls.want, cls.shared = mc.expected(cls.dq5, Path(cls.folder.name))

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def test_every_target_has_a_picture_within_its_colors(self):
        self.assertEqual(set(self.want), {m for _, _, m in mc.targets()})
        for m, (grid, colors) in self.want.items():
            self.assertLessEqual(len(colors), 15)
            self.assertLessEqual(max(max(row) for row in grid), len(colors), f'{m:02X}')

    def test_original_rom_fails_every_number_not_listed_later(self):
        # 원래 DQ5 그림 그대로인 번호는 LATER 에 적힌 것만 「아직」, 나머지는 빠진 것으로 실패
        rows, problems = mc.static_check(self.dq5, self.dq5, self.want, self.shared)
        later = {k for k, r in rows.items() if r['status'] == 'later'}
        self.assertEqual(later, {f'{m:02X}' for m in dq4monport.LATER})
        self.assertEqual(len(problems), len(rows) - len(later) + 1)

    def test_changed_color_that_is_not_expected_fails(self):
        # 기대 그림이 아닌데 원래와도 다른 번호(반쯤 들어간 그림)는 「아직」 으로 넘기지 않는다
        import dq5mongfx as M
        from dq5map import lorom
        _, _, m = mc.targets()[0]
        table, bank = M.record_table(self.dq5)
        at = lorom(bank << 16 | self.dq5.u16(table + m * 2)) + 2
        data = bytearray(self.dq5.d)
        data[at] ^= 1
        rows, problems = mc.static_check(self.dq5, self.Rom(bytes(data)), self.want, self.shared)
        self.assertEqual(rows[f'{m:02X}']['status'], 'wrong')
        self.assertTrue(any(p.startswith(f'{m:02X}(') for p in problems), problems)


if __name__ == '__main__':
    unittest.main()
