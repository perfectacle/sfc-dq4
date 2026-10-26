"""DQ5 필드 인물 스프라이트 세트 쓰기. 형식은 sfc/dq5/docs/dq5-graphics-format.md 의 「필드 인물 스프라이트」.

색 번호 PNG(팔레트 모드, 픽셀 값 = OBJ 팔레트의 색 번호 0~15, 0 투명)를 받아 타일을 나누고, 같은 타일과 좌우 반전
타일을 합쳐 칸 48개를 만들고, 1F:D2DB 의 런 길이 압축으로 묶어 세트 레코드(1F:D63D)와 함께 쓴다.

  6타일 세트(00~7F): 32x96. 열 걸음 프레임 0·1, 행 아래·왼쪽·오른쪽·위(16x24 씩).
  8타일 세트(80~A2): 48x64. 열 머리·몸 프레임 0·몸 프레임 1, 행 아래·왼쪽·오른쪽·위(16x16 씩).
    화면에서는 몸을 머리보다 8픽셀 아래에 두고 머리를 위에 그린다(00:F7AA). 몸짓에서는 머리와 몸 방향이 갈린다.

  python sfc/dq5/tools/dq5spritewrite.py rom/dq5.sfc dump 84 -o work/sprite/84.png
  python sfc/dq5/tools/dq5spritewrite.py rom/dq5.sfc patch work/sprite.json -o work/sprite.dq5patch.json [--at 3A:8000]
  python sfc/dq5/tools/dq5spritewrite.py rom/dq5.sfc check [work/sprite.json]

문서(dq5sprite/1):
  {"format": "dq5sprite/1",
   "sets": [{"set": "84", "image": "84.png", "palette": 0}],          # 기존 세트 그림 바꾸기(palette 는 생략 가능)
   "new_sets": [{"set": "70", "image": "70.png", "palette": 1}],      # 빈 세트 번호 70~7F(6타일)에 새 레코드
   "gfx": [{"gfx": "2B", "set": "70"}]}                               # 그림 번호 → 세트(25:86D0)
image 는 문서 파일 기준 상대 경로. 세트의 타일 수는 그 세트를 쓰는 그림 번호들이 원래 가리키던 세트의 타일 수를
넘을 수 없다(인물마다 VRAM 을 타일 수만큼 잡는다, 1F:CF1E). 압축 자료가 원래 자리보다 크면 --at 부터 차례로 놓는다.
"""
import argparse
import json
import re
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dq5sprite as S  # noqa: E402
from dq5build import PatchError  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402

FORMAT = 'dq5sprite/1'
RECORD_SIZE = 52
FREE_SETS = range(0x70, 0x80)          # 1F:D63D 포인터가 FFFF 인 번호. 6타일 배치만 된다(set & 80 으로 배치를 고름)
RECORD_AREA = (0x1FFE30, 0x200000)     # 뱅크 1F 끝 빈 자리(dq5build.py free). 레코드 포인터는 뱅크 1F 의 16비트
SIMPLE_SIZE, OVERLAP_SIZE = (32, 96), (48, 64)


def cpu(addr):
    return f'{addr >> 16:02X}:{addr & 0xFFFF:04X}'


def hexbyte(value, name):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9A-Fa-f]{2}', value):
        raise ValueError(f'{name}: 두 자리 16진 문자열이어야 함')
    return int(value, 16)


def address(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9A-Fa-f]{2}:[0-9A-Fa-f]{4}', value):
        raise ValueError('주소는 BB:AAAA 문자열이어야 함')
    bank, low = (int(p, 16) for p in value.split(':'))
    # 레코드 +2 의 아래 6비트가 뱅크다.
    if bank > 0x3F or low < 0x8000:
        raise ValueError('타일 자료 주소는 뱅크 00~3F 의 8000~FFFF 여야 함')
    return bank << 16 | low


def tile_bytes(rows):
    out = bytearray(32)
    for y, row in enumerate(rows):
        for x, c in enumerate(row):
            for bit in range(4):
                out[(bit // 2) * 16 + y * 2 + bit % 2] |= ((c >> bit) & 1) << (7 - x)
    return bytes(out)


def crop(grid, x0, y0):
    return [row[x0:x0 + 8] for row in grid[y0:y0 + 8]]


def image_grid(path, layout):
    with Image.open(path) as opened:
        image = opened.copy()
    want = SIMPLE_SIZE if layout == 'simple' else OVERLAP_SIZE
    if image.mode != 'P' or image.size != want:
        raise ValueError(f'{path}: {want[0]}x{want[1]} 팔레트 모드 PNG 여야 함(지금 {image.mode} {image.size[0]}x{image.size[1]})')
    data = list(image.tobytes())
    if max(data) > 15:
        raise ValueError(f'{path}: 색 번호는 0~15 여야 함')
    return [data[y * want[0]:(y + 1) * want[0]] for y in range(want[1])]


def cell_tiles(grid, layout):
    """색 번호 격자 → 칸 48개의 타일(칸 번호 순서)."""
    cells = [None] * 48
    for row, d in enumerate(S.DIRS):
        if layout == 'simple':
            for f in (0, 1):
                for i, (x, y) in enumerate(S.SIMPLE_POS):
                    cells[S.SIMPLE_BASE[d] + f * 6 + i] = tile_bytes(crop(grid, f * 16 + x, row * 24 + y))
        else:
            for i, (x, y) in enumerate(S.QUAD_POS):
                cells[S.HEAD_BASE[d] + i] = tile_bytes(crop(grid, x, row * 16 + y))
                for f in (0, 1):
                    cells[S.BODY_BASE[d] + f * 4 + i] = tile_bytes(crop(grid, 16 + f * 16 + x, row * 16 + y))
    return cells


def deduplicate(cells):
    """같은 타일·좌우 반전 타일을 합친다. (타일 목록, 칸 48개)."""
    tiles, index, refs = [], {}, []
    for tile in cells:
        flipped = tile_bytes([row[::-1] for row in S.pixels(tile)])
        if tile in index:
            refs.append(index[tile])
        elif flipped in index:
            refs.append(index[flipped] | 0x80)
        else:
            index[tile] = len(tiles)
            refs.append(len(tiles))
            tiles.append(tile)
    return tiles, refs


def commands(data):
    """1F:D2DB 의 런 길이 명령으로 data 를 가장 짧게 나눈다. [(명령 바이트들)]."""
    n = len(data)
    cost, choice = [0] * (n + 1), [None] * n
    for i in range(n - 1, -1, -1):
        best = None
        for length in range(1, min(127, n - i) + 1):
            c = length + 1 + cost[i + length]
            if best is None or c < best[0]:
                best = (c, length, False)
        run = 1
        while run < min(128, n - i) and data[i + run] == data[i]:
            run += 1
        for length in range(2, run + 1):
            c = 2 + cost[i + length]
            if c < best[0]:
                best = (c, length, True)
        cost[i], choice[i] = best[0], best[1:]
    out, i = [], 0
    while i < n:
        length, repeated = choice[i]
        out.append(bytes([0x80 | (length - 1), data[i]]) if repeated else bytes([length - 1]) + data[i:i + length])
        i += length
    return out + [b'\x80']


def place(chunks, start):
    """명령을 start 부터 놓는다. 명령이 뱅크 끝을 넘으면 7F 를 두고 다음 뱅크 8000 에서 잇는다. [(CPU 주소, 바이트)]."""
    out, at, current = [], start, bytearray()
    piece = start
    for chunk in chunks:
        # 명령 끝은 FFFE 까지. FFFF 를 쓰면 다음 명령(또는 7F)이 다음 뱅크 0000(WRAM 거울)에 놓인다.
        if (at & 0xFFFF) + len(chunk) >= 0x10000:
            current.append(0x7F)
            out.append((piece, bytes(current)))
            at = ((at >> 16) + 1) << 16 | 0x8000
            piece, current = at, bytearray()
            if at >> 16 > 0x3F:
                raise ValueError('타일 자료가 뱅크 3F 를 넘음')
        current.extend(chunk)
        at += len(chunk)
    out.append((piece, bytes(current)))
    return out, at


def packed(tiles):
    return commands(b''.join(t[0::2] for t in tiles)) + commands(b''.join(t[1::2] for t in tiles))


def decoded(rec_cells, tiles, layout):
    """칸·타일로 디코더가 그릴 모든 모양(걸음 8, 몸짓 24, 누운 4)."""
    rec = {'cells': rec_cells, 'layout': layout, 'tile_data': tiles}
    out = {(d, f): S.frame(rec, tiles, d, f) for d in S.DIRS for f in (0, 1)}
    if layout == 'overlap':
        for hd in S.DIRS:
            for bd in S.DIRS:
                if hd != bd:
                    for f in (0, 1):
                        out[f'{hd}/{bd}', f] = S.mixed_frame(rec, hd, bd, f)
    rec['lying_tiles'] = [S.rotate_tile(t) for t in tiles]
    rec['lying_cells'] = S.lying_cells(rec)
    out.update({('lying', d): S.lying_frame(rec, d) for d in S.DIRS})
    return out


def dump_image(rom, s, path):
    """세트 s 를 색 번호 PNG 로. 팔레트는 레코드의 OBJ 팔레트(보기용, 쓰기에서는 무시)."""
    rec = S.decode_set(rom, s)
    if rec is None:
        raise ValueError(f'세트 {s:02X} 가 없음')
    width, height = SIMPLE_SIZE if rec['layout'] == 'simple' else OVERLAP_SIZE
    grid = [[0] * width for _ in range(height)]
    pix = [S.pixels(t) for t in rec['tile_data']]

    def put(cell, x0, y0):
        v = rec['cells'][cell]
        for y in range(8):
            for x in range(8):
                grid[y0 + y][x0 + x] = pix[v & 0x7F][y][7 - x if v & 0x80 else x]

    for row, d in enumerate(S.DIRS):
        if rec['layout'] == 'simple':
            for f in (0, 1):
                for i, (x, y) in enumerate(S.SIMPLE_POS):
                    put(S.SIMPLE_BASE[d] + f * 6 + i, f * 16 + x, row * 24 + y)
        else:
            for i, (x, y) in enumerate(S.QUAD_POS):
                put(S.HEAD_BASE[d] + i, x, row * 16 + y)
                for f in (0, 1):
                    put(S.BODY_BASE[d] + f * 4 + i, 16 + f * 16 + x, row * 16 + y)
    image = Image.new('P', (width, height))
    image.putpalette([c for color in S.obj_palettes(rom)[rec['palette']] for c in S.rgb(color)])
    image.putdata([c for row in grid for c in row])
    image.info['transparency'] = 0
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    image.save(path, transparency=0)
    return rec


def original_tiles_by_gfx(rom):
    """그림 번호마다 원래 세트의 타일 수."""
    return {g: S.set_record(rom, S.gfx_set(rom, g))['tiles'] for g in range(S.GFX_COUNT)
            if S.set_record(rom, S.gfx_set(rom, g)) is not None}


def plan(rom, doc, base):
    """{세트: (칸, 타일, 팔레트, 새 세트인지)}, {그림: 세트}."""
    if not isinstance(doc, dict) or doc.keys() - {'format', 'sets', 'new_sets', 'gfx'} or doc.get('format') != FORMAT:
        raise ValueError(f'문서는 format={FORMAT}, sets·new_sets·gfx 만 담은 객체여야 함')
    sets = {}
    for section, new in (('sets', False), ('new_sets', True)):
        rows = doc.get(section, [])
        if not isinstance(rows, list):
            raise ValueError(f'{section}는 배열이어야 함')
        for i, row in enumerate(rows):
            label = f'{section}[{i}]'
            if not isinstance(row, dict) or row.keys() - {'set', 'image', 'palette'} or not {'set', 'image'} <= row.keys():
                raise ValueError(f'{label}: set·image(와 palette)만 받음')
            s = hexbyte(row['set'], f'{label}.set')
            rec = S.set_record(rom, s) if s < S.SET_COUNT else None
            if new and s not in FREE_SETS:
                raise ValueError(f'{label}: 새 세트는 70~7F(6타일)만 됨')
            if new and rec is not None:
                raise ValueError(f'{label}: 세트 {s:02X}는 이미 있음')
            if not new and rec is None:
                raise ValueError(f'{label}: 세트 {s:02X}가 없음(새 세트는 new_sets)')
            if s in sets:
                raise ValueError(f'{label}: 세트 {s:02X}를 두 번 지정함')
            palette = row.get('palette', None if new else rec['palette'])
            if type(palette) is not int or not 0 <= palette <= 3:
                raise ValueError(f'{label}.palette: 0~3 정수여야 함(새 세트는 필수)')
            if not isinstance(row['image'], str):
                raise ValueError(f'{label}.image: 파일 경로 문자열이어야 함')
            layout = 'overlap' if s & 0x80 else 'simple'
            tiles, refs = deduplicate(cell_tiles(image_grid(base / row['image'], layout), layout))
            sets[s] = (refs, tiles, palette, new)
    mapping = {}
    rows = doc.get('gfx', [])
    if not isinstance(rows, list):
        raise ValueError('gfx는 배열이어야 함')
    for i, row in enumerate(rows):
        if not isinstance(row, dict) or row.keys() != {'gfx', 'set'}:
            raise ValueError(f'gfx[{i}]: gfx·set 만 받음')
        g, s = hexbyte(row['gfx'], f'gfx[{i}].gfx'), hexbyte(row['set'], f'gfx[{i}].set')
        if g >= S.GFX_COUNT or g in mapping:
            raise ValueError(f'gfx[{i}]: 그림 번호 {g:02X}는 00~A8 이고 한 번만 지정함')
        if g == 0x9A:
            raise ValueError(f'gfx[{i}]: 그림 9A 는 1F:CF32 가 2F·97 칸을 대신 읽어 바꿔도 쓰이지 않음')
        if s >= S.SET_COUNT or (S.set_record(rom, s) is None and s not in sets):
            raise ValueError(f'gfx[{i}]: 세트 {s:02X}가 없음')
        mapping[g] = s
    limit = original_tiles_by_gfx(rom)
    final = {g: mapping.get(g, S.gfx_set(rom, g)) for g in range(S.GFX_COUNT)}
    for g, s in final.items():
        count = len(sets[s][1]) if s in sets else S.set_record(rom, s)['tiles']
        if g in limit and count > limit[g]:
            raise ValueError(f'그림 {g:02X} → 세트 {s:02X} 타일 {count}개가 원래 세트의 {limit[g]}개를 넘음')
    for s, (_, tiles, _, new) in sets.items():
        if new and not any(v == s for v in final.values()):
            raise ValueError(f'새 세트 {s:02X}를 가리키는 그림 번호가 없음')
    return sets, mapping


def patch(rom, doc, base=Path('.'), at=None, records_at=RECORD_AREA[0]):
    sets, mapping = plan(rom, doc, base)
    writes, cursor, record_cursor = [], at, records_at

    def write(addr, data, note, orig=True):
        item = {'at': cpu(addr), 'hex': data.hex(' '), 'note': note}
        if orig:
            item['orig'] = bytes(rom.d[lorom(addr):lorom(addr) + len(data)]).hex(' ')
        writes.append(item)

    for s in sorted(sets):
        refs, tiles, palette, new = sets[s]
        layout = 'overlap' if s & 0x80 else 'simple'
        rec = None if new else S.decode_set(rom, s)
        if rec is not None and decoded(refs, tiles, layout) == decoded(rec['cells'], rec['tile_data'], layout) \
                and palette == rec['palette']:
            continue
        chunks = packed(tiles)
        pieces, end = place(chunks, rec['data']) if rec is not None else (None, None)
        if rec is not None and end <= rec['end']:
            data_at, in_place = rec['data'], True
        else:
            in_place = False
            if cursor is None:
                raise ValueError(f'세트 {s:02X} 압축 자료가 원래 자리보다 커서 --at 이 필요함')
            data_at = cursor
            pieces, cursor = place(chunks, cursor)
        for piece_at, data in pieces:
            # 옮긴 자료는 orig 없이 쓴다. 원래 롬 안이면 빌더가 빈 자리 지도 밖을 거부한다.
            write(piece_at, data, f'세트 {s:02X} 타일 {len(tiles)}개 자료', orig=in_place)
        record = bytes([data_at & 0xFF, data_at >> 8 & 0xFF, data_at >> 16 | palette << 6]) + bytes(refs) + bytes([len(tiles)])
        if rec is not None:
            write(rec['record'], record, f'세트 {s:02X} 레코드')
        else:
            if record_cursor + RECORD_SIZE > RECORD_AREA[1] or record_cursor >> 16 != 0x1F:
                raise ValueError('새 세트 레코드가 뱅크 1F 빈 자리를 넘음')
            write(record_cursor, record, f'새 세트 {s:02X} 레코드', orig=False)
            write(S.SET_POINTERS + s * 2, (record_cursor & 0xFFFF).to_bytes(2, 'little'), f'세트 {s:02X} 레코드 포인터')
            record_cursor += RECORD_SIZE
    for g, s in sorted(mapping.items()):
        if S.gfx_set(rom, g) != s:
            write(S.GFX_SETS + g, bytes([s]), f'그림 {g:02X} → 세트 {s:02X}')
    return {'format': 'dq5patch/1', 'name': 'sprite-sets', 'writes': writes}


def apply(rom, manifest):
    from dq5build import build, parse_at
    data, _ = build(rom.d, [('sprite-sets', 0, [
        (parse_at(w['at'])[0], bytes.fromhex(w['hex']), bytes.fromhex(w['orig']) if 'orig' in w else None, w['note'])
        for w in manifest['writes']])], 2 if any(parse_at(w['at'])[0] >= 0x180000 for w in manifest['writes']) else 0)
    return Rom(data)


def check(rom, doc=None, base=Path('.'), at=None, workdir=None, records_at=RECORD_AREA[0]):
    """원본 세트 147개를 PNG 로 내보내 다시 인코딩해도 모든 모양이 같은지, 원본 문서가 쓰기 0개인지 본다.
    doc 를 주면 빌드한 롬에서 바꾼 세트가 입력 그림대로 풀리고 나머지 세트는 그대로인지 본다."""
    import tempfile
    folder = Path(workdir or tempfile.mkdtemp(prefix='dq5sprite-'))
    rows, shapes, sizes, crossing = [], 0, [], []
    for s in range(S.SET_COUNT):
        rec = S.set_record(rom, s)
        if rec is None:
            continue
        rec = dump_image(rom, s, folder / f'{s:02X}.png')
        layout = rec['layout']
        tiles, refs = deduplicate(cell_tiles(image_grid(folder / f'{s:02X}.png', layout), layout))
        want = decoded(rec['cells'], rec['tile_data'], layout)
        if decoded(refs, tiles, layout) != want:
            raise ValueError(f'세트 {s:02X}: 다시 인코딩한 모양이 원본과 다름')
        shapes += len(want)
        sizes.append((len(tiles), rec['tiles']))
        rows.append({'set': f'{s:02X}', 'image': f'{s:02X}.png'})
        # 제자리에 다시 놓아도 원래 끝 안이고, 조각이 뱅크의 8000 아래나 FFFF 에서 끝나는 명령을 만들지 않는지.
        pieces, end = place(packed(tiles), rec['data'])
        if end > rec['end'] or any(at & 0xFFFF < 0x8000 for at, _ in pieces) or end & 0xFFFF < 0x8000:
            raise ValueError(f'세트 {s:02X}: 다시 압축한 자료가 원래 자리에 들어가지 않음')
        if len(pieces) > 1:
            crossing.append(f'{s:02X}')
    if patch(rom, {'format': FORMAT, 'sets': rows}, folder)['writes']:
        raise ValueError('원본 그림을 그대로 넣었는데 쓰기가 생김')
    print(f'세트 {len(rows)}개, 모양 {shapes}개 다시 인코딩 일치; 원본 문서 쓰기 0개; '
          f'다시 나눈 타일 수가 원본보다 많은 세트 {sum(a > b for a, b in sizes)}개, 적은 세트 {sum(a < b for a, b in sizes)}개; '
          f'다시 압축해 모두 원래 자리 안(뱅크를 넘는 세트 {" ".join(crossing) or "없음"})')
    if doc is None:
        return
    manifest = patch(rom, doc, base, at, records_at)
    built = apply(rom, manifest)
    sets, mapping = plan(rom, doc, base)
    for s in range(S.SET_COUNT):
        after = S.decode_set(built, s)
        if s in sets:
            refs, tiles, palette, _ = sets[s]
            if after is None or after['palette'] != palette or \
                    decoded(after['cells'], after['tile_data'], after['layout']) != decoded(refs, tiles, after['layout']):
                raise ValueError(f'세트 {s:02X}: 빌드한 롬이 입력 그림대로 풀리지 않음')
        else:
            before = S.decode_set(rom, s)
            if (before is None) != (after is None) or before and (
                    before['tile_data'] != after['tile_data'] or before['cells'] != after['cells']
                    or before['palette'] != after['palette']):
                raise ValueError(f'세트 {s:02X}: 바꾸지 않은 세트가 달라짐')
    for g in range(S.GFX_COUNT):
        if S.gfx_set(built, g) != mapping.get(g, S.gfx_set(rom, g)):
            raise ValueError(f'그림 {g:02X}: 세트 연결이 다름')
    if S.obj_palettes(built) != S.obj_palettes(rom):
        raise ValueError('OBJ 팔레트가 달라짐')
    print(f'문서: 쓰기 {len(manifest["writes"])}개, 바꾼 세트 {len(sets)}개·그림 연결 {len(mapping)}개를 빌드한 롬에서 확인')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('rom', type=Path)
    sub = parser.add_subparsers(dest='command', required=True)
    export = sub.add_parser('dump')
    export.add_argument('set')
    export.add_argument('-o', '--out', type=Path, required=True)
    write = sub.add_parser('patch')
    write.add_argument('source', type=Path)
    write.add_argument('-o', '--out', type=Path, required=True)
    write.add_argument('--at', help='원래 자리에 들어가지 않는 압축 자료를 놓을 곳(BB:AAAA, 뱅크 00~3F)')
    write.add_argument('--records-at', default='1F:FE30', help='새 세트 레코드를 놓을 곳(뱅크 1F 빈 자리)')
    verify = sub.add_parser('check')
    verify.add_argument('source', type=Path, nargs='?')
    verify.add_argument('--at')
    verify.add_argument('--records-at', default='1F:FE30')
    args = parser.parse_args()
    try:
        rom = Rom(args.rom.read_bytes())
        if args.command == 'dump':
            rec = dump_image(rom, hexbyte(args.set, 'set'), args.out)
            print(f'세트 {rec["set"]:02X} {rec["layout"]} 팔레트 {rec["palette"]} 타일 {rec["tiles"]} → {args.out}')
            return 0
        doc = json.loads(args.source.read_text(encoding='utf-8')) if getattr(args, 'source', None) else None
        base = args.source.parent if getattr(args, 'source', None) else Path('.')
        at = address(args.at) if args.at else None
        records_at = int(args.records_at.replace(':', ''), 16) if re.fullmatch(r'1[Ff]:[0-9A-Fa-f]{4}', args.records_at) else None
        if records_at is None or not RECORD_AREA[0] <= records_at < RECORD_AREA[1]:
            raise ValueError('--records-at 은 1F:FE30~1F:FFFF 안이어야 함')
        if args.command == 'check':
            check(rom, doc, base, at, records_at=records_at)
            return 0
        manifest = patch(rom, doc, base, at, records_at)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        print(f'patch → {args.out} (쓰기 {len(manifest["writes"])}개)')
        return 0
    except (ValueError, OSError, IndexError, PatchError) as error:
        print(f'오류: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
