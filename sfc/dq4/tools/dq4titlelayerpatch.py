"""Build the native BG/OBJ title patch from verified layered assets."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from dq4romassets import SOURCE_SHA1, apply_ips, differences, ips_patch, set_checksum
from dq4titleassets import DEFAULT_SOURCE
from dq4titlelayers import read_pack
from dq4titlepatch import HOOK, MUSIC_HOOK, NEW_HOOK, NEW_MUSIC_HOOK, ORIGINAL_HOOK, ORIGINAL_MUSIC_HOOK, protect_outputs

# 그림 자료는 42~47 에 둔다. 낮은 WRAM 을 읽는 동안 DB 를 자기 뱅크로 두는 자료(새 맵 레코드·인물 목록)는 30~3F 에만 둘 수
# 있어, 타이틀이 그 뱅크를 비워 준다. 타이틀은 자료를 DMA 와 long 으로만 읽으므로 뱅크를 가리지 않는다.
PLACEMENTS = {'background.chr': 0x210000, 'background.map': 0x215000,
              'foreground.map': 0x216000, 'background.pal': 0x216800,
              'dragon.pal': 0x216900, 'cloud.pal': 0x216920, 'oam-pointers.bin': 0x216B00,
              'cloud-oam.bin': 0x230000,
              'foreground.chr': 0x218000, 'dragon-dma.bin': 0x220000,
              'dragon-initial.chr': 0x228000, 'layer-payload.bin': 0x238000}
ROM_SIZE = 0x400000


def verify_layout(original, rom, blobs):
    if len(rom) != ROM_SIZE or rom[0x7FD7] != 0x0C or rom[HOOK:HOOK + 5] != NEW_HOOK or rom[MUSIC_HOOK:MUSIC_HOOK + 3] != NEW_MUSIC_HOOK:
        raise ValueError('unexpected ROM layout, header or hooks')
    ranges = [(0x7FD7, 0x7FD8), (0x7FDC, 0x7FE0), (HOOK, HOOK + 5),
              (MUSIC_HOOK, MUSIC_HOOK + 3), (0x180000, 0x181000)]
    ranges += [(offset, offset + len(blobs[name])) for name, offset in PLACEMENTS.items()]
    merged = []
    for lo, hi in sorted(ranges):
        if merged and lo <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    ranges = merged
    mirrored = original + original[0x100000:] + bytes(ROM_SIZE - 0x200000)
    for start, data in differences(mirrored, rom):
        if not any(lo <= start and start + len(data) <= hi for lo, hi in ranges):
            raise ValueError(f'assembler wrote outside reserved ranges: {start:06X}')
    for name, offset in PLACEMENTS.items():
        if rom[offset:offset + len(blobs[name])] != blobs[name]:
            raise ValueError(f'embedded asset mismatch: {name}')


def build(rom_path, source, output, asar):
    rom_path, source, output = map(Path, (rom_path, source, output))
    assembly_path = Path(__file__).with_name('dq4titlelayers.asm')
    outputs = [output, output.with_suffix('.ips'), output.with_suffix('.json')]
    inputs = [rom_path, assembly_path, DEFAULT_SOURCE, source / 'layers.json']
    protect_outputs(outputs, inputs)
    original = rom_path.read_bytes()
    if hashlib.sha1(original).hexdigest() != SOURCE_SHA1 or len(original) != 0x180000:
        raise ValueError('source ROM SHA-1 mismatch')
    if original[0x7FD7] != 0x0B or original[HOOK:HOOK + 5] != ORIGINAL_HOOK or original[MUSIC_HOOK:MUSIC_HOOK + 3] != ORIGINAL_MUSIC_HOOK:
        raise ValueError('source header or hook mismatch')
    blobs, assets = read_pack(source)
    if assets.get('cloud_sprite_count') != 9:
        raise ValueError('runtime requires nine 32px foreground cloud sprites')
    protect_outputs(outputs, inputs + [source / name for name in (*blobs, 'title.png', 'animation.gif')])
    executable = shutil.which(asar)
    if not executable:
        raise ValueError('Asar not found')
    assembly = assembly_path.read_text()
    with tempfile.TemporaryDirectory(prefix='dq4-title-layers-') as directory:
        temp = Path(directory)
        for name, data in blobs.items():
            (temp / name).write_bytes(data)
        defines = f'!background_chr_size = {len(blobs["background.chr"])}\n!foreground_chr_size = {len(blobs["foreground.chr"])}\n'
        (temp / 'patch.asm').write_text(defines + assembly)
        target = temp / 'title.sfc'
        expanded = bytearray(original + original[0x100000:] + bytes(ROM_SIZE - 0x200000))
        expanded[0x7FD7] = 0x0C
        target.write_bytes(expanded)
        result = subprocess.run([executable, '--no-title-check', str(temp / 'patch.asm'), str(target)], capture_output=True, text=True)
        if result.returncode:
            raise ValueError(f'Asar failed: {result.stdout} {result.stderr}')
        rom = set_checksum(target.read_bytes())
    verify_layout(original, rom, blobs)
    patch = ips_patch(original, rom)
    if apply_ips(original, patch) != rom:
        raise ValueError('IPS application mismatch')
    if rom_path.read_bytes() != original:
        raise ValueError('source ROM changed during build')
    report = {'schema_version': 1, 'kind': 'dq5_layered_title', 'source_sha1': SOURCE_SHA1,
              'rom_sha1': hashlib.sha1(rom).hexdigest(), 'rom_sha256': hashlib.sha256(rom).hexdigest(),
              'rom_bytes': len(rom), 'assembly_sha256': hashlib.sha256(assembly.encode()).hexdigest(),
              'assets': assets, 'verification': {'approved_foreground_pixels': 'passed',
              'delta_playback_two_cycles': 'passed', 'declared_write_ranges': 'passed',
              'ips_equivalence': True, 'emulator': 'not_run'},
              'changed_ranges': [{'file_offset': f'{start:06X}', 'bytes': len(data)} for start, data in differences(original, rom)]}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(rom)
    output.with_suffix('.ips').write_bytes(patch)
    output.with_suffix('.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, default=Path('rom/dq5.sfc'))
    parser.add_argument('--input', type=Path, default=Path('work/dq4-title-layers'))
    parser.add_argument('--out', type=Path, default=Path('work/dq4-title-smooth/dq4-title-smooth.sfc'))
    parser.add_argument('--asar', default=os.environ.get('ASAR', 'asar'))
    args = parser.parse_args()
    report = build(args.rom, args.input, args.out, args.asar)
    print(json.dumps({'rom_sha1': report['rom_sha1'], 'verification': report['verification']}))
