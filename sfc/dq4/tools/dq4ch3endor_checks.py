"""엔돌(dq4ch3endor)의 검사 표. 내놓는 것은 dq4ch3checks 머리말."""
import dq4ch1walkcheck as wc
import dq4ch3event as ch3
import dq4ch3endor as endor
import dq4neneshop as shop
from dq4ch3walkparts import BENTO, CLOSE, FACE_UP, FIELD_OUT, SEARCH, TOWN, TOWN_WEST, gold, items, set_flag, talk, talk_yes, taps

FLAGS = {
    **{f'ENDOR_{k}': wc.flag(getattr(endor, k)) for k in ('ALLOWED', 'SHOP', 'ORDER', 'DELIVERED', 'SOLD', 'SON_CHEER',
                                                          'NOTICE', 'BUTTON', 'ASKED', 'PRESSED')},
    'ENDOR_COUNT': (ch3.VARS_AT + ch3.SLOTS['E'].vars[0] + endor.VARS, 0xFF),
    **{f'NENE_SALES{k}': (ch3.VARS2_AT + ch3.SLOTS['E'].vars2[0] + shop.SALES + k, 0xFF) for k in range(3)},
    'NENE_STOCK0': (shop.stock_addr(0), 0xFF),
    'NENE_MARK': (0x7E0000 | shop.VIEW_MARK, 0xFF),     # 보기 표지는 보기 밖에서 늘 0
    'NENE_LINES': (0x7E0000 | shop.VIEW_COUNT, 0xFF),   # 보기 쪽 줄 수(창 높이)
    'NENE_SPLIT': (0x7E0000 | shop.VIEW_SPLIT, 0xFF),   # 앞 쪽 위에 겹친 쪽의 물건 수(겹치지 않으면 0)
    # 보기 창 꼴(타일맵 버퍼 7E:5000 의 칸 아래 바이트, dq4windowname NENE_VIEW_XY = (18, 3)): 왼쪽 위 모서리 8C, 줄 머리 칸
    # (x 19)은 커서 없는 빈칸 01, 아래 테두리 8B. 표지가 써지지 않으면 창 37 이 DQ5 팔기 목록 꼴(x 9, ▶ 커서)로 떠 어긋난다
    **{f'NENE_CELL_{x}_{y}': (0x7E5000 + (y * 32 + x) * 2, 0xFF) for x, y in ((18, 3), (19, 4), (18, 20), (18, 10), (19, 9))},
    # 보기 창 타일맵 버퍼(7E:5000, 칸마다 낱말)의 오른쪽 테두리 열 x 29: 줄 k(위 테두리 y 3 아래 y 4 + 2k)의 아래 바이트는
    # 테두리 8E. 바깥 x 30 은 창 밖 빈칸(위 바이트 2C)
    **{f'NENE_RIGHT{k}': (0x7E5000 + ((4 + 2 * k) * 32 + 29) * 2, 0xFF) for k in range(8)},
    'NENE_OUTSIDE': (0x7E5000 + (4 * 32 + 30) * 2 + 1, 0xFF),
    # 따라 걷는 첫 칸의 그림 번호(인물 표 7E:3220 + 슬롯 1). 용병은 dq4people 이 NDS 병사·시인을 싣는 그림
    'FOLLOWER1': (0x7E3221, 0xFF),
}

# 엔돌: 사람 바로 아래 셀(FC 칸 한 칸 아래). 순간이동은 TO 의 한 셀 아래에 내린다
KING_BELOW = endor.cell(endor.KING[2][0], endor.KING[2][1] + 1)
ENDOR_OFF = ['ENDOR_ALLOWED', 'ENDOR_SHOP', 'ENDOR_ORDER']
BUTTON_CELL = endor.BUTTON_LAND[1]
# 말 창 뒤 물음 창이 뜨기를 기다려 커서를 「예」 에(dq4walk.lua 의 until·cursor)
ASK = 'until:300;until:300;cursor:0'


def below(mp, fc):
    """FC 칸 fc 의 사람 바로 아래 셀에 내리는 순간이동 인자(TO 의 한 셀 아래에 내린다)."""
    x, y = endor.cell(fc[0], fc[1] + 1)
    return f'{mp},{x},{y - 1}'


LETTER2_SET = f'{0x2190 + endor.LETTER2[0]:04X}|{endor.LETTER2[1]:02X}'


def effects(data):
    """용병 로렌스를 고용한 뒤의 일행 기록. 롬의 기록 틀을 읽는다."""
    import dq4mercenary as merc
    rec = merc.record(data, 'lawrence')
    party = ';'.join(f'{(ch3.PARTY_ITEMS - 0x16 + ch3.RECORD) + k & 0xFFFF:04X}={b:02X}' for k, b in enumerate(rec))
    return {'endor_lawrence_hire': {'set': f'{party};201D=02;201F=02;201E=02;2021=01;2029=01'}}


# 엔돌, 이야기 차례로: 왕 첫 알현(flag 없음) → 허락 전의 가게 주인 → 왕의 편지 뒤 허락 → 금화가 모자람 →
# 35001 골드로 가게를 삼(아침, 네네 옆으로) → 왕의 주문
SEGMENTS = [
    ('endor_king', 'warp', below(endor.THRONE, endor.KING[2]), {'map': endor.THRONE}),
    ('endor_king_first', 'walk', talk_yes('up', 6), {'map': endor.THRONE, 'off': ENDOR_OFF}),
    ('endor_seller', 'warp', below(endor.SHOP_UP, endor.SELLER[0][2]), {'map': endor.SHOP_UP}),
    ('endor_seller_wish', 'walk', talk('up', 4), {'map': endor.SHOP_UP, 'off': ENDOR_OFF}),
    ('endor_king_letter', 'warp', below(endor.THRONE, endor.KING[2]), {'map': endor.THRONE, 'set': LETTER2_SET}),
    ('endor_king_allow', 'walk', talk('up', 6), {'map': endor.THRONE, 'want': ['ENDOR_ALLOWED']}),
    ('endor_seller_allowed', 'warp', below(endor.SHOP_UP, endor.SELLER[0][2]), {'map': endor.SHOP_UP}),
    ('endor_seller_poor', 'walk', talk_yes('up', 6), {'map': endor.SHOP_UP, 'off': ['ENDOR_SHOP']}),
    ('endor_seller_buy', 'walk', talk_yes('up', 14),
     {'set': gold(endor.SHOP_PRICE + 1), 'map': endor.TOWN, 'cell': endor.NENE_SIDE[1], 'want': ['ENDOR_SHOP'],
      'bytes': {'GOLD0': 1, 'GOLD1': 0, 'GOLD2': 0}, 'changes': 1, 'after': 900}),
    ('endor_king_shop', 'warp', below(endor.THRONE, endor.KING[2]), {'map': endor.THRONE}),
    ('endor_king_order', 'walk', talk('up', 6), {'map': endor.THRONE, 'want': ['ENDOR_ORDER']}),
    # 네네: 가게를 산 뒤 낮에는 「쉴래요?」 → 「예」 면 잠, 개통 소식이 왔으면 08A0 → 개통
    ('endor_nene', 'warp', f'{endor.TOWN},{endor.NENE_SIDE[1][0]},{endor.NENE_SIDE[1][1] - 1}', {'map': endor.TOWN}),
    ('endor_nene_sleep', 'walk', talk_yes('right', 8), {'map': endor.TOWN, 'cell': endor.NENE_SIDE[1], 'changes': 1,
                                                     'after': 600, 'items': [BENTO]}),
    ('endor_nene_notice', 'walk', talk_yes('right', 12), {'map': endor.TOWN, 'set': set_flag(endor.NOTICE),
                                                       'want': ['TUNNEL_OPENED']}),
    # 납품: 주문 전에는 안내만, 주문 뒤 없으면 그대로, 칼 둘·갑옷 하나를 받고, 다 차면 60000 골드
    ('endor_deliver', 'warp', below(endor.CASTLE_HALL, endor.DELIVER[2]), {'map': endor.CASTLE_HALL}),
    ('endor_deliver_none', 'walk', talk_yes('up', 8), {'map': endor.CASTLE_HALL, 'bytes': {'ENDOR_COUNT': 0}}),
    ('endor_deliver_some', 'walk', talk_yes('up', 10),
     {'map': endor.CASTLE_HALL, 'set': items(endor.STEEL_SWORD, endor.STEEL_SWORD, endor.IRON_ARMOR),
      'bytes': {'ENDOR_COUNT': 0x12}, 'items': [0x42, BENTO]}),
    ('endor_deliver_full', 'walk', talk_yes('up', 10),
     {'map': endor.CASTLE_HALL,
      'set': ';'.join((items(endor.STEEL_SWORD, endor.IRON_ARMOR), gold(0), f'{FLAGS["ENDOR_COUNT"][0] & 0xFFFF:04X}=66')),
      'want': ['ENDOR_DELIVERED'], 'bytes': {'ENDOR_COUNT': 0x77, 'GOLD0': 0x60, 'GOLD1': 0xEA, 'GOLD2': 0}}),
    # 수집가: 여신상을 25000 골드에. 낮의 수집가는 걸어 다녀 밤에 서 있는 자리로 본다
    ('endor_collector', 'warp', below(endor.COLLECTOR, endor.COLLECTORS[1][2]), {'map': endor.COLLECTOR,
                                                                                   'poke': wc.NIGHT}),
    ('endor_collector_sell', 'walk', talk_yes('up', 4),
     {'map': endor.COLLECTOR, 'poke': wc.NIGHT, 'set': ';'.join((items(endor.STATUE), gold(0))), 'want': ['ENDOR_SOLD'],
      'bytes': {'GOLD0': 0xA8, 'GOLD1': 0x61, 'GOLD2': 0}, 'items': [0x42, BENTO]}),
    # 단추를 누른 뒤 입구 층의 계단은 48/03 대신 물이 빠진 48/04 로(누르기 전은 48/03)
    ('endor_cave_stair', 'warp', f'{endor.CAVE_ENTRY},22,8', {'map': endor.CAVE_ENTRY}),
    ('endor_cave_wet', 'walk', 'up:40;wait:300', {'map': endor.CAVE_WET, 'changes': 1, 'after': 60, 'off': ['ENDOR_BUTTON']}),
    ('endor_cave_stair2', 'warp', f'{endor.CAVE_ENTRY},22,8', {'map': endor.CAVE_ENTRY, 'set': set_flag(endor.BUTTON)}),
    ('endor_cave_dry', 'walk', 'up:40;wait:300', {'map': endor.CAVE_DRY, 'changes': 1, 'after': 60}),
    # 용병 로렌스(dq4mercenary): 600 골드로 고용하면 일행 기록 1 이 손님 로렌스(+0 = C0 | 29)
    ('endor_lawrence', 'warp', below(endor.BARD_HALL, endor.LAWRENCE[0][2]), {'map': endor.BARD_HALL}),
    ('endor_lawrence_hire', 'walk', talk_yes('up', 8),
     {'map': endor.BARD_HALL, 'set': ';'.join((gold(600), f'{ch3.LAWRENCE_DAYS & 0xFFFF:04X}=03')), 'want': ['LAWRENCE'],
      'bytes': {'PARTY_N': 2, 'PARTY1': 0xE9, 'LAWRENCE_DAYS': 0, 'GOLD0': 0, 'GOLD1': 0,
                'FOLLOWER1': ch3.LAWRENCE_PICTURE}}),
    # 날수: 시간이 01FF 인 필드 걸음에 하루가 지나고(3 → 4), 날수 5 인 필드 걸음에 0379 뒤 일행에서 빠진다
    ('endor_day_side', 'warp', TOWN_WEST, {'map': TOWN, 'set': f'{ch3.LAWRENCE_DAYS & 0xFFFF:04X}=03'}),
    ('endor_day', 'walk', 'left:64;wait:60;down:16', {'field': True, 'cell': (FIELD_OUT[0], FIELD_OUT[1] + 2),
                                                       'set': '075E=FF;075F=01',
                                                       'bytes': {'LAWRENCE_DAYS': 4, 'PARTY_N': 2}, 'want': ['LAWRENCE']}),
    ('endor_leave_side', 'warp', TOWN_WEST, {'map': TOWN, 'set': f'{ch3.LAWRENCE_DAYS & 0xFFFF:04X}=05'}),
    ('endor_leave', 'walk', f'left:64;wait:60;down:16;wait:60;{taps(6)};{CLOSE}', {'field': True, 'poke': wc.DAY,
                                                                                    'off': ['LAWRENCE'],
                                                                                    'bytes': {'PARTY_N': 1}}),
    # 여신상 방(48/07, FC 40/05)의 상자 아래에서 위를 보고 しらべる → 은의 여신상
    ('endor_statue', 'warp', f'{endor.STATUE_ROOM},12,10', {'map': endor.STATUE_ROOM}),
    ('endor_statue_open', 'walk', SEARCH, {'poke': FACE_UP, 'items': [endor.STATUE]}),
    # 여신상 동굴 단추: 「예」 면 물이 빠진 48/04 의 같은 칸으로
    ('endor_button_side', 'warp', f'{endor.CAVE_WET},{BUTTON_CELL[0]},{BUTTON_CELL[1] + 1}', {'map': endor.CAVE_WET}),
    ('endor_button', 'walk', f'up:40;ask:400;cursor:0;a:8;wait:60;a:8;wait:600',
     {'map': endor.CAVE_DRY, 'cell': endor.BUTTON_LAND[1], 'want': ['ENDOR_BUTTON'], 'changes': 1, 'after': 60}),
]


def hero_cases():
    # 여신상 동굴 단추 칸(FC 40/01 (11,02))의 두 열마다: 한 줄 아래(FC (11,03))에서 올라서 「예」 면 물이 빠진 48/04 의
    # 같은 칸에 서고, 왼쪽 통로(FC (0C,02))로 걸어 간다. 칸에 올라서면 말 창(00)에 이어 A 없이 물음 창(32)이 뜬다. 위를
    # 정해진 프레임만큼 누르면 물음 창이 뜨는 때(번호만 밀려도 두 프레임쯤 달라짐)에 따라 커서가 「아니요」 로 가므로, 창이 두 번
    # 바뀌기를 기다려 커서를 「예」(0)에 두고 고른다
    bx0, _, _, by1 = endor._hero_rect(*endor.BUTTON_FC)
    return {f'endor-button-{x}': {'warp': f'{endor.CAVE_WET},{x},{by1}', 'set': '',
                                  'walk': f'up:16;{ASK};a:8;wait:60;a:8;wait:800', 'free': '24,5',
                                  'want': [('ENDOR_BUTTON', endor.BUTTON)], 'map': endor.CAVE_DRY, 'maxf': 3000}
            for x in (bx0, bx0 + 1)}
