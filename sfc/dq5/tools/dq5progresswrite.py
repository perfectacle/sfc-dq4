"""DQ5 성장·조우 구역·상점의 고정 슬롯 쓰기.

형식은 sfc/dq5/docs/dq5-data-format.md의 레벨업 성장(23:EB50), 전투 조우(23:E7C2),
상점(06:F49C). 성장 53개는 각 0x50바이트, 조우 85개는 각 22바이트다. 상점은 품목 수를 바꾸거나
종류 끝에 목록을 더할 수 있고, 네 종류를 다시 늘어놓아 원래 자리에 넘치면 --shop-at 으로 옮긴다.
지정하지 않은 필드와 미사용 비트는 보존한다.

  python sfc/dq5/tools/dq5progresswrite.py rom/dq5.sfc dump -o work/progress.json
  python sfc/dq5/tools/dq5progresswrite.py rom/dq5.sfc patch work/progress.json -o work/progress.dq5patch.json [--shop-at 0B:FBB0]
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
# 06:F49C(키 찾기)·06:F545(품목 읽기)가 DB 로 두는 뱅크 즉값과 종류 포인터 표 주소 피연산자.
SHOP_BANK = (0x06F4AE, 0x06F54E)
SHOP_TABLE = (0x06F4BA, 0x06F50D)
# 7번째부터는 고를 수는 있지만 목록 창 밖(비교 창 아래)이라 보이지 않는다.
SHOP_ITEMS_MAX = 6


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


def shop_table(rom):
    banks = {read(rom, at, 1)[0] for at in SHOP_BANK}
    tables = {int.from_bytes(read(rom, at, 2), 'little') for at in SHOP_TABLE}
    if len(banks) != 1 or len(tables) != 1:
        raise ValueError('상점 검색 루틴의 뱅크·표 주소가 서로 다름')
    return banks.pop() << 16 | tables.pop()


def shop_records(rom):
    """종류마다 [키][품목…][FF] 목록. 마지막 종류는 키 자리의 FF 나 원래 표 끝에서 끝난다."""
    table = shop_table(rom)
    bank = table & 0xFF0000
    ptrs = read(rom, table, 8)
    starts = [bank | int.from_bytes(ptrs[k:k + 2], 'little') for k in range(0, 8, 2)]
    limit = END if table == LISTS else bank + 0x10000
    if starts[0] != table + 8 or any(a >= b for a, b in zip(starts, starts[1:])):
        raise ValueError('상점 종류 포인터의 원본 범위가 다름')
    out = {}
    for kind, addr in enumerate(starts):
        end = starts[kind + 1] if kind < 3 else limit
        index = 0
        while addr < end and not (kind == 3 and read(rom, addr, 1)[0] == 0xFF):
            cursor = addr + 1
            while cursor < end and read(rom, cursor, 1)[0] != 0xFF:
                integer(read(rom, cursor, 1)[0], ITEMS - 1, '원본 상점 물건')
                cursor += 1
            if cursor >= end or cursor == addr + 1:
                raise ValueError('상점 목록의 종료자가 없거나 품목이 없음')
            out[kind, index] = (addr, read(rom, addr, cursor - addr + 1))
            addr, index = cursor + 1, index + 1
        if kind < 3 and addr != end:
            raise ValueError('상점 목록이 종류 경계에서 끝나지 않음')
    return out


def shop_layout(lists, at):
    """종류 포인터 4개와 목록들을 at 에 늘어놓은 바이트."""
    body, ptrs = bytearray(), bytearray()
    for kind in range(4):
        ptrs += ((at + 8 + len(body)) & 0xFFFF).to_bytes(2, 'little')
        for index in range(sum(1 for k, _ in lists if k == kind)):
            body += lists[kind, index]
    return bytes(ptrs + body)


def shop_writes(rom, changes, shop_at):
    """바뀐 목록을 넣어 다시 늘어놓고 (주소, 새 바이트, 원래 바이트 또는 None, 설명) 목록을 돌려준다."""
    records = shop_records(rom)
    lists = {key: raw for key, (_, raw) in records.items()} | changes
    table = shop_table(rom)
    region_end = END if table == LISTS else max(addr + len(raw) for addr, raw in records.values()) + 1
    if shop_at is None:
        layout = shop_layout(lists, table)
        size = region_end - table
        # 옮긴 자리는 마지막 종류의 끝을 키 자리 FF 로만 알 수 있어 한 바이트를 남긴다.
        if len(layout) > size - (0 if table == LISTS else 1):
            raise ValueError(f'상점 목록 {len(layout)}바이트가 자리 {size}바이트를 넘음(--shop-at 필요)')
        old = read(rom, table, size)
        return [(table, layout + b'\xff' * (size - len(layout)), old, 'shops')]
    bank = shop_at >> 16
    if not (bank <= 0x3F or 0x80 <= bank <= 0xBF) or shop_at & 0xFFFF < 0x8000:
        raise ValueError('--shop-at 은 WRAM 거울이 보이는 뱅크(00~3F·80~BF)의 8000 이상이어야 함')
    layout = shop_layout(lists, shop_at) + b'\xff'
    if (shop_at & 0xFFFF) + len(layout) > 0x10000:
        raise ValueError('옮긴 상점 목록이 뱅크를 넘음')
    out = [(shop_at, layout, None, 'shops relocated')]
    for at in SHOP_BANK:
        out.append((at, bytes([bank]), read(rom, at, 1), 'shop bank'))
    for at in SHOP_TABLE:
        out.append((at, (shop_at & 0xFFFF).to_bytes(2, 'little'), read(rom, at, 2), 'shop table'))
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


def edits(rom, doc, shop_at=None):
    fields(doc, {'format', 'growth', 'encounters', 'shops', 'medal_prices', 'coin_prices'}, '문서')
    if doc.get('format') != FORMAT:
        raise ValueError(f'format은 {FORMAT}이어야 함')
    out, shop_changes = [], {}
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
                count = sum(1 for k, _ in shops if k == kind)
                appended = sum(1 for k, _ in shop_changes if k == kind and (k, _) not in shops)
                index = integer(row.get('index'), count + appended, 'shop index')
                key = kind, index
                if key in shops:
                    raw = shops[key][1]
                    if 'key' in row and integer(row['key'], 255, 'shop key') != raw[0]:
                        raise ValueError('상점 키는 바꿀 수 없음')
                    shop_key, items = raw[0], row.get('items', list(raw[1:-1]))
                else:
                    # 키 자리의 FF 는 마지막 종류의 끝 표시라 새 목록 키로 쓸 수 없다.
                    shop_key, items = integer(row.get('key'), 254, 'new shop key'), row.get('items')
                if not isinstance(items, list) or not 1 <= len(items) <= SHOP_ITEMS_MAX:
                    raise ValueError(f'items: 1~{SHOP_ITEMS_MAX}개 물건 번호 배열이어야 함')
                items = [integer(v, ITEMS - 1, 'items') for v in items]
                if key in seen:
                    raise ValueError(f'{section}: 중복 항목 {key}')
                seen.add(key)
                shop_changes[key] = bytes([shop_key, *items, 255])
                continue
            if key in seen:
                raise ValueError(f'{section}: 중복 항목 {key}')
            seen.add(key)
            out.append((addr, new, raw, f'{section} {key}'))
    if shop_changes or shop_at is not None:
        out += shop_writes(rom, shop_changes, shop_at)
    for name, addr, size, maximum in (('medal_prices', MEDAL_PRICES, 1, 255), ('coin_prices', COIN_PRICES, 3, 0xFFFFFF)):
        if name in doc:
            values = array(doc[name], 6, maximum, name)
            old = read(rom, addr, 6 * size)
            out.append((addr, b''.join(v.to_bytes(size, 'little') for v in values), old, name))
    return out


def patch(rom, doc, name='progress', shop_at=None):
    writes = []
    for addr, new, old, note in edits(rom, doc, shop_at):
        if new == old:
            continue
        write = {'at': f'{addr >> 16:02X}:{addr & 0xFFFF:04X}', 'hex': new.hex(' '), 'note': note}
        if old is not None:
            write['orig'] = old.hex(' ')
        writes.append(write)
    return {'format': 'dq5patch/1', 'name': name, 'writes': writes}


def check(rom):
    rows = edits(rom, dump(rom))
    bad = sum(new != old for _, new, old, _ in rows)
    shops = len(shop_records(rom))
    print(f'성장 53개·조우 {AREA_COUNT}개·상점 {shops}개·교환 값 12개: {sum(len(old) for _, _, old, _ in rows)}바이트, 다른 항목 {bad}개')
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
    write.add_argument('--shop-at', help='상점 목록을 옮길 자리(예 0B:FBB0)')
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
                shop_at = None
                if args.shop_at:
                    bank, _, low = args.shop_at.partition(':')
                    shop_at = int(bank, 16) << 16 | int(low, 16)
                result = patch(rom, json.load(f), args.name, shop_at)
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
