"""FC 3장 엔돌 카지노의 슬롯머신(릴 셋·줄 다섯)을 DQ5 슬롯 틀 위에 옮긴다.

FC 슬롯(뱅크 17, fc/dq4/docs/dq4-chapter3-format.md 「슬롯머신」)의 화면·무늬·릴 띠·줄·배당을 빌드가 FC 롬에서 읽어
SFC 자료로 바꾸고, 놀이는 dq4fcslot.asm 이 한다. DQ5 슬롯의 틀은 그대로 쓴다: 06:D14A(583·584 와 「예」) → 02:A8BC
(필드 저장·되돌림) → 11:BF71(슬롯 본체). 11:BF71 입구에서 기계 번호가 FIRST_MACHINE 이상이면 FC 본체로 간다.
FC 본체는 DQ5 슬롯 NMI(00:FEDD: BG3 타일맵 7E:6000 → VRAM 1400, CGRAM 30~5F ← $12CC, 패드 $1212)를 그대로 쓰고,
BG1 에 FC 화면, OBJ 에 무늬·램프·코인 수, BG3 에 글 창(11:BA8B 테두리, 11:B970 글, dq4slottext 한글 타일)을 둔다.
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools'), str(HERE.parents[2] / 'fc' / 'dq4' / 'tools')]

from dq5map import lorom  # noqa: E402

# FC 뱅크 17 자리(코드 읽기, 덤프와 견줌)
FC_BANK = 0x17
ROW_PATTERN, PATTERNS, REEL_ROWS, PIECES, ATTRS = 0xA744, 0xA763, 0xA7F7, 0xA806, 0xA8CC
PALETTES = 0xA975                  # BG 넷·OBJ 넷, 3바이트씩(색 0 = 0F)
BG_TILES, BG_FIRST = 0xA9C1, 0x90  # 타일 90~ 이 이어져 있음
SYMBOL_TILES = 0xAEE1              # 무늬 k(1~7)의 16x16 네 칸이 (k - 1) * 40 에
SMALL_TILES = 0xB0A1               # 숫자(01~0A = 0~9, 0B 빈칸)·램프(0C)가 타일 × 16 에
SYMBOL_PAL = 0xA666                # 무늬별 OBJ 팔레트
STRIPS, STRIP_PTRS, STRIP_SHAPE, STRIP_KIND = 0xA4BF, 0xA4B5, 0xA5FD, 0xA605
LINES = (0x9FCB, 0x9FD0, 0x9FD5)   # 줄마다 격자 칸 셋
PAYOUT = 0x9F4C                    # 색인 0~7 배당(2바이트)
FC_ROWS = 30
# FC 글 창(행 22~27)은 BG3 의 DQ5 창으로 바꾸므로 바탕 칸으로 덮는다
BOX_ROWS, BOX_FILL = range(22, 28), 0x8F
# 무늬가 비치는 릴 창(이 칸만 낮은 우선순위, 나머지 BG1 칸이 OBJ 우선순위 2 의 무늬를 가린다)
REEL_WINDOW_ROWS, REEL_WINDOW_COLS = range(6, 17), (*range(6, 10), *range(12, 16), *range(18, 22))
FILLS = {0x00: bytes(16), 0x8D: b'\xff' * 8 + bytes(8), 0x8E: b'\xff' * 16, 0x8F: bytes(8) + b'\xff' * 8}

FIRST_MACHINE = 0x10               # 06:D14A 에 넘기는 기계 번호 = FIRST_MACHINE + FC 기계(0~4)
MACHINES = 5
HOOK_AT, HOOK_ORIG = 0x11BF71, bytes.fromhex('08 8B C2 10')    # PHP / PHB / REP #$10
HOOK_BACK = 0x11BF75
from dq4ch3slots import CASINO_CODE  # noqa: E402
CODE_AT, CODE_END = CASINO_CODE
# 뱅크 11 받침(JSR 루틴을 다른 뱅크에서 부르고, 4E 에서 못 쓰는 BRK 효과음을 낸다). 슬롯 글 자리(dq4slottext)의 뒤 남는 곳
STUBS_AT, STUBS_END = 0x119030, 0x119044
# BG1 타일맵·글자, OBJ 글자(VRAM 워드). DQ5 슬롯 NMI 가 BG1 레버 칸(VRAM 11DC·11FC)을 쓰므로 BG1 맵은 0C00 에 둔다
BG1_MAP, BG1_CHR, OBJ_CHR = 0x0C00, 0x2000, 0x6000
BG_PAL, OBJ_PAL = 3, 0             # FC BG 팔레트 p → SNES 팔레트 BG_PAL + p


def fc_prg(dq4):
    from kr_patch.fc import ines
    return ines.prg(Path(dq4).read_bytes())


def rd(prg, a, n=1):
    o = FC_BANK * 0x4000 + a - 0x8000
    return prg[o] if n == 1 else prg[o:o + n]


def nametable(prg):
    """FC 17:$A68D 의 화면 짜기를 그대로: (타일 32x30, 속성 64바이트)."""
    nt, at = bytearray(0x400), [0]

    def put(v):
        nt[at[0]] = v
        at[0] += 1

    def pattern(v):
        ptr = rd(prg, PATTERNS + v * 2) | rd(prg, PATTERNS + v * 2 + 1) << 8
        y = 0
        while n := rd(prg, ptr + y):
            for _ in range(n):
                put(rd(prg, ptr + y + 1))
            y += 2
    for row in range(0x1F):
        pattern(rd(prg, ROW_PATTERN + row))
    addr, x = 0x20A5, 0
    while v := rd(prg, REEL_ROWS + x):
        at[0] = addr - 0x2000
        for _ in range(3):
            pattern(v)
        x, addr = x + 1, addr + 0x20
    y = 0
    while (lo := rd(prg, PIECES + y)) != 0xFF:
        at[0] = (rd(prg, PIECES + y + 1) << 8 | lo) - 0x2000
        y += 2
        while (t := rd(prg, PIECES + y)) != 0xFF:
            put(t)
            y += 1
        y += 1
    # 행 무늬 31줄째가 속성 표 앞 반을 채우고, 그 위에 ATTRS 26바이트를 덮는다(FC 와 같은 차례)
    for k in range(0x26):
        nt[0x3C0 + k] = rd(prg, ATTRS + k)
    return bytes(nt[:FC_ROWS * 32]), bytes(nt[0x3C0:0x400])


def fc_tile(prg, t):
    if t in FILLS:
        return FILLS[t]
    if t < BG_FIRST:
        raise ValueError(f'FC 슬롯 BG 타일 {t:02X} 의 자리를 모름')
    return rd(prg, BG_TILES + (t - BG_FIRST) * 16, 16)


def snes4(fc):
    """FC 2bpp 8x8 → SNES 4bpp(평면 2·3 은 0)."""
    return b''.join(bytes((fc[r], fc[8 + r])) for r in range(8)) + bytes(16)


def nes_color(c):
    import dq4block
    import dq4chapterbox
    return dq4chapterbox.bgr555(dq4block.nes_rgb(c))


def palettes(prg):
    """(BG CGRAM 자리와 바이트, OBJ CGRAM 자리와 바이트). 팔레트마다 16색, 색 0 은 투명이라 검정."""
    def pal(k):
        return bytes(2) + b''.join(nes_color(c) for c in rd(prg, PALETTES + 3 * k, 3)) + bytes(24)
    return (b''.join(pal(k) for k in range(4)), b''.join(pal(4 + k) for k in range(4)))


def bg(prg):
    """(BG1 타일 바이트, BG1 타일맵 32x32 워드). SNES 행 s = FC 행 s + 1(224줄)."""
    nt, attrs = nametable(prg)
    rows = [nt[r * 32:r * 32 + 32] for r in range(FC_ROWS)]
    for r in BOX_ROWS:
        rows[r] = bytes((BOX_FILL,)) * 32
    tiles, index, words = [], {}, bytearray(0x800)
    for s in range(28):
        r = s + 1
        for c in range(32):
            t = rows[r][c]
            if t not in index:
                index[t] = len(tiles)
                tiles.append(snes4(fc_tile(prg, t)))
            a = attrs[(r // 4) * 8 + c // 4]
            p = a >> (((r // 2) % 2) * 4 + ((c // 2) % 2) * 2) & 3
            low = r in REEL_WINDOW_ROWS and c in REEL_WINDOW_COLS
            w = index[t] | (BG_PAL + p) << 10 | (0 if low else 0x2000)
            words[(s * 32 + c) * 2:(s * 32 + c) * 2 + 2] = w.to_bytes(2, 'little')
    return b''.join(tiles), bytes(words)


def obj(prg):
    """OBJ 글자(16칸 줄): 무늬 k 는 이름 (k - 1) * 2(16x16), 작은 타일 t 는 이름 SMALL_NAME + t."""
    sheet = bytearray(32 * 16 * 4)

    def place(name, fc):
        sheet[name * 32:name * 32 + 32] = snes4(fc)
    for k in range(1, 8):
        base = SYMBOL_TILES + (k - 1) * 0x40
        for j, (dx, dy) in enumerate(((0, 0), (1, 0), (0, 1), (1, 1))):
            place((k - 1) * 2 + dx + dy * 16, rd(prg, base + j * 16, 16))
    for t in range(1, 0x0D):
        place(SMALL_NAME + t, rd(prg, SMALL_TILES + t * 16, 16))
    return bytes(sheet)


SMALL_NAME = 0x20                  # 작은 타일 t 의 OBJ 이름 = 20 + t(둘째 줄 첫 칸부터)


def machine_data(prg):
    """기계마다 [띠 길이 가림(0F/1F), 릴 셋 × 32칸 무늬(16칸 띠는 두 번 이어 둠)]."""
    out = bytearray()
    for k in range(MACHINES):
        ptr = rd(prg, STRIP_PTRS + 2 * k) | rd(prg, STRIP_PTRS + 2 * k + 1) << 8
        y = rd(prg, STRIP_KIND + k)
        starts, mask = [rd(prg, STRIP_SHAPE + y + i) for i in range(3)], rd(prg, STRIP_SHAPE + y + 3)
        out.append(mask)
        for s in starts:
            strip = bytes(rd(prg, ptr + s + i) for i in range(mask + 1))
            out += (strip * (32 // len(strip)))
    return bytes(out)


def tables(prg):
    lines = bytes(rd(prg, LINES[j] + i) for i in range(5) for j in range(3))     # 줄마다 칸 셋
    pay = rd(prg, PAYOUT, 16)
    sympal = bytes(rd(prg, SYMBOL_PAL + k) & 3 for k in range(8))
    xs = rd(prg, 0xA65B, 3)
    return lines, pay, sympal, xs


def apply(data, dq4, font, asar=None):
    asar = asar or os.environ.get('ASAR')
    if not asar:
        raise SystemExit('ASAR 에 asar 실행 파일을 주세요(sfc/dq4/docs/dq4-menu-format.md)')
    prg = fc_prg(dq4)
    d = bytearray(data)
    if bytes(d[lorom(HOOK_AT):lorom(HOOK_AT) + 4]) != HOOK_ORIG:
        raise SystemExit(f'{HOOK_AT:06X}: 슬롯 본체 첫 바이트가 원래 값이 아님')
    if any(d[lorom(CODE_AT):lorom(CODE_END - 1) + 1]) or any(d[lorom(STUBS_AT):lorom(STUBS_END)]):
        raise SystemExit('FC 슬롯 코드 자리가 비어 있지 않음')
    bg_tiles, bg_map = bg(prg)
    obj_tiles = obj(prg)
    bgpal, objpal = palettes(prg)
    lines, pay, sympal, xs = tables(prg)
    import dq4slottext
    lay = dq4slottext.Layout(font)
    files = {'bgtiles.bin': bg_tiles, 'bgmap.bin': bg_map, 'objtiles.bin': obj_tiles, 'bgpal.bin': bgpal,
             'objpal.bin': objpal, 'machines.bin': machine_data(prg), 'lines.bin': lines, 'pay.bin': pay,
             'sympal.bin': sympal, 'reelx.bin': xs}
    defs = ''.join(f'!{k} = ${v:X}\n' for k, v in {
        'code_at': CODE_AT, 'code_end': CODE_END, 'stubs_at': STUBS_AT, 'stubs_end': STUBS_END, 'hook_at': HOOK_AT,
        'hook_back': HOOK_BACK, 'first_machine': FIRST_MACHINE, 'bg1_map': BG1_MAP, 'bg1_chr': BG1_CHR,
        'obj_chr': OBJ_CHR, 'bg_pal_cg': BG_PAL * 16, 'obj_pal_cg': 0x80 + OBJ_PAL * 16, 'small_name': SMALL_NAME,
        'slottext_code': dq4slottext.CODE_AT, 'cursor_tile': lay.cursor & 0xFF,
        **{f'str_{name}': at for name, at in lay.addrs().items()},
    }.items())
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for name, blob in files.items():
            (tmp / name).write_bytes(blob)
        (tmp / 'main.asm').write_text(defs + (HERE / 'dq4fcslot.asm').read_text())
        (tmp / 'rom.sfc').write_bytes(bytes(d))
        r = subprocess.run([asar, '--fix-checksum=off', str(tmp / 'main.asm'), str(tmp / 'rom.sfc')],
                           capture_output=True, text=True)
        if r.returncode:
            raise SystemExit(f'asar: {r.stdout}{r.stderr}')
        out = (tmp / 'rom.sfc').read_bytes()
    if any(out[lorom(CODE_END):lorom(CODE_END) + 0x10]):
        raise ValueError('FC 슬롯 코드가 정해 둔 자리를 넘음')
    return out
