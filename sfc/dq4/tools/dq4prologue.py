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
from dq4environmentrom import GROUPS  # noqa: E402
from dq5map import lorom  # noqa: E402

VILLAGE, CELLAR = (f'{g:02X}/{n:02X}' for g, n in (GROUPS['14-00'], GROUPS['14-01']))
SCENE = box.PROLOGUE
# 7E:219E & 80, 검사의 물음에 대답하면 켬. 원래 롬은 이 비트를 따로 켜거나 보지 않는다(바이트를 통째로 쓰는 곳은 있어
# DQ5 중반 세이브에서는 켜져 있음). 새 게임에서는 꺼져 있다
DONE = (SCENE.flag[0] - 0x7E2190, SCENE.flag[1])
START = (CELLAR, 3 * 2, 0x0F * 2)                    # 지하 아래 방 (3,0F), 검사 바로 아래(말을 걸 수 있게)
CODE_AT = 0x5EC000
SWORD = (0x37, 0x00)                                 # 효과음 37(공격이 맞을 때)

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
M_ASK = talk(say('왜 그러느냐? @./벌써 항복이냐?')) + 0x3C6
M_YES = talk(say('그래. 오늘은 이쯤/해 두자……')) + 0x3C6
M_NO = talk(say('오오! 제법 버티는구나.', '하지만 오늘은 이쯤/해 두자.')) + 0x3C6
M_AFTER = talk(say('내 소임은 어서 너를/제 몫을 하는 전사로/키우는 것이지만/서둘러 봐야 소용없겠지.',
                   '자, 돌아가 볼까./@도 집에서 푹/쉬는 게 좋을 게다.')) + 0x3C6

# 마을 사람(낮). 서장은 해 질 녘이라 NDS 의 대사도 그렇다
T_FARMER = talk(say('어라, @ 아닌가./슬슬 해가 지겠구먼.', '어디, 나도 집에 가서/밥이나 먹어야겠구먼.'))
T_MAN = talk(say('이야, @./지친 얼굴이로군./그래, 검술 수련을……', '힘들겠지만 꺾이지 마./어쨌든 너는/우리의 희망이니까.',
                 '라고 해도 지금의 너는/무슨 말인지 모르겠지./신경 쓰지 않아도 돼.'))
T_MASTER = talk(say('푸하아아!!/오오, @. 너도/물 마시러 왔느냐?', '오늘 검술 수련은/좀 거칠었으니 말이다./와하하하하.',
                    '그런데 신시아와는/여전히 사이가 좋은/모양이구나.', '바로 며칠 전에도/나를 찾아와서는/너를 너무 괴롭히지/말라더구나.',
                    '뭐, 요즘 수련이 좀/지나쳤을지도 모르지만/그만큼 너도/강해졌다는 뜻이다.'))
T_WIZARD = talk(say('오오, 왔구나, @./오늘은 그대에게/베기라마 주문을/가르쳐 주마.',
                    '라고 하고 싶다만/오늘은 벌써 해가/저물어 가는구나./수업은 내일 하자꾸나.'))
T_SLEEPER = talk(say('쿨쿨…… 쿨쿨……/이 마을에는 아무도/못 들어온다!!/음냐음냐……'))
T_MERCHANT = talk(say('어라, 누군가 했더니/@ 씨군요./아니, 잠깐 방 청소를요.', '하긴 이런 산골 마을에/손님이 올 리도 없고/온다 해도 설마/재워 줄 수야……',
                      '아! 아니, 그, 뭐……/옛날 버릇이라는/거죠. 아하하하……'))
T_MOTHER = talk(say('어머, 왔니, @./배고프지?/금방 밥 차려 줄게.'))
T_FATHER = talk(say('오오, 왔느냐, @./그런데 신시아가/보이지 않는구나.', '아까 너를 부르러/간다고 나갔는데/어디서 엇갈린 게/아닌지 모르겠구나.',
                    '아직 너를 찾고/있다면 가엾으니/네가 이 근처를/찾아보고 오너라.'))
# 문지기는 DQ5 묻기 대화(06:B34F): 메시지 T + 3C6 뒤 예·아니요, 예면 +1, 아니요면 +2
T_GATE = 0x24F
TEXTS[T_GATE + 0x3C6] = say('여기는 마을 입구./수상한 놈이 들어오지/못하게 지키고 있다.', '그런데 @./마을 밖으로/나가고 싶으냐?')
TEXTS[T_GATE + 0x3C7] = say('하지만 아직 그때가/아니다. 지금의 너로는/아직 힘이 모자란다.')
TEXTS[T_GATE + 0x3C8] = say('음, 그렇지./마을을 떠나려면 너는/훨씬 더 강해져야/한단다.')

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
SLEEPER_AT = (0x13, 0x15)

# 서장 뒤쪽 깃발. 모두 원래 롬이 비트로 켜거나 보지 않는 비트(sfc/dq5/docs/dq5-flags.md)
FROG_MET = (0x0C, 0x08)         # 7E:219C bit3  개구리의 이야기를 들음
SHINSIA_START = (0x0C, 0x40)    # 7E:219C bit6  신시아에게 말을 걺 → 모샤스
MORPH = (0x02, 0x10)            # 7E:2192 bit4  신시아가 개구리로
MORPH_BACK = (0x04, 0x01)       # 7E:2194 bit0  개구리가 신시아로
SHINSIA_MET = (0x01, 0x08)      # 7E:2191 bit3  신시아가 집으로 감
DINNER = (0x01, 0x40)           # 7E:2191 bit6  저녁 대사가 끝남(끝 이벤트가 켬)
SUPPER = (0x04, 0x02)           # 7E:2194 bit1  아버지에게 대답함 → 식탁에 앉음
speak = ch1.speak
narrate = ch1.narrate
SHINSIA = '신시아'

# 개구리(마을): 말을 걸면 묻고, 대답에 따라 한마디 → 공주 이야기 → FROG_MET
T_FROG = 0x901
M_CALL = talk(say('용사님 용사님……')) + 0x3C6
M_HELP = talk(say('용사님 제발/도와주세요……')) + 0x3C6
M_FROG_ASK = talk(say('아! 놀라지 마세요……/저는 개구리가/아니랍니다.', '아! 지금 아무리 봐도/개구리라고/생각하셨죠?')) + 0x3C6
M_FROG_YES = talk(say('당신은 정직한/분이군요. 그 정직함을/믿고 부탁이/있어요.')) + 0x3C6
M_FROG_NO = talk(say('당신은 상냥한/분이군요. 그 상냥함을/믿고 부탁이/있어요.')) + 0x3C6
M_FROG_STORY = talk(say('이미 눈치채셨겠지만/실은 저는 어느 나라의/공주였답니다.',
                        '하지만 나쁜 마법사에게/저주를 받아 이런/모습이 되어/버렸지요.',
                        '뭐, 이렇게 된 건/어쩔 수 없고/개구리도 생각만큼/나쁘진 않아요.',
                        '그래서 날마다/태평하게 지내고/있었는데……', '곤란한 일이 생겼어요./그건…………',
                        '그건………………', '…………………………', '아! 안 돼./누가 와요!')) + 0x3C6
# 신시아(지하): 말을 걸면 웃음을 참다 개구리로 변한다
T_SHINSIA = 0x902
M_SHINSIA_MEET = talk(speak(SHINSIA, '아, @. 검술/수련 벌써/끝났나 보네.', '응? 무슨 일 있어?/뭐? 커다란 개구리?/무슨 소리야……',
                            '나는 계속 여기/있었는데/개구리 같은 건/못 봤……', '모, 못 봤……',
                            '풉! 아하하하/아하하…… 이제/못 참겠어!!', '네가 본 건/이 개구리지?')) + 0x3C6
M_MORPH = talk(narrate('신시아는/모샤스를 외웠다!!')) + 0x3C6
M_MIMIC = talk(speak(SHINSIA, '태평하게 지내고/있었는데/곤란한 일이/생겼어요. 그건……', '그건…………')) + 0x3C6
M_SORRY = talk(speak(SHINSIA, '……라니, 미안해./실은 그다음 대사가/떠오르지 않았어.',
                     '좀 더 제대로 뒷이야기/까지 생각하고 할 걸/그랬는데, 너한테/빨리 보여 주고 싶었거든.',
                     '놀랐지!/나 여러 가지로 모습을/바꿀 수 있는/모샤스 주문을 배웠어!')) + 0x3C6
M_BYE = talk(speak(SHINSIA, '그럼 난 갈게!')) + 0x3C6
M_SUPPER = talk(speak(SHINSIA, '아! 맞다!/너희 어머니가/부르셨어./벌써 저녁이래.', '그럼 @,/내일 봐!')) + 0x3C6
# 저녁(집): 신시아를 만난 뒤 아버지에게 말을 걸면 묻고(대화 903 → SUPPER), 식탁에 앉아 저녁을 먹는다(끝 이벤트)
T_FATHER_SUPPER = 0x903
M_FATHER_ASK = talk(say('음, @. 왔느냐?/그래, 신시아와는/만났느냐?')) + 0x3C6
M_FATHER_YES = talk(say('그러냐. 그거/잘됐구나.')) + 0x3C6
M_FATHER_NO = talk(say('그러냐……/포기하고 돌아갔는지도/모르겠구나./뭐, 괜찮겠지.')) + 0x3C6
M_SUPPER_LINES = [talk(say(*pages)) + 0x3C6 for pages in (
    ('좋아! 여보,/슬슬 밥 먹읍시다!/배가 등에 붙었구먼.',),
    ('네네. 지금 차려요.',),
    ('자, @./너도 자리에 앉으렴.',),
    ('흠! 이거 맛있구먼!/우물우물 우물우물……',
     '그런데 말이다, @./너는 아직 어려서/이 마을밖에/모르겠지만……',
     '바깥 세상은/아주 넓단다./그리고 온갖 사람들이/살고 있지.',
     '너도 언젠가 자라서/이 마을을 떠날 때가/올지도 모르겠구나.',
     '그때 바깥 세상에서/너는 어떤 사람들과/만나게 될까……'),
    ('당신도 참, 무슨 말을/하나 했더니!/밥 먹다가 쓸쓸해지는/얘기는 그만해요.',
     '이 아이는 계속/우리와 함께 사는/거예요. 무슨 일이/있어도요!'),
    ('오오, 그랬지!/이거 내가 그만……/와하하하하!',))]
M_STORY_BEGINS = talk(narrate('이야기는 이렇게/시작된다……')) + 0x3C6

FROG, GIRL = 0x50, 0x0E         # 개구리 그림이 DQ5 에 없어 슬라임, 신시아는 DQ5 소녀(임시)
FROG_AT = (0x0F, 0x0C)
FROG_OUT = [(0x10, 0x0C), (0x10, 0x0A)]
SHINSIA_AT = (3, 0x0E)          # 수련하던 자리
SHINSIA_OUT = [(4, 0x0E), (4, 0x07), (3, 0x07)]
FROG_SRC, FROG_SCRIPT = {"list": "05:B2EE", "index": 4}, "05:B352"
SHINSIA_SRC, SHINSIA_SCRIPT = {"list": "05:B2EE", "index": 7}, "05:B386"
FORM_SRC, FORM_SCRIPT = {"list": "05:B2EE", "index": 8}, "05:B3B3"
FATHER_SRC, FATHER_SCRIPT = {"list": "05:B466", "index": 0}, "05:B46D"
MOTHER_SRC, MOTHER_SCRIPT = {"list": "05:B48B", "index": 3}, "05:B4A7"
# 집의 식탁 (4,11) 과 의자 (3,11)·(5,11). 아버지는 오른쪽, 어머니는 왼쪽 의자, 주인공은 식탁 위쪽 (4,10) 에서 아래를 봄
FATHER_SEAT, MOTHER_PATH = (5, 0x11), [(3, 0x10), (3, 0x11)]
# 주인공은 아버지 오른쪽 칸 (6,12) 에서 말을 건다. 거기서 위로 2칸, 왼쪽으로 2칸(DQ5 셀 4·4)
HERO_TO_SEAT = ((0x08, 4), (0x02, 4))
# 1장 왕좌의 방 첫 자리(dq4chapter1.START)와 같은 칸
CHAPTER1_AT = (0x36, 0x01, 32, 42)


def _event_start(script):
    """인물 스크립트(명령 37)에서 이벤트 스크립트를 건다: $19B3~$19B5 = 주소, $19AE |= 80(dq5-event-format 「시작」).
    이벤트 스크립트는 메인 문맥(00:BED2)에서 돈다."""
    return (box.ENTER + bytes((0xA9, script & 0xFF, 0x8D, 0xB3, 0x19, 0xA9, script >> 8 & 0xFF, 0x8D, 0xB4, 0x19,
                               0xA9, script >> 16, 0x8D, 0xB5, 0x19,
                               0xAD, 0xAE, 0x19, 0x09, 0x80, 0x8D, 0xAE, 0x19)) + box.LEAVE)


FADE_SPEED = 0x40   # 곡 줄이기(소리 명령 04)의 X. dq4overture 가 서곡을 줄일 때와 같은 값


def _darken():
    """맵 곡을 줄이며(24:FEC7, 명령 04, A = 지금 맵 곡 $194B) 맵을 어둡게 한 뒤 주화면을 BG3(창)만으로: 검은 화면에
    메시지 창만 남는다(dq4chapterbox 의 맵 훅과 같은 값). 1장 상자·서술 동안 곡이 없게 한다."""
    return (box.ENTER + bytes((0xAD, 0x4B, 0x19, 0x29, 0x7F, 0xA2, FADE_SPEED, 0x00, 0x22, 0xC7, 0xFE, 0x24)) +
            box.fade(14, 0, 2) +
            bytes((0xA9, 0x04, 0x8D, 0x33, 0x07, 0x8D, 0x2C, 0x21, 0x8D, 0x2D, 0x21)) + box.wait(1) +
            bytes((0xA9, 0x0F, 0x8D, 0x1D, 0x00)) + box.LEAVE)


def _skip_song():
    """맵을 불러올 때 곡을 바꾸지 않게(7E:21A5 bit6). 1장 상자·서술 동안 곡이 없게, 새 게임 시작과 같은 값."""
    addr, bit = box.SKIP_SONG
    return (box.ENTER + bytes((0xAF, *addr.to_bytes(3, 'little'), 0x09, bit, 0x8F, *addr.to_bytes(3, 'little'))) +
            box.LEAVE)


NEAR = (4, 8, 12)    # 다가왔다고 볼 거리(DQ5 셀). 개구리 목소리 두 번(12·8)과 말 걸기(4), 신시아(4)
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


def _near(cells):
    """인물 명령 05 가 부르는 루틴: 주인공(슬롯 0)과 이 인물(슬롯 $90)의 X·Y 가 둘 다 cells 셀 안이면 A = 0
    (05 가 다음 명령으로), 아니면 A = 1(다음 프레임에 다시). 7E:3020·3080 은 인물 표의 X·Y."""
    def axis(table, far):
        return bytes((0xAF, table & 0xFF, table >> 8, 0x7E, 0x38, 0xFF, table & 0xFF, table >> 8, 0x7E,   # LDA 주인공 / SEC / SBC 인물,X
                      0x10, 0x03, 0x49, 0xFF, 0x1A,                                                       # 음수면 부호를 뒤집음
                      0xC9, cells + 1, 0xB0, far))                                                        # CMP / BCS 멂
    head = bytes((0x08, 0xC2, 0x30, 0xDA, 0x5A, 0x8B, 0xE2, 0x30, 0xA6, 0x90))  # PHP / REP / PHX / PHY / PHB / SEP / LDX $90
    tail_far = bytes((0xC2, 0x30, 0xAB, 0x7A, 0xFA, 0xA9, 0x01, 0x00, 0x28, 0x6B))   # REP / PLB / PLY / PLX / LDA #1 / PLP / RTL
    tail_near = bytes((0xC2, 0x30, 0xAB, 0x7A, 0xFA, 0xA9, 0x00, 0x00, 0x28, 0x6B))
    y_part = axis(0x3080, len(tail_near))
    x_part = axis(0x3020, len(y_part) + len(tail_near))
    return head + x_part + y_part + tail_near + tail_far


def native():
    """(바이트, {이름: 주소}). 인물 스크립트 명령 37 이 JSL 로 부르는 루틴과 이벤트 스크립트."""
    def layout(at):
        a, out = {}, bytearray()

        def put(name, code):
            a[name] = CODE_AT + len(out)
            out.extend(code)
        put('wait', box.ENTER + box.wait(20) + box.LEAVE)
        put('wait6', box.ENTER + box.wait(6) + box.LEAVE)
        put('darken', _darken())
        put('talk_slot', _talk_slot())
        put('talk_event', bytes((0xA0, *_long(at.get('talk_slot', 0)), 0xFF)))
        put('talk_here', _talk_here(at.get('talk_event', 0)))
        for cells in NEAR:
            put(f'near{cells}', _near(cells))
        put('skip_song', _skip_song())
        g, n, x, y = CHAPTER1_AT
        # 저녁: 주인공이 식탁에 앉아 아래를 봄(C1 40) → 저녁 대사 → 끝: 검은 화면 → 서술 → 곡 건너뛰기 →
        # 1장 왕좌의 방으로(이벤트 명령 90, $198E = 80)
        walk = bytes(b for d, k in HERO_TO_SEAT for b in (d, k)) + bytes((0xC1, 0x40))
        lines = b''.join(bytes((0x60, m & 0xFF, m >> 8)) for m in M_SUPPER_LINES)
        put('end_event', walk + lines + bytes((0x10, *DINNER, 0xA0, *_long(at.get('darken', 0)),
                                               0x60, M_STORY_BEGINS & 0xFF, M_STORY_BEGINS >> 8,
                                               0xA0, *_long(at.get('skip_song', 0)), 0x90, g, n, x, y, 0x01, 0x80, 0xFF)))
        put('end', _event_start(at.get('end_event', 0)))
        return bytes(out), a
    _, at = layout({})
    return layout(at)


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
    ]
    return {"format": "dq5talk/1", "scripts": [{"talk": f"{t:03X}", "body": body} for t, body in scripts]}


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


def _spin(at):
    """모샤스: 한 바퀴 반 돌기(NDS 는 6프레임마다 방향을 바꿈)."""
    out = []
    for d in (0x40, 0x20, 0x80, 0x10) * 2:
        out += [_cmd('2F', d), _cmd('37', *_long(at['wait6']))]
    return out


def master_script(boxes):
    """수련: 상자 → 밝히기 → 칼 소리 셋 → 조작을 풀고 주인공이 말을 걸어 대화가 끝날(깃발) 때까지 → 맺음말 → 나가기."""
    _, at = native()
    head = [_cmd('3F'), _cmd('37', *_long(boxes[SCENE.name])), _cmd('37', *_long(boxes['reveal'])),
            _cmd('02', 3), _cmd('37', *_long(at['wait'])), _cmd('20', *SWORD), _cmd('01'),
            _cmd('37', *_long(at['wait'])),
            _cmd('37', *_long(at['talk_here'])), _wait_on(DONE)]
    tail = [_msg(M_AFTER)] + _walk(MASTER_OUT) + [_cmd('28'), _cmd('40'), _cmd('16')]
    return {"address": MASTER_SCRIPT, "commands": head + tail}


def scripts():
    """서장 뒤쪽 인물 스크립트: 개구리 퇴장, 신시아·개구리 꼴의 모샤스, 아버지의 끝."""
    _, at = native()
    near = lambda cells: _cmd('05', *_long(at[f'near{cells}']))  # noqa: E731
    # 주인공이 다가오면 목소리 둘(NDS 의 깃발 6·7 자리) → 더 다가오면 개구리가 말을 건다
    frog = ([near(12), _cmd('3F'), _msg(M_CALL), _cmd('40'), near(8), _cmd('3F'), _msg(M_HELP), _cmd('40'),
             near(4), _cmd('37', *_long(at['talk_here'])), _wait_on(FROG_MET), _cmd('3F')] + _walk(FROG_OUT) +
            [_cmd('28'), _cmd('40'), _cmd('16')])
    sx, sy = SHINSIA_AT
    shinsia = ([near(4), _cmd('37', *_long(at['talk_here'])), _wait_on(SHINSIA_START), _cmd('3F'), _cmd('20', 0x37, 0)] + _spin(at) +
               [_cmd('51'), _cmd('10', *MORPH), _wait_on(MORPH_BACK),
                _cmd('50', sx * 2, sy * 2), _cmd('53'), _cmd('4F'), _msg(M_MORPH), _msg(M_BYE), _msg(M_SUPPER)] +
               # 주인공이 문틈 (4,0D) 쪽에서 다가오면 나가는 길에 선 채 말이 걸리므로, 주인공을 지나 걷는다(1C)
               [_cmd('1C')] + _walk(SHINSIA_OUT) + [_cmd('28'), _cmd('10', *SHINSIA_MET), _cmd('40'), _cmd('16')])
    form = ([_cmd('27'), _wait_on(MORPH), _cmd('50', sx * 2, sy * 2), _cmd('53'), _cmd('4F'),
             _msg(M_MORPH), _msg(M_MIMIC), _msg(M_SORRY)] + _spin(at) +
            # 51 은 안 보이게만 해 말을 걸 수 있는 채로 남는다. 52 로 자리를 치운다
            [_cmd('51'), _cmd('52'), _cmd('10', *MORPH_BACK), _cmd('16')])
    # 대답하면 부모가 의자로 가고, 아버지가 저녁 이벤트를 건다(이벤트는 메인 문맥에서 주인공을 걷게 하고 대사를 띄움)
    father = ([_wait_on(SUPPER), _cmd('3F')] + _walk([FATHER_SEAT]) + [_cmd('2F', 0x20), _cmd('37', *_long(at['wait'])),
              _cmd('37', *_long(at['end'])), _cmd('16')])
    mother = [_wait_on(SUPPER)] + _walk(MOTHER_PATH) + [_cmd('2F', 0x10), _cmd('16')]
    return [{"address": FROG_SCRIPT, "commands": frog}, {"address": SHINSIA_SCRIPT, "commands": shinsia},
            {"address": FORM_SCRIPT, "commands": form}, {"address": FATHER_SCRIPT, "commands": father},
            {"address": MOTHER_SCRIPT, "commands": mother}]


def npc_lists():
    """(lists, new_lists, overrides, scripts) 에 더할 것. 대체 목록은 앞에 둔 것부터 맞춰 본다."""
    master = ch1.entry(MASTER_SRC, *MASTER_AT, SWORDSMAN, 'down', T_ASK)
    sleeper = ch1.entry(SLEEPER_SRC, *SLEEPER_AT, MAN, 'down', T_SLEEPER)
    people = [ch1.entry(ch1.STATIC, x, y, g, f, t) for x, y, g, f, t in VILLAGERS] + [sleeper]
    father = next(i for i, v in enumerate(VILLAGERS) if v[4] == T_FATHER)
    x, y, g, f, _ = VILLAGERS[father]
    supper = people[:father] + [ch1.entry(FATHER_SRC, x, y, g, f, T_FATHER_SUPPER)] + people[father + 1:]
    mother = next(i for i, v in enumerate(VILLAGERS) if v[4] == T_MOTHER)
    x, y, g, f, t = VILLAGERS[mother]
    supper[mother] = ch1.entry(MOTHER_SRC, x, y, g, f, t)
    frog = ch1.entry(FROG_SRC, *FROG_AT, FROG, 'down', T_FROG)
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
