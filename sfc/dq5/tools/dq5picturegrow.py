"""DQ5 인물 그림 번호 표(25:86D0)를 늘려 옮기고, 말을 걸 수 없는 물체 그림을 표로 고른다.

원래 롬은 그림 번호 00~A8(169개)만 세트로 바꾸고(1F:CF45·03:D202 가 25:86D0,X 를 범위 검사 없이 읽음),
1E:DC67 이 그림 46~48·78·7F·84·A2 이상을 물체(7E:33A0 |= 09, 말을 걸 수 없고 지나갈 수 있음)로 만든다.
이 도구는 --at 에 [물체 판정 루틴][그림 표 N개][물체 표 256개] 를 두고 두 읽기의 주소와 1E:DC67 을 고친다.
형식: sfc/dq5/docs/dq5-graphics-format.md 의 「그림 번호와 세트」, sfc/dq5/docs/dq5-build-format.md 의 `dq5pictures/1`.

  python sfc/dq5/tools/dq5picturegrow.py rom/dq5.sfc dump -o work/pictures/dump.json
  python sfc/dq5/tools/dq5picturegrow.py rom/dq5.sfc patch work/pictures/edit.json --at 16:FE10 -o work/build/pictures.dq5patch.json
  python sfc/dq5/tools/dq5picturegrow.py rom/dq5.sfc check [work/pictures/edit.json] --at 16:FE10
"""
import argparse
import json
import re
import sys
from pathlib import Path

from dq5map import Rom, lorom

FORMAT = 'dq5pictures/1'
TABLE, COUNT = 0x2586D0, 0xA9
# 그림 표를 읽는 LDA long,X 두 곳(롬 전체에서 25:86D0 을 24비트 피연산자로 읽는 곳은 이 둘뿐).
READERS = (0x1FCF45, 0x03D202)
HOOK = 0x1EDC67
HOOK_ORIG = bytes.fromhex('a5 0a c9 84 f0 14')
# 1E:DC67 의 원래 판정: 그림이 84·78·7F, A2 이상, 46~48 이면 물체.
ORIGINAL_OBJECTS = {0x84, 0x78, 0x7F, *range(0xA2, 0x100), 0x46, 0x47, 0x48}
ROUTINE_SIZE = 15
# 말을 걸 대상을 찾는 05:8558 이 부르는 05:85F8 은 그림이 이 목록에 있으면 대상에서 뺀다(FF 로 끝).
# 04/03 에서는 그림 03·04·52 도 뺀다(05:860D, 코드에 박힘).
TALK_READER, TALK_LIST = 0x0585FE, 0x05862F
# 그림 9A 는 1F:CF32 가 97·2F 칸을 대신 읽어 표의 9A 칸이 쓰이지 않고, FF 는 말 걸기 목록의 끝 표시다.
RESERVED = {0x9A, 0xFF}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def text(addr):
    return f'{addr >> 16:02X}:{addr & 0xFFFF:04X}'


def address(value, name):
    require(isinstance(value, str) and re.fullmatch(r'[0-9A-Fa-f]{2}:[0-9A-Fa-f]{4}', value) is not None,
            f'{name}: BB:AAAA 형태여야 함')
    bank, addr = (int(v, 16) for v in value.split(':'))
    require(addr >= 0x8000 and (bank & 0x7F) < 0x7E, f'{name}: 롬에 닿지 않는 주소 {value}')
    return bank << 16 | addr


def hexbyte(value, name):
    require(isinstance(value, str) and re.fullmatch(r'[0-9A-Fa-f]{2}', value) is not None, f'{name}: 16진 두 자리')
    return int(value, 16)


def read(rom, addr, size):
    off = lorom(addr)
    raw = bytes(rom.d[off:off + size])
    require(len(raw) == size, f'{text(addr)}: 롬 범위 밖')
    return raw


def routine(table_objects):
    """1E:DC67 에서 JSL 로 부르는 물체 판정. 8비트 A·X, Y = 슬롯. 물체 표 값(00 또는 09)을 7E:33A0,Y 에 OR 한다."""
    t = table_objects.to_bytes(3, 'little')
    return bytes([0xDA, 0xA6, 0x0A, 0xBF, *t, 0x19, 0xA0, 0x33, 0x99, 0xA0, 0x33, 0xFA, 0x6B])


def talk_list(rom):
    raw = read(rom, TALK_READER, 4)
    require(raw[0] == 0xBF, f'{text(TALK_READER)}: 말 걸기 목록 읽기 명령이 원본과 다름')
    addr, out = int.from_bytes(raw[1:], 'little'), []
    while (v := read(rom, addr + len(out), 1)[0]) != 0xFF:
        out.append(v)
        require(len(out) < 256, '말 걸기 목록 끝 FF 를 찾지 못함')
    return addr, out


def set_tiles(rom, s):
    """세트의 타일 수(1F:CF1E 가 이만큼 OBJ VRAM 을 잡음). 레코드를 못 읽으면 None."""
    from dq5sprite import set_record
    record = set_record(rom, s)
    return None if record is None else record['tiles']


def valid_sets(rom):
    """포인터가 FFFF 가 아닌 세트. dq5spritewrite.py --sets-at 으로 옮긴 표면 그 표를 읽는다."""
    from dq5sprite import set_numbers, set_table
    table = set_table(rom)[0]
    return {s for s in set_numbers(rom) if int.from_bytes(read(rom, table + s * 2, 2), 'little') != 0xFFFF}


def layout(rom):
    """(그림 표 주소, 그림 수, 물체 표 주소 또는 None). 옮긴 롬이면 루틴 자리에서 읽는다."""
    bases = set()
    for at in READERS:
        raw = read(rom, at, 4)
        require(raw[0] == 0xBF, f'{text(at)}: 그림 표 읽기 명령이 원본과 다름')
        bases.add(int.from_bytes(raw[1:], 'little'))
    require(len(bases) == 1, '그림 표를 읽는 두 곳의 주소가 다름')
    base = bases.pop()
    hook = read(rom, HOOK, 6)
    if hook == HOOK_ORIG:
        require(base == TABLE, '물체 판정은 원본인데 그림 표만 옮겨진 롬')
        return base, COUNT, None
    require(hook[0] == 0x22 and hook[4:] == b'\x80\x1c', '1E:DC67 이 원본도 이 도구의 꼴도 아님')
    code = int.from_bytes(hook[1:4], 'little')
    raw = read(rom, code, ROUTINE_SIZE)
    objects = int.from_bytes(raw[4:7], 'little')
    require(raw == routine(objects), f'{text(code)}: 물체 판정 루틴이 이 도구의 꼴이 아님')
    require(base == code + ROUTINE_SIZE, '그림 표가 루틴 바로 뒤에 있지 않음')
    count = objects - base
    require(1 <= count <= 256, '그림 표 길이를 알 수 없음')
    return base, count, objects


def dump(rom):
    base, count, objects = layout(rom)
    table = read(rom, base, count)
    flags = read(rom, objects, 256) if objects else None
    skip = set(talk_list(rom)[1])
    return {'format': FORMAT, 'table': text(base), 'pictures': [
        {'picture': f'{g:02X}', 'set': f'{table[g]:02X}',
         'object': (flags[g] != 0) if flags else g in ORIGINAL_OBJECTS, 'talk_skip': g in skip} for g in range(count)]}


def patch(rom, doc, at, new_sets=()):
    require(isinstance(doc, dict) and set(doc) <= {'format', 'table', 'pictures'} and doc.get('format') == FORMAT,
            'format/pictures 가 잘못됨')
    rows = doc.get('pictures', [])
    require(isinstance(rows, list), 'pictures: 배열이어야 함')
    before = dump(rom)
    current = {int(p['picture'], 16): p for p in before['pictures']}
    # 그림 번호마다 원래 세트의 타일 수. 1F:CF1E 가 세트 타일 수만큼 VRAM 을 잡으므로 넘지 못하게 한다.
    limit = {g: set_tiles(rom, int(p['set'], 16)) for g, p in current.items()}
    # dq5spritewrite.py 가 같은 빌드에서 새로 채우는 세트(70~7F, 표를 늘리면 A5~FF)는 --new-sets 로 받는다.
    sets = valid_sets(rom) | set(new_sets)
    seen = set()
    for row in rows:
        require(isinstance(row, dict) and set(row) <= {'picture', 'set', 'object', 'talk_skip'}, f'항목 {row}: 필드가 잘못됨')
        g = hexbyte(row.get('picture'), 'picture')
        require(g not in seen, f'그림 {g:02X} 를 두 번 지정함')
        seen.add(g)
        old = current.get(g)
        require(g not in RESERVED or (old is not None and all(row.get(k, old[k]) == old[k] for k in old)),
                f'그림 {g:02X}: 9A 는 표 칸이 읽히지 않고 FF 는 말 걸기 목록 끝 표시라 바꾸거나 더할 수 없음')
        require(old is not None or 'set' in row, f'그림 {g:02X}: 새 그림에는 set 이 필요함')
        merged = dict(old or {'picture': f'{g:02X}', 'object': False, 'talk_skip': False}) | row
        s = hexbyte(merged['set'], f'그림 {g:02X} set')
        require(s in sets, f'그림 {g:02X}: 포인터가 없는 세트 {s:02X}')
        if old is not None and s != int(old['set'], 16) and s not in new_sets and limit.get(g) is not None:
            tiles = set_tiles(rom, s)
            require(tiles is None or tiles <= limit[g], f'그림 {g:02X} → 세트 {s:02X} 타일 {tiles}개가 원래 세트의 {limit[g]}개를 넘음')
        for flag in ('object', 'talk_skip'):
            require(type(merged[flag]) is bool, f'그림 {g:02X}: {flag} 는 true/false')
        current[g] = {'picture': f'{g:02X}', 'set': f'{s:02X}', 'object': merged['object'], 'talk_skip': merged['talk_skip']}
    count = max(current) + 1
    require(set(current) == set(range(count)), '그림 번호 사이에 빈 번호가 있음')
    if 'table' in doc:
        require(address(doc['table'], 'table') in (at + ROUTINE_SIZE, TABLE, address(before['table'], 'table')),
                'table 은 원래 자리·지금 자리·--at 뒤 그림 표 자리 가운데 하나여야 함')
    # 원래 말 걸기 목록에서 표 밖 번호(FE 등)는 그대로 남긴다.
    skip = sorted({g for g, p in current.items() if p['talk_skip']} | {g for g in talk_list(rom)[1] if g >= count})
    table, objects = at + ROUTINE_SIZE, at + ROUTINE_SIZE + count
    talk = objects + 256
    size = ROUTINE_SIZE + count + 256 + len(skip) + 1
    require((at & 0xFFFF) + size <= 0x10000, '--at 에서 뱅크를 넘음')
    for fixed in (HOOK, *READERS, TALK_READER):
        require(not at <= fixed < at + size, f'--at 자리가 고치는 코드 {text(fixed)} 와 겹침')
    blob = (routine(objects) + bytes(int(current[g]['set'], 16) for g in range(count))
            + bytes(0x09 if (g in current and current[g]['object']) or (g >= count and g in ORIGINAL_OBJECTS) else 0
                    for g in range(256)) + bytes(skip) + b'\xff')
    wanted = {at: (blob, '그림 표·물체 표·판정 루틴·말 걸기 목록')}
    for reader in READERS:
        wanted[reader + 1] = (table.to_bytes(3, 'little'), '그림 표 주소')
    wanted[TALK_READER + 1] = (talk.to_bytes(3, 'little'), '말 걸기 목록 주소')
    wanted[HOOK] = (bytes([0x22, *(at.to_bytes(3, 'little')), 0x80, 0x1C]), '물체 판정을 표로')
    writes, size = [], 0
    for addr, (raw, note) in sorted(wanted.items()):
        if lorom(addr) >= len(rom.d):
            # 늘린 롬의 새 뱅크는 원래 롬에 없으므로 orig 없이 쓰고 롬 크기를 4MB 로 늘린다.
            writes.append({'at': text(addr), 'hex': raw.hex(' '), 'note': note})
            size = 4
            continue
        old = read(rom, addr, len(raw))
        if old != raw:
            writes.append({'at': text(addr), 'hex': raw.hex(' '), 'orig': old.hex(' '), 'note': note})
    out = {'format': 'dq5patch/1', 'name': 'pictures', 'writes': writes}
    if size:
        out['rom_size'] = size
    return out


def check(rom, doc, at, new_sets=()):
    from dq5build import build, parse_at
    source = dump(rom) if doc is None else doc
    result = patch(rom, source, at, new_sets)
    lists = [('pictures', result.get('rom_size', 0), [
        (parse_at(w['at'])[0], bytes.fromhex(w['hex']), bytes.fromhex(w['orig']) if 'orig' in w else None, w['note'])
        for w in result['writes']])]
    rebuilt, _ = build(rom.d, lists, result.get('rom_size', 0))
    after = Rom(rebuilt)
    again_writes = [w for w in patch(after, source, at, new_sets)['writes'] if 'orig' in w]
    require(not again_writes, '빌더 적용 후 같은 입력을 다시 패치하면 쓰기가 남음')
    again = dump(after)
    require(again['table'] == text(at + ROUTINE_SIZE), '빌드한 롬의 그림 표 자리가 다름')
    want = {p['picture']: p for p in dump(rom)['pictures']} | {p['picture']: p for p in patch_rows(rom, source)}
    require({p['picture']: p for p in again['pictures']} == want, '빌드한 롬을 다시 읽은 값이 입력과 다름')
    require(talk_list(after)[0] == at + ROUTINE_SIZE + len(again['pictures']) + 256, '말 걸기 목록 자리가 다름')
    if doc is None:
        require(again['pictures'] == dump(rom)['pictures'], '원본 왕복이 다름')
    print(f'그림 {len(again["pictures"])}개(표 {again["table"]}), 쓰기 {len(result["writes"])}개 검사 통과')


def patch_rows(rom, doc):
    current = {p['picture']: p for p in dump(rom)['pictures']}
    out = []
    for row in doc.get('pictures', []):
        g = row['picture'].upper()
        merged = dict(current.get(g, {'picture': g, 'object': False, 'talk_skip': False})) | row
        out.append({'picture': g, 'set': merged['set'].upper(), 'object': merged['object'], 'talk_skip': merged['talk_skip']})
    return out


def sets_arg(value):
    out = [hexbyte(v.strip(), '--new-sets') for v in value.split(',') if v.strip()]
    require(all(0x70 <= v <= 0x7F or v >= 0xA5 for v in out), '--new-sets 는 70~7F 와 A5~FF(dq5spritewrite.py --sets-at)')
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('rom', type=Path)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('dump').add_argument('-o', '--out', type=Path)
    for name in ('patch', 'check'):
        p = sub.add_parser(name)
        p.add_argument('source', type=Path, nargs='?' if name == 'check' else None)
        p.add_argument('--at', required=True, help='루틴·그림 표·물체 표를 둘 자리 BB:AAAA')
        if name == 'patch':
            p.add_argument('-o', '--out', type=Path)
        p.add_argument('--new-sets', default='', help='같은 빌드에서 dq5spritewrite.py 가 더하는 세트 번호(16진, 쉼표)')
    args = parser.parse_args()
    try:
        rom = Rom(args.rom.read_bytes())
        doc = json.loads(args.source.read_text(encoding='utf-8')) if getattr(args, 'source', None) else None
        if args.command == 'check':
            check(rom, doc, address(args.at, '--at'), sets_arg(args.new_sets))
            return 0
        out = dump(rom) if args.command == 'dump' else patch(rom, doc, address(args.at, '--at'), sets_arg(args.new_sets))
        body = json.dumps(out, ensure_ascii=False, indent=2) + '\n'
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(body, encoding='utf-8')
        else:
            print(body, end='')
        return 0
    except (ValueError, OSError, KeyError) as error:
        print(f'오류: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
