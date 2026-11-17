"""The shop and inn key hooks run on the w65816 interpreter over a blank ROM whose return points only RTS."""

import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS.parents[1] / "dq5" / "tools"))

import dq4shopkey as hook  # noqa: E402
from w65816 import Cpu  # noqa: E402

AT = 0x3CFC00
ROWS = [(0x36, 0, 2, 0x60), (0x36, 3, 5, 0x61), (0x37, 0, 0x1F, 0x62)]


ONE_SHOT_AT = 0x7E1F00


def rom_with_hooks(one_shot_at=None):
    rom = bytearray(0x200000)

    def put(addr, data):
        at = (addr >> 16 & 0x7F) << 15 | addr & 0x7FFF
        rom[at:at + len(data)] = data

    for w in hook.writes(AT, ROWS, one_shot_at):
        bank, addr = w["at"].split(":")
        put(int(bank, 16) << 16 | int(addr, 16), bytes.fromhex(w["hex"]))
    # What follows each original pair (06:DC3C JSR $DFBA, 06:F57A the price loop) only returns here.
    put(hook.SHOP_SITE + len(hook.SHOP_ORIG), b"\x60")
    put(hook.INN_SITE + len(hook.INN_ORIG), b"\x60")
    return bytes(rom)


def original(m8, group, number, a):
    """$0F25, $0F26 and A after the original LDA $BC / STA $0F25."""
    if m8:
        return group, 0x77, (a & 0xFF00) | group
    return group, number, number << 8 | group


class ShopKeyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom = rom_with_hooks()

    def cpu(self, group, number, p):
        wram = bytearray(0x20000)
        wram[0xBC], wram[0xBD], wram[0x0F25], wram[0x0F26], wram[0x02] = group, number, 0x77, 0x77, 0x77
        cpu = Cpu(self.rom, wram)
        index = (0x34, 0x78) if p & 0x10 else (0x1234, 0x5678)
        cpu.pbr, cpu.dbr, cpu.p, cpu.a, (cpu.x, cpu.y) = 0x06, 0x7E, p, 0xAB00, index
        return cpu

    def shop(self, group, number, m8, x8=False):
        p = (0x20 if m8 else 0) | (0x10 if x8 else 0)
        cpu = self.cpu(group, number, p)
        index = (cpu.x, cpu.y)
        cpu.jsr(hook.SHOP_SITE, max_steps=2000)
        self.assertEqual((cpu.x, cpu.y, cpu.p & 0x30, cpu.s), (*index, p, 0x1FF))
        return cpu.wram[0x0F25], cpu.wram[0x0F26], cpu.a

    def inn(self, group, number):
        # 06:F574 SEP #$20 after REP #$30: 8-bit A, 16-bit X; DB is the inn table bank.
        cpu = self.cpu(group, number, 0x20)
        cpu.dbr = 0x3C
        cpu.jsr(hook.INN_SITE, max_steps=2000)
        self.assertEqual((cpu.x, cpu.y, cpu.p & 0x30, cpu.s), (0x1234, 0x5678, 0x20, 0x1FF))
        return cpu.wram[0x02], cpu.a

    def test_shop_key_of_the_map_range(self):
        for m8 in (True, False):
            for x8 in (True, False):
                with self.subTest(m8=m8, x8=x8):
                    self.assertEqual(self.shop(0x36, 0x02, m8, x8), original(m8, 0x60, 0x02, 0xAB00))
                    self.assertEqual(self.shop(0x36, 0x03, m8, x8), original(m8, 0x61, 0x03, 0xAB00))
                    self.assertEqual(self.shop(0x37, 0x1F, m8, x8), original(m8, 0x62, 0x1F, 0xAB00))

    def test_shop_map_bits_above_the_number_are_ignored_but_kept(self):
        # 2A:F397 keeps the map number in the low 5 bits; with 16-bit A the original stores $BD whole.
        self.assertEqual(self.shop(0x36, 0x23, False), original(False, 0x61, 0x23, 0xAB00))

    def test_shop_misses_keep_the_group(self):
        for m8 in (True, False):
            with self.subTest(m8=m8):
                self.assertEqual(self.shop(0x36, 0x06, m8), original(m8, 0x36, 0x06, 0xAB00))
                self.assertEqual(self.shop(0x03, 0x00, m8), original(m8, 0x03, 0x00, 0xAB00))

    def test_shop_flags_follow_the_load(self):
        cpu = self.cpu(0x00, 0x00, 0x30)
        cpu.jsr(hook.SHOP_SITE, max_steps=2000)
        self.assertEqual(cpu.p & 0x82, 0x02)
        cpu = self.cpu(0x36, 0x00, 0x30)
        cpu.jsr(hook.SHOP_SITE, max_steps=2000)
        self.assertEqual(cpu.p & 0x82, 0x00)

    def test_inn_key(self):
        self.assertEqual(self.inn(0x36, 0x04), (0x61, 0xAB61))
        self.assertEqual(self.inn(0x37, 0x00), (0x62, 0xAB62))
        self.assertEqual(self.inn(0x36, 0x06), (0x36, 0xAB36))
        self.assertEqual(self.inn(0x21, 0x00), (0x21, 0xAB21))

    def test_table_end_and_ranges(self):
        self.assertEqual(len(hook.table(ROWS)), len(ROWS) * hook.ROW_SIZE + 1)
        self.assertEqual(hook.table(ROWS)[-1], 0xFF)
        for bad in ([(0x36, 4, 2, 0x60)], [(0x36, 0, 0x20, 0x60)], [(0x36, 0, 0, 0x35)], [(0x36, 0, 0, 0x21)],
                    [(0x36, 0, 0, 0xFF)], [(0x36, 0, 0, 0x60), (0x37, 0, 0, 0x60)]):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                hook.table(bad)

    def test_overlapping_rows_and_high_groups_stop(self):
        with self.assertRaises(ValueError):
            hook.table([(0x40, 0, 3, 0x60), (0x40, 3, 5, 0x61)])
        hook.table([(0x40, 0, 2, 0x60), (0x40, 3, 5, 0x61), (0x41, 0, 5, 0x62)])
        with self.assertRaises(ValueError):
            hook.table([(0x60, 0, 0, 0x61)])

    def test_sites_keep_their_length(self):
        _, shop, inn = hook.writes(AT, ROWS, ONE_SHOT_AT)
        self.assertEqual(len(bytes.fromhex(shop["hex"])), len(hook.SHOP_ORIG))
        _, shop, inn = hook.writes(AT, ROWS)
        self.assertEqual(len(bytes.fromhex(shop["hex"])), len(hook.SHOP_ORIG))
        self.assertEqual(len(bytes.fromhex(inn["hex"])), len(hook.INN_ORIG))



class OneShotTest(unittest.TestCase):
    """한 번 쓰는 키: ONE_SHOT 값이면 그 키로 열고 바이트를 지운다. 다른 값은 건드리지 않는다."""

    @classmethod
    def setUpClass(cls):
        cls.rom = rom_with_hooks(ONE_SHOT_AT)

    def shop(self, one_shot, m8=True, group=0x36, number=0x04):
        wram = bytearray(0x20000)
        wram[0xBC], wram[0xBD], wram[0x0F25], wram[0x0F26] = group, number, 0x77, 0x77
        wram[ONE_SHOT_AT & 0xFFFF] = one_shot
        cpu = Cpu(self.rom, wram)
        p = 0x20 if m8 else 0
        cpu.pbr, cpu.dbr, cpu.p, cpu.a, (cpu.x, cpu.y) = 0x06, 0x7E, p, 0xAB00, (0x1234, 0x5678)
        cpu.jsr(hook.SHOP_SITE, max_steps=2000)
        self.assertEqual((cpu.x, cpu.y, cpu.p & 0x30, cpu.s), (0x1234, 0x5678, p, 0x1FF))
        return cpu.wram[0x0F25], cpu.wram[0x0F26], cpu.wram[ONE_SHOT_AT & 0xFFFF]

    def test_one_shot_key_is_taken_once(self):
        for key in hook.ONE_SHOT:
            with self.subTest(key=key):
                self.assertEqual(self.shop(key), (key, 0x77, 0))
                self.assertEqual(self.shop(key, m8=False), (key, 0x04, 0))

    def test_other_values_keep_the_map_key(self):
        for value in (0x00, 0x60, 0xEF, 0xF8, 0xFF):
            with self.subTest(value=value):
                self.assertEqual(self.shop(value), (0x61, 0x77, value))

    def test_inn_ignores_the_one_shot_key(self):
        wram = bytearray(0x20000)
        wram[0xBC], wram[0xBD], wram[ONE_SHOT_AT & 0xFFFF] = 0x36, 0x04, 0xF3
        cpu = Cpu(self.rom, wram)
        cpu.pbr, cpu.dbr, cpu.p, cpu.a, (cpu.x, cpu.y) = 0x06, 0x3C, 0x20, 0xAB00, (0x1234, 0x5678)
        cpu.jsr(hook.INN_SITE, max_steps=2000)
        self.assertEqual((cpu.wram[0x02], cpu.wram[ONE_SHOT_AT & 0xFFFF]), (0x61, 0xF3))

    def test_one_shot_keys_stay_above_assigned_keys(self):
        self.assertGreater(hook.ONE_SHOT.start, hook.KEY_LAST)
        self.assertEqual(hook.ONE_SHOT.start % len(hook.ONE_SHOT), 0)
        with self.assertRaises(ValueError):
            hook.table([(0x36, 0, 0, hook.ONE_SHOT.start)])


if __name__ == "__main__":
    unittest.main()
