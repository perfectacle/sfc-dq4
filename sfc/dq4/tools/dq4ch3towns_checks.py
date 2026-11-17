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
YES_A = 'a:8;wait:60'
NO = 'wait:60;down:8;wait:40;a:8;wait:60'
# 본몰 왕자 낮 자리(FC (01,0B))의 오른쪽 셀과 유모(FC (06,07)) 아래 셀. 왕자 방은 FC 열 06 의 줄 09 가 벽이라 열 04 로 오른다
PRINCE_RIGHT = W.cell(0x02, 0x0B)
NANNY_BELOW = W.cell(0x06, 0x08)

SEGMENTS = [
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
     {'map': W.BONMALMO, 'poke': f'{wc.DAY};{HOLD}',
      'set': f'{0x2190 + W.PRINCE_MET[0]:04X}&{~(W.PRINCE_MET[1] | W.LETTER1[1] | 0x20) & 0xFF:02X}'}),
    ('towns_nanny_scolded', 'walk',
     f'{wc.talk("left", 10)};wait:200;{W.cell(0x04, 0x0B)[0]},{PRINCE_RIGHT[1]};{W.cell(0x04, 0x08)[0]},{NANNY_BELOW[1]};'
     f'{NANNY_BELOW[0]},{NANNY_BELOW[1]};{wc.talk("up", 4)}',
     {'map': W.BONMALMO, 'cell': NANNY_BELOW, 'want': ['TOWNS_SCOLDED'], 'poke': f'{wc.DAY};{HOLD}'}),

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
