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
# FC_GROUPS 의 FC 기록 이름(dq4field.places 그대로, destinations 가 롬과 견줌). 창 글자(dq4windowtext)는 이름 표 0B 를
# 쓰기 전 롬으로 빌드하므로 칸 번호로 한글 이름을 찾는다(slot_names)
FC_NAMES = ('キングレオ', 'サントハイム', 'バトランド', 'エンドール', 'ボンモール', 'ブランカ', 'ハバりア', 'イムル',
            'たびだちのむら', 'モンバーバラ', 'レイクナバ', 'コーミズ')
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
# 장 끝 기록 물음(dq4ch2event.chapter_flow)에 「예」 로 쓴 기록. FC 는 그 기록을 이어 하면 다음 장 첫머리(제목 상자·서두)부터
# 다시 돈다(1A:$B96B 의 기록 뒤 리셋·이어 하기 실측). 그 기록은 다음 장 상태(첫머리 대기 flag 가 켜짐)이고 이어 할 칸
# 7E:2033 은 그 장 FC 귀환 자리 칸이다(타이틀의 기록 목록이 칸 번호로 이름 표 0B 를 읽으므로 ルーラ 칸 밖의 번호를 두면
# 목록 창이 멈춘다). 이어 하기 훅은 첫머리 대기 flag 를 보고 그 장 첫머리 맵의 시작 칸 줄로 보낸다. 저장 훅은 맵을 옮기는
# 7E:21A3 의 「예」 대답(dq4ch2event.SAVE_YES)이 켜져 있으면 맵의 칸 대신 7E:2033 을 그대로 둔다(장 끝 맵은 칸이 다름).
# (훅 안 번호, 그룹, 맵, 셀, 귀환 FC 그룹, 첫머리 대기 flag): 번호는 시작 자리 표를 찾는 starts 표의 열쇠로만 쓰고 저장하지
# 않는다(ルーラ 칸·새 게임 칸과 겹치지 않게 그 뒤). 셀·flag 는 dq4ch2event·dq4ch3event 의 것(test_dq4chaptersave 가 견줌)
CHAPTER_STARTS = ((0x17, 0x3D, 0x01, (0x12, 0x11), 0x13, (0x7E2208, 0x40)),
                  (0x18, 0x3E, 0x01, (0x36, 0x0B), 0x16, (0x7E2208, 0x20)))
SAVE_YES_FLAG = (0x7E21A3, 0x08)
# 7E:2193 is the last town entered, read only by キメラのつばさ (11:8CBB). An extra slot's town stores 80 | slot there,
# as no group number has bit7.
LAST_TOWN, VISITED, SLOT_MARK = 0x7E2193, 0x7E2030, 0x80
# FC 1~4장 「どこへ」 목록은 다녀온 비트 차례(10:$95EB 의 FC 그룹 차례)로 뜬다. 21:9E2C(BRK 88 4D, 목록 순번 → 칸)를
# 이 차례로 바꾸는 훅을 건다(order_slots). 목록 창 이름(04:B88A)과 고른 칸이 같은 길을 지나 함께 바뀐다.
# 그룹 0A 는 이 롬에 칸이 없다. 5장 목록(10:$95FA)은 차례가 달라 아직 다루지 않는다.
FC_LIST_ORDER = (0x02, 0x12, 0x01, 0x0E, 0x0F, 0x0C, 0x16, 0x05, 0x04, 0x15, 0x17, 0x00, 0x11, 0x0A)
ORDER_SITE, ORDER_ORIG, ORDER_DONE, ORDER_SLOTS = 0x219E2C, "AF 01 80 01", 0x219E4C, 0x18
# 장 시작 때 FC 는 다녀온 비트를 12:$9179[5 × 장] 으로 덮는다. 2장은 サントハイム 하나(04 = 비트 2 = 그룹 01)
CHAPTER2_VISITED_FC = (0x01,)
# キメラのつばさ(11:8CA3 BRK 95 00 / BRK 98 AE 「ほうりなげた」 → 88E5 물건 줄이기 → 8CB2 날기). 다녀온 칸이 있으면 그 앞에서 ルーラ
# 목록 창(BRK 95 4D)을 띄워 고른 칸을 7E:2193 = 80 | 칸 으로 두고, 그만두면 물건을 줄이지 않고 처리기 끝(11:8A36)으로.
# 창 BRK(95)는 뱅크 11 밖에서 부르면 창이 뜨지 않고 멈추었으므로(5B 에서 BRK 95 00 만 부른 롬, 98 은 됨), 창을 여는
# 토막은 뱅크 11 의 やみのランプ 처리기 자리(11:8C18~8C50, 이 롬에 나오지 않는 DQ5 물건)에 둔다. 그 물건은 「아무 일도
# 없음」 처리기(11:8BBD)로 돌린다. 목록을 띄울지는 뱅크 밖 kimera 가 C 로 돌려준다
KIMERA_SITE, KIMERA_ORIG, KIMERA_CANCEL = 0x118CA3, "00 95 00", 0x118A36
KIMERA_STUB, KIMERA_STUB_END = 0x118C18, 0x118C51
LAMP_HANDLER, LAMP_ORIG, NOTHING_HANDLER = 0x118F81, "18 8C", 0x8BBD
LAMP_CODE = ("00 95 00 AD 21 0F 85 F5 00 98 BE AD 49 19 D0 13 22 00 80 21 B0 0D 22 D3 F8 1F C9 00 D0 05 20 51 8C 90 07 "
             "00 97 13 00 98 8E 60 00 0E 00 95 FF C2 20 20 A1 82 68 68 82 91 FC")
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
        if e["name"] != FC_NAMES[slot]:
            raise ValueError(f"FC group {fc:02X}: record name {e['name']} is not FC_NAMES[{slot}] {FC_NAMES[slot]}")
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


def slot_names():
    """{ルーラ slot: FC kana name}: FC_GROUPS by FC_NAMES, then EXTRA."""
    return {**dict(enumerate(FC_NAMES)), **{len(FC_GROUPS) + k: name for k, (_, name, _) in enumerate(EXTRA)}}


def slot_of_fc(fc):
    """ルーラ slot of an FC group: its place in FC_GROUPS, then EXTRA."""
    order = [*FC_GROUPS, *(e[0] for e in EXTRA)]
    if fc not in order:
        raise ValueError(f"FC group {fc:02X} has no ルーラ slot")
    return order.index(fc)


def chapter_slot_code(church=CHAPTER2_CHURCH_FC, visited=CHAPTER2_VISITED_FC):
    """M8 code that puts a chapter's FC return place (church, chapter 2's by default) in 7E:2033 by day: where a
    wipe-out goes back to, and continuing, until the party saves. Then the visited bits 7E:2030~2032 become the FC
    chapter's (visited) as FC's chapter start overwrites them, and 7E:2193 its first town's slot."""
    out = bytes((0xA9, slot_of_fc(church), 0x8F, *PLACE_SAVED.to_bytes(3, "little")))
    bits = sum(1 << slot_of_fc(fc) for fc in visited)
    for k in range(3):
        out += bytes((0xA9, bits >> 8 * k & 0xFF, 0x8F, *(VISITED + k).to_bytes(3, "little")))
    return out + bytes((0xA9, SLOT_MARK | slot_of_fc(visited[0]), 0x8F, *LAST_TOWN.to_bytes(3, "little")))


def order_slots():
    """ルーラ 칸 0~23 을 FC 목록 차례(FC_LIST_ORDER, 칸이 있는 것만) 뒤에 나머지 칸 차례로. 모든 칸이 한 번씩 들어
    목록 수(BRK 88 4C)와 순번 → 칸이 어긋나지 않는다."""
    order = []
    for fc in FC_LIST_ORDER:
        try:
            order.append(slot_of_fc(fc))
        except ValueError:
            pass
    return order + [s for s in range(ORDER_SLOTS) if s not in order]


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


def chapter_start_rows():
    """Start table rows of the chapter starts (CHAPTER_STARTS): the opening map's start cell, [BC][BD][X][Y][층 1][80]."""
    return [bytes((group, number, *cell, 1, 0x80)) for _, group, number, cell, *_ in CHAPTER_STARTS]


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
    starts += b"".join(bytes((key, group, number)) for key, group, number, *_ in CHAPTER_STARTS)
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

    # save: M8 X8 (25:8352). 장 끝 기록 물음의 「예」 면 7E:2033(dq4ch2event.chapter_save 가 둔 귀환 자리 칸) 그대로
    asm.label("save").b(0xAF, *SAVE_YES_FLAG[0].to_bytes(3, "little"), 0x29, SAVE_YES_FLAG[1]).rel(0xF0, "sv_map")
    asm.b(0xAF, *PLACE_SAVED.to_bytes(3, "little"), 0x29, 0x7F, 0xAA, 0xA5, 0xBC, *jml(SAVE_DONE))
    asm.label("sv_map").word(0x20, "maplook").rel(0x90, "sv_engine").long(0xBF, "maps", 3).b(0xC9, 0xFF)
    asm.rel(0xF0, "sv_engine").b(0xAA, 0xA5, 0xBC, *jml(SAVE_DONE))
    asm.label("sv_engine").b(0xA5, 0xBC, 0xA2, 0x00, *jml(SAVE_BACK))

    # restart: A = the group 01:899C chose (M8 X8). Returns the saved slot byte (bit7 is night, 01:89A3 masks it).
    asm.label("restart_slot").b(0xAF, *PLACE_SAVED.to_bytes(3, "little"), 0x29, 0x7F, 0xC9, UNSAVED)
    asm.rel(0xB0, "rs_first").b(0xAF, *PLACE_SAVED.to_bytes(3, "little"), 0x6B)
    asm.label("rs_first").b(0xA9, slot_of_fc(FIRST_CHURCH_FC), 0x6B)

    # wipe: A = saved slot byte, M8 X8.
    asm.label("wipe").b(0x29, 0x7F, 0xAA).word(0x20, "restart").rel(0x90, "w_engine").b(*jml(WIPE_DONE))
    asm.label("w_engine").b(0xBF, *RULER_LIST.to_bytes(3, "little"), *jml(WIPE_BACK))

    # continue: A = slot, M8 X8, 기록을 WRAM 에 불러온 뒤. 다음 장 첫머리 대기 flag 가 켜진 기록(장 끝 기록 물음의 「예」)이면
    # 칸 대신 그 장 첫머리 줄(CHAPTER_STARTS). 뒤 장부터 본다
    asm.label("continue").b(0xAA)
    for k, (key, _, _, _, _, (addr, mask)) in reversed(list(enumerate(CHAPTER_STARTS))):
        asm.b(0xAF, *addr.to_bytes(3, "little"), 0x29, mask).rel(0xF0, f"k_not{k}").b(0xA2, key).rel(0x80, "k_look")
        asm.label(f"k_not{k}")
    asm.label("k_look").word(0x20, "restart").rel(0x90, "k_engine")
    asm.b(0xBF, *START_TABLE.to_bytes(3, "little"), *jml(CONTINUE_DONE))
    asm.label("k_engine").b(0xAF, 0x01, 0x80, 0x01, *jml(CONTINUE_BACK))

    # order (M8 X8, 21:9E2C): $42 = 목록 순번 → X = 그 순번의 다녀온 칸(order 표 차례), 없으면 FF. 21:9E4C 가 X 를 $46 에
    asm.label("order").b(0x64, 0x4D, 0xA2, 0x00)
    asm.label("o_loop").long(0xBF, "order_tab").b(0xC9, 0xFF).rel(0xF0, "o_none")
    asm.b(0xDA, 0x48, 0x4A, 0x4A, 0x4A, 0xAA, 0x68, 0x29, 0x07, 0xA8, 0xBF, *VISITED.to_bytes(3, "little"))
    asm.label("o_bit").b(0x88).rel(0x30, "o_test").b(0x4A).rel(0x80, "o_bit")
    asm.label("o_test").b(0x4A, 0xFA).rel(0x90, "o_next")
    asm.b(0xA5, 0x4D, 0xE6, 0x4D, 0xC5, 0x42).rel(0xF0, "o_hit")
    asm.label("o_next").b(0xE8).rel(0x80, "o_loop")
    asm.label("o_hit").long(0xBF, "order_tab").b(0xAA, *jml(ORDER_DONE))
    asm.label("o_none").b(0xA2, 0xFF, *jml(ORDER_DONE))

    # kimera (M8, KIMERA_STUB 의 JSL): 다녀온 칸이 있으면 C = 1(FC 는 장과 상관없이 「どこへ」 목록)
    asm.label("kimera").b(0xAF, *VISITED.to_bytes(3, "little"), 0x0F, *(VISITED + 1).to_bytes(3, "little"),
          0x0F, *(VISITED + 2).to_bytes(3, "little")).rel(0xF0, "k_no").b(0x38, 0x6B)
    asm.label("k_no").b(0x18, 0x6B)

    lands = b"".join(bytes((e["slot"], e["group"])) + e["land"][0].to_bytes(2, "little") + e["land"][1].to_bytes(2, "little")
                     for e in extra if e["land"])
    rows = b"".join(bytes(r) for r in maps)
    asm.label("maps").b(*rows, 0xFF).label("lands").b(*lands, 0xFF).label("order_tab").b(*order_slots(), 0xFF)
    return asm.assemble()


def kimera_stub(check):
    """(bytes, labels) of the bank-11 piece at KIMERA_STUB that 11:8CA3 calls with JSR in place of BRK 95 00 (M8 X8):
    `check` (the kimera hook) → list window, 7E:2193 = 80 | picked slot; then BRK 95 00 and back to the message.
    B in the window drops this return and ends the item handler like 11:8A36 without using the item."""
    import dq4environmentrom
    asm = dq4environmentrom._Asm(KIMERA_STUB)
    asm.b(0x22, *check.to_bytes(3, "little")).rel(0x90, "plain")
    asm.label("list").b(0x00, 0x95, 0x4D, 0xA5, 0xE8).rel(0x30, "cancel")
    asm.b(0x85, 0x42, 0x00, 0x88, 0x4D).label("pick").b(0xA5, 0x46, 0x09, SLOT_MARK, 0x8F, *LAST_TOWN.to_bytes(3, "little"))
    asm.label("plain").b(0x00, 0x95, 0x00, 0x60)
    asm.label("cancel").b(0x68, 0x68, 0x4C, *(KIMERA_CANCEL & 0xFFFF).to_bytes(2, "little"))
    data, labels = asm.assemble()
    if KIMERA_STUB + len(data) > KIMERA_STUB_END:
        raise ValueError("キメラのつばさ 목록 토막이 やみのランプ 처리기 자리를 넘음")
    return data, labels


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
    """dq5patch/1 writes: the routines and the site patches."""
    data, labels = hook_code(at, extra, maps)
    if at >> 16 != (at + len(data) - 1) >> 16:
        raise ValueError("ルーラ slot hook crosses a bank")
    stub, _ = kimera_stub(labels["kimera"])

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
            site(RESTART_SITE, RESTART_ORIG, 0x22, "restart_slot", "전멸 뒤 저장한 칸으로"),
            site(ORDER_SITE, ORDER_ORIG, 0x5C, "order", "ルーラ 목록을 FC 차례로"),
            {"at": cpu(KIMERA_STUB), "hex": stub.hex(" ").upper(),
             "orig": " ".join(LAMP_CODE.split()[:len(stub)]), "note": "2장 キメラのつばさ 목록 창(やみのランプ 처리기 자리)"},
            {"at": cpu(KIMERA_SITE), "hex": f"20 {KIMERA_STUB & 0xFF:02X} {KIMERA_STUB >> 8 & 0xFF:02X}",
             "orig": KIMERA_ORIG, "note": "キメラのつばさ: 창 BRK 앞에 2장 목록"},
            {"at": cpu(LAMP_HANDLER), "hex": f"{NOTHING_HANDLER & 0xFF:02X} {NOTHING_HANDLER >> 8:02X}",
             "orig": LAMP_ORIG, "note": "やみのランプ 처리기를 「아무 일도 없음」으로(자리를 목록 토막이 씀)"}]


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
