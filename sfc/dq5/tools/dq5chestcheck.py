"""상자·서랍·발밑 보상 쓰기를 원본/패치 롬의 실제 조사 명령으로 비교한다.

sfc/dq5/docs/dq5-map-format.md의 보물상자 형식. 입력 JSON→dq5patch→롬/IPS를 만들고,
선실에서 걸어가거나 맵에 재진입한 뒤 컨트롤러로 조사한다. 금화·조회된 보상·열림 비트·
기존 비트 보존을 확인한다. 원본 롬/세이브는 읽기만 하고 --out 아래 새 폴더에 저장한다.

  MESENCE=… python sfc/dq5/tools/dq5chestcheck.py rom/dq5.sfc --state work/state/ship.mss
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

from dq5chestwrite import FORMAT

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
INPUT = ('up:8,wait:30,a:8,wait:60,down:6,wait:25,down:6,wait:25,down:6,wait:25,'
         'right:6,wait:25,a:8,wait:200,a:4,wait:150,a:4,wait:150,b:4,wait:100')
CASES = {
    'chest': ({'chests': [{'index': 2, 'reward': 0x241}]}, 321, 0x2210, 0x20, 0x2210, 0x20, 0x33, 0x131),
    'search': ({'search': [{'index': 31, 'reward': 0x2B0, 'flag_index': 4, 'mask': 0x80}]},
               432, 0x2230, 0x80, 0x222F, 1, 0xA1, 0x12F),
    'foot': ({'foot': [{'index': 0, 'group': 0x17, 'map': 0, 'x': 3, 'y': 5, 'layer': 1,
                       'reward': 0x31F, 'flag_index': 3, 'mask': 0x40}]},
             543, 0x2243, 0x40, 0x222F, 1, 0xA1, 0x12B),
}


def command(tool, *args):
    subprocess.run([sys.executable, str(HERE / tool), *map(str, args)], check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=90)


def environment(libdir, state, dest):
    env = os.environ.copy()
    for key in ('ADULT', 'ANYWHERE', 'BATTLE', 'FIELD', 'GROUP', 'LATESET', 'PARTY', 'POKE', 'ROMPATCH', 'SAVE',
                'SET', 'TEST', 'TO', 'WAGON', 'PRE', 'LOOP', 'WAYPOINTS', 'PEEK', 'SHOTMSG', 'CALLS', 'WW',
                'WWRANGE', 'WRAMWATCH', 'COVER', 'ACCESS', 'VMADD', 'SHOTS', 'DUMP', 'VRAMDUMP', 'BG3FONT',
                'TRACE', 'LOG', 'RWATCH', 'WWATCH', 'LATE', 'PREPARE', 'WATCH', 'INPUT', 'FLAG', 'OLD_FLAG'):
        env.pop(key, None)
    env.update(LIBDIR=libdir, STATE=str(state), SHOT_DIR=str(dest))
    return env


def run(mesence, rom, script, dest, env):
    with (dest / 'mesen.log').open('w', encoding='utf-8') as log:
        subprocess.run([str(mesence), '--testrunner', str(rom), str(script), '--Snes.DisableFrameSkipping=true'],
                       env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=90)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def prepare(name, original, state, out, mesence, libdir):
    dest = out / (name + '-scene')
    dest.mkdir()
    env = environment(libdir, state, dest)
    if name == 'chest':
        env.update(TO='01/02,34,31', SETTLE='120', SAVE='scene.mss', MAXF='1500')
        script = HERE / 'lua/dq5warp.lua'
    else:
        env.update(PREPARE='1', DRIVER=str(ROOT / 'tools/lua/walk.lua'), PRE='b:4,wait:40',
                   WAYPOINTS='3,5;up:8', MAXF='1200', CHANGES='99')
        script = HERE / 'lua/dq5chestcheck.lua'
    run(mesence, original, script, dest, env)
    result = dest / 'scene.mss'
    require(result.is_file(), f'{name}: 장면 세이브가 없음')
    return result


def gold(wram):
    return int.from_bytes(wram[0x2019:0x201C], 'little')


def compare(name, state, original, out, mesence, libdir):
    changes, amount, flag, mask, old_flag, old_mask, old_reward, message = CASES[name]
    dest = out / name
    dest.mkdir()
    source, manifest, patched = dest / 'input.json', dest / 'patch.json', dest / 'patched.sfc'
    source.write_text(json.dumps({'format': FORMAT, **changes}, indent=2) + '\n', encoding='utf-8')
    command('dq5chestwrite.py', original, 'patch', source, '-o', manifest)
    command('dq5chestwrite.py', original, 'check', source)
    command('dq5build.py', original, 'build', manifest, '-o', patched, '--ips', dest / 'patched.ips')
    results = []
    for mode, rom in (('original', original), ('patched', patched)):
        run_dir = dest / mode
        run_dir.mkdir()
        env = environment(libdir, state, run_dir)
        env.update(INPUT=INPUT, FLAG=f'7E{flag:04X}', OLD_FLAG=f'7E{old_flag:04X}')
        run(mesence, rom, HERE / 'lua/dq5chestcheck.lua', run_dir, env)
        before, after = [(run_dir / f'{when}.wram').read_bytes() for when in ('before', 'after')]
        require(len(before) == len(after) == 0x20000, f'{name}/{mode}: WRAM 크기가 다름')
        trace = (run_dir / 'trace.txt').read_text(encoding='utf-8')
        rewards = [int(v, 16) for v in re.findall(r'reward .* value=([0-9A-F]+)', trace)]
        changed = mode == 'patched'
        expected = 0x100 + amount if changed else old_reward
        require(rewards == [expected], f'{name}/{mode}: 실제 조회 보상 {rewards} != {[expected]}')
        require(gold(before) == 100 and gold(after) == 100 + (amount if changed else 0),
                f'{name}/{mode}: 금화 전후가 다름')
        wanted_message = message if changed or name != 'foot' else 0x12F
        require(f'value={wanted_message:04X}' in trace, f'{name}/{mode}: 조사 종류 메시지가 다름')
        if changed:
            require(after[flag] == mask, f'{name}: 새 열림 비트가 다름')
            if old_flag != flag:
                require(after[old_flag] == 0, f'{name}: 원래 열림 비트까지 바뀜')
        else:
            require(after[old_flag] == old_mask, f'{name}: 원본 열림 비트가 다름')
            if old_flag != flag:
                require(after[flag] == 0, f'{name}: 원본 롬이 새 비트를 씀')
        results.append({'mode': mode, 'reward': expected, 'gold_before': gold(before), 'gold_after': gold(after),
                        'flag': f'7E:{flag:04X}', 'flag_value': after[flag], 'passed': True})
    return {'case': name, 'runs': results, 'passed': True}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('rom', type=Path)
    p.add_argument('--state', type=Path, required=True)
    p.add_argument('--out', type=Path, default=Path('work/chest-check'))
    p.add_argument('--mesence', default=os.environ.get('MESENCE'))
    args = p.parse_args()
    if not args.mesence:
        p.error('MESENCE 또는 --mesence가 필요함')
    try:
        original, state, mesence = args.rom.resolve(), args.state.resolve(), Path(args.mesence).resolve()
        for path in (original, state, mesence):
            require(path.is_file(), f'파일 없음: {path}')
        args.out.mkdir(parents=True, exist_ok=True)
        out = Path(tempfile.mkdtemp(prefix='run-', dir=args.out.resolve()))
        libdir = subprocess.check_output(['krpatch', 'sfc', 'lua'], text=True, timeout=30).strip()
        print(f'출력 {out}', flush=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futures = {name: pool.submit(prepare, name, original, state, out, mesence, libdir)
                       for name in ('chest', 'ship')}
            states = {name: future.result() for name, future in futures.items()}
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(lambda name: compare(name, states['chest' if name == 'chest' else 'ship'],
                                                        original, out, mesence, libdir), CASES))
        (out / 'results.json').write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8')
        print('3쌍/6실행 통과: 보상·금화·새 열림 비트·기존 비트 보존')
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stdout:
            print(error.stdout, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
