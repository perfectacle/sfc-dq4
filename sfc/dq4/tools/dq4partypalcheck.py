"""장마다 일행 전용 OBJ 줄(dq4people.PARTIES)이 그 장 일행이 서는 맵에서 실제 CGRAM 에 그 일행 색으로 실리는지 본다.

깃발로 줄을 덮는 장(2장부터)마다 그 장 출발 상태(걷기 검사 dq4ch<N>walkcheck 의 head)에서, 그 장 걷기 검사 표가
순간이동하는 맵 가운데 맵 그룹마다 앞·뒤 하나씩으로 순간이동(dq5warp.lua)하고 30프레임 뒤 CGRAM·OAM·WRAM 을
덤프한다(lua/dq4peopledump.lua). 기대 색은 롬의 맵 팔레트 루틴(01:996A)을 그 장 깃발을 켜고 그 장 첫 그룹의 XX/00 으로
돌린 일행 줄이다. 맵마다 일행 줄 색이 같고, 화면 안 OAM 에 선두의 줄이 있어야 통과한다. 장이 늘면 PARTIES 와 그 장
걷기 검사만 있으면 장면이 저절로 붙는다. 서장·1장 일행 줄은 깃발 없는 기본 줄이라 단위 시험(test_dq4partylines)만 본다.

  MESENCE=… LIBDIR=… python sfc/dq4/tools/dq4partypalcheck.py --rom work/ch3/dq4-ch1-full.sfc --out work/partypal
"""
import argparse
import concurrent.futures
import importlib
import json
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools'), str(HERE.parents[2] / 'fc' / 'dq4' / 'tools')]

import dq4ch1walkcheck as wc  # noqa: E402
import dq4mesen  # noqa: E402
import dq4people as P  # noqa: E402
import dq4peoplecheck as pc  # noqa: E402
import dq5objpalette  # noqa: E402
from dq5exitcheck import warp_exit  # noqa: E402
from w65816 import Cpu  # noqa: E402


def party(chapter):
    """[(역할, 줄, 깃발)] — 선두(leader)가 앞."""
    people = [next(p for p in P.PEOPLE if p.role == r) for r in P.PARTIES[chapter]]
    return [(p.role, p.palette, p.flag) for p in sorted(people, key=lambda p: not p.leader)]


def flagged_chapters():
    return [c for c in sorted(P.PARTIES) if all(f is not None for _, _, f in party(c))
            and (HERE / f'dq4ch{c}walkcheck.py').exists()]


def spots(chapter):
    """그 장 걷기 표의 순간이동 맵 가운데 그룹마다 처음·마지막 것 {맵: (x, y)}."""
    mod = importlib.import_module(f'dq4ch{chapter}walkcheck')
    by = {}
    for seg in mod.SEGMENTS[max(getattr(mod, 'HEAD', 0) - 1, 0):]:
        if seg[1] == 'warp':
            m, x, y = seg[2].split(',')[:3]
            if int(m[:2], 16) in P.party_groups(chapter):
                by.setdefault(m[:2], []).append((m, (int(x), int(y))))
    return dict(v for g in sorted(by) for v in (by[g][0], by[g][-1]))


def expected_lines(data, chapter):
    """그 장 깃발을 켜고 그 장 첫 그룹 XX/00 으로 맵 팔레트 루틴을 돌린 일행 줄(CGRAM 바이트)."""
    c = Cpu(data, bytearray(0x20000))
    c.wram[0xBC], c.wram[0xBD], c.wram[0xBE] = P.party_groups(chapter)[0], 0x00, 0x80
    for _, _, flag in party(chapter):
        c.wram[0x2190 + flag[0]] |= flag[1]
    c.dbr = 0x01
    c.jsr(dq5objpalette.MAP_LOADER)
    w = bytes(c.wram[0x3914:0x3D14])
    return {n: w[(8 + n) * 32 + 2:(8 + n) * 32 + 32] for _, n, _ in party(chapter)}


def judge(want, leader, cgram, oam):
    got = {n: cgram[0x100 + n * 32 + 2:0x100 + n * 32 + 32] for n in want}
    problems = [f'줄 {n} 색이 다름({got[n][:6].hex()}… 기대 {want[n][:6].hex()}…)' for n in sorted(want)
                if got[n] != want[n]]
    if leader not in {oam[i * 4 + 3] >> 1 & 7 for i in range(128) if oam[i * 4 + 1] < 224}:
        problems.append(f'화면 안 OAM 에 선두 줄 {leader} 이 없음')
    return problems


def scene(mesence, rom, base, out, chapter, m, cell, want, leader):
    dest = out / f'ch{chapter}' / (m.replace('/', '') if m else 'start')
    dest.mkdir(parents=True, exist_ok=True)
    state = base
    if cell is not None:
        env = {'STATE': str(base), 'TO': f'{m},{cell[0]},{cell[1]}', 'SAVE': 'end.mss', 'SETTLE': '120', 'MAXF': '1500',
               'WARPEXIT': f'{warp_exit(rom):X}', 'ANYWHERE': '1'}
        wc.run(mesence, rom, wc.WARP, dest, env, 300)
        state = dest / 'end.mss'
        if not state.exists():
            return {'chapter': chapter, 'map': m, 'ok': False, 'problems': ['워프 실패']}
    env = dict(os.environ, STATE=str(state.resolve()), OUT=str(dest.resolve()), WAIT='30', POKE='')
    dq4mesen.run(mesence, rom, pc.DUMP, folder=dest, tag='partypal', env=env, timeout=120, capture_output=True)
    if not (dest / 'wram.bin').exists():
        return {'chapter': chapter, 'map': m, 'ok': False, 'problems': ['덤프 없음']}
    wram = (dest / 'wram.bin').read_bytes()
    found = f'{wram[0xBC]:02X}/{wram[0xBD]:02X}'
    problems = ([] if m in (found, None) else [f'맵 {found}']) + \
        judge(want, leader, (dest / 'cgram.bin').read_bytes(), (dest / 'oam.bin').read_bytes())
    return {'chapter': chapter, 'map': m or found, 'ok': not problems, 'problems': problems}


def run_chapter(mesence, rom, data, out, chapter, jobs, cache):
    mod = importlib.import_module(f'dq4ch{chapter}walkcheck')
    base, head = mod.head(mesence, rom, data, out / f'ch{chapter}' / 'head', cache)
    if base is None:
        return [{'chapter': chapter, 'map': None, 'ok': False, 'problems': ['출발 상태 없음'], 'head': head}]
    want = expected_lines(data, chapter)
    if not all(any(v) for v in want.values()):
        return [{'chapter': chapter, 'map': None, 'ok': False, 'problems': ['롬이 그 장 첫 그룹에서 일행 줄을 덮지 않음']}]
    leader = party(chapter)[0][1]
    scenes = [(None, None)] + list(spots(chapter).items())
    with concurrent.futures.ThreadPoolExecutor(jobs) as pool:
        return list(pool.map(lambda s: scene(mesence, rom, base.resolve(), out, chapter, s[0], s[1], want, leader),
                             scenes))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', required=True, type=Path, help='검사할 장까지 넘어가는 dq4build.py 롬')
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--chapters', type=int, nargs='+', help='이 장만(기본: 깃발로 줄을 덮고 걷기 검사가 있는 장 모두)')
    ap.add_argument('--jobs', type=int, default=4, help='함께 띄울 MesenCE 수')
    ap.add_argument('--no-state-cache', action='store_true', help='출발 상태 캐시를 쓰지 않음')
    args = ap.parse_args()
    mesence = Path(os.environ['MESENCE'])
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f'{out} is not empty')
    out.mkdir(parents=True, exist_ok=True)
    rom = out / 'c.sfc'
    shutil.copyfile(args.rom.resolve(), rom)
    data = rom.read_bytes()
    cache = None if args.no_state_cache else wc.StateCache(data)
    results = []
    for chapter in args.chapters or flagged_chapters():
        results += run_chapter(mesence, rom, data, out, chapter, args.jobs, cache)
    for r in results:
        print(json.dumps(r, ensure_ascii=False, default=str), flush=True)
    failed = [f"{r['chapter']}:{r['map']}" for r in results if not r['ok']]
    print(json.dumps({'status': 'failed' if failed or not results else 'passed', 'scenes': len(results),
                      'failed': failed}, ensure_ascii=False))
    return 1 if failed or not results else 0


if __name__ == '__main__':
    sys.exit(main())
