"""2장 사건 전투 진입: 고정 무리의 이벤트 전투를 걸고, 이기면 공용 flag(dq4ch2slots.BATTLE_WON)를 켠다.

1장 탑 위 보스(dq4ch1event._battle)를 일반화한 것이다. 뱅크 06 의 공용 루틴 COMMON_AT 이 A(8비트) 의 무리 번호로
01:868B 를 부른다. 01:868B 는 전투 뒤 보통 조우와 같은 01:8715 로 가므로, 전멸(A = 80)이면 보통 전투처럼 전멸
처리(01:88ED, 교회로)를 한다. 루틴은 걸기 전에 BATTLE_WON 을 끄고, 전멸이 아니면 켠다. 사건 flag 는 부른 쪽이
BATTLE_WON 을 보고 켠다(대화 스크립트의 조건 1B, 인물 스크립트의 06·09).

부르는 길은 둘이다.
- 대화 스크립트: {"op": "call", "target": ...} 는 뱅크 06 안 주소만 받으므로 STUBS 의 입구(칸마다 무리 하나)를 쓴다.
  talk_call(칸).
- 네이티브(인물 스크립트 37, 이벤트 코드): far(무리) 바이트를 자기 사건 코드 자리에 두고 부른다.

형식은 sfc/dq4/docs/dq4-chapter2-format.md 「사건 전투」.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE)]

from dq4ch2slots import BATTLE_WON  # noqa: E402

# 뱅크 06 의 빈 자리 06:FF57~FFAF(1장 전투 06:FF00~·팡파르 06:FF40~ 뒤, 창 이름 훅 06:FFB0~ 앞)
COMMON_AT = 0x06FF58
STUBS_AT = 0x06FF81
STUB_SIZE = 9
STUB_COUNT = 5
END = 0x06FFB0
BATTLE = 0x01868B
WON_AT = 0x7E2190 + BATTLE_WON[0]
# 이벤트 무리 플래그: 도망칠 수 없음(bit6), 보스 곡(bit0-1 = 2). 1장 보스(dq4ch1event.BOSS_FLAGS)와 같음
BOSS_FLAGS = 0x40 | 0x02


def _al(a):
    return bytes((a & 0xFF, a >> 8 & 0xFF, a >> 16))


def common():
    """A = 무리 번호(8비트)로 부른다(JSL). P·DB 를 지키고 RTL. 데이터 뱅크를 06 으로 둔다: 대화 스크립트에서 부를 때와
    같고, BRK 는 부른 뱅크를 데이터 뱅크로 두므로 낮은 WRAM 거울이 있는 뱅크여야 한다."""
    clear = bytes((0xAF,)) + _al(WON_AT) + bytes((0x29, ~BATTLE_WON[1] & 0xFF, 0x8F)) + _al(WON_AT)
    win = bytes((0xAF,)) + _al(WON_AT) + bytes((0x09, BATTLE_WON[1], 0x8F)) + _al(WON_AT)
    return (bytes((0x08, 0xE2, 0x30, 0x8B, 0x4B, 0xAB, 0x48)) + clear +       # PHP / SEP #$30 / PHB / PHK / PLB / PHA
            bytes((0x00, 0x0E, 0x68, 0x22)) + _al(BATTLE) +                     # BRK 0E / PLA / JSL 01:868B
            bytes((0xC9, 0x80, 0xF0, len(win))) + win +                         # CMP #$80 / BEQ / 이김
            bytes((0xAB, 0x28, 0x6B)))                                          # PLB / PLP / RTL


def stub_at(k):
    if not 0 <= k < STUB_COUNT:
        raise ValueError(f'전투 입구 칸 {k}: 0~{STUB_COUNT - 1}')
    return STUBS_AT + STUB_SIZE * k


def stub(group):
    """대화 스크립트가 부르는 입구(JSR 로 들어와 RTS). SEP #$20 / LDA #무리 / JSL COMMON_AT / RTS."""
    return bytes((0xE2, 0x20, 0xA9, group, 0x22)) + _al(COMMON_AT) + b'\x60'


def talk_call(k):
    """대화 스크립트 명령: 입구 칸 k 의 전투를 건다."""
    return {"op": "call", "target": f"{stub_at(k) & 0xFFFF:04X}"}


def far(group):
    """네이티브 안에서 부르는 바이트(M 8, DB 아무것). A 를 덮는다."""
    return bytes((0xE2, 0x20, 0xA9, group, 0x22)) + _al(COMMON_AT)


def won_cond():
    """대화 스크립트 조건: 방금 건 전투를 이겼다."""
    return {"code": "1B", "index": BATTLE_WON[0], "mask": BATTLE_WON[1]}


def group_doc(group, members, flags=BOSS_FLAGS):
    """dq5encounter/1 의 event_groups 한 칸. members: [(DQ5 몬스터, 마릿수)]."""
    return {"index": group, "flags": flags, "members": [{"monster": m, "count": n} for m, n in members]}


def writes(stubs):
    """[(주소, 바이트)]: 공용 루틴과 입구들. stubs: {칸: 무리}."""
    out = [(COMMON_AT, common())]
    out += [(stub_at(k), stub(g)) for k, g in sorted(stubs.items())]
    for at, code in out:
        if at + len(code) > (STUBS_AT if at == COMMON_AT else END):
            raise ValueError(f'{at:06X}: 전투 진입 코드가 자리를 넘음')
    return out
