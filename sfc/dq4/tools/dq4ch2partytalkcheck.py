"""2장 동료 대화(dq4ch2partytalk) 실행 검사(MesenCE 헤드리스).

2장 출발 상태(dq4ch2walkcheck.head)에서 사례마다 flag·일행·시각을 두고 순간이동한 뒤, 앞에 아무도 없는 쪽을 보고
명령 창 「はなす」를 고른다. 보행 메시지(24:8BAF)가 받은 번호가 롬의 동료 대화 표에서 그 사례에 맞는 줄의 메시지여야
한다. 같은 우선순위의 맞는 줄이 둘이면 두 번 고를 때 차례로 나와야 하고, 맞는 줄이 없으면 원래의 129 여야 한다.

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
import dq4ch2frenol as frenol  # noqa: E402
import dq4ch2king as king  # noqa: E402
import dq4ch2partytalk as pt  # noqa: E402
import dq4ch2tempe as tempe  # noqa: E402
import dq4ch2walkcheck as cw  # noqa: E402

# 명령 창 → 「はなす」 뒤에는 B 로만 넘긴다. A 를 더 누르면 명령 창이 다시 열려 다음 「はなす」가 섞인다
TALK = 'a:8;wait:60;a:8;wait:200;' + ';'.join(['b:8;wait:60'] * 6)


def talk(face, times=1):
    return f'{face}:8;wait:30;' + ';'.join([TALK] * times)


# (이름, 순간이동 TO, 켤 flag, 일행 셋인지, 밤인지, 걷기 입력, 기대 메시지(MESSAGES 이름, 없으면 None = 129)).
# 순간이동은 TO 한 셀 아래에 내린다(dq4ch2walkcheck). 보는 쪽은 인물이 없는 쪽이다
CASES = [
    ('castle', f'{ch2.CASTLE},28,48', [ch2.JOINED], True, False, talk('up'), ['castle_joined']),
    ('castle_alone', f'{ch2.CASTLE},28,48', [ch2.JOINED], False, False, talk('up'), [None]),
    ('tempe_day', f'{ch2.TEMPE},{ch2.CHIEF[0]},{ch2.CHIEF[1] + 1}', [ch2.JOINED], True, False, talk('down'),
     ['tempe_day_kiryl']),
    ('tempe_night', f'{ch2.TEMPE},{ch2.CHIEF[0]},{ch2.CHIEF[1] + 1}', [ch2.JOINED], True, True, talk('down'),
     ['tempe_night_brey']),
    # 같은 우선순위 둘: 처음은 표 차례로 크리프트, 다음 「はなす」는 브라이
    ('tempe_won', f'{ch2.TEMPE},{ch2.CHIEF[0]},{ch2.CHIEF[1] + 1}', [ch2.JOINED, tempe.WON], True, False,
     talk('down', 2), ['tempe_won_kiryl', 'tempe_won_brey']),
    # 우선순위 3(구한 뒤)이 5(납치)보다 먼저
    ('frenol', f'{frenol.TOWN},10,13', [ch2.JOINED, frenol.KIDNAPPED, frenol.LEFT, frenol.RESCUED], True, False,
     talk('down'), ['frenol_rescued_brey']),
    ('king', f'{ch2.THRONE},{ch2.START_CELL[0]},{ch2.START_CELL[1] + 1}', [ch2.JOINED, king.CURED], True, False,
     talk('down'), ['king_cured_kiryl']),
]


def expected(data):
    """{MESSAGES 이름: 롬 표의 메시지 번호}. 줄은 lists 와 같은 차례(우선순위, 같으면 LINES 차례)로 롬에 놓인다."""
    ctx = next(c for c in ch2.contexts() if c.module is pt)
    table = pt.table(data, ctx.at['maps'])
    out = {}
    for key, rows in pt.lists(None).items():
        lines = sorted((ln for ln in pt.LINES if pt._key(ln.map) == key), key=lambda ln: ln.priority)
        for line, row in zip(lines, table[key]):
            out[line.message] = row[3]
        if len(lines) != len(table[key]):
            raise SystemExit(f'{key}: 롬 표의 줄 수 {len(table[key])}, 기대 {len(lines)}')
    return out


def run_case(mesence, rom, data, base, out, case, seed):
    name, to, flags, party, night, walk, want = case
    sets = [f'{0x2190 + i:04X}|{m:02X}' for i, m in flags] + ([cw.join_set(data)] if party else [])
    poke = {'poke': wc.NIGHT} if night else {}
    state, extra = base, ';'.join(sets)
    results = []
    if to.split(',')[0] == ch2.THRONE:
        hop = cw.HOPS[ch2.THRONE]
        r = wc.segment(mesence, rom, state, out / 'hop', ('hop', 'warp', hop, {'map': hop[:5]}), wc.NO_ENCOUNTERS,
                       extra, '', seed, flags=cw.FLAGS)
        results.append(r)
        if r['status'] != 'passed':
            return results
        state, extra = out / 'hop' / 'end.mss', ''
    r = wc.segment(mesence, rom, state, out / 'warp', ('warp', 'warp', to, {'map': to[:5], **poke}),
                   wc.NO_ENCOUNTERS, extra, '', seed, flags=cw.FLAGS)
    results.append(r)
    if r['status'] != 'passed':
        return results
    r = wc.segment(mesence, rom, out / 'warp' / 'end.mss', out / 'talk', ('talk', 'walk', walk, {'map': to[:5], **poke}),
                   wc.NO_ENCOUNTERS, '', '', seed, flags=cw.FLAGS)
    ids = expected(data)
    wanted = [f'{pt.NOBODY if m is None else ids[m]:03X}' for m in want]
    shown = r['messages']
    if shown != wanted:
        r = {**r, 'status': 'failed', 'problems': r['problems'] + [f'메시지 {shown}, 기대 {wanted}']}
    results.append(r)
    return results


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', required=True, type=Path, help='dq4build.py --chapter2 의 롬')
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--jobs', type=int, default=4, help='함께 띄울 MesenCE 수')
    ap.add_argument('--base', type=Path, help='같은 롬으로 만든 2장 출발 상태. 주면 머리를 건너뜀')
    ap.add_argument('--only', help='이 사례만(쉼표로 여럿)')
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
    cases = CASES
    if args.only:
        wanted = set(args.only.split(','))
        unknown = wanted - {c[0] for c in CASES}
        if unknown:
            raise SystemExit(f'없는 사례: {", ".join(sorted(unknown))}')
        cases = [c for c in CASES if c[0] in wanted]
    if args.base:
        base, head = args.base.resolve(), []
    else:
        cache = None if args.no_state_cache else wc.StateCache(data)
        base, head = cw.head(mesence, rom, data, out, cache)
    if base is None or any(r['status'] != 'passed' for r in head):
        print(json.dumps({'status': 'failed', 'head': head}, ensure_ascii=False))
        return 1
    with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
        jobs = {(s, c[0]): pool.submit(run_case, mesence, rom, data, base, wc.seed_dir(out, s, seeds) / c[0], c, s)
                for s in seeds for c in cases}
        results = {f'{s}:{n}': j.result() for (s, n), j in jobs.items()}
    failed = {k: [r for r in rs if r['status'] != 'passed'] for k, rs in results.items()
              if any(r['status'] != 'passed' for r in rs) or len(rs) < 2}
    report = {'status': 'failed' if failed else 'passed', 'seconds': round(time.monotonic() - began),
              'cases': results}
    (out / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'seconds': report['seconds'], 'cases': len(results),
                      'failed': failed}, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
