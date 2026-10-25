"""lua/dq5framedump.lua 두 결과(frames.bin)를 덤프마다 견주어 다른 주소를 영역별로 보인다.

사용:
  python sfc/dq5/tools/dq5framediff.py 원래_SHOT_DIR 패치_SHOT_DIR [--all]

출력 한 줄은 영역(W=WRAM 7E:0000~, V=VRAM, C=CGRAM, O=OAM)과 다른 바이트 수, 이어지는 구간마다
「시작-끝@처음 다른 덤프 번호」다. 기본은 WRAM 의 DP·스택 임시 값(7E:0000~00FF, 0200~02FF, 08C0~09FF)과
매 프레임 루틴 자리(7E:1AA6~1AA8)를 뺀다. 이 구간은 실행한 코드의 길이만 달라도 바뀌기 때문이다(--all 이면 모두).
"""
import argparse
import os
import sys

WRAM, VRAM, CGRAM, OAM = 0x20000, 0x10000, 0x200, 0x220
DUMP = WRAM + VRAM + CGRAM + OAM
AREAS = (('W', 0, WRAM, 0x7E0000), ('V', WRAM, VRAM, 0), ('C', WRAM + VRAM, CGRAM, 0), ('O', WRAM + VRAM + CGRAM, OAM, 0))
SCRATCH = ((0x0000, 0x0100), (0x0200, 0x0300), (0x08C0, 0x0A00), (0x1AA6, 0x1AA9))


def runs(addrs):
    out = []
    for a in addrs:
        if out and a == out[-1][1] + 1:
            out[-1][1] = a
        else:
            out.append([a, a])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('a')
    ap.add_argument('b')
    ap.add_argument('--all', action='store_true')
    args = ap.parse_args()
    a = open(os.path.join(args.a, 'frames.bin'), 'rb').read()
    b = open(os.path.join(args.b, 'frames.bin'), 'rb').read()
    n = min(len(a), len(b)) // DUMP
    print(f'dumps {n}')
    for name, off, size, base in AREAS:
        first = {}
        for k in range(n):
            x = a[k * DUMP + off:k * DUMP + off + size]
            y = b[k * DUMP + off:k * DUMP + off + size]
            if x == y:
                continue
            for i in range(size):
                if x[i] != y[i] and i not in first:
                    if name == 'W' and not args.all and any(lo <= i < hi for lo, hi in SCRATCH):
                        continue
                    first[i] = k
        spans = ' '.join((f'{base + s:X}' if s == e else f'{base + s:X}-{base + e:X}') + f'@{first[s]}'
                         for s, e in runs(sorted(first)))
        print(f'{name} {len(first)} {spans}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
