import contextlib
import io
import json
import tempfile
import unittest
import unittest.mock
from collections import Counter
from pathlib import Path

from PIL import Image

import dq4people as P
from dq4chapter1 import lorom
from w65816 import Cpu

TABLE = 0x2586D0
# 실제 표만큼 긴 줄 목록. 맵 그룹을 보는 줄을 앞에 둔다(hook_entries 와 같은 차례)
ENTRIES = [(0x2B, 0x3C, 0x70), (0x2E, 0x3C, 0x70), (0x08, 0x3C, 0x63), (0x17, 0x3C, 0x09), (0x09, 0x3C, 0x22),
           (0x1F, 0x3C, 0x2D), (0x2B, None, 0x71), (0x2E, None, 0x71), (0x5B, None, 0x20), (0x14, None, 0x04),
           (0x04, None, 0x3C), (0x9B, None, 0x39)]


def run(picture, group, p=0x30):
    rom = bytearray(0x400000)
    at = P.cpu(P.HOOK_AT)
    code = P.hook(ENTRIES)
    rom[lorom(at):lorom(at) + len(code)] = code
    for g in range(0x100):
        rom[lorom(TABLE + g)] = g ^ 0x80
    cpu = Cpu(bytes(rom), bytearray(0x20000))
    cpu.wram[0xBC] = group
    cpu.x, cpu.p = picture, p
    cpu.jsl(at)
    return cpu


class HookTests(unittest.TestCase):
    def test_every_entry_picks_its_set(self):
        for picture, group, s in ENTRIES:
            self.assertEqual(run(picture, 0x3C if group else 0x36).a & 0xFF, s, f'{picture:02X}')

    def test_prologue_only_entries_fall_back_elsewhere(self):
        self.assertEqual(run(0x08, 0x36).a & 0xFF, 0x08 ^ 0x80)
        self.assertEqual(run(0x2B, 0x36).a & 0xFF, 0x71)

    def test_other_pictures_read_the_table(self):
        for picture in (0x00, 0x06, 0x2C, 0xA8):
            self.assertEqual(run(picture, 0x3C).a & 0xFF, picture ^ 0x80)

    def test_flag_entry_wins_only_when_the_flag_is_on(self):
        entries = [(0x2B, None, (0x78, 0x10), 0x83)] + ENTRIES
        for flag, want in ((0x10, 0x83), (0x00, 0x71)):
            rom = bytearray(0x400000)
            at = P.cpu(P.HOOK_AT)
            code = P.hook(entries)
            rom[lorom(at):lorom(at) + len(code)] = code
            cpu = Cpu(bytes(rom), bytearray(0x20000))
            cpu.wram[0xBC], cpu.wram[0x2190 + 0x78] = 0x3D, flag
            cpu.x, cpu.p = 0x2B, 0x30
            cpu.jsl(at)
            self.assertEqual(cpu.a & 0xFF, want)

    def test_register_widths_come_back(self):
        # 03:D202 는 X 16비트(상위 0)로 부를 수 있다. PLP 가 폭을 되돌리고 X 는 그대로여야 한다
        cpu = run(0x9B, 0x36, p=0x20)
        self.assertEqual(cpu.p & 0x30, 0x20)
        self.assertEqual(cpu.x, 0x9B)


PAL_TABLE, SWAP_AT = 0x3DEA55, 0x3DEA19


def swap_rom():
    """인물 훅·그림 표·세트 팔레트 표·그림 바꾸기 팔레트 루틴을 넣고 03:D202·03:D24D 를 JSL 로 돌린 롬."""
    import dq5objpalette
    rom = bytearray(0x400000)
    at = P.cpu(P.HOOK_AT)
    code = P.hook(ENTRIES)
    rom[lorom(at):lorom(at) + len(code)] = code
    for g in range(0x100):
        rom[lorom(TABLE + g)] = g ^ 0x80
        rom[lorom(PAL_TABLE + g)] = 0xFF
    rom[lorom(PAL_TABLE + 0x71)], rom[lorom(PAL_TABLE + 0x20)] = 6, 5
    routine = dq5objpalette.swap_routine(PAL_TABLE)
    rom[lorom(SWAP_AT):lorom(SWAP_AT) + len(routine)] = routine
    rom[lorom(0x03D202):lorom(0x03D202) + 4] = bytes((0x22, at & 0xFF, at >> 8 & 0xFF, at >> 16))
    rom[lorom(P.SWAP_SITE):lorom(P.SWAP_SITE) + 4] = bytes((0x22, SWAP_AT & 0xFF, SWAP_AT >> 8 & 0xFF, SWAP_AT >> 16))
    return rom


def swap_run(rom, picture, group=0x36):
    cpu = Cpu(bytes(rom), bytearray(0x20000))
    cpu.wram[0xBC], cpu.wram[0x1EC0] = group, picture
    cpu.x, cpu.p = 0x80C0, 0x20
    cpu.jsl(SWAP_AT)
    return cpu


class SwapTests(unittest.TestCase):
    def test_hooked_picture_site_breaks_the_plain_routine(self):
        # 03:D202 가 JSL 이면 원래 루틴은 훅 코드 바이트를 세트로 읽는다
        self.assertNotEqual(swap_run(swap_rom(), 0x2B).wram[0x08], 6 * 2)

    def test_patched_routine_takes_the_hook_set(self):
        rom = swap_rom()
        write = P.swap_patch(bytes(rom))['writes'][0]
        head = bytes.fromhex(write['hex'])
        rom[lorom(SWAP_AT):lorom(SWAP_AT) + len(head)] = head
        for picture, want in ((0x2B, 6), (0x5B, 5)):
            cpu = swap_run(rom, picture)
            self.assertEqual(cpu.wram[0x08], want * 2, f'{picture:02X}')
            self.assertEqual((cpu.x, cpu.y, cpu.p & 0x30), (0x80C0, 2, 0x20))

    def test_hook_patch_widens_the_reload_bank_mask(self):
        rom = bytearray(0x400000)
        for site in P.HOOK_SITES:
            rom[lorom(P.cpu(site)):lorom(P.cpu(site)) + 4] = P.LOAD_SET
        rom[lorom(P.BANK_MASK_SITE):lorom(P.BANK_MASK_SITE) + 2] = b'\x29\x0f'
        rom[lorom(P.FIELD_MATH_SITE):lorom(P.FIELD_MATH_SITE) + 2] = b'\xa9\x50'
        with unittest.mock.patch.object(P, 'hook_entries', return_value=[]):
            writes = P.hook_patch(bytes(rom))['writes']
        self.assertIn({'at': '03:D2C7', 'hex': '29 3f', 'orig': '29 0f',
                       'note': '일행 그림 다시 싣기의 타일 자료 뱅크 6비트'}, writes)

    def test_hook_patch_turns_off_field_obj_color_math(self):
        # 장 주인공·동료는 OBJ 팔레트 5~7 이라, 필드의 OBJ 반 더하기가 남으면 BG 와 반씩 섞여 보인다
        rom = bytearray(0x400000)
        for site in P.HOOK_SITES:
            rom[lorom(P.cpu(site)):lorom(P.cpu(site)) + 4] = P.LOAD_SET
        rom[lorom(P.BANK_MASK_SITE):lorom(P.BANK_MASK_SITE) + 2] = b'\x29\x0f'
        rom[lorom(P.FIELD_MATH_SITE):lorom(P.FIELD_MATH_SITE) + 2] = b'\xa9\x50'
        with unittest.mock.patch.object(P, 'hook_entries', return_value=[]):
            writes = P.hook_patch(bytes(rom))['writes']
        self.assertEqual([(w['hex'], w['orig']) for w in writes if w['at'] == '2B:82F7'], [('a9 00', 'a9 50')])


def body(color=(200, 30, 30, 255)):
    c = Image.new('RGBA', (16, 24))
    for y in range(P.BOTTOM - 17, P.BOTTOM):
        for x in range(3, 13):
            c.putpixel((x, y), (60, 90, 120, 255) if y < P.BOTTOM - 5 else color)
    return c


class SheetTests(unittest.TestCase):
    def test_overlap_sheet_keeps_head_and_bodies(self):
        cells = {name: [body(), body((30, 200, 30, 255))] for name, _ in P.ROWS8}
        pal = [(60, 90, 120), (200, 30, 30), (30, 200, 30)]
        im = P.index_image(cells, pal, 'overlap')
        self.assertEqual(im.size, (48, 64))
        # 몸 열은 프레임의 8~23행이라 몸 0 과 몸 1 의 아랫줄(발) 색이 다르다
        self.assertEqual(im.getpixel((16 + 5, 16 - 3)), 2)
        self.assertEqual(im.getpixel((32 + 5, 16 - 3)), 3)

    def test_four_row_sheet_faces_right_on_row_one(self):
        sheet = Image.new('RGBA', (128, 128))
        for row in range(4):
            for y in range(row * 32 + 4, row * 32 + 28):
                for x in range(4, 12):
                    sheet.putpixel((x, y), (row * 60, 0, 0, 255))
        with tempfile.TemporaryDirectory() as d:
            sheet.save(Path(d) / 's.png')
            out = P.frames(Path(d) / 's.png', 'legs')
        self.assertEqual(out['right'][0].getpixel((4, 12))[0], 60)
        self.assertEqual(out['left'][0].getpixel((4, 12))[0], 180)

    def test_shrink_keeps_a_dark_eye(self):
        f = Image.new('RGBA', (28, 28), (230, 180, 140, 255))
        for y in (10, 11):
            f.putpixel((9, y), (0, 0, 0, 255))
        s = P.shrink(f)
        self.assertIn((0, 0, 0, 255), list(s.get_flattened_data()))

    def test_outline_darkens_only_the_edge(self):
        c = Image.new('RGBA', (16, 24))
        for y in range(10, 20):
            for x in range(4, 12):
                c.putpixel((x, y), (10, 10, 10, 255) if (x, y) == (7, 15) else (60, 180, 40, 255))
        P.outline(c)
        self.assertEqual(c.getpixel((4, 12)), (10, 10, 10, 255))
        self.assertEqual(c.getpixel((6, 14)), (60, 180, 40, 255))
        self.assertEqual(c.getpixel((3, 12))[3], 0)

    def test_place_keeps_earlier_waves_when_a_later_person_joins(self):
        a = P.Person((0x10,), None, 'x', 'a')
        b = P.Person((0x11,), None, 'x', 'b')
        late = P.Person((0x12,), None, 'x', 'late', wave=1, weight=P.KEY_WEIGHT)
        hists = {a: Counter({(200, 30, 30): 50, (20, 20, 20): 10}), b: Counter({(40, 40, 220): 50, (20, 20, 20): 10}),
                 late: Counter({(210, 60, 20): 80, (30, 200, 30): 40})}
        where = {a: {0x36, 0x46}, b: {0x37}, late: {0x36, 0x46}}
        before, was = P.place([a, b], hists, {a: {0x36}, b: {0x37}})
        after, board = P.place([a, b, late], hists, where)
        for p in (a, b):
            self.assertEqual(after[p], before[p])
        # 뒤 차례 인물이 서지 않는 그룹의 줄 색은 그대로다
        self.assertEqual(board[(0x37, after[b][0])], was[(0x37, before[b][0])])
        # 첫 차례 뒤에 생긴 그룹에도 앞 차례 인물의 줄이 실린다
        self.assertIn((0x46, after[a][0]), board)
        line, slots = after[late]
        self.assertEqual(set(slots), set(hists[late]))

    def test_place_keeps_one_slot_per_color_and_tunes_each_group(self):
        a = P.Person((0x10,), None, 'x', 'a')
        b = P.Person((0x11,), None, 'x', 'b')
        hists = {a: Counter({(200, 30, 30): 50, (20, 20, 20): 10}), b: Counter({(220, 40, 40): 50, (20, 20, 20): 10})}
        placed, board = P.place([a, b], hists, {a: {0x36}, b: {0x37}})
        for p, g in ((a, 0x36), (b, 0x37)):
            line, mapping = placed[p]
            for c, k in mapping.items():
                self.assertEqual(board[(g, line)][k], c)

    def test_where_adds_groups_that_use_the_spare_picture(self):
        elder = P.Person((0x1F,), 0x3C, 'x', 'elder', spare=0x9C)
        scholar = P.Person((0x1F,), None, 'x', 'scholar')
        out = P.where([elder, scholar], {0x9C: {0x36}, 0x1F: {0x3C, 0x45}})
        self.assertEqual(out[elder], {0x3C, 0x36})
        self.assertEqual(out[scholar], {0x45})

    def test_shade_edge_darkens_a_light_rim_with_a_deeper_shade_of_the_same_hue(self):
        light, deep, other = (230, 120, 120, 255), (150, 60, 60, 255), (40, 60, 160, 255)
        c = Image.new('RGBA', (16, 24))
        for y in range(8, 20):
            for x in range(4, 12):
                c.putpixel((x, y), light)
        c.putpixel((7, 12), deep)
        c.putpixel((8, 12), other)
        P.shade_edge(c)
        self.assertEqual(c.getpixel((4, 12)), deep)                  # 옆 가장자리
        self.assertEqual(c.getpixel((7, 8)), deep)                   # 윗 가장자리
        self.assertEqual(c.getpixel((6, 14)), light)                 # 안쪽
        self.assertEqual(c.getpixel((7, 19)), light)                 # 발 아랫줄은 땅에 붙는다
        self.assertEqual(c.getpixel((3, 12))[3], 0)

    def test_shade_edge_leaves_dark_rims_thin_lines_and_cells_beside_an_eye(self):
        light, deep, dark = (230, 120, 120, 255), (150, 60, 60, 255), (70, 30, 30, 255)
        c = Image.new('RGBA', (16, 24))
        for y in range(8, 20):
            for x in range(4, 12):
                c.putpixel((x, y), dark if x == 11 else light)
        c.putpixel((7, 12), deep)
        for y in range(2, 8):
            c.putpixel((6, y), light)                                # 한 칸 굵기의 창
        c.putpixel((5, 12), P.INK + (255,))
        P.shade_edge(c)
        self.assertEqual(c.getpixel((11, 12)), dark)
        self.assertEqual(c.getpixel((6, 4)), light)
        self.assertEqual(c.getpixel((4, 12)), light)
        self.assertEqual(c.getpixel((4, 14)), deep)

    def test_shade_edge_keeps_a_rim_without_a_deeper_shade_in_the_picture(self):
        light = (230, 120, 120, 255)
        c = Image.new('RGBA', (16, 24))
        for y in range(8, 20):
            for x in range(4, 12):
                c.putpixel((x, y), (40, 60, 160, 255) if (x, y) == (7, 12) else light)
        P.shade_edge(c)
        self.assertEqual(c.getpixel((4, 12)), light)

    def test_pack_backtracks_when_largest_first_fragments(self):
        bins = P.pack([('a', 6), ('b', 5), ('c', 5)], [10, 6])
        self.assertEqual(sorted(sorted(b) for b in bins), [['a'], ['b', 'c']])

    def test_reduce_keeps_the_most_used_colors(self):
        hist = Counter({(k * 10, 0, 0): 100 - k for k in range(20)})
        pal = P.reduce(hist)
        self.assertEqual(len(pal), 15)
        self.assertIn((0, 0, 0), pal)


SKIN, WHITE, DARK = (230, 170, 130, 255), (250, 250, 250, 255), (20, 20, 20, 255)


def face_frame(eyes=((8, 10), (13, 10)), whites=None, height=32):
    """24 폭 NDS 프레임: 살색 얼굴에 흰자 옆 1x2 눈동자. eyes 는 (x, 윗점 y)."""
    f = Image.new('RGBA', (24, height))
    for y in range(4, 24):
        for x in range(4, 20):
            f.putpixel((x, y), SKIN)
    for x, y in eyes:
        for yy in (y, y + 1):
            f.putpixel((x, yy), DARK)
    for x, y in (whites if whites is not None else [(x + d, y + k) for x, y in eyes for d in (-1, 1) for k in (0, 1)]):
        f.putpixel((x, y), WHITE)
    return f


class ColorTests(unittest.TestCase):
    def test_lab_lightness_runs_from_black_to_white(self):
        self.assertAlmostEqual(P.lab((0, 0, 0))[0], 0, places=3)
        self.assertAlmostEqual(P.lab((255, 255, 255))[0], 100, places=1)
        self.assertLess(P.lab((60, 60, 60))[0], P.lab((200, 200, 200))[0])

    def test_white_is_light_and_grey_but_skin_is_the_face(self):
        self.assertTrue(P.is_white((250, 250, 250)))
        self.assertFalse(P.is_white((250, 200, 200)))
        self.assertFalse(P.is_white((100, 100, 100)))
        self.assertTrue(P.is_face((230, 170, 130)))
        self.assertFalse(P.is_face((250, 250, 250)))
        self.assertFalse(P.is_face((20, 20, 20)))
        self.assertFalse(P.is_face((130, 170, 230)))

    def test_histogram_counts_opaque_pixels_over_every_cell(self):
        a, b = Image.new('RGBA', (2, 2), (1, 2, 3, 255)), Image.new('RGBA', (2, 2))
        b.putpixel((0, 0), (9, 9, 9, 255))
        self.assertEqual(P.histogram({'down': [a, b], 'up': [b, b]}), Counter({(1, 2, 3): 4, (9, 9, 9): 3}))

    def test_cost_is_the_weighted_distance_to_the_nearest_palette_colour(self):
        hist = Counter({(0, 0, 0): 3, (255, 255, 255): 2})
        self.assertEqual(P.cost(hist, [(0, 0, 0), (255, 255, 255)]), 0)
        self.assertAlmostEqual(P.cost(hist, [(0, 0, 0)]), 2 * P.lab((255, 255, 255))[0], places=3)

    def test_reduce_merges_the_least_used_of_the_closest_pair(self):
        hist = Counter({(0, 0, 0): 50, (4, 4, 4): 5, (255, 255, 255): 40})
        self.assertEqual(sorted(P.reduce(hist, 2)), [(0, 0, 0), (255, 255, 255)])
        self.assertEqual(sorted(P.reduce(hist, 5)), sorted(hist))

    def test_lines_put_each_person_on_the_line_that_grows_least(self):
        main = P.Person((1,), None, 's', 'main', main=True)
        extra = P.Person((2,), None, 's', 'extra')
        fixed = P.Person((3,), None, 's', 'fixed', palette=7)
        hists = {main: Counter({(200, 30, 30): 10}), extra: Counter({(30, 30, 200): 30}), fixed: Counter({(1, 1, 1): 1})}
        assign, shared = P.lines([extra, main, fixed], hists)
        # 두 사람의 색이 합쳐도 15색 안이라 늘어나는 거리가 0 이고, 비어 있는 줄과 비겨 첫 줄에 함께 든다
        self.assertEqual(assign[main], P.SHARED_LINES[0])
        self.assertEqual(assign[extra], P.SHARED_LINES[0])
        self.assertNotIn(fixed, assign)
        self.assertEqual(list(shared), [P.SHARED_LINES[0]])
        self.assertEqual(sorted(shared[P.SHARED_LINES[0]]), [(30, 30, 200), (200, 30, 30)])


class EyeTests(unittest.TestCase):
    def test_front_face_gives_the_closest_pair_at_the_same_height(self):
        eyes = P.find_eyes(face_frame())
        self.assertEqual(eyes, [(8, 10.5, DARK[:3]), (13, 10.5, DARK[:3])])

    def test_side_face_gives_the_eye_with_the_most_white_around_it(self):
        whites = [(7, 10), (7, 11), (9, 10), (9, 11), (12, 10), (12, 11)]
        self.assertEqual(P.find_eyes(face_frame(whites=whites), side=True), [(8, 10.5, DARK[:3])])

    def test_no_eyes_without_white_beside_the_pupil(self):
        self.assertEqual(P.find_eyes(face_frame(whites=[])), [])
        self.assertEqual(P.find_eyes(face_frame(whites=[]), side=True), [])

    def test_a_pupil_run_that_is_not_two_dots_tall_is_ignored(self):
        f = face_frame()
        f.putpixel((8, 12), DARK)
        self.assertEqual([e[0] for e in P.find_eyes(f)], [])

    def test_a_pupil_without_skin_below_is_not_an_eye(self):
        f = face_frame()
        for x in (8, 13):
            f.putpixel((x, 12), (0, 0, 0, 0))
        self.assertEqual(P.find_eyes(f), [])

    def test_eyes_too_far_apart_do_not_pair(self):
        self.assertEqual(P.find_eyes(face_frame(eyes=((6, 10), (14, 10)))), [])

    def test_sharpen_draws_one_by_two_ink_dots_at_the_scaled_eye_spots(self):
        f = face_frame()
        s = Image.new('RGBA', (19, 25), SKIN)
        ink = (5, 5, 5, 255)
        s.putpixel((0, 24), ink)
        stray = (7, 9)
        s.putpixel(stray, WHITE)
        P.sharpen_eyes(f, s, 'down')
        # x = int((8 + .5) * 19 / 24) = 6, int((13 + .5) * 19 / 24) = 10; y = int(10.5 * 25 / 32) = 8
        for spot in ((6, 8), (6, 9), (10, 8), (10, 9)):
            self.assertEqual(s.getpixel(spot), ink)
        self.assertEqual(s.getpixel(stray), SKIN)

    def test_back_view_and_frames_without_eyes_stay_as_they_are(self):
        s = Image.new('RGBA', (19, 25), SKIN)
        before = list(s.get_flattened_data())
        P.sharpen_eyes(face_frame(), s, 'up')
        P.sharpen_eyes(face_frame(whites=[]), s, 'down')
        self.assertEqual(list(s.get_flattened_data()), before)


def nds_sheet(path, blobs=2, height=256, top=4, bottom=28):
    """행마다 폭 8·높이 24(top~bottom) 의 덩어리를 blobs 개. 덩어리 색의 R 은 (행 번호 + 1) * 20 + 덩어리 번호."""
    sheet = Image.new('RGBA', (128, height))
    for row in range(height // 32):
        for k in range(blobs):
            for y in range(row * 32 + top, row * 32 + bottom):
                for x in range(4 + 16 * k, 12 + 16 * k):
                    sheet.putpixel((x, y), ((row + 1) * 20 + k, 100, 100, 255))
    sheet.save(path)


def face_sheet(path):
    """8줄 시트의 줄마다 face_frame 얼굴 하나. 옆모습 줄은 눈이 하나다."""
    sheet = Image.new('RGBA', (128, 256))
    sides = {row for name, row in P.ROWS8 if name in ('left', 'right')}
    for row in range(8):
        sheet.paste(face_frame(eyes=((8, 10),)) if row in sides else face_frame(), (0, row * 32))
    sheet.save(path)


def cells_of(image, color):
    return {(x, y) for y in range(image.height) for x in range(image.width) if image.getpixel((x, y)) == color}


class FramesTests(unittest.TestCase):
    def test_walking_pictures_keep_the_second_blob_only_when_asked(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 's.png'
            nds_sheet(path)
            legs, walk = P.frames(path, 'legs'), P.frames(path, 'frames')
        self.assertEqual(sorted(legs), ['down', 'left', 'right', 'up'])
        # 8줄 시트: down 은 4번째 줄, up 은 0번째 줄
        self.assertEqual(legs['down'][0].getpixel((0, 0))[0], 100)
        self.assertEqual(legs['up'][0].getpixel((0, 0))[0], 20)
        self.assertEqual(list(legs['down'][0].get_flattened_data()), list(legs['down'][1].get_flattened_data()))
        self.assertEqual((walk['down'][0].getpixel((0, 0))[0], walk['down'][1].getpixel((0, 0))[0]), (100, 101))
        self.assertEqual(walk['right'][1].size, (8, 24))

    def test_single_blob_sheet_repeats_the_first_frame(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 's.png'
            nds_sheet(path, blobs=1)
            walk = P.frames(path, 'frames')
        self.assertEqual(list(walk['left'][0].get_flattened_data()), list(walk['left'][1].get_flattened_data()))

    def rgb(self, sheet=nds_sheet, **kw):
        person = P.Person((1,), None, 'h900', 'x', **kw)
        with tempfile.TemporaryDirectory() as d:
            assets = Path(d)
            (assets / P.FIELD).mkdir(parents=True)
            sheet(assets / P.FIELD / 'h900.png')
            return P.rgb_frames(person, assets)

    def test_people_keep_the_nds_scale_and_stand_on_the_last_row(self):
        out = self.rgb()
        self.assertEqual(sorted(out), ['down', 'left', 'right', 'up'])
        for cells in out.values():
            for cell in cells:
                self.assertEqual(cell.size, (16, 24))
                # 8x24 → 6x19: 가로 5~10, 발이 맨 아랫줄(23행)
                self.assertEqual(cell.getbbox(), (5, 5, 11, 24))

    def test_people_taller_than_the_box_shrink_to_all_24_rows(self):
        def sheet(path):
            im = Image.new('RGBA', (128, 256))
            for row in range(8):
                im.paste((100, 100, 100, 255), (4, row * 32, 20, row * 32 + 32))
            im.save(path)
        for cells in self.rgb(sheet).values():
            # 16x32 → 12x24(배율 0.75). NDS 배율 그대로면 13x25 라 머리 한 줄이 잘린다
            self.assertEqual(cells[0].getbbox(), (2, 0, 14, 24))

    def test_people_get_a_shaded_rim(self):
        light, deep = (230, 120, 120, 255), (150, 60, 60, 255)

        def sheet(path):
            im = Image.new('RGBA', (128, 256))
            for row in range(8):
                im.paste(light, (4, row * 32 + 4, 12, row * 32 + 28))
                im.paste(deep, (7, row * 32 + 12, 9, row * 32 + 20))
            im.save(path)
        person = P.Person((1,), None, 'h900', 'x')
        with tempfile.TemporaryDirectory() as d:
            assets = Path(d)
            (assets / P.FIELD).mkdir(parents=True)
            sheet(assets / P.FIELD / 'h900.png')
            shaded, plain = P.rgb_frames(person, assets), P.rgb_frames(person, assets, outlined=False)
        for name in shaded:
            for cell in shaded[name]:
                self.assertEqual(cell.getpixel((5, 12)), deep, name)
                self.assertEqual(cell.getpixel((6, 8)), light, name)
            self.assertEqual(plain[name][0].getpixel((5, 12)), light, name)

    def test_walking_pictures_still_stand_on_row_21(self):
        out = self.rgb(anim='frames')
        # 8x24 → 6x19: 위는 22 - 19 = 3행
        self.assertEqual(out['left'][0].getbbox(), (5, P.BOTTOM - 19, 11, P.BOTTOM))
        self.assertEqual(out['left'][1].getbbox(), (5, P.BOTTOM - 19, 11, P.BOTTOM))

    def test_second_step_takes_the_third_nds_frame_from_step_top_down(self):
        out = self.rgb(lambda path: nds_sheet(path, blobs=3))
        for name, row in P.ROWS8:
            first, second = out[name]
            red = (row + 1) * 20
            self.assertEqual({p[0] for p in first.get_flattened_data() if p[3]}, {red}, name)
            # 머리·몸통 타일을 두 장이 함께 쓰려면 16행 위가 같아야 한다
            upper, lower = second.crop((0, 0, 16, 16)), second.crop((0, 16, 16, 24))
            self.assertEqual(list(upper.get_flattened_data()), list(first.crop((0, 0, 16, 16)).get_flattened_data()), name)
            self.assertEqual({p[0] for p in lower.get_flattened_data() if p[3]}, {red + 2}, name)

    def test_people_with_one_nds_frame_repeat_it(self):
        out = self.rgb()
        self.assertEqual(list(out['down'][0].get_flattened_data()), list(out['down'][1].get_flattened_data()))

    def test_touch_sets_ink_white_or_a_copied_cell_on_both_steps(self):
        out = self.rgb(touch={'down': [(6, 10, 'ink'), (7, 10, 'white'), (0, 0, (8, 12))]})
        for cell in out['down']:
            self.assertEqual(cell.getpixel((6, 10)), P.INK + (255,))
            self.assertEqual(cell.getpixel((7, 10)), P.WHITE + (255,))
            self.assertEqual(cell.getpixel((0, 0)), (100, 100, 100, 255))
        for name in ('left', 'right', 'up'):
            self.assertEqual(out[name][0].getpixel((0, 0))[3], 0, name)
            self.assertNotIn(P.INK + (255,), list(out[name][0].get_flattened_data()), name)

    def test_copy_makes_one_side_the_mirror_of_the_other(self):
        out = self.rgb(copy=('left', 'right'), touch={'left': [(5, 10, 'ink')]})
        for left, right in zip(out['left'], out['right']):
            self.assertEqual(left.getpixel((5, 10)), P.INK + (255,))
            self.assertEqual(list(right.get_flattened_data()),
                             list(left.transpose(Image.Transpose.FLIP_LEFT_RIGHT).get_flattened_data()))
        plain = self.rgb()
        self.assertNotEqual(list(plain['right'][0].get_flattened_data()),
                            list(plain['left'][0].transpose(Image.Transpose.FLIP_LEFT_RIGHT).get_flattened_data()))

    def test_people_get_ink_eyes_with_whites_outside_in_front_and_behind_on_the_side(self):
        out = self.rgb(face_sheet)
        ink, white = P.INK + (255,), P.WHITE + (255,)
        for name, beside in (('down', (-1, 1)), ('left', (1,)), ('right', (-1,))):
            cell = out[name][0]
            eyes = sorted({x for x, y in cells_of(cell, ink)})
            rows = sorted({y for x, y in cells_of(cell, ink)})
            self.assertEqual(len(eyes), len(beside), name)
            self.assertEqual(len(rows), 2, name)
            self.assertEqual(cells_of(cell, white), {(x + d, y) for x, d in zip(eyes, beside) for y in rows}, name)
        self.assertEqual(cells_of(out['up'][0], ink), set())

    def test_whites_option_leaves_the_sclera_of_those_views_to_touch(self):
        white = P.WHITE + (255,)
        for face in (False, True):
            out = self.rgb(face_sheet, whites=('down',), face=face)
            self.assertEqual(cells_of(out['down'][0], white), set(), face)
            self.assertEqual(len(cells_of(out['down'][0], P.INK + (255,))), 4, face)
            self.assertEqual(len(cells_of(out['left'][0], white)), 2, face)
            self.assertEqual(len(cells_of(self.rgb(face_sheet, face=face)['down'][0], white)), 4, face)

    def test_shrink_leaves_transparent_cells_empty(self):
        f = Image.new('RGBA', (28, 28))
        for y in range(14, 28):
            for x in range(28):
                f.putpixel((x, y), (200, 100, 50, 255))
        s = P.shrink(f)
        self.assertEqual(s.size, (22, 22))
        self.assertEqual(s.getpixel((10, 2))[3], 0)
        self.assertEqual(s.getpixel((10, 20)), (200, 100, 50, 255))

    def test_shrink_scales_both_sides_by_22_over_28(self):
        wide = Image.new('RGBA', (30, 40), (9, 9, 9, 255))
        shrunk = P.shrink(wide)
        self.assertEqual(shrunk.size, (round(30 * P.SCALE), round(40 * P.SCALE)))
        self.assertEqual(shrunk.getpixel((0, 0)), (9, 9, 9, 255))

    def test_outline_option_darkens_the_silhouette_edge_of_walking_pictures(self):
        # outline 은 사람이 아닌 그림(걸음 두 장을 NDS 그대로 쓰는 것)에만 듣는다. 사람은 shade_edge 가 맡는다
        person = P.Person((1,), None, 'h901', 'x', anim='frames', outline=True)
        with tempfile.TemporaryDirectory() as d:
            assets = Path(d)
            (assets / P.FIELD).mkdir(parents=True)
            sheet = Image.new('RGBA', (128, 256))
            for row in range(8):
                for y in range(row * 32 + 4, row * 32 + 28):
                    for x in range(4, 12):
                        sheet.putpixel((x, y), (200, 200, 200, 255) if 6 <= x <= 9 else (20, 20, 20, 255))
            sheet.save(assets / P.FIELD / 'h901.png')
            out = P.rgb_frames(person, assets)
        cell = out['right'][0]
        self.assertEqual(cell.getpixel((5, 10))[:3], (20, 20, 20))
        self.assertEqual(cell.getpixel((7, 3))[:3], (20, 20, 20))
        self.assertEqual(cell.getpixel((7, 10))[:3], (200, 200, 200))

    def test_outline_option_does_nothing_for_people(self):
        def sheet(path):
            im = Image.new('RGBA', (128, 256))
            for row in range(8):
                for y in range(row * 32 + 4, row * 32 + 28):
                    for x in range(4, 12):
                        im.putpixel((x, y), (200, 200, 200, 255))
            im.save(path)
        plain, outlined = self.rgb(sheet), self.rgb(sheet, outline=True)
        for name in plain:
            self.assertEqual(list(outlined[name][0].get_flattened_data()), list(plain[name][0].get_flattened_data()), name)


class SideStepTests(unittest.TestCase):
    def test_mirror_sides_flips_the_right_cells_for_the_left(self):
        a = Image.new('RGBA', (16, 24))
        a.putpixel((0, 0), (1, 2, 3, 255))
        cells = {'right': [a, a], 'left': []}
        P.mirror_sides(cells)
        self.assertEqual(cells['left'][0].getpixel((15, 0)), (1, 2, 3, 255))
        self.assertEqual(cells['left'][0].getpixel((0, 0))[3], 0)

    def test_still_repeats_the_first_cell_as_a_copy(self):
        a, b = Image.new('RGBA', (2, 2), (1, 1, 1, 255)), Image.new('RGBA', (2, 2), (2, 2, 2, 255))
        cells = {'up': [a, b]}
        P.still(cells, ('up',))
        self.assertEqual(cells['up'][1].getpixel((0, 0)), (1, 1, 1, 255))
        self.assertIsNot(cells['up'][1], cells['up'][0])

    def test_degrade_steps_come_in_the_stated_order(self):
        self.assertEqual([n for n, _ in P.DEGRADE], ['왼쪽=오른쪽 반전', '위 걸음 멈춤', '앞 걸음 멈춤', '모든 걸음 멈춤'])


class IndexImageTests(unittest.TestCase):
    def cells(self, c0=(60, 90, 120, 255), c1=(200, 30, 30, 255)):
        def cell(c):
            im = Image.new('RGBA', (16, 24))
            im.putpixel((2, 3), c)
            return im
        return {name: [cell(c0), cell(c1)] for name, _ in P.ROWS8}

    def test_simple_layout_puts_the_two_walk_cells_side_by_side(self):
        pal = {(60, 90, 120): 0, (200, 30, 30): 1}
        im = P.index_image(self.cells(), pal, 'simple')
        self.assertEqual(im.size, (32, 96))
        # 줄 r 의 칸은 y = 24 r, 걸음 1 은 x + 16. 색 번호는 칸 번호 + 1
        self.assertEqual((im.getpixel((2, 3)), im.getpixel((18, 3))), (1, 2))
        self.assertEqual((im.getpixel((2, 24 * 3 + 3)), im.getpixel((0, 0))), (1, 0))
        self.assertEqual(im.getpalette()[:9], [0, 0, 0, 60, 90, 120, 200, 30, 30])

    def test_list_palette_takes_the_nearest_colour(self):
        pal = [(0, 0, 0), (250, 250, 250)]
        im = P.index_image(self.cells((10, 10, 10, 255), (240, 240, 240, 255)), pal, 'simple')
        self.assertEqual((im.getpixel((2, 3)), im.getpixel((18, 3))), (1, 2))

    def test_overlap_layout_takes_head_from_first_cell_and_bodies_from_row_eight(self):
        cells = self.cells()
        for name, _ in P.ROWS8:
            cells[name][1].putpixel((4, 10), (200, 30, 30, 255))
        im = P.index_image(cells, {(60, 90, 120): 0, (200, 30, 30): 1}, 'overlap')
        self.assertEqual(im.size, (48, 64))
        self.assertEqual(im.getpixel((2, 3)), 1)                      # 머리
        self.assertEqual(im.getpixel((32 + 4, 10 - 8)), 2)           # 몸 1 은 프레임 8행부터


class HookEntryTests(unittest.TestCase):
    def test_entries_list_flag_leaders_first_then_grouped_people_then_ungrouped(self):
        fake = lambda person, rom: (0x40 + P.PEOPLE.index(person), 'simple', 10)  # noqa: E731
        with unittest.mock.patch.object(P, 'target', fake):
            entries = P.hook_entries(None)
        leaders = [p for p in P.PEOPLE if p.flag is not None and p.leader]
        self.assertEqual([p.flag for p in leaders], [P.CHAPTER2, P.CHAPTER3])
        n = 2 * len(leaders)
        for k, p in enumerate(leaders):
            for j in range(2):
                self.assertEqual(entries[2 * k + j], (P.LEADER_PICTURES[j], None, p.flag, 0x40 + P.PEOPLE.index(p)))
        frog = P.PEOPLE.index(next(p for p in P.PEOPLE if p.role == '개구리'))
        grouped = [e for e in entries[n:] if e[1] is not None]
        loose = [e for e in entries[n:] if e[1] is None]
        self.assertIn((0x50, P.PROLOGUE, None, 0x40 + frog), grouped)
        self.assertEqual(entries[n:], grouped + loose)
        wanted = sum(len(p.pictures) for p in P.PEOPLE
                     if (p.new_set is not None or p.spare is not None) and p.pictures != (p.spare,))
        self.assertEqual(len(entries), n + wanted)

    def test_hook_patch_refuses_a_site_that_is_not_the_table_read(self):
        with unittest.mock.patch.object(P, 'hook_entries', return_value=[]):
            with self.assertRaisesRegex(SystemExit, r'1F:CF45: LDA \$2586D0,X'):
                P.hook_patch(bytes(0x400000))

    def test_hook_patch_refuses_other_bank_masks_and_color_math(self):
        rom = bytearray(0x400000)
        for site in P.HOOK_SITES:
            rom[lorom(P.cpu(site)):lorom(P.cpu(site)) + 4] = P.LOAD_SET
        with unittest.mock.patch.object(P, 'hook_entries', return_value=[]):
            with self.assertRaisesRegex(SystemExit, 'AND #\\$0F'):
                P.hook_patch(bytes(rom))
            rom[lorom(P.BANK_MASK_SITE):lorom(P.BANK_MASK_SITE) + 2] = b'\x29\x0f'
            with self.assertRaisesRegex(SystemExit, 'LDA #\\$50'):
                P.hook_patch(bytes(rom))

    def test_hook_patch_lists_every_site_and_the_brey_picture(self):
        rom = bytearray(0x400000)
        for site in P.HOOK_SITES:
            rom[lorom(P.cpu(site)):lorom(P.cpu(site)) + 4] = P.LOAD_SET
        rom[lorom(P.BANK_MASK_SITE):lorom(P.BANK_MASK_SITE) + 2] = b'\x29\x0f'
        rom[lorom(P.FIELD_MATH_SITE):lorom(P.FIELD_MATH_SITE) + 2] = b'\xa9\x50'
        brey = P.cpu(P.COMPANION_PICTURES) + 5
        rom[lorom(brey)] = 0x11
        with unittest.mock.patch.object(P, 'hook_entries', return_value=[(0x50, None, 0x44)]):
            doc = P.hook_patch(bytes(rom))
        self.assertEqual((doc['format'], doc['name']), ('dq5patch/1', 'people-hook'))
        at = P.cpu(P.HOOK_AT)
        jsl = bytes((0x22, at & 0xFF, at >> 8 & 0xFF, at >> 16)).hex(' ')
        by_at = {w['at']: w for w in doc['writes']}
        self.assertEqual(by_at[P.HOOK_AT]['hex'], P.hook([(0x50, None, 0x44)]).hex(' '))
        for site in P.HOOK_SITES:
            self.assertEqual((by_at[site]['hex'], by_at[site]['orig']), (jsl, P.LOAD_SET.hex(' ')))
        self.assertEqual((by_at['05:D9DA']['hex'], by_at['05:D9DA']['orig']), (f'{P.BREY_PICTURE:02x}', '11'))

    def test_swap_patch_refuses_other_routines(self):
        rom = swap_rom()
        rom[lorom(P.SWAP_SITE)] = 0xAF
        with self.assertRaisesRegex(SystemExit, '세트 팔레트 훅'):
            P.swap_patch(bytes(rom))
        rom = swap_rom()
        rom[lorom(SWAP_AT)] ^= 0xFF
        with self.assertRaisesRegex(SystemExit, 'swap_routine'):
            P.swap_patch(bytes(rom))


class TargetTests(unittest.TestCase):
    def test_leader_takes_its_new_set_with_the_smaller_original_tile_count(self):
        with unittest.mock.patch.object(P.S, 'gfx_set', lambda rom, g: g + 1), \
                unittest.mock.patch.object(P.S, 'set_record', lambda rom, s: {'tiles': 10 * s}):
            lead = P.Person(P.LEADER_PICTURES, None, 's', 'lead', main=True, new_set=0x70)
            self.assertEqual(P.target(lead, None), (0x70, 'simple', 440))

    def test_others_use_the_spare_picture_set_and_its_layout(self):
        sets = {0x93: 0x85, 0x20: 0x10}
        with unittest.mock.patch.object(P.S, 'gfx_set', lambda rom, g: sets[g]), \
                unittest.mock.patch.object(P.S, 'set_record', lambda rom, s: {'tiles': s}):
            frog = P.Person((0x50,), None, 's', 'frog', spare=0x93)
            dog = P.Person((0x20,), None, 's', 'dog')
            self.assertEqual(P.target(frog, None), (0x85, 'overlap', 0x85))
            self.assertEqual(P.target(dog, None), (0x10, 'simple', 0x10))

    def test_tiles_count_distinct_tiles_of_a_sheet(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'a.png'
            blank = Image.new('P', (32, 96), 0)
            blank.putpalette([0] * 768)
            blank.save(path)
            self.assertEqual(P.tiles(path, 'simple'), 1)
            marked = blank.copy()
            marked.putpixel((0, 0), 3)
            marked.save(path)
            self.assertEqual(P.tiles(path, 'simple'), 2)


class UsageTests(unittest.TestCase):
    def test_groups_come_from_names_and_override_maps_limited_to_dq4_groups(self):
        doc = {'overrides': [{'list': 7, 'map': '37/01'}, {'list': 7, 'map': '02/01'}],
               'entries': [{'name': '36/00', 'list': 0, 'fields': {'gfx': 5}, 'day': {'gfx': 6}},
                           {'name': 'list7', 'list': 7, 'fields': {'gfx': 5}, 'night': {'gfx': 9}},
                           {'name': '02/00', 'list': 1, 'fields': {'gfx': 8}}]}
        with unittest.mock.patch.object(P.dq5npcrecord, 'dump', lambda base: doc):
            out = P.usage(b'rom')
        self.assertEqual(out, {5: {0x36, 0x37}, 6: {0x36}, 9: {0x37}})

    def test_chapter_groups_list_the_groups_with_a_map_of_that_chapter(self):
        import dq4groupbuild
        links = {0x38: [{'chapter': 1}, {'chapter': 2}], 0x36: [{'chapter': 1}], 0x40: [{'chapter': 3}]}
        with unittest.mock.patch.dict(dq4groupbuild.LINKS, links, clear=True):
            self.assertEqual(P.chapter_groups(1), [0x36, 0x38])
            self.assertEqual(P.chapter_groups(3), [0x40])
            self.assertEqual(P.chapter_groups(9), [])


class RecolorTests(unittest.TestCase):
    def test_recolor_moves_a_colour_before_the_touches(self):
        # 치마의 빨강이 노랑으로 옮겨지고 원래 색은 남지 않는다
        maya = next(p for p in P.PEOPLE if p.role == '마냐')
        self.assertEqual(maya.recolor[(132, 24, 0)], (247, 206, 24))
        self.assertTrue(set(maya.recolor.values()).isdisjoint(maya.recolor))

    def test_people_without_recolor_keep_an_empty_map(self):
        self.assertEqual(P.Person((0x10,), None, 'x', 'a').recolor, {})


class GroupTests(unittest.TestCase):
    def test_every_group_of_the_group_build_takes_its_own_lines(self):
        # 빠진 그룹은 맵 팔레트 줄을 받지 못해 앞 맵 그룹의 색으로 그려진다
        import dq4groupbuild
        self.assertEqual(P.DQ4_GROUPS, frozenset(dq4groupbuild.LINKS))

    def test_tile_areas_and_tables_do_not_overlap(self):
        spans = [(P.cpu(at), P.cpu(at) + size) for at, size in P.TILE_AREAS]
        spans += [(P.cpu(P.MAP_PALETTES_AT), P.cpu('39:F000')), (P.cpu(P.PALETTES_AT), P.cpu('3D:EB60')),
                  (P.cpu(P.HOOK_AT), P.cpu(P.HOOK_AT) + 0x200)]
        spans.sort()
        for (_, end), (start, _) in zip(spans, spans[1:]):
            self.assertLessEqual(end, start)


class TileAreaTests(unittest.TestCase):
    def test_empty_areas_keep_their_start(self):
        areas = P.tile_areas(bytes(0x400000))
        self.assertEqual(areas, tuple((at, size) for at, size in P.TILE_AREAS))

    def test_used_start_moves_to_the_next_16_byte_boundary(self):
        base = bytearray(0x400000)
        start = P.cpu(P.TILE_AREAS[0][0])
        base[lorom(start) + 5] = 1
        first = P.tile_areas(bytes(base))[0]
        self.assertEqual(first[0], '3E:D710')
        self.assertEqual(first[1], P.TILE_AREAS[0][1] - 0x10)

    def test_pack_takes_back_a_choice_that_leaves_the_last_item_homeless(self):
        # a 가 작은 자리(6)에 들어가면 c(6) 이 갈 곳이 없다 → a 를 큰 자리(8)로 옮긴다
        self.assertEqual(P.pack([('a', 4), ('b', 4), ('c', 6)], [8, 6]), [['a', 'b'], ['c']])

    def test_pack_reports_when_nothing_fits(self):
        with self.assertRaisesRegex(SystemExit, '타일 자료 자리가 모자람'):
            P.pack([('a', 6)], [5])
        self.assertEqual(P.pack([], [5]), [[]])

    def test_pack_stops_at_once_when_the_total_is_larger_than_the_room(self):
        # 되돌아가기에 들어가면 모든 배치를 다 해 본 뒤에야 끝난다. 합을 먼저 보고 그 두 수를 알린다
        items = [(f's{k}', 3) for k in range(40)]
        with self.assertRaisesRegex(SystemExit, '^타일 자료 자리가 모자람: 120 > 119$'):
            P.pack(items, [60, 59])

    def test_pack_reports_the_items_when_the_total_fits_but_no_layout_does(self):
        with self.assertRaisesRegex(SystemExit, "타일 자료 자리가 모자람: 세트·바이트 .*'a', 6"):
            P.pack([('a', 6), ('b', 6)], [11, 1])


class SplitPatchTests(unittest.TestCase):
    AREAS = (('3E:D700', 100), ('3F:EB80', 100))

    def run_split(self, sizes, doc):
        calls = []

        def patch(rom, part, base, at):
            calls.append((part, at))
            if len(calls) == 1:
                writes = [{'at': f'3E:{0xD700 + 0x100 * i:04X}', 'hex': ' '.join(['00'] * n), 'note': f'타일 {s} 자료'}
                          for i, (s, n) in enumerate(sizes.items())]
                writes.append({'at': '00:8000', 'hex': '00', 'note': '타일 10 앞쪽'})
                return {'writes': writes}
            return {'part': part, 'at': at}

        with unittest.mock.patch.object(P.dq5spritewrite, 'patch', patch):
            out = P.split_patches(None, doc, None, self.AREAS)
        return out, calls

    def test_new_sets_stay_first_and_the_rest_is_packed_into_the_areas(self):
        doc = {'format': 'dq5sprite/1', 'sets': [{'set': '10'}, {'set': '11'}, {'set': '12'}], 'new_sets': [{'set': '70'}]}
        out, calls = self.run_split({'70': 30, '10': 60, '11': 50, '12': 20}, doc)
        self.assertEqual(calls[0][1], 0x3ED700)
        first, second = out
        self.assertEqual([r['set'] for r in first['part']['sets']], ['10'])
        self.assertEqual([r['set'] for r in first['part']['new_sets']], ['70'])
        self.assertEqual(first['at'], 0x3ED700)
        self.assertEqual([r['set'] for r in second['part']['sets']], ['11', '12'])
        self.assertEqual(second['at'], 0x3FEB80)
        self.assertNotIn('new_sets', second['part'])

    def test_an_area_without_sets_gets_no_patch(self):
        doc = {'format': 'dq5sprite/1', 'sets': [{'set': '10'}], 'new_sets': []}
        out, _ = self.run_split({'10': 30}, doc)
        self.assertEqual(len(out), 1)
        self.assertEqual([r['set'] for r in out[0]['part']['sets']], ['10'])


def strip(*boxes):
    """2x2 상자를 옆으로 이은 그림. 상자마다 색 넷(왼쪽 위, 오른쪽 위, 왼쪽 아래, 오른쪽 아래), None 은 빈 칸."""
    f = Image.new('RGBA', (2 * len(boxes), 2))
    for k, box in enumerate(boxes):
        for n, c in enumerate(box):
            if c is not None:
                f.putpixel((2 * k + n % 2, n // 2), c + (255,))
    return f


class ResampleTests(unittest.TestCase):
    A, B, MEAN = (240, 200, 200), (200, 240, 200), (230, 210, 200)      # MEAN 은 A 셋 + B 하나의 평균
    BLACK = (8, 8, 8)

    def half(self, *boxes):
        out, xs, ys = P.resample(strip(*boxes), 0.5)
        return [out.getpixel((x, 0)) for x in range(out.width)], xs, ys

    def test_a_cell_takes_the_colour_that_fills_most_of_its_box_not_the_mean(self):
        cells, xs, ys = self.half([self.A, self.A, self.B, self.A], [self.MEAN] * 4)
        self.assertEqual(cells, [self.A + (255,), self.MEAN + (255,)])
        self.assertEqual((xs, ys), ([1, 3], [1]))

    def test_a_cell_without_a_majority_takes_the_colour_nearest_the_mean(self):
        mid = (220, 220, 200)
        cells, _, _ = self.half([self.A, self.A, self.B, self.B], [mid] * 4)
        self.assertEqual(cells[0], mid + (255,))

    def test_dark_dots_win_from_a_third_of_the_box(self):
        grey = (124, 104, 104)                                          # 검정 둘 + A 둘의 평균
        cells, _, _ = self.half([self.BLACK, self.A, self.A, self.A], [self.BLACK, self.BLACK, self.A, self.A], [grey] * 4)
        self.assertEqual(cells[0], self.A + (255,))                     # 4분의 1 은 모자라다
        self.assertEqual(cells[1], self.BLACK + (255,))

    def test_a_light_pattern_on_a_dark_ground_keeps_the_light_colour(self):
        ground, light, between = (60, 60, 90), (250, 250, 250), (150, 150, 170)
        self.assertLess(P.lab(ground)[0], 45)
        self.assertGreaterEqual(P.lab(between)[0], 50)
        cells, _, _ = self.half([ground, ground, ground, light], [between] * 4)
        self.assertEqual(cells[0], between + (255,))

    def test_cells_less_than_half_covered_stay_empty(self):
        cells, _, _ = self.half([self.A, None, None, None], [self.A, self.A, self.A, None])
        self.assertEqual(cells[0][3], 0)
        self.assertEqual(cells[1], self.A + (255,))


def skin_cell(left=0, right=16):
    c = Image.new('RGBA', (16, 24))
    for y in range(4, 20):
        for x in range(left, right):
            c.putpixel((x, y), FACE)
    return c


FACE = P.SKIN[1] + (255,)
INK, EYE_WHITE = P.INK + (255,), P.WHITE + (255,)
GRID = (list(range(16)), list(range(24)))


class DotEyeTests(unittest.TestCase):
    def test_front_eyes_are_one_by_two_ink_dots_with_whites_on_the_outside(self):
        s = skin_cell()
        P.dot_eyes([(5, 8), (10, 8)], s, *GRID)
        self.assertEqual(cells_of(s, INK), {(5, 8), (5, 9), (10, 8), (10, 9)})
        self.assertEqual(cells_of(s, EYE_WHITE), {(4, 8), (4, 9), (11, 8), (11, 9)})

    def test_side_eye_gets_its_white_behind_the_pupil(self):
        for facing, behind in ((-1, 6), (1, 4)):
            s = skin_cell()
            P.dot_eyes([(5, 8)], s, *GRID, facing=facing)
            self.assertEqual(cells_of(s, INK), {(5, 8), (5, 9)})
            self.assertEqual(cells_of(s, EYE_WHITE), {(behind, 8), (behind, 9)}, facing)

    def test_eyes_take_the_nearest_shrunk_column_and_row(self):
        s = skin_cell()
        P.dot_eyes([(11, 17)], s, [2 * k + 1 for k in range(16)], [2 * k for k in range(24)], facing=1)
        self.assertEqual(cells_of(s, INK), {(5, 8), (5, 9)})

    def test_no_white_is_drawn_without_sclera_or_outside_the_body(self):
        s = skin_cell()
        P.dot_eyes([(5, 8), (10, 8)], s, *GRID, sclera=False)
        self.assertEqual(cells_of(s, EYE_WHITE), set())
        s = skin_cell(left=5)
        P.dot_eyes([(5, 8), (10, 8)], s, *GRID)
        self.assertEqual(cells_of(s, EYE_WHITE), {(11, 8), (11, 9)})
        self.assertEqual(s.getpixel((4, 8))[3], 0)

    def test_nds_whites_beside_the_pupil_go_unless_the_person_wears_glasses(self):
        for glasses, left in ((False, FACE), (True, EYE_WHITE)):
            s = skin_cell()
            for y in (8, 9):
                s.putpixel((6, y), EYE_WHITE)
            P.dot_eyes([(5, 8), (10, 8)], s, *GRID, glasses, sclera=False)
            self.assertEqual(s.getpixel((6, 8)), left, glasses)

    def test_only_a_near_black_cell_above_the_eye_is_cleared(self):
        black, brown = (10, 10, 10, 255), (120, 70, 40, 255)
        self.assertLess(P.lab(black[:3])[0], 28)
        self.assertTrue(28 <= P.lab(brown[:3])[0] < 45)
        s = skin_cell()
        s.putpixel((5, 7), black)
        s.putpixel((10, 7), brown)
        P.dot_eyes([(5, 8), (10, 8)], s, *GRID)
        self.assertEqual(s.getpixel((5, 7)), FACE)
        self.assertEqual(s.getpixel((10, 7)), brown)

    def test_eyes_that_land_side_by_side_are_spread_by_the_face_width(self):
        for left, right, want in ((3, 13, {6, 9}), (5, 10, {6, 8})):
            s = skin_cell(left, right)
            P.dot_eyes([(6, 8), (7, 8)], s, *GRID, sclera=False)
            self.assertEqual({x for x, _ in cells_of(s, INK)}, want, (left, right))
            self.assertEqual({y for _, y in cells_of(s, INK)}, {8, 9})


class EyeSpotTests(unittest.TestCase):
    def single_dots(self):
        f = face_frame()
        for x in (8, 13):
            f.putpixel((x, 11), SKIN)
            for d in (-1, 1):
                f.putpixel((x + d, 11), SKIN)
        return f

    def test_spots_are_the_top_dot_of_each_pupil(self):
        self.assertEqual(P.eye_spots(face_frame(), False), [(8, 10), (13, 10)])
        self.assertEqual(P.eye_spots(face_frame(eyes=((8, 10),)), True), [(8, 10)])

    def test_one_dot_pupils_beside_a_white_are_found_too(self):
        f = self.single_dots()
        self.assertEqual(P.find_eyes(f), [])
        self.assertEqual(P.eye_spots(f, False), [(8, 10), (13, 10)])
        self.assertEqual(P.eye_spots(f, True), [(8, 10)])

    def test_a_dark_dot_without_white_or_face_below_is_not_an_eye(self):
        self.assertEqual(P.eye_spots(face_frame(whites=[]), False), [])
        f = self.single_dots()
        for x in (8, 13):
            for y in (11, 12, 13):
                f.putpixel((x, y), (40, 60, 160, 255))
        self.assertEqual(P.eye_spots(f, False), [])
        self.assertEqual(P.eye_spots(f, False, skin=False), [(8, 10), (13, 10)])

    def test_side_eye_is_looked_for_near_the_front_eye_level_only(self):
        f = face_frame(eyes=((8, 10),))
        self.assertEqual(P.eye_spots(f, True, level=f.height - 10), [(8, 10)])
        self.assertEqual(P.eye_spots(f, True, level=f.height - 12), [(8, 10)])
        self.assertEqual(P.eye_spots(f, True, level=f.height - 13), [])
        self.assertEqual(P.eye_spots(self.single_dots(), True, level=5), [])


class SharedColourTests(unittest.TestCase):
    def test_common_skin_gathers_near_skin_and_near_white_colours(self):
        near_skin, near_white, cloth = (224, 176, 143), (250, 250, 250), (40, 60, 160)
        for c, tone in ((near_skin, P.SKIN[1]), (near_white, P.WHITE)):
            self.assertLessEqual(P.math.dist(P.lab(c), P.lab(tone)), P.SKIN_NEAR)
        a = Image.new('RGBA', (5, 1))
        for x, c in enumerate((near_skin, near_white, cloth, P.INK)):
            a.putpixel((x, 0), c + (255,))
        b = Image.new('RGBA', (1, 1), P.SKIN[2] + (255,))
        P.common_skin({'down': [a, b]})
        self.assertEqual([a.getpixel((x, 0)) for x in range(5)],
                         [P.SKIN[1] + (255,), P.WHITE + (255,), cloth + (255,), P.INK + (255,), (0, 0, 0, 0)])
        self.assertEqual(b.getpixel((0, 0)), P.SKIN[2] + (255,))

    def test_people_share_the_skin_tones_but_walking_pictures_keep_their_own(self):
        def sheet(path):
            im = Image.new('RGBA', (128, 256))
            for row in range(8):
                for y in range(row * 32 + 4, row * 32 + 28):
                    for x in range(4, 12):
                        im.putpixel((x, y), (224, 176, 143, 255))
            im.save(path)
        with tempfile.TemporaryDirectory() as d:
            assets = Path(d)
            (assets / P.FIELD).mkdir(parents=True)
            sheet(assets / P.FIELD / 'h900.png')
            person = P.rgb_frames(P.Person((1,), None, 'h900', 'x'), assets)
            beast = P.rgb_frames(P.Person((1,), None, 'h900', 'x', anim='frames'), assets)
        self.assertEqual(set(P.histogram(person)), {P.SKIN[1]})
        self.assertEqual(set(P.histogram(beast)), {(224, 176, 143)})

    def test_histogram_weighs_ink_and_the_shared_tones(self):
        c = Image.new('RGBA', (4, 1))
        for x, colour in enumerate((P.INK, P.SKIN[0], P.WHITE, (40, 60, 160))):
            c.putpixel((x, 0), colour + (255,))
        self.assertEqual(P.histogram({'down': [c]}), Counter({P.INK: P.INK_WEIGHT, P.SKIN[0]: P.SKIN_WEIGHT,
                                                               P.WHITE: P.SKIN_WEIGHT, (40, 60, 160): 1}))

    def test_accented_lifts_small_own_colours_to_a_share_of_the_clothes(self):
        coat, ribbon, hem = (40, 60, 160), (200, 30, 30), (30, 160, 60)
        hist = Counter({coat: 900, ribbon: 2, hem: 98, P.SKIN[1]: 5, P.INK: 3, P.WHITE: 1})
        out = P.accented(hist)
        floor = 1000 * P.ACCENT_SHARE
        self.assertEqual(out[ribbon], floor)
        self.assertEqual((out[coat], out[hem]), (900, 98))
        for c in (P.SKIN[1], P.INK, P.WHITE):
            self.assertEqual(out[c], hist[c])
        self.assertGreater(floor, 2)
        self.assertLess(floor, 98)


def shades(red, n):
    return Counter({(red, 16 * k, 0): 10 for k in range(n)})


class LineTests(unittest.TestCase):
    ELSEWHERE = 0x40

    def person(self, n, **kw):
        return P.Person((n,), None, 's', f'p{n}', **kw)

    def test_line_three_is_shared(self):
        self.assertIn(3, P.SHARED_LINES)
        self.assertEqual(len(set(P.SHARED_LINES)), len(P.SHARED_LINES))
        for lent in P.LENT_LINES.values():
            self.assertFalse(set(lent) & set(P.SHARED_LINES))

    def test_people_seen_only_where_a_party_line_is_free_may_take_it(self):
        self.assertNotIn(self.ELSEWHERE, P.LENT_LINES)
        lent = P.LENT_LINES[P.PROLOGUE]
        crowd = [self.person(k) for k in range(len(P.SHARED_LINES))]
        home, both = self.person(0x20), self.person(0x21)
        hists = {p: shades(40 * k, 12) for k, p in enumerate(crowd)}
        hists[home], hists[both] = shades(250, 2), shades(251, 2)
        where = {p: {P.PROLOGUE, self.ELSEWHERE} for p in crowd}
        where[home], where[both] = {P.PROLOGUE}, {P.PROLOGUE, self.ELSEWHERE}
        assign, _ = P.lines([*crowd, home, both], hists, where)
        self.assertEqual(sorted(assign[p] for p in crowd), sorted(P.SHARED_LINES))
        self.assertEqual(assign[home], lent[0])
        self.assertIn(assign[both], P.SHARED_LINES)

    def test_two_heavy_people_in_one_group_go_to_different_lines(self):
        for weight, apart in ((P.KEY_WEIGHT, True), (1, False)):
            a, b = self.person(1, weight=weight), self.person(2, weight=weight)
            hists = {a: shades(200, 3), b: shades(30, 3)}
            assign, _ = P.lines([a, b], hists, {a: {self.ELSEWHERE}, b: {self.ELSEWHERE}})
            self.assertEqual(assign[a] != assign[b], apart, weight)

    def test_heavy_people_in_different_groups_may_share_a_line(self):
        a, b = self.person(1, weight=P.KEY_WEIGHT), self.person(2, weight=P.KEY_WEIGHT)
        hists = {a: shades(200, 3), b: shades(30, 3)}
        assign, _ = P.lines([a, b], hists, {a: {self.ELSEWHERE}, b: {self.ELSEWHERE + 1}})
        self.assertEqual(assign[a], assign[b])

    def test_a_heavy_person_takes_the_line_where_the_fewest_heavy_colours_meet(self):
        first, second, third = (self.person(k, weight=P.KEY_WEIGHT) for k in (1, 2, 3))
        light = [self.person(0x10 + k) for k in range(len(P.SHARED_LINES))]
        hists = {first: shades(200, 6), second: shades(30, 5), third: shades(120, 2)}
        hists.update({p: shades(60 + k, 1) for k, p in enumerate(light)})
        g = self.ELSEWHERE
        where = {p: {g} for p in hists}
        with unittest.mock.patch.object(P, 'SHARED_LINES', P.SHARED_LINES[:2]):
            assign, _ = P.lines([*light, third, second, first], hists, where)
        self.assertNotEqual(assign[first], assign[second])
        self.assertEqual(assign[third], assign[second])

    def test_heavy_people_are_placed_before_the_rest(self):
        light, heavy, main = self.person(1), self.person(2, weight=P.KEY_WEIGHT), self.person(3, main=True)
        hists = {light: shades(200, 12), heavy: shades(30, 2), main: shades(120, 3)}
        assign, _ = P.lines([light, heavy, main], hists, {p: {self.ELSEWHERE} for p in hists})
        self.assertEqual(list(assign), [main, heavy, light])

    def test_a_pinned_person_keeps_its_line_and_still_counts_as_heavy_there(self):
        pinned, other = self.person(1, main=True, line=2), self.person(2, main=True)
        hists = {pinned: shades(30, 3), other: shades(200, 3)}
        assign, _ = P.lines([pinned, other], hists, {p: {self.ELSEWHERE} for p in hists})
        self.assertEqual(assign[pinned], 2)
        self.assertNotEqual(assign[other], 2)

    def test_a_pin_on_a_line_the_person_cannot_use_stops_the_build(self):
        pinned = self.person(1, line=7)
        with self.assertRaisesRegex(SystemExit, '쓸 수 없는 줄'):
            P.lines([pinned], {pinned: shades(30, 3)}, {pinned: {self.ELSEWHERE}})

    def test_the_swordsman_is_pinned_to_line_zero(self):
        # 검사가 빌린 그림 90 의 세트 63 은 엔진이 OBJ 팔레트 0 으로 싣는다
        self.assertEqual(next(p for p in P.PEOPLE if p.role == '검사').line, 0)

    def test_a_set_the_engine_loads_on_palette_zero_must_sit_on_line_zero(self):
        row = lambda role, s, line: (P.Person((1,), None, 's', role), s, 'simple', 24, 20, [], line, [])  # noqa: E731
        self.assertEqual(P.line0_problems([row('a', 0x63, 0), row('b', 0x6C, 0), row('c', 0x62, 3)]), [])
        problems = P.line0_problems([row('a', 0x63, 2), row('b', 0x6C, 4), row('c', 0x62, 3)])
        self.assertEqual(len(problems), 2)
        self.assertIn('a: 세트 63', problems[0])
        self.assertIn('줄 4', problems[1])

    def test_the_palette_zero_sets_are_the_two_the_engine_tests_for(self):
        # 1F:D051 은 CMP #$63 / CMP #$6C 로 이 두 세트만 가린다
        self.assertEqual(P.LINE0_SETS, {0x63, 0x6C})


class WeightTests(unittest.TestCase):
    def test_main_people_weigh_the_key_weight_and_the_rest_one(self):
        self.assertGreater(P.KEY_WEIGHT, 1)
        self.assertEqual(P.Person((1,), None, 's', 'x', main=True).weight, P.KEY_WEIGHT)
        self.assertEqual(P.Person((1,), None, 's', 'x').weight, 1)
        self.assertEqual(P.Person((1,), None, 's', 'x', main=True, weight=3).weight, 3)
        for p in P.PEOPLE:
            if p.main:
                self.assertEqual(p.weight, P.KEY_WEIGHT, p.role)

    def test_key_event_people_and_the_emblem_townsfolk_weigh_the_key_weight(self):
        by_role = {p.role: p for p in P.PEOPLE if p.seen is not None}
        self.assertLessEqual({'엘프', '검은 망토', '카멜레온 맨', '비비안'}, P.KEY_EVENT)
        self.assertLessEqual(P.KEY_EVENT, set(by_role))
        for role, p in by_role.items():
            self.assertEqual(p.weight, P.KEY_WEIGHT if role in P.KEY_EVENT else 1, role)
        for role in ('병사', '위병', '슬라임'):
            self.assertEqual([p.weight for p in P.PEOPLE if p.role == role], [P.KEY_WEIGHT], role)
        self.assertEqual([p.weight for p in P.PEOPLE if p.role == '남자'], [1])


def synthetic_person(name, sheet, **kw):
    return P.Person((0x10 + len(name),), None, sheet, name, **kw)


class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.assets = Path(self.tmp.name) / 'assets'
        (self.assets / P.FIELD).mkdir(parents=True)
        for sheet in ('h900', 'h901', 'h902'):
            nds_sheet(self.assets / P.FIELD / f'{sheet}.png')
        self.work = Path(self.tmp.name) / 'work'
        self.work.mkdir()
        self.people = (synthetic_person('aa', 'h900', main=True), synthetic_person('bbb', 'h901'),
                       synthetic_person('cccc', 'h902', palette=7))

    def prepare(self, limit, sets=(0x41, 0x42, 0x43), **kw):
        table = dict(zip(self.people, sets))
        with unittest.mock.patch.object(P, 'PEOPLE', self.people), \
                unittest.mock.patch.object(P, 'target', lambda person, rom: (table[person], 'simple', limit)):
            return P.prepare(None, self.assets, self.work, **kw)

    def test_each_person_gets_a_sheet_a_line_and_colours(self):
        rows, board = self.prepare(limit=99)
        self.assertEqual([r[0].role for r in rows], ['aa', 'bbb', 'cccc'])
        for (person, s, layout, limit, n, steps, line, pal), want in zip(rows, (0x41, 0x42, 0x43)):
            self.assertEqual((s, layout, limit), (want, 'simple', 99))
            self.assertTrue((self.work / f'{s:02X}.png').is_file())
            self.assertEqual(Image.open(self.work / f'{s:02X}.png').size, (32, 96))
            self.assertEqual(steps, [])
            self.assertLessEqual(len(pal), 15)
        self.assertEqual(rows[2][6], 7)
        self.assertIn(rows[0][6], P.SHARED_LINES)
        self.assertTrue(all(len(row) == 15 or len(row) <= 15 for row in board.values()))

    def test_people_over_the_tile_limit_lose_walk_steps_in_order_unless_main(self):
        rows, _ = self.prepare(limit=0)
        main, other = rows[0], rows[1]
        self.assertEqual(main[5], [])
        self.assertEqual(other[5], [name for name, _ in P.DEGRADE])
        self.assertGreater(other[4], 0)

    def test_squeeze_mirrors_the_sides_of_everyone_but_main_people(self):
        mirror = P.DEGRADE[0][0]
        # 주요 인물은 반전을 허락받았어도(타일 한도를 넘을 때만 쓴다) 자리를 아끼려고 반전하지 않는다
        self.people += (synthetic_person('ddddd', 'h900', main=True, allow=(mirror,)),)
        sets = (0x41, 0x42, 0x43, 0x44)
        self.assertEqual([r[5] for r in self.prepare(limit=99, sets=sets)[0]], [[], [], [], []])
        rows, _ = self.prepare(limit=99, sets=sets, squeeze=True)
        self.assertEqual([r[5] for r in rows], [[], [mirror], [mirror], []])
        names = [name for name, _ in P.ROWS8]
        for (_, s, *_), mirrored in zip(rows, (False, True, True, False)):
            with Image.open(self.work / f'{s:02X}.png') as sheet:
                side = {name: sheet.crop((0, 24 * names.index(name), 16, 24 * names.index(name) + 24)) for name in names}
            flipped = side['right'].transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            self.assertEqual(list(side['left'].get_flattened_data()) == list(flipped.get_flattened_data()), mirrored, f'{s:02X}')

    def test_two_people_on_one_set_stop_the_build(self):
        with self.assertRaisesRegex(SystemExit, '두 인물이 같은 세트를 바꿈'):
            self.prepare(limit=99, sets=(0x41, 0x41, 0x43))


class MainTests(unittest.TestCase):
    ROW = (P.Person((1,), 0x36, 'h900', '용사'), 0x41, 'simple', 24, 20, ['위 걸음 멈춤'], 1, [])

    def run_main(self, *argv):
        out = io.StringIO()
        with unittest.mock.patch('sys.argv', ['dq4people.py', *argv]), contextlib.redirect_stdout(out):
            P.main()
        return out.getvalue()

    def test_report_line_lists_role_set_tiles_and_steps(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            P.report([self.ROW, (P.Person((0x0B, 0x0C), None, 'h007', '아이'), 0x42, 'overlap', 48, 40, [], 2, [])])
        first, second = out.getvalue().splitlines()
        self.assertEqual(first, '용사       그림 01    그룹 36  h900 세트 41 simple  타일 20/24 팔레트 1 위 걸음 멈춤')
        self.assertIn('그림 0B,0C', second)
        self.assertIn('어디나', second)
        self.assertIn('overlap', second)

    def test_plan_prints_the_table_without_building(self):
        with tempfile.TemporaryDirectory() as tmp:
            dq5 = Path(tmp) / 'dq5.sfc'
            dq5.write_bytes(b'dq5')
            with unittest.mock.patch.object(P, 'prepare', lambda rom, assets, work, base: ([self.ROW], {})), \
                    unittest.mock.patch.object(P, 'Rom', lambda raw: raw), \
                    unittest.mock.patch.object(P, 'build', side_effect=AssertionError('no build')):
                text = self.run_main('--plan', '--dq5', str(dq5), '--assets', tmp)
        self.assertIn('세트 41', text)
        self.assertNotIn('rom/', text)

    def test_build_needs_base_and_out(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                self.run_main('--assets', 'x')
        self.assertEqual(raised.exception.code, 2)

    def test_build_prints_the_report_and_the_output_path(self):
        seen = {}

        def fake_build(base, dq5, assets, out, work):
            seen.update(base=base, out=out, work=work.is_dir())
            return [self.ROW]
        with tempfile.TemporaryDirectory() as tmp:
            with unittest.mock.patch.object(P, 'build', fake_build):
                text = self.run_main('--base', 'b.sfc', '--out', 'o.sfc', '--assets', tmp, '--work', str(Path(tmp) / 'w'))
        self.assertEqual(text.splitlines()[-1], 'o.sfc')
        self.assertIn('세트 41', text)
        self.assertEqual(seen, {'base': Path('b.sfc'), 'out': Path('o.sfc'), 'work': True})


class BuildFlowTests(unittest.TestCase):
    """롬 없이 build 가 시트 준비 결과로 스프라이트·팔레트 문서를 짜고 패치를 얹는 차례를 본다. 시트 준비·패치 만들기는
    가짜로 바꾼다."""
    RED, GREEN, BLUE = (255, 0, 0), (0, 255, 0), (8, 16, 248)

    def person(self, role, new_set=None, palette=None, flag=None):
        from types import SimpleNamespace
        return SimpleNamespace(role=role, new_set=new_set, palette=palette, flag=flag)

    def rows(self, over=False):
        p = self.person
        return [(p('a'), 0x90, 'overlap', 48, 49 if over else 30, [], 1, [self.RED]),
                (p('hero1', new_set=0), 0xA5, 'overlap', 48, 40, [], 2, [self.GREEN]),
                (p('fixed', palette='x'), 0x91, 'simple', 24, 20, [], 3, [self.BLUE]),
                (p('hero2', new_set=1), 0xA6, 'overlap', 48, 40, [], 2, [self.GREEN]),
                (p('flagged', palette='y', flag=(0x12, 0x40)), 0x92, 'simple', 24, 20, [], 4, [self.RED, None])]

    BOARD = {(0x36, 1): [(0, 0, 0), None], (0x36, 2): [None, None], (0x37, 1): [(0, 0, 0), (8, 8, 8)],
             (0x37, 2): [(16, 16, 16), None]}

    def run_build(self, rows):
        calls = {'applied': [], 'palette_docs': []}

        def run(cmd, **kw):
            calls['dq5build'] = [str(c) for c in cmd]
            Path(cmd[cmd.index('-o') + 1]).write_bytes(b'mid')

        def objpalette(rom, doc, at):
            calls['palette_docs'].append((doc, at))
            return {'format': 'dq5patch/1', 'writes': [], 'at': at}

        def apply_writes(data, original, paths):
            calls['applied'].append([Path(p).name for p in paths])
            return bytearray(data)

        with tempfile.TemporaryDirectory() as t:
            work = Path(t)
            base, dq5, out = work / 'base.sfc', work / 'dq5.sfc', work / 'out.sfc'
            base.write_bytes(bytes(0x400000))
            dq5.write_bytes(b'dq5')
            with unittest.mock.patch.multiple(P, prepare=lambda *a: (rows, self.BOARD),
                                              split_patches=lambda rom, doc, w, areas: [{'n': 0}, {'n': 1}],
                                              tile_areas=lambda data: (('3F:8000', 16),),
                                              hook_patch=lambda rom: {'hook': 1}, swap_patch=lambda rom: {'swap': 1},
                                              apply_writes=apply_writes), \
                    unittest.mock.patch.object(P.subprocess, 'run', run), \
                    unittest.mock.patch.object(P.dq5objpalette, 'patch', objpalette):
                P.build(base, dq5, work / 'assets', out, work)
                calls['sprite'] = json.loads((work / 'sprite.json').read_text())
                calls['out'] = out.read_bytes()
        return calls

    def test_build_tries_again_with_squeeze_only_when_the_tile_room_runs_out(self):
        calls = []

        def assemble(base, dq5, assets, out, work, squeeze):
            calls.append(squeeze)
            if not squeeze:
                raise SystemExit('타일 자료 자리가 모자람: 2 > 1')
            return 'rows'
        with unittest.mock.patch.object(P, 'assemble', assemble):
            self.assertEqual(P.build(None, None, None, None, None), 'rows')
        self.assertEqual(calls, [False, True])
        with unittest.mock.patch.object(P, 'assemble', side_effect=SystemExit('타일 한도를 넘음: a 49>48')) as other:
            with self.assertRaisesRegex(SystemExit, '타일 한도'):
                P.build(None, None, None, None, None)
        self.assertEqual(other.call_count, 1)

    def test_tile_limit_stops_the_build(self):
        with self.assertRaisesRegex(SystemExit, 'a 49>48'):
            self.run_build(self.rows(over=True))

    def test_sprite_doc_links_the_new_leader_sets_to_the_leader_pictures(self):
        doc = self.run_build(self.rows())['sprite']
        self.assertEqual([r['set'] for r in doc['sets']], ['90', '91', '92'])
        self.assertEqual([(r['set'], r['palette']) for r in doc['new_sets']], [('A5', 0), ('A6', 0)])
        self.assertEqual(doc['gfx'], [{'gfx': f'{g:02X}', 'set': s} for g, s in zip(P.LEADER_PICTURES, ('A5', 'A6'))])

    def test_patches_go_on_sprites_then_palettes_then_the_swap(self):
        calls = self.run_build(self.rows())
        self.assertEqual(calls['applied'], [['sprite0.dq5patch.json', 'sprite1.dq5patch.json', 'palette.dq5patch.json',
                                             'maps.dq5patch.json', 'hook.dq5patch.json'], ['swap.dq5patch.json']])
        build = calls['dq5build']
        self.assertEqual([Path(a).name for a in build if a.endswith('.json')],
                         ['sprite0.dq5patch.json', 'sprite1.dq5patch.json'])
        out = calls['out']
        checksum = int.from_bytes(out[0x7FDE:0x7FE0], 'little')
        self.assertEqual(checksum ^ int.from_bytes(out[0x7FDC:0x7FDE], 'little'), 0xFFFF)

    def test_palette_lines_take_the_fullest_group_then_the_fixed_lines(self):
        docs = dict((at, doc) for doc, at in self.run_build(self.rows())['palette_docs'])
        pal = docs[P.PALETTES_AT]
        lines = {p['palette']: p['colors'] for p in pal['palettes']}
        # 37 이 칸이 더 찬 그룹이라 기본 줄 1·2 는 37 의 것, 깃발 없는 고정 줄 3 은 그 인물의 색
        self.assertEqual(sorted(lines), [1, 2, 3])
        self.assertEqual(lines[1][:2], [0, 1 << 10 | 1 << 5 | 1])
        self.assertEqual(lines[3][0], 31 << 10 | 2 << 5 | 1)
        self.assertTrue(all(len(c) == 15 for c in lines.values()))
        self.assertEqual(pal['sets'][0], {'set': '90', 'palette': 1})
        maps = docs[P.MAP_PALETTES_AT]['new_map_palettes']
        plain = [m for m in maps if m['flag'] == 'FF']
        self.assertEqual([(m['map'], m['line']) for m in plain], [('36/FF', '09'), ('36/FF', '0A'), ('37/FF', '09'),
                                                                   ('37/FF', '0A')])
        flagged = [m for m in maps if m['flag'] != 'FF']
        every = [f'{g:02X}/FF' for g in P.chapter_groups(2)] + ['FE/00', 'FE/01', 'FE/02']
        self.assertEqual([m['map'] for m in flagged], every)
        self.assertTrue(all((m['line'], m['flag'], m['mask']) == ('0C', '12', '40') for m in flagged))
        self.assertEqual(flagged[0]['colors'][:2], [31, 0])


if __name__ == '__main__':
    unittest.main()


class EventPeopleTests(unittest.TestCase):
    # 05:862F(말 걸 대상을 찾을 때 건너뛰는 그림)와 1E:DC67(말을 걸 수 없는 물체로 만드는 그림)
    SKIPPED = {*range(0x46, 0x50), 0x63, *range(0x78, 0x82), 0x83, 0x84, 0x99, 0x12, 0x24, 0x35, 0x98,
               *range(0xA2, 0x100)}

    def test_event_pictures_are_their_own_spare_and_unique(self):
        pictures = [pic for _, pic, *_ in P.EVENT_PEOPLE]
        self.assertEqual(len(set(pictures)), len(pictures))
        self.assertEqual(set(P.EVENT_PICTURES.values()), set(pictures))
        events = [p for p in P.PEOPLE if p.seen is not None]
        self.assertEqual(len(events), len(pictures))
        for p in events:
            self.assertEqual(p.pictures, (p.spare,), p.role)

    def test_event_pictures_are_not_used_by_other_people_or_skipped_when_talking(self):
        others = set()
        for p in P.PEOPLE:
            if p.seen is None:
                others |= set(p.pictures) | ({p.spare} if p.spare is not None else set())
        for role, pic, *_ in P.EVENT_PEOPLE:
            self.assertNotIn(pic, others, role)
            self.assertNotIn(pic, self.SKIPPED, role)

    def test_where_takes_the_event_groups_only(self):
        elf = P.Person((0x37,), None, 'x', 'elf', spare=0x37, seen=(0x45,))
        self.assertEqual(P.where([elf], {})[elf], {0x45})
        self.assertEqual(P.where([elf], {0x37: {0x36}})[elf], {0x45})
