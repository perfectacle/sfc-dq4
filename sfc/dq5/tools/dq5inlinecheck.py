"""인물 인라인 메시지 명령 21·32 가 A 를 기다렸다 창을 닫는지 화면과 PC 로 잰다.

dq5textgrowcheck.py 와 같은 17/00 인물(05:A84F)의 스크립트를 바꾼 롬 셋을 걸어가 부딪쳐 돌린다.
  21     21 29 01            창을 열어 메시지 129 를 띄우고 A 를 기다렸다 닫음(기준)
  32     32 29 01            창을 열지 않고 띄운 뒤 A 를 기다렸다 닫음
  30-32  30 29 01 / 32 2A 01  30 이 연 창에 32 가 이어 띄우고 A 를 기다렸다 닫음
롬마다 A 를 부딪친 뒤 400프레임과 200프레임에 누르는 두 번을 돌려, 처리기의 BRK 0E(기다림)·BRK 95 FF(닫기)를
실행한 프레임과 A 를 누른 프레임, 화면 아래 창 자리(y 128~215)를 견준다. 창 자리는 창이 닫힌 뒤 화면과 같으면
「창 없음」이다. 원본 롬·선실 상태는 읽기만 하고 출력은 --out 의 새 하위 폴더에 둔다.
  MESENCE=… python sfc/dq5/tools/dq5inlinecheck.py rom/dq5.sfc --state work/state/ship.mss
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

from PIL import Image, ImageChops

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
from dq5textgrowcheck import npc_patch, tool  # noqa: E402
import dq5mesen  # noqa: E402

CASES = {'21': [{'op': '21', 'args': [0x29, 0x01]}],
         '32': [{'op': '32', 'args': [0x29, 0x01]}],
         '30-32': [{'op': '30', 'args': [0x29, 0x01]}, {'op': '32', 'args': [0x2A, 0x01]}]}
# 처리기(01:C827 표)의 첫 명령, BRK 0E(A 기다림), BRK 95 FF(창 닫기)
MARKS = 'e21=01CE85;e30=01D004;e32=01D02F;w21=01CE97;c21=01CE99;w32=01D03A;c32=01D03C'
WAITS = (400, 200)
MAXF = 1300
WINDOW = (0, 128, 256, 216)


def run(name, rom, wait, out, mesence, libdir, state):
    dest = out / f'{name}-{wait}'
    dest.mkdir()
    env = {k: v for k, v in os.environ.items() if k not in ('ROMPATCH', 'SET', 'POKE')}
    env.update(LIBDIR=libdir, STATE=str(state), SHOT_DIR=str(dest), DRIVER=str(ROOT / 'tools/lua/walk.lua'),
               PRE='b:4,wait:40', WAYPOINTS=f'3,11;3,24;7,24;up:10;wait:{wait};a:4;wait:400',
               ROMPATCH='156FF5=E0090B0117', CHANGES='99', MAXF=str(MAXF), HOLD='90', MARKS=MARKS,
               SHOTS=','.join(str(f) for f in range(300, MAXF, 10)))
    with (dest / 'mesen.log').open('w', encoding='utf-8') as log:
        dq5mesen.testrunner(str(mesence), str(rom), str(HERE / 'lua/dq5inlinecheck.lua'),
                            '--Snes.DisableFrameSkipping=true', env=env, stdout=log, stderr=subprocess.STDOUT,
                            check=True, timeout=200)
    events = {}
    for f, what in re.findall(r'^f(\d+) (.+)$', (dest / 'inline.txt').read_text(encoding='utf-8'), re.M):
        events.setdefault(what, []).append(int(f))
    return dest, events


def window(dest, frame):
    return Image.open(dest / f'f{frame:04d}.png').convert('RGB').crop(WINDOW)


def judge(name, wait, dest, events):
    op = '21' if name == '21' else '32'
    begin, hold, close = events[f'e{op}'][-1], events[f'w{op}'][0], events[f'c{op}'][0]
    press = events['press a'][0] - 1      # 기록은 누른 다음 프레임의 끝에 남는다
    shot = lambda f: f - f % 10           # noqa: E731
    after = window(dest, shot(close) + 120)
    waiting = ImageChops.difference(window(dest, shot(press) - 10), after).getbbox() is not None
    reopened = ImageChops.difference(window(dest, shot(close) + 60), after).getbbox() is not None
    return {'case': f'{name}-{wait}', 'begin': begin, 'wait': hold, 'press': press, 'close': close,
            'messages': [m for m in events if m.startswith('message ')], 'window_while_waiting': waiting,
            'window_after_close': reopened}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/inlinecheck')
    args = ap.parse_args()
    if not args.mesence:
        ap.error('--mesence 또는 MESENCE가 필요함')
    try:
        original, state, mesence = args.rom.resolve(), args.state.resolve(), Path(args.mesence).resolve()
        for path in (original, state, mesence):
            if not path.is_file():
                raise ValueError(f'파일 없음: {path}')
        args.out.mkdir(parents=True, exist_ok=True)
        out = Path(tempfile.mkdtemp(prefix='run-', dir=args.out.resolve()))
        print(f'실행 출력: {out}', flush=True)
        roms = {}
        for name, commands in CASES.items():
            roms[name] = out / f'{name}.sfc'
            tool('dq5build.py', original, 'build', npc_patch(original, out, name, commands), '-o', roms[name])
        libdir = subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True,
                                check=True, timeout=30).stdout.strip()
        jobs = [(name, wait) for name in CASES for wait in WAITS]
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            runs = list(pool.map(lambda j: run(j[0], roms[j[0]], j[1], out, mesence, libdir, state), jobs))
        results = [judge(name, wait, *got) for (name, wait), got in zip(jobs, runs)]
        checks = {
            # 기다림은 A 앞에서 시작하고, 닫기는 A 를 누른 프레임에 온다. 누르는 때를 200프레임 당겨도 따라온다
            'waits-for-a': all(r['wait'] < r['press'] and 0 <= r['close'] - r['press'] <= 2 for r in results),
            # 21·30+32 는 기다리는 동안 창이 있고, 32 혼자는 창 자리가 닫힌 뒤와 같다(창을 열지 않음)
            'window': all(r['window_while_waiting'] == (not r['case'].startswith('32-')) for r in results),
            'closed': not any(r['window_after_close'] for r in results),
        }
        (out / 'results.json').write_text(json.dumps({'cases': results, 'checks': checks}, ensure_ascii=False,
                                                     indent=1) + '\n', encoding='utf-8')
        for r in results:
            print(f"{r['case']:>9}: 시작 f{r['begin']} 기다림 f{r['wait']} A f{r['press']} 닫기 f{r['close']}"
                  f" 기다리는 동안 창 {'있음' if r['window_while_waiting'] else '없음'} {' '.join(r['messages'])}")
        bad = [k for k, ok in checks.items() if not ok]
        print('통과' if not bad else f'실패: {bad}')
        return 1 if bad else 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
