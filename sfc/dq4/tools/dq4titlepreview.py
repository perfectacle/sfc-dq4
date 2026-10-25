"""Build a standalone SFC title viewer, not a patch for the DQ5 engine."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from kr_patch.sfc import header
from kr_patch.sfc.mapper import LoROM


def build(source, output, asar):
    source, output = Path(source), Path(output)
    blobs = {name: (source / name).read_bytes() for name in ('title.chr', 'title.map', 'title.pal')}
    tiles = blobs['title.chr']
    if not tiles or len(tiles) % 32 or len(tiles) > 0x8000:
        raise ValueError('CHR must contain 1..1024 complete 4bpp tiles')
    if len(blobs['title.map']) != 2048 or len(blobs['title.pal']) != 256:
        raise ValueError('expected a 32x32 tilemap and eight 16-color palettes')
    for i in range(0, 2048, 2):
        cell = int.from_bytes(blobs['title.map'][i:i + 2], 'little')
        if (cell & 0x3FF) >= len(tiles) // 32:
            raise ValueError('tilemap references a missing tile')
    palette = blobs['title.pal']
    if any(int.from_bytes(palette[i:i + 2], 'little') > 0x7FFF for i in range(0, 256, 2)):
        raise ValueError('palette must contain BGR555 colors')
    if any(palette[i:i + 2] != palette[:2] for i in range(0, 256, 32)):
        raise ValueError('all palettes must share backdrop color zero')
    source_files = [source / name for name in (*blobs, 'title.png', 'title-preview.png', 'manifest.json')]
    for destination in (output, output.with_suffix('.json')):
        for asset in source_files:
            if destination.resolve() == asset.resolve() or (destination.exists() and asset.exists() and destination.samefile(asset)):
                raise ValueError('output would overwrite a source asset')
    executable = shutil.which(asar)
    if executable is None:
        raise ValueError('Asar executable not found; set ASAR or pass --asar')
    version = subprocess.check_output([executable, '--version'], text=True).splitlines()[0]
    assembly = Path(__file__).with_suffix('.asm').read_text()
    with tempfile.TemporaryDirectory(prefix='dq4-title-preview-') as directory:
        temp = Path(directory)
        for name, data in blobs.items():
            (temp / name).write_bytes(data)
        (temp / 'preview.asm').write_text(f'!chr_size = {len(tiles)}\n' + assembly)
        romfile = temp / 'preview.sfc'
        romfile.write_bytes(bytes(0x10000))
        subprocess.run([executable, '--no-title-check', str(temp / 'preview.asm'), str(romfile)], check=True, capture_output=True, text=True)
        rom, checksum = header.fix(romfile.read_bytes(), LoROM())
    if len(rom) != 0x10000 or header.title(rom, LoROM()) != 'DQ4 KO TITLE PREVIEW':
        raise ValueError('unexpected preview ROM header')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(rom)
    report = {'schema_version': 1, 'kind': 'standalone_title_preview', 'dq5_engine_inserted': False,
              'rom_sha256': hashlib.sha256(rom).hexdigest(), 'rom_bytes': len(rom),
              'checksum': f'{checksum:04X}', 'assembler': version,
              'assets': {name: {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()} for name, data in blobs.items()},
              'display': {'width': 256, 'height': 224, 'bg_mode': 1, 'chr_vram_word': 0,
                          'tilemap_vram_word': 0x4000, 'palette_count': 8},
              'emulator_verified': False}
    output.with_suffix('.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--asar', default=os.environ.get('ASAR', 'asar'))
    args = parser.parse_args()
    try:
        report = build(args.input, args.out, args.asar)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'dq4titlepreview: {error}\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
