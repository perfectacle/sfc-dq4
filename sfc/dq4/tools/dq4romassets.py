"""라이안 정면을 DQ5 인물 세트에 넣는 재현 가능한 검증 패치.

형식 근거: sfc/dq5/docs/dq5-graphics-format.md, 로더 1F:D200·1F:D2DB.
원본 팔레트를 유지하며 정면 정지 그림만 교체한다. 공유 머리 때문에 두 번째
정면 프레임에도 머리가 바뀐다. 색을 바꾼 그림은 채택 전 시안이다.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'dq5' / 'tools'))
import dq5sprite as decoder
from dq5map import Rom, lorom
from dq4sprites import build_sheet

SOURCE_SHA1 = '1c47ed62c561d7965fe5dc2a03f4c37feb4a46b5'
TARGET_SET = 0x82
CHECKSUM_OFFSET = 0x7FDC


def tile_bytes(rows):
    if len(rows) != 8 or any(len(row) != 8 for row in rows):
        raise ValueError('tile must be 8x8')
    if any(not 0 <= c < 16 for row in rows for c in row):
        raise ValueError('tile color index must be 0..15')
    out = bytearray(32)
    for y, row in enumerate(rows):
        for x, c in enumerate(row):
            for bit in range(4):
                out[(bit // 2) * 16 + y * 2 + bit % 2] |= ((c >> bit) & 1) << (7 - x)
    return bytes(out)


def pack_stream(data):
    """7F 뱅크 이동 명령을 쓰지 않는 최소 길이 RLE."""
    n = len(data)
    cost, choices = [0] * (n + 1), [None] * n
    for i in range(n - 1, -1, -1):
        options = [(length + 1 + cost[i + length], length, False)
                   for length in range(1, min(127, n - i) + 1)]
        run = 1
        while run < min(128, n - i) and data[i + run] == data[i]:
            run += 1
        options.extend((2 + cost[i + length], length, True) for length in range(2, run + 1))
        cost[i], length, repeated = min(options)
        choices[i] = length, repeated
    out, i = bytearray(), 0
    while i < n:
        length, repeated = choices[i]
        if repeated:
            out.extend((0x80 | (length - 1), data[i]))
        else:
            out.append(length - 1)
            out.extend(data[i:i + length])
        i += length
    return bytes(out) + b'\x80'


def pack_tiles(tiles):
    return pack_stream(b''.join(t[0::2] for t in tiles)) + pack_stream(b''.join(t[1::2] for t in tiles))


def deduplicate(cells):
    tiles, refs = [], []
    for tile in cells:
        flipped = tile_bytes([row[::-1] for row in decoder.pixels(tile)])
        if tile in tiles:
            refs.append(tiles.index(tile))
        elif flipped in tiles:
            refs.append(tiles.index(flipped) | 0x80)
        else:
            refs.append(len(tiles))
            tiles.append(tile)
    if len(tiles) > 48:
        raise ValueError(f'{len(tiles)} tiles exceed the party allocation of 48')
    return tiles, refs


def mirrored_checksum(data):
    """12Mbit ROM 의 마지막 4Mbit를 한 번 더 더해 16Mbit 주소 공간을 채운다."""
    if len(data) == 0x200000:
        return sum(data) & 0xFFFF
    if len(data) == 0x180000:
        return (sum(data[:0x100000]) + 2 * sum(data[0x100000:])) & 0xFFFF
    raise ValueError('expected unheadered 12Mbit or 16Mbit ROM')


def set_checksum(data):
    out = bytearray(data)
    out[CHECKSUM_OFFSET:CHECKSUM_OFFSET + 4] = bytes.fromhex('ffff0000')
    checksum = mirrored_checksum(out)
    out[CHECKSUM_OFFSET:CHECKSUM_OFFSET + 4] = (checksum ^ 0xFFFF).to_bytes(2, 'little') + checksum.to_bytes(2, 'little')
    return bytes(out)


def differences(before, after):
    if len(before) > len(after):
        raise ValueError('ROM truncation is not supported')
    ranges, i = [], 0
    while i < len(before):
        if before[i] == after[i]:
            i += 1
            continue
        start = i
        while i < len(before) and before[i] != after[i] and i - start < 65535:
            i += 1
        ranges.append((start, after[start:i]))
    if len(after) > len(before):
        ranges.append((len(before), after[len(before):]))
    return ranges


def ips_patch(before, after):
    out = bytearray(b'PATCH')
    for start, data in differences(before, after):
        for chunk in range(0, len(data), 65535):
            address, values = start + chunk, data[chunk:chunk + 65535]
            if address == 0x454F46:
                raise ValueError('IPS EOF address is not representable')
            out.extend(address.to_bytes(3, 'big') + len(values).to_bytes(2, 'big') + values)
    return bytes(out) + b'EOF'


def apply_ips(before, patch):
    if not patch.startswith(b'PATCH'):
        raise ValueError('invalid IPS header')
    out, pos = bytearray(before), 5
    while patch[pos:pos + 3] != b'EOF':
        if pos + 5 > len(patch):
            raise ValueError('truncated IPS record')
        start = int.from_bytes(patch[pos:pos + 3], 'big')
        length = int.from_bytes(patch[pos + 3:pos + 5], 'big')
        pos += 5
        if not length or pos + length > len(patch) or start + length > 0x200000:
            raise ValueError('invalid or unsupported IPS record')
        if start + length > len(out):
            out.extend(bytes(start + length - len(out)))
        out[start:start + length] = patch[pos:pos + length]
        pos += length
    if pos + 3 != len(patch):
        raise ValueError('unexpected IPS trailer')
    return bytes(out)


def image_from_rows(rows, palette):
    image = Image.new('P', (len(rows[0]), len(rows)))
    image.putpalette([c for color in palette for c in decoder.rgb(color)])
    image.putdata([c for row in rows for c in row])
    image.info['transparency'] = 0
    return image


def sheet_image(rec, tiles, palette):
    out = Image.new('P', (32, 96))
    out.putpalette([c for color in palette for c in decoder.rgb(color)])
    for row, direction in enumerate(decoder.DIRS):
        for frame in range(2):
            out.paste(image_from_rows(decoder.frame(rec, tiles, direction, frame), palette), (frame * 16, row * 24))
    out.info['transparency'] = 0
    return out


def remap_front(source, palette):
    if source.size != (16, 24) or source.mode != 'P':
        raise ValueError('front must be a 16x24 indexed image')
    src_palette = source.getpalette()
    used = sorted(set(source.tobytes()) - {0})
    if any(i > 15 for i in used):
        raise ValueError('front uses more than 15 visible color slots')
    mapping = {0: 0}
    colors = []
    for index in used:
        rgb = src_palette[index * 3:index * 3 + 3]
        target = min(range(1, 16), key=lambda i: sum((a - b) ** 2 for a, b in zip(rgb, decoder.rgb(palette[i]))))
        mapping[index] = target
        colors.append({'source_index': index, 'source_rgb': rgb, 'target_index': target,
                       'target_rgb': list(decoder.rgb(palette[target]))})
    rows = [[mapping[source.getpixel((x, y))] for x in range(16)] for y in range(24)]
    return rows, colors


def build(data):
    if hashlib.sha1(data).hexdigest() != SOURCE_SHA1:
        raise ValueError('source SHA-1 mismatch; expected unmodified Japanese DQ5 ROM')
    rom = Rom(data)
    rec = decoder.set_record(rom, TARGET_SET)
    old_tiles, old_end = decoder.set_tiles(rom, rec)
    start, end = lorom(rec['data']), lorom(old_end)
    if rec['data'] >> 16 != (old_end - 1) >> 16:
        raise ValueError('source sprite spans banks')
    for s in range(decoder.SET_COUNT):
        other = decoder.set_record(rom, s)
        if other is None or s == TARGET_SET:
            continue
        _, other_end = decoder.set_tiles(rom, other)
        if max(start, lorom(other['data'])) < min(end, lorom(other_end)):
            raise ValueError(f'sprite data shared with set {s:02X}')
    palette = decoder.obj_palettes(rom)[rec['palette']]
    source = build_sheet('ragnar').crop((0, 0, 16, 24))
    mapped, colors = remap_front(source, palette)
    cells = [tile_bytes([row[::-1] if cell & 0x80 else row for row in decoder.pixels(old_tiles[cell & 0x7F])])
             for cell in rec['cells']]
    for i, (x, y) in enumerate(decoder.QUAD_POS):
        cells[decoder.HEAD_BASE['down'] + i] = tile_bytes([row[x:x + 8] for row in mapped[y:y + 8]])
        body_rows = [[0] * 16 for _ in range(8)] + mapped[16:24]
        cells[decoder.BODY_BASE['down'] + i] = tile_bytes([row[x:x + 8] for row in body_rows[y:y + 8]])
    tiles, refs = deduplicate(cells)
    packed = pack_tiles(tiles)
    expanded = len(packed) > end - start
    original_start = start
    if expanded:
        if data[0x7FD7] != 0x0B or len(packed) >= 0x8000:
            raise ValueError('unsupported expansion header or bank overflow')
        start = 0x180000
    data_cpu = 0x308000 if expanded else rec['data']
    record_offset = lorom(rec['record'])
    record = data_cpu.to_bytes(3, 'little')[:2] + bytes([(data_cpu >> 16) | (rec['palette'] << 6)]) + bytes(refs) + bytes([len(tiles)])
    # 12Mbit ROM의 마지막 4Mbit 미러를 보존한 뒤 새 자료 영역만 바꾼다.
    patched = bytearray(data + (data[0x100000:] if expanded else b''))
    patched[start:start + len(packed)] = packed
    patched[record_offset:record_offset + 52] = record
    patched = set_checksum(patched)
    decoded_rom = Rom(patched)
    new_rec = decoder.set_record(decoded_rom, TARGET_SET)
    new_tiles, packed_end = decoder.set_tiles(decoded_rom, new_rec)
    if new_tiles != tiles or lorom(packed_end) != start + len(packed):
        raise ValueError('independent decoder tile roundtrip mismatch')
    if decoder.frame(new_rec, new_tiles, 'down', 0) != mapped:
        raise ValueError('independent decoder front mismatch')
    preserved_frames = 0
    for direction in ('left', 'right', 'up'):
        for frame in range(2):
            if decoder.frame(new_rec, new_tiles, direction, frame) != decoder.frame(rec, old_tiles, direction, frame):
                raise ValueError('unmodified direction changed')
            preserved_frames += 1
    preserved_mixed = 0
    for head in ('left', 'right', 'up'):
        for body in decoder.DIRS:
            for frame in range(2):
                if body == 'down' and frame == 0:
                    continue
                before = dict(rec, tile_data=old_tiles)
                after = dict(new_rec, tile_data=new_tiles)
                if decoder.mixed_frame(before, head, body, frame) != decoder.mixed_frame(after, head, body, frame):
                    raise ValueError('unmodified mixed head/body pose changed')
                preserved_mixed += 1
    unchanged_sets = 0
    for s in range(decoder.SET_COUNT):
        before = decoder.set_record(rom, s)
        after = decoder.set_record(decoded_rom, s)
        if s == TARGET_SET or before is None:
            continue
        if before != after or decoder.set_tiles(rom, before)[0] != decoder.set_tiles(decoded_rom, after)[0]:
            raise ValueError(f'unrelated sprite set {s:02X} changed')
        unchanged_sets += 1
    if decoder.obj_palettes(rom) != decoder.obj_palettes(decoded_rom):
        raise ValueError('shared palettes changed')
    patch = ips_patch(data, patched)
    if apply_ips(data, patch) != patched:
        raise ValueError('IPS application mismatch')
    allowed = [(start, len(patched) if expanded else start + len(packed)), (record_offset, record_offset + 52), (CHECKSUM_OFFSET, CHECKSUM_OFFSET + 4)]
    changes = differences(data, patched)
    for offset, values in changes:
        if not any(lo <= offset and offset + len(values) <= hi for lo, hi in allowed):
            raise ValueError('write outside declared ranges')
    manifest = {
        'schema_version': 1, 'source_sha1': SOURCE_SHA1, 'output_sha1': hashlib.sha1(patched).hexdigest(),
        'target': {'set': TARGET_SET, 'gfx': 0x2E, 'record_cpu': f'{rec["record"]:06X}',
                   'data_cpu': f'{data_cpu:06X}', 'original_data_cpu': f'{rec["data"]:06X}', 'palette': rec['palette'], 'tiles': len(tiles),
                   'compressed_bytes': len(packed), 'allocation_bytes': end - original_start, 'expanded': expanded,
                   'source_rom_bytes': len(data), 'output_rom_bytes': len(patched)},
        'scope': '라이안 정면 정지 1장. 공유 머리는 정면 두 프레임에 적용되며 두 번째 몸과 다른 방향은 DQ5 원본입니다.',
        'visual_status': 'palette-remapped-draft',
        'source_visual_status': 'ragnar-front-still-approved',
        'palette_mapping': colors,
        'verification': {'tile_roundtrip': 'passed', 'front_pixel_match': 'passed',
                         'unchanged_direction_frames': preserved_frames, 'unchanged_sets': unchanged_sets,
                         'unchanged_mixed_head_body_poses': preserved_mixed,
                         'shared_palettes_unchanged': True, 'ips_equivalence': True,
                         'checksum': mirrored_checksum(patched), 'emulator': 'not_run'},
        'changed_ranges': [{'file_offset': f'{offset:06X}', 'length': len(values)} for offset, values in changes],
    }
    return manifest, patched, patch, tiles, packed, record, palette, source, mapped, rec, old_tiles, new_rec


def export(rom_path, outdir):
    rom_path, outdir = Path(rom_path), Path(outdir)
    files = {'sheet': '82-ragnar-front.png', 'source_front': 'ragnar-front-source.png',
             'mapped_front': 'ragnar-front-mapped.png', 'original_sheet': '82-original.png',
             'chr': '82-ragnar-front.chr', 'palette': '82-ragnar-front.pal',
             'compressed': '82-ragnar-front.rle', 'record': '82-ragnar-front.record',
             'rom': 'dq4-ragnar-front.sfc', 'ips': 'dq4-ragnar-front.ips'}
    for name in [*files.values(), 'manifest.json']:
        output = outdir / name
        if output.resolve() == rom_path.resolve() or (output.exists() and output.samefile(rom_path)):
            raise ValueError('output would overwrite input ROM')
    data = rom_path.read_bytes()
    manifest, patched, patch, tiles, packed, record, palette, source, mapped, rec, old_tiles, new_rec = build(data)
    outdir.mkdir(parents=True, exist_ok=True)
    blobs = {'rom': patched, 'ips': patch, 'chr': b''.join(tiles), 'compressed': packed, 'record': record,
             'palette': b''.join(c.to_bytes(2, 'little') for c in palette)}
    for key, blob in blobs.items():
        (outdir / files[key]).write_bytes(blob)
    for key, image in [('sheet', sheet_image(new_rec, tiles, palette)),
                       ('original_sheet', sheet_image(rec, old_tiles, palette)),
                       ('source_front', source), ('mapped_front', image_from_rows(mapped, palette))]:
        image.save(outdir / files[key], transparency=0)
    manifest['files'] = files
    manifest['file_sha256'] = {key: hashlib.sha256((outdir / name).read_bytes()).hexdigest() for key, name in files.items()}
    (outdir / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    if rom_path.read_bytes() != data:
        raise ValueError('input ROM changed during export')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rom', type=Path)
    parser.add_argument('--out', type=Path, default=Path('work/dq4-rom-assets'))
    args = parser.parse_args()
    result = export(args.rom, args.out)
    print(json.dumps({'target': result['target'], 'verification': result['verification']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
