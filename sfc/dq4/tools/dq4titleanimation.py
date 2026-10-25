"""Separate dragon poses and scrolling clouds into fixed-palette SFC title frames."""

import argparse
from collections import deque
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from dq4graphics import png_bytes
from dq4titleassets import APPROVED_SOURCE_SHA256, DEFAULT_SOURCE, native_title

ART = Path(__file__).with_name('dq4art') / 'title-animation'
FRAME_COUNT = 64


def logo_mask():
    mask = Image.new('L', (256, 224))
    draw = ImageDraw.Draw(mask)
    draw.polygon([(19, 78), (42, 83), (62, 91), (107, 91), (121, 86), (139, 90), (163, 89), (178, 93), (225, 82), (242, 78), (247, 89), (238, 110), (230, 139), (204, 133), (171, 134), (145, 131), (146, 169), (138, 175), (109, 174), (103, 167), (105, 137), (80, 134), (45, 139), (34, 131), (28, 108)], fill=255)
    draw.rectangle((87, 176, 182, 191), fill=255)
    return mask


def encode_frame(indices):
    local = (indices & 15).reshape(28, 8, 32, 8).transpose(0, 2, 1, 3).reshape(896, 8, 8)
    output = np.zeros((896, 32), dtype=np.uint8)
    for bit in range(4):
        packed = np.packbits((local >> bit) & 1, axis=2)[:, :, 0]
        output[:, (bit // 2) * 16 + np.arange(8) * 2 + bit % 2] = packed
    return output.tobytes()


def decode_frame(data, banks):
    tiles = np.frombuffer(data, dtype=np.uint8).reshape(896, 32)
    pixels = np.zeros((896, 8, 8), dtype=np.uint8)
    for bit in range(4):
        plane = tiles[:, (bit // 2) * 16 + np.arange(8) * 2 + bit % 2]
        pixels |= np.unpackbits(plane[:, :, None], axis=2) << bit
    local = pixels.reshape(28, 32, 8, 8).transpose(0, 2, 1, 3).reshape(224, 256)
    bank_grid = np.repeat(np.repeat(banks, 8, axis=0), 8, axis=1)
    return np.where(local, local + bank_grid * 16, 0).astype(np.uint8)


def title_map(banks):
    entries = np.zeros((32, 32), dtype='<u2')
    entries[:28] = np.arange(896).reshape(28, 32) | (banks.astype(np.uint16) << 10)
    return entries.tobytes()


def native_image(indices, palette):
    image = Image.fromarray(indices).convert('P')
    image.putpalette(palette)
    return image


def quantize_frames(frames, original, mask):
    original_pixels = np.array(original)
    palette = np.array(original.getpalette()[:384], dtype=np.int32).reshape(128, 3)
    codes = np.arange(32768)
    colors = np.column_stack([(codes >> shift & 31) * 255 // 31 for shift in (0, 5, 10)])
    lookup = np.zeros((8, 32768), dtype=np.uint8)
    errors = np.zeros((8, 32768), dtype=np.uint32)
    for bank in range(8):
        distances = ((colors[:, None, :] - palette[None, bank * 16:(bank + 1) * 16, :]) ** 2).sum(axis=2)
        lookup[bank] = distances.argmin(axis=1)
        errors[bank] = distances.min(axis=1)
    rgb = np.stack([np.array(frame.convert('RGB'), dtype=np.uint16) for frame in frames])
    encoded = (rgb[:, :, :, 0] >> 3) | ((rgb[:, :, :, 1] >> 3) << 5) | ((rgb[:, :, :, 2] >> 3) << 10)
    scores = np.stack([errors[bank, encoded].reshape(len(frames), 28, 8, 32, 8).sum(axis=(0, 2, 4)) for bank in range(8)])
    banks = scores.argmin(axis=0).astype(np.uint8)
    protected = np.array(mask) != 0
    for ty in range(28):
        for tx in range(32):
            region = protected[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8]
            if region.any():
                values = original_pixels[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8][region]
                used_banks = {int(v) >> 4 for v in values if v & 15}
                if len(used_banks) > 1:
                    raise ValueError('protected source tile has multiple palette banks')
                banks[ty, tx] = next(iter(used_banks), 0)
    bank_grid = np.repeat(np.repeat(banks, 8, axis=0), 8, axis=1)
    output = []
    for code in encoded:
        local = lookup[bank_grid, code]
        pixels = np.where(local, bank_grid * 16 + local, 0).astype(np.uint8)
        pixels[protected] = original_pixels[protected]
        output.append(pixels)
    return output, banks


def cloud_strip(source, width, height):
    image = source.resize((width, height), Image.Resampling.LANCZOS)
    data = np.array(image)
    data[data[:, :, 3] < 20] = 0
    blend = max(4, width // 16)
    for x in range(blend):
        left, right = data[:, x].astype(np.float32), data[:, width - 1 - x].astype(np.float32)
        shared = (left + right) / 2
        weight = x / blend
        data[:, x] = np.rint(shared * (1 - weight) + left * weight).astype(np.uint8)
        data[:, width - 1 - x] = np.rint(shared * (1 - weight) + right * weight).astype(np.uint8)
    return Image.fromarray(data)


def cloud_layer(canvas, strip, offset, y, opacity):
    strip = strip.copy()
    strip.putalpha(strip.getchannel('A').point(lambda value: round(value * opacity)))
    for x in range(-strip.width - offset % strip.width, 256, strip.width):
        canvas.alpha_composite(strip, (x, y))


def connected_poses(sheet):
    rgba = np.array(sheet)
    remaining = rgba[:, :, 3] > 32
    height, width = remaining.shape
    found = []
    while remaining.any():
        y, x = np.argwhere(remaining)[0]
        queue, points = deque([(int(x), int(y))]), []
        remaining[y, x] = False
        while queue:
            x, y = queue.popleft()
            points.append((x, y))
            for xx, yy in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if 0 <= xx < width and 0 <= yy < height and remaining[yy, xx]:
                    remaining[yy, xx] = False
                    queue.append((xx, yy))
        if len(points) > 1000:
            points = np.array(points)
            left, top = points.min(axis=0)
            right, bottom = points.max(axis=0) + 1
            crop = np.zeros((bottom - top, right - left, 4), dtype=np.uint8)
            crop[points[:, 1] - top, points[:, 0] - left] = rgba[points[:, 1], points[:, 0]]
            found.append((Image.fromarray(crop), (int(left), int(top))))
    found.sort(key=lambda item: (item[1][1] // (height // 2), item[1][0]))
    return found


def compose_frames(original, dragon_layout=None):
    with Image.open(ART / 'background.png') as opened:
        background = opened.convert('RGB').resize((256, 224), Image.Resampling.LANCZOS)
    # Preserve the original castle scale and lower scene while replacing the dragon's sky.
    a, b = np.array(background, dtype=np.float32), np.array(original.convert('RGB'), dtype=np.float32)
    weight = np.clip((np.arange(224) - 128) / 24, 0, 1)[:, None, None]
    base = Image.fromarray(np.rint(a * (1 - weight) + b * weight).astype(np.uint8)).convert('RGBA')
    layout = dragon_layout or {'file': 'dragon-poses.png', 'grid': [2, 2], 'anchors': [[440, 300], [431, 300], [440, 285], [431, 285]], 'native_width': 154}
    with Image.open(ART / layout['file']) as opened:
        sheet = opened.convert('RGBA')
    cols, rows = layout['grid']
    anchors = layout['anchors']
    if len(anchors) != cols * rows or len(anchors) not in (4, 8):
        raise ValueError('dragon layout needs four or eight anchored poses')
    cw, ch = sheet.width // cols, sheet.height // rows
    scale = layout['native_width'] / cw
    components = connected_poses(sheet) if layout.get('connected_components') else None
    if components is not None and len(components) != len(anchors):
        raise ValueError('dragon sheet component count differs from layout')
    dragons = []
    for index, anchor in enumerate(anchors):
        x, y = index % cols * cw, index // cols * ch
        if components is not None:
            crop, origin = components[index]
            anchor = (anchor[0] - origin[0], anchor[1] - origin[1])
        else:
            crop = sheet.crop((x, y, x + cw, y + ch))
        data = np.array(crop)
        data[data[:, :, 3] < 20] = 0
        dragons.append((Image.fromarray(data).resize((round(crop.width * scale), round(crop.height * scale)), Image.Resampling.LANCZOS), (round(anchor[0] * scale), round(anchor[1] * scale))))
    with Image.open(ART / 'cloud-strip.png') as opened:
        clouds = opened.convert('RGBA')
    far, near = cloud_strip(clouds, 64, 20), cloud_strip(clouds, 128, 40)
    mask = logo_mask()
    frames = []
    for index in range(FRAME_COUNT):
        frame = base.copy()
        cloud_layer(frame, far, index, 48, 0.45)
        cloud_layer(frame, near, index * 2, 191, 0.55)
        pose = (index % 16) * len(dragons) // 16
        dragon, anchor = dragons[pose]
        hover = round(2 * math.sin(index * 2 * math.pi / 32))
        target_x, target_y = layout.get('target_anchor', [84, 57])
        frame.alpha_composite(dragon, (target_x - anchor[0], target_y - anchor[1] + hover))
        frame.paste(original.convert('RGBA'), (0, 0), mask)
        frames.append(frame.convert('RGB'))
    return frames, mask


def write_pack(output, frames, banks, original, mask, smoke=False, layout=None, extra_inputs=()):
    inputs = [DEFAULT_SOURCE, *ART.glob('*.png'), *ART.glob('*.json'), *extra_inputs]
    names = ['title.chr', 'title.map', 'title.pal', 'title.png', 'title-preview.png', 'animation.json', 'animation.gif', 'logo-mask.bin'] + [f'frame{i:02d}.chr' for i in range(FRAME_COUNT)] + [f'preview{i:02d}.png' for i in (0, 4, 8, 12)]
    for name in names:
        target = output / name
        for source in inputs:
            if target.resolve() == source.resolve() or (target.exists() and target.samefile(source)):
                raise ValueError('animation output would overwrite source art')
    existing = [output / name for name in names if (output / name).exists()]
    for i, target in enumerate(existing):
        if any(target.samefile(other) for other in existing[i + 1:]):
            raise ValueError('animation output files alias one another')
    output.mkdir(parents=True, exist_ok=True)
    palette = original.getpalette()
    pal = b''.join(((palette[i * 3] >> 3) | ((palette[i * 3 + 1] >> 3) << 5) | ((palette[i * 3 + 2] >> 3) << 10)).to_bytes(2, 'little') for i in range(128))
    blobs = {'title.map': title_map(banks), 'title.pal': pal, 'logo-mask.bin': (np.array(mask) != 0).astype(np.uint8).tobytes()}
    images = []
    protected = np.array(mask) != 0
    source_pixels = np.array(original)
    for index, pixels in enumerate(frames):
        data = encode_frame(pixels)
        if not np.array_equal(decode_frame(data, banks), pixels):
            raise ValueError('frame CHR/map roundtrip mismatch')
        if not np.array_equal(pixels[protected], source_pixels[protected]):
            raise ValueError('protected logo pixels changed')
        blobs[f'frame{index:02d}.chr'] = data
        images.append(native_image(pixels, palette))
    blobs['title.chr'] = blobs['frame00.chr']
    blobs['title.png'] = png_bytes(images[0])
    blobs['title-preview.png'] = png_bytes(images[0].resize((1024, 896), Image.Resampling.NEAREST))
    for name, data in blobs.items():
        (output / name).write_bytes(data)
    for index in (0, 4, 8, 12):
        images[index].save(output / f'preview{index:02d}.png')
    images[0].save(output / 'animation.gif', save_all=True, append_images=images[1:], duration=[130, 130, 140] * 21 + [130], loop=0, optimize=False)
    report = {'schema_version': 1, 'frame_count': len(frames), 'ticks_per_frame': 8, 'smoke_test': smoke,
              'approved_source_sha256': APPROVED_SOURCE_SHA256, 'visual_status': 'animation_review_pending',
              'protected_pixels': int(protected.sum()), 'protected_pixel_differences': 0,
              'dragon_layout': layout, 'dragon_pose_count': len(layout['anchors']) if layout else 4, 'wing_cycle_frames': 16, 'wing_cycle_game_ticks': 128,
              'cloud_periods': [64, 128], 'cloud_pixels_per_frame': [1, 2],
              'source_art_sha256': {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (ART / 'background.png', ART / 'cloud-strip.png', ART / (layout['file'] if layout else 'dragon-poses.png'))},
              'frame_bytes': 0x7000, 'fixed_tile_count': 896, 'frame_palettes': 'shared',
              'files': {name: hashlib.sha256(data).hexdigest() for name, data in blobs.items()}}
    (output / 'animation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    return report


def read_pack(source):
    report = json.loads((source / 'animation.json').read_text())
    if report['schema_version'] != 1 or report['frame_count'] != FRAME_COUNT or report.get('approved_source_sha256') != APPROVED_SOURCE_SHA256:
        raise ValueError('unsupported animation frame count')
    if hashlib.sha256(DEFAULT_SOURCE.read_bytes()).hexdigest() != APPROVED_SOURCE_SHA256:
        raise ValueError('approved source hash mismatch')
    expected_mask = (np.array(logo_mask()) != 0).astype(np.uint8).tobytes()
    if (source / 'logo-mask.bin').read_bytes() != expected_mask:
        raise ValueError('animation changed the protected source mask')
    names = ['title.chr', 'title.map', 'title.pal'] + [f'frame{i:02d}.chr' for i in range(FRAME_COUNT)]
    blobs = {name: (source / name).read_bytes() for name in names}
    for name, data in blobs.items():
        if hashlib.sha256(data).hexdigest() != report['files'][name]:
            raise ValueError(f'animation hash mismatch: {name}')
    if len(blobs['title.map']) != 2048 or len(blobs['title.pal']) != 256 or any(len(blobs[name]) != 0x7000 for name in names if name.endswith('.chr')):
        raise ValueError('animation asset size mismatch')
    if blobs['title.chr'] != blobs['frame00.chr']:
        raise ValueError('initial frame mismatch')
    entries = np.frombuffer(blobs['title.map'], dtype='<u2').reshape(32, 32)
    if not np.array_equal(entries[:28] & 1023, np.arange(896).reshape(28, 32)) or np.any(entries & 0xE000) or np.any(entries[28:]):
        raise ValueError('animation requires fixed row-major tiles without flips')
    banks = ((entries[:28] >> 10) & 7).astype(np.uint8)
    original = native_title(DEFAULT_SOURCE)
    mask = np.array(logo_mask()) != 0
    source_pixels = np.array(original)
    expected_pal = b''.join(int((r >> 3) | ((g >> 3) << 5) | ((b >> 3) << 10)).to_bytes(2, 'little') for r, g, b in np.array(original.getpalette()[:384]).reshape(128, 3))
    if blobs['title.pal'] != expected_pal:
        raise ValueError('animation changed the protected source palette')
    for i in range(FRAME_COUNT):
        pixels = decode_frame(blobs[f'frame{i:02d}.chr'], banks)
        if not np.array_equal(pixels[mask], source_pixels[mask]):
            raise ValueError('animation changed protected logo pixels')
    return blobs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=Path('work/dq4-title-animation'))
    parser.add_argument('--dragon-layout', type=Path, default=ART / 'dragon-layout-8.json', help='pose grid and per-cell body anchors JSON')
    parser.add_argument('--smoke', action='store_true', help='duplicate approved still to test runtime buffers only')
    args = parser.parse_args()
    if hashlib.sha256(DEFAULT_SOURCE.read_bytes()).hexdigest() != APPROVED_SOURCE_SHA256:
        raise ValueError('approved source hash mismatch')
    original = native_title(DEFAULT_SOURCE)
    mask = logo_mask()
    layout = json.loads(args.dragon_layout.read_text()) if args.dragon_layout else None
    if args.smoke:
        pixels = np.array(original)
        banks = np.zeros((28, 32), dtype=np.uint8)
        for ty in range(28):
            for tx in range(32):
                values = pixels[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8]
                banks[ty, tx] = next(iter({int(v) >> 4 for v in values.flat if v & 15}), 0)
        frames = [pixels] * FRAME_COUNT
    else:
        rgb, mask = compose_frames(original, layout)
        frames, banks = quantize_frames(rgb, original, mask)
    report = write_pack(args.out, frames, banks, original, mask, args.smoke, layout, [args.dragon_layout])
    print(json.dumps({key: value for key, value in report.items() if key != 'files'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
