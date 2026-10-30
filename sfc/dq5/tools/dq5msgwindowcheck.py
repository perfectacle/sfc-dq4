"""전투 메시지 창(18·25) X 쓰기를 MesenCE 전투에서 VRAM BG3 타일맵과 화면으로 확인한다.

dq5windowwrite.py 로 두 창의 X 를 2 에서 0(left)·4(right)로 옮긴 롬과 원래 롬을 같은 입력으로 돌린다. 장면은 둘이다.
one 은 スライム 하나와 싸우며 공격 메시지 05E 를 긴 메시지 006·118·191 로, 피해 069 를 006 으로 바꾸고, 20:C62B 의
BRK A4 를 BRK 9E 로 바꿔(파일 오프셋 10462C, 세 롬 모두) 셋째 줄 다음에 줄을 올리게 한다. four 는 무리 넷(00·01·02·03)이
나타나 창 25 가 한 줄 올라가고 두 줄 늘어나는 갈래(04:A070)를 탄다. 둘 다 메시지 속도 7E:2035 = 7 로 두어 ▼ 를 띄우고
기다리게 한다(24:A519·24:A523).
원래 롬에서 메시지 창(맨 위 줄 21, 무리 넷이면 20 의 (2,줄)·(29,줄) 이 모서리 8B·8C)이 떠 있는 프레임마다, 고친 롬의
옮긴 자리 사각형이 원래 사각형과 워드(타일·속성)째 같고 원래 모서리 자리에는 모서리가 없는지 본다. 화면에서도 창 사각형
픽셀이 원래 롬 화면의 원래 자리와 같은지 본다. 원래 롬과 선실 상태는 읽기만 하며 롬·기록은 --out 의 새 폴더에 쓴다.
  MESENCE=… python sfc/dq5/tools/dq5msgwindowcheck.py rom/dq5.sfc --state work/state/ship.mss
"""
import argparse
import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from PIL import Image

HERE = Path(__file__).resolve().parent
LEFT = 2
WIDTH, HEIGHT = 28, 7
CORNERS = (0x8B, 0x8C)
CASES = {'left': 0, 'right': 4}
SCENES = {
    'one': {'BATTLE': '00:1', 'SWAP': '05E:006,118,191;069:006', 'ROMPATCH': '10462C=9E'},
    'four': {'BATTLE': '00:1,01:1,02:1,03:1'},
}
# 견주는 구간에서 지나야 하는 곳: 메시지·FD ▼·줄 올리기·셋째 줄 끝 ▼, 무리 넷이면 넷째 줄 끝 ▼.
COVER = {'one': {'248C39', '24880A', '24A569', '24A519'}, 'four': {'248C39', '24A519', '24A523'}}
FROM, STEP, SHOTEVERY, MAXF = 560, 2, 16, 3400
TAPS = ','.join(['wait:400'] + ['a:8,wait:24'] * 110)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def same_until(calls, moved):
    """두 롬의 실행 기록이 처음 갈리는 프레임. 같은 입력이라도 몇 턴 뒤 갈릴 수 있어 그 앞까지만 견준다.
    한쪽 기록이 먼저 끝나면 그 뒤는 견줄 수 없어 짧은 기록의 마지막 프레임까지로 한다."""
    calls, moved = [line for line in calls if line], [line for line in moved if line]
    for a, b in zip(calls, moved):
        if a != b:
            return min(int(a.split()[0]), int(b.split()[0]))
    if len(calls) != len(moved):
        short = min(calls, moved, key=len)
        return int(short[-1].split()[0]) if short else 0
    return MAXF


def word(dump, x, y):
    at = (y * 32 + x) * 2
    return dump[at] | dump[at + 1] << 8


def window(dump, x, y, h):
    return [[word(dump, x + c, y + r) for c in range(WIDTH)] for r in range(h)]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', type=Path, required=True)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/msgwindowcheck')
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
        roms = {'original': original}
        for name, x in CASES.items():
            doc = {'format': 'dq5windows/1', 'windows': [{'index': '25', 'x': x}]}
            (out / f'{name}.json').write_text(json.dumps(doc) + '\n')
            for tool, extra in (('dq5windowwrite.py', ['patch', out / f'{name}.json', '-o', out / f'{name}.patch.json']),
                                ('dq5build.py', ['build', out / f'{name}.patch.json', '-o', out / f'{name}.sfc',
                                                 '--ips', out / f'{name}.ips'])):
                subprocess.run([sys.executable, str(HERE / tool), str(original), *map(str, extra)], check=True,
                               capture_output=True, text=True, timeout=120)
            roms[name] = out / f'{name}.sfc'
        libdir = subprocess.run(['krpatch', 'sfc', 'lua'], check=True, capture_output=True, text=True,
                                timeout=30).stdout.strip()

        def run(job):
            rom, scene = job
            dest = out / scene / rom
            dest.mkdir(parents=True)
            env = os.environ.copy()
            for key in ('PARTY', 'SET', 'POKE', 'ROMPATCH', 'TO', 'LATESET', 'SWAP'):
                env.pop(key, None)
            env.update(LIBDIR=libdir, STATE=str(state), SHOT_DIR=str(dest), DRIVER=str(HERE / 'lua/dq5warp.lua'),
                       FIELD='341,56', SET='2035=07', TEST=TAPS, FROM=str(FROM), STEP=str(STEP),
                       SHOTEVERY=str(SHOTEVERY), MAXF=str(MAXF), **SCENES[scene])
            with (dest / 'mesen.log').open('w') as log:
                subprocess.run([str(mesence), '--testrunner', str(roms[rom]), str(HERE / 'lua/dq5msgwindowcheck.lua'),
                                '--Snes.DisableFrameSkipping=true'], env=env, stdout=log, stderr=subprocess.STDOUT,
                               check=True, timeout=300)
            data = (dest / 'bg3.bin').read_bytes()
            return [data[i:i + 0x800] for i in range(0, len(data), 0x800)], (dest / 'exec.txt').read_text().split('\n')

        jobs = [(rom, scene) for scene in SCENES for rom in roms]
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            seen = dict(zip(jobs, pool.map(run, jobs)))
        results = []
        for scene in SCENES:
            dumps, calls = seen[('original', scene)]
            for name, x in CASES.items():
                moved, moved_calls = seen[(name, scene)]
                limit = same_until(calls, moved_calls)
                frames = mismatched = screens = 0
                for k, (a, b) in enumerate(zip(dumps, moved)):
                    frame = FROM + k * STEP
                    if frame >= limit:
                        break
                    top = next((r for r in (21, 20) if word(a, LEFT, r) & 0xFF in CORNERS
                                and word(a, LEFT + WIDTH - 1, r) & 0xFF in CORNERS), None)
                    if top is None:
                        continue
                    h = HEIGHT + 2 * (top == 20)
                    frames += 1
                    if window(b, x, top, h) != window(a, LEFT, top, h) or any(
                            word(b, c, top) & 0xFF in CORNERS for c in (LEFT, LEFT + WIDTH - 1)):
                        mismatched += 1
                        continue
                    shot = out / scene / 'original' / f'f{frame:05d}.png'
                    if not shot.is_file():
                        continue
                    before = Image.open(shot).convert('RGB')
                    after = Image.open(out / scene / name / f'f{frame:05d}.png').convert('RGB')
                    # 화면의 BG3 는 타일맵보다 몇 점 위로 밀려 있고 아래 테두리 아래로는 뒤 배경이 비치므로,
                    # 아래 테두리 위 줄의 4점 위에서 끊는다.
                    box = (LEFT * 8, top * 8, (LEFT + WIDTH) * 8, min(224, (top + h - 1) * 8 - 4))
                    moved_box = (x * 8, box[1], (x + WIDTH) * 8, box[3])
                    # 턴이 바뀌는 몇 프레임은 화면에 BG3 가 나오지 않는다. 그때는 옮기기 전 자리의 두 화면이 같다.
                    if before.crop(box).tobytes() == after.crop(box).tobytes():
                        continue
                    require(before.crop(box).tobytes() == after.crop(moved_box).tobytes(),
                            f'{scene}/{name} f{frame}: 화면 창 사각형이 원래 롬과 다름')
                    screens += 1
                kinds = {line.split()[1] for line in calls if line and int(line.split()[0]) < limit}
                results.append({'scene': scene, 'case': name, 'until': limit, 'frames': frames,
                                'mismatched': mismatched, 'screens': screens, 'calls': sorted(kinds)})
                require(frames and not mismatched, f'{scene}/{name}: 창 {frames}프레임 중 {mismatched}프레임이 다름')
                require(kinds >= COVER[scene], f'{scene}/{name}: {limit}프레임 전에 {sorted(COVER[scene] - kinds)} 를 지나지 않음')
        (out / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
        print(json.dumps(results, ensure_ascii=False))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.output:
            print(error.output, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
