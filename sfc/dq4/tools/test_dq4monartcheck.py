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


def two_screen(lines, colors):
    """같은 그림(PICTURE)을 (40,60)·(100,60) 에 OAM 팔레트 lines 로 두고 CGRAM 줄 k 에 colors[k] 를 둔 덤프."""
    oam, vram = screen(40, 60, PICTURE, lines[0])
    oam = bytearray(oam)
    oam[4:8] = bytes((100, 59, 0, lines[1] << 1))
    cgram = [0] * 256
    for k, c in enumerate(colors):
        cgram[mc.OBJ_PALETTES + 16 * k + 1:mc.OBJ_PALETTES + 16 * k + 1 + len(c)] = c
    return bytes(oam), vram, cgram


class GroupTests(unittest.TestCase):
    COLORS = [0x1111, 0x2222, 0x3333]

    def test_same_species_on_two_lines(self):
        # 같은 종 두 무리는 줄 둘을 쓰고, 둘 다 그 종의 색이어야 한다
        oam, vram, cgram = two_screen((0, 1), [self.COLORS, self.COLORS])
        out, problems = mc.judge_group(oam, vram, cgram, (0x30, 0x30), {0x30: (PICTURE, self.COLORS)})
        self.assertEqual(problems, [])
        self.assertEqual(sorted(f['palettes'][0] for f in out['30']), [0, 1])

    def test_second_line_with_other_colors_fails(self):
        oam, vram, cgram = two_screen((0, 1), [self.COLORS, [0x1111, 0x2222, 0x7FFF]])
        _, problems = mc.judge_group(oam, vram, cgram, (0x30, 0x30), {0x30: (PICTURE, self.COLORS)})
        self.assertEqual(problems, ['30 줄 1 CGRAM 색이 기대와 다름'])

    def test_drawn_on_wrong_line_fails(self):
        oam, vram, cgram = two_screen((0, 0), [self.COLORS, self.COLORS])
        _, problems = mc.judge_group(oam, vram, cgram, (0x30, 0x30), {0x30: (PICTURE, self.COLORS)})
        self.assertIn('30 그림의 OBJ 팔레트 [0, 0], 무리 줄 [0, 1]', problems)

    def test_unplaced_group_is_not_judged(self):
        # 화면 폭에 들지 않는 무리(놓인 수 0)는 그림도 줄 색도 없다
        oam, vram = screen(40, 60, PICTURE, 0)
        cgram = [0] * 256
        cgram[mc.OBJ_PALETTES + 1:mc.OBJ_PALETTES + 4] = self.COLORS
        _, problems = mc.judge_group(oam, vram, cgram, (0x30, 0x30), {0x30: (PICTURE, self.COLORS)}, [1, 0])
        self.assertEqual(problems, [])


class CoverTests(unittest.TestCase):
    def test_covers_every_line_pair_in_order(self):
        # 무리 차례 그대로 센다: (1, 2) 와 (2, 1) 은 짝이 다르다
        orders = [(1, 2), (2, 1), (1, 3, 2), (4,)]
        picked, twice = mc.cover(orders, {1, 2, 3})
        self.assertEqual(mc.pairs_of(picked, {1, 2, 3}), mc.pairs_of(orders, {1, 2, 3}))
        self.assertEqual(twice, [])

    def test_done_pairs_and_unplaced_groups_are_left_out(self):
        orders = [(1, 2), (2, 1)]
        self.assertEqual(mc.cover(orders, {1, 2}, done={(1, 0), (2, 1)})[0], [(2, 1)])
        placed = {(1, 2): [1, 0], (2, 1): [1, 1]}.get
        self.assertEqual(mc.pairs_of(orders, {1, 2}, placed), {(1, 0), (2, 0), (1, 1)})

    def test_one_twice_order_per_species(self):
        orders = [(5, 5, 6), (5, 5), (6, 7, 6), (7,)]
        picked, twice = mc.cover(orders, {5, 6, 7})
        doubled = {m for o in picked + twice for m in o if o.count(m) > 1}
        self.assertEqual(doubled, {5, 6})


class FakeRom:
    """LoROM 주소 → 바이트 사전(dq5map.Rom 과 같은 u8·u16)."""
    def __init__(self, data):
        self.data = data

    def u8(self, a):
        return self.data.get(a, 0)

    def u16(self, a):
        return self.u8(a) | self.u8(a + 1) << 8


def background_rom(first, count, colors=1):
    """배경 31 칸이 모두 칸 0(낮)·2(밤)을 쓰고, 표의 모든 칸이 [count][first] 에 줄마다 색 colors 개인 레코드를 가리키는 롬."""
    data = {}
    record = [count, first] + [b for _ in range(count) for b in [colors] + [0x11, 0x22] * colors]
    for slot in range(0, 0x100, 2):
        data[mc.BG_RECORDS + slot], data[mc.BG_RECORDS + slot + 1] = 0x00, 0xC0
    for i, b in enumerate(record):
        data[0x28C000 + i] = b
    return FakeRom(data)


class BackgroundTests(unittest.TestCase):
    def test_slots_follow_day_night_and_modes(self):
        slots = mc.background_slots(background_rom(5, 3))
        self.assertEqual(sorted(slots), [0, 2, 0x98, 0xB4])
        self.assertEqual(len(slots[2]), mc.BG_COUNT)
        self.assertTrue(all(night for _, mode, night in slots[2]))

    def test_record_on_obj_lines_fails(self):
        self.assertEqual(mc.background_problems(background_rom(5, 3)), [])
        # 줄 5~8: 줄 8 은 CGRAM 128~(OBJ 팔레트 0)이라 무리 0 의 색을 덮는다
        self.assertEqual(len(mc.background_problems(background_rom(5, 4))), 4)
        self.assertEqual(len(mc.background_problems(background_rom(0, 1, colors=16))), 4)


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


@unittest.skipUnless((ROOT / 'rom' / 'dq5.sfc').is_file(), 'local source ROM not present')
class PaletteRomTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from dq5map import Rom, lorom
        cls.Rom, cls.lorom = Rom, staticmethod(lorom)
        cls.data = (ROOT / 'rom' / 'dq5.sfc').read_bytes()
        cls.dq5 = Rom(cls.data)

    def test_original_backgrounds_stay_below_obj_lines(self):
        self.assertEqual(mc.background_problems(self.dq5), [])
        # 22:8983 표 31 칸 바로 뒤는 22:89E5 의 첫 명령 PHP(08)다
        self.assertEqual(self.dq5.u8(mc.BG_INDEX + 2 * mc.BG_COUNT), 0x08)

    def test_background_on_obj_line_fails(self):
        at = 0x280000 | self.dq5.u16(mc.BG_RECORDS)
        data = bytearray(self.data)
        data[self.lorom(at) + 1] = mc.OBJ_LINE - 1
        problems = mc.background_problems(self.Rom(bytes(data)))
        self.assertTrue(problems and all(f'{at & 0xFFFF:04X}' in p for p in problems), problems)

    def test_original_monsters_use_their_own_colors(self):
        self.assertEqual(mc.color_problems(self.dq5), [])

    def test_fewer_record_colors_than_picture_fails(self):
        import dq5mongfx as M
        import dq5monwrite as W
        m = 0x02
        g, _ = M.monster(self.dq5, m)
        top = max(max(row) for row in W.picture_grid(self.dq5, g)[0])
        table, bank = M.record_table(self.dq5)
        data = bytearray(self.data)
        data[self.lorom(bank << 16 | self.dq5.u16(table + m * 2)) + 1] = top - 1
        self.assertTrue(any(p.startswith('02:') for p in mc.color_problems(self.Rom(bytes(data)))))


if __name__ == '__main__':
    unittest.main()
