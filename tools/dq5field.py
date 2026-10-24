"""DQ5(SFC) 필드(세계 지도). 형식은 docs/dq5-field-format.md.

필드에 나갈 때 01:A5C2 가 RLE(01:A64F) 두 덩어리를 WRAM 포트로 푼다.
  2A:8D3E → 7E:E000-FFFF (8KB)
  17:9A59 → 7F:0000-FFFF (64KB, 256x256 세계 지도. 한 바이트가 한 칸)

RLE: 제어 바이트 c. bit7=0 이면 다음 c+1 바이트를 그대로, bit7=1 이면 n=c&7F 가 0 이면 끝, 아니면 다음 한 바이트를 n+1 번.

사용:
  python tools/dq5field.py rom/dq5.sfc [--compare wram.bin] [--vram vram.bin] [--png out.png]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5map import Rom  # noqa: E402

WORLD = 0x179A59
FIELD_E000 = 0x2A8D3E
# 필드 BG 타일 512개(4bpp). RLE 를 7E:C000-FFFF 에 풀면 비트플레인 0·1·2·3 이 4KB 씩(C000/D000/E000/F000),
# 01:A4CE 가 타일마다 섞어 VRAM 워드 2000- 에 올린다.
FIELD_CHR = 0x12B1A8
# 블록(16x16) 정의: 블록마다 5바이트 = 타일 번호 하위 바이트 4개(왼위·오위·왼아래·오아래) + 상위 비트(bit 0x80>>칸, 00:BC9C).
BLOCK_LOWER = 0x2AA32C
BLOCK_UPPER = 0x2AAD27
# 타일 2개당 1바이트. 니블이 팔레트(00:BBAC): 위층 표는 4비트, 아래층은 3비트.
TILE_PALETTE = 0x2AD712
QUAD_BIT = (0x80, 0x40, 0x20, 0x10)


def rle(rom, a):
    """01:A64F. (풀린 바이트, 다음 주소)."""
    out = bytearray()
    while True:
        c = rom.u8(a)
        a += 1
        if c & 0x80:
            n = c & 0x7F
            if n == 0:
                return bytes(out), a
            out += bytes([rom.u8(a)]) * (n + 1)
            a += 1
        else:
            out += bytes(rom.u8(a + i) for i in range(c + 1))
            a += c + 1


def field_chr(rom):
    """VRAM 0x4000- 에 올라가는 순서의 4bpp 타일 16KB."""
    planes, _ = rle(rom, FIELD_CHR)
    c, d, e, f = (planes[i * 0x1000:(i + 1) * 0x1000] for i in range(4))
    out = bytearray()
    for i in range(512):
        for r in range(8):
            out += bytes([c[i * 8 + r], d[i * 8 + r]])
        for r in range(8):
            out += bytes([e[i * 8 + r], f[i * 8 + r]])
    return bytes(out)


def block_number(world, hibits, x, y):
    """00:BBF7. (x, y) 는 블록 좌표(0~255). 9번째 비트는 7E:E000 비트맵(00:BCA0 은 0x80>>i)."""
    i = y * 256 + x
    return world[i] | ((hibits[i >> 3] >> (7 - (i & 7))) & 1) << 8


def block_tiles(rom, table, m):
    """블록 m 의 네 칸 타일 번호(9비트)."""
    a = table + m * 5
    hi = rom.u8(a + 4)
    return [rom.u8(a + q) | (0x100 if hi & QUAD_BIT[q] else 0) for q in range(4)]


def tile_word(rom, tile, upper):
    """00:BBAC: 타일 번호에 팔레트 비트를 붙인 타일맵 워드."""
    nib = rom.u8(TILE_PALETTE + (tile >> 1))
    if upper:
        p = (nib & 0x0F) << 2 if tile & 1 else (nib & 0xF0) >> 2
    else:
        p = (nib & 0x07) << 2 if tile & 1 else (nib & 0x70) >> 2
    return tile | (p + 8) << 8


def render(rom, world, hibits, vram, cgram, x0, y0, w, h, path, char_base=0x4000):
    """블록 (x0, y0) 부터 w x h 블록을 그린다. 타일 그래픽·팔레트는 필드에 있을 때의 VRAM·CGRAM 덤프."""
    from PIL import Image
    pal = []
    for i in range(256):
        c = cgram[i * 2] | cgram[i * 2 + 1] << 8
        pal.append(tuple((v << 3) | (v >> 2) for v in (c & 31, (c >> 5) & 31, (c >> 10) & 31)))
    img = Image.new('RGB', (w * 16, h * 16), pal[0])
    px = img.load()
    for by in range(h):
        for bx in range(w):
            m = block_number(world, hibits, (x0 + bx) % 256, (y0 + by) % 256)
            for upper, table in ((False, BLOCK_LOWER), (True, BLOCK_UPPER)):
                for q, t in enumerate(block_tiles(rom, table, m)):
                    word = tile_word(rom, t, upper)
                    base = char_base + (word & 0x3FF) * 32
                    pn = (word >> 10) & 7
                    ox, oy = bx * 16 + (q & 1) * 8, by * 16 + (q >> 1) * 8
                    for yy in range(8):
                        b0, b1 = vram[base + yy * 2], vram[base + yy * 2 + 1]
                        b2, b3 = vram[base + 16 + yy * 2], vram[base + 17 + yy * 2]
                        for xx in range(8):
                            s = 7 - xx
                            v = (b0 >> s & 1) | (b1 >> s & 1) << 1 | (b2 >> s & 1) << 2 | (b3 >> s & 1) << 3
                            if v:
                                px[ox + xx, oy + yy] = pal[pn * 16 + v]
    img.save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('--compare')
    ap.add_argument('--png')
    ap.add_argument('--vram', help='필드에 선 순간의 VRAM 덤프(64KB)와 타일 그래픽 비교')
    args = ap.parse_args()
    rom = Rom(open(args.rom, 'rb').read())
    world, end_w = rle(rom, WORLD)
    e000, end_e = rle(rom, FIELD_E000)
    print(f'world {len(world)} bytes ({WORLD:06X}-{end_w - 1:06X}), distinct {len(set(world))}')
    print(f'7E:E000 {len(e000)} bytes ({FIELD_E000:06X}-{end_e - 1:06X})')
    if args.compare:
        w = open(args.compare, 'rb').read()
        print('world == 7F:0000:', world == w[0x10000:0x20000], '/ e000 == 7E:E000:', e000 == w[0xE000:0x10000])
    if args.vram:
        v = open(args.vram, 'rb').read()
        print('field chr == VRAM 4000-7FFF:', field_chr(rom) == v[0x4000:0x8000])
    if args.png:
        from PIL import Image
        Image.frombytes('L', (256, 256), world).resize((512, 512), Image.NEAREST).save(args.png)
    return 0


if __name__ == '__main__':
    sys.exit(main())
