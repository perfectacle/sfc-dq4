"""DQ5 실내 BG 팔레트 세트 표(10:DEBC) 쓰기·늘리기. 형식은 sfc/dq5/docs/dq5-build-format.md 「팔레트 세트 표」.

표는 그룹마다 [$BC][기본 세트]([$BD][세트])…[FF] 이고 표 끝은 FF 하나다. 10:DE0B 가 처음부터 $BC 를 찾고, 맞는 그룹 안에서
$BD 를 찾아 없으면 기본 세트를 쓴다. 그룹이 표에 없으면 CLC 로 돌아가 팔레트를 읽지 않는다. 세트 번호는 목록 표
10:DFE4(세트마다 낮·밤 16비트 포인터 둘)의 번호다.

표 바로 뒤가 목록 표이고 뱅크 10 의 빈 자리는 32바이트뿐이라, 원래 크기(296바이트)를 넘으면 --table-at 자리에
[찾기 루틴][표] 를 두고 10:DE0B 를 JSL 로 바꾼다. 루틴은 원래 찾기와 같은 순서로 표를 긴 주소로 읽어 $00 에 세트를 두고
SEC·RTL(찾음) 또는 CLC·RTL(없음)로 돌아온다. 10:DE0B 의 남은 자리는 JMP 로 원래 다음 명령(10:DE43)에 이어진다.

  python sfc/dq5/tools/dq5palsetwrite.py rom/dq5.sfc dump -o work/palset.json
  python sfc/dq5/tools/dq5palsetwrite.py rom/dq5.sfc patch work/palset.json -o work/palset.dq5patch.json \\
      [--table-at BB:AAAA] [--new-map GG/MM …]
  python sfc/dq5/tools/dq5palsetwrite.py rom/dq5.sfc check [work/palset.json --table-at … --new-map …]

입력: {"format": "dq5palset/1", "groups": [{"group": "36", "default": 6, "maps": [{"map": "00", "set": 19}]}]}
groups 에 적은 그룹은 그 항목 전체(기본 세트와 맵 목록)를 바꾸고, 적지 않은 그룹은 원래 항목을 그대로 둔다. 새 그룹은
표 끝에 붙인다. 그룹·맵은 롬에 있거나 --new-map 으로 알린 것만 받는다(그룹 50 이상의 맵 번호는 50 부터). 원래 표에
있던 맵 번호(52/00 처럼 없는 맵을 가리키는 것)는 그대로 받는다.
"""
import argparse
import json
import re
import sys
from pathlib import Path

from dq5build import PatchError, build
from dq5map import HIGH_GROUPS, PALSET_LISTS, PALSET_TABLE, Rom, group_spans, lorom, palset_table

FORMAT = 'dq5palset/1'
HIGH_FIRST = 0x50
LOADER = 0x10DE0B
# 10:DE0B~DE14 원래 명령: SEP #$20 / REP #$10 / LDX #$0000 / LDA $DEBC,X / CMP #$FF / BEQ … (그 뒤 DEBC 읽기 넷이 더 있음)
LOADER_ORIG = bytes.fromhex('e2 20 c2 10 a2 00 00 bd bc de')
# 찾은 뒤 원래 루틴이 이어 가는 곳(STZ $01 부터 목록 포인터 읽기)
LOADER_NEXT = 0x10DE43
ORIGINAL_SIZE = 296


def cpu(addr):
    return f'{addr >> 16:02X}:{addr & 0xFFFF:04X}'


def hex_key(value, name, size=2):
    if not isinstance(value, str) or not re.fullmatch(f'[0-9A-F]{{{size}}}', value):
        raise ValueError(f'{name}: 대문자 16진 {size}자리 문자열이어야 함')
    return int(value, 16)


def set_count(rom):
    """목록 표 10:DFE4 의 세트 수. 첫 목록이 표 바로 뒤에서 시작한다(원본 69세트)."""
    first = rom.u16(PALSET_LISTS)
    if first <= PALSET_LISTS & 0xFFFF or (first - (PALSET_LISTS & 0xFFFF)) % 4:
        raise ValueError(f'{cpu(PALSET_LISTS)}: 팔레트 목록 표의 첫 포인터가 맞지 않음')
    return (first - (PALSET_LISTS & 0xFFFF)) // 4


def parse_table(rom, at):
    """[(BC, 기본, [(BD, 세트)…])] 와 끝 FF 까지의 바이트 수."""
    def byte(a):
        if a - at > 0x4000 or lorom(a) >= len(rom.d):
            raise ValueError(f'{cpu(at)}: 팔레트 세트 표의 끝 FF 가 없음')
        return rom.d[lorom(a)]

    groups, a = [], at
    while byte(a) != 0xFF:
        bc, default, maps = byte(a), byte(a + 1), []
        a += 2
        while byte(a) != 0xFF:
            maps.append((byte(a), byte(a + 1)))
            a += 2
        a += 1
        groups.append((bc, default, maps))
    return groups, a + 1 - at


def encode(groups):
    return b''.join(bytes([bc, default, *(v for pair in maps for v in pair), 0xFF]) for bc, default, maps in groups) + b'\xff'


def original_keys(groups):
    """원래 표에 이미 있는 (BC, BD). 52/00 처럼 없는 맵을 가리키는 항목도 있어 그대로 다시 쓸 수 있게 한다."""
    return {(bc, bd) for bc, _, maps in groups for bd, _ in maps}


def known_maps(rom, new_maps=()):
    """{그룹: 맵 번호 집합}. 그룹 50 미만은 맵 포인터 그룹, 50 이상은 고층 그룹(맵 번호 50~), --new-map 을 더한다."""
    out = {g: set(range((e - s) // 3)) for g, (s, e) in enumerate(group_spans(rom)[0])}
    for i, (s, e) in enumerate(group_spans(rom, kind='high')[0]):
        out[HIGH_FIRST + i] = set(range(HIGH_FIRST, HIGH_FIRST + (e - s) // 3))
    count = len(group_spans(rom)[0])
    new = sorted({bc for bc, _ in new_maps if count <= bc < HIGH_FIRST})
    if new != list(range(count, count + len(new))):
        raise ValueError(f'--new-map 의 새 그룹은 {count:02X} 부터 빈 번호 없이 50 미만이어야 함')
    for bc, bd in new_maps:
        if bc >= HIGH_FIRST and bc not in out:
            raise ValueError(f'--new-map {bc:02X}/{bd:02X}: 그룹 50 이상의 새 그룹은 받지 않음')
        out.setdefault(bc, set()).add(bd)
    return out


def group_rows(doc, maps, sets, original=()):
    if not isinstance(doc, dict) or set(doc) - {'format', 'groups'} or doc.get('format') != FORMAT:
        raise ValueError(f'문서는 format={FORMAT}, groups 만 담아야 함')
    rows = doc.get('groups', [])
    if not isinstance(rows, list):
        raise ValueError('groups 는 배열이어야 함')
    out = {}
    for i, row in enumerate(rows):
        name = f'groups[{i}]'
        if not isinstance(row, dict) or set(row) - {'group', 'default', 'maps'} or {'group', 'default'} - set(row):
            raise ValueError(f'{name}: group·default(·maps)만 받음')
        bc = hex_key(row['group'], f'{name}.group')
        if bc not in maps:
            raise ValueError(f'{name}: 그룹 {bc:02X} 이 롬에 없음(새 그룹은 --new-map 으로 알림)')
        if bc in out:
            raise ValueError(f'{name}: 그룹 {bc:02X} 을 두 번 적음')
        default = row['default']
        if type(default) is not int or not 0 <= default < sets:
            raise ValueError(f'{name}.default: 세트 번호는 0~{sets - 1} 정수여야 함')
        listed = row.get('maps', [])
        if not isinstance(listed, list):
            raise ValueError(f'{name}.maps: 배열이어야 함')
        pairs = []
        for j, item in enumerate(listed):
            where = f'{name}.maps[{j}]'
            if not isinstance(item, dict) or set(item) != {'map', 'set'}:
                raise ValueError(f'{where}: map·set 만 받음')
            bd = hex_key(item['map'], f'{where}.map')
            if bd not in maps[bc] and (bc, bd) not in original:
                raise ValueError(f'{where}: 맵 {bc:02X}/{bd:02X} 이 롬에 없음(새 맵은 --new-map 으로 알림)')
            if any(bd == b for b, _ in pairs):
                raise ValueError(f'{where}: 맵 {bc:02X}/{bd:02X} 을 두 번 적음')
            if type(item['set']) is not int or not 0 <= item['set'] < sets:
                raise ValueError(f'{where}.set: 세트 번호는 0~{sets - 1} 정수여야 함')
            pairs.append((bd, item['set']))
        out[bc] = (default, pairs)
    return out


def assemble(at):
    """at 에 두는 찾기 루틴(뒤에 표가 붙음). 원래 10:DE0B~DE42 와 같은 차례로 표를 읽는다."""
    code, fix, labels = bytearray(), [], {}

    def long_x(plus=0):
        code.extend(b'\xbf')
        fix.append((len(code), 'table', plus))
        code.extend(b'\0\0\0')

    def branch(op, label):
        code.extend(bytes([op, 0]))
        fix.append((len(code) - 1, label, None))

    def label(name):
        labels[name] = len(code)

    code.extend(bytes.fromhex('e2 20 c2 10 a2 00 00'))  # SEP #$20 / REP #$10 / LDX #$0000
    label('group')
    long_x()                                        # LDA 표,X
    code.extend(b'\xc9\xff')                        # CMP #$FF
    branch(0xF0, 'none')
    code.extend(b'\xc5\xbc')                        # CMP $BC
    branch(0xF0, 'found')
    label('skip')
    code.extend(b'\xe8\xe8')                        # INX / INX
    long_x()
    code.extend(b'\xc9\xff')
    branch(0xD0, 'skip')
    code.extend(b'\xe8')
    branch(0x80, 'group')
    label('found')
    code.extend(b'\xe8')
    long_x()                                        # 기본 세트
    code.extend(b'\x85\x00')                        # STA $00
    label('map')
    code.extend(b'\xe8')
    long_x()
    code.extend(b'\xc9\xff')
    branch(0xF0, 'done')
    code.extend(b'\xc5\xbd')                        # CMP $BD
    branch(0xF0, 'hit')
    code.extend(b'\xe8')
    branch(0x80, 'map')
    label('hit')
    long_x(1)                                       # 그 맵의 세트
    code.extend(b'\x85\x00')
    label('done')
    code.extend(b'\x38\x6b')                        # SEC / RTL
    label('none')
    code.extend(b'\x18\x6b')                        # CLC / RTL
    table = at + len(code)
    for pos, name, plus in fix:
        if name == 'table':
            code[pos:pos + 3] = (table + plus).to_bytes(3, 'little')
        else:
            offset = labels[name] - (pos + 1)
            if not -128 <= offset <= 127:
                raise ValueError('찾기 루틴 분기 거리가 넘침')
            code[pos] = offset & 0xFF
    return bytes(code)


def stub_length():
    return len(assemble(0x008000))


def lorom_cpu(at):
    if not re.fullmatch(r'[0-9A-Fa-f]{2}:[0-9A-Fa-f]{4}', at or ''):
        raise ValueError(f'--table-at {at!r}: BB:AAAA 로 적어야 함')
    b, a = int(at[:2], 16), int(at[3:], 16)
    if not (0 <= b <= 0x7D and 0x8000 <= a <= 0xFFFF):
        raise ValueError(f'--table-at {at}: 뱅크 00~7D, AAAA 8000~FFFF 여야 함')
    return b << 16 | a


def writes_for(rom, doc, table_at=None, new_maps=()):
    """(주소, 새 값, 원본|None, 설명)."""
    current = palset_table(rom)
    if current != PALSET_TABLE:
        raise ValueError(f'팔레트 세트 표가 이미 {cpu(current)} 로 옮겨진 롬: 원본 롬에서 다시 만듦')
    if rom.d[lorom(LOADER):lorom(LOADER) + len(LOADER_ORIG)] != LOADER_ORIG:
        raise ValueError(f'{cpu(LOADER)}: 원래 팔레트 세트 찾기 명령이 아님')
    groups, size = parse_table(rom, PALSET_TABLE)
    if size != ORIGINAL_SIZE:
        raise ValueError(f'원래 팔레트 세트 표 크기가 {ORIGINAL_SIZE}바이트가 아님({size})')
    edits = group_rows(doc, known_maps(rom, new_maps), set_count(rom), original_keys(groups))
    out = [(bc, *edits.pop(bc)) if bc in edits else (bc, default, maps) for bc, default, maps in groups]
    out += [(bc, *edits[bc]) for bc in sorted(edits)]
    blob = encode(out)
    if table_at is None:
        if len(blob) > ORIGINAL_SIZE:
            raise ValueError(f'팔레트 세트 표 {len(blob)}바이트가 원래 자리 {ORIGINAL_SIZE}바이트를 넘음(--table-at 이 필요함)')
        old = rom.d[lorom(PALSET_TABLE):lorom(PALSET_TABLE) + len(blob)]
        return [(PALSET_TABLE, blob, bytes(old), '팔레트 세트 표')]
    at = lorom_cpu(table_at)
    code = assemble(at)
    if (at & 0xFFFF) + len(code) + len(blob) > 0x10000:
        raise ValueError(f'찾기 루틴·표 {len(code) + len(blob)}바이트가 {table_at} 의 뱅크 끝을 넘음')
    hook = bytes([0x22, *at.to_bytes(3, 'little'), 0xB0, 0x01, 0x60, 0x4C, *(LOADER_NEXT & 0xFFFF).to_bytes(2, 'little')])
    # 새 자리는 orig 를 붙이지 않는다. 빌더가 빈 자리 지도 밖이면 거부하게 하기 위해서다.
    return [(at, code + blob, None, f'팔레트 세트 찾기 루틴·표({len(out)}그룹)'),
            (LOADER, hook, LOADER_ORIG, '팔레트 세트 찾기를 옮긴 루틴으로(JSL, 없으면 RTS, 찾으면 DE43)')]


def patch(rom, doc, table_at=None, new_maps=()):
    writes = []
    top = 0
    for addr, new, old, note in writes_for(rom, doc, table_at, new_maps):
        if new == old:
            continue
        write = {'at': cpu(addr), 'hex': new.hex(' '), 'note': note}
        if old is not None:
            write['orig'] = old.hex(' ')
        writes.append(write)
        top = max(top, addr >> 16)
    result = {'format': 'dq5patch/1', 'name': 'palette-sets', 'writes': writes}
    size = 0 if top < 0x30 else 2 if top < 0x40 else 3 if top < 0x60 else 4
    if size:
        result['rom_size'] = size
    return result


def dump(rom):
    groups, _ = parse_table(rom, palset_table(rom))
    return {'format': FORMAT, 'groups': [
        {'group': f'{bc:02X}', 'default': default, 'maps': [{'map': f'{bd:02X}', 'set': s} for bd, s in maps]}
        for bc, default, maps in groups]}


def check(rom, doc=None, table_at=None, new_maps=()):
    """만든 롬을 dq5map.palette_set 으로 다시 읽어, 모든 맵의 세트가 입력대로인지 본다."""
    from dq5map import palette_set
    doc = doc or dump(rom)
    manifest = patch(rom, doc, table_at, new_maps)
    mb = manifest.get('rom_size', 0)
    writes = [(lorom(int(w['at'][:2], 16) << 16 | int(w['at'][3:], 16)), bytes.fromhex(w['hex']),
               bytes.fromhex(w['orig']) if 'orig' in w else None, w['note']) for w in manifest['writes']]
    built = Rom(build(rom.d, [('palette-sets', mb, writes)], mb)[0])
    maps = known_maps(rom, new_maps)
    edits = group_rows(doc, maps, set_count(rom), original_keys(parse_table(rom, PALSET_TABLE)[0]))
    checked = 0
    for bc in sorted(maps):
        for bd in sorted(maps[bc]):
            if bc in edits:
                default, pairs = edits[bc]
                want = dict(pairs).get(bd, default)
            else:
                try:
                    want = palette_set(rom, bc, bd)
                except KeyError:
                    want = None
            try:
                got = palette_set(built, bc, bd)
            except KeyError:
                got = None
            if got != want:
                raise ValueError(f'{bc:02X}/{bd:02X}: 만든 롬의 세트 {got} 가 입력 {want} 와 다름')
            checked += 1
    print(f'맵 {checked}개 세트 일치; 표 {cpu(palset_table(built))}, 쓰기 {len(writes)}개')
    return 0


def new_map(text):
    if not re.fullmatch(r'[0-9A-F]{2}/[0-9A-F]{2}', text):
        raise argparse.ArgumentTypeError('--new-map 은 대문자 16진 GG/MM 이어야 함')
    return tuple(int(v, 16) for v in text.split('/'))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('rom', type=Path)
    sub = parser.add_subparsers(dest='command', required=True)
    export = sub.add_parser('dump')
    export.add_argument('-o', '--out', type=Path, required=True)
    for name in ('patch', 'check'):
        p = sub.add_parser(name)
        p.add_argument('source', type=Path, nargs=None if name == 'patch' else '?')
        if name == 'patch':
            p.add_argument('-o', '--out', type=Path, required=True)
        p.add_argument('--table-at', help='표가 원래 자리를 넘을 때 찾기 루틴·표를 둘 자리(BB:AAAA)')
        p.add_argument('--new-map', action='append', default=[], type=new_map,
                       help='dq5newmap.py 로 함께 더하는 새 맵 GG/MM')
    args = parser.parse_args()
    try:
        rom = Rom(args.rom.read_bytes())
        if args.command == 'dump':
            result = dump(rom)
        else:
            doc = json.loads(args.source.read_text(encoding='utf-8')) if args.source else None
            if args.command == 'check':
                return check(rom, doc, args.table_at, args.new_map)
            result = patch(rom, doc, args.table_at, args.new_map)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(f'{args.command} → {args.out}')
        return 0
    except (ValueError, OSError, PatchError) as error:
        print(f'오류: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
