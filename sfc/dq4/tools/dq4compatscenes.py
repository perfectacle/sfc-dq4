"""호환성 프로브(dq4compatcheck probe)를 1장 걷기 밖의 장면 검사에도 붙인다(MesenCE 헤드리스).

장면 검사는 고치지 않고 그대로 띄운다. 띄울 때 DQ4_OPENBUS_LOG 를 주면 dq4mesen 이 띄우는 스크립트마다
lua/dq4openbus.lua 를 앞에 붙여 열린 버스·롬 거울 접근을 그 파일에 적는다. 읽은 바이트 캐시(dq4readset)가 MesenCE 를
건너뛰면 접근이 적히지 않으므로 DQ4_READSET=off 로 띄운다.

  장면   battle  dq4battlecheck(들판·탑 전투, 이름 창)
         save    dq4ch1savecheck(교회 저장 → 리셋 → 이어 하기, 전멸 → 교회). 출발 상태는 먼저 프로브 없이 1장 걷기 --units
         window  dq4windowcheck(가게·교회·여관·대화·전투 창, 창 글자의 높은 뱅크 코드). --window-rom·--symbols·
                 --symbols-rom 을 주어야 돈다
  범위   high    뱅크 40~7D 아래 절반(dq4openbus.lua 기본). 판정은 dq4compatcheck.probe_problems 와 같다
         io      뱅크 00~3F 의 열린 버스 구역 IO_RANGES. 우리 패치 코드(뱅크 40 이상, 또는 롬 장부의 단계가 쓴 자리)가
                 접근하면 실패, 원래 DQ5 코드의 접근은 적기만 한다

콜백이 많으면 MesenCE 가 느려져 장면이 시간 제한에 걸리므로 범위마다 장면을 따로 돌린다. 장면 검사가 실패해도 실패다.

  MESENCE=… LIBDIR=… uv run --locked python sfc/dq4/tools/dq4compatscenes.py --rom work/ch1/dq4-ch1-full.sfc \\
      --out 새폴더 [--scenes battle,save,window] [--ranges high,io] [--ledger work/ch1/ledger.json] \\
      [--window-rom work/ch1/dq4-ch1.sfc --symbols work/wc/wn.sym --symbols-rom work/wc/menu.sfc]
형식은 sfc/dq4/docs/dq4-compat-format.md 「장면 프로브」.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4compatcheck as cc  # noqa: E402

IO_RANGES = ','.join(f'00-3F:{r}' for r in ('2000-20FF', '2184-3FFF', '4000-4015', '4018-41FF', '4220-42FF',
                                             '4380-7FFF'))
RANGES = {'high': '', 'io': IO_RANGES}
SCENES = ('battle', 'save', 'window')
LINE = re.compile(r'([RW]) pc=(\w\w):(\w{4}) bank=(\w\w)(?: at=(\w{4}))?')


def patched_ranges(ledger):
    """롬 장부(dq4romledger)의 단계가 쓴 CPU 자리 [(뱅크, 처음, 끝)]."""
    out = []
    for stage in ledger.get('stages', []):
        for r in stage.get('ranges', []):
            a, b = r['cpu'].split('~')
            out.append((int(a[:2], 16), int(a[3:], 16), int(b[3:], 16)))
    return out


def ours(bank, pc, patched):
    """그 PC 가 우리 패치 코드인가: 뱅크 40 이상이거나 장부의 단계가 쓴 자리."""
    return bank >= 0x40 or any(b == bank and lo <= pc <= hi for b, lo, hi in patched)


def io_problems(lines, patched):
    """io 범위 기록 → (문제, 원래 DQ5 코드의 접근). BRK 줄은 dq4compatcheck.probe_problems 로 본다."""
    problems, dq5 = cc.probe_problems([x for x in lines if x.startswith('BRK')]), []
    for line in sorted(set(lines)):
        m = LINE.fullmatch(line)
        if not m:
            continue
        bank, pc = int(m[2], 16), int(m[3], 16)
        where = f'{m[4]}:{m[5] or "????"}'
        what = f'{m[2]}:{m[3]} 이 {where} 를 {"읽음" if m[1] == "R" else "씀"}'
        (problems if ours(bank, pc, patched) else dq5).append(what)
    return problems, dq5


def commands(scene, rng, a, out):
    """(장면, 범위) 를 도는 명령 목록. 앞 명령들은 프로브 없이(출발 상태 만들기), 마지막 명령에 프로브를 붙인다."""
    py = [sys.executable]
    dest = out / f'{scene}-{rng}'
    if scene == 'battle':
        return [], py + [str(HERE / 'dq4battlecheck.py'), '--rom', str(a.rom), '--out', str(dest), '--repeat', '1',
                         '--jobs', str(a.jobs)]
    if scene == 'save':
        walk = out / 'save-walk'
        pre = [] if walk.exists() else [py + [str(HERE / 'dq4ch1walkcheck.py'), '--rom', str(a.rom), '--out', str(walk),
                                              '--units', '--jobs', str(a.jobs)]]
        return pre, py + [str(HERE / 'dq4ch1savecheck.py'), '--rom', str(a.rom), '--states', str(walk), '--out', str(dest)]
    return [], py + [str(HERE / 'dq4windowcheck.py'), '--rom', str(a.window_rom), '--symbols', str(a.symbols),
                     '--symbols-rom', str(a.symbols_rom), '--out', str(dest), '--jobs', str(a.jobs), '--every']


def run_scene(scene, rng, a, out, patched):
    pre, cmd = commands(scene, rng, a, out)
    log = out / f'{scene}-{rng}.log'
    with log.open('w') as f:
        for c in pre:
            if subprocess.run(c, stdout=f, stderr=subprocess.STDOUT).returncode:
                return {'scene': scene, 'ranges': rng, 'status': 'failed', 'problems': [f'출발 상태 실패: {c[1]}']}
        bus = out / f'openbus-{scene}-{rng}.txt'
        env = dict(os.environ, DQ4_READSET='off', DQ4_OPENBUS_LOG=str(bus), DQ4_OPENBUS_RANGES=RANGES[rng])
        t0 = time.time()
        rc = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, env=env).returncode
    lines = bus.read_text(encoding='utf-8').splitlines() if bus.exists() else []
    if rng == 'high':
        problems, dq5 = cc.probe_problems(lines), []
    else:
        problems, dq5 = io_problems(lines, patched)
    if rc:
        problems.insert(0, f'장면 검사 실패(종료 {rc}, {log.name})')
    if not lines:
        problems.append('프로브 기록이 없음(프로브가 붙지 않았거나 장면이 돌지 않음)')
    return {'scene': scene, 'ranges': rng, 'status': 'failed' if problems else 'passed', 'problems': problems,
            'dq5_accesses': dq5, 'records': len(set(lines)),
            'high_bank_brk': sorted({x.split('op=')[1] for x in lines if x.startswith('BRK')}),
            'seconds': round(time.time() - t0)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', required=True, type=Path)
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--scenes', default=','.join(SCENES))
    ap.add_argument('--ranges', default=','.join(RANGES))
    ap.add_argument('--ledger', type=Path, help='롬 장부(기본: --rom 옆 ledger.json)')
    ap.add_argument('--jobs', type=int, default=3)
    ap.add_argument('--window-rom', type=Path)
    ap.add_argument('--symbols', type=Path)
    ap.add_argument('--symbols-rom', type=Path)
    a = ap.parse_args()
    if not os.environ.get('MESENCE'):
        ap.error('MESENCE 에 MesenCE 실행 파일을 주세요')
    scenes = a.scenes.split(',')
    if 'window' in scenes and not (a.window_rom and a.symbols and a.symbols_rom):
        ap.error('window 장면은 --window-rom·--symbols·--symbols-rom 이 있어야 함')
    a.rom = a.rom.resolve()
    for k in ('window_rom', 'symbols', 'symbols_rom'):
        if getattr(a, k):
            setattr(a, k, getattr(a, k).resolve())
    out = a.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f'{out} is not empty')
    out.mkdir(parents=True, exist_ok=True)
    ledger_path = a.ledger or a.rom.parent / 'ledger.json'
    if not ledger_path.exists():
        raise SystemExit(f'{ledger_path} 가 없음(dq4build.py 가 롬 옆에 둠)')
    patched = patched_ranges(json.loads(ledger_path.read_text()))
    results = [run_scene(s, r, a, out, patched) for s in scenes for r in a.ranges.split(',')]
    ok = all(r['status'] == 'passed' for r in results)
    (out / 'results.json').write_text(json.dumps({'status': 'passed' if ok else 'failed', 'scenes': results},
                                                 ensure_ascii=False, indent=1) + '\n')
    for r in results:
        print(json.dumps({k: v for k, v in r.items() if k != 'dq5_accesses'} | {'dq5_accesses': len(r['dq5_accesses'])},
                         ensure_ascii=False))
    print('통과' if ok else '실패')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
