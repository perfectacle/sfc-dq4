import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import dq4chapterbox as box

NES = Path(__file__).resolve().parents[3] / 'rom' / 'dq4.nes'


def branch_target(code, at):
    """at 의 BNE/BRA 가 가는 곳."""
    d = code[at + 1]
    return at + 2 + (d - 256 if d > 127 else d)


class CodeTests(unittest.TestCase):
    def test_if_pending_branches_reach_other(self):
        then, other = bytes((0xA9, 0x04)), bytes((0xA9, 0x17))
        code = box.if_pending((box.CHAPTER1,), then, other)
        skips = [i for i in range(len(code) - len(then) - len(other) - 2) if code[i] == 0xD0]
        self.assertEqual(len(skips), 3)
        other_at = len(code) - len(other)
        for at in skips:
            self.assertEqual(branch_target(code, at), other_at)
        bra = other_at - 2
        self.assertEqual(code[bra], 0x80)
        self.assertEqual(branch_target(code, bra), len(code))

    def test_if_pending_without_other_falls_to_end(self):
        then = bytes((0xA9, 0xA3, 0x8F, 0xDF, 0x21, 0x7E))
        code = box.if_pending((box.CHAPTER1,), then)
        for at in [i for i in range(len(code) - len(then)) if code[i] == 0xD0]:
            self.assertEqual(branch_target(code, at), len(code))

    def test_if_pending_tries_each_scene(self):
        # 장면마다 검사 셋. 맞지 않으면 다음 장면으로, 마지막 장면이 맞지 않으면 other. 앞 장면이 맞으면 BRA 로 then
        then, other = bytes((0xA9, 0x04)), bytes((0xA9, 0x17))
        code = box.if_pending((box.PROLOGUE, box.CHAPTER1), then, other)
        then_at = len(code) - len(other) - 2 - len(then)
        other_at = len(code) - len(other)
        block = 6 + 1 + 6 + 1 + 7 + 1                       # LDA/CMP/BNE ×2, LDA long/AND/BNE
        first = [6, 13, 21]                                  # 첫 장면 BNE 자리
        for at in first:
            self.assertEqual(code[at - 1], 0xD0)
            self.assertEqual(branch_target(code, at - 1), block + 2)
        self.assertEqual(code[block], 0x80)
        self.assertEqual(branch_target(code, block), then_at)
        for at in (block + 2 + 6, block + 2 + 13, block + 2 + 21):
            self.assertEqual(branch_target(code, at - 1), other_at)
        self.assertEqual(code[1:3], bytes((0xBC, 0x00)))
        self.assertEqual(code[4], box.PROLOGUE.where[0])
        self.assertEqual(code[block + 2 + 4], box.CHAPTER1.where[0])

    def test_fade_loop_jumps_back_to_store(self):
        code = box.fade(1, 15, 1)
        self.assertEqual(code[:2], bytes((0xA9, 1)))
        self.assertEqual(branch_target(code, len(code) - 2), 2)
        self.assertEqual(code[-4:-2], bytes((0xC9, 16)))
        self.assertEqual(box.fade(14, 0, 1)[-4:-2], bytes((0xC9, 0xFF)))

    def test_entry_points_do_not_depend_on_data(self):
        blank = bytes(box.BOX_W * box.BOX_H * 2)
        for scenes in ((box.CHAPTER1,), (box.PROLOGUE, box.CHAPTER1)):
            a = box.Layout(box.CODE_AT, scenes, b'', [blank] * len(scenes), box.palettes())
            b = box.Layout(box.CODE_AT, scenes, bytes(16 * 40), [blank] * len(scenes), box.palettes())
            self.assertEqual((a.box_at, a.reveal_at), (b.box_at, b.reveal_at))
            self.assertEqual(box.entry_points(scenes), {**a.box_at, 'reveal': a.reveal_at})

    def test_start_clears_song_skip_when_no_scene_waits(self):
        # 새 게임 첫 기록은 21A5 bit6 이 켜진 채 쓰여, 이어 하기에서 끄지 않으면 맵을 옮겨도 곡이 울리지 않았다
        blank = bytes(box.BOX_W * box.BOX_H * 2)
        scenes = box.GAME_SCENES
        lay = box.Layout(box.CODE_AT, scenes, b'', [blank] * len(scenes), box.palettes())
        start = lay.blob[:lay.hook_at - lay.start_at]
        addr = box.SKIP_SONG[0].to_bytes(3, 'little')
        on = bytes((0xAF, *addr, 0x09, 0x40, 0x8F, *addr))
        off = bytes((0xAF, *addr, 0x29, 0xBF, 0x8F, *addr))
        self.assertEqual(start, bytes((0xA9, 0x80, 0x85, 0xBE)) + box.if_pending(scenes, on, off) + start[-13:])
        at = start.index(off)
        self.assertEqual(start[at - 2:at], bytes((0x80, len(off))))   # 켜는 갈래는 끄기를 건너뜀

    def test_code_bank_is_not_a_sound_bank(self):
        # 사운드 세트는 이 롬 위에 얹으며 자기 뱅크가 비어 있어야 한다
        import dq4soundpatch
        self.assertNotIn(box.CODE_AT >> 16, dq4soundpatch.DATA_BANKS)

    def test_snes_tile_planes(self):
        rows = [[3, 1, 2, 0, 0, 0, 0, 0]] + [[0] * 8] * 7
        t = box.snes_tile(rows)
        self.assertEqual(t[:2], bytes((0b11000000, 0b10100000)))


class FcTileTests(unittest.TestCase):
    def nes(self, n, plane):
        bank, addr = box.FC_TILES
        o = 0x10 + bank * 0x4000 + (addr - 0x8000) + (n - 1) * 8
        data = bytearray(o + 8)
        data[o:o + 8] = plane
        return bytes(data)

    def test_no_shadow_tiles_keep_plane_0_only(self):
        plane = bytes([0xFF, 0x81, 0x55, 0, 0xAA, 0x0F, 0xF0, 0x3C])
        for n in box.FC_BORDER.values():
            rows = box.fc_tile(self.nes(n, plane), n)
            self.assertEqual([[v >> 1 for v in row] for row in rows], [[0] * 8] * 8, f'{n:02X}')
            self.assertEqual(rows[1], [1, 0, 0, 0, 0, 0, 0, 1])

    def test_shadow_is_plane_0_inverted_one_row_down(self):
        rows = box.fc_tile(self.nes(box.FC_FILL, bytes([0x80] + [0] * 7)), box.FC_FILL)
        self.assertEqual(rows[0], [3] + [2] * 7)
        self.assertEqual(rows[1], [0] + [2] * 7)
        self.assertEqual({v for row in rows[2:] for v in row}, {2})


class DotFont:
    """글자마다 폭 8, 점 하나(0, 0)만 찍는 글꼴. 띠 안의 위치는 dq4menupatch.render 가 정한다."""

    def char(self, ch):
        return 8, [(0, 0)]


def synthetic_nes():
    bank, addr = box.FC_TILES
    nes = bytearray(0x10 + (bank + 1) * 0x4000)
    start = 0x10 + bank * 0x4000 + (addr - 0x8000)
    for n in range(1, 0xAD):
        nes[start + (n - 1) * 8:start + n * 8] = bytes((n * 7 + i * 13) & 0xFF for i in range(8))
    return bytes(nes)


class TitleMaskTests(unittest.TestCase):
    def test_dot_is_doubled_and_centred(self):
        # 글자 하나: 점은 x=1(왼쪽 1점 비움), 폭 3 → 상자 폭 10 에서 왼쪽 여백 3
        mask = box.title_mask(DotFont(), 'A', 10)
        self.assertEqual(len(mask), 16)
        self.assertEqual(mask[0], [0, 0, 0, 0, 1, 1, 0, 0, 0, 0])
        self.assertEqual(sum(map(sum, mask)), 2)

    def test_text_wider_than_the_box_is_rejected(self):
        with self.assertRaisesRegex(ValueError, '상자 안 2점을 넘음'):
            box.title_mask(DotFont(), 'A', 2)


class BoxPixelTests(unittest.TestCase):
    def setUp(self):
        self.nes = synthetic_nes()
        self.img, self.pal = box.box_pixels(self.nes, DotFont(), 'A')

    def test_size_and_palette_lines(self):
        self.assertEqual((len(self.img), len(self.img[0])), (box.BOX_H * 8, box.BOX_W * 8))
        self.assertEqual((len(self.pal), len(self.pal[0])), (box.BOX_H, box.BOX_W))
        for ty in range(box.BOX_H):
            for tx in range(box.BOX_W):
                edge = ty in (0, box.BOX_H - 1) or tx in (0, box.BOX_W - 1)
                self.assertEqual(self.pal[ty][tx], box.PAL_BORDER if edge else box.PAL_TEXT)

    def test_border_and_fill_tiles_come_from_the_fc_tiles(self):
        corner = box.fc_tile(self.nes, box.FC_BORDER['tl'])
        self.assertEqual([row[:8] for row in self.img[:8]], corner)
        right = box.fc_tile(self.nes, box.FC_BORDER['r'])
        self.assertEqual([row[-8:] for row in self.img[8 * 3:8 * 4]], right)
        bottom_right = box.fc_tile(self.nes, box.FC_BORDER['br'])
        self.assertEqual([row[-8:] for row in self.img[-8:]], bottom_right)
        fill = box.fc_tile(self.nes, box.FC_FILL)
        self.assertEqual([row[8 * 5:8 * 6] for row in self.img[8 * 4:8 * 5]], fill)

    def test_title_dot_is_white_with_a_black_shadow_below(self):
        # 마스크 폭 192, 점 폭 3 → 왼쪽 여백 94, 점은 95·96. 상자 안 글자 띠는 TEXT_ROW 행, 왼쪽 테두리 한 타일 뒤
        row, col = box.TEXT_ROW * 8, 8 + 95
        self.assertEqual(self.img[row][col:col + 3], [3, 3, 2])
        self.assertEqual(self.img[row + 1][col:col + 3], [0, 0, 2])

    def test_subtitle_adds_a_white_dot_band_below_the_box(self):
        img, pal = box.box_pixels(self.nes, DotFont(), 'A', 'B')
        self.assertEqual(len(img), box.rows('B') * 8)
        self.assertEqual(len(pal), box.rows('B'))
        band = (box.BOX_H + box.SUB_GAP) * 8
        self.assertEqual(sum(img[band]), 2)
        self.assertEqual(set(img[band]) - {0}, {1})
        self.assertEqual(box.rows(None), box.BOX_H)

    def test_box_data_shares_identical_tiles_and_numbers_them_from_the_canvas(self):
        tiles, maps = box.box_data(self.nes, DotFont(), ['A', ('A', 'B')])
        self.assertEqual([len(m) for m in maps], [box.BOX_W * box.BOX_H * 2, box.BOX_W * box.rows('B') * 2])
        words = [int.from_bytes(maps[0][i:i + 2], 'little') for i in range(0, len(maps[0]), 2)]
        indices = {w & 0x3FF for w in words}
        self.assertEqual(min(indices), box.CANVAS)
        self.assertEqual(len(tiles), 16 * len({*(w & 0x3FF for m in maps for w in
                                                 (int.from_bytes(m[i:i + 2], 'little') for i in range(0, len(m), 2)))}))
        # 안쪽 바탕 타일은 모두 같은 번호, 테두리 팔레트 비트는 PAL_BORDER
        self.assertEqual(words[0] >> 10 & 7, box.PAL_BORDER)
        self.assertEqual(words[box.BOX_W * 4 + 5] >> 10 & 7, box.PAL_TEXT)
        self.assertEqual(words[box.BOX_W * 4 + 5] & 0x3FF, words[box.BOX_W * 4 + 6] & 0x3FF)

    def test_too_many_distinct_tiles_overflow_the_canvas(self):
        with mock.patch.object(box, 'CANVAS_END', box.CANVAS + 3):
            with self.assertRaisesRegex(ValueError, '캔버스를 넘음'):
                box.box_data(self.nes, DotFont(), ['A'])


class PaletteTests(unittest.TestCase):
    def test_bgr555_packs_channels_with_rounding(self):
        self.assertEqual(box.bgr555((255, 255, 255)), bytes((0xFF, 0x7F)))
        self.assertEqual(box.bgr555((0, 0, 0)), bytes(2))
        # 금색 (234, 158, 34) → 28, 19, 4
        self.assertEqual(box.bgr555(box.GOLD), (4 << 10 | 19 << 5 | 28).to_bytes(2, 'little'))

    def test_palettes_hold_two_lines_with_transparent_first_colour(self):
        pal = box.palettes()
        self.assertEqual(len(pal), 16)
        self.assertEqual(pal[0:2], bytes(2))
        self.assertEqual(pal[2:4], box.bgr555(box.GOLD))
        self.assertEqual(pal[8:10], bytes(2))
        self.assertEqual(pal[10:12], box.bgr555(box.WHITE))
        self.assertEqual(pal[12:14], box.bgr555(box.BLUE))


class CodeBytesTests(unittest.TestCase):
    def test_little_endian(self):
        self.assertEqual(box.le(0x123456, 3), bytes((0x56, 0x34, 0x12)))

    def test_dma_vram_carries_word_source_bank_and_size(self):
        code = box.dma_vram(0x1234, 0x5F8000, 0x0200)
        self.assertIn(bytes((0xA2, 0x34, 0x12, 0x8E, 0x16, 0x21)), code)
        self.assertIn(bytes((0xA2, 0x00, 0x80, 0x8E, 0x72, 0x43)), code)
        self.assertIn(bytes((0xA9, 0x5F, 0x8D, 0x74, 0x43)), code)
        self.assertIn(bytes((0xA2, 0x00, 0x02, 0x8E, 0x75, 0x43)), code)
        self.assertEqual(code[-5:], bytes((0xA9, 0x80, 0x8D, 0x0B, 0x42)))

    def test_dma_cgram_starts_at_the_colour_index(self):
        code = box.dma_cgram(4, 0x5F9000, 16)
        self.assertEqual(code[:5], bytes((0xA9, 4, 0x8D, 0x21, 0x21)))
        self.assertIn(bytes((0xA2, 16, 0, 0x8E, 0x75, 0x43)), code)

    def test_fill_vram_writes_low_then_high_byte_ports(self):
        code = box.fill_vram(0x1000, 0x5F8100, 0x40)
        halves = [code[:len(code) // 2], code[len(code) // 2:]]
        self.assertIn(bytes((0xA9, 0x18, 0x8D, 0x71, 0x43)), halves[0])
        self.assertIn(bytes((0xA9, 0x19, 0x8D, 0x71, 0x43)), halves[1])
        self.assertIn(bytes((0xA2, 0x00, 0x81, 0x8E, 0x72, 0x43)), halves[0])
        self.assertIn(bytes((0xA2, 0x01, 0x81, 0x8E, 0x72, 0x43)), halves[1])

    def test_mvn_counts_size_minus_one_and_orders_banks_dst_first(self):
        self.assertEqual(box.mvn(0x5F8123, 0x7E5000, 0x100),
                         bytes((0xA2, 0x23, 0x81, 0xA0, 0x00, 0x50, 0xA9, 0xFF, 0x00, 0x54, 0x7E, 0x5F)))

    def test_wait_screen_switches(self):
        self.assertEqual(box.wait(7), bytes((0, 9, 7)))
        self.assertEqual(box.screen_off()[-5:], bytes((0xA9, 0x80, 0x8D, 0x00, 0x21)))
        self.assertEqual(box.screen_on(), bytes((0xAD, 0x1E, 0x00, 0x8D, 0x00, 0x42)))

    def test_map_rows_blanks_or_copies_each_row(self):
        blank = box.map_rows(lambda r: None, 2)
        self.assertEqual(blank.count(bytes((0xA9, 0x00, 0x2C))), 2)
        first = box.MAP_BUFFER + (box.BOX_ROW * 32 + box.BOX_COL) * 2
        self.assertIn(bytes((0x8F, *box.le(first, 3))), blank)
        copy = box.map_rows(lambda r: 0x5F8000 + r * 52, 2)
        self.assertEqual(copy.count(0x54.to_bytes(1, 'little') + bytes((0x7E, 0x5F))), 2)
        self.assertIn(bytes((0xA9, 51, 0)), copy)

    def test_wait_button_loops_back_on_itself(self):
        code = box.wait_button()
        self.assertEqual(code.count(bytes((0, 9, 1))), 3)
        for at in (i for i, b in enumerate(code) if b in (0xD0, 0xF0) and i + 1 < len(code) and code[i - 1] in (0xC0, 0xF0, 0xD0)):
            target = at + 2 + (code[at + 1] - 256 if code[at + 1] > 127 else code[at + 1])
            self.assertGreaterEqual(target, 0)
            self.assertLessEqual(target, len(code))

    def test_soft_reset_jumps_to_the_reset_vector(self):
        code = box.soft_reset()
        self.assertEqual(code[0], 0x78)
        self.assertEqual(code[-4:], bytes((0x5C, *box.le(box.RESET, 3))))

    def test_soft_boot_ends_in_the_driver_upload_and_acks_with_rtl(self):
        code = box.soft_boot()
        upload = bytes((0x28, 0x5C, *box.le(box.DRIVER_UPLOAD, 3)))
        self.assertTrue(code.endswith(upload))
        self.assertIn(bytes((0x68, 0x28, 0x6B)), code)
        self.assertIn(bytes((0xA9, box.DRIVER_RESTART, 0x8D, 0x41, 0x21)), code)
        self.assertEqual(box.boot_points((box.CHAPTER1,))['acked'] - box.boot_points((box.CHAPTER1,))['boot'],
                         code.index(bytes((0x68, 0x28, 0x6B))))

    def test_reveal_code_waits_for_the_song_only_when_asked(self):
        with_wait = box.reveal_code()
        without = box.reveal_code(song_wait=False)
        self.assertGreater(len(with_wait), len(without))
        self.assertIn(bytes((0xA2, *box.le(box.SONG_WAIT_MAX, 2))), with_wait)
        self.assertNotIn(bytes((0xA2, *box.le(box.SONG_WAIT_MAX, 2))), without)
        self.assertTrue(with_wait.startswith(box.ENTER) and with_wait.endswith(box.LEAVE))
        self.assertIn(bytes((0x22, 0x8F, 0xFE, 0x23)), without)


class LayoutTests(unittest.TestCase):
    def layout(self, scenes):
        tiles, maps = box.box_data(synthetic_nes(), DotFont(), [(s.title, s.subtitle) for s in scenes])
        return box.Layout(box.CODE_AT, scenes, tiles, maps, box.palettes()), tiles, maps

    def test_data_follows_the_code_in_the_blob(self):
        lay, tiles, maps = self.layout(box.GAME_SCENES)
        self.assertTrue(lay.blob.endswith(tiles))
        data_at = lay.boot_at - lay.base + len(box.soft_boot())
        self.assertEqual(lay.blob[data_at:data_at + 2], b'\x00\xff')
        self.assertEqual(lay.blob[data_at + 2:data_at + 2 + len(lay.pal)], lay.pal)
        self.assertEqual(lay.blob[data_at + 2 + len(lay.pal):][:len(maps[0])], maps[0])
        self.assertEqual(list(lay.box_at), [s.name for s in box.GAME_SCENES])
        self.assertEqual(sorted(lay.box_at.values()), list(lay.box_at.values()))

    def test_ending_scene_waits_for_a_button_and_resets(self):
        lay, _, _ = self.layout(box.GAME_SCENES)
        ending = lay.blob[lay.box_at['end'] - lay.base:lay.reveal_at - lay.base]
        self.assertIn(box.wait_button(), ending)
        self.assertTrue(ending.endswith(box.soft_reset()))
        title = lay.blob[lay.box_at['box'] - lay.base:lay.box_at['box2'] - lay.base]
        self.assertNotIn(box.wait_button(), title)
        self.assertTrue(title.endswith(box.LEAVE))

    def test_bank_overflow_is_rejected(self):
        with self.assertRaisesRegex(ValueError, '뱅크를 넘음'):
            box.Layout(0x5FFF00, (box.CHAPTER1,), bytes(0x200), [bytes(box.BOX_W * box.BOX_H * 2)], box.palettes())


class ApplyTests(unittest.TestCase):
    def rom(self):
        data = bytearray(0x300000)
        for addr, orig in ((box.START_AT, box.START_ORIG), (box.HOOK_AT, box.HOOK_ORIG),
                           (box.DRIVER_UPLOAD_CALL, box.DRIVER_UPLOAD_ORIG)):
            data[box.lorom(addr):box.lorom(addr) + len(orig)] = orig
        return bytes(data)

    def test_writes_put_jumps_at_the_three_sites_and_the_blob_at_the_code_bank(self):
        writes = box.writes(synthetic_nes(), DotFont())
        self.assertEqual([w[0] for w in writes], [box.START_AT, box.HOOK_AT, box.DRIVER_UPLOAD_CALL, box.CODE_AT])
        lay = box.Layout(box.CODE_AT, (box.CHAPTER1,), *box.box_data(synthetic_nes(), DotFont(), [(box.TITLE, None)]),
                         box.palettes())
        self.assertEqual(writes[0][1], bytes((0x22, *box.le(lay.start_at, 3))))
        self.assertEqual(writes[1][1], bytes((0x22, *box.le(lay.hook_at, 3), 0xEA)))
        self.assertEqual(writes[2][1], bytes((0x22, *box.le(lay.boot_at, 3))))
        self.assertEqual(writes[3][1], lay.blob)
        self.assertIsNone(writes[3][2])

    def test_apply_patches_a_clean_rom_and_leaves_the_rest(self):
        rom = self.rom()
        out = box.apply(rom, synthetic_nes(), DotFont())
        self.assertEqual(len(out), len(rom))
        self.assertEqual(out[box.lorom(box.START_AT)], 0x22)
        self.assertEqual(out[box.lorom(box.HOOK_AT) + 4], 0xEA)
        blob = box.writes(synthetic_nes(), DotFont())[3][1]
        self.assertEqual(out[box.lorom(box.CODE_AT):box.lorom(box.CODE_AT) + len(blob)], blob)
        changed = [i for i in range(len(rom)) if rom[i] != out[i]]
        self.assertLess(len(changed), len(blob) + 20)

    def test_changed_original_bytes_are_refused(self):
        rom = bytearray(self.rom())
        rom[box.lorom(box.HOOK_AT)] ^= 0xFF
        with self.assertRaisesRegex(SystemExit, '원래 바이트가 아님'):
            box.apply(bytes(rom), synthetic_nes(), DotFont())

    def test_occupied_code_area_is_refused(self):
        rom = bytearray(self.rom())
        rom[box.lorom(box.CODE_AT) + 5] = 1
        with self.assertRaisesRegex(SystemExit, '비어 있지 않은 자리'):
            box.apply(bytes(rom), synthetic_nes(), DotFont())

    def test_applying_twice_is_refused(self):
        once = box.apply(self.rom(), synthetic_nes(), DotFont())
        with self.assertRaises(SystemExit):
            box.apply(once, synthetic_nes(), DotFont())


class PreviewTests(unittest.TestCase):
    def test_preview_paints_the_box_at_its_screen_position_twice_as_big(self):
        from PIL import Image
        nes = synthetic_nes()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'box.png'
            box.preview(nes, DotFont(), out)
            image = Image.open(out).convert('RGB')
        self.assertEqual(image.size, (512, 448))
        img, pal = box.box_pixels(nes, DotFont())
        colors = {box.PAL_BORDER: [(0, 0, 0), box.GOLD, box.BLUE, box.BLUE],
                  box.PAL_TEXT: [(0, 0, 0), box.WHITE, box.BLUE, box.WHITE]}
        for y, x in ((0, 0), (0, 3), (7, 7), (20, 100)):
            expected = colors[pal[y // 8][x // 8]][img[y][x]]
            self.assertEqual(image.getpixel((2 * (box.BOX_COL * 8 + x), 2 * (box.BOX_ROW * 8 + y))), expected)
        self.assertEqual(image.getpixel((0, 0)), (0, 0, 0))

    def test_main_preview_writes_the_file_and_prints_its_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / 'dq4.nes').write_bytes(synthetic_nes())
            out = tmp / 'box.png'
            buf = io.StringIO()
            argv = ['dq4chapterbox.py', 'preview', '--dq4', str(tmp / 'dq4.nes'), '--out', str(out)]
            with mock.patch('sys.argv', argv), mock.patch('dq4menupatch.Font', lambda name: DotFont()), \
                    contextlib.redirect_stdout(buf):
                box.main()
            self.assertTrue(out.stat().st_size > 0)
        self.assertEqual(buf.getvalue().strip(), str(out))


@unittest.skipUnless(NES.exists() and os.environ.get('DQ4_GALMURI'), 'rom/dq4.nes 와 DQ4_GALMURI 가 있어야 함')
class BoxTests(unittest.TestCase):
    def setUp(self):
        import dq4menupatch
        self.nes = NES.read_bytes()
        self.font = dq4menupatch.Font('galmuri11')

    def test_border_tiles_have_no_shadow_plane(self):
        for n in box.FC_BORDER.values():
            self.assertTrue(all(v in (0, 1) for row in box.fc_tile(self.nes, n) for v in row), f'{n:02X}')

    def test_fill_is_blue(self):
        self.assertEqual({v for row in box.fc_tile(self.nes, box.FC_FILL) for v in row}, {2})

    def test_box_fits_canvas(self):
        # 서장과 1장 상자가 캔버스를 함께 쓴다
        tiles, maps = box.box_data(self.nes, self.font, [box.PROLOGUE.title, box.CHAPTER1.title])
        self.assertLessEqual(box.CANVAS + len(tiles) // 16, box.CANVAS_END)
        self.assertEqual([len(w) for w in maps], [box.BOX_W * box.BOX_H * 2] * 2)


if __name__ == '__main__':
    unittest.main()


class EndBoxTest(unittest.TestCase):
    def test_a_box_without_a_map_never_darkens_a_map(self):
        import dq4chapterbox as b
        mapless = b.Scene('end', None, None, 't')
        self.assertEqual(b.if_pending((b.CHAPTER1, mapless), b'T', b'O'), b.if_pending((b.CHAPTER1,), b'T', b'O'))
        self.assertIn('box2', b.entry_points((b.CHAPTER1, b.CHAPTER2)))

    def test_chapter2_waits_for_its_chapter_flag(self):
        # 첫머리 대기 깃발이 꺼져 있으면(1장에 걸어 들어온 때, 첫머리 뒤) 맵을 검게 불러오지 않는다: BEQ 로 다음 장면에
        import dq4chapterbox as b
        import dq4ch2event as e
        addr, mask = 0x7E2190 + e.OPENING[0], e.OPENING[1]
        code = b.if_pending((b.CHAPTER2,), b'T', b'O')
        check = bytes((0xAF, addr & 0xFF, addr >> 8 & 0xFF, addr >> 16, 0x29, mask, 0xF0))
        self.assertIn(check, code)
        self.assertEqual(b.CHAPTER2.since, (addr, mask))
        self.assertIsNone(b.CHAPTER2.flag)
        self.assertEqual(b.CHAPTER2.where, tuple(int(v, 16) for v in e.THRONE.split('/')))

