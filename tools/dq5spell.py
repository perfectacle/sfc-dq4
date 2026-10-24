"""DQ5(SFC) 주문·행동 표. 형식은 docs/dq5-data-format.md 의 「주문과 행동」.

행동 번호(주문 01~38, 몬스터용 주문 39~65, 몬스터 행동 66~AA)는 이름 표 3번(21:959B)과 순서가 같다.
  MP·범위   26:8765[행동] (26:839A·26:83D0). bit0-4 MP(1F 없음, 1E = 36, 1D = 남은 MP 전부), bit5-6 범위, bit7 적 쪽
  처리 루틴 20:B7F9 + 행동*2. 루틴 첫머리가 LDX #내성 종류 / LDA #표 번호 를 넣고 공통 루틴으로 뛴다
  피해·회복량 27:8071 + (표 번호 & 3F)*2 = [바탕][폭]. 값 = 바탕(FE 이면 300) + 난수(0 ~ 폭-1) (20:AB70)
내성 종류(50~61)는 몬스터 레코드 +0C~+10 의 2비트 칸이다(21:91F9 + 종류*2, tools/dq5monster.py).

사용:
  python tools/dq5spell.py rom/dq5.sfc
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5map import Rom  # noqa: E402
from dq5text import string, string_codes, text  # noqa: E402

NAMES = 3
COUNT = 0xAB
COSTS = 0x268765
HANDLERS = 0x20B7F9
AMOUNTS = 0x278071
RANGES = ('자신', '하나', '그룹', '전체')
# 20:B307(주문)·20:B657(숨)·20:AB70 은 27:8071 의 양을 쓰고, 20:AE41·AEC6·AEFF 는 내성으로 성공을 가른다.
AMOUNT_ROUTINES = (0xB307, 0xB657, 0xAB70)
STATUS_ROUTINES = (0xAE41, 0xAEC6, 0xAEFF)


def name(rom, n):
    return text(string_codes(rom, string(rom, NAMES, n)))


def cost(rom, n):
    """26:839A. (MP, 범위 0~3, 적 쪽인가). MP 가 None 이면 MP 를 쓰지 않는 행동."""
    v = rom.u8(COSTS + n)
    mp = {0x1F: None, 0x1E: 36, 0x1D: 'all'}.get(v & 0x1F, v & 0x1F)
    return mp, (v >> 5) & 3, bool(v & 0x80)


def handler(rom, n):
    """20:B7F9 의 루틴 주소와, 첫머리에서 읽은 (LDA #, LDX #, 뛰는 곳)."""
    a = 0x200000 | rom.u16(HANDLERS + n * 2)
    p, lda, ldx = a, None, None
    if rom.u8(p) == 0xE2:
        p += 2
    for _ in range(4):
        op = rom.u8(p)
        if op == 0xA9:
            lda = rom.u8(p + 1)
        elif op == 0xA2:
            ldx = rom.u8(p + 1)
        elif op == 0x86:
            pass
        elif op in (0x4C, 0x20):
            return a & 0xFFFF, lda, ldx, rom.u16(p + 1)
        else:
            break
        p += 2
    return a & 0xFFFF, lda, ldx, None


def amount(rom, k):
    """27:8071. 표 번호 k 의 (바탕, 폭)."""
    a = AMOUNTS + (k & 0x3F) * 2
    base = rom.u8(a)
    return 300 if base == 0xFE else base, rom.u8(a + 1)


def describe(rom, n):
    mp, rng, enemy = cost(rom, n)
    addr, lda, ldx, target = handler(rom, n)
    out = [f'{n:02X}', name(rom, n)]
    out.append('MP-' if mp is None else f'MP{mp}')
    out.append(('적 ' if enemy else '편 ') + RANGES[rng])
    out.append(f'루틴{addr:04X}')
    if target in AMOUNT_ROUTINES and lda is not None:
        base, width = amount(rom, lda)
        out.append(f'양{lda:02X}={base}~{base + max(width, 1) - 1}')
    elif target in STATUS_ROUTINES and lda is not None:
        out.append(f'값{lda:02X}')
    if ldx is not None and ldx >= 0x50 and target is not None:
        out.append(f'내성{ldx:02X}')
    return ' '.join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    args = ap.parse_args()
    rom = Rom(open(args.rom, 'rb').read())
    for n in range(COUNT):
        print(describe(rom, n))
    return 0


if __name__ == '__main__':
    sys.exit(main())
