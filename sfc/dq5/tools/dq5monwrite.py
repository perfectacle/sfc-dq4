"""DQ5 전투 몬스터 그림·색 쓰기. 읽기 형식은 sfc/dq5/docs/dq5-graphics-format.md 의 「그림 형식」·「타일」.

그림 번호 하나를 색 번호 PNG(팔레트 모드, 픽셀 값 = OBJ 팔레트 색 번호 0~15, 0 투명, 크기는 가로 칸 × 8,
세로 칸 × 8)로 받아 머리·칸 비트맵·조각 니블·타일을 다시 만든다. 가로 칸은 1~15 또는 19(머리 +5 니블 F),
세로 칸은 1~16 이고, 원래 크기와 달라도 된다(+5 를 새로 씀). 머리 +0~+4 는 원래 값이고 "header" 로 바꾼다.
조각은 8픽셀 칸마다 자르고, 네 칸이 모두 그려진 2x2 는 16x16 조각으로, 앞 조각을 좌우로 뒤집은 것과 같으면
반전 복사(니블 4·6)로 쓴다. 타일은 평면마다 그대로/마스크 압축 중 짧은 쪽을 고른다(22:992A).
몬스터 레코드(27:E5DC)의 그림 번호와 색도 고친다.

  python sfc/dq5/tools/dq5monwrite.py rom/dq5.sfc dump 02 -o work/mon/02.png [--monster 00]
  python sfc/dq5/tools/dq5monwrite.py rom/dq5.sfc patch work/mon.json -o work/mon.dq5patch.json [--at 3B:8000]
      [--records-at 3C:8000]
  python sfc/dq5/tools/dq5monwrite.py rom/dq5.sfc check [work/mon.json] [--at 3B:8000] [--records-at 3C:8000]

문서(dq5monster/1):
  {"format": "dq5monster/1",
   "pictures": [{"picture": "02", "image": "02.png",
                 "header": {"float": false, "raise": 0, "shadow": 6, "shadow_dx": -4, "shadow_dy": 11,
                            "hit_x": 1, "hit_y": 1}}],
   "monsters": [{"monster": "00", "picture": "02", "colors": [32767, 0, 31]}]}

"header" 의 키는 모두 고르는 것이다. float·raise·shadow 는 +0 의 bit7·bit5-6·bit0-4, shadow_dx·shadow_dy 는 +1·+2
(부호 있는 바이트), hit_x·hit_y 는 +3·+4(상자 안 8픽셀 칸이라 가로·세로 칸 수보다 작게). shadow 는 0(없음)이거나
22:B4FE 표의 칸이 FFFF 가 아닌 번호여야 한다.

크기·띄움·들어올림을 바꾸었거나 조각·줄마다 타일·16x16 자리(22:91F7)가 원래보다 많은 그림은 입력 롬의 무리·구역으로 센 조합 검사(dq5monlimits.py)를 거친다. 같은 빌드에서
무리·구역을 바꾸면 그 패치를 먼저 넣은 롬을 입력으로 주고, 구역 수를 늘렸으면 --progress 또는 --areas 를 준다.
조합을 센 패치 목록에는 그 조합의 요약(compositions)을 남겨, dq5build.py build 가 빌드한 롬의 무리·구역·부르기와 다르면 거부한다
(dq5build.py check 와 build() 를 바로 부르는 도구에서는 보지 않는다).

새 그림이 원래 자리보다 길면 --at 에 놓는다. 머리 포인터 표는 그림 번호 구간마다 뱅크 25·26·27 의 16비트라,
이때는 22:9014 를 24비트 포인터 표(--at 첫머리)로 읽는 코드로 바꾼다.

색은 15개까지 받는다. 원래 레코드의 색 수보다 많은 몬스터가 있으면 레코드 포인터 표와 레코드 모두를 --records-at 의
한 뱅크에 새로 늘어놓고, 표를 읽는 두 곳(22:9003·22:900B, 몬스터 E4 의 색을 읽는 02:F48D·02:F498)의 주소·뱅크를 바꾼다.
"""
import argparse
import json
import tempfile
from contextlib import contextmanager
import re
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dq5mongfx as M  # noqa: E402
from dq5build import PatchError  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402

FORMAT = 'dq5monster/1'
PICTURES = 0x72                 # 그림 번호 00~71
FIND = 0x229014                 # 22:9014~9058: 그림 번호로 머리 포인터 $53~$55 를 정한다
FIND_ORIGINAL = bytes.fromhex('c9 57 90 15 e9 57 c2 20 29 ff 00 0a aa bf e4 82 27 85 53 e2 20 a9 27 80 2a')
FIND_END = 0x229059
# 몬스터 레코드 포인터 표를 읽는 곳. 레코드는 [$50](22:900F 그림 번호, 22:A5A4 색)로 읽어 뱅크는 $52 에 둔다.
RECORD_READ, RECORD_BANK = M.RECORD_READ, M.RECORD_BANK  # LDA $27E5DC,X / LDA #$27 (STA $52)
E4_BANK, E4_READ = 0x02F48D, 0x02F498                  # LDA #$27 (STA $02) / LDA $27E5DC,X — 몬스터 E4 의 색 10개
E4, E4_COLORS = 0xE4, 10
READ_ORIGINAL, BANK_ORIGINAL = bytes.fromhex('bf dc e5 27'), bytes.fromhex('a9 27')
MAX_COLORS = 15                 # OBJ 팔레트 1~15. 22:A5A4 는 색 수 0 이면 65536번 돈다
# 그림 하나의 타일은 풀고 난 다음 NMI 한 번(00:FD4A)에 VRAM 으로 보내, 많으면 0줄을 넘긴 뒤쪽이 VRAM 에 닿지 않는다
# (dq5mongfx.nmi_tiles). 첫 자리가 자리 줄 어디에 오든 모두 닿아야 받고, 잰 가장 늦은 첫 DMA 에 타일 하나 몫을 남긴다.
# 원래 그림 6C(110개)는 셈으로 뒤 5개가 닿지 않고, E4 일 때 22:90FA 가 한 프레임 뒤에 6개를 다시 보낸다.
NMI_MARGIN = 264
# 싸우는 도중에 그림을 푸는 NMI 가운데 부르기(22:D2FE)·がったい(22:D2FE)·パルプンテ(22:D45D)는 $19 bit1 이 꺼져
# 00:89BB 의 OAM DMA 없이 첫 DMA 가 전투 첫머리와 같은 241줄에 걸렸다(dq5monmidcheck.py). モシャス(22:D3B9)는 게임이
# 동료를 고르는 장면을 재지 못했다. 연출 중 OAM DMA 뒤에 목록을 보낸 NMI 에서 잰 첫 DMA(241줄 378 보다 4,768~4,814
# 늦음)보다 조금 더 일찍 끊고, 고른 몬스터를 덮어 モシャス 로 푼 실험 세 번(84·90·100 → 84·86·86)도 이 몫 안이었다.
# 22:ADE7 이 돌려받은 자리로 사슬이 끊겨 이어지면 목록 항목이 더 늘어나는데, 그 경우는 셈에 들어 있지 않다.
OAM_DMA_MARGIN = 4850
WIDTHS = (*range(1, 16), 0x13)  # 머리 +5 상위 니블 0~E → 1~15, F → 19
HEIGHTS = range(1, 17)
SHADOWS = 0x22B4FE              # 그림자 모양 표(22:B44A). 번호 × 2 의 칸이 FFFF 면 그림자 자료가 없음
HEADER_KEYS = ('float', 'raise', 'shadow', 'shadow_dx', 'shadow_dy', 'hit_x', 'hit_y')
ORIGINAL_SIZE = 0x180000        # 원래 롬. 이 안의 옮긴 자료는 빈 자리 지도(dq5build.free_ranges) 안이어야 한다


def cpu(addr):
    return f'{addr >> 16:02X}:{addr & 0xFFFF:04X}'


def hexbyte(value, name):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9A-Fa-f]{2}', value):
        raise ValueError(f'{name}: 두 자리 16진 문자열이어야 함')
    return int(value, 16)


def address(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9A-Fa-f]{2}:[0-9A-Fa-f]{4}', value):
        raise ValueError('주소는 BB:AAAA 문자열이어야 함')
    bank, low = (int(p, 16) for p in value.split(':'))
    if bank > 0x7D or low < 0x8000:
        raise ValueError('주소는 뱅크 00~7D 의 8000~FFFF 여야 함')
    return bank << 16 | low


def records_moved(rom):
    code = bytes(rom.d[lorom(RECORD_READ):lorom(RECORD_READ) + 4])
    if code == READ_ORIGINAL and bytes(rom.d[lorom(RECORD_BANK):lorom(RECORD_BANK) + 2]) == BANK_ORIGINAL:
        return False
    if code[0] != 0xBF or rom.u8(RECORD_BANK) != 0xA9:
        raise ValueError('22:9003 이 원본 레코드 읽기도 옮긴 레코드 읽기도 아님')
    return True


def used_pictures(rom):
    return sorted({M.monster(rom, m)[0] for m in range(M.COUNT)})


def tile_bytes(rows):
    out = bytearray(32)
    for y, row in enumerate(rows):
        for x, c in enumerate(row):
            for bit in range(4):
                out[(bit // 2) * 16 + y * 2 + bit % 2] |= ((c >> bit) & 1) << (7 - x)
    return bytes(out)


def encode_tile(t):
    """32바이트 타일 → 22:992A 모드 바이트와 자료. 그대로·마스크 압축(채움 값 0 또는 한 값) 중 가장 짧은 것."""
    planes = [i for i in range(4) if any(t[(i // 2) * 16 + r * 2 + i % 2] for r in range(8))]
    order = [(half * 16 + r * 2 + k, half * 2 + k) for half in (0, 1) for r in range(8) for k in (0, 1)
             if half * 2 + k in planes]
    mode = sum(1 << i for i in planes)
    best = bytes([mode]) + bytes(t[at] for at, _ in order)
    values = {t[at] for at, _ in order} | {0}
    for fill in values:
        bits = [t[at] != fill for at, _ in order]
        masks = bytes(sum(b << (7 - j) for j, b in enumerate(bits[i:i + 8])) for i in range(0, len(bits), 8))
        head = bytes([mode | 0x80 | (0x40 if fill else 0)]) + (bytes([fill]) if fill else b'')
        out = head + masks + bytes(t[at] for at, _ in order if t[at] != fill)
        if len(out) < len(best):
            best = out
    return best


def piece_image(grid, x, y, big):
    n = 2 if big else 1
    return tuple(tuple(grid[y * 8 + r][x * 8:x * 8 + 8 * n]) for r in range(8 * n))


def encode_picture(grid, w, h, head6):
    """색 번호 격자(h*8 x w*8) → 머리부터 끝까지 바이트, 조각 수, 타일 수(반전 복사 뺌), 줄마다 타일 수."""
    filled = [[any(grid[y * 8 + r][x * 8 + c] for r in range(8) for c in range(8)) for x in range(w)] for y in range(h)]
    covered = [[False] * w for _ in range(h)]
    cells, pieces = [], []
    for y in range(h):
        for x in range(w):
            if covered[y][x] or not filled[y][x]:
                continue
            big = (x + 1 < w and y + 1 < h and all(filled[yy][xx] and not covered[yy][xx]
                                                   for yy in (y, y + 1) for xx in (x, x + 1)))
            for yy in (y, y + 1) if big else (y,):
                for xx in (x, x + 1) if big else (x,):
                    covered[yy][xx] = True
            cells.append((x, y))
            pieces.append((x, y, big, piece_image(grid, x, y, big)))
    bitmap = bytearray((w * h + 7) // 8)
    for x, y in cells:
        i = y * w + x
        bitmap[i // 8] |= 0x80 >> (i % 8)
    nibbles, data, seen, tiles, bands = [], bytearray(), {}, 0, [0] * h
    for k, (x, y, big, image) in enumerate(pieces):
        mirrored = tuple(tuple(reversed(row)) for row in image)
        for r in range(y, y + (2 if big else 1)):
            bands[r] += 2 if big else 1
        if (big, mirrored) in seen:
            nibbles.append((6 if big else 4))
            data.append(seen[big, mirrored])
            continue
        seen.setdefault((big, image), k)
        nibbles.append(2 if big else 0)
        n = 2 if big else 1
        for ty in range(n):
            for tx in range(n):
                data += encode_tile(tile_bytes([row[tx * 8:tx * 8 + 8] for row in image[ty * 8:ty * 8 + 8]]))
                tiles += 1
    packed = bytes((nibbles[i] << 4) | (nibbles[i + 1] if i + 1 < len(nibbles) else 0)
                   for i in range(0, len(nibbles), 2))
    return bytes(head6) + bytes(bitmap) + packed + bytes(data), len(pieces), tiles, bands


def original_layout(rom, g):
    """원래 그림의 머리·비트맵·니블 바이트와 조각마다 (반전 복사면 자료 1바이트, 아니면 None)."""
    d = decode(rom, g)
    s = M.Stream(rom, d['head'])
    nbits = d['w'] * d['h']
    nib_at = 6 + (nbits + 7) // 8
    start = nib_at + (len(d['pieces']) + 1) // 2
    pos, refs = [start], []
    for k, piece in enumerate(d['pieces']):
        nib = s.u8(nib_at + k // 2) >> (0 if k & 1 else 4) & 15
        if nib & 0xC:
            refs.append(s.u8(pos[0]))
            pos[0] += 1
            continue
        refs.append(None)
        for _ in range(4 if nib & 2 else 1):
            M.tile(s, pos)
    return bytes(rom.u8(d['head'] + i) for i in range(start)), refs, d


def keep_layout(rom, g, grid):
    """원래 그림의 조각 배치(칸·크기·반전 복사·1픽셀 밀기)를 그대로 두고 타일만 새 그림에서 잘라 쓴다.
    그 배치로 다시 그린 것이 입력과 같을 때만 바이트를 돌려준다(None 이면 배치를 새로 짠다)."""
    prefix, refs, d = original_layout(rom, g)
    W, H = d['w'] * 8, d['h'] * 8
    if (len(grid[0]), len(grid)) != (W, H):
        return None
    pieces, data = [], bytearray()
    for (x0, y0, big, _, _), ref in zip(d['pieces'], refs):
        if ref is not None:
            source = pieces[ref]
            pieces.append((x0, y0, big, source[3], not source[4]))
            data.append(ref)
            continue
        n = 2 if big else 1
        tiles = [tile_bytes([[grid[y0 + ty * 8 + r][x0 + tx * 8 + c] if x0 + tx * 8 + c < W and y0 + ty * 8 + r < H else 0
                              for c in range(8)] for r in range(8)]) for ty in range(n) for tx in range(n)]
        pieces.append((x0, y0, big, tiles, False))
        for t in tiles:
            data += encode_tile(t)
    if [row[1:] for row in M.index_image(dict(d, pieces=pieces))] != grid:
        return None
    return prefix + bytes(data)


def stats(d):
    """원래 그림의 조각 수·타일 수(반전 복사 뺌)·줄마다 타일 수."""
    return len(d['pieces']), sum(len(p[3]) for p in d['pieces'] if not p[4]), M.band_counts(d)


def size_byte(w, h):
    return (0xF if w == 0x13 else w - 1) << 4 | (h - 1)


def encode(rom, g, grid, head5=None):
    """원래 배치로 되면 그것을, 아니면 새 배치. (바이트, 조각 수, 타일 수, 줄마다 타일 수).
    head5 는 머리 +0~+4(없으면 원래 값), 크기 +5 는 grid 의 크기."""
    d = decode(rom, g)
    head5 = bytes(head5) if head5 is not None else bytes(rom.u8(d['head'] + k) for k in range(5))
    raw = keep_layout(rom, g, grid)
    if raw is not None:
        return (head5 + raw[5:], *stats(d))
    w, h = len(grid[0]) // 8, len(grid) // 8
    return encode_picture(grid, w, h, head5 + bytes([size_byte(w, h)]))


def image_grid(path, w=None, h=None):
    """색 번호 격자. w·h 를 주면 그 크기만, 없으면 그림 상자로 쓸 수 있는 크기(WIDTHS × HEIGHTS)를 받는다."""
    with Image.open(path) as opened:
        image = opened.copy()
    if w is not None and image.size != (w * 8, h * 8):
        raise ValueError(f'{path}: {w * 8}x{h * 8} 팔레트 모드 PNG 여야 함(지금 {image.mode} {image.size[0]}x{image.size[1]})')
    W, H = image.size
    if image.mode != 'P' or W % 8 or H % 8 or W // 8 not in WIDTHS or H // 8 not in HEIGHTS:
        raise ValueError(f'{path}: 가로 8·16·…·120·152, 세로 8~128 픽셀(8의 배수) 팔레트 모드 PNG 여야 함'
                         f'(지금 {image.mode} {W}x{H})')
    data = list(image.tobytes())
    if max(data) > 15:
        raise ValueError(f'{path}: 색 번호는 0~15 여야 함')
    return [data[y * W:(y + 1) * W] for y in range(H)]


def header_bytes(rom, g, row, w, h, label):
    """머리 +0~+4. row 는 문서의 "header"(없으면 원래 값). 크기를 바꾸면 원래 값도 새 크기로 검사한다."""
    b = [rom.u8(head_of(rom, g) + k) for k in range(5)]
    row = {} if row is None else row
    if not isinstance(row, dict) or row.keys() - set(HEADER_KEYS):
        raise ValueError(f'{label}: {", ".join(HEADER_KEYS)} 만 받음')
    hd = dict(M.parse_header(b + [size_byte(w, h)]), **row)
    if type(hd['float']) is not bool:
        raise ValueError(f'{label}.float: true/false')
    for key, low, high in (('raise', 0, 3), ('shadow', 0, 31), ('shadow_dx', -128, 127), ('shadow_dy', -128, 127),
                           ('hit_x', 0, w - 1), ('hit_y', 0, h - 1)):
        if type(hd[key]) is not int or not low <= hd[key] <= high:
            raise ValueError(f'{label}.{key}: {low}~{high} 정수')
    if hd['shadow'] and rom.u16(SHADOWS + hd['shadow'] * 2) == 0xFFFF:
        raise ValueError(f'{label}.shadow: 그림자 모양 {hd["shadow"]} 은 22:B4FE 표에 자료가 없음')
    return bytes([hd['float'] << 7 | hd['raise'] << 5 | hd['shadow'], hd['shadow_dx'] & 0xFF, hd['shadow_dy'] & 0xFF,
                  hd['hit_x'], hd['hit_y']])


def head_of(rom, g):
    """그림 머리. 22:9014 를 24비트 표 코드로 바꾼 롬이면 그 표에서 읽는다."""
    code = bytes(rom.d[lorom(FIND):lorom(FIND) + len(FIND_ORIGINAL)])
    if code == FIND_ORIGINAL:
        return ORIGINAL_HEAD(rom, g)
    table = code[13] | code[14] << 8 | code[15] << 16
    patched = find_code(table)
    if bytes(rom.d[lorom(FIND):lorom(FIND) + len(patched)]) != patched:
        raise ValueError('22:9014 가 원본 코드도 24비트 표 코드도 아님')
    return rom.u24(table + g * 3)


ORIGINAL_HEAD = M.head


@contextmanager
def following_table():
    """그 안에서 dq5mongfx 의 머리 찾기(decode·match_oam 등)가 head_of 를 쓴다. 옮긴 그림을 읽으려고.
    옮긴 레코드는 dq5mongfx.monster 가 늘 22:9003 을 따라 읽는다."""
    saved, M.head = M.head, head_of
    try:
        yield
    finally:
        M.head = saved


def decode(rom, g):
    """dq5mongfx.decode 와 같되, 머리를 head_of 로 찾아 옮긴 그림도 읽는다."""
    with following_table():
        return M.decode(rom, g)


def picture_grid(rom, g):
    d = decode(rom, g)
    return [row[1:] for row in M.index_image(d)], d


def dump_image(rom, g, path, m=None):
    grid, d = picture_grid(rom, g)
    if m is None:
        m = next(i for i in range(M.COUNT) if M.monster(rom, i)[0] == g)
    colors = M.monster(rom, m)[1]
    image = Image.new('P', (d['w'] * 8, d['h'] * 8))
    image.putpalette([0, 0, 0] + [c for color in colors for c in M.rgb(color)] + [0] * 3 * (15 - len(colors)))
    image.putdata([c for row in grid for c in row])
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    image.save(path, transparency=0)
    return d, m


def heads(rom):
    """머리 주소마다 (그림 번호들, 끝). 같은 머리를 여러 번호가 가리킨다(빈 번호)."""
    out = {}
    for g in range(PICTURES):
        out.setdefault(head_of(rom, g), []).append(g)
    return {h: (gs, decode(rom, gs[0])['end']) for h, gs in out.items()}


def nmi_short(d, margin=NMI_MARGIN):
    """첫 자리를 자리 줄의 0~7 번째에 두어 NMI 한 번에 닿지 않는 타일이 있으면 (첫 자리, 닿는 수), 없으면 None.
    새 전투는 자리를 이어서 주므로 줄 안 위치만 목록 항목을 바꾼다."""
    tiles = len(M.obj_tiles(d, 0))
    for start in range(8):
        arrived = M.nmi_tiles(d, start, margin)
        if arrived < tiles:
            return start, arrived
    return None


def midbattle_pictures(rom, monsters):
    """OAM DMA 몫을 더 남길 그림 번호: モシャス 가 그림을 빌리는 동료 몬스터(레코드 +18 동료 종류가 0 이 아닌 몬스터)의 그림.
    부르기·がったい·パルプンテ 로 푸는 그림은 잰 대로 전투 첫머리와 같은 한도를 쓴다. monsters 는 바꾼 {몬스터: (그림, 색)}."""
    from dq5monster import record
    users = {m for m in range(M.COUNT) if record(rom, m)[0x18] & 0x7F}
    return {monsters[m][0] if m in monsters else M.monster(rom, m)[0] for m in users}


def picture_limits(rom, g):
    """(조각, 타일, 가로 칸, 세로 칸, 줄마다 타일 최대). 몬스터의 그림을 바꿀 때 원래 그림 이하로 둔다."""
    d = decode(rom, g)
    pieces, tiles, bands = stats(d)
    return pieces, tiles, d['w'], d['h'], max(bands)


def plan(rom, doc, base, areas=None):
    return plan_all(rom, doc, base, areas)[:2]


def plan_all(rom, doc, base, areas=None):
    """(그림, 몬스터, 무리 조합을 다시 셌는지)."""
    if not isinstance(doc, dict) or doc.keys() - {'format', 'pictures', 'monsters'} or doc.get('format') != FORMAT:
        raise ValueError(f'문서는 format={FORMAT}, pictures·monsters 만 담은 객체여야 함')
    if records_moved(rom):
        raise ValueError('몬스터 레코드를 이미 옮긴 롬(22:9003)은 받지 않음 — 레코드를 옮기기 전 롬을 입력으로 줌')
    used = set(used_pictures(rom))
    pictures, grown, limits, nmi = {}, {}, {}, {}
    rows = doc.get('pictures', [])
    if not isinstance(rows, list):
        raise ValueError('pictures는 배열이어야 함')
    for i, row in enumerate(rows):
        label = f'pictures[{i}]'
        if not isinstance(row, dict) or not {'picture', 'image'} <= row.keys() <= {'picture', 'image', 'header'} \
                or not isinstance(row['image'], str):
            raise ValueError(f'{label}: picture·image 와 header 만 받음')
        g = hexbyte(row['picture'], f'{label}.picture')
        if g not in used:
            raise ValueError(f'{label}: 그림 {g:02X}는 몬스터가 쓰는 그림이 아님(빈 번호는 다른 그림의 머리를 가리킴)')
        if g in pictures:
            raise ValueError(f'{label}: 그림 {g:02X}를 두 번 지정함')
        d = decode(rom, g)
        grid = image_grid(base / row['image'])
        head5 = header_bytes(rom, g, row.get('header'), len(grid[0]) // 8, len(grid) // 8, f'{label}.header')
        raw, pieces, tiles, bands = encode(rom, g, grid, head5)
        limit = stats(d)
        slots = M.slot_count(decode_bytes(raw))
        hd, old = M.parse_header(raw[:6]), M.parse_header([rom.u8(head_of(rom, g) + k) for k in range(6)])
        if keep_layout(rom, g, grid) is None:
            nmi[g] = (label, tiles, limit[1], decode_bytes(raw))
        # 크기·띄움·들어올림은 줄·y·가로 자리를 바꾸므로(22:A001·22:9284) 조합을 다시 센다.
        if pieces > limit[0] or slots > M.slot_count(d) or len(bands) > len(limit[2]) or \
                any(a > b for a, b in zip(bands, limit[2])) or \
                any(hd[k] != old[k] for k in ('w', 'h', 'float', 'raise')):
            grown[g] = (pieces, bands, slots, hd)
        pictures[g] = (grid, raw, pieces, tiles)
        limits[g] = (pieces, tiles, len(grid[0]) // 8, len(grid) // 8, max(bands))
    # 같은 머리를 가리키는 그림 번호(00·11·29, 58·5E 등)는 자료가 하나라 함께 바뀐다.
    for g in list(pictures):
        for other in used:
            if other != g and head_of(rom, other) == head_of(rom, g):
                if other in pictures and pictures[other][0] != pictures[g][0]:
                    raise ValueError(f'그림 {g:02X}·{other:02X} 는 같은 머리를 써서 다른 그림을 줄 수 없음')
                pictures[other] = pictures[g]
                limits[other] = limits[g]
                if g in grown:
                    grown[other] = grown[g]
    monsters = {}
    rows = doc.get('monsters', [])
    if not isinstance(rows, list):
        raise ValueError('monsters는 배열이어야 함')
    for i, row in enumerate(rows):
        label = f'monsters[{i}]'
        if not isinstance(row, dict) or row.keys() - {'monster', 'picture', 'colors'} or 'monster' not in row:
            raise ValueError(f'{label}: monster 와 picture·colors 만 받음')
        m = hexbyte(row['monster'], f'{label}.monster')
        if m >= M.COUNT or m in monsters:
            raise ValueError(f'{label}: 몬스터 {m:02X}는 00~EB 이고 한 번만 지정함')
        g0, colors0 = M.monster(rom, m)
        g = hexbyte(row['picture'], f'{label}.picture') if 'picture' in row else g0
        if g not in used:
            raise ValueError(f'{label}.picture: 그림 {g:02X}는 몬스터가 쓰는 그림이 아님')
        colors = row.get('colors', colors0)
        if not isinstance(colors, list) or not 1 <= len(colors) <= MAX_COLORS or \
                any(type(c) is not int or not 0 <= c <= 0x7FFF for c in colors):
            raise ValueError(f'{label}.colors: 0~7FFF 정수 1~{MAX_COLORS}개(원래 {len(colors0)}개보다 많으면 --records-at)')
        if g != g0:
            # 같은 문서에서 바꾼 그림이면 바꾼 크기로 견준다
            old, new = picture_limits(rom, g0), limits.get(g) or picture_limits(rom, g)
            if any(a > b for a, b in zip(new, old)):
                raise ValueError(f'{label}.picture: 그림 {g:02X} 의 조각·타일·가로·세로·줄 최대 타일 {new} 가 원래 그림 {g0:02X} 의 '
                                 f'{old} 를 넘음(전투 배치 한도)')
        monsters[m] = (g, colors)
    # 레코드를 함께 쓰는 몬스터(3B·3C 등)는 같은 값이어야 한다.
    for m in list(monsters):
        for other in range(M.COUNT):
            if other != m and rom.u16(M.RECORDS + other * 2) == rom.u16(M.RECORDS + m * 2):
                if other in monsters and monsters[other] != monsters[m]:
                    raise ValueError(f'몬스터 {m:02X}·{other:02X} 는 레코드를 함께 써서 다른 값을 줄 수 없음')
                monsters[other] = monsters[m]
    # 그림 6C 는 22:90FA 가 정해진 6타일을 다시 보내 버티므로, 원래 배치 그대로일 때만 NMI 한도를 넘겨 받는다.
    mid = midbattle_pictures(rom, monsters)
    for g, (label, tiles, original, d) in nmi.items():
        same = {x for x in used if head_of(rom, x) == head_of(rom, g)}
        late = bool(same & mid)
        short = nmi_short(d, NMI_MARGIN + (OAM_DMA_MARGIN if late else 0))
        if short:
            raise ValueError(f'{label}: 타일 {tiles}개 — 한 그림의 타일은 다음 NMI 한 번에 VRAM 으로 보내, 첫 자리가 '
                             f'{short[0]} 이면 {short[1]}개만 닿음'
                             + ('(モシャス 로 싸우는 도중에 풀릴 수 있는 그림이라 OAM DMA 몫을 더 남김)' if late else '')
                             + f'(원래 배치를 그대로 쓰면 원래 {original}개까지)')
    if E4 in monsters and len(monsters[E4][1]) < E4_COLORS:
        raise ValueError(f'몬스터 {E4:02X}: 색 {len(monsters[E4][1])}개 — 02:F498 이 늘 {E4_COLORS}개를 읽으므로 '
                         f'{E4_COLORS}개 이상이어야 함')
    for m in range(M.COUNT):
        g, colors = monsters.get(m, M.monster(rom, m))
        grid = pictures[g][0] if g in pictures else picture_grid(rom, g)[0]
        top = max(max(row) for row in grid)
        if top > len(colors):
            raise ValueError(f'몬스터 {m:02X}: 그림 {g:02X} 가 색 번호 {top} 을 쓰는데 색은 {len(colors)}개')
    # 조각·줄마다 타일·자리가 원래보다 많은 그림은, 나올 수 있는 무리 조합마다 원래보다 덜 놓이는 몬스터가 없을 때만 받는다.
    if grown:
        from dq5monlimits import losses
        swapped = {m: g for m, (g, _) in monsters.items() if g != M.monster(rom, m)[0]}
        bad = losses(rom, grown, swapped, areas=areas)
        if bad:
            groups, old, new, where, why = bad[0]
            shown = ' '.join(f'{m:02X}x{n}' for m, n, _ in groups)
            raise ValueError(f'그림 {", ".join(f"{g:02X}" for g in sorted(grown))}: 크기·띄움·들어올림을 바꾸었거나 조각·줄마다 타일·자리가 원래보다 많아 '
                             f'무리 조합 {len(bad)}개에 걸림. 첫째: {where} [{shown}] 놓이는 수 {old} → {new}, {why}')
    return pictures, monsters, bool(grown)


def find_code(table):
    """22:9014 를 대신한다. A(8비트) = 그림 번호, X 16비트. 24비트 표에서 $53~$55 를 채우고 9059 로."""
    t = [table & 0xFF, table >> 8 & 0xFF, table >> 16]
    t2 = table + 2
    code = bytes([0xC2, 0x20, 0x29, 0xFF, 0x00, 0x48, 0x0A, 0x18, 0x63, 0x01, 0xAA, 0x68,
                  0xBF, *t, 0x85, 0x53, 0xE2, 0x20, 0xBF, t2 & 0xFF, t2 >> 8 & 0xFF, t2 >> 16, 0x85, 0x55])
    return code + bytes([0x80, (FIND_END - (FIND + len(code) + 2)) & 0xFF])


def patch(rom, doc, base=Path('.'), at=None, areas=None, records_at=None):
    pictures, monsters, counted = plan_all(rom, doc, base, areas)
    writes = []

    def write(addr, data, note, orig=True):
        item = {'at': cpu(addr), 'hex': data.hex(' '), 'note': note}
        if orig:
            item['orig'] = bytes(rom.d[lorom(addr):lorom(addr) + len(data)]).hex(' ')
        writes.append(item)

    places = heads(rom)
    moved, done = {}, set()
    for g in sorted(pictures):
        if head_of(rom, g) in done:
            continue
        done.add(head_of(rom, g))
        grid, raw, pieces, tiles = pictures[g]
        if grid == picture_grid(rom, g)[0] and raw[:6] == bytes(rom.u8(head_of(rom, g) + k) for k in range(6)):
            continue
        h = head_of(rom, g)
        if h + len(raw) <= places[h][1]:
            write(h, raw, f'그림 {g:02X} 조각 {pieces}·타일 {tiles}' + (
                f'(같은 머리: {" ".join(f"{x:02X}" for x in places[h][0] if x != g)})' if len(places[h][0]) > 1 else ''))
        else:
            moved[g] = raw
    if moved:
        if at is None:
            raise ValueError('그림 ' + ' '.join(f'{g:02X}' for g in moved) + ' 이 원래 자리보다 길어 --at 이 필요함')
        table = at
        cursor = table + PICTURES * 3
        pointers = {g: head_of(rom, g) for g in range(PICTURES)}
        for g, raw in moved.items():
            # [$53],Y 로 읽으므로 그림 하나는 한 뱅크의 8000~FFFF 안에 있어야 한다.
            if (cursor & 0xFFFF) + len(raw) > 0x10000:
                cursor = ((cursor >> 16) + 1) << 16 | 0x8000
            # 옮긴 자료는 orig 없이 쓴다. 원래 롬 안이면 빌더가 빈 자리 지도 밖을 거부한다.
            write(cursor, raw, f'그림 {g:02X} 옮김', orig=False)
            old = head_of(rom, g)
            for other in range(PICTURES):
                if pointers[other] == old:
                    pointers[other] = cursor
            cursor += len(raw)
        if (table & 0xFFFF) + PICTURES * 3 > 0x10000:
            raise ValueError('24비트 머리 포인터 표가 뱅크를 넘음')
        write(table, b''.join(pointers[g].to_bytes(3, 'little') for g in range(PICTURES)), '그림 머리 24비트 포인터 표',
              orig=False)
        if bytes(rom.d[lorom(FIND):lorom(FIND) + len(FIND_ORIGINAL)]) != FIND_ORIGINAL:
            raise ValueError('22:9014 가 원본 머리 포인터 선택 코드가 아님')
        write(FIND, find_code(table), '머리 포인터를 24비트 표에서 읽기')
    grown = [m for m, (_, colors) in monsters.items() if len(colors) > len(M.monster(rom, m)[1])]
    if grown:
        if records_at is None:
            raise ValueError('몬스터 ' + ' '.join(f'{m:02X}' for m in sorted(grown)) + ' 의 색이 원래 레코드보다 많아 '
                             '--records-at 이 필요함')
        write_records(rom, monsters, records_at, write)
    else:
        if records_at is not None:
            raise ValueError('--records-at 을 주었지만 색이 원래 레코드보다 많은 몬스터가 없음(레코드는 제자리에 씀)')
        records = set()
        for m in sorted(monsters):
            g, colors = monsters[m]
            record = 0x270000 | rom.u16(M.RECORDS + m * 2)
            if (g, colors) == M.monster(rom, m) or record in records:
                continue
            records.add(record)
            write(record, bytes([g, len(colors)]) + b''.join(c.to_bytes(2, 'little') for c in colors),
                  f'몬스터 {m:02X} 그림·색')
    spans = sorted((parse(w['at']), parse(w['at']) + len(w['hex']) // 3 + 1) for w in writes if 'orig' not in w)
    for (a, b), (c, _) in zip(spans, spans[1:]):
        if c < b:
            raise ValueError(f'옮긴 자료가 겹침: {cpu(a)}~ 와 {cpu(c)}~ (--at·--records-at 을 떼어 줌)')
    from dq5build import free_ranges, inside
    free = free_ranges(rom.d)
    for a, b in spans:
        if lorom(a) < ORIGINAL_SIZE and not inside(lorom(a), b - a, free):
            raise ValueError(f'옮긴 자료 {cpu(a)}~ 가 원래 롬의 코드·자료 자리와 겹침(빈 자리 지도 밖)')
    manifest = {'format': 'dq5patch/1', 'name': 'monster-pictures', 'writes': writes}
    if counted:
        # 입력 롬의 무리·구역으로만 셌으므로, 다른 패치가 무리·구역·부르기를 바꾸면 dq5build.py 가 거부한다.
        from dq5monlimits import fingerprint
        manifest['compositions'] = {'areas': areas, 'sha1': fingerprint(rom, areas)}
    return manifest


def parse(text):
    bank, low = (int(p, 16) for p in text.split(':'))
    return bank << 16 | low


def write_records(rom, monsters, at, write):
    """레코드 포인터 표(256칸 × 2바이트)와 레코드를 at 의 한 뱅크에 새로 늘어놓고, 표를 읽는 코드를 바꾼다.
    레코드를 함께 쓰던 몬스터(3B·3C, 몬스터 칸이 아닌 EC~FF 와 00)는 새 자리에서도 함께 쓴다."""
    for addr, want in ((RECORD_READ, READ_ORIGINAL), (RECORD_BANK, BANK_ORIGINAL),
                       (E4_READ, READ_ORIGINAL), (E4_BANK, BANK_ORIGINAL)):
        if bytes(rom.d[lorom(addr):lorom(addr) + len(want)]) != want:
            raise ValueError(f'{cpu(addr)} 가 원본 레코드 읽기 코드가 아님')
    old = [0x270000 | rom.u16(M.RECORDS + m * 2) for m in range(M.TABLE_SIZE)]
    place, body = {}, bytearray()
    for record in sorted(set(old)):
        m = old.index(record)
        g, colors = monsters.get(m, M.monster(rom, m))
        place[record] = at + M.TABLE_SIZE * 2 + len(body)
        body += bytes([g, len(colors)]) + b''.join(c.to_bytes(2, 'little') for c in colors)
    if (at & 0xFFFF) + M.TABLE_SIZE * 2 + len(body) > 0x10000:
        raise ValueError('몬스터 레코드 표와 레코드가 --records-at 의 뱅크를 넘음')
    table = b''.join((place[r] & 0xFFFF).to_bytes(2, 'little') for r in old)
    write(at, table + bytes(body), f'몬스터 레코드 포인터 표·레코드 {len(place)}개 옮김', orig=False)
    t = at.to_bytes(3, 'little')
    write(RECORD_READ, bytes([0xBF, *t]), '레코드 포인터 표를 옮긴 자리에서 읽기')
    write(RECORD_BANK, bytes([0xA9, at >> 16]), '레코드 뱅크($52)')
    write(E4_READ, bytes([0xBF, *t]), '몬스터 E4 의 레코드 포인터')
    write(E4_BANK, bytes([0xA9, at >> 16]), '몬스터 E4 의 레코드 뱅크($02)')


def built(rom, manifest):
    from dq5build import build, parse_at
    lists = [(parse_at(w['at'])[0], bytes.fromhex(w['hex']), bytes.fromhex(w['orig']) if 'orig' in w else None, w['note'])
             for w in manifest['writes']]
    data, _ = build(rom.d, [('monster-pictures', 0, lists)], 2 if any(o >= 0x180000 for o, *_ in lists) else 0)
    return Rom(data)


def check(rom, doc=None, base=Path('.'), at=None, areas=None, records_at=None):
    """원본 107그림을 PNG 로 내보내 다시 인코딩해도 같은 그림으로 풀리고 원래 수 안인지, 원본 문서 쓰기 0개인지.
    doc 를 주면 빌드한 롬에서 바꾼 그림·몬스터가 입력대로이고 나머지가 그대로인지도 본다."""
    with tempfile.TemporaryDirectory(prefix='dq5mon-') as folder:
        check_in(rom, doc, base, at, Path(folder), areas, records_at)


def check_in(rom, doc, base, at, folder, areas=None, records_at=None):
    rows, fits, sizes = [], 0, [0, 0]
    for g in used_pictures(rom):
        d, _ = dump_image(rom, g, folder / f'{g:02X}.png')
        grid = image_grid(folder / f'{g:02X}.png', d['w'], d['h'])
        raw, pieces, tiles, bands = encode(rom, g, grid)
        got = decode_raw(raw, d['w'], d['h'])
        if got != grid:
            raise ValueError(f'그림 {g:02X}: 다시 인코딩한 그림이 원본과 다름')
        limit = stats(d)
        if pieces > limit[0] or tiles > limit[1] or any(a > b for a, b in zip(bands, limit[2])):
            raise ValueError(f'그림 {g:02X}: 다시 인코딩한 조각·타일 수가 원본보다 많음')
        fits += d['end'] - d['head'] >= len(raw)
        sizes[0] += len(raw)
        sizes[1] += d['end'] - d['head']
        rows.append({'picture': f'{g:02X}', 'image': f'{g:02X}.png'})
    if patch(rom, {'format': FORMAT, 'pictures': rows}, folder)['writes']:
        raise ValueError('원본 그림을 그대로 넣었는데 쓰기가 생김')
    print(f'그림 {len(rows)}개 다시 인코딩 일치(조각·타일·줄마다 타일 수 원본 이하); 원래 자리에 들어감 {fits}개; '
          f'다시 인코딩 {sizes[0]}바이트 / 원본 {sizes[1]}바이트; 원본 문서 쓰기 0개')
    if doc is None:
        return
    manifest = patch(rom, doc, base, at, areas, records_at)
    after = built(rom, manifest)
    pictures, monsters = plan(rom, doc, base, areas)
    for g in used_pictures(rom):
        want = pictures[g][0] if g in pictures else picture_grid(rom, g)[0]
        if picture_grid(after, g)[0] != want:
            raise ValueError(f'그림 {g:02X}: 빌드한 롬이 기대한 그림으로 풀리지 않음')
        if g in pictures and bytes(after.u8(head_of(after, g) + k) for k in range(6)) != pictures[g][1][:6]:
            raise ValueError(f'그림 {g:02X}: 빌드한 롬의 머리 +0~+5 가 기대와 다름')
    for m in range(M.COUNT):
        if M.monster(after, m) != monsters.get(m, M.monster(rom, m)):
            raise ValueError(f'몬스터 {m:02X}: 레코드가 기대와 다름')
    print(f'문서: 쓰기 {len(manifest["writes"])}개, 그림 {len(pictures)}개·몬스터 {len(monsters)}개를 빌드한 롬에서 확인')


def decode_bytes(raw):
    """머리부터의 바이트를 dq5mongfx.decode 로 푼 조각 목록."""
    data = bytearray(0x180000)
    data[lorom(0x258C99):lorom(0x258C99) + len(raw)] = raw
    data[lorom(0x258C45):lorom(0x258C45) + 2] = (0x8C99).to_bytes(2, 'little')
    data[lorom(FIND):lorom(FIND) + len(FIND_ORIGINAL)] = FIND_ORIGINAL
    return decode(Rom(data), 0)


def decode_raw(raw, w, h):
    """머리부터의 바이트를 dq5mongfx.decode 로 풀어 색 번호 격자로."""
    d = decode_bytes(raw)
    if (d['w'], d['h']) != (w, h):
        raise ValueError('머리 크기가 다름')
    return [row[1:] for row in M.index_image(d)]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('rom', type=Path)
    sub = parser.add_subparsers(dest='command', required=True)
    export = sub.add_parser('dump')
    export.add_argument('picture')
    export.add_argument('-o', '--out', type=Path, required=True)
    export.add_argument('--monster', help='팔레트를 빌릴 몬스터(16진). 없으면 그 그림을 쓰는 첫 몬스터')
    write = sub.add_parser('patch')
    write.add_argument('source', type=Path)
    write.add_argument('-o', '--out', type=Path, required=True)
    write.add_argument('--at', help='원래 자리보다 긴 그림과 24비트 포인터 표를 놓을 곳(BB:AAAA)')
    write.add_argument('--records-at', help='색이 원래보다 많은 몬스터가 있을 때 레코드 표·레코드를 놓을 곳(BB:AAAA)')
    verify = sub.add_parser('check')
    verify.add_argument('source', type=Path, nargs='?')
    verify.add_argument('--at')
    verify.add_argument('--records-at')
    for p in (write, verify):
        p.add_argument('--progress', type=Path, help='무리 조합 검사의 구역 수를 읽을 dq5progresswrite.py 패치 목록')
        p.add_argument('--areas', type=int, help='무리 조합 검사의 구역 수(기본 85)')
    args = parser.parse_args()
    try:
        rom = Rom(args.rom.read_bytes())
        if args.command == 'dump':
            g = hexbyte(args.picture, 'picture')
            if g not in used_pictures(rom):
                raise ValueError(f'그림 {g:02X}는 몬스터가 쓰는 그림이 아님')
            d, m = dump_image(rom, g, args.out, hexbyte(args.monster, 'monster') if args.monster else None)
            hd = M.parse_header([rom.u8(head_of(rom, g) + k) for k in range(6)])
            print(f'그림 {g:02X} {d["w"]}x{d["h"]}칸 (몬스터 {m:02X} 색) → {args.out}')
            print('header: ' + json.dumps({k: hd[k] for k in HEADER_KEYS}))
            return 0
        doc = json.loads(args.source.read_text(encoding='utf-8')) if getattr(args, 'source', None) else None
        base = args.source.parent if getattr(args, 'source', None) else Path('.')
        at = address(args.at) if args.at else None
        records_at = address(args.records_at) if getattr(args, 'records_at', None) else None
        from dq5monlimits import area_count
        areas = area_count(args.progress, args.areas)
        if args.command == 'check':
            check(rom, doc, base, at, areas, records_at)
            return 0
        manifest = patch(rom, doc, base, at, areas, records_at)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        print(f'patch → {args.out} (쓰기 {len(manifest["writes"])}개)')
        return 0
    except (ValueError, OSError, IndexError, PatchError) as error:
        print(f'오류: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
