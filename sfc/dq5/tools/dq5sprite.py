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
  python sfc/dq5/tools/dq5sprite.py rom/dq5.sfc --out work/sprites [--scale N] [--grid] [--no-index]
  python sfc/dq5/tools/dq5sprite.py rom/dq5.sfc --list
  python sfc/dq5/tools/dq5sprite.py rom/dq5.sfc --compare DIR   # wNNNN.bin vNNNN.vram oNNNN.oam cNNNN.cgram 덤프와 비교
--out 은 sfc-dq4-assets 의 폴더·파일 규칙대로 1배 그림을 쓴다. 세트마다 `<세트>[-<이름>].png`(행 아래·왼쪽·
오른쪽·위, 열 걸음 프레임 0·1), 색 번호 보기 `-index.png`(8픽셀 격자), 맵 OBJ 타일 `obj-<BC>-<BD>.png`, 그리고
index.json(색 번호 행렬 포함). 이름은 그 세트 인물의 대화 화자 이름으로 붙인다(set_names). 롬에서 나온 그림이므로
이 저장소에는 커밋하지 않는다.
"""
import argparse
import json
import os
import re
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
LYING_W, LYING_H = 24, 16
DIRS = ('down', 'left', 'right', 'up')
# 00:EE5C(6타일)·00:EE8C(8타일)를 방향별 칸 번호로 옮겼다.
SIMPLE_BASE = {'up': 0, 'right': 12, 'down': 24, 'left': 36}
HEAD_BASE = {'up': 0, 'right': 4, 'down': 8, 'left': 12}
BODY_BASE = {'up': 16, 'right': 24, 'down': 32, 'left': 40}
SIMPLE_POS = ((0, 0), (8, 0), (0, 8), (8, 8), (0, 16), (8, 16))
QUAD_POS = ((0, 0), (8, 0), (0, 8), (8, 8))
LYING_SIMPLE = bytes.fromhex('2426282527292a2c2e2b2d2f181a1c191b1d1e20221f21230c0e100d0f111214161315179c9a989d9b99a2a09ea3a19f')  # 1F:D0AC
LYING_OVERLAP = bytes.fromhex('0c0e0d0f080a090b040605078a888b89282a292b2c2e2d2f2022212324262527181a191b1c1e1d1fa2a0a3a1a6a4a7a5')  # 1F:D1B3


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


def mixed_frame(rec, head_dir, body_dir, f):
    """8타일 배치에서 머리와 몸의 방향이 다른 프레임. 몸을 먼저, 머리를 위에 그린다."""
    cells = frame_cells(rec, body_dir, f)[:4] + frame_cells(rec, head_dir, f)[4:]
    return render_cells(rec, rec['tile_data'], cells)


def render_cells(rec, tiles, cells):
    img = [[0] * FRAME_W for _ in range(FRAME_H)]
    pix = [pixels(t) for t in tiles]
    for c, x0, y0 in cells:
        v = rec['cells'][c]
        p = pix[v & 0x7F]
        for y in range(8):
            for x in range(8):
                ci = p[y][7 - x if v & 0x80 else x]
                if ci:
                    img[y0 + y][x0 + x] = ci
    return img


def frame(rec, tiles, d, f):
    """16x24 색 번호 격자(0 = 투명)."""
    return render_cells(rec, tiles, frame_cells(rec, d, f))


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


def rotate_tile(t):
    """1F:D413. 비트 평면마다 8x8 을 전치해 타일을 시계 방향으로 90도 돌린다. 새 (x, y) = 옛 (y, 7-x)."""
    out = bytearray(32)
    for half in (0, 16):
        for k in (0, 1):
            rows = [t[half + y * 2 + k] for y in range(8)]
            for y in range(8):
                out[half + y * 2 + k] = sum(((rows[7 - x] >> (7 - y)) & 1) << (7 - x) for x in range(8))
    return bytes(out)


def lying_cells(rec):
    """1F:D066(6타일, 표 1F:D0AC)·1F:D16D(8타일, 표 1F:D1B3). 누운 모양의 칸 48개 (타일, 좌우 반전, 상하 반전).
    표 값 bit0-6 = 원래 칸 번호, bit7 = 좌우 반전을 더함. 원래 칸의 좌우 반전은 돌린 뒤 상하 반전이 된다."""
    table = LYING_SIMPLE if rec['layout'] == 'simple' else LYING_OVERLAP
    out = []
    for t in table:
        v = rec['cells'][t & 0x7F]
        out.append((v & 0x7F, bool(t & 0x80), bool(v & 0x80)))
    return out


def lying_frame_cells(rec, d):
    """00:EC9B(6타일)·00:F3CE(8타일). 24x16 상자에서 (칸 번호, x, y), 아래에 깔리는 것부터.
    걸음 프레임은 없다. 8타일은 머리 16x16 과 몸 16x16 을 가로로 8픽셀 겹치고, 왼쪽(7E:31E0 bit5)을 볼 때만 머리가 왼쪽."""
    if rec['layout'] == 'simple':
        b = SIMPLE_BASE[d]
        return [(b + i, x, y) for i, (x, y) in enumerate(((16, 0), (8, 0), (0, 0), (16, 8), (8, 8), (0, 8)))]
    head, body = HEAD_BASE[d], BODY_BASE[d]
    hx, bx = (0, 8) if d == 'left' else (8, 0)
    quad = ((8, 0), (0, 0), (8, 8), (0, 8))
    return [(body + i, bx + x, y) for i, (x, y) in enumerate(quad)] + \
        [(head + i, hx + x, y) for i, (x, y) in enumerate(quad)]


def lying_frame(rec, d):
    img = [[0] * LYING_W for _ in range(LYING_H)]
    pix = [pixels(t) for t in rec['lying_tiles']]
    for c, x0, y0 in lying_frame_cells(rec, d):
        tile, hf, vf = rec['lying_cells'][c]
        p = pix[tile]
        for y in range(8):
            for x in range(8):
                ci = p[7 - y if vf else y][7 - x if hf else x]
                if ci:
                    img[y0 + y][x0 + x] = ci
    return img


def decode_set(rom, s):
    rec = set_record(rom, s)
    if rec is None:
        return None
    tiles, end = set_tiles(rom, rec)
    rec['end'] = end
    rec['tile_data'] = tiles
    rec['frames'] = {(d, f): frame(rec, tiles, d, f) for d in DIRS for f in (0, 1)}
    rec['lying_tiles'] = [rotate_tile(t) for t in tiles]
    rec['lying_cells'] = lying_cells(rec)
    rec['lying'] = {d: lying_frame(rec, d) for d in DIRS}
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


def sheet(rec, pal, scale=1, grid=False, index=False, lying=False):
    """행 아래·왼쪽·오른쪽·위, 열 프레임 0·1 시트(누운 모양은 24x16 한 열). 투명 배경."""
    from PIL import Image, ImageDraw

    colors = INDEX_COLORS if index else [rgb(c) for c in pal]
    fw, fh, cols = (LYING_W, LYING_H, (None,)) if lying else (FRAME_W, FRAME_H, (0, 1))
    W, H = fw * len(cols), fh * len(DIRS)
    img = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    for r, d in enumerate(DIRS):
        for k, f in enumerate(cols):
            for y, row in enumerate(rec['lying'][d] if lying else rec['frames'][(d, f)]):
                for x, v in enumerate(row):
                    if v:
                        img.putpixel((k * fw + x, r * fh + y), colors[v] + (255,))
    if scale > 1:
        img = img.resize((W * scale, H * scale), Image.NEAREST)
    if grid:
        dr = ImageDraw.Draw(img)
        k = max(scale, 1)
        for x in range(0, W + 1, 8):
            dr.line([(x * k, 0), (x * k, H * k)], fill=(128, 128, 128, 160) if x % fw else (255, 0, 0, 200))
        for y in range(0, H + 1, 8):
            dr.line([(0, y * k), (W * k, y * k)], fill=(128, 128, 128, 160) if y % fh else (255, 0, 0, 200))
    return img


def matrix(rec):
    """프레임마다 색 번호 행렬(. 투명, 16진 한 글자). {'down0': [줄…], …}."""
    return {f'{d}{f}': [''.join('%X' % v if v else '.' for v in row) for row in rec['frames'][(d, f)]]
            for d in DIRS for f in (0, 1)}


# 05:D98F: 일행 순서마다의 그림 번호(7E:196F). 사람은 05:D9D5[인물 번호], 몬스터(인물 번호 bit7)는
# 05:D9E1[동료 종류]. 사람 인물 번호 n 의 이름은 이름 표 0 의 n-3 번째(파파스·サンチョ·フローラ·ヘンリー·ビアンカ 다섯이
# 대화 화자 이름과 같다). 1·2 번(그림 90·91)은 짝이 맞는 이름이 없어 붙이지 않는다.
PARTY_PEOPLE = 0x05D9D5
PARTY_PEOPLE_COUNT = 12
COMPANION_GFX = 0x05D9E1
COMPANION_KINDS = 0x2A
HERO_CHILD = (0x82, ('パパスのむすこ', '7E:196F = 2E(배 선실의 주인공), 이름 표 1 의 0번'))


def party_names(rom):
    """세트 → (이름, 근거). 일행 표에서 사람과 동료 몬스터의 그림을 이름과 잇는다."""
    from dq5text import string, string_codes, text
    import dq5monster
    names = dict([HERO_CHILD])
    for n in range(3, PARTY_PEOPLE_COUNT):
        g = rom.u8(PARTY_PEOPLE + n)
        nm = text(string_codes(rom, string(rom, 0, n - 3)))
        names.setdefault(gfx_set(rom, g), (nm, f'일행 표 05:D9D5[{n}] = 그림 {g:02X}, 이름 표 0 의 {n - 3}번'))
    kind = {}
    for m in range(dq5monster.COUNT):
        kind.setdefault(dq5monster.record(rom, m)[0x18] & 0x7F,
                        text(string_codes(rom, string(rom, dq5monster.NAMES, m))))
    for k in range(1, COMPANION_KINDS):
        g = rom.u8(COMPANION_GFX + k)
        if k in kind:
            names.setdefault(gfx_set(rom, g), (kind[k], f'동료 표 05:D9E1[{k:02X}] = 그림 {g:02X}'))
    return names


# 자기를 가리키는 말 뒤에 오는 역할 단어(사람을 뜻하는 것만).
SELF_ROLE = re.compile(r'(?:わたし|わたくし|おれ|オレ|ぼく|ボク|わし|ワシ|あたし|アタシ|おいら)(?:は|が|も)[^。！？\n]{0,14}?'
                       r'(兵士|神父|シスター|商人|大臣|学者|船乗り|船長|町長|村長|戦士|踊り子|旅人|門番|大工|漁師|木こり|'
                       r'占い師|司祭|父さん|母さん|じいさん|ばあさん)')
# 일행 표 사람 1·2 번(그림 90·91 → 세트 63·6C). 이름 표 0 에는 짝이 없고, 이름 표 1 의 「！のむすこ」「！のむすめ」를 쓴다.
# 일행 레코드에 인물 번호 1·2 를 넣자 그림 90·91 이 올라왔고, 7E:21B3 bit3(결혼 상대)이 꺼져 있으면 팔레트 0,
# 켜져 있으면 레코드 팔레트 2 로 머리 색이 바뀌었다(1F:D051, 실측).
CHILDREN = {0x63: ('むすこ', '일행 인물 번호 1 = 그림 90(05:D9D5[1]) 실측, 7E:21B3 bit3 에 따라 머리 색 팔레트가 바뀜, 이름 표 1 「！のむすこ」'),
            0x6C: ('むすめ', '일행 인물 번호 2 = 그림 91(05:D9D5[2]) 실측, 7E:21B3 bit3 에 따라 머리 색 팔레트가 바뀜, 이름 표 1 「！のむすめ」')}
SPEAKER = re.compile(r'\{1003\}([^「{}\s]{1,12})「')


def set_names(rom):
    """세트 → (일본어 이름, 근거). 그 세트를 쓰는 인물 엔트리의 대화에서 「이름「…」 꼴로 말하는 이름을 센다.
    이름이 나온 엔트리의 60% 이상, 그 세트를 쓰는 엔트리 전체의 20% 이상인 이름만 붙인다. 그림 번호 넷 이상이
    나눠 쓰는 세트(00 은 14개)는 여러 장면의 대역이라 이름을 붙이지 않는다. 대화로 고른 추정이므로 근거를 함께 준다."""
    import collections
    import dq5npc
    import dq5talk
    said, total, cache = collections.defaultdict(collections.Counter), collections.Counter(), {}
    roles = collections.defaultdict(collections.Counter)
    for la, _ in dq5npc.all_lists(rom):
        for a, _ in dq5npc.list_entries(rom, la):
            for night in (False, True):
                f = dq5npc.parse(rom, a, night)
                if not f or f['gfx'] >= GFX_COUNT:
                    continue
                t = f['talk']
                if t not in cache:
                    try:
                        txt = '\n'.join(dq5talk.talk(rom, t))
                    except (ValueError, KeyError, IndexError):
                        txt = ''
                    cache[t] = (set(SPEAKER.findall(txt)), set(SELF_ROLE.findall(txt)))
                s = gfx_set(rom, f['gfx'])
                total[s] += 1
                said[s]['*'] += bool(cache[t][0])
                for n in cache[t][0]:
                    said[s][n] += 1
                for n in cache[t][1]:
                    roles[s][n] += 1
    names = party_names(rom)
    shared = collections.Counter(gfx_set(rom, g) for g in range(GFX_COUNT))
    for s, c in said.items():
        if shared[s] > 3:
            continue
        top = [(n, k) for n, k in c.most_common() if n != '*']
        if top and top[0][1] >= 0.6 * c['*'] and top[0][1] >= 0.2 * total[s] and \
                (len(top) == 1 or top[1][1] < top[0][1]):
            names.setdefault(s, (top[0][0], f'대화 화자 {top[0][1]}/{total[s]} 엔트리'))
    for s, c in roles.items():
        top = c.most_common()
        if s not in names and shared[s] <= 3 and len(top) == 1 and top[0][1] >= 4 and top[0][1] >= 0.05 * total[s]:
            names[s] = (top[0][0], f'역할: 자기 대사 「わたしは…{top[0][0]}」 {top[0][1]}/{total[s]} 엔트리(다른 역할 말 없음)')
    for s, nm in CHILDREN.items():
        names.setdefault(s, nm)
    return names


def obj_stem(m):
    if m['bc'] == 0x7E:
        return f'obj-field{m["bd"] & 0x7F}'
    return f'obj-{m["bc"]:02X}-' + ('xx' if m['bd'] & 0x7F == 0x7F else f'{m["bd"] & 0x7F:02X}')


# 탈것($1954 = 80 마법의 양탄자, 81 天空城, 82 マスタードラゴン). 배는 탈것이 아니라 주인공 그림 98(세트 64)이다. 타일은 01:C4BE(A 뱅크, X 주소, Y 타일 수, $00 VRAM 워드 주소)가 같은 런 길이 압축(1F:D28B 꼴,
# 7F 도 그대로)을 4bpp 그대로 풀어 VRAM 타일 180 부터 올리고, 칸은 16:F7DD 가 04 뱅크의 바이트(bit7 좌우 반전,
# bit0-6 + 7E:1997(=180))로 만든다. 그리는 것은 00:FC08: 가로 cols × 세로 rows 칸, 프레임 오프셋 = 프레임 × 37E0,
# 방향 오프셋 = 00:EE7C[방향] × 37C0(바이트). 칸 값의 팔레트는 $00(attr). 상하 반전 칸은 01:C42D·01:C160 표가
# 칸 바이트 오프셋으로 더한다. 팔레트 5 는 색이 모두 0 인 그림자(색 연산)다.
VEHICLES = (
    {'id': 0x80, 'name': 'まほうのじゅうたん', 'what': '마법의 양탄자', 'tiles': ((0x16E7BD, 0x2F, 0x180),), 'parts': (
        {'rom': 0x04952A, 'cols': 3, 'rows': 2, 'dir': 0x18, 'frame': 0x0C, 'attr': 0x0000, 'vflip': (), 'at': (0, 8)},
        {'rom': 0x0494CF, 'cols': 3, 'rows': 3, 'dir': 0x24, 'frame': 0x12, 'attr': 0x0000, 'vflip': (), 'at': (0, 0)},
        {'rom': 0x04955B, 'cols': 3, 'rows': 1, 'dir': 0x0C, 'frame': 0x06, 'attr': 0x0A00, 'vflip': (), 'at': (0, 24)})},
    {'id': 0x81, 'name': '天空城', 'what': '天空城', 'tiles': ((0x2B84F0, 0x14, 0x180),), 'parts': (
        {'rom': 0x049634, 'cols': 4, 'rows': 4, 'dir': 0, 'frame': 0, 'attr': 0x0600, 'vflip': (), 'at': (0, 0)},
        {'rom': 0x0496C6, 'cols': 4, 'rows': 2, 'dir': 0, 'frame': 0, 'attr': 0x0A00,
         'vflip': (0x08, 0x0A, 0x0C, 0x0E, 0x18, 0x1A, 0x1C, 0x1E), 'at': (0, 48)})},  # 01:C42D
    {'id': 0x82, 'name': 'マスタードラゴン', 'what': 'マスタードラゴン',
     'tiles': ((0x16EAF2, 0x40, 0x180), (0x16F115, 0x39, 0x1C0)), 'parts': (
        {'rom': 0x049574, 'cols': 4, 'rows': 4, 'dir': 0x60, 'frame': 0x20, 'attr': 0x0000, 'vflip': (), 'at': (0, 0)},
        {'rom': 0x049685, 'cols': 2, 'rows': 2, 'dir': 0x18, 'frame': 0x08, 'attr': 0x0A00,
         'vflip': bytes.fromhex('1c1e24262c2e30323436383a3c3e404244464c4e54565c5e'), 'at': (8, 56)})},  # 01:C160
)
MAP_PALETTES = 0x019A12
MAP_OBJECT_PLACES = 0x16F862


def map_object_places(rom):
    """16:F60D. 맵 OBJ 타일로 그리는 물체 74개. 9바이트 항목, FF 로 끝.
    [BC(FE 면 필드)][BD(아래 7비트, 7F 면 그룹 전부)][X 칸][Y 칸][가로 칸 수(bit0-5), bit7 이야기 조건(21:8000), bit6 반대]
    [세로 칸 수][bit0·1 X·Y 의 위 비트, bit2-4 OBJ 팔레트, bit5-6 우선순위(→ 7E:33A0)][칸 바이트 주소 16비트(16 뱅크)].
    X·Y 가 128 이면 나중에 스크립트가 놓는다. 칸 바이트는 bit7 좌우 반전, bit0-6 + 7E:1997(맵 OBJ 타일 첫 번호)이고
    16:F7DD 가 탈것 슬롯(7E:3220 = FE)의 칸 목록으로 만들어 00:FC08 이 그린다."""
    out, a = [], MAP_OBJECT_PLACES
    while rom.u8(a) != 0xFF:
        b = [rom.u8(a + i) for i in range(9)]
        ptr = 0x160000 | b[7] | b[8] << 8
        cols, rows = b[4] & 0x3F, b[5]
        out.append({'entry': a, 'bc': b[0], 'bd': b[1] & 0x7F, 'x': b[2] | (b[6] & 1) << 8,
                    'y': b[3] | (b[6] >> 1 & 1) << 8, 'cols': cols, 'rows': rows,
                    'cond': (b[4] >> 6) if b[4] & 0x80 else None, 'palette': (b[6] >> 2) & 7, 'priority': (b[6] >> 5) & 3,
                    'cells_at': ptr, 'cells': [rom.u8(ptr + i) for i in range(cols * rows)]})
        a += 9
    return out


def map_object_tiles_for(rom, bc, bd):
    """맵(BC, BD)에 올라오는 맵 OBJ 타일(1F:D59A 항목). 필드는 BC = FE 를 세계 BD 의 7E 항목으로 찾는다."""
    for m in map_objects(rom):
        if bc == 0xFE and m['bc'] == 0x7E and m['bd'] & 0x7F == bd:
            return m
        if m['bc'] == bc and (m['bd'] & 0x7F) in (bd, 0x7F):
            return m
    return None


def map_line_colors(rom, bc, bd, line):
    """그 맵에서 CGRAM 16색 줄 line 을 덮는 01:9A12 항목의 색(없으면 None)."""
    for e in map_palettes(rom):
        if e['line'] == line and e['bc'] == bc and e['bd'] in (bd, 0xFF):
            return e['colors']
    return None


def map_palettes(rom):
    """01:996A. 맵마다 덮는 16색 줄. 0x23바이트 항목 [BC(FE 면 필드)][BD(FF 면 그룹 전부, 필드면 세계)]
    [플래그 번호(FF 면 늘)][마스크][CGRAM 16색 줄 번호][색 1~15], FF 로 끝. 0 번 색은 0. 줄 0B 가 OBJ 팔레트 3."""
    out, a = [], MAP_PALETTES
    while rom.u8(a) != 0xFF:
        out.append({'entry': a, 'bc': rom.u8(a), 'bd': rom.u8(a + 1), 'flag': rom.u8(a + 2), 'mask': rom.u8(a + 3),
                    'line': rom.u8(a + 4), 'colors': [0] + [rom.u16(a + 5 + i * 2) for i in range(15)]})
        a += 0x23
    return out


def map_obj_palette3(rom, bc, bd):
    """맵(BC, BD)에서 OBJ 팔레트 3(줄 0B)을 덮는 첫 항목. 플래그 조건은 보지 않는다."""
    for e in map_palettes(rom):
        if e['line'] == 0x0B and e['bc'] == bc and e['bd'] in (bd, 0xFF):
            return e
    return None


# 'at' 은 부분들의 상자 왼쪽 위를 한 장에 놓는 자리(px). 탈것 장면 덤프의 OAM 에서 방향·프레임과 상관없이 같았다.
# 앞 부분일수록 OAM 앞 슬롯(위에 그려짐): 양탄자는 부분 1, 天空城·マスタードラゴン 은 부분 1(그림자 아래).


def vehicle_composite(frs, pals, scale=1, index=False):
    """부분을 'at' 자리에 겹친 한 장. 행 아래·왼쪽·오른쪽·위, 열 프레임(부분마다 프레임 수가 같다)."""
    from PIL import Image

    W = max(fr['part']['at'][0] + fr['part']['cols'] * 8 for fr in frs)
    H = max(fr['part']['at'][1] + fr['part']['rows'] * 8 for fr in frs)
    directional = frs[0]['part']['dir'] != 0
    dirs = DIRS if directional else (None,)
    nf = frs[0]['nframes'] if directional else 1
    im = Image.new('RGBA', (W * nf, H * len(dirs)), (0, 0, 0, 0))
    for r, d in enumerate(dirs):
        for f in range(nf):
            for fr in reversed(frs):
                g = fr['frames'].get((d, f)) if d else next(iter(fr['frames'].values()))
                if not g:
                    continue
                ax, ay = fr['part']['at']
                for y, row in enumerate(g):
                    for x, pv in enumerate(row):
                        if pv:
                            pal, ci = pv
                            col = INDEX_COLORS[ci] if index else ((48, 48, 48) if pal == 5 else rgb(pals[pal][ci]))
                            im.putpixel((f * W + ax + x, r * H + ay + y), col + ((160 if pal == 5 and not index else 255),))
    if scale > 1:
        im = im.resize((im.width * scale, im.height * scale), Image.NEAREST)
    return im


DIR_INDEX = {'up': 0, 'right': 1, 'down': 2, 'left': 3}  # 00:EE7C
FIELD_OBJ_PALETTE3 = 0x019BFF  # 필드의 OBJ 팔레트 3(덤프 CGRAM 과 같음)


def vehicle_tiles(rom, v):
    tiles = {}
    for a, n, t0 in v['tiles']:
        data, _ = unpack(rom, a, False)
        for i in range(n):
            tiles[t0 + i] = bytes(data[i * 32:i * 32 + 32])
    return tiles


def vehicle_part_cells(rom, part):
    """칸 값 목록(OAM 이름+속성 16비트). 상하 반전 표를 반영."""
    frames = max(1, part['dir'] // part['frame']) if part['frame'] else 1
    n = part['cols'] * part['rows'] * frames * (4 if part['dir'] else 1)
    out = []
    for i in range(n):
        b = rom.u8(part['rom'] + i)
        out.append(0x180 + (b & 0x7F) | (0x4000 if b & 0x80 else 0) | part['attr'])
    for off in part['vflip']:
        if off // 2 < len(out):
            out[off // 2] |= 0x8000
    return out, frames


def vehicle_frames(rom, v):
    """부분마다 {(방향, 프레임): (팔레트, 색 번호) 격자}."""
    tiles = vehicle_tiles(rom, v)
    pix = {t: pixels(b) for t, b in tiles.items()}
    out = []
    for part in v['parts']:
        cells, frames = vehicle_part_cells(rom, part)
        W, H = part['cols'] * 8, part['rows'] * 8
        fr = {}
        for d in DIRS:
            for f in range(frames):
                base = (DIR_INDEX[d] * part['dir'] + f * part['frame']) // 2 if part['dir'] else 0
                img = [[None] * W for _ in range(H)]
                for k in range(part['cols'] * part['rows']):
                    c = cells[base + k]
                    p = pix.get(c & 0x1FF)
                    if p is None:
                        continue
                    x0, y0 = (k % part['cols']) * 8, (k // part['cols']) * 8
                    for y in range(8):
                        for x in range(8):
                            ci = p[7 - y if c & 0x8000 else y][7 - x if c & 0x4000 else x]
                            if ci:
                                img[y0 + y][x0 + x] = ((c >> 9) & 7, ci)
                fr[(d, f)] = img
                if not part['dir']:
                    break
            if not part['dir']:
                break
        out.append({'part': part, 'frames': fr, 'cells': cells, 'nframes': frames})
    return out


def vehicle_sheet(fr, pals, scale=1, index=False):
    """행 아래·왼쪽·오른쪽·위, 열 프레임. 방향이 없는 부분은 한 장."""
    from PIL import Image

    keys = sorted(fr['frames'])
    dirs = [d for d in DIRS if any(k[0] == d for k in keys)]
    nf = max(k[1] for k in keys) + 1
    img0 = next(iter(fr['frames'].values()))
    W, H = len(img0[0]), len(img0)
    im = Image.new('RGBA', (W * nf, H * len(dirs)), (0, 0, 0, 0))
    for r, d in enumerate(dirs):
        for f in range(nf):
            g = fr['frames'].get((d, f))
            if not g:
                continue
            for y, row in enumerate(g):
                for x, pv in enumerate(row):
                    if pv:
                        pal, ci = pv
                        col = INDEX_COLORS[ci] if index else ((48, 48, 48) if pal == 5 else rgb(pals[pal][ci]))
                        im.putpixel((f * W + x, r * H + y), col + ((160 if pal == 5 and not index else 255),))
    if scale > 1:
        im = im.resize((im.width * scale, im.height * scale), Image.NEAREST)
    return im


LAYOUT_GROUP = {'overlap': '8타일(머리+몸, 세트 80~)', 'simple': '6타일(세트 00~6F)'}


def export_all(rom, outdir, scale=1, grid=False, index=True):
    """모든 세트·맵 OBJ 타일의 그림을 outdir 에 쓰고 index.json 과 같은 항목 목록을 돌려준다.

    파일 이름은 sfc-dq4-assets 의 규칙 `<번호>[-<이름>][-<변형>].png`: 세트는 `82-パパスのむすこ.png`,
    색 번호 보기는 `-index`, 맵 OBJ 타일은 `obj-<BC>-<BD>`(필드는 `obj-field<세계>`). 기본은 1배.
    항목마다 cat('sprites')·group·title·path(outdir 기준 상대 경로)·w·h 가 있다(dq5gallery.py 가 그대로 쓴다).
    세트 항목에는 set·name·gfx·layout·palette·tiles·colors·size·down_size·bbox·record·data·maps·matrix 가 붙는다.
    """
    if isinstance(rom, (bytes, bytearray)):
        rom = Rom(rom)
    os.makedirs(outdir, exist_ok=True)
    pals = obj_palettes(rom)
    users = npc_users(rom)
    names = set_names(rom)
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
        nm, why = names.get(s, (None, None))
        stem = f'{s:02X}' + (f'-{nm}' if nm else '')
        gl = gfx_of.get(s, [])
        title = f'{s:02X}' + (f' {nm}' if nm else '') + (' · 그림 ' + ' '.join(f'{g:02X}' for g in gl) if gl else ' · 그림 없음')
        e = save(sheet(rec, pals[rec['palette']], scale, grid), stem + '.png')
        e.update({'group': LAYOUT_GROUP[rec['layout']], 'title': title, 'set': s, 'name': nm, 'name_from': why,
                  'gfx': gl, 'layout': rec['layout'], 'palette': rec['palette'], 'tiles': rec['tiles'],
                  'record': f'{rec["record"]:06X}', 'data': f'{rec["data"]:06X}', 'data_end': f'{rec["end"]:06X}',
                  'frame': [FRAME_W, FRAME_H], 'scale': scale, 'note': '행 아래·왼쪽·오른쪽·위, 열 걸음 프레임 0·1'})
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
        e['matrix'] = matrix(rec)
        entries.append(e)
        le = save(sheet(rec, pals[rec['palette']], scale, grid, lying=True), stem + '-lying.png')
        le.update({'group': '누운 모양', 'title': title + ' 누운 모양', 'set': s,
                   'note': '행 아래·왼쪽·오른쪽·위, 24x16, 걸음 프레임 없음(7E:31C0 bit0)'})
        entries.append(le)
        if index:
            ie = save(sheet(rec, pals[rec['palette']], scale, True, True), stem + '-index.png')
            ie.update({'group': '색 번호 보기', 'title': title + ' 색 번호', 'set': s})
            entries.append(ie)
            ie = save(sheet(rec, pals[rec['palette']], scale, True, True, True), stem + '-lying-index.png')
            ie.update({'group': '색 번호 보기', 'title': title + ' 누운 모양 색 번호', 'set': s})
            entries.append(ie)
    vpals = [list(p) for p in pals] + [[0] * 16 for _ in range(4)]
    vpals[3] = [rom.u16(FIELD_OBJ_PALETTE3 + i * 2) for i in range(16)]
    for v in VEHICLES:
        frs = vehicle_frames(rom, v)
        stem = f'v{v["id"]:02X}' + (f'-{v["name"]}' if v['name'] else '')
        for idx in ((False, True) if index else (False,)):
            e = save(vehicle_composite(frs, vpals, scale, idx), stem + ('-index' if idx else '') + '.png')
            e.update({'group': '탈것' + (' 색 번호' if idx else ''), 'title': f'{v["what"]} 전체', 'vehicle': v['id'],
                      'vehicle_name': v['name'], 'part': 0, 'rom': f'{v["parts"][0]["rom"]:06X}',
                      'tile_data': [f'{a:06X}' for a, _, _ in v['tiles']], 'cols': None, 'rows': None,
                      'frames_per_dir': frs[0]['nframes'], 'directional': bool(v['parts'][0]['dir']),
                      'obj_palette': None, 'scale': scale,
                      'note': '부분을 덤프에서 잰 자리에 겹친 한 장. 행 아래·왼쪽·오른쪽·위, 열 프레임'})
            entries.append(e)
        for k, fr in enumerate(frs):
            part = fr['part']
            stem = f'v{v["id"]:02X}' + (f'-{v["name"]}' if v['name'] else '') + f'-{k + 1}'
            for idx in ((False, True) if index else (False,)):
                e = save(vehicle_sheet(fr, vpals, scale, idx), stem + ('-index' if idx else '') + '.png')
                e.update({'group': '탈것' + (' 색 번호' if idx else ''), 'title': f'{v["what"]} 부분 {k + 1}',
                          'vehicle': v['id'], 'vehicle_name': v['name'], 'part': k + 1,
                          'rom': f'{part["rom"]:06X}', 'tile_data': [f'{a:06X}' for a, _, _ in v['tiles']],
                          'cols': part['cols'], 'rows': part['rows'], 'frames_per_dir': fr['nframes'],
                          'directional': bool(part['dir']), 'obj_palette': (part['attr'] >> 9) & 7, 'scale': scale,
                          'note': '행 아래·왼쪽·오른쪽·위, 열 프레임. 팔레트 5 는 그림자(반투명 회색으로 칠함)'})
                entries.append(e)
    for k, mp in enumerate(map_object_places(rom)):
        mo = map_object_tiles_for(rom, mp['bc'], mp['bd'])
        if mo is None:
            continue
        line = 8 + mp['palette']
        pal = map_line_colors(rom, mp['bc'], mp['bd'], line)
        if pal is None:
            pal = vpals[mp['palette']] if mp['bc'] == 0xFE or mp['palette'] < 3 else [0] * 16
        where = 'field' if mp['bc'] == 0xFE else f'{mp["bc"]:02X}-' + ('xx' if mp['bd'] == 0x7F else f'{mp["bd"]:02X}')
        stem = f'objat-{where}-{k:02X}'
        for idx in ((False, True) if index else (False,)):
            img = place_image(mo['tiles'], mp, pal, scale, idx)
            e = save(img, stem + ('-index' if idx else '') + '.png')
            e.update({'group': '맵 OBJ 물체' + (' 색 번호' if idx else ''), 'title': f'{mo["where"]} 물체 {k:02X}',
                      'map_place': k, 'where': mo['where'], 'rom': f'{mp["entry"]:06X}', 'cells_at': f'{mp["cells_at"]:06X}',
                      'cols': mp['cols'], 'rows': mp['rows'], 'at': None if mp['x'] == 128 else [mp['x'], mp['y']],
                      'obj_palette': mp['palette'], 'scale': scale,
                      'note': '16:F862 항목대로 맵 OBJ 타일을 늘어놓은 것. 자리가 없는(128) 것은 스크립트가 놓음'})
            entries.append(e)
    seen = set()
    for k, m in enumerate(map_objects(rom)):
        stem = obj_stem(m)
        if stem in seen:
            stem += f'-{k:02X}'
        seen.add(stem)
        bd = m['bd'] & 0x7F
        mp = map_obj_palette3(rom, m['bc'], 0xFF if bd == 0x7F else bd) if m['bc'] != 0x7E else None
        pal = mp['colors'] if mp else vpals[3] if m['bc'] == 0x7E else pals[0]
        for idx in ((False, True) if index else (False,)):
            e = save(tile_sheet(m['tiles'], pal, scale, idx), stem + ('-index' if idx else '') + '.png')
            e.update({'group': '맵 OBJ 타일' + (' 색 번호' if idx else ''), 'title': f'{m["where"]} {m["data"]:06X}',
                      'map_object': k, 'where': m['where'], 'entry': f'{m["entry"]:06X}', 'data': f'{m["data"]:06X}',
                      'data_end': f'{m["end"]:06X}', 'tiles': len(m['tiles']), 'reserve': m['reserve'],
                      'packed': m['packed'], 'scale': scale,
                      'palette_from': (f'01:{mp["entry"] & 0xFFFF:04X}' if mp else '필드 OBJ 팔레트 3' if m['bc'] == 0x7E else '모름(팔레트 0)'),
                      'note': '배치 모름. 팔레트는 그 맵의 OBJ 팔레트 3(01:9A12 표)'})
            entries.append(e)
    with open(os.path.join(outdir, 'index.json'), 'w') as fp:
        json.dump(index_document(entries, pals), fp, ensure_ascii=False, indent=1)
    return entries


def cpu(a):
    return f'{a >> 16:02X}:${a & 0xFFFF:04X}'


def index_document(entries, pals):
    """sfc-dq4-assets 의 index.json 꼴(fc/dq4/sprites 와 같은 키): note·obj_palettes·sprites."""
    hexc = lambda c: f'{c:04X}'  # noqa: E731
    sprites = []
    for e in entries:
        if e.get('group') in ('색 번호 보기', '맵 OBJ 타일 색 번호', '탈것 색 번호', '맵 OBJ 물체 색 번호'):
            continue
        if 'layout' in e:
            sprites.append({
                'file': e['path'], 'set': e['set'], 'label': e['name'], 'label_from': e['name_from'], 'gfx': e['gfx'],
                'rotated': False, 'size': [e['w'], e['h']], 'frame': e['frame'],
                'rows': ['아래', '왼쪽', '오른쪽', '위'], 'cols': ['걸음 0', '걸음 1'],
                'rom': cpu(int(e['record'], 16)), 'data': cpu(int(e['data'], 16)), 'data_end': cpu(int(e['data_end'], 16)),
                'layout': e['layout'], 'obj_palette': e['palette'], 'colors': [hexc(c) for c in pals[e['palette']]],
                'tiles': e['tiles'], 'used_colors': e['colors'], 'bbox': e.get('bbox'), 'opaque_size': e.get('size'),
                'places': e['maps'], 'index_file': e['path'][:-4] + '-index.png',
                'frames': [{'row': r, 'step': int(k[-1]), 'matrix': m}
                           for k, m in e['matrix'].items()
                           for r in [{'down': '아래', 'left': '왼쪽', 'right': '오른쪽', 'up': '위'}[k[:-1]]]]})
        elif e.get('group') == '누운 모양':
            sprites.append({'file': e['path'], 'set': e['set'], 'rotated': True, 'size': [e['w'], e['h']],
                            'frame': [LYING_W, LYING_H], 'rows': ['아래', '왼쪽', '오른쪽', '위'], 'cols': ['누움'],
                            'index_file': e['path'][:-4] + '-index.png'})
        elif 'vehicle' in e and not e['group'].endswith('색 번호'):
            sprites.append({'file': e['path'], 'vehicle': e['vehicle'], 'label': e['vehicle_name'], 'part': e['part'],
                            'rom': cpu(int(e['rom'], 16)), 'data': [cpu(int(a, 16)) for a in e['tile_data']],
                            'cols': e['cols'], 'rows': e['rows'], 'frames_per_dir': e['frames_per_dir'],
                            'rows_dirs': ['아래', '왼쪽', '오른쪽', '위'] if e['directional'] else [],
                            'obj_palette': e['obj_palette'], 'size': [e['w'], e['h']],
                            'index_file': e['path'][:-4] + '-index.png'})
        elif 'map_place' in e and not e['group'].endswith('색 번호'):
            sprites.append({'file': e['path'], 'map_place': e['map_place'], 'where': e['where'], 'rom': cpu(int(e['rom'], 16)),
                            'cells_at': cpu(int(e['cells_at'], 16)), 'cols': e['cols'], 'rows': e['rows'], 'at': e['at'],
                            'obj_palette': e['obj_palette'], 'size': [e['w'], e['h']], 'index_file': e['path'][:-4] + '-index.png'})
        elif 'map_object' in e:
            sprites.append({'file': e['path'], 'map_object': e['map_object'], 'where': e['where'],
                            'rom': cpu(int(e['entry'], 16)), 'data': cpu(int(e['data'], 16)),
                            'data_end': cpu(int(e['data_end'], 16)), 'tiles': e['tiles'], 'reserve': e['reserve'],
                            'packed': e['packed'], 'size': [e['w'], e['h']], 'obj_palette': None,
                            'index_file': e['path'][:-4] + '-index.png'})
    return {'note': '세트 그림은 32x96: 행 아래·왼쪽·오른쪽·위, 열 걸음 0·1(프레임 16x24). -lying 은 누운 모양 24x16 한 열. '
                    '색 번호 0 투명, colors 는 OBJ 팔레트의 15비트 BGR 색 16개(0번은 투명 자리). matrix 는 프레임마다 색 번호(. 투명). '
                    'obj-*.png 는 맵 OBJ 타일을 한 줄 16개로 늘어놓은 것(배치·팔레트 모름, 팔레트 0 으로 칠함). '
                    'rom 은 세트 레코드(맵 OBJ 는 1F:D59A 항목) 주소, data 는 타일 자료.',
            'obj_palettes': [[hexc(c) for c in p] for p in pals], 'sprites': sprites}


def place_image(tiles, mp, pal, scale=1, index=False):
    """맵 OBJ 물체 하나를 가로 × 세로 칸으로. 칸 값의 타일이 맵 OBJ 타일 수를 넘으면 비워 둔다."""
    from PIL import Image

    colors = INDEX_COLORS if index else [rgb(c) for c in pal]
    img = Image.new('RGBA', (max(1, mp['cols']) * 8, max(1, mp['rows']) * 8), (0, 0, 0, 0))
    for k, b in enumerate(mp['cells']):
        t = b & 0x7F
        if t >= len(tiles):
            continue
        p = pixels(tiles[t])
        x0, y0 = (k % mp['cols']) * 8, (k // mp['cols']) * 8
        for y in range(8):
            for x in range(8):
                ci = p[y][7 - x if b & 0x80 else x]
                if ci:
                    img.putpixel((x0 + x, y0 + y), colors[ci] + (255,))
    if scale > 1:
        img = img.resize((img.width * scale, img.height * scale), Image.NEAREST)
    return img


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


def compare_vehicles(rom, wram, vram, items, stats, verbose):
    """탈것 슬롯(7E:3220 = FE): 타일이 VRAM 180~ 과, 칸 목록이 04 뱅크 표와, OAM 묶음이 부분 프레임과 같은지."""
    w16 = lambda a: wram[a] | wram[a + 1] << 8  # noqa: E731
    for v in VEHICLES:
        tiles = vehicle_tiles(rom, v)
        for k, fr in enumerate(vehicle_frames(rom, v)):
            part, cells = fr['part'], fr['cells']
            n = part['cols'] * part['rows']
            for slot in range(0x20):
                if wram[0x3220 + slot] != 0xFE:
                    continue
                lst = w16(0x8000 + wram[0x3200 + slot])
                got = [w16(lst + i * 2) for i in range(n)]
                if [c & 0xC1FF for c in got] != [c & 0xC1FF for c in cells[:n]]:
                    continue
                key = (v['id'], k)
                vt = sum(1 for t, b in tiles.items() if vram[0xC000 + t * 32:][:32] == b)
                stats.setdefault('vehicle_tiles', {})[v['id']] = (vt, len(tiles))
                want = [{(x, y): pv[1] for y, row in enumerate(img) for x, pv in enumerate(row) if pv}
                        for img in fr['frames'].values()]
                hits = 0
                for i in range(128 - n + 1):
                    grp = items[i:i + n]
                    if not all(grp) or not all(0x180 <= it[2] < 0x200 for it in grp):
                        continue
                    x0, y0, box = oam_box(grp, vram)
                    norm = {(x - min(p[0] for p in box), y - min(p[1] for p in box)): pv[1] for (x, y), pv in box.items()}
                    for wm in want:
                        if wm and {(x - min(p[0] for p in wm), y - min(p[1] for p in wm)): c for (x, y), c in wm.items()} == norm:
                            hits += 1
                            break
                st = stats.setdefault('vehicles', {}).setdefault(key, [0, 0])
                st[0] += 1
                st[1] += hits
                if verbose:
                    print(f'탈것 {v["id"]:02X} 부분 {k + 1} 슬롯 {slot:02X}: 타일 {vt}/{len(tiles)}, 칸 {n}/{n}, OAM 묶음 {hits}')


def compare_map_places(rom, wram, vram, items, stats, verbose):
    """맵 OBJ 물체 슬롯(7E:3220 = FE): 칸 목록이 16:F862 항목과, 그 타일을 쓰는 OAM 묶음이 물체 그림과 같은지."""
    w16 = lambda a: wram[a] | wram[a + 1] << 8  # noqa: E731
    base = w16(0x1997)
    bc, bd = (0xFE, wram[0x1949]) if wram[0xBE] < 0x80 else (wram[0xBC], wram[0xBD])
    for k, mp in enumerate(map_object_places(rom)):
        if mp['bc'] != bc or mp['bd'] not in (bd, 0x7F):
            continue
        n = mp['cols'] * mp['rows']
        want = [base + (b & 0x7F) | (0x4000 if b & 0x80 else 0) | mp['palette'] << 9 for b in mp['cells']]
        for slot in range(0x20):
            if wram[0x3220 + slot] != 0xFE or wram[0x34E0 + slot] != mp['cols'] or wram[0x3500 + slot] != mp['rows']:
                continue
            lst = w16(0x8000 + wram[0x3200 + slot])
            got = [w16(lst + i * 2) for i in range(n)]
            if [c & 0x4FFF for c in got] != want:
                continue
            hits = 0
            for i in range(128 - n + 1):
                grp = items[i:i + n]
                if not all(grp) or [g[2] for g in grp] != [c & 0x1FF for c in want]:
                    continue
                x0, y0 = min(g[0] for g in grp), min(g[1] for g in grp)
                if all(g[0] == x0 + (j % mp['cols']) * 8 and g[1] == y0 + (j // mp['cols']) * 8 and
                       bool(g[3] & 0x40) == bool(want[j] & 0x4000) and (g[3] >> 1) & 7 == mp['palette']
                       for j, g in enumerate(grp)):
                    hits += 1
            st = stats.setdefault('places', {}).setdefault(k, [0, 0])
            st[0] += 1
            st[1] += hits
            if verbose:
                print(f'맵 OBJ 물체 {k:02X} 슬롯 {slot:02X}: 칸 {n}/{n}, OAM 묶음 {hits}')
            break


def compare(rom, wram, vram, oam, cgram, stats, verbose=True):
    """인물 슬롯마다: 세트 타일이 VRAM 에 그대로 있는지, 칸 목록(7E:8060-)이 레코드와 같은지,
    그 세트 타일을 쓰는 OAM 묶음이 디코더 프레임 하나와 픽셀째로 같은지. 결과는 stats 에 더한다."""
    w16 = lambda a: wram[a] | wram[a + 1] << 8
    pals = obj_palettes(rom)
    cg = [cgram[256 + i * 2] | cgram[257 + i * 2] << 8 for i in range(64)]
    pal_ok = [all(cg[p * 16 + i] == pals[p][i] for i in range(1, 16)) for p in range(4)]
    stats['palette'] = stats.get('palette', []) + [pal_ok]
    items = oam_groups(oam)
    compare_vehicles(rom, wram, vram, items, stats, verbose)
    compare_map_places(rom, wram, vram, items, stats, verbose)
    seen = set()
    for slot in range(0x20):
        g = wram[0x3220 + slot]
        if g == 0xFF or g >= GFX_COUNT:
            continue
        lst = w16(0x8000 + wram[0x3200 + slot])
        cells = [w16(lst + i * 2) for i in range(48)]
        s = gfx_set(rom, g)
        rec = decode_set(rom, s)
        lying = bool(wram[0x31C0 + slot] & 1)
        base = (cells[0] & 0x1FF) - (rec['lying_cells'][0][0] if lying else rec['cells'][0] & 0x7F)
        if (s, base, lying) in seen or base < 0:
            continue
        seen.add((s, base, lying))
        tiles = rec['lying_tiles'] if lying else rec['tile_data']
        vt = sum(1 for i, t in enumerate(tiles) if vram[0xC000 + (base + i) * 32:][:32] == t)
        if lying:
            want_cells = [base + t | (0x4000 if hf else 0) | (0x8000 if vf else 0) for t, hf, vf in rec['lying_cells']]
            cell_ok = sum(1 for i in range(48) if cells[i] & 0xC1FF == want_cells[i])
            frames = {(d, 'lying'): img for d, img in rec['lying'].items()}
        else:
            cell_ok = sum(1 for i in range(48) if (cells[i] & 0x1FF) == base + (rec['cells'][i] & 0x7F)
                          and bool(cells[i] & 0x4000) == bool(rec['cells'][i] & 0x80))
            frames = dict(rec['frames'])
            if rec['layout'] == 'overlap':
                # 머리는 7E:3260, 몸은 7E:3240 의 방향을 따로 본다(00:F7E4·F808). 대화 몸짓에서 둘이 갈린다.
                for hd in DIRS:
                    for bd in DIRS:
                        if hd != bd:
                            for f in (0, 1):
                                frames[(f'{hd}/{bd}', f)] = mixed_frame(rec, hd, bd, f)
        if cell_ok < 48:
            continue  # 쓰지 않는 슬롯(지난 맵의 칸 목록이 남아 있음)
        n = 6 if rec['layout'] == 'simple' else 8
        inset = lambda it: it and base <= it[2] < base + len(tiles)
        shown = []
        i = 0
        pending = None
        while i < 128:
            if inset(items[i]) and all(inset(items[j]) for j in range(i, min(i + n, 128))):
                x0, y0, box = oam_box(items[i:i + n], vram)
                hit = None
                got = {(x - min(k[0] for k in box), y - min(k[1] for k in box)): pv for (x, y), pv in box.items()}
                pals_seen = set(pv[0] for pv in got.values())
                for (d, f), img in frames.items():
                    want = {(x, y): v for y, row in enumerate(img) for x, v in enumerate(row) if v}
                    b = bbox(img)
                    if (not b and not got) or b and {(x - b[0], y - b[1]): v for (x, y), v in want.items()} == \
                            {k: pv[1] for k, pv in got.items()}:
                        hit = f'{d}{f} {len(want)}px'
                        if pals_seen and pals_seen != {rec['palette']}:
                            hit += f' 팔레트 {"·".join(map(str, sorted(pals_seen)))}'
                            stats['other_palette'] = stats.get('other_palette', 0) + 1
                        stats.setdefault('frames', set()).add((s, d, f))
                        break
                if hit is None:
                    # 화면 가장자리에서 OBJ 몇 개가 빠진 인물이 앞에 있으면 묶음이 어긋난다. 한 칸씩 밀어 다시 본다.
                    if pending is None:
                        pending = (i, x0, y0)
                    elif i - pending[0] >= n:
                        shown.append(f'({pending[1]},{pending[2]}) 다름')
                        stats['groups'] = stats.get('groups', 0) + 1
                        pending = (i, x0, y0)
                    i += 1
                    continue
                pending = None
                shown.append(f'({x0},{y0}) {hit}')
                stats['groups'] = stats.get('groups', 0) + 1
                stats['hits'] = stats.get('hits', 0) + 1
                i += n
            else:
                i += 1
        if pending is not None:
            shown.append(f'({pending[1]},{pending[2]}) 다름')
            stats['groups'] = stats.get('groups', 0) + 1
        st = stats.setdefault('sets', {}).setdefault(s, [0, 0])
        st[0] += vt
        st[1] += len(tiles)
        if verbose:
            print(f'슬롯 {slot:02X} 그림 {g:02X} 세트 {s:02X} 타일 {base:03X}~: VRAM {vt}/{len(tiles)}, 칸 {cell_ok}/48, '
                  f'OAM {"; ".join(shown) if shown else "화면 밖"}' + (' (누운 모양)' if lying else ''))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('--out', help='시트·index.json 을 쓸 폴더(work/ 아래)')
    ap.add_argument('--scale', type=int, default=1)
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
        print(f'OAM 묶음 {stats.get("groups", 0)}개 중 {stats.get("hits", 0)}개가 디코더 프레임과 색 번호까지 픽셀째로 같음'
              f'(그중 레코드와 다른 OBJ 팔레트로 그린 것 {stats.get("other_palette", 0)}개), '
              f'서로 다른 (세트, 방향, 프레임) {len(frames)}개')
        for s in sorted(set(f[0] for f in frames)):
            print(f'  세트 {s:02X}: ' + ' '.join(sorted(f'{d}{f}' for t, d, f in frames if t == s)))
        for (vid, k), (seen_n, hits) in sorted(stats.get('vehicles', {}).items()):
            vt = stats['vehicle_tiles'][vid]
            print(f'탈것 {vid:02X} 부분 {k + 1}: 덤프 {seen_n}개에서 칸 목록 같음, 타일 {vt[0]}/{vt[1]}, OAM 묶음 {hits}개가 프레임과 같음')
        pl = stats.get('places', {})
        if pl:
            print(f'맵 OBJ 물체 {len(pl)}개: 칸 목록이 16:F862 항목과 같은 덤프 {sum(v[0] for v in pl.values())}개, '
                  f'OAM 묶음 {sum(v[1] for v in pl.values())}개가 칸 배치·반전·팔레트까지 같음 '
                  + ' '.join(f'{k:02X}' for k in sorted(pl)))
        print('VRAM 확인 세트: ' + ' '.join(f'{s:02X}' for s in sorted(sets)))
        lying = sorted(f for f in frames if f[2] == 'lying')
        print(f'누운 모양 (세트, 방향) {len(lying)}개: ' + ' '.join(f'{t:02X}{d}' for t, d, _ in lying))
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
