"""DQ5(SFC) 몬스터가 떨어뜨리는 물건. 형식은 sfc/dq5/docs/dq5-data-format.md 의 「몬스터」(필드 74·75).

전투가 끝나면 25:8956 이 떨어뜨릴 후보 몬스터($1116, FF 면 없음)의 필드 74(바이트9 bit3-5)로
27:8218 의 N 을 골라 난수(0~N-1)가 0 이면 필드 75(바이트23)의 물건을 상자로 떨어뜨린다.
20:8000 bit5 가 켜져 있으면 확률 판정을 건너뛴다(1/4096 등급으로 실측).

사용:
  python sfc/dq5/tools/dq5drop.py rom/dq5.sfc
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5chest import item_name  # noqa: E402
from dq5map import Rom  # noqa: E402
from dq5monster import COUNT, NAMES, record  # noqa: E402
from dq5text import string, string_codes, text  # noqa: E402

RATES = 0x278218  # 등급 0~7 의 N(16비트)


def drop(rom, n):
    """(물건 번호 또는 None, 1/N 의 N)."""
    r = record(rom, n)
    item = r[0x17]
    return (None if item == 0xFF else item), rom.u16(RATES + ((r[9] >> 3) & 7) * 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    args = ap.parse_args()
    rom = Rom(open(args.rom, 'rb').read())
    for n in range(COUNT):
        item, rate = drop(rom, n)
        if item is None:
            continue
        name = text(string_codes(rom, string(rom, NAMES, n)))
        print(f'{n:02X} {name} {item_name(rom, item)}({item:02X}) 1/{rate}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
