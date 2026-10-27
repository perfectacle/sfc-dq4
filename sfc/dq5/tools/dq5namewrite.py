"""DQ5 이름 문자열 표(인물·호칭·주문·몬스터·물건·작전·동료·마을)를 1바이트 부호 목록으로 내보내고 다시 넣는다.

형식은 sfc/dq5/docs/dq5-build-format.md 의 「이름 문자열 표 쓰기」. 21:955D 는 21:959B + 표 * 3 의 24비트 주소에서
[길이][바이트…] 를 n 번 건너뛰어 n 번째 이름을 찾는다. 항목 수는 그대로 두고 길이만 바꿀 수 있다.

  python sfc/dq5/tools/dq5namewrite.py rom/dq5.sfc export -o work/names.json
  python sfc/dq5/tools/dq5namewrite.py rom/dq5.sfc patch work/names.json -o work/names.dq5patch.json
  python sfc/dq5/tools/dq5namewrite.py rom/dq5.sfc patch work/names.json --at 3C:8000 -o work/names.dq5patch.json
  python sfc/dq5/tools/dq5namewrite.py rom/dq5.sfc check work/names.json [--at 3C:8000]

JSON: {"format":"dq5names/1", "tables":[{"table":4,"names":[{"id":0,"bytes":[33,58,4,64]}]}]}.
tables·names 에는 바꿀 항목만 넣을 수 있고, 빈 목록은 원본 전체를 다시 쓴다(바뀐 바이트가 없어 쓰기 0개).
bytes 는 0~255 정수 배열(24:A7B6 이 읽는 1바이트 부호, 84·83 은 탁점·반탁점 접두). 길이는 0~24.
--at 을 빼면 표를 원래 자리(23:C242~D6A0 의 여덟 표, 22:8000~841E 의 표 3)에 다시 채운다. 모자라면 거부한다.
--at 을 주면 표 아홉 개를 모두 그 자리부터 차례로 옮기고 포인터를 고친다. 한 표는 한 뱅크 안에 있어야 하므로
뱅크 끝에 들어가지 않는 표는 다음 뱅크 8000 에서 시작한다. 30~7D 뱅크만 받는다.
표 7(30:8000)·8·9(23:D6A1, 표가 아니라 21:A1D7 이 JSL 하는 코드)는 다루지 않는다.
--append 를 주면 원래 항목 수 다음 id 부터 빈틈 없이 이름을 덧붙인다(늘어난 표는 --at 으로 옮겨야 들어간다).
21:955D 는 항목 수를 보지 않고 n 번 건너뛰므로, 늘린 번호(예: dq5spellgrow.py 의 새 주문 C6~, 그 앞 AB~C5 는 빈 이름으로 채움)의 이름이 된다.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5map import Rom, lorom  # noqa: E402
from dq5text import STRING_TABLES  # noqa: E402

FORMAT = 'dq5names/1'
# 원래 자리. 23:C242~D6A0 은 표 0A·0·1·2·4·5·6·0B 가 빈틈 없이 이어진 곳, 22:8000~ 는 표 3 하나.
REGIONS = ((0x23C242, 0x23D6A1, (0x0A, 0, 1, 2, 4, 5, 6, 0x0B)), (0x228000, 0x22841F, (3,)))
COUNTS = {0: 8, 1: 17, 2: 3, 3: 171, 4: 236, 5: 222, 6: 6, 0x0A: 168, 0x0B: 23}
TABLES = tuple(t for _, _, ts in REGIONS for t in ts)
# 21:9589 는 [길이][바이트…] 를 직접 페이지 $00 부터 복사한다. 이름을 읽은 뒤 처음 접근이 읽기인 직접 페이지는
# $19·$1A(04:9D43·00:96AD)가 가장 낮았으므로(전투·물건·주문·상점·전투 주문 창 실측) $00~$18 만 덮는 24바이트까지.
MAX_NAME = 24
# 21:955D 는 이름 번호 $42 를 8비트 X 로 세므로 한 표는 256개까지.
MAX_ENTRIES = 256
BANK = 0x8000
LAST_BANK = 0x7D


def keys(value, allowed, name):
    if not isinstance(value, dict) or value.keys() - allowed:
        raise ValueError(f'{name}: 허용한 필드 {sorted(allowed)}만 있는 JSON 객체여야 함')


def valid_name(raw):
    if not isinstance(raw, list) or len(raw) > MAX_NAME:
        raise ValueError(f'bytes 는 길이 0~{MAX_NAME} 정수 배열이어야 함')
    for b in raw:
        if type(b) is not int or not 0 <= b <= 0xFF:
            raise ValueError(f'1바이트 부호가 아님: {b!r}')
    return raw


def table_at(data, table):
    return Rom(data).u24(STRING_TABLES + table * 3)


def read_tables(data):
    """{표: [이름 바이트 목록…]}. 원래 자리·항목 수가 맞는 원본 롬이어야 한다."""
    rom = Rom(data)
    out = {}
    for start, end, tables in REGIONS:
        a = start
        for t in tables:
            if table_at(data, t) != a:
                raise ValueError(f'표 {t:X} 포인터가 원래 자리가 아님; 원본 롬으로 패치 목록을 만들어야 함')
            names = []
            for _ in range(COUNTS[t]):
                n = rom.u8(a)
                names.append(valid_name([rom.u8(a + 1 + i) for i in range(n)]))
                a += n + 1
            out[t] = names
        if a != end:
            raise ValueError('이름 표 끝이 원래 자리와 다름; 원본 롬이어야 함')
    return out


def overrides(original, doc, append=False):
    keys(doc, {'format', 'tables'}, '문서')
    if doc.get('format') != FORMAT or not isinstance(doc.get('tables'), list):
        raise ValueError(f'format={FORMAT}과 tables 배열이 필요함')
    tables = {t: list(names) for t, names in original.items()}
    seen = set()
    for row in doc['tables']:
        keys(row, {'table', 'names'}, '표')
        t = row.get('table')
        if type(t) is not int or t not in TABLES or t in seen:
            raise ValueError(f'table 은 중복 없는 {", ".join(f"{x:X}" for x in TABLES)}(16진) 가운데 하나여야 함')
        seen.add(t)
        if not isinstance(row.get('names'), list):
            raise ValueError('names 배열이 필요함')
        ids = set()
        for name in row['names']:
            keys(name, {'id', 'bytes'}, '이름')
            i = name.get('id')
            if append and type(i) is int and i == len(tables[t]) < MAX_ENTRIES and i not in ids:
                ids.add(i)
                tables[t].append(valid_name(name.get('bytes')))
                continue
            if type(i) is not int or not 0 <= i < COUNTS[t] or i in ids:
                raise ValueError(f'표 {t:X} 의 id 는 중복 없는 0~{COUNTS[t] - 1} 정수여야 함'
                                 + ('(--append 면 그 뒤로 빈틈 없이)' if append else ''))
            ids.add(i)
            tables[t][i] = valid_name(name.get('bytes'))
    return tables


def blob(names):
    return b''.join(bytes([len(n), *n]) for n in names)


def parse_at(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-fA-F]{2}:[0-9a-fA-F]{4}', value):
        raise ValueError('--at 은 BB:AAAA 형식이어야 함')
    bank, low = (int(v, 16) for v in value.split(':'))
    if not 0x30 <= bank <= LAST_BANK or not 0x8000 <= low <= 0xFFFF:
        raise ValueError('--at 은 30~7D 뱅크의 8000~FFFF 만 받음')
    return bank << 16 | low


def place(data, tables, at):
    """(표 → 새 CPU 주소, [(CPU 주소, 바이트, 원래 롬이면 원래 바이트)])."""
    pointers, chunks = {}, []
    if at is None:
        for start, end, ts in REGIONS:
            raw = b''.join(blob(tables[t]) for t in ts)
            if len(raw) > end - start:
                raise ValueError(f'{start >> 16:02X}:{start & 0xFFFF:04X} 자리에 {len(raw) - (end - start)}바이트가 넘침; '
                                 '--at 으로 옮겨야 함')
            off = lorom(start)
            old = data[off:off + len(raw)]
            diff = [i for i in range(len(raw)) if raw[i] != old[i]]
            if diff:
                a, b = diff[0], diff[-1] + 1
                chunks.append((start + a, raw[a:b], old[a:b]))
            a = start
            for t in ts:
                pointers[t] = a
                a += len(blob(tables[t]))
        return pointers, chunks
    base = parse_at(at)
    if lorom(base) < len(data):
        raise ValueError('이름 표 배치가 입력 롬과 겹침; 원본 롬과 확장 뱅크를 사용해야 함')
    a = base
    for t in TABLES:
        raw = blob(tables[t])
        if (a & 0xFFFF) + len(raw) > 0x10000:
            a = ((a >> 16) + 1) << 16 | 0x8000
        if a >> 16 > LAST_BANK:
            raise ValueError('이름 표가 7D 뱅크 끝을 넘음')
        pointers[t] = a
        chunks.append((a, raw, None))
        a += len(raw)
        if a & 0xFFFF == 0:
            a = ((a >> 16) + 1) << 16 | 0x8000
    return pointers, chunks


def compile_tables(data, tables, at=None, name='names'):
    pointers, chunks = place(data, tables, at)
    writes = []
    end = 0
    for addr, raw, orig in chunks:
        if not raw:
            continue
        w = {'at': f'{addr >> 16:02X}:{addr & 0xFFFF:04X}', 'hex': raw.hex(' '), 'note': '이름 문자열 표'}
        if orig is not None:
            w['orig'] = orig.hex(' ')
        writes.append(w)
        end = max(end, lorom(addr) + len(raw))
    for t in TABLES:
        at_ptr = STRING_TABLES + t * 3
        off = lorom(at_ptr)
        old = data[off:off + 3]
        new = bytes((pointers[t] & 0xFF, pointers[t] >> 8 & 0xFF, pointers[t] >> 16))
        if new != old:
            writes.append({'at': f'{at_ptr >> 16:02X}:{at_ptr & 0xFFFF:04X}', 'hex': new.hex(' '), 'orig': old.hex(' '),
                           'note': f'이름 표 {t:X} 포인터'})
    manifest = {'format': 'dq5patch/1', 'name': name, 'writes': writes}
    if end > len(data):
        manifest['rom_size'] = max(2, -(-end // 0x100000))
    return manifest


def patch(data, doc, at=None, name='names', append=False):
    return compile_tables(data, overrides(read_tables(data), doc, append), at, name)


def decoded_tables(data, counts=None):
    """21:955D 와 같이 포인터를 따라 표마다 원래 항목 수만큼 읽는다."""
    rom = Rom(data)
    out = {}
    for t in TABLES:
        a = table_at(data, t)
        names = []
        try:
            for _ in range((counts or COUNTS)[t]):
                n = rom.u8(a)
                if (a & 0xFFFF) + n >= 0x10000:
                    raise ValueError(f'표 {t:X} 가 뱅크 끝을 넘음')
                names.append([rom.u8(a + 1 + i) for i in range(n)])
                a += n + 1
        except IndexError:
            raise ValueError(f'표 {t:X} 주소가 롬 범위를 벗어남') from None
        out[t] = names
    return out


def check(data, doc, at=None, append=False):
    from dq5build import PatchError, build, parse_at as patch_at
    tables = overrides(read_tables(data), doc, append)
    manifest = compile_tables(data, tables, at)
    writes = [(patch_at(w['at'])[0], bytes.fromhex(w['hex']), bytes.fromhex(w['orig']) if 'orig' in w else None,
               w['note']) for w in manifest['writes']]
    size = manifest.get('rom_size')
    try:
        rebuilt, _ = build(data, [(manifest['name'], size, writes)], size)
    except PatchError as error:
        raise ValueError(str(error)) from None
    decoded = decoded_tables(rebuilt, {t: len(names) for t, names in tables.items()})
    different = sum(a != b for t in TABLES for a, b in zip(tables[t], decoded[t]))
    print(f'이름 표 {len(TABLES)}개, 이름 {sum(map(len, decoded.values()))}개, 쓰기 {len(writes)}개, 다른 이름 {different}개')
    return bool(different)


def export(data):
    return {'format': FORMAT, 'tables': [{'table': t, 'names': [{'id': i, 'bytes': n} for i, n in enumerate(names)]}
                                         for t, names in read_tables(data).items()]}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('rom')
    subs = parser.add_subparsers(dest='command', required=True)
    out = subs.add_parser('export')
    out.add_argument('-o', '--out', required=True)
    write = subs.add_parser('patch')
    write.add_argument('source')
    write.add_argument('-o', '--out', required=True)
    write.add_argument('--at')
    write.add_argument('--name', default='names')
    write.add_argument('--append', action='store_true', help='원래 항목 수 다음 id 부터 이름을 덧붙임(--at 과 함께)')
    verify = subs.add_parser('check')
    verify.add_argument('source', nargs='?')
    verify.add_argument('--at')
    verify.add_argument('--append', action='store_true')
    args = parser.parse_args()
    try:
        with open(args.rom, 'rb') as f:
            data = f.read()
        if args.command == 'export':
            result = export(data)
        else:
            doc = {'format': FORMAT, 'tables': []}
            if args.source:
                with open(args.source, encoding='utf-8') as f:
                    doc = json.load(f)
            if args.command == 'check':
                return int(check(data, doc, args.at, args.append))
            result = patch(data, doc, args.at, args.name, args.append)
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
