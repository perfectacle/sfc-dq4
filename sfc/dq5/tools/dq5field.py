"""DQ5(SFC) 필드(세계 지도). 형식은 sfc/dq5/docs/dq5-field-format.md.

필드에 나갈 때 01:A5C2 가 RLE(01:A64F) 두 덩어리를 WRAM 포트로 푼다.
  2A:8D3E → 7E:E000-FFFF (8KB)
  17:9A59 → 7F:0000-FFFF (64KB, 256x256 세계 지도. 한 바이트가 한 칸)

RLE: 제어 바이트 c. bit7=0 이면 다음 c+1 바이트를 그대로, bit7=1 이면 n=c&7F 가 0 이면 끝, 아니면 다음 한 바이트를 n+1 번.

세계는 셋이고 01:9F40 이 $1949 로 고른다(0 지상 01:A5C2, 1 01:A5F1, 2 01:A620). 블록·타일 표는 셋이 같다.
마을 입장은 2A:F247: 필드 좌표가 04:FD97 [그룹][X][Y] 와 같고 그룹의 세계가 $1949 와 같으면 0F:EA97 항목으로 들어간다.

사용:
  python sfc/dq5/tools/dq5field.py rom/dq5.sfc [--world N] [--compare wram.bin] [--vram vram.bin] [--png out.png]
  python sfc/dq5/tools/dq5field.py rom/dq5.sfc --entrances
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5map import Rom, lorom  # noqa: E402

WORLD = 0x179A59
FIELD_E000 = 0x2A8D3E
# $1949 = 0, 1, 2 일 때의 (세계 지도 7F:0000, 9번째 비트 7E:E000).
WORLDS = ((WORLD, FIELD_E000), (0x2AB722, 0x2AC310), (0x2AC51A, 0x2AD299))
ENTRANCES = 0x04FD97
# 그룹마다 5바이트. +0 bit0-4 $BD, bit5-6 세계+1, bit7 → $194A bit7 / +1 X / +2 Y / +3 도착 층($C3 → 7E:31A0) / +4 bit0·1·7 → $198E, bit2-6 → $194A
GROUP_ARRIVAL = 0x0FEA97
# 필드 BG 타일 512개(4bpp). RLE 를 7E:C000-FFFF 에 풀면 비트플레인 0·1·2·3 이 4KB 씩(C000/D000/E000/F000),
# 01:A4CE 가 타일마다 섞어 VRAM 워드 2000- 에 올린다.
FIELD_CHR = 0x12B1A8
# 블록(16x16) 정의: 블록마다 5바이트 = 타일 번호 하위 바이트 4개(왼위·오위·왼아래·오아래) + 상위 비트(bit 0x80>>칸, 00:BC9C).
BLOCK_LOWER = 0x2AA32C
BLOCK_UPPER = 0x2AAD27
# 타일 2개당 1바이트. 니블이 팔레트(00:BBAC): 위층 표는 4비트, 아래층은 3비트.
TILE_PALETTE = 0x2AD712
QUAD_BIT = (0x80, 0x40, 0x20, 0x10)
# dq5fieldgfxwrite.py 의 타일 늘리기는 블록 표 읽기 00:BC6D(원래 PHB)를 SEP #$20 으로 시작하는 코드로 바꿔 상위 비트 바이트의
# 하위 니블(00:BCA4 의 08>>칸)을 10번째 비트로 읽는다. 원래 롬의 블록 1,022개는 이 니블이 모두 0 이다.
BLOCK_READ_SITE = 0x00BC6D
# 그 전 판은 00:BC80·BC8D 의 비트 읽기를 JSL 훅으로 바꿔 같은 니블을 읽었다(00:BC6D 는 원래 PHB). 그렇게 만든 롬도 읽는다.
BLOCK_HOOK_SITE = 0x00BC80
QUAD_BIT10 = (0x08, 0x04, 0x02, 0x01)


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


def entrances(rom):
    """04:FD97 입구마다 (그룹, X, Y, 세계, (도착 $BD, X, Y, 층)). 그룹 $50 이상과 2A:F28D 의 예외는 표를 따르지 않는다."""
    out, a = [], ENTRANCES
    while rom.u8(a) != 0xFF:
        g = rom.u8(a)
        e = [rom.u8(GROUP_ARRIVAL + g * 5 + i) for i in range(5)]
        # 2A:FEF5: $50 이상은 $54 를 빼고 세계 0. 05 도 세계 0 으로 본다.
        world = 0 if g >= 0x50 or g == 0x05 else ((e[0] >> 5) & 3) - 1
        out.append((g, rom.u16(a + 1), rom.u16(a + 3), world, (e[0] & 0x1F, e[1], e[2], e[3])))
        a += 5
    return out


def block_number(world, hibits, x, y):
    """00:BBF7. (x, y) 는 블록 좌표(0~255). 9번째 비트는 7E:E000 비트맵(00:BCA0 은 0x80>>i)."""
    i = y * 256 + x
    return world[i] | ((hibits[i >> 3] >> (7 - (i & 7))) & 1) << 8


def wide_tiles(rom):
    """타일 늘리기 패치가 블록의 10번째 비트를 읽는 롬인지."""
    return rom.u8(BLOCK_READ_SITE) == 0xE2 or rom.u8(BLOCK_HOOK_SITE) == 0x22


def block_tiles(rom, table, m):
    """블록 m 의 네 칸 타일 번호(9비트, 타일 늘리기 훅이 있으면 10비트). m 이 511 이상이면 옮긴 표에서 읽는다."""
    a = block_entry(rom, table == BLOCK_UPPER, m)
    hi = rom.u8(a + 4)
    wide = wide_tiles(rom) or m >= 511
    return [rom.u8(a + q) | (0x100 if hi & QUAD_BIT[q] else 0) | (0x200 if wide and hi & QUAD_BIT10[q] else 0)
            for q in range(4)]


# 블록 번호 511 이상(dq5fieldtables.py --blocks-at): 00:BC4E 를 JML 로 바꿔 511 이상이면 옮긴 표에서 읽는다.
# 훅은 BRA 로 건너뛰는 머리 [아래층 표][위층 표 24비트씩][블록 수 16비트] 로 시작하고, 두 표는 번호 511 부터 5바이트씩이다.
BLOCK_GROW_SITE = 0x00BC4E
# 번호 × 5 + 칸을 X 에, 번호 × 5 를 $02 에, 칸을 Y 에 두는 셈(A = 번호, M·X 16비트, C = 0). 결과는 원래 00:BC50~BC6C 와
# 같되($00 만 칸 대신 번호), 칸을 $90 의 LSR 이 남긴 C 와 $92 & 1 의 ROL 로 모아 짧다. 번호 × 4 와 ROL 이 넘치지 않아 C 는 0 이다.
INDEX5 = (b'\x85\x00\x0a\x0a\x65\x00\x85\x02'
          + b'\xa5\x90\x4a\xa5\x92\x29\x01\x00\x2a\xa8\x65\x02\xaa')
# 지형 표(03:CB1B 가 블록 >> 1 을 16비트 X 로 니블을 읽음). 블록을 늘리면 두 읽기의 피연산자를 옮긴 표로 바꾼다.
TERRAIN = 0x03CC48
TERRAIN_SITES = (0x03CB2A, 0x03CB36)
# 블록 번호 10·11번째 비트(dq5fieldwrite.py --planes-at): 00:BBF7·00:BDC5 의 9번째 비트 읽기(00:BC33·00:BE06)를 JSL 로 바꿔
# 세계마다 롬의 8KB 평면(칸마다 1비트, 7E:E000 과 같은 꼴)을 비트마다 하나씩 함께 읽는다. 훅은 BRA 로 건너뛰는 머리
# [세계 0·1·2 의 10번째 비트 평면][세계 0·1·2 의 11번째 비트 평면](24비트씩, 0 이면 없음)로 시작한다. 10번째 비트만 읽던 훅은
# 머리가 앞의 9바이트뿐이라 BRA 의 거리(09)로 가른다. 블록 표를 늘린 롬은 그 앞 00:BBF8·00:BDC9 에서 빠른 훅
# (dq5fieldwrite.fast_hook, 반 바이트 평면)으로 가므로 이 훅은 실행되지 않고 머리로 평면 자리만 알려 준다.
BIT9_SITES = (0x00BC33, 0x00BE06)
BIT11_HEAD = 18
BIT11_BODY = 2 + BIT11_HEAD


def grown_blocks(rom):
    """블록 늘리기 훅이 있으면 (아래층 표, 위층 표, 블록 수). 표는 번호 511 부터. 없으면 None."""
    if rom.u8(BLOCK_GROW_SITE) != 0x5C:
        return None
    hook = rom.u24(BLOCK_GROW_SITE + 1)
    return rom.u24(hook + 2), rom.u24(hook + 5), rom.u16(hook + 8)


def block_count(rom):
    g = grown_blocks(rom)
    return g[2] if g else 511


def block_entry(rom, upper, m):
    """블록 m 의 그 층 5바이트 항목 주소."""
    g = grown_blocks(rom)
    if g and m >= 511:
        return g[1 if upper else 0] + (m - 511) * 5
    return (BLOCK_UPPER if upper else BLOCK_LOWER) + m * 5


def terrain_table(rom):
    return rom.u24(TERRAIN_SITES[0] + 1)


def terrain(rom, m):
    """03:CB1B. 블록 m 의 지형 니블(짝수 블록은 위 니블)."""
    v = rom.u8(terrain_table(rom) + (m >> 1))
    return v & 0x0F if m & 1 else v >> 4


def bit9_planes(rom, bit=9):
    """세계 0·1·2 의 bit(9 = 10번째, 10 = 11번째) 비트 평면 주소(없으면 None). 훅이 없으면 모두 None.
    bit 가 9·10 이 아니면 ValueError."""
    if bit not in (9, 10):
        raise ValueError(f'bit 는 9(10번째 비트)·10(11번째 비트)만: {bit}')
    # 10비트 훅은 JSL 로 머리(BRA)에, 11비트 훅은 JML 로 머리 20바이트 뒤 첫 몸통에 들어간다.
    op = rom.u8(BIT9_SITES[0])
    if op not in (0x22, 0x5C):
        return [None] * 3
    hook = rom.u24(BIT9_SITES[0] + 1) - (BIT11_BODY if op == 0x5C else 0)
    if bit == 10 and rom.u8(hook + 1) != BIT11_HEAD:
        return [None] * 3
    return [rom.u24(hook + 2 + (bit - 9) * 9 + w * 3) or None for w in range(3)]


def world_blocks(rom, world, sources=None):
    """세계 지도 65,536칸의 블록 번호(y*256+x). 10·11번째 비트 평면이 있으면 더한다.
    sources 는 (지도, 9번째 비트) RLE 주소로, 주지 않으면 원래 자리다."""
    src_w, src_e = sources or WORLDS[world]
    low, _ = rle(rom, src_w)
    hi, _ = rle(rom, src_e)
    planes = [hi]
    for bit in (9, 10):
        plane = bit9_planes(rom, bit)[world]
        planes.append(rom.d[lorom(plane):lorom(plane) + 0x2000] if plane else bytes(0x2000))
    return [low[i] | sum(((p[i >> 3] >> (7 - (i & 7))) & 1) << (8 + k) for k, p in enumerate(planes))
            for i in range(65536)]


# dq5fieldgfxwrite.py --worlds-at 은 00:BBB4 등을 JSL 훅으로 바꾸고, 훅 안 LDA long,X 의 피연산자(훅 + 22)가
# 세계마다 256바이트인 니블 표 넷의 시작이다. 타일을 512개 넘게 늘린 훅은 훅 + 13 의 CLC 자리가 ASL A 라
# 세계마다 512바이트다.
NIB_SITE, NIB_HOOK_TABLE, NIB_HOOK_STRIDE = 0x00BBB4, 22, 13
# 타일을 늘리고 세 세계의 니블이 같으면 훅 없이 00:BBAC 를 바꿔(LDA $96 / TAX, 원래는 그 사이에 LSR) 타일맵 워드 윗바이트를
# 타일마다 1바이트 표에서 읽는다. 위층 표는 00:BBB1, 아래층 표는 00:BBC6 의 LDA long,X 가 읽는다.
PALETTE_SITE, PALETTE_UPPER, PALETTE_LOWER = 0x00BBAC, 0x00BBB1, 0x00BBC6
# 세 세계의 니블이 다르면 00:BBAC 를 LDA $7E1949 로 시작하는 코드로 바꿔, 세계마다 2KB 인 타일맵 워드 표(색인
# 세계 << 11 | 타일 << 1)를 위층은 00:BBBA, 아래층은 00:BBCB 의 LDA long,X 로 읽는다.
PALETTE_WORLD_UPPER, PALETTE_WORLD_LOWER = 0x00BBBA, 0x00BBCB


def palette_kind(rom):
    """00:BBAC 가 원래 니블 루틴이면 None, 타일마다 1바이트 표면 'shared', 세계마다 워드 표면 'worlds'."""
    if rom.u8(PALETTE_SITE + 2) == 0xAA:
        return 'shared'
    if rom.u8(PALETTE_SITE) == 0xAF:
        return 'worlds'
    return None


def nibble_table(rom, world=0):
    """00:BBAC 가 그 세계에서 읽는 니블 표 주소. 세계 훅이 없으면 세 세계 모두 2A:D712."""
    if palette_kind(rom):
        raise ValueError('00:BBAC 가 타일마다 팔레트 표를 읽는 롬이라 니블 표가 없음(tile_word 를 쓸 것)')
    if rom.u8(NIB_SITE) == 0x22:
        hook = rom.u24(NIB_SITE + 1)
        stride = 0x200 if rom.u8(hook + NIB_HOOK_STRIDE) == 0x0A else 0x100
        return rom.u24(hook + NIB_HOOK_TABLE) + (world & 3) * stride
    return TILE_PALETTE


def tile_word(rom, tile, upper, world=0):
    """00:BBAC: 타일 번호에 팔레트 비트를 붙인 타일맵 워드."""
    kind = palette_kind(rom)
    if kind == 'shared':
        return tile | rom.u8(rom.u24((PALETTE_UPPER if upper else PALETTE_LOWER) + 1) + tile) << 8
    if kind == 'worlds':
        table = rom.u24((PALETTE_WORLD_UPPER if upper else PALETTE_WORLD_LOWER) + 1)
        return rom.u16(table + ((world & 3) << 11 | tile << 1))
    nib = rom.u8(nibble_table(rom, world) + (tile >> 1))
    if upper:
        p = (nib & 0x0F) << 2 if tile & 1 else (nib & 0xF0) >> 2
    else:
        p = (nib & 0x07) << 2 if tile & 1 else (nib & 0x70) >> 2
    return tile | (p + 8) << 8


def render(rom, world, hibits, vram, cgram, x0, y0, w, h, path, char_base=0x4000, world_no=0):
    """블록 (x0, y0) 부터 w x h 블록을 그린다. 타일 그래픽·팔레트는 필드에 있을 때의 VRAM·CGRAM 덤프.
    world 는 블록 번호 지도 바이트, world_no 는 니블 표를 고르는 세계 번호($1949)."""
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
                    word = tile_word(rom, t, upper, world_no)
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
    ap.add_argument('--world', type=int, default=0, choices=(0, 1, 2), help='$1949')
    ap.add_argument('--entrances', action='store_true', help='04:FD97 입구와 0F:EA97 도착 자리')
    ap.add_argument('--compare')
    ap.add_argument('--png')
    ap.add_argument('--vram', help='필드에 선 순간의 VRAM 덤프(64KB)와 타일 그래픽 비교')
    args = ap.parse_args()
    rom = Rom(open(args.rom, 'rb').read())
    if args.entrances:
        for i, (g, x, y, w, (bd, ax, ay, d)) in enumerate(entrances(rom)):
            print(f'{i:2d} ({x},{y}) world {w} -> {g:02X}/{bd:02X} ({ax},{ay}) layer {d}')
        return 0
    src_w, src_e = WORLDS[args.world]
    world, end_w = rle(rom, src_w)
    e000, end_e = rle(rom, src_e)
    print(f'world {len(world)} bytes ({src_w:06X}-{end_w - 1:06X}), distinct {len(set(world))}')
    print(f'7E:E000 {len(e000)} bytes ({src_e:06X}-{end_e - 1:06X})')
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
