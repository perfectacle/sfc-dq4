"""성장·조우 레코드를 더하고 표를 옮긴 롬을 MesenCE 로 돌려, 게임이 새 레코드를 읽는지 확인한다.

만드는 롬(dq5build.py 로 셋을 합침):
  dq5namewrite.py --at 4E:8000            이름 표를 옮겨 23:C242~D6A0 을 비운다
  dq5progresswrite.py --area-at 23:C242 --person-at 23:96F3 --reuse-names
                                          구역 85(구역 1 을 틀로 スライム 한 종만) 추가, 사람 성장 11(주인공을 틀로
                                          ちから 곡선 +10·레벨 2 경험치 바꿈) 추가
  dq5encounterwrite.py --areas 86         21/02 의 $1948 = 0 구역과 53/50(23:FDD6, 그룹 50 이상)의 $1948 = 1·2 구역을 85 로
장면(원본 롬과 만든 롬 모두):
  growth-0   슬라임 전투에서 이겨 주인공(+0 = 00) 레벨 1 → 2
  growth-11  동료 칸(PARTY=02, 7E:206A)의 +0 을 0B 로, 능력치를 새 레코드의 레벨 1 값으로 둔 채 붙인 같은 전투에서
             레벨업(만든 롬만). 주인공 +0 을 바꾸면 필드·전투가 멈춰서 동료 칸을 쓴다
  area       21/02 (50,43) 에서 좌우로 걸음
  high       53/50 (40,42) 에서 $1948 = 1 로 좌우로 걸음
원본 롬과 선실 상태는 읽기만 하며 JSON·패치·롬·기록은 --out 의 새 폴더에 쓴다.
  MESENCE=… python sfc/dq5/tools/dq5recordgrowcheck.py rom/dq5.sfc --state work/state/ship.mss
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

from dq5growth import RECORD, RECORD_FIELD, exp_at, stats_at
from dq5map import Rom
from dq5progresswrite import dump, table_bases

HERE = Path(__file__).resolve().parent
NEW_AREA, NEW_PERSON = 0x55, 0x0B
HERO, SLOT = 0x2040, 0x206A           # 일행 레코드 0·1(42바이트씩)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def save_json(path, doc):
    path.write_text(json.dumps(doc, indent=2) + '\n', encoding='utf-8')


def command(tool, rom, *args):
    subprocess.run([sys.executable, str(HERE / tool), str(rom), *map(str, args)], check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=120)


def build(original, out):
    hero = dump(Rom(original.read_bytes()))['growth'][0]
    strength = [min(255, v + 10) for v in hero['stats']['strength']]
    slots = [{'index': i, 'weight': 7 if i == 5 else 0} for i in range(10)]
    slots[5].update(monster=0, count_code=0)
    progress = {'format': 'dq5progress/1',
                'growth': [{'kind': 'person', 'index': NEW_PERSON, 'base': 0, 'exp2': 31,
                            'stats': {'strength': strength}}],
                'encounters': [{'index': NEW_AREA, 'base': 1, 'slots': slots, 'fixed': {'weight': 0},
                                'rate_index': 7}]}
    encounter = {'format': 'dq5encounter/1', 'maps': [{'map': '21/02', 'areas': [NEW_AREA, 0x14, 0x14]},
                                                      {'map': '53/50', 'areas': [0xFF, NEW_AREA, NEW_AREA]}]}
    names = {'format': 'dq5names/1', 'tables': []}
    for name, doc in (('progress', progress), ('encounter', encounter), ('names', names)):
        save_json(out / f'{name}.json', doc)
    command('dq5namewrite.py', original, 'patch', out / 'names.json', '--at', '4E:8000', '-o', out / 'names.patch.json')
    command('dq5progresswrite.py', original, 'patch', out / 'progress.json', '--area-at', '23:C242',
            '--person-at', '23:96F3', '--reuse-names', '-o', out / 'progress.patch.json')
    command('dq5encounterwrite.py', original, 'patch', out / 'encounter.json', '--areas', NEW_AREA + 1,
            '-o', out / 'encounter.patch.json')
    command('dq5build.py', original, 'build', out / 'names.patch.json', out / 'progress.patch.json',
            out / 'encounter.patch.json', '-o', out / 'grown.sfc', '--ips', out / 'grown.ips')
    return out / 'grown.sfc'


def environment(libdir, state, dest, **extra):
    env = os.environ.copy()
    for key in ('ADULT', 'ANYWHERE', 'BATTLE', 'FIELD', 'GROUP', 'LATESET', 'PARTY', 'POKE', 'ROMPATCH', 'SAVE',
                'SET', 'TEST', 'TO', 'WAGON', 'PRE', 'LOOP', 'WAYPOINTS', 'PEEK', 'SHOTMSG', 'LVLUP', 'SETTLE'):
        env.pop(key, None)
    env.update(LIBDIR=libdir, STATE=str(state), SHOT_DIR=str(dest), **extra)
    return env


def run(mesence, rom, lua, dest, env):
    dest.mkdir(parents=True, exist_ok=True)
    with (dest / 'mesen.log').open('w') as log:
        subprocess.run([str(mesence), '--testrunner', str(rom), str(lua), '--Snes.DisableFrameSkipping=true'],
                       env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)


def scene(name, rom, battle_state, ship_state, out, mesence, libdir):
    dest = out / name
    walk = 'right:150,left:150,right:150,left:150'
    if name.startswith('growth'):
        state = battle_state.with_name('battle-11.mss') if name.startswith('growth-11') else battle_state
        env = environment(libdir, state, dest, DRIVER=str(HERE / 'lua/dq5battle.lua'), MAXF='2400',
                          LOOP='a:4,wait:20', LVLUP='1')
    elif name.startswith('area'):
        env = environment(libdir, ship_state, dest, DRIVER=str(HERE / 'lua/dq5warp.lua'), TO='21/02,50,43',
                          SETTLE='100', MAXF='1800', TEST=walk)
    else:
        env = environment(libdir, ship_state, dest, DRIVER=str(HERE / 'lua/dq5warp.lua'), TO='53/50,40,42',
                          SET='1948=01', SETTLE='100', MAXF='1800', TEST=walk)
    run(mesence, rom, HERE / 'lua/dq5recordgrowcheck.lua', dest, env)
    return (dest / 'records.txt').read_text(), (dest / 'final.wram').read_bytes()


def growth_result(name, rom_path, text, ram, person, slot=HERO):
    rom = Rom(rom_path.read_bytes())
    record = table_bases(rom)['person'] + person * RECORD
    actual = [int.from_bytes(ram[slot + field:slot + field + (2 if i < 2 else 1)], 'little')
              for i, field in enumerate(RECORD_FIELD)]
    next_exp = int.from_bytes(ram[slot + 0x26:slot + 0x29], 'little')
    require(ram[slot] == person, f'{name}: 일행 레코드 +0 이 {ram[slot]:02X}')
    require(f'growth record={record:06X}' in text, f'{name}: 성장 레코드 {record:06X} 를 고르지 않음')
    require(ram[slot + 0x12] == 2, f'{name}: 레벨 2 가 되지 않음')
    require(actual == stats_at(rom, record, 2) and next_exp == exp_at(rom, record, 3),
            f'{name}: 능력치 {actual}·다음 경험치 {next_exp} 가 레코드 {record:06X} 와 다름')
    return {'case': name, 'record': f'{record:06X}', 'stats': actual, 'next_exp': next_exp}


def area_result(name, text, place, area, monster):
    """place 맵에서 걸은 걸음의 구역이 모두 area 인지. 걷다가 출구로 다른 맵에 들어간 걸음은 뺀다."""
    areas = set(re.findall(rf'area ([0-9A-F]{{2}}) map {place}', text))
    require(areas == {f'{area:02X}'}, f'{name}: {place} 의 조우 판정 구역 {sorted(areas)} != {area:02X}')
    groups = re.findall(r'group ([0-9A-F]{16})', text)
    if monster is not None:
        require(groups and all(g[:4] == f'{monster:02X}FF' for g in groups),
                f'{name}: 무리 {groups} 가 몬스터 {monster:02X} 한 마리가 아님')
    return {'case': name, 'map': place, 'area': f'{area:02X}', 'steps': len(re.findall(f'map {place}', text)),
            'groups': groups}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', type=Path, required=True)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/recordgrowcheck')
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
        grown = build(original, out)
        libdir = subprocess.run(['krpatch', 'sfc', 'lua'], check=True, capture_output=True, text=True,
                                timeout=30).stdout.strip()
        battle = out / 'battle-state'
        run(mesence, original, HERE / 'lua/dq5warp.lua', battle,
            environment(libdir, state, battle, FIELD='341,56', BATTLE='00:1', SETTLE='300', SAVE='battle.mss',
                        MAXF='1800'))
        # 전투 중에 +0 을 바꾸면 전투가 끝날 때 원래 값으로 돌아오므로, 전투를 붙이기 전에 바꾼 상태를 따로 만든다.
        record = table_bases(Rom(grown.read_bytes()))['person'] + NEW_PERSON * RECORD
        sets = [f'{SLOT:04X}={NEW_PERSON:02X}', f'{SLOT + 0x26:04X}=01', f'{SLOT + 0x27:04X}=00', f'{SLOT + 0x28:04X}=00']
        for i, (field, value) in enumerate(zip(RECORD_FIELD, stats_at(Rom(grown.read_bytes()), record, 1))):
            for k in range(2 if i < 2 else 1):
                sets.append(f'{SLOT + field + k:04X}={value >> 8 * k & 0xFF:02X}')
        run(mesence, original, HERE / 'lua/dq5warp.lua', battle / '11',
            environment(libdir, state, battle / '11', FIELD='341,56', BATTLE='00:1', SETTLE='300', PARTY='02',
                        SAVE='battle.mss', MAXF='1800', LATESET=';'.join(sets)))
        (battle / '11/battle.mss').rename(battle / 'battle-11.mss')
        require((battle / 'battle.mss').is_file(), '전투 상태가 저장되지 않음')
        scenes = [('growth-0-original', original), ('growth-0-grown', grown), ('growth-11-grown', grown),
                  ('area-original', original), ('area-grown', grown), ('high-original', original),
                  ('high-grown', grown)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            seen = dict(zip((s[0] for s in scenes), pool.map(
                lambda s: scene(s[0], s[1], battle / 'battle.mss', state, out, mesence, libdir), scenes)))
        results = [growth_result('growth-0-original', original, *seen['growth-0-original'], 0),
                   growth_result('growth-0-grown', grown, *seen['growth-0-grown'], 0),
                   growth_result('growth-11-grown', grown, *seen['growth-11-grown'], NEW_PERSON, SLOT)]
        require(results[2]['stats'] != results[1]['stats'] and results[2]['next_exp'] != results[1]['next_exp'],
                '새 사람 레코드와 주인공 레코드의 결과가 같아 구별되지 않음')
        results += [area_result('area-original', seen['area-original'][0], '21/02', 0x01, None),
                    area_result('area-grown', seen['area-grown'][0], '21/02', NEW_AREA, 0x00),
                    area_result('high-original', seen['high-original'][0], '53/50', 0x27, None),
                    area_result('high-grown', seen['high-grown'][0], '53/50', NEW_AREA, None)]
        save_json(out / 'results.json', results)
        print(json.dumps(results, ensure_ascii=False))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.output:
            print(error.output, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
