"""DQ5(SFC) 낮밤. 형식은 sfc/dq5/docs/dq5-field-format.md 의 「낮밤」.

시간대 $075E(16비트)는 걸음마다 00:82D3 이 1 을 더하고 01FF 로 자른다.
$BE bit7(실내)·$1949(세계) ≠ 0·7E:2190 bit1 이면 더하지 않는다. 21:8000 은 00F0 이상을 밤으로 본다.

사용:
  python sfc/dq5/tools/dq5daynight.py rom/dq5.sfc
  python sfc/dq5/tools/dq5daynight.py rom/dq5.sfc --start 50 --steps 200
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5gfx import FIELD_TIME, FIELD_TIME_PTRS  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402

STEP = 0x0082D3   # REP #$20; LDA $075E; INC A; AND #imm; STA $075E
NIGHT = 0x218004  # LDA $00075E; CMP #imm
SLOTS = 10


def step_mask(rom):
    assert rom.u8(STEP + 6) == 0x29, 'AND #imm 이 아님'
    return rom.u16(STEP + 7)


def night_from(rom):
    assert rom.u8(NIGHT + 4) == 0xC9, 'CMP #imm 이 아님'
    return rom.u16(NIGHT + 5)


def is_night(rom, v):
    return v >= night_from(rom)


def advance(rom, v, steps):
    return (v + steps) & step_mask(rom)


def palette_ranges(rom):
    """[(첫 값, 끝 값, 01:A189 가 가리키는 벌 주소)]. 01:A132 는 뒤에서부터 하한 이상인 첫 항목을 고른다."""
    entries = [(rom.u16(FIELD_TIME + i * 3), rom.u8(FIELD_TIME + i * 3 + 2)) for i in range(SLOTS)]
    top = step_mask(rom)
    out = []
    for i, (lo, idx) in enumerate(entries):
        hi = entries[i + 1][0] - 1 if i + 1 < len(entries) else top
        out.append((lo, hi, rom.u16(FIELD_TIME_PTRS + idx)))  # 색인은 바이트 오프셋(짝수)
    return out


def constant_writes(rom):
    """$075E 에 상수를 쓰는 곳 [(LDA 주소, 값)]. 8비트 LDA 는 뒤에 STZ $075F 가 붙는 것만 센다."""
    d = rom.d
    out = []
    i = d.find(b'\x8d\x5e\x07')
    while i >= 0:
        bank, addr = i >> 15, 0x8000 | (i & 0x7FFF)
        if i >= 3 and d[i - 3] == 0xA9:
            out.append(((bank << 16) | (addr - 3), d[i - 2] | d[i - 1] << 8))
        elif i >= 2 and d[i - 2] == 0xA9 and d[i + 3:i + 6] == b'\x9c\x5f\x07':
            out.append(((bank << 16) | (addr - 2), d[i - 1]))
        i = d.find(b'\x8d\x5e\x07', i + 1)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('--start', type=lambda s: int(s, 16), help='시작 $075E(16진)')
    ap.add_argument('--steps', type=int, default=0, help='걸음 수')
    args = ap.parse_args()
    rom = Rom(open(args.rom, 'rb').read())
    mask, night = step_mask(rom), night_from(rom)
    if args.start is not None:
        v = advance(rom, args.start, args.steps)
        print(f'{args.start:04X} + {args.steps}걸음 = {v:04X} {"밤" if is_night(rom, v) else "낮"}')
        return 0
    cycle = mask + 1
    print(f'걸음마다 +1, & {mask:04X} (00:82D3): 한 바퀴 {cycle}걸음')
    print(f'밤 = {night:04X} 이상 (21:8000): 낮 {night}걸음, 밤 {cycle - night}걸음')
    print('필드 2·3번 줄 색 벌 (01:A16B):')
    for lo, hi, ptr in palette_ranges(rom):
        if lo <= hi:
            span = f'{lo:04X}' if lo == hi else f'{lo:04X}~{hi:04X}'
            print(f'  {span:<10} 01:{ptr:04X}')
    print('$075E 에 상수를 쓰는 곳:')
    for a, v in constant_writes(rom):
        print(f'  {a >> 16:02X}:{a & 0xFFFF:04X} {v:04X} {"밤" if is_night(rom, v) else "낮"}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
