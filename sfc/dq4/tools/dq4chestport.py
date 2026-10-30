"""FC DQ4 chests and タンス·つぼ of the new DQ5 groups (dq4environmentrom.GROUPS) as a dq5chestplace/1 input.

dq4environmentrom gives FC chest blocks the DQ5 chest attribute (+7 = 84) and FC search cells (AB, AA) the
タンス (+4 = 93) and ツボ (+7 = A7) attributes, so the cells are already in the map records: every entry is
written without a block (dq5-build-format 「새 맵의 상자」). An FC cell (x, y) is the DQ5 2x2 block at
(2x, 2y); the attribute is in its bottom-right cell. FC items are matched to DQ5 items by name; gold is
(content & 7F) * 40 as in FC (1E:$B4CE).

  python sfc/dq4/tools/dq4chestport.py --out work/dq4-chests
"""

import argparse
import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
DQ5_TOOLS = TOOLS.parents[1] / "dq5" / "tools"
FC_TOOLS = TOOLS.parents[2] / "fc" / "dq4" / "tools"
for path in (TOOLS, DQ5_TOOLS, FC_TOOLS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import dq4block  # noqa: E402
import dq4chest  # noqa: E402
import dq4shop  # noqa: E402
import dq5item  # noqa: E402
from dq4environmentrom import TARGETS  # noqa: E402
from dq4groupbuild import placement  # noqa: E402
from dq4shopport import _fold, dq5_items  # noqa: E402
from kr_patch.fc import ines  # noqa: E402

# DQ5 has no luck stat, so ラックのたね becomes the seed that raises the stat DQ5 has instead.
SUBSTITUTE = {"ラックのたね": "ふしぎなきのみ"}
GOLD = 0x100
# DQ5 drawer open bits 7E:222C + flag_index: the original table ends at 2236 & FC, and 2238 (flag_index 0C)
# is read outside the table (dq5-build-format 「보물상자·조사 보상」), so new entries start at 2237.
FIRST_FLAG = 0x0B


def _reward(names, items, content, gold=True):
    if content & 0x80:
        if not gold:
            raise ValueError(f"FC drawer item {content:02X} is not an item number")
        return GOLD + (content & 0x7F) * 40
    name = names[content]
    name = SUBSTITUTE.get(name, name)
    if _fold(name) not in items:
        raise ValueError(f"no DQ5 item named {name}")
    return items[_fold(name)]


def port(dq5_path, dq4_path):
    """(dq5chestplace/1 document, report rows)."""
    prg = ines.prg(Path(dq4_path).read_bytes())
    items = dq5_items(dq5item.Rom(Path(dq5_path).read_bytes()))
    names, _ = dq4shop.item_names(prg)
    target = placement(prg)
    maps, report = {}, []
    for (g, k), (group, number) in sorted(target.items(), key=lambda kv: kv[1]):
        for _, x, y, content, desc in dq4chest.chests(prg, g, k):
            if content in dq4chest.special_codes(prg, dq4chest.SPECIAL_CHEST):
                raise ValueError(f"{g:02X}/{k:02X} ({x},{y}): special chest {desc}")
            entry = {"x": 2 * x + 1, "y": 2 * y + 1, "reward": _reward(names, items, content)}
            maps.setdefault((group, number), {"chests": [], "furniture": []})["chests"].append(entry)
            report.append({"fc": f"{g:02X}/{k:02X} ({x},{y})", "map": f"{group:02X}/{number:02X}", "kind": "chest",
                           "fc_item": desc, "reward": entry["reward"]})
    flags = 0
    for e in dq4block.pots(prg):
        if (e["group"], e["index"]) not in target:
            continue
        group, number = target[e["group"], e["index"]]
        entry = {"x": 2 * e["x"] + 1, "y": 2 * e["y"] + 1, "reward": _reward(names, items, e["item"], gold=False),
                 "flag_index": FIRST_FLAG + flags // 8, "mask": 0x80 >> flags % 8}
        flags += 1
        maps.setdefault((group, number), {"chests": [], "furniture": []})["furniture"].append(entry)
        report.append({"fc": f"{e['group']:02X}/{e['index']:02X} ({e['x']},{e['y']})", "map": f"{group:02X}/{number:02X}",
                       "kind": "furniture", "fc_item": names[e["item"]], "reward": entry["reward"]})
    doc = {"format": "dq5chestplace/1",
           "maps": [{"map": f"{g:02X}/{n:02X}", **{k: v for k, v in m.items() if v}} for (g, n), m in sorted(maps.items())]}
    return doc, report


def base_tables(tables):
    """The original chest tables (dq5chestreloc dump) without the DQ5 maps whose records dq4environmentrom
    replaces (TARGETS). Their blocks carry no attributes, so the chest and drawer cells are gone, and
    dq5chestplace refuses a map whose chest cells differ from its count or a drawer entry off a furniture cell.
    The two-cells-ahead rows stay: they are found by coordinates, not cells, and 03/0B (13,16) owns 223D & 20,
    which 12:ADB0 reads."""
    slots = set(TARGETS.values())
    chests, maps, start = [], [], 0
    for row in tables["chest_maps"]:
        if (row["group"], row["map"]) not in slots:
            maps.append(row)
            chests += tables["chests"][start:start + row["count"]]
        start += row["count"]
    return {**tables, "chests": chests, "chest_maps": maps,
            "search": [e for e in tables["search"] if (e["group"], e["map"]) not in slots]}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dq5", default="rom/dq5.sfc")
    ap.add_argument("--dq4", default="rom/dq4.nes")
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    doc, report = port(args.dq5, args.dq4)
    (args.out / "place.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
