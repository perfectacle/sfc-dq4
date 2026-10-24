"""DQ5(SFC) 전투 배경(몬스터 뒤의 그림 띠). 형식은 docs/dq5-graphics-format.md.

$1AA0 을 정하는 곳: 필드는 걸음마다 01:84CF 가 지형(03:CB1B, 0~D)을 그대로 쓰고, 실내 맵은 들어갈 때 01:83E6 이
  맵 표(23:FD6A[BC] + BD*6)의 +3 에 80 을 OR 해 쓴다. 이벤트 전투는 따로 쓴다(첫 필드 이벤트 02:A77B 는 06).
  $1AA1 은 01:843D 의 21:8000 이 carry 를 돌려주면 1(팔레트만 두 번째 벌로 바뀐다).
배경 번호 n → 22:8983[n] 16비트 값 V (22:85EE). $1AA0 bit7 이 꺼져 있으면 n = $1AA0, 켜져 있으면 n = $1AA0 - 72
  (실내 맵 +3 값 v 는 n = v + E). n 은 0~30(49개).
  V 하위 바이트 & FC = 종류 오프셋 k($0D14, 종류 번호 = k/4), 하위 2비트 → $0DF2,
  상위 바이트 = 타일맵 상위 바이트 H($64: 팔레트·타일 번호 상위 2비트).
종류 k 로 찾는 표(모두 28 뱅크 16비트 포인터):
  28:82F9+k  그림 A(아래 띠 타일 재료)   28:82FB+k  그림 B(위 띠 타일, VRAM $5000 = BG 타일 $300~$3FF)
  28:C9C2+k*1.5  목록 1(BG1 위 띠)  +2 목록 2(BG2)  +4 목록 3(그림 A 의 타일을 골라 BG 타일 $200~$2FF 로)
  28:BDFC+k'  팔레트 레코드(22:8801). k' = k, 시대 값 $1949 가 0 이고 $1AA1 ≠ 0 이면 k+2,
              $1949=1 이고 k < 1E 이면 k+98, $1949≥2 이고 k < 1E 이면 k+B4.
그림(22:CA81 → 22:CB62·22:C959·22:C9F4): +0 상위 니블+1 = 가로 칸 수 w, 하위 니블+1 = 세로 칸 수 h,
  +1~ w*h 비트 칸 비트맵(가로 우선, MSB 먼저, 1 = 타일 있음), 그 뒤 있는 칸마다 4bpp 타일 하나
  (몬스터 그림과 같은 모드 바이트 형식, dq5mongfx.tile). 칸 (x, y) 는 7E:4000 + y*$200 + x*$20 에 놓인다
  (한 줄 16타일). 비트가 0 인 칸은 쓰지 않아 버퍼에 있던 값이 남는다(타일맵이 쓰지 않으므로 여기서는 0).
  그림 B 는 다 푼 뒤 첫 타일을 0 으로 지우고 7E:4000~5FFF 를 VRAM $5000 으로 보낸다.
목록 3(22:870D): [타일 번호 t][c] 를 FF 까지. 그림 A 의 타일 t 하나를 (c & 3F)+1 번 되풀이해 7E:6000~ 에 이어 붙이고,
  7E:6000~7FFF 를 VRAM $4000(BG 타일 $200~$2FF)으로 보낸다.
목록 1·2(22:8878): [타일 번호 하위 바이트][f] 를 FF 까지. 타일맵 칸 (f & 3F)+1 개를 같은 값으로 채운다.
  칸 = 하위 t, 상위 H | (f bit7 → 40 좌우 반전) | (f bit6 → 04 팔레트+1). 32칸 한 줄, $1C0 칸을 WRAM 7E:8A1D 에 쓴다.
  목록 1 → VRAM $0CC0(BG1, 32x64 의 38줄째), 목록 2 → $04C0(BG2 38줄째). $1949=2 이고 $1AA0 < 80 이고 $1AA0 ≠ 7 이면
  목록 2 대신 28:FD64. 그 뒤 BG2 $05C0(46줄째~)을 0 으로 지우고 BG1 $0DC0(46줄째~ 8줄)에 타일 $200~$2FF 를
  차례로 깐다(팔레트 = 팔레트 레코드의 시작 칸).
팔레트 레코드: [개수][시작 칸 s] 뒤에 개수만큼 [색 수 m][15비트 색 m개]. 칸 s, s+1, … 의 CGRAM 팔레트
  1번 색부터 채운다(22:A576 → 22:A5A4, 22:AB23 = 7E:2D00 + s*$20).
결과 띠: 32x16 칸(256x128). 위 8줄 = BG1 목록 1 위에 겹친 BG2 목록 2, 아래 8줄 = BG1 타일 $200~$2FF.
레코드가 채우지 않는 팔레트(예: 실내용 H=07 의 팔레트 1·2)는 22:8811 이 깔아 둔 7E:3914 사본, 곧 전투 직전 맵의 색이다.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5map import Rom  # noqa: E402
from dq5mongfx import Stream, pixels, rgb, tile  # noqa: E402

NUMBERS = 0x228983
COUNT = 0x31
PICS = 0x2882F9
LISTS = 0x28C9C2
PALS = 0x28BDFC
ALT_LIST2 = 0x28FD64


def entry(rom, n):
    """(종류 오프셋 k, 상위 바이트 H, $0DF2)."""
    v = rom.u16(NUMBERS + n * 2)
    return v & 0xFC, v >> 8, (v & 1) << 1 | (v >> 1 & 1)


def picture(rom, a):
    """그림 하나를 7E:4000 버퍼처럼 256타일(8KB) 바이트열로 푼다. 없는 칸은 0."""
    s = Stream(rom, a)
    b = s.u8(0)
    w, h = (b >> 4) + 1, (b & 15) + 1
    n = w * h
    pos = [1 + (n + 7) // 8]
    buf = bytearray(0x2000)
    for i in range(n):
        if s.u8(1 + i // 8) >> (7 - i % 8) & 1:
            o = (i // w) * 0x200 + (i % w) * 0x20
            buf[o:o + 32] = tile(s, pos)
    return buf, w, h, a + pos[0]


def palette(rom, k, era=0, alt=False):
    """{CGRAM 팔레트 번호: [색 1번부터]}, 시작 칸."""
    if era == 0:
        k += 2 if alt else 0
    elif k < 0x1E:
        k += 0x98 if era == 1 else 0xB4
    p = 0x280000 | rom.u16(PALS + k)
    count, slot = rom.u8(p), rom.u8(p + 1)
    q, out = p + 2, {}
    for i in range(count):
        m = rom.u8(q)
        out[(slot + i) & 15] = [rom.u16(q + 1 + j * 2) for j in range(m)]
        q += 1 + m * 2
    return out, slot


def tile_list(rom, a):
    """[(시작 타일, 개수)] (FF 까지)."""
    out = []
    while rom.u8(a) != 0xFF:
        out.append((rom.u8(a), (rom.u8(a + 1) & 0x3F) + 1))
        a += 2
    return out


def map_list(rom, a, hi):
    """타일맵 칸 값 목록(16비트)."""
    out = []
    while rom.u8(a) != 0xFF:
        t, f = rom.u8(a), rom.u8(a + 1)
        h = hi | (f >> 1 & 0x40)
        h += (f >> 1 & 0x20) >> 3
        out += [(h & 0xFF) << 8 | t] * ((f & 0x3F) + 1)
        a += 2
    return out


def build(rom, n, era=0, alt=False, indoor=False):
    """VRAM 에 올라가는 것을 재현한다: 타일 $200~$3FF, BG1·BG2 띠 타일맵(각 16줄), 팔레트."""
    k, hi, _ = entry(rom, n)
    pa = 0x280000 | rom.u16(PICS + k)
    pb = 0x280000 | rom.u16(PICS + k + 2)
    bufb = bytearray(picture(rom, pb)[0])
    bufb[0:32] = bytes(32)
    bufa = picture(rom, pa)[0]
    x = k + (k >> 1)
    l1, l2, l3 = (0x280000 | rom.u16(LISTS + x + i) for i in (0, 2, 4))
    if era == 2 and not indoor and n != 7:
        l2 = ALT_LIST2
    low = bytearray(0x2000)
    o = 0
    for t, c in tile_list(rom, l3):
        for j in range(c):
            if o < 0x2000:
                low[o:o + 32] = bufa[t * 32:t * 32 + 32]
            o += 32
    tiles = {0x200 + i: bytes(low[i * 32:i * 32 + 32]) for i in range(256)}
    tiles.update({0x300 + i: bytes(bufb[i * 32:i * 32 + 32]) for i in range(256)})
    pals, slot = palette(rom, k, era, alt)
    m1 = (map_list(rom, l1, hi) + [0] * 0x1C0)[:0x1C0]
    m2 = (map_list(rom, l2, hi) + [0] * 0x1C0)[:0x1C0]
    bg1 = m1[:0x100] + [(slot & 7) << 10 | (0x200 + i) for i in range(256)]
    bg2 = m2[:0x100] + [0] * 0x100
    return {'k': k, 'hi': hi, 'pics': (pa, pb), 'lists': (l1, l2, l3), 'tiles': tiles,
            'bg1': bg1, 'bg2': bg2, 'pals': pals, 'slot': slot, 'list1_len': len(map_list(rom, l1, hi)),
            'list2_len': len(map_list(rom, l2, hi)), 'list3_tiles': o // 32}


def compose(tiles, bg1, bg2, color):
    """두 층을 모드 1 우선순위(BG1 높음 > BG2 높음 > BG1 낮음 > BG2 낮음)로 겹친 256x128 (팔레트, 색 번호) 격자.
    tiles 는 타일 번호 → 32바이트(없으면 투명), color(팔레트, 번호) 는 쓰지 않고 격자만 돌려준다."""
    W, H = 256, 128
    best = [[(0, 0, 0)] * W for _ in range(H)]
    for layer, m in ((2, bg2), (1, bg1)):
        for i, v in enumerate(m):
            t = tiles.get(v & 0x3FF)
            if t is None:
                continue
            p = pixels(t)
            pal, pri = v >> 10 & 7, v >> 13 & 1
            rank = {(1, 1): 4, (2, 1): 3, (1, 0): 2, (2, 0): 1}[(layer, pri)]
            cx, cy = i % 32 * 8, i // 32 * 8
            for y in range(8):
                for xx in range(8):
                    sx = 7 - xx if v & 0x4000 else xx
                    sy = 7 - y if v & 0x8000 else y
                    c = p[sy][sx]
                    if c and rank > best[cy + y][cx + xx][0]:
                        best[cy + y][cx + xx] = (rank, pal, c)
    return [[(r[1], r[2]) if r[0] else None for r in row] for row in best]


def to_image(grid, color):
    from PIL import Image

    img = Image.new('RGB', (256, len(grid)))
    px = img.load()
    for y, row in enumerate(grid):
        for x, v in enumerate(row):
            px[x, y] = color(v)
    return img


def render(rom, n, era=0, alt=False, base=None):
    """배경 n 의 256x128 PIL 그림. 투명(뒤 색)은 검정.
    팔레트 레코드가 채우지 않는 색은 전투 직전 CGRAM(22:8811 이 7E:3914 사본을 그대로 깔고 시작한다)의 몫이라
    롬만으로는 정할 수 없다. base(CGRAM 512바이트)를 주면 그 색을 쓰고, 없으면 자홍으로 칠한다."""
    d = build(rom, n, era, alt)

    def color(v):
        if v is None:
            return (0, 0, 0)
        cs = d['pals'].get(v[0])
        if cs is not None and v[1] - 1 < len(cs):
            return rgb(cs[v[1] - 1])
        if base:
            i = v[0] * 16 + v[1]
            return rgb(base[i * 2] | base[i * 2 + 1] << 8)
        return (255, 0, 255)

    return to_image(compose(d['tiles'], d['bg1'], d['bg2'], color), color)


def compare(rom, n, dump, frame, era=0, alt=False):
    """MesenCE 덤프(dq5battledump.lua 의 v/c/w<프레임>)와 맞춘다. 결과 문자열 목록."""
    def rd(p):
        return open(os.path.join(dump, p % frame), 'rb').read()

    vram, cg = rd('v%05d.vram'), rd('c%05d.cgram')
    d = build(rom, n, era, alt)
    out = []
    used = {v & 0x3FF for v in d['bg1'] + d['bg2'] if v}
    for lo, name in ((0x200, '타일 $200~$2FF (VRAM $4000)'), (0x300, '타일 $300~$3FF (VRAM $5000)')):
        same = [t for t in range(lo, lo + 256) if vram[(0x2000 + t * 16) * 2:][:32] == d['tiles'][t]]
        u = [t for t in range(lo, lo + 256) if t in used]
        out.append('%s: %d/256 같음, 타일맵이 쓰는 %d개 중 %d개 같음' % (
            name, len(same), len(u), sum(t in same for t in u)))
    for name, base, m in (('BG1 $0CC0 위 8줄', 0x0CC0, d['bg1'][:0x100]), ('BG1 $0DC0 아래 8줄', 0x0DC0, d['bg1'][0x100:]),
                          ('BG2 $04C0 8줄', 0x04C0, d['bg2'][:0x100])):
        got = [vram[(base + i) * 2] | vram[(base + i) * 2 + 1] << 8 for i in range(0x100)]
        out.append('%s: %d/256 칸 같음' % (name, sum(a == b for a, b in zip(got, m))))
    for p, cs in sorted(d['pals'].items()):
        got = [cg[(p * 16 + 1 + j) * 2] | cg[(p * 16 + 1 + j) * 2 + 1] << 8 for j in range(len(cs))]
        out.append('팔레트 %d: %d/%d 색 같음' % (p, sum(a == b for a, b in zip(got, cs)), len(cs)))
    try:
        w = rd('w%05d.bin')
        out.append('WRAM $1AA0=%02X $1AA1=%02X $1949=%02X' % (w[0x1AA0], w[0x1AA1], w[0x1949]))
    except OSError:
        pass
    shot = os.path.join(dump, 's%05d.png' % frame)
    if os.path.exists(shot):
        out.append(match_screen(render(rom, n, era, alt, cg), shot))
    return out


def match_screen(img, shot):
    """화면 줄마다 띠의 어느 줄과 가장 많이 맞는지 찾는다(띠는 HDMA 로 세로로 늘었다 줄었다 한다)."""
    from PIL import Image

    a, s = img.load(), Image.open(shot).convert('RGB')
    b = s.load()
    rows = []
    for y in range(s.height):
        hit, ry = max((sum(b[x, y] == a[x, r] for x in range(256)), r) for r in range(img.height))
        if hit >= 128:
            rows.append((y, ry, hit))
    if not rows:
        return '화면: 띠와 맞는 줄 없음'
    full = sum(h == 256 for _, _, h in rows)
    return '화면: %d줄이 띠의 줄과 맞음(y %d~%d ← 띠 줄 %d~%d), 그중 %d줄은 256픽셀 모두, 픽셀 %d/%d' % (
        len(rows), rows[0][0], rows[-1][0], min(r for _, r, _ in rows), max(r for _, r, _ in rows), full,
        sum(h for _, _, h in rows), 256 * len(rows))


def vram_image(dump, frame):
    """덤프의 VRAM·CGRAM 만으로 같은 띠(BG1 38~53줄, BG2 38~45줄)를 그린다(맞춰 보기용)."""
    vram = open(os.path.join(dump, 'v%05d.vram' % frame), 'rb').read()
    cg = open(os.path.join(dump, 'c%05d.cgram' % frame), 'rb').read()
    tiles = {t: vram[(0x2000 + t * 16) * 2:][:32] for t in range(0x400)}

    def word(a):
        return vram[a * 2] | vram[a * 2 + 1] << 8

    bg1 = [word(0x0CC0 + i) for i in range(0x200)]
    bg2 = [word(0x04C0 + i) for i in range(0x100)] + [0] * 0x100

    def color(v):
        if v is None:
            return (0, 0, 0)
        i = v[0] * 16 + v[1]
        return rgb(cg[i * 2] | cg[i * 2 + 1] << 8)

    return to_image(compose(tiles, bg1, bg2, color), color)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('numbers', nargs='*', help='배경 번호(16진, $1AA0 & 7F). 없으면 전체 목록')
    ap.add_argument('--png', help='그림 파일(하나) 또는 폴더(여럿)')
    ap.add_argument('--era', type=int, default=0, help='$1949 값(0·1·2)')
    ap.add_argument('--alt', action='store_true', help='$1AA1 ≠ 0 (시대 0 에서 팔레트 두 번째 벌)')
    ap.add_argument('--cgram', help='레코드 밖 팔레트 색을 가져올 CGRAM 덤프(전투 직전 맵의 색)')
    ap.add_argument('--compare', nargs=2, metavar=('DUMPDIR', 'FRAME'), help='dq5battledump.lua 덤프와 맞춘다')
    args = ap.parse_args()
    rom = Rom(open(args.rom, 'rb').read())
    base = open(args.cgram, 'rb').read() if args.cgram else None
    nums = [int(a, 16) for a in args.numbers] or list(range(COUNT))
    if not args.numbers:
        print('번호 종류 상위  그림A  그림B  목록1  목록2  목록3 팔레트')
    for n in nums:
        d = build(rom, n, args.era, args.alt)
        print('%02X   %02X   %02X  %06X %06X %06X %06X %06X 칸%d~%s' % (
            n, d['k'] // 4, d['hi'], *d['pics'], *d['lists'], d['slot'], ','.join(str(p) for p in sorted(d['pals']))))
        if args.png:
            img = render(rom, n, args.era, args.alt, base)
            if len(nums) > 1 or os.path.isdir(args.png):
                os.makedirs(args.png, exist_ok=True)
                img.save(os.path.join(args.png, 'bg%02X.png' % n))
            else:
                img.save(args.png)
        if args.compare:
            for line in compare(rom, n, args.compare[0], int(args.compare[1]), args.era, args.alt):
                print('  ' + line)


if __name__ == '__main__':
    main()
