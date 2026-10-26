"""DQ5 실내 맵 그룹 00~35 에 새 맵 번호를 더한다(그룹 끝 번호부터 차례로).

맵 번호로 곧장 색인하는 표 넷 가운데 이 도구는 맵 포인터(0F:8ED7, 맵마다 3바이트)와 맵 속성(23:FD6A, 맵마다 6바이트:
조우 구역·전투 배경·주문 막기·곡)을 맡는다. 두 표 모두 그룹 목록 바로 뒤에 그룹 표가 있어 늘릴 빈틈이 없으므로,
그룹 표를 같은 뱅크 빈 자리로 옮기고(끝 표시 16비트를 하나 더 붙임) 비는 108바이트만큼 뒤 그룹의 목록을 민다.
코드는 표 주소 피연산자(01:9317, 01:83FC·8401)만 바꾸고 DB·뱅크는 그대로다. 출구·영역 이동은
dq5exitreloc.py --new-map, 인물 목록은 인물 도구가 맡는다. 형식: sfc/dq5/docs/dq5-build-format.md 「새 맵 번호」.

  python sfc/dq5/tools/dq5newmap.py rom/dq5.sfc patch work/newmap.json -o work/newmap.dq5patch.json
      [--pointer-table-at 0F:FF50] [--attr-table-at 23:FF20] [--records-at BB:AAAA]
  python sfc/dq5/tools/dq5newmap.py rom/dq5.sfc check work/newmap.json [같은 자리 선택]

입력: {"format": "dq5newmap/1", "maps": [{"map": "0D/05", "record": {"copy": "0D/02"}, "attrs": {"copy": "0D/02"}}]}
  record: {"copy": "GG/MM"} 그 맵과 같은 레코드, {"source": "파일.json"} dq5map/1 문서(입력 파일 기준 경로, --records-at 에 놓음)
  attrs:  {"copy": "GG/MM"} 또는 {"bytes": [6개]}
  새 맵은 record·attrs 가 둘 다 있어야 한다. 기존 맵(목록이 밀리는 그룹 포함)도 record·attrs 중 바꿀 것만 적을 수 있다.
"""
import argparse
import json
import re
import sys
from pathlib import Path

from dq5build import BANK, build, free_ranges
from dq5map import ATTR_SITES, ATTR_TABLE, GROUP_TABLE, GROUPS, POINTER_SITE, Rom, group_spans, lorom, map_pointer
from dq5mapwrite import encode, entries_for

FORMAT = 'dq5newmap/1'
TABLE_SIZE = GROUPS * 2
# (원래 그룹 표, 맵 하나의 크기, 기본 새 표 자리). 원래 표 뒤는 다른 자료(0F:8F43 고층 맵 레코드, 23:FDD6 고층 속성 목록).
TABLES = {'pointer': (GROUP_TABLE, 3, 0x0FFF50), 'attr': (ATTR_TABLE, 6, 0x23FF20)}


def cpu(addr):
    return f'{addr >> 16:02X}:{addr & 0xFFFF:04X}'


def read(rom, addr, size):
    off = lorom(addr)
    raw = bytes(rom.d[off:off + size])
    if len(raw) != size:
        raise ValueError(f'{cpu(addr)}: 롬 범위 밖')
    return raw


def map_key(value, name):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9A-F]{2}/[0-9A-F]{2}', value):
        raise ValueError(f'{name}: map 은 대문자 16진 GG/MM 이어야 함')
    return tuple(int(v, 16) for v in value.split('/'))


def entries(rom, kind):
    """그룹마다 [맵 항목 바이트…] 와 지금 그룹 표 자리."""
    spans, table = group_spans(rom, attr=kind == 'attr')
    size = TABLES[kind][1]
    bank = TABLES[kind][0] & 0xFF0000
    return [[read(rom, bank | start + i * size, size) for i in range((end - start) // size)]
            for start, end in spans], table


def plan(rom, doc, base):
    """입력 → 그룹마다 새 항목 목록(포인터·속성)과 새로 놓을 레코드 [(이름, 바이트)]."""
    if not isinstance(doc, dict) or set(doc) != {'format', 'maps'} or doc['format'] != FORMAT:
        raise ValueError(f'문서는 format={FORMAT} 과 maps 만 담아야 함')
    pointers, _ = entries(rom, 'pointer')
    attrs, _ = entries(rom, 'attr')
    if [len(g) for g in pointers] != [len(g) for g in attrs]:
        raise ValueError('맵 포인터와 맵 속성의 그룹별 맵 수가 다름')
    # copy 는 원본 항목에서 푼다. 입력 차례나 같은 입력의 다른 고침에 따라 값이 달라지지 않게 한다.
    base_pointers, base_attrs = [list(g) for g in pointers], [list(g) for g in attrs]
    pointers, attrs = [list(g) for g in pointers], [list(g) for g in attrs]
    records, seen = [], set()
    if not isinstance(doc['maps'], list):
        raise ValueError('maps 는 배열이어야 함')
    for i, row in enumerate(doc['maps']):
        name = f'maps[{i}]'
        if not isinstance(row, dict) or 'map' not in row or set(row) - {'map', 'record', 'attrs'}:
            raise ValueError(f'{name}: map·record·attrs 만 받음')
        bc, bd = map_key(row['map'], name)
        if bc >= GROUPS or (bc, bd) in seen:
            raise ValueError(f'{name}: 그룹 00~35 의 맵을 한 번만 적어야 함')
        seen.add((bc, bd))
        if bd == len(pointers[bc]):
            if set(row) != {'map', 'record', 'attrs'}:
                raise ValueError(f'{name}: 새 맵 {row["map"]} 에는 record 와 attrs 가 둘 다 필요함')
            pointers[bc].append(None)
            attrs[bc].append(None)
        elif bd > len(pointers[bc]):
            raise ValueError(f'{name}: 새 맵 번호는 그룹 {bc:02X} 의 끝 번호 {len(pointers[bc]):02X} 부터 차례로 더함')

        def source(value, field):
            if not isinstance(value, dict) or len(value) != 1:
                raise ValueError(f'{name}.{field}: 키 하나짜리 객체여야 함')
            if 'copy' in value:
                key = map_key(value['copy'], f'{name}.{field}.copy')
                if key[0] >= GROUPS or key[1] >= len(base_pointers[key[0]]):
                    raise ValueError(f'{name}.{field}: 복사할 맵 {value["copy"]} 이 원본에 없음(새 맵은 복사하지 않음)')
                return key
            return None

        if 'record' in row:
            key = source(row['record'], 'record')
            if key:
                pointers[bc][bd] = base_pointers[key[0]][key[1]]
            elif set(row['record']) == {'source'}:
                path = base / row['record']['source']
                record = json.loads(path.read_text(encoding='utf-8'))
                if record.get('map') not in (None, row['map']):
                    raise ValueError(f'{name}.record: {path} 의 map 이 {row["map"]} 이 아님')
                for line in entries_for(record):
                    raise ValueError(f'{name}.record: {line}')
                records.append(((bc, bd), encode(record)))
                pointers[bc][bd] = len(records) - 1
            else:
                raise ValueError(f'{name}.record: copy 또는 source 가 필요함')
        if 'attrs' in row:
            key = source(row['attrs'], 'attrs')
            if key:
                attrs[bc][bd] = base_attrs[key[0]][key[1]]
            elif set(row['attrs']) == {'bytes'} and isinstance(row['attrs']['bytes'], list) and \
                    len(row['attrs']['bytes']) == 6 and all(type(v) is int and 0 <= v <= 255 for v in row['attrs']['bytes']):
                attrs[bc][bd] = bytes(row['attrs']['bytes'])
            else:
                raise ValueError(f'{name}.attrs: copy 또는 0~255 정수 6개의 bytes 가 필요함')
    return pointers, attrs, records


def bank_free(rom, addr, size, extra=()):
    """addr~ size 바이트가 원래 롬 빈 자리나 extra 안이면 참."""
    spans = [((off // BANK) << 16 | 0x8000 | off % BANK, ((off // BANK) << 16 | 0x8000 | off % BANK) + n)
             for off, n in free_ranges(rom.d)] + list(extra)
    return any(lo <= addr and addr + size <= hi for lo, hi in spans)


def table_writes(rom, kind, groups, at):
    """그룹 목록을 밀어 쓴 쓰기와 새 그룹 표 쓰기, 피연산자 쓰기."""
    original, size, default = TABLES[kind]
    spans, table = group_spans(rom, attr=kind == 'attr')
    at = at or (table if table != original else default)
    bank = original & 0xFF0000
    if at >> 16 != original >> 16:
        raise ValueError(f'{kind}: 그룹 표는 뱅크 {original >> 16:02X} 에 둠(코드가 DB 를 그 뱅크로 둠)')
    start = spans[0][0]
    limit = (original & 0xFFFF) + TABLE_SIZE
    blob = b''.join(b for g in groups for b in g)
    if start + len(blob) > limit:
        raise ValueError(f'{kind}: 목록이 {len(blob) - (limit - start)}바이트 넘침(늘릴 수 있는 것은 옛 그룹 표 자리 108바이트)')
    starts, cursor = [], start
    for g in groups:
        starts.append(cursor)
        cursor += len(g) * size
    new_table = b''.join(v.to_bytes(2, 'little') for v in [*starts, cursor])
    out = [(bank | start, blob, '맵 포인터 목록' if kind == 'pointer' else '맵 속성 목록')]
    if len(blob) == spans[-1][1] - start:
        # 맵 수가 그대로면 표는 지금 자리에 둔다.
        return out
    current = [(table, table + TABLE_SIZE + 2)] if table != original else []
    if not bank_free(rom, at, TABLE_SIZE + 2, current):
        raise ValueError(f'{kind}: {cpu(at)}~ {TABLE_SIZE + 2}바이트가 빈 자리가 아님')
    out.append((at, new_table, '그룹 표(끝 표시 붙음)'))
    if kind == 'pointer':
        out.append((POINTER_SITE, (at & 0xFFFF).to_bytes(2, 'little'), '그룹 표 주소 01:9316'))
    else:
        out += [(ATTR_SITES[0], (at & 0xFFFF).to_bytes(2, 'little'), '맵 속성 표 주소 01:83FB'),
                (ATTR_SITES[1], (at + 1 & 0xFFFF).to_bytes(2, 'little'), '맵 속성 표 주소 01:8400')]
    return out


def writes_for(rom, doc, base=Path('.'), at=None):
    at = at or {}
    pointers, attrs, records = plan(rom, doc, base)
    cursor, placed = at.get('records'), []
    if records and not cursor:
        raise ValueError('새 레코드(source)를 놓을 --records-at 이 필요함')
    out = []
    if records and lorom(cursor) < 0x180000 and not bank_free(rom, cursor, sum(len(r) for _, r in records)):
        raise ValueError(f'--records-at {cpu(cursor)}: 원래 롬의 빈 자리나 늘린 뱅크(30~)여야 함')
    for key, raw in records:
        if (cursor & 0xFFFF) + len(raw) > 0x10000:
            raise ValueError(f'{key[0]:02X}/{key[1]:02X} 레코드가 {cpu(cursor)} 의 뱅크를 넘음')
        out.append((cursor, raw, f'맵 {key[0]:02X}/{key[1]:02X} 레코드'))
        placed.append(cursor)
        cursor += len(raw)
    pointer_groups = [[p if isinstance(p, bytes) else placed[p].to_bytes(3, 'little') for p in g] for g in pointers]
    if any(v is None for g in attrs for v in g):
        raise ValueError('속성이 없는 새 맵이 있음')
    out += table_writes(rom, 'pointer', pointer_groups, at.get('pointer'))
    out += table_writes(rom, 'attr', attrs, at.get('attr'))
    result = []
    for addr, new, note in out:
        off = lorom(addr)
        old = bytes(rom.d[off:off + len(new)]) if off + len(new) <= len(rom.d) else None
        # 앞이 같은 목록은 바뀐 첫 바이트부터 쓴다. 앞 그룹 맵을 고치는 다른 쓰기와 겹치지 않게 한다.
        same = next((i for i, (a, b) in enumerate(zip(new, old or b'')) if a != b), min(len(new), len(old or b'')))
        if old is not None and same:
            addr, new, old = addr + same, new[same:], old[same:]
        tail = next((i for i, (a, b) in enumerate(zip(new[::-1], (old or b'')[::-1])) if a != b), 0)
        if old is not None and tail:
            new, old = new[:-tail], old[:-tail]
        if new and new != old:
            result.append((addr, new, old if off < 0x180000 else None, note))
    top = max([a >> 16 for a, _, _, _ in result] or [0])
    return result, 0 if top < 0x30 else 2 if top < 0x40 else 3 if top < 0x60 else 4


def patch(rom, doc, base=Path('.'), at=None):
    writes, mb = writes_for(rom, doc, base, at)
    result = {'format': 'dq5patch/1', 'name': 'new-maps', 'writes': [
        {'at': cpu(a), 'hex': n.hex(' '), **({'orig': o.hex(' ')} if o is not None else {}), 'note': note}
        for a, n, o, note in writes]}
    if mb:
        result['rom_size'] = mb
    return result


def check(rom, doc, base=Path('.'), at=None):
    from dq5mapwrite import all_maps
    manifest = patch(rom, doc, base, at)
    mb = manifest.get('rom_size', 0)
    writes = [(lorom(int(w['at'][:2], 16) << 16 | int(w['at'][3:], 16)), bytes.fromhex(w['hex']),
               bytes.fromhex(w['orig']) if 'orig' in w else None, w['note']) for w in manifest['writes']]
    built = Rom(build(rom.d, [('new-maps', mb, writes)], mb)[0])
    before, after = set(all_maps(rom)), set(all_maps(built))
    pointers, attrs, _ = plan(rom, doc, base)
    added = sorted(after - before)
    if not before <= after or len(added) != sum(map(len, pointers)) - len([m for m in before if m[0] < GROUPS]):
        raise ValueError('만든 롬의 맵 목록이 원래 맵 + 새 맵이 아님')
    changed = {map_key(r['map'], '') for r in doc['maps']}
    old_attr, _ = entries(rom, 'attr')
    new_attr, _ = entries(built, 'attr')
    for bc, bd in sorted(before):
        if bc >= GROUPS or (bc, bd) in changed:
            continue
        if map_pointer(built, bc, bd) != map_pointer(rom, bc, bd) or new_attr[bc][bd] != old_attr[bc][bd]:
            raise ValueError(f'{bc:02X}/{bd:02X}: 고치지 않은 맵의 포인터나 속성이 바뀜')
    for bc, bd in sorted(changed):
        if isinstance(attrs[bc][bd], bytes) and new_attr[bc][bd] != attrs[bc][bd]:
            raise ValueError(f'{bc:02X}/{bd:02X}: 속성이 입력과 다름')
        want = pointers[bc][bd]
        if isinstance(want, bytes) and map_pointer(built, bc, bd) != int.from_bytes(want, 'little'):
            raise ValueError(f'{bc:02X}/{bd:02X}: 맵 포인터가 입력과 다름')
    if patch(built, doc, base, at)['writes']:
        raise ValueError('만든 롬에 같은 입력을 다시 패치하면 쓰기가 남음')
    print(f'맵 {len(before)}개 → {len(after)}개(새 {", ".join(f"{a:02X}/{b:02X}" for a, b in added)}); '
          f'그룹 표 {cpu(group_spans(built)[1])}·{cpu(group_spans(built, attr=True)[1])}; '
          f'쓰기 {len(writes)}개 검사 통과')


def address(text):
    if not re.fullmatch(r'[0-9A-Fa-f]{2}:[0-9A-Fa-f]{4}', text) or int(text[3:], 16) < 0x8000:
        raise argparse.ArgumentTypeError('BB:AAAA(AAAA 8000~FFFF) 로 적어야 함')
    return int(text[:2], 16) << 16 | int(text[3:], 16)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('rom', type=Path)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('patch', 'check'):
        p = sub.add_parser(name)
        p.add_argument('source', type=Path)
        if name == 'patch':
            p.add_argument('-o', '--out', type=Path, required=True)
        p.add_argument('--pointer-table-at', type=address, help=f'기본 {cpu(TABLES["pointer"][2])}')
        p.add_argument('--attr-table-at', type=address, help=f'기본 {cpu(TABLES["attr"][2])}')
        p.add_argument('--records-at', type=address, help='source 레코드를 놓을 자리')
    args = parser.parse_args()
    try:
        rom = Rom(args.rom.read_bytes())
        doc = json.loads(args.source.read_text(encoding='utf-8'))
        at = {'pointer': args.pointer_table_at, 'attr': args.attr_table_at, 'records': args.records_at}
        if args.command == 'check':
            check(rom, doc, args.source.parent, at)
        else:
            result = patch(rom, doc, args.source.parent, at)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(f'오류: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
