"""DQ5(SFC) 필드 인물 스프라이트. 형식은 sfc/dq5/docs/dq5-graphics-format.md 의 「필드 인물 스프라이트」.

그림 번호 g(인물 표 7E:3220, 주인공은 7E:196F) → 25:86D0[g] = 세트 번호 s(1F:CF45).
세트 s → 1F:D63D[s] 가 가리키는 1F 뱅크 레코드 52바이트(1F:CFA9·1F:D0DC):
  +0~+2  타일 자료 주소(+2 의 아래 6비트가 뱅크), +2 bit6-7 = OBJ 팔레트 0~3
  +3~+50 타일 칸 48개. bit0-6 = 세트 안 타일 번호, bit7 = 좌우 반전
  +51    타일 수(VRAM 에 올리는 8x8 타일 개수)
타일 자료는 VRAM 낮은 바이트(평면 0·2) 줄기와 높은 바이트(평면 1·3) 줄기를 차례로 둔 런 길이 압축이다(1F:D2DB).
  c < 7F: 다음 c+1 바이트 그대로 / 7F: 다음 뱅크 $8000 으로 / 80: 끝 / 그 밖: 다음 1바이트를 (c&7F)+1 번
세트 < 80 은 프레임마다 타일 6개(16x24, 00:F071), 80 이상은 머리 16x16 과 몸 16x16 을 8픽셀 겹친 타일 8개(00:F7AA).
OBJ 팔레트 0~3 은 04:96D6 의 16색 4줄이다. 팔레트 3 은 맵 OBJ 타일이 있는 맵에서 다른 색으로 바뀐다.
맵 OBJ 타일(1F:D59A, 1F:D4AF)은 맵마다 더 올리는 OBJ 타일로, 배치를 몰라 타일을 늘어놓기만 한다.

사용:
  python sfc/dq5/tools/dq5sprite.py rom/dq5.sfc --out work/sprites [--scale 4] [--grid] [--no-index]
  python sfc/dq5/tools/dq5sprite.py rom/dq5.sfc --list
  python sfc/dq5/tools/dq5sprite.py rom/dq5.sfc --compare DIR   # wNNNN.bin vNNNN.vram oNNNN.oam cNNNN.cgram 덤프와 비교
--out 은 세트마다 시트(행: 아래·왼쪽·오른쪽·위, 열: 프레임 0·1), 색 번호 보기 시트(-index.png, 8픽셀 격자),
색 번호 행렬(.txt), 맵 OBJ 타일 시트(mapobjNN.png)와 index.json 을 쓴다. 롬에서 나온 그림이므로
work/ 아래에만 쓴다(커밋 금지).
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5map import Rom  # noqa: E402

GFX_SETS = 0x2586D0
GFX_COUNT = 0xA9
SET_POINTERS = 0x1FD63D
SET_COUNT = 0xA3
OBJ_PALETTES = 0x0496D6
MAP_OBJECTS = 0x1FD59A
FRAME_W, FRAME_H = 16, 24
DIRS = ('down', 'left', 'right', 'up')
# 00:EE5C(6타일)·00:EE8C(8타일)를 방향별 칸 번호로 옮겼다.
SIMPLE_BASE = {'up': 0, 'right': 12, 'down': 24, 'left': 36}
HEAD_BASE = {'up': 0, 'right': 4, 'down': 8, 'left': 12}
BODY_BASE = {'up': 16, 'right': 24, 'down': 32, 'left': 40}
SIMPLE_POS = ((0, 0), (8, 0), (0, 8), (8, 8), (0, 16), (8, 16))
QUAD_POS = ((0, 0), (8, 0), (0, 8), (8, 8))


def gfx_set(rom, g):
    return rom.u8(GFX_SETS + g)


def set_record(rom, s):
    """레코드 dict. 쓰지 않는 번호(70~7F, 포인터 FFFF)는 None."""
    p = rom.u16(SET_POINTERS + s * 2)
    if p == 0xFFFF:
        return None
    a = 0x1F0000 | p
    b = [rom.u8(a + i) for i in range(0x34)]
    return {'set': s, 'record': a, 'data': (b[2] & 0x3F) << 16 | b[1] << 8 | b[0], 'palette': b[2] >> 6,
            'cells': b[3:51], 'tiles': b[51], 'layout': 'overlap' if s & 0x80 else 'simple'}


def unpack(rom, a, bank_skip=True):
    """1F:D2DB. (풀린 바이트, 다음 줄기 주소). bank_skip=False 는 1F:D28B(7F 도 그대로 128바이트)."""
    out = bytearray()
    while True:
        c = rom.u8(a)
        if c == 0x80:
            return out, a + 1
        if c == 0x7F and bank_skip:
            a = ((a >> 16) + 1) << 16 | 0x8000
        elif c < 0x80:
            out += bytes(rom.u8(a + 1 + i) for i in range(c + 1))
            a += c + 2
        else:
            out += bytes([rom.u8(a + 1)]) * ((c & 0x7F) + 1)
            a += 2


def split_tiles(rom, a, bank_skip=True):
    """낮은 바이트 줄기 → $2118, 높은 바이트 줄기 → $2119(1F:D200). (4bpp 타일 목록, 자료 끝 주소)."""
    lo, a = unpack(rom, a, bank_skip)
    hi, end = unpack(rom, a, bank_skip)
    tiles = []
    for i in range(len(lo) // 16):
        t = bytearray(32)
        t[0::2] = lo[i * 16:i * 16 + 16]
        t[1::2] = hi[i * 16:i * 16 + 16]
        tiles.append(bytes(t))
    return tiles, end


def set_tiles(rom, rec):
    return split_tiles(rom, rec['data'])


def map_objects(rom):
    """1F:D4AF. 맵마다 더 올리는 OBJ 타일(배치는 다른 루틴이 정한다). 6바이트 항목, FF 로 끝.
    [BC][BD][주소 16비트][뱅크][VRAM 에 잡는 타일 수]. BC = 7E 는 필드(BD 아래 7비트 = 세계 $1949),
    BD 아래 7비트 7F 는 그 그룹 모든 맵, BD bit7 은 압축(1F:D28B), 아니면 타일 수 × 32바이트 그대로(1F:D56A)."""
    out, a = [], MAP_OBJECTS
    while rom.u8(a) != 0xFF:
        bc, bd, n = rom.u8(a), rom.u8(a + 1), rom.u8(a + 5)
        src = rom.u8(a + 4) << 16 | rom.u16(a + 2)
        if bd & 0x80:
            tiles, end = split_tiles(rom, src, False)
        else:
            tiles = [bytes(rom.u8(src + i * 32 + k) for k in range(32)) for i in range(n)]
            end = src + n * 32
        where = (f'필드 세계 {bd & 0x7F}' if bc == 0x7E else
                 f'{bc:02X}/' + ('**' if bd & 0x7F == 0x7F else f'{bd & 0x7F:02X}'))
        out.append({'entry': a, 'bc': bc, 'bd': bd, 'where': where, 'data': src, 'end': end,
                    'reserve': n, 'tiles': tiles, 'packed': bool(bd & 0x80)})
        a += 6
    return out


def pixels(t):
    return [[(t[y * 2] >> (7 - x) & 1) | (t[y * 2 + 1] >> (7 - x) & 1) << 1
             | (t[16 + y * 2] >> (7 - x) & 1) << 2 | (t[17 + y * 2] >> (7 - x) & 1) << 3
             for x in range(8)] for y in range(8)]


def frame_cells(rec, d, f):
    """(칸 번호, x, y) 를 아래에 깔리는 것부터. 8타일 배치는 머리가 몸 위에 그려진다(OAM 낮은 슬롯이 위)."""
    if rec['layout'] == 'simple':
        b = SIMPLE_BASE[d] + f * 6
        return [(b + i, x, y) for i, (x, y) in enumerate(SIMPLE_POS)]
    body = BODY_BASE[d] + f * 4
    head = HEAD_BASE[d]
    return [(body + i, x, y + 8) for i, (x, y) in enumerate(QUAD_POS)] + \
        [(head + i, x, y) for i, (x, y) in enumerate(QUAD_POS)]


def frame(rec, tiles, d, f):
    """16x24 색 번호 격자(0 = 투명)."""
    img = [[0] * FRAME_W for _ in range(FRAME_H)]
    pix = [pixels(t) for t in tiles]
    for c, x0, y0 in frame_cells(rec, d, f):
        v = rec['cells'][c]
        p = pix[v & 0x7F]
        for y in range(8):
            for x in range(8):
                ci = p[y][7 - x if v & 0x80 else x]
                if ci:
                    img[y0 + y][x0 + x] = ci
    return img


def obj_palettes(rom):
    return [[rom.u16(OBJ_PALETTES + (p * 16 + i) * 2) for i in range(16)] for p in range(4)]


def rgb(c):
    # 5비트 → 8비트는 MesenCE 화면과 같게 (v << 3) | (v >> 2).
    return tuple((v << 3) | (v >> 2) for v in (c & 31, (c >> 5) & 31, (c >> 10) & 31))


# 색 번호 보기: 번호끼리 잘 구분되는 고정 색.
INDEX_COLORS = [(0, 0, 0), (32, 32, 32), (230, 25, 75), (60, 180, 75), (255, 225, 25), (0, 130, 200),
                (245, 130, 48), (145, 30, 180), (70, 240, 240), (240, 50, 230), (210, 245, 60),
                (250, 190, 212), (0, 128, 128), (220, 190, 255), (170, 110, 40), (255, 255, 255)]


def bbox(img):
    pts = [(x, y) for y, row in enumerate(img) for x, v in enumerate(row) if v]
    if not pts:
        return None
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def decode_set(rom, s):
    rec = set_record(rom, s)
    if rec is None:
        return None
    tiles, end = set_tiles(rom, rec)
    rec['end'] = end
    rec['tile_data'] = tiles
    rec['frames'] = {(d, f): frame(rec, tiles, d, f) for d in DIRS for f in (0, 1)}
    return rec


def npc_users(rom):
    """세트 → 그 세트를 쓰는 인물 목록 이름(맵 「BC/BD」, 「BC/BD 대체」, 「숨은 목록」)."""
    import dq5npc
    users = {}
    for la, name in dq5npc.all_lists(rom):
        for a, _ in dq5npc.list_entries(rom, la):
            for night in (False, True):
                f = dq5npc.parse(rom, a, night)
                if f and f['gfx'] < GFX_COUNT:
                    users.setdefault(f['gfx'], set()).add(name)
    return users


def sheet(rec, pal, scale=1, grid=False, index=False):
    """행 아래·왼쪽·오른쪽·위, 열 프레임 0·1 시트. 투명 배경."""
    from PIL import Image, ImageDraw

    colors = INDEX_COLORS if index else [rgb(c) for c in pal]
    W, H = FRAME_W * 2, FRAME_H * len(DIRS)
    img = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    for r, d in enumerate(DIRS):
        for f in (0, 1):
            for y, row in enumerate(rec['frames'][(d, f)]):
                for x, v in enumerate(row):
                    if v:
                        img.putpixel((f * FRAME_W + x, r * FRAME_H + y), colors[v] + (255,))
    if scale > 1:
        img = img.resize((W * scale, H * scale), Image.NEAREST)
    if grid:
        dr = ImageDraw.Draw(img)
        k = max(scale, 1)
        for x in range(0, W + 1, 8):
            dr.line([(x * k, 0), (x * k, H * k)], fill=(128, 128, 128, 160) if x % FRAME_W else (255, 0, 0, 200))
        for y in range(0, H + 1, 8):
            dr.line([(0, y * k), (W * k, y * k)], fill=(128, 128, 128, 160) if y % FRAME_H else (255, 0, 0, 200))
    return img


def matrix_text(rec):
    """프레임마다 색 번호 행렬(. 투명, 16진 한 글자)."""
    out = []
    for d in DIRS:
        for f in (0, 1):
            out.append(f'# {d} {f}')
            for row in rec['frames'][(d, f)]:
                out.append(''.join('%X' % v if v else '.' for v in row))
    return '\n'.join(out) + '\n'


LAYOUT_GROUP = {'overlap': '8타일(머리+몸, 세트 80~)', 'simple': '6타일(세트 00~6F)'}


def export_all(rom, outdir, scale=4, grid=False, index=True):
    """모든 세트·맵 OBJ 타일의 그림을 outdir 에 쓰고 index.json 과 같은 항목 목록을 돌려준다.

    항목마다 cat('sprites')·group·title·path(outdir 기준 상대 경로)·w·h 가 있다(dq5gallery.py 가 그대로 쓴다).
    세트 시트 항목에는 set·gfx·layout·palette·tiles·colors·size·down_size·bbox·record·data·maps 가 더 붙고,
    색 번호 보기는 group '색 번호 보기' 인 따로 된 항목이다. 맵 OBJ 타일 항목에는 map_object·where 가 붙는다.
    """
    if isinstance(rom, (bytes, bytearray)):
        rom = Rom(rom)
    os.makedirs(outdir, exist_ok=True)
    pals = obj_palettes(rom)
    users = npc_users(rom)
    gfx_of = {}
    for g in range(GFX_COUNT):
        gfx_of.setdefault(gfx_set(rom, g), []).append(g)
    entries = []

    def save(img, name):
        img.save(os.path.join(outdir, name))
        return {'cat': 'sprites', 'path': name, 'w': img.width, 'h': img.height}

    for s in range(SET_COUNT):
        rec = decode_set(rom, s)
        if rec is None:
            continue
        name = f'set{s:02X}'
        gl = gfx_of.get(s, [])
        title = f'세트 {s:02X}' + (' · 그림 ' + ' '.join(f'{g:02X}' for g in gl) if gl else ' · 그림 없음')
        e = save(sheet(rec, pals[rec['palette']], scale, grid), name + '.png')
        e.update({'group': LAYOUT_GROUP[rec['layout']], 'title': title, 'set': s, 'gfx': gl,
                  'layout': rec['layout'], 'palette': rec['palette'], 'tiles': rec['tiles'],
                  'record': f'{rec["record"]:06X}', 'data': f'{rec["data"]:06X}', 'data_end': f'{rec["end"]:06X}',
                  'frame': [FRAME_W, FRAME_H], 'scale': scale, 'note': '행 아래·왼쪽·오른쪽·위, 열 프레임 0·1'})
        used = set(v for img in rec['frames'].values() for row in img for v in row if v)
        e['colors'] = len(used)
        boxes = [b for b in (bbox(img) for img in rec['frames'].values()) if b]
        if boxes:
            e['bbox'] = [min(b[0] for b in boxes), min(b[1] for b in boxes),
                         max(b[2] for b in boxes), max(b[3] for b in boxes)]
            e['size'] = [e['bbox'][2] - e['bbox'][0] + 1, e['bbox'][3] - e['bbox'][1] + 1]
            down = bbox(rec['frames'][('down', 0)])
            if down:
                e['down_size'] = [down[2] - down[0] + 1, down[3] - down[1] + 1]
        e['maps'] = sorted(set(m for g in gl for m in users.get(g, ())))
        entries.append(e)
        if index:
            with open(os.path.join(outdir, name + '.txt'), 'w') as fp:
                fp.write(matrix_text(rec))
            e['matrix'] = name + '.txt'
            ie = save(sheet(rec, pals[rec['palette']], scale, True, True), name + '-index.png')
            ie.update({'group': '색 번호 보기', 'title': title + ' 색 번호', 'set': s, 'matrix': name + '.txt'})
            entries.append(ie)
    for k, m in enumerate(map_objects(rom)):
        name = f'mapobj{k:02X}'
        for idx in ((False, True) if index else (False,)):
            e = save(tile_sheet(m['tiles'], pals[0], scale, idx), name + ('-index' if idx else '') + '.png')
            e.update({'group': '맵 OBJ 타일' + (' 색 번호' if idx else ''), 'title': f'{m["where"]} {m["data"]:06X}',
                      'map_object': k, 'where': m['where'], 'entry': f'{m["entry"]:06X}', 'data': f'{m["data"]:06X}',
                      'data_end': f'{m["end"]:06X}', 'tiles': len(m['tiles']), 'reserve': m['reserve'],
                      'packed': m['packed'], 'scale': scale, 'note': '배치 모름, 팔레트 0 으로 칠함'})
            entries.append(e)
    with open(os.path.join(outdir, 'index.json'), 'w') as fp:
        json.dump(entries, fp, ensure_ascii=False, indent=1)
    return entries


def tile_sheet(tiles, pal, scale=1, index=False):
    """타일을 한 줄 16개로 늘어놓은 그림(맵 OBJ 타일용). 배치를 모르므로 팔레트는 0 번으로 칠한다."""
    from PIL import Image, ImageDraw

    colors = INDEX_COLORS if index else [rgb(c) for c in pal]
    rows = max(1, (len(tiles) + 15) // 16)
    img = Image.new('RGBA', (128, rows * 8), (0, 0, 0, 0))
    for i, t in enumerate(tiles):
        for y, row in enumerate(pixels(t)):
            for x, v in enumerate(row):
                if v:
                    img.putpixel(((i % 16) * 8 + x, (i // 16) * 8 + y), colors[v] + (255,))
    if scale > 1:
        img = img.resize((img.width * scale, img.height * scale), Image.NEAREST)
    if index:
        dr = ImageDraw.Draw(img)
        for x in range(0, 129, 8):
            dr.line([(x * scale, 0), (x * scale, img.height)], fill=(128, 128, 128, 160))
        for y in range(0, rows * 8 + 1, 8):
            dr.line([(0, y * scale), (img.width, y * scale)], fill=(128, 128, 128, 160))
    return img


def oam_groups(oam):
    """보이는 OAM 항목을 이어진 슬롯끼리 같은 인물로 묶는다. 인물 하나는 OBJ 6개(6타일) 또는 8개(8타일)다."""
    items = []
    for i in range(128):
        x, y, t, a = oam[i * 4:i * 4 + 4]
        h = oam[512 + (i >> 2)] >> ((i & 3) * 2) & 3
        x |= (h & 1) << 8
        if y >= 224 or h >> 1:
            items.append(None)
            continue
        items.append((x - 512 if x >= 256 else x, y + 1, t | (a & 1) << 8, a))
    return items


def oam_box(items, vram):
    """OAM 항목 몇 개를 왼쪽 위 기준 상자에 (팔레트, 색 번호) 로 그린다. 낮은 슬롯이 위."""
    x0, y0 = min(it[0] for it in items), min(it[1] for it in items)
    box = {}
    for x, y, t, a in reversed(items):
        p = pixels(vram[0xC000 + t * 32:][:32])
        for yy in range(8):
            for xx in range(8):
                v = p[7 - yy if a & 0x80 else yy][7 - xx if a & 0x40 else xx]
                if v:
                    box[(x - x0 + xx, y - y0 + yy)] = ((a >> 1) & 7, v)
    return x0, y0, box


def compare(rom, wram, vram, oam, cgram, stats, verbose=True):
    """인물 슬롯마다: 세트 타일이 VRAM 에 그대로 있는지, 칸 목록(7E:8060-)이 레코드와 같은지,
    그 세트 타일을 쓰는 OAM 묶음이 디코더 프레임 하나와 픽셀째로 같은지. 결과는 stats 에 더한다."""
    w16 = lambda a: wram[a] | wram[a + 1] << 8
    pals = obj_palettes(rom)
    cg = [cgram[256 + i * 2] | cgram[257 + i * 2] << 8 for i in range(64)]
    pal_ok = [all(cg[p * 16 + i] == pals[p][i] for i in range(1, 16)) for p in range(4)]
    stats['palette'] = stats.get('palette', []) + [pal_ok]
    items = oam_groups(oam)
    seen = set()
    for slot in range(0x20):
        g = wram[0x3220 + slot]
        if g == 0xFF or g >= GFX_COUNT:
            continue
        lst = w16(0x8000 + wram[0x3200 + slot])
        cells = [w16(lst + i * 2) for i in range(48)]
        s = gfx_set(rom, g)
        rec = decode_set(rom, s)
        base = (cells[0] & 0x1FF) - (rec['cells'][0] & 0x7F)
        if (s, base) in seen or base < 0:
            continue
        seen.add((s, base))
        tiles = rec['tile_data']
        vt = sum(1 for i, t in enumerate(tiles) if vram[0xC000 + (base + i) * 32:][:32] == t)
        cell_ok = sum(1 for i in range(48) if (cells[i] & 0x1FF) == base + (rec['cells'][i] & 0x7F)
                      and bool(cells[i] & 0x4000) == bool(rec['cells'][i] & 0x80))
        if cell_ok < 48:
            continue  # 쓰지 않는 슬롯(지난 맵의 칸 목록이 남아 있음)
        n = 6 if rec['layout'] == 'simple' else 8
        inset = lambda it: it and base <= it[2] < base + len(tiles)
        shown = []
        i = 0
        while i < 128:
            if inset(items[i]) and all(inset(items[j]) for j in range(i, min(i + n, 128))):
                x0, y0, box = oam_box(items[i:i + n], vram)
                hit = None
                for (d, f), img in rec['frames'].items():
                    want = {(x, y): (rec['palette'], v) for y, row in enumerate(img) for x, v in enumerate(row) if v}
                    b = bbox(img)
                    if b and {(x - b[0], y - b[1]): pv for (x, y), pv in want.items()} == \
                            {(x - min(k[0] for k in box), y - min(k[1] for k in box)): pv for (x, y), pv in box.items()}:
                        hit = f'{d}{f} {len(want)}px'
                        stats.setdefault('frames', set()).add((s, d, f))
                        break
                shown.append(f'({x0},{y0}) {hit or "다름"}')
                stats['groups'] = stats.get('groups', 0) + 1
                stats['hits'] = stats.get('hits', 0) + (hit is not None)
                i += n
            else:
                i += 1
        st = stats.setdefault('sets', {}).setdefault(s, [0, 0])
        st[0] += vt
        st[1] += len(tiles)
        if verbose:
            print(f'슬롯 {slot:02X} 그림 {g:02X} 세트 {s:02X} 타일 {base:03X}~: VRAM {vt}/{len(tiles)}, 칸 {cell_ok}/48, '
                  f'OAM {"; ".join(shown) if shown else "화면 밖"}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('--out', help='시트·index.json 을 쓸 폴더(work/ 아래)')
    ap.add_argument('--scale', type=int, default=4)
    ap.add_argument('--grid', action='store_true', help='보통 시트에도 8픽셀 격자')
    ap.add_argument('--no-index', action='store_true', help='색 번호 보기 시트와 행렬 txt 를 쓰지 않음')
    ap.add_argument('--list', action='store_true', help='세트 목록')
    ap.add_argument('--compare', metavar='DIR', nargs='+', help='lua/dq5sprdump.lua 덤프 폴더(폴더 안 프레임 모두)')
    ap.add_argument('-q', '--quiet', action='store_true', help='--compare 에서 슬롯마다 찍지 않음')
    args = ap.parse_args()
    rom = Rom(open(args.rom, 'rb').read())
    if args.compare:
        stats = {}
        for folder in args.compare:
            for fn in sorted(os.listdir(folder)):
                if not (fn.startswith('w') and fn.endswith('.bin')):
                    continue
                k = fn[1:-4]
                rd = lambda p: open(os.path.join(folder, p % k), 'rb').read()
                if not args.quiet:
                    print(f'== {folder} {k}')
                compare(rom, rd('w%s.bin'), rd('v%s.vram'), rd('o%s.oam'), rd('c%s.cgram'), stats, not args.quiet)
        sets = stats.get('sets', {})
        frames = stats.get('frames', set())
        pl = stats.get('palette', [])
        print(f'덤프 {len(pl)}개, OBJ 팔레트 0~2 가 ROM 과 같은 덤프 {sum(1 for p in pl if all(p[:3]))}개, '
              f'팔레트 3 까지 같은 덤프 {sum(1 for p in pl if all(p))}개')
        print(f'세트 {len(sets)}개, VRAM 타일 {sum(v[0] for v in sets.values())}/{sum(v[1] for v in sets.values())} 같음')
        print(f'OAM 묶음 {stats.get("groups", 0)}개 중 {stats.get("hits", 0)}개가 디코더 프레임과 픽셀째로 같음, '
              f'서로 다른 (세트, 방향, 프레임) {len(frames)}개')
        for s in sorted(set(f[0] for f in frames)):
            print(f'  세트 {s:02X}: ' + ' '.join(sorted(f'{d}{f}' for t, d, f in frames if t == s)))
    if args.list:
        gfx_of = {}
        for g in range(GFX_COUNT):
            gfx_of.setdefault(gfx_set(rom, g), []).append(g)
        for s in range(SET_COUNT):
            rec = set_record(rom, s)
            if rec is None:
                continue
            _, end = set_tiles(rom, rec)
            gl = ' '.join(f'{g:02X}' for g in gfx_of.get(s, []))
            print(f'세트 {s:02X} {rec["layout"]:<7} 팔레트 {rec["palette"]} 타일 {rec["tiles"]:2d} '
                  f'자료 {rec["data"]:06X}-{end - 1:06X} 그림 {gl}')
    if args.out:
        entries = export_all(rom, args.out, args.scale, args.grid, not args.no_index)
        sets = sum(1 for e in entries if 'layout' in e)
        objs = len(set(e['map_object'] for e in entries if 'map_object' in e))
        print(f'인물 세트 {sets}개, 맵 OBJ 타일 {objs}개 → {args.out}')


if __name__ == '__main__':
    main()
