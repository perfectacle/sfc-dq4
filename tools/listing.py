"""cover.lua 결과로 실제 실행된 명령만, 실행 당시 M·X 폭으로 디스어셈블한다.

사용: python tools/listing.py rom/dq5.sfc work/cover/cover.txt [시작 끝]
같은 PC 가 두 가지 폭으로 실행됐으면 모두 출력한다. 실행되지 않은 구간은 빈 줄로 띄운다.
"""
import sys

from kr_patch.snes.dis65816 import decode
from kr_patch.snes.mapper import LoROM


def main():
    rom = open(sys.argv[1], 'rb').read()
    lo, hi = (int(sys.argv[3], 16), int(sys.argv[4], 16)) if len(sys.argv) > 4 else (0, 0xFFFFFF)
    rows = []
    for line in open(sys.argv[2]):
        pc, p, cnt = line.split()
        pc, p = int(pc, 16), int(p, 16)
        if lo <= pc <= hi:
            rows.append((pc, p, int(cnt)))
    rows.sort()
    mapper, prev_end = LoROM(), None
    for pc, p, cnt in rows:
        text, n, _, _ = decode(rom, pc, m8=bool(p & 0x20), x8=bool(p & 0x10), mapper=mapper)
        if prev_end is not None and pc > prev_end:
            print()
        flags = ('m' if p & 0x20 else 'M') + ('x' if p & 0x10 else 'X')
        print(f'{text:<44} ; {flags} {cnt}')
        prev_end = max(prev_end or 0, pc + n)


if __name__ == '__main__':
    main()
