"""DQ5 전투 행동(주문) 번호를 AB 이상으로 늘린다.

행동 번호로 색인하는 표를 새 번호까지 늘린다. 긴 주소로 읽는 표 여섯은 --at 자리로 옮겨 쓰고 읽는 곳을 바꾼다.
처리 루틴 표(20:B7F9)와 필드 주문 표(11:8024)는 JSR (abs,X) 라 같은 뱅크에 있어야 하므로, 원래 표는 두고
뱅크 끝 빈 자리에 새 번호만 고르는 스텁과 덧붙인 표를 둔다. 이름(표 3)은 dq5namewrite.py --append 로 따로 늘린다.
형식: sfc/dq5/docs/dq5-build-format.md 의 「행동 번호 늘리기」.

  python sfc/dq5/tools/dq5spellgrow.py rom/dq5.sfc patch work/spellgrow.json --at 3D:8000 -o work/build/spellgrow.dq5patch.json
  python sfc/dq5/tools/dq5spellgrow.py rom/dq5.sfc check work/spellgrow.json --at 3D:8000

JSON: {"format": "dq5spellgrow/1", "spells": [{"id": "AB", "copy": "27", "MP": 4, "menu_mp": 4}]}
새 번호는 AB 부터 빈틈 없이 B4 까지 이어진다. copy 는 원래 행동(00~AA) 가운데 하나이고, 그 행동의 표 값을 모두 베낀다.
MP·범위·적쪽(26:8765, dq5tables.py 와 같은 뜻)과 menu_mp(21:9BB4, 주문 목록 창의 MP 숫자)만 덮을 수 있다.
copy 가 필드 주문(27~38)이면 필드 처리기도 베껴 필드에서 외울 수 있다.
"""
import argparse
import json
import re
import sys
from pathlib import Path

from dq5map import Rom, lorom
from dq5tables import SPELL_FIELDS, get, put

FORMAT = 'dq5spellgrow/1'
COUNT = 0xAB
# 처리 루틴 스텁(20:FFE0~FFFF)에 덧붙일 수 있는 것이 10개라 새 번호는 AB~B4 다(20:8455 는 D5 부터 전투 도구로 본다).
LAST = 0xB4
# 긴 주소로 읽는 표: 이름 → (원래 자리, 항목 크기, [(LDA long,X 명령 주소)]). 모두 X 를 행동 번호(또는 ×2)로 쓴다.
TABLES = {
    'flags': (0x268765, 1, (0x2683A1, 0x2683D7)),       # MP·범위·적쪽(26:839A·26:83D0)
    'executor': (0x268865, 2, (0x208497,)),              # 실행 루틴(대상 수)
    'executor_alt': (0x268565, 2, (0x2084A6,)),          # $1016 bit4 일 때 대신 읽는 표
    'menu_mp': (0x219BB4, 1, (0x219BAD,)),              # 주문 목록 창의 MP 숫자
    'fx_party': (0x268BE0, 1, (0x268B6E,)),             # 연출 번호(우리 편)
    'fx_monster': (0x268C75, 1, (0x268B74,)),           # 연출 번호(몬스터)
}
# 20:AA9D·20:AAD0 의 JSR ($B7F9,X)(X = 행동×2). 원래 171개는 그대로 두고, 이 둘을 스텁 JSR 로 바꾼다.
HANDLERS = 0x20B7F9
HANDLER_CALLS = (0x20AA9D, 0x20AAD0)
HANDLER_STUB = 0x20FFE0
HANDLER_END = 0x210000
# 11:8014 SBC #$27 / CMP #$12 / BCS 멈춤 / ASL / TAX / JSR ($8024,X). CMP 를 FF 로 풀고 JSR 을 스텁으로 돌린다.
FIELD = 0x118024
FIELD_FIRST, FIELD_COUNT = 0x27, 0x12
FIELD_LIMIT = 0x118017
FIELD_CALL = 0x11801C
FIELD_STUB = 0x11FFB0
FIELD_HANG = 0x118022
FIELD_END = 0x120000


def require(ok, message):
    if not ok:
        raise ValueError(message)


def text(addr):
    return f'{addr >> 16:02X}:{addr & 0xFFFF:04X}'


def read(rom, addr, size):
    off = lorom(addr)
    raw = bytes(rom.d[off:off + size])
    require(len(raw) == size, f'{text(addr)}: 롬 범위 밖')
    return raw


def hex_byte(value, name, low=0, high=0xFF):
    require(isinstance(value, str) and re.fullmatch(r'[0-9A-Fa-f]{2}', value) is not None, f'{name}: 16진 두 자리 문자열')
    v = int(value, 16)
    require(low <= v <= high, f'{name}: {low:02X}~{high:02X} 여야 함')
    return v


def address(value, name):
    require(isinstance(value, str) and re.fullmatch(r'[0-9A-Fa-f]{2}:[0-9A-Fa-f]{4}', value) is not None,
            f'{name}: BB:AAAA 형태여야 함')
    bank, low = (int(v, 16) for v in value.split(':'))
    require(bank <= 0x7D and low >= 0x8000, f'{name}: 뱅크 00~7D 의 8000~FFFF 여야 함')
    return bank << 16 | low


def check_original(rom):
    """바꿀 명령·표 자리가 원래 롬 그대로인지. 다른 도구가 먼저 고쳤으면 거부한다."""
    for name, (base, _, readers) in TABLES.items():
        for pc in readers:
            raw = read(rom, pc, 4)
            require(raw[0] == 0xBF and int.from_bytes(raw[1:], 'little') == base,
                    f'{text(pc)}: {name} 표를 읽는 원래 명령(LDA {text(base)},X)이 아님')
    for pc in HANDLER_CALLS:
        require(read(rom, pc, 3) == bytes([0xFC]) + (HANDLERS & 0xFFFF).to_bytes(2, 'little'),
                f'{text(pc)}: 원래 JSR ($B7F9,X) 가 아님')
    require(read(rom, FIELD_LIMIT - 3, 6) == bytes.fromhex('e9 27 c9 12 b0 08'), '11:8014 의 필드 주문 범위 검사가 원래와 다름')
    require(read(rom, FIELD_CALL, 3) == bytes.fromhex('fc 24 80'), '11:801C 가 원래 JSR ($8024,X) 가 아님')
    require(read(rom, HANDLER_STUB, HANDLER_END - HANDLER_STUB) == bytes(HANDLER_END - HANDLER_STUB),
            '20:FFE0~FFFF 가 0 이 아님')


def new_rows(rom, doc):
    keys = {'format', 'spells'}
    require(isinstance(doc, dict) and not doc.keys() - keys and doc.get('format') == FORMAT, f'format={FORMAT}·spells 만 받음')
    spells = doc.get('spells')
    require(isinstance(spells, list) and spells, 'spells 는 하나 이상인 배열')
    rows = []
    for i, row in enumerate(spells):
        require(isinstance(row, dict) and not row.keys() - {'id', 'copy', 'MP', '범위', '적쪽', 'menu_mp'},
                f'spells[{i}]: id·copy·MP·범위·적쪽·menu_mp 만 받음')
        n = hex_byte(row.get('id'), f'spells[{i}] id', COUNT, LAST)
        require(n == COUNT + i, f'spells[{i}] id: {COUNT + i:02X} 여야 함(AB 부터 빈틈 없이)')
        src = hex_byte(row.get('copy'), f'spells[{i}] copy', 0, COUNT - 1)
        flags = [read(rom, TABLES['flags'][0] + src, 1)[0]]
        for field in ('MP', '범위', '적쪽'):
            if field in row:
                value = row[field]
                width = sum(w for _, _, w in SPELL_FIELDS[field][1])
                require(type(value) is int and 0 <= value < 1 << width, f'spells[{i}] {field}: 0~{(1 << width) - 1} 정수')
                put(flags, SPELL_FIELDS[field][1], value)
        menu = read(rom, TABLES['menu_mp'][0] + src, 1)[0]
        if 'menu_mp' in row:
            require(type(row['menu_mp']) is int and 0 <= row['menu_mp'] <= 0xFF, f'spells[{i}] menu_mp: 0~255 정수')
            menu = row['menu_mp']
        rows.append({'id': n, 'copy': src, 'flags': flags[0], 'menu_mp': menu})
    return rows


def blob(rom, rows, start):
    """옮길 표 여섯을 start 부터 이어 놓은 (바이트, {표: 새 자리})."""
    out, place = bytearray(), {}
    for name, (base, size, _) in TABLES.items():
        place[name] = start + len(out)
        body = bytearray(read(rom, base, COUNT * size))
        for row in rows:
            if name == 'flags':
                body += bytes([row['flags']])
            elif name == 'menu_mp':
                body += bytes([row['menu_mp']])
            else:
                body += read(rom, base + row['copy'] * size, size)
        out += body
    return bytes(out), place


def handler_stub(rom, rows):
    """20:FFE0: CPX #$0156 / BCS +3 / JMP ($B7F9,X) / JMP (덧붙인 표 - $0156,X), 그 뒤 덧붙인 표."""
    table = HANDLER_STUB + 11
    code = (bytes([0xE0]) + (COUNT * 2).to_bytes(2, 'little') + bytes([0xB0, 0x03, 0x7C]) + (HANDLERS & 0xFFFF).to_bytes(2, 'little')
            + bytes([0x7C]) + ((table - COUNT * 2) & 0xFFFF).to_bytes(2, 'little'))
    body = b''.join(read(rom, HANDLERS + row['copy'] * 2, 2) for row in rows)
    require(table + len(body) <= HANDLER_END, f'20:FFE0~FFFF 에 새 행동 {len(rows)}개의 처리 루틴이 들어가지 않음(10개까지)')
    return code + body


def field_stub(rom, rows):
    """11:FFB0: X = (주문 - 27) * 2(carry 로 빠진 bit8 을 되살림). 원래 18칸이면 JMP ($8024,X),
    새 번호 범위면 덧붙인 표, 아니면 원래처럼 멈춤."""
    fields = [row for row in rows if FIELD_FIRST <= row['copy'] < FIELD_FIRST + FIELD_COUNT]
    if not fields:
        return None
    first, last = rows[0]['id'], rows[-1]['id']
    lo, hi = (first - FIELD_FIRST) * 2, (last - FIELD_FIRST + 1) * 2
    table = FIELD_STUB + 34
    # 11:801A 의 ASL 은 A 8비트라 주문 A7 이상이면 (주문-27)*2 의 bit8 이 carry 로 빠진다. TAX 앞에 B 를 01 로 둔다.
    code = bytes([0x90, 0x05, 0xEB, 0xA9, 0x01, 0xEB, 0xAA])                                  # BCC / XBA / LDA #1 / XBA / TAX
    code += bytes([0xEB, 0xA9, 0x00, 0xEB])                                                   # B 를 다시 0 으로
    code += bytes([0xE0]) + (FIELD_COUNT * 2).to_bytes(2, 'little') + bytes([0xB0, 0x03, 0x7C]) + (FIELD & 0xFFFF).to_bytes(2, 'little')
    code += bytes([0xE0]) + lo.to_bytes(2, 'little') + bytes([0x90, 0x08])                    # CPX #lo / BCC 멈춤
    code += bytes([0xE0]) + hi.to_bytes(2, 'little') + bytes([0xB0, 0x03])                    # CPX #hi / BCS 멈춤
    code += bytes([0x7C]) + ((table - lo) & 0xFFFF).to_bytes(2, 'little')                     # JMP (표 - lo,X)
    code += bytes([0x80, 0xFE])                                                               # 멈춤: BRA *
    require(len(code) == 34, '필드 스텁 길이')
    # 필드 처리기가 없는 새 행동은 원래 표의 빈 칸과 같이 11:8022(BRA *)로 둔다. 필드 목록에 넣지 않으면 불리지 않는다.
    none = (FIELD_HANG & 0xFFFF).to_bytes(2, 'little')
    body = b''.join(read(rom, FIELD + (row['copy'] - FIELD_FIRST) * 2, 2) if FIELD_FIRST <= row['copy'] < FIELD_FIRST + FIELD_COUNT
                    else none for row in rows)
    require(table + len(body) <= FIELD_END, f'11:FFB0~FFFF 에 새 행동 {len(rows)}개의 필드 처리기가 들어가지 않음')
    return code + body


def patch(rom, doc, at):
    check_original(rom)
    rows = new_rows(rom, doc)
    data, place = blob(rom, rows, at)
    require((at & 0xFFFF) + len(data) <= 0x10000, f'{text(at)}: 표 {len(data)}바이트가 뱅크 끝을 넘음')
    writes = [{'at': text(at), 'hex': data.hex(' '), 'note': '행동 번호로 색인하는 표(옮겨 늘림)'}]
    for name, (base, size, readers) in TABLES.items():
        for pc in readers:
            writes.append({'at': text(pc + 1), 'hex': place[name].to_bytes(3, 'little').hex(' '),
                           'orig': read(rom, pc + 1, 3).hex(' '), 'note': f'{name} 표 읽기'})
    stub = handler_stub(rom, rows)
    writes.append({'at': text(HANDLER_STUB), 'hex': stub.hex(' '), 'orig': read(rom, HANDLER_STUB, len(stub)).hex(' '),
                   'note': '처리 루틴 스텁과 덧붙인 표'})
    for pc in HANDLER_CALLS:
        writes.append({'at': text(pc), 'hex': (bytes([0x20]) + (HANDLER_STUB & 0xFFFF).to_bytes(2, 'little')).hex(' '),
                       'orig': read(rom, pc, 3).hex(' '), 'note': '처리 루틴 JSR 을 스텁으로'})
    stub = field_stub(rom, rows)
    if stub is not None:
        writes.append({'at': text(FIELD_STUB), 'hex': stub.hex(' '), 'note': '필드 주문 스텁과 덧붙인 표'})
        writes.append({'at': text(FIELD_LIMIT), 'hex': 'ff', 'orig': read(rom, FIELD_LIMIT, 1).hex(' '),
                       'note': '필드 주문 범위 검사를 스텁으로 넘김'})
        writes.append({'at': text(FIELD_CALL), 'hex': (bytes([0x20]) + (FIELD_STUB & 0xFFFF).to_bytes(2, 'little')).hex(' '),
                       'orig': read(rom, FIELD_CALL, 3).hex(' '), 'note': '필드 주문 JSR 을 스텁으로'})
    out = {'format': 'dq5patch/1', 'name': 'spellgrow', 'writes': writes}
    end = lorom(at) + len(data)
    if end > 0x180000:
        out['rom_size'] = 4 if end > 0x300000 else 3 if end > 0x200000 else 2
    return out


def read_back(rom, at, count):
    """빌드한 롬에서 표를 읽어 새 행동마다 (flags, executor, executor_alt, menu_mp, fx_party, fx_monster, 처리 루틴)."""
    out = []
    for n in range(COUNT, COUNT + count):
        row = []
        for name, (base, size, readers) in TABLES.items():
            where = int.from_bytes(read(rom, readers[0] + 1, 3), 'little')
            row.append(read(rom, where + n * size, size).hex())
        stub = HANDLER_STUB + 11 + (n - COUNT) * 2
        row.append(read(rom, stub, 2).hex())
        out.append(row)
    return out


def check(rom, doc, at):
    from dq5build import build, parse_at
    made = patch(rom, doc, at)
    lists = [('spellgrow', made.get('rom_size', 0), [
        (parse_at(w['at'])[0], bytes.fromhex(w['hex']), bytes.fromhex(w['orig']) if 'orig' in w else None, w['note'])
        for w in made['writes']])]
    from dq5build import PatchError
    try:
        rebuilt, _ = build(rom.d, lists, made.get('rom_size', 0))
    except PatchError as error:
        raise ValueError(str(error)) from None
    after = Rom(rebuilt)
    rows = new_rows(rom, doc)
    got = read_back(after, at, len(rows))
    for row, values in zip(rows, got):
        src = row['copy']
        want = [bytes([row['flags']]).hex(), read(rom, 0x268865 + src * 2, 2).hex(), read(rom, 0x268565 + src * 2, 2).hex(),
                bytes([row['menu_mp']]).hex(), read(rom, 0x268BE0 + src, 1).hex(), read(rom, 0x268C75 + src, 1).hex(),
                read(rom, HANDLERS + src * 2, 2).hex()]
        require(values == want, f'{row["id"]:02X}: 빌드한 롬에서 읽은 값 {values} 가 {want} 와 다름')
    for name, (base, size, readers) in TABLES.items():
        where = {int.from_bytes(read(after, pc + 1, 3), 'little') for pc in readers}
        require(len(where) == 1, f'{name}: 읽는 곳들이 서로 다른 자리를 가리킴')
        where = where.pop()
        require(read(after, where, COUNT * size) == read(rom, base, COUNT * size), f'{name}: 옮긴 표의 원래 {COUNT}개가 다름')
    print(f'새 행동 {len(rows)}개({rows[0]["id"]:02X}~{rows[-1]["id"]:02X}), 쓰기 {len(made["writes"])}개 검사 통과')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    sub = ap.add_subparsers(dest='command', required=True)
    for name in ('patch', 'check'):
        p = sub.add_parser(name)
        p.add_argument('source', type=Path)
        p.add_argument('--at', required=True, help='옮긴 표 여섯을 둘 자리 BB:AAAA(다른 패치와 겹치지 않게)')
        if name == 'patch':
            p.add_argument('-o', '--out', type=Path, required=True)
    args = ap.parse_args()
    try:
        rom = Rom(args.rom.read_bytes())
        doc = json.loads(args.source.read_text(encoding='utf-8'))
        at = address(args.at, '--at')
        if args.command == 'check':
            check(rom, doc, at)
            return 0
        out = patch(rom, doc, at)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(f'쓰기 {len(out["writes"])}개 → {args.out}')
        return 0
    except (ValueError, OSError) as error:
        print(f'오류: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
