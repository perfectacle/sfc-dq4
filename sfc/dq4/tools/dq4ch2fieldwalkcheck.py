"""2장 사건 사이 필드 길을 순간이동 없이 걷는 검사(MesenCE 헤드리스, 배포 관문 가드 dq4-ch2-field-walk).

2장 걷기 검사(dq4ch2walkcheck.py)는 사건 사이를 대부분 순간이동으로 건넌다. 이 검사는 FC 2장 차례대로 사건 사이의
길마다 묶음 하나를 둔다. 묶음은 2장 출발 상태에서 그 길 앞 사건까지의 flag 를 두고 출발지 도착 칸에 내린 뒤,

  나가기  출발지의 나가는 길(dq4groupbuild.LINKS 의 out, 텐페를 북쪽으로 지날 때는 마을을 걸어 위 가장자리)로
          필드에 나와 그 FC 그룹의 나오는 칸(dq4groupbuild.doors, 텐페 위 가장자리는 leave_rows)인지 본다
  필드    FC 필드 블록 속성 bit7(막힘)과 다른 입구 블록을 피해 꺾임이 적은 최단 길을 걸어 다음 곳의 입구 블록을
          밟고, 맵이 바뀌어 그 FC 그룹의 도착 맵·칸(LINKS arrival)에 섰는지 본다

를 다음 곳마다 되풀이한다. 산트하임 쪽(성·사란·텐페)과 프레놀·바자·탑·이쪽 사당 쪽은 텐페 마을 블록으로만 이어져
텐페를 지나간다. 엔돌 쪽 사당 → 엔돌과 사란 → 성문은 2장 걷기 검사의 두 묶음(shrine_side·gate_end_side)을 그대로
함께 돈다.

난수·시각·조우는 2장 걷기 검사와 같이 묶는다(조우 판정을 덮고 낮으로). --repeat 2 는 묶음마다 두 번 걸어 기록이 같은지
본다. 2장 출발 상태는 2장 걷기 검사의 머리(캐시 ch2-opening)를 쓴다.

  MESENCE=… LIBDIR=… python sfc/dq4/tools/dq4ch2fieldwalkcheck.py --rom work/ch2/dq4-ch1-full.sfc --out work/ch2field
"""
import argparse
import concurrent.futures
import heapq
import json
import os
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools'), str(HERE.parents[2] / 'fc' / 'dq4' / 'tools')]

import dq4ch2walkcheck as cw  # noqa: E402
import dq4fieldport  # noqa: E402
import dq4groupbuild as gb  # noqa: E402

wc = cw.wc
STEPS = ((1, 0), (-1, 0), (0, 1), (0, -1))

# FC 그룹: 산트하임 성·텐페·프레놀·사막의 바자·사란·엔돌·이쪽 사당·엔돌 쪽 사당·서쪽 탑·남쪽 동굴
CASTLE, TEMPE, FRENOL, BAZAAR, SARAN, ENDOR, SHRINE, SHRINE_FAR, TOWER, CAVE = (
    0x01, 0x0E, 0x0F, 0x0C, 0x13, 0x04, 0x1E, 0x1F, 0x2E, 0x39)

# (묶음 이름, 이 길 앞의 2장 걷기 검사 구간, 출발 FC 그룹, 들를 곳). 'north' 는 텐페를 위 가장자리로 나가 북쪽(프레놀
# 쪽)에 서는 것(dq4groupbuild.LINKS 의 leave_rows), 'door' 는 엔돌 쪽 사당의 여행의 문으로 이쪽 사당에 건너가는 것이다
LEGS = [
    ('road_saran', 'join', CASTLE, [SARAN, TEMPE]),
    ('road_frenol', 'chief_won', TEMPE, ['north', FRENOL]),
    ('road_cave', 'inn_open', FRENOL, [CAVE]),
    ('road_cave_back', 'chest', CAVE, [FRENOL]),
    ('road_bazaar', 'grave', FRENOL, [BAZAAR]),
    ('road_home', 'bazaar', BAZAAR, [TEMPE, CASTLE]),
    ('road_shrine', 'throne', CASTLE, [TEMPE, 'north', SHRINE]),
    ('road_tower', 'closed', SHRINE, [TOWER]),
    ('road_honey_home', 'honey', TOWER, [TEMPE, CASTLE]),
    ('road_door', 'cure', CASTLE, [TEMPE, 'north', SHRINE]),
    ('road_return', 'endor_messenger', ENDOR, [SHRINE_FAR, 'door', TEMPE, CASTLE]),
]
# 2장 걷기 검사에서 이미 필드를 걷는 묶음
REUSED = ('shrine_side', 'gate_end_side')


def part_of(fc):
    """(DQ5 그룹, LINKS 항목) of an FC group."""
    return next((g, p) for g, parts in gb.LINKS.items() for p in parts if p['fc'] == fc)


def arrival(prg, fc):
    """(DQ5 맵 'GG/KK', 도착 셀) of an FC group's field entrance."""
    group, part = part_of(fc)
    number = gb.placement(prg)[fc, part.get('map', 0)][1]
    return f'{group:02X}/{number:02X}', gb.cell(*part['arrival'])


def entrance_blocks(prg):
    """{FC 필드 0 블록: FC 그룹} of every field-0 entrance (both halves of a two-block one)."""
    import dq4field
    _, props = dq4fieldport.fc_field(prg)
    out = {}
    for g, fx, fy, *rest in dq4field.entrances(prg):
        if (rest[-1] or 0) == 0:
            for b in dq4fieldport.entrance_blocks(props, [(fx, fy)]):
                out[b] = g
    return out


def route(walkable, start, goals, avoid=frozenset()):
    """블록 길: start 에서 goals 중 하나까지 걸음(avoid 블록은 10걸음으로 셈)이 가장 적고, 그 가운데 꺾임이 가장 적은
    블록 목록. 없으면 None."""
    best = {}
    heap = [(0, 0, start, None, (start,))]
    while heap:
        steps, turns, at, d, path = heapq.heappop(heap)
        if at in goals:
            return list(path)
        if best.get((at, d), (1 << 30, 0)) <= (steps, turns):
            continue
        best[at, d] = (steps, turns)
        for step in STEPS:
            n = (at[0] + step[0], at[1] + step[1])
            if n in goals or walkable(n):
                heapq.heappush(heap, (steps + (10 if n in avoid else 1), turns + (d is not None and d != step), n, step,
                                      path + (n,)))
    return None


def corners(path):
    """블록 길의 꺾이는 곳과 끝을 걷기 웨이포인트(블록의 서는 셀 (2x, 2y+1))로."""
    keep = [p for i, p in enumerate(path[1:], 1)
            if i == len(path) - 1 or (path[i + 1][0] - p[0], path[i + 1][1] - p[1]) != (p[0] - path[i - 1][0], p[1] - path[i - 1][1])]
    return ';'.join('%d,%d' % dq4fieldport.stand(*p) for p in keep)


def field_road(prg, leave, goals):
    """필드 셀 leave 에서 블록 goals(집합) 중 하나까지 걷는 웨이포인트."""
    _, props = dq4fieldport.fc_field(prg)
    ents = entrance_blocks(prg)
    path = route(lambda b: not props(*b) & 0x80 and b not in ents, (leave[0] // 2, leave[1] // 2), goals)
    if path is None:
        raise ValueError(f'필드 {leave}에서 {sorted(goals)}에 닿는 길이 없음')
    return corners(path)


def entrance_of(prg, fc):
    """FC 그룹 fc 의 필드 입구 블록."""
    return {b for b, g in entrance_blocks(prg).items() if g == fc}


def town_walkable(prg, fc, number=0):
    import dq4block
    from dq4environmentmap import block_prop
    source = dq4block.Map(prg, fc, number)
    return source, (lambda b: 0 <= b[0] < source.w and 0 <= b[1] < source.h
                    and not block_prop(source, source.cell(*b) & 31) & 0x80)


def door_back(prg):
    """엔돌 쪽 사당 도착 블록에서 여행의 문 아래 블록까지 걷고 문을 밟는 웨이포인트, 이쪽 사당의 도착(문 짝 칸)."""
    _, part = part_of(SHRINE_FAR)
    (door,) = gb.exit_order(prg, SHRINE_FAR, 0)
    _, walkable = town_walkable(prg, SHRINE_FAR)
    below = (door[0], door[1] + 1)
    path = route(walkable, part['arrival'], {below})
    (far,) = gb.exit_order(prg, SHRINE, 0)
    return corners(path) + ';%d,%d' % gb.cell(*door), (arrival(prg, SHRINE)[0], gb.cell(*far))


def shrine_out(prg):
    """이쪽 사당의 여행의 문 칸에서 맵 아래 줄까지 걷고 아래로 나가는 웨이포인트."""
    source, walkable = town_walkable(prg, SHRINE)
    (door,) = gb.exit_order(prg, SHRINE, 0)
    path = route(walkable, door, {(x, source.h - 1) for x in range(source.w) if walkable((x, source.h - 1))})
    return corners(path) + ';down:64'


def leg_segments(prg, name, start, stops):
    """한 길의 구간: 출발지 도착 칸으로 순간이동, 그 뒤 들를 곳마다 나가기·필드 걷기."""
    doors = gb.doors(prg)
    day = {'poke': wc.DAY}
    where, cell = arrival(prg, start)
    segs = [(f'{name}_side', 'warp', '%s,%d,%d' % (where, *warp_cell(prg, start)), {'map': where})]
    here, leave, by_door = start, None, False
    for k, stop in enumerate(stops):
        tag = f'{name}_{k}'
        if stop == 'door':
            arg, (where, cell) = door_back(prg)
            segs.append((f'{tag}_door', 'walk', arg, {'map': where, 'cell': cell, 'changes': 1, 'after': 60, **day}))
            here, by_door = SHRINE, True
            continue
        if stop == 'north':
            arg, leave = north_exit(prg)
            segs.append((f'{tag}_out', 'walk', arg, {'field': True, 'cell': leave, **day}))
            continue
        if leave is None:
            leave = doors[here][1]
            arg = shrine_out(prg) if by_door else out_walk(prg, here)
            segs.append((f'{tag}_out', 'walk', arg, {'field': True, 'cell': leave, **day}))
        road = field_road(prg, leave, entrance_of(prg, stop))
        where, cell = arrival(prg, stop)
        segs.append((f'{tag}_in', 'walk', road, {'map': where, 'cell': cell, 'changes': 1, 'after': 60, **day,
                                                 'maxf': frames_for(leave, road)}))
        here, leave, by_door = stop, None, False
    return segs


def avoid_people(prg, fc, number=0):
    """FC 낮 목록 인물 칸과 그 둘레(돌아다니는 인물이 길을 막지 않게 길 찾기가 피함)."""
    import dq4talk
    out = set()
    for r in dq4talk.npc_list(prg, fc, number, False):
        x, y = dq4talk.pos(r, False)
        out |= {(x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
    return out


def north_exit(prg):
    """텐페 도착 블록에서 맵 위 줄까지 걷고 위로 나가는 웨이포인트, 그리고 나오는 셀(LINKS leave_rows)."""
    _, part = part_of(TEMPE)
    source, walkable = town_walkable(prg, TEMPE)
    path = route(walkable, part['arrival'], {(x, 0) for x in range(source.w) if walkable((x, 0))},
                 avoid_people(prg, TEMPE))
    (rows,) = part['leave_rows']
    return corners(path) + ';up:16', dq4fieldport.stand(*rows['block'])


def warp_cell(prg, fc):
    """출발 순간이동 칸: 도착 칸이 맵 가장자리면 순간이동이 곧바로 필드로 나가므로(성 앞마당) 나가는 쪽 반대로 한 블록
    들어간 칸."""
    _, part = part_of(fc)
    x, y = gb.cell(*part['arrival'])
    d = part['out'].split(':')[0]
    dx, dy = {'down': (0, -2), 'up': (0, 2), 'right': (-2, 0), 'left': (2, 0)}[d]
    source, walkable = town_walkable(prg, fc, part.get('map', 0))
    edge = {'down': y >= 2 * source.h - 2, 'up': y <= 1, 'right': x >= 2 * source.w - 2, 'left': x <= 1}[d]
    if edge and walkable(((x + dx) // 2, (y + dy) // 2)):
        return x + dx, y + dy
    return x, y


def out_walk(prg, fc):
    """출발지에서 필드로 나가는 웨이포인트: 도착 칸까지 걸은 뒤 LINKS out. 누르기는 맵이 바뀌어도 이어지므로
    가장자리까지 셀 수만큼만 누른다."""
    _, part = part_of(fc)
    x, y = gb.cell(*part['arrival'])
    toks = part['out'].split(',')
    if len(toks) > 1:
        return ';'.join(toks)
    d = toks[0].split(':')[0]
    source, _ = town_walkable(prg, fc, part.get('map', 0))
    n = {'down': 2 * source.h - y, 'up': y + 1, 'right': 2 * source.w - x, 'left': x + 1}[d]
    return f'{x},{y};{d}:{8 * n + 8}'


def frames_for(leave, road):
    return 600 + 400 * len(road.split(';')) + 8 * route_cells(leave, road)


def route_cells(leave, road):
    """웨이포인트를 잇는 셀 수(프레임 한도를 셈)."""
    total, (x, y) = 0, leave
    for tok in road.split(';'):
        if ',' in tok:
            nx, ny = map(int, tok.split(','))
            total += abs(nx - x) + abs(ny - y)
            x, y = nx, ny
    return total


def segments(prg):
    """2장 걷기 검사 구간 표에 길 구간을 그 앞 사건 구간 뒤에 끼운 표. 길 구간은 flag 를 바꾸지 않는다."""
    out = list(cw.SEGMENTS)
    for name, after, start, stops in LEGS:
        at = [s[0] for s in out].index(after) + 1
        # 끼운 곳 바로 뒤가 같은 묶음의 이어 걷기면 그 묶음 앞에 끼워 묶음을 가르지 않는다
        while at < len(out) and out[at][1] != 'warp':
            at += 1
        out[at:at] = leg_segments(prg, name, start, stops)
    return out


def chosen_units(table, only=None):
    """길 묶음과 다시 쓰는 두 묶음(only 가 있으면 그 이름으로 시작하는 묶음만)."""
    names = [s[0] for s in table]
    wanted = {f'{n}_side' for n, *_ in LEGS} | set(REUSED)
    if only:
        wanted &= set(only)
    return [u for u in cw.units(table) if names[u[0]] in wanted]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', required=True, type=Path, help='dq4build.py --chapter2 의 롬')
    ap.add_argument('--dq4', default=wc.ROOT / 'rom' / 'dq4.nes', type=Path, help='FC 롬(길과 입구를 셈)')
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--jobs', type=int, default=6, help='함께 띄울 MesenCE 수')
    ap.add_argument('--base', type=Path, help='같은 롬으로 만든 2장 출발 상태. 주면 머리를 건너뜀')
    ap.add_argument('--only', help='이 묶음만(첫 구간 이름, 쉼표로 여럿)')
    ap.add_argument('--repeat', type=int, default=1, choices=(1, 2), help='2 면 묶음마다 두 번 걸어 기록을 견줌')
    ap.add_argument('--list', action='store_true', help='구간 표만 찍고 끝냄')
    wc.add_seed_args(ap)
    args = ap.parse_args()
    from kr_patch.fc import ines
    prg = ines.prg(args.dq4.read_bytes())
    table = segments(prg)
    groups = chosen_units(table, args.only.split(',') if args.only else None)
    if args.list:
        for u in groups:
            for i in u:
                print(json.dumps(table[i], ensure_ascii=False, default=list))
        return 0
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
    names = [s[0] for s in table]
    if args.base:
        base, head_results = args.base.resolve(), []
    else:
        base, head_results = cw.head(mesence, rom, data, out, cache)
        for r in head_results:
            print(json.dumps(r, ensure_ascii=False), flush=True)
    runs, unit_seconds, repeat_problems = {s: [] for s in seeds}, {}, {}
    if base is not None:
        def one(seed, unit, n):
            t0 = time.monotonic()
            dest = wc.seed_dir(out, seed, seeds) / (f'run-{n}' if args.repeat > 1 else '')
            return cw.walk_unit(mesence, rom, data, dest, unit, base, seed, table), round(time.monotonic() - t0)
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
                    bad = cw.compare_runs(rs, jobs[s, tuple(u), 2].result()[0])
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
              'repeat': args.repeat, 'head': head_results, 'unit_seconds': unit_seconds,
              'repeat_problems': repeat_problems, 'seeds': per_seed}
    (out / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n')
    print(json.dumps({'status': report['status'], 'seconds': report['seconds'], 'units': len(groups),
                      'unit_seconds': unit_seconds,
                      'failed': [f"{s['seed']}:{r['name']}" for s in per_seed for r in s['segments']
                                 if r['status'] != 'passed']}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
