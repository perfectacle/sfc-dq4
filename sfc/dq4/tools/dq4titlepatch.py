"""승인된 한글 타이틀을 원본 DQ5의 타이틀 구간에 연결하는 로컬 ROM/IPS 빌드."""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from dq4graphics import export_image
from dq4romassets import SOURCE_SHA1, apply_ips, differences, ips_patch, set_checksum
from dq4titleassets import APPROVED_SOURCE_SHA256, DEFAULT_SOURCE, native_title

HOOK = 0x01FDFB
ORIGINAL_HOOK = bytes.fromhex('a90f8d0021')
NEW_HOOK = bytes.fromhex('5c008030ea')
MUSIC_HOOK = 0x00270C
ORIGINAL_MUSIC_HOOK = bytes.fromhex('000f10')
NEW_MUSIC_HOOK = bytes.fromhex('eaeaea')
GLEAM_RECT = (12, 67, 245, 151)


def protect_outputs(outputs, inputs):
    for output in outputs:
        for source in inputs:
            if output.resolve() == source.resolve() or (output.exists() and source.exists() and output.samefile(source)):
                raise ValueError('output would overwrite a source file')
    for i, output in enumerate(outputs):
        for other in outputs[i + 1:]:
            if output.resolve() == other.resolve() or (output.exists() and other.exists() and output.samefile(other)):
                raise ValueError('output files alias one another')


def gleam_palettes(image, palette):
    """로고 사각형 안에서만 쓰는 따뜻한 색을 골라 원본으로 돌아오는 32단계 팔레트."""
    points = {}
    for y in range(image.height):
        for x in range(image.width):
            points.setdefault(image.getpixel((x, y)), []).append((x, y))
    rgb = image.getpalette()
    x0, y0, x1, y1 = GLEAM_RECT
    selected = []
    for index, pixels in sorted(points.items()):
        if not index or index % 16 == 0:
            continue
        r, g, b = rgb[index * 3:index * 3 + 3]
        if max(r, g, b) >= 128 and r * 10 > b * 14 and g * 100 > b * 115 and all(x0 <= x < x1 and y0 <= y < y1 for x, y in pixels):
            selected.append(index)
    deltas = [round(3 * math.sin(math.pi * frame / 31) ** 2) for frame in range(32)]
    frames = []
    for delta in deltas:
        colors = bytearray(palette)
        for index in selected:
            value = int.from_bytes(palette[index * 2:index * 2 + 2], 'little')
            changed = sum(min(31, (value >> shift & 31) + delta) << shift for shift in (0, 5, 10))
            colors[index * 2:index * 2 + 2] = changed.to_bytes(2, 'little')
        frames.append(bytes(colors))
    if frames[0] != palette or frames[-1] != palette:
        raise ValueError('gleam endpoints must preserve the base palette')
    return b''.join(frames), selected, deltas


def read_assets(source):
    if hashlib.sha256(DEFAULT_SOURCE.read_bytes()).hexdigest() != APPROVED_SOURCE_SHA256:
        raise ValueError('canonical title source differs from the approved SHA-256')
    image = native_title(source / 'title.png')
    approved = native_title(DEFAULT_SOURCE)
    if image.convert('RGB').tobytes() != approved.convert('RGB').tobytes():
        raise ValueError('title pixels differ from the approved native title')
    generated, _ = export_image('title', image)
    blobs = {name: (source / name).read_bytes() for name in ('title.chr', 'title.map', 'title.pal')}
    if not blobs['title.chr'] or len(blobs['title.chr']) % 32 or len(blobs['title.chr']) > 0x7000:
        raise ValueError('CHR must fit the title VRAM reservation of 896 tiles')
    for name, data in blobs.items():
        if data != generated[name]:
            raise ValueError(f'{name} differs from the approved PNG encoding')
    gleam, selected, deltas = gleam_palettes(image, blobs['title.pal'])
    blobs['gleam.pal'] = gleam
    return blobs, selected, deltas


def verify_layout(original, rom, blobs):
    if len(rom) != 0x200000 or rom[HOOK:HOOK + 5] != NEW_HOOK or rom[MUSIC_HOOK:MUSIC_HOOK + 3] != NEW_MUSIC_HOOK:
        raise ValueError('unexpected ROM size or title hook')
    ranges = [(0x7FDC, 0x7FE0), (MUSIC_HOOK, MUSIC_HOOK + 3), (HOOK, HOOK + 5), (0x180000, 0x181000),
              (0x188000, 0x188000 + len(blobs['title.chr'])), (0x190000, 0x190900), (0x192000, 0x194000)]
    mirrored = original + original[0x100000:]
    for start, data in differences(mirrored, rom):
        if not any(lo <= start and start + len(data) <= hi for lo, hi in ranges):
            raise ValueError(f'assembler wrote outside declared regions at file offset {start:06X}')
    for name, offset in (('title.chr', 0x188000), ('title.map', 0x190000), ('title.pal', 0x190800), ('gleam.pal', 0x192000)):
        if rom[offset:offset + len(blobs[name])] != blobs[name]:
            raise ValueError(f'{name} was not embedded at its declared address')


def build(rom_path, source, output, asar):
    rom_path, source, output = Path(rom_path), Path(source), Path(output)
    assembly_path = Path(__file__).with_suffix('.asm')
    inputs = [rom_path, assembly_path, DEFAULT_SOURCE] + [source / name for name in ('title.chr', 'title.map', 'title.pal', 'title.png', 'title-preview.png', 'manifest.json')]
    outputs = [output, output.with_suffix('.ips'), output.with_suffix('.json')]
    protect_outputs(outputs, inputs)
    original = rom_path.read_bytes()
    if hashlib.sha1(original).hexdigest() != SOURCE_SHA1:
        raise ValueError('source SHA-1 mismatch; use the unmodified Japanese DQ5 ROM')
    if len(original) != 0x180000 or original[0x7FD7] != 0x0B or original[HOOK:HOOK + 5] != ORIGINAL_HOOK or original[MUSIC_HOOK:MUSIC_HOOK + 3] != ORIGINAL_MUSIC_HOOK:
        raise ValueError('unexpected source header or hook bytes')
    blobs, selected, deltas = read_assets(source)
    executable = shutil.which(asar)
    if executable is None:
        raise ValueError('Asar executable not found; set ASAR or pass --asar')
    version = subprocess.check_output([executable, '--version'], text=True).splitlines()[0]
    assembly = assembly_path.read_text()
    with tempfile.TemporaryDirectory(prefix='dq4-title-patch-') as directory:
        temp = Path(directory)
        for name, data in blobs.items():
            (temp / name).write_bytes(data)
        (temp / 'patch.asm').write_text(f'!chr_size = {len(blobs["title.chr"])}\n' + assembly)
        target = temp / 'dq4-title.sfc'
        target.write_bytes(original + original[0x100000:])
        result = subprocess.run([executable, '--no-title-check', str(temp / 'patch.asm'), str(target)], capture_output=True, text=True)
        if result.returncode:
            raise ValueError(f'Asar failed: {result.stderr.strip()} {result.stdout.strip()}')
        rom = set_checksum(target.read_bytes())
    verify_layout(original, rom, blobs)
    patch = ips_patch(original, rom)
    if apply_ips(original, patch) != rom:
        raise ValueError('IPS application differs from the built ROM')
    report = {
        'schema_version': 1, 'kind': 'dq5_integrated_title', 'source_sha1': SOURCE_SHA1,
        'rom_sha1': hashlib.sha1(rom).hexdigest(), 'rom_sha256': hashlib.sha256(rom).hexdigest(),
        'rom_bytes': len(rom), 'assembler': version, 'assembly_sha256': hashlib.sha256(assembly.encode()).hexdigest(),
        'hook': {'cpu': '03:FDFB', 'file_offset': f'{HOOK:06X}', 'original': ORIGINAL_HOOK.hex(), 'replacement': NEW_HOOK.hex(), 'destination': '30:8000'},
        'music_hook': {'cpu': '00:A70C', 'file_offset': f'{MUSIC_HOOK:06X}', 'original': ORIGINAL_MUSIC_HOOK.hex(), 'replacement': NEW_MUSIC_HOOK.hex(), 'purpose': 'start native track 10 at title and preserve playback into menu'},
        'assets': {name: {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()} for name, data in blobs.items()},
        'gleam': {'rectangle': list(GLEAM_RECT), 'indices': selected, 'deltas_5bit': deltas, 'base_palette_endpoints': True, 'index_zero_unchanged': True, 'outside_rectangle_unchanged': True},
        'verification': {'approved_native_pixels': 'passed', 'embedded_assets': 'passed', 'declared_write_ranges': 'passed', 'ips_equivalence': True, 'emulator': 'not_run'},
        'changed_ranges': [{'file_offset': f'{start:06X}', 'bytes': len(data)} for start, data in differences(original, rom)],
        'limitations': ['Warm-color gleam and fade are an SFC adaptation, not a reproduction of NDS 3D animation.', 'Runtime menu, SRAM, input and state restoration require separate emulator verification.'],
    }
    if rom_path.read_bytes() != original:
        raise ValueError('input ROM changed during build')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(rom)
    output.with_suffix('.ips').write_bytes(patch)
    output.with_suffix('.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, default=Path('rom/dq5.sfc'))
    parser.add_argument('--input', type=Path, default=Path('work/dq4-title-build'))
    parser.add_argument('--out', type=Path, default=Path('work/dq4-title-integrated/dq4-title.sfc'))
    parser.add_argument('--asar', default=os.environ.get('ASAR', 'asar'))
    args = parser.parse_args()
    try:
        report = build(args.rom, args.input, args.out, args.asar)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'dq4titlepatch: {error}\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
