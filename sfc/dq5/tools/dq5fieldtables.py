"""DQ5 필드 블록·입구·도착 표 쓰기. 형식은 sfc/dq5/docs/dq5-field-format.md.

블록 표(00:BC4E)는 아래층 2A:A32C, 위층 2A:AD27 에 각각 511항목이다.
번호 511은 다음 표·세계 1 RLE와 겹치므로 제자리에는 쓰지 않는다. --blocks-at 을 주면 번호 511~2047 을 그 자리의 두 표로
더하고 00:BC4E 를 그 표도 읽는 훅으로, 지형 표(03:CC48)를 1,024바이트로 옮긴다(블록마다 terrain). 블록 상위 비트 바이트의
하위 니블은 원본에서 보존한다. dq5fieldgfxwrite.py 의 타일 늘리기 패치를 넣은 롬(00:BC80 이 JSL)이면
그 니블을 10번째 비트로 써서 타일 번호를 1023 까지 받는다. check 는 롬의 블록 표가 타일이 가장 적은 세계의 타일 수
이상을 쓰면 실패한다(그림 쪽 타일 수를 바꾸면 이 도구의 패치를 다시 만들 것). 입구(2A:F247·FDCB)와 도착(2A:F384)도 고정 슬롯만
고치며 종료자·항목 순서·특수 그룹 도착 코드는 바꾸지 않는다.

  python sfc/dq5/tools/dq5fieldtables.py rom/dq5.sfc dump -o work/fieldtables.json
  python sfc/dq5/tools/dq5fieldtables.py rom/dq5.sfc patch work/fieldtables.json -o work/fieldtables.dq5patch.json
  python sfc/dq5/tools/dq5fieldtables.py rom/dq5.sfc check
  python sfc/dq5/tools/dq5fieldtables.py rom/dq5.sfc patch work/entrances.json --entrances-at 68:8000 -o …

JSON format 은 dq5fieldtables/1. blocks: [{index, lower:[타일4개], upper:[타일4개]}],
entrances: [{table:"main"|"aux", index, group, x, y}],
arrivals: [{group, map, x, y, layer, world_code, wagon, direction, party_overlap, map_flags}].
목록과 식별자 외의 필드는 생략할 수 있다. 생략한 값은 원본에서 보존한다.
번호·좌표·타일은 JSON 정수다. 세계 코드 0은 원본의 빈 세계 값이며 1~3이 세계 0~2다.
입구 그룹 50~54(16진)는 도착 표가 아닌 특수 코드가 처리한다. 원본의 좌표별 예외도 남는다.
입구 그룹은 롬의 맵 포인터 그룹 수(dq5newmap.py 로 늘린 롬이면 늘린 수)까지 받는다. 원본 롬에서 새 그룹(36~)의 입구를
함께 만들 때는 --new-map GG/MM 으로 그 그룹을 알린다(dq5newmap.py 입력과 같은 새 맵).
도착 표(0F:EA97)는 dq5newmap.py 의 「들어가는 곳 표」와 같은 표다. 새 그룹의 도착은 그 도구의 groups[].entrance 로 쓰고,
그 도구가 옮긴 롬에서는 옮긴 자리를 읽기만 한다(두 도구가 같은 자리를 쓰지 않게).
entrance_tables: {main: [{group, x, y}…], aux: […]} 는 입구 표 전체를 새 길이로 --entrances-at 자리에 옮겨 쓴다.
적지 않은 표는 원본 항목을 그대로 옮긴다. 표를 읽는 긴 주소 20곳과 세계 지도의 포인터 둘을 새 자리로 바꾼다.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5field import (BLOCK_GROW_SITE, BLOCK_HOOK_SITE, BLOCK_LOWER, BLOCK_UPPER, ENTRANCES, GROUP_ARRIVAL,  # noqa: E402
                      INDEX5, QUAD_BIT, QUAD_BIT10, TERRAIN_SITES, block_count, block_entry, grown_blocks, terrain_table)
from dq5map import Rom, group_spans, lorom  # noqa: E402
from dq5newmap import entrance_table  # noqa: E402

FORMAT = 'dq5fieldtables/1'
BLOCK_COUNT = 511
# --blocks-at 으로 늘릴 수 있는 블록 수. 지도의 블록 번호는 11비트까지다(10·11번째 비트는 dq5fieldwrite.py --planes-at).
BLOCK_MAX = 2048
BLOCK_GROW_ORIG = bytes.fromhex('c2308500')
TERRAIN_ORIG = bytes.fromhex('bf48cc03')
# 원본 롬의 도착 항목 수(그룹 00~35). 늘린 롬은 arrivals() 가 센다.
ARRIVAL_COUNT = 0x36
ENTRANCE_TABLES = {'main': (ENTRANCES, 47), 'aux': (0x04FE83, 14)}
# 입구 표를 긴 주소로 읽는 명령(LDA·CMP long,X)과 그 피연산자가 가리키는 표 안 거리(0 그룹, 1 X, 3 Y).
# 1E:E56C~ ルーラ 행선지, 2A:F24F~ 마을 입장, 2A:F42D~ 필드로 나옴, 2A:FE11~ 걸어 들어가는 보조 입구.
ENTRANCE_REFS = {
    'main': [(0x1EE56C, 0), (0x1EE581, 1), (0x1EE58A, 3), (0x2AF24F, 0), (0x2AF259, 1), (0x2AF263, 3),
             (0x2AF26B, 0), (0x2AF42D, 0), (0x2AF458, 1), (0x2AF45E, 3)],
    'aux': [(0x1EE59B, 0), (0x1EE5AC, 1), (0x1EE5B5, 3), (0x2AF443, 0), (0x2AF468, 1), (0x2AF46E, 3),
            (0x2AFE11, 0), (0x2AFE1B, 1), (0x2AFE25, 3), (0x2AFE32, 0)],
}
# 03:C811(세계 지도에서 지금 그룹의 필드 자리 찾기)이 LDY/LDA 로 읽는 [main 24비트][aux 24비트].
ENTRANCE_POINTERS = 0x03C880
# ルーラ 행선지 그룹 22개. 1E:E59B 의 보조 표 루프는 FF 를 보지 않으므로 이 그룹은 두 표 가운데 하나에 꼭 있어야 한다.
RULER_GROUPS = (0x2585D5, 22)
ARRIVAL_FIELDS = {'map', 'x', 'y', 'layer', 'world_code', 'wagon', 'direction', 'party_overlap', 'map_flags'}


def integer(value, maximum, name):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError(f'{name}: 0~{maximum} 정수여야 함')
    return value


def boolean(value, name):
    if type(value) is not bool:
        raise ValueError(f'{name}: true 또는 false 여야 함')
    return int(value)


def fields(value, allowed, name):
    if not isinstance(value, dict):
        raise ValueError(f'{name}: JSON 객체여야 함')
    unknown = value.keys() - allowed
    if unknown:
        raise ValueError(f'{name}: 모르는 필드 {", ".join(sorted(unknown))}')


def group_number(value, groups):
    integer(value, 0x54, 'group')
    if groups <= value < 0x50:
        raise ValueError(f'입구 group 은 00~{groups - 1:02X} 또는 50~54(16진)여야 함')
    return value


def interior_groups(rom, new_maps=()):
    """그룹 50 미만의 그룹 수. 롬의 맵 포인터 그룹에 --new-map 이 알린 새 그룹을 더한다."""
    try:
        count = len(group_spans(rom)[0])
    except IndexError:
        raise ValueError('롬에 맵 포인터 그룹 표가 없음') from None
    # 그룹 50 이상의 새 맵은 새 그룹이 아니다(입구 그룹 50~54 는 늘 받음).
    new = sorted({bc for bc, _ in new_maps if count <= bc < 0x50})
    if new != list(range(count, count + len(new))):
        raise ValueError(f'--new-map 의 새 그룹은 {count:02X} 부터 빈 번호 없이 50 미만이어야 함')
    return count + len(new)


def arrivals(rom):
    """도착 표 자리와 항목 수. 표를 옮긴 롬(dq5newmap.py)이면 옮긴 자리와 늘린 그룹 수다."""
    return entrance_table(rom), len(group_spans(rom)[0])


def record(rom, addr):
    off = lorom(addr)
    raw = bytes(rom.d[off:off + 5])
    if len(raw) != 5:
        raise ValueError(f'{addr:06X}: 롬에 5바이트 항목이 없음')
    return raw


def check_layout(rom, groups):
    for table in (BLOCK_LOWER, BLOCK_UPPER):
        record(rom, table + (BLOCK_COUNT - 1) * 5)
    table, count = arrivals(rom)
    record(rom, table + (count - 1) * 5)
    for name, (start, count) in ENTRANCE_TABLES.items():
        end = lorom(start + count * 5)
        if end >= len(rom.d) or rom.d[end] != 0xFF:
            raise ValueError(f'{name} 입구 표의 고정 종료자가 FF 가 아님')
        for i in range(count):
            group_number(record(rom, start + i * 5)[0], groups)


def wide_tiles(rom):
    """타일 늘리기 훅이 블록의 10번째 비트를 읽는 롬인지."""
    return rom.u8(BLOCK_HOOK_SITE) == 0x22


def block_tiles(raw, wide=False):
    return [raw[i] | (256 if raw[4] & bit else 0) | (512 if wide and raw[4] & bit10 else 0)
            for i, (bit, bit10) in enumerate(zip(QUAD_BIT, QUAD_BIT10))]


def tile_limit(rom):
    """블록 칸이 쓸 수 있는 가장 큰 타일 번호. 블록 표는 세 세계가 함께 쓰므로 타일이 가장 적은 세계를 따른다."""
    if not wide_tiles(rom):
        return 511
    from dq5fieldgfxwrite import tile_counts
    return min(tile_counts(rom)) - 1


def encode_block(raw, tiles, wide=False, limit=None):
    if not isinstance(tiles, list) or len(tiles) != 4:
        raise ValueError('블록 층은 타일 번호 네 개의 배열이어야 함')
    if not wide and any(type(v) is int and 512 <= v <= 1023 for v in tiles):
        raise ValueError('타일 512 이상은 dq5fieldgfxwrite.py 의 타일 늘리기(--extra-at) 패치를 넣은 롬으로 만들어야 함')
    limit = (1023 if wide else 511) if limit is None else limit
    if any(type(v) is int and limit < v <= 1023 for v in tiles):
        raise ValueError(f'블록은 세 세계가 함께 쓰므로 모든 세계에 그 타일을 둘 것(타일이 가장 적은 세계가 '
                         f'{limit + 1}개)')
    values = [integer(v, limit, '타일') for v in tiles]
    high = 0 if wide else raw[4] & 0x0F
    for value, bit, bit10 in zip(values, QUAD_BIT, QUAD_BIT10):
        if value & 256:
            high |= bit
        if value & 512:
            high |= bit10
    return bytes([*(v & 255 for v in values), high])


def entrance_fields(raw):
    return {'group': raw[0], 'x': int.from_bytes(raw[1:3], 'little'), 'y': int.from_bytes(raw[3:5], 'little')}


def encode_entrance(raw, changes, groups):
    value = entrance_fields(raw) | changes
    return bytes([group_number(value['group'], groups)]) + integer(value['x'], 511, 'x').to_bytes(2, 'little') + \
        integer(value['y'], 511, 'y').to_bytes(2, 'little')


def arrival_fields(raw):
    return {'map': raw[0] & 31, 'world_code': (raw[0] >> 5) & 3, 'wagon': bool(raw[0] & 128),
            'x': raw[1], 'y': raw[2], 'layer': raw[3], 'direction': raw[4] & 3,
            'party_overlap': bool(raw[4] & 128), 'map_flags': (raw[4] >> 2) & 31}


def encode_arrival(raw, changes):
    v = arrival_fields(raw) | changes
    head = integer(v['map'], 31, 'map') | integer(v['world_code'], 3, 'world_code') << 5 | boolean(v['wagon'], 'wagon') << 7
    tail = integer(v['direction'], 3, 'direction') | integer(v['map_flags'], 31, 'map_flags') << 2 | \
        boolean(v['party_overlap'], 'party_overlap') << 7
    return bytes([head, integer(v['x'], 255, 'x'), integer(v['y'], 255, 'y'), integer(v['layer'], 255, 'layer'), tail])


def lorom_cpu(at, option='--entrances-at'):
    bank, _, addr = at.partition(':')
    try:
        b, a = int(bank, 16), int(addr, 16)
    except ValueError:
        b = a = -1
    if not (0 <= b <= 0x7D and 0x8000 <= a <= 0xFFFF):
        raise ValueError(f'{option} {at!r}: BB:AAAA(뱅크 00~7D, AAAA 8000~FFFF) 여야 함')
    return b << 16 | a


def entrance_list(rows, table, groups):
    if not isinstance(rows, list) or not rows:
        raise ValueError(f'entrance_tables.{table}: 항목이 하나 이상인 배열이어야 함')
    out = b''
    for row in rows:
        fields(row, {'group', 'x', 'y'}, f'entrance_tables.{table}')
        if row.keys() != {'group', 'x', 'y'}:
            raise ValueError(f'entrance_tables.{table}: group·x·y 를 모두 적어야 함')
        out += encode_entrance(bytes(5), row, groups)
    return out


def table_groups(body, start):
    groups, i = set(), start
    while body[i] != 0xFF:
        groups.add(body[i])
        i += 5
    return groups


def relocate(rom, tables, at, groups):
    """입구 표 둘을 at 에 [main][FF][aux][FF] 로 쓰고 읽는 곳을 바꾸는 (주소, 새 값, 원본|None, 설명)."""
    fields(tables, set(ENTRANCE_TABLES), 'entrance_tables')
    start = lorom_cpu(at)
    body, place = b'', {}
    for name, (old, count) in ENTRANCE_TABLES.items():
        place[name] = start + len(body)
        if name in tables:
            body += entrance_list(tables[name], name, groups)
        else:
            off = lorom(old)
            body += bytes(rom.d[off:off + count * 5])
        body += b'\xff'
    if (start & 0xFFFF) + len(body) > 0x10000:
        raise ValueError(f'입구 표 {len(body)}바이트가 {at} 의 뱅크 끝을 넘음')
    groups = {g for name in ENTRANCE_TABLES for g in table_groups(body, place[name] - start)}
    off = lorom(RULER_GROUPS[0])
    missing = sorted(set(rom.d[off:off + RULER_GROUPS[1]]) - groups)
    if missing:
        raise ValueError('ルーラ 행선지 그룹이 두 입구 표에 없음: ' + ' '.join(f'{g:02X}' for g in missing))
    # 원래 롬 안이어도 orig 를 붙이지 않는다. 빌더가 빈 자리 지도 밖이면 거부하게 하기 위해서다.
    out = [(start, body, None, '옮긴 입구 표')]
    for name, refs in ENTRANCE_REFS.items():
        base = ENTRANCE_TABLES[name][0]
        for pc, delta in refs:
            raw = bytes(rom.d[lorom(pc):lorom(pc) + 4])
            if raw[0] not in (0xBF, 0xDF) or int.from_bytes(raw[1:], 'little') != base + delta:
                raise ValueError(f'{pc >> 16:02X}:{pc & 0xFFFF:04X}: 원본 입구 표 읽기 명령이 아님')
            out.append((pc + 1, (place[name] + delta).to_bytes(3, 'little'), raw[1:], f'{name} 입구 표 읽기'))
    raw = bytes(rom.d[lorom(ENTRANCE_POINTERS):lorom(ENTRANCE_POINTERS) + 6])
    if raw != ENTRANCE_TABLES['main'][0].to_bytes(3, 'little') + ENTRANCE_TABLES['aux'][0].to_bytes(3, 'little'):
        raise ValueError('03:C880 의 입구 표 포인터가 원본과 다름')
    out.append((ENTRANCE_POINTERS, place['main'].to_bytes(3, 'little') + place['aux'].to_bytes(3, 'little'), raw,
                '세계 지도의 입구 표 포인터'))
    return out


def terrains(rom):
    """지형 니블을 블록 번호 차례로(원래 표는 512블록 몫 256바이트). 블록을 1,024개까지 늘리던 롬은 옮긴 표가 512바이트라
    블록 수만큼만 읽는다."""
    off = lorom(terrain_table(rom))
    raw = rom.d[off:off + (max(512, block_count(rom)) + 1) // 2]
    return [v for b in raw for v in (b >> 4, b & 15)]


def dump(rom):
    check_layout(rom, interior_groups(rom))
    table, count = arrivals(rom)
    land, wide = terrains(rom), wide_tiles(rom)
    return {
        'format': FORMAT,
        'blocks': [{'index': i, 'lower': block_tiles(record(rom, block_entry(rom, False, i)), wide or i >= BLOCK_COUNT),
                    'upper': block_tiles(record(rom, block_entry(rom, True, i)), wide or i >= BLOCK_COUNT),
                    'terrain': land[i]}
                   for i in range(block_count(rom))],
        'entrances': [{'table': name, 'index': i, **entrance_fields(record(rom, start + i * 5))}
                      for name, (start, count) in ENTRANCE_TABLES.items() for i in range(count)],
        'arrivals': [{'group': i, **arrival_fields(record(rom, table + i * 5))} for i in range(count)],
    }


def edits(rom, doc, entrances_at=None, new_maps=(), blocks_at=None):
    """검사한 항목을 (주소, 새 값, 원본, 설명)으로 돌려준다. 원본이 None 이면 orig 없이 쓰는 새 자리."""
    fields(doc, {'format', 'blocks', 'entrances', 'arrivals', 'entrance_tables'}, '문서')
    if ('entrance_tables' in doc) != (entrances_at is not None):
        raise ValueError('entrance_tables 와 --entrances-at 은 함께 써야 함')
    if 'entrance_tables' in doc and doc.get('entrances'):
        raise ValueError('entrance_tables 로 옮길 때는 entrances(제자리 수정)를 함께 쓸 수 없음')
    if doc.get('format') != FORMAT:
        raise ValueError(f'format 은 {FORMAT}이어야 함')
    groups = interior_groups(rom, new_maps)
    check_layout(rom, groups)
    arrival_at, arrival_count = arrivals(rom)
    limit = tile_limit(rom)
    grown = grown_blocks(rom)
    if blocks_at is not None and grown:
        raise ValueError('이미 블록을 늘린 롬(00:BC4E 가 JML)이라 --blocks-at 을 다시 쓸 수 없음; 원래 롬으로 만들 것')
    count = grown[2] if grown else BLOCK_MAX if blocks_at is not None else BLOCK_COUNT
    land, new_blocks = terrains(rom), {}
    land += [0] * (count - len(land))
    out = []
    for section in ('blocks', 'entrances', 'arrivals'):
        rows = doc.get(section, [])
        if not isinstance(rows, list):
            raise ValueError(f'{section}: 배열이어야 함')
        seen = set()
        for row in rows:
            if section == 'blocks':
                fields(row, {'index', 'lower', 'upper', 'terrain'}, section)
                if blocks_at is None and not grown and type(row.get('index')) is int and \
                        BLOCK_COUNT <= row['index'] < BLOCK_MAX:
                    raise ValueError(f'블록 {row["index"]}: 번호 {BLOCK_COUNT} 이상은 --blocks-at 으로 블록 표를 늘려야 함')
                key = integer(row.get('index'), count - 1, 'index')
                if 'terrain' in row:
                    land[key] = integer(row['terrain'], 15, 'terrain')
                if key >= BLOCK_COUNT and not grown:
                    if row.keys() != {'index', 'lower', 'upper', 'terrain'}:
                        raise ValueError(f'블록 {key}: 새 블록은 lower·upper·terrain 을 모두 적어야 함')
                    new_blocks[key] = b''.join(encode_block(bytes(5), row[layer], True, limit)
                                               for layer in ('lower', 'upper'))
                for layer, upper in (('lower', False), ('upper', True)):
                    if layer in row and (key < BLOCK_COUNT or grown):
                        addr = block_entry(rom, upper, key)
                        raw = record(rom, addr)
                        out.append((addr, encode_block(raw, row[layer], wide_tiles(rom) or key >= BLOCK_COUNT, limit),
                                    raw, f'블록 {key} {layer}'))
            elif section == 'entrances':
                fields(row, {'table', 'index', 'group', 'x', 'y'}, section)
                table = row.get('table')
                if not isinstance(table, str) or table not in ENTRANCE_TABLES:
                    raise ValueError('table 은 main 또는 aux 여야 함')
                start, count = ENTRANCE_TABLES[table]
                index = integer(row.get('index'), count - 1, 'index')
                key = table, index
                addr = start + index * 5
                raw = record(rom, addr)
                changes = {k: v for k, v in row.items() if k not in ('table', 'index')}
                out.append((addr, encode_entrance(raw, changes, groups), raw, f'{table} 입구 {index}'))
            else:
                fields(row, {'group'} | ARRIVAL_FIELDS, section)
                key = integer(row.get('group'), arrival_count - 1, 'group')
                addr = arrival_at + key * 5
                raw = record(rom, addr)
                changes = {k: v for k, v in row.items() if k != 'group'}
                value = encode_arrival(raw, changes)
                if value != raw and arrival_at != GROUP_ARRIVAL:
                    raise ValueError(f'그룹 {key:02X} 도착: 도착 표를 옮긴 롬은 dq5newmap.py 의 groups[].entrance 로 고침'
                                     '(같은 자리를 두 도구가 쓰지 않게)')
                # 새 그룹을 더하는 빌드는 dq5newmap.py 가 원래 표를 새 자리로 복사하므로, 원래 자리에 쓴 값은 읽히지 않는다.
                if value != raw and groups > arrival_count:
                    raise ValueError(f'그룹 {key:02X} 도착: 새 그룹을 더하는 빌드에서는 dq5newmap groups[].entrance 로 고침')
                out.append((addr, value, raw, f'그룹 {key:02X} 도착'))
            if key in seen:
                raise ValueError(f'{section}: 중복 항목 {key}')
            seen.add(key)
    out += terrain_edits(rom, land, blocks_at is not None)
    if blocks_at is not None:
        out += grow_blocks(rom, new_blocks, blocks_at, land)
    if entrances_at is not None:
        out += relocate(rom, doc['entrance_tables'], entrances_at, groups)
    return out


def terrain_edits(rom, land, moving):
    """지형 니블 변경을 지금 표 자리의 바이트 쓰기로. 블록 표를 늘리면 표 전체를 grow_blocks 가 옮기므로 쓰지 않는다."""
    if moving:
        return []
    table, out = terrain_table(rom), []
    for i in range(0, len(land) // 2 * 2, 2):
        raw = record_byte(rom, table + i // 2)
        new = bytes([land[i] << 4 | land[i + 1]])
        if new != raw:
            out.append((table + i // 2, new, raw, f'블록 {i}·{i + 1} 지형'))
    return out


def record_byte(rom, addr):
    off = lorom(addr)
    return bytes(rom.d[off:off + 1])


def block_hook(lower, upper, count, masks):
    """00:BC4E 대신(JML 로 들어옴, M·X 는 아무것이나). 번호가 511 미만이면 INDEX5 를 하고 00:BC6D 로 돌아가 원래 표를 읽고,
    511 이상이면 옮긴 두 표(번호 511 부터)에서 원래와 같이 $94~$97 을 채운 뒤 00:BC47 의 RTS 로 부른 곳에 돌아간다.
    필드를 불러올 때 칸마다 불리므로, 511 미만 갈래가 원래 00:BC4E~BC6C 보다 몇 사이클만 길어도 불러오기가 한 프레임 늦어진다.
    칸 타일의 10번째 비트(상위 비트 바이트의 하위 니블)도 읽는다. masks 는 80>>칸 4개와 08>>칸 4개이고
    DB 를 훅 뱅크로 두고 읽는다."""
    def layer(table, dp):
        return (b'\xbf' + long3(table + 4) + b'\x39' + (masks + 4 & 0xFFFF).to_bytes(2, 'little') + b'\xc9\x01\xa9\x00\x2a\xeb'
                + b'\xbf' + long3(table + 4) + b'\x39' + (masks & 0xFFFF).to_bytes(2, 'little') + b'\xc9\x01\xeb\x2a'
                + bytes([0x85, dp]))
    fast = INDEX5 + b'\x5c\x6d\xbc\x00'
    return (b'\x80\x08' + long3(lower) + long3(upper) + count.to_bytes(2, 'little')
            + b'\xc2\x30\xc9\xff\x01\xb0' + bytes([len(fast)]) + fast
            + b'\xe9\xff\x01' + INDEX5
            + b'\x8b\x4b\xab\xe2\x20' + b'\xbf' + long3(lower) + b'\x85\x94' + b'\xbf' + long3(upper) + b'\x85\x96'
            + b'\xa6\x02' + layer(lower, 0x95) + layer(upper, 0x97) + b'\xab\x5c\x47\xbc\x00')


def long3(a):
    return a.to_bytes(3, 'little')


BLOCK_HOOK_LEN = len(block_hook(0, 0, 0, 0))
MASKS = bytes([0x80, 0x40, 0x20, 0x10, 0x08, 0x04, 0x02, 0x01])


def grow_blocks(rom, new_blocks, at, land):
    """블록 511 이상을 at 에 [훅][칸 마스크 8][아래층 표][위층 표][지형 1,024바이트] 로 두고 00:BC4E·03:CB1B 의 두 읽기를 바꾼다."""
    if not new_blocks:
        raise ValueError('--blocks-at 은 번호 511 이상의 블록을 더할 때만')
    n = max(new_blocks) + 1
    missing = [i for i in range(BLOCK_COUNT, n) if i not in new_blocks]
    if missing:
        raise ValueError(f'새 블록은 {BLOCK_COUNT} 부터 빈 번호 없이 적어야 함(빠진 번호 {missing[0]})')
    for site, want in ((BLOCK_GROW_SITE, BLOCK_GROW_ORIG), *((t, TERRAIN_ORIG) for t in TERRAIN_SITES)):
        if bytes(rom.d[lorom(site):lorom(site) + 4]) != want:
            raise ValueError(f'{site >> 16:02X}:{site & 0xFFFF:04X}: 원래 롬의 블록·지형 읽기가 아님')
    masks = at + BLOCK_HOOK_LEN
    lower = masks + len(MASKS)
    upper = lower + (n - BLOCK_COUNT) * 5
    terrain = upper + (n - BLOCK_COUNT) * 5
    end = terrain + BLOCK_MAX // 2
    bank = at >> 16
    if not 0x30 <= bank <= 0x7D or at & 0xFFFF < 0x8000 or (end - 1) >> 16 != bank:
        raise ValueError(f'--blocks-at 은 30~7D 뱅크의 8000~FFFF 한 뱅크 안({end - at}바이트)')
    body = (block_hook(lower, upper, n, masks) + MASKS
            + b''.join(new_blocks[i][:5] for i in range(BLOCK_COUNT, n))
            + b''.join(new_blocks[i][5:] for i in range(BLOCK_COUNT, n))
            + bytes(land[i] << 4 | land[i + 1] for i in range(0, BLOCK_MAX, 2)))
    out = [(at, body, None, f'블록 {BLOCK_COUNT}~{n - 1} 훅·표와 지형 표')]
    out.append((BLOCK_GROW_SITE, b'\x5c' + long3(at), BLOCK_GROW_ORIG, '블록 표 읽기(00:BC4E)를 늘리기 훅으로'))
    for site in TERRAIN_SITES:
        out.append((site, b'\xbf' + long3(terrain), TERRAIN_ORIG, '지형 표 읽기를 옮긴 표로'))
    return out


def patch(rom, doc, name='field-tables', entrances_at=None, new_maps=(), blocks_at=None):
    writes, size = [], 0
    for addr, new, old, note in edits(rom, doc, entrances_at, new_maps, blocks_at):
        if new != old:
            write = {'at': f'{addr >> 16:02X}:{addr & 0xFFFF:04X}', 'hex': new.hex(' '), 'note': note}
            if old is not None:
                write['orig'] = old.hex(' ')
            writes.append(write)
            end = lorom(addr) + len(new) if addr >> 16 >= 0x30 else 0
            size = max(size, 4 if end > 0x300000 else 3 if end > 0x200000 else 2 if end > 0x180000 else 0)
    doc = {'format': 'dq5patch/1', 'name': name, 'writes': writes}
    if size:
        doc['rom_size'] = size
    return doc


def block_overflow(rom):
    """롬의 블록 표에서 타일 수가 가장 적은 세계의 타일 수 이상을 쓰는 칸 [(블록, 층, 타일)]. 그림 쪽 타일 수를 블록 패치를
    만든 뒤에 줄여 빌드하면 패치를 만들 때의 검사가 다시 돌지 않으므로, 빌드한 롬에서 이것으로 다시 본다."""
    limit, wide = tile_limit(rom), wide_tiles(rom)
    return [(i, layer, v) for i in range(block_count(rom)) for layer, upper in (('lower', False), ('upper', True))
            for v in block_tiles(record(rom, block_entry(rom, upper, i)), wide or i >= BLOCK_COUNT) if v > limit]


def check(rom):
    over = block_overflow(rom)
    if over:
        i, layer, v = over[0]
        print(f'블록 칸 {len(over)}개가 타일이 가장 적은 세계의 타일 수({tile_limit(rom) + 1}개)를 넘음'
              f'(처음: 블록 {i} {layer} 타일 {v}). 그림 쪽 타일 수를 바꿨으면 dq5fieldtables 패치를 다시 만들 것')
        return True
    rows = edits(rom, dump(rom))
    bad = sum(new != old for _, new, old, _ in rows)
    print(f'블록 {block_count(rom)}개 × 2층, 입구 61개, 도착 {arrivals(rom)[1]}개: '
          f'{sum(len(old) for _, _, old, _ in rows)}바이트, 다른 항목 {bad}개')
    return bool(bad)


def new_map(text):
    if not re.fullmatch(r'[0-9A-F]{2}/[0-9A-F]{2}', text):
        raise argparse.ArgumentTypeError('--new-map 은 대문자 16진 GG/MM 이어야 함')
    return tuple(int(v, 16) for v in text.split('/'))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('rom')
    subs = parser.add_subparsers(dest='command', required=True)
    export = subs.add_parser('dump')
    export.add_argument('-o', '--out', required=True)
    write = subs.add_parser('patch')
    write.add_argument('source')
    write.add_argument('-o', '--out', required=True)
    write.add_argument('--name', default='field-tables')
    write.add_argument('--entrances-at', help='entrance_tables 를 쓸 자리(BB:AAAA). 다른 패치와 겹치지 않게 고름')
    write.add_argument('--blocks-at', help='번호 511 이상의 블록 표·훅·지형 표를 둘 자리(BB:AAAA, 30~7D)')
    write.add_argument('--new-map', action='append', default=[], type=new_map,
                       help='dq5newmap.py 로 함께 더하는 새 맵 GG/MM(새 그룹의 입구를 받게 함)')
    subs.add_parser('check')
    args = parser.parse_args()
    try:
        with open(args.rom, 'rb') as f:
            rom = Rom(f.read())
        if args.command == 'check':
            return int(check(rom))
        if args.command == 'dump':
            result = dump(rom)
        else:
            with open(args.source, encoding='utf-8') as f:
                result = patch(rom, json.load(f), args.name, args.entrances_at, args.new_map,
                               None if args.blocks_at is None else lorom_cpu(args.blocks_at, '--blocks-at'))
        os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
        with open(args.out, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
            f.write('\n')
        print(f'{args.command} → {args.out}')
        if args.command == 'patch':
            print(f'바뀐 항목 {len(result["writes"])}개')
        return 0
    except (ValueError, OSError) as error:
        print(f'오류: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
