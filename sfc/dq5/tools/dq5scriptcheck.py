"""DQ5 이벤트·인물 쓰기 도구의 MesenCE 실행 검사.

형식은 sfc/dq5/docs/dq5-build-format.md. 배 선실을 다시 불러 인물 스크립트를 읽고,
23:E2F4·23:E29A 표 조회를 거쳐 확장 뱅크의 이벤트를 실행한다. 명령 주소·좌표·플래그를 비교한다.
원본 롬 데이터가 들어가는 패치·롬·IPS·덤프는 --out 아래 새 실행 폴더에만 쓴다.

  MESENCE=… python sfc/dq5/tools/dq5scriptcheck.py rom/dq5.sfc --state work/state/ship.mss --out work/scriptcheck
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

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CASES = [('number', None, (8, 9)), ('event', None, (8, 9)), ('branch03', None, (8, 13)),
         ('branch06', 0, (5, 13)), ('branch06', 1, (8, 13)), ('branch07', None, (8, 13)),
         ('branch07outside', None, (5, 13))]


def write_json(path, doc):
    path.write_text(json.dumps(doc, indent=2) + '\n', encoding='utf-8')
    return path


def command(tool, *args):
    subprocess.run([sys.executable, str(HERE / tool), *map(str, args)], check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=60)


def npc_patch(rom, out, name, commands):
    source = write_json(out / f'{name}.json', {
        'format': 'dq5npcscript/1', 'address': '05:A84F', 'length': 23, 'commands': commands,
    })
    patch = out / f'{name}.dq5patch.json'
    command('dq5npcwrite.py', rom, 'patch', source, '-o', patch)
    return patch


def build(rom, out, name, patches):
    command('dq5build.py', rom, 'build', *patches, '--size', '4', '-o', out / f'{name}.sfc',
            '--ips', out / f'{name}.ips')


def build_cases(rom, out):
    for mode in ('number', 'event'):
        binding = {'kind': mode, 'index': 7 if mode == 'number' else 8}
        if mode == 'event':
            binding.update(x=9, y=11)
        source = write_json(out / f'{mode}.json', {
            'format': 'dq5event/1', 'binding': binding,
            'commands': [{'op': '10', 'args': [127, 64]}, {'op': '01', 'args': [2]}, {'op': 'FF'}],
        })
        patch = out / f'{mode}.dq5patch.json'
        command('dq5eventwrite.py', rom, 'patch', source, '--at', '60:8000', '-o', patch)
        # LDA #번호 / JSL 표 조회 / RTL: 스크립트 포인터를 직접 주입하지 않고 게임의 조회 루틴을 탄다.
        stub = write_json(out / f'{mode}-stub.dq5patch.json', {
            'format': 'dq5patch/1', 'name': 'table-call', 'rom_size': 4,
            'writes': [{'at': '61:8000', 'hex': 'A90722F4E2236B' if mode == 'number' else 'A908229AE2236B'}],
        })
        body = npc_patch(rom, out, mode + '-npc', [{'op': '37', 'args': [0, 128, 97]}, {'op': '16'}])
        build(rom, out, mode, [patch, stub, body])
    branches = {
        'branch03': {'op': '03', 'target': 'yes'},
        'branch06': {'op': '06', 'args': [15, 1], 'target': 'yes'},
        'branch07': {'op': '07', 'args': [9, 11, 9, 11], 'target': 'yes'},
        'branch07outside': {'op': '07', 'args': [1, 1, 2, 2], 'target': 'yes'},
    }
    for name, branch in branches.items():
        body = npc_patch(rom, out, name, [branch, {'op': '2B', 'args': [5, 13]}, {'op': '16'},
                                        {'label': 'yes', 'op': '2B', 'args': [8, 13]}, {'op': '16'}])
        build(rom, out, name, [body])


def run_case(case, out, state, mesence, libdir):
    name, flag, expected = case
    tag = name + (str(flag) if flag is not None else '')
    dest = out / tag
    dest.mkdir()
    env = dict(os.environ, DRIVER=str(ROOT / 'tools/lua/walk.lua'), LIBDIR=libdir, STATE=str(state),
               PRE='b:4,wait:40', WAYPOINTS='3,11;3,24;7,24;up:10', ROMPATCH='156FF5=E0090B0117',
               CHANGES='99', MAXF='1000', AFTER='120', HOLD='90', SHOT_DIR=str(dest),
               WATCH='x8=7E3028;y8=7E3088;flag=7E220F;ev=7E19B3:3;f19=7E219F;'
                     'p8lo=7E3488;p8hi=7E34A8;p8bank=7E34C8;move8=7E3308',
               POKE=f'7E219F={flag:02X}' if flag is not None else '')
    with (dest / 'mesen.log').open('w', encoding='utf-8') as log:
        subprocess.run([str(mesence), '--testrunner', str(out / f'{name}.sfc'),
                        str(HERE / 'lua/dq5scriptcheck.lua'), '--Snes.DisableFrameSkipping=true'],
                       env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=90)
    walk = (dest / 'walk.txt').read_text(encoding='utf-8')
    trace = (dest / 'trace.txt').read_text(encoding='utf-8')
    fields = dict(line.split('=', 1) for line in walk.splitlines()
                  if line.startswith(('x8=', 'y8=', 'flag=', 'ev=', 'f19=', 'p8lo=', 'p8hi=', 'p8bank=', 'move8=')))
    pos = (int(fields['x8'], 16), int(fields['y8'], 16))
    checks = [pos == expected, 'end map 17/00' in walk]
    if name in ('number', 'event'):
        checks += [fields['flag'] == '40', fields['ev'] == '608005', 'end map 17/00 x=11 y=11' in walk]
        lookup = '23E2F4' if name == 'number' else '23E29A'
        calls = re.findall(rf'pc={lookup} a=([0-9A-F]+)', trace)
        checks.append(any(int(value, 16) & 0xFF == (7 if name == 'number' else 8) for value in calls))
        checks += [f'event={addr} op={op}' in trace
                   for addr, op in [('608000', '10'), ('608003', '01'), ('608005', 'FF')]]
        if name == 'event':
            checks.append('event=001A0D op=C3' in trace)
    else:
        stop = {'branch03': '05A859', 'branch060': '05A857', 'branch061': '05A85B',
                'branch07': '05A85D', 'branch07outside': '05A859'}[tag]
        checks += [fields['p8bank'] + fields['p8hi'] + fields['p8lo'] == stop, fields['move8'] == '00']
    if not all(checks):
        raise ValueError(f'{tag}: 예상 좌표 {expected}, 관측 {pos}; {dest} 로그 확인')
    return {'case': tag, 'npc_position': pos, 'flag': fields['flag'], 'event_pointer': fields['ev'], 'passed': True}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path, help='조작 가능한 배 선실 ship.mss')
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'), help='MesenCE 실행 파일(MESENCE)')
    ap.add_argument('--out', default='work/scriptcheck', type=Path)
    args = ap.parse_args()
    if not args.mesence:
        ap.error('--mesence 또는 MESENCE가 필요함')
    try:
        rom, state, mesence = args.rom.resolve(), args.state.resolve(), Path(args.mesence).resolve()
        for path in (rom, state, mesence):
            if not path.is_file():
                raise ValueError(f'파일 없음: {path}')
        args.out.mkdir(parents=True, exist_ok=True)
        out = Path(tempfile.mkdtemp(prefix='run-', dir=args.out.resolve()))
        print(f'실행 출력: {out}', flush=True)
        libdir = subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True,
                                check=True, timeout=30).stdout.strip()
        build_cases(rom, out)
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(lambda case: run_case(case, out, state, mesence, libdir), CASES))
        write_json(out / 'results.json', results)
        print(f'{len(results)}/{len(CASES)} 실행 검사 통과')
        return 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.output:
            print(error.output, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
