"""DQ5(SFC) 동료가 되는 몬스터. 형식은 sfc/dq5/docs/dq5-data-format.md 의 「동료가 되는 몬스터」.

전투에 이기면 20:C1F6 이 마지막에 쓰러뜨린 몬스터의 필드 76(확률 등급)·77(동료 종류)로 판정한다.
  같은 종류를 이미 들인 수 = 7E:29EA[종류] 하위 4비트의 켜진 비트 수(27:8153)
  0 → 1/27:8162[등급], 1 → 1/27:8172[등급], 2 → 1/27:8182[등급], 3 이상이면 안 됨
  주인공 가진 물건 첫 7칸이 26:8D33 과 같으면 확률 판정 없이 동료가 됨(26:8D0A)

사용:
  python sfc/dq5/tools/dq5recruit.py rom/dq5.sfc
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5chest import item_name  # noqa: E402
from dq5map import Rom  # noqa: E402
from dq5monster import COUNT, NAMES, record  # noqa: E402
from dq5text import string, string_codes, text  # noqa: E402

CHANCE = (0x278162, 0x278172, 0x278182)  # 들인 수 0·1·2 일 때의 1/N 표, 등급마다 16비트
SECRET = 0x268D33  # 가진 물건 첫 7칸과 견주는 바이트


def chances(rom, grade):
    """등급의 들인 수 0·1·2 일 때 분모. 등급 0 은 동료가 되지 않음."""
    if grade == 0:
        return None
    return [rom.u16(t + grade * 2) for t in CHANCE]


def secret_items(rom):
    return [rom.u8(SECRET + i) for i in range(7)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    args = ap.parse_args()
    rom = Rom(open(args.rom, 'rb').read())
    for n in range(COUNT):
        r = record(rom, n)
        grade, kind = r[9] & 7, r[0x18] & 0x7F
        c = chances(rom, grade)
        if c is None:
            continue
        name = text(string_codes(rom, string(rom, NAMES, n)))
        print(f'{n:02X} {name} 등급{grade} 종류{kind:02X} 1/{c[0]} 1/{c[1]} 1/{c[2]}')
    items = ' '.join(item_name(rom, i) for i in secret_items(rom) if i != 0xFF)
    print(f'반드시 동료가 되는 가진 물건(첫 칸부터): {items}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
