"""DQ4(FC) 필드 인물·탈것 스프라이트와 전투 몬스터 그림을 롬에서 뽑는다. 형식은 fc/dq4/docs/dq4-fcsprite-format.md.

사용:
  python fc/dq4/tools/dq4fcsprite.py rom/dq4.nes field [N ...]     필드 그림(그림 번호, 없으면 표 00~6B 와 쓰이는 돌려 그리기 전부)
                                                             → work/dq4-fcsprite/field/
  python fc/dq4/tools/dq4fcsprite.py rom/dq4.nes monster [ID ...]  몬스터 그림(몬스터 ID, 없으면 전부) → work/dq4-fcsprite/monster/
  python fc/dq4/tools/dq4fcsprite.py rom/dq4.nes sheet              위 둘을 모두 만들고 index.html·sheet-*.png 로 묶음
  python fc/dq4/tools/dq4fcsprite.py rom/dq4.nes assets OUT          비공개 에셋 저장소 규칙으로 OUT/sprites·monsters·gallery/sprites.html
  python fc/dq4/tools/dq4fcsprite.py rom/dq4.nes who N              그림 번호 N(인물 레코드 값, 16진)을 쓰는 맵·인물
  python fc/dq4/tools/dq4fcsprite.py rom/dq4.nes check-rom          몬스터 데이터 경계 검사(끝 = 다음 시작)
  python fc/dq4/tools/dq4fcsprite.py rom/dq4.nes check-field DIR...    seq.lua·warp.lua 덤프(end.sram/chr/oam)와 비교
  python fc/dq4/tools/dq4fcsprite.py rom/dq4.nes check-monster DIR...  lua/spritebattle.lua 덤프(end.sram/nt/chr/pal/oam)와 비교
  python fc/dq4/tools/dq4fcsprite.py rom/dq4.nes changes            이벤트가 칸 그림을 바꾸는 곳(BRK 0D 87)과 へんげのつえ 그림 표
  python fc/dq4/tools/dq4fcsprite.py rom/dq4.nes boss               デスピサロ 형태 0~7 → work/dq4-fcsprite/monster/AE-k.*
  python fc/dq4/tools/dq4fcsprite.py rom/dq4.nes check-boss DIR...   lua/spriteboss.lua 덤프(f0~f7.nt/chr/pal/oam)와 비교
  --out 폴더 로 출력 위치를 바꾼다(기본 work/dq4-fcsprite). 롬 그림이므로 work/ 밖에 두지 않는다.

필드 근거 루틴: 08:$85D3(BRK 04 87, 그림 하나 올리기), $859B(번호 → 표 번호), $80D5·$8132(레코드 → 타일 주소 4개),
$8254(같은 주소 다시 안 올림, $7700), $82B0(타일 번호·속성 → $7200+칸×64), $8981·$89C9(돌려 그리기), $83BD(CHR $0000 으로 복사).
OBJ 팔레트 08:$86F2(08:$8703 12바이트 → $0609). 일행 1E:$9648, 필드 탈것 1E:$9799.
몬스터 근거 루틴: 14:$812F(전투 그림 올리기), $9F0C(몬스터 ID → 그림 번호 14:$B2D5), $9FA9(그림 레코드 14:$A019, 5바이트),
$9F26(데이터 뱅크), $9712(타일 16바이트 풀기), $9783(BG·OBJ 패턴으로 올리기), $98F5(배치), $9557·$9593(팔레트).
デスピサロ 형태: 14:$A3F4($6E7E → $A40D 의 형태 루틴), 부품 $B100(CHR)·$AA43(BG)·$AC1A(OBJ)·$AE7C(지우기)·$AECD(옮기기).
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
SHEET_ROWS = (2, 3, 1, 0)        # 시트 행 순서: 남·서·동·북(sfc/dq4/docs/dq4-sprite-format.md 시트와 같은 순서)
B14 = 0x14
MON_PIC = 0xB2D5         # 14:$9F0C: 몬스터 ID → 그림 번호
MON_REC = 0xA019         # 14:$9FA9 의 워드 → 그림마다 5바이트(타일 수, 데이터 주소, 팔레트 주소)
MON_BANKBITS = 0xB398    # 14:$9F4A: 그림 번호 비트가 1 이면 뱅크 07, 0 이면 06
MON_BANK_SPECIAL = {0x14: 0x14, 0x2E: 0x14, 0x3F: 0x14, 0xB2: 0x14, 0xC0: 0x14, 0xB1: 0x10}
MON_ROW0 = 10            # 그림 BG 0행이 화면 nametable 10행(실측)
MON_ROW0_BIG = {0xAE: 8, 0xBC: 8}   # デスピサロ·エスターク 는 8행(실측)
BOSS = 0xAE              # デスピサロ 그림 번호(= 몬스터 ID)
BOSS_NOPOS = 0x6A        # 14:$96DD: 남은 타일 수가 이보다 작으면 자리 바이트 없음
BOSS_PLACED = 0x36       # 14:$9852: 처음 화면에 놓는 타일 수(뒤는 형태 부품)
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
    마스크 1 인 자리만 바이트가 있음(14:$9734). bit3 이 0 이면 16바이트 그대로.
    デスピサロ(그림 AE)는 남은 타일 수 $D1 이 6A 보다 작으면(타일 56~) 자리 바이트가 없다(14:$96D5 가 $29 를 켬)."""
    n, a, pa = mon_record(prg, p)
    b, start = mon_bank(prg, p), a
    tiles = []
    for i in range(n):
        a, pls, data = mon_tile(prg, b, a, p == BOSS and n - i < BOSS_NOPOS)
        tiles.append((pls, data))
    c = rd(prg, B14, pa)
    tri = [[rd(prg, B14, pa + 1 + 3 * i + j) for j in range(3)] for i in range((c >> 4) + (c & 15))]
    return tiles, tri[:c & 15], tri[c & 15:], b, start, a


def mon_tile(prg, b, a, nopos=False):
    """14:$9712: 타일 하나 → (다음 주소, 배치 목록, 16바이트). nopos($29 ≠ 0)면 머리 바이트 뒤에 자리 바이트가 없다."""
    pls = []
    while True:
        h = rd(prg, b, a)
        k = 0 if nopos else 1 if h & 0x40 else 2
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
    return a, pls, bytes(data)


def mon_pixels(prg, mid):
    """몬스터 그림의 픽셀: {(x, y): NES 색 번호}. 좌표는 그림 BG 0행·0열 기준(OBJ 는 화면에 그려지는 자리).
    BG 가 먼저, OBJ 가 위에 그린다(OBJ 우선순위 비트는 0). デスピサロ 는 형태 0 과 같다(boss_forms)."""
    p = mon_pic(prg, mid)
    tiles, opal, bpal, *_ = mon_stream(prg, p)
    row0 = MON_ROW0_BIG.get(p, MON_ROW0)
    bg, obj = {}, {}
    for i, (pls, data) in enumerate(tiles):
        if p == BOSS and i >= BOSS_PLACED:   # 뒤 타일은 CHR 에만 올리는 형태 부품(14:$9852)
            break
        px = planes(data)
        for h, pos in pls:
            t = flip(px, h & 2, h & 4)
            pals = bpal if h & 0x40 else opal
            pal = pals[h >> 4 & 3]
            if h & 0x40:
                ox, oy, dst = (pos[0] & 15) * 8, (pos[0] >> 4) * 8, bg
            else:
                # 화면 자리는 (x + 그림 왼쪽 열 × 8) & FF, (y + 4F) & FF 라 그림 기준으로는 부호 있는 바이트
                sx, sy = (v - 256 if v & 0x80 else v for v in pos)
                ox, oy, dst = sx, sy + MON_OBJ_Y + 1 - row0 * 8, obj
            for y in range(8):
                for x in range(8):
                    # OBJ 는 먼저 놓은 것(낮은 OAM 칸)이 위
                    if t[y][x] and not (dst is obj and (ox + x, oy + y) in obj):
                        dst[(ox + x, oy + y)] = pal[t[y][x] - 1]
    bg.update(obj)
    return bg


# --- デスピサロ 형태 -------------------------------------------------------
# 형태 번호 $6E7E(0~7)는 전투 시작 때 0(12:$8092)이고, 쓰러질 때마다 14:$A3F4 가 $A40D 의 루틴으로 다음 형태를 그린 뒤
# 11:$9202·$9228 이 하나 올린다. 형태 루틴은 아래 부품 함수를 부른다. BOSS_STEPS 는 형태 k → k+1 루틴이 부르는 순서를
# 전투에서 기록해 반복을 묶은 것(lua/spriteboss.lua CALLS)이고, 각 기호의 뜻·표는 롬에서 읽는다.
#   Bxx  14:$B100 CHR 부품 xx: 타일 $B169&0F 개(bit4 면 BG, 좌우 반전 짝으로 2장씩)를 07:$B1BA 워드에서 풀어
#        PPU (($B169&10 | $B25C&0F) << 8 | $B25C&F0) 로. xx ≥ 2 는 자리 바이트 없음. 마지막 부품 데이터는 $7600 에도 남는다
#   Nxx  14:$AA43 BG 부품: $AA66 개 칸(자리 $AB23 워드, 행 << 4 | 열)에 타일 $AAE4 + 2i(반전이면 +1), $AAE4 가 0 이면 0.
#        $AAA5 가 0 이 아닌 짝수면 그대로·좌우 대칭 두 번, 홀수면 대칭만(14:$AFEA)
#   Oxx  14:$AC1A OBJ 부품: OAM 칸 $AC66 부터 $AC99 개, 타일 $ACFF + i, 속성 $ACCC, 자리 $AD65 워드
#        ($AD32 가 0 이면 행 << 4 | 열, 아니면 y, x 바이트 쌍). 대칭은 BG 부품과 같은 규칙(14:$AFA8)
#   Wk/Rk 14:$AE7C/$AE80 지우기·드러내기: $AEC2/$AEB7 의 k 번째 타일 범위를 끝에 빈 타일 또는 $7600 의 그림으로
#   Mss.dd.n.a.cc 14:$AECD OAM 칸 cc 부터 옮기기: 단계 ss~ss+n-1 마다 칸 cc~$AF1D 의 좌표 a(0 y, 3 x)를 dd 씩, 끝 칸이 $AF2F 가 될 때까지
#   Hyy.nn 14:$9C1D OAM 칸 yy 부터 nn 개 숨김. Syy.tt 14:$A44B OAM 칸 yy 의 타일을 tt 로. Vk 14:$A9FD OAM 칸 8·9 를 $AA3B 의 k 번째 만큼
#   Z0/Z1 14:$A07C/$A080 OBJ 타일 0 을 빈 타일/색 1 로. Ck 14:$A609 BG 팔레트 1 의 색 2·3 = $A648 의 k 번째
#   P 14:$A546 팔레트 $A650 15바이트(BG 3, OBJ 0~3). Qcc 14:$A77D·$A882 OBJ 팔레트 0 색 1 = cc. K 14:$A5DA $A667 의 한 바이트 쓰기 8개
#   Accdd.rree.p 14:$A8BF 칸 열 cc~dd·행 rr~ee 의 BG 팔레트 p. T 14:$A42A 속성 $23D0~$23DF = 55, $23E0~$23E7 = 05
BOSS_STEPS = (
    'T B00 S1.EE S3.EF S5.F0 S7.F1 S9.F2 SB.F3 B00 Z0 O00 W0 N00 H0D.12',
    'B00 Z0 O01 W1 N01 H01.1E',
    'O02 Z0 O03 W2 N03 B01 N04 H00.14',
    'Z0 (H00.14 O05 H00.14 O04)*4 H00.14 O05 N05 (H00.14 O06 H00.14 O05)*4 H00.14 O06 N06 '
    '(H00.14 O07 H00.14 O06)*4 H00.14 O07 N07 (H00.14 O08 H00.14 O07)*6 H00.14 O08 N08 '
    '(H00.14 O09 H00.14 O08)*8 (H00.14 O09 H00.14 O0A)*21 N09 (H00.14 O0B H00.14 O0A)*36 H00.14 O0B N0A H00.10 '
    '(C0 C1 C2 C3)*3 C0 C1 C2 P B02 B03 B04 B05 B06 B07 B08 N0B N0C N0D N0E N0F N10 B09 B0A N11 N12 B0B B0C B0D N13 '
    'B0E O0C B0F O0C B10 O0C B0F B0E B0B B0C B0D B0E B0F B10 B0F B0E B0B B0C B0D B0E B0F B10 K',
    'B12 B13 B14 B15 B16 B17 B18 B19 B1A B1B O0D O0E O0F M00.FF.4.3.09 O13 Z1 O14 N14 N15 N16 N17 N18 N19 N1A N1B R3 '
    'H02.18 O10 O11 O12 M04.01.4.3.09 H02.07 O15 O16 Z1 N1C N1D N1E N1F N20 N21 N22 N23 R4 H09.18',
    'B1C B1D B1E O17 N24 B1F B20 B21 B22 B23 B24 B25 B26 B27 B28 O18 N25 B1C Z0 O19 W5 N26 Q26 O1A M08.FF.3.3.06 '
    'O1B O1C O1D O1E N27 N28 N29 N2A N2B N2C N2D N2E B1D Z1 R6 H06.10 O1F O20 B1E Z1 R7 O21 N2F B1C Z0 O22 W8 N30 O23 '
    'M0B.01.3.3.06 O24 O25 O26 O27 N31 N32 N33 N34 N35 N36 N37 N38 B1D Z1 R9 H06.10 O28 O29 B1E Z1 RA H16.02 Q30',
    'B29 B2A B2B B2C B2D B2E B2F B30 B31 B32 B33 B34 B35 O2A O2B A0E13.0A0D.3 B36 B37 B38 B39 O2C O2D O2E O2F '
    'M0E.FF.4.0.1E B3A N39 B3B B3C N3A N3B B3D B3E B3F B40 O30 N3C V0 B41 B42 B43 B44 V1 N3D V2 B45 B46 V3 B47 B48 B49 '
    'N3E B4A B4B B4C B4D B4E O31 O32 B4F B50',
)
BOSS_FORMS = len(BOSS_STEPS) + 1
BOSS_COL0 = 0x0A         # 14:$9C84: 한 마리일 때 그림 왼쪽 열
BOSS_PART_BANK = 0x07


def hflip_tile(d):
    return bytes(int(f'{v:08b}'[::-1], 2) for v in d)


def vflip_tile(d):
    return d[7::-1] + d[15:7:-1]


def boss_steps(k):
    """형태 k → k+1 루틴의 기호 목록(괄호 묶음 풀기)."""
    out, toks = [], BOSS_STEPS[k].replace('(', ' ( ').replace(')', ' ) ').split()
    i = 0
    while i < len(toks):
        if toks[i] == '(':
            j = toks.index(')', i)
            n = int(toks[j + 1][1:])
            out += toks[i + 1:j] * n
            i = j + 2
        elif '*' in toks[i]:
            t, n = toks[i].split('*')
            out += [t] * int(n)
            i += 1
        else:
            out.append(toks[i])
            i += 1
    return out


class BossScreen:
    """전투 화면 중 デスピサロ 가 쓰는 것만: CHR(0~FF OBJ, 100~1FF BG), nametable 칸, 속성(2×2 칸), OAM 64칸, 팔레트."""

    def __init__(self, prg):
        self.prg, self.chr, self.nt, self.attr, self.oam, self.pal = prg, {}, {}, {}, [None] * 64, {}
        self.buf = bytes(256)
        self.first_draw()

    def rd(self, a):
        return rd(self.prg, B14, a)

    def first_draw(self):
        """14:$969C·$9783·$9822 의 첫 그림. BG 타일은 반전 종류마다 $1000 + 8D 부터, OBJ 타일은 1 부터 처음 쓰는 차례로
        한 장씩. 화면에 놓는 것은 앞 BOSS_PLACED 타일. 팔레트는 BG 목록 i → BG 칸 1+i, OBJ 목록 i → OBJ 칸 (수−1−i)."""
        prg = self.prg
        tiles, opal, bpal, *_ = mon_stream(prg, BOSS)
        row0 = MON_ROW0_BIG[BOSS]
        for i, t in enumerate(opal):
            self.pal[('O', len(opal) - 1 - i)] = list(t)
        for i, t in enumerate(bpal):
            self.pal[('B', 1 + i)] = list(t)
        nb, no, slot = 0x8D, 1, 0
        for i, (pls, data) in enumerate(tiles):
            var, got = [data, hflip_tile(data), vflip_tile(data), hflip_tile(vflip_tile(data))], {}
            for h, pos in pls:
                if h & 0x40:
                    v = h >> 1 & 3
                    if v not in got:
                        got[v], self.chr[0x100 + nb], nb = nb, var[v], nb + 1
                    if pos and i < BOSS_PLACED:
                        r, c = row0 + (pos[0] >> 4), BOSS_COL0 + (pos[0] & 15)
                        self.nt[(r, c)] = got[v]
                        self.attr[(r // 2, c // 2)] = 1 + (h >> 4 & 3)
                else:
                    if 'O' not in got:
                        got['O'], self.chr[no], no = no, data, no + 1
                    if pos and i < BOSS_PLACED:
                        a = (len(opal) - 1 - (h >> 4 & 3)) | (0x40 if h & 2 else 0) | (0x80 if h & 4 else 0)
                        self.oam[slot] = [(pos[1] + MON_OBJ_Y) & 0xFF, got['O'], a, (pos[0] + BOSS_COL0 * 8) & 0xFF]
                        slot += 1

    def chr_part(self, x):
        v1, v2 = self.rd(0xB169 + x), self.rd(0xB25C + x)
        t = ((v1 & 0x10 | v2 & 0x0F) << 8 | v2 & 0xF0) // 16
        a, buf = wd(self.prg, B14, 0xB1BA + 2 * x), bytearray()
        for _ in range(v1 & 15):
            a, _, data = mon_tile(self.prg, BOSS_PART_BANK, a, x >= 2)
            for d in ([data, hflip_tile(data)] if v1 & 0x10 else [data]):
                self.chr[t], t = d, t + 1
                buf += d
        self.buf = bytes(buf)

    @staticmethod
    def mirror_runs(m):
        return [0, 1] if m and not m & 1 else [m]

    def bg_part(self, x):
        n, m, base = self.rd(0xAA66 + x), self.rd(0xAAA5 + x), self.rd(0xAAE4 + x)
        p = wd(self.prg, B14, 0xAB23 + 2 * x)
        for mm in self.mirror_runs(m):
            for i in range(n):
                v = self.rd(p + i)
                c = 13 - (v & 15) if mm else v & 15
                self.nt[((v >> 4) + 8, c + 10)] = (base + 2 * i + mm) & 0xFF if base else 0

    def obj_part(self, x):
        grid = self.rd(0xAD32 + x) == 0
        slot, n, at, base = self.rd(0xAC66 + x), self.rd(0xAC99 + x), self.rd(0xACCC + x), self.rd(0xACFF + x)
        p = wd(self.prg, B14, 0xAD65 + 2 * x)
        a0 = (at >> 4 | (at & 0x80) >> 2 | (at & 8) << 4) & 0xFF
        for mm in self.mirror_runs(at & 3):
            for i in range(n):
                if grid:
                    v = self.rd(p + i)
                    c = 13 - (v & 15) if mm else v & 15
                    y, xx = (v >> 4) * 8 + 0x3F, (c + 10) * 8
                else:
                    y, b = (self.rd(p + 2 * i) + 0x3F) & 0xFF, self.rd(p + 2 * i + 1)
                    xx = ((0x68 - b if mm else b) + 0x50) & 0xFF
                self.oam[slot & 63] = [y, (base + i) & 0xFF if base else 0, a0 | (0x40 if mm else 0), xx]
                slot += 1

    def wipe(self, k, reveal_mask):
        hi, cnt = self.rd(0xAEC2 + k), self.rd(0xAEB7 + k)
        t = ((hi & 15) << 8 | hi & 0xF0) // 16
        show = reveal_mask == bool(cnt & 0x80)   # 끝 마스크(AE7C FF, AE80 00)를 $AEB7 bit7 이 0 이면 뒤집어 씀(14:$B0B9)
        for i in range(cnt & 15):
            self.chr[t + i] = self.buf[16 * i:16 * i + 16] if show else bytes(16)

    def move(self, st, d, n, axis, s0):
        for k in range(n):
            end, tgt = self.rd(0xAF1D + st + k), self.rd(0xAF2F + st + k)
            while True:
                for y in range(s0, end):
                    self.oam[y][axis] = (self.oam[y][axis] + d) & 0xFF
                if self.oam[end - 1][axis] == tgt:
                    break

    def step(self, op):
        c, arg = op[0], op[1:]
        h = [int(v, 16) for v in arg.split('.')] if arg else []
        if c == 'B':
            self.chr_part(h[0])
        elif c == 'N':
            self.bg_part(h[0])
        elif c == 'O':
            self.obj_part(h[0])
        elif c in 'WR':
            self.wipe(h[0], c == 'W')
        elif c == 'M':
            self.move(*h)
        elif c == 'H':
            for i in range(h[1]):
                self.oam[(h[0] + i) & 63] = [0xF7] * 4
        elif c == 'S':
            self.oam[h[0]][1] = h[1]
        elif c == 'V':
            dy, dx = self.rd(0xAA3B + 2 * h[0]), self.rd(0xAA3C + 2 * h[0])
            for y, sx in ((8, -dx), (9, dx)):
                self.oam[y][0] = (self.oam[y][0] - dy) & 0xFF
                self.oam[y][3] = (self.oam[y][3] + sx) & 0xFF
        elif c == 'Z':
            self.chr[0] = bytes([0xFF] * 8 + [0] * 8) if h[0] else bytes(16)
        elif c == 'C':
            self.pal[('B', 1)][1:] = [self.rd(0xA648 + 2 * h[0]), self.rd(0xA649 + 2 * h[0])]
        elif c == 'P':
            v = [self.rd(0xA650 + i) for i in range(15)]
            self.pal[('B', 3)] = v[:3]
            for i in range(4):
                self.pal[('O', i)] = v[3 + 3 * i:6 + 3 * i]
        elif c == 'Q':
            self.pal[('O', 0)][0] = h[0]
        elif c == 'K':
            for i in range(8):
                hi, lo, v = (self.rd(0xA667 + 3 * i + j) for j in range(3))
                t = bytearray(self.chr.get((hi << 8 | lo) // 16, bytes(16)))
                t[lo & 15] = v
                self.chr[(hi << 8 | lo) // 16] = bytes(t)
        elif c == 'A':
            for r in range(h[1] >> 8, (h[1] & 0xFF) + 1):
                for cc in range(h[0] >> 8, (h[0] & 0xFF) + 1):
                    self.attr[(r // 2, cc // 2)] = h[2]
        elif c == 'T':
            for qr in range(4, 10):   # $23D0~$23E7 = nametable 행 8~19. 05 는 행 16·17 만 팔레트 1
                for qc in range(16):
                    self.attr[(qr, qc)] = 1 if qr < 9 else 0
        else:
            raise ValueError(op)

    def pixels(self):
        """{(x, y): NES 색}. 화면 좌표. BG(행 8~17) 위에 OAM 을 낮은 칸이 위로, 속성 bit5 는 BG 뒤."""
        out, bgpx = {}, set()
        for (r, c), t in self.nt.items():
            d = self.chr.get(0x100 + t)
            if d is None or not 8 <= r < 18:
                continue
            pal = self.pal[('B', self.attr.get((r // 2, c // 2), 1))]
            for y, row in enumerate(planes(d)):
                for x, v in enumerate(row):
                    if v:
                        out[(c * 8 + x, r * 8 + y)] = pal[v - 1]
                        bgpx.add((c * 8 + x, r * 8 + y))
        for e in reversed(self.oam):
            if e is None or e[0] >= 0xEF:
                continue
            y, t, a, x = e
            pal = self.pal[('O', a & 3)]
            for yy, row in enumerate(flip(planes(self.chr[t]), a & 0x40, a & 0x80)):
                for xx, v in enumerate(row):
                    q = (x + xx, y + 1 + yy)
                    if v and x + xx < 256 and not (a & 0x20 and q in bgpx):
                        out[q] = pal[v - 1]
        return out


def boss_forms(prg):
    """형태 0~7 의 화면 픽셀 {(x, y): NES 색} 목록."""
    sc, out = BossScreen(prg), []
    out.append(sc.pixels())
    for k in range(len(BOSS_STEPS)):
        for op in boss_steps(k):
            sc.step(op)
        out.append(sc.pixels())
    return out


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


def boss_images(prg):
    """형태마다 (색 번호 행렬, 색 목록)과 모든 형태를 담는 공통 상자(그림 BG 0행·0열 기준 x0, y0, x1, y1)."""
    ox, oy = BOSS_COL0 * 8, MON_ROW0_BIG[BOSS] * 8
    fs = [{(x - ox, y - oy): c for (x, y), c in f.items()} for f in boss_forms(prg)]
    boxes = [mon_box(f) for f in fs]
    box = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))
    return box, [indexed(f, box[2] - box[0], box[3] - box[1], box[0], box[1]) for f in fs]


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


def write_boss(prg, folder, names):
    """デスピサロ 형태 0~7 을 같은 상자로 folder/AE-k.png·-x8.png·.txt 에."""
    (x0, y0, x1, y1), ims = boss_images(prg)
    for k, (grid, colors) in enumerate(ims):
        stem = os.path.join(folder, f'{BOSS:02X}-{k}')
        save_png(stem + '.png', grid, colors)
        save_png(stem + '-x8.png', grid, colors, 8)
        head = [f'# 몬스터 {BOSS:02X} {names[BOSS]} 형태 {k}($6E7E = {k}). 형태 {k - 1} → {k} 루틴: {BOSS_STEPS[k - 1]}'
                if k else f'# 몬스터 {BOSS:02X} {names[BOSS]} 형태 0(첫 그림)',
                f'# {x1 - x0}×{y1 - y0}, 왼위 = 그림 BG 0행 기준 ({x0},{y0}). 색 번호 = NES 색 ' +
                ' '.join(f'{B36[i + 1]}={c:02X}' for i, c in enumerate(colors))]
        with open(stem + '.txt', 'w') as f:
            f.write('\n'.join(head) + '\n' + matrix_text(grid) + '\n')
    return ims


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


# --- 이벤트가 바꾸는 그림 ------------------------------------------------------

DISGUISE = (0x1E, 0xB079, 0x25, 0x10)   # 1E:$B02F: へんげのつえ 그림 표. 앞 25개 또는 뒤 10개 중 난수로 → $6297


def event_changes(prg):
    """BRK 0D 87(08:$8668: 칸 X 에 표 A 를 번호 바꿈 없이 올림)을 부르는 곳마다 (뱅크, 주소, X, A). 바로 앞 두 명령이
    LDX #·LDA # 가 아니면 None(레지스터 값은 코드가 계산)."""
    out = []
    for b in range(len(prg) // 0x4000):
        base = 0xC000 if b in (0x0F, 0x1F) else 0x8000
        seg = prg[b * 0x4000:(b + 1) * 0x4000]
        for o in range(4, 0x4000 - 2):
            if seg[o:o + 3] != bytes([0x00, 0x0D, 0x87]):
                continue
            x = a = None
            for k in (2, 4):   # LDA #a / LDX #x 두 개가 어느 순서로든 바로 앞
                op, v = seg[o - k], seg[o - k + 1]
                if op == 0xA9 and a is None:
                    a = v
                elif op == 0xA2 and x is None:
                    x = v
                else:
                    break
            out.append((b, base + o, x, a))
    return out


def cmd_changes(prg):
    for b, a, x, t in event_changes(prg):
        xs = '?' if x is None else f'{x:X}'
        ts = '?' if t is None else f'{t:02X}' + (' 돌려 그리기' if t & 0x80 else '')
        lab = '' if t is None else field_label(prg, raw_number(t & 0x7F))
        print(f'{b:02X}:{a:04X} 칸 {xs} 표 {ts} {lab}'.rstrip())
    bank, addr, n1, n2 = DISGUISE
    v = [rd(prg, bank, addr + i) for i in range(n1 + n2)]
    print(f'へんげのつえ {bank:02X}:${addr:04X} 앞 {n1}개: ' + ' '.join(f'{t:02X}' for t in v[:n1]))
    print(f'  뒤 {n2}개(bit7 이 켜진 채 $6297 에): ' + ' '.join(f'{t:02X}' for t in v[n1:]))


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
    write_boss(prg, md, names)
    for k in range(BOSS_FORMS):
        mcells.append((f'monster/{BOSS:02X}-{k}', f'{BOSS:02X} {names[BOSS]} 형태 {k}', f'$6E7E = {k}', ''))

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


# --- 에셋 저장소용 --------------------------------------------------------

ASSET_ROWS = ('아래', '왼쪽', '오른쪽', '위')    # SHEET_ROWS 순서(남·서·동·북)


def asset_sprite_name(n):
    m, rot = field_index(n)
    if rot:
        return f'{m:02X}-{n:02X}'
    return f'{m:02X}-{dq4data.PARTY[m]}' if m < 8 else f'{m:02X}'


def cmd_assets(prg, rom, out):
    """비공개 에셋 저장소의 규칙(1배 PNG, `<번호>[-<번호2>][-<이름>].png`, 폴더마다 index.json·SOURCE.txt)으로
    out/sprites, out/monsters, out/gallery/sprites.html 을 쓴다."""
    import hashlib
    import json
    import subprocess
    sd, md, gd = (os.path.join(out, x) for x in ('sprites', 'monsters', 'gallery'))
    for x in (sd, md, gd):
        os.makedirs(x, exist_ok=True)
    try:
        commit = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True,
                                cwd=os.path.dirname(os.path.abspath(__file__))).stdout.strip()
    except OSError:
        commit = ''
    sha = hashlib.sha1(rom).hexdigest()

    def source(folder):
        with open(os.path.join(folder, 'SOURCE.txt'), 'w') as f:
            f.write(f'sfc-dq4 커밋: {commit}\n명령: uv run --locked python fc/dq4/tools/dq4fcsprite.py rom/dq4.nes assets $OUT\n'
                    f'롬: FC 「ドラゴンクエストIV」 일본판 Rev A, SHA-1 {sha}\n')
    use = {}
    for num, place, *_ in users(prg):
        use.setdefault(field_index(num), []).append(place)
    base = wd(prg, B08, FIELD_TABLE)
    sprites = []
    for n in field_numbers(prg):
        m, rot = field_index(n)
        grid, colors = indexed(field_sheet(prg, n), 32, 64)
        name = asset_sprite_name(n)
        save_png(os.path.join(sd, name + '.png'), grid, colors)
        frames = []
        for d in SHEET_ROWS:
            for col in range(2):
                px, pal = field_frame(prg, n, d * 2 + col)
                frames.append({'row': ASSET_ROWS[SHEET_ROWS.index(d)], 'step': col, 'block': d * 2 + col,
                               'obj_palette': pal, 'matrix': matrix_text(px).split('\n')})
        places = list(dict.fromkeys(use.get((m, rot), [])))
        sprites.append({'file': name + '.png', 'table': m, 'number': n, 'rotated': rot, 'label': field_label(prg, n),
                        'size': [32, 64], 'frame': [16, 16], 'rows': list(ASSET_ROWS), 'cols': ['걸음 0', '걸음 1'],
                        'rom': f'08:${base + 24 * m:04X}', 'colors': [f'{c:02X}' for c in colors],
                        'records': len(use.get((m, rot), [])), 'places': places, 'frames': frames})
    with open(os.path.join(sd, 'index.json'), 'w') as f:
        json.dump({'note': '그림 PNG 는 32×64: 행 아래·왼쪽·오른쪽·위, 열 걸음 0·1. 색 번호 0 투명, colors 는 색 번호 1~ 의 NES 색. '
                   'matrix 는 블록마다 OBJ 팔레트 안 색 번호(. 투명)', 'obj_palettes': [[f'{c:02X}' for c in t] for t in obj_palettes(prg)],
                   'sprites': sprites}, f, ensure_ascii=False, indent=1)
    source(sd)
    names = monster_names(prg)
    mons = []
    for mid, nm in enumerate(names):
        px = mon_pixels(prg, mid)
        x0, y0, x1, y1 = mon_box(px)
        grid, colors = indexed(px, x1 - x0, y1 - y0, x0, y0)
        p = mon_pic(prg, mid)
        short = nm.replace(chr(0x3000), '')
        fname = f'{mid:02X}-{short}.png'
        save_png(os.path.join(md, fname), grid, colors)
        tiles, opal, bpal, b, start, _ = mon_stream(prg, p)
        e = {'file': fname, 'id': mid, 'name': nm, 'picture': p, 'data': f'{b:02X}:${start:04X}',
             'record': f'14:${wd(prg, B14, MON_REC) + 5 * p:04X}', 'tiles': len(tiles), 'size': [x1 - x0, y1 - y0],
             'origin': [x0, y0], 'colors': [f'{c:02X}' for c in colors],
             'bg_palettes': [[f'{c:02X}' for c in t] for t in bpal], 'obj_palettes': [[f'{c:02X}' for c in t] for t in opal],
             'matrix': matrix_text(grid).split('\n')}
        if p == BOSS:
            (bx0, by0, bx1, by1), ims = boss_images(prg)
            e['forms'] = []
            for k, (g, cs) in enumerate(ims):
                ff = f'{mid:02X}-{k}-{short}.png'
                save_png(os.path.join(md, ff), g, cs)
                e['forms'].append({'file': ff, 'form': k, 'size': [bx1 - bx0, by1 - by0], 'origin': [bx0, by0],
                                   'colors': [f'{c:02X}' for c in cs], 'steps': BOSS_STEPS[k - 1] if k else '',
                                   'matrix': matrix_text(g).split('\n')})
            e['note'] = ('form 은 형태 번호 $6E7E. 형태마다 같은 상자로 자른 화면 그림(BG + OBJ). steps 는 앞 형태에서 이 형태로 바꾸는 '
                         '루틴의 부품 호출(기호는 sfc-dq4 fc/dq4/docs/dq4-fcsprite-format.md). file 은 형태 0 과 같은 첫 그림')
        mons.append(e)
    with open(os.path.join(md, 'index.json'), 'w') as f:
        json.dump({'note': 'origin 은 그림 BG 0행·0열 기준 왼위 자리. 색 번호 0 투명(전투 화면에서는 검정 바탕), colors 는 색 번호 1~ 의 NES 색. '
                   'matrix 문자는 색 번호(0-9A-Z, . 투명)', 'monsters': mons}, f, ensure_ascii=False, indent=1)
    source(md)
    cards = []
    for e in sprites:
        cards.append(('../sprites/' + e['file'], e['file'][:-4], (e['label'] + ' · ' if e['label'] else '') +
                      f'인물 {e["records"]} · 맵 {len(e["places"])}곳', 'spr'))
    for e in mons:
        cards.append(('../monsters/' + e['file'], f'{e["id"]:02X} {e["name"]}',
                      f'그림 {e["picture"]:02X} · {e["size"][0]}×{e["size"][1]}', 'mon'))
        for fm in e.get('forms', []):
            cards.append(('../monsters/' + fm['file'], f'{e["id"]:02X} {e["name"]} 형태 {fm["form"]}',
                          f'$6E7E = {fm["form"]} · {fm["size"][0]}×{fm["size"][1]}', 'mon'))

    def grid_html(kind):
        return '\n'.join(f'<div class="card {kind}"><a href="{html.escape(src)}"><img src="{html.escape(src)}" loading="lazy" '
                         f'alt="{html.escape(t)}"></a><div class="t">{html.escape(t)}</div><div class="s">{html.escape(sub)}</div></div>'
                         for src, t, sub, k in cards if k == kind)
    page = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DQ4 FC 스프라이트</title><style>
:root {{ color-scheme: light dark; --bg: #f6f6f4; --fg: #1d1d1b; --mut: #6b6b66; --card: #ffffff; --line: #ddd; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg: #161615; --fg: #e8e8e4; --mut: #9a9a94; --card: #22221f; --line: #3a3a36; }} }}
body {{ margin: 0; padding: 16px; background: var(--bg); color: var(--fg); font: 14px/1.5 system-ui, sans-serif; }}
h1 {{ font-size: 20px; }} h2 {{ font-size: 17px; margin-top: 28px; border-bottom: 1px solid var(--line); }}
nav a {{ margin-right: 12px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 10px; }}
.card {{ background: var(--card); border: 1px solid var(--line); border-radius: 6px; padding: 6px; }}
.card img {{ width: 100%; height: 180px; object-fit: contain; image-rendering: pixelated; background: #3a3a36; }}
.mon img {{ background: #000; height: 140px; }}
.card .t {{ font-weight: 600; word-break: break-all; }} .card .s {{ color: var(--mut); font-size: 12px; }}
</style></head><body>
<h1>DQ4(FC) 원작 스프라이트·몬스터</h1>
<nav><a href="index.html">← 그래픽 갤러리</a><a href="#sprites">필드 스프라이트 {len(sprites)}</a><a href="#monsters">몬스터 {len(mons)}</a></nav>
<p>필드 스프라이트는 32×64(행 아래·왼쪽·오른쪽·위, 열 걸음 0·1, 16×16 씩). 이름의 두 번째 번호는 돌려 그리기 그림 번호입니다.
몬스터는 그림 크기 그대로, 검정 바탕이 게임 화면의 색 0 입니다. 메타데이터는 각 폴더의 index.json.</p>
<h2 id="sprites">필드 스프라이트</h2><div class="grid">
{grid_html('spr')}
</div>
<h2 id="monsters">몬스터</h2><div class="grid">
{grid_html('mon')}
</div></body></html>
"""
    with open(os.path.join(gd, 'sprites.html'), 'w') as f:
        f.write(page)
    print(f'스프라이트 {len(sprites)}개 → {sd}, 몬스터 {len(mons)}개 → {md}, 갤러리 {os.path.join(gd, "sprites.html")}')



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
        # 여자 勇者(표 08)는 표 00 과 배치가 같고 CHR 만 다르다: CHR 까지 맞는 표를 고른다
        hits.sort(key=lambda m: -sum(chr_[t * 16:t * 16 + 16] == v for t, v in field_load(prg, m, got[0])[1].items()))
        if hits:
            slots[sl] = hits[0]
    tiles_ok = tiles_n = 0
    for sl, n in sorted(slots.items()):
        got = s[0x1200 + sl * 64:0x1240 + sl * 64]
        table, ch = field_load(prg, n, got[0])
        ok = table == got
        if not ok and sl >= 4:
            # 이벤트가 BRK 0D 87 로 칸 그림을 바꾸면 $6E5E 는 그대로다: 같은 64바이트를 만드는 표를 찾는다
            alt = [m for m in range(FIELD_COUNT) if field_load(prg, raw_number(m), got[0])[0] == got]
            alt.sort(key=lambda m: -sum(chr_[t * 16:t * 16 + 16] == v
                                        for t, v in field_load(prg, raw_number(m), got[0])[1].items()))
            if alt:
                print(f'  칸 {sl:X} 는 $6E5E 의 그림 {n:02X} 이 아니라 표 {alt[0]:02X} 로 바뀌어 있음')
                n = slots[sl] = raw_number(alt[0])
                table, ch = field_load(prg, n, got[0])
                ok = True
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


def check_boss(prg, d):
    """lua/spriteboss.lua 덤프 f0~f7(형태 0~7)의 화면 행 8~17 BG 와 OAM 을 그려 boss_forms 와 픽셀 비교.
    OAM 은 낮은 칸이 위, 속성 bit5 는 BG 뒤."""
    ok = True
    for k, want in enumerate(boss_forms(prg)):
        f = os.path.join(d, f'f{k}')
        if not os.path.exists(f + '.nt'):
            print(f'  형태 {k}: 덤프 없음')
            ok = False
            continue
        nt, chr_ = open(f + '.nt', 'rb').read(), open(f + '.chr', 'rb').read()
        oam = open(f + '.oam', 'rb').read()
        pal = [c & 0x3F for c in open(f + '.pal', 'rb').read()]
        got, bgpx = {}, set()
        for r in range(8, 18):
            for c in range(32):
                t = nt[r * 32 + c]
                a = nt[0x3C0 + (r // 4) * 8 + c // 4] >> ((r & 2) * 2 + (c & 2)) & 3
                for y, row in enumerate(planes(chr_[0x1000 + t * 16:0x1010 + t * 16])):
                    for x, v in enumerate(row):
                        if v:
                            got[(c * 8 + x, r * 8 + y)] = pal[a * 4 + v]
                            bgpx.add((c * 8 + x, r * 8 + y))
        for j in range(63, -1, -1):
            y, t, a, x = oam[4 * j:4 * j + 4]
            if y >= 0xEF:
                continue
            for yy, row in enumerate(flip(planes(chr_[t * 16:t * 16 + 16]), a & 0x40, a & 0x80)):
                for xx, v in enumerate(row):
                    q = (x + xx, y + 1 + yy)
                    if v and x + xx < 256 and not (a & 0x20 and q in bgpx):
                        got[q] = pal[16 + (a & 3) * 4 + v]
        keys = set(got) | set(want)
        same = sum(got.get(q) == want.get(q) for q in keys)
        ok &= same == len(keys)
        print(f'  형태 {k}: 픽셀 {same}/{len(keys)} 같음(화면 {len(got)}, 디코더 {len(want)})')
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
    elif a.cmd == 'assets':
        cmd_assets(prg, open(a.rom, 'rb').read(), a.args[0])
    elif a.cmd == 'sheet':
        cmd_sheet(prg, a.out)
    elif a.cmd == 'check-rom':
        check_rom(prg)
    elif a.cmd == 'boss':
        md = os.path.join(a.out, 'monster')
        os.makedirs(md, exist_ok=True)
        write_boss(prg, md, monster_names(prg))
        for k in range(BOSS_FORMS):
            print(f'{md}/{BOSS:02X}-{k}.png')
    elif a.cmd == 'changes':
        cmd_changes(prg)
    elif a.cmd == 'who':
        cmd_who(prg, int(a.args[0], 16))
    elif a.cmd in ('check-field', 'check-monster', 'check-boss'):
        fn = {'check-field': check_field, 'check-monster': check_monster, 'check-boss': check_boss}[a.cmd]
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
