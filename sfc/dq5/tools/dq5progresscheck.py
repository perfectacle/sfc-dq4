"""DQ5 성장·조우·상점 쓰기 도구를 실제 게임에서 확인한다.

형식은 sfc/dq5/docs/dq5-data-format.md. 새 패치로 전투 승리·무작위 조우·상점 조회를 실행하고
성장값·몬스터 무리·품목과 가격을 기존 디코더의 계산과 비교한다. 물건 가격은 dq5tables.py로 쓴다.
원본 롬·선실 상태는 읽기만 하고 입력 JSON부터 IPS·실행 로그까지 --out의 새 폴더에 둔다.

  MESENCE=… python sfc/dq5/tools/dq5progresscheck.py rom/dq5.sfc --state work/state/ship.mss
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

from dq5growth import PEOPLE, RECORD_FIELD, exp_at, stats_at
from dq5map import Rom
from dq5progresswrite import dump
from dq5shop import price
import dq5mesen

HERE = Path(__file__).resolve().parent


def require(condition, message):
    if not condition:
        raise ValueError(message)


def save_json(path, doc):
    path.write_text(json.dumps(doc, indent=2) + '\n', encoding='utf-8')


def command(tool, rom, *args):
    subprocess.run([sys.executable, str(HERE / tool), str(rom), *map(str, args)], check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=60)


def build_cases(original, out):
    data = dump(Rom(original.read_bytes()))
    hp = data['growth'][0]['stats']['hp'].copy()
    strength = data['growth'][0]['stats']['strength'].copy()
    hp[1], strength[1] = 30, 31
    shop = next(row for row in data['shops'] if row['kind'] == 2 and row['key'] == 1)
    items = shop['items'].copy()
    items[:2] = [0, 1]
    slots = [{'index': i, 'weight': 7 if i == 5 else 0} for i in range(10)]
    slots[5].update(monster=3, count_code=0)
    docs = {
        'growth': {'growth': [{'kind': 'person', 'index': 0, 'exp2': 23, 'stats': {'hp': hp, 'strength': strength}}]},
        'encounter': {'encounters': [{'index': 1, 'slots': slots, 'fixed': {'weight': 0}, 'rate_index': 7}]},
        'shop': {'shops': [{'kind': 2, 'index': shop['index'], 'items': items}]},
    }
    for name, changes in docs.items():
        source, patch = out / f'{name}.json', out / f'{name}.patch.json'
        save_json(source, {'format': 'dq5progress/1', **changes})
        command('dq5progresswrite.py', original, 'patch', source, '-o', patch)
        patches = [patch]
        if name == 'shop':
            tables = out / 'prices.json'
            save_json(tables, {'format': 'dq5tables/1', 'items': [
                {'id': '00', '가격': 77, '가격배수': 0}, {'id': '01', '가격': 88, '가격배수': 1}]})
            prices = out / 'prices.patch.json'
            command('dq5tables.py', original, 'patch', tables, '-o', prices)
            patches.append(prices)
        command('dq5build.py', original, 'build', *patches, '-o', out / f'{name}.sfc', '--ips', out / f'{name}.ips')
    return items


def environment(libdir, state, dest):
    env = os.environ.copy()
    # 장면 드라이버의 선택 옵션이 셸 환경에 남아 있어도 시험 입력은 같아야 한다.
    for key in ('ADULT', 'ANYWHERE', 'BATTLE', 'FIELD', 'GROUP', 'LATESET', 'PARTY', 'POKE', 'ROMPATCH', 'SAVE',
                'SET', 'TEST', 'TO', 'WAGON', 'PRE', 'LOOP', 'WAYPOINTS', 'PEEK', 'SHOTMSG', 'CALLS', 'WW',
                'WWRANGE', 'WRAMWATCH', 'COVER', 'ACCESS', 'VMADD', 'SHOTS', 'DUMP', 'VRAMDUMP', 'BG3FONT',
                'TRACE', 'LOG', 'RWATCH', 'WWATCH', 'LATE', 'OAMDUMP'):
        env.pop(key, None)
    env.update(LIBDIR=libdir, STATE=str(state), SHOT_DIR=str(dest))
    return env


def run(mesence, rom, lua, dest, env):
    dest.mkdir()
    with (dest / 'mesen.log').open('w', encoding='utf-8') as log:
        dq5mesen.testrunner(str(mesence), str(rom), str(lua), '--Snes.DisableFrameSkipping=true',
                            env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=90)


def prepare_battle(original, state, out, mesence, libdir):
    dest = out / 'battle-state'
    env = environment(libdir, state, dest)
    env.update(FIELD='341,56', BATTLE='00:1', SETTLE='300', SAVE='battle.mss', MAXF='1800')
    run(mesence, original, HERE / 'lua/dq5warp.lua', dest, env)
    require('timeout' not in (dest / 'warp.txt').read_text(), '전투 상태 생성 시간 초과')
    require((dest / 'battle.mss').is_file(), '전투 상태가 저장되지 않음')


def run_case(name, state, out, mesence, libdir):
    dest = out / name
    if name == 'growth':
        state = out / 'battle-state/battle.mss'
    env = environment(libdir, state, dest)
    env['MODE'] = name
    if name == 'growth':
        env.update(DRIVER=str(HERE / 'lua/dq5battle.lua'), MAXF='2400', LOOP='a:4,wait:20', PEEK='7E2040:42')
    elif name == 'shop':
        env.update(DRIVER=str(HERE / 'lua/dq5msg.lua'), MAXF='800', POKE='7E36EB=01;7E370B=00',
                   ROMPATCH='35C37=A901',
                   PRE='b:4,wait:40,up:3,wait:20,a:4,wait:30,a:4,wait:150,a:4,wait:80,a:4,wait:80')
    else:
        env.update(DRIVER=str(HERE / 'lua/dq5warptrace.lua'), TO='21/02,50,43', SETTLE='100', MAXF='1800',
                   TEST='right:150,left:150,right:150,left:150', TRACE='0082AF,23E7C2,23E9B0,23EA40,23E98F',
                   LOG='7E1001,7E1003,7E1005,7E1007')
    run(mesence, out / f'{name}.sfc', HERE / 'lua/dq5progresscheck.lua', dest, env)
    require(len((dest / 'final.wram').read_bytes()) == 0x20000, f'{name}: WRAM 덤프가 없음')


def verify(out, items):
    rom = Rom((out / 'growth.sfc').read_bytes())
    ram = (out / 'growth/final.wram').read_bytes()
    actual = [int.from_bytes(ram[0x2040 + field:0x2040 + field + (2 if i < 2 else 1)], 'little')
              for i, field in enumerate(RECORD_FIELD)]
    expected = stats_at(rom, PEOPLE, 2)
    next_exp = int.from_bytes(ram[0x2066:0x2069], 'little')
    require(ram[0x2052] == 2 and actual == expected and next_exp == exp_at(rom, PEOPLE, 3),
            f'성장 결과 불일치: {actual}, 다음 경험치 {next_exp}')
    observed = (out / 'growth/observed.txt').read_text()
    require('pc=23EB50' in observed and 'pc=23ED58' in observed, '성장·다음 경험치 계산 경로가 실행되지 않음')
    require('msg 0BF' in (out / 'growth/battle.txt').read_text(), '레벨업 메시지가 나오지 않음')
    results = [{'case': 'growth', 'level': 2, 'stats': actual, 'next_exp': next_exp}]
    ram = (out / 'encounter/final.wram').read_bytes()
    require(ram[0x1001:0x1009] == bytes([3, 255, 255, 255, 1, 0, 0, 0]), '조우 몬스터·마릿수 불일치')
    trace = (out / 'encounter/trace.txt').read_text()
    require(re.search(r'23E7C2 A=0001 .*Y=0007', trace) is not None, '맵 구역 1 조우 판정을 거치지 않음')
    require('23E9B0 A=0003' in trace and '7E1001=FF03' in trace and '7E1005=0001' in trace,
            '단일 무리 생성 경로에서 드라키 한 마리를 확인하지 못함')
    results.append({'case': 'encounter', 'area': 1, 'monster': 3, 'count': 1})
    text = (out / 'shop/observed.txt').read_text()
    prices = [(int(item, 16), int(value)) for item, value in re.findall(r'price item=([0-9A-F]+) value=(\d+)', text)]
    rom = Rom((out / 'shop.sfc').read_bytes())
    expected = [(item, price(rom, item)) for item in items]
    require(prices == expected and 'pc=06F49C' in text, f'상점 품목·가격 불일치: {prices}')
    results.append({'case': 'shop', 'items_and_prices': prices})
    save_json(out / 'results.json', results)
    return results


SHOP_KEY_PATCH = '35C37=A9{:02X}'  # 06:DC37 LDA $BC(맵 그룹을 키로) → LDA #키
NEW_KEY = 0x40  # 원본 무기점 목록에 없는 키


def shop_scene(name, rom, key, state, out, mesence, libdir):
    dest = out / name
    env = environment(libdir, state, dest)
    env.update(MODE='shop', DRIVER=str(HERE / 'lua/dq5msg.lua'), MAXF='900', POKE='7E36EB=01;7E370B=00',
               ROMPATCH=SHOP_KEY_PATCH.format(key),
               PRE='b:4,wait:40,up:3,wait:20,a:4,wait:30,a:4,wait:150,a:4,wait:80,a:4,wait:80')
    run(mesence, rom, HERE / 'lua/dq5progresscheck.lua', dest, env)
    text = (dest / 'observed.txt').read_text()
    require('pc=06F49C' in text, f'{name}: 상점 목록 검색을 거치지 않음')
    return [(int(item, 16), int(value)) for item, value in re.findall(r'price item=([0-9A-F]+) value=(\d+)', text)]


def shop_growth(original, state, out, mesence, libdir):
    """품목 수를 줄인 목록(원래 자리)과 새 키 목록(옮긴 자리)을 열고, 안 바꾼 목록이 그대로인지 본다."""
    data = dump(Rom(original.read_bytes()))
    weapons = [row for row in data['shops'] if row['kind'] == 2]
    first = next(row for row in weapons if row['key'] == 1)
    shorter, added = first['items'][:4], [0, 1, 2, 3, 4, 5]
    docs = {
        'inplace': ({'shops': [{'kind': 2, 'index': first['index'], 'items': shorter}]}, None),
        'moved': ({'shops': [{'kind': 2, 'index': len(weapons), 'key': NEW_KEY, 'items': added}]}, '0B:FBB0'),
    }
    roms = {'original': original}
    for name, (changes, at) in docs.items():
        source, manifest = out / f'shop-{name}.json', out / f'shop-{name}.patch.json'
        save_json(source, {'format': 'dq5progress/1', **changes})
        command('dq5progresswrite.py', original, 'patch', source, '-o', manifest, *(['--shop-at', at] if at else []))
        roms[name] = out / f'shop-{name}.sfc'
        command('dq5build.py', original, 'build', manifest, '-o', roms[name], '--ips', out / f'shop-{name}.ips')
    scenes = [('shop-key01-original', 'original', 1), ('shop-key01-inplace', 'inplace', 1),
              ('shop-key01-moved', 'moved', 1), ('shop-key40-moved', 'moved', NEW_KEY),
              ('shop-key1A-original', 'original', 0x1A), ('shop-key1A-moved', 'moved', 0x1A)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        seen = list(pool.map(lambda s: shop_scene(s[0], roms[s[1]], s[2], state, out, mesence, libdir), scenes))
    found = dict(zip((s[0] for s in scenes), seen))
    results = []
    for name, rom_name, key in scenes:
        rom = Rom(roms[rom_name].read_bytes())
        items = [item for item, _ in found[name]]
        require(found[name] == [(item, price(rom, item)) for item in items], f'{name}: 가격이 표와 다름')
        expected = {(1, 'original'): first['items'], (1, 'inplace'): shorter, (1, 'moved'): first['items'],
                    (NEW_KEY, 'moved'): added}.get((key, rom_name))
        if expected is not None:
            require(items == expected, f'{name}: 품목 {items} != {expected}')
        results.append({'case': name, 'rom': rom_name, 'key': key, 'items': items})
    require(found['shop-key1A-moved'] == found['shop-key1A-original'] and found['shop-key1A-original'],
            '옮긴 롬에서 안 바꾼 목록(키 1A)이 원본과 다름')
    return results


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/progresscheck')
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
        items = build_cases(original, out)
        prepare_battle(original, state, out, mesence, libdir)
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(lambda name: run_case(name, state, out, mesence, libdir), ('growth', 'encounter', 'shop')))
        results = verify(out, items)
        results += shop_growth(original, state, out, mesence, libdir)
        save_json(out / 'results.json', results)
        print(f'{len(results)}개 게임 검사 통과')
        print(json.dumps(results, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.output:
            print(error.output, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
