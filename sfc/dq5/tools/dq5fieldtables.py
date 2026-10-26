"""DQ5 필드 블록·입구·도착 표 쓰기. 형식은 sfc/dq5/docs/dq5-field-format.md.

블록 표(00:BC4E)는 아래층 2A:A32C, 위층 2A:AD27 에 각각 511항목이다.
번호 511은 다음 표·세계 1 RLE와 겹치므로 쓰지 않는다. 블록 상위 비트 바이트의
하위 니블은 원본에서 보존한다. 입구(2A:F247·FDCB)와 도착(2A:F384)도 고정 슬롯만
고치며 종료자·항목 순서·특수 그룹 도착 코드는 바꾸지 않는다.

  python sfc/dq5/tools/dq5fieldtables.py rom/dq5.sfc dump -o work/fieldtables.json
  python sfc/dq5/tools/dq5fieldtables.py rom/dq5.sfc patch work/fieldtables.json -o work/fieldtables.dq5patch.json
  python sfc/dq5/tools/dq5fieldtables.py rom/dq5.sfc check

JSON format 은 dq5fieldtables/1. blocks: [{index, lower:[타일4개], upper:[타일4개]}],
entrances: [{table:"main"|"aux", index, group, x, y}],
arrivals: [{group, map, x, y, layer, world_code, wagon, direction, party_overlap, map_flags}].
목록과 식별자 외의 필드는 생략할 수 있다. 생략한 값은 원본에서 보존한다.
번호·좌표·타일은 JSON 정수다. 세계 코드 0은 원본의 빈 세계 값이며 1~3이 세계 0~2다.
입구 그룹 50~54(16진)는 도착 표가 아닌 특수 코드가 처리한다. 원본의 좌표별 예외도 남는다.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5field import BLOCK_LOWER, BLOCK_UPPER, ENTRANCES, GROUP_ARRIVAL, QUAD_BIT  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402

FORMAT = 'dq5fieldtables/1'
BLOCK_COUNT = 511
ARRIVAL_COUNT = 0x36
ENTRANCE_TABLES = {'main': (ENTRANCES, 47), 'aux': (0x04FE83, 14)}
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


def group_number(value):
    integer(value, 0x54, 'group')
    if 0x36 <= value < 0x50:
        raise ValueError('입구 group 은 00~35 또는 50~54(16진)여야 함')
    return value


def record(rom, addr):
    off = lorom(addr)
    raw = bytes(rom.d[off:off + 5])
    if len(raw) != 5:
        raise ValueError(f'{addr:06X}: 롬에 5바이트 항목이 없음')
    return raw


def check_layout(rom):
    for table in (BLOCK_LOWER, BLOCK_UPPER):
        record(rom, table + (BLOCK_COUNT - 1) * 5)
    record(rom, GROUP_ARRIVAL + (ARRIVAL_COUNT - 1) * 5)
    for name, (start, count) in ENTRANCE_TABLES.items():
        end = lorom(start + count * 5)
        if end >= len(rom.d) or rom.d[end] != 0xFF:
            raise ValueError(f'{name} 입구 표의 고정 종료자가 FF 가 아님')
        for i in range(count):
            group_number(record(rom, start + i * 5)[0])


def block_tiles(raw):
    return [raw[i] | (256 if raw[4] & bit else 0) for i, bit in enumerate(QUAD_BIT)]


def encode_block(raw, tiles):
    if not isinstance(tiles, list) or len(tiles) != 4:
        raise ValueError('블록 층은 타일 번호 네 개의 배열이어야 함')
    values = [integer(v, 511, '타일') for v in tiles]
    high = raw[4] & 0x0F
    for value, bit in zip(values, QUAD_BIT):
        if value & 256:
            high |= bit
    return bytes([*(v & 255 for v in values), high])


def entrance_fields(raw):
    return {'group': raw[0], 'x': int.from_bytes(raw[1:3], 'little'), 'y': int.from_bytes(raw[3:5], 'little')}


def encode_entrance(raw, changes):
    value = entrance_fields(raw) | changes
    return bytes([group_number(value['group'])]) + integer(value['x'], 511, 'x').to_bytes(2, 'little') + \
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


def dump(rom):
    check_layout(rom)
    return {
        'format': FORMAT,
        'blocks': [{'index': i, 'lower': block_tiles(record(rom, BLOCK_LOWER + i * 5)),
                    'upper': block_tiles(record(rom, BLOCK_UPPER + i * 5))} for i in range(BLOCK_COUNT)],
        'entrances': [{'table': name, 'index': i, **entrance_fields(record(rom, start + i * 5))}
                      for name, (start, count) in ENTRANCE_TABLES.items() for i in range(count)],
        'arrivals': [{'group': i, **arrival_fields(record(rom, GROUP_ARRIVAL + i * 5))} for i in range(ARRIVAL_COUNT)],
    }


def edits(rom, doc):
    """검사한 항목을 (주소, 새 값, 원본, 설명)으로 돌려준다."""
    fields(doc, {'format', 'blocks', 'entrances', 'arrivals'}, '문서')
    if doc.get('format') != FORMAT:
        raise ValueError(f'format 은 {FORMAT}이어야 함')
    check_layout(rom)
    out = []
    for section in ('blocks', 'entrances', 'arrivals'):
        rows = doc.get(section, [])
        if not isinstance(rows, list):
            raise ValueError(f'{section}: 배열이어야 함')
        seen = set()
        for row in rows:
            if section == 'blocks':
                fields(row, {'index', 'lower', 'upper'}, section)
                key = integer(row.get('index'), BLOCK_COUNT - 1, 'index')
                for layer, start in (('lower', BLOCK_LOWER), ('upper', BLOCK_UPPER)):
                    if layer in row:
                        addr = start + key * 5
                        raw = record(rom, addr)
                        out.append((addr, encode_block(raw, row[layer]), raw, f'블록 {key} {layer}'))
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
                out.append((addr, encode_entrance(raw, changes), raw, f'{table} 입구 {index}'))
            else:
                fields(row, {'group'} | ARRIVAL_FIELDS, section)
                key = integer(row.get('group'), ARRIVAL_COUNT - 1, 'group')
                addr = GROUP_ARRIVAL + key * 5
                raw = record(rom, addr)
                changes = {k: v for k, v in row.items() if k != 'group'}
                out.append((addr, encode_arrival(raw, changes), raw, f'그룹 {key:02X} 도착'))
            if key in seen:
                raise ValueError(f'{section}: 중복 항목 {key}')
            seen.add(key)
    return out


def patch(rom, doc, name='field-tables'):
    writes = []
    for addr, new, old, note in edits(rom, doc):
        if new != old:
            writes.append({'at': f'{addr >> 16:02X}:{addr & 0xFFFF:04X}', 'hex': new.hex(' '),
                           'orig': old.hex(' '), 'note': note})
    return {'format': 'dq5patch/1', 'name': name, 'writes': writes}


def check(rom):
    rows = edits(rom, dump(rom))
    bad = sum(new != old for _, new, old, _ in rows)
    print(f'블록 {BLOCK_COUNT}개 × 2층, 입구 61개, 도착 {ARRIVAL_COUNT}개: '
          f'{sum(len(old) for _, _, old, _ in rows)}바이트, 다른 항목 {bad}개')
    return bool(bad)


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
                result = patch(rom, json.load(f), args.name)
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
