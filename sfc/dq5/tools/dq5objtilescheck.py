"""맵 OBJ 타일·탈것 타일 쓰기를 MesenCE에서 원본과 견준다.

고친 롬은 04/06 의 맵 OBJ 덩어리(obj-15, 1F:D59A 15번 항목의 17:803A, 8타일)와 양탄자(veh-80-0, 47타일)를 시험 무늬로 바꾼다. 무늬는
원래 자리보다 길어 --at 으로 옮기고, 1F:D59A 항목 주소와 01:BC93 의 LDA·LDX 를 고친다. 04/06 에 들어가는 장면과
필드에서 양탄자를 탄 장면(dq5warp.lua 의 FIELD·LATESET=1954=80)을 원본 롬과 함께 dq5gfxdump.lua 로 덤프하고,
VRAM 의 맵 OBJ 타일(7E:1997 부터)·탈것 타일(180~)이 그 롬의 타일과 같은지 본다.
  MESENCE=… python sfc/dq5/tools/dq5objtilescheck.py rom/dq5.sfc --state work/state/ship.mss
"""
import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dq5map import Rom  # noqa: E402
from dq5objtiles import FORMAT, PER_ROW, blocks, read_tiles, sheet_size  # noqa: E402

HERE = Path(__file__).resolve().parent
MAP_BLOCK, VEHICLE_BLOCK = 'obj-15', 'veh-80-0'
SCENES = [('map', {'TO': '04/06,10,10,1'}, MAP_BLOCK),
          ('vehicle', {'FIELD': '341,56', 'LATESET': '1954=80'}, VEHICLE_BLOCK)]
DUMPF = '700,800'


def pattern(path, n, seed):
    rng = random.Random(seed)
    w, h = sheet_size(n)
    grid = [[0] * w for _ in range(h)]
    for i in range(n):
        for y in range(8):
            for x in range(8):
                grid[(i // PER_ROW) * 8 + y][(i % PER_ROW) * 8 + x] = rng.randrange(16)
    image = Image.new('P', (w, h))
    image.putpalette([c for i in range(16) for c in (i * 16,) * 3])
    image.putdata([c for row in grid for c in row])
    image.save(path)


def tool(name, *args):
    subprocess.run([sys.executable, str(HERE / name), *map(str, args)], check=True, capture_output=True, text=True,
                   timeout=300)


def run(rom, name, extra, out, state, mesence, libdir):
    dest = out / name
    dest.mkdir()
    env = {k: v for k, v in os.environ.items()
           if k not in ('ADULT', 'ANYWHERE', 'BATTLE', 'FIELD', 'GROUP', 'LATESET', 'PARTY', 'POKE', 'TO',
                        'ROMPATCH', 'SAVE', 'SET', 'WAGON', 'EVERY')}
    env.update(LIBDIR=str(libdir), STATE=str(state), SHOT_DIR=str(dest), MAXF='1500', SETTLE='120',
               TEST='wait:400', DUMPF=DUMPF, **extra)
    with (dest / 'mesen.log').open('w', encoding='utf-8') as log:
        subprocess.run([str(mesence), '--testrunner', str(rom), str(HERE / 'lua/dq5gfxdump.lua'),
                        '--Snes.DisableFrameSkipping=true'], env=env, stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=180)
    return dest


def vram_matches(dest, tiles, first):
    """덤프마다 VRAM OBJ 타일 first~ 가 tiles 와 같은 수. first 가 None 이면 덤프 WRAM 의 7E:1997 을 쓴다."""
    out = []
    for tag in DUMPF.split(','):
        name = f'f{int(tag):05d}'
        vram = (dest / f'{name}.vram').read_bytes()
        wram = (dest / f'{name}.wram').read_bytes()
        base = first if first is not None else wram[0x1997] | wram[0x1998] << 8
        out.append(sum(vram[0xC000 + (base + i) * 32:][:32] == t for i, t in enumerate(tiles)))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/objtilescheck')
    ap.add_argument('--at', default='3C:8000', help='옮길 자료 자리(dq5objtiles.py --at)')
    args = ap.parse_args()
    if not args.mesence:
        ap.error('--mesence 또는 MESENCE가 필요함')
    try:
        original, state, mesence = args.rom.resolve(), args.state.resolve(), Path(args.mesence).resolve()
        for path in (original, state, mesence):
            if not path.is_file():
                raise ValueError(f'파일 없음: {path}')
        args.out.mkdir(parents=True, exist_ok=True)
        out = Path(tempfile.mkdtemp(prefix='run-', dir=args.out.resolve()))
        print(f'실행 출력: {out}', flush=True)
        base = Rom(original.read_bytes())
        known = blocks(base)
        for k, name in enumerate((MAP_BLOCK, VEHICLE_BLOCK)):
            pattern(out / f'{name}.png', len(known[name]['tiles']), 700 + k)
        doc = {'format': FORMAT, 'blocks': [{'block': n, 'image': f'{n}.png'} for n in (MAP_BLOCK, VEHICLE_BLOCK)]}
        (out / 'objtiles.json').write_text(json.dumps(doc, indent=1) + '\n', encoding='utf-8')
        tool('dq5objtiles.py', original, 'check', out / 'objtiles.json', '--at', args.at)
        tool('dq5objtiles.py', original, 'patch', out / 'objtiles.json', '-o', out / 'objtiles.dq5patch.json', '--at', args.at)
        edited = out / 'edited.sfc'
        tool('dq5build.py', original, 'build', out / 'objtiles.dq5patch.json', '--size', '2', '-o', edited,
             '--ips', out / 'edited.ips')
        manifest = json.loads((out / 'objtiles.dq5patch.json').read_text(encoding='utf-8'))
        krlua = Path(subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True,
                                    check=True, timeout=30).stdout.strip())
        libdir = out / 'lib'
        shutil.copytree(krlua, libdir)
        shutil.copyfile(HERE / 'lua/dq5warp.lua', libdir / 'boot.lua')
        roms = {'original': original, 'edited': edited}
        results = {}
        for rom_name, rom in roms.items():
            for scene, extra, block in SCENES:
                # 원본 롬은 원래 타일, 고친 롬은 입력 그림의 타일이 VRAM 에 있어야 한다.
                tiles = known[block]['tiles'] if rom_name == 'original' else \
                    read_tiles(out / f'{block}.png', len(known[block]['tiles']))
                dest = run(rom, f'{rom_name}-{scene}', extra, out, state, mesence, libdir)
                results[f'{rom_name}-{scene}'] = {'block': block, 'tiles': len(tiles),
                                                  'vram': vram_matches(dest, tiles, None if scene == 'map' else 0x180)}
        moved = sorted({w['note'].split()[0] for w in manifest['writes'] if w['note'].endswith('옮김')})
        checks = {
            'vram': all(all(v == r['tiles'] for v in r['vram']) for r in results.values()),
            'moved': moved == sorted((MAP_BLOCK, VEHICLE_BLOCK)),
        }
        (out / 'results.json').write_text(json.dumps({'results': results, 'moved': moved, 'checks': checks},
                                                     ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        for case, r in results.items():
            print(f'{case} {r["block"]}: VRAM 타일 ' + ', '.join(f'{v}/{r["tiles"]}' for v in r['vram']))
        print('옮긴 덩어리: ' + ' '.join(moved))
        for key, ok in checks.items():
            print(f'{key}: {"통과" if ok else "불일치"}')
        if not all(checks.values()):
            raise ValueError('불일치: ' + ', '.join(k for k, ok in checks.items() if not ok))
        print(f'검사 {len(checks)}개 통과')
        return 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
