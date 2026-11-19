"""3장 넘김과 첫머리 검사(MesenCE 헤드리스): 2장 끝 사건 뒤 3장 상자·서두를 지나 톨네코 집에서 조작이 풀리는지 본다.

2장 걷기 검사(dq4ch2walkcheck.py)의 2장 출발 상태(롬 SHA-1 별 캐시)와 걷기·판정을 그대로 쓴다. 우승 뒤 빈 산트하임
왕좌의 방(브라이의 말)에서 계단으로 성 앞마당에 내려가 2장 끝 서술 → 3장 넘김 → 레이크나바 톨네코 집(3E/01)에서
3장 제목 상자 → 서두 서술 → 네네의 부름 → 방향 키 → 네네가 깨우는 말을 넘긴 뒤, 3장 flag 가 켜지고 첫머리 대기
flag·2장 flag 가 꺼지고 일행 수 1·금화 0·주인공 기록이 톨네코이고 아리나 일행 기록이 맡긴 칸에 있는지 본다. 그 뒤
사건 등록 견본(dq4ch3lakanaba)으로 네네에게 말을 걸어, 도시락을 가졌으면 그대로이고 비우면 받는지 본다. 끝으로 대화 호출
표의 칸을 공용 장치(give·take·pay·earn)로 바꾼 롬 사본마다 같은 대화로 금화·물건·결과 flag 를 잰다(DEVICES).
난수·시각·조우는 2장 검사와 같이 묶고, --repeat 2 는 두 번 걸어 구간 기록이 같은지 본다.

  MESENCE=… uv run --locked python sfc/dq4/tools/dq4ch3opencheck.py --rom work/ch3/dq4-ch1-full.sfc --out work/ch3open

롬은 dq4build.py --chapter3 의 출력이어야 한다(2장 끝에서 3장으로 넘어감).
"""
import argparse
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
import dq4ch2walkcheck as cw  # noqa: E402
import dq4ch3event as ch3  # noqa: E402
import dq4ch3lakanaba as lakanaba  # noqa: E402
from dq4ch3slots import VARS_AT, VARS_SIZE  # noqa: E402
from dq4itemport import BENTO  # noqa: E402

# 2장 검사의 flag 표에 3장 flag 와 기록 바이트를 더한다(구간 판정이 이 표의 바이트를 찍는다)
cw.FLAGS.update({
    'CHAPTER3': wc.flag(ch3.CHAPTER3),
    'OPENING3': wc.flag(ch3.OPENING),
    'COUNT': (0x7E201D, 0xFF),
    'GOLD0': (ch2.GOLD_AT, 0xFF), 'GOLD1': (ch2.GOLD_AT + 1, 0xFF), 'GOLD2': (ch2.GOLD_AT + 2, 0xFF),
    'HP0': (ch2.PARTY_AT + 2, 0xFF), 'STR0': (ch2.PARTY_AT + 7, 0xFF), 'VIT0': (ch2.PARTY_AT + 8, 0xFF),
    'NAME0': (ch2.NAME_AT, 0xFF),
    # 맡긴 아리나 기록의 HP 낮은 바이트(맡긴 첫 칸 +1 의 +2)
    'STASH_HP': (ch3.stash_pieces()[0][1] + 2, 0xFF),
    'TIME0': (ch2.TIME_AT, 0xFF), 'TIME1': (ch2.TIME_AT + 1, 0xFF),
    'BENTO_TODAY': wc.flag(lakanaba.BENTO_TODAY),
    'ITEM1': (ch2.PARTY_AT + 0x16 + 1, 0xFF),
    # 3장 변수 칸(dq4ch3slots.VARS_AT) 첫·끝 바이트: 1·2장 동안 아무도 쓰지 않아 0 이어야 한다
    'VARS_FIRST': (VARS_AT, 0xFF), 'VARS_LAST': (VARS_AT + VARS_SIZE - 1, 0xFF),
    'RESULT': wc.flag(ch3.RESULT), 'ITEM0': (ch2.PARTY_AT + 0x16, 0xFF), 'EQUIP0': (ch2.PARTY_AT + 0x14, 0xFF),
    'BAG_BENTO': (ch3.BAG + BENTO, 0xFF),
})

# 서술·말을 A 로 넘기고 사이사이 왼쪽을 짧게 눌러 네네가 기다리는 방향 키를 준다. 조작이 풀린 뒤에도 몇 번 더
# 누르게 되므로 끝에 창을 닫는다. 왼쪽은 벽이라 톨네코는 시작 칸(침대, 네네 바로 아래)에 남는다. 침대 아래 칸으로
# 내려서면 침대 머리 칸으로 다시 올라갈 수 없어 네네에게 말을 걸 자리가 없다(실측)
OPEN_INPUT = ';'.join(['a:8;wait:50;left:2;wait:30'] * 26) + ';wait:120;' + wc.pc.CLOSE

# (이름, 방법, 인자, 선택). 2장 검사의 빈 성 묶음을 계단까지 쓰고(empty_leave), 그 뒤 성 앞마당에서 장 끝이 3장으로 이어진다
FIRST, LAST = 'empty_throne_side', 'empty_leave'
# 레이크나바 모듈(dq4ch3lakanaba): 시작 칸에서 위의 네네에게 말을 건다. 첫머리 직후(집을 다시 불러오기 전, FRESH)에는
# 「곧장 서쪽으로」 뿐이라 도시락(물건 칸 1)도 오늘 도시락 flag 도 그대로다. FRESH 를 지우고 도시락 칸을 비운 뒤 다시 걸면
# 오늘 도시락 전이라 잠 → 아침 → 도시락을 받고 BENTO_TODAY 가 켜진다
NENE_TALK = wc.talk('up', 12)
BENTO_KEEP = ('ch3_bento_keep', 'walk', NENE_TALK,
              {'map': ch3.HOUSE, 'off': ['BENTO_TODAY'], 'items': [BENTO], 'bytes': {'ITEM1': BENTO}})
BENTO_GIVE = ('ch3_bento_give', 'walk', NENE_TALK,
              {'map': ch3.HOUSE, 'want': ['BENTO_TODAY'], 'items': [BENTO], 'bytes': {'ITEM1': BENTO}})
# 도시락 칸을 비우고 첫머리 직후 표시(맵 안 임시 칸)를 지우는 시작 SET(한 번)
NO_BENTO = f'{(ch2.PARTY_AT + 0x16 + 1) & 0xFFFF:04X}=FF;{(0x7E2190 + ch3.FRESH[0]) & 0xFFFF:04X}=00'


def segments(start):
    """2장 검사 구간 표를 빈 성 계단(LAST)까지 쓰고 3장 첫머리 구간을 더한 표. start 는 3장 시작 HP(톨네코 1레벨)."""
    names = [s[0] for s in cw.SEGMENTS]
    out = list(cw.SEGMENTS[:names.index(LAST) + 1])
    out.append(('ch3_open', 'walk', OPEN_INPUT,
                {'changes': 1, 'after': 3200, 'maxf': 6000, 'map': ch3.HOUSE, 'cell': ch3.START_CELL,
                 'want': ['CHAPTER3'], 'off': ['CHAPTER2', 'OPENING3'], 'start': (5, 3),
                 'bytes': {'COUNT': 1, 'GOLD0': 0, 'GOLD1': 0, 'GOLD2': 0, 'HP0': start['hp'],
                           'STR0': start['stats'][0], 'VIT0': start['stats'][1],
                           'NAME0': ch2.name_bytes(ch3.TORNEKO_NAME)[0], 'STASH_HP': ch2.ALENA_STATS['hp'],
                           'ITEM1': BENTO, 'VARS_FIRST': 0, 'VARS_LAST': 0}}))
    out.append(BENTO_KEEP)
    return out


def give_bento(mesence, rom, dest, seed):
    """BENTO_KEEP 끝 상태에서 도시락 칸을 비우고 다시 네네에게 말을 건다(SET 은 구간 시작에 한 번)."""
    r = wc.segment(mesence, rom, dest / BENTO_KEEP[0] / 'end.mss', dest / BENTO_GIVE[0], BENTO_GIVE,
                   wc.NO_ENCOUNTERS, NO_BENTO, '', seed, flags=cw.FLAGS)
    more = [p for p in (cw.end_cell_problem(dest / BENTO_GIVE[0], BENTO_GIVE),
                        *cw.end_byte_problems(dest / BENTO_GIVE[0], BENTO_GIVE)) if p]
    return {**r, 'status': 'failed', 'problems': r['problems'] + more} if more else r


# 공용 장치(대화 호출 표의 give·take·pay·earn): 검사 롬 사본의 표 칸 0(레이크나바의 잠)을 그 장치로 바꾸고, 도시락을
# 비운 채 네네에게 한 번 말을 건다(오늘 도시락 전이라 080B·080C 뒤 표 칸 0 을 부름). (이름, 장치, 인자, 시작 SET, 끝 바이트). 톨네코는 ぬののふく(42, 장비)만 가진다
DEVICE_TALK = wc.talk('up', 2)
DEVICES = (
    ('pay_ok', 'pay', 0, '2019=40;201A=9C;201B=00', {'GOLD0': 0x88, 'GOLD1': 0x13, 'GOLD2': 0}),       # 40000 - 35000
    ('pay_short', 'pay', 0, '2019=64;201A=00;201B=00', {'GOLD0': 100, 'GOLD1': 0, 'GOLD2': 0}),
    ('earn', 'earn', 1, '2019=64;201A=00;201B=00', {'GOLD0': 0x0C, 'GOLD1': 0x62, 'GOLD2': 0}),         # 100 + 25000
    ('take', 'take', 0x42, '', {'ITEM0': 0xFF, 'EQUIP0': 0}),
    ('take_bag', 'take', BENTO, f'{(ch3.BAG + BENTO) & 0xFFFF:04X}=02', {'ITEM0': 0x42, 'BAG_BENTO': 1}),
    ('give_full', 'give', BENTO, ';'.join(f'{(ch2.PARTY_AT + 0x16 + k) & 0xFFFF:04X}=A1' for k in range(12)),
     {'ITEM1': 0xA1, 'BAG_BENTO': 1}),
)
DEVICE_RESULT = {'pay_ok': True, 'pay_short': False, 'take': True, 'take_bag': True}


def devices(mesence, data, dest, seed):
    """DEVICES 를 BENTO_KEEP 끝 상태에서 하나씩 돌린다."""
    import dq4chapter1
    base, out = ch3.native()[1], []
    for name, routine, param, more, want in DEVICES:
        d = bytearray(data)
        o = dq4chapter1.lorom(ch3.TABLE_AT)
        d[o:o + 4] = ch3._al(base[routine]) + bytes((param,))
        rom = dest / f'device-{name}.sfc'
        rom.write_bytes(bytes(d))
        opt = {'map': ch3.HOUSE, 'bytes': want}
        if name in DEVICE_RESULT:
            opt['want' if DEVICE_RESULT[name] else 'off'] = ['RESULT']
        seg = (f'device_{name}', 'walk', DEVICE_TALK, opt)
        start = ';'.join(v for v in (NO_BENTO, f'{ch3._flag_addr(ch3.RESULT) & 0xFFFF:04X}=00', more) if v)
        r = wc.segment(mesence, rom, dest / BENTO_KEEP[0] / 'end.mss', dest / seg[0], seg, wc.NO_ENCOUNTERS, start,
                       '', seed, flags=cw.FLAGS)
        more_problems = cw.end_byte_problems(dest / seg[0], seg)
        out.append({**r, 'status': 'failed', 'problems': r['problems'] + more_problems} if more_problems else r)
    return out


def unit(segs):
    names = [s[0] for s in segs]
    return list(range(names.index(FIRST), len(segs)))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', required=True, type=Path, help='dq4build.py --chapter3 의 롬')
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--base', type=Path, help='같은 롬으로 만든 2장 출발 상태. 주면 머리를 건너뜀')
    ap.add_argument('--repeat', type=int, default=1, choices=(1, 2), help='2 면 두 번 걸어 기록을 견줌')
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
    cache = None if args.no_state_cache else wc.StateCache(data)
    began = time.monotonic()
    if args.base:
        base, head = args.base.resolve(), []
    else:
        base, head = cw.head(mesence, rom, data, out, cache)
        for r in head:
            print(json.dumps(r, ensure_ascii=False), flush=True)
    import dq4growth
    segs = segments(ch3.start(Path(HERE.parents[2] / 'rom' / 'dq5.sfc'), dq4growth.DQ4))
    runs = {}
    ok = base is not None and all(r['status'] == 'passed' for r in head)
    for seed in seeds if ok else ():
        for n in range(1, args.repeat + 1):
            dest = wc.seed_dir(out, seed, seeds) / (f'run-{n}' if args.repeat > 1 else '')
            rs = cw.walk_unit(mesence, rom, data, dest, unit(segs), base, seed, segments=segs)
            if rs and all(r['status'] == 'passed' for r in rs):
                rs.append(give_bento(mesence, rom, dest, seed))
                rs += devices(mesence, data, dest, seed)
            for r in rs:
                print(json.dumps(r, ensure_ascii=False), flush=True)
            runs[seed, n] = rs
    problems = []
    for (seed, n), rs in runs.items():
        if len(rs) != len(unit(segs)) + 1 + len(DEVICES) or any(r['status'] != 'passed' for r in rs):
            problems.append(f'{seed}:{n} 실패')
        if n == 2:
            bad = cw.compare_runs(runs[seed, 1], rs)
            problems += [f'{seed}:{k} {v}' for k, v in bad.items()]
    ok = ok and bool(runs) and not problems
    report = {'status': 'passed' if ok else 'failed', 'seconds': round(time.monotonic() - began), 'head': head,
              'problems': problems, 'runs': {f'{s}:{n}': rs for (s, n), rs in runs.items()}}
    (out / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n')
    print(json.dumps({'status': report['status'], 'seconds': report['seconds'], 'problems': problems},
                     ensure_ascii=False))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
