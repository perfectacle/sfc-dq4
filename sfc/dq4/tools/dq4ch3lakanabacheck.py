"""레이크나바 사건 검사(MesenCE 헤드리스): 네네의 잠, 무기점 일과 손님 갈래, 아래층에서 그만두기, 톰 노인 밀기, 톰 아들의
개, 필드에서 돌아오면 지워지는 flag 를 3장 출발 상태(dq4ch3walkcheck.head)에서 사례마다 따로 돌려 메시지 차례·flag·
금화·일삯·재고를 본다.

손님 갈래는 난수로 갈린다. 사례마다 롬 사본의 사건 네이티브를 문턱만 바꿔 다시 써서(파는 손님·사는 결과·흥정·r2 를
늘 참이나 늘 거짓으로) 갈래를 고르고, 「아니오」 가 필요한 값 물음(032D)은 그 대화 스크립트의 조건 05 를 뒤집어 A 만
눌러도 그 갈래로 가게 한다. 그래서 대사 길이와 상관없이 A 만 눌러 결정적으로 돈다. 바꾼 바이트가 문턱·조건 자리
밖이면 멈춘다.

  MESENCE=… LIBDIR=… uv run --locked python sfc/dq4/tools/dq4ch3lakanabacheck.py --rom work/ch3/dq4-ch1-full.sfc \\
      --messages work/ch3/messages.json --out work/ch3lakanaba [--only 이름,…] [--repeat 2] [--jobs 4]

롬은 dq4build.py --chapter3 의 출력, --messages 는 같은 빌드의 messages.json(메시지 번호를 글로 찾는다).
"""
import argparse
import concurrent.futures
import copy
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
import dq4ch3event as ch3  # noqa: E402
import dq4ch3lakanaba as L  # noqa: E402
from dq4ch1event import FC_DOG_PICTURE  # noqa: E402
from dq4npcport import PICTURES  # noqa: E402
from dq4ch3slots import VARS_AT  # noqa: E402


def _a(addr):
    return addr & 0xFFFF


FLAGS = {
    'L0': (0x7E2190 + 0x70, 0xFF), 'L1': (0x7E2190 + 0x71, 0xFF), 'T4': (L.TEMP, 0xFF),
    'COMMON': (0x7E2190 + ch3.DOG[0], 0xFF),
    'SCOTT_DAYS': (ch3.SCOTT_DAYS, 0xFF), 'LAWRENCE_DAYS': (ch3.LAWRENCE_DAYS, 0xFF),
    'STOCK0': (L.STOCK_AT, 0xFF), 'STOCK1': (L.STOCK_AT + 1, 0xFF), 'STOCK2': (L.STOCK_AT + 2, 0xFF),
    'WAGE0': (L.WAGE_AT, 0xFF), 'WAGE1': (L.WAGE_AT + 1, 0xFF), 'ITEM': (L.ITEM_AT, 0xFF),
    'GOLD0': (ch2.GOLD_AT, 0xFF), 'GOLD1': (ch2.GOLD_AT + 1, 0xFF), 'TIME0': (ch2.TIME_AT, 0xFF),
    'HP0': (ch2.PARTY_AT + 2, 0xFF), 'ITEM1': (ch2.PARTY_AT + 0x17, 0xFF),
    # 걷는 그림 수·둘째 그림(dq4ch1event 따라 걷는 그림)과 일행 기록 수(전투에 드는 수)
    'WALKERS': (0x7E1967, 0xFF), 'WALKER1': (0x7E1970, 0xFF), 'PARTY_N': (0x7E201D, 0xFF),
    # 낮 네네의 자리와 바로 전 방향(L.NENE_SLOT, L.NENE_LAST)
    'NENE_X': (0x7E3020 + L.NENE_SLOT, 0xFF), 'NENE_Y': (0x7E3080 + L.NENE_SLOT, 0xFF), 'NENE_LAST': (L.NENE_LAST, 0xFF),
}
DOG_PICTURE = PICTURES[FC_DOG_PICTURE]
TALK = 'a:8;wait:60'
CLOSE = wc.pc.CLOSE


def taps(n):
    return ';'.join([TALK] * n)


def _set(**values):
    """SET 글: 이름=값(FLAGS 의 칸)."""
    return ';'.join(f'{_a(FLAGS[k][0]):04X}={v:02X}' for k, v in values.items())


def _flags(*flags):
    out = {}
    for idx, mask in flags:
        out[idx] = out.get(idx, 0) | mask
    return out


L0 = lambda *f: _flags(*f).get(0x70, 0)  # noqa: E731
SEEN_SHIFT = L0(L.SEEN, L.SHIFT)
# 3장 출발 상태는 톨네코 집(3E/01). 집으로 순간이동하면 마을을 먼저 들른다(같은 맵 순간이동은 도착을 알아채지 못함)
HOP = ('hop', 'warp', f'{L.TOWN},4,26', {})
WORK_AT = f'{L.TOWN},{L.COUNTER_IN[0]},{L.COUNTER_IN[1] - 1}'      # 순간이동은 TO 한 셀 아래에 내린다
WAIT_CUSTOMER = 'wait:900;' + taps(14)                           # 손님 사이 400~700프레임(+걸어 들어옴)


def ask(answer):
    """예/아니오 물음 하나에 답한다(0 예, 1 아니오). 메시지 창과 예/아니오 창은 창 번호(7E:0A00)가 같아 until 로 가르지
    못한다. 커서는 예/아니오 창이 열려야 움직이므로, 먼저 반대쪽으로 옮겨 창이 열린 것을 잡고(앞 물음의 커서가 남아
    있으면 곧바로 지나가고 둘째 토큰이 창을 기다린다) 답 쪽으로 되돌려 A."""
    return f'cursor:{1 - answer};cursor:{answer};a:8'


# 말이 끝나면 창이 키를 기다린다. 닫고 손님이 다시 말을 걸어 창이 열릴 때까지
RETALK = 'wait:30;b:8;wait:30;until:600'


def work_case(variant, msgs, check, more=None, extra_set=None, maxf=3400, inputs=WAIT_CUSTOMER):
    """일하는 중(카운터 안)에서 손님 하나를 맞는다. check(seen) 는 끝 바이트로 본 문제 목록."""
    sets = {'L0': SEEN_SHIFT, **(extra_set or {})}
    return {'variant': variant,
            'steps': [('work', 'warp', WORK_AT, {'set': _set(**sets)}),
                      ('customer', 'walk', f'{inputs};{CLOSE}', {'maxf': maxf, **(more or {})})],
            'msgs': msgs, 'check': check}


def _wage(seen):
    return seen.get('WAGE0', 0) | seen.get('WAGE1', 0) << 8


def wage_is(mode):
    """일삯 = 일삯 표[값 칸][PICK](다음 손님이 들어와도 품목 칸은 같다)."""
    def check(seen):
        want = L.wages()[mode][PICK]
        return [] if _wage(seen) == want else [f'일삯 {_wage(seen)}, 기대 {want}(값 칸 {mode})']
    return check


def same(**want):
    def check(seen):
        return [f'{k} = {seen.get(k)}, 기대 {v}' for k, v in want.items() if seen.get(k) != v]
    return check


def all_of(*checks):
    return lambda seen: [p for c in checks for p in c(seen)]


SELLER = {'SELLER_BELOW': 0xFF}
BUYER = {'SELLER_BELOW': 0}
RESULT = {'no_money': (0xFF, 0xFF, 0xFF), 'full': (0, 0xFF, 0xFF), 'no_equip': (0, 0, 0xFF), 'sold': (0, 0, 0)}


# 사는 손님 품목은 どうのつるぎ(칸 1): 값 칸마다 일삯이 달라(6·5·13) 갈래를 가린다
PICK = 1


def buyer(result, **more):
    return {**BUYER, 'RESULT_BELOW': RESULT[result], 'BUYER_PICK': PICK, **more}


INTRO = ['is_shop', 'show']
CASES = {
    # 네네: 오늘 도시락 전(3장 처음)이면 잠 → 아침 → 도시락 말. HP 를 낮춰 두면 채워진다. 날수 + 1
    # 잠은 톰 노인 flag 도 지운다(FC 15:$9F79)
    'nene_sleep': {'steps': [HOP, ('house', 'warp', f'{L.HOUSE},54,6',
                                   {'poke': L.NENE_HOLD, 'set': '2042=05;' + _set(L0=L0(L.TOM_DONE))}),
                             ('talk', 'walk', f'{wc.talk("down", 10)}', {'maxf': 2400, 'poke': L.NENE_HOLD})],
                   'msgs': ['home', 'goodnight', 'morning', 'bento'],
                   'check': same(SCOTT_DAYS=1, LAWRENCE_DAYS=1, TIME0=0x50, HP0=20, ITEM1=L.BENTO,
                                 L0=L0(L.BENTO_TODAY))},
    # 낮 네네는 FC 블록 2B 처럼 집 안 칸(L.NENE_CELLS)만 한 걸음씩 돌아다닌다: 칸 표 안에 있고 바로 전 방향이 남는다
    'nene_walk': {'steps': [HOP, ('house', 'warp', f'{L.HOUSE},60,16', {}),
                            ('wait', 'walk', 'wait:1500', {'maxf': 1600})],
                  'msgs': [], 'check': lambda s: _nene_walked(s)},
    'nene_forgot': {'steps': [HOP, ('house', 'warp', f'{L.HOUSE},54,6', {'poke': L.NENE_HOLD,
                                                                        'set': _set(L0=L0(L.BENTO_TODAY))}),
                              ('talk', 'walk', f'{wc.talk("down", 3)}', {'maxf': 1200, 'poke': L.NENE_HOLD})],
                    'msgs': ['forgot'], 'check': same(SCOTT_DAYS=0)},
    # 첫 출근: 문 밖에 서면 꾸지람 → 카운터 안으로 걸려 들어가 031D
    'first_day': {'steps': [('door', 'warp', f'{L.TOWN},20,52', {}),
                            ('scold', 'walk', f'16,53;{taps(6)};{CLOSE}', {'maxf': 1600, 'cell': L.COUNTER_IN})],
                  'msgs': ['late', 'how'], 'check': same(L0=SEEN_SHIFT)},
    # 둘째 날부터: 카운터 안 주인에게 「예」
    'second_day': {'steps': [('inside', 'warp', f'{L.TOWN},4,50', {'set': _set(L0=L0(L.SEEN))}),
                             ('ask', 'walk', f'{wc.talk("down", 12)}', {'maxf': 1600, 'cell': L.COUNTER_IN})],
                   'msgs': ['work', 'how'], 'check': same(L0=SEEN_SHIFT)},
    'across': {'steps': [('front', 'warp', f'{L.TOWN},8,52', {'set': _set(L0=L0(L.SEEN))}),
                         ('ask', 'walk', f'{wc.talk("left", 4)}', {'maxf': 1000})],
               'msgs': ['across', 'customer_ok'], 'check': same(L0=L0(L.SEEN))},
    # 손님 갈래(문턱을 바꾼 롬 사본). 파는 손님 はじゃのつるぎ: 금화·일삯 그대로, 재고 + 1
    'seller': work_case({**SELLER, 'HAJA_BELOW': 0xFF}, ['is_shop', 'sell_ask', 'offer', 'sold_to'],
                        same(STOCK2=1, GOLD0=0, WAGE0=0, ITEM=L.MODE_SELLER << 4 | L.HAJA)),
    'sold': work_case(buyer('sold'), INTRO + ['buy', 'bought'], wage_is(0)),
    'no_money': work_case(buyer('no_money'), INTRO + ['buy', 'no_money'], same(WAGE0=0)),
    'full': work_case(buyer('full'), INTRO + ['buy', 'full'], same(WAGE0=0)),
    'no_equip': work_case(buyer('no_equip'), INTRO + ['buy', 'no_equip', 'gift'], wage_is(0)),
    # 값 물음에 「아니오」(조건을 뒤집음): 깎음 「예」 → 팜(깎은 값 >> 4), 웃돈 「예」 r2 < 40 → 0332(웃돈 >> 3)
    'discount': work_case(buyer('sold', DISCOUNT_BELOW=0xFF, flip_buy=True), INTRO + ['buy', 'discount', 'bought'],
                          wage_is(1)),
    'raise': work_case(buyer('sold', DISCOUNT_BELOW=0, RAISE_BELOW=0xFF, LUCK40_BELOW=0xFF, flip_buy=True),
                       INTRO + ['buy', 'raise', 'raise_ok'], wage_is(2)),
    # 물건을 보여 달라는 말(032B)에 「아니오」 면 032C 를 「예」 까지 되풀이한다. 둘째 032C 는 손님이 다시 말을 걸어 묻는다
    'joke': work_case(buyer('sold'), INTRO + ['joke', 'joke', 'joke', 'buy', 'bought'], wage_is(0),
                      inputs=';'.join(['until:900', ask(0), ask(1), ask(1), RETALK, ask(1), RETALK, ask(0), RETALK,
                                       ask(0), taps(6)])),
    'no_deal': work_case(buyer('sold', DISCOUNT_BELOW=0, RAISE_BELOW=0, LUCK_BELOW=0xFF, flip_buy=True),
                         INTRO + ['buy', 'no_thanks'], same(WAGE0=0)),
    # 일삯이 100 을 넘으면 가게를 닫는다: 0341, 금화 + 일삯, 밤, 무기점 문 앞
    'closing': work_case(buyer('sold'), INTRO + ['buy', 'bought', 'closing'],
                         lambda s: ([] if s.get('L0', 0) & L.DONE[1] else ['오늘 일 마침 꺼짐']) +
                                   ([] if s.get('TIME0') == L.NIGHT_TIME else [f"시각 {s.get('TIME0')}"]) +
                                   ([] if _wage(s) == 0 else ['일삯이 남음']) +
                                   ([] if s.get('GOLD0', 0) == 95 + L.wages()[0][PICK] else
                                    [f"금화 {s.get('GOLD0')}"]),
                         more={'cell': L.SHOP_DOOR}, extra_set={'WAGE0': 95}, maxf=3800),
    # 첫날(맵을 첫 출근 전에 불러옴)에도 일삯이 100 을 넘으면 주인이 걸어 나와 가게를 닫는다
    'first_close': {'variant': buyer('sold'),
                    'steps': [('door', 'warp', f'{L.TOWN},20,52', {'set': _set(WAGE0=95)}),
                              ('scold', 'walk', f'16,53;{taps(6)};{CLOSE}', {'maxf': 1600, 'cell': L.COUNTER_IN}),
                              ('customer', 'walk', f'{WAIT_CUSTOMER};{CLOSE}', {'maxf': 3800, 'cell': L.SHOP_DOOR})],
                    'msgs': ['late', 'how', *INTRO, 'buy', 'bought', 'closing'],
                    'check': lambda s: ([] if s.get('TIME0') == L.NIGHT_TIME else [f"시각 {s.get('TIME0')}"]) +
                                       ([] if s.get('L0', 0) & L.DONE[1] else ['오늘 일 마침 꺼짐'])},
    # 아래층 주인에게 그만두기: 일삯을 금화로, 오늘 일 마침
    'quit': {'steps': [('cellar', 'warp', f'{L.CELLAR},14,10', {'set': _set(L0=SEEN_SHIFT, WAGE0=50)}),
                       ('ask', 'walk', f'{wc.talk("up", 6)}', {'maxf': 1400})],
             'msgs': ['quit_ask', 'quit_pay', 'tomorrow'], 'check': same(GOLD0=50, WAGE0=0, L0=SEEN_SHIFT | L.DONE[1])},
    # 톰 노인: 「예」 뒤 밀리는 인물이 되어 아래로 밀면 따라 움직인다(TOMY). 교회까지 미는 긴 길은 돌아다니는 마을 사람에
    # 따라 막혀 갈래가 생기므로, 마을을 다시 불러와 톰을 교회 문 안 (28,17) 에 옮겨 두고 위로 밀어 교회 안에 닿게 한다.
    # 교회에 닿으면 03AE, 2~12 골드(난수), 밀기 끝
    'tom': {'steps': [('tom', 'warp', f'{L.TOWN},48,24', {}),
                      ('ask', 'walk', f'{wc.talk("up", 5)}', {'maxf': 1200}),
                      ('push', 'walk', '50,25;50,21;48,21;48,25', {'maxf': 1200, 'tom_y': 0x1B}),
                      ('house', 'warp', f'{L.HOUSE},60,16', {}), ('church', 'warp', f'{L.TOWN},28,18', {}),
                      ('push_in', 'walk', f'28,13;wait:60;{taps(3)};{CLOSE}', {'maxf': 1500, 'tom_at': (28, 17)})],
            'msgs': ['tom_hello', 'tom_ask', 'tom_go', 'tom_church'],
            'check': lambda s: ([] if L.TOM_GOLD[0] <= s.get('GOLD0', 0) < sum(L.TOM_GOLD) else
                                [f"금화 {s.get('GOLD0')}"]) +
                               ([] if s.get('L0', 0) & 0x60 == L.TOM_DONE[1] else [f"톰 flag {s.get('L0')}"])},
    # 아들이 돌아온 뒤(SON_FREED) 톰의 첫마디는 0844(FC 15:$860D)
    'tom_back': {'steps': [('tom', 'warp', f'{L.TOWN},48,24',
                            {'set': f'{0x2190 + L.SON_FREED[0]:04X}={L.SON_FREED[1]:02X}'}),
                           ('ask', 'walk', f'{wc.talk("up", 5)}', {'maxf': 1200})],
                 'msgs': ['tom_glad', 'tom_ask', 'tom_go'], 'check': lambda s: []},
    # 톰 아들(본몰 감옥에서 풀려난 뒤에만 섬): 개를 빌려줌(DOG). 마을을 다시 불러오면 우리의 개가 없다(아래 dog_gone)
    'son': {'steps': [('son', 'warp', f'{L.TOWN},46,8', {'set': f'{0x2190 + L.SON_FREED[0]:04X}={L.SON_FREED[1]:02X}'}),
                      # 빌리면 개가 우리에서 아들 옆까지 걸어와 짖고(02F1) 아들이 03AD. 개가 닿아야 조작이 풀린다
                      ('ask', 'walk', f'{wc.talk("up", 5)};{taps(4)};{CLOSE}', {'maxf': 2000}),
                      ('leave', 'walk', '46,13', {'maxf': 600, 'cell': (46, 13)}),
                      ('house', 'warp', f'{L.HOUSE},60,16', {}), ('town', 'warp', f'{L.TOWN},46,8', {})],
            # 개는 걷는 줄 끝(톨네코 뒤)에 붙고 일행 기록에는 들지 않는다(FC: 걷는 줄 칸, 전투 목록에 없음)
            'msgs': ['son_lend', 'dog_bark', 'son_dog'], 'check': lambda s: ([] if s.get('COMMON', 0) & ch3.DOG[1] else ['DOG 꺼짐']) +
                                                  same(WALKERS=2, WALKER1=DOG_PICTURE, PARTY_N=1)(s),
            'dog_gone': True},
    # 여우를 쫓은 뒤(본몰 FOXED) 개를 데리고 아들에게: 「예」 면 돌려줌(DOG 끔, DOG_BACK)
    'son_return': {'steps': [('son', 'warp', f'{L.TOWN},46,8',
                              {'set': f'{0x2190 + L.FOXED[0]:04X}={L.FOXED[1] | L.SON_FREED[1]:02X};'
                                      f'{_a(FLAGS["COMMON"][0]):04X}={ch3.DOG[1]:02X}'}),
                             ('ask', 'walk', f'{wc.talk("up", 6)};{CLOSE}', {'maxf': 1400}),
                             # 돌려준 개가 줄 끝 자리에서 우리로 걸어가 닿아야 조작이 풀린다
                             ('leave', 'walk', '44,9;44,13', {'maxf': 900, 'cell': (44, 13)})],
                   'msgs': ['son_return', 'son_thanks', 'son_luck'],
                   'check': same(COMMON=0, L0=L0(L.DOG_BACK), WALKERS=1)},
    # 필드에서 마을로 들면 오늘 도시락·출근 flag 가 꺼진다(FC 는 필드로 나갈 때 $6285 를 지움)
    'field': {'steps': [('side', 'warp', f'{L.TOWN},4,26', {'set': _set(L0=L0(L.BENTO_TODAY, L.SHIFT, L.SEEN))}),
                        ('out', 'walk', 'left:64', {'field': True, 'poke': wc.DAY}),
                        ('in', 'walk', '208,73', {'map': L.TOWN, 'field': False, 'cell': (0, 27), 'poke': wc.DAY})],
              'msgs': [], 'check': same(L0=L0(L.SEEN))},
}


def _nene_walked(seen):
    x, y = seen.get('NENE_X', 0) & 0x7F, seen.get('NENE_Y', 0) & 0x7F
    cell = (x >> 1, (y - 1) >> 1)
    # 바로 전 방향(bit7)은 맵에 들 때 지워지고 한 걸음 걸어야 남는다. 자리는 걷다가 첫 칸에 돌아와 있을 수도 있다
    return ([] if cell in L.NENE_CELLS else [f'네네 FC 칸 {cell} 이 집 칸 표 밖']) + \
        ([] if seen.get('NENE_LAST', 0) & 0x80 else ['바로 전 방향이 남지 않음(걷지 않음)'])


def message_ids(messages_path):
    """{메시지 이름: 번호}: 같은 빌드의 messages.json 에서 이 모듈(SLOTS 키 L) 메시지가 놓인 번호(dq4msglabels.named: 사건
    메시지 자리를 정하고 그 자리에 모듈 메시지가 놓였는지 본다). 다른 모듈에 같은 글이 있어도 이름으로 갈린다."""
    import dq4msglabels
    names = dq4msglabels.named(dq4msglabels.load(messages_path))
    out = {label.split('.', 2)[2]: i for i, label in names.items() if label.startswith('ch3.L.')}
    if set(out) != set(L.MESSAGES):
        raise SystemExit(f'{messages_path}: 이 모듈 메시지 이름이 맞지 않음(롬과 같은 빌드인지)')
    return {name: out[name] for name in L.MESSAGES}

def context(ids):
    first = ids[next(iter(L.MESSAGES))] - len(ch3.MESSAGES)
    for ctx in ch3.contexts(first):
        if ctx.module is L:
            return ctx
    raise SystemExit('dq4ch3lakanaba 가 등록되지 않음')


THRESHOLDS = ('SELLER_BELOW', 'HAJA_BELOW', 'RESULT_BELOW', 'DISCOUNT_BELOW', 'RAISE_BELOW', 'LUCK_BELOW',
              'LUCK40_BELOW', 'BUYER_PICK')


def variant_rom(data, ctx, variant):
    """문턱(THRESHOLDS)을 바꿔 다시 쓴 사건 네이티브와, flip_buy 면 값 물음 조건을 뒤집은 사는 손님 대화를 얹은 롬."""
    import dq4chapter1
    import dq5talkwrite
    d = bytearray(data)
    keep = {k: getattr(L, k) for k in THRESHOLDS}
    code, _ = L.native(ctx)
    o = dq4chapter1.lorom(ctx.code_at)
    if bytes(d[o:o + len(code)]) != code:
        raise SystemExit(f'{ctx.code_at:06X}: 롬의 레이크나바 네이티브가 이 도구로 만든 것과 다름(다른 빌드?)')
    try:
        for k, v in variant.items():
            if k in THRESHOLDS:
                setattr(L, k, v)
        more, _ = L.native(ctx)
    finally:
        for k, v in keep.items():
            setattr(L, k, v)
    if len(more) != len(code):
        raise SystemExit('문턱을 바꾼 네이티브의 길이가 다름')
    d[o:o + len(more)] = more
    if variant.get('flip_buy'):
        k = L.TALKS.index('buyer')
        plain = dq5talkwrite.encode_script(L.talk_scripts(ctx)[k], 'buyer')
        flipped = dq5talkwrite.encode_script(L.talk_scripts(ctx, flip_buy=True)[k], 'buyer')
        diff = [i for i in range(len(plain)) if plain[i] != flipped[i]]
        at = [i for i in range(len(d) - len(plain)) if d[i:i + len(plain)] == plain]
        if len(plain) != len(flipped) or len(diff) != 1 or len(at) != 1:
            raise SystemExit(f'사는 손님 대화의 값 물음 조건을 찾지 못함(다른 바이트 {diff}, 자리 {len(at)})')
        d[at[0] + diff[0]] = flipped[diff[0]]
    return bytes(d)


def tom_slot(wram_path, talk):
    """순간이동 끝 WRAM 의 인물 표에서 톰(대화 번호 talk)의 슬롯."""
    if not wram_path.exists():
        return None
    w = wram_path.read_bytes()
    found = [k for k in range(8, 0x20) if w[0x36E0 + k] == talk & 0xFF and w[0x3700 + k] & 0x0F == talk >> 8]
    return found[0] if found else None


def run_case(mesence, data, base, ctx, ids, name, dest, seed):
    case = CASES[name]
    dest.mkdir(parents=True, exist_ok=True)
    rom = dest / 'c.sfc'
    rom.write_bytes(variant_rom(data, ctx, case.get('variant', {})))
    state, seen, messages, problems = base, {}, [], []
    flags, tom = dict(FLAGS), None
    for seg in case['steps']:
        seg_name, how, arg, opt = seg
        opt = dict(opt)
        more = opt.pop('set', '')
        tom_y, tom_at = opt.pop('tom_y', None), opt.pop('tom_at', None)
        if tom_at is not None:
            more = ';'.join(v for v in (more, f'{0x3020 + tom:04X}={tom_at[0]:02X};{0x3080 + tom:04X}={tom_at[1]:02X}') if v)
        r = wc.segment(mesence, rom, state, dest / seg_name, (seg_name, how, arg, opt), wc.NO_ENCOUNTERS, more, '',
                       seed, flags=flags)
        if how == 'warp':
            tom = tom_slot(dest / seg_name / 'final.wram', ctx.talk['tom'])
            flags['TOMY'] = (0x7E3080 + tom, 0xFF) if tom is not None else flags.get('TOMY', FLAGS['L0'])
        messages += [m for m in r.get('messages', []) if m != '129']
        problems += [f'{seg_name}: {p}' for p in r['problems']]
        if how == 'walk':
            import dq4chapterwalk as cwk
            problems += [f'{seg_name}: {p}' for p in filter(None, [cwk.end_cell_problem(dest / seg_name, seg)])]
            log = dest / seg_name / 'walk.txt'
            import re
            seen = {k: int(v, 16) for k, v in re.findall(r'^(\w+)=([0-9A-F]+)$', log.read_text(encoding='utf-8'), re.M)} \
                if log.exists() else {}
            if tom_y is not None and seen.get('TOMY') != tom_y:
                problems.append(f"{seg_name}: 톰 Y {seen.get('TOMY')}, 기대 {tom_y}(밀려 내려옴)")
        state = dest / seg_name / 'end.mss'
        if not state.exists():
            break
    want = [f'{ids[n]:X}' for n in case['msgs']]
    got = [m.upper().lstrip('0') or '0' for m in messages]
    pos = 0
    for w in want:
        try:
            pos = got.index(w, pos) + 1
        except ValueError:
            problems.append(f'메시지 {w}({[n for n in case["msgs"] if f"{ids[n]:X}" == w][0]}) 가 차례대로 뜨지 않음: {got}')
            break
    problems += case['check'](seen)
    if case.get('dog_gone'):
        wram = dest / case['steps'][-1][0] / 'final.wram'
        w = wram.read_bytes() if wram.exists() else b''
        there = [s for s in range(8, 0x20) if w and (w[0x3020 + s], w[0x3080 + s]) in (L.DOG, L.DOG_HOME)
                 and not w[0x3380 + s] & 0x80]
        if there:
            problems.append(f'개가 우리에 남음(슬롯 {there})')
    return {'name': name, 'status': 'failed' if problems else 'passed', 'problems': problems, 'messages': got,
            'bytes': {k: seen[k] for k in sorted(seen) if k in FLAGS}}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', required=True, type=Path)
    ap.add_argument('--messages', required=True, type=Path, help='같은 빌드의 messages.json')
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--base', type=Path, help='같은 롬의 3장 출발 상태. 주면 머리를 건너뜀')
    ap.add_argument('--only', help='이 사례만(쉼표로 여럿)')
    ap.add_argument('--jobs', type=int, default=4)
    ap.add_argument('--repeat', type=int, default=1, choices=(1, 2), help='2 면 두 번 돌려 메시지·바이트를 견줌')
    wc.add_seed_args(ap)
    args = ap.parse_args()
    seeds = wc.seeds_of(args)
    names = args.only.split(',') if args.only else list(CASES)
    unknown = [n for n in names if n not in CASES]
    if unknown:
        raise SystemExit(f'없는 사례: {unknown}')
    mesence = Path(os.environ['MESENCE'])
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f'{out} is not empty')
    out.mkdir(parents=True, exist_ok=True)
    rom = out / 'c.sfc'
    shutil.copyfile(args.rom.resolve(), rom)
    data = rom.read_bytes()
    ids = message_ids(args.messages)
    ctx = context(ids)
    began = time.monotonic()
    if args.base:
        base, head = args.base.resolve(), []
    else:
        import dq4ch3walkcheck
        cache = None if args.no_state_cache else wc.StateCache(data)
        base, head = dq4ch3walkcheck.head(mesence, rom, data, out, cache, repeat=args.repeat)
        for r in head:
            print(json.dumps(r, ensure_ascii=False), flush=True)
    results = []
    if base is not None:
        jobs = [(n, seed, k) for seed in seeds for n in names for k in range(1, args.repeat + 1)]
        with concurrent.futures.ThreadPoolExecutor(max(1, args.jobs)) as pool:
            futures = {pool.submit(run_case, mesence, data, base, ctx, ids, n,
                                   wc.seed_dir(out, seed, seeds) / (f'run-{k}' if args.repeat > 1 else '') / n, seed):
                       (n, seed, k) for n, seed, k in jobs}
            for f in concurrent.futures.as_completed(futures):
                n, seed, k = futures[f]
                r = {**f.result(), 'seed': seed, 'run': k}
                print(json.dumps(r, ensure_ascii=False), flush=True)
                results.append(r)
    problems = [] if base is not None else ['3장 출발 상태를 만들지 못함']
    problems += [f"{r['seed']}:{r['run']}:{r['name']} {p}" for r in results for p in r['problems']]
    if args.repeat > 1:
        by = {(r['seed'], r['name'], r['run']): r for r in results}
        for (seed, name, run), r in by.items():
            other = by.get((seed, name, 2))
            if run == 1 and other and (r['messages'], r['bytes']) != (other['messages'], other['bytes']):
                problems.append(f'{seed}:{name} 두 번 돌린 기록이 다름')
    ok = not problems and len(results) == len(names) * len(seeds) * args.repeat
    report = {'status': 'passed' if ok else 'failed', 'seconds': round(time.monotonic() - began), 'head': head,
              'problems': problems, 'results': sorted(results, key=lambda r: (r['seed'], r['name'], r['run']))}
    (out / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n')
    print(json.dumps({'status': report['status'], 'seconds': report['seconds'], 'problems': problems},
                     ensure_ascii=False))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
