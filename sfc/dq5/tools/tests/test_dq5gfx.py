"""그래픽 내보내기(dq5gfx): 타일·색 풀기, 물 타일 돌리기, 덤프 화면 그리기·맞추기, 맵 위 물체 해석기, 창 격자, 분류 폴더 쓰기."""
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dq5gfx as G  # noqa: E402
from dq5map import Rom, lorom, map_cgram  # noqa: E402

ROM = Path(__file__).resolve().parents[4] / 'rom' / 'dq5.sfc'
NO_ROM = '롬이 없음(rom/dq5.sfc)'


def rom_with(pieces, size=0x200000):
    data = bytearray(size)
    for at, raw in pieces:
        data[lorom(at):lorom(at) + len(raw)] = raw
    return Rom(data)


def png_size(path):
    with Image.open(path) as img:
        return img.size


def quiet(fn, *args, **kw):
    with redirect_stdout(io.StringIO()):
        return fn(*args, **kw)


class ColorTileTests(unittest.TestCase):
    def test_rgb_scales_five_bits_like_mesen(self):
        self.assertEqual(G.rgb(0x7FFF), (255, 255, 255))
        self.assertEqual(G.rgb(0x001F), (255, 0, 0))
        self.assertEqual(G.rgb(0x03E0), (0, 255, 0))
        self.assertEqual(G.rgb(0x0001), (8, 0, 0))
        self.assertEqual(G.cgram_colors(bytes([0x1F, 0x00, 0x00, 0x7C])), [(255, 0, 0), (0, 0, 255)])

    def test_planar_reads_four_planes(self):
        t = bytearray(32)
        t[0], t[1], t[16], t[17] = 0x80, 0x80, 0x80, 0x80  # 첫 줄 첫 점 = 15
        t[2 * 7] = 0x01                                       # 마지막 줄 마지막 점 = 1
        px = G.planar(bytes(t))
        self.assertEqual(px[0][0], 15)
        self.assertEqual(px[7][7], 1)
        self.assertEqual(sum(v for row in px for v in row), 16)

    def test_chr_2bpp_reads_two_planes(self):
        t = bytearray(16)
        t[0], t[1] = 0x80, 0x40
        px = G.chr_2bpp(bytes(t))
        self.assertEqual(px[0][:3], [1, 2, 0])

    def test_tile_image_flips_and_keeps_color_zero_transparent(self):
        px = [[0] * 8 for _ in range(8)]
        px[0][0] = 1
        colors = [(0, 0, 0), (10, 20, 30)]
        img = G.tile_image(px, colors)
        self.assertEqual(img.getpixel((0, 0)), (10, 20, 30, 255))
        self.assertEqual(img.getpixel((1, 0))[3], 0)
        self.assertEqual(G.tile_image(px, colors, flip_h=True).getpixel((7, 0)), (10, 20, 30, 255))
        self.assertEqual(G.tile_image(px, colors, flip_v=True).getpixel((0, 7)), (10, 20, 30, 255))

    def test_scaled_and_sheet_layout(self):
        img = Image.new('RGB', (3, 2), (9, 9, 9))
        self.assertIs(G.scaled(img, 1), img)
        self.assertEqual(G.scaled(img, 3).size, (9, 6))
        cells = [Image.new('RGB', (4, 4), (200, 0, 0)), None, Image.new('RGBA', (4, 4), (0, 200, 0, 255))]
        out = G.sheet(cells, 2, 4, 4, labels=['a', 'b', 'c'], label_h=10)
        self.assertEqual(out.size, (2 * 5 + 1, 2 * 15 + 1))
        self.assertEqual(out.getpixel((1, 11)), (200, 0, 0))
        self.assertEqual(out.getpixel((6, 11)), (32, 32, 40))  # 빈 칸은 바탕
        self.assertEqual(out.getpixel((1, 26)), (0, 200, 0))
        below = G.sheet(cells[:1], 1, 4, 4, labels=['a'], label_h=10, below=True, pad=0)
        self.assertEqual(below.getpixel((0, 0)), (200, 0, 0))


class WaterTests(unittest.TestCase):
    def test_rotate_pair_turns_sixteen_bits(self):
        a, b = bytes([0x80] + [0] * 31), bytes([0x01] + [0] * 31)
        ra, rb = G.rotate_pair(a, b, 1)
        self.assertEqual((ra[0], rb[0]), (0xC0, 0x00))  # 8001 → C000
        self.assertEqual(G.rotate_pair(a, b, 16), (a, b))
        self.assertEqual(G.rotate_pair(*G.rotate_pair(a, b, 5), -5), (a, b))

    def test_water_frames_cycle_back_to_source(self):
        src = bytes(range(128))
        for world in (0, 1, 2):
            frames = G.water_frames(src, world)
            self.assertEqual(len(frames), 16)
            self.assertEqual(frames[-1], src)
            self.assertEqual(len(set(frames)), 16)
        right, left = G.water_frames(src, 0)[0], G.water_frames(src, 1)[0]
        self.assertEqual(G.rotate_pair(right[:32], right[32:64], -2), G.rotate_pair(left[:32], left[32:64], 0))

    def test_world2_pushes_rows_up(self):
        src = bytearray(128)
        src[0:2] = b'\xAA\xBB'          # 타일 4 맨 윗줄(평면 0·1)
        src[0x40 + 14:0x40 + 16] = b'\x11\x22'  # 타일 20 맨 아랫줄
        f = G.water_frames(bytes(src), 2)[0]
        self.assertEqual(f[0x40 + 14:0x40 + 16], b'\xAA\xBB')
        self.assertEqual(f[0x40 + 12:0x40 + 14], b'\x11\x22')


def fake_dump(folder):
    """BG2 는 온통 색 1(빨강), BG1 은 칸 (2, 3) 하나만 색 2(초록). BG1 가로 스크롤 8."""
    vram = bytearray(0x10000)
    vram[0x2000:0x2000 + 32] = bytes([0xFF, 0] * 8 + [0] * 16)
    vram[0x4020:0x4040] = bytes([0, 0xFF] * 8 + [0] * 16)
    o = 0x800 + (3 * 32 + 2) * 2
    vram[o] = 1
    cg = bytearray(0x200)
    cg[0:2], cg[2:4], cg[4:6] = (0x7C00).to_bytes(2, 'little'), (0x001F).to_bytes(2, 'little'), (0x03E0).to_bytes(2, 'little')
    prefix = os.path.join(folder, 'f00001')
    Path(prefix + '.vram').write_bytes(vram)
    Path(prefix + '.cgram').write_bytes(cg)
    ppu = {'ppu.layers[1].tilemapAddress': 0, 'ppu.layers[1].chrAddress': 0x1000, 'ppu.layers[0].tilemapAddress': 0x400,
           'ppu.layers[0].chrAddress': 0x2000, 'ppu.layers[0].hscroll': 8, 'ppu.layers[0].vscroll': -512}
    lines = [f'{k}={v}' for k, v in ppu.items()]
    lines += [f'ppu.layers[{n}].double{d}=false' for n in (0, 1) for d in ('Width', 'Height')] + ['ppu.mode=one']
    Path(prefix + '.ppu.txt').write_text('\n'.join(lines) + '\n')
    return prefix, bytes(vram), bytes(cg)


class DumpTests(unittest.TestCase):
    def test_read_ppu_parses_numbers_and_words(self):
        with tempfile.TemporaryDirectory() as d:
            prefix, _, _ = fake_dump(d)
            ppu = G.read_ppu(prefix + '.ppu.txt')
        self.assertEqual(ppu['ppu.layers[0].vscroll'], -512)
        self.assertEqual(ppu['ppu.layers[1].chrAddress'], 0x1000)
        self.assertEqual(ppu['ppu.mode'], 'one')

    def test_bg_layer_sizes_and_bpp(self):
        with tempfile.TemporaryDirectory() as d:
            prefix, vram, cg = fake_dump(d)
            ppu = G.read_ppu(prefix + '.ppu.txt')
        bg2 = G.bg_layer(vram, cg, ppu, 1)
        self.assertEqual(bg2.size, (256, 256))
        self.assertEqual(bg2.getpixel((100, 100)), (255, 0, 0, 255))
        bg1 = G.bg_layer(vram, cg, ppu, 0, transparent=True)
        self.assertEqual(bg1.getpixel((16, 24)), (0, 255, 0, 255))
        self.assertEqual(bg1.getpixel((0, 0))[3], 0)
        ppu2 = dict(ppu, **{'ppu.layers[1].doubleWidth': 'true', 'ppu.layers[1].doubleHeight': 'true'})
        self.assertEqual(G.bg_layer(vram, cg, ppu2, 1).size, (512, 512))
        # 2bpp 로 보면 같은 타일 자리의 첫 두 평면만: 0xFF/0x00 → 색 1
        self.assertEqual(G.bg_layer(vram, cg, ppu, 1, bpp=2).getpixel((0, 0)), (255, 0, 0, 255))

    def test_dump_screen_overlays_bg1_and_scrolls(self):
        with tempfile.TemporaryDirectory() as d:
            prefix, _, _ = fake_dump(d)
            scr = G.dump_screen(prefix)
        self.assertEqual(scr.size, (256, 224))
        self.assertEqual(scr.getpixel((8, 24)), (0, 255, 0))
        self.assertEqual(scr.getpixel((16, 24)), (255, 0, 0))
        self.assertEqual(scr.getpixel((8, 32)), (255, 0, 0))

    def test_match_screen_finds_offset(self):
        # 8x8 칸마다 다른 색(맵처럼 칸 단위 무늬): 8점 걸음 거친 찾기 뒤 ±8 다듬기로 칸에 안 맞는 자리도 찾는다.
        full = Image.new('RGB', (64, 48))
        full.putdata([(x // 8 * 30 + 5, y // 8 * 40 + 5, (x // 8 + y // 8) % 2 * 200 + 20) for y in range(48) for x in range(64)])
        scr = Image.new('RGB', (256, 224), (0, 0, 0))
        scr.paste(full, (13, 5))
        x, y, hit, n = G.match_screen(full, scr)
        self.assertEqual((x, y), (-13, -5))
        self.assertEqual((hit, n), (64 * 48, 64 * 48))


def mini_rom(code, at=0x018000, extra=()):
    return rom_with([(at, bytes(code)), *extra])


class Mini65Tests(unittest.TestCase):
    def test_runs_loop_subroutine_and_cell_writes(self):
        w = 4
        code = [0xC2, 0x30,              # REP #$30
                0xA9, 0x34, 0x12,        # LDA #$1234
                0x85, 0x10,              # STA $10
                0xE2, 0x20,              # SEP #$20
                0xA2, 0x03, 0x00,        # LDX #$0003
                0x1A, 0xCA, 0xD0, 0xFC,  # INC A / DEX / BNE
                0x85, 0x12,              # STA $12
                0x20, 0x00, 0x90,        # JSR $9000
                0xA2, 0x01, 0x00,        # LDX #$0001
                0xA0, 0x02, 0x00,        # LDY #$0002
                0x22, 0x15, 0xFA, 0x25,  # JSL 25:FA15 → [$00] = 셀 (1, 2)
                0xA0, 0x05, 0x00,        # LDY #$0005
                0xA9, 0xAB,              # LDA #$AB
                0x97, 0x00,              # STA [$00],Y
                0x20, 0xED, 0xEF,        # JSR $EFED → 다음 줄
                0x97, 0x00,              # STA [$00],Y
                0x60]
        sub = [0xA9, 0x05, 0x0A, 0x85, 0x13, 0x60]  # LDA #5 / ASL / STA $13 / RTS
        rom = mini_rom(code, extra=[(0x019000, bytes(sub))])
        buf = bytearray(w * 4 * 8)
        m = G.Mini65(rom, buf, w, 0, 0)
        m.stack = ['top']
        m.run(0x018000)
        self.assertEqual(list(m.dp[0x10:0x14]), [0x34, 0x12, 0x37, 0x0A])
        self.assertEqual(buf[(2 * w + 1) * 8 + 5], 0xAB)
        self.assertEqual(buf[(3 * w + 1) * 8 + 5], 0xAB)
        self.assertEqual(sum(1 for b in buf if b), 2)

    def test_reads_cell_buffer_and_compares(self):
        code = [0xA9, 0x00, 0x85, 0x00, 0xA9, 0xC0, 0x85, 0x01, 0xA9, 0x7E, 0x85, 0x02,  # [$00] = 7E:C000
                0xA0, 0x03, 0xB7, 0x00,  # LDA [$00],Y
                0xC9, 0x42, 0xF0, 0x02,  # CMP #$42 / BEQ +2
                0xA9, 0xEE,              # (건너뜀)
                0x85, 0x20, 0x60]
        buf = bytearray(16)
        buf[3] = 0x42
        m = G.Mini65(mini_rom(code), buf, 2, 0, 0)
        m.stack = ['top']
        m.run(0x018000)
        self.assertEqual(m.dp[0x20], 0x42)
        self.assertEqual(m.rd(0x7EC003, 1), 0x42)
        self.assertEqual(m.rd(0x7EC000 + 100, 2), 0)  # 버퍼 밖은 0

    def test_ldx_bc_bd_reads_map_number(self):
        code = [0xA6, 0xBC, 0x86, 0x30, 0xA6, 0xBD, 0x86, 0x31, 0x60]
        m = G.Mini65(mini_rom(code), bytearray(8), 1, 0x12, 0x34)
        m.stack = ['top']
        m.run(0x018000)
        self.assertEqual((m.dp[0x30], m.dp[0x31]), (0x12, 0x34))

    def test_errors(self):
        for code, msg in (([0xDB], 'op DB'), ([0x22, 0x00, 0x80, 0x00], 'JSL 008000'), ([0x80, 0xFE], 'limit')):
            m = G.Mini65(mini_rom(code), bytearray(8), 1, 0, 0)
            m.stack = ['top']
            with self.assertRaisesRegex(RuntimeError, msg):
                m.run(0x018000, limit=50)

    def test_open_door_passes_position_and_kind(self):
        code = [0xA6, 0x0B, 0xA4, 0x0C, 0x22, 0x15, 0xFA, 0x25,  # X, Y = 물체 자리 → 셀 주소
                0x68, 0xA0, 0x05, 0x97, 0x00, 0x60]              # PLA(종류) / LDY #5 / STA [$00],Y
        rom = mini_rom(code, at=0x01F8AB)
        buf = bytearray(3 * 3 * 8)
        G.open_door(rom, buf, 3, 0, 0, 2, 1, 0x3E)
        self.assertEqual(buf[(1 * 3 + 2) * 8 + 5], 0x3E)


def window_rom_data(data):
    return patch('dq5text.window', return_value=(0x040000, bytes(data)))


class WindowGridTests(unittest.TestCase):
    def grid(self, data):
        with window_rom_data(data):
            return G.window_grid(None, 0)

    def test_rejects_short_small_or_hidden(self):
        self.assertIsNone(self.grid([0, 0, 5, 5, 0]))
        self.assertIsNone(self.grid([0, 0, 2, 5, 0, 0, 0xFE]))
        self.assertIsNone(self.grid([0x80, 0, 5, 5, 0, 0, 0xFE]))
        self.assertIsNone(self.grid([0, 0, 5, 5, 0x05, 0, 0, 0]))

    def test_list_window_with_dakuten(self):
        grid, x, y = self.grid([0x22, 0x03, 6, 4, 0x00, 0x01, 0xFE, 0x20, 0x21, 0xFF, 0xFE, 0x84, 0x22, 0xFF])
        self.assertEqual((x, y), (2, 3))
        self.assertEqual(grid[0], [0x08C, 0x08D, 0x08D, 0x08D, 0x08D, 0x48C])
        self.assertEqual(grid[1], [0x08E, 0x001, 0x084, 0x021, 0x001, 0x48E])
        self.assertEqual(grid[2], [0x08E, 0x001, 0x022, 0x001, 0x001, 0x48E])
        self.assertEqual(grid[3], [0x88C, 0x88D, 0x88D, 0x88D, 0x88D, 0xC8C])

    def test_dakuten_on_top_border_and_line(self):
        grid, _, _ = self.grid([0, 0, 5, 4, 0x00, 0x00, 0xFE, 0x83, 0x30, 0xFF])
        self.assertEqual(grid[0][2], 0x093)
        self.assertEqual(grid[1][2], 0x030)
        grid, _, _ = self.grid([0, 0, 5, 4, 0x00, 0x00, 0xFE, 0x84, 0xFF])
        self.assertEqual(grid[0][2], 0x084)  # 뒤 글자 없는 탁점은 위 칸에만

    def test_status_window_name_line_and_fields(self):
        grid, _, _ = self.grid([0, 0, 8, 6, 0xD0, 0, 0, 0, 0, 0x81, 0xB0, 0xFF])
        self.assertEqual(grid[1][1:5], list(G.SAMPLE_NAME))
        self.assertEqual(grid[2], [0x08F] + [0x090] * 6 + [0x48F])
        self.assertEqual(grid[3][1:4], [0x0B] * 3)  # 999 = 타일 0B 셋

    def test_text_window_name_slot_and_indent(self):
        grid, _, _ = self.grid([0, 0, 8, 4, 0x00, 0x20, 0xF3, 0xFF, 0x05])
        self.assertEqual(grid[1][3:7], [0x089] * 4)
        self.assertEqual(grid[2][1], 0x005)

    def test_line_longer_than_window_is_not_a_window(self):
        self.assertIsNone(self.grid([0, 0, 4, 4, 0x00, 0x00, 0xFE, 1, 2, 3, 4, 5, 0xFF]))


class SetCgramTests(unittest.TestCase):
    def test_backdrop_from_last_row_with_color(self):
        from dq5map import PALETTES, PALSET_LISTS
        pieces = [(PALSET_LISTS + 3 * 4, (0x8000).to_bytes(2, 'little')),
                  (PALSET_LISTS + 3 * 4 + 2, (0x8010).to_bytes(2, 'little')),
                  (0x108000, b''.join((r + 1).to_bytes(2, 'little') for r in range(7))),
                  (0x108010, b''.join((0x10 + r).to_bytes(2, 'little') for r in range(7)))]
        for r in range(7):
            pieces.append((PALETTES + (r + 1) * 32, bytes([r + 1]) * 32))
        pieces.append((PALETTES + 0x10 * 32, bytes(32)))  # 밤 쪽 첫 줄은 0번 색까지 0
        rom = rom_with(pieces)
        cg = G.set_cgram(rom, 3)
        self.assertEqual(cg[0x20:0x40], bytes([1]) * 32)
        self.assertEqual(cg[0xE0:0x100], bytes([7]) * 32)
        self.assertEqual(cg[0:2], bytes([7, 7]))  # 0번 색 = 0 이 아닌 가장 뒤 줄(7)의 0번 색
        night = G.set_cgram(rom, 3, alt=True)
        self.assertEqual(night[0x20:0x40], bytes(32))
        self.assertEqual(night[0:2], bytes(2))


class OutTests(unittest.TestCase):
    def test_save_add_finish_write_index_per_folder(self):
        with tempfile.TemporaryDirectory() as d:
            out = G.Out(d, 'abc123')
            img = Image.new('RGB', (5, 3))
            out.save(img, 'maps/a.png', 'maps', 'A', 'g', extra=1)
            out.save(img, 'gfx/blocks/maps/b.png', 'blocks', 'B')
            out.save(img, 'gfx/screens/c.png', 'screens', 'C')
            out.add('gfx/screens/c.gif', 'screens', 'C (GIF)')
            out.index['gfx/screens'] = {'custom': True}
            out.finish('명령 X')
            maps = json.loads(Path(d, 'maps/index.json').read_text())
            blocks = json.loads(Path(d, 'gfx/blocks/index.json').read_text())
            screens = json.loads(Path(d, 'gfx/screens/index.json').read_text())
            source = Path(d, 'maps/SOURCE.txt').read_text()
        self.assertEqual(maps, [{'cat': 'maps', 'group': 'g', 'title': 'A', 'path': 'a.png', 'w': 5, 'h': 3, 'extra': 1}])
        self.assertEqual(blocks[0]['path'], 'maps/b.png')
        self.assertEqual(screens, {'custom': True})
        self.assertIn('명령: 명령 X', source)
        self.assertIn('SHA-1 abc123', source)

    def test_source_text_without_git(self):
        with patch('subprocess.run', side_effect=subprocess.CalledProcessError(1, 'git')):
            self.assertIn('커밋: 알 수 없음', G.source_text('c', 's'))
        with patch('subprocess.run', side_effect=OSError):
            self.assertIn('커밋: 알 수 없음', G.source_text('c', 's'))

    def test_map_stem_names_only_low_groups(self):
        self.assertEqual(G.map_stem(0x02, 0x06, {0x02: '마을'}), '02-06-마을')
        self.assertEqual(G.map_stem(0x03, 0x00, {}), '03-00')
        self.assertEqual(G.map_stem(0x51, 0x50, {0x51: '마을'}), '51-50')

    def test_annotate_colors(self):
        base = Image.new('RGBA', (80, 80), (0, 0, 0, 255))
        marks = {'exits': [(1, 1)], 'npcs': [(0, 4, 4, 0, 0)], 'chests': [(0, 6, 1)], 'search': [(1, 8)],
                 'foot': [(5, 8)], 'doors': [(7, 6, 0x3E)]}
        img = G.annotate(base, marks)
        self.assertEqual(img.mode, 'RGB')
        self.assertEqual(img.getpixel((8, 8)), (0, 200, 255))
        self.assertEqual(img.getpixel((48, 15)), (255, 40, 40))
        self.assertEqual(img.getpixel((32, 47)), (255, 230, 0))
        self.assertEqual(img.getpixel((47, 47)), (255, 230, 0))
        self.assertEqual(img.getpixel((8, 71)), (255, 120, 200))
        self.assertEqual(img.getpixel((40, 71)), (255, 120, 200))
        self.assertEqual(img.getpixel((56, 55)), (255, 150, 0))
        self.assertEqual(img.getpixel((70, 30)), (0, 0, 0))


@unittest.skipUnless(ROM.exists(), NO_ROM)
class RomTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom = Rom(ROM.read_bytes())

    def test_map_ids_and_palette_overrides(self):
        ids = G.map_ids(self.rom)
        self.assertEqual(len(ids), 364)
        self.assertEqual(sum(1 for bc, _ in ids if bc >= 0x50), 18)
        self.assertEqual(len(set(ids)), len(ids))
        po = G.palette_overrides(self.rom)
        self.assertEqual(len(po), 6)
        self.assertEqual(po[0], (0x04, 0x00, 0x88, 0x40, 0x26))
        self.assertIsNone(po[1][1])

    def test_set_cgram_fills_bg_rows(self):
        cg = G.set_cgram(self.rom, 0x26)
        self.assertEqual(len(cg), 0x200)
        self.assertNotEqual(cg[0x20:0x100], bytes(0xE0))
        self.assertEqual(cg[0x100:], bytes(0x100))  # 세트는 BG 줄 1~7 만
        self.assertEqual(G.set_cgram(self.rom, 0x26, alt=True)[0x100:], bytes(0x100))

    def test_decode_map_and_flags(self):
        dec, w, h, buf, blocks = G.decode_map(self.rom, 0x02, 0x06)
        self.assertEqual(len(buf), w * h * 8)
        self.assertTrue(blocks)
        self.assertTrue(dec.doors)
        self.assertGreater(len(dec.common), 0x0B0 - 0x001)
        _, fw, fh, fbuf, _ = G.decode_map(self.rom, 0x02, 0x06, flags=True)
        self.assertEqual((fw, fh), (w, h))
        self.assertTrue(fbuf != buf)

    def test_common_tiles_slots(self):
        tiles = G.common_tiles(self.rom, 0x02, 0x06)
        self.assertEqual(min(tiles), 0x001)
        self.assertTrue(all(len(t) == 32 for t in tiles.values()))
        self.assertTrue({0x0AE + i for i in range(6)} <= set(tiles))
        other = G.common_tiles(self.rom, 0x53, 0x52)
        self.assertNotEqual(other[0x09E], tiles[0x09E])
        self.assertEqual(other[0x001], tiles[0x001])

    def test_door_entries_and_shapes(self):
        doors = G.door_entries(self.rom)
        self.assertEqual(len(doors), 113)
        self.assertTrue(all(len(e) == 5 and e[0] < 0x80 for v in doors.values() for e in v))
        for kind in (0x3E, 0x41, 0x43, 0x44, 0x3F, 0x46, 0x48):
            shape = G.door_shape(self.rom, kind)
            self.assertTrue(shape, f'{kind:02X}')
            self.assertTrue(all(0 <= dx < 4 for dx, _, _ in shape))
        _, w, h, buf, _ = G.decode_map(self.rom, 0x00, 0x00)
        closed, opened = bytearray(buf), bytearray(buf)
        placed = G.apply_doors(self.rom, 0x00, 0x00, closed, w, h, doors)
        self.assertEqual(placed, [(x, y, k) for x, y, k, _, _ in doors[(0, 0)]])
        G.apply_doors(self.rom, 0x00, 0x00, opened, w, h, doors, opened=True)
        self.assertTrue(closed != opened)
        self.assertEqual(G.apply_doors(self.rom, 0x7F, 0x7F, bytearray(buf), w, h, doors), [])

    def test_hook_clears(self):
        def cleared(m, flags):
            buf = bytearray(b'\xFF' * 0x4000)
            n = G.hook_clears(self.rom, *m, buf, flags)
            return n, sum(1 for b in buf if b != 0xFF)
        self.assertEqual(cleared((0x0D, 0x00), True), (20, 16))
        self.assertEqual(cleared((0x0D, 0x00), False), (0, 0))  # 플래그 분기 뒤에서만 지운다
        self.assertEqual(cleared((0x23, 0x00), False), (20, 16))
        self.assertEqual(G.hook_clears(self.rom, 0x02, 0x00, bytearray(8)), 0)

    def test_anim_override_kinds(self):
        self.assertEqual(G.anim_counters(self.rom, 0x17, 0x01), [])
        self.assertEqual(G.anim_counters(self.rom, 0x19, 0x00), list(range(0, 192, 8)))
        for m in ((0x1C, 0x00), (0x54, 0x50), (0x18, 0x00)):
            a, b = G.anim_override(self.rom, *m, 0), G.anim_override(self.rom, *m, 48)
            self.assertTrue(a)
            self.assertEqual(set(a), set(b))
            self.assertTrue(all(len(v) == 32 for v in a.values()))
            self.assertNotEqual(a, b, m)

    def test_draw_cells_override_changes_image(self):
        bc, bd = 0x18, 0x00
        dec, w, h, buf, _ = G.decode_map(self.rom, bc, bd)
        cg = map_cgram(self.rom, bc, bd)
        a = G.draw_cells(self.rom, dec, w, h, buf, cg)
        b = G.draw_cells(self.rom, dec, w, h, buf, cg, override=G.anim_override(self.rom, bc, bd, 72))
        self.assertEqual(a.size, (w * 8, h * 8))
        self.assertNotEqual(a.tobytes(), b.tobytes())

    def test_field_tables(self):
        sets = G.field_time_sets(self.rom)
        self.assertEqual(len(sets), 8)
        self.assertEqual(sum(len(los) for _, los in sets), 10)
        cg = G.field_cgram(self.rom, 0, sets[0][0])
        self.assertNotEqual(G.field_cgram(self.rom, 0, sets[0][0], wave=3)[4 * 32 + 2:4 * 32 + 8], cg[4 * 32 + 2:4 * 32 + 8])
        self.assertEqual(G.field_cgram(self.rom, 0, sets[0][0], wave=3)[5 * 32:], cg[5 * 32:])
        anim = G.field_anim_sets(self.rom)
        self.assertEqual((len(anim), len(anim[0]), len(anim[0][0])), (8, 6, 32))
        self.assertEqual(len(G.ui_tiles(self.rom)), 16 * (1 + G.UI_1BPP + G.UI_2BPP))
        self.assertTrue(all(b == 0xFF for b in G.ui_tiles(self.rom)[17:16 * (1 + G.UI_1BPP):2]))

    def test_world_screen_grid(self):
        grid = G.world_screen(self.rom)
        self.assertEqual((len(grid), len(grid[0])), (120, 128))
        self.assertTrue(all(0x20 <= v < 0x30 for row in grid for v in row))
        self.assertGreater(len({v for row in grid for v in row}), 3)

    def test_credits_rows_text(self):
        _, title = G.credits_rows(self.rom, 1)
        self.assertIn('DRAGON QUEST V', ' '.join(title))
        rows, staff = G.credits_rows(self.rom, 0)
        self.assertGreater(len(rows), 50)
        self.assertTrue(any('─' in t for t in staff))
        self.assertEqual(G.credits_image(self.rom, rows, [(0, 0, 0)] * 4).size, (256, len(rows) * 16))

    def test_effects(self):
        self.assertEqual(sum(1 for n in range(G.EFFECT_COUNT) if G.effect_lists(self.rom, n)), 51)
        _, obj = next(g for g in (G.effect_lists(self.rom, n) for n in range(G.EFFECT_COUNT)) if g and g[1])
        w, h, tiles = G.effect_cel(self.rom, obj[0], True)
        self.assertTrue(tiles)
        self.assertTrue(all(len(t) == 32 for _, _, t, _ in tiles))
        self.assertEqual(G.effect_image(self.rom, obj[0], True, [(255, 255, 255)]).size, (w * 8 + 8, h * 8))
        for n in (0x0D, 0x12, 0x00):
            self.assertTrue(all(len(c) for c in G.effect_colors(self.rom, n)))

    def test_the_end_and_title(self):
        rows = G.the_end_map(self.rom)
        self.assertEqual((len(rows), len(rows[0])), (4, 26))
        self.assertEqual(len(G.the_end_tiles(self.rom)), 41)
        self.assertEqual(G.title_screen(self.rom).size, (256, 224))
        logo = G.title_bitmap_map(self.rom, 'logo')
        self.assertEqual(len(logo), 8)
        tiles = [w & 0x3FF for row in logo for w in row if w]
        self.assertEqual(tiles, list(range(1, len(tiles) + 1)))
        self.assertEqual(sum(1 for row in logo for w in row if w >> 10 == 1), 12)
        self.assertEqual(len(G.title_castle_map(self.rom)), 32)

    def test_export_maps(self):
        maps = {(0x02, 0x06), (0x51, 0x50), (0x04, 0x00), (0x0D, 0x00)}
        with tempfile.TemporaryDirectory() as d:
            out = G.Out(d)
            quiet(G.export_maps, self.rom, out, maps)
            paths = {it['path'] for it in out.items}
            names = os.listdir(os.path.join(d, 'maps'))
            with Image.open(os.path.join(d, 'maps', next(n for n in names if n.startswith('51-50.')))) as day:
                size = day.size
        self.assertTrue(any(p.startswith('maps/04-00') and '-set26' in p for p in paths))
        self.assertTrue(any(p.startswith('maps/0D-00') and p.endswith('-flags.png') for p in paths))
        self.assertIn('maps/51-50-annot.png', paths)
        self.assertIn('gfx/blocks/maps/51-50.png', paths)
        it = next(i for i in out.items if i['path'] == 'maps/51-50.png')
        self.assertEqual(size, (it['w'], it['h']))
        self.assertEqual(it['size'], f'{size[0] // 8}x{size[1] // 8}')
        self.assertEqual({i['map'] for i in out.items}, {f'{a:02X}/{b:02X}' for a, b in maps})

    def test_export_field(self):
        with tempfile.TemporaryDirectory() as d:
            out = G.Out(d)
            quiet(G.export_field, self.rom, out)
            sizes = {it['path']: (it['w'], it['h']) for it in out.items}
        self.assertEqual(sizes['field/field0.png'], (4096, 4096))
        self.assertEqual(sizes['field/field1.png'], (2048, 2048))
        self.assertEqual(sizes['gfx/blocks/field-tiles.png'], (512, 256))
        self.assertIn('field/field0-night.png', sizes)
        self.assertIn('field/field2-annot.png', sizes)
        annot = next(it for it in out.items if it['path'] == 'field/field0-annot.png')
        self.assertTrue(annot['entrances'])

    def test_export_anim_field_parts(self):
        with tempfile.TemporaryDirectory() as d:
            out = G.Out(d)
            with patch.object(G, 'export_indoor_anim') as indoor:
                quiet(G.export_anim, self.rom, out)
            with Image.open(os.path.join(d, 'gfx/anim/field-water.gif')) as gif:
                gif_frames = gif.n_frames
        indoor.assert_called_once()
        frames = {it['path']: it.get('frames') for it in out.items}
        self.assertEqual(frames['gfx/anim/field-454.png'], 8)
        self.assertEqual(frames['gfx/anim/field-water.png'], 16)
        self.assertEqual(frames['gfx/anim/field-wave.png'], 10)
        self.assertEqual(gif_frames, 16)

    def test_export_indoor_anim_few_maps(self):
        import dq5anim
        few = [e for e in dq5anim.map_list(self.rom) if e[:2] in {(0x54, 0x50), (0x1E, 0x00), (0x19, 0x00)}]
        self.assertEqual(len(few), 3)
        with tempfile.TemporaryDirectory() as d:
            out = G.Out(d)
            with patch.object(dq5anim, 'map_list', return_value=few):
                quiet(G.export_indoor_anim, self.rom, out)
            paths = {it['path']: it for it in out.items}
        self.assertTrue(any(p.startswith('gfx/anim/maps/19-00') for p in paths))
        self.assertEqual(paths['gfx/anim/maps/54-50.gif']['frames'], 48)
        self.assertNotIn('gfx/anim/indoor-14.png', paths)
        for t in (2, 7, 13):
            self.assertIn(f'gfx/anim/indoor-{t:02d}.png', paths)

    def test_export_battlebg(self):
        with tempfile.TemporaryDirectory() as d:
            out = G.Out(d)
            quiet(G.export_battlebg, self.rom, out)
        self.assertEqual(len(out.items), 147)
        self.assertEqual({it['era'] for it in out.items}, {0, 1, 2})

    def test_main_exports_folders(self):
        only = 'chr,monsters,font,ui,worldmap,credits,windows,theend,battlewin,title,menus,effects'
        with tempfile.TemporaryDirectory() as d:
            with patch.object(sys, 'argv', ['dq5gfx.py', str(ROM), '--out', d, '--only', only]):
                self.assertEqual(quiet(G.main), 0)
            monsters = json.loads(Path(d, 'monsters/index.json').read_text())
            screens = json.loads(Path(d, 'gfx/screens/index.json').read_text())
            windows = json.loads(Path(d, 'gfx/screens/windows/index.json').read_text())
            source = Path(d, 'gfx/screens/SOURCE.txt').read_text()
            font = png_size(os.path.join(d, 'gfx/font.png'))
            chr13 = png_size(os.path.join(d, 'gfx/blocks/chr13-color.png'))
            effects = os.listdir(os.path.join(d, 'gfx/effects'))
            theend = png_size(os.path.join(d, 'gfx/screens/the-end.png'))
        self.assertEqual(len(monsters['monsters']), 236)
        self.assertEqual(monsters['monsters'][0xEA]['note'], G.MONSTER_NOTES[0xEA])
        paths = {it['path'] for it in screens}
        self.assertTrue({'window.png', 'world-map.png', 'world-map-1.png', 'title.png', 'menu-book.png',
                         'staff-roll.png', 'credits-font.png', 'the-end.png'} <= paths)
        self.assertEqual(len(windows), 98)  # gfx/ 아래 하위 폴더는 index.json 을 따로 둔다
        self.assertFalse(any(p.startswith('windows/') for p in paths))
        self.assertIn('SHA-1 ', source)
        self.assertEqual(font, (16 * 32, (0x3DB + 15) // 16 * 32))  # 글자 0x3DB 개, 16자씩 2배
        self.assertEqual(chr13, (512, 512))
        self.assertEqual(sum(1 for n in effects if n.endswith('.png')), 51)
        self.assertEqual(theend, (26 * 8, 32))

    def test_check_and_main_check(self):
        bc, bd = 0x02, 0x06
        dec, w, h, buf, _ = G.decode_map(self.rom, bc, bd)
        full = G.draw_cells(self.rom, dec, w, h, buf, map_cgram(self.rom, bc, bd))
        self.assertGreaterEqual(full.size, (272, 232))
        screen = full.crop((16, 8, 272, 232)).convert('RGB')
        with patch.object(G, 'dump_screen', return_value=screen):
            x, y, hit, n = G.check(self.rom, 'dump', bc, bd)
            self.assertEqual(hit, n)
            self.assertEqual(n, 256 * 224)
            self.assertEqual(full.crop((x, y, x + 256, y + 224)).convert('RGB').tobytes(), screen.tobytes())
            with patch.object(sys, 'argv', ['dq5gfx.py', str(ROM), '--check', 'dump', '02/06']):
                self.assertEqual(quiet(G.main), 0)
            with patch.object(sys, 'argv', ['dq5gfx.py', str(ROM), '--check', 'dump', '02/06', '--set', '26', '--night']):
                self.assertEqual(quiet(G.main), 1)


if __name__ == '__main__':
    unittest.main()
