"""Encode independent title layers and continuous dragon wing phases."""

import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from dq4titleanimation import ART, logo_mask
from dq4titleassets import DEFAULT_SOURCE, APPROVED_SOURCE_SHA256, native_title

PHASES = 128


def affine_part(part, pivot, target, scale, angle=0, squash=1):
    c, s = math.cos(angle), math.sin(angle)
    matrix = np.array([[c, -s], [s, c]]) @ np.diag([scale, scale * squash])
    inverse = np.linalg.inv(matrix)
    offset = np.array(pivot) - inverse @ np.array(target)
    coeff = (*inverse[0], offset[0], *inverse[1], offset[1])
    return part.transform((160, 96), Image.Transform.AFFINE, coeff, Image.Resampling.BICUBIC)


def dragon_frames():
    source = Image.open(ART / 'dragon-rig.png').convert('RGBA')
    body = source.crop((0, 280, 970, 650))
    near = source.crop((970, 140, 1520, 575))
    far = source.crop((1525, 235, 2079, 575))
    fixed = affine_part(body, (630, 160), (88, 67), .15)
    frames = []
    for phase in range(PHASES):
        theta = phase * math.tau / PHASES
        # Foreshortening stays nonzero so the inverse transform is well-defined.
        squash = .58 + .42 * math.cos(theta)
        angle = -.12 + .48 * math.sin(theta)
        canvas = Image.new('RGBA', (160, 96))
        canvas.alpha_composite(affine_part(far, (485, 200), (100, 57), .13, angle + .15, squash))
        canvas.alpha_composite(affine_part(near, (505, 295), (98, 57), .15, angle, squash))
        canvas.alpha_composite(fixed)
        frames.append(canvas)
    return frames


def quantize_dragon(frames):
    samples = np.concatenate([np.array(frame)[np.array(frame)[:, :, 3] >= 128, :3] for frame in frames])
    strip = Image.fromarray(samples.reshape(1, -1, 3))
    palette_image = strip.quantize(colors=15, method=Image.Quantize.MEDIANCUT)
    colors = np.array(palette_image.getpalette()[:45], dtype=np.uint16).reshape(15, 3)
    colors = ((colors >> 3) * 255 // 31).astype(np.uint8)
    palette = np.vstack([np.zeros((1, 3), dtype=np.uint8), colors])
    output = []
    for frame in frames:
        data = np.array(frame)
        distance = ((data[:, :, None, :3].astype(np.int32) - colors.astype(np.int32)) ** 2).sum(axis=3)
        pixels = (distance.argmin(axis=2) + 1).astype(np.uint8)
        pixels[data[:, :, 3] < 128] = 0
        indexed = Image.fromarray(pixels).convert('P')
        indexed.putpalette(palette.flatten().tolist() + [0] * (768 - 48))
        indexed.info['transparency'] = 0
        output.append(indexed)
    return output, palette


def obj_chr(image):
    pixels = np.array(image)
    tiles = np.zeros((256, 8, 8), dtype=np.uint8)
    for sprite in range(15):
        base = sprite % 4 * 4 + sprite // 4 * 64
        x, y = sprite % 5 * 32, sprite // 5 * 32
        for ty in range(4):
            for tx in range(4):
                tiles[base + ty * 16 + tx] = pixels[y + ty * 8:y + ty * 8 + 8, x + tx * 8:x + tx * 8 + 8]
    output = np.zeros((256, 32), dtype=np.uint8)
    for bit in range(4):
        output[:, bit // 2 * 16 + np.arange(8) * 2 + bit % 2] = np.packbits((tiles >> bit) & 1, axis=2)[:, :, 0]
    return output.tobytes()


def delta_runs(before, after, gap=2):
    old = np.frombuffer(before, dtype=np.uint8).reshape(256, 32)
    new = np.frombuffer(after, dtype=np.uint8).reshape(256, 32)
    changed = np.flatnonzero(np.any(old != new, axis=1))
    runs = []
    for tile in changed:
        if runs and tile - runs[-1][1] <= gap:
            runs[-1][1] = int(tile) + 1
        else:
            runs.append([int(tile), int(tile) + 1])
    return [(start * 32, after[start * 32:end * 32]) for start, end in runs]


def preview(out):
    out.mkdir(parents=True, exist_ok=True)
    frames, palette = quantize_dragon(dragon_frames())
    pages = [obj_chr(frame) for frame in frames]
    stats = []
    for i, page in enumerate(pages):
        runs = delta_runs(pages[(i - 2) % PHASES], page)
        stats.append({'phase': i, 'runs': len(runs), 'bytes': sum(len(data) for _, data in runs)})
    frames[0].resize((640, 384), Image.Resampling.NEAREST).save(out / 'dragon.png')
    enlarged = [frame.resize((640, 384), Image.Resampling.NEAREST) for frame in frames]
    enlarged[0].save(out / 'dragon.gif', save_all=True, append_images=enlarged[1:], duration=[20, 20, 10] * 42 + [20, 20], loop=0, disposal=2, transparency=0)
    sheet = Image.new('RGBA', (640, 384))
    for i in range(8):
        sheet.alpha_composite(frames[i * 16].convert('RGBA'), (i % 4 * 160, i // 4 * 192))
    sheet.save(out / 'poses.png')
    report = {'phases': PHASES, 'max_delta_bytes': max(s['bytes'] for s in stats), 'max_runs': max(s['runs'] for s in stats), 'frames': stats}
    (out / 'rig-profile.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'frames'}))



def encode_tiles(tiles, bpp):
    tiles = np.stack(tiles)
    output = np.zeros((len(tiles), bpp * 8), dtype=np.uint8)
    for bit in range(bpp):
        output[:, bit // 2 * 16 + np.arange(8) * 2 + bit % 2] = np.packbits((tiles >> bit) & 1, axis=2)[:, :, 0]
    return output.tobytes()


def tilemap(pixels, bpp, banks=None, priority=0):
    unique, indices, tiles = {}, [], []
    height, width = pixels.shape
    for y in range(0, height, 8):
        row = []
        for x in range(0, width, 8):
            tile = pixels[y:y + 8, x:x + 8]
            key = tile.tobytes()
            if key not in unique:
                unique[key] = len(tiles)
                tiles.append(tile)
            bank = int(banks[y // 8, x // 8]) if banks is not None else 0
            row.append(unique[key] | bank << 10 | priority << 13)
        indices.append(row)
    return encode_tiles(tiles, bpp), np.array(indices, dtype='<u2')


def foreground():
    original = native_title(DEFAULT_SOURCE)
    mask = logo_mask()
    ImageDraw.Draw(mask).polygon([(185,183),(185,174),(187,180),(190,180),(190,171),(192,169),(192,167),(194,167),(194,170),(201,171),(201,160),(203,160),(203,165),(209,165),(209,152),(211,148),(213,161),(213,159),(215,159),(215,163),(220,163),(220,144),(222,142),(224,153),(226,153),(227,155),(227,140),(229,137),(231,150),(231,153),(233,154),(233,147),(234,145),(235,154),(238,153),(239,160),(239,165),(244,166),(245,160),(246,164),(246,168),(250,168),(251,165),(252,170),(254,171),(254,174),(247,174),(240,171),(232,172),(231,166),(225,165),(224,176),(221,176),(220,171),(216,171),(216,177),(211,183),(206,185),(201,185),(200,177),(196,176),(194,180),(194,185),(191,186),(190,183)], fill=255)
    source = np.array(original)
    pixels = np.where(np.array(mask) > 0, np.where(source == 0, 16, source), 0).astype(np.uint8)
    palette = np.array(original.getpalette()[:384], dtype=np.uint8).reshape(128, 3)
    palette[16] = 0
    padded = np.zeros((256, 256), dtype=np.uint8)
    padded[:224] = pixels
    data, mapping = tilemap(padded, 8, priority=1)
    if len(data) > 0x6000:
        raise ValueError('foreground exceeds 384 8bpp tiles')
    return data, mapping.tobytes(), palette, pixels, mask


def background(palette):
    sky = Image.open(ART / 'sky.png').convert('RGB').resize((256, 224), Image.Resampling.LANCZOS).crop((64, 0, 192, 224))
    rgb = np.array(sky).astype(np.int32)
    for x in range(12):
        weight = (12 - x) / 12 / 2
        left, right = rgb[:, x].copy(), rgb[:, 127 - x].copy()
        rgb[:, x] = left * (1 - weight) + right * weight
        rgb[:, 127 - x] = right * (1 - weight) + left * weight
    pixels = np.zeros((224, 128), dtype=np.uint8)
    banks = np.zeros((28, 16), dtype=np.uint8)
    for ty in range(28):
        for tx in range(16):
            region = rgb[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8]
            choices = []
            for bank in range(8):
                colors = palette[bank * 16:(bank + 1) * 16].astype(np.int32)
                distances = ((region[:, :, None] - colors) ** 2).sum(axis=3)
                choices.append((int(distances.min(axis=2).sum()), distances.argmin(axis=2)))
            bank = min(range(8), key=lambda b: choices[b][0])
            banks[ty, tx] = bank
            pixels[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8] = choices[bank][1]
    padded = np.tile(pixels, (1, 4))
    padded = np.vstack([padded, padded[-32:]])
    bank_grid = np.tile(banks, (1, 4))
    bank_grid = np.vstack([bank_grid, bank_grid[-4:]])
    data, mapping = tilemap(padded, 4, bank_grid)
    if len(data) > 0x4800:
        raise ValueError('background exceeds 576 tiles')
    # SNES 64x32 maps store consecutive 32x32 screen blocks.
    map_data = mapping[:, :32].tobytes() + mapping[:, 32:].tobytes()
    full = pixels + np.repeat(np.repeat(banks, 8, axis=0), 8, axis=1) * 16
    return data, map_data, palette[full]


def snes_palette(palette):
    colors = palette.astype(np.uint16) >> 3
    return (colors[:, 0] | colors[:, 1] << 5 | colors[:, 2] << 10).astype('<u2').tobytes()


def oam_frame(phase):
    data = bytearray(544)
    data[512:] = bytes([0x55]) * 32
    for i in range(128):
        data[i * 4 + 1] = 224
    hover = round(2 * math.sin(phase * math.tau / PHASES))
    for i in range(15):
        data[512 + i // 4] &= ~(3 << (i % 4 * 2))
        data[i * 4:i * 4 + 4] = bytes((i % 5 * 32, i // 5 * 32 + hover + 2, i % 4 * 4 + i // 4 * 64, 0x20 | phase % 2))
    return bytes(data)


def pack_payload(pages):
    payload = bytearray()
    descriptors = bytearray(32768)
    pointers = bytearray()
    stats = []

    def store(data):
        physical = 0x1B0000 + len(payload)
        if physical % 0x8000 + len(data) > 0x8000:
            payload.extend(bytes(0x8000 - physical % 0x8000))
            physical = 0x1B0000 + len(payload)
        payload.extend(data)
        return 0x8000 | physical % 0x8000, physical // 0x8000

    for phase in range(PHASES):
        runs = delta_runs(pages[(phase - 2) % PHASES], pages[phase])
        if len(runs) > 31:
            raise ValueError('dragon delta exceeds descriptor run limit')
        total = sum(len(data) for _, data in runs)
        if total + 544 > 4096:
            raise ValueError('dragon delta and OAM exceed per-frame transfer budget')
        for i, (offset, data) in enumerate(runs):
            address, bank = store(data)
            destination = 0x6000 + phase % 2 * 0x1000 + offset // 2
            record = destination.to_bytes(2, 'little') + address.to_bytes(2, 'little') + len(data).to_bytes(2, 'little') + bytes((bank, 0))
            descriptors[phase * 256 + i * 8:phase * 256 + i * 8 + 8] = record
        address, bank = store(oam_frame(phase))
        pointers.extend(address.to_bytes(2, 'little') + bytes((bank, 0)))
        stats.append({'phase': phase, 'runs': len(runs), 'bytes': total, 'chr_sha256': __import__('hashlib').sha256(pages[phase]).hexdigest()})
    return bytes(payload), bytes(descriptors), bytes(pointers), stats


def write_pack(out):
    import hashlib
    from dq4titlepatch import protect_outputs
    if hashlib.sha256(DEFAULT_SOURCE.read_bytes()).hexdigest() != APPROVED_SOURCE_SHA256:
        raise ValueError('approved native title SHA-256 mismatch')
    fg, fgmap, palette, fg_pixels, mask = foreground()
    bg, bgmap, sky = background(palette)
    frames, obj_palette = quantize_dragon(dragon_frames())
    pages = [obj_chr(frame) for frame in frames]
    payload, descriptors, pointers, stats = pack_payload(pages)
    blobs = {'background.chr': bg, 'foreground.chr': fg, 'background.map': bgmap,
             'foreground.map': fgmap, 'background.pal': snes_palette(palette),
             'dragon.pal': snes_palette(obj_palette), 'dragon-initial.chr': pages[0] + pages[-1],
             'oam-pointers.bin': pointers, 'dragon-dma.bin': descriptors, 'layer-payload.bin': payload,
             'foreground-mask.bin': bytes(mask.tobytes())}
    outputs = [out / name for name in (*blobs, 'layers.json', 'title.png', 'animation.gif')]
    protect_outputs(outputs, [DEFAULT_SOURCE, ART / 'sky.png', ART / 'dragon-rig.png'])
    out.mkdir(parents=True, exist_ok=True)
    previews = []
    for tick in range(1024):
        phase = tick % PHASES
        frame = frames[phase]
        scrolling = np.concatenate([np.roll(sky[:192], -(tick // 4), axis=1), np.roll(sky[192:], -(tick // 8), axis=1)])
        image = Image.fromarray(np.tile(scrolling, (1, 2, 1))).convert('RGBA')
        image.alpha_composite(frame.convert('RGBA'), (0, round(2 * math.sin(phase * math.tau / PHASES)) + 2))
        layer = Image.fromarray(palette[fg_pixels]).convert('RGBA')
        layer.putalpha(mask)
        image.alpha_composite(layer)
        previews.append(image.convert('RGB'))
    previews[0].save(out / 'title.png')
    previews[0].save(out / 'animation.gif', save_all=True, append_images=previews[1:], duration=[20,20,10]*341+[20], loop=0)
    for name, data in blobs.items():
        (out / name).write_bytes(data)
    report = {'schema_version': 1, 'kind': 'dq4_title_layers', 'frame_count': PHASES,
              'mode': 3, 'foreground_bpp': 8, 'background_bpp': 4,
              'approved_source_sha256': APPROVED_SOURCE_SHA256,
              'background_period': 128, 'foreground_tiles': len(fg)//64,
              'background_tiles': len(bg)//32, 'max_delta_bytes': max(s['bytes'] for s in stats),
              'max_runs': max(s['runs'] for s in stats), 'frames': stats,
              'files': {name: {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()} for name, data in blobs.items()}}
    (out / 'layers.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('frames','files')}))


def decode_tiles(data, bpp):
    raw = np.frombuffer(data, dtype=np.uint8).reshape(-1, bpp * 8)
    pixels = np.zeros((len(raw), 8, 8), dtype=np.uint8)
    for bit in range(bpp):
        plane = raw[:, bit // 2 * 16 + np.arange(8) * 2 + bit % 2]
        pixels |= np.unpackbits(plane[:, :, None], axis=2) << bit
    return pixels


def read_pack(source):
    import hashlib
    report = json.loads((source / 'layers.json').read_text())
    if report.get('kind') != 'dq4_title_layers' or report.get('frame_count') != PHASES or report.get('mode') != 3:
        raise ValueError('unexpected layered title manifest')
    if hashlib.sha256(DEFAULT_SOURCE.read_bytes()).hexdigest() != APPROVED_SOURCE_SHA256 or report.get('approved_source_sha256') != APPROVED_SOURCE_SHA256:
        raise ValueError('approved native title SHA-256 mismatch')
    sizes = {'background.map': 4096, 'foreground.map': 2048, 'background.pal': 256,
             'dragon.pal': 32, 'dragon-initial.chr': 16384, 'oam-pointers.bin': 512,
             'dragon-dma.bin': 32768, 'foreground-mask.bin': 57344}
    names = set(sizes) | {'background.chr', 'foreground.chr', 'layer-payload.bin'}
    if set(report.get('files', {})) != names:
        raise ValueError('layered title file set mismatch')
    blobs = {}
    for name in sorted(names):
        data = (source / name).read_bytes()
        record = report['files'][name]
        if len(data) != record['bytes'] or hashlib.sha256(data).hexdigest() != record['sha256']:
            raise ValueError(f'{name} hash or size mismatch')
        if name in sizes and len(data) != sizes[name]:
            raise ValueError(f'{name} has invalid size')
        blobs[name] = data
    for name, size, maximum in [('background.chr', 32, 0x4800), ('foreground.chr', 64, 0x6000)]:
        if not blobs[name] or len(blobs[name]) % size or len(blobs[name]) > maximum:
            raise ValueError(f'{name} violates VRAM limits')
    expected_fg, expected_map, palette, pixels, mask = foreground()
    if blobs['foreground-mask.bin'] != mask.tobytes() or blobs['foreground.chr'] != expected_fg or blobs['foreground.map'] != expected_map:
        raise ValueError('foreground differs from immutable approved pixels and mask')
    if blobs['background.pal'] != snes_palette(palette):
        raise ValueError('background palette differs from approved title palette')
    if any(value & 0x8000 for value in np.frombuffer(blobs['dragon.pal'], dtype='<u2')):
        raise ValueError('OBJ palette contains non-SNES colors')
    if blobs['dragon.pal'][:2] != b'\0\0':
        raise ValueError('OBJ transparent color must be zero')
    mapping = np.frombuffer(blobs['background.map'], dtype='<u2')
    if np.any((mapping & 1023) >= len(blobs['background.chr']) // 32) or np.any(mapping & 0xE000):
        raise ValueError('background map exceeds its tile range or priority')
    payload = blobs['layer-payload.bin']
    if not payload or 0x1B0000 + len(payload) > 0x200000:
        raise ValueError('layer payload exceeds expanded ROM')

    def extract(address, bank, length):
        if address < 0x8000 or address + length > 0x10000:
            raise ValueError('asset transfer crosses a LoROM bank')
        offset = bank * 0x8000 + address - 0x8000 - 0x1B0000
        if offset < 0 or offset + length > len(payload):
            raise ValueError('asset transfer is outside packed payload')
        return payload[offset:offset + length]

    pages = [bytearray(blobs['dragon-initial.chr'][:8192]), bytearray(blobs['dragon-initial.chr'][8192:])]
    frames = report.get('frames', [])
    if len(frames) != PHASES:
        raise ValueError('phase verification records missing')
    for turn in range(PHASES * 2):
        phase = turn % PHASES
        record = blobs['dragon-dma.bin'][phase * 256:(phase + 1) * 256]
        total, runs, ended = 0, 0, False
        for cursor in range(0, 256, 8):
            dest, address, length = np.frombuffer(record[cursor:cursor + 6], dtype='<u2').tolist()
            bank, pad = record[cursor + 6:cursor + 8]
            if not length:
                if any(record[cursor:]):
                    raise ValueError('nonzero descriptor terminator padding')
                ended = True
                break
            offset = (dest - (0x6000 + phase % 2 * 0x1000)) * 2
            if offset < 0 or offset % 32 or length % 32 or offset + length > 8192 or pad:
                raise ValueError('descriptor writes outside the hidden OBJ page')
            pages[phase % 2][offset:offset + length] = extract(address, bank, length)
            total += length
            runs += 1
        if not ended or runs > 31 or total + 544 > 4096:
            raise ValueError('per-frame DMA budget exceeded')
        if frames[phase]['phase'] != phase or frames[phase]['runs'] != runs or frames[phase]['bytes'] != total or hashlib.sha256(pages[phase % 2]).hexdigest() != frames[phase]['chr_sha256']:
            raise ValueError('delta playback differs from encoded phase')
        pointer = blobs['oam-pointers.bin'][phase * 4:phase * 4 + 4]
        if pointer[3] or extract(int.from_bytes(pointer[:2], 'little'), pointer[2], 544) != oam_frame(phase):
            raise ValueError('OAM phase or page selection mismatch')
    return blobs, report


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, default=Path('work/dq4-title-layers'))
    parser.add_argument('--rig-only', action='store_true')
    args = parser.parse_args()
    (preview if args.rig_only else write_pack)(args.out)
