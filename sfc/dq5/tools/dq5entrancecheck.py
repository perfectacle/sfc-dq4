"""dq5fieldtables.py 의 입구 표 옮기기·늘리기를 MesenCE 에서 원래 롬과 견준다.

형식은 sfc/dq5/docs/dq5-build-format.md 의 「필드 블록·입구 표」. 입구 표 둘을 --at 자리로 옮기고 보조 표
(걸어서 들어가는 입구)에 항목 하나((345,56) → 그룹 02)를 더한 롬을 만든다.

  보조 입구  필드 341,56 세이브스테이트에서 오른쪽으로 걷는다. 원래 롬은 필드에 남고, 고친 롬은 02/00 에 들어감
  일반 입구  장면 이동 도구로 01/00 에서 필드로 나온다. 도구는 원래 자리의 그룹 01 입구를 341,56 으로 덮으므로,
             원래 롬은 341,56 에, 옮긴 표를 읽는 고친 롬은 옮긴 그룹 01 입구 그대로(331,67)에 선다
  일반 입구로 들어가기  옮긴 일반 표 맨 앞에 (331,67) → 그룹 02 를 하나 더 둔 롬(front.sfc)으로 01/00 에서 나와
             (331,67) 에 선 뒤 아래로 갔다 위로 돌아온다. 일반 입구 2A:F247 은 좌표가 같은 첫 항목을 고르므로 02/00 에,
             원래 롬(같은 자리에 FIELD 로 섬)은 01/00 에 들어간다

원본 롬·세이브스테이트는 읽기만 하고 입력 JSON부터 롬·실행 로그까지 --out 의 새 폴더에 둔다.

  MESENCE=… python sfc/dq5/tools/dq5entrancecheck.py rom/dq5.sfc --state work/state/ship.mss \\
      --field-state work/state/field-free.mss
"""
import argparse
import concurrent.futures
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from dq5fieldtables import ENTRANCE_TABLES, dump, entrance_fields, record
from dq5map import Rom
from dq5progresscheck import command, environment, require, run, save_json

HERE = Path(__file__).resolve().parent
NEW = {'group': 2, 'x': 345, 'y': 56}
FRONT = {'group': 2, 'x': 331, 'y': 67}


def build(original, out, at):
    rom = Rom(original.read_bytes())
    aux = [{k: e[k] for k in ('group', 'x', 'y')} for e in dump(rom)['entrances'] if e['table'] == 'aux']
    source = out / 'grow.json'
    save_json(source, {'format': 'dq5fieldtables/1', 'entrance_tables': {'aux': aux + [NEW]}})
    command('dq5fieldtables.py', original, 'patch', source, '--entrances-at', at, '-o', out / 'grow.patch.json')
    command('dq5build.py', original, 'build', out / 'grow.patch.json', '-o', out / 'grow.sfc', '--ips', out / 'grow.ips')
    start, count = ENTRANCE_TABLES['main']
    return next(entrance_fields(record(rom, start + i * 5)) for i in range(count)
                if record(rom, start + i * 5)[0] == 1)


def build_front(original, out, at):
    """옮긴 일반 표 맨 앞에 그룹 01 입구와 같은 자리의 그룹 02 항목을 둔 롬."""
    entries = dump(Rom(original.read_bytes()))['entrances']
    tables = {t: [{k: e[k] for k in ('group', 'x', 'y')} for e in entries if e['table'] == t] for t in ('main', 'aux')}
    tables['main'].insert(0, {'group': FRONT['group'], 'x': FRONT['x'], 'y': FRONT['y']})
    source = out / 'front.json'
    save_json(source, {'format': 'dq5fieldtables/1', 'entrance_tables': tables})
    command('dq5fieldtables.py', original, 'patch', source, '--entrances-at', at, '-o', out / 'front.patch.json')
    command('dq5build.py', original, 'build', out / 'front.patch.json', '-o', out / 'front.sfc')


def run_enter(rom, name, state, out, mesence, libdir, field):
    dest = out / name
    env = environment(libdir, state, dest)
    env.update(FIELD=field, SETTLE='60', MAXF='2000', TEST='down:24,wait:30,up:24,wait:400')
    run(mesence, rom, HERE / 'lua/dq5warp.lua', dest, env)


def entered(out, name):
    found = re.search(r'end map (\w\w)/(\w\w) cell (\d+),(\d+)', (out / name / 'warp.txt').read_text())
    require(found is not None, f'{name}: 맵에 들지 않음')
    return f'{found[1]}/{found[2]}', (int(found[3]), int(found[4]))


def run_walk(rom, name, state, out, mesence, libdir, reads):
    dest = out / name
    env = environment(libdir, state, dest)
    env.update(DRIVER=str(HERE / 'lua/dq5msg.lua'), MAXF='400', PRE='right:40,wait:300', READS=reads)
    run(mesence, rom, HERE / 'lua/dq5tablecheck.lua', dest, env)


def run_exit(rom, name, state, out, mesence, libdir):
    dest = out / name
    env = environment(libdir, state, dest)
    env.update(FIELD='341,56', SETTLE='60', MAXF='1500')
    run(mesence, rom, HERE / 'lua/dq5warp.lua', dest, env)


def place(out, name):
    ram = (out / name / 'final.wram').read_bytes()
    return {'BC': ram[0xBC], 'BD': ram[0xBD], 'BE': ram[0xBE],
            'x': int.from_bytes(ram[0xB6:0xB8], 'little'), 'y': int.from_bytes(ram[0xB8:0xBA], 'little')}


def landed(out, name):
    found = re.search(r'end map \S+ field (\d+),(\d+)', (out / name / 'warp.txt').read_text())
    require(found is not None, f'{name}: 필드에 나온 자리가 없음')
    return int(found[1]), int(found[2])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path, help='배 선실 세이브스테이트')
    ap.add_argument('--field-state', required=True, type=Path, help='필드 341,56 에 선 세이브스테이트')
    ap.add_argument('--at', default='68:8000', help='시험 롬에서 입구 표를 둘 자리')
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/entrancecheck')
    args = ap.parse_args()
    if not args.mesence:
        ap.error('--mesence 또는 MESENCE가 필요함')
    try:
        original, state, field = args.rom.resolve(), args.state.resolve(), args.field_state.resolve()
        mesence = Path(args.mesence).resolve()
        for path in (original, state, field, mesence):
            require(path.is_file(), f'파일 없음: {path}')
        args.out.mkdir(parents=True, exist_ok=True)
        out = Path(tempfile.mkdtemp(prefix='run-', dir=args.out.resolve()))
        print(f'실행 출력: {out}', flush=True)
        libdir = subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True,
                                check=True, timeout=30).stdout.strip()
        home = build(original, out, args.at)
        build_front(original, out, args.at)
        grow = out / 'grow.sfc'
        bank, _, addr = args.at.partition(':')
        at = int(bank, 16) << 16 | int(addr, 16)
        reads = f'04FE83-04FEC9,{at:06X}-{at + 0x1FF:06X}'
        jobs = [lambda: run_walk(original, 'walk-original', field, out, mesence, libdir, reads),
                lambda: run_walk(grow, 'walk-grow', field, out, mesence, libdir, reads),
                lambda: run_exit(original, 'exit-original', state, out, mesence, libdir),
                lambda: run_exit(grow, 'exit-grow', state, out, mesence, libdir),
                lambda: run_enter(original, 'enter-original', state, out, mesence, libdir, '331,67'),
                lambda: run_enter(out / 'front.sfc', 'enter-front', state, out, mesence, libdir, '341,56')]
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda job: job(), jobs))
        before, after = place(out, 'walk-original'), place(out, 'walk-grow')
        require(before['BE'] & 0x80 == 0 and before['x'] > NEW['x'], f'원래 롬: 필드에서 지나가지 않음 {before}')
        require(after['BE'] & 0x80 and (after['BC'], after['BD']) == (NEW['group'], 0), f'고친 롬: 02/00 에 들지 않음 {after}')
        grown = (out / 'walk-grow/observed.txt').read_text()
        require('read 04FE' in (out / 'walk-original/observed.txt').read_text() and 'read 04FE' not in grown
                and f'read {at >> 16:02X}' in grown, '고친 롬이 옮긴 보조 입구 표를 읽지 않음')
        exits = landed(out, 'exit-original'), landed(out, 'exit-grow')
        require(exits == ((341, 56), (home['x'], home['y'])), f'필드로 나온 자리가 다름 {exits}')
        enters = entered(out, 'enter-original'), entered(out, 'enter-front')
        require(enters == (('01/00', (32, 92)), ('02/00', (29, 83))), f'일반 입구로 들어간 맵이 다름 {enters}')
        results = {'보조 입구': {'원래': before, '고친': after},
                   '일반 입구로 들어가기': {'원래': enters[0], '앞에 둔 그룹 02': enters[1]},
                   '일반 입구': {'원래': exits[0], '고친': exits[1], '그룹 01 입구': (home['x'], home['y'])}}
        save_json(out / 'results.json', results)
        print('6회 실행, 입구 표 옮기기·늘리기 게임 검사 통과')
        print(json.dumps(results, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, StopIteration, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.output:
            print(error.output, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
