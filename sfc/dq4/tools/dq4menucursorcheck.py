"""게임 안 명령 창에서 두 방향을 겹쳐 눌러도 커서가 한 칸씩만 움직이는지 MesenCE 실제 패드 입력으로 확인한다.

1장 롬(dq4build.py)을 전원부터 켜 A·Y 로 이름 입력과 첫 장면을 넘긴 뒤 명령 창을 열고, 「작전」(색인 5)에서
사례마다 방향키를 누른다. 명령 창 색인은 행 × 2 + 열이다. 각 실행은 별도 롬 사본과 빈 SRAM 을 쓴다.

  MESENCE=… uv run --locked python sfc/dq4/tools/dq4menucursorcheck.py --rom work/ch1/dq4-ch1.sfc --out work/menu-cursor
형식은 sfc/dq4/docs/dq4-name-entry-format.md 「방향 처리」.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import subprocess

import dq4mesen as mesen

HERE = Path(__file__).resolve().parent
BOOT = 6600
SETUP = [(20, 3, 'b'), (60, 3, 'b'), (150, 3, 'a'), (230, 3, 'down'), (260, 3, 'down'), (290, 3, 'right')]
START = 340
COMMAND_WINDOW = 0x01


def scenarios():
    """(이름, START 기준 이벤트, 기대 위치, 기대 프레임(START 기준) 또는 None)."""
    return [
        ('together-tap', [(0, 3, 'up'), (0, 3, 'left')], [3], [0]),
        ('together-hold', [(0, 30, 'up'), (0, 30, 'left')], [3, 1], [0, 16]),
        ('together-hold-top', [(0, 60, 'up'), (0, 60, 'left')], [3, 1], None),
        ('up-then-left', [(0, 6, 'up'), (2, 8, 'left')], [3, 2], [0, 2]),
        ('left-then-up', [(0, 6, 'left'), (2, 8, 'up')], [4, 2], [0, 2]),
        ('release-up-first', [(0, 6, 'up'), (0, 12, 'left')], [3], None),
        ('one-frame-each', [(0, 1, 'up'), (1, 1, 'left')], [3, 2], [0, 1]),
        ('down-right', [(0, 4, 'down'), (0, 4, 'right')], [7], None),
        ('sequence', [(0, 3, 'up'), (10, 3, 'left'), (20, 3, 'down'), (30, 3, 'right')], [3, 2, 4, 5],
         [0, 10, 20, 30]),
        ('hold-up', [(0, 60, 'up')], [3, 1], [0, 16]),
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--rom', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    mesence = os.environ.get('MESENCE')
    if not mesence:
        parser.error('MESENCE 에 실행 파일을 주세요')
    output = args.out.resolve()
    if output.exists():
        parser.error('--out 은 아직 없는 폴더를 주세요')
    output.mkdir(parents=True)
    lib = os.environ.get('LIBDIR') or subprocess.check_output(
        ['uv', 'run', '--locked', 'krpatch', 'sfc', 'lua'], text=True).strip()

    def run(case):
        name, events, positions, frames = case
        folder = output / name
        folder.mkdir()
        cfg = folder / 'case.lua'
        events = SETUP + [(START + f, n, b) for f, n, b in events]
        cfg.write_text(f'return {{boot={BOOT},shot={START - 10},stop={START + 100},events={{'
                       + ','.join('{%d,%d,"%s"}' % e for e in events) + '}}')
        env = dict(os.environ, LIBDIR=lib, SHOT_DIR=str(folder), MENU_CURSOR_CASE=str(cfg))
        mesen.run(mesence, args.rom, HERE / 'lua/dq4menucursorcheck.lua', folder=folder, tag=name, extra=(), env=env,
                  check=True, timeout=300)
        moves = [row.split()[1:] for row in (folder / 'cursor.txt').read_text().splitlines()
                 if row.startswith('MOVE ')]
        moves = [(int(f), int(a), int(b), int(w, 16)) for f, a, b, w in moves]
        before = [m for m in moves if m[0] < START and m[3] == COMMAND_WINDOW]
        if not before or before[-1][2] != 5:
            return f'FAIL {name} 명령 창 「작전」에 서지 못함: {before[-3:]}'
        after = [(f - START, b) for f, _, b, w in moves if f >= START and w == COMMAND_WINDOW]
        if [b for _, b in after] != positions:
            return f'FAIL {name} positions={[b for _, b in after]} expected={positions}'
        if frames and [f for f, _ in after] != frames:
            return f'FAIL {name} frames={[f for f, _ in after]} expected={frames}'
        return f'PASS {name} moves={after}'

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
