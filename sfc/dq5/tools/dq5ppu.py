"""작은 SFC PPU 렌더러. MesenCE 상태 키(emu.getState() 의 ppu.*·dmaController.*)와 VRAM·CGRAM·OAM·WRAM 으로
한 화면을 그린다. 형식은 sfc/dq5/docs/dq5-graphics-format.md 의 「롬 코드로 그린 타이틀」.

BG 모드 0·1, 창 둘, 색 더하기·빼기(고정색·서브 화면), 밝기, OBJ, 그리고 WRAM 의 HDMA 표가 줄마다 바꾸는 BG 스크롤·창 자리를
흉내 낸다. 모드 7·모자이크·하이레스·인터레이스는 없다. HDMA 표와 간접 자료는 WRAM(뱅크 7E)에 있다고 본다.
쓰는 곳: dq5titlevm.py.
"""
import struct

import numpy as np


def load_state(path):
    """lua 가 emu.getState() 를 「키=값」 줄로 남긴 파일 → dict(문자열 값)."""
    d = {}
    for line in open(path):
        k, v = line.rstrip('\n').split('=', 1)
        d[k] = v
    return d


def b(v):
    return v == 'true'


def hdma_lines(wram, P, nlines=241):
    """HDMA 채널마다 줄별 (모드, B 버스 주소, 바이트들) 목록. 채널 설정은 P, 표는 WRAM."""
    en = int(P['dmaController.hdmaChannels'])
    regs = {}
    for ch in range(8):
        if not (en >> ch) & 1: continue
        k = f'dmaController.channel[{ch}].'
        mode = int(P[k + 'transferMode']); dest = int(P[k + 'destAddress'])
        ind = b(P[k + 'hdmaIndirectAddressing'])
        p = int(P[k + 'srcAddress'])
        nb = {0: 1, 1: 2, 2: 2, 3: 4, 4: 4}[mode]
        rd = lambda a: wram[a & 0xFFFF]
        vals = [None] * nlines
        lc = rd(p); p += 1; fin = lc == 0; addr = 0
        if ind and not fin: addr = rd(p) | rd(p + 1) << 8; p += 2
        do = True
        for line in range(nlines):
            if fin: break
            if do:
                if ind: data = [rd(addr + i) for i in range(nb)]; addr += nb
                else: data = [rd(p + i) for i in range(nb)]; p += nb
                vals[line] = (mode, dest, data)
            lc = (lc - 1) & 0xFF
            do = bool(lc & 0x80)
            if (lc & 0x7F) == 0:
                lc = rd(p); p += 1
                if lc == 0: fin = True
                elif ind: addr = rd(p) | rd(p + 1) << 8; p += 2
                do = True
        regs[ch] = vals
    return regs

def state_from(P, vram, cgram, oam, wram, hofs=1):
    """렌더러 입력. hofs 는 HDMA 첫 줄이 몇째 줄에 쓰이는지(MesenCE 와 맞춘 값 1)."""
    L = []
    for i in range(4):
        k = f'ppu.layers[{i}].'
        L.append(dict(map=int(P[k + 'tilemapAddress']) * 2,
                      chr=int(P[k + 'chrAddress']) * 2, dw=b(P[k + 'doubleWidth']), dh=b(P[k + 'doubleHeight']),
                      hs=int(P[k + 'hscroll']), vs=int(P[k + 'vscroll'])))
    R = dict(mode=int(P['ppu.bgMode']), bg3prio=b(P['ppu.mode1Bg3Priority']), layers=L, main=int(P['ppu.mainScreenLayers']), sub=int(P['ppu.subScreenLayers']),
             cmath=int(P['ppu.colorMathEnabled']), addsub=b(P['ppu.colorMathAddSubscreen']),
             subtract=b(P['ppu.colorMathSubtractMode']), halve=b(P['ppu.colorMathHalveResult']),
             fixed=int(P['ppu.fixedColor']), brightness=int(P['ppu.screenBrightness']), forcedBlank=b(P['ppu.forcedBlank']),
             win=[dict(act=[b(P[f'ppu.window[{w}].activeLayers[{i}]']) for i in range(6)], inv=[b(P[f'ppu.window[{w}].invertedLayers[{i}]']) for i in range(6)]) for w in range(2)],
             wmain=[b(P[f'ppu.windowMaskMain[{i}]']) for i in range(5)], wsub=[b(P[f'ppu.windowMaskSub[{i}]']) for i in range(5)],
             objbase=int(P['ppu.oamBaseAddress']) * 2, objofs=int(P['ppu.oamAddressOffset']))
    H = hdma_lines(wram, P)
    # HDMA 쓰기를 줄마다 누적해 그 줄의 스크롤·창 자리를 만든다
    hs = [l['hs'] for l in L]; vs = [l['vs'] for l in L]
    table = []
    cur_h = list(hs); cur_v = list(vs)
    cur_w = [[int(P[f'ppu.window[{w}].left']), int(P[f'ppu.window[{w}].right'])] for w in range(2)]
    for line in range(241):
        for ch, vals in H.items():
            v = vals[line - hofs] if 0 <= line - hofs < len(vals) else None
            if not v: continue
            mode, dest, data = v
            if dest in (0x0D, 0x0F, 0x11, 0x13) and mode == 2:
                cur_h[(dest - 0x0D) // 2] = (data[0] | data[1] << 8) & 0x3FF
            elif dest in (0x0E, 0x10, 0x12, 0x14) and mode == 2:
                cur_v[(dest - 0x0E) // 2] = (data[0] | data[1] << 8) & 0x3FF
            elif 0x26 <= dest <= 0x29:
                for i, x in enumerate(data):
                    r = dest + (i if mode in (1, 3, 4) else 0) - 0x26
                    if r < 4: cur_w[r // 2][r % 2] = x
        table.append(dict(hs=list(cur_h), vs=list(cur_v), win=[list(w) for w in cur_w]))
    return dict(vram=vram, cgram=cgram, oam=oam,
                regs=R, lines=lambda y: table[min(y, 240)])

def T(x):
    return 'true' if x else 'false'


def apply(P, writes, latch):
    """PPU·DMA 레지스터 쓰기 (주소, 값) 를 상태 P 에 반영. latch 는 BG 스크롤 레지스터가 함께 쓰는 앞 바이트 [값]."""
    for a, v in writes:
        if a == 0x2100:
            P['ppu.forcedBlank'] = T(v & 0x80); P['ppu.screenBrightness'] = str(v & 15)
        elif a == 0x2101:
            P['ppu.oamBaseAddress'] = str((v & 7) << 13); P['ppu.oamAddressOffset'] = str((((v >> 3) & 3) + 1) << 12)
        elif a == 0x2105:
            P['ppu.bgMode'] = str(v & 7); P['ppu.mode1Bg3Priority'] = T(v & 8)
        elif 0x2107 <= a <= 0x210A:
            k = f'ppu.layers[{a - 0x2107}].'
            P[k + 'tilemapAddress'] = str((v & 0xFC) << 8); P[k + 'doubleWidth'] = T(v & 1); P[k + 'doubleHeight'] = T(v & 2)
        elif a in (0x210B, 0x210C):
            i = (a - 0x210B) * 2
            P[f'ppu.layers[{i}].chrAddress'] = str((v & 0xF) << 12); P[f'ppu.layers[{i + 1}].chrAddress'] = str((v >> 4) << 12)
        elif 0x210D <= a <= 0x2114:
            i, vert = (a - 0x210D) // 2, (a - 0x210D) & 1
            k = f'ppu.layers[{i}].' + ('vscroll' if vert else 'hscroll')
            cur = int(P[k])
            new = (v << 8) | latch[0] if vert else (v << 8) | (latch[0] & ~7) | ((cur >> 8) & 7)
            P[k] = str(new & 0x3FF); latch[0] = v
        elif 0x2123 <= a <= 0x2125:
            for j in range(2):
                layer = (a - 0x2123) * 2 + j
                nib = (v >> (4 * j)) & 15
                if layer > 5: continue
                P[f'ppu.window[0].invertedLayers[{layer}]'] = T(nib & 1); P[f'ppu.window[0].activeLayers[{layer}]'] = T(nib & 2)
                P[f'ppu.window[1].invertedLayers[{layer}]'] = T(nib & 4); P[f'ppu.window[1].activeLayers[{layer}]'] = T(nib & 8)
        elif 0x2126 <= a <= 0x2129:
            r = a - 0x2126
            P[f'ppu.window[{r // 2}].' + ('right' if r & 1 else 'left')] = str(v)
        elif a == 0x212C: P['ppu.mainScreenLayers'] = str(v & 0x1F)
        elif a == 0x212D: P['ppu.subScreenLayers'] = str(v & 0x1F)
        elif a in (0x212E, 0x212F):
            for i in range(5): P[f"ppu.windowMask{'Main' if a == 0x212E else 'Sub'}[{i}]"] = T(v & (1 << i))
        elif a == 0x2130:
            P['ppu.colorMathAddSubscreen'] = T(v & 2)
        elif a == 0x2131:
            P['ppu.colorMathEnabled'] = str(v & 0x3F); P['ppu.colorMathHalveResult'] = T(v & 0x40); P['ppu.colorMathSubtractMode'] = T(v & 0x80)
        elif a == 0x2132:
            c = int(P['ppu.fixedColor'])
            for bit, sh in ((0x20, 0), (0x40, 5), (0x80, 10)):
                if v & bit: c = (c & ~(31 << sh)) | ((v & 31) << sh)
            P['ppu.fixedColor'] = str(c)
        elif a == 0x420C:
            P['dmaController.hdmaChannels'] = str(v)
        elif 0x4300 <= a <= 0x437F and (a & 0xF) <= 7:
            k = f'dmaController.channel[{(a >> 4) & 7}].'; r = a & 0xF
            if r == 0:
                P[k + 'transferMode'] = str(v & 7); P[k + 'fixedTransfer'] = T(v & 8); P[k + 'decrement'] = T(v & 0x10)
                P[k + 'hdmaIndirectAddressing'] = T(v & 0x40); P[k + 'invertDirection'] = T(v & 0x80)
            elif r == 1: P[k + 'destAddress'] = str(v)
            elif r == 2: P[k + 'srcAddress'] = str(int(P[k + 'srcAddress']) & 0xFF00 | v)
            elif r == 3: P[k + 'srcAddress'] = str(int(P[k + 'srcAddress']) & 0xFF | v << 8)
            elif r == 4: P[k + 'srcBank'] = str(v)
            elif r == 7: P[k + 'hdmaBank'] = str(v)

def c15(c):
    return ((c & 31), (c >> 5) & 31, (c >> 10) & 31)

def tile2(vram, base, t, row):
    a = (base + t * 16 + row * 2) & 0xFFFF
    p0, p1 = vram[a], vram[a + 1]
    return [((p0 >> (7 - x)) & 1) | (((p1 >> (7 - x)) & 1) << 1) for x in range(8)]

def tile4(vram, base, t, row):
    a = (base + t * 32 + row * 2) & 0xFFFF
    p = [vram[a], vram[a + 1], vram[a + 16], vram[a + 17]]
    return [sum(((p[b] >> (7 - x)) & 1) << b for b in range(4)) for x in range(8)]

def bg_line(vram, L, n, y, hs, vs, mode=0):
    """returns list of 256 (color_index_in_cgram or 0, prio) for mode-0 BG n"""
    out = [(0, 0)] * 256
    yy = (y + vs) & 0x3FF
    w64, h64 = L['dw'], L['dh']
    for sx in range(256):
        xx = (sx + hs) & 0x3FF
        tx, ty = (xx >> 3) & (63 if w64 else 31), (yy >> 3) & (63 if h64 else 31)
        m = L['map'] + ((ty & 31) * 32 + (tx & 31)) * 2
        if tx >= 32: m += 0x800
        if ty >= 32: m += 0x800 * (2 if w64 else 1)
        w = vram[m & 0xFFFF] | vram[(m + 1) & 0xFFFF] << 8
        t, pal, pr, hf, vf = w & 0x3FF, (w >> 10) & 7, (w >> 13) & 1, w & 0x4000, w & 0x8000
        r = yy & 7
        if vf: r = 7 - r
        bpp4 = mode == 1 and n < 2
        px = tile4(vram, L['chr'], t, r) if bpp4 else tile2(vram, L['chr'], t, r)
        c = px[7 - (xx & 7) if hf else (xx & 7)]
        if c:
            out[sx] = ((pal * 16 + c) if bpp4 else ((n * 32 if mode == 0 else 0) + pal * 4 + c), pr)
    return out

def render(st, size=(256, 239), yofs=1):
    """state_from 의 결과를 RGB 배열(높이 size[1], 너비 256)로. 색은 MesenCE 와 같게 v<<3 | v>>2."""
    vram, cg, oam, R = st['vram'], st['cgram'], st['oam'], st['regs']
    pal = [struct.unpack_from('<H', cg, i * 2)[0] for i in range(256)]
    img = np.zeros((size[1], 256, 3), np.uint8)
    if R['forcedBlank']:
        return img
    # OBJ list
    objs = []
    small, large = R.get('objsizes', (8, 16))
    for k in range(128):
        x, y, t, a = oam[4 * k:4 * k + 4]
        hi = (oam[512 + k // 4] >> ((k % 4) * 2)) & 3
        x |= (hi & 1) << 8
        if x >= 256: x -= 512
        sz = large if hi & 2 else small
        objs.append((k, x, y, t | (a & 1) << 8, a, sz))
    bright = R['brightness']
    for row in range(size[1]):
        y = row + yofs  # scanline
        lines = st['lines'](y)
        layers = []
        for n in range(4):
            L = R['layers'][n]
            if not ((R['main'] | R['sub']) >> n) & 1:
                layers.append(None); continue
            layers.append(bg_line(vram, L, n, y, lines['hs'][n], lines['vs'][n], R['mode']) if R['mode'] == 0 or n < 3 else None)
        # OBJ line (first in OAM order wins)
        objl = [None] * 256
        if (R['main'] | R['sub']) & 16:
            for (k, x, oy, t, a, sz) in objs:
                dy = (y - 1 - oy) & 0xFF  # OBJ drawn one line below
                if dy >= sz: continue
                vf, hf = a & 0x80, a & 0x40
                r = sz - 1 - dy if vf else dy
                for cx in range(sz):
                    sx = x + cx
                    if not 0 <= sx < 256 or objl[sx] is not None: continue
                    c2 = sz - 1 - cx if hf else cx
                    tt = (t & 0x100) | ((((t & 0xF0) + (r >> 3) * 16) & 0xF0) | ((t + (c2 >> 3)) & 0x0F))
                    base = R['objbase'] + ((R['objofs'] * 2) if tt & 0x100 else 0)
                    c = tile4(vram, base, tt & 0xFF, r & 7)[c2 & 7]
                    if c:
                        objl[sx] = (128 + ((a >> 1) & 7) * 16 + c, (a >> 4) & 3)
        wl = lines['win']
        def inwin(i, sx):
            r = False
            for w in range(2):
                if R['win'][w]['act'][i]:
                    a = wl[w][0] <= sx <= wl[w][1]
                    if R['win'][w]['inv'][i]: a = not a
                    r = r or a
            return r
        for sx in range(256):
            mm = R['main'] & ~sum((1 << i) for i in range(5) if R['wmain'][i] and inwin(i, sx))
            sm = R['sub'] & ~sum((1 << i) for i in range(5) if R['wsub'][i] and inwin(i, sx))
            def top(mask):
                b = [layers[n][sx] if layers[n] and (mask >> n) & 1 else (0, 0) for n in range(4)]
                o = objl[sx] if (mask & 16) and objl[sx] else None
                if R['mode'] == 0:
                    order = [('o', 3), (0, 1), (1, 1), ('o', 2), (0, 0), (1, 0), ('o', 1), (2, 1), (3, 1), ('o', 0), (2, 0), (3, 0)]
                else:
                    order = ([(2, 1)] if R['bg3prio'] else []) + [('o', 3), (0, 1), (1, 1), ('o', 2), (0, 0), (1, 0), ('o', 1)] + ([] if R['bg3prio'] else [(2, 1)]) + [('o', 0), (2, 0)]
                for who, p in order:
                    if who == 'o':
                        if o and o[1] == p: return ('o', o[0])
                    elif b[who][0] and b[who][1] == p:
                        return (who, b[who][0])
                return ('bd', 0)
            mw, mc = top(mm)
            col = c15(pal[mc])
            en = R['cmath']
            idx = {'o': 4, 'bd': 5}.get(mw, mw)
            use = (en >> idx) & 1 and not (mw == 'o' and mc < 192)
            if use:
                if R['addsub']:
                    sw, sc = top(sm)
                    s = c15(pal[sc]) if sw != 'bd' else c15(R['fixed'])
                else:
                    s = c15(R['fixed'])
                if R['subtract']:
                    col = tuple(max(0, a - b) for a, b in zip(col, s))
                else:
                    col = tuple(min(31, a + b) for a, b in zip(col, s))
                if R['halve'] and sw != 'bd':
                    col = tuple(v >> 1 for v in col)
            if bright < 15:
                col = tuple(v * (bright + 1) // 16 for v in col)
            img[row, sx] = [(v << 3) | (v >> 2) for v in col]
    return img
