"""NDS 리메이크의 서장(산골 마을 지하 검술 수련과 마을 사람)을 1장 앞에 넣는다.

무대는 dq4groupbuild.py 가 새 그룹에 넣은 FC 14/00(습격 전 마을)과 14/01(지하)이다. 새 게임은 지하에서
장 제목 상자 「서장」으로 시작하고, 수련 뒤 주인공이 말을 걸면 검사가 예·아니요로 묻고, 나간다. 마을에는 NDS 서장의
마을 사람을 세운다. 개구리의 이야기를 들으면 지하에 신시아가 와서 모샤스를 보여 주고, 아버지와 저녁을 먹으면
검은 화면의 서술 뒤 1장 왕좌의 방(dq4chapter1)으로 옮긴다. 대사는 NDS 서장 대사(MESS/ja/b0200000.mpt)를
옮긴 것이다. dq4chapter1.py build 가 넣는다(--no-prologue 면 뺀다).
형식은 sfc/dq4/docs/dq4-prologue-format.md.
"""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4chapter1 as ch1  # noqa: E402
import dq4chapterbox as box  # noqa: E402
import dq4sparfx as fx  # noqa: E402
from dq4environmentrom import GROUPS  # noqa: E402
from dq5map import lorom  # noqa: E402

VILLAGE, CELLAR = (f'{g:02X}/{n:02X}' for g, n in (GROUPS['14-00'], GROUPS['14-01']))
SCENE = box.PROLOGUE
# 검사의 물음에 대답하면 켬. 자리는 dq4chapterbox.PROLOGUE
DONE = (SCENE.flag[0] - 0x7E2190, SCENE.flag[1])
START = (CELLAR, 3 * 2, 0x0F * 2)                    # 지하 아래 방 (3,0F), 검사 바로 아래(말을 걸 수 있게)
CODE_AT = 0x5EC000
# NDS mlb1a 의 수련: 검은 화면에서 칼 여섯 합(효과 0xAC + 효과음 0x62 + 기다리기 0x09), 그 뒤에 지하가 밝아진다.
# (효과음, NDS 효과(dq4sparfx.EFFECTS 차례), 다음 합까지 프레임). 기다림은 NDS 스크립트 값(60fps).
# 銅の剣 412·鋼の剣 416 은 DQ4 가 부르지 않는 효과음 40 의 갈래 01·02 에 옮겨 둔다(dq4sound-game.args 의 --sfx-pcm).
# 마지막 합(우리 편이 맞음 403)은 37-03
# 합이 끝나면 NDS 는 지하를 90프레임에 걸쳐 밝히고(0x0E 90), 60·60프레임 기다린 뒤 검사가 묻는다
REVEAL_STEP = 6     # 밝기 1 → 15 한 단계에 6프레임
# NDS 의 60·60 은 밝힌 뒤 너무 오래 서 있어, 밝히기는 두고 기다리기만 줄였다(밝히기 시작 → 물음 약 2.5초)
REVEAL_HOLD = (20, 20)
SPIN_SPEED, WALK_SPEED = 4, 1
# NDS 는 지하에 들어오면 곡을 멈춘다(0x147 0). 무음 곡 4A(dq4sound-game.args 의 --silent-song)를 틀어 두면 그 곡에
# 붙인 칼 효과음 샘플이 미리 올라가(--sfx-carry 40=4A), 칼 소리를 부를 때 샘플을 받느라 늦지 않는다
SILENT_SONG = 0x4A
HERO_HIT, MASTER_HIT, LANDED = (0x40, 0x01), (0x40, 0x02), (0x37, 0x03)
SPAR = [(HERO_HIT, 0, 30), (MASTER_HIT, 1, 60), (HERO_HIT, 0, 30), (MASTER_HIT, 1, 20), (MASTER_HIT, 1, 60),
        (LANDED, 1, 90)]

say = ch1.say
# 서장 메시지. dq4chapter1.messages 가 1장 메시지와 합친다. dq4chapter1 을 스크립트로 돌리면 이 모듈이 import 하는
# dq4chapter1 은 다른 사본이라, 그쪽 TEXTS 에 넣으면 메시지 문서에 들어가지 않는다
TEXTS = {}
# 대화 번호 T(26D 이상)는 메시지 T + 3C6 을 띄운다. 1장 대화 번호 다음부터 쓴다
TALK_BASE = ch1.TALK_BASE + len(ch1._talks)
_talks = []


def talk(parts):
    t = TALK_BASE + len(_talks)
    _talks.append(parts)
    TEXTS[t + 0x3C6] = parts
    return t


# 지하: 검사의 물음과 대답. 대화 번호 자리를 메시지로만 쓴다(스크립트 명령 21·30 이 번호로 띄움)
# 검사의 물음은 덧붙인 대화 스크립트(dq5talkwrite, 번호 900~): 물음 → 예·아니요 → 대답 → 수련 끝 깃발.
# 인물 스크립트(01:C800) 안에서 예·아니요 창(BRK 95 32)을 부르면 04:DAD2 의 창 목록 고리에서 돌아오지
# 않았고, 명령 08(이벤트 시작)은 말 걸기가 아니었다(실측). 그래서 주인공이 말을 걸면 대화가 묻는다
T_ASK = 0x900
M_ASK = talk(say('왜 그러느냐? @. 벌써 항복이냐?')) + 0x3C6
M_YES = talk(say('그래. 오늘은 이쯤 해 두자……')) + 0x3C6
M_NO = talk(say('오오! 제법 버티는구나.', '하지만 오늘은 이쯤 해 두자.')) + 0x3C6
M_AFTER = talk(say('내 소임은 어서 너를 제 몫을 하는 전사로 키우는 것이지만 서둘러 봐야 소용없겠지.',
                   '자, 돌아가 볼까. @도 집에서 푹 쉬는 게 좋을 게다.')) + 0x3C6

# 마을 사람(낮). 서장은 해 질 녘이라 NDS 의 대사도 그렇다
T_FARMER = talk(say('어라, @ 아닌가. 슬슬 해가 지겠구먼.', '어디, 나도 집에 가서 밥이나 먹어야겠구먼.'))
T_MAN = talk(say('이야, @. 지친 얼굴이로군. 그래, 검술 수련을……', '힘들겠지만 꺾이지 마. 어쨌든 너는 우리의 희망이니까.',
                 '라고 해도 지금의 너는 무슨 말인지 모르겠지. 신경 쓰지 않아도 돼.'))
T_MASTER = talk(say('푸하아아!! 오오, @. 너도 물 마시러 왔느냐?', '오늘 검술 수련은 좀 거칠었으니 말이다. 와하하하하.',
                    '그런데 신시아와는 여전히 사이가 좋은 모양이구나.', '바로 며칠 전에도 나를 찾아와서는 너를 너무 괴롭히지 말라더구나.',
                    '뭐, 요즘 수련이 좀 지나쳤을지도 모르지만 그만큼 너도 강해졌다는 뜻이다.'))
T_WIZARD = talk(say('오오, 왔구나, @. 오늘은 그대에게 베기라마 주문을 가르쳐 주마.',
                    '라고 하고 싶다만 오늘은 벌써 해가 저물어 가는구나. 수업은 내일 하자꾸나.'))
T_SLEEPER = talk(say('쿨쿨…… 쿨쿨…… 이 마을에는 아무도 못 들어온다!! 음냐음냐……'))
T_MERCHANT = talk(say('어라, 누군가 했더니 @ 씨군요. 아니, 잠깐 방 청소를요.', '하긴 이런 산골 마을에 손님이 올 리도 없고 온다 해도 설마 재워 줄 수야……',
                      '아! 아니, 그, 뭐…… 옛날 버릇이라는 거죠. 아하하하……'))
T_MOTHER = talk(say('어머, 왔니, @. 배고프지? 금방 밥 차려 줄게.'))
T_FATHER = talk(say('오오, 왔느냐, @. 그런데 신시아가 보이지 않는구나.', '아까 너를 부르러 간다고 나갔는데 어디서 엇갈린 게 아닌지 모르겠구나.',
                    '아직 너를 찾고 있다면 가엾으니 네가 이 근처를 찾아보고 오너라.'))
# 문지기는 덧붙인 대화(묻고 예·아니요로 대답). DQ5 묻기 대화 24F~26C 는 DQ5 메시지를 덮어야 해서 쓰지 않는다
T_GATE = 0x904
M_GATE_ASK = talk(say('여기는 마을 입구. 수상한 놈이 들어오지 못하게 지키고 있다.', '그런데 @. 마을 밖으로 나가고 싶으냐?')) + 0x3C6
M_GATE_YES = talk(say('하지만 아직 그때가 아니다. 지금의 너로는 아직 힘이 모자란다.')) + 0x3C6
M_GATE_NO = talk(say('음, 그렇지. 마을을 떠나려면 너는 훨씬 더 강해져야 한단다.')) + 0x3C6

# 그림 번호(dq5sprite.py 시트에서 고름, dq4npcport.PICTURES 와 같은 역할)
SWORDSMAN, SOLDIER, FARMER, MAN, WIZARD, MERCHANT, WOMAN, FATHER = 0x08, 0x06, 0x29, 0x03, 0x1F, 0x40, 0x17, 0x09
# 수련 검사는 스크립트가 있는 1B/00 의 한 벌 엔트리를, 자는 남자는 누운 선원을 복사한다
MASTER_SRC = {"list": "05:B2EE", "index": 2}
MASTER_SCRIPT = "05:B329"
SLEEPER_SRC = {"list": "05:A848", "index": 1}
SLEEPER_SCRIPT = "05:A86E"

MASTER_AT = (3, 0x0E)
MASTER_OUT = [(4, 0x0E), (4, 0x07), (3, 0x07)]      # 아래 방에서 문 틈 (4,0D) 을 지나 위 방으로 나가 사라진다
# (FC x, FC y, 그림, 방향, 대화). 문지기 (0D,17) 은 마을 입구로 가는 하나뿐인 칸이라 서 있으면 밖으로 못 나간다
VILLAGERS = [
    (0x0D, 0x17, SOLDIER, 'up', T_GATE),
    (0x0B, 0x10, FARMER, 'up', T_FARMER),
    (0x0F, 0x09, MAN, 'down', T_MAN),
    (0x0D, 0x04, SWORDSMAN, 'left', T_MASTER),
    (0x13, 0x0D, WIZARD, 'down', T_WIZARD),
    (0x14, 0x14, MERCHANT, 'down', T_MERCHANT),
    (0x02, 0x10, WOMAN, 'down', T_MOTHER),
    (0x05, 0x12, FATHER, 'left', T_FATHER),
]
SLEEPER_AT = (0x13, 0x16)

# 서장 뒤쪽 깃발. 모두 DQ5 롬에서 켜고 끄고 보는 곳이 없는 비트다(sfc/dq5/docs/dq5-flags.md). 앞 바이트 21C5 는 맵을
# 옮길 때 8비트로만 지우고(00:A951), 21E1 은 바이트로 쓰는 곳이 없어 16비트 쓰기에 휩쓸리지 않는다
FROG_MET = (0x36, 0x01)         # 7E:21C6 bit0  개구리의 이야기를 들음
SHINSIA_START = (0x36, 0x02)    # 7E:21C6 bit1  신시아에게 말을 걺 → 모샤스
MORPH = (0x36, 0x04)            # 7E:21C6 bit2  신시아가 개구리로
MORPH_BACK = (0x36, 0x08)       # 7E:21C6 bit3  개구리가 신시아로
SHINSIA_MET = (0x36, 0x10)      # 7E:21C6 bit4  신시아가 집으로 감
DINNER = (0x52, 0x02)           # 7E:21E2 bit1  저녁 대사가 끝남(끝 이벤트가 켬)
SUPPER = (0x52, 0x08)           # 7E:21E2 bit3  아버지에게 대답함 → 식탁에 앉음
speak = ch1.speak
narrate = ch1.narrate
SHINSIA = '신시아'

# 개구리(마을): 말을 걸면 묻고, 대답에 따라 한마디 → 공주 이야기 → FROG_MET
T_FROG = 0x901
M_CALL = talk(say('용사님 용사님……')) + 0x3C6
M_HELP = talk(say('용사님 제발 도와주세요……')) + 0x3C6
M_FROG_ASK = talk(say('아! 놀라지 마세요…… 저는 개구리가 아니랍니다.', '아! 지금 아무리 봐도 개구리라고 생각하셨죠?')) + 0x3C6
M_FROG_YES = talk(say('당신은 정직한 분이군요. 그 정직함을 믿고 부탁이 있어요.')) + 0x3C6
M_FROG_NO = talk(say('당신은 상냥한 분이군요. 그 상냥함을 믿고 부탁이 있어요.')) + 0x3C6
M_FROG_STORY = talk(say('이미 눈치채셨겠지만 실은 저는 어느 나라의 공주였답니다.',
                        '하지만 나쁜 마법사에게 저주를 받아 이런 모습이 되어 버렸지요.',
                        '뭐, 이렇게 된 건 어쩔 수 없고 개구리도 생각만큼 나쁘진 않아요.',
                        '그래서 날마다 태평하게 지내고 있었는데……', '곤란한 일이 생겼어요. 그건…………',
                        '그건………………', '…………………………', '아! 안 돼. 누가 와요!')) + 0x3C6
# 신시아(지하): 말을 걸면 웃음을 참다 개구리로 변한다
T_SHINSIA = 0x902
M_SHINSIA_MEET = talk(speak(SHINSIA, '아, @. 검술 수련 벌써 끝났나 보네.', '응? 무슨 일 있어? 뭐? 커다란 개구리? 무슨 소리야……',
                            '나는 계속 여기 있었는데 개구리 같은 건 못 봤……', '모, 못 봤……',
                            '풉! 아하하하 아하하…… 이제 못 참겠어!!', '네가 본 건 이 개구리지?')) + 0x3C6
M_MORPH = talk(narrate('신시아는 모샤스를 외웠다!!')) + 0x3C6
M_MIMIC = talk(speak(SHINSIA, '태평하게 지내고 있었는데 곤란한 일이 생겼어요. 그건……', '그건…………')) + 0x3C6
M_SORRY = talk(speak(SHINSIA, '……라니, 미안해. 실은 그다음 대사가 떠오르지 않았어.',
                     '좀 더 제대로 뒷이야기 까지 생각하고 할 걸 그랬는데, 너한테 빨리 보여 주고 싶었거든.',
                     '놀랐지! 나 여러 가지로 모습을 바꿀 수 있는 모샤스 주문을 배웠어!')) + 0x3C6
M_BYE = talk(speak(SHINSIA, '그럼 난 갈게!')) + 0x3C6
M_SUPPER = talk(speak(SHINSIA, '아! 맞다! 너희 어머니가 부르셨어. 벌써 저녁이래.', '그럼 @, 내일 봐!')) + 0x3C6
# 저녁(집): 신시아를 만난 뒤 아버지에게 말을 걸면 묻고(대화 903 → SUPPER), 식탁에 앉아 저녁을 먹는다(끝 이벤트)
T_FATHER_SUPPER = 0x903
M_FATHER_ASK = talk(say('음, @. 왔느냐? 그래, 신시아와는 만났느냐?')) + 0x3C6
M_FATHER_YES = talk(say('그러냐. 그거 잘됐구나.')) + 0x3C6
M_FATHER_NO = talk(say('그러냐…… 포기하고 돌아갔는지도 모르겠구나. 뭐, 괜찮겠지.')) + 0x3C6
M_SUPPER_LINES = [talk(say(*pages)) + 0x3C6 for pages in (
    ('좋아! 여보, 슬슬 밥 먹읍시다! 배가 등에 붙었구먼.',),
    ('네네. 지금 차려요.',),
    ('자, @. 너도 자리에 앉으렴.',),
    ('흠! 이거 맛있구먼! 우물우물 우물우물……',
     '그런데 말이다, @. 너는 아직 어려서 이 마을밖에 모르겠지만……',
     '바깥 세상은 아주 넓단다. 그리고 온갖 사람들이 살고 있지.',
     '너도 언젠가 자라서 이 마을을 떠날 때가 올지도 모르겠구나.',
     '그때 바깥 세상에서 너는 어떤 사람들과 만나게 될까……'),
    ('당신도 참, 무슨 말을 하나 했더니! 밥 먹다가 쓸쓸해지는 얘기는 그만해요.',
     '이 아이는 계속 우리와 함께 사는 거예요. 무슨 일이 있어도요!'),
    ('오오, 그랬지! 이거 내가 그만…… 와하하하하!',))]
M_STORY_BEGINS = talk(narrate('이야기는 이렇게 시작된다……')) + 0x3C6
# 1장·서장이 받은 대화 번호의 끝. 옮긴 일본어 메시지는 메시지 TALK_END + 3C6 부터(dq4npcport.FIRST_MESSAGE)
TALK_END = TALK_BASE + len(_talks)
if TALK_END > 0x900:
    raise ValueError(f'1장·서장 대화 번호가 덧붙인 대화 자리(900~)를 넘음: {TALK_END:X}')

FROG, GIRL = 0x50, 0x0E         # 개구리 그림이 DQ5 에 없어 슬라임, 신시아는 DQ5 소녀(임시)
# NDS mlout1: 개구리는 맵에 서 있지 않고 다리 남쪽 연못에 숨어 있다가, 주인공이 다리 가운데에 오면 떠올라 다리로
# 뛰어오르고(주인공 뒤 동쪽), 이야기를 마치면 동쪽으로 다리를 벗어나 지하 오두막 계단으로 들어간다
FROG_AT = (0x13, 0x07)          # 연못
FROG_HIDDEN_X = 0x3F             # 맵(FC 폭 24) 밖. 인물 표 X 는 2배라 7E
FROG_JUMP = [((0x13, 0x06), 6), ((0x13, 0x05), 10), ((0x13, 0x04), 4)]   # (FC 칸, 그림을 띄울 점)
FROG_OUT = [(0x14, 0x04), (0x15, 0x04), (0x15, 0x03), (0x15, 0x02)]      # 다리 동쪽 → 오두막 계단
# 주인공 자리(인물 표 3020·3080, FC 칸 (x, y) 는 (2x, 2y+1))의 사각형. 지하에서 나오면 (42,5), 다리 줄은 y 9, 다리는 x 34~35
VOICE_HUT = (40, 7, 44, 8)      # 오두막을 나섬: 「용사님 용사님……」
VOICE_BRIDGE = (37, 8, 38, 10)  # 다리 동쪽 끝: 같은 말
FROG_CALL = (34, 8, 35, 10)     # 다리 위: 「용사님 제발 도와주세요……」 → 개구리가 나타남
SPLASH = JUMP = (0x45, 0x00)    # NDS EVE_JUMP 를 옮긴 빈 효과음(dq4sound-game.args). 첨벙 EVE_3_08 도 이 소리로
STAIRS = (0x34, 0x02)           # 계단(NDS 階段 으로 바뀐 갈래)
SHINSIA_AT = (3, 0x0E)          # 수련하던 자리
SHINSIA_OUT = [(4, 0x0E), (4, 0x07), (3, 0x07)]
# 신시아가 나가는 길 가운데 주인공이 말을 거는 칸에 닿는 앞 두 구간(인물 표 셀). 오른쪽 칸 (8,29) 에서 말을 걸면 주인공이
# 문틈 아래 그 길 위에 있어, 1C 로 지나가는 신시아와 겹쳐 보였다. 주인공이 한 칸 내려 비킨 뒤 위(신시아 쪽)를 본다
SHINSIA_WAY_CELLS = [(SHINSIA_AT[0] * 2, SHINSIA_AT[1] * 2)] + [(x * 2, y * 2) for x, y in SHINSIA_OUT[:2]]
FROG_SRC, FROG_SCRIPT = {"list": "05:B2EE", "index": 4}, "05:B352"
SHINSIA_SRC, SHINSIA_SCRIPT = {"list": "05:B2EE", "index": 7}, "05:B386"
FORM_SRC, FORM_SCRIPT = {"list": "05:B2EE", "index": 8}, "05:B3B3"
FATHER_SRC, FATHER_SCRIPT = {"list": "05:B466", "index": 0}, "05:B46D"
MOTHER_SRC, MOTHER_SCRIPT = {"list": "05:B48B", "index": 3}, "05:B4A7"
# 집의 식탁 (4,11) 과 의자 (3,11)·(5,11). 아버지는 오른쪽, 어머니는 왼쪽 의자, 주인공은 식탁 아래쪽 (4,12) 에서 위를 봄.
# 주인공이 식탁 위쪽에 서면 카메라가 주인공을 가운데에 두어 식탁·부모가 아래 메시지 창에 가렸다
FATHER_SEAT, MOTHER_PATH = (5, 0x11), [(3, 0x10), (3, 0x11)]
# 주인공은 아버지의 오른쪽·왼쪽·위(의자 칸) 어디서든 말을 걸 수 있다. 대답하면 주인공이 그 자리에서 식탁 아래쪽
# (4,12) 셀 (8,37) 까지 걷고(hero_routes), 아버지·어머니도 같이 의자로 간다. 인물은 2×2 셀을 차지하므로 길이 엇갈리면
# 1C(주인공 통과)로 지나가며 겹쳐 보인다. 그래서 선 자리마다 길과 기다림을 나눈다.
#   위(의자 칸): 아버지가 올라올 칸이라 먼저 오른쪽 줄(X 12)로 비킨 뒤 내려가고, 아버지는 주인공이 비킨 뒤에 걷는다.
#   오른쪽: 아래 줄(Y 37)로 왼쪽에 가면 아버지가 서 있던 칸 바로 아래를 지나므로, 아버지가 한 칸(8프레임) 오른 뒤
#   한 걸음(8프레임)의 여유를 두고 왼쪽으로 꺾게, Y 37 에 닿기까지가 두 걸음이 안 되면 그만큼 C2 로 기다린다.
#   왼쪽: X 8 그대로 내려간다(아버지·어머니와 2셀 떨어짐).
HERO_AT = (8, 37)
HERO_LEGS = (('y', HERO_AT[1]), ('x', HERO_AT[0]))
FATHER_CELL = next((x * 2, y * 2) for x, y, _, _, t in VILLAGERS if t == T_FATHER)   # 인물 표 셀은 FC 칸 × 2
FATHER_SEAT_CELL = (FATHER_SEAT[0] * 2, FATHER_SEAT[1] * 2)
SIDE_X = FATHER_CELL[0] + 2      # 아버지 오른쪽 줄
TURN_LEAD = 2                    # 오른쪽 줄에서 왼쪽으로 꺾기 전까지 둘 걸음(8프레임) 수
SUPPER_ROUTES = ([((FATHER_CELL[0] - 1, 0, SIDE_X - 1, FATHER_CELL[1] - 1), b'', (('x', SIDE_X),) + HERO_LEGS)] +
                 [((SIDE_X, y, 0x7F, 0x7F if y == HERO_AT[1] else y), bytes((0xC2,)) * (TURN_LEAD - (HERO_AT[1] - y)),
                   HERO_LEGS) for y in range(HERO_AT[1], HERO_AT[1] - TURN_LEAD, -1)] +
                 [(None, b'', HERO_LEGS)])
NPC_SLOT0 = 8                    # 인물 목록의 첫 인물 슬롯(00:E1A9 가 $81 을 8 로 둠, dq5-map-format 「인물 슬롯」)
HERO_AT_TABLE = 0x80             # 명령 C1 의 방향: 위
# hero_goto 가 걸음 이벤트를 만드는 자리. 7E:1BBE~ 의 DQ5 가 쓰지 않는 칸 가운데 1BC0~1BCF(조사·서장·1장)와
# 1BE0~1BE7(이름 입력) 뒤, 1BFF~(DQ5 바위 자리) 앞의 빈 곳. 앞붙임 8 + 걸음 세 구간 6 + 점프 4 바이트
ROUTE_BUF, ROUTE_MAX = 0x7E1BE8, 20
# 이벤트 걸음 방향(dq5-event-format 의 00~0F d n): (X 를 늘림, 줄임), (Y 를 늘림, 줄임)
STEP_X, STEP_Y = (0x01, 0x02), (0x04, 0x08)
# 1장 왕좌의 방 첫 자리(dq4chapter1.START)와 같은 칸
CHAPTER1_AT = (0x36, 0x01, 32, 42)


def _event_start(script):
    """인물 스크립트(명령 37)에서 이벤트 스크립트를 건다: $19B3~$19B5 = 주소, $19AE |= 80(dq5-event-format 「시작」).
    이벤트 스크립트는 메인 문맥(00:BED2)에서 돈다."""
    return (box.ENTER + bytes((0xA9, script & 0xFF, 0x8D, 0xB3, 0x19, 0xA9, script >> 8 & 0xFF, 0x8D, 0xB4, 0x19,
                               0xA9, script >> 16, 0x8D, 0xB5, 0x19,
                               0xAD, 0xAE, 0x19, 0x09, 0x80, 0x8D, 0xAE, 0x19)) + box.LEAVE)


def hero_goto(legs, then, prefix=b''):
    """인물 스크립트(명령 37)에서: 주인공(슬롯 0)을 지금 선 셀에서 legs 차례대로 걷게 하는 이벤트를 ROUTE_BUF 에 만들어
    건다. legs 는 ('x' 또는 'y', 목표 셀)이고, 이벤트는 prefix → 구간마다 그 축으로 목표까지 → C3 then(롬의 이어질
    이벤트)이다. then 이 None 이면 C3 대신 FF 로 끝난다. 축마다 첫 구간만 주인공 자리(7E:3020·3080)에서 걸음 수를
    세고, 같은 축의 다음 구간은 앞 구간의 목표에서 센다. 이벤트 리더(00:BED2)는 LDA [$80] 로 읽어 WRAM 의 스크립트도
    돈다. 이벤트 걸음은 벽을 지나가므로(실측) 길이 벽·인물을 넘지 않게 구간을 고른다. 걸음 수 0 은 255 걸음이 되어
    넣지 않는다."""
    return hero_routes([(None, prefix, legs)], then)


def hero_routes(routes, then):
    """hero_goto 의 갈래판. routes 는 (사각형, prefix, legs[, suffix]) 목록이고, 주인공 셀이 사각형 (x0, y0, x1, y1)(양 끝
    포함) 안에 드는 첫 갈래의 길을 쓴다. suffix 는 그 갈래의 걸음 뒤에 둘 이벤트 바이트다. 마지막 갈래의 사각형은
    None(나머지 모두)이어야 한다. 한 갈래뿐이면 고르는 코드 없이 hero_goto 와 같은 바이트다."""
    if not routes or routes[-1][0] is not None or any(r[0] is None for r in routes[:-1]):
        raise ValueError('hero_routes: 마지막 갈래만 사각형이 None 이어야 한다')
    tail_ops = (0xFF,) if then is None else (0xC3, *then.to_bytes(3, 'little'))
    routes = [(r[0], r[1], r[2], r[3] if len(r) > 3 else b'') for r in routes]
    for _, prefix, legs, suffix in routes:
        if len(prefix) + 2 * len(legs) + len(suffix) + len(tail_ops) > ROUTE_MAX:
            raise ValueError('hero_goto: 길이 ROUTE_BUF 보다 길다')
    buf = ROUTE_BUF.to_bytes(3, 'little')
    put_a = bytes((0x9F, *buf, 0xE8))                   # STA buf,X / INX

    def put(value):
        return bytes((0xA9, value)) + put_a

    def axis(table, goal, steps):
        plus, minus = steps
        neg = bytes((0x49, 0xFF, 0x1A, 0x48, 0xA9, plus)) + put_a + bytes((0x68,)) + put_a      # 목표가 큼: -차
        pos = bytes((0x48, 0xA9, minus)) + put_a + bytes((0x68,)) + put_a
        pos += bytes((0x80, len(neg)))
        return (bytes((0xAF, table & 0xFF, table >> 8, 0x7E, 0x29, 0x7F, 0x38, 0xE9, goal,   # 주인공 - 목표
                       0xF0, 2 + len(pos) + len(neg), 0x90, len(pos))) + pos + neg)

    def walk(prefix, legs, suffix):
        body, known = bytearray(), {}
        for name, goal in legs:
            table, steps = {'x': (0x3020, STEP_X), 'y': (0x3080, STEP_Y)}[name]
            if name in known:
                if goal != known[name]:
                    body += put(steps[0] if goal > known[name] else steps[1]) + put(abs(goal - known[name]))
            else:
                body += axis(table, goal, steps)
            known[name] = goal
        return b''.join(put(b) for b in prefix) + bytes(body) + b''.join(put(b) for b in suffix)

    def within(rect, miss):
        """주인공 셀이 rect 밖이면 miss 바이트 뒤로 건너뛴다(BRL). CMP 뒤 BCS/BCC 로 BRL 을 넘는다."""
        x0, y0, x1, y1 = rect
        out = bytearray()
        for table, lo, hi in ((0x3020, x0, x1), (0x3080, y0, y1)):
            out += bytes((0xAF, table & 0xFF, table >> 8, 0x7E, 0x29, 0x7F,
                          0xC9, lo, 0xB0, 0x03, 0x82, 0, 0,                  # CMP lo / BCS +3 / BRL 다음 갈래
                          0xC9, hi + 1, 0x90, 0x03, 0x82, 0, 0))             # CMP hi+1 / BCC +3 / BRL 다음 갈래
        # BRL 의 거리는 그 명령 뒤에서 센다. 자리를 채운 뒤 거리를 넣는다
        brls = [k for k in range(len(out)) if out[k] == 0x82 and out[k - 2] in (0xB0, 0x90) and out[k - 1] == 0x03]
        for k in brls:
            dist = len(out) - (k + 3) + miss
            out[k + 1:k + 3] = dist.to_bytes(2, 'little')
        return bytes(out)

    if len(routes) == 1:
        body = walk(*routes[0][1:])
    else:
        # 뒤 갈래부터 붙인다: 앞 갈래는 「사각형 판정 · 길 · BRL 끝」, 판정에 지면 다음 갈래로
        body = walk(*routes[-1][1:])
        for rect, *way in reversed(routes[:-1]):
            path = walk(*way)
            path += bytes((0x82, *len(body).to_bytes(2, 'little')))         # BRL 끝(뒤 갈래들을 넘음)
            body = within(rect, len(path)) + path + body
    body = bytes((0xE2, 0x30, 0xA2, 0x00)) + body + b''.join(put(b) for b in tail_ops)
    start = bytes((0xA9, buf[0], 0x8D, 0xB3, 0x19, 0xA9, buf[1], 0x8D, 0xB4, 0x19, 0xA9, buf[2], 0x8D, 0xB5, 0x19,
                   0xAD, 0xAE, 0x19, 0x09, 0x80, 0x8D, 0xAE, 0x19))
    return box.ENTER + body + start + box.LEAVE


def pick_route(routes, start):
    """hero_routes 가 주인공이 start 셀에 있을 때 고를 (prefix, legs, suffix)."""
    for rect, prefix, legs, *suffix in routes:
        if rect is None or (rect[0] <= start[0] <= rect[2] and rect[1] <= start[1] <= rect[3]):
            return prefix, legs, (suffix or [b''])[0]
    raise ValueError(start)


def walker_box(cells):
    """인물이 cells(인물 표 셀) 사이를 곧게 걸을 때 차지하는 점 사각형 [x0, x1) × [y0, y1). 인물은 16×16 점(2×2 셀)."""
    xs, ys = [x for x, _ in cells], [y for _, y in cells]
    return min(xs) * 8, min(ys) * 8, max(xs) * 8 + 16, max(ys) * 8 + 16


def hero_cells_in(box):
    """주인공이 서면 그 16×16 점이 box 와 겹치는 셀 사각형 (x0, y0, x1, y1)(양 끝 포함)."""
    x0, y0, x1, y1 = box
    return (x0 - 16) // 8 + 1, (y0 - 16) // 8 + 1, (x1 - 1) // 8, (y1 - 1) // 8


def step_aside(box, legs, suffix=b''):
    """걷는 인물의 길(점 사각형 box)에 주인공이 서 있으면 legs 로 비키게 하는 hero_routes 갈래. 길 밖이면 걷지 않는다."""
    return [(hero_cells_in(box), b'', legs, suffix), (None, b'', ())]


def _hero_flag(rect, flag):
    """인물 명령 37 이 부르는 루틴: 주인공 셀이 rect (x0, y0, x1, y1)(양 끝 포함) 안이면 깃발 flag((7E:2190 + i, 마스크))를
    켜고, 아니면 끈다. 인물 스크립트가 명령 06 으로 주인공이 선 자리에 따라 길을 고를 때 쓴다."""
    addr = (0x7E2190 + flag[0]).to_bytes(3, 'little')
    on = bytes((0xAF, *addr, 0x09, flag[1], 0x8F, *addr))
    body = b''
    for table, lo, hi in ((0x3080, rect[1], rect[3]), (0x3020, rect[0], rect[2])):
        tail = len(body) + len(on)
        body = bytes((0xAF, table & 0xFF, table >> 8, 0x7E, 0x29, 0x7F,
                      0xC9, lo, 0x90, 4 + tail, 0xC9, hi + 1, 0xB0, tail)) + body   # 작으면·크면 끝으로
    off = bytes((0xAF, *addr, 0x29, ~flag[1] & 0xFF, 0x8F, *addr))
    return box.ENTER + off + body + on + box.LEAVE


def _hero_clear(x0, y0, x1, y1):
    """인물 명령 05 가 부르는 루틴: 주인공(슬롯 0)이 차지한 16×16 점(셀 자리 × 8 + 걸음 도중의 점 7E:3000·3060 위 3비트)이
    점 사각형 [x0, x1) × [y0, y1) 과 겹치지 않으면 A = 0, 겹치면 1(다음 차례에 다시)."""
    def pixel(sub, cell):           # 스택에 셀 × 8 + 점을 남긴다(16비트)
        return bytes((0xAF, sub & 0xFF, sub >> 8, 0x7E, 0x29, 0xE0, 0x00, 0x4A, 0x4A, 0x4A, 0x4A, 0x4A, 0x48,
                      0xAF, cell & 0xFF, cell >> 8, 0x7E, 0x29, 0x7F, 0x00, 0x0A, 0x0A, 0x0A, 0x18, 0x63, 0x01, 0x83, 0x01))
    blocked = bytes((0x68, 0x68, 0xA9, 0x01, 0x00, 0x28, 0x6B))         # PLA ×2 / LDA #1 / PLP / RTL
    clear = bytes((0x68, 0x68, 0xA9, 0x00, 0x00, 0x28, 0x6B))
    # 스택: 1,S = Y 점, 3,S = X 점. 축마다 점 ≥ 끝이거나 점 + 16 ≤ 시작이면 겹치지 않는다
    tests = b''
    for at, lo, hi in ((1, y0, y1), (3, x0, x1)):          # 뒤 시험부터 붙여 clear 까지의 거리를 센다
        rest = len(tests) + len(blocked)
        tail = bytes((0x18, 0x69, 0x10, 0x00, 0xC9, *(lo + 1).to_bytes(2, 'little'), 0x90, rest))   # +16 / CMP / BCC
        tests = bytes((0xA3, at, 0xC9, *hi.to_bytes(2, 'little'), 0xB0, len(tail) + rest)) + tail + tests  # LDA n,S / CMP / BCS
    return bytes((0x08, 0xC2, 0x30)) + pixel(0x3000, 0x3020) + pixel(0x3060, 0x3080) + tests + blocked + clear


def _all_at(checks):
    """인물 명령 05 가 부르는 루틴: checks 의 (슬롯, X 셀, Y 셀, 방향 31E0 또는 None)이 모두 그 자리에 멈춰 섰고(걸음 도중의
    점 3000·3060 이 0) 이벤트가 돌지 않으면($19AE bit7 이 꺼짐) A = 0, 아니면 1."""
    fail = bytes((0xC2, 0x30, 0xA9, 0x01, 0x00, 0x28, 0x6B))
    ok = bytes((0xC2, 0x30, 0xA9, 0x00, 0x00, 0x28, 0x6B))
    parts = []
    for slot, x, y, face in checks:
        for table, mask, want in ((0x3020, 0x7F, x), (0x3080, 0x7F, y), (0x3000, 0xFF, 0), (0x3060, 0xFF, 0),
                                  *(((0x31E0, 0xFF, face),) if face is not None else ())):
            parts.append(bytes((0xAF, (table + slot) & 0xFF, (table + slot) >> 8, 0x7E, 0x29, mask, 0xC9, want)))
    parts.append(bytes((0xAF, 0xAE, 0x19, 0x7E, 0x29, 0x80, 0xC9, 0x00)))
    body = b''
    for part in reversed(parts):
        body = part + bytes((0xD0, len(body) + len(ok))) + body           # BNE 실패
    return bytes((0x08, 0xE2, 0x30)) + body + ok + fail


def route(start, legs, prefix=b''):
    """hero_goto 가 주인공이 start 셀 (x, y) 에 있을 때 만들 이벤트(C3 앞까지)."""
    out, here = bytearray(prefix), {'x': start[0], 'y': start[1]}
    for name, goal in legs:
        plus, minus = STEP_X if name == 'x' else STEP_Y
        if here[name] != goal:
            out += bytes((plus if here[name] < goal else minus, abs(here[name] - goal)))
        here[name] = goal
    return bytes(out)


FADE_SPEED = 0x40   # 곡 줄이기(소리 명령 04)의 X. dq4overture 가 서곡을 줄일 때와 같은 값


def _darken():
    """맵 곡을 줄이며(24:FEC7, 명령 04, A = 지금 맵 곡 $194B) 맵을 어둡게 한 뒤 주화면을 BG3(창)만으로: 검은 화면에
    메시지 창만 남는다(dq4chapterbox 의 맵 훅과 같은 값). 1장 상자·서술 동안 곡이 없게 한다."""
    return (box.ENTER + bytes((0xAD, 0x4B, 0x19, 0x29, 0x7F, 0xA2, FADE_SPEED, 0x00, 0x22, 0xC7, 0xFE, 0x24)) +
            box.fade(14, 0, 2) +
            bytes((0xA9, 0x04, 0x8D, 0x33, 0x07, 0x8D, 0x2C, 0x21, 0x8D, 0x2D, 0x21)) + box.wait(1) +
            bytes((0xA9, 0x0F, 0x8D, 0x1D, 0x00)) + box.LEAVE)


def _rel(code, target):
    """code 끝에 둘 2바이트 분기의 거리(code 다음 바이트 기준)."""
    d = target - (len(code) + 2)
    if not -128 <= d <= 127:
        raise ValueError(f'분기가 멂: {d}')
    return d & 0xFF


def _effect(se, branch):
    """BRK 16 se branch 와 같은 일: 효과음을 대기열에 넣고(24:FEAC, A = 효과음, X = 갈래) 보내질 때까지 기다린다(24:FE44).
    BRK 를 쓰지 않는다. BRK 핸들러는 DB 를 부른 코드의 뱅크(5E)로 두는데, 24:FE44 는 대기열 $1D91·$1D93 을 DB 기준으로
    읽는다. 5E:0000~7FFF 는 WRAM 거울이 아니다. MesenCE 는 열린 버스라 기다림이 그냥 넘어갔고, snes9x 는 롬 거울이라
    끝나지 않았다. 레지스터·폭·DB·D 를 BRK 처럼 지킨다."""
    return bytes((0x08, 0x8B, 0x0B, 0xC2, 0x30, 0x48, 0xDA, 0x5A,        # PHP / PHB / PHD / REP #$30 / PHA / PHX / PHY
                  0xF4, 0x00, 0x00, 0xAB, 0xAB, 0xF4, 0x00, 0x00, 0x2B,  # PEA $0000 / PLB / PLB / PEA $0000 / PLD
                  0xE2, 0x20, 0xA9, se, 0xA2, branch, 0x00,              # SEP #$20 / LDA #효과음 / LDX #갈래
                  0x22, 0xAC, 0xFE, 0x24, 0x22, 0x44, 0xFE, 0x24,        # JSL 24:FEAC / JSL 24:FE44
                  0xC2, 0x30, 0x7A, 0xFA, 0x68, 0x2B, 0xAB, 0x28))       # REP #$30 / PLY / PLX / PLA / PLD / PLB / PLP


def _fx_frames(addr):
    """서브루틴(JSR, M 8·X 16, DB 00). X = 프레임 목록(뱅크 fx.BANK), Y = 올릴 프레임 수. 프레임마다 화면을 잠깐 끄고
    그 레코드의 타일 행과 팔레트(BG3 팔레트 1 = CGRAM 4~7, 색 버퍼에도)를 올린 뒤 한 프레임 기다린다."""
    bank = fx.BANK >> 16
    long_x = lambda op, off: bytes((op, off & 0xFF, off >> 8 & 0xFF, bank))  # noqa: E731
    body = (bytes((0x5A, 0xDA, 0xC2, 0x20)) + long_x(0xBF, 0) + bytes((0xAA, 0xE2, 0x20,          # PHY / PHX / LDA rec
            0xA9, 0x80, 0x8D, 0x00, 0x21, 0x8D, 0x15, 0x21,                                    # 화면 끔 / $2115 = 80
            0xA9, 0x01, 0x8D, 0x70, 0x43, 0xA9, 0x18, 0x8D, 0x71, 0x43, 0xA9, bank, 0x8D, 0x74, 0x43,
            0xC2, 0x20)) + long_x(0xBF, 0) + bytes((0x8D, 0x16, 0x21)) +                        # VRAM 자리
            long_x(0xBF, 2) + bytes((0x8D, 0x72, 0x43)) + long_x(0xBF, 4) + bytes((0x8D, 0x75, 0x43,
            0xE2, 0x20, 0xA9, 0x80, 0x8D, 0x0B, 0x42,                                          # 타일 DMA
            0xA9, 0x04, 0x8D, 0x21, 0x21, 0x9C, 0x70, 0x43, 0xA9, 0x22, 0x8D, 0x71, 0x43,
            0xC2, 0x20)) + long_x(0xBF, 6) + bytes((0x8D, 0x72, 0x43, 0xA9, 0x08, 0x00, 0x8D, 0x75, 0x43,
            0xE2, 0x20, 0xA9, 0x80, 0x8D, 0x0B, 0x42,                                          # 팔레트 DMA
            0xC2, 0x20)) + long_x(0xBF, 6) + bytes((0xAA,)) +                                  # 색 버퍼에도
            b''.join(long_x(0xBF, 2 * i) + bytes((0x8F, *(box.CGRAM_BUFFER + 8 + 2 * i).to_bytes(3, 'little')))
                     for i in range(4)) +
            bytes((0xE2, 0x20, 0xAD, 0x1D, 0x00, 0x8D, 0x00, 0x21)) + box.wait(1) +            # 화면 밝기 되돌림
            bytes((0xFA, 0xE8, 0xE8, 0x7A, 0x88)))                                             # PLX / INX ×2 / PLY / DEY
    return body + bytes((0xF0, 3, 0x4C, *(addr & 0xFFFF).to_bytes(2, 'little'), 0x60))      # BEQ / JMP 처음 / RTS


def _fx_map(entry, step):
    """BG3 타일맵 버퍼의 효과 자리(fx.COL·ROW, COLS x ROWS)를 entry 부터 칸마다 step 씩 늘린 값으로. M 8·X 16."""
    out = bytearray((0xC2, 0x20, 0xA9, *entry.to_bytes(2, 'little')))
    for r in range(fx.ROWS):
        row = bytearray((0xA2, *(((fx.ROW + r) * 32 + fx.COL) * 2).to_bytes(2, 'little'), 0xA0, fx.COLS, 0x00))
        loop = bytes((0x9F, *(box.MAP_BUFFER & 0xFFFF).to_bytes(2, 'little'), box.MAP_BUFFER >> 16)) + \
            (bytes((0x1A,)) if step else b'') + bytes((0xE8, 0xE8, 0x88))
        out += row + loop + bytes((0xD0, _rel(loop, 0)))
    out += bytes((0xE2, 0x20))
    return bytes(out)


def _spar(at):
    """장 제목 상자 뒤 검은 화면(주화면 BG3 만)에서 칼 여섯 합. 합마다 효과음(_effect)을 내고, 칼 효과 자료
    (dq4sparfx, 뱅크 fx.BANK)가 있으면 그 효과 프레임을 BG3 의 메시지 창 캔버스 타일에 올린다. 자료가 없으면 효과음과
    기다리기만. 끝에 타일맵·캔버스·팔레트 1 을 되돌린다."""
    me = at.get('spar', CODE_AT)
    blank2 = at.get('blank2', 0)
    plain = bytearray()
    for (se, branch), _, gap in SPAR:
        plain += _effect(se, branch) + box.wait(gap)
    head = box.ENTER + bytes((0xAF, *fx.BANK.to_bytes(3, 'little'), 0xC9, fx.MAGIC[0]))       # LDA 표시 / CMP
    save = bytes((0xC2, 0x20)) + b''.join(bytes((0xAF, *(box.CGRAM_BUFFER + 8 + 2 * i).to_bytes(3, 'little'), 0x48))
                                          for i in range(4)) + bytes((0xE2, 0x20))
    blank_out = bytes((0xA9, 0x80, 0x8D, 0x00, 0x21))
    blank_in = bytes((0xAD, 0x1D, 0x00, 0x8D, 0x00, 0x21))
    first = box.CANVAS
    setup = (save + _fx_map(0x2000 | 1 << 10 | first, True) + blank_out +
             box.dma_vram(box.BG3_MAP, box.MAP_BUFFER, 0x800) + blank_in)
    teardown = (_fx_map(box.BLANK, False) + blank_out + box.dma_vram(box.BG3_MAP, box.MAP_BUFFER, 0x800) +
                box.fill_vram(box.BG3_CHR + first * 8, blank2, fx.ROWS * fx.COLS * 8) + bytes((0xC2, 0x20)) +
                b''.join(bytes((0x68, 0x8F, *(box.CGRAM_BUFFER + 8 + 2 * i).to_bytes(3, 'little')))
                         for i in reversed(range(4))) + bytes((0xE2, 0x20)) +
                box.dma_cgram(4, box.CGRAM_BUFFER + 8, 8) + blank_in)
    # 자리: head, BNE plain, JMP fx, plain, JMP end, fx: setup, 합들, teardown, end: LEAVE, frames 서브루틴
    fx_at = len(head) + 2 + 3 + len(plain) + 3
    def strikes(sub):
        out = bytearray()
        for (se, branch), effect, gap in SPAR:
            shown = min(fx.FRAMES, gap)
            out += _effect(se, branch) + bytes((0xC2, 0x20,
                          0xAF, *(fx.BANK + 4 + 2 * effect).to_bytes(3, 'little'), 0xAA, 0xE2, 0x20,   # X = 목록
                          0xA0, shown, 0x00, 0x20, *(sub & 0xFFFF).to_bytes(2, 'little')))             # LDY / JSR
            if gap > shown:
                out += box.wait(gap - shown)
        return bytes(out)
    end_at = fx_at + len(setup) + len(strikes(0)) + len(teardown)
    sub_at = end_at + len(box.LEAVE)
    fixed = strikes(me + sub_at)
    code = (head + bytes((0xD0, 3, 0x4C, *((me + fx_at) & 0xFFFF).to_bytes(2, 'little'))) + bytes(plain) +
            bytes((0x4C, *((me + end_at) & 0xFFFF).to_bytes(2, 'little'))) +
            setup + fixed + teardown + box.LEAVE + _fx_frames(me + sub_at))
    return code


def _skip_song():
    """맵을 불러올 때 곡을 바꾸지 않게(7E:21A5 bit6). 1장 상자·서술 동안 곡이 없게, 새 게임 시작과 같은 값."""
    addr, bit = box.SKIP_SONG
    return (box.ENTER + bytes((0xAF, *addr.to_bytes(3, 'little'), 0x09, bit, 0x8F, *addr.to_bytes(3, 'little'))) +
            box.LEAVE)


TALKER = 0x7E1BC4   # 말을 걸 인물 슬롯. 7E:1BBE~ 79바이트는 DQ5 가 쓰지 않는 자리(dq4josa 가 1BC0 을 씀)
TALK_TO = 0x06AF1C  # 06:AF1C: JSR $AF20 / RTL. A = 인물 슬롯으로 필드 「대화」(05:D596)와 같은 대화를 돌린다


def _talk_here(event):
    """인물 스크립트(명령 37)에서: 이 인물의 슬롯($90, 01:C800 의 LDY $90)을 TALKER 에 적고 대화 이벤트를 건다."""
    return (box.ENTER + bytes((0xA5, 0x90, 0x8F, *TALKER.to_bytes(3, 'little'))) +
            _event_start(event)[len(box.ENTER):])


def _talk_slot():
    """이벤트 명령 A0(메인 문맥)에서: TALKER 의 인물과 대화. 06:AF20 은 끝에 그 인물의 자세(7E:3240·3260,X)를
    $195F·$1960 으로 되돌리므로 지금 값을 넣어 둔다(필드 「대화」 는 인물을 주인공 쪽으로 돌리기 전에 넣음)."""
    return (box.ENTER + bytes((0xAF, *TALKER.to_bytes(3, 'little'), 0xC2, 0x20, 0x29, 0xFF, 0x00, 0xAA, 0xE2, 0x20,
                               0xBF, 0x40, 0x32, 0x7E, 0x8D, 0x5F, 0x19, 0xBF, 0x60, 0x32, 0x7E, 0x8D, 0x60, 0x19,
                               0xAF, *TALKER.to_bytes(3, 'little'), 0x22, *TALK_TO.to_bytes(3, 'little'))) + box.LEAVE)


def _inside(x0, y0, x1, y1):
    """인물 명령 05 가 부르는 루틴: 주인공(슬롯 0) X·Y 가 사각형 안이면 A = 0, 아니면 1(다음 프레임에 다시)."""
    far = bytes((0xC2, 0x30, 0xA9, 0x01, 0x00, 0x28, 0x6B))      # REP / LDA #1 / PLP / RTL
    near = bytes((0xC2, 0x30, 0xA9, 0x00, 0x00, 0x28, 0x6B))
    body = b''
    for table, lo, hi in ((0x3080, y0, y1), (0x3020, x0, x1)):
        tail = len(body) + len(near)
        body = bytes((0xAF, table & 0xFF, table >> 8, 0x7E, 0x29, 0x7F,       # LDA 주인공 / AND #$7F
                      0xC9, lo, 0x90, 4 + tail, 0xC9, hi + 1, 0xB0, tail)) + body   # 작으면·크면 멂
    return bytes((0x08, 0xE2, 0x30)) + body + near + far


def _reveal_hold():
    """지하 밝히기와 그 뒤 기다리기를 한 루틴으로. 인물 스크립트는 명령마다 다음 차례(이동 간격 1 이면 8프레임)를
    기다리므로 37 을 나누면 기다리기마다 그만큼 늘어난다. 맵 곡은 SPC 로 보내는 동안 기다리지 않고 밝히기 시작한다
    (NDS 는 지하에 곡이 없어 밝히기가 곡을 기다리지 않는다)."""
    code = box.reveal_code(REVEAL_STEP, song_wait=False)
    return code[:-len(box.LEAVE)] + b''.join(box.wait(f) for f in REVEAL_HOLD) + box.LEAVE


def _hero_face(facing):
    """주인공(슬롯 0)을 facing(31E0 꼴: 88 위, 11 오른쪽, 44 아래, 22 왼쪽)으로 돌린다. 고정하지 않은 인물의 그림은
    31E0 위 니블을 따르므로 자세(3240·3260)만 바꾸면 그대로였다."""
    return box.ENTER + bytes((0xA9, facing, 0x8F, 0xE0, 0x31, 0x7E, 0x29, 0x0F,
                              0x8F, 0x40, 0x32, 0x7E, 0x8F, 0x60, 0x32, 0x7E)) + box.LEAVE


def _face_hero():
    """인물 스크립트(명령 37)에서: 이 인물($90 슬롯)을 주인공(슬롯 0) 쪽으로 돌린다. X·Y 차가 큰 축(같으면 가로)을 본다.
    DQ5 의 「대화」 는 말을 걸 때만 인물을 돌리므로, 연출 중에 돈 인물은 이것으로 되돌린다."""
    def diff(table):        # 스택 1,S 에 주인공 - 인물(0~7F 칸) 차를 남긴다
        return bytes((0xBF, table & 0xFF, table >> 8, 0x7E, 0x29, 0x7F, 0x48,      # LDA 인물,X / AND #$7F / PHA
                      0xAF, table & 0xFF, table >> 8, 0x7E, 0x29, 0x7F,             # LDA 주인공 / AND #$7F
                      0x38, 0xE3, 0x01, 0x83, 0x01))                               # SEC / SBC 1,S / STA 1,S
    absolute = bytes((0x10, 0x03, 0x49, 0xFF, 0x1A))                              # BPL +3 / EOR #$FF / INC
    store = bytes((0x9F, 0xE0, 0x31, 0x7E, 0x29, 0x0F, 0x9F, 0x40, 0x32, 0x7E, 0x9F, 0x60, 0x32, 0x7E,
                   0x68, 0x68, 0x68))                                              # 31E0·3240·3260,X / PLA ×3
    pick = lambda plus, minus: bytes((0x30, 0x04, 0xA9, plus, 0x80, 0x02, 0xA9, minus))  # noqa: E731
    vertical = bytes((0xA3, 0x02)) + pick(0x44, 0x88)                              # LDA 2,S(dy)
    horizontal = bytes((0xA3, 0x03)) + pick(0x11, 0x22)                            # LDA 3,S(dx)
    body = (bytes((0xE2, 0x30, 0xA6, 0x90)) + diff(0x3020) + diff(0x3080) + bytes((0xA3, 0x01)) + absolute +
            bytes((0x48, 0xA3, 0x03)) + absolute +                                # PHA |dy| / LDA 3,S(dx) / |dx|
            bytes((0xC3, 0x01, 0xB0, len(vertical) + 2)) + vertical +            # CMP 1,S / BCS 가로
            bytes((0x80, len(horizontal))) + horizontal + store)
    return box.ENTER + body + box.LEAVE


def _mother_slot():
    return NPC_SLOT0 + next(i for i, v in enumerate(VILLAGERS) if v[4] == T_MOTHER)


def native():
    """(바이트, {이름: 주소}). 인물 스크립트 명령 37 이 JSL 로 부르는 루틴과 이벤트 스크립트."""
    def layout(at):
        a, out = {}, bytearray()

        def put(name, code):
            a[name] = CODE_AT + len(out)
            out.extend(code)
        put('wait', box.ENTER + box.wait(20) + box.LEAVE)
        put('wait6', box.ENTER + box.wait(6) + box.LEAVE)
        put('blank2', bytes((0x00, 0xFF)))      # 빈 캔버스 줄(plane 0 = 00, plane 1 = FF, dq4chapterbox 와 같음)
        put('quiet', box.ENTER + bytes((0xA9, SILENT_SONG, 0x22, 0x91, 0xFE, 0x24,      # 1A(앞 곡 정리)
                                        0xA9, SILENT_SONG, 0x22, 0x9A, 0xFE, 0x24)) +   # 01(곡 틀기)
            box.LEAVE)
        put('spar', _spar(at))
        put('reveal_slow', _reveal_hold())
        put('wait1', box.ENTER + box.wait(1) + box.LEAVE)
        put('face_hero', _face_hero())
        put('darken', _darken())
        put('talk_slot', _talk_slot())
        put('talk_event', bytes((0xA0, *_long(at.get('talk_slot', 0)), 0xFF)))
        put('talk_here', _talk_here(at.get('talk_event', 0)))
        for name, rect in (('voice_hut', VOICE_HUT), ('voice_bridge', VOICE_BRIDGE), ('frog_call', FROG_CALL)):
            put(name, _inside(*rect))
        put('hero_right', _hero_face(0x11))
        put('hero_up', _hero_face(0x88))
        put('skip_song', _skip_song())
        # 저녁: 주인공이 말을 건 칸에서 식탁 아래까지 걷는 동안(hero_walk) 아버지·어머니도 의자로 가고, 모두 앉으면(table_ready)
        # 끝 이벤트: 위를 봄(C1 80) → 저녁 대사 → 검은 화면 → 서술 → 곡 건너뛰기 → 1장 왕좌의 방으로(이벤트 명령 90, $198E = 80)
        put('end_event', b''.join(bytes((0x60, t[1] & 0xFF, t[1] >> 8)) if isinstance(t, tuple) else t
                                  for t in end_event(at)))
        way = walker_box(SHINSIA_WAY_CELLS)
        put('shinsia_aside', hero_routes(step_aside(way, (('y', way[3] // 8),), bytes((0xA0, *_long(at.get('hero_up', 0))))),
                                         None))
        put('shinsia_way', _hero_clear(*way))
        put('hero_walk', hero_routes(SUPPER_ROUTES, None))
        fx, fy = FATHER_CELL
        put('father_way', _hero_clear(fx * 8, FATHER_SEAT_CELL[1] * 8, fx * 8 + 16, fy * 8 + 16))
        put('table_ready', _all_at([(0, *HERO_AT, None), (_mother_slot(), MOTHER_PATH[-1][0] * 2, MOTHER_PATH[-1][1] * 2, 0x10)]))
        put('end', _event_start(at.get('end_event', 0)))
        return bytes(out), a
    _, at = layout({})
    return layout(at)


def end_event(at):
    """저녁 끝 이벤트의 토큰 목록: 바이트, 또는 메시지(이벤트 명령 60)는 ('msg', 번호). dq4msgwait 가 메시지 끝 코드를
    고를 때도 이 목록을 본다."""
    g, n, x, y = CHAPTER1_AT
    return ([bytes((0xC1, HERO_AT_TABLE))] +
            # C1 은 31E0 만 바꿔 그림(자세 3240·3260)이 앞모습으로 남았다
            [bytes((0xA0, *_long(at.get('hero_up', 0))))] +
            [('msg', m) for m in M_SUPPER_LINES] +
            [bytes((0x10, *DINNER, 0xA0, *_long(at.get('darken', 0)))), ('msg', M_STORY_BEGINS),
             bytes((0xA0, *_long(at.get('skip_song', 0)), 0x90, g, n, x, y, 0x01, 0x80, 0xFF))])


def _yes_no(ask, yes, no):
    return [{"op": "msg", "id": f"{ask:03X}"},
            {"op": "if", "cond": {"code": "05"},
             "then": {"op": "msg", "id": f"{yes:03X}"}, "else": {"op": "msg", "id": f"{no:03X}"}}]


def _flag_on(flag):
    return {"op": "flag-on", "index": flag[0], "mask": flag[1]}


def talk_doc():
    """dq5talkwrite 의 dq5talk/1: 덧붙인 대화 900~(빈 번호 없이). 조건 05 는 예·아니요 창(06:B383)에서 예."""
    msg = lambda m: {"op": "msg", "id": f"{m:03X}"}  # noqa: E731
    scripts = [
        (T_ASK, _yes_no(M_ASK, M_YES, M_NO) + [_flag_on(DONE)]),
        (T_FROG, _yes_no(M_FROG_ASK, M_FROG_YES, M_FROG_NO) + [msg(M_FROG_STORY), _flag_on(FROG_MET)]),
        (T_SHINSIA, [msg(M_SHINSIA_MEET), _flag_on(SHINSIA_START)]),
        (T_FATHER_SUPPER, _yes_no(M_FATHER_ASK, M_FATHER_YES, M_FATHER_NO) + [_flag_on(SUPPER)]),
        (T_GATE, _yes_no(M_GATE_ASK, M_GATE_YES, M_GATE_NO)),
    ]
    return {"format": "dq5talk/1", "scripts": [{"talk": f"{t:03X}", "body": body} for t, body in scripts]}


def _spin(at):
    """모샤스: 두 바퀴 돌기(NDS 는 방향을 바꾸고 6프레임 기다리기를 여덟 번). 인물 스크립트는 명령마다 다음 차례를
    기다리고, 속도 1 이면 차례가 8프레임이라 한 칸에 19프레임이 걸렸다. 도는 동안만 속도(1E)를 올려 차례를 당긴다.
    한 37 안에서 방향을 모두 바꾸면 그 사이 인물 그림을 다시 그리지 않아 돌지 않았다."""
    out = [_cmd('1E', SPIN_SPEED)]
    for d in (0x40, 0x20, 0x80, 0x10) * 2:
        out += [_cmd('2F', d), _cmd('37', *_long(at['wait1']))]
    return out + [_cmd('1E', WALK_SPEED)]


def _cmd(op, *args):
    return {"op": op, "args": list(args)}


def _long(addr):
    return [addr & 0xFF, addr >> 8 & 0xFF, addr >> 16]


def _msg(m):
    return _cmd('21', m & 0xFF, m >> 8)


def _wait_on(flag):
    return _cmd('09', 0x80 | flag[0], flag[1])


def _walk(path):
    return [c for x, y in path for c in (_cmd('13', x * 2, y * 2), _cmd('14'))]


def master_script(boxes):
    """수련: 상자 → 검은 화면에서 칼 여섯 합 → 밝히기 → 조작을 풀고 주인공이 말을 걸어 대화가 끝날(깃발) 때까지 → 맺음말 → 나가기."""
    _, at = native()
    head = [_cmd('3F'), _cmd('37', *_long(at['quiet'])), _cmd('37', *_long(boxes[SCENE.name])), _cmd('37', *_long(at['spar'])),
            _cmd('37', *_long(at['reveal_slow'])), _cmd('37', *_long(at['talk_here'])), _wait_on(DONE)]
    tail = [_msg(M_AFTER), _cmd('1C')] + _walk(MASTER_OUT) + [_cmd('28'), _cmd('40'), _cmd('16')]
    return {"address": MASTER_SCRIPT, "commands": head + tail}


def scripts():
    """서장 뒤쪽 인물 스크립트: 개구리 퇴장, 신시아·개구리 꼴의 모샤스, 아버지의 끝."""
    _, at = native()
    call = lambda name: _cmd('37', *_long(at[name]))  # noqa: E731
    inside = lambda name: _cmd('05', *_long(at[name]))  # noqa: E731
    fx, fy = FROG_AT
    jump = [c for (x, y), lift in FROG_JUMP for c in (_cmd('39', lift), _cmd('13', x * 2, y * 2 + 1), _cmd('14'))]
    hops = [c for k, (x, y) in enumerate(FROG_OUT)
            for c in (_cmd('39', 4 if k % 2 == 0 else 0), _cmd('13', x * 2, y * 2 + 1), _cmd('14'))]
    # 연못에 숨어 있다가 오두막을 나설 때·다리 동쪽 끝에서 목소리, 다리 위에서 도와 달라는 말 뒤 떠올라 다리로 뛰어오른다.
    # 물 위와 주인공 곁을 지나므로 1C. 착지 뒤 주인공 쪽(서쪽)을 보고 주인공을 동쪽으로 돌려세운 뒤 말을 건다
    frog = ([_cmd('27'),
             inside('voice_hut'), _cmd('3F'), _msg(M_CALL), _cmd('40'),
             inside('voice_bridge'), _cmd('3F'), _msg(M_CALL), _cmd('40'),
             inside('frog_call'), _cmd('3F'), _msg(M_HELP),
             _cmd('20', *SPLASH), _cmd('50', fx * 2, fy * 2 + 1), _cmd('53'), _cmd('4F'), call('wait'),
             _cmd('1C'), _cmd('1E', 0x02), _cmd('2F', 0x80)] + jump +
            [_cmd('38'), _cmd('2F', 0x20), call('wait'), call('hero_right'), call('wait6'),
             call('talk_here'), _wait_on(FROG_MET), _cmd('3F'),
             _cmd('20', *JUMP), _cmd('2F', 0x10)] + hops +
            [_cmd('38'), _cmd('20', *STAIRS), _cmd('51'), _cmd('52'), _cmd('40'), _cmd('16')])
    sx, sy = SHINSIA_AT
    # NDS mlb1a 처럼 말을 걸어야 시작한다(대화 902 가 신시아 시작 깃발을 켬)
    shinsia = ([_wait_on(SHINSIA_START), _cmd('3F'), _cmd('20', 0x37, 0)] + _spin(at) +
               [_cmd('51'), _cmd('10', *MORPH), _wait_on(MORPH_BACK),
                # 돌기는 오른쪽 보기로 끝나므로, 주인공 쪽을 보고 다시 나타나 말한다
                _cmd('50', sx * 2, sy * 2), _cmd('37', *_long(at['face_hero'])), _cmd('53'), _cmd('4F'), _msg(M_MORPH), _msg(M_BYE),
                _msg(M_SUPPER)] +
               # 주인공이 문틈 (4,0D) 쪽에서 다가오면 나가는 길에 선 채 말이 걸리므로, 주인공을 비키게 하고(shinsia_aside)
               # 길에서 벗어나기를 기다린다. 1C 는 남겨 둔다(조작을 막은 채 걷다 막히면 멈춤)
               [call('shinsia_aside'), inside('shinsia_way'), _cmd('1C')] + _walk(SHINSIA_OUT) + [_cmd('28'), _cmd('10', *SHINSIA_MET), _cmd('40'), _cmd('16')])
    form = ([_cmd('27'), _wait_on(MORPH), _cmd('50', sx * 2, sy * 2), _cmd('37', *_long(at['face_hero'])), _cmd('53'), _cmd('4F'),
             _msg(M_MORPH), _msg(M_MIMIC), _msg(M_SORRY)] + _spin(at) +
            # 51 은 안 보이게만 해 말을 걸 수 있는 채로 남는다. 52 로 자리를 치운다
            [_cmd('51'), _cmd('52'), _cmd('10', *MORPH_BACK), _cmd('16')])
    # 대답하면 주인공(이벤트)·아버지·어머니가 함께 식탁으로 가고, 모두 앉으면 아버지가 저녁 이벤트를 건다. 아버지는 주인공이
    # 의자 칸에서 비킨 뒤 걷는다(father_way). 조작을 막은 채 걸으므로 1C: 의자 칸에서 말을 건 주인공에 막히면 저녁이 멈췄다
    father = ([_wait_on(SUPPER), _cmd('3F'), _cmd('1C'), call('hero_walk'), inside('father_way')] + _walk([FATHER_SEAT]) +
              [_cmd('2F', 0x20), inside('table_ready'), call('end'), _cmd('16')])
    mother = [_wait_on(SUPPER), _cmd('1C')] + _walk(MOTHER_PATH) + [_cmd('2F', 0x10), _cmd('16')]
    return [{"address": FROG_SCRIPT, "commands": frog}, {"address": SHINSIA_SCRIPT, "commands": shinsia},
            {"address": FORM_SCRIPT, "commands": form}, {"address": FATHER_SCRIPT, "commands": father},
            {"address": MOTHER_SCRIPT, "commands": mother}]


def npc_lists():
    """(lists, new_lists, overrides, scripts) 에 더할 것. 대체 목록은 앞에 둔 것부터 맞춰 본다."""
    master = ch1.entry(MASTER_SRC, *MASTER_AT, SWORDSMAN, 'down', T_ASK)
    sleeper = ch1.entry(SLEEPER_SRC, *SLEEPER_AT, MAN, 'right', T_SLEEPER)
    sleeper['fields']['x'] += 1
    people = [ch1.entry(ch1.STATIC, x, y, g, f, t) for x, y, g, f, t in VILLAGERS] + [sleeper]
    father = next(i for i, v in enumerate(VILLAGERS) if v[4] == T_FATHER)
    x, y, g, f, _ = VILLAGERS[father]
    supper_father = ch1.entry(FATHER_SRC, x, y, g, f, T_FATHER_SUPPER)
    # 빌린 칸의 이동 간격 4 면 스크립트 명령마다 약 32프레임을 기다려, 대답 뒤 저녁 대사까지 늘어졌다
    supper_father["fields"]["interval"] = 1
    supper = people[:father] + [supper_father] + people[father + 1:]
    mother = next(i for i, v in enumerate(VILLAGERS) if v[4] == T_MOTHER)
    x, y, g, f, t = VILLAGERS[mother]
    supper[mother] = ch1.entry(MOTHER_SRC, x, y, g, f, t)
    # 맵에 들어온 첫 프레임엔 대본의 27(숨기)이 아직 돌지 않아 연못 자리에 잠깐 보였다. 맵 밖에 두고 50 으로 데려온다
    frog = ch1.entry(FROG_SRC, FROG_HIDDEN_X, FROG_AT[1], FROG, 'down', T_FROG)
    # 인물 스크립트는 이동 간격(3300 위 니블)마다 돈다. 빌린 칸의 간격이면 명령 05 의 자리 판정이 약 120프레임에 한 번이라
    # 걸어 지나가는 주인공을 놓쳤다
    frog["fields"]["interval"] = 1
    shinsia = [ch1.entry(SHINSIA_SRC, *SHINSIA_AT, GIRL, 'down', T_SHINSIA),
               ch1.entry(FORM_SRC, *SHINSIA_AT, FROG, 'down', T_SHINSIA)]
    lists = [{"map": CELLAR, "entries": [master]}, {"map": VILLAGE, "entries": people + [frog]}]
    new_lists = [{"name": "cellar_after", "entries": []}, {"name": "cellar_shinsia", "entries": shinsia},
                 {"name": "village_frog_gone", "entries": people}, {"name": "village_supper", "entries": supper}]
    over = lambda m, flag, name: {"map": m, "flag": flag[0], "when": "on", "mask": flag[1], "list": f"new:{name}"}  # noqa: E731
    overrides = [over(CELLAR, SHINSIA_MET, 'cellar_after'), over(CELLAR, FROG_MET, 'cellar_shinsia'),
                 over(CELLAR, DONE, 'cellar_after'),
                 over(VILLAGE, SHINSIA_MET, 'village_supper'), over(VILLAGE, FROG_MET, 'village_frog_gone')]
    out_scripts = [master_script(box.entry_points(box.GAME_SCENES)),
                   {"address": SLEEPER_SCRIPT, "commands": [_cmd('16')]}] + scripts()
    return lists, new_lists, overrides, out_scripts


def apply(data):
    d = bytearray(data)
    code, _ = native()
    o = lorom(CODE_AT)
    if any(d[o:o + len(code)]):
        raise SystemExit(f'{CODE_AT:06X}: 비어 있지 않은 자리')
    d[o:o + len(code)] = code
    return bytes(d)
