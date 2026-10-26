"""DQ5 조우를 고르는 고정 표 쓰기: 필드 구역 격자, 실내 맵의 구역 연결, 고정 무리, 이벤트 전투 무리.

형식은 sfc/dq5/docs/dq5-data-format.md 의 「전투 조우」. 표의 크기·위치는 그대로 두고 적은 값만 바꾼다.
구역 레코드(23:96F3) 자체는 dq5progresswrite.py 가 쓴다.

  python sfc/dq5/tools/dq5encounterwrite.py rom/dq5.sfc dump -o work/encounter.json
  python sfc/dq5/tools/dq5encounterwrite.py rom/dq5.sfc patch work/encounter.json -o work/encounter.dq5patch.json
  python sfc/dq5/tools/dq5encounterwrite.py rom/dq5.sfc check

JSON format 은 dq5encounter/1.
  field_grids   index 0~4(dq5encounter.FIELD_GRIDS 순서), rows 는 17칸 줄의 배열(줄 수는 원래대로). 값은 구역 0~84
  maps          map "BC/BD"(16진, 그룹 00~35 와 23:FDD6 의 50~54), areas 는 $1948 = 0·1·2 일 때의 구역 셋
                (0~84, 255 = 조우 없음). patch --progress 패치 목록을 주면 그 패치가 더한 구역까지.
                그룹 50 이상의 새 맵은 tail(+3~+5)을 함께 적고 patch --high-at 으로 목록을 30~3F 뱅크로 옮긴다
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
from dq5encounter import (AREA_COUNT, AREA_SIZE, EVENT_COUNT, EVENT_GROUPS, EVENT_SIZE, FIELD_GRIDS, FIELD_WIDTH,  # noqa: E402
                          FIXED, FIXED_COUNT, GROUPS)
from dq5map import Rom, group_spans, lorom  # noqa: E402

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
# 그룹 50 이상 목록을 읽는 01:8477~ 의 피연산자: 데이터 뱅크 즉값(LDA #$23), 그룹 목록(LDA $FDD6,Y)과
# 그 포인터(LDX $FDD7,Y). 목록에 없는 맵은 01:8474 가 01:83EB 에서 쌓은 바이트를 남긴 채 RTL 해 장면이 깨진다.
HIGH_BANK = 0x01847A
HIGH_LIST = 0x018480
HIGH_POINTER = 0x018490


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
    for bc, (p, q) in enumerate(group_spans(rom, attr=True)[0]):
        if (q - p) % MAP_SIZE or q < p:
            raise ValueError(f'맵 그룹 {bc:02X} 의 항목 범위가 원래 꼴이 아님')
        for bd in range((q - p) // MAP_SIZE):
            out[bc, bd] = 0x230000 | p + bd * MAP_SIZE
    return out | high_map_slots(rom, high_base(rom))


def high_base(rom):
    """01:8477~ 이 읽는 그룹 50 이상 목록의 주소(옮긴 롬이면 옮긴 자리)."""
    return read(rom, HIGH_BANK, 1)[0] << 16 | int.from_bytes(read(rom, HIGH_LIST, 2), 'little')


def high_map_slots(rom, at=HIGH_GROUPS):
    """그룹 50 이상의 (BC, BD) → 6바이트 항목 주소(23:FDD6, 01:8477). 포인터는 목록과 같은 뱅크."""
    out, bank = {}, at & 0xFF0000
    while (bc := rom.u8(at)) != 0xFF:
        if bc < HIGH_FIRST:
            raise ValueError(f'23:FDD6 목록에 그룹 {bc:02X}(50 미만)이 있음')
        if any(key[0] == bc for key in out):
            raise ValueError(f'23:FDD6 목록에 그룹 {bc:02X} 가 둘 있음(앞의 것만 읽힘)')
        entry = bank | rom.u16(at + 1)
        while (bd := rom.u8(entry)) != 0xFF:
            if (bc, bd) in out:
                raise ValueError(f'23:FDD6 목록에 맵 {bc:02X}/{bd:02X} 가 둘 있음(앞의 것만 읽힘)')
            out[bc, bd] = entry + 1
            entry += 1 + MAP_SIZE
        at += 3
    return out


def high_layout(rom, entries, at):
    """{(BC, BD): 6바이트} 를 at 에 [BC][포인터]…FF, 그룹마다 [BD][6바이트]…FF 꼴로 늘어놓은 바이트.
    그룹과 맵 순서는 원래 목록 순서를 따르고 새것은 뒤에 붙인다."""
    groups = []
    for bc, bd in entries:
        if bc not in groups:
            groups.append(bc)
    head = len(groups) * 3 + 1
    body, ptrs = bytearray(), bytearray()
    for bc in groups:
        ptrs += bytes([bc]) + ((at + head + len(body)) & 0xFFFF).to_bytes(2, 'little')
        for (c, bd), raw in entries.items():
            if c == bc:
                body += bytes([bd]) + raw
        body.append(0xFF)
    return bytes(ptrs + b'\xff' + body)


def high_writes(rom, entries, at):
    """그룹 50 이상 목록을 at(뱅크 30~3F)으로 옮기는 (주소, 새 바이트, 원래 바이트 또는 None, 설명) 목록."""
    if not 0x30 <= at >> 16 <= 0x3F or at & 0xFFFF < 0x8000:
        raise ValueError('--high-at 은 30~3F 뱅크의 8000~FFFF 여야 함(낮은 WRAM·$4202 를 abs 로 씀)')
    for addr, expected in ((HIGH_BANK - 1, b'\xa9\x23'), (HIGH_LIST - 1, b'\xb9\xd6\xfd'),
                           (HIGH_POINTER - 1, b'\xbe\xd7\xfd')):
        if read(rom, addr, len(expected)) != expected:
            raise ValueError(f'{addr:06X}: 원래 그룹 50 이상 목록 읽기 명령이 아님')
    raw = high_layout(rom, entries, at)
    if (at & 0xFFFF) + len(raw) > 0x10000:
        raise ValueError('그룹 50 이상 목록이 뱅크를 넘음')
    return [(at, raw, None, 'high group list relocated'),
            (HIGH_BANK, bytes([at >> 16]), read(rom, HIGH_BANK, 1), 'high group bank'),
            (HIGH_LIST, (at & 0xFFFF).to_bytes(2, 'little'), read(rom, HIGH_LIST, 2), 'high group list'),
            (HIGH_POINTER, ((at + 1) & 0xFFFF).to_bytes(2, 'little'), read(rom, HIGH_POINTER, 2),
             'high group pointer')]


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


def edits(rom, doc, areas=AREA_COUNT, high_at=None):
    integer(areas, NO_AREA, '구역 수', AREA_COUNT)
    fields(doc, {'format', 'field_grids', 'maps', 'fixed_groups', 'event_groups'}, '문서')
    if doc.get('format') != FORMAT:
        raise ValueError(f'format 은 {FORMAT} 이어야 함')
    slots = map_slots(rom)
    high = {key: read(rom, addr, MAP_SIZE) for key, addr in high_map_slots(rom, high_base(rom)).items()}
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
                fields(row, {'map', 'areas', 'tail'}, section)
                text = row.get('map')
                parts = text.split('/') if isinstance(text, str) else []
                key = tuple(int(v, 16) for v in parts) if len(parts) == 2 and all(
                    len(v) == 2 and all(c in '0123456789abcdefABCDEF' for c in v) for v in parts) else None
                if key not in slots:
                    if key is None or key[0] < HIGH_FIRST or 0xFF in key:
                        raise ValueError(f'maps: {text!r} 는 구역 연결 표에 없는 맵(그룹 00~{GROUPS - 1:02X}, 23:FDD6 의 50~)')
                    if high_at is None:
                        raise ValueError(f'maps: 그룹 50 이상 새 맵 {text} 은 --high-at 으로 목록을 옮겨야 함')
                    tail = row.get('tail')
                    if not isinstance(tail, list) or len(tail) != 3:
                        raise ValueError(f'맵 {text}: 새 맵은 tail(+3~+5 세 값)이 필요함')
                    raw = bytes([NO_AREA] * 3) + bytes(integer(v, 255, f'맵 {text} tail') for v in tail)
                    addr = None
                elif 'tail' in row:
                    raise ValueError(f'맵 {text}: tail 은 새 맵에만 씀')
                else:
                    addr = slots[key]
                    raw = read(rom, addr, MAP_SIZE)
                new = encode_map(raw, row.get('areas'), f'맵 {text}', areas)
                if key[0] >= HIGH_FIRST and high_at is not None:
                    if key in seen:
                        raise ValueError(f'{section}: 중복 항목 {key}')
                    seen.add(key)
                    high[key] = new
                    continue
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
    if high_at is not None:
        out += high_writes(rom, high, high_at)
    return out


def areas_in(progress):
    """dq5progresswrite.py 패치 목록(dq5patch/1)에서 구역 수. 구역 표를 옮기지 않았으면 원래 수."""
    tables = [w for w in progress.get('writes', []) if w.get('note') == 'area table relocated']
    if len(tables) > 1:
        raise ValueError('구역 표 쓰기가 둘 이상인 패치 목록')
    if not tables:
        return AREA_COUNT
    size = len(bytes.fromhex(tables[0]['hex']))
    if size % AREA_SIZE:
        raise ValueError('구역 표 쓰기의 길이가 22 의 배수가 아님')
    return size // AREA_SIZE


def patch(rom, doc, name='encounter', areas=AREA_COUNT, high_at=None):
    writes = []
    for addr, new, old, note in edits(rom, doc, areas, high_at):
        if new == old:
            continue
        write = {'at': f'{addr >> 16:02X}:{addr & 0xFFFF:04X}', 'hex': new.hex(' '), 'note': note}
        if old is not None:
            write['orig'] = old.hex(' ')
        writes.append(write)
    manifest = {'format': 'dq5patch/1', 'name': name, 'writes': writes}
    if high_at is not None:
        manifest['rom_size'] = 2
    return manifest


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
    write.add_argument('--progress', help='dq5progresswrite.py 패치 목록. 구역을 더했으면 그 구역 번호를 받음')
    write.add_argument('--high-at', help='그룹 50 이상 목록을 옮길 자리(30~3F 뱅크). 새 맵을 더할 때 필요. 다른 패치와 겹치지 않게 고름')
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
                doc = json.load(f)
            areas = AREA_COUNT
            if args.progress:
                with open(args.progress, encoding='utf-8') as f:
                    areas = areas_in(json.load(f))
            high_at = None
            if args.high_at:
                bank, _, low = args.high_at.partition(':')
                try:
                    high_at = int(bank, 16) << 16 | int(low, 16)
                except ValueError:
                    raise ValueError('--high-at 은 BB:AAAA 형식이어야 함') from None
            result = patch(rom, doc, args.name, areas, high_at)
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
