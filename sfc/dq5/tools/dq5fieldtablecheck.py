"""DQ5 필드 표 쓰기와 세 세계 재압축을 MesenCE에서 확인한다.

형식은 sfc/dq5/docs/dq5-build-format.md. 블록 정의는 BG1·BG2 타일맵 8KB,
입구·도착 표는 실제 보행과 도착 WRAM, 재압축 지도는 세계마다 72KB WRAM을 비교한다.
원본 롬·배 선실 세이브스테이트는 읽기만 하고 모든 출력은 --out의 새 실행 폴더에 둔다.

  MESENCE=… python sfc/dq5/tools/dq5fieldtablecheck.py rom/dq5.sfc --state work/state/ship.mss
"""
import argparse
import concurrent.futures
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from dq5field import BLOCK_LOWER, BLOCK_UPPER, block_tiles, tile_word
from dq5fieldwrite import read_grid, split
from dq5map import Rom
import dq5mesen

HERE = Path(__file__).resolve().parent
BLOCK = 8
TILES = {'lower': [1, 257, 2, 258], 'upper': [3, 259, 4, 260]}
SCENES = {
    'baseline': {'FIELD': '341,56'},
    'blocks': {'FIELD': '341,56'},
    'entrance': {'FIELD': '399,380', 'SETTLE': '150', 'TEST': 'up:60,wait:150', 'DUMPF': '750'},
    'aux': {'FIELD': '341,56', 'SETTLE': '150', 'TEST': 'down:8,wait:200', 'DUMPF': '750'},
    'exit': {'TO': '01/00,32,92,2', 'SET': '2194|80', 'SETTLE': '150',
             'TEST': 'down:80,wait:150', 'DUMPF': '750'},
    **{f'world{w}': {'FIELD': '341,56' if w == 0 else '50,28', 'POKE': f'7E1949={w:02X}'}
       for w in range(3)},
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def command(tool, rom, *args):
    subprocess.run([sys.executable, str(HERE / tool), str(rom), *map(str, args)], check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=60)


def save_json(path, doc):
    path.write_text(json.dumps(doc, indent=2) + '\n', encoding='utf-8')


def build_cases(rom, out):
    changes = {
        'blocks': {'blocks': [{'index': BLOCK, **TILES}]},
        'entrance': {'entrances': [{'table': 'main', 'index': 0, 'group': 4}],
                     'arrivals': [{'group': 4, 'x': 27, 'y': 73, 'layer': 1, 'direction': 1}]},
        'aux': {'entrances': [{'table': 'aux', 'index': 0, 'group': 4, 'x': 341, 'y': 57}],
                'arrivals': [{'group': 4, 'x': 27, 'y': 73, 'layer': 1, 'direction': 1}]},
        'exit': {'entrances': [{'table': 'main', 'index': 10, 'x': 341, 'y': 56}]},
    }
    for name, changeset in changes.items():
        source, patch = out / f'{name}.json', out / f'{name}.patch.json'
        save_json(source, {'format': 'dq5fieldtables/1', **changeset})
        command('dq5fieldtables.py', rom, 'patch', source, '-o', patch)
        command('dq5build.py', rom, 'build', patch, '-o', out / f'{name}.sfc', '--ips', out / f'{name}.ips')
    for w in range(3):
        command('dq5fieldwrite.py', rom, 'dump', w, '-o', out / f'w{w}.bin')
    command('dq5fieldwrite.py', rom, 'patch', *(out / f'w{w}.bin' for w in range(3)),
            '--world', 0, '--world', 1, '--world', 2, '--at', '34:8000', '-o', out / 'repack.patch.json')
    command('dq5build.py', rom, 'build', out / 'repack.patch.json', '--size', 4,
            '-o', out / 'repack.sfc', '--ips', out / 'repack.ips')


def run_scene(name, original, state, out, mesence, libdir):
    dest = out / name
    dest.mkdir()
    env = os.environ.copy()
    for key in ('ADULT', 'ANYWHERE', 'BATTLE', 'FIELD', 'GROUP', 'LATESET', 'PARTY', 'POKE', 'ROMPATCH',
                'SAVE', 'SET', 'TEST', 'TO', 'WAGON', 'EVERY', 'FROM'):
        env.pop(key, None)
    env.update(LIBDIR=str(libdir), STATE=str(state), SHOT_DIR=str(dest), MAXF='1800', SETTLE='900', DUMPF='900')
    env.update(SCENES[name])
    rom = original if name == 'baseline' else out / ('repack.sfc' if name.startswith('world') else f'{name}.sfc')
    with (dest / 'mesen.log').open('w', encoding='utf-8') as log:
        dq5mesen.testrunner(str(mesence), str(rom), str(HERE / 'lua/dq5gfxdump.lua'),
                            '--Snes.DisableFrameSkipping=true', env=env, stdout=log, stderr=subprocess.STDOUT,
                            check=True, timeout=90)
    require('timeout' not in (dest / 'warp.txt').read_text(encoding='utf-8'), f'{name}: 보행 시간 초과')
    return name


def read_dump(out, name):
    frame = int(SCENES[name].get('DUMPF', '900'))
    prefix = out / name / f'f{frame:05d}'
    ram = prefix.with_suffix('.wram').read_bytes()
    vram = prefix.with_suffix('.vram').read_bytes()
    ppu = dict(line.strip().split('=', 1) for line in prefix.with_suffix('.ppu.txt').read_text().splitlines())
    require(len(ram) == 0x20000 and len(vram) == 0x10000, f'{name}: 덤프 길이 오류')
    require(ppu['ppu.forcedBlank'] == 'false', f'{name}: 화면이 아직 꺼져 있음')
    return ram, vram, ppu


def check_blocks(original, out):
    _, before, ppu0 = read_dump(out, 'baseline')
    _, after, ppu1 = read_dump(out, 'blocks')
    for layer, base in ((0, '2048'), (1, '0')):
        for key, value in (('tilemapAddress', base), ('doubleWidth', 'true'), ('doubleHeight', 'false')):
            key = f'ppu.layers[{layer}].{key}'
            require(ppu0[key] == ppu1[key] == value, f'블록 비교의 PPU 배치가 다름: {key}')
    rom = Rom(original.read_bytes())
    layers = [(0, BLOCK_LOWER, False, 'lower'), (0x1000, BLOCK_UPPER, True, 'upper')]
    old, new = {}, {}
    for base, table, upper, name in layers:
        priority = 0x2000 if upper else 0
        old[base] = [tile_word(rom, tile, upper) | priority for tile in block_tiles(rom, table, BLOCK)]
        new[base] = [tile_word(rom, tile, upper) | priority for tile in TILES[name]]

    def offset(base, x, y):
        x, y = x % 64, y % 32
        return base + (x // 32) * 0x800 + (y * 32 + x % 32) * 2

    def word(base, x, y):
        pos = offset(base, x, y)
        return int.from_bytes(before[pos:pos + 2], 'little')

    expected = bytearray(before[:0x2000])
    full, halves = 0, 0
    for y in range(32):
        for x in range(64):
            match = all(word(base, x + q % 2, y + q // 2) == old[base][q]
                        for base, _, _, _ in layers for q in range(4))
            # 스크롤 버퍼의 경계에는 오른쪽 열만 불러온 블록이 남는다.
            half = not match and all(word(base, x, y + row) == (0x2000 if upper else 0)
                                    and word(base, x + 1, y + row) == old[base][row * 2 + 1]
                                    for base, _, upper, _ in layers for row in range(2))
            if not match and not half:
                continue
            full += int(match)
            halves += int(half)
            for base, _, _, _ in layers:
                for q in range(4) if match else (1, 3):
                    pos = offset(base, x + q % 2, y + q // 2)
                    expected[pos:pos + 2] = new[base][q].to_bytes(2, 'little')
    require(full > 0, '비교할 필드 블록을 찾지 못함')
    differences = sum(a != b for a, b in zip(expected, after[:0x2000]))
    require(differences == 0, f'BG 타일맵 예상과 {differences}바이트 다름')
    return {'case': 'blocks', 'bytes': 0x2000, 'differences': differences, 'full_blocks': full,
            'right_halves': halves, 'changed_bytes': sum(a != b for a, b in zip(before, expected))}


def verify(original, out):
    results = [check_blocks(original, out)]
    for name, fragment in [('entrance', 'end map 04/00 cell 27,73 BE=80'),
                           ('aux', 'end map 04/00 cell 27,73 BE=80'),
                           ('exit', 'end map 01/00 field 341,56 BE=00')]:
        log = (out / name / 'warp.txt').read_text(encoding='utf-8')
        require(fragment in log, f'{name}: 도착 결과가 다름')
        ram, _, _ = read_dump(out, name)
        if name in ('entrance', 'aux'):
            require((ram[0xBC], ram[0xBD], ram[0x3020], ram[0x3080]) == (4, 0, 27, 73), '입구 도착 WRAM 불일치')
            require(ram[0xC3] == 1 and ram[0x31E0] == 0x11, '도착 층·방향 불일치')
        else:
            require(int.from_bytes(ram[0xB6:0xB8], 'little') == 341
                    and int.from_bytes(ram[0xB8:0xBA], 'little') == 56, '필드 출구 좌표 불일치')
        results.append({'case': name, 'passed': True})
    for w in range(3):
        ram, _, _ = read_dump(out, f'world{w}')
        low, high = split(read_grid(out / f'w{w}.bin'))
        require(ram[0x1949] == w and ram[0xBE] & 0x80 == 0, f'세계 {w}: 필드에 서지 않음')
        differences = sum(a != b for a, b in zip(low + high, ram[0x10000:] + ram[0xE000:0x10000]))
        require(differences == 0, f'세계 {w}: 지도 {differences}바이트 다름')
        results.append({'case': f'world{w}', 'bytes': len(low) + len(high), 'differences': differences})
    save_json(out / 'results.json', results)
    return results


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', default='work/fieldtablecheck', type=Path)
    args = ap.parse_args()
    if not args.mesence:
        ap.error('--mesence 또는 MESENCE가 필요함')
    try:
        original, state, mesence = args.rom.resolve(), args.state.resolve(), Path(args.mesence).resolve()
        for path in (original, state, mesence):
            require(path.is_file(), f'파일 없음: {path}')
        args.out.mkdir(parents=True, exist_ok=True)
        out = Path(tempfile.mkdtemp(prefix='run-', dir=args.out.resolve()))
        print(f'실행 출력: {out}', flush=True)
        krlua = Path(subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True,
                                   check=True, timeout=30).stdout.strip())
        libdir = out / 'lib'
        shutil.copytree(krlua, libdir)
        shutil.copyfile(HERE / 'lua/dq5warp.lua', libdir / 'boot.lua')
        build_cases(original, out)
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(lambda name: run_scene(name, original, state, out, mesence, libdir), SCENES))
        results = verify(original, out)
        print(f'{len(SCENES)}개 장면 실행, {len(results)}개 비교 통과')
        print(json.dumps(results, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.output:
            print(error.output, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
