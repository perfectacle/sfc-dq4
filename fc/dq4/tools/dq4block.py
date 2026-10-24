"""DQ4(FC) 맵 블록 → 8×8 타일 4개·팔레트·통행. 형식은 fc/dq4/docs/dq4-block-format.md.

사용:
  python fc/dq4/tools/dq4block.py rom/dq4.nes defs T              맵 종류 T($0028)의 블록 정의·애니메이션·낮 팔레트
  python fc/dq4/tools/dq4block.py rom/dq4.nes G K [--png]         맵의 통행 지도(텍스트). --png 는 work/ 에 렌더링
  python fc/dq4/tools/dq4block.py rom/dq4.nes G K --nt            맵 전체의 nametable 타일 번호 배열
  python fc/dq4/tools/dq4block.py rom/dq4.nes field [F] [--png]   필드 F(기본 0)의 통행 지도
  python fc/dq4/tools/dq4block.py rom/dq4.nes props [--maps]      롬 전체 맵·필드의 속성 값별 뜻·맵 수·칸 수(--maps 는 맵마다)
  python fc/dq4/tools/dq4block.py rom/dq4.nes compare DIR [PREFIX] seq.lua 의 end.* (또는 blockload.lua 의 PREFIX.*) 덤프와 비교
  python fc/dq4/tools/dq4block.py rom/dq4.nes effects G K          맵에서 지형 효과가 있는 칸(떨어지면 가는 곳 포함)
  python fc/dq4/tools/dq4block.py rom/dq4.nes tables               떨어지는 칸·리프트·タンス/つぼ·팻말 표와 속성 값의 뜻
  python fc/dq4/tools/dq4block.py rom/dq4.nes links [G K]          계단·旅の扉 등 출구 칸마다 목적지(08:$B22E)
  python fc/dq4/tools/dq4block.py rom/dq4.nes json [OUT]           맵·필드 전부의 속성·칸·표를 JSON 으로(기본 work/dq4block.json)


근거 루틴: 08:$84E9(블록 표 올리기), $8055(맵 종류 → 블록 표), $8473(블록 하나), $80D5(타일 모양 레코드),
$823D(CHR 타일 번호 나누기, $7700 중복 목록), $83BD·0F:$C7E1(CHR 뱅크 0C·0D 에서 16바이트 복사),
$853E(블록 20·21), $8710(빈 칸에 FC~FF), 1E:$A046(맵에 쓰인 블록 표시), 1E:$9F47(벽 아래 그늘 블록 바꾸기),
0F:$D4E6(다른 구역은 블록 20·21 로), $D44C(맵 밖 블록), $EB23(블록 → 타일 4개), 0F:$D088(통행).
지형 효과: 0F:$CEB1(걸음 뒤 분기), $CA77(밀리는 바닥), $E9E4(느린 칸), 1E:$9ACA(바닥 피해), 1E:$8676·12:$B6DD(떨어지기),
1E:$8700·$894A(리프트), 1E:$B2A6·$B36E·$B3B7(「とびら」와 열쇠), 1E:$80D8(카운터 너머 「はなす」),
1E:$BB10·$BC7A·$BB52(タンス·つぼ·팻말), 08:$B22E·$B246·$B554(출구 칸 순번으로 목적지), 08:$8796(연 문 블록),
1E:$8A0D·$8A48(리프트 사각형 구역).
"""
import os
import sys

from kr_patch.fc import ines

import dq4chest
import dq4field
import dq4map

B08 = 0x08


def rd(prg, bank, addr):
    return prg[bank * 0x4000 + (addr & 0x3FFF)]


def wd(prg, bank, addr):
    return rd(prg, bank, addr) | rd(prg, bank, addr + 1) << 8


BLOCKS = wd  # 08:$80B3 → 맵 종류마다 64바이트(블록 32개 × 2바이트)
EXTRA_SEL, EXTRA = 0x8AA2, 0x8AAF   # 08:$853E 블록 20·21
OUTSIDE_ALT = 0x8A92                # 08:$8A85: 맵 종류 0E 미만의 무늬 바깥 블록 → $0582
SPARE = (0x18, 0x11)                # 08:$8710: 빈 블록 칸에 넣는 정의(타일 FC~FF)
TILE0 = 0x8D                        # 08:$84FF: 블록 타일은 BG 패턴 $1000 + 번호 × 16 의 8D 부터


def block_entry(prg, t, b):
    return wd(prg, B08, 0x80B3) + t * 64 + 2 * b


def shape(prg, a, b):
    """08:$80D5($09=0): 블록 2바이트(a, b) → (CHR 뱅크, 타일 주소 4개, 속성 바이트 $6F40).
    a bit2-0·b 가 모양 레코드(08:$A80D, 3바이트) 번호. 레코드: 타일 번호 하위, bit7-4 모양·bit2 뱅크·bit1-0 번호 상위, 속성."""
    idx = (a & 7) << 8 | b
    r = wd(prg, B08, 0x8235) + 3 * idx
    r0, r1, prop = rd(prg, B08, r), rd(prg, B08, r + 1), rd(prg, B08, r + 2)
    form, hb = r1 >> 4, (r1 >> 2) & 1
    chr_ = (r1 & 3) << 8 | r0
    if form in (0x0E, 0x0F):            # $81C6: 타일 주소 4개를 표(08:$A28D)에서 그대로
        p = wd(prg, B08, 0x8225) + (chr_ * 8 & 0xFFFF)
        return 0x0C + hb, [wd(prg, B08, p + 2 * i) for i in range(4)], prop
    base = (wd(prg, B08, 0x8229 + 2 * hb) + (chr_ << 4)) & 0xFFFF
    d = wd(prg, B08, 0x8237) + form * 3  # 앞 타일에서 몇 타일 떨어졌는지(부호 있는 바이트) 3개
    addrs = [base]
    for i in range(3):
        v = rd(prg, B08, d + i)
        base = (base + ((v - 256 if v & 0x80 else v) << 4)) & 0xFFFF
        addrs.append(base)
    return 0x0C + hb, addrs, prop


def swap(a, b, chapter=0, flag=0):
    """08:$808E: $615A(장)이 1 이 아니면 블록 정의 00 17 을 00 12 로 바꾼다. 2 일 때는 $6286 bit4 가 켜져 있어야 바꾼다."""
    if (a, b) == (0x00, 0x17) and chapter != 1 and (chapter != 2 or flag & 0x10):
        return 0x00, 0x12
    return a, b


def defs(prg, t, chapter=0, flag=0):
    """맵 종류 t 의 블록 0~1F 와 20·21. 블록마다 dict(a, b, 뱅크, 주소, 팔레트, 종류 $6F20, 속성 $6F40).
    chapter·flag 는 $615A·$6286(swap 참고)."""
    out = {}
    for blk in range(0x20):
        e = block_entry(prg, t, blk)
        out[blk] = entry(prg, *swap(rd(prg, B08, e), rd(prg, B08, e + 1), chapter, flag))
    if t:
        for i, (a, b) in enumerate(extra_pairs(prg, t)):
            out[0x20 + i] = entry(prg, a, b)
    return out


def entry(prg, a, b):
    if a & 7 == 7:
        return None
    bank, addrs, prop = shape(prg, a, b)
    return {'a': a, 'b': b, 'bank': bank, 'addrs': addrs, 'pal': a >> 3 & 3, 'kind': a >> 5, 'prop': prop}


def extra_pairs(prg, t):
    """08:$853E: 맵 종류 t 로 8AA2 표의 2비트를 골라 블록 20·21 의 2바이트 정의 두 쌍."""
    sel = rd(prg, B08, EXTRA_SEL + (t >> 2)) >> (2 * ((t & 3) ^ 3)) & 3
    p = EXTRA + sel * 4
    return [(rd(prg, B08, p), rd(prg, B08, p + 1)), (rd(prg, B08, p + 2), rd(prg, B08, p + 3))]


def used_blocks(buf, outside):
    """1E:$A046: 맵에 쓰인 블록(아래 5비트)과 바깥 블록 $0520."""
    return {v & 0x1F for v in buf} | {outside & 0x1F}


PATCH_G, PATCH_K, PATCH_B, PATCH_V = 0x8A6C, 0x8A73, 0x8A79, 0x8A7F


def patch_props(prg, prop, g=None, k=None, field=0):
    """08:$8A2A: 블록 표를 올린 뒤 속성($6F40)을 몇 군데 고친다.
    필드는 $65 가 3 일 때만 블록 01 을 80, 블록 14 를 00 으로($8A34). 맵은 (그룹, 순번) 목록에 맞는 블록을 정해진 값으로($8A43)."""
    if g is None:
        if field == 3:
            prop[0x01], prop[0x14] = 0x80, 0x00
        return
    i = 0
    while not (e := rd(prg, B08, PATCH_G + i)) & 0x80:
        if g in (e, e | 0x80) and rd(prg, B08, PATCH_K + i) == k:
            prop[rd(prg, B08, PATCH_B + i)] = rd(prg, B08, PATCH_V + i)
        i += 1


ANIM_T, ANIM_BLK, ANIM_SRC = 0x8096, 0x80A6, 0x80DE   # 1D:$802A(BRK 1D 함수 2)


def anim_blocks(prg, t):
    """1D:$802A: 맵 종류 t 에서 CHR 이 프레임마다 바뀌는 블록과 그 그림 원본(뱅크 1D 주소). 목록 1D:$8096 의
    bit7 이 켜진 값마다 무리(X)가 하나씩 늘고, 값의 아래 7비트가 맵 종류다. 무리마다 칸 8개(1D:$80DE 의 주소, 0 이면 빈 칸)."""
    x, y = -1, 0
    while (e := rd(prg, 0x1D, ANIM_T + y)) != 0xFF:
        if e & 0x80:
            x += 1
        if e & 0x7F == t:
            out = {}
            for i in range(8):
                src = wd(prg, 0x1D, ANIM_SRC + 16 * x + 2 * i)
                if src:
                    out.setdefault(rd(prg, 0x1D, ANIM_BLK + 8 * y + i), []).append(src)
            return out
        y += 1
    return {}


def palette(prg, t, g=0, k=0, clock=0, field=0, flag6293=0):
    """BG 팔레트 1~4 의 색 1~3(12바이트, $05FD~). 색 0 은 모두 0F($05FC).
    맵: 0E:$BB55 가 (맵 종류, 밤) → 팔레트 세트 번호(0E:$BBE6), 몇몇 장소는 맵 종류를 바꿔 고른다(0E:$BBB1·$BBD3·$BBC5),
    0E:$802B 가 세트(0E:$BC68, 4바이트) → 색 세 개 묶음(0E:$BD40, 3바이트). 밤은 $62ED ≥ 78.
    필드: 1E:$A2A8 이 $62ED(시각)를 1E:$A2DB 의 경계 8개와 비교해 1E:$A2E3 의 12바이트 묶음을 고른다(필드 3 은 8번)."""
    if t == 0:
        x = 8 if field == 3 else max(i for i in range(8) if clock >= rd(prg, 0x1E, 0xA2DB + i))
        return bytes(rd(prg, 0x1E, 0xA2E3 + 12 * x + i) for i in range(12))
    a, night = t, int(clock >= 0x78)
    if field == 3:
        night = 1
    else:
        i = 0
        while not (e := rd(prg, 0x0E, 0xBBB1 + i)) & 0x80:
            kk = rd(prg, 0x0E, 0xBBD3 + i)
            if g in (e, e | 0x80) and (kk & 0x80 or kk == k):
                break
            i += 1
        else:
            i = None
        if i is not None:
            if i < 0x0E:
                a = rd(prg, 0x0E, 0xBBC5 + i)
            elif i == 0x0E:
                a = 0x36 if flag6293 & 0x10 else t
            else:
                night = int(i < 0x11)
    p = rd(prg, 0x0E, 0xBBE6 + 2 * a + night)
    out = []
    for i in range(4):
        n = rd(prg, 0x0E, 0xBC68 + 4 * p + i)
        out += [rd(prg, 0x0E, 0xBD40 + 3 * n + j) for j in range(3)]
    return bytes(out)


def load(prg, t, used=None):
    """08:$84E9 를 따라 블록 표를 올린다. used 가 None 이면(필드) 모두 올린다.
    돌려주는 것: tiles[블록] = 타일 번호 4개(왼위, 오른위, 왼아래, 오른아래), pal, kind, prop, chr{타일 번호: (뱅크, 주소)}."""
    ds = defs(prg, t)
    anim = anim_blocks(prg, t) if t else {}
    tiles, pal, kind, prop = {}, {}, {}, {}
    chr_, seen, nxt = {}, [], TILE0
    for blk in sorted(ds):
        d = ds[blk]
        if d is None:
            continue
        pal[blk] = d['pal']
        if blk < 0x20:
            kind[blk], prop[blk] = d['kind'], d['prop']
        # $8487: 맵(종류 0 이 아님)에서 구역 비트도 속성도 없는 블록은 맵에 쓰였을 때만 올린다.
        if t and blk < 0x20 and used is not None and not d['a'] & 0xE0 and not d['prop'] & 0x7F and blk not in used:
            tiles[blk] = [0, 0, 0, 0]
            continue
        ts = []
        for addr in d['addrs']:
            if blk in anim:                        # 애니메이션 블록은 찾지 않고 새 타일 4개를 받는다(1D:$8C52 가 이어진 4개를 덮어씀)
                seen.append(addr)
                chr_[nxt] = (d['bank'], addr)
                ts.append(nxt)
                nxt += 1
            elif addr in seen:                     # $823D: 같은 주소의 타일은 다시 올리지 않는다
                ts.append(TILE0 + seen.index(addr))   # 같은 주소가 여럿이면 처음 것
            else:
                seen.append(addr)
                chr_[nxt] = (d['bank'], addr)
                ts.append(nxt)
                nxt += 1
        tiles[blk] = ts
    if t and t != 0x1E and used is not None:     # $8710: 처음 비는 블록 칸($0568)에 FC~FF
        # $6E5E 가 0 인 첫 칸. 구역 비트가 있는 블록은 $84A8 이 DEC 하므로 0 이 아니게 된다.
        spare = next((b for b in range(0x20) if b not in used and not (ds[b] and ds[b]['a'] & 0xE0)), None)
        if spare is not None:
            d = entry(prg, *SPARE)
            tiles[spare] = [0xFC, 0xFD, 0xFE, 0xFF]
            pal[spare], kind[spare], prop[spare] = d['pal'], d['kind'], d['prop']
            for i, addr in enumerate(d['addrs']):
                chr_[0xFC + i] = (d['bank'], addr)
    return {'tiles': tiles, 'pal': pal, 'kind': kind, 'prop': prop, 'chr': chr_}


def shade(buf, w, h, kind, outside, t):
    """1E:$9F47: 종류(속성 a bit7-5 의 아래 3비트) 1~3 인 블록 아래 칸이 종류 0 이면 그 블록을 종류 5~7 의 블록으로 바꾼다.
    아래 칸이 다른 구역(위 3비트)이면 맵 종류에 따라 다르다($A016·$A01C 표)."""
    alt = {}
    for b in range(0x20):
        v = kind.get(b, 0) & 7
        if v >= 5:
            alt[(v & 3) - 1] = b
    out = bytearray(buf)
    for i in range(w * h):
        cur = buf[i]
        v = kind.get(cur & 0x1F, 0) & 7
        if not 1 <= v <= 3:
            continue
        below = buf[i + w] if i + w < w * h else outside
        area = cur & 0xE0
        if i + w >= w * h:
            change = not kind.get(outside & 0x1F, 0) & 7
        elif below & 0xE0 == area:
            change = not kind.get(below & 0x1F, 0) & 7
        elif t in (0x25, 0x26, 0x27, 0x28, 0x2B):
            change = (below & 0x1F) == outside and not kind.get(below & 0x1F, 0) & 7
        elif t in (0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x1D, 0x29, 0x2A):
            change = True
        else:
            change = area != 0
        if change and v - 1 in alt:
            out[i] = area | alt[v - 1]
    return bytes(out)


STIPPLE_X = 0xD469   # 0F:$D44C: $0550 bit7 이면 (X&7, Y&7) 무늬로 바깥 블록을 $0520/$0582 중에서 고른다
STIPPLE_Y = 0xD471


class Map:
    """맵 하나를 화면에 그릴 때의 상태. 마을·던전은 (그룹, 순번), 필드는 group=None(필드 0)."""

    def __init__(self, prg, g=None, k=None, field=0):
        self.prg, self.g, self.k = prg, g, k
        if g is None:
            self.t, self.f, self.field = 0, field, dq4field.decode(prg, field)
            self.w, self.h = dq4field.size(prg, field)
            self.outside = self.alt = 0
            self.code = 0
            self.blocks = load(prg, 0)
            patch_props(prg, self.blocks['prop'], field=field)
            self.buf = None
            return
        m, self.w, self.h, raw = dq4chest.load(prg, g, k)
        self.code, self.t = m[2], m[2] & 0x3F              # 08:$B708: $0550 = 레코드 첫 바이트, $0028 = 아래 6비트
        bank, ptr = m[3], m[4]
        self.outside = dq4map.header(prg, bank, ptr)[4]      # $0520
        self.alt = rd(prg, B08, OUTSIDE_ALT + self.t) if self.t < 0x0F else 0   # $0582
        self.raw = raw
        self.blocks = load(prg, self.t, used_blocks(raw, self.outside))
        patch_props(prg, self.blocks['prop'], g, k)
        self.buf = shade(raw, self.w, self.h, self.blocks['kind'], self.outside, self.t)

    def cell(self, x, y):
        """칸 값(위 3비트 구역 + 블록). 맵 밖은 0F:$D403 → $D44C."""
        if self.buf is None:
            return dq4field.lookup(self.field, self.w, self.h, x & 0xFF, y & 0xFF)
        if 0 <= x < self.w and 0 <= y < self.h:
            return self.buf[y * self.w + x]
        if self.code & 0x80 and not (rd(self.prg, 0x0F, STIPPLE_X + (x & 7)) & rd(self.prg, 0x0F, STIPPLE_Y + (y & 7))):
            return self.alt
        return self.outside

    def block(self, x, y, area=0, mode=0):
        """0F:$D4E6: 주인공 칸과 구역(위 3비트, $46)이 다른 칸은 블록 20(주인공이 구역 0) 또는 21 로 그린다.
        mode 는 $07BA: 4 일 때는 바깥 블록이 구역과 상관없이 보인다."""
        v = self.cell(x, y)
        if self.buf is not None and v & 0xE0 != area and not (mode == 4 and v & 0x1F == self.outside):
            return 0x21 if area else 0x20
        return v & 0x1F

    def tiles(self, b):
        return self.blocks['tiles'].get(b, [0, 0, 0, 0])

    def passable(self, x, y):
        """0F:$D088: 걸어 들어가려는 칸의 블록 속성($6F40) bit7 이 켜져 있으면 못 간다(83 은 배로만)."""
        return not self.blocks['prop'].get(self.cell(x, y) & 0x1F, 0) & 0x80


def screen(m, left, top, sx, sy, area=0, mode=0, cols=16, rows=15):
    """화면 왼쪽 위 칸 (left, top)($7C, $7B)과 스크롤 픽셀 (sx, sy)로 nametable 2장(세로 미러링: 가로로 나란히)을 채운다.
    돌려주는 것: {(nametable 열 0~63, 줄 0~29): 타일}, {(열, 줄): 팔레트}(2×2 타일마다)."""
    nt, pal = {}, {}
    for j in range(rows):
        for i in range(cols):
            b = m.block((left + i) & 0xFF, (top + j) & 0xFF, area, mode)
            c, r = (sx // 8 + 2 * i) % 64, (sy // 8 + 2 * j) % 30
            for q, t in enumerate(m.tiles(b)):
                nt[((c + (q & 1)) % 64, (r + (q >> 1)) % 30)] = t
            if b in m.blocks['pal']:            # 정의가 없는 블록은 빈 타일 00 이라 팔레트가 보이지 않는다
                pal[(c, r)] = m.blocks['pal'][b]
    return nt, pal


def nt_read(nt, c, r):
    return nt[(c // 32) * 0x400 + r * 32 + c % 32]


def nt_pal(nt, c, r):
    """attribute 표에서 (열, 줄) 타일이 쓰는 팔레트."""
    a = nt[(c // 32) * 0x400 + 0x3C0 + (r // 4) * 8 + (c % 32) // 4]
    return a >> ((r & 2) * 2 + (c & 2)) & 3


def compare(prg, d, prefix=None):
    """seq.lua 의 end.ram·end.sram·end.nt·end.chr·end.pal(prefix 를 주면 blockload.lua 의 <prefix>.cpu·chr·nt·pal) 와 비교.
    블록 표($7600·$76C0·$6F20·$6F40), 올린 CHR 타일, BG 팔레트, 화면 16×15 칸의 nametable·attribute."""
    if prefix is None:
        ram = open(os.path.join(d, 'end.ram'), 'rb').read()
        wram = open(os.path.join(d, 'end.sram'), 'rb').read()
        nt, chr_, ppal = (open(os.path.join(d, 'end.' + x), 'rb').read() for x in ('nt', 'chr', 'pal'))
    else:
        p = os.path.join(d, prefix)
        cpu = open(p + '.cpu', 'rb').read()
        ram, wram = cpu[:0x800], cpu[0x6000:0x8000]
        nt, chr_, ppal = (open(p + '.' + x, 'rb').read() for x in ('nt', 'chr', 'pal'))
    t = ram[0x28]
    m = Map(prg, field=ram[0x65]) if t == 0 else Map(prg, ram[0x63], ram[0x64])
    bl = m.blocks
    ab = anim_blocks(prg, t)
    bad = []
    for b, ts in bl['tiles'].items():
        if (b not in ab and list(wram[0x1600 + 4 * b:0x1604 + 4 * b]) != ts) or wram[0x16C0 + b] != bl['pal'][b]:
            bad.append(f'{b:02X}')
    for b in range(0x20):
        if wram[0xF20 + b] != bl['kind'].get(b, 0) or wram[0xF40 + b] != bl['prop'].get(b, 0):
            bad.append(f'{b:02X}:{wram[0xF40 + b]:02X}≠{bl["prop"].get(b, 0):02X}')
    anim = {n for b in ab for n in bl['tiles'].get(b, [])}
    cbad = [n for n, (bank, a) in bl['chr'].items() if n not in anim
            and chr_[0x1000 + n * 16:0x1010 + n * 16] != prg[bank * 0x4000 + (a & 0x3FFF):][:16]]
    print(f'맵 종류 {t:02X}: 블록 표 {len(bad)} 다름' + (f'({" ".join(bad)})' if bad else '')
          + f', CHR 타일 {len(bl["chr"]) - len(anim)}개 중 {len(cbad)} 다름(애니메이션 {len(anim)}개 뺌)')
    want_p = palette(prg, t, ram[0x63], ram[0x64], wram[0x2ED], ram[0x65], wram[0x293])
    got_p = bytes(ppal[i] for i in range(16) if i & 3)
    print(f'BG 팔레트 {"같음" if want_p == got_p else "다름 " + got_p.hex(" ") + " / " + want_p.hex(" ")}')
    if m.buf is not None:
        cur = wram[0x1800:0x1800 + m.w * m.h]
        sd = sum(x != y for x, y in zip(m.buf, cur))
        print(f'$7800(그늘 바꾸기 뒤) {m.w * m.h} 바이트 중 {sd} 다름, 바뀐 칸 {sum(x != y for x, y in zip(m.raw, m.buf))}')
    area = wram[0x1140] & 0xE0 if t else 0
    sx = (ram[0x505] & 1) * 256 + ram[0x508]
    sy = ram[0x509]
    want, wpal = screen(m, ram[0x7C], ram[0x7B], sx, sy, area, ram[0x7BA])
    nd = [(c, r) for (c, r), v in want.items() if nt_read(nt, c, r) != v and v not in anim]
    pd = [(c, r) for (c, r), v in wpal.items() if nt_pal(nt, c, r) != v]
    print(f'화면 nametable {len(want)} 타일 중 {len(nd)} 다름, attribute {len(wpal)} 칸 중 {len(pd)} 다름')
    if nd:
        print('  다른 곳(열,줄):', ' '.join(f'{c},{r}' for c, r in nd[:16]))
    return not bad and not cbad and want_p == got_p and not nd and not pd


TERRAIN_VALUES = 0xCEEB           # 0F:$CEB1: 걸음을 마친 칸의 속성 아래 7비트와 비교하는 값 11개
CONVEYOR_PAD = 0xCB1A             # 0F:$CA77: 속성 10~13 의 아래 2비트 → 패드 $14 (위·오른쪽·아래·왼쪽)
DOOR_LOCKS = 0xB3C8               # 1E:$B36E: 문 값 16개를 잠금 단계(행)마다 4개씩
KEYS = 0xB3D8                     # 1E:$B3B7: 열쇠 아이템 3개(とうぞく·まほう·さいご), 뒤일수록 센 열쇠
LIFTS = 0x89C8                    # 1E:$894A: 속성 0F 칸의 (그룹, 포인터) 표
FALLS = 0xB96F                    # 12:$B6DD: 떨어지는 칸(05·0B)의 목적지 표 포인터
FALL_FIELD1 = 0xB8C5              # 12:$B8A5: 그룹 2D·46 은 필드 1 의 방향별 좌표
POTS = 0xBCED                     # 1E:$BC7A: タンス·つぼ 7바이트 항목
SIGNS = 0xBBB6                    # 1E:$BB52: 팻말 표 포인터 2개
SIGN_CHAPTER = 0xBBE6             # 1E:$BB8C: 팻말 메시지 바이트가 00 이면 장($615A)마다 셋 중 하나

STEP_XY = [(0, -1), (1, 0), (0, 1), (-1, 0)]
FACING = {0x2B: 'dresser', 0x2A: 'pot', 0x28: 'sign', 0x30: 'push_door', 0x2C: 'stuck_door'}


def terrain(prg, prop):
    """블록 속성 하나가 걷기·명령에서 뜻하는 것(fc/dq4/docs/dq4-block-format.md 「지형 효과」).
    walk: 걸어서 들어감, ship: 배로 들어감, effect: 걸음을 마친 뒤(0F:$CEB1) 하는 일,
    door·talk_over·facing: 앞 칸으로 쓰일 때(「とびら」·「はなす」·「しらべる」)."""
    v = prop & 0x7F
    out = {'walk': not prop & 0x80, 'ship': prop in (0x83, 0x24)}
    if prop == 0x83:
        out['effect'] = 'water'
    elif prop == 0x24:
        out['effect'] = 'dock'                  # 0F:$D00D: 배를 탄 채로 지나감
    elif not prop & 0x80:
        if v in (0x01, 0x02):
            out.update(effect='damage', hp=1 if v == 1 else 15)     # 1E:$9ACA
        elif v == 0x04:
            out['effect'] = 'chest'
        elif v in (0x05, 0x0B):
            out['effect'] = 'fall'              # 1E:$8676 → 12:$B6DD
        elif v == 0x0A:
            out['effect'] = 'travel_door'       # 1B:$A10F
        elif v == 0x0F:
            out['effect'] = 'lift'              # 1E:$8700 → 1E:$894A
        elif 0x10 <= v <= 0x13:
            pad = rd(prg, 0x0F, CONVEYOR_PAD + (v & 3))
            out.update(effect='conveyor', dir=['up', 'right', 'down', 'left'][[0x10, 0x80, 0x20, 0x40].index(pad)])
        elif v == 0x31:
            out['effect'] = 'slow_vertical'     # 0F:$E9E4
        elif v == 0x33:
            out['effect'] = 'search'            # 1E:$B41C
        elif v in [rd(prg, 0x0F, TERRAIN_VALUES + i) for i in range(11)]:
            out['effect'] = 'exit'              # 1E:$9100
    locks = [rd(prg, 0x1E, DOOR_LOCKS + i) for i in range(16)]
    if prop & 0x80 and v in locks:
        i = locks.index(v)
        # lock 0 은 열쇠 없이 열림, 1~3 은 KEYS[lock-1] 이상의 열쇠
        out['door'] = {'lock': i >> 2, 'shape': i & 3}
    if prop & 0x80 and v in (0x17, 0x27):
        out['talk_over'] = True                 # 1E:$80D8
    if prop & 0x80 and v in FACING:
        out['facing'] = FACING[v]
    return out


def fall_table(prg):
    """12:$B6DD 의 표. 항목 = 그룹, 순번(bit7 이면 조건이 붙음), [조건, 목적지]….
    조건: x|80 y 크기(아래 4비트 폭−1, 위 4비트 높이−1)인 사각형, 또는 x y 한 칸. 조건 첫 바이트 bit6 이면 다음 조건이 이어짐.
    목적지: 순번|80(좌표 그대로) 또는 순번 x y(x 는 아래 6비트)."""
    p = wd(prg, 0x12, FALLS)
    out = []

    def dest(p):
        d = rd(prg, 0x12, p)
        if d & 0x80:
            return {'index': d & 0x7F}, p + 1
        return {'index': d, 'x': rd(prg, 0x12, p + 1) & 0x3F, 'y': rd(prg, 0x12, p + 2)}, p + 3

    while (g := rd(prg, 0x12, p)) != 0xFF:
        k = rd(prg, 0x12, p + 1)
        p += 2
        if not k & 0x80:
            to, p = dest(p)
            out.append({'group': g, 'index': k, 'when': None, 'to': to})
            continue
        while True:
            c = rd(prg, 0x12, p)
            if c & 0x80:
                s = rd(prg, 0x12, p + 2)
                when = {'x': c & 0x3F, 'y': rd(prg, 0x12, p + 1) & 0x3F, 'w': (s & 15) + 1, 'h': (s >> 4) + 1}
                p += 3
            else:
                when = {'x': c & 0x3F, 'y': rd(prg, 0x12, p + 1), 'w': 1, 'h': 1}
                p += 2
            to, p = dest(p)
            out.append({'group': g, 'index': k & 0x7F, 'when': when, 'to': to})
            if not c & 0x40:
                break
    return out


def fall(prg, g, k, x, y, d=2, mode=0, chapter=0):
    """12:$B6DD: (g, k) 의 (x, y) 에서 떨어졌을 때 가는 곳. d 는 걷던 방향($3D), mode 는 $07BA, chapter 는 $615A.
    돌려주는 것: {'group', 'index', 'x', 'y'}(맵), {'field': n, 'x', 'y'}(필드 n 의 좌표),
    {'field': None, 'dx', 'dy'}(들어온 필드 자리 $42/$43 에서 그만큼 옮긴 곳)."""
    if g == 0x1C:
        return {'group': 0x3A, 'index': 0, 'x': 0x17, 'y': 0x03}
    if g == 0x46 and (x, y) == (0x23, 0x1D):
        return {'field': 1, 'x': 0x13, 'y': 0x11}
    if g in (0x2D, 0x46):
        return {'field': 1, 'x': rd(prg, 0x12, FALL_FIELD1 + 2 * d), 'y': rd(prg, 0x12, FALL_FIELD1 + 2 * d + 1)}
    if g == 0x30:
        return {'field': None, 'dx': 0, 'dy': 3 if chapter == 0 else 2}
    if g == 0x2E and k == 1:
        if x >= 0x0B and y < 0x06:
            return {'group': g, 'index': 2, 'x': 0x0A, 'y': 0x06}
        if x >= 0x03 and y < 0x07:
            return {'group': g, 'index': 2, 'x': 0x05, 'y': 0x06}
        if y < 0x11:
            return {'group': g, 'index': 2, 'x': 0x06, 'y': 0x0A}
    elif g == 0x3D and k == 1:
        return {'group': g, 'index': 3, 'x': 0x08, 'y': 0x0F}      # $62AA bit7 도 켬
    elif g != 0x2E:
        for e in fall_table(prg):
            w = e['when']
            if (e['group'], e['index']) != (g, k):
                continue
            if w and not (w['x'] <= x < w['x'] + w['w'] and w['y'] <= y < w['y'] + w['h']):
                continue
            return {'group': g, 'index': e['to']['index'], 'x': e['to'].get('x', x), 'y': e['to'].get('y', y)}
    dx, dy = STEP_XY[d & 3]
    if d == 0 and mode in (0, 4, 5) or d == 1 and mode == 0:
        dx, dy = 2 * dx, 2 * dy
    return {'field': None, 'dx': dx, 'dy': dy}


def lifts(prg):
    """1E:$894A: 속성 0F 칸. 그룹마다 8바이트 레코드 = (순번, x, y, 값) 두 개가 서로 오가는 짝. 값은 $7F 로 간다."""
    out, a = [], LIFTS
    while (g := rd(prg, 0x1E, a)) != 0xFF:
        p = wd(prg, 0x1E, a + 1)
        while rd(prg, 0x1E, p) != 0xFF:
            e = [rd(prg, 0x1E, p + i) for i in range(8)]
            out.append({'group': g, 'a': dict(zip(('index', 'x', 'y', 'arg'), e[:4])),
                        'b': dict(zip(('index', 'x', 'y', 'arg'), e[4:]))})
            p += 8
        a += 3
    return out


LIFT_RECTS = 0x8A24               # 1E:$8A68: 리프트 넷째 바이트($7F)마다 5바이트 = 구역, 폭, 높이, $7800 주소
LIFT_AREA = 0x8A42                # 1E:$8A48: 내린 뒤 그 사각형과 주인공($46)의 구역


def lift_rects(prg):
    """1E:$8A0D·$8A48: 리프트의 넷째 바이트 n(FF 가 아니면)이 고르는 사각형. 떠날 때 사각형의 칸 위 3비트를
    구역(80)으로, 내리면 LIFT_AREA[n] 으로 바꾼다(1E:$8A9A). 돌려주는 것: n 마다 {'w', 'h', 'offset', 'ride', 'land'}.
    offset 은 $7800 에서 떨어진 바이트 수(맵 폭으로 나누면 왼쪽 위 칸)."""
    out = []
    for n in range(6):
        a = LIFT_RECTS + 5 * n
        out.append({'ride': rd(prg, 0x1E, a), 'w': rd(prg, 0x1E, a + 1), 'h': rd(prg, 0x1E, a + 2),
                    'offset': wd(prg, 0x1E, a + 3) - 0x7800, 'land': rd(prg, 0x1E, LIFT_AREA + n)})
    return out


def pots(prg):
    """1E:$BC7A: タンス·つぼ(앞 칸 속성 AB·AA). 7바이트 = 그룹, 순번, x, y, 아이템, 플래그 $6273+n, 비트."""
    out, a = [], POTS
    while rd(prg, 0x1E, a) != 0xFF:
        e = [rd(prg, 0x1E, a + i) for i in range(7)]
        out.append({'group': e[0], 'index': e[1], 'x': e[2], 'y': e[3], 'item': e[4], 'flag': 0x6273 + e[5], 'bit': e[6]})
        a += 7
    return out


def signs(prg):
    """1E:$BB52: 팻말(앞 칸 속성 A8). 그룹은 보지 않고 좌표만 본다. 표 0 은 $41 bit7 이 켜졌을 때, 표 1 은 꺼졌을 때.
    항목 = x, y, 메시지 하위 바이트(상위는 03). 00 이면 장에 따라 SIGN_CHAPTER 의 셋 중 하나(1·2장, 3장, 4장부터)."""
    out = []
    for t in range(2):
        a = wd(prg, 0x1E, SIGNS + 2 * t)
        while (x := rd(prg, 0x1E, a)) != 0xFF:
            lo = rd(prg, 0x1E, a + 2)
            msgs = [0x300 | rd(prg, 0x1E, SIGN_CHAPTER + i) for i in range(3)] if lo == 0 else [0x300 | lo]
            out.append({'table': t, 'x': x, 'y': rd(prg, 0x1E, a + 1), 'msg': msgs})
            a += 3
    return out


EXIT_BUF = 0xB671                 # 08:$B4ED: 칸 세기의 시작 주소($7800)
EXIT_KINDS = 0xB673               # 08:$B4ED·$B554: 세는 속성 값 목록의 포인터(00 끝)
EXIT_FIXED = 0xB681               # 08:$B323: 9바이트 = 그룹, 순번, x, y → 그룹, 순번, x, y, 방향. FF 끝
EXIT_TABLE = 0xB974               # 08:$B246: 그룹마다 순번별 출구 레코드 목록의 포인터


def exit_kinds(prg):
    a, out = wd(prg, B08, EXIT_KINDS), []
    while v := rd(prg, B08, a):
        out.append(v)
        a += 1
    return out


def exit_cells(prg, m):
    """맵에서 08:$B4ED 가 세는 칸(속성 아래 7비트가 exit_kinds 에 있는 칸)을 $7800 순서(줄마다 왼쪽부터)로 (x, y, 속성)."""
    kinds = exit_kinds(prg)
    out = []
    for i, v in enumerate(m.buf):
        p = m.blocks['prop'].get(v & 0x1F, 0)
        if p & 0x7F in kinds:
            out.append((i % m.w, i // m.w, p))
    return out


def exit_fixed(prg):
    out, a = [], EXIT_FIXED
    while rd(prg, B08, a) != 0xFF:
        e = [rd(prg, B08, a + i) for i in range(9)]
        out.append({'group': e[0], 'index': e[1], 'x': e[2], 'y': e[3],
                    'to': {'group': e[4], 'index': e[5], 'x': e[6], 'y': e[7], 'dir': e[8]}})
        a += 9
    return out


def exit_table(prg):
    """08:$B246 의 표: {그룹: [순번마다 레코드 목록]}. 레코드 첫 바이트 bit7 이 그 순번의 마지막,
    bit6-5 가 종류, bit4-0 이 목적지 순번. 종류 0 = 1바이트(필드로), 1 = 3바이트(순번, n, 그룹),
    2 = 2바이트(그룹, 필드에서 들어갈 때의 자리로), 3 = 2바이트(같은 그룹의 순번, n). n 은 목적지 맵에서 센 칸 순번."""
    a, out = wd(prg, B08, EXIT_TABLE), {}
    while (g := rd(prg, B08, a)) != 0xFF:
        a += 1
        subs = [[]]
        while (b := rd(prg, B08, a)) != 0xFF:
            t = b >> 5 & 3
            e = {'kind': ['field', 'map', 'enter', 'same'][t]}
            if t == 1:
                e.update(group=rd(prg, B08, a + 2), index=b & 0x1F, n=rd(prg, B08, a + 1))
            elif t == 2:
                e.update(group=rd(prg, B08, a + 1))
            elif t == 3:
                e.update(group=g, index=b & 0x1F, n=rd(prg, B08, a + 1))
            subs[-1].append(e)
            a += [1, 3, 2, 2][t]
            if b & 0x80:
                subs.append([])
        a += 1
        if not subs[-1]:
            subs.pop()
        out[g] = subs
    return out


def exit_special(g, k, n, flags=0, night=False, flag6295=0):
    """08:$B397: 목적지 그룹·순번에 따라 이벤트 플래그($62AA)·밤·$6295 로 순번(과 n)을 바꾼다(코드 읽기)."""
    if g == 0x3D and k == 1 and flags & 0x80:
        return 2, n + 1 if 1 <= n < 4 else n
    if g == 0x40 and k == 1 and n == 0 and flags & 0x20:
        return 2, n
    if g == 0x45 and k == 4 and n in (0, 4) and flags & 0x10:
        return 6, 5 if n == 4 else n
    if g == 0x45 and k == 5 and n == 2 and flags & 0x02:
        return 7, n
    if g == 0x42 and k == 1 and flags & 0x08:
        return 0, n
    if g == 0x19 and k == 0 and night:
        return 1, n
    if g == 0x15 and k == 3 and not night:
        return 2, n
    if g == 0x34 and k == 3 and not flag6295 & 1:
        return 2, 0
    if g == 0x14 and k == 0 and flags & 1:
        return 2, 0
    return k, n


def exit_arrive_dir(prop):
    """08:$B59F: 도착 칸의 속성으로 방향(bit1-0, 0 위 1 오른쪽 2 아래 3 왼쪽)을 정한다. 정하지 않으면 None."""
    return {0x08: 0x83, 0x09: 0x81, 0x25: 0x80, 0x26: 0x80, 0x0F: 0x82, 0x0A: 0x82}.get(prop & 0x7F)


EXIT_FIELD_SPECIAL = {(0x41, 0x0E, 0x30): (0x8D, 0x1F), (0x42, 0x1F, 0x02): (0x84, 0x5A)}   # 08:$B2EC


def exit_to_field(prg, g, x, y):
    """08:$B2E5 → $B06A: 그룹의 필드 입구(0E:$BE69 의 첫 항목) 좌표로, 필드 번호는 도착 표(08:$B7F9)의 bit6-5.
    그룹 0E·0B 는 B06A 가 걷던 방향($3D)에 따라 좌표를 한 칸 옮긴다(코드 읽기, 여기서는 옮기지 않음)."""
    for eg, fx, fy, *rest in dq4field.entrances(prg):
        if eg == g:
            fx, fy = EXIT_FIELD_SPECIAL.get((g, x, y), (fx, fy))
            return {'field': rest[4], 'group': g, 'x': fx, 'y': fy}
    return {'field': None, 'group': g}


def exit_links(prg, g, k, maps=None, **flags):
    """(g, k) 의 출구 칸마다 08:$B22E 가 정하는 목적지. maps 는 {(그룹, 순번): Map} 캐시.
    돌려주는 것: [{'x', 'y', 'prop', 'ord', 'to'}]. to 는 {'group', 'index', 'n', 'x', 'y', 'dir'}(맵, n 은 도착 맵의 칸 순번),
    {'field', 'group', 'x', 'y'}(필드 번호와 좌표), {'enter': 그룹}(필드에서 들어갈 때의 도착 자리 08:$B7F9 로), None(레코드 없음)."""
    maps = {} if maps is None else maps

    def get(gg, kk):
        if (gg, kk) not in maps:
            maps[gg, kk] = Map(prg, gg, kk)
        return maps[gg, kk]

    fixed = {(e['group'], e['index'], e['x'], e['y']): e['to'] for e in exit_fixed(prg)}
    # 08:$B285: 순번 k 의 목록까지 건너뛴 뒤 칸 순번만큼 레코드를 건너뛴다. 목록 끝을 보지 않으므로
    # 레코드보다 칸이 많은 맵은 다음 순번의 레코드를 읽는다.
    subs = exit_table(prg).get(g, [])
    recs = [r for s in subs[k:] for r in s]
    out = []
    for i, (x, y, p) in enumerate(exit_cells(prg, get(g, k))):
        e = {'x': x, 'y': y, 'prop': p, 'ord': i}
        if (g, k, x, y) in fixed:
            e['to'] = dict(fixed[g, k, x, y], fixed=True)
        elif i >= len(recs):
            e['to'] = None
        else:
            r = recs[i]
            if r['kind'] == 'field':
                e['to'] = exit_to_field(prg, g, x, y)
            elif r['kind'] == 'enter':
                e['to'] = {'enter': r['group']}
            else:
                dk, n = exit_special(r['group'], r['index'], r['n'], **flags)
                try:
                    cells = exit_cells(prg, get(r['group'], dk))
                except (KeyError, IndexError, ValueError):
                    cells = []
                to = {'group': r['group'], 'index': dk, 'n': n}
                if n < len(cells):
                    to.update(x=cells[n][0], y=cells[n][1], dir=exit_arrive_dir(cells[n][2]))
                e['to'] = to
        out.append(e)
    return out


DOOR_FLOORS = 0x882A              # 08:$880E: 문을 연 뒤 바닥으로 고를 모양 레코드 번호(2바이트씩, FF FF 끝). 앞일수록 먼저


def door_floor_rank(prg, rec):
    a, i = DOOR_FLOORS, 0
    while (lo := rd(prg, B08, a)) != 0xFF or rd(prg, B08, a + 1) != 0xFF:
        if (rd(prg, B08, a + 1), lo) == (rec >> 8, rec & 0xFF):
            return i
        a, i = a + 2, i + 1
    return 0xFF


def door_open(prg, m, x, y, d):
    """08:$8796(문 모양 0, 값 14~17): (x, y) 에 서서 d 방향(0 위 1 오른쪽 2 아래 3 왼쪽)의 문을 열면 문 칸에 쓰는 블록.
    선 칸과 문 너머 칸의 블록 모양 레코드(블록 정의 a&3, b)를 DOOR_FLOORS 에서 찾아 앞쪽에 있는 것을 고른다(같으면 선 칸).
    돌려주는 것: (문 x, 문 y, 블록)."""
    dx, dy = STEP_XY[d & 3]
    here = m.cell(x, y) & 0x1F
    there = m.cell(x + 2 * dx, y + 2 * dy) & 0x1F

    blocks = defs(prg, m.t)

    def rank(b):
        e = blocks.get(b)
        return door_floor_rank(prg, (e['a'] & 3) << 8 | e['b']) if e else 0xFF
    return x + dx, y + dy, there if rank(there) < rank(here) else here


def export(prg, path):
    """맵 279개·필드 3개의 블록 속성과 칸, 지형 효과에 딸린 표를 JSON 하나로. 칸은 줄마다 16진 문자열
    (맵은 그늘 바꾸기 뒤 $7800 의 값: 위 3비트 구역 + 블록, 필드는 블록 번호)."""
    import json
    effects = {}

    def props(prop):
        for p in prop.values():
            effects.setdefault(f'{p:02X}', terrain(prg, p))
        return [f'{prop[b]:02X}' if b in prop else None for b in range(0x20)]

    maps, cache = [], {}
    for g, k, *_ in map_list(prg):
        m = cache.setdefault((g, k), Map(prg, g, k))
        fl = [{'x': x, 'y': y, 'to': fall(prg, g, k, x, y)} for y in range(m.h) for x in range(m.w)
              if m.blocks['prop'].get(m.buf[y * m.w + x] & 0x1F, 0) in (0x05, 0x0B)]
        maps.append({'group': g, 'index': k, 'type': m.t, 'w': m.w, 'h': m.h, 'outside': m.outside,
                     'props': props(m.blocks['prop']), 'cells': [m.buf[y * m.w:(y + 1) * m.w].hex() for y in range(m.h)],
                     'falls': fl, 'exits': exit_links(prg, g, k, cache)})
    fields = []
    for f in range(3):
        m = Map(prg, field=f)
        fields.append({'field': f, 'w': m.w, 'h': m.h, 'props': props(m.blocks['prop']),
                       'cells': [bytes(r).hex() for r in m.field]})
    data = {'effects': dict(sorted(effects.items())), 'keys': [rd(prg, 0x1E, KEYS + i) for i in range(3)],
            'maps': maps, 'fields': fields, 'fall_table': fall_table(prg), 'lifts': lifts(prg),
            'pots': pots(prg), 'signs': signs(prg), 'lift_rects': lift_rects(prg),
            'exit_kinds': exit_kinds(prg), 'exit_fixed': exit_fixed(prg),
            'exit_table': {f'{g:02X}': v for g, v in exit_table(prg).items()}}
    for e in data['signs']:      # 팻말 표는 그룹을 보지 않으므로 그 좌표에 A8 칸이 있는 곳을 붙인다
        if e['table']:
            e['at'] = [f'field{f["field"]}' for f in fields if (row := f['cells'][e['y']] if e['y'] < f['h'] else '')
                       and e['x'] < f['w'] and f['props'][int(row[2 * e['x']:2 * e['x'] + 2], 16)] == 'A8']
        else:
            e['at'] = [f'{m["group"]:02X}/{m["index"]:02X}' for m in maps if e['x'] < m['w'] and e['y'] < m['h']
                       and m['props'][int(m['cells'][e['y']][2 * e['x']:2 * e['x'] + 2], 16) & 0x1F] == 'A8']
    with open(path, 'w') as fp:
        json.dump(data, fp, ensure_ascii=False, separators=(',', ':'))
    return data


MARKS = 'GHIJKLMNOPQRSTUVWXYZ'
BLOCKED = 'abcdefghijklmnopqrstuvwxyz'

# 속성($6F40) 값 → 사람이 읽는 뜻. 기계가 읽는 뜻은 terrain(). 근거는 fc/dq4/docs/dq4-block-format.md 의 「속성 값」 표.
KINDS = {
    0x00: '바닥',
    0x01: '독늪(걸음마다 HP 1)',
    0x02: '데미지 바닥(걸음마다 HP 15)',
    0x04: '보물상자',
    0x05: '떨어지는 칸(12:$B6DD)',
    0x06: '입구·출구 검사',
    0x07: '입구·출구 검사',
    0x08: '계단',
    0x09: '계단',
    0x0A: '旅の扉',
    0x0B: '떨어지는 칸(12:$B6DD)',
    0x0C: '입구·출구 검사',
    0x0F: '리프트(1E:$894A)',
    0x10: '밀리는 바닥(위)',
    0x11: '밀리는 바닥(오른쪽)',
    0x12: '밀리는 바닥(아래)',
    0x13: '밀리는 바닥(왼쪽)',
    0x24: '걸어서·배로 감',
    0x25: '입구·출구 검사',
    0x26: '입구·출구 검사',
    0x31: '세로로 느린 칸',
    0x33: '「しらべる」 칸(1E:$B41C)',
    0x80: '벽',
    0x83: '물(배로만)',
    0x94: '문(열쇠 없이)',
    0x95: '문(とうぞくのカギ)',
    0x96: '문(まほうのカギ)',
    0x97: '문(さいごのカギ)·카운터',
    0x9C: '문(열쇠 없이)',
    0x9D: '문(とうぞくのカギ)',
    0xA0: '문(열쇠 없이)',
    0xA2: '문(まほうのカギ)',
    0xA7: '카운터(너머로 말 걸기)',
    0xA8: '팻말',
    0xAA: 'つぼ',
    0xAB: 'タンス',
    0xAC: '열리지 않는 문',
    0xB0: '막힘(그룹 3F 는 부술 수 있는 문)',
}


def kind_name(prop):
    if prop in KINDS:
        return KINDS[prop]
    return '막힘(뜻 모름)' if prop & 0x80 else '지나감(뜻 모름)'


def marks(used):
    """통행 지도 글자: . 바닥(00), # 벽(80), ~ 물(83), 그 밖의 막힌 값은 작은 값부터 a, b, …(맵마다 다름),
    지나가는 값은 01~0F 이면 16진 한 자리, 10~ 이면 G 부터."""
    out, nb = {}, 0
    for p in sorted(used):
        if p in (0x00, 0x80, 0x83):
            out[p] = {0x00: '.', 0x80: '#', 0x83: '~'}[p]
        elif p & 0x80:
            out[p] = BLOCKED[nb % len(BLOCKED)]
            nb += 1
        else:
            out[p] = f'{p:X}' if p < 0x10 else MARKS[(p - 0x10) % len(MARKS)]
    return out


def show_pass(m):
    """맵 전체의 통행 지도(블록 속성 $6F40 기준). 인물·이벤트로 막히는 칸은 들어 있지 않다."""
    props = m.blocks['prop']
    grid = [[props.get(m.cell(x, y) & 0x1F, 0) for x in range(m.w)] for y in range(m.h)]
    mk = marks({p for row in grid for p in row})
    print(f'# 크기 {m.w}x{m.h}, 맵 종류 {m.t:02X}' + (f', 바깥 블록 {m.outside:02X}' if m.buf is not None else ''))
    print('    ' + ''.join(f'{x >> 4:X}' for x in range(m.w)))
    print('    ' + ''.join(f'{x & 15:X}' for x in range(m.w)))
    for y, row in enumerate(grid):
        print(f'{y:02X}  ' + ''.join(mk[p] for p in row))
    print('# 속성:', ', '.join(f'{c}={p:02X} {kind_name(p)}' for p, c in mk.items()))


def map_list(prg):
    """맵 279개(그룹 48 까지). dq4map.maps 는 마지막 그룹을 세지 못해 dq4chest.all_maps 를 쓴다."""
    return dq4chest.all_maps(prg)


def all_maps(prg):
    """롬의 맵 279개와 필드 3개를 (이름, Map) 으로."""
    for g, k, *_ in map_list(prg):
        yield f'{g:02X}/{k:02X}', Map(prg, g, k)
    for f in range(3):
        yield f'field{f}', Map(prg, field=f)


def map_props(m):
    """맵에 실제로 그려지는 칸의 {속성: [블록…]}과 칸 수."""
    props, cells = m.blocks['prop'], {}
    for y in range(m.h):
        for x in range(m.w):
            b = m.cell(x, y) & 0x1F
            cells.setdefault(props.get(b, 0), {}).setdefault(b, 0)
            cells[props.get(b, 0)][b] += 1
    return cells


def show_props(prg, per_map=False):
    """속성 값마다 뜻·쓰는 맵 수·칸 수와 예. per_map 이면 맵마다 한 줄(속성=블록들)."""
    total = {}
    for name, m in all_maps(prg):
        cells = map_props(m)
        if per_map:
            print(f'{name} 종류 {m.t:02X}: ' + ' '.join(
                f'{p:02X}=' + ','.join(f'{b:02X}' for b in sorted(bs)) for p, bs in sorted(cells.items())))
        for p, bs in cells.items():
            t = total.setdefault(p, [0, 0, []])
            t[0] += 1
            t[1] += sum(bs.values())
            if len(t[2]) < 3:
                t[2].append(f'{name}:{min(bs):02X}')
    if per_map:
        return
    print('속성 | 뜻 | 맵 수 | 칸 수 | 예(맵:블록)')
    for p in sorted(total):
        n, c, ex = total[p]
        print(f'{p:02X} | {kind_name(p)} | {n} | {c} | {" ".join(ex)}')


def hx(o):
    """출력용: dict·list 안의 정수를 두 자리 16진 문자열로."""
    if isinstance(o, dict):
        return '{' + ', '.join(f'{k}: {hx(v)}' for k, v in o.items()) + '}'
    if isinstance(o, list):
        return '[' + ', '.join(hx(v) for v in o) + ']'
    if isinstance(o, bool) or o is None:
        return str(o)
    return f'{o:02X}' if isinstance(o, int) else str(o)


def show_effects(prg, g, k):
    """맵의 속성마다 terrain() 의 뜻과 칸 수, 떨어지는 칸이면 가는 곳."""
    m = Map(prg, g, k)
    cells = {}
    for y in range(m.h):
        for x in range(m.w):
            cells.setdefault(m.blocks['prop'].get(m.buf[y * m.w + x] & 0x1F, 0), []).append((x, y))
    for p, xs in sorted(cells.items()):
        print(f'{p:02X} {len(xs):4d}칸', hx(terrain(prg, p)))
        if p in (0x05, 0x0B):
            for x, y in xs:
                print(f'   ({x:02X},{y:02X}) →', hx(fall(prg, g, k, x, y)))


def show_tables(prg):
    used = {}
    for g, k, *_ in map_list(prg):
        for p in Map(prg, g, k).blocks['prop'].values():
            used.setdefault(p, terrain(prg, p))
    for f in range(3):
        for p in Map(prg, field=f).blocks['prop'].values():
            used.setdefault(p, terrain(prg, p))
    print('# 속성 값')
    for p, t in sorted(used.items()):
        print(f'{p:02X}', hx(t))
    print('# 떨어지는 칸 표(12:$B6DD)')
    for e in fall_table(prg):
        print(hx(e))
    print('# 리프트(1E:$894A)')
    for e in lifts(prg):
        print(hx(e))
    print('# 리프트 사각형(1E:$8A24)')
    for e in lift_rects(prg):
        print(hx(e))
    print('# タンス·つぼ(1E:$BC7A)')
    for e in pots(prg):
        print(hx(e))
    print('# 팻말(1E:$BB52)')
    for e in signs(prg):
        print(hx(e))


def show_links(prg, g=None, k=None):
    """출구 칸(08:$B22E)마다 목적지. 맵을 주지 않으면 모든 맵."""
    cache = {}
    for gg, kk, *_ in map_list(prg):
        if g is not None and (gg, kk) != (g, k):
            continue
        for e in exit_links(prg, gg, kk, cache):
            t = e['to']
            if t is None:
                dest = '레코드 없음'
            elif 'enter' in t:
                dest = f"그룹 {t['enter']:02X} 의 필드 도착 자리"
            elif 'field' in t:
                dest = f"필드 {t['field']} ({t.get('x', 0):02X},{t.get('y', 0):02X})"
            else:
                dest = (f"{t['group']:02X}/{t['index']:02X} ({t.get('x', 0):02X},{t.get('y', 0):02X})"
                        + (' 고정 표' if t.get('fixed') else f" n={t['n']}"))
            print(f"{gg:02X}/{kk:02X} ({e['x']:02X},{e['y']:02X}) {e['prop']:02X} #{e['ord']} → {dest}")


def show_nt(m):
    """맵 전체를 nametable 타일 번호(블록마다 2×2)로. 구역은 주인공이 구역 0 에 있을 때처럼 그린다."""
    for y in range(m.h):
        rows = [[], []]
        for x in range(m.w):
            ts = m.tiles(m.block(x, y))
            rows[0] += ts[:2]
            rows[1] += ts[2:]
        for r in rows:
            print(' '.join(f'{v:02X}' for v in r))


def nes_rgb(c):
    """NES 색 번호 → 대략의 RGB(확인용 그림 전용). 색상(아래 4비트)을 YIQ 색 원 위의 각도 195°−30°×색상으로,
    밝기(bit5-4)를 Y 로 놓은 근사다. 각도·채도·밝기는 MesenCE 화면 덤프의 색 17가지에 맞춘 값."""
    import math
    hue, lum = c & 0x0F, c >> 4 & 3
    if hue >= 0x0E:
        return (0, 0, 0)
    if hue in (0x00, 0x0D):
        v = ((0.40, 0.68, 1.0, 1.0) if hue == 0 else (0.0, 0.0, 0.31, 0.62))[lum]
        return (int(v * 255),) * 3
    y = (0.12, 0.36, 0.62, 0.86)[lum]
    sat = 0.15 if lum == 3 else 0.30
    ang = math.radians(195 - 30 * hue)
    i, q = sat * math.cos(ang), sat * math.sin(ang)
    r, g, b = y + 0.956 * i + 0.621 * q, y - 0.272 * i - 0.647 * q, y - 1.106 * i + 1.703 * q
    return tuple(max(0, min(255, int(v * 255))) for v in (r, g, b))


def render_png(m, path, clock=0):
    """맵 전체를 블록 그림으로(확인용). 롬 그래픽이므로 work/ 아래에만 두고 커밋하지 않는다."""
    from PIL import Image
    pal = palette(m.prg, m.t, m.g or 0, m.k or 0, clock, m.f if m.buf is None else 0)
    colors = [[0x0F] + list(pal[3 * i:3 * i + 3]) for i in range(4)]
    im = Image.new('RGB', (m.w * 16, m.h * 16))
    px = im.load()
    chr_ = m.blocks['chr']
    for y in range(m.h):
        for x in range(m.w):
            b = m.block(x, y)
            cs = colors[m.blocks['pal'].get(b, 0)]
            for q, tn in enumerate(m.tiles(b)):
                if tn not in chr_:
                    continue
                bank, a = chr_[tn]
                o = bank * 0x4000 + (a & 0x3FFF)
                data = m.prg[o:o + 16]
                for r in range(8):
                    for cc in range(8):
                        v = (data[r] >> (7 - cc) & 1) | (data[r + 8] >> (7 - cc) & 1) << 1
                        px[x * 16 + (q & 1) * 8 + cc, y * 16 + (q >> 1) * 8 + r] = nes_rgb(cs[v])
    im.save(path)


def main():
    a = sys.argv
    if len(a) < 3:
        print(__doc__)
        sys.exit(2)
    prg = ines.prg(open(a[1], 'rb').read())
    if a[2] == 'compare':
        sys.exit(0 if compare(prg, a[3], a[4] if len(a) > 4 else None) else 1)
    if a[2] == 'json':
        out = a[3] if len(a) > 3 else os.path.join('work', 'dq4block.json')
        os.makedirs(os.path.dirname(out) or '.', exist_ok=True)
        d = export(prg, out)
        print(f"{out}: 맵 {len(d['maps'])}, 필드 {len(d['fields'])}, 속성 값 {len(d['effects'])}가지")
        return
    if a[2] == 'tables':
        show_tables(prg)
        return
    if a[2] == 'links':
        show_links(prg, int(a[3], 16), int(a[4], 16)) if len(a) > 4 else show_links(prg)
        return
    if a[2] == 'effects':
        show_effects(prg, int(a[3], 16), int(a[4], 16))
        return
    if a[2] == 'defs':
        t = int(a[3], 16)
        anim = anim_blocks(prg, t)
        for blk, d in defs(prg, t).items():
            if d is None:
                print(f'{blk:02X}: 없음')
                continue
            print(f"{blk:02X}: {d['a']:02X} {d['b']:02X} 뱅크 {d['bank']:02X} 타일 " + ' '.join(f'{x:04X}' for x in d['addrs'])
                  + f" 팔레트 {d['pal']} 종류 {d['kind']} 속성 {d['prop']:02X}"
                  + (' 애니메이션 1D:' + ','.join(f'{s:04X}' for s in anim[blk]) if blk in anim else ''))
        pal = palette(prg, t)
        print('팔레트(낮):', ' / '.join(pal[3 * i:3 * i + 3].hex(' ') for i in range(4)))
        return
    if a[2] == 'props':
        show_props(prg, '--maps' in a)
        return
    rest = [x for x in a[3:] if not x.startswith('--')]
    if a[2] == 'field':
        f = int(rest[0], 16) if rest else 0
        m, name = Map(prg, field=f), f'field{f}'
    else:
        g, k = int(a[2], 16), int(rest[0], 16)
        m, name = Map(prg, g, k), f'{g:02X}_{k:02X}'
    if '--nt' in a:
        show_nt(m)
    else:
        show_pass(m)
    if '--png' in a:
        os.makedirs('work', exist_ok=True)
        out = os.path.join('work', f'dq4block-{name}.png')
        render_png(m, out)
        print('그림:', out)


if __name__ == '__main__':
    main()
