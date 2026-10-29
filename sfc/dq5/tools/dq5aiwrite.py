"""DQ5 일행 작전 AI 의 행동·물건 AI 레코드, 작전 레코드, 학습 배율 표와 주문 내성 배율·갑옷 원소 표를 쓴다.

모두 고정 길이 표이고 항목 수는 바꾸지 않는다. 받는 필드는 원래 롬과 견주어 게임에서 효과를 확인한 것뿐이다.
행동 AI 표는 처음부터 행동 00~EF 240칸이고 물건 표가 바로 뒤에 붙는다(21:D19C 가 행동×5, 물건이면 +4B0). 그래서
dq5spellgrow.py 가 더한 새 번호 C6~D4 의 레코드도 제자리에 쓴다. 새 번호는 copy 로 원래 행동의 5바이트를 베낀 뒤 덮는다.
형식: sfc/dq5/docs/dq5-data-format.md 의 「작전 AI」·「주문과 행동」, sfc/dq5/docs/dq5-build-format.md 의 `dq5ai/1`.

  python sfc/dq5/tools/dq5aiwrite.py rom/dq5.sfc dump -o work/ai/dump.json
  python sfc/dq5/tools/dq5aiwrite.py rom/dq5.sfc patch work/ai/edit.json -o work/build/ai.dq5patch.json
  python sfc/dq5/tools/dq5aiwrite.py rom/dq5.sfc check [work/ai/edit.json]
"""
import argparse
import json
import re
import sys
from pathlib import Path

from dq5map import Rom, lorom
from dq5spellgrow import FIRST as NEW_FIRST, LAST as NEW_LAST, WIDE

FORMAT = 'dq5ai/1'
ACTIONS, ACTION_COUNT = 0x21BC86, 0xAB
ITEMS, ITEM_COUNT = 0x21C136, 0xD8
# 새 번호 C6~D4 의 원래 레코드는 모두 11 00 30 00 FF 라, 베끼지 않으면 작전 AI 가 고르지 않는다.
NEW_ACTIONS = range(NEW_FIRST, NEW_LAST + 1)
BATTLE_MP = 0x268765
TACTICS, TACTIC_COUNT, TACTIC_SIZE = 0x21D8BD, 5, 32
# 작전 레코드에서 받는 칸: (이름, 위치, 바이트 수). +3~+5·+A·+12 는 게임에서 확인하지 않아 내보내지 않는다.
TACTIC_FIELDS = (('per_mp', 0, 1), ('flat', 1, 1), ('mp_ratio', 2, 1), ('danger', 6, 1),
                 ('fubaha', 7, 1), ('baikiruto', 8, 1), ('sukuruto', 9, 1), ('mp_penalty', 0x10, 2))
# 27:8228 이 고르는 학습 배율 표 셋. [갈래 0~2][라운드 수 0~3][내성 단계 0~3].
ODDS = {'normal': 0x278254, 'easy': 0x278284, 'saving': 0x2782B4}
RESIST = 0x278055
ARMOR = 0x2780FC
NO_RESIST = 0x1F
KNOWN_RANGES = {0x00, 0x20, 0x40, 0x60, 0x80}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def keys(value, allowed, name):
    require(isinstance(value, dict), f'{name}: 객체가 필요함')
    extra = value.keys() - set(allowed)
    require(not extra, f'{name}: 지원하지 않는 필드 {sorted(extra)}')


def integer(value, low, high, name):
    require(type(value) is int and low <= value <= high, f'{name}: {low}~{high} 정수여야 함')
    return value


def hexbyte(value, name):
    require(isinstance(value, str) and re.fullmatch(r'[0-9A-Fa-f]{2}', value) is not None, f'{name}: 16진 두 자리')
    return int(value, 16)


def u8(rom, addr):
    off = lorom(addr)
    require(off < len(rom.d), f'{addr:06X}: 롬 범위 밖')
    return rom.d[off]


def record(rom, base, n):
    return [u8(rom, base + n * 5 + i) for i in range(5)]


def armor_entries(rom):
    rows, addr = [], ARMOR
    while u8(rom, addr) != 0:
        rows.append((addr, [u8(rom, addr + i) for i in range(3)]))
        addr += 3
        require(len(rows) < 64, '갑옷 원소 표 끝 00 을 찾지 못함')
    return rows


def branches(rom):
    """원래 행동·물건 레코드에 나오는 평가 갈래(+2) 값을 따로. 21:DAEE·21:ED7E·21:F5C8 의 처리기가 이 값으로 갈린다."""
    return ({record(rom, ACTIONS, n)[2] for n in range(ACTION_COUNT)},
            {record(rom, ITEMS, n)[2] for n in range(ITEM_COUNT)})


def decode_action(rom, n, rec):
    mp = u8(rom, BATTLE_MP + n) & 0x1F
    row = {'action': f'{n:02X}', 'kind': f'{rec[0]:02X}', 'value': rec[1], 'branch': f'{rec[2]:02X}', 'mp': rec[3],
           'range': f'{rec[4] & 0xE0:02X}',
           'resist': None if rec[4] & 0x1F == NO_RESIST else f'{(rec[4] & 0x1F) + 0x50:02X}'}
    # 26:8765 의 1F 는 MP 를 쓰지 않음, 1E 는 36, 1D 는 남은 MP 전부.
    row['battle_mp'] = {0x1F: None, 0x1E: 36, 0x1D: 'all'}.get(mp, mp)
    return row


def dump(rom):
    out = {'format': FORMAT,
           'actions': [decode_action(rom, n, record(rom, ACTIONS, n)) for n in (*range(ACTION_COUNT), *NEW_ACTIONS)],
           'items': [{'item': f'{n:02X}', 'value': rec[1], 'branch': f'{rec[2]:02X}'}
                     for n, rec in ((n, record(rom, ITEMS, n)) for n in range(ITEM_COUNT))],
           'tactics': [], 'odds': {}, 'resist_rates': [u8(rom, RESIST + i) for i in range(4)],
           'armor': []}
    for t in range(TACTIC_COUNT):
        base = TACTICS + t * TACTIC_SIZE
        row = {'tactic': t}
        for name, at, size in TACTIC_FIELDS:
            row[name] = sum(u8(rom, base + at + i) << (8 * i) for i in range(size))
        out['tactics'].append(row)
    for name, base in ODDS.items():
        out['odds'][name] = [[[u8(rom, base + g * 16 + r * 4 + s) for s in range(4)] for r in range(4)] for g in range(3)]
    for i, (_, (element, item, value)) in enumerate(armor_entries(rom)):
        out['armor'].append({'index': i, 'element': f'{element:02X}', 'item': f'{item:02X}',
                             'reduce': value - 256 if value & 0x80 else value})
    return out


def edits(rom, doc, original=None):
    keys(doc, ('format', 'actions', 'items', 'tactics', 'odds', 'resist_rates', 'armor'), '문서')
    require(doc.get('format') == FORMAT, 'format 이 잘못됨')
    allowed = branches(original or rom)
    wanted, notes = {}, {}

    def put(addr, value, note):
        require(wanted.get(addr, value) == value, f'{addr:06X}: 두 입력이 다른 값을 씀')
        wanted[addr], notes[addr] = value, note

    def rows(section, key, count, extra=()):
        value = doc.get(section, [])
        require(isinstance(value, list), f'{section}: 배열이어야 함')
        seen = set()
        for row in value:
            require(isinstance(row, dict), f'{section}: 항목은 객체여야 함')
            raw = row.get(key)
            if key == 'tactic':
                n = integer(raw, 0, count - 1, key)
            else:
                n = hexbyte(raw, f'{section} {key}')
                require(n < count or n in extra, f'{section}: {raw} 는 {count} 개 밖'
                        + (f'(새 번호는 {extra[0]:02X}~{extra[-1]:02X})' if extra else ''))
            require(n not in seen, f'{section}: {raw} 를 두 번 지정함')
            seen.add(n)
            yield n, row

    def branch(row, name, pool, current):
        value = hexbyte(row['branch'], f'{name} branch')
        require(value in pool or value == current, f'{name}: 원래 표의 같은 종류 레코드에 없는 평가 갈래 {value:02X}')
        return value

    for n, row in rows('actions', 'action', ACTION_COUNT, NEW_ACTIONS):
        name = f'actions {n:02X}'
        keys(row, ('action', 'copy', 'kind', 'value', 'branch', 'mp', 'range', 'resist', 'battle_mp'), name)
        base = ACTIONS + n * 5
        rec = record(rom, ACTIONS, n)
        if 'copy' in row:
            require(n in NEW_ACTIONS, f'{name}: copy 는 새 번호({NEW_FIRST:02X}~{NEW_LAST:02X})만 받음')
            src = hexbyte(row['copy'], f'{name} copy')
            require(src < ACTION_COUNT, f'{name} copy: 원래 행동 00~{ACTION_COUNT - 1:02X} 여야 함')
            rec = record(original or rom, ACTIONS, src)
        old = decode_action(rom, n, rec)
        if 'kind' in row:
            require(hexbyte(row['kind'], f'{name} kind') == int(old['kind'], 16), f'{name}: kind 는 읽기 전용')
        require(row.get('battle_mp', old['battle_mp']) == old['battle_mp'], f'{name}: battle_mp 는 읽기 전용')
        if 'value' in row:
            put(base + 1, integer(row['value'], 0, 255, f'{name} value'), f'행동 {n:02X} AI 기대 값')
        if 'branch' in row:
            put(base + 2, branch(row, name, allowed[0], rec[2]), f'행동 {n:02X} AI 평가 갈래')
        if 'mp' in row:
            put(base + 3, integer(row['mp'], 0, 255, f'{name} mp'), f'행동 {n:02X} AI MP')
        if 'range' in row or 'resist' in row:
            rng = rec[4] & 0xE0
            if 'range' in row:
                value = hexbyte(row['range'], f'{name} range')
                # 뜻을 확인한 다섯 값으로만 바꾼다. A0·C0·E0 은 원래 값 그대로 둘 때만 받는다.
                require(value in KNOWN_RANGES or value == rng, f'{name} range: 00·20·40·60·80 중 하나(또는 원래 값)')
                rng = value
            resist = rec[4] & 0x1F
            if 'resist' in row:
                if row['resist'] is None:
                    resist = NO_RESIST
                else:
                    kind = hexbyte(row['resist'], f'{name} resist')
                    require(0x50 <= kind <= 0x61 and kind != 0x5F, f'{name} resist: 50~61(5F 제외) 또는 null')
                    resist = kind - 0x50
            put(base + 4, rng | resist, f'행동 {n:02X} AI 범위·내성')
        if 'copy' in row:
            # 덮지 않은 칸은 베낀 레코드 값으로.
            for i, v in enumerate(rec):
                if base + i not in wanted:
                    put(base + i, v, f'행동 {n:02X} AI 레코드({src:02X} 베낌)')

    for n, row in rows('items', 'item', ITEM_COUNT):
        name = f'items {n:02X}'
        keys(row, ('item', 'value', 'branch'), name)
        base = ITEMS + n * 5
        if 'value' in row:
            put(base + 1, integer(row['value'], 0, 255, f'{name} value'), f'물건 {n:02X} AI 기대 값')
        if 'branch' in row:
            put(base + 2, branch(row, name, allowed[1], record(rom, ITEMS, n)[2]), f'물건 {n:02X} AI 평가 갈래')

    for t, row in rows('tactics', 'tactic', TACTIC_COUNT):
        keys(row, ('tactic', *(f[0] for f in TACTIC_FIELDS)), f'tactics {t}')
        base = TACTICS + t * TACTIC_SIZE
        for field, at, size in TACTIC_FIELDS:
            if field in row:
                value = integer(row[field], 0, (1 << (8 * size)) - 1, f'tactics {t} {field}')
                for i in range(size):
                    put(base + at + i, value >> (8 * i) & 0xFF, f'작전 {t} {field}')

    odds = doc.get('odds', {})
    keys(odds, tuple(ODDS), 'odds')
    for table, value in odds.items():
        require(isinstance(value, list) and len(value) == 3 and all(
            isinstance(r, list) and len(r) == 4 and all(isinstance(s, list) and len(s) == 4 for s in r) for r in value),
                f'odds {table}: [갈래 3][라운드 4][단계 4] 배열이어야 함')
        for g in range(3):
            for r in range(4):
                for s in range(4):
                    put(ODDS[table] + g * 16 + r * 4 + s, integer(value[g][r][s], 0, 255, f'odds {table}'),
                        f'학습 배율 {table}')

    if 'resist_rates' in doc:
        rates = doc['resist_rates']
        require(isinstance(rates, list) and len(rates) == 4, 'resist_rates: 4개 배열이어야 함')
        for i, v in enumerate(rates):
            put(RESIST + i, integer(v, 0, 255, 'resist_rates'), '내성 단계 배율')

    entries = armor_entries(rom)
    value = doc.get('armor', [])
    require(isinstance(value, list), 'armor: 배열이어야 함')
    seen = set()
    for row in value:
        keys(row, ('index', 'element', 'item', 'reduce'), 'armor')
        old = entries[integer(row.get('index'), 0, len(entries) - 1, 'armor index')][1]
        i = integer(row.get('index'), 0, len(entries) - 1, 'armor index')
        require(i not in seen, f'armor: {i} 를 두 번 지정함')
        seen.add(i)
        addr = entries[i][0]
        # 원소·물건 칸은 바꾼 실측이 없어 읽기 전용이다.
        for at, field in ((0, 'element'), (1, 'item')):
            if field in row:
                require(hexbyte(row[field], f'armor {field}') == old[at], f'armor {i}: {field} 는 읽기 전용')
        if 'reduce' in row:
            reduce = integer(row['reduce'], -128, 127, 'armor reduce')
            put(addr + 2, reduce & 0xFF, f'갑옷 원소 {i}')
    return wanted, notes


def copy_warnings(spells, doc):
    """새 번호의 copy 가 dq5spellgrow.py 가 베낀 행동과 다른지. spells 는 그 패치를 넣은 롬.
    실행 루틴·둘째 실행 표·처리 루틴(26:8865·26:8565·20:B7F9)이 copy 원본과 다르면 경고 문장을 돌려준다(쓰기는 막지 않음).
    세 칸이 같은 다른 행동을 베꼈으면 알아차리지 못한다."""
    out = []
    for row in doc.get('actions', []):
        if not isinstance(row, dict) or 'copy' not in row:
            continue
        n, src = int(row['action'], 16), int(row['copy'], 16)
        if n not in NEW_ACTIONS:
            continue
        for name in ('handler', 'executor', 'executor_alt'):
            base, size, empty = WIDE[name]
            got = [int.from_bytes(spells.d[lorom(base + k * size):lorom(base + k * size) + size], 'little') for k in (n, src)]
            # 둘째 실행 표는 원래 행동에도 빈 값이 흔해, 비었는지는 처리 루틴으로만 본다.
            if name == 'handler' and got[0] == empty:
                out.append(f'actions {n:02X}: dq5spellgrow.py 롬에서 {name} 칸이 비어 있음(그 번호를 더하지 않음)')
                break
            if got[0] != got[1]:
                out.append(f'actions {n:02X}: AI copy {src:02X} 와 dq5spellgrow.py 가 베낀 행동의 {name} 칸이 다름 '
                           f'({got[1]:04X} / {got[0]:04X})')
                break
    return out


def patch(rom, doc, original=None):
    wanted, notes = edits(rom, doc, original)
    changed = sorted(a for a, v in wanted.items() if u8(rom, a) != v)
    writes, i = [], 0
    while i < len(changed):
        j = i
        while j + 1 < len(changed) and changed[j + 1] == changed[j] + 1 and notes[changed[j + 1]] == notes[changed[i]]:
            j += 1
        start, size = changed[i], j - i + 1
        writes.append({'at': f'{start >> 16:02X}:{start & 0xFFFF:04X}',
                       'hex': bytes(wanted[start + k] for k in range(size)).hex(' '),
                       'orig': bytes(u8(rom, start + k) for k in range(size)).hex(' '), 'note': notes[start]})
        i = j + 1
    return {'format': 'dq5patch/1', 'name': 'ai', 'writes': writes}


def check(rom, doc=None):
    from dq5build import build, parse_at
    original = dump(rom)
    source = original if doc is None else doc
    writes = patch(rom, source)['writes']
    require(doc is not None or not writes, '원본 왕복 쓰기가 0개가 아님')
    rebuilt, _ = build(rom.d, [('ai', 0, [
        (parse_at(w['at'])[0], bytes.fromhex(w['hex']), bytes.fromhex(w['orig']), w['note']) for w in writes])], 0)
    after = Rom(rebuilt)
    require(not patch(after, source, rom)['writes'], '빌더 적용 후 같은 입력을 다시 패치하면 쓰기가 남음')
    require(not patch(after, dump(after), rom)['writes'], '빌드한 롬을 다시 읽고 인코딩한 결과가 다름')
    print(f'행동 {len(original["actions"])}개·물건 {len(original["items"])}개·작전 {len(original["tactics"])}개·'
          f'학습 표 {len(original["odds"])}개·갑옷 원소 {len(original["armor"])}개; 쓰기 {len(writes)}개 검사 통과')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('rom', type=Path)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('dump').add_argument('-o', '--out', type=Path)
    write = sub.add_parser('patch')
    write.add_argument('source', type=Path)
    write.add_argument('-o', '--out', type=Path)
    verify = sub.add_parser('check')
    verify.add_argument('source', type=Path, nargs='?')
    for p in (write, verify):
        p.add_argument('--spells-from', type=Path, help='dq5spellgrow.py 패치를 넣은 롬. 새 번호의 copy 가 그쪽과 다르면 경고')
    args = parser.parse_args()
    try:
        rom = Rom(args.rom.read_bytes())
        doc = json.loads(args.source.read_text(encoding='utf-8')) if getattr(args, 'source', None) else None
        if doc is not None and getattr(args, 'spells_from', None):
            for warning in copy_warnings(Rom(args.spells_from.read_bytes()), doc):
                print(f'경고: {warning}', file=sys.stderr)
        if args.command == 'check':
            check(rom, doc)
            return 0
        out = dump(rom) if args.command == 'dump' else patch(rom, doc)
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
