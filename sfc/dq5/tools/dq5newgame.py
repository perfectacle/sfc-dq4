"""DQ5 새 게임을 시작할 때의 일행·금화·이름 쓰기.

형식은 sfc/dq5/docs/dq5-build-format.md 의 「새 게임 일행」. 23:D6A1(21:A1D7 이 JSL)이 7E:2000~2A9F 를 지운 뒤
23:D6ED 의 64바이트를 7E:2000 에, 인물 레코드 표 23:C014 의 앞 42바이트(인물 0, 주인공)를 7E:2040 에 베낀다.
머리 64바이트는 제자리에서 고치고, 일행 레코드는 --at 에 새 표로 두어 23:D6DE 의 원본 주소와 23:D6E8 의 길이를
고친다. 23:C014 는 사람이 일행에 들 때도 읽으므로 고치지 않는다.

  python sfc/dq5/tools/dq5newgame.py rom/dq5.sfc dump -o work/newgame.json
  python sfc/dq5/tools/dq5newgame.py rom/dq5.sfc patch work/newgame.json [--at 3C:8000] -o work/newgame.dq5patch.json
  python sfc/dq5/tools/dq5newgame.py rom/dq5.sfc check

JSON: {"format":"dq5newgame/1", "gold":20, "names":{"hero":[1,1,1,1,1,1,1,1]},
       "walking":1, "wagon":false, "members":[{"base":0, "level":1, "items":[66,0], "equipped":[0,1]}]}
members 를 적으면 일행 레코드 전부를 다시 정한다(1~8개, --at 필요). base 는 23:C014 표의 칸 번호(0~12)이고 나머지
필드는 그 칸 위에 덮는다. level 을 바꾸면 적지 않은 exp·next_exp 에 원래 성장 표(23:9E41·A1B1)의 level·(level + 1)
누적 경험치를 넣는다. 마차가 없으면 walking 은 일행 수와 같다. 주인공(+0 = 0)은 첫 레코드에만, 같은 사람은 한 번만. 적지 않은 머리 필드는 원래 값을 둔다. 이름은 1바이트 부호 8개까지(남는 칸은 01).
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5growth import MONSTERS as MONSTER_GROWTH, PEOPLE as PERSON_GROWTH, RECORD as GROWTH_RECORD, exp_at  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402

FORMAT = 'dq5newgame/1'
HEADER = 0x23D6ED
HEADER_SIZE = 0x40
PEOPLE = 0x23C014
PEOPLE_COUNT = 13                # 23:C014 표에서 +0 이 인물 번호(00~0A, 47·48)나 80·81 인 앞 13칸
RECORD = 0x2A
COPY_SOURCE = 0x23D6DE           # LDA $23C014,X
COPY_LENGTH = 0x23D6E7           # CPX #$002A
MEMBERS_MAX = 8
NAMES = {'hero': 0x01, 'son': 0x09, 'daughter': 0x11}
GOLD = 0x19
WAGON, COUNT, WALKING, WALKING_COPY = 0x1C, 0x1D, 0x1E, 0x1F
ORDER, ORDER_COPY = 0x20, 0x28
# 일행 레코드 필드(오프셋, 바이트 수). sfc/dq5/docs/dq5-data-format.md 의 파티 레코드와 dq5growth.RECORD_FIELD.
FIELDS = {'person': (0x00, 1), 'status': (0x01, 1), 'hp': (0x02, 2), 'mp': (0x04, 2), 'agility': (0x06, 1),
          'strength': (0x07, 1), 'resilience': (0x08, 1), 'wisdom': (0x09, 1), 'luck': (0x0A, 1), 'exp': (0x0B, 3),
          'max_hp': (0x0E, 2), 'max_mp': (0x10, 2), 'level': (0x12, 1), 'max_level': (0x13, 1), 'title': (0x22, 1),
          'spells': (0x23, 3), 'next_exp': (0x26, 3), 'flags': (0x29, 1)}
EQUIPPED, ITEMS, ITEM_SLOTS, ITEM_MAX = 0x14, 0x16, 12, 0xD7


def integer(value, maximum, name, minimum=0):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f'{name}: {minimum}~{maximum} 정수여야 함')
    return value


def fields(value, allowed, name):
    if not isinstance(value, dict) or value.keys() - allowed:
        raise ValueError(f'{name}: 허용한 필드 {sorted(allowed)}만 있는 JSON 객체여야 함')


def read(rom, addr, size):
    off = lorom(addr)
    raw = bytes(rom.d[off:off + size])
    if len(raw) != size:
        raise ValueError(f'{addr:06X}: 롬에 {size}바이트가 없음')
    return raw


def check_code(rom):
    """23:D6DB~ 의 복사 루프가 원래 꼴인지 본다. 원본 롬만 받는다."""
    if read(rom, COPY_SOURCE, 4) != b'\xbf\x14\xc0\x23' or read(rom, COPY_LENGTH, 3) != b'\xe0\x2a\x00' \
            or read(rom, 0x23D6CD, 4) != b'\xbf\xed\xd6\x23':
        raise ValueError('23:D6CD~D6E9 가 원래 새 게임 복사 루프가 아님; 원본 롬이어야 함')


def record_fields(raw):
    out = {name: int.from_bytes(raw[at:at + size], 'little') for name, (at, size) in FIELDS.items()}
    items = list(raw[ITEMS:ITEMS + ITEM_SLOTS])
    equipped = int.from_bytes(raw[EQUIPPED:EQUIPPED + 2], 'little')
    out['items'] = [v for v in items if v != 0xFF]
    out['equipped'] = [i for i in range(ITEM_SLOTS) if equipped >> i & 1]
    return out


def dump(rom):
    check_code(rom)
    head = read(rom, HEADER, HEADER_SIZE)
    return {'format': FORMAT,
            'gold': int.from_bytes(head[GOLD:GOLD + 3], 'little'),
            'names': {k: list(head[at:at + 8]) for k, at in NAMES.items()},
            'walking': head[WALKING], 'wagon': bool(head[WAGON] & 0x80),
            'members': [{'base': 0, **record_fields(read(rom, PEOPLE, RECORD))}]}


def encode_record(rom, row, name):
    fields(row, {'base', 'items', 'equipped', *FIELDS}, name)
    base = integer(row.get('base'), PEOPLE_COUNT - 1, f'{name} base')
    out = bytearray(read(rom, PEOPLE + base * RECORD, RECORD))
    for key, (at, size) in FIELDS.items():
        if key in row:
            out[at:at + size] = integer(row[key], (1 << 8 * size) - 1, f'{name} {key}').to_bytes(size, 'little')
    if 'items' in row:
        items = row['items']
        if not isinstance(items, list) or len(items) > ITEM_SLOTS:
            raise ValueError(f'{name} items: 물건 번호 {ITEM_SLOTS}개까지의 배열이어야 함')
        out[ITEMS:ITEMS + ITEM_SLOTS] = bytes([integer(v, ITEM_MAX, f'{name} item') for v in items] +
                                             [0xFF] * (ITEM_SLOTS - len(items)))
    if 'equipped' in row:
        slots = row['equipped']
        if not isinstance(slots, list) or len(set(slots)) != len(slots):
            raise ValueError(f'{name} equipped: 중복 없는 물건 칸 번호 배열이어야 함')
        bits = 0
        for i in slots:
            if out[ITEMS + integer(i, ITEM_SLOTS - 1, f'{name} equipped')] == 0xFF:
                raise ValueError(f'{name} equipped: 빈 물건 칸 {i} 는 장비할 수 없음')
            bits |= 1 << i
        out[EQUIPPED:EQUIPPED + 2] = bits.to_bytes(2, 'little')
    if 'level' in row:
        # 새 게임 첫 장면까지 주인공(레코드 0)의 +26 은 성장 표의 (레벨 + 1) 값으로 다시 셈해진다. 다른 레코드도 같게 두고,
        # 지금 경험치도 그 레벨의 누적 값으로 맞춘다. 인물 47·48(フローラ 등)은 & 3F 로 성장 레코드 7·8 을 쓴다(코드 읽기).
        person = out[0]
        growth = (MONSTER_GROWTH if person & 0x80 else PERSON_GROWTH) + (person & 0x3F) * GROWTH_RECORD
        if 'next_exp' not in row:
            out[0x26:0x29] = exp_at(rom, growth, out[0x12] + 1).to_bytes(3, 'little')
        if 'exp' not in row:
            out[0x0B:0x0E] = exp_at(rom, growth, out[0x12]).to_bytes(3, 'little')
    if int.from_bytes(out[2:4], 'little') > int.from_bytes(out[0x0E:0x10], 'little') or \
            int.from_bytes(out[4:6], 'little') > int.from_bytes(out[0x10:0x12], 'little'):
        raise ValueError(f'{name}: 지금 HP·MP 가 최대보다 큼')
    if not 1 <= out[0x12] <= out[0x13]:
        raise ValueError(f'{name}: level 은 1~max_level 이어야 함')
    return bytes(out)


def parse_at(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-fA-F]{2}:[0-9a-fA-F]{4}', value):
        raise ValueError('--at 은 BB:AAAA 형식이어야 함')
    bank, low = (int(v, 16) for v in value.split(':'))
    if not 0x30 <= bank <= 0x7D or low < 0x8000:
        raise ValueError('--at 은 30~7D 뱅크의 8000~FFFF 여야 함')
    return bank << 16 | low


def edits(rom, doc, at=None):
    """(주소, 새 바이트, 원래 바이트 또는 None, 설명) 목록."""
    check_code(rom)
    fields(doc, {'format', 'gold', 'names', 'walking', 'wagon', 'order', 'members'}, '문서')
    if doc.get('format') != FORMAT:
        raise ValueError(f'format 은 {FORMAT} 이어야 함')
    old = read(rom, HEADER, HEADER_SIZE)
    head = bytearray(old)
    if 'gold' in doc:
        head[GOLD:GOLD + 3] = integer(doc['gold'], 999999, 'gold').to_bytes(3, 'little')
    names = doc.get('names', {})
    fields(names, set(NAMES), 'names')
    for key, value in names.items():
        if not isinstance(value, list) or not 1 <= len(value) <= 8:
            raise ValueError(f'names.{key}: 1~8개 바이트 배열이어야 함')
        head[NAMES[key]:NAMES[key] + 8] = bytes([integer(v, 0xFF, f'names.{key}') for v in value] + [1] * (8 - len(value)))
    out = []
    members = doc.get('members')
    count = head[COUNT]
    if members is not None:
        if not isinstance(members, list) or not 1 <= len(members) <= MEMBERS_MAX:
            raise ValueError(f'members: 1~{MEMBERS_MAX}개 배열이어야 함')
        if at is None:
            raise ValueError('members 를 쓰려면 --at 으로 새 레코드 표 자리를 줘야 함')
        records = b''.join(encode_record(rom, row, f'members[{i}]') for i, row in enumerate(members))
        people = [records[i * RECORD] for i in range(len(members))]
        # 21:9F49 는 +0 이 0 인 칸을 빈 칸으로, 21:9FD8 은 +0 이 같은 첫 칸을 그 사람으로 본다(코드 읽기).
        if 0 in people[1:]:
            raise ValueError('members: 인물 0(주인공)은 첫 레코드에만 둘 수 있음')
        persons = [p for p in people if not p & 0x80]
        if len(set(persons)) != len(persons):
            raise ValueError('members: 같은 사람(+0)을 두 번 둘 수 없음')
        if (at & 0xFFFF) + len(records) > 0x10000:
            raise ValueError('새 레코드 표가 뱅크를 넘음')
        count = len(members)
        out += [(at, records, None, 'new game party records'),
                (COPY_SOURCE + 1, at.to_bytes(3, 'little'), read(rom, COPY_SOURCE + 1, 3), 'new game record source'),
                (COPY_LENGTH + 1, len(records).to_bytes(2, 'little'), read(rom, COPY_LENGTH + 1, 2),
                 'new game record length')]
    elif at is not None:
        raise ValueError('--at 은 members 를 쓸 때만 씀')
    wagon = doc.get('wagon', bool(head[WAGON] & 0x80))
    if type(wagon) is not bool:
        raise ValueError('wagon: true/false 여야 함')
    # 마차가 없으면 모두 걷는다. 걷는 수가 일행 수보다 작은 상태는 마차가 있을 때만 실측했다.
    walking = integer(doc.get('walking', min(3, count) if wagon else count), min(3, count), 'walking', 1)
    if not wagon and walking != count:
        raise ValueError('마차가 없으면 walking 은 일행 수와 같아야 함')
    order = doc.get('order', list(range(count)))
    if not isinstance(order, list) or sorted(order) != list(range(count)) or \
            any(type(v) is not int for v in order):
        raise ValueError(f'order: 0~{count - 1} 의 순열이어야 함')
    head[WAGON] = head[WAGON] & 0x7F | (0x80 if wagon else 0)
    if count > 3 and not wagon:
        raise ValueError('넷 이상으로 시작하려면 wagon 이 필요함(마차 밖은 셋까지)')
    head[COUNT] = count
    head[WALKING] = head[WALKING_COPY] = walking
    head[ORDER:ORDER + 8] = head[ORDER_COPY:ORDER_COPY + 8] = bytes(order + [0] * (8 - count))
    out.insert(0, (HEADER, bytes(head), old, 'new game header'))
    return out


def patch(rom, doc, at=None, name='newgame'):
    writes = []
    for addr, new, old, note in edits(rom, doc, at):
        if new == old:
            continue
        w = {'at': f'{addr >> 16:02X}:{addr & 0xFFFF:04X}', 'hex': new.hex(' '), 'note': note}
        if old is not None:
            w['orig'] = old.hex(' ')
        writes.append(w)
    manifest = {'format': 'dq5patch/1', 'name': name, 'writes': writes}
    if at is not None:
        size = sum(len(bytes.fromhex(w['hex'])) for w in writes if w['note'] == 'new game party records')
        manifest['rom_size'] = max(2, -(-(lorom(at) + size) // 0x100000))
    return manifest


def new_game(rom):
    """빌드한 롬이 새 게임에서 7E:2000~ 에 둘 (머리 64바이트, 일행 레코드들)."""
    head = read(rom, HEADER, HEADER_SIZE)
    source = int.from_bytes(read(rom, COPY_SOURCE + 1, 3), 'little')
    size = int.from_bytes(read(rom, COPY_LENGTH + 1, 2), 'little')
    return head, read(rom, source, size)


def check(rom):
    doc = dump(rom)
    changed = sum(new != old for _, new, old, _ in edits(rom, {k: v for k, v in doc.items() if k != 'members'}))
    print(f'머리 {HEADER_SIZE}바이트·주인공 레코드 {RECORD}바이트: 다른 쓰기 {changed}개')
    return bool(changed)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('rom')
    sub = parser.add_subparsers(dest='command', required=True)
    out = sub.add_parser('dump')
    out.add_argument('-o', '--out', required=True)
    write = sub.add_parser('patch')
    write.add_argument('source')
    write.add_argument('-o', '--out', required=True)
    write.add_argument('--at')
    write.add_argument('--name', default='newgame')
    sub.add_parser('check')
    args = parser.parse_args()
    try:
        with open(args.rom, 'rb') as f:
            rom = Rom(f.read())
        if args.command == 'check':
            return int(check(rom))
        if args.command == 'dump':
            result = dump(rom)
        else:
            with open(args.source, encoding='utf-8') as f:
                doc = json.load(f)
            result = patch(rom, doc, parse_at(args.at) if args.at else None, args.name)
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
