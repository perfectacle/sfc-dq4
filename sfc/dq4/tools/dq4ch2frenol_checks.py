"""프레놀 가짜 공주·남쪽 동굴(dq4ch2frenol)의 검사 표. 내놓는 것은 dq4eventchecks 머리말."""
import dq4ch1walkcheck as wc
import dq4ch2frenol as frenol
from dq4ch2walkparts import CLOSE, flag, set_flags, talk, taps

FLAGS = {
    'FRENOL_KIDNAPPED': flag(frenol.KIDNAPPED),
    'FRENOL_LEFT': flag(frenol.LEFT),
    'FRENOL_RESCUED': flag(frenol.RESCUED),
    # 묘지 장면 동안만 켜는 flag 다섯(끝에 모두 꺼짐)
    'FRENOL_SCENE': (0x7E2190 + frenol.IDX, frenol.SCENE_BITS),
    'BRACELET_CHEST': (0x7E0000 | frenol.CHEST_OPEN[0], frenol.CHEST_OPEN[1]),
}

# 남쪽 동굴의 상자를 연 기록: 주인공(비단 로브 하나를 가짐)의 둘째 칸에 황금의 팔찌, 상자 열림 비트
BRACELET_SET = f'{(wc.ITEMS & 0xFFFF) + 1:04X}={frenol.BRACELET:02X};{frenol.CHEST_OPEN[0]:04X}|{frenol.CHEST_OPEN[1]:02X}'


def effects(data):
    return {'chest': {'set': BRACELET_SET}}


# 명령 창 → 「조사하기」(dq4chestcheck.SEARCH 를 walk.lua 꼴로)
CHEST_SEARCH = ('a:8;wait:60;down:6;wait:25;down:6;wait:25;down:6;wait:25;right:6;wait:25;a:8;wait:200;'
                'a:4;wait:150;a:4;wait:150;b:4;wait:220')

SEGMENTS = [
    # 프레놀 가짜 공주(dq4ch2frenol): 여관 2층 방 아래 (1E,08)에서 위로 올라가면 비명 → 「멈춰라!」 → 셋이 계단으로
    ('inn_side', 'warp', f'{frenol.INN},60,17', {'map': frenol.INN}),
    ('kidnap', 'walk', '60,16;wait:60;' + taps(1) + ';' + CLOSE + ';60,14;58,14;58,12;wait:60;' + taps(6) + ';wait:400;' + CLOSE,
     {'want': ['FRENOL_KIDNAPPED'], 'map': frenol.INN}),
    # 마을에서는 셋이 서쪽 길로 빠져나간다. 서쪽 어귀 위 (05,06)에서 기다린다
    ('kidnap_town_side', 'warp', f'{frenol.TOWN},10,13', {'map': frenol.TOWN}),
    ('kidnap_town', 'walk', 'wait:1200', {'want': ['FRENOL_LEFT'], 'map': frenol.TOWN}),
    # 납치 뒤에는 여관 주인이 「아이고, 아이고……」 뒤 여관을 연다(FC 대화 033 의 15:BF30). 카운터 아래 (11,0E)에서
    ('inn_open_side', 'warp', f'{frenol.TOWN},34,28', {'map': frenol.TOWN}),
    ('inn_open', 'walk', talk('up', 2), {'map': frenol.TOWN}),
    # 남쪽 동굴: 상자 아래 칸에서 위를 보고 「조사하기」
    ('cave_side', 'warp', f'{frenol.CAVE},20,71', {'map': frenol.CAVE}),
    ('chest', 'walk', 'up:8;wait:30;' + CHEST_SEARCH + ';' + CLOSE,
     {'want': ['BRACELET_CHEST'], 'items': [frenol.BRACELET], 'map': frenol.CAVE}),
    # 밤의 묘지: 서쪽 어귀에서 내려와 (03,0B)에 서면 망토가 요구 → 예 → 메이 → 도적의 열쇠 → 아침의 같은 칸
    ('grave_side', 'warp', f'{frenol.TOWN},6,19', {'map': frenol.TOWN, 'poke': wc.NIGHT}),
    ('grave', 'walk', '6,23;wait:120;' + taps(30, 50) + ';wait:300;' + CLOSE,
     {'want': ['FRENOL_RESCUED'], 'off': ['FRENOL_SCENE'], 'items': [frenol.THIEF_KEY], 'map': frenol.TOWN}),
]

# 여관 2층은 계단 앞 (1E,08)에서 방 줄로 올라간다(셀 60 줄은 Y 05 에서 쓰러진 가짜 크리프트가 막아 58 줄로). 밤의
# 묘지 (03,0B)는 위(3 열)나 왼쪽 (02,0B)에서만 들어선다. -no 는 처음 요구에 아니요
FRENOL_INN = '60,16;wait:60;a:8;wait:50;{close};60,14;58,14;58,12;wait:60;{taps};wait:400;{close}'
FRENOL_GRAVE = [('frenol-grave-above', '6,23', ''), ('frenol-grave-left', '4,23;6,23', ''),
                ('frenol-grave-no', '6,23', 'ask:600;cursor:1;a:8;wait:120;')]


def hero_cases():
    out = {'frenol-inn': {'warp': f'{frenol.INN},60,17', 'set': '', 'walk': FRENOL_INN.format(close=CLOSE, taps=taps(6)),
                          'want': [('FRENOL_KIDNAPPED', frenol.KIDNAPPED)], 'free': '58,14', 'maxf': 3000}}
    night = f'{wc.NIGHT_SET};{(wc.ITEMS & 0xFFFF) + 1:04X}={frenol.BRACELET:02X}'
    for name, at, first in FRENOL_GRAVE:
        out[name] = {'warp': f'{frenol.TOWN},4,19', 'set': ';'.join((set_flags(frenol.KIDNAPPED, frenol.LEFT), night)),
                     'late': wc.NIGHT_SET, 'walk': f'{at};wait:120;{first}{taps(30, 50)};wait:300;{CLOSE}',
                     'want': [('FRENOL_RESCUED', frenol.RESCUED)], 'hero_at': frenol.MORNING_CELL, 'maxf': 6000,
                     'distinct': 8 if first else 7}
    return out


PASS_NO_DEVICE = {
    **{frenol.SCRIPTS[frenol.USE[k]]: '프레놀 여관 2층 납치범: 주인공이 방 줄(FC Y 05)에 오면 조작을 막고 계단 줄(Y 01·02)로만 걸음'
       '(kidnap 구간)' for k in ('inn_cloak_a', 'inn_cloak_b', 'inn_princess')},
    frenol.SCRIPTS[frenol.USE['mei']]: '메이: 주인공을 묘지 (03,0B)에 묶은 채 (06,0B)→(04,0B) 만 걷고, 떠날 때는 깜박이며 사라짐(grave 구간)',
    **{frenol.SCRIPTS[frenol.USE[k]]: '프레놀 마중 둘: 서쪽 어귀 줄(FC Y 06)만 걸음. 주인공은 묘지 (03,0B)에 묶여 있음(grave 구간)'
       for k in ('brey', 'kiryl')},
}


# 조작을 막지 않고 걷는 인물(test_dq4heroblock.WALK_EXEMPT)
WALK_EXEMPT = {
    frenol.SCRIPTS[frenol.USE['trio']]: '프레놀 납치범 셋: 조작을 막지 않고 서쪽 길로 나간다. 주인공이 길에 서면 비킬 때까지 기다린다',
}
