"""창 자리·크기 쓰기를 MesenCE 전투에서 BG3 타일맵 버퍼로 확인한다.

슬라임 하나와의 전투(dq5warp.lua FIELD·BATTLE)에서 상태 창 17, 몬스터 목록 창 1B, 혼자일 때의 たたかう 창 87,
こうげき 창 1E 를 옮기고 1B 의 너비를 18 에서 14 로 줄인 롬과 원래 롬을 돌린다. 700·1000프레임(앞 셋·こうげき 창이 열린 때)의 BG3 타일맵 버퍼
7E:5000~ 에서 창 왼쪽 위 모서리 타일(8C)이 새 자리에 있고 원래 자리에서 사라졌는지 본다.
원래 롬과 선실 상태는 읽기만 하며 롬·기록은 --out 의 새 폴더에 쓴다.
  MESENCE=… python sfc/dq5/tools/dq5windowcheck.py rom/dq5.sfc --state work/state/ship.mss
"""
import argparse
import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import dq5mesen

HERE = Path(__file__).resolve().parent
CORNER = 0x8C
# (창, 원래 자리, 새 자리, 확인할 프레임)
# 1B 는 너비도 18 → 14 로 줄여 오른쪽 위 모서리가 (10 + 13, 16) 으로 오는지 본다.
NARROW = 14
MOVES = [('17', (2, 2), (12, 2), 700), ('1B', (10, 20), (10, 16), 700), ('87', (2, 20), (12, 12), 700),
         ('1E', (2, 18), (20, 8), 1000)]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', type=Path, required=True)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/windowcheck')
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
        doc = {'format': 'dq5windows/1', 'windows': [
            {'index': n, **{k: v for k, v, o in zip('xy', new, old) if v != o}} for n, old, new, _ in MOVES]}
        doc['windows'][1]['w'] = NARROW
        (out / 'windows.json').write_text(json.dumps(doc) + '\n')
        for tool, extra in (('dq5windowwrite.py', ['patch', out / 'windows.json', '-o', out / 'windows.patch.json']),
                            ('dq5build.py', ['build', out / 'windows.patch.json', '-o', out / 'moved.sfc',
                                             '--ips', out / 'moved.ips'])):
            subprocess.run([sys.executable, str(HERE / tool), str(original), *map(str, extra)], check=True,
                           capture_output=True, text=True, timeout=120)
        libdir = subprocess.run(['krpatch', 'sfc', 'lua'], check=True, capture_output=True, text=True,
                                timeout=30).stdout.strip()

        def run(case):
            name, rom = case
            dest = out / name
            dest.mkdir()
            env = os.environ.copy()
            for key in ('PARTY', 'SET', 'POKE', 'ROMPATCH', 'TO', 'LATESET'):
                env.pop(key, None)
            env.update(LIBDIR=libdir, STATE=str(state), SHOT_DIR=str(dest), DRIVER=str(HERE / 'lua/dq5warp.lua'),
                       FIELD='341,56', BATTLE='00:1', TEST='wait:400,a:8,wait:200', FRAMES='700,1000', MAXF='1100')
            with (dest / 'mesen.log').open('w') as log:
                dq5mesen.testrunner(str(mesence), str(rom), str(HERE / 'lua/dq5windowcheck.lua'),
                                    '--Snes.DisableFrameSkipping=true', env=env, stdout=log, stderr=subprocess.STDOUT,
                                    check=True, timeout=180)
            return {f: (dest / f'bg3-f{f:05d}.bin').read_bytes() for f in (700, 1000)}

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            seen = dict(zip(('original', 'moved'), pool.map(run, [('original', original), ('moved', out / 'moved.sfc')])))
        results = []
        for n, old, new, frame in MOVES:
            def tile(case, at):
                return seen[case][frame][(at[1] * 32 + at[0]) * 2]
            got = {'original_old': tile('original', old), 'original_new': tile('original', new),
                   'moved_old': tile('moved', old), 'moved_new': tile('moved', new)}
            require(got['original_old'] == CORNER and got['moved_new'] == CORNER and
                    got['original_new'] != CORNER and got['moved_old'] != CORNER,
                    f'창 {n}: 모서리 타일 {got}')
            if n == '1B':
                right = (new[0] + NARROW - 1, new[1])
                require(tile('moved', right) == CORNER and tile('moved', (new[0] + 17, new[1])) != CORNER,
                        f'창 1B: 너비 {NARROW} 의 오른쪽 모서리가 {right} 에 없음')
                got['moved_right'] = tile('moved', right)
            results.append({'window': n, 'from': old, 'to': new, 'frame': frame,
                            **{k: f'{v:02X}' for k, v in got.items()}})
        (out / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
        print(json.dumps(results))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.output:
            print(error.output, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
