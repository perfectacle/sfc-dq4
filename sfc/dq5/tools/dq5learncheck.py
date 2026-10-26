"""새 주문의 레벨업 습득과 필드·전투 목록 실행을 MesenCE에서 확인한다.

원본 ROM/선실 상태는 읽기만 하며 입력·IPS·로그·화면은 --out의 새 하위 폴더에 저장한다.
  MESENCE=… python sfc/dq5/tools/dq5learncheck.py rom/dq5.sfc --state work/state/ship.mss
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from dq5learnwrite import FORMAT, dump
from dq5map import Rom

HERE = Path(__file__).resolve().parent
# (몬스터 번호, 동료 종류, 동료 확률 등급) — 처음 레벨 1 인 スライムナイト 와 3 인 キメラ.
JOINS = ((0x26, 7, 5), (0x5E, 17, 4))
# 20:8000 bit0 이 합류 앞의 플래그·레벨 검사를 건너뛰고, 27:8162 워드 표가 등급마다 1/N 의 N 이다.
JOIN_PATCH = '100000=01;{:06X}=0100'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def command(tool, rom, *args):
    subprocess.run([sys.executable, str(HERE / tool), str(rom), *map(str, args)],
                   check=True, capture_output=True, text=True, timeout=60)


def run(name, state, driver, rom, out, mesence, libdir, **options):
    dest = out / name
    dest.mkdir()
    env = os.environ.copy()
    for key in ('ROMPATCH', 'SET', 'POKE', 'CALLS', 'PRE', 'LOOP', 'WAYPOINTS', 'WW', 'WWRANGE',
                'WRAMWATCH', 'WRAMWATCHREAD', 'COVER', 'ACCESS', 'VMADD', 'SHOTS', 'DUMP', 'VRAMDUMP',
                'BG3FONT', 'SHOTMSG', 'BATTLE', 'FIELD', 'TO', 'PARTY', 'WAGON', 'ADULT', 'ANYWHERE',
                'SAVE', 'LATESET', 'TEST'):
        env.pop(key, None)
    env.update(LIBDIR=libdir, STATE=str(state), SHOT_DIR=str(dest), DRIVER=str(HERE / 'lua' / driver), **options)
    lua = HERE / ('lua/dq5warp.lua' if driver == 'dq5warp.lua' else 'lua/dq5learncheck.lua')
    with (dest / 'mesen.log').open('w', encoding='utf-8') as log:
        subprocess.run([str(mesence), '--testrunner', str(rom), str(lua), '--Snes.DisableFrameSkipping=true'],
                       env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=90)
    return dest


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/learncheck')
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
        hero = dump(Rom(original.read_bytes()))['characters'][0]
        hero['learn'][0]['level'] = 2
        hero['field'][0] = hero['battle'][0] = 0x28
        source, manifest, rom = out / 'input.json', out / 'patch.json', out / 'learn.sfc'
        save(source, {'format': FORMAT, 'characters': [hero]})
        command('dq5learnwrite.py', original, 'patch', source, '-o', manifest)
        command('dq5learnwrite.py', original, 'check', source)
        command('dq5build.py', original, 'build', manifest, '-o', rom, '--ips', out / 'learn.ips')
        libdir = subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True,
                                check=True, timeout=30).stdout.strip()
        prep = run('prepare', state, 'dq5warp.lua', rom, out, mesence, libdir,
                   FIELD='341,56', BATTLE='00:1', SETTLE='300', SAVE='battle.mss', MAXF='1800')
        require((prep / 'battle.mss').is_file(), '전투 상태 생성 실패')
        level = run('level', prep / 'battle.mss', 'dq5battle.lua', rom, out, mesence, libdir,
                    MODE='level', MAXF='2400', LOOP='a:4,wait:20', PEEK='7E2040:42')
        ram = (level / 'final.wram').read_bytes()
        bits = ram[0x2063:0x2066]
        require(ram[0x2052] == 2 and bits == bytes([1, 1, 0]), '레벨/습득 슬롯 불일치')
        require('msg 0C7' in (level / 'battle.txt').read_text(), '주문 습득 메시지가 없음')
        results = [{'case': 'learn', 'level': 2, 'learned_bits': bits.hex()}]
        for name, start, driver, pre in (
                ('field', state, 'dq5msg.lua', 'b:4,wait:40,a:4,wait:30,right:4,wait:20,a:4,wait:40,a:4,wait:40,a:4,wait:200'),
                ('battle', prep / 'battle.mss', 'dq5battle.lua', 'a:4,wait:30,down:4,wait:20,a:4,wait:40,a:4,wait:40,a:4,wait:200')):
            dest = run(name, start, driver, rom, out, mesence, libdir, MODE=name, LEARNED=bits.hex(),
                       MAXF='650', PRE=pre, LOOP='wait:500', PEEK='7E2040:42')
            observed = (dest / 'observed.txt').read_text()
            require(('23BE28=28 pc=21:9BAA' if name == 'field' else '23BE31=28 pc=21:9D00') in observed,
                    f'{name}: 바뀐 주문 목록을 읽지 않음')
            ram = (dest / 'final.wram').read_bytes()
            if name == 'battle':
                match = re.search(r'msg 094 7E2040=([0-9A-F]{84})', (dest / 'battle.txt').read_text())
                require(match is not None, '전투 회복 메시지가 없음')
                record = bytes.fromhex(match[1])
                hp, mp = int.from_bytes(record[2:4], 'little'), int.from_bytes(record[4:6], 'little')
            else:
                hp, mp = int.from_bytes(ram[0x2042:0x2044], 'little'), int.from_bytes(ram[0x2044:0x2046], 'little')
            require(80 <= hp <= 100 and mp == 95, f'{name}: 베호이미 회복/MP 불일치 {hp}/{mp}')
            results.append({'case': name, 'spell': 0x28, 'hp_set': 5, 'hp_after': hp, 'mp_set': 100, 'mp_after': mp})
        original_doc = dump(Rom(original.read_bytes()))
        for monster, kind, grade in JOINS:
            row = next(r for r in original_doc['characters'] if r['kind'] == 'monster' and r['index'] == kind)
            first = row['learn'][0]
            changed = {**first, 'field_slots': [1], 'battle_slots': [2]}
            weak = out / f'join{kind}-weak.json'
            save(weak, {'format': 'dq5tables/1', 'monsters': [{'id': f'{monster:02X}', 'HP': 1, '공격': 0, '민첩': 0}]})
            command('dq5tables.py', original, 'patch', weak, '-o', out / f'join{kind}-weak.patch.json')
            learn = out / f'join{kind}-learn.json'
            save(learn, {'format': FORMAT, 'characters': [{'kind': 'monster', 'index': kind,
                                                            'learn': [changed, *row['learn'][1:]]}]})
            command('dq5learnwrite.py', original, 'patch', learn, '-o', out / f'join{kind}-learn.patch.json')
            for label, manifests, entry in (('original', [f'join{kind}-weak.patch.json'], first),
                                           ('patched', [f'join{kind}-weak.patch.json', f'join{kind}-learn.patch.json'], changed)):
                target = out / f'join{kind}-{label}.sfc'
                command('dq5build.py', original, 'build', *(out / m for m in manifests), '-o', target)
                name = f'join{kind}-{label}'
                start = run(f'{name}-prepare', state, 'dq5warp.lua', target, out, mesence, libdir, FIELD='341,56',
                            BATTLE=f'{monster:02X}:1', SETTLE='300', SAVE='battle.mss', MAXF='1800')
                dest = run(name, start / 'battle.mss', 'dq5battle.lua', target, out, mesence, libdir, MODE='join',
                           MAXF='4000', LOOP='a:4,wait:20', ROMPATCH=JOIN_PATCH.format(0x138162 + grade * 2))
                ram = (dest / 'final.wram').read_bytes()
                records = [ram[0x2040 + k * 42:0x2040 + (k + 1) * 42] for k in range(4)]
                joined = [r for r in records if r[0] == 0x80 | kind]
                require(len(joined) == 1, f'{name}: 동료가 되지 않음')
                mask = sum(1 << s for s in entry['field_slots']) | sum(1 << (s + 8) for s in entry['battle_slots'])
                level, bits = joined[0][0x12], joined[0][0x23:0x26]
                require(level == first['level'] and bits == mask.to_bytes(3, 'little'),
                        f'{name}: 합류 레벨/습득 비트 불일치 {level} {bits.hex()}')
                results.append({'case': name, 'monster': monster, 'kind': kind, 'level': level, 'learned_bits': bits.hex()})
        save(out / 'results.json', results)
        print(json.dumps(results, ensure_ascii=False))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.output:
            print(error.output, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
