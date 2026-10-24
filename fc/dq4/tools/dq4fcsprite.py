"""DQ4(FC) 필드 인물·탈것 스프라이트와 전투 몬스터 그림을 롬에서 뽑는다. 형식은 docs/dq4-fcsprite-format.md.

사용:
  python tools/dq4fcsprite.py rom/dq4.nes field [N ...]     필드 그림(그림 번호, 없으면 표 00~6B 와 쓰이는 돌려 그리기 전부)
                                                             → work/dq4-fcsprite/field/
  python tools/dq4fcsprite.py rom/dq4.nes monster [ID ...]  몬스터 그림(몬스터 ID, 없으면 전부) → work/dq4-fcsprite/monster/
  python tools/dq4fcsprite.py rom/dq4.nes sheet              위 둘을 모두 만들고 index.html·sheet-*.png 로 묶음
  python tools/dq4fcsprite.py rom/dq4.nes who N              그림 번호 N(인물 레코드 값, 16진)을 쓰는 맵·인물
  python tools/dq4fcsprite.py rom/dq4.nes check-rom          몬스터 데이터 경계 검사(끝 = 다음 시작)
  python tools/dq4fcsprite.py rom/dq4.nes check-field DIR...    seq.lua·warp.lua 덤프(end.sram/chr/oam)와 비교
  python tools/dq4fcsprite.py rom/dq4.nes check-monster DIR...  lua/fc/spritebattle.lua 덤프(end.sram/nt/chr/pal/oam)와 비교
  --out 폴더 로 출력 위치를 바꾼다(기본 work/dq4-fcsprite). 롬 그림이므로 work/ 밖에 두지 않는다.

필드 근거 루틴: 08:$85D3(BRK 04 87, 그림 하나 올리기), $859B(번호 → 표 번호), $80D5·$8132(레코드 → 타일 주소 4개),
$8254(같은 주소 다시 안 올림, $7700), $82B0(타일 번호·속성 → $7200+칸×64), $8981·$89C9(돌려 그리기), $83BD(CHR $0000 으로 복사).
OBJ 팔레트 08:$86F2(08:$8703 12바이트 → $0609). 일행 1E:$9648, 필드 탈것 1E:$9799.
몬스터 근거 루틴: 14:$812F(전투 그림 올리기), $9F0C(몬스터 ID → 그림 번호 14:$B2D5), $9FA9(그림 레코드 14:$A019, 5바이트),
$9F26(데이터 뱅크), $9712(타일 16바이트 풀기), $9783(BG·OBJ 패턴으로 올리기), $98F5(배치), $9557·$9593(팔레트).
"""
import argparse
import html
import os
import sys

from kr_patch.fc import ines

import dq4block
import dq4data
import dq4map
import dq4talk
import dq4text

B08 = 0x08
FIELD_TABLE = 0x8649     # 08:$8649 의 워드 → 그림 표(08:$979B, 24바이트 = 3바이트 레코드 8개)
FIELD_BASE = 0x8231      # 08:$8229+8: 뱅크 0D·0E 의 타일 0 주소
FIELD_OFFS = 0x8239      # 08:$8237+2: 모양마다 다음 타일까지 부호 있는 16바이트 단위 3개
OBJ_PAL = 0x8703         # 08:$86F2 가 $0609 에 복사(FF 로 끝)
FIELD_COUNT = 108        # 표는 08:$A1BB(블록 모양 표) 앞에서 끝난다
VEHICLES = (0x1E, 0x97AE, 10)   # 1E:$9799 가 필드에서 칸 4~D 에 올리는 그림 번호 10개
DIRS = ('북', '동', '남', '서')  # 블록 = 방향 × 2 + 걸음. 방향은 $7000(0 위 1 오른쪽 2 아래 3 왼쪽)
SHEET_ROWS = (2, 3, 1, 0)        # 시트 행 순서: 남·서·동·북(docs/dq4-sprite-format.md 시트와 같은 순서)
B14 = 0x14
MON_PIC = 0xB2D5         # 14:$9F0C: 몬스터 ID → 그림 번호
MON_REC = 0xA019         # 14:$9FA9 의 워드 → 그림마다 5바이트(타일 수, 데이터 주소, 팔레트 주소)
MON_BANKBITS = 0xB398    # 14:$9F4A: 그림 번호 비트가 1 이면 뱅크 07, 0 이면 06
MON_BANK_SPECIAL = {0x14: 0x14, 0x2E: 0x14, 0x3F: 0x14, 0xB2: 0x14, 0xC0: 0x14, 0xB1: 0x10}
MON_ROW0 = 10            # 그림 BG 0행이 화면 nametable 10행(실측)
MON_ROW0_BIG = {0xAE: 8, 0xBC: 8}   # デスピサロ·エスターク 는 8행(실측: エスターク)
GREY = (0x00, 0x10, 0x20)    # 팔레트를 모를 때 대신 쓰는 회색 세 단계
MON_OBJ_Y = 0x4F         # OBJ y = 바이트 2 + 4F(14:$9963). 화면에는 한 줄 아래에 그려진다


def rd(prg, bank, addr):
    return prg[bank * 0x4000 + (addr & 0x3FFF)]


def wd(prg, bank, addr):
    return rd(prg, bank, addr) | rd(prg, bank, addr + 1) << 8


def planes(data):
    """2bpp 16바이트 → 8×8 색 번호(0~3)."""
    return [[(data[y] >> (7 - x) & 1) | (data[8 + y] >> (7 - x) & 1) << 1 for x in range(8)] for y in range(8)]


def flip(px, h, v):
    rows = px[::-1] if v else px
    return [r[::-1] if h else list(r) for r in rows]


# --- 필드 ---------------------------------------------------------------

def field_index(n):
    """08:$859B: 그림 번호(아래 7비트) → 표 번호. 53 이상은 −0B, 48~4F 는 일행 0~7. bit7 은 돌려 그리기."""
    m = n & 0x7F
    if m >= 0x53:
        m -= 0x0B
    elif 0x48 <= m < 0x50:
        m -= 0x48
    return m, bool(n & 0x80)


def field_record(prg, m, j):
    a = wd(prg, B08, FIELD_TABLE) + 24 * m + 3 * j
    return [rd(prg, B08, a + i) for i in range(3)]


def rotate_tile(data):
    """08:$89C9: 8×8 타일을 시계 방향으로 90° 돌린 16바이트."""
    out = bytearray(16)
    for p in (0, 8):
        for j in range(8):
            m = 0x80 >> j
            out[p + j] = sum(1 << r for r in range(8) if data[p + r] & m)
    return bytes(out)


def field_blocks(prg, n):
    """그림 번호 n 의 블록 8개(방향 × 2 + 걸음). 블록 = 타일 4개(왼위·오른위·왼아래·오른아래),
    타일 = (뱅크, 주소, 16바이트, 좌우 반전, 상하 반전, OBJ 팔레트).
    bit7(돌려 그리기)이면 레코드 4 하나를 방향마다 90°씩 돌린다(08:$8618·$8981·$89C9·$82CB)."""
    m, rot = field_index(n)
    base = (wd(prg, B08, FIELD_BASE), wd(prg, B08, FIELD_BASE + 2))
    offs = wd(prg, B08, FIELD_OFFS)
    out = []
    for j in range(8):
        r0, r1, r2 = field_record(prg, m, 4 if rot else j)
        form, hb = r2 >> 2, (r1 >> 2) & 1
        if form == 0x3F:
            raise ValueError(f'표 {m:02X} 블록 {j}: 모양 3F(08:$81C6 경로)는 그림 표에 없어야 함')
        a = (base[hb] + (((r1 & 3) << 8 | r0) << 4)) & 0xFFFF
        addrs = [a]
        for i in range(3):
            v = rd(prg, B08, offs + form * 3 + i)
            a = (a + ((v - 256 if v & 0x80 else v) << 4)) & 0xFFFF
            addrs.append(a)
        nib, k = r1 >> 4, (j >> 1) if rot else 0
        for _ in range(k):   # 4타일 자리와 반전 비트를 시계 방향으로
            addrs = [addrs[2], addrs[0], addrs[3], addrs[1]]
            nib = (nib >> 1 & 1) << 3 | (nib >> 3 & 1) << 2 | (nib & 1) << 1 | (nib >> 2 & 1)
        tiles = []
        for i, a in enumerate(addrs):
            data = bytes(rd(prg, 0x0D + hb, a + b) for b in range(16))
            for _ in range(k):
                data = rotate_tile(data)
            f = bool(nib >> (3 - i) & 1)
            # 08:$82F6: 돌린 횟수가 홀수면 반전 비트가 상하 반전으로 간다
            tiles.append((0x0D + hb, a, data, f and k % 2 == 0, f and k % 2 == 1, r2 & 3))
        out.append(tiles)
    return out


def field_load(prg, n, start):
    """08:$85D3 을 흉내 내 $7200+칸×64 의 64바이트와 올리는 CHR(타일 번호 → 16바이트)을 돌려준다.
    같은 그림 주소는 다시 올리지 않는다(주소만 비교, 뱅크는 안 봄). 돌려 그리기는 방향마다 목록을 비운다."""
    m, rot = field_index(n)
    seen, nxt, base, table, chr_ = [], start, start, bytearray(), {}
    for j, tiles in enumerate(field_blocks(prg, n)):
        for bank, a, data, h, v, pal in tiles:
            if a in seen:
                t = base + seen.index(a)
            else:
                seen.append(a)
                t, nxt = nxt, nxt + 1
                chr_[t] = data
            table += bytes([t & 0xFF, (0x80 if v else 0) | (0x40 if h else 0) | pal])
        if rot and j & 1:
            seen, base = [], nxt
    return bytes(table), chr_


def obj_palettes(prg):
    p = [rd(prg, B08, OBJ_PAL + i) for i in range(12)]
    return [p[3 * i:3 * i + 3] for i in range(4)]


def field_frame(prg, n, block):
    """16×16 (색 번호 행렬, 팔레트 번호). 팔레트는 레코드마다 하나라 블록 안에서 같다."""
    tiles = field_blocks(prg, n)[block]
    px = [[0] * 16 for _ in range(16)]
    for i, (_, _, data, h, v, pal) in enumerate(tiles):
        t = flip(planes(data), h, v)
        for y in range(8):
            for x in range(8):
                px[(i >> 1) * 8 + y][(i & 1) * 8 + x] = t[y][x]
    return px, tiles[0][5]


def party_names():
    return [f'{dq4data.PARTY[i]}' for i in range(8)] + ['勇者(여)']


def raw_number(m, rot=False):
    """표 번호 → 그 표를 가리키는 그림 번호 하나(48~4F 는 일행으로 바뀌므로 53~ 쪽)."""
    return (m if m < 0x48 else m + 0x0B) | (0x80 if rot else 0)


def field_stem(n):
    m, rot = field_index(n)
    return f'{m:02X}' + ('r' if rot else '')


SEEN = {0x09: '말', 0x0A: '마차', 0x0B: '배', 0x0C: '기구', 0x0E: '관'}   # 그림을 보고 붙인 이름


def field_label(prg, n):
    m, rot = field_index(n)
    if rot:
        return '돌려 그리기'
    if m < 9:
        return party_names()[m]
    if m in SEEN:
        return SEEN[m] + (' 필드 칸 4~D(1E:$9799)' if m != 0x0E else ' 빈 일행 칸')
    vs = [field_index(rd(prg, VEHICLES[0], VEHICLES[1] + i))[0] for i in range(VEHICLES[2])]
    if m in vs:
        return f'필드 칸 {4 + vs.index(m):X}(1E:$9799)'
    return ''


# --- 몬스터 -------------------------------------------------------------

def mon_pic(prg, mid):
    return rd(prg, B14, MON_PIC + mid)


def mon_bank(prg, p):
    if p in MON_BANK_SPECIAL:
        return MON_BANK_SPECIAL[p]
    return 0x07 if rd(prg, B14, MON_BANKBITS + (p >> 3)) << (p & 7) & 0x80 else 0x06


def mon_record(prg, p):
    a = wd(prg, B14, MON_REC) + 5 * p
    n, lo, hi, plo, phi = (rd(prg, B14, a + i) for i in range(5))
    return n, lo | hi << 8, plo | phi << 8


def mon_stream(prg, p):
    """(타일 목록, OBJ 팔레트, BG 팔레트, 데이터 뱅크, 시작, 끝).
    타일 = (배치 목록, 16바이트). 배치 = (머리 바이트 H, 자리 바이트들). H bit7 = 이 타일의 마지막 배치,
    bit6 = BG(자리 1바이트 = 행 << 4 | 열) / 0 이면 OBJ(자리 2바이트 = x, y), bit5-4 팔레트, bit2 상하·bit1 좌우 반전.
    마지막 배치의 bit3 이면 타일이 압축: bit0 이면 채움 바이트, 그다음 16비트 마스크(둘째 바이트가 위),
    마스크 1 인 자리만 바이트가 있음(14:$9734). bit3 이 0 이면 16바이트 그대로."""
    n, a, pa = mon_record(prg, p)
    b, start = mon_bank(prg, p), a
    tiles = []
    for _ in range(n):
        pls = []
        while True:
            h = rd(prg, b, a)
            k = 1 if h & 0x40 else 2
            pls.append((h, tuple(rd(prg, b, a + 1 + i) for i in range(k))))
            a += 1 + k
            if h & 0x80:
                break
        if h & 0x08:
            fill = 0
            if h & 1:
                fill, a = rd(prg, b, a), a + 1
            mask, a = rd(prg, b, a + 1) << 8 | rd(prg, b, a), a + 2
            data = bytearray()
            for i in range(16):
                if mask & 0x8000 >> i:
                    data.append(rd(prg, b, a))
                    a += 1
                else:
                    data.append(fill)
        else:
            data = bytearray(rd(prg, b, a + i) for i in range(16))
            a += 16
        tiles.append((pls, bytes(data)))
    c = rd(prg, B14, pa)
    tri = [[rd(prg, B14, pa + 1 + 3 * i + j) for j in range(3)] for i in range((c >> 4) + (c & 15))]
    return tiles, tri[:c & 15], tri[c & 15:], b, start, a


def mon_pixels(prg, mid):
    """몬스터 그림의 픽셀: {(x, y): NES 색 번호}. 좌표는 그림 BG 0행·0열 기준(OBJ 는 화면에 그려지는 자리).
    BG 가 먼저, OBJ 가 위에 그린다(OBJ 우선순위 비트는 0)."""
    p = mon_pic(prg, mid)
    tiles, opal, bpal, *_ = mon_stream(prg, p)
    row0 = MON_ROW0_BIG.get(p, MON_ROW0)
    bg, obj = {}, {}
    for pls, data in tiles:
        px = planes(data)
        for h, pos in pls:
            t = flip(px, h & 2, h & 4)
            pals = bpal if h & 0x40 else opal
            # デスピサロ(그림 AE)는 팔레트를 그림 레코드가 아닌 곳에서 받는다(14:$815A 가 팔레트 맞추기를 건너뜀)
            pal = pals[h >> 4 & 3] if (h >> 4 & 3) < len(pals) else GREY
            if h & 0x40:
                ox, oy, dst = (pos[0] & 15) * 8, (pos[0] >> 4) * 8, bg
            else:
                # 화면 자리는 (x + 그림 왼쪽 열 × 8) & FF, (y + 4F) & FF 라 그림 기준으로는 부호 있는 바이트
                sx, sy = (v - 256 if v & 0x80 else v for v in pos)
                ox, oy, dst = sx, sy + MON_OBJ_Y + 1 - row0 * 8, obj
            for y in range(8):
                for x in range(8):
                    if t[y][x]:
                        dst[(ox + x, oy + y)] = pal[t[y][x] - 1]
    bg.update(obj)
    return bg


# --- 그림 파일 ----------------------------------------------------------

B36 = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'


def indexed(colors_at, w, h, ox=0, oy=0):
    """{(x, y): NES 색} → (색 번호 행렬, 색 목록). 색 번호 1~ 은 처음 나온 순서, 같은 NES 색은 한 번호."""
    order = []
    grid = [[0] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            c = colors_at.get((x + ox, y + oy))
            if c is None:
                continue
            if c not in order:
                order.append(c)
            grid[y][x] = order.index(c) + 1
    return grid, order


def matrix_text(grid):
    return '\n'.join(''.join(B36[v] if v else '.' for v in row) for row in grid)


def save_png(path, grid, colors, scale=1):
    from PIL import Image
    h, w = len(grid), len(grid[0])
    im = Image.new('P', (w, h), 0)
    pal = [0, 0, 0]
    for c in colors:
        pal += list(dq4block.nes_rgb(c))
    im.putpalette(pal + [0] * (768 - len(pal)))
    im.putdata([v for row in grid for v in row])
    if scale > 1:
        im = im.resize((w * scale, h * scale), Image.NEAREST)
    im.save(path, transparency=0)


def field_sheet(prg, n):
    """그림 번호 n 의 시트 {(x, y): NES 색}: 32×64, 행 남·서·동·북, 열 걸음 0·1."""
    pals, out = obj_palettes(prg), {}
    for row, d in enumerate(SHEET_ROWS):
        for col in range(2):
            px, pal = field_frame(prg, n, d * 2 + col)
            for y in range(16):
                for x in range(16):
                    if px[y][x]:
                        out[(col * 16 + x, row * 16 + y)] = pals[pal][px[y][x] - 1]
    return out


def write_field(prg, n, folder):
    grid, colors = indexed(field_sheet(prg, n), 32, 64)
    stem = os.path.join(folder, field_stem(n))
    save_png(stem + '.png', grid, colors)
    save_png(stem + '-x8.png', grid, colors, 8)
    lines = [f'# 필드 그림 번호 {n:02X}(표 {field_index(n)[0]:02X}) {field_label(prg, n)}'.rstrip(),
             '# 32×64: 행 남·서·동·북, 열 걸음 0·1(16×16 씩). 색 번호 1~ = NES 색 ' +
             ' '.join(f'{i + 1}={c:02X}' for i, c in enumerate(colors))]
    for row, d in enumerate(SHEET_ROWS):
        for col in range(2):
            px, pal = field_frame(prg, n, d * 2 + col)
            lines.append(f'[{DIRS[d]} 걸음{col} 블록{d * 2 + col} OBJ 팔레트 {pal}] (팔레트 안 색 번호 1~3)')
            lines.append(matrix_text(px))
    with open(stem + '.txt', 'w') as f:
        f.write('\n'.join(lines) + '\n')
    return grid, colors


def mon_box(px):
    xs, ys = [x for x, _ in px], [y for _, y in px]
    return min(xs), min(ys), max(xs) + 1, max(ys) + 1


def write_monster(prg, mid, folder, names):
    px = mon_pixels(prg, mid)
    x0, y0, x1, y1 = mon_box(px)
    grid, colors = indexed(px, x1 - x0, y1 - y0, x0, y0)
    stem = os.path.join(folder, f'{mid:02X}')
    save_png(stem + '.png', grid, colors)
    save_png(stem + '-x8.png', grid, colors, 8)
    p = mon_pic(prg, mid)
    tiles, opal, bpal, b, start, _ = mon_stream(prg, p)
    head = [f'# 몬스터 {mid:02X} {names[mid]} 그림 {p:02X} 데이터 {b:02X}:{start:04X} 타일 {len(tiles)}',
            f'# {x1 - x0}×{y1 - y0}, 왼위 = 그림 BG 0행 기준 ({x0},{y0}). 색 번호 = NES 색 ' +
            ' '.join(f'{B36[i + 1]}={c:02X}' for i, c in enumerate(colors)),
            '# BG 팔레트 ' + ' / '.join(' '.join(f'{c:02X}' for c in t) for t in bpal) +
            ('  OBJ 팔레트 ' + ' / '.join(' '.join(f'{c:02X}' for c in t) for t in opal) if opal else '')]
    with open(stem + '.txt', 'w') as f:
        f.write('\n'.join(head) + '\n' + matrix_text(grid) + '\n')
    return grid, colors


def monster_names(prg):
    return [dq4text.text(nm) for nm in dq4data.name_list(prg, 'monster')[1:]]


# --- 쓰는 곳 ------------------------------------------------------------

def users(prg):
    """(그림 번호, 장소 'GG/KK', 목록 이름, 인물 순번, 레코드) 전부. 보통 목록 낮·밤과 진행 목록(1C:$9D0E) 낮·밤.
    dq4talk.show_looks 와 같은 범위이고, 그림 번호는 dq4talk.sprite. 순번은 그 시간에 나오는 레코드만 센 것."""
    out = []

    def add(recs, place, kind):
        for night in (False, True):
            shown = [r for r in recs if r[0] & (0x08 if night else 0x10)]
            for i, r in enumerate(shown):
                out.append((dq4talk.sprite(r, night), place, kind + ('밤' if night else '낮'), i, r))
    for g, k, *_ in dq4map.maps(prg):
        add(dq4map.npc_records(prg, g, k), f'{g:02X}/{k:02X}', '')
    for g, k, m, fi, a in dq4map.event_entries(prg):
        add(dq4map.records_at(prg, 0x1C, a)[0], f'{g:02X}/{k:02X}', f'진행 {fi:02X}&{m:02X} ')
    return out


def field_numbers(prg):
    """뽑을 그림 번호: 표 00~6B 를 그대로 한 번씩, 그리고 인물 레코드가 쓰는 돌려 그리기 번호."""
    rot = sorted({raw_number(field_index(u[0])[0], True) for u in users(prg) if u[0] & 0x80})
    return [raw_number(m) for m in range(FIELD_COUNT)] + rot


def cmd_who(prg, n):
    """그림 번호 n 과 같은 겉모습(같은 표, 같은 돌려 그리기 여부)을 쓰는 인물 레코드."""
    key = field_index(n)
    hits = [u for u in users(prg) if field_index(u[0]) == key]
    print(f'그림 번호 {n:02X} → 표 {field_stem(n)} {field_label(prg, n)}: 인물 {len(hits)}명')
    for s, place, kind, i, r in hits:
        night = kind.endswith('밤')
        x, y = dq4talk.pos(r, night)
        tid = dq4talk.talk_id(r, night)
        print(f'  {place} {kind} 슬롯 {6 + i:2d} ({x:02X},{y:02X}) 그림 {s:02X} 대화 {tid:03X}')


# --- 묶음 ---------------------------------------------------------------

def cmd_sheet(prg, out):
    from PIL import Image
    fd, md = os.path.join(out, 'field'), os.path.join(out, 'monster')
    os.makedirs(fd, exist_ok=True)
    os.makedirs(md, exist_ok=True)
    names = monster_names(prg)
    use = {}
    for s, place, *_ in users(prg):
        use.setdefault(field_index(s), set()).add(place)
    cells = []
    for n in field_numbers(prg):
        write_field(prg, n, fd)
        places = sorted(use.get(field_index(n), ()))
        cells.append((f'field/{field_stem(n)}', f'표 {field_stem(n)}', field_label(prg, n),
                      f'맵 {len(places)}곳: ' + ' '.join(places[:6]) + (' …' if len(places) > 6 else '') if places else ''))
    mcells = []
    for mid in range(len(names)):
        write_monster(prg, mid, md, names)
        mcells.append((f'monster/{mid:02X}', f'{mid:02X} {names[mid]}', f'그림 {mon_pic(prg, mid):02X}', ''))

    def contact(items, path, cell_w, cell_h, cols):
        rows = (len(items) + cols - 1) // cols
        im = Image.new('RGBA', (cols * cell_w, rows * cell_h), (40, 40, 40, 255))
        for i, (stem, *_) in enumerate(items):
            t = Image.open(os.path.join(out, stem + '.png')).convert('RGBA')
            x, y = (i % cols) * cell_w, (i // cols) * cell_h
            im.alpha_composite(t, (x + (cell_w - t.width) // 2, y + (cell_h - t.height) // 2))
        im.save(path)
    contact(cells, os.path.join(out, 'sheet-field.png'), 40, 72, 18)
    contact(mcells, os.path.join(out, 'sheet-monster.png'), 136, 112, 13)

    def section(title, items, scale):
        s = [f'<h2>{html.escape(title)}</h2><div class="grid">']
        for stem, head, sub, note in items:
            s.append(f'<figure><a href="{stem}-x8.png"><img src="{stem}.png" style="zoom:{scale}"></a>'
                     f'<figcaption><b>{html.escape(head)}</b> {html.escape(sub)}<br><small>{html.escape(note)}</small>'
                     f' <a href="{stem}.txt">행렬</a></figcaption></figure>')
        return '\n'.join(s + ['</div>'])
    page = ('<!doctype html><meta charset="utf-8"><title>DQ4 FC 스프라이트</title>'
            '<style>body{background:#222;color:#ddd;font:13px sans-serif;margin:16px}'
            '.grid{display:flex;flex-wrap:wrap;gap:8px}figure{margin:0;padding:6px;background:#333;width:180px}'
            'img{image-rendering:pixelated;background:#555}a{color:#9cf}</style>'
            '<h1>DQ4(FC) 필드 그림·몬스터 그림</h1><p>롬에서 뽑은 그림입니다. 필드 그림은 32×64(행 남·서·동·북, 열 걸음 0·1), '
            '몬스터는 그림 크기 그대로. 그림을 누르면 8배, 「행렬」 은 색 번호 행렬입니다. 색은 근사 RGB 입니다.</p>'
            + section('필드 그림(표 번호)', cells, 2) + section('몬스터(ID)', mcells, 2))
    with open(os.path.join(out, 'index.html'), 'w') as f:
        f.write(page)
    print(f'필드 {len(cells)}개, 몬스터 {len(mcells)}개 → {os.path.join(out, "index.html")}')


# --- 덤프와 비교 ----------------------------------------------------------

def check_field(prg, d):
    """$6E5E(맵 인물 그림 칸 0~F → $7200 칸 4~13)와 일행 칸 0~3 의 표·CHR, 화면 OAM 2×2 묶음의 픽셀을 비교."""
    s = open(os.path.join(d, 'end.sram'), 'rb').read()
    chr_ = open(os.path.join(d, 'end.chr'), 'rb').read()
    oam = open(os.path.join(d, 'end.oam'), 'rb').read()
    ram = open(os.path.join(d, 'end.ram'), 'rb').read()
    slots = {}
    if ram[0x28] == 0:   # 필드: 칸 4~ 는 1E:$9799 의 탈것 그림($6E5E 는 앞 맵 값이 남음)
        for i in range(VEHICLES[2]):
            slots[i + 4] = rd(prg, VEHICLES[0], VEHICLES[1] + i)
    else:
        for i, n in enumerate(s[0xE5E:0xE6E]):
            if n != 0xFF:
                slots[i + 4] = n
    bad = 0
    for sl in range(4):
        got = s[0x1200 + sl * 64:0x1240 + sl * 64]
        hits = [m for m in range(FIELD_COUNT) if field_load(prg, m, got[0])[0] == got]
        if hits:
            slots[sl] = hits[0]
    tiles_ok = tiles_n = 0
    for sl, n in sorted(slots.items()):
        got = s[0x1200 + sl * 64:0x1240 + sl * 64]
        table, ch = field_load(prg, n, got[0])
        ok = table == got
        cb = sum(chr_[t * 16:t * 16 + 16] != v for t, v in ch.items())
        tiles_n += len(ch)
        tiles_ok += len(ch) - cb
        bad += (not ok) + (cb > 0)
        print(f'  칸 {sl:X} 그림 {n:02X}(표 {field_index(n)[0]:02X}) $7200 {"같음" if ok else "다름"},'
              f' CHR {len(ch) - cb}/{len(ch)}')
    # 화면: OAM 4개가 2×2 로 붙은 묶음마다 칸·블록을 찾아 픽셀 비교
    ents = [tuple(oam[4 * i:4 * i + 4]) for i in range(64)]
    groups, px_ok, px_n, dir_ok, dir_n = 0, 0, 0, 0, 0
    for i in range(0, 64, 4):
        e = ents[i:i + 4]
        if e[0][0] >= 0xEF:
            continue
        key = bytes(v for y, t, a, x in e for v in (t, a & 0xC3))
        found = [(sl, n, b) for sl, n in slots.items() for b in range(8)
                 if s[0x1200 + sl * 64 + b * 8:0x1208 + sl * 64 + b * 8] == key]
        if not found:
            continue
        sl, n, b = found[0]
        px, pal = field_frame(prg, n, b)
        groups += 1
        # 0F:$D869: 블록 = ($7000 아래 2비트) × 2 + ($0526 bit7). 그 칸을 쓰는 보이는 인물($6F60 < 80)이
        # 모두 같은 방향이면 견준다(칸 0 은 주인공 하나). 같은 그림의 블록이 여럿이면(물결처럼 방향이 없는 그림) 그중 하나면 된다
        # $7000 bit7 인 인물(걷는 중)이 있으면 OAM 을 만든 뒤 방향이 바뀔 수 있어 견주지 않는다
        who = [s[0x1000 + k] for k in range(32) if s[0xFE0 + k] == sl and s[0xF60 + k] < 0x80]
        ds = {v & 3 for v in who}
        if len(ds) == 1 and not any(v & 0x80 for v in who):
            dir_n += 1
            dir_ok += any(f[0] == sl and f[2] >> 1 in ds for f in found)
            if not any(f[0] == sl and f[2] >> 1 in ds for f in found):
                print(f'  방향 다름: 칸 {sl:X} 그림 {n:02X} 블록 {[f[2] for f in found]} $7000 아래 2비트 {sorted(ds)}')
        for k, (y, t, a, x) in enumerate(e):
            tp = flip(planes(chr_[t * 16:t * 16 + 16]), a & 0x40, a & 0x80)
            for yy in range(8):
                for xx in range(8):
                    px_n += 1
                    px_ok += tp[yy][xx] == px[(k >> 1) * 8 + yy][(k & 1) * 8 + xx]
    pal = [c & 0x3F for c in open(os.path.join(d, 'end.pal'), 'rb').read()]
    pal_ok = [pal[17 + 4 * i:20 + 4 * i] for i in range(4)] == obj_palettes(prg)
    print(f'  화면 OAM 묶음 {groups}개, 픽셀 {px_ok}/{px_n} 같음, 방향 {dir_ok}/{dir_n} 같음. CHR 타일 {tiles_ok}/{tiles_n},'
          f' OBJ 팔레트 {"같음" if pal_ok else "다름 " + bytes(pal[16:32]).hex(" ")}')
    return bad == 0 and px_ok == px_n and dir_ok == dir_n and pal_ok


def check_monster(prg, d):
    """무리 4칸 $6E45 의 몬스터마다, nametable·attribute·BG 팔레트·OBJ 로 그린 화면 픽셀(NES 색)을 디코더 그림과 비교.
    그림 자리는 화면에서 찾는다(가로 자리는 무리 수에 따라 달라짐). 같은 몬스터 여러 마리면 첫 마리."""
    sram = open(os.path.join(d, 'end.sram'), 'rb').read()
    nt = open(os.path.join(d, 'end.nt'), 'rb').read()
    chr_ = open(os.path.join(d, 'end.chr'), 'rb').read()
    pal = [c & 0x3F for c in open(os.path.join(d, 'end.pal'), 'rb').read()]
    oam = open(os.path.join(d, 'end.oam'), 'rb').read()
    screen = {}
    for r in range(30):
        for c in range(32):
            t = nt[r * 32 + c]
            a = nt[0x3C0 + (r // 4) * 8 + c // 4] >> ((r & 2) * 2 + (c & 2)) & 3
            tp = planes(chr_[0x1000 + t * 16:0x1010 + t * 16])
            for y in range(8):
                for x in range(8):
                    if tp[y][x]:
                        screen[(c * 8 + x, r * 8 + y)] = pal[a * 4 + tp[y][x]]
    for i in range(63, -1, -1):   # 낮은 번호가 위
        y, t, a, x = oam[4 * i:4 * i + 4]
        if y >= 0xEF:
            continue
        tp = flip(planes(chr_[t * 16:t * 16 + 16]), a & 0x40, a & 0x80)
        for yy in range(8):
            for xx in range(8):
                if tp[yy][xx]:
                    screen[(x + xx, y + 1 + yy)] = pal[16 + (a & 3) * 4 + tp[yy][xx]]
    ok = True
    names = monster_names(prg)
    for i in range(4):
        mid = sram[0xE45 + i]
        if mid == 0xFF or not sram[0xE49 + i]:
            continue
        px = mon_pixels(prg, mid)
        best = None
        for dy in range(0, 240, 8):
            for dx in range(0, 256, 8):
                hit = sum(screen.get((x + dx, y + dy)) == c for (x, y), c in px.items())
                if best is None or hit > best[0]:
                    best = (hit, dx, dy)
        hit, dx, dy = best
        # 그림 상자 안에서 디코더에 없는 화면 픽셀도 센다(창 테두리가 들어오면 늘어난다)
        x0, y0, x1, y1 = mon_box(px)
        extra = sum(1 for (x, y) in screen if x0 + dx <= x < x1 + dx and y0 + dy <= y < y1 + dy
                    and (x - dx, y - dy) not in px)
        good = hit == len(px) and dy == MON_ROW0_BIG.get(mon_pic(prg, mid), MON_ROW0) * 8
        ok &= good
        print(f'  몬스터 {mid:02X} {names[mid]} 그림 {mon_pic(prg, mid):02X}: 화면 ({dx},{dy}) 에서 픽셀 {hit}/{len(px)} 같음,'
              f' 상자 안 남는 화면 픽셀 {extra}')
    return ok


def check_rom(prg):
    """몬스터 데이터마다 다 읽은 끝이 같은 뱅크의 다음 데이터 시작과 같은지."""
    ends = {}
    for p in range(max(mon_pic(prg, m) for m in range(len(monster_names(prg)))) + 1):
        *_, b, start, end = mon_stream(prg, p)
        ends.setdefault((b, start), set()).add(end)
    ok = bad = 0
    for bank in sorted({b for b, _ in ends}):
        starts = sorted(a for b, a in ends if b == bank)
        for a, nxt in zip(starts, starts[1:]):
            if nxt in ends[(bank, a)]:
                ok += 1
            else:
                bad += 1
                print(f'  {bank:02X}:{a:04X} 끝 {" ".join(f"{e:04X}" for e in sorted(ends[(bank, a)]))}, 다음 시작 {nxt:04X}')
    print(f'몬스터 데이터 {len(ends)}가지, 경계 {ok + bad}곳 중 {ok}곳 맞음')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('cmd')
    ap.add_argument('args', nargs='*')
    ap.add_argument('--out', default='work/dq4-fcsprite')
    a = ap.parse_args()
    prg = ines.prg(open(a.rom, 'rb').read())
    if a.cmd == 'field':
        fd = os.path.join(a.out, 'field')
        os.makedirs(fd, exist_ok=True)
        for n in [int(x, 16) for x in a.args] or field_numbers(prg):
            write_field(prg, n, fd)
            print(open(os.path.join(fd, field_stem(n) + '.txt')).read() if a.args else f'{fd}/{field_stem(n)}.png',
                  end='' if a.args else '\n')
    elif a.cmd == 'monster':
        md = os.path.join(a.out, 'monster')
        os.makedirs(md, exist_ok=True)
        names = monster_names(prg)
        for mid in [int(x, 16) for x in a.args] or range(len(names)):
            write_monster(prg, mid, md, names)
            print(open(os.path.join(md, f'{mid:02X}.txt')).read() if a.args else f'{md}/{mid:02X}.png',
                  end='' if a.args else '\n')
    elif a.cmd == 'sheet':
        cmd_sheet(prg, a.out)
    elif a.cmd == 'check-rom':
        check_rom(prg)
    elif a.cmd == 'who':
        cmd_who(prg, int(a.args[0], 16))
    elif a.cmd in ('check-field', 'check-monster'):
        fn = check_field if a.cmd == 'check-field' else check_monster
        res = []
        for d in a.args:
            print(d)
            res.append(fn(prg, d))
        print(f'덤프 {len(res)}개 중 {sum(res)}개 모두 같음')
        sys.exit(0 if all(res) else 1)
    else:
        ap.error(f'모르는 명령 {a.cmd}')


if __name__ == '__main__':
    main()
