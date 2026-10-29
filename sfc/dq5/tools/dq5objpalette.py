"""DQ5 필드 OBJ 팔레트 색, 인물 세트의 팔레트 배정, 맵 팔레트 줄 쓰기.

맵을 불러올 때 01:93AE 가 1F:D45F 를 불러 04:96D6 의 256바이트(OBJ 팔레트 0~7, 16색씩)를 CGRAM 사본 7E:3A14 로
옮기고, 이어 01:93B2 → 01:996A 가 맵마다 덮는 16색 줄(01:9A12, 0x23바이트 항목)을 적용한다.
인물 세트는 레코드(1F:D63D) +2 bit6-7 로 OBJ 팔레트 0~3 중 하나를 쓴다. 1F:CFC8(6타일)·1F:D0FB(8타일)가 그 값을
OAM 속성의 팔레트 비트로 바꿔 칸 목록 7E:8060- 에 ORA 하고, 03:D24D 는 인물 그림을 바꿀 때 같은 값을 $08 에 둔다.
입력 형식은 sfc/dq5/docs/dq5-build-format.md 의 「OBJ 팔레트·세트 팔레트 배정」.

--at 을 주면 두 가지를 그 자리에 둔다.
- 세트 팔레트 표: 세 곳을 JSL 로 바꾸고, 루틴이 256칸 표[세트](FF 면 레코드 그대로)를 OBJ 팔레트 0~7 로 쓴다.
  sets 에 팔레트 4~7 이 있으면 표를 놓고, 이미 표가 있는 롬이면 sets 는 그 표에 쓴다(레코드는 그대로).
- 맵 팔레트 줄 늘리기(new_map_palettes): 01:996A~9A11 루틴과 01:9954 입구를 그 자리로 옮기고 표를 늘린다.
  01:996A·01:9954 는 JSL 옮긴 루틴 / RTS 가 된다. 루틴이 표와 $1949 를 DB 기준 abs 로 읽으므로 뱅크 00~3F 만 받는다.
dump 의 users·map·line 은 보기용이라 쓰기에서 읽지 않는다(map·line 은 바꾸면 거부).

  python sfc/dq5/tools/dq5objpalette.py rom/dq5.sfc dump -o work/objpalette.json
  python sfc/dq5/tools/dq5objpalette.py rom/dq5.sfc patch work/objpalette.json -o work/objpalette.dq5patch.json [--at 3B:8000]
  python sfc/dq5/tools/dq5objpalette.py rom/dq5.sfc check [work/objpalette.json] [--at 3B:8000]

문서(dq5objpalette/1):
  {"format": "dq5objpalette/1",
   "palettes": [{"palette": 1, "colors": [15개]}],             # OBJ 팔레트 0~7 의 색 1~15(0 번은 투명이라 두지 않음)
   "map_palettes": [{"index": 3, "colors": [15개]}],           # 01:9A12 의 기존 항목 색 1~15(맵·조건·줄은 그대로)
   "new_map_palettes": [{"map": "02/06", "line": "0E", "flag": "FF", "mask": "00", "colors": [15개]}],  # --at 이 필요
   "sets": [{"set": "84", "palette": 6}]}                      # 인물 세트가 쓰는 OBJ 팔레트(0~7, 4~7 은 --at 이 필요)
new_map_palettes 의 map 은 BC/BD(BD = FF 면 그룹 전부), 필드는 FE/세계. 표 끝에 붙으므로 같은 줄을 덮는 앞 항목보다 나중에 적용된다.
flag 는 7E:2190 의 바이트 번호(bit7 이면 꺼졌을 때 참, FF 면 늘), mask 는 그 바이트의 비트.
dump 는 팔레트마다 그 팔레트를 쓰는 세트와 그림 번호를 함께 적는다(users). 쓰기에서는 읽지 않는다.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dq5sprite as S  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402

FORMAT = 'dq5objpalette/1'
PALETTES = 8                    # 1F:D463 이 256바이트를 옮긴다
MAP_ENTRY = 0x23
# 세트 팔레트를 OAM 속성 비트로 만드는 원래 명령. 1F 둘은 LDY #$02 / LDA [$09],Y / AND #$C0 / LSR×5 / STA $01(8비트 X).
SITE_ORIG = bytes.fromhex('a0 02 b7 09 29 c0 4a 4a 4a 4a 4a 85 01')
# 03:D24D 는 LDY #$0002 / LDA [$00],Y / LSR×5 / STA $08(16비트 X). AND 가 없어 자료 뱅크 bit5 가 OAM 타일 bit8 로 간다.
SWAP_SITE = 0x03D24D
SWAP_ORIG = bytes.fromhex('a0 02 00 b7 00 4a 4a 4a 4a 4a 85 08')
# 03:D202 LDA $2586D0,X. 03:D24D 루틴은 그림 번호($1EC0)를 세트로 바꿀 때 이 명령의 24비트 피연산자를 실행 중에 읽는다.
# dq5picturegrow.py 가 그림 표를 옮기면 이 피연산자가 바뀌므로, 어느 순서로 패치해도 같은 표를 본다.
PICTURE_SITE = 0x03D202
MAP_LOADER, MAP_ALT = 0x01996A, 0x019954
MAP_LOADER_SIZE = 0xA8          # 01:996A~9A11
# 01:9954: PHP / PHB / REP #$30 / LDA #$3B14 / LDX #$007E / BRA $9976. DB 는 부르는 01:994A 가 01 로 둔다.
MAP_ALT_ORIG = bytes.fromhex('08 8b c2 30 a9 14 3b a2 7e 00 80 16')
# 옮길 때 고치는 곳(루틴 안 오프셋): 표 abs 일곱 곳(명령, 표 안 오프셋), 루틴 안 JMP 둘(원래 대상), 끝 RTS.
MAP_TABLE_REFS = {0x15: (0xBD, 0), 0x28: (0xBD, 1), 0x33: (0xBD, 2), 0x49: (0x3D, 3), 0x6C: (0xDD, 1), 0x79: (0xBD, 4),
                  0x94: (0xBD, 0)}
MAP_JUMPS = {0x71: 0x999D, 0xA5: 0x997D}
MAP_RTS = 0x64
MAP_ALT_INTO = 0x0C             # 01:9954 의 BRA 가 닿는 01:9976


def cpu(addr):
    return f'{addr >> 16:02X}:{addr & 0xFFFF:04X}'


def keys(value, allowed, name):
    if not isinstance(value, dict) or value.keys() - allowed:
        raise ValueError(f'{name}: 허용한 키 {sorted(allowed)}만 있는 객체여야 함')


def colors15(value, name):
    if not isinstance(value, list) or len(value) != 15 or any(type(c) is not int or not 0 <= c <= 0x7FFF for c in value):
        raise ValueError(f'{name}: 0~7FFF 정수 15개(색 1~15)여야 함')
    return value


def hex2(value, name, high=0xFF):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9A-Fa-f]{2}', value) or int(value, 16) > high:
        raise ValueError(f'{name}: 00~{high:02X} 두 자리 16진 문자열이어야 함')
    return int(value, 16)


def palette_colors(rom, p):
    return [rom.u16(S.OBJ_PALETTES + (p * 16 + i) * 2) for i in range(1, 16)]


def set_palettes(rom):
    """{세트: OAM 에 쓰는 OBJ 팔레트}."""
    table = S.set_palette_table(rom)
    return {s: S.set_obj_palette(rom, s, table) for s in S.set_numbers(rom) if S.set_record(rom, s) is not None}


def pictures(rom):
    """[(그림 번호, 세트)]. 그림 표 주소·개수는 dq5picturegrow.layout(옮긴 롬이면 늘린 표)."""
    from dq5picturegrow import layout
    base, count, _ = layout(rom)
    return [(g, rom.u8(base + g)) for g in range(count)]


def users(rom):
    """팔레트마다 (세트, 그 세트를 쓰는 그림 번호들)."""
    gfx = {}
    for g, s in pictures(rom):
        gfx.setdefault(s, []).append(g)
    out = {p: [] for p in range(PALETTES)}
    for s, p in set_palettes(rom).items():
        out[p].append({'set': f'{s:02X}', 'gfx': [f'{g:02X}' for g in gfx.get(s, [])]})
    return out


def dump(rom):
    who = users(rom)
    return {'format': FORMAT,
            'palettes': [{'palette': p, 'colors': palette_colors(rom, p), **({'users': who[p]} if who[p] else {})}
                         for p in range(PALETTES)],
            'map_palettes': [{'index': i, 'map': f'{e["bc"]:02X}/{e["bd"]:02X}', 'line': f'{e["line"]:02X}',
                              'colors': e['colors'][1:]} for i, e in enumerate(S.map_palettes(rom))],
            'sets': [{'set': f'{s:02X}', 'palette': p} for s, p in set_palettes(rom).items()]}


def at_cpu(at):
    if not re.fullmatch(r'[0-9A-Fa-f]{2}:[0-9A-Fa-f]{4}', at or ''):
        raise ValueError(f'--at {at!r}: BB:AAAA 로 적어야 함')
    b, a = int(at[:2], 16), int(at[3:], 16)
    if not (b <= 0x3F and a >= 0x8000):
        raise ValueError(f'--at {at}: 뱅크 00~3F, AAAA 8000~FFFF 여야 함(옮긴 맵 팔레트 루틴이 $1949 를 abs 로 읽음)')
    return b << 16 | a


def map_rows(rom, rows):
    """new_map_palettes → 0x23바이트 항목들."""
    if not isinstance(rows, list):
        raise ValueError('new_map_palettes는 배열이어야 함')
    if not rows:
        return []
    from dq5palsetwrite import known_maps
    maps = known_maps(rom)
    out = []
    for i, row in enumerate(rows):
        label = f'new_map_palettes[{i}]'
        keys(row, {'map', 'line', 'flag', 'mask', 'colors'}, label)
        if not isinstance(row.get('map'), str) or not re.fullmatch(r'[0-9A-Fa-f]{2}/[0-9A-Fa-f]{2}', row['map']):
            raise ValueError(f'{label}.map: BC/BD 두 자리 16진')
        bc, bd = (int(v, 16) for v in row['map'].split('/'))
        if bc == 0xFE:
            if bd > 2:
                raise ValueError(f'{label}.map: 필드는 FE/00~FE/02(세계)')
        elif bc not in maps or bd != 0xFF and bd not in maps[bc]:
            raise ValueError(f'{label}.map: 맵 {bc:02X}/{bd:02X} 이 롬에 없음')
        line = hex2(row.get('line'), f'{label}.line', 0x0F)
        flag = hex2(row.get('flag', 'FF'), f'{label}.flag')
        mask = hex2(row.get('mask', '00'), f'{label}.mask')
        if (flag == 0xFF) != (mask == 0):
            raise ValueError(f'{label}.mask: flag 가 FF(늘)면 00, 아니면 0 이 아닌 비트여야 함')
        colors = colors15(row.get('colors'), f'{label}.colors')
        out.append(bytes([bc, bd, flag, mask, line]) + b''.join(c.to_bytes(2, 'little') for c in colors))
    return out


def set_rows(rom, rows):
    """{세트: 팔레트}."""
    if not isinstance(rows, list):
        raise ValueError('sets는 배열이어야 함')
    out = {}
    for i, row in enumerate(rows):
        label = f'sets[{i}]'
        keys(row, {'set', 'palette'}, label)
        name = row.get('set')
        if not isinstance(name, str) or not re.fullmatch(r'[0-9A-Fa-f]{2}', name):
            raise ValueError(f'{label}.set: 두 자리 16진 문자열')
        s = int(name, 16)
        if s not in S.set_numbers(rom) or S.set_record(rom, s) is None or s in out:
            raise ValueError(f'{label}: 세트 {name}가 없거나 두 번 지정함')
        p = row.get('palette')
        if type(p) is not int or not 0 <= p < PALETTES:
            raise ValueError(f'{label}.palette: 0~7 정수(4~7 은 --at 의 세트 팔레트 표)')
        out[s] = p
    return out


def set_routine(table):
    """1F:CFC8·1F:D0FB 가 JSL 로 부르는 루틴(8비트 M·X). 원래 명령처럼 Y = 2 로 두고 $01 에 OAM 속성 팔레트 비트를 둔다."""
    return (S.SET_PALETTE_ROUTINE + table.to_bytes(3, 'little') +
            bytes.fromhex('30 03'                           # BMI 레코드(표 값 FF)
                          '0a 80 09'                        # ASL / BRA 두기
                          'b7 09 29 c0 4a 4a 4a 4a 4a'      # 레코드: 원래 명령 그대로
                          '85 01 6b'))                      # 두기: STA $01 / RTL


def swap_routine(table):
    """03:D24D 가 JSL 로 부르는 루틴(8비트 M, 16비트 X). 그림 번호 $1EC0 을 세트로 바꿔 표를 찾고, FF 면 원래 명령.
    그림 표는 03:D202 의 피연산자(뱅크 → DB, 주소 + 그림 번호 → X)로 찾는다."""
    operand, bank = PICTURE_SITE + 1, PICTURE_SITE + 3
    return (bytes.fromhex('da 8b af') + bank.to_bytes(3, 'little') +     # PHX / PHB / LDA 그림 표 뱅크
            bytes.fromhex('48 ab c2 20 af c0 1e 7e 29 ff 00 18 6f') +    # PHA / PLB / REP #$20 / LDA $7E1EC0 / AND #$00FF / CLC / ADC
            operand.to_bytes(3, 'little') +                              # 그림 표 주소(16비트)
            bytes.fromhex('aa e2 20 bd 00 00 ab'                         # TAX / SEP #$20 / LDA $0000,X / PLB
                          'c2 20 29 ff 00 aa e2 20') +                   # REP #$20 / AND #$00FF / TAX / SEP #$20
            bytes.fromhex('a0 02 00') + b'\xbf' + table.to_bytes(3, 'little') +
            bytes.fromhex('30 03 0a 80 07'                     # BMI 레코드 / ASL / BRA 두기
                          'b7 00 4a 4a 4a 4a 4a'               # 레코드: 원래 명령 그대로
                          '85 08 fa 6b'))                      # 두기: STA $08 / PLX / RTL


def map_routine(rom, at):
    """[01:9954 입구][01:996A~9A11] 를 at 으로 옮긴 바이트(표는 바로 뒤)와 (9954 입구, 996A 입구, 표) 주소."""
    raw = bytes(rom.d[lorom(MAP_LOADER):lorom(MAP_LOADER) + MAP_LOADER_SIZE])
    alt = bytes(rom.d[lorom(MAP_ALT):lorom(MAP_ALT) + len(MAP_ALT_ORIG)])
    expect = [(0, 0x08), (1, 0x8B), (2, 0x4B), (3, 0xAB), (MAP_RTS, 0x60)] + [(o, op) for o, (op, _) in MAP_TABLE_REFS.items()]
    word = lambda o: int.from_bytes(raw[o + 1:o + 3], 'little')  # noqa: E731
    if alt != MAP_ALT_ORIG or any(raw[o] != v for o, v in expect) or \
            any(word(o) != S.MAP_PALETTES + k & 0xFFFF for o, (_, k) in MAP_TABLE_REFS.items()) or \
            any(raw[o] != 0x4C or word(o) != t for o, t in MAP_JUMPS.items()):
        raise ValueError(f'{cpu(MAP_LOADER)}: 원래 맵 팔레트 루틴이 아님')
    # 01:9954 는 DB 를 부르는 쪽에 맡기지만 옮긴 루틴은 자기 뱅크의 표를 읽으므로 PHK / PLB 를 넣는다.
    head = bytes.fromhex('08 8b 4b ab c2 30 a9 14 3b a2 7e 00 80') + bytes([MAP_ALT_INTO])
    code = bytearray(raw)
    entry = at + len(head)
    table = entry + len(raw)
    for o, (_, k) in MAP_TABLE_REFS.items():
        code[o + 1:o + 3] = (table + k & 0xFFFF).to_bytes(2, 'little')
    for o, t in MAP_JUMPS.items():
        code[o + 1:o + 3] = (entry + t - MAP_LOADER & 0xFFFF).to_bytes(2, 'little')
    code[MAP_RTS] = 0x6B
    return head + bytes(code), (at, entry, table)


def edits(rom, doc, at=None):
    """[(주소, 새 바이트, 원본 바이트 또는 None(새 자리), 설명)]."""
    keys(doc, {'format', 'palettes', 'map_palettes', 'new_map_palettes', 'sets'}, '문서')
    if doc.get('format') != FORMAT:
        raise ValueError(f'format={FORMAT}이 필요함')
    out = []
    rows = doc.get('palettes', [])
    if not isinstance(rows, list):
        raise ValueError('palettes는 배열이어야 함')
    seen = set()
    for i, row in enumerate(rows):
        label = f'palettes[{i}]'
        # dump 가 붙이는 설명 키(users)는 받되 쓰지 않는다.
        keys(row, {'palette', 'colors', 'users'}, label)
        n = row.get('palette')
        if type(n) is not int or not 0 <= n < PALETTES or n in seen:
            raise ValueError(f'{label}.palette: 0~{PALETTES - 1} 정수이고 한 번만 지정함')
        seen.add(n)
        new = b''.join(c.to_bytes(2, 'little') for c in colors15(row.get('colors'), f'{label}.colors'))
        a = S.OBJ_PALETTES + (n * 16 + 1) * 2
        out.append((a, new, bytes(rom.d[lorom(a):lorom(a) + 30]), f'OBJ 팔레트 {n} 색 1~15'))

    entries = S.map_palettes(rom)
    rows = doc.get('map_palettes', [])
    if not isinstance(rows, list):
        raise ValueError('map_palettes는 배열이어야 함')
    colored, seen = {}, set()
    for i, row in enumerate(rows):
        label = f'map_palettes[{i}]'
        keys(row, {'index', 'colors', 'map', 'line'}, label)
        n = row.get('index')
        if type(n) is not int or not 0 <= n < len(entries) or n in seen:
            raise ValueError(f'{label}.index: 0~{len(entries) - 1} 정수이고 한 번만 지정함')
        seen.add(n)
        e = entries[n]
        if row.get('map', f'{e["bc"]:02X}/{e["bd"]:02X}') != f'{e["bc"]:02X}/{e["bd"]:02X}' or \
                row.get('line', f'{e["line"]:02X}') != f'{e["line"]:02X}':
            raise ValueError(f'{label}: map·line 은 바꿀 수 없음(원본 {e["bc"]:02X}/{e["bd"]:02X} 줄 {e["line"]:02X})')
        colored[n] = b''.join(c.to_bytes(2, 'little') for c in colors15(row.get('colors'), f'{label}.colors'))
    added = map_rows(rom, doc.get('new_map_palettes', []))
    if added and rom.u8(MAP_LOADER) == 0x22:
        raise ValueError(f'{cpu(MAP_LOADER)}: 맵 팔레트 표를 이미 옮긴 롬. new_map_palettes 를 모두 담아 원본 롬에서 다시 만듦')
    if added and at is None:
        raise ValueError('new_map_palettes 는 표를 옮길 --at 이 필요함')
    if not added:
        for n, new in colored.items():
            e = entries[n]
            out.append((e['entry'] + 5, new, bytes(rom.d[lorom(e['entry'] + 5):lorom(e['entry'] + 5) + 30]),
                        f'맵 팔레트 {n}({e["bc"]:02X}/{e["bd"]:02X} 줄 {e["line"]:02X}) 색 1~15'))

    sets = set_rows(rom, doc.get('sets', []))
    table = S.set_palette_table(rom)
    before = set_palettes(rom)
    changed = {s: p for s, p in sets.items() if p != before[s]}
    hook = table is None and any(p > 3 for p in changed.values())
    if hook and at is None:
        raise ValueError('세트 팔레트 4~7 은 세트 팔레트 표를 둘 --at 이 필요함(레코드 칸은 0~3)')
    if table is not None:
        for s, p in changed.items():
            out.append((table + s, bytes([p]), bytes([rom.u8(table + s)]), f'세트 {s:02X} 팔레트 {before[s]} → {p}(표)'))
    elif not hook:
        for s, p in changed.items():
            rec = S.set_record(rom, s)
            old = rom.u8(rec['record'] + 2)
            out.append((rec['record'] + 2, bytes([old & 0x3F | p << 6]), bytes([old]), f'세트 {s:02X} 팔레트 {before[s]} → {p}'))

    place = None if at is None else at_cpu(at)
    blob, notes = b'', []
    if hook:
        swap_at = place + len(set_routine(0))
        new_table = swap_at + len(swap_routine(0))
        cells = bytearray([0xFF] * 0x100)
        for s, p in changed.items():
            cells[s] = p
        blob = set_routine(new_table) + swap_routine(new_table) + bytes(cells)
        notes.append(f'세트 팔레트 루틴·표(세트 {len(changed)}개)')
        if rom.u8(PICTURE_SITE) != 0xBF:
            raise ValueError(f'{cpu(PICTURE_SITE)}: 그림 표 읽기(LDA long,X)가 아님. 03:D24D 루틴이 이 피연산자를 읽음')
        for site, orig, entry in ((S.SET_PALETTE_SITES[0], SITE_ORIG, place), (S.SET_PALETTE_SITES[1], SITE_ORIG, place),
                                  (SWAP_SITE, SWAP_ORIG, swap_at)):
            if bytes(rom.d[lorom(site):lorom(site) + len(orig)]) != orig:
                raise ValueError(f'{cpu(site)}: 원래 세트 팔레트 명령이 아님(이미 고친 롬이면 원본에서 다시 만듦)')
            out.append((site, bytes([0x22, *entry.to_bytes(3, 'little')]) + b'\xea' * (len(orig) - 4), orig,
                        'OBJ 팔레트를 세트 팔레트 표에서 고름(JSL)'))
    if added:
        code, (alt, entry, _) = map_routine(rom, place + len(blob))
        body = bytearray()
        for n, e in enumerate(entries):
            raw = bytearray(rom.d[lorom(e['entry']):lorom(e['entry']) + MAP_ENTRY])
            if n in colored:
                raw[5:] = colored[n]
            body += raw
        blob += code + bytes(body) + b''.join(added) + b'\xff'
        notes.append(f'맵 팔레트 루틴·표({len(entries)}+{len(added)}항목)')
        for site, target, note in ((MAP_LOADER, entry, '맵 팔레트 줄을 옮긴 루틴으로(JSL / RTS)'),
                                   (MAP_ALT, alt, '맵 팔레트 줄(7E:3B14 쪽 입구)을 옮긴 루틴으로(JSL / RTS)')):
            out.append((site, bytes([0x22, *target.to_bytes(3, 'little'), 0x60]),
                        bytes(rom.d[lorom(site):lorom(site) + 5]), note))
    if blob:
        if (place & 0xFFFF) + len(blob) > 0x10000:
            raise ValueError(f'--at {at}: 루틴·표 {len(blob)}바이트가 뱅크 끝을 넘음')
        # 새 자리는 orig 를 붙이지 않는다. 빌더가 빈 자리 지도 밖이면 거부하게 하기 위해서다.
        out.append((place, blob, None, ', '.join(notes)))
    return out


def patch(rom, doc, at=None):
    writes, top, record = [], 0, False
    for addr, new, old, note in edits(rom, doc, at):
        record |= bool(re.match(r'세트 [0-9A-F]{2} 팔레트 .*\d$', note))
        if new == old:
            continue
        w = {'at': cpu(addr), 'hex': new.hex(' '), 'note': note}
        if old is not None:
            w['orig'] = old.hex(' ')
        writes.append(w)
        top = max(top, addr >> 16)
    if record:
        # 세트 팔레트는 지금 표가 가리키는 레코드에 쓴다. 같은 빌드에서 dq5spritewrite.py --sets-at 이 표와 레코드를
        # 옮기면 이 쓰기는 죽은 레코드에 떨어지므로, 표 주소 피연산자를 그대로 다시 써 빌더가 겹침으로 막게 한다.
        site = S.SET_TABLE_SITES[0]
        raw = bytes(rom.d[lorom(site):lorom(site) + 3]).hex(' ')
        writes.append({'at': cpu(site), 'hex': raw, 'orig': raw, 'note': '세트 포인터 표 주소(그대로, --sets-at 과 함께 쓰지 않게)'})
    result = {'format': 'dq5patch/1', 'name': 'obj-palettes', 'writes': writes}
    if top >= 0x30:
        result['rom_size'] = 2
    return result


def overridden(rom, doc):
    """바꾼 OBJ 팔레트 줄을 맵마다 덮는 01:9A12 항목(새 항목 포함). 그 맵에서는 바꾼 색이 보이지 않는다."""
    changed = {row['palette'] for row in doc.get('palettes', []) if row['colors'] != palette_colors(rom, row['palette'])}
    lines = [(e['bc'], e['bd'], e['line']) for e in S.map_palettes(rom)]
    lines += [(r[0], r[1], r[4]) for r in map_rows(rom, doc.get('new_map_palettes', []))]
    return {p: [f'{bc:02X}/{bd:02X}' for bc, bd, line in lines if line == 8 + p] for p in sorted(changed)}


def after_sets(rom, doc):
    after = set_palettes(rom)
    for row in doc.get('sets', []):
        after[int(row['set'], 16)] = row['palette']
    return after


def affected(rom, doc):
    """바꾼 OBJ 팔레트를 쓰는 세트(새 배정 포함)."""
    after = after_sets(rom, doc)
    changed = {row['palette'] for row in doc.get('palettes', []) if row['colors'] != palette_colors(rom, row['palette'])}
    return {p: sorted(f'{s:02X}' for s, q in after.items() if q == p) for p in sorted(changed)}


def shared_lines(rom, doc):
    """세트에 준 OBJ 팔레트 4~7 마다 그 줄을 함께 쓰는 것: 세트, 맵 OBJ 물체(16:F862), 그 줄을 덮는 맵(01:9A12·새 항목)."""
    after = after_sets(rom, doc)
    lines = [(e['bc'], e['bd'], e['line']) for e in S.map_palettes(rom)]
    lines += [(r[0], r[1], r[4]) for r in map_rows(rom, doc.get('new_map_palettes', []))]
    out = {}
    for p in sorted({q for q in after.values() if q > 3}):
        out[p] = {'sets': sorted(f'{s:02X}' for s, q in after.items() if q == p),
                  'objects': sorted({f'{m["bc"]:02X}/{m["bd"]:02X}' for m in S.map_object_places(rom) if m['palette'] == p}),
                  'map_lines': sorted({f'{bc:02X}/{bd:02X}' for bc, bd, line in lines if line == 8 + p})}
    return out


class Done(Exception):
    pass


def run_cells(data, s):
    """1F:CFA9(6타일)·1F:D0DC(8타일)를 그대로 돌려 칸 목록 48개(7E:8060-)를 얻는다. 7E:21B3 bit3 을 켜 둔다(1F:D051)."""
    from w65816 import Cpu
    c = Cpu(data, bytearray(0x20000))
    c.wram[0x0C], c.wram[0x0D], c.wram[0xA0], c.wram[0x21B3] = s, 0, 0, 0x08
    c.p = 0x30
    c.jsr(0x1FD0DC if s & 0x80 else 0x1FCFA9)
    return [c.wram[0x8060 + i * 2] | c.wram[0x8061 + i * 2] << 8 for i in range(48)]


def run_swap(data, g, record):
    """03:D24D 의 명령(훅이면 그 루틴)만 돌려 ($08, Y)."""
    from w65816 import Cpu
    c = Cpu(data, bytearray(0x20000))
    c.wram[0x1EC0] = g
    c.wram[0:3] = record.to_bytes(3, 'little')
    c.p = 0x20

    def stop(_):
        raise Done

    c.hooks[SWAP_SITE + len(SWAP_ORIG)] = stop
    c.pbr, c.pc = SWAP_SITE >> 16, SWAP_SITE & 0xFFFF
    try:
        c.run(10000)
    except Done:
        pass
    return c.wram[0x08], c.y


def run_lines(data, bc, bd, indoor, world, entry):
    """01:996A(또는 01:9954) 를 돌려 CGRAM 사본 7E:3914~3D13 을 얻는다(7E:2190 은 0)."""
    from w65816 import Cpu
    c = Cpu(data, bytearray(0x20000))
    c.wram[0xBC], c.wram[0xBD], c.wram[0xBE], c.wram[0x1949] = bc, bd, 0x80 if indoor else 0, world
    c.dbr = 0x01
    c.jsr(entry)
    return bytes(c.wram[0x3914:0x3D14])


def model_lines(entries, bc, bd, indoor, world, base):
    """맵 팔레트 줄 항목을 01:996A 와 같은 차례·조건으로 적용한 CGRAM 사본(7E:2190 이 0 이라 조건은 bit7 항목만 참)."""
    out = bytearray(0x400)
    for e in entries:
        hit = (not indoor and e[1] == world) if e[0] == 0xFE else (indoor and e[0] == bc and e[1] in (bd, 0xFF))
        if hit and (e[2] == 0xFF or e[2] & 0x80):
            a = base + e[4] * 32
            out[a:a + 32] = bytes(2) + e[5:35]
    return bytes(out)


def check(rom, doc=None, at=None):
    from dq5build import build, parse_at
    from dq5palsetwrite import known_maps
    source = dump(rom) if doc is None else doc
    manifest = patch(rom, source, at)
    writes = manifest['writes']
    if doc is None and writes:
        raise ValueError('원본 왕복 쓰기가 0개가 아님')
    mb = manifest.get('rom_size', 0)
    data, _ = build(rom.d, [('obj-palettes', mb, [(parse_at(w['at'])[0], bytes.fromhex(w['hex']),
                                                   bytes.fromhex(w['orig']) if 'orig' in w else None, w['note'])
                                                  for w in writes])], mb)
    moved = Rom(data)
    if patch(moved, dump(moved))['writes']:
        raise ValueError('빌드한 롬을 다시 읽어 패치하면 쓰기가 남음')
    want = after_sets(rom, source)
    got = set_palettes(moved)
    if got != want:
        raise ValueError('세트 팔레트가 입력과 다름: ' + ' '.join(f'{s:02X}' for s in sorted(want) if got.get(s) != want[s]))
    for s in S.set_numbers(rom):
        a, b = S.set_record(rom, s), S.set_record(moved, s)
        if (a is None) != (b is None) or a and (a['cells'], a['data'], a['tiles']) != (b['cells'], b['data'], b['tiles']):
            raise ValueError(f'세트 {s:02X}: 팔레트 밖 레코드가 달라짐')
    # 롬 코드를 그대로 돌려 칸 목록의 팔레트 비트를 본다(OAM 속성 bit1-3 이 칸 워드 bit9-11).
    original = bytes(rom.d)
    for s, p in want.items():
        before, after = run_cells(original, s), run_cells(data, s)
        if [c & ~0x0E00 for c in before] != [c & ~0x0E00 for c in after] or any((c >> 9) & 7 != p for c in after):
            raise ValueError(f'세트 {s:02X}: 칸 목록의 팔레트가 {p} 가 아님')
    # 03:D24D: 그림 번호마다 $08. 표 값이 있으면 팔레트 × 2, 없으면 원래 명령(레코드 +2 >> 5)과 같고 Y 는 2 로 남는다.
    table = S.set_palette_table(moved)
    swaps = 0
    for g, s in pictures(moved):
        rec = S.set_record(moved, s) if s in S.set_numbers(moved) else None
        if rec is None:
            continue
        v = moved.u8(table + s) if table else 0xFF
        expect = v << 1 if v < 8 else moved.u8(rec['record'] + 2) >> 5
        got8, y = run_swap(data, g, rec['record'])
        if (got8, y) != (expect, 2):
            raise ValueError(f'그림 {g:02X}(세트 {s:02X}): 03:D24D 의 $08 {got8:02X}·Y {y} 가 예측 {expect:02X}·2 와 다름')
        swaps += 1
    # 01:996A·01:9954: 맵마다 CGRAM 사본을 표 항목대로 덮는지 원본·만든 롬 모두에서 본다.
    def raw_entries(r):
        return [bytes(r.d[lorom(e['entry']):lorom(e['entry']) + MAP_ENTRY]) for e in S.map_palettes(r)]
    before, after = raw_entries(rom), raw_entries(moved)
    scenes = [(bc, bd, True, 0) for bc, ms in sorted(known_maps(rom).items()) for bd in sorted(ms)]
    scenes += [(0, 0, False, w) for w in range(3)]
    for bc, bd, indoor, world in scenes:
        for entry, base in ((MAP_LOADER, 0), (MAP_ALT, 0x200)):
            if run_lines(original, bc, bd, indoor, world, entry) != model_lines(before, bc, bd, indoor, world, base) or \
                    run_lines(data, bc, bd, indoor, world, entry) != model_lines(after, bc, bd, indoor, world, base):
                where = f'{bc:02X}/{bd:02X}' if indoor else f'필드 {world}'
                raise ValueError(f'{where}: {cpu(entry)} 가 덮는 줄이 예측과 다름')
    print(f'OBJ 팔레트 {PALETTES}개, 맵 팔레트 {len(before)}→{len(after)}개, 세트 {len(want)}개 검사 통과; '
          f'칸 목록 {len(want)}세트·그림 바꾸기 {swaps}그림·맵 {len(scenes)}곳을 롬 코드로 확인; 쓰기 {len(writes)}개')


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
        p.add_argument('--at', help='세트 팔레트 표·옮긴 맵 팔레트 루틴과 표를 둘 자리(BB:AAAA, 뱅크 00~3F)')
    args = parser.parse_args()
    try:
        rom = Rom(args.rom.read_bytes())
        doc = json.loads(args.source.read_text(encoding='utf-8')) if getattr(args, 'source', None) else None
        if args.command == 'check':
            check(rom, doc, args.at)
            return 0
        result = dump(rom) if args.command == 'dump' else patch(rom, doc, args.at)
        if args.command == 'patch':
            for p, sets in affected(rom, doc).items():
                print(f'OBJ 팔레트 {p} 를 쓰는 세트 {len(sets)}개: {" ".join(sets)}')
            for p, maps in overridden(rom, doc).items():
                if maps:
                    print(f'OBJ 팔레트 {p} 줄을 맵 팔레트가 덮는 맵(바꾼 색이 안 보임): {" ".join(maps)}')
            for p, who in shared_lines(rom, doc).items():
                print(f'OBJ 팔레트 {p}: 세트 {" ".join(who["sets"])}'
                      + (f', 같은 줄을 쓰는 맵 OBJ 물체 {" ".join(who["objects"])}' if who['objects'] else '')
                      + (f', 그 줄을 덮는 맵 {" ".join(who["map_lines"])}' if who['map_lines'] else '')
                      + (', 필드 탈것 그림자(색 0)' if p == 5 else ''))
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        print(f'{args.command} → {args.out}')
        return 0
    except (ValueError, OSError, IndexError, KeyError) as error:
        print(f'오류: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
