"""DQ5(SFC) 실내 맵 출구. 형식은 docs/dq5-map-format.md 의 「출구」.

출구는 좌표를 저장하지 않는다. 셀 버퍼에서 속성(+4 또는 +7)이 EXIT_ATTRS 인 셀을 앞에서부터 센 순서가 출구 번호이고(2A:FC16),
그 번호로 2A:ED61 목적지 표의 항목을 고른다(2A:F6FD). 도착할 때도 새 맵에서 N 번째 출구 셀을 찾아 그 왼쪽에 선다(2A:FC93).

사용:
  python tools/dq5exit.py rom/dq5.sfc BC BD
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5map import Decoder, Rom, map_pointer  # noqa: E402

DEST_TABLE = 0x2AED61
# 2A:FF37. 블록 오른쪽 아래 셀에만 bit7 이 붙으므로(01:8ACB) 블록 하나가 한 번만 세어진다.
EXIT_ATTRS = 0x2AFF37
ENTRY_SIZE = {0x00: 1, 0x20: 3, 0x40: 2, 0x60: 5}


def exit_attrs(rom):
    out, a = [], EXIT_ATTRS
    while rom.u8(a) != 0xFF:
        out.append(rom.u8(a))
        a += 1
    return out


def exit_cells(buf, width, height, attrs):
    """출구 셀 (x, y) 를 셀 버퍼 순서대로."""
    cells = []
    for i in range(width * height):
        if buf[i * 8 + 4] in attrs or buf[i * 8 + 7] in attrs:
            cells.append((i % width, i // width))
    return cells


def group_start(rom, bc):
    """2A:F711. [BC] 로 시작해 FF 로 끝나는 그룹을 차례로 찾는다."""
    a = DEST_TABLE
    while rom.u8(a) != 0xFF:
        if rom.u8(a) == bc:
            return a + 1
        while rom.u8(a) != 0xFF:
            a += 1
        a += 1
    return None


def map_exits(rom, bc, bd):
    """(bc, bd) 맵의 목적지 항목 목록. 맵마다 bit7 이 켜진 항목으로 끝난다(2A:F738)."""
    a = group_start(rom, bc)
    if a is None:
        return []
    for _ in range(bd):
        while True:
            b = rom.u8(a)
            a += ENTRY_SIZE[b & 0x60]
            if b & 0x80:
                break
    out = []
    while True:
        b = rom.u8(a)
        n = ENTRY_SIZE[b & 0x60]
        out.append((a, bytes(rom.u8(a + i) for i in range(n))))
        a += n
        if b & 0x80:
            return out


def describe(bc, entry):
    b0 = entry[0]
    kind, bd = b0 & 0x60, b0 & 0x1F
    if kind == 0x40:
        return f'{bc:02X}/{bd:02X} 의 출구 {entry[1]}'
    if kind == 0x20:
        return f'{entry[2]:02X}/{bd:02X} 의 출구 {entry[1]}'
    if kind == 0x60:
        return f'{entry[4]:02X}/{bd:02X} ({entry[1]},{entry[2]}) 방향 {entry[3]}'
    return '특수(2A:F7B2)'


def arrival(rom, bc, bd, n, attrs):
    """2A:FC93: 도착 맵의 n 번째 출구 셀 왼쪽 칸."""
    dec = Decoder(rom, 0xBE)
    w, h, buf, _ = dec.decode(map_pointer(rom, bc, bd))
    x, y = exit_cells(buf, w, h, attrs)[n]
    return x - 1, y


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('bc', type=lambda s: int(s, 16))
    ap.add_argument('bd', type=lambda s: int(s, 16))
    args = ap.parse_args()
    rom = Rom(open(args.rom, 'rb').read())
    attrs = exit_attrs(rom)
    dec = Decoder(rom, 0xBE)
    w, h, buf, _ = dec.decode(map_pointer(rom, args.bc, args.bd))
    cells = exit_cells(buf, w, h, attrs)
    exits = map_exits(rom, args.bc, args.bd)
    print(f'map {args.bc:02X}/{args.bd:02X}: exit cells {len(cells)}, table entries {len(exits)}')
    for k, (a, e) in enumerate(exits):
        cell = cells[k] if k < len(cells) else None
        dest = describe(args.bc, e)
        extra = ''
        if e[0] & 0x60 == 0x40:
            extra = f' → 도착 {arrival(rom, args.bc, e[0] & 0x1F, e[1], attrs)}'
        elif e[0] & 0x60 == 0x20:
            extra = f' → 도착 {arrival(rom, e[2], e[0] & 0x1F, e[1], attrs)}'
        print(f'  {k}: cell {cell} [{e.hex(" ")}] at {a:06X}: {dest}{extra}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
