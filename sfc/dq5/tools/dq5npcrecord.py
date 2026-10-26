"""DQ5 인물 레코드 필드와 등장 조건 표를 제자리에서 고친다.

형식: sfc/dq5/docs/dq5-map-format.md 의 「인물」. 엔트리 길이·인물 수·목록 순서는 그대로 두고,
좌표·방향·그림·대화 번호·층·이동·걸음·애니메이션 간격과 한 벌 엔트리의 낮/밤을 바꾼다.
기타 bit3-7, 첫 바이트 bit4-5, 두 벌 엔트리의 마스크처럼 뜻을 다 모르는 비트는 그대로 둔다.
조건 표는 12:8449(대체 목록)와 12:839C(인물을 놓지 않음)의 기존 항목만 고친다.

  python sfc/dq5/tools/dq5npcrecord.py rom/dq5.sfc dump -o work/npc-records.json
  python sfc/dq5/tools/dq5npcrecord.py rom/dq5.sfc patch work/npc-records.json -o work/npc-records.dq5patch.json
  python sfc/dq5/tools/dq5npcrecord.py rom/dq5.sfc check [work/npc-records.json]

dq5npcrelocate.py 로 목록을 옮기면 게임은 옮긴 사본을 읽으므로, 이 문서는 그 도구의 --records 로 넘긴다.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dq5map import Rom, lorom  # noqa: E402
from dq5mapwrite import all_maps  # noqa: E402
from dq5npc import (  # noqa: E402
    ALT_END, ALT_START, FACING_BY_XY, FIELDS, NO_NPC, OVERRIDE_LISTS, SHARED_BITS, all_lists,
    entry_size, list_entries, parse,
)

FORMAT = 'dq5npcrecord/1'
OVERRIDE_COUNT, NO_NPC_COUNT = 296, 43
FACINGS = ('up', 'right', 'down', 'left')     # 1E:DD9C 색인 순서(X bit7 << 1 | Y bit7)
TIMES = {0x80: 'day', 0x40: 'night', 0xC0: 'both'}
TIME_BITS = {'day': 0x80, 'night': 0x40}
VALUE_KEYS = ('x', 'y', 'facing', 'talk', 'gfx', 'layer', 'interval', 'speed', 'step', 'walk_anim', 'stand_anim')
ENTRY_KEYS = {'list', 'index', 'name', 'address', 'time', 'fields', 'day', 'night'}
CONDITION_KEYS = {'index', 'map', 'flag', 'when', 'mask'}


def cpu(addr):
    return f'{addr >> 16:02X}:{addr & 0xFFFF:04X}'


def address(value, name):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9A-Fa-f]{2}:[0-9A-Fa-f]{4}', value):
        raise ValueError(f'{name}: BB:AAAA 문자열이어야 함')
    return int(value.replace(':', ''), 16)


def integer(value, low, high, name):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{name}: {low}~{high} 정수여야 함')
    return value


def keys(value, allowed, name):
    if not isinstance(value, dict) or value.keys() - allowed:
        raise ValueError(f'{name}: 허용한 키 {sorted(allowed)}만 있는 객체여야 함')


def map_name(bc, bd):
    return f'{bc:02X}/{bd:02X}'


def map_number_raw(value):
    return tuple(int(v, 16) for v in value.split('/'))


def map_number(value, known):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9A-Fa-f]{2}/[0-9A-Fa-f]{2}', value):
        raise ValueError('map은 GG/MM 형태여야 함')
    result = tuple(int(v, 16) for v in value.split('/'))
    if result not in known:
        raise ValueError(f'원본 맵 목록에 없는 맵 {value}')
    return result


def raw(rom, addr, size):
    result = bytes(rom.d[lorom(addr):lorom(addr) + size])
    if len(result) != size:
        raise ValueError(f'{cpu(addr)}: 롬 범위 밖')
    return result


def offsets(data):
    """엔트리 바이트에서 시간대마다 필드 바이트의 오프셋. 12:8161(낮)·12:8227(밤)의 읽는 순서와 같다."""
    b0 = data[0]
    if b0 & 0xC0 != 0xC0:
        one = {'flags': 0, **{name: i + 1 for i, name in enumerate(FIELDS)},
               'extra': None if b0 & 0x10 else 7}
        return {'day': one, 'night': one}
    mask = data[1]
    night_flags = 0 if mask & 0x80 else 2
    pos = 1 if mask & 0x80 else 2
    day, night = {'flags': 0}, {'flags': night_flags}
    for name, bit in zip(FIELDS, SHARED_BITS):
        pos += 1
        day[name] = pos
        if not mask & bit:
            pos += 1
        night[name] = pos
    day['extra'] = None if b0 & 0x10 else pos + 1
    if not b0 & 0x10:
        pos += 1
    night['extra'] = None if data[night_flags] & 0x10 else pos + 1
    return {'day': day, 'night': night}


def decode(data, where):
    """한 시간대 필드 바이트 → 쓰기 값. 1E:DB44 가 인물 표에 넣는 뜻으로 푼다."""
    flags, misc, x, y = data[where['flags']], data[where['misc']], data[where['x']], data[where['y']]
    move = data[where['move']]
    value = {'x': x & 0x7F, 'y': (y & 0x7F) - (misc >> 7), 'facing': FACINGS[(x >> 7) << 1 | y >> 7],
             'talk': (flags & 0x0F) << 8 | data[where['talk']], 'gfx': data[where['gfx']],
             'layer': move & 3, 'interval': move >> 2 & 0x0F, 'speed': move >> 6, 'step': misc & 7}
    if where['extra'] is not None:
        value['walk_anim'], value['stand_anim'] = data[where['extra']] >> 4, data[where['extra']] & 0x0F
    return value


def encode(data, where, value, name):
    """쓰기 값 → {오프셋: 바이트}. 모르는 비트는 data 의 것을 둔다."""
    keys(value, set(VALUE_KEYS), name)
    if (where['extra'] is None) != ('walk_anim' not in value) or ('walk_anim' in value) != ('stand_anim' in value):
        raise ValueError(f'{name}: 추가 값이 없는 엔트리에는 walk_anim·stand_anim 을 쓸 수 없음(길이가 바뀜)')
    if value['facing'] not in FACINGS:
        raise ValueError(f'{name}: facing 은 {FACINGS} 가운데 하나')
    facing = FACINGS.index(value['facing'])
    misc = data[where['misc']] & 0xF8 | integer(value['step'], 0, 7, f'{name}.step')
    lift = misc >> 7
    x = integer(value['x'], 0, 127, f'{name}.x')
    y = integer(value['y'], 0, 127 - lift, f'{name}.y') + lift
    talk = integer(value['talk'], 0, 0xFFF, f'{name}.talk')
    out = {where['flags']: data[where['flags']] & 0xF0 | talk >> 8, where['talk']: talk & 0xFF,
           where['misc']: misc, where['x']: (facing >> 1) << 7 | x, where['y']: (facing & 1) << 7 | y,
           where['gfx']: integer(value['gfx'], 0, 255, f'{name}.gfx'),
           where['move']: integer(value['speed'], 0, 3, f'{name}.speed') << 6
           | integer(value['interval'], 0, 15, f'{name}.interval') << 2 | integer(value['layer'], 0, 3, f'{name}.layer')}
    if where['extra'] is not None:
        out[where['extra']] = (integer(value['walk_anim'], 0, 15, f'{name}.walk_anim') << 4
                               | integer(value['stand_anim'], 0, 15, f'{name}.stand_anim'))
    return out


def layout(rom):
    """원본 구조: 목록 {주소: (이름, [엔트리 주소])}, 대체 표·빈 맵 표 항목, 맵 목록, 대체 목록 시작점."""
    lists = {at: (name, [a for a, _ in list_entries(rom, at)]) for at, name in all_lists(rom)}
    overrides = []
    for i in range(OVERRIDE_COUNT):
        at = OVERRIDE_LISTS + i * 6
        overrides.append((at, raw(rom, at, 6)))
    if raw(rom, OVERRIDE_LISTS + OVERRIDE_COUNT * 6, 1) != b'\xff':
        raise ValueError('대체 목록 표의 원본 종료자가 없음')
    no_npc = []
    for i in range(NO_NPC_COUNT):
        at = NO_NPC + i * 4
        no_npc.append((at, raw(rom, at, 4)))
    if raw(rom, NO_NPC + NO_NPC_COUNT * 4, 1) != b'\xff':
        raise ValueError('빈 맵 표의 원본 종료자가 없음')
    alt_starts = {at for at in lists if ALT_START <= at < ALT_END}
    return lists, overrides, no_npc, set(all_maps(rom)), alt_starts


def entry_value(rom, entry, name, index, list_at):
    data = raw(rom, entry, entry_size(rom, entry))
    kind = TIMES.get(data[0] & 0xC0)
    if kind is None:
        raise ValueError(f'{cpu(entry)}: 시간대 비트가 00 인 엔트리')
    where = offsets(data)
    row = {'list': cpu(list_at), 'index': index, 'name': name, 'address': cpu(entry), 'time': kind}
    if kind == 'both':
        row['day'], row['night'] = decode(data, where['day']), decode(data, where['night'])
    else:
        row['fields'] = decode(data, where[kind])
    if any(part['y'] < 0 for part in (row.get('fields'), row.get('day'), row.get('night')) if part):
        raise ValueError(f'{cpu(entry)}: 기타 bit7 과 저장 Y 0 이 겹쳐 놓는 칸이 음수')
    return row


def condition_value(data, index, with_list):
    value = {'index': index, 'map': map_name(data[0], data[1]), 'flag': data[2] & 0x7F,
             'when': 'off' if data[2] & 0x80 else 'on', 'mask': data[3]}
    if with_list:
        value['list'] = cpu(0x100000 | data[4] | data[5] << 8)
    return value


def dump(rom):
    lists, overrides, no_npc, _, _ = layout(rom)
    entries = []
    for at, (name, rows) in lists.items():
        entries.extend(entry_value(rom, entry, name, i, at) for i, entry in enumerate(rows))
    return {'format': FORMAT, 'entries': entries,
            'overrides': [condition_value(data, i, True) for i, (_, data) in enumerate(overrides)],
            'no_npc': [condition_value(data, i, False) for i, (_, data) in enumerate(no_npc)]}


def entry_bytes(rom, entry, row, name):
    """엔트리 하나의 새 바이트(길이는 원본과 같음)."""
    data = bytearray(raw(rom, entry, entry_size(rom, entry)))
    original = bytes(data)
    kind = TIMES.get(data[0] & 0xC0)
    where = offsets(data)
    time = row.get('time', kind)
    if not isinstance(time, str):
        raise ValueError(f'{name}.time: day·night·both 문자열이어야 함')
    if kind == 'both':
        if time != 'both' or 'fields' in row:
            raise ValueError(f'{name}: 두 벌 엔트리는 time=both, day·night 로만 고침(낮/밤 전환은 길이가 바뀜)')
        times = ('day', 'night')
    else:
        if time not in TIME_BITS or 'day' in row or 'night' in row:
            raise ValueError(f'{name}: 한 벌 엔트리는 time=day|night, fields 로만 고침')
        times = ('fields',)
    # 빠진 시간대도 원본 값으로 인코딩해, 한쪽만 바꾼 공유 바이트를 충돌로 잡는다.
    owner = {}
    for part in times:
        where_part = where['day'] if part == 'fields' else where[part]
        base = decode(original, where_part)
        keys(row.get(part, {}), set(base), f'{name}.{part}')
        for at, value in encode(original, where_part, base | row.get(part, {}), f'{name}.{part}').items():
            if at in owner and owner[at][1] != value:
                # 기타 bit7 이 낮·밤에 다르면 같은 Y 바이트가 낮·밤에 한 칸 다른 y 로 풀린다.
                raise ValueError(f'{name}: 낮·밤이 공유하는 바이트 +{at}에 다른 값({owner[at][0]} {owner[at][1]:02X}·'
                                 f'{part} {value:02X})이 나옴; 공유 필드는 같은 바이트가 되게 둠')
            owner[at] = (part, value)
    for at, (_, value) in owner.items():
        data[at] = value
    if kind != 'both':
        data[0] = data[0] & 0x3F | TIME_BITS[time]
    return bytes(data)


def condition_bytes(old, row, known, alt_starts, with_list, name):
    value = condition_value(old, row['index'], with_list) | {k: v for k, v in row.items() if k != 'index'}
    bc, bd = map_number(value['map'], known)
    flag = integer(value['flag'], 0, 0x7F, f'{name}.flag')
    if value['when'] not in ('on', 'off'):
        raise ValueError(f'{name}.when: on 또는 off')
    if value['mask'] not in (1, 2, 4, 8, 16, 32, 64, 128) or type(value['mask']) is not int:
        raise ValueError(f'{name}.mask: 한 비트(1·2·4·…·128)여야 함')
    out = bytes([bc, bd, flag | (0x80 if value['when'] == 'off' else 0), value['mask']])
    if with_list:
        target = address(value['list'], f'{name}.list')
        if target not in alt_starts:
            raise ValueError(f'{name}.list: 10:8000~DDB1 대체 목록의 시작점이 아님')
        out += (target & 0xFFFF).to_bytes(2, 'little')
    return out


def edits(rom, doc):
    """[(주소, 새 바이트, 원본 바이트, 설명)]. 바뀌지 않은 항목도 들어 있다."""
    keys(doc, {'format', 'entries', 'overrides', 'no_npc'}, '문서')
    if doc.get('format') != FORMAT:
        raise ValueError(f'format={FORMAT}이 필요함')
    lists, overrides, no_npc, known, alt_starts = layout(rom)
    out, seen = [], set()
    rows = doc.get('entries', [])
    if not isinstance(rows, list):
        raise ValueError('entries는 배열이어야 함')
    for row in rows:
        keys(row, ENTRY_KEYS, 'entries')
        list_at = address(row.get('list'), 'list')
        if list_at not in lists:
            raise ValueError(f'{row["list"]}: 원본 인물 목록의 시작점이 아님')
        name, entries = lists[list_at]
        if not entries:
            raise ValueError(f'{row["list"]}: 인물이 없는 목록')
        index = integer(row.get('index'), 0, len(entries) - 1, 'index')
        entry = entries[index]
        label = f'{row["list"]}[{index}]'
        if 'name' in row and row['name'] != name or 'address' in row and row['address'] != cpu(entry):
            raise ValueError(f'{label}: name·address 가 원본({name}, {cpu(entry)})과 다름')
        if entry in seen:
            raise ValueError(f'{label}: 같은 엔트리를 두 번 지정함')
        seen.add(entry)
        old = raw(rom, entry, entry_size(rom, entry))
        out.append((entry, entry_bytes(rom, entry, row, label), old, f'인물 {name} {label}'))
    for section, table, with_list in (('overrides', overrides, True), ('no_npc', no_npc, False)):
        rows = doc.get(section, [])
        if not isinstance(rows, list):
            raise ValueError(f'{section}는 배열이어야 함')
        used = set()
        for row in rows:
            keys(row, CONDITION_KEYS | ({'list'} if with_list else set()), section)
            index = integer(row.get('index'), 0, len(table) - 1, f'{section}.index')
            if index in used:
                raise ValueError(f'{section}[{index}]: 같은 항목을 두 번 지정함')
            used.add(index)
            at, old = table[index]
            out.append((at, condition_bytes(old, row, known, alt_starts, with_list, f'{section}[{index}]'), old,
                        f'{section} {index}'))
    count_guard(rom, lists, overrides, out)
    return out


def placed_count(rom, entries, night):
    return sum(parse(rom, e, night) is not None for e in entries)


def count_guard(rom, lists, overrides, writes):
    """낮밤을 바꿔 한 시간대 인물 수가 늘 때, 그 목록을 쓰는 맵이 원본의 같은 시간대에 놓던 최대 수를 넘지 않게 한다.

    인물 표 슬롯 번호($81)에는 상한 검사가 없고 인물 뒤에 다른 물체가 이어 놓이는지 확인하지 않았으므로,
    원본이 그 맵에서 이미 놓던 수 안에서만 받는다.
    """
    data = bytearray(rom.d)
    for at, new, _, _ in writes:
        data[lorom(at):lorom(at) + len(new)] = new
    edited = Rom(data)
    changed = {at: new for at, new, _, _ in writes}

    def uses(rows):
        pairs = {(map_number_raw(name), at) for at, (name, _) in lists.items()
                 if re.fullmatch(r'[0-9A-F]{2}/[0-9A-F]{2}', name)}
        pairs.update(((row[0], row[1]), 0x100000 | row[4] | row[5] << 8) for row in rows)
        return pairs

    before, most = uses(old for _, old in overrides), {}
    for key, at in before:
        for night in (False, True):
            most[key, night] = max(most.get((key, night), 0), placed_count(rom, lists[at][1], night))
    for key, at in uses(changed.get(at, old) for at, old in overrides):
        for night in (False, True):
            count = placed_count(edited, lists[at][1], night)
            if (key, at) in before and count <= placed_count(rom, lists[at][1], night):
                continue
            if count > most.get((key, night), 0):
                time = '밤' if night else '낮'
                raise ValueError(f'{map_name(*key)}: {cpu(at)} 목록이 {time}에 {count}명을 놓게 됨; 원본이 이 맵 {time}에 '
                                 f'놓던 최대 {most.get((key, night), 0)}명을 넘음(인물 표 슬롯 상한 미확인)')


def patch(rom, doc):
    return {'format': 'dq5patch/1', 'name': 'npc-records', 'writes': [
        {'at': cpu(at), 'hex': new.hex(' '), 'orig': old.hex(' '), 'note': note}
        for at, new, old, note in edits(rom, doc) if new != old]}


def structure(rom):
    """목록마다 (엔트리 크기, 시간대 비트) — 제자리 쓰기 뒤에도 같아야 하는 것."""
    return {at: [(entry_size(rom, e), rom.u8(e) & 0xC0 == 0xC0) for e in rows]
            for at, (_, rows) in layout(rom)[0].items()}


def check(rom, doc=None):
    from dq5build import build, parse_at
    lists = layout(rom)[0]
    # offsets()가 12:8161·12:8227 을 옮긴 parse()와 같은 값을 읽는지 모든 엔트리에서 본다.
    for name, rows in lists.values():
        for entry in rows:
            data = raw(rom, entry, entry_size(rom, entry))
            for time, where in offsets(data).items():
                f = parse(rom, entry, time == 'night')
                if f is None:
                    continue
                got = {k: data[where[k]] for k in FIELDS}
                got['extra'] = 0xFF if where['extra'] is None else data[where['extra']]
                if any(got[k] != f[k] & 0xFF for k in (*FIELDS, 'extra')) or data[where['flags']] != f['flags']:
                    raise ValueError(f'{name} {cpu(entry)} {time}: 필드 오프셋이 로더와 다름')
    original = dump(rom)
    source = original if doc is None else doc
    writes = patch(rom, source)['writes']
    if doc is None and writes:
        raise ValueError('원본 왕복 쓰기가 0개가 아님')
    rebuilt, _ = build(rom.d, [('npc-records', 0, [
        (parse_at(w['at'])[0], bytes.fromhex(w['hex']), bytes.fromhex(w['orig']), w['note']) for w in writes])], 0)
    moved = Rom(rebuilt)
    if structure(moved) != structure(rom):
        raise ValueError('빌드한 롬의 목록·엔트리 크기·두 벌 여부가 원본과 다름')
    if patch(moved, source)['writes']:
        raise ValueError('빌더 적용 후 같은 입력을 다시 패치하면 쓰기가 남음')
    if patch(moved, dump(moved))['writes']:
        raise ValueError('빌드한 롬을 다시 읽고 인코딩한 결과가 다름')
    count = sum(len(rows) for _, rows in lists.values())
    print(f'목록 {len(lists)}개, 인물 {count}개, 대체 표 {OVERRIDE_COUNT}개, 빈 맵 표 {NO_NPC_COUNT}개 검사 통과; '
          f'바뀐 레코드 {len(writes)}개')


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
    args = parser.parse_args()
    try:
        rom = Rom(args.rom.read_bytes())
        doc = json.loads(args.source.read_text(encoding='utf-8')) if getattr(args, 'source', None) else None
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
    raise SystemExit(main())
