"""DQ5(SFC) 그래픽을 롬에서 PNG 로 뽑는다. 형식은 sfc/dq5/docs/dq5-graphics-format.md 의 「그래픽 내보내기와 갤러리」.

스프라이트를 새로 그릴 때 원작 그림을 같은 배율로 찾아보려는 용도다. 디코더는 다른 도구의 것을 그대로 쓴다.
OUT 아래 분류 폴더는 에셋 저장소(sfc-dq4-assets)의 공통 규칙을 따른다.

  maps/          실내 맵 346개와 그룹 $50 이상 18개(맵별 루틴 15:F907 반영). <BC>-<BD>[-마을 이름][-변형].png,
                 변형 annot(인물·출구·상자·タンス·발밑 표시), night(밤 팔레트), setNN(플래그 팔레트 세트 01:9771)
  field/         세계 지도 셋. field0(낮)·field0-night·field0-<포인터>(다른 시간대 팔레트)·field1·field2·fieldN-annot(입구)
  monsters/      전투 몬스터 236마리 <번호>-<이름>.png (dq5mongfx)
  battlebg/      전투 배경 49개 × 세계($1949) 셋 <번호>[-<세계>].png (dq5battlebg)
  gfx/blocks/    CHR 뱅크(chrNN-color·-gray), 맵마다 쓰는 블록(maps/), 필드 블록·타일
  gfx/screens/   창·메뉴 BG3 타일(04:E528)과 창 견본
  gfx/anim/      필드의 움직이는 타일(타일 454~459 8벌, 물 타일 돌리기, 물결 팔레트) 시트와 GIF
  gfx/font.png   폰트 글자 0x3DB 개

맵·지도·몬스터·배경은 1배, 타일 시트만 2배다. 분류 폴더마다 index.json(항목 목록)과 SOURCE.txt(만든 커밋·명령·롬)를 남긴다.
롬에서 뽑은 그림이므로 공개 저장소에 커밋하지 않는다.

사용:
  python sfc/dq5/tools/dq5gfx.py rom/dq5.sfc [--out work/dq5gfx] [--only maps,field] [--maps 02/06,51/50]
  python sfc/dq5/tools/dq5gfx.py rom/dq5.sfc --check work/d/f00005 06/03 [--set 26] [--night]
--check 는 sfc/dq5/tools/lua/dq5gfxdump.lua 로 그 맵에서 덤프한 VRAM·CGRAM 으로 BG2 위에 BG1 을 겹친 화면을 맵 그림과 비교한다.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(__file__))
from dq5exit import apply_hook, exit_attrs  # noqa: E402
from dq5map import (CHR_PALETTE, GROUP_TABLE, HIGH_CHR_PALETTE, PALETTES, PALSET_LISTS, Decoder,  # noqa: E402
                    Rom, chr_pixels, lorom, map_cgram, map_pointer)

SLOT = 0xBE
# 01:9771: 맵을 들어갈 때 10:DE0B 로 고른 팔레트 세트를 플래그에 따라 바꾸는 표. [BC][BD|FF][플래그|FF][마스크][세트], FF 로 끝.
# 플래그 bit7 이 0 이면 7E:2190+번호 & 마스크가 켜졌을 때, 1 이면 꺼졌을 때 그 세트를 10:DDCF 로 다시 불러온다.
PALSET_FLAGS = 0x2A8690
# 0F:8ED7 그룹 포인터 54개. 마지막 그룹은 표 바로 앞에서 끝난다.
GROUPS = 0x36
# 그룹 $50 이상: ($BC, $BD 개수). docs/dq5-map-format.md 「그룹 $50 이상」.
HIGH_MAPS = ((0x50, 2), (0x51, 8), (0x52, 1), (0x53, 3), (0x54, 4))
# 01:A16B: [하한 16비트][포인터 색인] 10개를 뒤에서부터 보아 $075E 이상인 첫 항목. 01:A189 포인터 → 2·3번 줄 색 1~15.
FIELD_TIME = 0x01A16B
FIELD_TIME_PTRS = 0x01A189
# 세계 1·2 의 2·3번 줄(01:A6A3).
FIELD_WORLD_ROWS = (None, 0x01A199, 0x01A3B5)
# 필드 4번 줄은 팔레트 세트 목록의 $34 번(10:EC48), 세계 0 은 색 1~3 을 01:A0F6 + $1961*6 의 물결 색으로 바꾼다(10단계).
FIELD_ROW4 = PALETTES + 0x34 * 32
FIELD_WAVE = 0x01A0F6
WAVE_STEPS = 10
# 04:E17D: BG3 창·메뉴 타일. 04:E528 에서 1bpp 138개(둘째 평면은 FF)를 타일 1 부터, 이어서 2bpp 11개를 올린다.
UI_TILES = 0x04E528
UI_1BPP, UI_2BPP = 0x8A, 0x0B
# 04:9870: CGRAM 0번 줄(BG3 2bpp 팔레트 넷) 32바이트.
UI_PALETTE = 0x0498D7
# 2B:8000: 필드 타일 454~459(VRAM 워드 3C60)의 8벌을 1E:D0FF 의 RLE(01:A64F 와 같은 꼴)로 7E:C800 에 푼다.
FIELD_ANIM = 0x1ED0FF
FIELD_ANIM_TILE, FIELD_ANIM_COUNT, FIELD_ANIM_SETS = 0x1C6, 6, 8
# 25:85D5: ルーラ 목적지의 맵 그룹 22개. 이름은 이름 표 0B(23:D5F3) 의 같은 순번.
RURA_GROUPS, RURA_COUNT, TOWN_NAMES = 0x2585D5, 22, 0x0B


def rgb(c):
    # 5비트 → 8비트는 MesenCE 화면과 같게 (v << 3) | (v >> 2).
    return tuple((v << 3) | (v >> 2) for v in (c & 31, (c >> 5) & 31, (c >> 10) & 31))


def cgram_colors(cg):
    return [rgb(cg[i * 2] | cg[i * 2 + 1] << 8) for i in range(len(cg) // 2)]


def planar(t):
    """4bpp 타일 32바이트 → 8x8 색 번호."""
    return [[(t[y * 2] >> (7 - x) & 1) | (t[y * 2 + 1] >> (7 - x) & 1) << 1
             | (t[16 + y * 2] >> (7 - x) & 1) << 2 | (t[17 + y * 2] >> (7 - x) & 1) << 3
             for x in range(8)] for y in range(8)]


def tile_image(px, colors, flip_h=False, flip_v=False):
    """색 번호 8x8 → RGBA(0 번 색은 투명)."""
    img = Image.new('RGBA', (8, 8), (0, 0, 0, 0))
    p = img.load()
    for y in range(8):
        for x in range(8):
            v = px[7 - y if flip_v else y][7 - x if flip_h else x]
            if v:
                p[x, y] = colors[v] + (255,)
    return img


def scaled(img, scale):
    return img.resize((img.width * scale, img.height * scale), Image.NEAREST) if scale > 1 else img


def sheet(cells, cols, cell_w, cell_h, labels=None, bg=(32, 32, 40), pad=1, label_h=0, below=False):
    """같은 크기 그림을 격자로. labels 를 주면 칸 위(below 면 아래)에 작은 글씨."""
    rows = (len(cells) + cols - 1) // cols
    W, H = cols * (cell_w + pad) + pad, rows * (cell_h + label_h + pad) + pad
    out = Image.new('RGB', (W, H), bg)
    d = ImageDraw.Draw(out)
    for i, c in enumerate(cells):
        x, y = pad + i % cols * (cell_w + pad), pad + i // cols * (cell_h + label_h + pad)
        if labels:
            d.text((x, y + (cell_h if below else 0)), labels[i], fill=(200, 200, 120))
        if c is not None:
            out.paste(c, (x, y + (0 if below else label_h)), c if c.mode == 'RGBA' else None)
    return out


# ---------------------------------------------------------------- 실내 맵

def map_ids(rom):
    """실내 맵 346개와 그룹 $50 이상 18개의 ($BC, $BD)."""
    ptr = [rom.u16(GROUP_TABLE + g * 2) for g in range(GROUPS)] + [GROUP_TABLE & 0xFFFF]
    out = [(g, b) for g in range(GROUPS) for b in range((ptr[g + 1] - ptr[g]) // 3)]
    return out + [(g, 0x50 + b) for g, n in HIGH_MAPS for b in range(n)]


class TileCache:
    """(CHR, 팔레트 줄, 반전) → 8x8 RGBA. 맵 하나의 팔레트 안에서만 쓴다."""

    def __init__(self, rom, high, colors):
        self.rom, self.high, self.colors, self.px, self.img = rom, high, colors, {}, {}

    def get(self, chr_id, pal, fh, fv):
        k = (chr_id, pal, fh, fv)
        if k not in self.img:
            if chr_id not in self.px:
                self.px[chr_id] = chr_pixels(self.rom, chr_id, self.high)
            self.img[k] = tile_image(self.px[chr_id], self.colors[pal * 16:pal * 16 + 16], fh, fv)
        return self.img[k]


def palette_overrides(rom):
    """01:9771 표: [(BC, BD 또는 None, 플래그 번호, 마스크, 세트)]."""
    out, a = [], PALSET_FLAGS
    while rom.u8(a) != 0xFF:
        e = [rom.u8(a + i) for i in range(5)]
        out.append((e[0], None if e[1] == 0xFF else e[1], e[2], e[3], e[4]))
        a += 5
    return out


def set_cgram(rom, s, alt=False):
    """map_cgram 과 같되 팔레트 세트 번호를 바로 준다(10:DDCF)."""
    lst = 0x100000 | rom.u16(PALSET_LISTS + s * 4 + (2 if alt else 0))
    cg = bytearray(0x200)
    for r in range(7):
        o = lorom(PALETTES + (rom.u16(lst + r * 2) & 0x7FF) * 32)
        cg[0x20 + r * 32:0x40 + r * 32] = rom.d[o:o + 32]
    for r in range(7, 1, -1):
        if cg[r * 32] | cg[r * 32 + 1]:
            cg[0:2] = cg[r * 32:r * 32 + 2]
            break
    return bytes(cg)


def decode_map(rom, bc, bd):
    high = bc >= 0x50
    dec = Decoder(rom, SLOT, high)
    trace = []
    w, h, buf, _ = dec.decode(map_pointer(rom, bc, bd), trace=trace)
    buf = bytearray(buf)
    apply_hook(rom, bc, bd, buf, w)
    blocks = sorted({args[0] for *_, op, args in trace if op == 'block'}
                    | ({(rom.u8(map_pointer(rom, bc, bd) + 7) & 7) << 8 | rom.u8(map_pointer(rom, bc, bd) + 8)}
                       if rom.u8(map_pointer(rom, bc, bd) + 7) & 0x80 else set()))
    return dec, w, h, buf, blocks


def draw_cells(rom, dec, w, h, buf, cgram, layers=(2, 5)):
    colors = cgram_colors(cgram)
    slot_chr = {v & 0x3FF: k for k, v in dec.chr_map.items()}
    tc = TileCache(rom, dec.high, colors)
    img = Image.new('RGB', (w * 8, h * 8), colors[0])
    for layer in layers:
        for cell in range(w * h):
            o = cell * 8 + layer
            word = buf[o] | buf[o + 1] << 8
            chr_id = slot_chr.get(word & 0x3FF) if word else None
            if chr_id is None:
                continue
            t = tc.get(chr_id, (word >> 10) & 7, bool(word & 0x4000), bool(word & 0x8000))
            img.paste(t, (cell % w * 8, cell // w * 8), t)
    return img


def block_image(rom, dec, n, colors, tc):
    """블록 하나를 그 자리 그대로(위층 줄도 한 그림에)."""
    h, w, upper, attr, rows = dec.load_block(n)
    slot_chr = {v & 0x3FF: k for k, v in dec.chr_map.items()}
    img = Image.new('RGBA', (w * 8, h * 8), colors[0] + (255,))
    for r, row in enumerate(rows):
        for c, (_, word) in enumerate(row):
            t = tc.get(slot_chr[word & 0x3FF], (word >> 10) & 7, bool(word & 0x4000), bool(word & 0x8000))
            img.paste(t, (c * 8, r * 8), t)
    return img


# ---------------------------------------------------------------- 필드

def field_time_sets(rom):
    """세계 0 의 2·3번 줄 8벌(01:A189 포인터 표 순서): [(포인터, [그 벌을 고르는 $075E 하한…])]. 01:A132."""
    entries = [(rom.u16(FIELD_TIME + i * 3), rom.u8(FIELD_TIME + i * 3 + 2)) for i in range(10)]
    ptrs = [rom.u16(FIELD_TIME_PTRS + i * 2) for i in range(8)]
    return [(p, sorted(lo for lo, idx in entries if idx == i * 2)) for i, p in enumerate(ptrs)]


def field_cgram(rom, world, rows23=None, wave=0, base=(0x01, 0x00)):
    """필드 CGRAM 을 롬에서. 1·5~7번 줄은 마지막 맵(base)의 세트, 2·3번 줄은 시간대·세계, 4번 줄은 10:EC48(+물결)."""
    cg = bytearray(map_cgram(rom, *base))
    src = rows23 if world == 0 else FIELD_WORLD_ROWS[world]
    o = lorom(0x010000 | src)
    for r, k in ((2, 0), (3, 30)):
        cg[r * 32 + 2:r * 32 + 32] = rom.d[o + k:o + k + 30]
    o4 = lorom(FIELD_ROW4)
    cg[4 * 32:5 * 32] = rom.d[o4:o4 + 32]
    if world == 0:
        w = lorom(FIELD_WAVE + wave * 6)
        cg[4 * 32 + 2:4 * 32 + 8] = rom.d[w:w + 6]
    return bytes(cg)


def field_tiles(rom):
    """필드 타일 512개의 8x8 색 번호. 팔레트는 층마다 다르므로(00:BBAC) 칠하는 것은 부르는 쪽."""
    from dq5field import field_chr
    chrs = field_chr(rom)
    return [planar(chrs[i * 32:i * 32 + 32]) for i in range(512)]


def field_block_images(rom, cgram, tiles, layers=('lower', 'upper')):
    from dq5field import BLOCK_LOWER, BLOCK_UPPER, block_tiles, tile_word
    colors = cgram_colors(cgram)
    cache = {}
    out = []
    for m in range(512):
        img = Image.new('RGBA', (16, 16), colors[0] + (255,))
        for upper, table in ((False, BLOCK_LOWER), (True, BLOCK_UPPER)):
            if ('upper' if upper else 'lower') not in layers:
                continue
            for q, t in enumerate(block_tiles(rom, table, m)):
                word = tile_word(rom, t, upper)
                k = (word & 0x3FF, (word >> 10) & 7)
                if k not in cache:
                    cache[k] = tile_image(tiles[k[0]], colors[k[1] * 16:k[1] * 16 + 16])
                img.paste(cache[k], ((q & 1) * 8, (q >> 1) * 8), cache[k])
        out.append(img)
    return out


def world_image(rom, world, blocks):
    from dq5field import WORLDS, block_number, rle
    src_w, src_e = WORLDS[world]
    wmap, _ = rle(rom, src_w)
    hib, _ = rle(rom, src_e)
    size = 256 if world == 0 else 128
    img = Image.new('RGB', (size * 16, size * 16))
    for by in range(size):
        for bx in range(size):
            img.paste(blocks[block_number(wmap, hib, bx, by)], (bx * 16, by * 16))
    return img


# ---------------------------------------------------------------- 몬스터·폰트

# ---------------------------------------------------------------- 창·움직이는 타일

def ui_tiles(rom):
    """BG3 타일 0~149 의 2bpp 바이트(VRAM 워드 $1000 또는 $4000 부터 올라가는 그대로). 타일 0 은 0."""
    out = bytearray(16)
    o = lorom(UI_TILES)
    for t in range(UI_1BPP):
        for r in range(8):
            out += bytes([rom.d[o + t * 8 + r], 0xFF])
    o += UI_1BPP * 8
    for t in range(UI_2BPP):
        for r in range(8):
            out += bytes([rom.d[o + t * 16 + r], rom.d[o + t * 16 + 8 + r]])
    return bytes(out)


# 화면에서 본 창 타일맵(배 선실 덤프의 BG3): 8C 모서리, 8D 위 테두리, 8E 옆 테두리, 8F·90 가로줄, 01 빈칸. 40 = 좌우, 80 = 상하 반전.
UI_SAMPLE = (
    (0x08C, 0x08D, 0x08D, 0x08D, 0x08D, 0x08D, 0x08D, 0x48C),
    (0x08E, 0x010, 0x010, 0x010, 0x010, 0x001, 0x001, 0x48E),
    (0x08F, 0x090, 0x090, 0x090, 0x090, 0x090, 0x090, 0x48F),
    (0x08E, 0x00C, 0x001, 0x004, 0x006, 0x001, 0x001, 0x48E),
    (0x08E, 0x00D, 0x001, 0x001, 0x002, 0x001, 0x001, 0x48E),
    (0x08E, 0x087, 0x085, 0x001, 0x003, 0x001, 0x001, 0x48E),
    (0x88C, 0x88D, 0x88D, 0x88D, 0x88D, 0x88D, 0x88D, 0xC8C),
)


def field_anim_sets(rom):
    """타일 454~459 의 8벌: [벌][타일] = 32바이트."""
    from dq5field import rle
    data, _ = rle(rom, FIELD_ANIM)
    n = FIELD_ANIM_COUNT * 32
    return [[data[k * n + t * 32:k * n + t * 32 + 32] for t in range(FIELD_ANIM_COUNT)] for k in range(FIELD_ANIM_SETS)]


def rotate_pair(a, b, k):
    """01:C790 이 하는 일: 이웃한 두 타일의 줄마다(평면마다) 16비트를 k 픽셀 오른쪽으로 돌린다. 세계 1·2 는 왼쪽."""
    oa, ob = bytearray(32), bytearray(32)
    for i in range(32):
        v = a[i] << 8 | b[i]
        v = (v >> k | v << (16 - k)) & 0xFFFF
        oa[i], ob[i] = v >> 8, v & 0xFF
    return bytes(oa), bytes(ob)


# ---------------------------------------------------------------- 덤프한 VRAM 에서 BG 그리기

def read_ppu(path):
    """dq5gfxdump.lua 의 .ppu.txt → {키: 값}."""
    out = {}
    for line in open(path):
        k, _, v = line.strip().partition('=')
        out[k] = int(v) if v.lstrip('-').isdigit() else v
    return out


def chr_2bpp(t):
    return [[(t[y * 2] >> (7 - x) & 1) | (t[y * 2 + 1] >> (7 - x) & 1) << 1 for x in range(8)] for y in range(8)]


def bg_layer(vram, cgram, ppu, layer, bpp=None, transparent=False):
    """BG 하나의 타일맵 전체(32x32·64x32·32x64·64x64 칸)를 덤프한 VRAM·CGRAM 으로 그린다. 스크롤은 무시한다.
    bpp 를 안 주면 모드 1 기준(BG1·BG2 4bpp, BG3 2bpp)."""
    pre = f'ppu.layers[{layer}].'
    tm, cb = ppu[pre + 'tilemapAddress'] * 2, ppu[pre + 'chrAddress'] * 2
    dw, dh = ppu[pre + 'doubleWidth'] == 'true', ppu[pre + 'doubleHeight'] == 'true'
    bpp = bpp or (2 if layer == 2 else 4)
    colors = cgram_colors(cgram)
    W, H = 64 if dw else 32, 64 if dh else 32
    img = Image.new('RGBA', (W * 8, H * 8), (0, 0, 0, 0) if transparent else colors[0] + (255,))
    cache = {}
    for ty in range(H):
        for tx in range(W):
            screen = (tx >> 5) + ((ty >> 5) << (1 if dw else 0))
            o = (tm + screen * 0x800 + ((ty & 31) * 32 + (tx & 31)) * 2) & 0xFFFF
            word = vram[o] | vram[o + 1] << 8
            k = word & 0xDFFF
            if k not in cache:
                tile = word & 0x3FF
                a = (cb + tile * 8 * bpp) & 0xFFFF
                px = planar(vram[a:a + 32]) if bpp == 4 else chr_2bpp(vram[a:a + 16])
                pal = (word >> 10) & 7
                cache[k] = tile_image(px, colors[pal * (1 << bpp):pal * (1 << bpp) + (1 << bpp)],
                                      bool(word & 0x4000), bool(word & 0x8000))
            img.paste(cache[k], (tx * 8, ty * 8), cache[k])
    return img


def dump_screen(prefix):
    """dq5gfxdump.lua 덤프(prefix = 경로/fNNNNN)로 BG2 위에 BG1 을 겹치고 BG1 스크롤만큼 자른 256x224 화면."""
    vram, cgram = open(prefix + '.vram', 'rb').read(), open(prefix + '.cgram', 'rb').read()
    ppu = read_ppu(prefix + '.ppu.txt')
    comp = bg_layer(vram, cgram, ppu, 1)
    hi = bg_layer(vram, cgram, ppu, 0, transparent=True)
    comp.paste(hi, (0, 0), hi)
    W, H = comp.size
    hs, vs = ppu['ppu.layers[0].hscroll'] % W, ppu['ppu.layers[0].vscroll'] % H
    tiled = Image.new('RGB', (W * 2, H * 2))
    for x in (0, W):
        for y in (0, H):
            tiled.paste(comp, (x, y))
    return tiled.crop((hs, vs, hs + 256, vs + 224))


def match_screen(full, scr):
    """맵 그림 full 에서 화면 scr 이 가장 잘 맞는 자리 (x, y, 같은 픽셀, 맵 안 픽셀). 맵 밖 칸은 세지 않는다."""
    from PIL import ImageChops
    W, H = full.size
    out = (1, 2, 3)
    pad = Image.new('RGB', (W + 512, H + 448), out)
    pad.paste(full.convert('RGB'), (256, 224))

    def score(ox, oy):
        d = ImageChops.difference(pad.crop((ox, oy, ox + 256, oy + 224)), scr).convert('L')
        return d.histogram()[0]

    _, cx, cy = max((score(x, y), x, y) for y in range(0, H + 225, 8) for x in range(0, W + 257, 8))
    _, x, y = max((score(x, y), x, y) for y in range(max(0, cy - 8), cy + 9) for x in range(max(0, cx - 8), cx + 9))
    a, b = pad.crop((x, y, x + 256, y + 224)).load(), scr.load()
    inside = [a[i, j] == b[i, j] for j in range(224) for i in range(256) if a[i, j] != out]
    return x - 256, y - 224, sum(inside), len(inside)


def check(rom, prefix, bc, bd, pset=None, night=False):
    """덤프한 화면과 맵 그림 비교. 결과 (x, y, 같은 픽셀, 맵 안 픽셀)."""
    dec, w, h, buf, _ = decode_map(rom, bc, bd)
    cg = set_cgram(rom, pset, night) if pset is not None else map_cgram(rom, bc, bd, night)
    return match_screen(draw_cells(rom, dec, w, h, buf, cg), dump_screen(prefix))


# ---------------------------------------------------------------- 내보내기

class Out:
    """그림을 ROOT 아래 분류 폴더에 쓰고, 분류 폴더마다 index.json·SOURCE.txt 를 남긴다."""

    def __init__(self, root, rom_sha=''):
        self.root, self.items, self.rom_sha = root, [], rom_sha
        self.index = {}  # 분류 폴더 → index.json 내용(기본은 항목 목록)

    def save(self, img, rel, cat, title, group='', **meta):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        img.save(path)
        self.items.append({'cat': cat, 'group': group, 'title': title, 'path': rel,
                           'w': img.width, 'h': img.height, **meta})

    def add(self, rel, cat, title, group='', **meta):
        self.items.append({'cat': cat, 'group': group, 'title': title, 'path': rel, **meta})

    def finish(self, command):
        dirs = {}
        for it in self.items:
            d = os.path.dirname(it['path'])
            top = d if d.startswith('gfx/') else d.split('/')[0]
            if top.startswith('gfx/blocks'):
                top = 'gfx/blocks'
            dirs.setdefault(top, []).append(dict(it, path=os.path.relpath(it['path'], top)))
        for top, items in dirs.items():
            folder = os.path.join(self.root, top)
            with open(os.path.join(folder, 'index.json'), 'w') as f:
                json.dump(self.index.get(top, items), f, ensure_ascii=False, indent=0)
            with open(os.path.join(folder, 'SOURCE.txt'), 'w') as f:
                f.write(source_text(command, self.rom_sha))


def source_text(command, rom_sha):
    try:
        commit = subprocess.run(['git', '-C', os.path.dirname(os.path.abspath(__file__)), 'rev-parse', 'HEAD'],
                                capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        commit = '알 수 없음'
    return (f'sfc-dq4 커밋: {commit}\n명령: {command}\n'
            f'롬: SFC 「ドラゴンクエストV」 일본판, SHA-1 {rom_sha}\n')


def group_names(rom):
    """ルーラ 목적지 목록 25:85D5 의 맵 그룹 22개와 이름 표 0B(마을 이름)를 짝지은 {그룹: 이름}.
    그룹마다 「ここは ○○」 대사가 이 이름과 맞는다(01 ラインハット, 1A アルカパ, 21 サンタローズ 등)."""
    from dq5text import string, string_codes, text
    return {rom.u8(RURA_GROUPS + i): text(string_codes(rom, string(rom, TOWN_NAMES, i))) for i in range(RURA_COUNT)}


def map_stem(bc, bd, names):
    name = names.get(bc) if bc < 0x50 else None
    return f'{bc:02X}-{bd:02X}' + (f'-{name}' if name else '')


def map_marks(rom, bc, bd, buf, w, h):
    """주석판에 그릴 것: 출구 셀, 인물(낮 기본 목록), 보물상자, タンス·ツボ·タル, 발밑."""
    from dq5chest import chest_maps, chests, foot_entries, search_entries
    from dq5exit import exit_cells
    marks = {'exits': exit_cells(buf, w, h, exit_attrs(rom)), 'npcs': [], 'chests': [], 'search': [], 'foot': []}
    if bc < 0x50:
        from dq5npc import map_entries, parse
        for k, (a, _) in enumerate(map_entries(rom, bc, bd)):
            f = parse(rom, a)
            if f:
                marks['npcs'].append((k, f['x'] & 0x7F, f['y'] & 0x7F, f['gfx'], f['talk']))
    for cbc, cbd, start, _ in chest_maps(rom):
        if (cbc, cbd) == (bc, bd):
            marks['chests'] = [(n, x, y) for n, (x, y), _ in chests(rom, bc, bd, start)]
    marks['search'] = [(x, y) for sbc, sbd, x, y, *_ in search_entries(rom) if (sbc, sbd) == (bc, bd)]
    marks['foot'] = [(x, y) for sbc, sbd, x, y, *_ in foot_entries(rom) if (sbc, sbd) == (bc, bd)]
    return marks


def annotate(base, marks):
    """노랑 인물(번호, 왼쪽 칸 기준 16x16), 하늘색 출구, 빨강 T 보물상자, 분홍 S タンス·ツボ·タル, 분홍 F 발밑."""
    img = base.convert('RGB')
    d = ImageDraw.Draw(img)
    for x, y in marks['exits']:
        d.rectangle((x * 8, y * 8, x * 8 + 7, y * 8 + 7), outline=(0, 200, 255))
    for x, y in marks['search']:
        d.rectangle((x * 8, y * 8, x * 8 + 7, y * 8 + 7), outline=(255, 120, 200))
        d.text((x * 8 + 1, y * 8 - 2), 'S', fill=(255, 120, 200))
    for x, y in marks['foot']:
        d.rectangle((x * 8, y * 8, x * 8 + 7, y * 8 + 7), outline=(255, 120, 200))
        d.text((x * 8 + 1, y * 8 - 2), 'F', fill=(255, 120, 200))
    for _, x, y in marks['chests']:
        d.rectangle((x * 8, y * 8, x * 8 + 7, y * 8 + 7), outline=(255, 40, 40))
        d.text((x * 8 + 1, y * 8 - 2), 'T', fill=(255, 40, 40))
    for k, x, y, _, _ in marks['npcs']:
        d.rectangle((x * 8, y * 8, x * 8 + 15, y * 8 + 15), outline=(255, 230, 0))
        d.text((x * 8 + 1, y * 8 + 3), f'{k}', fill=(255, 230, 0))
    return img


def export_maps(rom, out, only=None):
    names = group_names(rom)
    ids = map_ids(rom)
    if only:
        ids = [m for m in ids if m in only]
    for bc, bd in ids:
        stem = map_stem(bc, bd, names)
        dec, w, h, buf, blocks = decode_map(rom, bc, bd)
        marks = map_marks(rom, bc, bd, buf, w, h)
        meta = dict(map=f'{bc:02X}/{bd:02X}', name=names.get(bc, '') if bc < 0x50 else '', stem=stem,
                    size=f'{w}x{h}', addr=f'{map_pointer(rom, bc, bd):06X}', blocks=len(blocks), chrs=len(dec.chr_map),
                    npcs=len(marks['npcs']), exits=len(marks['exits']), chests=len(marks['chests']))
        title = f'{bc:02X}/{bd:02X}' + (f' {meta["name"]}' if meta['name'] else '')
        group = f'그룹 {bc:02X}'
        day_cg = map_cgram(rom, bc, bd)
        day = draw_cells(rom, dec, w, h, buf, day_cg)
        out.save(day, f'maps/{stem}.png', 'maps', title, group, variant='낮', **meta)
        out.save(annotate(day, marks), f'maps/{stem}-annot.png', 'maps', title, group, variant='주석', **meta,
                 annot={k: v for k, v in marks.items()})
        night_cg = map_cgram(rom, bc, bd, alt=True)
        if night_cg != day_cg:
            out.save(draw_cells(rom, dec, w, h, buf, night_cg), f'maps/{stem}-night.png', 'maps', title, group,
                     variant='밤', **meta)
        for obc, obd, flag, mask, pset in palette_overrides(rom):
            if obc == bc and obd in (None, bd):
                cond = f'7E:{0x2190 + (flag & 0x7F):04X} & {mask:02X} {"= 0" if flag & 0x80 else "≠ 0"}'
                for alt in (False, True):
                    if alt and set_cgram(rom, pset, True) == set_cgram(rom, pset):
                        continue
                    out.save(draw_cells(rom, dec, w, h, buf, set_cgram(rom, pset, alt)),
                             f'maps/{stem}-set{pset:02X}{"-night" if alt else ""}.png', 'maps', title, group,
                             variant=f'세트 {pset:02X}' + (' 밤' if alt else ''), **meta,
                             note=f'{cond} 이면 01:9771 이 바꾸는 팔레트')
                break
        colors = cgram_colors(day_cg)
        tc = TileCache(rom, dec.high, colors)
        imgs = [block_image(rom, dec, n, colors, tc) for n in blocks]
        cw = max(20, max(i.width for i in imgs))
        ch = max(i.height for i in imgs)
        out.save(sheet(imgs, max(1, min(16, 512 // (cw + 1))), cw, ch, [f'{n:03X}' for n in blocks], label_h=10,
                       below=True),
                 f'gfx/blocks/maps/{stem}.png', 'blocks', title, group, variant='블록', **meta)
        print(f'map {bc:02X}/{bd:02X} {w}x{h} blocks {len(blocks)}')


def export_chr(rom, out):
    """CHR 뱅크마다 1,024개(32개씩 32줄, 2배). -color 는 CHR 팔레트 번호대로 02/06(51/50) 낮 팔레트, -gray 는 색 번호."""
    gray = [(0, 0, 0)] + [(v * 17, v * 17, v * 17) for v in range(1, 16)]
    for high, base, pal_table, cg_map, count in ((False, 0x13, CHR_PALETTE, (0x02, 0x06), 0x1000),
                                                 (True, 0x1F, HIGH_CHR_PALETTE, (0x51, 0x50), 0x200)):
        colors = cgram_colors(map_cgram(rom, *cg_map))
        tc = TileCache(rom, high, colors)
        for part in range(0, count, 0x400):
            col, gr = [], []
            for chr_id in range(part, min(count, part + 0x400)):
                nib = rom.u8(pal_table + (chr_id >> 1))
                pal = ((nib & 0x0F) + 1) * 4 if chr_id & 1 else ((nib & 0xF0) >> 2) + 4
                col.append(scaled(tc.get(chr_id, (pal >> 2) & 7, False, False), 2))
                gr.append(scaled(tile_image(chr_pixels(rom, chr_id, high), gray), 2))
            bank = base + (part >> 10)
            for img, kind in ((col, 'color'), (gr, 'gray')):
                out.save(sheet(img, 32, 16, 16, pad=0, bg=(0, 0, 0)), f'gfx/blocks/chr{bank:02X}-{kind}.png', 'chr',
                         f'CHR {bank:02X}:8000 ({kind})', 'CHR', bank=f'{bank:02X}',
                         first=f'{part:03X}', palette=f'{cg_map[0]:02X}/{cg_map[1]:02X} 낮' if kind == 'color' else '색 번호')
    print('chr')


def export_field(rom, out):
    from dq5field import entrances, tile_word
    names = group_names(rom)
    tiles = field_tiles(rom)
    ents = entrances(rom)
    sets = field_time_sets(rom)
    day = next(p for p, los in sets if 2 in los)
    night = next(p for p, los in sets if 0xF2 in los)
    blocks_by = {}
    for ptr, los in sets:
        blocks = field_block_images(rom, field_cgram(rom, 0, ptr), tiles)
        blocks_by[ptr] = blocks
        stem = 'field0' if ptr == day else 'field0-night' if ptr == night else f'field0-{ptr:04X}'
        when = ', '.join(f'{v:04X}' for v in los) or '없음(시간대 표가 고르지 않음)'
        out.save(world_image(rom, 0, blocks), f'field/{stem}.png', 'field', '세계 0', '세계 지도',
                 variant='낮' if ptr == day else '밤' if ptr == night else f'01:{ptr:04X}', palette=f'01:{ptr:04X}',
                 note=f'$075E 하한 {when}')
    worlds = {0: blocks_by[day]}
    for world in (1, 2):
        worlds[world] = field_block_images(rom, field_cgram(rom, world), tiles)
        out.save(world_image(rom, world, worlds[world]), f'field/field{world}.png', 'field', f'세계 {world}',
                 '세계 지도', variant='낮', note=f'$1949 = {world}. 땅이 있는 왼쪽 위 128x128 블록')
    for world, blocks in worlds.items():
        img = world_image(rom, world, blocks)
        d = ImageDraw.Draw(img)
        el = []
        for g, x, y, w, (bd, ax, ay, _) in ents:
            if w != world:
                continue
            d.rectangle((x * 8 - 2, y * 8 - 2, x * 8 + 9, y * 8 + 9), outline=(255, 255, 0), width=2)
            d.text((x * 8 + 12, y * 8 - 2), f'{g:02X} {names.get(g, "")}', fill=(255, 255, 0))
            el.append({'group': f'{g:02X}', 'name': names.get(g, ''), 'x': x, 'y': y, 'to': f'{g:02X}/{bd:02X}',
                       'at': [ax, ay]})
        out.save(img, f'field/field{world}-annot.png', 'field', f'세계 {world}', '세계 지도', variant='주석',
                 entrances=el, note='노랑 = 04:FD97 입구(그룹 번호와 이름)')
    cg = field_cgram(rom, 0, day)
    labels = [f'{m:03X}' for m in range(512)]
    for layers, stem in ((('lower', 'upper'), 'field'), (('lower',), 'field-lower'), (('upper',), 'field-upper')):
        imgs = field_block_images(rom, cg, tiles, layers)
        out.save(sheet(imgs, 16, 20, 16, labels, label_h=10, below=True), f'gfx/blocks/{stem}.png', 'blocks',
                 f'필드 블록 512개 ({"·".join({"lower": "아래층", "upper": "위층"}[k] for k in layers)})', '필드',
                 note='블록 번호(9비트). 정의 2A:A32C·2A:AD27')
    colors = cgram_colors(cg)
    cells = []
    for t in range(512):
        p = (tile_word(rom, t, True) >> 10) & 7
        cells.append(scaled(tile_image(tiles[t], colors[p * 16:p * 16 + 16]), 2))
    out.save(sheet(cells, 32, 16, 16, pad=0, bg=(0, 0, 0)), 'gfx/blocks/field-tiles.png', 'chr',
             '필드 타일 512개 12:B1A8', 'CHR', note='VRAM 워드 2000-, 2배, 위층 표의 팔레트')
    print('field')


def frames_out(out, frames, stem, title, note, duration):
    sheet_img = sheet(frames, 1, frames[0].width, frames[0].height, [f'{k}' for k in range(len(frames))], label_h=10)
    out.save(sheet_img, f'gfx/anim/{stem}.png', 'anim', title, '필드', note=note, frames=len(frames))
    path = os.path.join(out.root, f'gfx/anim/{stem}.gif')
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=duration, loop=0)
    out.add(f'gfx/anim/{stem}.gif', 'anim', title + ' (GIF)', '필드', w=frames[0].width, h=frames[0].height)


def export_anim(rom, out):
    from dq5field import field_chr, tile_word
    sets = field_time_sets(rom)
    day = next(p for p, los in sets if 2 in los)
    colors = cgram_colors(field_cgram(rom, 0, day))

    def img(t, raw):
        p = (tile_word(rom, t, False) >> 10) & 7
        return tile_image(planar(raw), colors[p * 16:p * 16 + 16])

    frames = []
    for tiles in field_anim_sets(rom):
        strip = Image.new('RGB', (FIELD_ANIM_COUNT * 8, 8), colors[0])
        for i, raw in enumerate(tiles):
            t = img(FIELD_ANIM_TILE + i, raw)
            strip.paste(t, (i * 8, 0), t)
        frames.append(strip)
    frames_out(out, frames, 'field-454', '필드 타일 454~459 8벌', '1E:D0FF RLE → 7E:C800 → VRAM 워드 3C60', 150)
    chrs = field_chr(rom)
    frames = []
    for k in range(16):
        strip = Image.new('RGB', (32, 8), colors[0])
        for j, (t1, t2) in enumerate(((0x04, 0x05), (0x14, 0x15))):
            a, b = rotate_pair(chrs[t1 * 32:t1 * 32 + 32], chrs[t2 * 32:t2 * 32 + 32], k)
            for q, (t, raw) in enumerate(((t1, a), (t2, b))):
                ti = img(t, raw)
                strip.paste(ti, (j * 16 + q * 8, 0), ti)
        frames.append(strip)
    frames_out(out, frames, 'field-water', '필드 물 타일 4·5·20·21 16단계',
               '두 타일을 줄마다 16비트로 보고 k 픽셀 돌림(01:C790, 세계 0 은 오른쪽)', 120)
    frames = []
    for wave in range(WAVE_STEPS):
        b = field_block_images(rom, field_cgram(rom, 0, day, wave), field_tiles(rom))
        strip = Image.new('RGB', (16 * 8, 16))
        for i in range(8):
            strip.paste(b[i], (i * 16, 0))
        frames.append(strip)
    frames_out(out, frames, 'field-wave', '필드 물결 팔레트 10단계(블록 000~007)',
               '4번 줄 색 1~3 을 01:A0F6 + $1961*6 으로(01:A0CF)', 120)
    print('anim')


MATRIX_CHARS = '.123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'
# 몬스터 EA·EB 는 ミルドラース 최종 모습의 윗몸·아랫몸이라 둘을 같은 원점에 겹쳐 그린다(dq5-graphics-format.md).
MONSTER_NOTES = {0xEA: '윗몸. 게임은 EB(아랫몸)를 같은 원점에 겹쳐 그림', 0xEB: '아랫몸. EA 와 겹쳐 그림'}


def export_monsters(rom, out):
    from dq5mongfx import COUNT, RECORDS, decode, index_image, monster
    from dq5mongfx import render as render_monster
    from dq5monster import NAMES
    from dq5text import string, string_codes, text
    records = []
    for m in range(COUNT):
        g, colors = monster(rom, m)
        name = text(string_codes(rom, string(rom, NAMES, m)))
        d = decode(rom, g)
        grid = index_image(d)
        img = render_monster(rom, m, None)
        file = f'{m:02X}-{name}.png'
        out.save(img, f'monsters/{file}', 'monsters', f'{m:02X} {name}', '몬스터', monster=f'{m:02X}', name=name,
                 pic=f'{g:02X}')
        records.append({'file': file, 'id': m, 'name': name, 'picture': g,
                        'record': f'27:{rom.u16(RECORDS + m * 2):04X}', 'head': f'{d["head"] >> 16:02X}:{d["head"] & 0xFFFF:04X}',
                        'cells': [d['w'], d['h']], 'pieces': len(d['pieces']), 'size': [img.width, img.height],
                        'colors': [f'{c:04X}' for c in colors], 'usable': True, 'note': MONSTER_NOTES.get(m, ''),
                        'matrix': [''.join(MATRIX_CHARS[v] for v in row) for row in grid]})
    out.index['monsters'] = {
        'note': '그림은 1배, 투명 배경. 왼쪽 1픽셀은 반전 조각이 한 픽셀 왼쪽으로 나갈 자리. colors 는 OBJ 팔레트 1번 색부터의 '
                '15비트 BGR, matrix 문자는 색 번호(. 투명, 1~9·A~). record 는 27 뱅크 몬스터 레코드, head 는 그림 머리',
        'monsters': records}
    print('monsters')


def export_battlebg(rom, out):
    import dq5battlebg as bb
    for n in range(bb.COUNT):
        for era in (0, 1, 2):
            stem = f'{n:02X}' + (f'-{era}' if era else '')
            out.save(bb.render(rom, n, era), f'battlebg/{stem}.png', 'battlebg', f'{n:02X} ($1949={era})',
                     f'세계 {era}', number=f'{n:02X}', era=era, note='레코드 밖 팔레트 색은 자홍')
    print('battlebg')


def export_font(rom, out):
    from dq5text import GLYPHS, font_groups, glyph
    groups = font_groups(rom)
    cells = []
    for code in range(GLYPHS):
        w, h, rows = glyph(rom, code, groups)
        img = Image.new('RGB', (16, 16))
        p = img.load()
        for y, row in enumerate(rows):
            for x, v in enumerate(row):
                if v and x < 16 and y < 16:
                    p[x, y] = (255, 255, 255)
        cells.append(scaled(img, 2))
    out.save(sheet(cells, 16, 32, 32, pad=0, bg=(0, 0, 0)), 'gfx/font.png', 'font', f'폰트 글자 {GLYPHS}개', '폰트',
             note='24:A609, 16자씩 한 줄, 2배. n 번째 칸 = 글자 코드 n')
    print('font')


def export_ui(rom, out):
    o = lorom(UI_PALETTE)
    colors = cgram_colors(rom.d[o:o + 32])
    data = ui_tiles(rom)
    tiles = [chr_2bpp(data[t * 16:t * 16 + 16]) for t in range(len(data) // 16)]
    for pal in range(4):
        cells = [scaled(tile_image(px, colors[pal * 4:pal * 4 + 4]), 2) for px in tiles]
        stem = 'window-tiles' + (f'-pal{pal}' if pal else '')
        out.save(sheet(cells, 16, 16, 16, pad=0, bg=colors[0]), f'gfx/screens/{stem}.png', 'screens',
                 f'창·메뉴 타일 {len(tiles)}개 (BG3 팔레트 {pal})', '창', note='04:E528, 2배, n 번째 칸 = 타일 n')
    win = Image.new('RGBA', (len(UI_SAMPLE[0]) * 8, len(UI_SAMPLE) * 8), colors[0] + (255,))
    for y, row in enumerate(UI_SAMPLE):
        for x, w in enumerate(row):
            t = tile_image(tiles[w & 0xFF], colors[0:4], bool(w & 0x400), bool(w & 0x800))
            win.paste(t, (x * 8, y * 8), t)
    out.save(win.convert('RGB'), 'gfx/screens/window.png', 'screens', '창 견본(배 선실의 상태 창)', '창',
             note='타일 8C~90 테두리와 글자 타일')
    print('ui')


EXPORTS = {'maps': export_maps, 'chr': export_chr, 'field': export_field, 'anim': export_anim,
           'monsters': export_monsters, 'battlebg': export_battlebg, 'font': export_font, 'ui': export_ui}
COMMAND = 'uv run --locked python sfc/dq5/tools/dq5gallery.py rom/dq5.sfc --out $OUT'


def export_all(rom, root, only=None, maps=None, rom_sha='', command=COMMAND):
    out = Out(root, rom_sha)
    for k, fn in EXPORTS.items():
        if only and k not in only:
            continue
        if k == 'maps':
            fn(rom, out, maps)
        else:
            fn(rom, out)
    out.finish(command)
    return out.items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('--out', default='work/dq5gfx', help='분류 폴더(maps/ field/ …)를 만들 곳')
    ap.add_argument('--only', help='쉼표로: ' + ','.join(EXPORTS))
    ap.add_argument('--maps', help='쉼표로 맵만 골라서: 02/06,51/50')
    ap.add_argument('--check', nargs=2, metavar=('DUMP', 'BC/BD'),
                    help='dq5gfxdump.lua 덤프(경로/fNNNNN)의 BG 화면과 맵 그림을 픽셀째 비교')
    ap.add_argument('--set', type=lambda v: int(v, 16), help='--check 에서 팔레트 세트를 직접(16진)')
    ap.add_argument('--night', action='store_true', help='--check 에서 밤 팔레트')
    args = ap.parse_args()
    data = open(args.rom, 'rb').read()
    rom = Rom(data)
    if args.check:
        bc, bd = (int(v, 16) for v in args.check[1].split('/'))
        x, y, hit, n = check(rom, args.check[0], bc, bd, args.set, args.night)
        print(f'{bc:02X}/{bd:02X}: 화면 왼쪽 위 = 맵 ({x},{y}) 픽셀, 맵 안 BG 픽셀 {hit}/{n} 같음')
        return 0 if hit == n else 1
    only = set(args.only.split(',')) if args.only else None
    maps = {tuple(int(v, 16) for v in m.split('/')) for m in args.maps.split(',')} if args.maps else None
    items = export_all(rom, args.out, only, maps, hashlib.sha1(data).hexdigest(),
                       'uv run --locked python sfc/dq5/tools/dq5gfx.py rom/dq5.sfc --out $OUT')
    print(f'{len(items)} items -> {args.out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
