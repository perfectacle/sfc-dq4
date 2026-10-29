"""DQ5(SFC) 필드(세계 지도) 그림 쓰기. 타일 512개·타일 팔레트 니블·필드 팔레트 2·3번 줄·물결 색·움직이는 타일 벌·
세계 0 낮밤 인물 팔레트(11·12번 줄)를 내보내고 고친 것을 넣는다. 블록 정의(2A:A32C·AD27)는 dq5fieldtables.py,
지도는 dq5fieldwrite.py 가 쓴다. 형식은 sfc/dq5/docs/dq5-field-format.md 의 「타일 그래픽과 팔레트」「팔레트」, 입력은
sfc/dq5/docs/dq5-build-format.md 「필드 그림 `dq5fieldgfx/1`」.

  dump   롬 → 폴더(-o). fieldgfx.json, tiles.bin(4bpp SNES 타일 512개), anim.bin(움직이는 타일 6개 × 8벌)
  patch  fieldgfx.json → 패치 목록(-o). 바뀐 것이 없으면 쓰기 0개. 다시 싼 RLE 가 원래보다 길면
         --tiles-at·--anim-at BB:AAAA(30~3F, 한 뱅크 안)로 옮긴다. 움직이는 타일 벌 수를 바꾸면 --anim-at,
         세계 1·2 의 타일 벌(worlds)을 주면 --worlds-at 이 필요하다
  check  두 RLE 를 다시 싸서 풀기, 내보낸 그대로 patch 하면 쓰기 0개인지

타일: 12:B1A8 의 RLE(01:A4A7 이 뱅크, 01:A4AE 가 주소 즉값)를 7E:C000 에 풀면 평면 0~3 이 4KB 씩.
움직이는 타일: 1E:D0FF 의 RLE(2B:8006 뱅크, 2B:8016 주소)를 7E:C800 에 1,536바이트. 둘 다 DB 를 자료 뱅크로 두고
DMA 레지스터를 절대 주소로 쓰는 루틴(01:A64F·2B:8039)이 읽으므로 30~3F 의 한 뱅크 안에만 옮긴다.
벌은 02:ACD5 가 $1C31 로 02:AD89 의 WRAM 주소 표를 골라 넘기고 02:ACE7 의 AND #$07 로 돈다.
세계마다 타일 벌: 01:A4A7(10바이트)을 JSL 로 바꿔 $1949 로 [주소][뱅크] 표를 고르고, 니블을 읽는 00:BBB4·BBBE·BBDA·BBE4 의
LDA $2AD712,X 를 세계마다 256바이트 표를 읽는 JSL 로 바꾼다.
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
# 세계 0 의 인물 팔레트: 01:A132 가 고른 시간대 색인이 0C 이상($075E 00F1~01FD)이면 01:A422, 아니면 01:A45E 를
# 01:A3F1 이 11·12번 줄 색 1~15 에 옮긴다(30색, 60바이트).
PERSON = {'day': 0x01A45E, 'night': 0x01A422}
# 움직이는 타일 벌: 2B:8000 이 7E:C800 에 풀고, 02:ACD5 가 $1C31 로 02:AD89 의 WRAM 주소 표를 골라 $1C13 에 둔다.
# 필드에서 7E:CE00~DFFF 는 타일을 올린 뒤 읽고 쓰는 코드가 없어(실측) 벌은 D400 까지, 16벌까지 늘린다.
ANIM_SET = FIELD_ANIM_COUNT * 32
ANIM_WRAM = 0xC800
ANIM_COUNTS = (1, 2, 4, 8, 16)
ANIM_TABLE = 0x02AD89
ANIM_SITES = {'table': (0x02ACD5, b'\xbf\x89\xad\x02'), 'table_hi': (0x02ACDC, b'\xbf\x8a\xad\x02'),
              'mask': (0x02ACE7, b'\x29\x07')}
# 세계마다 타일 벌. 01:A4A7 의 LDA #$12 / STA $4374 / PHA / PLB / LDX #$B1A8 을 JSL 과 BRA 로 바꾸고,
# 니블 읽기 넷(LDA $2AD712,X)을 JSL 로 바꾼다.
LOAD_SITE, LOAD_ORIG = 0x01A4A7, bytes.fromhex('a9128d744348aba2a8b1')
NIB_SITES = (0x00BBB4, 0x00BBBE, 0x00BBDA, 0x00BBE4)
NIB_ORIG = bytes.fromhex('bf12d72a')
WORLDS = ('world0', 'world1', 'world2')


def cpu(a):
    return f'{a >> 16:02X}:{a & 0xFFFF:04X}'


def check_sites(rom):
    sites = [(at, want, kind) for kind, ss in SITES.items() for at, want in ss]
    sites += [(at, want, 'anim') for at, want in ANIM_SITES.values()]
    sites += [(LOAD_SITE, LOAD_ORIG, 'tiles'), *((at, NIB_ORIG, 'tile_palettes') for at in NIB_SITES)]
    for at, want, kind in sites:
        if rom.d[lorom(at):lorom(at) + len(want)] != want:
            raise ValueError(f'{cpu(at)}: 원래 롬의 {kind} 코드가 아님; 원본 롬으로 만들어야 함')


def long_addr(a):
    return bytes([a & 0xFF, a >> 8 & 0xFF, a >> 16])


def load_hook(table):
    """01:A4A7 대신. $1949(세계, & 3)로 table 의 4바이트 [주소 16비트][뱅크][0] 을 골라 $4374·DB 를 뱅크로, X 를 주소로.
    원래 코드처럼 STA $4374 는 들어온 DB 로 쓴다. A 8비트, X 16비트, D = 0(01:A4A3 의 TDC 가 기대함).
    나갈 때 A 의 윗바이트는 원래처럼 0 으로 둔다."""
    return (b'\x7b' + b'\xaf\x49\x19\x7e' + b'\x29\x03' + b'\x0a\x0a' + b'\xaa'
            + b'\xbf' + long_addr(table + 2) + b'\x8d\x74\x43' + b'\x48'
            + b'\xc2\x20' + b'\xbf' + long_addr(table) + b'\xaa' + b'\x7b' + b'\xe2\x20' + b'\xab' + b'\x6b')


def nib_hook(tables):
    """LDA $2AD712,X 대신. X(16비트)와 A 의 윗바이트를 지키고 tables + 세계*256 + X 를 읽는다.
    00:BBC9 가 XBA 로 윗바이트를 타일맵 워드의 아랫바이트에 넣으므로 윗바이트가 바뀌면 타일 번호가 어긋난다.
    부른 곳은 바로 AND 로 플래그를 다시 정한다."""
    return (b'\xda' + b'\xeb' + b'\x48' + b'\xc2\x20' + b'\xaf\x49\x19\x7e' + b'\x29\x03\x00' + b'\xeb'
            + b'\x18' + b'\x63\x02' + b'\xaa' + b'\xe2\x20' + b'\x68' + b'\xeb'
            + b'\xbf' + long_addr(tables) + b'\xfa' + b'\x6b')


LOAD_LEN, NIB_LEN = len(load_hook(0)), len(nib_hook(0))


def worlds_layout(at):
    """--worlds-at 자리의 (불러오기 훅, 니블 훅, 고르기 표 16바이트, 니블 표 4 × 256바이트, 그 뒤 RLE)."""
    nib = at + LOAD_LEN
    table = nib + NIB_LEN
    tables = table + 16
    return at, nib, table, tables, tables + 0x400


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


def nibbles(rom, a):
    return [rom.u8(a + i // 2) >> (0 if i & 1 else 4) & 15 for i in range(TILES)]


def original(rom):
    check_sites(rom)
    planes, tiles_end = rle(rom, FIELD_CHR)
    anim, anim_end = rle(rom, ANIM)
    if len(planes) != 0x4000 or len(anim) != ANIM_BYTES:
        raise ValueError('원래 롬의 필드 타일·움직이는 타일 RLE 크기가 다름')
    if [rom.u16(ANIM_TABLE + k * 2) for k in range(FIELD_ANIM_SETS)] != \
            [ANIM_WRAM + k * ANIM_SET for k in range(FIELD_ANIM_SETS)]:
        raise ValueError(f'{cpu(ANIM_TABLE)}: 원래 롬의 움직이는 타일 벌 표가 아님')
    return {'tiles': planar_to_tiles(planes), 'anim': anim,
            'rle': {'tiles': rom.d[lorom(FIELD_CHR):lorom(tiles_end)], 'anim': rom.d[lorom(ANIM):lorom(anim_end)]},
            'tile_palettes': nibbles(rom, TILE_PALETTE),
            'palettes': {k: [colors(rom, a, 30) for a in v] for k, v in PALETTE_SETS.items()},
            'wave': [colors(rom, WAVE + i * 6, 3) for i in range(WAVE_STEPS)],
            'person_palettes': {k: colors(rom, a, 30) for k, a in PERSON.items()}}


def current(rom):
    """패치한 롬에서 지금 읽히는 것. 검사 도구가 쓴다. worlds 는 세계마다 (타일, 니블),
    anim_sets 는 $1C31 이 0 부터 도는 차례대로 DMA 로 올리는 192바이트."""
    out = {}
    if rom.d[lorom(LOAD_SITE)] == 0x22:
        _, _, table, tables, _ = worlds_layout(rom.u24(LOAD_SITE + 1))
        srcs = [rom.u8(table + w * 4 + 2) << 16 | rom.u16(table + w * 4) for w in range(3)]
        nibs = [nibbles(rom, tables + w * 0x100) for w in range(3)]
    else:
        (bank_site, _), (addr_site, _) = SITES['tiles']
        srcs = [rom.u8(bank_site) << 16 | rom.u16(addr_site)] * 3
        nibs = [nibbles(rom, TILE_PALETTE)] * 3
    out['worlds'] = {k: (planar_to_tiles(rle(rom, srcs[w])[0]), nibs[w]) for w, k in enumerate(WORLDS)}
    out['tiles'], out['tile_palettes'] = out['worlds']['world0']
    (bank_site, _), (addr_site, _) = SITES['anim']
    out['anim'] = rle(rom, rom.u8(bank_site) << 16 | rom.u16(addr_site))[0]
    table_site, _ = ANIM_SITES['table']
    mask_site, _ = ANIM_SITES['mask']
    table = rom.u24(table_site + 1)
    out['anim_sets'] = []
    for k in range(rom.u8(mask_site + 1) + 1):
        o = rom.u16(table + k * 2) - ANIM_WRAM
        out['anim_sets'].append(out['anim'][o:o + ANIM_SET])
    out['palettes'] = {k: [colors(rom, a, 30) for a in v] for k, v in PALETTE_SETS.items()}
    out['wave'] = [colors(rom, WAVE + i * 6, 3) for i in range(WAVE_STEPS)]
    out['person_palettes'] = {k: colors(rom, a, 30) for k, a in PERSON.items()}
    return out


def dump(rom, out):
    o = original(rom)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, 'tiles.bin'), 'wb') as f:
        f.write(o['tiles'])
    with open(os.path.join(out, 'anim.bin'), 'wb') as f:
        f.write(o['anim'])
    doc = {'format': FORMAT, 'tiles_file': 'tiles.bin', 'anim_file': 'anim.bin',
           'tile_palettes': o['tile_palettes'], 'palettes': o['palettes'], 'wave': o['wave'],
           'person_palettes': o['person_palettes']}
    with open(os.path.join(out, 'fieldgfx.json'), 'w', encoding='utf-8') as f:
        json.dump(doc, f, separators=(',', ':'))
        f.write('\n')
    return doc


def color_list(v, n, name):
    if not isinstance(v, list) or len(v) != n or any(type(c) is not int or not 0 <= c <= 0x7FFF for c in v):
        raise ValueError(f'{name}: 15비트 색 {n}개')
    return v


def read_file(folder, name, key):
    if not isinstance(name, str):
        raise ValueError(f'{key} 는 파일 이름 문자열')
    with open(os.path.join(folder, name), 'rb') as f:
        return f.read()


def nibble_list(v, name):
    if not isinstance(v, list) or len(v) != TILES or any(type(c) is not int or not 0 <= c <= 15 for c in v):
        raise ValueError(f'{name} 는 0~15 {TILES}개')
    return v


def warn_anim_slots(tiles, orig, name):
    changed = [t for t in ANIM_SLOTS if tiles[t * 32:t * 32 + 32] != orig[t * 32:t * 32 + 32]]
    if changed:
        print(f'경고: {name} 타일 {changed} 은 움직이는 타일 벌이 늘 덮어 보이지 않음(anim.bin 을 고칠 것)',
              file=sys.stderr)


def place_in(at, size, option, placed):
    bank, low = at >> 16, at & 0xFFFF
    if not 0x30 <= bank <= 0x3F or low < 0x8000 or low + size > 0x10000:
        raise ValueError(f'{option} 은 30~3F 의 한 뱅크 안({size}바이트)')
    if any(at < e and lo < at + size for lo, e, _ in placed):
        raise ValueError(f'{option} 자리가 {[n for lo, e, n in placed if at < e and lo < at + size]} 와 겹침')
    placed.append((at, at + size, option))


def patch(rom, doc, folder, tiles_at=None, anim_at=None, name='field-gfx', worlds_at=None):
    o = original(rom)
    keys = {'format', 'tiles_file', 'anim_file', 'tile_palettes', 'palettes', 'wave', 'person_palettes', 'worlds'}
    if not isinstance(doc, dict) or doc.get('format') != FORMAT or set(doc) - keys:
        raise ValueError(f'format={FORMAT} 와 {sorted(keys - {"format"})} 만')
    data = {'tiles': read_file(folder, doc.get('tiles_file'), 'tiles_file'),
            'anim': read_file(folder, doc.get('anim_file'), 'anim_file')}
    if len(data['tiles']) != TILES * 32:
        raise ValueError(f'{doc["tiles_file"]}: {TILES * 32}바이트여야 함(타일 수는 늘리지 않음)')
    sets, rest = divmod(len(data['anim']), ANIM_SET)
    if rest or sets not in ANIM_COUNTS:
        raise ValueError(f'{doc["anim_file"]}: {ANIM_SET}바이트 벌 {ANIM_COUNTS} 개여야 함({len(data["anim"])}바이트)')
    if sets != FIELD_ANIM_SETS and anim_at is None:
        raise ValueError(f'움직이는 타일 벌 수를 {sets} 로 바꾸려면 --anim-at 이 필요함(벌 주소 표를 그 뒤에 둠)')
    nib = nibble_list(doc.get('tile_palettes'), 'tile_palettes')
    pals = doc.get('palettes')
    if not isinstance(pals, dict) or set(pals) != set(PALETTE_SETS) or \
            any(not isinstance(pals[k], list) or len(pals[k]) != len(PALETTE_SETS[k]) for k in PALETTE_SETS):
        raise ValueError(f'palettes 는 {sorted(PALETTE_SETS)} 마다 원래 벌 수')
    wave = doc.get('wave')
    if not isinstance(wave, list) or len(wave) != WAVE_STEPS:
        raise ValueError(f'wave 는 {WAVE_STEPS}단계')
    person = doc.get('person_palettes', o['person_palettes'])
    if not isinstance(person, dict) or set(person) != set(PERSON):
        raise ValueError(f'person_palettes 는 {sorted(PERSON)} 의 30색씩')
    worlds = doc.get('worlds', {})
    if not isinstance(worlds, dict) or set(worlds) - {'world1', 'world2'} or \
            any(not isinstance(v, dict) or set(v) != {'tiles_file', 'tile_palettes'} for v in worlds.values()):
        raise ValueError('worlds 는 world1·world2 마다 {tiles_file, tile_palettes}')
    if worlds and worlds_at is None:
        raise ValueError('worlds(세계마다 타일 벌)에는 --worlds-at 이 필요함')
    if worlds_at is not None and not worlds:
        raise ValueError('--worlds-at 은 worlds 와 함께만')
    world_data = {}
    for key, v in sorted(worlds.items()):
        tiles = read_file(folder, v['tiles_file'], f'worlds.{key}.tiles_file')
        if len(tiles) != TILES * 32:
            raise ValueError(f'{v["tiles_file"]}: {TILES * 32}바이트여야 함')
        warn_anim_slots(tiles, o['tiles'], key)
        world_data[key] = (tiles, nibble_list(v['tile_palettes'], f'worlds.{key}.tile_palettes'))
    warn_anim_slots(data['tiles'], o['tiles'], 'world0')
    writes = []

    def write(addr, raw, note, orig=True):
        w = {'at': cpu(addr), 'hex': raw.hex(' '), 'note': note}
        if orig:
            off = lorom(addr)
            w['orig'] = rom.d[off:off + len(raw)].hex(' ')
        writes.append(w)

    placed = []
    world0_at = FIELD_CHR
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
        table = encode_anim_table(sets) if kind == 'anim' and sets != FIELD_ANIM_SETS else b''
        place_in(at, len(packed) + len(table), f'--{kind}-at', placed)
        write(at, packed, f'{kind} RLE', orig=False)
        if kind == 'tiles':
            world0_at = at
        if kind == 'tiles' and worlds:
            continue                                  # 즉값 자리는 세계 훅이 덮는다
        (bank_site, _), (addr_site, _) = SITES[kind]
        write(bank_site, bytes([at >> 16]), f'{kind} 뱅크')
        write(addr_site, (at & 0xFFFF).to_bytes(2, 'little'), f'{kind} 주소')
        if table:
            t = at + len(packed)
            write(t, table, f'움직이는 타일 벌 {sets}개의 WRAM 주소 표', orig=False)
            write(ANIM_SITES['table'][0] + 1, long_addr(t), '벌 주소 표(하위 바이트)')
            write(ANIM_SITES['table_hi'][0] + 1, long_addr(t + 1), '벌 주소 표(상위 바이트)')
            write(ANIM_SITES['mask'][0] + 1, bytes([sets - 1]), f'벌 돌리기 AND #${sets - 1:02X}')
    nib_bytes = bytes(nib[i] << 4 | nib[i + 1] for i in range(0, TILES, 2))
    old = rom.d[lorom(TILE_PALETTE):lorom(TILE_PALETTE) + len(nib_bytes)]
    for i in range(len(nib_bytes)):
        if nib_bytes[i] != old[i]:
            write(TILE_PALETTE + i, bytes([nib_bytes[i]]), f'타일 팔레트 니블 {i * 2:03X}')
    if worlds:
        write_worlds(worlds_at, world0_at, data['tiles'], nib, world_data, placed, write)
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
    for key, a in PERSON.items():
        new = color_list(person[key], 30, f'person_palettes.{key}')
        if new != o['person_palettes'][key]:
            write(a, b''.join(c.to_bytes(2, 'little') for c in new), f'세계 0 {key} 인물 팔레트(11·12번 줄)')
    manifest = {'format': 'dq5patch/1', 'name': name, 'writes': writes}
    if placed:
        manifest['rom_size'] = 2
    return manifest


def encode_anim_table(sets):
    return b''.join((ANIM_WRAM + k * ANIM_SET).to_bytes(2, 'little') for k in range(sets))


def write_worlds(at, world0_at, tiles0, nib0, world_data, placed, write):
    """세계 훅 둘·고르기 표·니블 표 넷(넷째는 세계 0 과 같게)·세계 1·2 RLE 를 at 에 차례로 둔다.
    세계 0 과 같은 타일이면 RLE 를 따로 두지 않고 세계 0 의 것을 가리킨다."""
    load, nib, table, tables, rles = worlds_layout(at)
    srcs, nibs, blob = [world0_at], [nib0], bytearray()
    for key in WORLDS[1:]:
        tiles, n = world_data.get(key, (tiles0, nib0))
        nibs.append(n)
        if tiles == tiles0:
            srcs.append(world0_at)
            continue
        srcs.append(rles + len(blob))
        blob += encode_rle(tiles_to_planar(tiles))
    srcs.append(world0_at)
    nibs.append(nib0)
    code = load_hook(table) + nib_hook(tables)
    body = code + b''.join(long_addr(a) + b'\x00' for a in srcs) + \
        b''.join(bytes(n[i] << 4 | n[i + 1] for i in range(0, TILES, 2)) for n in nibs) + bytes(blob)
    place_in(at, len(body), '--worlds-at', placed)
    write(at, body, '세계마다 타일 벌: 불러오기 훅·니블 훅·고르기 표·니블 표 넷·세계 1·2 RLE', orig=False)
    write(LOAD_SITE, b'\x22' + long_addr(load) + b'\x80\x04' + b'\xea' * 4, '타일 불러오기를 세계 훅으로')
    for site in NIB_SITES:
        write(site, b'\x22' + long_addr(nib), '타일 팔레트 니블 읽기를 세계 훅으로')


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
    ap.add_argument('--worlds-at')
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
                         parse_at(a.tiles_at, '--tiles-at'), parse_at(a.anim_at, '--anim-at'), a.name,
                         parse_at(a.worlds_at, '--worlds-at'))
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
