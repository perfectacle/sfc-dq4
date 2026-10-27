"""DQ5 맵 OBJ 타일과 탈것 타일 쓰기. 읽기 형식은 sfc/dq5/docs/dq5-graphics-format.md 의 「맵 OBJ 타일」·「탈것」.

맵 OBJ 타일: 1F:D4AF 가 1F:D59A 의 6바이트 항목 [BC][BD(bit7 = 압축)][주소 16비트][뱅크][잡는 타일 수] 으로 올린다.
  압축이면 낮은 바이트(평면 0·2)·높은 바이트(평면 1·3) 두 줄기를 1F:D28B 의 런 길이(00~7F 그대로 c+1, 80 끝,
  81~FF 반복)로 둔다. 여러 항목이 같은 자료를 가리킨다.
탈것 타일: 01:C4BE 가 A 뱅크·X 주소·Y 타일 수로 같은 런 길이(4bpp 바이트 한 줄기)를 푼다. 부르는 곳은
  01:BC93(양탄자 2F)·01:C3C0(天空城 14)·01:C06B·01:C07B(マスタードラゴン 40·39) 의 LDA #뱅크·LDX #주소.

자료 덩어리마다 타일을 16개씩 한 줄로 늘어놓은 색 번호 PNG(팔레트 모드, 픽셀 값 = 색 번호)를 받는다. 타일 수와
타일 배치(16:F862·04 뱅크 칸 표)·팔레트·VRAM 에 잡는 수는 그대로 둔다. 새 자료가 원래 자리보다 길면 --at 에 놓고
항목의 주소(맵 OBJ)나 LDA·LDX 피연산자(탈것)를 바꾼다.

  python sfc/dq5/tools/dq5objtiles.py rom/dq5.sfc dump -o work/objtiles      # 덩어리마다 PNG 와 objtiles.json
  python sfc/dq5/tools/dq5objtiles.py rom/dq5.sfc patch work/objtiles/objtiles.json -o work/objtiles.dq5patch.json --at 3C:8000
  python sfc/dq5/tools/dq5objtiles.py rom/dq5.sfc check [문서] [--at 3C:8000]
"""
import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dq5sprite as S  # noqa: E402
from dq5build import PatchError  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402

FORMAT = 'dq5objtiles/1'
PER_ROW = 16
# 탈것 덩어리: (이름, LDA #뱅크 피연산자 자리, LDX #주소 피연산자 자리). 01:C4BE 를 부르기 전 a9 BB a2 LL HH a0 NN.
VEHICLE_SITES = {0x16E7BD: (0x01BC94, 0x01BC96), 0x2B84F0: (0x01C3C1, 0x01C3C3),
                 0x16EAF2: (0x01C06C, 0x01C06E), 0x16F115: (0x01C07C, 0x01C07E)}


def cpu(addr):
    return f'{addr >> 16:02X}:{addr & 0xFFFF:04X}'


def address(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9A-Fa-f]{2}:[0-9A-Fa-f]{4}', value):
        raise ValueError('주소는 BB:AAAA 문자열이어야 함')
    bank, low = (int(p, 16) for p in value.split(':'))
    if bank > 0x7D or low < 0x8000:
        raise ValueError('주소는 뱅크 00~7D 의 8000~FFFF 여야 함')
    return bank << 16 | low


def blocks(rom):
    """자료 덩어리 {이름: {data, end, split, tiles, users}}. split = 낮·높은 바이트 두 줄기(맵 OBJ)."""
    out, named = {}, {}
    for i, m in enumerate(S.map_objects(rom)):
        if not m['packed']:
            raise ValueError(f'맵 OBJ 항목 {i}: 압축하지 않은 자료는 다루지 않음')
        # 이름은 그 자료를 쓰는 첫 항목 번호(1F:D59A 차례)라, 자료를 옮겨도 바뀌지 않는다.
        name = named.setdefault(m['data'], f'obj-{i:02d}')
        block = out.setdefault(name, {'data': m['data'], 'end': m['end'], 'split': True, 'tiles': m['tiles'],
                                      'entries': [], 'users': [], 'reserve': []})
        block['entries'].append(m['entry'])
        block['users'].append(m['where'])
        # +5 만큼만 $1995 를 늘리지만 줄기는 전부 그 자리부터 쓴다. 잡은 수 뒤 타일은 다음 자리로 넘친다.
        block['reserve'].append(m['reserve'])
    for v in S.VEHICLES:
        for k, (original, n, _) in enumerate(v['tiles']):
            if original not in VEHICLE_SITES:
                raise ValueError(f'탈것 {v["id"]:02X} 타일 {cpu(original)}: 부르는 곳을 모름')
            # 옮긴 롬도 읽도록 자료 주소는 부르는 곳의 LDA·LDX 피연산자에서 읽는다.
            bank_at, addr_at = VEHICLE_SITES[original]
            a = rom.u8(bank_at) << 16 | rom.u16(addr_at)
            data, end = S.unpack(rom, a, False)
            out[f'veh-{v["id"]:02X}-{k}'] = {'data': a, 'end': end, 'split': False, 'count': n, 'entries': [],
                                             'site': original,
                                             'users': [f'탈것 {v["id"]:02X} {v["what"]}'],
                                             'tiles': [bytes(data[i * 32:i * 32 + 32]) for i in range(n)]}
    for b in out.values():
        if b['data'] >> 16 != (b['end'] - 1) >> 16:
            raise ValueError(f'{cpu(b["data"])}: 자료가 뱅크를 넘음')
    return out


def tile_bytes(rows):
    out = bytearray(32)
    for y, row in enumerate(rows):
        for x, c in enumerate(row):
            for bit in range(4):
                out[(bit // 2) * 16 + y * 2 + bit % 2] |= ((c >> bit) & 1) << (7 - x)
    return bytes(out)


def sheet_size(n):
    return PER_ROW * 8, ((n + PER_ROW - 1) // PER_ROW) * 8


def dump_image(tiles, path, palette):
    w, h = sheet_size(len(tiles))
    grid = [[0] * w for _ in range(h)]
    for i, t in enumerate(tiles):
        for y, row in enumerate(S.pixels(t)):
            for x, c in enumerate(row):
                grid[(i // PER_ROW) * 8 + y][(i % PER_ROW) * 8 + x] = c
    image = Image.new('P', (w, h))
    image.putpalette([c for color in palette for c in S.rgb(color)])
    image.putdata([c for row in grid for c in row])
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    image.save(path, transparency=0)


def read_tiles(path, n):
    with Image.open(path) as opened:
        image = opened.copy()
    w, h = sheet_size(n)
    if image.mode != 'P' or image.size != (w, h):
        raise ValueError(f'{path}: {w}x{h} 팔레트 모드 PNG 여야 함(지금 {image.mode} {image.size[0]}x{image.size[1]})')
    data = list(image.tobytes())
    if max(data) > 15:
        raise ValueError(f'{path}: 색 번호는 0~15 여야 함')
    grid = [data[y * w:(y + 1) * w] for y in range(h)]
    tiles = []
    for i in range((h // 8) * PER_ROW):
        rows = [grid[(i // PER_ROW) * 8 + y][(i % PER_ROW) * 8:(i % PER_ROW) * 8 + 8] for y in range(8)]
        if i >= n:
            if any(any(r) for r in rows):
                raise ValueError(f'{path}: 타일 {n}개 뒤 칸은 비어 있어야 함(타일 수는 바꾸지 않음)')
            continue
        tiles.append(tile_bytes(rows))
    return tiles


def rle(data):
    """1F:D28B 런 길이: 00~7F = 뒤 c+1 바이트 그대로(7F 도 128바이트), 81~FF = 다음 바이트 (c&7F)+1 번, 80 끝. 가장 짧게."""
    n = len(data)
    cost, choice = [0] * (n + 1), [None] * n
    for i in range(n - 1, -1, -1):
        best = None
        for length in range(1, min(128, n - i) + 1):
            c = length + 1 + cost[i + length]
            if best is None or c < best[0]:
                best = (c, length, False)
        run = 1
        while run < min(128, n - i) and data[i + run] == data[i]:
            run += 1
        for length in range(2, run + 1):
            if 2 + cost[i + length] < best[0]:
                best = (2 + cost[i + length], length, True)
        cost[i], choice[i] = best[0], best[1:]
    out, i = bytearray(), 0
    while i < n:
        length, repeated = choice[i]
        out += bytes([0x80 | (length - 1), data[i]]) if repeated else bytes([length - 1]) + data[i:i + length]
        i += length
    return bytes(out) + b'\x80'


def encode(tiles, split):
    if split:
        return rle(b''.join(t[0::2] for t in tiles)) + rle(b''.join(t[1::2] for t in tiles))
    return rle(b''.join(tiles))


def decode(raw, split, base=0x308000):
    """encode 의 역(dq5sprite 의 디코더로 푼다)."""
    data = bytearray(0x200000)
    data[lorom(base):lorom(base) + len(raw)] = raw
    rom = Rom(data)
    if split:
        return S.split_tiles(rom, base, False)[0]
    out, _ = S.unpack(rom, base, False)
    return [bytes(out[i * 32:i * 32 + 32]) for i in range(len(out) // 32)]


def dump(rom, folder):
    folder = Path(folder)
    rows = []
    palette = S.obj_palettes(rom)[0]
    for name, b in blocks(rom).items():
        dump_image(b['tiles'], folder / f'{name}.png', palette)
        users = [f'{u} (잡는 타일 {r})' for u, r in zip(b['users'], b['reserve'])] if b['split'] else b['users']
        rows.append({'block': name, 'image': f'{name}.png', 'tiles': len(b['tiles']), 'users': users})
    doc = {'format': FORMAT, 'blocks': rows}
    (folder / 'objtiles.json').write_text(json.dumps(doc, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    return doc


def plan(rom, doc, base):
    if not isinstance(doc, dict) or doc.keys() - {'format', 'blocks'} or doc.get('format') != FORMAT:
        raise ValueError(f'문서는 format={FORMAT}, blocks 만 담은 객체여야 함')
    known = blocks(rom)
    rows = doc.get('blocks', [])
    if not isinstance(rows, list):
        raise ValueError('blocks는 배열이어야 함')
    out = {}
    for i, row in enumerate(rows):
        label = f'blocks[{i}]'
        # tiles·users 는 dump 가 붙이는 보기용이다. 바꾸면 거부하지는 않지만 읽지 않는다.
        if not isinstance(row, dict) or row.keys() - {'block', 'image', 'tiles', 'users'} or \
                not isinstance(row.get('block'), str) or not isinstance(row.get('image'), str):
            raise ValueError(f'{label}: block·image(와 보기용 tiles·users)만 받음')
        name = row['block']
        if name not in known or name in out:
            raise ValueError(f'{label}: {name} 은 없는 덩어리이거나 두 번 지정함')
        out[name] = read_tiles(base / row['image'], len(known[name]['tiles']))
    return known, out


def patch(rom, doc, base=Path('.'), at=None):
    known, tiles = plan(rom, doc, base)
    writes, cursor = [], at

    def write(addr, data, note, orig=True):
        item = {'at': cpu(addr), 'hex': data.hex(' '), 'note': note}
        if orig:
            item['orig'] = bytes(rom.d[lorom(addr):lorom(addr) + len(data)]).hex(' ')
        writes.append(item)

    for name in sorted(tiles):
        b = known[name]
        if tiles[name] == b['tiles']:
            continue
        if b['split']:
            spill = [i for i, (new, old) in enumerate(zip(tiles[name], b['tiles'])) if new != old and i >= min(b['reserve'])]
            if spill:
                print(f'{name}: 바꾼 타일 {" ".join(f"{i:02X}" for i in spill)} 은 어떤 맵에서는 잡은 수 '
                      f'({"·".join(str(r) for r in b["reserve"])}) 밖이라 다음 VRAM 자리로 넘쳐 올라감', file=sys.stderr)
        raw = encode(tiles[name], b['split'])
        if b['data'] + len(raw) <= b['end']:
            write(b['data'], raw, f'{name} 타일 {len(tiles[name])}개(쓰는 곳: {", ".join(b["users"])})')
            continue
        if cursor is None:
            raise ValueError(f'{name}: 새 자료 {len(raw)}바이트가 원래 {b["end"] - b["data"]}바이트보다 길어 --at 이 필요함')
        if (cursor & 0xFFFF) + len(raw) > 0x10000:
            cursor = ((cursor >> 16) + 1) << 16 | 0x8000
        # 옮긴 자료는 orig 없이 쓴다. 원래 롬 안이면 빌더가 빈 자리 지도 밖을 거부한다.
        write(cursor, raw, f'{name} 옮김', orig=False)
        if b['split']:
            for entry in b['entries']:
                write(entry + 2, bytes([cursor & 0xFF, cursor >> 8 & 0xFF, cursor >> 16]), f'{name} 항목 {cpu(entry)} 주소')
        else:
            bank_at, addr_at = VEHICLE_SITES[b['site']]
            write(bank_at, bytes([cursor >> 16]), f'{name} 뱅크(LDA #)')
            write(addr_at, (cursor & 0xFFFF).to_bytes(2, 'little'), f'{name} 주소(LDX #)')
        cursor += len(raw)
    return {'format': 'dq5patch/1', 'name': 'obj-tiles', 'writes': writes}


def built(rom, manifest):
    from dq5build import build, parse_at
    lists = [(parse_at(w['at'])[0], bytes.fromhex(w['hex']), bytes.fromhex(w['orig']) if 'orig' in w else None, w['note'])
             for w in manifest['writes']]
    data, _ = build(rom.d, [('obj-tiles', 0, lists)], 2 if any(o >= 0x180000 for o, *_ in lists) else 0)
    return Rom(data)


def check(rom, doc=None, base=Path('.'), at=None):
    """원본 덩어리를 PNG 로 내보내 다시 넣어도 쓰기 0개이고, 다시 압축한 것이 같은 타일로 풀리며 원래 자리에 드는지.
    doc 를 주면 빌드한 롬에서 바꾼 덩어리가 입력대로이고 나머지가 그대로인지도 본다."""
    with tempfile.TemporaryDirectory(prefix='dq5objtiles-') as folder:
        original = dump(rom, folder)
        if patch(rom, original, Path(folder))['writes']:
            raise ValueError('원본 그림을 그대로 넣었는데 쓰기가 생김')
    fits = 0
    for name, b in blocks(rom).items():
        raw = encode(b['tiles'], b['split'])
        if decode(raw, b['split'])[:len(b['tiles'])] != b['tiles']:
            raise ValueError(f'{name}: 다시 압축한 자료가 원본 타일로 풀리지 않음')
        fits += b['data'] + len(raw) <= b['end']
    print(f'덩어리 {len(original["blocks"])}개 다시 압축 일치, 원래 자리에 들어감 {fits}개; 원본 문서 쓰기 0개')
    if doc is None:
        return
    manifest = patch(rom, doc, base, at)
    after = built(rom, manifest)
    known, tiles = plan(rom, doc, base)
    now = blocks(after)
    for name, b in known.items():
        if now[name]['tiles'][:len(b['tiles'])] != tiles.get(name, b['tiles']):
            raise ValueError(f'{name}: 빌드한 롬이 기대한 타일로 풀리지 않음')
    print(f'문서: 쓰기 {len(manifest["writes"])}개, 바꾼 덩어리 {sum(tiles[n] != known[n]["tiles"] for n in tiles)}개 확인')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('rom', type=Path)
    sub = parser.add_subparsers(dest='command', required=True)
    export = sub.add_parser('dump')
    export.add_argument('-o', '--out', type=Path, required=True)
    write = sub.add_parser('patch')
    write.add_argument('source', type=Path)
    write.add_argument('-o', '--out', type=Path, required=True)
    write.add_argument('--at', help='원래 자리보다 긴 자료를 놓을 곳(BB:AAAA)')
    verify = sub.add_parser('check')
    verify.add_argument('source', type=Path, nargs='?')
    verify.add_argument('--at')
    args = parser.parse_args()
    try:
        rom = Rom(args.rom.read_bytes())
        if args.command == 'dump':
            doc = dump(rom, args.out)
            print(f'덩어리 {len(doc["blocks"])}개 → {args.out}')
            return 0
        doc = json.loads(args.source.read_text(encoding='utf-8')) if getattr(args, 'source', None) else None
        base = args.source.parent if getattr(args, 'source', None) else Path('.')
        at = address(args.at) if args.at else None
        if args.command == 'check':
            check(rom, doc, base, at)
            return 0
        manifest = patch(rom, doc, base, at)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        print(f'patch → {args.out} (쓰기 {len(manifest["writes"])}개)')
        return 0
    except (ValueError, OSError, IndexError, PatchError) as error:
        print(f'오류: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
