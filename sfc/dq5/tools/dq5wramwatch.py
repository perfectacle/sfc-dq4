"""다른 검사 도구가 띄우는 MesenCE 실행마다 WRAM 범위의 읽기·쓰기를 PC 별로 센다(lua/dq5wramwatch.lua).

dq4 트랙의 dq4mesen.run·Runner 로 MesenCE 를 띄우는 도구(예: dq4ch1walkcheck.py)를 그대로 부르되, 띄울 스크립트를
감시 스크립트로 감싼다. 감싼 도구의 인자는 -- 뒤에 그대로 준다. 실행마다 [실행 폴더 이름, 프레임 수, 접근] 을
--out 의 watch-*.txt 로 남기고, 끝에 PC 별 합계와 범위 밖에서 온 PC 를 요약한다.

  MESENCE=… python sfc/dq5/tools/dq5wramwatch.py --range 1ABC-1BB0 --out work/wramwatch \\
      --tool sfc/dq4/tools/dq4ch1walkcheck.py -- --rom work/ch1/dq4-ch1.sfc --out work/ch1walk
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import runpy
import sys
import uuid

HERE = Path(__file__).resolve().parent
WATCH = HERE / 'lua' / 'dq5wramwatch.lua'


def wrap(mesen, low, high, out, slow=4):
    """dq4mesen 의 run·Runner 가 띄울 스크립트를 감시 스크립트로 바꾸고, 실행마다 기록 파일을 정한다.
    메모리 콜백이 에뮬레이션을 늦추므로 감싼 도구가 준 timeout 을 slow 배로 늘린다(늘리지 않으면 긴 구간이 끝나기
    전에 끊겨 세이브스테이트를 남기지 못한다)."""
    import os

    def env_for(script, kwargs):
        env = dict(kwargs.get('env') or os.environ)
        name = Path(kwargs.get('cwd') or '.').name or 'run'
        env.update(WATCH_FROM=f'{low:X}', WATCH_TO=f'{high:X}', WATCH_INNER=str(script),
                   WATCH_FILE=str(out / f'watch-{name}-{uuid.uuid4().hex[:8]}.txt'))
        kwargs['env'] = env
        if kwargs.get('timeout'):
            kwargs['timeout'] *= slow

    run, init = mesen.run, mesen.Runner.__init__

    def run_watched(mesence, rom, script, *args, **kwargs):
        env_for(script, kwargs)
        return run(mesence, rom, WATCH, *args, **kwargs)

    def init_watched(self, mesence, rom, script, *args, **kwargs):
        env_for(script, kwargs)
        init(self, mesence, rom, WATCH, *args, **kwargs)

    mesen.run, mesen.Runner.__init__ = run_watched, init_watched


def summarize(out):
    """watch-*.txt 를 모아 (접근 종류, PC) 별 합계와 실행 수·프레임 수."""
    by_pc, runs, frames = Counter(), 0, 0
    addrs = {}
    for path in sorted(out.glob('watch-*.txt')):
        runs += 1
        for line in path.read_text(encoding='utf-8').splitlines():
            parts = line.split()
            if not parts:
                continue
            if parts[0] == 'frames':
                frames += int(parts[1])
                continue
            kind, addr, pc, count = parts
            by_pc[kind, pc] += int(count)
            addrs.setdefault((kind, pc), set()).add(addr)
    rows = [{'kind': k, 'pc': pc, 'count': n, 'addresses': len(addrs[k, pc]),
             'first': min(addrs[k, pc]), 'last': max(addrs[k, pc])} for (k, pc), n in sorted(by_pc.items())]
    return {'runs': runs, 'frames': frames, 'pcs': rows}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--range', required=True, help='WRAM 기준 주소 범위(끝 포함), 예 1ABC-1BB0')
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--tool', required=True, type=Path, help='dq4mesen 으로 MesenCE 를 띄우는 검사 도구')
    ap.add_argument('--slow', type=int, default=4, help='감싼 도구의 MesenCE 시간 제한을 늘릴 배수')
    ap.add_argument('rest', nargs=argparse.REMAINDER, help='-- 뒤에 감쌀 도구의 인자')
    args = ap.parse_args()
    low, high = (int(v, 16) for v in args.range.split('-'))
    args.out.mkdir(parents=True, exist_ok=True)
    out = args.out.resolve()
    tool = args.tool.resolve()
    sys.path[:0] = [str(tool.parent), str(HERE.parents[1] / 'dq4' / 'tools')]
    import dq4mesen
    wrap(dq4mesen, low, high, out, args.slow)
    rest = args.rest[1:] if args.rest[:1] == ['--'] else args.rest
    sys.argv = [str(tool), *rest]
    code = 0
    try:
        runpy.run_path(str(tool), run_name='__main__')
    except SystemExit as stop:
        code = stop.code or 0
    summary = summarize(out)
    (out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(f"실행 {summary['runs']}번, {summary['frames']}프레임, 접근한 PC {len(summary['pcs'])}곳")
    for row in summary['pcs']:
        print(f"  {row['kind']} {row['pc']} {row['count']}회 {row['addresses']}곳 {row['first']}~{row['last']}")
    return code


if __name__ == '__main__':
    sys.exit(main())
