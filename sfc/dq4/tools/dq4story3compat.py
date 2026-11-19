"""3장 한 줄 걷기(dq4story3)를 MesenCE 밖의 libretro 코어(bsnes·snes9x)에서 걷는 호환성 검사.

코어마다 dq4compatcheck.Walker 로 서장 → 2장 출발 상태 → 3장 출발 상태(코어별 캐시)를 만든 뒤, 구간 표를 차례로 한
코어에서 끊지 않고 걷는다. 토막은 dq4storytokens 가 Lua 와 같은 판정으로 돌린다. 실행 주소 훅이 필요한 구간(걸음
전투를 붙이는 다리 앞, 떠돌이 상인)과 곁가지는 건너뛰고 결과에 skipped 로 남긴다. 장 끝은 Walker.ending(어두운 끝
화면 뒤 타이틀이 다시 밝아지고 소리가 남)으로 본다.

  python sfc/dq4/tools/dq4cores.py && python sfc/dq4/tools/dq4story3compat.py --rom work/ch3/dq4-ch1-full.sfc \
      --out work/ch3storycompat [--cores bsnes,snes9x] [--seed 0]
"""
import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4ch1walkcheck as wc  # noqa: E402
import dq4compatcheck as cc  # noqa: E402
import dq4cores  # noqa: E402
import dq4story3 as story  # noqa: E402
import dq4story3check as check  # noqa: E402
import dq4storytokens as tokens  # noqa: E402

WATCH_EXTRA = {'GOLD': (0x7E2019, 3), 'TIME': (0x7E075E, 2)}


# 이 검사가 건너뛰는 구간 전부와 까닭. 표 밖의 구간이 건너뛰어지면(새 곁가지·훅 토막) 실패한다(분모가 몰래 줄지 않게).
# 곁가지는 MesenCE 판도 줄기를 앞 상태에서 이어 가므로 대 줄 것이 없다. 줄기 구간은 뒤 구간의 출발을 어떻게 맞추는지 적는다
SKIPPED = {
    'early_quit': '곁가지',
    'merchant': '떠돌이 상인 조우는 실행 주소 훅. 산 약초는 뒤 구간이 쓰지 않고, 금화는 엔돌 가게 구간이 다시 둔 뒤에만 '
                '확인하므로 대 줄 것 없음(test_dq4story3compat 가 지킴)',
    'drop_armor': '곁가지',
    'drop_sword': '곁가지',
    'bm_bridge_fight': '걸음 전투는 실행 주소 훅. 전투를 뺀 걸음(STAND_IN)을 걸어 끝 칸을 맞춘 뒤 이어 감',
    'tunnel_song': '곁가지',
}
# 건너뛴 줄기 구간 대신 걷는 토막: 훅 토막만 뺀 걸음. 구간의 끝 칸·flag 판정은 그대로 본다
STAND_IN = {'bm_bridge_fight': 'right:16;right:30;wait:30'}


def skip_reason(seg):
    """이 구간을 코어에서 건너뛰는 까닭(없으면 None)."""
    name, toks, opt = seg
    if opt.get('side'):
        return '곁가지'
    if 'fight' in opt or opt.get('encounters'):
        return '걸음 전투·조우를 실행 주소 훅으로 다룸'
    if any(t.split(':')[0] in tokens.HOOKED for t in toks.split(';')):
        return '메시지·전투 실행 주소 훅이 필요한 토막'
    return None


def text_of(w, runner, problems):
    """dq4story3check.problems_of 가 읽는 walk.txt 꼴의 글."""
    x, y = runner.hero()
    lines = [f'f{runner.n:05d} fail {p}' for p in problems]
    lines.append(f'f{runner.n:05d} end map {w.rd(0x7E00BC):02X}/{w.rd(0x7E00BD):02X} x={x} y={y}')
    for k, (a, _) in story.FLAGS.items():
        lines.append(f'{k}={w.rd(a):02X}')
    for k, (a, n) in WATCH_EXTRA.items():
        lines.append(f'{k}={sum(w.rd(a + i) << 8 * i for i in range(n)):0{2 * n}X}')
    lines.append(f'BE={w.rd(0x7E00BE):02X}')
    for half in range(2):
        lines.append(f'ITEMS{half}=' + ''.join(f'{w.rd(wc.ITEMS + 6 * half + i):02X}' for i in reversed(range(6))))
    return '\n'.join(lines) + '\n'


def walk_story(w, seed):
    """3장 출발 상태가 실린 코어에서 구간 표를 걷는다."""
    results = []
    for seg in story.SEGMENTS:
        name, toks, opt = seg
        why = skip_reason(seg)
        if why and name not in STAND_IN:
            results.append({'name': name, 'status': 'skipped', 'why': why})
            continue
        if why:
            toks, opt = STAND_IN[name], {k: v for k, v in opt.items() if k != 'fight'}
        if toks.startswith('ending:'):
            r = {**w.ending(), 'name': name}
            results.append(r)
            print(json.dumps(r, ensure_ascii=False), flush=True)
            break
        rng, held = check.segment_rng(opt, seed)
        cc.apply_sets(w.c, ';'.join(v for v in (rng, story.writes_set(opt)) if v))
        w.pokes = [(int(a, 16), int(v, 16)) for a, v in (p.split('=') for p in check.segment_poke(opt, seed).split(';') if p)]
        runner = tokens.Runner(w, opt.get('tokmax', tokens.TOKMAX))
        problems, t0 = [], time.monotonic()
        try:
            runner.run(toks)
            for _ in range(30):
                w.step(set())
        except tokens.Failed as e:
            problems.append(str(e))
        w.pokes = []
        found, _ = check.problems_of(text_of(w, runner, problems), opt, story.FLAGS)
        r = {'name': name, 'status': 'failed' if found else 'passed', 'problems': found, 'frames': runner.n,
             **({'stand_in': toks} if why else {}),
             'seconds': round(time.monotonic() - t0, 1), 'log': runner.log[-12:] if found else []}
        w.c.shot(w.out / f'{name}.png')
        (w.out / f'{name}.txt').write_text('\n'.join(runner.log) + '\n', encoding='utf-8')
        results.append(r)
        print(json.dumps({k: v for k, v in r.items() if k != 'log'}, ensure_ascii=False), flush=True)
        if found:
            break
    return results


def one_core(name, rom, out, seed, cache):
    core_path = dq4cores.core_path(name)
    if not core_path.exists():
        raise SystemExit(f'{core_path} 가 없음: sfc/dq4/tools/dq4cores.py 로 빌드하거나 {cc.CORES[name]} 로 코어 파일을 줌')
    dest = out / name
    dest.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    w = cc.Walker(core_path, rom, dest, seed, chapter=3)
    w.flags = story.FLAGS
    # 3장 출발 상태는 3장 호환성 걷기(dq4compatcheck walk --chapter3)와 같은 캐시를 쓴다
    base, pro, head, _, _, stop = w.bases([seed], core_path, cache, f'compat-{name}', t0)
    if stop:
        return {'core': name, 'status': 'failed', 'problems': ['3장 출발 상태를 만들지 못함'], 'head': head}
    data = Path(base).read_bytes()
    w.c.run(set())
    w.c.load((data[8:], int.from_bytes(data[:8], 'little')))
    w.seed = seed
    results = walk_story(w, seed)
    return {'core': name, 'seed': seed, 'seconds': round(time.time() - t0), **tally(results), 'segments': results}


def tally(results):
    """분모는 구간 표 전체. 건너뛴 구간이 SKIPPED 와 다르거나 걸은 구간이 모자라면 실패."""
    walked = [r for r in results if r['status'] != 'skipped']
    skipped = {r['name'] for r in results if r['status'] == 'skipped'}
    problems = []
    if skipped != set(SKIPPED) - set(STAND_IN):
        problems.append(f'건너뛴 구간이 표와 다름: {sorted(skipped ^ (set(SKIPPED) - set(STAND_IN)))}')
    if len(results) != len(story.SEGMENTS):
        problems.append(f'걸은·건너뛴 구간 {len(results)}, 구간 표 {len(story.SEGMENTS)}')
    ok = not problems and all(r['status'] == 'passed' for r in walked)
    return {'status': 'passed' if ok else 'failed', 'walked': len(walked), 'skipped': len(skipped),
            'expected': len(story.SEGMENTS), 'problems': problems}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', required=True, type=Path)
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--cores', default='bsnes,snes9x')
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--no-state-cache', action='store_true')
    args = ap.parse_args()
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f'{out} is not empty')
    out.mkdir(parents=True, exist_ok=True)
    rom = args.rom.resolve()
    cache = None if args.no_state_cache else wc.StateCache(rom.read_bytes())
    cores = [c for c in args.cores.split(',') if c]
    # 코어는 ctypes 로 이 프로세스에 실리므로 하나씩 돈다
    reports = [one_core(c, rom, out, args.seed, cache) for c in cores]
    ok = all(r['status'] == 'passed' for r in reports)
    (out / 'results.json').write_text(json.dumps({'status': 'passed' if ok else 'failed', 'cores': reports},
                                                 ensure_ascii=False, indent=1) + '\n')
    lines = {r['core']: f"{r['status']} {r.get('walked')}/{r.get('expected')}(건너뜀 {r.get('skipped')}) "
                        f"{r.get('seconds')}초" for r in reports}
    print(json.dumps({'status': 'passed' if ok else 'failed', 'cores': lines}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
