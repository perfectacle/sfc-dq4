"""DQ5(SFC) 전투 배경 쓰기. 그림·목록·팔레트 레코드와 세 포인터 표를 내보내고, 고친 것을 다시 싸서 넣는다.
형식은 sfc/dq5/docs/dq5-graphics-format.md 「전투 배경」, 입력은 sfc/dq5/docs/dq5-build-format.md 「전투 배경 쓰기」.

  dump   롬 → 폴더(-o). bg.json 과 그림마다 4bpp 타일 파일(pic-<주소>.bin, 칸 순서)
  patch  bg.json → 패치 목록(-o). 바뀐 것이 없으면 쓰기 0개. --at BB:AAAA 이면 그림을 그 뱅크로 옮긴다
  check  모든 그림을 풀어 다시 싸 다시 풀기, 내보낸 그대로 patch 하면 쓰기 0개인지

자료는 모두 뱅크 28 이고 표는 16비트 포인터다. 그림은 [$53] 롱 간접으로 읽고 뱅크를 22:CB35·22:CB54 의 즉값 28 에서
받으므로(DB 는 7E), 그림 전체를 다른 뱅크로 옮길 수 있다. 목록(22:8878 이 뱅크 28 을 $52 에)과 팔레트(22:8808 이 $55 에)는
뱅크 28 에 남기고, 그림이 비운 자리를 넘침 자리로 쓴다. 세계 2 목록 28:FD64 는 22:88D3 의 즉값으로 가리킨다.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5map import Rom, lorom  # noqa: E402
from dq5mongfx import Stream, tile as decode_tile  # noqa: E402

FORMAT = 'dq5battlebg/1'
BANK = 0x28
NUMBERS, NUMBER_COUNT = 0x228983, 0x31
TABLES = {'pictures': (0x2882F9, 78), 'palettes': (0x28BDFC, 106), 'lists': (0x28C9C2, 117)}
# 표 다음부터 다음 표 앞까지가 원래 자료 자리. 목록 끝 28:FFEE~ 은 0 이지만 원래 쓰지 않던 자리라 넣지 않는다.
REGIONS = {'pictures': (0x288395, 0x28BDFC), 'palettes': (0x28BED0, 0x28C9C2), 'lists': (0x28CAAC, 0x28FFEE)}
PICTURE_BANK_SITES = (0x22CB36, 0x22CB55)    # LDA #$28 / STA $55 의 즉값
ALT_LIST_SITE = 0x2288D4                    # LDA #$FD64 / STA $50 의 즉값


def cpu(a):
    return f'{a >> 16:02X}:{a & 0xFFFF:04X}'


def ident(a):
    return f'{a:06X}'


# ---- 타일 4bpp 압축(22:992A) ----

def encode_tile(data):
    """32바이트 타일 → 게임이 같은 32바이트로 푸는 가장 짧은 바이트열. 없는 평면은 0 이어야 한다."""
    if len(data) != 32:
        raise ValueError('타일은 32바이트')
    # 평면 p 의 줄 r 바이트 위치. 앞 16바이트가 평면 0·1, 뒤가 2·3, 줄마다 두 평면이 번갈아 온다.
    pos = [[(p // 2) * 16 + r * 2 + p % 2 for r in range(8)] for p in range(4)]
    planes = [any(data[i] for i in pos[p]) for p in range(4)]
    order = [pos[p][r] for half in (0, 1) for r in range(8) for p in (half * 2, half * 2 + 1) if planes[p]]
    values = [data[i] for i in order]
    mode = sum(1 << p for p in range(4) if planes[p])
    best = bytes([mode]) + bytes(values)
    n = sum(planes)
    for fill in sorted(set(values) | {0}):
        bits = [v != fill for v in values]
        masks = bytes(sum(bit << (7 - j) for j, bit in enumerate(bits[i:i + 8])) for i in range(0, len(bits), 8))
        out = bytes([0x80 | (0x40 if fill else 0) | mode]) + (bytes([fill]) if fill else b'') + masks + \
            bytes(v for v in values if v != fill)
        if len(masks) == n and len(out) < len(best):
            best = out
    return best


def tile_at(data, pos):
    """타일 하나를 풀고 (32바이트, 다음 위치). data 는 bytes."""
    class Raw:
        def __init__(self, d):
            self.d = d

        def u8(self, i):
            return self.d[i]

    p = [pos]
    return decode_tile(Raw(data), p), p[0]


# ---- 자료 읽기 ----

def read_picture(rom, a):
    """그림 → (w, h, 칸 비트 목록, 칸마다 32바이트(없는 칸은 0), 크기)."""
    s = Stream(rom, a)
    b = s.u8(0)
    w, h = (b >> 4) + 1, (b & 15) + 1
    n = w * h
    cells = [s.u8(1 + i // 8) >> (7 - i % 8) & 1 for i in range(n)]
    pos = [1 + (n + 7) // 8]
    tiles = []
    for c in cells:
        tiles.append(decode_tile(s, pos) if c else bytes(32))
    return w, h, cells, tiles, pos[0]


def encode_picture(w, h, cells, tiles):
    if not (1 <= w <= 16 and 1 <= h <= 16) or len(cells) != w * h or len(tiles) != w * h:
        raise ValueError('그림 칸 수가 맞지 않음')
    bitmap = bytearray((w * h + 7) // 8)
    body = bytearray()
    for i, (c, t) in enumerate(zip(cells, tiles)):
        if c:
            bitmap[i // 8] |= 0x80 >> (i % 8)
            body += encode_tile(t)
        elif any(t):
            raise ValueError(f'칸 {i} 는 비트가 0 인데 타일이 0 이 아님')
    return bytes([(w - 1) << 4 | (h - 1)]) + bytes(bitmap) + bytes(body)


def read_list(rom, a):
    out = []
    while rom.u8(a) != 0xFF:
        out.append([rom.u8(a), rom.u8(a + 1)])
        a += 2
    return out, len(out) * 2 + 1


def encode_list(entries):
    out = bytearray()
    for e in entries:
        if not (isinstance(e, list) and len(e) == 2 and all(type(v) is int and 0 <= v <= 255 for v in e)) or e[0] == 0xFF:
            raise ValueError(f'목록 항목 {e!r}: [0~254, 0~255]')
        out += bytes(e)
    return bytes(out) + b'\xff'


def read_palette(rom, a):
    count, slot = rom.u8(a), rom.u8(a + 1)
    q, rows = a + 2, []
    for _ in range(count):
        m = rom.u8(q)
        rows.append([rom.u16(q + 1 + j * 2) for j in range(m)])
        q += 1 + m * 2
    return {'slot': slot, 'rows': rows}, q - a


def encode_palette(p):
    rows, slot = p.get('rows'), p.get('slot')
    if type(slot) is not int or not 0 <= slot <= 255 or not isinstance(rows, list) or not 1 <= len(rows) <= 255:
        raise ValueError('팔레트는 slot 0~255 와 rows 1~255줄')
    out = bytearray([len(rows), slot])
    for row in rows:
        if not isinstance(row, list) or not 1 <= len(row) <= 15 or \
                any(type(c) is not int or not 0 <= c <= 0x7FFF for c in row):
            raise ValueError('팔레트 줄은 15비트 색 1~15개')
        out.append(len(row))
        for c in row:
            out += c.to_bytes(2, 'little')
    return bytes(out)


# 원래 롬에서 이 자리들이 그림 뱅크·세계 2 목록 즉값이어야 한다(다른 패치를 먼저 한 롬을 거부).
ORIGINAL_SITES = {0x22CB35: b'\xa9\x28', 0x22CB54: b'\xa9\x28', 0x2288D3: b'\xa9\x64\xfd'}


def original(rom):
    """{'tables': {종류: [주소]}, 'resources': {종류: {주소: (값, 원래 바이트)}}, 'alt_list': 주소, 'numbers': [...],
    'spans': {종류: 원래 자료가 차지한 [시작, 끝) 목록}}."""
    for at, want in ORIGINAL_SITES.items():
        if rom.d[lorom(at):lorom(at) + len(want)] != want:
            raise ValueError(f'{cpu(at)}: 원래 롬의 전투 배경 즉값이 아님; 원본 롬으로 만들어야 함')
    tables = {kind: [BANK << 16 | rom.u16(t + i * 2) for i in range(n)] for kind, (t, n) in TABLES.items()}
    alt = BANK << 16 | rom.u16(ALT_LIST_SITE)
    res = {'pictures': {}, 'lists': {}, 'palettes': {}}
    for a in sorted(set(tables['pictures'])):
        w, h, cells, tiles, size = read_picture(rom, a)
        res['pictures'][a] = ((w, h, cells, tiles), rom.d[lorom(a):lorom(a) + size])
    for a in sorted(set(tables['lists']) | {alt}):
        entries, size = read_list(rom, a)
        res['lists'][a] = (entries, rom.d[lorom(a):lorom(a) + size])
    for a in sorted(set(tables['palettes'])):
        p, size = read_palette(rom, a)
        res['palettes'][a] = (p, rom.d[lorom(a):lorom(a) + size])
    for kind, items in res.items():
        lo, hi = REGIONS[kind]
        for a, (_, raw) in items.items():
            if not (lo <= a and a + len(raw) <= hi):
                raise ValueError(f'{cpu(a)}: 원래 {kind} 자리 밖')
    numbers = [rom.u16(NUMBERS + i * 2) for i in range(NUMBER_COUNT)]
    # 다시 놓을 때는 원래 자료가 쓰던 바이트만 쓴다. 표가 가리키지 않는 틈(28:C112·CD7F·D143 등)은 건드리지 않는다.
    spans = {kind: merge([(a, a + len(raw)) for a, (_, raw) in items.items()]) for kind, items in res.items()}
    return {'tables': tables, 'resources': res, 'alt_list': alt, 'numbers': numbers, 'spans': spans}


def merge(ranges):
    out = []
    for lo, hi in sorted(ranges):
        if out and lo <= out[-1][1]:
            out[-1][1] = max(out[-1][1], hi)
        else:
            out.append([lo, hi])
    return [tuple(r) for r in out]


def dump(rom, out):
    o = original(rom)
    os.makedirs(out, exist_ok=True)
    pics = []
    for a, ((w, h, cells, tiles), _) in o['resources']['pictures'].items():
        name = f'pic-{ident(a)}.bin'
        with open(os.path.join(out, name), 'wb') as f:
            f.write(b''.join(tiles))
        pics.append({'id': ident(a), 'w': w, 'h': h, 'cells': ''.join(map(str, cells)), 'file': name})
    doc = {'format': FORMAT,
           'numbers': o['numbers'],
           'picture_table': [ident(a) for a in o['tables']['pictures']],
           'list_table': [ident(a) for a in o['tables']['lists']],
           'palette_table': [ident(a) for a in o['tables']['palettes']],
           'alt_list': ident(o['alt_list']),
           'pictures': pics,
           'lists': [{'id': ident(a), 'entries': e} for a, (e, _) in o['resources']['lists'].items()],
           'palettes': [{'id': ident(a), **p} for a, (p, _) in o['resources']['palettes'].items()]}
    with open(os.path.join(out, 'bg.json'), 'w', encoding='utf-8') as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
        f.write('\n')
    return doc


# ---- 입력 ----

def keys(obj, allowed, name):
    if not isinstance(obj, dict) or set(obj) - allowed:
        raise ValueError(f'{name}: 허용한 필드 {sorted(allowed)}만 있는 객체여야 함')


def norm_id(v):
    """자료 id. 원래 자료는 6자리 16진 주소(대문자로 맞춤), 새 자료는 16진이 아닌 이름."""
    if not isinstance(v, str) or not v:
        raise ValueError(f'id {v!r}: 빈 문자열이 아닌 문자열')
    return v.upper() if re.fullmatch(r'[0-9A-Fa-f]{6}', v) else v


def load(doc, folder):
    """bg.json → {'pictures': {id: 바이트}, ...}(새로 싼 바이트), 표, alt, numbers."""
    keys(doc, {'format', 'numbers', 'picture_table', 'list_table', 'palette_table', 'alt_list',
               'pictures', 'lists', 'palettes'}, '문서')
    if doc.get('format') != FORMAT:
        raise ValueError(f'format 은 {FORMAT}')
    res = {'pictures': {}, 'lists': {}, 'palettes': {}}
    for p in doc.get('pictures', []):
        keys(p, {'id', 'w', 'h', 'cells', 'file'}, '그림')
        w, h, cells = p.get('w'), p.get('h'), p.get('cells')
        if type(w) is not int or type(h) is not int or not isinstance(cells, str) or not re.fullmatch(r'[01]*', cells):
            raise ValueError(f'그림 {p.get("id")}: w·h 정수, cells 는 0·1 문자열')
        with open(os.path.join(folder, p['file']), 'rb') as f:
            data = f.read()
        if len(data) != w * h * 32:
            raise ValueError(f'그림 {p["id"]}: 파일이 {w}x{h} 칸 = {w * h * 32}바이트가 아님')
        tiles = [data[i * 32:i * 32 + 32] for i in range(w * h)]
        res['pictures'][norm_id(p.get('id'))] = ((w, h, [int(c) for c in cells], tiles), None)
    for p in doc.get('lists', []):
        keys(p, {'id', 'entries'}, '목록')
        res['lists'][norm_id(p.get('id'))] = (p.get('entries'), None)
    for p in doc.get('palettes', []):
        keys(p, {'id', 'slot', 'rows'}, '팔레트')
        res['palettes'][norm_id(p.get('id'))] = ({'slot': p.get('slot'), 'rows': p.get('rows')}, None)
    tables = {}
    for kind, key in (('pictures', 'picture_table'), ('lists', 'list_table'), ('palettes', 'palette_table')):
        t = doc.get(key)
        if not isinstance(t, list) or len(t) != TABLES[kind][1]:
            raise ValueError(f'{key} 는 {TABLES[kind][1]}개')
        t = [norm_id(v) for v in t]
        for v in t:
            if v not in res[kind]:
                raise ValueError(f'{key}: {kind} 에 없는 id {v}')
        tables[kind] = t
    if norm_id(doc.get('alt_list')) not in res['lists']:
        raise ValueError('alt_list 가 lists 에 없음')
    numbers = doc.get('numbers')
    if not isinstance(numbers, list) or len(numbers) != NUMBER_COUNT or \
            any(type(v) is not int or not 0 <= v <= 0xFFFF for v in numbers):
        raise ValueError(f'numbers 는 16비트 정수 {NUMBER_COUNT}개')
    for v in numbers:
        if (v & 0xFC) // 4 >= TABLES['pictures'][1] // 2:
            raise ValueError(f'numbers 값 {v:04X}: 종류 번호가 표 밖')
    return res, tables, norm_id(doc['alt_list']), numbers


ENCODERS = {'pictures': lambda v: encode_picture(*v), 'lists': encode_list, 'palettes': encode_palette}


def same(kind, a, b):
    if kind == 'pictures':
        wa, ha, ca, ta = a
        wb, hb, cb, tb = b
        return (wa, ha, ca) == (wb, hb, cb) and all(x == y for x, y, c in zip(ta, tb, ca) if c)
    return a == b


def place(sizes, regions):
    """[(id, 크기)] 를 regions([시작, 끝) 목록) 에 큰 것부터(같으면 id 순) 첫 맞는 자리로.
    ({id: 주소}, 남은 자리) 또는 (None, regions)."""
    free = [list(r) for r in regions]
    out = {}
    for name, size in sorted(sizes, key=lambda x: (-x[1], x[0])):
        for r in free:
            if r[1] - r[0] >= size:
                out[name] = r[0]
                r[0] += size
                break
        else:
            return None, list(regions)
    return out, [tuple(r) for r in free if r[1] > r[0]]


def patch(rom, doc, folder, at=None, name='battle-bg'):
    o = original(rom)
    res, tables, alt, numbers = load(doc, folder)
    origin = {kind: {ident(a): v for a, v in items.items()} for kind, items in o['resources'].items()}
    blobs, changed = {}, {}
    for kind in res:
        blobs[kind], changed[kind] = {}, False
        used = set(tables[kind]) | ({alt} if kind == 'lists' else set())
        for rid in sorted(used):
            value = res[kind][rid][0]
            old = origin[kind].get(rid)
            if old is not None and same(kind, value, old[0]):
                blobs[kind][rid] = bytes(old[1])
            else:
                blobs[kind][rid] = ENCODERS[kind](value)
                changed[kind] = True
        old_table = [ident(a) for a in o['tables'][kind]]
        if tables[kind] != old_table or (kind == 'lists' and alt != ident(o['alt_list'])):
            changed[kind] = True
    writes = []

    def write(addr, data, note, orig=True):
        w = {'at': cpu(addr), 'hex': data.hex(' '), 'note': note}
        if orig:
            off = lorom(addr)
            w['orig'] = rom.d[off:off + len(data)].hex(' ')
        writes.append(w)

    for i, v in enumerate(numbers):
        if v != o['numbers'][i]:
            write(NUMBERS + i * 2, v.to_bytes(2, 'little'), f'배경 번호 {i:02X}')
    if not any(changed.values()) and at is None:
        return {'format': 'dq5patch/1', 'name': name, 'writes': writes}, {}

    # 자리: 그대로 들어가면 원래 자리, 아니면 종류별로 원래 자료가 쓰던 자리에 다시 놓고, 넘치면 그림이 비운 자리를 빌린다.
    regions = {k: list(o['spans'][k]) for k in REGIONS}
    pic_bank = BANK
    spare = []
    if at is not None:
        bank, low = at >> 16, at & 0xFFFF
        if not 0x8000 <= low or bank in (0x7E, 0x7F) or bank > 0x7D or bank < 0x30:
            raise ValueError('--at 은 늘린 뱅크 30~7D 의 BB:AAAA')
        pic_bank = bank
        regions['pictures'] = [(at, (bank << 16) | 0x10000)]
        spare = list(o['spans']['pictures'])
    layout = {}
    for kind in ('pictures', 'palettes', 'lists'):
        items = blobs[kind]
        moving = kind == 'pictures' and at is not None
        in_place = all(rid in origin[kind] and len(items[rid]) <= len(origin[kind][rid][1]) for rid in items)
        if (not changed[kind] or in_place) and not moving:
            layout[kind] = {rid: int(rid, 16) for rid in items}
        else:
            sizes = lambda: [(rid, len(b)) for rid, b in items.items()]
            got, _ = place(sizes(), regions[kind])
            if got is None:
                # 원래 바이트를 지킨 것보다 다시 싼 것이 짧은 자료는 다시 싼 것으로 바꿔 한 번 더 놓아 본다.
                for rid in sorted(items):
                    again = ENCODERS[kind](res[kind][rid][0])
                    if len(again) < len(items[rid]):
                        items[rid] = again
                got, _ = place(sizes(), regions[kind])
            if got is None and kind != 'pictures':
                got, left = place(sizes(), regions[kind] + spare)
                if got is not None:
                    spare = left
            if got is None:
                need = sum(len(b) for b in items.values())
                room = sum(e - s for s, e in regions[kind] + (spare if kind != 'pictures' else []))
                raise ValueError(f'{kind} {need}바이트가 자리 {room}바이트에 들어가지 않음'
                                 + ('(--at 으로 그림을 옮기면 그 자리를 목록·팔레트가 쓸 수 있음)' if at is None else ''))
            layout[kind] = got
        for rid, addr in sorted(layout[kind].items(), key=lambda x: x[1]):
            data = items[rid]
            old = origin[kind].get(rid)
            if old is not None and addr == int(rid, 16) and data == bytes(old[1]):
                continue
            write(addr, data, f'{kind} {rid}', orig=addr >> 16 == BANK)
        t, n = TABLES[kind]
        new = b''.join((layout[kind][rid] & 0xFFFF).to_bytes(2, 'little') for rid in tables[kind])
        old = rom.d[lorom(t):lorom(t) + n * 2]
        if new != old:
            write(t, new, f'{kind} 표')
    if pic_bank != BANK:
        for site in PICTURE_BANK_SITES:
            write(site, bytes([pic_bank]), '그림 뱅크')
    alt_addr = layout['lists'][alt]
    if alt_addr != o['alt_list']:
        write(ALT_LIST_SITE, (alt_addr & 0xFFFF).to_bytes(2, 'little'), '세계 2 목록 2')
    manifest = {'format': 'dq5patch/1', 'name': name, 'writes': writes}
    end = max([0] + [lorom(int(w['at'].replace(':', ''), 16)) + len(bytes.fromhex(w['hex'])) for w in writes])
    if end > 0x180000:
        manifest['rom_size'] = 4 if end > 0x300000 else 3 if end > 0x200000 else 2
    return manifest, {k: {rid: cpu(a) for rid, a in v.items()} for k, v in layout.items()}


def check(rom, folder):
    o = original(rom)
    bad, raw, enc = 0, 0, 0
    for a, ((w, h, cells, tiles), old) in o['resources']['pictures'].items():
        data = encode_picture(w, h, cells, tiles)
        again = read_picture(Rom(data + bytes(0x8000)), 0x8000)
        if again[:4] != (w, h, cells, tiles):
            bad += 1
            print(f'{cpu(a)}: 다시 싼 그림이 다르게 풀림')
        raw += len(old)
        enc += len(data)
    print(f'그림 {len(o["resources"]["pictures"])}개: 원래 {raw}바이트, 다시 싸면 {enc}바이트, 다르게 풀린 그림 {bad}개')
    doc = dump(rom, folder)
    manifest, _ = patch(rom, doc, folder)
    print(f'내보낸 그대로 patch: 쓰기 {len(manifest["writes"])}개')
    return bool(bad or manifest['writes'])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom')
    ap.add_argument('cmd', choices=('dump', 'patch', 'check'))
    ap.add_argument('source', nargs='?', help='patch 의 bg.json')
    ap.add_argument('-o', '--out')
    ap.add_argument('--at', help='그림을 옮길 CPU 주소 BB:AAAA(늘린 뱅크)')
    ap.add_argument('--name', default='battle-bg')
    ap.add_argument('--layout', help='patch 의 자리 대응표 JSON')
    a = ap.parse_args()
    try:
        rom = Rom(open(a.rom, 'rb').read())
        if a.cmd == 'dump':
            if not a.out:
                raise ValueError('dump 에는 -o 폴더')
            doc = dump(rom, a.out)
            print(f'그림 {len(doc["pictures"])}개·목록 {len(doc["lists"])}개·팔레트 {len(doc["palettes"])}개 → {a.out}')
            return 0
        if a.cmd == 'check':
            import tempfile
            with tempfile.TemporaryDirectory() as tmp:
                return int(check(rom, tmp))
        if not a.source or not a.out:
            raise ValueError('patch 에는 bg.json 과 -o')
        at = None
        if a.at:
            if not re.fullmatch(r'[0-9A-Fa-f]{2}:[0-9A-Fa-f]{4}', a.at):
                raise ValueError('--at 은 BB:AAAA')
            at = int(a.at.replace(':', ''), 16)
        with open(a.source, encoding='utf-8') as f:
            doc = json.load(f)
        manifest, layout = patch(rom, doc, os.path.dirname(os.path.abspath(a.source)), at, a.name)
        os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True)
        with open(a.out, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, ensure_ascii=False, indent=1)
            f.write('\n')
        if a.layout:
            with open(a.layout, 'w', encoding='utf-8') as f:
                json.dump(layout, f, indent=1)
        print(f'쓰기 {len(manifest["writes"])}개 → {a.out}')
        return 0
    except (ValueError, OSError, KeyError) as e:
        print(f'오류: {e}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
