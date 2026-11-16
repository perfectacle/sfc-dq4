"""3장 엔돌 사건(dq4ch3endor)의 대화 갈래를 MesenCE 헤드리스로 걸어 메시지 차례·flag 를 본다.

이야기 차례의 큰 길(왕 첫 알현 → 허락 → 가게 사기 → 주문 → 네네 → 납품 → 여신상 팔기 → 동굴 단추)은 3장 걷기 검사
(dq4ch3walkcheck 의 endor_* 구간)가 flag·금화·물건·맵으로 본다. 이 검사는 같은 틀(3장 출발 상태에서 묶음마다 따로,
dq4chapterwalk)로 「아니요」 갈래와 flag 마다 다른 첫 말을 걷고, 묶음 첫 구간의 SET 으로 그 갈래의 flag 를 둔 뒤 구간마다
띄운 메시지가 MESSAGES 의 차례로 시작하는지 본다(걷기 검사는 메시지 번호를 견주지 않음).

  MESENCE=… LIBDIR=… python sfc/dq4/tools/dq4ch3endorcheck.py --rom work/ch3/dq4-ch1-full.sfc --out work/ch3endor
  (--only 구간,… · --repeat 2 · --seeds 는 dq4ch3walkcheck 와 같다)
"""
import json
import sys
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4ch1walkcheck as wc  # noqa: E402
import dq4ch3endor as endor  # noqa: E402
import dq4ch3event as ch3  # noqa: E402
import dq4ch3walkcheck as walk  # noqa: E402
import dq4chapterwalk as cwk  # noqa: E402

CLOSE = wc.pc.CLOSE
_set, _items, _below, _gold = walk._set, walk._items, walk._below, walk._gold
talk = wc.talk
# 3장 출발 상태의 엔돌 flag 를 모두 끄고 갈래의 flag 만 켠다
CLEAR = f'{0x2190 + endor.IDX:04X}=00;{0x2190 + endor.IDX2:04X}=00'


def talk_no(face, before, after):
    """그 쪽을 보고 말을 건 뒤 A 를 before 번 눌러 물음에 닿고, 「아니요」(아래)를 고른 다음 A 를 after 번(남은 쪽 수.
    더 누르면 다시 말을 걸어 갈래가 섞인다)."""
    return (f'{face}:8;wait:30;a:8;wait:60;a:8;wait:60;{wc.taps(before, 90)};wait:150;down:8;wait:30;'
            f'{wc.taps(after, 90)};{CLOSE}')


def sets(*flags, more=()):
    return ';'.join((CLEAR, *(_set(f) for f in flags), *more))


def COUNT_SET(v):
    return f'{walk.FLAGS["ENDOR_COUNT"][0] & 0xFFFF:04X}={v:02X}'


# 맡긴 물건(7E:2250 + 물건 번호)에만 칼·갑옷 하나씩
BAG_SET = f'{(ch3.BAG & 0xFFFF) + endor.STEEL_SWORD:04X}=01;{(ch3.BAG & 0xFFFF) + endor.IRON_ARMOR:04X}=01'
RNG_PIN = '7E075B=00;7E075C=00;7E075D=00'
SELLER_NIGHT = endor.SELLER[1][2]                     # 밤의 가게 주인(05,02). 그 아래에서 말을 건다
NENE_NIGHT = endor.NENE[1][2]                          # 밤의 네네(04/08 (03,03))
SON_NIGHT = endor.SON[1][2]
GUIDE = endor.GUIDE[2]
COLLECTOR_NIGHT = endor.COLLECTORS[1][2]

# (이름, 방법, 인자, 선택): dq4ch3walkcheck.SEGMENTS 와 같은 꼴. 순간이동 구간마다 묶음이고, 묶음 첫 구간 set 이 flag 를 둔다
SEGMENTS = [
    ('king_no_side', 'warp', _below(endor.THRONE, endor.KING[2]), {'map': endor.THRONE, 'set': sets()}),
    ('king_no', 'walk', talk_no('up', 1, 1), {'map': endor.THRONE, 'off': ['ENDOR_ALLOWED']}),
    ('king_wait_side', 'warp', _below(endor.THRONE, endor.KING[2]),
     {'map': endor.THRONE, 'set': sets(endor.LETTER1)}),
    ('king_wait', 'walk', talk('up', 3), {'map': endor.THRONE, 'off': ['ENDOR_ALLOWED']}),
    ('king_done_side', 'warp', _below(endor.THRONE, endor.KING[2]),
     {'map': endor.THRONE, 'set': sets(endor.SHOP, endor.DELIVERED)}),
    ('king_done', 'walk', talk('up', 4), {'map': endor.THRONE}),
    ('seller_no_side', 'warp', _below(endor.SHOP_UP, endor.SELLER[0][2]),
     {'map': endor.SHOP_UP, 'set': sets(endor.ALLOWED, more=(_gold(endor.SHOP_PRICE),))}),
    ('seller_no', 'walk', talk_no('up', 3, 1), {'map': endor.SHOP_UP, 'off': ['ENDOR_SHOP'],
                                              'bytes': {'GOLD0': 0xB8, 'GOLD1': 0x88}}),
    # 밤: 가게를 산 뒤 위층에는 아들과 네네. 네네는 「늦게까지 수고」 뒤 잠(아침, 마을의 네네 옆)
    ('son_night_side', 'warp', _below(endor.SHOP_UP, SON_NIGHT),
     {'map': endor.SHOP_UP, 'set': sets(endor.SHOP), 'poke': wc.NIGHT}),
    ('son_night', 'walk', talk('up', 2), {'map': endor.SHOP_UP, 'poke': wc.NIGHT}),
    ('nene_night_side', 'warp', _below(endor.SHOP_UP, NENE_NIGHT),
     {'map': endor.SHOP_UP, 'set': sets(endor.SHOP), 'poke': wc.NIGHT}),
    ('nene_night', 'walk', talk('up', 6), {'poke': wc.NIGHT, 'map': endor.TOWN, 'cell': endor.NENE_SIDE[1], 'changes': 1, 'after': 600}),
    ('nene_no_side', 'warp', f'{endor.TOWN},{endor.NENE_SIDE[1][0]},{endor.NENE_SIDE[1][1] - 1}',
     {'map': endor.TOWN, 'set': sets(endor.SHOP)}),
    ('nene_no', 'walk', talk_no('right', 0, 2), {'map': endor.TOWN}),
    ('nene_lie_side', 'warp', f'{endor.TOWN},{endor.NENE_SIDE[1][0]},{endor.NENE_SIDE[1][1] - 1}',
     {'map': endor.TOWN, 'set': sets(endor.SHOP, endor.NOTICE)}),
    ('nene_lie', 'walk', talk_no('right', 2, 5), {'map': endor.TOWN, 'want': ['ENDOR_OPENED']}),
    # 납품: 주문 전·「아니요」·다 채운 뒤. 안내하는 옆 사람도 셋
    ('deliver_idle_side', 'warp', _below(endor.CASTLE_HALL, endor.DELIVER[2]),
     {'map': endor.CASTLE_HALL, 'set': sets()}),
    ('deliver_idle', 'walk', talk('up', 2), {'map': endor.CASTLE_HALL}),
    ('deliver_no_side', 'warp', _below(endor.CASTLE_HALL, endor.DELIVER[2]),
     {'map': endor.CASTLE_HALL, 'set': sets(endor.ORDER, more=(_items(endor.STEEL_SWORD),))}),
    ('deliver_no', 'walk', talk_no('up', 0, 4),
     {'map': endor.CASTLE_HALL, 'bytes': {'ENDOR_COUNT': 0}, 'items': [0x42, walk.BENTO, endor.STEEL_SWORD]}),
    # FC 15:$A118 실측 갈래: 가진 것이 없음, 칼만, 넘침(남은 수보다 많이 가짐 → 남은 만큼만 받고 다 참), 맡긴 물건뿐,
    # 갑옷은 다 찼고 칼 하나(남은 갑옷 줄이 빠짐)
    ('deliver_empty_side', 'warp', _below(endor.CASTLE_HALL, endor.DELIVER[2]),
     {'map': endor.CASTLE_HALL, 'set': sets(endor.ORDER)}),
    ('deliver_empty', 'walk', talk('up', 7), {'map': endor.CASTLE_HALL, 'bytes': {'ENDOR_COUNT': 0}}),
    ('deliver_one_side', 'warp', _below(endor.CASTLE_HALL, endor.DELIVER[2]),
     {'map': endor.CASTLE_HALL, 'set': sets(endor.ORDER, more=(_items(endor.STEEL_SWORD),))}),
    ('deliver_one', 'walk', talk('up', 8), {'map': endor.CASTLE_HALL, 'bytes': {'ENDOR_COUNT': 0x01},
                                            'items': [0x42, walk.BENTO]}),
    ('deliver_over_side', 'warp', _below(endor.CASTLE_HALL, endor.DELIVER[2]),
     {'map': endor.CASTLE_HALL,
      'set': sets(endor.ORDER, more=(_items(*[endor.STEEL_SWORD] * 4, endor.IRON_ARMOR), _gold(0), COUNT_SET(0x64)))}),
    ('deliver_over', 'walk', talk('up', 8), {'map': endor.CASTLE_HALL, 'want': ['ENDOR_DELIVERED'],
                                             'bytes': {'ENDOR_COUNT': 0x77, 'GOLD0': 0x60, 'GOLD1': 0xEA},
                                             'items': [0x42, walk.BENTO, endor.STEEL_SWORD]}),
    ('deliver_bag_side', 'warp', _below(endor.CASTLE_HALL, endor.DELIVER[2]),
     {'map': endor.CASTLE_HALL, 'set': sets(endor.ORDER, more=(BAG_SET,))}),
    ('deliver_bag', 'walk', talk('up', 7), {'map': endor.CASTLE_HALL, 'bytes': {'ENDOR_COUNT': 0}}),
    ('deliver_armors_full_side', 'warp', _below(endor.CASTLE_HALL, endor.DELIVER[2]),
     {'map': endor.CASTLE_HALL, 'set': sets(endor.ORDER, more=(_items(endor.STEEL_SWORD), COUNT_SET(0x70)))}),
    ('deliver_armors_full', 'walk', talk('up', 7), {'map': endor.CASTLE_HALL, 'bytes': {'ENDOR_COUNT': 0x71}}),
    ('deliver_done_side', 'warp', _below(endor.CASTLE_HALL, endor.DELIVER[2]),
     {'map': endor.CASTLE_HALL, 'set': sets(endor.ORDER, endor.DELIVERED)}),
    ('deliver_done', 'walk', talk('up', 1), {'map': endor.CASTLE_HALL}),
    ('guide_idle_side', 'warp', _below(endor.CASTLE_HALL, GUIDE), {'map': endor.CASTLE_HALL, 'set': sets()}),
    ('guide_idle', 'walk', talk('up', 1), {'map': endor.CASTLE_HALL}),
    ('guide_order_side', 'warp', _below(endor.CASTLE_HALL, GUIDE),
     {'map': endor.CASTLE_HALL, 'set': sets(endor.ORDER)}),
    ('guide_order', 'walk', talk('up', 2), {'map': endor.CASTLE_HALL}),
    ('guide_done_side', 'warp', _below(endor.CASTLE_HALL, GUIDE),
     {'map': endor.CASTLE_HALL, 'set': sets(endor.ORDER, endor.DELIVERED)}),
    ('guide_done', 'walk', talk('up', 2), {'map': endor.CASTLE_HALL}),
    # 수집가(밤에 서 있는 자리): 여신상이 없을 때·「아니요」·판 뒤
    ('collector_none_side', 'warp', _below(endor.COLLECTOR, COLLECTOR_NIGHT),
     {'map': endor.COLLECTOR, 'set': sets(), 'poke': wc.NIGHT}),
    ('collector_none', 'walk', talk('up', 3), {'map': endor.COLLECTOR, 'poke': wc.NIGHT}),
    ('collector_no_side', 'warp', _below(endor.COLLECTOR, COLLECTOR_NIGHT),
     {'map': endor.COLLECTOR, 'set': sets(more=(_items(endor.STATUE),)), 'poke': wc.NIGHT}),
    ('collector_no', 'walk', talk_no('up', 1, 1), {'poke': wc.NIGHT, 'map': endor.COLLECTOR, 'off': ['ENDOR_SOLD'],
                                                 'items': [0x42, walk.BENTO, endor.STATUE]}),
    ('collector_after_side', 'warp', _below(endor.COLLECTOR, COLLECTOR_NIGHT),
     {'map': endor.COLLECTOR, 'set': sets(endor.SOLD), 'poke': wc.NIGHT}),
    ('collector_after', 'walk', talk('up', 3), {'map': endor.COLLECTOR, 'poke': wc.NIGHT}),
    # 낮의 수집가: 걸어 다녀서 난수(7E:075B~075D)를 매 프레임 묶어 시드와 상관없이 같은 길을 걷게 한다. 들어선 뒤 한 칸
    # 왼쪽으로 옮겨 가는 자리 아래에서 말을 건다
    ('collector_day_side', 'warp', _below(endor.COLLECTOR, endor.COLLECTORS[0][2]),
     {'map': endor.COLLECTOR, 'set': sets(), 'poke': f'{wc.DAY};{RNG_PIN}'}),
    ('collector_day', 'walk', f"10,9;{talk('up', 3)}", {'map': endor.COLLECTOR, 'poke': f'{wc.DAY};{RNG_PIN}'}),
    # 용병: 로렌스 「아니요」·금화 모자람, 스콧은 개가 따라오면 거절·400 골드로 고용(손님 기록 C0 | 28)
    ('lawrence_no_side', 'warp', _below(endor.BARD_HALL, endor.LAWRENCE[0][2]), {'map': endor.BARD_HALL, 'set': sets()}),
    ('lawrence_no', 'walk', talk_no('up', 1, 1), {'map': endor.BARD_HALL, 'off': ['LAWRENCE']}),
    ('lawrence_poor_side', 'warp', _below(endor.BARD_HALL, endor.LAWRENCE[0][2]),
     {'map': endor.BARD_HALL, 'set': sets(more=(_gold(599),))}),
    ('lawrence_poor', 'walk', talk('up', 4), {'map': endor.BARD_HALL, 'off': ['LAWRENCE'], 'bytes': {'PARTY_N': 1}}),
    ('scott_dog_side', 'warp', _below(endor.TOWN, endor.SCOTT[2]),
     {'map': endor.TOWN, 'set': sets(more=(_gold(400), f'{0x2190 + ch3.DOG[0]:04X}|{ch3.DOG[1]:02X}'))}),
    ('scott_dog', 'walk', talk('up', 4), {'map': endor.TOWN, 'off': ['SCOTT'], 'bytes': {'GOLD0': 0x90, 'GOLD1': 0x01}}),
    ('scott_side', 'warp', _below(endor.TOWN, endor.SCOTT[2]), {'map': endor.TOWN, 'set': sets(more=(_gold(400),))}),
    ('scott_hire', 'walk', talk('up', 6), {'map': endor.TOWN, 'want': ['SCOTT'],
                                           'bytes': {'PARTY_N': 2, 'PARTY1': 0xE8, 'GOLD0': 0, 'GOLD1': 0}}),
    # 단추에 「아니요」: 그대로 48/03, 칸을 떠났다가 다시 서야 또 묻는다
    ('button_no_side', 'warp', f'{endor.CAVE_WET},{walk.BUTTON_CELL[0]},{walk.BUTTON_CELL[1] + 1}',
     {'map': endor.CAVE_WET, 'set': sets()}),
    ('button_no', 'walk', f'up:40;wait:200;down:8;wait:30;a:8;wait:200;{CLOSE};wait:300',
     {'map': endor.CAVE_WET, 'off': ['ENDOR_BUTTON', 'ENDOR_ASKED', 'ENDOR_PRESSED']}),
]

# 구간마다 띄워야 할 메시지(dq4ch3endor.MESSAGES 이름)의 앞 차례
MESSAGES = {
    'king_no': ['king_first', 'king_first_no'], 'king_wait': ['king_wait'], 'king_done': ['king_done'],
    'seller_no': ['seller_old', 'seller_offer', 'seller_pity'],
    'son_night': ['son_home'], 'nene_night': ['nene_late', 'nene_night', 'nene_morning', 'nene_bento'],
    'nene_no': ['nene_rest', 'nene_shopkeep'], 'nene_lie': ['nene_notice', 'nene_lie', 'nene_farewell'],
    'deliver_idle': ['deliver_idle'], 'deliver_done': ['deliver_thanks'],
    'deliver_empty': ['deliver_ask', 'deliver_take', 'deliver_none', 'deliver_left', 'left_swords', 'left_armors',
                      'deliver_more'],
    'deliver_one': ['deliver_ask', 'deliver_take', 'deliver_swords', 'deliver_got', 'deliver_left', 'left_swords',
                    'left_armors', 'deliver_more'],
    'deliver_over': ['deliver_ask', 'deliver_take', 'deliver_swords', 'deliver_armors', 'deliver_got', 'deliver_full',
                     'deliver_thanks'],
    'deliver_bag': ['deliver_ask', 'deliver_take', 'deliver_none', 'deliver_left', 'left_swords', 'left_armors',
                    'deliver_more'],
    'deliver_armors_full': ['deliver_ask', 'deliver_take', 'deliver_swords', 'deliver_got', 'deliver_left',
                            'left_swords', 'deliver_more'],
    'deliver_no': ['deliver_ask', 'deliver_left', 'left_swords', 'left_armors', 'deliver_more'],
    'guide_idle': ['guide_idle'], 'guide_order': ['guide_order'], 'guide_done': ['guide_done'],
    'collector_none': ['collector_wish'], 'collector_no': ['collector_offer', 'collector_no'],
    'lawrence_no': ['lawrence_offer', 'lawrence_no'], 'lawrence_poor': ['lawrence_offer', 'lawrence_poor'],
    'scott_dog': ['scott_offer', 'scott_dog'], 'scott_hire': ['scott_offer', 'scott_hired'],
    'collector_after': ['collector_admire'], 'collector_day': ['collector_wish'], 'button_no': ['button'],
}


def message_ids():
    """{이름: 메시지 번호}: 빌드와 같은 셈(옮긴 인물 메시지 뒤 1장·2장 사건 메시지, 그 뒤 3장 공용·모듈 차례)."""
    import dq4chapter1
    import dq4npcport
    root = HERE.parents[2]
    _, ported, _ = dq4npcport.port(root / 'rom' / 'dq5.sfc', root / 'rom' / 'dq4.nes')
    first = dq4chapter1.chapter3_message(dq4npcport.FIRST_MESSAGE + len(ported))
    return next(c for c in ch3.contexts(first) if c.key == 'E').msg


def units():
    return cwk.units(SEGMENTS, 0)


def walk_unit(mesence, rom, data, out, unit, base, seed=0):
    return cwk.walk_unit(mesence, rom, data, out, unit, base, seed, SEGMENTS, 0, walk.FLAGS, lambda _: {}, walk.HOPS,
                         walk.battle_patch)


def chapter():
    return types.SimpleNamespace(SEGMENTS=SEGMENTS, HEAD=0, head=walk.head, units=units, walk_unit=walk_unit)


def check_messages(report, ids):
    """걷기 결과(results.json)의 구간마다 메시지가 MESSAGES 의 차례로 시작하는지. [문제]."""
    problems = []
    for run in report['seeds']:
        for seg in run['segments']:
            want = MESSAGES.get(seg['name'])
            if want is None:
                continue
            got = [int(m, 16) for m in seg['messages']]
            if got[:len(want)] != [ids[k] for k in want]:
                problems.append(f"시드 {run['seed']} {seg['name']}: 메시지 {seg['messages']}, 기대 "
                                f"{[f'{ids[k]:03X}' for k in want]}({', '.join(want)})")
    return problems


def main():
    rc = cwk.main(chapter(), __doc__, 'dq4build.py --chapter3 의 롬', '같은 롬으로 만든 3장 출발 상태')
    out = Path(sys.argv[sys.argv.index('--out') + 1]).resolve()
    report = json.loads((out / 'results.json').read_text(encoding='utf-8'))
    problems = check_messages(report, message_ids())
    for p in problems:
        print(p, flush=True)
    report['message_problems'] = problems
    if problems:
        report['status'] = 'failed'
    (out / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n')
    print(json.dumps({'status': report['status'], 'message_problems': len(problems)}, ensure_ascii=False))
    return 0 if report['status'] == 'passed' and not rc else 1


if __name__ == '__main__':
    sys.exit(main())
