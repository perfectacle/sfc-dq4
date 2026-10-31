"""FC DQ4 shops, inns and churches of the new DQ5 groups (dq4environmentrom.GROUPS).

People who open a shop in FC (fc/dq4/tools/dq4shop.merchants, on the base person list) get the DQ5 talk
number of the same service (06:DBD2: 01 weapon, 02 item, 03 armor, 04 deposit, 05 church, 06 inn; SERVICE). Every FC group
with a shop list or an inn gets its own key (dq4shopkey: 06:DC37 and 06:F576 read it in place of $BC).
Weapon, item and armor lists go to the DQ5 shop lists (dq5progress/1 `shops`) under that key, with FC items
matched to DQ5 items by name (an FC item DQ5 lacks may take a borrowed DQ5 slot, dq4itemport.BORROWED); every item a
list sells gets its FC price (dq4itemport.writes). The inn price table 04:FD6D has no end mark and no room, so it is copied with
the new keys added and the two operands that point at it (06:F567 bank, 06:F56D address) are changed.

  python sfc/dq4/tools/dq4shopport.py --out work/dq4-shops
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

import dq4itemport  # noqa: E402
import dq4shop  # noqa: E402
import dq5item  # noqa: E402
import dq4shopkey  # noqa: E402
from dq4environmentrom import GROUPS  # noqa: E402
from dq4groupbuild import chapter, fc_map, has_people, placement  # noqa: E402
from kr_patch.fc import ines  # noqa: E402

# FC shop kind (dq4shop.KINDS) -> DQ5 shop list kind (04:FBD5: 0 item, 1 armor, 2 weapon).
LIST_KIND = {1: 2, 2: 0, 3: 1}
# FC service (15:$9CBF; 0 and 5 both go to the church 15:$B550) -> DQ5 talk number of the same service.
# FC 7 (a free inn, 15:$A6B0) has no DQ5 counterpart; DQ5 07 is the monster deposit.
SERVICE = {0: 5, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6}
# Script conditions a seller may have and still be one at the start of chapter 1: talking across the
# counter, the time of day, and Burland's armor seller turning away at Y = 16 (15:$9D2A).
SELLER_CONDITIONS = ("counter", "낮", "밤", "주인공 Y")
# Story-flag person lists (dq4shop.npc_lists) are not the start of chapter 1.
FLAG_LIST = "목록 플래그"
STORY_FLAG = "flag& "
# dq4talk condition 16: $615A == n - 1, so "chapter n" is chapter n.
CHAPTER = "chapter "
# dq4talk 조건 03: 걷는 일행에 FC 인물 n 이 있다. 장 초기화(12:$913E)는 선두 하나만 둔다(86 87 85 83 80):
# 1장 ライアン, 2장 アリーナ, 3장 トルネコ, 4장 マーニャ, 5장 勇者.
PARTY = "party "
START_LEAD = {1: 6, 2: 7, 3: 5, 4: 3, 5: 0}
YES = "yes"
INN, CHURCH = 6, 5
INN_TABLE = 0x04FD6D
INN_ENTRIES = 21
INN_BANK_OPERAND = 0x06F568
INN_ADDR_OPERAND = 0x06F56E
# dq5progresswrite takes 1-6 items: the 7th row is under the comparison window (dq5-build-format 「성장·조우·상점」).
MAX_ITEMS = 6


def _fold(name):
    """Hiragana as katakana: DQ5 writes some item names in katakana (いばらのムチ)."""
    return "".join(chr(ord(c) + 0x60) if "ぁ" <= c <= "ゖ" else c for c in name)


def dq5_items(rom):
    """Folded name -> DQ5 item, with the borrowed slots under their FC names."""
    out = {}
    for i in range(216):
        name = _fold(dq4itemport.BORROWED.get(i) or dq5item.item_name(rom, i))
        if name in out:
            raise ValueError(f"DQ5 items {out[name]:02X} and {i:02X} share the name {name}")
        out[name] = i
    return out


@functools.cache
def _names(prg):
    return dq4shop.item_names(prg)[0]


def has_goods(prg, kind, fc_group, number, items):
    """Whether an FC service sells anything DQ5 has: a list kind needs one DQ5 item (dq5_items) in its FC list."""
    if kind not in LIST_KIND:
        return True
    names = _names(prg)
    return any(_fold(names[i & 0x7F]) in items for i in dq4shop.lookup(prg, kind, fc_group, number))


def merchants(prg, fc_group, number, items=None):
    """{(x, y, night): FC service kind} for the base person list (no story-flag list). With `items` (dq5_items),
    a seller whose list has no DQ5 item at all only talks: レイクナバ 16/01 sells nothing but うまのふん."""
    out = {}
    for x, y, _, kind, cond, _ in dq4shop.merchants(prg, fc_group, number):
        if any(FLAG_LIST in c for c in cond):
            continue
        if items is not None and not has_goods(prg, kind, fc_group, number, items):
            continue
        # Story flags are all off at the start of a chapter: a seller that needs one is not there yet, and one
        # that needs one off is. The skip comes before the condition check so that the other conditions of a
        # seller who is not there yet (a talk answer, day) do not stop the build.
        if any(c.startswith(STORY_FLAG) for c in cond):
            continue
        cond = [c for c in cond if not c.startswith(f"아님({STORY_FLAG}")]
        # The chapter is the one whose start the FC group shows (dq4groupbuild.chapter).
        here = chapter(fc_group)
        if any(c.startswith(CHAPTER) and int(c[len(CHAPTER):]) != here for c in cond) or \
                any(c.startswith(f"아님({CHAPTER}") and int(c[len(CHAPTER) + 3:-1]) == here for c in cond):
            continue
        cond = [c for c in cond if not c.startswith((CHAPTER, f"아님({CHAPTER}"))]
        # 일행 조건은 그 장 시작의 선두로 본다: コーミズ 17/00 의 판매자는 ミネア·マーニャ 가 없을 때만 있다.
        lead = START_LEAD[here]
        if any(c.startswith(PARTY) and int(c[len(PARTY):], 16) != lead for c in cond) or \
                any(c.startswith(f"아님({PARTY}") and int(c[len(PARTY) + 3:-1], 16) == lead for c in cond):
            continue
        cond = [c for c in cond if not c.startswith((PARTY, f"아님({PARTY}"))]
        # A seller behind a はい/いいえ question (レイクナバ's weapon shop, where chapter 3's job starts) waits for
        # its event; until then the person only talks.
        if YES in cond:
            continue
        unknown = [c for c in cond if not any(c.startswith(k) for k in SELLER_CONDITIONS)]
        if unknown:
            raise ValueError(f"{fc_group:02X}/{number:02X} ({x:02X},{y:02X}): seller condition {unknown}")
        if kind not in SERVICE:
            raise ValueError(f"{fc_group:02X}/{number:02X} ({x:02X},{y:02X}): FC service {kind} has no DQ5 service")
        times = [n for n, tag in ((False, "낮"), (True, "밤")) if tag in cond] or [False, True]
        for night in times:
            if out.get((x, y, night), SERVICE[kind]) != SERVICE[kind]:
                raise ValueError(f"{fc_group:02X}/{number:02X} ({x:02X},{y:02X}): two services")
            out[x, y, night] = SERVICE[kind]
    return out


def _cpu(addr):
    return f"{addr >> 16:02X}:{addr & 0xFFFF:04X}"


def keys(place, kinds):
    """dq4shopkey rows (DQ5 group, first DQ5 map, last DQ5 map, key), keys from KEY_FIRST up. kinds[(DQ5 group,
    DQ5 map)]: the list kinds and inn of its sellers. Each FC group with any of them gets one row over all its maps,
    split into consecutive runs where a map brings a kind the run already has: a key has one list per kind and one
    inn price (エンドール sells armour on 04/00 and in 04/09)."""
    spans = {}
    for (fc_group, _), (group, number) in place.items():
        spans.setdefault((group, fc_group), []).append(number)
    rows, key = [], dq4shopkey.KEY_FIRST
    for (group, _), numbers in sorted(spans.items()):
        numbers = sorted(numbers)
        if not any(kinds.get((group, n)) for n in numbers):
            continue
        first, seen = numbers[0], set()
        for n in numbers:
            here = kinds.get((group, n), set())
            if here & seen:
                rows.append((group, first, n - 1, key))
                key, first, seen = key + 1, n, set()
            seen |= here
        rows.append((group, first, numbers[-1], key))
        key += 1
    return rows


def port(dq5_path, dq4_path, inn_at, key_at, with_people=True):
    """(service kinds per person, dq5progress shops, patch writes of the inn table and the key hook, report);
    `with_people` False ports no sellers.
    The inn table bank must show the low WRAM: 06:F563 keeps the table bank in DB and writes $0F28-$0F36 with
    absolute addresses."""
    if not inn_at >> 16 <= 0x3F:
        raise ValueError(f"inn table bank {inn_at >> 16:02X}: needs 00-3F")
    prg = ines.prg(Path(dq4_path).read_bytes())
    rom = dq5item.Rom(Path(dq5_path).read_bytes())
    items = dq5_items(rom)
    names, _ = dq4shop.item_names(prg)
    progress = json.loads(_dump_progress(dq5_path))
    counts = {k: sum(1 for s in progress["shops"] if s["kind"] == k) for k in range(4)}
    services, shops, inns, prices = {}, [], {}, {}
    report = {"shops": [], "missing_items": [], "inns": {}, "keys": {}, "prices": {}}
    maps = sorted(GROUPS.values())
    for group, number in maps:
        fc_group, fc_number = fc_map(prg, group, number)
        services[f"{group:02X}/{number:02X}"] = (merchants(prg, fc_group, fc_number, items)
                                                 if has_people(fc_group, with_people) else {})
    rows = keys(placement(prg), {(group, number): set(services[f"{group:02X}/{number:02X}"].values()) & {*LIST_KIND, INN}
                                 for group, number in maps})
    for group, number in maps:
        fc_group, fc_number = fc_map(prg, group, number)
        found = services[f"{group:02X}/{number:02X}"]
        key = next((k for g, first, last, k in rows if g == group and first <= number <= last), None)
        for kind in sorted(set(found.values())):
            if kind in LIST_KIND:
                if any(s["key"] == key and s["kind"] == LIST_KIND[kind] for s in shops):
                    raise ValueError(f"{group:02X}/{number:02X}: two {dq4shop.KINDS[kind]} lists under key {key:02X}")
                fc_items = dq4shop.lookup(prg, kind, fc_group, fc_number)
                picked = []
                for i in fc_items:
                    item = names[i & 0x7F]
                    if _fold(item) in items:
                        picked.append(items[_fold(item)])
                        price = dq4shop.price(prg, fc_group, fc_number, i & 0x7F)
                        if prices.setdefault(picked[-1], price) != price:
                            raise ValueError(f"{item}: FC prices {prices[picked[-1]]} and {price}")
                    else:
                        report["missing_items"].append(f"{group:02X}/{number:02X} {item}")
                if len(picked) > MAX_ITEMS:
                    raise ValueError(f"{group:02X}: more than {MAX_ITEMS} items")
                dq5_kind = LIST_KIND[kind]
                shops.append({"kind": dq5_kind, "index": counts[dq5_kind], "key": key, "items": picked})
                counts[dq5_kind] += 1
                report["shops"].append({"map": f"{group:02X}/{number:02X}", "kind": dq4shop.KINDS[kind],
                                        "fc": [names[i & 0x7F] for i in fc_items], "dq5": picked})
            elif kind == INN:
                price = dq4shop.inn_price(prg, fc_group, fc_number)
                if price is None or price > 0x7F:
                    raise ValueError(f"{fc_group:02X}/{fc_number:02X}: inn price {price}")
                # One key per FC group: its maps share one price.
                if inns.get(key, price) != price:
                    raise ValueError(f"{key:02X}: inn prices {inns[key]} and {price} ({fc_group:02X}/{fc_number:02X})")
                inns[key] = price
                report["inns"][f"{group:02X}/{number:02X}"] = price
    report["keys"] = {f"{g:02X}/{first:02X}-{last:02X}": f"{k:02X}" for g, first, last, k in rows}
    original = bytes(rom.u8(INN_TABLE + i) for i in range(INN_ENTRIES * 2))
    # New entries keep bit7 off: after sleeping the party lines up behind the hero ($0F36 -> $198E).
    table = original + b"".join(bytes((k, p)) for k, p in sorted(inns.items()))
    writes = [
        {"at": _cpu(inn_at), "hex": table.hex(" ").upper(), "note": "여관 1인 값 표(원래 21항목 + 새 키)"},
        {"at": _cpu(INN_BANK_OPERAND), "hex": f"{inn_at >> 16:02X}", "orig": "04", "note": "여관 표 뱅크(DB)"},
        {"at": _cpu(INN_ADDR_OPERAND), "hex": f"{inn_at & 0xFF:02X} {inn_at >> 8 & 0xFF:02X}", "orig": "6D FD",
         "note": "여관 표 주소"},
        *dq4shopkey.writes(key_at, rows),
        *dq4itemport.writes(rom, prg, prices),
    ]
    report["prices"] = {f"{i:02X} {dq4itemport.BORROWED.get(i) or dq5item.item_name(rom, i)}": p
                        for i, p in sorted(prices.items())}
    return services, shops, writes, report


def _dump_progress(dq5_path):
    import tempfile
    import dq4buildcache
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "progress.json"
        dq4buildcache.run(DQ5_TOOLS / "dq5progresswrite.py", dq5_path, "dump", "-o", out)
        return out.read_text(encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dq5", default="rom/dq5.sfc")
    ap.add_argument("--dq4", default="rom/dq4.nes")
    ap.add_argument("--inn-at", default="3C:F000")
    ap.add_argument("--key-at", default="3C:FE00")
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    inn_at, key_at = (int(a.split(":")[0], 16) << 16 | int(a.split(":")[1], 16) for a in (args.inn_at, args.key_at))
    services, shops, writes, report = port(args.dq5, args.dq4, inn_at, key_at)
    (args.out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps({**report, "services": {m: {f"{x},{y},{'night' if n else 'day'}": k for (x, y, n), k in s.items()}
                                             for m, s in services.items()}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
