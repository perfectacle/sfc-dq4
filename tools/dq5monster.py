"""DQ5(SFC) 몬스터 레코드. 형식은 docs/dq5-data-format.md 의 「몬스터」.

몬스터 레코드는 23:8000 부터 25바이트씩이고 이름 표 4번(21:959B) 과 순서가 같다. 게임은 필드 읽기(21:8B00)의
묶음 2 로 읽는데, 필드마다 레코드 안 오프셋·길이(21:8D96·21:8C86)와 후처리(21:8E8C)가 정해져 있다.
후처리가 덧붙이는 위 비트는 그 필드 오프셋에서 X+1 바이트 뒤를 읽는다(21:A333).

사용:
  python tools/dq5monster.py rom/dq5.sfc
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5map import Rom  # noqa: E402
from dq5text import string, string_codes, text  # noqa: E402

RECORDS = 0x238000
SIZE = 25
NAMES = 4
COUNT = 236


def record(rom, n):
    return [rom.u8(RECORDS + n * SIZE + i) for i in range(SIZE)]


def fields(r):
    """필드 번호별 값. 이름은 실측한 것만 붙인다."""
    return {
        'HP(55)': r[3] | (r[10] & 7) << 8,          # 21:A2D2·A2FA
        '경험치(72)': r[5] | r[6] << 8,               # 21:A21E
        '금화(73)': r[7] | ((r[8] >> 2) & 3) << 8,    # 21:A32A
        'f63': r[1] | (r[8] >> 7) << 8,              # 21:A2A9
        'f67': r[2] | ((r[8] >> 6) & 1) << 8,        # 21:A2B5
        'f5F': r[0],
        'f5B': r[4],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    args = ap.parse_args()
    rom = Rom(open(args.rom, 'rb').read())
    for n in range(COUNT):
        name = text(string_codes(rom, string(rom, NAMES, n)))
        f = fields(record(rom, n))
        print(f'{n:02X} {name} ' + ' '.join(f'{k}={v}' for k, v in f.items()))
    return 0


if __name__ == '__main__':
    sys.exit(main())
