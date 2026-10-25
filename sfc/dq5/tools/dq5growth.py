"""DQ5(SFC) 레벨업 성장 표. 형식은 sfc/dq5/docs/dq5-data-format.md 의 「레벨업 성장」.

레벨이 오를 때 23:EB50 이 일행 레코드 +0(종류)으로 성장 레코드를 고른다(23:EDCD).
  +0 < 80 이면 사람: 23:9E41 + (+0 & 3F) * 50(11개),  80 이상이면 동료 몬스터: 23:A1B1 + (+0 & 3F) * 50(종류 00~29)
성장 레코드 50 바이트:
  +0       꺾이는 레벨 수 n(주인공 7)
  +2~      꺾이는 레벨 n 개(주인공 5 10 15 20 30 45 60)
  +11 +1A +23 +2C +35 +3E +47   능력치 7개의 값 9바이트씩(23:F126): 레벨 1, 꺾이는 레벨들, 끝(레벨 99)
                                 순서는 최대 HP, 최대 MP, ちから(+7), すばやさ(+6), かしこさ(+9), うんのよさ(+A), みのまもり(+8)
레벨 L 의 값(23:F12D): 꺾이는 레벨 사이를 직선으로 잇고 나머지는 버린다. HP·MP 는 레벨 1 칸 밖의 값을 2배로 읽는다(23:F0A6).
  마지막 꺾이는 레벨 뒤는 레벨 100 까지 끝 값으로 잇고, 레벨 99 는 끝 값 그대로.
오르는 양(23:EC00): 값(L+1) - 값(L). 다만 지금 능력치가 0 이 아니고 값(L) + 값(L)/2 이상이면 난수 0 또는 1(23:EC8E).
경험치(23:EDF6, exp_at): +1 과 +9~ 의 배수 바이트로 만든 누적 곡선. 다음 레벨 경험치(일행 레코드 +26)는 exp_at(레벨 + 1).

사용:
  python sfc/dq5/tools/dq5growth.py rom/dq5.sfc                 # 주인공 레벨 1~99 표
  python sfc/dq5/tools/dq5growth.py rom/dq5.sfc --monster 02    # 동료 몬스터 종류 02(スライム)
  python sfc/dq5/tools/dq5growth.py rom/dq5.sfc --person 0 --level 10
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5map import Rom  # noqa: E402

PEOPLE = 0x239E41
MONSTERS = 0x23A1B1
RECORD = 0x50
STAT_OFFSETS = (0x11, 0x1A, 0x23, 0x2C, 0x35, 0x3E, 0x47)
STATS = ('최대HP', '최대MP', 'ちから', 'すばやさ', 'かしこさ', 'うんのよさ', 'みのまもり')
# 능력치 순번 → 일행 레코드 안 자리
RECORD_FIELD = (0x0E, 0x10, 0x07, 0x06, 0x09, 0x0A, 0x08)


def record_address(kind):
    """일행 레코드 +0(종류) → 성장 레코드 주소(23:EDCD)."""
    base = MONSTERS if kind & 0x80 else PEOPLE
    return base + (kind & 0x3F) * RECORD


def stat_at(rom, rec, stat, level):
    """23:F12D. 성장 레코드 rec 의 능력치 stat 을 레벨 level 에서."""
    count = rom.u8(rec)
    points = [1] + [rom.u8(rec + 2 + k) for k in range(count)] + [100]
    base = rec + STAT_OFFSETS[stat]

    for k in range(len(points) - 1):
        lo, hi = points[k], points[k + 1]
        if lo <= level < hi or (k == len(points) - 2 and level >= lo):
            v0 = rom.u8(base + k)
            v1 = rom.u8(base + (k + 1 if k + 1 <= count else 8))
            # 23:F0A6: HP·MP 는 구간 시작 값(레벨 1 이 아닐 때)과 끝 값을 2배로 읽는다
            if stat < 2:
                if lo >= 2:
                    v0 *= 2
                v1 *= 2
            if level == 99 and hi == 100:
                return v1
            if level == lo:
                return v0
            return v0 + (v1 - v0) * (level - lo) // (hi - lo)
    raise ValueError(level)


def exp_at(rom, rec, level):
    """23:EDF6. 레벨 level 이 되는 누적 경험치. 값은 1/32 단위 고정소수점으로 셈한다.

    v(1) = 0, v(2) = +1. v(L) = v(L-1) + (v(L-1) - v(L-2)) × 배수. 배수 바이트 = +9 + (지난 꺾이는 레벨 수),
    아래 3비트가 정수, 위 5비트가 1/32. 곱은 23:F029 처럼 소수끼리의 곱도 1/32 로 더한다. 10000000 에서 멈춘다.
    """
    count = rom.u8(rec)
    if level <= 1:
        return 0
    prev, cur = (0, 0), (rom.u8(rec + 1), 0)
    k = 0
    for lv in range(3, level + 1):
        if k < count and rom.u8(rec + 2 + k) == lv:
            k += 1
        f = rom.u8(rec + 9 + k)
        fi, ff = f & 7, f >> 3
        di, df = cur[0] - prev[0], cur[1] + 32 - prev[1]
        if df < 32:
            di -= 1
        else:
            df -= 32
        part = di * ff + df * fi + df * ff
        ri, rf = di * fi + (part >> 5), part & 31
        ni, nf = cur[0] + ri, cur[1] + rf
        if nf >= 32:
            ni, nf = ni + 1, nf - 32
        if ni >= 0x989681:
            ni = 0x989680
        prev, cur = cur, (ni, nf)
    return cur[0]


def stats_at(rom, rec, level):
    return [stat_at(rom, rec, s, level) for s in range(len(STATS))]


def gains(rom, rec, level, current=None):
    """레벨 level → level+1 에서 오르는 양. current 가 있으면 1.5배 규칙으로 난수 칸을 None 으로."""
    a, b = stats_at(rom, rec, level), stats_at(rom, rec, level + 1)
    out = []
    for s in range(len(STATS)):
        if current is not None and current[s] and current[s] >= a[s] + (a[s] >> 1):
            out.append(None)
        else:
            out.append(b[s] - a[s])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('--person', type=lambda s: int(s, 16))
    ap.add_argument('--monster', type=lambda s: int(s, 16))
    ap.add_argument('--level', type=int)
    args = ap.parse_args()
    rom = Rom(open(args.rom, 'rb').read())
    kind = 0x80 | args.monster if args.monster is not None else (args.person or 0)
    rec = record_address(kind)
    count = rom.u8(rec)
    breaks = [rom.u8(rec + 2 + k) for k in range(count)]
    print(f'종류 {kind:02X} 레코드 {rec >> 16:02X}:{rec & 0xFFFF:04X} 꺾이는 레벨 {breaks}')
    print('레벨 ' + ' '.join(f'{s:>6}' for s in STATS) + '  경험치')
    levels = [args.level] if args.level else range(1, 100)
    for lv in levels:
        print(f'{lv:4d} ' + ' '.join(f'{v:6d}' for v in stats_at(rom, rec, lv)) + f' {exp_at(rom, rec, lv):8d}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
