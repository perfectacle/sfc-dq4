"""폴더의 단위 테스트 파일(test_*.py)을 걸리는 시간이 고르게 n 조각으로 나눠, k 번째 조각의 모듈 이름을 찍는다.

CI test 잡이 오래 걸리는 트랙을 조각으로 나눠 함께 돌릴 때 쓴다. 조각을 모두 모으면 `unittest discover -p 'test_*.py'`
가 고르는 파일과 같다. 파일마다 시간은 unitshard-times.json(저장소 경로: 초)에서 읽고, 없는 파일은 그 평균으로 본다.
시간이 어긋나도 조각이 고르지 않을 뿐 빠지는 테스트는 없다.

  python tools/unitshard.py sfc/dq4/tools 1 2      # 첫째 조각(그 폴더에서 python -m unittest 에 넘길 이름)
  python tools/unitshard.py --record sfc/dq4/tools # 파일마다 돌려 시간을 고쳐 씀
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TIMES = Path(__file__).resolve().parent / 'unitshard-times.json'


def test_files(folder):
    """discover 처럼 그 폴더 바로 아래의 test_*.py(저장소 경로, 이름 차례)."""
    return sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / folder).glob('test_*.py'))


def load_times():
    try:
        return json.loads(TIMES.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def shards(files, n, times):
    """files 를 n 조각으로(긴 것부터 가장 가벼운 조각에 넣음). 같은 입력이면 같은 결과."""
    known = [times[f] for f in files if f in times]
    default = sum(known) / len(known) if known else 1.0
    out = [[] for _ in range(n)]
    loads = [0.0] * n
    for f in sorted(files, key=lambda f: (-times.get(f, default), f)):
        i = loads.index(min(loads))
        out[i].append(f)
        loads[i] += times.get(f, default)
    return [sorted(s) for s in out]


def record(folders):
    times = load_times()
    for folder in folders:
        for f in test_files(folder):
            t0 = time.time()
            subprocess.run([sys.executable, '-m', 'unittest', '-q', Path(f).stem], cwd=ROOT / folder,
                           capture_output=True)
            times[f] = round(time.time() - t0, 1)
            print(f'{times[f]:6.1f} {f}')
    TIMES.write_text(json.dumps(dict(sorted(times.items())), indent=1, ensure_ascii=False) + '\n', encoding='utf-8')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--record', action='store_true', help='폴더마다 테스트 파일을 하나씩 돌려 시간을 적는다')
    ap.add_argument('folder', nargs='+', help='폴더(저장소 경로). --record 가 아니면 폴더, k, n')
    a = ap.parse_args()
    if a.record:
        record(a.folder)
        return 0
    if len(a.folder) != 3:
        ap.error('폴더 k n')
    folder, k, n = a.folder[0], int(a.folder[1]), int(a.folder[2])
    if not 1 <= k <= n:
        ap.error('1 <= k <= n')
    part = shards(test_files(folder), n, load_times())[k - 1]
    print(' '.join(Path(f).stem for f in part))
    return 0


if __name__ == '__main__':
    sys.exit(main())
