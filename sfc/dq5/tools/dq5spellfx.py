"""DQ5 전투 행동의 처리 루틴 연결·처리 루틴 첫머리 값과 필드 주문의 처리기·MP·회복량을 쓴다.

전투: 20:B7F9[행동*2] 의 처리 루틴과, 처리 루틴 첫머리 `SEP #$30 / LDX #내성 / LDA #값 / JMP 공통 루틴` 의 두 즉값
(JMP 없이 바로 공통 루틴으로 이어지는 첫머리도).
필드: 11:8024[주문-27] 의 처리기와, 처리기 안 MP 검사·빼기(11:87DF·87F4, 11:8048)와 ホイミ·ベホイミ 회복량의 즉값.
기존 코드 길이 안에서 즉값과 표만 바꾼다. 형식: sfc/dq5/docs/dq5-build-format.md 의 `dq5spellfx/1`.

  python sfc/dq5/tools/dq5spellfx.py rom/dq5.sfc dump -o work/spellfx/dump.json
  python sfc/dq5/tools/dq5spellfx.py rom/dq5.sfc patch work/spellfx/edit.json -o work/build/spellfx.dq5patch.json
  python sfc/dq5/tools/dq5spellfx.py rom/dq5.sfc check [work/spellfx/edit.json]
"""
import argparse
import json
import re
import sys
from pathlib import Path

from dq5map import Rom, lorom

FORMAT = 'dq5spellfx/1'
ACTIONS = 0xAB
HANDLERS = 0x20B7F9
EXECUTORS = 0x268865
# 공통 루틴과 첫머리 LDA # 의 뜻. B307 은 주문 피해, B657 은 숨 피해, AB70 은 회복·양 번호,
# AE41·AEC6·AEFF 는 상태 주문(우리 쪽에게는 난수 0~7 < 값). B301·B651 은 JMP 없이 B307·B657 로 이어진다.
AMOUNT = {0xB307: 'damage', 0xB657: 'damage', 0xAB70: 'amount'}
CHANCE = {0xAE41: 'status', 0xAEC6: 'status', 0xAEFF: 'status'}
# 내성 칸(LDX #)을 공통 루틴이 그대로 쓰는 것. AB70 은 X 를 받지 않는다.
RESIST_USERS = {0xB307, 0xB657, 0xAE41, 0xAEC6, 0xAEFF}
RESISTS = set(range(0x50, 0x62)) - {0x5F}
FIELD_TABLE = 0x118024
FIELD_FIRST = 0x27
FIELD_COUNT = 18
FIELD_NONE = 0x8022
# 필드 처리기마다 그 처리기가 쓰는 MP 즉값의 피연산자 주소 전부(코드 읽기). 11:87DF(검사)·11:87F4(빼기) 앞의 것과,
# 둘을 잇달아 부르는 11:8048 앞의 것. 뱅크 11 에서 이 셋을 부르는 LDA # 은 아래 26곳뿐이다.
FIELD_MP = {0x84FA: (0x1184FB, 0x11851A), 0x85A5: (0x1185A6, 0x1185C5), 0x85DC: (0x1185DD, 0x1185FB),
            0x865D: (0x11865E, 0x118675), 0x86C7: (0x1186C8, 0x1186D9), 0x860C: (0x11860D, 0x118624),
            0x8636: (0x118637, 0x11864E), 0x8056: (0x118064, 0x118089), 0x82B6: (0x1182B9,),
            0x8797: (0x118798, 0x1187B2), 0x82E8: (0x1182F9, 0x118386), 0x877D: (0x11877E, 0x118792),
            0x826F: (0x118272,), 0x8729: (0x11872A, 0x118741)}
# ホイミ·ベホイミ: (まんたん 값 LDA #, 난수 폭 LDA # → 00:953A, 바탕 ADC #) 의 피연산자. 회복량 = 바탕 + 난수(0~폭-1).
FIELD_HEAL = {0x84FA: (0x11851F, 0x118526, 0x11852D), 0x85A5: (0x1185CA, 0x1185D1, 0x1185D8)}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def keys(value, allowed, name):
    require(isinstance(value, dict), f'{name}: 객체가 필요함')
    extra = value.keys() - set(allowed)
    require(not extra, f'{name}: 지원하지 않는 필드 {sorted(extra)}')


def hexval(value, name, digits, low=0, high=None):
    require(isinstance(value, str) and re.fullmatch(f'[0-9A-Fa-f]{{{digits}}}', value) is not None,
            f'{name}: 16진 {digits}자리 문자열이어야 함')
    result = int(value, 16)
    require(low <= result and (high is None or result <= high), f'{name}: 범위 밖 {value}')
    return result


def integer(value, low, high, name):
    require(type(value) is int and low <= value <= high, f'{name}: {low}~{high} 정수여야 함')
    return value


def u8(rom, addr):
    off = lorom(addr)
    require(off < len(rom.d), f'{addr:06X}: 롬 범위 밖')
    return rom.d[off]


def u16(rom, addr):
    return u8(rom, addr) | u8(rom, addr + 1) << 8


def stub(rom, handler):
    """처리 루틴 첫머리. E2 30 뒤 LDX #·LDA # (순서 무관, 각 한 번), 그 뒤 JMP·JSR 공통 루틴이거나 바로 공통 루틴.
    맞으면 {'target', 'lda', 'ldx'}(값은 피연산자 주소), 아니면 None."""
    a = 0x200000 | handler
    if (u8(rom, a), u8(rom, a + 1)) != (0xE2, 0x30):
        return None
    p, found = a + 2, {}
    for _ in range(2):
        op = u8(rom, p)
        name = {0xA9: 'lda', 0xA2: 'ldx'}.get(op)
        if name is None or name in found:
            break
        found[name] = p + 1
        p += 2
    if 'lda' not in found:
        return None
    if p & 0xFFFF in AMOUNT or p & 0xFFFF in CHANCE:
        target = p & 0xFFFF
    elif u8(rom, p) in (0x4C, 0x20):
        target = u16(rom, p + 1)
    else:
        return None
    if target not in AMOUNT and target not in CHANCE:
        return None
    return {'target': target, 'lda': found['lda'], 'ldx': found.get('ldx')}


def battle_layout(rom):
    slots = [u16(rom, HANDLERS + n * 2) for n in range(ACTIONS)]
    executors = [u16(rom, EXECUTORS + n * 2) for n in range(ACTIONS)]
    stubs = {h: s for h in sorted(set(slots)) if (s := stub(rom, h)) is not None}
    return slots, executors, stubs


def field_layout(rom):
    slots = [u16(rom, FIELD_TABLE + i * 2) for i in range(FIELD_COUNT)]
    for handler, sites in FIELD_MP.items():
        values = {u8(rom, s) for s in sites}
        for s in sites:
            require(u8(rom, s - 1) == 0xA9, f'{s:06X}: 필드 MP 즉값 자리가 원본과 다름')
        require(len(values) == 1, f'11:{handler:04X}: MP 검사와 빼기 값이 다름')
    for handler, (top, spread, base) in FIELD_HEAL.items():
        require((u8(rom, top - 1), u8(rom, spread - 1), u8(rom, base - 1)) == (0xA9, 0xA9, 0x69),
                f'11:{handler:04X}: 회복량 즉값 자리가 원본과 다름')
        # まんたん 값은 바탕 + 폭 - 1 로 맞춰 쓰므로 dump 에 따로 내지 않는다. 다른 값이면 왕복이 깨진다.
        require(u8(rom, top) == u8(rom, base) + u8(rom, spread) - 1, f'11:{handler:04X}: まんたん 값이 바탕 + 폭 - 1 이 아님')
    return slots


class Layout:
    def __init__(self, rom, original=None):
        self.slots, self.executors, self.stubs = battle_layout(rom)
        self.field = field_layout(rom)
        base = original or self
        self.handlers = set(base.slots)
        self.pairs = set(zip(base.executors, base.slots))
        self.field_handlers = set(base.field) - {FIELD_NONE}


def users(slots, handler):
    return [f'{n:02X}' for n, h in enumerate(slots) if h == handler]


def dump(rom):
    lay = Layout(rom)
    battle = [{'action': f'{n:02X}', 'handler': f'{h:04X}', 'executor': f'{lay.executors[n]:04X}'}
              for n, h in enumerate(lay.slots)]
    stubs = []
    for h, s in lay.stubs.items():
        row = {'handler': f'{h:04X}', 'routine': f'{s["target"]:04X}', 'users': users(lay.slots, h)}
        row['amount' if s['target'] in AMOUNT else 'chance'] = (f'{u8(rom, s["lda"]):02X}' if s['target'] in AMOUNT
                                                                else u8(rom, s['lda']))
        if s['ldx'] is not None and s['target'] in RESIST_USERS:
            row['resist'] = f'{u8(rom, s["ldx"]):02X}'
        stubs.append(row)
    field = [{'spell': f'{FIELD_FIRST + i:02X}', 'handler': f'{h:04X}'} for i, h in enumerate(lay.field)]
    handlers = []
    for h, sites in FIELD_MP.items():
        row = {'handler': f'{h:04X}', 'spells': [f'{FIELD_FIRST + i:02X}' for i, s in enumerate(lay.field) if s == h],
               'mp': u8(rom, sites[0])}
        if h in FIELD_HEAL:
            _, spread, base = FIELD_HEAL[h]
            row['heal'] = {'base': u8(rom, base), 'spread': u8(rom, spread)}
        handlers.append(row)
    return {'format': FORMAT, 'battle_slots': battle, 'battle_handlers': stubs,
            'field_slots': field, 'field_handlers': handlers}


def edits(rom, doc, original=None, raw=False):
    """{주소: 바이트} 와 그 자리의 설명. 허용 집합(처리 루틴·짝·필드 처리기)은 original(없으면 입력 롬)에서 모으므로
    입력에는 원래 롬을 준다."""
    keys(doc, ('format', 'battle_slots', 'battle_handlers', 'field_slots', 'field_handlers'), '문서')
    require(doc.get('format') == FORMAT, 'format 이 잘못됨')
    lay = Layout(rom, original)
    wanted, notes = {}, {}

    def put(addr, raw_bytes, note):
        for k, v in enumerate(raw_bytes):
            require(wanted.get(addr + k, v) == v, f'{addr + k:06X}: 두 입력이 다른 값을 씀')
            wanted[addr + k], notes[addr + k] = v, note

    def rows(section, key, convert):
        value = doc.get(section, [])
        require(isinstance(value, list), f'{section}: 배열이어야 함')
        seen = set()
        for row in value:
            index = convert(row.get(key) if isinstance(row, dict) else None)
            require(index not in seen, f'{section}: {row.get(key)} 를 두 번 지정함')
            seen.add(index)
            yield index, row

    for n, row in rows('battle_slots', 'action', lambda v: hexval(v, 'action', 2, 0, ACTIONS - 1)):
        keys(row, ('action', 'handler', 'executor'), f'battle_slots {n:02X}')
        if 'executor' in row:
            require(hexval(row['executor'], 'executor', 4) == lay.executors[n],
                    f'battle_slots {n:02X}: executor 는 읽기 전용(26:8865 는 dq5tables.py 의 대상루틴)')
        if 'handler' not in row:
            continue
        h = hexval(row['handler'], f'battle_slots {n:02X} handler', 4, 0x8000)
        if not raw:
            require(h in lay.handlers, f'battle_slots {n:02X}: 원래 표에 없는 처리 루틴 {h:04X}(--raw)')
            require((lay.executors[n], h) in lay.pairs,
                    f'battle_slots {n:02X}: 실행 루틴 {lay.executors[n]:04X} 과 처리 루틴 {h:04X} 은 원래 짝이 아님(--raw)')
        put(HANDLERS + n * 2, h.to_bytes(2, 'little'), f'행동 {n:02X} 처리 루틴')

    for h, row in rows('battle_handlers', 'handler', lambda v: hexval(v, 'handler', 4)):
        keys(row, ('handler', 'routine', 'users', 'amount', 'chance', 'resist'), f'battle_handlers {h:04X}')
        s = lay.stubs.get(h)
        require(s is not None, f'battle_handlers {h:04X}: 첫머리를 고칠 수 있는 처리 루틴이 아님')
        if 'routine' in row:
            require(hexval(row['routine'], 'routine', 4) == s['target'], f'battle_handlers {h:04X}: routine 은 읽기 전용')
        if 'users' in row:
            require(row['users'] == users(lay.slots, h), f'battle_handlers {h:04X}: users 는 읽기 전용')
        if 'amount' in row:
            require(s['target'] in AMOUNT, f'battle_handlers {h:04X}: 양 번호를 받는 루틴이 아님')
            put(s['lda'], [hexval(row['amount'], 'amount', 2, 0, 0x3F)], f'처리 루틴 {h:04X} 양 번호')
        if 'chance' in row:
            require(s['target'] in CHANCE, f'battle_handlers {h:04X}: 성공 값을 받는 루틴이 아님')
            put(s['lda'], [integer(row['chance'], 0, 8, 'chance')], f'처리 루틴 {h:04X} 성공 값')
        if 'resist' in row:
            require(s['ldx'] is not None and s['target'] in RESIST_USERS,
                    f'battle_handlers {h:04X}: 내성 칸을 받는 루틴이 아님')
            value = hexval(row['resist'], 'resist', 2)
            require(value in RESISTS, 'resist: 50~61(5F 제외)이어야 함')
            put(s['ldx'], [value], f'처리 루틴 {h:04X} 내성 칸')

    for i, row in rows('field_slots', 'spell',
                       lambda v: hexval(v, 'spell', 2, FIELD_FIRST, FIELD_FIRST + FIELD_COUNT - 1) - FIELD_FIRST):
        keys(row, ('spell', 'handler'), f'field_slots {FIELD_FIRST + i:02X}')
        if 'handler' not in row:
            continue
        h = hexval(row['handler'], 'handler', 4, 0x8000)
        require(raw or h in lay.field_handlers or (h == FIELD_NONE and lay.field[i] == FIELD_NONE),
                f'field_slots {FIELD_FIRST + i:02X}: 원래 표의 처리기가 아님 {h:04X}(8022 는 멈춤 루프)')
        put(FIELD_TABLE + i * 2, h.to_bytes(2, 'little'), f'필드 주문 {FIELD_FIRST + i:02X} 처리기')

    for h, row in rows('field_handlers', 'handler', lambda v: hexval(v, 'handler', 4)):
        keys(row, ('handler', 'spells', 'mp', 'heal'), f'field_handlers {h:04X}')
        require(h in FIELD_MP, f'field_handlers {h:04X}: MP 자리를 아는 처리기가 아님')
        if 'spells' in row:
            require(row['spells'] == [f'{FIELD_FIRST + i:02X}' for i, s in enumerate(lay.field) if s == h],
                    f'field_handlers {h:04X}: spells 는 읽기 전용')
        if 'mp' in row:
            mp = integer(row['mp'], 0, 255, 'mp')
            for site in FIELD_MP[h]:
                put(site, [mp], f'필드 처리기 {h:04X} MP')
        if 'heal' in row:
            require(h in FIELD_HEAL, f'field_handlers {h:04X}: 회복량 자리가 없음')
            heal = row['heal']
            keys(heal, ('base', 'spread'), 'heal')
            require(set(heal) == {'base', 'spread'}, 'heal: base·spread 가 모두 필요함')
            base, spread = integer(heal['base'], 0, 255, 'heal base'), integer(heal['spread'], 1, 255, 'heal spread')
            # 11:852E 는 8비트 A 로 회복량을 넘기므로 최댓값이 255 를 넘으면 0 쪽으로 돈다.
            require(base + spread - 1 <= 255, 'heal: base + spread - 1 이 255 를 넘음')
            top, spread_at, base_at = FIELD_HEAL[h]
            put(top, [base + spread - 1], f'필드 처리기 {h:04X} まんたん 회복량')
            put(spread_at, [spread], f'필드 처리기 {h:04X} 회복 폭')
            put(base_at, [base], f'필드 처리기 {h:04X} 회복 바탕')
    return wanted, notes


def patch(rom, doc, original=None, raw=False):
    wanted, notes = edits(rom, doc, original, raw)
    writes, changed = [], sorted(a for a, v in wanted.items() if u8(rom, a) != v)
    i = 0
    while i < len(changed):
        j = i
        while j + 1 < len(changed) and changed[j + 1] == changed[j] + 1 and notes[changed[j + 1]] == notes[changed[i]]:
            j += 1
        start, size = changed[i], j - i + 1
        writes.append({'at': f'{start >> 16:02X}:{start & 0xFFFF:04X}',
                       'hex': bytes(wanted[start + k] for k in range(size)).hex(' '),
                       'orig': bytes(u8(rom, start + k) for k in range(size)).hex(' '), 'note': notes[start]})
        i = j + 1
    return {'format': 'dq5patch/1', 'name': 'spellfx', 'writes': writes}


def check(rom, doc=None, raw=False):
    from dq5build import build, parse_at
    original = dump(rom)
    source = original if doc is None else doc
    lay = Layout(rom)
    writes = patch(rom, source, raw=raw)['writes']
    require(doc is not None or not writes, '원본 왕복 쓰기가 0개가 아님')
    rebuilt, _ = build(rom.d, [('spellfx', 0, [
        (parse_at(w['at'])[0], bytes.fromhex(w['hex']), bytes.fromhex(w['orig']), w['note']) for w in writes])], 0)
    after = Rom(rebuilt)
    require(not patch(after, source, lay, raw)['writes'], '빌더 적용 후 같은 입력을 다시 패치하면 쓰기가 남음')
    require(not patch(after, dump(after), lay, True)['writes'], '빌드한 롬을 다시 읽고 인코딩한 결과가 다름')
    print(f'전투 행동 {len(original["battle_slots"])}개·첫머리 {len(original["battle_handlers"])}개, '
          f'필드 주문 {len(original["field_slots"])}칸·처리기 {len(original["field_handlers"])}개; 쓰기 {len(writes)}개 검사 통과')


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
        p.add_argument('--raw', action='store_true', help='원래 표에 없는 처리 루틴·처리기와 짝이 아닌 연결도 받음')
    args = parser.parse_args()
    try:
        rom = Rom(args.rom.read_bytes())
        doc = json.loads(args.source.read_text(encoding='utf-8')) if getattr(args, 'source', None) else None
        if args.command == 'check':
            check(rom, doc, args.raw)
            return 0
        out = dump(rom) if args.command == 'dump' else patch(rom, doc, raw=args.raw)
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
