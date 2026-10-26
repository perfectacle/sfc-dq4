"""DQ5 인물 인라인 스크립트 쓰기(01:C800·12:8093).

형식: sfc/dq5/docs/dq5-map-format.md 「인라인 스크립트」.
명령은 {"op": "2B", "args": [5, 13]}, 상대 분기는 {"op": "03", "target": "start"}.
명령에 "label"을 붙일 수 있다. 06·07의 target은 마지막 변위 인자를 대신한다.
04 절대 점프는 원시 인자를 보존하며 재배치하지 않는다.

  python sfc/dq5/tools/dq5npcwrite.py rom/dq5.sfc dump 05:A84F -o work/npc.json
  python sfc/dq5/tools/dq5npcwrite.py rom/dq5.sfc encode work/npc.json -o work/npc.bin
  python sfc/dq5/tools/dq5npcwrite.py rom/dq5.sfc patch work/npc.json -o work/npc.dq5patch.json
  python sfc/dq5/tools/dq5npcwrite.py rom/dq5.sfc check

address는 첫 명령이 아닌 길이 바이트 주소다. patch는 그 길이를 유지하며 남는 바이트를
00(그 자리)으로 채운다. 낮·밤 공유 슬롯은 양쪽이 함께 바뀐다. encode 출력은 길이 없는 명령 본문이다.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5map import Rom  # noqa: E402
from dq5npc import (  # noqa: E402
    SCRIPT_OPS, SCRIPT_STOPS, all_lists, list_entries, s8,
    script_address, script_bytes, script_ops,
)

FORMAT = 'dq5npcscript/1'
RELATIVE = {0x03, 0x06, 0x07}


def byte(value):
    if type(value) is not int or not 0 <= value <= 255:
        raise ValueError(f'바이트는 0~255 정수여야 함: {value!r}')
    return value


def address(value):
    if not isinstance(value, str):
        raise ValueError('주소는 BB:AAAA 문자열이어야 함')
    try:
        bank, low = value.split(':')
        result = int(bank, 16) << 16 | int(low, 16)
        if len(bank) != 2 or len(low) != 4 or not 0 <= int(bank, 16) <= 0x3F or not 0x8000 <= int(low, 16) <= 0xFFFF:
            raise ValueError()
    except ValueError:
        raise ValueError(f'잘못된 LoROM 주소: {value}') from None
    return result


def cpu(value):
    return f'{value >> 16:02X}:{value & 0xFFFF:04X}'


def slots(rom):
    """길이 바이트 주소마다 그 슬롯을 쓰는 인물·시간대를 모은다."""
    result = {}
    for start, name in all_lists(rom):
        for entry, _ in list_entries(rom, start):
            for night in (False, True):
                a = script_address(rom, entry, night)
                # 한 벌 엔트리는 script_address가 반대 시간대에도 같은 주소를 돌려준다.
                flags = rom.u8(entry) & 0xC0
                if a is None or flags != 0xC0 and flags != (0x40 if night else 0x80):
                    continue
                result.setdefault(a, []).append({'entry': cpu(entry), 'map': name, 'time': 'night' if night else 'day'})
    return result


def branch_target(offset, raw):
    return offset + (1 if raw[0] == 0x03 else 0) + s8(raw[-1])


def dump_script(rom, at, references=None):
    code = script_bytes(rom, at)
    ops = script_ops(code)
    labels = {branch_target(off, raw) for off, raw, _ in ops if raw[0] in RELATIVE}
    commands = []
    for off, raw, _ in ops:
        item = {'op': f'{raw[0]:02X}', 'args': list(raw[1:])}
        if off in labels:
            item['label'] = f'L{off:02X}'
        if raw[0] in RELATIVE:
            item['args'] = list(raw[1:-1])
            item['target'] = f'L{branch_target(off, raw):02X}'
        commands.append(item)
    doc = {'format': FORMAT, 'address': cpu(at), 'length': len(code), 'commands': commands}
    if references is not None:
        doc['references'] = references
    return doc


def encode(doc):
    if not isinstance(doc, dict) or doc.get('format') != FORMAT:
        raise ValueError(f'format은 {FORMAT}이어야 함')
    commands = doc.get('commands')
    if not isinstance(commands, list) or not commands:
        raise ValueError('commands는 비어 있지 않은 목록이어야 함')
    labels, rows, offset = {}, [], 0
    for item in commands:
        if not isinstance(item, dict) or set(item) - {'op', 'args', 'label', 'target'}:
            raise ValueError(f'잘못된 명령: {item!r}')
        op = item.get('op')
        if not isinstance(op, str) or len(op) != 2 or any(c not in '0123456789abcdefABCDEF' for c in op):
            raise ValueError('op은 두 자리 16진 문자열이어야 함')
        try:
            op = byte(int(op, 16))
        except ValueError:
            raise ValueError(f'잘못된 op: {op!r}') from None
        n = 2 if op & 0x80 else SCRIPT_OPS.get(op, (None, None))[0]
        if n is None:
            raise ValueError(f'모르는 명령: {op:02X}')
        args = item.get('args', [])
        if not isinstance(args, list):
            raise ValueError('args는 바이트 목록이어야 함')
        args = [byte(v) for v in args]
        target = item.get('target')
        if 'target' in item and (op not in RELATIVE or not isinstance(target, str) or not target):
            raise ValueError('target은 상대 분기의 라벨 이름이어야 함')
        if len(args) != n - 1 - (target is not None):
            raise ValueError(f'{op:02X}: 인자 길이가 맞지 않음')
        if 'label' in item:
            label = item['label']
            if not isinstance(label, str) or not label or label in labels:
                raise ValueError(f'비었거나 중복된 label: {label!r}')
            labels[label] = offset
        rows.append((offset, op, args, target))
        offset += n
    if offset > 255:
        raise ValueError(f'스크립트 {offset}바이트가 길이 바이트 한계 255를 넘음')
    code = bytearray()
    for off, op, args, target in rows:
        if target is not None:
            if target not in labels:
                raise ValueError(f'정의되지 않은 라벨: {target}')
            delta = labels[target] - off - (1 if op == 0x03 else 0)
            if not -128 <= delta <= 127:
                raise ValueError(f'{target}: 상대 변위 {delta}가 -128~127 밖')
            args = args + [delta & 255]
        code.extend([op, *args])
    ops = script_ops(code)
    starts = {off for off, _, _ in ops}
    for off, raw, _ in ops:
        if raw[0] in RELATIVE and branch_target(off, raw) not in starts:
            raise ValueError(f'+{off:02X}: 상대 분기가 명령 경계 밖을 가리킴')
    return bytes(code)


def validate_flow(code, start):
    """바뀐 슬롯의 도달 가능한 흐름이 끝을 넘어 읽지 않는지 검사한다."""
    ops = {off: raw for off, raw, _ in script_ops(code)}
    pending, visited = [0], set()
    while pending:
        off = pending.pop()
        if off in visited:
            continue
        if off not in ops:
            raise ValueError(f'+{off:02X}: 스크립트 끝 또는 명령 중간으로 흐름이 이어짐')
        visited.add(off)
        raw = ops[off]
        op = raw[0]
        if op in RELATIVE:
            pending.append(branch_target(off, raw))
        if op == 0x04:
            dest = raw[1] | raw[2] << 8
            relative = dest - (start & 0xFFFF)
            if 0 <= relative < len(code):
                pending.append(relative)
            # 외부 절대 점프는 원시 주소 계약을 유지한다.
        if op not in SCRIPT_STOPS:
            pending.append(off + len(raw))


def patch(rom, doc, name='npc-script'):
    if not isinstance(doc, dict):
        raise ValueError('스크립트 JSON은 객체여야 함')
    at = address(doc.get('address'))
    known = slots(rom)
    if at not in known:
        raise ValueError(f'{cpu(at)}는 원본 인물 스크립트 길이 바이트가 아님')
    original = script_bytes(rom, at)
    if type(doc.get('length')) is not int or doc['length'] != len(original):
        raise ValueError('length가 원본 슬롯 길이와 다름')
    code = encode(doc)
    if len(code) > len(original):
        raise ValueError(f'스크립트 {len(code)}바이트가 원본 슬롯 {len(original)}바이트를 넘음')
    if (at & 0xFFFF) + len(original) > 0xFFFF:
        raise ValueError('인물 스크립트 슬롯이 뱅크 경계를 넘음')
    padded = code + bytes(len(original) - len(code))
    if padded != original:
        validate_flow(padded, at + 1)
    data = bytes([len(original)]) + padded
    orig = bytes([len(original)]) + original
    return {'format': 'dq5patch/1', 'name': name, 'writes': [
        {'at': cpu(at), 'hex': data.hex(' '), 'orig': orig.hex(' '),
         'note': f'인물 스크립트 슬롯 유지, 참조 {len(known[at])}개'}]}, known[at]


def check(rom):
    known = slots(rom)
    count, size = 0, 0
    for at in known:
        original = script_bytes(rom, at)
        if encode(dump_script(rom, at)) != original:
            raise ValueError(f'{cpu(at)}: 왕복 바이트 불일치')
        count += 1
        size += len(original)
    print(f'고유 스크립트 {count}개, {size}바이트 왕복 일치; 시간대 참조 {sum(map(len, known.values()))}개')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rom')
    sub = parser.add_subparsers(dest='command', required=True)
    for verb in ('dump', 'encode', 'patch'):
        part = sub.add_parser(verb)
        part.add_argument('source')
        part.add_argument('-o', '--out', required=True)
        if verb == 'patch':
            part.add_argument('--name', default='npc-script')
    sub.add_parser('check')
    args = parser.parse_args()
    try:
        if args.command == 'encode':
            with open(args.source, encoding='utf-8') as f:
                result = encode(json.load(f))
        else:
            rom = Rom(open(args.rom, 'rb').read())
            if args.command == 'check':
                check(rom)
                return 0
            if args.command == 'dump':
                at = address(args.source)
                known = slots(rom)
                if at not in known:
                    raise ValueError('원본 인물 스크립트 슬롯 주소가 아님')
                result = dump_script(rom, at, known[at])
            else:
                with open(args.source, encoding='utf-8') as f:
                    result, refs = patch(rom, json.load(f), args.name)
                print('참조: ' + ', '.join(f'{r["entry"]} {r["time"]}' for r in refs))
        os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
        if isinstance(result, bytes):
            with open(args.out, 'wb') as f:
                f.write(result)
        else:
            with open(args.out, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
                f.write('\n')
        print(f'{args.command} → {args.out}')
        return 0
    except (ValueError, OSError, IndexError) as error:
        print(f'오류: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
