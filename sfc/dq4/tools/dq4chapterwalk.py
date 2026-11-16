"""장 걷기 검사(2장 dq4ch2walkcheck.py, 3장 dq4ch3walkcheck.py)가 함께 쓰는 틀(MesenCE 헤드리스).

장마다 「출발 상태」(그 장 첫머리가 끝나 조작이 풀린 세이브스테이트) 하나를 만들어 캐시하고, 그 뒤 구간 표를 순간이동
구간마다 묶음으로 나눠 묶음마다 출발 상태에서 따로 걷는다. 묶음 첫 구간에는 앞 구간들의 want·off 와 기록 효과
(effects)를 SET·PARTY 로 둔다. 걷기·순간이동·판정은 1장 검사(dq4ch1walkcheck.segment)의 것이다.

장 모듈이 내놓는 것: SEGMENTS(구간 표), HEAD(표 앞쪽의 머리 구간 수. 머리는 출발 상태를 만드는 데만 걷는다),
head(mesence, rom, data, out, cache) → (출발 상태, 머리 결과), units(), walk_unit(mesence, rom, data, out, unit, base,
seed). walk_unit 은 이 모듈의 walk_unit 에 그 장의 flag 표·효과·들르는 곳·전투 패치를 넘긴다.

구간 선택은 dq4ch1walkcheck.SEGMENTS 의 것(want·off·map·field·items·poke·maxf·changes·after)에 더해
  cell   걷기 구간 끝에 주인공이 선 셀 (x, y)
  bytes  {flag 표 이름: 값} 끝 바이트(마스크 FF 로 표에 둔 칸)
  battle 사건 전투 몬스터를 덮는 롬 패치(장 모듈의 battle(data, kind))
  set    그 구간 시작에 한 번 더 두는 SET(뒤 묶음에는 이어지지 않는다. 이어져야 하는 기록은 effects 로)
"""
import argparse
import concurrent.futures
import inspect
import json
import os
import re
import shutil
import time
from pathlib import Path

import dq4ch1walkcheck as wc


def units(segments, head):
    """머리 뒤 구간을 묶음으로 나눈다: 순간이동 구간마다 새 묶음."""
    out = []
    for i in range(head, len(segments)):
        if segments[i][1] == 'warp' or not out:
            out.append([i])
        else:
            out[-1].append(i)
    return out


def setup(segments, head, first, flags, effects):
    """first 번째 구간 앞까지 걸었다면 켜져 있을 flag·기록(SET)과 동료(PARTY). 머리 구간의 flag 는 출발 상태에 이미
    있으므로 머리 뒤 구간만 센다."""
    return wc.setup(segments[head:], first - head, flags, effects)


def battle_patch(data, kind, every):
    """사건 전투 몬스터(every: 그 장 사건 모듈 BATTLES 의 몬스터 번호들)를 덮는 ROMPATCH. win 은 HP 1·수비 0(1장
    boss_patch 와 같음), weak 는 win 에 공격 0·MP 0·행동 여섯 모두 たたかう(일행이 다치지 않음), lose 는 HP 1000·공격
    511·민첩 255·행동 모두 たたかう(일행이 먼저 쓰러짐). 「weak:5A+lose:4C」 처럼 + 로 잇고 : 뒤에 몬스터(16진, 쉼표)를
    주면 그 몬스터만 덮는다."""
    out = []
    for piece in kind.split('+'):
        how, _, only = piece.partition(':')
        for n in [int(m, 16) for m in only.split(',')] if only else every:
            base = wc.MONSTERS + n * 25
            if how in ('win', 'weak'):
                out += [f'{base + 2:X}=00', f'{base + 3:X}=01',
                        f'{base + 8:X}={data[base + 8] & ~(0xC0 if how == "weak" else 0x40) & 0xFF:02X}',
                        f'{base + 10:X}={data[base + 10] & ~0x07 & 0xFF:02X}']
                if how == 'weak':
                    out += [f'{base + 1:X}=00', f'{base + 4:X}=00', *(f'{base + k:X}=73' for k in range(17, 23))]
            elif how == 'lose':
                out += [f'{base:X}=FF', f'{base + 1:X}=FF', f'{base + 3:X}=E8', f'{base + 8:X}={data[base + 8] | 0x80:02X}',
                        f'{base + 10:X}={data[base + 10] & ~0x07 | 0x03:02X}']
                # 행동도 모두 たたかう: 주문·ようすをみる 를 고르면 진 판이 구간 프레임 안에 끝나지 않았다(bsnes, 비비안 8E)
                out += [f'{base + k:X}=73' for k in range(17, 23)]
            else:
                raise ValueError(f'전투 선택 {kind}: win·weak·lose')
    return ';'.join(out)


def walk_unit(mesence, rom, data, out, unit, base, seed, segments, head, flags, effects, hops, battle):
    """한 묶음을 출발 상태 base 에서 걷는다. effects(data) 는 구간 이름 → 기록 효과, hops 는 출발 상태와 같은 맵으로
    순간이동할 때 먼저 들를 곳({맵: 'GG/MM,x,y'}), battle(data, kind) 는 구간 선택 battle 의 롬 패치."""
    extra, party = setup(segments, head, unit[0], flags, effects(data) if data is not None else {})
    state, results = base, []
    name, how, arg, _ = segments[unit[0]]
    if how == 'warp' and arg.split(',')[0] in hops:
        # dq5warp.lua 는 같은 맵 안의 순간이동이면 목적지 칸에 꼭 맞게 서야 도착으로 본다. 이웃 맵을 거친다
        hop = hops[arg.split(',')[0]]
        r = wc.segment(mesence, rom, state, out / f'{name}-hop', (f'{name}-hop', 'warp', hop, {'map': hop[:5]}),
                       wc.NO_ENCOUNTERS, extra, party, seed, flags=flags)
        if r['status'] != 'passed':
            return [r]
        state, extra, party = out / f'{name}-hop' / 'end.mss', '', ''
    for k, i in enumerate(unit):
        seg = segments[i]
        patch = wc.NO_ENCOUNTERS + (';' + battle(data, seg[3]['battle']) if 'battle' in seg[3] else '')
        start = ';'.join(v for v in (extra if k == 0 else '', seg[3].get('set', '')) if v)
        r = wc.segment(mesence, rom, state, out / seg[0], seg, patch, start, party if k == 0 else '', seed, flags=flags)
        more = [p for p in (end_cell_problem(out / seg[0], seg), *end_byte_problems(out / seg[0], seg)) if p]
        if more:
            r = {**r, 'status': 'failed', 'problems': r['problems'] + more}
        results.append(r)
        if r['status'] != 'passed':
            break
        state = out / seg[0] / 'end.mss'
    return results


def end_cell_problem(dest, seg):
    """선택 cell 이 있는 걷기 구간에서 끝에 선 셀이 다르면 그 까닭."""
    name, how, _, opt = seg
    if 'cell' not in opt or how != 'walk':
        return None
    log = dest / 'walk.txt'
    found = re.search(r'end map \w\w/\w\w x=(\d+) y=(\d+)', log.read_text(encoding='utf-8')) if log.exists() else None
    got = (int(found[1]), int(found[2])) if found else None
    return None if got == tuple(opt['cell']) else f"끝 셀 {got}, 기대 {tuple(opt['cell'])}"


def end_byte_problems(dest, seg):
    """선택 bytes({FLAGS 이름: 값})가 있는 걷기 구간에서 끝 값이 다른 칸들. walk.lua 는 FLAGS 의 바이트를 이름=값으로 찍는다."""
    name, how, _, opt = seg
    if 'bytes' not in opt or how != 'walk':
        return []
    log = dest / 'walk.txt'
    seen = dict(re.findall(r'^(\w+)=([0-9A-F]+)$', log.read_text(encoding='utf-8'), re.M)) if log.exists() else {}
    return [f'{k} = {seen.get(k)}, 기대 {v:02X}' for k, v in opt['bytes'].items()
            if k not in seen or int(seen[k], 16) & 0xFF != v]


def compare_runs(first, second):
    """두 번 걸은 묶음 결과에서 구간 기록 SHA-1 이 다른 구간의 까닭."""
    problems = {}
    for a, b in zip(first, second):
        if a.get('trace') != b.get('trace') or a['status'] != b['status']:
            problems[a['name']] = f"두 번 걸은 기록이 다름: {a.get('trace')}/{a['status']} ≠ {b.get('trace')}/{b['status']}"
    if len(first) != len(second):
        problems['_'] = f'두 번 걸은 구간 수가 다름: {len(first)} ≠ {len(second)}'
    return problems


def main(chapter, doc, rom_help, base_help):
    """장 걷기 검사의 명령줄. chapter 는 장 모듈(SEGMENTS·HEAD·head·units·walk_unit)."""
    ap = argparse.ArgumentParser(description=doc, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', required=True, type=Path, help=rom_help)
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--jobs', type=int, default=6, help='함께 띄울 MesenCE 수')
    ap.add_argument('--base', type=Path, help=base_help)
    ap.add_argument('--only', help='이 구간으로 시작하는 묶음만(쉼표로 여럿)')
    ap.add_argument('--repeat', type=int, default=1, choices=(1, 2), help='2 면 묶음마다 두 번 걸어 기록을 견줌')
    wc.add_seed_args(ap)
    args = ap.parse_args()
    seeds = wc.seeds_of(args)
    mesence = Path(os.environ['MESENCE'])
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f'{out} is not empty')
    out.mkdir(parents=True, exist_ok=True)
    rom = out / 'c.sfc'
    shutil.copyfile(args.rom.resolve(), rom)
    data = rom.read_bytes()
    cache = None if args.no_state_cache else wc.StateCache(data)
    began = time.monotonic()
    segments, head = chapter.SEGMENTS, chapter.HEAD
    names = [s[0] for s in segments]
    groups = chapter.units()
    if args.only:
        wanted = args.only.split(',')
        unknown = [w for w in wanted if w not in names[head:]]
        if unknown:
            raise SystemExit(f'없는 구간: {", ".join(unknown)}')
        groups = [u for u in groups if names[u[0]] in wanted]
    if args.base:
        base, head_results = args.base.resolve(), []
    else:
        # 머리도 두 번 걸어 견주는 장(head 가 repeat 를 받음)은 --repeat 를 넘긴다
        more = {'repeat': args.repeat} if 'repeat' in inspect.signature(chapter.head).parameters else {}
        base, head_results = chapter.head(mesence, rom, data, out, cache, **more)
        for r in head_results:
            print(json.dumps(r, ensure_ascii=False), flush=True)
    runs = {s: [] for s in seeds}
    unit_seconds = {}
    repeat_problems = {}
    if base is not None:
        def one(seed, unit, n):
            t0 = time.monotonic()
            dest = wc.seed_dir(out, seed, seeds) / (f'run-{n}' if args.repeat > 1 else '')
            rs = chapter.walk_unit(mesence, rom, data, dest, unit, base, seed)
            return rs, round(time.monotonic() - t0)
        with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
            jobs = {(s, tuple(u), n): pool.submit(one, s, u, n)
                    for s in seeds for u in groups for n in range(1, args.repeat + 1)}
            for job in concurrent.futures.as_completed(jobs.values()):
                for r in job.result()[0]:
                    print(json.dumps(r, ensure_ascii=False), flush=True)
        for s in seeds:
            for u in groups:
                rs, secs = jobs[s, tuple(u), 1].result()
                unit_seconds[f'{s}:{names[u[0]]}'] = secs
                if args.repeat > 1:
                    bad = compare_runs(rs, jobs[s, tuple(u), 2].result()[0])
                    for r in rs:
                        if r['name'] in bad:
                            r['problems'] = r['problems'] + [bad[r['name']]]
                            r['status'] = 'failed'
                    if '_' in bad:
                        repeat_problems[f'{s}:{names[u[0]]}'] = bad['_']
                runs[s] += rs
    head_ok = base is not None and all(r['status'] == 'passed' for r in head_results)
    expected = sum(len(u) for u in groups)
    per_seed = [{'seed': s, 'rng': wc.rng_for(s),
                 'status': 'passed' if head_ok and len(rs) == expected and all(r['status'] == 'passed' for r in rs)
                 and not any(k.startswith(f'{s}:') for k in repeat_problems) else 'failed',
                 'segments': rs} for s, rs in runs.items()]
    ok = head_ok and all(r['status'] == 'passed' for r in per_seed)
    report = {'status': 'passed' if ok else 'failed', 'seconds': round(time.monotonic() - began),
              'state_cache': 'off' if cache is None or args.base else
              'hit' if head_results and head_results[0].get('cached') else 'miss',
              'repeat': args.repeat, 'head': head_results, 'unit_seconds': unit_seconds,
              'repeat_problems': repeat_problems, 'seeds': per_seed}
    (out / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n')
    print(json.dumps({'status': report['status'], 'seconds': report['seconds'], 'state_cache': report['state_cache'],
                      'units': len(groups), 'unit_seconds': unit_seconds,
                      'failed': [f"{s['seed']}:{r['name']}" for s in per_seed for r in s['segments']
                                 if r['status'] != 'passed']}, ensure_ascii=False))
    return 0 if ok else 1
