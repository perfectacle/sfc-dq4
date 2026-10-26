"""대화 스크립트 쓰기(dq5talkwrite.py) 결과를 MesenCE 에서 말을 걸어 확인한다.

선실 세이브스테이트에서 파파스(슬롯 0B)에게 말을 건다. 대화 번호는 POKE 로 바꾸고, 대화마다 06:AF62(대화 시작)·
06:AF9C(묶음 포인터를 $F9 에 넣는 곳, A = 묶음 시작)·24:8BAF(A = 메시지 번호)를 기록해 첫 대화의 메시지 순서와
묶음 시작, 대화 뒤 플래그(7E:2190~)를 기대값과 견준다. 변경 롬은 조건 뒤집기·메시지 바꾸기·긴 스크립트를 뱅크 06 빈 자리로
옮기기·묶음 다시 채우기 네 벌이고, 바꾸지 않은 대화는 원본 롬과 같은지 본다.
원본 롬·선실 상태는 읽기만 하고 입력·패치·롬·기록은 --out 의 새 하위 폴더에 둔다.
  MESENCE=… python sfc/dq5/tools/dq5talkcheck.py rom/dq5.sfc --state work/state/ship.mss
"""
import argparse
import concurrent.futures
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from dq5map import lorom
from dq5talkwrite import TABLE

HERE = Path(__file__).resolve().parent
AT = '06:FE10'
PAPAS = {'op': 'if', 'cond': {'code': '1B', 'index': 1, 'mask': 1},
         'then': [{'op': 'msg', 'id': '74F'}, {'op': 'flag-on', 'index': 2, 'mask': 128}],
         'else': {'op': 'msg', 'id': '742'}}
# 원래 15바이트를 41바이트로 늘려 묶음 0(370바이트)이 원래 자리를 넘는 스크립트. 플래그 세 명령, はい/いいえ, else 없는 조건문
# 셋(참·거짓·블록 아닌 분기), 네이티브 호출(06:B3A0 은 메시지 1CC 를 띄움)을 차례로 쓴다.
LONG = [
    {'op': 'flag-set', 'index': 0x60, 'value': 0x5A},
    {'op': 'flag-on', 'index': 0x61, 'mask': 0x81},
    {'op': 'flag-off', 'index': 0x62, 'mask': 0x0F},
    {'op': 'msg', 'id': '742'},
    {'op': 'if', 'cond': {'code': '05'},
     'then': [{'op': 'msg', 'id': '616'}, {'op': 'flag-on', 'index': 0x63, 'mask': 0x01}],
     'else': {'op': 'msg', 'id': '617'}},
    {'op': 'if', 'cond': {'code': '1B', 'index': 0x61, 'mask': 0x80}, 'then': {'op': 'call', 'target': 'B3A0'}},
    {'op': 'if', 'cond': {'code': '1B', 'index': 0x62, 'mask': 0xF0}, 'then': [{'op': 'msg', 'id': '129'}]},
    {'op': 'msg', 'id': '74F'},
]
EDITS = {
    'cond': ([], [{'talk': '012', 'body': [{**PAPAS, 'cond': {**PAPAS['cond'], 'not': True}}]}]),
    'msg': ([], [{'talk': '012', 'body': [{**PAPAS, 'else': {'op': 'msg', 'id': '129'}}]}]),
    'long': (['--at', AT], [{'talk': '012', 'body': LONG}]),
    'repack': (['--at', AT, '--repack'], [{'talk': '012', 'body': LONG}]),
}
TALK = 'b:4,wait:40,up:3,wait:20,a:4,wait:30,a:4'
ANSWER = {'yes': 'wait:150,a:4', 'no': 'wait:120,down:3,wait:27,a:4'}
REST = ',wait:100,a:4' * 5
# (이름, 롬, 대화 번호, はい/いいえ, 기대 메시지(None 이면 원본 롬의 같은 대화와 같음),
#  기대 묶음 시작(None 이면 그 롬의 06:AEF8 표 값), 기대 플래그 {7E 주소: 값})
CASES = [
    ('original', 'original', 0x012, 'yes', ['742'], '8129', {0x2192: 0x00}),
    ('cond', 'cond', 0x012, 'yes', ['74F'], '8129', {0x2192: 0x80}),
    ('msg', 'msg', 0x012, 'yes', ['129'], '8129', {0x2192: 0x00}),
    ('long-yes', 'long', 0x012, 'yes', ['742', '616', '1CC', '74F'], 'FE10',
     {0x21F0: 0x5A, 0x21F1: 0x81, 0x21F2: 0x0F, 0x21F3: 0x01}),
    ('long-no', 'long', 0x012, 'no', ['742', '617', '1CC', '74F'], 'FE10',
     {0x21F0: 0x5A, 0x21F1: 0x81, 0x21F2: 0x0F, 0x21F3: 0x00}),
    ('repack-yes', 'repack', 0x012, 'yes', ['742', '616', '1CC', '74F'], '8129',
     {0x21F0: 0x5A, 0x21F1: 0x81, 0x21F2: 0x0F, 0x21F3: 0x01}),
    ('015-original', 'original', 0x015, 'yes', None, '8129', {}),
    ('015-long', 'long', 0x015, 'yes', None, 'FE10', {}),
    ('120-original', 'original', 0x120, 'yes', None, None, {}),
    ('120-repack', 'repack', 0x120, 'yes', None, None, {}),
    ('24E-original', 'original', 0x24E, 'yes', None, None, {}),
    ('24E-repack', 'repack', 0x24E, 'yes', None, 'FE10', {}),
]


def require(ok, message):
    if not ok:
        raise ValueError(message)


def command(tool, rom, *args):
    subprocess.run([sys.executable, str(HERE / tool), str(rom), *map(str, args)],
                   check=True, capture_output=True, text=True, timeout=120)


def run(case, roms, state, out, mesence, libdir):
    name, rom, talk, answer, *_ = case
    dest = out / name
    dest.mkdir()
    env = {k: v for k, v in os.environ.items()
           if k not in ('ROMPATCH', 'SET', 'POKE', 'CALLS', 'WW', 'WWRANGE', 'WRAMWATCH', 'COVER', 'ACCESS',
                        'VMADD', 'SHOTS', 'DUMP', 'VRAMDUMP', 'BG3FONT', 'LOG')}
    env.update(LIBDIR=str(libdir), STATE=str(state), SHOT_DIR=str(dest), MAXF='1100',
               CALLS='06AF62,06AF9C,248BAF', DUMP='1100:7E2190:8,1100:7E21F0:8', SHOTS='240',
               # 7E:21F2 를 FF 로 두어 flag-off(&= 0F)가 보이게 한다. 대화 번호는 파파스 슬롯 0B 의 인물 표.
               SET='21F2=FF', POKE=f'7E36EB={talk & 0xFF:02X};7E370B={talk >> 8:02X}',
               PRE=f'{TALK},{ANSWER[answer]}{REST}')
    with (dest / 'mesen.log').open('w', encoding='utf-8') as log:
        subprocess.run([str(mesence), '--testrunner', str(roms[rom]), str(HERE / 'lua/dq5msg.lua'),
                        '--Snes.DisableFrameSkipping=true'], env=env, stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=120)
    talks, flags = [], {}
    for line in (dest / 'msg.txt').read_text(encoding='utf-8').splitlines():
        parts = line.split()
        if len(parts) > 2 and parts[1] == '06AF62':
            talks.append({'start': None, 'messages': []})
        elif len(parts) > 2 and parts[1] == '06AF9C' and talks:
            talks[-1]['start'] = parts[2][2:]
        elif len(parts) > 2 and parts[1] == '248BAF' and talks:
            talks[-1]['messages'].append(parts[2][2:].lstrip('0').zfill(3))
        elif len(parts) > 3 and parts[1] == 'dump':
            base = int(parts[2], 16) & 0xFFFF
            flags.update({base + i: int(v, 16) for i, v in enumerate(parts[3:])})
    require(talks and talks[0]['messages'], f'{name}: 대화가 시작되지 않았거나 메시지가 없음')
    return talks[0], flags


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/talkcheck')
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
        for key, (options, scripts) in EDITS.items():
            source, manifest = out / f'{key}.json', out / f'{key}.patch.json'
            source.write_text(json.dumps({'format': 'dq5talk/1', 'scripts': scripts}, ensure_ascii=False, indent=1)
                              + '\n', encoding='utf-8')
            command('dq5talkwrite.py', original, 'patch', source, '-o', manifest, *options)
            command('dq5talkwrite.py', original, 'check', source, *options)
            roms[key] = out / f'{key}.sfc'
            command('dq5build.py', original, 'build', manifest, '-o', roms[key], '--ips', out / f'{key}.ips')
        libdir = subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True,
                                check=True, timeout=30).stdout.strip()
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            seen = list(pool.map(lambda case: run(case, roms, state, out, mesence, libdir), CASES))
        by_name = {case[0]: got for case, got in zip(CASES, seen)}
        results = []
        for (name, rom, talk, answer, want, start, want_flags), (got, flags) in zip(CASES, seen):
            if want is None:
                want = by_name[f'{talk:03X}-original'][0]['messages']
            if start is None:
                at = lorom(TABLE + ((talk - 0x11) >> 5) * 2)
                start = f'{int.from_bytes(roms[rom].read_bytes()[at:at + 2], "little"):04X}'
            ok = (got['messages'] == want and got['start'] == start
                  and all(flags.get(a) == v for a, v in want_flags.items()))
            results.append({'case': name, 'rom': rom, 'talk': f'{talk:03X}', 'answer': answer,
                            'messages': got['messages'], 'expected_messages': want,
                            'group_start': got['start'], 'expected_group_start': start,
                            'flags': {f'7E:{a:04X}': f'{flags.get(a, 0):02X}' for a in want_flags},
                            'expected_flags': {f'7E:{a:04X}': f'{v:02X}' for a, v in want_flags.items()},
                            'passed': ok})
        (out / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        for r in results:
            print(f'{r["case"]}: talk {r["talk"]} 메시지 {" ".join(r["messages"])} 묶음 {r["group_start"]} '
                  f'{" ".join(f"{a}={v}" for a, v in r["flags"].items())}{"" if r["passed"] else " 불일치"}')
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
