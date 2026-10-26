"""DQ5 이벤트 명령 JSON 인코더. 형식은 sfc/dq5/docs/dq5-event-format.md.

00:BEC3 명령 길이와 23:E2C2·23:E325 표를 쓴다. 지정한 표 항목만 바꾸며,
같은 주소를 가리키는 다른 항목이나 코드의 직접 참조는 바꾸지 않는다.

  dq5eventwrite.py rom/dq5.sfc dump --event 8 -o work/event.json
  dq5eventwrite.py rom/dq5.sfc dump --number 41 -o work/event.json
  dq5eventwrite.py rom/dq5.sfc dump 15F702
  dq5eventwrite.py rom/dq5.sfc encode work/event.json -o work/event.bin
  dq5eventwrite.py rom/dq5.sfc patch work/event.json -o work/event.dq5patch.json
  dq5eventwrite.py rom/dq5.sfc check

commands 는 {"op": "10", "args": [37, 16]} 꼴이다. op 는 두 자리 16진 문자열,
args 는 바이트 정수 배열이다. C3 는 args 대신 target(CPU 주소 정수 또는 라벨 이름)을
쓴다. 명령에 label 을 붙일 수 있다. 주소 인자는 바이트 순서 그대로(리틀 엔디언)다.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5build import PatchError, cpu, parse_at  # noqa: E402
from dq5event import EMPTY, EVENTS, EVENT_COUNT, NUMBERED, NUMBER_COUNT, OPS, all_scripts, all_starts  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402

FORMAT = 'dq5event/1'
BANK = 0x8000


def integer(value, maximum, name):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError(f'{name}: 0~{maximum} 정수여야 함')
    return value


def opcode(command):
    value = command.get('op')
    if not isinstance(value, str) or len(value) != 2 or any(c not in '0123456789abcdefABCDEF' for c in value):
        raise ValueError('op 는 두 자리 16진 문자열이어야 함')
    op = int(value, 16)
    if op >= 0x10 and op != 0xFF and op not in OPS:
        raise ValueError(f'모르는 명령 {op:02X}')
    return op


def length(op):
    return 2 if op < 0x10 else 1 if op == 0xFF else OPS[op][0]


def parse(rom, addr):
    """FF·C3 까지 엄격하게 읽는다. 메시지 본문은 내보내지 않는다."""
    integer(addr, 0xFFFFFF, '주소')
    start, is_cpu = parse_at(f'{addr >> 16:02X}:{addr & 0xFFFF:04X}')
    if not is_cpu or start >= len(rom.d):
        raise ValueError('스크립트 주소가 롬 밖')
    at, commands = start, []
    end = min(len(rom.d), (start // BANK + 1) * BANK)
    while at < end:
        op = rom.d[at]
        command = {'op': f'{op:02X}'}
        opcode(command)
        n = length(op)
        if at + n > end:
            raise ValueError(f'{cpu(at)}: 잘린 명령 또는 뱅크 경계')
        args = rom.d[at + 1:at + n]
        if op == 0xC3:
            command['target'] = int.from_bytes(args, 'little')
        else:
            command['args'] = list(args)
        commands.append(command)
        at += n
        if op in (0xFF, 0xC3):
            return {'format': FORMAT, 'address': addr, 'commands': commands}, at - start
    raise ValueError('뱅크 끝까지 종료 명령 FF·C3 가 없음')


def encode(doc, addr=None):
    """명령 라벨은 이 스크립트의 CPU 시작 주소를 기준으로 푼다."""
    if not isinstance(doc, dict) or doc.get('format') != FORMAT:
        raise ValueError(f'format 은 {FORMAT}')
    commands = doc.get('commands')
    if not isinstance(commands, list) or not commands:
        raise ValueError('commands 는 비어 있지 않은 배열이어야 함')
    labels, ops, size = {}, [], 0
    for command in commands:
        if not isinstance(command, dict):
            raise ValueError('명령은 객체여야 함')
        op = opcode(command)
        ops.append(op)
        if 'label' in command:
            label = command['label']
            if not isinstance(label, str) or not label or label in labels:
                raise ValueError('label 은 비어 있지 않은 고유 문자열이어야 함')
            labels[label] = size
        size += length(op)
    if ops[-1] not in (0xFF, 0xC3):
        raise ValueError('마지막 명령은 FF 또는 C3 여야 함')
    base = doc.get('address') if addr is None else addr
    if base is not None:
        integer(base, 0xFFFFFF, '주소')
        off, _ = parse_at(f'{base >> 16:02X}:{base & 0xFFFF:04X}')
        if off % BANK + size > BANK:
            raise ValueError('스크립트가 뱅크 경계를 넘음')
    elif size > BANK:
        raise ValueError('스크립트가 한 뱅크보다 큼')
    out = bytearray()
    for command, op in zip(commands, ops):
        out.append(op)
        if op == 0xC3:
            if 'args' in command or 'target' not in command:
                raise ValueError('C3 는 args 대신 target 을 써야 함')
            target = command['target']
            if isinstance(target, str):
                if target not in labels:
                    raise ValueError(f'없는 라벨 {target!r}')
                if base is None:
                    raise ValueError('라벨을 풀려면 address 또는 --at 이 필요함')
                target = base + labels[target]
            out.extend(integer(target, 0xFFFFFF, 'target').to_bytes(3, 'little'))
        else:
            if 'target' in command:
                raise ValueError('target 은 C3 만 쓸 수 있음')
            args = command.get('args', [])
            if not isinstance(args, list) or len(args) != length(op) - 1:
                raise ValueError(f'{op:02X}: args 는 {length(op) - 1}바이트여야 함')
            out.extend(integer(v, 255, 'args') for v in args)
    return bytes(out)


def patch(data, docs, at=0x608000, name='events'):
    """명시한 binding(event/number)만 새 스크립트에 연결한다."""
    integer(at, 0xFFFFFF, '주소')
    off, _ = parse_at(f'{at >> 16:02X}:{at & 0xFFFF:04X}')
    if off < len(data) or off >= 0x400000:
        raise ValueError('새 스크립트는 원본 롬 뒤의 확장 영역(최대 4MB)에 놓아야 함')
    writes, seen = [], set()
    if not docs:
        raise ValueError('패치할 스크립트가 없음')
    for doc in docs:
        if not isinstance(doc, dict):
            raise ValueError('스크립트 JSON은 객체여야 함')
        binding = doc.get('binding', {})
        if not isinstance(binding, dict) or binding.get('kind') not in ('event', 'number'):
            raise ValueError('binding.kind 는 event 또는 number 여야 함')
        kind = binding['kind']
        index = integer(binding.get('index'), EVENT_COUNT - 1 if kind == 'event' else NUMBER_COUNT - 1, 'index')
        key = kind, index
        if key in seen:
            raise ValueError(f'중복 표 항목 {kind} {index}')
        seen.add(key)
        # 먼저 뱅크 첫머리에서 인코딩해 길이를 구한 뒤 실제 배치 주소로 라벨을 푼다.
        size = len(encode(doc, 0x608000))
        if off % BANK + size > BANK:
            off = (off // BANK + 1) * BANK
        if off + size > 0x400000:
            raise ValueError('확장 롬 4MB 를 넘음')
        address = int(cpu(off).replace(':', ''), 16)
        raw = encode(doc, address)
        label = f'{kind} {index:02X}'
        writes.append({'at': cpu(off), 'hex': raw.hex(' '), 'note': label})
        site = lorom(EVENTS + index * 5 if kind == 'event' else NUMBERED + index * 3)
        if site + (5 if kind == 'event' else 3) > len(data):
            raise ValueError('원본 롬에 표 항목이 없음')
        value = address.to_bytes(3, 'little')
        if kind == 'event':
            x = integer(binding.get('x', data[site]), 255, 'x')
            y = integer(binding.get('y', data[site + 1]), 255, 'y')
            value = bytes((x, y)) + value
        writes.append({'at': cpu(site), 'hex': value.hex(' '), 'orig': data[site:site + len(value)].hex(' '),
                       'note': f'{label} 표 항목'})
        off += len(raw)
    return {'format': 'dq5patch/1', 'name': name, 'rom_size': 4 if off > 0x300000 else 3 if off > 0x200000 else 2,
            'writes': writes}


def check(rom):
    bad = 0
    groups = [('시작점', [a for _, a, _ in all_starts(rom)]), ('연속 영역', all_scripts(rom))]
    for name, starts in groups:
        total = 0
        for addr in starts:
            doc, n = parse(rom, addr)
            total += n
            if encode(doc) != rom.d[lorom(addr):lorom(addr) + n]:
                bad += 1
                print(f'{addr:06X}: 원본과 다름')
        print(f'{name} {len(starts)}개(고유 주소 {len(set(starts))}개), {total}바이트')
    print(f'다른 스크립트 {bad}개')
    return bool(bad)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom')
    ap.add_argument('cmd', choices=('dump', 'encode', 'check', 'patch'))
    ap.add_argument('files', nargs='*')
    selection = ap.add_mutually_exclusive_group()
    selection.add_argument('--event', type=int, choices=range(EVENT_COUNT))
    selection.add_argument('--number', type=lambda s: int(s, 16), choices=range(NUMBER_COUNT))
    ap.add_argument('-o', '--out')
    ap.add_argument('--at', help='CPU 주소 BB:AAAA. patch 기본값 60:8000')
    ap.add_argument('--name', default='events')
    a = ap.parse_args()
    try:
        data = open(a.rom, 'rb').read()
        rom = Rom(data)
        if a.cmd == 'check':
            return int(check(rom))
        address = None
        if a.at:
            off, _ = parse_at(a.at)
            if not 0 <= off < 0x400000:
                raise ValueError('--at 은 4MB 롬 범위여야 함')
            address = int(cpu(off).replace(':', ''), 16)
        if a.cmd == 'dump':
            binding = None
            if a.event is not None:
                site = EVENTS + a.event * 5
                addr = rom.u24(site + 2)
                binding = {'kind': 'event', 'index': a.event, 'x': rom.u8(site), 'y': rom.u8(site + 1)}
            elif a.number is not None:
                addr = rom.u24(NUMBERED + a.number * 3)
                if addr == EMPTY:
                    raise ValueError('이 번호는 스크립트가 아닌 빈 표 항목')
                binding = {'kind': 'number', 'index': a.number}
            elif len(a.files) == 1:
                addr = int(a.files[0].replace(':', ''), 16)
            else:
                raise ValueError('dump 에는 주소 하나 또는 --event/--number 가 필요함')
            doc, _ = parse(rom, addr)
            if binding:
                doc['binding'] = binding
        else:
            docs = [json.load(open(p, encoding='utf-8')) for p in a.files]
            if a.cmd == 'encode':
                if len(docs) != 1 or not a.out:
                    raise ValueError('encode 에는 JSON 하나와 -o 가 필요함')
                raw = encode(docs[0], address)
                os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True)
                with open(a.out, 'wb') as f:
                    f.write(raw)
                print(f'{len(raw)}바이트 → {a.out}')
                return 0
            if not a.out:
                raise ValueError('patch 에는 -o 가 필요함')
            doc = patch(data, docs, address if address is not None else 0x608000, a.name)
        result = json.dumps(doc, ensure_ascii=False, indent=2) + '\n'
        if a.out:
            os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True)
            with open(a.out, 'w', encoding='utf-8') as f:
                f.write(result)
            print(f'{a.cmd} → {a.out}')
        else:
            print(result, end='')
        return 0
    except (ValueError, PatchError, OSError, KeyError, TypeError) as e:
        print(f'오류: {e}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
