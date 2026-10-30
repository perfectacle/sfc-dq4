"""Build the DQ4 environment maps with whole FC groups in new DQ5 groups, linked by their FC exits.

Order matters (sfc/dq4/docs/dq4-environment-format.md, 「그룹 연결」):
  1. dq4environmentrom.py patch -> env ROM. dq5newmap.py check wants the door table copy made in 2 to match
     bank 01 from 01:F037 on, so the copy must contain the hook stubs of the bank-01 tail.
  2. dq5newmap.py from the env ROM: new groups, maps (records from the dq5map/1 documents of 1), arrivals.
  3. dq5exitreloc.py, dq5npcrelocate.py (the FC people of dq4npcport.py), dq5fieldtables.py from the original
     ROM with --new-map, dq5textwrite.py with their Japanese FC text, and dq5progresswrite.py with the FC
     shop lists plus the inn price table and the per-FC-group shop key hook of dq4shopport.py, and
     dq5talkwrite.py with the talk scripts that show the people's messages (dq4npcport.talk_doc).
  4. dq5chestplace.py from the original ROM with the patches of 1-3 (--with-patch): the FC chests and
     タンス·つぼ of dq4chestport.py on the cells 1 gave their DQ5 attributes.
  5. dq4fieldport.py: FC field 0 as DQ5 world 0 (dq5fieldwrite.py).
  6. dq5build.py on the original ROM with 1-5.

FC stairs (08:$B22E) become same-group exits, FC exit-table cells ($05A0) become area moves, and the map
edge leads to the field through the aux entrance table, onto the FC entrance of the group. The original DQ5
entrances of world 0 move off the FC ground (dq4fieldport.park).

  python sfc/dq4/tools/dq4groupbuild.py --out work/dq4-groups
"""

import argparse
import functools
import json
import subprocess
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
# in DQ5 song slot 01. The DQ5 group's own arrival (the dq5newmap entrance) is its first FC group's.
LINKS = {
    0x36: [{"fc": 0x02, "arrival": (0x00, 0x1D), "attrs": "03/00", "music": 0x01, "field": [(0xA4, 0x2E)],
            "out": "left:64"}],
    # 마을 곡: 19/02 의 곡 바이트 07 은 사운드 포팅에서 楽しいカジノ 자리라, FC 마을 곡 0C 街でのひととき 가 든 06 으로
    0x37: [{"fc": 0x12, "arrival": (0x0D, 0x19), "attrs": "19/02", "music": 0x06, "field": [(0x9A, 0x16)], "out": "down:64"}],
    # 古井戸の底, the tower of chapter 1's end, and the house of 41/00. Their attributes are a placeholder
    # (the castle's: no encounters) until the DQ4 encounters and music are ported.
    0x38: [{"fc": 0x1C, "arrival": (0x0D, 0x10), "attrs": "03/00", "field": [(0xA2, 0x1A)], "out": "down:64"}],
    0x39: [{"fc": 0x30, "arrival": (0x10, 0x21), "map": 3, "attrs": "03/00", "field": [(0x88, 0x17)],
            "out": "down:64"}],
    # 41/00's arrival is its stair to the field: step off and back on. FC enters it from two caves.
    0x3A: [{"fc": 0x41, "arrival": (0x03, 0x03), "attrs": "03/00", "field": [(0x8D, 0x1B), (0x8D, 0x1F)],
            "out": "down:32,wait:60,up:32"}],
    # Below 古井戸の底: no field entrance; its group arrival is the cell the well's stair leads to (3A/02).
    0x3B: [{"fc": 0x3A, "arrival": (0x03, 0x02), "map": 2, "attrs": "03/00", "field": None, "out": None}],
    # The prologue's village (FC 14/00). The field leads to the ruined 14/02, so this arrival is the same cell
    # of 14/00. The prologue places its own people: the FC people of 14/00 belong to chapter 5's start.
    0x3C: [{"fc": 0x14, "arrival": (0x0C, 0x18), "attrs": "19/02", "music": 0x06, "field": [(0x91, 0x31)], "out": "down:64",
            "people": False}],
    # Chapter 2: サントハイム castle, テンペ and フレノール. フレノール's FC arrival is on the map's top row.
    0x3D: [{"fc": 0x01, "arrival": (0x0F, 0x1B), "attrs": "03/00", "field": [(0x27, 0x49)], "out": "down:64"},
           {"fc": 0x0E, "arrival": (0x0A, 0x2C), "attrs": "03/00", "field": [(0x47, 0x39)], "out": "down:64"},
           {"fc": 0x0F, "arrival": (0x16, 0x00), "attrs": "03/00", "field": [(0x60, 0x28)], "out": "up:64"}],
}
# The attribute table grows by 6 bytes a map and outgrows its own bank (108 spare bytes), so it moves whole.
NEWMAP_AT = ("--entrance-table-at", "3C:C000", "--records-at", "34:8000", "--door-bank", "3B",
             "--attr-table-at", "3C:D000")
EXIT_AT = ("--exits-at", "2A:D812", "--records-at", "3C:A000")
ENTRANCES_AT = ("--entrances-at", "3C:8000")
# dq5textwrite writes the whole walking text again, so it takes banks of its own.
TEXT_AT = ("--at", "35:8000")
# Talk scripts 900- (the prologue's and the ported people's, dq4npcport.talk_doc). Bank 30-3F: the hook reads
# them with DB set to their bank. Between the shop lists and the inn table: in the chapter-1 ROM bank 3A is full of
# new-map records.
TALK_AT = ("--extra-at", "3C:E800", "--hook-at", "06:FE10")
SHOP_AT = ("--shop-at", "3C:E000")
INN_AT = 0x3CF000
ENTRANCE_HOOK_AT = 0x3CF800
SHOP_KEY_AT = 0x3CFC00
# The three tables chests and drawers grow; dq5chestplace reads chest_maps and search with DB, so bank 00-3F.
CHEST_AT = ("--chests-at", "3C:8400", "--chest-maps-at", "3C:8800", "--search-at", "3C:8C00")
# The field loader reads both RLE chunks with DB set to their bank, so 30-3F; bank 3A is free in this build.
FIELD_AT = "3A:8000"
LAYER = 1
WORLD_CODE = 1
AREA_FLAGS = 0x80
# FC direction (0 up, 2 down) -> the DQ5 row of an FC cell the party first steps onto.
ENTRY_ROW = {0: 1, 2: 0}


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


def has_people(fc_group):
    """Whether the FC people and shops of an FC group are ported (LINKS "people", on by default)."""
    return all(part.get("people", True) for parts in LINKS.values() for part in parts if part["fc"] == fc_group)


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


def hook_rows(links, place, entrances):
    """dq4entrancehook (arrivals, leaving) of every FC group with a field entrance: each of its entrance cells
    (entrances[FC group] = (cells, leave cell), as doors) leads to its arrival, and its maps leave onto the leave
    cell. A DQ5 group of one FC group leaves from any map."""
    arrivals, leaving = [], []
    for group, parts in links.items():
        for part in parts:
            if not part["field"]:
                continue
            found, (lx, ly) = entrances[part["fc"]]
            for fx, fy in found:
                arrivals.append((group, fx, fy, place[part["fc"], part.get("map", 0)][1], *cell(*part["arrival"]),
                                 LAYER, 0))
            numbers = [n for (g, _), (_, n) in place.items() if g == part["fc"]]
            first, last = (0, 0x1F) if len(parts) == 1 else (min(numbers), max(numbers))
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
                row = {"kind": "same-group", "destination_map": there_number, "exit": there.index((dest["x"], dest["y"]))}
                if there_group != group:
                    row = {**row, "kind": "other-group", "group": there_group}
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
            if flag & 3 not in ENTRY_ROW:
                raise ValueError(f"{fc_group:02X}/{number:02X}: sideways exit needs a vertical area rect")
            left, row = run["x0"] * 2, run["y"] * 2 + ENTRY_ROW[flag & 3]
            right, _ = cell(run["x1"], run["y"])
            dx, dy = cell(run["ax0"], ay)
            rows.append({"rect": [left, row, right + 1, row + 1], "source_layer": LAYER, "flags": AREA_FLAGS,
                         "destination_group": group, "destination_map": place[dg, dk][1], "x": dx, "y": dy,
                         "span_raw": right - left + 1, "destination_layer": LAYER})
        if rows:
            out[f"{group:02X}/{place[fc_group, number][1]:02X}"] = rows
    return out


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
    proc = subprocess.run([sys.executable, str(tool), *map(str, args)], capture_output=True, text=True)
    if proc.returncode:
        raise RuntimeError(f"{Path(tool).name} {' '.join(map(str, args[:2]))}: {proc.stderr[-1500:]}")
    return proc.stdout


def _save(path, doc):
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return path


def map_attrs(dq5, link):
    """dq5newmap attrs: a copy of the borrowed map's attributes, with the song byte replaced when "music" is set."""
    if "music" not in link:
        return {"copy": link["attrs"]}
    import dq5newmap
    from dq5map import Rom
    attrs, _ = dq5newmap.entries(Rom(dq5.read_bytes()), "attr")
    group, number = (int(v, 16) for v in link["attrs"].split("/"))
    row = list(attrs[group][number])
    row[5] = link["music"]
    return {"bytes": row}


def build(dq5, dq4, out):
    out.mkdir(parents=True, exist_ok=True)
    prg = ines.prg(dq4.read_bytes())
    place = placement(prg)
    env = out / "env"
    report = json.loads(_run(TOOLS / "dq4environmentrom.py", "--dq5", dq5, "--dq4", dq4, "--out", env))
    env_rom = out / "env.sfc"
    _run(DQ5_TOOLS / "dq5build.py", dq5, "build", env / "dq4-environment.dq5patch.json", "--size", 4, "-o", env_rom)

    new_maps = [f"{g:02X}/{n:02X}" for g, n in sorted(GROUPS.values())]
    new_map_args = [a for m in new_maps for a in ("--new-map", m)]
    names = {f"{g:02X}/{n:02X}": name for name, (g, n) in GROUPS.items()}
    newmap = {"format": "dq5newmap/1", "groups": [], "maps": []}
    for group, (first, *_) in LINKS.items():
        x, y = cell(*first["arrival"])
        number = place[first["fc"], first.get("map", 0)][1]
        newmap["groups"].append({"group": f"{group:02X}",
                                 "entrance": {"bytes": [WORLD_CODE << 5 | number, x, y, LAYER, 0]}})
    part_of = {part["fc"]: part for parts in LINKS.values() for part in parts}
    for m in new_maps:
        fc_group, _ = fc_map(prg, int(m[:2], 16), int(m[3:], 16))
        newmap["maps"].append({"map": m, "record": {"source": f"env/{names[m]}.dq5map.json"},
                               "attrs": map_attrs(dq5, part_of[fc_group])})
    manifests = [env / "dq4-environment.dq5patch.json"]

    def step(tool, name, doc, base, *args):
        source = _save(out / f"{name}.json", doc)
        manifest = out / f"{name}.dq5patch.json"
        _run(DQ5_TOOLS / tool, base, "patch", source, "-o", manifest, *args)
        manifests.append(manifest)
        return tool, source, args

    checks = [step("dq5newmap.py", "newmap", newmap, env_rom, *NEWMAP_AT)]
    import dq4npcport  # imports this module
    lists, messages, people = dq4npcport.port(dq5, dq4)
    _save(out / "npc-report.json", people)
    _run(DQ5_TOOLS / "dq5npcrelocate.py", dq5, "patch",
         _save(out / "npc.json", {"format": "dq5npcrelocate/1", "scripts": [], "lists": lists}),
         "-o", out / "npc.dq5patch.json", "--report", out / "npc-layout.json", *new_map_args)
    manifests.append(out / "npc.dq5patch.json")
    checks.append(step("dq5textwrite.py", "text", {"format": "dq5text/1", "messages": messages}, dq5, *TEXT_AT))
    checks.append(step("dq5talkwrite.py", "talk", dq4npcport.talk_doc(messages), dq5, *TALK_AT))
    import dq4shopport  # imports this module
    _, shops, inn_writes, shop_report = dq4shopport.port(dq5, dq4, INN_AT, SHOP_KEY_AT)
    _save(out / "shop-report.json", shop_report)
    step("dq5progresswrite.py", "shops", {"format": "dq5progress/1", "shops": shops}, dq5, *SHOP_AT)
    manifests.append(_save(out / "inn.dq5patch.json", {"format": "dq5patch/1", "name": "dq4-inns-shop-keys", "writes": inn_writes}))

    _run(DQ5_TOOLS / "dq5exitreloc.py", dq5, "dump", "-o", out / "exits-orig.json", *new_map_args)
    exits = json.loads((out / "exits-orig.json").read_text(encoding="utf-8"))
    ours = {}
    areas = {}
    for group in LINKS:
        ours.update(exit_records(prg, group))
        areas.update(area_records(prg, group))
    for row in exits["exits"]:
        if row["map"] in ours:
            row["records"] = ours[row["map"]]
    have = {row["map"] for row in exits["triggers"]}
    for row in exits["triggers"]:
        if row["map"] in areas:
            row["records"] = areas[row["map"]]
    exits["triggers"] += [{"map": m, "records": r} for m, r in areas.items() if m not in have]
    checks.append(step("dq5exitreloc.py", "exits", exits, dq5, *new_map_args, *EXIT_AT))

    _run(DQ5_TOOLS / "dq5fieldtables.py", dq5, "dump", "-o", out / "fieldtables-orig.json")
    tables = json.loads((out / "fieldtables-orig.json").read_text(encoding="utf-8"))
    worlds = {a["group"]: a for a in tables["arrivals"]}
    entrance_tables = {name: dq4fieldport.park([e for e in tables["entrances"] if e["table"] == name], worlds)
                       for name in ("main", "aux")}
    found = doors(prg)
    entrance_tables["aux"] += [{"group": group, "x": x, "y": y} for group, parts in LINKS.items()
                               for part in parts if part["field"] for x, y in found[part["fc"]][0]]
    step("dq5fieldtables.py", "entrances", {"format": "dq5fieldtables/1", "entrance_tables": entrance_tables}, dq5,
         *ENTRANCES_AT, *new_map_args)
    arrivals, leaving = hook_rows(LINKS, place, found)
    manifests.append(_save(out / "entrance-hook.dq5patch.json", {
        "format": "dq5patch/1", "name": "dq4-entrance-hook",
        "writes": dq4entrancehook.writes(ENTRANCE_HOOK_AT, arrivals, leaving)}))

    import dq4chestport  # imports this module
    place, chest_report = dq4chestport.port(dq5, dq4)
    _save(out / "chest-report.json", chest_report)
    _run(DQ5_TOOLS / "dq5chestreloc.py", dq5, "dump", "-o", out / "chest-tables-orig.json")
    base = dq4chestport.base_tables(json.loads((out / "chest-tables-orig.json").read_text(encoding="utf-8")))
    with_patches = [a for m in manifests for a in ("--with-patch", m)]
    checks.append(step("dq5chestplace.py", "chests", place, dq5, *CHEST_AT, "--tables", _save(out / "chest-tables.json", base),
                       *new_map_args, *with_patches))
    manifests.append(dq4fieldport.patch(dq5, prg, out / "field.dq5patch.json", FIELD_AT))

    rom = out / "groups.sfc"
    _run(DQ5_TOOLS / "dq5build.py", dq5, "build", *manifests, "--size", 4, "-o", rom, "--ips", out / "groups.ips")
    check_door_copy(rom.read_bytes(), int(NEWMAP_AT[NEWMAP_AT.index("--door-bank") + 1], 16))
    # dq5newmap checks the built ROM; the others build their own from the original.
    for tool, source, args in checks:
        _run(DQ5_TOOLS / tool, rom if tool == "dq5newmap.py" else dq5, "check", source, *args)
    summary = {"rom": str(rom), "maps": new_maps, "exits": ours, "areas": areas,
               "fields": {tag(g, part): {"entrances": found[part["fc"]][0], "leave": found[part["fc"]][1]}
                          for g, parts in LINKS.items() for part in parts if part["field"]},
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
    if args.no_people:
        for parts in LINKS.values():
            for part in parts:
                part["people"] = False
    print(json.dumps(build(args.dq5, args.dq4, args.out), ensure_ascii=False))


if __name__ == "__main__":
    main()
