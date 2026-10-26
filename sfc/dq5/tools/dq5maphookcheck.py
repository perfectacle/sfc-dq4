"""맵별 루틴 표 쓰기(dq5maphook.py)를 MesenCE 에서 확인한다.

변경 롬 다섯 벌(루틴 막기, 플래그 조건 둘, 표를 15:FF80 으로 옮겨 다시 쓰기, 제자리에 항목 하나를 빼고 다시 쓰기)과
원본 롬에서 같은 맵에 순간이동해, 15:F7D0 이 고른 루틴·셀 버퍼 값·걸은 뒤의 맵과 칸을 견준다.
원본 롬·선실 상태는 읽기만 하고 출력은 --out 의 새 하위 폴더에 둔다.
  MESENCE=… python sfc/dq5/tools/dq5maphookcheck.py rom/dq5.sfc --state work/state/ship.mss
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

from dq5maphook import FORMAT, NONE, dump, text
from dq5map import Rom

HERE = Path(__file__).resolve().parent
# 01/05 의 루틴 02:94E0 은 (51,20) +4 를 85 로 두어 출구 셀을 하나 더한다. 그 셀이 없으면 (13,47) 계단이
# 출구 1 이 되어 01/04 (13,47) 대신 출구 표 1번(01/04 (64,17) 층 1)으로 간다.
STAIRS = ('01/05,12,45', 'down:16', f'{0xC000 + (20 * 68 + 51) * 8 + 4:04X}')
# 04/00 의 매 프레임 루틴 02:A7BD 는 X 1F~21, Y < 0D 에 선 주인공을 04/0A (8,17) 로 옮긴다.
TOWER = ('04/00,32,12,2', 'wait:60', None)
# 01/04 (32,5) 도 같은 범위의 바닥이다. 원래 표에는 01/04 항목이 없다.
HALL = ('01/04,32,5', 'wait:60', None)
ADULT = '2190|40'


def entry(entries, selector):
    group, bd = selector.split('/')
    return next(e for e in entries if e['group'] == group and e['map'] == bd)


def edits(rom):
    entries = dump(rom)['entries']
    stairs, tower, ship = entry(entries, '01/05'), entry(entries, '04/00'), entry(entries, '17/00')
    flag = {'index': '00', 'mask': '40'}
    hall = {'group': '01', 'map': '04', 'flag': None, 'post_load': text(NONE), 'per_frame': tower['per_frame']}
    strip = [{k: v for k, v in e.items() if k != 'index'} for e in entries]
    return {
        'off': ('patch', None, [{'index': stairs['index'], 'post_load': text(NONE)},
                                {'index': tower['index'], 'per_frame': text(NONE)}]),
        'set': ('patch', None, [{'index': stairs['index'], 'flag': flag | {'when': 'set'}}]),
        'clear': ('patch', None, [{'index': stairs['index'], 'flag': flag | {'when': 'clear'}}]),
        'moved': ('rewrite', '15:FF80', [hall] + [strip[e['index']] for e in (stairs, ship)]),
        'short': ('rewrite', '15:F907', [e for i, e in enumerate(strip) if i != tower['index']]),
    }


# (이름, 롬, 장면, SET, 기대: 고른 루틴 (post, frame 중 None 은 보지 않음), 셀 값이 85 인가, 맵, 칸)
CASES = [
    ('stairs-original', 'original', STAIRS, None, ('02:94E0', None), True, '01/04', (13, 47)),
    ('stairs-off', 'off', STAIRS, None, ('15:F906', None), False, '01/04', (64, 17)),
    ('tower-original', 'original', TOWER, None, (None, '02:A7BD'), None, '04/0A', (8, 17)),
    ('tower-off', 'off', TOWER, None, (None, '15:F906'), None, '04/00', None),
    ('flag-set', 'set', STAIRS, None, ('15:F906', None), False, '01/04', (64, 17)),
    ('flag-set-adult', 'set', STAIRS, ADULT, ('02:94E0', None), True, '01/04', (13, 47)),
    ('flag-clear', 'clear', STAIRS, None, ('02:94E0', None), True, '01/04', (13, 47)),
    ('flag-clear-adult', 'clear', STAIRS, ADULT, ('15:F906', None), False, '01/04', (64, 17)),
    ('original-adult', 'original', STAIRS, ADULT, ('02:94E0', None), True, '01/04', (13, 47)),
    ('hall-original', 'original', HALL, None, (None, '15:F906'), None, '01/04', None),
    ('hall-moved', 'moved', HALL, None, (None, '02:A7BD'), None, '04/0A', (8, 17)),
    ('stairs-moved', 'moved', STAIRS, None, ('02:94E0', None), True, '01/04', (13, 47)),
    ('tower-moved', 'moved', TOWER, None, ('15:F906', '15:F906'), None, '04/00', None),
    ('stairs-short', 'short', STAIRS, None, ('02:94E0', None), True, '01/04', (13, 47)),
    ('tower-short', 'short', TOWER, None, ('15:F906', '15:F906'), None, '04/00', None),
]


def require(ok, message):
    if not ok:
        raise ValueError(message)


def command(*args):
    subprocess.run([sys.executable, *map(str, args)], check=True, capture_output=True, text=True, timeout=120)


def run(case, roms, state, out, mesence, libdir):
    name, rom, (to, test, cell), setting, *_ = case
    dest = out / name
    dest.mkdir()
    env = {k: v for k, v in os.environ.items()
           if k not in ('ADULT', 'ANYWHERE', 'BATTLE', 'CELL', 'FIELD', 'GROUP', 'LATESET', 'PARTY', 'POKE',
                        'ROMPATCH', 'SAVE', 'SET', 'WAGON')}
    env.update(LIBDIR=str(libdir), STATE=str(state), SHOT_DIR=str(dest), MAXF='1500', SETTLE='120',
               TO=to, TEST=f'{test},wait:300')
    if cell:
        env['CELL'] = cell
    if setting:
        env['SET'] = setting
    with (dest / 'mesen.log').open('w', encoding='utf-8') as log:
        subprocess.run([str(mesence), '--testrunner', str(roms[rom]), str(HERE / 'lua/dq5maphookcheck.lua'),
                        '--Snes.DisableFrameSkipping=true'], env=env, stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=120)
    log = (dest / 'warp.txt').read_text(encoding='utf-8')
    final = re.search(r'final map (\w\w/\w\w) cell (\d+),(\d+)', log)
    target = to.split(',')[0]
    load = re.search(rf'load {target} BE=\w\w post (\w\w:\w{{4}}) frame (\w\w:\w{{4}})(?: cell (\w\w))?', log)
    require(final is not None and load is not None and 'timeout' not in log, f'{name}: 결과가 없음')
    return {'post': load[1], 'frame': load[2], 'cell': load[3], 'map': final[1], 'at': [int(final[2]), int(final[3])]}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/maphookcheck')
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
        tool = HERE / 'dq5maphook.py'
        for key, (mode, at, entries) in edits(Rom(original.read_bytes())).items():
            source, manifest = out / f'{key}.json', out / f'{key}.patch.json'
            source.write_text(json.dumps({'format': FORMAT, 'entries': entries}, ensure_ascii=False, indent=2) + '\n',
                              encoding='utf-8')
            where = ['--at', at] if at else []
            command(tool, original, mode, source, *where, '-o', manifest)
            command(tool, original, 'check', source, *where)
            roms[key] = out / f'{key}.sfc'
            command(HERE / 'dq5build.py', original, 'build', manifest, '-o', roms[key], '--ips', out / f'{key}.ips')
        krlua = Path(subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True,
                                    check=True, timeout=30).stdout.strip())
        libdir = out / 'lib'
        shutil.copytree(krlua, libdir)
        shutil.copyfile(HERE / 'lua/dq5warp.lua', libdir / 'boot.lua')
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            seen = list(pool.map(lambda case: run(case, roms, state, out, mesence, libdir), CASES))
        results = []
        for (name, rom, scene, setting, (post, frame), made, want_map, want_at), got in zip(CASES, seen):
            ok = ((post is None or got['post'] == post) and (frame is None or got['frame'] == frame)
                  and (made is None or (got['cell'] == '85') == made)
                  and got['map'] == want_map and (want_at is None or got['at'] == list(want_at)))
            results.append({'case': name, 'rom': rom, 'to': scene[0], 'set': setting, **got,
                            'expected': {'post': post, 'frame': frame, 'exit_cell': made, 'map': want_map,
                                         'at': list(want_at) if want_at else None}, 'passed': ok})
        (out / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        for r in results:
            print(f'{r["case"]}: post {r["post"]} frame {r["frame"]} cell {r["cell"]} → {r["map"]} {tuple(r["at"])}'
                  f'{"" if r["passed"] else " 불일치"}')
        failed = [r['case'] for r in results if not r['passed']]
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
