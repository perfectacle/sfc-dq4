"""DQ5(SFC) 물건 표. 형식은 sfc/dq5/docs/dq5-data-format.md 의 「물건 표」.

23:B081 부터 물건 216개(D8)짜리 1바이트 표 9개가 이어진다(23:B081 + k*D8).
  k0 가격 바탕, k1 bit0-1 가격 배수(21:A447) / 나머지 플래그
  k2 bit0-2 장비 칸(0 무기, 1 갑옷, 2 방패, 3 투구, 4 도구, 5~7 うでわ·リング 같은 장신구)
  k5 공격력(무기) 또는 수비력(갑옷·방패·투구)
  k6 장비할 수 있는 인물 비트. 인물 번호 → 비트는 21:A632(bit7 = 주인공)
  k7·k8 은 따로 된 표가 아니라 물건마다 16비트 하나(23:B669 + 물건*2): 동료 몬스터가 장비할 수 있는 갈래 비트.
     갈래 = 23:AED1 + 몬스터*9 + 8 의 하위 4비트, 비트 = 8000 >> 갈래 (21:A53B, 코드 읽기)
  k1·k2·k3·k4 의 나머지 비트는 21:A49D~A61F 의 루틴이 하나씩 읽고, 다른 뱅크는 BRK #94 n(조회 표 21:A3FF)으로 부른다.
  k1 bit3 팔 수 없음(상점 메시지), k2 bit7 상점의 「전투에서 쓰면 효과」 설명, k2 bit6 전투에서 쓸 때 대상 창, k2 bit5 대상이 적 쪽,
  k2 bit3 저주받은 장비(장비할 때 25:FD00)

사용:
  python sfc/dq5/tools/dq5item.py rom/dq5.sfc
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


def monster_equip(rom, item):
    """k7·k8 자리의 16비트. bit15 = 갈래 0."""
    return rom.u16(TABLES + 7 * ITEMS + item * 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    args = ap.parse_args()
    rom = Rom(open(args.rom, 'rb').read())
    for i in range(ITEMS):
        slot = field(rom, 2, i) & 7
        kind = SLOTS[slot]
        print(f'{i:02X} {item_name(rom, i)} {kind} 힘{field(rom, 5, i)} 장비{field(rom, 6, i):08b}'
              f' 몬스터{monster_equip(rom, i):016b} {price(rom, i)}G'
              f' [{" ".join(f"{field(rom, k, i):02X}" for k in range(5))}]')
    return 0


if __name__ == '__main__':
    sys.exit(main())
