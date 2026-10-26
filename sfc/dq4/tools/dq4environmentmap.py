"""Place original environment art on the FC maps' measured block grids."""

import hashlib
import sys
from collections import Counter
from pathlib import Path

from PIL import Image
from kr_patch.fc import ines

FC_TOOLS = Path(__file__).resolve().parents[3] / "fc" / "dq4" / "tools"
if str(FC_TOOLS) not in sys.path:
    sys.path.insert(0, str(FC_TOOLS))

import dq4block  # noqa: E402
from dq4environmentart import palette_variant  # noqa: E402


# IDs address the eight-column FC block sheets, not the art sheet's order.
BLOCK_ART = {
    0x0A: {
        0x00: ("grass", "잔디"),
        0x01: ("water0", "물"),
        0x02: ("tree16", "나무"),
        0x03: ("bush", "풀밭"),
        0x04: ("flowers", "꽃"),
        0x05: ("red_paving", "붉은 바닥・실내와 길 공용"),
        0x06: ("stone_wall_top", "석벽 윗줄"),
        0x07: ("stone_wall", "석벽 가운데"),
        0x08: ("castle_wall", "성 몸체 석벽"),
        0x09: ("tower_cap_left", "성탑 상단 왼쪽"),
        0x0A: ("tower_cap_right", "성탑 상단 오른쪽"),
        0x0B: ("tower_left", "성탑 벽 왼쪽"),
        0x0C: ("tower_right", "성탑 벽 오른쪽"),
        0x0D: ("gold_door16", "문"),
        0x0E: ("sign_church", "교회 표식"),
        0x0F: ("sign_inn", "여관 표식"),
        0x10: ("gate_top_left", "성문 상단 왼쪽"),
        0x11: ("gate_top_right", "성문 상단 오른쪽"),
        0x12: ("chest_closed", "보물상자"),
        0x13: ("dirt", "모래 바닥"),
        0x14: ("gate_bottom_left", "성문 하단 왼쪽"),
        0x15: ("gate_bottom_right", "성문 하단 오른쪽"),
        0x16: ("stairs_down", "아래 계단"),
        0x17: ("statue", "석상"),
        0x18: ("counter", "카운터"),
        0x19: ("stairs_up", "위 계단"),
        0x1A: ("well", "우물"),
        0x1B: ("chair", "의자"),
        0x1C: ("bed_left", "침대 발치"),
        0x1D: ("bed_right", "침대 머리맡"),
        0x1E: ("window16", "창문"),
        0x1F: ("round_table", "둥근 탁자"),
    },
    0x0E: {
        0x00: ("grass", "잔디"),
        0x01: ("water0", "물"),
        0x02: ("tree16", "나무"),
        0x03: ("flowers", "꽃"),
        0x04: ("carpet", "실내 바닥"),
        0x05: ("cobble", "길"),
        0x06: ("stone_wall_top", "벽 윗줄"),
        0x07: ("stone_wall", "벽 가운데"),
        0x08: ("stone_wall", "벽 아랫줄"),
        0x09: ("gold_door16", "문"),
        0x0A: ("sign_church", "교회 표식"),
        0x0B: ("sign_weapon", "무기점 표식"),
        0x0C: ("sign_armour", "방어구점 표식"),
        0x0D: ("sign_shop", "도구점 표식・장화 모양 해석은 미확인"),
        0x0E: ("sign_inn", "여관 표식"),
        0x0F: ("counter", "카운터"),
        0x10: ("chest_closed", "보물상자"),
        0x11: ("chest_closed", "보물상자"),
        0x12: ("stairs_up", "위 계단"),
        0x13: ("stairs_down", "아래 계단"),
        0x14: ("washbasin", "수반 모양 장식・뜻 미확인"),
        0x15: ("bed_left", "침대 발치"),
        0x16: ("bed_right", "침대 머리맡"),
        0x17: ("round_table", "둥근 탁자"),
        0x18: ("chair", "의자"),
        0x19: ("barrel", "둥근 목재 가구"),
        0x1A: ("wardrobe", "옷장"),
        0x1B: ("washbasin", "수반 모양 장식・뜻 미확인"),
        0x1C: ("chimney", "원통형 석재 장식・뜻 미확인"),
        0x1D: ("statue", "석재 장식"),
        0x1E: ("dark_void", "빈 검정 영역"),
        0x1F: ("dirt", "모래 바닥"),
    },
}

# Blocks of the other town and castle sheets whose graphics are not in BLOCK_ART. Each entry names
# the first sheet block showing that graphic; every block with the same CHR and colours follows it.
EXAMPLES = {
    (0x03, 0x02): ("wood_floor", "나무 바닥"),
    (0x03, 0x06): ("gold_door16", "문(とうぞくのカギ)"),
    (0x03, 0x07): ("iron_door", "쇠창살 문(さいごのカギ)"),
    (0x03, 0x08): ("red_paving_cracked", "갈라진 붉은 바닥"),
    (0x03, 0x0E): ("cloth_table", "천 덮인 탁자"),
    (0x03, 0x0F): ("counter", "카운터 끝"),
    (0x03, 0x10): ("potted_plant", "화분"),
    (0x03, 0x14): ("chair", "등받이 의자"),
    (0x03, 0x15): ("pot", "항아리"),
    (0x03, 0x18): ("counter", "카운터"),
    (0x03, 0x19): ("bookshelf", "책장"),
    (0x03, 0x1A): ("sky", "하늘・떨어지는 칸"),
    (0x03, 0x1B): ("gold_door16", "문(まほうのカギ)"),
    (0x03, 0x1E): ("brick_paving", "벽돌 바닥"),
    (0x04, 0x06): ("cabin_slats_left", "통나무집 창살 왼쪽"),
    (0x04, 0x07): ("cabin_slats", "통나무집 창살"),
    (0x04, 0x08): ("cabin_planks_right", "통나무집 벽 오른쪽 기둥"),
    (0x04, 0x09): ("cabin_slats_post", "통나무집 창살 기둥"),
    (0x04, 0x0A): ("cabin_planks_post", "통나무집 벽 기둥"),
    (0x04, 0x0B): ("cabin_slats_right", "통나무집 창살 오른쪽"),
    (0x04, 0x0D): ("stump", "그루터기"),
    (0x04, 0x0F): ("log_pile", "장작"),
    (0x04, 0x10): ("crops", "채소밭"),
    (0x04, 0x11): ("signboard", "팻말"),
    (0x04, 0x12): ("grave", "묘비"),
    (0x04, 0x14): ("stairs_up", "위 계단"),
    (0x04, 0x15): ("stairs_down", "아래 계단"),
    (0x04, 0x1F): ("pot", "항아리"),
    (0x05, 0x0C): ("stone_ledge", "바위 턱"),
    (0x05, 0x18): ("stone_floor", "흰 바닥"),
    (0x05, 0x1E): ("lion_statue", "사자상"),
    (0x06, 0x05): ("swamp", "독늪"),
    (0x06, 0x10): ("travel_door", "여행의 문"),
    (0x07, 0x0A): ("rock_wall", "바위벽"),
    (0x07, 0x0B): ("rock_wall_dark", "어두운 바위벽"),
    (0x07, 0x1D): ("blue_tile", "청백 타일"),
    (0x08, 0x0D): ("stone_wall_cracked", "금 간 석벽"),
    (0x08, 0x0E): ("stone_wall_cracked", "금 간 석벽"),
    (0x08, 0x0F): ("log_pile", "장작"),
    (0x09, 0x0C): ("stone_band", "무늬 판석 띠"),
    (0x09, 0x17): ("altar", "금 제단"),
    (0x09, 0x18): ("curtain", "휘장 문간"),
    (0x09, 0x19): ("valance", "푸른 휘장"),
    (0x09, 0x1A): ("pillar_top", "기둥 머리"),
    (0x09, 0x1B): ("pillar", "기둥"),
    (0x09, 0x1C): ("dais_left", "왕좌 뒤 장식 왼쪽"),
    (0x09, 0x1D): ("dais_middle", "왕좌 뒤 장식 가운데"),
    (0x09, 0x1E): ("dais_right", "왕좌 뒤 장식 오른쪽"),
    (0x09, 0x1F): ("throne", "옥좌"),
    (0x0B, 0x12): ("archway_left", "아치 통로 왼쪽"),
    (0x0B, 0x13): ("archway_right", "아치 통로 오른쪽"),
    (0x0B, 0x1C): ("bridge", "다리"),
    (0x0B, 0x1F): ("dark_void", "어둠"),
    (0x0C, 0x06): ("barrier", "결계"),
    (0x0C, 0x19): ("pew", "긴 의자"),
    (0x0D, 0x18): ("counter", "카운터 왼쪽"),
    (0x0D, 0x19): ("counter", "카운터 오른쪽"),
}
# The floor under transparent fixtures, as on the FC sheet.
SHEET_FLOORS = {0x04: "dirt", 0x0E: "carpet"}
BACKGROUNDS = {(0x08, 0x0F): "grass"}
TOWN_SHEETS = (0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0B, 0x0C, 0x0D)

# FC interior maps drawn with block sheets 0A and 0E, by name; their FC palettes are the same set
# except アッテムト, which uses a darker set.
MAPS = (
    (0x02, 0, 0x0A, "burland"), (0x08, 0, 0x0A, "gardenburg"), (0x09, 0, 0x0A, "stancia"),
    (0x09, 3, 0x0A, "stancia-03"), (0x09, 6, 0x0A, "stancia-06"), (0x0D, 0, 0x0A, "mintos"),
    (0x12, 0, 0x0E, "imuru"), (0x13, 4, 0x0A, "saran-04"), (0x19, 0, 0x0E, "seaside"),
    (0x19, 1, 0x0E, "seaside-01"), (0x1B, 0, 0x0A, "rosaryhill"), (0x1B, 1, 0x0A, "rosaryhill-01"),
    (0x2A, 0, 0x0A, "shrine-2a"), (0x32, 6, 0x0E, "konenbery-06"), (0x34, 5, 0x0E, "attemut-05"),
    (0x34, 7, 0x0E, "attemut-07"),
)
# Maps whose FC palette is darker than their sheet's: アッテムト, and the night or cursed variants
# 34/09, 3C/09 and 46/01-03 (one NES brightness step down in some or all colours).
MAP_PALETTES = {"attemut-05": "dim", "attemut-07": "dim", "34-09": "dim", "3C-09": "dim",
                "46-01": "dim", "46-02": "dim", "46-03": "dim"}


def all_maps(prg):
    """MAPS plus every FC map of TOWN_SHEETS as (group, number, sheet, name)."""
    yield from MAPS
    for _, source in dq4block.all_maps(prg):
        if source.buf is not None and source.t in TOWN_SHEETS:
            yield source.g, source.k, source.t, f"{source.g:02X}-{source.k:02X}"


def _graphic(prg, t, block):
    d = dq4block.defs(prg, t).get(block)
    if d is None:
        return None
    colours = dq4block.palette(prg, t)[3 * d["pal"]:3 * d["pal"] + 3]
    return d["bank"], tuple(d["addrs"]), bytes(colours)


def sheet_art(prg, t):
    """{block: (asset, role)} for every block of sheet t that has a BLOCK_ART or EXAMPLES graphic."""
    known = {}
    for (sheet, block), art in [((s, b), a) for s, arts in BLOCK_ART.items() for b, a in arts.items()] + list(EXAMPLES.items()):
        known.setdefault(_graphic(prg, sheet, block), art)
    out = dict(BLOCK_ART.get(t, {}))
    for block in range(32):
        if block not in out:
            graphic = _graphic(prg, t, block)
            if graphic in known:
                out[block] = known[graphic]
    return out


def _tile(assets, name, palette, map_type, block=None):
    if name not in assets:
        raise ValueError(f"Missing environment asset: {name}")
    tile = assets[name]
    if tile.mode != "P" or tile.size != (16, 16):
        raise ValueError(f"{name}: map block requires indexed 16x16 art, got {tile.mode} {tile.size}")
    if tile.getpalette() != palette:
        raise ValueError(f"{name}: palette differs from the shared environment palette")
    transparency = tile.info.get("transparency")
    if transparency not in (None, 0):
        raise ValueError(f"{name}: only transparent index zero is supported")
    pixels = tile.tobytes()
    transparent = pixels.count(0) if transparency == 0 and name != "dark_void" else 0
    background_name = BACKGROUNDS.get((map_type, block), SHEET_FLOORS.get(map_type, "red_paving"))
    if name in {"tree16", "bush", "flowers", "crops"}:
        background_name = "grass"
    elif name in {"sign_church", "sign_weapon", "sign_armour", "sign_inn", "sign_shop", "window16"}:
        background_name = "stone_wall"
    background = assets[background_name]
    if background.mode != "P" or background.size != (16, 16) or background.getpalette() != palette:
        raise ValueError(f"{background_name}: incompatible background tile")
    result = tile.copy()
    result.info.pop("transparency", None)
    remapped = 0
    for y in (0, 8):
        for x in (0, 8):
            indices = tile.crop((x, y, x + 8, y + 8)).tobytes()
            banks = {v >> 4 for v in indices if v}
            if len(banks) > 1 or any(v >= 128 or (v and (v < 16 or v % 16 == 0)) for v in indices):
                raise ValueError(f"{name}: incompatible SFC palette banks at {x},{y}")
            if not transparent:
                continue
            bank = next(iter(banks), None)
            for dy in range(8):
                for dx in range(8):
                    if tile.getpixel((x + dx, y + dy)):
                        continue
                    value = background.getpixel((x + dx, y + dy))
                    if bank is not None and value >> 4 != bank:
                        rgb = palette[value * 3:value * 3 + 3]
                        value = min(range(bank * 16 + 1, bank * 16 + 16), key=lambda i: sum(
                            (palette[i * 3 + channel] - rgb[channel]) ** 2 for channel in range(3)))
                        remapped += 1
                    result.putpixel((x + dx, y + dy), value)
    return result, {
        "background": background_name if transparent else None,
        "transparent_pixels_filled": transparent,
        "background_palette_remapped_pixels": remapped,
        "foreground_pixels_remapped": 0,
    }


# Blocks without an FC definition (the black filler 0E/1E) have no property; treat them as walls.
UNDEFINED = 0x80


def block_prop(source, block):
    return source.blocks["prop"].get(block, UNDEFINED)


def prepare_maps(prg, assets, names=None):
    """Yield each FC map with its block counts and composited 16x16 block art."""
    if not assets:
        raise ValueError("Environment asset collection is empty")
    palette = next(iter(assets.values())).getpalette()
    if palette is None:
        raise ValueError("Environment palette is missing")
    arts = {}
    for group, number, expected_type, name in all_maps(prg) if names is None else [m for m in all_maps(prg) if m[3] in names]:
        source = dq4block.Map(prg, group, number)
        if source.t != expected_type:
            raise ValueError(f"{group:02X}/{number:02X}: expected map type {expected_type:02X}, got {source.t:02X}")
        counts = Counter(value & 31 for value in source.buf)
        mapping = arts.setdefault(source.t, sheet_art(prg, source.t))
        unsupported = sorted(set(counts) - mapping.keys())
        if unsupported:
            raise ValueError(f"{name}: unsupported source blocks {unsupported}")
        prepared = {block: _tile(assets, mapping[block][0], palette, source.t, block) for block in counts}
        yield group, number, name, source, counts, prepared, palette


def render_maps(rom_path, assets, names=None):
    """Return complete block-grid previews and their ROM-derived mapping evidence."""
    data = Path(rom_path).read_bytes()
    result = {}
    prg = ines.prg(data)
    for group, number, name, source, counts, prepared, palette in prepare_maps(prg, assets, names):
        mapping = sheet_art(prg, source.t)
        preview = Image.new("P", (source.w * 16, source.h * 16))
        preview.putpalette(palette_variant(MAP_PALETTES.get(name, "normal")))
        for y in range(source.h):
            for x in range(source.w):
                block = source.cell(x, y) & 31
                preview.paste(prepared[block][0], (x * 16, y * 16))
        records = []
        for block, count in sorted(counts.items()):
            prop = block_prop(source, block)
            records.append({
                "source_block": f"{block:02X}",
                "asset": mapping[block][0],
                "visual_role": mapping[block][1],
                "property": prop,
                "functional_role": dq4block.kind_name(prop),
                "passable": not bool(prop & 0x80),
                "cells": count,
                "composition": prepared[block][1],
            })
        result[name] = (preview, {
            "map": f"{group:02X}/{number:02X}",
            "map_type": f"{source.t:02X}",
            "palette": MAP_PALETTES.get(name, "normal"),
            "size_blocks": [source.w, source.h],
            "source_rom_sha1": hashlib.sha1(data).hexdigest(),
            "source_layout_sha256": hashlib.sha256(bytes(source.buf)).hexdigest(),
            "source_sheet": f"fc/dq4/gfx/blocks/{source.t:02X}.png",
            "block_mappings": records,
            "unsupported_blocks": [],
            "source_cells": source.w * source.h,
            "rendered_cells": sum(counts.values()),
            "palette_remapped_pixels": sum(prepared[b][1]["background_palette_remapped_pixels"] * n for b, n in counts.items()),
            "foreground_pixels_remapped": 0,
            "layout_preserved": True,
            "region_visibility": "all regions exposed, matching the FC reference renderer",
            "characters_rendered": False,
            "engine_ready": False,
            "limitations": [
                "Static closed-door and first-water-frame preview; no events or animation are executed.",
                "Passability and functional roles are recorded, not installed into the DQ5 engine.",
                "Wall heights and roof overlays are not added to the FC block grid.",
                "Visual meanings marked unconfirmed remain hypotheses, independent of ROM properties.",
            ],
        })
    return result
