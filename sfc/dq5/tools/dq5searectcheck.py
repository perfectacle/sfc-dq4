"""배를 탄 채 고르는 바다 구역 직사각형(01:85D8)의 경계를 MesenCE 에서 잰다.

01:8590 은 $1954 = 3 이면(견주기는 01:85A9 부터) $1948 = 2 일 때 둘째, 아니면 첫째 직사각형 [X0][X1][Y0][Y1](16비트)을 읽어
X0 ≤ $B6/2 < X1, Y0 ≤ $B8/2 < Y1 이면 안 구역(+8), 아니면 밖 구역(+9)을 고른다(코드 읽기). 경계마다 양쪽이 바다인
칸을 골라 dq5warp.lua 로 배를 띄우고(LATESET="1954=03;21BE|01", 둘째는 1948=02 도) 경계를 건너 저으며
lua/dq5searect.lua 로 걸음마다 $B6·$B8 과 고른 구역을 적는다. 첫째 직사각형의 X1(33) 경계는 양쪽이 바다인 칸이 없어,
x1p 는 첫째의 X1 을 06 으로 덮은 롬(ROMPATCH)에서 x0 과 같은 줄을 저어 05 → 06 을 건넌다.
  MESENCE=… python sfc/dq5/tools/dq5searectcheck.py rom/dq5.sfc --state work/state/ship.mss
"""
import argparse
import concurrent.futures
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from dq5map import Rom, lorom
from dq5progresscheck import environment, require, run, save_json

HERE = Path(__file__).resolve().parent
RECTS = 0x0185D8
# (이름, 직사각형, 시작 $B6·$B8, 젓는 쪽, 건너는 좌표 축, 경계 값의 자리)
CROSSINGS = (('x0', 0, '2,140', 'right', 'B6', 0), ('y0', 0, '10,128', 'down', 'B8', 2),
             ('y1', 0, '10,302', 'down', 'B8', 3), ('x0b', 1, '176,250', 'right', 'B6', 0),
             ('x1b', 1, '320,250', 'right', 'B6', 1), ('y0b', 1, '182,244', 'down', 'B8', 2),
             ('y1b', 1, '182,392', 'down', 'B8', 3), ('x1p', 0, '2,140', 'right', 'B6', 1, 0x06))


def rects(rom):
    """[(X0, X1, Y0, Y1, 안 구역, 밖 구역)] 두 개."""
    out = []
    for r in range(2):
        base = RECTS + r * 10
        out.append((*(rom.u16(base + k * 2) for k in range(4)), rom.u8(base + 8), rom.u8(base + 9)))
    return out


def cross(rom, name, rect, field, way, state, out, mesence, libdir, x1=None):
    dest = out / name
    env = environment(libdir, state, dest)
    late = '1954=03;21BE|01' + (';1948=02' if rect else '')
    env.update(DRIVER=str(HERE / 'lua/dq5warp.lua'), FIELD=field, LATESET=late, MAXF='1300', SETTLE='60',
               TEST=f'{way}:{100 if x1 is not None else 60},wait:60')
    if x1 is not None:
        env['ROMPATCH'] = f'{lorom(RECTS + rect * 10 + 2):X}={x1:02X}'
    run(mesence, rom, HERE / 'lua/dq5searect.lua', dest, env)
    text = (dest / 'sea.txt').read_text(encoding='utf-8')
    coords = re.findall(r'rect B6=(\d+) B8=(\d+) 1948=(\d+)', text)
    areas = re.findall(r'area ([0-9A-F]{2})', text)
    return [(int(x), int(y), int(a, 16)) for (x, y, _), a in zip(coords, areas)]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/searectcheck')
    args = ap.parse_args()
    if not args.mesence:
        ap.error('--mesence 또는 MESENCE가 필요함')
    try:
        rom, state, mesence = args.rom.resolve(), args.state.resolve(), Path(args.mesence).resolve()
        for path in (rom, state, mesence):
            require(path.is_file(), f'파일 없음: {path}')
        args.out.mkdir(parents=True, exist_ok=True)
        out = Path(tempfile.mkdtemp(prefix='run-', dir=args.out.resolve()))
        print(f'실행 출력: {out}', flush=True)
        libdir = subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True,
                                check=True, timeout=30).stdout.strip()
        boxes = rects(Rom(rom.read_bytes()))
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures = {c[0]: pool.submit(cross, rom, c[0], c[1], c[2], c[3], state, out, mesence, libdir, *c[6:])
                       for c in CROSSINGS}
            seen = {n: f.result() for n, f in futures.items()}
        checks, results = {}, {}
        for name, rect, _, _, axis, k, *patched in CROSSINGS:
            x0, x1, y0, y1, inside, outside = boxes[rect]
            x1 = patched[0] if patched else x1
            want = [(x, y, inside if x0 <= x >> 1 < x1 and y0 <= y >> 1 < y1 else outside) for x, y, _ in seen[name]]
            edge = (x0, x1, y0, y1)[k]
            values = [(x if axis == 'B6' else y) >> 1 for x, y, _ in seen[name]]
            checks[name] = bool(seen[name]) and seen[name] == want and edge - 1 in values and edge in values
            results[name] = {'경계': f'{axis}/2 = {edge:02X}', '걸음': [f'{x},{y}:{a:02X}' for x, y, a in seen[name]]}
            print(f'{name}: {axis}/2 경계 {edge:02X} — ' + ' '.join(f'{(x if axis == "B6" else y) >> 1:02X}:{a:02X}'
                                                              for x, y, a in seen[name]))
        save_json(out / 'results.json', {'rects': boxes, 'crossings': results, 'checks': checks})
        for key, ok in checks.items():
            print(f'{key}: {"통과" if ok else "불일치"}')
        require(all(checks.values()), '불일치: ' + ', '.join(k for k, ok in checks.items() if not ok))
        print(f'{len(checks)}건 통과')
        return 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
