"""레이크나바(dq4ch3lakanaba)의 검사 표. 내놓는 것은 dq4ch3checks 머리말."""
import dq4ch1walkcheck as wc
import dq4ch3event as ch3
import dq4ch3lakanaba as lakanaba
from dq4ch3walkparts import CLOSE, HOP, TOWN, talk, taps

FLAGS = {'BENTO': wc.flag(lakanaba.BENTO_TODAY), 'SEEN': wc.flag(lakanaba.SEEN), 'SHIFT': wc.flag(lakanaba.SHIFT),
         'TOM_PUSH': wc.flag(lakanaba.TOM_PUSH)}

# 네네: 오늘 도시락 전이라 잠 → 아침(날수 + 1) → 오늘 도시락. 손님 갈래·톰을 교회까지 미는 길은 dq4ch3lakanabacheck 가
# 롬 사본·톰 자리로 본다
SEGMENTS = [
    ('nene_house', 'warp', f'{ch3.HOUSE},54,6', {'map': ch3.HOUSE}),
    ('nene_sleep', 'walk', talk('down', 10), {'map': ch3.HOUSE, 'want': ['BENTO'], 'bytes': {'SCOTT_DAYS': 1}}),
    # 톰 노인: 「예」 뒤 밀리는 인물이 되고, 밀며 집 남쪽으로 걸어 나간다(막히면 끝 셀이 다름)
    ('tom_room', 'warp', f'{TOWN},48,24', {'map': TOWN}),
    ('tom_ask', 'walk', talk('up', 5), {'map': TOWN, 'want': ['TOM_PUSH']}),
    ('tom_push', 'walk', '50,25;50,21;48,21;48,25', {'map': TOWN, 'cell': (48, 25)}),
    # 무기점 첫 출근: 문 밖에 서면 꾸지람 뒤 카운터 안으로 걸려 들어간다
    ('shop_door', 'warp', f'{TOWN},20,52', {'map': TOWN}),
    # 꾸지람 뒤 주인이 비키고 주인공이 걷는 동안 누른 A 는 버려지므로 넉넉히 누른다
    ('shop_first', 'walk', f'16,53;{taps(12)};{CLOSE}',
     {'map': TOWN, 'cell': lakanaba.COUNTER_IN, 'want': ['SEEN', 'SHIFT'], 'maxf': 2400}),
]

# 레이크나바 무기점 첫 출근: 문 칸이나 문 밖 칸에 들어서면 꾸지람(02F3) 뒤 카운터 안 (4,53)으로 걸려 들어가 031D. 문 밖
# 오른쪽·위·아래에서 들어선다. 끝나면 카운터 안 방 위쪽으로 다시 걷는다
SHOP_APPROACH = [('shop-right', '20,52'), ('shop-above', '16,48'), ('shop-below', '16,56')]


def hero_cases():
    nx, ny = ch3.NENE_CELL
    # 네네(낮, 침대 머리 위 칸)에게 위 칸에서 아래로 말을 건다. 침대(시작 칸)는 FC 에서 막힌 블록이라 맵을 다시 불러온
    # 뒤에는 설 수 없고, 순간이동으로 세우면 「その方向には誰もいない」(129)만 떴다. 순간이동은 TO 한 셀 아래에 내린다.
    # 말이 끝나면 위 줄로 돌아 방 오른쪽으로 걸어 간다(오른쪽 칸은 침대). 말이 끝난 뒤 A 를 더 누르면 다시 말을 걸어
    # 창이 남으므로 닫기만 누른다. distinct 1: 129 밖의 메시지가 하나. 오늘 도시락 flag 를 켜 두어 잠 갈래(맵을 다시
    # 불러옴) 대신 한마디(dq4ch3lakanaba 「forgot」)만 하게 한다
    bento = f'{0x2190 + lakanaba.BENTO_TODAY[0]:04X}={lakanaba.BENTO_TODAY[1]:02X}'
    out = {'nene-above': {'hop': HOP, 'warp': f'{ch3.HOUSE},{nx},{ny - 3}', 'set': bento,
                          'walk': f'{talk("down", 12)};wait:120;{CLOSE};{CLOSE};{nx},{ny - 4}', 'free': f'{nx + 4},{ny - 4}',
                          'want': [], 'map': ch3.HOUSE, 'distinct': 1, 'maxf': 2500}}
    for name, warp in SHOP_APPROACH:
        out[name] = {'warp': f'{lakanaba.TOWN},{warp}', 'set': '', 'walk': f'16,53;{taps(12)};{CLOSE}',
                     'free': f'{lakanaba.COUNTER_IN[0]},{lakanaba.COUNTER_IN[1] - 4}', 'hero_at': lakanaba.COUNTER_IN,
                     'want': [('SEEN', lakanaba.SEEN), ('SHIFT', lakanaba.SHIFT)], 'maxf': 2600}
    return out


PASS_NO_DEVICE = {
    lakanaba.SCRIPTS['customer'][2]: '레이크나바 손님: 주인공이 카운터 안 (4,53)에 선 뒤 조작을 막고서야 카운터 바깥 '
    '(12,53)~(8,53) 만 걷고, 맵 구석으로 사라진 뒤 조작을 푼다(dq4ch3lakanabacheck 손님 사례)',
    lakanaba.SCRIPTS['first_master'][2]: '레이크나바 첫 출근 주인: 주인공이 문 칸·문 밖(X 14 이상)에 서면 조작을 막고 X 12 '
    '이하((12,53)→(10,53)→(10,49))로만 비킴(heroblock shop-right·shop-above·shop-below)',
}
