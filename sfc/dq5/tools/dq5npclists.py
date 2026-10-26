"""dq5npcrelocate.py 가 쓰는 인물 목록 구조·등장 조건 표 편집.

목록의 인물 수·순서를 바꾸고(lists), 새 대체 목록을 더하고(new_lists), 대체 표(overrides)와
빈 맵 표(no_npc)를 통째로 다시 쓴다. 형식은 sfc/dq5/docs/dq5-build-format.md 의 「인물 목록 재배치」.

대체 표는 12:82FB 가 PHK·PLB 로 데이터 뱅크를 12 로 두고 $8449,Y 로만 읽어, 뱅크 12 밖으로
옮기려면 루틴을 바꿔야 한다. 12:82FB 를 「JSL 새 루틴; RTS」로 덮고, 새 루틴은 데이터 뱅크를 7E 로
두어 플래그를 $2190,Y 로 읽고 표는 긴 주소 ,X 로 읽는다. 빈 맵 표(12:8357)는 8비트 Y 로 4바이트씩
읽어 64항목에서 끝나므로 원래 자리(12:839C)에서 63항목+종료자까지 늘린다(옛 대체 표 자리를 덮음).
"""
import re

from dq5map import lorom
from dq5mapwrite import all_maps
from dq5npc import ALT_END, ALT_START, NO_NPC, OVERRIDE_LISTS, entry_size, list_entries
from dq5npcrecord import EDIT_KEYS, entry_bytes, map_name, map_number

OVERRIDE_COUNT, NO_NPC_COUNT = 296, 43
NO_NPC_MAX = 63
MAP_OBJECTS = 0x16F862      # 16:F60D 가 인물 뒤에 같은 슬롯 번호($81)로 놓는 맵 OBJ 물체 표(9바이트 항목)
SLOT_FIRST = 8              # 00:E1A9 가 $81 을 8 로 시작한다
SLOT_LIMIT = 0x1F           # 원본 모든 맵·낮밤에서 물체까지 놓은 뒤 $81(7E:1983) 의 최댓값
FIND_OVERRIDE = 0x1282FB
FIND_OVERRIDE_HEAD = bytes.fromhex('8b 08 4b ab c2 10')
NAME = re.compile(r'[A-Za-z0-9_-]{1,32}')


def cpu(addr):
    return f'{addr >> 16:02X}:{addr & 0xFFFF:04X}'


def read(rom, addr, size):
    off = lorom(addr)
    return bytes(rom.d[off:off + size])


def map_objects(rom, bc, bd, night):
    """16:F60D 가 실내 맵 bc/bd 에 놓는 맵 OBJ 물체 수. +4 bit7 이면 21:8000(7E:075E >= F0, 밤)으로 고르고 bit6 은 밤에만."""
    count, at = 0, MAP_OBJECTS
    while (group := rom.u8(at)) != 0xFF:
        mine = rom.u8(at + 1) & 0x7F
        if group == bc and mine in (0x7F, bd):
            flags = rom.u8(at + 4)
            count += not flags & 0x80 or bool(flags & 0x40) == night
        at += 9
    return count


def placed(raws, night):
    """엔트리 첫 바이트 bit7-6 으로 그 시간대에 놓이는 인물 수(12:8161·12:8227)."""
    return sum(bool(raw[0] & (0x40 if night else 0x80)) for raw in raws)


def entry_items(rom, lists, rows, own, records, label):
    """목록 하나의 새 엔트리 [(원본 엔트리 주소, 새 바이트)]."""
    if not isinstance(rows, list):
        raise ValueError(f'{label}.entries는 배열이어야 함')
    out = []
    for i, item in enumerate(rows):
        where = f'{label}.entries[{i}]'
        if not isinstance(item, dict) or item.keys() - {'from', *EDIT_KEYS}:
            raise ValueError(f'{where}: from 과 {sorted(EDIT_KEYS)} 만 받음')
        source = item.get('from')
        if type(source) is int and own is not None:
            at, index = own, source
        elif isinstance(source, dict) and source.keys() == {'list', 'index'} and isinstance(source['list'], str) \
                and re.fullmatch(r'[0-9A-Fa-f]{2}:[0-9A-Fa-f]{4}', source['list']):
            at, index = int(source['list'].replace(':', ''), 16), source['index']
        else:
            raise ValueError(f'{where}.from: 같은 목록의 번호 또는 {{"list": "BB:AAAA", "index": n}}')
        if at not in lists:
            raise ValueError(f'{where}.from: {cpu(at)}는 원본 인물 목록의 시작점이 아님')
        entries = lists[at]
        if type(index) is not int or not 0 <= index < len(entries):
            raise ValueError(f'{where}.from: 번호가 0~{len(entries) - 1} 밖')
        entry = entries[index]
        edit = {k: item[k] for k in EDIT_KEYS if k in item}
        if edit and entry in records:
            raise ValueError(f'{where}: {cpu(entry)}를 --records 와 lists 에서 함께 고침')
        raw = entry_bytes(rom, entry, edit, where) if edit else records.get(entry, read(rom, entry, entry_size(rom, entry)))
        out.append((entry, raw))
    return out


GROUP_COUNT = 54           # 05:D4B2 의 원래 그룹 포인터 수(00~35)
HIGH_GROUPS = 0x50         # 12:801C: 그룹 50 이상은 기본 목록을 읽지 않는다


def new_map_keys(original, new_maps):
    """--new-map 으로 더할 맵 [(BC, BD)]. 기존 그룹은 끝 번호부터, 새 그룹은 36 부터 차례로 맵 0 부터 빈틈없이 이어져야
    한다(dq5newmap.py 와 같은 규칙). 그룹 50 이상은 기본 목록이 없어 받지 않는다."""
    counts = {}
    for _, name in original:
        if re.fullmatch(r'[0-9A-F]{2}/[0-9A-F]{2}', name):
            bc = int(name[:2], 16)
            counts[bc] = counts.get(bc, 0) + 1
    out = sorted(set(new_maps))
    if len(out) != len(new_maps):
        raise ValueError('--new-map 에 같은 맵을 두 번 줌')
    groups = sorted({bc for bc, _ in out if bc not in counts})
    if groups and groups != list(range(GROUP_COUNT, GROUP_COUNT + len(groups))):
        raise ValueError('새 그룹은 36 부터 빈틈없이 이어져야 함: ' + ' '.join(f'{g:02X}' for g in groups))
    for bc, bd in out:
        if bc >= HIGH_GROUPS:
            raise ValueError(f'{map_name(bc, bd)}: 그룹 50 이상은 기본 인물 목록을 읽지 않음(12:801C)')
        want = counts.get(bc, 0) + sum(1 for g, d in out if g == bc and d < bd)
        if bd != want:
            raise ValueError(f'{map_name(bc, bd)}: 새 맵은 {map_name(bc, want)} 부터 이어져야 함')
    return out


def list_plan(rom, doc, original, records, new_maps=()):
    """[(목록 열쇠, [(원본 엔트리, 바이트)])] 기본·대체 두 영역. 열쇠는 원본 목록 주소, 'new:이름'(새 대체 목록),
    'GG/MM'(새 맵의 기본 목록). 새 맵 목록은 그 그룹 마지막 목록 뒤에 둔다(12:803F 가 00 끝 목록을 $BD 개 건너뜀)."""
    lists = {at: [a for a, _ in list_entries(rom, at)] for at, _ in original}
    by_map = {name: at for at, name in original if re.fullmatch(r'[0-9A-F]{2}/[0-9A-F]{2}', name)}
    fresh = {map_name(bc, bd): [] for bc, bd in new_map_keys(original, list(new_maps))}
    given = set()
    changed = {}
    rows = doc.get('lists', [])
    if not isinstance(rows, list):
        raise ValueError('lists는 배열이어야 함')
    for row in rows:
        if isinstance(row, dict) and row.keys() == {'map', 'entries'} and isinstance(row['map'], str):
            label = f'lists[{row["map"]}]'
            if not re.fullmatch(r'[0-9A-F]{2}/[0-9A-F]{2}', row['map']):
                raise ValueError(f'{label}: map 은 대문자 16진 GG/MM 이어야 함')
            if row['map'] in fresh:
                if row['map'] in given:
                    raise ValueError(f'{row["map"]}를 두 번 지정함')
                given.add(row['map'])
                fresh[row['map']] = entry_items(rom, lists, row['entries'], None, records, label)
                continue
            if row['map'] not in by_map:
                raise ValueError(f'{row["map"]}: 원본 맵도 --new-map 으로 준 맵도 아님')
            at = by_map[row['map']]
        elif isinstance(row, dict) and row.keys() == {'list', 'entries'} and isinstance(row['list'], str) \
                and re.fullmatch(r'[0-9A-Fa-f]{2}:[0-9A-Fa-f]{4}', row['list']):
            label = f'lists[{row["list"]}]'
            at = int(row['list'].replace(':', ''), 16)
            if at not in lists:
                raise ValueError(f'{row["list"]}는 원본 인물 목록의 시작점이 아님')
        else:
            raise ValueError('lists 항목은 list(BB:AAAA) 또는 map(GG/MM)과 entries 만 받음')
        if at in changed:
            raise ValueError(f'{label}: 같은 목록을 두 번 지정함')
        changed[at] = entry_items(rom, lists, row['entries'], at, records, label)
    news = doc.get('new_lists', [])
    if not isinstance(news, list):
        raise ValueError('new_lists는 배열이어야 함')
    created = []
    for row in news:
        if not isinstance(row, dict) or row.keys() != {'name', 'entries'} or not isinstance(row['name'], str) \
                or not NAME.fullmatch(row['name']):
            raise ValueError('new_lists 항목은 name(영문·숫자·_- 1~32자)과 entries 만 받음')
        key = 'new:' + row['name']
        if key in (k for k, _ in created):
            raise ValueError(f'새 목록 이름 {row["name"]}이 겹침')
        created.append((key, entry_items(rom, lists, row['entries'], None, records, key)))

    def items(at):
        if at in changed:
            return changed[at]
        return [(e, records.get(e, read(rom, e, entry_size(rom, e)))) for e in lists[at]]

    base_only = [(at, name) for at, name in original if not ALT_START <= at < ALT_END]
    base = []
    for i, (at, name) in enumerate(base_only):
        base.append((at, items(at)))
        if i + 1 == len(base_only) or base_only[i + 1][1][:2] != name[:2]:
            # 그룹 마지막 목록 뒤에 새 맵 목록을 번호 차례로 둔다.
            base.extend((key, fresh[key]) for key in sorted(k for k in fresh if k[:2] == name[:2]))
    # 새 그룹(36~)은 기본 목록 맨 뒤에 그룹·맵 차례로. 그룹 포인터는 dq5npcrelocate 가 표 끝에 더한다.
    old_groups = {name[:2] for _, name in base_only}
    base.extend((key, fresh[key]) for key in sorted(k for k in fresh if k[:2] not in old_groups))
    alt = [(at, items(at)) for at, _ in original if ALT_START <= at < ALT_END] + created
    return base, alt


def condition_row(row, known, targets, label):
    if not isinstance(row, dict) or row.keys() - {'map', 'flag', 'when', 'mask', 'list'} \
            or {'map', 'flag', 'when', 'mask'} - row.keys():
        raise ValueError(f'{label}: map·flag·when·mask(대체 표는 list 도)가 필요함')
    bc, bd = map_number(row['map'], known)
    flag = row['flag']
    if type(flag) is not int or not 0 <= flag <= 0x7F:
        raise ValueError(f'{label}.flag: 0~127 정수여야 함')
    if row['when'] not in ('on', 'off'):
        raise ValueError(f'{label}.when: on 또는 off')
    if type(row['mask']) is not int or row['mask'] not in (1, 2, 4, 8, 16, 32, 64, 128):
        raise ValueError(f'{label}.mask: 한 비트(1·2·4·…·128)여야 함')
    head = bytes([bc, bd, flag | (0x80 if row['when'] == 'off' else 0), row['mask']])
    if targets is None:
        if 'list' in row:
            raise ValueError(f'{label}: 빈 맵 표에는 list 가 없음')
        return head, None
    target = row.get('list')
    if isinstance(target, str) and target in targets:
        return head, target
    if isinstance(target, str) and re.fullmatch(r'[0-9A-Fa-f]{2}:[0-9A-Fa-f]{4}', target) \
            and int(target.replace(':', ''), 16) in targets:
        return head, int(target.replace(':', ''), 16)
    raise ValueError(f'{label}.list: 원본 대체 목록 시작점(10:xxxx) 또는 new:이름 이어야 함')


def condition_plan(rom, doc, records, alt_keys, new_maps=()):
    """(대체 표 [(조건 4바이트, 목록 열쇠)], 빈 맵 표 [4바이트], 대체 표를 옮기는지)."""
    known = set(all_maps(rom)) | set(new_maps)
    record_rows = {at for at in records if NO_NPC <= at < OVERRIDE_LISTS + OVERRIDE_COUNT * 6}
    moved = 'overrides' in doc or 'no_npc' in doc and isinstance(doc['no_npc'], list) and len(doc['no_npc']) > NO_NPC_COUNT
    if ('overrides' in doc or 'no_npc' in doc) and record_rows:
        raise ValueError('조건 표를 통째로 쓸 때는 --records 의 overrides·no_npc 를 함께 쓸 수 없음')
    if 'overrides' in doc:
        rows = doc['overrides']
        if not isinstance(rows, list):
            raise ValueError('overrides는 배열이어야 함')
        overrides = [condition_row(row, known, set(alt_keys), f'overrides[{i}]') for i, row in enumerate(rows)]
    else:
        overrides = []
        for i in range(OVERRIDE_COUNT):
            at = OVERRIDE_LISTS + i * 6
            raw = records.get(at, read(rom, at, 6))
            overrides.append((raw[:4], 0x100000 | raw[4] | raw[5] << 8))
    if 'no_npc' in doc:
        rows = doc['no_npc']
        if not isinstance(rows, list) or len(rows) > NO_NPC_MAX:
            raise ValueError(f'no_npc는 {NO_NPC_MAX}개 이하 배열이어야 함(12:8357 은 8비트 Y 로 64항목에서 끝남)')
        no_npc = [condition_row(row, known, None, f'no_npc[{i}]')[0] for i, row in enumerate(rows)]
    else:
        no_npc = None
    unused = {k for k in alt_keys if isinstance(k, str)} - {key for _, key in overrides}
    if unused:
        raise ValueError(f'대체 표가 가리키지 않는 새 목록: {", ".join(sorted(unused))}')
    if moved and read(rom, FIND_OVERRIDE, len(FIND_OVERRIDE_HEAD)) != FIND_OVERRIDE_HEAD:
        raise ValueError('12:82FB 가 원본 대체 표 찾기 루틴이 아님')
    return overrides, no_npc, moved


def slot_guard(rom, original, base, alt, overrides, allow_growth, new_maps=()):
    """맵·시간대마다 물체까지 놓은 뒤의 $81 이 원본 그 맵의 최댓값(allow_growth 면 SLOT_LIMIT)을 넘지 않게 한다."""
    def pairs(rows):
        out = {(tuple(int(v, 16) for v in name.split('/')), at) for at, name in original
               if re.fullmatch(r'[0-9A-F]{2}/[0-9A-F]{2}', name)}
        out.update(((head[0], head[1]), key) for head, key in rows)
        return out

    old_lists = {at: [read(rom, e, entry_size(rom, e)) for e, _ in list_entries(rom, at)] for at, _ in original}
    old_rows = [(read(rom, OVERRIDE_LISTS + i * 6, 4), 0x100000 | rom.u16(OVERRIDE_LISTS + i * 6 + 4))
                for i in range(OVERRIDE_COUNT)]
    most = {}
    for (bc, bd), at in pairs(old_rows):
        for night in (False, True):
            used = SLOT_FIRST + placed(old_lists[at], night) + map_objects(rom, bc, bd, night)
            most[bc, bd, night] = max(most.get((bc, bd, night), 0), used)
    new_lists = {key: [raw for _, raw in items] for key, items in base + alt}
    report = []
    fresh = {((bc, bd), map_name(bc, bd)) for bc, bd in new_maps}
    for (bc, bd), key in sorted(pairs(overrides) | fresh, key=str):
        for night in (False, True):
            used = SLOT_FIRST + placed(new_lists[key], night) + map_objects(rom, bc, bd, night)
            # 새 맵은 원본에 잰 값이 없어 원본 전체 최댓값까지 받는다(늘어난 맵으로 출력).
            limit = SLOT_LIMIT if allow_growth or (bc, bd) in new_maps else \
                most.get((bc, bd, night), SLOT_FIRST + map_objects(rom, bc, bd, night))
            name = key if isinstance(key, str) else cpu(key)
            if used > limit:
                raise ValueError(f'{map_name(bc, bd)} {"밤" if night else "낮"} {name}: 인물·물체 뒤 슬롯 {used:#04x} 가 '
                                 f'한도 {limit:#04x} 를 넘음' + ('' if allow_growth else '(--allow-growth 로 1F 까지)'))
            if used > most.get((bc, bd, night), SLOT_FIRST + map_objects(rom, bc, bd, night)):
                report.append(f'{map_name(bc, bd)} {"밤" if night else "낮"} {name} 슬롯 {used:#04x}')
    return report


def assemble_find(table, alt_bank):
    """12:82FB 를 대신하는 루틴. 표는 [BC][BD][플래그][마스크][포인터 16비트] 6바이트, FF 로 끝."""
    def long(op, plus):
        a = table + plus
        return [op, a & 0xFF, a >> 8 & 0xFF, a >> 16]

    code, labels, fixes = [], {}, []

    def emit(*parts):
        for part in parts:
            code.extend(part if isinstance(part, list) else [part])

    def branch(op, label):
        code.append(op)
        fixes.append((len(code), label))
        code.append(0)

    emit(0x8B, 0x08, [0xE2, 0x20], [0xC2, 0x10], [0xA9, 0x7E], 0x48, 0xAB, [0xA2, 0x00, 0x00])
    labels['loop'] = len(code)
    emit(long(0xBF, 0), [0xC9, 0xFF])
    branch(0xF0, 'none')
    emit([0xC5, 0xBC])
    branch(0xD0, 'next')
    emit(long(0xBF, 1), [0xC5, 0xBD])
    branch(0xD0, 'next')
    emit(long(0xBF, 2), [0x85, 0x00], [0xC2, 0x20], [0x29, 0x7F, 0x00], 0xA8, [0xE2, 0x20],
         [0xB9, 0x90, 0x21], long(0x3F, 3))
    branch(0xF0, 'off')
    emit([0xA5, 0x00])
    branch(0x30, 'next')
    branch(0x80, 'hit')
    labels['off'] = len(code)
    emit([0xA5, 0x00])
    branch(0x10, 'next')
    labels['hit'] = len(code)
    emit(long(0xBF, 4), [0x85, 0xA5], long(0xBF, 5), [0x85, 0xA6], [0xA9, alt_bank], [0x85, 0xA7],
         0x28, 0xAB, 0x38, 0x6B)
    labels['next'] = len(code)
    emit([0xC2, 0x20], 0x8A, 0x18, [0x69, 0x06, 0x00], 0xAA, [0xE2, 0x20])
    branch(0x80, 'loop')
    labels['none'] = len(code)
    emit(0x28, 0xAB, 0x18, 0x6B)
    for at, label in fixes:
        delta = labels[label] - (at + 1)
        if not -128 <= delta <= 127:
            raise ValueError('루틴 분기가 너무 멂')
        code[at] = delta & 0xFF
    return bytes(code)
