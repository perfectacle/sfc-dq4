"""장마다 일행 전용 OBJ 줄(dq4people.PARTIES)이 그 장 일행이 서는 맵에서 실제 CGRAM 에 그 일행 색으로 실리는지 본다.

깃발로 줄을 덮는 장(2장부터)마다 그 장 출발 상태(걷기 검사 dq4ch<N>walkcheck 의 head)에서, 그 장 걷기 검사 표가
순간이동하는 맵 가운데 맵 그룹마다 앞·뒤 하나씩으로 순간이동(dq5warp.lua)하고 30프레임 뒤 CGRAM·OAM·WRAM 을
덤프한다(lua/dq4peopledump.lua). 기대 색은 롬의 맵 팔레트 루틴(01:996A)을 그 장 깃발을 켜고 그 장 첫 그룹의 XX/00 으로
돌린 일행 줄이다. 맵마다 일행 줄 색이 같고, 화면 안 OAM 에 선두의 줄이 있어야 통과한다. 장이 늘면 PARTIES 와 그 장
걷기 검사만 있으면 장면이 저절로 붙는다. 서장·1장 일행 줄은 깃발 없는 기본 줄이라 단위 시험(test_dq4partylines)만 본다.

선두 밖 일행(용병 등)과 따라 걷는 그림(FOLLOWERS, 개 등)은 JOINS 의 기록·깃발을 순간이동 때 써 넣어 같은 맵마다 세운다.
그 그림의 인물 슬롯이 제 세트로 화면에 그려지고(dq4peoplecheck.judge), 전용 줄이면 Person.palette 줄을 쓰며 그 CGRAM 색이
위 기대 색과 같아야 한다. 공용 줄이면 배치 표 slots 의 NDS 색마다 그 줄 안에 SHARED_TOLERANCE 안의 색이 있고, 그 그림의
타일이 쓰는 색 번호마다 맵 사이 색 차이도 SHARED_TOLERANCE 안이어야 한다(그 그룹에 배치되지 않은 그림은 칸에 다른 인물
색이 모인다). 공용 줄 판정은 실제로 그려진 색만 보므로, 배치 표에 그룹이 빠졌어도 색이 우연히 같으면 지난다. 배치 표
그룹은 단위 시험이 본다.

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

# 따라 걷는 그림(전용 줄 없음, PARTIES 밖): 장 → {이름: 배치 표(people-pin.toml)의 인물}
FOLLOWERS = {3: {'개': '개'}}
# 공용 줄 칸 색과 그 그림 NDS 색의 채널별 차이 한도(5비트 단위). 배치 표대로면 칸 색은 그 칸에 모인 색 가운데 하나다
SHARED_TOLERANCE = 6


def _hired(who):
    """용병을 고용한 뒤의 일행 기록(dq4ch3endor_checks.effects 와 같은 꼴, 일행 둘째 칸)과 깃발."""
    def make(data):
        import dq4ch3event as ch3
        import dq4mercenary as merc
        rec = merc.record(data, who)
        party = ';'.join(f'{(ch3.PARTY_ITEMS - 0x16 + ch3.RECORD) + k & 0xFFFF:04X}={b:02X}' for k, b in enumerate(rec))
        flag = merc.FLAGS[who]
        return f'{party};201D=02;201F=02;201E=02;2021=01;2029=01;{0x2190 + flag[0]:04X}|{flag[1]:02X}'
    return make


def _flag(flag_of):
    def make(data):
        f = flag_of()
        return f'{0x2190 + f[0]:04X}|{f[1]:02X}'
    return make


def _ch3(name):
    import dq4ch3event
    return getattr(dq4ch3event, name)


# 장 → {역할·이름: (그림, 그 그림을 일행 뒤에 세우는 SET 을 롬 바이트로 만드는 함수)}. 선두 밖 PARTIES 와 FOLLOWERS 는
# 여기에 있어야 한다(test_dq4partylines 가 봄)
def _ch2_joined(data):
    import dq4ch2walkcheck
    return dq4ch2walkcheck.join_set(data)


def _ch2(name):
    import dq4ch2event
    return getattr(dq4ch2event, name)


JOINS = {
    2: {'크리프트': (lambda: _ch2('KIRYL_PICTURE'), _ch2_joined),
        '브라이': (lambda: _ch2('BREY_PICTURE'), _ch2_joined)},
    3: {'스콧': (lambda: _ch3('SCOTT_PICTURE'), _hired('scott')),
        '로렌스': (lambda: _ch3('LAWRENCE_PICTURE'), _hired('lawrence')),
        '개': (lambda: __import__('dq4npcport').PICTURES[__import__('dq4ch1event').FC_DOG_PICTURE],
               _flag(lambda: _ch3('DOG')))},
}


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
    problems = [f'롬이 줄 {n} 을 그 장 첫 그룹에서 덮지 않음' for n in sorted(want) if not any(want[n])]
    problems += [f'줄 {n} 색이 다름({got[n][:6].hex()}… 기대 {want[n][:6].hex()}…)' for n in sorted(want)
                 if any(want[n]) and got[n] != want[n]]
    if leader not in {oam[i * 4 + 3] >> 1 & 7 for i in range(128) if oam[i * 4 + 1] < 224}:
        problems.append(f'화면 안 OAM 에 선두 줄 {leader} 이 없음')
    return problems


def member_line(chapter, name):
    """(줄, 전용 줄인지)."""
    if name in FOLLOWERS.get(chapter, {}):
        return pins()[FOLLOWERS[chapter][name]]['line'], False
    return next(p.palette for p in P.PEOPLE if p.role == name), True


def pins():
    import tomllib
    return tomllib.loads(P.PINS.read_text())['person']


def bgr(c):
    return c & 0x1F, c >> 5 & 0x1F, c >> 10 & 0x1F


def used_indices(vram, base, count):
    """세트 타일(VRAM C000~)이 쓰는 색 번호(0 투명 빼고)."""
    out = set()
    for t in range(count):
        b = vram[0xC000 + (base + t) * 32:0xC000 + (base + t) * 32 + 32]
        for y in range(8):
            planes = (b[y * 2], b[y * 2 + 1], b[16 + y * 2], b[16 + y * 2 + 1])
            for x in range(8):
                out.add(sum((pl >> (7 - x) & 1) << n for n, pl in enumerate(planes)))
    return sorted(out - {0})


def spread_problems(results):
    """따라 걷는 그림(공용 줄)이 쓰는 색 번호마다 맵 사이 색 차이가 SHARED_TOLERANCE 를 넘으면 문제. 배치되지 않은 그룹에서는
    그 칸에 다른 인물 색이 모여 벌어진다."""
    by = {}
    for r in results:
        for name, colors in r.get('colors', {}).items():
            for i, c in colors.items():
                by.setdefault((name, i), []).append((r['map'], c))
    out = []
    for (name, i), seen in sorted(by.items()):
        d = max(max(abs(a - b) for a, b in zip(c1, c2)) for _, c1 in seen for _, c2 in seen)
        if d > SHARED_TOLERANCE:
            out.append(f'{name}: 색 {i} 이 맵마다 다름(차이 {d}: ' + ', '.join(f'{m} {c}' for m, c in seen) + ')')
    return out


def judge_member(rom, wram, vram, oam, cgram, chapter, name, picture, want, seen):
    line, own = member_line(chapter, name)
    slots = [sl for sl in pc.judge(rom, wram, vram) if sl['picture'] == picture]
    if not slots:
        return [f'{name}: 그림 {picture:02X} 슬롯 없음']
    sl = slots[0]
    problems = [] if sl['ok'] else [f"{name}: 슬롯 판정 {sl.get('tiles')} {sl.get('cells')} {sl.get('palette')}"]
    if 'base' in sl and not pc.shown(oam, sl['base'], int(sl['tiles'].split('/')[1])):
        problems.append(f'{name}: 화면에 없음')
    used = sl.get('palette', '').rsplit('(', 1)[-1].rstrip(')')
    if own and used != str(line):
        problems.append(f'{name}: 줄 {used}(기대 전용 줄 {line})')
    if not used.isdigit():
        return problems
    line = int(used)
    got = cgram[0x100 + line * 32 + 2:0x100 + line * 32 + 32]
    if own:
        if got != want.get(line, b''):
            problems.append(f'{name}: 줄 {line} 색이 다름({got[:6].hex()}… 기대 {want.get(line, b"")[:6].hex()}…)')
        return problems
    # 공용 줄: 그 그림의 NDS 색마다 줄 안에 가까운 색이 있어야 한다. 칸 차례는 배치 표를 다시 뜨면 바뀌므로 보지 않는다
    colors = [bgr(got[k * 2] | got[k * 2 + 1] << 8) for k in range(15)]
    seen[name] = {i: colors[i - 1] for i in used_indices(vram, sl['base'], int(sl['tiles'].split('/')[1]))}
    far = []
    for entry in pins()[FOLLOWERS[chapter][name]]['slots']:
        rgb = entry.split('=')[0]
        nds = [int(rgb[i:i + 2], 16) >> 3 for i in (0, 2, 4)]
        d = min(max(abs(a - b) for a, b in zip(c, nds)) for c in colors)
        if d > SHARED_TOLERANCE:
            far.append(f'{rgb} 차이 {d}')
    if far:
        problems.append(f'{name}: 줄 {line} 에 NDS 색이 없음({", ".join(far[:4])})')
    return problems


def scene(mesence, rom, base, out, chapter, m, cell, want, leader, member=None):
    tag = (m.replace('/', '') if m else 'start') + (f'-{member[0]}' if member else '')
    dest = out / f'ch{chapter}' / tag
    dest.mkdir(parents=True, exist_ok=True)
    state = base
    if member is not None and cell is None:
        return {'chapter': chapter, 'map': m, 'ok': False, 'problems': ['출발 맵에는 세우지 않음']}
    if cell is not None:
        env = {'STATE': str(base), 'TO': f'{m},{cell[0]},{cell[1]}', 'SAVE': 'end.mss', 'SETTLE': '120', 'MAXF': '1500',
               'WARPEXIT': f'{warp_exit(rom):X}', 'ANYWHERE': '1', **({'SET': member[2]} if member else {})}
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
    cgram, oam = (dest / 'cgram.bin').read_bytes(), (dest / 'oam.bin').read_bytes()
    problems = ([] if m in (found, None) else [f'맵 {found}']) + judge(want, leader, cgram, oam)
    seen = {}
    if member is not None:
        problems += judge_member(rom.read_bytes(), wram, (dest / 'vram.bin').read_bytes(), oam, cgram, chapter,
                                 member[0], member[1], want, seen)
    return {'chapter': chapter, 'map': m or found, **({'member': member[0]} if member else {}),
            'ok': not problems, 'problems': problems, **({'colors': seen} if seen else {})}


def run_chapter(mesence, rom, data, out, chapter, jobs, cache):
    mod = importlib.import_module(f'dq4ch{chapter}walkcheck')
    base, head = mod.head(mesence, rom, data, out / f'ch{chapter}' / 'head', cache)
    if base is None:
        return [{'chapter': chapter, 'map': None, 'ok': False, 'problems': ['출발 상태 없음'], 'head': head}]
    want = expected_lines(data, chapter)
    if not any(want[n] for n in want if n == party(chapter)[0][1]):
        return [{'chapter': chapter, 'map': None, 'ok': False, 'problems': ['롬이 그 장 첫 그룹에서 선두 줄을 덮지 않음']}]
    leader = party(chapter)[0][1]
    places = list(spots(chapter).items())
    scenes = [(None, None, None)] + [(m, c, None) for m, c in places]
    for name, (picture, make) in JOINS.get(chapter, {}).items():
        scenes += [(m, c, (name, picture(), make(data))) for m, c in places]
    with concurrent.futures.ThreadPoolExecutor(jobs) as pool:
        results = list(pool.map(lambda s: scene(mesence, rom, base.resolve(), out, chapter, s[0], s[1], want, leader,
                                                s[2]), scenes))
    spread = spread_problems(results)
    return results + ([{'chapter': chapter, 'map': '맵 사이', 'ok': False, 'problems': spread}] if spread else [])


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
