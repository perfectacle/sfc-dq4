"""DQ5 실내 출구·영역 이동 표 전체를 다시 쓰고, 필요하면 다른 자리로 옮긴다.

출구 목적지 표, 일반 영역 이동 레코드·색인, 고층(그룹 $50 이상) 목록 16개를 통째로 다시 직렬화한다.
맵마다 출구·레코드 수, 출구 종류(길이), 색인에 새 맵을 넣는 것까지 바꿀 수 있다. 표 크기가 원래 자리에 맞으면
원래 자리에 그대로 쓰고 코드는 고치지 않는다. 옮기면 표를 찾는 코드의 즉값만 고친다.

  출구 표(2A:F6FD): 같은 뱅크 2A 안이면 2A:F70A·F70E 의 즉값 두 개만. 다른 뱅크면 ($84) 읽기 11곳을 [$84] 로 바꾸고
                    2A:F709 를 JSL 로 바꿔, 표 앞 13바이트 스텁이 $84~$86 을 채운다. DB 는 그대로 2A 다.
  색인(01:9430):    DB 를 색인 뱅크로 두고 abs 로 읽는다. 같은 DB 로 MMIO 곱셈($4202~)과 $183A~ 를 쓰므로 뱅크 00~3F.
  레코드(01:94A2):  실행기 00:CDEC·2A:F4B9·2A:FD11 이 레코드 뱅크를 DB 로 두고 WRAM($1954·$1EAB·$198E)을 abs 로
                    쓰므로 뱅크 00~3F. 고층 목록도 같다(01:94B4 의 즉값 16벌).
형식: sfc/dq5/docs/dq5-build-format.md 의 「실내 출구·영역 이동 표 옮기기」.

  python sfc/dq5/tools/dq5exitreloc.py rom/dq5.sfc dump -o work/exit-tables.json
  python sfc/dq5/tools/dq5exitreloc.py rom/dq5.sfc patch work/exit-tables.json -o work/exit-tables.dq5patch.json \\
      [--exits-at BB:AAAA] [--records-at BB:AAAA] [--index-at BB:AAAA] [--high-at BB:AAAA]
  python sfc/dq5/tools/dq5exitreloc.py rom/dq5.sfc check [work/exit-tables.json] [같은 자리 선택]
"""
import argparse
import json
import re
import sys
from pathlib import Path

from dq5build import BANK, ORIGINAL_SIZE, build, free_ranges, parse_at
from dq5exitwrite import TRIGGER_FIELDS, decode_exit, decode_trigger, high_list, map_name
from dq5map import Rom, lorom
from dq5mapwrite import all_maps

FORMAT = 'dq5exittables/1'
EXIT_GROUPS = 54
HIGH_FIRST = 0x50
RECORD = 12
STUB_SIZE = 13
# 2A:F709 LDA #$61 / STA $84 / LDA #$ED / STA $85
EXIT_INIT = 0x2AF709
EXIT_SHORT = (0x2AF711, 0x2AF71B, 0x2AF738, 0x2AF74B, 0x2AF755)
EXIT_INDEXED = (0x2AF76E, 0x2AF773, 0x2AF778, 0x2AF77D, 0x2AF7C9, 0x2AF7D6)
INDEX_BANK = 0x01943E
INDEX_OPERANDS = ((0x019449, 0), (0x019454, 1), (0x019459, 2), (0x019470, 2))
RECORD_LOW, RECORD_BANK = 0x0194A2, 0x0194AD
# 01:94B4 이하. 목록마다 LDA long 개수 / STA $183D / LDX #레코드 / STX $183A / LDA #뱅크. 원래 목록 순서.
HIGH_SITES = (0x0194BA, 0x0194D9, 0x0194EA, 0x0194FF, 0x01951A, 0x01952F, 0x019549, 0x01955F,
              0x019575, 0x01958B, 0x0195A1, 0x0195B7, 0x0195D3, 0x0195E9, 0x0195FF, 0x019615)
HIGH_ORIGINAL = (0x019635, 0x019642, 0x019667, 0x019680, 0x01968D, 0x01969A, 0x0196A7, 0x0196B4,
                 0x0196CD, 0x0196DA, 0x0196E7, 0x0196F4, 0x019701, 0x019732, 0x01974B, 0x019764)
ORIGINAL = {'exits': 0x2AED61, 'records': 0x2AD812, 'index': 0x2AEB0E, 'high': 0x019635}
# 원래 표가 차지하던 자리. 표를 옮기면 비므로 다른 표를 넣어도 된다.
POOLS = ((0x2AD812, 0x2AF224), (0x019635, 0x019771))
EXIT_FIELDS = {'same-group': ('destination_map', 'exit'), 'other-group': ('destination_map', 'exit', 'group'),
               'position': ('destination_map', 'x', 'y', 'layer', 'group'), 'special': ('special',)}
KIND_BITS = {'special': 0, 'other-group': 0x20, 'same-group': 0x40, 'position': 0x60}
SIZES = {0: 1, 0x20: 3, 0x40: 2, 0x60: 5}


def cpu(addr):
    return f'{addr >> 16:02X}:{addr & 0xFFFF:04X}'


def read(rom, addr, size):
    off = lorom(addr)
    raw = bytes(rom.d[off:off + size])
    if len(raw) != size:
        raise ValueError(f'{cpu(addr)}: 롬 범위 밖')
    return raw


def u16(rom, addr):
    return int.from_bytes(read(rom, addr, 2), 'little')


def stub(table):
    return bytes([0xA9, table & 0xFF, 0x85, 0x84, 0xA9, table >> 8 & 0xFF, 0x85, 0x85,
                  0xA9, table >> 16, 0x85, 0x86, 0x6B])


def high_maps(known):
    lists = {}
    for bc, bd in sorted(known):
        if bc >= HIGH_FIRST:
            lists.setdefault(high_list(bc, bd), []).append(map_name(bc, bd))
    return [lists[at] for at in HIGH_ORIGINAL]


def locate(rom):
    """코드의 즉값에서 네 표의 자리를 읽는다. 원래 롬이면 ORIGINAL 과 같다."""
    init = read(rom, EXIT_INIT, 8)
    if init[0] == 0xA9 and init[2:5] == b'\x85\x84\xa9' and init[6:] == b'\x85\x85':
        exits, short = 0x2A0000 | init[5] << 8 | init[1], True
    elif init[0] == 0x22 and init[4:] == b'\xea' * 4:
        at = int.from_bytes(init[1:4], 'little')
        code = read(rom, at, STUB_SIZE)
        exits, short = (code[9] << 16 | code[5] << 8 | code[1]), False
        if code != stub(exits):
            raise ValueError(f'{cpu(at)}: 출구 표 스텁 꼴이 아님')
        if at + STUB_SIZE != exits:
            raise ValueError('출구 표가 스텁 바로 뒤에 있지 않음')
    else:
        raise ValueError('2A:F709 가 알아보는 꼴이 아님')
    for sites, op in ((EXIT_SHORT, (0xB2, 0xA7)), (EXIT_INDEXED, (0xB1, 0xB7))):
        for at in sites:
            if read(rom, at, 2) != bytes([op[0] if short else op[1], 0x84]):
                raise ValueError(f'{cpu(at)}: 출구 표 읽기 명령이 표 자리와 맞지 않음')
    index = read(rom, INDEX_BANK, 1)[0] << 16 | u16(rom, INDEX_OPERANDS[0][0])
    for at, plus in INDEX_OPERANDS:
        if u16(rom, at) != (index + plus) & 0xFFFF:
            raise ValueError(f'{cpu(at)}: 색인 주소 즉값이 서로 맞지 않음')
    records = read(rom, RECORD_BANK, 1)[0] << 16 | u16(rom, RECORD_LOW)
    lists = []
    for site in HIGH_SITES:
        code = read(rom, site, 15)
        if code[0] != 0xAF or code[4:8] != b'\x8d\x3d\x18\xa2' or code[10:14] != b'\x8e\x3a\x18\xa9':
            raise ValueError(f'{cpu(site)}: 고층 목록 선택 코드 꼴이 아님')
        count = int.from_bytes(code[1:4], 'little')
        if (code[14] << 16 | int.from_bytes(code[8:10], 'little')) != count + 1:
            raise ValueError(f'{cpu(site)}: 고층 목록 레코드가 개수 바로 뒤에 있지 않음')
        lists.append(count)
    return {'exits': exits, 'records': records, 'index': index, 'high': tuple(lists)}


def known_maps(rom, new=()):
    """원본 맵 목록과 new(dq5newmap.py 로 그룹 끝에 더할 맵). 새 맵도 그룹마다 번호가 이어져야 한다."""
    known = set(all_maps(rom)) | set(new)
    groups = {}
    for bc, bd in known:
        groups.setdefault(bc, []).append(bd)
    for bc, maps in groups.items():
        # 2A:F732 는 $BD 번째 목록까지 건너뛰므로 맵 번호가 이어져 있어야 한다.
        if bc < HIGH_FIRST and sorted(maps) != list(range(len(maps))):
            raise ValueError(f'그룹 {bc:02X} 의 맵 번호가 0부터 이어지지 않음')
    normal = sorted({bc for bc in groups if bc < HIGH_FIRST})
    # 원래 그룹 00~35 에 새 그룹(dq5newmap.py)이 이어 붙는다. 출구 표는 그룹 머리를 찾으므로 번호가 이어져야 한다.
    if normal != list(range(len(normal))) or len(normal) < EXIT_GROUPS:
        raise ValueError('출구 그룹이 00 부터 이어지지 않거나 원래 그룹 00~35 가 빠짐')
    return known


def exit_groups(known):
    return 1 + max(bc for bc, _ in known if bc < HIGH_FIRST)


def exit_kind(raw):
    return next(k for k, v in KIND_BITS.items() if v == raw & 0x60)


def parse(rom, loc=None, known=None):
    """표 자리(loc, 생략하면 코드에서 읽음)에서 known(생략하면 롬의 맵 목록)의 문서를 읽는다. 엔진이 읽는 순서 그대로 따라간다."""
    loc = loc or locate(rom)
    known = known or known_maps(rom)
    doc = {'format': FORMAT, 'exits': [], 'triggers': [], 'high_triggers': []}
    addr = loc['exits']
    for bc in range(exit_groups(known)):
        if read(rom, addr, 1)[0] != bc:
            raise ValueError(f'{cpu(addr)}: 출구 그룹 {bc:02X} 머리가 없음')
        addr += 1
        for bd in range(sum(1 for g, _ in known if g == bc)):
            rows = []
            while True:
                first = read(rom, addr, 1)[0]
                if first == 0xFF:
                    raise ValueError(f'{cpu(addr)}: 맵 출구가 끝나기 전에 그룹 끝 FF')
                raw = read(rom, addr, SIZES[first & 0x60])
                rows.append({'kind': exit_kind(first), **{k: v for k, v in decode_exit(raw).items() if k != 'kind'}})
                addr += len(raw)
                if first & 0x80:
                    break
            doc['exits'].append({'map': map_name(bc, bd), 'records': rows})
        if read(rom, addr, 1)[0] != 0xFF:
            raise ValueError(f'{cpu(addr)}: 출구 그룹 {bc:02X} 끝 FF 가 없음')
        addr += 1
    at, cursor = loc['index'], loc['records']
    while read(rom, at, 1)[0] < 0x80:
        bc, bd, count = read(rom, at, 3)
        doc['triggers'].append({'map': map_name(bc, bd), 'records': [
            decode_trigger(read(rom, cursor + k * RECORD, RECORD)) for k in range(count)]})
        cursor += count * RECORD
        at += 3
    for at, maps in zip(loc['high'], high_maps(known)):
        count = read(rom, at, 1)[0]
        doc['high_triggers'].append({'maps': maps, 'records': [
            decode_trigger(read(rom, at + 1 + k * RECORD, RECORD)) for k in range(count)]})
    return doc


def integer(value, maximum, name):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError(f'{name}: 0~{maximum} 정수여야 함')
    return value


def exact(value, keys, name):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError(f'{name}: 필드가 정확히 {sorted(keys)} 여야 함')


def map_key(value, name):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9A-F]{2}/[0-9A-F]{2}', value):
        raise ValueError(f'{name}: map 은 대문자 16진 GG/MM 이어야 함')
    return tuple(int(v, 16) for v in value.split('/'))


def encode_exit(row, last, name):
    if not isinstance(row, dict) or row.get('kind') not in EXIT_FIELDS:
        raise ValueError(f'{name}: kind 는 {sorted(EXIT_FIELDS)} 중 하나')
    exact(row, ('kind', *EXIT_FIELDS[row['kind']]), name)
    # 2A:F711 은 다른 그룹을 FF 가 나올 때까지 한 바이트씩 건너뛰므로 레코드 안의 FF 는 그룹을 끊는다.
    values = [integer(row[k], 31 if k in ('special', 'destination_map') else 254, f'{name}.{k}')
              for k in EXIT_FIELDS[row['kind']]]
    raw = bytes([(0x80 if last else 0) | KIND_BITS[row['kind']] | values[0], *values[1:]])
    if 0xFF in raw:
        raise ValueError(f'{name}: 레코드에 FF 바이트가 생김(마지막 좌표 출구의 destination_map 31)')
    return raw


def encode_trigger(row, name):
    exact(row, ('rect', *TRIGGER_FIELDS), name)
    rect = row['rect']
    if not isinstance(rect, list) or len(rect) != 4:
        raise ValueError(f'{name}.rect: 좌표 바이트 네 개여야 함')
    rect = [integer(v, 255, f'{name}.rect') for v in rect]
    for start, end in ((rect[0], rect[2]), (rect[1], rect[3])):
        # 주인공 좌표가 음수이면 엔진은 상한 대신 시작점과 같은지만 본다(00:CE0C·CE21).
        if start < 128 and start >= end:
            raise ValueError(f'{name}.rect: 양수 영역의 끝은 시작보다 커야 함')
    return bytes([*rect, *(integer(row[k], 255, f'{name}.{k}') for k in TRIGGER_FIELDS)])


def serialize(doc, known):
    """문서 → (출구 표, 색인, 레코드, 고층 목록 16개) 바이트. 목적지 맵과 도착 출구 번호도 검사한다."""
    exact(doc, ('format', 'exits', 'triggers', 'high_triggers'), '문서')
    if doc['format'] != FORMAT:
        raise ValueError(f'format={FORMAT} 이 필요함')
    want = [map_name(*k) for k in sorted(known) if k[0] < HIGH_FIRST]
    rows = doc['exits']
    if not isinstance(rows, list) or [r.get('map') if isinstance(r, dict) else None for r in rows] != want:
        raise ValueError('exits 는 그룹 50 미만의 모든 맵을 맵 번호 순서로 하나씩 담아야 함')
    counts = {}
    for row in rows:
        exact(row, ('map', 'records'), f'exits {row["map"]}')
        if not isinstance(row['records'], list) or not row['records']:
            raise ValueError(f'exits {row["map"]}: 레코드가 하나 이상이어야 함(출구가 없으면 special 0)')
        counts[map_key(row['map'], 'exits')] = len(row['records'])
    out = bytearray()
    for bc in range(exit_groups(known)):
        out.append(bc)
        for row in rows:
            key = map_key(row['map'], 'exits')
            if key[0] != bc:
                continue
            for i, rec in enumerate(row['records']):
                name = f'exits {row["map"]} {i}'
                out += encode_exit(rec, i == len(row['records']) - 1, name)
                if rec['kind'] != 'special':
                    target = rec.get('group', bc), rec['destination_map']
                    if target not in known:
                        raise ValueError(f'{name}: 목적지 맵 {map_name(*target)} 이 원본 목록에 없음')
                    if 'exit' in rec and rec['exit'] >= counts.get(target, 0):
                        raise ValueError(f'{name}: 도착 출구 번호가 {map_name(*target)} 의 출구 수 밖')
        out.append(0xFF)

    def trigger_rows(records, name):
        if not isinstance(records, list) or len(records) > 255:
            raise ValueError(f'{name}: records 는 0~255개 배열')
        blob = bytearray()
        for i, rec in enumerate(records):
            raw = encode_trigger(rec, f'{name} {i}')
            if not raw[6] & 0x80 and (raw[6], raw[7]) not in known:
                raise ValueError(f'{name} {i}: 목적지 맵 {map_name(raw[6], raw[7])} 이 원본 목록에 없음')
            blob += raw
        return bytes(blob)

    index, records, seen = bytearray(), bytearray(), set()
    if not isinstance(doc['triggers'], list):
        raise ValueError('triggers 는 배열이어야 함')
    for row in doc['triggers']:
        exact(row, ('map', 'records'), 'triggers')
        key = map_key(row['map'], 'triggers')
        if key not in known or key[0] >= HIGH_FIRST or key in seen:
            raise ValueError(f'triggers {row["map"]}: 그룹 50 미만의 맵을 한 번만 적어야 함')
        seen.add(key)
        blob = trigger_rows(row['records'], f'triggers {row["map"]}')
        if not blob:
            raise ValueError(f'triggers {row["map"]}: 레코드가 없으면 항목을 빼야 함')
        index += bytes([*key, len(blob) // RECORD])
        records += blob
    index.append(0xFF)
    high = doc['high_triggers']
    shared = high_maps(known)
    if not isinstance(high, list) or len(high) != len(shared):
        raise ValueError(f'high_triggers 는 목록 {len(shared)}개여야 함')
    lists = []
    for i, (row, maps) in enumerate(zip(high, shared)):
        exact(row, ('maps', 'records'), f'high_triggers {i}')
        if row['maps'] != maps:
            raise ValueError(f'high_triggers {i}: maps 는 {maps} 여야 함(01:94B4 가 고르는 맵)')
        blob = trigger_rows(row['records'], f'high_triggers {i}')
        lists.append(bytes([len(blob) // RECORD]) + blob)
    return {'exits': bytes(out), 'index': bytes(index), 'records': bytes(records), 'high': lists}


def allowed(original):
    """표를 둘 수 있는 자리: 원래 표 자리, 원래 롬 빈 자리, 늘린 뱅크(30~7D). (CPU 시작, 끝) 목록."""
    out = list(POOLS)
    for off, size in free_ranges(original):
        start = (off // BANK) << 16 | 0x8000 | off % BANK
        out.append((start, start + size))
    out += [(bank << 16 | 0x8000, bank + 1 << 16) for bank in range(ORIGINAL_SIZE // BANK, 0x7E)]
    return out


def current_places(loc):
    """locate() 결과를 --*-at 과 같은 꼴(출구는 스텁 자리)로."""
    exits = loc['exits'] if loc['exits'] >> 16 == 0x2A else loc['exits'] - STUB_SIZE
    return {'exits': exits, 'records': loc['records'], 'index': loc['index'], 'high': loc['high'][0]}


def occupied(rom, known):
    """이미 옮긴 롬이면 지금 표들이 차지한 자리. 같은 자리에 다시 쓸 수 있게 허용 목록에 더한다."""
    loc = locate(rom)
    blobs = serialize(parse(rom, loc, known), known)
    exits = loc['exits'] if loc['exits'] >> 16 == 0x2A else loc['exits'] - STUB_SIZE
    return [(exits, loc['exits'] + len(blobs['exits'])), (loc['index'], loc['index'] + len(blobs['index'])),
            (loc['records'], loc['records'] + len(blobs['records'])),
            (loc['high'][0], loc['high'][0] + sum(map(len, blobs['high'])))]


def placement(original, sizes, at, current, extra=()):
    """at: 표 이름 → CPU 주소(없으면 지금 자리 current). extra 는 더 허용할 (시작, 끝). 검사한 자리를 돌려준다."""
    at = {k: at.get(k) or current[k] for k in ORIGINAL}
    spans = {}
    for name, size in sizes.items():
        start = at[name]
        bank = start >> 16
        if name == 'exits' and bank != 0x2A:
            size += STUB_SIZE
        if not 0x8000 <= start & 0xFFFF or start + size > (bank + 1) << 16:
            raise ValueError(f'{name}: {cpu(start)} 에서 {size}바이트가 한 뱅크(8000~FFFF)에 들어가지 않음')
        # 색인 읽기(01:9430)와 실행기(00:CDEC, 2A:F4B9, 2A:FD11)는 표 뱅크를 DB 로 두고 MMIO·WRAM 을 abs 로 쓴다.
        if name != 'exits' and bank > 0x3F:
            raise ValueError(f'{name}: 뱅크 00~3F 만 됨(DB 로 MMIO·WRAM 을 읽음)')
        if bank > 0x7D:
            raise ValueError(f'{name}: 뱅크 00~7D 로 적어야 함')
        if not any(lo <= start and start + size <= hi for lo, hi in [*allowed(original), *extra]):
            raise ValueError(f'{name}: {cpu(start)}~ {size}바이트가 원래 표 자리·빈 자리·늘린 뱅크 어느 한 곳에도 들지 않음')
        spans[name] = (start, start + size)
    order = sorted(spans.items(), key=lambda kv: kv[1])
    for (a, (_, end)), (b, (start, _)) in zip(order, order[1:]):
        if start < end:
            raise ValueError(f'{a} 와 {b} 의 자리가 겹침')
    return at


def rom_size(addresses):
    top = max(a >> 16 for a in addresses)
    return 0 if top < 0x30 else 2 if top < 0x40 else 3 if top < 0x60 else 4


def writes_for(rom, doc, at=None, new=()):
    """문서와 자리 → [(CPU 주소, 새 바이트, 원래 바이트 또는 None, 설명)] 과 롬 크기(MB). new 는 더할 맵."""
    known = known_maps(rom, new)
    blobs = serialize(doc, known)
    sizes = {'exits': len(blobs['exits']), 'index': len(blobs['index']), 'records': len(blobs['records']),
             'high': sum(map(len, blobs['high']))}
    loc = locate(rom)
    # 원래 꼴 롬이면 원래 표 자리(POOLS)가 이미 허용 목록에 있다.
    extra = [] if loc == {**ORIGINAL, 'high': HIGH_ORIGINAL} else occupied(rom, known)
    at = placement(rom.d, sizes, at or {}, current_places(loc), extra)
    short = at['exits'] >> 16 == 0x2A
    table = at['exits'] if short else at['exits'] + STUB_SIZE
    data = [(at['exits'], (b'' if short else stub(table)) + blobs['exits'], '출구 목적지 표'),
            (at['index'], blobs['index'], '영역 이동 색인'),
            (at['records'], blobs['records'], '영역 이동 레코드')]
    cursor, high = at['high'], []
    for blob in blobs['high']:
        high.append(cursor)
        cursor += len(blob)
    data.append((at['high'], b''.join(blobs['high']), '고층 영역 이동 목록'))
    code = [(EXIT_INIT, bytes([0xA9, table & 0xFF, 0x85, 0x84, 0xA9, table >> 8 & 0xFF, 0x85, 0x85]) if short
             else bytes([0x22, *at['exits'].to_bytes(3, 'little'), 0xEA, 0xEA, 0xEA, 0xEA]), '출구 표 자리')]
    code += [(a, bytes([0xB2 if short else 0xA7]), '출구 표 읽기 ($84)/[$84]') for a in EXIT_SHORT]
    code += [(a, bytes([0xB1 if short else 0xB7]), '출구 표 읽기 ($84),Y/[$84],Y') for a in EXIT_INDEXED]
    code.append((INDEX_BANK, bytes([at['index'] >> 16]), '색인 뱅크(DB)'))
    code += [(a, ((at['index'] + plus) & 0xFFFF).to_bytes(2, 'little'), '색인 주소') for a, plus in INDEX_OPERANDS]
    code += [(RECORD_LOW, (at['records'] & 0xFFFF).to_bytes(2, 'little'), '레코드 주소'),
             (RECORD_BANK, bytes([at['records'] >> 16]), '레코드 뱅크')]
    for site, start in zip(HIGH_SITES, high):
        code += [(site + 1, start.to_bytes(3, 'little'), '고층 목록 개수'),
                 (site + 8, (start + 1 & 0xFFFF).to_bytes(2, 'little'), '고층 목록 레코드'),
                 (site + 14, bytes([start >> 16]), '고층 목록 뱅크')]
    out = []
    for addr, new, note in data + code:
        old = bytes(rom.d[lorom(addr):lorom(addr) + len(new)]) if lorom(addr) + len(new) <= len(rom.d) else None
        if new and new != old:
            out.append((addr, new, old if lorom(addr) < ORIGINAL_SIZE else None, note))
    if out:
        # 원래 표 자리 중 새 표가 들지 않은 곳도 같은 바이트로 써서 이 도구가 맡는다. 고정 슬롯 쓰기(dq5exitwrite.py)를
        # 한 빌드에 함께 넣으면 빌더가 겹침으로 거부한다. 같이 넣으면 그 편집이 옮겨 간 표에 닿지 않기 때문이다.
        gaps = []
        for lo, hi in POOLS:
            taken = sorted((max(a, lo), min(a + len(n), hi)) for a, n, _, _ in out if a < hi and a + len(n) > lo)
            cursor = lo
            for first, last in taken + [(hi, hi)]:
                if first > cursor:
                    old = read(rom, cursor, first - cursor)
                    gaps.append((cursor, old, old, '원래 표 자리 맡음(바이트 그대로)'))
                cursor = max(cursor, last)
        out += gaps
        out.sort()
    return out, rom_size([a for a, _, _, _ in out] or [0])


def dump(rom, new=()):
    """원본 문서. new 의 맵은 출구 special 0 하나(출구 없음)로 넣는다."""
    doc = parse(rom)
    known = known_maps(rom, new)
    names = [map_name(*k) for k in sorted(known) if k[0] < HIGH_FIRST]
    rows = {r['map']: r for r in doc['exits']}
    doc['exits'] = [rows.get(n) or {'map': n, 'records': [{'kind': 'special', 'special': 0}]} for n in names]
    return doc


def patch(rom, doc, at=None, new=()):
    writes, mb = writes_for(rom, doc, at, new)
    result = {'format': 'dq5patch/1', 'name': 'exit-tables', 'writes': [
        {'at': cpu(addr), 'hex': new.hex(' '), **({'orig': old.hex(' ')} if old is not None else {}), 'note': note}
        for addr, new, old, note in writes]}
    if mb:
        result['rom_size'] = mb
    return result


def engine_exits(rom, loc, bc, bd):
    """2A:F711~F755 를 따라 (bc, bd) 의 출구 레코드를 [(주소, 바이트)] 로 얻는다. 그룹이 없으면 None."""
    addr = loc['exits']
    while (head := read(rom, addr, 1)[0]) != bc:
        if head == 0xFF:
            return None
        addr += 1
        while read(rom, addr, 1)[0] != 0xFF:
            addr += 1
        addr += 1
    addr += 1
    for _ in range(bd + 1):
        out = []
        while True:
            first = read(rom, addr, 1)[0]
            out.append((addr, read(rom, addr, SIZES[first & 0x60])))
            addr += len(out[-1][1])
            if first & 0x80:
                break
    return out


def engine_triggers(rom, loc, bc, bd):
    """01:9430 처럼 색인 개수를 더해 (bc, bd) 레코드를 찾는다."""
    at, total = loc['index'], 0
    while (head := read(rom, at, 1)[0]) < 0x80:
        if head == bc and read(rom, at + 1, 1)[0] == bd:
            count = read(rom, at + 2, 1)[0]
            return [read(rom, loc['records'] + (total + k) * RECORD, RECORD) for k in range(count)]
        total += read(rom, at + 2, 1)[0]
        at += 3
    return []


def check(rom, doc=None, at=None, new=()):
    if locate(rom) != {**ORIGINAL, 'high': HIGH_ORIGINAL}:
        raise ValueError('check 는 원래 롬에서 돌린다')
    original = parse(rom)
    if patch(rom, original)['writes']:
        raise ValueError('원본을 다시 직렬화한 결과가 원래 바이트와 다름')
    source = dump(rom, new) if doc is None else doc
    known = known_maps(rom, new)
    manifest = patch(rom, source, at, new)
    writes = [(lorom(int(w['at'][:2], 16) << 16 | int(w['at'][3:], 16)), bytes.fromhex(w['hex']),
               bytes.fromhex(w['orig']) if 'orig' in w else None, w['note']) for w in manifest['writes']]
    built, _ = build(rom.d, [('exit-tables', manifest.get('rom_size', 0), writes)], manifest.get('rom_size', 0))
    moved = Rom(built)
    loc = locate(moved)
    if parse(moved, loc, known) != json.loads(json.dumps(source)):
        raise ValueError('만든 롬을 코드가 가리키는 자리에서 다시 읽은 결과가 입력과 다름')
    for row in source['exits']:
        bc, bd = map_key(row['map'], 'exits')
        want = [encode_exit(r, i == len(row['records']) - 1, '') for i, r in enumerate(row['records'])]
        if [raw for _, raw in engine_exits(moved, loc, bc, bd)] != want:
            raise ValueError(f'{row["map"]}: 엔진 순서로 찾은 출구가 입력과 다름')
    listed = {map_key(r['map'], 'triggers'): r['records'] for r in source['triggers']}
    for bc, bd in sorted(known):
        if bc < HIGH_FIRST and [decode_trigger(r) for r in engine_triggers(moved, loc, bc, bd)] != listed.get((bc, bd), []):
            raise ValueError(f'{map_name(bc, bd)}: 엔진 순서로 찾은 영역 이동이 입력과 다름')
    if patch(moved, source, at, new)['writes']:
        raise ValueError('만든 롬에 같은 입력을 다시 패치하면 쓰기가 남음')
    sizes = (sum(len(r['records']) for r in source['exits']), sum(len(r['records']) for r in source['triggers']),
             len(source['triggers']), sum(len(r['records']) for r in source['high_triggers']))
    print(f'출구 {sizes[0]}개, 영역 이동 {sizes[1]}개(색인 {sizes[2]}맵), 고층 {sizes[3]}개; '
          f'표 자리 {", ".join(f"{k} {cpu(v if k != "high" else v[0])}" for k, v in loc.items())}; '
          f'쓰기 {len(writes)}개, 롬 {manifest.get("rom_size") or 1.5}MB 검사 통과')


def address(text):
    if not re.fullmatch(r'[0-9A-Fa-f]{2}:[0-9A-Fa-f]{4}', text):
        raise argparse.ArgumentTypeError('BB:AAAA 로 적어야 함')
    try:
        off, _ = parse_at(text)
    except Exception as error:
        raise argparse.ArgumentTypeError(str(error)) from error
    return (off // BANK) << 16 | 0x8000 | off % BANK


def new_map(text):
    try:
        key = map_key(text, '--new-map')
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error
    if key[0] >= HIGH_FIRST:
        raise argparse.ArgumentTypeError('--new-map 은 그룹 50 미만만 받음(그룹 50 이상은 출구 표가 없음)')
    return key


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('rom', type=Path)
    sub = parser.add_subparsers(dest='command', required=True)
    export = sub.add_parser('dump')
    export.add_argument('-o', '--out', type=Path, required=True)
    write = sub.add_parser('patch')
    write.add_argument('source', type=Path)
    write.add_argument('-o', '--out', type=Path, required=True)
    verify = sub.add_parser('check')
    verify.add_argument('source', type=Path, nargs='?')
    for p in (write, verify):
        for name in ORIGINAL:
            p.add_argument(f'--{name}-at', type=address, help=f'기본 {cpu(ORIGINAL[name])}')
    for p in (export, write, verify):
        p.add_argument('--new-map', action='append', default=[], type=new_map,
                       help='dq5newmap.py 로 더할 맵 GG/MM(여럿이면 되풀이)')
    args = parser.parse_args()
    try:
        rom = Rom(args.rom.read_bytes())
        at = {k: getattr(args, f'{k}_at', None) for k in ORIGINAL}
        doc = json.loads(args.source.read_text(encoding='utf-8')) if getattr(args, 'source', None) else None
        if args.command == 'check':
            check(rom, doc, at, args.new_map)
        else:
            result = dump(rom, args.new_map) if args.command == 'dump' else patch(rom, doc, at, args.new_map)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(f'오류: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
