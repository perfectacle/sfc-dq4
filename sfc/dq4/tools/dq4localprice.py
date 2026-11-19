"""Shop prices that differ by place: FC 15:$B2F7 gives a few items a price of their own at one place (the fox village's
はがねのつるぎ 10G), while DQ5 keeps one price per item (21:A447, BRK 94 02).

The two reads that show or charge the price of a bought item run the DQ5 price routine and then look the shop key
($0F25, dq4shopkey) and the item up in a table of (key, item, price) rows. A matching row puts its price in $46-$48
where the routine left the DQ5 one.

  list  04:B6DC JSL $06DBCA / BRK 94 02: the item under the buy list's row and its price for the row
  buy   06:DCD7·06:DDF4 LDA $0F22 / BRK 94 02: the picked item's price, which the shop copies to $0F28 to charge it

Selling keeps the DQ5 price: FC sells at the item's own price (15:$B387 reads BRK 11 0F, not 15:$B2F7), so the fox
village buys a steel sword back for 1500G like any other shop. The routine is called through its dispatcher entry
21:A3F8 with X = 4 (the BRK 94 handler 00:917D does the same with the caller's A), so the code may sit in any bank.
Format: sfc/dq4/docs/dq4-environment-format.md 「장소별 값」.
"""

import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from dq4environmentrom import _Asm  # noqa: E402

# 57:D000~ 는 성장 표가 떠난 빈 곳(dq4growth). 그 끝 쪽 256바이트
AT, END = 0x57EF00, 0x57F000
LIST_SITE, LIST_ORIG = 0x04B6DC, bytes.fromhex("22 ca db 06 00 94 02")
BUY_SITES, BUY_ORIG = (0x06DCD7, 0x06DDF4), bytes.fromhex("ad 22 0f 00 94 02")
PRICE_ENTRY, PRICE_FUNCTION = 0x21A3F8, 4
SHOP_KEY = 0x7E0F25
ROW = 4
END_MARK = 0xFF


def table(rows):
    """rows: (shop key, DQ5 item, price)."""
    out, seen = bytearray(), set()
    for key, item, price in rows:
        if key == END_MARK or (key, item) in seen or not 0 <= price <= 0xFFFF:
            raise ValueError(f"local price {key:02X} {item:02X} {price}")
        seen.add((key, item))
        out += bytes((key, item)) + price.to_bytes(2, "little")
    return bytes(out) + bytes((END_MARK,))


def code(at, rows):
    asm = _Asm(at)
    # The caller's own instructions first, in the caller's widths.
    asm.label("list").b(0x22, 0xCA, 0xDB, 0x06).word(0x20, "price").b(0x6B)
    asm.label("buy").b(0xAD, 0x22, 0x0F).word(0x20, "price").b(0x6B)
    # price: A = item. Keeps A, X, Y and P as BRK 94 02 does.
    asm.label("price").b(0xDA, 0x5A, 0x08, 0xE2, 0x10, 0xA2, PRICE_FUNCTION,
                         0x22, *PRICE_ENTRY.to_bytes(3, "little"))
    # The item stays on the stack (low byte at 1,S) while 8-bit A walks the table with 16-bit X.
    asm.b(0xC2, 0x30, 0x48, 0xE2, 0x20, 0xA2, 0x00, 0x00)
    asm.label("loop").long(0xBF, "rows").b(0xC9, END_MARK).rel(0xF0, "done")
    asm.b(0xCF, *SHOP_KEY.to_bytes(3, "little")).rel(0xD0, "next")
    asm.long(0xBF, "rows", 1).b(0xC3, 0x01).rel(0xD0, "next")
    asm.long(0xBF, "rows", 2).b(0x85, 0x46).long(0xBF, "rows", 3).b(0x85, 0x47, 0x64, 0x48).rel(0x80, "done")
    asm.label("next").b(*(0xE8,) * ROW).rel(0x80, "loop")
    asm.label("done").b(0xC2, 0x20, 0x68, 0x28, 0x7A, 0xFA, 0x60)
    asm.label("rows").b(*table(rows))
    return asm.assemble()


def _cpu(addr):
    return f"{addr >> 16:02X}:{addr & 0xFFFF:04X}"


def _jsl(target, pad):
    return bytes((0x22, *target.to_bytes(3, "little")) + (0xEA,) * pad).hex(" ").upper()


def writes(rom, rows, at=AT):
    """dq5patch/1 writes: the routines with their table and the three JSLs. No rows: nothing."""
    if not rows:
        return []
    data, labels = code(at, rows)
    if at + len(data) > END:
        raise ValueError(f"local price code {len(data)} bytes past {_cpu(END)}")
    for site, orig in ((LIST_SITE, LIST_ORIG), *((s, BUY_ORIG) for s in BUY_SITES)):
        got = bytes(rom.u8(site + k) for k in range(len(orig)))
        if got != orig:
            raise ValueError(f"{_cpu(site)}: {got.hex(' ')} 이지 {orig.hex(' ')} 가 아님")
    return [
        {"at": _cpu(at), "hex": data.hex(" ").upper(), "note": "장소별 가게 값 루틴과 표(키·물건·값)"},
        {"at": _cpu(LIST_SITE), "hex": _jsl(labels["list"], len(LIST_ORIG) - 4), "orig": LIST_ORIG.hex(" ").upper(),
         "note": "사기 목록 값: 장소별 값"},
        *({"at": _cpu(site), "hex": _jsl(labels["buy"], len(BUY_ORIG) - 4), "orig": BUY_ORIG.hex(" ").upper(),
           "note": "사기 값($0F28 에 옮김): 장소별 값"} for site in BUY_SITES),
    ]


def parse(rom, at=AT):
    """빌드 롬의 장소별 값 {(키, 물건): 값}. 사기 자리에 이 루틴의 JSL 이 없으면 빈 사전."""
    _, labels = code(at, [])
    if bytes(rom.u8(BUY_SITES[0] + k) for k in range(4)) != bytes((0x22, *labels["buy"].to_bytes(3, "little"))):
        return {}
    rows, a = {}, labels["rows"]
    while rom.u8(a) != END_MARK:
        rows[rom.u8(a), rom.u8(a + 1)] = rom.u8(a + 2) | rom.u8(a + 3) << 8
        a += ROW
    return rows
