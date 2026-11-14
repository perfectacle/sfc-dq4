"""2장 동료 대화(dq4ch2partytalk) 실행 검사(MesenCE 헤드리스).

2장 출발 상태(dq4ch2walkcheck.head)에서 동료 대화 줄이 있는 맵마다 한 번 순간이동해 말 상대가 없는 쪽을 보고 서고,
2장 진행 단계(dq4ch2partytalk.STAGES)마다 낮·밤으로 flag·시각을 WRAM 에 써 가며 명령 창 「はなす」를 고른다
(lua/dq4partytalk.lua). 단계마다 보행 메시지(24:8BAF)가 받은 번호가 하나이고, 롬의 동료 대화 표를 조건 평가 루틴과 같은
규칙으로 따라 고른 줄의 메시지(맞는 줄이 없으면 원래의 129)여야 한다. 단계마다 「마지막으로 고른 줄」을 0 으로 두므로
같은 우선순위의 맞는 줄 가운데 표의 첫 줄이 나온다. 메시지가 없거나 둘 이상이면 멈췄거나 창이 닫히지 않은 것이다.

  MESENCE=... LIBDIR=$(uv run krpatch sfc lua) \\
    uv run --locked python sfc/dq4/tools/dq4ch2partytalkcheck.py --rom work/ch2/dq4-ch1-full.sfc --out work/ch2talk
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
    ('40/06', '40/06,26,39', 'down', ''),
    ('40/07', '40/07,28,26', 'down', ''),
    ('40/0C', '40/0C,22,17', 'down', ''),
    ('40/0E', '40/0E,22,35', 'down', ''),
    ('45/00', '45/00,26,9', 'down', ''),
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


def expected(rows, flags, night):
    """롬 표 한 맵의 줄(pt.table 꼴)에서 조건 평가 루틴이 고를 메시지(없으면 129). 일행은 셋 다 살아 있고 선두는 아리나다.
    「마지막으로 고른 줄」이 0 이므로 가장 작은 우선순위의 맞는 줄 가운데 첫 줄이다."""
    values = {a: v for a, (v, _) in stage_bytes(flags).items()}
    party, lead = {pt.ALENA, pt.KIRYL, pt.BREY}, pt.ALENA

    def holds(kind, a, b):
        byte = values.get(0x2190 + a, 0)
        return {pt.ON: lambda: byte & b != 0, pt.OFF: lambda: byte & b == 0, pt.EQUAL: lambda: byte == b,
                pt.LEAD: lambda: a == lead, pt.WITH: lambda: a in party, pt.WITHOUT: lambda: a not in party}[kind]()
    for prio, speaker, when, msg, conds in rows:
        if speaker in party and when in (0, 2 if night else 1) and all(holds(*c) for c in conds):
            return msg
    return pt.NOBODY


def step_env(flags, night):
    writes = [f'{a:04X}={v:02X}/{k:02X}' for a, (v, k) in sorted(stage_bytes(flags).items())]
    t = NIGHT if night else DAY
    writes += [f'075E={t & 0xFF:02X}', f'075F={t >> 8:02X}', f'{0x2190 + pt.LAST[0]:04X}=00']
    return ','.join(writes)


def table_of(data):
    ctx = next(c for c in ch2.contexts() if c.module is pt)
    return pt.table(data, ctx.at['maps'])


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


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', required=True, type=Path, help='dq4build.py --chapter2 의 롬')
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--jobs', type=int, default=4, help='함께 띄울 MesenCE 수')
    ap.add_argument('--base', type=Path, help='같은 롬으로 만든 2장 출발 상태. 주면 머리를 건너뜀')
    ap.add_argument('--only', help='이 맵만(쉼표로 여럿, 필드는 field)')
    ap.add_argument('--shots', action='store_true', help='단계마다 대사 첫 쪽 화면을 talk/<단계>.png 로 남김')
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
    spots = SPOTS
    if args.only:
        wanted = set(args.only.split(','))
        unknown = wanted - {s[0] for s in SPOTS}
        if unknown:
            raise SystemExit(f'없는 맵: {", ".join(sorted(unknown))}')
        spots = [s for s in SPOTS if s[0] in wanted]
    if args.base:
        base, head = args.base.resolve(), []
    else:
        cache = None if args.no_state_cache else wc.StateCache(data)
        base, head = cw.head(mesence, rom, data, out, cache)
    if base is None or any(r['status'] != 'passed' for r in head):
        print(json.dumps({'status': 'failed', 'head': head}, ensure_ascii=False))
        return 1
    with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
        jobs = {(s, p[0]): pool.submit(run_spot, mesence, rom, data, base,
                                       wc.seed_dir(out, s, seeds) / p[0].replace('/', ''), p, s, args.shots)
                for s in seeds for p in spots}
        results = {f'{s}:{n}': j.result() for (s, n), j in jobs.items()}
    failed = {k: [r for r in rs if r['status'] != 'passed'] for k, rs in results.items()
              if any(r['status'] != 'passed' for r in rs) or rs[-1].get('name') != 'talk'}
    shown = sum(1 for rs in results.values() if rs[-1].get('name') == 'talk'
                for ids in rs[-1]['shown'].values() if ids and ids != [f'{pt.NOBODY:03X}'])
    report = {'status': 'failed' if failed else 'passed', 'seconds': round(time.monotonic() - began),
              'spots': len(results), 'talks': len(results) * len(steps()), 'lines_shown': shown, 'cases': results}
    (out / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('status', 'seconds', 'spots', 'talks', 'lines_shown')} | {'failed': failed},
                     ensure_ascii=False))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
