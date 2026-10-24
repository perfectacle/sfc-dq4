"""DQ5(SFC) 상점 품목과 물건 가격. 형식은 docs/dq5-data-format.md 의 「상점」.

대화 번호 000~010 은 06:DBD2 가 06:DBDB 점프 표로 처리한다(01 무기점, 02 도구점, 03 방어구점, 08 よろず屋 …).
가게 처리기가 목록 종류를 7E:0F20 에, 찾을 키를 7E:0F25 에 두면 06:F49C 가 04:FBD5[종류] 에서
[키][물건 번호 …][FF] 목록을 키가 같은 것이 나올 때까지 찾는다. 무기·도구·방어구점의 키는 맵 그룹 $BC 다(06:DC37).
같은 키의 목록이 둘 이상이면 06:F4CB 가 이야기 진행 플래그(7E:2190 & 40 등)나 주인공 Y 좌표로 뒤의 목록을 고른다(코드 읽기).
가격은 21:A447 이 물건마다 두 표로 계산한다.

사용:
  python tools/dq5shop.py rom/dq5.sfc
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5chest import item_name  # noqa: E402
from dq5map import Rom  # noqa: E402

LISTS = 0x04FBD5
# 21:A447. 가격 = 23:B081[물건] × 21:A47B[23:B159[물건] & 3](1, 10, 100, 1000). 물건은 216개(23:B081~B158).
PRICE_BASE = 0x23B081
PRICE_SCALE = 0x23B159
SCALES = (1, 10, 100, 1000)
ITEMS = 0xD8
# 종류 0~3 의 목록은 빈틈없이 이어지고, 종류 3 은 04:FD55 에서 끝난다(뒤는 다른 데이터).
KINDS = ('도구점', '방어구점', '무기점', 'よろず屋')
END = 0x04FD55


def price(rom, item):
    return rom.u8(PRICE_BASE + item) * SCALES[rom.u8(PRICE_SCALE + item) & 3]


def shop_lists(rom):
    """[(종류, 키, [물건 번호])]."""
    starts = [0x040000 | rom.u16(LISTS + 2 * k) for k in range(len(KINDS))] + [END]
    out = []
    for kind in range(len(KINDS)):
        a = starts[kind]
        while a < starts[kind + 1]:
            key, a = rom.u8(a), a + 1
            items = []
            while rom.u8(a) != 0xFF:
                items.append(rom.u8(a))
                a += 1
            a += 1
            out.append((kind, key, items))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    args = ap.parse_args()
    rom = Rom(open(args.rom, 'rb').read())
    for kind, key, items in shop_lists(rom):
        print(f'{KINDS[kind]} {key:02X}: ' + ', '.join(f'{item_name(rom, i)} {price(rom, i)}G' for i in items))
    return 0


if __name__ == '__main__':
    sys.exit(main())
