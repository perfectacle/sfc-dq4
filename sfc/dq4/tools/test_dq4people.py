import unittest
from collections import Counter

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

    def test_register_widths_come_back(self):
        # 03:D202 는 X 16비트(상위 0)로 부를 수 있다. PLP 가 폭을 되돌리고 X 는 그대로여야 한다
        cpu = run(0x9B, 0x36, p=0x20)
        self.assertEqual(cpu.p & 0x30, 0x20)
        self.assertEqual(cpu.x, 0x9B)


def body(color=(200, 30, 30, 255)):
    c = Image.new('RGBA', (16, 24))
    for y in range(P.BOTTOM - 17, P.BOTTOM):
        for x in range(3, 13):
            c.putpixel((x, y), (60, 90, 120, 255) if y < P.BOTTOM - 5 else color)
    return c


class SheetTests(unittest.TestCase):
    def test_steps_change_only_the_legs(self):
        for name in ('down', 'left', 'right', 'up'):
            cells = [body(), body()]
            P.step(cells, name, 17)
            a, b = (list(c.get_flattened_data()) for c in cells)
            top = (P.BOTTOM - 5) * 16
            self.assertEqual(a[:top], b[:top], name)
            self.assertNotEqual(a[top:], b[top:], name)
            self.assertFalse(any(p[3] for p in a[P.BOTTOM * 16:]), name)

    def test_overlap_sheet_keeps_head_and_bodies(self):
        cells = {name: [body(), body((30, 200, 30, 255))] for name, _ in P.ROWS8}
        pal = [(60, 90, 120), (200, 30, 30), (30, 200, 30)]
        im = P.index_image(cells, pal, 'overlap')
        self.assertEqual(im.size, (48, 64))
        # 몸 열은 프레임의 8~23행이라 몸 0 과 몸 1 의 아랫줄(발) 색이 다르다
        self.assertEqual(im.getpixel((16 + 5, 16 - 3)), 2)
        self.assertEqual(im.getpixel((32 + 5, 16 - 3)), 3)

    def test_reduce_keeps_the_most_used_colors(self):
        hist = Counter({(k * 10, 0, 0): 100 - k for k in range(20)})
        pal = P.reduce(hist)
        self.assertEqual(len(pal), 15)
        self.assertIn((0, 0, 0), pal)


if __name__ == '__main__':
    unittest.main()
