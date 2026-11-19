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
from dq4itemport import FLUTE, IRON_SAFE, STATUE  # noqa: E402
from dq4shopport import _fold, dq5_items  # noqa: E402
from kr_patch.fc import ines  # noqa: E402

# Items DQ5 lacks
# take a DQ5 item of the same kind: a dancer's outfit for ピンクのレオタード (DQ5's てんしのレオタード is a far stronger armour), and the commonest herb for the joke
# うまのふん. はねぼうし and ラックのたね have a borrowed slot (dq4itemport.BORROWED), and chapter 2's story items slots of their own
# (dq4itemport.EVENT_ITEMS), あやかしのふえ among them (EVENT_CHEST_ITEMS).
SUBSTITUTE = {"ピンクのレオタード": "おどりこのふく", "せいじゃくのたま": "まふうじのつえ", "うまのふん": "やくそう"}
# せいじゃくのたま 와 まふうじのつえ 는 둘 다 쓰면 マホトーン 이 걸린다. じょうせんけん(ハバリア 의 배를 타는 표)은 DQ5 에
# 같은 것이 없고 쓸 곳(배 이벤트)도 아직 없어, 그 이벤트를 옮길 때까지 빈 상자로 둔다.
LATER = {"じょうせんけん"}
# 3장 은의 여신상 동굴 40/05 (06,04)의 ぎんのめがみぞう 는 엔돌 수집가에게 파는 사건 물건(dq4ch3endor)이다
EVENT_CHEST_ITEMS = {"ぎんのめがみぞう": STATUE, "あやかしのふえ": FLUTE}
# 2장 산트하임 01/00 상자의 あやかしのふえ 는 사건 물건 자리(dq4itemport.FLUTE)
GOLD = 0x100
# FC special chest contents with a DQ5 reward of the same kind: FF, the empty chest (message 0297), is DQ5 FFFF
# 「からっぽだった」.
EMPTY = 0xFFFF
# EE is chapter 3's iron safe (きたのどうくつ 3D/06, 1E:$B81B), the story item of its own slot. Putting it back
# (dq4ch3safe) clears this chest's open bit.
SPECIAL = {0xFF: EMPTY, 0xEE: IRON_SAFE}
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
    if name in EVENT_CHEST_ITEMS:
        return EVENT_CHEST_ITEMS[name]
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
    for (group, number), x, y, reward, desc in look_up_feet(prg, items, target):
        entry = {"x": x, "y": y, "reward": reward, "flag_index": FLAG_BYTES[flags // 8], "mask": 0x80 >> flags % 8}
        flags += 1
        maps.setdefault((group, number), {"chests": [], "furniture": []})["furniture"].append(entry)
        report.append({"fc": desc, "map": f"{group:02X}/{number:02X}", "kind": "furniture", "fc_item": desc,
                       "reward": reward})
    doc = {"format": "dq5chestplace/1",
           "maps": [{"map": f"{g:02X}/{n:02X}", **{k: v for k, v in m.items() if v}} for (g, n), m in sorted(maps.items())]}
    return doc, report


# 일반 상자 열림 비트는 상자 표 차례로 2210 부터 매기므로, 5장에서 상자 193번째가 아래층 상자 비트(2228·2229)에 닿았다.
# 아래층 상자를 어느 표도 쓰지 않는 2243·2244 로 옮겨 일반 상자를 222B 까지(224개) 받는다.
LOWER_SHIFT = 0x1B


# FC 발밑 숨은 물건(fc dq4chest.feet_items) 가운데 물건·금화를 주는 것을 옮기는 장(뒤 장 맵은 그 장을 옮길 때 화면으로
# 확인하며 넣는다. 문서 「남은 것」 에 뒤 장 줄이 있다)
FEET_CHAPTERS = (1, 2, 3)
# 「그 칸에서 조사」(내용 00~7F, A0~AA 는 1E:$BF4F 표의 물건·금화)는 DQ5 발밑 표(12:E6BE: 선 칸과 그 위·오른쪽 위·오른쪽 칸)의
# (2x, 2y+1) — 일행이 FC (x, y) 에 선 DQ5 칸(dq4groupbuild.cell)이라 그 칸에 섰을 때만 걸린다
FOOT_LAYER = 1                                 # 새 그룹 실내 맵의 주인공 층($C3)
# 「위를 보면」(E5~E9, 1E:$B917·B94B·B964·B97D)은 FC 에서 바로 위 칸의 물건 없는 つぼ·タンス 를 보고 조사하는 것이라, 그 가구
# 칸에 서랍 표 항목으로 둔다(DQ5 조사는 가구를 두 칸 앞 표보다 먼저 찾아, 두 칸 앞 표로는 빈 つぼ 가 가로막았다)
FEET_LOOK_UP = {0xE9: "すばやさのたね", 0xE7: "かわのよろい", 0xE6: "やくそう", 0xE5: 50}
# 발밑 표는 칸 수를 늘리면 옮길 자리가 필요해, DQ4 가 쓰지 않는 DQ5 맵의 ちいさなメダル 등 물건 줄을 차례로 덮고 그 줄의
# 열림 비트(7E:2240 + flag_index)를 물려받는다(DQ4 는 그 DQ5 맵에 가지 않아 1·2장 기록에서 0). 2240~2242 를 표 밖에서 읽는
# 명령은 없다(06:B4BE·BAEB·D9A6 의 0C 22xx 는 BRK 0C 의 피연산자). 뒤 장은 이 목록의 남은 줄부터 쓴다
FREE_FOOT = (0, 4, 9, 10, 11, 12, 15, 16, 17)


def _chapter(group):
    import dq4groupbuild
    return min(p.get("chapter") or 1 for p in dq4groupbuild.LINKS[group])


def _feet(prg, target):
    for g, k, x, y, c, desc, _ in dq4chest.feet_items(prg):
        if (g, k) in target and _chapter(target[g, k][0]) in FEET_CHAPTERS:
            yield target[g, k], x, y, c, f"{g:02X}/{k:02X} ({x},{y}) {desc}"


def look_up_feet(prg, items, target):
    """[(DQ5 맵, x, y, 보상, 설명)]: 「위를 보면」 발밑 물건을 그 위 FC 칸(가구) (x, y−1) 의 DQ5 가구 칸 (2x+1, 2y−1) 에."""
    out = []
    for there, x, y, c, desc in _feet(prg, target):
        if c in FEET_LOOK_UP:
            gift = FEET_LOOK_UP[c]
            reward = GOLD + gift if isinstance(gift, int) else items[_fold(gift)]
            out.append((there, 2 * x + 1, 2 * (y - 1) + 1, reward, desc))
    return out


def feet(dq5_path, dq4_path):
    """{'foot': [줄]}: 옮긴 1~3장 맵의 FC 발밑 물건(그 칸에서 조사)을 dq5chesttables/1 발밑 줄로."""
    prg = ines.prg(Path(dq4_path).read_bytes())
    items = dq5_items(dq5item.Rom(Path(dq5_path).read_bytes()))
    names, _ = dq4shop.item_names(prg)
    out = {"foot": []}
    for (group, number), x, y, c, _ in _feet(prg, placement(prg)):
        if c < 0x80 or 0xA0 <= c < 0xAB:
            it = c if c < 0x80 else dq4chest.rd(prg, dq4chest.CHEST_BANK, dq4chest.FLAG_ITEMS + (c & 0x0F))
            reward = GOLD + (it & 0x7F) * 40 if c >= 0x80 and it & 0x80 else _reward(names, items, it & 0x7F)
            out["foot"].append({"group": group, "map": number, "x": 2 * x, "y": 2 * y + 1, "layer": FOOT_LAYER,
                                "reward": reward})
    return out


def base_tables(tables, feet_rows=None):
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
    lower = [{**e, "flag_index": e["flag_index"] + LOWER_SHIFT} for e in tables["lower"]]
    out = {**tables, "chests": chests, "chest_maps": maps, "lower": lower,
           "search": [e for e in tables["search"] if (e["group"], e["map"]) not in slots]}
    for name, free in (("foot", FREE_FOOT),):
        new = (feet_rows or {}).get(name, [])
        if not new:
            continue
        if len(new) > len(free):
            raise ValueError(f"{name}: FC 발밑 {len(new)}줄, 덮을 DQ5 줄 {len(free)}")
        rows = [dict(e) for e in tables[name]]
        for slot, row in zip(free, new):
            if rows[slot]["reward"] >= 0xD000 or (rows[slot]["group"], rows[slot]["map"]) in slots:
                raise ValueError(f"{name} {slot}: 사건 보상이나 DQ4 가 쓰는 맵의 줄은 덮지 않음")
            rows[slot].update(row)
        out[name] = rows
    return out


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
