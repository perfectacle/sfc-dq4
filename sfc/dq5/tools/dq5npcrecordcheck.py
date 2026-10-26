"""인물 레코드·조건 표 쓰기를 MesenCE에서 확인한다.

02/06 기본 목록의 인물 둘을 고친 롬(밤 인물을 낮으로 바꿔 주인공 두 칸 위에 새 대화 번호로,
다른 인물은 그림만)과 02/06 대체 목록 조건을 뒤집은 롬, 같은 문서를 dq5npcrelocate.py --records 로
옮긴 롬을 원본과 함께 돌린다. 인물 목록 로더 직후(12:803C) WRAM 인물 표 23칸을 롬에서 예측한 값과 견주고,
주인공이 위 칸에 말을 걸었을 때 메시지 루틴(24:8BAF)이 받은 번호를 본다.
원본 롬·선실 상태는 읽기만 하고 출력은 --out 의 새 하위 폴더에 둔다.
  MESENCE=… python sfc/dq5/tools/dq5npcrecordcheck.py rom/dq5.sfc --state work/state/ship.mss
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dq5map import Rom  # noqa: E402
from dq5npc import FLAGS, list_address, list_entries, parse, table_values  # noqa: E402

HERE = Path(__file__).resolve().parent
TALK = 0x300            # 26D 이상은 메시지 T + 3C6 을 바로 띄운다(06:AFFB)
MESSAGE = TALK + 0x3C6
# 02/06 기본 목록(05:8CD4): 밤 인물 하나를 낮으로 옮겨 주인공 두 칸 위에 세우고, 낮 인물 하나는 그림만 바꾼다.
MOVED, REDRAWN, NIGHT = 0x058D34, 0x058D0B, 0x058D2C
HERO = '02/06,24,14,1'
ENTRIES = [{'list': '05:8CD4', 'index': 3, 'time': 'day',
            'fields': {'x': 24, 'y': 12, 'facing': 'down', 'gfx': 0x18, 'talk': TALK}},
           {'list': '05:8CD4', 'index': 1, 'fields': {'gfx': 0x18}}]
TALK_TEST = 'up:40,wait:40,a:4,wait:60,a:4,wait:200'
# (이름, 롬, 밤, TEST). edited 는 레코드만, relocated 는 같은 문서를 dq5npcrelocate.py --records 로,
# condition 은 02/06 의 21AD bit4 대체 조건을 「꺼졌을 때」로 뒤집은 롬.
CASES = [
    ('day-original', 'original', False, TALK_TEST),
    ('day-edited', 'edited', False, TALK_TEST),
    ('day-relocated', 'relocated', False, TALK_TEST),
    ('night-original', 'original', True, ''),
    ('night-edited', 'edited', True, ''),
    ('condition-original', 'original', False, ''),
    ('condition-edited', 'condition', False, ''),
]


def require(ok, message):
    if not ok:
        raise ValueError(message)


def command(tool, rom, *args):
    subprocess.run([sys.executable, str(HERE / tool), str(rom), *map(str, args)],
                   check=True, capture_output=True, text=True, timeout=120)


def override_index(rom):
    """02/06 의 7E:21AD bit4 조건(10:9B57) 항목 번호."""
    from dq5npc import overrides
    rows = overrides(rom, 2, 6)
    target = [i for i, (n, m, a) in enumerate(rows) if (n, m, a) == (0x1D, 0x10, 0x109B57)]
    require(target, '02/06 의 21AD bit4 대체 조건을 찾지 못함')
    from dq5npc import OVERRIDE_LISTS
    at, i = OVERRIDE_LISTS, 0
    while rom.u8(at) != 0xFF:
        if (rom.u8(at), rom.u8(at + 1), rom.u8(at + 2), rom.u8(at + 3)) == (2, 6, 0x1D, 0x10):
            return i
        at, i = at + 6, i + 1
    raise ValueError('대체 표 항목 번호를 찾지 못함')


def run(case, roms, state, out, mesence, libdir):
    name, rom, night, test = case
    dest = out / name
    dest.mkdir()
    to = HERO
    bc, bd = to.split(',')[0].split('/')
    env = {k: v for k, v in os.environ.items()
           if k not in ('ADULT', 'ANYWHERE', 'BATTLE', 'FIELD', 'GROUP', 'LATESET', 'PARTY', 'POKE',
                        'ROMPATCH', 'SAVE', 'SET', 'WAGON')}
    env.update(LIBDIR=str(libdir), STATE=str(state), SHOT_DIR=str(dest), MAXF='1500', SETTLE='120',
               TO=to, TEST=f'{test},wait:30' if test else 'wait:30', CHECK_GROUP=bc, CHECK_MAP=bd)
    if night:
        env['POKE'] = '7E075E=F0;7E075F=00'
    with (dest / 'mesen.log').open('w', encoding='utf-8') as log:
        subprocess.run([str(mesence), '--testrunner', str(roms[rom]), str(HERE / 'lua/dq5npcrecordcheck.lua'),
                        '--Snes.DisableFrameSkipping=true'], env=env, stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=120)
    text = (dest / 'warp.txt').read_text(encoding='utf-8')
    require('timeout' not in text and (dest / 'npc.bin').is_file(), f'{name}: 맵에 들어가지 못함')
    messages = re.search(r'^messages (.*)$', text, re.M)[1]
    return (dest / 'npc.bin').read_bytes(), [int(v, 16) for v in messages.split(',') if v]


def slots(rom, wram, bc, bd, night):
    """로더가 고른 목록과 그 목록의 인물 표 예측값을 덤프 플래그로 구한다."""
    flags = {FLAGS + i: wram[0x2190 + i] for i in range(0x170)}
    source = list_address(rom, bc, bd, flags)
    placed = [] if source is None else [(at, f) for at, _ in list_entries(rom, source) if (f := parse(rom, at, night))]
    return source, placed, table_values(rom, placed, flags)


def compare(wram, expected, skip=()):
    bad = []
    for slot, values in enumerate(expected, 8):
        bad.extend(f'{slot:02X}/{addr:04X} {wram[addr + slot]:02X}!={want:02X}'
                   for addr, want in values.items() if addr not in skip and wram[addr + slot] != want)
    return bad


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/npcrecordcheck')
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
        docs = {'edited': {'format': 'dq5npcrecord/1', 'entries': ENTRIES},
                'condition': {'format': 'dq5npcrecord/1', 'overrides': [{'index': override_index(base), 'when': 'off'}]}}
        roms = {'original': original}
        for key, doc in docs.items():
            source = out / f'{key}.json'
            source.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            command('dq5npcrecord.py', original, 'check', source)
            command('dq5npcrecord.py', original, 'patch', source, '-o', out / f'{key}.dq5patch.json')
            roms[key] = out / f'{key}.sfc'
            command('dq5build.py', original, 'build', out / f'{key}.dq5patch.json', '-o', roms[key],
                    '--ips', out / f'{key}.ips')
        (out / 'scripts.json').write_text('{"format": "dq5npcrelocate/1"}\n', encoding='utf-8')
        command('dq5npcrelocate.py', original, 'patch', out / 'scripts.json', '-o', out / 'relocated.dq5patch.json',
                '--records', out / 'edited.json', '--report', out / 'layout.json')
        roms['relocated'] = out / 'relocated.sfc'
        command('dq5build.py', original, 'build', out / 'relocated.dq5patch.json', '-o', roms['relocated'],
                '--ips', out / 'relocated.ips')
        krlua = Path(subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True,
                                    check=True, timeout=30).stdout.strip())
        libdir = out / 'lib'
        shutil.copytree(krlua, libdir)
        shutil.copyfile(HERE / 'lua/dq5warp.lua', libdir / 'boot.lua')
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            seen = list(pool.map(lambda case: run(case, roms, state, out, mesence, libdir), CASES))
        models = {'original': base, 'edited': Rom(roms['edited'].read_bytes()),
                  'condition': Rom(roms['condition'].read_bytes())}
        # 옮긴 롬은 같은 문서를 넣은 edited 롬과 인물 표가 같아야 한다. 스크립트 포인터만 다르다.
        models['relocated'] = models['edited']
        results, got = [], dict(zip((c[0] for c in CASES), seen))
        for (name, rom, night, _), (wram, messages) in zip(CASES, seen):
            source, placed, expected = slots(models[rom], wram, 2, 6, night)
            bad = compare(wram, expected, (0x3480, 0x34A0) if rom == 'relocated' else ())
            results.append({'case': name, 'rom': rom, 'list': None if source is None else f'{source:06X}',
                            'slots': len(placed), 'placed': [f'{a:06X}' for a, _ in placed],
                            'table_mismatch': bad[:20], 'messages': [f'{m:03X}' for m in messages]})
        by = {r['case']: r for r in results}

        def cell(case, entry, *columns):
            wram, at = got[case][0], 8 + by[case]['placed'].index(f'{entry:06X}')
            return tuple(wram[c + at] for c in columns)

        columns = (0x3020, 0x3080, 0x3220, 0x36E0, 0x3700)
        moved = (24, 12, 0x18, TALK & 0xFF, TALK >> 8)
        checks = {
            # 밤에만 있던 인물이 낮에 주인공 두 칸 위 (24,12)에 새 대화 번호로 놓였는가. 원본 낮에는 없음
            'moved': cell('day-edited', MOVED, *columns) == moved and cell('day-relocated', MOVED, *columns) == moved
            and f'{MOVED:06X}' not in by['day-original']['placed'],
            'gfx': cell('day-edited', REDRAWN, 0x3220) == (0x18,) and cell('day-original', REDRAWN, 0x3220) == (0x29,),
            'talk': MESSAGE in got['day-edited'][1] and MESSAGE in got['day-relocated'][1],
            'talk-original': MESSAGE not in got['day-original'][1],
            'night': by['night-edited']['placed'] == [f'{NIGHT:06X}']
            and by['night-original']['placed'] == [f'{NIGHT:06X}', f'{MOVED:06X}'],
            'condition': by['condition-edited']['list'] == '109B57' and by['condition-original']['list'] != '109B57',
            'tables': all(not r['table_mismatch'] for r in results),
        }
        (out / 'results.json').write_text(json.dumps({'cases': results, 'checks': checks}, ensure_ascii=False,
                                                     indent=2) + '\n', encoding='utf-8')
        for r in results:
            print(f'{r["case"]}: 목록 {r["list"]} 인물 {r["slots"]} 표 불일치 {len(r["table_mismatch"])} '
                  f'메시지 {",".join(r["messages"]) or "-"}')
        for key, ok in checks.items():
            print(f'{key}: {"통과" if ok else "불일치"}')
        require(all(checks.values()), '불일치: ' + ', '.join(k for k, ok in checks.items() if not ok))
        print(f'{len(CASES)}개 장면, 검사 {len(checks)}개 통과')
        return 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
