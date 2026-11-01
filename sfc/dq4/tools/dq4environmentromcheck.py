"""Check the environment maps inside DQ5 with MesenCE.

For each replaced map: warp in from the ship cabin, dump WRAM/VRAM/CGRAM, redraw the
whole map from the game's own cell buffer and compare it pixel by pixel with the
offline FC-layout render; compare the walkable-layer nibbles with the FC block
properties. Then leave to an untouched map and compare its cell buffer and block
table with the same warp on the original ROM.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from kr_patch.fc import ines
from PIL import Image

TOOLS = Path(__file__).resolve().parent
DQ5_TOOLS = TOOLS.parents[1] / "dq5" / "tools"
for path in (TOOLS, DQ5_TOOLS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import dq5map  # noqa: E402
from dq5exitcheck import dp86_allowed, warp_exit  # noqa: E402
from dq4environmentart import create_assets  # noqa: E402
from dq4environmentmap import prepare_maps, render_maps  # noqa: E402
from dq4environmentmap import block_prop  # noqa: E402
from dq4environmentrom import (COUNTER_PROPS, DOOR_KIND, FLOOR, GATE_KIND, OPENINGS, door_floor, GROUPS, MAPS, STAIRS, WALL, WATER_SLOT, water_block,  # noqa: E402
                               WATER_FRAMES, WATER_PERIOD, build_graphics, objects, water_frames)
import dq4mesen  # noqa: E402

OBJECT_SIZE = {DOOR_KIND: (2, 3), GATE_KIND: (4, 4)}  # noqa: E402
# Cell +4/+7 values 2A:F6B8 counts as exits (2A:FF37).
EXIT_MARKS = {0x85, 0xA1, 0xB3, 0xCC}

WARP = DQ5_TOOLS / "lua" / "dq5warp.lua"
DUMP = TOOLS / "lua" / "dq4environmentdump.lua"
# An untouched map with no animation, reached after leaving a replaced map.
CONTROL = (0x01, 0x03)
# Untouched maps compared with the original ROM: 1A/00 and 19/00 have their door entries more than 0x100
# bytes after 01:D2FC (the object hook must keep the high byte of Y, or those doors vanish); 03/00, 19/02
# and 06/06 are DQ5 maps no longer replaced. Needs a ROM with the GROUPS maps (dq4groupbuild.py).
UNTOUCHED = ((0x1A, 0x00), (0x19, 0x00), (0x03, 0x00), (0x19, 0x02), (0x06, 0x06))


def _run(mesence, rom, script, env):
    full = dict(os.environ, **{k: str(v) for k, v in env.items()})
    dq4mesen.testrunner(str(mesence), str(rom), str(script), env=full,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600, check=False)


def warp(mesence, rom, state, to, out, name, test=False, **extra):
    """Warp in and save; with test, also press each direction after saving (dq5warp TEST)."""
    out.mkdir(parents=True, exist_ok=True)
    # dq5warp overwrites the ship ladder's exit entry, which moves with the exit tables.
    env = {"STATE": state, "TO": to, "SHOT_DIR": out, "SAVE": f"{name}.mss", "MAXF": 1500,
           "WARPEXIT": f"{warp_exit(rom):X}", "DP86OK": dp86_allowed(rom), **extra}
    if test:
        env.setdefault("TEST", "left:40,up:40,right:40,down:40")
    _run(mesence, rom, WARP, env)
    log = (out / "warp.txt").read_text()
    saved = out / f"{name}.mss"
    if "arrived" not in log or not saved.exists():
        raise RuntimeError(f"warp to {to} failed: {log[-300:]}")
    return saved, "moved=yes" in log


def dump(mesence, rom, state, out, frames=10):
    out.mkdir(parents=True, exist_ok=True)
    _run(mesence, rom, DUMP, {"STATE": state, "OUT": out, "FRAMES": frames})
    return tuple((out / f).read_bytes() for f in ("wram.bin", "vram.bin", "cgram.bin"))


BLANK_TILE = 0x2000 * 2


def _rgb(cgram, index):
    v = cgram[index * 2] | cgram[index * 2 + 1] << 8
    return tuple((c << 3 | c >> 2) for c in (v & 31, v >> 5 & 31, v >> 10 & 31))


def redraw(wram, vram, cgram, known):
    """Draw the map from the cell buffer: lower layer, then non-zero upper pixels."""
    width, height = wram[0xBF], wram[0xC0]
    words = [w for o in range(0xC000, 0xC000 + width * height * 8, 8) for w in
             (wram[o + 2] | wram[o + 3] << 8, wram[o + 5] | wram[o + 6] << 8) if w & 0x3FF]
    base = _char_base(vram, words, known)
    image = Image.new("RGB", (width * 8, height * 8))
    pixels = image.load()
    for cy in range(height):
        for cx in range(width):
            o = 0xC000 + (cy * width + cx) * 8
            for layer, at in ((0, 2), (1, 5)):
                word = wram[o + at] | wram[o + at + 1] << 8
                if not word & 0x3FF and layer:
                    continue
                tile = base + (word & 0x3FF) * 32
                pal = word >> 10 & 7
                for y in range(8):
                    sy = 7 - y if word & 0x8000 else y
                    planes = [vram[tile + sy * 2], vram[tile + sy * 2 + 1], vram[tile + 16 + sy * 2],
                              vram[tile + 16 + sy * 2 + 1]]
                    for x in range(8):
                        sx = x if word & 0x4000 else 7 - x
                        v = sum((planes[p] >> sx & 1) << p for p in range(4))
                        if v or not layer:
                            pixels[cx * 8 + x, cy * 8 + y] = _rgb(cgram, pal * 16 + v if v else 0)
    return image


def _char_base(vram, words, known):
    """BG character base: the 8 KiB step at which the most used slots hold one of our CHR."""
    slots = {w & 0x3FF for w in words}
    best = max(range(0, 0x10000, 0x2000),
               key=lambda base: sum(bytes(vram[base + n * 32:base + n * 32 + 32]) in known for n in slots))
    return best


def walk_layers(wram):
    width, height = wram[0xBF], wram[0xC0]
    return [wram[0xC000 + i * 8 + 1] & 0x0F for i in range(width * height)]


def with_floor_doors(image, source, prepared):
    """Offline render with FC doors and gates replaced by their floor, as the ROM record has them."""
    image = image.convert("RGB")
    for y in range(source.h):
        for x in range(source.w):
            if block_prop(source, source.cell(x, y) & 31) in OPENINGS:
                image.paste(prepared[door_floor(source, x, y)][0].convert("RGB"), (x * 16, y * 16))
    return image


def check_map(name, wram, vram, cgram, expected, source, known):
    """Compare everything except the cells DQ5 objects draw over; objects are checked by their
    kind byte at cell +7 of the top-left cell."""
    got = redraw(wram, vram, cgram, known)
    if got.size != expected.size:
        return {"size": [got.size, expected.size], "pixel_differences": None}
    width = source.w * 2
    covered = set()
    placed = []
    for x, y, kind, _ in objects(source):
        w, h = OBJECT_SIZE[kind]
        covered |= {(x + dx, y + dy) for dx in range(w) for dy in range(h)}
        placed.append(wram[0xC000 + (y * width + x) * 8 + 7] == kind)
    a, b = got.tobytes(), expected.convert("RGB").tobytes()
    differences = 0
    for i in range(0, len(a), 3):
        px = i // 3
        if (px % got.width // 8, px // got.width // 8) in covered:
            continue
        differences += a[i:i + 3] != b[i:i + 3]
    layers = walk_layers(wram)
    width = source.w * 2
    exits = sum(wram[0xC000 + i * 8 + at] in EXIT_MARKS for i in range(len(layers)) for at in (4, 7))
    wrong = 0
    for i, value in enumerate(layers):
        x, y = i % width, i // width
        prop = block_prop(source, source.cell(x // 2, y // 2) & 31)
        blocked = prop & 0x80 and prop not in OPENINGS | COUNTER_PROPS
        # A counter is a floor cell that +1 bit7 blocks.
        counter = bool(wram[0xC000 + i * 8 + 1] & 0x80) if prop in COUNTER_PROPS else None
        if value != (WALL if blocked else FLOOR) or counter is False:
            wrong += 1
    return {"pixels": len(a) // 3, "object_cells_skipped": len(covered), "pixel_differences": differences,
            "objects_drawn": f"{sum(placed)}/{len(placed)}", "cells": len(layers), "exit_cells": exits,
            "walk_layer_mismatches": wrong}, got


def _static_cells(wram, width, height):
    """Cell buffer without +0 bit0-2, which mark where people stand at the moment."""
    cells = bytearray(wram[0xC000:0xC000 + width * height * 8])
    for o in range(0, len(cells), 8):
        cells[o] &= 0xF8
    return bytes(cells)


def water_cycle(wram_vram, water_ids, frames):
    """Which water frame each dump holds in the four water CHR slots (None if no frame matches)."""
    seen = []
    for wram, vram in wram_vram:
        tiles = []
        for chr_id in water_ids:
            slot = (wram[0x6000 + chr_id * 2] | wram[0x6001 + chr_id * 2] << 8) & 0x3FF
            at = (0x2000 + slot * 16) * 2
            tiles.append(bytes(vram[at:at + 32]))
        data = b"".join(tiles)
        seen.append(next((i for i in range(len(frames) // 128) if frames[i * 128:i * 128 + 128] == data), None))
    return seen


def _arrival(source):
    """A walkable FC cell (and its right neighbour) closest to the centre, in DQ5 cells."""
    best = None
    for y in range(source.h):
        for x in range(source.w - 1):
            if any(block_prop(source, source.cell(x + d, y) & 31) & 0x80 for d in (0, 1)):
                continue
            score = abs(x - source.w // 2) + abs(y - source.h // 2)
            if best is None or score < best[0]:
                best = (score, x * 2, y * 2)
    return best[1], best[2]


def _control_cell(dq5, target=CONTROL):
    rom = dq5map.Rom(dq5)
    dec = dq5map.Decoder(rom, 0xBE)
    width, height, buf, _ = dec.decode(dq5map.map_pointer(rom, *target))
    for y in range(height // 3, height - 1):
        for x in range(width // 3, width - 2):
            if all(buf[((y + dy) * width + x + dx) * 8 + 1] & 1 for dx in (0, 1, 2) for dy in (0, 1)):
                return x, y
    raise RuntimeError("no walkable control cell")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rom", required=True, type=Path, help="DQ5 ROM built with dq4-environment.dq5patch.json")
    ap.add_argument("--orig", default="rom/dq5.sfc", type=Path)
    ap.add_argument("--dq4", default="rom/dq4.nes", type=Path)
    ap.add_argument("--state", default="work/state/ship.mss", type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    mesence = os.environ["MESENCE"]
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} is not empty")
    prg = ines.prg(args.dq4.read_bytes())
    assets = create_assets()

    def expected(name, frame):
        """Offline render with the water frame the game was showing."""
        shown = dict(assets, **{WATER_FRAMES[0]: assets[WATER_FRAMES[frame]]})
        image = render_maps(args.dq4, shown, [name])[name][0]
        return with_floor_doors(image, sources[name], prepared[name])

    sources, prepared = {}, {}
    for _, _, name, source, _, tiles, _ in prepare_maps(prg, assets, MAPS):
        sources[name], prepared[name] = source, tiles
    chr_data, _, block_words, _, built, _ = build_graphics(prg, assets)
    known = set(chr_data)
    water_ids = block_words[next(w for w in (water_block(*b) for b in built.values()) if w is not None)]
    frames = water_frames(assets, chr_data, water_ids)
    results = {"maps": {}}
    states = {}
    for name, (group, number) in MAPS.items():
        x, y = _arrival(sources[name])
        to = f"{group:02X}/{number:02X},{x},{y}"
        states[name], moved = warp(mesence, args.rom.resolve(), args.state.resolve(), to, out / name, name, True)
        # TEST 는 처음과 끝 칸만 견주므로 네 방향을 오가다 제자리로 돌아오면 moved=no 다. 직각 두 방향씩 다시 누르면 상쇄되지 않는다.
        for n, test in enumerate(("left:40,up:40", "right:40,down:40")):
            if not moved:
                _, moved = warp(mesence, args.rom.resolve(), args.state.resolve(), to, out / name / f"test{n}", name,
                                True, TEST=test)
        wram, vram, cgram = dump(mesence, args.rom.resolve(), states[name], out / name / "dump")
        later = [dump(mesence, args.rom.resolve(), states[name], out / name / f"dump{n}", 10 + n * WATER_PERIOD)
                 for n in (1, 2)]
        has_water = water_block(*built[name]) is not None
        cycle = water_cycle([(wram, vram)] + [(w, v) for w, v, _ in later], water_ids, frames) if has_water else [0]
        result, image = check_map(name, wram, vram, cgram, expected(name, cycle[0] or 0), sources[name], known)
        image.save(out / name / "redraw.png")
        result["water_frames"] = cycle
        result["water_slots"] = not has_water or all(
            (wram[0x6000 + i * 2] | wram[0x6001 + i * 2] << 8) & 0x3FF == WATER_SLOT + k for k, i in enumerate(water_ids))
        # BG1 is filled with CHR slot 0 (VRAM word 2000); it must stay blank or it covers the map.
        result["blank_tile_kept"] = all(bytes(v[BLANK_TILE:BLANK_TILE + 32]) == bytes(32)
                                        for v in [vram] + [v for _, v, _ in later])
        # The routine counts its own calls, not frames: where the game runs slower (36/01 with 21 people
        # calls it every other frame) a frame may stay for a dump, but it never skips or goes back.
        result["water_cycles"] = not has_water or None not in cycle and all(
            (b - a) % 3 in (0, 1) for a, b in zip(cycle, cycle[1:])) and cycle[0] != cycle[-1]
        source = sources[name]
        result["exit_cells_expected"] = sum(block_prop(source, source.cell(cx, cy) & 31) in STAIRS
                                            for cy in range(source.h) for cx in range(source.w)) if name in GROUPS else 0
        results["maps"][name] = {"target": f"{group:02X}/{number:02X}", "arrival": [x, y], "moved": moved, **result}
    cx, cy = _control_cell(args.orig.read_bytes())
    to = f"{CONTROL[0]:02X}/{CONTROL[1]:02X},{cx},{cy}"
    first = next(iter(MAPS))
    base, _ = warp(mesence, args.orig.resolve(), args.state.resolve(), to, out / "control-orig", "control")
    after, _ = warp(mesence, args.rom.resolve(), states[first], to, out / "control-after", "control")
    w0, _, _ = dump(mesence, args.orig.resolve(), base, out / "control-orig" / "dump")
    w1, _, _ = dump(mesence, args.rom.resolve(), after, out / "control-after" / "dump")
    width, height = w0[0xBF], w0[0xC0]
    results["control"] = {
        "map": to, "left_from": first,
        "cell_buffer_equal": _static_cells(w0, width, height) == _static_cells(w1, width, height),
        "block_table_equal": w0[0xB000:0xC000] == w1[0xB000:0xC000],
        "chr_bank_equal": w0[0x1823:0x1827] == w1[0x1823:0x1827],
    }
    for group, number in UNTOUCHED:
        name = f"orig-{group:02X}{number:02X}"
        fx, fy = _control_cell(args.orig.read_bytes(), (group, number))
        to = f"{group:02X}/{number:02X},{fx},{fy}"
        dumps = []
        for label, rom in (("orig", args.orig), ("rom", args.rom)):
            saved, _ = warp(mesence, rom.resolve(), args.state.resolve(), to, out / f"{name}-{label}", name)
            dumps.append(dump(mesence, rom.resolve(), saved, out / f"{name}-{label}" / "dump")[0])
        width, height = dumps[0][0xBF], dumps[0][0xC0]
        results["control"][f"{name}_cell_buffer_equal"] = (
            _static_cells(dumps[0], width, height) == _static_cells(dumps[1], width, height))
    # Open state: object flags 7E:21C2- are cleared on a group change, so visit another map of the
    # Burland group, set every flag there, come back and walk up through the gate. Past the gate the
    # castle door's area move takes the party to 02/01.
    group = MAPS["burland"][0]
    gx, gy, _, _ = next(o for o in objects(sources["burland"]) if o[2] == GATE_KIND)
    hx, hy = _arrival(sources["02-01"])
    side, _ = warp(mesence, args.rom.resolve(), states["burland"], f"{group:02X}/01,{hx},{hy + 1}",
                   out / "open-hop", "hop", ANYWHERE=1)
    back, _ = warp(mesence, args.rom.resolve(), side, f"{group:02X}/00,{gx},{gy + 9}", out / "open-gate", "gate",
                   True, ANYWHERE=1, SET="21C2=FF", TEST="up:150", MAXF=1700)
    log = (out / "open-gate" / "warp.txt").read_text()
    end = log.split("test cell ")[-1].split(" ->")[1].split()[1]
    reached = int(end.split(",")[1])
    inside = f"end map {group:02X}/01" in log
    results["gate_open"] = {"flags": "7E:21C2=FF", "start": [gx, gy + 9], "reached_row": reached,
                            "entered_castle": inside, "passed_gate_row": inside or reached <= gy + 3}

    ok = results["gate_open"]["passed_gate_row"] and all(m.get("pixel_differences") == 0 and m.get("walk_layer_mismatches") == 0 and m["moved"]
             and m["objects_drawn"].split("/")[0] == m["objects_drawn"].split("/")[1]
             and m["water_cycles"] and m["blank_tile_kept"] and m["water_slots"]
             and m["exit_cells"] == m["exit_cells_expected"]
             for m in results["maps"].values()) and all(
        v for k, v in results["control"].items() if k.endswith("_equal"))
    results["status"] = "passed" if ok else "failed"
    (out / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps(results, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
