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
    0x29: 0x25,  # ~ おおめだま -> ダークアイ(3장 격투장에만, dq4shopport.arena)
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
# 1·3장 구역에 처음 FC 값으로 넣은 종(dq4monport.NUMBERED: 그림은 대역의 그림 레코드)
MONSTERS.update({fc: m for fc, (m, _) in dq4monport.NUMBERED.items()})
# FC 3장의 구역(dq4encounter.ch3_reach 로 닿는 필드 구역과 그 입구 던전의 구역)
CH3_FIELD, CH3_DUNGEON = (0x14, 0x15, 0x16, 0x17), (0x48, 0x49, 0x4A, 0x4B)
CH3_ZONES = CH3_FIELD + CH3_DUNGEON
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
    coefs = _coefs(dq5)
    return min(range(8), key=lambda i: (rate_error(prg, base, coefs[i], kinds), i))


def rate_error(prg, base, coef, kinds=LAND_KINDS):
    """field_rate_index's error of coefficient `coef` for FC base rate `base`; a coefficient that never fights is
    infinitely wrong."""
    enc = _fc(prg)
    factors = [f for t in (enc.TERRAIN_DAY, enc.TERRAIN_NIGHT) for k in kinds if (f := enc.rd(prg, t + k))]
    steps = [dq5_steps(coef, f) for f in factors]
    if not all(steps):
        return math.inf
    return sum(abs(math.log(s / (2 * fc_steps(prg, base, f)))) for s, f in zip(steps, factors))


# 계수 표(23:EA44)에 기본 조우율 28 에 맞는 값이 없어(가장 가까운 2B 로는 풀밭이 FC 보다 15% 드묾) 그 기본의 필드
# 구역(1~3장에서는 구역 08 하나)만 FC 에 가장 가까운 계수(own_coef)를 coef 훅이 표 대신 준다. 다른 구역은 표 그대로
OWN_COEF_BASES = (28,)
COEF_SITE, COEF_ORIG = 0x23E892, bytes.fromhex("A9 00 EB A5 01 A8 B9 44 EA")   # LDA #0 / XBA / LDA $01 / TAY / LDA $EA44,Y


@functools.cache
def own_coef(prg, base):
    """1~FF 가운데 rate_error 가 가장 작은 계수(같으면 작은 값)."""
    return min(range(1, 0x100), key=lambda c: (rate_error(prg, base, c), c))


def own_coefs(prg, report):
    """[(DQ5 구역, 계수)]: 기본 조우율이 OWN_COEF_BASES 인 필드 구역(fc_zones·chapter3_zones). report 는 docs 의 보고."""
    enc = _fc(prg)
    out = []
    for z in sorted({*fc_zones(prg), *chapter3_zones(prg)}):
        base = enc.zone(prg, z)["rate"]
        if base in OWN_COEF_BASES and f"{z:02X}" in report:
            out.append((report[f"{z:02X}"]["zone"], own_coef(prg, base)))
    return out


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


def fixed_groups(prg, dq5, fixed):
    """dq5encounter/1 fixed_groups of the FC formations `fixed` (dungeon_fixed): each member's monster through
    MONSTERS and the DQ5 count code of the same range."""
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
        out.append({"index": k, "members": [{"monster": MONSTERS[m], "count_code": codes[lo, hi]}
                                            for m, lo, hi in members]})
    return out


def placed(prg, z, dungeon=None, field_fixed=None, monsters=None):
    """(DQ5 slots 0-9, fixed slot, {DQ5 slot 0-10: FC slot}, FC slots left out) of FC zone z, as record() lays them.
    The fixed slot (DQ5 10) takes slot 12's formation through `dungeon` (dungeon_fixed) in a dungeon zone, or through
    `field_fixed` on the field; else it is empty."""
    enc = _fc(prg)
    monsters = MONSTERS if monsters is None else monsters
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
    through `field_fixed` (the formations of field_formations). Monsters go through MONSTERS."""
    enc = _fc(prg)
    rec = enc.zone(prg, z)
    w = enc.weights(prg, rec["row"])
    slots, fixed_slot, _, dropped = placed(prg, z, dungeon, field_fixed)
    rate = field_rate_index(prg, dq5, rec["rate"], kinds) if dungeon is None else dungeon_rate_index(prg, dq5, rec["rate"])
    return {"level": rec["b1"], "slots": slots, "fixed": fixed_slot,
            "species_weights": [3, 1 if w[14] else 0, 1 if w[15] else 0], "rate_index": rate,
            "flag_1000": rec.get("b0", 0) & 3, "flag_1010": False, "fixed_night_only": False}, dropped


def docs(prg, dq5, enc, dungeon=()):
    """(dq5progress/1, dq5encounter/1, report) for the FC field zones (with chapter 3's, chapter3_assign) and the FC
    dungeon zones `dungeon` (dungeon_zones). The terrain rates are terrain_rates; the grid hook is grid_hook_writes."""
    assign = zones(prg, enc)
    late = chapter3_assign(prg, enc, dungeon)
    field = field_formations(prg)
    fixed = dungeon_fixed(prg, dungeon, field)
    groups = fixed_groups(prg, dq5, fixed)
    records, report = [], {}
    found_dungeon = dungeon_zones(prg, enc, dungeon)
    for kind, found in (("field", {**assign, **late}), ("dungeon", found_dungeon)):
        for fc, area in found.items():
            fields, dropped = record(prg, dq5, fc, fixed if kind == "dungeon" else None,
                                     field_fixed=fixed if fc in field else None)
            _, _, origin, _ = placed(prg, fc, fixed if kind == "dungeon" else None, fixed if fc in field else None)
            records.append({"index": area, **fields})
            monsters = {sl["monster"] for sl in fields["slots"] if sl["weight"]}
            if fields["fixed"]["weight"]:
                monsters |= {m["monster"] for m in groups[fields["fixed"]["group"]]["members"]}
            report[f"{fc:02X}"] = {"zone": area, "kind": kind, "level": fields["level"], "dropped_slots": dropped,
                                   "rate_index": fields["rate_index"], "fixed": fields["fixed"],
                                   "monsters": sorted(monsters), "origin": sorted(origin.items())}
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


# ---- FC 무리 고르기, 3장 떠돌이 상인과 전투 뒤 물건 ----
#
# 형식 문서 sfc/dq4/docs/dq4-ch3-monsters-format.md.
#
# 무리 고르기(1~3장 모든 구역): DQ5 는 칸 무게를 3비트로, 여러 종 무리의 종 수를 2비트 무게로 고른다. FC 대로 고르려고
# 구역마다 FC 칸 차례의 (DQ5 칸, FC 무게) 목록을 두고 FC 식(18:$9DDE)으로 뽑는다: FF 칸과 마스크(낮 칸 4·10·13, 밤 칸 0·6
# 을 뺌, 둘째 무리부터는 칸 0~3/1~4, 던전은 모두)로 빠진 칸을 빼고 무게 합 S, r = S × 난수 >> 8(S = FF 면 난수 그대로),
# 누적 무게가 r 이상이 되는 첫 칸. 여러 종 무리는 첫 무리 + 둘째 무리에 난수 < 무게 줄 바이트 14 면 셋째, 그다음 난수 <
# 바이트 15 면 넷째(18:$9ED8). 난수는 DQ5 조우의 난수(23:EAFD, $0993~$0996 의 32비트 ×3 + 15AD, 위 16비트의 아래 바이트)를
# 그대로 돌린다. 밤은 DQ5 의 밤 판정 21:8000(carry 면 밤)이다. 표에 없는 구역은 DQ5 원래 고르기다.
#
#   23:E8FE  PHX / LDY #0 / STZ $0F → JML pick:  구역(X = 구역 × 22)을 표에서 찾아 낮·밤 칸 묶음 주소를 PICK 에 두고 첫 무리
#            칸을 Y 로 23:E93F 에. 고를 칸이 없으면 23:E91D(조우 없음). 표에 없으면 PICK = FFFF, 원래 명령을 하고 23:E904
#   23:E9B4  STY $0A / LDY #0 → JSL count:  PICK 이 있으면 셋째·넷째를 굴려 $0C(0~2) 로 23:E9E8 에, 없으면 원래 명령
#   23:EAA7  PHX / LDY #0 → JSL pick2 / RTS:  PICK 이 있으면 둘째 무리부터의 칸(A, carry), 없으면 원래 23:EAAD
#
# 떠돌이 상인: 23:E8EE  LDY #$FFFF / STY $1001 → JSL merchant:  3장 flag 이고 구역이 3장 필드(CH3_FIELD)면 rand(10) = 0 일 때
# 싸우지 않고 상인(아래). 아니면 원래 두 명령을 하고 돌아온다
#
# 전투 뒤 물건: FC 3장(12:$91DE, $615A = 2)은 몬스터 떨어뜨림 대신 16칸 표를 rand(16) 칸부터 차례로 돌며 rand(256) < 문턱이면
# 그 물건을 얻는다. 문턱 0 인 칸(はがねのつるぎ·てつのよろい)은 톨네코 레벨이다(fc/dq4/docs/dq4-chapter3-format.md
# 「전투 뒤 물건」). 몬스터를 하나라도 쓰러뜨렸을 때만 돈다(FC $7200 은 쓰러뜨린 몬스터, 처음 FF; DQ5 는 쓰러뜨린 수
# $111A 가 처음 FF).
#
#   25:8966  LDA $1116 / CMP #$FF / BNE → JSL drop / BNE:  3장 flag 가 아니면 원래 판정(Z = 후보 없음). 3장이면 위 표를 굴려
#            못 얻으면 Z = 1(떨어뜨림 없음), 얻으면 $46 = 물건, $42 = 0(메시지 이름은 칸 0 의 몬스터)으로 두고 돌아갈
#            곳을 25:89AA(떨어뜨릴 물건을 $46 에서 읽는 곳)로 바꾼다. 메시지는 DQ5 의 떨어뜨림 그대로(FC 3장은 「もっていた」)

# 코드와 표. 뱅크 4E 는 다른 도구가 쓰지 않는다
CH3_CODE_AT = 0x4E8000
CH3_CODE_END = 0x4EC000     # 몬스터·상인 몫의 끝. 4E:C000~ 은 3장 엔돌 몫(dq4ch3slots)
# 23:E8FE 에서 고른 이번 조우의 낮·밤 칸 묶음 주소(16비트, 뱅크 CH3_CODE_AT, FFFF = 표에 없는 구역). 7E:1A86~1A97 은 전원부터
# 배·필드·전투까지 아무도 읽지 않는 자리이고(dq4dungeonrate.RAM), 1A86~1A91 은 던전 걸음 훅, 1A94~1A97 은 소리 패치가 쓴다
PICK = 0x7E1A92
NIGHT_SITE, NIGHT_ORIG = 0x23E8EE, bytes((0xA0, 0xFF, 0xFF, 0x8C, 0x01, 0x10))
PICK_SITE, PICK_ORIG = 0x23E8FE, bytes((0xDA, 0xA0, 0x00, 0x00, 0x64, 0x0F))
FIRST_LOOP, NO_ENCOUNTER = 0x23E904, 0x23E91D
FORMED = 0x23EA40          # PLB / PLP / SEC / RTL: 무리를 다 지은 끝
# 26:832E STZ $71 / LDA $1000: 선제·기습 두 난수(rand(32) < 27:8043 쌍)를 FC 18:$A20E 의 rand(33) 하나와 문턱 둘로
SURPRISE_SITE, SURPRISE_ORIG = 0x26832E, bytes((0x64, 0x71, 0xAD, 0x00, 0x10))
SURPRISE_DONE = 0x26835B
BATTLE_FLAGS = 0x7E1000
RAND8, SURPRISE_RANGE = 0x00953A, 0x21     # A = n → 0~n-1(M·X 8비트), FC BRK 17 0F 에 A = 21
RNG_LOW, RNG_HIGH = 0x0993, 0x0995     # 23:EAFD 의 32비트 난수(뱅크 23 의 WRAM 거울로 읽음)
RNG_ADD = 0x15AD
IS_NIGHT = 0x218000
CH3_ZONE_RECORD = 22            # 23:96F3 + 구역 × 22
FC_FIXED_SLOT = 12

DROP_SITE, DROP_ORIG = 0x258966, bytes((0xAD, 0x16, 0x11, 0xC9, 0xFF, 0xD0, 0x03))
DROP_ITEM = 0x2589AA        # LDA $46 / CMP #$FF: 떨어뜨릴 물건
RANDOM = 0x00953E           # A(16비트) = n → 0~n-1
CANDIDATE, KILLS = 0x7E1116, 0x7E111A
# 떨어뜨림 후보: DQ5 는 처음 쓰러뜨린 종류($1116, 20:A346)이고 다른 종류를 쓰러뜨리면 FF(20:A363, 섞인 무리는 떨어뜨림
# 없음), 물건·확률·이름은 마지막으로 빠진 몬스터 종류($1113, 20:A170, 도망 포함)의 칸에서 읽는다(25:8970). FC 는 마지막으로
# 쓰러뜨린 몬스터 칸($7200, 11:$91F1)의 물건이고 도망은 이를 바꾸지 않는다(실측). 20:A363 을 「쓰러뜨릴 때마다 $1116 = 그
# 종류」로, 25:8977·8984 가 $1113 대신 쓰러뜨릴 때마다 쓰는 마지막 종류 $111C(20:A33E)를 읽게 한다
LAST_KILL_SITE = 0x20A363
LAST_KILL_ORIG = bytes.fromhex('ad 16 11 c9 ff f0 09 c5 46 f0 05 a9 ff 8d 16 11')
LAST_KILL = bytes.fromhex('a5 46 8d 16 11') + bytes((0xEA,) * 11)
DROP_SPECIES = ((0x258977, bytes.fromhex('cd 13 11'), bytes.fromhex('cd 1c 11')),
                (0x258984, bytes.fromhex('ad 13 11'), bytes.fromhex('ad 1c 11')))
# 떨어뜨림 메시지(25:89BF BRK 9E B1 / 다음 BRK 9E 00 의 첫 바이트): FC 12:$9246 는 무리가 모두 한 종류면 01C7「…は
# たからばこを もっていた！」, 아니면 01C8「まもののむれは たからばこを もっていた！」. 0B1 의 한글을 FC 뜻으로 두고, 섞인
# 무리면 1A8. BRK 가 부른 뱅크를 DB 로 쓰므로 WRAM 거울이 있는 뱅크 0B(dq4monspecial 코드 뒤)에 둔다
DROP_MSG_SITE, DROP_MSG_ORIG = 0x2589BF, bytes.fromhex('00 9e b1 00')
# 덮은 넷째 바이트는 다음 BRK 9E 00 의 첫 바이트라 그 BRK 를 이 코드가 하고 25:89C5(BRK 16 35 00, 상자 여는 소리)로
# 돌아간다. 그 BRK 16 은 사운드 패치가 효과음 번호를 바꾸는 자리(dq4sound-game.args 2589C5=35:3F)라 옮기지 않는다.
# BRK 를 가리키는 JML 은 롬 장부 검사(dq4romledgercheck inv_hooks)가 빈 자리로 뛴 훅과 가르지 못해 RTL 로 돌아간다
DROP_MSG_TAIL, DROP_MSG_NEXT = bytes.fromhex('00 9e 00'), 0x2589C5
DROP_MSG_AT = 0x0BFFA0
# 전투가 끝날 때 무리(7E:1001~)는 비어 있고 그림 종류(7E:117C~)는 도망친 종류가 빠진다. 무리 몬스터 사본 7E:1156~1159
# (전투 시작 26:82B4, 부르기 20:DAC2 가 씀)은 남아 있어 FC 의 $6E45~ 처럼 도망친 무리도 센다
BATTLE_SPECIES = 0x7E1156
MSG_DROP, MSG_DROP_GROUP = 0x0B1, 0x1A8


def drop_msg_code(at=DROP_MSG_AT):
    """(바이트, 라벨): 전투의 무리 몬스터 7E:1156~1159 의 FF 아닌 것이 모두 같으면 BRK 9E B1, 아니면 BRK 9F A8, 그 뒤 원래의
    BRK 9E 00 과 25:89C5(RTL 로). M·X 8비트."""
    from dq4environmentrom import _Asm
    a = _Asm(at)
    a.label('drop_msg').b(0xA0, 0xFF, 0xA2, 0x00)
    a.label('dm_loop').b(0xBF, *_long(BATTLE_SPECIES), 0xC9, 0xFF).rel(0xF0, 'dm_next')
    a.b(0xC0, 0xFF).rel(0xD0, 'dm_cmp').b(0xA8).rel(0x80, 'dm_next')
    a.label('dm_cmp').b(0x48, 0x98, 0xC3, 0x01).rel(0xF0, 'dm_same').b(0x68).rel(0x80, 'dm_group')
    a.label('dm_same').b(0x68)
    a.label('dm_next').b(0xE8, 0xE0, 0x04).rel(0x90, 'dm_loop')
    a.b(0x00, 0x9E, MSG_DROP).rel(0x80, 'dm_tail')
    a.label('dm_group').b(0x00, 0x9F, MSG_DROP_GROUP & 0xFF)
    a.label('dm_tail').b(*DROP_MSG_TAIL, 0xA9, DROP_MSG_NEXT >> 16, 0x48, 0xF4, *((DROP_MSG_NEXT - 1) & 0xFFFF).to_bytes(2, 'little'), 0x6B)
    data, labels = a.assemble()
    if at + len(data) > 0x0C0000:
        raise ValueError('떨어뜨림 메시지 코드가 뱅크 0B 끝을 넘음')
    return data, labels
TORNEKO_LEVEL = 0x7E2052    # 일행 기록 0(7E:2040) + 12. 3장 일행 기록 0 은 톨네코

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
WAKE_RTS = 0x06E47F         # E43A 의 끝 RTS
FIELD_REDRAW = 0x06D98E     # 낮밤 바꾸기 06:D905 의 필드 갈래(LDA #$07 / JSL 03:A6CB / JSL 01:A04B …)

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


def merchant_zones(report):
    """떠돌이 상인이 나오는 DQ5 구역: 3장 필드 구역(CH3_FIELD). report 는 docs 의 보고(FC 구역 → zone)."""
    return [report[f'{z:02X}']['zone'] for z in CH3_FIELD]


def pick_lists(prg, z, mode, data=None):
    """FC 구역 z 의 (첫 무리 목록, 둘째 무리부터의 목록): FC 칸 차례로 [(FC 칸, FC 무게)]. mode 의 FC 마스크
    (dq4encounter.MASK_FIRST·MASK_SECOND)와 FF 칸을 빼고, data(zone_data)를 주면 그 자료에 없는 칸(DQ5 몬스터가
    없는 고정 편성)도 뺀다."""
    enc = _fc(prg)
    rec = enc.zone(prg, z)
    s, w = rec['slots'], enc.weights(prg, rec['row'])

    def usable(i):
        return data is None or (i in data['formations'] if i >= FORMATION_SLOT else True)

    def live(mask, n):
        return [(i, w[i]) for i in range(n) if mask >> i & 1 and s[i] != 0xFF and usable(i)]
    return live(enc.MASK_FIRST[mode], 14), live(enc.MASK_SECOND[mode], 5)


def zone_data(prg, z, monsters=None):
    """FC 구역 z 의 무리 짓기 자료: {'monsters': FC 칸 0~13 의 DQ5 몬스터(FF 없음, 칸 12·13 은 FF), 'codes': 무게 줄
    바이트 16·17(칸 6~10 의 마릿수 부호 3비트씩), 'formations': {12·13: [(DQ5 몬스터 또는 FF, 바탕, 폭)] 넷}}."""
    enc = _fc(prg)
    rec = enc.zone(prg, z)
    s, w = rec['slots'], enc.weights(prg, rec['row'])
    to = MONSTERS if monsters is None else monsters
    monsters = [0xFF if i >= FORMATION_SLOT or s[i] == 0xFF else to[s[i]] for i in range(14)]
    forms = {}
    for i in (12, 13):
        if s[i] == 0xFF:
            continue
        a = enc.rw(prg, enc.FORMATION) + 6 * s[i]
        r = [enc.rd(prg, a + k) for k in range(6)]
        members = []
        for g in range(4):
            c = r[g >> 1] >> (3 if g & 1 else 0) & 7
            members.append((0xFF if r[2 + g] == 0xFF else to.get(r[2 + g]), enc.rd(prg, enc.FORM_ADD + c),
                            enc.rd(prg, enc.FORM_CNT + c)))
        # 아직 DQ5 몬스터가 없는 FC 몬스터가 든 편성(5장 マネマネ 등)은 두지 않고 그 칸을 고르지 않는다
        if None not in (mon for mon, _, _ in members):
            forms[i] = members
    return {'monsters': monsters, 'codes': w[16] | w[17] << 8, 'formations': forms}


def fc_tables(prg):
    """FC 18 뱅크의 표: {'extra_max': $A464, 'extra_p': $A46C, 'solo_add': $A335, 'solo_cnt': $A32D,
    'surprise': $A45C(기습·선제 문턱 둘씩 넷)}(8칸씩)."""
    enc = _fc(prg)
    return {k: [enc.rd(prg, a + i) for i in range(8)] for k, a in (('extra_max', enc.EXTRA_MAX), ('extra_p', enc.EXTRA_P),
                                                                  ('solo_add', enc.SOLO_ADD), ('solo_cnt', enc.SOLO_CNT),
                                                                  ('surprise', enc.AMBUSH))}


def row_monsters(row):
    """pick_rows 의 한 줄에서 무리 짓기가 낼 수 있는 DQ5 몬스터(낮·밤 목록의 칸과 고정 편성 구성원)."""
    *_, modes, data = row
    out = set()
    for first, second in modes.values():
        for slot, _ in first + second:
            if slot < FORMATION_SLOT:
                out.add(data['monsters'][slot])
            else:
                out |= {m for m, _, _ in data['formations'][slot] if m != 0xFF}
    return out


def fc_surprise(thresholds, k, r):
    """FC 18:$A20E: 문턱 번호 k, r = rand(33) 일 때 $1000 아래 두 비트(DQ5 뜻: 0 보통, 1 기습, 2 선제)."""
    t0, t1 = thresholds[2 * k], thresholds[2 * k + 1]
    return 0 if r <= t0 else 1 if r <= t1 else 2


def fc_formation(row, tables, k, night, state):
    """FC 18:$9D6B~$9F78 의 무리 짓기 모형: ([(DQ5 몬스터, 마릿수)] 무리 차례, 다음 난수 상태). row 는 pick_rows 의 한 줄,
    k 는 장 번호($615A, 1장 0), 난수는 rng_next 를 차례로. 고를 칸이 없으면 ([], state)."""
    _, _, third, fourth, modes, data = row
    first, second = modes['night' if night else 'day']
    mons = data['monsters']

    def rnd():
        nonlocal state
        state, r = rng_next(state)
        return r

    def rand(n):
        return n * rnd() >> 8

    slot = fc_pick(first, rnd())
    if slot is None:
        return [], state
    groups = []
    if slot < 5:
        groups = [[mons[slot], 1]]
        for limit in (None, third, fourth):
            if limit is not None and rnd() >= limit:
                break
            s2 = fc_pick(second, rnd())
            if s2 is None:
                break
            groups.append([mons[s2], 1])
        total, at = len(groups), 0
        while total < tables['extra_max'][k] and rnd() < tables['extra_p'][k]:
            at = 0 if at >= len(groups) else at
            groups[at][1] += 1
            at, total = at + 1, total + 1
    elif slot == 5:
        groups = [[mons[5], 1]]
        s2 = fc_pick(second, rnd())
        if s2 is not None:
            groups.append([mons[s2], 3 + rand(5)])
    elif slot < 11:
        c = data['codes'] >> 3 * (slot - 6) & 7
        groups = [[mons[slot], tables['solo_add'][c] + rand(tables['solo_cnt'][c])]]
    elif slot == 11:
        groups = [[mons[11], 1]]
    else:
        # 18:$9E2D 는 몬스터가 FF 인 무리도 마릿수를 굴린다
        groups = [[m, n] for m, n in [(m, add + rand(cnt)) for m, add, cnt in data['formations'][slot]] if m != 0xFF]
    return [tuple(g) for g in groups], state


def fc_pick(entries, rnd):
    """FC 18:$9DDE 로 entries([(칸, 무게)])에서 난수 바이트 rnd 일 때 고르는 칸(없으면 None)."""
    total = sum(w for _, w in entries)
    if total > 0xFF:
        raise ValueError(f'무게 합 {total} 이 FF 를 넘음(FC 는 8비트로 더함)')
    r = rnd if total == 0xFF else total * rnd >> 8
    cum = 0
    for k, w in entries:
        cum += w
        if cum >= r:
            return k
    return None


def fc_pick_odds(entries):
    """{칸: 256 경우 중 몇 번}: 난수 바이트가 고르다고 볼 때 fc_pick 의 분포."""
    out = {}
    for rnd in range(256):
        k = fc_pick(entries, rnd)
        out[k] = out.get(k, 0) + 1
    return out


def species_odds(third, fourth):
    """여러 종 무리의 {종 수: 확률}: FC 무게 줄 바이트 14·15(/256, 18:$9ED8)."""
    p3, p4 = third / 256, fourth / 256
    return {2: 1 - p3, 3: p3 * (1 - p4), 4: p3 * p4}


def rng_next(state):
    """23:EAFD: 32비트 난수 state 의 다음 값과 그 난수 바이트(위 16비트의 아래 바이트)."""
    state = (state * 3 + RNG_ADD) & 0xFFFFFFFF
    return state, state >> 16 & 0xFF


def pick_rows(prg, report):
    """[(DQ5 구역, FC 구역, 셋째 /256, 넷째 /256, {낮·밤: (첫 목록, 둘째 목록)}, zone_data)]: docs 가 레코드를 쓰는 구역 모두(필드·
    던전·바다). 필드·바다는 FC 낮·밤 마스크, 던전은 dungeon 마스크를 낮·밤 모두에. report 는 docs 의 보고."""
    enc = _fc(prg)
    zones = [(r['zone'], int(fc, 16), dict(r['origin']), r['kind'] == 'dungeon') for fc, r in report.items()]
    sea = dict(placed(prg, SEA_ZONE)[2])
    taken = {r['zone'] for r in report.values()}
    zones += [(area, SEA_ZONE, sea, False) for area in SEA_AREAS if area not in taken]
    out = []
    for area, z, _, dungeon in sorted(zones):
        w = enc.weights(prg, enc.zone(prg, z)['row'])
        modes = ('dungeon', 'dungeon') if dungeon else ('day', 'night')
        data = zone_data(prg, z)
        out.append((area, z, w[14], w[15], {k: pick_lists(prg, z, m, data) for k, m in zip(('day', 'night'), modes)},
                    data))
    return out


def _long(v):
    return v.to_bytes(3, 'little')


PICK_BLOCK = 8     # 낮·밤 묶음: 셋째 /256, 넷째 /256, 첫 목록 주소, 둘째 목록 주소, 구역 자료 주소


def ch3_code(merchant, picks, items, tables, coefs=(), at=CH3_CODE_AT):
    """(코드, 라벨). merchant 는 merchant_zones, picks 는 pick_rows, items 는 DQ5 물건 16칸(dq5_drop_items), tables 는
    fc_tables, coefs 는 own_coefs."""
    from dq4environmentrom import _Asm
    import dq4ch2event
    flag, bit = chapter3_flag()
    flag2, bit2 = FLAG_BASE + dq4ch2event.CHAPTER2[0], dq4ch2event.CHAPTER2[1]
    a = _Asm(at)
    bank = at >> 16
    # 23:E8EE 에서: M 8비트, X 16비트, DB 23, X = 구역 × 22
    a.label('encounter').b(0x08, 0x48, 0xDA)                                 # PHP PHA PHX
    a.b(0xAF, *_long(flag), 0x29, bit).rel(0xF0, 'encounter_out')            # LDA flag / AND / BEQ
    a.b(0xC2, 0x20, 0x8A, 0xA2, 0x00, 0x00)                                  # REP #$20 / TXA / LDX #0
    a.label('zone').long(0xDF, 'zones').rel(0xF0, 'found')                  # CMP zones,X / BEQ
    a.b(0xE8, 0xE8)                                                          # INX ×2
    a.b(0xE0, *(2 * len(merchant)).to_bytes(2, 'little')).rel(0x90, 'zone')  # CPX #n / BCC
    a.rel(0x80, 'encounter_16')
    a.label('found').b(0xA9, MERCHANT_RATE, 0x00, 0x22, *_long(RANDOM))    # rand(10)
    a.label('rolled10').b(0xC9, 0x00, 0x00).rel(0xF0, 'to_merchant')         # CMP #0 / BEQ
    a.label('encounter_16').b(0xE2, 0x20)
    a.label('encounter_out').b(0xFA, 0x68, 0x28)                             # PLX PLA PLP
    a.b(*NIGHT_ORIG, 0x6B)                                                   # LDY #$FFFF / STY $1001 / RTL
    a.label('to_merchant').word(0x4C, 'merchant')                            # JMP merchant
    # 23:E8FE 에서: M 8비트, X 16비트, DB 23, X = 구역 × 22. 원래 길은 스택 맨 위의 돌아갈 곳을 버리고 JML 로 잇는다
    row = 2 + 2 * PICK_BLOCK
    a.label('pick').b(0xDA, 0xC2, 0x20, 0x8A, 0xA2, 0x00, 0x00)              # PHX / REP #$20 / TXA / LDX #0
    a.label('pick_zone').long(0xDF, 'picks').rel(0xF0, 'pick_found')        # CMP picks,X / BEQ
    a.b(0x48, 0x8A, 0x18, 0x69, row, 0x00, 0xAA, 0x68)                      # PHA / TXA / CLC / ADC #row / TAX / PLA
    a.b(0xE0, *(row * len(picks)).to_bytes(2, 'little')).rel(0x90, 'pick_zone')  # CPX #n / BCC
    a.b(0xA9, 0xFF, 0xFF, 0x8F, *_long(PICK), 0xE2, 0x20)                   # PICK = FFFF / SEP #$20
    a.b(0xFA, 0x68, 0x68, 0x68, *PICK_ORIG, 0x5C, *_long(FIRST_LOOP))        # PLX / 버림 / 원래 명령 / JML 23:E904
    a.label('pick_found').b(0x8A, 0x18).word(0x69, 'picks', 2)              # TXA / CLC / ADC #picks+2
    a.b(0x22, *_long(IS_NIGHT)).rel(0x90, 'pick_mode')                       # JSL 21:8000 / BCC(낮)
    a.b(0x18, 0x69, PICK_BLOCK, 0x00)                                        # CLC / ADC #묶음(밤)
    a.label('pick_mode').b(0x8F, *_long(PICK), 0xAA)                         # STA PICK / TAX
    a.b(0xBF, 0x02, 0x00, bank, 0xAA, 0xE2, 0x20)                           # LDA 첫 목록 / TAX / SEP #$20
    a.word(0x20, 'pickl').rel(0xB0, 'pick_slot')                            # JSR pickl / BCS
    a.label('pick_none').b(0xFA, 0x68, 0x68, 0x68, 0x5C, *_long(NO_ENCOUNTER))
    # FC 18:$9E0D 처럼 고른 FC 칸으로 무리(7E:1001~ 몬스터, 1005~ 마릿수)를 짓고 23:EA40(PLB PLP SEC RTL)으로 끝낸다.
    # DP $00~$0F 는 23:E7C2 가 덮어쓰는 자리: $04 칸, $06 돌아가며 더할 무리, $08 장(k), $0A 구역 자료, $0C 무리 수,
    # $0E 마릿수 합, $0F 넣을 마릿수(16비트로 읽는 칸은 위 바이트를 0 으로 둔다)
    a.label('pick_slot').b(0x85, 0x04, 0x64, 0x05, 0x64, 0x07, 0x64, 0x09, 0x64, 0x0C, 0x64, 0x0D)
    a.b(0x9C, 0x09, 0x10, 0x9C, 0x0A, 0x10, 0x9C, 0x0B, 0x10)               # 줄 번호 $1009~$100B = 0
    a.b(0xC2, 0x20, 0xAF, *_long(PICK), 0xAA, 0xBF, 0x06, 0x00, bank, 0x85, 0x0A, 0xE2, 0x20)  # $0A = 구역 자료
    a.b(0x64, 0x08, 0xAF, *_long(flag2), 0x29, bit2).rel(0xF0, 'k_ch3').b(0xA9, 0x01, 0x85, 0x08)
    a.label('k_ch3').b(0xAF, *_long(flag), 0x29, bit).rel(0xF0, 'k_done').b(0xA9, 0x02, 0x85, 0x08)
    a.label('k_done').b(0xA5, 0x04, 0xC9, 0x05, 0xB0, 0x03).word(0x4C, 'f_group').b(0xD0, 0x03).word(0x4C, 'f_lead')
    a.b(0xC9, 0x0B, 0xB0, 0x03).word(0x4C, 'f_solo').b(0xD0, 0x03).word(0x4C, 'f_one').word(0x4C, 'f_form')
    # 칸 0~4: 그 칸과 둘째 무리, 바이트 14·15 확률로 셋째·넷째(18:$9EB9), 그 뒤 합 < $A464[k] 이고 난수 < $A46C[k] 인
    # 동안 첫 무리부터 돌아가며 한 마리씩(18:$9F04)
    a.label('f_group').word(0x20, 'mon').word(0x20, 'add1')
    a.word(0x20, 'pick2').rel(0x90, 'g_extra').word(0x20, 'mon').word(0x20, 'add1')
    for k in (0, 1):
        a.b(0xC2, 0x20, 0xAF, *_long(PICK), 0xAA, 0xE2, 0x20).word(0x20, 'rnd')
        a.b(0xDF, k, 0x00, bank).rel(0xB0, 'g_extra')
        a.word(0x20, 'pick2').rel(0x90, 'g_extra').word(0x20, 'mon').word(0x20, 'add1')
    a.label('g_extra').b(0xA5, 0x0C, 0x85, 0x0E, 0x64, 0x06)
    a.label('g_loop').b(0xA6, 0x08, 0xA5, 0x0E).long(0xDF, 'extra_max').rel(0xB0, 'f_done')
    a.word(0x20, 'rnd').b(0xA6, 0x08).long(0xDF, 'extra_p').rel(0xB0, 'f_done')
    a.b(0xA5, 0x06, 0xC5, 0x0C).rel(0x90, 'g_inc').b(0x64, 0x06)
    a.label('g_inc').b(0xA6, 0x06, 0xFE, 0x05, 0x10, 0xE6, 0x06, 0xE6, 0x0E).rel(0x80, 'g_loop')
    # 칸 5: 그 칸 한 마리와 둘째 무리 3 + rand(5)(18:$9F5D)
    a.label('f_lead').word(0x20, 'mon').word(0x20, 'add1')
    a.word(0x20, 'pick2').rel(0x90, 'f_done').word(0x20, 'mon').b(0x48, 0xA9, 0x05).word(0x20, 'randn')
    a.b(0x18, 0x69, 0x03, 0x85, 0x0F, 0x68).word(0x20, 'add').rel(0x80, 'f_done')
    # 칸 6~10: 부호 c 로 $A335[c] + rand($A32D[c])(18:$9E7B). 부호는 구역 자료 +14~+18
    a.label('f_solo').word(0x20, 'mon').b(0x48, 0xA5, 0x04, 0x18, 0x69, 14 - 6).word(0x20, 'mon')
    a.b(0xC2, 0x20, 0x29, 0xFF, 0x00, 0xAA, 0xE2, 0x20).long(0xBF, 'solo_cnt').word(0x20, 'randn')
    a.b(0x18).long(0x7F, 'solo_add').b(0x85, 0x0F, 0x68).word(0x20, 'add').rel(0x80, 'f_done')
    # 칸 11: 한 마리(18:$9E70)
    a.label('f_one').word(0x20, 'mon').word(0x20, 'add1')
    a.label('f_done').b(0xFA, 0x68, 0x68, 0x68, 0x5C, *_long(FORMED))
    # 칸 12·13: 고정 편성 [몬스터, 바탕, 폭] 넷. 몬스터가 FF 인 무리도 마릿수를 굴린다(18:$9E2D)
    a.label('f_form').b(0x38, 0xE9, 12, 0x0A, 0x18, 0x69, 19, 0xC2, 0x20, 0x29, 0xFF, 0x00, 0x18, 0x65, 0x0A, 0xAA)
    a.b(0xBF, 0x00, 0x00, bank, 0xAA, 0xE2, 0x20, 0xA9, 0x04, 0x85, 0x06)
    a.label('m_loop').b(0xDA, 0xBF, 0x02, 0x00, bank).word(0x20, 'randn').b(0xFA, 0x18, 0x7F, 0x01, 0x00, bank)
    a.b(0x85, 0x0F, 0xBF, 0x00, 0x00, bank, 0xC9, 0xFF).rel(0xF0, 'm_next').b(0xDA).word(0x20, 'add').b(0xFA)
    a.label('m_next').b(0xE8, 0xE8, 0xE8, 0xC6, 0x06).rel(0xD0, 'm_loop').rel(0x80, 'f_done')
    # A = 구역 자료의 칸 → 그 바이트
    a.label('mon').b(0xC2, 0x20, 0x29, 0xFF, 0x00, 0x18, 0x65, 0x0A, 0xAA, 0xE2, 0x20, 0xBF, 0x00, 0x00, bank, 0x60)
    # 무리 하나: A = 몬스터, $0F = 마릿수(add1 은 1)
    a.label('add1').b(0x48, 0xA9, 0x01, 0x85, 0x0F, 0x68)
    a.label('add').b(0xA6, 0x0C, 0x9D, 0x01, 0x10, 0xA5, 0x0F, 0x9D, 0x05, 0x10, 0xE6, 0x0C, 0x60)
    # 둘째 무리부터의 칸(A, SEC). 없으면 CLC
    a.label('pick2').b(0xC2, 0x20, 0xAF, *_long(PICK), 0xAA, 0xBF, 0x04, 0x00, bank, 0xAA, 0xE2, 0x20)
    a.word(0x4C, 'pickl')
    # rand(A) = A × 난수 >> 8(FC 10:$A1F6)
    a.label('randn').b(0x48).word(0x20, 'rnd').b(0xEB, 0x68, 0x8D, 0x02, 0x42, 0xEB, 0x8D, 0x03, 0x42)
    a.b(0xEA, 0xEA, 0xEA, 0xEA, 0xAD, 0x17, 0x42, 0x60)
    # 목록 X([개수][칸 무게]…)에서 FC 18:$9DDE 로 고른 칸(A, SEC). DP $00~$03 은 원래 고르기도 덮어쓰는 자리
    a.label('pickl').b(0xBF, 0x00, 0x00, bank).rel(0xF0, 'pickl_none')     # LDA 개수 / BEQ
    a.b(0x85, 0x03, 0x64, 0x00, 0xDA)                                        # STA $03 / STZ $00 / PHX
    a.label('pickl_sum').b(0xE8, 0xE8, 0xBF, 0x00, 0x00, bank, 0x18, 0x65, 0x00, 0x85, 0x00, 0xC6, 0x03)
    a.rel(0xD0, 'pickl_sum')                                                 # $00 = S
    a.b(0xFA).word(0x20, 'rnd').b(0x85, 0x01)                               # PLX / $01 = 난수
    a.b(0xA5, 0x00, 0xC9, 0xFF).rel(0xF0, 'pickl_raw')                      # S = FF 면 난수 그대로
    a.b(0x8D, 0x02, 0x42, 0xA5, 0x01, 0x8D, 0x03, 0x42, 0xEA, 0xEA, 0xEA, 0xEA)  # S × 난수(4202·4203)
    a.b(0xAD, 0x17, 0x42, 0x85, 0x01)                                        # $01 = 위 바이트
    a.label('pickl_raw').b(0xBF, 0x00, 0x00, bank, 0x85, 0x03, 0x64, 0x02)  # $03 = 개수 / $02 = 누적
    a.label('pickl_walk').b(0xE8, 0xE8, 0xBF, 0x00, 0x00, bank, 0x18, 0x65, 0x02, 0x85, 0x02, 0xC5, 0x01)
    a.rel(0xB0, 'pickl_hit')                                                 # 누적 >= r
    a.b(0xC6, 0x03).rel(0xD0, 'pickl_walk')
    a.label('pickl_none').b(0x18, 0x60)                                      # CLC / RTS
    a.label('pickl_hit').b(0xCA, 0xBF, 0x00, 0x00, bank, 0x38, 0x60)        # DEX / LDA 칸 / SEC / RTS
    # 23:EAFD 그대로(JSR 이라 뱅크 23 밖에서 부르지 못해 옮김): A = 난수 바이트. DB 23 의 WRAM 거울로 읽고 쓴다
    a.label('rnd').b(0xC2, 0x20, 0xAD, *RNG_HIGH.to_bytes(2, 'little'), 0x48, 0xAD, *RNG_LOW.to_bytes(2, 'little'))
    a.b(0x0E, *RNG_LOW.to_bytes(2, 'little'), 0x2E, *RNG_HIGH.to_bytes(2, 'little'), 0x18)
    a.b(0x6D, *RNG_LOW.to_bytes(2, 'little'), 0x8D, *RNG_LOW.to_bytes(2, 'little'))
    a.b(0x68, 0x6D, *RNG_HIGH.to_bytes(2, 'little'), 0x8D, *RNG_HIGH.to_bytes(2, 'little'))
    a.b(0xAD, *RNG_LOW.to_bytes(2, 'little'), 0x18, 0x69, *RNG_ADD.to_bytes(2, 'little'))
    a.b(0x8D, *RNG_LOW.to_bytes(2, 'little'), 0xAD, *RNG_HIGH.to_bytes(2, 'little'), 0x69, 0x00, 0x00)
    a.b(0x8D, *RNG_HIGH.to_bytes(2, 'little'), 0xE2, 0x20, 0xAD, *RNG_HIGH.to_bytes(2, 'little'), 0x60)
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
    # 06:E462 에서(여관에서 깬 뒤, 06:E43A 안, A 8비트): 원래 LDA $BC / CMP #$01 은 그룹 01(DQ5 ラインハット 여관)이면
    # 01/00 (50,83)에 세우고, 아니면 00:C6D8 로 지금 맵을 실내로 다시 불러온다. 필드의 $BC 도 01 이고 C6D8 은 $BE 를 80
    # 으로 두어 필드에서 자면 01/00 그림이 그려졌다. 필드($BE bit7 꺼짐)면 낮밤 바꾸기(06:D905)의 필드 갈래 06:D98E(필드
    # 다시 그리기 01:A04B 와 밝히기)로 간다. D905 는 PHP / PHB 로 들어와 PLB / PLP / RTL 로 끝나므로 같은 꼴로 쌓고, RTL 은
    # 06:E47F 의 RTS 로 가 E43A 를 부른 JSR 로 돌아간다
    a.label('wake').b(0xAF, 0xBE, 0x00, 0x7E).rel(0x10, 'wake_field')         # LDA $BE / BPL
    a.b(0xAF, 0xBC, 0x00, 0x7E, 0xC9, 0x01, 0x6B)                            # LDA $BC / CMP #$01 / RTL
    back = WAKE_RTS - 1
    a.label('wake_field').b(0x68, 0x68, 0x68)                                 # 이 훅의 돌아갈 곳을 버림
    a.b(0xA9, WAKE_RTS >> 16, 0x48, 0xC2, 0x20, 0xA9, back & 0xFF, back >> 8 & 0xFF, 0x48, 0xE2, 0x20)
    a.b(0x08, 0x8B, 0xA9, WAKE_RTS >> 16, 0x48, 0xAB, 0xE2, 0x30)            # PHP PHB / DB 06 / SEP #$30
    a.b(0x5C, *_long(FIELD_REDRAW))                                           # JML 06:D98E
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
    # 메시지의 몬스터 이름은 칸 0(첫 무리)의 것. BRK 는 놓인 뱅크를 DB 로 두어(4E 면 WRAM 대신 롬을 읽음) 이 뱅크에서 부르지 않는다
    a.label('hit').long(0xBF, 'items').b(0x85, 0x46, 0x64, 0x42)             # LDA items,X / STA $46 / STZ $42
    back = DROP_ITEM - 1
    a.b(0xC2, 0x20, 0xA9, back & 0xFF, back >> 8 & 0xFF, 0x83, 0x01, 0xE2, 0x20, 0x6B)  # 돌아갈 곳 / RTL
    # 26:832E 에서(M·X 8비트): FC 18:$A20E 처럼 r = rand(33) 하나로 r ≤ T0 이면 보통, r ≤ T1 이면 기습(bit0), 그 위는
    # 선제(bit1). 문턱 번호는 구역 레코드 +4 bit6-7 이 옮겨 온 $1000 아래 두 비트(record 의 flag_1000 = FC k)
    a.label('surprise_hook').b(0xAF, *_long(BATTLE_FLAGS), 0x29, 0x03, 0x0A, 0xAA, 0xA9, SURPRISE_RANGE)
    a.b(0x22, *_long(RAND8)).long(0xDF, 'surprise', 0).rel(0x90, 's_normal').rel(0xF0, 's_normal')
    a.long(0xDF, 'surprise', 1).rel(0x90, 's_ambush').rel(0xF0, 's_ambush').b(0xA9, 0x02).rel(0x80, 's_set')
    a.label('s_normal').b(0xA9, 0x00).rel(0x80, 's_set')
    a.label('s_ambush').b(0xA9, 0x01)
    a.label('s_set').b(0x85, 0x71, 0xAF, *_long(BATTLE_FLAGS), 0x29, 0xFC, 0x05, 0x71, 0x8F, *_long(BATTLE_FLAGS))
    a.b(0x5C, *_long(SURPRISE_DONE))
    # 23:E892 에서(M 8비트, X 16비트, DB 23, X = 구역 × 22): coefs 의 구역이면 그 계수, 아니면 원래처럼 표 23:EA44[$01]
    a.label('coef')
    for zone, coef in coefs:
        a.b(0xE0, *(zone * CH3_ZONE_RECORD).to_bytes(2, 'little')).rel(0xD0, f'coef_not{zone}')  # CPX #구역×22 / BNE
        a.b(0xA9, 0x00, 0xEB, 0xA9, coef, 0x6B)                                 # LDA #0 / XBA / LDA #계수 / RTL
        a.label(f'coef_not{zone}')
    a.b(*COEF_ORIG, 0x6B)
    a.label('zones')
    for zone in merchant:
        a.b(*(zone * CH3_ZONE_RECORD).to_bytes(2, 'little'))
    a.label('thresholds')
    a.b(*(t for t, _ in items))
    a.label('items')
    a.b(*(m for _, m in items))
    # 구역마다 [구역 × 22][낮 묶음][밤 묶음], 묶음은 [셋째][넷째][첫 목록][둘째 목록][구역 자료]. 같은 목록은 한 벌
    lists = {}
    for *_, modes, _ in picks:
        for first, second in modes.values():
            for entries in (first, second):
                lists.setdefault(tuple(entries), f'list{len(lists)}')
    a.label('picks')
    for n, (zone, _, third, fourth, modes, _) in enumerate(picks):
        a.b(*(zone * CH3_ZONE_RECORD).to_bytes(2, 'little'))
        for mode in ('day', 'night'):
            first, second = modes[mode]
            a.b(third, fourth).word(None, lists[tuple(first)]).word(None, lists[tuple(second)]).word(None, f'zd{n}')
    for entries, name in lists.items():
        a.label(name).b(len(entries), *(v for pair in entries for v in pair))
    # 구역 자료: FC 칸 0~13 의 DQ5 몬스터, 칸 6~10 의 마릿수 부호, 칸 12·13 고정 편성 [몬스터, 바탕, 폭] 넷의 주소
    for n, (*_, data) in enumerate(picks):
        codes = [data['codes'] >> 3 * k & 7 for k in range(5)]
        a.label(f'zd{n}').b(*data['monsters'], *codes)
        for slot in (12, 13):
            a.word(None, f'zf{n}_{slot}') if slot in data['formations'] else a.b(0, 0)
        for slot, members in data['formations'].items():
            a.label(f'zf{n}_{slot}').b(*(v for member in members for v in member))
    for name, values in tables.items():
        a.label(name).b(*values)
    return a.assemble()


def ch3_inputs(prg, dq5, report):
    """ch3_code 의 (merchant, picks, items, tables, coefs)."""
    table = fc_drop_table(prg)
    return (merchant_zones(report), pick_rows(prg, report), list(zip((t for t, _ in table), dq5_drop_items(prg, dq5))),
            fc_tables(prg), own_coefs(prg, report))


def ch3_labels(prg, dq5, report, at=CH3_CODE_AT):
    """ch3_writes 가 쓰는 코드의 라벨(검사가 훅 안 자리를 고를 때)."""
    return ch3_code(*ch3_inputs(prg, dq5, report), at)[1]


def no_merchant_patch(prg, dq5, report):
    """떠돌이 상인 갈래(rand(10) = 0 의 BEQ)를 NOP 로 덮는 ROMPATCH(파일 오프셋=바이트): 조우·무리를 보는 검사가 상인
    대화에 걷기가 멈추지 않게."""
    at = ch3_labels(prg, dq5, report)['rolled10'] + 3
    return f'{_lorom(at):X}=EAEA'


def ch3_writes(prg, dq5, report, at=CH3_CODE_AT):
    """dq5patch/1 쓰기: 코드·표와 훅 여섯 곳. report 는 docs 의 보고."""
    blob, labels = ch3_code(*ch3_inputs(prg, dq5, report), at)
    if at + len(blob) > CH3_CODE_END:
        raise ValueError(f'3장 몬스터 코드 {len(blob)}바이트가 {at:06X}~{CH3_CODE_END - 1:06X} 를 넘음')

    def put(addr, new, orig, note):
        return {'at': f'{addr >> 16:02X}:{addr & 0xFFFF:04X}', 'hex': new.hex(' ').upper(), 'orig': orig.hex(' ').upper(),
                'note': note}

    def jsl(label):
        return bytes((0x22, *_long(labels[label])))
    out = [{'at': f'{at >> 16:02X}:{at & 0xFFFF:04X}', 'hex': blob.hex(' ').upper(),
            'note': 'FC 무리 고르기 표, 3장 떠돌이 상인과 3장 전용 전투 뒤 물건'},
           put(NIGHT_SITE, jsl('encounter') + b'\xEA\xEA', NIGHT_ORIG, '3장 필드 조우의 1/10 은 떠돌이 상인'),
           put(PICK_SITE, jsl('pick') + b'\xEA\xEA', PICK_ORIG, '무리 짓기를 FC 18:$9D6B~$9F78 대로'),
]
    out.append(put(DROP_SITE, jsl('drop') + bytes((0xD0, 0x04, 0xEA)), DROP_ORIG, '3장이면 전투 뒤 물건을 FC 3장 표로'))
    out.append(put(SURPRISE_SITE, bytes((0x5C, *_long(labels['surprise_hook']), 0xEA)), SURPRISE_ORIG,
                   '걸음 전투의 기습·선제를 FC 문턱으로'))
    out.append(put(WAKE_SITE, jsl('wake'), WAKE_ORIG, '필드 여관(떠돌이 상인)에서 깨면 그룹 01 갈래로 가지 않음'))
    out.append(put(COEF_SITE, jsl('coef') + bytes((0xEA,) * (len(COEF_ORIG) - 4)), COEF_ORIG,
                   '계수 표에 맞는 값이 없는 기본 조우율의 구역은 FC 에 맞춘 계수로(own_coefs)'))
    out.append(put(LAST_KILL_SITE, LAST_KILL, LAST_KILL_ORIG, '떨어뜨림 후보는 마지막으로 쓰러뜨린 종류(FC)'))
    for site, orig, new in DROP_SPECIES:
        out.append(put(site, new, orig, '떨어뜨림 종류는 마지막으로 쓰러뜨린 종류 $111C(FC, 도망은 바꾸지 않음)'))
    msg, msg_labels = drop_msg_code()
    tail = dq5[_lorom(DROP_MSG_SITE + 3):_lorom(DROP_MSG_NEXT)]
    if tail != DROP_MSG_TAIL or dq5[_lorom(DROP_MSG_NEXT):_lorom(DROP_MSG_NEXT) + 2] != bytes((0x00, 0x16)):
        raise ValueError(f'25:89C2~89CB 가 {tail.hex()}')
    out.append({'at': f'{DROP_MSG_AT >> 16:02X}:{DROP_MSG_AT & 0xFFFF:04X}', 'hex': msg.hex(' ').upper(),
                'note': '떨어뜨림 메시지: 섞인 무리면 마물 무리(FC 01C8)'})
    out.append(put(DROP_MSG_SITE, bytes((0x5C, *_long(msg_labels['drop_msg']))), DROP_MSG_ORIG,
                   '떨어뜨림 메시지를 FC 처럼 무리 종류로'))
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
