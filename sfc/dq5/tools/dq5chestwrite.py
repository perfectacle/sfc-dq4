"""DQ5 보물상자·조사 보상의 고정 표 쓰기.

sfc/dq5/docs/dq5-map-format.md의 보물상자 형식(25:FAB0, 12:FB9D·E6BE·FCDD·FD46).
일반 상자의 좌표와 열림 비트는 맵 셀 순서·상자 번호에서 나온다. chest_maps는
기존 맵 슬롯의 연결/개수만 바꾸며 총 상자 수를 유지한다. 나머지 표는 좌표·보상·
플래그를 직접 바꾼다. 검색 우선순위·목록 길이·미사용 바이트·종료자는 보존한다.

  python sfc/dq5/tools/dq5chestwrite.py rom/dq5.sfc dump -o work/chests.json
  python sfc/dq5/tools/dq5chestwrite.py rom/dq5.sfc patch work/chests.json -o work/chests.patch.json
  python sfc/dq5/tools/dq5chestwrite.py rom/dq5.sfc check [work/chests.json]

JSON format=dq5chest/1. chests[{index,reward}], chest_maps[{index,group,map,count}],
search/foot/ahead/lower[{index,group,map,x,y,reward,flag_index,mask}]. foot만 layer를 받는다.
모든 수치는 JSON 정수, reward는 원본 16비트 부호다. index 외 필드는 생략할 수 있다.
"""
import argparse
import json
import sys
from pathlib import Path

from dq5chest import (AHEAD_TABLE, CHEST_ITEMS, CHEST_MAPS, FOOT_TABLE, LOWER_TABLE,
                      SEARCH_TABLE, chests)
from dq5gfx import map_ids
from dq5map import Rom, lorom, map_pointer

FORMAT = 'dq5chest/1'
TABLES = {'chests': (CHEST_ITEMS, 161, 2), 'chest_maps': (CHEST_MAPS, 83, 3),
          'search': (SEARCH_TABLE, 86, 9), 'foot': (FOOT_TABLE, 18, 9),
          'ahead': (AHEAD_TABLE, 17, 8), 'lower': (LOWER_TABLE, 11, 8)}


def integer(value, maximum, field):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError(f'{field}: 0~{maximum} 정수여야 함')
    return value


def fields(value, allowed, name):
    if not isinstance(value, dict) or value.keys() - allowed:
        raise ValueError(f'{name}: 허용한 필드 {sorted(allowed)}만 있는 객체여야 함')


def read(rom, addr, size):
    raw = bytes(rom.d[lorom(addr):lorom(addr) + size])
    if len(raw) != size:
        raise ValueError(f'{addr:06X}: 롬 범위 밖')
    return raw


def layout(rom):
    for name, (start, count, size) in TABLES.items():
        read(rom, start, count * size)
        if name == 'chests':
            continue
        if read(rom, start + count * size, 2) != b'\xff\xff':
            raise ValueError(f'{name}: 고정 종료자가 FFFF가 아님')
        if any(read(rom, start + i * size, 2) == b'\xff\xff' for i in range(count)):
            raise ValueError(f'{name}: 표 안에 이른 종료자가 있음')


def decode(name, raw):
    if name == 'chests':
        return {'reward': int.from_bytes(raw, 'little')}
    if name == 'chest_maps':
        return dict(zip(('group', 'map', 'count'), raw))
    v = dict(zip(('group', 'map', 'x', 'y'), raw[:4]))
    offset = 5 if len(raw) == 9 else 4
    if name == 'foot':
        v['layer'] = raw[4]
    v.update(reward=int.from_bytes(raw[offset:offset + 2], 'little'),
             flag_index=raw[-2], mask=raw[-1])
    return v


def encode(name, raw, changes):
    value = decode(name, raw) | changes
    fields(changes, set(decode(name, raw)), name)
    for key, v in value.items():
        integer(v, 65535 if key == 'reward' else 255, key)
    if 'reward' in value and not (value['reward'] <= 0xD009 or value['reward'] >= 0xFFFC):
        raise ValueError('reward: D00A~FFFB는 보상 처리기가 지원하지 않음')
    if 'mask' in value and value['mask'] == 0:
        raise ValueError('mask: 열림을 기록할 비트가 필요함')
    out = bytearray(raw)
    if name == 'chests':
        return value['reward'].to_bytes(2, 'little')
    out[0:2] = bytes([value['group'], value['map']])
    if name == 'chest_maps':
        out[2] = value['count']
        return bytes(out)
    out[2:4] = bytes([value['x'], value['y']])
    offset = 5 if len(raw) == 9 else 4
    if name == 'foot':
        out[4] = value['layer']
    out[offset:offset + 2] = value['reward'].to_bytes(2, 'little')
    out[-2:] = bytes([value['flag_index'], value['mask']])
    return bytes(out)


def dump(rom):
    layout(rom)
    return {'format': FORMAT, **{name: [{'index': i, **decode(name, read(rom, start + i * size, size))}
                                       for i in range(count)] for name, (start, count, size) in TABLES.items()}}


def validate_tables(rom, doc, check_cells=False):
    available = set(map_ids(rom))
    for name in TABLES.keys() - {'chests'}:
        seen = set()
        for row in doc[name]:
            if (row['group'], row['map']) not in available:
                raise ValueError(f'{name} {row["index"]}: 존재하지 않는 맵')
            if name == 'chest_maps' and row['group'] >= 0x50:
                raise ValueError('chest_maps: 일반 실내 맵 그룹 00~35만 지원함')
            key = (row['group'], row['map'])
            if name != 'chest_maps':
                key += (row['x'], row['y'])
            if name == 'foot':
                key += (row['layer'],)
            if key in seen:
                raise ValueError(f'{name}: 먼저 나오는 항목에 가려지는 중복 위치 {key}')
            seen.add(key)
    if sum(row['count'] for row in doc['chest_maps']) != TABLES['chests'][1]:
        raise ValueError('chest_maps: count 합계는 161이어야 함')
    if check_cells:
        start = 0
        for row in doc['chest_maps']:
            cells = chests(rom, row['group'], row['map'], start)
            if len(cells) != row['count']:
                raise ValueError(f'chest_maps {row["index"]}: 맵 상자 셀 {len(cells)}개와 count가 다름')
            start += row['count']


def map_dimensions(rom, group, map_number):
    addr = map_pointer(rom, group, map_number)
    return tuple(read(rom, addr + 1, 2))


def edits(rom, doc):
    fields(doc, {'format', *TABLES}, '문서')
    if doc.get('format') != FORMAT:
        raise ValueError(f'format={FORMAT}이 필요함')
    current = dump(rom)
    out, positions, map_changed = [], [], False
    for name, (start, count, size) in TABLES.items():
        rows = doc.get(name, [])
        if not isinstance(rows, list):
            raise ValueError(f'{name}: 배열이어야 함')
        seen = set()
        for row in rows:
            allowed = {'index', *decode(name, bytes(size))}
            fields(row, allowed, name)
            i = integer(row.get('index'), count - 1, 'index')
            if i in seen:
                raise ValueError(f'{name}: 중복 index {i}')
            seen.add(i)
            addr = start + i * size
            old = read(rom, addr, size)
            new = encode(name, old, {k: v for k, v in row.items() if k != 'index'})
            current[name][i] = {'index': i, **decode(name, new)}
            if name not in ('chests', 'chest_maps') and old[:4] != new[:4]:
                positions.append(current[name][i])
            map_changed |= name == 'chest_maps' and new != old
            out.append((addr, new, old, f'{name} {i}'))
    validate_tables(rom, current, map_changed)
    dimensions = {}
    for row in positions:
        key = row['group'], row['map']
        if key not in dimensions:
            dimensions[key] = map_dimensions(rom, *key)
        width, height = dimensions[key]
        if row['x'] >= width or row['y'] >= height:
            raise ValueError(f'좌표가 맵 {width}×{height} 밖')
    return out


def patch(rom, doc):
    return {'format': 'dq5patch/1', 'name': 'chest-rewards', 'writes': [
        {'at': f'{addr >> 16:02X}:{addr & 0xFFFF:04X}', 'hex': new.hex(' '), 'orig': old.hex(' '), 'note': note}
        for addr, new, old, note in edits(rom, doc) if new != old]}


def check(rom, doc=None):
    source = dump(rom) if doc is None else doc
    rows = edits(rom, source)
    data = bytearray(rom.d)
    for addr, new, _, _ in rows:
        data[lorom(addr):lorom(addr) + len(new)] = new
    result = dump(Rom(data))
    for name in TABLES:
        for row in source.get(name, []):
            if any(result[name][row['index']][key] != value for key, value in row.items()):
                raise ValueError(f'{name}: 쓴 뒤 읽은 값이 다름')
    validate_tables(Rom(data), result, True)
    if doc is None and data != rom.d:
        raise ValueError('원본을 다시 쓴 바이트가 다름')
    print(f'고정 항목 {sum(t[1] for t in TABLES.values())}개, '
          f'{sum(t[1] * t[2] for t in TABLES.values())}바이트; 다시 읽기 일치, 맵 83개 상자 수 일치')


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('rom', type=Path)
    subs = p.add_subparsers(dest='command', required=True)
    d = subs.add_parser('dump')
    d.add_argument('-o', '--out', type=Path, required=True)
    w = subs.add_parser('patch')
    w.add_argument('source', type=Path)
    w.add_argument('-o', '--out', type=Path, required=True)
    c = subs.add_parser('check')
    c.add_argument('source', type=Path, nargs='?')
    args = p.parse_args()
    try:
        rom = Rom(args.rom.read_bytes())
        doc = json.loads(args.source.read_text(encoding='utf-8')) if getattr(args, 'source', None) else None
        if getattr(args, 'source', None):
            fields(doc, {'format', *TABLES}, '문서')
        if args.command == 'check':
            check(rom, doc)
        else:
            result = dump(rom) if args.command == 'dump' else patch(rom, doc)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            print(f'{args.command} → {args.out}')
        return 0
    except (ValueError, OSError, IndexError) as error:
        print(f'오류: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
