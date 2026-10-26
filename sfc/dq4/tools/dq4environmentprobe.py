"""Boot environment assets in a standalone SFC viewer and compare MesenCE output.

This verifies SFC graphics encoding, not insertion into the DQ5 map engine.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

from PIL import Image
from kr_patch.sfc import header
from kr_patch.sfc.mapper import LoROM

import dq4titlepreview

HERE = Path(__file__).resolve().parent


def verify(source, stem, output, asar, mesence):
    source, output = Path(source).resolve(), Path(output).resolve()
    if Path(stem).name != stem or stem in ('.', '..'):
        raise ValueError('stem must be a file name without a directory')
    blobs = {suffix: (source / f'{stem}.{suffix}').read_bytes() for suffix in ('chr', 'map', 'pal')}
    if len(blobs['map']) == 32 * 28 * 2:
        blobs['map'] += bytes(32 * 4 * 2)
    with Image.open(source / f'{stem}.png') as image:
        expected = image.convert('RGB')
    if expected.size != (256, 224):
        raise ValueError('expected a 256x224 source image')
    if output.exists():
        raise ValueError('use a new output directory to preserve earlier evidence')
    with tempfile.TemporaryDirectory(prefix='dq4-environment-') as directory:
        stage = Path(directory)
        for suffix, data in blobs.items():
            (stage / f'title.{suffix}').write_bytes(data)
        built = stage / 'viewer.sfc'
        dq4titlepreview.build(stage, built, asar)
        rom = bytearray(built.read_bytes())
        rom[0x7FC0:0x7FD5] = b'DQ4 ENV PREVIEW'.ljust(21, b' ')
        rom, checksum = header.fix(bytes(rom), LoROM())
    output.mkdir(parents=True)
    rompath = output / 'environment-preview.sfc'
    rompath.write_bytes(rom)
    command = [mesence, '--testrunner', str(rompath), str(HERE / 'lua/dq4environment.lua'),
               '--Snes.Region=Ntsc', '--Snes.EnableRandomPowerOnState=false',
               '--Snes.DisableFrameSkipping=true', '--Emulation.RunAheadFrames=0']
    process = subprocess.run(command, env=dict(os.environ, ENVIRONMENT_OUT=str(output)),
                             capture_output=True, timeout=90)
    (output / 'emulator.log').write_bytes(process.stdout + process.stderr)
    process.check_returncode()
    with Image.open(output / 'screen.png') as screenshot:
        actual = screenshot.convert('RGB')
    if actual.size != expected.size:
        raise ValueError(f'expected screenshot {expected.size}, got {actual.size}')
    actual_rgb, expected_rgb = actual.tobytes(), expected.tobytes()
    differences = sum(actual_rgb[i:i + 3] != expected_rgb[i:i + 3]
                      for i in range(0, len(actual_rgb), 3))
    vram = (output / 'screen.vram').read_bytes()
    palette = (output / 'screen.cgram').read_bytes()
    checks = {'pixel_differences': differences, 'pixels_compared': 256 * 224,
              'chr_bytes_equal': vram[:len(blobs['chr'])] == blobs['chr'],
              'map_bytes_equal': vram[0x8000:0x8800] == blobs['map'],
              'palette_bytes_equal': palette[:256] == blobs['pal']}
    report = {'schema_version': 1, 'kind': 'standalone_environment_preview',
              'dq5_engine_inserted': False, 'no_memory_injection': True,
              'frames': 120, 'checksum': f'{checksum:04X}',
              'rom_sha256': hashlib.sha256(rom).hexdigest(),
              'assets': {suffix: hashlib.sha256(data).hexdigest() for suffix, data in blobs.items()},
              'screenshot': 'screen.png', 'checks': checks}
    (output / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
    if differences or not all(checks[name] for name in ('chr_bytes_equal', 'map_bytes_equal', 'palette_bytes_equal')):
        raise ValueError(f'SFC output differs from assets: {checks}')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--stem', default='environment')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--asar', default=os.environ.get('ASAR', 'asar'))
    parser.add_argument('--mesence', default=os.environ.get('MESENCE'))
    args = parser.parse_args()
    if not args.mesence:
        parser.error('set MESENCE or pass --mesence')
    try:
        report = verify(args.input, args.stem, args.out, args.asar, args.mesence)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f'dq4environmentprobe: {error}\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
