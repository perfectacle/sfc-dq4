"""DQ5 창 레코드(04:EB48)의 자리·크기 쓰기. 전투 창도 같은 레코드를 쓴다.

형식은 sfc/dq5/docs/dq5-build-format.md 의 「창 자리·크기」. 레코드 머리 +0 아래 5비트 X, +1 아래 5비트 Y,
+2 아래 5비트 너비, +3 아래 4비트 높이(타일)만 바꾸고 나머지 비트와 내용은 그대로 둔다.
전투 메시지 창 둘(18 턴 메시지, 25 「…が あらわれた！」)은 글자·▼ 칸이 코드에 박혀 있어 두 레코드의 X 를 함께
옮기고 그 코드 피연산자도 고친다. 너비·Y·높이는 받지 않는다(message_edits 의 오류 문구가 까닭).

  python sfc/dq5/tools/dq5windowwrite.py rom/dq5.sfc dump -o work/windows.json
  python sfc/dq5/tools/dq5windowwrite.py rom/dq5.sfc patch work/windows.json -o work/windows.dq5patch.json
  python sfc/dq5/tools/dq5windowwrite.py rom/dq5.sfc check

JSON: {"format":"dq5windows/1", "windows":[{"index":"19","x":12,"y":14}]}. index 는 창 번호(16진 문자열),
x·y·w·h 가운데 바꿀 것만 적는다. 바꾼 창은 BG3 타일맵(32 × 32 타일) 안이어야 한다. +0 bit7 인 창(다른 창을 가리킴),
여러 번호가 함께 쓰는 레코드(89~8C), +0 bit6 창의 h(높이를 04:9FD3 이 일행에 맞춰 정함)는 받지 않는다.
18·25 는 한쪽만 적어도 둘 다 옮기고, 둘 다 적으면 값이 같아야 한다.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5map import Rom, lorom  # noqa: E402
from dq5text import WINDOWS  # noqa: E402

FORMAT = 'dq5windows/1'
FIELDS = {'x': (0, 0x1F), 'y': (1, 0x1F), 'w': (2, 0x1F), 'h': (3, 0x0F)}
MAP_W = 32
# 전투 메시지 창. 18 은 턴 메시지(24:A5D9 가 26칸 × 6줄 글자 격자를 옮김), 25 는 나타난 무리(04:BCE7).
MESSAGES = (0x18, 0x25)
# 격자 7E:1DD5 는 26칸 × 6줄(메시지 3줄)이고 바로 뒤 7E:1E71~ 는 필드 변수(01:DA5C 등)라 넓히거나 줄을 늘릴 수 없다.
MESSAGE_W = 28
# +0 bit6 창은 04:9FD3 이 높이를 다시 센다. bit5 가 켜지면 일행 수(4까지) × 2 + 3, 꺼지면 메뉴마다 달라 4비트 최대로 본다.
PARTY_HEIGHT = 4 * 2 + 3
MENU_HEIGHT = 0x0F


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


def records(rom):
    """창 번호 → 레코드 주소. 포인터는 첫 레코드 앞까지 놓일 수 있지만, 원본은 94 부터 0000·00FF·FFFF 같은
    창이 아닌 바이트라 8000 미만인 첫 포인터에서 센다."""
    first = rom.u16(WINDOWS)
    out = {}
    for n in range((first - (WINDOWS & 0xFFFF)) // 2):
        low = rom.u16(WINDOWS + n * 2)
        if low < 0x8000:
            break
        if low > 0x10000 - 4:
            raise ValueError(f'창 {n:02X}: 레코드 머리 04:{low:04X} 가 뱅크 04 끝을 넘음')
        out[n] = 0x040000 | low
    if not 0 < len(out) <= 0x100:
        raise ValueError('04:EB48 창 표가 원래 꼴이 아님')
    return out


def header(raw):
    return {k: raw[at] & mask for k, (at, mask) in FIELDS.items()}


def message_sites(x, y):
    """메시지 창 X·Y 에 맞춘 코드 피연산자: (명령 주소, 여는 바이트, 피연산자 크기, 값, 설명).
    BG3 타일맵 버퍼(7E:5000) 안 바이트 위치이고, 원래 롬(2,21)의 값과 같다. ▼ 는 오른쪽 테두리 바로 안 칸.
    STA long(9F)은 아래 두 바이트만 고치고, 뱅크 바이트 7E 는 원래 꼴인지 볼 때만 쓴다."""

    def at(row, col):
        return (row * 32 + col) * 2

    return [(0x24A5EC, 0x9F, 2, 0x5000 + at(y, x + 1), '글자 격자 → BG3 버퍼'),
            (0x24883B, 0x9F, 2, 0x5000 + at(y + 1, x + 1), 'FD ▼(켜기)'),
            (0x24884F, 0x9F, 2, 0x5000 + at(y + 1, x + 1), 'FD ▼(끄기)'),
            (0x24A51E, 0xA2, 2, at(y + 5, x + MESSAGE_W - 2), '셋째 줄 끝 ▼'),
            (0x24A528, 0xA2, 2, at(y + 6, x + MESSAGE_W - 2), '넷째 무리 줄 끝 ▼'),
            (0x04BCF8, 0xA9, 1, x + 1, '무리 줄 첫 칸')]


def message_edits(rom, table, sharing, rows):
    """창 18·25 를 같은 X 로 옮기는 쓰기. rows 는 {창: 문서 줄}."""
    olds = {n: read(rom, table[n], 4) for n in MESSAGES}
    base = header(olds[MESSAGES[0]])
    for n, old in olds.items():
        if old[0] & 0x80 or len(sharing[table[n]]) > 1 or header(old) != base:
            raise ValueError('창 18·25 레코드가 원래 꼴(따로 쓰는 레코드, 같은 자리·크기)이 아님')
    want = dict(base)
    for key, (_, mask) in FIELDS.items():
        values = {integer(row[key], mask, f'창 {n:02X} {key}') for n, row in rows.items() if key in row}
        if len(values) > 1:
            raise ValueError(f'창 18·25 는 함께 옮겨 {key} 가 같아야 함')
        if values:
            want[key] = values.pop()
    if want == base:
        return []
    if want['w'] != base['w']:
        raise ValueError('창 18·25 너비는 받지 않음: 글자 격자 7E:1DD5 가 26칸이고 바로 뒤 7E:1E71~ 는 필드 변수라 넓힐 수 없음. '
                         '글자는 줄을 저절로 바꾸지 않아 좁히면 테두리를 넘음')
    if want['y'] != base['y'] or want['h'] != base['h']:
        raise ValueError('창 18·25 Y·높이는 받지 않음: 전투 BG3 0~6줄은 상태 창, 7~20줄은 공격·주문 효과 층(00:FD75 가 '
                         '7E:8A1D 를 VRAM 1CE0 에 14줄 올림), 28줄부터는 화면 밖이라 메시지 창은 21~27줄에만 둘 수 있음')
    if want['x'] + want['w'] > MAP_W:
        raise ValueError('창 18·25: BG3 타일맵 32칸 밖')
    out = []
    for n in MESSAGES:
        new = bytearray(olds[n])
        new[0] = new[0] & 0xE0 | want['x']
        out.append((table[n], bytes(new), olds[n], f'window {n:02X}'))
    for (addr, op, size, before, note), (_, _, _, after, _) in zip(message_sites(base['x'], base['y']),
                                                                  message_sites(want['x'], base['y'])):
        long = op == 0x9F
        old = read(rom, addr, 1 + size + long)
        if old[0] != op or int.from_bytes(old[1:1 + size], 'little') != before or long and old[-1] != 0x7E:
            raise ValueError(f'{addr >> 16:02X}:{addr & 0xFFFF:04X}: {note} 코드가 원래 꼴이 아님')
        if after != before:
            out.append((addr + 1, after.to_bytes(size, 'little'), old[1:1 + size], f'message window: {note}'))
    return out


def dump(rom):
    out = []
    for n, addr in records(rom).items():
        raw = read(rom, addr, 4)
        if not raw[0] & 0x80:
            out.append({'index': f'{n:02X}', **header(raw)})
    return {'format': FORMAT, 'windows': out}


def edits(rom, doc):
    fields(doc, {'format', 'windows'}, '문서')
    if doc.get('format') != FORMAT or not isinstance(doc.get('windows'), list):
        raise ValueError(f'format={FORMAT}과 windows 배열이 필요함')
    table = records(rom)
    sharing = {}
    for n, addr in table.items():
        sharing.setdefault(addr, []).append(n)
    out, seen, pair = [], set(), {}
    for row in doc['windows']:
        fields(row, {'index', *FIELDS}, '창')
        text = row.get('index')
        n = int(text, 16) if isinstance(text, str) and re.fullmatch(r'[0-9A-Fa-f]{2}', text) else None
        if n not in table or n in seen:
            raise ValueError(f'index {text!r}: 중복 없는 창 번호(16진 두 자리, 00~{len(table) - 1:02X})여야 함')
        seen.add(n)
        if n in MESSAGES:
            pair[n] = row
            continue
        addr = table[n]
        old = read(rom, addr, 4)
        if old[0] & 0x80:
            raise ValueError(f'창 {n:02X}: 다른 창을 가리키는 레코드라 고칠 수 없음')
        new = bytearray(old)
        for key, (at, mask) in FIELDS.items():
            if key in row:
                new[at] = new[at] & ~mask & 0xFF | integer(row[key], mask, f'창 {n:02X} {key}')
        h = header(new)
        height = (PARTY_HEIGHT if new[0] & 0x20 else MENU_HEIGHT) if new[0] & 0x40 else h['h']
        # bit6 창이 원래 Y 보다 내려가지 않으면 원본 자리에서 그려지던 높이 그대로라 최악 높이로 막지 않는다.
        if new[0] & 0x40 and h['y'] <= header(old)['y']:
            height = 0
        # 원본에도 높이 1 인 창(28·8F)이 있어, 너비·높이 하한은 문서가 적은 필드에만 건다.
        if new != old and (h['x'] + h['w'] > MAP_W or h['y'] + height > MAP_W
                           or any(k in row and h[k] < 2 for k in ('w', 'h'))):
            raise ValueError(f'창 {n:02X}: BG3 타일맵 32 × 32 밖이거나 고친 너비·높이가 2 미만임')
        if new != old and len(sharing[addr]) > 1:
            names = '·'.join(f'{m:02X}' for m in sharing[addr])
            raise ValueError(f'창 {n:02X}: 레코드 {addr >> 16:02X}:{addr & 0xFFFF:04X} 를 {names} 가 함께 써 따로 고칠 수 없음')
        if old[0] & 0x40 and new[3] != old[3]:
            raise ValueError(f'창 {n:02X}: +0 bit6 창은 높이를 04:9FD3 이 일행에 맞춰 정해 h 를 받지 않음')
        out.append((addr, bytes(new), old, f'window {n:02X}'))
    if pair:
        out += message_edits(rom, table, sharing, pair)
    return out


def patch(rom, doc, name='windows'):
    return {'format': 'dq5patch/1', 'name': name, 'writes': [
        {'at': f'{a >> 16:02X}:{a & 0xFFFF:04X}', 'hex': new.hex(' '), 'orig': old.hex(' '), 'note': note}
        for a, new, old, note in edits(rom, doc) if new != old]}


def check(rom):
    doc = dump(rom)
    changed = sum(new != old for _, new, old, _ in edits(rom, doc))
    print(f'창 {len(doc["windows"])}개: 다른 쓰기 {changed}개')
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
    write.add_argument('--name', default='windows')
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
                result = patch(rom, json.load(f), args.name)
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
