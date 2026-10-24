"""DQ5(SFC) 전투 몬스터 그림. 형식은 docs/dq5-graphics-format.md.

몬스터 번호 m → 27:E5DC[m] 이 가리키는 27 뱅크 레코드 [그림 번호][색 수 n][색 n개(15비트)]. 22:8FF8·22:A5A4 가 읽는다.
그림 번호 g → 머리 포인터: g < 2A 는 25:8C45, 2A~56 은 26:8F99, 57~ 는 27:82E4 (뱅크는 표와 같다, 22:9014).
22:9822 가 머리를 읽어 조각(8x8 또는 16x16 OBJ) 단위로 4bpp 타일을 풀고 7E:4000 버퍼(한 줄 16타일, $200 바이트)에 쓴다.

머리:  +0 플래그  +1~+4 배치 값(22:9314)  +5 상위 니블+1 = 가로 칸 수(F 면 19), 하위 니블+1 = 세로 칸 수(8픽셀 칸)
       +6~ 칸 비트맵(가로 우선, MSB 먼저) → 조각마다 니블 하나(상위 먼저) → 타일 자료
니블:  bit1 = 16x16(타일 4개 TL·TR·BL·BR), bit2·3 이 0 이 아니면 앞 조각의 좌우 반전 복사(자료 1바이트 = 조각 번호,
       bit2 가 0 이면 1픽셀 왼쪽, 22:9E95)
타일:  모드 바이트 M. M bit7 = 마스크 압축(bit6 이면 채움 바이트, 아니면 0), bit0~3 = 비트평면 0~3 이 있는지.
       마스크 압축이면 평면 수만큼의 마스크 바이트 뒤에 자료, 마스크 비트가 1 인 바이트만 자료에서 읽는다(22:9AEB 등).
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5map import Rom  # noqa: E402

RECORDS = 0x27E5DC
COUNT = 236
HEADS = ((0x00, 0x258C45), (0x2A, 0x268F99), (0x57, 0x2782E4))


def monster(rom, m):
    """(그림 번호, 색 목록). 색 목록의 0 번째가 OBJ 팔레트 1번 색이다(0번은 투명)."""
    a = 0x270000 | rom.u16(RECORDS + m * 2)
    n = rom.u8(a + 1)
    return rom.u8(a), [rom.u16(a + 2 + i * 2) for i in range(n)]


def head(rom, g):
    first, table = [h for h in HEADS if g >= h[0]][-1]
    return (table & 0xFF0000) | rom.u16(table + (g - first) * 2)


class Stream:
    def __init__(self, rom, base):
        self.rom, self.base = rom, base

    def u8(self, i):
        return self.rom.u8(self.base + i)


def plane_bytes(s, pos, masked, fill, planes):
    """한 타일의 반(평면 0·1 또는 2·3) 16바이트. planes 는 [아래 평면 있음, 위 평면 있음]."""
    out = bytearray(16)
    for row in range(8):
        for k in range(2):
            if not planes[k]:
                continue
            if masked:
                bit = s.mask_bits.pop(0)
                if not bit:
                    out[row * 2 + k] = fill
                    continue
            out[row * 2 + k] = s.u8(pos[0])
            pos[0] += 1
    return out


def tile(s, pos):
    """pos[0] 위치에서 타일 하나(32바이트)를 풀고 pos 를 옮긴다(22:992A)."""
    m = s.u8(pos[0])
    pos[0] += 1
    masked = bool(m & 0x80)
    fill = 0
    if masked and m & 0x40:
        fill = s.u8(pos[0])
        pos[0] += 1
    planes = [bool(m >> i & 1) for i in range(4)]
    if masked:
        n = sum(planes)
        s.mask_bits = [b >> (7 - i) & 1 for b in (s.u8(pos[0] + j) for j in range(n)) for i in range(8)]
        pos[0] += n
    data = plane_bytes(s, pos, masked, fill, planes[0:2]) + plane_bytes(s, pos, masked, fill, planes[2:4])
    return bytes(data)


def decode(rom, g):
    """그림 g 를 조각 목록으로 푼다. 조각 = (x, y, 16x16 여부, 타일 목록, 좌우 반전)."""
    s = Stream(rom, head(rom, g))
    b5 = s.u8(5)
    w = 0x13 if b5 >> 4 == 0xF else (b5 >> 4) + 1
    h = (b5 & 15) + 1
    nbits = w * h
    cells = [(i % w, i // w) for i in range(nbits) if s.u8(6 + i // 8) >> (7 - i % 8) & 1]
    nib_at = 6 + (nbits + 7) // 8
    pos = [nib_at + (len(cells) + 1) // 2]
    pieces = []
    for k, (x, y) in enumerate(cells):
        nib = s.u8(nib_at + k // 2) >> (0 if k & 1 else 4) & 15
        big = bool(nib & 2)
        if nib & 0xC:
            ref = pieces[s.u8(pos[0])]
            pos[0] += 1
            dx = 0 if nib & 4 else -1
            pieces.append((x * 8 + dx, y * 8, big, ref[3], not ref[4]))
            continue
        tiles = [tile(s, pos) for _ in range(4 if big else 1)]
        pieces.append((x * 8, y * 8, big, tiles, False))
    return {'w': w, 'h': h, 'head': s.base, 'end': s.base + pos[0], 'pieces': pieces}


def pixels(t):
    return [[(t[y * 2] >> (7 - x) & 1) | (t[y * 2 + 1] >> (7 - x) & 1) << 1
             | (t[16 + y * 2] >> (7 - x) & 1) << 2 | (t[17 + y * 2] >> (7 - x) & 1) << 3
             for x in range(8)] for y in range(8)]


def rgb(c):
    # 5비트 → 8비트는 MesenCE 화면과 같게 (v << 3) | (v >> 2).
    return tuple((v << 3) | (v >> 2) for v in (c & 31, (c >> 5) & 31, (c >> 10) & 31))


def index_image(d):
    """색 번호 격자(0 = 투명). 반전 복사가 1픽셀 왼쪽으로 나갈 수 있어 왼쪽에 1픽셀 여백을 둔다."""
    W, H = d['w'] * 8 + 1, d['h'] * 8
    img = [[0] * W for _ in range(H)]
    for x0, y0, big, tiles, flip in d['pieces']:
        n = 2 if big else 1
        for ty in range(n):
            for tx in range(n):
                p = pixels(tiles[ty * n + tx])
                for y in range(8):
                    for x in range(8):
                        v = p[y][x]
                        px = tx * 8 + x
                        if flip:
                            px = n * 8 - 1 - px
                        if v and 0 <= y0 + ty * 8 + y < H:
                            img[y0 + ty * 8 + y][x0 + 1 + px] = v
    return img


def render(rom, m, path, scale=1):
    from PIL import Image

    g, colors = monster(rom, m)
    d = decode(rom, g)
    grid = index_image(d)
    pal = [rgb(c) for c in colors]
    img = Image.new('RGBA', (len(grid[0]), len(grid)), (0, 0, 0, 0))
    for y, row in enumerate(grid):
        for x, v in enumerate(row):
            if v:
                img.putpixel((x, y), pal[v - 1] + (255,) if v - 1 < len(pal) else (255, 0, 255, 255))
    if scale > 1:
        img = img.resize((img.width * scale, img.height * scale), Image.NEAREST)
    if path:
        img.save(path)
    return img


def match_screen(rom, m, shot):
    """게임 화면에서 그림이 가장 잘 맞는 자리와 (맞은 픽셀, 불투명 픽셀) 수."""
    from PIL import Image

    spr = render(rom, m, None)
    a, b = spr.load(), Image.open(shot).convert('RGB').load()
    W, H = Image.open(shot).size
    opaque = [(x, y, a[x, y][:3]) for y in range(spr.height) for x in range(spr.width) if a[x, y][3]]
    best = (0, 0, 0)
    for oy in range(0, H - spr.height + 1):
        for ox in range(0, W - spr.width + 1):
            hit = 0
            for x, y, c in opaque[::7]:
                hit += b[ox + x, oy + y] == c
            if hit > best[0]:
                best = (hit, ox, oy)
    _, ox, oy = best
    hit = sum(1 for x, y, c in opaque if b[ox + x, oy + y] == c)
    return hit, len(opaque), ox, oy


def oam_grid(oam, vram):
    """OAM·VRAM 덤프로 OBJ 만 그린 색 번호 격자(256x224). OBJ 이름 기준 VRAM $6000(바이트 $C000), 두 이름 표는 붙어 있다."""
    grid = [[0] * 256 for _ in range(224)]
    for i in range(127, -1, -1):
        x, y, t, a = oam[i * 4:i * 4 + 4]
        h = oam[512 + (i >> 2)] >> ((i & 3) * 2) & 3
        x |= (h & 1) << 8
        if x >= 256:
            x -= 512
        if y >= 224:
            continue
        t |= (a & 1) << 8
        n = 2 if h >> 1 else 1
        for ty in range(n):
            for tx in range(n):
                p = pixels(vram[0xC000 + ((t + ty * 16 + tx) & 0x1FF) * 32:][:32])
                for yy in range(8):
                    for xx in range(8):
                        sx, sy = tx * 8 + xx, ty * 8 + yy
                        if a & 0x40:
                            sx = n * 8 - 1 - sx
                        if a & 0x80:
                            sy = n * 8 - 1 - sy
                        X, Y = x + sx, y + 1 + sy
                        if p[yy][xx] and 0 <= X < 256 and 0 <= Y < 224:
                            grid[Y][X] = p[yy][xx]
    return grid


def match_oam(rom, m, oam, vram):
    """색 번호로 비교한다. 팔레트를 바꾸는 연출이 있는 전투(EA 등)에서도 쓸 수 있다."""
    grid = oam_grid(oam, vram)
    img = index_image(decode(rom, monster(rom, m)[0]))
    opaque = [(x, y, v) for y, row in enumerate(img) for x, v in enumerate(row) if v]
    best = (0, 0, 0)
    for oy in range(0, 224 - len(img) + 1):
        for ox in range(0, 256 - len(img[0]) + 1):
            hit = sum(grid[oy + y][ox + x] == v for x, y, v in opaque[::7])
            if hit > best[0]:
                best = (hit, ox, oy)
    _, ox, oy = best
    return sum(grid[oy + y][ox + x] == v for x, y, v in opaque), len(opaque), ox, oy


def compare_wram(rom, m, wram):
    """풀어 낸 타일이 7E:4000-7E:5FFF 버퍼(게임이 실제로 푼 결과)에 32바이트째로 있는지."""
    g, _ = monster(rom, m)
    buf = wram[0x4000:0x6000]
    tiles = [t for p in decode(rom, g)['pieces'] if not p[4] for t in p[3]]
    found = sum(1 for t in tiles if any(buf[o:o + 32] == t for o in range(0, len(buf), 32)))
    return found, len(tiles)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('monsters', nargs='*', help='몬스터 번호(16진). 없으면 전체 목록')
    ap.add_argument('--png', help='그림 파일(몬스터 하나) 또는 폴더(여럿)')
    ap.add_argument('--scale', type=int, default=1)
    ap.add_argument('--compare', help='전투 중 WRAM 덤프(128KB): 풀어 낸 타일이 버퍼에 있는지')
    ap.add_argument('--shot', help='전투 화면 PNG: 그림이 화면과 픽셀째로 맞는지')
    ap.add_argument('--oam', nargs=2, metavar=('OAM', 'VRAM'), help='OAM·VRAM 덤프: 그림이 OBJ 색 번호와 맞는지')
    args = ap.parse_args()
    rom = Rom(open(args.rom, 'rb').read())
    ms = [int(x, 16) for x in args.monsters] or range(COUNT)
    for m in ms:
        g, colors = monster(rom, m)
        d = decode(rom, g)
        big = sum(p[2] for p in d['pieces'])
        mirror = sum(p[4] for p in d['pieces'])
        line = (f'{m:02X} 그림 {g:02X} 머리 {d["head"]:06X}-{d["end"]:06X} {d["w"]}x{d["h"]}칸 '
                f'조각 {len(d["pieces"])}(16x16 {big}, 반전 {mirror}) 색 {len(colors)}')
        if args.compare:
            line += ' 버퍼 %d/%d' % compare_wram(rom, m, open(args.compare, 'rb').read())
        if args.shot:
            line += ' 화면 %d/%d @(%d,%d)' % match_screen(rom, m, args.shot)
        if args.oam:
            line += ' OBJ %d/%d @(%d,%d)' % match_oam(rom, m, *(open(f, 'rb').read() for f in args.oam))
        print(line)
        if args.png:
            path = args.png if len(ms) == 1 else os.path.join(args.png, f'{m:02X}.png')
            if len(ms) > 1:
                os.makedirs(args.png, exist_ok=True)
            render(rom, m, path, args.scale)
    return 0


if __name__ == '__main__':
    sys.exit(main())
