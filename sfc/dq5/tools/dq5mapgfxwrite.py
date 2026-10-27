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
    CHR_BANK, CHR_PALETTE, HIGH_BLOCKS, HIGH_CHR_BANK, HIGH_CHR_PALETTE, PALETTES, Rom, lorom,
)

FORMAT = 'dq5mapgfx/1'
BANK = 0x8000
PALETTE_ROWS = 208
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
    with open(os.path.join(out, 'mapgfx.json'), 'w', encoding='utf-8') as f:
        json.dump(doc, f, separators=(',', ':'))
        f.write('\n')
    return doc


def patch(rom, doc, folder, chr_at=None, blocks_at=None, name='map-gfx'):
    if not isinstance(doc, dict) or doc.get('format') != FORMAT or not isinstance(doc.get('set', 'normal'), str) \
            or doc.get('set', 'normal') not in SETS:
        raise ValueError(f'format={FORMAT}, set 은 {sorted(SETS)}')
    kind = doc.get('set', 'normal')
    st = SETS[kind]
    fields = {'format', 'set', 'chr_file', 'chr_palettes', 'blocks'} | ({'palettes'} if st['palettes'] else set())
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
    if st['palettes'] and (not isinstance(pals, list) or len(pals) != PALETTE_ROWS or any(
            not isinstance(r, list) or len(r) != 16 or any(type(c) is not int or not 0 <= c <= 0x7FFF for c in r)
            for r in pals)):
        raise ValueError(f'palettes 는 15비트 색 16개짜리 줄 {PALETTE_ROWS}개(줄 수는 늘리지 않음)')
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

    # BG 팔레트 줄: 제자리.
    for r, row in enumerate(pals):
        raw = b''.join(c.to_bytes(2, 'little') for c in row)
        o = lorom(PALETTES + r * 32)
        if raw != rom.d[o:o + 32]:
            write(PALETTES + r * 32, raw, f'BG 팔레트 줄 {r}')
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
                         parse_at(a.chr_at, '--chr-at'), parse_at(a.blocks_at, '--blocks-at'), a.name)
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
