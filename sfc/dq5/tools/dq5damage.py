"""DQ5(SFC) 보통 공격 피해 계산. 형식은 sfc/dq5/docs/dq5-data-format.md 의 「전투 계산식」.

보통 공격(たたかう, 처리 루틴 20:AF6C → 20:B030):
  공격력 = 공격하는 쪽 필드 10(일행, 7E:0760+칸*12 +0) / 38(몬스터), 수비력 = 맞는 쪽 필드 14(일행 +2) / 64(몬스터, 7E:07C0+칸*16 +8)
  h = (공격력 - 수비력/2) / 2   (나머지 버림)
  h 가 0 이하            → 난수 0~1
  맞는 쪽이 일행이고 공격력/16 ≥ h → 난수 0~공격력/16
  h < 8                  → h - 1 + 난수 0~2 (음수면 0)
  그 밖                  → h*7/8 + 난수(0~255) * (h/4 + 1) / 256
회심(일행이 공격할 때 20:C697, 1/32): 수비력을 보지 않고 공격력 * (55~65) * 4 / 256 (20:AB04)

사용:
  python sfc/dq5/tools/dq5damage.py 200 5            # 공격력 200, 수비력 5: 피해 범위와 회심 범위
  python sfc/dq5/tools/dq5damage.py 64 120 --party   # 맞는 쪽이 일행
"""
import argparse
import sys


def normal_range(attack, defense, target_party=False):
    """(최소, 최대) 피해. 20:B030."""
    diff = attack - defense // 2
    if diff < 0:
        return 0, 1
    h = diff >> 1
    if h == 0:
        return 0, 1
    if target_party and attack >> 4 >= h:
        return 0, attack >> 4
    if h < 8:
        return max(h - 1, 0), h + 1
    base = h * 7 // 8
    return base, base + (255 * ((h >> 2) + 1) >> 8)


def critical_range(attack):
    """20:AB04. 회심 피해(수비력 무시)."""
    return attack * 55 * 4 >> 8, attack * 65 * 4 >> 8


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('attack', type=int)
    ap.add_argument('defense', type=int)
    ap.add_argument('--party', action='store_true', help='맞는 쪽이 일행')
    args = ap.parse_args()
    lo, hi = normal_range(args.attack, args.defense, args.party)
    print(f'보통 공격 {lo}~{hi}')
    if not args.party:
        lo, hi = critical_range(args.attack)
        print(f'회심 {lo}~{hi}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
