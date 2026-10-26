"""dq5encounterwrite.py 로 고친 필드 구역 격자·실내 구역 연결·고정 무리·이벤트 전투 무리를 실제 게임에서 확인한다.

형식은 sfc/dq5/docs/dq5-data-format.md 의 「전투 조우」. 고친 롬마다 대조 롬으로 같은 장면을 돌려 무리가 갈리는지 본다.

  필드    필드 341,56 에서 좌우로 걷는다. 격자 0 의 그 둘레 3x3 칸을 구역 0D → 01
  실내    21/02 (50,43) 에서 좌우로 걷는다. 21/02 의 구역 셋을 01·14·14 → 0D·01·0D. $1948 을 0·1·2 로 둔 세 번
  고정    같은 자리. 대조 롬은 구역 01 을 고정 무리 5 만 나오게 한 롬(dq5progresswrite.py), 고친 롬은
          거기에 고정 무리 5 를 スライム 3·ドラキー 1 로
  이벤트  첫 필드 이벤트 전투(무리 01, スライム 3)를 ドラキー 2 로

장면 준비로 조우 계수 표 23:EA44 를 모두 FF 로 덮어 걸음마다 조우가 잦게 한다(확인하는 표가 아님).
원본 롬·선실 상태는 읽기만 하고 입력 JSON부터 롬·실행 로그까지 --out 의 새 폴더에 둔다.

  MESENCE=… python sfc/dq5/tools/dq5encountercheck.py rom/dq5.sfc --state work/state/ship.mss
"""
import argparse
import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from dq5encounter import AREA_SIZE, EXITS, area
from dq5encounterwrite import dump
from dq5map import Rom
from dq5progresscheck import command, environment, require, run, save_json

HERE = Path(__file__).resolve().parent
GRID_AREA = 0x01
MAP_AREAS = [0x0D, 0x01, 0x0D]   # 21/02 의 원래 구역 셋은 01·14·14
FIXED_MEMBERS = [(0x00, 3), (0x03, 1)]
EVENT_MEMBERS = [(0x03, 2)]

PROGRESS = {'format': 'dq5progress/1', 'encounters': [
    {'index': 1, 'slots': [{'index': i, 'weight': 0} for i in range(10)], 'fixed': {'weight': 7, 'group': 5}}]}
EDITS = {
    'map': {'maps': [{'map': '21/02', 'areas': MAP_AREAS}]},
    'fixed': {'fixed_groups': [{'index': 5, 'members': [{'monster': m, 'count_code': c - 1} for m, c in FIXED_MEMBERS]}]},
    'event': {'event_groups': [{'index': 1, 'members': [{'monster': m, 'count': c} for m, c in EVENT_MEMBERS]}]},
}
RATE = '11EA44=FFFFFFFFFFFFFFFF'
WALK = 'right:150,left:150,right:150,left:150,right:150,left:150'
TRACE = {'TRACE': '23E7C2,23E9B0,23EA40,23E98F,248C39', 'LOG': '7E1001,7E1003,7E1005,7E1007'}
SCENES = {
    'field': ({'FIELD': '341,56', 'ROMPATCH': RATE, 'TEST': WALK}, 'grid'),
    'indoor': ({'TO': '21/02,50,43', 'ROMPATCH': RATE, 'TEST': WALK}, 'map'),
    'indoor1': ({'TO': '21/02,50,43', 'ROMPATCH': RATE, 'TEST': WALK, 'SET': '1948=01'}, 'map'),
    'indoor2': ({'TO': '21/02,50,43', 'ROMPATCH': RATE, 'TEST': WALK, 'SET': '1948=02'}, 'map'),
    'fixed': ({'TO': '21/02,50,43', 'ROMPATCH': RATE, 'TEST': WALK}, 'fixed'),
    'event': ({'FIELD': '341,56', 'GROUP': '01', 'TEST': ','.join(['a:4,wait:30'] * 20)}, 'event'),
}


def grid_edit(original):
    grid = dump(Rom(original.read_bytes()))['field_grids'][0]
    for row in range(0, 3):
        for col in range(9, 12):
            grid['rows'][row][col] = GRID_AREA
    return [grid]


def build(original, out):
    command('dq5progresswrite.py', original, 'patch', save(out / 'progress.json', PROGRESS), '-o', out / 'progress.patch.json')
    command('dq5build.py', original, 'build', out / 'progress.patch.json', '-o', out / 'base.sfc', '--ips', out / 'base.ips')
    for name, edit in {'grid': {'field_grids': grid_edit(original)}, **EDITS}.items():
        source = save(out / f'{name}.json', {'format': 'dq5encounter/1', **edit})
        command('dq5encounterwrite.py', original, 'patch', source, '-o', out / f'{name}.patch.json')
        patches = [out / f'{name}.patch.json'] + ([out / 'progress.patch.json'] if name == 'fixed' else [])
        command('dq5build.py', original, 'build', *patches, '-o', out / f'{name}.sfc', '--ips', out / f'{name}.ips')


def save(path, doc):
    save_json(path, doc)
    return path


def run_case(scene, case, rom, state, out, mesence, libdir):
    options, _ = SCENES[scene]
    dest = out / f'{scene}-{case}'
    env = environment(libdir, state, dest)
    env.update(options, **TRACE, SETTLE='60', MAXF='1800')
    run(mesence, rom, HERE / 'lua/dq5warptrace.lua', dest, env)
    require((dest / 'trace.txt').is_file(), f'{dest.name}: trace.txt 가 없음')


def records(out, name):
    """(걸음마다 구역 번호 목록, 무리를 정한 곳마다 (갈래, 구역, 무리), 첫 전투 메시지 때 무리)."""
    areas, groups, first = [], [], None
    for line in (out / name / 'trace.txt').read_text().splitlines():
        f = line.split()
        if len(f) < 3:
            continue
        kv = dict(x.split('=') for x in f[2:] if '=' in x)
        b = b''.join(int(kv[k], 16).to_bytes(2, 'little') for k in ('7E1001', '7E1003', '7E1005', '7E1007'))
        party = [(m, c) for m, c in zip(b[:4], b[4:]) if m != 0xFF]
        if f[1] == '23E7C2':
            areas.append(int(kv['A'], 16) & 0xFF)
        elif f[1] in EXITS:
            groups.append((EXITS[f[1]], int(kv['X'], 16) // AREA_SIZE, party))
        elif f[1] == '248C39' and first is None:
            first = party
    return areas, groups, first


def possible(rom, n):
    return {m for m, w in zip(area(rom, n)['monsters'], area(rom, n)['weights']) if w}


def verify(original, out):
    results = {}
    rom = Rom(original.read_bytes())
    for scene, (before, after) in (('field', (0x0D, GRID_AREA)), ('indoor', (0x01, MAP_AREAS[0])),
                                   ('indoor1', (0x14, MAP_AREAS[1])), ('indoor2', (0x14, MAP_AREAS[2]))):
        for case, want in (('original', before), (SCENES[scene][1], after)):
            areas, groups, _ = records(out, f'{scene}-{case}')
            require(areas and set(areas) == {want}, f'{scene}-{case}: 구역이 {want:02X} 만이 아님 {sorted(set(areas))}')
            require(groups, f'{scene}-{case}: 조우가 없음')
            require(all(k != 'fixed' and n == want and {m for m, _ in p} <= possible(rom, want) for k, n, p in groups),
                    f'{scene}-{case}: 무리가 구역 {want:02X} 에서 나올 수 없음 {groups}')
            results[f'{scene}-{case}'] = {'구역': want, '걸음': len(areas), '무리': [p for _, _, p in groups]}
    for case, want in (('original', [(0xB2, 2), (0xB0, 1), (0xB1, 2)]), ('fixed', FIXED_MEMBERS)):
        _, groups, _ = records(out, f'fixed-{case}')
        require(groups and all(k == 'fixed' and n == 1 and p == want for k, n, p in groups),
                f'fixed-{case}: 고정 무리가 {want} 가 아님 {groups}')
        results[f'fixed-{case}'] = {'무리': want, '조우': len(groups)}
    for case, want in (('original', [(0x00, 3)]), ('event', EVENT_MEMBERS)):
        _, _, first = records(out, f'event-{case}')
        require(first == want, f'event-{case}: 첫 전투 메시지 때 무리가 {want} 가 아님 {first}')
        results[f'event-{case}'] = {'무리': want}
    save_json(out / 'results.json', results)
    return results


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/encountercheck')
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
        libdir = subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True,
                                check=True, timeout=30).stdout.strip()
        build(original, out)
        jobs = []
        for scene, (_, case) in SCENES.items():
            jobs.append((scene, 'original', out / 'base.sfc' if scene == 'fixed' else original))
            jobs.append((scene, case, out / f'{case}.sfc'))
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda job: run_case(*job, state, out, mesence, libdir), jobs))
        results = verify(original, out)
        print(f'{len(jobs)}회 실행, {len(SCENES)}장면 게임 검사 통과')
        print(json.dumps(results, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.output:
            print(error.output, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
