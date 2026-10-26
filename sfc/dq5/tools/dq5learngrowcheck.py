"""주문 습득 항목·목록을 늘리고 옮긴 롬을 MesenCE 에서 원본과 견준다.

동료 몬스터 종류 14(PARTY=0E)에게 필드 칸 2·전투 칸 6 을 새로 붙이고(ホイミ), 레벨 2 항목으로 배우게 한다.
습득 표·목록을 늘린 뱅크로 옮긴 롬(relocated)과 뱅크 23 안에서 다시 채운 롬(repacked)을 만들어
레벨업 습득, 필드·전투 사용, 주인공의 습득(사람 표), 몬스터 전투 창의 칸 8 을 원본 롬과 함께 돌린다.
원본 롬·선실 상태는 읽기만 하고 입력·패치·롬·기록은 --out 의 새 하위 폴더에 둔다.
  MESENCE=… python sfc/dq5/tools/dq5learngrowcheck.py rom/dq5.sfc --state work/state/ship.mss
"""
import argparse
import concurrent.futures
import copy
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import dq5learnwrite
from dq5build import build, parse_at
from dq5learnwrite import FORMAT, dump, layout, patch
from dq5map import Rom

HERE = Path(__file__).resolve().parent
KIND = 14
HOIMI = 0x27
# 시험용 자리. 다른 도구와 함께 빌드할 때는 겹치지 않는 곳을 고른다.
RELOCATE = {'learn_at': 0x3FC000, 'stub_at': 0x23FF20, 'lists_at': 0x3FD000}
# 동료 레코드는 일행 둘째(7E:206A). +4 MP, +10 최대 MP, +9 かしこさ, +23~+25 습득 비트, +26~+28 다음 레벨 경험치.
MON = 0x206A
FIRST_BITS = '01 03 00'
FIELD_TEST = 'wait:30,a:4,wait:30,right:4,wait:20,a:4,wait:40,down:4,wait:20,a:4,wait:40,down:4,wait:20,a:4,wait:40,a:4,wait:200'
BATTLE_PRE = 'wait:60,a:4,wait:30,a:4,wait:30,a:4,wait:30,down:4,wait:20,a:4,wait:40,down:4,wait:20,a:4,wait:60,a:4,wait:400'
WINDOW_PRE = 'wait:60,a:4,wait:30,a:4,wait:30,a:4,wait:30,down:4,wait:20,a:4,wait:60,down:4,wait:20,down:4,wait:20,right:4,wait:60'
CLEAR = ('ROMPATCH', 'SET', 'POKE', 'CALLS', 'PRE', 'LOOP', 'WAYPOINTS', 'WW', 'WWRANGE', 'WRAMWATCH', 'WRAMWATCHREAD',
         'COVER', 'ACCESS', 'VMADD', 'SHOTS', 'DUMP', 'VRAMDUMP', 'BG3FONT', 'SHOTMSG', 'BATTLE', 'FIELD', 'TO', 'PARTY',
         'WAGON', 'ADULT', 'ANYWHERE', 'SAVE', 'LATESET', 'TEST', 'INIT', 'READS', 'FRAMES', 'MODE', 'LEARNED')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def late(pairs):
    return ';'.join(f'{a:04X}={v:02X}' for a, v in pairs)


def bits_set(bits):
    return [(MON + 0x23 + i, b) for i, b in enumerate(bytes.fromhex(bits))]


def documents(original):
    rows = {(r['kind'], r['index']): r for r in original['characters']}
    mon = copy.deepcopy(rows['monster', KIND])
    first, rest = mon['learn'][0], mon['learn'][1:]
    grown = {'kind': 'monster', 'index': KIND, 'field': mon['field'] + [HOIMI], 'battle': mon['battle'] + [HOIMI],
             'learn': [first, {'level': 2, 'field_slots': [len(mon['field'])], 'battle_slots': [len(mon['battle'])]}, *rest]}
    # 뱅크 23 안에서 다시 채우려면 늘린 만큼 줄인다: 사람 5 의 마지막 항목(4바이트)·사람 10 의 전투 목록 둘(습득 항목 없음).
    shrink = [{'kind': 'person', 'index': 5, 'learn': rows['person', 5]['learn'][:-1]},
              {'kind': 'person', 'index': 10, 'battle': rows['person', 10]['battle'][:2]}]
    # 칸 8 시험: スライム(종류 2)의 전투 목록 9칸. 쓰기 도구는 몬스터 전투 8칸까지만 받으므로 이 롬만 한도를 풀어 만든다.
    slime = rows['monster', 2]
    cap = {'kind': 'monster', 'index': 2, 'battle': slime['battle'] + [0x28]}
    return {'relocated': ([grown], RELOCATE), 'repacked': ([grown, *shrink], {}),
            'cap': ([cap], {'lists_at': RELOCATE['lists_at']})}


def run(name, rom, out, mesence, libdir, state, driver, **env_extra):
    dest = out / name
    dest.mkdir()
    env = {k: v for k, v in os.environ.items() if k not in CLEAR}
    env.update(LIBDIR=libdir, STATE=str(state), SHOT_DIR=str(dest), DRIVER=str(HERE / 'lua' / driver), **env_extra)
    lua = HERE / ('lua/dq5warp.lua' if env_extra.get('SAVE') else 'lua/dq5learncheck.lua')
    with (dest / 'mesen.log').open('w', encoding='utf-8') as log:
        subprocess.run([str(mesence), '--testrunner', str(rom), str(lua), '--Snes.DisableFrameSkipping=true'],
                       env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
    return dest


def reads(dest):
    """observed.txt 의 「read 주소=값 pc=…」 줄을 겹치지 않게 「주소=값 pc=…」 로."""
    lines = (dest / 'observed.txt').read_text().splitlines()
    return sorted({line.removeprefix('read ') for line in lines if line.startswith('read ')})


def record(dest, base):
    ram = (dest / 'final.wram').read_bytes()
    return ram[base:base + 42]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/learngrowcheck')
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
        base = Rom(original.read_bytes())
        roms, slots = {'original': original}, {}
        for key, (rows, options) in documents(dump(base)).items():
            doc = {'format': FORMAT, 'characters': rows}
            (out / f'{key}.json').write_text(json.dumps(doc, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
            saved = dq5learnwrite.MONSTER_BATTLE
            try:
                if key == 'cap':
                    dq5learnwrite.MONSTER_BATTLE = 12
                else:
                    dq5learnwrite.check(base, doc, **options)
                manifest = patch(base, doc, **options)
            finally:
                dq5learnwrite.MONSTER_BATTLE = saved
            (out / f'{key}.patch.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
            writes = [(parse_at(w['at'])[0], bytes.fromhex(w['hex']), bytes.fromhex(w['orig']) if 'orig' in w else None,
                       w['note']) for w in manifest['writes']]
            size = manifest.get('rom_size', 0)
            data, _ = build(base.d, [(key, size, writes)], size)
            roms[key] = out / f'{key}.sfc'
            roms[key].write_bytes(data)
            parts = layout(Rom(data))
            mon = parts['monster', KIND]
            slots[key] = {'field': mon['field'][0] + len(mon['field'][1]) - 1,
                          'battle': mon['battle'][0] + len(mon['battle'][1]) - 1,
                          'slime7': parts['monster', 2]['battle'][0] + 8, 'slime8': parts['monster', 2]['battle'][0] + 9}
        libdir = subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True,
                                check=True, timeout=30).stdout.strip()
        cases = ('original', 'relocated', 'repacked')

        def prepare(name, rom, sets, party=True):
            extra = {'PARTY': f'{KIND:02X}'} if party else {}
            dest = run(name, roms[rom], out, mesence, libdir, state, 'dq5warp.lua', FIELD='341,56', BATTLE='00:1',
                       SETTLE='300', SAVE='battle.mss', MAXF='1800', LATESET=late(sets), **extra)
            require((dest / 'battle.mss').is_file(), f'{name}: 전투 상태 생성 실패')
            return dest / 'battle.mss'

        def level(rom):
            start = prepare(f'level-{rom}-prep', rom, bits_set(FIRST_BITS) + [(MON + 0x26, 1), (MON + 0x27, 0), (MON + 0x28, 0)])
            dest = run(f'level-{rom}', roms[rom], out, mesence, libdir, start, 'dq5battle.lua', MODE='level',
                       MAXF='2400', LOOP='a:4,wait:20', PEEK='7E2040:84')
            mon = record(dest, MON)
            return {'level': mon[0x12], 'bits': mon[0x23:0x26].hex(' '),
                    'learn_messages': (dest / 'battle.txt').read_text().count('msg 0C7')}

        def hero(rom):
            start = prepare(f'hero-{rom}-prep', rom, [], party=False)
            dest = run(f'hero-{rom}', roms[rom], out, mesence, libdir, start, 'dq5battle.lua', MODE='level',
                       INIT='2052=03', MAXF='2400', LOOP='a:4,wait:20', PEEK='7E2040:42')
            h = record(dest, 0x2040)
            return {'level': h[0x12], 'bits': h[0x23:0x26].hex(' '),
                    'learn_messages': (dest / 'battle.txt').read_text().count('msg 0C7')}

        def use(rom, where, bits):
            sets = bits_set(bits) + [(MON + 4, 100), (MON + 5, 0), (MON + 0x10, 100), (MON + 0x11, 0), (0x2042, 5), (0x2043, 0)]
            watch = f'{slots.get(rom, slots["relocated"])[where]:06X}'
            if where == 'field':
                dest = run(f'field-{rom}', roms[rom], out, mesence, libdir, state, 'dq5warp.lua', MODE='join',
                           FIELD='341,56', PARTY=f'{KIND:02X}', LATESET=late(sets), TEST=FIELD_TEST, MAXF='1500',
                           READS=watch)
            else:
                # かしこさ 가 낮은 동료는 めいれいさせろ 에서도 명령을 따르지 않을 때가 있어 99 로 둔다.
                start = prepare(f'battle-{rom}-prep', rom, sets + [(MON + 9, 99)])
                dest = run(f'battle-{rom}', roms[rom], out, mesence, libdir, start, 'dq5battle.lua', MODE='join',
                           PRE=BATTLE_PRE, LOOP='wait:500', MAXF='700', PEEK='7E2040:84', READS=watch)
            h, mon = record(dest, 0x2040), record(dest, MON)
            return {'hero_hp': int.from_bytes(h[2:4], 'little'), 'mp': int.from_bytes(mon[4:6], 'little'),
                    'reads': reads(dest)}

        def window():
            # スライム 은 칸 7·8 만 배운 상태로 둔다. 칸 8 이 창에 나오면 21:9D00 이 그 바이트를 읽는다.
            dest_prep = run('window-prep', roms['cap'], out, mesence, libdir, state, 'dq5warp.lua', FIELD='341,56',
                            BATTLE='00:1', SETTLE='300', SAVE='battle.mss', MAXF='1800', PARTY='02',
                            LATESET=late([(MON + 0x23, 0), (MON + 0x24, 0x80), (MON + 0x25, 1)]))
            dest = run('window', roms['cap'], out, mesence, libdir, dest_prep / 'battle.mss', 'dq5battle.lua',
                       MODE='join', PRE=WINDOW_PRE, LOOP='wait:500', MAXF='400', FRAMES='399',
                       READS=f'{slots["cap"]["slime7"]:06X},{slots["cap"]["slime8"]:06X}')
            return {'reads': reads(dest)}

        jobs = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            for rom in cases:
                jobs['level', rom] = pool.submit(level, rom)
                jobs['hero', rom] = pool.submit(hero, rom)
            jobs['window', 'cap'] = pool.submit(window)
            got = {key: job.result() for key, job in jobs.items()}
            learned = got['level', 'relocated']['bits'].replace(' ', '')
            for rom in cases:
                for where in ('field', 'battle'):
                    jobs[where, rom] = pool.submit(use, rom, where, learned)
            got.update({key: job.result() for key, job in jobs.items() if key not in got})
        new_bits = '05 43 00'
        expect = {
            ('level', 'original'): lambda r: r['level'] == 2 and r['bits'] == FIRST_BITS and r['learn_messages'] == 0,
            ('hero', 'original'): lambda r: r['level'] == 4 and r['bits'] == '01 01 00' and r['learn_messages'] == 1,
            ('field', 'original'): lambda r: r['mp'] == 100 and r['hero_hp'] == 5,
            ('battle', 'original'): lambda r: r['mp'] == 100,
            ('window', 'cap'): lambda r: any(s.startswith(f'{slots["cap"]["slime7"]:06X}=') for s in r['reads'])
            and not any(s.startswith(f'{slots["cap"]["slime8"]:06X}=') for s in r['reads']),
        }
        for rom in ('relocated', 'repacked'):
            expect['level', rom] = lambda r: r['level'] == 2 and r['bits'] == new_bits and r['learn_messages'] == 1
            expect['hero', rom] = lambda r: r['level'] == 4 and r['bits'] == '01 01 00' and r['learn_messages'] == 1
            for where, pc in (('field', '21:9BAA'), ('battle', '21:9D00')):
                address = f'{slots[rom][where]:06X}={HOIMI:02X}'
                expect[where, rom] = (lambda a: lambda r: r['mp'] == 97 and r['hero_hp'] > 5
                                      and a in r['reads'])(f'{address} pc={pc}')
        results = [{'scene': scene, 'rom': rom, **value, 'passed': bool(expect[scene, rom](value))}
                   for (scene, rom), value in got.items()]
        (out / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        for r in results:
            print(json.dumps(r, ensure_ascii=False))
        failed = [f'{r["scene"]}-{r["rom"]}' for r in results if not r['passed']]
        require(not failed, f'불일치: {", ".join(failed)}')
        print(f'{len(results)}개 장면 통과')
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.output:
            print(error.output, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
