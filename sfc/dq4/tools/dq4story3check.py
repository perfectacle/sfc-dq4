"""3장 첫머리부터 장 끝 상자까지 순간이동 없이 한 줄로 걷는 검사(MesenCE 헤드리스, 배포 관문 가드 dq4-ch3-story).

3장 걷기 검사(dq4ch3walkcheck.py)는 사건마다 필요한 flag·물건을 SET 으로 써 넣고 순간이동으로 시작한다. 이 검사는 3장
출발 상태(dq4ch3walkcheck.head: 2장 끝 → 3장 넘김 → 첫머리, 캐시 ch3-start)에서 구간 표(dq4story3.SEGMENTS)를 차례로,
앞 구간의 끝 세이브스테이트에서 다음 구간을 시작한다. 사건 flag·사건 물건·자리는 써 넣지 않는다. 써 넣는 것은 FC 에서
무기점 일·장사·전투로 버는 금화와 납품 무기뿐이고(구간 선택 gold·give), 무엇을 어디서 왜 썼는지 결과의 writes 표에 남는다.

입력은 dq4storywalk.lua 의 토막이다: 걷기와 함께 창 번호(7E:0A00)·필드 루프(7E:007F)·메시지 번호를 보고 A·예·아니요를
주므로 프레임 수로 기다리지 않는다. 구간마다 시작에 난수(7E:075B~075D)를 시드 값으로 두고, 선택 rng 인 구간은 끝까지
그 값으로 묶는다(걸어 다니는 사람에게 말을 걸 때). 시각은 묶지 않는다(밤은 FC 처럼 필드를 걸어서, 아침은 잠·여관으로).
걸음 조우는 끈다(2장 필드 길 검사와 같음). 필드 전투는 선택 battle 의 구간만 붙인다.

  파트  구간 표를 PARTS 의 이름으로 나눈다. 파트 끝 상태는 롬 SHA-1·검사 코드·앞 구간 표·시드로 정한 지문으로
        원래 체크아웃 work/cache/states 에 두어(--repeat 2 로 같을 때만), 다음 파트를 다시 걸을 때 앞을 걷지 않는다.
        --from 파트 는 그 파트부터(앞은 캐시에서), --upto 파트 는 그 파트까지.
  시드  시드마다, --repeat 2 면 두 번씩 처음부터 따로 걸어(함께 돎) 구간 기록 SHA-1 이 같은지 본다. --part k/n 은
        시드를 n 몫으로 나눈 k 번째만(CI 하위 조각).

  MESENCE=… LIBDIR=… python sfc/dq4/tools/dq4story3check.py --rom work/ch3/dq4-ch1-full.sfc --out work/ch3story \
      --seeds 0,5,9 --repeat 2

롬은 dq4build.py --chapter3 의 출력이어야 한다. 형식은 sfc/dq4/docs/dq4-chapter3-format.md 「한 줄 걷기」.
"""
import argparse
import concurrent.futures
import hashlib
import inspect
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4ch1walkcheck as wc  # noqa: E402
import dq4ch3walkcheck as tw  # noqa: E402
import dq4story3 as story  # noqa: E402

LUA = HERE / 'lua' / 'dq4storywalk.lua'
WATCH_MORE = ';GOLD=7E2019:3;TIME=7E075E:2'


def problems_of(text, opt, flags):
    """walk.txt 와 구간 선택으로 판정한다."""
    seen = {k: int(v, 16) for k, v in re.findall(r'^(\w+)=([0-9A-F]+)$', text, re.M)}
    out = [line.split(' ', 2)[2] for line in text.splitlines() if re.match(r'f\d+ fail ', line)]
    end = re.search(r'end map (\w\w/\w\w) x=(\d+) y=(\d+)', text)
    if not end:
        return out + ['끝 기록 없음'], seen
    if 'map' in opt and end[1] != opt['map']:
        out.append(f'끝 맵 {end[1]}, 기대 {opt["map"]}')
    if 'cell' in opt and (int(end[2]), int(end[3])) != tuple(opt['cell']):
        out.append(f'끝 셀 ({end[2]},{end[3]}), 기대 {tuple(opt["cell"])}')
    if 'field' in opt and bool(seen.get('BE', 0x80) & 0x80) == opt['field']:
        out.append('필드가 아님' if opt['field'] else '필드에 있음')
    for k in opt.get('want', []):
        if not seen.get(k, 0) & flags[k][1]:
            out.append(f'flag {k} 꺼짐')
    for k in opt.get('off', []):
        if seen.get(k, 0) & flags[k][1]:
            out.append(f'flag {k} 켜짐')
    items = [b for k in ('ITEMS0', 'ITEMS1') for b in seen.get(k, 0).to_bytes(6, 'little')]
    for want in opt.get('items', []):
        if want not in items:
            out.append(f'물건 {want:02X} 없음')
    for want in opt.get('no_items', []):
        if want in items:
            out.append(f'물건 {want:02X} 있음')
    for k, v in opt.get('bytes', {}).items():
        if seen.get(k) is None or seen[k] != v:
            out.append(f'{k} = {seen.get(k)}, 기대 {v:X}')
    if 'gold_min' in opt and seen.get('GOLD', 0) < opt['gold_min']:
        out.append(f'금화 {seen.get("GOLD")}, 기대 {opt["gold_min"]} 이상')
    return out, seen


def data_of(rom):
    return Path(rom).read_bytes()


def segment(mesence, rom, state, dest, seg, seed, flags):
    """구간 하나를 state 에서 걷는다. 토막이 ending:<장면> 이면 끝 상자에서 버튼으로 리셋되는지(dq4ch1walkcheck.ending)."""
    name, toks, opt = seg
    if toks.startswith('ending:'):
        return {**wc.ending(mesence, rom, state, dest, seed, toks.split(':', 1)[1]), 'name': name}
    rng = wc.rng_for(seed)
    if 'rng_fixed' in opt:
        # 시드와 상관없이 정한 난수(떠돌이 상인을 만나는 값)를 구간 내내 묶는다
        rng = ';'.join(f'{a:04X}={v:02X}' for a, v in zip((0x075B, 0x075C, 0x075D), opt['rng_fixed']))
    start = ';'.join(v for v in (rng, story.writes_set(opt)) if v)
    poke = ';'.join(f'7E{v}' for v in rng.split(';')) if opt.get('rng') or 'rng_fixed' in opt else ''
    patch = '' if opt.get('encounters') else wc.NO_ENCOUNTERS
    if 'battle' in opt:
        patch += ';' + tw.battle_patch(data_of(rom), opt['battle'])
    after = ''
    if 'fight' in opt:
        # 이 구간의 첫 걸음 조우를 정한 무리(HP 1)로 붙이고, 전투가 끝나면 조우를 다시 끈다
        import dq4battlecheck as bc
        patch = ';'.join((bc.force_patch(opt['fight']), bc.weak_patch(data_of(rom), [m for m, _ in opt['fight']])))
        after = wc.NO_ENCOUNTERS
    env = {'STATE': str(state), 'WALK': str(LUA), 'WAYPOINTS': toks, 'LIMIT': str(wc.MSG_LIMIT), 'SAVE': 'end.mss',
           'MAXF': str(opt.get('maxf', 30000)), 'TOKMAX': str(opt.get('tokmax', 6000)), 'WATCH': wc.watch_flags(flags) + WATCH_MORE, 'ROMPATCH': patch,
           'SET': start, **({'POKE': poke} if poke else {}), **({'AFTERPATCH': after} if after else {})}
    t0 = time.monotonic()
    why = wc.run(mesence, rom, wc.WALK_STATE, dest, env, opt.get('maxf', 30000) // 40 + 180)
    log = dest / 'walk.txt'
    text = log.read_text(encoding='utf-8') if log.exists() else ''
    problems, seen = problems_of(text, opt, flags)
    if not (dest / 'end.mss').exists():
        problems.append('세이브스테이트 없음')
    if why and problems:
        problems.append(f'MesenCE 실행: {why}')
    frames = re.search(r'f(\d+) end map', text)
    found = re.search(r'^messages (.*)$', text, re.M)
    return {'name': name, 'status': 'failed' if problems else 'passed', 'problems': problems,
            'frames': int(frames[1]) if frames else None, 'seconds': round(time.monotonic() - t0, 1),
            'trace': wc.digest(log), 'gold': seen.get('GOLD'), 'time': seen.get('TIME'),
            'end': (re.search(r'end map (.*)$', text, re.M) or [None, None])[1],
            'messages': [v.split('@')[0] for v in found[1].split(',') if v] if found else []}


def code_key(mesence, data):
    """파트 끝 상태 지문의 뿌리: 3장 출발 상태 키, 이 검사와 Lua 코드, flag 표."""
    return wc.fingerprint(tw.head_key(mesence, data), Path(__file__), LUA, wc.WALK_STATE,
                          inspect.getsource(story.writes_set), repr(sorted(story.FLAGS.items())))


def part_keys(root, seed):
    """파트마다 (이름, 구간 번호들, 끝 상태 지문). 지문은 앞 파트 지문에 그 파트 구간 표를 더한다."""
    out, key = [], wc.fingerprint(root, seed)
    for name, idx in story.parts():
        key = wc.fingerprint(key, repr([story.SEGMENTS[i] for i in idx]))
        out.append((name, idx, key))
    return out


def walk_chain(mesence, rom, data, out, base, seed, chosen, cache, root):
    """시드 하나를 처음부터(또는 캐시된 앞 파트 끝에서) 걷는다. chosen 은 걸을 파트 이름들(차례대로)."""
    results, state = [], base
    keys = part_keys(root, seed)
    first = next(k for k, (name, *_) in enumerate(keys) if name == chosen[0])
    if first:
        hit = cache.get('ch3story', keys[first - 1][2], '.mss', out / '_from.mss') if cache else None
        if not hit:
            return [{'name': keys[first][0], 'status': 'failed', 'problems': ['앞 파트 끝 상태 캐시 없음(--from 없이 다시)']}]
        state = hit[0]
    for name, idx, key in keys[first:]:
        if name not in chosen:
            break
        part = []
        for i in idx:
            seg = story.SEGMENTS[i]
            r = segment(mesence, rom, state, out / seg[0], seg, seed, story.FLAGS)
            r['part'] = name
            part.append(r)
            if r['status'] != 'passed':
                return results + part
            # 곁가지(side)는 같은 상태에서 따로 보고 줄기는 앞 상태에서 이어 간다
            if not seg[2].get('side'):
                state = out / seg[0] / 'end.mss'
        results += part
    return results


def compare(first, second):
    bad = {}
    for a, b in zip(first, second):
        if a.get('trace') != b.get('trace') or a['status'] != b['status']:
            bad[a['name']] = f"두 번 걸은 기록이 다름: {a.get('trace')} ≠ {b.get('trace')}"
    if len(first) != len(second):
        bad['_'] = f'두 번 걸은 구간 수가 다름: {len(first)} ≠ {len(second)}'
    return bad


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', required=True, type=Path, help='dq4build.py --chapter3 의 롬')
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--jobs', type=int, default=6, help='함께 걸을 시드·반복 수')
    ap.add_argument('--base', type=Path, help='같은 롬으로 만든 3장 출발 상태. 주면 머리를 건너뜀')
    ap.add_argument('--from', dest='start', help='이 파트부터(앞 파트 끝 상태는 캐시)')
    ap.add_argument('--upto', help='이 파트까지')
    ap.add_argument('--repeat', type=int, default=1, choices=(1, 2), help='2 면 두 번 걸어 기록을 견줌')
    ap.add_argument('--list', action='store_true', help='파트·구간·써 넣기 표만 찍음')
    wc.add_seed_args(ap)
    import dq4shards
    dq4shards.add_part_arg(ap)
    args = ap.parse_args()
    names = [n for n, _ in story.parts()]
    for v in (args.start, args.upto):
        if v and v not in names:
            raise SystemExit(f'없는 파트 {v}: {", ".join(names)}')
    chosen = names[names.index(args.start) if args.start else 0:names.index(args.upto) + 1 if args.upto else None]
    if args.list:
        for n, idx in story.parts():
            print(n, ' '.join(story.SEGMENTS[i][0] for i in idx))
        print(json.dumps(story.writes(), ensure_ascii=False, indent=1))
        return 0
    # CI 하위 조각은 시드로 나눈다(한 시드의 두 번 걷기는 같은 조각에서 견줌)
    seeds = dq4shards.part_of(wc.seeds_of(args), args.part, key=str)
    mesence = Path(os.environ['MESENCE'])
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f'{out} is not empty')
    out.mkdir(parents=True)
    rom = out / 'c.sfc'
    shutil.copyfile(args.rom.resolve(), rom)
    data = rom.read_bytes()
    cache = None if args.no_state_cache else wc.StateCache(data)
    began = time.monotonic()
    if args.base:
        base, head = args.base.resolve(), []
    else:
        base, head = tw.head(mesence, rom, data, out, cache, repeat=2 if cache else 1)
    root = code_key(mesence, data)
    runs = {}
    if base is not None:
        with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
            jobs = {(s, n): pool.submit(walk_chain, mesence, rom, data,
                                        wc.seed_dir(out, s, seeds) / (f'run-{n}' if args.repeat > 1 else ''), base, s,
                                        chosen, cache, root)
                    for s in seeds for n in range(1, args.repeat + 1)}
            runs = {k: j.result() for k, j in jobs.items()}
    head_ok = base is not None and all(r['status'] == 'passed' for r in head)
    want = sum(len(idx) for n, idx in story.parts() if n in chosen)
    per_seed = []
    for s in seeds:
        rs = runs.get((s, 1), [])
        problems = []
        if args.repeat > 1:
            bad = compare(rs, runs.get((s, 2), []))
            for r in rs:
                if r['name'] in bad:
                    r['problems'] = r['problems'] + [bad[r['name']]]
                    r['status'] = 'failed'
            if '_' in bad:
                problems.append(bad['_'])
        ok = head_ok and len(rs) == want and all(r['status'] == 'passed' for r in rs) and not problems
        per_seed.append({'seed': s, 'rng': wc.rng_for(s), 'status': 'passed' if ok else 'failed', 'problems': problems,
                         'frames': sum(r['frames'] for r in rs if isinstance(r.get('frames'), int)), 'segments': rs})
    ok = head_ok and all(p['status'] == 'passed' for p in per_seed)
    # 두 번 걸어 같고 모두 통과했을 때만 파트 끝 상태를 캐시에 넣는다(시드마다)
    if ok and cache and args.repeat > 1:
        for s in seeds:
            seed_out = wc.seed_dir(out, s, seeds) / 'run-1'
            for name, idx, key in part_keys(root, s):
                last = [i for i in idx if not story.SEGMENTS[i][2].get('side')
                        and not story.SEGMENTS[i][1].startswith('ending:')]
                end = seed_out / story.SEGMENTS[last[-1]][0] / 'end.mss'
                if name in chosen and end.exists():
                    cache.put('ch3story', key, '.mss', end,
                              {'segments': [r for r in runs[s, 1] if r.get('part') == name]})
    report = {'status': 'passed' if ok else 'failed', 'seconds': round(time.monotonic() - began), 'repeat': args.repeat,
              'parts': chosen, 'head': head, 'writes': story.writes(), 'seeds': per_seed}
    (out / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n')
    for p in per_seed:
        for r in p['segments']:
            print(f"{p['seed']} {r.get('part')} {r['name']} {r['status']} f={r.get('frames')} {r.get('end')} "
                  f"gold={r.get('gold')} {'; '.join(r['problems'])}")
    print(json.dumps({'status': report['status'], 'seconds': report['seconds'], 'parts': len(chosen),
                      'failed': [f"{p['seed']}:{r['name']}" for p in per_seed for r in p['segments']
                                 if r['status'] != 'passed'] + [f"{p['seed']}:{q}" for p in per_seed for q in p['problems']]},
                     ensure_ascii=False))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
