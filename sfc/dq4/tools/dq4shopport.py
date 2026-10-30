"""FC DQ4 shops, inns and churches of the new DQ5 groups (dq4environmentrom.GROUPS).

People who open a shop in FC (fc/dq4/tools/dq4shop.merchants, on the base person list) get the DQ5 talk
number of the same service (06:DBD2: 01 weapon, 02 item, 03 armor, 04 deposit, 05 church, 06 inn; SERVICE). Every FC group
with a shop list or an inn gets its own key (dq4shopkey: 06:DC37 and 06:F576 read it in place of $BC).
Weapon, item and armor lists go to the DQ5 shop lists (dq5progress/1 `shops`) under that key, with FC items
matched to DQ5 items by name. The inn price table 04:FD6D has no end mark and no room, so it is copied with
the new keys added and the two operands that point at it (06:F567 bank, 06:F56D address) are changed.

  python sfc/dq4/tools/dq4shopport.py --out work/dq4-shops
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

import dq4shop  # noqa: E402
import dq5item  # noqa: E402
import dq4shopkey  # noqa: E402
from dq4environmentrom import GROUPS  # noqa: E402
from dq4groupbuild import fc_map, placement  # noqa: E402
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
    out = {}
    for i in range(216):
        name = _fold(dq5item.item_name(rom, i))
        if name in out:
            raise ValueError(f"DQ5 items {out[name]:02X} and {i:02X} share the name {name}")
        out[name] = i
    return out


def merchants(prg, fc_group, number):
    """{(x, y, night): FC service kind} for the base person list (no story-flag list)."""
    out = {}
    for x, y, _, kind, cond, _ in dq4shop.merchants(prg, fc_group, number):
        if any(FLAG_LIST in c for c in cond):
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


def keys(place, sellers):
    """dq4shopkey rows for the (DQ5 group, FC group) pairs in `sellers`, keys from KEY_FIRST up in that order:
    (DQ5 group, first DQ5 map, last DQ5 map of the FC group, key)."""
    rows = []
    for key, (group, fc_group) in enumerate(sorted(sellers), dq4shopkey.KEY_FIRST):
        numbers = [n for (g, _), (dg, n) in place.items() if g == fc_group and dg == group]
        rows.append((group, min(numbers), max(numbers), key))
    return rows


def port(dq5_path, dq4_path, inn_at, key_at):
    """(service kinds per person, dq5progress shops, patch writes of the inn table and the key hook, report).
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
    services, shops, inns, report = {}, [], {}, {"shops": [], "missing_items": [], "inns": {}, "keys": {}}
    maps = sorted(GROUPS.values())
    for group, number in maps:
        services[f"{group:02X}/{number:02X}"] = merchants(prg, *fc_map(prg, group, number))
    sellers = {(group, fc_map(prg, group, number)[0]) for group, number in maps
               if set(services[f"{group:02X}/{number:02X}"].values()) & {*LIST_KIND, INN}}
    rows = keys(placement(prg), sellers)
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
    ]
    return services, shops, writes, report


def _dump_progress(dq5_path):
    import subprocess
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "progress.json"
        subprocess.run([sys.executable, str(DQ5_TOOLS / "dq5progresswrite.py"), str(dq5_path), "dump", "-o", str(out)],
                       check=True, capture_output=True)
        return out.read_text(encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dq5", default="rom/dq5.sfc")
    ap.add_argument("--dq4", default="rom/dq4.nes")
    ap.add_argument("--inn-at", default="3C:F000")
    ap.add_argument("--key-at", default="3C:FC00")
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
