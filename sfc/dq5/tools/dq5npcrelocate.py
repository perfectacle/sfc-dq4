"""DQ5 인물 목록의 스크립트 길이를 바꾸고 두 확장 뱅크로 재배치한다.

형식은 sfc/dq5/docs/dq5-map-format.md의 인물. 12:8020·8050·833B의 즉값을 바꾸고
기본 그룹 포인터와 12:8449 대체 목록 포인터를 다시 쓴다. 인물 수·순서·시간대 공유는 유지한다.
원본 목록은 남겨 두며 코드 내부의 임의 직접 참조는 수정하지 않는다.

  python sfc/dq5/tools/dq5npcrelocate.py rom/dq5.sfc dump -o work/npc-lists.json
  python sfc/dq5/tools/dq5npcrelocate.py rom/dq5.sfc patch work/npc-lists.json -o work/npc-lists.dq5patch.json --report work/npc-layout.json
  python sfc/dq5/tools/dq5npcrelocate.py rom/dq5.sfc check

JSON: {"format":"dq5npcrelocate/1","scripts":[{"address":"05:A84F","commands":[...]}]}.
address는 원본 길이 바이트 주소, commands는 dq5npcwrite.py와 같은 형식이다.
생략한 스크립트는 원본을 보존한다. 새 스크립트는 1~255바이트. 04 절대 점프는 재배치할 수 없어 거부한다.
각 목록 영역은 한 뱅크에 들어가야 한다. 기본 32:8000에는 그룹 포인터 108바이트와 기본 목록,
대체 33:8000에는 대체 목록을 둔다. --base·--alt는 서로 다른 30~3F 뱅크를 받는다.
--records는 dq5npcrecord.py 문서(인물 필드·조건 표)를 옮기는 사본과 조건 표에 함께 넣는다.
이때 dq5npcrecord.py의 패치 목록은 따로 빌드에 넣지 않는다.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from dq5map import Rom, lorom  # noqa: E402
from dq5mapwrite import all_maps  # noqa: E402
from dq5npc import (  # noqa: E402
    ALT_END, ALT_START, NO_NPC, NPC_GROUPS, OVERRIDE_LISTS, all_lists, entry_size,
    list_entries, parse, script_address, script_bytes, script_ops, table_values,
)
from dq5npclists import (  # noqa: E402
    FIND_OVERRIDE, assemble_find, condition_plan, list_plan, new_map_keys, slot_guard,
)
from dq5npcrecord import edits as record_edits  # noqa: E402
from dq5npcwrite import FORMAT as SCRIPT_FORMAT, dump_script, encode, validate_flow  # noqa: E402

FORMAT = 'dq5npcrelocate/1'
BASE_START, BASE_END = 0x058651, NPC_GROUPS
GROUP_COUNT = 54
OVERRIDE_COUNT = 296
HOOKS = {0x128020: bytes.fromhex('a9 05 85 a7'), 0x128050: bytes.fromhex('b9 b2 d4'),
         0x12833B: bytes.fromhex('a9 10 85 a7')}


def cpu(addr):
    return f'{addr >> 16:02X}:{addr & 0xFFFF:04X}'


def read(rom, addr, size):
    off = lorom(addr)
    raw = bytes(rom.d[off:off + size])
    if len(raw) != size:
        raise ValueError(f'{cpu(addr)}에 {size}바이트가 없음')
    return raw


def destination(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-fA-F]{2}:[0-9a-fA-F]{4}', value):
        raise ValueError('목적지는 BB:AAAA 문자열이어야 함')
    bank, low = (int(p, 16) for p in value.split(':'))
    # 목록을 읽는 DB로도 낮은 WRAM을 접근하므로 40 이상의 뱅크는 쓰지 않는다.
    if not 0x30 <= bank <= 0x3F or not 0x8000 <= low <= 0xFFFF:
        raise ValueError('목적지는 확장 뱅크 30~3F의 8000~FFFF여야 함')
    return bank << 16 | low


def original_layout(rom):
    for addr, expected in HOOKS.items():
        if read(rom, addr, len(expected)) != expected:
            raise ValueError(f'{cpu(addr)}: 원본 인물 로더 명령과 다름')
    if read(rom, OVERRIDE_LISTS + OVERRIDE_COUNT * 6, 1) != b'\xff':
        raise ValueError('대체 목록 표의 원본 종료자가 없음')
    lists = all_lists(rom)
    if len(lists) != 346 + 293 or lists[0][0] != BASE_START:
        raise ValueError('원본 인물 목록의 개수나 시작점이 다름')
    return lists


def script_slots(rom, entries):
    result = set()
    for entry, _ in entries:
        for night in (False, True):
            addr = script_address(rom, entry, night)
            if addr is not None:
                result.add(addr)
    return result


def dump(rom):
    lists = original_layout(rom)
    known = set()
    for at, _ in lists:
        known.update(script_slots(rom, list_entries(rom, at)))
    return {'format': FORMAT, 'scripts': [{'address': cpu(at), 'commands': dump_script(rom, at)['commands']}
                                         for at in sorted(known)]}


def replacements(rom, doc, known):
    if not isinstance(doc, dict) or set(doc) - {'format', 'scripts', 'lists', 'new_lists', 'overrides', 'no_npc'} \
            or doc.get('format') != FORMAT:
        raise ValueError(f'문서는 format={FORMAT}, scripts·lists·new_lists·overrides·no_npc 만 담은 객체여야 함')
    rows = doc.get('scripts', [])
    if not isinstance(rows, list):
        raise ValueError('scripts는 배열이어야 함')
    out = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'address', 'commands'}:
            raise ValueError('스크립트 항목에는 address와 commands가 필요함')
        address = row['address']
        if not isinstance(address, str) or not re.fullmatch(r'[0-9a-fA-F]{2}:[0-9a-fA-F]{4}', address):
            raise ValueError('스크립트 주소는 BB:AAAA 문자열이어야 함')
        at = int(address.replace(':', ''), 16)
        if at not in known:
            raise ValueError(f'{address}는 원본 인물 스크립트 슬롯이 아님')
        if at in out:
            raise ValueError(f'중복 스크립트 주소 {address}')
        code = encode({'format': SCRIPT_FORMAT, 'commands': row['commands']})
        if any(raw[0] == 0x04 for _, raw, _ in script_ops(code)):
            raise ValueError('04 절대 점프는 인물 목록 재배치에서 지원하지 않음')
        out[at] = code
    return out


def repack_entry(rom, old, new, changes, raw=None):
    size = entry_size(rom, old)
    raw = raw or read(rom, old, size)
    if len(raw) != size:
        raise ValueError(f'{cpu(old)}: 고친 인물 레코드 길이가 원본과 다름')
    scripts = sorted(script_slots(rom, [(old, size)]))
    cursor, out, mapping = 0, bytearray(), {}
    for at in scripts:
        off = at - old
        original = script_bytes(rom, at)
        if not original or off < cursor or off + 1 + len(original) > size:
            raise ValueError(f'{cpu(at)}: 원본 스크립트 경계가 인물 레코드와 맞지 않음')
        code = changes.get(at, original)
        if any(b[0] == 0x04 for _, b, _ in script_ops(code)):
            raise ValueError(f'{cpu(at)}: 04 절대 점프는 재배치할 수 없음')
        out.extend(raw[cursor:off])
        target = new + len(out)
        mapping[at] = target
        if code != original:
            validate_flow(code, target + 1)
        out.extend(bytes([len(code)]) + code)
        cursor = off + 1 + len(original)
    out.extend(raw[cursor:])
    return bytes(out), mapping


def pack_region(rom, lists, start, changes, prefix=0):
    """lists 는 [(목록 열쇠, [(원본 엔트리 주소, 엔트리 바이트)])]. 같은 원본을 두 번 쓰면 대응표에는 처음 것을 남긴다."""
    out = bytearray(prefix)
    mapping, scripts, entries = {}, {}, {}
    for key, items in lists:
        mapping[key] = start + len(out)
        for addr, raw in items:
            new = start + len(out)
            raw, moved = repack_entry(rom, addr, new, changes, raw)
            entries.setdefault(addr, new)
            for old, at in moved.items():
                scripts.setdefault(old, at)
            out.extend(raw)
        out.append(0)
    if (start & 0xFFFF) + len(out) > 0x10000:
        raise ValueError(f'{cpu(start)}: 목록 {len(out)}바이트가 한 뱅크를 넘음')
    return out, mapping, scripts, entries


def patch(rom, doc, base=0x328000, alt=0x338000, records=None, allow_growth=False, new_maps=()):
    if type(base) is not int or type(alt) is not int:
        raise ValueError('목적지 주소는 정수여야 함')
    base, alt = destination(cpu(base)), destination(cpu(alt))
    if base >> 16 == alt >> 16:
        raise ValueError('기본·대체 목록은 서로 다른 뱅크여야 함')
    lists = original_layout(rom)
    base_lists = [(at, name) for at, name in lists if BASE_START <= at < BASE_END]
    alt_lists = [(at, name) for at, name in lists if ALT_START <= at < ALT_END]
    known = set()
    for at, _ in lists:
        known.update(script_slots(rom, list_entries(rom, at)))
    changes = replacements(rom, doc, known)
    # 인물 레코드·조건 표 수정(dq5npcrecord.py)은 옮기는 사본에 넣는다. 원본 자리를 고쳐도 게임은 사본을 읽는다.
    edited = {at: new for at, new, old, _ in (record_edits(rom, records) if records is not None else []) if new != old}
    entry_edits = {at: v for at, v in edited.items() if not NO_NPC <= at < OVERRIDE_LISTS + OVERRIDE_COUNT * 6}
    new_maps = new_map_keys(base_lists, list(new_maps))
    new_groups = sorted({bc for bc, _ in new_maps if bc >= GROUP_COUNT})
    base_items, alt_items = list_plan(rom, doc, base_lists + alt_lists, entry_edits, new_maps)
    first, lm1, sm1, em1 = pack_region(rom, base_items, base, changes, (GROUP_COUNT + len(new_groups)) * 2)
    second, lm2, sm2, em2 = pack_region(rom, alt_items, alt, changes)
    overrides, no_npc, moved = condition_plan(rom, doc, edited, [key for key, _ in alt_items], new_maps)
    growth = slot_guard(rom, lists, base_items, alt_items, overrides, allow_growth, new_maps)
    if moved:
        table = alt + len(second)
        rows = b''.join(head + (lm2[key] & 0xFFFF).to_bytes(2, 'little') for head, key in overrides) + b'\xff'
        routine = assemble_find(table, alt >> 16)
        second.extend(rows + routine)
        if (alt & 0xFFFF) + len(second) > 0x10000:
            raise ValueError(f'{cpu(alt)}: 대체 목록·대체 표·루틴 {len(second)}바이트가 한 뱅크를 넘음')
        find = table + len(rows)
    for i in range(GROUP_COUNT):
        old = 0x050000 | rom.u16(NPC_GROUPS + i * 2)
        if old not in lm1:
            raise ValueError(f'그룹 {i}: 목록 시작점이 아닌 포인터')
        first[i * 2:i * 2 + 2] = (lm1[old] & 0xFFFF).to_bytes(2, 'little')
    # 새 그룹(36~)의 포인터는 옮긴 그룹 표 끝에 이어 둔다. 12:8050 이 $BC*2 로 읽는 표다.
    for bc in new_groups:
        first[bc * 2:bc * 2 + 2] = (lm1[f'{bc:02X}/00'] & 0xFFFF).to_bytes(2, 'little')
    writes = [{'at': cpu(base), 'hex': first.hex(' '), 'note': '기본 인물 그룹 포인터와 목록'},
              {'at': cpu(alt), 'hex': second.hex(' '), 'note': '대체 인물 목록'}]

    def original_write(addr, value, note):
        writes.append({'at': cpu(addr), 'hex': value.hex(' '), 'orig': read(rom, addr, len(value)).hex(' '), 'note': note})

    original_write(0x128021, bytes([base >> 16]), '기본 인물 목록 뱅크')
    original_write(0x128051, (base & 0xFFFF).to_bytes(2, 'little'), '기본 그룹 포인터 표')
    if moved:
        original_write(FIND_OVERRIDE, bytes([0x22, find & 0xFF, find >> 8 & 0xFF, find >> 16, 0x60]),
                       f'대체 표 찾기를 {cpu(find)} 로(표 {cpu(table)} {len(overrides)}항목)')
    else:
        original_write(0x12833C, bytes([alt >> 16]), '대체 인물 목록 뱅크')
        for addr, value, note in condition_writes(rom, edited, lm2):
            original_write(addr, value, note)
    if no_npc is not None:
        original_write(NO_NPC, b''.join(no_npc) + b'\xff', f'빈 맵 표 {len(no_npc)}항목')
    layout = {'lists': {(k if isinstance(k, str) else cpu(k)): cpu(v) for k, v in (lm1 | lm2).items()},
              'scripts': {cpu(k): cpu(v) for k, v in (sm1 | sm2).items()},
              'entries': {cpu(k): cpu(v) for k, v in (em1 | em2).items()},
              'base_bytes': len(first), 'alt_bytes': len(second), 'slot_growth': growth}
    if moved:
        layout['override_table'], layout['override_find'] = cpu(table), cpu(find)
    return {'format': 'dq5patch/1', 'name': 'npc-relocate', 'rom_size': 2, 'writes': writes}, layout


def condition_writes(rom, edited, moved_lists):
    """대체 표 포인터를 옮긴 목록으로 바꾸고, 고친 조건 항목은 조건과 포인터를 한 번에 쓴다. [(주소, 바이트, 설명)]."""
    out = []
    for i in range(OVERRIDE_COUNT):
        row = OVERRIDE_LISTS + i * 6
        head = edited.get(row, read(rom, row, 6))
        old = 0x100000 | head[4] | head[5] << 8
        if old not in moved_lists:
            raise ValueError(f'대체 표 {i}: 목록 시작점이 아닌 포인터')
        pointer = (moved_lists[old] & 0xFFFF).to_bytes(2, 'little')
        if row in edited:
            out.append((row, head[:4] + pointer, f'대체 표 {i} 조건과 목록 주소'))
        else:
            out.append((row + 4, pointer, f'대체 표 {i} 목록 주소'))
    out.extend((at, edited[at], '빈 맵 표 조건') for at in sorted(edited) if NO_NPC <= at < OVERRIDE_LISTS)
    return out


def apply_manifest(rom, manifest):
    data = bytearray(rom.d) + bytes(max(0, 0x200000 - len(rom.d)))
    for item in manifest['writes']:
        off = lorom(int(item['at'].replace(':', ''), 16))
        raw = bytes.fromhex(item['hex'])
        if 'orig' in item and data[off:off + len(raw)] != bytes.fromhex(item['orig']):
            raise ValueError('패치 원본이 다름')
        data[off:off + len(raw)] = raw
    return Rom(data)


def check(rom):
    manifest, layout = patch(rom, dump(rom))
    moved = apply_manifest(rom, manifest)
    entries = scripts = placed = native_refs = 0
    for old, target in layout['lists'].items():
        old, target = int(old.replace(':', ''), 16), int(target.replace(':', ''), 16)
        before, after = list_entries(rom, old), list_entries(moved, target)
        if len(before) != len(after):
            raise ValueError('재배치 후 인물 수가 달라짐')
        for (a, n), (b, m) in zip(before, after):
            if n != m or read(rom, a, n) != read(moved, b, m):
                raise ValueError(f'{cpu(a)} 인물 레코드 바이트가 달라짐')
            entries += 1
        for night in (False, True):
            p1 = [(a, f) for a, _ in before if (f := parse(rom, a, night))]
            p2 = [(a, f) for a, _ in after if (f := parse(moved, a, night))]
            v1, v2 = table_values(rom, p1), table_values(moved, p2)
            for (a, f), (_, g), x, y in zip(p1, p2, v1, v2):
                if f['script'] is not None:
                    wanted = int(layout['scripts'][cpu(f['script'])].replace(':', ''), 16)
                    if g['script'] != wanted:
                        raise ValueError(f'{cpu(a)} 스크립트 포인터가 다름')
                for key in x.keys() - {0x3480, 0x34A0}:
                    if x[key] != y[key]:
                        raise ValueError(f'{cpu(a)} 인물 표 {key:04X}가 다름')
                placed += 1
    for old, target in layout['scripts'].items():
        if script_bytes(rom, int(old.replace(':', ''), 16)) != script_bytes(moved, int(target.replace(':', ''), 16)):
            raise ValueError('스크립트 바이트가 다름')
        for _, raw, _ in script_ops(script_bytes(rom, int(old.replace(':', ''), 16))):
            if raw[0] in (0x05, 0x37):
                addr = int.from_bytes(raw[1:], 'little')
                native_refs += int(BASE_START <= addr < BASE_END or ALT_START <= addr < ALT_END)
        scripts += 1
    print(f'목록 {len(layout["lists"])}개, 인물 {entries}개, 낮·밤 인물 {placed}개, 스크립트 {scripts}개 일치; '
          f'기본 {layout["base_bytes"]}바이트, 대체 {layout["alt_bytes"]}바이트; '
          f'05·37의 원본 목록 영역 호출 {native_refs}개')


def new_map(text):
    if not re.fullmatch(r'[0-9A-F]{2}/[0-9A-F]{2}', text):
        raise argparse.ArgumentTypeError('--new-map 은 대문자 16진 GG/MM')
    return tuple(int(v, 16) for v in text.split('/'))


def new_maps_from(rom, given, newmap_doc):
    """--new-map 과 dq5newmap 문서의 새 맵을 맞춘다. 문서가 더하는 맵을 빠뜨리면 그 맵이 다음 그룹 첫 목록을 읽기 때문이다."""
    if any(bc >= 0x50 for bc, _ in given):
        raise ValueError('--new-map 은 그룹 50 미만만 받음(그룹 50 이상은 기본 인물 목록을 읽지 않음, 12:801C)')
    if newmap_doc is None:
        return given
    doc = json.loads(newmap_doc.read_text(encoding='utf-8'))
    if not isinstance(doc, dict) or doc.get('format') != 'dq5newmap/1' or not isinstance(doc.get('maps'), list):
        raise ValueError(f'{newmap_doc}: dq5newmap/1 문서가 아님')
    known = set(all_maps(rom))
    added = []
    for row in doc['maps']:
        name = row.get('map') if isinstance(row, dict) else None
        if not isinstance(name, str) or not re.fullmatch(r'[0-9A-F]{2}/[0-9A-F]{2}', name):
            raise ValueError(f'{newmap_doc}: map 은 대문자 GG/MM')
        key = tuple(int(v, 16) for v in name.split('/'))
        # 그룹 50 이상은 기본 인물 목록을 읽지 않으므로(12:801C) 고층 새 맵은 인물 목록 대상이 아니다.
        if key not in known and key[0] < 0x50:
            added.append(key)
    if given and sorted(set(given)) != sorted(added):
        raise ValueError('--new-map ' + ' '.join(f'{a:02X}/{b:02X}' for a, b in sorted(set(given))) + ' 이 dq5newmap 문서의 새 맵 '
                         + ' '.join(f'{a:02X}/{b:02X}' for a, b in sorted(added)) + ' 과 다름')
    return added


def save(path, value):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('rom')
    sub = parser.add_subparsers(dest='command', required=True)
    exp = sub.add_parser('dump')
    exp.add_argument('-o', '--out', required=True)
    write = sub.add_parser('patch')
    write.add_argument('source')
    write.add_argument('-o', '--out', required=True)
    write.add_argument('--base', default='32:8000')
    write.add_argument('--alt', default='33:8000')
    write.add_argument('--report')
    write.add_argument('--records', help='dq5npcrecord/1 문서. 레코드·조건 표 수정을 옮기는 사본에 넣는다')
    write.add_argument('--new-map', action='append', default=[], type=new_map,
                       help='dq5newmap.py 로 더할 맵 GG/MM(여럿이면 되풀이). 그 그룹 마지막 목록 뒤에 기본 목록을 둔다')
    write.add_argument('--newmap-doc', type=Path,
                       help='dq5newmap/1 문서. 원래 롬에 없는 맵을 새 맵으로 받고, --new-map 을 함께 주면 둘이 같은지 본다')
    write.add_argument('--allow-growth', action='store_true',
                       help='맵의 원본 최대 대신 슬롯 1F 까지 인물을 늘림(맵에서 04:FB1C 등이 더 쓰는 슬롯은 따지지 않음)')
    sub.add_parser('check')
    args = parser.parse_args()
    try:
        with open(args.rom, 'rb') as f:
            rom = Rom(f.read())
        if args.command == 'check':
            check(rom)
            return 0
        if args.command == 'dump':
            save(args.out, dump(rom))
        else:
            with open(args.source, encoding='utf-8') as f:
                doc = json.load(f)
            records = None
            if args.records:
                with open(args.records, encoding='utf-8') as f:
                    records = json.load(f)
            manifest, layout = patch(rom, doc, destination(args.base), destination(args.alt), records, args.allow_growth,
                                     new_maps_from(rom, args.new_map, args.newmap_doc))
            for line in layout['slot_growth']:
                print(f'원본보다 많은 슬롯: {line}')
            save(args.out, manifest)
            if args.report:
                save(args.report, layout)
        print(f'{args.command} → {args.out}')
        return 0
    except (ValueError, OSError, IndexError) as error:
        print(f'오류: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
