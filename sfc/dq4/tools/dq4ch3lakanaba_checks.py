"""레이크나바(dq4ch3lakanaba)의 검사 표. 내놓는 것은 dq4ch3checks 머리말."""
import dq4ch1walkcheck as wc
import dq4ch3event as ch3
import dq4ch3lakanaba as lakanaba
from dq4ch3walkparts import CLOSE, HOP, TOWN, gold, talk, talk_yes, taps

FLAGS = {'BENTO': wc.flag(lakanaba.BENTO_TODAY), 'SEEN': wc.flag(lakanaba.SEEN), 'SHIFT': wc.flag(lakanaba.SHIFT),
         'TOM_PUSH': wc.flag(lakanaba.TOM_PUSH), 'DONE': wc.flag(lakanaba.DONE)}

# 명령 창 → 「문」(왼쪽 열 넷째 줄). 무기점의 두 문(FC 16/00 (03,17)·16/02 (05,05), 블록 속성 94)은 DQ5 문 물체라 FC
# 「とびら」 처럼 문 쪽을 보고 이 명령으로 연다. 걸어 들어가기만 하면 열리지 않는다
DOOR = ('wait:20;a:8;wait:40;down:4;wait:15;down:4;wait:15;down:4;wait:15;a:8;wait:90;b:8;wait:30;b:8;wait:30')

# 명령 창 「말하기」 → 0323(두 쪽) 「예」 → 0324 → 가게 메뉴 「사기」(물음·메뉴는 커서 토큰이 창을 기다림) → 「어느 걸로 하겠나?」 뒤 키를 기다리는
# 동안(06:DC34) 누르면 목록이 열린다. 목록 커서는 열린 뒤에야 움직여 pick 토큰이 열림을 기다린다
SHOP_PICK = 'wait:60;a:8'
BOOMERANG = lakanaba.GOODS[lakanaba.STOCKED][0]

# 네네: 오늘 도시락 전이라 잠 → 아침(날수 + 1) → 오늘 도시락. 손님 갈래·톰을 교회까지 미는 길은 dq4ch3lakanabacheck 가
# 롬 사본·톰 자리로 본다
SEGMENTS = [
    ('nene_house', 'warp', f'{ch3.HOUSE},54,6', {'map': ch3.HOUSE, 'poke': lakanaba.NENE_HOLD}),
    # 돌아다니는 낮 네네는 첫머리 자리에 묶고 말을 건다(lakanaba.NENE_HOLD)
    ('nene_sleep', 'walk', talk('down', 10), {'map': ch3.HOUSE, 'want': ['BENTO'], 'bytes': {'SCOTT_DAYS': 1},
                                              'poke': lakanaba.NENE_HOLD}),
    # 톰 노인: 「예」 뒤 밀리는 인물이 되고, 밀며 집 남쪽으로 걸어 나간다(막히면 끝 셀이 다름)
    ('tom_room', 'warp', f'{TOWN},48,24', {'map': TOWN}),
    ('tom_ask', 'walk', talk_yes('up', 5), {'map': TOWN, 'want': ['TOM_PUSH']}),
    ('tom_push', 'walk', '50,25;50,21;48,21;48,25', {'map': TOWN, 'cell': (48, 25)}),
    # 무기점 첫 출근: 문 밖에 서면 꾸지람 뒤 카운터 안으로 걸려 들어간다
    ('shop_door', 'warp', f'{TOWN},20,52', {'map': TOWN}),
    # 꾸지람 뒤 주인이 비키고 주인공이 걷는 동안 누른 A 는 버려지므로 넉넉히 누른다
    ('shop_first', 'walk', f'16,53;{taps(12)};{CLOSE}',
     {'map': TOWN, 'cell': lakanaba.COUNTER_IN, 'want': ['SEEN', 'SHIFT'], 'maxf': 2400}),
    # 카운터 안 → 문(FC (03,17))을 열고 가게 바닥 → 길. 순간이동은 카운터 안 방 위쪽에 내릴 뿐 그 뒤는 걷는다
    ('counter_room', 'warp', f'{TOWN},4,50', {'map': TOWN}),
    ('counter_out', 'walk', f'4,47;right:8;{DOOR};10,47;10,49;10,53;20,53', {'map': TOWN, 'cell': (20, 53), 'maxf': 2000}),
    # 출근 중(일삯 50) 가게 바닥에서 문을 열고 카운터 안 → 계단(FC (01,1B)) → 아래층 도착 (4,13) → 문(FC (05,05))을 열고
    # 주인(FC (07,04)) 아래에서 위로 말을 걸어 일찍 그만둔다(087F 「예」 → 0880). 손님이 들어오는 카운터 칸 (4,53)은 밟지 않는다
    ('shop_floor', 'warp', f'{TOWN},10,48', {'map': TOWN, 'set': f'{gold(0)};{(lakanaba.WAGE_AT & 0xFFFF):04X}=32'}),
    ('cellar_quit', 'walk', f'8,47;left:8;{DOOR};4,47;2,47;2,53;down:16;wait:150;8,13;8,11;right:8;{DOOR};14,11;'
     f'{talk_yes("up", 6)}',
     {'map': lakanaba.CELLAR, 'cell': (14, 11), 'want': ['DONE'], 'bytes': {'GOLD0': 50}, 'changes': 1, 'after': 1800,
      'maxf': 4000}),
    # 일찍 그만둔 뒤(출근 중·오늘 일 마침) 아래층 계단(FC (04,06))으로 낮 마을 카운터 안에 올라와도 마을이 멈추지 않고
    # 걷는다
    ('after_quit', 'walk', f'8,11;down:16;wait:150;4,47;right:8;{DOOR};10,47;10,49;10,53;20,53',
     {'map': TOWN, 'cell': (20, 53), 'maxf': 3200}),
    # 그만둔 날은 주인이 카운터에 선다. 손님 쪽에서 말을 걸어(0323 「예」 → 0324) 주인 가게: 3장 무기 셋 뒤에 재고가 있는
    # ブーメラン·はじゃのつるぎ 가 붙고, 넷째(ブーメラン 350G)를 산다. 금화만 줄고 재고는 그대로(FC 실측)
    ('master_shop', 'walk', f'10,53;8,53;wait:30;left:8;wait:30;a:8;wait:40;a:8;until:600;wait:90;a:8;cursor:1;cursor:0;a:8;cursor:1;cursor:0;'
     f'a:8;{SHOP_PICK};pick:{BOOMERANG};'
     f'a:8;wait:90;{taps(4)};b:8;wait:90;b:8;wait:90;b:8;wait:90;b:8;wait:90;10,53',
     {'map': TOWN, 'cell': (10, 53), 'maxf': 3200,
      'set': f'{gold(5000)};{lakanaba.STOCK_AT & 0xFFFF:04X}=01;{(lakanaba.STOCK_AT + 2) & 0xFFFF:04X}=01',
      'bytes': {'GOLD0': (5000 - 350) & 0xFF, 'GOLD1': (5000 - 350) >> 8}}),
    # 집 맨 윗줄 (10,00)의 빈 가게 사람은 FC 에서도 닿지 않는 가운데 빈 땅(X 08~19)에 선다. 두 방에서 그쪽 벽으로
    # 밀어도 벽 앞 칸에서 멈춰야 한다(넘으면 FC 에 없는 말 걸기가 생김). 낮 네네는 묶는다
    ('house_left', 'warp', f'{ch3.HOUSE},{2 * 3},{2 * 1}', {'map': ch3.HOUSE, 'poke': lakanaba.NENE_HOLD}),
    ('wall_left', 'walk', 'right:200', {'map': ch3.HOUSE, 'cell': (2 * 6, 2 * 1 + 1), 'poke': lakanaba.NENE_HOLD}),
    ('house_right', 'warp', f'{ch3.HOUSE},{2 * 29},{2 * 2}', {'map': ch3.HOUSE, 'poke': lakanaba.NENE_HOLD}),
    ('wall_right', 'walk', 'left:200', {'map': ch3.HOUSE, 'cell': (2 * 27, 2 * 2 + 1), 'poke': lakanaba.NENE_HOLD}),
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
                          'want': [], 'map': ch3.HOUSE, 'distinct': 1, 'maxf': 2500,
                          # 돌아다니는 낮 네네를 첫머리 자리에 묶는다(lakanaba.NENE_HOLD)
                          'poke': lakanaba.NENE_HOLD}}
    for name, warp in SHOP_APPROACH:
        # 손님은 쉼(PACE)을 묶어 오지 않게 한다: 꾸지람 말을 다 넘기는 사이 FC 처럼 첫 손님이 와서 말을 걸면 조작이 막혀
        # 위로 걷지 못한다(이 장면은 첫 출근 주인이 주인공을 막지 않는지만 본다)
        out[name] = {'warp': f'{lakanaba.TOWN},{warp}', 'set': '', 'walk': f'16,53;{taps(12)};{CLOSE}',
                     'poke': lakanaba.CUSTOMER_HOLD,
                     'free': f'{lakanaba.COUNTER_IN[0]},{lakanaba.COUNTER_IN[1] - 4}', 'hero_at': lakanaba.COUNTER_IN,
                     'want': [('SEEN', lakanaba.SEEN), ('SHIFT', lakanaba.SHIFT)], 'maxf': 2600}
    return out


PASS_NO_DEVICE = {
    lakanaba.SCRIPTS['first_master'][2]: '레이크나바 첫 출근 주인: 주인공이 문 칸·문 밖(X 14 이상)에 서면 조작을 막고 X 12 '
    '이하((12,53)→(10,53)→(10,49))로만 비킴(heroblock shop-right·shop-above·shop-below)',
    lakanaba.SCRIPTS['master'][2]: '레이크나바 카운터 주인: 가게를 닫을 때만 걷고, 그때 주인공은 손님이 막은 채 카운터 안 '
    '(4,53)에 서 있다. 주인은 계단 칸 (2,55)→(4,55) 한 걸음(dq4ch3lakanabacheck closing 사례)',
    **{lakanaba.SCRIPTS[name][2]: '레이크나바 우리의 개: 아들에게 빌리고 돌려줄 때만 조작을 막고 걷는다. 주인공은 아들 아래 '
       '(46,9)에서 말을 건 채이고, 빌릴 때 개는 Y 7 줄((54,7)→(46,7))만, 돌려줄 때는 FC 처럼 줄 끝 자리 (46,11)에서 주인공 '
       '칸을 지나 (46,7)→(54,7)로 간다(dq4ch3lakanabacheck son·son_return 사례)' for name in ('dog_home', 'dog_home_night')},
    **{lakanaba.SCRIPTS[name][2]: '레이크나바 톰 아들: 개를 빌리고 돌려줄 때 제자리 (46,7)과 위 칸 (46,5) 사이만 걷는다. '
       '주인공은 아래 (46,9)에서 말을 건 채다(dq4ch3lakanabacheck son·son_return 사례)' for name in ('son', 'son_night')},
}

# 조작을 막지 않고 걷는 인물(test_dq4heroblock.WALK_EXEMPT)
WALK_EXEMPT = {
    lakanaba.SCRIPTS['nene_walk'][2]: '레이크나바 낮 네네: FC 블록 2B 처럼 한 걸음씩 고르는 네이티브(nene_step)가 주인공을 '
    '비롯해 보이는 인물이 선 칸은 고르지 않는다. DQ5 의 돌아다니는 인물처럼 1C 없이 걷는다',
    lakanaba.SCRIPTS['customer'][2]: '레이크나바 손님: FC 손님처럼 주인공을 지나가지 않고 카운터 바깥 (12,53)~(8,53) 만 '
    '걷는다. 문 칸에 주인공이 서 있으면 나타나지 않고, 길에 서 있으면 막혀 기다린다(dq4ch3lakanabacheck 손님 사례)',
}
