"""DQ5(SFC) 필드(세계 지도) 쓰기. 형식은 sfc/dq5/docs/dq5-field-format.md 의 「불러오기」, 패치 목록은
sfc/dq5/docs/dq5-build-format.md.

세계마다 256x256 칸의 블록 번호(9비트)를 RLE 두 덩어리(지도 하위 8비트 64KB, 9번째 비트 8KB)로 싸서 늘린 롬에 놓고,
불러오기 루틴(01:A5C2·A5F1·A620)의 `LDA #뱅크 / STA $4374 / PHA / PLB / LDX #주소 / JSR $A64F` 두 벌의 뱅크·주소를
바꾼다. 01:A64F 는 덩어리를 DMA 원본($4372 16비트 + $4374 뱅크)으로 쓰므로 덩어리 하나는 뱅크를 넘지 않게 놓는다.

지도 파일(.bin)은 칸마다 16비트 리틀 엔디언 블록 번호(0~511)를 y*256+x 순서로 둔 128KB 다.

  dump   세계 N 의 지도 → .bin(-o)
  check  세계 셋을 풀어 다시 싸고 풀면 같은지, 크기는 원래와 얼마나 다른지
  patch  --world N 지도.bin … → 패치 목록(-o). 덩어리는 --at(기본 34:8000) 부터 뱅크를 넘지 않게 차례로 놓는다

사용:
  python sfc/dq5/tools/dq5fieldwrite.py rom/dq5.sfc dump 0 -o work/field/w0.bin
  python sfc/dq5/tools/dq5fieldwrite.py rom/dq5.sfc patch --world 0 work/field/w0.bin -o work/build/field.dq5patch.json
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5field import WORLDS, rle  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402

LOADERS = (0x01A5C2, 0x01A5F1, 0x01A620)
SIZE = 256 * 256


def loader_sites(rom, world):
    """불러오기 루틴의 (9번째 비트, 지도) 덩어리마다 (뱅크 즉값 자리, 주소 즉값 자리) CPU 주소."""
    a, out = LOADERS[world], []
    for _ in range(2):
        # A9 bb 8D 74 43 48 AB A2 ll hh 20 4F A6
        while not (rom.u8(a) == 0xA9 and rom.u16(a + 2) == 0x748D and rom.u8(a + 7) == 0xA2
                   and rom.u8(a + 10) == 0x20 and rom.u16(a + 11) == 0xA64F):
            a += 1
            if a > LOADERS[world] + 0x40:
                raise ValueError(f'세계 {world} 불러오기 루틴의 꼴이 다름')
        out.append((a + 1, a + 8))
        a += 13
    return out


def encode_rle(data):
    """01:A64F 가 푸는 RLE. 3바이트 이상 같은 값은 반복(최대 128), 나머지는 글자 그대로(최대 128). 끝은 80."""
    out, lit, i, n = bytearray(), bytearray(), 0, len(data)

    def flush():
        for k in range(0, len(lit), 128):
            part = lit[k:k + 128]
            out.append(len(part) - 1)
            out.extend(part)
        lit.clear()

    while i < n:
        j = i
        while j < n and data[j] == data[i] and j - i < 128:
            j += 1
        if j - i >= 3:
            flush()
            out += bytes([0x80 | (j - i - 1), data[i]])
            i = j
        else:
            lit.append(data[i])
            i += 1
    flush()
    out.append(0x80)
    return bytes(out)


def split(grid):
    """블록 번호 65536개 → (지도 하위 8비트 64KB, 9번째 비트 8KB). 비트는 0x80 >> (i & 7)(00:BCA0)."""
    low = bytes(v & 0xFF for v in grid)
    hi = bytearray(SIZE // 8)
    for i, v in enumerate(grid):
        if v >> 8:
            hi[i >> 3] |= 0x80 >> (i & 7)
    return low, bytes(hi)


def world_grid(rom, world):
    src_w, src_e = WORLDS[world]
    low, _ = rle(rom, src_w)
    hi, _ = rle(rom, src_e)
    return [low[i] | ((hi[i >> 3] >> (7 - (i & 7))) & 1) << 8 for i in range(SIZE)]


def read_grid(path):
    b = open(path, 'rb').read()
    if len(b) != SIZE * 2:
        raise ValueError(f'{path}: {SIZE * 2}바이트여야 함(지금 {len(b)})')
    grid = [b[i * 2] | b[i * 2 + 1] << 8 for i in range(SIZE)]
    bad = [i for i, v in enumerate(grid) if v > 0x1FF]
    if bad:
        raise ValueError(f'{path}: ({bad[0] % 256},{bad[0] // 256}) 의 블록 {grid[bad[0]]} 가 0~511 밖')
    return grid


def cpu(off):
    return f'{off // 0x8000:02X}:{0x8000 + off % 0x8000:04X}'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('cmd', choices=('dump', 'check', 'patch'))
    ap.add_argument('args', nargs='*')
    ap.add_argument('--world', type=int, action='append', choices=(0, 1, 2))
    ap.add_argument('-o', '--out')
    ap.add_argument('--at', default='34:8000')
    ap.add_argument('--name', default='field')
    a = ap.parse_args()
    data = open(a.rom, 'rb').read()
    rom = Rom(data)
    if a.cmd == 'dump':
        g = world_grid(rom, int(a.args[0]))
        os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True)
        open(a.out, 'wb').write(b''.join(v.to_bytes(2, 'little') for v in g))
        print(f'세계 {a.args[0]} → {a.out}')
        return 0
    if a.cmd == 'check':
        bad = 0
        for w in range(3):
            g = world_grid(rom, w)
            for (src, part) in zip(WORLDS[w], split(g)):
                enc = encode_rle(part)
                _, end = rle(rom, src)
                back, _ = rle(Rom(enc + bytes(0x8000 - len(enc) % 0x8000)), 0x8000)
                ok = back == part
                bad += not ok
                print(f'세계 {w} {src:06X}: 원래 {lorom(end) - lorom(src)}바이트 → {len(enc)}바이트, 다시 풀면 같음 {ok}')
            if split(g) != (rle(rom, WORLDS[w][0])[0], rle(rom, WORLDS[w][1])[0]):
                bad += 1
                print(f'세계 {w}: 지도를 나눈 것이 원래 덩어리와 다름')
        return 1 if bad else 0
    worlds = a.world or []
    if len(worlds) != len(a.args):
        print('오류: --world N 과 지도 파일을 같은 수로', file=sys.stderr)
        return 1
    bank, _, low = a.at.partition(':')
    at = lorom(int(bank, 16) << 16 | int(low, 16))
    writes = []
    for w, path in zip(worlds, a.args):
        try:
            grid = read_grid(path)
        except ValueError as e:
            print(f'오류: {e}', file=sys.stderr)
            return 1
        hi_part, map_part = split(grid)[1], split(grid)[0]
        for (bank_site, addr_site), part, label in zip(loader_sites(rom, w), (hi_part, map_part), ('9번째 비트', '지도')):
            enc = encode_rle(part)
            if len(enc) > 0x8000:
                print(f'오류: 세계 {w} {label} 덩어리 {len(enc)}바이트가 한 뱅크보다 큼', file=sys.stderr)
                return 1
            if at // 0x8000 != (at + len(enc) - 1) // 0x8000:
                at = (at // 0x8000 + 1) * 0x8000
            cpu_at = (at // 0x8000) << 16 | 0x8000 + at % 0x8000
            writes.append({'at': cpu(at), 'hex': enc.hex(' '), 'note': f'세계 {w} {label} RLE'})
            b, ad = lorom(bank_site), lorom(addr_site)
            writes.append({'at': cpu(b), 'hex': f'{cpu_at >> 16:02X}', 'orig': f'{data[b]:02X}',
                           'note': f'세계 {w} {label} 뱅크'})
            writes.append({'at': cpu(ad), 'hex': (cpu_at & 0xFFFF).to_bytes(2, 'little').hex(' '),
                           'orig': data[ad:ad + 2].hex(' '), 'note': f'세계 {w} {label} 주소'})
            at += len(enc)
    doc = {'format': 'dq5patch/1', 'name': a.name, 'rom_size': 4 if at > 0x300000 else 3 if at > 0x200000 else 2,
           'writes': writes}
    os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True)
    with open(a.out, 'w', encoding='utf-8') as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
        f.write('\n')
    print(f'세계 {len(worlds)}개, 쓰기 {len(writes)}개 → {a.out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
