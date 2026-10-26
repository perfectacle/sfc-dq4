"""DQ5 실내 출구·영역 이동 고정 슬롯 쓰기.

출구 종류·길이·목록 수를 유지하며, 일반/고층 영역 이동의 층과 좌표를 편집한다.
고층 공유 목록을 바꿀 때는 shared_maps에 영향을 받는 모든 맵을 명시한다.
형식: sfc/dq5/docs/dq5-map-format.md의 출구·영역 이동.

  python sfc/dq5/tools/dq5exitwrite.py rom/dq5.sfc dump -o work/connections.json
  python sfc/dq5/tools/dq5exitwrite.py rom/dq5.sfc patch work/connections.json -o work/connections.patch.json
  python sfc/dq5/tools/dq5exitwrite.py rom/dq5.sfc check [work/connections.json]
"""
import argparse
import json
import re
import sys
from pathlib import Path

from dq5exit import DEST_TABLE, ENTRY_SIZE
from dq5map import Rom, lorom
from dq5mapwrite import all_maps
from dq5trigger import INDEX, RECORD_SIZE, RECORDS

FORMAT = 'dq5connections/1'
EXIT_END = 0x2AF224
KINDS = {0: 'special', 0x20: 'other-group', 0x40: 'same-group', 0x60: 'position'}
TRIGGER_FIELDS = ('source_layer', 'flags', 'destination_group', 'destination_map',
                  'x', 'y', 'span_raw', 'destination_layer')
HIGH_LISTS = ((0x019635, 1), (0x019642, 3), (0x019667, 2), (0x019680, 1),
              (0x01968D, 1), (0x01969A, 1), (0x0196A7, 1), (0x0196B4, 2),
              (0x0196CD, 1), (0x0196DA, 1), (0x0196E7, 1), (0x0196F4, 1),
              (0x019701, 4), (0x019732, 2), (0x01974B, 2), (0x019764, 1))
HIGH_END = 0x019771


def integer(value, maximum, name):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError(f'{name}: 0~{maximum} 정수여야 함')
    return value


def fields(value, allowed, name):
    if not isinstance(value, dict) or value.keys() - allowed:
        raise ValueError(f'{name}: 허용한 필드 {sorted(allowed)}만 있는 객체여야 함')


def read(rom, addr, size):
    result = bytes(rom.d[lorom(addr):lorom(addr) + size])
    if len(result) != size:
        raise ValueError(f'{addr:06X}: 롬 범위 밖')
    return result


def map_name(bc, bd):
    return f'{bc:02X}/{bd:02X}'


def map_number(value, known):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-fA-F]{2}/[0-9a-fA-F]{2}', value):
        raise ValueError('map은 GG/MM 형태여야 함')
    result = tuple(int(v, 16) for v in value.split('/'))
    if result not in known:
        raise ValueError(f'원본 목록에 없는 맵 {value}')
    return result


def high_list(bc, bd):
    if bc == 0x50:
        return 0x019635
    if bc == 0x51:
        return (0x01968D, 0x01969A, 0x0196B4, 0x0196E7, 0x0196F4, 0x0196A7, 0x0196CD, 0x0196DA)[bd - 0x50]
    if bc == 0x52:
        return 0x019680
    if bc == 0x53:
        return 0x019642 if bd == 0x51 else 0x019667
    return (0x019701, 0x019732, 0x01974B, 0x019764)[bd - 0x50]


def layout(rom):
    from dq5exitreloc import HIGH_ORIGINAL, ORIGINAL, locate
    if locate(rom) != {**ORIGINAL, 'high': HIGH_ORIGINAL}:
        raise ValueError('표를 옮긴 롬이라 고정 슬롯을 쓸 수 없음(dq5exitreloc.py 로 고침)')
    known = set(all_maps(rom))
    exits, triggers = {}, {}
    addr = DEST_TABLE
    for bc in range(54):
        if read(rom, addr, 1)[0] != bc:
            raise ValueError('출구 그룹 순서가 원본과 다름')
        addr += 1
        maps = sorted(bd for group, bd in known if group == bc)
        for bd in maps:
            rows = []
            while True:
                if addr >= EXIT_END:
                    raise ValueError('출구 목록이 고정 영역을 넘음')
                first = read(rom, addr, 1)[0]
                if first == 0xFF:
                    raise ValueError('맵 출구가 끝나기 전에 그룹 종료자를 만남')
                size = ENTRY_SIZE[first & 0x60]
                if addr + size > EXIT_END:
                    raise ValueError('출구 레코드가 고정 영역을 넘음')
                rows.append((addr, read(rom, addr, size)))
                addr += size
                if first & 128:
                    break
            exits[bc, bd] = rows
        if read(rom, addr, 1) != b'\xff':
            raise ValueError('출구 그룹 종료자가 없음')
        addr += 1
    if addr != EXIT_END:
        raise ValueError('출구 표 크기가 원본과 다름')
    cursor = RECORDS
    for i in range(198):
        bc, bd, count = read(rom, INDEX + i * 3, 3)
        if (bc, bd) not in known or (bc, bd) in triggers:
            raise ValueError('영역 이동 색인에 잘못되거나 중복된 맵')
        if cursor + count * RECORD_SIZE > INDEX:
            raise ValueError('영역 이동 레코드가 색인과 겹침')
        triggers[bc, bd] = [(cursor + k * RECORD_SIZE, read(rom, cursor + k * RECORD_SIZE, RECORD_SIZE)) for k in range(count)]
        cursor += count * RECORD_SIZE
    if cursor != INDEX or read(rom, INDEX + 198 * 3, 1) != b'\xff':
        raise ValueError('영역 이동 표 크기나 종료자가 원본과 다름')
    for at, count in HIGH_LISTS:
        if read(rom, at, 1)[0] != count:
            raise ValueError(f'{at:06X}: 고층 목록 개수가 원본과 다름')
    for bc, bd in sorted(known):
        if bc < 0x50:
            continue
        at = high_list(bc, bd)
        triggers[bc, bd] = [(at + 1 + k * RECORD_SIZE, read(rom, at + 1 + k * RECORD_SIZE, RECORD_SIZE)) for k in range(read(rom, at, 1)[0])]
    references = {}
    for (bc, bd), rows in triggers.items():
        for at, _ in rows:
            references.setdefault(at, []).append(map_name(bc, bd))
    return known, exits, triggers, references


def decode_exit(raw):
    kind = raw[0] & 0x60
    value = {'kind': KINDS[kind]}
    if kind == 0:
        value['special'] = raw[0] & 31
    else:
        value['destination_map'] = raw[0] & 31
        if kind in (0x20, 0x40):
            value['exit'] = raw[1]
        if kind == 0x20:
            value['group'] = raw[2]
        if kind == 0x60:
            value.update(x=raw[1], y=raw[2], layer=raw[3], group=raw[4])
    return value


def encode_exit(raw, changes):
    original = decode_exit(raw)
    fields(changes, set(original), '출구')
    value = original | changes
    if value['kind'] != original['kind']:
        raise ValueError('출구 종류와 길이는 바꿀 수 없음')
    for key in value.keys() - {'kind'}:
        # 2A:F711 은 다른 그룹을 FF 가 나올 때까지 한 바이트씩 건너뛰므로 레코드 안의 FF 는 그룹을 끊는다.
        integer(value[key], 31 if key in ('special', 'destination_map') else 254, key)
    first = raw[0] & 0xE0 | value.get('destination_map', value.get('special', 0))
    kind = raw[0] & 0x60
    if kind == 0:
        return bytes([first])
    if kind == 0x40:
        return bytes([first, value['exit']])
    if kind == 0x20:
        return bytes([first, value['exit'], value['group']])
    return bytes([first, value['x'], value['y'], value['layer'], value['group']])


def decode_trigger(raw):
    return {'rect': list(raw[:4]), **dict(zip(TRIGGER_FIELDS, raw[4:]))}


def encode_trigger(raw, changes):
    fields(changes, {'rect', *TRIGGER_FIELDS}, '영역 이동')
    value = decode_trigger(raw) | changes
    rect = value['rect']
    if not isinstance(rect, list) or len(rect) != 4:
        raise ValueError('rect는 좌표 바이트 네 개여야 함')
    for v in rect:
        integer(v, 255, 'rect')
    for key in TRIGGER_FIELDS:
        integer(value[key], 255, key)
    if rect != list(raw[:4]):
        for start, end in ((rect[0], rect[2]), (rect[1], rect[3])):
            # 주인공 좌표가 음수이면 엔진은 상한 대신 시작점과 같은지만 본다(00:CE0C·CE21).
            if start < 128 and start >= end:
                raise ValueError('양수 영역의 끝은 시작보다 커야 함')
    return bytes([*rect, *(value[k] for k in TRIGGER_FIELDS)])


def dump(rom):
    _, exits, triggers, references = layout(rom)
    result = {'format': FORMAT, 'exits': [], 'triggers': []}
    for section, tables, decoder in (('exits', exits, decode_exit), ('triggers', triggers, decode_trigger)):
        seen = set()
        for (bc, bd), rows in sorted(tables.items()):
            for i, (at, raw) in enumerate(rows):
                if at in seen:
                    continue
                seen.add(at)
                value = {'map': map_name(bc, bd), 'index': i, **decoder(raw)}
                if section == 'triggers' and len(references[at]) > 1:
                    value['shared_maps'] = sorted(references[at])
                result[section].append(value)
    return result


def destination(section, key, value, known, exits):
    if section == 'exits' and value['kind'] != 'special':
        target = value.get('group', key[0]), value['destination_map']
        if target not in known:
            raise ValueError('출구 목적지 맵이 원본 목록에 없음')
        if 'exit' in value and value['exit'] >= len(exits.get(target, [])):
            raise ValueError('도착 출구 번호가 목적지 목록 밖')
    elif section == 'triggers' and not value['destination_group'] & 128:
        if (value['destination_group'], value['destination_map']) not in known:
            raise ValueError('영역 이동 목적지 맵이 원본 목록에 없음')


def edits(rom, doc):
    fields(doc, {'format', 'exits', 'triggers'}, '문서')
    if doc.get('format') != FORMAT:
        raise ValueError(f'format={FORMAT}이 필요함')
    known, exits, triggers, references = layout(rom)
    out, seen = [], set()
    for section, tables, decoder, encoder in (('exits', exits, decode_exit, encode_exit), ('triggers', triggers, decode_trigger, encode_trigger)):
        rows = doc.get(section, [])
        if not isinstance(rows, list):
            raise ValueError(f'{section}는 배열이어야 함')
        for row in rows:
            fields(row, {'map', 'index', 'kind', 'special', 'group', 'exit', 'layer',
                         'destination_map', 'x', 'y'} if section == 'exits' else {'map', 'index', 'shared_maps', 'rect', *TRIGGER_FIELDS}, section)
            key = map_number(row.get('map'), known)
            slots = tables.get(key, [])
            if not slots:
                raise ValueError(f'{row["map"]}: {section} 레코드가 없는 맵')
            i = integer(row.get('index'), len(slots) - 1, 'index')
            at, old = slots[i]
            if at in seen:
                raise ValueError(f'같은 레코드를 두 번 지정함: {at:06X}')
            seen.add(at)
            new = encoder(old, {k: v for k, v in row.items() if k not in ('map', 'index', 'shared_maps')})
            shared = sorted(references.get(at, [])) if section == 'triggers' else []
            if ('shared_maps' in row or new != old and len(shared) > 1) and (
                    sorted(row.get('shared_maps') or []) != shared or len(shared) < 2):
                    raise ValueError(f'공유 목록 수정에는 shared_maps={shared}를 명시해야 함')
            if new != old:
                destination(section, key, decoder(new), known, exits)
            out.append((at, new, old, f'{section} {row["map"]} {i}'))
    return out


def patch(rom, doc):
    return {'format': 'dq5patch/1', 'name': 'map-connections', 'writes': [
        {'at': f'{at >> 16:02X}:{at & 65535:04X}', 'hex': new.hex(' '), 'orig': old.hex(' '), 'note': note}
        for at, new, old, note in edits(rom, doc) if new != old]}


def group_scan(rom):
    """2A:F711 처럼 그룹 머리를 찾아 그룹마다 첫 레코드 주소를 돌려준다."""
    starts, addr = {}, DEST_TABLE
    while True:
        bc = read(rom, addr, 1)[0]
        if bc == 0xFF or bc in starts:
            return starts
        starts[bc] = addr + 1
        addr += 1
        while read(rom, addr, 1)[0] != 0xFF:
            addr += 1
        addr += 1


def check(rom, doc=None):
    from dq5build import build, parse_at
    original = dump(rom)
    source = original if doc is None else doc
    writes = patch(rom, source)['writes']
    if doc is None and writes:
        raise ValueError('원본 왕복 쓰기가 0개가 아님')
    rebuilt, _ = build(rom.d, [('map-connections', 0, [
        (parse_at(w['at'])[0], bytes.fromhex(w['hex']), bytes.fromhex(w['orig']), w['note']) for w in writes])], 0)
    moved = Rom(rebuilt)
    _, exits, _, _ = layout(moved)
    starts = group_scan(moved)
    for bc in range(54):
        first = min(rows[0][0] for (group, _), rows in exits.items() if group == bc)
        if starts.get(bc) != first:
            raise ValueError(f'그룹 {bc:02X}: 엔진의 그룹 탐색이 표 구조와 다른 곳에 닿음')
    if patch(moved, source)['writes']:
        raise ValueError('빌더 적용 후 같은 입력을 다시 패치하면 쓰기가 남음')
    if patch(moved, dump(moved))['writes']:
        raise ValueError('빌드한 롬을 다시 읽고 인코딩한 결과가 다름')
    size = EXIT_END - DEST_TABLE + INDEX + 198 * 3 + 1 - RECORDS + HIGH_END - HIGH_LISTS[0][0]
    print(f'출구 {len(original["exits"])}개, 영역 이동 {len(original["triggers"])}개; '
          f'고정 표 {size}바이트 검사 통과; 바뀐 레코드 {len(writes)}개')


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
        return 0
    except (ValueError, OSError, IndexError) as error:
        print(f'오류: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
