"""Map outside: draw the cells off the edge of a ported map with the FC map's outside block, as FC does.

FC draws every cell off the map with the outside block of the map header ($0520, fc/dq4/docs/dq4-map-format.md 「맵
밖 칸」). DQ5 picks the way from map header +3 (01:97D0 -> $182C; 01:98A4 tile word -> $182D, 01:98BA routine ->
$1830, sfc/dq5/docs/dq5-map-format.md). Way 0 (00:BAD6) fills with tile word 0000, black, and the environment
build gave every ported map way 0, so a town whose road runs off the edge (36/00 west end) showed black beside it.
Ways 3 and 6 (00:BA74, 00:BAEA) map an outside cell back onto the map edge (2 or 4 cells repeated) and draw that
cell from the common tail 00:BAC3, with the in-map cell in $00/$01; FC map edges seldom hold the outside block.

OUTSIDE_WAY, which no DQ5 map uses, now leads through the bank-00 stub STUB_AT to ROUTINE_AT: it looks the current
map ($BC, $BD) up in its table and puts in $00/$01 a fixed in-map block cell holding the outside block, plus the
low bit of the outside cell ($90, $92), so the 2x2 cells of that block repeat. The stub then jumps to 00:BAC3, as
00:BA74 does. The in-map block is one in FC zone 0: FC draws the outside block in zone 0 (0F:$D4E6), so from inside
a house (another zone) it is darkened, which the DQ5 zone drawing of that cell does too. A map whose outside block
appears only in other zones or not at all keeps way 0 (black).

FC maps with header $0550 bit7 (3C/00, the prologue village) mix $0520 with $0582 in a pattern (0F:$D44C); here they
get $0520 alone.
"""

# Chapter 1 and the prologue (dq4environmentrom.GROUPS 36-3C).
GROUPS = range(0x36, 0x3D)
OUTSIDE_WAY = 5
WAY_TILES, WAY_ROUTINES = 0x0198A4, 0x0198BA
WAY_ROUTINE_ORIG = bytes((0x4C, 0xBB))            # 00:BB4C, unused: no DQ5 map header has +3 = 5
# 00:FFA8-FFAF: after the window text NMI stub (00:FFA1-FFA7), before the header dq5build keeps (00:FFB0-FFDF).
STUB_AT, STUB_END = 0x00FFA8, 0x00FFB0
COMMON_TAIL = 0x00BAC3
# After dq4door's finder (57:F400); dq4dungeonrate takes 57:8000 and dq4balance 57:F000.
ROUTINE_AT, ROUTINE_END = 0x57FC00, 0x580000


def cell(source):
    """The DQ5 cell (top-left of the 2x2) of the first FC zone-0 block of `source` (dq4block.Map) that is its
    outside block, or None."""
    for y in range(source.h):
        for x in range(source.w):
            if source.buf[y * source.w + x] == source.outside:
                return x * 2, y * 2
    return None


def way(target, source):
    """Map header +3 for DQ5 map `target` (group, number) made from `source`."""
    return OUTSIDE_WAY if target[0] in GROUPS and cell(source) is not None else 0


def routine(table):
    """table: [(group, number, x, y)]. Keeps P, X and Y; reads only the direct page and its own bank."""
    from dq4environmentrom import _Asm   # dq4environmentrom imports this module for way()
    asm = _Asm(ROUTINE_AT)
    asm.b(0x08, 0xC2, 0x10, 0xDA, 0x5A, 0xE2, 0x30)          # PHP / REP #$10 / PHX / PHY / SEP #$30
    asm.b(0xA2, 0x00)                                        # LDX #$00
    asm.label("loop").long(0xBF, "table").b(0xC9, 0xFF).rel(0xF0, "none")         # LDA table,X / CMP #$FF / BEQ
    asm.b(0xC5, 0xBC).rel(0xD0, "next")                      # CMP $BC / BNE next
    asm.long(0xBF, "table", 1).b(0xC5, 0xBD).rel(0xD0, "next")                    # LDA table+1,X / CMP $BD / BNE
    asm.b(0xA5, 0x90, 0x29, 0x01, 0x18).long(0x7F, "table", 2).b(0x85, 0x00)     # $00 = ($90 & 1) + x
    asm.b(0xA5, 0x92, 0x29, 0x01, 0x18).long(0x7F, "table", 3).b(0x85, 0x01)     # $01 = ($92 & 1) + y
    asm.label("done").b(0xC2, 0x10, 0x7A, 0xFA, 0x28, 0x6B)  # REP #$10 / PLY / PLX / PLP / RTL
    asm.label("next").b(0xE8, 0xE8, 0xE8, 0xE8).rel(0x80, "loop")
    asm.label("none").b(0x64, 0x00, 0x64, 0x01).rel(0x80, "done")                 # STZ $00 / STZ $01
    asm.label("table").b(*(b for row in table for b in row), 0xFF)
    return asm.assemble()[0]


def rows(group_maps):
    """The routine's table from dq4environmentrom's report "group_maps" ({name: {"map": "GG/NN", "outside": [x, y]
    or None}})."""
    out = []
    for entry in group_maps.values():
        if entry.get("outside") is not None:
            g, n = (int(v, 16) for v in entry["map"].split("/"))
            out.append((g, n, *entry["outside"]))
    return sorted(out)


def writes(table):
    """dq5patch/1 writes: the way's routine pointer, the bank-00 stub and the routine with its table."""
    code = routine(table)
    if ROUTINE_AT + len(code) > ROUTINE_END:
        raise ValueError(f"outside routine overflows bank 57 by {ROUTINE_AT + len(code) - ROUTINE_END} bytes")
    stub = bytes((0x22, *ROUTINE_AT.to_bytes(3, "little"), 0x4C, *(COMMON_TAIL & 0xFFFF).to_bytes(2, "little")))
    if STUB_AT + len(stub) > STUB_END:
        raise ValueError("outside stub overflows 00:FFA8-FFAF")
    pointer = WAY_ROUTINES + OUTSIDE_WAY * 2
    return [
        {"at": _cpu(ROUTINE_AT), "hex": _hex(code), "note": f"맵 밖 칸을 바깥 블록 칸으로(맵 {len(table)}개)"},
        {"at": _cpu(STUB_AT), "hex": _hex(stub), "orig": _hex(bytes(len(stub))), "note": "맵 밖 칸 루틴 다리"},
        {"at": _cpu(pointer), "hex": _hex((STUB_AT & 0xFFFF).to_bytes(2, "little")), "orig": _hex(WAY_ROUTINE_ORIG),
         "note": f"맵 밖 칸 그리기 방법 {OUTSIDE_WAY} 을 바깥 블록으로"},
    ]


def _hex(data):
    return data.hex(" ").upper()


def _cpu(addr):
    return f"{addr >> 16:02X}:{addr & 0xFFFF:04X}"
