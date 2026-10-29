"""DQ5 실내 맵에 새 맵 번호·새 그룹 번호를 더한다(그룹 끝 번호부터, 새 그룹은 마지막 그룹 다음부터 차례로).

맵 번호로 곧장 색인하는 표 가운데 이 도구는 맵 포인터(0F:8ED7, 맵마다 3바이트), 맵 속성(23:FD6A, 맵마다 6바이트:
조우 구역·전투 배경·주문 막기·곡), 그룹 50 이상의 맵 포인터(1F:CEB6), 그룹마다 들어가는 곳(0F:EA97, 5바이트)을 맡는다.
그룹 50 이상의 맵 속성(23:FDD6 목록)은 dq5encounterwrite.py --high-at 이 맡는다. 세 포인터·속성 표는 그룹 목록 바로 뒤에
그룹 표가 있어 늘릴 틈이 없다.
  같은 뱅크: 그룹 표를 같은 뱅크 빈 자리로 옮기고 비는 옛 표 자리만큼 목록을 민다. 표 주소 피연산자만 바꾼다.
  다른 뱅크(00~3F): 목록과 그룹 표를 함께 옮기고 DB 즉값(01:92F1·01:83ED·01:9326)까지 바꾼다. DB 로 WRAM·MMIO 를
  abs 로 쓰므로 뱅크 40 이상은 안 된다.
옮긴 그룹 표는 [그룹마다 시작][끝][0000] 꼴이다(dq5map.group_spans). 출구·영역 이동은 dq5exitreloc.py --new-map,
인물 목록은 인물 도구가 맡는다. 형식: sfc/dq5/docs/dq5-build-format.md 「새 맵 번호」.

  python sfc/dq5/tools/dq5newmap.py rom/dq5.sfc patch work/newmap.json -o work/newmap.dq5patch.json [자리 선택]
  python sfc/dq5/tools/dq5newmap.py rom/dq5.sfc check work/newmap.json [자리 선택]
  자리 선택: --pointer-table-at --attr-table-at --high-table-at --entrance-table-at --door-stub-at --records-at BB:AAAA,
            --door-bank BB

입력: {"format": "dq5newmap/1", "groups": [{"group": "36", "entrance": {"copy": "0D"}}],
       "maps": [{"map": "0D/05", "record": {"copy": "0D/02"}, "attrs": {"copy": "0D/02"}}]}
  record: {"copy": "GG/MM"} 그 맵과 같은 레코드, {"source": "파일.json"} dq5map/1 문서(입력 파일 기준 경로, --records-at 에 놓음)
  attrs:  {"copy": "GG/MM"} 또는 {"bytes": [6개]}. entrance: {"copy": "GG"} 또는 {"bytes": [5개]}
  새 맵은 record·attrs 가 둘 다 있어야 한다(그룹 50 이상은 record 만). 기존 맵도 바꿀 것만 적을 수 있다. 새 그룹은 groups 에 들어가는 곳이 있어야 하고,
  groups 에 기존 그룹을 적으면 그 그룹의 들어가는 곳을 바꾼다.
  그룹 50 이상은 50·52·53 에만 더한다(51·54 는 01:94B4 가 $BD 마다 영역 이동 목록을 고르고, 맞는 것이 없으면
  앞 맵의 개수 $183D 가 남음).
  문 표(01:D2FC)는 --door-bank BB(30~3F)로 늘린다: 뱅크 01 을 그 뱅크에 복사하고 복사본의 문 표에 빈 맵·빈 그룹을
  끼운 뒤, 문 자료로 들어가는 여섯 입구를 JML 로 --door-stub-at(기본 01:FED0)의 스텁에 보내 DB 를 그 뱅크로 둔다.
  주지 않으면 새 맵이 건너뛰기로 읽게 되는 문 목록이 비어 있지 않거나 표 밖일 때 거부하고,
  --allow-door-readthrough 를 주면 그대로 만든다.
"""
import argparse
import json
import re
import sys
from pathlib import Path

from dq5build import BANK, ORIGINAL_SIZE, PatchError, build, free_ranges
from dq5map import (DOOR_ENTRIES, DOOR_TABLE, TABLE_KINDS, Rom, door_groups, door_stub, door_table, group_spans,
                    group_table, lorom, map_pointer)
from dq5mapwrite import encode, entries_for

FORMAT = 'dq5newmap/1'
HIGH_FIRST = 0x50
HIGH_OK = (0x50, 0x52, 0x53)
# 같은 뱅크에서 그룹 표를 둘 기본 자리(그 뱅크 끝 빈 자리).
DEFAULT_TABLE = {'pointer': 0x0FFF50, 'attr': 0x23FF20, 'high': 0x1FFE30}
# 2A:F393 등 LDA $0FEA97,X 꼴(긴 주소) 여덟 곳의 피연산자와 표 시작에서 더하는 값. 그룹마다 5바이트.
ENTRANCE_SITES = ((0x2AF394, 0), (0x2AF39C, 1), (0x2AF3A2, 2), (0x2AF3A8, 3), (0x2AF3AE, 4),
                  (0x2AFD90, 4), (0x2AFD9B, 0), (0x2AFF13, 0))
ENTRANCE_SIZE = 5
# 01:F3F9: 문 표. 그룹은 C0 이상 바이트로, 그룹 안 맵은 80 이상 바이트로 끝나고 $BC·$BD 만큼 건너뛰어 찾는다.
DOOR_END = 0x01D8C2
DOOR_STUB = 0x01FED0
STUB_SIZE = 11
# 문 루틴이 문 표 밖에서 같은 DB 로 읽는 뱅크 01 자료가 든 구간. 문을 여는 01:DFAB 가 종류마다 $0E 에 넣는
# 타일 워드 표 F037·F067(01:E170, 종류 3F·40)·F097·F0D7(01:E539, 41·42)과 $03 의 그림 표 FDxx·FExx 이 이 안이다.
# 늘린 문 표는 이 앞에서 끝나야 하고, 복사본의 이 구간은 뱅크 01 과 같아야 한다. 구간 안의 코드도 함께 견주므로
# 문 루틴을 고치는 다른 패치(01:F42D 훅 등)를 복사 뒤에 넣으면 거부된다.
DOOR_DATA = (0xF037, 0xFEB7)


def cpu(addr):
    return f'{addr >> 16:02X}:{addr & 0xFFFF:04X}'


def read(rom, addr, size):
    off = lorom(addr)
    raw = bytes(rom.d[off:off + size])
    if len(raw) != size:
        raise ValueError(f'{cpu(addr)}: 롬 범위 밖')
    return raw


def map_key(value, name):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9A-F]{2}/[0-9A-F]{2}', value):
        raise ValueError(f'{name}: map 은 대문자 16진 GG/MM 이어야 함')
    return tuple(int(v, 16) for v in value.split('/'))


def entries(rom, kind):
    """그룹마다 [항목 바이트…] 와 지금 그룹 표 자리."""
    spans, table = group_spans(rom, kind=kind)
    size, bank = TABLE_KINDS[kind]['size'], table & 0xFF0000
    return [[read(rom, bank | start + i * size, size) for i in range((end - start) // size)]
            for start, end in spans], table


def entrance_table(rom):
    table = None
    for site, plus in ENTRANCE_SITES:
        if read(rom, site - 1, 1)[0] != 0xBF:
            raise ValueError(f'{cpu(site - 1)} 이 들어가는 곳 표를 읽는 원래 명령이 아님')
        value = int.from_bytes(read(rom, site, 3), 'little') - plus
        if table not in (None, value):
            raise ValueError('들어가는 곳 표 주소 피연산자가 서로 맞지 않음')
        table = value
    return table


def door_readthrough(rom, bc, bd):
    """01:F40F~F42B 처럼 건너뛰어 (bc, bd) 가 읽게 되는 문 목록 첫 자리. 표 밖이면 None."""
    y = 0
    for limit, count in ((0xC0, bc), (0x80, bd)):
        for _ in range(count):
            while DOOR_TABLE + y < DOOR_END and read(rom, DOOR_TABLE + y, 1)[0] < limit:
                y += 1
            y += 1
    return DOOR_TABLE + y if DOOR_TABLE + y < DOOR_END else None


class Plan:
    """입력을 표마다 새 항목으로 푼다."""

    def __init__(self, rom, doc, base):
        if not isinstance(doc, dict) or set(doc) - {'format', 'maps', 'groups'} or doc.get('format') != FORMAT:
            raise ValueError(f'문서는 format={FORMAT}, maps, groups 만 담아야 함')
        self.pointers, _ = entries(rom, 'pointer')
        self.attrs, _ = entries(rom, 'attr')
        self.high, _ = entries(rom, 'high')
        if [len(g) for g in self.pointers] != [len(g) for g in self.attrs]:
            raise ValueError('맵 포인터와 맵 속성의 그룹별 맵 수가 다름')
        table = entrance_table(rom)
        self.entrances = [read(rom, table + g * ENTRANCE_SIZE, ENTRANCE_SIZE) for g in range(len(self.pointers))]
        # copy 는 원본 항목에서 푼다. 입력 차례나 같은 입력의 다른 고침에 따라 값이 달라지지 않게 한다.
        base_ptr, base_attr = [list(g) for g in self.pointers], [list(g) for g in self.attrs]
        base_high = [list(g) for g in self.high]
        base_entr = list(self.entrances)
        self.records, self.changed = [], set()
        groups = doc.get('groups', [])
        if not isinstance(groups, list):
            raise ValueError('groups 는 배열이어야 함')
        added = set()
        for i, row in enumerate(groups):
            name = f'groups[{i}]'
            if not isinstance(row, dict) or set(row) != {'group', 'entrance'} or not isinstance(row['group'], str) \
                    or not re.fullmatch(r'[0-9A-F]{2}', row['group']):
                raise ValueError(f'{name}: group(대문자 16진 GG)·entrance 가 필요함')
            bc = int(row['group'], 16)
            if bc in added:
                raise ValueError(f'{name}: 그룹 {bc:02X} 을 두 번 적음')
            added.add(bc)
            if bc > len(self.pointers) or bc >= HIGH_FIRST:
                raise ValueError(f'{name}: 새 그룹은 {len(self.pointers):02X} 부터 차례로(50 미만)')
            value = row['entrance']
            if isinstance(value, dict) and set(value) == {'copy'} and isinstance(value['copy'], str) \
                    and re.fullmatch(r'[0-9A-F]{2}', value['copy']) and int(value['copy'], 16) < len(base_entr):
                entrance = base_entr[int(value['copy'], 16)]
            elif isinstance(value, dict) and set(value) == {'bytes'} and isinstance(value['bytes'], list) and \
                    len(value['bytes']) == 5 and all(type(v) is int and 0 <= v <= 255 for v in value['bytes']):
                entrance = bytes(value['bytes'])
            else:
                raise ValueError(f'{name}.entrance: 원본 그룹 copy 또는 0~255 정수 5개의 bytes 가 필요함')
            if bc < len(self.pointers):
                self.entrances[bc] = entrance
                continue
            self.pointers.append([])
            self.attrs.append([])
            self.entrances.append(entrance)
        if not isinstance(doc.get('maps', []), list):
            raise ValueError('maps 는 배열이어야 함')
        for i, row in enumerate(doc.get('maps', [])):
            self.map_row(f'maps[{i}]', row, base, base_ptr, base_attr, base_high)
        for g, maps in enumerate(self.pointers):
            if not maps:
                raise ValueError(f'새 그룹 {g:02X} 에 맵이 없음')

    def map_row(self, name, row, base, base_ptr, base_attr, base_high):
        if not isinstance(row, dict) or 'map' not in row or set(row) - {'map', 'record', 'attrs'}:
            raise ValueError(f'{name}: map·record·attrs 만 받음')
        bc, bd = map_key(row['map'], name)
        if (bc, bd) in self.changed:
            raise ValueError(f'{name}: 같은 맵을 두 번 적음')
        self.changed.add((bc, bd))
        high = bc >= HIGH_FIRST
        if high:
            if bc - HIGH_FIRST >= len(self.high):
                raise ValueError(f'{name}: 그룹 {bc:02X} 이 없음(그룹 50 이상의 새 그룹은 받지 않음)')
            ptrs, slot = self.high[bc - HIGH_FIRST], bd - HIGH_FIRST
        else:
            if bc >= len(self.pointers):
                raise ValueError(f'{name}: 그룹 {bc:02X} 이 없음(새 그룹은 groups 에 먼저 적음)')
            ptrs, slot = self.pointers[bc], bd
        if high and 'attrs' in row:
            raise ValueError(f'{name}: 그룹 50 이상의 맵 속성은 dq5encounterwrite.py(maps 의 tail, --high-at)로 씀')
        if slot == len(ptrs):
            if set(row) != ({'map', 'record'} if high else {'map', 'record', 'attrs'}):
                raise ValueError(f'{name}: 새 맵 {row["map"]} 에는 record' + ('' if high else ' 와 attrs 가 둘 다') + ' 필요함')
            if high and bc not in HIGH_OK:
                raise ValueError(f'{name}: 그룹 {bc:02X} 에는 새 맵을 더하지 않음(50·52·53 만)')
            ptrs.append(None)
            if not high:
                self.attrs[bc].append(None)
        elif not 0 <= slot < len(ptrs):
            raise ValueError(f'{name}: 새 맵 번호는 그룹 {bc:02X} 의 끝 번호부터 차례로 더함')

        def copy_key(value, field):
            if not isinstance(value, dict) or len(value) != 1:
                raise ValueError(f'{name}.{field}: 키 하나짜리 객체여야 함')
            if 'copy' not in value:
                return None
            key = map_key(value['copy'], f'{name}.{field}.copy')
            if (key[0] >= HIGH_FIRST) != high:
                raise ValueError(f'{name}.{field}: 그룹 50 이상과 미만은 서로 복사하지 않음')
            if high:
                ok = key[0] - HIGH_FIRST < len(base_high) and 0 <= key[1] - HIGH_FIRST < len(base_high[key[0] - HIGH_FIRST])
            else:
                ok = key[0] < len(base_ptr) and key[1] < len(base_ptr[key[0]])
            if not ok:
                raise ValueError(f'{name}.{field}: 복사할 맵 {value["copy"]} 이 원본에 없음(새 맵은 복사하지 않음)')
            return key

        if 'record' in row:
            key = copy_key(row['record'], 'record')
            if key:
                ptrs[slot] = (base_high[key[0] - HIGH_FIRST][key[1] - HIGH_FIRST] if high else base_ptr[key[0]][key[1]])
            elif set(row['record']) == {'source'}:
                path = base / row['record']['source']
                record = json.loads(path.read_text(encoding='utf-8'))
                if record.get('map') not in (None, row['map']):
                    raise ValueError(f'{name}.record: {path} 의 map 이 {row["map"]} 이 아님')
                for line in entries_for(record):
                    raise ValueError(f'{name}.record: {line}')
                self.records.append(((bc, bd), encode(record)))
                ptrs[slot] = len(self.records) - 1
            else:
                raise ValueError(f'{name}.record: copy 또는 source 가 필요함')
        if 'attrs' in row:
            key = copy_key(row['attrs'], 'attrs')
            if key:
                value = base_attr[key[0]][key[1]]
            elif set(row['attrs']) == {'bytes'} and isinstance(row['attrs']['bytes'], list) and \
                    len(row['attrs']['bytes']) == 6 and all(type(v) is int and 0 <= v <= 255 for v in row['attrs']['bytes']):
                value = bytes(row['attrs']['bytes'])
            else:
                raise ValueError(f'{name}.attrs: copy 또는 0~255 정수 6개의 bytes 가 필요함')
            self.attrs[bc][slot] = value


def bank_free(rom, addr, size, extra=()):
    """addr~ size 바이트가 원래 롬 빈 자리·늘린 뱅크·extra(지금 표가 놓인 자리) 안이면 참.
    extra 뒤에 이어지는 0 바이트도 그 자리로 친다. 옮긴 표를 다시 늘릴 때 빈 자리 계산의 여백에 막히지 않게 한다."""
    if lorom(addr) >= ORIGINAL_SIZE and (addr & 0xFFFF) + size <= 0x10000:
        return True
    spans = [((off // BANK) << 16 | 0x8000 | off % BANK, ((off // BANK) << 16 | 0x8000 | off % BANK) + n)
             for off, n in free_ranges(rom.d)]
    for lo, hi in extra:
        while hi & 0xFFFF and lorom(hi) < len(rom.d) and rom.d[lorom(hi)] == 0:
            hi += 1
        spans.append((lo, hi))
    return any(lo <= addr and addr + size <= hi for lo, hi in spans)


def table_writes(rom, kind, groups, at):
    """목록·그룹 표·코드 쓰기. 같은 뱅크면 표만 옮기고 목록을 밀고, 다른 뱅크면 목록과 표를 함께 옮긴다."""
    k = TABLE_KINDS[kind]
    original, size = k['original'], k['size']
    spans, table = group_spans(rom, kind=kind)
    bank, start = table & 0xFF0000, spans[0][0]
    blob = b''.join(b for g in groups for b in g)
    lists = [(bank | start, blob, f'{kind} 목록')]
    if len(groups) == len(spans) and len(blob) == spans[-1][1] - start and at is None:
        return lists
    moved_block = bank != original & 0xFF0000
    if at is None:
        at = bank | start if moved_block else (table if table != original else DEFAULT_TABLE[kind])
    table_size = 2 * len(groups) + 4
    if at >> 16 == original >> 16 and not moved_block:
        # 같은 뱅크: 목록은 제자리에서 밀고 그룹 표만 at 으로 옮긴다.
        limit = (original & 0xFFFF) + 2 * k['groups']
        if start + len(blob) > limit:
            raise ValueError(f'{kind}: 목록이 {start + len(blob) - limit}바이트 넘침(같은 뱅크에서는 옛 그룹 표 자리만큼만 '
                             f'늘어남, 다른 뱅크 00~3F 를 주면 표 덩어리를 옮김)')
        current = [(table, table + 2 * len(spans) + 4)] if table != original else []
        if not bank_free(rom, at, table_size, current):
            raise ValueError(f'{kind}: {cpu(at)}~ {table_size}바이트가 빈 자리가 아님')
        list_start, table_at = start, at
        out = lists
    else:
        # 다른 뱅크(또는 이미 옮긴 덩어리): [목록][그룹 표] 를 at 에 둔다.
        if at >> 16 > 0x3F:
            raise ValueError(f'{kind}: 뱅크 00~3F 만 됨(DB 로 WRAM·MMIO 를 abs 로 씀)')
        total = len(blob) + table_size
        current = [(bank | start, (table + 2 * len(spans) + 4))] if moved_block else []
        if (at & 0xFFFF) + total > 0x10000 or not bank_free(rom, at, total, current):
            raise ValueError(f'{kind}: {cpu(at)}~ {total}바이트가 한 뱅크의 빈 자리가 아님')
        list_start, table_at = at & 0xFFFF, (at & 0xFF0000) | (at + len(blob)) & 0xFFFF
        out = [(at, blob, f'{kind} 목록(옮김)')]
    starts, cursor = [], list_start
    for g in groups:
        starts.append(cursor)
        cursor += len(g) * size
    out.append((table_at, b''.join(v.to_bytes(2, 'little') for v in [*starts, cursor, 0]), f'{kind} 그룹 표(끝 표시·0000)'))
    out.append((k['db'], bytes([table_at >> 16]), f'{kind} 표 뱅크(DB)'))
    out += [(site, (table_at + i & 0xFFFF).to_bytes(2, 'little'), f'{kind} 표 주소') for i, site in enumerate(k['sites'])]
    return out


def door_writes(rom, plan, at):
    """새 맵·새 그룹에 빈 문 목록을 끼운 문 표. 처음 늘릴 때는 뱅크 01 전체를 door_bank 에 복사하고 그 복사본의
    D2FC 에 표를 둔 뒤, 여섯 입구를 JML 로 스텁에 보내 DB 를 door_bank 로 둔다(문 루틴이 DB 로 읽는 뱅크 01 의 다른
    자료도 복사본에서 같은 값으로 읽힌다). door_bank 는 비어 있어야 하고(롬 끝 너머이거나 모두 0), 이미 늘린 롬은
    복사본의 DOOR_DATA(입구 머리 제외)가 뱅크 01 과 같을 때만 다시 쓴다."""
    table = door_table(rom)
    groups = door_groups(rom, len(group_spans(rom)[0]))
    size = sum(len(m) for maps in groups for m in maps)
    if table == DOOR_TABLE and DOOR_TABLE + size > DOOR_END:
        # --allow-door-readthrough 로 만든 새 그룹은 표 뒤 코드를 문 목록으로 읽는다. 그대로 옮기면 그 바이트가 문이 된다.
        raise ValueError(f'문 표가 {cpu(DOOR_END)} 를 넘어 읽힘(문 표를 늘리지 않고 더한 그룹이 있음)')
    for g, maps in enumerate(plan.pointers):
        have = len(groups[g]) if g < len(groups) else 0
        if len(maps) <= have:
            continue
        add = [b'\x80'] * (len(maps) - have - 1) + [b'\xc0']
        if g < len(groups):
            last = groups[g][-1]
            groups[g][-1] = last[:-1] + bytes([last[-1] & 0x3F | 0x80])
            groups[g] += add
        else:
            groups.append(add)
    blob = b''.join(b''.join(maps) for maps in groups)
    if (DOOR_TABLE & 0xFFFF) + len(blob) > DOOR_DATA[0]:
        raise ValueError(f'문 표 {len(blob)}바이트가 복사본에서 문 루틴이 읽는 {DOOR_DATA[0]:04X} 를 덮음')
    if table != DOOR_TABLE:
        if at.get('door_bank') not in (None, table >> 16):
            raise ValueError(f'문 표는 이미 뱅크 {table >> 16:02X} 에 있음')
        jml = read(rom, DOOR_ENTRIES[-1], 4)
        stub = (0x010000 | jml[1] | jml[2] << 8) - (len(DOOR_ENTRIES) - 1) * STUB_SIZE
        if at.get('door_stub') not in (None, stub):
            raise ValueError(f'문 표 스텁은 이미 {cpu(stub)} 에 있음')
        lo, n = DOOR_DATA[0], DOOR_DATA[1] - DOOR_DATA[0]
        copy, here = read(rom, table & 0xFF0000 | lo, n), read(rom, 0x010000 | lo, n)
        for a in range(lo, lo + n):
            if copy[a - lo] != here[a - lo] and not any(e & 0xFFFF <= a < (e & 0xFFFF) + 4 for e in DOOR_ENTRIES):
                raise ValueError(f'뱅크 {table >> 16:02X} 복사본의 {a:04X} 가 뱅크 01 과 다름(복사 뒤 다른 패치가 뱅크 01 을 '
                                 '고침. 그 패치를 먼저 넣은 롬에서 문 표 패치를 다시 만듦)')
        return [(table, blob, '문 표')]
    bank = at['door_bank']
    if not 0x30 <= bank <= 0x3F:
        raise ValueError('--door-bank 는 30~3F(문 루틴이 그 DB 로 WRAM 을 abs 로 씀)')
    off = lorom(bank << 16 | 0x8000)
    if any(rom.d[off:off + 0x8000]):
        raise ValueError(f'--door-bank {bank:02X}: 뱅크 01 을 복사할 뱅크가 비어 있지 않음')
    copy = bytearray(read(rom, 0x018000, 0x8000))
    copy[(DOOR_TABLE & 0x7FFF):(DOOR_TABLE & 0x7FFF) + len(blob)] = blob
    stub = at.get('door_stub') or DOOR_STUB
    if stub >> 16 != 0x01 or not bank_free(rom, stub, STUB_SIZE * len(DOOR_ENTRIES)):
        raise ValueError(f'--door-stub-at {cpu(stub)}: 뱅크 01 의 빈 자리 {STUB_SIZE * len(DOOR_ENTRIES)}바이트가 필요함')
    out = [(bank << 16 | 0x8000, bytes(copy), '뱅크 01 복사본(문 표를 늘림)')]
    for i, entry in enumerate(DOOR_ENTRIES):
        at_stub = stub + i * STUB_SIZE
        out += [(at_stub, door_stub(entry, bank), f'문 표 입구 {cpu(entry)} 스텁'),
                (entry, bytes([0x5C, *at_stub.to_bytes(3, 'little')]), f'문 표 입구 {cpu(entry)}')]
    return out


def writes_for(rom, doc, base=Path('.'), at=None, allow_doors=False):
    at = at or {}
    plan = Plan(rom, doc, base)
    doors_handled = door_table(rom) != DOOR_TABLE or at.get('door_bank') is not None
    if not allow_doors and not doors_handled:
        original = entries(rom, 'pointer')[0]
        for bc, maps in enumerate(plan.pointers):
            for bd in range(len(original[bc]) if bc < len(original) else 0, len(maps)):
                door = door_readthrough(rom, bc, bd)
                if door is None or read(rom, door, 1)[0] < 0x80:
                    where = '표 밖' if door is None else f'{cpu(door)} 의 문 목록'
                    raise ValueError(f'{bc:02X}/{bd:02X}: 문 표(01:D2FC)를 건너뛰면 {where}을 읽음(--door-bank 로 문 표를 '
                                     '늘리거나 --allow-door-readthrough 로 그대로 만듦)')
    cursor, placed, out = at.get('records'), [], []
    if plan.records and not cursor:
        raise ValueError('새 레코드(source)를 놓을 --records-at 이 필요함')
    if plan.records and not bank_free(rom, cursor, sum(len(r) for _, r in plan.records)):
        raise ValueError(f'--records-at {cpu(cursor)}: 원래 롬의 빈 자리나 늘린 뱅크(30~)여야 함')
    for key, raw in plan.records:
        if (cursor & 0xFFFF) + len(raw) > 0x10000:
            raise ValueError(f'{key[0]:02X}/{key[1]:02X} 레코드가 {cpu(cursor)} 의 뱅크를 넘음')
        out.append((cursor, raw, f'맵 {key[0]:02X}/{key[1]:02X} 레코드'))
        placed.append(cursor)
        cursor += len(raw)

    def resolve(groups):
        return [[p if isinstance(p, bytes) else placed[p].to_bytes(3, 'little') for p in g] for g in groups]

    if any(v is None for g in plan.attrs for v in g):
        raise ValueError('속성이 없는 새 맵이 있음')
    out += table_writes(rom, 'pointer', resolve(plan.pointers), at.get('pointer'))
    out += table_writes(rom, 'attr', plan.attrs, at.get('attr'))
    out += table_writes(rom, 'high', resolve(plan.high), at.get('high'))
    out += entrance_writes(rom, plan, at.get('entrance'))
    if doors_handled:
        out += door_writes(rom, plan, at)
    spans = sorted((addr, addr + len(new), note) for addr, new, note in out)
    for (a1, e1, n1), (a2, _, n2) in zip(spans, spans[1:]):
        if a2 < e1:
            raise ValueError(f'자리가 겹침: {n1} {cpu(a1)} 와 {n2} {cpu(a2)}')
    result = []
    for addr, new, note in out:
        off = lorom(addr)
        old = bytes(rom.d[off:off + len(new)]) if off + len(new) <= len(rom.d) else None
        # 앞뒤가 같은 쓰기는 바뀐 곳만 쓴다. 다른 맵을 고치는 다른 쓰기와 겹치지 않게 한다.
        same = next((i for i, (a, b) in enumerate(zip(new, old or b'')) if a != b), min(len(new), len(old or b'')))
        if old is not None and same:
            addr, new, old = addr + same, new[same:], old[same:]
        tail = next((i for i, (a, b) in enumerate(zip(new[::-1], (old or b'')[::-1])) if a != b), 0)
        if old is not None and tail:
            new, old = new[:-tail], old[:-tail]
        if new and new != old:
            result.append((addr, new, old if lorom(addr) < ORIGINAL_SIZE else None, note))
    top = max([a >> 16 for a, _, _, _ in result] or [0])
    return result, 0 if top < 0x30 else 2 if top < 0x40 else 3 if top < 0x60 else 4


def entrance_writes(rom, plan, at):
    table = entrance_table(rom)
    blob = b''.join(plan.entrances)
    count = len(group_spans(rom)[0])
    if len(plan.entrances) == count and at is None:
        return [(table, blob, '들어가는 곳 표')]
    if at is None:
        if table == 0x0FEA97:
            raise ValueError('새 그룹을 더하면 들어가는 곳 표(0F:EA97)를 옮길 --entrance-table-at 이 필요함')
        at = table
    current = [(table, table + count * ENTRANCE_SIZE)] if table != 0x0FEA97 else []
    if (at & 0xFFFF) + len(blob) > 0x10000 or not bank_free(rom, at, len(blob), current):
        raise ValueError(f'들어가는 곳 표: {cpu(at)}~ {len(blob)}바이트가 한 뱅크의 빈 자리가 아님')
    return [(at, blob, '들어가는 곳 표(옮김)')] + [
        (site, (at + plus).to_bytes(3, 'little'), '들어가는 곳 표 주소') for site, plus in ENTRANCE_SITES]


def patch(rom, doc, base=Path('.'), at=None, allow_doors=False):
    writes, mb = writes_for(rom, doc, base, at, allow_doors)
    result = {'format': 'dq5patch/1', 'name': 'new-maps', 'writes': [
        {'at': cpu(a), 'hex': n.hex(' '), **({'orig': o.hex(' ')} if o is not None else {}), 'note': note}
        for a, n, o, note in writes]}
    if mb:
        result['rom_size'] = mb
    return result


def check(rom, doc, base=Path('.'), at=None, allow_doors=False):
    from dq5mapwrite import all_maps
    manifest = patch(rom, doc, base, at, allow_doors)
    mb = manifest.get('rom_size', 0)
    writes = [(lorom(int(w['at'][:2], 16) << 16 | int(w['at'][3:], 16)), bytes.fromhex(w['hex']),
               bytes.fromhex(w['orig']) if 'orig' in w else None, w['note']) for w in manifest['writes']]
    built = Rom(build(rom.d, [('new-maps', mb, writes)], mb)[0])
    before, after = set(all_maps(rom)), set(all_maps(built))
    plan = Plan(rom, doc, base)
    want = {(bc, bd) for bc, g in enumerate(plan.pointers) for bd in range(len(g))} | \
        {(HIGH_FIRST + i, HIGH_FIRST + bd) for i, g in enumerate(plan.high) for bd in range(len(g))}
    if after != want or not before <= after:
        raise ValueError('만든 롬의 맵 목록이 원래 맵 + 새 맵이 아님')
    old_attr, new_attr = entries(rom, 'attr')[0], entries(built, 'attr')[0]
    for bc, bd in sorted(before):
        if (bc, bd) in plan.changed:
            continue
        same = map_pointer(built, bc, bd) == map_pointer(rom, bc, bd)
        if bc < HIGH_FIRST:
            same = same and new_attr[bc][bd] == old_attr[bc][bd]
        if not same:
            raise ValueError(f'{bc:02X}/{bd:02X}: 고치지 않은 맵의 포인터나 속성이 바뀜')
    for bc, bd in sorted(plan.changed):
        ptrs = plan.high[bc - HIGH_FIRST] if bc >= HIGH_FIRST else plan.pointers[bc]
        value = ptrs[bd - HIGH_FIRST if bc >= HIGH_FIRST else bd]
        if isinstance(value, bytes) and map_pointer(built, bc, bd) != int.from_bytes(value, 'little'):
            raise ValueError(f'{bc:02X}/{bd:02X}: 맵 포인터가 입력과 다름')
        if bc < HIGH_FIRST and new_attr[bc][bd] != plan.attrs[bc][bd]:
            raise ValueError(f'{bc:02X}/{bd:02X}: 속성이 입력과 다름')
    table = entrance_table(built)
    if [read(built, table + g * ENTRANCE_SIZE, ENTRANCE_SIZE) for g in range(len(plan.entrances))] != plan.entrances:
        raise ValueError('들어가는 곳 표가 입력과 다름')
    if door_table(built) != DOOR_TABLE or door_table(rom) != DOOR_TABLE:
        doors = door_groups(built, len(plan.pointers))
        old = door_groups(rom, len(group_spans(rom)[0]))
        for bc, maps in enumerate(plan.pointers):
            if len(doors[bc]) != len(maps):
                raise ValueError(f'그룹 {bc:02X}: 문 표의 맵 수 {len(doors[bc])} 가 맵 수 {len(maps)} 와 다름')
            for bd, raw in enumerate(doors[bc]):
                prev = old[bc][bd] if bc < len(old) and bd < len(old[bc]) else raw[-1:]
                if raw[:-1] != prev[:-1] or raw[-1] & 0x3F != prev[-1] & 0x3F:
                    raise ValueError(f'{bc:02X}/{bd:02X}: 문 목록이 원래와 다름')
    if patch(built, doc, base, at, allow_doors)['writes']:
        raise ValueError('만든 롬에 같은 입력을 다시 패치하면 쓰기가 남음')
    added = sorted(after - before)
    print(f'맵 {len(before)}개 → {len(after)}개(새 {", ".join(f"{a:02X}/{b:02X}" for a, b in added) or "없음"}); '
          f'그룹 {len(group_spans(rom)[0])} → {len(group_spans(built)[0])}개; 표 '
          f'{cpu(group_table(built, "pointer"))}·{cpu(group_table(built, "attr"))}·{cpu(group_table(built, "high"))}'
          f'·들어가는 곳 {cpu(table)}; 쓰기 {len(writes)}개 검사 통과')


def address(text):
    if not re.fullmatch(r'[0-9A-Fa-f]{2}:[0-9A-Fa-f]{4}', text) or int(text[3:], 16) < 0x8000:
        raise argparse.ArgumentTypeError('BB:AAAA(AAAA 8000~FFFF) 로 적어야 함')
    return int(text[:2], 16) << 16 | int(text[3:], 16)


PLACES = {'pointer': '맵 포인터 그룹 표(같은 뱅크 0F 면 표만, 다른 뱅크면 덩어리)',
          'attr': '맵 속성 그룹 표(23 / 다른 뱅크)', 'high': '그룹 50 이상 맵 포인터 그룹 표(1F / 다른 뱅크)',
          'entrance': '들어가는 곳 표(새 그룹이 있으면 필요)', 'records': 'source 레코드',
          'door_stub': '문 표 입구 스텁(뱅크 01, 기본 01:FED0)'}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('rom', type=Path)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('patch', 'check'):
        p = sub.add_parser(name)
        p.add_argument('source', type=Path)
        if name == 'patch':
            p.add_argument('-o', '--out', type=Path, required=True)
        p.add_argument('--allow-door-readthrough', action='store_true',
                       help='새 맵이 문 표를 건너뛰어 다른 맵의 문 목록이나 표 밖을 읽어도 만듦')
        p.add_argument('--door-bank', type=lambda v: int(v, 16), help='문 표를 늘릴 때 뱅크 01 을 복사할 늘린 뱅크(30~3F)')
        for key, text in PLACES.items():
            p.add_argument(f'--{key.replace("_", "-")}{"-table" if key in ("pointer", "attr", "high", "entrance") else ""}-at',
                           dest=key, type=address, help=text)
    args = parser.parse_args()
    try:
        rom = Rom(args.rom.read_bytes())
        doc = json.loads(args.source.read_text(encoding='utf-8'))
        at = {k: getattr(args, k) for k in PLACES} | {'door_bank': args.door_bank}
        if args.command == 'check':
            check(rom, doc, args.source.parent, at, args.allow_door_readthrough)
        else:
            result = patch(rom, doc, args.source.parent, at, args.allow_door_readthrough)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return 0
    except (ValueError, OSError, KeyError, TypeError, PatchError) as error:
        print(f'오류: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
