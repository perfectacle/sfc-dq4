"""FC field encounter zones on DQ5 worlds 0-2: the DQ5 zone grids (dq5encounterwrite.py) and zone records
(dq5progresswrite.py) for the FC zones of fields 0, 1 and 3.

An FC zone map cell is 16x16 FC blocks ((Y >> 4) * 16 + (X >> 4), fc/dq4/docs/dq4-encounter-format.md) and a DQ5
grid cell is 32x32 field cells, also 16x16 blocks ((Y >> 5) * 17 + (X >> 5), 01:854F), so FC zone cell (c, r) is
DQ5 grid cell (c, r). Each FC zone takes one DQ5 zone that only the field grids use (zones), whose record is
rewritten in place with the FC zone's monsters through MONSTERS (record), and the four sea zones of 01:85D8 take
FC zone 00, the zone FC uses on the ship. The DQ5 terrain rates become FC's terrain factors (terrain_rates).
sfc/dq4/docs/dq4-field-format.md 「조우」.

  python sfc/dq4/tools/dq4fieldencounter.py -o work/encounter
"""

import argparse
import functools
import json
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
# original ROM).
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
    0x18: 0x0B,  # ~ あばれこまいぬ -> スカルサーペント
    0x19: 0x12,  # ~ ダックスビル -> まほうつかい
    0x1A: 0x12,  # ~ ひとくいそう -> まほうつかい
    0x1B: 0x1B,  # ~ つかいま -> がいこつへい
    0x1C: 0x12,  # ~ あばれうしどり -> まほうつかい
    0x1D: 0x12,  # ~ べビーマジシャン -> まほうつかい
    0x1E: 0x12,  # ~ リリパット -> まほうつかい
    0x20: 0x1F,  # ~ とさかへび -> わらいぐさ
    0x21: 0x12,  # ~ おおにわとり -> まほうつかい
    0x22: 0x12,  # ~ ピクシー -> まほうつかい
    0x23: 0x1B,  # ~ ヘルビートル -> がいこつへい
    0x24: 0x1F,  # ~ テベロ -> わらいぐさ
    0x25: 0x25,  # ~ おにこぞう -> ダークアイ
    0x26: 0x1F,  # ~ ラリホービートル -> わらいぐさ
    0x27: 0x1B,  # ~ メイジももんじゃ -> がいこつへい
    0x28: 0x1F,  # ~ サンドマスター -> わらいぐさ
    0x2C: 0x1F,  # ~ コドラ -> わらいぐさ
    0x2D: 0x1B,  # ~ ベロベロ -> がいこつへい
    0x2F: 0x25,  # ~ しびれだんびら -> ダークアイ
    0x31: 0x29,  # ~ ダークドリアード -> エビルアップル
    0x32: 0x25,  # ~ エビルハムスター -> ダークアイ
    0x34: 0x47,  # ~ くびながりゅう -> メタルライダー
    0x35: 0x47,  # ~ エビルアングラー -> メタルライダー
    0x38: 0x3F,  # ~ かまいたち -> インスペクター
    0x39: 0xC8,  # しびれくらげ
    0x3A: 0x47,  # ~ さつじんえい -> メタルライダー
    0x3B: 0x47,  # ~ とつげきうお -> メタルライダー
    0x3D: 0x29,  # ~ ひとつめピエロ -> エビルアップル
    0x3E: 0x3F,  # ~ プテラノドン -> インスペクター
    0x3F: 0x47,  # ~ トドマン -> メタルライダー
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
# DQ5 field grids (dq5encounterwrite field_grids, 01:A6D9): index -> ($1949 world, rows, the FC zone-map rows read
# there). World 0 picks its grid by $1948 and 01:854F does not clamp the row, so with $1948 = 0 rows 7-15 of
# grid 0 read rows 0-8 of grid 1: grid 1 holds FC rows 7-15 there and serves $1948 = 1 only from its row 9.
GRIDS = {0: (0, 7, list(range(0, 7))),
         1: (0, 17, list(range(7, 16)) + list(range(9, 16)) + [None]),
         2: (0, 17, list(range(0, 16)) + [None]),
         3: (1, 5, None), 4: (2, 4, None)}
GRID_WIDTH = 17
SEA_ZONE = 0x00
SEA_AREAS = (81, 82, 83, 84)   # 01:85D8: the ship's two rectangles take these four
# FC fields 1 and 3 have no zone map (18:$9C3F): field 1 is zone 35 above Y = 0C and 34 below, field 3 zone 36.
# A DQ5 grid row is 16 blocks, so field 1's first row takes 35.
FIELD1_TOP, FIELD1, FIELD3 = 0x35, 0x34, 0x36
RATE_COEF = 0x23EA44
# FC dungeons take terrain factor 0F on every tile (18:$9F9B) and DQ5 indoor maps rate 7 (01:8522). An FC step is
# a 16-pixel block and a DQ5 step one 8-pixel cell (00:82AB runs for each), and the two engines scale a step's
# chance by the steps since the last fight in different ways, so a dungeon zone takes the coefficient whose mean
# cells to a fight are nearest twice FC's mean steps (dungeon_rate_index).
FC_DUNGEON_TERRAIN, DQ5_INDOOR_RATE = 0x0F, 7
MEAN_STEPS = 4096
# DQ5 rate per terrain nibble (01:84CF's Y), day then night, 14 each. FC's chance per step is base x 16 x the
# terrain factor >> 8 and DQ5's coefficient x Y >> 6, so with Y = the FC factor and coefficient = 4 x base
# (rate_index) a DQ5 step has the FC chance. FC fights only on tiles below 8 ($9CB5).
TERRAIN_RATES = 0x23F1E0
TERRAINS = 14
FC_TERRAINS = 8


@functools.cache
def _fc(prg):
    import dq4encounter
    return dq4encounter


def fc_zones(prg):
    """FC zones of the zone map chapters 1, 2 and 4 use on field 0, and of fields 1 and 3."""
    _, rows = _fc(prg).zone_map(prg, 0)
    return sorted({v & 0x3F for row in rows for v in row} | {FIELD1_TOP, FIELD1, FIELD3})


def zones(prg, enc):
    """{FC zone: DQ5 zone}: the FC zones in order on the DQ5 zones only the field grids use (enc is the
    dq5encounterwrite dump of the original ROM), in order."""
    used = {a for m in enc["maps"] for a in m["areas"]}
    field = sorted({a for g in enc["field_grids"] for row in g["rows"] for a in row} - used - set(SEA_AREAS))
    fc = fc_zones(prg)
    if len(fc) > len(field):
        raise ValueError(f"{len(fc)} FC zones, {len(field)} field-only DQ5 zones")
    return dict(zip(fc, field))


def dungeon_zones(prg, enc, fc):
    """{FC dungeon zone: DQ5 zone}: the FC zones `fc` on the field-only DQ5 zones that zones() leaves, in order.
    The field grids written by grids() hold only zones()'s zones and the sea, so these are no longer read there."""
    used = {a for m in enc["maps"] for a in m["areas"]}
    field = sorted({a for g in enc["field_grids"] for row in g["rows"] for a in row} - used - set(SEA_AREAS))
    left = [a for a in field if a not in zones(prg, enc).values()]
    fc = sorted(set(fc))
    if len(fc) > len(left):
        raise ValueError(f"{len(fc)} FC dungeon zones, {len(left)} DQ5 zones left")
    return dict(zip(fc, left))


def grids(prg, assign):
    """dq5encounter/1 field_grids: every cell of the five grids from the FC zone maps."""
    _, fc_rows = _fc(prg).zone_map(prg, 0)
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
                row = [assign[v & 0x3F] for v in fc_rows[source[r]]] + [sea] * (GRID_WIDTH - 16)
            rows.append(row)
        out.append({"index": index, "rows": rows})
    return out


def rate_index(dq5, base):
    """Index of the DQ5 rate coefficient (23:EA44) nearest 4 x FC's base rate: on the field, where Y is the FC
    terrain factor (TERRAIN_RATES), a DQ5 step then has the chance of an FC step."""
    coefs = dq5[_lorom(RATE_COEF):_lorom(RATE_COEF) + 8]
    return min(range(8), key=lambda i: (abs(coefs[i] - 4 * base), i))


def _mean(chances):
    """Mean steps to a fight for the chances (out of 256) of steps 1, 2, ...."""
    mean, left = 0.0, 1.0
    for k, p in enumerate(chances, 1):
        mean += k * left * min(p, 256) / 256
        left *= 1 - min(p, 256) / 256
    return mean


def fc_dungeon_steps(prg, base):
    """FC's mean steps to a fight in a dungeon zone of base rate `base`: base x the step factor (18:$A33D[$6E42],
    the first three steps after a fight) x 0F >> 8 (18:$9CCC)."""
    enc = _fc(prg)
    after = [enc.rd(prg, enc.AFTER_BATTLE + n) for n in range(3)]
    return _mean(base * (after[k] if k < 3 else 0x10) * FC_DUNGEON_TERRAIN >> 8 for k in range(MEAN_STEPS))


def dq5_steps(coef, rate):
    """DQ5's mean steps to a fight for coefficient `coef` and rate Y (23:E7C2): with s = $1A9A, the steps since the
    last fight counting this one, and n = 256 / Y, Y is 0 below 3 and >> 6, >> 4, >> 2, >> 1 below 5, 7, 9, 11, then
    (Y >> 1) + (Y >> 2) below n, Y + (Y >> 1) below 2n and 4Y after, at most FF; the chance is coef x Y >> 6
    (23:E898)."""
    n = 0x100 // rate

    def y(s):
        if s < n:
            for top, shift in ((3, 8), (5, 6), (7, 4), (9, 2), (11, 1)):
                if s < top:
                    return rate >> shift
            return (rate >> 1) + (rate >> 2)
        return min(0xFF, rate + (rate >> 1) if s < 2 * n else 4 * rate)
    return _mean(coef * y(min(s, 0xFF)) >> 6 for s in range(1, MEAN_STEPS + 1))


def dungeon_rate_index(prg, dq5, base):
    """Index of the DQ5 rate coefficient whose mean cells to a fight at the indoor rate is nearest two cells per FC
    step of fc_dungeon_steps."""
    coefs = dq5[_lorom(RATE_COEF):_lorom(RATE_COEF) + 8]
    want = 2 * fc_dungeon_steps(prg, base)
    return min(range(8), key=lambda i: (abs(dq5_steps(coefs[i], DQ5_INDOOR_RATE) - want), i))


def terrain_rates(prg, dq5):
    """dq5patch/1 write of the DQ5 day and night terrain rates: each terrain nibble of the DQ5 blocks the FC kinds
    0-7 borrow (dq4fieldport.BLOCKS) takes the FC day and night factor of that kind; the nibbles only other kinds
    borrow are 0. A nibble shared by kinds below and above 8 keeps the factor of the kind below 8."""
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
            new[half * TERRAINS + t] = enc.rd(prg, table + fc[0]) if fc else 0
    return {"at": f"{TERRAIN_RATES >> 16:02X}:{TERRAIN_RATES & 0xFFFF:04X}", "hex": new.hex(" ").upper(),
            "orig": old.hex(" ").upper(), "note": "지형별 조우율(낮·밤)을 FC 지형 배수로"}


def _lorom(addr):
    return (addr >> 16 & 0x7F) * 0x8000 + (addr & 0x7FFF)


def dungeon_fixed(prg, fc):
    """{FC formation: DQ5 fixed group} of the slot-12 formations of the FC dungeon zones `fc`, in formation order."""
    enc = _fc(prg)
    found = sorted({enc.zone(prg, z)["slots"][FORMATION_SLOT] for z in set(fc)} - {0xFF})
    if len(found) > FIXED_GROUPS:
        raise ValueError(f"{len(found)} FC formations, {FIXED_GROUPS} DQ5 fixed groups")
    return {f: k for k, f in enumerate(found)}


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


def record(prg, dq5, z, dungeon=None):
    """dq5progress/1 encounter fields of FC zone z (without its index) and the FC slots left out. `dungeon` is
    dungeon_fixed for a dungeon zone (None on the field): the rate is dungeon_rate_index, and slot 12 becomes DQ5
    slot 10."""
    enc = _fc(prg)
    rec = enc.zone(prg, z)
    s, w = rec["slots"], enc.weights(prg, rec["row"])
    code16 = w[16] | w[17] << 8
    used = [i for i in (*GROUP_SLOTS, *SOLO_SLOTS, *ONE_SLOTS) if s[i] != 0xFF]
    top = max(w[i] for i in used)

    def weight(i):
        return max(1, round(DQ5_WEIGHT * w[i] / top)) if w[i] else 0

    slots = {k: {"index": k, "weight": 0, "count_code": 0, "monster": 0} for k in range(10)}
    for i in GROUP_SLOTS:
        if s[i] != 0xFF:
            slots[i].update(weight=weight(i), count_code=GROUP_COUNT, monster=MONSTERS[s[i]])
    for i in SOLO_SLOTS:
        if s[i] != 0xFF:
            slots[i - 1].update(weight=weight(i), count_code=code16 >> 3 * (i - 6) & 7, monster=MONSTERS[s[i]])
    dropped = [i for i in (12, 13) if s[i] != 0xFF]
    fixed_slot = {"weight": 0, "group": 0}
    if dungeon is not None and s[FORMATION_SLOT] != 0xFF and w[FORMATION_SLOT]:
        fixed_slot = {"weight": weight(FORMATION_SLOT), "group": dungeon[s[FORMATION_SLOT]]}
        dropped.remove(FORMATION_SLOT)
    for i in ONE_SLOTS:
        if s[i] == 0xFF:
            continue
        free = [k for k in DQ5_SOLO if not slots[k]["weight"]]
        if not free or not w[i]:
            dropped.append(i)
            continue
        slots[free[0]].update(weight=weight(i), count_code=0, monster=MONSTERS[s[i]])
    return {"level": rec["b1"], "slots": list(slots.values()), "fixed": fixed_slot,
            "species_weights": [3, 1 if w[14] else 0, 1 if w[15] else 0], "rate_index": rate_index(dq5, rec["rate"]) if dungeon is None else dungeon_rate_index(prg, dq5, rec["rate"]),
            "flag_1000": 0, "flag_1010": False, "fixed_night_only": False}, dropped


def docs(prg, dq5, enc, dungeon=()):
    """(dq5progress/1, dq5encounter/1, report) for the FC field zones and the FC dungeon zones `dungeon`
    (dungeon_zones). The terrain rates are terrain_rates."""
    assign = zones(prg, enc)
    fixed = dungeon_fixed(prg, dungeon)
    groups = fixed_groups(prg, dq5, fixed)
    records, report = [], {}
    for kind, found in (("field", assign), ("dungeon", dungeon_zones(prg, enc, dungeon))):
        for fc, area in found.items():
            fields, dropped = record(prg, dq5, fc, fixed if kind == "dungeon" else None)
            records.append({"index": area, **fields})
            monsters = {sl["monster"] for sl in fields["slots"] if sl["weight"]}
            if fields["fixed"]["weight"]:
                monsters |= {m["monster"] for m in groups[fields["fixed"]["group"]]["members"]}
            report[f"{fc:02X}"] = {"zone": area, "kind": kind, "level": fields["level"], "dropped_slots": dropped,
                                   "rate_index": fields["rate_index"], "fixed": fields["fixed"],
                                   "monsters": sorted(monsters)}
    sea, _ = record(prg, dq5, SEA_ZONE)
    records += [{"index": area, **sea} for area in SEA_AREAS]
    return ({"format": "dq5progress/1", "encounters": records},
            {"format": "dq5encounter/1", "field_grids": grids(prg, assign), "fixed_groups": groups}, report)


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
