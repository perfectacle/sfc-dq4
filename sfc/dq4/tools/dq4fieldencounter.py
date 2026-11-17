"""FC field encounter zones on DQ5 worlds 0-2: the DQ5 zone grids (dq5encounterwrite.py) and zone records
(dq5progresswrite.py) for the FC zones of fields 0, 1 and 3.

An FC zone map cell is 16x16 FC blocks ((Y >> 4) * 16 + (X >> 4), fc/dq4/docs/dq4-encounter-format.md) and a DQ5
grid cell is 32x32 field cells, also 16x16 blocks ((Y >> 5) * 17 + (X >> 5), 01:854F), so FC zone cell (c, r) is
DQ5 grid cell (c, r). Each FC zone takes one DQ5 zone that only the field grids use (zones), whose record is
rewritten in place with the FC zone's monsters through MONSTERS (record), and the four sea zones of 01:85D8 take
FC zone 00, the zone FC uses on the ship. The DQ5 terrain rates become FC's terrain factors (terrain_rates), and
each zone's coefficient keeps FC's mean distance to a fight (field_rate_index).
sfc/dq4/docs/dq4-field-format.md 「조우」.

  python sfc/dq4/tools/dq4fieldencounter.py -o work/encounter
"""

import argparse
import functools
import json
import math
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
DQ5_TOOLS = TOOLS.parents[1] / "dq5" / "tools"
FC_TOOLS = TOOLS.parents[2] / "fc" / "dq4" / "tools"
for path in (TOOLS, DQ5_TOOLS, FC_TOOLS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

# FC monster -> DQ5 monster, a placeholder until the DQ4 monsters are ported: the DQ5 monster of the same name, or
# else (marked ~) the first DQ5 monster, by number, of a DQ5 zone whose level is nearest the lowest level of the
# FC zones the monster appears in (FC zones of fields 0, 1 and 3, then the dungeon zones; DQ5 zones as in the
# original ROM). The monsters only chapter 2's tower and south cave bring take the placeholder of a monster of the
# same FC zone.
MONSTERS = {
    0x00: 0x00,  # スライム
    0x01: 0x03,  # ~ キリキリバッタ -> ドラキー
    0x02: 0x03,  # ~ いたずらもぐら -> ドラキー
    0x03: 0x03,  # ~ はさみくわがた -> ドラキー
    0x04: 0x00,  # スライム
    0x05: 0x03,  # ~ スライムベス -> ドラキー
    0x06: 0x03,  # ~ ももんじゃ -> ドラキー
    0x07: 0x03,  # ~ おおみみず -> ドラキー
    0x08: 0x03,  # ~ みみとびねずみ -> ドラキー
    0x09: 0x03,  # ~ エアラット -> ドラキー
    0x0A: 0x09,  # バブルスライム
    0x0B: 0x0C,  # つちわらし
    0x0C: 0x0B,  # ~ きりかぶおばけ -> スカルサーペント
    0x0D: 0x12,  # ~ メラゴースト -> まほうつかい
    0x0E: 0x0B,  # ~ ミノーン -> スカルサーペント
    0x0F: 0x0B,  # ~ とんがりあたま -> スカルサーペント
    0x10: 0x10,  # ~ みならいあくま -> スピニー
    0x11: 0x30,  # おばけキノコ
    0x13: 0x12,  # ~ キラースコップ -> まほうつかい
    0x14: 0x1E,  # ホイミスライム
    0x16: 0x1B,  # ~ いしにんぎょう -> がいこつへい
    0x17: 0x12,  # ~ エレフローパー -> まほうつかい
    0x18: 0x0B,  # ~ あばれこまいぬ -> スカルサーペント
    0x19: 0x12,  # ~ ダックスビル -> まほうつかい
    0x1A: 0x12,  # ~ ひとくいそう -> まほうつかい
    0x1B: 0x1B,  # ~ つかいま -> がいこつへい
    0x1C: 0x12,  # ~ あばれうしどり -> まほうつかい
    0x1D: 0x12,  # ~ べビーマジシャン -> まほうつかい
    0x1E: 0x12,  # ~ リリパット -> まほうつかい
    0x1F: 0x1F,  # ~ きゅうけつこうもり -> わらいぐさ
    0x20: 0x1F,  # ~ とさかへび -> わらいぐさ
    0x21: 0x12,  # ~ おおにわとり -> まほうつかい
    0x22: 0x12,  # ~ ピクシー -> まほうつかい
    0x23: 0x1B,  # ~ ヘルビートル -> がいこつへい
    0x24: 0x1F,  # ~ テベロ -> わらいぐさ
    0x25: 0x25,  # ~ おにこぞう -> ダークアイ
    0x26: 0x1F,  # ~ ラリホービートル -> わらいぐさ
    0x27: 0x1B,  # ~ メイジももんじゃ -> がいこつへい
    0x28: 0x1F,  # ~ サンドマスター -> わらいぐさ
    0x2A: 0x3F,  # ~ ポイズンリザード -> インスペクター
    0x2C: 0x1F,  # ~ コドラ -> わらいぐさ
    0x2D: 0x1B,  # ~ ベロベロ -> がいこつへい
    0x2E: 0x3F,  # ~ スペクテット -> インスペクター
    0x2F: 0x25,  # ~ しびれだんびら -> ダークアイ
    0x31: 0x29,  # ~ ダークドリアード -> エビルアップル
    0x32: 0x25,  # ~ エビルハムスター -> ダークアイ
    0x33: 0x3F,  # ~ はえおとこ -> インスペクター
    0x34: 0x47,  # ~ くびながりゅう -> メタルライダー
    0x35: 0x47,  # ~ エビルアングラー -> メタルライダー
    0x36: 0x3F,  # ~ ひとくいサーベル -> インスペクター
    0x38: 0x3F,  # ~ かまいたち -> インスペクター
    0x39: 0xC8,  # しびれくらげ
    0x3A: 0x47,  # ~ さつじんえい -> メタルライダー
    0x3B: 0x47,  # ~ とつげきうお -> メタルライダー
    0x3D: 0x29,  # ~ ひとつめピエロ -> エビルアップル
    0x3E: 0x3F,  # ~ プテラノドン -> インスペクター
    0x3F: 0x47,  # ~ トドマン -> メタルライダー
    0x40: 0x3F,  # ~ ドラゴンバタフライ -> インスペクター
    0x45: 0x29,  # ~ とらおとこ -> エビルアップル
    0x46: 0x48,  # さまようよろい
    0x48: 0x3F,  # ~ がいこつけんし -> インスペクター
    0x4D: 0x25,  # ~ さそりアーマー -> ダークアイ
    0x5C: 0x2D,  # メタルスライム
    0x5D: 0x94,  # ~ キラーアーマー -> スライムベホマズン
    0x8A: 0x8A,  # ~ オーガー -> シャドーサタン
    0x8D: 0x8A,  # ~ ライバーン -> シャドーサタン
    0x8E: 0x8A,  # ~ ブラックマージ -> シャドーサタン
    0x90: 0x8A,  # ~ やつざきアニマル -> シャドーサタン
    0x92: 0x8A,  # ~ じごくのもんばん -> シャドーサタン
    0x95: 0x8A,  # ~ よるのていおう -> シャドーサタン
    0x98: 0x94,  # ~ トーテムキラー -> スライムベホマズン
    0xA3: 0x94,  # ~ ガーディアン -> スライムベホマズン
    0xA4: 0x94,  # ~ てっきゅうまじん -> スライムベホマズン
    0xA6: 0x94,  # ~ デビルプリンス -> スライムベホマズン
    0xA7: 0x94,  # ~ グレートライドン -> スライムベホマズン
    0xA8: 0xA2,  # メタルキング
    0xA9: 0x94,  # ~ ライバーンロード -> スライムベホマズン
}
# 2장 몬스터는 NDS 그림을 넣으려고 FC 몬스터마다 따로 DQ5 번호를 준다(dq4monport.PORT, 레코드는 PLACEHOLDERS 의 대역 것을
# 옮겨 능력치는 같음). PLACEHOLDERS 는 위 대역 표 그대로
PLACEHOLDERS = dict(MONSTERS)
import dq4monport  # noqa: E402
MONSTERS.update(dq4monport.PORT)
# FC 3장의 구역(dq4encounter.ch3_reach 로 닿는 필드 구역과 그 입구 던전의 구역). 3장에만 FC 값을 넣은 종(dq4monport.CH3)은
# 이 구역에서만 그 번호를 쓴다. 같은 종이 1장 던전·필드에도 대역으로 나오는데, 1장 롬의 전투를 바꾸지 않으려고 그쪽은 둔다
CH3_FIELD, CH3_DUNGEON = (0x14, 0x15, 0x16, 0x17), (0x48, 0x49, 0x4A, 0x4B)
CH3_ZONES = CH3_FIELD + CH3_DUNGEON
CHAPTER3_MONSTERS = {**MONSTERS, **{fc: m for fc, (m, _) in dq4monport.CH3.items()}}


def monsters_of(z):
    """FC 구역 z 의 몬스터를 옮기는 표."""
    return CHAPTER3_MONSTERS if z in CH3_ZONES else MONSTERS
# FC slots: 0-4 a group plus more groups (DQ5 slots 0-4, several species), 6-10 one group of a count code (DQ5
# slots 5-9, codes 0-7 of the same meaning but 4 and 5: FC 1-3 and 2-4, DQ5 2-3 and 3-4), 5 and 11 one monster (a
# free DQ5 slot of 5-9 with code 0), 12-13 FC formations (in a dungeon zone, slot 12 is DQ5 slot 10's fixed group,
# dungeon_fixed; on the field neither is ported).
GROUP_SLOTS, SOLO_SLOTS, ONE_SLOTS = range(0, 5), range(6, 11), (5, 11)
DQ5_SOLO = range(5, 10)
GROUP_COUNT = 1          # DQ5 several-species count code 1: one of each (code + 7 = 8)
DQ5_WEIGHT = 7
FORMATION_SLOT = 12
# DQ5 fixed groups (23:B04B, dq5encounterwrite fixed_groups): nine, three members each. Only ported zones are
# reachable, so the DQ5 groups are taken from 0.
FIXED_GROUPS, FIXED_MEMBERS = 9, 3
COUNT_BASE, COUNT_WIDTH, COUNT_CODES = 0x23EA63, 0x23EA73, 15
# FC field-0 zone maps by $615A (fc/dq4/tools/dq4encounter.zone_map): chapters 1, 2 and 4 share one, chapter 3 has
# its own of 8 rows (the dungeon list follows it).
FC_MAP, FC_MAP3 = 0, 2
CH3_ROWS = 8
# DQ5 field grids (dq5encounterwrite field_grids, 01:A6D9): index -> ($1949 world, rows, the (FC zone map, row) read
# there). World 0 picks its grid by $1948 and 01:854F does not clamp the row, so with $1948 = 0 rows 7-15 of
# grid 0 read rows 0-8 of grid 1: grid 1 holds FC rows 7-15 there and serves $1948 = 1 only from its row 9. This port
# never sets $1948 to 2, so grid 2 is chapter 3's: the grid hook (grid_hook_writes) picks it while the chapter-3 flag
# is on. Its rows past the chapter-3 map take the shared map's rows.
GRIDS = {0: (0, 7, [(FC_MAP, r) for r in range(0, 7)]),
         1: (0, 17, [(FC_MAP, r) for r in [*range(7, 16), *range(9, 16)]] + [None]),
         2: (0, 17, [(FC_MAP3 if r < CH3_ROWS else FC_MAP, r) for r in range(16)] + [None]),
         3: (1, 5, None), 4: (2, 4, None)}
CH3_GRID = 2
WORLD0_GRIDS = (0x23F1FC, 0x23F273, 0x23F394)
# 01:A6E3 (LDA $1948 / BNE) -> JSL to the hook, then BRA to 01:A711, where the grid's X (address) and A (bank) are
# taken. The hook runs with 8-bit A and 16-bit X (01:A6DA).
GRID_SITE, GRID_ORIG, GRID_BACK = 0x01A6E3, bytes((0xAD, 0x48, 0x19, 0xD0, 0x07, 0xA2)), 0x01A711
GRID_HOOK_AT = 0x57C000
# Event flags are bytes from 7E:2190 (dq4ch2slots 「flag 자리」).
FLAG_BASE = 0x7E2190


def chapter3_flag():
    """(address, bit) of the chapter-3 flag (dq4ch3event.CHAPTER3, set at the end of chapter 2)."""
    import dq4ch3event
    index, bit = dq4ch3event.CHAPTER3
    return FLAG_BASE + index, bit
GRID_WIDTH = 17
SEA_ZONE = 0x00
# 01:85D8: the ship's two rectangles take these four, the second pair only while $1948 = 2 (never in this port).
SEA_AREAS = (81, 82, 83, 84)
# The 32 DQ5 zones only the field grids use ran out with chapter 3, so later zones take these: the unused sea pair
# and 78, which only DQ5 54/52 uses (group 54 is reached by DQ5 15/0A only, and every DQ5 entrance is parked).
SPARE_AREAS = (83, 84, 78)
# FC fields 1 and 3 have no zone map (18:$9C3F): field 1 is zone 35 above Y = 0C and 34 below, field 3 zone 36.
# A DQ5 grid row is 16 blocks, so field 1's first row takes 35.
FIELD1_TOP, FIELD1, FIELD3 = 0x35, 0x34, 0x36
RATE_COEF = 0x23EA44
# FC's chance per step is base x the step factor x the terrain factor >> 8 (18:$9CCC), 0F on every dungeon tile
# (18:$9F9B); DQ5's is coefficient x Y' >> 6, Y' the rate scaled by the steps since the last fight (23:E7C2). An
# FC step is a 16-pixel block and a DQ5 step one 8-pixel cell (00:82AB runs for each, indoors and on the field),
# so a zone takes the coefficient whose mean cells to a fight are nearest twice FC's mean steps: indoors at the
# DQ5 indoor rate 7 (01:8522, dungeon_rate_index), on the field with each terrain's rate at its FC factor
# (terrain_rates, field_rate_index).
FC_DUNGEON_TERRAIN, DQ5_INDOOR_RATE = 0x0F, 7
MEAN_STEPS = 4096
# DQ5 rate per terrain nibble (01:84CF's Y), day then night, 14 each. FC fights only on tiles below 8 ($9CB5).
TERRAIN_RATES = 0x23F1E0
TERRAINS = 14
FC_TERRAINS = 8
# FC kind 0 is the sea, walked only on the ship (the sea zones); the land zones are matched on the other kinds.
SEA_KINDS, LAND_KINDS = (0,), tuple(range(1, FC_TERRAINS))


@functools.cache
def _fc(prg):
    import dq4encounter
    return dq4encounter


def _rows(prg, key):
    return _fc(prg).zone_map(prg, key)[1]


def fc_zones(prg):
    """FC zones of the zone map chapters 1, 2 and 4 use on field 0, and of fields 1 and 3."""
    return sorted({v & 0x3F for row in _rows(prg, FC_MAP) for v in row} | {FIELD1_TOP, FIELD1, FIELD3})


def chapter3_zones(prg):
    """FC zones of chapter 3's field-0 grid rows that fc_zones lacks."""
    rows = _rows(prg, FC_MAP3)[:CH3_ROWS]
    return sorted({v & 0x3F for row in rows for v in row} - set(fc_zones(prg)))


def _pool(enc):
    """DQ5 zones the FC zones take, in order: those only the field grids use (enc is the dq5encounterwrite dump of
    the original ROM), then SPARE_AREAS."""
    used = {a for m in enc["maps"] for a in m["areas"]}
    field = sorted({a for g in enc["field_grids"] for row in g["rows"] for a in row} - used - set(SEA_AREAS))
    return field + [a for a in SPARE_AREAS if a not in field]


def zones(prg, enc):
    """{FC zone: DQ5 zone}: the FC zones in order on the DQ5 zones of _pool, in order."""
    field, fc = _pool(enc), fc_zones(prg)
    if len(fc) > len(field):
        raise ValueError(f"{len(fc)} FC zones, {len(field)} DQ5 zones")
    return dict(zip(fc, field))


def dungeon_zones(prg, enc, fc):
    """{FC dungeon zone: DQ5 zone}: the FC zones `fc`, in the order they first come, on the _pool zones that zones()
    leaves, in order. The caller orders `fc` so that zones added later come last and the earlier ones keep their DQ5
    zones. The field grids written by grids() hold only field zones and the sea, so these are not read there."""
    taken = zones(prg, enc).values()
    left = [a for a in _pool(enc) if a not in taken]
    fc = list(dict.fromkeys(fc))
    if len(fc) > len(left):
        raise ValueError(f"{len(fc)} FC dungeon zones, {len(left)} DQ5 zones left")
    return dict(zip(fc, left))


def chapter3_assign(prg, enc, dungeon):
    """{FC zone: DQ5 zone} of chapter3_zones on the _pool zones left after zones() and dungeon_zones(dungeon)."""
    taken = {*zones(prg, enc).values(), *dungeon_zones(prg, enc, dungeon).values()}
    left = [a for a in _pool(enc) if a not in taken]
    fc = chapter3_zones(prg)
    if len(fc) > len(left):
        raise ValueError(f"{len(fc)} chapter-3 FC zones, {len(left)} DQ5 zones left")
    return dict(zip(fc, left))


def grids(prg, assign):
    """dq5encounter/1 field_grids: every cell of the five grids from the FC zone maps."""
    maps = {key: _rows(prg, key) for key in (FC_MAP, FC_MAP3)}
    sea = assign[SEA_ZONE]
    out = []
    for index, (world, count, source) in GRIDS.items():
        rows = []
        for r in range(count):
            if world == 1:
                row = [assign[FIELD1_TOP if r == 0 else FIELD1]] * GRID_WIDTH
            elif world == 2:
                row = [assign[FIELD3]] * GRID_WIDTH
            elif source[r] is None:
                row = [sea] * GRID_WIDTH
            else:
                key, k = source[r]
                row = [assign[v & 0x3F] for v in maps[key][k]] + [sea] * (GRID_WIDTH - 16)
            rows.append(row)
        out.append({"index": index, "rows": rows})
    return out


def grid_hook_writes(at=GRID_HOOK_AT):
    """dq5patch/1 writes: 01:A6E3 jumps to a hook that picks grid CH3_GRID while chapter3_flag() is on and else the
    grid of $1948 as the original (0, 1, or 2 and up), then goes on at GRID_BACK with X = the grid and A = its bank."""
    from dq4environmentrom import _Asm
    flag, bit = chapter3_flag()
    grid = {k: (addr >> 16, addr & 0xFFFF) for k, addr in enumerate(WORLD0_GRIDS)}
    asm = _Asm(at)
    asm.label("hook").b(0xAF, *flag.to_bytes(3, "little"), 0x29, bit).rel(0xD0, "ch3")
    asm.b(0xAF, 0x48, 0x19, 0x7E).rel(0xD0, "stage")
    asm.b(0xA2, *grid[0][1].to_bytes(2, "little"), 0xA9, grid[0][0], 0x6B)
    asm.label("stage").b(0xC9, 0x01).rel(0xD0, "ch3")
    asm.b(0xA2, *grid[1][1].to_bytes(2, "little"), 0xA9, grid[1][0], 0x6B)
    asm.label("ch3").b(0xA2, *grid[CH3_GRID][1].to_bytes(2, "little"), 0xA9, grid[CH3_GRID][0], 0x6B)
    code, _ = asm.assemble()
    site = bytes((0x22, *at.to_bytes(3, "little"), 0x80, GRID_BACK - (GRID_SITE + 6)))
    return [{"at": f"{at >> 16:02X}:{at & 0xFFFF:04X}", "hex": code.hex(" ").upper(),
             "note": "3장 flag 면 필드 조우 격자 2(3장 지도)를 고름"},
            {"at": f"{GRID_SITE >> 16:02X}:{GRID_SITE & 0xFFFF:04X}", "hex": site.hex(" ").upper(),
             "orig": GRID_ORIG.hex(" ").upper(), "note": "필드 조우 격자 고르기를 훅으로"}]


def _coefs(dq5):
    return dq5[_lorom(RATE_COEF):_lorom(RATE_COEF) + 8]


def _mean(chances):
    """Mean steps to a fight for the chances (out of 256) of steps 1, 2, ...."""
    mean, left = 0.0, 1.0
    for k, p in enumerate(chances, 1):
        mean += k * left * min(p, 256) / 256
        left *= 1 - min(p, 256) / 256
    return mean


@functools.cache
def fc_steps(prg, base, terrain=FC_DUNGEON_TERRAIN):
    """FC's mean steps to a fight in a zone of base rate `base` on tiles of terrain factor `terrain` (0F in a
    dungeon): base x the step factor (18:$A33D[$6E42], the first three steps after a fight) x terrain >> 8
    (18:$9CCC)."""
    enc = _fc(prg)
    after = [enc.rd(prg, enc.AFTER_BATTLE + n) for n in range(3)]
    return _mean(base * (after[k] if k < 3 else 0x10) * terrain >> 8 for k in range(MEAN_STEPS))


def dq5_chance(coef, rate, steps):
    """DQ5's chance (out of 256) of a fight on a step for coefficient `coef` and rate Y (23:E7C2): with s = $1A9A,
    the steps since the last fight counting this one (at most FF), and n = 256 / Y, Y is 0 below 3 and >> 6, >> 4,
    >> 2, >> 1 below 5, 7, 9, 11, then (Y >> 1) + (Y >> 2) below n, Y + (Y >> 1) below 2n and 4Y after, at most
    FF; the chance is coef x Y >> 6 (23:E898)."""
    n, s = 0x100 // rate, min(steps, 0xFF)
    if s < n:
        y = (rate >> 1) + (rate >> 2)
        for top, shift in ((3, 8), (5, 6), (7, 4), (9, 2), (11, 1)):
            if s < top:
                y = rate >> shift
                break
    else:
        y = min(0xFF, rate + (rate >> 1) if s < 2 * n else 4 * rate)
    return coef * y >> 6


@functools.cache
def dq5_steps(coef, rate):
    """DQ5's mean steps to a fight for coefficient `coef` and rate Y (dq5_chance)."""
    return _mean(dq5_chance(coef, rate, s) for s in range(1, MEAN_STEPS + 1))


def dungeon_rate_index(prg, dq5, base):
    """Index of the DQ5 rate coefficient whose mean cells to a fight at the indoor rate is nearest two cells per FC
    step of fc_steps."""
    coefs = _coefs(dq5)
    want = 2 * fc_steps(prg, base)
    return min(range(8), key=lambda i: (abs(dq5_steps(coefs[i], DQ5_INDOOR_RATE) - want), i))


def field_rate_index(prg, dq5, base, kinds=LAND_KINDS):
    """Index of the DQ5 rate coefficient whose mean cells to a fight, the terrain rate being the FC factor
    (terrain_rates), are nearest two cells per FC step of fc_steps on the FC kinds `kinds` by day and by night:
    the least sum of the ratios' absolute logarithms. A factor of 0 fights in neither engine."""
    enc = _fc(prg)
    coefs = _coefs(dq5)
    factors = [f for t in (enc.TERRAIN_DAY, enc.TERRAIN_NIGHT) for k in kinds if (f := enc.rd(prg, t + k))]

    def error(coef):
        return sum(abs(math.log(dq5_steps(coef, f) / (2 * fc_steps(prg, base, f)))) for f in factors)
    return min(range(8), key=lambda i: (error(coefs[i]), i))


def terrain_rates(prg, dq5):
    """dq5patch/1 write of the DQ5 day and night terrain rates: each terrain nibble of the DQ5 blocks the FC kinds
    0-7 borrow (dq4fieldport.BLOCKS) takes the FC day and night factor of that kind times dq4balance.ENCOUNTER
    (field_rate_index still matches FC's own factor, so the port fights less than FC); the nibbles only other kinds
    borrow are 0. A nibble shared by kinds below and above 8 keeps the factor of the kind below 8."""
    import dq4balance
    import dq4fieldport
    from dq5field import terrain
    from dq5map import Rom
    enc = _fc(prg)
    rom = Rom(dq5)
    o = _lorom(TERRAIN_RATES)
    old = dq5[o:o + 2 * TERRAINS]
    new = bytearray(old)
    kinds = {}
    for kind, block in dq4fieldport.BLOCKS.items():
        kinds.setdefault(terrain(rom, block), []).append(kind)
    for t, found in kinds.items():
        fc = [k for k in found if k < FC_TERRAINS]
        if len(fc) > 1:
            raise ValueError(f"terrain {t:X}: FC kinds {fc} share it")
        for half, table in enumerate((enc.TERRAIN_DAY, enc.TERRAIN_NIGHT)):
            new[half * TERRAINS + t] = dq4balance.chance(enc.rd(prg, table + fc[0])) if fc else 0
    return {"at": f"{TERRAIN_RATES >> 16:02X}:{TERRAIN_RATES & 0xFFFF:04X}", "hex": new.hex(" ").upper(),
            "orig": old.hex(" ").upper(), "note": "지형별 조우율(낮·밤)을 FC 지형 배수의 3/4 로"}


def _lorom(addr):
    return (addr >> 16 & 0x7F) * 0x8000 + (addr & 0x7FFF)


def _formations(prg, zones):
    enc = _fc(prg)
    return {enc.zone(prg, z)["slots"][FORMATION_SLOT] for z in set(zones)} - {0xFF}


def dungeon_fixed(prg, fc, field=()):
    """{FC formation: DQ5 fixed group} of the slot-12 formations of the FC dungeon zones `fc`, in formation order,
    then those only the FC field zones `field` have (field_formations), in formation order: a field formation added
    later leaves the dungeon groups' numbers as they were."""
    found = sorted(_formations(prg, fc))
    found += sorted(_formations(prg, field) - set(found))
    if len(found) > FIXED_GROUPS:
        raise ValueError(f"{len(found)} FC formations, {FIXED_GROUPS} DQ5 fixed groups")
    return {f: k for k, f in enumerate(found)}


def field_formations(prg):
    """The FC field zones whose slot-12 formation becomes DQ5 slot 10 on the field: chapter 3's (CH3_FIELD), so
    the zones chapters 1 and 2 walk keep their records."""
    enc = _fc(prg)
    return [z for z in CH3_FIELD if enc.zone(prg, z)["slots"][FORMATION_SLOT] != 0xFF
            and enc.weights(prg, enc.zone(prg, z)["row"])[FORMATION_SLOT]]


def fixed_groups(prg, dq5, fixed, chapter3=()):
    """dq5encounter/1 fixed_groups of the FC formations `fixed` (dungeon_fixed): each member's monster through
    MONSTERS (CHAPTER3_MONSTERS for the formations in `chapter3`) and the DQ5 count code of the same range."""
    enc = _fc(prg)
    base, width = (dq5[_lorom(t):_lorom(t) + COUNT_CODES] for t in (COUNT_BASE, COUNT_WIDTH))
    codes = {(base[c], base[c] + max(width[c], 1) - 1): c for c in reversed(range(COUNT_CODES))}
    out = []
    for f, k in sorted(fixed.items(), key=lambda kv: kv[1]):
        members = [(m, lo, hi) for m, lo, hi in enc.formation(prg, f) if m != 0xFF]
        if len(members) > FIXED_MEMBERS:
            raise ValueError(f"FC formation {f:02X}: {len(members)} groups, a DQ5 fixed group holds {FIXED_MEMBERS}")
        if any((lo, hi) not in codes for _, lo, hi in members):
            raise ValueError(f"FC formation {f:02X}: a count range no DQ5 count code has")
        table = CHAPTER3_MONSTERS if f in chapter3 else MONSTERS
        out.append({"index": k, "members": [{"monster": table[m], "count_code": codes[lo, hi]}
                                            for m, lo, hi in members]})
    return out


def placed(prg, z, dungeon=None, field_fixed=None, monsters=None):
    """(DQ5 slots 0-9, fixed slot, {DQ5 slot 0-10: FC slot}, FC slots left out) of FC zone z, as record() lays them.
    The fixed slot (DQ5 10) takes slot 12's formation through `dungeon` (dungeon_fixed) in a dungeon zone, or through
    `field_fixed` on the field; else it is empty."""
    enc = _fc(prg)
    monsters = monsters_of(z) if monsters is None else monsters
    rec = enc.zone(prg, z)
    s, w = rec["slots"], enc.weights(prg, rec["row"])
    code16 = w[16] | w[17] << 8
    used = [i for i in (*GROUP_SLOTS, *SOLO_SLOTS, *ONE_SLOTS) if s[i] != 0xFF]
    top = max(w[i] for i in used)

    def weight(i):
        return max(1, round(DQ5_WEIGHT * w[i] / top)) if w[i] else 0

    slots = {k: {"index": k, "weight": 0, "count_code": 0, "monster": 0} for k in range(10)}
    origin = {}
    for i in GROUP_SLOTS:
        if s[i] != 0xFF:
            slots[i].update(weight=weight(i), count_code=GROUP_COUNT, monster=monsters[s[i]])
            origin[i] = i
    for i in SOLO_SLOTS:
        if s[i] != 0xFF:
            slots[i - 1].update(weight=weight(i), count_code=code16 >> 3 * (i - 6) & 7, monster=monsters[s[i]])
            origin[i - 1] = i
    dropped = [i for i in (12, 13) if s[i] != 0xFF]
    fixed_slot = {"weight": 0, "group": 0}
    groups = dungeon if dungeon is not None else field_fixed
    if groups is not None and s[FORMATION_SLOT] in groups and w[FORMATION_SLOT]:
        fixed_slot = {"weight": weight(FORMATION_SLOT), "group": groups[s[FORMATION_SLOT]]}
        dropped.remove(FORMATION_SLOT)
        origin[10] = FORMATION_SLOT
    for i in ONE_SLOTS:
        if s[i] == 0xFF:
            continue
        free = [k for k in DQ5_SOLO if not slots[k]["weight"]]
        if not free or not w[i]:
            dropped.append(i)
            continue
        slots[free[0]].update(weight=weight(i), count_code=0, monster=monsters[s[i]])
        origin[free[0]] = i
    return list(slots.values()), fixed_slot, origin, dropped


def record(prg, dq5, z, dungeon=None, kinds=LAND_KINDS, field_fixed=None):
    """dq5progress/1 encounter fields of FC zone z (without its index) and the FC slots left out. `dungeon` is
    dungeon_fixed for a dungeon zone (None on the field): the rate is dungeon_rate_index, and slot 12 becomes DQ5
    slot 10. On the field the rate is field_rate_index on the FC kinds `kinds`, and slot 12 becomes slot 10 only
    through `field_fixed` (the formations of field_formations). Monsters go through monsters_of(z)."""
    enc = _fc(prg)
    rec = enc.zone(prg, z)
    w = enc.weights(prg, rec["row"])
    slots, fixed_slot, _, dropped = placed(prg, z, dungeon, field_fixed)
    rate = field_rate_index(prg, dq5, rec["rate"], kinds) if dungeon is None else dungeon_rate_index(prg, dq5, rec["rate"])
    return {"level": rec["b1"], "slots": slots, "fixed": fixed_slot,
            "species_weights": [3, 1 if w[14] else 0, 1 if w[15] else 0], "rate_index": rate,
            "flag_1000": 0, "flag_1010": False, "fixed_night_only": False}, dropped


def docs(prg, dq5, enc, dungeon=()):
    """(dq5progress/1, dq5encounter/1, report) for the FC field zones (with chapter 3's, chapter3_assign) and the FC
    dungeon zones `dungeon` (dungeon_zones). The terrain rates are terrain_rates; the grid hook is grid_hook_writes."""
    assign = zones(prg, enc)
    late = chapter3_assign(prg, enc, dungeon)
    field = field_formations(prg)
    fixed = dungeon_fixed(prg, dungeon, field)
    # 3장 구역만 쓰는 편성이어야 3장 번호로 옮긴다(1·2장 구역과 함께 쓰는 고정 무리는 그 장 롬의 전투가 바뀌므로 대역 그대로)
    chapter3 = _formations(prg, [z for z in [*dungeon, *field] if z in CH3_ZONES]) - \
        _formations(prg, [z for z in dungeon if z not in CH3_ZONES])
    groups = fixed_groups(prg, dq5, fixed, chapter3)
    records, report = [], {}
    found_dungeon = dungeon_zones(prg, enc, dungeon)
    for kind, found in (("field", {**assign, **late}), ("dungeon", found_dungeon)):
        for fc, area in found.items():
            fields, dropped = record(prg, dq5, fc, fixed if kind == "dungeon" else None,
                                     field_fixed=fixed if fc in field else None)
            records.append({"index": area, **fields})
            monsters = {sl["monster"] for sl in fields["slots"] if sl["weight"]}
            if fields["fixed"]["weight"]:
                monsters |= {m["monster"] for m in groups[fields["fixed"]["group"]]["members"]}
            report[f"{fc:02X}"] = {"zone": area, "kind": kind, "level": fields["level"], "dropped_slots": dropped,
                                   "rate_index": fields["rate_index"], "fixed": fields["fixed"],
                                   "monsters": sorted(monsters)}
    sea, _ = record(prg, dq5, SEA_ZONE, kinds=SEA_KINDS)
    taken = {*assign.values(), *late.values(), *found_dungeon.values()}
    records += [{"index": area, **sea} for area in SEA_AREAS if area not in taken]
    return ({"format": "dq5progress/1", "encounters": records},
            {"format": "dq5encounter/1", "field_grids": grids(prg, {**assign, **late}), "fixed_groups": groups}, report)


# DQ5 몬스터 표(23:8000, dq5tables MONSTER_FIELDS)의 비트 수. FC 레코드(18:$8046)는 HP·공격·수비·금화가 10비트다.
DQ5_BITS = {"HP": 11, "MP": 8, "민첩": 8, "공격": 9, "수비": 9, "경험치": 16, "금화": 10}
# DQ5 수비 1FF 는 게임이 7FF 로 읽는다(21:A2B5). FC 수비 1023(메탈 셋)은 그 값으로 받는다.
DQ5_DEFENCE_MAX = 0x1FF
# 드롭 확률 등급: FC 바이트 20 bit2-0(0 반드시, 1~6 은 12:$9286 의 20 10 08 04 02 01 /256, 7 은 1/4096)과 DQ5
# 27:8218 의 1/N(1, 8, 16, 32, 64, 128, 256, 4096)이 등급마다 같다.
FC_DROP_NONE = 0x7F


def fc_monster_fields(record):
    """FC 몬스터 레코드 22바이트 → DQ5 표의 이름으로 된 값과 FC 드롭(물건 번호 또는 None, 등급)."""
    ten = lambda lo, hi: record[lo] | (record[hi] & 3) << 8  # noqa: E731
    drop = record[8] & 0x7F
    return ({"HP": ten(4, 15), "MP": record[3], "민첩": record[2], "공격": ten(5, 16), "수비": ten(6, 17),
             "경험치": record[0] | record[1] << 8, "금화": ten(7, 18)},
            None if drop == FC_DROP_NONE else drop, record[20] & 7)


def monster_fit(prg, dq5, ids=None):
    """FC 몬스터를 DQ5 몬스터 자리에 옮길 때 걸리는 것: {FC ID: {name, fields, over, drop, drop_rate, dq5_drop}}.
    over 는 DQ5 비트 수를 넘는 필드(수비 1023 은 DQ5 1FF 로 받으므로 뺌), dq5_drop 은 이름이 같은 DQ5 물건 번호
    (없으면 None). ids 가 없으면 모든 몬스터."""
    import dq4data
    import dq4text
    from dq5chest import item_name
    from dq5map import Rom
    rom = Rom(dq5)
    names = {}
    for k in range(0xD8):
        names.setdefault(item_name(rom, k), k)
    kana = str.maketrans("りべぺへぼ", "リベペヘボ")
    items = dq4data.name_list(prg, "item")
    out = {}
    for i, name, _, _, record in dq4data.monsters(prg):
        if ids is not None and i not in ids:
            continue
        fields, drop, rate = fc_monster_fields(record)
        over = [k for k, v in fields.items() if v >= 1 << DQ5_BITS[k] and not (k == "수비" and v == 0x3FF)]
        drop_name = None if drop is None else dq4text.text(items[drop + 1])
        dq5_drop = None if drop is None else names.get(drop_name, names.get(drop_name.translate(kana)))
        out[i] = {"name": name, "fields": fields, "over": over, "drop": drop_name, "drop_rate": rate,
                  "dq5_drop": dq5_drop}
    return out


def zone_monsters(prg, zones):
    """FC 구역(필드·던전 번호) 레코드 칸에 나오는 몬스터 ID."""
    enc = _fc(prg)
    return sorted({m for z in zones for m in enc.zone(prg, z)["slots"] if m not in (0, 0xFF)})


# ---- 3장 밤·낮 칸과 전투 뒤 물건 ----
#
# 형식 문서 sfc/dq4/docs/dq4-ch3-monsters-format.md.
#
# 밤·낮 칸: FC 필드는 첫 무리를 고를 때 낮이면 칸 4·10·13, 밤이면 칸 0·6 을 빼고(dq4encounter.MASK_FIRST), 둘째 무리부터는
# 칸 0~3(낮)·1~4(밤)에서 고른다(MASK_SECOND). 둘째 마스크는 첫 마스크를 칸 0~4 로 자른 것과 같아, 빠진 칸의 무게를 0 으로
# 두면 두 단계 모두 FC 와 같다. DQ5 는 칸 무게를 두 곳(23:E904 첫 무리, 23:EAAD 둘째 종부터)에서 읽으므로 둘 다 훅을 건다.
# 마스크는 3장 flag(chapter3_flag)가 켜진 동안 3장 필드 구역(CH3_FIELD)에만 건다: 1·2장 롬의 조우는
# 그대로다. 밤은 DQ5 의 밤 판정 21:8000(carry 면 밤, 고정 무리의 밤 칸이 쓰는 것)이다.
#
#   23:E8EE  LDY #$FFFF / STY $1001 → JSL night:  구역(X = 구역 × 22)이 표에 있고 3장 flag 면 그 낮·밤 마스크를 MASK 에,
#            아니면 0. 원래 두 명령을 하고 돌아온다
#   23:E907·23:EAB0  AND #$07 / STA $0000,Y → JSL weight:  칸 Y 의 MASK 비트가 켜져 있으면 무게 0
#
# 전투 뒤 물건: FC 3장(12:$91DE, $615A = 2)은 몬스터 떨어뜨림 대신 16칸 표를 rand(16) 칸부터 차례로 돌며 rand(256) < 문턱이면
# 그 물건을 얻는다. 문턱 0 인 칸(はがねのつるぎ·てつのよろい)은 톨네코 레벨이다(fc/dq4/docs/dq4-chapter3-format.md
# 「전투 뒤 물건」). 몬스터를 하나라도 쓰러뜨렸을 때만 돈다(FC $7200 은 쓰러뜨린 몬스터, 처음 FF; DQ5 는 쓰러뜨린 수
# $111A 가 처음 FF).
#
#   25:8966  LDA $1116 / CMP #$FF / BNE → JSL drop / BNE:  3장 flag 가 아니면 원래 판정(Z = 후보 없음). 3장이면 위 표를 굴려
#            못 얻으면 Z = 1(떨어뜨림 없음), 얻으면 $46 = 물건, $42 = 마지막으로 쓰러뜨린 종류($111C)의 칸으로 두고 돌아갈
#            곳을 25:89AA(떨어뜨릴 물건을 $46 에서 읽는 곳)로 바꾼다. 메시지는 DQ5 의 떨어뜨림 그대로(FC 3장은 「もっていた」)

# 코드와 표. 뱅크 4E 는 다른 도구가 쓰지 않는다
CH3_CODE_AT = 0x4E8000
# 23:E8EE 에서 정한 이번 조우의 칸 마스크(16비트, bit k = DQ5 칸 k 를 뺌). 7E:1A86~1A97 은 전원부터 배·필드·전투까지
# 아무도 읽지 않는 자리이고(dq4dungeonrate.RAM), 1A86~1A91 은 던전 걸음 훅, 1A94~1A97 은 소리 패치가 쓴다
MASK = 0x7E1A92
NIGHT_SITE, NIGHT_ORIG = 0x23E8EE, bytes((0xA0, 0xFF, 0xFF, 0x8C, 0x01, 0x10))
WEIGHT_SITES = (0x23E907, 0x23EAB0)
WEIGHT_ORIG = bytes((0x29, 0x07, 0x99, 0x00, 0x00))
IS_NIGHT = 0x218000
CH3_ZONE_RECORD = 22            # 23:96F3 + 구역 × 22
FC_FIXED_SLOT = 12

DROP_SITE, DROP_ORIG = 0x258966, bytes((0xAD, 0x16, 0x11, 0xC9, 0xFF, 0xD0, 0x03))
DROP_ITEM = 0x2589AA        # LDA $46 / CMP #$FF: 떨어뜨릴 물건
RANDOM = 0x00953E           # A(16비트) = n → 0~n-1
CANDIDATE, KILLS, LAST_KIND = 0x7E1116, 0x7E111A, 0x7E111C
TORNEKO_LEVEL = 0x7E2052    # 일행 기록 0(7E:2040) + 12. 3장 일행 기록 0 은 톨네코
BATTLE_FIELD = 0x88         # BRK 88 n: 칸 $42 의 전투 필드 n → $46
KIND_FIELD = 0x78
MONSTER_SLOTS = 0x10

# 떠돌이 상인(FC 18:$9D12): 3장 필드 조우의 1/10 은 싸우지 않고 여관(rand(256) < 16)이나 도구점
MERCHANT_RATE = 10
MERCHANT_INN = 0x10
EVENT_SCRIPT, EVENT_FLAG = 0x7E19B3, 0x7E19AE
CELLS_SINCE_FIGHT = 0x7E1A9A
# 말을 걸 인물 칸: 필드에서 인물 표(대화 번호 7E:36E0·7E:3700)의 끝 칸은 비어 있다(실측: 1D~1F 가 0)
MERCHANT_SLOT = 0x1F
TALK_LOW, TALK_HIGH = 0x36E0, 0x3700
TALK = 0x06AF1C             # JSR $AF20 / RTL: A = 인물 칸으로 대화(06:AFF4 가 대화 번호로 갈래)
TALK_SHOP, TALK_INN = 0x02, 0x06    # 특수 기능 도구점·여관(06:DBD2)
WAKE_SITE, WAKE_ORIG = 0x06E462, bytes((0xA5, 0xBC, 0xC9, 0x01))     # 여관에서 깬 뒤 맵 고르기(06:E43A 안)

# FC 3장 전용 표(12:$91DE): 문턱 12:$928E, 물건 12:$929E 의 16칸
FC_BANK, FC_THRESHOLDS, FC_ITEMS, DROP_SLOTS = 0x12, 0x928E, 0x929E, 16


def _rd(prg, bank, addr, n):
    o = bank * 0x4000 + (addr & 0x3FFF)
    return list(prg[o:o + n])


def fc_drop_table(prg):
    """[(문턱, FC 물건)] 16칸. 문턱 0 은 톨네코 레벨."""
    return list(zip(_rd(prg, FC_BANK, FC_THRESHOLDS, DROP_SLOTS), _rd(prg, FC_BANK, FC_ITEMS, DROP_SLOTS)))


def drop_roll(table, level, start, rolls):
    """FC 3장 전용 표를 start 칸부터 굴린 칸(못 얻으면 None). rolls 는 칸마다 쓰는 rand(256) 값(앞에서부터)."""
    for k in range(DROP_SLOTS):
        x = (start + k) % DROP_SLOTS
        threshold = table[x][0] or level
        if rolls[k] < threshold:
            return x
    return None


def drop_chance(table, level):
    """한 번 굴려 무엇이든 얻을 확률(시작 칸 고르게)."""
    total = 0.0
    for start in range(DROP_SLOTS):
        miss = 1.0
        for k in range(DROP_SLOTS):
            miss *= 1 - (table[(start + k) % DROP_SLOTS][0] or level) / 256
        total += 1 - miss
    return total / DROP_SLOTS


def dq5_drop_items(prg, dq5):
    """FC 표의 물건 16칸 → DQ5 물건 번호(가게·상자와 같은 짝, dq4monport.drop_items). 짝이 없으면 ValueError."""
    import dq4monport
    of = dq4monport.drop_items(prg, dq5)
    out = []
    for _, item in fc_drop_table(prg):
        m = of(item)
        if m is None:
            raise ValueError(f'FC 물건 {item:02X} 에 DQ5 짝이 없음')
        out.append(m)
    return out


def ch3_masks(prg, z):
    """FC 필드 구역 z 의 (낮 마스크, 밤 마스크): FC 첫 무리 마스크에서 빠지는 FC 칸이 놓인 DQ5 칸의 비트
    (placed 의 짝). 필드의 고정 편성 칸 12 는 낮·밤 모두 남아 고정 무리 칸 10 은 보지 않는다."""
    import dq4encounter
    _, _, origin, _ = placed(prg, z)
    out = []
    for mode in ('day', 'night'):
        keep = dq4encounter.MASK_FIRST[mode]
        out.append(sum(1 << k for k, fc in origin.items() if not keep >> fc & 1))
    return tuple(out)


def ch3_zone_masks(prg, report):
    """[(DQ5 구역, 낮 마스크, 밤 마스크)]: 3장 필드 구역(CH3_FIELD) 모두. 마스크가 없는 구역도 떠돌이 상인이 나오는
    구역이라 둔다. report 는 docs 의 보고(FC 구역 → zone)."""
    return [(report[f'{z:02X}']['zone'], *ch3_masks(prg, z)) for z in CH3_FIELD]


def _long(v):
    return v.to_bytes(3, 'little')


def ch3_code(rows, items, at=CH3_CODE_AT):
    from dq4environmentrom import _Asm
    """(코드, 라벨). rows 는 zone_masks, items 는 DQ5 물건 16칸(dq5_drop_items)."""
    flag, bit = chapter3_flag()
    a = _Asm(at)
    # 23:E8EE 에서: M 8비트, X 16비트, DB 23, X = 구역 × 22
    a.label('night').b(0x08, 0x48, 0xDA)                                     # PHP PHA PHX
    a.b(0xC2, 0x20, 0xA9, 0x00, 0x00, 0x8F, *_long(MASK))                    # REP #$20 / LDA #0 / STA MASK
    a.b(0xE2, 0x20, 0xAF, *_long(flag), 0x29, bit).rel(0xF0, 'night_out')     # SEP #$20 / LDA flag / AND / BEQ
    a.b(0xC2, 0x20, 0x8A, 0xA2, 0x00, 0x00)                                  # REP #$20 / TXA / LDX #0
    a.label('zone').long(0xDF, 'zones').rel(0xF0, 'found')                  # CMP zones,X / BEQ
    a.b(0xE8, 0xE8, 0xE8, 0xE8, 0xE8, 0xE8)                                  # INX ×6
    a.b(0xE0, *(6 * len(rows)).to_bytes(2, 'little')).rel(0x90, 'zone')      # CPX #n / BCC
    a.rel(0x80, 'night_16')
    a.label('found').b(0xA9, MERCHANT_RATE, 0x00, 0x22, *_long(RANDOM))    # rand(10)
    a.label('rolled10').b(0xC9, 0x00, 0x00).rel(0xF0, 'merchant')            # CMP #0 / BEQ
    a.b(0x22, *_long(IS_NIGHT)).rel(0xB0, 'dark')                            # JSL 21:8000 / BCS
    a.long(0xBF, 'zones', 2).rel(0x80, 'store')                             # LDA zones+2,X (낮)
    a.label('dark').long(0xBF, 'zones', 4)                                  # LDA zones+4,X (밤)
    a.label('store').b(0x8F, *_long(MASK))
    a.label('night_16').b(0xE2, 0x20)
    a.label('night_out').b(0xFA, 0x68, 0x28)                                 # PLX PLA PLP
    a.b(*NIGHT_ORIG, 0x6B)                                                   # LDY #$FFFF / STY $1001 / RTL
    # 떠돌이 상인: 이벤트 스크립트를 걸고(23:E2F4 와 같이 $19B3~$19B5·$19AE bit7) 걸음 수를 처음부터, 23:E7C2 는 조우 없음
    # (23:E91C 의 PLB / PLP / CLC / RTL)으로 끝낸다. 여기는 M 16비트, X 16비트
    a.label('merchant').word(0xA9, 'script').b(0x8F, *_long(EVENT_SCRIPT))   # LDA #script / STA $19B3
    a.b(0xE2, 0x20, 0xA9, at >> 16)                                           # SEP / LDA #뱅크(스크립트는 이 코드와 한 뱅크)
    a.b(0x8F, *_long(EVENT_SCRIPT + 2))                                       # STA $19B5
    a.b(0xAF, *_long(EVENT_FLAG), 0x09, 0x80, 0x8F, *_long(EVENT_FLAG))       # $19AE |= 80
    a.b(0xA9, 0x00, 0x8F, *_long(CELLS_SINCE_FIGHT))                          # $1A9A = 0
    a.b(0xFA, 0x68, 0x28, 0x68, 0x68, 0x68, 0xAB, 0x28, 0x18, 0x6B)          # PLX PLA PLP / 돌아갈 곳 버림 / PLB PLP CLC RTL
    # 이벤트 스크립트: 네이티브 하나(00:C046 이 7E:1A2E 의 JSL 로 부름, M·X 8비트) 뒤 끝
    a.label('script').long(0xA0, 'talk').b(0xFF)
    # 16/256 이면 여관(대화 번호 06), 아니면 도구점(02)을 인물 칸 MERCHANT_SLOT 에 두고 말을 건다(06:AF1C, A = 칸,
    # 05:D596 과 같이 M 8비트·X 16비트). 키는 필드 $BC/$BD 의 상인 키(dq4shopport.MERCHANT_MAP)
    a.label('talk').b(0x08, 0x8B, 0xC2, 0x30)                                # PHP PHB / REP #$30
    a.b(0xA9, 0x00, 0x01, 0x22, *_long(RANDOM), 0xE2, 0x20)                  # rand(256)
    a.label('rolled256').b(0xC9, MERCHANT_INN, 0xA9, TALK_SHOP).rel(0xB0, 'talk_set')  # CMP #16 / LDA #02 / BCS
    a.b(0xA9, TALK_INN)
    a.label('talk_set').b(0x8F, *_long(0x7E0000 | TALK_LOW + MERCHANT_SLOT))
    a.b(0xA9, 0x00, 0x8F, *_long(0x7E0000 | TALK_HIGH + MERCHANT_SLOT))      # 상위 0
    # 06:AF20 은 DB 를 정하지 않고 $0F1E 에 쓴다: WRAM 이 보이는 뱅크로
    a.b(0xA9, 0x7E, 0x48, 0xAB, 0xA9, MERCHANT_SLOT, 0x22, *_long(TALK))     # DB 7E / LDA #칸 / JSL 06:AF1C
    a.b(0xAB, 0x28, 0x6B)                                                     # PLB PLP RTL
    # 06:E462 에서(여관에서 깬 뒤, A 8비트): 원래 LDA $BC / CMP #$01 은 그룹 01(DQ5 ラインハット 여관)이면 01/00 (50,83)
    # 에 세운다. 필드의 $BC 도 01 이라 필드에서 자면 그 맵으로 갔다: 필드($BE bit7 꺼짐)면 Z = 0 으로 지금 자리를 다시 그림
    a.label('wake').b(0xAF, 0xBE, 0x00, 0x7E).rel(0x10, 'wake_field')         # LDA $BE / BPL
    a.b(0xAF, 0xBC, 0x00, 0x7E, 0xC9, 0x01, 0x6B)                            # LDA $BC / CMP #$01 / RTL
    a.label('wake_field').b(0xA9, 0x00, 0xC9, 0x01, 0x6B)                     # Z = 0
    # 23:E907·23:EAB0 에서: M 8비트, X·Y 16비트, Y = 칸
    a.label('weight').b(0x29, 0x07).rel(0xF0, 'weight_store')               # AND #7 / BEQ
    a.b(0x48, 0x5A, 0xC2, 0x20, 0xAF, *_long(MASK))                         # PHA PHY REP #$20 LDA MASK
    a.b(0xC0, 0x00, 0x00).rel(0xF0, 'test')                                 # CPY #0 / BEQ
    a.label('shift').b(0x4A, 0x88).rel(0xD0, 'shift')                       # LSR / DEY / BNE
    a.label('test').b(0xE2, 0x20, 0x4A, 0x7A, 0x68).rel(0x90, 'weight_store')  # SEP LSR PLY PLA BCC
    a.b(0xA9, 0x00)                                                          # LDA #0
    a.label('weight_store').b(0x99, 0x00, 0x00, 0x6B)                        # STA $0000,Y / RTL
    # 25:8966 에서: M·X 8비트
    a.label('drop').b(0xAF, *_long(flag), 0x29, bit).rel(0xD0, 'ch3')
    a.b(0xAF, *_long(CANDIDATE), 0xC9, 0xFF, 0x6B)                           # 원래 판정
    a.label('ch3').b(0xAF, *_long(KILLS), 0xC9, 0xFF).rel(0xD0, 'roll')
    a.label('none').b(0xA9, 0x00, 0x6B)                                      # Z = 1: 떨어뜨림 없음
    a.label('roll').b(0xC2, 0x20, 0xA9, DROP_SLOTS, 0x00, 0x22, *_long(RANDOM))  # rand(16)
    a.label('start').b(0xE2, 0x20, 0xAA, 0xA0, DROP_SLOTS)                        # SEP / TAX / LDY #16
    a.label('slot').long(0xBF, 'thresholds').rel(0xD0, 'have')               # LDA thresholds,X / BNE
    a.b(0xAF, *_long(TORNEKO_LEVEL))
    a.label('have').b(0x85, 0x46, 0x5A)                                       # STA $46 / PHY
    a.b(0xC2, 0x20, 0xA9, 0x00, 0x01, 0x22, *_long(RANDOM))                 # rand(256)
    a.label('rolled').b(0xE2, 0x20, 0x7A, 0xC5, 0x46).rel(0x90, 'hit')       # SEP / PLY / CMP $46 / BCC
    a.b(0xE8, 0x8A, 0x29, DROP_SLOTS - 1, 0xAA, 0x88).rel(0xD0, 'slot')           # INX TXA AND TAX DEY BNE
    a.rel(0x80, 'none')
    a.label('hit').long(0xBF, 'items').b(0x48, 0x64, 0x42)                   # LDA items,X / PHA / STZ $42
    a.label('find').b(0x00, BATTLE_FIELD, KIND_FIELD, 0xA5, 0x46)            # BRK 88 78 / LDA $46
    a.b(0xCF, *_long(LAST_KIND)).rel(0xF0, 'found_kind')                     # CMP $111C / BEQ
    a.b(0xE6, 0x42, 0xA5, 0x42, 0xC9, MONSTER_SLOTS).rel(0x90, 'find')        # INC LDA CMP BCC
    a.b(0x64, 0x42)
    a.label('found_kind').b(0x68, 0x85, 0x46)                                # PLA / STA $46
    back = DROP_ITEM - 1
    a.b(0xC2, 0x20, 0xA9, back & 0xFF, back >> 8 & 0xFF, 0x83, 0x01, 0xE2, 0x20, 0x6B)  # 돌아갈 곳 / RTL
    a.label('zones')
    for zone, day, night in rows:
        a.b(*(zone * CH3_ZONE_RECORD).to_bytes(2, 'little'), *day.to_bytes(2, 'little'), *night.to_bytes(2, 'little'))
    a.label('thresholds')
    a.b(*(t for t, _ in items))
    a.label('items')
    a.b(*(m for _, m in items))
    return a.assemble()


def ch3_writes(prg, dq5, report, at=CH3_CODE_AT):
    """dq5patch/1 쓰기: 코드·표와 훅 네 곳. report 는 docs 의 보고."""
    table = fc_drop_table(prg)
    items = list(zip((t for t, _ in table), dq5_drop_items(prg, dq5)))
    rows = ch3_zone_masks(prg, report)
    if not rows:
        raise ValueError('밤·낮 마스크가 있는 3장 필드 구역이 없음')
    blob, labels = ch3_code(rows, items, at)

    def put(addr, new, orig, note):
        return {'at': f'{addr >> 16:02X}:{addr & 0xFFFF:04X}', 'hex': new.hex(' ').upper(), 'orig': orig.hex(' ').upper(),
                'note': note}

    def jsl(label):
        return bytes((0x22, *_long(labels[label])))
    out = [{'at': f'{at >> 16:02X}:{at & 0xFFFF:04X}', 'hex': blob.hex(' ').upper(),
            'note': '3장 몬스터: 밤·낮 칸 마스크와 3장 전용 전투 뒤 물건'},
           put(NIGHT_SITE, jsl('night') + b'\xEA\xEA', NIGHT_ORIG, '조우마다 3장 필드 구역의 밤·낮 칸 마스크를 정함')]
    out += [put(site, jsl('weight') + b'\xEA', WEIGHT_ORIG, '칸 무게를 읽을 때 마스크로 뺀 칸은 0')
            for site in WEIGHT_SITES]
    out.append(put(DROP_SITE, jsl('drop') + bytes((0xD0, 0x04, 0xEA)), DROP_ORIG, '3장이면 전투 뒤 물건을 FC 3장 표로'))
    out.append(put(WAKE_SITE, jsl('wake'), WAKE_ORIG, '필드 여관(떠돌이 상인)에서 깨면 그룹 01 갈래로 가지 않음'))
    return out


def main():
    from kr_patch.fc import ines
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dq5", default="rom/dq5.sfc", type=Path)
    ap.add_argument("--dq4", default="rom/dq4.nes", type=Path)
    ap.add_argument("-o", "--out", required=True, type=Path)
    args = ap.parse_args()
    import subprocess
    args.out.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, str(DQ5_TOOLS / "dq5encounterwrite.py"), args.dq5, "dump", "-o",
                    args.out / "encounter-orig.json"], check=True, capture_output=True)
    enc = json.loads((args.out / "encounter-orig.json").read_text(encoding="utf-8"))
    progress, grid, report = docs(ines.prg(args.dq4.read_bytes()), args.dq5.read_bytes(), enc)
    for name, doc in (("progress", progress), ("encounter", grid), ("report", report)):
        (args.out / f"{name}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
