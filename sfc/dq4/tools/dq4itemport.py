"""FC DQ4 item values on the DQ5 item table (sfc/dq5/docs/dq5-data-format.md 「물건 가격」·「물건 표」).

Items the ported shops sell get their FC price: DQ5 price = 23:B081[item] x 21:A47B[23:B159[item] & 3] (1, 10, 100,
1000), so each price is written as a base byte and a scale. FC items that DQ5 lacks take the slot of a DQ5 item no FC
item is named after (BORROWED): the name, the power (k5) and the price become the FC ones. The equip bits (k6, k7-k8)
stay DQ5's, as for every other ported item. Format: sfc/dq4/docs/dq4-environment-format.md 「가게」.
"""

import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
DQ5_TOOLS = TOOLS.parents[1] / "dq5" / "tools"
FC_TOOLS = TOOLS.parents[2] / "fc" / "dq4" / "tools"
for path in (TOOLS, DQ5_TOOLS, FC_TOOLS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

ITEM_COUNT = 0xD8
PRICE_BASE = 0x23B081
PRICE_SCALE = 0x23B159
SLOT = 0x23B231
POWER = 0x23B4B9
SCALES = (1, 10, 100, 1000)
ITEM_NAMES = 5
WEAPON = 0
# DQ5 item -> FC item name. たけのやり: a spear like てつのやり, a name of the same length, and no FC item by that name.
BORROWED = {0x01: "てつのやり"}


def _cpu(addr):
    return f"{addr >> 16:02X}:{addr & 0xFFFF:04X}"


def encode_price(price):
    """(base, scale index) with base x SCALES[scale] == price, the smallest scale that fits a byte."""
    for scale, unit in enumerate(SCALES):
        if price % unit == 0 and price // unit <= 0xFF:
            return price // unit, scale
    raise ValueError(f"price {price}: not a byte x 1, 10, 100 or 1000")


def name_at(rom, n):
    """CPU address of the length byte of DQ5 item n's name (the string table dq5text.string reads)."""
    import dq5text
    a = rom.u24(dq5text.STRING_TABLES + ITEM_NAMES * 3)
    for _ in range(n):
        a += rom.u8(a) + 1
    return a & 0x7FFFFF


def _name_codes(rom):
    """Kana -> one name byte, from the DQ5 item names that use no dakuten mark bytes (83, 84)."""
    import dq5text
    out = {}
    for n in range(ITEM_COUNT):
        raw = dq5text.string(rom, ITEM_NAMES, n)
        if any(b in (0x83, 0x84) for b in raw):
            continue
        for b, c in zip(raw, dq5text.text(dq5text.string_codes(rom, raw))):
            out.setdefault(c, b)
    return out


def encode_name(rom, name):
    codes = _name_codes(rom)
    missing = [c for c in name if c not in codes]
    if missing:
        raise ValueError(f"{name}: no single name byte for {''.join(missing)}")
    return bytes(codes[c] for c in name)


def _byte(rom, addr, value, note):
    return {"at": _cpu(addr), "hex": f"{value:02X}", "orig": f"{rom.u8(addr):02X}", "note": note}


def price_writes(rom, item, price, name):
    base, scale = encode_price(price)
    flags = rom.u8(PRICE_SCALE + item) & ~3
    return [_byte(rom, PRICE_BASE + item, base, f"{name} 가격 바탕({price}G)"),
            _byte(rom, PRICE_SCALE + item, flags | scale, f"{name} 가격 배수")]


def borrowed_writes(rom, prg, item, fc_name):
    """Name, power and FC price of fc_name on DQ5 item `item`."""
    import dq4data
    import dq5text
    fc = next((i, p, price) for i, n, p, price, _ in dq4data.items(prg) if n == fc_name)
    if dq4data.item_kind(prg, fc[0]) != WEAPON or rom.u8(SLOT + item) & 7 != WEAPON:
        raise ValueError(f"{fc_name}: only weapons borrow a DQ5 weapon slot")
    at = name_at(rom, item)
    old = dq5text.string(rom, ITEM_NAMES, item)
    new = encode_name(rom, fc_name)
    if len(new) != len(old):
        raise ValueError(f"{fc_name}: {len(new)} name bytes in place of {len(old)}")
    return [{"at": _cpu(at + 1), "hex": new.hex(" ").upper(), "orig": old.hex(" ").upper(),
             "note": f"물건 {item:02X} 이름 {fc_name}"},
            _byte(rom, POWER + item, fc[1], f"{fc_name} 공격력"),
            *price_writes(rom, item, fc[2], fc_name)]


def writes(rom, prg, prices):
    """Patch writes for the borrowed slots and for prices {DQ5 item: FC price} of the shop items."""
    import dq5chest
    out = [w for item, name in sorted(BORROWED.items()) for w in borrowed_writes(rom, prg, item, name)]
    for item, price in sorted(prices.items()):
        if item not in BORROWED:
            out += price_writes(rom, item, price, dq5chest.item_name(rom, item))
    return out


def korean_names():
    """{DQ5 item: Korean name} for the borrowed slots, from nds/dq4/tables/adopt.tsv (window and battle name tables
    are built from a ROM that still holds the DQ5 name)."""
    import dq4windowtext
    adopted = dq4windowtext.adopted(dq4windowtext.KINDS[ITEM_NAMES][0])
    return {item: adopted[dq4windowtext.kana_key(name)] for item, name in BORROWED.items()}
