"""늘린 행동 번호 AB(ホイミ 를 베낀 새 주문)를 배우고 필드·전투에서 쓰는 것을 MesenCE 에서 확인한다.

형식은 sfc/dq5/docs/dq5-build-format.md 의 「행동 번호 늘리기」. 롬 두 벌을 만든다.
  grow   dq5spellgrow.py(AB = 27 베낌) + dq5namewrite.py --append(표 3 의 AB 이름) + 주인공 습득 레벨 2
         + 주인공 필드·전투 목록 첫 칸을 AB 로(dq5learnwrite.py --spells-from 으로 늘린 번호를 받음)
  base   위에서 dq5spellgrow·이름만 뺀 대조 롬(목록에는 AB 가 있지만 표는 원래 171개)
주인공을 레벨 2 로 올려 배우게 하고, 필드 じゅもん 과 전투 じゅもん 으로 외운다. 원본 롬·선실 상태는 읽기만 한다.

  MESENCE=… python sfc/dq5/tools/dq5spellgrowcheck.py rom/dq5.sfc --state work/state/ship.mss
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from dq5learnwrite import FORMAT as LEARN_FORMAT, dump as learn_dump
from dq5map import Rom
from dq5namewrite import read_tables
from dq5progresscheck import command, environment, require, run, save_json
from dq5spellgrow import FIELD_STUB, HANDLER_STUB, TABLES

HERE = Path(__file__).resolve().parent
AT = '6E:8000'
NAMES_AT = '6F:8000'
NEW, COPY = 0xAB, 0x27
FIELD_USE = 'b:4,wait:40,a:4,wait:30,right:4,wait:20,a:4,wait:40,a:4,wait:40,a:4,wait:200'
BATTLE_USE = 'a:4,wait:30,down:4,wait:20,a:4,wait:40,a:4,wait:40,a:4,wait:200'


def build(original, out):
    data = original.read_bytes()
    save_json(out / 'grow.json', {'format': 'dq5spellgrow/1', 'spells': [{'id': f'{NEW:02X}', 'copy': f'{COPY:02X}'}]})
    command('dq5spellgrow.py', original, 'check', out / 'grow.json', '--at', AT)
    command('dq5spellgrow.py', original, 'patch', out / 'grow.json', '--at', AT, '-o', out / 'grow.patch.json')
    command('dq5build.py', original, 'build', out / 'grow.patch.json', '-o', out / 'spells.sfc')
    hero = learn_dump(Rom(data))['characters'][0]
    hero['learn'][0]['level'] = 2
    hero['field'][0] = hero['battle'][0] = NEW
    save_json(out / 'learn.json', {'format': LEARN_FORMAT, 'characters': [hero]})
    command('dq5learnwrite.py', original, 'check', out / 'learn.json', '--spells-from', out / 'spells.sfc')
    command('dq5learnwrite.py', original, 'patch', out / 'learn.json', '-o', out / 'learn.patch.json',
            '--spells-from', out / 'spells.sfc')
    name = read_tables(data)[3][COPY]
    save_json(out / 'names.json', {'format': 'dq5names/1', 'tables': [{'table': 3, 'names': [{'id': NEW, 'bytes': name + name[-1:]}]}]})
    command('dq5namewrite.py', original, 'check', out / 'names.json', '--at', NAMES_AT, '--append')
    command('dq5namewrite.py', original, 'patch', out / 'names.json', '--at', NAMES_AT, '--append', '-o', out / 'names.patch.json')
    for rom, parts in (('grow', ('learn', 'grow', 'names')), ('base', ('learn',))):
        command('dq5build.py', original, 'build', *[out / f'{p}.patch.json' for p in parts], '-o', out / f'{rom}.sfc',
                '--ips', out / f'{rom}.ips')


def places():
    """옮긴 표에서 AB 칸의 CPU 주소. 표 여섯은 AT 부터 차례로 원래 171개 + 1개씩 놓인다."""
    bank, low = (int(v, 16) for v in AT.split(':'))
    at, out = bank << 16 | low, {}
    for name, (_, size, _) in TABLES.items():
        out[name] = at + NEW * size
        at += (NEW + 1) * size
    return out


def scene(name, rom, state, out, mesence, libdir, mode, driver, **options):
    dest = out / name
    env = environment(libdir, state, dest)
    at = places()
    env.update(MODE=mode, DRIVER=str(HERE / 'lua' / driver), **options,
               READS=','.join(f'{a:06X}' for a in at.values()),
               EXECS=f'{HANDLER_STUB:06X},{FIELD_STUB:06X},248C39,248BAF')
    run(mesence, rom, HERE / 'lua/dq5spellgrowcheck.lua', dest, env)
    text = (dest / 'observed.txt').read_text()
    require('truncated' not in text, f'{name}: 관측 기록이 잘림')
    return text, (dest / 'final.wram').read_bytes()


def messages(text, pc):
    return [m for m in re.findall(rf'pc={pc} A=0([0-9A-F]{{3}})', text)]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/spellgrowcheck')
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
        libdir = subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True, check=True, timeout=30).stdout.strip()
        build(original, out)
        prep = out / 'prepare'
        env = environment(libdir, state, prep)
        env.update(FIELD='341,56', BATTLE='00:1', SETTLE='300', SAVE='battle.mss', MAXF='1800')
        run(mesence, out / 'grow.sfc', HERE / 'lua/dq5warp.lua', prep, env)
        battle = prep / 'battle.mss'
        require(battle.is_file(), '전투 상태 생성 실패')
        at = places()
        results = {}

        text, ram = scene('grow-level', out / 'grow.sfc', battle, out, mesence, libdir, 'level', 'dq5battle.lua',
                          MAXF='1300', LOOP='a:4,wait:20', SHOTMSG='19F')
        said = messages(text, '248C39')
        require(ram[0x2052] == 2 and ram[0x2063:0x2066] == bytes([1, 1, 0]) and '19F' in said,
                f'레벨업 습득: 레벨 {ram[0x2052]}, 비트 {ram[0x2063:0x2066].hex()}, 메시지 {said}')
        require(f'read {at["menu_mp"]:06X}=' in text, '습득 메시지에서 옮긴 주문 목록 MP 표를 읽지 않음')
        results['습득'] = {'레벨': 2, '비트': '010100', '메시지': '19F'}

        for rom in ('grow', 'base'):
            text, ram = scene(f'{rom}-field', out / f'{rom}.sfc', state, out, mesence, libdir, 'field', 'dq5msg.lua',
                              LEARNED='010100', MAXF='650', PRE=FIELD_USE, SHOTS='160')
            hp, mp = int.from_bytes(ram[0x2042:0x2044], 'little'), int.from_bytes(ram[0x2044:0x2046], 'little')
            if rom == 'grow':
                require(f'pc={FIELD_STUB:06X}' in text and f'read {at["menu_mp"]:06X}=03' in text and hp > 5 and mp == 97,
                        f'grow 필드: 스텁·목록 MP 를 거치지 않거나 HP {hp}·MP {mp}')
            else:
                require(hp == 5 and mp == 100, f'base 필드: 외워짐 HP {hp}·MP {mp}')
            results[f'{rom} 필드'] = {'HP': [5, hp], 'MP': [100, mp], '메시지': messages(text, '248BAF')}

            text, ram = scene(f'{rom}-battle', out / f'{rom}.sfc', battle, out, mesence, libdir, 'battle', 'dq5battle.lua',
                              LEARNED='010100', MAXF='650', PRE=BATTLE_USE, LOOP='wait:500', PEEK='7E2040:42')
            said = re.findall(r'msg ([0-9A-F]{3}) 7E2040=([0-9A-F]{84})', (out / f'{rom}-battle' / 'battle.txt').read_text())
            codes = [m for m, _ in said]
            if rom == 'grow':
                record = bytes.fromhex(next(r for m, r in said if m == '094'))
                hp, mp = int.from_bytes(record[2:4], 'little'), int.from_bytes(record[4:6], 'little')
                require(codes[:2] == ['070', '094'] and hp > 5 and mp == 97, f'grow 전투: {codes} HP {hp} MP {mp}')
                require(f'pc={HANDLER_STUB:06X} A=0156 X=0156' in text
                        and all(f'read {at[k]:06X}' in text for k in ('flags', 'executor', 'executor_alt')),
                        'grow 전투: 처리 루틴 스텁이나 옮긴 표를 거치지 않음')
                results['grow 전투'] = {'메시지': codes[:2], 'HP': hp, 'MP': mp}
            else:
                require('094' not in codes and '070' not in codes, f'base 전투: 주문이 걸림 {codes}')
                results['base 전투'] = {'메시지': codes}
        save_json(out / 'results.json', results)
        print('7회 실행, 새 행동 AB 의 습득·필드·전투 게임 검사 통과')
        print(json.dumps(results, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, StopIteration, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.output:
            print(error.output, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
