"""DQ5(SFC) 전투 조우 표. 형식은 docs/dq5-data-format.md 의 「전투 조우」.

조우 판정과 무리 고르기는 23:E7C2(00:82B4 가 부름)이고, 그 앞의 01:84CF 가 조우 구역 번호(A)와 조우율(Y)을 정한다.
- 실내 맵: 23:FD6A[BC] 가 가리키는 맵마다 6바이트 [구역 x3 ($1948 로 고름)][배경][+4][+5]. FF 는 조우 없음(01:83E6).
- 필드: 17칸 너비 구역 격자(01:A6D9 가 $1949·$1948 로 고름)를 (Y>>5)*17 + (X>>5) 로 찾고(01:854F),
  조우율은 지형별 23:F1E0(낮)·23:F1EE($075E >= F0)에서 온다. 배($1954 == 3)는 01:85D8 직사각형 표.
- 구역 레코드 23:96F3 + n*22: [+0 레벨][+1~+B 칸 11개의 무게·마릿수][+C~+15 몬스터 10마리].
  칸 0~4 를 뽑으면 여러 종 무리(23:E9B4), 칸 5~9 는 한 종(23:E99B), 칸 10 은 23:B04B 의 고정 무리(23:E953).

사용:
  python tools/dq5encounter.py rom/dq5.sfc            # 구역 85개
  python tools/dq5encounter.py rom/dq5.sfc 21 02      # 그 맵의 구역과 무리
  python tools/dq5encounter.py rom/dq5.sfc --maps     # 조우가 있는 실내 맵 목록
  python tools/dq5encounter.py rom/dq5.sfc --field    # 필드 구역 격자
  python tools/dq5encounter.py rom/dq5.sfc --trace trace.txt
      # 툴킷 probe/trace.lua 기록(TRACE=23E7C2,23E9B0,23EA40,23E98F LOG=7E1001,7E1003,7E1005,7E1007)의
      # 무리가 표에서 나올 수 있는 것인지 검사
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5map import Rom  # noqa: E402
from dq5text import string, string_codes, text  # noqa: E402

AREAS = 0x2396F3
AREA_SIZE = 22
AREA_COUNT = 0x55          # 실내 표·필드 격자·배 표가 쓰는 가장 큰 번호가 54
SLOTS = 11
MONSTERS = 10
FIXED = 0x23B04B           # 칸 10 의 고정 무리, 6바이트 [몬스터 x3][마릿수<<4 | 미확인 x3]
FIXED_COUNT = 9            # FF 없이 끝나는 앞 9개만 몬스터 번호로 맞는다
RATE_COEF = 0x23EA44       # 8개. 계수 번호는 칸 4·5·6 바이트의 bit7
COUNT_BASE = 0x23EA63      # 마릿수 = 기본 + rand(폭), 폭이 1 이면 기본
COUNT_RANGE = 0x23EA73
MAP_TABLE = 0x23FD6A       # 맵 그룹 54개의 포인터(뱅크 23), 맵마다 6바이트
GROUPS = 54
FIELD_RATE_DAY = 0x23F1E0  # 지형 14종
FIELD_RATE_NIGHT = 0x23F1EE
FIELD_WIDTH = 17
# 01:A6D9: ($1949, $1948) -> 격자. $1949 가 0 이 아니면 $1948 은 보지 않는다.
FIELD_GRIDS = [
    ('$1949=0 $1948=0', 0x23F1FC, 7),
    ('$1949=0 $1948=1', 0x23F273, 17),
    ('$1949=0 $1948=2', 0x23F394, 17),
    ('$1949=1', 0x23F4B5, 5),
    ('$1949=2~', 0x23F50A, 4),
]
SHIP_RECTS = 0x0185D8      # 01:858D. $1948 == 2 이면 +A 부터. [X0][X1][Y0][Y1](16비트) [안][밖]
INDOOR_RATE = 7            # 01:8522. X 가 음수면 20(01:8526)
NAMES = 4


def monster_name(rom, n):
    return text(string_codes(rom, string(rom, NAMES, n)))


def count_range(rom, code):
    base = rom.u8(COUNT_BASE + code)
    width = rom.u8(COUNT_RANGE + code)
    return (base, base) if width == 1 else (base, base + width - 1)


def area(rom, n):
    a = AREAS + n * AREA_SIZE
    raw = [rom.u8(a + i) for i in range(AREA_SIZE)]
    slots = raw[1:1 + SLOTS]
    mons = raw[1 + SLOTS:]
    coef_idx = (slots[4] >> 7) | (slots[5] >> 7) << 1 | (slots[6] >> 7) << 2
    return {
        'n': n,
        'raw': raw,
        'level': raw[0],                                   # $100F, $1A99(せいすい 류 비교로 보임)
        'weights': [s & 7 for s in slots],
        'count_codes': [(s >> 3) & 7 for s in slots],
        'monsters': mons,
        # 칸 0~2 의 bit6-7: 여러 종 무리의 종 수가 2·3·4 일 무게
        'species_weights': [slots[0] >> 6, slots[1] >> 6, slots[2] >> 6],
        'coef': rom.u8(RATE_COEF + coef_idx),
        'flag_1000': slots[3] >> 6,                        # $1000 bit0-1
        'flag_1010': slots[7] >> 7,                        # $1010
        'fixed_night_only': slots[8] >> 7,                 # 칸 10 은 21:8000 이 carry 일 때만
        'fixed_group': slots[10] >> 3,
    }


def fixed_group(rom, g):
    raw = [rom.u8(FIXED + g * 6 + i) for i in range(6)]
    return [(raw[i], count_range(rom, raw[3 + i] >> 4), raw[3 + i] & 15) for i in range(3) if raw[i] != 0xFF]


def groups(rom, ar):
    """칸마다 나오는 무리와 확률(무게 / 합)."""
    total = sum(ar['weights'])
    out = []
    for s in range(SLOTS):
        w = ar['weights'][s]
        if not w:
            continue
        p = w / total
        if s < 5:
            # 23:E9B4: 첫 종은 이 칸, 나머지 종은 칸 0~4 에서 무게대로 다시 뽑는다(같은 칸이 또 나올 수 있다)
            lo, hi = count_range(rom, ar['count_codes'][s] + 7)
            out.append((s, p, 'mixed', [(ar['monsters'][s], (lo, hi))]))
        elif s < 10:
            out.append((s, p, 'single', [(ar['monsters'][s], count_range(rom, ar['count_codes'][s]))]))
        else:
            out.append((s, p, 'fixed', [(m, c) for m, c, _ in fixed_group(rom, ar['fixed_group'])]))
    return out


def map_entry(rom, bc, bd):
    p = rom.u16(MAP_TABLE + bc * 2)
    q = rom.u16(MAP_TABLE + bc * 2 + 2) if bc + 1 < GROUPS else MAP_TABLE & 0xFFFF
    if bd >= (q - p) // 6:
        return None
    return [rom.u8(0x230000 | (p + bd * 6 + i)) for i in range(6)]


def map_entries(rom):
    for bc in range(GROUPS):
        p = rom.u16(MAP_TABLE + bc * 2)
        q = rom.u16(MAP_TABLE + bc * 2 + 2) if bc + 1 < GROUPS else MAP_TABLE & 0xFFFF
        for bd in range((q - p) // 6):
            yield bc, bd, map_entry(rom, bc, bd)


def field_grid(rom, addr, rows):
    return [[rom.u8(addr + r * FIELD_WIDTH + c) for c in range(FIELD_WIDTH)] for r in range(rows)]


def field_area(rom, grid_index, x, y):
    """필드 좌표(8픽셀 단위 $B6, $B8)의 구역. 01:854F."""
    _, addr, _ = FIELD_GRIDS[grid_index]
    return rom.u8(addr + (y >> 5) * FIELD_WIDTH + (x >> 5))


def format_area(rom, ar):
    lines = [f'구역 {ar["n"]:02X}  레벨 {ar["level"]}  계수 {ar["coef"]:02X}  종 수 무게(2/3/4) {ar["species_weights"]}'
             f'  $1000={ar["flag_1000"]} $1010={ar["flag_1010"]} 칸10밤만={ar["fixed_night_only"]}']
    for s, p, kind, mons in groups(rom, ar):
        desc = ', '.join(f'{monster_name(rom, m)}({m:02X}) {lo}~{hi}' if lo != hi else
                         f'{monster_name(rom, m)}({m:02X}) {lo}' for m, (lo, hi) in mons)
        label = {'mixed': '여러 종', 'single': '한 종', 'fixed': f'고정 {ar["fixed_group"]:02X}'}[kind]
        lines.append(f'  칸 {s:2d} {p * 100:5.1f}%  {label}: {desc}')
    return '\n'.join(lines)


EXITS = {'23E9B0': 'single', '23EA40': 'mixed', '23E98F': 'fixed'}


def check_trace(rom, path):
    """23:E7C2 가 무리를 정하고 나가는 세 곳(SEC; RTL 직전)의 X(구역*22)·Y·$1001~$1008 을 표와 맞춘다."""
    bad = total = 0
    for line in open(path):
        f = line.split()
        if len(f) < 3 or f[1] not in EXITS:
            continue
        kv = dict(x.split('=') for x in f[2:] if '=' in x)
        x, y = int(kv['X'], 16), int(kv['Y'], 16)
        b = []
        for k in ('7E1001', '7E1003', '7E1005', '7E1007'):
            v = int(kv[k], 16)
            b += [v & 0xFF, v >> 8]
        ids, counts = b[:4], b[4:]
        ar = area(rom, x // AREA_SIZE)
        kind = EXITS[f[1]]
        got = [(m, c) for m, c in zip(ids, counts) if m != 0xFF]
        if kind == 'single':
            m = ar['monsters'][y]
            lo, hi = count_range(rom, ar['count_codes'][y])
            ok = ar['weights'][y] > 0 and len(got) == 1 and got[0][0] == m and lo <= got[0][1] <= hi
        elif kind == 'mixed':
            allowed = {}
            for s in range(5):
                if ar['weights'][s]:
                    allowed.setdefault(ar['monsters'][s], []).append(count_range(rom, ar['count_codes'][s] + 7))
            ok = 2 <= len(got) <= 4 and all(m in allowed and any(lo <= c <= hi for lo, hi in allowed[m])
                                            for m, c in got)
        else:
            want = fixed_group(rom, ar['fixed_group'])
            ok = len(got) == len(want) and all(m == w[0] and w[1][0] <= c <= w[1][1] for (m, c), w in zip(got, want))
        total += 1
        bad += not ok
        names = ', '.join(f'{monster_name(rom, m)} {c}' for m, c in got)
        print(f'{"OK " if ok else "NG "} 구역 {ar["n"]:02X} {kind:6s} 칸 {y if kind == "single" else "-"}: {names}')
    print(f'{total}개 중 {bad}개 어긋남')
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('bc', nargs='?')
    ap.add_argument('bd', nargs='?')
    ap.add_argument('--maps', action='store_true')
    ap.add_argument('--field', action='store_true')
    ap.add_argument('--trace')
    args = ap.parse_args()
    rom = Rom(open(args.rom, 'rb').read())

    if args.trace:
        return check_trace(rom, args.trace)

    if args.maps:
        for bc, bd, e in map_entries(rom):
            if e[0] != 0xFF or e[1] != 0xFF or e[2] != 0xFF:
                print(f'{bc:02X}/{bd:02X} 구역($1948=0/1/2) ' + ' '.join(f'{x:02X}' for x in e[:3]) +
                      '  +3~+5 ' + ' '.join(f'{x:02X}' for x in e[3:]))
        return 0
    if args.field:
        print('지형별 조우율(낮) ' + ' '.join(f'{rom.u8(FIELD_RATE_DAY + i):02X}' for i in range(14)))
        print('지형별 조우율(밤) ' + ' '.join(f'{rom.u8(FIELD_RATE_NIGHT + i):02X}' for i in range(14)))
        for name, addr, rows in FIELD_GRIDS:
            print(f'{name} ({0x230000 | addr & 0xFFFF:06X}, {FIELD_WIDTH}x{rows}, 한 칸 = 32x32 필드 좌표)')
            for row in field_grid(rom, addr, rows):
                print('  ' + ' '.join(f'{x:02X}' for x in row))
        return 0
    if args.bc is not None:
        bc, bd = int(args.bc, 16), int(args.bd, 16)
        e = map_entry(rom, bc, bd)
        if e is None:
            print('그런 맵 없음')
            return 1
        print(f'{bc:02X}/{bd:02X} 구역($1948=0/1/2) ' + ' '.join(f'{x:02X}' for x in e[:3]) +
              f'  조우율 {INDOOR_RATE}')
        for n in sorted({x for x in e[:3] if x != 0xFF}):
            print(format_area(rom, area(rom, n)))
        return 0
    for n in range(AREA_COUNT):
        print(format_area(rom, area(rom, n)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
