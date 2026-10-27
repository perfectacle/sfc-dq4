"""DQ5 사람·몬스터의 주문 습득과 필드/전투 주문 목록을 쓴다.

습득 표는 23:EB50 이 데이터 뱅크 23 에서 23:ECE3(사람)·23:ECEE(몬스터)의 LDX 즉값부터 [개수][레벨, 마스크 3]… 를
인물 번호만큼 건너뛰어 읽는다. 목록은 21:9C92(필드)·21:9D03(전투)이 23:BD53·23:BDBD 의 16비트 포인터와
21:9CA2·21:9D13 의 뱅크 즉값으로 [$3A] 롱 포인터를 만들어 읽는다. 형식은 sfc/dq5/docs/dq5-data-format.md 의 주문 습득 절.

항목 수·목록 길이를 바꿀 수 있다. 원래 자리에 들어가지 않으면 습득 표는 23:B819~BD52 에 다시 채우거나 --learn-at 으로,
목록은 23:BE27~C013 에 다시 채우거나 --lists-at 으로 옮긴다. 습득 표를 뱅크 23 밖(30~3F)에 두려면 --stub-at(뱅크 23)에
데이터 뱅크를 바꾸는 8바이트 루틴을 둔다.

  python sfc/dq5/tools/dq5learnwrite.py rom/dq5.sfc dump -o work/learn.json
  python sfc/dq5/tools/dq5learnwrite.py rom/dq5.sfc patch work/learn.json -o work/learn.patch.json \\
      [--learn-at 3F:8000 --stub-at 23:FF20] [--lists-at 3F:9000] [--spells-from work/build/spellgrow.sfc]
  python sfc/dq5/tools/dq5learnwrite.py rom/dq5.sfc check work/learn.json [같은 옵션]
"""
import argparse
import json
import re
import sys
from pathlib import Path

from dq5map import Rom, lorom

FORMAT = 'dq5learn/1'
GROUPS = {'person': (11, 0x23B819, 0x23B978, 0), 'monster': (42, 0x23B979, 0x23BD53, 11)}
TABLES = {'field': 0x23BD53, 'battle': 0x23BDBD}
COMPANIONS = 0x23AED1
# 21:9CD1 이 필드 슬롯을 비트 0~7, 21:9D21 이 전투 슬롯을 비트 8~19 로 센다(습득 마스크 3바이트).
CAPS = {'field': 8, 'battle': 12}
# 동료 몬스터의 전투 とくぎ 창은 칸 0~7 만 칸 번호 자리에 놓는다(칸 8 을 배워도 창에 나오지 않음, 실측).
MONSTER_BATTLE = 8
LEARN_REGION = (0x23B819, 0x23BD53)
LIST_REGION = (0x23BE27, 0x23C014)
# 23:ECD7 의 LDY #$0000 자리. 습득 표를 다른 뱅크에 두면 이 자리를 JSR 로 바꿔 데이터 뱅크를 고친다.
LDY_AT, LDY = 0x23ECD7, bytes.fromhex('a0 00 00')
BASE_AT = {'person': 0x23ECE4, 'monster': 0x23ECEF}
BANK_AT = {'field': 0x219CA2, 'battle': 0x219D13}
# 사람이 일행에 들 때(21:8042 → 21:9F78 등) 인물 레코드 표 23:C014 의 칸을 그대로 베낀다. 습득 비트는 그 칸의 +23~+25 이고
# 습득 표(23:EB50)는 이때 불리지 않는다(실측). 칸 +0 이 인물 번호(bit7 이면 동료 몬스터 종류).
# dq5spellgrow.py 로 더한 행동 번호(C6~D4). 256칸 처리 루틴 표(20:B7F9)의 그 칸이 빈 값 AF27 이 아니면 새 행동이다.
# 11:801C 가 11:FFB0 스텁으로 가면 그 표(11:FFD2~, C6 부터)의 칸이 11:8022(멈춤)가 아닌 새 번호만 필드에서 외울 수 있다.
SPELLS = 0xAB
NEW_FIRST, NEW_LAST = 0xC6, 0xD4
HANDLERS, HANDLER_EMPTY = 0x20B7F9, 0xAF27
FIELD_CALL, FIELD_STUB, FIELD_HANG = 0x11801C, 0x11FFB0, 0x8022
FIELD_SPELLS = set(range(0x27, 0x39)) - {0x2A, 0x2B, 0x30, 0x31}
JOIN = 0x23C014
JOIN_COUNT = 13
JOIN_SIZE = 42


def require(ok, message):
    if not ok:
        raise ValueError(message)


def keys(value, allowed, name):
    require(isinstance(value, dict), f'{name}: 객체가 필요함')
    require(not value.keys() - set(allowed), f'{name}: 지원하지 않는 필드 {value.keys() - set(allowed)}')


def integer(value, low, high, name):
    require(type(value) is int and low <= value <= high, f'{name}: {low}~{high} 정수여야 함')
    return value


def read(rom, address, count):
    off = lorom(address)
    raw = bytes(rom.d[off:off + count])
    require(len(raw) == count, '입력 롬이 표보다 짧음')
    return raw


def stub(bank):
    """LDA #bank / PHA / PLB / LDY #$0000 / RTS. 23:EB50 은 끝(23:ED38)에서 PLB 로 부른 쪽 데이터 뱅크를 되돌린다."""
    return bytes([0xA9, bank, 0x48, 0xAB, 0xA0, 0x00, 0x00, 0x60])


def config(rom):
    """지금 롬의 습득 표 시작·뱅크와 목록 뱅크."""
    at = read(rom, LDY_AT, 3)
    if at == LDY:
        bank, stub_at = 0x23, None
    else:
        require(at[0] == 0x20, '23:ECD7 이 LDY #0 도 JSR 도 아님')
        stub_at = 0x230000 | int.from_bytes(at[1:], 'little')
        code = read(rom, stub_at, 8)
        require(code == stub(code[1]), f'{stub_at:06X}: 데이터 뱅크 루틴이 아님')
        bank = code[1]
    bases = {kind: bank << 16 | int.from_bytes(read(rom, at, 2), 'little') for kind, at in BASE_AT.items()}
    banks = {name: read(rom, at, 1)[0] for name, at in BANK_AT.items()}
    return {'bases': bases, 'bank': bank, 'stub': stub_at, 'banks': banks}


def layout(rom, cfg=None):
    cfg = cfg or config(rom)
    rows = {}
    for kind, (count, _, _, offset) in GROUPS.items():
        address = cfg['bases'][kind]
        for index in range(count):
            n = read(rom, address, 1)[0]
            require((address & 0xFFFF) + 1 + n * 4 <= 0x10000, '습득 표가 뱅크를 넘음')
            parts = {'learn': (address, read(rom, address, 1 + n * 4))}
            for name, table in TABLES.items():
                pointer = cfg['banks'][name] << 16 | int.from_bytes(read(rom, table + (offset + index) * 2, 2), 'little')
                size = read(rom, pointer, 1)[0]
                require(pointer & 0xFFFF >= 0x8000 and size <= CAPS[name] and (pointer & 0xFFFF) + size + 1 <= 0x10000,
                        f'{name} 목록 {pointer:06X}: 길이나 자리가 맞지 않음')
                parts[name] = (pointer, read(rom, pointer, size + 1))
            rows[kind, index] = parts
            address += 1 + n * 4
        if kind == 'person':
            # 사람 번호 & 3F 가 11 이면 걷기가 사람 표 끝 다음 바이트(원본 23:B978 = 00)를 개수로 읽고, 12 이상이면
            # 몬스터 표로 넘어간다(코드 읽기). 그 바이트와 두 표가 붙어 있는 것을 늘 지킨다.
            require(address + 1 == cfg['bases']['monster'], '사람 표 끝 + 1 바이트가 몬스터 표 시작이 아님')
    return rows


def person_tail(rom, cfg):
    return read(rom, cfg['bases']['monster'] - 1, 1)


def decode(parts):
    raw = parts['learn'][1]
    learn = []
    for pos in range(1, len(raw), 4):
        mask = int.from_bytes(raw[pos + 1:pos + 4], 'little')
        require(mask < 1 << 20, '지원하지 않는 습득 상위 비트')
        learn.append({'level': raw[pos], 'field_slots': [i for i in range(8) if mask & (1 << i)],
                      'battle_slots': [i for i in range(12) if mask & (1 << (i + 8))]})
    return {'learn': learn, **{name: list(parts[name][1][1:]) for name in TABLES}}


def join_owner(rom, entry):
    """인물 레코드 표 칸의 (kind, index)."""
    first = read(rom, JOIN + entry * JOIN_SIZE, 1)[0]
    return ('monster', first & 0x7F) if first & 0x80 else ('person', first & 0x3F)


def owner_name(owner):
    return f'{owner[0]} {owner[1]:02X}'


def join_rows(rom):
    out = []
    for k in range(JOIN_COUNT):
        mask = int.from_bytes(read(rom, JOIN + k * JOIN_SIZE + 0x23, 3), 'little') & 0xFFFFF
        out.append({'entry': k, 'owner': owner_name(join_owner(rom, k)), 'field_slots': [i for i in range(8) if mask >> i & 1],
                    'battle_slots': [i for i in range(12) if mask >> (i + 8) & 1]})
    return out


def dump(rom):
    return {'format': FORMAT, 'characters': [dict(kind=kind, index=index, **decode(parts))
                                            for (kind, index), parts in layout(rom).items()],
            'join': join_rows(rom)}


def spells(rom):
    """(전투 목록에 넣을 수 있는 가장 큰 행동 번호, 필드 목록에 넣을 수 있는 번호 집합)."""
    battle, field = SPELLS - 1, set(FIELD_SPELLS)
    n = NEW_FIRST
    while n <= NEW_LAST and int.from_bytes(read(rom, HANDLERS + n * 2, 2), 'little') != HANDLER_EMPTY:
        battle = n
        n += 1
    if battle >= NEW_FIRST and read(rom, FIELD_CALL, 3) == bytes([0x20]) + (FIELD_STUB & 0xFFFF).to_bytes(2, 'little'):
        for n in range(NEW_FIRST, battle + 1):
            if int.from_bytes(read(rom, FIELD_STUB + 34 + (n - NEW_FIRST) * 2, 2), 'little') != FIELD_HANG:
                field.add(n)
    return battle, field


def encode(old, change, floor=2, caps=None, allowed=None):
    caps = caps or CAPS
    battle_max, field_ok = allowed or (SPELLS - 1, FIELD_SPELLS)
    result = old | {k: v for k, v in change.items() if k in ('learn', 'field', 'battle')}
    for name in TABLES:
        values = result[name]
        require(isinstance(values, list) and len(values) <= caps[name], f'{name}: {caps[name]}칸까지의 배열이어야 함')
        for value in values:
            integer(value, 1, battle_max, name)
            require(name != 'field' or value in field_ok, f'필드에서 외울 수 없는 주문 {value:02X}')
    learn = result['learn']
    require(isinstance(learn, list) and len(learn) <= 99, 'learn: 99개까지의 배열이어야 함')
    # 23:EB50 은 레벨이 오를 때와 동료가 될 때(21:81D5, 처음 레벨) 그 레벨의 항목만 찾는다.
    # floor 보다 낮은 레벨은 원본에 그 레벨 항목이 있던 경우만 받는다. 사람이 일행에 들 때는 23:EB50 이 불리지 않아
    # (실측) 사람의 레벨 1 항목은 쓰이지 않는다.
    low = {row['level'] for row in old['learn'] if row['level'] < floor}
    raw = bytearray([len(learn)])
    previous = 0
    for row in learn:
        keys(row, ('level', 'field_slots', 'battle_slots'), 'learn 항목')
        require(set(row) == {'level', 'field_slots', 'battle_slots'}, 'learn 항목의 필드가 빠짐')
        level = integer(row['level'], 1, 99, 'level')
        require(level > previous, '습득 레벨은 중복 없이 오름차순이어야 함')
        require(level >= floor or level in low,
                f'레벨 {floor} 보다 낮은 항목은 배울 기회가 없음(몬스터는 동료 표의 처음 레벨, 사람은 2. '
                '사람이 일행에 들 때의 주문은 습득 표가 아니라 join 으로 정함)')
        previous = level
        mask = 0
        for name, shift in (('field', 0), ('battle', 8)):
            slots = row[name + '_slots']
            require(isinstance(slots, list), '슬롯은 배열이어야 함')
            seen = set()
            for slot in slots:
                integer(slot, 0, len(result[name]) - 1, name + ' slot')
                require(slot not in seen, '중복 습득 슬롯')
                seen.add(slot)
                mask |= 1 << (shift + slot)
        require(mask != 0, '습득 슬롯이 비었음')
        raw.extend(bytes([level]) + mask.to_bytes(3, 'little'))
    return {'learn': bytes(raw), **{name: bytes([len(result[name]), *result[name]]) for name in TABLES}}


def cpu(address):
    return f'{address >> 16:02X}:{address & 0xFFFF:04X}'


def parse_at(value, name):
    m = re.fullmatch(r'([0-9A-Fa-f]{2}):([0-9A-Fa-f]{4})', value or '')
    require(m is not None and int(m[2], 16) >= 0x8000, f'{name} {value!r}: BB:AAAA(AAAA 8000~FFFF)')
    return int(m[1], 16) << 16 | int(m[2], 16)


def changed_writes(expected, rom, note, gap=4):
    """{주소: 값} 가운데 롬과 다른 바이트를 묶은 쓰기. gap 바이트 안쪽으로 떨어진 것은 한 쓰기로 묶고 뱅크와
    원래 롬 끝(파일 180000)에서 끊는다. 늘린 자리는 입력 롬에 없으므로 orig 없이 쓴다."""
    def old(pos):
        off = lorom(pos)
        return rom.d[off] if off < len(rom.d) else None

    def original(pos):
        return lorom(pos) < 0x180000

    changed = sorted(pos for pos, value in expected.items() if old(pos) != value)
    writes, i = [], 0
    while i < len(changed):
        start = end = changed[i]
        while i < len(changed) and changed[i] - end <= gap and changed[i] >> 16 == start >> 16 \
                and original(changed[i]) == original(start) \
                and all(p in expected or old(p) is not None for p in range(end, changed[i])):
            end = changed[i] + 1
            i += 1
        data = bytes(expected[p] if p in expected else old(p) for p in range(start, end))
        write = {'at': cpu(start), 'hex': data.hex(' '), 'note': note}
        if original(start):
            write['orig'] = bytes(old(p) for p in range(start, end)).hex(' ')
        writes.append(write)
    return writes


def target_ok(rom, start, size, name, here=None):
    """옮길 자리는 늘린 뱅크(파일 180000~)이거나 원래 롬의 빈 자리 지도 안이어야 한다.
    here(시작, 길이)는 같은 표가 이미 차지한 자리라 그 안에서 다시 쓰는 것은 받는다."""
    from dq5build import free_ranges
    off = lorom(start)
    require((start & 0xFFFF) + size <= 0x10000, f'{name} {cpu(start)}: {size}바이트가 뱅크를 넘음')
    spans = list(free_ranges(rom.d))
    if here is not None:
        spans.append((lorom(here[0]), here[1]))
    require(off >= 0x180000 or any(s <= off and off + size <= s + n for s, n in spans),
            f'{name} {cpu(start)}~: 늘린 뱅크나 빈 자리 지도 안이 아님')


def place_learn(rom, cfg, original, tables, learn_at, stub_at):
    """(사람 표 시작, 뱅크). 사람 표(끝 바이트 포함) 바로 뒤에 몬스터 표를 둔다.
    --learn-at 이 있으면 늘 그곳에, 없으면 사람 표 길이가 같고 몬스터 표가 짧거나 같을 때 제자리, 아니면 23:B819~BD52 에 다시 채운다."""
    size = {kind: sum(len(raw) for raw in rows) for kind, rows in tables.items()}
    old = {kind: sum(len(parts['learn'][1]) for (k, _), parts in original.items() if k == kind) for kind in GROUPS}
    old['person'] += 1
    total = size['person'] + size['monster']
    if learn_at is None:
        if size['person'] == old['person'] and size['monster'] <= old['monster']:
            return cfg['bases']['person'], cfg['bank']
        home = cfg['bank'] == 0x23 and cfg['bases'] == {k: GROUPS[k][1] for k in GROUPS}
        require(home and LEARN_REGION[0] + total <= LEARN_REGION[1],
                f'습득 표 {total}바이트가 원래 자리(23:B819~BD52)를 넘음. --learn-at 이 필요함')
        return LEARN_REGION[0], 0x23
    bank = learn_at >> 16
    # 23:ECDA·23:ED05 가 $09A5·$09A6 을 데이터 뱅크로 읽으므로 WRAM 거울이 있는 뱅크(30~3F)여야 한다.
    require(bank == 0x23 or 0x30 <= bank <= 0x3F, '--learn-at: 뱅크 23 이나 30~3F 만 받음(WRAM 거울)')
    require(bank != 0x23 or stub_at is None, '--learn-at 이 뱅크 23 이면 --stub-at 이 필요 없음')
    require(bank == 0x23 or stub_at is not None or bank == cfg['bank'],
            '--learn-at 이 뱅크 23 밖이면 --stub-at(뱅크 23)이 필요함')
    if LEARN_REGION[0] <= learn_at < LEARN_REGION[1]:
        here = (LEARN_REGION[0], LEARN_REGION[1] - LEARN_REGION[0])
    else:
        here = (learn_at, old['person'] + old['monster']) if learn_at == cfg['bases']['person'] else None
    target_ok(rom, learn_at, total, '--learn-at', here)
    return learn_at, bank


def place_lists(rom, cfg, original, blobs, lists_at):
    """같은 바이트의 목록은 한 번만 두고 차례로 채운다. ({blob: 주소}, 뱅크)."""
    unique = list(dict.fromkeys(blobs))
    total = sum(len(b) for b in unique)
    spans = [parts[name] for parts in original.values() for name in TABLES]
    low = min(a for a, _ in spans)
    used = max(a + len(raw) for a, raw in spans) - low
    if lists_at is None:
        require(cfg['banks'] == {'field': 0x23, 'battle': 0x23} and LIST_REGION[0] + total <= LIST_REGION[1],
                f'주문 목록 {total}바이트가 원래 자리(23:BE27~C013)를 넘음. --lists-at 이 필요함')
        start = LIST_REGION[0]
    else:
        start = lists_at
        # 롱 포인터라 다른 뱅크도 읽을 수 있지만(코드 읽기) 게임에서 본 것은 뱅크 3F 뿐이라 2MB 안(30~3F)만 받는다.
        require(lists_at >> 16 == 0x23 or 0x30 <= lists_at >> 16 <= 0x3F, '--lists-at: 뱅크 23 이나 30~3F')
        here = (low, used) if lists_at == low else None
        if LIST_REGION[0] <= lists_at < LIST_REGION[1]:
            here = (LIST_REGION[0], LIST_REGION[1] - LIST_REGION[0])
        target_ok(rom, lists_at, total, '--lists-at', here)
    where, a = {}, start
    for blob in unique:
        where[blob] = a
        a += len(blob)
    return where, start >> 16


def patch(rom, doc, learn_at=None, stub_at=None, lists_at=None, spell_rom=None):
    keys(doc, ('format', 'characters', 'join'), '문서')
    require(doc.get('format') == FORMAT and isinstance(doc.get('characters'), list), 'format/characters가 잘못됨')
    require(isinstance(doc.get('join', []), list), 'join 은 배열이어야 함')
    cfg = config(rom)
    original = layout(rom, cfg)
    # 행동 번호를 늘리는 패치(dq5spellgrow.py)와 함께 빌드할 때는 그 패치를 넣어 만든 롬에서 범위를 읽는다.
    allowed = spells(spell_rom or rom)
    changes = {}
    for row in doc['characters']:
        keys(row, ('kind', 'index', 'learn', 'field', 'battle'), '인물')
        kind = row.get('kind')
        require(isinstance(kind, str) and kind in GROUPS, 'kind는 person/monster여야 함')
        index = integer(row.get('index'), 0, GROUPS[kind][0] - 1, 'index')
        key = kind, index
        require(key not in changes, '중복 인물')
        floor = read(rom, COMPANIONS + index * 9, 1)[0] if kind == 'monster' else 2
        caps = CAPS if kind == 'person' else {**CAPS, 'battle': MONSTER_BATTLE}
        changes[key] = encode(decode(original[key]), row, floor, caps, allowed)
    new = {key: {name: changes.get(key, {}).get(name, raw) for name, (_, raw) in parts.items()}
           for key, parts in original.items()}
    expected = {}

    def put(address, data, what):
        for i, value in enumerate(data):
            pos = address + i
            require(pos not in expected or expected[pos] == value, f'{cpu(pos)}: {what} 쓰기가 다른 쓰기와 겹침')
            expected[pos] = value

    tables = {kind: [new[kind, i]['learn'] for i in range(GROUPS[kind][0])] for kind in GROUPS}
    tables['person'].append(person_tail(rom, cfg))
    person, bank = place_learn(rom, cfg, original, tables, learn_at, stub_at)
    monster = person + sum(len(raw) for raw in tables['person'])
    for kind, base in (('person', person), ('monster', monster)):
        put(base, b''.join(tables[kind]), '습득 표')
        if base & 0xFFFF != cfg['bases'][kind] & 0xFFFF:
            put(BASE_AT[kind], (base & 0xFFFF).to_bytes(2, 'little'), '습득 표 시작')
    if bank == 0x23:
        if cfg['bank'] != 0x23:
            put(LDY_AT, LDY, '습득 표 뱅크')
    else:
        at = stub_at if stub_at is not None else cfg['stub']
        if at != cfg['stub'] or bank != cfg['bank']:
            require(at >> 16 == 0x23, '--stub-at 은 뱅크 23 이어야 함(23:ECD7 의 JSR)')
            target_ok(rom, at, 8, '--stub-at', (at, 8) if at == cfg['stub'] else None)
            put(at, stub(bank), '데이터 뱅크 루틴')
            put(LDY_AT, bytes([0x20]) + (at & 0xFFFF).to_bytes(2, 'little'), '습득 표 뱅크')

    if lists_at is None and all(len(new[key][name]) == len(original[key][name][1]) for key in original for name in TABLES):
        # 길이가 같으면 제자리에 쓴다. 다른 목록과 바이트를 나눠 쓰는 곳(23:BE63)이 있어 모든 목록의 바이트를 함께 맞춘다.
        users = {}
        for key, parts in original.items():
            for name in TABLES:
                address, raw = parts[name]
                users.setdefault((address, len(raw)), []).append((key, name))
        for key, parts in original.items():
            for name in TABLES:
                address, old = parts[name]
                raw = new[key][name]
                if raw != old:
                    for user, part in users[address, len(old)]:
                        require(user in changes and changes[user][part] == raw,
                                f'공유 목록 {address:06X}: 모든 사용자에 같은 값을 지정해야 함')
                for i, value in enumerate(raw):
                    pos = address + i
                    require(pos not in expected or expected[pos] == value,
                            f'공유 바이트 {pos:06X}: 다른 목록의 값/개수와 충돌함')
                    expected[pos] = value
    else:
        order = [(key, name) for name in TABLES for key in original]
        where, list_bank = place_lists(rom, cfg, original, [new[k][n] for k, n in order], lists_at)
        for blob, address in where.items():
            put(address, blob, '주문 목록')
        for key, name in order:
            offset = GROUPS[key[0]][3] + key[1]
            put(TABLES[name] + offset * 2, (where[new[key][name]] & 0xFFFF).to_bytes(2, 'little'), '목록 포인터')
        for name in TABLES:
            if cfg['banks'][name] != list_bank:
                put(BANK_AT[name], bytes([list_bank]), '목록 뱅크')
    # 일행에 들 때의 습득 비트. 적지 않은 칸도 늘이거나 줄인 목록 길이 안인지 본다.
    joins, seen = {row['entry']: row for row in join_rows(rom)}, set()
    for row in doc.get('join', []):
        keys(row, ('entry', 'owner', 'field_slots', 'battle_slots'), 'join 항목')
        require({'entry', 'field_slots', 'battle_slots'} <= set(row), 'join 항목의 필드가 빠짐')
        entry = integer(row['entry'], 0, JOIN_COUNT - 1, 'join entry')
        require(entry not in seen, f'join 칸 {entry} 를 두 번 적음')
        owner = join_owner(rom, entry)
        require(row.get('owner', owner_name(owner)) == owner_name(owner), f'join 칸 {entry} 는 {owner_name(owner)} 의 칸')
        seen.add(entry)
        joins[entry] = row
    for entry, row in joins.items():
        owner = join_owner(rom, entry)
        require(owner in new, f'join 칸 {entry}: 인물 {owner} 가 표에 없음')
        mask = 0
        for name, shift in (('field', 0), ('battle', 8)):
            slots = row[name + '_slots']
            require(isinstance(slots, list) and all(type(v) is int for v in slots) and len(set(slots)) == len(slots),
                    'join 슬롯은 중복 없는 정수 배열이어야 함')
            for slot in slots:
                integer(slot, 0, len(new[owner][name]) - 2, f'join 칸 {entry} {name} slot')
                mask |= 1 << (shift + slot)
        at = JOIN + entry * JOIN_SIZE + 0x23
        # 몬스터 칸(80·81)은 쓰이는 때를 확인하지 못했고, 몬스터 합류(21:81E5)는 +23~+25 를 습득 표 결과로 덮는다(코드 읽기).
        require(owner[0] == 'person' or mask == int.from_bytes(read(rom, at, 3), 'little') & 0xFFFFF,
                f'join 칸 {entry}: 동료 몬스터 칸은 바꾸지 않음(쓰임 미확인)')
        high = read(rom, at + 2, 1)[0] & 0xF0
        put(at, mask.to_bytes(3, 'little')[:2] + bytes([mask >> 16 | high]), '일행에 들 때 습득 비트')
    writes = changed_writes(expected, rom, '주문 습득·목록')
    result = {'format': 'dq5patch/1', 'name': 'learn', 'writes': writes}
    top = max((lorom(parse_at(w['at'], 'at')) + len(bytes.fromhex(w['hex'])) for w in writes), default=0)
    if top > 0x180000:
        result['rom_size'] = 2 if top <= 0x200000 else 3 if top <= 0x300000 else 4
    return result


def check(rom, doc=None, **options):
    from dq5build import build
    from dq5build import parse_at as build_at
    original = dump(rom)
    source = original if doc is None else doc
    result = patch(rom, source, **options)
    if doc is None:
        require(not result['writes'], '원본 왕복 쓰기가 0개가 아님')
    writes = [(build_at(w['at'])[0], bytes.fromhex(w['hex']), bytes.fromhex(w['orig']) if 'orig' in w else None,
               w['note']) for w in result['writes']]
    size = result.get('rom_size', 0)
    rebuilt, _ = build(rom.d, [('learn', size, writes)], size)
    after = Rom(rebuilt)
    want = {(row['kind'], row['index']): row for row in original['characters']}
    for row in source['characters']:
        key = row['kind'], row['index']
        want[key] = {**want[key], **{k: v for k, v in row.items() if k in ('learn', 'field', 'battle')}}
        want[key]['learn'] = [{**e, 'field_slots': sorted(e['field_slots']), 'battle_slots': sorted(e['battle_slots'])}
                               for e in want[key]['learn']]
    got = {(row['kind'], row['index']): row for row in dump(after)['characters']}
    require(got == want, '빌드한 롬을 다시 읽은 습득·목록이 입력과 다름')
    joins = {row['entry']: row for row in original['join']}
    joins.update({row['entry']: {**joins[row['entry']], 'field_slots': sorted(row['field_slots']),
                                 'battle_slots': sorted(row['battle_slots'])} for row in source.get('join', [])})
    require(dump(after)['join'] == [joins[k] for k in range(JOIN_COUNT)], '빌드한 롬의 일행에 들 때 습득 비트가 입력과 다름')
    require(not patch(after, source, **options)['writes'], '빌드한 롬에 같은 입력을 다시 패치하면 쓰기가 남음')
    cfg = config(after)
    print(f'인물 {len(source["characters"])}종, 쓰기 {len(writes)}개 {sum(len(w[1]) for w in writes)}바이트; '
          f'습득 표 {cpu(cfg["bases"]["person"])}·{cpu(cfg["bases"]["monster"])}, '
          f'목록 뱅크 {cfg["banks"]["field"]:02X}·{cfg["banks"]["battle"]:02X}; 다시 읽기·다시 패치 0개')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('command', choices=('dump', 'patch', 'check'))
    ap.add_argument('source', nargs='?', type=Path)
    ap.add_argument('-o', '--out', type=Path)
    ap.add_argument('--learn-at', help='습득 표를 옮길 곳(뱅크 23 또는 30~3F)')
    ap.add_argument('--stub-at', help='습득 표가 뱅크 23 밖일 때 데이터 뱅크 루틴 8바이트를 둘 곳(뱅크 23)')
    ap.add_argument('--lists-at', help='주문 목록을 옮길 곳(뱅크 23 또는 30~3F)')
    ap.add_argument('--spells-from', type=Path, help='dq5spellgrow.py 패치를 넣어 만든 롬. 더한 행동 번호(C6~)를 받음')
    args = ap.parse_args()
    try:
        rom = Rom(args.rom.read_bytes())
        options = {name: parse_at(getattr(args, name), '--' + name.replace('_', '-'))
                   for name in ('learn_at', 'stub_at', 'lists_at') if getattr(args, name)}
        if getattr(args, 'spells_from', None):
            options['spell_rom'] = Rom(args.spells_from.read_bytes())
        require(args.command != 'dump' or args.source is None, 'dump에는 입력 파일을 주지 않음')
        if args.command == 'dump':
            result = dump(rom)
        else:
            require(args.command != 'patch' or args.source is not None, 'patch에는 입력 파일이 필요함')
            doc = json.loads(args.source.read_text(encoding='utf-8')) if args.source else None
            if args.command == 'check':
                check(rom, doc, **options)
                return 0
            result = patch(rom, doc, **options)
        text = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(text, encoding='utf-8')
        else:
            print(text, end='')
        return 0
    except (OSError, ValueError) as error:
        print(f'오류: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
