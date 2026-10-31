"""Build the DQ4 environment maps with whole FC groups in new DQ5 groups, linked by their FC exits.

Order matters (sfc/dq4/docs/dq4-environment-format.md, 「그룹 연결」):
  1. dq4environmentrom.py patch and dq4door.py -> env ROM. dq5newmap.py check wants the door table copy made in 2
     to match bank 01 from 01:F037 on, so the copy must contain the hook stubs and door code of the bank-01 tail.
  2. dq5newmap.py from the env ROM: new groups, maps (records from the dq5map/1 documents of 1), arrivals.
  3. dq5exitreloc.py, dq5npcrelocate.py (the FC people of dq4npcport.py), dq5fieldtables.py from the original
     ROM with --new-map, dq5textwrite.py with their Japanese FC text, and dq5progresswrite.py with the FC
     shop lists plus the inn price table and the per-FC-group shop key hook of dq4shopport.py, and
     dq5talkwrite.py with the talk scripts that show the people's messages (dq4npcport.talk_doc), and the
     ルーラ list slots and names of the FC destinations (dq4fieldtravel.py, dq5namewrite.py), and the FC field
     encounter zones (dq4fieldencounter.py: dq5progresswrite.py records, dq5encounterwrite.py grids).
  4. dq5chestplace.py from the original ROM with the patches of 1-3 (--with-patch): the FC chests and
     タンス·つぼ of dq4chestport.py on the cells 1 gave their DQ5 attributes.
  5. dq4fieldport.py: FC fields 0, 1 and 3 as DQ5 worlds 0-2 with the DQ4 field art (dq5fieldgfxwrite.py,
     dq5fieldtables.py, dq5fieldwrite.py).
  6. dq5build.py on the original ROM with 1-5.

FC stairs (08:$B22E) become same-group exits, FC exit-table cells ($05A0) become area moves, and the map
edge leads to the field through the aux entrance table, onto the FC entrance of the group. The original DQ5
entrances of every world move off the FC ground (dq4fieldport.park).

  python sfc/dq4/tools/dq4groupbuild.py --out work/dq4-groups
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import functools
import json
import os
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parents[2]
DQ5_TOOLS = TOOLS.parents[1] / "dq5" / "tools"
FC_TOOLS = ROOT / "fc" / "dq4" / "tools"
for path in (TOOLS, DQ5_TOOLS, FC_TOOLS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import dq4block  # noqa: E402
import dq4buildcache  # noqa: E402
import dq4entrancehook  # noqa: E402
import dq4field  # noqa: E402
import dq4fieldport  # noqa: E402
import dq4map  # noqa: E402
from dq4environmentmap import all_maps, block_prop  # noqa: E402
from dq4environmentrom import DOOR_BANK, DOOR_TABLES, GROUPS, STAIRS  # noqa: E402
from kr_patch.fc import ines  # noqa: E402

# New DQ5 group -> the FC groups it holds, in DQ5 map order (layout). Per FC group: the FC arrival from the
# field ($44/$45 after walking in from the field entrance; fc/dq4/tools/dq4field.py entrances lists the same
# cells) and its FC map ("map", 0 when absent), the borrowed DQ5 map whose attributes (encounters, battle
# background, music) its maps take, its FC field-0 entrance blocks (dq4field.py entrances; the DQ5 world is FC
# field 0 block for block, dq4fieldport.py), and the inputs that take the party from the arrival to the field.
# "music" replaces the song byte of the copied attributes (attribute +5): FC plays one song for the whole group
# (19:$803B, map branch $07BA), and 02 バトランド plays FC song 03, 王宮のメヌエット, which the sound port puts
# in DQ5 song slot 01. A "dungeon" part's maps take the zones of the FC dungeon list in place of the borrowed
# ones (map_attrs, dungeon_zones) and its DQ5 group counts steps for encounters (INDOOR_ENCOUNTERS). The DQ5
# group's own arrival (the dq5newmap entrance) is its first FC group's.
LINKS = {
    0x36: [{"fc": 0x02, "arrival": (0x00, 0x1D), "attrs": "03/00", "music": 0x01, "field": [(0xA4, 0x2E)],
            "out": "left:64"}],
    # 마을 곡: 19/02 의 곡 바이트 07 은 사운드 포팅에서 楽しいカジノ 자리라, FC 마을 곡 0C 街でのひととき 가 든 06 으로
    0x37: [{"fc": 0x12, "arrival": (0x0D, 0x19), "attrs": "19/02", "music": 0x06, "field": [(0x9A, 0x16)], "out": "down:64"}],
    # 古井戸の底, the tower of chapter 1's end, and the house of 41/00. The dungeons borrow a DQ5 cave (21/02:
    # battle background 07, ルーラ hits the ceiling) or tower (33/00: background 0A) and take the FC dungeon
    # zones ("dungeon"). FC plays 恐怖の洞窟 (FC song 06, DQ5 slot 09) in 1C and map branch 5 (3A, 41) and
    # 呪われし塔 (07, slot 0A) in branch 4 (30).
    0x38: [{"fc": 0x1C, "arrival": (0x0D, 0x10), "attrs": "21/02", "music": 0x09, "dungeon": True,
            "field": [(0xA2, 0x1A)], "out": "down:64"}],
    0x39: [{"fc": 0x30, "arrival": (0x10, 0x21), "map": 3, "attrs": "33/00", "music": 0x0A, "dungeon": True,
            "field": [(0x88, 0x17)], "out": "down:64"}],
    # 41/00's arrival is its stair to the field: step off and back on. FC enters it from two caves, each onto
    # its own stair, and each stair leaves by its cave (08:$B2EC). Bataland's land reaches only (8D,1F) and
    # イムル's only (8D,1B), so one arrival and one way out made the cave one-way.
    0x3A: [{"fc": 0x41, "arrival": (0x03, 0x03), "attrs": "21/02", "music": 0x09, "dungeon": True,
            "field": [(0x8D, 0x1B), (0x8D, 0x1F)],
            "stairs": {(0x8D, 0x1B): (0x03, 0x03), (0x8D, 0x1F): (0x0E, 0x30)}, "out": "down:32,wait:60,up:32"}],
    # Below 古井戸の底: no field entrance; its group arrival is the cell the well's stair leads to (3A/02).
    0x3B: [{"fc": 0x3A, "arrival": (0x03, 0x02), "map": 2, "attrs": "21/02", "music": 0x09, "dungeon": True,
            "field": None, "out": None}],
    # The prologue's village (FC 14/00). The field leads to the ruined 14/02, so this arrival is the same cell
    # of 14/00. The prologue places its own people: the FC people of 14/00 belong to chapter 5's start.
    0x3C: [{"fc": 0x14, "arrival": (0x0C, 0x18), "attrs": "19/02", "music": 0x06, "field": [(0x91, 0x31)], "out": "down:64",
            "people": False}],
    # Chapter 2: サントハイム castle, テンペ and フレノール. フレノール's FC arrival is on the map's top row.
    0x3D: [{"fc": 0x01, "arrival": (0x0F, 0x1B), "attrs": "03/00", "field": [(0x27, 0x49)], "out": "down:64", "chapter": 2},
           {"fc": 0x0E, "arrival": (0x0A, 0x2C), "attrs": "03/00", "field": [(0x47, 0x39)], "out": "down:64", "chapter": 2},
           {"fc": 0x0F, "arrival": (0x16, 0x00), "attrs": "03/00", "field": [(0x60, 0x28)], "out": "up:64", "chapter": 2}],
    # Chapter 3: レイクナバ and the cave where its iron safe lies (きたのどうくつ, arrival on its stair to the field),
    # ボンモール, and エンドール. Each town leads a DQ5 group, so each takes a ルーラ slot (dq4fieldtravel). Their
    # people and sellers are those of chapter 3's start ($615A = 2).
    0x3E: [{"fc": 0x16, "arrival": (0x00, 0x0D), "attrs": "03/00", "field": [(0x68, 0x24)], "out": "left:64",
            "chapter": 3},
           {"fc": 0x3D, "arrival": (0x0B, 0x03), "attrs": "03/00", "field": [(0x71, 0x14)],
            "out": "down:32,wait:60,up:32", "chapter": 3}],
    0x3F: [{"fc": 0x05, "arrival": (0x11, 0x1F), "map": 1, "attrs": "03/00", "field": [(0x74, 0x46)], "out": "down:64",
            "chapter": 3}],
    0x40: [{"fc": 0x04, "arrival": (0x17, 0x20), "attrs": "03/00", "field": [(0x67, 0x65)], "out": "down:64",
            "chapter": 3}],
    # 4장: モンバーバラ, コーミズ 와 그 서쪽 동굴(にしのどうくつ, 도착은 필드로 나가는 계단 위), ハバリア, キングレオ 성.
    # 인물과 판매자는 4장 시작 상태($615A = 3)의 것.
    0x41: [{"fc": 0x15, "arrival": (0x13, 0x1B), "attrs": "03/00", "field": [(0x39, 0xE6)], "out": "down:64",
            "chapter": 4}],
    0x42: [{"fc": 0x17, "arrival": (0x00, 0x10), "attrs": "03/00", "field": [(0x33, 0xBD)], "out": "left:64",
            "chapter": 4},
           {"fc": 0x38, "arrival": (0x11, 0x24), "attrs": "03/00", "field": [(0x1F, 0xBA)],
            "out": "down:32,wait:60,up:32", "chapter": 4}],
    0x43: [{"fc": 0x11, "arrival": (0x26, 0x25), "attrs": "03/00", "field": [(0x42, 0x9A)], "out": "down:64",
            "chapter": 4}],
    0x44: [{"fc": 0x00, "arrival": (0x0F, 0x1A), "attrs": "03/00", "field": [(0x40, 0xA6)], "out": "down:64",
            "chapter": 4}],
    # Chapter 2's other places in one group: サラン, the desert bazaar, the tower of the honey (西の塔) and the
    # bracelet cave south of フレノール. The tower and the cave borrow the attributes of chapter 1's tower and cave.
    # The travel-door shrine by エンドール (1E) waits: its travel door (FC exit kind 0A) has no DQ5 exit yet.
    0x45: [{"fc": 0x13, "arrival": (0x0C, 0x19), "attrs": "03/00", "music": 0x06, "field": [(0x22, 0x49)],
            "out": "down:64", "chapter": 2},
           {"fc": 0x0C, "arrival": (0x1F, 0x0B), "attrs": "03/00", "field": [(0x3F, 0x4A)], "out": "right:64",
            "chapter": 2},
           {"fc": 0x2E, "arrival": (0x15, 0x1F), "map": 3, "attrs": "33/00", "music": 0x0A, "dungeon": True,
            "field": [(0x24, 0x57)], "out": "down:64", "chapter": 2},
           {"fc": 0x39, "arrival": (0x23, 0x08), "map": 1, "attrs": "21/02", "music": 0x09, "dungeon": True,
            "field": [(0x58, 0x3C)], "out": "down:32,wait:60,up:32", "chapter": 2}],
    # 5장 시작 지역: ブランカ 와 きこりのいえ(20). 인물과 판매자는 5장 시작 상태($615A = 4)의 것. 여우가 홀리는
    # 마을(18)은 자고 나면 사라지는 이벤트와 장소별 값(はがねのつるぎ 10G)이 있어 뺀다.
    0x46: [{"fc": 0x06, "arrival": (0x10, 0x1D), "attrs": "03/00", "field": [(0x99, 0x45)], "out": "down:64",
            "chapter": 5},
           {"fc": 0x20, "arrival": (0x06, 0x0C), "attrs": "03/00", "field": [(0x92, 0x3A)], "out": "down:64",
            "chapter": 5}],
    # ブランカ 에서 エンドール 로 가는 터널. 3장에 뚫린 뒤(5장)의 42/01 만 옮긴다. FC 는 입구마다 그 쪽 계단으로
    # 들여보낸다(08:$AF99).
    0x47: [{"fc": 0x42, "arrival": (0x1F, 0x02), "map": 1, "attrs": "03/00", "field": [(0x84, 0x5A), (0x79, 0x5D)],
            "stairs": {(0x84, 0x5A): (0x1F, 0x02), (0x79, 0x5D): (0x05, 0x0F)}, "out": "down:32,wait:60,up:32",
            "chapter": 5}],
}
# The attribute table grows by 6 bytes a map and outgrows its own bank (108 spare bytes), so it moves whole; the
# map pointer table (3 bytes a map) outgrew bank 0F with chapter 3's maps and moves the same way. The entrance and
# pointer tables sit after the chest tables (3C:8400-), leaving 3C:A000-CFFF to the area moves.
NEWMAP_AT = ("--entrance-table-at", "3C:9000", "--door-bank", "3B", "--attr-table-at", "3C:D000",
             "--pointer-table-at", "3C:9200")
# New-map records, [start, end) areas in banks 30-3F: the map loader reads a record with DB set to its bank and
# reads low WRAM meanwhile. One dq5newmap call puts all its records in one bank, so the records that do not fit the
# first area go to the next areas in later calls (record_areas, records_pass).
# 3F 는 환경 맵 레코드가 3E 에서 끝나 비어 있고, 30 은 이 빌드에서 아무도 쓰지 않는다(1장 빌드는 이 표를
# dq4chapter1.RECORDS_AT 로 바꾼다).
RECORDS_AT = ((0x348000, 0x350000), (0x318000, 0x320000), (0x3F8000, 0x400000), (0x308000, 0x310000))
# The record a new map points at until a later call gives it its own: any original map.
RECORD_PLACEHOLDER = "03/00"
EXIT_AT = ("--exits-at", "2A:D812", "--records-at", "3C:A000")
ENTRANCES_AT = ("--entrances-at", "3C:8000")
# dq5textwrite writes the whole walking text again, so it takes banks of its own.
TEXT_AT = ("--at", "35:8000")
# Talk scripts 900- (the prologue's and the ported people's, dq4npcport.talk_doc). Bank 30-3F: the hook reads
# them with DB set to their bank. Not 3A: the chapter-1 build fills it with new-map records.
TALK_AT = ("--extra-at", "3C:E800", "--hook-at", "06:FE10")
SHOP_AT = ("--shop-at", "3C:E000")
INN_AT = 0x3CF000
# The entrance hook's tables grow with every group; past chapters 2-4 they reached the shop-key routine at
# 3C:FE00, so the hook has a bank of its own (5B: no other tool writes there).
ENTRANCE_HOOK_AT = 0x5B8000
SHOP_KEY_AT = 0x3CFE00
WELL_SWITCH_AT = 0x3CFF00
DUNGEON_RATE_AT = 0x578000   # a bank of its own: no other tool writes 57
# The three tables chests and drawers grow; dq5chestplace reads chest_maps and search with DB, so bank 00-3F.
# 필드 입구 표(3C:8000)가 5장에서 3C:8400 을 넘어, 어느 뱅크든 long 으로 읽는 상자 표(chests)를 입구 훅과 같은
# 5B 의 뒤쪽으로 옮기고 입구 표가 3C:8800 까지 쓴다.
CHEST_AT = ("--chests-at", "5B:C000", "--chest-maps-at", "3C:8800", "--search-at", "3C:8C00")
# The field loader reads both RLE chunks with DB set to their bank, so 30-3F; bank 3A is free in this build.
FIELD_AT = "3A:8000"
# dq5npcrelocate 의 기본 목록·대체 목록 자리(비우면 그 도구의 기본값 32:8000·33:8000).
NPC_AT = ()
LAYER = 1
WORLD_CODE = 1
# Group arrival +4 bit2-6 -> $194A bit0-4 (2A:FD7E): 4 counts steps for encounters indoors (00:8340), as in the
# DQ5 caves 07-09; 0 never does.
INDOOR_ENCOUNTERS = 0x04
AREA_FLAGS = 0x80
# FC direction (0 up, 2 down) -> the DQ5 row of an FC cell the party first steps onto.
ENTRY_ROW = {0: 1, 2: 0}
# 옆으로 걷는 FC 방향(1 오른쪽, 3 왼쪽) → 일행이 먼저 밟는 열. 일행은 블록의 아래 줄(cell)로만 걸으므로 한 칸이면 된다.
ENTRY_COLUMN = {1: 0, 3: 1}

# Companion monster names (name table 0A, kind * 4 + name number) in the name-entry display bytes, so the status and
# battle windows, battle messages and field messages print them through the same Korean path as the hero's name.
# The tables are packed in place with no spare byte, and other patches write item names inside the later tables, so
# the bytes the longer names take come off the end of slots 0-3 (kind 00 is no companion kind; kinds start at 01) and
# the rewrite stays inside table 0A.
COMPANION_TABLE = 0x0A
COMPANION_NAMES = {0x05 * 4: "호이민"}
COMPANION_SPARE = range(4)
# Human companions' names (name table 00, person number - 3). Chapter 2 borrows the person records of ヘンリー (09) and
# サンチョ (05) for クリフト and ブライ; ピピン, フローラ and パパス never join in this hack, so their slots give the bytes.
PERSON_TABLE = 0x00
PERSON_NAMES = {0x09 - 3: "크리프트", 0x05 - 3: "브라이"}
PERSON_SPARE = (0x06 - 3, 0x07 - 3, 0x08 - 3)


def korean_names(dq5, table, korean, spare):
    """dq5names/1 table: the Korean names in name-entry display bytes, the extra bytes cut off the ends of `spare`
    slots so the packed table keeps its length."""
    import dq4nameentry
    import dq5namewrite
    original = dq5namewrite.read_tables(dq5)[table]
    names = {n: list(b"".join(dq4nameentry.code_bytes(dq4nameentry.GLYPHS.index(c)) for c in name))
             for n, name in korean.items()}
    grow = sum(len(raw) - len(original[n]) for n, raw in names.items())
    for n in spare:
        cut = min(grow, len(original[n]) - 1)
        if cut > 0:
            names[n] = original[n][:len(original[n]) - cut]
            grow -= cut
    if grow > 0:
        raise ValueError(f"name table {table:02X}: {grow} bytes more than slots {list(spare)} hold")
    return {"table": table, "names": [{"id": n, "bytes": raw} for n, raw in sorted(names.items())]}


def companion_names(dq5):
    return korean_names(dq5, COMPANION_TABLE, COMPANION_NAMES, COMPANION_SPARE)


def person_names(dq5):
    return korean_names(dq5, PERSON_TABLE, PERSON_NAMES, PERSON_SPARE)


def cell(x, y):
    """DQ5 cell where the party stands on FC cell (x, y): the bottom-left cell of the 2x2 block, as a
    DQ5 stair arrival (one cell left of the block's bottom-right exit cell)."""
    return x * 2, y * 2 + 1


def layout(links, fc_maps):
    """{(FC group, FC map): (DQ5 group, DQ5 map)}: a DQ5 group's FC groups in `links` order, each one's maps
    (fc_maps[FC group]) in FC order on consecutive DQ5 map numbers from 0."""
    place, seen = {}, set()
    for group, parts in links.items():
        number = 0
        for part in parts:
            if part["fc"] in seen:
                raise ValueError(f"FC group {part['fc']:02X} is listed twice")
            seen.add(part["fc"])
            for k in sorted(fc_maps.get(part["fc"], ())):
                # The engine keeps the map number in 5 bits (2A:F397 AND #$1F).
                if number > 0x1F:
                    raise ValueError(f"DQ5 group {group:02X}: FC {part['fc']:02X}/{k:02X} would be map {number:02X}")
                place[part["fc"], k] = (group, number)
                number += 1
    return place


@functools.cache
def _fc_names(prg):
    return {name: (g, k) for g, k, _, name in all_maps(prg)}


def placement(prg):
    """layout of LINKS for the GROUPS maps. GROUPS must put every map where layout does: dq4environmentrom
    builds each map where GROUPS says, and exits, people and chests read from its FC map go where this says."""
    fc = _fc_names(prg)
    fc_maps = {}
    for name in GROUPS:
        if name not in fc:
            raise ValueError(f"{name}: no FC map")
        fc_maps.setdefault(fc[name][0], []).append(fc[name][1])
    place = layout(LINKS, fc_maps)
    for name, there in GROUPS.items():
        if place.get(fc[name]) != there:
            raise ValueError(f"{name}: FC map {fc[name]} goes to {place.get(fc[name])}, GROUPS says {there}")
    return place


def fc_map(prg, group, number):
    """(FC group, FC map) put on DQ5 map group/number."""
    found = [k for k, v in placement(prg).items() if v == (group, number)]
    if not found:
        raise ValueError(f"{group:02X}/{number:02X}: no FC map is placed there")
    return found[0]


def fc_numbers(prg, fc_group):
    """Ported FC map numbers of an FC group."""
    return sorted(k for g, k in placement(prg) if g == fc_group)


def has_people(fc_group, with_people=True):
    """Whether the FC people and shops of an FC group are ported (LINKS "people", on by default; `with_people` False
    ports none)."""
    return with_people and all(part.get("people", True) for parts in LINKS.values() for part in parts if part["fc"] == fc_group)


def chapter(fc_group):
    """FC chapter whose start the FC people and sellers of an FC group show (LINKS "chapter", 1 by default)."""
    return next((part.get("chapter", 1) for parts in LINKS.values() for part in parts if part["fc"] == fc_group), 1)


def tag(group, part):
    """Name of an FC group's entrance: the DQ5 group, with the FC group when the DQ5 group holds several."""
    return f"{group:02X}" if len(LINKS[group]) == 1 else f"{group:02X}-{part['fc']:02X}"


def doors(prg):
    """{FC group: (DQ5 entrance cells, DQ5 cell it leaves onto)} of every LINKS part with a field entrance
    (dq4fieldport.door on FC field 0). Each listed block must be an FC entrance of that group."""
    fc_entrances = {(fx, fy): g for g, fx, fy, *rest in dq4field.entrances(prg) if (rest[-1] or 0) == 0}
    _, props = dq4fieldport.fc_field(prg)
    out = {}
    for parts in LINKS.values():
        for part in parts:
            if not part["field"]:
                continue
            for fx, fy in part["field"]:
                if fc_entrances.get((fx, fy)) != part["fc"]:
                    raise ValueError(f"FC field ({fx:02X},{fy:02X}) is not an entrance of FC group {part['fc']:02X}")
            out[part["fc"]] = dq4fieldport.door(props, part["field"])
    return out


def entrance_doors(prg):
    """{(FC group, FC field x, y): doors value of that one entrance} of the LINKS parts with "stairs"."""
    _, props = dq4fieldport.fc_field(prg)
    return {(part["fc"], *b): dq4fieldport.door(props, [b])
            for parts in LINKS.values() for part in parts for b in part.get("stairs", {})}


def hook_rows(links, place, entrances, each=None):
    """dq4entrancehook (arrivals, leaving) of every FC group with a field entrance: each of its entrance cells
    (entrances[FC group] = (cells, leave cell), as doors) leads to its arrival, and its maps leave onto the leave
    cell. A DQ5 group of one FC group leaves from any map. A part with "stairs" ({FC field entrance: FC stair})
    enters each entrance onto its stair and leaves each stair by its entrance (each = entrance_doors); other
    hero rows of its maps leave onto the leave cell."""
    arrivals, leaving = [], []
    for group, parts in links.items():
        for part in parts:
            if not part["field"]:
                continue
            found, (lx, ly) = entrances[part["fc"]]
            stairs = part.get("stairs", {})
            number = place[part["fc"], part.get("map", 0)][1]
            for b, stair in stairs.items():
                cells, (sx, sy) = each[(part["fc"], *b)]
                arrivals += [(group, fx, fy, number, *cell(*stair), LAYER, 0) for fx, fy in cells]
                row = cell(*stair)[1]
                leaving.append((group, number, number, sx, sy, row, row))
            done = {(r[1], r[2]) for r in arrivals if r[0] == group}
            for fx, fy in found:
                if (fx, fy) not in done:
                    arrivals.append((group, fx, fy, number, *cell(*part["arrival"]), LAYER, 0))
            numbers = [n for (g, _), (_, n) in place.items() if g == part["fc"]]
            first, last = (0, 0x1F) if len(parts) == 1 else (min(numbers), max(numbers))
            if part["fc"] in FALL_FIELD and group in FALL_GROUPS:
                # 2A:F425 takes the first row that matches, so the fall row goes first
                (k0, k1), (fx, fy) = FALL_FIELD[part["fc"]]
                leaving.append((group, place[part["fc"], k0][1], place[part["fc"], k1][1], fx * 2, fy * 2))
            leaving.append((group, first, last, lx, ly))
    return arrivals, leaving


def exit_order(prg, fc_group, number):
    """FC stair cells of a map in DQ5 exit order (row-major by the block's bottom-right cell)."""
    source = dq4block.Map(prg, fc_group, number)
    found = [(x, y) for y in range(source.h) for x in range(source.w)
             if block_prop(source, source.cell(x, y) & 31) in STAIRS]
    return sorted(found, key=lambda c: (c[1], c[0]))


def exit_rows(group, parts, place, stairs, order):
    """dq5exittables/1 exit lists of DQ5 group `group` holding FC groups `parts`. stairs[(FC group, FC map)]:
    [(x, y, FC destination)] in DQ5 exit order; order(FC group, FC map): a map's stair cells in that order. A
    stair to a map of another DQ5 group is an other-group exit, one to the field the special exit 0."""
    records = {}
    for part in parts:
        fc_group = part["fc"]
        for fc_number in sorted(k for g, k in place if g == fc_group):
            rows = []
            for x, y, dest in stairs[fc_group, fc_number]:
                if dest and "field" in dest:
                    # 2A:F425 leaves by the entrance of the FC group the map belongs to (hook_rows); a part
                    # without one would leave by another FC group's entrance.
                    if not part["field"] and len(parts) > 1:
                        raise ValueError(f"{fc_group:02X}/{fc_number:02X} ({x:02X},{y:02X}): stair to the field "
                                         f"from FC group {fc_group:02X} with no field entrance in DQ5 group {group:02X}")
                    # 2A:F7B2 -> 2A:F425: out to the group's field entrance (aux entrance table).
                    rows.append({"kind": "special", "special": 0})
                    continue
                if not dest or (dest.get("group"), dest.get("index")) not in place:
                    raise ValueError(f"{fc_group:02X}/{fc_number:02X} ({x:02X},{y:02X}): stair to an FC map not ported: {dest}")
                there_group, there_number = place[dest["group"], dest["index"]]
                there = order(dest["group"], dest["index"])
                if (dest["x"], dest["y"]) in there:
                    row = {"kind": "same-group", "destination_map": there_number, "exit": there.index((dest["x"], dest["y"]))}
                    if there_group != group:
                        row = {**row, "kind": "other-group", "group": there_group}
                else:
                    # 출구 표가 정한 목적지가 계단 칸이 아니면(キングレオ 00/04 → 00/00 (0A,13)) 좌표 출구로 선다.
                    x, y = cell(dest["x"], dest["y"])
                    row = {"kind": "position", "destination_map": there_number, "x": x, "y": y, "layer": LAYER,
                           "group": there_group}
                rows.append(row)
            records[f"{group:02X}/{place[fc_group, fc_number][1]:02X}"] = rows or [{"kind": "special", "special": 0}]
    return records


def exit_records(prg, group):
    """exit_rows of a LINKS group from the FC stair links."""
    place = placement(prg)
    cache = {}
    stairs = {}
    for fc_group in (part["fc"] for part in LINKS[group]):
        for fc_number in fc_numbers(prg, fc_group):
            links = dq4block.exit_links(prg, fc_group, fc_number, cache)
            other = sorted({e["prop"] & 0x7F for e in links} - STAIRS)
            if other:
                raise ValueError(f"{fc_group:02X}/{fc_number:02X}: FC exit kinds {[f'{p:02X}' for p in other]} have no DQ5 exit yet")
            to = {(e["x"], e["y"]): e["to"] for e in links}
            stairs[fc_group, fc_number] = [(x, y, to[x, y]) for x, y in exit_order(prg, fc_group, fc_number)]
    return exit_rows(group, LINKS[group], place, stairs, lambda g, k: exit_order(prg, g, k))


def area_records(prg, group):
    """Area moves from the FC exit table ($05A0). Neighbouring FC cells with the same destination share
    one rect. The rect is one DQ5 row: a taller rect maps the arrival Y in proportion with a negative span
    (2A:F636 -> F67C), a one-row rect maps X across span_raw cells (F650). The row is the first one the party
    steps onto, walking in the arrival flag's direction (an FC exit below the map edge must catch the party
    on that first outside row, before the field exit 2A:F425); X holds the party's left cell on the cells. The arrival is the FC arrival cell; the engine then takes one more step in the
    walking direction (2A:F69F), which carries the party off a destination cell that is itself an exit
    (02/01 -> the 02/00 gate)."""
    place = placement(prg)
    cells = {(part["fc"], k): list(dq4map.exits(prg, part["fc"], k))
             for part in LINKS[group] for k in fc_numbers(prg, part["fc"])}
    return area_rows(group, place, cells)


def area_rows(group, place, cells):
    """area_records of DQ5 group `group` from cells[(FC group, FC map)]: FC exit-table cells (x, y, FC group,
    FC map, arrival x, arrival y, flag). The destination may be any FC map placed in the same DQ5 group."""
    out = {}
    for (fc_group, number), found in cells.items():
        runs = []
        for x, y, dg, dk, ax, ay, flag in sorted(found, key=lambda e: (e[1], e[0])):
            if place.get((dg, dk), (None,))[0] != group:
                raise ValueError(f"{fc_group:02X}/{number:02X} ({x:02X},{y:02X}) leaves the group")
            last = runs[-1] if runs else None
            if last and last["y"] == y and last["x1"] + 1 == x and last["to"] == (dg, dk, ay, flag) \
                    and last["ax1"] + 1 == ax:
                last["x1"], last["ax1"] = x, ax
            else:
                runs.append({"x0": x, "x1": x, "y": y, "to": (dg, dk, ay, flag), "ax0": ax, "ax1": ax})
        rows = []
        for run in runs:
            dg, dk, ay, flag = run["to"]
            dx, dy = cell(run["ax0"], ay)
            if flag & 3 in ENTRY_COLUMN:
                if run["x0"] != run["x1"]:
                    raise ValueError(f"{fc_group:02X}/{number:02X}: sideways exit across {run['x1'] - run['x0'] + 1} cells")
                left, row = run["x0"] * 2 + ENTRY_COLUMN[flag & 3], cell(run["x0"], run["y"])[1]
                rows.append({"rect": [left, row, left + 1, row + 1], "source_layer": LAYER, "flags": AREA_FLAGS,
                             "destination_group": group, "destination_map": place[dg, dk][1], "x": dx, "y": dy,
                             "span_raw": 1, "destination_layer": LAYER})
                continue
            left, row = run["x0"] * 2, run["y"] * 2 + ENTRY_ROW[flag & 3]
            right, _ = cell(run["x1"], run["y"])
            rows.append({"rect": [left, row, right + 1, row + 1], "source_layer": LAYER, "flags": AREA_FLAGS,
                         "destination_group": group, "destination_map": place[dg, dk][1], "x": dx, "y": dy,
                         "span_raw": right - left + 1, "destination_layer": LAYER})
        if rows:
            out[f"{group:02X}/{place[fc_group, number][1]:02X}"] = rows
    return out


FALL_PROPS = (0x05, 0x0B)
# Groups whose falling cells are linked. The other chapters' holes come with their chapter's events. In chapter 3's
# きたのどうくつ the way to the iron safe is the hole of 3D/01 down to 3D/03 (FC then sets $62AA bit7, which turns the
# stairs into 3D/01 to 3D/02; that flag is not ported).
FALL_GROUPS = (*range(0x36, 0x3C), 0x3E, 0x40)
# FC groups whose falls drop to the field: {FC group: (FC maps, FC field cell)}. FC moves the party from the field
# cell it came in by (12:$B6DD, $42/$43): the tower 30 drops it 3 cells below where そらとぶくつ lands, (88,16),
# past the moat around the island. Those maps have no other way to the field, so the hook's leave row for them
# (hook_rows) stands there.
FALL_FIELD = {0x30: ((0, 2), (0x88, 0x19))}
FIELD_EXIT = {"destination_group": 0xFF, "destination_map": 0, "x": 0, "y": 0, "span_raw": 0, "destination_layer": 0}


def fall_records(prg, group):
    """FC falling cells (1E:$8676 -> 12:$B6DD, dq4block.fall) whose destination is a map placed in any new DQ5
    group, as area moves {DQ5 map: rows}. One row per run of falling cells on an FC row with the same destination.
    span_raw 1 makes the arrival X the same wherever the party steps in (2A:F650 scales by span - 1). Falls to
    the field are left out."""
    place = placement(prg)
    out = {}
    for part in LINKS[group]:
        for k in fc_numbers(prg, part["fc"]):
            m = dq4block.Map(prg, part["fc"], k)
            runs = []
            for y in range(m.h):
                for x in range(m.w):
                    if m.blocks["prop"].get(m.buf[y * m.w + x] & 0x1F, 0) not in FALL_PROPS:
                        continue
                    to = dq4block.fall(prg, part["fc"], k, x, y)
                    if "field" in to and part["fc"] in FALL_FIELD:
                        key = "field"
                    elif "group" not in to or (to["group"], to["index"]) not in place:
                        continue
                    else:
                        key = (to["group"], to["index"], to["x"], to["y"])
                    last = runs[-1] if runs else None
                    if last and last["y"] == y and last["x1"] + 1 == x and last["to"] == key:
                        last["x1"] = x
                    else:
                        runs.append({"x0": x, "x1": x, "y": y, "to": key})
            rows = []
            for run in runs:
                rect = {"rect": [run["x0"] * 2, run["y"] * 2 + 1, run["x1"] * 2 + 1, run["y"] * 2 + 2],
                        "source_layer": LAYER, "flags": AREA_FLAGS}
                if run["to"] == "field":
                    rows.append({**rect, **FIELD_EXIT})
                    continue
                dg, dk, ax, ay = run["to"]
                dx, dy = cell(ax, ay)
                rows.append({**rect, "destination_group": place[dg, dk][0],
                             "destination_map": place[dg, dk][1], "x": dx, "y": dy, "span_raw": 1,
                             "destination_layer": LAYER})
            if rows:
                out[f"{group:02X}/{place[part['fc'], k][1]:02X}"] = rows
    return out


def record_areas(sizes, areas):
    """Area index of each record (sizes in map order): records follow one another, and one that does not fit the
    rest of its area starts the next area."""
    for start, end in areas:
        if not (0x30 <= start >> 16 <= 0x3F and start & 0xFFFF >= 0x8000 and start < end <= (start | 0xFFFF) + 1):
            raise ValueError(f"records area {_cpu(start)}-{_cpu(end - 1)}: needs one bank of 30-3F")
    out, k, at = [], 0, areas[0][0]
    for size in sizes:
        while at + size > areas[k][1]:
            k += 1
            if k == len(areas):
                raise ValueError(f"new-map records: {sum(sizes)} bytes do not fit the areas")
            at = areas[k][0]
        out.append(k)
        at += size
    return out


def _span(write):
    bank, addr = (int(v, 16) for v in write["at"].split(":"))
    return bank << 16 | addr, (bank << 16 | addr) + len(bytes.fromhex(write["hex"]))


def splice(writes, extra):
    """Lay each write of `extra` that falls inside one of `writes` over its bytes there (dq5patch/1 write lists,
    `writes` changed in place): a later dq5newmap call rewrites map pointers inside the first call's pointer list,
    which dq5build would refuse as an overlap. Returns the writes of `extra` that touch none of `writes`."""
    rest = []
    for w in extra:
        lo, hi = _span(w)
        inside = [v for v in writes if _span(v)[0] <= lo and hi <= _span(v)[1]]
        if not inside:
            if any(_span(v)[0] < hi and lo < _span(v)[1] for v in writes):
                raise ValueError(f"{w['at']} {w.get('note', '')}: overlaps an earlier write without lying inside it")
            rest.append(w)
            continue
        v = inside[0]
        data = bytearray.fromhex(v["hex"])
        data[lo - _span(v)[0]:hi - _span(v)[0]] = bytes.fromhex(w["hex"])
        v["hex"] = data.hex(" ").upper()
    return rest


def new_map_records(env):
    """{(DQ5 group, map): record bytes} of the GROUPS maps from dq4environmentrom's documents in `env`."""
    from dq5mapwrite import encode
    return {(group, number): encode(json.loads((env / f"{name}.dq5map.json").read_text(encoding="utf-8")))
            for name, (group, number) in GROUPS.items()}


def check_records(rom, records):
    """Each new map's pointer in the built ROM leads to its record (records {(group, map): bytes})."""
    from dq5map import Rom, lorom, map_pointer
    built = Rom(rom)
    for (group, number), record in records.items():
        at = map_pointer(built, group, number)
        if rom[lorom(at):lorom(at) + len(record)] != record:
            raise ValueError(f"{group:02X}/{number:02X}: the map pointer {_cpu(at)} does not lead to its record")


def _cpu(addr):
    return f"{addr >> 16:02X}:{addr & 0xFFFF:04X}"


def check_door_copy(rom, door_bank):
    """The door routines read bank 01's FD97-FEB6 from DOOR_BANK on our maps, and dq4environmentrom copies them
    from the original ROM: the built ROM must still have the same bytes in both banks. dq5newmap's --door-bank must
    be another bank, since it copies all of bank 01 there."""
    if door_bank == DOOR_BANK:
        raise ValueError(f"dq5newmap --door-bank {door_bank:02X} is the dq4 door bank")
    lo, hi = DOOR_TABLES
    here = rom[0x8000 + (lo & 0x7FFF):0x8000 + (hi - 1 & 0x7FFF) + 1]
    there = rom[DOOR_BANK * 0x8000 + (lo & 0x7FFF):DOOR_BANK * 0x8000 + (hi - 1 & 0x7FFF) + 1]
    if here != there:
        at = next(i for i in range(len(here)) if here[i] != there[i]) + lo
        raise ValueError(f"{DOOR_BANK:02X}:{at:04X} differs from 01:{at:04X}: a patch changed bank 01's door tables "
                         "after dq4environmentrom copied them")


def _run(tool, *args):
    return dq4buildcache.run(tool, *args)


def _save(path, doc):
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return path


def map_attrs(dq5, link, zone=None):
    """dq5newmap attrs: a copy of the borrowed map's attributes, with the song byte replaced when "music" is set
    and, for a "dungeon" part, the zones of all three $1948 values set to the DQ5 zone `zone` (None: FF, none)."""
    if "music" not in link and not link.get("dungeon"):
        return {"copy": link["attrs"]}
    import dq5newmap
    from dq5map import Rom
    attrs, _ = dq5newmap.entries(Rom(dq5.read_bytes()), "attr")
    group, number = (int(v, 16) for v in link["attrs"].split("/"))
    row = list(attrs[group][number])
    if "music" in link:
        row[5] = link["music"]
    if link.get("dungeon"):
        row[0:3] = [0xFF if zone is None else zone] * 3
    return {"bytes": row}


def dungeon_zones(prg):
    """{(FC group, FC map): FC zone} of the ported maps of the LINKS "dungeon" parts, from the chapters 1-4 dungeon
    list (18:$A069, indexed by the FC map number); maps without a zone are left out."""
    import dq4encounter
    _, _, recs = dq4encounter.dungeon_lists(prg)[0]
    lists = dict(recs)
    out = {}
    for parts in LINKS.values():
        for part in parts:
            if part.get("dungeon"):
                zones = lists.get(part["fc"], [])
                for k in fc_numbers(prg, part["fc"]):
                    if k < len(zones) and zones[k] != 0xFF:
                        out[part["fc"], k] = zones[k]
    return out


def records_pass(dq5, out, manifests, k, sources):
    """dq5newmap call k (1-): the records {map: dq5map/1 document} at RECORDS_AT[k], made on the ROM of
    `manifests` (the environment and the earlier calls). Its pointer writes go into the first call's list (splice).
    Appends its patch to `manifests`; returns its check."""
    base = out / f"newmap-{k}.sfc"
    _run(DQ5_TOOLS / "dq5build.py", dq5, "build", *manifests, "--size", 4, "-o", base)
    source = _save(out / f"newmap-{k}.json", {"format": "dq5newmap/1", "maps": [
        {"map": m, "record": {"source": doc}} for m, doc in sources.items()]})
    args = ("--records-at", _cpu(RECORDS_AT[k][0]))
    patch = out / f"newmap-{k}.dq5patch.json"
    _run(DQ5_TOOLS / "dq5newmap.py", base, "patch", source, "-o", patch, *args)
    first = json.loads((out / "newmap.dq5patch.json").read_text(encoding="utf-8"))
    doc = json.loads(patch.read_text(encoding="utf-8"))
    doc["writes"] = splice(first["writes"], doc["writes"])
    _save(out / "newmap.dq5patch.json", first)
    _save(patch, doc)
    manifests.append(patch)
    return "dq5newmap.py", source, args


def build(dq5, dq4, out, with_people=True):
    out.mkdir(parents=True, exist_ok=True)
    with _Pool(os.cpu_count()) as pool:
        try:
            return _build(pool, dq5, dq4, out, with_people)
        except BaseException as e:
            # 남은 도구는 돌리지 않고, 함께 실패했지만 아무도 result() 를 부르지 않은 호출도 알린다
            pool.shutdown(cancel_futures=True)
            for f in pool.futures:
                if f.done() and not f.cancelled() and f.exception() not in (None, e):
                    e.add_note(f"also failed: {f.exception()}")
            raise


class _Pool(ThreadPoolExecutor):
    def __init__(self, workers):
        super().__init__(workers)
        self.futures = []

    def submit(self, *args, **kwargs):
        f = super().submit(*args, **kwargs)
        self.futures.append(f)
        return f


def _build(pool, dq5, dq4, out, with_people):
    """Tool calls that need only the original ROM run in `pool` while the others go on; drain() waits for the
    patch lists that a later call reads (a base ROM, --with-patch) or builds."""
    prg = ines.prg(dq4.read_bytes())
    place = placement(prg)
    new_maps = [f"{g:02X}/{n:02X}" for g, n in sorted(GROUPS.values())]
    new_map_args = [a for m in new_maps for a in ("--new-map", m)]
    dumps = {name: pool.submit(_run, DQ5_TOOLS / tool, dq5, "dump", "-o", out / f"{name}.json", *extra)
             for name, tool, extra in (("exits-orig", "dq5exitreloc.py", new_map_args),
                                       ("fieldtables-orig", "dq5fieldtables.py", ()),
                                       ("encounter-orig", "dq5encounterwrite.py", ()),
                                       ("chest-tables-orig", "dq5chestreloc.py", ()))}
    pending = []

    def drain():
        for f in pending:
            f.result()
        pending.clear()

    env = out / "env"
    report = json.loads(_run(TOOLS / "dq4environmentrom.py", "--dq5", dq5, "--dq4", dq4, "--out", env))
    env_rom = out / "env.sfc"
    import dq4door
    # dq4door writes bank 01 too: in the env ROM, so that dq5newmap's door bank copy has it.
    door_patch = _save(out / "doors.dq5patch.json", {"format": "dq5patch/1", "name": "dq4-doors", "writes": dq4door.writes()})
    _run(DQ5_TOOLS / "dq5build.py", dq5, "build", env / "dq4-environment.dq5patch.json", door_patch, "--size", 4,
         "-o", env_rom)

    names = {f"{g:02X}/{n:02X}": name for name, (g, n) in GROUPS.items()}
    records = {f"{g:02X}/{n:02X}": r for (g, n), r in new_map_records(env).items()}
    area = dict(zip(new_maps, record_areas([len(records[m]) for m in new_maps], RECORDS_AT)))
    newmap = {"format": "dq5newmap/1", "groups": [], "maps": []}
    for group, (first, *_) in LINKS.items():
        x, y = cell(*first["arrival"])
        number = place[first["fc"], first.get("map", 0)][1]
        indoor = INDOOR_ENCOUNTERS << 2 if any(part.get("dungeon") for part in LINKS[group]) else 0
        newmap["groups"].append({"group": f"{group:02X}",
                                 "entrance": {"bytes": [WORLD_CODE << 5 | number, x, y, LAYER, indoor]}})
    part_of = {part["fc"]: part for parts in LINKS.values() for part in parts}
    import dq4fieldencounter
    dumps["encounter-orig"].result()
    encounter_orig = json.loads((out / "encounter-orig.json").read_text(encoding="utf-8"))
    fc_zones = dungeon_zones(prg)
    dq5_zone = dq4fieldencounter.dungeon_zones(prg, encounter_orig, fc_zones.values())
    for m in new_maps:
        fc_group, fc_number = fc_map(prg, int(m[:2], 16), int(m[3:], 16))
        record = {"source": f"env/{names[m]}.dq5map.json"} if area[m] == 0 else {"copy": RECORD_PLACEHOLDER}
        zone = dq5_zone.get(fc_zones.get((fc_group, fc_number)))
        newmap["maps"].append({"map": m, "record": record, "attrs": map_attrs(dq5, part_of[fc_group], zone)})
    manifests = [env / "dq4-environment.dq5patch.json", door_patch]

    def step(tool, name, doc, base, *args):
        source = _save(out / f"{name}.json", doc)
        manifest = out / f"{name}.dq5patch.json"
        pending.append(pool.submit(_run, DQ5_TOOLS / tool, base, "patch", source, "-o", manifest, *args))
        manifests.append(manifest)
        return tool, source, args

    # The check of the first call rebuilds its own placeholders, so the maps of later areas are covered only by
    # check_records on the built ROM.
    checks = [step("dq5newmap.py", "newmap", newmap, env_rom, *NEWMAP_AT, "--records-at", _cpu(RECORDS_AT[0][0]))]
    drain()
    record_patches = []
    for k in range(1, max(area.values()) + 1):
        checks.append(records_pass(dq5, out, manifests, k, {m: f"env/{names[m]}.dq5map.json"
                                                            for m in new_maps if area[m] == k}))
        record_patches.append(manifests[-1].name)
    import dq4npcport  # imports this module
    lists, messages, people = dq4npcport.port(dq5, dq4, with_people)
    _save(out / "npc-report.json", people)
    pending.append(pool.submit(
        _run, DQ5_TOOLS / "dq5npcrelocate.py", dq5, "patch",
        _save(out / "npc.json", {"format": "dq5npcrelocate/1", "scripts": [],
                                 "lists": [lst for lst in lists if "map" in lst]}),
        "-o", out / "npc.dq5patch.json", "--report", out / "npc-layout.json", *NPC_AT, *new_map_args))
    manifests.append(out / "npc.dq5patch.json")
    # dq5textwrite appends gap-free from 3200; the Korean chapter 1 and prologue lines before the ported ones go in only
    # with the menu build's tree, so this ROM gets placeholders there
    held = [{"id": m, "codes": dq4npcport.nothing_codes()} for m in range(dq4npcport.MESSAGES, dq4npcport.FIRST_MESSAGE)]
    checks.append(step("dq5textwrite.py", "text", {"format": "dq5text/1", "messages": held + messages}, dq5, *TEXT_AT))
    checks.append(step("dq5talkwrite.py", "talk", dq4npcport.talk_doc(messages), dq5, *TALK_AT))
    import dq4shopport  # imports this module
    _, shops, inn_writes, shop_report = dq4shopport.port(dq5, dq4, INN_AT, SHOP_KEY_AT, with_people)
    _save(out / "shop-report.json", shop_report)
    step("dq5progresswrite.py", "shops", {"format": "dq5progress/1", "shops": shops}, dq5, *SHOP_AT)
    manifests.append(_save(out / "inn.dq5patch.json", {"format": "dq5patch/1", "name": "dq4-inns-shop-keys", "writes": inn_writes}))

    dumps["exits-orig"].result()
    exits = json.loads((out / "exits-orig.json").read_text(encoding="utf-8"))
    ours = {}
    areas = {}
    for group in LINKS:
        ours.update(exit_records(prg, group))
        areas.update(area_records(prg, group))
        for m, rows in (fall_records(prg, group) if group in FALL_GROUPS else {}).items():
            areas[m] = areas.get(m, []) + rows
    for row in exits["exits"]:
        if row["map"] in ours:
            row["records"] = ours[row["map"]]
    have = {row["map"] for row in exits["triggers"]}
    for row in exits["triggers"]:
        if row["map"] in areas:
            row["records"] = areas[row["map"]]
    exits["triggers"] += [{"map": m, "records": r} for m, r in areas.items() if m not in have]
    checks.append(step("dq5exitreloc.py", "exits", exits, dq5, *new_map_args, *EXIT_AT))

    dumps["fieldtables-orig"].result()
    tables = json.loads((out / "fieldtables-orig.json").read_text(encoding="utf-8"))
    worlds = {a["group"]: a for a in tables["arrivals"]}
    entrance_tables = {name: dq4fieldport.park([e for e in tables["entrances"] if e["table"] == name], worlds)
                       for name in ("main", "aux")}
    found = doors(prg)
    import dq4fieldtravel
    destinations = dq4fieldtravel.destinations(prg, LINKS, found)
    entrance_tables["aux"] += dq4fieldtravel.landing_rows(
        [{"group": group, "x": x, "y": y} for group, parts in LINKS.items()
         for part in parts if part["field"] for x, y in found[part["fc"]][0]], destinations)
    step("dq5fieldtables.py", "entrances", {"format": "dq5fieldtables/1", "entrance_tables": entrance_tables}, dq5,
         *ENTRANCES_AT, *new_map_args)
    arrivals, leaving = hook_rows(LINKS, place, found, entrance_doors(prg))
    manifests.append(_save(out / "entrance-hook.dq5patch.json", {
        "format": "dq5patch/1", "name": "dq4-entrance-hook",
        "writes": dq4entrancehook.writes(ENTRANCE_HOOK_AT, arrivals, leaving)}))
    manifests.append(_save(out / "travel.dq5patch.json", {
        "format": "dq5patch/1", "name": "dq4-travel", "writes": dq4fieldtravel.writes(dq5.read_bytes(), destinations)}))
    checks.append(step("dq5namewrite.py", "names", dq4fieldtravel.names_doc(dq5.read_bytes(), destinations), dq5))
    # A doc of its own: one doc writes one span from its first to its last changed byte, which would cover the item
    # names other patches write between tables 0A and 0B.
    checks.append(step("dq5namewrite.py", "companion-names",
                       {"format": "dq5names/1", "tables": [companion_names(dq5.read_bytes())]}, dq5))
    checks.append(step("dq5namewrite.py", "person-names",
                       {"format": "dq5names/1", "tables": [person_names(dq5.read_bytes())]}, dq5))
    zones, grids, zone_report = dq4fieldencounter.docs(prg, dq5.read_bytes(), encounter_orig, fc_zones.values())
    _save(out / "zone-report.json", zone_report)
    step("dq5progresswrite.py", "zones", zones, dq5)
    step("dq5encounterwrite.py", "grids", grids, dq5)
    import dq4balance
    import dq4dungeonrate
    import dq4wellswitch
    manifests.append(_save(out / "rates.dq5patch.json", {
        "format": "dq5patch/1", "name": "dq4-encounter-rates",
        "writes": [dq4fieldencounter.terrain_rates(prg, dq5.read_bytes()),
                   *dq4wellswitch.writes(WELL_SWITCH_AT, prg, placement(prg)),
                   *dq4dungeonrate.writes(DUNGEON_RATE_AT, prg, placement(prg), dq5_zone, fc_zones),
                   *dq4balance.writes()]}))

    import dq4chestport  # imports this module
    place, chest_report = dq4chestport.port(dq5, dq4)
    _save(out / "chest-report.json", chest_report)
    dumps["chest-tables-orig"].result()
    drain()
    base = dq4chestport.base_tables(json.loads((out / "chest-tables-orig.json").read_text(encoding="utf-8")))
    with_patches = [a for m in manifests for a in ("--with-patch", m)]
    checks.append(step("dq5chestplace.py", "chests", place, dq5, *CHEST_AT, "--tables", _save(out / "chest-tables.json", base),
                       *new_map_args, *with_patches))
    manifests += dq4fieldport.patch(dq5, prg, out / "field.dq5patch.json", FIELD_AT)
    drain()

    rom = out / "groups.sfc"
    _run(DQ5_TOOLS / "dq5build.py", dq5, "build", *manifests, "--size", 4, "-o", rom, "--ips", out / "groups.ips")
    check_door_copy(rom.read_bytes(), int(NEWMAP_AT[NEWMAP_AT.index("--door-bank") + 1], 16))
    check_records(rom.read_bytes(), {(int(m[:2], 16), int(m[3:], 16)): r for m, r in records.items()})
    # dq5newmap checks the built ROM; the others build their own from the original.
    list(pool.map(lambda c: _run(DQ5_TOOLS / c[0], rom if c[0] == "dq5newmap.py" else dq5, "check", c[1], *c[2]),
                  checks))
    summary = {"rom": str(rom), "maps": new_maps, "exits": ours, "areas": areas,
               "fields": {tag(g, part): {"entrances": found[part["fc"]][0], "leave": found[part["fc"]][1]}
                          for g, parts in LINKS.items() for part in parts if part["field"]},
               "ruler": destinations, "record_patches": record_patches,
               "record_areas": {m: _cpu(RECORDS_AT[k][0]) for m, k in area.items()},
               "records_end": report["records_end"], "bank01_bytes": report["bank01_bytes"]}
    _save(out / "groups.json", summary)
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dq5", default="rom/dq5.sfc", type=Path)
    ap.add_argument("--dq4", default="rom/dq4.nes", type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--no-people", action="store_true",
                    help="no FC people or shops: a ROM for dq4groupcheck, where wandering people block stairs")
    args = ap.parse_args()
    print(json.dumps(build(args.dq5, args.dq4, args.out, with_people=not args.no_people), ensure_ascii=False))


if __name__ == "__main__":
    main()
