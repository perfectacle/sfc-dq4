"""상자·서랍·발밑·두 칸 앞·아래층 상자·필드 보상 쓰기를 원본/패치 롬의 실제 조사 명령으로 비교한다.

sfc/dq5/docs/dq5-map-format.md의 보물상자 형식. 입력 JSON→dq5patch→롬/IPS를 만들고,
선실에서 걸어가거나 dq5warp.lua 로 그 자리에 내려선 뒤 컨트롤러로 조사한다. 금화·조회된 보상·열림 비트·
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
         'right:6,wait:25,a:8,wait:200,a:4,wait:150,a:4,wait:150,b:4,wait:220')
CASES = {
    'chest': ({'chests': [{'index': 2, 'reward': 0x241}]}, 321, 0x2210, 0x20, 0x2210, 0x20, 0x33, 0x131),
    'search': ({'search': [{'index': 31, 'reward': 0x2B0, 'flag_index': 4, 'mask': 0x80}]},
               432, 0x2230, 0x80, 0x222F, 1, 0xA1, 0x12F),
    'foot': ({'foot': [{'index': 0, 'group': 0x17, 'map': 0, 'x': 3, 'y': 5, 'layer': 1,
                       'reward': 0x31F, 'flag_index': 3, 'mask': 0x40}]},
             543, 0x2243, 0x40, 0x222F, 1, 0xA1, 0x12B),
    'ahead': ({'ahead': [{'index': 11, 'reward': 0x38E, 'flag_index': 0x2E, 'mask': 0x02}]},
              654, 0x223E, 0x02, 0x223D, 0x08, 0x5F, 0x12B),
    'lower': ({'lower': [{'index': 3, 'reward': 0x3FD, 'flag_index': 0x19, 'mask': 0x08}]},
              765, 0x2229, 0x08, 0x2228, 0x08, 0xB1, 0x131),
    'field': ({'field': [{'index': 0, 'reward': 0x46C}]}, 876, 0x21B3, 0x10, 0x21B3, 0x10, 0xCA, 0x12B),
    # 원본은 이 칸에 보상이 없다(old_reward None)
    'field_move': ({'field': [{'index': 0, 'x': 24, 'y': 168, 'reward': 0x46C, 'flag_index': 0x22, 'mask': 0x04}]},
                   876, 0x21B2, 0x04, 0x21B3, 0x10, None, 0x12B),
}


def grow_chests(doc):
    # 표에 없는 상자 칸 26개의 맵을 뒤에 붙임. 19/00 이 마지막이라 (6,45) 가 상자 185(7E:2227 & 40)
    for group, map_number, count in ((0x00, 0x0C, 2), (0x02, 0x01, 3), (0x19, 0x02, 3), (0x1D, 0x03, 2),
                                     (0x1F, 0x00, 2), (0x20, 0x00, 2), (0x20, 0x01, 7), (0x19, 0x00, 5)):
        doc['chest_maps'].append({'group': group, 'map': map_number, 'count': count})
        doc['chests'] += [{'reward': 0xFFFF}] * count
    doc['chests'][185] = {'reward': 0x100 + 987}


def grow_search(doc):
    doc['search'].append({'group': 0x17, 'map': 0, 'x': 2, 'y': 4, 'unused': 1, 'reward': 0x100 + 111,
                          'flag_index': 0x0B, 'mask': 0x01})


def grow_foot(doc):
    doc['foot'].append({'group': 0x17, 'map': 0, 'x': 3, 'y': 5, 'layer': 1, 'reward': 0x100 + 222,
                        'flag_index': 3, 'mask': 0x20})


def grow_ahead(doc):
    doc['ahead'].append({'group': 0x17, 'map': 0, 'x': 9, 'y': 9, 'reward': 0x100 + 333,
                         'flag_index': 0x2E, 'mask': 0x04})


def move_lower(doc):
    doc['lower'][3].update(reward=0x100 + 444, flag_index=0x19, mask=0x10)


# dq5chestreloc.py 로 표 전체를 다시 쓰는 사례: (문서 고치기, 자리, 금화, 새 비트, 마스크, 원래 비트, 마스크,
# 원본 보상 또는 None, 패치 메시지, 원본이 못 찾을 때의 메시지). 자리는 시험용으로 고른 빈 곳이다
RELOC = {
    'grow_chests': (grow_chests, {'chests': '3F:8000', 'chest-maps': '1E:EE4E'}, 987, 0x2227, 0x40, 0x2227, 0x40,
                    None, 0x131, 0x12C),
    'grow_search': (grow_search, {'search': '3F:9000'}, 111, 0x2237, 0x01, 0x2237, 0x01, None, 0x12F, 0x130),
    'grow_foot': (grow_foot, {'foot': '3F:A000'}, 222, 0x2243, 0x20, 0x222F, 0x01, 0xA1, 0x12B, None),
    'grow_ahead': (grow_ahead, {'ahead': '3F:B000'}, 333, 0x223E, 0x04, 0x223E, 0x04, None, 0x12B, 0x12C),
    'move_lower': (move_lower, {'ahead': '3F:B000', 'lower': '1E:F435'}, 444, 0x2229, 0x10, 0x2228, 0x08, 0xB1,
                   0x131, None),
}
# 원본이 그 자리에서 아무것도 찾지 못할 때의 첫 메시지가 패치와 다른 사례(상자로 보지 않아 12B)
ORIGINAL_KIND = {'grow_chests': 0x12B}
for _name, (_edit, _at, *_rest) in RELOC.items():
    CASES[_name] = (None, *_rest[:-1])
# 조사 뒤 세계 지도 버퍼의 블록(블록 좌표 x, y, 원본, 패치). 밤이라 빛 블록 A7 이 놓인 자리를 본다
# 필드에 들어갈 때 빛 블록을 놓으므로, 장면도 그 롬으로 만들어야 하는 사례
OWN_SCENE = {'field_move'}
BLOCKS = {'field_move': ((11, 83, 0xA7, 0xCA), (12, 84, 0x178, 0xA7))}
# 장면 없이 --state 를 그대로 쓰는 사례
START = 'start'
# 장면: 원본 롬에서 dq5warp.lua 로 내려선 자리, 없으면 선실에서 걸어감.
# 필드는 밤(`$075E` = `0100` 으로 둠)이고 21AA.0 이 켜져 있어야 빛 블록 코드가 21A5.2 를 켠다
SCENES = {'chest': {'TO': '01/02,34,31'}, 'search': None, 'foot': None, 'ahead': {'TO': '03/04,10,10'},
          'lower': {'TO': '51/51,18,37,2'}, 'field': {'FIELD': '22,166', 'SET': '21AA|01;075E=00;075F=01'},
          'field_move': {'FIELD': '24,168', 'SET': '21AA|01;075E=00;075F=01'},
          'grow_chests': {'TO': '19/00,5,46'}, 'grow_search': {'WAYPOINTS': '1,5;up:8'}, 'grow_foot': None,
          'grow_ahead': START, 'move_lower': 'lower'}
# 필드 조사는 선 자리를 보므로 걷지 않고 바로 명령 창을 연다
INPUTS = {'field': INPUT.removeprefix('up:8,wait:30,'), 'field_move': INPUT.removeprefix('up:8,wait:30,')}


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


def prepare(name, original, state, out, mesence, libdir, label=None):
    dest = out / ((label or name) + '-scene')
    dest.mkdir()
    env = environment(libdir, state, dest)
    setup = SCENES.get(name) or {'WAYPOINTS': '3,5;up:8'}
    if 'WAYPOINTS' not in setup:
        env.update(setup, SETTLE='120', SAVE='scene.mss', MAXF='1500')
        script = HERE / 'lua/dq5warp.lua'
    else:
        env.update(PREPARE='1', DRIVER=str(ROOT / 'tools/lua/walk.lua'), PRE='b:4,wait:40',
                   WAYPOINTS=setup['WAYPOINTS'], MAXF='1200', CHANGES='99')
        script = HERE / 'lua/dq5chestcheck.lua'
    run(mesence, original, script, dest, env)
    result = dest / 'scene.mss'
    require(result.is_file(), f'{name}: 장면 세이브가 없음')
    return result


def scene(name):
    value = SCENES[name]
    if value == START:
        return START
    if isinstance(value, str):
        assert not isinstance(SCENES[value], str), value
        return scene(value)
    return name if value else 'ship'


def block(wram, x, y):
    i = y * 256 + x
    return wram[0x10000 + i] | (wram[0xE000 + (i >> 3)] >> (7 - (i & 7)) & 1) << 8


def gold(wram):
    return int.from_bytes(wram[0x2019:0x201C], 'little')


def compare(name, state, original, out, mesence, libdir, start):
    changes, amount, flag, mask, old_flag, old_mask, old_reward, message = CASES[name]
    dest = out / name
    dest.mkdir()
    source, manifest, patched = dest / 'input.json', dest / 'patch.json', dest / 'patched.sfc'
    none_message = 0x12C
    if name in RELOC:
        edit, at, *_, none_message = RELOC[name]
        command('dq5chestreloc.py', original, 'dump', '-o', source)
        doc = json.loads(source.read_text(encoding='utf-8'))
        edit(doc)
        source.write_text(json.dumps(doc, indent=2) + '\n', encoding='utf-8')
        places = [arg for table, place in at.items() for arg in (f'--{table}-at', place)]
        command('dq5chestreloc.py', original, 'patch', source, '-o', manifest, *places)
        command('dq5chestreloc.py', original, 'check', source, *places)
    else:
        source.write_text(json.dumps({'format': FORMAT, **changes}, indent=2) + '\n', encoding='utf-8')
        command('dq5chestwrite.py', original, 'patch', source, '-o', manifest)
        command('dq5chestwrite.py', original, 'check', source)
    command('dq5build.py', original, 'build', manifest, '-o', patched, '--ips', dest / 'patched.ips')
    results = []
    for mode, rom in (('original', original), ('patched', patched)):
        run_dir = dest / mode
        run_dir.mkdir()
        run_state = prepare(name, rom, start, out, mesence, libdir, f'{name}-{mode}') if name in OWN_SCENE else state
        env = environment(libdir, run_state, run_dir)
        env.update(INPUT=INPUTS.get(name, INPUT), FLAG=f'7E{flag:04X}', OLD_FLAG=f'7E{old_flag:04X}')
        run(mesence, rom, HERE / 'lua/dq5chestcheck.lua', run_dir, env)
        before, after = [(run_dir / f'{when}.wram').read_bytes() for when in ('before', 'after')]
        require(len(before) == len(after) == 0x20000, f'{name}/{mode}: WRAM 크기가 다름')
        trace = (run_dir / 'trace.txt').read_text(encoding='utf-8')
        rewards = [int(v, 16) for v in re.findall(r'reward .* value=([0-9A-F]+)', trace)]
        changed = mode == 'patched'
        expected = 0x100 + amount if changed else old_reward
        require(rewards == ([] if expected is None else [expected]),
                f'{name}/{mode}: 실제 조회 보상 {rewards} != {expected}')
        require(gold(before) == 100 and gold(after) == 100 + (amount if changed else 0),
                f'{name}/{mode}: 금화 전후가 다름')
        wanted_message = message if changed or name not in ('foot', 'grow_foot') else 0x12F
        if expected is None:
            require(f'value={none_message:04X}' in trace, f'{name}/{mode}: 찾지 못함 메시지 {none_message:X} 가 없음')
            wanted_message = ORIGINAL_KIND.get(name, message)
        require(f'value={wanted_message:04X}' in trace, f'{name}/{mode}: 조사 종류 메시지가 다름')
        if changed:
            require(after[flag] == mask, f'{name}: 새 열림 비트가 다름')
            if old_flag != flag:
                require(after[old_flag] == 0, f'{name}: 원래 열림 비트까지 바뀜')
        else:
            require(after[old_flag] == (0 if old_reward is None else old_mask), f'{name}: 원본 열림 비트가 다름')
            if old_flag != flag:
                require(after[flag] == 0, f'{name}: 원본 롬이 새 비트를 씀')
        blocks = {f'{x},{y}': block(after, x, y) for x, y, *_ in BLOCKS.get(name, ())}
        for x, y, *values in BLOCKS.get(name, ()):
            require(blocks[f'{x},{y}'] == values[changed], f'{name}/{mode}: 블록 ({x},{y}) = {blocks[f"{x},{y}"]:X}')
        results.append({'mode': mode, 'reward': expected, 'blocks': blocks, 'gold_before': gold(before), 'gold_after': gold(after),
                        'flag': f'7E:{flag:04X}', 'flag_value': after[flag],
                        'old_flag': f'7E:{old_flag:04X}', 'old_flag_value': after[old_flag], 'passed': True})
    return {'case': name, 'runs': results, 'passed': True}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('rom', type=Path)
    p.add_argument('--state', type=Path, required=True)
    p.add_argument('--out', type=Path, default=Path('work/chest-check'))
    p.add_argument('--mesence', default=os.environ.get('MESENCE'))
    p.add_argument('--case', choices=CASES, action='append', help='이 사례만(여러 번 줄 수 있음)')
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
        cases = list(dict.fromkeys(args.case or CASES))
        scenes = sorted({scene(name) for name in cases if name not in OWN_SCENE} - {START})
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            futures = {name: pool.submit(prepare, name, original, state, out, mesence, libdir)
                       for name in scenes}
            states = {name: future.result() for name, future in futures.items()} | {START: state}
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(lambda name: compare(name, states.get(scene(name)),
                                                        original, out, mesence, libdir, state), cases))
        (out / 'results.json').write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8')
        print(f'{len(cases)}쌍/{2 * len(cases)}실행 통과: 보상·금화·새 열림 비트·기존 비트 보존')
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stdout:
            print(error.stdout, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
