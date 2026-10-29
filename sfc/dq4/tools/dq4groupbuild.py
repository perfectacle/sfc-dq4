"""Build the DQ4 environment maps with whole FC groups as new DQ5 groups, linked by their FC exits.

Order matters (sfc/dq4/docs/dq4-environment-format.md, 「그룹 연결」):
  1. dq4environmentrom.py patch -> env ROM. The door table copy made in 2 must contain its bank-01 tail.
  2. dq5newmap.py from the env ROM: new groups, maps (records from the dq5map/1 documents of 1), arrivals.
  3. dq5exitreloc.py, dq5npcrelocate.py (the FC people of dq4npcport.py), dq5fieldtables.py from the original
     ROM with --new-map, dq5textwrite.py with their Japanese FC text, and dq5progresswrite.py with the FC
     shop lists plus the inn price table of dq4shopport.py.
  4. dq5build.py on the original ROM with 1, 2 and 3.

FC stairs (08:$B22E) become same-group exits, FC exit-table cells ($05A0) become area moves, and the map
edge leads to the field through the aux entrance table. Field spots are temporary until the DQ4 field is in.

  python sfc/dq4/tools/dq4groupbuild.py --out work/dq4-groups
"""

import argparse
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
import dq4map  # noqa: E402
from dq4environmentmap import all_maps, block_prop  # noqa: E402
from dq4environmentrom import GROUPS, STAIRS  # noqa: E402
from kr_patch.fc import ines  # noqa: E402

# New DQ5 group -> FC group, the FC arrival from the field ($44/$45 after walking in from the field entrance;
# fc/dq4/tools/dq4field.py entrances lists the same cells) and its map ("map", 0 when absent), the borrowed DQ5 map whose attributes (encounters, battle background, music) it takes,
# the temporary field cell of its entrance, the inputs that take the party from the arrival to the field, and a
# walk from the field cell (341,56) onto the entrance that passes no other entrance. Field steps vary with the
# ground, so the entrances sit where their walks end (measured). "music" replaces the song byte of the copied
# attributes (attribute +5): FC plays one song for the whole group (19:$803B, map branch $07BA), and
# 02 バトランド plays FC song 03, 王宮のメヌエット, which the sound port puts in DQ5 song slot 01.
LINKS = {
    0x36: {"fc": 0x02, "arrival": (0x00, 0x1D), "attrs": "03/00", "music": 0x01, "field": (345, 56), "out": "left:64", "walk": "right:64"},
    0x37: {"fc": 0x12, "arrival": (0x0D, 0x19), "attrs": "19/02", "field": (337, 56), "out": "down:64", "walk": "left:64"},
    # 古井戸の底, the tower of chapter 1's end, and the house of 41/00. Their attributes are a placeholder
    # (the castle's: no encounters) until the DQ4 encounters and music are ported.
    0x38: {"fc": 0x1C, "arrival": (0x0D, 0x10), "attrs": "03/00", "field": (332, 52), "out": "down:64", "walk": "up:64,wait:30,left:64"},
    0x39: {"fc": 0x30, "arrival": (0x10, 0x21), "map": 3, "attrs": "03/00", "field": (349, 62), "out": "down:64",
           "walk": "down:64,wait:30,right:64,wait:30,up:16"},
    # 41/00's arrival is its stair to the field: step off and back on.
    0x3A: {"fc": 0x41, "arrival": (0x03, 0x03), "attrs": "03/00", "field": (333, 64), "out": "down:32,wait:60,up:32",
           "walk": "down:64,wait:30,left:64"},
    # Below 古井戸の底: no field entrance; its group arrival is the cell the well's stair leads to (3A/02).
    0x3B: {"fc": 0x3A, "arrival": (0x03, 0x02), "map": 2, "attrs": "03/00", "field": None, "out": None},
}
# The attribute table grows by 6 bytes a map and outgrows its own bank (108 spare bytes), so it moves whole.
NEWMAP_AT = ("--entrance-table-at", "3C:C000", "--records-at", "34:8000", "--door-bank", "3B",
             "--attr-table-at", "3C:D000")
EXIT_AT = ("--exits-at", "2A:D812", "--records-at", "3C:A000")
ENTRANCES_AT = ("--entrances-at", "3C:8000")
# dq5textwrite writes the whole walking text again, so it takes banks of its own.
TEXT_AT = ("--at", "35:8000")
SHOP_AT = ("--shop-at", "3C:E000")
INN_AT = 0x3CF000
LAYER = 1
WORLD_CODE = 1
AREA_FLAGS = 0x80
# FC direction (0 up, 2 down) -> the DQ5 row of an FC cell the party first steps onto.
ENTRY_ROW = {0: 1, 2: 0}


def cell(x, y):
    """DQ5 cell where the party stands on FC cell (x, y): the bottom-left cell of the 2x2 block, as a
    DQ5 stair arrival (one cell left of the block's bottom-right exit cell)."""
    return x * 2, y * 2 + 1


def fc_numbers(group):
    return sorted(number for g, number in GROUPS.values() if g == group)


def exit_order(prg, fc_group, number):
    """FC stair cells of a map in DQ5 exit order (row-major by the block's bottom-right cell)."""
    source = dq4block.Map(prg, fc_group, number)
    found = [(x, y) for y in range(source.h) for x in range(source.w)
             if block_prop(source, source.cell(x, y) & 31) in STAIRS]
    return sorted(found, key=lambda c: (c[1], c[0]))


def exit_records(prg, group):
    """dq5exittables/1 exit lists of the group's maps from the FC stair links. A stair to another ported FC
    group is an other-group exit, one to the field the special exit 0."""
    fc_group = LINKS[group]["fc"]
    dq5_group = {link["fc"]: g for g, link in LINKS.items()}
    numbers = fc_numbers(group)
    order = {n: exit_order(prg, fc_group, n) for n in numbers}
    cache = {}
    records = {}
    for number in numbers:
        links = dq4block.exit_links(prg, fc_group, number, cache)
        other = sorted({e["prop"] & 0x7F for e in links} - STAIRS)
        if other:
            raise ValueError(f"{fc_group:02X}/{number:02X}: FC exit kinds {[f'{p:02X}' for p in other]} have no DQ5 exit yet")
        to = {(e["x"], e["y"]): e["to"] for e in links}
        rows = []
        for x, y in order[number]:
            dest = to[x, y]
            if dest and "field" in dest:
                # 2A:F7B2 -> 2A:F425: out to the group's field entrance (aux entrance table).
                rows.append({"kind": "special", "special": 0})
                continue
            if not dest or dest.get("group") not in dq5_group or "index" not in dest or \
                    dest["index"] not in fc_numbers(dq5_group[dest["group"]]):
                raise ValueError(f"{fc_group:02X}/{number:02X} ({x:02X},{y:02X}): stair to an FC group not ported: {dest}")
            there = exit_order(prg, dest["group"], dest["index"])
            row = {"kind": "same-group", "destination_map": dest["index"], "exit": there.index((dest["x"], dest["y"]))}
            if dest["group"] != fc_group:
                row = {**row, "kind": "other-group", "group": dq5_group[dest["group"]]}
            rows.append(row)
        records[f"{group:02X}/{number:02X}"] = rows or [{"kind": "special", "special": 0}]
    return records


def area_records(prg, group):
    """Area moves from the FC exit table ($05A0). Neighbouring FC cells with the same destination share
    one rect. The rect is one DQ5 row: a taller rect maps the arrival Y in proportion with a negative span
    (2A:F636 -> F67C), a one-row rect maps X across span_raw cells (F650). The row is the first one the party
    steps onto, walking in the arrival flag's direction (an FC exit below the map edge must catch the party
    on that first outside row, before the field exit 2A:F425); X holds the party's left cell on the cells. The arrival is the FC arrival cell; the engine then takes one more step in the
    walking direction (2A:F69F), which carries the party off a destination cell that is itself an exit
    (02/01 -> the 02/00 gate)."""
    fc_group = LINKS[group]["fc"]
    out = {}
    for number in fc_numbers(group):
        cells = sorted(dq4map.exits(prg, fc_group, number), key=lambda e: (e[1], e[0]))
        runs = []
        for x, y, dg, dk, ax, ay, flag in cells:
            if dg != fc_group:
                raise ValueError(f"{fc_group:02X}/{number:02X} ({x:02X},{y:02X}) leaves the group")
            last = runs[-1] if runs else None
            if last and last["y"] == y and last["x1"] + 1 == x and last["to"] == (dk, ay, flag) \
                    and last["ax1"] + 1 == ax:
                last["x1"], last["ax1"] = x, ax
            else:
                runs.append({"x0": x, "x1": x, "y": y, "to": (dk, ay, flag), "ax0": ax, "ax1": ax})
        rows = []
        for run in runs:
            dk, ay, flag = run["to"]
            if flag & 3 not in ENTRY_ROW:
                raise ValueError(f"{fc_group:02X}/{number:02X}: sideways exit needs a vertical area rect")
            left, row = run["x0"] * 2, run["y"] * 2 + ENTRY_ROW[flag & 3]
            right, _ = cell(run["x1"], run["y"])
            dx, dy = cell(run["ax0"], ay)
            rows.append({"rect": [left, row, right + 1, row + 1], "source_layer": LAYER, "flags": AREA_FLAGS,
                         "destination_group": group, "destination_map": dk, "x": dx, "y": dy,
                         "span_raw": right - left + 1, "destination_layer": LAYER})
        if rows:
            out[f"{group:02X}/{number:02X}"] = rows
    return out


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


def check_groups(prg):
    """GROUPS must keep the FC map number as the DQ5 map number of the group's LINKS entry: exits are
    written with FC map numbers."""
    fc = {name: (g, k) for g, k, _, name in all_maps(prg)}
    for name, (group, number) in GROUPS.items():
        want = (LINKS[group]["fc"], number) if group in LINKS else None
        if fc.get(name) != want:
            raise ValueError(f"{name}: FC map {fc.get(name)} is not {want} for group {group:02X}")


def build(dq5, dq4, out):
    out.mkdir(parents=True, exist_ok=True)
    prg = ines.prg(dq4.read_bytes())
    check_groups(prg)
    env = out / "env"
    report = json.loads(_run(TOOLS / "dq4environmentrom.py", "--dq5", dq5, "--dq4", dq4, "--out", env))
    env_rom = out / "env.sfc"
    _run(DQ5_TOOLS / "dq5build.py", dq5, "build", env / "dq4-environment.dq5patch.json", "--size", 4, "-o", env_rom)

    new_maps = [f"{g:02X}/{n:02X}" for g, n in sorted(GROUPS.values())]
    new_map_args = [a for m in new_maps for a in ("--new-map", m)]
    names = {f"{g:02X}/{n:02X}": name for name, (g, n) in GROUPS.items()}
    newmap = {"format": "dq5newmap/1", "groups": [], "maps": []}
    for group, link in LINKS.items():
        x, y = cell(*link["arrival"])
        newmap["groups"].append({"group": f"{group:02X}",
                                 "entrance": {"bytes": [WORLD_CODE << 5 | link.get("map", 0), x, y, LAYER, 0]}})
    for m in new_maps:
        group = int(m[:2], 16)
        newmap["maps"].append({"map": m, "record": {"source": f"env/{names[m]}.dq5map.json"},
                               "attrs": map_attrs(dq5, LINKS[group])})
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
    import dq4shopport  # imports this module
    _, shops, inn_writes, shop_report = dq4shopport.port(dq5, dq4, INN_AT)
    _save(out / "shop-report.json", shop_report)
    step("dq5progresswrite.py", "shops", {"format": "dq5progress/1", "shops": shops}, dq5, *SHOP_AT)
    manifests.append(_save(out / "inn.dq5patch.json", {"format": "dq5patch/1", "name": "dq4-inns", "writes": inn_writes}))

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
    aux = [{k: e[k] for k in ("group", "x", "y")} for e in tables["entrances"] if e["table"] == "aux"]
    aux += [{"group": group, "x": link["field"][0], "y": link["field"][1]} for group, link in LINKS.items()
            if link["field"]]
    step("dq5fieldtables.py", "entrances", {"format": "dq5fieldtables/1", "entrance_tables": {"aux": aux}}, dq5,
         *ENTRANCES_AT, *new_map_args)

    rom = out / "groups.sfc"
    _run(DQ5_TOOLS / "dq5build.py", dq5, "build", *manifests, "--size", 4, "-o", rom, "--ips", out / "groups.ips")
    # dq5newmap checks the built ROM; dq5exitreloc and dq5textwrite build their own from the original.
    for tool, source, args in checks:
        _run(DQ5_TOOLS / tool, rom if tool == "dq5newmap.py" else dq5, "check", source, *args)
    summary = {"rom": str(rom), "maps": new_maps, "exits": ours, "areas": areas,
               "fields": {f"{g:02X}": link["field"] for g, link in LINKS.items() if link["field"]},
               "records_end": report["records_end"], "bank01_bytes": report["bank01_bytes"]}
    _save(out / "groups.json", summary)
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dq5", default="rom/dq5.sfc", type=Path)
    ap.add_argument("--dq4", default="rom/dq4.nes", type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    print(json.dumps(build(args.dq5, args.dq4, args.out), ensure_ascii=False))


if __name__ == "__main__":
    main()
