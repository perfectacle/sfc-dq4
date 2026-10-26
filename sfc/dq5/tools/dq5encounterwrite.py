"""DQ5 조우를 고르는 고정 표 쓰기: 필드 구역 격자, 실내 맵의 구역 연결, 고정 무리, 이벤트 전투 무리.

형식은 sfc/dq5/docs/dq5-data-format.md 의 「전투 조우」. 표의 크기·위치는 그대로 두고 적은 값만 바꾼다.
구역 레코드(23:96F3) 자체는 dq5progresswrite.py 가 쓴다.

  python sfc/dq5/tools/dq5encounterwrite.py rom/dq5.sfc dump -o work/encounter.json
  python sfc/dq5/tools/dq5encounterwrite.py rom/dq5.sfc patch work/encounter.json -o work/encounter.dq5patch.json
  python sfc/dq5/tools/dq5encounterwrite.py rom/dq5.sfc check

JSON format 은 dq5encounter/1.
  field_grids   index 0~4(dq5encounter.FIELD_GRIDS 순서), rows 는 17칸 줄의 배열(줄 수는 원래대로). 값은 구역 0~84
  maps          map "BC/BD"(16진, 그룹 00~35 와 23:FDD6 의 50~54), areas 는 $1948 = 0·1·2 일 때의 구역 셋
                (0~84, 255 = 조우 없음). patch --areas N 이면 구역 0~N-1(dq5progresswrite.py 로 더한 구역)
  fixed_groups  index 0~8, members 는 1~3개의 {monster 0~235, count_code 0~14}
  event_groups  index 0~63, flags 첫 바이트(bit0-1 곡 0~2, bit4~7. 실측 안 된 bit2·3 은 받지 않음),
                members 는 1~4개의 {monster 0~235, count 1~9}
빈 자리는 몬스터 FF 로 채운다. 고정 무리의 줄 번호(하위 4비트)와 이벤트 무리의 +9~+C 는 원래 값을 둔다.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5encounter import (AREA_COUNT, EVENT_COUNT, EVENT_GROUPS, EVENT_SIZE, FIELD_GRIDS, FIELD_WIDTH,  # noqa: E402
                          FIXED, FIXED_COUNT, GROUPS, MAP_TABLE)
from dq5map import Rom, lorom  # noqa: E402

FORMAT = 'dq5encounter/1'
FIXED_SIZE = 6
MAP_SIZE = 6
MONSTER_MAX = 235
COUNT_CODES = 15       # 23:EA63·23:EA73 의 마릿수 부호 0~14
EVENT_COUNT_MAX = 9    # 이벤트 무리에서 실측한 가장 큰 마릿수(몬스터 00 9마리)
NO_AREA = 0xFF
# 01:8477: BC 가 50 이상이면 23:FDD6 의 [BC][포인터] 목록(FF 로 끝)에서 그룹을 찾고, 그 포인터의 [BD][6바이트] 목록
# (BD 자리 FF 로 끝)에서 맵을 찾는다. 6바이트의 꼴은 그룹 00~35 의 항목과 같다.
HIGH_GROUPS = 0x23FDD6
HIGH_FIRST = 0x50


def integer(value, maximum, name, minimum=0):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f'{name}: {minimum}~{maximum} 정수여야 함')
    return value


def fields(value, allowed, name):
    if not isinstance(value, dict):
        raise ValueError(f'{name}: JSON 객체여야 함')
    if value.keys() - allowed:
        raise ValueError(f'{name}: 모르는 필드 {sorted(value.keys() - allowed)}')


def read(rom, addr, size):
    off = lorom(addr)
    return bytes(rom.d[off:off + size])


def map_slots(rom):
    """(BC, BD) → 맵 항목 주소. 그룹 n 의 항목은 포인터 n 부터 포인터 n+1(마지막은 표 자신) 앞까지."""
    out = {}
    for bc in range(GROUPS):
        p = rom.u16(MAP_TABLE + bc * 2)
        q = rom.u16(MAP_TABLE + bc * 2 + 2) if bc + 1 < GROUPS else MAP_TABLE & 0xFFFF
        if (q - p) % MAP_SIZE or q < p:
            raise ValueError(f'맵 그룹 {bc:02X} 의 항목 범위가 원래 꼴이 아님')
        for bd in range((q - p) // MAP_SIZE):
            out[bc, bd] = 0x230000 | p + bd * MAP_SIZE
    return out | high_map_slots(rom)


def high_map_slots(rom):
    """그룹 50 이상의 (BC, BD) → 6바이트 항목 주소(23:FDD6, 코드 읽기 01:8477)."""
    out, at = {}, HIGH_GROUPS
    while (bc := rom.u8(at)) != 0xFF:
        if bc < HIGH_FIRST:
            raise ValueError(f'23:FDD6 목록에 그룹 {bc:02X}(50 미만)이 있음')
        if any(key[0] == bc for key in out):
            raise ValueError(f'23:FDD6 목록에 그룹 {bc:02X} 가 둘 있음(앞의 것만 읽힘)')
        entry = 0x230000 | rom.u16(at + 1)
        while (bd := rom.u8(entry)) != 0xFF:
            if (bc, bd) in out:
                raise ValueError(f'23:FDD6 목록에 맵 {bc:02X}/{bd:02X} 가 둘 있음(앞의 것만 읽힘)')
            out[bc, bd] = entry + 1
            entry += 1 + MAP_SIZE
        at += 3
    return out


def members(raw, count, monster_at, value_at):
    return [(raw[monster_at + i], raw[value_at + i]) for i in range(count) if raw[monster_at + i] != 0xFF]


def dump(rom):
    return {
        'format': FORMAT,
        'field_grids': [{'index': i, 'condition': name,
                         'rows': [list(read(rom, addr + r * FIELD_WIDTH, FIELD_WIDTH)) for r in range(rows)]}
                        for i, (name, addr, rows) in enumerate(FIELD_GRIDS)],
        'maps': [{'map': f'{bc:02X}/{bd:02X}', 'areas': list(read(rom, addr, 3))}
                 for (bc, bd), addr in map_slots(rom).items()],
        'fixed_groups': [{'index': g, 'members': [{'monster': m, 'count_code': v >> 4} for m, v in
                                                  members(read(rom, FIXED + g * FIXED_SIZE, FIXED_SIZE), 3, 0, 3)]}
                         for g in range(FIXED_COUNT)],
        'event_groups': [{'index': g, 'flags': raw[0], 'members': [{'monster': m, 'count': c} for m, c in members(raw, 4, 1, 5)]}
                         for g in range(EVENT_COUNT) for raw in [read(rom, EVENT_GROUPS + g * EVENT_SIZE, EVENT_SIZE)]],
    }


def member_list(value, most, name):
    if not isinstance(value, list) or not 1 <= len(value) <= most:
        raise ValueError(f'{name}: 1~{most}개의 배열이어야 함')
    return value


def encode_grid(raw, rows, name, areas=AREA_COUNT):
    if not isinstance(rows, list) or len(rows) != len(raw) // FIELD_WIDTH:
        raise ValueError(f'{name}: {len(raw) // FIELD_WIDTH}줄이어야 함')
    out = bytearray()
    for row in rows:
        if not isinstance(row, list) or len(row) != FIELD_WIDTH:
            raise ValueError(f'{name}: 줄마다 {FIELD_WIDTH}칸이어야 함')
        out += bytes(integer(v, areas - 1, f'{name} 구역') for v in row)
    return bytes(out)


def encode_map(raw, areas, name, count=AREA_COUNT):
    if not isinstance(areas, list) or len(areas) != 3:
        raise ValueError(f'{name}: areas 는 구역 셋이어야 함')
    for v in areas:
        if integer(v, NO_AREA, f'{name} 구역') != NO_AREA:
            integer(v, count - 1, f'{name} 구역(255 = 조우 없음)')
    return bytes(areas) + raw[3:]


def encode_fixed(raw, change, name):
    out = bytearray(raw)
    rows = member_list(change['members'], 3, name)
    for i in range(3):
        if i < len(rows):
            fields(rows[i], {'monster', 'count_code'}, name)
            if rows[i].keys() != {'monster', 'count_code'}:
                raise ValueError(f'{name}: monster·count_code 를 모두 적어야 함')
            out[i] = integer(rows[i]['monster'], MONSTER_MAX, f'{name} monster')
            out[3 + i] = integer(rows[i]['count_code'], COUNT_CODES - 1, f'{name} count_code') << 4 | raw[3 + i] & 15
        else:
            out[i] = 0xFF
            if raw[i] != 0xFF:
                out[3 + i] = raw[3 + i] & 15
    return bytes(out)


def encode_event(raw, change, name):
    out = bytearray(raw)
    if 'flags' in change:
        flags = integer(change['flags'], 255, f'{name} flags')
        # 26:8F96 의 곡 표는 셋뿐이고, bit2·3 은 원래 표에서 늘 꺼져 있어 뜻을 보지 못했다.
        if flags & 0x0C or flags & 3 == 3:
            raise ValueError(f'{name} flags: bit2·3 과 곡 번호 3 은 쓸 수 없음')
        out[0] = flags
    if 'members' in change:
        rows = member_list(change['members'], 4, name)
        for i in range(4):
            if i < len(rows):
                fields(rows[i], {'monster', 'count'}, name)
                if rows[i].keys() != {'monster', 'count'}:
                    raise ValueError(f'{name}: monster·count 를 모두 적어야 함')
                out[1 + i] = integer(rows[i]['monster'], MONSTER_MAX, f'{name} monster')
                out[5 + i] = integer(rows[i]['count'], EVENT_COUNT_MAX, f'{name} count', 1)
            else:
                out[1 + i], out[5 + i] = 0xFF, 0
    return bytes(out)


def edits(rom, doc, areas=AREA_COUNT):
    integer(areas, NO_AREA, '구역 수', AREA_COUNT)
    fields(doc, {'format', 'field_grids', 'maps', 'fixed_groups', 'event_groups'}, '문서')
    if doc.get('format') != FORMAT:
        raise ValueError(f'format 은 {FORMAT} 이어야 함')
    slots = map_slots(rom)
    out = []
    for section in ('field_grids', 'maps', 'fixed_groups', 'event_groups'):
        rows = doc.get(section, [])
        if not isinstance(rows, list):
            raise ValueError(f'{section}: 배열이어야 함')
        seen = set()
        for row in rows:
            if section == 'field_grids':
                fields(row, {'index', 'condition', 'rows'}, section)
                key = integer(row.get('index'), len(FIELD_GRIDS) - 1, 'field_grids index')
                if row.get('condition', FIELD_GRIDS[key][0]) != FIELD_GRIDS[key][0]:
                    raise ValueError(f'격자 {key}: condition 이 {FIELD_GRIDS[key][0]!r} 와 다름')
                _, addr, count = FIELD_GRIDS[key]
                raw = read(rom, addr, count * FIELD_WIDTH)
                new = encode_grid(raw, row.get('rows'), f'격자 {key}', areas)
            elif section == 'maps':
                fields(row, {'map', 'areas'}, section)
                text = row.get('map')
                parts = text.split('/') if isinstance(text, str) else []
                key = tuple(int(v, 16) for v in parts) if len(parts) == 2 and all(
                    len(v) == 2 and all(c in '0123456789abcdefABCDEF' for c in v) for v in parts) else None
                if key not in slots:
                    raise ValueError(f'maps: {text!r} 는 구역 연결 표에 없는 맵(그룹 00~{GROUPS - 1:02X}, 23:FDD6 의 50~)')
                addr = slots[key]
                raw = read(rom, addr, MAP_SIZE)
                new = encode_map(raw, row.get('areas'), f'맵 {text}', areas)
            elif section == 'fixed_groups':
                fields(row, {'index', 'members'}, section)
                key = integer(row.get('index'), FIXED_COUNT - 1, 'fixed_groups index')
                addr = FIXED + key * FIXED_SIZE
                raw = read(rom, addr, FIXED_SIZE)
                new = encode_fixed(raw, row, f'고정 무리 {key}') if 'members' in row else raw
            else:
                fields(row, {'index', 'flags', 'members'}, section)
                key = integer(row.get('index'), EVENT_COUNT - 1, 'event_groups index')
                addr = EVENT_GROUPS + key * EVENT_SIZE
                raw = read(rom, addr, EVENT_SIZE)
                new = encode_event(raw, row, f'이벤트 무리 {key:02X}')
            if key in seen:
                raise ValueError(f'{section}: 중복 항목 {key}')
            seen.add(key)
            out.append((addr, new, raw, f'{section} {row.get("map", key)}'))
    return out


def patch(rom, doc, name='encounter', areas=AREA_COUNT):
    return {'format': 'dq5patch/1', 'name': name, 'writes': [
        {'at': f'{addr >> 16:02X}:{addr & 0xFFFF:04X}', 'hex': new.hex(' '), 'orig': old.hex(' '), 'note': note}
        for addr, new, old, note in edits(rom, doc, areas) if new != old]}


def check(rom):
    rows = edits(rom, dump(rom))
    bad = sum(new != old for _, new, old, _ in rows)
    print(f'격자 {len(FIELD_GRIDS)}개·맵 {len(map_slots(rom))}개·고정 무리 {FIXED_COUNT}개·이벤트 무리 {EVENT_COUNT}개: '
          f'{sum(len(old) for _, _, old, _ in rows)}바이트, 다른 항목 {bad}개')
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
    write.add_argument('--name', default='encounter')
    write.add_argument('--areas', type=int, default=AREA_COUNT,
                       help='구역 수. dq5progresswrite.py 로 구역을 더했으면 그 수(85~255). 실제로 더한 수인지는 보지 않음')
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
                result = patch(rom, json.load(f), args.name, args.areas)
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
