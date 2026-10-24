"""DQ5(SFC) 그래픽을 롬에서 PNG 로 뽑는다. 형식은 sfc/dq5/docs/dq5-graphics-format.md 의 「그래픽 내보내기와 갤러리」.

스프라이트를 새로 그릴 때 원작 그림을 같은 배율로 찾아보려는 용도다. 디코더는 다른 도구의 것을 그대로 쓴다.

  maps     실내 맵 346개와 그룹 $50 이상 18개 전체 그림(낮·밤, 맵별 루틴 15:F907 반영), 속성 겹침, 맵이 쓰는 블록 모음
  chr      실내 CHR(13:8000-, 1F:8000-)을 CHR 팔레트 번호(2A:8781, 0F:CF83)대로 칠한 모음
  field    세계 지도 셋 전체(세계 0 은 시간대 8벌), 필드 블록 512개, 필드 타일 512개
  monsters 전투 몬스터 236마리(dq5mongfx)
  font     폰트 글자 0x3DB 개(dq5text)

결과는 OUT(기본 work/gfx)에 쓰고, 항목 목록을 OUT/manifest.json 에 남긴다(tools/dq5gallery.py 가 읽는다).
롬에서 뽑은 그림이므로 저장소에 커밋하지 않는다.

사용:
  python sfc/dq5/tools/dq5gfx.py rom/dq5.sfc [--out work/gfx] [--only maps,field] [--maps 02/06,51/50]
  python sfc/dq5/tools/dq5gfx.py rom/dq5.sfc --check work/d/f00005 06/03 [--set 26] [--night]
--check 는 sfc/dq5/tools/lua/dq5gfxdump.lua 로 그 맵에서 덤프한 VRAM·CGRAM 으로 BG2 위에 BG1 을 겹친 화면을 맵 그림과 비교한다.
"""
import argparse
import json
import os
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


def sheet(cells, cols, cell_w, cell_h, labels=None, bg=(32, 32, 40), pad=1, label_h=0):
    """같은 크기 그림을 격자로. labels 를 주면 칸 위에 작은 글씨."""
    rows = (len(cells) + cols - 1) // cols
    W, H = cols * (cell_w + pad) + pad, rows * (cell_h + label_h + pad) + pad
    out = Image.new('RGB', (W, H), bg)
    d = ImageDraw.Draw(out)
    for i, c in enumerate(cells):
        x, y = pad + i % cols * (cell_w + pad), pad + i // cols * (cell_h + label_h + pad)
        if labels:
            d.text((x, y), labels[i], fill=(200, 200, 120))
        if c is not None:
            out.paste(c, (x, y + label_h), c if c.mode == 'RGBA' else None)
    return out


class Out:
    def __init__(self, root):
        self.root, self.items = root, []

    def save(self, img, rel, cat, title, group='', **meta):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        img.save(path)
        self.items.append({'cat': cat, 'group': group, 'title': title, 'path': rel,
                           'w': img.width, 'h': img.height, **meta})


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


def attr_overlay(base, w, h, buf, exits):
    """셀 +1 아래 니블(걸을 수 있는 층)과 가구·출구를 반투명으로. 16칸마다 굵은 격자."""
    img = base.convert('RGBA')
    ov = Image.new('RGBA', img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    for cell in range(w * h):
        x, y = cell % w * 8, cell // w * 8
        b1, a4, a7 = buf[cell * 8 + 1], buf[cell * 8 + 4], buf[cell * 8 + 7]
        if a4 in exits or a7 in exits:
            c = (255, 0, 255, 150)
        elif b1 & 0x80:
            c = (255, 140, 0, 110)
        elif b1 & 7:
            c = ((0, 255, 0, 70), (0, 200, 255, 90), (0, 255, 200, 90), (80, 80, 255, 90),
                 (160, 255, 80, 90), (200, 120, 255, 90), (255, 255, 0, 90))[(b1 & 7) - 1]
        else:
            c = (255, 0, 0, 90)
        d.rectangle((x, y, x + 7, y + 7), fill=c)
    img = Image.alpha_composite(img, ov)
    d = ImageDraw.Draw(img)
    for x in range(0, w * 8, 16):
        d.line((x, 0, x, h * 8), fill=(0, 0, 0, 255) if x % 128 == 0 else (0, 0, 0, 90))
    for y in range(0, h * 8, 16):
        d.line((0, y, w * 8, y), fill=(0, 0, 0, 255) if y % 128 == 0 else (0, 0, 0, 90))
    for y in range(0, h, 16):
        for x in range(0, w, 16):
            d.text((x * 8 + 2, y * 8 + 1), f'{x},{y}', fill=(255, 255, 255, 255))
    return img.convert('RGB')


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


def export_maps(rom, out, only=None):
    exits = set(exit_attrs(rom))
    ids = map_ids(rom)
    if only:
        ids = [m for m in ids if m in only]
    for bc, bd in ids:
        name = f'{bc:02X}-{bd:02X}'
        group = f'그룹 {bc:02X}'
        dec, w, h, buf, blocks = decode_map(rom, bc, bd)
        meta = dict(map=f'{bc:02X}/{bd:02X}', size=f'{w}x{h} 셀', addr=f'{map_pointer(rom, bc, bd):06X}',
                    blocks=len(blocks), chrs=len(dec.chr_map))
        day_cg = map_cgram(rom, bc, bd)
        day = draw_cells(rom, dec, w, h, buf, day_cg)
        out.save(day, f'maps/{name}-day.png', 'maps', f'{bc:02X}/{bd:02X} 낮', group, **meta)
        night_cg = map_cgram(rom, bc, bd, alt=True)
        if night_cg != day_cg:
            out.save(draw_cells(rom, dec, w, h, buf, night_cg), f'maps/{name}-night.png', 'maps',
                     f'{bc:02X}/{bd:02X} 밤', group, **meta)
        for obc, obd, flag, mask, pset in palette_overrides(rom):
            if obc == bc and obd in (None, bd):
                cond = f'7E:{0x2190 + (flag & 0x7F):04X} & {mask:02X} {"= 0" if flag & 0x80 else "≠ 0"}'
                for alt, when in ((False, '낮'), (True, '밤')):
                    if alt and set_cgram(rom, pset, True) == set_cgram(rom, pset):
                        continue
                    out.save(draw_cells(rom, dec, w, h, buf, set_cgram(rom, pset, alt)),
                             f'maps/{name}-set{pset:02X}{"-night" if alt else ""}.png', 'maps',
                             f'{bc:02X}/{bd:02X} {when} 세트 {pset:02X}', group, **meta, note=f'{cond} 이면 01:9771 이 바꾸는 팔레트')
                break
        out.save(attr_overlay(day, w, h, buf, exits), f'maps/{name}-attr.png', 'maps-attr',
                 f'{bc:02X}/{bd:02X} 속성', group, **meta)
        colors = cgram_colors(day_cg)
        tc = TileCache(rom, dec.high, colors)
        imgs = [scaled(block_image(rom, dec, n, colors, tc), 2) for n in blocks]
        cw = max(24, max(i.width for i in imgs))
        ch = max(i.height for i in imgs)
        out.save(sheet(imgs, max(1, min(16, 1024 // (cw + 1))), cw, ch, [f'{n:03X}' for n in blocks], label_h=10),
                 f'maps/{name}-blocks.png', 'map-blocks', f'{bc:02X}/{bd:02X} 블록 {len(blocks)}개', group, **meta)
        print(f'map {bc:02X}/{bd:02X} {w}x{h} blocks {len(blocks)}')


def export_chr(rom, out):
    """실내 CHR 을 팔레트 번호대로. 색은 오프닝 02/06 의 낮 팔레트(줄마다 뜻이 맵에 따라 다르다)."""
    for high, bank, pal_table, cg_map, count, title in (
            (False, 0x13, CHR_PALETTE, (0x02, 0x06), 0x1000, '실내 CHR 13:8000-'),
            (True, 0x1F, HIGH_CHR_PALETTE, (0x51, 0x50), 0x200, '그룹 $50 이상 CHR 1F:8000-')):
        colors = cgram_colors(map_cgram(rom, *cg_map))
        tc = TileCache(rom, high, colors)
        cells = []
        for chr_id in range(count):
            a = (bank + (chr_id >> 10)) << 16 | 0x8000 + (chr_id & 0x3FF) * 32
            if lorom(a) + 32 > len(rom.d):
                break
            nib = rom.u8(pal_table + (chr_id >> 1))
            pal = ((nib & 0x0F) + 1) * 4 if chr_id & 1 else ((nib & 0xF0) >> 2) + 4
            cells.append(scaled(tc.get(chr_id, (pal >> 2) & 7, False, False), 2))
        for part in range(0, len(cells), 0x400):
            img = sheet(cells[part:part + 0x400], 32, 16, 16)
            out.save(img, f'chr/{"high" if high else "indoor"}-{part:03X}.png', 'chr',
                     f'{title} {part:03X}-{part + len(cells[part:part + 0x400]) - 1:03X}',
                     note=f'2배, 32개씩 한 줄, 색은 {cg_map[0]:02X}/{cg_map[1]:02X} 팔레트')
        print(f'chr {title}: {len(cells)}')


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


def export_field(rom, out):
    from dq5field import entrances
    tiles = field_tiles(rom)
    sets = field_time_sets(rom)
    ents = entrances(rom)
    for k, (ptr, los) in enumerate(sets):
        cg = field_cgram(rom, 0, ptr)
        blocks = field_block_images(rom, cg, tiles)
        img = world_image(rom, 0, blocks)
        when = ', '.join(f'{v:04X}' for v in los) or '없음(표가 고르지 않음)'
        out.save(img, f'field/world0-{ptr:04X}.png', 'field', f'세계 0 (팔레트 01:{ptr:04X})', '세계 지도',
                 note=f'$075E 하한 {when} 에서 고르는 2·3번 줄. 블록 256x256(16픽셀)', big=True)
        if 2 in los:  # $075E 0002~00ED, 낮
            first = (cg, blocks)
        print(f'field world0 {ptr:04X}')
    for world in (1, 2):
        cg = field_cgram(rom, world)
        img = world_image(rom, world, field_block_images(rom, cg, tiles))
        out.save(img, f'field/world{world}.png', 'field', f'세계 {world}', '세계 지도',
                 note='$1949 = %d. 땅이 있는 왼쪽 위 128x128 블록' % world, big=True)
    # 입구 표시: 첫 벌 위에 04:FD97 입구(블록 좌표)를 노란 틀로, 1/4 축소.
    cg, blocks = first
    day_ptr = next(p for p, los in sets if 2 in los)
    small = world_image(rom, 0, blocks).resize((1024, 1024), Image.BOX)
    d = ImageDraw.Draw(small)
    for g, x, y, w, _ in ents:
        if w == 0:
            d.rectangle((x * 2 - 4, y * 2 - 4, x * 2 + 6, y * 2 + 6), outline=(255, 255, 0))
            d.text((x * 2 + 8, y * 2 - 4), f'{g:02X}', fill=(255, 255, 0))
    out.save(small, 'field/world0-entrances.png', 'field', '세계 0 입구(1/4)', '세계 지도',
             note='노란 틀과 숫자 = 04:FD97 입구의 그룹 $BC')
    labels = [f'{m:03X}' for m in range(512)]
    for layers, name in ((('lower', 'upper'), '아래+위층'), (('lower',), '아래층'), (('upper',), '위층')):
        imgs = [scaled(i, 2) for i in field_block_images(rom, cg, tiles, layers)]
        out.save(sheet(imgs, 16, 32, 32, labels, label_h=10), f'field/blocks-{"-".join(layers)}.png', 'field-blocks',
                 f'필드 블록 512개 {name}', '블록', note='블록 번호(9비트), 2배. 정의 2A:A32C·2A:AD27')
    from dq5field import tile_word
    colors = cgram_colors(cg)
    cells = []
    for t in range(512):
        word = tile_word(rom, t, True)
        p = (word >> 10) & 7
        cells.append(scaled(tile_image(tiles[t], colors[p * 16:p * 16 + 16]), 2))
    out.save(sheet(cells, 32, 16, 16), 'field/tiles.png', 'field-blocks', '필드 타일 512개', '타일',
             note='12:B1A8 (VRAM 워드 2000-), 2배, 위층 표의 팔레트로 칠함')
    # 4번 줄 물결 색 10단계: 물이 들어간 블록 000 을 단계마다.
    frames = []
    for wave in range(WAVE_STEPS):
        cgw = field_cgram(rom, 0, day_ptr, wave)
        b = field_block_images(rom, cgw, tiles)
        strip = Image.new('RGB', (16 * 8, 16))
        for i, m in enumerate((0x000, 0x001, 0x002, 0x003, 0x004, 0x005, 0x006, 0x007)):
            strip.paste(b[m], (i * 16, 0))
        frames.append(scaled(strip, 3))
    out.save(sheet(frames, 1, frames[0].width, frames[0].height,
                   [f'$1961={k}' for k in range(WAVE_STEPS)], label_h=10),
             'field/wave.png', 'anim', '필드 물결 팔레트 10단계(블록 000~007)', '필드',
             note='4번 줄 색 1~3 을 01:A0F6 + $1961*6 으로 바꿈(매 프레임 01:A0CF)')
    frames[0].save(os.path.join(out.root, 'field/wave.gif'), save_all=True,
                   append_images=frames[1:], duration=120, loop=0)
    out.items.append({'cat': 'anim', 'group': '필드', 'title': '필드 물결(GIF)', 'path': 'field/wave.gif',
                      'w': frames[0].width, 'h': frames[0].height})


# ---------------------------------------------------------------- 몬스터·폰트

def export_monsters(rom, out):
    from dq5mongfx import COUNT, monster
    from dq5mongfx import render as render_monster
    try:
        from dq5monster import NAMES
        from dq5text import string, string_codes, text
        name = lambda m: text(string_codes(rom, string(rom, NAMES, m)))  # noqa: E731
    except Exception:  # 이름 표를 못 읽어도 그림은 뽑는다
        name = lambda m: ''  # noqa: E731
    thumbs = []
    for m in range(COUNT):
        g, colors = monster(rom, m)
        img = render_monster(rom, m, None)
        out.save(img, f'monsters/{m:02X}.png', 'monsters', f'{m:02X} {name(m)}', '몬스터',
                 pic=f'{g:02X}', colors=len(colors))
        thumbs.append(img)
    cw, ch = max(i.width for i in thumbs), max(i.height for i in thumbs)
    out.save(sheet(thumbs, 12, cw, ch, [f'{m:02X}' for m in range(COUNT)], label_h=10),
             'monsters/sheet.png', 'monsters', '몬스터 236마리 모음', '모음')
    print(f'monsters {COUNT}')


def export_font(rom, out):
    from dq5text import GLYPHS, font_groups, glyph
    groups = font_groups(rom)
    cells, labels = [], []
    for code in range(GLYPHS):
        w, h, rows = glyph(rom, code, groups)
        img = Image.new('RGBA', (16, 16), (0, 0, 0, 255))
        p = img.load()
        for y, row in enumerate(rows):
            for x, v in enumerate(row):
                if v and x < 16 and y < 16:
                    p[x, y] = (255, 255, 255, 255)
        cells.append(scaled(img, 2))
        labels.append(f'{code:03X}')
    out.save(sheet(cells, 16, 32, 32, labels, label_h=10), 'font/glyphs.png', 'font', f'폰트 글자 {GLYPHS}개', '폰트',
             note='24:A609 묶음 표, 1bpp, 2배. 글자 코드 = 칸 위 숫자')
    print(f'font {GLYPHS}')



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

EXPORTS = {'maps': export_maps, 'chr': export_chr, 'field': export_field,
           'monsters': export_monsters, 'font': export_font}


def export_all(rom, outdir, only=None, maps=None):
    out = Out(outdir)
    for k, fn in EXPORTS.items():
        if only and k not in only:
            continue
        if k == 'maps':
            fn(rom, out, maps)
        else:
            fn(rom, out)
    return out.items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('--out', default='work/gfx')
    ap.add_argument('--only', help='쉼표로: ' + ','.join(EXPORTS))
    ap.add_argument('--maps', help='쉼표로 맵만 골라서: 02/06,51/50')
    ap.add_argument('--check', nargs=2, metavar=('DUMP', 'BC/BD'),
                    help='dq5gfxdump.lua 덤프(경로/fNNNNN)의 BG 화면과 맵 그림을 픽셀째 비교')
    ap.add_argument('--set', type=lambda v: int(v, 16), help='--check 에서 팔레트 세트를 직접(16진)')
    ap.add_argument('--night', action='store_true', help='--check 에서 밤 팔레트')
    args = ap.parse_args()
    rom = Rom(open(args.rom, 'rb').read())
    if args.check:
        bc, bd = (int(v, 16) for v in args.check[1].split('/'))
        x, y, hit, n = check(rom, args.check[0], bc, bd, args.set, args.night)
        print(f'{bc:02X}/{bd:02X}: 화면 왼쪽 위 = 맵 ({x},{y}) 픽셀, 맵 안 BG 픽셀 {hit}/{n} 같음')
        return 0 if hit == n else 1
    only = set(args.only.split(',')) if args.only else None
    maps = {tuple(int(v, 16) for v in m.split('/')) for m in args.maps.split(',')} if args.maps else None
    items = export_all(rom, args.out, only, maps)
    with open(os.path.join(args.out, 'manifest.json'), 'w') as f:
        json.dump(items, f, ensure_ascii=False, indent=0)
    print(f'{len(items)} items -> {args.out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
