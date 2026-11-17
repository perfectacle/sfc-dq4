"""왕의 병과 여행의 문 사당(dq4ch2king)의 검사 표. 내놓는 것은 dq4eventchecks 머리말."""
import dq4ch1walkcheck as wc
import dq4ch2endor as endor
import dq4ch2event as ch2
import dq4ch2king as king
from dq4ch2walkparts import CLOSE, flag, set_flags, talk, taps

FLAGS = {
    'KING_BAZAAR': flag(king.BAZAAR),
    'KING_HEARD': flag(king.HEARD),
    'KING_SEEN': flag(king.SEEN),
    'KING_GOT': flag(king.GOT),
    'KING_CURED': flag(king.CURED),
}

# 탑 꼭대기에서 찾은 지저귐의 꿀. 묶음마다 따로 시작하므로 크리프트(일행 기록 1, 물건 둘)의 셋째 칸에 둔다. 주인공의
# 칸은 앞 사건의 물건과 겹친다
HONEY_SET = f'{(ch2.JOIN_RECORDS_AT & 0xFFFF) + 0x16 + 2:04X}={king.HONEY:02X}'


def effects(data):
    return {'honey': {'set': HONEY_SET}}


# 엔돌 쪽 사당 문 (6,7)에서 아래 입구로 나가 필드 (174,167), 필드를 걸어 엔돌 입구 블록 (67,65)로 든다. 사당은 FC
# 1F/00 의 문 쪽 반(왼쪽 기둥 열)을 따라 내려가고, 필드 길은 FC 필드 블록 속성에서 막히지 않은 칸을 이은 것이다
SHRINE_FAR_OUT = '4,7;4,13;0,13;0,29;14,29;down:60;174,167'
ENDOR_ROAD = ('176,167;176,169;178,169;178,171;180,171;180,173;182,173;182,175;184,175;184,177;186,177;'
              '186,179;188,179;188,181;190,181;190,183;196,183;196,197;198,197;198,199;206,199;206,203')

# 바자 병사 → 왕좌의 방 병사 → 사당이 막힘 → 탑 꼭대기의 엘프와 꿀 → 왕 회복 → 사당의 여행의 문
SEGMENTS = [
    ('bazaar_side', 'warp', f'{king.BAZAAR_MAP},{king.BAZAAR_SOLDIER[0]},{king.BAZAAR_SOLDIER[1] + 1}',
     {'map': king.BAZAAR_MAP}),
    ('bazaar', 'walk', talk('up'), {'want': ['KING_BAZAAR']}),
    # 계단 아래 칸에서 위로 걸어 계단 위 줄에 들면 병사가 알린다
    ('throne_side', 'warp', f'{ch2.THRONE},24,36', {'map': ch2.THRONE}),
    ('throne', 'walk', '24,34;wait:120;' + taps(4, 60) + ';' + CLOSE, {'want': ['KING_HEARD']}),
    # 왕이 낫기 전에는 사당 병사가 위 방으로 가는 틈에 서 있어 여행의 문에 닿지 못한다
    ('closed_side', 'warp', f'{king.SHRINE},10,20', {'map': king.SHRINE}),
    ('closed', 'walk', '10,15;8,15;8,11;wait:60;' + taps(4, 60) + ';' + CLOSE,
     {'map': king.SHRINE, 'maxf': 1500, 'cell': (8, 15)}),
    # 탑 꼭대기: 계단 옆에서 위로 걸어 줄 0C 에 들면 엘프가 달아나고, 엘프가 섰던 칸을 밟으면 꿀을 찾는다
    ('tower_side', 'warp', f'{king.TOWER_TOP},14,28', {'map': king.TOWER_TOP}),
    ('tower', 'walk', '14,25;wait:60;' + taps(6, 60) + ';wait:200', {'want': ['KING_SEEN']}),
    ('honey', 'walk', '16,18;wait:60;' + taps(3, 60) + ';' + CLOSE, {'want': ['KING_GOT']}),
    # 꿀을 가진 채 왕에게 말을 걸면 먹이고 왕이 낫는다. 먹인 꿀은 크리프트의 칸에서 빠진다
    ('cure_side', 'warp', f'{ch2.THRONE},{ch2.START_CELL[0]},{ch2.START_CELL[1] - 1}', {'map': ch2.THRONE}),
    ('cure', 'walk', talk('up', 20), {'want': ['KING_CURED'], 'bytes': {'KIRYL_ITEM2': 0xFF}}),
    # 병사가 비켜선 사당: 위 방의 여행의 문으로 엔돌 쪽 사당에 닿는다
    ('shrine_side', 'warp', f'{king.SHRINE},10,20', {'map': king.SHRINE}),
    ('shrine', 'walk', '10,15;8,15;8,11;10,11;10,7', {'map': king.SHRINE_FAR, 'changes': 1}),
    ('shrine_out', 'walk', SHRINE_FAR_OUT, {'field': True, 'cell': (174, 167), 'poke': wc.DAY}),
    ('endor_road', 'walk', ENDOR_ROAD, {'map': endor.TOWN, 'changes': 1, 'after': 60, 'poke': wc.DAY, 'maxf': 4000}),
]


def hero_cases():
    """칸으로 거는 장면을 들어서는 쪽마다. 걸린 뒤 다시 걸을 수 있어야 한다(free)."""
    out = {}
    # 바자: 오른쪽에서 X 09 줄을 지나 왼쪽으로
    out['bazaar-left'] = {'warp': f'{king.BAZAAR_MAP},26,22', 'set': '', 'walk': f'16,23;wait:60;{taps(3)};{CLOSE}',
                          'free': '24,23', 'want': [('KING_BAZAAR', king.BAZAAR)], 'maxf': 2500}
    # 왕좌의 방 계단 위 줄은 출발 상태가 그 맵이라 순간이동할 수 없어(같은 맵) 걷기 검사의 throne 구간이 본다
    heard = set_flags(king.BAZAAR, king.HEARD)
    # 탑 꼭대기: 계단 옆과 오른쪽에서 위로 줄 0C 에 든다. 꿀은 오른쪽에서 엘프가 섰던 칸에
    for name, warp, at in (('elves-up', '14,28', '14,25'), ('elves-right', '24,28', '24,25')):
        out[name] = {'warp': f'{king.TOWER_TOP},{warp}', 'set': heard, 'walk': f'{at};wait:60;{taps(6, 60)};wait:200',
                     'free': '22,23', 'want': [('KING_SEEN', king.SEEN)], 'maxf': 3000}
    out['honey-left'] = {'warp': f'{king.TOWER_TOP},24,18', 'set': set_flags(king.BAZAAR, king.HEARD, king.SEEN),
                         'walk': f'18,19;wait:60;{taps(3, 60)};{CLOSE}', 'free': '24,21',
                         'want': [('KING_GOT', king.GOT)], 'maxf': 2500}
    return out


PASS_NO_DEVICE = {
    king.SCRIPTS[king.USE[name]]: '탑 꼭대기 엘프: 주인공이 줄 0C(셀 Y 26) 아래에서 들어설 때 걸리고, 엘프는 그보다 위 '
    '셀 Y 17·19 에서 위로만 걸음(elves-up·elves-right 사례 겹침 0)' for name in ('elf_a', 'elf_b')
}
