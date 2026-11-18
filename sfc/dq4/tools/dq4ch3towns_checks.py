"""3장 마을 사람(dq4ch3towns)의 검사 표. 내놓는 것은 dq4eventchecks 머리말.

파수꾼이 말한 뒤 일행을 내보내는 자리를 본다. 두 파수꾼은 걸어 다니는 사람이라 인물 이동 간격(7E:3300 + 칸)을 0 으로
붙들어 처음 칸에 세운다.
"""
import dq4ch1walkcheck as wc
import dq4ch3event as ch3
import dq4ch3towns as W

# 인물 칸 08~1F 의 이동 간격을 0 으로(dq4screencheck.SHOP_HOLD 와 같음)
HOLD = ';'.join(f'7E{0x3300 + slot:04X}=00' for slot in range(0x08, 0x20))


def _below(mp, fc):
    """FC 칸 fc 의 사람 바로 아래 셀에 내리는 순간이동 인자(순간이동은 TO 의 한 셀 아래에 내린다)."""
    x, y = W.cell(fc[0], fc[1] + 1)
    return f'{mp},{x},{y - 1}'


def _out(name):
    mp, fc = W.OUT_TO[name]
    return mp, W.cell(*fc)


FLAGS = {'TOWNS_SCOLDED': wc.flag(W.NANNY_SCOLDED),
         # 톨네코 물건 칸 0·1 과 금화(방어구 매입)
         'TOWNS_ITEM0': (ch3.PARTY_ITEMS, 0xFF), 'TOWNS_ITEM1': (ch3.PARTY_ITEMS + 1, 0xFF),
         'TOWNS_GOLD0': (ch3.GOLD_AT, 0xFF), 'TOWNS_GOLD1': (ch3.GOLD_AT + 1, 0xFF), 'TOWNS_GOLD2': (ch3.GOLD_AT + 2, 0xFF)}
LEATHER = 0x48                 # DQ5 かわのよろい(FC 26, 값 180)
CLUB = 0x02                    # DQ5 こんぼう(무기: 사지 않음)
# 물건 칸 0·1 = かわのよろい·こんぼう(장비 비트 없음), 나머지 빈 칸, 금화 0
BUY_SET = ';'.join([f'{(ch3.PARTY_ITEMS & 0xFFFF) + k:04X}={v:02X}' for k, v in enumerate([LEATHER, CLUB] + [0xFF] * 10)] +
                   [f'{(ch3.EQUIP & 0xFFFF) + k:04X}=00' for k in range(2)] +
                   [f'{(ch3.GOLD_AT & 0xFFFF) + k:04X}=00' for k in range(3)])
BUYER = W.cell(0x04, 0x15)
# 엔돌 카지노(열린 목록: 굴 공사 재개 RESUMED). 코인 수는 DQ5 7E:203C(16비트)
COINS = 0x7E203C
FLAGS.update({'TOWNS_COIN0': (COINS, 0xFF), 'TOWNS_COIN1': (COINS + 1, 0xFF)})
# 슬롯 화면 안의 코인(7E:1216, 슬롯을 나올 때 7E:203C 로 옮김)
FLAGS.update({'POKER_RANK': (0x7E1228, 0xFF)})   # FC 포커 판정한 패(dq4fcpoker !pk_rank)
FLAGS.update({'TOWNS_SLOT_COIN0': (0x7E1216, 0xFF), 'TOWNS_SLOT_COIN1': (0x7E1217, 0xFF)})
SELLER = W.cell(0x18, 0x02)
EXCHANGE = W.cell(0x1C, 0x08)
SLOT = W.cell(*W.SLOT_CELLS[2])
POKER = W.cell(0x13, 0x0B)
POKER_DECK = 0x7E1280          # dq4fcpoker !deck(앞 다섯이 손)
GAME_RNG = 0x7E075B
ARENA = W.cell(0x08, 0x0A)
ARENA_RNG = '7E075B=11;7E075C=22;7E075D=33'
# 시합 동안 셋째 몬스터(몬스터 칸 2, 7E:07C0 + 칸 × 16 의 +2 HP)를 999 로 묶어 난수와 상관없이 셋째가 이기게 한다
ARENA_STRONG = '7E07E2=E7;7E07E3=03'
MAGIC_WATER = 0xA9              # DQ5 まほうのせいすい(FC 경품 첫 줄 5A)


def _resumed():
    import dq4ch3tunnel as tunnel
    return f'{0x2190 + tunnel.RESUMED[0]:04X}|{tunnel.RESUMED[1]:02X}'


def _gold(n):
    return ';'.join(f'{(ch3.GOLD_AT & 0xFFFF) + k:04X}={n >> 8 * k & 0xFF:02X}' for k in range(3))


def _slot_rng(fill):
    return ';'.join(f'{GAME_RNG + k:06X}={fill:02X}' for k in range(3))


def _coins(n):
    return ';'.join(f'{(COINS & 0xFFFF) + k:04X}={n >> 8 * k & 0xFF:02X}' for k in range(2))
YES_A = 'a:8;wait:60'
NO = 'wait:60;down:8;wait:40;a:8;wait:60'
# 본몰 왕자 낮 자리(FC (01,0B))의 오른쪽 셀과 유모(FC (06,07)) 아래 셀. 왕자 방은 FC 열 06 의 줄 09 가 벽이라 열 04 로 오른다
PRINCE_RIGHT = W.cell(0x02, 0x0B)
# 쫓겨난 방문의 유모는 FC (04,09)까지 걸어와 선다(본몰 모듈)
NANNY_BELOW = W.cell(0x04, 0x0A)
PRINCE_HOLD = '7E3308=00'

SEGMENTS = [
    # 격투장(DQ5 대화 0E, 시합은 FC 3장 표). 게임 난수(7E:075B~075D)는 매 프레임 굴러(가만히 서 있어도 30프레임에
    # 4A, 31프레임에 4B) 코어마다 늦는 프레임 수가 달라 시합 고르기·승패가 갈린다. 말 거는 동안은 난수를 묶어 시합을
    # FC 4번(슬라임 5.0·오두방정메뚜기 5.3·가위 사슴 벌레 3.9·슬라임 베스 3.9)으로 정하고, 시합 동안은 난수를 풀고
    # (내내 묶으면 전투가 같은 고리에서 멈춤) 셋째 HP 를 묶어(ARENA_STRONG) 셋째가 이기게 한다. 수 창에서 위 한 번에
    # 2장씩 늘어 위 넷이면 9장: 셋째에 걸면 이겨 91 + 9 × 3.9(반올림 35) = 126, 첫째에 걸면 져 91. 시합을 여는 A 는
    # 시합 구간에 둔다(앞 구간에서 전투에 들면 dq4peoplesample 이 시합을 전투로 세지 못함)
    *(seg for k, (pick, coins) in enumerate(((2, 126), (0, 91)))
      for seg in ((f'towns_arena_{("win", "lose")[k]}_side', 'warp', f'{W.CASINO},{ARENA[0]},{ARENA[1] + 1}',
                   {'map': W.CASINO, 'poke': f'{wc.DAY};{HOLD}', 'set': ';'.join((_resumed(), _coins(100)))}),
                  (f'towns_arena_{("win", "lose")[k]}', 'walk',
                   f'up:8;wait:30;{";".join(["a:8;wait:90"] * 4)};wait:60;{"down:8;wait:30;" * pick}'
                   f'wait:{38 * (3 - pick) + 1};a:8;wait:90;{"up:2;wait:14;" * 4}a:8;wait:100',
                   {'map': W.CASINO, 'poke': f'{wc.DAY};{HOLD};{ARENA_RNG}',
                    'bytes': {'TOWNS_COIN0': 91, 'TOWNS_COIN1': 0}}),
                  (f'towns_arena_{("win", "lose")[k]}_fight', 'walk', f'a:8;wait:3000;{";".join(["b:8;wait:150"] * 6)}',
                   {'map': W.CASINO, 'poke': f'{wc.DAY};{HOLD};{ARENA_STRONG}',
                    'bytes': {'TOWNS_COIN0': coins, 'TOWNS_COIN1': 0}}))),
    # 슬롯(FC 기계 칸 가운데, 아래에서 위를 보고 말 걸기 → DQ5 1코인 기계): 583·584 에 「예」, 위로 한 장 넣으면 슬롯 안
    # 코인이 99. 돌린 뒤 배당은 코어 난수에 따라 달라 코인은 넣은 뒤에만 본다
    ('towns_slot_side', 'warp', f'{W.CASINO},{SLOT[0]},{SLOT[1] + 1}',
     {'map': W.CASINO, 'poke': f'{wc.DAY};{HOLD}', 'set': ';'.join((_resumed(), _coins(100)))}),
    ('towns_slot', 'walk', f'up:8;wait:30;{";".join(["a:8;wait:90"] * 4)};wait:200;up:8;wait:60',
     {'map': W.CASINO, 'poke': f'{wc.DAY};{HOLD}', 'bytes': {'TOWNS_SLOT_COIN0': 99, 'TOWNS_SLOT_COIN1': 0}}),
    # FC 슬롯 한 판(기계 2, 코인 둘 = 가운데·위 줄). 릴 처음 자리는 게임 난수(00:953A)로 고르므로 판 동안 7E:075B~075D 를
    # 묶어 결과를 정한다: 모두 00 이면 배당 10 이라 100 − 2 + 10 = 108, 모두 11 이면 맞는 줄이 없어 98.
    # 「한 번 더?」 에 B(아니오)로 나온다
    *(seg for name, fill, coins in (('win', 0x00, 108), ('lose', 0x11, 98))
      for seg in ((f'towns_slot_{name}_side', 'warp', f'{W.CASINO},{SLOT[0]},{SLOT[1] + 1}',
                   {'map': W.CASINO, 'poke': f'{wc.DAY};{HOLD}', 'set': ';'.join((_resumed(), _coins(100)))}),
                  (f'towns_slot_{name}', 'walk', f'up:8;wait:30;{";".join(["a:8;wait:90"] * 4)};wait:200;up:4;wait:30;'
                   'up:4;wait:30;a:4;wait:700;b:8;wait:300',
                   {'map': W.CASINO, 'poke': f'{wc.DAY};{HOLD};{_slot_rng(fill)}',
                    'bytes': {'TOWNS_COIN0': coins, 'TOWNS_COIN1': 0}}))),
    # FC 포커 한 판. 섞기는 게임 난수(00:953A, $075B~075D 를 NMI 가 매 프레임 올림)라 코어마다 덱이 갈리므로, 판 동안
    # 덱 앞 다섯(7E:1280~, 손)을 묶고 다섯 장을 모두 남긴다(바꿔 넣기가 없어 묶은 손 그대로). 패(!pk_rank)와 나온 뒤
    # 코인(7E:203C, 포커를 나올 때 옮겨짐)을 본다. 카드 = 숫자(A 0 … K 12) × 4 + 무늬
    # - take: 9 9 9 2 K → 스리 카드(배당 2), 더블 업 아니오 → 100 − 1 + 2 = 101
    # - double_win: 9 9 9 K K → 풀 하우스(8), 더블 업 예 → 펴 보인 9 보다 넷째 K 가 셈 → 16, 다음 도전 아니오 → 115
    # - double_lose: 9 9 9 3 3 → 풀 하우스, 넷째 3 이 약함 → 99
    # - nothing: 2 5 7 9 J(무늬 섞임) → 패 없음 → 99
    *(seg for name, hand, tail, rank, coins in (
        ('take', (32, 33, 34, 4, 48), 'b:4;wait:60;b:4;wait:200', 7, 101),
        ('double_win', (32, 33, 34, 48, 49), 'a:4;wait:120;right:4;wait:20;right:4;wait:20;a:4;wait:300;b:4;wait:100;'
                                              'b:4;wait:100;b:4;wait:200', 4, 115),
        ('double_lose', (32, 33, 34, 8, 9), 'a:4;wait:120;right:4;wait:20;right:4;wait:20;a:4;wait:300;b:4;wait:100;'
                                             'b:4;wait:100;b:4;wait:200', 4, 99),
        ('nothing', (4, 17, 26, 35, 40), 'b:4;wait:100;b:4;wait:200', 0xFF, 99))
      for seg in ((f'towns_poker_{name}_side', 'warp', f'{W.CASINO},{POKER[0]},{POKER[1] + 1}',
                   {'map': W.CASINO, 'poke': f'{wc.DAY};{HOLD}', 'set': ';'.join((_resumed(), _coins(100)))}),
                  (f'towns_poker_{name}', 'walk', f'up:8;wait:30;{";".join(["a:8;wait:90"] * 3)};wait:200;a:4;wait:300;'
                   f'{"a:4;wait:20;right:4;wait:20;" * 4}a:4;wait:20;down:4;wait:30;a:4;wait:200;{tail}',
                   {'map': W.CASINO,
                    'poke': f'{wc.DAY};{HOLD};' + ';'.join(f'{POKER_DECK + k:06X}={c:02X}' for k, c in enumerate(hand)),
                    'bytes': {'TOWNS_COIN0': coins, 'TOWNS_COIN1': 0, 'POKER_RANK': rank}}))),
    # 코인 판매(DQ5 대화 0B): 금화 1000 에서 한 장(3장 한 장 200)
    ('towns_coin_side', 'warp', f'{W.CASINO},{SELLER[0]},{SELLER[1] + 3}',
     {'map': W.CASINO, 'poke': f'{wc.DAY};{HOLD}', 'set': ';'.join((_resumed(), _gold(1000), _coins(0)))}),
    # 코인 교환(DQ5 대화 0C, 경품은 FC 04/01 목록): 코인 30 으로 첫 경품 まほうのせいすい(30)
    ('towns_prize_side', 'warp', f'{W.CASINO},{EXCHANGE[0] - 4},{EXCHANGE[1] - 1}',
     {'map': W.CASINO, 'poke': f'{wc.DAY};{HOLD}', 'set': ';'.join((_resumed(), _coins(30)))}),
    ('towns_prize', 'walk', f'right:8;wait:30;a:8;wait:60;a:8;wait:120;{";".join(["a:8;wait:90"] * 8)};{wc.pc.CLOSE}',
     {'map': W.CASINO, 'poke': f'{wc.DAY};{HOLD}', 'bytes': {'TOWNS_COIN0': 0, 'TOWNS_COIN1': 0},
      'items': [MAGIC_WATER]}),
    ('towns_coin_buy', 'walk', f'up:8;wait:30;a:8;wait:60;a:8;wait:120;a:8;wait:90;a:8;wait:120;up:8;wait:40;'
     f'{";".join(["a:8;wait:90"] * 6)};{wc.pc.CLOSE}',
     {'map': W.CASINO, 'poke': f'{wc.DAY};{HOLD}'}),
    # 본몰 방어구 매입(FC 대화 060): 「예」 → 첫 물건 かわのよろい 를 골라 「예」(금화 + 값, 칸이 빔) → 「또」 「예」 →
    # 둘째로 당겨진 こんぼう 를 고르면 082D → 「또」 「아니오」 로 0833
    ('towns_buyer_side', 'warp', f'{W.BONMALMO},{BUYER[0]},{BUYER[1] + 1}',
     {'map': W.BONMALMO, 'poke': f'{wc.DAY};{HOLD}', 'set': BUY_SET}),
    ('towns_buy_armor', 'walk',
     f'up:8;wait:30;a:8;wait:60;a:8;wait:120;{YES_A};a:8;wait:120;a:8;wait:120;a:8;wait:120;{YES_A};a:8;wait:120;'
     f'{YES_A};a:8;wait:120;a:8;wait:120;a:8;wait:120;{NO};a:8;wait:120;a:8;wait:120;{wc.pc.CLOSE}',
     {'map': W.BONMALMO, 'bytes': {'TOWNS_ITEM0': CLUB, 'TOWNS_ITEM1': 0xFF, 'TOWNS_GOLD1': 0, 'TOWNS_GOLD2': 0},
      'poke': f'{wc.DAY};{HOLD}'}),

    # 본몰 왕자를 낮에 처음 만나 쫓겨난 그 방문에 유모에게 말을 걸면 03B1(본몰 NANNY_SCOLDED). 다시 든 방문의 0836 은
    # npccheck 상태 towns_prince
    ('towns_prince_side', 'warp', f'{W.BONMALMO},{PRINCE_RIGHT[0]},{PRINCE_RIGHT[1] - 1}',
     # 앞 묶음들이 켠 편지·왕자 flag 를 끈다(왕자가 첫 만남 갈래로 가게)
     # 붙든 이동 간격은 상태에 남는다. 유모가 걸어와야 해서 낮 왕자(인물 칸 4)만 붙든다
     {'map': W.BONMALMO, 'poke': f'{wc.DAY};{PRINCE_HOLD}',
      'set': f'{0x2190 + W.PRINCE_MET[0]:04X}&{~(W.PRINCE_MET[1] | W.LETTER1[1] | 0x20) & 0xFF:02X}'}),
    ('towns_nanny_scolded', 'walk',
     f'{wc.talk("left", 10)};wait:200;{NANNY_BELOW[0]},{PRINCE_RIGHT[1]};{NANNY_BELOW[0]},{NANNY_BELOW[1]};'
     f'{wc.talk("up", 4)}',
     {'map': W.BONMALMO, 'cell': NANNY_BELOW, 'want': ['TOWNS_SCOLDED'], 'poke': f'{wc.DAY};{PRINCE_HOLD}'}),

    # 본몰 감옥 병사(FC 05/00 (0A,0E), 대화 066): 말한 뒤 성 05/01 (19,02)로
    ('towns_jail_side', 'warp', _below(W.PRISON, (0x0A, 0x0E)),
     {'map': W.PRISON, 'poke': f'{wc.DAY};{HOLD}'}),
    ('towns_jail_out', 'walk', f'{wc.talk("up", 4)};wait:300',
     {'map': _out('jail_out')[0], 'cell': _out('jail_out')[1], 'changes': 1, 'after': 120, 'poke': f'{wc.DAY};{HOLD}'}),
    # 엔돌 성 1층 밤 파수꾼(FC 04/02 (0C,1C), 대화 028): 말한 뒤 마을 04/00 (17,0A)로
    ('towns_night_side', 'warp', _below(W.ENDOR_HALL, (0x0C, 0x1C)),
     {'map': W.ENDOR_HALL, 'poke': f'{wc.NIGHT};{HOLD}'}),
    ('towns_night_out', 'walk', f'{wc.talk("up", 4)};wait:300',
     {'map': _out('night_out')[0], 'cell': _out('night_out')[1], 'changes': 1, 'after': 120,
      'poke': f'{wc.NIGHT};{HOLD}'}),
]
