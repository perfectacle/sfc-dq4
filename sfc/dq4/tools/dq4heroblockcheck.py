"""주인공이 선 자리 때문에 사건이 멈추지 않는지, 주인공을 걷게 하는 사건이 어느 칸에서 시작해도 같은 칸에 서는지 보는
검사(MesenCE 헤드리스). 규칙과 사건 목록은 sfc/dq4/docs/dq4-prologue-format.md 「주인공이 막는 사건」.

사건마다 주인공이 그 사건을 걸 수 있는 칸(말을 거는 이웃 칸, 판정 줄의 칸)을 모두 사례로 두고, 사례마다 같은 출발
상태에서 따로 돈다(--jobs 개씩 함께).
  1. 전원부터 새 게임 → 서장 첫 장면(dq4ch1walkcheck.prologue_start) → 명령 창을 닫고 성 마을 36/00 으로 순간이동해
     출발 상태를 만든다. 서장 첫 장면 지하와 다른 맵이라 어느 사건 맵으로도 같은 방법으로 옮길 수 있다.
  2. 사례마다 사건 맵으로 순간이동하며(dq5warp.lua) 그 사건 앞까지의 깃발을 SET 으로 두고, 난수·시각을 묶고 걸음 전투를
     없앤다. 도착한 첫 프레임에 난수·시각을 다시 둔다.
  3. lua/dq4heroblock.lua(walk.lua)로 그 칸까지 걸어 말을 걸고 A 를 넘긴 뒤, 사건이 끝났는지 본다: 깃발, 끝 맵, 인물
     자리(52 로 치웠으면 X = 80), 끝에 주인공이 다시 걸을 수 있는지(free 칸에 닿음), 메시지가 뜬 때의 자리·방향과 화면.

  MESENCE=… LIBDIR=… python sfc/dq4/tools/dq4heroblockcheck.py --rom work/ch1/dq4-ch1-full.sfc --out work/heroblock
  (--only 사례이름,… 은 그 사례만, --base 는 1단계 출발 상태를 다시 쓴다)
  --seed N·--seeds 0,5,9 는 2·3단계 난수(dq4ch1walkcheck.rng_for)를 고른다. 1단계 출발 상태는 늘 시드 0 이고 롬
  SHA-1 별로 work/cache/states/prologue 에 두어 다시 만들지 않는다(--no-state-cache 로 끔). 여러 시드면 seed-N/ 아래에 사례 폴더.
"""
import argparse
import concurrent.futures
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DQ5_TOOLS = HERE.parents[1] / 'dq5' / 'tools'
sys.path[:0] = [str(HERE), str(DQ5_TOOLS)]

import dq4ch1event as ev  # noqa: E402
import dq4ch1walkcheck as wc  # noqa: E402
import dq4prologue as pro  # noqa: E402
import dq4prologuecheck as pc  # noqa: E402
from dq5exitcheck import warp_exit  # noqa: E402

DRIVER = HERE / 'lua' / 'dq4heroblock.lua'
HUB = '36/00,16,72'


def flags(*pairs):
    """(7E:2190 + i, 마스크) 꼴 깃발을 켜는 SET 조각."""
    return ';'.join(f'{(0x2190 + i) & 0xFFFF:04X}|{m:02X}' for i, m in pairs)


def clear(*pairs):
    return ';'.join(f'{(0x2190 + i) & 0xFFFF:04X}&{~m & 0xFF:02X}' for i, m in pairs)


def chapter1(name):
    """1장 걷기 검사에서 그 구간 앞까지 켜졌을 깃발·동료."""
    names = [s[0] for s in wc.SEGMENTS]
    return wc.setup(wc.SEGMENTS, names.index(name))


def slot(n):
    """인물 표 슬롯 n 의 X·Y·방향을 보는 WATCH 조각."""
    return f'X{n:02X}=7E{0x3020 + n:04X}:1;Y{n:02X}=7E{0x3080 + n:04X}:1;F{n:02X}=7E{0x31E0 + n:04X}:1'


# 겹침을 셀 슬롯: 일행(0~7)과 인물 목록의 슬롯(8~, dq5-map-format 「인물 슬롯」). 일행과 인물 사이만 센다. 일행끼리는
# DQ5 에서도 서로 지나가며 겹쳐 그리고, 인물끼리는 돌아다니는 마을 사람이 어긋나 스치는 일이 있다(1C 와 무관)
TRACK = list(range(0x20))
PARTY_SLOTS = 8
HERO = 'HX=7E3020:1;HY=7E3080:1;HF=7E31E0:1;HP=7E3240:1;HQ=7E3260:1'

# 서장 저녁: 아버지(슬롯 0F)에게 오른쪽·왼쪽·위(의자 칸)에서. 주인공 셀은 반 칸(Y 짝수)에도 선다.
# 순간이동은 TO 보다 한 셀 아래에 내린다(dq5warp 의 「아래로 한 걸음」)
SUPPER_SET = f"{flags(pro.DONE, pro.FROG_MET, pro.SHINSIA_MET)};{clear(pro.SUPPER, pro.DINNER)}"
SUPPER_SNAP = {'HX': pro.HERO_AT[0], 'HY': pro.HERO_AT[1], 'HF': 0x88, 'HP': 0x08, 'HQ': 0x08,
               'X0F': 10, 'Y0F': 34, 'F0F': 0x20, 'X0E': 6, 'Y0E': 34, 'F0E': 0x10}
LEFT_SIDE = '12,33;6,33;6,37;8,37'
SUPPER = [(f'supper-{side}', at, face) for side, at, face in (
    ('right37', '12,37', 'left'), ('right36', '12,36', 'left'), ('right35', '12,35', 'left'),
    ('left37', LEFT_SIDE, 'right'), ('left36', LEFT_SIDE + ';8,36', 'right'),
    ('above10', '12,33;10,33;10,34', 'down'), ('above11', '12,33;11,33;11,34', 'down'))]
# 신시아(지하, (6,28)): 나가는 길 (8,28) → (8,14) 에 오른쪽 칸이 걸린다
SHINSIA_SET = f"{flags(pro.DONE, pro.FROG_MET)};{clear(pro.SHINSIA_START, pro.MORPH, pro.MORPH_BACK, pro.SHINSIA_MET)}"
SHINSIA = [('shinsia-right', '8,29', 'left'), ('shinsia-below', '8,31;6,31', 'up'),
           ('shinsia-left', '8,31;4,31;4,29', 'right')]
# 탑 병사(39/01 슬롯 08, (36,49)): 말을 걸면 (28,49) 쪽 왼쪽으로 걸어 나간다. 왼쪽 칸이 그 길 위
SOLDIER = [('soldier-below', '36,51', 'up'), ('soldier-left', '34,51;34,49', 'right'),
           ('soldier-left-half', '34,51;34,50', 'right'), ('soldier-right', '38,51;38,49', 'left'),
           ('soldier-above', '38,51;38,47;36,47', 'down')]
# 탑 위(39/04): X ≥ 44 로 Y 37 에 오면 아이(슬롯 0A)가 (46,35)까지 와서 운다
CRY = [(f'cry-{x}', f'{x},41;{x},37') for x in (44, 46, 48)]
# 탑 입구(39/00): Y 19 줄에 오면 마물(슬롯 08)과 아이(09)가 (18,15)·(16,15)에서 위로 걸어 나간다
KIDNAP = [(f'kidnap-{x}', f'{x},25;{x},19') for x in (16, 18, 20)]
# 이무르(37/00): 아이들이 따라오는 채 Y 47 줄에 오면 엄마 곁으로 보내고, 아이 둘이 줄 앞 (28,43)·(26,43)에서
# 나타나 (28,37)·(24,35)로 걷는다. 남쪽 입구에서 올라오는 통로의 X 마다(X 24·30 은 줄 아래가 막힘)
KIDS_HOME = [(f'kids-home-{x}', x) for x in (26, 28)]
# 보스 뒤 왕좌의 방: Y 51 줄의 X 24~38 에 오면 병사가 갈라서고 주인공이 통로로 걸어 왕 앞 줄까지. 출구 쪽 줄(Y 53)은
# 문지기 둘이 막아, 통로(X 30~32) 밖의 줄 칸은 위쪽 방에서 내려와야 닿는다. -pass 는 줄에서 서지 않고 지나간다.
# (이름, 순간이동 TO, 걸음)
LINEUP = [('king-30', '30,66', '30,53;30,51'), ('king-31', '30,66', '31,53;31,51'), ('king-32', '30,66', '32,53;32,51'),
          # 통로에서 위로 계속 누르면 병사 바로 아래 반 칸(Y 50)에 선다
          ('king-carpet-up', '30,66', '30,40'),
          ('king-24', '24,46', '24,51'), ('king-38', '38,46', '38,51'),
          ('king-26-pass', '26,46', '26,53'), ('king-36-pass', '36,46', '36,53'),
          # 벽 너머 0A 열의 줄 칸에서는 걸리지 않고, 돌아와 줄에 서야 걸린다
          ('king-outside', '20,46', '20,51;wait:300;20,53;26,53;26,51')]


def cases():
    """사례 목록: 이름 → {warp, set, walk, want(깃발), map, gone(52 로 치울 슬롯), at(끝 슬롯 자리), free, snap}."""
    out = {}
    talk = wc.talk
    for name, at, face in SUPPER:
        out[name] = {'warp': '3C/00,12,36', 'set': SUPPER_SET, 'walk': f'{at};{talk(face, 70)}', 'maxf': 4500,
                     'changes': 1, 'map': '36/01', 'want': [('DINNER', pro.DINNER)],
                     'snap': (pro.M_SUPPER_LINES[0], SUPPER_SNAP), 'watch': ';'.join((HERO, slot(0x0E), slot(0x0F)))}
    for name, at, face in SHINSIA:
        out[name] = {'warp': '3C/01,8,28', 'set': SHINSIA_SET, 'walk': f'{at};{talk(face, 40)}', 'free': '8,31',
                     'want': [('SHINSIA_MET', pro.SHINSIA_MET)]}
    extra, _ = chapter1('soldier')
    for name, at, face in SOLDIER:
        out[name] = {'warp': '39/01,36,50', 'set': extra, 'walk': f'{at};{talk(face, 6)};wait:300', 'free': '36,53',
                     'want': [('SOLDIER', ev.SOLDIER_LEFT)], 'gone': [0x08]}
    extra, _ = chapter1('boss')
    for name, at in CRY:
        out[name] = {'warp': '39/04,46,40', 'set': extra, 'walk': f'{at};wait:200;{wc.taps(4)};{pc.CLOSE}',
                     'free': '44,41', 'at': {0x0A: (46, 35)}}
    extra, _ = chapter1('kidnap')
    for name, at in KIDNAP:
        out[name] = {'warp': '39/00,18,24', 'set': extra, 'walk': f'{at};{wc.taps(6)};{pc.CLOSE};wait:200',
                     'free': '18,25', 'want': [('KIDNAPPED', ev.KIDNAPPED)], 'gone': [0x08, 0x09]}
    extra, party = chapter1('homecoming')
    for name, x in KIDS_HOME:
        out[name] = {'warp': f'37/00,{x},49', 'set': extra, 'party': party,
                     'walk': f'{x},45;{wc.taps(6)};{pc.CLOSE};wait:300', 'not': [('KIDS_FOLLOW', ev.KIDS_FOLLOW)]}
    extra, party = chapter1('castle')
    for name, to, at in LINEUP:
        out[name] = {'warp': f'36/01,{to}', 'set': extra, 'party': party, 'walk': f'{at};{wc.taps(200, 60)}',
                     'maxf': 16000, 'changes': 1, 'map': '36/00', 'want': [('REPORTED', ev.REPORTED)]}
    # 아이들을 데리고 오면 돌려보내라 하고 조작을 돌려준다. 줄로 내려가면(지나쳐도) 다시 왕 앞까지 걷고 또 말한다
    kids = f"{extra};{flags(ev.KIDS_FOLLOW)}"
    out['king-kids'] = {'warp': '36/01,30,66', 'set': kids, 'party': party,
                        'walk': f'30,53;30,51;wait:400;{wc.taps(4)};{pc.CLOSE};32,47;32,53;wait:400;'
                                f'{wc.taps(4)};{pc.CLOSE}', 'free': '32,45', 'maxf': 6000,
                        'not': [('REPORTED', ev.REPORTED)], 'repeat': 2}
    return out


def overlaps(text):
    """track.txt(lua/dq4heroblock.lua 의 TRACK)에서 두 인물이 겹쳐 보인 프레임 수와 처음 몇 프레임.
    인물은 16×16 점(2×2 셀)을 차지하므로 X·Y 점 차가 둘 다 16 보다 작으면 겹친다. 그리지 않는 슬롯은 빼고 일행과 인물
    사이만 센다."""
    frames, first = 0, []
    for line in text.splitlines():
        f, *slots = line.split()
        seen = []
        for v in slots:
            n, rest = v.split(':')
            x, y, gone = map(int, rest.split(','))
            if not gone:
                seen.append((n, x, y))
        hits = [f'{a[0]}/{b[0]}' for i, a in enumerate(seen) for b in seen[i + 1:]
                if (int(a[0], 16) < PARTY_SLOTS) != (int(b[0], 16) < PARTY_SLOTS) and abs(a[1] - b[1]) < 16 and abs(a[2] - b[2]) < 16]
        if hits:
            frames += 1
            if len(first) < 3:
                first.append(f"{f}:{'+'.join(hits)}")
    return frames, first


def run_case(mesence, rom, base, out, name, case, exit_at, seed=0):
    dest = out / name
    rng = wc.rng_for(seed)
    pins = f'{rng};{wc.DAY_SET}'
    wc.run(mesence, rom, wc.WARP, dest / 'warp', {
        'STATE': str(base), 'TO': case['warp'], 'SAVE': 'end.mss', 'SETTLE': '60', 'MAXF': '1500',
        'WARPEXIT': f'{exit_at:X}', 'ANYWHERE': '1', 'ROMPATCH': wc.NO_ENCOUNTERS,
        'SET': ';'.join(v for v in (pins, case['set']) if v), 'LATESET': ';'.join(v for v in (pins, case.get('late')) if v),
        **({'PARTY': case['party']} if case.get('party') else {})}, 300)
    state = dest / 'warp' / 'end.mss'
    problems = []
    if not state.exists():
        return {'name': name, 'seed': seed, 'status': 'failed', 'problems': ['순간이동 실패']}
    walk = case['walk'] + (f";{case['free']}" if case.get('free') else '')
    watch = ';'.join(v for v in (HERO, case.get('watch', ''),
                                 ';'.join(slot(n) for n in case.get('gone', [])),
                                 ';'.join(slot(n) for n in case.get('at', {})),
                                 ';'.join(f'{k}=7E{0x2190 + i:04X}:1' for k, (i, _) in
                                          case.get('want', []) + case.get('not', []))) if v)
    env = {'STATE': str(state), 'WALK': str(wc.WALK), 'WALK_STATE': str(wc.WALK_STATE), 'WAYPOINTS': walk,
           'MAXF': str(case.get('maxf', wc.frames(walk))), 'CHANGES': str(case.get('changes', 99)), 'AFTER': '30',
           'WATCH': watch, 'ROMPATCH': wc.NO_ENCOUNTERS, 'SET': rng}
    if 'snap' in case:
        env.update(SNAPMSG=f"{case['snap'][0]:X}", SNAPWATCH=case['watch'])
    env['TRACK'] = ','.join(f'{n:02X}' for n in TRACK)
    wc.run(mesence, rom, DRIVER, dest, env, int(env['MAXF']) // 40 + 120)
    text = (dest / 'walk.txt').read_text(encoding='utf-8') if (dest / 'walk.txt').exists() else ''
    seen = {k: int(v, 16) for k, v in re.findall(r'^(\w+)=([0-9A-F]+)$', text, re.M)}
    end = re.search(r'end map (\w\w/\w\w) x=(\d+) y=(\d+)', text)
    if not end:
        problems.append('기록 없음')
    if 'map' in case and (not end or end[1] != case['map']):
        problems.append(f"끝 맵 {end[1] if end else None}, 기대 {case['map']}")
    for k, (_, m) in case.get('want', []):
        if not seen.get(k, 0) & m:
            problems.append(f'깃발 {k} 꺼짐')
    for k, (_, m) in case.get('not', []):
        if seen.get(k, 0) & m:
            problems.append(f'깃발 {k} 켜짐')
    for n in case.get('gone', []):
        if seen.get(f'X{n:02X}') != 0x80:
            problems.append(f'슬롯 {n:02X} 이 남음 ({seen.get(f"X{n:02X}")},{seen.get(f"Y{n:02X}")})')
    for n, (x, y) in case.get('at', {}).items():
        if (seen.get(f'X{n:02X}'), seen.get(f'Y{n:02X}')) != (x, y):
            problems.append(f'슬롯 {n:02X} 자리 ({seen.get(f"X{n:02X}")},{seen.get(f"Y{n:02X}")}), 기대 ({x},{y})')
    shown = re.search(r'^messages (.*)$', text, re.M)
    shown = [v.split('@')[0] for v in shown[1].split(',') if v] if shown else []
    if case.get('repeat') and (not shown or shown.count(shown[0]) < case['repeat']):
        problems.append(f"첫 메시지가 {case['repeat']}번 뜨지 않음: {shown}")
    if case.get('free') and f"reached {case['free']}" not in text:
        problems.append(f"끝에 {case['free']} 로 걷지 못함(조작이 돌아오지 않음)")
    snap = {}
    if 'snap' in case:
        snap_file = dest / 'snap.txt'
        snap = ({k: int(v, 16) for k, v in re.findall(r'^(\w+)=([0-9A-F]+)$', snap_file.read_text(), re.M)}
                if snap_file.exists() else {})
        if not snap:
            problems.append('메시지가 뜨지 않음')
        for k, v in case['snap'][1].items():
            if snap and snap.get(k) != v:
                problems.append(f'{k}={snap.get(k)}, 기대 {v}')
    overlap, track = None, dest / 'track.txt'
    if not track.exists():
        problems.append('track.txt 없음')
    else:
        overlap, first = overlaps(track.read_text())
        if overlap:
            problems.append(f'인물이 겹쳐 보인 프레임 {overlap}개(처음 {first})')
    return {'name': name, 'seed': seed, 'status': 'failed' if problems else 'passed', 'problems': problems, 'overlap': overlap,
            'end': end[0] if end else None, 'hero': (seen.get('HX'), seen.get('HY')), 'snap': snap,
            'stuck': re.findall(r'stuck at \S+ heading \S+', text)}


def make_base(mesence, rom, out, cache=None):
    """서장 첫 장면 → 명령 창 닫기 → 성 마을 36/00. 사례마다 여기서 사건 맵으로 옮긴다. 시드와 상관없이 시드 0 으로
    만들고, cache(dq4ch1walkcheck.StateCache)에 같은 롬·같은 코드로 만든 것이 있으면 그것을 쓴다."""
    key = wc.code_key(mesence, Path(__file__), HUB) if cache else None
    base = out / 'hub' / 'end.mss'
    if cache and cache.get('heroblock-hub', key, '.mss', base):
        return base, True
    start = wc.prologue_start(mesence, rom, out)
    wc.run(mesence, rom, wc.WALK_STATE, out / 'close', {'STATE': str(start), 'WALK': str(wc.WALK),
                                                       'WAYPOINTS': f'{pc.CLOSE};wait:30', 'SAVE': 'end.mss',
                                                       'MAXF': '200', 'CHANGES': '99'}, 120)
    pins = f'{wc.RNG};{wc.DAY_SET}'
    wc.run(mesence, rom, wc.WARP, out / 'hub', {
        'STATE': str(out / 'close' / 'end.mss'), 'TO': HUB, 'SAVE': 'end.mss', 'SETTLE': '60', 'MAXF': '1500',
        'WARPEXIT': f'{warp_exit(rom):X}', 'ANYWHERE': '1', 'ROMPATCH': wc.NO_ENCOUNTERS, 'SET': pins,
        'LATESET': pins}, 300)
    if not base.exists():
        raise SystemExit('출발 상태를 만들지 못함')
    log = out / 'hub' / 'warp.txt'
    # 세이브스테이트는 도착하지 못해도 남는다. 도착한 것만 캐시에 두어 다음 실행이 틀린 출발점을 받지 않게 한다
    arrived = re.search(r'arrived map (\w\w/\w\w)', log.read_text(encoding='utf-8')) if log.exists() else None
    if cache and arrived and arrived[1] == HUB[:5]:
        cache.put('heroblock-hub', key, '.mss', base, {'name': 'hub', 'arrived': arrived[1]})
    return base, False


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', required=True, type=Path)
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--jobs', type=int, default=6)
    ap.add_argument('--only', help='이 사례만(쉼표로 여럿, 앞부분이 같으면 모두: supper)')
    ap.add_argument('--base', type=Path, help='같은 롬으로 만든 출발 상태(hub/end.mss)')
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
    began = time.monotonic()
    cache = None if args.no_state_cache else wc.StateCache(rom.read_bytes())
    if args.base:
        base, cached = args.base.resolve(), None
    else:
        base, cached = make_base(mesence, rom, out, cache)
    todo = cases()
    if args.only:
        keys = args.only.split(',')
        todo = {k: v for k, v in todo.items() if any(k == p or k.startswith(p + '-') for p in keys)}
    exit_at = warp_exit(rom)
    with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
        jobs = [pool.submit(run_case, mesence, rom, base, wc.seed_dir(out, s, seeds), k, v, exit_at, s)
                for s in seeds for k, v in todo.items()]
        results = []
        for job in concurrent.futures.as_completed(jobs):
            r = job.result()
            results.append(r)
            print(json.dumps(r, ensure_ascii=False), flush=True)
    results.sort(key=lambda r: (seeds.index(r['seed']), list(todo).index(r['name'])))
    per_seed = []
    for s in seeds:
        rs = [r for r in results if r['seed'] == s]
        passed = len(rs) == len(todo) and all(r['status'] == 'passed' for r in rs)
        per_seed.append({'seed': s, 'rng': wc.rng_for(s), 'status': 'passed' if passed else 'failed', 'cases': rs})
    ok = all(r['status'] == 'passed' for r in per_seed)
    report = {'status': 'passed' if ok else 'failed', 'seconds': round(time.monotonic() - began),
              'state_cache': 'off' if cached is None or cache is None else 'hit' if cached else 'miss', 'seeds': per_seed}
    if len(seeds) == 1:
        report.update(seed=seeds[0], rng=per_seed[0]['rng'], cases=per_seed[0]['cases'])
    (out / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n')
    print(json.dumps({'status': report['status'], 'seconds': report['seconds'], 'state_cache': report['state_cache'],
                      'failed': [f"{r['seed']}:{r['name']}" for r in results if r['status'] != 'passed']},
                     ensure_ascii=False))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
