"""FC DQ4 item values on the DQ5 item table (sfc/dq5/docs/dq5-data-format.md 「물건 가격」·「물건 표」).

Items the ported shops sell get their FC price: DQ5 price = 23:B081[item] x 21:A47B[23:B159[item] & 3] (1, 10, 100,
1000), so each price is written as a base byte and a scale. FC items that DQ5 lacks take the slot of a DQ5 item no FC
item is named after (BORROWED): the name, the power (k5) and the price become the FC ones. The equip bits (k6, k7-k8)
stay DQ5's, as for every other ported item. Format: sfc/dq4/docs/dq4-environment-format.md 「가게」.

Chapter 2's story items take DQ5 key-item slots no DQ5 talk condition or item query of this hack reads (EVENT_ITEMS):
the FC name goes on the slot, the record (k1-k4) and the field-use handler become those of ゴールドオーブ, which shows
「しかし ここでは 何も おこらなかった！」 (11:8BE4 -> message 1A8). とうぞくのカギ keeps DQ5's own slot B7, whose record
DQ5 leaves empty (a weapon that sells): it gets まほうのカギ's record, and dq4door opens lock-1 doors for it.
Format: sfc/dq4/docs/dq4-chapter2-format.md 「사건 물건」.
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
# DQ5 item -> FC item name, each on a DQ5 slot of the same kind and name length that no FC item is named after and no
# ported shop or chest uses. たけのやり: a spear like てつのやり. エンドール's shops: オリハルコンのキバ (a monster-only
# fang) for せいぎのそろばん, てつのむねあて for てつのまえかけ, メタルキングよろい (the same defence, 95) for
# はぐれメタルよろい.
BORROWED = {0x01: "てつのやり", 0x34: "せいぎのそろばん", 0x4E: "てつのまえかけ", 0x61: "はぐれメタルよろい"}
# DQ5 key item -> FC story item. ゴールドオーブ (C6) has おうごんのうでわ's name length (10 bytes with the dakuten
# marks); あくまのおもちゃ (BE) is an empty DQ5 record of さえずりのみつ's length (8 bytes).
EVENT_ITEMS = {0xC6: "おうごんのうでわ", 0xBE: "さえずりのみつ"}
EVENT_TEMPLATE = 0xC6
THIEF_KEY, KEY_TEMPLATE = 0xB7, 0xB8
# Record bytes the story items copy: k1 (flags, price scale), k2 (slot), k3 and k4 (description and use message).
RECORD = (0x23B159, SLOT, 0x23B309, 0x23B3E1)
USE_HANDLERS = 0x118F5B
FIRST_USE = 0xA1


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
    """Kana -> its name bytes, from the DQ5 item names: one byte, or a mark byte (84 dakuten, 83 handakuten) and a key."""
    import dq5text
    out = {}
    for n in range(ITEM_COUNT):
        raw = dq5text.string(rom, ITEM_NAMES, n)
        i = 0
        while i < len(raw):
            size = 2 if raw[i] in (0x83, 0x84) else 1
            chunk = raw[i:i + size]
            out.setdefault(dq5text.text(dq5text.string_codes(rom, chunk)), chunk)
            i += size
    return out


def encode_name(rom, name):
    codes = _name_codes(rom)
    missing = [c for c in name if c not in codes]
    if missing:
        raise ValueError(f"{name}: no single name byte for {''.join(missing)}")
    return b"".join(codes[c] for c in name)


def _byte(rom, addr, value, note):
    return {"at": _cpu(addr), "hex": f"{value:02X}", "orig": f"{rom.u8(addr):02X}", "note": note}


def price_writes(rom, item, price, name):
    base, scale = encode_price(price)
    flags = rom.u8(PRICE_SCALE + item) & ~3
    return [_byte(rom, PRICE_BASE + item, base, f"{name} 가격 바탕({price}G)"),
            _byte(rom, PRICE_SCALE + item, flags | scale, f"{name} 가격 배수")]


def borrowed_writes(rom, prg, item, fc_name):
    """Name, power (attack or defence) and FC price of fc_name on DQ5 item `item` of the same kind."""
    import dq4data
    import dq5text
    fc = next((i, p, price) for i, n, p, price, _ in dq4data.items(prg) if n == fc_name)
    if dq4data.item_kind(prg, fc[0]) != rom.u8(SLOT + item) & 7:
        raise ValueError(f"{fc_name}: FC kind {dq4data.item_kind(prg, fc[0])} on a DQ5 slot of kind {rom.u8(SLOT + item) & 7}")
    at = name_at(rom, item)
    old = dq5text.string(rom, ITEM_NAMES, item)
    new = encode_name(rom, fc_name)
    if len(new) != len(old):
        raise ValueError(f"{fc_name}: {len(new)} name bytes in place of {len(old)}")
    return [{"at": _cpu(at + 1), "hex": new.hex(" ").upper(), "orig": old.hex(" ").upper(),
             "note": f"물건 {item:02X} 이름 {fc_name}"},
            _byte(rom, POWER + item, fc[1], f"{fc_name} 공격력·수비력"),
            *price_writes(rom, item, fc[2], fc_name)]


def fc_name(rom, item):
    """The name item n goes by in this hack: the FC name of a borrowed slot, else DQ5's."""
    import dq5item
    return BORROWED.get(item) or EVENT_ITEMS.get(item) or dq5item.item_name(rom, item)


def _record_writes(rom, item, template, name, handler=True):
    out = [_byte(rom, table + item, rom.u8(table + template), f"{name} 물건 표({_cpu(table)})")
           for table in RECORD if rom.u8(table + item) != rom.u8(table + template)]
    if not handler:
        return out
    at, src = USE_HANDLERS + (item - FIRST_USE) * 2, USE_HANDLERS + (template - FIRST_USE) * 2
    if rom.u16(at) != rom.u16(src):
        out.append({"at": _cpu(at), "hex": f"{rom.u8(src):02X} {rom.u8(src + 1):02X}",
                    "orig": f"{rom.u8(at):02X} {rom.u8(at + 1):02X}", "note": f"{name} 필드에서 쓰기"})
    return out


def event_writes(rom, prg):
    """Name, record and use handler of the story items (EVENT_ITEMS), and まほうのカギ's record on とうぞくのカギ."""
    import dq4shop
    import dq5text
    fc = set(dq4shop.item_names(prg)[0].values())
    out = []
    for item, fc_item in sorted(EVENT_ITEMS.items()):
        if fc_item not in fc:
            raise ValueError(f"{fc_item}: not an FC item name")
        at = name_at(rom, item)
        old = dq5text.string(rom, ITEM_NAMES, item)
        new = encode_name(rom, fc_item)
        if len(new) != len(old):
            raise ValueError(f"{fc_item}: {len(new)} name bytes in place of {len(old)}")
        out.append({"at": _cpu(at + 1), "hex": new.hex(" ").upper(), "orig": old.hex(" ").upper(),
                    "note": f"물건 {item:02X} 이름 {fc_item}"})
        out += _record_writes(rom, item, EVENT_TEMPLATE, fc_item)
    # B7 keeps its own handler (11:8E43, key level 1); まほうのカギ's would open lock-2 doors.
    out += _record_writes(rom, THIEF_KEY, KEY_TEMPLATE, "とうぞくのカギ", handler=False)
    return out


def writes(rom, prg, prices):
    """Patch writes for the borrowed slots, the story items and prices {DQ5 item: FC price} of the shop items."""
    import dq5chest
    out = [w for item, name in sorted(BORROWED.items()) for w in borrowed_writes(rom, prg, item, name)]
    out += event_writes(rom, prg)
    for item, price in sorted(prices.items()):
        if item not in BORROWED:
            out += price_writes(rom, item, price, dq5chest.item_name(rom, item))
    return out


def korean_names():
    """{DQ5 item: Korean name} for the borrowed slots, from nds/dq4/tables/adopt.tsv (window and battle name tables
    are built from a ROM that still holds the DQ5 name)."""
    import dq4windowtext
    adopted = dq4windowtext.adopted(dq4windowtext.KINDS[ITEM_NAMES][0])
    return {item: adopted[dq4windowtext.kana_key(name)] for item, name in {**BORROWED, **EVENT_ITEMS}.items()}
