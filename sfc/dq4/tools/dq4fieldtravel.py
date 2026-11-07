"""ルーラ destinations and the ship of the FC towns ported as DQ5 groups (dq4groupbuild.LINKS).

The DQ5 ルーラ list (25:85D5, 22 groups; its names are name table 0B by slot, its visited flags 7E:2030~ by
slot) takes the FC towns in FC destination order (FC_GROUPS). 1E:E545 lands the party on (X, Y+1) of the group's
first entrance row, so the group's aux entrance rows start with the cell above the FC destination block
(landing_rows): the party lands on that block's top-left cell. After landing, 1E:E4AE moves an owned ship to the
landing cell plus the slot's (dx, dy) of SHIP_OFFSETS (slots 0-12), which takes the FC destination's ship block.
sfc/dq4/docs/dq4-field-format.md 「ルーラ」·「배」.

  python sfc/dq4/tools/dq4fieldtravel.py -o work/travel
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

RULER_LIST, RULER_COUNT = 0x2585D5, 22
NAME_TABLE = 11
# 1E:E498 picks one of the two signed (dx, dy) tables by a story flag (BRK 0B) and reads it with DB = 23; both
# get the same offsets.
SHIP_OFFSETS = (0x23E41E, 0x23E438)
SHIP_SLOTS = 13          # 1E:E4B2 CPX #$0D
# FC ルーラ destinations (fc/dq4/tools/dq4field.py places) by FC group, in FC destination order. Each must be the
# first FC group of its DQ5 group: the landing takes the DQ5 group's first entrance row. テンペ (0E) and フレノール
# (0F) share DQ5 group 3D with サントハイム, so they have no slot of their own.
FC_GROUPS = (0x00, 0x01, 0x02, 0x04, 0x05, 0x06, 0x11, 0x12, 0x14, 0x15, 0x16, 0x17)
# Slots after FC_GROUPS for FC groups that share their DQ5 group with another (テンペ·フレノール in 3D, the bazaar and
# サラン in 45): (FC group, name, listed). The engine ties a slot to its group alone, so the hook (hook_writes) ties
# these slots to their maps. サラン is no FC ルーラ destination but has an FC church to come back to, and DQ5 keeps the
# place to continue as a slot (7E:2033), so it takes a slot whose visited bit is never set. They follow the FC slots
# rather than going between them in FC order: a slot is a bit of 7E:2030~ and the number in 7E:2033 of saved games.
EXTRA = ((0x0E, "テンペ", True), (0x0F, "フレノール", True), (0x0C, "さばくのバザー", True), (0x13, "サラン", False))
VISITED_SLOTS = 17       # 06:D3F0 LDX #$10: map entry sets the visited bit of the first 17 slots only
SEA = 0x83

# Hooks of the extra slots (hook_writes). Each site keeps its original bytes in "orig" for the build to check.
HOOK_AT = 0x5BBC00
LAND_SITE, LAND_ORIG, LAND_BACK, LAND_DONE = 0x1EE552, "AA AF 01 80 01", 0x1EE557, 0x1EE5C1
VISIT_SITE, VISIT_ORIG, IN_LIST = 0x018EB2, "22 ED D3 06", 0x06D3ED
SLOT_OF = 0x23E452       # group A → its first slot X (from X)
CHIMERA_SITE, SHIP_SITE, SLOT_OF_ORIG = 0x118CBF, 0x1EE4AE, "22 52 E4 23"
SAVE_SITE, SAVE_ORIG, SAVE_BACK, SAVE_DONE = 0x258365, "A5 BC A2 00", 0x258369, 0x258383
WIPE_SITE, WIPE_ORIG, WIPE_BACK, WIPE_DONE = 0x0189A3, "29 7F AA BF D5 85 25", 0x0189AA, 0x0189E0
CONTINUE_SITE, CONTINUE_ORIG, CONTINUE_BACK, CONTINUE_DONE = 0x2582A9, "AA AF 01 80 01", 0x2582AE, 0x2582DB
START_TABLE = 0x258621   # 다시 시작 자리 표: 6바이트 [BC][BD][X][Y][층][198E], FF 로 끝
# 전멸 뒤 자리: DQ5 는 01:899C 가 고른 그룹(마지막에 들어간 마을 $195E)의 첫 칸으로 가지만, FC·NDS 는 마지막으로 저장한
# 교회로 간다(FC $6290). 그래서 그룹을 칸으로 바꾸는 01:899F 를 저장한 칸(7E:2033)을 돌려주는 훅으로 바꾼다. 아직 저장하지
# 않은 기록(새 게임이 쓴 16)은 FC 1장 시작 귀환 자리(バトランド 교회)의 칸이다.
RESTART_SITE, RESTART_ORIG, PLACE_SAVED, UNSAVED = 0x01899F, "22 46 80 25", 0x7E2033, 0x16
FIRST_CHURCH_FC = 0x02
# 2장 시작의 FC 귀환 자리(1E:$A75E[1] = 10, サラン 교회). 1장 끝에서 2장으로 넘길 때 7E:2033 에 둔다(chapter_slot).
CHAPTER2_CHURCH_FC = 0x13
# 7E:2193 is the last town entered, read only by キメラのつばさ (11:8CBB). An extra slot's town stores 80 | slot there,
# as no group number has bit7.
LAST_TOWN, VISITED, SLOT_MARK = 0x7E2193, 0x7E2030, 0x80
# FC return places (1E:$A76D, 22 records of FC group, FC map, x, y, end byte): the church each saved game goes back to.
FC_RETURNS, FC_RETURN_COUNT = (0x1E, 0xA76D), 22


def lorom(addr):
    return (addr >> 16 & 0x7F) * 0x8000 + (addr & 0x7FFF)


def cpu(addr):
    return f"{addr >> 16:02X}:{addr & 0xFFFF:04X}"


@functools.cache
def _codes(dq5):
    """DQ5 name byte(s) of each kana: single bytes first, then 84 (dakuten) or 83 (handakuten) + key."""
    import dq5text
    from dq5map import Rom
    rom = Rom(dq5)
    out = {}
    for b in range(0x02, 0x83):
        out.setdefault(dq5text.text([rom.u16(dq5text.STRING_CODES + b * 2)]), bytes([b]))
    for k in range(0x28 + 11):
        prefix = 0x84 if k < 0x28 else 0x83
        out.setdefault(dq5text.text([rom.u16(dq5text.MARK_CODES + k * 2)]),
                       bytes([prefix, rom.u8(dq5text.MARK_KEYS + k)]))
    return out


def name_bytes(dq5, name):
    """DQ5 name-table bytes of a kana name. FC text writes some katakana with the hiragana glyph (り), so a kana
    with no code is tried in the other script."""
    codes = _codes(dq5)
    out = b""
    for c in name:
        other = chr(ord(c) + 0x60) if "ぁ" <= c <= "ゖ" else chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c
        if c not in codes and other not in codes:
            raise ValueError(f"{name}: no DQ5 code for {c!r}")
        out += codes.get(c, codes.get(other))
    return out


def destinations(prg, links, doors):
    """[{slot, fc, group, name, land, row, ship}] of FC_GROUPS: the DQ5 group whose first part is the FC group,
    the landing cell (top-left cell of the FC destination block), the entrance cell above it that must lead the
    group's entrance rows, and the DQ5 cell of the FC ship block (None when the record has none).
    doors[FC group] = (DQ5 entrance cells, leave cell) as dq4groupbuild.doors."""
    import dq4field
    import dq4fieldport
    _, props = dq4fieldport.fc_field(prg)
    records = {e["group"]: e for e in dq4field.places(prg) if e["kind"] == "field" and e["field"] == 0}
    first = {parts[0]["fc"]: group for group, parts in links.items()}
    out = []
    for slot, fc in enumerate(FC_GROUPS):
        if fc not in first:
            raise ValueError(f"FC group {fc:02X} is not the first part of a LINKS group")
        e = records[fc]
        land = (2 * e["x"], 2 * e["y"])
        row = (land[0], land[1] - 1)
        if row not in doors[fc][0]:
            raise ValueError(f"FC group {fc:02X}: {row} above the landing {land} is not one of its entrance cells")
        out.append({"slot": slot, "fc": fc, "group": first[fc], "name": e["name"], "land": land, "row": row,
                    "ship": ship_cell(props, e["ship"], land)})
    return out


def ship_cell(props, block, land):
    """DQ5 cell of the FC ship block next to a walkable FC block, so the party can walk onto it: one with land
    above or below first (walking onto the ship from its left did not board it in the game), then nearest `land`.
    None for an FC record without a ship (00 00)."""
    # 오른쪽 칸이 땅인 배 칸에서는 배가 위아래로 나아가지 못했다(ハバリア (131,309)·コーミズ (71,366), 같은 블록의
    # 왼쪽 칸 (130,309) 은 위로 나아감). 그래서 오른쪽 칸도 바다인 칸을 먼저 고른다.
    sx, sy = block
    if (sx, sy) == (0, 0):
        return None
    if props(sx, sy) != SEA:
        raise ValueError(f"FC ship block ({sx:02X},{sy:02X}) is not sea")
    ok = []
    for cx, cy in ((2 * sx + dx, 2 * sy + dy) for dy in (0, 1) for dx in (0, 1)):
        sides = [n for n in ((0, -1), (0, 1), (1, 0), (-1, 0)) if not props((cx + n[0]) >> 1, (cy + n[1]) >> 1) & 0x80]
        if sides:
            ok.append((props((cx + 1) >> 1, cy >> 1) != SEA, sides[0][0] != 0, abs(cx - land[0]) + abs(cy - land[1]),
                       cx, cy))
    if not ok:
        raise ValueError(f"FC ship block ({sx:02X},{sy:02X}) has no cell next to land")
    return min(ok)[3:]


def landing_rows(rows, dests):
    """Aux entrance rows ({group, x, y}) with each destination's row first among its group's rows."""
    want = {(d["group"], *d["row"]) for d in dests}
    return sorted(rows, key=lambda r: (r["group"], r["x"], r["y"]) not in want)


def slot_of_fc(fc):
    """ルーラ slot of an FC group: its place in FC_GROUPS, then EXTRA."""
    order = [*FC_GROUPS, *(e[0] for e in EXTRA)]
    if fc not in order:
        raise ValueError(f"FC group {fc:02X} has no ルーラ slot")
    return order.index(fc)


def chapter_slot_code():
    """M8 code that puts chapter 2's FC return place (CHAPTER2_CHURCH_FC) in 7E:2033 by day: where a wipe-out goes back
    to, and continuing, until the party saves."""
    return bytes((0xA9, slot_of_fc(CHAPTER2_CHURCH_FC), 0x8F, *PLACE_SAVED.to_bytes(3, "little")))


def fc_returns(prg):
    """{FC group: (FC map, x, y)} of the first FC return place (1E:$A76D) of each FC group."""
    base = FC_RETURNS[0] * 0x4000 + FC_RETURNS[1] - 0x8000
    out = {}
    for i in range(FC_RETURN_COUNT):
        group, number, x, y = prg[base + 5 * i:base + 5 * i + 4]
        out.setdefault(group, (number, x, y))
    return out


def extras(prg, links, place):
    """The EXTRA slots after FC_GROUPS: {slot, fc, group, name, listed, maps, land, row, ship, restart}. maps is the
    part's DQ5 map range (place = dq4groupbuild.placement), land the top-left cell of the FC destination block (None
    when not listed), restart (DQ5 map, cell) of its FC return place or None."""
    import dq4field
    import dq4fieldport
    import dq4groupbuild
    _, props = dq4fieldport.fc_field(prg)
    records = {e["group"]: e for e in dq4field.places(prg) if e["kind"] == "field" and e["field"] == 0}
    group_of = {part["fc"]: group for group, parts in links.items() for part in parts}
    returns = fc_returns(prg)
    out = []
    for k, (fc, name, listed) in enumerate(EXTRA):
        slot = len(FC_GROUPS) + k
        if slot >= VISITED_SLOTS:
            raise ValueError(f"{name}: slot {slot} is past the {VISITED_SLOTS} slots with a visited bit")
        numbers = sorted(n for (g, _), (dg, n) in place.items() if g == fc)
        if not numbers or numbers != list(range(numbers[0], numbers[-1] + 1)):
            raise ValueError(f"FC group {fc:02X}: its DQ5 maps {numbers} are not one run")
        land = ship = None
        if listed:
            e = records[fc]
            land = (2 * e["x"], 2 * e["y"])
            # 1E:E4B2 moves the ship for slots below SHIP_SLOTS only.
            ship = ship_cell(props, e["ship"], land) if slot < SHIP_SLOTS else None
        restart = None
        if fc in returns:
            number, x, y = returns[fc]
            restart = (place[fc, number][1], dq4groupbuild.cell(x, y))
        out.append({"slot": slot, "fc": fc, "group": group_of[fc], "name": name, "listed": listed,
                    "maps": (numbers[0], numbers[-1]), "land": land, "row": None, "ship": ship, "restart": restart})
    return out


def map_rows(links, place, extra):
    """(group, first map, last map, slot, flags) for every map of the DQ5 groups holding an extra slot: flags bit0
    sets the visited bit and 7E:2193 on entering. The other parts of those groups get slot FF: no visited bit, no
    save slot of their own. A group's first part keeps the engine's lookup (its first slot) when it has an FC slot."""
    by_fc = {e["fc"]: e for e in extra}
    rows = []
    for group in sorted({e["group"] for e in extra}):
        for k, part in enumerate(links[group]):
            numbers = sorted(n for (g, _), (dg, n) in place.items() if g == part["fc"])
            if not numbers:
                continue
            if part["fc"] in by_fc:
                e = by_fc[part["fc"]]
                rows.append((group, *e["maps"], e["slot"], int(e["listed"])))
            elif not (k == 0 and part["fc"] in FC_GROUPS):
                rows.append((group, numbers[0], numbers[-1], 0xFF, 0))
    return rows


def restart_rows(extra):
    """6-byte rows of the start table (START_TABLE) for the extra slots' churches: [BC][BD][X][Y][층 1][80]."""
    return [bytes((e["group"], e["restart"][0], *e["restart"][1], 1, 0x80)) for e in extra if e["restart"]]


def hook_code(at, extra, maps):
    """(bytes, labels) of the extra-slot routines and their tables at `at`.

      land     1E:E552  slot X with a landing cell → $00/$0B54 group, $00·$02/$0B50·$0B52 cell, as 1E:E57F does
      visit    01:8EB2  map ($BC, $BD) in the map table → set its slot's visited bit, 7E:2193 = 80 | slot; slot FF or
                        flags 0 → nothing. Other maps: 06:D3ED as before
      chimera  11:8CBF  7E:2193 with bit7 → that slot
      ship     1E:E4AE  landed cell ($B6, $B8) and group of an extra slot → that slot (others: 23:E452)
      save     25:8365  map in the map table with a slot → that slot as the place to continue
      wipe     01:89A3  saved slot with a church → its row of the start table
      continue 25:82A9  the same for continuing a saved game
      restart  01:899F  the saved slot (7E:2033) instead of the slot of the last town's group; unsaved → the FC
                        chapter-1 church's slot
    """
    import dq4environmentrom
    asm = dq4environmentrom._Asm(at)
    # The slot → church table leads, so a built ROM tells its rows at `at` (rom_restarts).
    starts = b"".join(bytes((e["slot"], e["group"], e["restart"][0])) for e in extra if e["restart"])
    asm.label("starts").b(*starts, 0xFF)

    def jml(target):
        return (0x5C, *target.to_bytes(3, "little"))

    # maplook (M8 X8): carry set and X = the map row of ($BC, $BD).
    asm.label("maplook").b(0xA2, 0x00)
    asm.label("m_loop").long(0xBF, "maps").b(0xC9, 0xFF).rel(0xF0, "m_no").b(0xC5, 0xBC).rel(0xD0, "m_next")
    # 2A:F397 keeps the map number in 5 bits.
    asm.b(0xA5, 0xBD, 0x29, 0x1F).long(0xDF, "maps", 1).rel(0x90, "m_next").long(0xDF, "maps", 2)
    asm.rel(0xF0, "m_hit").rel(0xB0, "m_next")
    asm.label("m_hit").b(0x38, 0x60)
    asm.label("m_next").b(0xE8, 0xE8, 0xE8, 0xE8, 0xE8).rel(0x80, "m_loop")
    asm.label("m_no").b(0x18, 0x60)
    # restart (M8 X8): X = slot in; carry set and X = its row offset in the start table, else X = slot.
    asm.label("restart").b(0x8A, 0x48, 0xA2, 0x00)
    asm.label("r_loop").long(0xBF, "starts").b(0xC9, 0xFF).rel(0xF0, "r_no").b(0xC3, 0x01).rel(0xF0, "r_have")
    asm.b(0xE8, 0xE8, 0xE8).rel(0x80, "r_loop")
    asm.label("r_have").long(0xBF, "starts", 2).b(0x48).long(0xBF, "starts", 1).b(0x48, 0xA2, 0x00)
    asm.label("r_row").b(0xBF, *START_TABLE.to_bytes(3, "little"), 0xC9, 0xFF).rel(0xF0, "r_none")
    asm.b(0xC3, 0x01).rel(0xD0, "r_step").b(0xBF, *(START_TABLE + 1).to_bytes(3, "little"), 0xC3, 0x02)
    asm.rel(0xF0, "r_yes")
    asm.label("r_step").b(0x8A, 0x18, 0x69, 0x06, 0xAA).rel(0x80, "r_row")
    asm.label("r_yes").b(0x68, 0x68, 0x68, 0x38, 0x60)
    asm.label("r_none").b(0x68, 0x68)
    asm.label("r_no").b(0xFA, 0x18, 0x60)

    # land: entered with M8 X8 (1E:E550), A = slot.
    asm.label("land").b(0xAA, 0xDA, 0xA2, 0x00)
    asm.label("l_loop").long(0xBF, "lands").b(0xC9, 0xFF).rel(0xF0, "l_no").b(0xC3, 0x01).rel(0xF0, "l_hit")
    asm.b(0xE8, 0xE8, 0xE8, 0xE8, 0xE8, 0xE8).rel(0x80, "l_loop")
    asm.label("l_hit").long(0xBF, "lands", 1).b(0x85, 0x00, 0x8F, 0x54, 0x0B, 0x7E, 0xC2, 0x20)
    asm.long(0xBF, "lands", 2).b(0x85, 0x00, 0x8F, 0x50, 0x0B, 0x7E)
    asm.long(0xBF, "lands", 4).b(0x85, 0x02, 0x8F, 0x52, 0x0B, 0x7E, 0xE2, 0x20, 0xFA, *jml(LAND_DONE))
    asm.label("l_no").b(0xFA, 0xAF, 0x01, 0x80, 0x01, *jml(LAND_BACK))

    # visit: any width; returns like 06:D3ED (carry set: the caller sets the visited bit and 7E:2193 by group).
    asm.label("visit").b(0x08, 0xE2, 0x30).word(0x20, "maplook").rel(0x90, "v_engine")
    asm.long(0xBF, "maps", 4).b(0x4A).rel(0x90, "v_skip")
    asm.long(0xBF, "maps", 3).b(0x09, SLOT_MARK, 0x8F, *LAST_TOWN.to_bytes(3, "little"), 0x29, 0x7F, 0x48)
    asm.b(0x4A, 0x4A, 0x4A, 0xAA, 0x68, 0x29, 0x07, 0xA8, 0xA9, 0x01)
    asm.label("v_bit").b(0x88).rel(0x30, "v_set").b(0x0A).rel(0x80, "v_bit")
    asm.label("v_set").b(0x1F, *VISITED.to_bytes(3, "little"), 0x9F, *VISITED.to_bytes(3, "little"))
    asm.label("v_skip").b(0x28, 0x18, 0x6B)
    asm.label("v_engine").b(0x28, 0xA5, 0xBC, *jml(IN_LIST))

    # chimera: A = 7E:2193, X = 0 (M8 X8).
    asm.label("chimera").b(0xC9, SLOT_MARK).rel(0x90, "c_engine").b(0x29, 0x7F, 0xAA, 0x6B)
    asm.label("c_engine").b(*jml(SLOT_OF))

    # ship: A = $BC, X = 0, M8 X8, after the landing set $B6/$B8.
    asm.label("ship").b(0x48)
    asm.label("s_loop").long(0xBF, "lands").b(0xC9, 0xFF).rel(0xF0, "s_no").long(0xBF, "lands", 1)
    asm.b(0xC3, 0x01).rel(0xD0, "s_next").b(0xC2, 0x20).long(0xBF, "lands", 2).b(0xC5, 0xB6).rel(0xD0, "s_wide")
    asm.long(0xBF, "lands", 4).b(0xC5, 0xB8).rel(0xD0, "s_wide").b(0xE2, 0x20).long(0xBF, "lands")
    asm.b(0xAA, 0x68, 0x6B)
    asm.label("s_wide").b(0xE2, 0x20)
    asm.label("s_next").b(0xE8, 0xE8, 0xE8, 0xE8, 0xE8, 0xE8).rel(0x80, "s_loop")
    asm.label("s_no").b(0x68, 0xA2, 0x00, *jml(SLOT_OF))

    # save: M8 X8 (25:8352).
    asm.label("save").word(0x20, "maplook").rel(0x90, "sv_engine").long(0xBF, "maps", 3).b(0xC9, 0xFF)
    asm.rel(0xF0, "sv_engine").b(0xAA, 0xA5, 0xBC, *jml(SAVE_DONE))
    asm.label("sv_engine").b(0xA5, 0xBC, 0xA2, 0x00, *jml(SAVE_BACK))

    # restart: A = the group 01:899C chose (M8 X8). Returns the saved slot byte (bit7 is night, 01:89A3 masks it).
    asm.label("restart_slot").b(0xAF, *PLACE_SAVED.to_bytes(3, "little"), 0x29, 0x7F, 0xC9, UNSAVED)
    asm.rel(0xB0, "rs_first").b(0xAF, *PLACE_SAVED.to_bytes(3, "little"), 0x6B)
    asm.label("rs_first").b(0xA9, slot_of_fc(FIRST_CHURCH_FC), 0x6B)

    # wipe: A = saved slot byte, M8 X8.
    asm.label("wipe").b(0x29, 0x7F, 0xAA).word(0x20, "restart").rel(0x90, "w_engine").b(*jml(WIPE_DONE))
    asm.label("w_engine").b(0xBF, *RULER_LIST.to_bytes(3, "little"), *jml(WIPE_BACK))

    # continue: A = slot, M8 X8.
    asm.label("continue").b(0xAA).word(0x20, "restart").rel(0x90, "k_engine")
    asm.b(0xBF, *START_TABLE.to_bytes(3, "little"), *jml(CONTINUE_DONE))
    asm.label("k_engine").b(0xAF, 0x01, 0x80, 0x01, *jml(CONTINUE_BACK))

    lands = b"".join(bytes((e["slot"], e["group"])) + e["land"][0].to_bytes(2, "little") + e["land"][1].to_bytes(2, "little")
                     for e in extra if e["land"])
    rows = b"".join(bytes(r) for r in maps)
    asm.label("maps").b(*rows, 0xFF).label("lands").b(*lands, 0xFF)
    return asm.assemble()


def rom_restarts(rom, at=HOOK_AT):
    """{slot: (group, map)} of the slot → church table of a ROM whose continue site jumps into the hook at `at`;
    {} for a ROM without the hook."""
    o = lorom(CONTINUE_SITE)
    if rom[o] != 0x5C or rom[o + 3] != at >> 16:
        return {}
    out, t = {}, lorom(at)
    while rom[t] != 0xFF:
        out[rom[t]] = (rom[t + 1], rom[t + 2])
        t += 3
    return out


def hook_writes(extra, maps, at=HOOK_AT):
    """dq5patch/1 writes: the routines and the eight site patches."""
    data, labels = hook_code(at, extra, maps)
    if at >> 16 != (at + len(data) - 1) >> 16:
        raise ValueError("ルーラ slot hook crosses a bank")

    def site(addr, orig, opcode, label, note):
        size = len(bytes.fromhex(orig))
        code = bytes((opcode, *labels[label].to_bytes(3, "little"))) + b"\xEA" * (size - 4)
        return {"at": cpu(addr), "hex": code.hex(" ").upper(), "orig": orig, "note": note}

    return [{"at": cpu(at), "hex": data.hex(" ").upper(), "note": "맵별 ルーラ 칸 루틴과 표"},
            site(LAND_SITE, LAND_ORIG, 0x5C, "land", "ルーラ 칸으로 내리는 자리"),
            site(VISIT_SITE, VISIT_ORIG, 0x22, "visit", "맵에 들어설 때 다녀온 칸"),
            site(CHIMERA_SITE, SLOT_OF_ORIG, 0x22, "chimera", "キメラのつばさ 의 마지막 마을 칸"),
            site(SHIP_SITE, SLOT_OF_ORIG, 0x22, "ship", "ルーラ 뒤 배 자리의 칸"),
            site(SAVE_SITE, SAVE_ORIG, 0x5C, "save", "저장할 때 이어 할 칸"),
            site(WIPE_SITE, WIPE_ORIG, 0x5C, "wipe", "전멸 뒤 다시 시작 자리"),
            site(CONTINUE_SITE, CONTINUE_ORIG, 0x5C, "continue", "이어 할 때 다시 시작 자리"),
            site(RESTART_SITE, RESTART_ORIG, 0x22, "restart_slot", "전멸 뒤 저장한 칸으로")]


def writes(dq5, dests):
    """dq5patch/1 writes: the ルーラ list slots and both ship offset tables."""
    out = []
    o = lorom(RULER_LIST)
    old = dq5[o:o + RULER_COUNT]
    new = bytearray(old)
    for d in dests:
        new[d["slot"]] = d["group"]
    out.append({"at": cpu(RULER_LIST), "hex": new.hex(" ").upper(), "orig": old.hex(" ").upper(),
                "note": "ルーラ 행선지 그룹"})
    for table in SHIP_OFFSETS:
        o = lorom(table)
        old = dq5[o:o + 2 * SHIP_SLOTS]
        new = bytearray(old)
        for d in dests:
            if d["ship"] is None:
                continue
            if d["slot"] >= SHIP_SLOTS:
                raise ValueError(f"slot {d['slot']}: 1E:E4B2 moves the ship for slots below {SHIP_SLOTS} only")
            dx, dy = (d["ship"][i] - d["land"][i] for i in (0, 1))
            if not (-128 <= dx < 128 and -128 <= dy < 128):
                raise ValueError(f"{d['name']}: ship offset {dx},{dy} is not a signed byte")
            new[2 * d["slot"]:2 * d["slot"] + 2] = bytes((dx & 0xFF, dy & 0xFF))
        out.append({"at": cpu(table), "hex": new.hex(" ").upper(), "orig": old.hex(" ").upper(),
                    "note": "ルーラ 뒤 배 자리(행선지 칸 기준)"})
    return out


def names_doc(dq5, dests):
    """dq5names/1 of the destinations' names in name table 0B (the ルーラ list window)."""
    return {"format": "dq5names/1", "tables": [{"table": NAME_TABLE, "names": [
        {"id": d["slot"], "bytes": list(name_bytes(dq5, d["name"]))} for d in dests]}]}


def main():
    import dq4groupbuild
    from kr_patch.fc import ines
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dq5", default="rom/dq5.sfc", type=Path)
    ap.add_argument("--dq4", default="rom/dq4.nes", type=Path)
    ap.add_argument("-o", "--out", required=True, type=Path)
    args = ap.parse_args()
    prg = ines.prg(args.dq4.read_bytes())
    dests = destinations(prg, dq4groupbuild.LINKS, dq4groupbuild.doors(prg))
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "travel.json").write_text(json.dumps(dests, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(dests, ensure_ascii=False))


if __name__ == "__main__":
    main()
