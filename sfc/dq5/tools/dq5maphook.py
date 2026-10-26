"""DQ5 맵별 루틴 표(15:F907)를 내보내고 고친다.

항목마다 맵 고르기(그룹·맵 또는 필드 세계), 플래그 조건, 맵을 푼 뒤 부를 루틴, 매 프레임 루틴을 JSON 으로 다룬다.
patch 는 항목 수를 그대로 두고 고치고, rewrite 는 표 전체를 다른 항목 수로 --at 자리에 다시 쓴다.
형식: sfc/dq5/docs/dq5-map-format.md 의 「맵별 루틴」, sfc/dq5/docs/dq5-build-format.md 의 `dq5maphook/1`.

  python sfc/dq5/tools/dq5maphook.py rom/dq5.sfc dump -o work/maphook/dump.json
  python sfc/dq5/tools/dq5maphook.py rom/dq5.sfc patch work/maphook/edit.json -o work/build/maphook.dq5patch.json
  python sfc/dq5/tools/dq5maphook.py rom/dq5.sfc rewrite work/maphook/table.json --at 15:FF80 -o work/build/maphook.dq5patch.json
  python sfc/dq5/tools/dq5maphook.py rom/dq5.sfc check [work/maphook/edit.json] [--at 15:FF80]
"""
import argparse
import json
import re
import sys
from pathlib import Path

from dq5map import Rom, lorom
from dq5mapwrite import all_maps

FORMAT = 'dq5maphook/1'
ENTRY = 10
NONE = 0x15F906
FIELD = 0xFE
FIELD_WORLDS = 3
GAP = 4
# 15:F7F4 는 15:F7D2 의 PHK/PLB 로 DB = 15 인 채 표를 `abs,X`(X 16비트)로 읽는다. 표 주소는 이 11개 명령의 피연산자에만 있고,
# 명령마다 항목 안 위치(+0~+9)를 더한 값이 들어 있다. 다른 곳(15:F887 의 15:FF5C 표 포함)은 이 표를 읽지 않는다.
OPERANDS = ((0x15F7F7, 0xBD, 0), (0x15F80A, 0xBD, 1), (0x15F85D, 0xDD, 1), (0x15F815, 0xBD, 2),
            (0x15F82B, 0x3D, 3), (0x15F865, 0xBD, 4), (0x15F86A, 0xBD, 5), (0x15F86F, 0xBD, 6),
            (0x15F880, 0xBD, 7), (0x15F87A, 0xBD, 8), (0x15F874, 0xBD, 9))
# 표를 다시 쓸 수 있는 자리. 원래 표(162개와 끝 FF)와 빈 자리 지도의 15:FF80~. 15:FF5C~FF62 는 15:F887 이 읽는 다른 표다.
SPANS = ((0x15F907, 0x15FF5C), (0x15FF80, 0x160000))


def require(ok, message):
    if not ok:
        raise ValueError(message)


def keys(value, allowed, name):
    require(isinstance(value, dict), f'{name}: 객체가 필요함')
    extra = value.keys() - set(allowed)
    require(not extra, f'{name}: 지원하지 않는 필드 {sorted(extra)}')


def hex_byte(value, name, low=0, high=0xFF):
    require(isinstance(value, str) and re.fullmatch(r'[0-9A-Fa-f]{2}', value) is not None, f'{name}: 16진 두 자리 문자열이어야 함')
    result = int(value, 16)
    require(low <= result <= high, f'{name}: {low:02X}~{high:02X} 여야 함')
    return result


def address(value, name):
    require(isinstance(value, str) and re.fullmatch(r'[0-9A-Fa-f]{2}:[0-9A-Fa-f]{4}', value) is not None,
            f'{name}: BB:AAAA 형태여야 함')
    bank, addr = (int(v, 16) for v in value.split(':'))
    return bank << 16 | addr


def text(addr):
    return f'{addr >> 16:02X}:{addr & 0xFFFF:04X}'


def read(rom, addr, size):
    off = lorom(addr)
    raw = bytes(rom.d[off:off + size])
    require(len(raw) == size, f'{text(addr)}: 롬 범위 밖')
    return raw


def table_base(rom):
    """로더 피연산자 11개가 가리키는 표 시작. 서로 맞지 않으면 로더가 바뀐 롬이라 거부한다."""
    bases = set()
    for at, opcode, offset in OPERANDS:
        raw = read(rom, at, 3)
        require(raw[0] == opcode, f'{text(at)}: 맵별 루틴 로더 명령이 원본과 다름')
        bases.add(0x150000 | (int.from_bytes(raw[1:], 'little') - offset))
    require(len(bases) == 1, '맵별 루틴 로더의 표 주소가 서로 맞지 않음')
    return bases.pop()


def span_of(base, size):
    for start, end in SPANS:
        if start <= base and base + size <= end:
            return start, end
    return None


def read_table(rom, base):
    span = span_of(base, 1)
    require(span is not None, f'{text(base)}: 표가 알려진 자리 밖에 있음')
    rows, addr = [], base
    while read(rom, addr, 1)[0] != 0xFF:
        require(addr + ENTRY + 1 <= span[1], f'{text(base)}: 표 끝 FF 가 자리 안에 없음')
        rows.append(read(rom, addr, ENTRY))
        addr += ENTRY
    return rows


def decode(raw):
    group, bd, flag, mask = raw[:4]
    row = {'group': f'{group:02X}', 'map': None if bd == 0xFF and group != FIELD else f'{bd:02X}', 'flag': None,
           'post_load': text(int.from_bytes(raw[4:7], 'little')), 'per_frame': text(int.from_bytes(raw[7:10], 'little'))}
    if flag != 0xFF:
        row['flag'] = {'index': f'{flag & 0x7F:02X}', 'mask': f'{mask:02X}', 'when': 'clear' if flag & 0x80 else 'set'}
    else:
        require(mask == 0, '조건 없는 항목의 마스크가 0 이 아님')
    return row


def routines(rows):
    post, frame = {NONE}, {NONE}
    for raw in rows:
        post.add(int.from_bytes(raw[4:7], 'little'))
        frame.add(int.from_bytes(raw[7:10], 'little'))
    return post, frame


class Context:
    def __init__(self, rom, allowed=None, raw_routines=False):
        self.base = table_base(rom)
        self.rows = read_table(rom, self.base)
        self.known = set(all_maps(rom))
        self.allowed = allowed or routines(self.rows)
        if allowed is None and self.base != SPANS[0][0]:
            # 표를 옮겨도 이 도구는 옛 자리를 지우지 않으므로, 남아 있으면 그 루틴도 받는다.
            try:
                post, frame = routines(read_table(rom, SPANS[0][0]))
                self.allowed = (self.allowed[0] | post, self.allowed[1] | frame)
            except ValueError:
                pass
        self.raw = raw_routines


def routine(value, allowed, raw, name):
    addr = address(value, name)
    if raw:
        bank, low = addr >> 16, addr & 0xFFFF
        # dq5build.parse_at 과 같은 범위. 뱅크 40~ 의 0000~7FFF 는 롬이 아니고 70~ 은 SRAM 이다.
        require(low >= 0x8000 and (bank & 0x7F) < 0x7E, f'{name}: 롬에 닿지 않는 주소 {value}')
    else:
        require(addr in allowed, f'{name}: 원래 표의 같은 칸에 없는 루틴 {value}(다른 주소는 --raw-routines)')
    return addr


def encode(row, ctx, name):
    require(set(row) >= {'group', 'map', 'flag', 'post_load', 'per_frame'}, f'{name}: 필드가 빠짐')
    group = hex_byte(row['group'], f'{name} group', 0, FIELD)
    if group == FIELD:
        bd = hex_byte(row['map'], f'{name} map', 0, FIELD_WORLDS - 1) if row['map'] is not None else None
        require(bd is not None, f'{name}: 필드 항목(FE)은 map 에 세계 번호가 필요함(15:F85D 는 FF 를 「모두」로 보지 않음)')
    elif row['map'] is None:
        require(any(g == group for g, _ in ctx.known), f'{name}: 맵 목록에 없는 그룹 {group:02X}')
        bd = 0xFF
    else:
        bd = hex_byte(row['map'], f'{name} map', 0, 0xFE)
        require((group, bd) in ctx.known, f'{name}: 맵 목록에 없는 맵 {group:02X}/{bd:02X}')
    flag = row['flag']
    if flag is None:
        flag_byte, mask = 0xFF, 0
    else:
        keys(flag, ('index', 'mask', 'when'), f'{name} flag')
        require(set(flag) == {'index', 'mask', 'when'}, f'{name} flag: index·mask·when 이 모두 필요함')
        index = hex_byte(flag['index'], f'{name} flag index', 0, 0x7F)
        mask = hex_byte(flag['mask'], f'{name} flag mask', 1, 0xFF)
        require(flag['when'] in ('set', 'clear'), f'{name} flag when: set 또는 clear')
        flag_byte = index | (0x80 if flag['when'] == 'clear' else 0)
        require(flag_byte != 0xFF, f'{name} flag: 7F 의 clear 는 「조건 없음」(FF)과 같은 바이트라 쓸 수 없음')
    post = routine(row['post_load'], ctx.allowed[0], ctx.raw, f'{name} post_load')
    frame = routine(row['per_frame'], ctx.allowed[1], ctx.raw, f'{name} per_frame')
    return bytes([group, bd, flag_byte, mask]) + post.to_bytes(3, 'little') + frame.to_bytes(3, 'little')


def covers(a, b):
    """항목 a 가 조건 없이 b 의 맵을 모두 먼저 잡으면 b 는 불리지 않는다(15:F7F4 는 처음 맞는 항목만 씀)."""
    return a[2] == 0xFF and a[0] == b[0] and (a[1] == b[1] or a[0] != FIELD and a[1] == 0xFF)


def shadowed(rows):
    return [j for j, b in enumerate(rows) if any(covers(a, b) for a in rows[:j])]


def dump(rom):
    ctx = Context(rom)
    return {'format': FORMAT, 'table': text(ctx.base),
            'entries': [{'index': i, **decode(raw)} for i, raw in enumerate(ctx.rows)]}


def runs(rom, wanted, note):
    """wanted {주소: 바이트} 가운데 롬과 다른 것을 쓰기로 묶는다. 사이가 GAP 바이트 이하이고 그 사이도 wanted 안이면
    (같은 값이라도) 한 쓰기로 잇는다. wanted 밖의 바이트는 다른 도구 몫일 수 있어 덮지 않는다."""
    changed = sorted(a for a, v in wanted.items() if read(rom, a, 1)[0] != v)
    writes, i = [], 0
    while i < len(changed):
        j = i
        while (j + 1 < len(changed) and changed[j + 1] - changed[j] <= GAP + 1 and changed[j + 1] >> 16 == changed[i] >> 16
               and all(a in wanted for a in range(changed[j], changed[j + 1]))):
            j += 1
        start, size = changed[i], changed[j] - changed[i] + 1
        writes.append({'at': text(start), 'hex': bytes(wanted[start + k] for k in range(size)).hex(' '),
                       'orig': read(rom, start, size).hex(' '), 'note': note})
        i = j + 1
    return writes


def result(writes):
    return {'format': 'dq5patch/1', 'name': 'maphook', 'writes': writes}


def warn(rows, known=()):
    for j in sorted(set(shadowed(rows)) - set(known)):
        print(f'경고: 항목 {j} 는 앞의 조건 없는 항목이 먼저 잡아 불리지 않음', file=sys.stderr)


def patch(rom, doc, allowed=None, raw_routines=False, quiet=False):
    keys(doc, ('format', 'table', 'entries'), '문서')
    require(doc.get('format') == FORMAT and isinstance(doc.get('entries'), list), 'format/entries 가 잘못됨')
    ctx = Context(rom, allowed, raw_routines)
    if 'table' in doc:
        require(address(doc['table'], 'table') == ctx.base, f'table 이 롬의 표 자리 {text(ctx.base)} 와 다름')
    rows, seen = list(ctx.rows), set()
    for row in doc['entries']:
        keys(row, ('index', 'group', 'map', 'flag', 'post_load', 'per_frame'), '항목')
        index = row.get('index')
        require(type(index) is int and 0 <= index < len(rows), f'index: 0~{len(rows) - 1} 정수여야 함')
        require(index not in seen, f'항목 {index} 를 두 번 지정함')
        seen.add(index)
        rows[index] = encode(decode(ctx.rows[index]) | {k: v for k, v in row.items() if k != 'index'}, ctx, f'항목 {index}')
    if not quiet:
        warn(rows, shadowed(ctx.rows))
    wanted = {ctx.base + i * ENTRY + k: v for i, raw in enumerate(rows) for k, v in enumerate(raw)}
    return result(runs(rom, wanted, '맵별 루틴 항목'))


def rewrite(rom, doc, at=None, allowed=None, raw_routines=False, quiet=False):
    keys(doc, ('format', 'table', 'entries'), '문서')
    require(doc.get('format') == FORMAT and isinstance(doc.get('entries'), list), 'format/entries 가 잘못됨')
    ctx = Context(rom, allowed, raw_routines)
    base = ctx.base if at is None else at
    if 'table' in doc:
        require(address(doc['table'], 'table') == base, f'table 이 쓸 자리 {text(base)} 와 다름(자리는 --at 으로 정함)')
    rows = []
    for i, row in enumerate(doc['entries']):
        keys(row, ('index', 'group', 'map', 'flag', 'post_load', 'per_frame'), '항목')
        index = row.get('index', i)
        require(type(index) is int and index == i, f'항목 {i}: rewrite 의 index 는 순서와 같아야 함')
        rows.append(encode(row, ctx, f'항목 {i}'))
    require(rows, '항목이 하나도 없음')
    size = len(rows) * ENTRY + 1
    require(base >> 16 == 0x15, '표는 뱅크 15 에 있어야 함(15:F7D2 PHK/PLB 로 DB = 15)')
    require(span_of(base, size) is not None,
            f'{text(base)}+{size}: 표를 둘 수 있는 자리 밖(' + ', '.join(f'{text(s)}~{text(e - 1)}' for s, e in SPANS) + ')')
    if not quiet:
        old = {ctx.rows[j] for j in shadowed(ctx.rows)}
        warn(rows, [j for j in shadowed(rows) if rows[j] in old])
    wanted = {base + i * ENTRY + k: v for i, raw in enumerate(rows) for k, v in enumerate(raw)}
    wanted[base + len(rows) * ENTRY] = 0xFF
    current = range(ctx.base, ctx.base + len(ctx.rows) * ENTRY + 1)
    for a in wanted:
        require(SPANS[0][0] <= a < SPANS[0][1] or a in current or read(rom, a, 1)[0] == 0,
                f'{text(a)}: 표 자리 밖의 0 이 아닌 바이트를 덮음(이미 다른 쓰기가 있는 롬)')
    writes = runs(rom, wanted, '맵별 루틴 표')
    operands = {}
    for at_, _, offset in OPERANDS:
        operands.update({at_ + 1 + k: v for k, v in enumerate(((base & 0xFFFF) + offset).to_bytes(2, 'little'))})
    return result(writes + runs(rom, operands, '맵별 루틴 로더의 표 주소'))


def check(rom, doc=None, at=None, raw_routines=False):
    from dq5build import build, parse_at
    original = dump(rom)
    source = original if doc is None else doc
    allowed = routines(Context(rom).rows)
    make = (lambda r, d, q=True: rewrite(r, d, at, allowed, raw_routines, q)) if at is not None else (
        lambda r, d, q=True: patch(r, d, allowed, raw_routines, q))
    writes = make(rom, source, False)['writes']
    require(doc is not None or not writes, '원본 왕복 쓰기가 0개가 아님')
    rebuilt, _ = build(rom.d, [('maphook', 0, [
        (parse_at(w['at'])[0], bytes.fromhex(w['hex']), bytes.fromhex(w['orig']), w['note']) for w in writes])], 0)
    after = Rom(rebuilt)
    require(not make(after, source)['writes'], '빌더 적용 후 같은 입력을 다시 패치하면 쓰기가 남음')
    again = dump(after)
    require(not patch(after, again, allowed, True, True)['writes'], '빌드한 롬을 다시 읽고 인코딩한 결과가 다름')
    if at is not None:
        require(again['table'] == text(at), '빌드한 롬의 로더가 새 자리를 가리키지 않음')
        require(len(again['entries']) == len(source['entries']), '빌드한 롬의 항목 수가 입력과 다름')
    print(f'항목 {len(again["entries"])}개(표 {again["table"]}), 쓰기 {len(writes)}개 검사 통과')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('rom', type=Path)
    sub = parser.add_subparsers(dest='command', required=True)
    export = sub.add_parser('dump')
    export.add_argument('-o', '--out', type=Path)
    for name in ('patch', 'rewrite', 'check'):
        p = sub.add_parser(name)
        p.add_argument('source', type=Path, nargs='?' if name == 'check' else None)
        if name != 'check':
            p.add_argument('-o', '--out', type=Path)
        p.add_argument('--at', help='rewrite·check: 표를 둘 자리 BB:AAAA. 빼면 rewrite 는 지금 자리')
        p.add_argument('--raw-routines', action='store_true', help='원래 표에 없는 루틴 주소도 받음')
    args = parser.parse_args()
    try:
        rom = Rom(args.rom.read_bytes())
        doc = json.loads(args.source.read_text(encoding='utf-8')) if getattr(args, 'source', None) else None
        at = address(args.at, '--at') if getattr(args, 'at', None) else None
        require(args.command != 'patch' or at is None, 'patch 는 --at 을 받지 않음(표 자리를 옮기려면 rewrite)')
        if args.command == 'check':
            check(rom, doc, at, args.raw_routines)
            return 0
        if args.command == 'dump':
            out = dump(rom)
        elif args.command == 'patch':
            out = patch(rom, doc, raw_routines=args.raw_routines)
        else:
            out = rewrite(rom, doc, at, raw_routines=args.raw_routines)
        body = json.dumps(out, ensure_ascii=False, indent=2) + '\n'
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(body, encoding='utf-8')
        else:
            print(body, end='')
        return 0
    except (ValueError, OSError) as error:
        print(f'오류: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
