"""DQ5 보행 메시지 3,200개를 코드 목록으로 내보내고 허프만 트리와 함께 다시 넣는다. 3200 이상 번호를 덧붙일 수 있다.

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
--at 기본 38:8000. 30~3F(색인 훅 OR 20) 또는 60~7D(OR 60, 4MB)를 받는다. 디코더·트리는 한 뱅크,
전체는 같은 창의 끝(3F:FFFF 또는 7D:FFFF) 안에 있어야 한다.
--base 롬은 이미 보행 메시지를 옮긴 롬(DQ4 메뉴 빌드 등)이다. 그 롬의 디코더·색인으로 메시지를 읽어 고친 것만
바꾸고, 그 롬의 글자 묶음 표(늘린 한글 글자 포함)를 새 머리에 옮겨 표 피연산자도 고친다. 패치는 여전히
원래 롬 기준(orig)이며, 옛 메시지 묶음과 같은 원본 자리 쓰기를 대신한다(sfc/dq5/docs/dq5-build-format.md).
id 가 지금 끝(원본은 3200) 이상이면 빈 번호 없이 이어 덧붙이고, 16개 묶음 끝까지 {1001} 한 코드 메시지로 채운다.
최대 id 는 1FFF(8191). 덧붙이면 색인 표를 머리(트리 뒤, 글자 묶음 표 앞)로 옮기고 24:8BC3 의 색인 읽기
뱅크·주소를 고친다. 3,200개만이면 쓰기는 예전과 같다.
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
from dq5text import ENDS, FONT_GROUPS, FONT_TABLE_OPERANDS, GLYPHS, INDEX, NODES_0, NODES_1, ROOT  # noqa: E402

FORMAT = 'dq5text/1'
BANK = 0x8000
# 24:8BAF 는 번호를 16비트로 받아 (번호 >> 4) * 3 을 X 로 이 코드의 표를 읽는다. 표를 옮길 때 뱅크와 세 주소만 바꾼다.
INDEX_LOAD = 0x248BC3
INDEX_LOAD_CODE = bytes.fromhex('a9 24 48 ab bd 1e af 85 00 bd 1f af 85 01 bd 20 af')
# 대화 스크립트 메시지 명령(06:B070)의 bit5 갈래가 v & 1FFF 라 이 수까지 받는다.
MAX_MESSAGES = 0x2000
PAD = [0x1001]
# 색인은 21비트라 훅이 뱅크 바이트에 창의 첫 뱅크를 OR 한다. 디코더 사본은 PHK·PLB 로 자기 뱅크만 읽으므로
# 낮은 WRAM 거울이 없는 60~ 에서도 돈다(DQ4 메뉴가 65:8000 에서 실측). 7E·7F 는 WRAM 이라 7D 까지.
WINDOWS = {0x20: (0x30, 0x3F), 0x60: (0x60, 0x7D)}


def keys(value, allowed, name):
    if not isinstance(value, dict) or value.keys() - allowed:
        raise ValueError(f'{name}: 허용한 필드 {sorted(allowed)}만 있는 JSON 객체여야 함')


def valid_message(codes, glyphs=GLYPHS, controls=()):
    if not isinstance(codes, list) or not codes:
        raise ValueError('codes는 비어 있지 않은 정수 배열이어야 함')
    for c in codes:
        if type(c) is not int or not (0 <= c < glyphs or 0x1000 <= c <= 0x101D or 0x1100 <= c <= 0x1118
                                      or c in controls):
            raise ValueError(f'지원하지 않는 글자·제어 코드: {c!r}')
    if codes[-1] not in ENDS or any(c in ENDS for c in codes[:-1]):
        raise ValueError('끝 코드 1001·1010·1018은 마지막에 한 번만 있어야 함')
    return codes


def overrides(original, doc, glyphs=GLYPHS, controls=()):
    keys(doc, {'format', 'messages'}, '문서')
    if doc.get('format') != FORMAT or not isinstance(doc.get('messages'), list):
        raise ValueError(f'format={FORMAT}과 messages 배열이 필요함')
    messages = list(original)
    count(messages)
    rows = {}
    for row in doc['messages']:
        keys(row, {'id', 'codes'}, '메시지')
        index = row.get('id')
        if type(index) is not int or not 0 <= index < MAX_MESSAGES or index in rows:
            raise ValueError(f'id는 중복 없는 0~{MAX_MESSAGES - 1} 정수여야 함')
        rows[index] = row.get('codes')
    added = sorted(i for i in rows if i >= len(messages))
    if added != list(range(len(messages), len(messages) + len(added))):
        raise ValueError(f'{len(messages)} 이상 id 는 {len(messages)} 부터 빈 번호 없이 이어져야 함')
    messages += [None] * len(added)
    for index, codes in rows.items():
        messages[index] = valid_message(codes, glyphs, controls)
    return messages + [PAD] * (-len(messages) % 16)


def count(messages):
    """메시지 수를 검사해 덧붙였는지(3,200개 초과) 돌려준다."""
    if not MESSAGES <= len(messages) <= MAX_MESSAGES or len(messages) % 16:
        raise ValueError(f'메시지는 {MESSAGES}~{MAX_MESSAGES}개, 16의 배수여야 함')
    return len(messages) > MESSAGES


def parse_at(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-fA-F]{2}:[0-9a-fA-F]{4}', value):
        raise ValueError('--at은 BB:AAAA 형식이어야 함')
    bank, low = (int(v, 16) for v in value.split(':'))
    if window(bank) is None or not 0x8000 <= low <= 0xFFFF:
        raise ValueError('--at은 30~3F 또는 60~7D 뱅크의 8000~FFFF만 지원함')
    return bank << 16 | low


def window(bank):
    """뱅크가 든 색인 창의 OR 값. 창 밖이면 None."""
    return next((w for w, (lo, hi) in WINDOWS.items() if lo <= bank <= hi), None)


def window_end(bank):
    """창의 마지막 뱅크 다음 파일 위치."""
    return lorom(WINDOWS[window(bank)][1] << 16 | 0xFFFF) + 1


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


def index_table(data, mask):
    """보행 색인 표의 (CPU 주소, 메시지 수). 24:8BC3 이 원래 코드면 24:AF1E 의 3,200개다. 옮긴 표는 머리 끝의
    글자 묶음 표(옮기지 않았으면 메시지 0) 바로 앞에서 끝나므로 그 사이를 세 바이트씩 센다.
    색인이 디코더와 다른 뱅크에 따로 있으면(DQ4 메뉴의 59:8000) 끝을 알려 주는 자료가 뒤에 없으므로,
    항목이 앞으로 가는 동안을 센다."""
    rom = Rom(data)
    at = lorom(INDEX_LOAD)
    code = data[at:at + len(INDEX_LOAD_CODE)]
    if code == INDEX_LOAD_CODE:
        return INDEX, MESSAGES
    index = code[1] << 16 | rom.u16(INDEX_LOAD + 5)
    expected = bytearray(INDEX_LOAD_CODE)
    expected[1] = code[1]
    for k, off in enumerate((5, 10, 15)):
        expected[off:off + 2] = ((index & 0xFFFF) + k).to_bytes(2, 'little')
    if code != expected:
        raise ValueError('지원하는 보행 색인 읽기 코드(24:8BC3)가 아님')
    if index >> 16 != rom.u24(DECODER + 1) >> 16:
        groups = contiguous_groups(data, index, mask, separate_index_groups(rom, index))
        if not MESSAGES < groups * 16 <= MAX_MESSAGES:
            raise ValueError('따로 둔 보행 색인 표의 끝을 찾지 못함')
        return index, groups * 16
    end = lorom((rom.u24(index) >> 3) | mask << 16)
    table = lorom(rom.u24(FONT_TABLE_OPERANDS[0][0]))
    if lorom(index) < table < end:
        end = table
    size = end - lorom(index)
    if size % 3 or not MESSAGES < size // 3 * 16 <= MAX_MESSAGES:
        raise ValueError('옮긴 보행 색인 표의 끝을 찾지 못함')
    # 끝을 머리 배치로 세므로, 색인과 메시지 0 사이에 다른 자료가 끼면 묶음 비트 자리가 앞으로 가지 않는 것으로 알아챈다
    bits = [rom.u24(index + 3 * k) for k in range(size // 3)]
    if any(a >= b for a, b in zip(bits, bits[1:])):
        raise ValueError('옮긴 보행 색인 표의 항목이 앞으로 가지 않음(색인과 메시지 0 사이에 다른 자료가 낀 것으로 보임)')
    return index, size // 3 * 16


def separate_index_groups(rom, index):
    """머리 밖에 따로 둔 색인 표의 묶음 수. 표는 한 뱅크 안이고, 뒤는 0 이라 앞으로 가지 않는 첫 항목에서 끝난다."""
    n, last = 0, -1
    while (index & 0xFFFF) + 3 * n + 3 <= 0x10000:
        v = rom.u24(index + 3 * n)
        if v <= last:
            break
        last = v
        n += 1
    return n


def contiguous_groups(data, index, mask, groups):
    """색인 항목 가운데 앞 묶음이 끝난 비트에서 다음 묶음이 시작하는 데까지의 묶음 수. 메시지는 비트로 이어 붙으므로
    색인 뒤에 앞으로 가는 다른 자료가 이어져도 그 항목은 앞 묶음의 끝과 맞지 않아 여기서 잘린다."""
    rom = Rom(data)
    decoder = rom.u24(DECODER + 1)
    for k in range(groups - 1):
        try:
            _, end = decode_check(data, decoder=decoder, bank_mask=mask, with_end=True, index=index + 3 * k, count=16)
        except (IndexError, ValueError):
            return k
        v = rom.u24(index + 3 * k + 3)
        start = lorom((v >> 3) | mask << 16)
        if start != lorom(end) - (1 if v & 7 else 0):
            return k + 1
    return groups


def relocated(data):
    """보행 메시지를 옮긴 롬의 (디코더 주소, 색인 창 OR 값). 옮기지 않았으면 오류."""
    rom = Rom(data)
    call = lorom(DECODER)
    stub = lorom(WALK_INDEX_STUB)
    if data[call] != 0x22 or data[call + 4] != 0x60:
        raise ValueError('새 보행 디코더 호출이 없음')
    if data[stub:stub + 6] != bytes.fromhex('20 8d 8c a5 f2 09') or data[stub + 6] not in WINDOWS \
            or data[stub + 7:stub + 10] != bytes.fromhex('85 f2 60'):
        raise ValueError('지원하는 보행 색인 훅이 아님')
    return rom.u24(DECODER + 1), data[stub + 6]


def base_package(base):
    """옮긴 롬의 메시지 묶음: (메시지, 글자 묶음 표 바이트, 글자 수, 묶음이 차지한 파일 구간 목록, 더 받는 제어 코드).
    글자 묶음 표는 표 피연산자부터 메시지 0 의 첫 바이트까지다(머리 끝에 두고 메시지를 바로 이은 꼴). 메시지 0 이
    머리 뒤에 바로 오지 않으면(DQ4 메뉴: 머리 5A:8000, 메시지 64:C400) 표는 0 이 아닌 5바이트 항목이 이어지는 데까지이고,
    구간은 머리·따로 둔 색인·메시지 셋이다. 그 사이의 다른 자료는 구간에 넣지 않는다.
    원래 표 밖의 1000 번대 제어 코드(101E~10FF)는 기준 롬의 메시지가 쓰고 있으면 그 롬이 처리하는 것으로 보고 받는다
    (DQ4 1장 빌드의 조사 코드 101E~1024 는 24:81D1 을 고치는 dq4josa 가 처리하는데, 메뉴 롬에는 그 훅이 아직 없다)."""
    rom = Rom(base)
    decoder, mask = relocated(base)
    index, total = index_table(base, mask)
    try:
        messages, end = decode_check(base, decoder=decoder, bank_mask=mask, with_end=True, index=index, count=total)
    except IndexError:
        raise ValueError('기준 롬의 메시지·트리 주소가 롬 범위를 벗어남') from None
    table = rom.u24(FONT_TABLE_OPERANDS[0][0])
    for at, k in FONT_TABLE_OPERANDS:
        if rom.u24(at) != table + k:
            raise ValueError(f'{at:06X}: 글자 묶음 표 피연산자가 서로 맞지 않음')
    first = (rom.u24(index) >> 3) | mask << 16
    head_end = lorom(first)
    if table == FONT_GROUPS:
        font, glyphs = None, GLYPHS
    else:
        # 머리가 뱅크 끝에 꼭 맞으면 메시지 0 은 다음 뱅크 첫머리라 CPU 주소가 아니라 파일 위치로 견준다.
        size = lorom(first) - lorom(table)
        if not 0 < size <= BANK or size % 5:
            if table >> 16 != decoder >> 16:
                raise ValueError('글자 묶음 표가 메시지 묶음 머리 끝에 있지 않음')
            size = 0
            while (table & 0xFFFF) + size + 5 <= 0x10000 and any(base[lorom(table) + size:lorom(table) + size + 5]):
                size += 5
            if not size:
                raise ValueError('글자 묶음 표가 메시지 묶음 머리 끝에 있지 않음')
            # 표 뒤가 0 인 항목으로 끝나야 표 밖의 자료까지 읽지 않은 것이다
            if (table & 0xFFFF) + size + 5 > 0x10000:
                raise ValueError('따로 둔 글자 묶음 표의 끝(0 인 항목)을 뱅크 안에서 찾지 못함')
            head_end = lorom(table) + size
            if sum(int.from_bytes(base[lorom(table) + i:lorom(table) + i + 2], 'little') & 0xFFF
                   for i in range(0, size, 5)) < GLYPHS:
                raise ValueError('따로 둔 글자 묶음 표의 글자 수가 원래보다 적음')
        font = bytes(base[lorom(table):lorom(table) + size])
        glyphs = sum(int.from_bytes(font[i:i + 2], 'little') & 0xFFF for i in range(0, len(font), 5))
    controls = frozenset(c for codes in messages for c in codes if 0x101E <= c <= 0x10FF)
    used = max((c for codes in messages for c in codes if c < 0x1000), default=0)
    if used >= glyphs:
        raise ValueError(f'메시지가 쓰는 글자 {used:03X} 가 글자 묶음 표의 글자 수 {glyphs:03X} 를 넘음')
    for codes in messages:
        valid_message(codes, glyphs, controls)
    if head_end == lorom(first):
        extents = [(lorom(decoder), lorom(end))]
    else:
        extents = [(lorom(decoder), head_end), (lorom(first), lorom(end))]
    if index >> 16 != decoder >> 16 and index != INDEX:
        extents.insert(1, (lorom(index), lorom(index) + total // 16 * 3))
    return messages, font, glyphs, extents, controls


def export(data, base=None):
    messages = base_package(base)[0] if base else read_messages(data)
    return {'format': FORMAT, 'messages': [{'id': i, 'codes': codes} for i, codes in enumerate(messages)]}


def tree(messages, glyphs=GLYPHS, controls=()):
    count(messages)
    freq = Counter(c for codes in messages for c in valid_message(codes, glyphs, controls))
    if not freq:
        raise ValueError('빈 허프만 트리는 만들 수 없음')
    if len(freq) == 1:
        code = next(iter(freq))
        return {code: '0'}, [(0x8000 | code, 0x8000 | code)], 0
    return build_tree(freq)


def compile_messages(data, messages, at='38:8000', name='walk-text', font=None, glyphs=GLYPHS, controls=()):
    """font 는 머리 끝에 옮겨 둘 글자 묶음 표(base_package). None 이면 원래 표 24:B176 을 그대로 쓴다.
    controls 는 기준 롬이 더 받는 제어 코드(base_package)."""
    base = parse_at(at)
    start = lorom(base)
    if start < len(data):
        raise ValueError('메시지 배치가 입력 롬과 겹침; 원본 롬과 확장 뱅크를 사용해야 함')
    code = decoder_code(data)
    codes, nodes, root = tree(messages, glyphs, controls)
    grown = count(messages)
    if grown and data[lorom(INDEX_LOAD):lorom(INDEX_LOAD) + len(INDEX_LOAD_CODE)] != INDEX_LOAD_CODE:
        raise ValueError('원래 보행 색인 읽기 코드(24:8BC3)가 아님')
    mask = bytes(1 << i for i in range(8))
    mask_at = base + len(code)
    t1_at = mask_at + len(mask)
    t0_at = t1_at + len(nodes) * 2
    index_at = t0_at + len(nodes) * 2
    font_at = index_at + index_size(messages)
    head_size = len(code) + len(mask) + len(nodes) * 4 + index_size(messages) + len(font or b'')
    if len(nodes) > 0x2000 or (base & 0xFFFF) + head_size > 0x10000:
        raise ValueError('디코더·마스크·트리가 한 뱅크를 넘음')
    bits = sum(len(codes[c]) for message_codes in messages for c in message_codes)
    size = head_size + (bits + 7) // 8
    bank_or = window(base >> 16)
    if start + size > window_end(base >> 16):
        raise ValueError(f'메시지가 색인 훅이 지원하는 {WINDOWS[bank_or][1]:02X} 뱅크 끝을 넘음')
    for operand, target in ((MASK_OPERAND, mask_at), (NODES_1_OPERAND, t1_at), (NODES_0_OPERAND, t0_at)):
        code[operand - DECODER:operand - DECODER + 2] = (target & 0xFFFF).to_bytes(2, 'little')
    code[ROOT_OPERAND - DECODER:ROOT_OPERAND - DECODER + 2] = (root * 2).to_bytes(2, 'little')
    code[-1] = 0x6B
    blob, starts = encode(codes, messages)
    index = bytearray()
    for m in range(0, len(messages), 16):
        bit = starts[m]
        off = start + head_size + (bit >> 3)
        cpu = (off // BANK) << 16 | 0x8000 | off % BANK
        value = ((cpu - (bank_or << 16)) << 3) | (bit & 7)
        if not 0 <= value < 1 << 24:
            raise ValueError('메시지 색인 24비트 범위 초과')
        index += cpu_to_bytes(value)
    head = code + mask + b''.join(n[0].to_bytes(2, 'little') for n in nodes) + \
        b''.join(n[1].to_bytes(2, 'little') for n in nodes) + (index if grown else b'') + (font or b'')
    stream = bytes(head + blob)
    writes = []
    pos = 0
    while pos < len(stream):
        off = start + pos
        part = stream[pos:pos + BANK - off % BANK]
        cpu = (off // BANK) << 16 | 0x8000 | off % BANK
        writes.append({'at': f'{cpu >> 16:02X}:{cpu & 0xFFFF:04X}', 'hex': part.hex(' '),
                       'note': '보행 디코더·허프만 트리·메시지'})
        pos += len(part)
    stub = bytes((0x20, 0x8D, 0x8C, 0xA5, 0xF2, 0x09, bank_or, 0x85, 0xF2, 0x60))
    if grown:
        load = bytearray(INDEX_LOAD_CODE)
        load[1] = index_at >> 16
        for k, off in enumerate((5, 10, 15)):
            load[off:off + 2] = ((index_at & 0xFFFF) + k).to_bytes(2, 'little')
        table = (INDEX_LOAD, bytes(load), '보행 메시지 색인 읽기(머리로 옮긴 표)')
    else:
        table = (INDEX, index, '보행 메시지 색인')
    originals = [table,
                 (DECODER, bytes([0x22]) + cpu_to_bytes(base) + b'\x60', '보행 디코더 호출'),
                 (WALK_INDEX_STUB, stub, '보행 색인 뱅크 훅'),
                 (WALK_INDEX_CALL, (WALK_INDEX_STUB & 0xFFFF).to_bytes(2, 'little'), '보행 색인 호출')]
    if font is not None:
        originals += [(at, cpu_to_bytes(font_at + k), '글자 묶음 표 피연산자') for at, k in FONT_TABLE_OPERANDS]
    for addr, raw, note in originals:
        off = lorom(addr)
        writes.append({'at': f'{addr >> 16:02X}:{addr & 0xFFFF:04X}', 'hex': raw.hex(' '),
                       'orig': data[off:off + len(raw)].hex(' '), 'note': note})
    return {'format': 'dq5patch/1', 'name': name, 'rom_size': 2 if bank_or == 0x20 else 4, 'writes': writes}


def index_size(messages):
    """머리에 둘 색인 표 바이트 수. 3,200개면 원래 24:AF1E 를 덮어 쓰므로 0."""
    return len(messages) // 16 * 3 if count(messages) else 0


def patch(data, doc, at='38:8000', name='walk-text', base=None):
    if base is None:
        return compile_messages(data, overrides(read_messages(data), doc), at, name)
    messages, font, glyphs, _, controls = base_package(base)
    return compile_messages(data, overrides(messages, doc, glyphs, controls), at, name, font, glyphs, controls)


def decoded_messages(data):
    decoder, mask = relocated(data)
    index, total = index_table(data, mask)
    try:
        return decode_check(data, decoder=decoder, bank_mask=mask, index=index, count=total)
    except IndexError:
        raise ValueError('메시지·트리 주소가 롬 범위를 벗어남') from None


def check(data, doc, at, base=None):
    from dq5build import build, parse_at as patch_at
    if base is None:
        messages, font, glyphs, controls = overrides(read_messages(data), doc), None, GLYPHS, ()
    else:
        messages, font, glyphs, _, controls = base_package(base)
        messages = overrides(messages, doc, glyphs, controls)
    manifest = compile_messages(data, messages, at, font=font, glyphs=glyphs, controls=controls)
    writes = [(patch_at(w['at'])[0], bytes.fromhex(w['hex']), bytes.fromhex(w['orig']) if 'orig' in w else None,
               w['note']) for w in manifest['writes']]
    rebuilt, _ = build(data, [(manifest['name'], manifest['rom_size'], writes)], manifest['rom_size'])
    decoded = decoded_messages(rebuilt)
    different = sum(a != b for a, b in zip(messages, decoded))
    print(f'보행 메시지 {len(decoded)}개, 코드 {sum(map(len, messages))}개, 다른 메시지 {different}개')
    return bool(different or len(decoded) != len(messages))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('rom')
    subs = parser.add_subparsers(dest='command', required=True)
    out = subs.add_parser('export')
    out.add_argument('-o', '--out', required=True)
    out.add_argument('--base')
    write = subs.add_parser('patch')
    write.add_argument('source')
    write.add_argument('-o', '--out', required=True)
    write.add_argument('--at', default='38:8000')
    write.add_argument('--name', default='walk-text')
    write.add_argument('--base')
    verify = subs.add_parser('check')
    verify.add_argument('source', nargs='?')
    verify.add_argument('--at', default='38:8000')
    verify.add_argument('--base')
    args = parser.parse_args()
    try:
        with open(args.rom, 'rb') as f:
            data = f.read()
        base = None
        if args.base:
            with open(args.base, 'rb') as f:
                base = f.read()
        if args.command == 'export':
            result = export(data, base)
        else:
            doc = {'format': FORMAT, 'messages': []}
            if args.source:
                with open(args.source, encoding='utf-8') as f:
                    doc = json.load(f)
            if args.command == 'check':
                return int(check(data, doc, args.at, base))
            result = patch(data, doc, args.at, args.name, base)
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
