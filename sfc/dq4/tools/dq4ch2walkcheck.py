"""2장 사건을 구간마다 따로 걷는 검사(MesenCE 헤드리스). 1장 걷기 검사(dq4ch1walkcheck.py)의 걷기·순간이동·판정을
그대로 쓰고, 구간 표와 flag 표만 2장 것이다.

  머리  서장 끝 상태(dq4ch1walkcheck.prologue, 롬 SHA-1 별 캐시)에서 1장 왕 보고 앞까지의 flag 를 두고 1장 끝을 걸어
        2장 왕좌의 방 첫머리를 넘긴다. 이 끝 상태가 「2장 출발 상태」이고, 같은 캐시 폴더에 둔다(ch2-opening-<지문>.mss).
  묶음  나머지 구간은 순간이동 구간마다 묶음 하나다. 묶음마다 2장 출발 상태에서 따로 시작해 함께 돈다(--jobs).
        묶음 첫 구간에는 앞 구간들이 켰을 flag(want·off)와 기록에 남기는 것(effects)을 SET·PARTY 로 둔다.

난수·시각·조우는 1장 검사와 같이 묶는다: 구간 시작과 순간이동 도착에 난수(--seed)·시각(낮 50, 밤 구간은 F0)을 두고,
조우 판정을 덮어 걸음 전투를 없앤다. --repeat 2 는 묶음마다 두 번 걸어 구간 기록(walk.txt·warp.txt)의 SHA-1 이 같은지
본다. 같지 않으면 실패다(운으로 통과하지 않는다는 근거).

  MESENCE=… LIBDIR=… python sfc/dq4/tools/dq4ch2walkcheck.py --rom work/ch2/dq4-ch1-full.sfc --out work/ch2walk
  (--only 구간,… 은 그 구간으로 시작하는 묶음만, --base 는 2장 출발 상태를 다시 쓴다)

롬은 dq4build.py --chapter2 의 출력이어야 한다(1장 끝에서 2장으로 넘어감). 구간을 붙이는 법은
sfc/dq4/docs/dq4-chapter2-format.md 「검사에 구간 붙이기」.
"""
import inspect
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4ch1walkcheck as wc  # noqa: E402
import dq4chapterwalk as cwk  # noqa: E402
import dq4ch2checks  # noqa: E402
import dq4ch2event as ch2  # noqa: E402
from dq4ch2walkparts import CLOSE, flag, talk, taps  # noqa: E402

# 사건 모듈 _checks 의 flag 표를 잇는 차례. flag 표 차례가 기록(WATCH·SET) 차례라 모듈로 나누기 전의 차례를 지킨다.
# 새 모듈·묶음은 여기 적지 않는다: 여기 없는 것은 EVENTS 차례로 뒤에 붙는다(dq4eventchecks.ordered). 구간 표는 공용
# 구간 뒤에 EVENTS 차례 그대로다
FLAG_ORDER = ('common.castle', 'E1', 'E4', 'common.kiryl', 'E2', 'E3', 'E5', 'common.bank')

# 2장 공용 flag(dq4ch2event). 사건 flag 는 그 사건 모듈의 _checks 에
COMMON_FLAGS = {
    'common.castle': {
        'TALKED_GATE': flag(ch2.TALKED_GATE),
        'TALKED_BREY': flag(ch2.TALKED_BREY),
        'TALKED_KIRYL': flag(ch2.TALKED_KIRYL),
        'READY': flag(ch2.READY),
        'KICKED': flag(ch2.KICKED),
        'JOINED': flag(ch2.JOINED),
    },
    # 크리프트의 셋째 칸(지저귐의 꿀을 두는 곳). 왕에게 먹이면 비어야 한다
    'common.kiryl': {'KIRYL_ITEM2': (ch2.JOIN_RECORDS_AT + 0x16 + 2, 0xFF)},
    # flag 가 아니라 바이트 전체(마스크 FF)를 본다: 1장에 맡긴 やくそう 개수와 맡긴 금화(1000G 단위) 아래 바이트
    'common.bank': {'BANK_HERB': (ch2.BANK_ITEMS_AT + 0xA1, 0xFF), 'BANK_GOLD': (ch2.BANK_GOLD_AT, 0xFF)},
}

# 1장 flag(머리 구간이 보는 REPORTED·CHAPTER2·OPENING 등)에 2장 공용·사건 flag 를 잇는다
FLAGS = dict(wc.FLAGS)
for _, _flags in dq4ch2checks.ordered(list(COMMON_FLAGS.items()) + dq4ch2checks.blocks('FLAGS', 'FLAG_BLOCKS'),
                                      FLAG_ORDER):
    FLAGS.update(_flags)

# 1장 왕 보고 앞에 맡긴 것: やくそう 3 개와 금화 2000. FC 장 초기화처럼 2장 첫머리에는 둘 다 0 이어야 한다
CH1_BANK = f'{(ch2.BANK_ITEMS_AT + 0xA1) & 0xFFFF:04X}=03;{ch2.BANK_GOLD_AT & 0xFFFF:04X}=02'


def join_set(data):
    """두 사람 합류(dq4ch2event._join)가 기록에 남기는 것: 일행 기록 1·2, 일행 수 3, 순서 0 1 2. 다음 레벨 경험치는
    틀 값 그대로다(합류 이벤트는 21:805A 로 다시 셈). dq5warp.lua PARTY 는 몬스터 동료 기록만 만들어 쓰지 않는다."""
    records = b''.join(ch2.recruit_records(data))
    at = ch2.JOIN_RECORDS_AT & 0xFFFF
    out = [f'{at + i:04X}={v:02X}' for i, v in enumerate(records)]
    n = 1 + len(ch2.RECRUITS)
    out += [f'{a:04X}={n:02X}' for a in (0x201D, 0x201E, 0x201F)]
    out += [f'{base + k:04X}={k:02X}' for k in range(n) for base in (0x2020, 0x2028)]
    return ';'.join(out)


def effects(data):
    """구간이 flag 말고 기록(7E:2000~2A9F)에 남기는 것(구간 이름 → SET(set)·dq5warp.lua PARTY(party)). 묶음 첫
    구간에 둔다. 롬의 기록 틀을 읽는 것이 있어 롬 바이트를 받는다. 사건 모듈 _checks 의 effects 를 더한다."""
    return {'join': {'set': join_set(data)}, **dq4ch2checks.effects(data)}


# 같은 맵 안으로 순간이동하는 묶음이 먼저 들르는 곳(2장 출발 상태는 왕좌의 방 3D/01)
HOPS = {ch2.THRONE: f'{ch2.CASTLE},28,45'}

# 낮의 왕좌의 방에서 걸어 다니는 브라이(목록 첫 인물 = 물체 슬롯 08)의 걸음 간격을 0 으로 묶어 제자리에 세운다.
# 묶지 않으면 난수에 따라 비켜 서서 시드 5·9 에서 「その方向には誰もいない」(129)가 났다
HOLD_BREY = '7E3308=00'

KING_INDEX = [s[0] for s in wc.SEGMENTS].index('castle')

# (이름, 방법, 인자, 선택). 꼴은 dq4ch1walkcheck.SEGMENTS 와 같다. 첫 셋이 머리(2장 출발 상태까지)다
SEGMENTS = [
    wc.SEGMENTS[KING_INDEX],
    wc.CHAPTER2_END[0],
    # 제목 상자·서두 서술·부르는 소리·왕의 말을 넘기면 첫머리 flag 가 꺼지고 조작이 풀린다. A 를 더 누르면 왕에게
    # 다시 말을 걸어 물음이 되풀이되므로(12번째 A 에서 실측) 넘길 만큼만 누른다
    ('opening', 'walk', 'wait:200;' + taps(10, 90) + ';wait:300;' + CLOSE,
     {'maxf': 4000, 'map': ch2.THRONE, 'want': ['CHAPTER2'], 'off': ['OPENING', 'BANK_HERB', 'BANK_GOLD'],
      'items': [ch2.SILK_ROBE], 'start': (7, 2)}),
]
HEAD = 3


def battle_patch(data, kind):
    """사건 전투 몬스터(dq4ch2event 모듈의 BATTLES)를 덮는 ROMPATCH(dq4chapterwalk.battle_patch)."""
    every = sorted({m for _, mod in ch2.modules() for b in getattr(mod, 'BATTLES', ()) for m, _ in b['members']})
    return cwk.battle_patch(data, kind, every)


# 2장 사건 구간. 순간이동(warp) 구간마다 새 묶음이고, 묶음 첫 구간에는 앞 구간들의 want·off·effects 가 놓인다.
# 선택은 dq4ch1walkcheck.SEGMENTS 의 것에 더해 cell(끝에 주인공이 선 셀 (x, y)). 사건 구간은 사건 모듈 _checks 의
# SEGMENTS(dq4ch2checks)
COMMON_SEGMENTS = [
    # 산트하임 성: 크리프트·브라이·성문 병사와 이야기해 「셋 다」를 켠다(dq4ch2event TALKED_*·READY)
    ('kiryl_side', 'warp', f'{ch2.CASTLE},52,22', {'map': ch2.CASTLE}),
    ('kiryl', 'walk', talk('up'), {'want': ['TALKED_KIRYL']}),
    ('brey_side', 'warp', f'{ch2.THRONE},24,26', {'map': ch2.THRONE, 'poke': HOLD_BREY}),
    ('brey', 'walk', talk('right'), {'want': ['TALKED_BREY'], 'poke': HOLD_BREY}),
    ('gate_side', 'warp', f'{ch2.CASTLE},28,48', {'map': ch2.CASTLE}),
    ('gate', 'walk', talk('down'), {'want': ['TALKED_GATE', 'READY']}),
    # 왕의 방 벽 앞에서 오른쪽을 보면 묻고, 예 → 걷어차 필드 산트하임 나오는 칸 (78,149)로. 필드 네 걸음째에 두
    # 사람이 합류한다. 필드에서도 7E:00BC·00BD 는 떠난 맵 번호 그대로라 끝 맵 대신 필드인지를 본다
    ('wall_side', 'warp', f'{ch2.BEDROOM},22,9', {'map': ch2.BEDROOM}),
    ('wall', 'walk', f'{ch2.WALL_STAND[0]},{ch2.WALL_STAND[1]};right:8;ask:600;cursor:0;' + taps(3, 60) + ';wait:400',
     {'want': ['KICKED'], 'field': True, 'cell': (78, 149)}),
    ('join', 'walk', 'down:120;wait:200;' + taps(8) + ';' + CLOSE, {'want': ['JOINED'], 'field': True}),
]
SEGMENTS += [seg for _, segs in dq4ch2checks.ordered(
    [('common', COMMON_SEGMENTS)] + dq4ch2checks.blocks('SEGMENTS', 'SEGMENT_BLOCKS'), ('common',)) for seg in segs]


def units(segments=None):
    """머리 뒤 구간을 묶음으로 나눈다: 순간이동 구간마다 새 묶음."""
    return cwk.units(SEGMENTS if segments is None else segments, HEAD)


def setup(first, segments=None, data=None):
    """first 번째 구간 앞까지 걸었다면 켜져 있을 flag·기록(SET)과 동료(PARTY). 머리 구간의 flag 는 2장 출발 상태에
    이미 있으므로 머리 뒤 구간만 센다. data(롬 바이트)가 없으면 기록 효과는 두지 않는다."""
    return cwk.setup(SEGMENTS if segments is None else segments, HEAD, first, FLAGS,
                     effects(data) if data is not None else {})


def head_key(mesence):
    """2장 출발 상태를 정하는 것: 서장 캐시 키(1장 검사·사건 코드·Lua·에뮬레이터)에 머리를 걷는 코드와 머리 구간·그
    시작 flag 를 더한다. 이 파일 전체를 넣지 않는 것은 사건 구간이 붙을 때마다 머리를 다시 걷지 않게 하려는 것이다."""
    return wc.code_key(mesence, inspect.getsource(head), repr(SEGMENTS[:HEAD]), CH1_BANK,
                       repr(wc.setup(wc.SEGMENTS, KING_INDEX)))


def head_effects():
    """머리 묶음 첫 구간에 둘 기록: 1장 검사의 것에 1장에 맡긴 것(CH1_BANK)을 더한다. setup 은 첫 구간 앞 구간의
    효과만 모으므로 왕 보고 바로 앞 구간에 붙인다."""
    effects = dict(wc.EFFECTS)
    before = wc.SEGMENTS[KING_INDEX - 1][0]
    effects[before] = {**effects.get(before, {}),
                       'set': ';'.join(v for v in (effects.get(before, {}).get('set'), CH1_BANK) if v)}
    return effects


def head(mesence, rom, data, out, cache=None):
    """2장 출발 상태와 머리 구간 결과. 서장은 dq4ch1walkcheck.prologue(캐시)로, 머리는 시드 0 으로 한 번만 걷는다."""
    key = head_key(mesence) if cache else None
    state = out / SEGMENTS[HEAD - 1][0] / 'end.mss'
    hit = cache.get('ch2-opening', key, '.mss', state) if cache else None
    if hit:
        return state, [{**r, 'cached': cache.path('ch2-opening', key, '.mss').name} for r in hit[1]['segments']]
    base, pro = wc.prologue(mesence, rom, data, out, wc.SEGMENTS, cache)
    if pro['status'] != 'passed':
        return None, [pro]
    # 1장 구간 표의 왕 보고 앞까지에 머리를 이어, 1장 묶음 걷기와 같은 flag·동료·같은 맵 들르기로 시작한다
    chain = wc.SEGMENTS[:KING_INDEX] + SEGMENTS[:HEAD]
    results = wc.walk_unit(mesence, rom, data, out, chain, list(range(KING_INDEX, KING_INDEX + HEAD)), base,
                           flags=FLAGS, effects=head_effects())
    if len(results) != HEAD or any(r['status'] != 'passed' for r in results):
        return None, results
    if cache:
        cache.put('ch2-opening', key, '.mss', state, {'segments': results})
    return state, results


def walk_unit(mesence, rom, data, out, unit, base, seed=0, segments=None):
    """한 묶음을 2장 출발 상태에서 걷는다."""
    return cwk.walk_unit(mesence, rom, data, out, unit, base, seed, SEGMENTS if segments is None else segments, HEAD,
                         FLAGS, effects, HOPS, battle_patch)


end_cell_problem, end_byte_problems, compare_runs = cwk.end_cell_problem, cwk.end_byte_problems, cwk.compare_runs


def main():
    return cwk.main(sys.modules[__name__], __doc__, 'dq4build.py --chapter2 의 롬',
                    '같은 롬으로 만든 2장 출발 상태(opening/end.mss). 주면 머리를 건너뜀')


if __name__ == '__main__':
    sys.exit(main())
