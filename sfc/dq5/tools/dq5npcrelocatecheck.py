"""인물 목록 재배치의 원본·패치 롬을 MesenCE에서 비교한다.

기본은 선실·02/06·01/05 낮밤과 02/06 대체 목록. --all은 기본 맵 346개 낮밤을 비교한다.
--base·--alt·--group-bank 는 dq5npcrelocate.py 와 같아 목록을 여러 뱅크에 나눈 롬을 볼 수 있고,
--case 로 대체 목록을 고르는 플래그와 맵을 더 준다.
인물 배치 직후 12:803C에서 23칸을 비교하고, 스크립트가 있으면 뱅크까지 포함한
3바이트 포인터를 재배치 주소표에 대조한다. 시험 롬·덤프·화면은 --out의 새 폴더에만 쓴다.

  MESENCE=… python sfc/dq5/tools/dq5npcrelocatecheck.py rom/dq5.sfc --state work/state/ship.mss --out work/npc-check --all
"""
import argparse
import concurrent.futures
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dq5map import Rom  # noqa: E402
from dq5npc import FLAGS, all_lists, list_address, list_entries, parse, table_values  # noqa: E402
from dq5npcrelocate import FORMAT, cpu, group_bank, patch, places  # noqa: E402
import dq5mesen  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def extra_case(text):
    match = re.fullmatch(r'([0-9A-F]{2})/([0-9A-F]{2})((?::7E[0-9A-F]{4}=[0-9A-F]{2})(?:;7E[0-9A-F]{4}=[0-9A-F]{2})*)?', text)
    if not match:
        raise argparse.ArgumentTypeError('--case 는 GG/MM 또는 GG/MM:7EXXXX=VV;… (대문자 16진)')
    return int(match[1], 16), int(match[2], 16), (';' + match[3][1:]) if match[3] else ''


def command(tool, *args):
    subprocess.run([sys.executable, str(HERE / tool), *map(str, args)], check=True, capture_output=True, text=True, timeout=60)


def environment(case, dest, state, libdir):
    bc, bd, night, flags = case
    env = os.environ.copy()
    for key in ('TEST', 'TO', 'FIELD', 'WATCH', 'PRE', 'LOOP', 'WAYPOINTS', 'POKE', 'ROMPATCH',
                'MAXF', 'AFTER', 'HOLD', 'CHANGES', 'SAVE', 'SHOTMSG', 'PEEK', 'SHOTS', 'DUMP',
                'VRAMDUMP', 'BG3FONT', 'TRACE', 'LOG', 'RWATCH', 'WWATCH', 'COVER', 'ACCESS', 'VMADD'):
        env.pop(key, None)
    env.update(LIBDIR=libdir, STATE=str(state), DRIVER=str(ROOT / 'tools/lua/walk.lua'),
               SHOT_DIR=str(dest), PRE='b:4,wait:40', WAYPOINTS='3,11;3,24;7,24;up:10',
               ROMPATCH=f'156FF5={0xE0 | bd:02X}090B01{bc:02X}', CHANGES='99', MAXF='1200',
               AFTER='120', HOLD='90', CHECK_GROUP=f'{bc:02X}', CHECK_MAP=f'{bd:02X}',
               POKE=f'7E075E={0xF0 if night else 0x50:02X};7E075F=00' + flags)
    return env


def capture(rom, case, dest, state, mesence, libdir):
    dest.mkdir()
    env = environment(case, dest, state, libdir)
    with (dest / 'mesen.log').open('w', encoding='utf-8') as log:
        dq5mesen.testrunner(str(mesence), str(rom), str(HERE / 'lua/dq5npcrelocatecheck.lua'),
                            env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=90)
    return (dest / 'npc.bin').read_bytes()


def compare_case(case, out, original_path, relocated_path, original, layout, state, mesence, libdir, model=None):
    """model 은 재배치 롬의 인물 표를 예측할 롬(인물 레코드를 고쳤으면 원래 롬에 그 패치만 넣은 것). 없으면 원래 롬."""
    bc, bd, night, flags_override = case
    tag = f'{bc:02X}-{bd:02X}-' + ('night' if night else 'day') + ('-override' if flags_override else '')
    a = capture(original_path, case, out / (tag + '-original'), state, mesence, libdir)
    b = capture(relocated_path, case, out / (tag + '-relocated'), state, mesence, libdir)
    if len(a) != 0x20000 or len(b) != 0x20000:
        raise ValueError(f'{tag}: WRAM 덤프 크기가 다름')
    flags = {FLAGS + i: a[0x2190 + i] for i in range(0x170)}
    if a[0x2190:0x2300] != b[0x2190:0x2300] or a[0x075E] != b[0x075E]:
        raise ValueError(f'{tag}: 플래그·시간대가 다름')
    model = model or original

    def predict(rom):
        source = list_address(rom, bc, bd, flags)
        placed = [] if source is None else [(at, value) for at, _ in list_entries(rom, source)
                                            if (value := parse(rom, at, night))]
        return source, placed, table_values(rom, placed, flags)

    source, placed, expected = predict(original)
    bad, pointers = [], 0
    for slot, ((_, value), want_values) in enumerate(zip(placed, expected), 8):
        bad += [f'원본 {slot:02X}/{addr:04X}' for addr, want in want_values.items() if a[addr + slot] != want]
        if value['script'] is not None:
            actual = a[0x3480 + slot] | a[0x34A0 + slot] << 8 | a[0x34C0 + slot] << 16
            if actual != value['script'] + 1:
                bad.append(f'원본 포인터 {slot:02X}: {actual:06X}!={value["script"] + 1:06X}')
    source, placed, expected = predict(model)
    for slot, ((_, value), want_values) in enumerate(zip(placed, expected), 8):
        bad += [f'재배치 {slot:02X}/{addr:04X}' for addr, want in want_values.items()
                if addr not in (0x3480, 0x34A0) and b[addr + slot] != want]
        if value['script'] is not None:
            new = int(layout['scripts'][cpu(value['script'])].replace(':', ''), 16) + 1
            actual = b[0x3480 + slot] | b[0x34A0 + slot] << 8 | b[0x34C0 + slot] << 16
            if actual != new:
                bad.append(f'재배치 포인터 {slot:02X}: {actual:06X}!={new:06X}')
            pointers += 1
        elif b[0x3480 + slot] or b[0x34A0 + slot]:
            bad.append(f'없는 스크립트 포인터 {slot:02X}')
    if bad:
        raise ValueError(f'{tag}: ' + ', '.join(bad[:20]))
    return {'case': tag, 'list': cpu(source) if source is not None else None,
            'slots': len(placed), 'script_pointers': pointers, 'passed': True}



# 선실·기본 공유·대체 공유 스크립트를 39바이트로 늘린다. 실행하면 (5,13) 에 멈춘다.
MUTATION_ADDRESSES = ('05:A84F', '05:8B2D', '10:914F')
MUTATION_COMMANDS = [{'op': '1A'}] * 35 + [{'op': '2B', 'args': [5, 13]}, {'op': '16'}]
MUTATION_SOURCE = {'format': FORMAT, 'scripts': [{'address': address, 'commands': MUTATION_COMMANDS}
                                                 for address in MUTATION_ADDRESSES]}


def check_mutations(out, original_path, original, state, mesence, libdir, jobs):
    manifest, layout = patch(original, MUTATION_SOURCE)
    manifest_path, rom_path = out / 'long.dq5patch.json', out / 'long.sfc'
    manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
    (out / 'long-layout.json').write_text(json.dumps(layout, indent=2), encoding='utf-8')
    command('dq5build.py', original_path, 'build', manifest_path, '-o', rom_path,
            '--ips', out / 'long.ips')
    return run_mutations(out, rom_path, layout, state, mesence, libdir, jobs)


def run_mutations(out, rom_path, layout, state, mesence, libdir, jobs):
    """MUTATION_SOURCE 를 넣은 롬에서 긴 스크립트 5건을 실행해 좌표·이동 상태·포인터를 견준다."""
    addresses = MUTATION_ADDRESSES
    cases = [((0x17, 0, False, ''), 8, addresses[0])]
    for night in (False, True):
        cases.extend([((2, 0, night, ';7E2190=00;7E21AD=00;7E21A8=00'), 10, addresses[1]),
                      ((2, 1, night, ';7E2190=00;7E21AD=00;7E21A8=02'), 17, addresses[2])])

    def run(item):
        case, slot, address = item
        tag = f'long-{case[0]:02X}-{case[1]:02X}-' + ('night' if case[2] else 'day')
        dest = out / tag
        dest.mkdir()
        env = environment(case, dest, state, libdir)
        watches = {'x': 0x3020 + slot, 'y': 0x3080 + slot, 'move': 0x3300 + slot,
                   'lo': 0x3480 + slot, 'hi': 0x34A0 + slot, 'bank': 0x34C0 + slot, 'time': 0x075E}
        env.update(MAXF='6000', WATCH=';'.join(f'{key}=7E{addr:04X}' for key, addr in watches.items()))
        with (dest / 'mesen.log').open('w', encoding='utf-8') as log:
            dq5mesen.testrunner(str(mesence), str(rom_path), str(HERE / 'lua/dq5scriptcheck.lua'),
                                env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=90)
        text = (dest / 'walk.txt').read_text(encoding='utf-8')
        got = {key: int(value, 16) for key, value in re.findall(r'^(\w+)=([0-9A-F]+)$', text, re.M)}
        expected = int(layout['scripts'][address].replace(':', ''), 16) + 39
        pointer = got['lo'] | got['hi'] << 8 | got['bank'] << 16
        if (got['x'], got['y'], got['move'], got['time'], pointer) != (5, 13, 0, 0xF0 if case[2] else 0x50, expected):
            raise ValueError(f'{tag}: 긴 스크립트 실행 결과가 다름: {got}, 기대 포인터 {expected:06X}')
        return {'case': tag, 'script': address, 'length': 39, 'pointer': cpu(pointer),
                'slots': 1, 'script_pointers': 1, 'passed': True}

    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        return list(pool.map(run, cases))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rom', type=Path)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--out', type=Path, default=Path('work/npc-relocate-check'))
    parser.add_argument('--mesence', default=os.environ.get('MESENCE'))
    parser.add_argument('--all', action='store_true')
    parser.add_argument('--mutations', action='store_true', help='긴 선실·기본 공유·대체 공유 스크립트 실행 5건 추가')
    parser.add_argument('--jobs', type=int, default=4)
    parser.add_argument('--base', default='32:8000', help='dq5npcrelocate.py patch 의 --base(쉼표로 여러 뱅크)')
    parser.add_argument('--alt', default='33:8000', help='dq5npcrelocate.py patch 의 --alt(쉼표로 여러 뱅크)')
    parser.add_argument('--group-bank', action='append', default=[], type=group_bank, help='dq5npcrelocate.py 의 --group-bank')
    parser.add_argument('--case', action='append', default=[], type=extra_case,
                        help='낮밤으로 더 볼 맵 GG/MM[:7EXXXX=VV;…] (대체 목록을 고르는 플래그를 함께 줌)')
    args = parser.parse_args()
    if not args.mesence or args.jobs < 1:
        parser.error('MESENCE 또는 --mesence와 양수 --jobs가 필요함')
    try:
        original_path, state, mesence = args.rom.resolve(), args.state.resolve(), Path(args.mesence).resolve()
        for path in (original_path, state, mesence):
            if not path.is_file():
                raise ValueError(f'파일 없음: {path}')
        original = Rom(original_path.read_bytes())
        manifest, layout = patch(original, {'format': FORMAT}, places(args.base), places(args.alt),
                                 group_banks=dict(args.group_bank))
        args.out.mkdir(parents=True, exist_ok=True)
        out = Path(tempfile.mkdtemp(prefix='run-', dir=args.out.resolve()))
        (out / 'relocate.dq5patch.json').write_text(json.dumps(manifest), encoding='utf-8')
        (out / 'layout.json').write_text(json.dumps(layout, indent=2), encoding='utf-8')
        relocated_path = out / 'relocated.sfc'
        command('dq5build.py', original_path, 'build', out / 'relocate.dq5patch.json', '-o', relocated_path,
                '--ips', out / 'relocated.ips')
        libdir = subprocess.check_output(['krpatch', 'sfc', 'lua'], text=True, timeout=30).strip()
        maps = [tuple(int(v, 16) for v in name.split('/')) for _, name in all_lists(original)[:346]] if args.all else [(0x17, 0), (2, 6), (1, 5)]
        cases = [(bc, bd, night, '') for bc, bd in maps for night in (False, True)]
        cases.extend((2, 6, night, ';7E21AD=10') for night in (False, True))
        cases.extend((bc, bd, night, pokes) for bc, bd, pokes in args.case for night in (False, True))
        print(f'출력 {out}; 검사 {len(cases)}건', flush=True)
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            futures = [pool.submit(compare_case, case, out, original_path, relocated_path, original,
                                   layout, state, mesence, libdir) for case in cases]
            for future in concurrent.futures.as_completed(futures):
                results.append(future.result())
                if len(results) % 40 == 0:
                    print(f'{len(results)}/{len(cases)} 통과', flush=True)
        if args.mutations:
            results.extend(check_mutations(out, original_path, original, state, mesence, libdir, args.jobs))
        (out / 'results.json').write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8')
        print(f'{len(results)}/{len(cases) + (5 if args.mutations else 0)} 통과, 인물 {sum(r["slots"] for r in results)}슬롯, '
              f'포인터 {sum(r["script_pointers"] for r in results)}개', flush=True)
        return 0
    except (ValueError, OSError, subprocess.SubprocessError, KeyError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.output:
            print(error.output, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
