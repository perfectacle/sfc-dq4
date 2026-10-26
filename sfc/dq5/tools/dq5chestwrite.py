"""DQ5 보물상자·조사 보상의 고정 표 쓰기.

sfc/dq5/docs/dq5-map-format.md의 보물상자 형식(25:FAB0, 12:FB9D·E6BE·FCDD·FD46)과 필드 조사(12:E5F2).
일반 상자의 좌표와 열림 비트는 맵 셀 순서·상자 번호에서 나온다. chest_maps는
기존 맵 슬롯의 연결/개수만 바꾸며 총 상자 수를 유지한다. 나머지 표는 좌표·보상·
플래그를 직접 바꾼다. 검색 우선순위·목록 길이·미사용 바이트·종료자는 보존한다. field는
코드에 박힌 보상 즉시값만 같은 길이로 바꾸고, 좌표·플래그·명령 바이트는 보존한다.

  python sfc/dq5/tools/dq5chestwrite.py rom/dq5.sfc dump -o work/chests.json
  python sfc/dq5/tools/dq5chestwrite.py rom/dq5.sfc patch work/chests.json -o work/chests.patch.json
  python sfc/dq5/tools/dq5chestwrite.py rom/dq5.sfc check [work/chests.json]

JSON format=dq5chest/1. chests[{index,reward}], chest_maps[{index,group,map,count}],
search/foot/ahead/lower[{index,group,map,x,y,reward,flag_index,mask}]. foot만 layer를 받는다.
field[{index:0,reward}]. dump는 x,y,width,height(필드 8픽셀 칸)·flag_index·mask도 내지만 바꿀 수 없다.
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
SECTIONS = {*TABLES, 'field'}
FIELD_CALL, FIELD_CODE = 0x12E5A7, 0x12E5F2
# 12:E5F2 의 명령 바이트. ?? 는 조건 플래그(21A5.2·21AA.0)이고, 이름 붙은 자리는 읽는 즉시값이다
# (x·y 시작, X·Y 끝(미포함), r 보상, i·m 열림 시험과 기록의 번호·마스크). 0·1 은 하위·상위 바이트
FIELD_TEMPLATE = ('C2 20 00 0B ?? ?? F0 3D A5 B6 C9 x0 x1 90 36 C9 X0 X1 B0 31 A5 B8 C9 y0 y1 90 2A C9 Y0 Y1 '
                  'B0 25 00 0B m0 i0 D0 1F 00 0B ?? ?? F0 19 A9 r0 r1 8D 73 1E E2 20 A9 i1 8D 80 1E A9 m1 '
                  '8D 81 1E').split()


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


def read_field(rom):
    if read(rom, FIELD_CALL, 3) != bytes.fromhex('20 F2 E5'):
        raise ValueError('field: 12:E5A7 이 12:E5F2 를 부르지 않음')
    raw = read(rom, FIELD_CODE, len(FIELD_TEMPLATE))
    for i, token in enumerate(FIELD_TEMPLATE):
        if all(c in '0123456789ABCDEF' for c in token) and raw[i] != int(token, 16):
            raise ValueError(f'field: 12:{(FIELD_CODE + i) & 0xFFFF:04X} 명령 바이트가 다름')
    decode_field(raw)
    return raw


def decode_field(raw):
    pick = {token: raw[i] for i, token in enumerate(FIELD_TEMPLATE)}
    word = lambda key: pick[key + '0'] | pick[key + '1'] << 8
    if (pick['i0'], pick['m0']) != (pick['i1'], pick['m1']):
        raise ValueError('field: 열림 시험과 기록 플래그가 다름')
    if word('X') <= word('x') or word('Y') <= word('y'):
        raise ValueError('field: 칸 범위의 끝이 시작보다 커야 함')
    return {'x': word('x'), 'y': word('y'), 'width': word('X') - word('x'), 'height': word('Y') - word('y'),
            'reward': word('r'), 'flag_index': pick['i0'], 'mask': pick['m0']}


def encode_field(raw, changes):
    old = decode_field(raw)
    fields(changes, set(old), 'field')
    # 01:9FF9~A035·A05D~ 의 빛나는 풀 블록 코드가 같은 칸과 21B3.4·21AA.0 을 따로 들고 있어 함께 바뀌지 않는다
    if any(changes[key] != old[key] for key in changes.keys() - {'reward'}):
        raise ValueError('field: reward만 바꿀 수 있음(좌표·플래그는 필드 빛 블록 코드와 짝이 맞아야 함)')
    reward = integer(changes.get('reward', old['reward']), 65535, 'reward')
    if reward > 0xCFFF:
        raise ValueError('field: reward는 물건(0000~00FF)·금화(0100~CFFF)만 받음')
    out = bytearray(raw)
    out[FIELD_TEMPLATE.index('r0')] = reward & 0xFF
    out[FIELD_TEMPLATE.index('r1')] = reward >> 8
    return bytes(out)


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


def dump(rom, field=True):
    layout(rom)
    # 필드 코드가 다른 패치로 바뀐 롬에서도 표만 고치는 입력은 받도록, field 를 쓰지 않으면 읽지 않는다
    doc = {'format': FORMAT, **{name: [{'index': i, **decode(name, read(rom, start + i * size, size))}
                                       for i in range(count)] for name, (start, count, size) in TABLES.items()}}
    if field:
        doc['field'] = [{'index': 0, **decode_field(read_field(rom))}]
    return doc


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
    fields(doc, {'format', *SECTIONS}, '문서')
    if doc.get('format') != FORMAT:
        raise ValueError(f'format={FORMAT}이 필요함')
    current = dump(rom, 'field' in doc)
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
    out += field_edits(rom, doc.get('field', []))
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


def field_edits(rom, rows):
    if not isinstance(rows, list) or len(rows) > 1:
        raise ValueError('field: 항목 하나까지의 배열이어야 함')
    if not rows:
        return []
    fields(rows[0], {'index', *decode_field(read_field(rom))}, 'field')
    integer(rows[0].get('index'), 0, 'index')
    old = read_field(rom)
    new = encode_field(old, {k: v for k, v in rows[0].items() if k != 'index'})
    out, i = [], 0
    while i < len(new):
        if new[i] == old[i]:
            i += 1
            continue
        j = i
        while j < len(new) and new[j] != old[j]:
            j += 1
        out.append((FIELD_CODE + i, new[i:j], old[i:j], 'field 0'))
        i = j
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
    result = dump(Rom(data), 'field' in source)
    for name in SECTIONS:
        for row in source.get(name, []):
            if any(result[name][row['index']][key] != value for key, value in row.items()):
                raise ValueError(f'{name}: 쓴 뒤 읽은 값이 다름')
    validate_tables(Rom(data), result, True)
    if doc is None and data != rom.d:
        raise ValueError('원본을 다시 쓴 바이트가 다름')
    print(f'고정 항목 {sum(t[1] for t in TABLES.values())}개, '
          f'{sum(t[1] * t[2] for t in TABLES.values())}바이트와 필드 조사 1곳; 다시 읽기 일치, 맵 83개 상자 수 일치')


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
            fields(doc, {'format', *SECTIONS}, '문서')
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
