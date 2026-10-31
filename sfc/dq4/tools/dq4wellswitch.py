"""The encounter switch of the well bottom (FC group 3A).

FC meets monsters in group 3A only while $6E05 bit7 is on (18:$9FC8), and in its maps 0 and 3 a step onto a cell
of the table 18:$A247 sets that bit to the cell's value (18:$9FB8, fc/dq4/tools/dq4encounter.py toggles). The DQ5
indoor step (01:84CF, run by 00:82AB) reads the map's zone at 01:8518; the hook takes its place:

  in the DQ5 group of FC group 3A, first a step onto a switch cell (map $BD, the FC cell of the hero's cell
  7E:3020/7E:3080, X AND FE and (Y-1) AND FE as dq4ch1event's voices) sets or clears FLAG, then while FLAG is
  off the zone is FF (01:854B: rate 0, no fight). Elsewhere it is $1A98 as before.
"""

import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
FC_TOOLS = TOOLS.parents[2] / "fc" / "dq4" / "tools"
for path in (TOOLS, FC_TOOLS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dq4environmentrom import _Asm  # noqa: E402

FC_GROUP, FC_MAPS = 0x3A, (0, 3)
# A DQ5 bit nothing reads (sfc/dq5/docs/dq5-flags.md). Saved with the game, where FC's $6E05 is cleared on loading
# and on reviving after a wipe-out (1E:$A5AD).
FLAG = (0x7E21E1, 0x02)
# 01:8518 LDA $1A98 / CMP #$FF / BEQ $854B, with M and X 8-bit (01:84D0). X carries 00:CAFD's zone-change mark to
# 01:851F TXY, so the hook keeps X.
SITE, ORIG = 0x018518, bytes((0xAD, 0x98, 0x1A, 0xC9, 0xFF, 0xF0, 0x2C))
NONE = 0x01854B
HERO_X, HERO_Y = 0x7E3020, 0x7E3080
ENTRY = 4


def cells(prg, place):
    """[(DQ5 map, DQ5 cell X & FE, (Y-1) & FE, FLAG bit or 0)] of the FC switch cells, in FC table order (the first
    match wins in FC, and each cell is listed once)."""
    import dq4encounter
    out = []
    for k in FC_MAPS:
        number = place[FC_GROUP, k][1]
        for (x, y), on in dq4encounter.toggles(prg, k).items():
            out.append((number, 2 * x, 2 * y, FLAG[1] if on else 0))
    return out


def group(place):
    return place[FC_GROUP, 0][0]


def code(at, dq5_group, rows):
    asm = _Asm(at)
    flag = FLAG[0].to_bytes(3, "little")
    asm.label("hook").b(0xA5, 0xBC, 0xC9, dq5_group).rel(0xD0, "plain").b(0xDA, 0xA2, 0x00)
    asm.label("loop").long(0xBF, "table").rel(0x30, "done").b(0xC5, 0xBD).rel(0xD0, "next")
    asm.b(0xAF, *HERO_X.to_bytes(3, "little"), 0x29, 0xFE).long(0xDF, "table", 1).rel(0xD0, "next")
    asm.b(0xAF, *HERO_Y.to_bytes(3, "little"), 0x3A, 0x29, 0xFE).long(0xDF, "table", 2).rel(0xD0, "next")
    asm.b(0xAF, *flag, 0x29, ~FLAG[1] & 0xFF).long(0x1F, "table", 3).b(0x8F, *flag)
    asm.label("next").b(*(0xE8,) * ENTRY).rel(0x80, "loop")
    asm.label("done").b(0xFA, 0xAF, *flag, 0x29, FLAG[1]).rel(0xD0, "plain").b(0xA9, 0xFF).rel(0x80, "test")
    asm.label("plain").b(0xAD, 0x98, 0x1A)
    asm.label("test").b(0xC9, 0xFF, 0x6B)
    table = b"".join(bytes(row) for row in rows) + b"\xFF"
    if len(table) > 0x80:
        raise ValueError("switch table longer than an 8-bit index walks")
    asm.label("table").b(*table)
    return asm.assemble()


def writes(at, prg, place):
    """dq5patch/1 writes: the hook with its table, and the JSL at 01:8518."""
    data, labels = code(at, group(place), cells(prg, place))
    if at >> 16 != (at + len(data) - 1) >> 16:
        raise ValueError("well switch crosses a bank")
    branch = NONE - (SITE + 6)
    return [
        {"at": _cpu(at), "hex": data.hex(" ").upper(), "note": "우물 아래 조우 켬/끔 칸과 꺼져 있을 때 구역 FF"},
        {"at": _cpu(SITE), "hex": bytes((0x22, *labels["hook"].to_bytes(3, "little"), 0xF0, branch, 0xEA)).hex(" ").upper(),
         "orig": ORIG.hex(" ").upper(), "note": "실내 걸음의 구역 읽기를 켬/끔 훅으로"},
    ]


def _cpu(addr):
    return f"{addr >> 16:02X}:{addr & 0xFFFF:04X}"
