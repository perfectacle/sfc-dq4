"""FC's step chance in the ported dungeons.

DQ5 judges a fight on every 8-pixel cell with a chance that grows with the cells since the last fight (23:E7C2,
dq4fieldencounter.dq5_chance); FC judges one on every 16-pixel block with base x the step factor (2, 4, 8 on the
first three steps after a fight or a map entry, then 16) x 0F >> 8 (18:$9CCC, $9F9B), and on a step whose cell
region ($7140 bit7-5, the room a block belongs to) differs from the step before with 55 out of 256 ($9FA0). The hook
takes 23:E8B7, where 23:E7C2 holds its chance in $00/$01 and the zone's record index (zone x 16) in X:

  in a zone of the FC dungeons, only every second cell walked is an FC step (two 8-pixel cells make a block, and a
  hero stepping to and fro across a block edge walks no farther than FC's one step); the other cells have chance
  0. On a step the count goes up (at most 4) and the chance is the zone's for that count, or REGION_CHANCE when
  the region of the hero's FC block (7E:3020 AND FE, 7E:3080 - 1 AND FE, as dq4wellswitch) differs from the last
  step's. A drop of $1A9A (the cells since the last fight, which a fight and a map entry reset) or another map
  starts over on an odd cell: count 0, this block's region. Other zones go on as before.

The region of a block comes from its FC map (dq4map, the top 3 bits of the map byte), kept per map as runs of
(length, region) in row order; a map of one region is left out, and its blocks have none (never a change).
"""

import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
FC_TOOLS = TOOLS.parents[2] / "fc" / "dq4" / "tools"
for path in (TOOLS, FC_TOOLS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dq4environmentrom import _Asm  # noqa: E402

SITE, ORIG = 0x23E8B7, bytes((0xA5, 0x01, 0xD0, 0x0B))   # LDA $01 / BNE $E8C6, M 8-bit, X 16-bit, DB 23
ON, CERTAIN = 0x23E8BB, 0x23E8C6
ZONE_RECORD = 0x16          # 23:E862: X = zone x 16
REGION_CHANCE = 0x55        # 18:$9FA0
FC_TERRAIN = 0x0F           # 18:$9F9B: every dungeon tile
STEPS = 4
HERO_X, HERO_Y = 0x7E3020, 0x7E3080
# 7E:1A86-1A97 is read by nothing from power-on through the ship, the field and fights (dq4soundpatch KEEP_SONG);
# the sound patch holds 1A94-1A97.
RAM = {"group": 0x7E1A86, "map": 0x7E1A87, "cells": 0x7E1A88, "count": 0x7E1A89, "x": 0x7E1A8A, "y": 0x7E1A8B,
       "region": 0x7E1A8C, "zone": 0x7E1A8D, "bx": 0x7E1A8E, "index": 0x7E1A8F, "odd": 0x7E1A91}
CELLS = 0x7E1A9A


def chances(prg, base):
    """FC's chance on steps 1..STEPS after a fight in a dungeon zone of base rate `base`."""
    import dq4encounter
    factor = [dq4encounter.rd(prg, dq4encounter.AFTER_BATTLE + n) for n in range(3)] + [0x10]
    return [base * f * FC_TERRAIN >> 8 for f in factor]


def zone_rows(prg, dq5_zones):
    """[(DQ5 zone, [chance per step])] for {FC zone: DQ5 zone}."""
    import dq4encounter
    return [(area, chances(prg, dq4encounter.zone(prg, fc)["rate"])) for fc, area in sorted(dq5_zones.items())]


def region_runs(prg, fc_group, k):
    """(FC map width, [(length, region)]) of an FC map's block regions in row order, or None for one region."""
    import dq4map
    _, w, _, cells = dq4map.load(prg, fc_group, k)
    regions = [v >> 5 for v in cells]
    if len(set(regions)) == 1:
        return None
    runs = []
    for r in regions:
        if runs and runs[-1][1] == r and runs[-1][0] < 0xFF:
            runs[-1][0] += 1
        else:
            runs.append([1, r])
    return w, [tuple(run) for run in runs]


def map_rows(prg, place, fc_maps):
    """[(DQ5 group, DQ5 map, FC width, runs)] of the FC maps `fc_maps` with more than one region."""
    out = []
    for fc_group, k in sorted(fc_maps):
        got = region_runs(prg, fc_group, k)
        if got:
            out.append((*place[fc_group, k], *got))
    return out


def code(at, zones, maps):
    # The tables come first, so that a check can patch the chances at fixed offsets (chance_offsets).
    asm = _Asm(at)
    ram = {k: v.to_bytes(3, "little") for k, v in RAM.items()}

    def lda(name):
        return (0xAF, *ram[name])

    def sta(name):
        return (0x8F, *ram[name])

    def cmp(name):
        return (0xCF, *ram[name])

    asm.label("region_chance").b(REGION_CHANCE)
    asm.label("zones")
    for area, steps in zones:
        asm.b(*(area * ZONE_RECORD).to_bytes(2, "little"), *steps)
    asm.b(0xFF, 0xFF)
    asm.label("maps")
    for group, number, width, _ in maps:
        asm.b(group, number, width).word(None, f"runs{group:02X}{number:02X}")
    asm.b(0xFF)
    for group, number, _, runs in maps:
        asm.label(f"runs{group:02X}{number:02X}")
        for length, region in runs:
            asm.b(length, region)
        asm.b(0x00)

    # Entered by JML from SITE: M 8-bit, X 16-bit, DB 23, X the zone record index.
    asm.label("hook").b(0x8B, 0xDA, 0xA9, at >> 16, 0x48, 0xAB, 0xC2, 0x20, 0xA0, 0x00, 0x00)
    asm.label("find").word(0xB9, "zones").b(0xC9, 0xFF, 0xFF).rel(0xF0, "plain").b(0xC3, 0x01).rel(0xF0, "found")
    asm.b(0x98, 0x18, 0x69, 2 + STEPS, 0x00, 0xA8).rel(0x80, "find")
    asm.label("plain").b(0xE2, 0x20, 0xFA, 0xAB, 0xA5, 0x01).rel(0xF0, "on")
    asm.b(0x5C, *CERTAIN.to_bytes(3, "little"))
    asm.label("on").b(0x5C, *ON.to_bytes(3, "little"))

    asm.label("found").b(0xE2, 0x20, 0x98, *sta("zone"))
    asm.b(0xA5, 0xBC, *cmp("group")).rel(0xD0, "reset").b(0xA5, 0xBD, *cmp("map")).rel(0xD0, "reset")
    asm.b(0xAF, *CELLS.to_bytes(3, "little"), *cmp("cells")).rel(0x90, "reset").b(*sta("cells")).rel(0x80, "walk")
    asm.label("reset").b(0xA5, 0xBC, *sta("group"), 0xA5, 0xBD, *sta("map"))
    asm.b(0xAF, *CELLS.to_bytes(3, "little"), *sta("cells"), 0xA9, 0x00, *sta("count"), 0x1A, *sta("odd"))
    asm.b(0x20).word(None, "block").b(*sta("x"), 0xEB, *sta("y"))
    asm.b(0x20).word(None, "region").b(*sta("region"), 0xA9, 0x00).word(0x4C, "write")
    asm.label("walk").b(*lda("odd"), 0x49, 0x01, *sta("odd")).rel(0xF0, "judge").b(0xA9, 0x00).rel(0x80, "write")
    asm.label("judge").b(0x20).word(None, "block").b(*sta("x"), 0xEB, *sta("y"))
    asm.b(*lda("count"), 0xC9, STEPS).rel(0xB0, "counted").b(0x1A, *sta("count"))
    # bx holds this block's region from here on.
    asm.label("counted").b(0x20).word(None, "region").b(*sta("bx"))
    asm.b(*lda("region"), 0xC9, 0xFF).rel(0xF0, "same").b(*lda("bx"), 0xC9, 0xFF).rel(0xF0, "same")
    asm.b(*cmp("region")).rel(0xF0, "same").b(*sta("region")).word(0xAD, "region_chance").rel(0x80, "write")
    asm.label("same").b(*lda("bx"), *sta("region"), *lda("count"), 0x18, 0x6F, *ram["zone"])
    asm.b(0xC2, 0x20, 0x29, 0xFF, 0x00, 0xA8, 0xE2, 0x20).word(0xB9, "zones", 1).rel(0x80, "write")
    asm.label("write").b(0x85, 0x00, 0x64, 0x01, 0xFA, 0xAB, 0x5C, *ON.to_bytes(3, "little"))

    # block: bx = hero X AND FE (also in A), B = hero Y - 1 AND FE.
    asm.label("block").b(0xAF, *HERO_Y.to_bytes(3, "little"), 0x3A, 0x29, 0xFE, 0xEB)
    asm.b(0xAF, *HERO_X.to_bytes(3, "little"), 0x29, 0xFE, *sta("bx"), 0x60)

    # region: A = the region of block (x, y) of this map from its runs, FF without one. Y is free.
    asm.label("region").b(0xA0, 0x00, 0x00)
    asm.label("rmap").word(0xB9, "maps").b(0xC9, 0xFF).rel(0xF0, "none").b(0xC5, 0xBC).rel(0xD0, "rnext")
    asm.word(0xB9, "maps", 1).b(0xC5, 0xBD).rel(0xF0, "rfound")
    asm.label("rnext").b(0xC8, 0xC8, 0xC8, 0xC8, 0xC8).rel(0x80, "rmap")
    asm.label("none").b(0xA9, 0xFF, 0x60)
    asm.label("rfound").b(*lda("x"), 0x4A).word(0xD9, "maps", 2).rel(0xB0, "none")
    asm.b(*sta("bx"), *lda("y"), 0x4A, 0x8F, 0x02, 0x42, 0x00).word(0xB9, "maps", 2).b(0x8F, 0x03, 0x42, 0x00)
    asm.b(0xC2, 0x20).word(0xB9, "maps", 3).b(0xA8, *lda("bx"), 0x29, 0xFF, 0x00, 0x18)
    asm.b(0x6F, 0x16, 0x42, 0x00, *sta("index"), 0xE2, 0x20)
    asm.label("run").b(0xB9, 0x00, 0x00).rel(0xF0, "none").b(0xC2, 0x20, 0x29, 0xFF, 0x00, 0x85, 0x02)
    asm.b(*lda("index"), 0xC5, 0x02).rel(0x90, "hit").b(0x38, 0xE5, 0x02, *sta("index"), 0xE2, 0x20, 0xC8, 0xC8)
    asm.rel(0x80, "run")
    asm.label("hit").b(0xE2, 0x20, 0xB9, 0x01, 0x00, 0x60)
    return asm.assemble()


def rows(prg, place, dq5_zones, fc_maps):
    return zone_rows(prg, dq5_zones), map_rows(prg, place, fc_maps)


def writes(at, prg, place, dq5_zones, fc_maps):
    """dq5patch/1 writes: the tables with the hook in bank `at`, and the JML at SITE."""
    data, labels = code(at, *rows(prg, place, dq5_zones, fc_maps))
    if at >> 16 != (at + len(data) - 1) >> 16:
        raise ValueError("dungeon step chance crosses a bank")
    return [
        {"at": _cpu(at), "hex": data.hex(" ").upper(),
         "note": "던전 조우를 FC 처럼 블록 걸음마다, 구역이 바뀐 걸음은 55"},
        {"at": _cpu(SITE), "hex": bytes((0x5C, *labels["hook"].to_bytes(3, "little"))).hex(" ").upper(),
         "orig": ORIG.hex(" ").upper(), "note": "조우 확률 비교 앞을 FC 던전 걸음 훅으로"},
    ]


def chance_offsets(at, zones):
    """File offsets (LoROM) of REGION_CHANCE and of each zone row's chances, for a check's ROMPATCH."""
    base = (at >> 16 & 0x7F) * 0x8000 + (at & 0x7FFF)
    return base, [base + 1 + i * (2 + STEPS) + 2 for i in range(len(zones))]


def rom_patch(rom, at, steps, region=None):
    """A check's ROMPATCH items (file offset=bytes) that set every zone row of the tables at `at` in the ROM bytes
    `rom` to the chances `steps`, and the region chance to `region` unless None."""
    base, _ = chance_offsets(at, [])
    items = [] if region is None else [f"{base:X}={region:02X}"]
    row = base + 1
    while rom[row:row + 2] != b"\xFF\xFF":
        items.append(f"{row + 2:X}=" + bytes(steps).hex().upper())
        row += 2 + STEPS
    return ";".join(items)


def _cpu(addr):
    return f"{addr >> 16:02X}:{addr & 0xFFFF:04X}"


class Walk:
    """The hook's state machine in Python, for a check: step() is the chance the hook leaves in $00 at 23:E8BB."""

    def __init__(self, zones, maps, region_chance=REGION_CHANCE):
        self.zones = {area * ZONE_RECORD: steps for area, steps in zones}
        self.maps = {(group, number): (width, runs) for group, number, width, runs in maps}
        self.region_chance, self.state = region_chance, None

    def region(self, group, number, x, y):
        width, runs = self.maps.get((group, number), (0, []))
        if x >> 1 >= width:
            return 0xFF
        index = (y >> 1) * width + (x >> 1)
        for length, region in runs:
            if index < length:
                return region
            index -= length
        return 0xFF

    def step(self, group, number, cells, hero_x, hero_y, zone_index):
        """None for a zone the hook leaves alone."""
        steps = self.zones.get(zone_index)
        if steps is None:
            return None
        x, y = hero_x & 0xFE, (hero_y - 1) & 0xFE
        s = self.state
        if s is None or (s["group"], s["map"]) != (group, number) or cells < s["cells"]:
            self.state = {"group": group, "map": number, "cells": cells, "count": 0, "odd": True,
                          "region": self.region(group, number, x, y)}
            return 0
        s["cells"], s["odd"] = cells, not s["odd"]
        if s["odd"]:
            return 0
        s["count"] = min(s["count"] + 1, STEPS)
        new, old = self.region(group, number, x, y), s["region"]
        s["region"] = new
        if 0xFF not in (old, new) and new != old:
            return self.region_chance
        return steps[s["count"] - 1]
