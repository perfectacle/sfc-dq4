"""텐페 제물 사건(앞 절반은 dq4ch2event, 보스 전투와 뒤 절반은 dq4ch2tempe)의 검사 표. 내놓는 것은 dq4eventchecks 머리말."""
import dq4ch1walkcheck as wc
import dq4ch2event as ch2
import dq4ch2tempe as tempe
from dq4ch2walkparts import CLOSE, flag, set_flags, talk, talk_yes, taps

FLAGS = {
    'TEMPE_HEARD': flag(ch2.TEMPE_HEARD),
    'TEMPE_GONE': flag(ch2.TEMPE_GONE),
    'TEMPE_ALTAR': flag(ch2.TEMPE_ALTAR),
    'TEMPE_WON': flag(tempe.WON),
}

# 신부에게 대신 간다 → 바구니 서술. 제단 앞에 닿으면 곧 보스 전투(dq4ch2tempe)다
def ask_talk(face):
    """그 쪽을 보고 말을 걸어 신부의 물음이 뜰 때까지 넘기고 「예」(dq4walk.lua ask·cursor), 이어 바구니 서술을 넘긴다. 말 끝의
    B 가 물음에 「아니요」 로 답하지 않게 talk 의 끝 닫기는 두지 않는다."""
    return f'{face}:8;wait:30;a:8;wait:60;a:8;wait:60;ask:900;cursor:0;{taps(14)}'


BASKET = ask_talk('up') + ';wait:600;' + taps(10)
# 지면 FC 2장 시작 귀환 자리(サラン 교회 45/02, dq4fieldtravel 의 2장 칸)에서 다시 시작한다
WIPE_MAP, WIPE_CELL = '45/02', (8, 19)
# 아침의 제단 위에서 곧장 아래로(교회를 지나) 촌장 위 칸까지 걸어 내려온다
LEAVE_ALTAR = f'{tempe.CHIEF_TALK_CELL[0]},{tempe.CHIEF_TALK_CELL[1]}'

SEGMENTS = [
    # 텐페 제물 사건 앞 절반: 촌장의 부탁 → 신부에게 대신 간다 → 바구니로 제단 앞(밤)
    ('chief_side', 'warp', f'{ch2.TEMPE},{ch2.CHIEF[0]},{ch2.CHIEF[1] + 1}', {'map': ch2.TEMPE}),
    ('chief', 'walk', talk_yes('up', 10), {'want': ['TEMPE_HEARD']}),
    # 텐페 뒤 절반: 바구니로 제단 앞에 닿으면 보스 전투(dq4ch2tempe). 지면 기록한 교회(サラン)로 가고 앞 절반 flag 가
    # 꺼져 촌장에게 다시 듣는다. 이기면 서술 뒤 아침의 제단 앞, 괴물이 사라진 뒤의 마을
    ('lose_side', 'warp', f'{ch2.TEMPE},{ch2.PRIEST[0]},{ch2.PRIEST[1] + 1}', {'map': ch2.TEMPE}),
    ('lose', 'walk', BASKET + ';' + taps(40, 40) + ';wait:300;' + CLOSE,
     {'battle': 'lose', 'off': ['TEMPE_HEARD', 'TEMPE_GONE', 'TEMPE_ALTAR', 'TEMPE_WON'], 'map': WIPE_MAP,
      'cell': WIPE_CELL}),
    ('rechief_side', 'warp', f'{ch2.TEMPE},{ch2.CHIEF[0]},{ch2.CHIEF[1] + 1}', {'map': ch2.TEMPE}),
    ('rechief', 'walk', talk_yes('up', 10), {'want': ['TEMPE_HEARD']}),
    ('priest_side', 'warp', f'{ch2.TEMPE},{ch2.PRIEST[0]},{ch2.PRIEST[1] + 1}', {'map': ch2.TEMPE}),
    ('priest', 'walk', BASKET + ';' + taps(110, 40) + ';wait:600;' + taps(6) + ';' + CLOSE,
     {'battle': 'win', 'poke': wc.HERO_HP, 'want': ['TEMPE_WON'], 'off': ['TEMPE_HEARD', 'TEMPE_GONE', 'TEMPE_ALTAR'],
      'map': ch2.TEMPE, 'cell': tempe.MORNING_CELL}),
    ('leave_altar', 'walk', LEAVE_ALTAR, {'map': ch2.TEMPE, 'cell': tempe.CHIEF_TALK_CELL}),
    ('chief_won', 'walk', talk('down', 6), {'want': ['TEMPE_WON'], 'map': ch2.TEMPE}),
]

# 텐페 신부(3D/03 (24,49)): 촌장에게 들은 뒤 예 → 바구니 이벤트로 제단 두 칸 아래에 닿아 보스 전투(dq4ch2tempe,
# 몬스터를 약하게 덮고 HP 를 채워 이김) → 아침의 같은 자리. 끝에 마을 쪽으로 걸어 내려간다
# 보스 전투 동안 아리나 혼자 버티게 HP 를 999 로(일행 기록 0 의 지금 HP)
HERO_FULL = '2042=E7;2043=03'
PRIEST = [('priest-below', '24,51', 'up'), ('priest-left', '22,51;22,49', 'right'),
          ('priest-right', '26,51;26,49', 'left')]


def hero_cases():
    heard = set_flags(ch2.TEMPE_HEARD)
    px, py = ch2.PRIEST
    mx, my = tempe.MORNING_CELL
    return {name: {'warp': f'{ch2.TEMPE},{px},{py + 1}', 'set': ';'.join((heard, HERO_FULL)),
                   'walk': f'{at};{ask_talk(face)};wait:600;{taps(10)};{taps(110, 40)};wait:600;{taps(6)};{CLOSE}',
                   'free': f'{mx},{my + 6}', 'battle': 'win', 'want': [('TEMPE_WON', tempe.WON)],
                   'not': [('TEMPE_ALTAR', ch2.TEMPE_ALTAR)], 'hero_at': tempe.MORNING_CELL, 'maxf': 12000}
            for name, at, face in PRIEST}
