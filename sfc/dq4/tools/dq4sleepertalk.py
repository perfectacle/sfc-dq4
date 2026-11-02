"""Let the party talk to a sleeper from the foot of the bed, as FC does.

DQ5 picks whom the party talks to in 05:82C0. A person lying down (7E:31C0 bit0, entry 기타 bit7) is looked for by
05:84FE at two cells beside the cell the hero faces three cells ahead: facing up (x, y-3) and (x-1, y-3), down
(x, y+1) and (x-1, y+1), right (x+2, y-1) and (x+2, y-2), left (x-3, y-1) and (x-3, y-2). dq4npcport lays an FC
sleeper half a block right of its FC cell, at (2x+1, 2y), so from the FC foot of the bed (below, above or left of
it) the cell looked at is one to the left of the sleeper. FC answers there and not beside the head of the bed.

The hook makes 05:84FE look at the cell one to the right as well when the first finds nobody. Only people lying
down go through 05:84FE (05:8501 is the standing check), so no one else is reached from further away. The head side
stays as it was.

Format: sfc/dq4/docs/dq4-environment-format.md 「인물」.
"""

LYING_CHECK = 0x0584FE              # TDC / BRA 8503: look for a person lying down at ($00, $01)
LYING_CHECK_ORIG = bytes.fromhex("7B 80 02")
CHECK_BODY = 0x8503                 # 05:8503, A = 0 for the lying check; C set when found
HOOK_AT = 0x05FEF0                  # empty in the original ROM; local JSRs need bank 05


def code():
    lo, hi = CHECK_BODY & 0xFF, CHECK_BODY >> 8
    return bytes((
        0x7B,                   # TDC
        0x20, lo, hi,           # JSR $8503
        0xB0, 0x08,             # BCS done
        0xE6, 0x00,             # INC $00
        0x7B,                   # TDC
        0x20, lo, hi,           # JSR $8503
        0xC6, 0x00,             # DEC $00     (C kept)
        0x60,                   # done: RTS
    ))


def _cpu(addr):
    return f"{addr >> 16:02X}:{addr & 0xFFFF:04X}"


def writes(at=HOOK_AT):
    """dq5patch/1 writes: the hook at `at` (bank 05, local JSRs) and the jump to it from 05:84FE."""
    data = code()
    if at >> 16 != LYING_CHECK >> 16 or (at + len(data) - 1) >> 16 != at >> 16:
        raise ValueError("the hook must sit in bank 05")
    return [
        {"at": _cpu(at), "hex": data.hex(" ").upper(), "note": "누운 인물을 한 칸 오른쪽에서도 찾기(침대 발치에서 말 걸기)"},
        {"at": _cpu(LYING_CHECK), "hex": bytes((0x4C, at & 0xFF, (at >> 8) & 0xFF)).hex(" ").upper(),
         "orig": LYING_CHECK_ORIG.hex(" ").upper(), "note": "누운 인물 찾기를 훅으로"},
    ]
