"""Put the Burland and Imuru environment maps into SFC DQ5 as replacement interior maps.

CHR, CHR palette nibbles and the BG palette live in a graphics bank. Block definitions and
map records must stay in banks 30-3F: the loader reads them with the data bank set to
their bank and still touches low WRAM and I/O registers by absolute address, which banks
40 and up do not mirror. Two hooks in bank 01 switch the loader to this data only for the
replaced maps; see sfc/dq4/docs/dq4-environment-format.md.
"""

import argparse
import json
import sys
from pathlib import Path

from kr_patch.fc import ines

TOOLS = Path(__file__).resolve().parent
DQ5_TOOLS = TOOLS.parents[1] / "dq5" / "tools"
for path in (TOOLS, DQ5_TOOLS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dq4environmentart import create_assets  # noqa: E402
from dq4environmentmap import prepare_maps  # noqa: E402
from dq5mapwrite import Rom, encode, lorom, pointer_addr  # noqa: E402

# FC map name -> replaced DQ5 interior map. Targets must have no animated tiles,
# preloaded blocks, reserved slots, per-map routine or objects (01:D2FC): those run with the original
# block numbers or common tiles and would overwrite the new map.
TARGETS = {"burland": (0x03, 0x00), "imuru": (0x19, 0x02)}
CHR_BANK = 0x40
GFX_BANK = 0x41
NIBBLES_AT = 0x8000
PALETTE_AT = 0x8400
BLOCK_BANK = 0x3D
BLOCKS_AT = 0x8000
POINTERS_AT = 0x8800
MAPS_AT = 0x3D9000
HOOK_AT = 0x01FED0
HOOK_END = 0x020000
BLOCK_TABLE = 0x7EB000
PALETTE_LINE1 = 0x3934
WALL = 8
FLOOR = 1
WATER_BLOCK = 0x01
WATER_FRAMES = ("water0", "water1", "water2")
WATER_AT = 0x40C000
WATER_PERIOD = 24
ANIM_AT = 0x3DF000
# FC door properties and the DQ5 objects (01:D2FC kinds) that replace them. The record under an
# object is the map's floor so the cell is walkable once the object opens; closed objects block
# their last row themselves (cell +1 bit7).
DOOR = 0x94
GATE = 0xA0
FLOORS = {"burland": 0x05, "imuru": 0x04}
DOOR_KIND = 0x3B
GATE_KIND = 0x48
OBJECT_TABLE = 0x01D2FC
# Every caller of 15:F7D0, which picks the per-frame routine 7E:1AA5 after a map loads.
ROUTINE_CALLS = (0x018F84, 0x0198FC, 0x019FD6)


def _off(addr):
    return (addr >> 16) * 0x8000 + (addr & 0x7FFF)


def _bgr555(rgb):
    r, g, b = (v >> 3 for v in rgb)
    return r | g << 5 | b << 10


def _tiles(image, x, y):
    tile = image.crop((x, y, x + 8, y + 8)).tobytes()
    banks = {v >> 4 for v in tile if v}
    if len(banks) > 1:
        raise ValueError(f"mixed palette banks in an 8x8 tile at {x},{y}")
    return bytes(v & 15 for v in tile), next(iter(banks), 1)


def _planar(pixels):
    out = bytearray(32)
    for y in range(8):
        for x in range(8):
            v = pixels[y * 8 + x]
            for plane in range(4):
                if v >> plane & 1:
                    out[(plane >> 1) * 16 + y * 2 + (plane & 1)] |= 0x80 >> x
    return bytes(out)


def build_graphics(prg, assets):
    """Deduplicate CHR (pattern + palette) and 2x2 blocks shared by both maps."""
    chr_ids, chr_data, chr_banks = {}, [], []
    block_ids, block_words = {}, []
    maps = {}
    palette = None
    for group, number, name, source, counts, prepared, palette in prepare_maps(prg, assets):
        local = {}
        for fc_block, (image, _) in prepared.items():
            words = []
            for ty in (0, 8):
                for tx in (0, 8):
                    pixels, bank = _tiles(image, tx, ty)
                    if bank == 0:
                        bank = 1
                    key = (pixels, bank)
                    if key not in chr_ids:
                        chr_ids[key] = len(chr_data)
                        chr_data.append(_planar(pixels))
                        chr_banks.append(bank)
                    words.append(chr_ids[key])
            key = tuple(words)
            if key not in block_ids:
                block_ids[key] = len(block_words)
                block_words.append(key)
            local[fc_block] = block_ids[key]
        maps[name] = (source, local)
    if len(chr_data) > 1024:
        raise ValueError(f"{len(chr_data)} CHR do not fit one bank")
    return chr_data, chr_banks, block_words, maps, palette


def _prop(source, x, y):
    return source.blocks["prop"][source.cell(x, y) & 31]


def objects(source):
    """DQ5 object entries [x, y, kind] for FC doors (2x3 door over the wall row above) and gates."""
    found = []
    gate = [(x, y) for y in range(source.h) for x in range(source.w) if _prop(source, x, y) == GATE]
    if gate:
        found.append([min(x for x, _ in gate) * 2, min(y for _, y in gate) * 2, GATE_KIND])
    for y in range(source.h):
        for x in range(source.w):
            if _prop(source, x, y) == DOOR:
                found.append([x * 2, y * 2 - 1, DOOR_KIND])
    if len(found) > 32:
        raise ValueError("more objects than the 32 open flags 7E:21C2-21C5")
    return found


def object_entries(found):
    """01:D2FC entries [x][y][kind][flag][end]; flag picks bit (i % 8) of 7E:21C2 + i // 8."""
    out = bytearray()
    for i, (x, y, kind) in enumerate(found):
        out += bytes((x, y, kind, (i // 8) << 4 | i % 8, 0x80 if i == len(found) - 1 else 0x00))
    return bytes(out or b"\x80")


def map_document(name, source, local, target):
    """FC layout as DQ5 commands; blocked FC cells become wall cells via attribute pass 1."""
    width, height = source.w * 2, source.h * 2
    floor = local[FLOORS[name]]
    opening = {DOOR, GATE}

    def block_at(x, y):
        return floor if _prop(source, x, y) in opening else local[source.cell(x, y) & 31]

    def blocked(x, y):
        prop = _prop(source, x, y)
        return prop & 0x80 and prop not in opening
    bits = max(10, (width * height - 1).bit_length())
    if bits > 14:
        raise ValueError(f"{name}: {width}x{height} cells exceed 14 position bits")
    commands = []
    for block in sorted({block_at(x, y) for y in range(source.h) for x in range(source.w)}):
        commands.append(["block", block])
        for y in range(source.h):
            x = 0
            while x < source.w:
                if block_at(x, y) != block:
                    x += 1
                    continue
                end = x
                while end + 1 < source.w and block_at(end + 1, y) == block:
                    end += 1
                if end - x >= 2:
                    commands.append(["fill", x * 2, y * 2, end * 2, y * 2])
                else:
                    commands.extend(["put", cx * 2, y * 2] for cx in range(x, end + 1))
                x = end + 1
    commands.append(["end"])
    entries = []
    for y in range(height):
        x = 0
        while x < width:
            if not blocked(x // 2, y // 2):
                x += 1
                continue
            end = x
            while end + 1 < width and blocked((end + 1) // 2, y // 2):
                end += 1
            run = end - x + 1
            while run:
                n = min(run, 257)
                if n == 1:
                    entries.append([x, y, 1, WALL, "one"])
                else:
                    entries.append([x, y, n, WALL, "short" if n <= 17 else "long"])
                x += n
                run -= n
            x = end + 1
    return {
        "format": "dq5map/1", "map": f"{target[0]:02X}/{target[1]:02X}",
        "kind": 1, "width": width, "height": height, "outside": 0, "zone": 0, "attr": FLOOR, "bits": bits,
        "background_hi": 0, "background_lo": 0,
        "commands": commands,
        "passes": [
            {"vertical": False, "entries": entries},
            {"vertical": False, "entries": []},
            {"vertical": True, "entries": []},
        ],
    }


def _asm_targets():
    """Compare $BC/$BD against each target; branch offsets are filled by the caller."""
    code, fixups = bytearray(), []
    for group, number in TARGETS.values():
        code += bytes((0xA5, 0xBC, 0xC9, group, 0xD0, 0x06, 0xA5, 0xBD, 0xC9, number, 0xF0, 0x00))
        fixups.append(len(code) - 1)
    return code, fixups


# Hooks run where the original code returned or called; keep the caller's A and P intact.
SAVE_A = bytes((0x08, 0xC2, 0x30, 0x48, 0xE2, 0x20))
RESTORE_A = bytes((0xC2, 0x30, 0x68, 0x28))


def hooks(block_count):
    """Machine code for the two bank-01 hooks; returns (address, bytes) and the patched call sites."""
    base = HOOK_AT & 0xFFFF
    load = bytearray(SAVE_A)
    body, fix = _asm_targets()
    fix = [len(load) + at for at in fix]
    load += body
    # Not a replaced map: rebuild the original block table only if a replaced map left its own
    # there. Before the game first builds the table it is all zero, so test for our entry.
    entry1 = BLOCK_TABLE + 2
    ours_entry1 = BLOCKS_AT + 11
    load += bytes((0xC2, 0x20, 0xAF, entry1 & 0xFF, entry1 >> 8 & 0xFF, entry1 >> 16,
                   0xC9, ours_entry1 & 0xFF, ours_entry1 >> 8, 0xE2, 0x20, 0xD0, 0x00))
    skip_restore = len(load) - 1
    load += bytes((0x20, 0xD8, 0x8C, 0x80, 0x00))
    skip_ours = len(load) - 1
    ours = len(load)
    count = block_count * 2 - 1
    load += bytes((
        0xA9, BLOCK_BANK, 0x8D, 0x23, 0x18,
        0xA9, CHR_BANK, 0x8D, 0x24, 0x18,
        0xA2, 0x00, 0x80, 0x8E, 0x25, 0x18,
        0xA9, GFX_BANK, 0x85, 0xB3,
        0xA2, NIBBLES_AT & 0xFF, NIBBLES_AT >> 8, 0x86, 0xB1,
        0xC2, 0x30,
        0xA9, count & 0xFF, count >> 8,
        0xA2, POINTERS_AT & 0xFF, POINTERS_AT >> 8,
        0xA0, BLOCK_TABLE & 0xFF, BLOCK_TABLE >> 8 & 0xFF,
        0x54, 0x7E, BLOCK_BANK,
    ))
    done = len(load)
    load += RESTORE_A + bytes((0x28, 0xAB, 0x60))
    for at in fix:
        load[at] = ours - (at + 1)
    load[skip_restore] = done - (skip_restore + 1)
    load[skip_ours] = done - (skip_ours + 1)

    pal_at = base + len(load)
    # 01:996A rewrites some BG lines per map after the palette loader, so override after it.
    pal = bytearray((0x20, 0x6A, 0x99)) + SAVE_A
    start = len(pal)
    body, fix = _asm_targets()
    pal += body
    pal += bytes((0x80, 0x00))
    skip = len(pal) - 1
    ours = len(pal)
    pal += bytes((
        0xC2, 0x30,
        0xA9, 0xDF, 0x00,
        0xA2, PALETTE_AT & 0xFF, PALETTE_AT >> 8,
        0xA0, PALETTE_LINE1 & 0xFF, PALETTE_LINE1 >> 8,
        0x54, 0x7E, GFX_BANK,
    ))
    out = len(pal)
    pal += RESTORE_A + bytes((0x60,))
    for at in fix:
        pal[start + at] = ours - (start + at + 1)
    pal[skip] = out - (skip + 1)
    code = bytes(load + pal)
    if HOOK_AT + len(code) > HOOK_END:
        raise ValueError("bank 01 hooks overflow the free tail")
    sites = [
        (0x01936E, bytes((0x28, 0xAB, 0x60)), bytes((0x4C, base & 0xFF, base >> 8))),
        (0x0193B2, bytes((0x20, 0x6A, 0x99)), bytes((0x20, pal_at & 0xFF, pal_at >> 8))),
    ]
    return code, sites


def water_animation(water_ids):
    """Per-frame routine for the replaced maps: every WATER_PERIOD frames queue the next water
    frame's four CHR for the NMI DMA list (00:8F53: VRAM word 1C1C+2i, bytes 1C26+2i, source
    1C0D+3i, count $BA), the same list 03:D4B5 uses for DQ5's own animated tiles."""
    tick, frame = 0x7E1ECE, 0x7E1EC2
    routine_at = ANIM_AT + 0x60
    # The queueing body is longer than a relative branch reaches, so skip it with BCS/JMP.
    routine = bytearray((0x08, 0xC2, 0x30, 0xAF) + tuple(tick.to_bytes(3, "little")) + (
        0x1A, 0xC9, WATER_PERIOD, 0x00, 0xB0, 0x03, 0x4C, 0x00, 0x00))
    skip = len(routine) - 2
    routine += bytes((0xAF,) + tuple(frame.to_bytes(3, "little")) + (0x1A, 0xC9, len(WATER_FRAMES), 0x00,
                     0x90, 0x03, 0xA9, 0x00, 0x00, 0x8F) + tuple(frame.to_bytes(3, "little")))
    routine += bytes((0x0A,) * 7 + (0xAA,))
    for k, chr_id in enumerate(water_ids):
        slot = 0x7E6000 + chr_id * 2
        source = (WATER_AT & 0xFFFF) + k * 32
        routine += bytes((0xAF,) + tuple(slot.to_bytes(3, "little")) + (
            0x29, 0xFF, 0x03, 0x0A, 0x0A, 0x0A, 0x0A, 0x18, 0x69, 0x00, 0x20,
            0x8F, 0x1C + 2 * k, 0x1C, 0x00,
            0xA9, 0x20, 0x00, 0x8F, 0x26 + 2 * k, 0x1C, 0x00,
            0x8A, 0x18, 0x69, source & 0xFF, source >> 8, 0x8F, 0x0D + 3 * k, 0x1C, 0x00,
            0xE2, 0x20, 0xA9, WATER_AT >> 16, 0x8F, 0x0F + 3 * k, 0x1C, 0x00, 0xC2, 0x20))
    routine += bytes((0xE2, 0x20, 0xA9, len(water_ids), 0x85, 0xBA, 0xC2, 0x20, 0xA9, 0x00, 0x00))
    store = (routine_at + len(routine)) & 0xFFFF
    routine[skip:skip + 2] = store.to_bytes(2, "little")
    routine += bytes((0x8F,) + tuple(tick.to_bytes(3, "little")) + (0x28, 0x6B))

    wrapper = bytearray((0x22, 0xD0, 0xF7, 0x15)) + SAVE_A
    start = len(wrapper)
    body, fix = _asm_targets()
    wrapper += body + bytes((0x80, 0x00))
    out_fix = len(wrapper) - 1
    ours = len(wrapper)
    wrapper += bytes((0xC2, 0x20, 0xA9, routine_at & 0xFF, routine_at >> 8 & 0xFF, 0x8F, 0xA6, 0x1A, 0x7E,
                      0xE2, 0x20, 0xA9, routine_at >> 16, 0x8F, 0xA8, 0x1A, 0x7E,
                      0xA9, 0x00, 0x8F, 0xCE, 0x1E, 0x7E, 0x8F, 0xCF, 0x1E, 0x7E,
                      0x8F, 0xC2, 0x1E, 0x7E, 0x8F, 0xC3, 0x1E, 0x7E))
    out = len(wrapper)
    wrapper += RESTORE_A + bytes((0x6B,))
    for at in fix:
        wrapper[start + at] = ours - (start + at + 1)
    wrapper[out_fix] = out - (out_fix + 1)
    if len(wrapper) > routine_at - ANIM_AT:
        raise ValueError("animation wrapper overlaps the per-frame routine")
    code = bytes(wrapper) + bytes(routine_at - ANIM_AT - len(wrapper)) + bytes(routine)
    sites = [(at, bytes((0x22, 0xD0, 0xF7, 0x15)), bytes((0x22,)) + ANIM_AT.to_bytes(3, "little"))
             for at in ROUTINE_CALLS]
    return code, sites


def object_hook(base, tables):
    """01:F42D (LDX #$0009 after 01:F3F9 found the map's entries in Y) -> pick our entries for the
    replaced maps. Everything that reads the object table (drawing 01:F3E8, とびら 01:DE62, 01:D920,
    01:F122) goes through 01:F3F9, so one hook covers them. Returns the code and its call site."""
    code = bytearray()
    for (group, number), at in tables.items():
        offset = at - (OBJECT_TABLE & 0xFFFF)
        code += bytes((0xA5, 0xBC, 0xC9, group, 0xD0, 0x09, 0xA5, 0xBD, 0xC9, number, 0xD0, 0x03,
                       0xA0, offset & 0xFF, offset >> 8))
    code += bytes((0xA2, 0x09, 0x00, 0x60))
    return bytes(code), (0x01F42D, bytes((0xA2, 0x09, 0x00)), bytes((0x20, base & 0xFF, base >> 8)))


def _hex(data):
    return " ".join(f"{b:02X}" for b in data)


def _cpu(addr):
    return f"{addr >> 16:02X}:{addr & 0xFFFF:04X}"


def water_frames(assets, chr_data, water_ids):
    """Planar CHR of each water frame in the water block's quadrant order; frame 0 must be the map's."""
    frames = []
    for name in WATER_FRAMES:
        image = assets[name]
        frames.append([_planar(_tiles(image, x, y)[0]) for y in (0, 8) for x in (0, 8)])
    if [chr_data[i] for i in water_ids] != frames[0]:
        raise ValueError("the map's water block is not the first water frame")
    return b"".join(b"".join(f) for f in frames)


def build(dq5_path, dq4_path, out):
    dq5 = Path(dq5_path).read_bytes()
    prg = ines.prg(Path(dq4_path).read_bytes())
    assets = create_assets()
    chr_data, chr_banks, block_words, maps, palette = build_graphics(prg, assets)
    water_blocks = {local[WATER_BLOCK] for _, local in maps.values() if WATER_BLOCK in local}
    if len(water_blocks) != 1:
        raise ValueError(f"expected one shared water block, got {water_blocks}")
    water_ids = block_words[water_blocks.pop()]
    anim_code, anim_sites = water_animation(water_ids)
    out.mkdir(parents=True, exist_ok=True)

    blocks, pointers = bytearray(), bytearray()
    for words in block_words:
        pointers += (BLOCKS_AT + len(blocks)).to_bytes(2, "little")
        blocks += bytes((0x09, 0x00, 0x00)) + b"".join(w.to_bytes(2, "little") for w in words)
    if BLOCKS_AT + len(blocks) > POINTERS_AT:
        raise ValueError("block definitions overflow into the pointer table")
    nibbles = bytearray((len(chr_banks) + 1) // 2)
    for i, bank in enumerate(chr_banks):
        nibbles[i // 2] |= (bank - 1) << (0 if i & 1 else 4)
    colors = b"".join(_bgr555(palette[i * 3:i * 3 + 3]).to_bytes(2, "little") for i in range(16, 128))

    orig_entry1 = 0x8000 + 3 + 2 * (((dq5[_off(0x168000)] >> 3 & 7) + 1) * ((dq5[_off(0x168000)] & 7) + 1))
    if orig_entry1 == BLOCKS_AT + 11:
        raise ValueError("original first block has our block size; dirty-table check would not work")
    code, sites = hooks(len(block_words))
    found = {name: objects(source) for name, (source, _) in maps.items()}
    tables, at = {}, HOOK_AT + len(code)
    entries = bytearray()
    for name in maps:
        tables[TARGETS[name]] = (at + len(entries)) & 0xFFFF
        entries += object_entries(found[name])
    hook_at = at + len(entries)
    obj_code, obj_site = object_hook(hook_at & 0xFFFF, tables)
    code += bytes(entries) + obj_code
    if HOOK_AT + len(code) > HOOK_END:
        raise ValueError(f"bank 01 tail overflows by {HOOK_AT + len(code) - HOOK_END} bytes")
    sites.append(obj_site)

    (out / "chr.bin").write_bytes(b"".join(chr_data))
    (out / "blocks.bin").write_bytes(blocks)
    writes = [
        {"at": _cpu(CHR_BANK << 16 | 0x8000), "file": "chr.bin", "note": f"환경 CHR {len(chr_data)}개"},
        {"at": _cpu(BLOCK_BANK << 16 | BLOCKS_AT), "file": "blocks.bin", "note": f"2x2 블록 {len(block_words)}개"},
        {"at": _cpu(BLOCK_BANK << 16 | POINTERS_AT), "hex": _hex(pointers), "note": "7E:B000 에 복사할 블록 포인터"},
        {"at": _cpu(GFX_BANK << 16 | NIBBLES_AT), "hex": _hex(nibbles), "note": "CHR 팔레트 니블"},
        {"at": _cpu(GFX_BANK << 16 | PALETTE_AT), "hex": _hex(colors), "note": "BG 팔레트 1~7번 줄"},
        {"at": _cpu(HOOK_AT), "hex": _hex(code), "note": "바꾼 맵이면 CHR·블록·팔레트를 그래픽 뱅크로"},
        {"at": _cpu(WATER_AT), "hex": _hex(water_frames(assets, chr_data, water_ids)), "note": "물 그림 3장"},
        {"at": _cpu(ANIM_AT), "hex": _hex(anim_code), "note": "바꾼 맵의 매 프레임 물 루틴"},
    ]
    for at, orig, new in sites + anim_sites:
        writes.append({"at": _cpu(at), "hex": _hex(new), "orig": _hex(orig), "note": "환경 맵 훅"})
    rom = Rom(dq5)
    at = MAPS_AT
    report = {"chr": len(chr_data), "blocks": len(block_words), "water_chr": list(water_ids),
              "bank01_bytes": len(code), "objects": found, "maps": {}}
    for name, (source, local) in maps.items():
        target = TARGETS[name]
        doc = map_document(name, source, local, target)
        (out / f"{name}.dq5map.json").write_text(json.dumps(doc, ensure_ascii=False) + "\n")
        record = encode(doc)
        (out / f"{name}.bin").write_bytes(record)
        if (at & 0xFFFF) + len(record) > 0x10000:
            raise ValueError("map records must stay inside one bank below 40")
        writes.append({"at": _cpu(at), "file": f"{name}.bin", "note": f"{name} 맵 레코드"})
        pointer = lorom(pointer_addr(rom, *target))
        writes.append({"at": f"0x{pointer:06X}", "hex": _hex(at.to_bytes(3, "little")),
                       "orig": _hex(dq5[pointer:pointer + 3]), "note": f"{target[0]:02X}/{target[1]:02X} 맵 포인터"})
        report["maps"][name] = {"target": doc["map"], "cells": [doc["width"], doc["height"]],
                                "record_bytes": len(record), "commands": len(doc["commands"]),
                                "wall_entries": len(doc["passes"][0]["entries"]), "at": _cpu(at)}
        at += len(record)
    patch = {"format": "dq5patch/1", "name": "dq4-environment", "rom_size": 4, "writes": writes}
    (out / "dq4-environment.dq5patch.json").write_text(json.dumps(patch, ensure_ascii=False, indent=1) + "\n")
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n")
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dq5", default="rom/dq5.sfc")
    ap.add_argument("--dq4", default="rom/dq4.nes")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    print(json.dumps(build(args.dq5, args.dq4, args.out), ensure_ascii=False))


if __name__ == "__main__":
    main()
