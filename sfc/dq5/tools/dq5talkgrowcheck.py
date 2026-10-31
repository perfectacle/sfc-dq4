"""대화 번호 900~ 에 덧붙인 스크립트를 MesenCE 에서 원래 뱅크의 같은 스크립트와 견준다.

덧붙인 롬은 대화 900~921(34개, 묶음 둘)을 뱅크 3F 에 두고 루틴을 06:FE10 에 둔다. 대조 롬은 같은 몸통 셋을
원래 스크립트 012·013·014 에 넣고 묶음을 다시 채운다. 선실 파파스의 대화 번호를 POKE 로 바꿔 말을 걸고
첫 대화의 메시지 순서와 플래그(7E:2190~·21F0~)를 견준다. 02/06 인물 하나의 대화 번호를 921 로 바꾼 롬에서는
인물 레코드로 이어진 덧붙인 스크립트를 걸어서 확인한다. 원본 롬·선실 상태는 읽기만 하고 출력은 --out 의 새 하위 폴더에 둔다.
  MESENCE=… python sfc/dq5/tools/dq5talkgrowcheck.py rom/dq5.sfc --state work/state/ship.mss
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

HERE = Path(__file__).resolve().parent
EXTRA = ['--extra-at', '3F:8000', '--hook-at', '06:FE10']
CONTROL = ['--at', '06:FE10', '--repack']


def branch(cond):
    return {'op': 'if', 'cond': cond, 'then': {'op': 'msg', 'id': '616'}, 'else': {'op': 'msg', 'id': '617'}}


# 900: 조건 뒤집기와 플래그. 901: BRK 를 쓰는 조건(일행·물건·레코드)·はい/いいえ·네이티브 호출·플래그. 921: 둘째 묶음.
# 902: 선실에서 거짓인 BRK 조회 조건(サンチョ 05 가 일행에 없음, 일행 레코드 1 이 없음, ドラゴンオーブ D1 을 갖지 않음)과
# 901 에 없던 조건 02·14·1A·1E·1F.
BODIES = {
    0x900: [{'op': 'if', 'cond': {'code': '1B', 'index': 1, 'mask': 1, 'not': True},
             'then': [{'op': 'msg', 'id': '74F'}, {'op': 'flag-on', 'index': 2, 'mask': 128}],
             'else': {'op': 'msg', 'id': '742'}}],
    0x901: [{'op': 'flag-set', 'index': 0x60, 'value': 0x5A},
            branch({'code': '03', 'member': 0}), branch({'code': '13', 'record': 0}),
            branch({'code': '11', 'item': 0x42}), branch({'code': '20'}),
            {'op': 'if', 'cond': {'code': '05'},
             'then': [{'op': 'msg', 'id': '618'}, {'op': 'flag-on', 'index': 0x61, 'mask': 1}],
             'else': {'op': 'msg', 'id': '619'}},
            {'op': 'call', 'target': 'B3A0'}, {'op': 'msg', 'id': '74F'}],
    0x902: [branch({'code': '03', 'member': 5}), branch({'code': '13', 'record': 1}),
            branch({'code': '11', 'item': 0xD1}), branch({'code': '02'}), branch({'code': '14'}),
            branch({'code': '1A', 'index': 1, 'value': 1}), branch({'code': '1E'}), branch({'code': '1F'})],
    0x921: [{'op': 'flag-off', 'index': 0x62, 'mask': 0x0F}, {'op': 'msg', 'id': '129'}, {'op': 'msg', 'id': '742'}],
}
PAIRS = {0x900: 0x012, 0x901: 0x013, 0x902: 0x015, 0x921: 0x014}
TALK = 'b:4,wait:40,up:3,wait:20,a:4,wait:30,a:4,wait:150' + ',a:4,wait:100' * 9
# 02/06 기본 목록(05:8CD4) 넷째(밤) 인물을 낮의 (24,12) 에 세우고 대화 번호를 921 로(dq5npcrecordcheck.py 와 같은 자리).
NPC = {'format': 'dq5npcrecord/1', 'entries': [{'list': '05:8CD4', 'index': 3, 'time': 'day',
                                                'fields': {'x': 24, 'y': 12, 'facing': 'down', 'gfx': 0x18,
                                                           'talk': 0x921}}]}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def tool(name, *args):
    subprocess.run([sys.executable, str(HERE / name), *map(str, args)], check=True, capture_output=True,
                   text=True, timeout=120)


def documents():
    extra = [{'talk': f'{t:03X}', 'body': BODIES.get(t) or [{'op': 'msg', 'id': f'{0x700 + t - 0x902:03X}'}]}
             for t in range(0x900, 0x922)]
    control = [{'talk': f'{PAIRS[t]:03X}', 'body': body} for t, body in BODIES.items()]
    return {'extra': ({'format': 'dq5talk/1', 'scripts': extra}, EXTRA),
            'control': ({'format': 'dq5talk/1', 'scripts': control}, CONTROL)}


def papas(name, rom, talk, out, mesence, libdir, state):
    dest = out / name
    dest.mkdir()
    env = {k: v for k, v in os.environ.items() if k not in ('ROMPATCH', 'SET', 'POKE', 'CALLS', 'DUMP', 'SHOTS', 'LOG')}
    env.update(LIBDIR=libdir, STATE=str(state), SHOT_DIR=str(dest), MAXF='1400', CALLS='06AF62,248BAF',
               DUMP='1400:7E2190:16,1400:7E21F0:4', SET='21F2=FF',
               POKE=f'7E36EB={talk & 0xFF:02X};7E370B={talk >> 8:02X}', PRE=TALK)
    with (dest / 'mesen.log').open('w', encoding='utf-8') as log:
        subprocess.run([str(mesence), '--testrunner', str(rom), str(HERE / 'lua/dq5msg.lua'),
                        '--Snes.DisableFrameSkipping=true'], env=env, stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=120)
    talks, flags = [], ''
    for line in (dest / 'msg.txt').read_text(encoding='utf-8').splitlines():
        parts = line.split()
        if parts[1:2] == ['06AF62']:
            talks.append([])
        elif parts[1:2] == ['248BAF'] and talks:
            talks[-1].append(f'{int(parts[2][2:], 16):03X}')
        elif parts[1:2] == ['dump']:
            flags += ' '.join(parts[3:]) + ' '
    require(talks and talks[0], f'{name}: 대화가 없음')
    return {'messages': talks[0], 'flags': flags.strip()}


def walk(name, rom, out, mesence, libdir, state):
    dest = out / name
    dest.mkdir()
    lib = out / 'lib'
    env = {k: v for k, v in os.environ.items() if k not in ('ROMPATCH', 'SET', 'POKE', 'LATESET', 'PARTY')}
    env.update(LIBDIR=str(lib), STATE=str(state), SHOT_DIR=str(dest), MAXF='1500', SETTLE='120',
               TO='02/06,24,14,1', TEST='up:40,wait:40,a:4,wait:60,a:4,wait:200,wait:30',
               CHECK_GROUP='02', CHECK_MAP='06')
    with (dest / 'mesen.log').open('w', encoding='utf-8') as log:
        subprocess.run([str(mesence), '--testrunner', str(rom), str(HERE / 'lua/dq5npcrecordcheck.lua'),
                        '--Snes.DisableFrameSkipping=true'], env=env, stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=120)
    text = (dest / 'warp.txt').read_text(encoding='utf-8')
    found = re.search(r'^messages (.*)$', text, re.M)
    require(found is not None, f'{name}: 메시지 기록이 없음')
    return {'messages': [v for v in found[1].split(',') if v]}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/talkgrowcheck')
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
        manifests = {}
        for key, (doc, options) in documents().items():
            source = out / f'{key}.json'
            source.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
            manifests[key] = out / f'{key}.patch.json'
            tool('dq5talkwrite.py', original, 'check', source, *options)
            tool('dq5talkwrite.py', original, 'patch', source, '-o', manifests[key], *options)
            roms[key] = out / f'{key}.sfc'
            tool('dq5build.py', original, 'build', manifests[key], '-o', roms[key], '--ips', out / f'{key}.ips')
        npc = out / 'npc.json'
        npc.write_text(json.dumps(NPC, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        tool('dq5npcrecord.py', original, 'patch', npc, '-o', out / 'npc.patch.json')
        roms['linked'] = out / 'linked.sfc'
        tool('dq5build.py', original, 'build', manifests['extra'], out / 'npc.patch.json', '-o', roms['linked'])
        libdir = subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True,
                                check=True, timeout=30).stdout.strip()
        shutil.copytree(libdir, out / 'lib')
        shutil.copyfile(HERE / 'lua/dq5warp.lua', out / 'lib/boot.lua')
        jobs = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            for t, c in PAIRS.items():
                jobs[f'extra-{t:03X}'] = pool.submit(papas, f'extra-{t:03X}', roms['extra'], t, out, mesence, libdir, state)
                jobs[f'control-{c:03X}'] = pool.submit(papas, f'control-{c:03X}', roms['control'], c, out, mesence,
                                                       libdir, state)
            jobs['extra-012'] = pool.submit(papas, 'extra-012', roms['extra'], 0x012, out, mesence, libdir, state)
            jobs['original-012'] = pool.submit(papas, 'original-012', original, 0x012, out, mesence, libdir, state)
            jobs['linked-921'] = pool.submit(walk, 'linked-921', roms['linked'], out, mesence, libdir, state)
            got = {name: job.result() for name, job in jobs.items()}
        results = []
        for t, c in PAIRS.items():
            a, b = got[f'extra-{t:03X}'], got[f'control-{c:03X}']
            results.append({'case': f'{t:03X} vs {c:03X}', 'extra': a, 'control': b, 'passed': a == b})
        a, b = got['extra-012'], got['original-012']
        results.append({'case': '012 덧붙인 롬 vs 원본', 'extra': a, 'control': b, 'passed': a == b})
        linked, control = got['linked-921'], got['control-014']
        # 02/06 에 들어설 때 장면 메시지 1D1(원본 롬에서도 같음, dq5npcrecordcheck.py)이 먼저 나온다.
        results.append({'case': '02/06 인물 대화 번호 921', 'extra': linked, 'control': control,
                        'passed': linked['messages'] == ['1D1', *control['messages']]})
        (out / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        for r in results:
            print(f'{r["case"]}: {" ".join(r["extra"]["messages"])} | {" ".join(r["control"]["messages"])}'
                  f'{"" if r["passed"] else " 불일치"}')
        failed = [r['case'] for r in results if not r['passed']]
        require(not failed, f'불일치: {", ".join(failed)}')
        print(f'{len(results)}개 비교 통과')
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
