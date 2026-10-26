"""실제 패드 입력으로 자모판 방향 전환·반복·Start 커서를 MesenCE 에서 확인한다.

각 실행은 별도 롬 사본과 빈 SRAM 을 쓰며, 첫 자모판의 시작 커서만 지정합니다.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import shutil
import subprocess

import dq4nameentry as ne

HERE = Path(__file__).resolve().parent


def scenarios():
    cases = []

    def add(name, initial, events, positions, frames=None, typed=False, confirm=False):
        cases.append(dict(name=name, initial=initial, events=events, positions=positions,
                          frames=frames, typed=typed, confirm=confirm))

    for gap in (0, 1, 2):
        add(f'up-left-gap{gap}', 25, [(1300, 3, 'up'), (1303 + gap, 3, 'left')],
            [14, 13], [1300, 1303 + gap])
    add('up-left-one-frame', 25, [(1300, 1, 'up'), (1301, 1, 'left')], [14, 13], [1300, 1301])
    add('left-up-one-frame', 25, [(1300, 1, 'left'), (1301, 1, 'up')], [24, 13], [1300, 1301])
    add('overlap-release-old', 25, [(1300, 8, 'up'), (1306, 10, 'left')], [14, 13], [1300, 1306])
    add('simultaneous', 25, [(1300, 3, 'up'), (1300, 3, 'left')], [14], [1300])
    add('overlap-release-selected', 25, [(1300, 30, 'right'), (1306, 4, 'down')],
        [26, 37, 38, 39], [1300, 1306, 1322, 1329])
    add('hold-repeat', 25, [(1300, 50, 'right')], [26, 27, 28, 29, 30, 32],
        [1300, 1316, 1323, 1330, 1337, 1344])
    add('top-left-wrap', 0, [(1300, 3, 'left')], [9], [1300])
    add('hole-right', 4, [(1300, 3, 'right')], [8], [1300])
    add('hole-left', 8, [(1300, 3, 'left')], [4], [1300])
    keys = [cell for row in ne.GRID for cell in row + [None] * (ne.ROW_CELLS - len(row))]
    done = keys.index(ne.DONE)
    for i, key in enumerate(keys):
        if key is not None:
            add(f'start-empty-{i:02d}', i, [(1300, 40, 'start')], [] if i == done else [done])
    add('start-name-hold', 25, [(1300, 40, 'start')], [done], typed=True)
    add('start-name-confirm', 25, [(1300, 40, 'start'), (1400, 3, 'a')], [done], typed=True, confirm=True)
    add('start-name-twice', 25, [(1300, 3, 'start'), (1320, 3, 'start'), (1400, 3, 'a')],
        [done], typed=True, confirm=True)
    add('start-name-back', 25, [(1300, 40, 'start'), (1400, 3, 'b')], [done], typed=True)
    add('start-name-back-at-end', 25, [(1300, 50, 'right'), (1360, 3, 'start'), (1440, 3, 'b')],
        [26, 27, 28, 29, 30, done], typed=True)
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, required=True)
    parser.add_argument('--symbols', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    mesence = os.environ.get('MESENCE')
    if not mesence:
        parser.error('MESENCE 에 실행 파일을 주세요')
    output = args.out.resolve()
    if output.exists():
        parser.error('--out 은 아직 없는 폴더를 주세요')
    output.mkdir(parents=True)
    symbols = {}
    for line in args.symbols.read_text().splitlines():
        words = line.split()
        if len(words) == 2 and ':' in words[0]:
            symbols[words[1]] = int(words[0].replace(':', ''), 16)
    lib = os.environ.get('LIBDIR') or subprocess.check_output(
        ['uv', 'run', '--locked', 'krpatch', 'sfc', 'lua'], text=True).strip()

    def run(case):
        folder = output / case['name']
        folder.mkdir()
        rom = folder / (output.name + '-' + case['name'] + '.sfc')
        shutil.copyfile(args.rom, rom)
        cfg = folder / 'case.lua'
        events = [(600, 3, 'a'), (900, 3, 'a'), (1100, 3, 'a')]
        if case['typed']:
            events.append((1250, 3, 'a'))
        events += case['events']
        cfg.write_text('return {initial=' + str(case['initial']) + ',loop=' + str(symbols['NeLoop'])
                       + ',finish=' + str(symbols['NeReturn']) + ',events={'
                       + ','.join('{%d,%d,"%s"}' % e for e in events) + '}}')
        env = dict(os.environ, LIBDIR=lib, SHOT_DIR=str(folder), NAME_CURSOR_CASE=str(cfg))
        subprocess.run([mesence, '--testrunner', str(rom), str(HERE / 'lua/dq4namecursorcheck.lua')],
                       env=env, check=True, timeout=120)
        rows = (folder / 'cursor.txt').read_text().splitlines()
        moves = [tuple(map(int, row.split()[1:])) for row in rows if row.startswith('MOVE ')]
        positions = [m[2] for m in moves]
        if positions != case['positions']:
            return f'FAIL {case["name"]} positions={positions} expected={case["positions"]}'
        if case['frames'] and [m[0] for m in moves] != case['frames']:
            return f'FAIL {case["name"]} frames={[m[0] for m in moves]} expected={case["frames"]}'
        if len({m[0] for m in moves}) != len(moves):
            return f'FAIL {case["name"]} 한 프레임에 두 번 이동'
        returns = [row for row in rows if row.startswith('RETURN ')]
        if case['confirm']:
            if len(returns) != 1 or int(returns[0].split()[1]) < 1400:
                return f'FAIL {case["name"]} A 전 완료 또는 완료 누락: {returns}'
        elif returns:
            return f'FAIL {case["name"]} 뜻하지 않은 이름 완료: {returns}'
        if case['name'].startswith('start-'):
            before = next(row.split(' ', 1)[1] for row in rows if row.startswith('BEFORE '))
            after = next(row.split(' ', 1)[1] for row in rows if row.startswith('AFTER '))
            if before != after:
                return f'FAIL {case["name"]} Start 가 이름·완료 버퍼를 바꿈'
        if case['name'].startswith('start-name-back'):
            if 'NAME 0 0' not in rows or 'CURSOR 32' not in rows:
                return f'FAIL {case["name"]} B 삭제 후 이름·커서가 다름'
        return f'PASS {case["name"]} moves={moves}'

    with ThreadPoolExecutor(max_workers=4) as pool:
        reports = list(pool.map(run, scenarios()))
    report = '\n'.join(reports) + '\n'
    (output / 'summary.txt').write_text(report)
    print(report, end='')
    if any(row.startswith('FAIL') for row in reports):
        raise SystemExit(1)
    print(f'{len(reports)}개 입력 사례 통과')


if __name__ == '__main__':
    main()
