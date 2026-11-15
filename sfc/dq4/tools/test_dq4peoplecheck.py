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


class FarMapTests(unittest.TestCase):
    def test_takes_the_first_entry_of_each_map_outside_the_near_groups(self):
        entries = [{'name': '40/01', 'day': {'x': 5, 'y': 9}, 'night': {'x': 1, 'y': 1}},
                   {'name': '40/01', 'fields': {'x': 7, 'y': 7}},
                   {'name': '45/09', 'fields': {'x': 3, 'y': 4}},
                   {'name': '36/00', 'fields': {'x': 3, 'y': 4}},      # 서장·1장 그룹은 MAPS 가 맡는다
                   {'name': '1B/00', 'fields': {'x': 3, 'y': 4}},      # DQ4 그룹이 아님
                   {'name': '숨은 목록', 'fields': {'x': 3, 'y': 4}}]
        self.assertEqual(C.far_maps(entries), {'40/01': (5, 11), '45/09': (3, 6)})


class SharedLineTests(unittest.TestCase):
    def cgram(self, lines):
        out = bytearray(0x200)
        for n, v in lines.items():
            out[0x100 + n * 32:0x120 + n * 32] = bytes([v]) * 32
        return bytes(out)

    def test_a_line_the_rom_covers_must_hold_the_rom_colours(self):
        want = self.cgram({0: 1, 3: 2})
        self.assertEqual(C.wrong_lines(want, self.cgram({0: 1, 3: 2, 2: 9})), [])   # 줄 2 는 롬이 덮지 않음
        self.assertEqual(C.wrong_lines(want, self.cgram({0: 1, 3: 7})), [3])

    def test_colour_zero_of_a_line_is_not_compared(self):
        want, got = bytearray(self.cgram({3: 2})), bytearray(self.cgram({3: 2}))
        got[0x160:0x162] = b'\xff\x7f'
        self.assertEqual(C.wrong_lines(bytes(want), bytes(got)), [])

    def oam(self, rows):
        out = bytearray(0x220)
        for i in range(128):
            out[i * 4 + 1] = 0xF0                                       # 화면 밖
        for i, (x, y, tile, line) in enumerate(rows):
            out[i * 4:i * 4 + 4] = bytes((x, y, tile & 0xFF, tile >> 8 | line << 1 | 0x20))
        return bytes(out)

    def test_counts_shared_line_tiles_outside_the_judged_slots(self):
        slots = [{'base': 0x90, 'tiles': '24/24'}, {'ok': False}]
        oam = self.oam([(10, 10, 0x90, 3), (10, 10, 0xA7, 3), (10, 10, 0xA8, 3), (10, 10, 0x1A8, 4),
                        (10, 10, 0x30, 6), (10, 0xF0, 0x30, 3)])
        self.assertEqual(C.foreign_oam(oam, slots), {3: 1, 4: 1})          # 일행 줄 6 과 화면 밖은 세지 않음
        self.assertEqual(C.foreign_oam(self.oam([(10, 10, 0x90, 3)]), slots), {})


class FieldClashTests(unittest.TestCase):
    def test_names_slots_on_the_lines_the_field_routine_overwrites(self):
        slots = [{'slot': 0, 'palette': '48/48 (6)'}, {'slot': 8, 'palette': '48/48 (3)'},
                 {'slot': 9, 'palette': '40/48 (4)'}, {'slot': 10, 'palette': '48/48 (2)'}, {'slot': 11, 'ok': False}]
        self.assertEqual(C.field_clash(slots), [8, 9])


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
