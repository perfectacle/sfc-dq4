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

# DQ5 has no luck stat, so ラックのたね becomes the seed that raises the stat DQ5 has instead. Items DQ5 lacks
# take a DQ5 item of the same kind: a flute for the key item あやかしのふえ until DQ4 key items exist, a hat for
# はねぼうし, a dancer's outfit for ピンクのレオタード (DQ5's てんしのレオタード is a far stronger armour).
SUBSTITUTE = {"ラックのたね": "ふしぎなきのみ", "あやかしのふえ": "はるかぜのフルート", "はねぼうし": "きのぼうし",
              "ピンクのレオタード": "おどりこのふく", "せいじゃくのたま": "まふうじのつえ"}
# せいじゃくのたま 와 まふうじのつえ 는 둘 다 쓰면 マホトーン 이 걸린다. じょうせんけん(ハバリア 의 배를 타는 표)은 DQ5 에
# 같은 것이 없고 쓸 곳(배 이벤트)도 아직 없어, 그 이벤트를 옮길 때까지 빈 상자로 둔다.
LATER = {"じょうせんけん"}
GOLD = 0x100
# FC special chest contents with a DQ5 reward of the same kind: FF, the empty chest (message 0297), is DQ5 FFFF
# 「からっぽだった」.
EMPTY = 0xFFFF
# EE is chapter 3's iron safe (きたのどうくつ 3D/06): FC sets $627D bit3 and turns the cell into block 19 (1E:$B81B).
# DQ5 has no such item, so it opens empty until that event is ported.
SPECIAL = {0xFF: EMPTY, 0xEE: EMPTY}
# E3 은 4장에서 やみのランプ 만 준다(1E:$B9ED, 5장이면 메시지와 이벤트가 이어짐). DQ5 에 같은 이름이 있다.
SPECIAL_ITEMS = {0xE3: "やみのランプ"}
# DQ5 drawer open bits 7E:222C + flag_index: the original table ends at 2236 & FC, 2238 (flag_index 0C) is read
# outside the table and 223C- are the two-cells-ahead chests (dq5-build-format 「보물상자·조사 보상」), so new
# entries take 2237 and 2239-223B.
FLAG_BYTES = (0x0B, 0x0D, 0x0E, 0x0F)


def _reward(names, items, content, gold=True):
    if content & 0x80:
        if not gold:
            raise ValueError(f"FC drawer item {content:02X} is not an item number")
        return GOLD + (content & 0x7F) * 40
    name = names[content]
    if name in LATER:
        return EMPTY
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
            if content in SPECIAL:
                reward = SPECIAL[content]
            elif content in SPECIAL_ITEMS:
                reward = items[_fold(SPECIAL_ITEMS[content])]
            elif content in dq4chest.special_codes(prg, dq4chest.SPECIAL_CHEST):
                raise ValueError(f"{g:02X}/{k:02X} ({x},{y}): special chest {desc}")
            else:
                reward = _reward(names, items, content)
            entry = {"x": 2 * x + 1, "y": 2 * y + 1, "reward": reward}
            maps.setdefault((group, number), {"chests": [], "furniture": []})["chests"].append(entry)
            report.append({"fc": f"{g:02X}/{k:02X} ({x},{y})", "map": f"{group:02X}/{number:02X}", "kind": "chest",
                           "fc_item": desc, "reward": entry["reward"]})
    flags = 0
    for e in dq4block.pots(prg):
        if (e["group"], e["index"]) not in target:
            continue
        group, number = target[e["group"], e["index"]]
        entry = {"x": 2 * e["x"] + 1, "y": 2 * e["y"] + 1, "reward": _reward(names, items, e["item"], gold=False),
                 "flag_index": FLAG_BYTES[flags // 8], "mask": 0x80 >> flags % 8}
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
