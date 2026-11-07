"""2장 출발 상태(산트하임 왕좌의 방 3D/01)에서 인물이 서 있을 자리에 서 있고, 걷는 인물이 DQ5 마을 사람만큼 느리게
걷는지 보는 검사(MesenCE 헤드리스).

FC 가 세워 두는 인물(블록이 걷지 않음, dq4npcblock.walk_interval = 0)은 레코드의 명령 간격이 1 이어도 서 있다. 옮긴
인물이 그 간격을 그대로 DQ5 이동 간격으로 받으면 몇 프레임마다 한 칸씩 쉬지 않고 돌아다녔다. 그래서

  서는 인물  FC 왕좌의 방(01/01) 낮 목록에서 걷지 않는 인물마다 DQ5 칸(dq4npcport.cell)에 그 인물이 있고, FRAMES
             동안 한 번도 칸이 바뀌지 않는다.
  걷는 인물  나머지 보이는 인물(슬롯 08~)의 이동 간격이 dq4npcport.WALK_FASTEST~WALK_SLOWEST 이고, 칸이 바뀐 수가
             MAX_MOVES 이하다(DQ5 마을 19/00(오라클베리)·18/00 의 간격 15 마을 사람은 1800프레임에 칸 7~27번).

시드마다(--seeds, 난수 7E:075B~075D 와 낮 시각을 첫 프레임에 둠) 두 번 돌려 기록이 같아야 한다(운으로 통과하지 않음).

  MESENCE=… LIBDIR=… python sfc/dq4/tools/dq4npcwalkcheck.py --rom work/ch2/dq4-ch1-full.sfc --out work/npcwalk \
      --seeds 0,5,9
"""
import argparse
import concurrent.futures
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools'), str(HERE.parents[2] / 'fc' / 'dq4' / 'tools')]

import dq4ch1walkcheck as wc  # noqa: E402
import dq4ch2walkcheck as ch2walk  # noqa: E402
import dq4mesen  # noqa: E402
import dq4npcport as port  # noqa: E402
from kr_patch.fc import ines  # noqa: E402

LUA = HERE / 'lua' / 'dq4npcwalk.lua'
MAP = '3D/01'
FC_MAP = (0x01, 0x01)
FRAMES = 1800
FIRST_PERSON = 0x08
# 걷는 인물 칸 바뀜 수의 상한(1800프레임). 고치기 전 간격 1 병사는 153번이었고, 간격 8 로 옮긴 인물은 시드 0·5·9 에서
# 19~38번이다. 걸음 빠르기는 간격 범위가 지키고, 이 상한은 간격이 맞아도 쉬지 않고 걷는 것을 잡는다
MAX_MOVES = 60


def fc_standers(prg):
    """FC 왕좌의 방 낮 목록에서 서 있는 인물의 DQ5 칸."""
    return [port.cell(p["x"], p["y"]) for p in port.fc_people(prg, *FC_MAP, False) if not p["interval"]]


def parse(text):
    """dq4npcwalk.lua 기록: (맵, {슬롯: (그림, x, y, 3300)}, {슬롯: [프레임…]}, 끝까지 적혔는지)."""
    mp, slots, moves, done = None, {}, {}, False
    for line in text.splitlines():
        p = line.split()
        if p[0] == 'map':
            mp = p[1]
        elif p[0] == 'slot':
            slots[int(p[1], 16)] = (int(p[3], 16), int(p[5], 16), int(p[7], 16), int(p[9], 16))
        elif p[0] == 'move':
            moves.setdefault(int(p[2], 16), []).append(int(p[1]))
        elif p[0] == 'end':
            done = True
    return mp, slots, moves, done


def judge(text, standers):
    mp, slots, moves, done = parse(text)
    problems = []
    if not done:
        problems.append('기록이 끝까지 적히지 않음')
    if mp != MAP:
        problems.append(f'맵이 {mp}({MAP} 이어야 함)')
    people = {s: v for s, v in slots.items() if s >= FIRST_PERSON and v[0] not in (0x00, 0xFF) and v[1] < 0x80}
    at = {(v[1], v[2]): s for s, v in people.items()}
    standing = set()
    for xy in standers:
        s = at.get(xy)
        if s is None:
            problems.append(f'FC 가 세워 두는 인물이 칸 {xy} 에 없음')
            continue
        standing.add(s)
        # 간격은 보지 않는다: 사건 스크립트를 빌린 인물(왕 병의 왕좌의 방 병사)은 스크립트가 돌게 간격 1 로 선다
        if moves.get(s):
            problems.append(f'슬롯 {s:02X} 칸 {xy}: 서 있을 인물이 {len(moves[s])}번 움직임(처음 {moves[s][0]}프레임)')
    walkers = {}
    for s, (gfx, x, y, interval) in sorted(people.items()):
        if s in standing:
            continue
        n = len(moves.get(s, []))
        if interval >> 4 or n:
            walkers[f'{s:02X}'] = {'gfx': f'{gfx:02X}', 'interval': interval >> 4, 'moves': n}
        if interval >> 4 and not port.WALK_FASTEST <= interval >> 4 <= port.WALK_SLOWEST:
            problems.append(f'슬롯 {s:02X}: 이동 간격 {interval >> 4} 이 {port.WALK_FASTEST}~{port.WALK_SLOWEST} 밖')
        if n > MAX_MOVES:
            problems.append(f'슬롯 {s:02X}: {FRAMES}프레임에 칸이 {n}번 바뀜(상한 {MAX_MOVES})')
        if not interval >> 4 and n:
            problems.append(f'슬롯 {s:02X}: 이동 간격 0 인데 {n}번 움직임')
    return {'standing': [f'{s:02X}' for s in sorted(standing)], 'walkers': walkers, 'problems': problems}


def run_once(mesence, rom, state, dest, seed):
    dest.mkdir(parents=True, exist_ok=True)
    log = dest / 'moves.txt'
    env = {**os.environ, 'STATE': str(state), 'OUT': str(log), 'FRAMES': str(FRAMES),
           'SET': f'{wc.rng_for(seed)};{wc.DAY_SET}'}
    dq4mesen.run(mesence, rom, LUA, folder=dest, tag='npcwalk', env=env, timeout=300,
                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return log.read_text() if log.is_file() else ''


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', required=True, type=Path, help='dq4build.py --chapter2 의 롬')
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--dq4', type=Path, default=HERE.parents[2] / 'rom' / 'dq4.nes')
    ap.add_argument('--base', type=Path, help='같은 롬으로 만든 2장 출발 상태. 없으면 dq4ch2walkcheck.head(캐시)')
    ap.add_argument('--jobs', type=int, default=4)
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
    standers = fc_standers(ines.prg(args.dq4.read_bytes()))
    if args.base:
        state = args.base.resolve()
    else:
        cache = None if args.no_state_cache else wc.StateCache(data)
        state, head = ch2walk.head(mesence, rom, data, out / 'head', cache)
        if state is None:
            print(json.dumps({'status': 'failed', 'head': head}, ensure_ascii=False))
            return 1
    with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
        jobs = {(s, n): pool.submit(run_once, mesence, rom, state, out / f'seed-{s}' / f'run-{n}', s)
                for s in seeds for n in (1, 2)}
    results = []
    for s in seeds:
        first, second = jobs[s, 1].result(), jobs[s, 2].result()
        r = {'seed': s, **judge(first, standers),
             'trace': hashlib.sha1(first.encode()).hexdigest()[:12]}
        if first != second:
            r['problems'].append('같은 시드 두 번의 기록이 다름')
        r['status'] = 'failed' if r['problems'] else 'passed'
        results.append(r)
        print(json.dumps(r, ensure_ascii=False), flush=True)
    ok = all(r['status'] == 'passed' for r in results)
    report = {'status': 'passed' if ok else 'failed', 'map': MAP, 'frames': FRAMES, 'standers': standers,
              'seeds': results}
    (out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print(json.dumps({'status': report['status'], 'seeds': len(results)}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
