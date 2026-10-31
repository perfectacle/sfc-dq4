import unittest

from PIL import Image

import dq4leader as L
from dq4chapter1 import lorom
from w65816 import Cpu

TABLE = 0x2586D0


def machine(code):
    rom = bytearray(0x400000)
    at = L.cpu(L.HOOK_AT)
    rom[lorom(at):lorom(at) + len(code)] = code
    for g in range(0x100):
        rom[lorom(TABLE + g)] = g ^ 0x80
    return Cpu(bytes(rom), bytearray(0x20000)), at


class HookTests(unittest.TestCase):
    def setUp(self):
        self.code = L.hook([(0x70, 0x3C)], 0x71)

    def pick(self, picture, group, p=0x30):
        cpu, at = machine(self.code)
        cpu.wram[0xBC] = group
        cpu.x, cpu.p = picture, p
        cpu.jsl(at)
        return cpu

    def test_leader_pictures_follow_the_map_group(self):
        for picture in L.LEADER_PICTURES:
            self.assertEqual(self.pick(picture, 0x3C).a & 0xFF, 0x70)
            self.assertEqual(self.pick(picture, 0x36).a & 0xFF, 0x71)

    def test_other_pictures_read_the_table(self):
        for picture in (0x00, 0x14, 0x2C, 0x9A):
            self.assertEqual(self.pick(picture, 0x3C).a & 0xFF, picture ^ 0x80)

    def test_register_widths_come_back(self):
        # 03:D202 는 X 16비트(상위 0)로 부를 수 있다. PLP 가 폭을 되돌리고 X 는 그대로여야 한다
        cpu = self.pick(0x2B, 0x36, p=0x20)
        self.assertEqual(cpu.p & 0x30, 0x20)
        self.assertEqual(cpu.x, 0x2B)


class SheetTests(unittest.TestCase):
    def setUp(self):
        fr = {}
        for k, (name, _) in enumerate(L.ROWS):
            im = Image.new('RGBA', (22, 28), (40 * k + 20, 60, 90, 255))
            for y in range(20, 28):
                for x in range(4, 9):
                    im.putpixel((x, y), (200, 30, 30, 255))
            fr[name] = im
        self.pal = L.palette(fr)
        self.sheet = L.sheet(fr, self.pal)

    def cells(self, r, col):
        return [[self.sheet.getpixel((col * 16 + x, r * 24 + y)) for x in range(16)] for y in range(24)]

    def test_steps_change_only_the_legs(self):
        legs = L.BOTTOM - round(L.HEIGHT * 5 / 24)
        for r in range(4):
            a, b = self.cells(r, 0), self.cells(r, 1)
            self.assertEqual(a[:legs], b[:legs])
            self.assertNotEqual(a[legs:], b[legs:])

    def test_feet_stand_on_the_measured_line(self):
        for r in range(4):
            for col in (0, 1):
                rows = self.cells(r, col)
                self.assertFalse(any(rows[L.BOTTOM]) or any(rows[L.BOTTOM + 1]))
                self.assertTrue(any(rows[L.BOTTOM - L.HEIGHT]))

    def test_palette_fits_an_obj_line(self):
        self.assertLessEqual(len(self.pal), 15)
        self.assertLessEqual(max(self.sheet.get_flattened_data()), len(self.pal))


if __name__ == '__main__':
    unittest.main()
