"""호환성 프로브(dq4compatcheck probe)를 1장 걷기 밖의 장면 검사에도 붙인다(MesenCE 헤드리스).

장면 검사는 고치지 않고 그대로 띄운다. 띄울 때 DQ4_OPENBUS_LOG 를 주면 dq4mesen 이 띄우는 스크립트마다
lua/dq4openbus.lua 를 앞에 붙여 열린 버스·롬 거울 접근을 그 파일에 적는다. 읽은 바이트 캐시(dq4readset)가 MesenCE 를
건너뛰면 접근이 적히지 않으므로 DQ4_READSET=off 로 띄운다.

  장면   battle  dq4battlecheck(들판·탑 전투, 이름 창)
         save    dq4ch1savecheck(교회 저장 → 리셋 → 이어 하기, 전멸 → 교회). 출발 상태는 먼저 프로브 없이 1장 걷기 --units
         window  dq4windowcheck(가게·교회·여관·대화·전투 창, 창 글자의 높은 뱅크 코드). --window-rom·--symbols·
                 --symbols-rom 을 주어야 돈다
  범위   high    뱅크 40~7D 아래 절반(dq4openbus.lua 기본). 판정은 dq4compatcheck.probe_problems 와 같다
         io      뱅크 00~3F 의 열린 버스 구역 IO_RANGES. 우리 패치 코드(뱅크 40 이상, 또는 롬 장부의 단계가 쓴 자리)의
                 접근, DQ5_ALLOWED(PC·접근 뱅크·주소 범위)밖의 원래 DQ5 접근, 해석하지 못한 줄은 실패

콜백이 많으면 MesenCE 가 느려져 장면이 시간 제한에 걸리므로 범위마다 장면을 따로 돌린다. (장면, 범위) 는 기본으로 모두
함께 돌고(--parallel), 띄우는 MesenCE 수는 tools/headless_slots 의 자리가 묶는다. 장면 검사가 실패하거나(창 검사는 장면마다 끝까지 돌고 잰 프레임이 있어야 함) 기록이 없어도 실패다. 캐시는
읽지도(DQ4_READSET=off) 쓰지도(DQ4_READSET_STORE=off) 않는다.

  MESENCE=… LIBDIR=… uv run --locked python sfc/dq4/tools/dq4compatscenes.py --rom work/ch1/dq4-ch1-full.sfc \\
      --out 새폴더 [--scenes battle,save,window] [--ranges high,io] [--parallel 6] [--jobs N] [--ledger work/ch1/ledger.json] \\
      [--window-rom work/ch1/dq4-ch1.sfc --symbols work/wc/wn.sym --symbols-rom work/wc/menu.sfc]
형식은 sfc/dq4/docs/dq4-compat-format.md 「장면 프로브」.
"""
import argparse
import concurrent.futures
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
import dq4shards  # noqa: E402

IO_RANGES = ','.join(f'00-3F:{r}' for r in ('2000-20FF', '2184-3FFF', '4000-4015', '4018-41FF', '4220-42FF',
                                             '4380-7FFF'))
RANGES = {'high': '', 'io': IO_RANGES}
SCENES = ('battle', 'save', 'window')
LINE = re.compile(r'([RW]) pc=(\w\w):(\w{4}) bank=(\w\w)(?: at=(\w{4}))?')


# 원래 DQ5 코드의 io 접근 가운데 허용하는 것: (PC, 접근 뱅크, 처음, 끝, 까닭). PC 는 MesenCE 읽기 콜백의 cpu.pc 라
# 접근한 명령의 다음 주소다. 이 밖의 원래 DQ5 접근도 실패로 친다
DQ5_ALLOWED = [
    ('06:F536', 0x3D, 0x4380, 0x4380, '06:F534 LDA ($00),Y: 가게 목록 첫 바이트(키)'),
    ('06:F53D', 0x3D, 0x2000, 0x7FFF, '06:F53B LDA ($00),Y: 가게 목록의 다음 바이트'),
]


def patched_ranges(ledger):
    """롬 장부(dq4romledger)의 단계가 쓴 CPU 자리 [(뱅크, 처음, 끝)]. 뱅크를 넘는 범위(LoROM 은 뱅크마다 8000~FFFF)는
    뱅크마다 나눈다."""
    out = []
    for stage in ledger.get('stages', []):
        for r in stage.get('ranges', []):
            a, b = r['cpu'].split('~')
            b1, lo, b2, hi = int(a[:2], 16), int(a[3:], 16), int(b[:2], 16), int(b[3:], 16)
            if b1 == b2:
                out.append((b1, lo, hi))
                continue
            out.append((b1, lo, 0xFFFF))
            out += [(bank, 0x8000, 0xFFFF) for bank in range(b1 + 1, b2)]
            out.append((b2, 0x8000, hi))
    return out


def ours(bank, pc, patched):
    """그 PC 가 우리 패치 코드인가: 뱅크 40 이상이거나 장부의 단계가 쓴 자리."""
    return bank >= 0x40 or any(b == bank and lo <= pc <= hi for b, lo, hi in patched)


def dq5_allowed(pc, bank, at):
    """원래 DQ5 코드의 그 접근이 DQ5_ALLOWED 안인가."""
    return any(p == pc and b == bank and lo <= at <= hi for p, b, lo, hi, _ in DQ5_ALLOWED)


def io_problems(lines, patched):
    """io 범위 기록 → (문제, 허용한 원래 DQ5 코드의 접근). BRK 줄은 dq4compatcheck.probe_problems 로 본다. 우리 코드의
    접근, DQ5_ALLOWED 밖의 원래 DQ5 접근, 해석하지 못한 줄은 문제다."""
    problems, dq5 = cc.probe_problems([x for x in lines if x.startswith('BRK')]), []
    for line in sorted(set(lines)):
        if line.startswith('BRK'):
            continue
        m = LINE.fullmatch(line)
        if not m or m[5] is None:
            problems.append(f'해석하지 못한 기록 줄: {line}')
            continue
        bank, pc = int(m[2], 16), int(m[3], 16)
        at = int(m[5], 16)
        what = f'{m[2]}:{m[3]} 이 {m[4]}:{m[5]} 를 {"읽음" if m[1] == "R" else "씀"}'
        if ours(bank, pc, patched):
            problems.append(what)
        elif dq5_allowed(f'{m[2]}:{m[3]}', int(m[4], 16), at):
            dq5.append(what)
        else:
            problems.append(f'{what}(원래 DQ5 코드, DQ5_ALLOWED 밖)')
    return problems, dq5


def window_frames(every=True):
    """dq4windowcheck 가 장면마다 덤프하는 프레임 수(--every 면 EVERY 구간을 더함)."""
    import dq4windowcheck as wck
    out = {}
    for sc in wck.scenes('ship', 'party', 'shop', 'battle'):
        frames = set(sc[5]) | (set(wck.EVERY.get(sc[0], ())) if every else set())
        out[sc[0]] = len(frames)
    return out


def window_reached(dest, want=None):
    """창 검사가 장면마다 끝까지 돌았는가(dq4windowcheck 는 장면이 돌지 않아도 0 으로 끝날 수 있다). 장면마다 MesenCE 가
    0 으로 끝나고, 덤프한 프레임(v*.bin) 수가 그 장면이 덤프할 프레임 수(window_frames)와 같아야 한다. 문제 목록."""
    info = dest / 'readset.json'
    if not info.exists():
        return ['창 검사 readset.json 없음']
    want = window_frames() if want is None else want
    bad = []
    for name, i in json.loads(info.read_text()).items():
        got = len(list((dest / name).glob('v*.bin')))
        if i.get('timed_out') or i.get('returncode') not in (0, None):
            bad.append(f'창 장면 {name}: 종료 {i.get("returncode")}, 시간 초과 {i.get("timed_out")}')
        elif name not in want:
            bad.append(f'창 장면 {name}: 덤프할 프레임 수를 모름')
        elif got != want[name]:
            bad.append(f'창 장면 {name}: 덤프한 프레임 {got}, 기대 {want[name]}')
    return bad


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
                return {'scene': scene, 'ranges': rng, 'status': 'failed', 'problems': [f'출발 상태 실패: {c[1]}'],
                        'dq5_accesses': [], 'records': 0, 'pcs': [], 'high_bank_brk': [], 'seconds': 0}
        bus = out / f'openbus-{scene}-{rng}.txt'
        env = dict(os.environ, DQ4_READSET='off', DQ4_READSET_STORE='off', DQ4_OPENBUS_LOG=str(bus),
                   DQ4_OPENBUS_RANGES=RANGES[rng])
        t0 = time.time()
        rc = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, env=env).returncode
    lines = bus.read_text(encoding='utf-8').splitlines() if bus.exists() else []
    if rng == 'high':
        problems, dq5 = cc.probe_problems(lines), []
    else:
        problems, dq5 = io_problems(lines, patched)
    if rc:
        problems.insert(0, f'장면 검사 실패(종료 {rc}, {log.name})')
    if scene == 'window':
        problems += window_reached(out / f'{scene}-{rng}')
    if not lines:
        problems.append('프로브 기록이 없음(프로브가 붙지 않았거나 장면이 돌지 않음)')
    return {'scene': scene, 'ranges': rng, 'status': 'failed' if problems else 'passed', 'problems': problems,
            'dq5_accesses': dq5, 'records': len(set(lines)),
            'pcs': sorted({m[2] + ':' + m[3] for m in map(LINE.fullmatch, set(lines)) if m}),
            'high_bank_brk': sorted({x.split('op=')[1] for x in lines if x.startswith('BRK')}),
            'seconds': round(time.time() - t0)}


def run_pairs(pairs, run, save_walk, parallel):
    """(장면, 범위) 마다 run(pair) 를 parallel 개까지 함께 돌려 pairs 순서대로 돌려준다. 장면 검사마다 MesenCE 를 여럿
    띄우고 tools/headless_slots 가 전체 수를 묶는다. save_walk(저장 장면의 출발 상태 만들기, 성공이면 참)는 다른 장면과
    함께 한 번만 돌고, 저장 장면만 그것을 기다린다."""
    with concurrent.futures.ThreadPoolExecutor(1) as walker:
        walked = walker.submit(save_walk) if save_walk else None

        def one(pair):
            if pair[0] == 'save' and not (walked and walked.result()):
                return {'scene': pair[0], 'ranges': pair[1], 'status': 'failed',
                        'problems': ['저장 장면 출발 상태(1장 걷기)를 만들지 못함(save-walk.log)'], 'dq5_accesses': [],
                        'records': 0, 'pcs': [], 'high_bank_brk': [], 'seconds': 0}
            return run(pair)

        return dq4shards.pmap(one, pairs, parallel)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', required=True, type=Path)
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--scenes', default=','.join(SCENES))
    ap.add_argument('--ranges', default=','.join(RANGES))
    ap.add_argument('--ledger', type=Path, help='롬 장부(기본: --rom 옆 ledger.json)')
    ap.add_argument('--jobs', type=int, default=dq4shards.jobs(), help='장면 검사 하나가 함께 띄우는 MesenCE 수(기본 HEADLESS_SLOTS)')
    ap.add_argument('--parallel', type=int, default=len(SCENES) * len(RANGES),
                    help='함께 도는 (장면, 범위) 수. 기본은 모두(MesenCE 수는 자리가 묶음)')
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
    pairs = [(s, r) for s in scenes for r in a.ranges.split(',')]
    # 장면 검사는 서장 끝 상태를 캐시에서 받는다. 캐시가 비어 있으면 프로브를 붙인 채 서장을 걷게 되는데, 그때 MesenCE 가
    # 출력 없이 끝난 일이 있었다(서장은 dq4-openbus-probe 가 본다). 그래서 롬마다 서장 끝 상태를 프로브 없이 먼저 만든다
    roms = {a.rom} | ({a.window_rom} if 'window' in scenes else set())

    def warm(k, rom):
        with (out / f'warm-{k}.log').open('w') as f:
            return subprocess.run([sys.executable, str(HERE / 'dq4ch1walkcheck.py'), '--rom', str(rom), '--out',
                                   str(out / f'warm-{k}'), '--until', 'prologue'], stdout=f, stderr=subprocess.STDOUT).returncode

    ordered = sorted(roms)
    for k, (rom, rc) in enumerate(zip(ordered, dq4shards.pmap(lambda k: warm(k, ordered[k]), range(len(ordered))))):
        if rc:
            raise SystemExit(f'서장 끝 상태를 만들지 못함: {rom.name}(warm-{k}.log)')

    def save_walk():
        # 저장 장면의 출발 상태는 범위마다 같은 것을 쓰므로 한 번만 만든다
        pre, _ = commands('save', 'high', a, out)
        with (out / 'save-walk.log').open('w') as f:
            return all(subprocess.run(c, stdout=f, stderr=subprocess.STDOUT).returncode == 0 for c in pre)

    results = run_pairs(pairs, lambda p: run_scene(*p, a, out, patched), save_walk if 'save' in scenes else None,
                        a.parallel)
    ok = all(r['status'] == 'passed' for r in results)
    (out / 'results.json').write_text(json.dumps({'status': 'passed' if ok else 'failed', 'scenes': results},
                                                 ensure_ascii=False, indent=1) + '\n')
    for r in results:
        print(json.dumps({k: v for k, v in r.items() if k != 'dq5_accesses'} | {'dq5_accesses': len(r.get('dq5_accesses', []))},
                         ensure_ascii=False))
    print('통과' if ok else '실패')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
