"""맵 블록 → 타일·팔레트·통행과 지형 효과 표(모양 레코드·타일 중복 올리기·빈 칸 FC~FF·그늘·팔레트 고르기·
떨어지기·출구 순번)를 합성 PRG 로 검사한다."""
import unittest
from types import SimpleNamespace

import dq4block as b

PRG_SIZE = 32 * 0x4000
B08 = 0x08


def put(prg, bank, addr, data):
    o = bank * 0x4000 + (addr & 0x3FFF)
    prg[o:o + len(data)] = bytes(data)


def word(v):
    return [v & 0xFF, v >> 8]


def shape_prg():
    """08 뱅크의 블록 표(08:9000), 모양 레코드(08:A000), 타일 차이 표(08:B000), 모양 F·E 표."""
    prg = bytearray(PRG_SIZE)
    put(prg, B08, 0x80B3, word(0x9000))
    put(prg, B08, 0x8235, word(0xA000))
    put(prg, B08, 0x8229, word(0x0000) + word(0x1000))
    put(prg, B08, 0x8237, word(0xB000))
    put(prg, B08, 0x8225, word(0xB100))
    put(prg, B08, 0x8227, word(0xB200))
    put(prg, B08, 0xB000 + 2 * 3, [0x01, 0x0F, 0xFF])           # 모양 2: +1, +15, −1 타일
    put(prg, B08, 0xA000 + 3 * 1, [0x05, 0x20, 0x80])           # 레코드 1: 타일 05, 모양 2, 뱅크 0C
    put(prg, B08, 0xA000 + 3 * 2, [0x06, 0x20, 0x00])
    put(prg, B08, 0xA000 + 3 * 3, [0x05, 0x26, 0x01])           # 뱅크 0D, 번호 위 2비트 2
    put(prg, B08, 0xA000 + 3 * 4, [0x02, 0xF0, 0x08])           # 모양 F
    put(prg, B08, 0xB100 + 2 * 8, word(0x1234) + word(0x2345) + word(0x3456) + word(0x4567))
    put(prg, B08, 0xA000 + 3 * 5, [0x03, 0xE0, 0x09])           # 모양 E
    put(prg, B08, 0xB200 + 2 * 3, word(0x0800))
    put(prg, B08, 0xA000 + 3 * 0x105, [0x07, 0x20, 0x44])       # a 아래 3비트가 레코드 번호 위 바이트
    return prg


class ShapeTests(unittest.TestCase):
    def setUp(self):
        self.prg = shape_prg()

    def test_relative_tiles_use_signed_steps(self):
        self.assertEqual(b.shape(self.prg, 0x00, 0x01), (0x0C, [0x50, 0x60, 0x150, 0x140], 0x80))

    def test_bank_bit_and_high_tile_bits(self):
        bank, addrs, _ = b.shape(self.prg, 0x00, 0x03)
        self.assertEqual((bank, addrs[0]), (0x0D, 0x1000 + (0x205 << 4)))

    def test_form_f_reads_four_addresses(self):
        self.assertEqual(b.shape(self.prg, 0x00, 0x04), (0x0C, [0x1234, 0x2345, 0x3456, 0x4567], 0x08))

    def test_form_e_is_four_consecutive_tiles_in_1d(self):
        self.assertEqual(b.shape(self.prg, 0x00, 0x05), (0x1D, [0x0800, 0x0810, 0x0820, 0x0830], 0x09))

    def test_record_index_takes_low_bits_of_a(self):
        self.assertEqual(b.shape(self.prg, 0x01, 0x05)[2], 0x44)

    def test_entry_fields_and_empty(self):
        e = b.entry(self.prg, 0x59, 0x01)   # a = 010 11 001: 종류 2, 팔레트 3, 레코드 위 1
        self.assertEqual((e['pal'], e['kind']), (3, 2))
        self.assertIsNone(b.entry(self.prg, 0x07, 0x00))

    def test_swap_depends_on_chapter_and_flag(self):
        self.assertEqual(b.swap(0x00, 0x17, chapter=1), (0x00, 0x17))
        self.assertEqual(b.swap(0x00, 0x17, chapter=0), (0x00, 0x12))
        self.assertEqual(b.swap(0x00, 0x17, chapter=2), (0x00, 0x17))
        self.assertEqual(b.swap(0x00, 0x17, chapter=2, flag=0x10), (0x00, 0x12))
        self.assertEqual(b.swap(0x00, 0x16, chapter=0), (0x00, 0x16))

    def test_extra_pairs_select_two_bits_per_type(self):
        put(self.prg, B08, b.EXTRA_SEL + 1, [0b00_01_10_11])     # 종류 4·5·6·7 → 0·1·2·3
        put(self.prg, B08, b.EXTRA + 4 * 2, [1, 2, 3, 4])
        self.assertEqual(b.extra_pairs(self.prg, 6), [(1, 2), (3, 4)])
        self.assertEqual(b.extra_pairs(self.prg, 4), [(0, 0), (0, 0)])


class LoadTests(unittest.TestCase):
    def setUp(self):
        self.prg = prg = shape_prg()
        t = 1
        blocks = [(0x07, 0x00)] * 0x20
        blocks[0] = (0x00, 0x01)
        blocks[1] = (0x08, 0x02)        # 팔레트 1, 타일 둘이 블록 0 과 같은 주소
        blocks[3] = (0x20, 0x00)        # 구역 비트: 쓰이지 않아도 올린다
        blocks[4] = (0x00, 0x00)        # 구역·속성 없음: 쓰이지 않으면 빈 타일
        put(prg, B08, 0x9000 + 64 * t, [v for p in blocks for v in p])
        self.out = b.load(prg, t, used={0, 1})

    def test_shared_addresses_reuse_tile_numbers(self):
        tiles = self.out['tiles']
        self.assertEqual(tiles[0], [0x8D, 0x8E, 0x8F, 0x90])
        self.assertEqual(tiles[1], [0x8E, 0x91, 0x92, 0x8F])
        self.assertEqual(self.out['chr'][0x91], (0x0C, 0x70))

    def test_unused_plain_block_is_blank_and_area_block_is_loaded(self):
        self.assertEqual(self.out['tiles'][4], [0, 0, 0, 0])
        self.assertEqual(self.out['tiles'][3], [0x93] * 4)

    def test_first_free_slot_gets_spare_tiles(self):
        self.assertEqual(self.out['tiles'][2], [0xFC, 0xFD, 0xFE, 0xFF])
        self.assertEqual(self.out['pal'][2], (b.SPARE[0] >> 3) & 3)

    def test_field_loads_everything_without_spare(self):
        out = b.load(self.prg, 0)
        self.assertNotIn(0xFC, [t for ts in out['tiles'].values() for t in ts])
        self.assertNotIn(0x20, out['tiles'])
        self.assertEqual(out['tiles'][0x1F], [b.TILE0] * 4)   # 종류 0 의 정의는 모두 레코드 0


class ShadeTests(unittest.TestCase):
    def test_wall_above_floor_takes_shadow_variant(self):
        kind = {0x01: 1, 0x02: 0, 0x05: 5}
        buf = bytes([0x01, 0x01, 0x02, 0x01])   # 2×2: 왼쪽 위 아래가 바닥, 오른쪽 위 아래는 벽
        out = b.shade(buf, 2, 2, kind, outside=0x02, t=0x01)
        self.assertEqual(out, bytes([0x05, 0x01, 0x02, 0x05]))   # 맨 아래 줄은 바깥 블록과 견줌

    def test_other_area_below_depends_on_type(self):
        kind = {0x01: 1, 0x02: 0, 0x05: 5}
        buf = bytes([0x01, 0x22])
        self.assertEqual(b.shade(buf, 1, 2, kind, 0x01, t=0x10)[0], 0x05)
        self.assertEqual(b.shade(buf, 1, 2, kind, 0x01, t=0x01)[0], 0x01)    # 구역 0 이면 안 바꿈
        buf = bytes([0x21, 0x02])
        self.assertEqual(b.shade(buf, 1, 2, kind, 0x01, t=0x01)[0], 0x25)    # 구역은 그대로 두고 블록만


class PaletteTests(unittest.TestCase):
    def setUp(self):
        self.prg = prg = bytearray(PRG_SIZE)
        put(prg, 0x1E, 0xA2DB, [0x00, 0x20, 0x40, 0x60, 0x80, 0xA0, 0xC0, 0xE0])
        put(prg, 0x1E, 0xA2E3, bytes(range(12 * 9)))
        put(prg, 0x0E, 0xBBB1, [0x05, 0x80])
        put(prg, 0x0E, 0xBBD3, [0x80])
        put(prg, 0x0E, 0xBBC5, [0x09])
        put(prg, 0x0E, 0xBBE6 + 2 * 3, [0x01, 0x02])           # 종류 3: 낮 세트 1, 밤 2
        put(prg, 0x0E, 0xBBE6 + 2 * 9, [0x03, 0x03])
        for s, ns in ((1, [0, 1, 2, 3]), (2, [4, 4, 4, 4]), (3, [5, 5, 5, 5])):
            put(prg, 0x0E, 0xBC68 + 4 * s, ns)
        put(prg, 0x0E, 0xBD40, bytes(range(0x10, 0x10 + 3 * 6)))

    def test_field_by_clock(self):
        self.assertEqual(b.palette(self.prg, 0, clock=0x45), bytes(range(24, 36)))
        self.assertEqual(b.palette(self.prg, 0, clock=0x00), bytes(range(12)))
        self.assertEqual(b.palette(self.prg, 0, clock=0x00, field=3), bytes(range(96, 108)))

    def test_map_day_night(self):
        self.assertEqual(b.palette(self.prg, 3, g=1), bytes(range(0x10, 0x1C)))
        self.assertEqual(b.palette(self.prg, 3, g=1, clock=0x78), bytes([0x1C, 0x1D, 0x1E] * 4))

    def test_place_override_changes_type(self):
        self.assertEqual(b.palette(self.prg, 3, g=5, k=7), bytes([0x1F, 0x20, 0x21] * 4))


class SmallTableTests(unittest.TestCase):
    def setUp(self):
        self.prg = bytearray(PRG_SIZE)

    def test_anim_blocks_group_by_marked_entries(self):
        put(self.prg, 0x1D, b.ANIM_T, [0x81, 0x05, 0x82, 0xFF])
        put(self.prg, 0x1D, b.ANIM_BLK + 8, [0x0A, 0x0B, 0x0A])
        put(self.prg, 0x1D, b.ANIM_SRC, word(0x9000) + word(0) + word(0x9100))
        self.assertEqual(b.anim_blocks(self.prg, 5), {0x0A: [0x9000, 0x9100]})
        self.assertEqual(b.anim_blocks(self.prg, 7), {})

    def test_patch_props_for_listed_maps_and_field3(self):
        put(self.prg, B08, b.PATCH_G, [0x04, 0x04, 0x80])
        put(self.prg, B08, b.PATCH_K, [0x01, 0x02])
        put(self.prg, B08, b.PATCH_B, [0x03, 0x05])
        put(self.prg, B08, b.PATCH_V, [0x80, 0x81])
        prop = {}
        b.patch_props(self.prg, prop, 0x04, 0x02)
        self.assertEqual(prop, {0x05: 0x81})
        prop = {}
        b.patch_props(self.prg, prop, field=3)
        self.assertEqual(prop, {0x01: 0x80, 0x14: 0x00})
        prop = {}
        b.patch_props(self.prg, prop, field=1)
        self.assertEqual(prop, {})

    def test_terrain_effects(self):
        put(self.prg, 0x0F, b.CONVEYOR_PAD, [0x10, 0x80, 0x20, 0x40])
        put(self.prg, 0x0F, b.TERRAIN_VALUES, [0x08] + [0x08] * 10)
        put(self.prg, 0x1E, b.DOOR_LOCKS, [0x14, 0x15, 0x1C, 0x1D] + [0x30 + i for i in range(12)])
        self.assertEqual(b.terrain(self.prg, 0x02), {'walk': True, 'ship': False, 'effect': 'damage', 'hp': 15})
        self.assertEqual(b.terrain(self.prg, 0x12)['dir'], 'down')
        self.assertEqual(b.terrain(self.prg, 0x08)['effect'], 'exit')
        self.assertEqual(b.terrain(self.prg, 0x83), {'walk': False, 'ship': True, 'effect': 'water'})
        door = b.terrain(self.prg, 0x9C)['door']
        self.assertEqual(door, {'lock': 0, 'shape': 2, 'opens': 'beyond_2x2'})
        self.assertEqual(b.terrain(self.prg, 0xB5)['door']['lock'], 2)
        self.assertEqual(b.terrain(self.prg, 0xAB)['facing'], 'dresser')

    def test_fall_table_conditions_and_destinations(self):
        put(self.prg, 0x12, b.FALLS, word(0xA000))
        put(self.prg, 0x12, 0xA000, [0x10, 0x01, 0x82,                  # 그룹 10 순번 1 → 순번 2 같은 좌표
                                     0x11, 0x81,                         # 조건 붙음
                                     0xC2, 0x03, 0x21, 0x03, 0x45, 0x06,   # 사각형 (2,3) 2×3 → 순번 3 (5,6), 다음 조건 이어짐
                                     0x07, 0x08, 0x84,                   # 한 칸 (7,8) → 순번 4
                                     0xFF])
        t = b.fall_table(self.prg)
        self.assertEqual(len(t), 3)
        self.assertEqual(t[1]['when'], {'x': 2, 'y': 3, 'w': 2, 'h': 3})
        self.assertEqual(b.fall(self.prg, 0x10, 0x01, 9, 9), {'group': 0x10, 'index': 2, 'x': 9, 'y': 9})
        self.assertEqual(b.fall(self.prg, 0x11, 0x01, 3, 5), {'group': 0x11, 'index': 3, 'x': 5, 'y': 6})
        self.assertEqual(b.fall(self.prg, 0x11, 0x01, 4, 5)['field'], None)     # 사각형 밖
        self.assertEqual(b.fall(self.prg, 0x11, 0x01, 7, 8)['index'], 4)

    def test_fall_fallback_steps(self):
        put(self.prg, 0x12, b.FALLS, word(0xA000))
        put(self.prg, 0x12, 0xA000, [0xFF])
        self.assertEqual(b.fall(self.prg, 0x20, 0x00, 0, 0, d=0, mode=0), {'field': None, 'dx': 0, 'dy': -2})
        self.assertEqual(b.fall(self.prg, 0x20, 0x00, 0, 0, d=1, mode=1), {'field': None, 'dx': 1, 'dy': 0})
        self.assertEqual(b.fall(self.prg, 0x2E, 0x01, 0x0C, 0x02)['x'], 0x0A)

    def test_lifts_pots_signs(self):
        put(self.prg, 0x1E, b.LIFTS, [0x30] + word(0xA000) + [0xFF])
        put(self.prg, 0x1E, 0xA000, [0, 1, 2, 3, 1, 4, 5, 0xFF, 0xFF])
        self.assertEqual(b.lifts(self.prg)[0]['b'], {'index': 1, 'x': 4, 'y': 5, 'arg': 0xFF})
        put(self.prg, 0x1E, b.POTS, [1, 2, 3, 4, 5, 6, 7, 0xFF])
        self.assertEqual(b.pots(self.prg)[0]['flag'], 0x6279)
        put(self.prg, 0x1E, b.SIGNS, word(0xA100) + word(0xA110))
        put(self.prg, 0x1E, 0xA100, [1, 2, 0x00, 0xFF])
        put(self.prg, 0x1E, 0xA110, [3, 4, 0x55, 0xFF])
        put(self.prg, 0x1E, b.SIGN_CHAPTER, [0x10, 0x11, 0x12])
        self.assertEqual([s['msg'] for s in b.signs(self.prg)], [[0x310, 0x311, 0x312], [0x355]])


def fake_map(w, cells, prop):
    return SimpleNamespace(w=w, buf=bytes(cells), blocks={'prop': prop})


class ExitTests(unittest.TestCase):
    def setUp(self):
        self.prg = prg = bytearray(PRG_SIZE)
        put(prg, B08, b.EXIT_KINDS, word(0xA200))
        put(prg, B08, 0xA200, [0x08, 0x09, 0x00])
        put(prg, B08, b.EXIT_FIXED, [0xFF])
        put(prg, B08, b.EXIT_TABLE, word(0xA000))
        put(prg, B08, 0xA000, [0x03,
                               0x20, 0x01, 0x04,      # 순번 0, 칸 0: 그룹 4 순번 0 의 칸 1 로
                               0xE1, 0x00,            # 순번 0 의 마지막: 같은 그룹 순번 1 의 칸 0
                               0xFF,
                               0x04, 0xC0, 0x02, 0xFF,  # 그룹 4 순번 0: 필드에서 그룹 2 에 들어갈 때 자리로
                               0xFF])
        prop = {0x01: 0x08, 0x02: 0x09, 0x03: 0x00}
        self.maps = {
            (0x03, 0x00): fake_map(3, [0x01, 0x03, 0x02, 0x03, 0x22, 0x03], prop),   # 칸 셋(구역 비트 무시)
            (0x03, 0x01): fake_map(2, [0x03, 0x02], prop),
            (0x04, 0x00): fake_map(2, [0x01, 0x03, 0x03, 0x02], prop),
        }

    def test_exit_table_parses_kinds_and_sub_lists(self):
        t = b.exit_table(self.prg)
        self.assertEqual(t[0x03], [[{'kind': 'map', 'group': 0x04, 'index': 0, 'n': 1},
                                    {'kind': 'same', 'group': 0x03, 'index': 1, 'n': 0}]])
        self.assertEqual(t[0x04], [[{'kind': 'enter', 'group': 0x02}]])

    def test_exit_cells_row_order(self):
        self.assertEqual(b.exit_cells(self.prg, self.maps[0x03, 0x00]), [(0, 0, 0x08), (2, 0, 0x09), (1, 1, 0x09)])

    def test_links_resolve_cell_order_and_missing_record(self):
        out = b.exit_links(self.prg, 0x03, 0x00, maps=self.maps)
        self.assertEqual(out[0]['to'], {'group': 0x04, 'index': 0, 'n': 1, 'x': 1, 'y': 1, 'dir': 0x81})
        self.assertEqual(out[1]['to'], {'group': 0x03, 'index': 1, 'n': 0, 'x': 1, 'y': 0, 'dir': 0x81})
        self.assertEqual(out[2]['to'], {'group': 0x03, 'index': 0x1F, 'n': 0x04, 'invalid': True})
        self.assertEqual(b.exit_links(self.prg, 0x04, 0x00, maps=self.maps)[0]['to'], {'enter': 0x02})

    def test_exit_special_and_arrive_dir(self):
        self.assertEqual(b.exit_special(0x3D, 1, 2, flags=0x80), (2, 3))
        self.assertEqual(b.exit_special(0x45, 4, 4, flags=0x10), (6, 5))
        self.assertEqual(b.exit_special(0x19, 0, 1, night=True), (1, 1))
        self.assertEqual(b.exit_special(0x34, 3, 5), (2, 0))
        self.assertEqual(b.exit_special(0x34, 3, 5, flag6295=1), (3, 5))
        self.assertEqual(b.exit_arrive_dir(0x88), 0x83)
        self.assertIsNone(b.exit_arrive_dir(0x00))


class DoorTests(unittest.TestCase):
    def setUp(self):
        self.prg = prg = shape_prg()
        blocks = [(0x07, 0x00)] * 0x20
        blocks[2], blocks[3], blocks[4] = (0x00, 0x01), (0x00, 0x02), (0x00, 0x05)
        put(prg, B08, 0x9000 + 64 * 1, [v for p in blocks for v in p])
        put(prg, B08, b.DOOR_FLOORS, [0x02, 0x00, 0x01, 0x00, 0xFF, 0xFF])   # 레코드 002 가 001 보다 앞

    def fake(self, grid):
        return SimpleNamespace(t=1, cell=lambda x, y: grid.get((x, y), 0), blocks={'prop': {}})

    def test_floor_rank(self):
        self.assertEqual([b.door_floor_rank(self.prg, r) for r in (0x002, 0x001, 0x005)], [0, 1, 0xFF])

    def test_door_takes_better_ranked_floor(self):
        m = self.fake({(5, 5): 0x22, (5, 3): 0x23})     # 위 문 너머가 블록 3(레코드 002)
        self.assertEqual(b.door_open(self.prg, m, 5, 5, 0), (5, 4, 0x03))
        m = self.fake({(5, 5): 0x23, (7, 5): 0x24})     # 너머가 표에 없으면 선 칸
        self.assertEqual(b.door_open(self.prg, m, 5, 5, 1), (6, 5, 0x03))

    def test_2x2_door_picks_corner_and_beyond_cell(self):
        prop = {0x1C: 0x9C, 0x05: 0x00}
        grid = {(4, 3): 0x1C, (5, 3): 0x1C, (4, 4): 0x1C, (5, 4): 0x1C, (4, 2): 0x05}
        m = SimpleNamespace(cell=lambda x, y: grid.get((x, y), 0), blocks={'prop': prop})
        self.assertEqual(b.door_open_2x2(self.prg, m, 5, 5, 0), (4, 3, 0x05))   # 왼쪽 칸도 문이면 그 열부터
        grid[(6, 5)] = grid[(6, 6)] = grid[(7, 5)] = grid[(7, 6)] = 0x1C
        grid[(8, 5)] = 0x07                          # 문(6~7) 너머 한 칸
        self.assertEqual(b.door_open_2x2(self.prg, m, 5, 6, 1), (6, 5, 0x07))


class MarkTests(unittest.TestCase):
    def test_marks_assign_letters_by_value(self):
        self.assertEqual(b.marks({0x00, 0x80, 0x83, 0x81, 0x90, 0x05, 0x12}),
                         {0x00: '.', 0x05: '5', 0x12: 'I', 0x80: '#', 0x81: 'a', 0x83: '~', 0x90: 'b'})

    def test_kind_name_unknown(self):
        self.assertEqual(b.kind_name(0xFE), '막힘(뜻 모름)')

    def test_nes_rgb_is_triplet(self):
        self.assertEqual(len(b.nes_rgb(0x0F)), 3)


if __name__ == '__main__':
    unittest.main()
