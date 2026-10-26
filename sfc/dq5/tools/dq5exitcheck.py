"""출구·영역 이동 쓰기를 MesenCE에서 밟아 확인한다.

변경 롬 두 벌(출구 세 종류·출발층·고층 공유 목록·음수 가장자리, 옮긴 사각형)과 원본 롬에서
같은 자리를 밟아 도착 맵·칸·주인공 층을 견준다. 원본 롬·선실 상태는 읽기만 하고 출력은 --out의 새 하위 폴더에 둔다.
  MESENCE=… python sfc/dq5/tools/dq5exitcheck.py rom/dq5.sfc --state work/state/ship.mss
"""
import argparse
import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from dq5exit import arrival, exit_attrs
from dq5map import Rom

HERE = Path(__file__).resolve().parent
EDITS = {
    'a': {'exits': [{'map': '01/00', 'index': 1, 'destination_map': 9, 'exit': 1},
                    {'map': '21/02', 'index': 0, 'group': 1, 'destination_map': 3, 'exit': 0},
                    {'map': '01/01', 'index': 0, 'destination_map': 4, 'x': 16, 'y': 6, 'layer': 1}],
          'triggers': [{'map': '01/00', 'index': 6, 'source_layer': 2, 'destination_map': 4, 'x': 16, 'y': 6},
                       {'map': '50/50', 'index': 0, 'shared_maps': ['50/50', '50/51'],
                        'destination_group': 1, 'destination_map': 4, 'x': 16, 'y': 6},
                       {'map': '01/06', 'index': 0, 'rect': [255, 6, 0, 9]}]},
    'b': {'triggers': [{'map': '01/00', 'index': 6, 'rect': [32, 58, 33, 59], 'source_layer': 2,
                        'destination_map': 4, 'x': 16, 'y': 6, 'span_raw': 1}]},
}
# (이름, 롬, TO, TEST, 기대: 맵(field 면 필드로 나감), 칸·층(None 이면 보지 않음))
# 사각형이 넓으면 도착 칸이 들어선 자리에 비례하므로(2A:F650) 그런 장면은 맵과 층만 본다.
CASES = [
    ('same', 'a', '01/00,60,79,2', 'down:16', ('01/09', ('arrival', 1, 9, 1), None)),
    ('same-original', 'original', '01/00,60,79,2', 'down:16', ('01/03', ('arrival', 1, 3, 0), None)),
    ('other', 'a', '21/02,111,8,1', 'up:16', ('01/03', ('arrival', 1, 3, 0), None)),
    ('other-original', 'original', '21/02,111,8,1', 'up:16', ('0E/03', ('arrival', 0x0E, 3, 1), None)),
    ('position', 'a', '01/01,13,8,1', 'up:24', ('01/04', (16, 6), 1)),
    ('position-original', 'original', '01/01,13,8,1', 'up:24', ('01/00', (21, 28), 2)),
    ('layer', 'a', '01/00,32,59,2', 'down:16', ('01/04', None, 1)),
    ('layer-original', 'original', '01/00,32,59,2', 'down:16', ('01/00', None, 2)),
    ('high-50', 'a', '50/50,31,17,1', 'down:16', ('01/04', None, 1)),
    ('high-51', 'a', '50/51,31,17,1', 'down:16', ('01/04', None, 1)),
    ('high-original', 'original', '50/50,31,17,1', 'down:16', ('05/01', None, 1)),
    ('high-51-original', 'original', '50/51,31,17,1', 'down:16', ('05/01', None, 1)),
    ('edge-kept', 'a', '01/06,0,8,1', 'left:24', ('01/04', None, 1)),
    ('edge-kept-original', 'original', '01/06,0,8,1', 'left:24', ('01/04', None, 1)),
    ('edge-cut', 'a', '01/06,0,10,1', 'left:24', ('field', None, None)),
    ('edge-original', 'original', '01/06,0,10,1', 'left:24', ('01/04', (16, 8), 1)),
    ('rect', 'b', '01/00,32,57,2', 'down:16', ('01/04', None, 1)),
    ('rect-original', 'original', '01/00,32,57,2', 'down:16', ('01/00', (32, 58), 2)),
    ('rect-old', 'b', '01/00,32,61,1', 'up:16', ('01/00', None, 1)),
    ('rect-old-original', 'original', '01/00,32,61,1', 'up:16', ('01/01', None, None)),
]


def require(ok, message):
    if not ok:
        raise ValueError(message)


def command(tool, rom, *args):
    subprocess.run([sys.executable, str(HERE / tool), str(rom), *map(str, args)],
                   check=True, capture_output=True, text=True, timeout=60)


def run(case, roms, state, out, mesence, libdir):
    name, rom, to, test, _ = case
    dest = out / name
    dest.mkdir()
    env = {k: v for k, v in os.environ.items()
           if k not in ('ADULT', 'ANYWHERE', 'BATTLE', 'FIELD', 'GROUP', 'LATESET', 'PARTY', 'POKE',
                        'ROMPATCH', 'SAVE', 'SET', 'WAGON')}
    env.update(LIBDIR=str(libdir), STATE=str(state), SHOT_DIR=str(dest), MAXF='1500', SETTLE='120',
               TO=to, TEST=f'{test},wait:300')
    with (dest / 'mesen.log').open('w', encoding='utf-8') as log:
        subprocess.run([str(mesence), '--testrunner', str(roms[rom]), str(HERE / 'lua/dq5exitcheck.lua'),
                        '--Snes.DisableFrameSkipping=true'], env=env, stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=120)
    text = (dest / 'warp.txt').read_text(encoding='utf-8')
    match = re.search(r'final map (\w\w/\w\w) cell (\d+),(\d+) layer (\w\w) BE=(\w\w)', text)
    require(match is not None and 'timeout' not in text, f'{name}: 보행 결과가 없음')
    return match[1] if int(match[5], 16) & 0x80 else 'field', (int(match[2]), int(match[3])), int(match[4], 16)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/exitcheck')
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
        roms = {'original': original}
        for key, edits in EDITS.items():
            source, manifest = out / f'{key}.json', out / f'{key}.patch.json'
            source.write_text(json.dumps({'format': 'dq5connections/1', **edits}, ensure_ascii=False, indent=2) + '\n',
                              encoding='utf-8')
            command('dq5exitwrite.py', original, 'patch', source, '-o', manifest)
            command('dq5exitwrite.py', original, 'check', source)
            roms[key] = out / f'{key}.sfc'
            command('dq5build.py', original, 'build', manifest, '-o', roms[key], '--ips', out / f'{key}.ips')
        krlua = Path(subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True,
                                    check=True, timeout=30).stdout.strip())
        libdir = out / 'lib'
        shutil.copytree(krlua, libdir)
        shutil.copyfile(HERE / 'lua/dq5warp.lua', libdir / 'boot.lua')
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            seen = list(pool.map(lambda case: run(case, roms, state, out, mesence, libdir), CASES))
        results = []
        for (name, rom, to, test, (want_map, want_cell, want_layer)), (got_map, cell, layer) in zip(CASES, seen):
            if want_cell and want_cell[0] == 'arrival':
                _, bc, bd, n = want_cell
                built = Rom(roms[rom].read_bytes())
                want_cell = arrival(built, bc, bd, n, exit_attrs(built))
            ok = (got_map == want_map and (want_cell is None or cell == tuple(want_cell))
                  and (want_layer is None or layer == want_layer))
            results.append({'case': name, 'rom': rom, 'to': to, 'test': test, 'map': got_map, 'cell': list(cell),
                            'layer': layer, 'expected_map': want_map,
                            'expected_cell': list(want_cell) if want_cell else None,
                            'expected_layer': want_layer, 'passed': ok})
        (out / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        failed = [r['case'] for r in results if not r['passed']]
        for r in results:
            print(f'{r["case"]}: {r["map"]} {tuple(r["cell"])} 층 {r["layer"]:02X}{"" if r["passed"] else " 불일치"}')
        require(not failed, f'불일치: {", ".join(failed)}')
        print(f'{len(results)}개 장면 통과')
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
