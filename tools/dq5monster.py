"""DQ5(SFC) 몬스터 레코드. 형식은 docs/dq5-data-format.md 의 「몬스터」.

몬스터 레코드는 23:8000 부터 25바이트씩이고 이름 표 4번(21:959B) 과 순서가 같다. 게임은 필드 읽기(21:8B00)의
묶음 2 로 읽는데, 필드마다 레코드 안 오프셋·길이(21:8D96·21:8C86)와 후처리(21:8E8C)가 정해져 있다.
후처리가 덧붙이는 위 비트는 그 필드 오프셋에서 X+1 바이트 뒤를 읽는다(21:A333).
행동 6개(필드 6A, +11~+16)는 tools/dq5spell.py 의 행동 번호다.

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


RESISTS = 18  # 내성 종류 50~61. 21:91F9 + 종류*2 = [+0C 부터의 바이트][2비트 마스크]


def resist(r, k):
    """내성 종류 50+k 의 값 0~3. 0 = 그대로, 3 = 듣지 않음."""
    byte, shift = 0x0C + (k + 1) // 4, 6 - (k + 1) % 4 * 2
    return (r[byte] >> shift) & 3


def fields(r):
    """필드 번호별 값. 이름은 전투에서 실측한 것만 붙이고, 나머지는 필드 번호로 둔다."""
    return {
        'HP(55)': r[3] | (r[10] & 7) << 8,          # 21:A2D2·A2FA
        'MP(5B)': r[4],
        '민첩(5F)': r[0],
        '공격(63)': r[1] | (r[8] >> 7) << 8,         # 21:A2A9
        '수비(67)': r[2] | ((r[8] >> 6) & 1) << 8,   # 21:A2B5, 1FF 이면 7FF
        '경험치(72)': r[5] | r[6] << 8,               # 21:A21E
        '금화(73)': r[7] | ((r[8] >> 2) & 3) << 8,    # 21:A32A
        '행동수(6B)': r[11] >> 6,
        '재생(6C)': (r[10] >> 3) & 3,
        '첫잠(71)': r[9] >> 6,
        '드롭률(74)': (r[9] >> 3) & 7,
        '드롭(75)': r[0x17],
        'f68': r[8] & 3,
        'f69': r[10] >> 5,
        'f6D': (r[12] >> 6) & 1,
        'f6E': (r[8] >> 4) & 3,
        'f70': r[12] >> 7,
        'f76': r[9] & 7,
        'f77': r[0x18] & 0x7F,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    args = ap.parse_args()
    rom = Rom(open(args.rom, 'rb').read())
    for n in range(COUNT):
        name = text(string_codes(rom, string(rom, NAMES, n)))
        r = record(rom, n)
        f = fields(r)
        acts = ' '.join(f'{a:02X}' for a in r[0x11:0x17])
        res = ''.join(str(resist(r, k)) for k in range(RESISTS))
        print(f'{n:02X} {name} ' + ' '.join(f'{k}={v}' for k, v in f.items()) + f' 행동(6A)={acts} 내성50~61={res}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
