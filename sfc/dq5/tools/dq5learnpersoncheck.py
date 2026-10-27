"""사람이 일행에 들 때의 습득 비트와 사람 주문 목록을 늘린 롬을 MesenCE 에서 원본과 견준다.

선실 파파스의 대화 스크립트를 네이티브 06:F646(ビアンカ 를 21:8042 로 일행에 넣음)을 부르게 바꿔 말을 건다.
롬 넷: 그대로, 습득 표의 ビアンカ 항목 슬롯만 바꿈, 인물 레코드 표 23:C014 칸 3 의 습득 비트만 바꿈(dq5learnwrite 의 join),
ビアンカ 필드 목록에 ベホイミ 를 붙이고 레벨 11 항목으로 배우게 한 뒤 습득 표·목록을 뱅크 3F 로 옮김.
일행에 든 레코드, 그때 23:EB50 이 불리는지, 레벨 10→11 습득, 필드에서 새 칸 쓰기를 본다.
원본 롬·선실 상태는 읽기만 하고 입력·패치·롬·기록은 --out 의 새 하위 폴더에 둔다.
  MESENCE=… python sfc/dq5/tools/dq5learnpersoncheck.py rom/dq5.sfc --state work/state/ship.mss
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

from dq5learnwrite import JOIN, JOIN_SIZE, dump, layout
from dq5map import Rom

HERE = Path(__file__).resolve().parent
BIANCA = 3
RECORD = 0x206A                    # 일행 레코드 1
RELOCATE = ['--learn-at', '3F:C000', '--stub-at', '23:FF20', '--lists-at', '3F:D000']
TALK_PRE = 'b:4,wait:40,up:3,wait:20,a:4,wait:30,a:4,wait:150' + ',a:4,wait:100' * 9
FIELD_TEST = 'wait:30,a:4,wait:30,right:4,wait:20,a:4,wait:40,down:4,wait:20,a:4,wait:40,a:4,wait:40,a:4,wait:200'
PARTY = [(0x201D, 2), (0x201E, 2), (0x201F, 2), (0x2020, 0), (0x2021, 1), (0x2028, 0), (0x2029, 1)]
CLEAR = ('ROMPATCH', 'SET', 'POKE', 'CALLS', 'PRE', 'LOOP', 'DUMP', 'SHOTS', 'LOG', 'BATTLE', 'FIELD', 'TO', 'PARTY',
         'LATESET', 'TEST', 'INIT', 'READS', 'FRAMES', 'MODE', 'SAVE', 'SETTLE', 'PEEK')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def tool(name, *args):
    subprocess.run([sys.executable, str(HERE / name), *map(str, args)], check=True, capture_output=True,
                   text=True, timeout=120)


def documents(original):
    rows = {(r['kind'], r['index']): r for r in original['characters']}
    bianca = rows['person', BIANCA]
    moved = copy.deepcopy(bianca['learn'])
    for k, row in enumerate(moved[:4]):
        row['battle_slots'] = [4 + k]
    learn = [*bianca['learn'][:4], {'level': 11, 'field_slots': [len(bianca['field'])], 'battle_slots': []},
             *bianca['learn'][4:]]
    return {
        'table': ({'format': 'dq5learn/1', 'characters': [{'kind': 'person', 'index': BIANCA, 'learn': moved}]}, []),
        'join': ({'format': 'dq5learn/1', 'characters': [],
                  'join': [{'entry': BIANCA, 'field_slots': [0], 'battle_slots': [4]}]}, []),
        'grown': ({'format': 'dq5learn/1', 'characters': [{'kind': 'person', 'index': BIANCA,
                                                            'field': bianca['field'] + [0x28], 'learn': learn}]},
                  RELOCATE),
    }


def late(rom, exp=None, bits=None, extra=()):
    rec = bytearray(rom.u8(JOIN + BIANCA * JOIN_SIZE + i) for i in range(JOIN_SIZE))
    if exp is not None:
        rec[0x26:0x29] = exp
    if bits is not None:
        rec[0x23:0x26] = bits
        rec[4:6] = rec[0x10:0x12] = (100).to_bytes(2, 'little')
    sets = [(RECORD + i, v) for i, v in enumerate(rec)] + PARTY + list(extra)
    return ';'.join(f'{a:04X}={v:02X}' for a, v in sets)


def run(name, rom, out, mesence, libdir, state, lua, **extra):
    dest = out / name
    dest.mkdir()
    env = {k: v for k, v in os.environ.items() if k not in CLEAR}
    env.update(LIBDIR=libdir, STATE=str(state), SHOT_DIR=str(dest), **extra)
    with (dest / 'mesen.log').open('w', encoding='utf-8') as log:
        subprocess.run([str(mesence), '--testrunner', str(rom), str(HERE / 'lua' / lua),
                        '--Snes.DisableFrameSkipping=true'], env=env, stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=180)
    return dest


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/learnpersoncheck')
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
        talk = out / 'talk.json'
        talk.write_text(json.dumps({'format': 'dq5talk/1', 'scripts': [
            {'talk': '012', 'body': [{'op': 'call', 'target': 'F646'}]}]}) + '\n', encoding='utf-8')
        tool('dq5talkwrite.py', original, 'patch', talk, '-o', out / 'talk.patch.json')
        roms = {'original': original}
        roms['base'] = out / 'base.sfc'
        tool('dq5build.py', original, 'build', out / 'talk.patch.json', '-o', roms['base'])
        for key, (doc, options) in documents(dump(Rom(original.read_bytes()))).items():
            source = out / f'{key}.json'
            source.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
            tool('dq5learnwrite.py', original, 'check', source, *options)
            tool('dq5learnwrite.py', original, 'patch', source, '-o', out / f'{key}.patch.json', *options)
            roms[key] = out / f'{key}.sfc'
            tool('dq5build.py', original, 'build', out / 'talk.patch.json', out / f'{key}.patch.json', '-o', roms[key])
        libdir = subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True,
                                check=True, timeout=30).stdout.strip()
        grown = Rom(roms['grown'].read_bytes())
        new_slot = layout(grown)['person', BIANCA]['field']
        new_slot = new_slot[0] + len(new_slot[1]) - 1

        def join(rom):
            dest = run(f'join-{rom}', roms[rom], out, mesence, libdir, state, 'dq5msg.lua', MAXF='1300',
                       CALLS='218042,23EB50', DUMP='1300:7E201D:1,1300:7E206A:42', PRE=TALK_PRE)
            lines = (dest / 'msg.txt').read_text().splitlines()
            dumps = [bytes.fromhex(''.join(line.split()[3:])) for line in lines if ' dump ' in line]
            record = dumps[1]
            table = bytes(Rom(roms[rom].read_bytes()).u8(JOIN + BIANCA * JOIN_SIZE + i) for i in range(JOIN_SIZE))
            return {'joined': any('218042' in line for line in lines),
                    'learn_routine': sum('23EB50' in line for line in lines), 'party': dumps[0][0],
                    'bits': record[0x23:0x26].hex(' '), 'record_is_table': record == table}

        def level(rom):
            source = Rom(roms[rom].read_bytes())
            prep = run(f'level-{rom}-prep', roms[rom], out, mesence, libdir, state, 'dq5warp.lua', FIELD='341,56',
                       BATTLE='00:1', SETTLE='300', SAVE='battle.mss', MAXF='1800', LATESET=late(source, exp=b'\x01\x00\x00'))
            dest = run(f'level-{rom}', roms[rom], out, mesence, libdir, prep / 'battle.mss', 'dq5learncheck.lua',
                       DRIVER=str(HERE / 'lua/dq5battle.lua'), MODE='level', MAXF='2400', LOOP='a:4,wait:20',
                       PEEK='7E206A:42')
            rec = (dest / 'final.wram').read_bytes()[RECORD:RECORD + JOIN_SIZE]
            return {'level': rec[0x12], 'bits': rec[0x23:0x26].hex(' '),
                    'learn_messages': (dest / 'battle.txt').read_text().count('msg 0C7')}

        def field(rom):
            source = Rom(roms[rom].read_bytes())
            dest = run(f'field-{rom}', roms[rom], out, mesence, libdir, state, 'dq5learncheck.lua',
                       DRIVER=str(HERE / 'lua/dq5warp.lua'), MODE='join', FIELD='341,56', TEST=FIELD_TEST, MAXF='1500',
                       LATESET=late(source, bits=b'\x02\x0f\x00', extra=[(0x2042, 5), (0x2043, 0)]),
                       READS=f'{new_slot:06X}')
            ram = (dest / 'final.wram').read_bytes()
            reads = sorted({line.removeprefix('read ') for line in (dest / 'observed.txt').read_text().splitlines()
                            if line.startswith('read ')})
            return {'hero_hp': int.from_bytes(ram[0x2042:0x2044], 'little'),
                    'mp': int.from_bytes(ram[RECORD + 4:RECORD + 6], 'little'), 'reads': reads}

        jobs = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            for rom in ('base', 'table', 'join', 'grown'):
                jobs['join', rom] = pool.submit(join, rom)
            for rom in ('original', 'grown'):
                jobs['level', rom] = pool.submit(level, rom)
                jobs['field', rom] = pool.submit(field, rom)
            got = {key: job.result() for key, job in jobs.items()}
        joined = lambda bits: lambda r: (r['joined'] and r['learn_routine'] == 0 and r['party'] == 2
                                         and r['record_is_table'] and r['bits'] == bits)
        read = f'{new_slot:06X}=28 pc=21:9BAA'
        expect = {
            ('join', 'base'): joined('00 0f 00'), ('join', 'table'): joined('00 0f 00'),
            ('join', 'join'): joined('01 10 00'), ('join', 'grown'): joined('00 0f 00'),
            ('level', 'original'): lambda r: r['level'] == 11 and r['bits'] == '00 0f 00' and r['learn_messages'] == 0,
            ('level', 'grown'): lambda r: r['level'] == 11 and r['bits'] == '02 0f 00' and r['learn_messages'] == 1,
            ('field', 'original'): lambda r: r['hero_hp'] == 5 and r['mp'] == 100,
            ('field', 'grown'): lambda r: r['hero_hp'] > 5 and r['mp'] == 95 and read in r['reads'],
        }
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
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
