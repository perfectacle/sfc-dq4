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
  말 건 뒤  PEOPLE 의 사람 옆(대개 바로 아래)에 순간이동해 그쪽을 보고 말을 걸고(대화 시작 훅이 「말 건 사람」 값 pt.TALKED_TO 에 적음) 돌아서서
         「はなす」 를 고른다. 말 상대 칸이 그 사람이고, 그 값이 그 대화 번호의 번호 표 차례 + 1 이고, 동료 대사가 그 값으로
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
# 「말 건 뒤」: (이름, 맵, 말 상대 FC 칸, 선 쪽, 단계 이름, 더 켤 flag, 밤인지, 말 걸 때 일행, 「はなす」 때 일행, 더 볼 것).
# 선 쪽 'below' 는 말 상대 바로 아래에서 위를, 'left' 는 왼쪽에서 오른쪽을 보고 말을 건다. 말을 걸면 묻는 사람(용병·
# 가게 주인·노인·네네)은 B 로 「아니오」 를 고른다. 용병은 고용하지 않은 채 말을 걸고 「はなす」 때 일행에 넣는다
# (NDS 는 고용 대사 뒤의 최근 이벤트 값)
PEOPLE = [
    ('king', '40/06', (0x0B, 0x0A), 'below', '허락', (), False, 'both', 'both', ()),      # 엔돌 왕: 장사를 허락받은 뒤
    ('collector', '40/0A', (0x06, 0x03), 'below', '허락', (), False, 'both', 'both', ('statue',)),   # 여신상을 가진 채
    ('ryan', '40/01', (0x13, 0x06), 'below', '가게', (), False, 'both', 'both', ()),      # 닫힌 카지노의 라이안
    ('deliver', '40/02', (0x11, 0x12), 'below', '납품', (), False, 'both', 'both', ()),   # 병사장: 납품을 다 채운 뒤
    ('pizarro_gone', '40/02', (0x12, 0x19), 'below', '여우', (), False, 'both', 'both', ()),
    ('maid', '40/05', (0x05, 0x02), 'below', '여우', (), True, 'both', 'both', ()),      # 성 지하 하녀(밤)
    ('pizarro_fan', '40/05', (0x02, 0x02), 'below', '여우', (), True, 'both', 'both', ()),
    ('warrior', '40/0B', (0x0B, 0x03), 'below', '여우', (), True, 'both', 'both', ()),   # 여관 2층 전사(밤)
    ('seller', '40/08', (0x03, 0x03), 'below', '허락', (), False, 'both', 'both', ()),   # 가게를 사기 전 가게 주인
    ('nene_shop', '40/00', (0x06, 0x1C), 'left', '가게', (), False, 'both', 'both', ()),  # 가게를 산 뒤 네네
    # 용병: 'hire' 는 금화를 쥐여 「예」 로 고용한 직후(일행·flag 는 게임이 만든 그대로) 고용 대사 줄이 나와야 하고,
    # 'refuse' 는 「방금 고용함」 을 미리 켜 두고 「아니오」 한 뒤 그 용병을 일행에 넣어도 고용 대사 줄이 아니어야 한다
    # (대화 시작 훅이 그 flag 를 끔)
    ('scott_hire', '40/00', (0x05, 0x13), 'below', '여우', (), False, 'none', 'scott', ('hire',)),
    ('scott_refuse', '40/00', (0x05, 0x13), 'below', '여우', (), False, 'none', 'scott', ('refuse',)),
    ('lawrence_hire', '40/0B', (0x07, 0x08), 'below', '여우', (), False, 'none', 'lawrence', ('hire',)),
    ('lawrence_refuse', '40/0B', (0x07, 0x08), 'below', '여우', (), False, 'none', 'lawrence', ('refuse',)),
    ('bonmalmo_king', '3F/01', (0x11, 0x07), 'below', '여우', (), False, 'both', 'both', ()),
    # 왕자 방의 유모: 제자리 (06,06). 둘째 유모 (06,07)은 FC 가 싣지 않는 사람이라 목록에 없고(dq4ch3bonmalmo
    # .SECOND_NANNY), 왕자가 처음 말을 마치기(NANNY_GO) 전에는 걷지 않는다
    ('nanny', '3F/01', (0x06, 0x06), 'below', '여우', (), False, 'both', 'both', ()),
    ('scholar', '3F/01', (0x06, 0x1C), 'below', '톰 아들', ('DOG',), False, 'none', 'none', ()),   # 개 토마스
    ('nun', '3E/00', (0x0D, 0x07), 'below', '톰 아들', ('DOG',), False, 'none', 'none', ()),       # 개 토마스
    ('tom_son', '3E/00', (0x17, 0x03), 'below', '톰 아들', ('DOG',), False, 'none', 'none', ()),   # 개 토마스
    ('nene_home', '3E/01', (0x1B, 0x04), 'below', '여우', (), False, 'both', 'both', ()),
    ('old_man', '47/00', (0x12, 0x0A), 'below', '가게', (), False, 'both', 'both', ()),  # 굴 노인: 공사비 내기 전
]
# 고용: 명령 창 → 「はなす」, 묻는 말(두 쪽, dq4mercenary *_offer)의 첫 쪽을 B 로 넘기고 물음에 A 로 「예」, 고용 말은
# B 로 넘긴다. 고용 뒤 A 를 더 누르면 명령 창 → 「はなす」 로 숨기 전의 용병에게 다시 말을 걸어 「방금 고용함」 이 꺼졌다(실측)
HIRE_TALK = ','.join(['a:8', 'wait:60', 'a:8', 'wait:200', 'b:8', 'wait:120', 'a:8', 'wait:200'] + ['b:8', 'wait:70'] * 6)
SIDES = {'below': ((0, 1), 'up', 'down'), 'left': ((-1, 0), 'right', 'left')}


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

    def __init__(self, name, names, night, party, days=(0, 0), statue=False, gold=None, game=False, keep=()):
        self.name, self.names, self.night, self.party = name, frozenset(names), night, tuple(party)
        self.days, self.statue, self.gold = days, statue, gold
        # game: 게임이 만든 일행·flag 를 그대로 두고 시각·마지막 줄만 쓴다. keep: 쓰지 않는(게임이 정하는) flag 이름
        self.game, self.keep = game, frozenset(keep)

    def flags(self):
        return self.names | {'SCOTT' if w == 'scott' else 'LAWRENCE' for w in self.party}

    def env(self, data, reset_talked=True):
        t = NIGHT if self.night else DAY
        clock = [f'075E={t & 0xFF:02X}', f'075F={t >> 8:02X}', f'{0x2190 + pt.LAST[0]:04X}=00']
        if self.game:
            return ','.join(clock)
        kept = {0x2190 + i: m for n, (i, m) in c3.CONDITIONS.items() if n in self.keep}
        writes = [f'{a:04X}={v:02X}/{k & ~kept.get(a, 0) & 0xFF:02X}' for a, (v, k) in sorted(flag_bytes(self.flags()).items())]
        writes += clock
        if reset_talked:
            writes.append(f'{0x2190 + pt.TALKED_TO[0]:04X}=00')
        writes += party_writes(data, self.party)
        if self.gold is not None:
            writes += [f'{(ch3.GOLD_AT & 0xFFFF) + k:04X}={self.gold >> 8 * k & 0xFF:02X}' for k in range(3)]
        writes += [f'{ch3.SCOTT_DAYS & 0xFFFF:04X}={self.days[0]:02X}', f'{ch3.LAWRENCE_DAYS & 0xFFFF:04X}={self.days[1]:02X}']
        writes += [f'{ITEM_SLOT:04X}={c3.ITEMS["STATUE"] if self.statue else 0xFF:02X}',
                   f'{(pt.BAG & 0xFFFF) + c3.ITEMS["STATUE"]:04X}=00']
        return ','.join(writes)

    def expect(self, table, key, talked=0, sets=None):
        """(메시지, 고른 줄 또는 None): 맵 key 의 줄에서, 맞는 줄이 없으면 맵 무관 줄(pt.ANY_KEY)에서."""
        values = {a: v for a, (v, _) in flag_bytes(self.flags()).items()}
        party = {c3.TORNEKO} | {c3.SPEAKERS['SCOTT' if w == 'scott' else 'LAWRENCE'] for w in self.party}
        var = {c3.VARS['SCOTT_DAYS']: self.days[0], c3.VARS['LAWRENCE_DAYS']: self.days[1]}
        items = {c3.ITEMS['STATUE']} if self.statue else set()
        for k in (key, pt.ANY_KEY):
            got = base.pick(table.get(k, []), values, party, c3.TORNEKO, self.night, talked, sets, items, var)
            if got[1] is not None:
                return got
        return got


def spot_steps(mp):
    """맵 mp 의 단계들."""
    if mp == pt.FIELD:
        return ([Step(f's{d}', c3.STAGES[-1][1], False, ('scott',), days=(d, 0)) for d in range(5)] +
                [Step(f'l{d}', c3.STAGES[-1][1], False, ('lawrence',), days=(0, d)) for d in range(5)] +
                [Step('none', c3.STAGES[-1][1], False, ()),
                 Step('dog', c3.STAGES[0][1] | {'DOG'}, False, ()),
                 Step('dog_away', c3.STAGES[0][1] | {'DOG', 'DOG_AWAY'}, False, ())])
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
    maps = sorted({ln.map for ln in c3.LINES if ln.map not in (pt.FIELD, pt.ANY)})
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
    table = base.table_of(data)
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
        msg, row = s.expect(table, pt._key(mp))
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
    name, mp, fc, side, stage, more, night, person_party, party, extra = case
    names = dict(c3.STAGES)[stage] | set(more)
    hire, refuse = 'hire' in extra, 'refuse' in extra
    price = merc.PRICES[party] if hire else None
    step = Step('after', names | ({'HIRED_NOW'} if hire else set()), night, PARTIES[party], statue='statue' in extra,
                game=hire, keep=('HIRED_NOW',) if refuse else ())
    meet = Step('person', names | ({'HIRED_NOW'} if refuse else set()), night, PARTIES[person_party],
                statue='statue' in extra, gold=price)
    t = NIGHT if night else DAY
    clock = f'7E075E={t & 0xFF:02X};7E075F={t >> 8:02X}'
    sets = ';'.join(f'{a:04X}={v:02X}' for a, (v, _k) in sorted(flag_bytes(meet.flags()).items()))
    (dx, dy), face, away = SIDES[side]
    x, y = _cell(fc[0] + dx, fc[1] + dy)
    results = {'name': name, 'status': 'failed'}
    if mp in cw3.HOPS:
        hop = cw3.HOPS[mp]
        r = wc.segment(mesence, rom, start, out / 'hop', ('hop', 'warp', hop, {'map': hop[:5], 'poke': HOLD}),
                       wc.NO_ENCOUNTERS, '', '', seed, flags=cw3.FLAGS)
        if r['status'] != 'passed':
            return {**results, 'problems': [f"hop: {r.get('problems') or r['status']}"]}
        start = out / 'hop' / 'end.mss'
    r = wc.segment(mesence, rom, start, out / 'warp',
                   ('warp', 'warp', f'{mp},{x},{y - 1}', {'map': mp, 'poke': HOLD + ';' + clock}),
                   wc.NO_ENCOUNTERS, sets, '', seed, flags=cw3.FLAGS)
    if r['status'] != 'passed':
        return {**results, 'problems': [f"warp: {r.get('problems') or r['status']}"]}
    table = base.table_of(data)
    ids, talk_sets = base.talk_sets(data)
    plan = [f'person|{meet.env(data)}|{HIRE_TALK if hire else base.PERSON_TALK}', f'turn||{away}:8,wait:40',
            f'after|{step.env(data, reset_talked=False)}']
    env = {'STATE': str(out / 'warp' / 'end.mss'), 'PRE': f'{face}:8,wait:30', 'TALK': _talk_input(),
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
    talked = peek.get('turn', seen).get('21FD', 0)
    if not want_id or talked != want_id:
        problems.append(f'대화 번호 {talk:03X} → 말 건 사람 값 {talked}, 기대 {want_id}')
    msg, row = step.expect(table, pt._key(mp), talked, talk_sets)
    if got.get('after') != [f'{msg:03X}']:
        problems.append(f'after: 메시지 {got.get("after")}, 기대 [{msg:03X}]')
    hired_now = 0x2190 + ch3.HIRED_NOW[0]
    if (hire or refuse) and bool(seen.get(f'{hired_now:04X}', 0) & ch3.HIRED_NOW[1]) != hire:
        problems.append(f"말을 마친 뒤 방금 고용함 flag {'꺼짐' if hire else '켜짐'}")
    if refuse:
        if row is not None and any(c[0] == pt.TALKED for c in row[4]):
            problems.append('「아니오」 뒤에 고용 대사 줄(말 건 뒤 줄)을 고름')
    elif row is None or not any(c[0] == pt.TALKED for c in row[4]):
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
    ap.add_argument('--people', help='이 「말 건 뒤」 사례만(PEOPLE 이름, 쉼표로 여럿). --only 가 없으면 맵 자리는 돌지 않음')
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
    if args.people:
        picked = set(args.people.split(','))
        unknown = picked - {c[0] for c in PEOPLE}
        if unknown:
            raise SystemExit(f'없는 사례: {", ".join(sorted(unknown))}')
        cases = [c for c in PEOPLE if c[0] in picked]
        if not args.only:
            places = []
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
