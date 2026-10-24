"""DQ4(FC) 맵 블록 → 8×8 타일 4개·팔레트·통행. 형식은 docs/dq4-block-format.md.

사용:
  python tools/dq4block.py rom/dq4.nes defs T              맵 종류 T($0028)의 블록 정의·애니메이션·낮 팔레트
  python tools/dq4block.py rom/dq4.nes G K [--png]         맵의 통행 지도(텍스트). --png 는 work/ 에 렌더링
  python tools/dq4block.py rom/dq4.nes G K --nt            맵 전체의 nametable 타일 번호 배열
  python tools/dq4block.py rom/dq4.nes field [F] [--png]   필드 F(기본 0)의 통행 지도
  python tools/dq4block.py rom/dq4.nes props [--maps]      롬 전체 맵·필드의 속성 값별 뜻·맵 수·칸 수(--maps 는 맵마다)
  python tools/dq4block.py rom/dq4.nes compare DIR [PREFIX] seq.lua 의 end.* (또는 blockload.lua 의 PREFIX.*) 덤프와 비교

근거 루틴: 08:$84E9(블록 표 올리기), $8055(맵 종류 → 블록 표), $8473(블록 하나), $80D5(타일 모양 레코드),
$823D(CHR 타일 번호 나누기, $7700 중복 목록), $83BD·0F:$C7E1(CHR 뱅크 0C·0D 에서 16바이트 복사),
$853E(블록 20·21), $8710(빈 칸에 FC~FF), 1E:$A046(맵에 쓰인 블록 표시), 1E:$9F47(벽 아래 그늘 블록 바꾸기),
0F:$D4E6(다른 구역은 블록 20·21 로), $D44C(맵 밖 블록), $EB23(블록 → 타일 4개), 0F:$D088(통행).
"""
import os
import sys

from kr_patch.fc import ines

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
        m, self.w, self.h, raw = dq4map.load(prg, g, k)
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


MARKS = 'GHIJKLMNOPQRSTUVWXYZ'
BLOCKED = 'abcdefghijklmnopqrstuvwxyz'

# 속성($6F40) 값 → 뜻. 근거는 docs/dq4-block-format.md 의 「속성 값」 표.
KINDS = {
    0x00: '바닥',
    0x01: '독늪(걸음마다 HP 1)',
    0x02: '독늪류(1E:$9956 이 01 과 함께 봄)',
    0x04: '보물상자',
    0x05: '1E:$8676 로 감(뜻 모름)',
    0x06: '입구·출구 검사',
    0x07: '입구·출구 검사',
    0x08: '계단',
    0x09: '계단',
    0x0A: '1B:$A10F',
    0x0B: '1E:$8676 로 감(뜻 모름)',
    0x0C: '입구·출구 검사',
    0x0F: '스위치(1E:$8700)',
    0x10: '미끄러지는 바닥',
    0x11: '미끄러지는 바닥',
    0x12: '미끄러지는 바닥',
    0x13: '미끄러지는 바닥',
    0x24: '걸어서·배로 감',
    0x25: '입구·출구 검사',
    0x26: '입구·출구 검사',
    0x80: '벽',
    0x83: '물(배로만)',
    0xA0: '문',
    0xA7: '카운터(너머로 말 걸기)',
    0xB0: '막힘(그룹 3F 특수)',
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


def all_maps(prg):
    """롬의 맵 269개와 필드 3개를 (이름, Map) 으로."""
    for g, k, *_ in dq4map.maps(prg):
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
