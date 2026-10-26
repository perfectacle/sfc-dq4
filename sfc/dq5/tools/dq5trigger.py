"""DQ5(SFC) 실내 맵 영역 이동(트리거). 형식은 sfc/dq5/docs/dq5-map-format.md 의 「영역 이동」.

맵을 불러올 때 01:9430 이 2A:EB0E 색인([$BC][$BD][개수], bit7 바이트로 끝)에서 그 맵의 레코드 위치를 정하고,
걸을 때마다 00:CDEC 가 12바이트 레코드의 사각형·층을 검사해 2A:F47D 로 맵을 옮긴다.

사용:
  python sfc/dq5/tools/dq5trigger.py rom/dq5.sfc [BC BD]   (맵을 주지 않으면 전체 통계)
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5map import Rom  # noqa: E402

INDEX = 0x2AEB0E
RECORDS = 0x2AD812
RECORD_SIZE = 12


def index(rom):
    """[(bc, bd, 개수, 첫 레코드 주소)]."""
    out, a, total = [], INDEX, 0
    while not rom.u8(a) & 0x80:
        bc, bd, n = rom.u8(a), rom.u8(a + 1), rom.u8(a + 2)
        out.append((bc, bd, n, RECORDS + total * RECORD_SIZE))
        total += n
        a += 3
    return out


def record(rom, a):
    r = [rom.u8(a + i) for i in range(RECORD_SIZE)]
    return {
        'rect': (r[0], r[1], r[2], r[3]), 'source_layer': r[4], 'flags': r[5],
        'bc': r[6], 'bd': r[7], 'x': r[8], 'y': r[9], 'span': r[10], 'destination_layer': r[11], 'raw': r,
    }


def describe(t):
    x0, y0, x1, y1 = t['rect']
    where = f'({x0},{y0})~({x1 - 1},{y1 - 1})'
    if t['bc'] & 0x80:
        dest = '필드로'
    else:
        dest = f'{t["bc"]:02X}/{t["bd"]:02X} ({t["x"]},{t["y"]})'
    cond = '' if t['flags'] & 0x40 else ' (이동 효과음)'
    return f'{where} 에 층 {t["source_layer"]:02X}로 들어서면 → {dest}, 도착 층 {t["destination_layer"]:02X}{cond}'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('bc', nargs='?', type=lambda s: int(s, 16))
    ap.add_argument('bd', nargs='?', type=lambda s: int(s, 16))
    args = ap.parse_args()
    rom = Rom(open(args.rom, 'rb').read())
    idx = index(rom)
    if args.bc is None:
        total = sum(n for _, _, n, _ in idx)
        print(f'maps {len(idx)}, records {total}, records end {RECORDS + total * RECORD_SIZE:06X} (index at {INDEX:06X})')
        return 0
    for bc, bd, n, a in idx:
        if (bc, bd) == (args.bc, args.bd):
            print(f'map {bc:02X}/{bd:02X}: {n} records at {a:06X}')
            for k in range(n):
                t = record(rom, a + k * RECORD_SIZE)
                print(f'  {k}: [{" ".join(f"{b:02X}" for b in t["raw"])}] {describe(t)}')
            return 0
    print(f'map {args.bc:02X}/{args.bd:02X}: no records')
    return 0


if __name__ == '__main__':
    sys.exit(main())
