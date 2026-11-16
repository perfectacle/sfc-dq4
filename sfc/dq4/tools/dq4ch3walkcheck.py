"""3장 사건을 구간마다 따로 걷는 검사(MesenCE 헤드리스). 걷기·순간이동·판정과 묶음 나누기는 2장 검사와 같은
틀(dq4chapterwalk.py)이고, 구간 표·flag 표·출발 상태만 3장 것이다.

  머리  2장 걷기 검사의 2장 출발 상태(dq4ch2walkcheck.head, 캐시)에서 3장 첫머리 검사 구간(dq4ch3opencheck:
        우승 뒤 빈 산트하임 → 2장 끝 → 3장 넘김 → 톨네코 집 첫머리)을 시드 0 으로 걷는다. 끝 상태가 「3장 출발
        상태」(3E/01, 조작 풀림)이고, 같은 캐시 폴더에 둔다(ch3-start-<지문>.mss). 캐시는 --repeat 2 로 머리를 두 번
        걸어 기록이 같을 때만 넣는다.
  묶음  SEGMENTS 는 순간이동 구간마다 묶음 하나다. 묶음마다 3장 출발 상태에서 따로 시작해 함께 돈다(--jobs).
        묶음 첫 구간에는 앞 구간들이 켰을 flag(want·off)와 기록에 남기는 것(effects)을 SET·PARTY 로 둔다.

난수·시각·조우는 2장 검사와 같이 묶는다. --repeat 2 는 묶음마다 두 번 걸어 구간 기록의 SHA-1 이 같은지 본다.

  MESENCE=… LIBDIR=… python sfc/dq4/tools/dq4ch3walkcheck.py --rom work/ch3/dq4-ch1-full.sfc --out work/ch3walk
  (--only 구간,… 은 그 구간으로 시작하는 묶음만, --base 는 3장 출발 상태를 다시 쓴다)

롬은 dq4build.py --chapter3 의 출력이어야 한다(2장 끝에서 3장으로 넘어감). 구간을 붙이는 법은
sfc/dq4/docs/dq4-chapter3-format.md 「검사」.
"""
import functools
import inspect
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4ch1walkcheck as wc  # noqa: E402
import dq4ch2walkcheck as cw  # noqa: E402
import dq4ch3event as ch3  # noqa: E402
import dq4ch3opencheck as opening  # noqa: E402
import dq4ch3safe as safe  # noqa: E402
import dq4chapterwalk as cwk  # noqa: E402

talk, taps = wc.talk, wc.taps
CLOSE = wc.pc.CLOSE

# 2장 검사의 flag 표(dq4ch3opencheck 가 3장 flag 와 첫머리 바이트를 더한 것)에 3장 사건 flag 를 더한다. 새 사건 flag 는
# 여기에 한 줄씩: 'NAME': wc.flag(모듈.FLAG)
FLAGS = {
    **cw.FLAGS,
    'SAFE_DRAINED': wc.flag(safe.DRAINED),
    'SAFE_ANSWERED': wc.flag(safe.ANSWERED),
    'SAFE_YES': wc.flag(safe.YES),
    # 톨네코 물건 칸 2(칸 0 옷, 칸 1 도시락 다음): 금고 상자를 열면 철 금고가 들어오는 칸
    'SAFE_SLOT': (0x7E2056 + 2, 0xFF),
}

TOWN = '3E/00'                 # FC 16/00 레이크나바
# 3장 출발 상태(3E/01)와 같은 맵으로 순간이동하는 묶음이 먼저 들르는 곳
HOPS = {ch3.HOUSE: f'{TOWN},4,26'}


def effects(data):
    """구간이 flag 말고 기록(7E:2000~2A9F)에 남기는 것(구간 이름 → SET(set)·dq5warp.lua PARTY(party)). 묶음 첫
    구간에 둔다. 롬의 기록 틀을 읽는 것이 있어 롬 바이트를 받는다."""
    return {}


def battle_patch(data, kind):
    """3장 사건 전투 몬스터(사건 모듈의 BATTLES)를 덮는 ROMPATCH(dq4chapterwalk.battle_patch)."""
    modules = ch3.modules() if hasattr(ch3, 'modules') else ()
    every = sorted({m for _, mod in modules for b in getattr(mod, 'BATTLES', ()) for m, _ in b['members']})
    return cwk.battle_patch(data, kind, every)


# 머리는 SEGMENTS 밖(head_segments)에서 걷는다. 출발 상태 맵이 롬에 따라 다르지 않아 표에는 사건 구간만 둔다
HEAD = 0

# 레이크나바 마을 FC 16/00 의 왼쪽 가장자리 도착 칸(dq4groupbuild LINKS arrival (00,0D) = 셀 (0,27))의 두 칸 오른쪽.
# 순간이동은 TO 의 한 셀 아래에 내린다
TOWN_WEST = f'{TOWN},4,26'
# 나가면 필드의 레이크나바 입구 블록(dq4groupbuild.doors: 셀 (208,72)~(209,73)) 아래 (208,75)에 선다
FIELD_OUT = (208, 75)
TOWN_ARRIVAL = (0, 27)
# 집 계단(FC 16/01 (21,07))으로 내려서는 마을 칸
HOUSE_OUT = (56, 55)

# 북쪽 동굴: 오른쪽·왼쪽 수문 앞 주인공 셀(dq4ch3safe.RIGHT·LEFT 의 사각형 왼쪽 아래). 순간이동은 두 셀 아래에 내려
# 위로 걸어 선다. 바닥 글은 세 쪽 뒤 「예」 에 커서
SAFE_RIGHT = (safe.RIGHT['rect'][0], safe.RIGHT['rect'][3])
SAFE_LEFT = (safe.LEFT['rect'][0], safe.LEFT['rect'][3])
SAFE_OFF = ['SAFE_ANSWERED', 'SAFE_YES']
SAFE_ASK = 'wait:30'
SAFE_FLOOR = 'a:8;wait:80;a:8;wait:80;a:8;wait:120'
SAFE_FACE_UP = '7E31E0=88'
# 명령 창 → しらべる(dq4chestcheck.SEARCH), 상자 메시지를 넘기고 창을 닫는다
SAFE_SEARCH = ('a:8;wait:60;down:6;wait:25;down:6;wait:25;down:6;wait:25;right:6;wait:25;a:8;wait:200;'
               'a:4;wait:150;a:4;wait:150;b:4;wait:220')

# (이름, 방법, 인자, 선택). 꼴은 dq4ch2walkcheck.SEGMENTS 와 같다(선택은 dq4chapterwalk 머리말)
SEGMENTS = [
    # 첫머리 뒤 침대(시작 칸)에서 침대 아래로 내려서 방을 지나 문(FC (1F,07))을 열고 계단(FC (21,07))으로 마을에
    ('house', 'walk', '54,13;58,13;58,15;66,15',
     {'map': TOWN, 'changes': 1, 'after': 60, 'cell': HOUSE_OUT, 'want': ['CHAPTER3'], 'off': ['OPENING3']}),
    # 마을 왼쪽 가장자리로 나가 필드의 입구 아래 칸에 서고, 위로 걸어 다시 마을 도착 칸에
    ('town_side', 'warp', TOWN_WEST, {'map': TOWN}),
    ('town_out', 'walk', 'left:64', {'field': True, 'cell': FIELD_OUT, 'poke': wc.DAY}),
    # 필드에서는 7E:00BC·00BD 가 떠난 맵 그대로라 맵 바뀜으로 잡히지 않는다. 실내(field False)와 끝 셀로 본다
    ('town_in', 'walk', f'{FIELD_OUT[0]},{FIELD_OUT[1] - 2}', {'map': TOWN, 'field': False, 'cell': TOWN_ARRIVAL,
                                                                'poke': wc.DAY}),
    # 북쪽 동굴(dq4ch3safe). 수문 앞 칸에 서면 묻고, 「아니요」 면 그대로, 칸을 떠났다 다시 서서 「예」 면 물살에 계단으로
    ('safe_gates', 'warp', f'{safe.GATES},{SAFE_RIGHT[0]},{SAFE_RIGHT[1] + 2}', {'map': safe.GATES}),
    ('safe_no', 'walk', f'up:40;wait:200;{SAFE_ASK};down:4;wait:30;a:8;wait:200;{CLOSE}',
     {'map': safe.GATES, 'cell': SAFE_RIGHT, 'off': SAFE_OFF}),
    ('safe_right', 'walk', f'down:20;wait:60;up:30;wait:200;{SAFE_ASK};a:8;wait:60;a:8;wait:1300',
     {'map': safe.ENTRY, 'cell': safe.RIGHT['to'][1], 'off': SAFE_OFF, 'changes': 1, 'after': 60}),
    # 왼쪽 수문은 통로 끝 구덩이로 떨어뜨리고 물이 빠졌다는 flag 를 켠다
    ('safe_left_side', 'warp', f'{safe.GATES},{SAFE_LEFT[0]},{SAFE_LEFT[1] + 2}', {'map': safe.GATES}),
    ('safe_left', 'walk', f'up:40;wait:200;{SAFE_ASK};a:8;wait:60;a:8;wait:1300',
     {'map': safe.PIT, 'cell': safe.LEFT['to'][1], 'want': ['SAFE_DRAINED'], 'changes': 1, 'after': 60}),
    # 물이 빠진 뒤 입구 층의 계단(출구 번호 1)은 3E/04 대신 3E/05 의 같은 계단으로
    ('safe_dry_side', 'warp', f'{safe.ENTRY},6,34', {'map': safe.ENTRY}),
    ('safe_dry', 'walk', 'left:40;wait:300', {'map': safe.DRY, 'cell': (22, 29), 'want': ['SAFE_DRAINED']}),
    # 금고 상자 아래에서 위를 보고 しらべる → 철 금고. 상자 칸을 떠났다 밟으면 바닥 글, 「예」 면 되돌리고 상자가 닫힘
    ('safe_vault', 'warp', f'{safe.VAULT},8,8', {'map': safe.VAULT}),
    ('safe_open', 'walk', SAFE_SEARCH, {'poke': SAFE_FACE_UP, 'items': [safe.IRON_SAFE]}),
    ('safe_return', 'walk', f'8,9;wait:60;8,8;wait:300;{SAFE_FLOOR};a:8;wait:200;a:8;wait:200;{CLOSE}',
     {'map': safe.VAULT, 'cell': (8, 8), 'bytes': {'SAFE_SLOT': 0xFF}, 'off': SAFE_OFF}),
    ('safe_reopen', 'walk', f'8,9;wait:60;{SAFE_SEARCH}', {'poke': SAFE_FACE_UP, 'items': [safe.IRON_SAFE]}),
]


def units(segments=None):
    return cwk.units(SEGMENTS if segments is None else segments, HEAD)


def setup(first, segments=None, data=None):
    return cwk.setup(SEGMENTS if segments is None else segments, HEAD, first, FLAGS,
                     effects(data) if data is not None else {})


def walk_unit(mesence, rom, data, out, unit, base, seed=0, segments=None):
    """한 묶음을 3장 출발 상태에서 걷는다."""
    return cwk.walk_unit(mesence, rom, data, out, unit, base, seed, SEGMENTS if segments is None else segments, HEAD,
                         FLAGS, effects, HOPS, battle_patch)


@functools.cache
def head_segments():
    """머리 구간 표: 2장 검사 표를 빈 성 계단까지 쓰고 3장 첫머리(ch3_open)를 더한 것(dq4ch3opencheck.segments 의
    ch3_open 까지)과 그 가운데 걷는 묶음(빈 성 왕좌의 방부터)."""
    import dq4growth
    segs = opening.segments(ch3.start(HERE.parents[2] / 'rom' / 'dq5.sfc', dq4growth.DQ4))
    names = [s[0] for s in segs]
    segs = segs[:names.index('ch3_open') + 1]
    return segs, list(range(names.index(opening.FIRST), len(segs)))


def head_key(mesence, data):
    """3장 출발 상태를 정하는 것: 2장 출발 상태의 키에 머리를 걷는 코드·머리 구간 표·그 묶음의 시작 flag 를 더한다.
    사건 구간(SEGMENTS)은 넣지 않아 구간을 붙여도 머리를 다시 걷지 않는다."""
    segs, unit = head_segments()
    return wc.fingerprint(cw.head_key(mesence), inspect.getsource(head), Path(cwk.__file__),
                          repr([segs[i] for i in unit]), repr(cw.setup(unit[0], segs, data)), repr(sorted(FLAGS.items())))


def head(mesence, rom, data, out, cache=None, repeat=1):
    """3장 출발 상태와 머리 결과(2장 머리 결과 + 3장 머리 묶음 결과). 머리는 시드 0 으로 걷는다."""
    segs, unit = head_segments()
    key = head_key(mesence, data) if cache else None
    state = out / 'head' / segs[-1][0] / 'end.mss'
    hit = cache.get('ch3-start', key, '.mss', state) if cache else None
    if hit:
        return state, [{**r, 'cached': cache.path('ch3-start', key, '.mss').name} for r in hit[1]['segments']]
    base, results = cw.head(mesence, rom, data, out, cache)
    if base is None:
        return None, results
    runs = []
    for n in range(1, repeat + 1):
        dest = out / ('head' if n == 1 else f'head-{n}')
        rs = cw.walk_unit(mesence, rom, data, dest, unit, base, 0, segments=segs)
        runs.append(rs)
        if len(rs) != len(unit) or any(r['status'] != 'passed' for r in rs):
            return None, results + rs
    if repeat > 1:
        bad = cwk.compare_runs(*runs)
        if bad:
            return None, results + [{**r, 'status': 'failed', 'problems': r['problems'] + [bad[r['name']]]}
                                    if r['name'] in bad else r for r in runs[0]]
    results = results + runs[0]
    # 한 번만 걸은 머리는 결정적인지 모르므로 캐시에 넣지 않는다(가드는 --repeat 2)
    if cache and repeat > 1:
        cache.put('ch3-start', key, '.mss', state, {'segments': results})
    return state, results


def main():
    return cwk.main(sys.modules[__name__], __doc__, 'dq4build.py --chapter3 의 롬',
                    '같은 롬으로 만든 3장 출발 상태(head/ch3_open/end.mss). 주면 머리를 건너뜀')


if __name__ == '__main__':
    sys.exit(main())
