"""DQ4 3장 레이크나바 사건(dq4ch3slots 'L'): 네네의 도시락과 잠, 무기점 일, 톰 노인을 교회로 밀기, 톰 아들의 개.

FC 를 헤드리스로 잰 흐름(fc/dq4/docs/dq4-chapter3-format.md 「무기점 일」·「손님 갈래」·「일삯」)을 SFC 인물 스크립트와
대화 스크립트로 옮긴다. 형식은 sfc/dq4/docs/dq4-chapter3-format.md 「레이크나바」.

  네네   첫머리 직후(집을 다시 불러오기 전, dq4ch3event.FRESH)에는 080A. 낮에 오늘 일했거나(WORKED) 오늘 도시락을
         받지 않았으면(BENTO_TODAY 꺼짐) 080B·080C 뒤 잠, 아니면 이번 방문에 잤으면 080F, 아니면 0810. 밤에는 0811·080C 뒤 잠. 잠은 이벤트로 HP·MP 를 채우고 아침으로 집을 다시 불러온 뒤
         080D·080E, 도시락이 없고 물건 칸이 비었으면 도시락을 준다.
  무기점 첫 출근은 문 앞에서 꾸지람(02F3) 뒤 카운터 안으로 걸려 들어가 031D. 다음부터는 카운터 안의 주인에게 말을 걸어
         「예」(0326). 일하는 동안 손님이 문으로 들어와 카운터 앞에 서고, 주인공이 카운터 안 (02,1A) 에 서면 말을 건다.
         사는 손님·파는 손님과 값 흥정은 FC 난수 문턱 그대로이고, 일삯이 100 이 넘으면 가게를 닫고(0341) 밤이 된다.
         아래층 주인(052)에게 말하면 일찍 그만둔다.
  톰     「예」(0816) 뒤 밀리는 인물이 되고, 교회 안(FC X 0C~10, Y 04~06)에 닿으면 03AE 와 2~12 골드.
  톰 아들 084B 로 개 토마스를 빌려준다(공용 flag DOG). 우리의 개는 DOG 동안 숨는다. 여우를 쫓은 뒤(본몰 FOXED)에는
         돌려받는다(0899).
"""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4chapter1 as ch1  # noqa: E402
import dq4ch2event as ch2  # noqa: E402
import dq4ch3event as ch3  # noqa: E402
from dq4chapterbox import ENTER, LEAVE  # noqa: E402
from dq4ch2endor import Asm, BCC, BCS, BEQ, BNE, BRA, lda, sta  # noqa: E402
from dq4itemport import BENTO  # noqa: E402
from dq4ch3slots import SLOTS as _SLOTS, VARS2_AT  # noqa: E402
from dq4shopkey import ONE_SHOT  # noqa: E402

say, narrate = ch1.say, ch1.narrate
pages = ch2._speaker_pages
_al = ch2._al

# 7E:2200(dq4ch3slots L 의 첫 바이트): 저장되는 진행
BENTO_TODAY = (0x70, 0x01)     # 오늘 네네에게 도시락을 받음(FC $6285&02). 필드로 나가면 꺼짐
SEEN = (0x70, 0x02)            # 첫 출근 꾸지람을 봄(FC $6284&02)
WORKED = (0x70, 0x04)          # 오늘 손님에게 팔았음(FC $6284&01). 잠이 끔
SHIFT = (0x70, 0x08)           # 이번에 출근함(FC $6285&01). 켜져 있으면 카운터 주인이 없음. 필드로 나가면 꺼짐
DONE = (0x70, 0x10)            # 오늘 일을 마침(FC $6284&04): 손님이 오지 않음. 출근과 잠이 끔
TOM_PUSH = (0x70, 0x20)        # 톰 노인을 밀어 주기로 함(FC $6280&20)
TOM_DONE = (0x70, 0x40)        # 톰 노인이 교회에 닿음(FC $6280&10)
DOG_BACK = (0x70, 0x80)        # 개 토마스를 돌려줌(FC $6286&08)
# 7E:2201: 손님 하나를 맞는 동안의 값(대화 스크립트가 조건으로 봄). 손님이 들어올 때 모두 지운다
SELLER = (0x71, 0x01)          # 파는 손님(FC rand < 30)
NO_MONEY = (0x71, 0x02)        # 사는 결과: 돈이 모자람(0335)
FULL = (0x71, 0x04)            # 소지품이 가득(0336)
NO_EQUIP = (0x71, 0x08)        # 장비할 수 없음(0337)
SOLD = (0x71, 0x10)            # 팜(032F)
LUCK = (0x71, 0x20)            # 흥정의 둘째 난수 r2 < 80
CLOSE = (0x71, 0x40)           # 일삯이 100 이 넘어 가게를 닫음
STAGE = (0x71, 0x80)           # 사는 손님이 물건을 보자고 했음: 다시 말을 걸면 값 제시(032D)부터
FLAGS = (BENTO_TODAY, SEEN, WORKED, SHIFT, DONE, TOM_PUSH, TOM_DONE, DOG_BACK,
         SELLER, NO_MONEY, FULL, NO_EQUIP, SOLD, LUCK, CLOSE, STAGE)
# 7E:21A4: 맵을 옮기면 지워지는 칸(dq5flags 「맵 안 임시 값」). 이 해킹의 다른 도구는 쓰지 않는다
ACROSS = (0x14, 0x01)          # 주인공이 카운터 바깥(손님 쪽)에서 말을 걺
START = (0x14, 0x02)           # 카운터 주인에게 「예」: 주인 스크립트가 출근 장면을 돌림
AGAIN = (0x14, 0x04)           # 손님이 같은 자리에서 다시 말을 걺(FC 032E → 032D, 032C 뒤)
SLEPT = (0x14, 0x08)           # 이번 방문에 잤음(FC $628B bit7 이 꺼짐): 네네가 080F
HERE_ = (0x14, 0x10)           # 주인공이 카운터 안 (02,1A) 에 섬
SERVED = (0x14, 0x20)          # 이 손님을 맞았음(주인공이 먼저 말을 걸었으면 손님 스크립트가 다시 걸지 않음)
DISCOUNT = (0x14, 0x40)        # 흥정: 깎아 줌(0330)
RAISE = (0x14, 0x80)           # 흥정: 값을 올림(0331)
LUCK40 = (0x13, 0x40)          # 7E:21A3 bit6(맵을 옮기면 지워짐): 같은 r2 < 40(웃돈을 받아들임)
JOKE = (0x13, 0x08)            # 7E:21A3 bit3(맵을 옮기면 지워짐): 032C 에 「아니오」. 손님이 다시 말을 걸면 032C 부터
TEMP = 0x7E21A4
FOXED = (0x73, 0x01)           # 본몰 모듈(dq4ch3slots B)의 여우를 쫓음(FC $6280&02). 조건으로만 본다
SON_FREED = (0x73, 0x04)       # 본몰 모듈의 감옥의 톰 아들을 풀어 줌(FC $6280&04). 레이크나바의 아들이 이때부터 선다
PACE = 0x7E21A2                # 다음 손님까지 남은 차례(맵을 옮기면 0)
ANSWERED = ch2.ANSWERED        # 7E:21A3 bit0 대화가 끝남(맵을 옮기면 지워짐)

# 변수 칸(dq4ch3slots L: +4~+9)
STOCK_AT = ch3.VARS_AT + 4     # 파는 손님에게서 산 ブーメラン·くさりがま·はじゃのつるぎ 수(FC $62E7~$62E9)
WAGE_AT = ch3.VARS_AT + 7      # 오늘 일삯 16비트(FC $07C6~). 가게를 닫거나 그만둘 때 금화로
ITEM_AT = ch3.VARS_AT + 9      # 지금 손님: bit0-2 품목 칸, bit4-5 값(0 그대로, 1 깎음, 2 웃돈, 3 파는 손님)
# 둘째 변수 칸(dq4ch3slots L): 가게 키 덮어쓰기(dq4shopkey ONE_SHOT). 주인 가게를 열기 직전에 재고 조합으로 쓴다
SHOP_KEY_AT = VARS2_AT + _SLOTS['L'].vars2[0]
MODE_SELLER = 3
ROW = 16                       # 값·일삯 표의 값 칸마다 칸 수(ITEM_AT 의 bit4-5 가 그대로 16 단위)
# 무기점 품목: (DQ5 물건, FC 값). 앞 셋이 FC 무기점 목록(01 02 09), 뒤 셋은 파는 손님에게서 사면 그 재고만큼 목록 뒤에
# 붙는다(15:$B26B). 파는 손님의 품목은 15:$A4A1(01 02 09 0B 04)이고 rand < 8 이면 はじゃのつるぎ(23)
GOODS = ((0x02, 30), (0x06, 100), (0x1C, 200), (0x21, 350), (0x07, 550), (0x0D, 3500))
STOCKED = 3
HAJA = 5
SELLER_GOODS = 5


def prices():
    """[값 칸][품목]: 그대로, 깎음(− 값/10, 최소 1), 웃돈(+ 값/10), 파는 손님(p − ⌊(p + 3)/4⌋, 15:$B4A4)."""
    def tenth(p):
        return max(1, p // 10)
    return [[p for _, p in GOODS], [p - tenth(p) for _, p in GOODS], [p + tenth(p) for _, p in GOODS],
            [p - (p + 3) // 4 for _, p in GOODS]]


def wages():
    """[값 칸][품목]: 판 값 >> 4, 웃돈이면 >> 3, 0 이면 1(15:$A297·$9DB8). 파는 손님은 일삯이 늘지 않음."""
    table = prices()
    return [[max(1, p >> (3 if mode == 2 else 4)) for p in table[mode]] for mode in range(3)] + [[0] * len(GOODS)]


CLOSE_WAGE = 100
# FC 손님 갈래 문턱(rand 0~255). 이 엔진의 난수 장치는 N 을 주면 0~N-1 이라 255 로 부른다
SELLER_BELOW = 0x30
HAJA_BELOW = 8
RESULT_BELOW = (0x20, 0x40, 0x60)       # 돈 모자람 / 소지품 가득 / 장비 못 함 / 나머지 팜
DISCOUNT_BELOW, RAISE_BELOW = 0x40, 0x80
LUCK_BELOW, LUCK40_BELOW = 0x80, 0x40      # 흥정 뒤 r2 의 두 문턱
TOM_GOLD = (2, 11)                      # 2 + rand mod 11(15:$A06E)
RAND = 0x00953A                         # JSL, A = N: 0~N-1(DP $10·$11 을 씀)

TOWN, HOUSE, CELLAR = '3E/00', ch3.HOUSE, '3E/02'   # FC 16/00 마을·무기점, 16/01 집, 16/02 무기점 아래층


def cell(x, y):
    return (2 * x, 2 * y + 1)


COUNTER_IN = cell(0x02, 0x1A)          # 일하는 자리(카운터 안)
COUNTER_OUT = cell(0x04, 0x1A)         # 손님이 서는 자리(카운터 앞)
SHOP_DOOR = cell(0x07, 0x1A)           # 무기점 문. 손님이 들고 나는 자리, 가게를 닫은 뒤 서는 자리(FC 1D 이벤트 5A)
# 손님이 나타나고 사라지는 자리(FC 1D 이벤트 2E 의 (06,1A)). 문 칸에 세우면 가게 안으로 걸어 들어오지 못했다(실측)
CUSTOMER_IN = cell(0x06, 0x1A)
FIRST_MASTER = cell(0x06, 0x1A)        # 첫 출근 꾸지람 주인(FC 슬롯 11 은 문 (07,1A) 에 서지만 문을 막지 않게 한 칸 안)
FIRST_ASIDE = ((0x05 * 2, 0x1A * 2 + 1), (0x05 * 2, 0x18 * 2 + 1))   # 꾸지람 뒤 주인이 비키는 길
# FC 는 일행이 문 밖 (08,1A) 에 서면 꾸지람. 문 칸 (07,1A) 까지 넣는다(셀 사각형, 양 끝 포함)
FIRST_TRIGGER = (0x07 * 2, 0x1A * 2, 0x08 * 2 + 1, 0x1A * 2 + 2)
COUNTER_X = 0x03 * 2                   # 카운터 칸. 주인공 X 가 이 칸 이상이면 카운터 바깥
CHURCH = (0x0C * 2, 0x04 * 2, 0x10 * 2 + 1, 0x06 * 2 + 1)    # 톰이 닿으면 03AE(FC 1D 이벤트 55, 톰의 X·Y)
# 필드에서 마을로 들면 서는 왼쪽 가장자리(FC (00,0D), dq4groupbuild LINKS). 맵을 이 자리에서 시작하면 필드에서 온 것
FIELD_ARRIVAL = (0, 0x0D * 2, 1, 0x0D * 2 + 2)
HELPER_CELL = (0, 1)                   # 보이지 않는 도우미 인물: 맵 왼쪽 위 벽 안
PARK = (2, 1)                          # 손님이 없을 때 서 있는 맵 왼쪽 위 구석(주인공이 닿지 않는 나무 안)

# 옮긴 인물(dq4npcport): (맵, 시간대, 셀) → 바꿀 것
MASTER = (TOWN, 'day', COUNTER_IN)                      # FC 16/00 슬롯 13, 대화 054
STRAYS = ((TOWN, 'day', cell(0x07, 0x1A)), (TOWN, 'day', cell(0x00, 0x25)), (TOWN, 'day', cell(0x01, 0x25)))
TOM = {'day': cell(0x18, 0x0B), 'night': cell(0x16, 0x0B)}   # FC 16/00 대화 058
SON = cell(0x17, 0x03)                                  # FC 16/00 슬롯 2, 대화 055
DOG = cell(0x1B, 0x04)                                  # FC 16/00 우리 안의 개(대화 0663)
NENE = {'day': ch3.NENE_CELL, 'night': cell(0x1D, 0x03)}     # FC 16/01 대화 057
NENE_FC_STEP = 8                                         # FC 슬롯 07 의 걸음 간격(차례, 머리 바이트 80 = 128프레임)
# FC 16/01 낮 목록의 둘째 네네(슬롯 07, 돌아다님). FC 는 첫머리 뒤 이쪽만 두지만, 첫머리 자리 (1B,04) 의 네네를 남기고 이쪽을
# 뺀다(한 사람만 서게, 말 거는 자리가 검사·첫머리 인물과 같게)
NENE_WALKER = (HOUSE, 'day', cell(0x21, 0x02))
POPOLO = {'day': (cell(0x1B, 0x07),), 'night': (cell(0x1B, 0x07), cell(0x10, 0x02))}
QUIT_MASTER = (CELLAR, 'day', cell(0x07, 0x04))        # FC 16/02 대화 052
MASTER_PIC = 0x07
WALK_SPEED = 0x02               # 인물 명령 1E: 7E:3360(01 이면 한 칸 8프레임)
CUSTOMER_PIC = 0x40            # FC 손님 겉모습 17(15:$A3FC 의 하나). 이 맵 인물이 이미 쓰는 그림이라 OBJ 자리가 늘지 않음
# FC 는 손님마다 1D:$A3FC[rand & 7](그림 11 14 17 18 3B 1F 22 21)로 겉모습을 고른다. 인물 그림은 맵에 들 때 세트마다 한 번
# VRAM 에 올라가고 슬롯은 칸 목록 번호(7E:3200+슬롯)로 그 타일을 가리키므로, 같은 맵 낮의 다른 인물이 쓰는 그림이면 그
# 인물의 칸 목록 번호를 베껴 겉모습만 바꿀 수 있다(실측). 낮 3E/00 에 올라와 있는 FC 짝은 14(29)·17·21(40)뿐이라 나머지
# 칸은 같은 맵 마을 사람 그림 05(두건 쓴 여자)·0B(소년)로 채운다
LOOKS = (0x05, 0x29, 0x40, 0x0B, 0x05, 0x29, 0x0B, 0x40)
CUSTOMER_SLOT = 0x08           # 목록 맨 앞이라 물체 슬롯 08(실측)
SLOT_CELLS, SLOT_PIC, SLOT_DRAW = 0x7E3200, 0x7E3220, 0x7E32A0
# 가게를 닫을 때 주인(FC 슬롯 14)이 (01,1B)에 나타나 (02,1B), 곧 카운터 안 주인공 바로 아래로 한 걸음 걸어와 0341(실측)
CLOSE_FROM, CLOSE_AT = cell(0x01, 0x1B), cell(0x02, 0x1B)

# 빌릴 인물 스크립트(dq4ch3slots L): 낮 칸 10:9B81, 밤 칸 10:A031
DAY_LIST, NIGHT_LIST = '10:9B81', '10:A031'
SCRIPTS = {'customer': (DAY_LIST, 0, '10:9B88'), 'first_master': (DAY_LIST, 1, '10:9BEC'),
           'master': (DAY_LIST, 8, '10:9C82'), 'tom': (DAY_LIST, 9, '10:9CBD'),
           'helper': (DAY_LIST, 10, '10:9D34'), 'dog': (DAY_LIST, 11, '10:9D83'),
           'helper_night': (NIGHT_LIST, 0, '10:A038'), 'dog_night': (NIGHT_LIST, 1, '10:A04F'),
           'son': (DAY_LIST, 12, '10:9DD2'), 'cellar': (DAY_LIST, 13, '10:9E21'),
           'son_night': (NIGHT_LIST, 2, '10:A07B')}


def _mark(*pieces):
    """메시지 코드 목록의 글자 사이에 숫자({N} 1004)·물건 이름({I} 100A)·루틴 부르기({R} 101D)를 넣는다."""
    marks = {'①': 0x1004, '②': 0x100A, '③': 0x101D}
    out = []
    for piece in pieces:
        if not isinstance(piece, str):
            out.append(piece)
            continue
        buf = ''
        for c in piece:
            if c in marks:
                if buf:
                    out.append(buf)
                    buf = ''
                out.append(marks[c])
            else:
                buf += c
        if buf:
            out.append(buf)
    return out


def _gain(who='톨네코'):
    """FC 「…は [F8]ゴールドを てにいれた！」: 서술 한 쪽(앞에 쪽 넘김)."""
    return [ch1.PAGE] + _mark(*narrate(f'{who}는 ①골드를/손에 넣었다!'))[:-1]


def _join(*parts):
    """메시지 여럿(끝 코드 달린 코드 목록)을 쪽 넘김으로 이어 한 메시지로."""
    out = []
    for p in parts:
        body = p[:-1] if p and p[-1] == ch1.END else p
        if out and body and body[0] != ch1.PAGE:
            out.append(ch1.PAGE)
        out += body
    return out + [ch1.END]


# FC 메시지를 옮겼다. 서술은 해라체, 인물은 입말. ①·②·③ 은 _mark 의 자리
MESSAGES = {
    # 네네·포포로(FC 16/01)
    'bento': pages('네네', '자, 여기 도시락./오늘도 힘내고 와요.'),                          # 080E
    'go_west': pages('네네', '집을 나서면/졸지 말고/곧장 서쪽으로/걸어가요.', '그럼 힘내고 와요.'),   # 080A
    'forgot': pages('네네', '어머 여보./뭐 두고 간 거라도/있어요?', '일 힘내고 와요./쪽.'),    # 0810
    'dream': pages('네네', '있잖아요……/우리도 언젠가는/우리 가게를/갖고 싶네요.',           # 080F
                   '당신은 언제까지나/남 밑에서 일할/사람이 아니에요.',
                   '그렇게 생각해서/나는 당신과/결혼한 거예요.', '물론 그것만은/아니지만요. 우후.'),
    'home': pages('네네', '어머 여보, 왔어요?/많이 힘들었죠?'),                               # 080B
    'night_home': pages('네네', '어서 와요./이렇게 늦게까지/정말 수고 많았어요.'),            # 0811
    'goodnight': pages('네네', '자, 푹 쉬어요./잘 자요, 여보……'),                            # 080C
    'morning': pages('네네', '좋은 아침, 여보./벌써 아침이에요.'),                            # 080D
    'popolo_day': say('음냐음냐……/아빠, 다녀오세요……'),                                      # 0661
    'popolo_night': say('다녀오셨어요!/응, 나 착하게/있었어요.',                              # 0554
                        '나 크면/아빠처럼 돈 많이 벌어서/아빠랑 엄마/편하게 해 줄게요!'),
    # 무기점 주인(FC 16/00·16/02)
    'late': say('늦었잖아!/자, 가게 안으로/들어와, 들어와!'),                                  # 02F3
    'how': say('거기 서 있으면/손님이 올 거야.', '급료는 판 만큼/제대로 쳐줄 테니/열심히 일하라고.',   # 031D
               '그럼 맡긴다./나는 아래층에/있을 테니까.'),
    'across': say('그런 데 멀뚱히/서 있지 말고/얼른 이쪽으로/돌아와.', '아니면 오늘은/손님으로 온 건가?'),  # 0323
    'customer_ok': say('뭐야, 그랬던 거야?/좋아, 알았어!'),                                   # 0324
    'come_in': say('그럼 얼른/이쪽으로 와.'),                                                  # 0325
    'work': say('기다렸어./일하러 온 거지?'),                                                  # 0326
    'not_today': say('그래?/뭐, 너도 이것저것/하고 싶은 일이/있겠지.',                         # 0328
                     '알았어! 힘내라고./그리고 여기서/일하고 싶어지면/다시 돌아와.'),
    'closing': _join(say('오늘은 벌써/늦었으니 슬슬/가게 문 닫자./수고했어.', '자, 오늘 급료다.'),   # 0341
                     _gain(), say('내일도 잘 부탁해.')),
    'quit_ask': say('왜 그래?/오늘은 이만/끝낼 텐가?'),                                        # 087F
    'quit_pay': _join(say('수고했어./그럼 지금 급료를/계산해 주지.', '자, 오늘 급료다.'), _gain()),  # 0880
    'tomorrow': say('내일도 잘 부탁해.'),                                                      # 0881
    'back_to_work': say('그럼 얼른 가게로/돌아가서/장사를 계속해 줘.', '그만둘 때는/여기로 오라고.'),  # 0882
    # 손님(FC 15:$A2FC~)
    'angry': say('이 가게는 장사할/마음이 있는 거야?/언제까지 기다리게/할 셈이야! 흥흥.'),       # 067A
    'is_shop': say('여기가 무기점인가?'),                                                      # 0329
    'wrong': say('뭐야, 아닌가./실례했네.'),                                                   # 032A·033B
    'show': say('파는 물건 좀/보여 주겠나?'),                                                  # 032B
    'joke': say('어이 어이./농담 말고/보여 주게.'),                                            # 032C
    'buy': _mark(*say('②{을} 사지./③①골드면 되지?')),                                         # 032D
    'kidding': say('자네 농담을/좋아하는구먼……'),                                              # 032E
    'bought': say('아니, 좋은 물건을/샀어./고맙네. 또 오지.'),                                 # 032F
    'discount': _mark(*say('뭐야, 깎아 주는 건가!/②{을}/③①골드에/사도 되겠나?')),              # 0330
    'raise': _mark(*say('뭐라고? 값을/올렸다고?', '②{이}/오늘부터 ③①골드가/됐다고?')),          # 0331
    'raise_ok': say('할 수 없지./그 값에 사지./고맙네.'),                                       # 0332
    'no_thanks': say('그럼 됐네./다음에 보세!'),                                                # 0333
    'no_money': say('이런, 그걸 사기엔/돈이 모자랐군.', '실례했네./또 오지.'),                  # 0335
    'full': say('어라? 잠깐./소지품이/꽉 찬 모양이야.', '어디서 팔든 버리든/하고 올 테니/잘 부탁하네!'),  # 0336
    'no_equip': say('이런! 나는 이걸/장비할 수 없나 봐./그래도 팔아 주겠나?'),                  # 0337
    'gift': say('고맙네./아는 사람한테라도/선물해야겠군./그럼 또 보세.'),                       # 0338
    'no_sale': say('역시 안 되나……/실례했네.'),                                                # 0339
    'sell_ask': say('실은 무기를/팔고 싶은데/사 주겠나?'),                                      # 033C
    'other_shop': say('그런가. 할 수 없지./다른 가게로/가 봐야겠군.'),                          # 033D
    'offer': _mark(*say('② 말인데/③①골드에 어떤가?')),                                        # 033E
    'refused': say('뭐야, 필요 없나……/그럼 다른 데를/알아볼까.'),                               # 033F
    'sold_to': say('이야, 보는 눈이/있구먼!/자네 좋은 장사꾼이/되겠어!', '그럼 고맙네.'),       # 0340
    # 톰 노인(FC 16/00 대화 058)
    'tom_hello': pages('톰', '오오, 톨네코!/이 톰 영감도/나이를 먹어서인지/다리 허리가 약해져서.'),   # 0815
    'tom_ask': pages('톰', '사례는 할 테니/이 늙은이를 교회까지/밀어다 주지 않겠나?'),          # 0816
    'tom_go': pages('톰', '그럼 잘 밀어 주게.'),                                                # 0817
    'tom_no': pages('톰', '그런가……/아쉽구먼.'),                                                # 0818
    'tom_push': pages('톰', '이봐, 왜 그러나?/좀 더 힘껏/밀지 못하겠나.'),                       # 0819
    'tom_son': pages('톰', '내 아들 녀석은/지독한 난봉꾼이라/마을을 뛰쳐나가서는/그걸로 끝이야.',  # 081B
                     '지금쯤 어디서/뭘 하고 있는지.'),
    'tom_night': pages('톰', '뒤에 있는 건/아들 녀석이 기르던/개인데, 아들 말밖에/안 들어서 말이지……',  # 0822
                       '불쌍하지만/우리에 넣어/두었다네.'),
    'tom_church': _join(pages('톰', '아이고, 교회에/다 왔구먼./미안했네./이걸 받아 주게.'), _gain()),  # 03AE
    # 톰의 아들(FC 대화 055)
    'son_lend': say('톨네코 씨!/나야, 톰의 아들!/덕분에 돌아올 수/있었어.', '맞다, 사례를/해야지.',   # 084B
                    '응? 사례는 됐고/개 토마스를/빌려 달라고?/그거야 쉽지!',
                    '여우 사냥이/특기인 개라/분명 쓸모가/있을 거야.'),
    'son_dog': say('토마스,/톨네코 씨 말을/잘 들어야 한다!'),                                   # 03AD
    'son_return': say('여어, 톨네코 씨./개를 돌려주러/와 준 건가?'),                            # 0899
    'son_thanks': say('좋아, 토마스/수고했다./자, 우리로/돌아가렴!'),                           # 089A
    'son_luck': say('톨네코 씨/당신의 성공을/빌게!'),                                           # 089B
    'son_later': say('그럼 돌려주고/싶어지면 언제든/와 줘./나는 여기 있으니까.'),               # 089C
}

# 네이티브 안의 자료(dq4brkscan 이 코드로 풀지 않게)
DATA_ENTRIES = ('ids', 'prices', 'wages', 'looks', 'close_event', 'sleep_event')

TALKS = ('nene', 'popolo_day', 'popolo_night', 'late', 'master', 'quit', 'buyer_intro', 'buyer', 'seller', 'tom',
         'son')
# 첫 칸(표 칸 0)은 네네의 잠: dq4ch3opencheck 의 공용 장치 시험이 이 칸을 바꿔 네네 대화로 부른다
CALLS = {'sleep': ('sleep', 0), 'where': ('where', 0), 'prep': ('prep', 0), 'result': ('result', 0),
         'haggle': ('haggle', 0), 'sell': ('sell', 0),
         'buy_in': ('buy_in', 0), 'pay_wage': ('pay_wage', 0), 'shop_key': ('shop_key', 0)}


def _flag_addr(flag):
    return 0x7E2190 + flag[0]


def _set(flag):
    a = _flag_addr(flag)
    return lda(a) + bytes((0x09, flag[1])) + sta(a)


def _clear(*flags):
    a = _flag_addr(flags[0])
    mask = 0
    for f in flags:
        if _flag_addr(f) != a:
            raise ValueError('같은 바이트의 flag 만')
        mask |= f[1]
    return lda(a) + bytes((0x29, ~mask & 0xFF)) + sta(a)


def _rand(n):
    """A(8비트) = 0~n-1. X·Y 는 지키지 않는다."""
    return bytes((0xA9, n, 0x22)) + _al(RAND)


POLL_END = {res: bytes((0xC2, 0x30, 0x7A, 0xFA, 0x68, 0x2B, 0xAB, 0xA9, res, 0x00, 0x28, 0x6B)) for res in (0, 1)}


def _where():
    """대화 호출: 주인공이 카운터 바깥이면 ACROSS, 카운터 안 일하는 자리면 HERE_."""
    a = Asm()(ENTER, _clear(ACROSS, HERE_))
    a(lda(0x7E3020), 0x29, 0x7F, 0xC9, COUNTER_X).br(BCC, 'in')(_set(ACROSS))
    a.label('in')(lda(0x7E3020), 0x29, 0x7F, 0xC9, COUNTER_IN[0]).br(BNE, 'end')
    a(lda(0x7E3080), 0x29, 0x7F, 0xC9, COUNTER_IN[1]).br(BNE, 'end')(_set(HERE_))
    return a.label('end').bytes() + LEAVE


def _hero_across():
    """인물 명령 05: 주인공이 카운터 바깥(손님 쪽)이면 0."""
    a = Asm()(ENTER, 0xE2, 0x30, lda(0x7E3020), 0x29, 0x7F, 0xC9, COUNTER_X).br(BCS, 'go')
    return a(POLL_END[1]).label('go')(POLL_END[0]).bytes()


def _pace():
    """인물 명령 05: 손님 사이의 쉼. 처음 부르면 50 + rand(38) 차례(이동 간격 1 의 8프레임씩, FC 실측 400~700프레임)를
    잡고 1, 그 뒤 하나씩 줄여 0 이 되면 0."""
    a = Asm()(ENTER, lda(PACE)).br(BNE, 'count')
    a(_rand(38), 0x18, 0x69, 50, sta(PACE)).br(BRA, 'wait')
    a.label('count')(0x3A, sta(PACE)).br(BEQ, 'go')
    a.label('wait')(POLL_END[1]).label('go')(POLL_END[0])
    return a.bytes()


def _arrive():
    """인물 명령 37: 손님 하나의 값을 지우고 난수로 파는 손님·사는 손님과 품목을 정한다. 사는 손님의 품목은 무기점
    목록(앞 셋 + 재고가 있는 뒤 셋)의 rand mod 개수."""
    temp_keep = ~(ACROSS[1] | START[1] | SLEPT[1]) & 0xFF
    a = Asm()(ENTER, 0xE2, 0x30, 0xA9, 0x00, sta(_flag_addr(SELLER)))
    a(lda(TEMP), 0x29, ~temp_keep & 0xFF, sta(TEMP))
    a(_rand(0xFF), 0xC9, SELLER_BELOW).br(BCS, 'buyer')(_set(SELLER))
    a(_rand(0xFF), 0xC9, HAJA_BELOW).br(BCS, 'common')(0xA9, HAJA).br(BRA, 'seller_item')
    a.label('common')(_rand(SELLER_GOODS))
    a.label('seller_item')(0x09, MODE_SELLER << 4, sta(ITEM_AT)).brl('end')
    a.label('buyer')(0xA2, STOCKED)
    for k in range(STOCKED, len(GOODS)):
        a(lda(STOCK_AT + k - STOCKED)).br(BEQ, f'none{k}')(0xE8).label(f'none{k}')
    a(_pick(), 0xC9, STOCKED).br(BCC, 'buyer_item')
    a(0x38, 0xE9, STOCKED, 0xA8, 0xA2, STOCKED)
    a.label('scan')(0xBF, *_al(STOCK_AT - STOCKED)).br(BEQ, 'skip')(0xC0, 0x00).br(BEQ, 'found')(0x88)
    a.label('skip')(0xE8, 0xE0, len(GOODS)).br(BCC, 'scan')(0xA9, 0x00).br(BRA, 'buyer_item')
    a.label('found')(0x8A)
    a.label('buyer_item')(sta(ITEM_AT))
    a.label('end')
    return a.bytes() + LEAVE


def _shop_key():
    """대화 호출: 주인 가게를 열기 직전에 재고 조합(STOCK_AT 의 k 번째가 0 이 아니면 bit k)으로 가게 키를 덮어쓴다
    (dq4shopport 가 조합마다 둔 무기 목록)."""
    a = Asm()(ENTER, 0xE2, 0x30, 0xA0, ONE_SHOT.start)
    for k in range(len(GOODS) - STOCKED):
        a(lda(STOCK_AT + k)).br(BEQ, f'none{k}')(0x98, 0x09, 1 << k, 0xA8).label(f'none{k}')
    return a(0x98, sta(SHOP_KEY_AT)).bytes() + LEAVE


def _look(at):
    """인물 명령 37: 다음 손님 겉모습을 LOOKS[rand(8)] 로. 그 그림을 쓰는 다른 슬롯이 없으면(숨은 인물) 그대로 둔다."""
    a = Asm()(ENTER, 0xE2, 0x30, _rand(len(LOOKS)), 0xAA, 0xBF, *_al(at['looks']), 0xA2, 0x03)
    a.label('scan')(0xE0, CUSTOMER_SLOT).br(BEQ, 'next')(0xDF, *_al(SLOT_PIC)).br(BEQ, 'found')
    a.label('next')(0xE8, 0xE0, 0x20).br(BCC, 'scan').br(BRA, 'end')
    a.label('found')(sta(SLOT_PIC + CUSTOMER_SLOT), 0xBF, *_al(SLOT_CELLS), sta(SLOT_CELLS + CUSTOMER_SLOT))
    # 32A0 의 위 두 비트는 그림 세트가 고르는 그리기 루틴(dq5-graphics-format 「인물 그림」)이라 함께 옮긴다
    a(0xBF, *_al(SLOT_DRAW), 0x29, 0xC0, 0x48, lda(SLOT_DRAW + CUSTOMER_SLOT), 0x29, 0x3F, 0x03, 0x01)
    a(sta(SLOT_DRAW + CUSTOMER_SLOT), 0x68)
    return a.label('end').bytes() + LEAVE


def _pick():
    """A = 사는 손님 품목 칸 = rand(목록 수 X). BUYER_PICK 이 있으면(검사가 품목을 고를 때) 그 칸, 같은 5바이트."""
    if BUYER_PICK is None:
        return bytes((0x8A, 0x22)) + _al(RAND)
    return bytes((0xA9, BUYER_PICK, 0xEA, 0xEA, 0xEA))


BUYER_PICK = None


def _set_talk(talks):
    """인물 명령 37(손님 슬롯 $90): 그 슬롯의 대화 번호를 지금 단계의 대화로(파는 손님, 값 제시부터의 사는 손님, 처음의
    사는 손님). 한 대화 스크립트가 256바이트까지라 사는 손님을 둘로 나눴다."""
    a = Asm()(ENTER, 0xE2, 0x30, 0xA6, 0x90)

    def put(talk):
        return bytes((0xA9, talk & 0xFF, 0x9F, *_al(0x7E36E0), 0xA9, talk >> 8, 0x9F, *_al(0x7E3700)))
    a(lda(_flag_addr(SELLER)), 0x29, SELLER[1]).br(BEQ, 'buyer')(put(talks['seller'])).br(BRA, 'end')
    a.label('buyer')(lda(_flag_addr(STAGE)), 0x29, STAGE[1]).br(BEQ, 'intro')(put(talks['buyer'])).br(BRA, 'end')
    a.label('intro')(put(talks['buyer_intro']))
    a.label('end')
    return a.bytes() + LEAVE


def _item_to_f5(at):
    """$F5 = 지금 품목의 DQ5 물건 번호({I}), 7E:0F13~0F15 = 값 루틴(메시지의 {101D} 가 JSL 해 {N} 앞에 $F5 를 값으로)."""
    price = at['price_to_f5']
    return (bytes((0xE2, 0x30)) + lda(ITEM_AT) + bytes((0x29, 0x07, 0xAA, 0xBF)) + _al(at['ids']) +
            bytes((0x85, 0xF5, 0x64, 0xF6, 0x64, 0xF7, 0xA9, price & 0xFF)) + sta(0x7E0F13) +
            bytes((0xA9, price >> 8 & 0xFF)) + sta(0x7E0F14) + bytes((0xA9, price >> 16)) + sta(0x7E0F15))


def _prep(at):
    """대화 호출(값을 보이기 전): 흥정·결과 값을 지우고, 사는 손님이면 값 칸을 그대로로, $F5·값 루틴을 둔다."""
    a = Asm()(ENTER, _clear(NO_MONEY, FULL, NO_EQUIP, SOLD, LUCK), _clear(DISCOUNT, RAISE, AGAIN))
    a(lda(ITEM_AT), 0x29, 0x30, 0xC9, MODE_SELLER << 4).br(BEQ, 'keep')
    a(lda(ITEM_AT), 0x29, 0x07, sta(ITEM_AT))
    a.label('keep')(_item_to_f5(at))
    return a.bytes() + LEAVE


def _price_to_f5(at):
    """메시지 {101D} 가 JSL: $F5~$F7 = 값 표[값 칸 × 8 + 품목](16비트)."""
    return (ENTER + lda(ITEM_AT) + bytes((0x29, 0x37, 0xC2, 0x30, 0x29, 0xFF, 0x00, 0x0A, 0xAA, 0xBF)) +
            _al(at['prices']) + bytes((0x85, 0xF5, 0xE2, 0x20, 0x64, 0xF7)) + LEAVE)


def _result():
    """대화 호출(값에 「예」): r < 20 돈 모자람, < 40 소지품 가득, < 60 장비 못 함, 나머지 팜."""
    a = Asm()(ENTER, _clear(NO_MONEY, FULL, NO_EQUIP, SOLD), _rand(0xFF))
    for flag, below in zip((NO_MONEY, FULL, NO_EQUIP), RESULT_BELOW):
        a(0xC9, below).br(BCS, f'not{below}')(_set(flag)).brl('end').label(f'not{below}')
    a(_set(SOLD)).label('end')
    return a.bytes() + LEAVE


def _haggle(at):
    """대화 호출(값에 「아니오」): r < 40 깎음(DISCOUNT, 값 칸 1), < 80 웃돈(RAISE, 값 칸 2), 나머지 흥정 없음. 깎거나
    올리면 $F5·값 루틴을 그 값으로 둔다. 그 뒤 갈래가 볼 둘째 난수 r2 도 여기서 굴린다: LUCK = r2 < 80, LUCK40 = r2 < 40
    (갈래마다 r2 를 한 번만 보므로 한 값으로 두 문턱을 둬도 FC 와 같은 확률)."""
    a = Asm()(ENTER, _clear(LUCK), _clear(LUCK40), _rand(0xFF), 0x48, 0xC9, LUCK_BELOW).br(BCS, 'r40')(_set(LUCK))
    a.label('r40')(0x68, 0xC9, LUCK40_BELOW).br(BCS, 'r')(_set(LUCK40))
    a.label('r')(_rand(0xFF), 0xC9, DISCOUNT_BELOW).br(BCS, 'raise')
    a(_set(DISCOUNT), 0xA9, 0x10).br(BRA, 'mode')
    a.label('raise')(0xC9, RAISE_BELOW).br(BCS, 'end')(_set(RAISE), 0xA9, 0x20)
    a.label('mode')(0x48, lda(ITEM_AT), 0x29, 0x07, 0x03, 0x01, sta(ITEM_AT), 0x68, _item_to_f5(at))
    a.label('end')
    return a.bytes() + LEAVE


def _sell(at):
    """대화 호출(팜): 일삯 += 일삯 표[값 칸 × 8 + 품목], 오늘 일함. 목록 뒤 품목이면 그 재고 − 1. 일삯이 100 이상이면 CLOSE."""
    a = Asm()(ENTER, _set(WORKED), lda(ITEM_AT), 0x29, 0x37, 0xC2, 0x30, 0x29, 0xFF, 0x00, 0x0A, 0xAA)
    a(0x18, lda(WAGE_AT), 0x7F, *_al(at['wages']), sta(WAGE_AT), 0xC9, CLOSE_WAGE, 0x00).br(BCC, 'stock')
    a(0xE2, 0x20, _set(CLOSE))
    a.label('stock')(0xE2, 0x30, lda(ITEM_AT), 0x29, 0x07, 0xC9, STOCKED).br(BCC, 'end')(0xAA)
    a(0xBF, *_al(STOCK_AT - STOCKED)).br(BEQ, 'end')(0x3A, 0x9F, *_al(STOCK_AT - STOCKED))
    a.label('end')
    return a.bytes() + LEAVE


def _buy_in():
    """대화 호출(파는 손님에게서 삼): 목록 뒤 품목이면 그 재고 + 1(FF 에서 멈춤). 금화·일삯은 그대로(FC 실측)."""
    a = Asm()(ENTER, 0xE2, 0x30, lda(ITEM_AT), 0x29, 0x07, 0xC9, STOCKED).br(BCC, 'end')(0xAA)
    a(0xBF, *_al(STOCK_AT - STOCKED), 0x1A).br(BEQ, 'end')(0x9F, *_al(STOCK_AT - STOCKED))
    a.label('end')
    return a.bytes() + LEAVE


def _pay():
    """대화 호출·이벤트 A0: 금화 += 일삯, $F5~$F7 = 일삯, 일삯 0, 오늘 일 마침."""
    a = Asm()(ENTER, 0xC2, 0x30, lda(WAGE_AT), 0x85, 0xF5, 0x18, lda(ch2.GOLD_AT), 0x65, 0xF5, sta(ch2.GOLD_AT))
    a(0xE2, 0x20, 0x64, 0xF7, lda(ch2.GOLD_AT + 2), 0x69, 0x00, sta(ch2.GOLD_AT + 2))
    a(0xC2, 0x20, 0xA9, 0x00, 0x00, sta(WAGE_AT), 0xE2, 0x20, _set(DONE))
    return a.bytes() + LEAVE


def _night():
    """이벤트 A0: 필드 시간을 밤 첫머리로(FC 1D 이벤트 5A 의 $62ED = 8C 자리). 다시 불러온 맵이 밤 목록·밤 색이 된다."""
    return ENTER + bytes((0xC2, 0x20, 0xA9, NIGHT_TIME & 0xFF, NIGHT_TIME >> 8)) + sta(ch2.TIME_AT) + \
        bytes((0xE2, 0x20)) + LEAVE


NIGHT_TIME = 0x00F0             # dq4ch2event.TIME_AT 이 F0 이상이면 밤


def _rest():
    """이벤트 A0(잠): 걷는 일행 모두 HP·MP 를 채우고(FC 실측), 아침, 날수 + 1(공용 next_day), 오늘 일한 것·마침을 지우고
    오늘 도시락을 켠다(FC 15:$9DED: $6284 &= FA, $6285 |= 02)."""
    a = Asm()(ENTER, 0xC2, 0x30, 0xA2, 0x00, 0x00)
    # 쓰러진 사람(+1 bit7 꺼짐)은 그대로
    a.label('rec')(0xBF, *_al(ch2.PARTY_AT + 0x01), 0x29, 0x80, 0x00).br(BEQ, 'skip')
    a(0xBF, *_al(ch2.PARTY_AT + 0x0E), 0x9F, *_al(ch2.PARTY_AT + 0x02))
    a(0xBF, *_al(ch2.PARTY_AT + 0x10), 0x9F, *_al(ch2.PARTY_AT + 0x04))
    a.label('skip')(0x8A, 0x18, 0x69, ch3.RECORD, 0x00, 0xAA, 0xE0, ch3.RECORD * ch3.PARTY_MAX, 0x00).br(BCC, 'rec')
    a(0xA9, ch2.MORNING & 0xFF, ch2.MORNING >> 8, sta(ch2.TIME_AT), 0xE2, 0x20)
    a(0x22, *_al(ch3.native()[1]['next_day']))
    a(_clear(WORKED, DONE), _set(BENTO_TODAY))
    return a.bytes() + LEAVE


def _wake():
    """이벤트 A0(깬 뒤): 일행 기록 0 에 도시락이 없고 빈 물건 칸이 있으면 첫 빈 칸에 넣는다(FC 15:$A794·$A79F: 이미 가졌거나
    칸이 다 찼으면 주지 않음). 이번 방문에 잤음."""
    items = ch3.PARTY_ITEMS
    a = Asm()(ENTER, _set(SLEPT), 0xE2, 0x30, 0xA2, 0x00)
    a.label('has')(0xBF, *_al(items), 0xC9, BENTO).br(BEQ, 'end')(0xE8, 0xE0, ch3.ITEM_SLOTS).br(BCC, 'has')
    a(0xA2, 0x00).label('free')(0xBF, *_al(items), 0xC9, 0xFF).br(BEQ, 'put')
    a(0xE8, 0xE0, ch3.ITEM_SLOTS).br(BCC, 'free').br(BRA, 'end')
    a.label('put')(0xA9, BENTO, 0x9F, *_al(items))
    a.label('end')
    return a.bytes() + LEAVE


def _tom_slot(a, talk):
    """a 에 붙인다: X(8비트) = 톰(대화 번호 talk)의 인물 슬롯. 없으면 C = 1."""
    a(0xE2, 0x30, 0xA2, 0x08)
    a.label('t_next')(0xBF, *_al(0x7E36E0), 0xC9, talk & 0xFF).br(BNE, 't_skip')
    a(0xBF, *_al(0x7E3700), 0x29, 0x0F, 0xC9, talk >> 8).br(BEQ, 't_found')
    a.label('t_skip')(0xE8, 0xE0, 0x20).br(BCC, 't_next')(0x38).br(BRA, 't_out')
    a.label('t_found')(0x18).label('t_out')
    return a


def _tom_check(talk):
    """인물 명령 05: 톰이 교회 안(CHURCH)에 서 있으면 0."""
    x0, y0, x1, y1 = CHURCH
    a = _tom_slot(Asm()(ENTER), talk)
    a.br(BCS, 'far')
    for table, lo, hi in ((0x7E3020, x0, x1), (0x7E3080, y0, y1)):
        a(0xBF, *_al(table), 0x29, 0x7F, 0xC9, lo).br(BCC, 'far')(0xC9, hi + 1).br(BCS, 'far')
    a(POLL_END[0]).label('far')(POLL_END[1])
    return a.bytes()


def _tom_pay(talk):
    """인물 명령 37: 금화 += 2 + rand(11), $F5~ = 그 값, 밀기 끝(TOM_DONE), 톰이 더 밀리지 않게(31C0 bit1 끔)."""
    a = Asm()(ENTER, _rand(TOM_GOLD[1]), 0x18, 0x69, TOM_GOLD[0], 0x85, 0xF5, 0x64, 0xF6, 0x64, 0xF7)
    a(0xC2, 0x20, 0x18, lda(ch2.GOLD_AT), 0x65, 0xF5, sta(ch2.GOLD_AT), 0xE2, 0x20)
    a(lda(ch2.GOLD_AT + 2), 0x69, 0x00, sta(ch2.GOLD_AT + 2))
    a(_clear(TOM_PUSH, TOM_DONE), _set(TOM_DONE))
    _tom_slot(a, talk).br(BCS, 'end')(0xBF, *_al(0x7E31C0), 0x29, 0xFD, 0x9F, *_al(0x7E31C0))
    a.label('end')
    return a.bytes() + LEAVE


def _event_bytes(tokens):
    return b''.join(bytes((0x60, t[1] & 0xFF, t[1] >> 8)) if isinstance(t, tuple) else t for t in tokens)


def _warp(mp, at):
    g, n = (int(v, 16) for v in mp.split('/'))
    return bytes((0x90, g, n, *at, 0x01, 0x80))


def _close_tokens(ctx, at):
    """가게를 닫는 이벤트: 일삯을 받고(0341) 밤으로 무기점 문 앞에 다시 선다(FC 1D 이벤트 5A, 실측)."""
    m = ctx.msg['closing'] if ctx.msg else 0
    return [bytes((0xA0, *_al(at['pay_wage']))), ('msg', m),
            bytes((0xA0, *_al(at['night']))) + _warp(TOWN, SHOP_DOOR) + b'\xff']


def _sleep_tokens(ctx, at):
    """잠 이벤트: 채우기·아침 → 침대로 집을 다시 불러옴 → 080D·080E → 도시락."""
    m = ctx.msg or {'morning': 0, 'bento': 0}
    return [bytes((0xA0, *_al(at['rest']))) + _warp(HOUSE, ch3.START_CELL), ('msg', m['morning']), ('msg', m['bento']),
            bytes((0xA0, *_al(at['wake']), 0xFF))]


def native(ctx):
    import dq4prologue
    out = bytearray()
    at = {}

    def put(name, b):
        at[name] = ctx.code_at + len(out)
        out.extend(b)
    talk = ctx.talk or {name: 0 for name in TALKS}
    put('ids', bytes(i for i, _ in GOODS) + bytes(8 - len(GOODS)))
    # 표 칸 = ITEM_AT & 37(값 칸 × 16 + 품목)이라 값 칸마다 16칸
    put('prices', b''.join(p.to_bytes(2, 'little') for row in prices() for p in row + [0] * (ROW - len(GOODS))))
    put('wages', b''.join(w.to_bytes(2, 'little') for row in wages() for w in row + [0] * (ROW - len(GOODS))))
    # 값 루틴 주소가 _item_to_f5 에 들어가므로 먼저 둔다
    put('price_to_f5', _price_to_f5(at))
    put('where', _where())
    put('looks', bytes(LOOKS))
    put('look', _look(at))
    put('shop_key', _shop_key())
    put('pace', _pace())
    put('hero_across', _hero_across())
    put('arrive', _arrive())
    put('set_talk', _set_talk(talk))
    put('prep', _prep(at))
    put('result', _result())
    put('haggle', _haggle(at))
    put('sell', _sell(at))
    put('buy_in', _buy_in())
    put('pay_wage', _pay())
    put('night', _night())
    put('rest', _rest())
    put('wake', _wake())
    put('first_trigger', dq4prologue._inside(*FIRST_TRIGGER))
    put('tom_check', _tom_check(talk['tom']))
    put('tom_pay', _tom_pay(talk['tom']))
    put('at_counter', dq4prologue._all_at([(0, *COUNTER_IN, None)]))
    put('face_right', dq4prologue._hero_face(0x11))
    # 주인공 셀이 반 칸 어긋나 있어도(순간이동한 검사에서 Y 54) 카운터 안 칸에 맞춰 서게 Y 도 걷는다
    put('first_walk', dq4prologue.hero_goto([('x', COUNTER_IN[0]), ('y', COUNTER_IN[1])], None))
    put('counter_walk', dq4prologue.hero_goto([('x', COUNTER_IN[0]), ('y', COUNTER_IN[1])], None))
    put('close_event', _event_bytes(_close_tokens(ctx, at)))
    put('close', dq4prologue._event_start(at['close_event']))
    put('sleep_event', _event_bytes(_sleep_tokens(ctx, at)))
    put('sleep', dq4prologue._event_start(at['sleep_event']))
    return bytes(out), at


def events(ctx):
    return [_close_tokens(ctx, ctx.at), _sleep_tokens(ctx, ctx.at)]


# ---- 대화 ----

def _not(cond):
    return {**cond, "not": True}


YES = {"code": "05"}
WEAPON_SHOP = {"op": "service", "index": 1}    # DQ5 대화 번호 01 의 무기점(목록 키는 shop_key 가 덮어씀)
DAY = {"code": "14"}


def _flag_off(flag):
    return {"op": "flag-off", "index": flag[0], "mask": ~flag[1] & 0xFF}


def talk_scripts(ctx, flip_buy=False):
    """flip_buy 는 검사용: 값 물음(032D)의 「예」 조건을 뒤집는다(dq4ch3lakanabacheck 가 A 만으로 「아니오」 갈래를 돈다)."""
    say_, call, flag, on, when = ctx.say, ctx.call, ctx.flag, ctx.flag_on, ctx.when
    done = on(ANSWERED)
    nene = when(DAY,
                [when(flag(ch3.FRESH), [say_('go_west')], [when(flag(WORKED), [say_('home'), say_('goodnight'), call('sleep')],
                      [when(flag(BENTO_TODAY), [when(flag(SLEPT), [say_('dream')], [say_('forgot')])],
                            [say_('home'), say_('goodnight'), call('sleep')])])])],
                [say_('night_home'), say_('goodnight'), call('sleep')])
    master = [call('where'),
              when(flag(ACROSS), [say_('across'), when(YES, [say_('customer_ok'), call('shop_key'), WEAPON_SHOP],
                                                       [say_('come_in')])],
                   [say_('work'), when(YES, [on(START)], [say_('not_today')])])]
    quit_ = [when(flag(SHIFT), [when(flag(DONE), [say_('tomorrow')],
                                     [say_('quit_ask'), when(YES, [call('pay_wage'), say_('quit_pay'), say_('tomorrow')],
                                                             [say_('back_to_work')])])],
                  [say_('tomorrow')])]
    # 사는 손님. 물건을 보자고 하기 전(STAGE 꺼짐)과 값 제시부터로 나눈다. 다시 말을 걸 일(032C 뒤, 032E 뒤)은 AGAIN 을
    # 켜고 끝내 손님 스크립트가 다시 말을 건다
    # FC: 흥정을 거절하면 r2 < 80 이면 0333 으로 가고, 아니면 032E 뒤 처음 값으로 다시(032D)
    leave_or_again = when(flag(LUCK), [say_('no_thanks')], [say_('kidding'), on(AGAIN)])
    price = [call('prep'), say_('buy'),
             when(_not(YES) if flip_buy else YES, [call('result')],
                  [call('haggle'),
                   when(flag(DISCOUNT), [say_('discount'), when(YES, [call('result')], [leave_or_again])]),
                   when(flag(RAISE), [say_('raise'),
                                      when(YES, [when(flag(LUCK40), [say_('raise_ok'), call('sell')],
                                                      [say_('no_thanks')])],
                                           [leave_or_again])]),
                   when(_not(flag(DISCOUNT)), [when(_not(flag(RAISE)), [leave_or_again])])]),
             when(flag(NO_MONEY), [say_('no_money')]),
             when(flag(FULL), [say_('full')]),
             when(flag(NO_EQUIP), [say_('no_equip'), when(YES, [say_('gift'), call('sell')], [say_('no_sale')])]),
             when(flag(SOLD), [say_('bought'), call('sell')])]
    served = when(_not(flag(AGAIN)), [on(SERVED)])
    # 물건을 보자고 하면(032B 「예」) 값 제시부터는 손님 스크립트가 buyer 로 다시 말을 건다. 「아니오」 면 032C 를 「예」
    # 까지 되풀이한다(FC 실측): 「아니오」 마다 손님 스크립트가 다시 말을 걸어 JOKE 갈래로 032C 부터
    # 맞은 손님(SERVED)은 나가는 동안 말을 걸어도 다시 팔지 않는다(FC 15:$A26F 가 $6288 bit5 로 두 번 응대하지 않음)
    joke = [say_('joke'), when(YES, [_flag_off(JOKE), on(STAGE)], [on(JOKE)])]
    intro = [call('where'),
             when(flag(HERE_), [when(_not(flag(SERVED)), [
                 when(flag(JOKE), [on(AGAIN), *joke],
                      [say_('is_shop'), when(YES, [say_('show'), on(AGAIN), when(YES, [on(STAGE)], joke)],
                                             [say_('wrong')])]),
                 served])],
                  [say_('angry')]),
             done]
    buyer = [call('where'), when(flag(HERE_), [when(_not(flag(SERVED)), [*price, served])], [say_('angry')]), done]
    seller = [call('where'),
              when(flag(HERE_), [when(_not(flag(SERVED)), [say_('is_shop'),
                                 when(YES, [say_('sell_ask'),
                                            when(YES, [call('prep'), say_('offer'),
                                                       when(YES, [say_('sold_to'), call('buy_in')], [say_('refused')])],
                                                 [say_('other_shop')])],
                                      [say_('wrong')]),
                                 served])],
                   [say_('angry')]),
              done]
    tom = [when(DAY, [when(flag(TOM_DONE), [say_('tom_son')],
                           [when(flag(TOM_PUSH), [say_('tom_push')],
                                 [say_('tom_hello'), say_('tom_ask'),
                                  when(YES, [say_('tom_go'), on(TOM_PUSH)], [say_('tom_no')])])])],
                [say_('tom_night')])]
    # 여우를 쫓은 뒤(본몰 모듈의 FOXED, FC $6280&02)에는 개를 돌려받는 갈래(FC 대화 055)
    lend = [when(flag(ch3.DOG), [say_('son_dog')], [say_('son_lend'), on(ch3.DOG)])]
    son = [when(flag(FOXED),
                [when(flag(DOG_BACK), [say_('son_luck')],
                      [when(flag(ch3.DOG), [say_('son_return'),
                                            when(YES, [say_('son_thanks'), say_('son_luck'), _flag_off(ch3.DOG),
                                                       on(DOG_BACK)],
                                                 [say_('son_later')])],
                            lend)])],
                lend)]
    bodies = {'nene': [nene], 'popolo_day': [say_('popolo_day')], 'popolo_night': [say_('popolo_night')],
              'late': [say_('late')], 'master': master, 'quit': quit_, 'buyer_intro': intro, 'buyer': buyer,
              'seller': seller,
              'tom': tom, 'son': son}
    return [bodies[name] for name in TALKS]


# ---- 인물 스크립트 ----

def _cmd(op, *args, **kw):
    return {"op": op, "args": list(args), **kw}


def _wait_on(flag):
    """09: flag 가 켜질 때까지."""
    return _cmd('09', 0x80 | flag[0], flag[1])


def _if_on(flag, target):
    return _cmd('06', flag[0], flag[1], target=target)


def _if_off(flag, target):
    return _cmd('06', 0x80 | flag[0], flag[1], target=target)


def _or(flag):
    return _cmd('10', flag[0], flag[1])


def _and_off(*flags, **kw):
    mask = 0
    for f in flags:
        mask |= f[1]
    return _cmd('11', flags[0][0], ~mask & 0xFF, **kw)


def scripts(ctx):
    at = ctx.at
    talk_here = ch2.native()[1]['talk_here']
    call = lambda a, **kw: _cmd('37', *_al(a), **kw)  # noqa: E731
    poll = lambda a, **kw: _cmd('05', *_al(a), **kw)  # noqa: E731
    msg = lambda k: _cmd('21', *(ctx.msg[k].to_bytes(2, 'little') if ctx.msg else (0, 0)))  # noqa: E731
    hide = [_cmd('28', label='hide'), _cmd('52'), _cmd('16')]
    out_x, out_y = CUSTOMER_IN
    # 빌린 인물의 속도가 0 이라 걷기(13)가 끝나지 않았다(실측). 한 칸 4프레임으로. 숨기는 것은 DQ5 의 걷는 인물처럼 맵
    # 구석으로 순간이동(2B)해서 한다: 52(사라진 뒤 치우기)·53(나타나기) 뒤에는 걷기가 도착하지 않았다(실측)
    customer = [
        _cmd('1E', WALK_SPEED), _cmd('1C'), _cmd('2B', *PARK),
        # 기다림은 09 로: 06 으로 같은 자리로 되뛰면 두 명령이 한 프레임 안에서 끝없이 돌아(출근 중 일찍 그만둔 뒤 낮
        # 마을이 멈췄다, 실측) 차례를 넘기지 않는다
        _wait_on(SHIFT) | {"label": "wait"}, _cmd('09', DONE[0], DONE[1]), poll(at['pace']),
        _if_off(SHIFT, 'wait'), _if_on(DONE, 'wait'),
        # 주인공이 카운터 안에 선 뒤 조작을 막고서야 들어와, 걷는 길((12,53)~(8,53))이 주인공과 겹치지 않는다
        poll(at['at_counter']), _cmd('3F'), call(at['look']),
        _cmd('2B', out_x, out_y), _cmd('13', *COUNTER_OUT), _cmd('14'), _cmd('2F', 0x22),
        call(at['arrive']),
        _and_off(ANSWERED) | {"label": "talk"}, _and_off(AGAIN), call(at['set_talk']), call(talk_here),
        _wait_on(ANSWERED), _if_on(AGAIN, 'talk'),
        _if_on(CLOSE, 'close'),
        _cmd('13', out_x, out_y), _cmd('14'), _cmd('2B', *PARK), _cmd('40'), _cmd('03', target='wait'),
        # 가게를 닫는 것은 주인 스크립트가 맡는다(조작은 막힌 채)
        _cmd('2B', *PARK, label='close'), _cmd('16')]
    first = [_if_on(SEEN, 'hide'), _cmd('1E', WALK_SPEED), _cmd('1C'), poll(at['first_trigger']), _cmd('3F'), msg('late'),
             *[c for x, y in FIRST_ASIDE for c in (_cmd('13', x, y), _cmd('14'))],
             call(at['first_walk']), poll(at['at_counter']), call(at['face_right']), msg('how'),
             _or(SEEN), _or(SHIFT), _and_off(DONE), _cmd('40'), _cmd('28'), _cmd('52'), _cmd('16'), *hide]
    # 출근 중에는 맵 구석에서 기다리다 손님 스크립트가 가게를 닫으면(CLOSE, 손님 말이 끝난 뒤) 걸어 나와 0341. 숨는 것은
    # 52 가 아니라 2B 로: 52 로 치운 인물은 다시 걷지 못했다(손님 스크립트와 같은 실측). 일찍 그만둔 날(DONE)은 FC 처럼
    # ($6285 bit0 이 꺼져 슬롯 13 이 섬) 카운터에 서서 가게를 열어 준다. 다만 아래층에서 올라온 주인공이 계단 앞 칸
    # (4,55)에 서므로, 주인공이 카운터 바깥으로 나간 뒤에 선다(그 칸 위가 주인 자리라 먼저 서면 주인공이 갇혔다, 실측)
    # 첫 출근 전(SEEN 꺼짐)에 맵을 불러오면 첫 출근 주인이 출근을 맡고, 이 주인은 맵 구석에서 그날 가게를 닫을 때를 기다린다
    # (숨기만 하고 멈추면 첫날 일삯이 100 을 넘어도 가게가 닫히지 않았다, 실측)
    master = [_if_off(SEEN, 'shift'), _if_off(SHIFT, 'stand'), _if_off(DONE, 'shift'),
              _cmd('2B', *PARK), poll(at['hero_across']), _cmd('2B', *COUNTER_IN), _cmd('2F', 0x11),
              _wait_on(START) | {"label": "stand"}, _and_off(START), _cmd('3F'), _cmd('2B', *PARK),
              call(at['counter_walk']), poll(at['at_counter']), call(at['face_right']), msg('how'),
              _or(SHIFT), _and_off(DONE), _cmd('40'),
              _cmd('2B', *PARK, label='shift'), _cmd('1E', WALK_SPEED), _cmd('1C'), _wait_on(CLOSE), _wait_on(ANSWERED),
              _cmd('2B', *CLOSE_FROM), _cmd('13', *CLOSE_AT), _cmd('14'), _cmd('2F', 0x88), _cmd('40'),
              call(at['close']), _cmd('16'), *hide]
    tom = [_if_on(TOM_DONE, 'stand'), _wait_on(TOM_PUSH), _cmd('1F'), _cmd('1B'), _cmd('16', label='stand')]
    helper = [_cmd('07', *FIELD_ARRIVAL, target='field'), _cmd('03', target='tom'),
              _and_off(BENTO_TODAY, SHIFT, label='field'),
              _if_on(TOM_DONE, 'end') | {"label": "tom"}, _wait_on(TOM_PUSH), poll(at['tom_check']), _cmd('3F'),
              call(at['tom_pay']), msg('tom_church'), _cmd('40'), _cmd('16', label='end')]
    helper_night = [_cmd('07', *FIELD_ARRIVAL, target='field'), _cmd('16'),
                    _and_off(BENTO_TODAY, SHIFT, label='field'), _cmd('16')]
    dog = [_if_off(ch3.DOG, 'stay'), _if_on(DOG_BACK, 'stay'), _cmd('28'), _cmd('52'), _cmd('16', label='stay')]
    # 아들은 본몰 감옥에서 풀려난 뒤에만(FC 1C:$A29A 가 $6280&04 로 목록을 고침), 아래층 주인은 출근 중에만(1C:$A326)
    son = [_if_off(SON_FREED, 'hide'), _cmd('16'), *hide]
    cellar = [_if_off(SHIFT, 'hide'), _if_on(DONE, 'hide'), _cmd('16'), *hide]
    bodies = {'customer': customer, 'first_master': first, 'master': master, 'tom': tom, 'helper': helper,
              'dog': dog, 'helper_night': helper_night, 'dog_night': list(dog), 'son': son, 'son_night': list(son),
              'cellar': cellar}
    return [{"address": SCRIPTS[name][2], "commands": bodies[name]} for name in SCRIPTS]


def _src(name):
    lst, idx, _ = SCRIPTS[name]
    return {"list": lst, "index": idx}


def _person(name, time, at, facing, talk, gfx):
    # 이동 간격 0 이면 인물 스크립트가 차례를 받지 못한다(실측: 첫 출근 주인이 서 있기만 함). 1 이면 명령마다 8프레임
    return {"from": _src(name), "time": time,
            "fields": {"x": at[0], "y": at[1], "facing": facing, "talk": talk, "gfx": gfx, "layer": 0, "interval": 1}}


def _at(e):
    return (e["fields"]["x"], e["fields"]["y"])


def npc_lists(lists, ctx):
    """옮긴 목록을 고친다(대체 목록 없이 인물 스크립트가 flag 를 보고 숨거나 나타난다). 이 모듈이 맨 앞 차례라 뒤 모듈이
    3E/00·3E/01 목록을 베끼면 여기서 고친 인물이 함께 간다."""
    t = ctx.talk
    if TOWN not in lists:
        return [], []           # 인물 없이 옮긴 목록(dq4npcport.port 의 with_people=False)
    town = lists[TOWN]["entries"]
    strays = {(time, c) for m, time, c in STRAYS}
    before = len(town)
    town[:] = [e for e in town if (e["time"], _at(e)) not in strays]
    if before - len(town) != len(strays):
        raise SystemExit(f'{TOWN}: 무기점 일 인물(문·밖에 세운 FC 슬롯 11·14·15)이 {before - len(town)}명')
    hit = 0
    for k, e in enumerate(town):
        key = (e["time"], _at(e))
        if key == MASTER[1:]:
            town[k] = _person('master', 'day', COUNTER_IN, e["fields"]["facing"], t['master'], e["fields"]["gfx"])
            hit += 1
        elif key == ('day', TOM['day']):
            town[k] = _person('tom', 'day', TOM['day'], e["fields"]["facing"], t['tom'], e["fields"]["gfx"])
            hit += 1
        elif key == ('night', TOM['night']):
            e["fields"] = {**e["fields"], "talk": t['tom']}
            hit += 1
        elif _at(e) == SON:
            town[k] = _person('son' if e["time"] == 'day' else 'son_night', e["time"], SON, e["fields"]["facing"],
                              t['son'], e["fields"]["gfx"])
            hit += 1
        elif _at(e) == DOG:
            town[k] = _person('dog' if e["time"] == 'day' else 'dog_night', e["time"], DOG, e["fields"]["facing"],
                              e["fields"]["talk"], e["fields"]["gfx"])
            hit += 1
    if hit != 7:
        raise SystemExit(f'{TOWN}: 바꿀 인물(주인·톰 낮밤·아들 낮밤·개 낮밤)이 {hit}명')
    # 손님·첫 출근 주인·도우미는 목록 앞(낮 물체 슬롯 앞자리)에 둔다
    town[:0] = [_person('customer', 'day', CUSTOMER_IN, 'left', t['buyer_intro'], CUSTOMER_PIC),
                _person('first_master', 'day', FIRST_MASTER, 'right', t['late'], MASTER_PIC),
                _person('helper', 'day', HELPER_CELL, 'down', t['late'], 0),
                _person('helper_night', 'night', HELPER_CELL, 'down', t['late'], 0)]
    if HOUSE in lists:
        house = lists[HOUSE]["entries"]
        before = len(house)
        house[:] = [e for e in house if (e["time"], _at(e)) != NENE_WALKER[1:]]
        if before - len(house) != 1:
            raise SystemExit(f'{HOUSE}: 둘째 네네 {NENE_WALKER[2]} 이 {before - len(house)}명')
        # 첫머리 목록(dq4ch3event ch3_opening)은 이 손질 전에 기본 목록을 베낀 것이라 둘째 네네가 남는다. 첫머리 뒤 집을 다시
        # 불러오기 전까지 걸려 있으므로 거기서도 뺀다. dq4ch3event 가 뒤에 같은 목록 객체의 첫머리 네네 대화를 바꾸므로 제자리에서
        for lst in getattr(ctx, 'made_all', {}).values():
            if lst["name"] == 'ch3_opening':
                lst["entries"][:] = [e for e in lst["entries"] if (e["time"], _at(e)) != NENE_WALKER[1:]]
        for time, c in NENE.items():
            ctx.retalk(lists, HOUSE, c, t['nene'], time=time)
        # 낮 네네는 FC 슬롯 07 처럼 집 안을 돌아다닌다(128프레임마다 한 걸음, 실측). 첫머리는 따로 목록(dq4ch3event
        # ch3_opening)이라 서 있는 연출 그대로다
        import dq4npcport
        for e in house:
            if (e["time"], _at(e)) == ('day', NENE['day']):
                e["from"] = dq4npcport.WALK
                e["fields"] = {**e["fields"], "interval": dq4npcport.dq5_interval(NENE_FC_STEP)}
        for time, cells in POPOLO.items():
            for c in cells:
                ctx.retalk(lists, HOUSE, c, t[f'popolo_{time}'], time=time)
    if CELLAR in lists:
        cellar = lists[CELLAR]["entries"]
        hit = [k for k, e in enumerate(cellar) if (e["time"], _at(e)) == QUIT_MASTER[1:]]
        if len(hit) != 1:
            raise SystemExit(f'{CELLAR}: 아래층 주인 {QUIT_MASTER[2]} 이 {len(hit)}명')
        e = cellar[hit[0]]
        cellar[hit[0]] = _person('cellar', 'day', QUIT_MASTER[2], e["fields"]["facing"], t['quit'], e["fields"]["gfx"])
    return [], []


def start_messages(ctx):
    """{(맵, FC 대화, 밤 또는 None): 첫 메시지}: 3장 처음 상태(오늘 도시락 flag 꺼짐, 출근 전)에서 대화를 바꾼 인물(3장
    인물 검사의 기대값). 네네는 낮에도 오늘 도시락을 받기 전이라 잠 갈래다."""
    m = ctx.msg
    return {(HOUSE, FC_NENE, False): m['home'], (HOUSE, FC_NENE, True): m['night_home'],
            (HOUSE, FC_POPOLO_DAY, False): m['popolo_day'], (HOUSE, FC_POPOLO_NIGHT, True): m['popolo_night'],
            (TOWN, FC_TOM, False): m['tom_hello'], (TOWN, FC_TOM, True): m['tom_night']}


def absent(ctx):
    """{(맵, DQ5 셀 x, y, 밤)}: 처음 상태에서 없는 FC 인물. 카운터 주인은 첫 출근(꾸지람) 전에는 숨고, 문·밖에 세운 FC 슬롯
    11·14·15 와 집의 둘째 네네는 목록에서 뺐다(첫 출근 주인·손님·가게를 닫는 이벤트, 첫머리 자리 네네가 맡음). 아래층 주인은
    출근 전, 톰 아들은 본몰 감옥에서 풀려나기 전에 숨는다."""
    return {(m, *c, time == 'night') for m, time, c in (MASTER, *STRAYS, NENE_WALKER, QUIT_MASTER,
                                                         (TOWN, 'day', SON), (TOWN, 'night', SON))}


FC_NENE, FC_TOM, FC_SON, FC_MASTER, FC_QUIT = 0x057, 0x058, 0x055, 0x054, 0x052
FC_POPOLO_DAY, FC_POPOLO_NIGHT = 0x2C2, 0x1B5
