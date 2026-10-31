"""Doors: the front cell of the door command, and doors that open when walked into.

DQ5's door command (01:D8C2) and the other door entries find the door in front with 01:D9E5. Its first check,
01:DA4D, takes the 2x3 doors (kinds 3B-3E, 43, 45, 46, 4D, cell +7 = kind | 80). Such a door marks only its
bottom-right cell; the door's entry in the object table (01:D2FC) is that cell minus (1, 2). The hero's cell
($C1, $C2, kept in 7E:1E8C-1E8D by 01:D9CE) is the top-left of the 2x2 the hero covers, and DA4D looks only at
(X+1, Y-1) facing up and (X+1, Y+1) facing down. The hero walks in 8-pixel cells, so a hero half a block to the
left or right of a door (X = door X - 1 or + 1) misses the mark and gets 「その方向には トビラがない！」.

FIND replaces DA4D (JSL from 01:DA4D) and looks at the cells a hero touching the door could face:

  up     row Y-1, columns X+1, X+2, X
  down   row Y+1, columns X+1, X+2, X
  left   column X-1, rows Y, Y+1 (a door between rooms side by side: the hero walks along the door's bottom row,
         the only row of the object that blocks)
  right  column X+3, rows Y, Y+1

and sets 1E71/1E72 (the mark), 1E8A/1E8B (the entry) and 1E76 (the kind) as DA4D does. DA4D's call of 01:DADB (on
DQ5 maps 23/00 and 18/00, no door above row 20 for a hero on floor 1) is kept in FIND.

With AUTO_OPEN, a deliberate change from FC DQ4 (sfc/dq4/docs/dq4-chapter1-format.md 「사용자 결정에 의한 원작과의
차이」): when a step is blocked indoors on foot (00:81B7, after 00:A97D said blocked and 81F1 put the pressed
direction in 7E:31E0, which D9CE copies to 1E8F), AUTO runs the door finders of D9E5 except the water gate (D7) and
the counter (4A, CA), and opens the door with 01:DFAB (sound and picture as the command) when 01:DCFC says open. A locked door without the key
shows the door command's message (01:D8FC) once per push, as NDS shows 「トビラには カギが かかっている！」 and stops
the hero: $1958, the directions already bumped that 00:83B4 keeps for its sound, says whether this push showed it.
Doors of lock kind 4 and up (special story doors, whose lock code prints messages itself) stay shut without a message.
When it opened nothing and showed nothing, AUTO goes on with 00:83B4 (the bump sound) as before.
"""

import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from dq4environmentrom import _Asm  # noqa: E402

AUTO_OPEN = True

# FIND goes after dq4balance's reward hook in bank 57; AUTO in bank 01's empty tail from FED0 (it calls bank-01
# routines by JSR), above the stubs dq4environmentrom keeps below its HOOK_END.
FIND_AT = 0x57F400
AUTO_AT, AUTO_END = 0x01FF00, 0x020000
DA4D, DA4D_ORIG = 0x01DA4D, bytes((0x20, 0x2D, 0xF0, 0x10, 0x04))       # JSR $F02D / BPL $DA56, M/X 8-bit
BLOCKED, BLOCKED_ORIG = 0x0081B7, bytes((0x20, 0xB4, 0x83, 0x9C, 0x5A, 0x19))   # JSR $83B4 / STZ $195A
BUMP = 0x0083B4
# The RTL of a bank-00 routine (00:880C PLB PLP RTL), for calling the RTS routine BUMP from bank 01.
RTL00 = 0x00880E
TWO_BY_THREE = (0xBB, 0xBC, 0xBD, 0xBE, 0xC3, 0xC5, 0xC6, 0xCD)   # 01:DA73-DA8F
CELL_UPPER = 0x25F9F4         # A=1, X/Y cell: A = cell +7; keeps X and Y
WRAM = 0x7E0000

OFFSETS = {
    "up": [(1, -1), (2, -1), (0, -1)],
    "down": [(1, 1), (2, 1), (0, 1)],
    "left": [(-1, 0), (-1, 1)],
    "right": [(3, 0), (3, 1)],
}


def _long(addr):
    return (WRAM | addr).to_bytes(3, "little")


def find_code(at=FIND_AT):
    """FIND, entered by JSL from DA4D in D9E5's chain (M/X 8-bit, D = 0, DB 01); RTL with carry as DA4D's RTS."""
    asm = _Asm(at)
    asm.label("find").b(0x8B, 0x4B, 0xAB, 0xAF, *_long(0x1E8F))         # PHB PHK PLB / LDA $7E1E8F
    for direction in ("up", "down", "left", "right"):
        asm.b(0xA0).label(f"y_{direction}").b(0x00)                    # LDY #index (set below)
        asm.b(0x0A).rel(0xB0, "scan")                                   # ASL / BCS scan
    asm.rel(0x80, "none")
    asm.label("scan").word(0xB9, "offsets").b(0xC9, 0x80).rel(0xF0, "none")   # LDA offsets,Y / CMP #$80
    asm.b(0x18, 0x6F, *_long(0x1E8C), 0xAA)                             # CLC / ADC $7E1E8C / TAX
    asm.word(0xB9, "offsets", 1).b(0x18, 0x6F, *_long(0x1E8D))         # LDA offsets+1,Y / CLC / ADC $7E1E8D
    asm.b(0x5A, 0xA8)                                                    # PHY / TAY
    asm.b(0xE4, 0xBF).rel(0xB0, "next").b(0xC4, 0xC0).rel(0xB0, "next")  # inside the map: X < $BF, Y < $C0
    asm.b(0xA9, 0x01, 0x22, *CELL_UPPER.to_bytes(3, "little"))
    asm.b(0x5A, 0xA0, len(TWO_BY_THREE) - 1)                            # PHY / LDY #n-1
    asm.label("kind").word(0xD9, "kinds").rel(0xF0, "hit").b(0x88).rel(0x10, "kind")   # CMP kinds,Y / DEY / BPL
    asm.b(0x7A)                                                          # PLY
    asm.label("next").b(0x7A, 0xC8, 0xC8).rel(0x80, "scan")             # PLY / INY / INY / BRA scan
    asm.label("none").b(0xAB, 0xE2, 0x30, 0x18, 0x6B)                   # PLB / SEP #$30 / CLC / RTL (as 01:DA06)
    asm.label("hit").b(0x7A, 0x8F, *_long(0x1E76), 0x68, 0xAB)         # PLY / STA $7E1E76 / PLA (index) / PLB
    asm.b(0x8E, 0x71, 0x1E, 0x8C, 0x72, 0x1E)                           # STX $1E71 / STY $1E72
    asm.b(0x8A, 0x3A, 0x8D, 0x8A, 0x1E, 0x98, 0x3A, 0x3A, 0x8D, 0x8B, 0x1E)   # entry = mark - (1, 2)
    # 01:DADB: on 23/00 and 18/00 a hero on floor 1 (1E8E) finds no door above row 20 (1E8D).
    asm.b(0xA5, 0xBD).rel(0xD0, "ok").b(0xA5, 0xBC, 0xC9, 0x23).rel(0xF0, "floor").b(0xC9, 0x18).rel(0xD0, "ok")
    asm.label("floor").b(0xAD, 0x8D, 0x1E, 0xC9, 0x20).rel(0xB0, "ok")
    asm.b(0xAD, 0x8E, 0x1E, 0xC9, 0x01).rel(0xD0, "ok").b(0xE2, 0x30, 0x18, 0x6B)
    asm.label("ok").b(0xAD, 0x76, 0x1E, 0x38, 0x6B)                     # LDA $1E76 / SEC / RTL
    asm.label("kinds").b(*TWO_BY_THREE)
    asm.label("offsets")
    index, pos = {}, 0
    for direction in ("up", "down", "left", "right"):
        index[direction] = pos
        for dx, dy in OFFSETS[direction]:
            asm.b(dx & 0xFF, dy & 0xFF)
            pos += 2
        asm.b(0x80, 0x80)
        pos += 2
    data, labels = asm.assemble()
    out = bytearray(data)
    for direction, value in index.items():
        out[labels[f"y_{direction}"] - at] = value
    return bytes(out), labels


def auto_code(at=AUTO_AT):
    """AUTO, entered by JSL from BLOCKED in any M/X and DB; leaves by RTL behind it."""
    asm = _Asm(at)
    word = lambda v: (v & 0xFF, v >> 8 & 0xFF)  # noqa: E731
    asm.label("auto").b(0x08, 0x8B, 0x4B, 0xAB, 0xC2, 0x30, 0x48, 0xDA, 0x5A, 0xE2, 0x30)
    asm.b(0x20).word(None, "try").rel(0xB0, "opened")                  # JSR try / BCS opened (or told)
    # JSR to BUMP from bank 01: its RTS lands on RTL00, whose RTL comes back to "opened".
    asm.b(0x4B, 0xF4).word(None, "opened", -1).b(0xF4, *word(RTL00 - 1), 0x5C, *BUMP.to_bytes(3, "little"))
    asm.label("opened").b(0xE2, 0x30, 0xA9, 0x00, 0x8F, *_long(0x195A))   # SEP #$30 / STZ $195A as BLOCKED did
    asm.b(0xC2, 0x30, 0x7A, 0xFA, 0x68, 0xAB, 0x28, 0x6B)
    # try: carry set when a door opened or its lock message showed. M/X 8-bit, DB 01 (the door routines' own).
    asm.label("try").b(0xA5, 0xBE).rel(0x10, "shut")                   # indoors ($BE bit7)
    asm.b(0xAD, 0x54, 0x19).rel(0xD0, "shut")                           # on foot ($1954 = 0)
    asm.b(0x20, 0xCE, 0xD9)                                              # JSR $D9CE (hero cell, facing)
    for finder in (0xDA4D, 0xDB06, 0xDB96):
        asm.b(0x20, *word(finder)).rel(0xB0, "door")
    asm.b(0x20, 0x5C, 0xDC).rel(0x90, "shut")
    # The lock kind from 01:DE49, which steps 1E8B back for kinds C1, C2, C9: keep 1E8B for DCFC's own call.
    asm.label("door").b(0xC9, 0x4A).rel(0xF0, "shut")
    asm.b(0xAE, 0x8B, 0x1E, 0xDA, 0x20, 0x49, 0xDE, 0xA8, 0xFA, 0x8E, 0x8B, 0x1E)
    asm.b(0xC0, 0x04).rel(0xB0, "shut")
    asm.b(0xAD, 0x76, 0x1E, 0x20, 0xFC, 0xDC, 0xE2, 0x30).rel(0x90, "shut")   # LDA $1E76 / JSR $DCFC
    asm.b(0xAA).rel(0xD0, "locked").b(0x20, 0xAB, 0xDF, 0xE2, 0x30, 0x38, 0x60)  # TAX / BNE / JSR $DFAB / SEC
    # Locked: the door command's message for the result (01:D8FC: 1 -> 187, 2 -> 188, 3 -> 315), once per push. $1958
    # holds the directions already bumped (00:83B4 sounds the bump only for a new one; walking on clears it).
    asm.label("locked").b(0xAD, 0x58, 0x19, 0x25, 0xC4).rel(0xD0, "shut")      # LDA $1958 / AND $C4 / BNE shut
    asm.b(0xA5, 0xC4, 0x0C, 0x58, 0x19, 0x8A, 0x20, 0xFC, 0xD8, 0xE2, 0x30, 0x38, 0x60)   # TSB $1958 / TXA / JSR $D8FC
    asm.label("shut").b(0xE2, 0x30, 0x18, 0x60)
    return asm.assemble()


def writes():
    """dq5patch/1 writes: FIND in bank 57 and the JSL at DA4D; with AUTO_OPEN, AUTO in bank 01 and its call."""
    find, flabels = find_code()
    if FIND_AT >> 16 != (FIND_AT + len(find) - 1) >> 16:
        raise ValueError("door finder crosses a bank")
    out = [
        {"at": _cpu(FIND_AT), "hex": _hex(find), "note": "2×3 문 찾기(반 칸 걸침·옆·위에서)"},
        {"at": _cpu(DA4D), "hex": _hex(bytes((0x22, *flabels["find"].to_bytes(3, "little"), 0x60))),
         "orig": _hex(DA4D_ORIG), "note": "01:DA4D 를 넓은 문 찾기로"},
    ]
    if AUTO_OPEN:
        auto, alabels = auto_code()
        if AUTO_AT + len(auto) > AUTO_END:
            raise ValueError(f"door code overflows bank 01 by {AUTO_AT + len(auto) - AUTO_END} bytes")
        out += [
            {"at": _cpu(AUTO_AT), "hex": _hex(auto), "note": "걸음이 막히면 앞의 문을 열기"},
            {"at": _cpu(BLOCKED), "hex": _hex(bytes((0x22, *alabels["auto"].to_bytes(3, "little"), 0xEA, 0xEA))),
             "orig": _hex(BLOCKED_ORIG), "note": "막힌 걸음에서 문 열기 코드로"},
            {"at": _cpu(RTL00), "hex": "6B", "orig": "6B", "note": "문 열기 코드가 00:83B4 에서 돌아올 RTL"},
        ]
    return out


def _hex(data):
    return data.hex(" ").upper()


def _cpu(addr):
    return f"{addr >> 16:02X}:{addr & 0xFFFF:04X}"
