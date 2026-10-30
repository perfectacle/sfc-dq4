"""Shop and inn keys per FC group instead of per DQ5 group.

DQ5 keys the weapon, armor and item lists and the inn prices by the map group $BC. A DQ5 group that holds
several FC groups needs one key per FC group, so both reads of $BC first look up (group $BC, map $BD in
[first, last]) and take that row's key:

  shop  06:DC37 LDA $BC / STA $0F25 (the key 06:F49C searches the lists for). Any M width: the hook writes
        $0F25 (and $0F26 = $BD with 16-bit A) the way the original pair would, and leaves A and N/Z as its LDA.
  inn   06:F576 LDA $BC / STA $02 (the key the loop 06:F57A searches the price table for), with 8-bit A.

Maps not in the table keep $BC. Keys must avoid the DQ5 groups (00-35, among them 01/21/22 that 06:F58E
treats apart) and the list end FF, so they start at KEY_FIRST.
"""

import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from dq4environmentrom import _Asm  # noqa: E402

# 06:DC3B (STA's last byte) gets a NOP; nothing in the ROM branches or points into 06:DC38-06:DC3B.
SHOP_SITE, SHOP_ORIG = 0x06DC37, bytes((0xA5, 0xBC, 0x8D, 0x25, 0x0F))
INN_SITE, INN_ORIG = 0x06F576, bytes((0xA5, 0xBC, 0x85, 0x02))
KEY_FIRST, KEY_LAST = 0x60, 0xFE
ROW_SIZE = 4


def table(rows):
    """rows: (DQ5 group, first map, last map, key)."""
    out, keys = bytearray(), set()
    for group, first, last, key in rows:
        if not first <= last <= 0x1F:
            raise ValueError(f"{group:02X}: map range {first:02X}-{last:02X}")
        if not KEY_FIRST <= key <= KEY_LAST or key in keys:
            raise ValueError(f"{group:02X} {first:02X}-{last:02X}: key {key:02X}")
        keys.add(key)
        out += bytes((group, first, last, key))
    return bytes(out) + b"\xFF"


def code(at, rows):
    """(bytes at `at`, labels): both routines, the lookup they share, and the table."""
    asm = _Asm(at)
    # shop: B gets $BD only when the caller has 16-bit A (P on the stack at 4,S), as LDA $BC would load it.
    asm.label("shop").b(0x08, 0xC2, 0x10, 0xDA, 0xE2, 0x20).word(0x20, "find").b(0x48, 0xA3, 0x04, 0x29, 0x20)
    asm.rel(0xD0, "s_keep").b(0xA5, 0xBD, 0xEB)
    # The long store and load: the caller's DB is not known, and the load sets N/Z in the caller's width.
    asm.label("s_keep").b(0x68, 0xFA, 0x28, 0x8F, 0x25, 0x0F, 0x7E, 0xAF, 0x25, 0x0F, 0x7E, 0x6B)
    # inn: runs with DB = the inn table bank, so the table is read with long addresses only.
    asm.label("inn").b(0x08, 0xE2, 0x20, 0xC2, 0x10, 0xDA).word(0x20, "find").b(0xFA, 0x28, 0x85, 0x02, 0x6B)
    # find: 8-bit A, 16-bit X; A = the key or $BC. B is left alone.
    asm.label("find").b(0xA2, 0x00, 0x00)
    asm.label("f_loop").long(0xBF, "keys").b(0xC9, 0xFF).rel(0xF0, "f_miss").b(0xC5, 0xBC).rel(0xD0, "f_next")
    asm.b(0xA5, 0xBD, 0x29, 0x1F).long(0xDF, "keys", 1).rel(0x90, "f_next").long(0xDF, "keys", 2)
    asm.rel(0xF0, "f_hit").rel(0xB0, "f_next")
    asm.label("f_hit").long(0xBF, "keys", 3).b(0x60)
    asm.label("f_next").b(*(0xE8,) * ROW_SIZE).rel(0x80, "f_loop")
    asm.label("f_miss").b(0xA5, 0xBC, 0x60)
    asm.label("keys").b(*table(rows))
    return asm.assemble()


def writes(at, rows):
    """dq5patch/1 writes: the routines with their table, and the two JSLs."""
    data, labels = code(at, rows)
    if at >> 16 != (at + len(data) - 1) >> 16:
        raise ValueError("shop key hook crosses a bank")
    return [
        {"at": _cpu(at), "hex": data.hex(" ").upper(), "note": "FC 그룹별 가게·여관 키 루틴과 표"},
        {"at": _cpu(SHOP_SITE), "hex": _jsl(labels["shop"]) + " EA", "orig": SHOP_ORIG.hex(" ").upper(),
         "note": "가게 목록 키($0F25)를 FC 그룹별 키로"},
        {"at": _cpu(INN_SITE), "hex": _jsl(labels["inn"]), "orig": INN_ORIG.hex(" ").upper(),
         "note": "여관 값 표 키($02)를 FC 그룹별 키로"},
    ]


def _jsl(target):
    return bytes((0x22, *target.to_bytes(3, "little"))).hex(" ").upper()


def _cpu(addr):
    return f"{addr >> 16:02X}:{addr & 0xFFFF:04X}"
