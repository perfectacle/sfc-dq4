"""전투 몬스터 그림(dq5mongfx): 조각·타일 압축 풀기, 색 번호 격자와 그림, 화면·OBJ·WRAM 견주기, VRAM 자리·NMI 전송,
무리 배치, 명령줄. 합성 롬에 손으로 싼 그림 하나를 두고 본다."""
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import dq5mongfx as M  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402
from test_dq5spc import run_main  # noqa: E402

RAW = bytes(range(1, 33))                          # 모드 0F: 네 평면 그대로
TWO = bytes([0xF0, 0x0F] * 8)                      # 모드 03: 평면 0·1 만
MASKED_DATA = bytes([0xAA, 0x55])                  # 모드 81: 평면 0, 마스크 0x81 → 줄 0·7 만 자료, 나머지 0
FILLED = bytes([0xFF, 0x01, 0x80, 0x11, 0x22])     # 모드 C5: 채움 FF, 평면 0·2 마스크 01·80
SMALL = bytes([0x81] * 32)                         # 작은 조각
COLORS = [0x001F, 0x03E0, 0x7C00]


def tiles():
    t_two = bytearray(32)
    t_two[:16] = TWO
    t_masked = bytearray(32)
    t_masked[0], t_masked[14] = 0xAA, 0x55
    t_filled = bytearray(32)
    for row in range(8):
        t_filled[row * 2] = 0xFF
        t_filled[16 + row * 2] = 0xFF
    t_filled[14] = 0x11
    t_filled[16] = 0x22
    return [RAW, bytes(t_two), bytes(t_masked), bytes(t_filled)]


def picture(flag=0x80 | 0x20 | 0x05):
    """3x2 칸: (0,0) 16x16, (2,0) 8x8, (2,1) 은 조각 1 의 좌우 반전 복사."""
    head = bytes([flag, 0xFE, 0x03, 0x10, 0x08, 0x21])
    return (head + bytes([0b10100100]) + bytes([0x20, 0x40])
            + bytes([0x0F]) + RAW + bytes([0x03]) + TWO + bytes([0x81, 0x81]) + MASKED_DATA
            + bytes([0xC5, 0xFF, 0x01, 0x80, 0x11, 0x22]) + bytes([0x0F]) + SMALL + bytes([0x01]))


def mongfx_rom(head_flag=0x80 | 0x20 | 0x05):
    d = bytearray(0x200000)
    rec = 0x27F000
    for m in range(M.TABLE_SIZE):
        d[lorom(M.RECORDS) + m * 2:lorom(M.RECORDS) + m * 2 + 2] = (rec & 0xFFFF).to_bytes(2, 'little')
    body = bytes([0x00, len(COLORS)]) + b''.join(c.to_bytes(2, 'little') for c in COLORS)
    d[lorom(rec):lorom(rec) + len(body)] = body
    pic = 0x25A000
    d[lorom(M.HEADS[0][1]):lorom(M.HEADS[0][1]) + 2] = (pic & 0xFFFF).to_bytes(2, 'little')
    raw = picture(head_flag)
    d[lorom(pic):lorom(pic) + len(raw)] = raw
    return d


class DecodeTest(unittest.TestCase):
    def setUp(self):
        self.rom = Rom(mongfx_rom())
        self.d = M.decode(self.rom, 0)

    def test_record_and_heads(self):
        self.assertEqual(M.record_table(self.rom), (M.RECORDS, 0x27))
        self.assertEqual(M.monster(self.rom, 5), (0, COLORS))
        self.assertEqual(M.head(self.rom, 0), 0x25A000)
        d = bytearray(self.rom.d)
        d[lorom(0x268F99) + 2:lorom(0x268F99) + 4] = b'\x34\x92'
        self.assertEqual(M.head(Rom(d), 0x2B), 0x269234)

    def test_moved_record_table(self):
        d = bytearray(self.rom.d)
        o, b = lorom(M.RECORD_READ), lorom(M.RECORD_BANK)
        d[o:o + 4] = bytes([0xBF, 0x00, 0x90, 0x31])
        d[b:b + 2] = bytes([0xA9, 0x31])
        self.assertEqual(M.record_table(Rom(d)), (0x319000, 0x31))

    def test_pieces_and_tiles(self):
        d = self.d
        self.assertEqual((d['w'], d['h'], d['head']), (3, 2, 0x25A000))
        self.assertEqual(d['end'], 0x25A000 + len(picture()))
        (x0, y0, big0, t0, f0), (x1, y1, big1, t1, f1), (x2, y2, big2, t2, f2) = d['pieces']
        self.assertEqual((x0, y0, big0, f0), (0, 0, True, False))
        self.assertEqual(t0, tiles())
        self.assertEqual((x1, y1, big1, t1, f1), (16, 0, False, [SMALL], False))
        self.assertEqual((x2, y2, big2, f2), (16, 8, False, True))
        self.assertIs(t2, t1)

    def test_mirror_one_pixel_left_when_bit2_clear(self):
        raw = bytearray(picture())
        raw[8] = 0x80                            # 셋째 조각 니블 8: 반전, 1픽셀 왼쪽
        d = bytearray(mongfx_rom())
        d[lorom(0x25A000):lorom(0x25A000) + len(raw)] = raw
        self.assertEqual(M.decode(Rom(d), 0)['pieces'][2][:3], (15, 8, False))

    def test_pixels_and_index_image(self):
        self.assertEqual(M.pixels(SMALL)[0], [15, 0, 0, 0, 0, 0, 0, 15])
        img = M.index_image(self.d)
        self.assertEqual((len(img[0]), len(img)), (25, 16))
        self.assertEqual(img[0][17], 15)          # 작은 조각 왼쪽 끝(여백 1)
        self.assertEqual(img[8][17], 15)          # 반전 복사도 양 끝이 같다
        self.assertEqual(img[0][1:9], M.pixels(RAW)[0])
        self.assertEqual(img[8][9:17], M.pixels(tiles()[3])[0])

    def test_rgb(self):
        self.assertEqual(M.rgb(0x001F), (255, 0, 0))
        self.assertEqual(M.rgb(0x7FFF), (255, 255, 255))
        self.assertEqual(M.rgb(0x0421), (8, 8, 8))

    def test_render_maps_colors_and_scales(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'm.png'
            img = M.render(self.rom, 0, str(path), scale=2)
            self.assertEqual(img.size, (50, 32))
            saved = Image.open(path)
            self.assertEqual(saved.size, (50, 32))
        img = M.render(self.rom, 0, None)
        grid = M.index_image(self.d)
        for y, row in enumerate(grid):
            for x, v in enumerate(row):
                want = (0, 0, 0, 0) if not v else (255, 0, 255, 255) if v > 3 else M.rgb(COLORS[v - 1]) + (255,)
                self.assertEqual(img.getpixel((x, y)), want)


class HeaderTest(unittest.TestCase):
    def test_parse(self):
        h = M.parse_header([0x80 | 0x40 | 0x05, 0xFE, 0x03, 0x10, 0x08, 0xF2])
        self.assertEqual(h, {'float': True, 'raise': 2, 'shadow': 5, 'shadow_dx': -2, 'shadow_dy': 3, 'hit_x': 0x10,
                             'hit_y': 8, 'w': 0x13, 'h': 3})
        self.assertEqual(M.header(Rom(mongfx_rom()), 0)['w'], 3)


class VramTest(unittest.TestCase):
    def setUp(self):
        self.d = M.decode(Rom(mongfx_rom()), 0)

    def test_slots_and_obj_tiles(self):
        self.assertEqual(M.slot_count(self.d), 2)
        self.assertEqual(M.obj_tiles(self.d, 0), [0, 1, 16, 17, 2])
        self.assertEqual(M.obj_tiles(self.d, 7), [14, 15, 30, 31, 32])
        self.assertEqual(M.transfer_runs(self.d, 0), [[0, 3], [16, 2]])

    def test_small_pieces_share_a_slot(self):
        small = {'pieces': [(0, 0, False, [], False)] * 5 + [(0, 0, True, [], False)]}
        self.assertEqual(M.obj_tiles(small, 0), [0, 1, 16, 17, 2, 4, 5, 20, 21])
        self.assertEqual(M.slot_count(small), 1 + 2)

    def test_nmi_tiles(self):
        self.assertEqual(M.nmi_tiles(self.d, 0), 5)
        per_tile = 32 * 8 * M.LINE / (M.LINE - M.REFRESH)
        margin = M.NMI_DEADLINE - (M.NMI_FIRST_DMA + 2.5 * per_tile)
        self.assertEqual(M.nmi_tiles(self.d, 0, margin), 2)
        margin = M.NMI_DEADLINE - (M.NMI_FIRST_DMA + 3 * per_tile + M.NMI_ENTRY_GAP / 2)
        self.assertEqual(M.nmi_tiles(self.d, 0, margin), 3)

    def test_band_counts(self):
        self.assertEqual(M.band_counts(self.d), [3, 3])


def hd(w=3, h=2, float_=False, raise_=0):
    return {'float': float_, 'raise': raise_, 'w': w, 'h': h}


class PlaceTest(unittest.TestCase):
    def test_rows_and_y(self):
        kept, pieces, bands = M.place([(1, 2, 0, hd(), 3, [3, 3]), (2, 1, 1, hd(raise_=1), 3, [3, 3]),
                                       (3, 1, 0x80, hd(h=8), 3, [1] * 8), (M.LOWERED, 1, 0, hd(), 3, [3, 3])])
        self.assertEqual([(m, j, row, y, k) for m, j, _, row, y, k in kept],
                         [(1, 2, 0, 0x90, 2), (2, 1, 1, 0x70, 1), (3, 1, 2, 0x40, 1), (M.LOWERED, 1, 0, 0x92, 1)])
        self.assertEqual(pieces, 15)
        self.assertEqual(bands[(0x90 >> 3) - 7], 3 * 3)

    def test_width_and_piece_limits(self):
        kept, _, _ = M.place([(1, 9, 0, hd(w=6), 1, [1])])
        self.assertEqual(kept[0][1], 4)
        kept, pieces, _ = M.place([(1, 9, 1, hd(w=1), 30, [1])])
        self.assertEqual((kept[0][1], pieces), (3, 90))

    def test_band_limit_and_negative_rows(self):
        kept, _, bands = M.place([(1, 5, 0, hd(w=1), 1, [10])])
        self.assertEqual(kept[0][1], 2)
        self.assertEqual(max(bands), 20)
        kept, _, bands = M.place([(1, 1, 0x80, hd(h=8, raise_=3), 1, [5] * 8)])
        self.assertEqual(kept[0][1], 1)
        self.assertEqual(sum(bands), 5 * 6)       # y = 0x28 라 위 두 줄은 음수 줄이어서 세지 않는다

    def test_layout_centres_rows(self):
        rom = Rom(mongfx_rom(head_flag=0x05))
        self.assertEqual(M.layout(rom, [(0, 2, 0), (1, 1, 0)]),
                         [(0, 88, 0x90), (0, 112, 0x90), (1, 144, 0x90)])
        self.assertEqual(M.layout(rom, [(0, 1, 1)]), [(0, 116, 0x78)])


def oam_for(ox, oy):
    """그림을 (ox, oy) 에 OBJ 로 둔 OAM·VRAM 덤프. 반전 복사는 h 반전 OBJ."""
    d = M.decode(Rom(mongfx_rom()), 0)
    vram = bytearray(0x10000)
    oam = bytearray(544)
    for k in range(128):
        oam[k * 4 + 1] = 0xF0
    for t, data in zip(M.obj_tiles(d, 0), [*d['pieces'][0][3], SMALL]):
        vram[0xC000 + t * 32:0xC000 + t * 32 + 32] = data
    entries = [(ox + 1, oy - 1, 0, 0x00, 2), (ox + 17, oy - 1, 2, 0x00, 0), (ox + 17, oy + 7, 2, 0x40, 0)]
    for k, (x, y, t, attr, size) in enumerate(entries):
        oam[k * 4:k * 4 + 4] = bytes([x & 0xFF, y, t, attr])
        oam[512 + (k >> 2)] |= (size | (x >> 8 & 1)) << ((k & 3) * 2)
    return bytes(oam), bytes(vram)


class MatchTest(unittest.TestCase):
    def setUp(self):
        self.rom = Rom(mongfx_rom())

    def test_oam_grid_draws_flipped_objects(self):
        oam, vram = oam_for(40, 30)
        grid = M.oam_grid(oam, vram)
        img = M.index_image(M.decode(self.rom, 0))
        for y, row in enumerate(img):
            for x, v in enumerate(row):
                if v:
                    self.assertEqual(grid[30 + y][40 + x], v)

    def test_oam_grid_vertical_flip_and_offscreen(self):
        oam = bytearray(544)
        for k in range(128):
            oam[k * 4 + 1] = 0xF0
        oam[0:4] = bytes([0xFC, 10, 0, 0x80])
        oam[512] = 0x01                           # x 9비트 → -4
        vram = bytearray(0x10000)
        vram[0xC000:0xC020] = SMALL
        grid = M.oam_grid(bytes(oam), bytes(vram))
        self.assertEqual(grid[11][0:4], [0, 0, 0, 15])
        self.assertEqual(grid[18][3], 15)

    def test_match_oam_finds_the_picture(self):
        oam, vram = oam_for(40, 30)
        hit, total, ox, oy = M.match_oam(self.rom, 0, oam, vram)
        self.assertEqual((hit, ox, oy), (total, 40, 30))

    def test_match_screen(self):
        spr = M.render(self.rom, 0, None)
        shot = Image.new('RGB', (64, 40), (1, 2, 3))
        shot.paste(spr, (20, 10), spr)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 's.png'
            shot.save(path)
            hit, total, ox, oy = M.match_screen(self.rom, 0, str(path))
        self.assertEqual((hit, ox, oy), (total, 20, 10))

    def test_compare_wram(self):
        wram = bytearray(0x20000)
        for k, t in enumerate(tiles() + [SMALL]):
            wram[0x4000 + k * 64:0x4000 + k * 64 + 32] = t
        self.assertEqual(M.compare_wram(self.rom, 0, bytes(wram)), (5, 5))
        wram[0x4000:0x4020] = bytes(32)
        self.assertEqual(M.compare_wram(self.rom, 0, bytes(wram)), (4, 5))


class MainTest(unittest.TestCase):
    def test_main_modes(self):
        rom = Rom(mongfx_rom())
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            path = tmp / 'r.sfc'
            path.write_bytes(rom.d)
            code, out = run_main(M, [str(path), '--layout', '0:2,1:1:80'])
            self.assertEqual(code, 0)
            self.assertEqual(out.splitlines(), ['00 x=88 y=72 3x2칸', '00 x=112 y=72 3x2칸', '01 x=144 y=72 3x2칸'])
            code, out = run_main(M, [str(path)])
            lines = out.splitlines()
            self.assertEqual(len(lines), M.COUNT)
            self.assertEqual(lines[0], f'00 그림 00 머리 25A000-{0x25A000 + len(picture()):06X} 3x2칸 조각 3(16x16 1, 반전 1) 색 3')
            oam, vram = oam_for(40, 30)
            (tmp / 'oam.bin').write_bytes(oam)
            (tmp / 'vram.bin').write_bytes(vram)
            (tmp / 'wram.bin').write_bytes(bytes(0x20000))
            spr = M.render(rom, 0, None)
            shot = Image.new('RGB', (40, 24))
            shot.paste(spr, (5, 3), spr)
            shot.save(tmp / 'shot.png')
            code, out = run_main(M, [str(path), '00', '--png', str(tmp / 'one.png'), '--scale', '3',
                                     '--compare', str(tmp / 'wram.bin'), '--shot', str(tmp / 'shot.png'),
                                     '--oam', str(tmp / 'oam.bin'), str(tmp / 'vram.bin')])
            self.assertIn('버퍼 0/5', out)
            self.assertIn('@(5,3)', out)
            self.assertIn('@(40,30)', out)
            self.assertEqual(Image.open(tmp / 'one.png').size, (75, 48))
            run_main(M, [str(path), '00', '01', '--png', str(tmp / 'many')])
            self.assertEqual(sorted(p.name for p in (tmp / 'many').iterdir()), ['00.png', '01.png'])


if __name__ == '__main__':
    unittest.main()
