"""환경 맵 그리기를 롬 없이 합성 FC 맵·합성 에셋(16x16 팔레트 그림)으로 검사한다."""
import sys
import tempfile
import hashlib
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dq4environmentmap as em  # noqa: E402


def make_palette():
    """색 i 는 (i, 255 - i, i // 2). 33 번은 20 번과 같은 색(은행이 다른 같은 색의 이동을 보려고),
    21 번은 은행 1 에서 가장 어둡고 20 번은 가장 밝다."""
    pal = []
    for i in range(256):
        pal += [i, 255 - i, i // 2]
    pal[21 * 3:21 * 3 + 3] = [0, 0, 0]
    pal[20 * 3:20 * 3 + 3] = [250, 250, 250]
    pal[33 * 3:33 * 3 + 3] = [250, 250, 250]
    return pal


PALETTE = make_palette()


def tile(fill=None, rows=None, transparency=None):
    image = Image.new("P", (16, 16), fill or 0)
    image.putpalette(PALETTE)
    if rows is not None:
        image.putdata([rows(x, y) for y in range(16) for x in range(16)])
    if transparency is not None:
        image.info["transparency"] = transparency
    return image


def assets_set():
    return {
        "floor": tile(17), "wall": tile(33), "baseart": tile(rows=lambda x, y: 20 if x >= 8 else 17),
        "cave_floor_earth": tile(33), "sky": tile(17), "sky_deep": tile(17), "dark_void": tile(17),
        "grass": tile(17), "water0": tile(18), "dirt": tile(17),
    }


class NearestTests(unittest.TestCase):
    def test_nearest_colour_of_the_bank(self):
        self.assertEqual(em._nearest(PALETTE, 33, 1), 20)
        self.assertEqual(em._nearest(PALETTE, 21, 1), 21)

    def test_span_limits_the_search(self):
        # 은행 7 은 1~7 만 보면(span 8) 바깥의 같은 색이 있어도 안쪽 것을 고른다
        near = em._nearest(PALETTE, 120, 7, 8)
        self.assertIn(near, range(7 * 16 + 1, 7 * 16 + 8))


class ShapeClassTests(unittest.TestCase):
    def classes(self, rows, kind="trace", base="floor"):
        with mock.patch.object(em, "fc_pixels", lambda prg, t, block: rows):
            return em._shape_classes(None, 0x10, 1, kind, base)

    def rows(self):
        rows = [[0x16] * 16 for _ in range(16)]
        rows[0][0], rows[0][1] = 0x21, 0x12
        rows[5][5] = 0x0F
        for y in range(8, 11):
            for x in range(8, 11):
                rows[y][x] = 0x0F
        rows[14][14] = 0x26
        rows[14][2] = 0x01
        return rows

    def test_trace_marks_sky_outline_and_void(self):
        out = self.classes(self.rows())
        self.assertEqual((out[0][0], out[0][1]), ("S", "D"))
        self.assertEqual(out[5][5], "O")
        self.assertEqual(out[9][9], "V")
        self.assertEqual(out[8][8], "O")
        self.assertEqual(out[14][14], "A")
        self.assertEqual(out[3][3], "A")

    def test_relief_raises_colours_brighter_than_the_slab(self):
        out = self.classes(self.rows(), kind="relief")
        self.assertEqual(out[14][14], "H")
        self.assertEqual(out[3][3], "A")

    def test_water_blue_is_water_only_on_a_water_base(self):
        rows = self.rows()
        rows[1][1] = 0x21
        self.assertEqual(self.classes(rows, base="water0")[1][1], "A")
        self.assertEqual(self.classes(rows, base="floor")[1][1], "S")

    def test_unknown_kind_is_an_error(self):
        with self.assertRaisesRegex(ValueError, "unknown shape"):
            em._shape_classes(None, 0x10, 1, "mystery", "floor")


class TileTests(unittest.TestCase):
    def tile(self, name, assets, **kw):
        return em._tile(assets, name, PALETTE, kw.pop("map_type", 0x10), kw.pop("block", 1), **kw)

    def assets(self):
        a = assets_set()
        # 왼쪽 위 8x8: 왼쪽 절반이 투명(은행 1), 오른쪽 위 8x8 은 전부 투명, 나머지는 18
        a["fg"] = tile(rows=lambda x, y: 0 if (y < 8 and (x >= 8 or x < 4)) else 18, transparency=0)
        return a

    def test_transparent_pixels_take_the_background_in_the_tile_bank(self):
        image, info = self.tile("fg", self.assets(), background_name="wall")
        self.assertEqual(info, {"background": "wall", "transparent_pixels_filled": 96,
                                "background_palette_remapped_pixels": 32, "foreground_pixels_remapped": 0})
        self.assertEqual(image.getpixel((0, 0)), 20)       # 은행 2 의 33 → 은행 1 의 같은 색 20
        self.assertEqual(image.getpixel((8, 0)), 33)       # 투명뿐인 8x8 은 배경 그대로
        self.assertEqual(image.getpixel((5, 0)), 18)
        self.assertNotIn("transparency", image.info)

    def test_opaque_tile_is_copied_without_background(self):
        image, info = self.tile("floor", self.assets())
        self.assertEqual(image.tobytes(), self.assets()["floor"].tobytes())
        self.assertEqual(info["background"], None)
        self.assertEqual(info["transparent_pixels_filled"], 0)

    def test_background_defaults_to_the_sheet_floor_and_fixtures_override_it(self):
        a = self.assets()
        a["tree16"] = tile(rows=lambda x, y: 0 if x < 8 else 18, transparency=0)
        a["stone_wall"] = a["wall"]
        a["fg"].info["transparency"] = 0
        _, info = self.tile("fg", a, map_type=0x04)
        self.assertEqual(info["background"], "dirt")
        _, info = self.tile("tree16", a)
        self.assertEqual(info["background"], "grass")
        a["sign_inn"] = a["tree16"].copy()
        a["sign_inn"].info["transparency"] = 0
        _, info = self.tile("sign_inn", a)
        self.assertEqual(info["background"], "stone_wall")
        _, info = self.tile("fg", a, map_type=0x08, block=0x0F)
        self.assertEqual(info["background"], "grass")

    def test_dark_void_never_counts_as_transparent(self):
        a = self.assets()
        a["dark_void"] = tile(rows=lambda x, y: 0 if x < 8 else 17, transparency=0)
        _, info = self.tile("dark_void", a)
        self.assertEqual(info["transparent_pixels_filled"], 0)

    def test_bad_art_is_refused(self):
        a = self.assets()
        with self.assertRaisesRegex(ValueError, "Missing environment asset"):
            self.tile("nothing", a)
        a["rgb"] = Image.new("RGB", (16, 16))
        with self.assertRaisesRegex(ValueError, "requires indexed 16x16"):
            self.tile("rgb", a)
        a["small"] = Image.new("P", (8, 8))
        with self.assertRaisesRegex(ValueError, "requires indexed 16x16"):
            self.tile("small", a)
        odd = tile(17)
        odd.putpalette([0] * 768)
        a["odd"] = odd
        with self.assertRaisesRegex(ValueError, "palette differs"):
            self.tile("odd", a)
        a["t5"] = tile(17, transparency=5)
        with self.assertRaisesRegex(ValueError, "only transparent index zero"):
            self.tile("t5", a)
        a["backdrop"] = Image.new("P", (16, 16))
        with self.assertRaisesRegex(ValueError, "incompatible background"):
            self.tile("floor", a, background_name="backdrop")

    def test_mixed_banks_or_reserved_indices_in_an_8x8_are_refused(self):
        a = self.assets()
        a["mixed"] = tile(rows=lambda x, y: 17 if x % 2 else 33)
        with self.assertRaisesRegex(ValueError, "incompatible SFC palette banks"):
            self.tile("mixed", a)
        a["high"] = tile(130)
        with self.assertRaisesRegex(ValueError, "incompatible SFC palette banks"):
            self.tile("high", a)
        a["first"] = tile(16)
        with self.assertRaisesRegex(ValueError, "incompatible SFC palette banks"):
            self.tile("first", a)
        a["low"] = tile(5)
        with self.assertRaisesRegex(ValueError, "incompatible SFC palette banks"):
            self.tile("low", a)


class ShapeTileTests(unittest.TestCase):
    def test_slope_floor_moves_into_the_base_bank_and_outline_is_darkest(self):
        image, info = em._shape_tile(None, assets_set(), "slope:baseart", PALETTE, 0x10, 2)
        self.assertEqual(image.getpixel((0, 0)), 20)       # 바닥(33, 은행 2) → 같은 색 20
        self.assertEqual(image.getpixel((15, 0)), 21)      # 대각선은 은행 1 의 가장 어두운 색
        self.assertEqual(image.getpixel((15, 15)), 20)     # 바탕은 기본 에셋 그대로(오른쪽 절반은 20)
        self.assertEqual(info["shape"], "slope")
        self.assertEqual(info["background_palette_remapped_pixels"], 120)

    def test_relief_raised_parts_take_the_lightest_used_colour(self):
        rows = [[0x16] * 16 for _ in range(16)]
        rows[2][2] = 0x26
        with mock.patch.object(em, "fc_pixels", lambda prg, t, block: rows):
            image, _ = em._shape_tile(None, assets_set(), "relief:baseart", PALETTE, 0x10, 2)
        self.assertEqual(image.getpixel((2, 2)), 20)
        self.assertEqual(image.getpixel((3, 3)), 17)

    def test_sheet_with_third_style_entry_uses_it_as_void(self):
        a = assets_set()
        a["sky"] = tile(18)
        # 시트 1C 의 허공은 스타일의 셋째 항목(sky)에서 온다
        rows = [[0x0F] * 16 for _ in range(16)]
        rows[0][0] = 0x16
        with mock.patch.object(em, "fc_pixels", lambda prg, t, block: rows):
            a["stone_floor"] = tile(17)
            image, _ = em._shape_tile(None, a, "trace:baseart", PALETTE, 0x1C, 2)
        self.assertEqual({image.getpixel((x, y)) for x in range(3, 13) for y in range(3, 13)}, {18})


class FcPixelTests(unittest.TestCase):
    def test_two_bit_pixels_pick_the_map_colours(self):
        bank, quarter = 1, [0x8000, 0x8010, 0x8020, 0x8030]
        prg = bytearray(0x10000)
        base = bank * 0x4000
        for q, addr in enumerate(quarter):
            data = base + (addr & 0x3FFF)
            prg[data + 0] = 0b10000000 if q == 0 else 0
            prg[data + 8] = 0b01000000 if q == 0 else 0xFF
        graphic = (bank, tuple(quarter), bytes((0x11, 0x22, 0x33)))
        with mock.patch.object(em, "_graphic", lambda prg, t, block: graphic):
            rows = em.fc_pixels(bytes(prg), 0x10, 1)
        self.assertEqual(rows[0][:3], [0x11, 0x22, 0x0F])
        self.assertEqual(rows[0][8], 0x22)
        self.assertEqual(rows[8][0], 0x22)
        self.assertEqual(rows[1][1], 0x0F)


class SheetArtTests(unittest.TestCase):
    def setUp(self):
        graphics = {
            (0x70, 1): (1, (0x8000,) * 4, 0, 0x00), (0x70, 2): (2, (0x8010,) * 4, 1, 0x00),
            (0x70, 3): (3, (0x8020,) * 4, 2, 0x05), (0x70, 4): (3, (0x8030,) * 4, 2, 0x31),
            (0x70, 5): (3, (0x8040,) * 4, 2, 0x40), (0x70, 6): (3, (0x8050,) * 4, 2, 0x80),
            (0x70, 7): (3, (0x8060,) * 4, 2, 0x00), (0x70, 8): (3, (0x8070,) * 4, 2, 0x00),
            (0x71, 5): (2, (0x8010,) * 4, 1, 0x00),
        }

        def defs(prg, t):
            return {b: {"bank": g[0], "addrs": list(g[1]), "pal": g[2], "prop": g[3]}
                    for (sheet, b), g in graphics.items() if sheet == t}

        self.patches = [
            mock.patch.object(em.dq4block, "defs", defs),
            mock.patch.object(em.dq4block, "palette", lambda prg, t: bytes(range(1, 10))),
            mock.patch.object(em.dq4block, "kind_name", lambda prop: f"K{prop:02X}"),
            mock.patch.object(em, "BLOCK_ART", {0x70: {1: ("a1", "role1")}}),
            mock.patch.object(em, "EXAMPLES", {(0x71, 5): ("ex", "ex-role")}),
            mock.patch.object(em, "SHEET_STYLES", {0x70: ("wallart", "floorart", "voidart")}),
            mock.patch.object(em, "LADDER_SHEETS", {0x70}),
            mock.patch.object(em, "PROPERTY_ART", {0x40: "doorart"}),
            mock.patch.object(em, "SHAPES", {0x70: {7: "relief"}}),
        ]
        for patcher in self.patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_art_comes_from_the_table_example_property_or_sheet_style(self):
        out = em.sheet_art(None, 0x70)
        self.assertEqual(out[1], ("a1", "role1"))
        self.assertEqual(out[2], ("ex", "ex-role"))
        self.assertEqual(out[3], ("voidart", "떨어지는 칸(시트 기본)"))
        self.assertEqual(out[4], ("ladder", "사다리(속성 기본)"))
        self.assertEqual(out[5], ("doorart", "K40(속성 기본)"))
        self.assertEqual(out[6], ("wallart", "벽(시트 기본)"))
        self.assertEqual(out[8], ("floorart", "바닥(시트 기본)"))

    def test_undefined_blocks_count_as_walls(self):
        self.assertEqual(em.sheet_art(None, 0x70)[20], ("wallart", "벽(시트 기본)"))
        self.assertEqual(len(em.sheet_art(None, 0x70)), 32)

    def test_shape_replaces_a_default_floor_with_a_relief_of_it(self):
        self.assertEqual(em.sheet_art(None, 0x70)[7], ("relief:floorart", "바닥 부조(FC 모양)"))

    def test_shape_with_a_base_and_a_cliff_role(self):
        with mock.patch.object(em, "SHAPES", {0x70: {7: "trace:water0"}}):
            self.assertEqual(em.sheet_art(None, 0x70)[7], ("trace:water0", "벼랑·비탈(FC 모양)"))

    def test_shape_over_an_explicit_art_is_refused(self):
        with mock.patch.object(em, "SHAPES", {0x70: {1: "slope"}}):
            with self.assertRaisesRegex(ValueError, "SHAPES would replace a1"):
                em.sheet_art(None, 0x70)

    def test_sheet_without_style_keeps_only_blocks_with_a_known_graphic(self):
        self.assertEqual(em.sheet_art(None, 0x71), {5: ("ex", "ex-role")})


class FakeSource:
    def __init__(self, g, k, t, w, h, buf, props=None):
        self.g, self.k, self.t, self.w, self.h = g, k, t, w, h
        self.buf = bytearray(buf)
        self.blocks = {"prop": props or {}}

    def cell(self, x, y):
        return self.buf[y * self.w + x]


class MapEditTests(unittest.TestCase):
    def source(self, props):
        return FakeSource(0x14, 0, 0x0A, 0x20, 8, [0x22] * (0x20 * 8), props)

    def test_edit_cells_swaps_only_the_block_bits(self):
        src = self.source({2: 0x00, 1: 0x00})
        src.buf = bytes(src.buf)
        em.edit_cells(src, 0x14, 0)
        self.assertIsInstance(src.buf, bytearray)
        self.assertEqual(src.cell(0x13, 4) & 31, 1)
        self.assertEqual(src.cell(0x13, 4) & ~31, 0x20)
        self.assertEqual(src.cell(0x15, 3) & 31, 1)
        self.assertEqual(src.cell(0, 0), 0x22)

    def test_other_maps_are_untouched(self):
        src = self.source({})
        before = bytes(src.buf)
        em.edit_cells(src, 0x01, 0)
        self.assertEqual(bytes(src.buf), before)

    def test_edit_that_changes_passability_is_refused(self):
        src = self.source({2: 0x00, 1: 0x80})
        with self.assertRaisesRegex(ValueError, "지나가기 속성이 다른 블록"):
            em.edit_cells(src, 0x14, 0)

    def test_block_prop_defaults_to_wall(self):
        self.assertEqual(em.block_prop(self.source({3: 0x31}), 3), 0x31)
        self.assertEqual(em.block_prop(self.source({}), 9), em.UNDEFINED)

    def test_map_palette_by_name_then_sheet(self):
        self.assertEqual(em.map_palette("attemut-05", 0x0A), "dim")
        self.assertEqual(em.map_palette("x", 0x28), "purple")
        self.assertEqual(em.map_palette("x", 0x0A), "normal")


class MapListTests(unittest.TestCase):
    def test_extra_fc_maps_follow_the_named_ones_when_their_sheet_is_listed(self):
        found = [(None, SimpleNamespace(buf=b"x", t=0x10, g=0x30, k=2)),
                 (None, SimpleNamespace(buf=None, t=0x10, g=0x30, k=3)),
                 (None, SimpleNamespace(buf=b"x", t=0xFE, g=0x30, k=4))]
        with mock.patch.object(em.dq4block, "all_maps", lambda prg: found):
            maps = list(em.all_maps(None))
        self.assertEqual(maps[:len(em.MAPS)], list(em.MAPS))
        self.assertEqual(maps[len(em.MAPS):], [(0x30, 2, 0x10, "30-02")])


class PrepareAndRenderTests(unittest.TestCase):
    def setUp(self):
        self.sources = {(0x30, 1): FakeSource(0x30, 1, 0x10, 2, 1, [0, 1], {0: 0x00, 1: 0x80})}
        self.mapping = {0: ("floor", "바닥"), 1: ("wall", "벽")}
        listing = [(0x30, 1, 0x10, "demo"), (0x30, 2, 0x10, "other")]
        for patcher in (
                mock.patch.object(em, "all_maps", lambda prg: listing),
                mock.patch.object(em, "sheet_art", lambda prg, t: self.mapping),
                mock.patch.object(em.dq4block, "Map", lambda prg, g, k: self.sources[g, k]),
                mock.patch.object(em.ines, "prg", lambda raw: raw)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_prepare_yields_counts_and_art_for_the_requested_names(self):
        (found,) = list(em.prepare_maps(b"", assets_set(), names=["demo"]))
        group, number, name, source, counts, prepared, palette = found
        self.assertEqual((group, number, name), (0x30, 1, "demo"))
        self.assertEqual(dict(counts), {0: 1, 1: 1})
        self.assertEqual(sorted(prepared), [0, 1])
        self.assertEqual(prepared[1][0].getpixel((0, 0)), 33)
        self.assertEqual(palette, PALETTE)

    def test_shape_art_is_drawn_through_shape_tile(self):
        self.mapping = {0: ("floor", "바닥"), 1: ("slope:baseart", "비탈")}
        (found,) = list(em.prepare_maps(b"", assets_set(), names=["demo"]))
        self.assertEqual(found[5][1][1]["shape"], "slope")

    def test_empty_or_paletteless_assets_are_refused(self):
        with self.assertRaisesRegex(ValueError, "collection is empty"):
            list(em.prepare_maps(b"", {}))
        with self.assertRaisesRegex(ValueError, "palette is missing"):
            list(em.prepare_maps(b"", {"rgb": Image.new("RGB", (16, 16))}))

    def test_wrong_sheet_type_is_refused(self):
        self.sources[0x30, 1].t = 0x11
        with self.assertRaisesRegex(ValueError, "expected map type 10, got 11"):
            list(em.prepare_maps(b"", assets_set(), names=["demo"]))

    def test_block_without_art_is_refused(self):
        self.mapping = {0: ("floor", "바닥")}
        with self.assertRaisesRegex(ValueError, r"demo: unsupported source blocks \[1\]"):
            list(em.prepare_maps(b"", assets_set(), names=["demo"]))

    def test_render_maps_places_each_block_art_and_records_the_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            rom = Path(tmp) / "dq4.nes"
            rom.write_bytes(b"fc-rom")
            result = em.render_maps(rom, assets_set(), names=["demo"])
        preview, info = result["demo"]
        self.assertEqual(preview.size, (32, 16))
        self.assertEqual((preview.getpixel((0, 0)), preview.getpixel((16, 0))), (17, 33))
        self.assertEqual(info["map"], "30/01")
        self.assertEqual(info["map_type"], "10")
        self.assertEqual(info["palette"], "normal")
        self.assertEqual(info["size_blocks"], [2, 1])
        self.assertEqual(info["source_rom_sha1"], hashlib.sha1(b"fc-rom").hexdigest())
        self.assertEqual(info["source_layout_sha256"], hashlib.sha256(bytes([0, 1])).hexdigest())
        self.assertEqual(info["source_sheet"], "fc/dq4/gfx/blocks/10.png")
        self.assertEqual((info["source_cells"], info["rendered_cells"]), (2, 2))
        floor, wall = info["block_mappings"]
        self.assertEqual((floor["source_block"], floor["asset"], floor["property"], floor["passable"]),
                         ("00", "floor", 0, True))
        self.assertEqual((wall["source_block"], wall["asset"], wall["property"], wall["passable"]),
                         ("01", "wall", 0x80, False))
        self.assertEqual(wall["cells"], 1)
        self.assertEqual(info["palette_remapped_pixels"], 0)
        self.assertFalse(info["engine_ready"])


class FieldRenderTests(unittest.TestCase):
    def render(self, blocks):
        field_source = SimpleNamespace(dw=2, dh=1, cell=lambda x, y: blocks[x])
        with tempfile.TemporaryDirectory() as tmp:
            rom = Path(tmp) / "dq4.nes"
            rom.write_bytes(b"fc")
            with mock.patch.object(em.ines, "prg", lambda raw: raw), mock.patch.object(em.dq4field, "FIELDS", (0,)), \
                    mock.patch.object(em.dq4block, "Map", lambda prg, field=None: field_source):
                return em.render_fields(rom, assets_set())

    def test_field_blocks_are_drawn_from_field_art(self):
        image, info = self.render((0x00, 0x02))["field0"]
        self.assertEqual(image.size, (32, 16))
        self.assertEqual(image.getpixel((0, 0)), 18)        # 바다는 water0 그대로
        self.assertEqual(image.getpixel((16, 0)), 17)       # 초원은 grass
        self.assertEqual(info["field"], 0)
        self.assertEqual(info["size_blocks"], [2, 1])
        self.assertEqual([m["asset"] for m in info["block_mappings"]], ["water0", "grass"])
        self.assertEqual([m["cells"] for m in info["block_mappings"]], [1, 1])

    def test_block_without_field_art_is_refused(self):
        with self.assertRaisesRegex(ValueError, r"field 0: unsupported blocks \[31\]"):
            self.render((0x00, 0x1F))


if __name__ == "__main__":
    unittest.main()
