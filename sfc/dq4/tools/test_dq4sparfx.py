"""칼 효과 뱅크 자료(머리·프레임 목록·레코드·타일)의 주소와 크기, 빈 자리 확인을 합성 프레임으로 검사한다."""
import shutil
import tempfile
import unittest
from pathlib import Path

from PIL import Image

import dq4sparfx as fx
from dq4chapterbox import BG3_CHR, CANVAS

ROW_BYTES = fx.COLS * 16
SIZE = (fx.CROP[2] - fx.CROP[0], fx.CROP[3] - fx.CROP[1])


def frame(rows=(), color=(255, 255, 255)):
    """타일 행마다 왼쪽 위 한 점만 칠한 그림."""
    img = Image.new('RGB', SIZE)
    for r in rows:
        img.putpixel((0, r * 8), color)
    return img


def write_frames(root, name, images):
    folder = Path(root) / fx.FX_DIR / name
    folder.mkdir(parents=True, exist_ok=True)
    for k, img in enumerate(images):
        img.save(folder / f'f{k:02d}.png')


def u16(data, at):
    return int.from_bytes(data[at:at + 2], 'little')


class SparBuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        # 303 은 프레임마다 다른 한 행, 끝 두 장은 비움. 311 은 늘 같은 그림(레코드를 나눠 써야 한다).
        self.moving = [frame([k % fx.ROWS]) for k in range(fx.FRAMES - 2)] + [frame(), frame()]
        write_frames(self.tmp.name, '303', self.moving)
        write_frames(self.tmp.name, '311', [frame([3, 4])] * fx.FRAMES)
        self.blob = fx.build(self.tmp.name)
        self.base = fx.BANK & 0xFFFF

    def offset(self, pointer):
        self.assertGreaterEqual(pointer, self.base)
        at = pointer - self.base
        self.assertLess(at, len(self.blob))
        return at

    def lists(self):
        return [[u16(self.blob, self.offset(u16(self.blob, 4 + 2 * i)) + 2 * k) for k in range(fx.FRAMES)]
                for i in range(len(fx.EFFECTS))]

    def record(self, pointer):
        at = self.offset(pointer)
        return [u16(self.blob, at + 2 * i) for i in range(4)]

    def test_head_points_at_back_to_back_frame_lists(self):
        self.assertEqual(self.blob[:4], fx.MAGIC)
        first = 4 + 2 * len(fx.EFFECTS)
        self.assertEqual(u16(self.blob, 4), self.base + first)
        self.assertEqual(u16(self.blob, 6), self.base + first + 2 * fx.FRAMES)

    def test_records_point_inside_the_blob_with_whole_rows(self):
        records_at = 4 + 2 * len(fx.EFFECTS) + 2 * fx.FRAMES * len(fx.EFFECTS)
        for keys in self.lists():
            for pointer in keys:
                self.assertEqual((pointer - self.base - records_at) % 8, 0)
                vram, data, size, palette = self.record(pointer)
                self.assertEqual(size % ROW_BYTES, 0)
                r0, rest = divmod((vram - BG3_CHR) // 8 - CANVAS, fx.COLS)
                self.assertEqual((rest, (vram - BG3_CHR) % 8), (0, 0))
                self.assertGreaterEqual(r0, 0)
                self.assertLessEqual(r0 + size // ROW_BYTES, fx.ROWS)
                self.assertLessEqual(self.offset(data) + size, len(self.blob))
                self.assertLessEqual(self.offset(palette) + 8, len(self.blob))
                self.assertEqual(self.blob[self.offset(palette):self.offset(palette) + 2], bytes(2))

    def test_first_frame_clears_every_row_then_only_lit_rows(self):
        for keys in self.lists():
            vram, _, size, _ = self.record(keys[0])
            self.assertEqual((vram, size), (BG3_CHR + CANVAS * 8, fx.ROWS * ROW_BYTES))
        def lit(k):
            # 목록 k 는 그림 f(k+LEAD) 를 올린다. 303 은 끝 두 장이 비었다
            j = min(k + fx.LEAD, fx.FRAMES - 1)
            return {j % fx.ROWS} if j < fx.FRAMES - 2 else set()

        keys = self.lists()[0]
        for k in range(1, fx.FRAMES):
            # 앞 그림에서 칠한 행도 함께 올려 지운다
            need = sorted(lit(k) | lit(k - 1)) or [0]
            vram, _, size, _ = self.record(keys[k])
            with self.subTest(k=k):
                self.assertEqual((vram - BG3_CHR) // 8 - CANVAS, need[0] * fx.COLS)
                self.assertEqual(size, (need[-1] - need[0] + 1) * ROW_BYTES)

    def test_lit_pixel_lands_in_the_tile_bitplanes(self):
        keys = self.lists()[0]
        # 목록 0 이 올리는 것은 f02(2행 칠함): 2행 첫 타일 첫 줄의 맨 왼쪽 비트
        _, data, _, _ = self.record(keys[0])
        at = self.offset(data) + 2 * ROW_BYTES
        self.assertEqual(self.blob[at] | self.blob[at + 1], 0x80)
        self.assertFalse(any(self.blob[self.offset(data):at]))

    def test_identical_frames_share_records(self):
        keys = self.lists()[1]
        self.assertEqual(len(set(keys[1:])), 1)
        self.assertNotEqual(keys[0], keys[1])

    def test_bank_overflow_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            # 프레임마다 다른 밝기로 칠해 팔레트·자료가 모두 달라지게 해 한 뱅크를 넘긴다
            for i, (name, _) in enumerate(fx.EFFECTS):
                images = []
                for k in range(fx.FRAMES):
                    img = Image.new('RGB', SIZE)
                    for y in range(SIZE[1]):
                        for x in range(SIZE[0]):
                            img.putpixel((x, y), ((x * 7 + y * 13 + k * 31 + i) % 200 + 40,) * 3)
                    images.append(img)
                write_frames(root, name, images)
            # 넘친 자료의 주소가 16비트를 넘으면 크기 검사 전에 주소 인코딩에서 멈춘다. 어느 쪽이든 쓰지 않아야 한다
            with self.assertRaises((ValueError, OverflowError)):
                fx.build(root)


class SparApplyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.base = self.tmp / 'in.sfc'
        self.base.write_bytes(bytes(0x300000))
        self.at = (fx.BANK >> 16) * 0x8000 + (fx.BANK & 0x7FFF)

    def test_missing_frames_keep_the_rom(self):
        out = self.tmp / 'out.sfc'
        fx.apply(self.base, self.tmp / 'assets', out)
        self.assertEqual(out.read_bytes(), self.base.read_bytes())

    def test_blob_goes_to_the_bank_file_offset_and_needs_empty_space(self):
        for name, _ in fx.EFFECTS:
            write_frames(self.tmp / 'assets', name, [frame([1])] * fx.FRAMES)
        out = self.tmp / 'out.sfc'
        fx.apply(self.base, self.tmp / 'assets', out)
        blob = fx.build(self.tmp / 'assets')
        data = out.read_bytes()
        self.assertEqual(data[self.at:self.at + len(blob)], blob)
        self.assertFalse(any(data[:self.at]) or any(data[self.at + len(blob):]))
        dirty = bytearray(self.base.read_bytes())
        dirty[self.at + len(blob) - 1] = 1
        self.base.write_bytes(dirty)
        with self.assertRaises(SystemExit):
            fx.apply(self.base, self.tmp / 'assets', out)


if __name__ == '__main__':
    unittest.main()
