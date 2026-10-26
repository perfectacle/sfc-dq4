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
from collections import Counter
from pathlib import Path

from kr_patch.fc import ines

TOOLS = Path(__file__).resolve().parent
DQ5_TOOLS = TOOLS.parents[1] / "dq5" / "tools"
for path in (TOOLS, DQ5_TOOLS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dq4environmentart import create_assets, palette_variant  # noqa: E402
from dq4environmentmap import block_prop, map_palette, prepare_maps, sheet_art  # noqa: E402
from dq5mapwrite import Rom, encode, lorom, pointer_addr  # noqa: E402

# FC map name -> replaced DQ5 interior map. Targets must have no animated tiles,
# preloaded blocks, reserved slots, per-map routine or objects (01:D2FC): those run with the original
# block numbers or common tiles and would overwrite the new map. 08/00 is also out: the object
# drawer 01:F3D9 sends it to its own routine 01:FCD5 instead of the table.
TARGETS = {
    "burland": (0x03, 0x00), "gardenburg": (0x16, 0x02), "stancia": (0x09, 0x00), "stancia-03": (0x09, 0x01),
    "stancia-06": (0x09, 0x04), "mintos": (0x0A, 0x01), "imuru": (0x19, 0x02), "saran-04": (0x0A, 0x02),
    "seaside": (0x0B, 0x01), "seaside-01": (0x0D, 0x03), "rosaryhill": (0x0D, 0x04), "rosaryhill-01": (0x0E, 0x01),
    "shrine-2a": (0x0E, 0x03), "konenbery-06": (0x12, 0x00), "attemut-05": (0x13, 0x00), "attemut-07": (0x16, 0x01),
    # One or two maps of each other town and castle sheet, picked for block coverage and few doors:
    # door objects must fit the bank 01 tail.
    "1A-01": (0x08, 0x02), "03-02": (0x08, 0x03), "17-00": (0x03, 0x0B), "0B-00": (0x03, 0x0E),
    "08-01": (0x03, 0x0F), "10-00": (0x03, 0x10), "16-00": (0x04, 0x01), "0F-00": (0x04, 0x08),
    "0A-00": (0x04, 0x09), "04-06": (0x0A, 0x06), "00-01": (0x04, 0x0B), "09-01": (0x04, 0x0C),
    "00-00": (0x05, 0x00), "05-01": (0x06, 0x03), "02-01": (0x06, 0x06), "01-00": (0x08, 0x01),
    # Harbour, theatre and the smaller sheets; none of these has a door.
    "11-00": (0x03, 0x03), "1A-00": (0x03, 0x09), "0E-00": (0x04, 0x0A), "15-03": (0x0A, 0x08),
    "34-06": (0x0A, 0x0B), "2E-00": (0x0B, 0x03),
    # One doorless map of several dungeon and tower families.
    "34-00": (0x0D, 0x01), "36-01": (0x0D, 0x02), "2F-00": (0x11, 0x01), "43-00": (0x12, 0x02),
    "46-00": (0x12, 0x04), "31-02": (0x12, 0x06), "48-01": (0x12, 0x07), "2D-00": (0x15, 0x00),
}
# Further banks for map records once the first one reaches the library.
MAPS_NEXT = (0x3E8000, 0x3F8000)
CHR_BANK = 0x40
GFX_BANK = 0x41
NIBBLES_AT = 0x8000
PALETTE_AT = 0x8400
BLOCK_BANK = 0x3D
BLOCKS_AT = 0x8000
POINTERS_AT = 0x8C00
MAPS_AT = 0x3D9000
HOOK_AT = 0x01FED0
HOOK_END = 0x020000
BLOCK_TABLE = 0x7EB000
PALETTE_LINE1 = 0x3934
WALL = 8
FLOOR = 1
WATER_FRAMES = ("water0", "water1", "water2")
WATER_AT = 0x41F000
WATER_PERIOD = 24
LIB_AT = 0x3DE000
# FC door properties and the DQ5 objects (01:D2FC kinds) that replace them. The record under an
# object is the map's floor so the cell is walkable once the object opens; closed objects block
# their last row themselves (cell +1 bit7).
DOORS = {0x94, 0x95, 0x96}
GATE = 0xA0
OPENINGS = DOORS | {GATE}
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
    for group, number, name, source, counts, prepared, palette in prepare_maps(prg, assets, TARGETS):
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


def water_block(source, local):
    """New block id of the map's water, or None; every sheet's water uses the same art."""
    found = {local[b] for b, (asset, _) in sheet_art(source.prg, source.t).items() if asset == WATER_FRAMES[0] and b in local}
    if len(found) > 1:
        raise ValueError(f"{len(found)} water blocks in one map")
    return found.pop() if found else None


def _prop(source, x, y):
    return block_prop(source, source.cell(x, y) & 31)


def objects(source):
    """DQ5 object entries [x, y, kind] for FC doors (2x3 door over the wall row above) and gates."""
    found = []
    gate = {(x, y) for y in range(source.h) for x in range(source.w) if _prop(source, x, y) == GATE}
    for x, y in sorted(gate, key=lambda c: (c[1], c[0])):
        if (x, y) in gate:
            found.append([x * 2, y * 2, GATE_KIND])
            gate -= {(x + dx, y + dy) for dx in (0, 1) for dy in (0, 1)}
    for y in range(source.h):
        for x in range(source.w):
            if _prop(source, x, y) in DOORS:
                found.append([x * 2, y * 2 - 1, DOOR_KIND])
    if len(found) > 32:
        raise ValueError("more objects than the 32 open flags 7E:21C2-21C5")
    return found


def door_floor(source, x, y):
    """FC block drawn under a door or gate: the nearest walkable cell, below first on ties. Water
    gates in a wall row have none; they take the map's most common walkable block."""
    best = None
    for ny in range(max(0, y - 3), min(source.h, y + 4)):
        for nx in range(max(0, x - 3), min(source.w, x + 4)):
            if _prop(source, nx, ny) & 0x80:
                continue
            key = (abs(nx - x) + abs(ny - y), ny < y, abs(nx - x))
            if best is None or key < best[0]:
                best = (key, source.cell(nx, ny) & 31)
    if best is None:
        return Counter(source.cell(cx, cy) & 31 for cy in range(source.h) for cx in range(source.w)
                       if not _prop(source, cx, cy) & 0x80).most_common(1)[0][0]
    return best[1]


def object_entries(found):
    """01:D2FC entries [x][y][kind][flag][end]; flag picks bit (i % 8) of 7E:21C2 + i // 8."""
    out = bytearray()
    for i, (x, y, kind) in enumerate(found):
        out += bytes((x, y, kind, (i // 8) << 4 | i % 8, 0x80 if i == len(found) - 1 else 0x00))
    return bytes(out)


def map_document(name, source, local, target):
    """FC layout as DQ5 commands; blocked FC cells become wall cells via attribute pass 1."""
    width, height = source.w * 2, source.h * 2
    def block_at(x, y):
        return local[door_floor(source, x, y) if _prop(source, x, y) in OPENINGS else source.cell(x, y) & 31]

    def blocked(x, y):
        prop = _prop(source, x, y)
        return prop & 0x80 and prop not in OPENINGS
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


class _Asm:
    """Two-pass assembler for the few hand-written routines: bytes plus label references."""

    def __init__(self, origin):
        self.origin, self.items = origin, []

    def b(self, *values):
        self.items.append(("b", bytes(values)))
        return self

    def label(self, name):
        self.items.append(("label", name))
        return self

    def rel(self, opcode, name):
        self.items.append(("rel", opcode, name))
        return self

    def word(self, opcode, name, offset=0):
        """opcode + 16-bit address of a label plus offset (opcode None: the value alone)."""
        self.items.append(("word", opcode, name, offset))
        return self

    def long(self, opcode, name, offset=0):
        self.items.append(("long", opcode, name, offset))
        return self

    def assemble(self, external=None):
        labels, at = dict(external or {}), self.origin
        size = {"b": lambda it: len(it[1]), "label": lambda it: 0, "rel": lambda it: 2,
                "word": lambda it: 2 if it[1] is None else 3, "long": lambda it: 4}
        for item in self.items:
            if item[0] == "label":
                labels[item[1]] = at
            at += size[item[0]](item)
        out, at = bytearray(), self.origin
        for item in self.items:
            kind = item[0]
            if kind == "b":
                out += item[1]
            elif kind == "rel":
                distance = labels[item[2]] - (at + 2)
                if not -128 <= distance <= 127:
                    raise ValueError(f"branch to {item[2]} is {distance} bytes away")
                out += bytes((item[1], distance & 0xFF))
            elif kind == "word":
                target = (labels[item[2]] + item[3]) & 0xFFFF
                out += (bytes((item[1],)) if item[1] is not None else b"") + target.to_bytes(2, "little")
            elif kind == "long":
                out += bytes((item[1],)) + (labels[item[2]] + item[3]).to_bytes(3, "little")
            at += size[kind](item)
        return bytes(out), labels


# Hooked code paths keep the caller's A, X, Y and P.
_ENTER = (0x08, 0xC2, 0x30, 0x48, 0xDA, 0x5A)
_LEAVE = (0xC2, 0x30, 0x7A, 0xFA, 0x68, 0x28)


def engine_code(block_count, water_ids, palettes, entries, waters):
    """Routines in BLOCK_BANK (LIB_AT) and the bank-01 stubs that call them.

    palettes: per target, the bank-GFX address of its 224-byte BG palette.
    entries: per target, its 01:D2FC-format object entries (placed in bank 01, since the object
    reader 01:F3F9 indexes $D2FC,Y with the data bank at 01).
    waters: per target, whether the map has water.
    Returns (library bytes, bank-01 bytes, patched sites)."""
    targets = list(TARGETS.values())
    stubs = _Asm(HOOK_AT)
    stubs.label("s_load").long(0x22, "load").b(0x28, 0xAB, 0x60)
    stubs.label("s_pal").b(0x20, 0x6A, 0x99).long(0x22, "pal").b(0x60)
    stubs.label("s_obj").long(0x22, "obj").b(0x60)
    stubs.label("s_rebuild").b(0x20, 0xD8, 0x8C, 0x6B)
    stubs.label("no_objects").b(0x80)
    for i, data in enumerate(entries):
        if data:
            stubs.label(f"objects{i}").b(*data)

    lib = _Asm(LIB_AT)
    lib.label("targets")
    for group, number in targets:
        lib.b(group, number)
    lib.b(0xFF).label("palettes")
    for address in palettes:
        lib.b(address & 0xFF, address >> 8)
    lib.label("waters")
    for flag in waters:
        lib.b(int(flag), 0)
    lib.label("objects")
    for i, data in enumerate(entries):
        lib.word(None, f"objects{i}" if data else "no_objects", -(OBJECT_TABLE & 0xFFFF))

    # find: carry set and X = target index * 2 if $BC/$BD is a replaced map.
    lib.label("find").b(0x08, 0xE2, 0x30, 0xA2, 0x00)
    lib.label("find_loop").long(0xBF, "targets").b(0xC9, 0xFF).rel(0xF0, "find_none")
    lib.b(0xC5, 0xBC).rel(0xD0, "find_next").long(0xBF, "targets", 1).b(0xC5, 0xBD).rel(0xF0, "find_hit")
    lib.label("find_next").b(0xE8, 0xE8).rel(0x80, "find_loop")
    lib.label("find_none").b(0x28, 0x18, 0x6B)
    lib.label("find_hit").b(0x28, 0x38, 0x6B)

    # load (end of 01:92E2): new CHR bank, nibble table and block table for a replaced map; any
    # other map gets the original block table back if a replaced map left its own there.
    count = block_count * 2 - 1
    lib.label("load").b(*_ENTER).long(0x22, "find").rel(0xB0, "load_ours")
    lib.b(0xC2, 0x20, 0xAF, 0x02, 0xB0, 0x7E, 0xC9, (BLOCKS_AT + 11) & 0xFF, (BLOCKS_AT + 11) >> 8)
    lib.rel(0xD0, "load_done").long(0x22, "s_rebuild").rel(0x80, "load_done")
    lib.label("load_ours").b(
        0xE2, 0x20, 0xA9, BLOCK_BANK, 0x8D, 0x23, 0x18, 0xA9, CHR_BANK, 0x8D, 0x24, 0x18,
        0xA9, GFX_BANK, 0x85, 0xB3,
        0xC2, 0x20, 0xA9, 0x00, 0x80, 0x8D, 0x25, 0x18, 0xA9, NIBBLES_AT & 0xFF, NIBBLES_AT >> 8, 0x85, 0xB1,
        0xA9, count & 0xFF, count >> 8, 0xA2, POINTERS_AT & 0xFF, POINTERS_AT >> 8,
        0xA0, BLOCK_TABLE & 0xFF, BLOCK_TABLE >> 8 & 0xFF, 0x54, 0x7E, BLOCK_BANK)
    lib.label("load_done").b(*_LEAVE, 0x6B)

    # pal (after 01:996A): copy the target's BG lines 1-7.
    lib.label("pal").b(*_ENTER).long(0x22, "find").rel(0x90, "pal_done")
    lib.long(0xBF, "palettes").b(0xAA, 0xA9, 0xDF, 0x00, 0xA0, PALETTE_LINE1 & 0xFF, PALETTE_LINE1 >> 8,
                                 0x54, 0x7E, GFX_BANK)
    lib.label("pal_done").b(*_LEAVE, 0x6B)

    # obj (01:F42D): Y = the target's object entries, then the replaced LDX #$0009.
    lib.label("obj").b(0x08, 0xC2, 0x30, 0x48, 0xDA).long(0x22, "find").rel(0x90, "obj_keep")
    lib.long(0xBF, "objects").b(0xA8)
    lib.label("obj_keep").b(0xC2, 0x30, 0xFA, 0x68, 0x28, 0xA2, 0x09, 0x00, 0x6B)

    # wrap (calls of 15:F7D0): after the original choice, a replaced map with water runs the water
    # routine. Without water its CHR have no slot (7E:6000 reads 0), and the routine would write
    # them over slot 0, the blank tile that fills BG1.
    lib.label("wrap").b(0x22, 0xD0, 0xF7, 0x15, 0x08, 0xC2, 0x30, 0x48, 0xDA).long(0x22, "find")
    lib.rel(0x90, "wrap_out").long(0xBF, "waters").rel(0xF0, "wrap_out").b(0xC2, 0x20).word(0xA9, "water").b(0x8F, 0xA6, 0x1A, 0x7E, 0xE2, 0x20)
    lib.b(0xA9, LIB_AT >> 16, 0x8F, 0xA8, 0x1A, 0x7E, 0xA9, 0x00)
    for counter in (0x1ECE, 0x1ECF, 0x1EC2, 0x1EC3):
        lib.b(0x8F, counter & 0xFF, counter >> 8, 0x7E)
    lib.label("wrap_out").b(0xC2, 0x30, 0xFA, 0x68, 0x28, 0x6B)

    # water: every WATER_PERIOD frames queue the next water frame's four CHR on the NMI DMA list
    # (00:8F53: VRAM word 1C1C+2i, bytes 1C26+2i, source 1C0D+3i, count $BA) that 03:D4B5 uses.
    tick, frame = 0x7E1ECE, 0x7E1EC2
    lib.label("water").b(0x08, 0xC2, 0x30, 0xAF, *tick.to_bytes(3, "little"), 0x1A, 0xC9, WATER_PERIOD, 0x00)
    lib.b(0xB0, 0x03).word(0x4C, "water_store")
    lib.b(0xAF, *frame.to_bytes(3, "little"), 0x1A, 0xC9, len(WATER_FRAMES), 0x00, 0x90, 0x03, 0xA9, 0x00, 0x00,
          0x8F, *frame.to_bytes(3, "little"), *(0x0A,) * 7, 0xAA)
    for k, chr_id in enumerate(water_ids):
        source = (WATER_AT & 0xFFFF) + k * 32
        lib.b(0xAF, *(0x7E6000 + chr_id * 2).to_bytes(3, "little"),
              0x29, 0xFF, 0x03, 0x0A, 0x0A, 0x0A, 0x0A, 0x18, 0x69, 0x00, 0x20, 0x8F, 0x1C + 2 * k, 0x1C, 0x00,
              0xA9, 0x20, 0x00, 0x8F, 0x26 + 2 * k, 0x1C, 0x00,
              0x8A, 0x18, 0x69, source & 0xFF, source >> 8, 0x8F, 0x0D + 3 * k, 0x1C, 0x00,
              0xE2, 0x20, 0xA9, WATER_AT >> 16, 0x8F, 0x0F + 3 * k, 0x1C, 0x00, 0xC2, 0x20)
    lib.b(0xE2, 0x20, 0xA9, len(water_ids), 0x85, 0xBA, 0xC2, 0x20, 0xA9, 0x00, 0x00)
    lib.label("water_store").b(0x8F, *tick.to_bytes(3, "little"), 0x28, 0x6B)

    _, stub_labels = stubs.assemble({"load": 0, "pal": 0, "obj": 0})
    lib_code, lib_labels = lib.assemble(stub_labels)
    stub_code, stub_labels = stubs.assemble(lib_labels)
    if HOOK_AT + len(stub_code) > HOOK_END:
        raise ValueError(f"bank 01 tail overflows by {HOOK_AT + len(stub_code) - HOOK_END} bytes")
    if LIB_AT + len(lib_code) > (LIB_AT | 0xFFFF) + 1:
        raise ValueError("library overflows its bank")
    sites = [
        (0x01936E, bytes((0x28, 0xAB, 0x60)), bytes((0x4C,)) + (stub_labels["s_load"] & 0xFFFF).to_bytes(2, "little")),
        (0x0193B2, bytes((0x20, 0x6A, 0x99)), bytes((0x20,)) + (stub_labels["s_pal"] & 0xFFFF).to_bytes(2, "little")),
        (0x01F42D, bytes((0xA2, 0x09, 0x00)), bytes((0x20,)) + (stub_labels["s_obj"] & 0xFFFF).to_bytes(2, "little")),
    ] + [(at, bytes((0x22, 0xD0, 0xF7, 0x15)), bytes((0x22,)) + lib_labels["wrap"].to_bytes(3, "little"))
         for at in ROUTINE_CALLS]
    return lib_code, stub_code, sites


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
    water_blocks = {water_block(source, local) for source, local in maps.values()} - {None}
    if len(water_blocks) != 1:
        raise ValueError(f"expected one shared water block, got {water_blocks}")
    water_ids = block_words[water_blocks.pop()]
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

    orig_entry1 = 0x8000 + 3 + 2 * (((dq5[_off(0x168000)] >> 3 & 7) + 1) * ((dq5[_off(0x168000)] & 7) + 1))
    if orig_entry1 == BLOCKS_AT + 11:
        raise ValueError("original first block has our block size; dirty-table check would not work")
    variants = sorted({map_palette(name, source.t) for name, (source, _) in maps.items()})
    palette_at = {kind: PALETTE_AT + 0x100 * i for i, kind in enumerate(variants)}
    found = {name: objects(source) for name, (source, _) in maps.items()}
    lib_code, stub_code, sites = engine_code(
        len(block_words), water_ids,
        [palette_at[map_palette(name, maps[name][0].t)] for name in TARGETS],
        [object_entries(found[name]) for name in TARGETS],
        [water_block(*maps[name]) is not None for name in TARGETS])

    (out / "chr.bin").write_bytes(b"".join(chr_data))
    (out / "blocks.bin").write_bytes(blocks)
    writes = [
        {"at": _cpu(CHR_BANK << 16 | 0x8000), "file": "chr.bin", "note": f"환경 CHR {len(chr_data)}개"},
        {"at": _cpu(BLOCK_BANK << 16 | BLOCKS_AT), "file": "blocks.bin", "note": f"2x2 블록 {len(block_words)}개"},
        {"at": _cpu(BLOCK_BANK << 16 | POINTERS_AT), "hex": _hex(pointers), "note": "7E:B000 에 복사할 블록 포인터"},
        {"at": _cpu(GFX_BANK << 16 | NIBBLES_AT), "hex": _hex(nibbles), "note": "CHR 팔레트 니블"},
        {"at": _cpu(HOOK_AT), "hex": _hex(stub_code), "note": "엔진 훅 중계 코드와 맵 위 물체 항목"},
        {"at": _cpu(WATER_AT), "hex": _hex(water_frames(assets, chr_data, water_ids)), "note": "물 그림 3장"},
        {"at": _cpu(LIB_AT), "hex": _hex(lib_code), "note": "바꾼 맵 표와 불러오기·팔레트·물체·물 루틴"},
    ]
    for kind, at in palette_at.items():
        flat = palette_variant(kind)
        data = b"".join(_bgr555(flat[i * 3:i * 3 + 3]).to_bytes(2, "little") for i in range(16, 128))
        writes.append({"at": _cpu(GFX_BANK << 16 | at), "hex": _hex(data), "note": f"BG 팔레트 1~7번 줄({kind})"})
    for at, orig, new in sites:
        writes.append({"at": _cpu(at), "hex": _hex(new), "orig": _hex(orig), "note": "환경 맵 훅"})
    rom = Rom(dq5)
    at, spare = MAPS_AT, list(MAPS_NEXT)
    report = {"chr": len(chr_data), "blocks": len(block_words), "water_chr": list(water_ids),
              "bank01_bytes": len(stub_code), "library_bytes": len(lib_code), "objects": found, "maps": {}}
    for name, (source, local) in maps.items():
        target = TARGETS[name]
        doc = map_document(name, source, local, target)
        (out / f"{name}.dq5map.json").write_text(json.dumps(doc, ensure_ascii=False) + "\n")
        record = encode(doc)
        (out / f"{name}.bin").write_bytes(record)
        if at < LIB_AT <= at + len(record) or (at & 0xFFFF) + len(record) > 0x10000:
            if not spare:
                raise ValueError("map records overflow the banks below 40")
            at = spare.pop(0)
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
