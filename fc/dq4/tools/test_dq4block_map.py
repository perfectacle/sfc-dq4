"""블록 모듈의 Map·화면 그리기·통행/지형 표시·출구 연결·JSON 내보내기·명령줄을 합성 롬으로 검사한다.
맵 하나(4×2, 블록 0 은 벽, 블록 1 은 계단)와 필드 표를 한 롬에 얹는다."""
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from PIL import Image

import dq4block as b
import dq4map
from test_dq4block import B08, PRG_SIZE, put, shape_prg, word
from test_dq4field import field_prg
from test_dq4map import Writer, end

CHR_BANK = 0x0C


def ines(prg):
    return b'NES\x1a' + bytes((len(prg) // 0x4000, 0, 0x10, 0)) + bytes(8) + bytes(prg)


def overlay(dst, src):
    for i, v in enumerate(src):
        if v:
            dst[i] = v


def world_prg(code=0x01):
    """맵 00/00: 4×2 = 0 0 0 0 / 0 1 0 0, 바깥 블록 1. 블록 0 = 벽(80), 블록 1 = 계단(08)."""
    prg = field_prg()
    overlay(prg, shape_prg())
    blocks = [(0x07, 0x00)] * 0x20
    blocks[0], blocks[1] = (0x00, 0x01), (0x08, 0x02)
    put(prg, B08, 0x9000 + 64, [v for p in blocks for v in p])
    put(prg, B08, 0xA000 + 3 * 2, [0x06, 0x20, 0x08])          # 블록 1 을 계단으로
    put(prg, *dq4map.GROUPS, [0x00, 0xA0, 0xFF, 0xFF])
    put(prg, 0x17, 0xA000, [code, 0x00, 0x90, 0xFF])
    w = Writer()(0, 2)(0, 2)(1, 2)(3, 2)(5, 3)
    end(w, 2)(0, 2)
    put(prg, 0x09, 0x9000, [4, 2, 0x01] + list(w.bytes()))
    put(prg, 0x1D, b.ANIM_T, [0xFF])
    put(prg, B08, b.PATCH_G, [0x80])
    put(prg, 0x0E, 0xBBB1, [0x80])
    put(prg, 0x0E, 0xBBE6 + 2, [0x01, 0x01])
    put(prg, 0x0E, 0xBC68 + 4, [0, 0, 0, 0])
    put(prg, 0x0E, 0xBD40, [0x16, 0x27, 0x30])
    put(prg, 0x0F, b.TERRAIN_VALUES, [0x08])
    put(prg, 0x1E, b.DOOR_LOCKS, [0x14, 0x15, 0x1C, 0x1D] + [0x30 + i for i in range(12)])
    put(prg, B08, b.EXIT_KINDS, word(0xA800))
    put(prg, B08, 0xA800, [0x08, 0x00])
    put(prg, B08, b.EXIT_FIXED, [0xFF])
    put(prg, B08, b.EXIT_TABLE, word(0xA900))
    put(prg, B08, 0xA900, [0x00, 0x80, 0xFF, 0xFF])           # 그룹 0 순번 0: 첫 출구 칸은 필드로
    put(prg, *b.dq4field.ARRIVE_PTR, word(0xAA00))
    put(prg, B08, 0xAA00, [0x00, 0x22, 5, 6, 0, 0xFF])
    put(prg, *b.dq4field.ENTRANCE_PTR, word(0x9100))
    put(prg, 0x0E, 0x9100, [0x00, 0x20, 0x21, 0xFF])
    put(prg, 0x12, b.FALLS, word(0xA000))
    put(prg, 0x12, 0xA000, [0xFF])
    put(prg, 0x1E, b.LIFTS, [0xFF])
    put(prg, 0x1E, b.POTS, [0xFF])
    put(prg, 0x1E, b.SIGNS, word(0xA100) + word(0xA110))
    put(prg, 0x1E, 0xA100, [0xFF])
    put(prg, 0x1E, 0xA110, [0xFF])
    for a in (0x50, 0x60, 0x70, 0x140, 0x150, 0x160):
        put(prg, CHR_BANK, a, [a & 0xFF] * 16)
    return prg


class MapStateTests(unittest.TestCase):
    def setUp(self):
        self.prg = world_prg()
        self.m = b.Map(self.prg, 0, 0)

    def test_map_header_and_cells(self):
        m = self.m
        self.assertEqual((m.t, m.w, m.h, m.outside, m.alt), (1, 4, 2, 1, 0))
        self.assertEqual(m.raw, bytes([0, 0, 0, 0, 0, 1, 0, 0]))
        self.assertEqual([m.cell(x, 1) for x in range(4)], [0, 1, 0, 0])
        self.assertEqual(m.cell(-1, 0), 1)          # 맵 밖은 바깥 블록
        self.assertEqual(m.cell(0, 5), 1)

    def test_passable_follows_block_property_bit7(self):
        self.assertFalse(self.m.passable(0, 0))
        self.assertTrue(self.m.passable(1, 1))
        self.assertTrue(self.m.passable(9, 9))      # 바깥 블록은 계단

    def test_block_other_area_is_20_or_21_and_mode4_shows_outside(self):
        m = self.m
        self.assertEqual(m.block(1, 1), 1)
        self.assertEqual(m.block(1, 1, area=0x20), 0x21)
        self.assertEqual(m.block(-1, 0, area=0x20), 0x21)
        self.assertEqual(m.block(-1, 0, area=0x20, mode=4), 1)
        self.assertEqual(m.tiles(1), [0x8E, 0x91, 0x92, 0x8F])
        self.assertEqual(m.tiles(0x1F), [0, 0, 0, 0])

    def test_stipple_picks_alt_outside_block(self):
        prg = world_prg(code=0x81)
        put(prg, B08, b.OUTSIDE_ALT + 1, [0x02])
        put(prg, 0x0F, b.STIPPLE_X, [0x01] * 8)
        put(prg, 0x0F, b.STIPPLE_Y, [0x02] * 8)       # 01 & 02 == 0 이라 늘 alt
        m = b.Map(prg, 0, 0)
        self.assertEqual((m.code, m.t, m.alt), (0x81, 1, 2))
        self.assertEqual(m.cell(-1, 0), 2)
        put(prg, 0x0F, b.STIPPLE_Y, [0x01] * 8)       # 01 & 01 != 0 이라 바깥 블록
        self.assertEqual(b.Map(prg, 0, 0).cell(-1, 0), 1)

    def test_field_cells_and_block_three_rule(self):
        m = b.Map(self.prg, field=0)
        self.assertEqual((m.t, m.buf, m.g), (0, None, None))
        self.assertEqual((m.w, m.h), (253, 2))
        self.assertEqual(m.cell(3, 1), 0)              # 줄 1 은 높이 안이라도 좌표 −3 이 음수면 0
        f3 = object.__new__(b.Map)
        f3.buf, f3.f = None, 3
        f3.field, f3.w, f3.h = [[0, 1], [1, 2]], 2, 2
        f3.blocks = {'prop': {}}
        self.assertEqual(f3.block(0, 0), 0)            # 좌표 −3 이라 범위 밖
        f3.field = [[0] * 4 + [1, 2]] * 5
        f3.w = f3.h = 5
        self.assertEqual(f3.cell(4, 3), 1)
        self.assertEqual(f3.block(4, 3), 0x18)         # 필드 3 의 블록 01
        self.assertEqual(f3.block(5, 3), 2)

    def test_used_blocks(self):
        self.assertEqual(b.used_blocks(bytes([0x21, 0x03]), 0x05), {1, 3, 5})


class ScreenTests(unittest.TestCase):
    def setUp(self):
        self.m = b.Map(world_prg(), 0, 0)

    def test_screen_puts_four_tiles_per_block(self):
        nt, pal = b.screen(self.m, 0, 0, 0, 0, cols=4, rows=2)
        self.assertEqual([nt[(c, r)] for r in (0, 1) for c in (0, 1)], [0x8D, 0x8E, 0x8F, 0x90])
        self.assertEqual([nt[(c, r)] for r in (2, 3) for c in (2, 3)], [0x8E, 0x91, 0x92, 0x8F])
        self.assertEqual((pal[(0, 0)], pal[(2, 2)]), (0, 1))
        self.assertEqual(len(nt), 4 * 2 * 4)

    def test_scroll_shifts_and_wraps_columns(self):
        nt, _ = b.screen(self.m, 0, 0, 8, 0, cols=1, rows=1)
        self.assertEqual({k: v for k, v in nt.items()}, {(1, 0): 0x8D, (2, 0): 0x8E, (1, 1): 0x8F, (2, 1): 0x90})
        nt, _ = b.screen(self.m, 0, 0, 31 * 8, 0, cols=1, rows=1)
        self.assertIn((32, 0), nt)

    def test_nt_helpers_read_two_nametables(self):
        nt = bytearray(0x800)
        nt[0x400 + 3 * 32 + 5] = 0x77
        self.assertEqual(b.nt_read(nt, 37, 3), 0x77)
        nt[0x3C0 + 8 + 1] = 0b11_10_01_00
        self.assertEqual([b.nt_pal(nt, c, r) for r in (4, 6) for c in (4, 6)], [0, 1, 2, 3])


class RenderTests(unittest.TestCase):
    def test_png_size_and_quadrant_colours(self):
        m = b.Map(world_prg(), 0, 0)
        prg = bytearray(m.prg)
        put(prg, CHR_BANK, 0x50, [0xFF] * 16)             # 블록 0 왼쪽 위 타일(8D)은 색 3
        put(prg, CHR_BANK, 0x60, [0x00] * 16)
        m.prg = prg
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'm.png')
            b.render_png(m, p)
            im = Image.open(p).convert('RGB')
            self.assertEqual(im.size, (64, 32))
            self.assertEqual(im.getpixel((1, 1)), (255, 255, 255))      # 팔레트 색 3 = 30
            self.assertEqual(im.getpixel((9, 1)), (0, 0, 0))            # 색 0 = 0F

    def test_nes_rgb_shapes(self):
        self.assertEqual(b.nes_rgb(0x0F), (0, 0, 0))
        self.assertEqual(b.nes_rgb(0x30), (255, 255, 255))
        self.assertEqual(b.nes_rgb(0x0D), (0, 0, 0))
        self.assertEqual(b.nes_rgb(0x2D), (79, 79, 79))
        self.assertEqual(b.nes_rgb(0x00), (102, 102, 102))
        r, g, bl = b.nes_rgb(0x11)
        self.assertGreater(bl, r)                                  # 파랑 계열


class ShowTests(unittest.TestCase):
    def setUp(self):
        self.prg = world_prg()
        self.m = b.Map(self.prg, 0, 0)

    def capture(self, fn, *a, **k):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            fn(*a, **k)
        return out.getvalue().splitlines()

    def test_show_pass_grid_and_legend(self):
        self.assertEqual(self.capture(b.show_pass, self.m), [
            '# 크기 4x2, 맵 종류 01, 바깥 블록 01',
            '    0000',
            '    0123',
            '00  ####',
            '01  #8##',
            '# 속성: 8=08 계단, #=80 벽',
        ])

    def test_show_nt_two_lines_per_row(self):
        self.assertEqual(self.capture(b.show_nt, self.m), [
            '8D 8E 8D 8E 8D 8E 8D 8E', '8F 90 8F 90 8F 90 8F 90',
            '8D 8E 8E 91 8D 8E 8D 8E', '8F 90 92 8F 8F 90 8F 90'])

    def test_hx_formats_nested_values(self):
        self.assertEqual(b.hx({'a': [1, 255], 'b': None, 'c': True, 'd': 'x'}), '{a: [01, FF], b: None, c: True, d: x}')

    def test_show_effects_counts_and_meaning(self):
        self.assertEqual(self.capture(b.show_effects, self.prg, 0, 0), [
            '08    1칸 {walk: True, ship: False, effect: exit}',
            '80    7칸 {walk: False, ship: False}'])

    def test_show_effects_lists_fall_destinations(self):
        prg = world_prg()
        put(prg, B08, 0xA000 + 3 * 2, [0x06, 0x20, 0x05])   # 블록 1 을 떨어지는 칸으로
        out = self.capture(b.show_effects, prg, 0, 0)
        self.assertEqual(out[0], '05    1칸 {walk: True, ship: False, effect: fall}')
        self.assertEqual(out[1], '   (01,01) → {field: None, dx: 00, dy: 01}')

    def test_show_links_destination_forms(self):
        self.assertEqual(self.capture(b.show_links, self.prg), ['00/00 (01,01) 08 #0 → 필드 1 (20,21)'])
        self.assertEqual(self.capture(b.show_links, self.prg, 0, 0), ['00/00 (01,01) 08 #0 → 필드 1 (20,21)'])
        self.assertEqual(self.capture(b.show_links, self.prg, 9, 9), [])

    def test_show_tables_sections(self):
        out = self.capture(b.show_tables, self.prg)
        self.assertEqual(out[0], '# 속성 값')
        self.assertIn('08 {walk: True, ship: False, effect: exit}', out)
        self.assertIn('80 {walk: False, ship: False}', out)
        heads = [ln for ln in out if ln.startswith('# ')]
        self.assertEqual(heads, ['# 속성 값', '# 떨어지는 칸 표(12:$B6DD)', '# 리프트(1E:$894A)', '# 리프트 사각형(1E:$8A24)',
                                 '# タンス·つぼ(1E:$BC7A)', '# 팻말(1E:$BB52)'])

    def test_show_props_table_and_per_map(self):
        out = self.capture(b.show_props, self.prg)
        self.assertEqual(out[0], '속성 | 뜻 | 맵 수 | 칸 수 | 예(맵:블록)')
        self.assertIn('08 | 계단 | 1 | 1 | 00/00:01', out)
        self.assertIn('80 | 벽 | 1 | 7 | 00/00:00', out)
        out = self.capture(b.show_props, self.prg, True)
        self.assertEqual(out[0], '00/00 종류 01: 08=01 80=00')
        self.assertEqual(len([ln for ln in out if ' 종류 ' in ln]), 4)    # 맵 하나 + 필드 셋

    def test_map_props_counts_cells_by_block(self):
        self.assertEqual(b.map_props(self.m), {0x80: {0: 7}, 0x08: {1: 1}})


class ExportTests(unittest.TestCase):
    def test_json_has_maps_fields_and_tables(self):
        prg = world_prg()
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'o.json')
            data = b.export(prg, p)
            self.assertEqual(json.loads(Path(p).read_text()), json.loads(json.dumps(data)))
        mp = data['maps'][0]
        self.assertEqual((mp['group'], mp['index'], mp['type'], mp['w'], mp['h'], mp['outside']), (0, 0, 1, 4, 2, 1))
        self.assertEqual(mp['cells'], ['00000000', '00010000'])
        self.assertEqual(mp['props'][:4], ['80', '08', '00', None])     # 블록 2 는 빈 칸에 넣는 정의
        self.assertEqual(mp['falls'], [])
        self.assertEqual(mp['exits'][0]['to'], {'field': 1, 'group': 0, 'x': 0x20, 'y': 0x21})
        self.assertEqual([f['field'] for f in data['fields']], [0, 1, 3])
        self.assertEqual(sorted(data['effects']), ['00', '08', '80'])
        self.assertEqual(data['keys'], [0, 0, 0])
        self.assertEqual(data['exit_kinds'], [0x08])
        self.assertEqual(data['exit_table'], {'00': [[{'kind': 'field'}]]})

    def test_signs_point_to_cells_with_sign_property(self):
        prg = world_prg()
        put(prg, B08, 0xA000 + 3 * 2, [0x06, 0x20, 0xA8])      # 블록 1 을 팻말(A8)로
        put(prg, 0x1E, 0xA100, [1, 1, 0x55, 0xFF])
        put(prg, 0x1E, 0xA110, [0, 0, 0x66, 0xFF])
        with tempfile.TemporaryDirectory() as d:
            data = b.export(prg, os.path.join(d, 'o.json'))
        s0, s1 = data['signs']
        self.assertEqual((s0['table'], s0['msg'], s0['at']), (0, [0x355], ['00/00']))
        self.assertEqual((s1['table'], s1['msg'], s1['at']), (1, [0x366], []))


class TerrainTests(unittest.TestCase):
    def setUp(self):
        self.prg = prg = bytearray(PRG_SIZE)
        put(prg, 0x0F, b.CONVEYOR_PAD, [0x10, 0x80, 0x20, 0x40])
        put(prg, 0x0F, b.TERRAIN_VALUES, [0x08] * 11)
        put(prg, 0x1E, b.DOOR_LOCKS, [0x14, 0x15, 0x1C, 0x1D] + [0x30 + i for i in range(12)])

    def effect(self, prop):
        return b.terrain(self.prg, prop).get('effect')

    def test_walk_effects(self):
        self.assertEqual(self.effect(0x01), 'damage')
        self.assertEqual(b.terrain(self.prg, 0x01)['hp'], 1)
        self.assertEqual([self.effect(p) for p in (0x04, 0x05, 0x0B, 0x0A, 0x0F, 0x31)],
                         ['chest', 'fall', 'fall', 'travel_door', 'lift', 'slow_vertical'])
        self.assertEqual(b.terrain(self.prg, 0x33), {'walk': True, 'ship': False, 'effect': 'search', 'item': 0x57})
        self.assertEqual([b.terrain(self.prg, p)['dir'] for p in (0x10, 0x11, 0x12, 0x13)], ['up', 'right', 'down', 'left'])
        self.assertIsNone(self.effect(0x00))

    def test_ship_and_dock(self):
        self.assertEqual(b.terrain(self.prg, 0x24), {'walk': True, 'ship': True, 'effect': 'dock'})

    def test_blocked_cells_talk_over_and_facing(self):
        self.assertEqual(b.terrain(self.prg, 0xA7)['talk_over'], True)
        self.assertEqual(b.terrain(self.prg, 0x97)['talk_over'], True)
        self.assertEqual([b.terrain(self.prg, p).get('facing') for p in (0xA8, 0xAA, 0xAB, 0xB0, 0xAC)],
                         ['sign', 'pot', 'dresser', 'push_door', 'stuck_door'])
        self.assertEqual(b.terrain(self.prg, 0x80), {'walk': False, 'ship': False})
        self.assertEqual(b.terrain(self.prg, 0x94)['door'], {'lock': 0, 'shape': 0, 'opens': 'cell'})

    def test_kind_names(self):
        self.assertEqual(b.kind_name(0x80), '벽')
        self.assertEqual(b.kind_name(0x7E), '지나감(뜻 모름)')


class FallBranchTests(unittest.TestCase):
    def setUp(self):
        self.prg = bytearray(PRG_SIZE)
        put(self.prg, 0x12, b.FALLS, word(0xA000))
        put(self.prg, 0x12, 0xA000, [0xFF])
        put(self.prg, 0x12, b.FALL_FIELD1, [10, 11, 12, 13, 14, 15, 16, 17])

    def test_special_groups(self):
        f = lambda g, k, x=0, y=0, **kw: b.fall(self.prg, g, k, x, y, **kw)
        self.assertEqual(f(0x1C, 0), {'group': 0x3A, 'index': 0, 'x': 0x17, 'y': 0x03})
        self.assertEqual(f(0x46, 0, 0x23, 0x1D), {'field': 1, 'x': 0x13, 'y': 0x11})
        self.assertEqual(f(0x46, 0, 1, 1, d=1), {'field': 1, 'x': 12, 'y': 13})
        self.assertEqual(f(0x2D, 0, d=3), {'field': 1, 'x': 16, 'y': 17})
        self.assertEqual(f(0x30, 0, chapter=0), {'field': None, 'dx': 0, 'dy': 3})
        self.assertEqual(f(0x30, 0, chapter=1), {'field': None, 'dx': 0, 'dy': 2})
        self.assertEqual(f(0x3D, 1), {'group': 0x3D, 'index': 3, 'x': 8, 'y': 0x0F})

    def test_group_2e_regions(self):
        f = lambda x, y: b.fall(self.prg, 0x2E, 1, x, y)
        self.assertEqual(f(0x0B, 0x05), {'group': 0x2E, 'index': 2, 'x': 0x0A, 'y': 0x06})
        self.assertEqual(f(0x03, 0x06), {'group': 0x2E, 'index': 2, 'x': 0x05, 'y': 0x06})
        self.assertEqual(f(0x00, 0x10), {'group': 0x2E, 'index': 2, 'x': 0x06, 'y': 0x0A})
        self.assertEqual(f(0x00, 0x11), {'field': None, 'dx': 0, 'dy': 1})
        self.assertEqual(b.fall(self.prg, 0x2E, 0, 0, 0), {'field': None, 'dx': 0, 'dy': 1})

    def test_step_doubling_by_direction_and_mode(self):
        f = lambda d, mode: b.fall(self.prg, 0x20, 0, 0, 0, d=d, mode=mode)
        self.assertEqual(f(0, 5), {'field': None, 'dx': 0, 'dy': -2})
        self.assertEqual(f(0, 1), {'field': None, 'dx': 0, 'dy': -1})
        self.assertEqual(f(3, 0), {'field': None, 'dx': -1, 'dy': 0})
        self.assertEqual(f(1, 0), {'field': None, 'dx': 2, 'dy': 0})


class SmallTableExtraTests(unittest.TestCase):
    def setUp(self):
        self.prg = bytearray(PRG_SIZE)

    def test_lift_rects(self):
        put(self.prg, 0x1E, b.LIFT_RECTS + 5, [0x80, 3, 2] + word(0x7810))
        put(self.prg, 0x1E, b.LIFT_AREA, [0x00, 0x20])
        r = b.lift_rects(self.prg)
        self.assertEqual(len(r), 6)
        self.assertEqual(r[1], {'ride': 0x80, 'w': 3, 'h': 2, 'offset': 0x10, 'land': 0x20})

    def test_exit_fixed_and_kinds(self):
        put(self.prg, B08, b.EXIT_FIXED, [1, 2, 3, 4, 5, 6, 7, 8, 9, 0xFF])
        self.assertEqual(b.exit_fixed(self.prg), [{'group': 1, 'index': 2, 'x': 3, 'y': 4,
                                                   'to': {'group': 5, 'index': 6, 'x': 7, 'y': 8, 'dir': 9}}])
        put(self.prg, B08, b.EXIT_KINDS, word(0xA200))
        put(self.prg, B08, 0xA200, [0x08, 0x25, 0x00, 0x09])
        self.assertEqual(b.exit_kinds(self.prg), [0x08, 0x25])

    def test_exit_special_remaining_rules(self):
        s = b.exit_special
        self.assertEqual(s(0x3D, 1, 5, flags=0x80), (2, 5))
        self.assertEqual(s(0x40, 1, 0, flags=0x20), (2, 0))
        self.assertEqual(s(0x40, 1, 1, flags=0x20), (1, 1))
        self.assertEqual(s(0x45, 4, 0, flags=0x10), (6, 0))
        self.assertEqual(s(0x45, 5, 2, flags=0x02), (7, 3))
        self.assertEqual(s(0x42, 1, 4, flags=0x08), (0, 4))
        self.assertEqual(s(0x15, 3, 1), (2, 1))
        self.assertEqual(s(0x15, 3, 1, night=True), (3, 1))
        self.assertEqual(s(0x14, 0, 7, flags=1), (2, 0))
        self.assertEqual(s(0x01, 1, 2), (1, 2))

    def test_exit_to_field_special_entrance_and_missing_group(self):
        put(self.prg, *b.dq4field.ARRIVE_PTR, word(0xA400))
        put(self.prg, B08, 0xA400, [0x41, 0x22, 5, 6, 0, 0xFF])
        put(self.prg, *b.dq4field.ENTRANCE_PTR, word(0x9100))
        put(self.prg, 0x0E, 0x9100, [0x41, 0x30, 0x31, 0xFF])
        self.assertEqual(b.exit_to_field(self.prg, 0x41, 0x0E, 0x30), {'field': 1, 'group': 0x41, 'x': 0x8D, 'y': 0x1F})
        self.assertEqual(b.exit_to_field(self.prg, 0x41, 0, 0), {'field': 1, 'group': 0x41, 'x': 0x30, 'y': 0x31})
        self.assertEqual(b.exit_to_field(self.prg, 0x33, 0, 0), {'field': None, 'group': 0x33})


class DoorExtraTests(unittest.TestCase):
    def setUp(self):
        self.prg = bytearray(PRG_SIZE)
        self.prop = {0x1C: 0x9C, 0x05: 0x00}

    def m(self, grid):
        return SimpleNamespace(cell=lambda x, y: grid.get((x, y), 0), blocks={'prop': self.prop})

    def test_open_downward(self):
        grid = {(4, 6): 0x1C, (5, 6): 0x1C, (5, 8): 0x05}
        self.assertEqual(b.door_open_2x2(self.prg, self.m(grid), 5, 5, 2), (4, 6, 0x05))
        grid = {(5, 6): 0x1C, (6, 8): 0x07}
        self.assertEqual(b.door_open_2x2(self.prg, self.m(grid), 5, 5, 2), (5, 6, 0x07))

    def test_open_leftward(self):
        grid = {(4, 5): 0x1C, (3, 4): 0x1C, (2, 4): 0x09}
        self.assertEqual(b.door_open_2x2(self.prg, self.m(grid), 5, 5, 3), (3, 4, 0x09))
        grid = {(4, 5): 0x1C, (2, 5): 0x0A}
        self.assertEqual(b.door_open_2x2(self.prg, self.m(grid), 5, 5, 3), (3, 5, 0x0A))


class CompareTests(unittest.TestCase):
    TILES = {0: [0x8D, 0x8E, 0x8F, 0x90], 1: [0x8E, 0x91, 0x92, 0x8F], 2: [0xFC, 0xFD, 0xFE, 0xFF],
             0x20: [0x93] * 4, 0x21: [0x93] * 4}
    PAL = {0: 0, 1: 1, 2: 3, 0x20: 0, 0x21: 0}
    PROP = {0: 0x80, 1: 0x08, 2: 0x00}
    CHR_ADDR = {0x8D: 0x50, 0x8E: 0x60, 0x8F: 0x150, 0x90: 0x140, 0x91: 0x70, 0x92: 0x160,
                0xFC: 0, 0xFD: 0, 0xFE: 0, 0xFF: 0, 0x93: 0}

    def dumps(self, prg):
        ram, wram = bytearray(0x800), bytearray(0x2000)
        ram[0x28] = 1
        for blk, ts in self.TILES.items():
            wram[0x1600 + 4 * blk:0x1604 + 4 * blk] = bytes(ts)
            wram[0x16C0 + blk] = self.PAL[blk]
            if blk < 0x20:
                wram[0xF40 + blk] = self.PROP[blk]
        wram[0x1800:0x1808] = bytes([0, 0, 0, 0, 0, 1, 0, 0])
        chr_ = bytearray(0x2000)
        for n, a in self.CHR_ADDR.items():
            o = CHR_BANK * 0x4000 + a
            chr_[0x1000 + n * 16:0x1010 + n * 16] = prg[o:o + 16]
        ppal = bytearray(16)
        for i in range(16):
            ppal[i] = (0x16, 0x27, 0x30)[(i & 3) - 1] if i & 3 else 0x0F
        nt = bytearray(0x800)
        pal_at = {}
        for j in range(15):
            for i in range(16):
                blk = [[0, 0, 0, 0], [0, 1, 0, 0]][j][i] if j < 2 and i < 4 else 1
                c, r = 2 * i, 2 * j
                for q, t in enumerate(self.TILES[blk]):
                    nt[(r + (q >> 1)) * 32 + c + (q & 1)] = t
                shift = (r & 2) * 2 + (c & 2)
                a = 0x3C0 + (r // 4) * 8 + c // 4
                pal_at[a] = pal_at.get(a, 0) | self.PAL[blk] << shift
        for a, v in pal_at.items():
            nt[a] = v
        return ram, wram, bytes(nt), bytes(chr_), bytes(ppal)

    def write(self, d, ram, wram, nt, chr_, ppal, prefix=None):
        if prefix is None:
            for name, data in (('ram', ram), ('sram', wram), ('nt', nt), ('chr', chr_), ('pal', ppal)):
                Path(d, 'end.' + name).write_bytes(data)
        else:
            cpu = bytearray(0x8000)
            cpu[:0x800] = ram
            cpu[0x6000:] = wram
            Path(d, prefix + '.cpu').write_bytes(cpu)
            for name, data in (('nt', nt), ('chr', chr_), ('pal', ppal)):
                Path(d, prefix + '.' + name).write_bytes(data)

    def run_compare(self, prg, d, prefix=None):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            ok = b.compare(prg, d, prefix)
        return ok, out.getvalue().splitlines()

    def test_matching_dumps_pass_with_both_layouts(self):
        prg = world_prg()
        parts = self.dumps(prg)
        for prefix in (None, 'blk'):
            with tempfile.TemporaryDirectory() as d:
                self.write(d, *parts, prefix=prefix)
                ok, out = self.run_compare(prg, d, prefix)
            self.assertTrue(ok, out)
            self.assertEqual(out[0], '맵 종류 01: 블록 표 0 다름, CHR 타일 11개 중 0 다름(애니메이션 0개 뺌)')
            self.assertEqual(out[1], 'BG 팔레트 같음')
            self.assertEqual(out[2], '$7800(그늘 바꾸기 뒤) 8 바이트 중 0 다름, 바뀐 칸 0')
            self.assertTrue(out[3].endswith('다름, attribute 240 칸 중 0 다름') or '0 다름' in out[3])

    def test_wrong_tile_property_palette_and_screen_are_reported(self):
        prg = world_prg()
        ram, wram, nt, chr_, ppal = self.dumps(prg)
        wram[0x1604] ^= 1                  # 블록 1 의 첫 타일
        wram[0xF40] = 0x00                 # 블록 0 속성
        chr_ = bytearray(chr_)
        chr_[0x1000 + 0x91 * 16] ^= 0xFF
        ppal = bytearray(ppal)
        ppal[1] = 0x01
        nt = bytearray(nt)
        nt[0] ^= 0xFF
        wram[0x1800 + 5] = 7
        with tempfile.TemporaryDirectory() as d:
            self.write(d, ram, wram, bytes(nt), bytes(chr_), bytes(ppal))
            ok, out = self.run_compare(prg, d)
        self.assertFalse(ok)
        self.assertEqual(out[0], '맵 종류 01: 블록 표 2 다름(01 00:00≠80), CHR 타일 11개 중 1 다름(애니메이션 0개 뺌)')
        self.assertTrue(out[1].startswith('BG 팔레트 다름 '))
        self.assertEqual(out[2], '$7800(그늘 바꾸기 뒤) 8 바이트 중 1 다름, 바뀐 칸 0')
        self.assertIn('다른 곳(열,줄): 0,0', out[-1])


class MainCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.rom = os.path.join(self.tmp.name, 'r.nes')
        self.prg = world_prg()
        Path(self.rom).write_bytes(ines(self.prg))

    def run_main(self, *argv, cwd=None):
        out = io.StringIO()
        old = os.getcwd()
        if cwd:
            os.chdir(cwd)
        try:
            with mock.patch('sys.argv', ['dq4block.py', *argv]), contextlib.redirect_stdout(out):
                try:
                    b.main()
                    code = 0
                except SystemExit as e:
                    code = e.code
        finally:
            os.chdir(old)
        return code, out.getvalue().splitlines()

    def test_without_command_prints_doc_and_exits_2(self):
        code, out = self.run_main(self.rom)
        self.assertEqual(code, 2)
        self.assertTrue(out[0].startswith('DQ4(FC) 맵 블록'))

    def test_map_grid_and_nt(self):
        code, out = self.run_main(self.rom, '0', '0')
        self.assertEqual(out[0], '# 크기 4x2, 맵 종류 01, 바깥 블록 01')
        self.assertEqual(out[3:5], ['00  ####', '01  #8##'])
        _, out = self.run_main(self.rom, '0', '0', '--nt')
        self.assertEqual(out[0], '8D 8E 8D 8E 8D 8E 8D 8E')
        self.assertEqual(len(out), 4)

    def test_map_png_goes_to_work_dir(self):
        _, out = self.run_main(self.rom, '0', '0', '--png', cwd=self.tmp.name)
        self.assertEqual(out[-1], '그림: ' + os.path.join('work', 'dq4block-00_00.png'))
        self.assertEqual(Image.open(os.path.join(self.tmp.name, 'work', 'dq4block-00_00.png')).size, (64, 32))

    def test_field_grid(self):
        _, out = self.run_main(self.rom, 'field', '0')
        self.assertEqual(out[0], '# 크기 253x2, 맵 종류 00')
        self.assertEqual(out[3], '00  ' + '.' * 253)

    def test_defs_lists_blocks_and_palette(self):
        _, out = self.run_main(self.rom, 'defs', '1')
        self.assertEqual(out[0], '00: 00 01 뱅크 0C 타일 0050 0060 0150 0140 팔레트 0 종류 0 속성 80')
        self.assertEqual(out[1], '01: 08 02 뱅크 0C 타일 0060 0070 0160 0150 팔레트 1 종류 0 속성 08')
        self.assertEqual(out[2], '02: 없음')
        self.assertEqual(out[-1], '팔레트(낮): 16 27 30 / 16 27 30 / 16 27 30 / 16 27 30')

    def test_defs_marks_animation(self):
        put(self.prg, 0x1D, b.ANIM_T, [0x81, 0xFF])
        put(self.prg, 0x1D, b.ANIM_BLK, [0x01])
        put(self.prg, 0x1D, b.ANIM_SRC, word(0x9000))
        Path(self.rom).write_bytes(ines(self.prg))
        _, out = self.run_main(self.rom, 'defs', '0')
        self.assertTrue(any(ln.startswith('01:') for ln in out))
        put(self.prg, 0x1D, b.ANIM_T, [0x81 | 1, 0xFF])
        Path(self.rom).write_bytes(ines(self.prg))
        _, out = self.run_main(self.rom, 'defs', '1')
        self.assertTrue(out[1].endswith('애니메이션 1D:9000'))

    def test_subcommands_delegate(self):
        _, out = self.run_main(self.rom, 'effects', '0', '0')
        self.assertEqual(out[0], '08    1칸 {walk: True, ship: False, effect: exit}')
        _, out = self.run_main(self.rom, 'links', '0', '0')
        self.assertEqual(out, ['00/00 (01,01) 08 #0 → 필드 1 (20,21)'])
        _, out = self.run_main(self.rom, 'links')
        self.assertEqual(len(out), 1)
        _, out = self.run_main(self.rom, 'tables')
        self.assertEqual(out[0], '# 속성 값')
        _, out = self.run_main(self.rom, 'props')
        self.assertEqual(out[0], '속성 | 뜻 | 맵 수 | 칸 수 | 예(맵:블록)')
        _, out = self.run_main(self.rom, 'props', '--maps')
        self.assertEqual(out[0], '00/00 종류 01: 08=01 80=00')

    def test_json_default_and_explicit_path(self):
        out_path = os.path.join(self.tmp.name, 'sub', 'o.json')
        _, out = self.run_main(self.rom, 'json', out_path)
        self.assertEqual(out, [f'{out_path}: 맵 1, 필드 3, 속성 값 3가지'])
        self.assertTrue(os.path.exists(out_path))
        _, out = self.run_main(self.rom, 'json', cwd=self.tmp.name)
        self.assertEqual(out[0].split(':')[0], os.path.join('work', 'dq4block.json'))
        self.assertTrue(os.path.exists(os.path.join(self.tmp.name, 'work', 'dq4block.json')))

    def test_compare_exit_codes(self):
        cm = CompareTests()
        parts = cm.dumps(self.prg)
        d = os.path.join(self.tmp.name, 'dump')
        os.mkdir(d)
        cm.write(d, *parts)
        code, out = self.run_main(self.rom, 'compare', d)
        self.assertEqual(code, 0)
        self.assertEqual(out[1], 'BG 팔레트 같음')
        cm.write(d, parts[0], parts[1], parts[2], parts[3], bytes(16))
        code, _ = self.run_main(self.rom, 'compare', d)
        self.assertEqual(code, 1)
        cm.write(d, *parts, prefix='blk')
        code, _ = self.run_main(self.rom, 'compare', d, 'blk')
        self.assertEqual(code, 0)


class LinkDestinationTests(unittest.TestCase):
    def test_every_destination_form_is_printed(self):
        prg = world_prg()
        put(prg, B08, 0xA000 + 3 * 1, [0x05, 0x20, 0x07])         # 블록 0 도 출구 칸(07)
        put(prg, B08, 0xA800, [0x08, 0x07, 0x00])
        # 필드로, 필드에서 들어갈 때 자리로(그룹 5), 같은 맵 첫 칸으로(마지막 레코드)
        put(prg, B08, 0xA900, [0x00, 0x00, 0x40, 0x05, 0xA0, 0x00, 0x00, 0xFF, 0xFF])
        put(prg, B08, b.EXIT_FIXED, [0, 0, 0, 1, 3, 2, 7, 8, 1, 0xFF])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            b.show_links(prg)
        self.assertEqual(out.getvalue().splitlines(), [
            '00/00 (00,00) 07 #0 → 필드 1 (20,21)',
            '00/00 (01,00) 07 #1 → 그룹 05 의 필드 도착 자리',
            '00/00 (02,00) 07 #2 → 00/00 (00,00) n=0',
            '00/00 (03,00) 07 #3 → 레코드 없음(그룹 끝 FF 를 읽어 없는 맵 00/1F n=FF)',
            '00/00 (00,01) 07 #4 → 03/02 (07,08) 고정 표',
            '00/00 (01,01) 08 #5 → 레코드 없음',
            '00/00 (02,01) 07 #6 → 레코드 없음',
            '00/00 (03,01) 07 #7 → 레코드 없음'])


class ShowTablesEntriesTests(unittest.TestCase):
    def test_rows_of_each_table_are_printed(self):
        prg = world_prg()
        put(prg, 0x12, 0xA000, [0x10, 0x01, 0x82, 0xFF])
        put(prg, 0x1E, b.LIFTS, [0x30] + word(0xA000) + [0xFF])
        put(prg, 0x1E, 0xA000, [0, 1, 2, 3, 1, 4, 5, 0xFF, 0xFF])
        put(prg, 0x1E, b.POTS, [1, 2, 3, 4, 5, 6, 7, 0xFF])
        put(prg, 0x1E, 0xA100, [1, 2, 0x55, 0xFF])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            b.show_tables(prg)
        lines = out.getvalue().splitlines()

        def section(head):
            i = lines.index(head) + 1
            j = next((k for k in range(i, len(lines)) if lines[k].startswith('# ')), len(lines))
            return lines[i:j]
        self.assertEqual(section('# 떨어지는 칸 표(12:$B6DD)'), ['{group: 10, index: 01, when: None, to: {index: 02}}'])
        self.assertEqual(section('# 리프트(1E:$894A)'),
                         ['{group: 30, a: {index: 00, x: 01, y: 02, arg: 03}, b: {index: 01, x: 04, y: 05, arg: FF}}'])
        self.assertEqual(len(section('# 리프트 사각형(1E:$8A24)')), 6)
        self.assertEqual(section('# タンス·つぼ(1E:$BC7A)'), ['{group: 01, index: 02, x: 03, y: 04, item: 05, flag: 6279, bit: 07}'])
        self.assertEqual(section('# 팻말(1E:$BB52)'), ['{table: 00, x: 01, y: 02, msg: [355]}'])


class PaletteBranchTests(unittest.TestCase):
    def setUp(self):
        self.prg = prg = bytearray(PRG_SIZE)
        put(prg, 0x0E, 0xBBB1, [0x01] * 14 + [0x05, 0x06, 0x09, 0x07, 0x80])
        put(prg, 0x0E, 0xBBD3, [0x80] * 19)
        put(prg, 0x0E, 0xBBE6 + 2 * 3, [0x01, 0x02])
        put(prg, 0x0E, 0xBBE6 + 2 * 0x36, [0x03, 0x03])
        for s, ns in ((1, [0, 1, 2, 3]), (2, [4, 4, 4, 4]), (3, [5, 5, 5, 5])):
            put(prg, 0x0E, 0xBC68 + 4 * s, ns)
        put(prg, 0x0E, 0xBD40, bytes(range(0x10, 0x10 + 3 * 6)))

    def test_entry_0e_swaps_type_by_flag(self):
        self.assertEqual(b.palette(self.prg, 3, g=5, flag6293=0x10), bytes([0x1F, 0x20, 0x21] * 4))
        self.assertEqual(b.palette(self.prg, 3, g=5), bytes(range(0x10, 0x1C)))

    def test_later_entries_force_night_or_day(self):
        self.assertEqual(b.palette(self.prg, 3, g=6), bytes([0x1C, 0x1D, 0x1E] * 4))             # 0F 이상 11 미만은 밤
        self.assertEqual(b.palette(self.prg, 3, g=7, clock=0x78), bytes(range(0x10, 0x1C)))      # 11 부터는 낮

    def test_field_three_is_always_night(self):
        self.assertEqual(b.palette(self.prg, 3, field=3), bytes([0x1C, 0x1D, 0x1E] * 4))


class ShadeAreaTests(unittest.TestCase):
    def test_other_area_below_with_outside_block(self):
        kind = {0x01: 1, 0x02: 0, 0x05: 5}
        buf = bytes([0x01, 0x22])
        self.assertEqual(b.shade(buf, 1, 2, kind, outside=0x02, t=0x25)[0], 0x05)
        self.assertEqual(b.shade(buf, 1, 2, kind, outside=0x03, t=0x25)[0], 0x01)


if __name__ == '__main__':
    unittest.main()
