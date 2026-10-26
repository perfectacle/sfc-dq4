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

MAPS = ((0x02, 0, 0x0A, "burland"), (0x12, 0, 0x0E, "imuru"))


def _tile(assets, name, palette, map_type):
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
    background_name = "carpet" if map_type == 0x0E else "red_paving"
    if name in {"tree16", "bush", "flowers"}:
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


def prepare_maps(prg, assets):
    """Yield each FC map with its block counts and composited 16x16 block art."""
    if not assets:
        raise ValueError("Environment asset collection is empty")
    palette = next(iter(assets.values())).getpalette()
    if palette is None:
        raise ValueError("Environment palette is missing")
    for group, number, expected_type, name in MAPS:
        source = dq4block.Map(prg, group, number)
        if source.t != expected_type:
            raise ValueError(f"{group:02X}/{number:02X}: expected map type {expected_type:02X}, got {source.t:02X}")
        counts = Counter(value & 31 for value in source.buf)
        mapping = BLOCK_ART[source.t]
        unsupported = sorted(set(counts) - mapping.keys())
        if unsupported:
            raise ValueError(f"{name}: unsupported source blocks {unsupported}")
        prepared = {block: _tile(assets, mapping[block][0], palette, source.t) for block in counts}
        yield group, number, name, source, counts, prepared, palette


def render_maps(rom_path, assets):
    """Return complete block-grid previews and their ROM-derived mapping evidence."""
    data = Path(rom_path).read_bytes()
    result = {}
    for group, number, name, source, counts, prepared, palette in prepare_maps(ines.prg(data), assets):
        mapping = BLOCK_ART[source.t]
        preview = Image.new("P", (source.w * 16, source.h * 16))
        preview.putpalette(palette)
        for y in range(source.h):
            for x in range(source.w):
                block = source.cell(x, y) & 31
                preview.paste(prepared[block][0], (x * 16, y * 16))
        records = []
        for block, count in sorted(counts.items()):
            prop = source.blocks["prop"][block]
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
