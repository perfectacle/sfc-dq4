"""DQ5 보행 메시지 3,200개를 코드 목록으로 내보내고 허프만 트리와 함께 다시 넣는다.

형식은 sfc/dq5/docs/dq5-text-format.md. 24:9E02 디코더 사본과 트리는 한 뱅크에,
메시지는 뒤에 연속 배치한다. 24:AF1E의 21비트 주소에는 뱅크 20을 빼서 넣고
보행 호출 24:8BD6만 OR 20 색인 훅으로 돌린다. 전투 디코더·창·이름·글꼴은 바꾸지 않는다.

  python sfc/dq5/tools/dq5textwrite.py rom/dq5.sfc export -o work/messages.json
  python sfc/dq5/tools/dq5textwrite.py rom/dq5.sfc patch work/messages.json -o work/text.dq5patch.json
  python sfc/dq5/tools/dq5textwrite.py rom/dq5.sfc check

JSON: {"format":"dq5text/1", "messages":[{"id":297,"codes":[4102,0,4097]}]}.
messages에는 바꿀 항목만 넣을 수 있고, 빈 목록은 원본 전체를 다시 부호화한다.
codes는 정수 배열: 원래 글자 000~3DA, 제어 1000~101D·1100~1118(16진)만 지원한다.
끝 코드 1001·1010·1018은 반드시 마지막에 한 번만 둔다. 이름·숫자 변수의 인자는
부르는 코드가 대기열에 넣어야 한다. 새 글꼴·문자열 입력·전투 메시지·창·이름 표 편집은 지원하지 않는다.
--at 기본 38:8000. 30~3F만 지원하며 디코더·트리는 한 뱅크, 전체는 3F:FFFF 안에 있어야 한다.
생성하는 패치는 최소 2MB를 요구하며 다른 패치와 함께 3·4MB 롬으로 빌드할 수 있다.
"""
import argparse
from collections import Counter
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5hangul import (  # noqa: E402
    DECODER, DECODER_END, MASK_OPERAND, MESSAGES, NODES_0_OPERAND, NODES_1_OPERAND,
    ROOT_OPERAND, WALK_INDEX_CALL, WALK_INDEX_STUB, build_tree, cpu_to_bytes, decode_check, encode,
)
from dq5map import Rom, lorom  # noqa: E402
from dq5text import ENDS, GLYPHS, INDEX, NODES_0, NODES_1, ROOT  # noqa: E402

FORMAT = 'dq5text/1'
DATA_END = 0x200000
BANK = 0x8000


def keys(value, allowed, name):
    if not isinstance(value, dict) or value.keys() - allowed:
        raise ValueError(f'{name}: 허용한 필드 {sorted(allowed)}만 있는 JSON 객체여야 함')


def valid_message(codes):
    if not isinstance(codes, list) or not codes:
        raise ValueError('codes는 비어 있지 않은 정수 배열이어야 함')
    for c in codes:
        if type(c) is not int or not (0 <= c < GLYPHS or 0x1000 <= c <= 0x101D or 0x1100 <= c <= 0x1118):
            raise ValueError(f'지원하지 않는 글자·제어 코드: {c!r}')
    if codes[-1] not in ENDS or any(c in ENDS for c in codes[:-1]):
        raise ValueError('끝 코드 1001·1010·1018은 마지막에 한 번만 있어야 함')
    return codes


def overrides(original, doc):
    keys(doc, {'format', 'messages'}, '문서')
    if doc.get('format') != FORMAT or not isinstance(doc.get('messages'), list):
        raise ValueError(f'format={FORMAT}과 messages 배열이 필요함')
    messages = list(original)
    if len(messages) != MESSAGES:
        raise ValueError(f'원본 메시지는 {MESSAGES}개여야 함')
    seen = set()
    for row in doc['messages']:
        keys(row, {'id', 'codes'}, '메시지')
        index = row.get('id')
        if type(index) is not int or not 0 <= index < MESSAGES or index in seen:
            raise ValueError('id는 중복 없는 0~3199 정수여야 함')
        seen.add(index)
        messages[index] = valid_message(row.get('codes'))
    return messages


def parse_at(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-fA-F]{2}:[0-9a-fA-F]{4}', value):
        raise ValueError('--at은 BB:AAAA 형식이어야 함')
    bank, low = (int(v, 16) for v in value.split(':'))
    if not 0x30 <= bank <= 0x3F or not 0x8000 <= low <= 0xFFFF:
        raise ValueError('--at은 30~3F 뱅크의 8000~FFFF만 지원함')
    return bank << 16 | low


def decoder_code(data):
    code = bytearray(data[lorom(DECODER):lorom(DECODER_END)])
    if len(code) != DECODER_END - DECODER or code[:4] != bytes.fromhex('08 8b 4b ab') or code[-1] != 0x60:
        raise ValueError('원래 보행 디코더가 아님; 원본 롬으로 패치 목록을 만들어야 함')
    for at, op, expected in ((NODES_1_OPERAND, 0xBD, NODES_1 & 0xFFFF),
                             (NODES_0_OPERAND, 0xBD, NODES_0 & 0xFFFF),
                             (MASK_OPERAND, 0x39, 0x9E8C), (ROOT_OPERAND, 0xA2, ROOT)):
        off = at - DECODER
        if code[off - 1] != op or int.from_bytes(code[off:off + 2], 'little') != expected:
            raise ValueError('원래 허프만 디코더 피연산자가 아님')
    call = lorom(WALK_INDEX_CALL - 1)
    if data[call:call + 3] != bytes.fromhex('20 8d 8c'):
        raise ValueError('원래 보행 색인 호출이 아님')
    return code


def read_messages(data):
    decoder_code(data)
    try:
        messages = decode_check(data, decoder=DECODER, bank_mask=0)
    except IndexError:
        raise ValueError('메시지·트리 주소가 원본 롬 범위를 벗어남') from None
    for codes in messages:
        valid_message(codes)
    return messages


def export(data):
    return {'format': FORMAT, 'messages': [{'id': i, 'codes': codes} for i, codes in enumerate(read_messages(data))]}


def tree(messages):
    if len(messages) != MESSAGES:
        raise ValueError(f'메시지는 {MESSAGES}개여야 함')
    freq = Counter(c for codes in messages for c in valid_message(codes))
    if not freq:
        raise ValueError('빈 허프만 트리는 만들 수 없음')
    if len(freq) == 1:
        code = next(iter(freq))
        return {code: '0'}, [(0x8000 | code, 0x8000 | code)], 0
    return build_tree(freq)


def compile_messages(data, messages, at='38:8000', name='walk-text'):
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
    if len(nodes) > 0x2000 or (base & 0xFFFF) + head_size > 0x10000:
        raise ValueError('디코더·마스크·트리가 한 뱅크를 넘음')
    bits = sum(len(codes[c]) for message_codes in messages for c in message_codes)
    size = head_size + (bits + 7) // 8
    if start + size > DATA_END:
        raise ValueError('메시지가 색인 훅이 지원하는 3F 뱅크 끝을 넘음')
    for operand, target in ((MASK_OPERAND, mask_at), (NODES_1_OPERAND, t1_at), (NODES_0_OPERAND, t0_at)):
        code[operand - DECODER:operand - DECODER + 2] = (target & 0xFFFF).to_bytes(2, 'little')
    code[ROOT_OPERAND - DECODER:ROOT_OPERAND - DECODER + 2] = (root * 2).to_bytes(2, 'little')
    code[-1] = 0x6B
    head = code + mask + b''.join(n[0].to_bytes(2, 'little') for n in nodes) + \
        b''.join(n[1].to_bytes(2, 'little') for n in nodes)
    blob, starts = encode(codes, messages)
    stream = bytes(head + blob)
    index = bytearray()
    for m in range(0, MESSAGES, 16):
        bit = starts[m]
        off = start + head_size + (bit >> 3)
        cpu = (off // BANK) << 16 | 0x8000 | off % BANK
        value = ((cpu - 0x200000) << 3) | (bit & 7)
        if not 0 <= value < 1 << 24:
            raise ValueError('메시지 색인 24비트 범위 초과')
        index += cpu_to_bytes(value)
    writes = []
    pos = 0
    while pos < len(stream):
        off = start + pos
        part = stream[pos:pos + BANK - off % BANK]
        cpu = (off // BANK) << 16 | 0x8000 | off % BANK
        writes.append({'at': f'{cpu >> 16:02X}:{cpu & 0xFFFF:04X}', 'hex': part.hex(' '),
                       'note': '보행 디코더·허프만 트리·메시지'})
        pos += len(part)
    stub = bytes.fromhex('20 8d 8c a5 f2 09 20 85 f2 60')
    for addr, raw, note in ((INDEX, index, '보행 메시지 색인'),
                            (DECODER, bytes([0x22]) + cpu_to_bytes(base) + b'\x60', '보행 디코더 호출'),
                            (WALK_INDEX_STUB, stub, '보행 색인 뱅크 훅'),
                            (WALK_INDEX_CALL, (WALK_INDEX_STUB & 0xFFFF).to_bytes(2, 'little'), '보행 색인 호출')):
        off = lorom(addr)
        writes.append({'at': f'{addr >> 16:02X}:{addr & 0xFFFF:04X}', 'hex': raw.hex(' '),
                       'orig': data[off:off + len(raw)].hex(' '), 'note': note})
    return {'format': 'dq5patch/1', 'name': name, 'rom_size': 2, 'writes': writes}


def patch(data, doc, at='38:8000', name='walk-text'):
    return compile_messages(data, overrides(read_messages(data), doc), at, name)


def decoded_messages(data):
    rom = Rom(data)
    call = lorom(DECODER)
    if data[call] != 0x22 or data[call + 4] != 0x60:
        raise ValueError('새 보행 디코더 호출이 없음')
    stub = lorom(WALK_INDEX_STUB)
    if data[stub:stub + 10] != bytes.fromhex('20 8d 8c a5 f2 09 20 85 f2 60'):
        raise ValueError('지원하는 보행 색인 훅이 아님')
    try:
        return decode_check(data, decoder=rom.u24(DECODER + 1))
    except IndexError:
        raise ValueError('메시지·트리 주소가 롬 범위를 벗어남') from None


def check(data, doc, at):
    from dq5build import build, parse_at as patch_at
    messages = overrides(read_messages(data), doc)
    manifest = compile_messages(data, messages, at)
    writes = [(patch_at(w['at'])[0], bytes.fromhex(w['hex']), bytes.fromhex(w['orig']) if 'orig' in w else None,
               w['note']) for w in manifest['writes']]
    rebuilt, _ = build(data, [(manifest['name'], 2, writes)], 2)
    decoded = decoded_messages(rebuilt)
    different = sum(a != b for a, b in zip(messages, decoded))
    print(f'보행 메시지 {len(decoded)}개, 코드 {sum(map(len, messages))}개, 다른 메시지 {different}개')
    return bool(different or len(decoded) != MESSAGES)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('rom')
    subs = parser.add_subparsers(dest='command', required=True)
    out = subs.add_parser('export')
    out.add_argument('-o', '--out', required=True)
    write = subs.add_parser('patch')
    write.add_argument('source')
    write.add_argument('-o', '--out', required=True)
    write.add_argument('--at', default='38:8000')
    write.add_argument('--name', default='walk-text')
    verify = subs.add_parser('check')
    verify.add_argument('source', nargs='?')
    verify.add_argument('--at', default='38:8000')
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
