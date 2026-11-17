"""3장 한 줄 걷기(dq4story3check.py)의 구간 표. FC 3장 사건 차례(fc/dq4/docs/dq4-chapter3-format.md 「사건 차례」)대로
놓는다.

구간은 (이름, 토막, 선택)이다. 토막은 dq4storywalk.lua 의 꼴(셀 x,y · talk · free · yes · no · yes* · msg:HHH · map:GG/MM ·
face:dir · dir:n · wait:n · until:…). 선택:
  part    이 구간부터 새 파트(파트 끝 상태를 캐시해 다음 파트를 다시 걸을 때 앞을 걷지 않음)
  map·cell·field·want·off·items·no_items·bytes·gold_min  끝에 보는 것(flag 이름은 FLAGS)
  rng     구간 내내 난수를 시드 값으로 묶음(걸어 다니는 사람에게 말을 걸 때)
  battle  사건 전투 패치(dq4chapterwalk.battle_patch 꼴)
  maxf    최대 프레임, tokmax 토막 하나의 최대 프레임(기본 6000)
  gold    구간 시작에 금화를 이 값으로(FC 에서 장사·전투로 버는 금화). why 와 함께
  give    구간 시작에 톨네코 물건 칸에 납품 무기를 둠 [(칸, 물건)]. why 와 함께
써 넣기는 gold·give 둘뿐이고(writes_set 이 그 밖을 거부), writes() 가 표로 낸다.
"""
import dq4ch3bonmalmo as bm
import dq4ch3event as ch3
import dq4ch3endor as endor
import dq4ch3safe as safe
import dq4ch3tunnel as tunnel
import dq4ch3walkcheck as tw
import dq4monport

FLAGS = tw.FLAGS
ALLOWED_ITEMS = (endor.STEEL_SWORD, endor.IRON_ARMOR)
ITEM_SLOT = ch3.PARTY_ITEMS & 0xFFFF


def writes_set(opt):
    """구간 선택 gold·give 를 SET 조각으로. 다른 써 넣기는 이 검사가 하지 않는다."""
    out = []
    if 'gold' in opt:
        n = opt['gold']
        out += [f'{(ch3.GOLD_AT & 0xFFFF) + k:04X}={n >> 8 * k & 0xFF:02X}' for k in range(3)]
    for slot, item in opt.get('give', ()):
        if item not in ALLOWED_ITEMS or not 0 <= slot < 12:
            raise ValueError(f'써 넣을 수 없는 물건 {item:02X}·칸 {slot}')
        out.append(f'{ITEM_SLOT + slot:04X}={item:02X}')
    if ('gold' in opt or 'give' in opt) and not opt.get('why'):
        raise ValueError('써 넣기에는 why')
    return ';'.join(out)


L_TOWN, L_HOUSE = '3E/00', ch3.HOUSE
# 걸음 전투를 붙일 때의 몬스터(3장 구역의 버블 슬라임, dq4ch3monstercheck 와 같음)
BUBBLE = dq4monport.CH3[0x0A][0]
SEARCH = 'cmd:down,down,down,right'
# 엔돌 FC 04: 마을 도착 칸 (17,20) → 여관(FC (12,18), 카운터 아래) / 여관 아래 → 왕좌의 방 왕 아래 칸 (0B,0B)
E_TO_INN = '46,63;42,63;42,53;36,53'
E_INN_TO_KING = '42,53;42,27;46,27;46,19;map:40/02;24,67;24,59;26,59;26,49;map:40/06;24,39;24,31;22,31;22,23'
# 네네 옆(FC (05,1C)) → 왕 아래 칸 / 마을 도착 칸
E_NENE_TO_KING = '6,57;6,47;8,47;8,33;16,33;16,27;46,27;46,19;map:40/02;24,67;24,59;26,59;26,49;map:40/06;26,39;24,39;24,31;22,31;22,23'
E_NENE_TO_GATE = '6,57;6,47;8,47;8,43;20,43;20,45;42,45;42,63;46,63;46,65'
# 납품하는 사람 아래 → 네네 옆
E_DELIVER_TO_NENE = '34,41;36,41;36,45;32,45;32,57;28,57;28,71;map:40/00;48,21;46,21;46,27;16,27;16,33;8,33;8,47;6,47;6,57;10,57'
# 엔돌 나오는 칸 → 굴 엔돌 쪽 입구(FC 필드 (79,5D))
E_TO_TUNNEL = '210,205;210,199;232,199;232,187;242,187'
# 굴 47/00(FC 42/00): 도착 칸 ↔ 노인 아래 칸, 계단으로 나가면 서는 필드 칸
T_TO_OLD = '10,21;10,17;34,17;34,23;36,23'
T_TO_STAIRS = '34,23;34,17;10,17;10,21;down:16'
T_FIELD = (242, 189)
NIGHT_FROM = 'serve:075E>=00F0'
# 레이크나바 마을 FC 16/00: 집 계단 (1C,1B) 앞 칸 → …, 도구점(FC (1B,11)) 아래 칸 (1B,12), 왼쪽 가장자리 (00,0D)
L_HOUSE_TO_TOWN = '54,13;58,13;58,15;66,15;map:3E/00'
L_TO_ITEMS = '56,53;40,53;40,37;54,37'
L_ITEMS_OUT = '40,37;40,33;14,33;14,25;0,25;0,27;left:16;field'

SEGMENTS = [
    # 1. 첫머리 뒤 침대에서 네네(첫머리 직후 말) → 집 계단으로 마을
    ('house', f'face:up;talk;free;{L_HOUSE_TO_TOWN}',
     {'part': 'lakanaba', 'map': L_TOWN, 'cell': (56, 55), 'want': ['CHAPTER3'], 'off': ['OPENING3']}),
    # 무기점 문 밖에 서면 꾸지람 뒤 카운터 안으로 걸려 들어간다
    ('shop_first', '56,53;17,53;free', {'map': L_TOWN, 'cell': (4, 53), 'want': ['SEEN', 'SHIFT']}),
    # 카운터 안에 서서 손님마다 「예」. 일삯이 100 을 넘으면 가게를 닫아 일삯을 금화로, 밤, 무기점 문 앞
    ('work', NIGHT_FROM, {'map': L_TOWN, 'cell': (14, 53), 'gold_min': 100, 'maxf': 60000, 'tokmax': 60000}),
    # 밤에 집으로 돌아가 네네(밤 자리 FC (1D,03))에게 「예」 → 잠 → 아침, 도시락
    ('sleep', '56,53;56,55;map:3E/01;58,15;58,9;face:up;talk;yes*',
     {'map': L_HOUSE, 'cell': (54, 11), 'want': ['BENTO'], 'bytes': {'TIME': 0x50}}),
    # 도구점에서 키메라의 날개(감옥의 아들에게 줌)
    ('wings', f'{L_HOUSE_TO_TOWN};{L_TO_ITEMS};face:up;talk;win:3A;pick:0F22={bm.WINGS:02X};win:32;win:33;close',
     {'map': L_TOWN, 'items': [bm.WINGS]}),
    # 2. 마을 왼쪽 가장자리로 나가 필드를 걸어 북쪽 동굴 입구(FC (71,14))
    ('cave_road', f'{L_ITEMS_OUT};232,75;232,41;226,41;map:{safe.ENTRY}', {'part': 'cave', 'map': safe.ENTRY, 'cell': (22, 7)}),
    # 입구 층 → 3E/04 위 → 오른쪽 통로 계단으로 입구 층 아래 → 3E/04 왼쪽 방 → 왼쪽 수문 「예」 → 물살에 3E/06
    ('cave_gates', f'22,9;20,9;20,7;6,7;6,9;map:{safe.GATES};14,9;28,9;28,23;40,23;40,55;map:{safe.ENTRY};'
     f'12,51;12,33;4,33;4,35;map:{safe.GATES};16,31;16,29;yes;map:{safe.PIT}', {'map': safe.PIT, 'want': ['SAFE_DRAINED']}),
    # 3E/06 → 3E/07: 바위를 줄 13 오른쪽·열 0B 아래·줄 1E 왼쪽으로 이끌어 왼쪽 구덩이를 메우고 건너 3E/09. 기다림은 바위가
    # 멈출 자리에 닿을 때까지(입력 없음)
    ('cave_boulder', f'16,13;8,13;8,7;4,7;map:{safe.ROLL};38,29;34,29;34,21;6,21;6,29;6,39;22,39;22,43;wait:800;22,61;16,61;'
     f'wait:330;8,61;8,53;wait:260;8,39;12,39;wait:600;8,39;8,89;6,89;6,91;map:{safe.VAULT}',
     {'map': safe.VAULT, 'bytes': {'SAFE_FILL': 0x01}}),
    # 금고 상자 아래에서 しらべる → 철 금고
    ('cave_safe', f'20,39;8,39;8,9;{SEARCH};free', {'map': safe.VAULT, 'items': [safe.IRON_SAFE]}),
    # 나오는 길: 금고 방 계단 → 3E/07(바위가 처음 자리로 돌아가 구덩이로 떨어짐) → 3E/08 위 계단 → 3E/07 오른쪽 계단 →
    # 3E/06 오른쪽 계단 → 물 빠진 3E/05 → 입구 층 아래 → 3E/05 오른쪽 통로 → 입구 층 위 → 필드
    ('cave_out', f'8,39;24,39;down:20;map:{safe.ROLL};8,73;map:{safe.PIT_BELOW};6,17;26,17;26,5;map:{safe.ROLL};'
     f'20,21;34,21;34,29;38,29;38,39;40,39;map:{safe.PIT};8,7;8,13;26,13;26,7;30,7;map:{safe.DRY};18,29;22,29;'
     f'map:{safe.ENTRY};12,35;12,45;20,45;20,51;map:{safe.DRY};40,23;28,23;28,9;14,9;14,5;map:{safe.ENTRY};'
     '6,7;20,7;20,9;22,9;22,7;field', {'field': True, 'cell': (226, 43), 'items': [safe.IRON_SAFE]}),
    # 3. 본몰: 동굴에서 필드를 걸어 본몰 성(밤에 닿음) → 여관에서 아침
    ('bm_road', f'232,43;232,87;234,87;234,95;218,95;218,143;232,143;232,141;map:{bm.CASTLE}',
     {'part': 'bonmalmo', 'map': bm.CASTLE, 'cell': (34, 63)}),
    ('bm_inn', f'34,57;22,57;face:up;talk;yes*', {'map': bm.CASTLE, 'bytes': {'TIME': 0x50}}),
    # 낮의 왕자(인물 칸 08, 걸어 다님): 옆에 서서 말을 걸면 유모가 꾸짖음
    ('bm_prince_walk', '32,57;32,37;20,37;20,25;4,25', {'map': bm.CASTLE}),
    ('bm_prince', 'near:08;talk;free', {'map': bm.CASTLE, 'want': ['BM_PRINCE_MET'], 'rng': True}),
    # 성을 나가 필드를 밤이 될 때까지 걷고 다시 들어와 무기점 뒤 왕자에게서 편지
    ('bm_night', '4,25;16,25;16,35;34,35;34,63;down:64;field;until:075E>=00F0,left,right;232,143;232,141;'
     f'map:{bm.CASTLE};34,49;56,49;56,33;64,33;64,15;face:up;talk;free',
     {'map': bm.CASTLE, 'items': [bm.PRINCE_LETTER], 'tokmax': 20000}),
    # 밤에는 북쪽 통로를 파수꾼이 막아 감옥 계단으로 갈 수 없다: 여관에서 아침을 기다려 감옥(3F/00)의 창살 너머 아들에게
    # 키메라의 날개
    ('bm_inn2', '64,33;56,33;56,49;26,49;26,57;22,57;face:up;talk;yes*', {'map': bm.CASTLE, 'bytes': {'TIME': 0x50}}),
    ('bm_prison', f'32,57;32,35;18,35;18,33;20,33;20,5;50,5;map:{bm.PRISON};10,25;10,17;22,17;22,25;face:right;talk;yes*',
     {'map': bm.PRISON, 'want': ['BM_SON_FREED'], 'no_items': [bm.WINGS]}),
    # 레이크나바로 돌아가 톰의 아들에게서 개 토마스
    ('bm_dog', f'22,17;10,17;10,25;14,25;map:{bm.CASTLE};20,5;20,31;18,31;18,35;34,35;34,63;down:64;field;'
     f'218,143;218,95;234,95;234,73;208,73;map:{L_TOWN};0,25;14,25;14,33;40,33;40,35;46,35;46,25;44,25;44,21;48,21;'
     '48,17;46,17;46,9;face:up;talk;free', {'map': L_TOWN, 'want': ['DOG']}),
    # 여우 마을(개와 함께): 촌장 → 숲 → 여우에게 「예」 → 강철 갑옷, 돈 가아데가 떠남
    ('bm_fox', '46,17;48,17;48,21;44,21;44,25;46,25;46,35;40,35;40,33;14,33;14,25;0,25;0,27;left:16;field;248,75;248,105;'
     f'map:{bm.FOX_TOWN};40,59;40,23;48,23;48,5;26,5;26,7;22,7;22,3;face:right;talk;yes*',
     {'map': bm.FOREST, 'want': ['BM_FOXED'], 'items': [bm.STEEL_ARMOR], 'tokmax': 12000}),
    # 숲에서 필드로 나가 끊긴 다리 서쪽 한 칸 앞까지
    ('bm_bridge_near', '0,25;left:16;field;218,107;218,159', {'field': True, 'cell': (218, 159)}),
    # 다리 서쪽 칸으로 내디디면 걸음 전투(버블 슬라임 하나, HP 1)를 붙여 이기고, 고치기 전 다리로는 건너지 못한다
    ('bm_bridge_fight', 'right:16;fight;right:30;wait:30',
     {'field': True, 'cell': (220, 159), 'off': ['BM_BRIDGE'], 'fight': [(BUBBLE, 1)]}),
    # 본몰 왕에게 말을 걸면 다리를 고친다
    ('bm_king', f'220,143;232,143;232,141;map:{bm.CASTLE};34,17;face:up;talk;free', {'map': bm.CASTLE, 'want': ['BM_BRIDGE']}),
    # 4. 고친 다리를 건너 동쪽 칸에 선다
    ('bridge_cross', '34,63;down:64;field;220,143;220,159;226,159', {'part': 'endor', 'field': True, 'cell': (226, 159)}),
    # 엔돌(밤에 닿음) 여관에서 아침 → 왕 첫 알현(「예」) → 모니카에게 왕자의 편지(왕의 편지로 바뀜)
    ('endor_inn', f'226,187;218,187;218,195;208,195;208,203;map:{endor.TOWN};{E_TO_INN};face:up;talk;yes*',
     {'map': endor.TOWN, 'bytes': {'TIME': 0x50}}),
    ('endor_king_first', f'{E_INN_TO_KING};face:up;talk;yes*', {'map': endor.THRONE, 'off': ['ENDOR_ALLOWED']}),
    ('endor_monica', '22,25;28,25;28,23;30,23;face:up;talk;yes*',
     {'map': endor.THRONE, 'want': ['BM_LETTER1'], 'items': [bm.KING_LETTER]}),
    # 왕의 편지를 본몰 왕에게(다리를 건너 돌아감)
    ('endor_letter2', f'28,23;28,25;26,25;26,39;map:{endor.CASTLE_HALL};26,71;map:{endor.TOWN};46,33;44,33;44,63;46,63;46,65;'
     f'down:64;field;210,205;210,195;218,195;218,187;226,187;226,159;220,159;220,143;232,143;232,141;map:{bm.CASTLE};'
     '34,17;face:up;talk;free', {'map': bm.CASTLE, 'want': ['BM_LETTER2'], 'no_items': [bm.KING_LETTER]}),
    # 다시 엔돌(밤) 여관 → 왕의 허락
    ('endor_allowed', f'34,63;down:64;field;220,143;220,159;226,159;226,187;218,187;218,195;208,195;208,203;'
     f'map:{endor.TOWN};{E_TO_INN};face:up;talk;yes*;{E_INN_TO_KING};face:up;talk;yes*',
     {'map': endor.THRONE, 'want': ['ENDOR_ALLOWED']}),
    # 가게 주인에게 35000 골드로 가게를 삼 → 아침, 네네 옆
    ('endor_shop', f'22,31;24,31;24,39;26,39;map:{endor.CASTLE_HALL};26,71;map:{endor.TOWN};46,27;16,27;16,33;8,33;8,47;'
     f'6,47;6,59;map:{endor.SHOP_UP};2,13;6,13;6,9;face:up;talk;yes*;free',
     {'map': endor.TOWN, 'cell': endor.NENE_SIDE[1], 'want': ['ENDOR_SHOP'], 'gold': endor.SHOP_PRICE,
      'why': 'FC 는 무기점 일·장사·전투로 35000 골드를 모은다(이 검사는 무기점 일 한 바퀴만 걷고 나머지 벌이를 써 넣음)'}),
    # 5. 은의 여신상 동굴: 필드 → 입구 층 배 → 아래층 → 단추 「예」 → 물 빠진 층 → 배로 섬 → 여신상
    ('statue_road', '6,57;6,47;8,47;8,43;20,43;20,45;42,45;42,63;46,63;46,65;down:64;field;210,205;210,199;224,199;'
     '224,195;236,195;236,165;246,165;246,157;252,157;252,153;254,153;254,147;256,147;256,129;258,129;'
     f'map:{endor.CAVE_ENTRY}', {'part': 'statue', 'map': endor.CAVE_ENTRY}),
    ('statue_button', f'6,25;24,25;24,11;22,11;22,9;24,9;24,11;44,11;wait:30;62,11;62,31;50,31;left:20;'
     f'map:{endor.CAVE_LOW_WET};6,63;6,55;8,55;22,55;22,39;26,39;26,35;64,35;64,53;68,53;68,63;map:{endor.CAVE_WET};'
     '56,55;56,47;52,47;52,39;48,39;48,35;20,35;20,25;22,25;22,21;24,21;24,19;26,19;26,11;30,11;30,7;34,7;34,5;yes;'
     f'map:{endor.CAVE_DRY}', {'map': endor.CAVE_DRY, 'cell': endor.BUTTON_LAND[1], 'want': ['ENDOR_BUTTON']}),
    ('statue_take', f'24,5;24,31;28,31;28,33;54,33;54,45;60,45;60,49;map:{endor.CAVE_LOW_DRY};60,57;60,55;58,55;wait:30;'
     f'58,53;64,53;64,47;60,47;60,43;56,43;56,39;52,39;52,35;30,35;30,17;30,15;28,15;28,13;map:{endor.STATUE_ROOM};'
     f'18,39;18,37;16,37;16,33;12,33;12,11;{SEARCH};free', {'map': endor.STATUE_ROOM, 'items': [endor.STATUE]}),
    # 섬 계단으로 내려가면 배가 섬 (0E,09)에 와 있다. 배로 돌아가 물 빠진 층 → 입구 층 → 필드
    ('statue_out', f'12,33;16,33;16,37;18,37;18,39;20,39;map:{endor.CAVE_LOW_DRY};28,15;28,17;28,19;wait:30;30,19;30,35;'
     f'52,35;52,39;56,39;56,43;60,43;60,47;64,47;64,53;58,53;58,55;60,55;60,57;62,57;map:{endor.CAVE_DRY};56,49;56,47;'
     f'52,47;52,39;48,39;48,35;20,35;20,23;8,23;8,25;6,25;6,27;map:{endor.CAVE_ENTRY};22,11;24,11;24,25;6,25;6,39;field',
     {'field': True, 'items': [endor.STATUE]}),
    # 엔돌(밤) 수집가(밤에는 서 있음)에게 25000 골드에 팖
    ('statue_sell', '256,131;256,147;254,147;254,153;252,153;252,157;246,157;246,165;236,165;236,185;234,185;234,199;'
     f'208,199;208,203;map:{endor.TOWN};46,41;80,41;80,39;82,39;82,33;84,33;84,31;map:40/04;8,13;4,13;4,11;'
     f'map:{endor.COLLECTOR};4,11;4,9;8,9;8,13;14,13;face:up;talk;yes*',
     {'map': endor.COLLECTOR, 'want': ['ENDOR_SOLD'], 'no_items': [endor.STATUE], 'gold_min': endor.STATUE_PRICE}),
    # 8. 용병 로렌스를 600 골드로 고용(판 금화로)
    ('lawrence', f'8,13;8,9;4,9;4,11;map:40/04;4,11;4,13;8,13;8,17;map:{endor.TOWN};84,33;82,33;82,39;80,39;80,41;42,41;'
     f'42,53;36,53;36,59;30,59;30,51;map:{endor.BARD_HALL};14,5;12,5;12,15;14,15;face:down;talk;yes*',
     {'part': 'order', 'map': endor.BARD_HALL, 'want': ['LAWRENCE'], 'bytes': {'PARTY_N': 2, 'LAWRENCE_DAYS': 0}}),
    # 밤의 가게 위층 네네에게 「예」 → 잠(날수 + 1) → 아침 네네 옆. 6. 왕의 무기 주문
    ('order', f'12,15;12,5;14,5;map:{endor.TOWN};30,51;30,59;36,59;36,53;42,53;42,45;20,45;20,43;8,43;8,47;6,47;6,59;'
     f'map:{endor.SHOP_UP};2,15;2,13;6,13;6,9;face:up;talk;yes*;{E_NENE_TO_KING};face:up;talk;yes*',
     {'map': endor.THRONE, 'want': ['ENDOR_ORDER'], 'bytes': {'LAWRENCE_DAYS': 1}}),
    # 납품: 소지품 칸이 모자라 두 번에 나눠 낸다
    ('deliver1', f'22,31;24,31;24,39;26,39;map:{endor.CASTLE_HALL};26,49;26,57;32,57;32,45;36,45;36,41;34,41;face:up;talk;yes*',
     {'map': endor.CASTLE_HALL, 'bytes': {'ENDOR_COUNT': 0x44},
      'give': [(k, endor.STEEL_SWORD) for k in range(4, 8)] + [(k, endor.IRON_ARMOR) for k in range(8, 12)],
      'why': 'FC 는 강철 검·철 갑옷을 무기점·전투로 모은다(각 7, 소지품 8칸이 비어 넷씩)'}),
    ('deliver2', 'talk;yes*', {'map': endor.CASTLE_HALL, 'want': ['ENDOR_DELIVERED'], 'bytes': {'ENDOR_COUNT': 0x77},
                               'gold_min': endor.DELIVERY_PAY,
                               'give': [(k, endor.STEEL_SWORD) for k in range(4, 7)] + [(k, endor.IRON_ARMOR) for k in range(7, 10)],
                               'why': '나머지 셋씩'}),
    # 낮 네네에게 네 번 더 잠 → 로렌스 날수 5
    ('days', f'{E_DELIVER_TO_NENE};' + ';'.join(['face:right;talk;yes*'] * 4),
     {'map': endor.TOWN, 'bytes': {'LAWRENCE_DAYS': 5}, 'want': ['LAWRENCE'], 'tokmax': 8000}),
    # 7. 엔돌을 나와 필드 걸음에 로렌스가 떠나고(0379), 굴 노인에게 60000 골드
    ('tunnel_road', f'{E_NENE_TO_GATE};down:64;field;{E_TO_TUNNEL};map:{tunnel.BLOCKED}',
     {'part': 'tunnel', 'map': tunnel.BLOCKED, 'off': ['LAWRENCE'], 'bytes': {'PARTY_N': 1}}),
    ('tunnel_pay', f'{T_TO_OLD};face:up;talk;yes*', {'map': tunnel.BLOCKED, 'want': ['TUNNEL_PAID', 'TUNNEL_WAITING']}),
    # 필드에 나갔다 들어와 다시 말을 걸면 공사 재개
    ('tunnel_resume', f'{T_TO_STAIRS};field;{T_FIELD[0]},{T_FIELD[1] - 2};map:{tunnel.BLOCKED};{T_TO_OLD};face:up;talk;yes*',
     {'map': tunnel.BLOCKED, 'want': ['TUNNEL_RESUMED'], 'off': ['TUNNEL_WAITING']}),
    # 엔돌 40/01 에 들면 개통 소식, 네네에게 「예」 → 굴이 뚫림
    ('tunnel_news', f'{T_TO_STAIRS};field;230,189;230,199;208,199;208,203;map:{endor.TOWN};46,63;42,63;42,53;36,53;36,59;'
     f'32,59;32,57;map:{tunnel.NOTICE_MAP};free', {'map': tunnel.NOTICE_MAP, 'want': ['ENDOR_NOTICE'], 'off': ['TUNNEL_OPENED']}),
    ('tunnel_nene', f'48,29;50,29;map:{endor.TOWN};32,57;32,59;36,59;36,53;42,53;42,45;20,45;20,43;8,43;8,47;6,47;6,57;'
     '10,57;face:right;talk;yes*', {'map': endor.TOWN, 'want': ['TUNNEL_OPENED']}),
    # 뚫린 굴: 이주민이 지나가게 계단 옆으로 비켜 기다린 뒤 동쪽 계단을 밟는다
    ('tunnel_through', f'{E_NENE_TO_GATE};down:64;field;{E_TO_TUNNEL};map:{tunnel.OPEN_MAP};6,31;wait:1200;6,25;20,25;'
     '20,13;36,13;36,9;60,9;60,5;right:16;wait:20', {'map': tunnel.OPEN_MAP}),
    # 서술을 넘기면 엔딩 곡(14). 곁가지: 같은 상태에서
    ('tunnel_song', f'see:1D8B={tunnel.ENDING_SONG:02X}', {'side': True, 'bytes': {'SONG': tunnel.ENDING_SONG}}),
    # 끝 상자 → 버튼 → 리셋 → 타이틀(소리 켜기)
    ('tunnel_end', f'ending:{tunnel.END_SCENE}', {}),
]


def parts():
    """[(파트 이름, 구간 번호들)]."""
    out = []
    for i, (_, _, opt) in enumerate(SEGMENTS):
        if 'part' in opt or not out:
            out.append((opt.get('part', 'start'), []))
        out[-1][1].append(i)
    return out


def writes():
    """써 넣기 표: [{구간, 무엇, 왜}]."""
    out = []
    for name, _, opt in SEGMENTS:
        if 'gold' in opt:
            out.append({'segment': name, 'what': f"금화 {opt['gold']}", 'why': opt['why']})
        if 'give' in opt:
            out.append({'segment': name, 'what': ' '.join(f'칸{s}={i:02X}' for s, i in opt['give']), 'why': opt['why']})
    return out
