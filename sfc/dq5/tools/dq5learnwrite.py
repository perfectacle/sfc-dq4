"""DQ5 사람·몬스터의 주문 습득과 필드/전투 주문 목록을 쓴다.

23:ECE3의 사람 습득 표와 23:ECEA의 몬스터 표, 21:9C92·9D03의 목록 포인터를 따른다.
기존 항목 수와 포인터는 유지한다. 형식은 docs/dq5-data-format.md의 주문 습득 절.
"""
import argparse
import json
import sys
from pathlib import Path

from dq5map import Rom, lorom

FORMAT = 'dq5learn/1'
GROUPS = {'person': (11, 0x23B819, 0x23B978, 0), 'monster': (42, 0x23B979, 0x23BD53, 11)}
TABLES = {'field': 0x23BD53, 'battle': 0x23BDBD}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def keys(value, allowed, name):
    require(isinstance(value, dict), f'{name}: 객체가 필요함')
    require(not value.keys() - set(allowed), f'{name}: 지원하지 않는 필드 {value.keys() - set(allowed)}')


def integer(value, low, high, name):
    require(type(value) is int and low <= value <= high, f'{name}: {low}~{high} 정수여야 함')
    return value


def read(rom, address, count):
    off = lorom(address)
    raw = bytes(rom.d[off:off + count])
    require(len(raw) == count, '입력 롬이 표보다 짧음')
    return raw


def layout(rom):
    rows = {}
    for kind, (count, start, end, offset) in GROUPS.items():
        address = start
        for index in range(count):
            n = read(rom, address, 1)[0]
            require(address + 1 + n * 4 <= end, '습득 표가 원본 영역을 넘음')
            parts = {'learn': (address, read(rom, address, 1 + n * 4))}
            for name, table in TABLES.items():
                pointer = 0x230000 | int.from_bytes(read(rom, table + (offset + index) * 2, 2), 'little')
                require(0x23BE27 <= pointer < 0x23C014, '주문 목록 포인터가 원본 영역 밖임')
                size = read(rom, pointer, 1)[0]
                require(size <= (8 if name == 'field' else 12) and pointer + size + 1 <= 0x23C014,
                        '주문 목록 길이가 원본 영역을 넘음')
                parts[name] = (pointer, read(rom, pointer, size + 1))
            rows[kind, index] = parts
            address += 1 + n * 4
        require(address == end, '습득 표 끝이 원본과 다름')
    return rows


def decode(parts):
    raw = parts['learn'][1]
    learn = []
    for pos in range(1, len(raw), 4):
        mask = int.from_bytes(raw[pos + 1:pos + 4], 'little')
        require(mask < 1 << 20, '지원하지 않는 습득 상위 비트')
        learn.append({'level': raw[pos], 'field_slots': [i for i in range(8) if mask & (1 << i)],
                      'battle_slots': [i for i in range(12) if mask & (1 << (i + 8))]})
    return {'learn': learn, **{name: list(parts[name][1][1:]) for name in TABLES}}


def dump(rom):
    return {'format': FORMAT, 'characters': [dict(kind=kind, index=index, **decode(parts))
                                            for (kind, index), parts in layout(rom).items()]}


def encode(old, change):
    result = old | {k: v for k, v in change.items() if k in ('learn', 'field', 'battle')}
    for name in TABLES:
        values = result[name]
        require(isinstance(values, list) and len(values) == len(old[name]), f'{name}: 원본 목록 길이를 유지해야 함')
        for value in values:
            integer(value, 0x27 if name == 'field' else 1, 0x38 if name == 'field' else 0xAA, name)
            require(name != 'field' or value not in (0x2A, 0x2B, 0x30, 0x31), '필드에서 실행할 수 없는 주문')
    learn = result['learn']
    require(isinstance(learn, list) and len(learn) == len(old['learn']), 'learn: 원본 습득 항목 수를 유지해야 함')
    raw = bytearray([len(learn)])
    previous = 0
    for row, before in zip(learn, old['learn']):
        keys(row, ('level', 'field_slots', 'battle_slots'), 'learn 항목')
        require(set(row) == {'level', 'field_slots', 'battle_slots'}, 'learn 항목의 필드가 빠짐')
        level = integer(row['level'], 1, 99, 'level')
        require(level > previous, '습득 레벨은 중복 없이 오름차순이어야 함')
        # 습득 루틴은 레벨업 때만 같은 레벨을 찾으므로, 새로 레벨 1로 옮긴 항목은 배울 기회가 없다.
        require(level != 1 or before['level'] == 1, '원본이 레벨 1이 아닌 항목은 레벨 1로 옮길 수 없음')
        previous = level
        mask = 0
        for name, shift in (('field', 0), ('battle', 8)):
            slots = row[name + '_slots']
            require(isinstance(slots, list), '슬롯은 배열이어야 함')
            seen = set()
            for slot in slots:
                integer(slot, 0, len(result[name]) - 1, name + ' slot')
                require(slot not in seen, '중복 습득 슬롯')
                seen.add(slot)
                mask |= 1 << (shift + slot)
        require(mask != 0, '습득 슬롯이 비었음')
        raw.extend(bytes([level]) + mask.to_bytes(3, 'little'))
    return {'learn': bytes(raw), **{name: bytes([len(result[name]), *result[name]]) for name in TABLES}}


def patch(rom, doc):
    keys(doc, ('format', 'characters'), '문서')
    require(doc.get('format') == FORMAT and isinstance(doc.get('characters'), list), 'format/characters가 잘못됨')
    original = layout(rom)
    changes = {}
    for row in doc['characters']:
        keys(row, ('kind', 'index', 'learn', 'field', 'battle'), '인물')
        kind = row.get('kind')
        require(isinstance(kind, str) and kind in GROUPS, 'kind는 person/monster여야 함')
        index = integer(row.get('index'), 0, GROUPS[kind][0] - 1, 'index')
        key = kind, index
        require(key not in changes, '중복 인물')
        changes[key] = encode(decode(original[key]), row)
    users = {}
    for key, parts in original.items():
        for name, (address, raw) in parts.items():
            users.setdefault((address, len(raw)), []).append((key, name))
    expected, before = {}, {}
    for key, parts in original.items():
        for name, (address, old) in parts.items():
            raw = changes.get(key, {}).get(name, old)
            if raw != old:
                for user, part in users[address, len(old)]:
                    require(user in changes and changes[user][part] == raw,
                            f'공유 목록 {address:06X}: 모든 사용자에 같은 값을 지정해야 함')
            for i, value in enumerate(raw):
                pos = address + i
                require(pos not in expected or expected[pos] == value,
                        f'공유 바이트 {pos:06X}: 다른 목록의 값/개수와 충돌함')
                expected[pos], before[pos] = value, old[i]
    changed = sorted(pos for pos in expected if expected[pos] != before[pos])
    writes = []
    while changed:
        start = changed[0]
        end = start + 1
        while end in expected and expected[end] != before[end]:
            end += 1
        writes.append({'at': f'{start >> 16:02X}:{start & 0xFFFF:04X}',
                       'hex': bytes(expected[p] for p in range(start, end)).hex(' '),
                       'orig': bytes(before[p] for p in range(start, end)).hex(' '), 'note': '주문 습득·목록'})
        changed = [pos for pos in changed if pos >= end]
    return {'format': 'dq5patch/1', 'name': 'learn', 'writes': writes}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('rom', type=Path)
    ap.add_argument('command', choices=('dump', 'patch', 'check'))
    ap.add_argument('source', nargs='?', type=Path)
    ap.add_argument('-o', '--out', type=Path)
    args = ap.parse_args()
    try:
        rom = Rom(args.rom.read_bytes())
        require(args.command != 'dump' or args.source is None, 'dump에는 입력 파일을 주지 않음')
        if args.command == 'dump':
            result = dump(rom)
        else:
            doc = json.loads(args.source.read_text()) if args.source else dump(rom)
            require(args.command != 'patch' or args.source is not None, 'patch에는 입력 파일이 필요함')
            result = patch(rom, doc)
            if args.command == 'check':
                from dq5build import build, parse_at
                writes = [(parse_at(w['at'])[0], bytes.fromhex(w['hex']), bytes.fromhex(w['orig']), w['note'])
                          for w in result['writes']]
                rebuilt, _ = build(rom.d, [('learn', 2, writes)], 2)
                after = Rom(rebuilt)
                require(not patch(after, doc)['writes'], '빌더 적용 후 입력과 불일치')
                if args.source is None:
                    require(not result['writes'], '원본 왕복 불일치')
                print(f'인물 {len(doc["characters"])}종, 쓰기 {len(result["writes"])}개 검사 통과')
                return 0
        text = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(text, encoding='utf-8')
        else:
            print(text, end='')
        return 0
    except (OSError, ValueError) as error:
        print(f'오류: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
