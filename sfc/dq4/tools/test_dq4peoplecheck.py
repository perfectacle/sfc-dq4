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


class SceneOkTests(unittest.TestCase):
    def test_needs_the_map_and_at_least_one_passing_slot(self):
        good, bad = {'ok': True}, {'ok': False}
        self.assertTrue(C.scene_ok('36/00', '36/00', [good]))
        self.assertFalse(C.scene_ok('36/00', '36/00', []))
        self.assertFalse(C.scene_ok('36/00', '36/00', [good, bad]))
        self.assertFalse(C.scene_ok('37/00', '36/00', [good]))


class EventMapTests(unittest.TestCase):
    def test_every_event_group_has_a_map(self):
        groups = {group for _, _, _, group, _ in C.dq4people.EVENT_PEOPLE}
        self.assertEqual({int(m[:2], 16) for m in C.EVENT_MAPS}, groups)

    def test_spots_hold_every_picture_of_a_map_on_screen(self):
        seen, per_map = {}, {}
        for _, _, _, group, _ in C.dq4people.EVENT_PEOPLE:             # event_rom 처럼 그룹의 맵에 차례로 나눔
            maps = [m for m in C.EVENT_MAPS if int(m[:2], 16) == group]
            m = maps[seen.get(group, 0) % len(maps)]
            seen[group] = seen.get(group, 0) + 1
            per_map[m] = per_map.get(m, 0) + 1
        for m, n in per_map.items():
            self.assertLessEqual(n, len(C.EVENT_SPOTS_AT.get(m, C.EVENT_SPOTS)), m)
        for spots in (C.EVENT_SPOTS, *C.EVENT_SPOTS_AT.values()):
            self.assertEqual(len(set(spots)), len(spots))
            self.assertNotIn((0, 0), spots)                             # 주인공 칸에 겹치지 않음
            for dx, dy in spots:                                        # 화면 16×14칸, 주인공이 가운데쯤
                self.assertLessEqual(abs(dx), 7)
                self.assertLessEqual(abs(dy), 6)


class ShownTests(unittest.TestCase):
    def test_counts_on_screen_sprites_in_the_tile_range(self):
        oam = bytearray(544)
        for i in range(128):
            oam[i * 4 + 1] = 0xF0                                        # 화면 밖(세로 240)
        oam[0:4] = bytes((40, 100, 0xB8, 0x30))                          # 타일 B8, 보임
        oam[4:8] = bytes((48, 230, 0xB9, 0x30))                          # 세로 230 은 화면 밖
        oam[8:12] = bytes((56, 100, 0x10, 0x31))                         # 타일 110(이름 표 bit)
        oam[12:16] = bytes((0, 100, 0xBA, 0x30))
        oam[512] = 0x01 << 6                                             # 3번의 x bit8 → x = -256
        oam[16:20] = bytes((64, 100, 0xBB, 0x04))                        # 우선순위 0: 나무 밑에 가려짐
        self.assertEqual(C.shown(oam, 0xB0, 16), 1)
        self.assertEqual(C.shown(oam, 0x110, 1), 1)
        self.assertEqual(C.shown(oam, 0x100, 16), 0)
