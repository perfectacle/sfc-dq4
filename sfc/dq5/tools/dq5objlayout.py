"""DQ5 맵 OBJ 물체·탈것·인물 세트의 칸 배치 쓰기와 새 맵 OBJ 물체. 읽기 형식은
sfc/dq5/docs/dq5-graphics-format.md 의 「맵 OBJ 물체」·「탈것」·「프레임 배치」, 쓰기 형식은 dq5-build-format.md.

칸 하나는 OBJ 8x8 한 장이고, 칸 바이트는 bit7 = 좌우 반전, bit0-6 = 타일 번호(그 물체가 받은 첫 VRAM 타일에서 센다).
글에서는 `05`(그대로)·`h05`(좌우 반전)·`v05`/`hv05`(상하 반전, 탈것 그림자에만 있음)로 쓴다.

  맵 OBJ 물체: 16:F60D 가 16:F862 의 9바이트 항목(FF 로 끝)을 읽어 탈것 슬롯(7E:3220 = FE)을 만든다. 표와 칸 바이트는
    모두 16 뱅크(PHK·PLB)이고 칸 바이트 주소는 16비트다. 표를 늘리면 제자리에서 뒤로 늘리고, 늘어난 표에 덮이는
    칸 바이트와 바꾼 칸 바이트는 16 뱅크 안의 같은 바이트를 찾아 가리키거나 --at(16 뱅크)에 놓는다.
  탈것: 01:BD29(양탄자)·01:C436(天空城)·01:C087(マスタードラゴン)이 부분마다 LDY #칸 표 / JSL 16:F7D9 를 부른다.
    가로·세로 칸 수·방향·프레임 간격·옮겨 쓰는 블록 수는 같은 루틴의 즉값이라 이 도구는 칸 바이트만 제자리에 쓴다.
    상하 반전은 01:C42D·01:C160 표가 슬롯 칸 목록에 나중에 더하므로 칸 바이트로 바꿀 수 없다.
  인물 세트(배 68 등): 세트 레코드 +3~+50 의 칸 48개(1F:CFC8·1F:D0FB 가 칸 목록으로 옮김). 자리는 00:F071(6타일)·
    00:F7AA(8타일)가 정한다. 타일 번호는 그 세트의 타일 수(+51)보다 작아야 한다.

  python sfc/dq5/tools/dq5objlayout.py rom/dq5.sfc dump -o work/objlayout/layout.json
  python sfc/dq5/tools/dq5objlayout.py rom/dq5.sfc patch work/objlayout/layout.json -o work/objlayout.dq5patch.json --at 16:FE10
  python sfc/dq5/tools/dq5objlayout.py rom/dq5.sfc check [문서] [--at 16:FE10]

문서(dq5objlayout/1). 세 칸 모두 생략할 수 있고, 생략한 것은 그대로 둔다.
  {"format": "dq5objlayout/1",
   "objects": [{"map": "04/06", "x": 39, "y": 9, "cond": null, "palette": 3, "priority": 2,
                "cells": ["00 01", "02 03", "04 05", "06 07"]}, ...],     # 표 전체(차례대로). 줄 수 = 세로, 낱말 수 = 가로
   "vehicles": [{"part": "80-1", "cells": {"down0": ["09 0a 0b", "0c 0d h0c"], ...}}],
   "sets": [{"set": "68", "cells": {"down0": "18 19 1a 1b 1c 1d", ...}}]}
map 은 "04/06", 그룹 전체 "04/**", 필드 "field0"(세계). cond 는 null·"day"·"night"(+4 bit7·bit6, 21:8000 이 7E:075E >= F0 을
밤으로 봄). x·y 가 128 이면 스크립트가 놓는다. bit7(+6 bit7)은 쓰임을 모르는 원래 값으로, 없으면 0.
8타일 세트(80~)의 cells 는 "up-head" 같은 머리 4칸과 "up0"·"up1" 몸 4칸이다.
"""
import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dq5sprite as S  # noqa: E402
from dq5build import PatchError  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402

FORMAT = 'dq5objlayout/1'
TABLE = S.MAP_OBJECT_PLACES
BANK = TABLE >> 16
# 원래 표 뒤의 칸 바이트 구역 끝(16:FDFF 는 아무 항목도 가리키지 않는 0). 표는 이 앞까지만 늘릴 수 있다.
REGION_END = 0x16FDFF
ENTRY = 9
DIRS = ('up', 'right', 'down', 'left')     # 00:EE7C 차례(방향 번호 0~3)
# 탈것 부분: (dq5sprite.VEHICLES 의 번호, 부분 차례, LDY #칸 표 피연산자, 칸 표 뱅크 LDA # 피연산자).
# 한 탈것의 부분은 LDA #$04 / PHA / PLB 한 번 뒤의 DB 를 같이 쓴다.
VEHICLE_PARTS = {'80-1': (0x80, 0, 0x01BDA5, 0x01BDA8), '80-2': (0x80, 1, 0x01BDC1, 0x01BDA8),
                 '80-3': (0x80, 2, 0x01BDD4, 0x01BDA8), '81-1': (0x81, 0, 0x01C48E, 0x01C491),
                 '81-2': (0x81, 1, 0x01C4AA, 0x01C491), '82-1': (0x82, 0, 0x01C0EB, 0x01C0EE),
                 '82-2': (0x82, 1, 0x01C106, 0x01C0EE)}
TOKEN = re.compile(r'(h?)(v?)([0-9A-Fa-f]{2})')


def cpu(addr):
    return f'{addr >> 16:02X}:{addr & 0xFFFF:04X}'


def address(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9A-Fa-f]{2}:[0-9A-Fa-f]{4}', value):
        raise ValueError('주소는 BB:AAAA 문자열이어야 함')
    bank, low = (int(p, 16) for p in value.split(':'))
    if bank != BANK or low < 0x8000:
        raise ValueError(f'--at 은 {BANK:02X} 뱅크 8000~FFFF 여야 함(표와 칸 바이트를 PHK·PLB 로 읽음)')
    return bank << 16 | low


def token(value):
    """칸 바이트 + 상하 반전 → 글."""
    b, v = value
    return ('h' if b & 0x80 else '') + ('v' if v else '') + f'{b & 0x7F:02X}'


def parse_token(text, label, limit=0x80, vflip=False):
    m = TOKEN.fullmatch(text)
    if not m:
        raise ValueError(f'{label}: 칸 {text!r} 는 [h][v]두 자리 16진이어야 함')
    tile = int(m[3], 16)
    if tile >= limit:
        raise ValueError(f'{label}: 타일 {tile:02X} 는 {limit:02X} 보다 작아야 함')
    if m[2] and not vflip:
        raise ValueError(f'{label}: 상하 반전(v)은 탈것 그림자 칸에만 있음')
    return tile | (0x80 if m[1] else 0), bool(m[2])


def parse_row(text, label, **kw):
    if not isinstance(text, str):
        raise ValueError(f'{label}: 칸 줄은 문자열이어야 함')
    return [parse_token(t, label, **kw) for t in text.split()]


def parse_map(text, label):
    if text is not None and isinstance(text, str):
        m = re.fullmatch(r'field([0-9])', text)
        if m:
            return 0xFE, int(m[1])
        m = re.fullmatch(r'([0-9A-Fa-f]{2})/([0-9A-Fa-f]{2}|\*\*)', text)
        if m and int(m[1], 16) < 0xFE:
            return int(m[1], 16), 0x7F if m[2] == '**' else int(m[2], 16) & 0x7F
    raise ValueError(f'{label}: map 은 "04/06"·"04/**"·"field0" 꼴이어야 함')


def map_name(bc, bd):
    if bc == 0xFE:
        return f'field{bd}'
    return f'{bc:02X}/' + ('**' if bd & 0x7F == 0x7F else f'{bd & 0x7F:02X}')


# --- 맵 OBJ 물체 ---------------------------------------------------------------------------------------------------

def read_objects(rom):
    """16:F862 표. 항목마다 원래 바이트 9개와 칸 바이트."""
    out, a = [], TABLE
    while rom.u8(a) != 0xFF:
        b = bytes(rom.u8(a + i) for i in range(ENTRY))
        cols, rows = b[4] & 0x3F, b[5]
        ptr = BANK << 16 | b[7] | b[8] << 8
        out.append({'entry': a, 'raw': b, 'ptr': ptr, 'cells': bytes(rom.u8(ptr + i) for i in range(cols * rows))})
        a += ENTRY
    return out


def object_doc(o):
    b = o['raw']
    cols = b[4] & 0x3F
    row = {'map': map_name(b[0], b[1]), 'x': b[2] | (b[6] & 1) << 8, 'y': b[3] | (b[6] >> 1 & 1) << 8,
           'cond': None if not b[4] & 0x80 else ('night' if b[4] & 0x40 else 'day'),
           'palette': b[6] >> 2 & 7, 'priority': b[6] >> 5 & 3,
           'cells': [' '.join(token((c, False)) for c in o['cells'][r * cols:(r + 1) * cols]) for r in range(b[5])]}
    if b[6] & 0x80:
        row['bit7'] = True
    if b[0] != 0xFE and b[1] & 0x80:
        row['bd7'] = True
    return row


def object_entry(row, label):
    """문서 항목 → (항목 앞 7바이트, 칸 바이트)."""
    keys = {'map', 'x', 'y', 'cond', 'palette', 'priority', 'cells', 'bit7', 'bd7'}
    if not isinstance(row, dict) or row.keys() - keys or not {'map', 'x', 'y', 'cells'} <= row.keys():
        raise ValueError(f'{label}: map·x·y·cells(와 cond·palette·priority·bit7·bd7)만 받음')
    bc, bd = parse_map(row['map'], label)
    if row.get('bd7') and bc != 0xFE:
        bd |= 0x80
    x, y = row['x'], row['y']
    palette, priority = row.get('palette', 3), row.get('priority', 2)
    for name, v, top in (('x', x, 0x200), ('y', y, 0x200), ('palette', palette, 8), ('priority', priority, 4)):
        if not isinstance(v, int) or isinstance(v, bool) or not 0 <= v < top:
            raise ValueError(f'{label}: {name} 는 0~{top - 1} 정수여야 함')
    cond = row.get('cond')
    if cond not in (None, 'day', 'night'):
        raise ValueError(f'{label}: cond 는 null·"day"·"night"')
    rows = row['cells']
    if not isinstance(rows, list) or not 1 <= len(rows) <= 0xFF:
        raise ValueError(f'{label}: cells 는 1~255 줄의 배열이어야 함')
    grid = [parse_row(r, f'{label} 줄 {i}') for i, r in enumerate(rows)]
    cols = len(grid[0])
    if not 1 <= cols <= 0x3F or any(len(r) != cols for r in grid):
        raise ValueError(f'{label}: 줄마다 칸 수가 같고 1~63 이어야 함')
    head = bytes([bc, bd, x & 0xFF, y & 0xFF,
                  cols | (0x80 if cond else 0) | (0x40 if cond == 'night' else 0), len(grid),
                  x >> 8 | (y >> 8) << 1 | palette << 2 | priority << 5 | (0x80 if row.get('bit7') else 0)])
    return head, bytes(c for r in grid for c, _ in r)


def plan_objects(rom, rows, at):
    """새 표와 칸 바이트 자리. (쓰기 목록 [(주소, 바이트, 원래 롬 안인지, 설명)], 옮기거나 새로 둔 칸 수)."""
    if not isinstance(rows, list):
        raise ValueError('objects 는 배열이어야 함')
    old = read_objects(rom)
    entries = [object_entry(r, f'objects[{i}]') for i, r in enumerate(rows)]
    table_end = TABLE + len(entries) * ENTRY + 1
    if table_end > REGION_END:
        raise ValueError(f'objects {len(entries)}개: 표가 {cpu(REGION_END)} 를 넘음(최대 {(REGION_END - TABLE - 1) // ENTRY}개)')
    region = bytes(rom.u8(a) for a in range(table_end, REGION_END))
    placed, blob, cursor = [], bytearray(), at
    moved = 0
    for i, (head, cells) in enumerate(entries):
        orig = old[i] if i < len(old) else None
        if orig and orig['cells'] == cells and orig['ptr'] >= table_end:
            placed.append(orig['ptr'])
            continue
        # 표에 덮이지 않고 그대로 남는 구역에서 같은 바이트를 찾고, 없으면 --at 뒤에 둔다.
        k = region.find(cells)
        if k >= 0:
            placed.append(table_end + k)
        else:
            k = bytes(blob).find(cells)
            if k < 0:
                if cursor is None:
                    raise ValueError(f'objects[{i}]: 칸 바이트를 둘 곳이 없어 --at 이 필요함')
                k = len(blob)
                blob += cells
            placed.append(cursor + k)
        moved += 1
    if blob and cursor >> 16 != BANK:
        raise ValueError(f'--at {cpu(cursor)}: 칸 바이트는 {BANK:02X} 뱅크에 있어야 함')
    if blob and (cursor & 0xFFFF) + len(blob) > 0x10000:
        raise ValueError(f'--at {cpu(cursor)} 뒤 칸 바이트 {len(blob)}바이트가 16 뱅크를 넘음')
    table = b''.join(h + bytes([p & 0xFF, p >> 8 & 0xFF]) for (h, _), p in zip(entries, placed)) + b'\xff'
    writes = []
    old_table = bytes(rom.u8(TABLE + i) for i in range(len(table)))
    if table != old_table:
        writes.append((TABLE, table, True, f'맵 OBJ 물체 표 {len(entries)}항목'))
    if blob:
        writes.append((cursor, bytes(blob), False, f'맵 OBJ 물체 칸 바이트 {len(blob)}바이트'))
    return writes, moved


# --- 탈것 ----------------------------------------------------------------------------------------------------------

def vehicle_part(rom, name):
    vid, k, ldy, bank = VEHICLE_PARTS[name]
    part = next(v for v in S.VEHICLES if v['id'] == vid)['parts'][k]
    table = rom.u8(bank) << 16 | rom.u16(ldy)
    frames = part['dir'] // part['frame'] if part['dir'] else 1
    per = part['cols'] * part['rows']
    vflip = {off // 2 for off in part['vflip']}
    keys = [(d, f) for d in DIRS for f in range(frames)] if part['dir'] else [(None, 0)]
    blocks = {}
    for d, f in keys:
        start = (DIRS.index(d) * part['dir'] + f * part['frame']) // 2 if d else 0
        blocks[f'{d}{f}' if d else 'all'] = list(range(start, start + per))
    used = max(i for b in blocks.values() for i in b) + 1
    return {'part': part, 'table': table, 'blocks': blocks, 'vflip': vflip, 'used': used,
            'bytes': bytes(rom.u8(table + i) for i in range(used))}


def vehicle_doc(rom, name):
    p = vehicle_part(rom, name)
    cols = p['part']['cols']
    cells = {}
    for key, idx in p['blocks'].items():
        toks = [token((p['bytes'][i], i in p['vflip'])) for i in idx]
        cells[key] = [' '.join(toks[r * cols:(r + 1) * cols]) for r in range(p['part']['rows'])]
    return {'part': name, 'cells': cells}


def plan_vehicles(rom, rows):
    if not isinstance(rows, list):
        raise ValueError('vehicles 는 배열이어야 함')
    writes, seen = [], set()
    for i, row in enumerate(rows):
        label = f'vehicles[{i}]'
        if not isinstance(row, dict) or row.keys() - {'part', 'cells'} or row.get('part') not in VEHICLE_PARTS \
                or row['part'] in seen or not isinstance(row.get('cells'), dict):
            raise ValueError(f'{label}: part(80-1 등, 한 번씩)·cells 만 받음')
        seen.add(row['part'])
        p = vehicle_part(rom, row['part'])
        data = bytearray(p['bytes'])
        if row['cells'].keys() - p['blocks'].keys():
            raise ValueError(f'{label}: cells 의 열쇠는 {" ".join(p["blocks"])} 중 하나')
        for key, rows_ in row['cells'].items():
            if not isinstance(rows_, list) or len(rows_) != p['part']['rows']:
                raise ValueError(f'{label} {key}: 줄 {p["part"]["rows"]}개여야 함(가로·세로 칸 수는 바꾸지 않음)')
            toks = [t for r, text in enumerate(rows_) for t in parse_row(text, f'{label} {key} 줄 {r}', vflip=True)]
            if len(toks) != len(p['blocks'][key]):
                raise ValueError(f'{label} {key}: 칸 {len(p["blocks"][key])}개여야 함')
            for i_, (b, v) in zip(p['blocks'][key], toks):
                if v != (i_ in p['vflip']):
                    raise ValueError(f'{label} {key}: 상하 반전 칸은 01:C42D·01:C160 표가 정해 바꿀 수 없음')
                data[i_] = b
        if bytes(data) != p['bytes']:
            writes.append((p['table'], bytes(data), True, f'탈것 {row["part"]} 칸 {len(data)}개'))
    return writes


# --- 인물 세트 -----------------------------------------------------------------------------------------------------

def set_blocks(rec):
    if rec['layout'] == 'simple':
        return {f'{d}{f}': [S.SIMPLE_BASE[d] + f * 6 + i for i in range(6)] for d in DIRS for f in range(2)}
    out = {}
    for d in DIRS:
        out[f'{d}-head'] = [S.HEAD_BASE[d] + i for i in range(4)]
        for f in range(2):
            out[f'{d}{f}'] = [S.BODY_BASE[d] + f * 4 + i for i in range(4)]
    return out


def set_doc(rec):
    return {'set': f'{rec["set"]:02X}',
            'cells': {k: ' '.join(token((rec['cells'][i], False)) for i in idx) for k, idx in set_blocks(rec).items()}}


def plan_sets(rom, rows):
    if not isinstance(rows, list):
        raise ValueError('sets 는 배열이어야 함')
    writes, seen = [], set()
    for i, row in enumerate(rows):
        label = f'sets[{i}]'
        if not isinstance(row, dict) or row.keys() - {'set', 'cells'} or not isinstance(row.get('cells'), dict) or \
                not isinstance(row.get('set'), str) or not re.fullmatch(r'[0-9A-Fa-f]{2}', row['set']):
            raise ValueError(f'{label}: set(두 자리 16진)·cells 만 받음')
        s = int(row['set'], 16)
        rec = S.set_record(rom, s)
        if rec is None or s in seen:
            raise ValueError(f'{label}: 세트 {s:02X} 는 없거나 두 번 지정함')
        seen.add(s)
        blocks = set_blocks(rec)
        if row['cells'].keys() - blocks.keys():
            raise ValueError(f'{label}: cells 의 열쇠는 {" ".join(blocks)} 중 하나')
        cells = bytearray(rec['cells'])
        for key, text in row['cells'].items():
            toks = parse_row(text, f'{label} {key}', limit=rec['tiles'])
            if len(toks) != len(blocks[key]):
                raise ValueError(f'{label} {key}: 칸 {len(blocks[key])}개여야 함')
            for c, (b, _) in zip(blocks[key], toks):
                cells[c] = b
        if bytes(cells) != bytes(rec['cells']):
            writes.append((rec['record'] + 3, bytes(cells), True, f'세트 {s:02X} 칸 48개'))
    return writes


# --- 문서 ----------------------------------------------------------------------------------------------------------

def dump(rom):
    return {'format': FORMAT,
            'objects': [object_doc(o) for o in read_objects(rom)],
            'vehicles': [vehicle_doc(rom, n) for n in VEHICLE_PARTS],
            'sets': [set_doc(S.set_record(rom, s)) for s in S.set_numbers(rom) if S.set_record(rom, s)]}


def patch(rom, doc, at=None):
    if not isinstance(doc, dict) or doc.get('format') != FORMAT or doc.keys() - {'format', 'objects', 'vehicles', 'sets'}:
        raise ValueError(f'문서는 format={FORMAT} 와 objects·vehicles·sets 만 담은 객체여야 함')
    writes, moved = [], 0
    if 'objects' in doc:
        w, moved = plan_objects(rom, doc['objects'], at)
        writes += w
    writes += plan_vehicles(rom, doc.get('vehicles', []))
    writes += plan_sets(rom, doc.get('sets', []))
    out = []
    for addr, data, inside, note in writes:
        item = {'at': cpu(addr), 'hex': data.hex(' '), 'note': note}
        # 새 칸 바이트는 orig 없이 써서, 원래 롬 안이면 빌더가 빈 자리 지도 밖을 거부한다.
        if inside:
            item['orig'] = bytes(rom.d[lorom(addr):lorom(addr) + len(data)]).hex(' ')
        out.append(item)
    if moved:
        print(f'맵 OBJ 물체 칸 바이트 {moved}개를 다른 자리에서 가리킴', file=sys.stderr)
    return {'format': 'dq5patch/1', 'name': 'obj-layout', 'writes': out}


def built(rom, manifest):
    from dq5build import build, parse_at
    lists = [(parse_at(w['at'])[0], bytes.fromhex(w['hex']), bytes.fromhex(w['orig']) if 'orig' in w else None, w['note'])
             for w in manifest['writes']]
    data, _ = build(rom.d, [('obj-layout', 0, lists)], 0)
    return Rom(data)


def normalized(doc, rom):
    """비교용: 생략한 칸은 롬 값으로 채운 dump 꼴."""
    base = dump(rom)
    if 'objects' in doc:
        base['objects'] = [object_doc({'raw': h + b'\0\0', 'cells': c}) for h, c in
                           (object_entry(r, '') for r in doc['objects'])]
    for row in doc.get('vehicles', []):
        cur = next(v for v in base['vehicles'] if v['part'] == row['part'])
        cur['cells'].update({k: [canon(r) for r in v] for k, v in row['cells'].items()})
    for row in doc.get('sets', []):
        cur = next(s for s in base['sets'] if s['set'] == row['set'].upper())
        cur['cells'].update({k: canon(v) for k, v in row['cells'].items()})
    return base


def canon(text):
    return ' '.join(token(parse_token(t, '', vflip=True)) for t in text.split())


def check(rom, doc=None, at=None):
    """원본을 dump 해 다시 넣으면 쓰기 0개인지. doc 를 주면 빌드한 롬을 다시 dump 해 문서와 같은지."""
    original = dump(rom)
    if patch(rom, original)['writes']:
        raise ValueError('원본 문서를 그대로 넣었는데 쓰기가 생김')
    print(f'원본: 물체 {len(original["objects"])}개, 탈것 부분 {len(original["vehicles"])}개, '
          f'세트 {len(original["sets"])}개, 다시 넣어 쓰기 0개')
    if doc is None:
        return
    manifest = patch(rom, doc, at)
    after = built(rom, manifest)
    got = dump(after)
    want = normalized(doc, rom)
    for key in ('objects', 'vehicles', 'sets'):
        if got[key] != want[key]:
            raise ValueError(f'빌드한 롬의 {key} 가 문서와 다름')
    print(f'문서: 쓰기 {len(manifest["writes"])}개, 빌드한 롬을 다시 읽어 물체 {len(got["objects"])}개·탈것·세트가 문서와 같음')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('rom', type=Path)
    sub = parser.add_subparsers(dest='command', required=True)
    export = sub.add_parser('dump')
    export.add_argument('-o', '--out', type=Path, required=True)
    write = sub.add_parser('patch')
    write.add_argument('source', type=Path)
    write.add_argument('-o', '--out', type=Path, required=True)
    write.add_argument('--at', help='새 칸 바이트를 놓을 곳(16:xxxx)')
    verify = sub.add_parser('check')
    verify.add_argument('source', type=Path, nargs='?')
    verify.add_argument('--at')
    args = parser.parse_args()
    try:
        rom = Rom(args.rom.read_bytes())
        if args.command == 'dump':
            doc = dump(rom)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
            print(f'물체 {len(doc["objects"])}개, 탈것 부분 {len(doc["vehicles"])}개, 세트 {len(doc["sets"])}개 → {args.out}')
            return 0
        doc = json.loads(args.source.read_text(encoding='utf-8')) if getattr(args, 'source', None) else None
        at = address(args.at) if args.at else None
        if args.command == 'check':
            check(rom, doc, at)
            return 0
        manifest = patch(rom, doc, at)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        print(f'patch → {args.out} (쓰기 {len(manifest["writes"])}개)')
        return 0
    except (ValueError, OSError, IndexError, PatchError) as error:
        print(f'오류: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
