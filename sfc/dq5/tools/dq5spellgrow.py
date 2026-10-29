"""DQ5 전투 행동(주문)을 비어 있는 행동 번호 C6~D4 에 더한다.

행동 번호로 색인하는 표 가운데 MP·범위(26:8765)·실행 루틴(26:8865)·둘째 실행 표(26:8565)·처리 루틴(20:B7F9)은
처음부터 256칸(00~FF)이라 새 번호의 칸에 바로 쓴다. 이 칸들이 모두 빈 값(MP 1F·실행 DB0C·둘째 0070·처리 AF27)인
번호만 받는다. 주문 목록 창의 MP 숫자(21:9BB4)는 0 줄 안의 그 칸에 쓴다. 연출 표 둘(26:8BE0·26:8C75)은 우리 편
표의 C6~D4 가 몬스터 표와 겹치므로 --at 으로 옮겨 쓴다. 필드 주문 표(11:8024)는 JSR (abs,X) 라 뱅크 끝 스텁과
덧붙인 표로 늘린다. class 가 spell 이면 66 경계 비교 셋을 스텁으로 돌려 새 번호도 주문으로 다룬다.
element 를 주면 몬스터가 일행에게 쓸 때 갑옷 원소 표(27:80FC)에서 그 원소로 다룬다(20:ABF4 를 스텁으로).
이름(표 3)은 dq5namewrite.py --append 로 따로 늘린다. 형식: sfc/dq5/docs/dq5-build-format.md 의 「행동 번호 늘리기」.

  python sfc/dq5/tools/dq5spellgrow.py rom/dq5.sfc patch work/spellgrow.json --at 6E:8000 -o work/build/spellgrow.dq5patch.json
  python sfc/dq5/tools/dq5spellgrow.py rom/dq5.sfc check work/spellgrow.json --at 6E:8000

JSON: {"format": "dq5spellgrow/1", "spells": [{"id": "C6", "copy": "27", "class": "spell", "MP": 4, "menu_mp": 4,
                                             "element": "01"}]}
새 번호는 C6 부터 빈틈 없이 D4 까지 이어진다. copy 는 원래 행동(00~AA) 가운데 하나이고, 그 행동의 표 값을 모두 베낀다.
MP·범위·적쪽(26:8765, dq5tables.py 와 같은 뜻)과 menu_mp(21:9BB4)만 덮을 수 있다. class 는 spell 또는 skill(기본)이고
spell 을 앞에 몰아 둔다. copy 가 필드 주문(27~38)이면 필드 처리기도 베껴 필드에서 외울 수 있다.
element 는 원소 비트 하나(01 メラ·02 ギラ·04 ヒャド·08 バギ·10·20 숨·40 イオ·80 デイン)이고, 주지 않으면 원래처럼
갑옷으로 줄지 않는다.
"""
import argparse
import json
import re
import sys
from pathlib import Path

from dq5map import Rom, lorom
from dq5tables import SPELL_FIELDS, put

FORMAT = 'dq5spellgrow/1'
COUNT = 0xAB
# 66~D4 는 특기 번호이고, 그 가운데 C6~D4 는 아래 네 표가 모두 빈 값이다. BB~C0 도 비어 있으나 C1~C5 를 몬스터가
# 쓰므로 C6~D4 와 이어지지 않는다. 66 경계 스텁은 새 주문을 한 범위로 보므로 이어진 번호만 받는다.
FIRST, LAST = 0xC6, 0xD4
# 256칸 표: 이름 → (자리, 칸 크기, 빈 값).
WIDE = {
    'flags': (0x268765, 1, 0x1F),          # MP·범위·적쪽(26:839A·26:83D0)
    'executor': (0x268865, 2, 0xDB0C),     # 실행 루틴(대상 수)
    'executor_alt': (0x268565, 2, 0x0070),  # $1016 bit4 일 때 대신 읽는 표
    'handler': (0x20B7F9, 2, 0xAF27),      # 처리 루틴(20:AA9D·AAD0 의 JSR ($B7F9,X))
}
# 주문 목록 창의 MP 숫자. 21:9BAD 가 LDA $219BB4,X 로 읽는다. 66 뒤는 21:9C92 의 코드 앞까지 0 이다.
MENU_MP = 0x219BB4
# 연출 번호. 26:8B64 가 D5 이상이면 읽지 않고, 우리 편 표(8BE0)는 95 칸부터 몬스터 표(8C75)와 겹친다. 둘 다 D5 칸으로 옮긴다.
FX = {'fx_party': (0x268BE0, (0x268B6E,)), 'fx_monster': (0x268C75, (0x268B74,))}
FX_COUNT = 0xD5
# 11:8014 SBC #$27 / CMP #$12 / BCS 멈춤 / ASL / TAX / JSR ($8024,X). CMP 를 FF 로 풀고 JSR 을 스텁으로 돌린다.
FIELD = 0x118024
FIELD_FIRST, FIELD_COUNT = 0x27, 0x12
FIELD_LIMIT = 0x118017
FIELD_CALL = 0x11801C
FIELD_STUB = 0x11FFB0
FIELD_HANG = 0x118022
FIELD_END = 0x120000
# 행동 번호가 66 밑이면 주문으로 보는 비교. (자리, 원래 4바이트, 비교 명령, 경계, 주문 갈래, 특기 갈래, 같을 때 갈래).
#   25:8BF3 CMP #$66 / BCS: 습득 메시지 0C7「じゅもん」·19F「とくぎ」
#   20:8460 CPX #$66 / BCS: 66 밑이면 20:A7B4(저주 상태면 1/4 로 행동을 DF 로 바꿔 「のろいのため じゅもんは かきけされた」)
#   20:8EE8 CMP #$65 / BCC (이어서 BNE): $1073,X 가 65 이하면 $1016 bit4 를 켬
# 롬에서 #$65~#$67 을 행동 번호와 견주는 비교를 모두 찾은 것 가운데 이 셋만 경계다(나머지는 같음 비교·다른 값).
CLASS_SITES = (
    (0x258BF3, 'c9 66 b0 05', 0xC9, 0x66, 0x258BF7, 0x258BFC, None),
    (0x208460, 'e0 66 b0 17', 0xE0, 0x66, 0x208464, 0x20847B, None),
    (0x208EE8, 'c9 65 90 05', 0xC9, 0x65, 0x208EF1, 0x208EFB, 0x208EEE),
)

# 일행이 맞는 주문의 원소(20:ABDC). 20:ABF4 CMP #$13 / BCS 에서 행동 01~12·39~47 은 27:80E3, 8E~94 는 27:80F5 를
# 읽어 20:AC27 에서 $75 에 둔다. 그 밖의 번호는 20:AC8D 로 가 갑옷·$9E·$9F 장비 값을 빼지 않는다.
ELEMENT_SITE, ELEMENT_ORIG = 0x20ABF4, 'c9 13 b0 0a'
ELEMENT_LOW, ELEMENT_HIGH, ELEMENT_STORE = 0x20ABF8, 0x20AC02, 0x20AC27
ELEMENTS = (0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80)


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


def value(rom, base, size, n):
    return int.from_bytes(read(rom, base + n * size, size), 'little')


def hex_byte(v, name, low=0, high=0xFF):
    require(isinstance(v, str) and re.fullmatch(r'[0-9A-Fa-f]{2}', v) is not None, f'{name}: 16진 두 자리 문자열')
    n = int(v, 16)
    require(low <= n <= high, f'{name}: {low:02X}~{high:02X} 여야 함')
    return n


def address(v, name):
    require(isinstance(v, str) and re.fullmatch(r'[0-9A-Fa-f]{2}:[0-9A-Fa-f]{4}', v) is not None, f'{name}: BB:AAAA 형태여야 함')
    bank, low = (int(x, 16) for x in v.split(':'))
    require(bank <= 0x7D and low >= 0x8000, f'{name}: 뱅크 00~7D 의 8000~FFFF 여야 함')
    return bank << 16 | low


def check_original(rom, rows):
    """새 번호 칸이 빈 값이고, 바꿀 명령이 원래 롬 그대로인지. 다른 도구가 먼저 고쳤으면 거부한다."""
    for row in rows:
        n = row['id']
        for name, (base, size, empty) in WIDE.items():
            require(value(rom, base, size, n) == empty, f'{n:02X}: {name} 칸이 빈 값 {empty:X} 가 아님(이미 쓰는 번호)')
        require(read(rom, MENU_MP + n, 1) == b'\0', f'{n:02X}: 주문 목록 MP 칸이 0 이 아님')
    for name, (base, readers) in FX.items():
        for pc in readers:
            raw = read(rom, pc, 4)
            require(raw[0] == 0xBF and int.from_bytes(raw[1:], 'little') == base, f'{text(pc)}: {name} 원래 읽기 명령이 아님')
    require(read(rom, 0x219BAD, 4) == bytes.fromhex('bf b4 9b 21'), '21:9BAD 가 원래 LDA $219BB4,X 가 아님')
    require(read(rom, FIELD_LIMIT - 3, 6) == bytes.fromhex('e9 27 c9 12 b0 08'), '11:8014 의 필드 주문 범위 검사가 원래와 다름')
    require(read(rom, FIELD_CALL, 3) == bytes.fromhex('fc 24 80'), '11:801C 가 원래 JSR ($8024,X) 가 아님')


def new_rows(rom, doc):
    require(isinstance(doc, dict) and not doc.keys() - {'format', 'spells'} and doc.get('format') == FORMAT,
            f'format={FORMAT}·spells 만 받음')
    spells = doc.get('spells')
    require(isinstance(spells, list) and spells, 'spells 는 하나 이상인 배열')
    rows = []
    for i, row in enumerate(spells):
        require(isinstance(row, dict) and not row.keys() - {'id', 'copy', 'MP', '범위', '적쪽', 'menu_mp', 'class', 'element'},
                f'spells[{i}]: id·copy·MP·범위·적쪽·menu_mp·class·element 만 받음')
        n = hex_byte(row.get('id'), f'spells[{i}] id', FIRST, LAST)
        require(n == FIRST + i, f'spells[{i}] id: {FIRST + i:02X} 여야 함({FIRST:02X} 부터 빈틈 없이)')
        kind = row.get('class', 'skill')
        require(kind in ('spell', 'skill'), f'spells[{i}] class: spell 또는 skill')
        require(kind == 'skill' or all(r['class'] == 'spell' for r in rows), f'spells[{i}]: spell 은 skill 보다 앞에 두어야 함')
        src = hex_byte(row.get('copy'), f'spells[{i}] copy', 0, COUNT - 1)
        flags = [value(rom, WIDE['flags'][0], 1, src)]
        for field in ('MP', '범위', '적쪽'):
            if field in row:
                v = row[field]
                width = sum(w for _, _, w in SPELL_FIELDS[field][1])
                require(type(v) is int and 0 <= v < 1 << width, f'spells[{i}] {field}: 0~{(1 << width) - 1} 정수')
                put(flags, SPELL_FIELDS[field][1], v)
        menu = read(rom, MENU_MP + src, 1)[0]
        if 'menu_mp' in row:
            require(type(row['menu_mp']) is int and 0 <= row['menu_mp'] <= 0xFF, f'spells[{i}] menu_mp: 0~255 정수')
            menu = row['menu_mp']
        element = None
        if 'element' in row:
            element = hex_byte(row['element'], f'spells[{i}] element')
            require(element in ELEMENTS, f'spells[{i}] element: 원소 비트 하나(01·02·04·08·10·20·40·80)')
        rows.append({'id': n, 'copy': src, 'flags': flags[0], 'menu_mp': menu, 'class': kind, 'element': element})
    return rows


def wide_writes(rom, rows):
    writes = []
    for name, (base, size, _) in WIDE.items():
        for row in rows:
            n = row['id']
            new = bytes([row['flags']]) if name == 'flags' else read(rom, base + row['copy'] * size, size)
            writes.append({'at': text(base + n * size), 'hex': new.hex(' '), 'orig': read(rom, base + n * size, size).hex(' '),
                           'note': f'{name} {n:02X}'})
    first = rows[0]['id']
    writes.append({'at': text(MENU_MP + first), 'hex': bytes(r['menu_mp'] for r in rows).hex(' '),
                   'orig': read(rom, MENU_MP + first, len(rows)).hex(' '), 'note': '주문 목록 MP'})
    return writes


def fx_blob(rom, rows, start):
    out, place = bytearray(), {}
    for name, (base, _) in FX.items():
        place[name] = start + len(out)
        body = bytearray(read(rom, base, FX_COUNT))
        for row in rows:
            body[row['id']] = read(rom, base + row['copy'], 1)[0]
        out += body
    return bytes(out), place


def field_stub(rom, rows):
    """11:FFB0: X = (주문 - 27) * 2(8비트 ASL 에서 carry 로 빠진 bit8 을 되살리고 B 를 다시 0 으로).
    원래 18칸이면 JMP ($8024,X), 새 번호 범위면 덧붙인 표, 아니면 원래처럼 멈춤."""
    if not any(FIELD_FIRST <= row['copy'] < FIELD_FIRST + FIELD_COUNT for row in rows):
        return None
    first, last = rows[0]['id'], rows[-1]['id']
    lo, hi = (first - FIELD_FIRST) * 2, (last - FIELD_FIRST + 1) * 2
    table = FIELD_STUB + 34
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


def class_stubs(spells, start):
    """비교 셋마다 JML 로 올 스텁. 원래 경계 밑이거나 새 주문 범위면 주문 갈래, 아니면 특기 갈래(carry 를 켜고)."""
    first, last = spells[0]['id'], spells[-1]['id']
    out, entry = bytearray(), {}
    for site, _, op, limit, spell, skill, equal in CLASS_SITES:
        entry[site] = start + len(out)
        code = bytearray([op, limit, 0x90, 0])            # CMP #limit / BCC 주문
        if equal is not None:
            code += bytes([0xF0, 0])                       # BEQ 같을 때
        code += bytes([op, first, 0x90, 0])                # CMP #first / BCC 특기
        code += bytes([op, last + 1, 0x90, 0])             # CMP #last+1 / BCC 주문
        to_skill = len(code)
        code += bytes([0x38, 0x5C]) + skill.to_bytes(3, 'little')        # SEC / JML 특기
        to_spell = len(code)
        code += bytes([0x5C]) + spell.to_bytes(3, 'little')              # JML 주문
        if equal is not None:
            to_equal = len(code)
            code += bytes([0x5C]) + equal.to_bytes(3, 'little')
            code[5] = to_equal - 6
        branches = [i for i in range(0, to_skill, 2) if code[i] == 0x90]
        code[branches[0] + 1] = to_spell - (branches[0] + 2)
        code[branches[1] + 1] = to_skill - (branches[1] + 2)
        code[branches[2] + 1] = to_spell - (branches[2] + 2)
        out += code
    return bytes(out), entry


def element_stub(rows, start):
    """20:ABF4 에서 JML 로 올 스텁. 새 번호면 덧붙인 원소 표를 읽어 20:AC27 로, 아니면 원래 CMP #$13 / BCS 대로."""
    first, last = rows[0]['id'], rows[-1]['id']
    table = start + 32
    code = bytes([0xC9, first, 0x90, 0x10, 0xC9, last + 1, 0xB0, 0x0C, 0x38, 0xE9, first, 0xAA, 0xBF])  # CMP / BCC / CMP / BCS / SEC / SBC / TAX / LDA
    code += table.to_bytes(3, 'little') + bytes([0x5C]) + ELEMENT_STORE.to_bytes(3, 'little')            # 표,X / JML 20:AC27
    code += bytes([0xC9, 0x13, 0xB0, 0x04, 0x5C]) + ELEMENT_LOW.to_bytes(3, 'little')                    # CMP #$13 / BCS / JML 20:ABF8
    code += bytes([0x5C]) + ELEMENT_HIGH.to_bytes(3, 'little')                                           # JML 20:AC02
    require(len(code) == 32, '원소 스텁 길이')
    return code + bytes(row['element'] or 0 for row in rows)


def patch(rom, doc, at):
    rows = new_rows(rom, doc)
    check_original(rom, rows)
    writes = wide_writes(rom, rows)
    data, place = fx_blob(rom, rows, at)
    spells = [row for row in rows if row['class'] == 'spell']
    entry = {}
    if spells:
        stubs, entry = class_stubs(spells, at + len(data))
        data += stubs
    element_at = None
    if any(row['element'] is not None for row in rows):
        require(read(rom, ELEMENT_SITE, 4) == bytes.fromhex(ELEMENT_ORIG), f'{text(ELEMENT_SITE)}: 원래 비교 {ELEMENT_ORIG} 가 아님')
        element_at = at + len(data)
        data += element_stub(rows, element_at)
    require((at & 0xFFFF) + len(data) <= 0x10000, f'{text(at)}: {len(data)}바이트가 뱅크 끝을 넘음')
    writes.append({'at': text(at), 'hex': data.hex(' '), 'note': '옮긴 연출 표와 66 경계·원소 스텁'})
    if element_at is not None:
        writes.append({'at': text(ELEMENT_SITE), 'hex': (bytes([0x5C]) + element_at.to_bytes(3, 'little')).hex(' '),
                       'orig': ELEMENT_ORIG, 'note': '일행이 맞는 주문 원소를 스텁으로(새 번호의 갑옷 원소)'})
    for name, (base, readers) in FX.items():
        for pc in readers:
            writes.append({'at': text(pc + 1), 'hex': place[name].to_bytes(3, 'little').hex(' '),
                           'orig': read(rom, pc + 1, 3).hex(' '), 'note': f'{name} 표 읽기'})
    for site, orig, *_ in CLASS_SITES:
        if site in entry:
            require(read(rom, site, 4) == bytes.fromhex(orig), f'{text(site)}: 원래 비교 {orig} 가 아님')
            writes.append({'at': text(site), 'hex': (bytes([0x5C]) + entry[site].to_bytes(3, 'little')).hex(' '),
                           'orig': orig, 'note': '행동 번호 66 경계를 스텁으로(새 번호도 주문)'})
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


def element_of(rom, action):
    """20:ABF4 부터 롬 코드를 돌려 행동의 원소를 얻는다. 20:AC27 에 닿으면 A, 20:AC8D(원소 없음)면 None."""
    from w65816 import Cpu
    cpu = Cpu(rom.d, bytes(0x20000))
    cpu.pbr, cpu.pc, cpu.p, cpu.a = ELEMENT_SITE >> 16, ELEMENT_SITE & 0xFFFF, 0x30, action
    for _ in range(64):
        here = cpu.pbr << 16 | cpu.pc
        if here == ELEMENT_STORE:
            return cpu.a & 0xFF
        if here == 0x20AC8D:
            return None
        cpu.step()
    raise ValueError(f'{action:02X}: 원소 갈래가 20:AC27·AC8D 에 닿지 않음')


def check(rom, doc, at):
    from dq5build import PatchError, build, parse_at
    made = patch(rom, doc, at)
    lists = [('spellgrow', made.get('rom_size', 0), [
        (parse_at(w['at'])[0], bytes.fromhex(w['hex']), bytes.fromhex(w['orig']) if 'orig' in w else None, w['note'])
        for w in made['writes']])]
    try:
        rebuilt, _ = build(rom.d, lists, made.get('rom_size', 0))
    except PatchError as error:
        raise ValueError(str(error)) from None
    after = Rom(rebuilt)
    for row in new_rows(rom, doc):
        n, src = row['id'], row['copy']
        require(value(after, WIDE['flags'][0], 1, n) == row['flags'], f'{n:02X}: MP·범위 칸이 다름')
        for name in ('executor', 'executor_alt', 'handler'):
            base, size, _ = WIDE[name]
            require(value(after, base, size, n) == value(rom, base, size, src), f'{n:02X}: {name} 칸이 {src:02X} 와 다름')
        require(read(after, MENU_MP + n, 1)[0] == row['menu_mp'], f'{n:02X}: 주문 목록 MP 가 다름')
        for name, (base, readers) in FX.items():
            where = {int.from_bytes(read(after, pc + 1, 3), 'little') for pc in readers}
            require(len(where) == 1, f'{name}: 읽는 곳들이 서로 다른 자리를 가리킴')
            where = where.pop()
            require(read(after, where + n, 1) == read(rom, base + src, 1), f'{n:02X}: {name} 칸이 다름')
    for name, (base, readers) in FX.items():
        where = int.from_bytes(read(after, readers[0] + 1, 3), 'little')
        moved = bytearray(read(after, where, FX_COUNT))
        for row in new_rows(rom, doc):
            moved[row['id']] = read(rom, base + row['id'], 1)[0]
        require(bytes(moved) == read(rom, base, FX_COUNT), f'{name}: 옮긴 표의 원래 칸이 다름')
    if any(row['element'] is not None for row in new_rows(rom, doc)):
        # element 를 주지 않은 새 번호는 표 값 0 이라 갑옷 항목과 맞는 것이 없다.
        wanted = {row['id']: row['element'] or 0 for row in new_rows(rom, doc)}
        for n in range(0x100):
            want = wanted[n] if n in wanted else element_of(rom, n)
            got = element_of(after, n)
            require(got == want, f'{n:02X}: 갑옷 원소 {got} 이 {want} 가 아님')
    print(f'새 행동 {len(new_rows(rom, doc))}개, 쓰기 {len(made["writes"])}개 검사 통과')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    sub = ap.add_subparsers(dest='command', required=True)
    for name in ('patch', 'check'):
        p = sub.add_parser(name)
        p.add_argument('source', type=Path)
        p.add_argument('--at', required=True, help='옮긴 연출 표와 스텁을 둘 자리 BB:AAAA(다른 패치와 겹치지 않게)')
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
