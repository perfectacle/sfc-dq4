"""DQ5(SFC) 물건 표. 형식은 docs/dq5-data-format.md 의 「물건 표」.

23:B081 부터 물건 216개(D8)짜리 1바이트 표 9개가 이어진다(23:B081 + k*D8).
  k0 가격 바탕, k1 bit0-1 가격 배수(21:A447) / 나머지 플래그
  k2 bit0-2 장비 칸(0 무기, 1 갑옷, 2 방패, 3 투구, 4 도구, 5~7 うでわ·リング 같은 장신구)
  k5 공격력(무기) 또는 수비력(갑옷·방패·투구)
  k6 장비할 수 있는 인물 비트. bit7 = 주인공
  k3·k4·k7·k8 은 미확인

사용:
  python tools/dq5item.py rom/dq5.sfc
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5chest import item_name  # noqa: E402
from dq5map import Rom  # noqa: E402
from dq5shop import ITEMS, price  # noqa: E402

TABLES = 0x23B081
SLOTS = ('무기', '갑옷', '방패', '투구', '도구', '장신구', '장신구', '장신구')


def field(rom, k, item):
    return rom.u8(TABLES + k * ITEMS + item)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    args = ap.parse_args()
    rom = Rom(open(args.rom, 'rb').read())
    for i in range(ITEMS):
        slot = field(rom, 2, i) & 7
        kind = SLOTS[slot]
        print(f'{i:02X} {item_name(rom, i)} {kind} 힘{field(rom, 5, i)} 장비{field(rom, 6, i):08b} {price(rom, i)}G'
              f' [{" ".join(f"{field(rom, k, i):02X}" for k in range(9))}]')
    return 0


if __name__ == '__main__':
    sys.exit(main())
