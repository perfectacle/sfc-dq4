"""FC DQ4 item values on the DQ5 item table (sfc/dq5/docs/dq5-data-format.md 「물건 가격」·「물건 표」).

Items the ported shops sell get their FC price: DQ5 price = 23:B081[item] x 21:A47B[23:B159[item] & 3] (1, 10, 100,
1000), so each price is written as a base byte and a scale. FC items that DQ5 lacks take the slot of a DQ5 item no FC
item is named after (BORROWED): the name, the power (k5) and the price become the FC ones. The equip bits (k6, k7-k8)
stay DQ5's, as for every other ported item. Format: sfc/dq4/docs/dq4-environment-format.md 「가게」.

Chapter 2's and 3's story items take DQ5 key-item slots no DQ5 talk condition or item query of this hack reads (EVENT_ITEMS):
the FC name goes on the slot, the record (k1-k4) and the field-use handler become those of ゴールドオーブ, which shows
「しかし ここでは 何も おこらなかった！」 (11:8BE4 -> message 1A8). とうぞくのカギ keeps DQ5's own slot B7, whose record
DQ5 leaves empty (a weapon that sells): it gets まほうのカギ's record, and dq4door opens lock-1 doors for it.
Format: sfc/dq4/docs/dq4-chapter2-format.md 「사건 물건」, sfc/dq4/docs/dq4-chapter3-format.md 「사건 물건」.
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
# はぐれメタルよろい. Chapter 2's monster drops: けがわのフード (the nearest defence, 11 for 12) for きんのかみかざり,
# シルクハット for はねぼうし. Chapter 1's ラックのたね: たいまつ (C5), with まもりのたね's record (BORROWED_RECORDS;
# dq4fcitems turns its use into luck). まもりのたね itself is an NDS item and keeps its slot. Chapter 3's casino prizes: おおかなづち (a weapon DQ5 cannot use in battle, 27:819A, so
# using it does nothing instead of a DQ5 effect) for ほほえみのつえ, メタルキングのたて for はぐれメタルのたて.
BORROWED = {0x01: "てつのやり", 0x34: "せいぎのそろばん", 0x4E: "てつのまえかけ", 0x61: "はぐれメタルよろい",
            0x89: "きんのかみかざり", 0x8C: "はねぼうし", 0x37: "ほほえみのつえ", 0x84: "はぐれメタルのたて",
            0xC5: "ラックのたね", 0x6E: "ピンクのレオタード"}
# Borrowed slots whose record (k1-k4) comes from another DQ5 item: たいまつ is a key item, まもりのたね a seed (used up,
# sold, usable in battle)
BORROWED_RECORDS = {0xC5: 0xAE}
# DQ5 key item -> FC story item. ゴールドオーブ (C6) has おうごんのうでわ's name length (10 bytes with the dakuten
# marks); あくまのおもちゃ (BE) is an empty DQ5 record of さえずりのみつ's length (8 bytes). Chapter 3's take DQ5 items
# no FC item, chest substitute or talk condition names: モンスターほいほい (C3, empty record) and ルラムーンそう (CA,
# ゴールドオーブ's record) fit their letters' lengths. No free slot is 11 bytes long for ぎんのめがみぞう, so the three
# neighbours まもののエサ·ばくだんいし·ファイトいっぱつ (6 + 8 + 9) are rewritten as one run (NAME_RUNS).
BENTO, IRON_SAFE, STATUE, PRINCE_LETTER, KING_LETTER = 0xBB, 0xBC, 0xBD, 0xC3, 0xCA
# 2장 산트하임 상자의 あやかしのふえ: 이름 길이가 같은(7바이트) DQ5 열쇠 물건 おうけのあかし 자리. 이 해킹은 그 물건을 쓰지 않는다
FLUTE = 0xCB
# 4장 상자의 せいじゃくのたま 는 이름 길이가 같은(9바이트) たたかいのドラム(C4) 자리. じょうせんけん(8)·うまのふん(5)은 이웃한
# てんしのすず(C1, 7)·いのちのいし(C2, 6)를 한 줄로 고쳐 쓴다(NAME_RUNS). 전투 쓰기는 dq4fcitems 가 고친다
SILENCE_ORB, SHIP_TICKET, HORSE_DUNG = 0xC4, 0xC1, 0xC2
EVENT_ITEMS = {0xC6: "おうごんのうでわ", 0xBE: "さえずりのみつ",
               BENTO: "おべんとう", IRON_SAFE: "てつのきんこ", STATUE: "ぎんのめがみぞう",
               PRINCE_LETTER: "おうじのてがみ", KING_LETTER: "おうのてがみ", FLUTE: "あやかしのふえ",
               SILENCE_ORB: "せいじゃくのたま", SHIP_TICKET: "じょうせんけん", HORSE_DUNG: "うまのふん"}
# 기록(k1~k4)과 필드 쓰기를 ゴールドオーブ 대신 빌릴 물건: あやかしのふえ 는 DQ5 피리 はるかぜのフルート(C7). FC 는 쓰면
# 「…は あやかしのふえを ふいた。」 만 뜨고 남는다(실측). おべんとう 는 FC 에서 やくそう 와 같은 물건(10G, 회복 30+rand(11),
# 쓰면 없어짐, 전투 행동 94)이라 やくそう(A1) 기록·처리기
HERB = 0xA1
EVENT_TEMPLATES = {FLUTE: 0xC7, HORSE_DUNG: HORSE_DUNG, BENTO: HERB}
# FC 필드 효과 비트($8D1B bit7)가 꺼진 사건 물건은 쓰면 「…をつかった！」 뒤 「しかし なにも おこらなかった。」(02C5)뿐이라,
# 같은 뜻의 글(18E)을 띄우는 いのちのいし 처리기(11:8BB9, うまのふん 자리에 그대로 남음)를 필드 쓰기로 빌린다(use_template)
NOTHING_USE = HORSE_DUNG
FC_FIELD_USE = 0x80
# Neighbouring items whose names are written together: the string table is walked by length (21:955D), so the names may
# change length as long as the run keeps its total. No armour slot is 11 bytes long for ピンクのレオタード: it takes
# プリンセスローブ (6E, 10 bytes) and its neighbour シルクのビスチェ (6D, 9 bytes, no FC item and no ported shop or chest)
# gives up its の (RENAMED). ラックのたね (6 bytes) on たいまつ (4) is paid by はるかぜのフルート (C7, 10 bytes, a DQ5 item no
# FC or NDS item is named after, out of reach in this hack) going by はるかぜのふえ (8): C4-C7 keep 9 + 4 + 10 + 10.
RENAMED = {0x6D: "シルクビスチェ", 0xC7: "はるかぜのふえ"}
NAME_RUNS = ((BENTO, IRON_SAFE, STATUE), (0x6D, 0x6E), (SHIP_TICKET, HORSE_DUNG), (SILENCE_ORB, 0xC5, 0xC6, 0xC7))
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


# k1 의 「팔 수 없음」(bit3, 가게 팔기 06:DEF2)과 그와 늘 함께 켜진 bit4(가득 찰 때 고르는 창). 빌린 자리는 FC 물건의
# 「못 팖」($8D1B bit5)을 따른다: DQ5 プリンセスローブ 는 0G 라 켜져 있고 ピンクのレオタード 는 6300G 에 팔린다
NO_SALE = 0x18
FC_NO_SALE = 0x20


# 가게에서 팔지 않아도 값을 두는 물건과, k1 bit5(쓰면 없어짐)를 끄는 물건: うまのふん 은 FC 2G 에 팔리고 쓰면 남는다
# (いのちのいし 기록은 쓰면 없어짐)
FIXED_PRICES = {HORSE_DUNG: 2, BENTO: 10}
CONSUMED = 0x20
KEEP_ON_USE = {HORSE_DUNG}


def price_writes(rom, item, price, name, sellable=None):
    """Price base and scale of item. The scale byte keeps the flags of the record the item ends up with (an event item's
    template, EVENT_TEMPLATES)."""
    base, scale = encode_price(price)
    record = (EVENT_TEMPLATES.get(item, EVENT_TEMPLATE) if item in EVENT_ITEMS else BORROWED_RECORDS.get(item, item))
    flags = rom.u8(PRICE_SCALE + record) & ~3
    if item in KEEP_ON_USE:
        flags &= ~CONSUMED
    if sellable is not None:
        flags = flags & ~NO_SALE | (0 if sellable else NO_SALE)
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
    in_run = any(item in run for run in NAME_RUNS)
    if len(new) != len(old) and not in_run:
        raise ValueError(f"{fc_name}: {len(new)} name bytes in place of {len(old)}")
    name = [] if in_run else [{"at": _cpu(at + 1), "hex": new.hex(" ").upper(), "orig": old.hex(" ").upper(),
                               "note": f"물건 {item:02X} 이름 {fc_name}"}]
    record = _record_writes(rom, item, BORROWED_RECORDS[item], fc_name, skip_price=True) if item in BORROWED_RECORDS else []
    return [*name, *record,
            _byte(rom, POWER + item, fc[1], f"{fc_name} 공격력·수비력"),
            *price_writes(rom, item, fc[2], fc_name,
                          sellable=not dq4data.rd(prg, dq4data.ITEM_BANK, dq4data.ITEM_FLAGS + fc[0]) & FC_NO_SALE)]


def fc_name(rom, item):
    """The name item n goes by in this hack: the FC name of a borrowed slot, else DQ5's."""
    import dq5item
    return BORROWED.get(item) or EVENT_ITEMS.get(item) or dq5item.item_name(rom, item)


def use_template(prg, item):
    """The item whose DQ5 field-use handler an event item takes: NOTHING_USE when the FC item has no field effect, else
    its record template."""
    import dq4data
    import dq4shop
    fc = {n: i for i, n in dq4shop.item_names(prg)[0].items()}[EVENT_ITEMS[item]]
    if not dq4data.rd(prg, dq4data.ITEM_BANK, dq4data.ITEM_FLAGS + fc) & FC_FIELD_USE:
        return NOTHING_USE
    return EVENT_TEMPLATES.get(item, EVENT_TEMPLATE)


def _record_writes(rom, item, template, name, use=None, skip_price=False):
    """Record bytes of template on item (the price scale byte is left to price_writes when the item has a price of its
    own: a fixed price, or skip_price), and the field-use handler of `use` (None: the handler stays)."""
    out = [_byte(rom, table + item, rom.u8(table + template), f"{name} 물건 표({_cpu(table)})")
           for table in RECORD if rom.u8(table + item) != rom.u8(table + template)
           and not (table == PRICE_SCALE and (skip_price or item in FIXED_PRICES))]
    if use is None:
        return out
    at, src = USE_HANDLERS + (item - FIRST_USE) * 2, USE_HANDLERS + (use - FIRST_USE) * 2
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
    in_runs = {item for run in NAME_RUNS for item in run}
    named = {**RENAMED, **BORROWED, **EVENT_ITEMS}
    for run in NAME_RUNS:
        if list(run) != list(range(run[0], run[0] + len(run))) or not set(run) <= set(named):
            raise ValueError(f"{run}: a name run is neighbouring items this hack names")
        at = name_at(rom, run[0])
        old = bytes(rom.u8(at + k) for k in range(name_at(rom, run[-1] + 1) - at))
        new = b"".join(bytes((len(n),)) + n for n in (encode_name(rom, named[i]) for i in run))
        if len(new) != len(old):
            raise ValueError(f"{run}: {len(new)} name bytes in place of {len(old)}")
        out.append({"at": _cpu(at), "hex": new.hex(" ").upper(), "orig": old.hex(" ").upper(),
                    "note": "물건 " + "·".join(f"{i:02X} {named[i]}" for i in run) + " 이름(길이째)"})
    for item, fc_item in sorted(EVENT_ITEMS.items()):
        if fc_item not in fc:
            raise ValueError(f"{fc_item}: not an FC item name")
        if item not in in_runs:
            at = name_at(rom, item)
            old = dq5text.string(rom, ITEM_NAMES, item)
            new = encode_name(rom, fc_item)
            if len(new) != len(old):
                raise ValueError(f"{fc_item}: {len(new)} name bytes in place of {len(old)}")
            out.append({"at": _cpu(at + 1), "hex": new.hex(" ").upper(), "orig": old.hex(" ").upper(),
                        "note": f"물건 {item:02X} 이름 {fc_item}"})
        out += _record_writes(rom, item, EVENT_TEMPLATES.get(item, EVENT_TEMPLATE), fc_item, use_template(prg, item))
    # B7 keeps its own handler (11:8E43, key level 1); まほうのカギ's would open lock-2 doors.
    out += _record_writes(rom, THIEF_KEY, KEY_TEMPLATE, "とうぞくのカギ")
    return out


def writes(rom, prg, prices):
    """Patch writes for the borrowed slots, the story items and prices {DQ5 item: FC price} of the shop items."""
    import dq5chest
    import dq4fcitems
    out = [w for item, name in sorted(BORROWED.items()) for w in borrowed_writes(rom, prg, item, name)]
    out += dq4fcitems.writes(rom, EVENT_ITEMS)
    out += event_writes(rom, prg)
    for item, price in sorted({**FIXED_PRICES, **prices}.items()):
        if item not in BORROWED:
            out += price_writes(rom, item, price, dq5chest.item_name(rom, item))
    return out


def korean_names():
    """{DQ5 item: Korean name} for the borrowed slots, from nds/dq4/tables/adopt.tsv (window and battle name tables
    are built from a ROM that still holds the DQ5 name)."""
    import dq4windowtext
    adopted = dq4windowtext.adopted(dq4windowtext.KINDS[ITEM_NAMES][0])
    adopted.update({dq4windowtext.kana_key(k): v for k, v in dq4windowtext.EXTRA_NAMES.get(ITEM_NAMES, {}).items()})
    return {item: adopted[dq4windowtext.kana_key(name)] for item, name in {**BORROWED, **EVENT_ITEMS}.items()}
