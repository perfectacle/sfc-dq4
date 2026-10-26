"""DQ5 필드 블록·입구·도착 표 쓰기. 형식은 sfc/dq5/docs/dq5-field-format.md.

블록 표(00:BC4E)는 아래층 2A:A32C, 위층 2A:AD27 에 각각 511항목이다.
번호 511은 다음 표·세계 1 RLE와 겹치므로 쓰지 않는다. 블록 상위 비트 바이트의
하위 니블은 원본에서 보존한다. 입구(2A:F247·FDCB)와 도착(2A:F384)도 고정 슬롯만
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
entrance_tables: {main: [{group, x, y}…], aux: […]} 는 입구 표 전체를 새 길이로 --entrances-at 자리에 옮겨 쓴다.
적지 않은 표는 원본 항목을 그대로 옮긴다. 표를 읽는 긴 주소 20곳과 세계 지도의 포인터 둘을 새 자리로 바꾼다.
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


def lorom_cpu(at):
    bank, _, addr = at.partition(':')
    try:
        b, a = int(bank, 16), int(addr, 16)
    except ValueError:
        b = a = -1
    if not (0 <= b <= 0x7D and 0x8000 <= a <= 0xFFFF):
        raise ValueError(f'--entrances-at {at!r}: BB:AAAA(뱅크 00~7D, AAAA 8000~FFFF) 여야 함')
    return b << 16 | a


def entrance_list(rows, table):
    if not isinstance(rows, list) or not rows:
        raise ValueError(f'entrance_tables.{table}: 항목이 하나 이상인 배열이어야 함')
    out = b''
    for row in rows:
        fields(row, {'group', 'x', 'y'}, f'entrance_tables.{table}')
        if row.keys() != {'group', 'x', 'y'}:
            raise ValueError(f'entrance_tables.{table}: group·x·y 를 모두 적어야 함')
        out += encode_entrance(bytes(5), row)
    return out


def table_groups(body, start):
    groups, i = set(), start
    while body[i] != 0xFF:
        groups.add(body[i])
        i += 5
    return groups


def relocate(rom, tables, at):
    """입구 표 둘을 at 에 [main][FF][aux][FF] 로 쓰고 읽는 곳을 바꾸는 (주소, 새 값, 원본|None, 설명)."""
    fields(tables, set(ENTRANCE_TABLES), 'entrance_tables')
    check_layout(rom)
    start = lorom_cpu(at)
    body, place = b'', {}
    for name, (old, count) in ENTRANCE_TABLES.items():
        place[name] = start + len(body)
        if name in tables:
            body += entrance_list(tables[name], name)
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


def edits(rom, doc, entrances_at=None):
    """검사한 항목을 (주소, 새 값, 원본, 설명)으로 돌려준다. 원본이 None 이면 orig 없이 쓰는 새 자리."""
    fields(doc, {'format', 'blocks', 'entrances', 'arrivals', 'entrance_tables'}, '문서')
    if ('entrance_tables' in doc) != (entrances_at is not None):
        raise ValueError('entrance_tables 와 --entrances-at 은 함께 써야 함')
    if 'entrance_tables' in doc and doc.get('entrances'):
        raise ValueError('entrance_tables 로 옮길 때는 entrances(제자리 수정)를 함께 쓸 수 없음')
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
    if entrances_at is not None:
        out += relocate(rom, doc['entrance_tables'], entrances_at)
    return out


def patch(rom, doc, name='field-tables', entrances_at=None):
    writes, size = [], 0
    for addr, new, old, note in edits(rom, doc, entrances_at):
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
    write.add_argument('--entrances-at', help='entrance_tables 를 쓸 자리(BB:AAAA). 다른 패치와 겹치지 않게 고름')
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
                result = patch(rom, json.load(f), args.name, args.entrances_at)
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
