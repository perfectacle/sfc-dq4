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
import dq4neneshop as shop  # noqa: E402
import dq4ch3tunnel as tunnel  # noqa: E402
import dq4ch3event as ch3  # noqa: E402
import dq4ch3endor_checks as endor_checks  # noqa: E402
import dq4ch3walkcheck as walk  # noqa: E402
import dq4ch3walkparts as parts  # noqa: E402
import dq4chapterwalk as cwk  # noqa: E402

CLOSE = wc.pc.CLOSE
_set, _items, _below, _gold = parts.set_flag, parts.items, endor_checks.below, parts.gold
talk = wc.talk
# 3장 출발 상태의 엔돌 flag 를 모두 끄고 갈래의 flag 만 켠다
CLEAR = f'{0x2190 + endor.IDX:04X}=00;{0x2190 + endor.IDX2:04X}=00'


def talk_no(face, before, after):
    """그 쪽을 보고 말을 건 뒤 물음 창이 뜰 때까지 A 로 글을 넘기고(dq4walk.lua ask), 커서를 「아니요」 에 둔 다음 A 를
    after 번(고르기 + 남은 쪽 수. 더 누르면 다시 말을 걸어 갈래가 섞인다). before 는 물음까지의 쪽 수(넘길 시간의 상한)."""
    return f'{face}:8;wait:30;ask:{300 + 120 * before};cursor:1;{wc.taps(after, 90)};{CLOSE}'


def sets(*flags, more=()):
    return ';'.join((CLEAR, *(_set(f) for f in flags), *more))


def COUNT_SET(v):
    return f'{walk.FLAGS["ENDOR_COUNT"][0] & 0xFFFF:04X}={v:02X}'


# 맡긴 물건(7E:2250 + 물건 번호)에만 칼·갑옷 하나씩
BAG_SET = f'{(ch3.BAG & 0xFFFF) + endor.STEEL_SWORD:04X}=01;{(ch3.BAG & 0xFFFF) + endor.IRON_ARMOR:04X}=01'
RNG_PIN = '7E075B=00;7E075C=00;7E075D=00'
UNSOLD_PIN = '7E075B=C0;7E075C=C0;7E075D=C0'
SELLER_NIGHT = endor.SELLER[1][2]                     # 밤의 가게 주인(05,02). 그 아래에서 말을 건다
NENE_NIGHT = endor.NENE[1][2]                          # 밤의 네네(04/08 (03,03))
SON_NIGHT = endor.SON[1][2]
GUIDE = endor.GUIDE[2]
COLLECTOR_NIGHT = endor.COLLECTORS[1][2]
NENE_DAY = endor.cell(*endor.NENE[0][2])
CHEAP = 0x01                                           # DQ5 물건 01(값 50)


def sales_set(n):
    """네네 매상(둘째 변수 칸, 3바이트)을 n 으로 두는 SET 조각."""
    at = ch3.VARS2_AT + ch3.SLOTS['E'].vars2[0] + shop.SALES
    return ';'.join(f'{(at + k) & 0xFFFF:04X}={n >> 8 * k & 0xFF:02X}' for k in range(3))


# 가게 칸 0~2 에 강철 검(2000G) 둘·물건 01(50G)
STOCK_SET = ';'.join(f'{shop.stock_addr(k) & 0xFFFF:04X}={item + 1:02X}'
                     for k, item in enumerate((endor.STEEL_SWORD, endor.STEEL_SWORD, CHEAP)))
# 카운터 위에서 말을 건다. 물음은 창 상태로 넘긴다(dq4walk.lua ask·cursor)
TALK_DOWN = 'down:8;wait:30;a:8;wait:60;a:8;wait:60'
YES, NO = 'ask:600;cursor:0;a:8', 'ask:600;cursor:1;a:8'
# 036B 「예」, 매상(036D)을 넘기면 물건 고르기 창(DQ5 필드 도구 창 0F)이 뜨므로 그때까지 A 로 넘긴다(dq4walk.lua open).
# 창이 뜬 프레임에는 커서(7E:0AD7)가 앞 창 값이고 뒤이어 첫 칸으로 놓여, 잠깐 기다린 뒤 칸 2(강철 검)를 고른다.
# 036F 「예」, 0371 「아니요」, 0374 「아니요」 → 0375
ITEM_LIST = 0x0F
COUNTER_WALK = f'{TALK_DOWN};{YES};open:{ITEM_LIST};settle:8;cursor:2;a:8;{YES};{NO};{NO};{wc.taps(1, 90)};{CLOSE}'
# 036B 「예」(매상 없음), 물건 창을 B 로 그만두고 0374 「예」 → 가게 물건 창(BRK 95 0F)을 B 로 닫고 0375
VIEW_WALK = f'{TALK_DOWN};{YES};wait:150;b:8;{YES};wait:150;b:8;wait:60;{wc.taps(1, 90)};{CLOSE}'
# 톨네코 소지품이 없으면 0334 → 0374 「예」 → 가게가 비었으면 0376 만
EMPTY_WALK = f'{TALK_DOWN};{YES};{YES};{wc.taps(1, 90)};{CLOSE}'
NO_ITEMS = ';'.join(f'{(ch3.PARTY_ITEMS & 0xFFFF) + k:04X}=FF' for k in range(12)) + \
    f';{(ch3.PARTY_ITEMS - 2) & 0xFFFF:04X}=00;{(ch3.PARTY_ITEMS - 1) & 0xFFFF:04X}=00'
NO_STOCK = ';'.join(f'{shop.stock_addr(k) & 0xFFFF:04X}=00' for k in range(shop.STOCK_SLOTS))
# 120칸이 다 찼으면(FC 15:$9EC8 ≥ 78) 036B 「예」 → 0377(끝에 보기 물음) 「아니요」 → 0375
FULL_STOCK = ';'.join(f'{shop.stock_addr(k) & 0xFFFF:04X}={endor.STEEL_SWORD + 1:02X}' for k in range(shop.STOCK_SLOTS))
FULL_WALK = f'{TALK_DOWN};{YES};{NO};{wc.taps(1, 90)};{CLOSE}'

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
    ('nene_lie', 'walk', talk_no('right', 2, 5), {'map': endor.TOWN, 'want': ['TUNNEL_OPENED']}),
    # 공사 재개 뒤 소식 전(굴 모듈 RESUMED): 「아무 소식도 안 왔어요」(08A1)
    ('nene_nonews_side', 'warp', f'{endor.TOWN},{endor.NENE_SIDE[1][0]},{endor.NENE_SIDE[1][1] - 1}',
     {'map': endor.TOWN, 'set': sets(endor.SHOP, more=(f'{0x2190 + tunnel.IDX:04X}=00', _set(tunnel.RESUMED)))}),
    ('nene_nonews', 'walk', talk('right', 3), {'map': endor.TOWN, 'off': ['TUNNEL_OPENED']}),
    # 네네 가게(dq4neneshop): 카운터 너머(위)에서 말을 걸면 어제 매상을 건네고, 고른 물건을 가게 칸에
    ('nene_counter_side', 'warp', f'{endor.TOWN},{NENE_DAY[0]},{NENE_DAY[1] - 5}',
     {'map': endor.TOWN, 'set': sets(endor.SHOP, more=(_items(endor.STEEL_SWORD), _gold(0), sales_set(1000)))}),
    ('nene_counter', 'walk', COUNTER_WALK,
     {'map': endor.TOWN, 'bytes': {'GOLD0': 0xE8, 'GOLD1': 0x03, 'NENE_SALES0': 0, 'NENE_SALES1': 0,
                                   'NENE_STOCK0': endor.STEEL_SWORD + 1}}),
    # 0374 「예」: 가게 물건 창을 열고 닫아도 가게 칸·소지품·장비가 그대로
    ('nene_view_side', 'warp', f'{endor.TOWN},{NENE_DAY[0]},{NENE_DAY[1] - 5}',
     {'map': endor.TOWN, 'set': sets(endor.SHOP, more=(_items(endor.STEEL_SWORD), STOCK_SET, sales_set(0)))}),
    ('nene_view', 'walk', VIEW_WALK,
     {'map': endor.TOWN, 'items': [0x42, parts.BENTO, endor.STEEL_SWORD],
      'bytes': {'NENE_STOCK0': endor.STEEL_SWORD + 1, 'EQUIP0': 0x01}}),
    ('nene_empty_side', 'warp', f'{endor.TOWN},{NENE_DAY[0]},{NENE_DAY[1] - 5}',
     {'map': endor.TOWN, 'set': sets(endor.SHOP, more=(NO_ITEMS, NO_STOCK, sales_set(0)))}),
    ('nene_empty', 'walk', EMPTY_WALK, {'map': endor.TOWN, 'bytes': {'NENE_STOCK0': 0}}),
    ('nene_full_side', 'warp', f'{endor.TOWN},{NENE_DAY[0]},{NENE_DAY[1] - 5}',
     {'map': endor.TOWN, 'set': sets(endor.SHOP, more=(FULL_STOCK, sales_set(0)))}),
    ('nene_full', 'walk', FULL_WALK, {'map': endor.TOWN, 'bytes': {'NENE_STOCK0': endor.STEEL_SWORD + 1}}),
    # 잠으로 날이 바뀌면 가게 칸마다 rand < C0 이면 값 × (96 + ⌊r × 33/256⌋)/64 가 매상으로. 난수를 고정하면 셋 다 팔려
    # 8043(값 합 4050 의 2배 8100 이하, 1.5배 6075 이상)
    ('nene_day_side', 'warp', f'{endor.TOWN},{endor.NENE_SIDE[1][0]},{endor.NENE_SIDE[1][1] - 1}',
     {'map': endor.TOWN, 'set': sets(endor.SHOP, more=(STOCK_SET, sales_set(0))),
      'poke': RNG_PIN}),
    ('nene_day', 'walk', talk('right', 8),
     {'map': endor.TOWN, 'poke': RNG_PIN, 'changes': 1, 'after': 600,
      'bytes': {'NENE_SALES0': 0x6B, 'NENE_SALES1': 0x1F, 'NENE_SALES2': 0, 'NENE_STOCK0': 0}}),
    # 안 팔린 날: 강철 검 하나를 두고 난수를 C0 으로 고정하면 굴림이 3/4 밖이라 칸에 남고 매상은 0(00·40·80·FF 는 팔림)
    ('nene_unsold_side', 'warp', f'{endor.TOWN},{endor.NENE_SIDE[1][0]},{endor.NENE_SIDE[1][1] - 1}',
     {'map': endor.TOWN, 'set': sets(endor.SHOP, more=(STOCK_SET.split(';')[0], sales_set(0))), 'poke': UNSOLD_PIN}),
    ('nene_unsold', 'walk', talk('right', 8),
     {'map': endor.TOWN, 'poke': UNSOLD_PIN, 'changes': 1, 'after': 600,
      'bytes': {'NENE_SALES0': 0, 'NENE_SALES1': 0, 'NENE_SALES2': 0, 'NENE_STOCK0': endor.STEEL_SWORD + 1}}),
    # 납품: 주문 전·「아니요」·다 채운 뒤. 안내하는 옆 사람도 셋
    ('deliver_idle_side', 'warp', _below(endor.CASTLE_HALL, endor.DELIVER[2]),
     {'map': endor.CASTLE_HALL, 'set': sets()}),
    ('deliver_idle', 'walk', talk('up', 2), {'map': endor.CASTLE_HALL}),
    ('deliver_no_side', 'warp', _below(endor.CASTLE_HALL, endor.DELIVER[2]),
     {'map': endor.CASTLE_HALL, 'set': sets(endor.ORDER, more=(_items(endor.STEEL_SWORD),))}),
    ('deliver_no', 'walk', talk_no('up', 0, 4),
     {'map': endor.CASTLE_HALL, 'bytes': {'ENDOR_COUNT': 0}, 'items': [0x42, parts.BENTO, endor.STEEL_SWORD]}),
    # FC 15:$A118 실측 갈래: 가진 것이 없음, 칼만, 넘침(남은 수보다 많이 가짐 → 남은 만큼만 받고 다 참), 맡긴 물건뿐,
    # 갑옷은 다 찼고 칼 하나(남은 갑옷 줄이 빠짐)
    ('deliver_empty_side', 'warp', _below(endor.CASTLE_HALL, endor.DELIVER[2]),
     {'map': endor.CASTLE_HALL, 'set': sets(endor.ORDER)}),
    ('deliver_empty', 'walk', talk('up', 7), {'map': endor.CASTLE_HALL, 'bytes': {'ENDOR_COUNT': 0}}),
    ('deliver_one_side', 'warp', _below(endor.CASTLE_HALL, endor.DELIVER[2]),
     {'map': endor.CASTLE_HALL, 'set': sets(endor.ORDER, more=(_items(endor.STEEL_SWORD),))}),
    ('deliver_one', 'walk', talk('up', 8), {'map': endor.CASTLE_HALL, 'bytes': {'ENDOR_COUNT': 0x01},
                                            'items': [0x42, parts.BENTO]}),
    ('deliver_over_side', 'warp', _below(endor.CASTLE_HALL, endor.DELIVER[2]),
     {'map': endor.CASTLE_HALL,
      'set': sets(endor.ORDER, more=(_items(*[endor.STEEL_SWORD] * 4, endor.IRON_ARMOR), _gold(0), COUNT_SET(0x64)))}),
    ('deliver_over', 'walk', talk('up', 8), {'map': endor.CASTLE_HALL, 'want': ['ENDOR_DELIVERED'],
                                             'bytes': {'ENDOR_COUNT': 0x77, 'GOLD0': 0x60, 'GOLD1': 0xEA},
                                             'items': [0x42, parts.BENTO, endor.STEEL_SWORD]}),
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
                                                 'items': [0x42, parts.BENTO, endor.STATUE]}),
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
                                           'bytes': {'PARTY_N': 2, 'PARTY1': 0xE8, 'GOLD0': 0, 'GOLD1': 0,
                                                     'FOLLOWER1': ch3.SCOTT_PICTURE}}),
    # 단추에 「아니요」: 그대로 48/03, 칸을 떠났다가 다시 서야 또 묻는다
    ('button_no_side', 'warp', f'{endor.CAVE_WET},{endor_checks.BUTTON_CELL[0]},{endor_checks.BUTTON_CELL[1] + 1}',
     {'map': endor.CAVE_WET, 'set': sets()}),
    ('button_no', 'walk', f'up:16;ask:300;cursor:1;a:8;wait:200;{CLOSE};wait:300',
     {'map': endor.CAVE_WET, 'off': ['ENDOR_BUTTON', 'ENDOR_ASKED', 'ENDOR_PRESSED']}),
]

# 구간마다 띄워야 할 메시지(dq4ch3endor.MESSAGES 이름)의 앞 차례
MESSAGES = {
    'king_no': ['king_first', 'king_first_no'], 'king_wait': ['king_wait'], 'king_done': ['king_done'],
    'seller_no': ['seller_old', 'seller_offer', 'seller_pity'],
    'son_night': ['son_home'], 'nene_night': ['nene_late', 'nene_night', 'nene_morning', 'nene_bento'],
    'nene_no': ['nene_rest', 'nene_shopkeep'], 'nene_lie': ['news', 'news_no', 'news_farewell'], 'nene_nonews': ['no_news'],
    'nene_day': ['nene_rest', 'nene_night'],
    'nene_view': ['nene_counter_ask', 'nene_pick', 'nene_done', 'nene_cheer'],
    'nene_empty': ['nene_counter_ask', 'nene_nothing', 'nene_done', 'nene_empty'],
    'nene_full': ['nene_counter_ask', 'nene_full', 'nene_cheer'],
    'nene_unsold': ['nene_rest', 'nene_night'],
    'nene_counter': ['nene_counter_ask', 'nene_sales', 'nene_pick', 'nene_item', 'nene_offer', 'nene_put', 'nene_more',
                     'nene_done', 'nene_cheer'],
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
    msg = {k: c.msg for c in ch3.contexts(first) for k in ('E', 'T') if c.key == k}
    # 네네의 개통 갈래는 굴 모듈 메시지(dq4ch3tunnel.news_talk)
    clash = set(msg['E']) & set(msg['T'])
    if clash:
        raise SystemExit(f'엔돌·굴 메시지 이름이 겹침: {sorted(clash)}')
    return {**msg['E'], **msg['T']}


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
