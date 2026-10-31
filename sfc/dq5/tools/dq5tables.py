"""DQ5(SFC) 게임 데이터 표 쓰기. 몬스터·물건·주문·피해량·동료 몬스터 표를 필드 이름이 붙은 JSON 으로 내보내고,
고친 JSON 을 빌더(dq5build.py)의 패치 목록(dq5patch/1)으로 바꾼다. 형식은 sfc/dq5/docs/dq5-data-format.md,
패치 목록은 sfc/dq5/docs/dq5-build-format.md.

입력 JSON 은 내보낸 것의 일부만 있어도 된다. 항목은 id(16진)로 찾고, 적힌 필드만 롬 값 위에 덮는다.
「이름」 처럼 _ 로 시작하거나 표에 없는 키는 읽지 않는다. 필드가 차지하지 않는 비트(뜻 모르는 비트)는 롬 값 그대로 둔다.
표의 크기(항목 수)는 늘리지 않는다.

  export  롬 → JSON(-o, 빼면 표준 출력). --tables monsters,items 처럼 고를 수 있음
  patch   JSON 여럿 → 패치 목록(-o). 롬과 다른 바이트만 쓰기로 내고 orig 를 채운다
  check   JSON 을 패치 목록으로 바꾸고, 그 목록을 붙인 롬을 다시 읽어 적은 값이 모두 나오는지 본다

사용:
  python sfc/dq5/tools/dq5tables.py rom/dq5.sfc export -o work/tables/dq5.json
  python sfc/dq5/tools/dq5tables.py rom/dq5.sfc patch work/tables/edit.json -o work/build/tables.dq5patch.json
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5chest import ITEM_NAMES  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402
from dq5text import string, string_codes, text  # noqa: E402

FORMAT = 'dq5tables/1'


def piece(byte, lsb=0, width=8):
    return byte, lsb, width


# 필드: 이름 → (종류, [(가상 바이트 번호, 시작 비트, 비트 수)…] 낮은 비트부터). 종류 int 는 정수, hex 는 16진 문자열,
# bits 는 2진 문자열(왼쪽이 높은 비트).
MONSTER_FIELDS = {
    'HP': ('int', [piece(3), piece(10, 0, 3)]),
    'MP': ('int', [piece(4)]),
    '민첩': ('int', [piece(0)]),
    '공격': ('int', [piece(1), piece(8, 7, 1)]),
    # 1FF 이면 게임이 7FF 로 읽는다(21:A2B5).
    '수비': ('int', [piece(2), piece(8, 6, 1)]),
    '경험치': ('int', [piece(5), piece(6)]),
    '금화': ('int', [piece(7), piece(8, 2, 2)]),
    '행동수': ('int', [piece(11, 6, 2)]),
    '재생': ('int', [piece(10, 3, 2)]),
    '첫상태확률': ('int', [piece(9, 6, 2)]),
    '첫상태종류': ('int', [piece(12, 7, 1)]),
    '드롭률': ('int', [piece(9, 3, 3)]),
    '드롭': ('hex', [piece(23)]),
    'f68': ('int', [piece(8, 0, 2)]),
    'f69': ('int', [piece(10, 5, 3)]),
    '대상고정': ('int', [piece(12, 6, 1)]),
    '피하기': ('int', [piece(8, 4, 2)]),
    '동료확률': ('int', [piece(9, 0, 3)]),
    '동료종류': ('hex', [piece(24, 0, 7)]),
    **{f'행동{i + 1}': ('hex', [piece(17 + i)]) for i in range(6)},
}
# 내성 종류 50+k 의 2비트 칸(21:91F9). 18칸을 숫자 18자리 문자열 하나로 다룬다.
RESISTS = 18


def resist_piece(k):
    return piece(0x0C + (k + 1) // 4, 6 - (k + 1) % 4 * 2, 2)


ITEM_COUNT = 0xD8
ITEM_FIELDS = {
    '가격': ('int', [piece(0)]),
    '가격배수': ('int', [piece(1, 0, 2)]),
    'k1b2': ('int', [piece(1, 2, 1)]),
    '팔수없음': ('int', [piece(1, 3, 1)]),
    '가득창': ('int', [piece(1, 4, 1)]),
    '쓰면없어짐': ('int', [piece(1, 5, 1)]),
    '필드대상창': ('int', [piece(1, 6, 1)]),
    '사용메시지없음': ('int', [piece(1, 7, 1)]),
    '칸': ('int', [piece(2, 0, 3)]),
    '저주': ('int', [piece(2, 3, 1)]),
    '그룹무작위': ('int', [piece(2, 4, 1)]),
    '적쪽': ('int', [piece(2, 5, 1)]),
    '전투대상창': ('int', [piece(2, 6, 1)]),
    '상점전투설명': ('int', [piece(2, 7, 1)]),
    '인파스설명': ('int', [piece(3, 0, 6)]),
    '인파스가격줄': ('int', [piece(3, 6, 1)]),
    '인파스횟수줄': ('int', [piece(3, 7, 1)]),
    'k4하위': ('int', [piece(4, 0, 6)]),
    '인파스장비줄': ('int', [piece(4, 6, 1)]),
    '인파스종류': ('int', [piece(4, 7, 1)]),
    '힘': ('int', [piece(5)]),
    '장비사람': ('bits', [piece(6)]),
    '장비몬스터': ('bits', [piece(7), piece(8)]),
}

SPELL_COUNT = 0xAB
SPELL_FIELDS = {
    # 1F = MP 를 쓰지 않음, 1E = 36, 1D = 남은 MP 전부(26:839A).
    'MP': ('int', [piece(0, 0, 5)]),
    '범위': ('int', [piece(0, 5, 2)]),
    '적쪽': ('int', [piece(0, 7, 1)]),
    # 뱅크 20 의 실행 루틴. 975F 적 하나, 9771 적 그룹, 97BC 적 전체, 9824 우리 편 하나, 9829 우리 편 전체.
    '대상루틴': ('hex', [piece(1), piece(2)]),
}

# 주문 목록 창의 MP 숫자(21:9BAD 의 LDA $219BB4,X). 작전 AI 가 MP 가 모자란 주문과 작전 3 에서 MP 드는 주문을 빼는
# 거름(21:DA58, BRK 88 85 의 $47)도 이 값을 본다. 원본은 모든 주문에서 menu_mp(전투 MP) 와 같으므로, 전투 MP 를
# 바꾸면 이 칸도 같이 쓴다. 66 뒤 칸도 원본은 0 이고 그 행동들의 전투 MP 는 1F 다.
MENU_MP = 0x219BB4


def menu_mp(battle):
    """전투 MP 5비트 → 창의 MP 칸. 1F(쓰지 않음)은 0, 1E 는 36, 1D(남은 MP 전부)는 FF."""
    return {0x1F: 0, 0x1E: 36, 0x1D: 0xFF}.get(battle, battle)


AMOUNT_COUNT = 0x40
AMOUNT_FIELDS = {
    # FE 는 300 으로 읽는다(20:AB70).
    '바탕': ('int', [piece(0)]),
    '폭': ('int', [piece(1)]),
}

COMPANION_COUNT = 0x2A
COMPANION_FIELDS = {
    '레벨': ('int', [piece(0)]),
    '최대레벨': ('int', [piece(1)]),
    'HP': ('int', [piece(6)]),
    'MP': ('int', [piece(7)]),
    '장비갈래': ('int', [piece(8, 0, 4)]),
}


def name_of(table):
    return lambda rom, n: text(string_codes(rom, string(rom, table, n)))


class Table:
    def __init__(self, key, count, fields, addrs, names=None, resists=False):
        self.key, self.count, self.fields, self.addrs, self.names, self.resists = key, count, fields, addrs, names, resists

    def bytes_of(self, data, n):
        return [data[lorom(a)] for a in self.addrs(n)]


TABLES = {
    'monsters': Table('monsters', 236, MONSTER_FIELDS,
                      lambda n: [0x238000 + n * 25 + i for i in range(25)], name_of(4), resists=True),
    'items': Table('items', ITEM_COUNT, ITEM_FIELDS,
                   lambda n: [0x23B081 + k * ITEM_COUNT + n for k in range(7)] + [0x23B669 + n * 2, 0x23B66A + n * 2],
                   name_of(ITEM_NAMES)),
    'spells': Table('spells', SPELL_COUNT, SPELL_FIELDS,
                    lambda n: [0x268765 + n, 0x268865 + n * 2, 0x268866 + n * 2], name_of(3)),
    'amounts': Table('amounts', AMOUNT_COUNT, AMOUNT_FIELDS, lambda n: [0x278071 + n * 2, 0x278072 + n * 2]),
    'companions': Table('companions', COMPANION_COUNT, COMPANION_FIELDS,
                        lambda n: [0x23AED1 + n * 9 + i for i in range(9)]),
}


def get(b, pieces):
    v, shift = 0, 0
    for byte, lsb, width in pieces:
        v |= (b[byte] >> lsb & (1 << width) - 1) << shift
        shift += width
    return v


def put(b, pieces, v):
    width_all = sum(w for _, _, w in pieces)
    if not 0 <= v < 1 << width_all:
        raise ValueError(f'{v} 는 {width_all}비트에 들어가지 않음')
    for byte, lsb, width in pieces:
        mask = (1 << width) - 1
        b[byte] = b[byte] & ~(mask << lsb) | (v & mask) << lsb
        v >>= width


def fmt(kind, pieces, v):
    width = sum(w for _, _, w in pieces)
    if kind == 'hex':
        return f'{v:0{(width + 3) // 4}X}'
    if kind == 'bits':
        return f'{v:0{width}b}'
    return v


def parse(kind, s):
    if kind == 'int':
        if isinstance(s, bool) or not isinstance(s, int):
            raise ValueError(f'정수가 아님: {s!r}')
        return s
    if not isinstance(s, str):
        raise ValueError(f'문자열이 아님: {s!r}')
    return int(s.replace(' ', ''), 16 if kind == 'hex' else 2)


def decode(t, rom, data, n):
    b = t.bytes_of(data, n)
    e = {'id': f'{n:02X}'}
    if t.names and rom is not None:
        e['_이름'] = t.names(rom, n)
    for k, (kind, pieces) in t.fields.items():
        e[k] = fmt(kind, pieces, get(b, pieces))
    if t.resists:
        e['내성'] = ''.join(str(get(b, [resist_piece(k)])) for k in range(RESISTS))
    return e


def export(rom, data, keys):
    doc = {'format': FORMAT}
    for key in keys:
        t = TABLES[key]
        doc[key] = [decode(t, rom, data, n) for n in range(t.count)]
    return doc


def encode(t, data, entry):
    """항목 하나를 롬 바이트 위에 덮은 (번호, 새 가상 바이트, 원래 가상 바이트)."""
    n = int(entry['id'], 16)
    if not 0 <= n < t.count:
        raise ValueError(f'{t.key} id {entry["id"]} 가 0~{t.count - 1:X} 밖')
    old = t.bytes_of(data, n)
    b = list(old)
    for k, v in entry.items():
        try:
            if k in t.fields:
                kind, pieces = t.fields[k]
                put(b, pieces, parse(kind, v))
            elif k == '내성' and t.resists:
                if len(v) != RESISTS or any(c not in '0123' for c in v):
                    raise ValueError('0~3 숫자 18자리여야 함')
                for i, c in enumerate(v):
                    put(b, [resist_piece(i)], int(c))
        except ValueError as e:
            raise ValueError(f'{t.key} {entry["id"]} {k}: {e}') from None
    return n, b, old


def writes_for(docs, data):
    """JSON 문서들 → 롬에 쓸 (파일 위치, 새 바이트, 원래 바이트, 설명) 를 위치 순으로. 같은 바이트를 두 번 고치면 거부."""
    changed = {}
    for doc in docs:
        if doc.get('format') != FORMAT:
            raise ValueError(f'format 이 {FORMAT!r} 이 아님')
        for key, t in TABLES.items():
            for entry in doc.get(key, []):
                n, new, old = encode(t, data, entry)
                for a, x, y in zip(t.addrs(n), new, old):
                    if x == y:
                        continue
                    off = lorom(a)
                    if off in changed and changed[off][0] != x:
                        raise ValueError(f'{t.key} {n:02X}: 파일 {off:X} 를 다른 값으로 두 번 고침')
                    changed[off] = (x, y, f'{t.key} {n:02X}')
    for n in range(SPELL_COUNT):
        off = lorom(0x268765 + n)
        if off not in changed:
            continue
        old, new = data[off] & 0x1F, changed[off][0] & 0x1F
        menu = lorom(MENU_MP + n)
        if old == new:
            continue
        if data[menu] != menu_mp(old):
            raise ValueError(f'spells {n:02X}: 주문 목록 MP 칸 {cpu(menu)} = {data[menu]:02X} 가 전투 MP {old} 와 맞지 않는 롬'
                             f'(원본에서 만들 것)')
        if menu_mp(new) != data[menu]:
            changed[menu] = (menu_mp(new), data[menu], f'spells {n:02X} 주문 목록 MP')
    return [(o, *changed[o]) for o in sorted(changed)]


def field_mp_warnings(writes, data):
    """전투 MP 를 바꾼 주문 가운데 필드에서도 외우는 것의 필드 MP(dq5spellfx.py 의 field_handlers, 뱅크 11 의 즉값)가
    새 전투 MP 와 다르면 그 경고 문장들. 필드에서 외울 때는 그 즉값만큼 빼고, 창의 MP 숫자는 21:9BB4 를 보인다."""
    from dq5spellfx import FIELD_COUNT, FIELD_FIRST, FIELD_MP, FIELD_TABLE
    out = []
    for off, new, old, label in writes:
        n = next((n for n in range(SPELL_COUNT) if lorom(0x268765 + n) == off), None)
        if n is None or not 0 <= n - FIELD_FIRST < FIELD_COUNT or (new ^ old) & 0x1F == 0:
            continue
        handler = int.from_bytes(data[lorom(FIELD_TABLE + (n - FIELD_FIRST) * 2):][:2], 'little')
        if handler in FIELD_MP and data[lorom(FIELD_MP[handler][0])] != new & 0x1F:
            out.append(f'경고: spells {n:02X} 의 필드 MP(처리기 11:{handler:04X})는 {data[lorom(FIELD_MP[handler][0])]} 그대로라 '
                       f'필드에서 외우면 그만큼 뺌(창에는 {new & 0x1F}). dq5spellfx.py 의 field_handlers 에서 맞출 것')
    return out


def cpu(off):
    return f'{off // 0x8000:02X}:{0x8000 + off % 0x8000:04X}'


def patch_doc(writes, name):
    """이어진 바이트는 쓰기 하나로 묶는다(뱅크 안에서만)."""
    out = []
    for off, new, old, label in writes:
        if out and out[-1][0] + len(out[-1][1]) == off and off % 0x8000:
            out[-1][1].append(new)
            out[-1][2].append(old)
            if label not in out[-1][3]:
                out[-1][3].append(label)
        else:
            out.append([off, [new], [old], [label]])
    return {'format': 'dq5patch/1', 'name': name, 'writes': [
        {'at': cpu(o), 'hex': bytes(n).hex(' '), 'orig': bytes(p).hex(' '), 'note': ', '.join(ls)}
        for o, n, p, ls in out]}


def check(docs, data):
    """패치를 붙인 롬을 다시 읽어, 입력에 적힌 값이 모두 그대로 나오는지. 틀린 것 목록."""
    d = bytearray(data)
    for off, new, _, _ in writes_for(docs, data):
        d[off] = new
    bad = []
    for doc in docs:
        for key, t in TABLES.items():
            for entry in doc.get(key, []):
                got = decode(t, None, d, int(entry['id'], 16))
                for k, v in entry.items():
                    if k in got and k != 'id':
                        kind = t.fields[k][0] if k in t.fields else 'int'
                        want = v if kind == 'int' else fmt(kind, t.fields[k][1], parse(kind, v))
                        if got[k] != want:
                            bad.append(f'{key} {entry["id"]} {k}: 적은 값 {v!r}, 읽은 값 {got[k]!r}')
    for n in range(SPELL_COUNT):
        battle = d[lorom(0x268765 + n)] & 0x1F
        if d[lorom(MENU_MP + n)] != menu_mp(battle) and data[lorom(MENU_MP + n)] == menu_mp(data[lorom(0x268765 + n)] & 0x1F):
            bad.append(f'spells {n:02X}: 주문 목록 MP {d[lorom(MENU_MP + n)]} 가 전투 MP {battle} 와 맞지 않음')
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('cmd', choices=('export', 'patch', 'check'))
    ap.add_argument('inputs', nargs='*')
    ap.add_argument('-o', '--out')
    ap.add_argument('--tables', default=','.join(TABLES))
    ap.add_argument('--name', default='tables')
    a = ap.parse_args()
    data = open(a.rom, 'rb').read()
    rom = Rom(data)
    if a.cmd == 'export':
        keys = a.tables.split(',')
        unknown = [k for k in keys if k not in TABLES]
        if unknown:
            print(f'모르는 표: {",".join(unknown)} (있는 표: {",".join(TABLES)})', file=sys.stderr)
            return 1
        text_out = json.dumps(export(rom, data, keys), ensure_ascii=False, indent=1) + '\n'
        if a.out:
            os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True)
            open(a.out, 'w', encoding='utf-8').write(text_out)
        else:
            sys.stdout.write(text_out)
        return 0
    docs = [json.load(open(p, encoding='utf-8')) for p in a.inputs]
    try:
        if a.cmd == 'check':
            bad = check(docs, data)
            for line in bad:
                print(line)
            print(f'쓰기 {len(writes_for(docs, data))}바이트, 다시 읽어 틀린 값 {len(bad)}개')
            return 1 if bad else 0
        writes = writes_for(docs, data)
        for line in field_mp_warnings(writes, data):
            print(line, file=sys.stderr)
    except ValueError as e:
        print(f'오류: {e}', file=sys.stderr)
        return 1
    doc = patch_doc(writes, a.name)
    os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True)
    with open(a.out, 'w', encoding='utf-8') as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
        f.write('\n')
    print(f'바뀐 바이트 {len(writes)}개, 쓰기 {len(doc["writes"])}개 → {a.out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
