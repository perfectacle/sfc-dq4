"""Field entrances that pick their own arrival, and maps that pick their own field cell.

DQ5 keeps one arrival per group (the entrance table of dq5newmap) and, leaving for the field, stands on the
first field entrance of the group (2A:F425). A DQ5 group that holds several FC groups needs both per entrance:

  enter  2A:F28D (the per-map exceptions, run after 2A:F384 set the group's arrival on the main and the aux
         entrance paths, and by the indoor day/night redraw 2A:F363) first looks up (group $BC, field $B6, $B8) and overwrites $BD, $C1, $C2, $C3, $198E.
  leave  2A:F425 first looks up (group $BC, map $BD in [first, last]) and stands on its field cell.

Entries not in a table keep the original behaviour.
"""

import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from dq4environmentrom import _Asm  # noqa: E402

ENTER_SITE, ENTER_ORIG, ENTER_BACK = 0x2AF28D, bytes((0xA5, 0xBC, 0xC9, 0x16)), 0x2AF291
# 2A:F429 (the REP's operand) stays: the hook never returns before 2A:F42A.
LEAVE_SITE, LEAVE_ORIG, LEAVE_ON, LEAVE_BACK = 0x2AF425, bytes((0x08, 0xE2, 0x20, 0xC2)), 0x2AF475, 0x2AF42A
ARRIVAL_SIZE, FIELD_SIZE = 10, 7


def tables(arrivals, fields):
    """arrivals: (group, field x, field y, map, x, y, layer, $198E); fields: (group, first map, last map, x, y)."""
    arr = bytearray()
    for group, fx, fy, number, x, y, layer, facing in arrivals:
        # The original masks both (2A:F397 AND #$1F, 2A:F3B1 AND #$83); the hook stores them as given.
        if number > 0x1F or facing & ~0x83:
            raise ValueError(f"{group:02X} ({fx},{fy}): map {number:02X} or facing {facing:02X} out of range")
        arr += bytes((group,)) + fx.to_bytes(2, "little") + fy.to_bytes(2, "little") + bytes((number, x, y, layer, facing))
    out = bytearray()
    for group, first, last, fx, fy in fields:
        if not first <= last <= 0x1F:
            raise ValueError(f"{group:02X}: map range {first:02X}-{last:02X}")
        out += bytes((group, first, last)) + fx.to_bytes(2, "little") + fy.to_bytes(2, "little")
    return bytes(arr) + b"\xFF", bytes(out) + b"\xFF"


def code(at, arrivals, fields):
    """(bytes at `at`, labels): both routines, then both tables."""
    asm = _Asm(at)
    # enter: any M/X width (2A:F286 sets both 8-bit, 2A:F379 has 16-bit X); P and the full X are kept.
    asm.label("enter").b(0x08, 0xC2, 0x10, 0xE2, 0x20, 0xDA, 0xA2, 0x00, 0x00)
    asm.label("e_loop").long(0xBF, "arr").b(0xC9, 0xFF).rel(0xF0, "e_done").b(0xC5, 0xBC).rel(0xD0, "e_next")
    asm.b(0xC2, 0x20).long(0xBF, "arr", 1).b(0xC5, 0xB6).rel(0xD0, "e_next")
    asm.long(0xBF, "arr", 3).b(0xC5, 0xB8).rel(0xD0, "e_next").b(0xE2, 0x20)
    for offset, dp in ((5, 0xBD), (6, 0xC1), (7, 0xC2), (8, 0xC3)):
        asm.long(0xBF, "arr", offset).b(0x85, dp)
    # $198E with a long store: the data bank here is whatever the field code left.
    asm.long(0xBF, "arr", 9).b(0x8F, 0x8E, 0x19, 0x7E).rel(0x80, "e_done")
    asm.label("e_next").b(0xC2, 0x20, 0x8A, 0x18, 0x69, ARRIVAL_SIZE, 0x00, 0xAA, 0xE2, 0x20).rel(0x80, "e_loop")
    asm.label("e_done").b(0xFA, 0x28, *ENTER_ORIG, 0x5C, *ENTER_BACK.to_bytes(3, "little"))
    # leave: the original first three instructions, then the lookup; 2A:F475 expects 16-bit A and the PHP.
    asm.label("leave").b(0x08, 0xE2, 0x20, 0xC2, 0x10, 0xA2, 0x00, 0x00)
    asm.label("l_loop").long(0xBF, "out").b(0xC9, 0xFF).rel(0xF0, "l_back").b(0xC5, 0xBC).rel(0xD0, "l_next")
    asm.b(0xA5, 0xBD, 0x29, 0x1F).long(0xDF, "out", 1).rel(0x90, "l_next").long(0xDF, "out", 2)
    asm.rel(0xF0, "l_hit").rel(0xB0, "l_next")
    asm.label("l_hit").b(0xC2, 0x20).long(0xBF, "out", 3).b(0x85, 0xB6).long(0xBF, "out", 5).b(0x85, 0xB8)
    asm.b(0x5C, *LEAVE_ON.to_bytes(3, "little"))
    asm.label("l_next").b(*(0xE8,) * FIELD_SIZE).rel(0x80, "l_loop")
    asm.label("l_back").b(0x5C, *LEAVE_BACK.to_bytes(3, "little"))
    arr, out = tables(arrivals, fields)
    asm.label("arr").b(*arr).label("out").b(*out)
    return asm.assemble()


def writes(at, arrivals, fields):
    """dq5patch/1 writes: the routines with their tables, and the two JMLs."""
    data, labels = code(at, arrivals, fields)
    if at >> 16 != (at + len(data) - 1) >> 16:
        raise ValueError("entrance hook crosses a bank")
    return [
        {"at": _cpu(at), "hex": data.hex(" ").upper(), "note": "입구별 도착·맵별 필드 자리 루틴과 표"},
        {"at": _cpu(ENTER_SITE), "hex": _jml(labels["enter"]), "orig": ENTER_ORIG.hex(" ").upper(),
         "note": "맵별 예외 앞에서 입구별 도착을 덮음"},
        {"at": _cpu(LEAVE_SITE), "hex": _jml(labels["leave"]), "orig": LEAVE_ORIG.hex(" ").upper(),
         "note": "필드로 나올 때 맵별 필드 자리를 먼저 찾음"},
    ]


def _jml(target):
    return bytes((0x5C, *target.to_bytes(3, "little"))).hex(" ").upper()


def _cpu(addr):
    return f"{addr >> 16:02X}:{addr & 0xFFFF:04X}"
