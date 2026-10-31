"""맵별 루틴 표 쓰기(dq5maphook.py)를 MesenCE 에서 확인한다.

변경 롬 여덟 벌(루틴 막기, 플래그 조건 둘, 표를 15:FF80 으로 옮겨 다시 쓰기, 제자리에 항목 하나를 빼고 다시 쓰기,
163개로 늘려 뱅크 3F 로 옮기기, 15:FF5C 둘째 표에 01/04 항목 더하기·플래그 조건)과 원본 롬에서 같은 맵에 순간이동해,
15:F7D0 이 고른 루틴·셀 읽기 루틴($1AAA)·셀 버퍼 값·걸은 뒤의 맵과 칸을 견준다.
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

from dq5maphook import CELL_FORMAT, FORMAT, NONE, cells_dump, dump, text
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
# 01/04 (32,5) 에서 네 방향으로 따로 걸어 셀 읽기 루틴이 통행을 바꾸는지 본다
WALKS = {d: ('01/04,32,5', f'{d}:160', None) for d in ('left', 'down', 'right', 'up')}
WALK_END = {'left': ('01/06', (75, 67)), 'down': ('01/04', (32, 7)), 'right': ('01/04', (36, 5)), 'up': ('01/04', (32, 4))}


def entry(entries, selector):
    group, bd = selector.split('/')
    return next(e for e in entries if e['group'] == group and e['map'] == bd)


def edits(rom):
    entries = dump(rom)['entries']
    stairs, tower, ship = entry(entries, '01/05'), entry(entries, '04/00'), entry(entries, '17/00')
    flag = {'index': '00', 'mask': '40'}
    hall = {'group': '01', 'map': '04', 'flag': None, 'post_load': text(NONE), 'per_frame': tower['per_frame']}
    strip = [{k: v for k, v in e.items() if k != 'index'} for e in entries]
    cells = [{k: v for k, v in e.items() if k != 'index'} for e in cells_dump(rom)['entries']]
    # 01/04 를 17/01 의 셀 읽기 루틴(00:BCC3)으로. 「7E:2190 bit6 이 켜졌을 때」 조건을 단 것도 만든다.
    room = {'group': '01', 'map': '04', 'flag': flag | {'when': 'set'}, 'routine': cells[0]['routine']}
    return {
        'off': ('patch', None, [{'index': stairs['index'], 'post_load': text(NONE)},
                                {'index': tower['index'], 'per_frame': text(NONE)}]),
        'set': ('patch', None, [{'index': stairs['index'], 'flag': flag | {'when': 'set'}}]),
        'clear': ('patch', None, [{'index': stairs['index'], 'flag': flag | {'when': 'clear'}}]),
        'moved': ('rewrite', '15:FF80', [hall] + [strip[e['index']] for e in (stairs, ship)]),
        'short': ('rewrite', '15:F907', [e for i, e in enumerate(strip) if i != tower['index']]),
        # 162개 뒤에 01/04 를 더해 163개. 뱅크 15 에 들어가지 않으므로 3F 로 옮기고 로더의 DB 를 스텁으로 바꾼다.
        'grown': ('rewrite', '3F:8000', strip + [hall], '15:FFF0'),
        'cells': ('cells-rewrite', '15:FF80', cells + [room | {'flag': None}]),
        'cellflag': ('cells-rewrite', '15:FF80', cells + [room]),
        # 04/00 항목의 맵 고르기를 01/04 로(제자리, 루틴은 그대로)
        'select': ('patch', None, [{'index': tower['index'], 'group': '01', 'map': '04'}]),
        # 04/00 항목의 맵을 푼 뒤 루틴을 원래 표의 그 칸에 없던 02:94E0(01/05 의 것)으로
        'raw': ('patch', None, [{'index': tower['index'], 'post_load': stairs['post_load']}], None, ['--raw-routines']),
        # 'moved' 의 3항목 표를 원래 롬의 빈 자리 0B:FBB0 에 두고 로더 DB 를 스텁으로
        'freebank': ('rewrite', '0B:FBB0', [hall] + [strip[e['index']] for e in (stairs, ship)], '15:FFF0'),
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
    ('hall-grown', 'grown', HALL, None, (None, '02:A7BD'), None, '04/0A', (8, 17)),
    ('tower-grown', 'grown', TOWER, None, (None, '02:A7BD'), None, '04/0A', (8, 17)),
    ('stairs-grown', 'grown', STAIRS, None, ('02:94E0', None), True, '01/04', (13, 47)),
    ('hall-select', 'select', HALL, None, ('02:94C1', '02:A7BD'), None, '04/0A', (8, 17)),
    ('tower-select', 'select', TOWER, None, ('15:F906', '15:F906'), None, '04/00', None),
    ('tower-raw', 'raw', TOWER, None, ('02:94E0', '02:A7BD'), None, '04/0A', (8, 17)),
    ('hall-freebank', 'freebank', HALL, None, (None, '02:A7BD'), None, '04/0A', (8, 17)),
    ('stairs-freebank', 'freebank', STAIRS, None, ('02:94E0', None), True, '01/04', (13, 47)),
    ('tower-freebank', 'freebank', TOWER, None, ('15:F906', '15:F906'), None, '04/00', None),
    # 01/04 를 00:BCC3 으로 읽는 롬도 원본과 같은 칸에 서거나 같은 출구로 나간다
    *[(f'walk-{d}-{rom}', rom, WALKS[d], None, (None, None), None, *WALK_END[d])
      for d in WALKS for rom in ('original', 'cells')],
]
# (이름, 롬, SET, 01/04 를 풀었을 때의 $1AAA, JMP ($1AAA) 로 00:BCC3 에 갔는가)
CELL_CASES = [
    ('room-original', 'original', None, 'B869', False),
    ('room-cells', 'cells', None, 'BCC3', True),
    ('room-cellflag', 'cellflag', None, 'B869', False),
    ('room-cellflag-adult', 'cellflag', ADULT, 'BCC3', True),
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
    load = re.search(rf'load {target} BE=\w\w post (\w\w:\w{{4}}) frame (\w\w:\w{{4}})(?: cell (\w\w))? cellread (\w{{4}})', log)
    require(final is not None and load is not None and 'timeout' not in log, f'{name}: 결과가 없음')
    jumps = dict(re.findall(r'jump (\w{4}) (\d+)', log))
    return {'post': load[1], 'frame': load[2], 'cell': load[3], 'cellread': load[4], 'jumps': jumps,
            'map': final[1], 'at': [int(final[2]), int(final[3])]}


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
        for key, (mode, at, entries, *more) in edits(Rom(original.read_bytes())).items():
            stub, options = (more[0] if more else None), (more[1] if len(more) > 1 else [])
            source, manifest = out / f'{key}.json', out / f'{key}.patch.json'
            kind = CELL_FORMAT if mode == 'cells-rewrite' else FORMAT
            source.write_text(json.dumps({'format': kind, 'entries': entries}, ensure_ascii=False, indent=2) + '\n',
                              encoding='utf-8')
            where = (['--at', at] if at else []) + (['--stub-at', stub] if stub else []) + options
            command(tool, original, mode, source, *where, '-o', manifest)
            command(tool, original, 'cells-check' if mode == 'cells-rewrite' else 'check', source, *where)
            roms[key] = out / f'{key}.sfc'
            command(HERE / 'dq5build.py', original, 'build', manifest, '-o', roms[key], '--ips', out / f'{key}.ips')
        krlua = Path(subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True,
                                    check=True, timeout=30).stdout.strip())
        libdir = out / 'lib'
        shutil.copytree(krlua, libdir)
        shutil.copyfile(HERE / 'lua/dq5warp.lua', libdir / 'boot.lua')
        cell_cases = [(name, rom, HALL, setting) for name, rom, setting, _, _ in CELL_CASES]
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            seen = list(pool.map(lambda case: run(case, roms, state, out, mesence, libdir), CASES + cell_cases))
        seen, cell_seen = seen[:len(CASES)], seen[len(CASES):]
        results = []
        for (name, rom, scene, setting, (post, frame), made, want_map, want_at), got in zip(CASES, seen):
            ok = ((post is None or got['post'] == post) and (frame is None or got['frame'] == frame)
                  and (made is None or (got['cell'] == '85') == made)
                  and got['map'] == want_map and (want_at is None or got['at'] == list(want_at)))
            results.append({'case': name, 'rom': rom, 'to': scene[0], 'set': setting, **got,
                            'expected': {'post': post, 'frame': frame, 'exit_cell': made, 'map': want_map,
                                         'at': list(want_at) if want_at else None}, 'passed': ok})
        for (name, rom, setting, want, jumped), got in zip(CELL_CASES, cell_seen):
            ok = got['cellread'] == want and ('BCC3' in got['jumps']) == jumped and got['map'] == '01/04'
            results.append({'case': name, 'rom': rom, 'to': HALL[0], 'set': setting, **got,
                            'expected': {'cellread': want, 'jumps_bcc3': jumped, 'map': '01/04'}, 'passed': ok})
        (out / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        for r in results:
            print(f'{r["case"]}: post {r["post"]} frame {r["frame"]} cell {r["cell"]} cellread {r["cellread"]} → {r["map"]} {tuple(r["at"])}'
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
