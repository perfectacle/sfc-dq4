import unittest

import dq4groupbuild
import dq4peoplecheck as C
from test_dq4people import swap_rom


class HookSetTests(unittest.TestCase):
    def test_runs_the_rom_hook_with_the_dumped_group(self):
        rom = bytes(swap_rom())
        wram = bytearray(0x20000)
        wram[0xBC] = 0x3C
        self.assertEqual(C.hook_set(rom, wram, 0x2B), 0x70)
        wram[0xBC] = 0x36
        self.assertEqual(C.hook_set(rom, wram, 0x2B), 0x71)
        self.assertEqual(C.hook_set(rom, wram, 0x03), 0x03 ^ 0x80)


class MapTests(unittest.TestCase):
    def test_maps_cover_the_prologue_and_chapter1_groups(self):
        groups = {g for g, maps in dq4groupbuild.LINKS.items() if not any(m.get('chapter') for m in maps)}
        self.assertEqual({int(m[:2], 16) for m in C.MAPS}, groups)

    def test_start_maps_have_a_hop(self):
        self.assertNotIn(C.HOP, C.STATE_MAP.values())
        self.assertIn(C.HOP, C.MAPS)
