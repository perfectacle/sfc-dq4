"""DQ5(SFC) 실내 맵 그림 쓰기. CHR(4bpp 8x8)·CHR 팔레트 니블·BG 팔레트 줄·블록 정의를 내보내고 고친 것을 넣는다.
--set high 는 그룹 50 이상 맵의 따로 된 블록(17:8369)·CHR(1F:8000)·니블 표(0F:CF83)를 다룬다(BG 팔레트 줄은 함께 쓰므로
normal 쪽에서만). 형식은 sfc/dq5/docs/dq5-map-format.md 의 「블록」「CHR 과 VRAM 슬롯」「팔레트」「그룹 50 이상」,
입력은 sfc/dq5/docs/dq5-build-format.md 「실내 맵 그림 쓰기」.

  dump   롬 → 폴더(-o). mapgfx.json 과 chr.bin(CHR 번호 순서, 32바이트씩)
  patch  mapgfx.json → 패치 목록(-o). 바뀐 것이 없으면 쓰기 0개
         CHR 수를 늘리면 --chr-at BB:8000 으로 CHR 전체와 CHR 팔레트 니블 표를 옮긴다(CHR 은 DMA 로 읽음)
         블록 크기를 바꾸거나 늘리면 --blocks-at BB:AAAA(30~3F)로 블록 정의 전체를 옮긴다
  check  내보낸 그대로 patch 하면 쓰기 0개인지, 블록·CHR 수

원래 자리(normal): 블록 16:8000~(01:8CD8 이 다음 블록의 +2 가 FF 이면 끝으로 보고 최대 2,048개 포인터를 7E:B000 에 만듦),
CHR 13:8000 + 번호*32(번호 bit10~11 은 뱅크에 더함, 01:8C15 가 DMA), 니블 표 2A:8781(01:9304 가 $B1~$B3 에),
BG 팔레트 줄 10:E5C8 + 번호*32. 블록 뱅크는 01:92F4·01:8CDE 의 즉값, CHR 뱅크는 01:92F9 의 즉값이다.
블록 표를 만드는 01:8CD8 은 DB 를 블록 뱅크로 두고 곱셈기 $4202 를 절대 주소로 쓰므로 블록은 30~3F 에만 옮긴다.
high 는 01:9329 가 같은 변수를 두고, 맵을 불러올 때마다 01:8C72 가 최대 512개 포인터를 7E:A000 에 만든다.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5map import (  # noqa: E402
    CHR_BANK, CHR_PALETTE, HIGH_BLOCKS, HIGH_CHR_BANK, HIGH_CHR_PALETTE, PALETTES, PALSET_LISTS, ROW_READ, ROW_STUB,
    SET_READ, SET_STUB, Rom, lorom, palset_lists,
)

FORMAT = 'dq5mapgfx/1'
BANK = 0x8000
PALETTE_ROWS = 208
PALETTE_MAX = 0x800
SET_COUNT = 69
# 10:DE84 LDA $E5C8,Y(DB = 10)가 줄을 읽는다. 줄을 늘릴 때는 이 3바이트를 JSR $FFE0 으로 바꾸고, 원래 롬의 빈 자리
# 10:FFE0 에 PHX / TYX / LDA long,X / PLX / RTS 를 두어 옮긴 줄을 롱 주소로 읽는다(Y = 줄 번호 * 32).
# 세트를 늘릴 때(--sets-at)는 10:DE56 의 LDA $DFE4,X(세트 번호 * 4 + 낮0/밤2)를 JSR $FFE8 로 바꾼다. 스텁은 옮긴 세트 표를
# 긴 주소로 읽고 DB 를 그 뱅크로 바꿔, 뒤따르는 LDA ($00),Y 가 옮긴 목록을 읽게 한다. 그 뒤 LDA $1EAE 가 DB 로 읽으므로
# WRAM 거울이 있는 30~3F 에만 두고, 줄 읽기도 DB 를 보지 않게 늘 10:FFE0 스텁으로 바꾼다. 세트 번호는 8비트($00, STZ $01).
SET_ORIG = bytes.fromhex('bd e4 df')
SET_MAX, LIST_ROWS = 256, 7
SITES = {'block_bank': (0x0192F5, 1), 'builder_bank': (0x018CDF, 1), 'builder_start': (0x018CE7, 2),
         'chr_bank': (0x0192FA, 1), 'chrpal_bank': (0x019305, 1), 'chrpal_addr': (0x019309, 2)}
EXPECT = {'block_bank': b'\x16', 'builder_bank': b'\x16', 'builder_start': b'\x00\x80',
          'chr_bank': b'\x13', 'chrpal_bank': b'\x2a', 'chrpal_addr': b'\x81\x87'}
SETS = {
    'normal': {'block_start': 0x168000, 'block_max': 0x800, 'chr_bank': CHR_BANK, 'chr_palette': CHR_PALETTE,
               'sites': SITES, 'expect': EXPECT, 'palettes': True},
    # 01:8C72 는 LDA #$01FF 를 센 값으로 쓰고 첫 포인터를 따로 두어 512개까지.
    'high': {'block_start': HIGH_BLOCKS, 'block_max': 0x200, 'chr_bank': HIGH_CHR_BANK,
             'chr_palette': HIGH_CHR_PALETTE,
             'sites': {'block_bank': (0x01932A, 1), 'builder_bank': (0x018C79, 1), 'builder_start': (0x018C81, 2),
                       'chr_bank': (0x01932F, 1), 'chrpal_bank': (0x01933A, 1), 'chrpal_addr': (0x01933E, 2)},
             'expect': {'block_bank': b'\x17', 'builder_bank': b'\x17', 'builder_start': b'\x69\x83',
                        'chr_bank': b'\x1f', 'chrpal_bank': b'\x0f', 'chrpal_addr': b'\x83\xcf'},
             'palettes': False},
}


def cpu(a):
    return f'{a >> 16:02X}:{a & 0xFFFF:04X}'


def chr_addr(bank, i):
    return (bank + (i >> 10)) << 16 | 0x8000 + (i & 0x3FF) * 32


def check_sites(rom, kind='normal'):
    st = SETS[kind]
    for key, (at, n) in st['sites'].items():
        if rom.d[lorom(at):lorom(at) + n] != st['expect'][key]:
            raise ValueError(f'{cpu(at)}: 원래 롬의 {key} 즉값이 아님; 원본 롬으로 만들어야 함')


def read_blocks(rom, kind='normal'):
    """[(블록 바이트, 주소)]. 01:8CD8·01:8C72 와 같이 다음 블록의 +2 가 FF 이면 끝."""
    out, a = [], SETS[kind]['block_start']
    while len(out) < SETS[kind]['block_max']:
        b0 = rom.u8(a)
        size = 3 + 2 * (((b0 >> 3) & 7) + 1) * ((b0 & 7) + 1)
        out.append((rom.d[lorom(a):lorom(a) + size], a))
        a += size
        if rom.u8(a + 2) == 0xFF:
            break
    return out


def block_doc(raw):
    b0 = raw[0]
    w, h = ((b0 >> 3) & 7) + 1, (b0 & 7) + 1
    return {'w': w, 'h': h, 'flags': b0 >> 6, 'b1': raw[1], 'attr': raw[2],
            'words': [raw[3 + i * 2] | raw[4 + i * 2] << 8 for i in range(w * h)]}


def encode_block(b, chr_count):
    if not isinstance(b, dict) or set(b) - {'w', 'h', 'flags', 'b1', 'attr', 'words'}:
        raise ValueError('블록 필드는 w·h·flags·b1·attr·words')
    w, h, flags, b1, attr, words = (b.get(k) for k in ('w', 'h', 'flags', 'b1', 'attr', 'words'))
    # attr FF 는 01:8CD8 이 표의 끝 표지로 읽으므로 받지 않는다.
    for name, v, hi in (('w', w, 8), ('h', h, 8), ('flags', flags, 3), ('b1', b1, 255), ('attr', attr, 254)):
        if type(v) is not int or not (1 if name in 'wh' else 0) <= v <= hi:
            raise ValueError(f'블록 {name} 범위 밖: {v!r}')
    if not isinstance(words, list) or len(words) != w * h:
        raise ValueError(f'블록 words 는 {w}x{h}개')
    out = bytearray([flags << 6 | (w - 1) << 3 | (h - 1), b1, attr])
    for v in words:
        if type(v) is not int or not 0 <= v <= 0xFFFF or v & 0x3000:
            raise ValueError(f'블록 칸 {v!r}: CHR 번호 bit0-11, 반전 bit14·15')
        if (v & 0xFFF) >= chr_count:
            raise ValueError(f'블록 칸이 없는 CHR {v & 0xFFF:03X} 를 씀(CHR {chr_count}개)')
        out += v.to_bytes(2, 'little')
    return bytes(out)


def chr_count(rom, blocks):
    return max(w & 0xFFF for raw, _ in blocks for w in block_doc(raw)['words']) + 1


def set_count(rom, table):
    """세트 표의 세트 수. 첫 목록이 표 바로 뒤에서 시작한다(원본 69세트)."""
    first = rom.u16(table)
    if first <= table & 0xFFFF or (first - (table & 0xFFFF)) % 4:
        raise ValueError(f'{cpu(table)}: 팔레트 세트 표의 첫 포인터가 맞지 않음')
    return (first - (table & 0xFFFF)) // 4


def palette_lists(rom):
    """(세트마다 [낮 목록 id, 밤 목록 id], {목록 id: 줄 번호 7개}). 목록 id 는 세트 표 뱅크 안 주소 4자리."""
    table = palset_lists(rom)
    bank = table & 0xFF0000
    sets, lists = [], {}
    for i in range(set_count(rom, table)):
        pair = [f'{rom.u16(table + i * 4 + k):04X}' for k in (0, 2)]
        for p in pair:
            lists.setdefault(p, [rom.u16(bank | int(p, 16) + j * 2) for j in range(LIST_ROWS)])
        sets.append(pair)
    return sets, dict(sorted(lists.items()))


def row_stub(rows):
    return bytes([0xDA, 0xBB, 0xBF]) + rows.to_bytes(3, 'little') + bytes([0xFA, 0x60])


def set_stub(table):
    """10:DE56 의 LDA $DFE4,X 대신(M·X 16비트). 옮긴 세트 표를 읽고 DB 를 그 뱅크로 바꾼다."""
    return (b'\xbf' + table.to_bytes(3, 'little') + b'\x48' + b'\xe2\x20' + bytes([0xA9, table >> 16]) + b'\x48\xab'
            + b'\xc2\x20' + b'\x68' + b'\x60')


def write_sets(sets_at, sets, lists, rows, write):
    """세트 표와 목록을 sets_at 에 [세트 표 N×4][목록 14바이트씩] 으로 두고 10:DE56·10:DE84 를 스텁으로 바꾼다.
    목록은 세트 표에 처음 나오는 차례로 둔다. 세트 0 의 낮 목록이 표 바로 뒤에 와야 세트 수를 셀 수 있다(set_count)."""
    bank, low = sets_at >> 16, sets_at & 0xFFFF
    order = list(dict.fromkeys([v for pair in sets for v in pair] + sorted(lists)))
    start = low + len(sets) * 4
    where = {lid: start + k * LIST_ROWS * 2 for k, lid in enumerate(order)}
    raw = b''.join(where[v].to_bytes(2, 'little') for pair in sets for v in pair)
    raw += b''.join(v.to_bytes(2, 'little') for lid in order for v in lists[lid])
    if not 0x30 <= bank <= 0x3F or low < 0x8000 or low + len(raw) > 0x10000:
        raise ValueError(f'--sets-at 은 30~3F 의 한 뱅크 안({len(raw)}바이트, 스텁이 DB 를 바꿔 WRAM 거울이 필요)')
    write(sets_at, raw, f'BG 팔레트 세트 표 {len(sets)}개와 목록 {len(order)}개', orig=False)
    write(SET_STUB, set_stub(sets_at), 'BG 팔레트 세트 표 읽기(DB 를 옮긴 뱅크로)')
    write(SET_READ, bytes([0x20, SET_STUB & 0xFF, SET_STUB >> 8 & 0xFF]), 'BG 팔레트 세트 표 읽기 훅')
    if rows == PALETTES:
        write(ROW_STUB, row_stub(PALETTES), 'BG 팔레트 줄 읽기(DB 를 보지 않게 원래 자리를 긴 주소로)')
        write(ROW_READ, bytes([0x20, ROW_STUB & 0xFF, ROW_STUB >> 8 & 0xFF]), 'BG 팔레트 줄 읽기 훅')


def dump(rom, out, kind='normal'):
    st = SETS[kind]
    check_sites(rom, kind)
    blocks = read_blocks(rom, kind)
    n = chr_count(rom, blocks)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, 'chr.bin'), 'wb') as f:
        for i in range(n):
            o = lorom(chr_addr(st['chr_bank'], i))
            f.write(rom.d[o:o + 32])
    nib = [rom.u8(st['chr_palette'] + i // 2) >> (0 if i & 1 else 4) & 15 for i in range(n)]
    doc = {'format': FORMAT, 'set': kind, 'chr_file': 'chr.bin', 'chr_palettes': nib,
           'blocks': [block_doc(raw) for raw, _ in blocks]}
    if st['palettes']:
        doc['palettes'] = [[rom.u16(PALETTES + r * 32 + c * 2) for c in range(16)] for r in range(PALETTE_ROWS)]
        doc['palette_sets'], doc['palette_lists'] = palette_lists(rom)
    with open(os.path.join(out, 'mapgfx.json'), 'w', encoding='utf-8') as f:
        json.dump(doc, f, separators=(',', ':'))
        f.write('\n')
    return doc


def patch(rom, doc, folder, chr_at=None, blocks_at=None, name='map-gfx', palettes_at=None, sets_at=None):
    if not isinstance(doc, dict) or doc.get('format') != FORMAT or not isinstance(doc.get('set', 'normal'), str) \
            or doc.get('set', 'normal') not in SETS:
        raise ValueError(f'format={FORMAT}, set 은 {sorted(SETS)}')
    kind = doc.get('set', 'normal')
    st = SETS[kind]
    fields = {'format', 'set', 'chr_file', 'chr_palettes', 'blocks'} | (
        {'palettes', 'palette_sets', 'palette_lists'} if st['palettes'] else set())
    if set(doc) - fields or not {'chr_file', 'chr_palettes', 'blocks'} <= set(doc):
        raise ValueError(f'{kind} 문서는 {sorted(fields)} 만')
    check_sites(rom, kind)
    sites, chr_bank0, chr_palette0 = st['sites'], st['chr_bank'], st['chr_palette']
    blocks = read_blocks(rom, kind)
    count0 = chr_count(rom, blocks)
    with open(os.path.join(folder, doc['chr_file']), 'rb') as f:
        chrs = f.read()
    if len(chrs) % 32 or not 1 <= len(chrs) // 32 <= 0x1000:
        raise ValueError('chr.bin 은 32바이트 타일 1~4096개')
    count = len(chrs) // 32
    nib = doc.get('chr_palettes')
    if not isinstance(nib, list) or len(nib) != count or any(type(v) is not int or not 0 <= v <= 15 for v in nib):
        raise ValueError(f'chr_palettes 는 CHR 수({count})만큼의 0~15')
    pals = doc.get('palettes', [])
    if st['palettes'] and (not isinstance(pals, list) or not PALETTE_ROWS <= len(pals) <= PALETTE_MAX or any(
            not isinstance(r, list) or len(r) != 16 or any(type(c) is not int or not 0 <= c <= 0x7FFF for c in r)
            for r in pals)):
        raise ValueError(f'palettes 는 15비트 색 16개짜리 줄 {PALETTE_ROWS}~{PALETTE_MAX}개')
    if not st['palettes'] and (palettes_at is not None or sets_at is not None):
        raise ValueError('--palettes-at·--sets-at 은 normal 쪽에서만')
    if sets_at is not None and rom.d[lorom(SET_READ):lorom(SET_READ) + 3] != SET_ORIG:
        raise ValueError(f'{cpu(SET_READ)}: 원래 롬의 세트 표 읽기가 아님; 원본 롬으로 만들어야 함')
    if len(pals) > PALETTE_ROWS and palettes_at is None:
        raise ValueError(f'BG 팔레트 줄 {len(pals)}개는 원래 {PALETTE_ROWS}개보다 많음: 10:FFC8 뒤가 비지 않아 '
                         '--palettes-at 으로 옮겨야 함')
    if not isinstance(doc.get('blocks'), list) or not 1 <= len(doc['blocks']) <= st['block_max']:
        raise ValueError(f'blocks 는 1~{st["block_max"]}개')
    new_blocks = [encode_block(b, count) for b in doc['blocks']]
    writes = []

    def write(addr, data, note, orig=True):
        w = {'at': cpu(addr), 'hex': data.hex(' '), 'note': note}
        if orig:
            o = lorom(addr)
            w['orig'] = rom.d[o:o + len(data)].hex(' ')
        writes.append(w)

    # BG 팔레트 줄: 제자리 또는 --palettes-at.
    if palettes_at is None:
        for r, row in enumerate(pals):
            raw = b''.join(c.to_bytes(2, 'little') for c in row)
            o = lorom(PALETTES + r * 32)
            if raw != rom.d[o:o + 32]:
                write(PALETTES + r * 32, raw, f'BG 팔레트 줄 {r}')
    elif st['palettes']:
        bank, low = palettes_at >> 16, palettes_at & 0xFFFF
        raw = b''.join(c.to_bytes(2, 'little') for row in pals for c in row)
        start = lorom(palettes_at)
        if not 0x30 <= bank <= 0x7D or low < 0x8000 or lorom(0x7DFFFF) + 1 < start + len(raw):
            raise ValueError('--palettes-at 은 늘린 뱅크 30~7D, 줄 전체가 7D:FFFF 안')
        # 롱 색인 읽기는 뱅크 끝에서 다음 뱅크 0000 으로 넘어가므로(LoROM 이 아님) 한 뱅크 안에 둔다.
        if low + len(raw) > 0x10000:
            raise ValueError(f'--palettes-at 부터 {len(raw)}바이트가 한 뱅크를 넘음')
        write(palettes_at, raw, 'BG 팔레트 줄', orig=False)
        write(ROW_STUB, row_stub(palettes_at), 'BG 팔레트 줄 읽기')
        write(ROW_READ, bytes([0x20, ROW_STUB & 0xFF, ROW_STUB >> 8 & 0xFF]), 'BG 팔레트 줄 읽기 훅')
    if st['palettes']:
        sets0, lists0 = palette_lists(rom)
        sets, lists = doc.get('palette_sets', sets0), doc.get('palette_lists', lists0)
        if not isinstance(lists, dict) or any(not re.fullmatch('[0-9A-F]{4}', k) for k in lists):
            raise ValueError('palette_lists 는 목록 id(대문자 16진 4자리) → 줄 번호')
        # sets0 은 그 롬의 세트 수(set_count)를 센 것이라, 옮긴 롬에서도 늘렸는지를 바르게 가른다.
        grow = set(lists) != set(lists0) or not isinstance(sets, list) or len(sets) != len(sets0)
        if grow and sets_at is None:
            raise ValueError(f'세트 {len(sets0)}개·원래 목록 id 와 다르면(늘리기) 뱅크 10 이 차 있어 --sets-at 으로 옮겨야 함')
        moved = palset_lists(rom) != PALSET_LISTS
        if moved and sets_at is None and (sets != sets0 or lists != lists0):
            raise ValueError('세트 표를 이미 --sets-at 으로 옮긴 롬이라 뱅크 10 제자리 쓰기는 읽히지 않음; '
                             '원본 롬으로 --sets-at 을 주어 만들어야 함')
        if not isinstance(sets, list) or not 1 <= len(sets) <= SET_MAX or any(
                not isinstance(p, list) or len(p) != 2 or any(v not in lists for v in p) for p in sets):
            raise ValueError(f'palette_sets 는 palette_lists 의 [낮 목록 id, 밤 목록 id] 1~{SET_MAX}개')
        for lid, rows in lists.items():
            if not isinstance(rows, list) or len(rows) != LIST_ROWS or any(
                    type(v) is not int or not 0 <= v < len(pals) for v in rows):
                raise ValueError(f'palette_lists.{lid}: 줄 번호(0~{len(pals) - 1}) {LIST_ROWS}개')
            if sets_at is None and rows != lists0[lid]:
                write(0x100000 | int(lid, 16), b''.join(v.to_bytes(2, 'little') for v in rows), f'BG 팔레트 목록 {lid}')
        if sets_at is not None:
            write_sets(sets_at, sets, lists, PALETTES if palettes_at is None else palettes_at, write)
        else:
            for i, (pair, pair0) in enumerate(zip(sets, sets0)):
                if pair != pair0:
                    write(PALSET_LISTS + i * 4, b''.join(int(v, 16).to_bytes(2, 'little') for v in pair),
                          f'BG 팔레트 세트 {i}')
    # CHR 과 니블 표.
    if count > count0 and chr_at is None:
        raise ValueError(f'CHR {count}개는 원래 {count0}개보다 많음: 원래 자리 뒤는 다른 자료라 --chr-at 으로 옮겨야 함')
    nib_bytes = bytearray((count + 1) // 2)
    for i, v in enumerate(nib):
        nib_bytes[i // 2] |= v << (0 if i & 1 else 4)
    if chr_at is None:
        for i in range(count):
            o = lorom(chr_addr(chr_bank0, i))
            if chrs[i * 32:i * 32 + 32] != rom.d[o:o + 32]:
                write(chr_addr(chr_bank0, i), chrs[i * 32:i * 32 + 32], f'CHR {i:03X}')
        old = rom.d[lorom(chr_palette0):lorom(chr_palette0) + len(nib_bytes)]
        # 홀수 개면 마지막 바이트의 아래 니블은 다음 CHR 몫이라 원래 값을 둔다.
        if count & 1:
            nib_bytes[-1] |= old[-1] & 0x0F
        for i in range(len(nib_bytes)):
            if nib_bytes[i] != old[i]:
                write(chr_palette0 + i, bytes([nib_bytes[i]]), f'CHR 팔레트 니블 {i * 2:03X}')
    else:
        bank, low = chr_at >> 16, chr_at & 0xFFFF
        last = bank + ((count - 1) >> 10)
        if low != 0x8000 or not 0x30 <= bank or last > 0x7D:
            raise ValueError('--chr-at 은 BB:8000(BB 30~7D), CHR 번호 bit10~11 이 뱅크에 더해짐')
        for b in range(bank, last + 1):
            part = chrs[(b - bank) * 0x8000:(b - bank + 1) * 0x8000]
            write(b << 16 | 0x8000, part, f'CHR 뱅크 {b - bank}', orig=False)
        end = lorom(chr_addr(bank, count - 1)) + 32
        if end % BANK + len(nib_bytes) > BANK:
            end = (end // BANK + 1) * BANK
        nib_at = (end // BANK) << 16 | 0x8000 + end % BANK
        if nib_at >> 16 > 0x7D:
            raise ValueError('CHR 팔레트 니블 표가 7D 뱅크 뒤로 넘음')
        write(nib_at, bytes(nib_bytes), 'CHR 팔레트 니블 표', orig=False)
        write(sites['chr_bank'][0], bytes([bank]), 'CHR 뱅크')
        write(sites['chrpal_bank'][0], bytes([nib_at >> 16]), 'CHR 팔레트 니블 표 뱅크')
        write(sites['chrpal_addr'][0], (nib_at & 0xFFFF).to_bytes(2, 'little'), 'CHR 팔레트 니블 표 주소')
    # 블록.
    old_raw = [raw for raw, _ in blocks]
    same_shape = len(new_blocks) == len(old_raw) and all(len(a) == len(b) for a, b in zip(new_blocks, old_raw))
    if same_shape and blocks_at is None:
        for (raw, addr), new in zip(blocks, new_blocks):
            if new != raw:
                write(addr, new, '블록')
    elif blocks_at is None:
        raise ValueError('블록 수나 크기가 바뀜: 원래 자리 뒤는 다른 자료라 --blocks-at 으로 옮겨야 함')
    else:
        bank, low = blocks_at >> 16, blocks_at & 0xFFFF
        # 끝 표지: 마지막 블록 다음의 +2 가 FF 여야 01:8CD8 이 멈춘다.
        data = b''.join(new_blocks) + b'\xff\xff\xff'
        if not 0x30 <= bank <= 0x3F or low < 0x8000 or low + len(data) > 0x10000:
            raise ValueError(f'--blocks-at 은 30~3F 의 한 뱅크 안({len(data)}바이트)')
        write(blocks_at, data, '블록 정의', orig=False)
        write(sites['block_bank'][0], bytes([bank]), '블록 뱅크')
        write(sites['builder_bank'][0], bytes([bank]), '블록 표 만들기 뱅크')
        write(sites['builder_start'][0], low.to_bytes(2, 'little'), '블록 표 시작')
    manifest = {'format': 'dq5patch/1', 'name': name, 'writes': writes}
    end = max([0] + [lorom(int(w['at'].replace(':', ''), 16)) + len(bytes.fromhex(w['hex'])) for w in writes])
    if end > 0x180000:
        manifest['rom_size'] = 4 if end > 0x300000 else 3 if end > 0x200000 else 2
    return manifest


def check(rom, folder, kind='normal'):
    doc = dump(rom, folder, kind)
    manifest = patch(rom, doc, folder)
    print(f'{kind}: 블록 {len(doc["blocks"])}개, CHR {len(doc["chr_palettes"])}개, '
          f'BG 팔레트 줄 {len(doc.get("palettes", []))}개; 내보낸 그대로 patch: 쓰기 {len(manifest["writes"])}개')
    return bool(manifest['writes'])


def parse_at(v, name):
    if v is None:
        return None
    if not re.fullmatch(r'[0-9A-Fa-f]{2}:[0-9A-Fa-f]{4}', v):
        raise ValueError(f'{name} 은 BB:AAAA')
    return int(v.replace(':', ''), 16)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom')
    ap.add_argument('cmd', choices=('dump', 'patch', 'check'))
    ap.add_argument('source', nargs='?')
    ap.add_argument('-o', '--out')
    ap.add_argument('--chr-at')
    ap.add_argument('--blocks-at')
    ap.add_argument('--palettes-at', help='BG 팔레트 줄 전체를 옮길 CPU 주소(줄을 늘릴 때)')
    ap.add_argument('--sets-at', help='BG 팔레트 세트 표와 목록을 옮길 CPU 주소(30~3F, 세트·목록을 늘릴 때)')
    ap.add_argument('--name', default='map-gfx')
    ap.add_argument('--set', default='normal', choices=sorted(SETS), help='dump·check 할 쪽(patch 는 문서의 set)')
    a = ap.parse_args()
    try:
        rom = Rom(open(a.rom, 'rb').read())
        if a.cmd == 'dump':
            if not a.out:
                raise ValueError('dump 에는 -o 폴더')
            doc = dump(rom, a.out, a.set)
            print(f'{a.set}: 블록 {len(doc["blocks"])}개·CHR {len(doc["chr_palettes"])}개 → {a.out}')
            return 0
        if a.cmd == 'check':
            import tempfile
            with tempfile.TemporaryDirectory() as tmp:
                return int(check(rom, tmp, a.set))
        if not a.source or not a.out:
            raise ValueError('patch 에는 mapgfx.json 과 -o')
        with open(a.source, encoding='utf-8') as f:
            doc = json.load(f)
        if isinstance(doc, dict) and doc.get('set', 'normal') != a.set and a.set != 'normal':
            raise ValueError(f'--set {a.set} 이지만 문서의 set 은 {doc.get("set", "normal")}(patch 는 문서의 set 을 따름)')
        manifest = patch(rom, doc, os.path.dirname(os.path.abspath(a.source)),
                         parse_at(a.chr_at, '--chr-at'), parse_at(a.blocks_at, '--blocks-at'), a.name,
                         parse_at(a.palettes_at, '--palettes-at'), parse_at(a.sets_at, '--sets-at'))
        os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True)
        with open(a.out, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, ensure_ascii=False, indent=1)
            f.write('\n')
        print(f'쓰기 {len(manifest["writes"])}개 → {a.out}')
        return 0
    except (ValueError, OSError, KeyError, TypeError) as e:
        print(f'오류: {e}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
