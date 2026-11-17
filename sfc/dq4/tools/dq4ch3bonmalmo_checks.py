"""본몰·여우 마을(dq4ch3bonmalmo)의 검사 표. 내놓는 것은 dq4ch3checks 머리말. 물건은 톨네코 물건 칸 2 에 SET 으로
두고 말을 건다."""
import dq4ch1walkcheck as wc
import dq4ch3bonmalmo as bm
from dq4ch3walkparts import CLOSE, talk, taps

FLAGS = {
    'BM_FOXED': wc.flag(bm.FOXED),
    'BM_PRINCE_MET': wc.flag(bm.PRINCE_MET),
    'BM_NANNY_SCOLDED': wc.flag(bm.NANNY_SCOLDED),
    'BM_SON_FREED': wc.flag(bm.SON_FREED),
    'BM_BRIDGE': wc.flag(bm.BRIDGE),
    'BM_LETTER1': wc.flag(bm.LETTER1),
    'BM_LETTER2': wc.flag(bm.LETTER2),
    'BM_FOX_SCENE': wc.flag(bm.FOX_SCENE),
    # 톨네코 물건 칸 2(칸 0 옷, 칸 1 도시락 다음): 사건 물건을 두고 빠지는지 보는 칸
    'BM_SLOT2': (0x7E2056 + 2, 0xFF),
    'BM_BAG_LETTER': (0x7E2250 + bm.PRINCE_LETTER, 0xFF),
}

BM_SLOT2 = '2058'
BM_FOX_OFF = ['BM_FOX_SCENE']
# 예·아니요 창에서 「아니요」 를 고르는 누름(창이 없을 때의 아래는 대사 창에 먹히지 않음)
BM_NO = 'wait:60;down:8;wait:40;a:8;wait:60'
# 톨네코 물건 칸 2~11 을 こんぼう(02)로 채운다(칸 0 옷, 칸 1 도시락)
# 낮 왕자(3F/01 낮 목록 첫 사람, 인물 칸 4)는 오가는 사람이라 이동 간격(7E:3300 + 2 × 칸)을 0 으로 붙든다. 붙들지 않으면
# snes9x 에서 왕자가 비켜 말이 걸리지 않았다
BM_PRINCE_HOLD = wc.DAY + ';7E3308=00'
# 여우 마을 필드 입구 블록(FC (7C,34))의 왼쪽 위 칸
BM_FOX_GATE = (0x7C * 2, 0x34 * 2)
BM_FULL = ';'.join(f'{0x2058 + k:04X}=02' for k in range(10))
# 본몰 성 출구 줄(dq4groupbuild LINKS 3F arrival (11,1F) 위 칸)과 나가면 서는 필드 칸, 다리(FC (6F,4F)) 서쪽·동쪽 칸
BM_GATE = (0x11 * 2, 0x1E * 2 + 1)
BM_FIELD_GATE = (0x74 * 2, 0x47 * 2)
BM_WEST = (0x6E * 2, 0x4F * 2)
BM_EAST = (0x71 * 2, 0x4F * 2)
SEGMENTS = [
    # 감옥: 창살 너머 아들에게 오른쪽을 보고 말을 걸어 키메라의 날개를 준다. 「아니요」 면 0841 뒤 다시 묻고(두 번),
    # 「예」 면 날개가 빠지고 아들이 사라진다
    ('bm_prison_no', 'warp', f'{bm.PRISON},{bm.SON[0] - 4},{bm.SON[1] - 1}',
     {'map': bm.PRISON, 'set': f'{BM_SLOT2}={bm.WINGS:02X}', 'poke': wc.DAY}),
    ('bm_son_no', 'walk', f'right:8;wait:30;a:8;wait:60;a:8;wait:60;{";".join([BM_NO] * 5)};{taps(8)};{CLOSE}',
     {'want': ['BM_SON_FREED'], 'bytes': {'BM_SLOT2': 0xFF}, 'poke': wc.DAY}),
    # 여우 마을 촌장: 개가 없으면 「예」·「예」 로 묵고 숲에서 아침에 깬다
    ('bm_inn_town', 'warp', f'{bm.FOX_TOWN},{bm.CHIEF[0] - 2},{bm.CHIEF[1] - 1}', {'map': bm.FOX_TOWN, 'poke': wc.NIGHT}),
    ('bm_inn', 'walk', f'{talk("right", 8)};wait:600', {'map': bm.FOREST, 'cell': bm.FOREST_WAKE, 'off': ['BM_FOXED']}),
    # 왕자: 낮에 처음 말을 걸면 유모가 꾸짖고 일행은 그 자리. 밤에는 무기점 뒤에서 왕자의 편지를 준다
    ('bm_prince_side', 'warp', f'{bm.CASTLE},{bm.PRINCE["day"][0] + 2},{bm.PRINCE["day"][1] - 1}',
     {'map': bm.CASTLE, 'poke': BM_PRINCE_HOLD}),
    ('bm_prince', 'walk', f'{talk("left", 10)};wait:300',
     {'map': bm.CASTLE, 'cell': (bm.PRINCE['day'][0] + 2, bm.PRINCE['day'][1]),
      'want': ['BM_PRINCE_MET', 'BM_NANNY_SCOLDED'],
      'poke': BM_PRINCE_HOLD}),
    ('bm_prince_night_side', 'warp', f'{bm.CASTLE},{bm.PRINCE["night"][0]},{bm.PRINCE["night"][1] + 1}',
     {'map': bm.CASTLE, 'poke': wc.NIGHT}),
    ('bm_prince_night', 'walk', talk('up', 12), {'items': [bm.PRINCE_LETTER], 'poke': wc.NIGHT}),
    # 소지품이 가득이면(열 칸을 채움) 036A 만, 편지는 소지품에도 맡긴 물건에도 들지 않는다
    ('bm_prince_full_side', 'warp', f'{bm.CASTLE},{bm.PRINCE["night"][0]},{bm.PRINCE["night"][1] + 1}',
     {'map': bm.CASTLE, 'set': BM_FULL, 'poke': wc.NIGHT}),
    ('bm_prince_full', 'walk', talk('up', 8), {'bytes': {'BM_SLOT2': 0x02, 'BM_BAG_LETTER': 0}, 'poke': wc.NIGHT}),
    # 개가 따라오면 촌장이 놀라 숲으로 바뀌고, 여우가 빌어 「예」 면 강철 갑옷, 돈 가아데가 떠나 FOXED
    ('bm_fox_town', 'warp', f'{bm.FOX_TOWN},{bm.CHIEF[0] - 2},{bm.CHIEF[1] - 1}',
     {'map': bm.FOX_TOWN, 'set': '21FF|02', 'poke': wc.DAY}),
    # 여우가 처음 빌 때 「아니요」(084E) 면 다시 빌고, 「예」 에 갑옷
    ('bm_fox', 'walk', f'{talk("right", 2)};wait:200;{";".join([BM_NO] * 3)};{taps(16, 80)};wait:600;{CLOSE}',
     {'map': bm.FOREST, 'want': ['BM_FOXED'], 'off': BM_FOX_OFF, 'items': [bm.STEEL_ARMOR], 'maxf': 6000,
      'poke': wc.DAY}),
    # 여우를 쫓은 뒤: 숲 어귀에서 필드로 나가 위의 입구로 들면 마을 대신 숲 어귀에 선다
    ('bm_forest_side', 'warp', f'{bm.FOREST},{bm.FOREST_ENTRY[0] + 2},{bm.FOREST_ENTRY[1] - 1}',
     {'map': bm.FOREST, 'poke': wc.DAY}),
    ('bm_forest_out', 'walk', 'left:80', {'field': True, 'poke': wc.DAY}),
    # 입구 블록 칸까지 걷는다(누름 길이로 걸으면 snes9x 에서 입구에 못 닿았다). 48/00 을 거쳐 숲 어귀 (0,31)에 내린 뒤에도
    # 걷기가 그 칸 쪽(오른쪽)으로 이어 걸어 나무에 막힌 (4,31)에서 멈춘다. 그 줄은 숲 어귀로만 닿는다
    ('bm_forest_in', 'walk', f'{BM_FOX_GATE[0]},{BM_FOX_GATE[1]}',
     {'map': bm.FOREST, 'cell': (bm.FOREST_ENTRY[0] + 4, bm.FOREST_ENTRY[1]), 'changes': 2, 'after': 300,
      'poke': wc.DAY}),
    # 다리: 고치기 전에는 본몰에서 나가 다리 서쪽 칸(FC (6E,4F))에서 동쪽으로 걸어도 그 자리
    ('bm_castle_gate', 'warp', f'{bm.CASTLE},{BM_GATE[0]},{BM_GATE[1] - 1}', {'map': bm.CASTLE, 'poke': wc.DAY}),
    ('bm_castle_out', 'walk', 'down:64', {'field': True, 'poke': wc.DAY}),
    ('bm_bridge_shut', 'walk', f'{BM_WEST[0]},{BM_FIELD_GATE[1]};{BM_WEST[0]},{BM_WEST[1]};right:60;wait:30',
     {'field': True, 'cell': BM_WEST, 'off': ['BM_BRIDGE'], 'poke': wc.DAY}),
    # 여우를 쫓은 뒤 왕에게 말을 걸면 다리가 고쳐진다
    ('bm_king', 'warp', f'{bm.CASTLE},{bm.KING[0]},{bm.KING[1] + 1}', {'map': bm.CASTLE, 'poke': wc.DAY}),
    ('bm_bridge', 'walk', talk('up', 6), {'want': ['BM_BRIDGE'], 'poke': wc.DAY}),
    # 고친 뒤에는 같은 길로 다리를 건너 동쪽 섬(FC (71,4F))에 선다
    ('bm_castle_gate2', 'warp', f'{bm.CASTLE},{BM_GATE[0]},{BM_GATE[1] - 1}', {'map': bm.CASTLE, 'poke': wc.DAY}),
    ('bm_castle_out2', 'walk', 'down:64', {'field': True, 'poke': wc.DAY}),
    ('bm_bridge_open', 'walk', f'{BM_WEST[0]},{BM_FIELD_GATE[1]};{BM_WEST[0]},{BM_WEST[1]};{BM_EAST[0]},{BM_EAST[1]}',
     {'field': True, 'cell': BM_EAST, 'poke': wc.DAY}),
    # 편지: 왕자의 편지를 가진 채 모니카에게 말을 걸면 왕의 편지로 바뀌고, 그것을 가진 채 본몰 왕에게
    ('bm_monica_side', 'warp', f'{bm.ENDOR_THRONE},{bm.MONICA[0]},{bm.MONICA[1] + 1}',
     {'map': bm.ENDOR_THRONE, 'set': f'{BM_SLOT2}={bm.PRINCE_LETTER:02X}', 'poke': wc.DAY}),
    ('bm_monica', 'walk', talk('up', 24), {'want': ['BM_LETTER1'], 'bytes': {'BM_SLOT2': bm.KING_LETTER},
                                           'poke': wc.DAY}),
    ('bm_king_side', 'warp', f'{bm.CASTLE},{bm.KING[0]},{bm.KING[1] + 1}',
     {'map': bm.CASTLE, 'set': f'{BM_SLOT2}={bm.KING_LETTER:02X}', 'poke': wc.DAY}),
    ('bm_king_letter', 'walk', talk('up', 12), {'want': ['BM_LETTER2'], 'bytes': {'BM_SLOT2': 0xFF}, 'poke': wc.DAY}),
]


def hero_cases():
    """말을 건 쪽과 상관없이 장면 뒤 조작이 돌아오고 인물이 주인공을 지나가지 않는지. 여우 장면은 촌장 오른쪽에서(걷기
    검사는 왼쪽), 왕자는 아래에서(걷기 검사는 오른쪽) 말을 건다."""
    cx, cy = bm.CHIEF
    px, py = bm.PRINCE['day']
    wx, wy = bm.FOREST_WAKE
    return {'bm-fox-right': {'warp': f'{bm.FOX_TOWN},{cx + 2},{cy - 1}', 'set': '21FF|02',
                             'walk': f'{talk("left", 4)};wait:400;{taps(16, 80)};wait:600;{CLOSE}',
                             'free': f'{wx},{wy - 4}', 'want': [('BM_FOXED', bm.FOXED)], 'map': bm.FOREST, 'maxf': 7000},
            'bm-prince-below': {'warp': f'{bm.CASTLE},{px},{py + 1}', 'set': '',
                                'walk': f'{talk("up", 10)};wait:300', 'free': f'{px + 4},{py + 2}',
                                'want': [('BM_PRINCE_MET', bm.PRINCE_MET)], 'map': bm.CASTLE, 'maxf': 3000}}


PASS_NO_DEVICE = {
    bm.SCRIPTS['fox'][2]: '숲의 여우: 장면 동안 주인공은 (04,0C)에 묶이고 여우는 (05,0D)→(05,04) 열로만 걸음(bm-fox-right 사례 겹침 0)',
    bm.SCRIPTS['gaade'][2]: '돈 가아데: 주인공 아래 줄(FC Y 0D)로만 걸음(bm-fox-right 사례 겹침 0)',
}
