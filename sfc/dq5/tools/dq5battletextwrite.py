"""DQ5 전투 모드 메시지 432개를 1바이트 부호 목록으로 내보내고 허프만 트리와 함께 다시 넣는다.

형식은 sfc/dq5/docs/dq5-build-format.md 의 「전투 메시지 일괄 쓰기」. 24:9E47 전투 디코더 사본·마스크·트리는 --at 의
한 뱅크에, 메시지는 그 뒤에 연속 배치한다. 24:AECD 색인은 21비트 주소라 뱅크 1F 까지만 가리키므로, 비운 디코더 자리
24:9E4C 에 색인 풀기(24:8C8D) 뒤 뱅크에 (--at 뱅크 & E0)을 OR 하는 훅을 두고 전투 호출 24:8C60 만 그리로 돌린다.
보행 디코더·글꼴·창·이름 표는 바꾸지 않는다.

  python sfc/dq5/tools/dq5battletextwrite.py rom/dq5.sfc export -o work/battle.json
  python sfc/dq5/tools/dq5battletextwrite.py rom/dq5.sfc patch work/battle.json --at 3B:8000 -o work/battle.dq5patch.json
  python sfc/dq5/tools/dq5battletextwrite.py rom/dq5.sfc check work/battle.json --at 3B:8000

JSON: {"format":"dq5battletext/1", "messages":[{"id":94,"codes":[247,40,254]}]}.
messages 에는 바꿀 항목만 넣을 수 있고, 빈 목록은 원본 전체를 다시 부호화한다.
codes 는 0~255 정수 배열(이름 문자열과 같은 1바이트 부호, E2 이상은 24:86F2 처리기). 끝 부호 E7·EF·FE 는 마지막에
한 번만 둔다. 24:8C21 이 메시지마다 128바이트를 한 번에 풀어 두므로 끝 부호까지 128바이트를 넘지 못한다.
이름·숫자 부호(F7·FB 등)의 인자는 부르는 코드가 대기열에 넣어야 한다.
--at 은 반드시 준다. 30~7D 뱅크만 받으며, 디코더·트리는 한 뱅크, 메시지 끝은 (뱅크 & E0) + 1F 뱅크와 7D 안에 있어야 한다.
다른 도구가 같은 자리를 쓰면 빌더가 거부한다.
"""
import argparse
from collections import Counter
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5battletext import COUNT, ENDS, INDEX, NODES_0, NODES_1, ROOT  # noqa: E402
from dq5hangul import build_tree, cpu_to_bytes, encode  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402

FORMAT = 'dq5battletext/1'
DECODER = 0x249E47
DECODER_END = 0x249E8C                    # RTS(24:9E8B) 다음. 24:9E8C 마스크는 보행 디코더도 읽으므로 두고 사본에 따로 둔다
ROOT_OPERAND, MASK_OPERAND, NODES_1_OPERAND, NODES_0_OPERAND = 0x249E52, 0x249E5B, 0x249E62, 0x249E67
INDEX_CALL = 0x248C61                     # 24:8C60 JSR $8C8D 의 피연산자
STUB = 0x249E4C                           # JSL 사본 / RTS 뒤의 비운 자리
INDEX_ROUTINE = 0x8C8D
BUFFER = 128                              # 24:8C21 이 7E:0E4B 에 푸는 바이트 수
BANK = 0x8000
LAST_BANK = 0x7D


def keys(value, allowed, name):
    if not isinstance(value, dict) or value.keys() - allowed:
        raise ValueError(f'{name}: 허용한 필드 {sorted(allowed)}만 있는 JSON 객체여야 함')


def valid_message(codes):
    if not isinstance(codes, list) or not codes:
        raise ValueError('codes 는 비어 있지 않은 정수 배열이어야 함')
    for c in codes:
        if type(c) is not int or not 0 <= c <= 0xFF:
            raise ValueError(f'1바이트 부호가 아님: {c!r}')
    if codes[-1] not in ENDS or any(c in ENDS for c in codes[:-1]):
        raise ValueError('끝 부호 E7·EF·FE 는 마지막에 한 번만 있어야 함')
    if len(codes) > BUFFER:
        raise ValueError(f'메시지가 {BUFFER}바이트를 넘음({len(codes)})')
    return codes


def overrides(original, doc):
    keys(doc, {'format', 'messages'}, '문서')
    if doc.get('format') != FORMAT or not isinstance(doc.get('messages'), list):
        raise ValueError(f'format={FORMAT}과 messages 배열이 필요함')
    messages = list(original)
    if len(messages) != COUNT:
        raise ValueError(f'원본 메시지는 {COUNT}개여야 함')
    seen = set()
    for row in doc['messages']:
        keys(row, {'id', 'codes'}, '메시지')
        index = row.get('id')
        if type(index) is not int or not 0 <= index < COUNT or index in seen:
            raise ValueError(f'id 는 중복 없는 0~{COUNT - 1} 정수여야 함')
        seen.add(index)
        messages[index] = valid_message(row.get('codes'))
    return messages


def parse_at(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-fA-F]{2}:[0-9a-fA-F]{4}', value):
        raise ValueError('--at 은 BB:AAAA 형식이어야 함')
    bank, low = (int(v, 16) for v in value.split(':'))
    if not 0x30 <= bank <= LAST_BANK or not 0x8000 <= low <= 0xFFFF:
        raise ValueError('--at 은 30~7D 뱅크의 8000~FFFF 만 받음')
    return bank << 16 | low


def decoder_code(data):
    code = bytearray(data[lorom(DECODER):lorom(DECODER_END)])
    if len(code) != DECODER_END - DECODER or code[:4] != bytes.fromhex('08 8b 4b ab') or code[-1] != 0x60:
        raise ValueError('원래 전투 디코더가 아님; 원본 롬으로 패치 목록을 만들어야 함')
    for at, op, expected in ((ROOT_OPERAND, 0xA2, ROOT), (MASK_OPERAND, 0x39, 0x9E8C),
                             (NODES_1_OPERAND, 0xBD, NODES_1 & 0xFFFF), (NODES_0_OPERAND, 0xBD, NODES_0 & 0xFFFF)):
        off = at - DECODER
        if code[off - 1] != op or int.from_bytes(code[off:off + 2], 'little') != expected:
            raise ValueError('원래 전투 허프만 디코더 피연산자가 아님')
    call = lorom(INDEX_CALL - 1)
    if data[call:call + 3] != bytes((0x20, INDEX_ROUTINE & 0xFF, INDEX_ROUTINE >> 8)):
        raise ValueError('원래 전투 색인 호출이 아님')
    return code


def decode(data, decoder, bank_or):
    """디코더(decoder)의 트리 피연산자와 24:AECD 색인을 따라 432개를 푼다. bank_or 는 색인 주소 뱅크에 OR 하는 값."""
    rom = Rom(data)
    bank = decoder & 0xFF0000
    t1 = bank | rom.u16(decoder + NODES_1_OPERAND - DECODER)
    t0 = bank | rom.u16(decoder + NODES_0_OPERAND - DECODER)
    root = rom.u16(decoder + ROOT_OPERAND - DECODER)
    out, budget = [], len(data) * 8
    try:
        for g in range(COUNT // 16):
            v = rom.u24(INDEX + g * 3)
            addr, bit = (v >> 3) | bank_or << 16, v & 7
            for _ in range(16):
                msg = []
                while True:
                    x, seen = root, set()
                    while True:
                        if x in seen or budget <= 0:
                            raise ValueError('허프만 트리 순환 또는 메시지 비트 한계 초과')
                        seen.add(x)
                        budget -= 1
                        b = (rom.u8(addr) >> bit) & 1
                        bit += 1
                        if bit == 8:
                            bit = 0
                            addr += 1
                            if addr & 0xFFFF == 0:
                                addr |= 0x8000
                        val = rom.u16((t1 if b else t0) + x)
                        if val & 0x8000:
                            break
                        x = (val & 0xFF) * 2
                    msg.append(val & 0xFF)
                    if msg[-1] in ENDS:
                        break
                out.append(msg)
    except IndexError:
        raise ValueError('메시지·트리 주소가 롬 범위를 벗어남') from None
    return out


def read_messages(data):
    decoder_code(data)
    messages = decode(data, DECODER, 0)
    for codes in messages:
        valid_message(codes)
    return messages


def export(data):
    return {'format': FORMAT, 'messages': [{'id': i, 'codes': codes} for i, codes in enumerate(read_messages(data))]}


def tree(messages):
    if len(messages) != COUNT:
        raise ValueError(f'메시지는 {COUNT}개여야 함')
    freq = Counter(c for codes in messages for c in valid_message(codes))
    if len(freq) == 1:
        code = next(iter(freq))
        return {code: '0'}, [(0x8000 | code, 0x8000 | code)], 0
    return build_tree(freq)


def cpu_of(off):
    return (off // BANK) << 16 | 0x8000 | off % BANK


def compile_messages(data, messages, at, name='battle-text'):
    base = parse_at(at)
    start = lorom(base)
    if start < len(data):
        raise ValueError('메시지 배치가 입력 롬과 겹침; 원본 롬과 확장 뱅크를 사용해야 함')
    code = decoder_code(data)
    codes, nodes, root = tree(messages)
    mask = bytes(1 << i for i in range(8))
    mask_at = base + len(code)
    t1_at = mask_at + len(mask)
    t0_at = t1_at + len(nodes) * 2
    head_size = len(code) + len(mask) + len(nodes) * 4
    if (base & 0xFFFF) + head_size > 0x10000:
        raise ValueError('디코더·마스크·트리가 한 뱅크를 넘음')
    bank_or = (base >> 16) & 0xE0
    bits = sum(len(codes[c]) for message_codes in messages for c in message_codes)
    end_bank = cpu_of(start + head_size + (bits + 7) // 8 - 1) >> 16
    if end_bank > min(bank_or | 0x1F, LAST_BANK):
        raise ValueError(f'메시지가 색인 훅이 닿는 뱅크 {min(bank_or | 0x1F, LAST_BANK):02X} 끝을 넘음')
    for operand, target in ((MASK_OPERAND, mask_at), (NODES_1_OPERAND, t1_at), (NODES_0_OPERAND, t0_at)):
        code[operand - DECODER:operand - DECODER + 2] = (target & 0xFFFF).to_bytes(2, 'little')
    code[ROOT_OPERAND - DECODER:ROOT_OPERAND - DECODER + 2] = (root * 2).to_bytes(2, 'little')
    code[-1] = 0x6B
    head = code + mask + b''.join(n[0].to_bytes(2, 'little') for n in nodes) + \
        b''.join(n[1].to_bytes(2, 'little') for n in nodes)
    blob, starts = encode(codes, messages)
    stream = bytes(head + blob)
    index = bytearray()
    for m in range(0, COUNT, 16):
        bit = starts[m]
        cpu = cpu_of(start + head_size + (bit >> 3))
        index += cpu_to_bytes(((cpu - (bank_or << 16)) << 3) | (bit & 7))
    writes = []
    pos = 0
    while pos < len(stream):
        off = start + pos
        part = stream[pos:pos + BANK - off % BANK]
        cpu = cpu_of(off)
        writes.append({'at': f'{cpu >> 16:02X}:{cpu & 0xFFFF:04X}', 'hex': part.hex(' '),
                       'note': '전투 디코더·허프만 트리·메시지'})
        pos += len(part)
    stub = bytes((0x20, INDEX_ROUTINE & 0xFF, INDEX_ROUTINE >> 8, 0xA5, 0xF2, 0x09, bank_or, 0x85, 0xF2, 0x60))
    for addr, raw, note in ((INDEX, index, '전투 메시지 색인'),
                            (DECODER, bytes([0x22]) + cpu_to_bytes(base) + b'\x60', '전투 디코더 호출'),
                            (STUB, stub, '전투 색인 뱅크 훅'),
                            (INDEX_CALL, (STUB & 0xFFFF).to_bytes(2, 'little'), '전투 색인 호출')):
        off = lorom(addr)
        writes.append({'at': f'{addr >> 16:02X}:{addr & 0xFFFF:04X}', 'hex': raw.hex(' '),
                       'orig': data[off:off + len(raw)].hex(' '), 'note': note})
    end = start + len(stream)
    return {'format': 'dq5patch/1', 'name': name, 'rom_size': max(2, -(-end // 0x100000)), 'writes': writes}


def patch(data, doc, at, name='battle-text'):
    return compile_messages(data, overrides(read_messages(data), doc), at, name)


def decoded_messages(data):
    rom = Rom(data)
    call = lorom(DECODER)
    if data[call] != 0x22 or data[call + 4] != 0x60:
        raise ValueError('새 전투 디코더 호출이 없음')
    stub = data[lorom(STUB):lorom(STUB) + 10]
    if rom.u16(INDEX_CALL) != STUB & 0xFFFF or stub[:6] != bytes.fromhex('20 8d 8c a5 f2 09') or \
            stub[7:] != bytes.fromhex('85 f2 60'):
        raise ValueError('지원하는 전투 색인 훅이 아님')
    return decode(data, rom.u24(DECODER + 1), stub[6])


def copy_errors(original, rebuilt):
    """새 디코더 사본이 원래 24:9E47~9E8B 와 피연산자 넷·끝 RTL 만 다르고, 마스크가 01~80 인지 본다."""
    rom = Rom(rebuilt)
    base = rom.u24(DECODER + 1)
    size = DECODER_END - DECODER
    orig = original[lorom(DECODER):lorom(DECODER_END)]
    copy = rebuilt[lorom(base):lorom(base) + size]
    operands = set()
    for at in (ROOT_OPERAND, MASK_OPERAND, NODES_1_OPERAND, NODES_0_OPERAND):
        operands.update((at - DECODER, at - DECODER + 1))
    errors = [f'{DECODER + i:06X}' for i in range(size - 1) if i not in operands and copy[i] != orig[i]]
    if copy[-1] != 0x6B:
        errors.append('끝 RTL')
    mask = (base & 0xFF0000) | rom.u16(base + MASK_OPERAND - DECODER)
    if bytes(rom.u8(mask + i) for i in range(8)) != bytes(1 << i for i in range(8)):
        errors.append('마스크')
    return errors


def check(data, doc, at):
    from dq5build import PatchError, build, parse_at as patch_at
    messages = overrides(read_messages(data), doc)
    manifest = compile_messages(data, messages, at)
    writes = [(patch_at(w['at'])[0], bytes.fromhex(w['hex']), bytes.fromhex(w['orig']) if 'orig' in w else None,
               w['note']) for w in manifest['writes']]
    try:
        rebuilt, _ = build(data, [(manifest['name'], manifest['rom_size'], writes)], manifest['rom_size'])
    except PatchError as error:
        raise ValueError(str(error)) from None
    decoded = decoded_messages(rebuilt)
    different = sum(a != b for a, b in zip(messages, decoded))
    errors = copy_errors(data, rebuilt)
    print(f'전투 메시지 {len(decoded)}개, 부호 {sum(map(len, messages))}개, 다른 메시지 {different}개, '
          f'디코더 사본 오류 {errors or 0}')
    return bool(different or errors or len(decoded) != COUNT)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('rom')
    subs = parser.add_subparsers(dest='command', required=True)
    out = subs.add_parser('export')
    out.add_argument('-o', '--out', required=True)
    write = subs.add_parser('patch')
    write.add_argument('source')
    write.add_argument('-o', '--out', required=True)
    write.add_argument('--at', required=True)
    write.add_argument('--name', default='battle-text')
    verify = subs.add_parser('check')
    verify.add_argument('source', nargs='?')
    verify.add_argument('--at', required=True)
    args = parser.parse_args()
    try:
        with open(args.rom, 'rb') as f:
            data = f.read()
        if args.command == 'export':
            result = export(data)
        else:
            doc = {'format': FORMAT, 'messages': []}
            if args.source:
                with open(args.source, encoding='utf-8') as f:
                    doc = json.load(f)
            if args.command == 'check':
                return int(check(data, doc, args.at))
            result = patch(data, doc, args.at, args.name)
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
