"""3장 동료 대화(dq4ch3partytalk 의 줄, 표·훅은 dq4ch2partytalk) 실행 검사(MesenCE 헤드리스).

3장 출발 상태(dq4ch3walkcheck.head)에서 3장 동료 대화 줄이 있는 맵마다 한 번 순간이동해 말 상대가 없는 쪽을 보고
서고, 단계(아래)마다 flag·시각·일행·용병 날수·물건을 WRAM 에 써 가며 명령 창 「はなす」를 고른다(lua/dq4partytalk.lua,
2장 검사와 같은 lua). 단계마다 보행 메시지(24:8BAF)가 받은 번호가 하나이고, 롬의 동료 대화 표를 조건 평가 루틴의
모형(dq4ch2partytalkcheck.pick)으로 따라 고른 메시지(맞는 줄이 없으면 129)여야 한다. 단계마다 「마지막으로 고른 줄」과
「말 건 사람」 값을 0 으로 둔다.

  일행   none(톨네코 혼자), scott·lawrence(용병 하나), both(둘). 용병은 일행 기록 1·2 에 손님 기록(dq4mercenary.record)과
         동행 flag 를 쓴다. 일행이 없는 단계는 모두 129 여야 한다(3장 동료 대화는 용병·개만 말함).
  단계   맵 자리마다 3장 진행 단계(dq4ch3partytalk.STAGES) × 낮·밤을 둘이 함께, 마지막 단계에서 하나씩·없음. 필드는
         용병 하나씩 날수 0~4. 은의 여신상을 가진 단계(여신상 동굴·수집가 집)와 개가 따라오는 단계(레이크나바·여우 마을).
  말 건 뒤  PEOPLE 의 사람 바로 아래에 순간이동해 위를 보고 말을 걸고(대화 시작 훅이 7E:21FD 에 적음) 아래로 돌아서서
         「はなす」 를 고른다. 말 상대 칸이 그 사람이고, 7E:21FD 가 그 대화 번호의 번호 표 차례 + 1 이고, 동료 대사가 그 값으로
         고른 「말 건 뒤」 줄이어야 한다.

맵 자리는 FC 맵에서 걸을 수 있고 바로 아래가 벽이며 옮긴 인물(dq4npcport)에서 세 칸 넘게 떨어진 칸을 고른다. 인물은
HOLD 로 세운다. 3장 출발 상태와 같은 맵(3E/01)은 한 번 다른 맵을 거친다(dq4ch3walkcheck.HOPS).

  MESENCE=... LIBDIR=$(uv run krpatch sfc lua) \\
    uv run --locked python sfc/dq4/tools/dq4ch3partytalkcheck.py --rom work/ch3/dq4-ch1-full.sfc --out work/ch3talk
"""
import argparse
import concurrent.futures
import json
import os
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools'), str(HERE.parents[2] / 'fc' / 'dq4' / 'tools')]

import dq4ch1walkcheck as wc  # noqa: E402
import dq4ch2event as ch2  # noqa: E402
import dq4ch2partytalk as pt  # noqa: E402
import dq4ch2partytalkcheck as base  # noqa: E402
import dq4ch3event as ch3  # noqa: E402
import dq4ch3partytalk as c3  # noqa: E402
import dq4ch3walkcheck as cw3  # noqa: E402
import dq4mercenary as merc  # noqa: E402

LUA = base.LUA
HOLD = base.HOLD
DAY, NIGHT = ch2.MORNING, ch2.NIGHT
RECORD = 42
ITEM_SLOT = (ch3.PARTY_ITEMS & 0xFFFF) + 11      # 톨네코 물건 칸 11(끝 칸): 여신상을 두거나 비운다
PARTIES = {'none': (), 'scott': ('scott',), 'lawrence': ('lawrence',), 'both': ('scott', 'lawrence')}
# 맵마다 더 볼 것: 'statue' 여신상을 가진·안 가진 단계, 'dog' 개가 따라오는 단계
EXTRA = {'48/02': ('statue',), '48/04': ('statue',), '48/07': ('statue',), '40/0A': ('statue',),
         '3E/00': ('dog',), '48/00': ('dog',), '3F/01': ('dog',)}
# 필드: 레이크나바 왼쪽 도착 칸 둘 오른쪽에서 왼쪽으로 걸어 나가 필드에 선다
FIELD_SPOT = (pt.FIELD, '3E/00,4,26', 'left', 'left:90,wait:240')
# 「말 건 뒤」: (이름, 맵, 말 상대 FC 칸, 단계 이름, 밤인지, 일행, 더 볼 것). 말 상대 바로 아래 칸에서 위를 보고 말을 건다
PEOPLE = [
    ('king', '40/06', (0x0B, 0x0A), '허락', False, 'both', ()),                 # 엔돌 왕: 장사를 허락받은 뒤
    ('collector', '40/0A', (0x06, 0x03), '허락', False, 'both', ('statue',)),   # 수집가: 여신상을 가진 채
    ('ryan', '40/01', (0x13, 0x06), '가게', False, 'both', ()),                 # 닫힌 카지노의 라이안
]


def _cell(x, y):
    return 2 * x, 2 * y + 1


def flag_bytes(names):
    """{WRAM 하위 16비트: (값, 마스크)}: 3장 줄 조건의 flag 를 names 대로 켜고 나머지는 끈다."""
    out = {}
    for name, (i, mask) in c3.CONDITIONS.items():
        v, k = out.get(0x2190 + i, (0, 0))
        out[0x2190 + i] = (v | (mask if name in names else 0), k | mask)
    return out


def party_writes(data, members):
    """일행을 톨네코와 members(용병 이름) 로: 기록 1·2, 수·걷는 줄·차례."""
    out = []
    for k, who in enumerate(members, 1):
        rec = merc.record(data, who)
        at = (ch3.PARTY_ITEMS & 0xFFFF) - 0x16 + RECORD * k
        out += [f'{at + i:04X}={b:02X}' for i, b in enumerate(rec)]
    n = 1 + len(members)
    out += [f'{a:04X}={n:02X}' for a in (0x201D, 0x201E, 0x201F)]
    out += [f'{0x2020 + k:04X}={k:02X}' for k in range(1, n)] + [f'{0x2028 + k:04X}={k:02X}' for k in range(1, n)]
    return out


class Step:
    """「はなす」 한 번의 상태. names 는 flag 이름(진행 단계 + 동행), party 는 용병 이름들."""

    def __init__(self, name, names, night, party, days=(0, 0), statue=False):
        self.name, self.names, self.night, self.party = name, frozenset(names), night, tuple(party)
        self.days, self.statue = days, statue

    def flags(self):
        return self.names | {'SCOTT' if w == 'scott' else 'LAWRENCE' for w in self.party}

    def env(self, data, reset_talked=True):
        writes = [f'{a:04X}={v:02X}/{k:02X}' for a, (v, k) in sorted(flag_bytes(self.flags()).items())]
        t = NIGHT if self.night else DAY
        writes += [f'075E={t & 0xFF:02X}', f'075F={t >> 8:02X}', f'{0x2190 + pt.LAST[0]:04X}=00']
        if reset_talked:
            writes.append(f'{0x2190 + pt.TALKED_TO[0]:04X}=00')
        writes += party_writes(data, self.party)
        writes += [f'{ch3.SCOTT_DAYS & 0xFFFF:04X}={self.days[0]:02X}', f'{ch3.LAWRENCE_DAYS & 0xFFFF:04X}={self.days[1]:02X}']
        writes += [f'{ITEM_SLOT:04X}={c3.ITEMS["STATUE"] if self.statue else 0xFF:02X}',
                   f'{(pt.BAG & 0xFFFF) + c3.ITEMS["STATUE"]:04X}=00']
        return ','.join(writes)

    def expect(self, rows, talked=0, sets=None):
        """(메시지, 고른 줄 또는 None)."""
        values = {a: v for a, (v, _) in flag_bytes(self.flags()).items()}
        party = {c3.TORNEKO} | {c3.SPEAKERS['SCOTT' if w == 'scott' else 'LAWRENCE'] for w in self.party}
        var = {c3.VARS['SCOTT_DAYS']: self.days[0], c3.VARS['LAWRENCE_DAYS']: self.days[1]}
        items = {c3.ITEMS['STATUE']} if self.statue else set()
        return base.pick(rows, values, party, c3.TORNEKO, self.night, talked, sets, items, var)


def spot_steps(mp):
    """맵 mp 의 단계들."""
    if mp == pt.FIELD:
        return ([Step(f's{d}', c3.STAGES[-1][1], False, ('scott',), days=(d, 0)) for d in range(5)] +
                [Step(f'l{d}', c3.STAGES[-1][1], False, ('lawrence',), days=(0, d)) for d in range(5)] +
                [Step('none', c3.STAGES[-1][1], False, ())])
    out = [Step(f'{k:02d}{"n" if night else "d"}', names, night, ('scott', 'lawrence'))
           for k, (_, names) in enumerate(c3.STAGES) for night in (False, True)]
    last = c3.STAGES[-1][1]
    out += [Step(f'p_{p}', last, False, PARTIES[p]) for p in ('none', 'scott', 'lawrence')]
    if 'statue' in EXTRA.get(mp, ()):
        out += [Step(f'{k:02d}s', names, False, ('scott', 'lawrence'), statue=True)
                for k, (_, names) in enumerate(c3.STAGES)]
    if 'dog' in EXTRA.get(mp, ()):
        out += [Step(f'{k:02d}g', names | {'DOG'}, False, ('scott',) if k else (), statue=False)
                for k, (_, names) in enumerate(c3.STAGES[:3])]
    return out


def spots(dq5, dq4):
    """[(맵, 순간이동 TO, 보는 쪽, 더 걸을 입력)]: 줄이 있는 3장 맵마다 사람에게서 먼 걸을 수 있는 칸 가운데 바로 아래가
    벽인 칸에서 아래를 본다(아래가 걸을 수 있으면 방향 키에 한 걸음 내디뎌 출구로 나가기도 했다)."""
    import dq4block
    import dq4npccheck as nc
    import dq4npcport
    from dq4groupbuild import fc_map
    from kr_patch.fc import ines
    prg = ines.prg(Path(dq4).read_bytes())
    _lists, _messages, report = dq4npcport.port(str(dq5), str(dq4))
    maps = sorted({ln.map for ln in c3.LINES if ln.map != pt.FIELD})
    out = []
    for m in maps:
        g, n = (int(v, 16) for v in m.split('/'))
        source = dq4block.Map(prg, *fc_map(prg, g, n))
        people = [(p['x'], p['y']) for p in report.get(m, ())]
        best = None
        for y in range(1, source.h - 1):
            for x in range(1, source.w - 1):
                if not nc.walkable(source, x, y) or nc.walkable(source, x, y + 1):
                    continue
                far = min([max(abs(x - px), abs(y - py)) for px, py in people] or [99])
                if best is None or far > best[0]:
                    best = (far, x, y)
        if best is None or best[0] < 3:
            raise SystemExit(f'{m}: 사람에게서 세 칸 넘게 떨어진 걸을 수 있는 칸이 없음')
        _, x, y = best
        out.append((m, nc.warp_to(m, x, y, 1), 'down', ''))
    return out + [FIELD_SPOT]


def _talk_input():
    pages = max(parts.count(pt.ch1.PAGE) + 1 for parts in c3.MESSAGES.values())
    return ','.join(['a:8', 'wait:60', 'a:8', 'wait:200'] + ['b:8', 'wait:70'] * (pages + 2))


def _read(log):
    got, peek = {}, {}
    if log.exists():
        for line in log.read_text(encoding='utf-8').splitlines():
            if line.startswith('peek '):
                _, step, *pairs = line.split()
                peek[step] = {k: int(v, 16) for k, v in (p.split('=') for p in pairs)}
                continue
            name, _, ids = line.partition(' ')
            got[name] = [v for v in ids.split(',') if v]
    return got, peek


def run_spot(mesence, rom, data, start, out, spot, seed, shots=False):
    mp, to, face, pre = spot
    results = []
    if to[:5] in cw3.HOPS:
        hop = cw3.HOPS[to[:5]]
        r = wc.segment(mesence, rom, start, out / 'hop', ('hop', 'warp', hop, {'map': hop[:5], 'poke': HOLD}),
                       wc.NO_ENCOUNTERS, '', '', seed, flags=cw3.FLAGS)
        results.append(r)
        if r['status'] != 'passed':
            return results
        start = out / 'hop' / 'end.mss'
    r = wc.segment(mesence, rom, start, out / 'warp', ('warp', 'warp', to, {'map': to[:5], 'poke': HOLD}),
                   wc.NO_ENCOUNTERS, '', '', seed, flags=cw3.FLAGS)
    results.append(r)
    if r['status'] != 'passed':
        return results
    rows = base.table_of(data).get(pt._key(mp), [])
    plan = spot_steps(mp)
    env = {'STATE': str(out / 'warp' / 'end.mss'), 'PRE': ','.join(v for v in (f'{face}:8,wait:30', pre) if v),
           'TALK': _talk_input(), 'ROMPATCH': wc.NO_ENCOUNTERS, 'POKE': HOLD, **({'SHOTS': '1'} if shots else {}),
           'STEPS': ';'.join(f'{s.name}|{s.env(data)}' for s in plan)}
    dest = out / 'talk'
    why = wc.run(mesence, rom, LUA, dest, env, 1200)
    got, _ = _read(dest / 'talk.txt')
    problems = [str(why)] if why and not (dest / 'talk.txt').exists() else []
    shown = {}
    for s in plan:
        msg, row = s.expect(rows)
        want = f'{msg:03X}'
        if got.get(s.name) != [want]:
            problems.append(f'{s.name}: 메시지 {got.get(s.name)}, 기대 [{want}]')
        if not s.party and 'DOG' not in s.names and msg != pt.NOBODY:
            problems.append(f'{s.name}: 톨네코 혼자인데 동료 대사 {want} 를 고름(모형)')
        if row is not None:
            shown[s.name] = want
    results.append({'name': 'talk', 'status': 'failed' if problems else 'passed', 'problems': problems,
                    'shown': shown, 'steps': len(plan)})
    return results


def run_person(mesence, rom, data, start, out, case, seed):
    """말을 건 뒤 「はなす」 사례 하나. 결과 dict."""
    name, mp, fc, stage, night, party, extra = case
    step = Step('after', dict(c3.STAGES)[stage], night, PARTIES[party], statue='statue' in extra)
    t = NIGHT if night else DAY
    clock = f'7E075E={t & 0xFF:02X};7E075F={t >> 8:02X}'
    sets = ';'.join(f'{a:04X}={v:02X}' for a, (v, _k) in sorted(flag_bytes(step.flags()).items()))
    x, y = _cell(fc[0], fc[1] + 1)
    r = wc.segment(mesence, rom, start, out / 'warp',
                   ('warp', 'warp', f'{mp},{x},{y - 1}', {'map': mp, 'poke': HOLD + ';' + clock}),
                   wc.NO_ENCOUNTERS, sets, '', seed, flags=cw3.FLAGS)
    if r['status'] != 'passed':
        return {'name': name, 'status': 'failed', 'problems': [f"warp: {r.get('problems') or r['status']}"]}
    rows = base.table_of(data).get(pt._key(mp), [])
    ids, talk_sets = base.talk_sets(data)
    plan = [f'person|{step.env(data)}|{base.PERSON_TALK}', 'turn||down:8,wait:40',
            f'after|{step.env(data, reset_talked=False)}']
    env = {'STATE': str(out / 'warp' / 'end.mss'), 'PRE': 'up:8,wait:30', 'TALK': _talk_input(),
           'ROMPATCH': wc.NO_ENCOUNTERS, 'POKE': HOLD + ';' + clock, 'STEPS': ';'.join(plan)}
    dest = out / 'talk'
    why = wc.run(mesence, rom, LUA, dest, env, 900)
    got, peek = _read(dest / 'talk.txt')
    problems = [str(why)] if why and not (dest / 'talk.txt').exists() else []
    seen = peek.get('person', {})
    talk = seen.get('36E0', 0) | seen.get('3700', 0) << 8
    want_id = ids.index(talk) + 1 if talk in ids else 0
    if (seen.get('3020', 0) & 0x7F, seen.get('3080', 0) & 0x7F) != _cell(*fc):
        problems.append(f"말 상대 칸 {(seen.get('3020', 0) & 0x7F, seen.get('3080', 0) & 0x7F)}, 기대 {_cell(*fc)}")
    if not want_id or seen.get('21FD') != want_id:
        problems.append(f'대화 번호 {talk:03X} → 21FD {seen.get("21FD")}, 기대 {want_id}')
    msg, row = step.expect(rows, seen.get('21FD', 0), talk_sets)
    if got.get('after') != [f'{msg:03X}']:
        problems.append(f'after: 메시지 {got.get("after")}, 기대 [{msg:03X}]')
    if row is None or not any(c[0] == pt.TALKED for c in row[4]):
        problems.append('모형이 「말 건 뒤」 줄을 고르지 않음(사례가 그 줄을 재지 못함)')
    return {'name': name, 'status': 'failed' if problems else 'passed', 'problems': problems,
            'shown': got.get('after'), 'talk': f'{talk:03X}'}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', required=True, type=Path, help='dq4build.py --chapter3 의 롬')
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--jobs', type=int, default=4, help='함께 띄울 MesenCE 수')
    ap.add_argument('--base', type=Path, help='같은 롬으로 만든 3장 출발 상태. 주면 머리를 건너뜀')
    ap.add_argument('--only', help='이 맵만(쉼표로 여럿, 필드는 field)')
    ap.add_argument('--shots', action='store_true', help='단계마다 대사 첫 쪽 화면을 talk/<단계>.png 로 남김')
    ap.add_argument('--dq5', type=Path, default=HERE.parents[2] / 'rom' / 'dq5.sfc')
    ap.add_argument('--dq4', type=Path, default=HERE.parents[2] / 'rom' / 'dq4.nes')
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
    began = time.monotonic()
    places = spots(args.dq5, args.dq4)
    if args.only:
        wanted = set(args.only.split(','))
        unknown = wanted - {s[0] for s in places}
        if unknown:
            raise SystemExit(f'없는 맵: {", ".join(sorted(unknown))}')
        places = [s for s in places if s[0] in wanted]
    if args.base:
        start, head = args.base.resolve(), []
    else:
        cache = None if args.no_state_cache else wc.StateCache(data)
        start, head = cw3.head(mesence, rom, data, out, cache, repeat=2 if cache else 1)
    if start is None or any(r['status'] != 'passed' for r in head):
        print(json.dumps({'status': 'failed', 'head': head}, ensure_ascii=False))
        return 1
    cases = [c for c in PEOPLE if not args.only or c[1] in wanted]
    with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
        jobs = {(s, p[0]): pool.submit(run_spot, mesence, rom, data, start,
                                       wc.seed_dir(out, s, seeds) / p[0].replace('/', ''), p, s, args.shots)
                for s in seeds for p in places}
        people = {(s, c[0]): pool.submit(run_person, mesence, rom, data, start,
                                         wc.seed_dir(out, s, seeds) / 'people' / c[0], c, s)
                  for s in seeds for c in cases}
        results = {f'{s}:{n}': j.result() for (s, n), j in jobs.items()}
        person_results = {f'{s}:{n}': j.result() for (s, n), j in people.items()}
    failed = {k: [r for r in rs if r['status'] != 'passed'] for k, rs in results.items()
              if any(r['status'] != 'passed' for r in rs) or rs[-1].get('name') != 'talk'}
    failed.update({f'people {k}': [r] for k, r in person_results.items() if r['status'] != 'passed'})
    shown = sum(len(rs[-1].get('shown', {})) for rs in results.values() if rs[-1].get('name') == 'talk')
    talks = sum(rs[-1].get('steps', 0) for rs in results.values() if rs[-1].get('name') == 'talk')
    report = {'status': 'failed' if failed else 'passed', 'seconds': round(time.monotonic() - began),
              'spots': len(results), 'talks': talks, 'lines_shown': shown, 'people': len(person_results),
              'cases': results, 'people_cases': person_results}
    (out / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('status', 'seconds', 'spots', 'talks', 'lines_shown', 'people')}
                     | {'failed': failed}, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
