"""DQ5 그룹마다 걸음마다 부르는 루틴 표(00:C689) 쓰기·늘리기. 형식은 sfc/dq5/docs/dq5-build-format.md 「걸음 루틴 표」.

표는 [$BC][루틴 16비트]… [FF] 이다. 00:C652 가 $BE bit7(실내)일 때 처음부터 $BC 를 찾아 루틴 주소를 $1AAD 에 두고,
없거나 필드면 기본 00:C687(CLC / RTS)을 둔다. 00:C357 이 `JMP ($1AAD)` 로 부르므로 표의 루틴 주소는 뱅크 00 이다.
원본은 15그룹(46바이트)이고 표 바로 뒤가 코드라 제자리로는 늘리지 못한다. 그보다 많으면 --table-at 자리에
[찾기 루틴][표] 를 두고 00:C652 를 JML 로 바꾼다. 루틴은 원래와 같은 차례로 표를 긴 주소로 읽고 $1AAD 를 긴 주소로 쓴 뒤
RTL 한다(원래 루틴도 RTL 로 끝남). 색인 X 가 8비트라 끝 FF 를 X ≤ 255 에서 읽어야 하므로
표는 85그룹까지다(85그룹이면 끝 FF 가 X = 255).
루틴을 뱅크 00 밖(BB:AAAA, BB ≠ 00)에 적으면 찾기를 옮겨 비는 00:C656~C686 에 받침 `JSL 루틴 / RTS`(5바이트)를 두고
표에는 받침 주소를 적는다. 받침은 9개까지라 뱅크 00 밖 루틴도 9개까지이고, --table-at 이 있어야 한다.
루틴 몸통은 이 도구가 쓰지 않는다. 몸통은 RTL 로 끝나고 돌려줄 값은 원래 루틴처럼 캐리다.

  python sfc/dq5/tools/dq5stepwrite.py rom/dq5.sfc dump -o work/step.json
  python sfc/dq5/tools/dq5stepwrite.py rom/dq5.sfc patch work/step.json -o work/step.dq5patch.json \\
      [--table-at BB:AAAA] [--new-map GG/MM …]
  python sfc/dq5/tools/dq5stepwrite.py rom/dq5.sfc check [work/step.json --table-at … --new-map …]

입력: {"format": "dq5step/1", "groups": [{"group": "36", "routine": "00:C385"}]}
적은 그룹은 그 루틴으로 바꾸고, 적지 않은 그룹은 원래 항목을 둔다. 루틴을 기본 00:C687 로 적으면 항목을 뺀다.
새 그룹은 표 끝에 붙인다. 그룹은 롬에 있거나 --new-map 으로 알린 것만 받는다.
"""
import argparse
import json
import re
import sys
from pathlib import Path

from dq5build import PatchError, build
from dq5map import Rom, lorom
from dq5palsetwrite import known_maps, lorom_cpu, new_map

FORMAT = 'dq5step/1'
LOOKUP = 0x00C652
# 00:C652~C662: PHP / PHB / PHK / PLB / SEP #$30 / LDA $BE / BPL … / LDX #$00 / LDA $C689,X
LOOKUP_ORIG = bytes.fromhex('08 8b 4b ab e2 30 a5 be 10 1e a2 00 bd 89 c6')
LOOKUP_END = 0x00C687
TABLE = 0x00C689
DEFAULT = 0x00C687
ORIGINAL_SIZE = 46
MAX_GROUPS = 85
ROUTINE_SLOT = 0x1AAD
# 찾기를 옮기면 00:C656~C686 은 아무 데서도 오지 않는다(정적 검색·실내 맵 훑기, 형식 문서 「걸음 루틴 표」)
TRAMPOLINES = 0x00C656
TRAMPOLINE_SIZE = 5
MAX_FAR = (LOOKUP_END - TRAMPOLINES) // TRAMPOLINE_SIZE


def cpu(addr):
    return f'{addr >> 16:02X}:{addr & 0xFFFF:04X}'


def parse_table(rom, at):
    """[(BC, 루틴 24비트)]. 끝 FF 까지."""
    rows, a = [], at
    while True:
        if a - at > MAX_GROUPS * 3 or lorom(a) >= len(rom.d):
            raise ValueError(f'{cpu(at)}: 걸음 루틴 표의 끝 FF 가 없음')
        bc = rom.u8(a)
        if bc & 0x80:
            return rows
        rows.append((bc, rom.u16(a + 1)))
        a += 3


def assemble(at):
    """at 에 두는 찾기 루틴(뒤에 표가 붙음). 원래 00:C652~C686 과 같은 갈래를 긴 주소로 한다."""
    slot = ROUTINE_SLOT.to_bytes(3, 'little')
    head = bytes.fromhex('08 e2 30 a5 be 10 23 a2 00')   # PHP / SEP #$30 / LDA $BE / BPL 기본 / LDX #$00
    size = len(head) + 4 + 2 + 2 + 2 + 3 + 2 + 4 + 4 + 4 + 4 + 2 + 2 + 4 + 2 + 4 + 2
    table = at + size
    body = bytearray(head)
    body += b'\xbf' + table.to_bytes(3, 'little')           # 찾기: LDA 표,X
    body += b'\x30\x1b'                                     # BMI 기본
    body += b'\xc5\xbc'                                     # CMP $BC
    body += b'\xf0\x05'                                     # BEQ 찾음
    body += b'\xe8\xe8\xe8'                                 # INX ×3
    body += b'\x80\xf1'                                     # BRA 찾기
    body += b'\xbf' + (table + 1).to_bytes(3, 'little')     # 찾음: LDA 표+1,X
    body += b'\x8f' + slot                                  # STA $001AAD
    body += b'\xbf' + (table + 2).to_bytes(3, 'little')
    body += b'\x8f' + (ROUTINE_SLOT + 1).to_bytes(3, 'little')
    body += b'\x28\x6b'                                     # PLP / RTL
    body += b'\xa9' + bytes([DEFAULT & 0xFF]) + b'\x8f' + slot             # 기본: LDA #$87 / STA $001AAD
    body += b'\xa9' + bytes([DEFAULT >> 8 & 0xFF]) + b'\x8f' + (ROUTINE_SLOT + 1).to_bytes(3, 'little')
    body += b'\x28\x6b'
    assert len(body) == size
    return bytes(body)


def trampoline(target):
    return b'\x22' + target.to_bytes(3, 'little') + b'\x60'           # JSL 루틴 / RTS


def far_target(rom, routine):
    """표의 16비트 루틴이 옮긴 찾기 롬의 받침이면 받침이 부르는 24비트 주소, 아니면 00:루틴."""
    if rom.u8(LOOKUP) == 0x5C and TRAMPOLINES <= routine < LOOKUP_END \
            and (routine - TRAMPOLINES) % TRAMPOLINE_SIZE == 0 \
            and rom.u8(routine) == 0x22 and rom.u8(routine + 4) == 0x60:
        return rom.u24(routine + 1)
    return routine


def step_table(rom):
    """롬이 읽는 표 자리. 00:C652 가 JML 이면 옮긴 루틴의 첫 LDA 피연산자."""
    if rom.u8(LOOKUP) == 0x5C:
        stub = rom.u24(LOOKUP + 1)
        if rom.d[lorom(stub):lorom(stub) + 9] != assemble(stub)[:9] or rom.u8(stub + 9) != 0xBF:
            raise ValueError(f'{cpu(LOOKUP)}: JML {cpu(stub)} 이 이 도구의 찾기 루틴이 아님')
        return rom.u24(stub + 10)
    if rom.d[lorom(LOOKUP):lorom(LOOKUP) + len(LOOKUP_ORIG)] != LOOKUP_ORIG:
        raise ValueError(f'{cpu(LOOKUP)}: 원래 걸음 루틴 찾기 명령이 아님')
    return TABLE


def routine_value(value, name):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9A-F]{2}:[0-9A-F]{4}', value):
        raise ValueError(f'{name}: 대문자 16진 BB:AAAA 문자열이어야 함')
    bank, addr = int(value[:2], 16), int(value[3:], 16)
    if addr < 0x8000 or bank > 0x7D:
        raise ValueError(f'{name}: 뱅크 00~7D, AAAA 8000~FFFF 여야 함')
    if bank == 0 and LOOKUP <= addr < LOOKUP_END:
        raise ValueError(f'{name}: {value} 은 찾기 루틴 자리(00:C652~C686)')
    return bank << 16 | addr


def group_rows(doc, groups):
    if not isinstance(doc, dict) or set(doc) - {'format', 'groups'} or doc.get('format') != FORMAT:
        raise ValueError(f'문서는 format={FORMAT}, groups 만 담아야 함')
    rows = doc.get('groups', [])
    if not isinstance(rows, list):
        raise ValueError('groups 는 배열이어야 함')
    out = {}
    for i, row in enumerate(rows):
        name = f'groups[{i}]'
        if not isinstance(row, dict) or set(row) != {'group', 'routine'}:
            raise ValueError(f'{name}: group·routine 만 받음')
        if not isinstance(row['group'], str) or not re.fullmatch(r'[0-9A-F]{2}', row['group']):
            raise ValueError(f'{name}.group: 대문자 16진 2자리 문자열이어야 함')
        bc = int(row['group'], 16)
        if bc not in groups:
            raise ValueError(f'{name}: 그룹 {bc:02X} 이 롬에 없음(새 그룹은 --new-map 으로 알림)')
        if bc in out:
            raise ValueError(f'{name}: 그룹 {bc:02X} 을 두 번 적음')
        out[bc] = routine_value(row['routine'], f'{name}.routine')
    return out


def merged(rom, doc, new_maps=()):
    edits = group_rows(doc, known_maps(rom, new_maps))
    rows = [(bc, edits.pop(bc) if bc in edits else r) for bc, r in parse_table(rom, TABLE)]
    rows += sorted(edits.items())
    return [(bc, r) for bc, r in rows if r != DEFAULT]


def encode(rows):
    return b''.join(bytes([bc]) + r.to_bytes(2, 'little') for bc, r in rows) + b'\xff'


def far_layout(rows):
    """뱅크 00 밖 루틴을 받침으로 바꾼 (표 줄, 받침 바이트). 같은 루틴은 받침 하나를 같이 쓴다."""
    slots = {}
    for _, r in rows:
        if r >> 16 and r not in slots:
            slots[r] = TRAMPOLINES + len(slots) * TRAMPOLINE_SIZE
    if len(slots) > MAX_FAR:
        raise ValueError(f'뱅크 00 밖 루틴 {len(slots)}개가 받침 자리 00:C656~C686 의 {MAX_FAR}개를 넘음')
    return [(bc, slots.get(r, r)) for bc, r in rows], b''.join(trampoline(r) for r in slots)


def writes_for(rom, doc, table_at=None, new_maps=()):
    """(주소, 새 값, 원본|None, 설명)."""
    if step_table(rom) != TABLE:
        raise ValueError(f'걸음 루틴 표가 이미 {cpu(step_table(rom))} 로 옮겨진 롬: 원본 롬에서 다시 만듦')
    size = len(encode(parse_table(rom, TABLE)))
    if size != ORIGINAL_SIZE:
        raise ValueError(f'원래 걸음 루틴 표 크기가 {ORIGINAL_SIZE}바이트가 아님({size}). 원본 롬에서 다시 만듦')
    rows = merged(rom, doc, new_maps)
    if len(rows) > MAX_GROUPS:
        raise ValueError(f'걸음 루틴 표 {len(rows)}그룹이 8비트 색인 한도 {MAX_GROUPS}그룹을 넘음')
    far = [r for _, r in rows if r >> 16]
    rows, stubs = far_layout(rows)
    blob = encode(rows)
    if stubs and table_at is None:
        raise ValueError('뱅크 00 밖 루틴은 찾기를 옮긴 자리에 받침을 두므로 --table-at 이 필요함')
    if table_at is None:
        if len(blob) > ORIGINAL_SIZE:
            raise ValueError(f'걸음 루틴 표 {len(blob)}바이트가 원래 자리 {ORIGINAL_SIZE}바이트를 넘음(--table-at 이 필요함)')
        old = rom.d[lorom(TABLE):lorom(TABLE) + len(blob)]
        return [(TABLE, blob, bytes(old), '걸음 루틴 표')]
    at = lorom_cpu(table_at)
    # 몸통은 다른 패치가 쓰므로, 이 패치를 넣은 롬(원래 크기와 찾기 루틴 자리로 늘린 크기 가운데 큰 쪽) 안이어야 한다
    limit = max(len(rom.d), rom_size(at >> 16) << 20)
    for r in far:
        if lorom(r) >= limit:
            raise ValueError(f'루틴 {cpu(r)} 이 이 패치를 넣은 롬({limit / (1 << 20):g}MB) 밖. 몸통 뱅크까지 늘리는 '
                             f'--table-at 이나 롬 안 자리를 적음')
    code = assemble(at)
    if (at & 0xFFFF) + len(code) + len(blob) > 0x10000:
        raise ValueError(f'찾기 루틴·표 {len(code) + len(blob)}바이트가 {table_at} 의 뱅크 끝을 넘음')
    hook = bytes([0x5C, *at.to_bytes(3, 'little')])
    # 새 자리는 orig 를 붙이지 않는다. 빌더가 빈 자리 지도 밖이면 거부하게 하기 위해서다.
    writes = [(at, code + blob, None, f'걸음 루틴 찾기 루틴·표({len(rows)}그룹)'),
              (LOOKUP, hook, LOOKUP_ORIG[:4], '걸음 루틴 찾기를 옮긴 루틴으로(JML)')]
    if stubs:
        old = rom.d[lorom(TRAMPOLINES):lorom(TRAMPOLINES) + len(stubs)]
        writes.append((TRAMPOLINES, stubs, bytes(old), f'뱅크 00 밖 걸음 루틴 받침 {len(stubs) // TRAMPOLINE_SIZE}개'))
    return writes


def rom_size(bank):
    """그 뱅크까지 쓰는 패치 목록의 rom_size(MB). 원래 크기(뱅크 2F 까지) 안이면 0."""
    return 0 if bank < 0x30 else 2 if bank < 0x40 else 3 if bank < 0x60 else 4


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
    result = {'format': 'dq5patch/1', 'name': 'step-routines', 'writes': writes}
    size = rom_size(top)
    if size:
        result['rom_size'] = size
    return result


def dump(rom):
    return {'format': FORMAT, 'groups': [{'group': f'{bc:02X}', 'routine': cpu(far_target(rom, r))}
                                         for bc, r in parse_table(rom, step_table(rom))]}


def check(rom, doc=None, table_at=None, new_maps=()):
    """만든 롬의 표를 다시 읽어 그룹마다 루틴이 입력대로인지 본다."""
    doc = doc or dump(rom)
    manifest = patch(rom, doc, table_at, new_maps)
    mb = manifest.get('rom_size', 0)
    writes = [(lorom(int(w['at'][:2], 16) << 16 | int(w['at'][3:], 16)), bytes.fromhex(w['hex']),
               bytes.fromhex(w['orig']) if 'orig' in w else None, w['note']) for w in manifest['writes']]
    built = Rom(build(rom.d, [('step-routines', mb, writes)], mb)[0])
    want = dict(merged(rom, doc, new_maps))
    got = {bc: far_target(built, r) for bc, r in parse_table(built, step_table(built))}
    for bc in sorted(known_maps(rom, new_maps)):
        if got.get(bc, DEFAULT) != want.get(bc, DEFAULT):
            raise ValueError(f'그룹 {bc:02X}: 만든 롬의 루틴 {cpu(got.get(bc, DEFAULT))} 가 입력 '
                             f'{cpu(want.get(bc, DEFAULT))} 와 다름')
    print(f'그룹 {len(known_maps(rom, new_maps))}개 루틴 일치(항목 {len(got)}개); 표 {cpu(step_table(built))}, '
          f'쓰기 {len(writes)}개')
    return 0


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
