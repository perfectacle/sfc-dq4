"""DQ5(SFC) 실내 맵의 움직이는 타일(맵 CHR 슬롯 BE~). 형식은 sfc/dq5/docs/dq5-graphics-format.md 의 「실내 맵의 움직이는 타일」.

맵에 들어갈 때 03:D3E9 가 03:D82E 의 [BC][BD][k] 3바이트 목록(FF 로 끝)에서 맵을 찾아 03:D806[k](16비트)를 종류
비트마스크로 쓴다(bit15 는 블록만 올리고 움직이지 않는 종류 15, 7E:1ED0 에는 & 7FFF). 종류 t 마다 03:D471 이
03:D786[t*8] 의 블록 4개(FFFF 는 없음)를 01:8B98 로 풀어 CHR 을 슬롯 $1834 부터 올리고, 그 VRAM 워드 주소를
7E:1ED2[t] 에 둔다.
매 프레임 03:D4B5 가 카운터 7E:1ECE(0~BF, 192프레임 주기)를 올리고, 종류마다 03:D964[t*2] = 주기 p,
D965 = 수 c, 03:D982[t*2] = 타일 수 n, 03:D9A0[t*2] = 자료 주소 a 를 쓴다. 1ECE % p == 0 인 프레임에만 움직인다.
  t < 6 : 미리 그린 벌을 바꿔 낀다. 벌 = (1ECE / p) % c (t = 4 는 3 → 1, 왕복), 원본 03:(a + 벌 * n * 32).
  t >= 6: 7E:a 의 CHR 사본을 03:D751 로 한 줄씩 아래로 돌린다(타일 c 개). t = 14 는 7E:$C4(걷는 방향) bit0·bit1 일 때
          가로로 민다(03:D5CC), t = 7 은 03:D5EC(코드 읽기).
돌린 결과는 다음 프레임에 VRAM 7E:1ED2[t] 로 n 타일 DMA 된다.

사용:
  python sfc/dq5/tools/dq5anim.py rom/dq5.sfc                  종류 표와 맵 목록
  python sfc/dq5/tools/dq5anim.py rom/dq5.sfc 01 01            그 맵의 종류
  python sfc/dq5/tools/dq5anim.py rom/dq5.sfc --check 덤프폴더 첫프레임 끝프레임
      dq5gfxdump.lua 가 프레임마다 남긴 fNNNNN.wram·.vram 으로 벌 바꾸기와 줄 돌리기를 롬·앞 프레임과 견준다
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5map import CHR_BANK, Rom, block_table, lorom  # noqa: E402

MAPS = 0x03D82E
MASKS = 0x03D806
BLOCKS = 0x03D786
PERIOD = 0x03D964
TILES = 0x03D982
SOURCE = 0x03D9A0


def map_list(rom):
    out, a = [], MAPS
    while rom.u8(a) != 0xFF:
        out.append((rom.u8(a), rom.u8(a + 1), rom.u8(a + 2)))
        a += 3
    return out


def map_types(rom, bc, bd):
    """(움직이는 종류 목록, 블록만 올리는 종류 목록). 표에 없는 맵은 ([], [])."""
    for b, d, k in map_list(rom):
        if (b, d) == (bc, bd):
            m = rom.u16(MASKS + k)
            moving = [t for t in range(15) if m >> t & 1]
            return moving, [15] if m & 0x8000 else []
    return [], []


def kind(rom, t):
    blocks = [rom.u16(BLOCKS + t * 8 + j * 2) for j in range(4)]
    return {'period': rom.u8(PERIOD + t * 2), 'count': rom.u8(PERIOD + t * 2 + 1), 'tiles': rom.u16(TILES + t * 2),
            'source': rom.u16(SOURCE + t * 2), 'blocks': [b for b in blocks if b != 0xFFFF]}


def frame_index(rom, t, counter):
    k = kind(rom, t)
    f = (counter // k['period']) % k['count']
    return 1 if t == 4 and f == 3 else f


def frame_bytes(rom, t, f):
    """t < 6 의 벌 f(롬 03 뱅크)."""
    k = kind(rom, t)
    o = lorom(0x030000 | k['source']) + f * k['tiles'] * 32
    return rom.d[o:o + k['tiles'] * 32]


def block_chrs(rom, blocks):
    """블록들의 CHR 번호를 처음 나온 순서대로(01:8C15 가 슬롯을 주는 순서)."""
    table, out = block_table(rom), []
    for n in blocks:
        a = table[n]
        b0 = rom.u8(a)
        for i in range(((b0 & 7) + 1) * (((b0 >> 3) & 7) + 1)):
            c = rom.u16(a + 3 + i * 2) & 0x0FFF
            if c not in out:
                out.append(c)
    return out


def chr_raw(rom, c):
    o = lorom((CHR_BANK + (c >> 10)) << 16 | 0x8000 + (c & 0x3FF) * 32)
    return rom.d[o:o + 32]


def roll(tile, n):
    """03:D751: 평면 0·1 의 8워드와 평면 2·3 의 8워드를 각각 n 줄 아래로 돌린다."""
    a = [tile[i * 2:i * 2 + 2] for i in range(8)]
    b = [tile[16 + i * 2:16 + i * 2 + 2] for i in range(8)]
    return b''.join(a[-n:] + a[:-n]) + b''.join(b[-n:] + b[:-n])


def check(rom, d, first, last):
    """덤프 폴더의 프레임마다 견준다. 결과 문자열 목록."""
    def rd(f, ext):
        return open(os.path.join(d, 'f%05d.%s' % (f, ext)), 'rb').read()

    w0 = rd(first, 'wram')
    mask = w0[0x1ED0] | w0[0x1ED1] << 8
    out = ['7E:1ED0 = %04X, 종류 %s' % (mask, [t for t in range(16) if mask >> t & 1])]
    for t in range(15):
        if not mask >> t & 1:
            continue
        k = kind(rom, t)
        dest = (w0[0x1ED2 + t * 2] | w0[0x1ED3 + t * 2] << 8) * 2
        n = k['tiles'] * 32
        same = total = 0
        steps = []
        for f in range(first + 1, last + 1):
            wp, vp, v = rd(f - 1, 'wram'), rd(f - 1, 'vram'), rd(f, 'vram')
            counter = wp[0x1ECE] | wp[0x1ECF] << 8
            got, prev = v[dest:dest + n], vp[dest:dest + n]
            if t < 6:
                total += 1
                same += got == frame_bytes(rom, t, frame_index(rom, t, counter))
            elif got != prev:
                total += 1
                steps.append(counter)
                same += t == 14 or got == b''.join(roll(prev[i:i + 32], 1) for i in range(0, n, 32))
        line = '종류 %d: 주기 %d, 수 %d, 타일 %d, VRAM %04X → %d/%d 맞음' % (
            t, k['period'], k['count'], k['tiles'], dest // 2, same, total)
        if t >= 6:
            line += ', 바뀐 프레임의 1ECE %s' % steps[:8]
        if t >= 6 and t != 14:
            chrs = block_chrs(rom, k['blocks'])
            tiles = [v[dest + i * 32:dest + i * 32 + 32] for i in range(k['tiles'])]
            rows = {r for i, c in enumerate(chrs[:len(tiles)]) for r in range(8) if roll(chr_raw(rom, c), r) == tiles[i]}
            line += ', 블록 CHR %d개와 %s줄 돌린 꼴로 같음' % (len(chrs), sorted(rows))
        out.append(line)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('bc', nargs='?')
    ap.add_argument('bd', nargs='?')
    ap.add_argument('--check', nargs=3, metavar=('DIR', 'FIRST', 'LAST'))
    args = ap.parse_args()
    rom = Rom(open(args.rom, 'rb').read())
    if args.check:
        for line in check(rom, args.check[0], int(args.check[1]), int(args.check[2])):
            print(line)
        return 0
    if args.bc:
        moving, static = map_types(rom, int(args.bc, 16), int(args.bd, 16))
        for t in moving + static:
            k = kind(rom, t)
            if t == 15:
                print('종류 15 (올리기만) 블록 %s' % ' '.join('%03X' % b for b in k['blocks']))
                continue
            print('종류 %2d 주기 %3d 수 %2d 타일 %2d 자료 %06X 블록 %s' % (
                t, k['period'], k['count'], k['tiles'], (0x030000 if t < 6 else 0x7E0000) | k['source'],
                ' '.join('%03X' % b for b in k['blocks'])))
        return 0
    for t in range(16):
        k = kind(rom, t)
        if t == 15:
            print('종류 15 (올리기만) 블록 %s' % ' '.join('%03X' % b for b in k['blocks']))
            continue
        print('종류 %2d 주기 %3d 수 %2d 타일 %2d 자료 %04X 블록 %s' % (
            t, k['period'], k['count'], k['tiles'], k['source'], ' '.join('%03X' % b for b in k['blocks'])))
    for bc, bd, k in map_list(rom):
        moving, static = map_types(rom, bc, bd)
        print('%02X/%02X k=%02X 종류 %s%s' % (bc, bd, k, moving, ' +15' if static else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
