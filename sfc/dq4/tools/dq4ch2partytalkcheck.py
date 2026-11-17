"""2장 동료 대화(dq4ch2partytalk) 실행 검사(MesenCE 헤드리스).

2장 출발 상태(dq4ch2walkcheck.head)에서 동료 대화 줄이 있는 맵마다 한 번 순간이동해 말 상대가 없는 쪽을 보고 서고,
2장 진행 단계(dq4ch2partytalk.STAGES)마다 낮·밤으로 flag·시각을 WRAM 에 써 가며 명령 창 「はなす」를 고른다
(lua/dq4partytalk.lua). 단계마다 보행 메시지(24:8BAF)가 받은 번호가 하나이고, 롬의 동료 대화 표를 조건 평가 루틴과 같은
규칙으로 따라 고른 줄의 메시지(맞는 줄이 없으면 원래의 129)여야 한다. 단계마다 「마지막으로 고른 줄」과 「마지막으로 말을
건 인물」(pt.TALKED_TO)을 0 으로 두므로 같은 우선순위의 맞는 줄 가운데 표의 첫 줄이 나온다. 메시지가 없거나 둘 이상이면
멈췄거나 창이 닫히지 않은 것이다.

「말 건 뒤」 사례(people): 짝 표(dq4ch2partytalk-people.tsv)의 확인된 인물마다, 그 인물 옆 FC 칸에 순간이동해 말을 걸고
(대화 시작 훅이 pt.TALKED_TO 에 적음) 돌아서서 「はなす」를 고른다. 말 상대 슬롯의 칸이 짝 표의 칸이고, 그 값이 그 슬롯
대화 번호의 번호 표 차례 + 1 이고, 동료 대사가 그 값으로 고른 줄이어야 한다. 단계는 그 값으로 「말 건 인물」 줄이 뽑히는
첫 단계(그런 단계가 없으면 그 값만 봄). 맵은 사건 목록이 아닌 2장 시작 목록이 실리게 합류 flag 없이 들어간다.

  MESENCE=... LIBDIR=$(uv run krpatch sfc lua) \\
    uv run --locked python sfc/dq4/tools/dq4ch2partytalkcheck.py --rom work/ch2/dq4-ch1-full.sfc --out work/ch2talk
  --part k/n(기본 DQ4_GUARD_PART): 맵 자리·「말 건 뒤」 사례(시드마다)를 n 몫으로 나눠 k 번째만 돈다.
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
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4ch1walkcheck as wc  # noqa: E402
import dq4ch2event as ch2  # noqa: E402
import dq4ch2partytalk as pt  # noqa: E402
import dq4ch2walkcheck as cw  # noqa: E402
import dq4shards  # noqa: E402

LUA = HERE / 'lua' / 'dq4partytalk.lua'
DAY, NIGHT = ch2.MORNING, ch2.NIGHT
# 인물(물체 슬롯 08~1F)의 걸음 간격 7E:3300 + 슬롯 을 0 으로 묶어 제자리에 세운다. 걸어 다니는 인물이 앞에 서면 그
# 인물의 대사가 떠 시드마다 결과가 갈렸다(엔돌 카지노·성 1층)
HOLD = ';'.join(f'7E{0x3300 + s:04X}=00' for s in range(0x08, 0x20))

# (맵, 순간이동 TO, 보는 쪽, 맵에 선 뒤 더 걸을 입력). 순간이동은 TO 한 셀 아래에 내린다(dq4ch2walkcheck). 자리는
# 사건 검사가 쓰는 자리이거나 FC 계단 블록(dq4groupbuild.exit_order) 바로 아래 칸이다. 보는 쪽에는 인물이 없어야 한다
SPOTS = [
    ('3D/00', '3D/00,28,48', 'up', ''),
    ('3D/01', f'3D/01,{ch2.START_CELL[0]},{ch2.START_CELL[1] + 1}', 'down', ''),
    ('3D/02', '3D/02,34,21', 'down', ''),
    ('3D/03', f'3D/03,{ch2.CHIEF[0]},{ch2.CHIEF[1] + 1}', 'down', ''),
    ('3D/04', '3D/04,10,13', 'down', ''),
    ('3D/05', '3D/05,8,5', 'down', ''),
    ('40/00', '40/00,46,28', 'down', ''),
    ('40/01', '40/01,24,13', 'down', ''),
    ('40/02', '40/02,26,41', 'left', ''),
    ('40/05', '40/05,20,6', 'down', ''),
    ('40/06', '40/06,26,39', 'down', ''),
    ('40/07', '40/07,28,26', 'down', ''),
    ('40/0C', '40/0C,22,17', 'down', ''),
    ('40/0E', '40/0E,22,35', 'down', ''),
    ('45/00', '45/00,26,9', 'down', ''),
    ('45/02', '45/02,10,18', 'down', ''),
    ('45/05', '45/05,22,30', 'down', ''),
    ('45/06', '45/06,14,28', 'down', ''),
    ('45/07', '45/07,34,11', 'down', ''),
    ('45/08', '45/08,26,17', 'down', ''),
    ('45/09', '45/09,26,17', 'down', ''),
    ('45/0A', '45/0A,10,19', 'down', ''),
    ('45/0B', '45/0B,28,15', 'down', ''),
    ('45/0C', '45/0C,18,9', 'down', ''),
    ('45/0D', '45/0D,34,13', 'down', ''),
    ('45/0E', '45/0E,10,20', 'down', ''),
    ('45/0F', '45/0F,6,7', 'down', ''),
    # 필드: 사란 남쪽 출구 위에서 아래로 걸어 나가 필드에 선 뒤 말을 건다
    (pt.FIELD, '45/00,24,50', 'down', 'down:90,wait:240'),
]


def _talk_input():
    """명령 창 → 「はなす」 뒤 B 로만 넘긴다(A 를 더 누르면 명령 창이 다시 열림). 가장 긴 메시지의 쪽 수 + 2 번."""
    pages = max(parts.count(pt.ch1.PAGE) + 1 for parts in pt.MESSAGES.values())
    return ','.join(['a:8', 'wait:60', 'a:8', 'wait:200'] + ['b:8', 'wait:70'] * (pages + 2))


def stage_bytes(flags):
    """{WRAM 주소: (값, 마스크)}: 동료 대화 조건의 flag 를 flags(이름 집합) 대로 켜고 나머지는 끈다."""
    out = {}
    for name, (i, mask) in pt.CONDITIONS.items():
        v, k = out.get(0x2190 + i, (0, 0))
        out[0x2190 + i] = (v | (mask if name in flags else 0), k | mask)
    return out


def steps():
    """[(이름, flag 이름 집합, 밤인지)]: 진행 단계마다 낮·밤."""
    return [(f'{k:02d}{"n" if night else "d"}', flags, night)
            for k, (_, flags) in enumerate(pt.STAGES) for night in (False, True)]


def expected(rows, flags, night, talked=0, sets=None):
    """롬 표 한 맵의 줄(pt.table 꼴)에서 조건 평가 루틴이 고를 메시지(없으면 129). 일행은 셋 다 살아 있고 선두는 아리나다.
    「마지막으로 고른 줄」이 0 이므로 가장 작은 우선순위의 맞는 줄 가운데 첫 줄이다. talked 는 pt.TALKED_TO 의 값, sets 는
    {번호 묶음 주소: [차례 + 1]}(TALKED 조건)."""
    return expected_row(rows, flags, night, talked, sets)[0]


def expected_row(rows, flags, night, talked=0, sets=None):
    """(메시지, 고른 줄 또는 None)."""
    values = {a: v for a, (v, _) in stage_bytes(flags).items()}
    return pick(rows, values, {pt.ALENA, pt.KIRYL, pt.BREY}, pt.ALENA, night, talked, sets)


def pick(rows, values, party, lead, night, talked=0, sets=None, items=(), var=None):
    """장에 매이지 않은 조건 평가 루틴의 모형: (메시지, 고른 줄 또는 None). values 는 {WRAM 하위 16비트: 바이트}(flag
    자리), party 는 걷는 줄의 살아 있는 인물 번호, items 는 일행이 가진 물건 번호, var 는 {3장 변수 칸 오프셋: 값}."""
    def holds(kind, a, b):
        byte = values.get(0x2190 + a, 0)
        return {pt.ON: lambda: byte & b != 0, pt.OFF: lambda: byte & b == 0, pt.EQUAL: lambda: byte == b,
                pt.LEAD: lambda: a == lead, pt.WITH: lambda: a in party, pt.WITHOUT: lambda: a not in party,
                pt.TALKED: lambda: talked != 0 and talked in (sets or {}).get(a | b << 8, ()),
                pt.HAVE: lambda: a in items, pt.LACK: lambda: a not in items,
                pt.VAR: lambda: (var or {}).get(a, 0) == b}[kind]()
    for row in rows:
        prio, speaker, when, msg, conds = row
        if speaker in party and when in (0, 2 if night else 1) and all(holds(*c) for c in conds):
            return msg, row
    return pt.NOBODY, None


def step_env(flags, night, reset_talked=True):
    writes = [f'{a:04X}={v:02X}/{k:02X}' for a, (v, k) in sorted(stage_bytes(flags).items())]
    t = NIGHT if night else DAY
    writes += [f'075E={t & 0xFF:02X}', f'075F={t >> 8:02X}', f'{0x2190 + pt.LAST[0]:04X}=00']
    if reset_talked:
        writes.append(f'{0x2190 + pt.TALKED_TO[0]:04X}=00')
    return ','.join(writes)


def table_of(data):
    ctx = next(c for c in ch2.contexts() if c.module is pt)
    return pt.table(data, ctx.at['maps'])


def talk_sets(data):
    """(번호 표 [대화 번호], {번호 묶음 주소: [차례 + 1]}): 롬의 동료 대화 표에서."""
    at = next(c for c in ch2.contexts() if c.module is pt).at
    sets = {c[1] | c[2] << 8: pt.talk_set(data, at['maps'], c[1] | c[2] << 8)
            for rows in pt.table(data, at['maps']).values() for row in rows for c in row[4] if c[0] == pt.TALKED}
    return pt.talk_ids(data, at), sets


def run_spot(mesence, rom, data, base, out, spot, seed, shots=False):
    mp, to, face, pre = spot
    sets = [f'{0x2190 + ch2.JOINED[0]:04X}|{ch2.JOINED[1]:02X}', cw.join_set(data)]
    state, extra, results = base, ';'.join(sets), []
    if to.split(',')[0] == ch2.THRONE:
        hop = cw.HOPS[ch2.THRONE]
        r = wc.segment(mesence, rom, state, out / 'hop', ('hop', 'warp', hop, {'map': hop[:5], 'poke': HOLD}),
                       wc.NO_ENCOUNTERS,
                       extra, '', seed, flags=cw.FLAGS)
        results.append(r)
        if r['status'] != 'passed':
            return results
        state, extra = out / 'hop' / 'end.mss', ''
    r = wc.segment(mesence, rom, state, out / 'warp', ('warp', 'warp', to, {'map': to[:5], 'poke': HOLD}),
                   wc.NO_ENCOUNTERS,
                   extra, '', seed, flags=cw.FLAGS)
    results.append(r)
    if r['status'] != 'passed':
        return results
    rows = table_of(data).get(pt._key(mp), [])
    plan = steps()
    env = {'STATE': str(out / 'warp' / 'end.mss'), 'PRE': ','.join(v for v in (f'{face}:8,wait:30', pre) if v),
           'TALK': _talk_input(), 'ROMPATCH': wc.NO_ENCOUNTERS, 'POKE': HOLD,
           **({'SHOTS': '1'} if shots else {}),
           'STEPS': ';'.join(f'{name}|{step_env(flags, night)}' for name, flags, night in plan)}
    dest = out / 'talk'
    why = wc.run(mesence, rom, LUA, dest, env, 900)
    log = dest / 'talk.txt'
    got = {}
    if log.exists():
        for line in log.read_text(encoding='utf-8').splitlines():
            name, _, ids = line.partition(' ')
            got[name] = [v for v in ids.split(',') if v]
    problems = [str(why)] if why and not log.exists() else []
    for name, flags, night in plan:
        want = f'{expected(rows, flags, night):03X}'
        if got.get(name) != [want]:
            problems.append(f'{name}: 메시지 {got.get(name)}, 기대 [{want}]')
    results.append({'name': 'talk', 'status': 'failed' if problems else 'passed', 'problems': problems,
                    'shown': {k: v for k, v in got.items() if k[:2].isdigit()}})
    return results


AWAY = {'up': (0, -1), 'down': (0, 1), 'left': (-1, 0), 'right': (1, 0)}
PERSON_TALK = ','.join(['a:8', 'wait:60', 'a:8', 'wait:200'] + ['b:8', 'wait:70'] * 8)


def token_ids(data):
    """{「NDS 맵:인물 번호」: {차례 + 1}}: 롬의 번호 묶음을 줄 표의 talked 묶음과 짝지어(묶음은 talked 묶음의 정렬 차례로
    놓임) 사람 하나짜리 묶음에서 읽는다. 짝이 맞지 않으면(빈 묶음이 빠짐) 사람이 든 모든 묶음의 합."""
    _ids, sets = talk_sets(data)
    groups = sorted({ln.talked for ln in pt.all_lines() if ln.talked})
    addrs = sorted(sets)
    out = {}
    if len(addrs) == len(groups):
        for g, a in zip(groups, addrs):
            if len(g) == 1:
                out.setdefault(g[0], set()).update(sets[a])
        for g, a in zip(groups, addrs):
            for t in g:
                if t not in out:
                    out[t] = set(sets[a])
    return out


def people_cases(dq5, dq4):
    """([사례], [(토큰, 행, 빠진 까닭)]). 사례: {'token', 'map', 'cell', 'night', 'to', 'face', 'away'}."""
    import dq4block
    import dq4npccheck as nc
    import dq4npcport
    from dq4groupbuild import fc_map
    from kr_patch.fc import ines
    prg = ines.prg(Path(dq4).read_bytes())
    _lists, _messages, report = dq4npcport.port(str(dq5), str(dq4))
    cases, skipped = [], []
    used = {k for ln in pt.LINES for k in ln.talked}
    for (mp, who), rows in sorted(pt.PEOPLE.items()):
        token = f'{mp}:{who}'
        if token not in used:
            continue                    # 줄에 쓰이지 않은 인물은 번호 표에 없다
        for r in rows:
            if r['status'] != pt.SURE:
                continue
            m, night = r['map'], r['time'] == 'night'
            g, n = (int(v, 16) for v in m.split('/'))
            source = dq4block.Map(prg, *fc_map(prg, g, n))
            occupied = {(p['x'], p['y']) for p in report[m] if p['night'] == night}
            fx, fy = nc.talk_cell({'dq5': {'x': r['cell'][0], 'y': r['cell'][1]}})
            side = nc.talk_side(source, fx, fy, occupied)
            if side is None:
                skipped.append((token, r, '말을 걸 빈 칸이 없음'))
                continue
            sx, sy, face = side
            # 돌아설 쪽: 앞 세 칸에 인물이 없는 쪽. 막힌 쪽이면 제자리에서 돌기만 한다
            ways = [k for k, (dx, dy) in AWAY.items() if k != face
                    and not any((sx + dx * i, sy + dy * i) in occupied for i in (1, 2, 3))]
            if not ways:
                skipped.append((token, r, '돌아설 쪽에 인물이 있음'))
                continue
            away = min(ways, key=lambda k: nc.walkable(source, sx + AWAY[k][0], sy + AWAY[k][1]))
            cases.append({'token': token, 'map': m, 'cell': r['cell'], 'night': night,
                          'to': nc.warp_to(m, sx, sy, 1), 'face': face, 'away': away})
    return cases, skipped


def case_name(case):
    return f"{case['token']} {case['map']} {case['cell'][0]},{case['cell'][1]} {'night' if case['night'] else 'day'}"


def person_stages(data, case):
    """(줄, 번호 표, 번호 묶음, 이 인물의 번호, [(단계, flag)]): 단계는 이 인물의 번호로 「말 건 인물」 줄이 뽑히는 단계."""
    night = case['night']
    rows = table_of(data).get(pt._key(case['map']), [])
    ids, sets = talk_sets(data)
    mine = token_ids(data).get(case['token'], set())
    stages = [(k, flags) for k, (_, flags) in enumerate(pt.STAGES)
              if any(expected_row(rows, flags, night, i, sets)[1] is not None and
                     any(c[0] == pt.TALKED for c in expected_row(rows, flags, night, i, sets)[1][4]) for i in mine)]
    return rows, ids, sets, mine, stages


def run_person(mesence, rom, data, base, out, case, seed):
    """말을 건 뒤 「はなす」 사례 하나. 결과 dict."""
    mp, night = case['map'], case['night']
    t = NIGHT if night else DAY
    clock = f'7E075E={t & 0xFF:02X};7E075F={t >> 8:02X}'
    name = case_name(case)
    state, extra = base, cw.join_set(data)
    if mp == ch2.THRONE:
        # 2장 출발 상태가 왕좌의 방이라 같은 맵 순간이동은 도착을 알아채지 못한다. 한 번 다른 맵을 거친다(run_spot 과 같음)
        hop = cw.HOPS[ch2.THRONE]
        r = wc.segment(mesence, rom, state, out / 'hop', ('hop', 'warp', hop, {'map': hop[:5], 'poke': HOLD}),
                       wc.NO_ENCOUNTERS, extra, '', seed, flags=cw.FLAGS)
        if r['status'] != 'passed':
            return {'name': name, 'status': 'failed', 'problems': [f"hop: {r.get('problems') or r['status']}"]}
        state, extra = out / 'hop' / 'end.mss', ''
    r = wc.segment(mesence, rom, state, out / 'warp', ('warp', 'warp', case['to'], {'map': mp, 'poke': HOLD + ';' + clock}),
                   wc.NO_ENCOUNTERS, extra, '', seed, flags=cw.FLAGS)
    if r['status'] != 'passed':
        return {'name': name, 'status': 'failed', 'problems': [f"warp: {r.get('problems') or r['status']}"]}
    wram = (out / 'warp' / 'final.wram').read_bytes()
    if not any((wram[0x3020 + s] & 0x7F, wram[0x3080 + s] & 0x7F) == tuple(case['cell']) and wram[0x3220 + s]
               for s in range(0x08, 0x20)):
        # 짝 표는 FC 시작 상태의 인물이다. 사건 모듈이 2장 시작 목록에서 뺀 인물(프레놀 3D/04 (40,27) 등)은 없다
        return {'name': name, 'status': 'passed', 'absent': True, 'problems': []}
    rows, ids, sets, mine, stages = person_stages(data, case)
    reset = f'{0x2190 + pt.TALKED_TO[0]:04X}=00,{0x2190 + pt.LAST[0]:04X}=00'
    plan = [f'person|{reset}|{PERSON_TALK}', f"turn||{case['away']}:8,wait:40"]
    plan += [f'{k:02d}|{step_env(flags, night, reset_talked=False)}' for k, flags in stages]
    env = {'STATE': str(out / 'warp' / 'end.mss'), 'PRE': f"{case['face']}:8,wait:30", 'TALK': _talk_input(),
           'ROMPATCH': wc.NO_ENCOUNTERS, 'POKE': HOLD + ';' + clock, 'STEPS': ';'.join(plan)}
    dest = out / 'talk'
    why = wc.run(mesence, rom, LUA, dest, env, 900)
    log = dest / 'talk.txt'
    got, peek = {}, {}
    if log.exists():
        for line in log.read_text(encoding='utf-8').splitlines():
            if line.startswith('peek '):
                _, step, *pairs = line.split()
                peek[step] = {k: int(v, 16) for k, v in (p.split('=') for p in pairs)}
                continue
            step, _, shown = line.partition(' ')
            got[step] = [v for v in shown.split(',') if v]
    problems = [str(why)] if why and not log.exists() else []
    seen = peek.get('person', {})
    slot_cell = (seen.get('3020', 0) & 0x7F, seen.get('3080', 0) & 0x7F)
    talk = seen.get('36E0', 0) | seen.get('3700', 0) << 8
    want_id = ids.index(talk) + 1 if talk in ids else 0
    if slot_cell != tuple(case['cell']):
        problems.append(f'말 상대 칸 {slot_cell}, 짝 표 {tuple(case["cell"])}')
    if not want_id or seen.get('21FD') != want_id:
        problems.append(f'대화 번호 {talk:03X} → 21FD {seen.get("21FD")}, 기대 {want_id}')
    elif want_id not in mine:
        problems.append(f'21FD {want_id} 가 {case["token"]} 의 번호 묶음 {sorted(mine)} 에 없음')
    picked = 0
    for k, flags in stages:
        msg, row = expected_row(rows, flags, night, seen.get('21FD', 0), sets)
        if got.get(f'{k:02d}') != [f'{msg:03X}']:
            problems.append(f'{k:02d}: 메시지 {got.get(f"{k:02d}")}, 기대 [{msg:03X}]')
        picked += row is not None and any(c[0] == pt.TALKED for c in row[4])
    return {'name': name, 'status': 'failed' if problems else 'passed', 'problems': problems,
            'talked_lines': picked, 'stages': len(stages)}


def work_units(spots, cases, seeds):
    """몫으로 나누는 단위 [(종류 'spot'·'people', 시드, 차례, 자리 또는 사례)]. 단위마다 2장 출발 상태에서 따로
    순간이동해 돌아 서로 상태를 주고받지 않는다. 차례는 나누기 전 목록의 차례라, 몫으로 돌아도 결과 키·폴더가 나누지
    않고 돈 것과 같다."""
    return ([('spot', s, k, p) for s in seeds for k, p in enumerate(spots)] +
            [('people', s, k, c) for s in seeds for k, c in enumerate(cases)])


def unit_key(u):
    kind, seed, _k, item = u
    return f"{seed}:{kind}:{item[0] if kind == 'spot' else case_name(item)}"


def part_units(units, part, data=None):
    """part(k, n) 몫의 단위. 무게는 MesenCE 실행 수(순간이동·대화 둘) + 「はなす」 수: 맵 자리는 단계 수, 사례는 말 걸기·
    돌아서기 + 고른 단계 수(data 가 없으면 단계를 모두 센 어림)."""
    def weight(u):
        kind, _s, _k, item = u
        if kind == 'spot':
            return 2 + len(steps())
        return 4 + (len(person_stages(data, item)[4]) if data is not None else len(pt.STAGES))
    return dq4shards.part_of(units, part, key=unit_key, weight=weight)


def summarize(results, person_results, skipped, part=None):
    """(보고, 실패): 돈 단위의 결과만으로 센다. 몫으로 돌면 맵 자리·대화·사례 수는 그 몫의 것이다. 「말 건 뒤」 사례에서
    빠진 것(skipped)은 에뮬레이터 없이 짝 표에서 정해지는 목록이라 몫과 상관없이 모두 적는다."""
    failed = {k: [r for r in rs if r['status'] != 'passed'] for k, rs in results.items()
              if any(r['status'] != 'passed' for r in rs) or rs[-1].get('name') != 'talk'}
    failed.update({f'people {k}': [r] for k, r in person_results.items() if r['status'] != 'passed'})
    shown = sum(1 for rs in results.values() if rs[-1].get('name') == 'talk'
                for ids in rs[-1]['shown'].values() if ids and ids != [f'{pt.NOBODY:03X}'])
    report = {'status': 'failed' if failed else 'passed', 'part': part,
              'spots': len(results), 'talks': len(results) * len(steps()), 'lines_shown': shown,
              'people': len(person_results),
              'people_talked_lines': sum(1 for r in person_results.values() if r.get('talked_lines')),
              'people_absent': sorted(r['name'] for r in person_results.values() if r.get('absent')),
              'people_skipped': [f'{t} {r["map"]} {r["cell"]} {r["time"]}: {why}' for t, r, why in skipped],
              'cases': results, 'people_cases': person_results}
    return report, failed


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', required=True, type=Path, help='dq4build.py --chapter2 의 롬')
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--jobs', type=int, default=4, help='함께 띄울 MesenCE 수')
    ap.add_argument('--base', type=Path, help='같은 롬으로 만든 2장 출발 상태. 주면 머리를 건너뜀')
    ap.add_argument('--only', help='이 맵만(쉼표로 여럿, 필드는 field)')
    ap.add_argument('--shots', action='store_true', help='단계마다 대사 첫 쪽 화면을 talk/<단계>.png 로 남김')
    ap.add_argument('--no-people', action='store_true', help='「말 건 뒤」 사례를 건너뜀')
    ap.add_argument('--dq5', type=Path, default=HERE.parents[2] / 'rom' / 'dq5.sfc')
    ap.add_argument('--dq4', type=Path, default=HERE.parents[2] / 'rom' / 'dq4.nes')
    wc.add_seed_args(ap)
    dq4shards.add_part_arg(ap)
    args = ap.parse_args()
    seeds = wc.seeds_of(args)
    part = f'{args.part[0]}/{args.part[1]}' if args.part else None
    mesence = Path(os.environ['MESENCE'])
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f'{out} is not empty')
    out.mkdir(parents=True, exist_ok=True)
    rom = out / 'c.sfc'
    shutil.copyfile(args.rom.resolve(), rom)
    data = rom.read_bytes()
    began = time.monotonic()
    spots = SPOTS
    if args.only:
        wanted = set(args.only.split(','))
        unknown = wanted - {s[0] for s in SPOTS}
        if unknown:
            raise SystemExit(f'없는 맵: {", ".join(sorted(unknown))}')
        spots = [s for s in SPOTS if s[0] in wanted]
    cases, skipped = ([], []) if args.no_people else people_cases(args.dq5, args.dq4)
    if args.only:
        cases = [c for c in cases if c['map'] in wanted]
    mine = part_units(work_units(spots, cases, seeds), args.part, data)
    if args.base:
        base, head = args.base.resolve(), []
    else:
        cache = None if args.no_state_cache else wc.StateCache(data)
        base, head = cw.head(mesence, rom, data, out, cache)
    if base is None or any(r['status'] != 'passed' for r in head):
        print(json.dumps({'status': 'failed', 'part': part, 'head': head}, ensure_ascii=False))
        return 1
    with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
        jobs = {(s, p[0]): pool.submit(run_spot, mesence, rom, data, base,
                                       wc.seed_dir(out, s, seeds) / p[0].replace('/', ''), p, s, args.shots)
                for kind, s, _k, p in mine if kind == 'spot'}
        people = {(s, k): pool.submit(run_person, mesence, rom, data, base,
                                      wc.seed_dir(out, s, seeds) / 'people' / f'{k:03d}', c, s)
                  for kind, s, k, c in mine if kind == 'people'}
        results = {f'{s}:{n}': j.result() for (s, n), j in jobs.items()}
        person_results = {f'{s}:{k:03d}': j.result() for (s, k), j in people.items()}
    report, failed = summarize(results, person_results, skipped, part)
    report['seconds'] = round(time.monotonic() - began)
    (out / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('status', 'part', 'seconds', 'spots', 'talks', 'lines_shown', 'people',
                                             'people_talked_lines', 'people_absent', 'people_skipped')}
                     | {'failed': failed},
                     ensure_ascii=False))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
