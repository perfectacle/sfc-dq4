"""DQ5(SFC) 필드(세계 지도) 쓰기. 형식은 sfc/dq5/docs/dq5-field-format.md 의 「불러오기」, 패치 목록은
sfc/dq5/docs/dq5-build-format.md.

세계마다 256x256 칸의 블록 번호(9비트)를 RLE 두 덩어리(지도 하위 8비트 64KB, 9번째 비트 8KB)로 싸서 늘린 롬에 놓고,
불러오기 루틴(01:A5C2·A5F1·A620)의 `LDA #뱅크 / STA $4374 / PHA / PLB / LDX #주소 / JSR $A64F` 두 벌의 뱅크·주소를
바꾼다. 01:A64F 는 덩어리를 DMA 원본($4372 16비트 + $4374 뱅크)으로 쓰므로 덩어리 하나는 뱅크를 넘지 않게 놓는다.
DB를 바꾼 뒤 01:A668의 LDX $00A5와 01:A67D의 STA $420B도 같은 뱅크를 쓰므로, 확장 영역 중 30~3F만 허용한다.

지도 파일(.bin)은 칸마다 16비트 리틀 엔디언 블록 번호(0~510)를 y*256+x 순서로 둔 128KB 다. dq5fieldtables.py --blocks-at 으로
블록을 늘린 롬에서 만들면 그 블록 수(2,048개까지)를 받는다. 512 이상이 있는 세계는 10번째 비트를, 1,024 이상이 있는 세계는
11번째 비트도 압축하지 않은 8KB 평면으로 --planes-at(30~7D)에 두고, 00:BBF7·00:BDC5 의 9번째 비트 읽기(00:BC33·00:BE06)를
평면도 함께 읽는 훅으로 바꾼다. 평면은 롬이라 게임이 칸을 바꾸는 00:CF50(밤에 빛나는 풀 등, 부르는 곳 넷이 칸과 번호를
즉값으로 줌)은 10·11번째 비트를 바꾸지 못한다. 그래서 그 칸들(즉값을 롬에서 읽으므로 dq5chestwrite.py 의 field 로 옮긴 빛 칸도 따름)에 512 이상을 두면
거부한다. 지도 패치는 상자 패치를 넣은 롬에서 만든다(반대 순서는 dq5chestwrite.py 가 512 이상 칸을 거부).
10·11번째 비트 평면을 쓰는 세계는 한 번의 patch 에 함께 준다(훅이 하나다).

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
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5field import BIT9_SITES, WORLDS, bit9_planes, block_count, rle, world_blocks  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402

LOADERS = (0x01A5C2, 0x01A5F1, 0x01A620)
SIZE = 256 * 256
BLOCK_COUNT = 511
DATA_START, DATA_END = 0x180000, 0x200000


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
        if v >> 8 & 1:
            hi[i >> 3] |= 0x80 >> (i & 7)
    return low, bytes(hi)


# 00:CF50 을 부르는 넷이 $90·$92(8픽셀 칸)를 즉값으로 두는 곳. 원본에서는 블록 (0B,53)·(0B,53)·(11,7C)·(E2,75)~(E2,77).
# 01:A01B 는 밤에 빛나는 풀이라 dq5chestwrite.py 의 field 가 칸을 옮기므로 롬에서 읽는다.
# 꼴: 16진은 그대로 있어야 하는 명령 바이트, x0 x1·y0 y1 은 칸, n0 n1 은 05:EF0F 의 되풀이 횟수 − 1(Y 는 2 씩 줄어듦).
CHANGED_SITES = (
    (0x01A01B, 'A2 x0 x1 86 90 A2 y0 y1 86 92 22 50 CF 00'),
    (0x12EFC1, 'A9 x0 x1 85 90 A9 y0 y1 85 92 A9 CA 00 22 50 CF 00'),
    (0x03BB3C, 'A2 x0 x1 86 90 A2 y0 y1 86 92 7B A9 71 22 50 CF 00'),
    (0x05EF0F, 'A9 y0 y1 85 CA A9 x0 x1 85 CC A2 n0 n1 DA A5 CA 85 92 3A 3A 85 CA A5 CC 85 90'),
)


def changed_cells(rom):
    """게임이 00:CF50 으로 블록을 바꾸는 칸(블록 좌표). 즉값 자리의 명령 바이트가 다르면 거부한다."""
    out = []
    for at, text in CHANGED_SITES:
        raw = rom.d[lorom(at):lorom(at) + len(text.split())]
        v = {}
        for token, b in zip(text.split(), raw):
            if token[0] in 'xyn':
                v[token[0]] = v.get(token[0], 0) | b << 8 * int(token[1])
            elif int(token, 16) != b:
                raise ValueError(f'{at >> 16:02X}:{at & 0xFFFF:04X}: 00:CF50 을 부르는 즉값 꼴이 아님')
        for k in range(v.get('n', 0) + 1):
            out.append((v['x'] >> 1, (v['y'] - 2 * k) >> 1))
    return out
BIT9_ORIG = (bytes.fromhex('bf00e07ee210bb3fa0bc00f002a901eb'), bytes.fromhex('bf00e07ee21039a0bcf002a901eb'))
PLANE = SIZE // 8


def current_sources(rom, world):
    """불러오기 루틴이 지금 가리키는 (지도, 9번째 비트) RLE 주소."""
    (hb, ha), (mb, ma) = loader_sites(rom, world)
    return rom.u8(mb) << 16 | rom.u16(ma), rom.u8(hb) << 16 | rom.u16(ha)


def world_grid(rom, world):
    return world_blocks(rom, world, current_sources(rom, world))


def read_grid(path, count=BLOCK_COUNT):
    with open(path, 'rb') as source:
        b = source.read()
    if len(b) != SIZE * 2:
        raise ValueError(f'{path}: {SIZE * 2}바이트여야 함(지금 {len(b)})')
    grid = [b[i * 2] | b[i * 2 + 1] << 8 for i in range(SIZE)]
    bad = [i for i, v in enumerate(grid) if v >= count]
    if bad:
        hint = '' if count > BLOCK_COUNT else '(511 이상은 dq5fieldtables.py --blocks-at 을 넣은 롬으로 만들 것)'
        raise ValueError(f'{path}: ({bad[0] % 256},{bad[0] // 256}) 의 블록 {grid[bad[0]]} 가 0~{count - 1} 밖{hint}')
    return grid


def bit9_hook(planes, planes10=(None, None, None)):
    """00:BC33·00:BE06 대신(JSL, A 8비트, X 16비트 = 9번째 비트 바이트 자리, Y 아랫바이트 = 칸의 비트 0~7, A 윗바이트 = 번호 하위
    8비트). planes·planes10 은 세계 0·1·2 의 10·11번째 비트 평면 주소(None 이면 그 비트는 0). 7E:E000 과 두 평면의 바이트를
    스택에 쌓고, 11번째 비트부터 꺼내 Y 에 ROL 로 모은다. 나갈 때 A 아랫바이트 = 하위 8비트, 윗바이트 = 비트10 << 2 | 비트9 << 1
    | 비트8 로 원래 루틴의 XBA 뒤와 같고, X·Y 는 원래처럼 칸의 비트 자리다. Y 의 윗바이트는 M 8비트·X 16비트의 TAY(00:BC32)가
    A 윗바이트를 함께 옮긴 것이라, 원래 루틴처럼 SEP #$10 으로 지운 뒤 TYX 한다. 마스크는 원래처럼 00:BCA0 을 긴 주소로 읽는다.
    11번째 비트 평면이 없으면 10번째 비트만 읽는 짧은 훅을 낸다. 이 훅은 명령이 22개에서 35개로 늘어 세계 0 의 움직이는 타일
    위상과 세계 2 의 첫걸음이 원본 게임보다 늦어지므로 쓰지 않을 때는 피한다."""
    if not any(planes10):
        return bit10_hook(planes)
    read = lambda p: b'\xbf' + p.to_bytes(3, 'little') if p else b'\xa9\x00\xea\xea'
    last = read(None) + b'\x48' + read(None) + b'\x48'
    arms = b''
    for k in range(3):
        arms += read(planes[k]) + b'\x48' + read(planes10[k]) + b'\x48' + b'\x80' + bytes([(2 - k) * 12 + len(last)])
    # 세계 0·1·2 의 갈래는 12바이트씩이고 넷째 세계(0)는 BRA 없이 tail 로 이어진다.
    head = (b'\xbf\x00\xe0\x7e\x48\xaf\x49\x19\x7e\x29\x03'
            + b'\xf0\x08\x3a\xf0\x11\x3a\xf0\x1a\x80\x24')
    bit = b'\x68\x3f\xa0\xbc\x00\xc9\x01\x98\x2a\xa8'
    tail = b'\xe2\x10\xbb\xa0\x00' + bit * 3 + b'\x9b\xeb\x6b'
    return (bytes([0x80, 18]) + b''.join((p or 0).to_bytes(3, 'little') for p in (*planes, *planes10))
            + head + arms + last + tail)


def bit10_hook(planes):
    """10번째 비트만 읽는 훅. 머리는 [세계 0·1·2 평면 24비트씩]이고, 나갈 때 A 윗바이트 = 비트9 << 1 | 비트8 이다."""
    slot = [b'\xbf' + p.to_bytes(3, 'little') if p else b'\xa9\x00\xea\xea' for p in planes]
    tail = (b'\x48\xbf\x00\xe0\x7e\xe2\x10\xbb\x3f\xa0\xbc\x00\xc9\x01\x68\x08'
            + b'\x3f\xa0\xbc\x00\xc9\x01\xa9\x00\x2a\x28\x2a\xeb\x6b')
    # 갈래는 세계 0·1·2 의 4바이트 읽기 + BRA(6바이트씩)와 넷째 세계(0). 머리 16바이트 뒤에 붙고 join 은 그 뒤다.
    arms = b''
    for k, sl in enumerate(slot):
        arms += sl + b'\x80' + bytes([(2 - k) * 6 + 4])
    arms += b'\xa9\x00\xea\xea'
    head = b'\xaf\x49\x19\x7e\x29\x03\xf0\x08\x3a\xf0\x0b\x3a\xf0\x0e\x80\x12'
    return b'\x80\x09' + b''.join((p or 0).to_bytes(3, 'little') for p in planes) + head + arms + tail


def plane_bits(grid, bit=9):
    out = bytearray(PLANE)
    for i, v in enumerate(grid):
        if v >> bit & 1:
            out[i >> 3] |= 0x80 >> (i & 7)
    return bytes(out)


def cpu(off):
    return f'{off // 0x8000:02X}:{0x8000 + off % 0x8000:04X}'


def parse_at(value):
    """필드 로더가 읽을 수 있는 확장 뱅크 30~3F의 CPU 주소를 파일 위치로."""
    if not isinstance(value, str) or not re.fullmatch(r'[0-9A-Fa-f]{2}:[0-9A-Fa-f]{4}', value):
        raise ValueError('--at은 BB:AAAA 형식이어야 함')
    bank, low = (int(part, 16) for part in value.split(':'))
    if not 0x30 <= bank <= 0x3F or not 0x8000 <= low <= 0xFFFF:
        raise ValueError('--at은 확장 뱅크 30~3F의 8000~FFFF만 허용함')
    return lorom(bank << 16 | low)


def parse_any(value, option):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9A-Fa-f]{2}:[0-9A-Fa-f]{4}', value):
        raise ValueError(f'{option} 은 BB:AAAA 형식이어야 함')
    bank, low = (int(part, 16) for part in value.split(':'))
    if not 0x30 <= bank <= 0x7D or not 0x8000 <= low <= 0xFFFF:
        raise ValueError(f'{option} 은 30~7D 뱅크의 8000~FFFF')
    return bank << 16 | low


def plane_writes(rom, data, grids, at):
    """번호 512 이상이 있는 세계의 10·11번째 비트 평면과 훅 쓰기, 롬 크기(MB). 평면은 비트마다 그 비트를 쓰는 세계만,
    뱅크를 넘지 않게 8KB 씩."""
    wide = {w: g for w, g in grids.items() if any(v >> 9 for v in g)}
    if not wide:
        if at is not None:
            raise ValueError('--planes-at 은 번호 512 이상의 블록을 쓰는 세계가 있을 때만')
        return [], 2
    if at is None:
        raise ValueError(f'세계 {sorted(wide)} 가 번호 512 이상을 씀: --planes-at 으로 10·11번째 비트 평면 자리를 줄 것')
    if rom.u8(BIT9_SITES[0]) == 0x22 or any(bit9_planes(rom)):
        raise ValueError('이미 10번째 비트 훅이 있는 롬: 평면을 쓰는 세계를 모두 한 번에, 훅이 없는 롬으로 만들 것')
    for site, want in zip(BIT9_SITES, BIT9_ORIG):
        if data[lorom(site):lorom(site) + len(want)] != want:
            raise ValueError(f'{site >> 16:02X}:{site & 0xFFFF:04X}: 원래 롬의 9번째 비트 읽기가 아님')
    cells = changed_cells(rom)
    for w, g in wide.items():
        bad = [(x, y) for x, y in cells if g[y * 256 + x] >> 9]
        if bad:
            raise ValueError(f'세계 {w} 블록 칸 {bad[0]}: 게임이 00:CF50 으로 바꾸는 칸이라 10·11번째 비트를 쓸 수 없음(512 미만만)')
    eleven = any(v >> 10 for g in wide.values() for v in g)
    size = len(bit9_hook([None] * 3, [0x8000 if eleven else None] * 3))
    if (at & 0xFFFF) + size > 0x10000:
        raise ValueError(f'--planes-at: 훅 {size}바이트가 한 뱅크 안에 들어가지 않음')
    planes, a, out = {9: [None] * 3, 10: [None] * 3}, at + size, []
    for w, bit in ((w, bit) for w in sorted(wide) for bit in (9, 10)):
        if not any(v >> bit & 1 for v in wide[w]):
            continue
        # 훅이나 앞 평면이 뱅크 끝에 딱 맞으면 a 가 다음 뱅크 0000 이 되는데, 그 자리는 LoROM 의 롬이 아니다
        if a & 0xFFFF < 0x8000:
            a |= 0x8000
        elif (a & 0xFFFF) + PLANE > 0x10000:
            a = ((a >> 16) + 1) << 16 | 0x8000
        if a >> 16 > 0x7D:
            raise ValueError('--planes-at: 평면이 뱅크 7D 를 넘음')
        planes[bit][w] = a
        out.append({'at': f'{a >> 16:02X}:{a & 0xFFFF:04X}', 'hex': plane_bits(wide[w], bit).hex(' '),
                    'note': f'세계 {w} 블록 번호 {bit + 1}번째 비트 평면'})
        a += PLANE
    hook = bit9_hook(planes[9], planes[10])
    out.insert(0, {'at': f'{at >> 16:02X}:{at & 0xFFFF:04X}', 'hex': hook.hex(' '), 'note': '블록 번호 10·11번째 비트 훅'})
    for site, want in zip(BIT9_SITES, BIT9_ORIG):
        skip = len(want) - 6
        raw = b'\x22' + at.to_bytes(3, 'little') + b'\x80' + bytes([skip]) + b'\xea' * skip
        out.append({'at': f'{site >> 16:02X}:{site & 0xFFFF:04X}', 'hex': raw.hex(' '), 'orig': want.hex(' '),
                    'note': '9번째 비트 읽기를 10·11번째 비트 훅으로'})
    end = lorom(a - 1) + 1
    return out, 4 if end > 0x300000 else 3 if end > 0x200000 else 2


def place_chunk(at, size):
    """한 뱅크 안에 놓고, 맞춘 뒤에도 필드 로더의 주소 범위인지 확인한다."""
    if not 1 <= size <= 0x8000:
        raise ValueError(f'필드 압축 덩어리 {size}바이트가 1~32768 밖')
    if not DATA_START <= at < DATA_END:
        raise ValueError('필드 압축 덩어리는 확장 뱅크 30~3F에 놓아야 함')
    if at // 0x8000 != (at + size - 1) // 0x8000:
        at = (at // 0x8000 + 1) * 0x8000
    if at + size > DATA_END:
        raise ValueError('필드 압축 덩어리가 뱅크 3F 끝을 넘음')
    return at


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('cmd', choices=('dump', 'check', 'patch'))
    ap.add_argument('args', nargs='*')
    ap.add_argument('--world', type=int, action='append', choices=(0, 1, 2))
    ap.add_argument('-o', '--out')
    ap.add_argument('--at', default='34:8000', help='CPU 주소 BB:AAAA, 뱅크 30~3F만 허용')
    ap.add_argument('--planes-at', help='번호 512 이상이 있는 세계의 10·11번째 비트 평면·훅 자리(BB:AAAA, 30~7D)')
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
    try:
        at = parse_at(a.at)
    except ValueError as e:
        print(f'오류: {e}', file=sys.stderr)
        return 1
    try:
        planes_at = None if a.planes_at is None else parse_any(a.planes_at, '--planes-at')
        grids = {w: read_grid(path, block_count(rom)) for w, path in zip(worlds, a.args)}
        tail, size = plane_writes(rom, data, grids, planes_at)
    except ValueError as e:
        print(f'오류: {e}', file=sys.stderr)
        return 1
    writes = []
    for w, grid in grids.items():
        hi_part, map_part = split(grid)[1], split(grid)[0]
        for (bank_site, addr_site), part, label in zip(loader_sites(rom, w), (hi_part, map_part), ('9번째 비트', '지도')):
            enc = encode_rle(part)
            try:
                at = place_chunk(at, len(enc))
            except ValueError as e:
                print(f'오류: 세계 {w} {label}: {e}', file=sys.stderr)
                return 1
            cpu_at = (at // 0x8000) << 16 | 0x8000 + at % 0x8000
            writes.append({'at': cpu(at), 'hex': enc.hex(' '), 'note': f'세계 {w} {label} RLE'})
            b, ad = lorom(bank_site), lorom(addr_site)
            writes.append({'at': cpu(b), 'hex': f'{cpu_at >> 16:02X}', 'orig': f'{data[b]:02X}',
                           'note': f'세계 {w} {label} 뱅크'})
            writes.append({'at': cpu(ad), 'hex': (cpu_at & 0xFFFF).to_bytes(2, 'little').hex(' '),
                           'orig': data[ad:ad + 2].hex(' '), 'note': f'세계 {w} {label} 주소'})
            at += len(enc)
    doc = {'format': 'dq5patch/1', 'name': a.name, 'rom_size': size, 'writes': writes + tail}
    os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True)
    with open(a.out, 'w', encoding='utf-8') as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
        f.write('\n')
    print(f'세계 {len(worlds)}개, 쓰기 {len(writes)}개 → {a.out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
