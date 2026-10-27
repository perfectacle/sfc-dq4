"""DQ5(SFC) 필드(세계 지도) 그림 쓰기. 타일 512개·타일 팔레트 니블·필드 팔레트 2·3번 줄·물결 색·움직이는 타일 8벌을
내보내고 고친 것을 넣는다. 블록 정의(2A:A32C·AD27)는 dq5fieldtables.py, 지도는 dq5fieldwrite.py 가 쓴다.
형식은 sfc/dq5/docs/dq5-field-format.md 의 「타일 그래픽과 팔레트」「팔레트」, 입력은
sfc/dq5/docs/dq5-build-format.md 「필드 그림 `dq5fieldgfx/1`」.

  dump   롬 → 폴더(-o). fieldgfx.json, tiles.bin(4bpp SNES 타일 512개), anim.bin(움직이는 타일 6개 × 8벌)
  patch  fieldgfx.json → 패치 목록(-o). 바뀐 것이 없으면 쓰기 0개. 다시 싼 RLE 가 원래보다 길면
         --tiles-at·--anim-at BB:AAAA(30~3F, 한 뱅크 안)로 옮긴다
  check  두 RLE 를 다시 싸서 풀기, 내보낸 그대로 patch 하면 쓰기 0개인지

타일: 12:B1A8 의 RLE(01:A4A7 이 뱅크, 01:A4AE 가 주소 즉값)를 7E:C000 에 풀면 평면 0~3 이 4KB 씩.
움직이는 타일: 1E:D0FF 의 RLE(2B:8006 뱅크, 2B:8016 주소)를 7E:C800 에 1,536바이트. 둘 다 DB 를 자료 뱅크로 두고
DMA 레지스터를 절대 주소로 쓰는 루틴(01:A64F·2B:8039)이 읽으므로 30~3F 의 한 뱅크 안에만 옮긴다.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5field import FIELD_CHR, TILE_PALETTE, rle  # noqa: E402
from dq5gfx import FIELD_ANIM as ANIM, FIELD_ANIM_COUNT, FIELD_ANIM_SETS, FIELD_ANIM_TILE  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402

FORMAT = 'dq5fieldgfx/1'
BANK = 0x8000
TILES = 512
ANIM_BYTES = FIELD_ANIM_COUNT * FIELD_ANIM_SETS * 32
# 이 타일들은 움직이는 타일 벌이 늘 덮으므로 tiles.bin 에서 고쳐도 보이지 않는다.
ANIM_SLOTS = range(FIELD_ANIM_TILE, FIELD_ANIM_TILE + FIELD_ANIM_COUNT)
# 2·3번 줄 색 1~15 를 차례로 60바이트. 세계 0 은 시간대 8벌(01:A132 가 고름), 세계 1·2 는 한 벌.
PALETTE_SETS = {'world1': [0x01A199], 'world0': [0x01A1D5 + k * 60 for k in range(8)], 'world2': [0x01A3B5]}
WAVE, WAVE_STEPS = 0x01A0F6, 10        # 세계 0 의 4번 줄 색 1~3, $1961 단계마다 6바이트
# 2·3번 줄 색 14·15(30색 목록의 13·14·28·29번)는 02:ABEF~ABFE 가 몇 프레임마다 두 값으로 덮으므로 고칠 수 없다.
CYCLED = (13, 14, 28, 29)
SITES = {'tiles': ((0x01A4A8, b'\x12'), (0x01A4AF, b'\xa8\xb1')), 'anim': ((0x2B8007, b'\x1e'), (0x2B8017, b'\xff\xd0'))}
SOURCES = {'tiles': FIELD_CHR, 'anim': ANIM}


def cpu(a):
    return f'{a >> 16:02X}:{a & 0xFFFF:04X}'


def check_sites(rom):
    for kind, sites in SITES.items():
        for at, want in sites:
            if rom.d[lorom(at):lorom(at) + len(want)] != want:
                raise ValueError(f'{cpu(at)}: 원래 롬의 {kind} 즉값이 아님; 원본 롬으로 만들어야 함')


def planar_to_tiles(planes):
    """평면 0~3 이 4KB 씩인 16KB → SNES 4bpp 타일 512개(01:A4CE 가 VRAM 에 올리는 순서)."""
    c, d, e, f = (planes[i * 0x1000:(i + 1) * 0x1000] for i in range(4))
    out = bytearray()
    for i in range(TILES):
        for r in range(8):
            out += bytes([c[i * 8 + r], d[i * 8 + r]])
        for r in range(8):
            out += bytes([e[i * 8 + r], f[i * 8 + r]])
    return bytes(out)


def tiles_to_planar(tiles):
    planes = [bytearray(0x1000) for _ in range(4)]
    for i in range(TILES):
        t = tiles[i * 32:i * 32 + 32]
        for r in range(8):
            planes[0][i * 8 + r], planes[1][i * 8 + r] = t[r * 2], t[r * 2 + 1]
            planes[2][i * 8 + r], planes[3][i * 8 + r] = t[16 + r * 2], t[17 + r * 2]
    return b''.join(bytes(p) for p in planes)


def encode_rle(data):
    """01:A64F 가 푸는 RLE 를 가장 짧게. 글자 그대로 1~128바이트는 [n-1][바이트…], 같은 값 2~128번은 [80|n-1][값], 끝은 80.
    dq5fieldwrite.encode_rle(3번 이상만 반복)보다 짧아 원래 자리에 다시 들어갈 여지가 크다."""
    n = len(data)
    INF = float('inf')
    cost = [0] + [INF] * n
    choice = [None] * (n + 1)
    for i in range(n):
        if cost[i] == INF:
            continue
        for k in range(1, min(128, n - i) + 1):
            if cost[i] + 1 + k < cost[i + k]:
                cost[i + k], choice[i + k] = cost[i] + 1 + k, (i, 'lit')
        k = 1
        while i + k < n and k < 128 and data[i + k] == data[i]:
            k += 1
            if cost[i] + 2 < cost[i + k]:
                cost[i + k], choice[i + k] = cost[i] + 2, (i, 'run')
    parts, j = [], n
    while j:
        i, kind = choice[j]
        parts.append(bytes([0x80 | (j - i - 1), data[i]]) if kind == 'run' else bytes([j - i - 1]) + data[i:j])
        j = i
    return b''.join(reversed(parts)) + b'\x80'


def colors(rom, a, n):
    return [rom.u16(a + i * 2) for i in range(n)]


def original(rom):
    check_sites(rom)
    planes, tiles_end = rle(rom, FIELD_CHR)
    anim, anim_end = rle(rom, ANIM)
    if len(planes) != 0x4000 or len(anim) != ANIM_BYTES:
        raise ValueError('원래 롬의 필드 타일·움직이는 타일 RLE 크기가 다름')
    return {'tiles': planar_to_tiles(planes), 'anim': anim,
            'rle': {'tiles': rom.d[lorom(FIELD_CHR):lorom(tiles_end)], 'anim': rom.d[lorom(ANIM):lorom(anim_end)]},
            'tile_palettes': [rom.u8(TILE_PALETTE + i // 2) >> (0 if i & 1 else 4) & 15 for i in range(TILES)],
            'palettes': {k: [colors(rom, a, 30) for a in v] for k, v in PALETTE_SETS.items()},
            'wave': [colors(rom, WAVE + i * 6, 3) for i in range(WAVE_STEPS)]}


def current(rom):
    """패치한 롬에서 지금 읽히는 타일·움직이는 타일(즉값이 가리키는 RLE)과 니블·팔레트. 검사 도구가 쓴다."""
    out = {}
    for kind in ('tiles', 'anim'):
        (bank_site, _), (addr_site, _) = SITES[kind]
        raw, _ = rle(rom, rom.u8(bank_site) << 16 | rom.u16(addr_site))
        out[kind] = planar_to_tiles(raw) if kind == 'tiles' else raw
    out['tile_palettes'] = [rom.u8(TILE_PALETTE + i // 2) >> (0 if i & 1 else 4) & 15 for i in range(TILES)]
    out['palettes'] = {k: [colors(rom, a, 30) for a in v] for k, v in PALETTE_SETS.items()}
    out['wave'] = [colors(rom, WAVE + i * 6, 3) for i in range(WAVE_STEPS)]
    return out


def dump(rom, out):
    o = original(rom)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, 'tiles.bin'), 'wb') as f:
        f.write(o['tiles'])
    with open(os.path.join(out, 'anim.bin'), 'wb') as f:
        f.write(o['anim'])
    doc = {'format': FORMAT, 'tiles_file': 'tiles.bin', 'anim_file': 'anim.bin',
           'tile_palettes': o['tile_palettes'], 'palettes': o['palettes'], 'wave': o['wave']}
    with open(os.path.join(out, 'fieldgfx.json'), 'w', encoding='utf-8') as f:
        json.dump(doc, f, separators=(',', ':'))
        f.write('\n')
    return doc


def color_list(v, n, name):
    if not isinstance(v, list) or len(v) != n or any(type(c) is not int or not 0 <= c <= 0x7FFF for c in v):
        raise ValueError(f'{name}: 15비트 색 {n}개')
    return v


def patch(rom, doc, folder, tiles_at=None, anim_at=None, name='field-gfx'):
    o = original(rom)
    if not isinstance(doc, dict) or doc.get('format') != FORMAT or \
            set(doc) - {'format', 'tiles_file', 'anim_file', 'tile_palettes', 'palettes', 'wave'}:
        raise ValueError(f'format={FORMAT} 와 tiles_file·anim_file·tile_palettes·palettes·wave 만')
    data = {}
    for kind, key, size in (('tiles', 'tiles_file', TILES * 32), ('anim', 'anim_file', ANIM_BYTES)):
        if not isinstance(doc.get(key), str):
            raise ValueError(f'{key} 는 파일 이름 문자열')
        with open(os.path.join(folder, doc[key]), 'rb') as f:
            data[kind] = f.read()
        if len(data[kind]) != size:
            raise ValueError(f'{doc[key]}: {size}바이트여야 함(개수는 늘리지 않음)')
    nib = doc.get('tile_palettes')
    if not isinstance(nib, list) or len(nib) != TILES or any(type(v) is not int or not 0 <= v <= 15 for v in nib):
        raise ValueError(f'tile_palettes 는 0~15 {TILES}개')
    pals = doc.get('palettes')
    if not isinstance(pals, dict) or set(pals) != set(PALETTE_SETS) or \
            any(not isinstance(pals[k], list) or len(pals[k]) != len(PALETTE_SETS[k]) for k in PALETTE_SETS):
        raise ValueError(f'palettes 는 {sorted(PALETTE_SETS)} 마다 원래 벌 수')
    wave = doc.get('wave')
    if not isinstance(wave, list) or len(wave) != WAVE_STEPS:
        raise ValueError(f'wave 는 {WAVE_STEPS}단계')
    changed_slots = [t for t in ANIM_SLOTS if data['tiles'][t * 32:t * 32 + 32] != o['tiles'][t * 32:t * 32 + 32]]
    if changed_slots:
        print(f'경고: 타일 {changed_slots} 은 움직이는 타일 벌이 늘 덮어 보이지 않음(anim.bin 을 고칠 것)',
              file=sys.stderr)
    writes = []

    def write(addr, raw, note, orig=True):
        w = {'at': cpu(addr), 'hex': raw.hex(' '), 'note': note}
        if orig:
            off = lorom(addr)
            w['orig'] = rom.d[off:off + len(raw)].hex(' ')
        writes.append(w)

    placed = []
    for kind, at in (('tiles', tiles_at), ('anim', anim_at)):
        if data[kind] == o[kind] and at is None:
            continue
        raw = tiles_to_planar(data[kind]) if kind == 'tiles' else data[kind]
        packed = encode_rle(raw)
        if at is None:
            if len(packed) > len(o['rle'][kind]):
                raise ValueError(f'{kind} RLE {len(packed)}바이트가 원래 {len(o["rle"][kind])}바이트보다 김: '
                                 f'--{kind}-at 으로 옮겨야 함')
            write(SOURCES[kind], packed, f'{kind} RLE')
            continue
        bank, low = at >> 16, at & 0xFFFF
        if not 0x30 <= bank <= 0x3F or low < 0x8000 or low + len(packed) > 0x10000:
            raise ValueError(f'--{kind}-at 은 30~3F 의 한 뱅크 안({len(packed)}바이트)')
        if any(at < e and lo < at + len(packed) for lo, e in placed):
            raise ValueError(f'--{kind}-at 자리가 다른 RLE 와 겹침')
        placed.append((at, at + len(packed)))
        write(at, packed, f'{kind} RLE', orig=False)
        (bank_site, _), (addr_site, _) = SITES[kind]
        write(bank_site, bytes([bank]), f'{kind} 뱅크')
        write(addr_site, low.to_bytes(2, 'little'), f'{kind} 주소')
    nib_bytes = bytes(nib[i] << 4 | nib[i + 1] for i in range(0, TILES, 2))
    old = rom.d[lorom(TILE_PALETTE):lorom(TILE_PALETTE) + len(nib_bytes)]
    for i in range(len(nib_bytes)):
        if nib_bytes[i] != old[i]:
            write(TILE_PALETTE + i, bytes([nib_bytes[i]]), f'타일 팔레트 니블 {i * 2:03X}')
    for key, addrs in PALETTE_SETS.items():
        for k, a in enumerate(addrs):
            new = color_list(pals[key][k], 30, f'palettes.{key}[{k}]')
            bad = [i for i in CYCLED if new[i] != o['palettes'][key][k][i]]
            if bad:
                raise ValueError(f'palettes.{key}[{k}] 의 {bad}번은 2·3번 줄 색 14·15 라 게임이 덮어씀')
            if new != o['palettes'][key][k]:
                write(a, b''.join(c.to_bytes(2, 'little') for c in new), f'필드 팔레트 {key} {k}')
    for i in range(WAVE_STEPS):
        new = color_list(wave[i], 3, f'wave[{i}]')
        if new != o['wave'][i]:
            write(WAVE + i * 6, b''.join(c.to_bytes(2, 'little') for c in new), f'물결 색 {i}')
    manifest = {'format': 'dq5patch/1', 'name': name, 'writes': writes}
    if tiles_at is not None or anim_at is not None:
        manifest['rom_size'] = 2
    return manifest


def check(rom, folder):
    o = original(rom)
    bad = 0
    for kind, raw in (('tiles', tiles_to_planar(o['tiles'])), ('anim', o['anim'])):
        packed = encode_rle(raw)
        back, _ = rle(Rom(packed + bytes(BANK - len(packed) % BANK)), 0x8000)
        same = back == raw
        bad += not same
        print(f'{kind}: 원래 RLE {len(o["rle"][kind])}바이트, 다시 싸면 {len(packed)}바이트, 다시 풀면 같음 {same}')
    if tiles_to_planar(o['tiles']) != rle(rom, FIELD_CHR)[0]:
        bad += 1
        print('타일 ↔ 평면 바꾸기가 원래와 다름')
    doc = dump(rom, folder)
    manifest = patch(rom, doc, folder)
    print(f'내보낸 그대로 patch: 쓰기 {len(manifest["writes"])}개')
    return bool(bad or manifest['writes'])


def parse_at(v, name):
    if v is None:
        return None
    if not re.fullmatch(r'[0-9A-Fa-f]{2}:[0-9A-Fa-f]{4}', v):
        raise ValueError(f'{name} 은 BB:AAAA')
    return int(v.replace(':', ''), 16)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom')
    ap.add_argument('cmd', choices=('dump', 'patch', 'check'))
    ap.add_argument('source', nargs='?')
    ap.add_argument('-o', '--out')
    ap.add_argument('--tiles-at')
    ap.add_argument('--anim-at')
    ap.add_argument('--name', default='field-gfx')
    a = ap.parse_args()
    try:
        rom = Rom(open(a.rom, 'rb').read())
        if a.cmd == 'dump':
            if not a.out:
                raise ValueError('dump 에는 -o 폴더')
            dump(rom, a.out)
            print(f'타일 {TILES}개·움직이는 타일 {ANIM_BYTES}바이트 → {a.out}')
            return 0
        if a.cmd == 'check':
            import tempfile
            with tempfile.TemporaryDirectory() as tmp:
                return int(check(rom, tmp))
        if not a.source or not a.out:
            raise ValueError('patch 에는 fieldgfx.json 과 -o')
        with open(a.source, encoding='utf-8') as f:
            doc = json.load(f)
        manifest = patch(rom, doc, os.path.dirname(os.path.abspath(a.source)),
                         parse_at(a.tiles_at, '--tiles-at'), parse_at(a.anim_at, '--anim-at'), a.name)
        os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True)
        with open(a.out, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, ensure_ascii=False, indent=1)
            f.write('\n')
        print(f'쓰기 {len(manifest["writes"])}개 → {a.out}')
        return 0
    except (ValueError, OSError, KeyError, TypeError) as e:
        print(f'오류: {e}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
