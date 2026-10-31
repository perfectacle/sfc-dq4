"""Fewer fights, bigger rewards: a deliberate change from FC DQ4 (sfc/dq4/docs/dq4-chapter1-format.md 「사용자 결정에
의한 원작과의 차이」).

Every encounter chance of the port is FC's times ENCOUNTER: the field terrain rates (dq4fieldencounter.terrain_rates)
and the dungeon step chances and region-change chance (dq4dungeonrate). The experience and gold a won fight gives are
the monsters' sums times REWARD, so the reward per step walked stays FC's.

The reward hook takes the JSL at VICTORY (20:8100, the first call of the victory sequence: 25:88D3 gives each living
member the experience sum 7E:10FC-10FE and prints it, 25:8C10 then adds the gold sum 7E:10FF-1101). 28:81F9 and
28:8235 add each beaten monster's field 72 and 73 to those sums, so at VICTORY they are final. The hook sets each sum
v to v + round(v / 3) (v + (v + 1) // 3, at most FFFFFF as 28:81F9 caps it), dividing by 3 a byte at a time with
the CPU divider (4204-4206, quotient 4214, remainder 4216), then goes on to 25:88D3. Event rewards that do not go
through a fight (the king's 3000) are not touched.
"""

from fractions import Fraction
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from dq4environmentrom import _Asm  # noqa: E402

ENCOUNTER = Fraction(3, 4)
REWARD = Fraction(4, 3)

VICTORY, GIVE = 0x208100, 0x2588D3
EXP_SUM, GOLD_SUM = 0x10FC, 0x10FF        # bank 7E
# Bank 57 holds the dungeon step chance from 8000 (dq4groupbuild.DUNGEON_RATE_AT); this goes at its end.
REWARD_AT = 0x57F000


def chance(value):
    """An FC chance or rate (out of 256) times ENCOUNTER, rounded half up; a non-zero one stays at least 1."""
    if not value:
        return 0
    return max(1, int(value * ENCOUNTER + Fraction(1, 2)))


def reward(value, top=0xFFFFFF):
    """A monster sum after the hook: v + (v + 1) // 3, at most `top`."""
    return min(top, value + (value + 1) // 3)


def code(at=REWARD_AT):
    if REWARD != Fraction(4, 3):
        raise ValueError("the hook adds a third: change its division with REWARD")
    asm = _Asm(at)
    # Entered by JSL from VICTORY in any M/X and DB; leaves by JML to GIVE, whose RTL returns behind VICTORY.
    asm.label("hook").b(0x08, 0x8B, 0xC2, 0x30, 0x48, 0xDA, 0x5A, 0xE2, 0x20)
    asm.b(0xA2, *EXP_SUM.to_bytes(2, "little")).word(0x20, "scale")
    asm.b(0xA2, *GOLD_SUM.to_bytes(2, "little")).word(0x20, "scale")
    asm.b(0xC2, 0x30, 0x7A, 0xFA, 0x68, 0xAB, 0x28, 0x5C, *GIVE.to_bytes(3, "little"))

    # scale: the 3-byte sum at 7E:X (M 8-bit, X 16-bit). Quotient bytes go on the stack high first, so they come
    # back low first for the add; CMP #2 on the last remainder is the rounding carry.
    asm.label("scale").b(0xA9, 0x00, 0x8F, 0x05, 0x42, 0x00)
    for k in (2, 1, 0):
        if k != 2:
            asm.b(0xAF, 0x16, 0x42, 0x00, 0x8F, 0x05, 0x42, 0x00)
        asm.b(0xBF, k, 0x00, 0x7E, 0x8F, 0x04, 0x42, 0x00, 0xA9, 0x03, 0x8F, 0x06, 0x42, 0x00)
        asm.b(*[0xEA] * 8, 0xAF, 0x14, 0x42, 0x00, 0x48)
    asm.b(0xAF, 0x16, 0x42, 0x00, 0xC9, 0x02)
    for k in (0, 1, 2):
        asm.b(0x68, 0x7F, k, 0x00, 0x7E, 0x9F, k, 0x00, 0x7E)
    asm.rel(0x90, "done").b(0xA9, 0xFF, 0x9F, 0x00, 0x00, 0x7E, 0x9F, 0x01, 0x00, 0x7E, 0x9F, 0x02, 0x00, 0x7E)
    asm.label("done").b(0x60)
    return asm.assemble()


def writes(at=REWARD_AT):
    """dq5patch/1 writes: the reward hook at `at` and the JSL at VICTORY."""
    data, labels = code(at)
    if at >> 16 != (at + len(data) - 1) >> 16:
        raise ValueError("reward hook crosses a bank")
    return [
        {"at": _cpu(at), "hex": data.hex(" ").upper(), "note": "전투 경험치·금화 합계를 4/3 배로"},
        {"at": _cpu(VICTORY), "hex": bytes((0x22, *labels["hook"].to_bytes(3, "little"))).hex(" ").upper(),
         "orig": bytes((0x22, *GIVE.to_bytes(3, "little"))).hex(" ").upper(),
         "note": "승리 처리 첫 호출을 보상 훅으로"},
    ]


def _cpu(addr):
    return f"{addr >> 16:02X}:{addr & 0xFFFF:04X}"
