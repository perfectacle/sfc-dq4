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
SELLER = W.cell(0x18, 0x02)
EXCHANGE = W.cell(0x1C, 0x08)
ARENA = W.cell(0x08, 0x0A)
MAGIC_WATER = 0xA9              # DQ5 まほうのせいすい(FC 경품 첫 줄 5A)


def _resumed():
    import dq4ch3tunnel as tunnel
    return f'{0x2190 + tunnel.RESUMED[0]:04X}|{tunnel.RESUMED[1]:02X}'


def _gold(n):
    return ';'.join(f'{(ch3.GOLD_AT & 0xFFFF) + k:04X}={n >> 8 * k & 0xFF:02X}' for k in range(3))


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
    # 격투장 맞은편에서 코인 100
    ('towns_arena_side', 'warp', f'{W.CASINO},{ARENA[0]},{ARENA[1] + 1}',
     {'map': W.CASINO, 'poke': f'{wc.DAY};{HOLD}', 'set': ';'.join((_resumed(), _coins(100)))}),
    # 격투장(DQ5 대화 0E, 시합은 FC 3장 표): 첫 몬스터에 한 장 걸면 시합 전에 코인이 준다. 이기고 지는 것은 시합과
    # 코어(MesenCE·snes9x·bsnes)의 난수에 따라 달라 코인은 건 뒤에만 본다
    ('towns_arena', 'walk', f'up:8;wait:30;{";".join(["a:8;wait:90"] * 7)}',
     {'map': W.CASINO, 'poke': f'{wc.DAY};{HOLD}', 'bytes': {'TOWNS_COIN0': 99, 'TOWNS_COIN1': 0}}),
    # 시합 뒤에는 B 로 글을 넘기고 「다시 도전」 에 아니오(시합 길이가 표에 따라 달라 A 수로 맞추지 않음)
    ('towns_arena_end', 'walk', f'{";".join(["b:8;wait:90"] * 40)}', {'map': W.CASINO}),
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
