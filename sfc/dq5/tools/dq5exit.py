"""DQ5(SFC) 실내 맵 출구. 형식은 docs/dq5-map-format.md 의 「출구」.

출구는 좌표를 저장하지 않는다. 셀 버퍼에서 속성(+4 또는 +7)이 EXIT_ATTRS 인 셀을 앞에서부터 센 순서가 출구 번호이고(2A:FC16),
그 번호로 2A:ED61 목적지 표의 항목을 고른다(2A:F6FD). 도착할 때도 새 맵에서 N 번째 출구 셀을 찾아 그 왼쪽에 선다(2A:FC93).
셀 버퍼는 맵을 푼 뒤 15:F7D0 이 부르는 맵별 루틴(15:F907 표)이 고치기도 하므로, 출구 속성을 쓰는 곳을 그 루틴에서 찾아 반영한다.

사용:
  python tools/dq5exit.py rom/dq5.sfc BC BD
"""
import argparse
import os
import sys

from kr_patch.sfc.dis65816 import decode
from kr_patch.sfc.mapper import LoROM

sys.path.insert(0, os.path.dirname(__file__))
from dq5map import Decoder, Rom, map_pointer  # noqa: E402

DEST_TABLE = 0x2AED61
# 2A:FF37. 블록 오른쪽 아래 셀에만 bit7 이 붙으므로(01:8ACB) 블록 하나가 한 번만 세어진다.
EXIT_ATTRS = 0x2AFF37
ENTRY_SIZE = {0x00: 1, 0x20: 3, 0x40: 2, 0x60: 5}
# 15:F7F4. [BC][BD|FF][플래그|FF][마스크][맵을 푼 뒤 부를 루틴 24비트][다른 루틴 24비트], FF 로 끝. 처음 맞는 항목을 쓴다.
# 둘째 루틴은 $1AA6~$1AA8 에 둔다(쓰임 미확인). 15:F906 은 RTL 하나뿐인 「루틴 없음」.
HOOK_TABLE = 0x15F907
HOOK_NONE = 0x15F906
HOOK_SCAN_LIMIT = 200
# A 를 바꾸지 않아 앞의 LDA #즉값 이 유효한 채로 남는 명령: STA long/abs, PHA, PLB, PHP, PLP, PHB, BRK, Bxx.
KEEPS_A = {0x8F, 0x8D, 0x48, 0xAB, 0x08, 0x28, 0x8B, 0x00, 0x10, 0x30, 0x50, 0x70, 0x90, 0xB0, 0xD0, 0xF0}
# 무조건 점프. 뒤 바이트는 순서대로 실행되지 않으므로 여기서 읽기를 멈춘다.
JUMPS = {0x80, 0x82, 0x4C, 0x5C, 0x6C, 0x7C, 0xDC}
CELL_BUFFER = 0x7EC000


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


def map_hook(rom, bc, bd):
    """15:F7F4 가 실내 맵($BE bit7)에 고르는 루틴 주소. 플래그 번호 bit7 이 0 이면 7E:2190+번호 & 마스크가 켜졌을 때 참.
    플래그는 모두 꺼진 것으로 본다. 맵을 옮길 때 00:A8CC 가 219F·21A0 을 지우므로 그 두 바이트는 실제로도 0 이다."""
    a = HOOK_TABLE
    while rom.u8(a) != 0xFF:
        e = [rom.u8(a + i) for i in range(4)]
        if e[0] == bc and e[1] in (0xFF, bd) and (e[2] == 0xFF or e[2] & 0x80):
            return rom.u24(a + 4)
        a += 10
    return HOOK_NONE


def hook_writes(rom, pc, depth=0):
    """루틴에서 `LDA #즉값` 다음 `STA long` 이나 `STA abs`(같은 루틴의 `LDA #$7E / PHA / PLB` 뒤) 로 쓰는 (RAM 주소, 바이트들) 을 찾는다.
    JSL 은 한 단계만 따라간다. BRK #$0B(플래그 검사, 00:93BA)는 인자 2바이트를 더 먹는다.
    조건 분기는 따지지 않고 처음 RTL·RTS·RTI 나 무조건 점프까지 순서대로 읽으므로, 플래그가 꺼졌을 때 지나는 쪽이 앞에 오는 루틴만 맞게 읽는다.
    STA long,X·STA abs,X·STZ, 들어올 때 이미 DB=$7E 인 STA abs 는 보지 않는다."""
    data, mapper = rom.d, LoROM()
    m8 = x8 = True
    imm, db, pushed, out = None, None, None, []
    for _ in range(HOOK_SCAN_LIMIT):
        op = rom.u8(pc)
        _, n, _, _ = decode(data, pc, m8=m8, x8=x8, mapper=mapper)
        if op in (0xC2, 0xE2):
            v = rom.u8(pc + 1)
            if v & 0x20:
                imm = None
            m8 = (m8 or bool(v & 0x20)) if op == 0xE2 else (m8 and not v & 0x20)
            x8 = (x8 or bool(v & 0x10)) if op == 0xE2 else (x8 and not v & 0x10)
        elif op == 0xA9:
            imm = bytes(rom.u8(pc + 1 + i) for i in range(1 if m8 else 2))
        elif op == 0x48:
            pushed = imm[0] if imm else None
        elif op == 0xAB:
            db, pushed = pushed, None
        elif op == 0x8F and imm is not None:
            out.append((rom.u24(pc + 1), imm))
        elif op == 0x8D and imm is not None and db == 0x7E:
            out.append((0x7E0000 | rom.u16(pc + 1), imm))
        elif op == 0x22:
            if depth == 0:
                out += hook_writes(rom, rom.u24(pc + 1), 1)
            imm = db = pushed = None
        elif op == 0x00:
            if rom.u8(pc + 1) != 0x0B:
                break
            n = 4
        elif op not in KEEPS_A:
            imm = None
        if op in (0x40, 0x60, 0x6B) or op in JUMPS:
            break
        pc = (pc & 0xFF0000) | ((pc + n) & 0xFFFF)
    else:
        print(f'warning: {pc:06X} 까지 {HOOK_SCAN_LIMIT} 명령을 읽고도 루틴 끝을 못 찾음', file=sys.stderr)
    return out


def apply_hook(rom, bc, bd, buf, width):
    """맵별 루틴이 셀 버퍼에 쓰는 값을 buf 에 반영하고, 출구 여부가 바뀐 셀을 [(x, y, 더함?)] 로 돌려준다."""
    pc = map_hook(rom, bc, bd)
    if pc == HOOK_NONE:
        return []
    attrs = exit_attrs(rom)

    def is_exit(c):
        return buf[c * 8 + 4] in attrs or buf[c * 8 + 7] in attrs

    before = {}
    for ram, data in hook_writes(rom, pc):
        for k, v in enumerate(data):
            i = ram + k - CELL_BUFFER
            if 0 <= i < len(buf):
                before.setdefault(i // 8, is_exit(i // 8))
                buf[i] = v
    return [(c % width, c // width, is_exit(c)) for c, was in sorted(before.items()) if was != is_exit(c)]


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


def map_exit_cells(rom, bc, bd, attrs):
    """맵별 루틴까지 반영한 출구 셀 목록과, 그 루틴이 출구 여부를 바꾼 셀 목록."""
    w, h, buf, _ = Decoder(rom, 0xBE).decode(map_pointer(rom, bc, bd))
    buf = bytearray(buf)
    hooked = apply_hook(rom, bc, bd, buf, w)
    return exit_cells(buf, w, h, attrs), hooked


def arrival(rom, bc, bd, n, attrs):
    """2A:FC93: 도착 맵의 n 번째 출구 셀 왼쪽 칸."""
    x, y = map_exit_cells(rom, bc, bd, attrs)[0][n]
    return x - 1, y


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('bc', type=lambda s: int(s, 16))
    ap.add_argument('bd', type=lambda s: int(s, 16))
    args = ap.parse_args()
    rom = Rom(open(args.rom, 'rb').read())
    attrs = exit_attrs(rom)
    cells, hooked = map_exit_cells(rom, args.bc, args.bd, attrs)
    exits = map_exits(rom, args.bc, args.bd)
    print(f'map {args.bc:02X}/{args.bd:02X}: exit cells {len(cells)}, table entries {len(exits)}')
    hook = map_hook(rom, args.bc, args.bd)
    for x, y, added in hooked:
        print(f'  맵별 루틴 {hook:06X} 이 ({x}, {y}) 를 출구 셀로 {"만듦" if added else "지움"}')
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
