"""DQ5 보물상자·조사 보상 표 여섯을 통째로 다시 쓰고, 필요하면 늘려서 다른 자리로 옮긴다.

sfc/dq5/docs/dq5-build-format.md 의 「보물상자·조사 보상 표 옮기기」. 표 크기가 지금 자리에 맞으면 그 자리에 쓰고
코드는 고치지 않는다. 옮기면 표를 읽는 명령의 즉값만 고친다.

  chests(1E:EE4E)     12:E6AC 의 LDA long 하나. 뱅크 00~7D 어디든.
  ahead(1E:F435)      12:FCE5·FCF4·FCFE·FD1D 의 LDA long. 뱅크 00~7D 어디든.
  search(1F:F5CB)     12:FB9D 가 DB 를 12:FBA2 의 즉값으로 두고 abs 8곳(+0·+2·+3)으로 읽는다. 같은 DB 로 WRAM($1E71 등)을
                      abs 로 쓰므로 뱅크 00~3F.
  foot(1E:F08B)       12:E6D7 이 DB 를 12:E6E1 의 즉값으로 두고 abs 8곳으로 읽는다. 뱅크 00~3F(같은 까닭).
  chest_maps(1E:EF90) 1F:FD18·1F:FDD0·25:FAB0 이 DB 를 즉값 셋(1F:FD1B·FDD8·25:FAB5)으로 두고 abs 6곳으로 읽는다.
  lower(1E:F4DF)      12:FD46 의 LDA long 4곳과, 맵에 들어갈 때 1F:FC7B 가 DB 를 1F:FC7E 의 즉값으로 두고 abs 3곳.
                      이 둘은 DB 를 둔 채 2A:FBCD·25:FA15·01:EFE7·00:95DA 등을 부르지만, 그동안 DB 로 닿는 곳은 표 읽기와
                      WRAM($1E71 등)뿐이라(lua/dq5dbread.lua 의 DB 창 감사) 서랍·발밑과 같이 뱅크 00~3F.
일반 상자 수(chest_maps 의 count 합)는 256 까지. 상자 번호 n 은 8비트 덧셈(25:FAB0·1F:FDD0)으로 나오고, 열림 비트는
7E:2210 + n/8(12:E680·1F:FE02 읽기, 12:E697 이 2190 기준 번호 (n/8 | 80) 으로 켬)이라 2210~222F 를 쓴다. 상자가 193개를
넘으면 원래 아래층 상자(2228~2229)·서랍(222C~)의 비트와 겹치므로, 그 항목들의 flag_index 를 빈 비트로 옮겨야 한다.
다섯 표의 열림 비트는 모두 7E:2210~224F 안이어야 하고 서로 겹치면 거부한다. 표 밖의 코드가 직접 보는 비트(RESERVED)는
원래 주인 항목만 쓴다. 발밑·두 칸 앞·아래층 상자는 8비트 색인으로 읽어 행 수 한도(ROW_LIMIT)가 있다.
게임에서는 상자 192·193·256 을 확인했고, 194~255번은 코드 읽기(12:E691·1F:FDD0·25:FAB0)로만 정했다.

  python sfc/dq5/tools/dq5chestreloc.py rom/dq5.sfc dump -o work/chest-tables.json
  python sfc/dq5/tools/dq5chestreloc.py rom/dq5.sfc patch work/chest-tables.json -o work/chest-tables.dq5patch.json \\
      [--chests-at BB:AAAA] [--chest-maps-at …] [--search-at …] [--foot-at …] [--ahead-at …] [--lower-at …]
  python sfc/dq5/tools/dq5chestreloc.py rom/dq5.sfc check [work/chest-tables.json] [같은 자리 선택]
"""
import argparse
import json
import re
import sys
from pathlib import Path

from dq5build import BANK, ORIGINAL_SIZE, build, free_ranges, parse_at
from dq5chest import AHEAD_TABLE, CHEST_ITEMS, CHEST_MAPS, FOOT_TABLE, LOWER_TABLE, SEARCH_TABLE, chests
from dq5chestwrite import decode, encode, integer, map_dimensions
from dq5gfx import map_ids
from dq5map import Rom, lorom

FORMAT = 'dq5chesttables/1'
ORIGINAL = {'chests': CHEST_ITEMS, 'chest_maps': CHEST_MAPS, 'search': SEARCH_TABLE, 'foot': FOOT_TABLE,
            'ahead': AHEAD_TABLE, 'lower': LOWER_TABLE}
ENTRY = {'chests': 2, 'chest_maps': 3, 'search': 9, 'foot': 9, 'ahead': 8, 'lower': 8}
# 명령 자리(옵코드 주소). LONG 은 3바이트 즉값, ABS 는 (자리, 표 시작에서 더한 값)
LONG = {'chests': (0x12E6AC,), 'ahead': (0x12FCE5, 0x12FCF4, 0x12FCFE, 0x12FD1D),
        'lower': (0x12FD4B, 0x12FD5A, 0x12FD65, 0x12FD71)}
ABS = {'chest_maps': ((0x1FFD23, 0), (0x1FFD38, 0), (0x1FFDE2, 0), (0x1FFDEC, 0), (0x25FAC3, 0), (0x25FAD2, 0)),
       'search': ((0x12FBAA, 0), (0x12FBC6, 0), (0x12FBD8, 2), (0x12FBDF, 3), (0x12FBF2, 0), (0x12FC1F, 2),
                  (0x12FC2A, 3), (0x12FC2D, 0)),
       'foot': ((0x12E6E8, 0), (0x12E700, 0), (0x12E719, 0), (0x12E726, 2), (0x12E72B, 3), (0x12E73C, 0),
                (0x12E742, 2), (0x12E74F, 3)),
       'lower': ((0x1FFC83, 0), (0x1FFC91, 0), (0x1FFC9A, 0))}
# 표 뱅크를 DB 로 두는 즉값 자리. 같은 표의 자리끼리 값이 같아야 한다
DB_SITES = {'search': (0x12FBA2,), 'foot': (0x12E6E1,), 'chest_maps': (0x1FFD1B, 0x1FFDD8, 0x25FAB5),
            'lower': (0x1FFC7E,)}
MAX_CHESTS = 256
# 표마다 (열림 비트의 WRAM 주소 = 기준 + flag_index, flag_index 한도). 두 칸 앞은 12:FD7A 가 2190 + (번호 | 80) 으로,
# 아래층 상자는 같은 식과 1F:FCB5 의 2210 + 번호 둘로 읽으므로 7F 이하만 받는다
FLAG_BASE = {'search': (0x222C, 0xFF), 'foot': (0x2240, 0xFF), 'ahead': (0x2210, 0x7F), 'lower': (0x2210, 0x7F)}
FLAG_AREA = (0x2210, 0x2250)
# 표 밖의 코드가 직접 보는 열림 비트: (주소, 비트) → (보는 곳, 그 비트를 원래 쓰는 두 칸 앞 항목의 (BC, BD, X, Y) 또는 None).
# 주인 항목만 그 비트를 쓸 수 있고, 주인 항목의 flag_index·mask 는 바꿀 수 없다. 2238 은 어느 비트를 보는지 몰라 바이트 전체
RESERVED = {**{(0x2238, bit): ('21:8C2F(전투 0C 에서 읽음)', None) for bit in (1, 2, 4, 8, 16, 32, 64, 128)},
            (0x223C, 0x80): ('06:D3CB', (0x10, 0x02, 29, 9)), (0x223D, 0x08): ('12:AE9C', (0x03, 0x04, 10, 7)),
            (0x223D, 0x20): ('12:ADB0', (0x03, 0x0B, 13, 16)), (0x223D, 0x80): ('12:AEA9', (0x15, 0x0A, 28, 35)),
            (0x223E, 0x01): ('12:AEB4', (0x15, 0x0A, 30, 35))}
# 8비트 색인으로 읽는 표의 행 수 한도. 마지막 종료자 낱말을 색인 FE 이하에서 읽어야 한다(행 수 × 크기 ≤ FE)
ROW_LIMIT = {'foot': (28, '12:E6E6'), 'ahead': (31, '12:FCE3'), 'lower': (31, '12:FD48·1F:FC81')}
# 종료자를 못 찾은 표를 끝없이 읽지 않게 두는 한도. 서랍 표 86 이 원래 가장 길다
MAX_ROWS = 255
ORIGINAL_BYTES = {'chests': 161 * 2, 'chest_maps': 83 * 3 + 2, 'search': 86 * 9 + 2, 'foot': 18 * 9 + 2,
                  'ahead': 17 * 8 + 2, 'lower': 11 * 8 + 2}
ROW_FIELDS = {'chests': ('reward',), 'chest_maps': ('group', 'map', 'count'),
              'search': ('group', 'map', 'x', 'y', 'unused', 'reward', 'flag_index', 'mask'),
              'foot': ('group', 'map', 'x', 'y', 'layer', 'reward', 'flag_index', 'mask'),
              'ahead': ('group', 'map', 'x', 'y', 'reward', 'flag_index', 'mask'),
              'lower': ('group', 'map', 'x', 'y', 'reward', 'flag_index', 'mask')}


def cpu(addr):
    return f'{addr >> 16:02X}:{addr & 0xFFFF:04X}'


def read(rom, addr, size):
    raw = bytes(rom.d[lorom(addr):lorom(addr) + size])
    if len(raw) != size:
        raise ValueError(f'{cpu(addr)}: 롬 범위 밖')
    return raw


def locate(rom):
    """코드가 가리키는 표 여섯의 CPU 주소. 같은 표를 읽는 자리끼리 값이 다르면 거부한다."""
    out = {}
    for name in ORIGINAL:
        found = {int.from_bytes(read(rom, site + 1, 3), 'little') for site in LONG.get(name, ())}
        if name in ABS:
            banks = {read(rom, site, 1)[0] for site in DB_SITES[name]}
            if len(banks) != 1:
                raise ValueError(f'{name}: DB 즉값 자리끼리 뱅크가 다름 {[f"{b:02X}" for b in sorted(banks)]}')
            bank = banks.pop()
            found |= {bank << 16 | (int.from_bytes(read(rom, site + 1, 2), 'little') - plus) & 0xFFFF
                      for site, plus in ABS[name]}
        if len(found) != 1:
            raise ValueError(f'{name}: 표를 읽는 명령들이 가리키는 자리가 다름 {[cpu(a) for a in sorted(found)]}')
        out[name] = found.pop()
    return out


def row_decode(name, raw):
    if name == 'chests':
        return {'reward': int.from_bytes(raw, 'little')}
    if name == 'chest_maps':
        return dict(zip(ROW_FIELDS[name], raw))
    value = decode(name, raw)
    if name == 'search':
        value['unused'] = raw[4]
    return {key: value[key] for key in ROW_FIELDS[name]}


def parse(rom, loc=None):
    loc = loc or locate(rom)
    doc = {'format': FORMAT}
    for name in ('chest_maps', 'search', 'foot', 'ahead', 'lower'):
        rows, a = [], loc[name]
        while read(rom, a, 2) != b'\xff\xff':
            rows.append(row_decode(name, read(rom, a, ENTRY[name])))
            a += ENTRY[name]
            if len(rows) > MAX_ROWS:
                raise ValueError(f'{name}: 종료자 FFFF 가 없음')
        doc[name] = rows
    total = sum(row['count'] for row in doc['chest_maps'])
    doc['chests'] = [row_decode('chests', read(rom, loc['chests'] + i * 2, 2)) for i in range(total)]
    return {key: doc[key] for key in ('format', *ORIGINAL)}


def row_encode(name, row, label):
    if not isinstance(row, dict) or set(row) != set(ROW_FIELDS[name]):
        raise ValueError(f'{label}: 필드 {list(ROW_FIELDS[name])}를 모두 적은 객체여야 함')
    if name == 'chests':
        return encode(name, bytes(2), row)
    if name == 'chest_maps':
        for key in ROW_FIELDS[name]:
            integer(row[key], 255, f'{label}.{key}')
        if row['count'] == 0:
            raise ValueError(f'{label}: count 는 1 이상이어야 함')
        return bytes(row[key] for key in ROW_FIELDS[name])
    changes = {k: v for k, v in row.items() if k != 'unused'}
    out = bytearray(encode(name, bytes(ENTRY[name]), changes))
    if name == 'search':
        out[4] = integer(row['unused'], 255, f'{label}.unused')
    return bytes(out)


def serialize(rom, doc):
    """문서 → 표 이름별 바이트. 표에 든 맵·좌표·상자 수를 검사한다."""
    if not isinstance(doc, dict) or set(doc) != {'format', *ORIGINAL} or doc['format'] != FORMAT:
        raise ValueError(f'format={FORMAT} 과 표 여섯 {list(ORIGINAL)}을 모두 적어야 함')
    available = set(map_ids(rom))
    blobs, dimensions = {}, {}
    for name in ORIGINAL:
        rows, limit = doc[name], MAX_CHESTS if name == 'chests' else MAX_ROWS
        if not isinstance(rows, list) or len(rows) > limit:
            raise ValueError(f'{name}: {limit}개까지의 배열이어야 함')
        if name in ROW_LIMIT and len(rows) > ROW_LIMIT[name][0]:
            raise ValueError(f'{name}: {ROW_LIMIT[name][1]} 가 8비트 색인으로 읽으므로 {ROW_LIMIT[name][0]}행까지')
        seen, raws = set(), []
        for i, row in enumerate(rows):
            raws.append(row_encode(name, row, f'{name}[{i}]'))
            if name == 'chests':
                continue
            key = (row['group'], row['map'])
            if key not in available:
                raise ValueError(f'{name}[{i}]: 존재하지 않는 맵')
            if name == 'chest_maps' and row['group'] >= 0x50:
                raise ValueError(f'{name}[{i}]: 일반 실내 맵 그룹 00~35만 지원함')
            if name != 'chest_maps':
                if key not in dimensions:
                    dimensions[key] = map_dimensions(rom, *key)
                width, height = dimensions[key]
                if row['x'] >= width or row['y'] >= height:
                    raise ValueError(f'{name}[{i}]: 좌표가 맵 {width}×{height} 밖')
                key += (row['x'], row['y']) + ((row['layer'],) if name == 'foot' else ())
            if key in seen:
                raise ValueError(f'{name}[{i}]: 먼저 나오는 항목에 가려지는 중복 {key}')
            seen.add(key)
        blobs[name] = b''.join(raws) + (b'' if name == 'chests' else b'\xff\xff')
    total = sum(row['count'] for row in doc['chest_maps'])
    if total > MAX_CHESTS or len(doc['chests']) != total:
        raise ValueError(f'chests: 상자 수는 chest_maps 의 count 합({total})과 같고 {MAX_CHESTS} 이하여야 함')
    flag_bits(doc)
    return blobs


def flag_bits(doc):
    """다섯 표의 열림 비트 → {(WRAM 주소, 비트): 항목 이름}. 두 항목이 한 비트를 나눠 쓰면 하나를 열 때 다른 것도 열린다."""
    owner = {}
    keep = {place: bit for bit, (_, place) in RESERVED.items() if place}

    def claim(addr, mask, label, place=None):
        if not FLAG_AREA[0] <= addr < FLAG_AREA[1]:
            raise ValueError(f'{label}: 열림 비트 7E:{addr:04X} 가 상자 비트 자리 7E:2210~224F 밖')
        for bit in (0x80, 0x40, 0x20, 0x10, 0x08, 0x04, 0x02, 0x01):
            if mask & bit:
                if (addr, bit) in owner:
                    raise ValueError(f'{label}: 열림 비트 7E:{addr:04X} & {bit:02X} 를 {owner[addr, bit]} 가 이미 씀')
                if (addr, bit) in RESERVED and keep.get(place) != (addr, bit):
                    raise ValueError(f'{label}: 열림 비트 7E:{addr:04X} & {bit:02X} 는 {RESERVED[addr, bit][0]} 가 '
                                     '직접 보는 비트라 쓸 수 없음')
                owner[addr, bit] = label
    for n in range(len(doc['chests'])):
        claim(0x2210 + (n >> 3), 0x80 >> (n & 7), f'일반 상자 {n}')
    for name, (base, limit) in FLAG_BASE.items():
        for i, row in enumerate(doc[name]):
            if row['flag_index'] > limit:
                raise ValueError(f'{name}[{i}]: flag_index 는 {limit:02X} 이하여야 함')
            place = (row['group'], row['map'], row['x'], row['y']) if name == 'ahead' else None
            if place in keep and (base + row['flag_index'], row['mask']) != keep[place]:
                addr, bit = keep[place]
                raise ValueError(f'{name}[{i}]: 이 자리의 열림 비트 7E:{addr:04X} & {bit:02X} 는 '
                                 f'{RESERVED[addr, bit][0]} 가 직접 보므로 바꿀 수 없음')
            claim(base + row['flag_index'], row['mask'], f'{name}[{i}]', place)
    return owner


def check_cells(rom, doc):
    start = 0
    for i, row in enumerate(doc['chest_maps']):
        cells = chests(rom, row['group'], row['map'], start)
        if len(cells) != row['count']:
            raise ValueError(f'chest_maps[{i}]: 맵 상자 셀 {len(cells)}개와 count 가 다름')
        start += row['count']


def original_spans():
    """원래 롬에서 표 여섯이 차지한 자리(종료자 포함). 옮기면 비므로 다른 표를 넣어도 된다.
    이미 옮긴 롬에서는 원래 자리를 다시 읽을 수 없으므로 크기를 적어 두고, check 가 원본과 맞는지 본다."""
    return {name: (ORIGINAL[name], ORIGINAL[name] + ORIGINAL_BYTES[name]) for name in ORIGINAL}


def allowed(original):
    free = []
    for off, size in free_ranges(original):
        start = (off // BANK) << 16 | 0x8000 | off % BANK
        free.append((start, start + size))
    out = [*original_spans().values(), *free]
    out += [(bank << 16 | 0x8000, bank + 1 << 16) for bank in range(ORIGINAL_SIZE // BANK, 0x7E)]
    return merge(out)


def merge(spans):
    # 1E:EE4E~F12F 의 상자 내용물·맵 연결·발밑 표처럼 붙어 있는 자리는 하나로 본다. 겹침은 placement 가 따로 본다
    out = []
    for lo, hi in sorted(spans):
        if out and lo <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], hi))
        else:
            out.append((lo, hi))
    return out


def placement(rom, sizes, at, extra):
    """at: 표 이름 → CPU 주소(없으면 지금 자리). 지금 자리는 extra 로 허용한다."""
    current = locate(rom)
    at = {name: at.get(name) or current[name] for name in ORIGINAL}
    spans = {}
    for name, size in sizes.items():
        start, bank = at[name], at[name] >> 16
        if not 0x8000 <= start & 0xFFFF or start + size > (bank + 1) << 16:
            raise ValueError(f'{name}: {cpu(start)} 에서 {size}바이트가 한 뱅크(8000~FFFF)에 들어가지 않음')
        if name in DB_SITES and bank > 0x3F:
            raise ValueError(f'{name}: 뱅크 00~3F 만 됨(같은 DB 로 WRAM 을 abs 로 씀)')
        if bank > 0x7D:
            raise ValueError(f'{name}: 뱅크 00~7D 로 적어야 함')
        if not any(lo <= start and start + size <= hi for lo, hi in [*allowed(rom.d), *extra.get(name, ())]):
            raise ValueError(f'{name}: {cpu(start)}~ {size}바이트가 원래 표 자리·빈 자리·늘린 뱅크 어느 한 곳에도 들지 않음')
        spans[name] = (start, start + size)
    order = sorted(spans.items(), key=lambda kv: kv[1])
    for (a, (_, end)), (b, (start, _)) in zip(order, order[1:]):
        if start < end:
            raise ValueError(f'{a} 와 {b} 의 자리가 겹침')
    return at


def rom_size(addresses):
    top = max(a >> 16 for a in addresses)
    return 0 if top < 0x30 else 2 if top < 0x40 else 3 if top < 0x60 else 4


def writes_for(rom, doc, at=None):
    """문서와 자리 → [(CPU 주소, 새 바이트, 원래 바이트 또는 None, 설명)] 과 롬 크기(MB)."""
    # orig 는 원래 롬 바이트여야 빌더가 붙일 수 있으므로, 이미 옮긴 롬에는 쓰지 않는다
    if locate(rom) != ORIGINAL:
        raise ValueError('표를 옮긴 롬에는 패치를 만들지 않음. 원래 롬에서 만든다')
    blobs = serialize(rom, doc)
    check_cells(rom, doc)
    at = placement(rom, {name: len(blob) for name, blob in blobs.items()}, at or {}, {})
    data = [(at[name], blobs[name], f'{name} 표') for name in ORIGINAL]
    code = []
    for name in ORIGINAL:
        code += [(site + 1, at[name].to_bytes(3, 'little'), f'{name} 표 자리(long)') for site in LONG.get(name, ())]
        code += [(site + 1, ((at[name] + plus) & 0xFFFF).to_bytes(2, 'little'), f'{name} 표 자리(abs)')
                 for site, plus in ABS.get(name, ())]
        code += [(site, bytes([at[name] >> 16]), f'{name} 표 뱅크(DB)') for site in DB_SITES.get(name, ())]
    out = []
    for addr, new, note in data + code:
        old = bytes(rom.d[lorom(addr):lorom(addr) + len(new)]) if lorom(addr) + len(new) <= len(rom.d) else None
        if new != old:
            out.append((addr, new, old if lorom(addr) < ORIGINAL_SIZE else None, note))
    if out:
        # 원래 표 자리 중 새 표가 들지 않은 곳도 같은 바이트로 써서 이 도구가 맡는다. 고정 표 쓰기(dq5chestwrite.py)를
        # 한 빌드에 함께 넣으면 빌더가 겹침으로 거부한다. 같이 넣으면 그 편집이 옮겨 간 표에 닿지 않기 때문이다.
        gaps = []
        for lo, hi in original_spans().values():
            taken = sorted((max(a, lo), min(a + len(n), hi)) for a, n, _, _ in out if a < hi and a + len(n) > lo)
            cursor = lo
            for first, last in taken + [(hi, hi)]:
                if first > cursor:
                    old = read(rom, cursor, first - cursor)
                    gaps.append((cursor, old, old, '원래 표 자리 맡음(바이트 그대로)'))
                cursor = max(cursor, last)
        out += gaps
        out.sort()
    return out, rom_size([a for a, _, _, _ in out] or [0])


def patch(rom, doc, at=None):
    writes, mb = writes_for(rom, doc, at)
    result = {'format': 'dq5patch/1', 'name': 'chest-tables', 'writes': [
        {'at': cpu(addr), 'hex': new.hex(' '), **({'orig': old.hex(' ')} if old is not None else {}), 'note': note}
        for addr, new, old, note in writes]}
    if mb:
        result['rom_size'] = mb
    return result


def check(rom, doc=None, at=None):
    if locate(rom) != ORIGINAL:
        raise ValueError('check 는 원래 롬에서 돌린다')
    original = parse(rom)
    if {name: len(blob) for name, blob in serialize(rom, original).items()} != ORIGINAL_BYTES:
        raise ValueError('원래 표 크기가 적어 둔 값과 다름')
    if patch(rom, original)['writes']:
        raise ValueError('원본을 다시 직렬화한 결과가 원래 바이트와 다름')
    source = original if doc is None else doc
    manifest = patch(rom, source, at)
    writes = [(lorom(int(w['at'][:2], 16) << 16 | int(w['at'][3:], 16)), bytes.fromhex(w['hex']),
               bytes.fromhex(w['orig']) if 'orig' in w else None, w['note']) for w in manifest['writes']]
    built, _ = build(rom.d, [('chest-tables', manifest.get('rom_size', 0), writes)], manifest.get('rom_size', 0))
    moved = Rom(built)
    loc = locate(moved)
    if parse(moved, loc) != json.loads(json.dumps(source)):
        raise ValueError('만든 롬을 코드가 가리키는 자리에서 다시 읽은 결과가 입력과 다름')
    check_cells(moved, source)
    if any(read(moved, loc[name], len(blob)) != blob for name, blob in serialize(moved, source).items()):
        raise ValueError('만든 롬의 표 바이트가 입력을 다시 직렬화한 것과 다름')
    counts = ', '.join(f'{name} {len(source[name])}' for name in ORIGINAL)
    print(f'{counts}; 표 자리 {", ".join(f"{k} {cpu(v)}" for k, v in loc.items())}; '
          f'쓰기 {len(writes)}개, 롬 {manifest.get("rom_size") or 1.5}MB 검사 통과')


def address(text):
    if not re.fullmatch(r'[0-9A-Fa-f]{2}:[0-9A-Fa-f]{4}', text):
        raise argparse.ArgumentTypeError('BB:AAAA 로 적어야 함')
    try:
        off, _ = parse_at(text)
    except Exception as error:
        raise argparse.ArgumentTypeError(str(error)) from error
    return (off // BANK) << 16 | 0x8000 | off % BANK


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('rom', type=Path)
    sub = parser.add_subparsers(dest='command', required=True)
    export = sub.add_parser('dump')
    export.add_argument('-o', '--out', type=Path, required=True)
    write = sub.add_parser('patch')
    write.add_argument('source', type=Path)
    write.add_argument('-o', '--out', type=Path, required=True)
    verify = sub.add_parser('check')
    verify.add_argument('source', type=Path, nargs='?')
    for p in (write, verify):
        for name in ORIGINAL:
            p.add_argument(f'--{name.replace("_", "-")}-at', dest=f'{name}_at', type=address,
                           help=f'기본 지금 자리(원래 {cpu(ORIGINAL[name])})')
    args = parser.parse_args()
    try:
        rom = Rom(args.rom.read_bytes())
        at = {k: getattr(args, f'{k}_at', None) for k in ORIGINAL}
        doc = json.loads(args.source.read_text(encoding='utf-8')) if getattr(args, 'source', None) else None
        if args.command == 'check':
            check(rom, doc, at)
        else:
            result = parse(rom) if args.command == 'dump' else patch(rom, doc, at)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            print(f'{args.command} → {args.out}')
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(f'오류: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
