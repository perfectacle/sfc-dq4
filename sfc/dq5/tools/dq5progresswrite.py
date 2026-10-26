"""DQ5 성장·조우 구역·상점의 고정 슬롯 쓰기.

형식은 sfc/dq5/docs/dq5-data-format.md의 레벨업 성장(23:EB50), 전투 조우(23:E7C2),
상점(06:F49C). 성장 53개는 각 0x50바이트, 조우 85개는 각 22바이트이며 상점은
기존 목록의 키·순서·품목 수를 유지한다. 지정하지 않은 필드와 미사용 비트는 보존한다.

  python sfc/dq5/tools/dq5progresswrite.py rom/dq5.sfc dump -o work/progress.json
  python sfc/dq5/tools/dq5progresswrite.py rom/dq5.sfc patch work/progress.json -o work/progress.dq5patch.json
  python sfc/dq5/tools/dq5progresswrite.py rom/dq5.sfc check

JSON format은 dq5progress/1. growth의 kind는 person/monster, index는 종류 내 번호.
stats는 hp/mp/strength/agility/wisdom/luck/resilience의 활성 값(레벨1, 꺾이는 레벨들, 레벨99).
HP·MP는 레벨1 외에는 저장값의 두 배로 읽힌다. breaks 길이를 바꾸면 multipliers와 모든 stats가 필요하다.
encounters의 slots는 0~9만이며 칸10은 fixed:{weight,group}이다. shops는 kind와 종류 내 index로 식별한다.
medal_prices·coin_prices는 각각 여섯 값. 모든 숫자는 JSON 정수, 플래그 둘은 JSON bool이다.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5encounter import AREAS, AREA_COUNT, AREA_SIZE, FIXED_COUNT  # noqa: E402
from dq5growth import MONSTERS, PEOPLE, RECORD, STAT_OFFSETS  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402
from dq5shop import COIN_PRICES, END, ITEMS, LISTS, MEDAL_PRICES  # noqa: E402

FORMAT = 'dq5progress/1'
GROWTH = {'person': (PEOPLE, 11), 'monster': (MONSTERS, 42)}
STATS = ('hp', 'mp', 'strength', 'agility', 'wisdom', 'luck', 'resilience')
SHOP_COUNTS = (11, 15, 17, 5)


def integer(value, maximum, name):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError(f'{name}: 0~{maximum} 정수여야 함')
    return value


def boolean(value, name):
    if type(value) is not bool:
        raise ValueError(f'{name}: true/false여야 함')
    return int(value)


def fields(value, allowed, name):
    if not isinstance(value, dict):
        raise ValueError(f'{name}: JSON 객체여야 함')
    if value.keys() - allowed:
        raise ValueError(f'{name}: 모르는 필드 {sorted(value.keys() - allowed)}')


def array(value, count, maximum, name):
    if not isinstance(value, list) or len(value) != count:
        raise ValueError(f'{name}: {count}개 값의 배열이어야 함')
    return [integer(v, maximum, name) for v in value]


def read(rom, addr, size):
    off = lorom(addr)
    raw = bytes(rom.d[off:off + size])
    if len(raw) != size:
        raise ValueError(f'{addr:06X}: 롬에 {size}바이트가 없음')
    return raw


def growth_fields(raw):
    n = integer(raw[0], 7, '원본 꺾이는 레벨 수')
    return {'breaks': list(raw[2:2 + n]), 'exp2': raw[1], 'multipliers': list(raw[9:10 + n]),
            'stats': {name: list(raw[off:off + n + 1]) + [raw[off + 8]] for name, off in zip(STATS, STAT_OFFSETS)}}


def encode_growth(raw, change):
    old = growth_fields(raw)
    breaks = change.get('breaks', old['breaks'])
    if not isinstance(breaks, list) or len(breaks) > 7:
        raise ValueError('breaks: 최대 7개 레벨 배열이어야 함')
    breaks = [integer(v, 99, '꺾이는 레벨') for v in breaks]
    if breaks != old['breaks'] and (any(v < 2 for v in breaks) or any(a >= b for a, b in zip(breaks, breaks[1:]))):
        raise ValueError('breaks: 2~99 사이의 엄격한 오름차순이어야 함')
    n = len(breaks)
    changed_stats = change.get('stats', {})
    fields(changed_stats, set(STATS), 'stats')
    if n != len(old['breaks']) and ('multipliers' not in change or set(changed_stats) != set(STATS)):
        raise ValueError('breaks 개수를 바꾸면 multipliers와 능력치 일곱을 모두 지정해야 함')
    multipliers = array(change.get('multipliers', old['multipliers']), n + 1, 255, 'multipliers')
    out = bytearray(raw)
    out[0], out[1] = n, integer(change.get('exp2', old['exp2']), 255, 'exp2')
    out[2:2 + n], out[9:10 + n] = bytes(breaks), bytes(multipliers)
    for stat, (name, off) in enumerate(zip(STATS, STAT_OFFSETS)):
        values = array(changed_stats.get(name, old['stats'][name]), n + 2, 255, name)
        if values != old['stats'][name] or breaks != old['breaks']:
            effective = [values[0]] + [v * (2 if stat < 2 else 1) for v in values[1:]]
            if any(a > b for a, b in zip(effective, effective[1:])):
                raise ValueError(f'{name}: 낮아지는 능력치 곡선은 쓸 수 없음')
        out[off:off + n + 1], out[off + 8] = bytes(values[:-1]), values[-1]
    return bytes(out)


def encounter_fields(raw):
    return {'level': raw[0],
            'slots': [{'index': i, 'weight': raw[1 + i] & 7, 'count_code': raw[1 + i] >> 3 & 7,
                       'monster': raw[12 + i]} for i in range(10)],
            'fixed': {'weight': raw[11] & 7, 'group': raw[11] >> 3},
            'species_weights': [raw[1 + i] >> 6 for i in range(3)],
            'rate_index': sum((raw[5 + i] >> 7) << i for i in range(3)),
            'flag_1000': raw[4] >> 6, 'flag_1010': bool(raw[8] & 128), 'fixed_night_only': bool(raw[9] & 128)}


def encode_encounter(raw, change):
    out = bytearray(raw)
    if 'level' in change:
        out[0] = integer(change['level'], 255, 'level')
    slots = change.get('slots', [])
    if not isinstance(slots, list):
        raise ValueError('slots: 배열이어야 함')
    seen = set()
    for slot in slots:
        fields(slot, {'index', 'weight', 'count_code', 'monster'}, 'slot')
        i = integer(slot.get('index'), 9, 'slot index')
        if i in seen:
            raise ValueError(f'중복 slot {i}')
        seen.add(i)
        if 'weight' in slot:
            out[1 + i] = out[1 + i] & 0xF8 | integer(slot['weight'], 7, 'weight')
        if 'count_code' in slot:
            out[1 + i] = out[1 + i] & 0xC7 | integer(slot['count_code'], 7, 'count_code') << 3
        if 'monster' in slot:
            out[12 + i] = integer(slot['monster'], 235, 'monster')
    if 'fixed' in change:
        value = change['fixed']
        fields(value, {'weight', 'group'}, 'fixed')
        if 'weight' in value:
            out[11] = out[11] & 0xF8 | integer(value['weight'], 7, 'fixed weight')
        if 'group' in value:
            out[11] = out[11] & 7 | integer(value['group'], FIXED_COUNT - 1, 'fixed group') << 3
    if 'species_weights' in change:
        for i, value in enumerate(array(change['species_weights'], 3, 3, 'species_weights')):
            out[1 + i] = out[1 + i] & 0x3F | value << 6
    if 'rate_index' in change:
        value = integer(change['rate_index'], 7, 'rate_index')
        for i in range(3):
            out[5 + i] = out[5 + i] & 0x7F | ((value >> i) & 1) << 7
    for name, at, mask, shift in (('flag_1000', 4, 0x3F, 6), ('flag_1010', 8, 0x7F, 7), ('fixed_night_only', 9, 0x7F, 7)):
        if name in change:
            value = integer(change[name], 3, name) if name == 'flag_1000' else boolean(change[name], name)
            out[at] = out[at] & mask | value << shift
    if not sum(v & 7 for v in out[1:12]):
        raise ValueError('조우 무게 합이 0일 수 없음')
    if sum(v & 7 for v in out[1:6]) and not sum(v >> 6 for v in out[1:4]):
        raise ValueError('여러 종 무리의 종 수 무게 합이 0일 수 없음')
    return bytes(out)


def shop_records(rom):
    ptrs = read(rom, LISTS, 8)
    starts = [0x040000 | int.from_bytes(ptrs[k:k + 2], 'little') for k in range(0, 8, 2)] + [END]
    if starts[0] != LISTS + 8 or any(a >= b for a, b in zip(starts, starts[1:])):
        raise ValueError('상점 종류 포인터의 원본 범위가 다름')
    out = {}
    for kind, count in enumerate(SHOP_COUNTS):
        addr, end = starts[kind:kind + 2]
        for index in range(count):
            if addr >= end:
                raise ValueError('상점 목록이 부족함')
            key = read(rom, addr, 1)[0]
            cursor = addr + 1
            while cursor < end and read(rom, cursor, 1)[0] != 0xFF:
                integer(read(rom, cursor, 1)[0], ITEMS - 1, '원본 상점 물건')
                cursor += 1
            if cursor >= end or cursor == addr + 1:
                raise ValueError('상점 목록의 종료자가 없거나 품목이 없음')
            out[kind, index] = (addr, read(rom, addr, cursor - addr + 1))
            addr = cursor + 1
        if addr != end:
            raise ValueError('상점 목록 수가 원본과 다름')
    return out


def dump(rom):
    return {'format': FORMAT,
            'growth': [{'kind': kind, 'index': i, **growth_fields(read(rom, base + i * RECORD, RECORD))}
                       for kind, (base, count) in GROWTH.items() for i in range(count)],
            'encounters': [{'index': i, **encounter_fields(read(rom, AREAS + i * AREA_SIZE, AREA_SIZE))} for i in range(AREA_COUNT)],
            'shops': [{'kind': kind, 'index': i, 'key': raw[0], 'items': list(raw[1:-1])}
                      for (kind, i), (_, raw) in shop_records(rom).items()],
            'medal_prices': list(read(rom, MEDAL_PRICES, 6)),
            'coin_prices': [int.from_bytes(read(rom, COIN_PRICES + 3 * i, 3), 'little') for i in range(6)]}


def edits(rom, doc):
    fields(doc, {'format', 'growth', 'encounters', 'shops', 'medal_prices', 'coin_prices'}, '문서')
    if doc.get('format') != FORMAT:
        raise ValueError(f'format은 {FORMAT}이어야 함')
    out = []
    for section in ('growth', 'encounters', 'shops'):
        rows = doc.get(section, [])
        if not isinstance(rows, list):
            raise ValueError(f'{section}: 배열이어야 함')
        seen = set()
        shops = shop_records(rom) if section == 'shops' and rows else {}
        for row in rows:
            if section == 'growth':
                fields(row, {'kind', 'index', 'breaks', 'exp2', 'multipliers', 'stats'}, section)
                kind = row.get('kind')
                if not isinstance(kind, str) or kind not in GROWTH:
                    raise ValueError('growth kind는 person/monster여야 함')
                base, count = GROWTH[kind]
                index = integer(row.get('index'), count - 1, 'growth index')
                key, addr = (kind, index), base + index * RECORD
                raw = read(rom, addr, RECORD)
                new = encode_growth(raw, row)
            elif section == 'encounters':
                fields(row, {'index', 'level', 'slots', 'fixed', 'species_weights', 'rate_index', 'flag_1000',
                             'flag_1010', 'fixed_night_only'}, section)
                key = integer(row.get('index'), AREA_COUNT - 1, 'encounter index')
                addr = AREAS + key * AREA_SIZE
                raw = read(rom, addr, AREA_SIZE)
                new = encode_encounter(raw, row)
            else:
                fields(row, {'kind', 'index', 'key', 'items'}, section)
                kind = integer(row.get('kind'), 3, 'shop kind')
                index = integer(row.get('index'), SHOP_COUNTS[kind] - 1, 'shop index')
                key = kind, index
                addr, raw = shops[key]
                if 'key' in row and integer(row['key'], 255, 'shop key') != raw[0]:
                    raise ValueError('상점 키는 바꿀 수 없음')
                items = array(row.get('items', list(raw[1:-1])), len(raw) - 2, ITEMS - 1, 'items')
                new = bytes([raw[0], *items, 255])
            if key in seen:
                raise ValueError(f'{section}: 중복 항목 {key}')
            seen.add(key)
            out.append((addr, new, raw, f'{section} {key}'))
    for name, addr, size, maximum in (('medal_prices', MEDAL_PRICES, 1, 255), ('coin_prices', COIN_PRICES, 3, 0xFFFFFF)):
        if name in doc:
            values = array(doc[name], 6, maximum, name)
            old = read(rom, addr, 6 * size)
            out.append((addr, b''.join(v.to_bytes(size, 'little') for v in values), old, name))
    return out


def patch(rom, doc, name='progress'):
    return {'format': 'dq5patch/1', 'name': name, 'writes': [
        {'at': f'{addr >> 16:02X}:{addr & 0xFFFF:04X}', 'hex': new.hex(' '), 'orig': old.hex(' '), 'note': note}
        for addr, new, old, note in edits(rom, doc) if new != old]}


def check(rom):
    rows = edits(rom, dump(rom))
    bad = sum(new != old for _, new, old, _ in rows)
    print(f'성장 53개·조우 {AREA_COUNT}개·상점 48개·교환 값 12개: {sum(len(old) for _, _, old, _ in rows)}바이트, 다른 항목 {bad}개')
    return bool(bad)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('rom')
    sub = parser.add_subparsers(dest='command', required=True)
    export = sub.add_parser('dump')
    export.add_argument('-o', '--out', required=True)
    write = sub.add_parser('patch')
    write.add_argument('source')
    write.add_argument('-o', '--out', required=True)
    write.add_argument('--name', default='progress')
    sub.add_parser('check')
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
        return 0
    except (ValueError, OSError) as error:
        print(f'오류: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
