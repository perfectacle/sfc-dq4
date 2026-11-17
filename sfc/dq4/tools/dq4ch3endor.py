"""DQ4 3장 엔돌 사건(dq4ch3slots 'E'): 왕의 허락, 가게 사기, 네네의 가게, 왕의 무기 주문과 납품, 은의 여신상.

FC 엔돌(그룹 04)은 SFC 40/00~0E(맵 번호 그대로), 여신상 동굴(FC 40/00~05)은 48/02~07 이다(dq4groupbuild LINKS).
FC 차례(fc/dq4/docs/dq4-chapter3-format.md 「사건 차례」 12~21·24):
  왕     04/06 (0B,0A) 대화 072. 첫 알현 0886(「예」 0887 / 「아니요」 0888, flag 없음), 왕자의 편지를 모니카에게 전한 뒤
         0889, 왕의 편지를 본몰 왕에게 전한 뒤 0888A($6286|=40), 그 뒤 088B, 가게를 사면 088C(주문 $6284|=08),
         납품을 다 채우면 088D.
  가게   04/08 (03,03) 주인 대화 04D: 063B 뒤, $6286 bit6 이면 0862 「35000ゴールドで この みせを かわぬか？」 →
         「예」 면 −35000(모자라면 0864) → 0865, $6286|=20, 1C 이벤트 09(아침, 04/00 (05,1C), 035B·035C).
         아들 08B(낮 067B, $6288|=02 / 밤 0554).
  네네   가게를 사면 04/00 (06,1C)(낮)·04/08 (03,03)(밤)에 나타난다(장소별 손질 1C:$A3B9·$A4E2). 대화 075: 굴 개통
         알림($6286 bit0)이면 08A0 → 08A2·08A4 → 08A3 → $62AA|=08. 낮 0866 「もう やすむ？」 → 잠 / 0867, 밤 0811 → 잠.
  납품   04/02 (11,12) 대화 03F(주문 뒤): 0873 → 칼·갑옷을 받아 $628F 의 니블에 셈, 77 이면 087B +60000 $6288|=10.
         옆 (12,12) 대화 03E 가 안내(0872·087D·087E).
  여신상 40/01 (11,02) 단추(03B3) → $62AA|=20, 40/02 로. 40/05 상자 (06,04)에 ぎんのめがみぞう. 04/0A 수집가(대화 04C)
         에게 팔면 +25000, $6286|=80.

옮긴 엔돌 기본 목록은 FC 2장 대회 중 목록이라(dq4npcport.fc_people 이 flag 없이 고름), 3장 동안의 엔돌 맵은 이 모듈이
기본 목록을 베껴 대화를 바꾼 목록으로 덮는다. 바꾸는 사람은 FC 3장 목록과 같은 칸에 있다. 형식은
sfc/dq4/docs/dq4-chapter3-format.md 「엔돌」.
"""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4chapter1 as ch1  # noqa: E402
import dq4ch2event as ch2  # noqa: E402
import dq4ch3event as ch3  # noqa: E402
from dq4chapterbox import ENTER, LEAVE  # noqa: E402
from dq4itemport import BENTO, STATUE  # noqa: E402
import dq4mercenary as merc  # noqa: E402

say, narrate = ch1.say, ch1.narrate
pages = ch2._speaker_pages

# 7E:2205: 저장되는 진행
IDX = 0x75
ALLOWED = (IDX, 0x01)          # 왕이 가게를 허락함(FC $6286&40). 가게 주인이 판다고 묻는다
SHOP = (IDX, 0x02)             # 가게를 삼(FC $6286&20). 네네·아들이 나타나고 주인이 빠짐
ORDER = (IDX, 0x04)            # 왕의 무기 주문을 받음(FC $6284&08)
DELIVERED = (IDX, 0x08)        # 납품을 다 채워 대금을 받음(FC $6288&10)
SOLD = (IDX, 0x10)             # 여신상을 수집가에게 팖(FC $6286&80)
SON_CHEER = (IDX, 0x20)        # 아들이 「와아 아빠 최고」 라 함(FC $6288&02)
NOTICE = (IDX, 0x40)           # 굴이 뚫렸다는 소식이 왔음(FC $6286&01). 굴 모듈이 04/01 에 들 때 켤 자리
OPENED = (IDX, 0x80)           # 네네에게 개통을 들음(FC $62AA&08). 굴 입구가 뚫린 쪽으로
# 7E:2206
IDX2 = 0x76
BUTTON = (IDX2, 0x01)          # 여신상 동굴 단추를 누름(FC $62AA&20). 40/01 첫 출구가 40/02 로
ASKED = (IDX2, 0x02)           # 단추 물음에 대답함(대화가 켜고 인물 스크립트가 끔)
PRESSED = (IDX2, 0x04)         # 그 대답이 「예」(인물 스크립트가 보고 끔)
# 납품 대화 한 번의 결과(deliver 가 쓰고 대화 갈래가 봄)
GAVE_SWORDS = (IDX2, 0x08)     # 이번에 칼을 받음
GAVE_ARMORS = (IDX2, 0x10)     # 이번에 갑옷을 받음
FULL = (IDX2, 0x20)            # 칼·갑옷이 다 참
LEFT_SWORDS = (IDX2, 0x40)     # 아직 받을 칼이 남음(남은 수 줄을 띄움)
LEFT_ARMORS = (IDX2, 0x80)     # 아직 받을 갑옷이 남음
FLAGS = (ALLOWED, SHOP, ORDER, DELIVERED, SOLD, SON_CHEER, NOTICE, OPENED, BUTTON, ASKED, PRESSED,
         GAVE_SWORDS, GAVE_ARMORS, FULL, LEFT_SWORDS, LEFT_ARMORS)

# 본몰 모듈(dq4ch3bonmalmo)의 편지 flag. test_dq4ch3endor 가 그 모듈이 있으면 같은지 본다
LETTER1 = (0x73, 0x10)         # 왕자의 편지를 모니카에게 전함(FC $6280&01)
LETTER2 = (0x73, 0x20)         # 왕의 편지를 본몰 왕에게 전함(FC $6283&01)

TOWN, CASTLE_HALL, THRONE, SHOP_UP, COLLECTOR, BARD_HALL = '40/00', '40/02', '40/06', '40/08', '40/0A', '40/0B'
# 여신상 동굴: FC 40/0k 는 SFC 48/(02+k). test_dq4ch3endor 가 dq4groupbuild.placement 와 견준다
CAVE_GROUP = 0x48
CAVE_ENTRY, CAVE_WET, CAVE_DRY, CAVE_LOW_WET, CAVE_LOW_DRY, STATUE_ROOM = (
    '48/02', '48/03', '48/04', '48/05', '48/06', '48/07')


def cell(x, y):
    """FC 칸 → 옮긴 인물·순간이동 셀(dq4npcport.cell)."""
    return (2 * x, 2 * y + 1)


# FC 3장 목록의 사람(맵, 낮·밤, FC 칸). 옮긴 기본 목록에도 같은 칸에 사람이 있다(test_dq4ch3endor)
KING = (THRONE, 'day', (0x0B, 0x0A))
DELIVER = (CASTLE_HALL, 'day', (0x11, 0x12))
GUIDE = (CASTLE_HALL, 'day', (0x12, 0x12))
SELLER = ((SHOP_UP, 'day', (0x03, 0x03)), (SHOP_UP, 'night', (0x05, 0x02)), (SHOP_UP, 'night', (0x01, 0x03)))
SON = ((SHOP_UP, 'day', (0x01, 0x03)), (SHOP_UP, 'night', (0x05, 0x03)))
NENE = ((TOWN, 'day', (0x06, 0x1C)), (SHOP_UP, 'night', (0x03, 0x03)))
COLLECTORS = ((COLLECTOR, 'day', (0x06, 0x03)), (COLLECTOR, 'night', (0x07, 0x05)))
SCOTT = (TOWN, 'day', (0x05, 0x13))                                     # FC 04/00 슬롯 0D, 대화 071
LAWRENCE = ((BARD_HALL, 'day', (0x07, 0x08)), (BARD_HALL, 'night', (0x07, 0x08)))   # FC 04/0B 슬롯 06, 대화 051
# FC 3장 밤에 04/0B 는 레코드 4((05,08)의 둘째 로렌스)를 숨긴다(1C:$A51E)
BARD_HIDDEN = ((BARD_HALL, 'night', (0x05, 0x08)),)
# 가게를 사기 전(1C:$A3B9·$A4E2)에는 네네·아들이 없고, 산 뒤에는 주인이 없다
BEFORE_SHOP = SON + NENE
AFTER_SHOP = SELLER
# 가게를 산 뒤 아침에 서는 자리(FC 1C 이벤트 09·잠 15:$9E56: 04/00 (05,1C), 네네 왼쪽)
NENE_SIDE = (TOWN, cell(0x05, 0x1C))

# 단추(FC 40/01 (11,02), 1D 이벤트 5E). 누르면 40/02 의 같은 칸으로 옮겨진다
BUTTON_FC = (0x11, 0x02)
BUTTON_LAND = (CAVE_DRY, (2 * BUTTON_FC[0], 2 * BUTTON_FC[1] + 1))
# 단추를 누른 뒤에는 40/01·40/03 에 다시 갈 수 없고(40/00 에서 40/01 첫 출구로 드는 길이 40/02 로, 40/03 은 40/01 로만
# 이어짐), FC 는 두 맵이 상자 열림 번호를 함께 쓴다. 누를 때 열림 비트를 물 빠진 쪽으로 옮겨 적는다
CHEST_PAIRS = ((CAVE_WET, CAVE_DRY), (CAVE_LOW_WET, CAVE_LOW_DRY))

STEEL_SWORD, IRON_ARMOR = 0x0C, 0x50           # DQ5 はがねのつるぎ·てつのよろい(FC 06·28)
ORDERED = 7                                     # 칼·갑옷 각 7(FC 088C)
SHOP_PRICE, STATUE_PRICE, DELIVERY_PAY = 35000, 25000, 60000

VARS = 0                       # 변수 칸 +0(ctx.vars_at): 위 니블 갑옷, 아래 니블 칼 납품 수(FC $628F)
GAVE_SWORD, GAVE_ARMOR = 1, 2  # +1·+2: 이번에 받은 칼·갑옷 수(메시지 숫자)


def _al(a):
    return bytes((a & 0xFF, a >> 8 & 0xFF, a >> 16))


def _flag_addr(flag):
    return 0x7E2190 + flag[0]


# ---- 메시지 ----

def _mark(*pieces):
    """메시지 코드 목록의 ① 자리에 숫자({N} 1004, $F5~$F7)를 넣는다."""
    out = []
    for piece in pieces:
        if not isinstance(piece, str) or '①' not in piece:
            out.append(piece)
            continue
        head, *rest = piece.split('①')
        if head:
            out.append(head)
        for part in rest:
            out.append(0x1004)
            if part:
                out.append(part)
    return out


def _join(*messages):
    """메시지 여럿을 한 메시지로(쪽 넘김으로 잇는다)."""
    out = []
    for m in messages:
        out += m[:-1] + [ch1.PAGE]
    return out[:-1] + [ch1.END]


MESSAGES = {
    # 엔돌 왕(FC 대화 072)
    'king_first': say('먼 길을 와서/나에게 문안을 오다니/수고가 많구나!',
                      '호오, 이곳 엔돌에/가게를 낼 허락이/필요하다고 하는가!'),                      # 0886
    'king_first_yes': say('그대의 소원은/잘 알았노라./생각해 두겠다!/자, 물러가거라.'),              # 0887
    'king_first_no': say('그것참 다행이로다!/그 허락을 청하는/자가 많아서 나도/곤란하던 참이니라.'),  # 0888
    'king_wait': say('내 편지를/본몰 왕에게!/부디 잘 부탁하노라.', '지금은 사람끼리/다투고 있을/때가 아니니라.',
                     '만약 그대의 활약으로/전쟁을 막을 수/있다면 가게를 내는/것도 허락하겠노라!'),           # 0889
    'king_allow': say('오오! 톨네코!/잘 돌아왔도다!', '이미 본몰에서/소식을 받았느니라!',
                      '모든 것이/그대의 활약 덕분!/약속대로 가게를/내는 것을 허락하마!'),                   # 088A
    'king_go': say('톨네코여!/앞으로도 세상과/사람을 위해 장사에/힘쓰도록 하여라.',
                   '그리고 만약/가게를 냈거든/나에게도 알리도록/하여라.'),                                   # 088B
    'king_order': say('오오! 톨네코!/드디어 가게를/냈다고 들었다.', '내 축하의 뜻이니라!/당장 그대에게/주문을 하마!',
                      '성 병사들의/무기와 방어구를/사 모아 아래층/사람에게 바쳐라.',
                      '주문은/강철 검 7자루,/철 갑옷 7벌이니라!'),                                           # 088C
    'king_done': say('병사들의 무기와/방어구 조달,/참으로 수고가/많았느니라!',
                     '그런데 그대도/천공의 검의 소문을/들은 적이/있을 테지.',
                     '어떤 바위라도/부수는 최강의/검이라고 하더구나.', '꼭 손에 넣고/싶은 것이로다…….'),     # 088D
    # 가게 주인(FC 대화 04D)
    'seller_old': say('아래 가게는/쉬느냐고?', '나도 이제 나이가/들어서 말이야.',
                      '가게를 팔아/그 돈으로 은퇴라도/하고 싶은데…….'),                                      # 063B
    'seller_wish': say('임금님께 장사/허락을 받았고/게다가 가게를 갖고/싶은 사람은 없으려나…….'),            # 0861
    'seller_offer': say('어떤가./35000골드면 되니/이 가게를/사지 않겠나?'),                                  # 0862
    'seller_pity': say('그런가……./아쉽구먼…….'),                                                            # 0863
    'seller_poor': say('하지만 돈을/갖고 있지 않잖나./늙은이를 놀리지/말게나.'),                             # 0864
    'seller_sold': say('오오! 사 주겠나!?/오늘부터 이 가게는/자네 것일세!'),                                 # 0865
    'family': narrate('이리하여 톨네코는/마침내 자기 가게를/손에 넣고 가족을/불러들였다.'),                   # 035B
    'nene_shop': pages('네네', '어머 여보, 멋져요!/이게 우리 가게군요./꼭 꿈만 같아요!',
                       '오늘부터 나도/열심히 일할게요!', '둘이서 일해서/이 가게를 세계 제일의/가게로 만들어요!',
                       '여보……./사랑해요……. 쪽.'),                                                          # 035C
    # 아들(FC 대화 08B)
    'son_cheer': say('와아, 아빠 최고야!/드디어 자기 가게를/가졌구나!/와아 와아!'),                          # 067B
    'son_home': say('어서 와요!/응. 나 착하게/있었어.', '나 커서 아빠처럼/돈을 벌어서/아빠랑 엄마/편하게 해 줄게!'),  # 0554
    # 네네(FC 대화 075)
    'nene_rest': pages('네네', '오늘은 벌써/피곤해요? 그럼/조금 이르지만/이제 쉴래요?'),                     # 0866
    'nene_shopkeep': pages('네네', '그럼 나는 가게를/볼 테니까 당신은/여러 물건을/사들여 와요.',
                           '이 테이블 건너편에서/말을 걸어 주면/물건을 가게에/내놓을게요.'),                 # 0867
    'nene_late': pages('네네', '어서 와요./이렇게 늦게까지/정말 수고/많았어요.'),                             # 0811
    'nene_night': pages('네네', '자, 푹 쉬세요./잘 자요, 여보…….'),                                          # 080C
    'nene_morning': pages('네네', '좋은 아침이에요,/여보. 벌써/아침이에요.'),                                 # 080D
    'nene_bento': pages('네네', '자, 여기 도시락./오늘도 힘내고 와요.'),                                      # 080E
    'nene_notice': pages('네네', '여보, 어서 와요!/방금 소식이 왔는데/동굴이 뚫렸대요!',
                         '하지만 나는/무슨 말인지/모르겠어서…….', '설마 당신……./또 여행을 떠날/생각이에요?'),  # 08A0
    'nene_quiet': pages('네네', '알았어요./이제 아무 말도/안 할게요.'),                                       # 08A2
    'nene_lie': pages('네네', '괜찮아요./그런 거짓말로/나를 달래지/않아도…….',
                      '나도 천공의 검/소문을 들었어요./그걸 찾을/생각이군요…….'),                            # 08A4
    'nene_farewell': pages('네네', '당신은 언제나/꿈이 없으면/살 수 없는/사람…….',
                           '그런 당신이라서/나도 좋아하게/된 거겠죠.', '다녀와요, 여보!/언제까지나/기다릴게요!'),  # 08A3
    # 성 아래층 납품(FC 대화 03F)·안내(03E)
    'deliver_idle': say('호오, 그대는/무기상인가? 요즘은/여러 강한 무기도/있다더군.',
                        '하지만 이 성에서는/병사들이 아직도/구리 검을 쓰고/있지. 한심한 일이야…….'),          # 0871
    'guide_idle': say('임금님도 이것저것/생각할 일이 많아/무기까지는 신경이/못 미치시는 게지.'),              # 0872
    'guide_order': say('전부 바치고 나면/60000골드를/치러 주겠네.',
                       '어느 마을에서/사 와도 좋으니/아무튼 힘내서/모아 오시게.'),                            # 087D
    'guide_done': say('호호호./꽤 큰돈을/손에 넣었구먼.', '그 돈을 장래를/위해 쓰시게.'),                    # 087E
    'deliver_ask': say('임금님께 부탁받아/병사들의 무기와/방어구를 바치러/왔는가?'),                          # 0873
    'deliver_take': say('그럼 당장/강철 검과 철 갑옷을/받도록 하지!'),                                       # 0874
    'deliver_swords': _mark(*say('강철 검 ①자루!')),                                                       # 0875
    'deliver_armors': _mark(*say('철 갑옷 ①벌!')),                                                         # 0876
    'deliver_got': say('분명히 받았네!'),                                                                    # 0877
    'deliver_none': say('뭐라고!/아직 안 가져왔단/말인가!?'),                                                # 0878
    'deliver_left': say('주문한 것은/앞으로…….'),                                                           # 0879
    # 남은 수(0879 뒤 0875·0876). 받은 수와 끝 코드가 달라(뒤에 대화 호출이 옴) 메시지를 따로 둔다
    'left_swords': _mark(*say('강철 검 ①자루!')),
    'left_armors': _mark(*say('철 갑옷 ①벌!')),
    'deliver_more': say('힘내서/모아 오도록 하게.'),                                                         # 087A
    'deliver_full': _join(say('좋아! 이것으로/전부 갖춰졌네!/약속대로 대금을/치르겠네!'),
                          narrate('톨네코는/60000골드를/손에 넣었다!')),                                    # 087B
    'deliver_thanks': say('수고했네!/앞으로도 더욱/장사에 힘쓰도록/하게.'),                                  # 087C
    # 수집가(FC 대화 04C)
    'collector_wish': say('저는 오래된 물건을/모으는 것이/취미랍니다.',
                          '소문으로는 어딘가에/은의 여신상이/잠들어 있다고/들었지요.',
                          '아이고, 얼마를/내더라도 손에/넣고 싶군요…….'),                                   # 0869·086A
    'collector_offer': say('아니! 거기 가지고/있는 건 혹시/은의 여신상!?',
                           '20000…… 아니!/25000골드를/내겠소! 팔아/주지 않겠소?'),                        # 086B
    'collector_bought': say('오오! 고맙소!/분명히 받았소!'),                                                # 086C
    'collector_no': say('으음, 안 되는가……./하지만 혹시 마음이/바뀌면 언제든지/팔러 와 주시오!'),          # 086D
    'collector_admire': say('아이고, 이 여신상은/언제 봐도/넋을 잃겠구려.',
                            '그런데 소문으로는/그 옛날 천공의/검이라는 것이/있었다더군요.',
                            '아이고, 얼마를/내더라도 손에/넣고 싶군요…….'),                                 # 086E·086A
    # 여신상 동굴 단추(FC 03B3)
    'button': narrate('단추가 있다./눌러 보겠습니까?'),
}
MESSAGES.update(merc.MESSAGES)
TALKS = ('king', 'seller', 'son', 'nene', 'deliver', 'guide', 'collector', 'button') + merc.TALKS
CALLS = {'pay_shop': ('pay', SHOP_PRICE), 'earn_statue': ('earn', STATUE_PRICE), 'take_statue': ('take', STATUE),
         'earn_delivery': ('earn', DELIVERY_PAY), 'move_in': ('move_in', 0), 'sleep': ('sleep', 0),
         'deliver': ('deliver', 0), 'count': ('deliver', 1),
         **merc.CALLS, 'show_swords': ('show', GAVE_SWORD), 'show_armors': ('show', GAVE_ARMOR),
         'left_swords': ('left', 0), 'left_armors': ('left', 4)}


# ---- 네이티브 ----

def _asm():
    from dq4ch2endor import Asm
    return Asm()


def _event_bytes(tokens):
    return b''.join(bytes((0x60, t[1] & 0xFF, t[1] >> 8)) if isinstance(t, tuple) else t for t in tokens)


def _warp(mp, at):
    g, n = (int(v, 16) for v in mp.split('/'))
    return bytes((0x90, g, n, *at, 0x01, 0x80))


def _morning():
    """이벤트 A0: 필드 시간을 아침으로(FC 1C 이벤트 09·잠의 $62ED = 00)."""
    from dq4ch2endor import sta
    return ENTER + bytes((0xC2, 0x20, 0xA9, ch2.MORNING & 0xFF, ch2.MORNING >> 8)) + sta(ch2.TIME_AT) + \
        bytes((0xE2, 0x20)) + LEAVE


def _rest(next_day):
    """이벤트 A0(잠): 걷는 일행 가운데 쓰러지지 않은 사람의 HP·MP 를 채우고 아침으로. next_day 가 있으면(공용 날수
    장치) 부른다."""
    from dq4ch2endor import BEQ, BCC, sta
    a = _asm()(ENTER, 0xC2, 0x30, 0xA2, 0x00, 0x00)
    a.label('rec')(0xBF, *_al(ch2.PARTY_AT + 0x01), 0x29, 0x80, 0x00).br(BEQ, 'skip')
    a(0xBF, *_al(ch2.PARTY_AT + 0x0E), 0x9F, *_al(ch2.PARTY_AT + 0x02))
    a(0xBF, *_al(ch2.PARTY_AT + 0x10), 0x9F, *_al(ch2.PARTY_AT + 0x04))
    a.label('skip')(0x8A, 0x18, 0x69, ch3.RECORD, 0x00, 0xAA, 0xE0, ch3.RECORD * ch3.PARTY_MAX, 0x00).br(BCC, 'rec')
    a(0xA9, ch2.MORNING & 0xFF, ch2.MORNING >> 8, sta(ch2.TIME_AT), 0xE2, 0x20)
    if next_day is not None:
        a(0x22, *_al(next_day))
    return a.bytes() + LEAVE


def _bento():
    """이벤트 A0(깬 뒤): 일행 기록 0 에 도시락이 없고 빈 물건 칸이 있으면 첫 빈 칸에 넣는다(FC 15:$9E82 → 15:$A794·$A79F)."""
    from dq4ch2endor import BCC, BEQ, BRA
    items = ch3.PARTY_ITEMS
    a = _asm()(ENTER, 0xE2, 0x30, 0xA2, 0x00)
    a.label('has')(0xBF, *_al(items), 0xC9, BENTO).br(BEQ, 'end')(0xE8, 0xE0, ch3.ITEM_SLOTS).br(BCC, 'has')
    a(0xA2, 0x00).label('free')(0xBF, *_al(items), 0xC9, 0xFF).br(BEQ, 'put')
    a(0xE8, 0xE0, ch3.ITEM_SLOTS).br(BCC, 'free').br(BRA, 'end')
    a.label('put')(0xA9, BENTO, 0x9F, *_al(items))
    a.label('end')
    return a.bytes() + LEAVE


def _move_in_tokens(ctx, at):
    """가게를 산 뒤(FC 1C 이벤트 09): 아침으로 04/00 의 네네 옆에 다시 서서 035B·035C."""
    m = ctx.msg or {'family': 0, 'nene_shop': 0}
    return [bytes((0xA0, *_al(at['morning']))) + _warp(*NENE_SIDE), ('msg', m['family']), ('msg', m['nene_shop']),
            b'\xff']


def _sleep_tokens(ctx, at):
    """네네와 잠(FC 15:$9E56): 채우기·아침 → 04/00 의 네네 옆 → 080D·080E → 도시락."""
    m = ctx.msg or {'nene_morning': 0, 'nene_bento': 0}
    return [bytes((0xA0, *_al(at['rest']))) + _warp(*NENE_SIDE), ('msg', m['nene_morning']), ('msg', m['nene_bento']),
            bytes((0xA0, *_al(at['bento']), 0xFF))]


def _show():
    """대화 호출: $F5~$F7 = 변수 칸 +인자(메시지 {N})."""
    from dq4ch2endor import lda
    return lambda ctx: (ENTER + bytes((0xE2, 0x30)) + lda(ch3.ARG) + bytes((0xAA, 0xBF)) + _al(ctx.vars_at) +
                        bytes((0x85, 0xF5, 0x64, 0xF6, 0x64, 0xF7)) + LEAVE)


def _left():
    """대화 호출: $F5~$F7 = 7 − 납품 수의 니블(인자 0 칼, 4 갑옷)."""
    from dq4ch2endor import BEQ, lda
    def make(ctx):
        a = _asm()(ENTER, 0xE2, 0x30, lda(ch3.ARG)).br(BEQ, 'low')(lda(ctx.vars_at + VARS), 0x4A, 0x4A, 0x4A, 0x4A)
        a.br(0x80, 'have').label('low')(lda(ctx.vars_at + VARS)).label('have')
        a(0x29, 0x0F, 0x49, 0xFF, 0x18, 0x69, ORDERED + 1, 0x85, 0xF5, 0x64, 0xF6, 0x64, 0xF7)
        return a.bytes() + LEAVE
    return make


def _deliver(ctx):
    """대화 호출. 인자 0(납품 「예」): 톨네코 소지품에서 철 갑옷, 그다음 강철 검을 주문 수 7 이 찰 때까지 빼고
    (넘는 몫은 소지품에 남음, 맡긴 물건은 세지 않음. FC 15:$A212 실측) 납품 수 니블에 더한다. 이번에 받은 수를 변수 칸
    +1·+2 에, 받았으면 GAVE_SWORDS·GAVE_ARMORS, 둘 다 7 이면 FULL. 인자 1(「아니요」)은 빼지 않는다. 끝에 아직 남은
    종류마다 LEFT_SWORDS·LEFT_ARMORS(FC 는 남은 수가 0 인 줄을 띄우지 않음, 15:$A159·$A196)."""
    from dq4ch2endor import BCC, BCS, BEQ, lda, sta, take_item
    vars_at = ctx.vars_at
    a = _asm()(ENTER, 0xE2, 0x30)
    clear = FULL[1] | GAVE_SWORDS[1] | GAVE_ARMORS[1] | LEFT_SWORDS[1] | LEFT_ARMORS[1]
    a(lda(_flag_addr(FULL)), 0x29, ~clear & 0xFF, sta(_flag_addr(FULL)))
    a(0xA9, 0x00, sta(vars_at + GAVE_SWORD), sta(vars_at + GAVE_ARMOR))
    a(lda(ch3.ARG)).br(BEQ, 'give').brl('left').label('give')
    for k, (item, gave, flag, shift) in enumerate(((IRON_ARMOR, GAVE_ARMOR, GAVE_ARMORS, 4),
                                                    (STEEL_SWORD, GAVE_SWORD, GAVE_SWORDS, 0))):
        a.label(f'k{k}')(0xE2, 0x30, lda(vars_at + VARS))
        if shift:
            a(0x4A, 0x4A, 0x4A, 0x4A)
        a(0x29, 0x0F, 0xC9, ORDERED).br(BCC, f'more{k}').brl(f'done{k}').label(f'more{k}')
        # 3장 일행에서 물건을 가진 것은 톨네코(기록 0)뿐이다(용병 기록은 물건이 없음)
        take_item(a, ch3.PARTY_ITEMS, ch3.EQUIP, item, f'done{k}', p=f't{k}')
        a(0xE2, 0x30, lda(vars_at + VARS), 0x18, 0x69, 1 << shift, sta(vars_at + VARS))
        a(lda(vars_at + gave), 0x1A, sta(vars_at + gave))
        a(lda(_flag_addr(flag)), 0x09, flag[1], sta(_flag_addr(flag))).brl(f'k{k}')
        a.label(f'done{k}')
    a.label('left')(0xE2, 0x30)
    for flag, shift in ((LEFT_SWORDS, 0), (LEFT_ARMORS, 4)):
        a(lda(vars_at + VARS), *([0x4A] * shift), 0x29, 0x0F, 0xC9, ORDERED).br(BCS, f'full{shift}')
        a(lda(_flag_addr(flag)), 0x09, flag[1], sta(_flag_addr(flag))).label(f'full{shift}')
    a(lda(vars_at + VARS), 0xC9, ORDERED << 4 | ORDERED).br(0xD0, 'end')
    a(lda(_flag_addr(FULL)), 0x09, FULL[1], sta(_flag_addr(FULL)))
    a.label('end')
    return a.bytes() + LEAVE


def _hero_rect(x, y):
    """FC 칸 → 주인공 셀 사각형(주인공은 FC 칸 (x, y) 에서 (2x 또는 2x+1, 2y+1 또는 2y+2) 에 선다)."""
    return (2 * x, 2 * y + 1, 2 * x + 1, 2 * y + 2)


def _map(name):
    return int(name.split('/')[1], 16)


# 상자 열림 비트(dq4ch3safe 와 같은 셈): 25:FAB0 이 chest_maps(25:FAB5 의 즉값 뱅크, 25:FAC4 의 abs)를 (그룹, 맵, 개수)
# 3바이트씩 훑어 앞 맵들의 개수를 더한 것이 그 맵 첫 상자 번호 n 이고, 비트는 7E:2210 + n/8 의 25:FAE9[n & 7]
CHEST_BANK, CHEST_TABLE, CHEST_MASKS, CHEST_BITS = 0x25FAB5, 0x25FAC4, 0x25FAE9, 0x7E2210


def _find(a, key, p):
    """M·X 16 에서: 상자 표를 훑어 (그룹, 맵) = key 의 첫 상자 번호를 스택에 넣고(PHY) A = 개수. 표에 없으면 0, 0."""
    from dq4ch2endor import BEQ, BRA
    a(0x8B, 0xAF, *_al(CHEST_TABLE), 0xAA, 0xE2, 0x20, 0xAF, *_al(CHEST_BANK), 0x48, 0xAB, 0xC2, 0x20, 0xA0, 0x00, 0x00)
    a.label(f'{p}row')(0xBD, 0x00, 0x00, 0xC9, *key.to_bytes(2, 'little')).br(BEQ, f'{p}hit')
    a(0xC9, 0xFF, 0xFF).br(BEQ, f'{p}miss')
    a(0xBD, 0x02, 0x00, 0x29, 0xFF, 0x00, 0x5A, 0x18, 0x63, 0x01, 0x7A, 0xA8, 0xE8, 0xE8, 0xE8).br(BRA, f'{p}row')
    a.label(f'{p}miss')(0xA9, 0x00, 0x00, 0xA8).br(BRA, f'{p}done')
    a.label(f'{p}hit')(0xBD, 0x02, 0x00, 0x29, 0xFF, 0x00)
    a.label(f'{p}done')(0xAB, 0x5A)


# M·X 16, A = 상자 번호 → X = 7E:2210 에서의 바이트, A(M8) = 마스크
_BIT = bytes((0x48, 0x4A, 0x4A, 0x4A, 0xAA, 0x68, 0x29, 0x07, 0x00, 0xDA, 0xAA, 0xE2, 0x20, 0xBF, *_al(CHEST_MASKS), 0xFA))


def _press(ctx):
    """이벤트 A0(단추를 누름): BUTTON 을 켜고, CHEST_PAIRS 마다 앞 맵의 열린 상자 비트를 뒤 맵의 같은 차례 상자에 켠다."""
    from dq4ch2endor import BEQ, lda, sta
    a = _asm()(ENTER, lda(_flag_addr(BUTTON)), 0x09, BUTTON[1], sta(_flag_addr(BUTTON)), 0xC2, 0x30)
    for k, (src, dst) in enumerate(CHEST_PAIRS):
        _find(a, CAVE_GROUP | _map(src) << 8, f's{k}')
        a(0x48)
        _find(a, CAVE_GROUP | _map(dst) << 8, f'd{k}')
        # 스택: +1 dst 첫 번호, +3 남은 개수, +5 src 첫 번호
        a.label(f'loop{k}')(0xA3, 0x03).br(BEQ, f'next{k}')
        a(0x3A, 0x83, 0x03, 0x18, 0x63, 0x05, _BIT, 0x3F, *_al(CHEST_BITS)).br(BEQ, f'skip{k}')
        a(0xC2, 0x20, 0xA3, 0x03, 0x18, 0x63, 0x01, _BIT, 0x1F, *_al(CHEST_BITS), 0x9F, *_al(CHEST_BITS))
        a.label(f'skip{k}')(0xC2, 0x30).brl(f'loop{k}')
        a.label(f'next{k}')(0x68, 0x68, 0x68)
    a(0xE2, 0x20)
    return a.bytes() + LEAVE


def _button_tokens(at):
    """단추를 누르면(FC 1D 이벤트 5E 의 「はい」): 비트를 옮기고 물이 빠진 40/02 의 같은 칸으로."""
    return [bytes((0xA0, *_al(at['press']))) + _warp(*BUTTON_LAND) + b'\xff']


def _exit(ctx):
    """출구 훅(2A:F7AB, dq4ch3safe 의 출구 훅 뒤에 잇는다. M8·X8, DB 2A): 금고 동굴 갈래를 거친 도착 출구 번호(A)가
    0 이고 그룹 48·맵 03 이며 BUTTON 이면 맵을 04 로(FC 08:$B3C0, 40/01 첫 출구 → 40/02)."""
    from dq4ch2endor import BEQ, BNE, lda
    a = _asm()(0x22, *_al(_safe_exit(ctx)), 0x48, 0xC9, 0x00).br(BNE, 'out')
    a(0xA5, 0xBC, 0xC9, CAVE_GROUP).br(BNE, 'out')(0xA5, 0xBD, 0xC9, _map(CAVE_WET)).br(BNE, 'out')
    a(lda(_flag_addr(BUTTON)), 0x29, BUTTON[1]).br(BEQ, 'out')(0xA9, _map(CAVE_DRY), 0x85, 0xBD)
    a.label('out')(0x68, 0x6B)
    return a.bytes()


HERO_X, HERO_Y = 0x7E3020, 0x7E3080


def _inside(rect, away=False):
    """인물 명령 05: 주인공 셀이 rect 안이면(away 면 밖이면) A = 0, 아니면 1(인물 표 X·Y 의 bit7 은 지움)."""
    from dq4ch2endor import BCC, BCS, BRA, lda
    x0, y0, x1, y1 = rect
    out = 'near' if away else 'far'
    a = _asm()(0x08, 0xE2, 0x30)
    for table, lo, hi in ((HERO_X, x0, x1), (HERO_Y, y0, y1)):
        a(lda(table), 0x29, 0x7F, 0xC9, lo).br(BCC, out)(0xC9, hi + 1).br(BCS, out)
    a.br(BRA, 'far' if away else 'near')
    a.label('near')(0xC2, 0x30, 0xA9, 0x00, 0x00, 0x28, 0x6B)
    a.label('far')(0xC2, 0x30, 0xA9, 0x01, 0x00, 0x28, 0x6B)
    return a.bytes()


def _safe_ctx(ctx):
    return next(c for c in ch3.contexts(original=ctx.original) if c.key == 'S')


def _safe_exit(ctx):
    """dq4ch3safe 의 출구 루틴 주소($BD 를 쓰고 A = 도착 출구 번호, RTL)."""
    return _safe_ctx(ctx).at['exit']


ROUTINES = {'morning': lambda ctx: _morning(), 'bento': lambda ctx: _bento(), 'show': _show(), 'left': _left(),
            'deliver': _deliver}


def native(ctx):
    """(바이트, {이름: 주소}). 모두 ctx.code_at 부터 이 모듈 몫 안에 둔다."""
    import dq4prologue
    out = bytearray()
    at = {}

    def put(name, code):
        at[name] = ctx.code_at + len(out)
        out.extend(code)
    for name, make in ROUTINES.items():
        put(name, make(ctx))
    put('rest', _rest(ctx.base.get('next_day')))
    put('move_in_event', _event_bytes(_move_in_tokens(ctx, at)))
    put('move_in', dq4prologue._event_start(at['move_in_event']))
    put('sleep_event', _event_bytes(_sleep_tokens(ctx, at)))
    put('sleep', dq4prologue._event_start(at['sleep_event']))
    rect = _hero_rect(*BUTTON_FC)
    put('at_button', _inside(rect))
    put('away_button', _inside(rect, away=True))
    put('press', _press(ctx))
    put('button_event', _event_bytes(_button_tokens(at)))
    put('push', dq4prologue._event_start(at['button_event']))
    put('exit', _exit(ctx))
    merc.natives(ctx, put, at, _event_bytes)
    return bytes(out), at


# dq4brkscan: PHP 로 시작하지 않는 진입점. exit 는 P 를 부른 쪽이 PLP 로 되돌리는 훅, *_event 는 이벤트 스크립트 자료
CODE_ENTRIES = ('exit',) + merc.CODE_ENTRIES
DATA_ENTRIES = ('move_in_event', 'sleep_event', 'button_event') + merc.DATA_ENTRIES


def events(ctx):
    return [_move_in_tokens(ctx, ctx.at), _sleep_tokens(ctx, ctx.at), _button_tokens(ctx.at)] + merc.events(ctx)


def hooks(ctx):
    """금고 동굴 모듈이 2A:F7AB 에 둔 JSL 의 대상을 이 모듈의 출구 루틴으로 바꾼다(그 루틴이 금고 동굴 루틴을 먼저 부름)."""
    import dq4ch3safe as safe
    old = next(new for site, _, new in safe.hooks(_safe_ctx(ctx)) if site == safe.EXIT_SITE)
    return [(safe.EXIT_SITE, old, bytes((0x22, *_al(ctx.at['exit']))) + old[4:])] + merc.hooks(ctx)


# 빌린 인물 스크립트(DQ5 01/09 대체 목록 10:8E0D, dq4ch3slots E 칸 1): 단추를 묻는 보이지 않는 인물
SCRIPT_LIST = '10:8E0D'
SCRIPTS = {'button': ('10:8E1B', 1), 'scott': ('10:8E41', 2), 'lawrence': ('10:8E5A', 3)}


def _cmd(op, *args, **kw):
    return {"op": op, "args": list(args), **kw}


def _off(flag):
    return _cmd('11', flag[0], ~flag[1] & 0xFF)


def scripts(ctx):
    """단추: 칸에 서면 묻고, 「예」 면 단추 이벤트, 「아니요」 면 칸을 떠났다가 다시 서야 또 묻는다(dq4ch3safe 의 수문과 같은 꼴)."""
    at = ctx.at
    call = lambda a: _cmd('37', *_al(a))  # noqa: E731
    talk_here = ch2.native()[1]['talk_here']
    button = [_cmd('28'), _cmd('52'), _cmd('05', *_al(at['at_button']), label='wait'), _cmd('37', *_al(talk_here)),
              _cmd('09', 0x80 | ASKED[0], ASKED[1]), _off(ASKED), _cmd('06', *PRESSED, target='push'),
              _cmd('05', *_al(at['away_button'])), _cmd('03', target='wait'),
              {**_off(PRESSED), "label": 'push'}, _cmd('3F'), call(at['push']), _cmd('16')]
    out = [{"address": SCRIPTS['button'][0], "commands": button}]
    # 용병: 고용했으면 숨는다(FC 장소별 손질 1C:$A3B9·$A51E 가 고용한 용병을 숨김). 이 방문에 고용하면 그 자리에서 숨는다.
    # 스콧은 FC 처럼 처음 자리 둘레를 걷는다(옮긴 걷는 사람 틀 05:8857 칸 6 의 19 03 03)
    for who, walk in (('scott', [_cmd('19', 0x03, 0x03)]), ('lawrence', [])):
        f = merc.FLAGS[who]
        out.append({"address": SCRIPTS[who][0], "commands": [
            _cmd('06', *f, target='gone'), *walk, _cmd('09', 0x80 | f[0], f[1]),
            {**_cmd('28'), "label": 'gone'}, _cmd('16')]})
    return out


# ---- 대화 ----

YES = {"code": "05"}
DAY = {"code": "14"}


def talk_scripts(ctx):
    say_, call, flag, on, when = ctx.say, ctx.call, ctx.flag, ctx.flag_on, ctx.when
    first = [say_('king_first'), when(YES, [say_('king_first_yes')], [say_('king_first_no')])]
    king = when(flag(DELIVERED), [say_('king_done')], [when(flag(SHOP), [say_('king_order'), on(ORDER)], [
        when(flag(ALLOWED), [say_('king_go')], [
            when(flag(LETTER2), [say_('king_allow'), on(ALLOWED)], [
                when(flag(LETTER1), [say_('king_wait')], first)])])])])
    buy = [call('pay_shop'), when(ctx.paid(), [say_('seller_sold'), on(SHOP), call('move_in')], [say_('seller_poor')])]
    seller = [say_('seller_old'), when(flag(ALLOWED), [say_('seller_offer'), when(YES, buy, [say_('seller_pity')])],
                                       [say_('seller_wish')])]
    son = when(DAY, [on(SON_CHEER), say_('son_cheer')], [say_('son_home')])
    sleep = [say_('nene_night'), call('sleep')]
    nene = when(flag(NOTICE), [say_('nene_notice'), when(YES, [say_('nene_quiet')], [say_('nene_lie')]),
                               say_('nene_farewell'), on(OPENED)], [
        when(DAY, [say_('nene_rest'), when(YES, sleep, [say_('nene_shopkeep')])], [say_('nene_late'), *sleep])])
    # FC 15:$A118 실측: 「예」 면 받을 것이 없어도 0874 부터. 받은 수·남은 수 줄은 그 종류가 0 이면 빠진다
    tally = [say_('deliver_left'), when(flag(LEFT_SWORDS), [call('left_swords'), say_('left_swords')]),
             when(flag(LEFT_ARMORS), [call('left_armors'), say_('left_armors')]), say_('deliver_more')]
    got = [when(flag(GAVE_SWORDS), [call('show_swords'), say_('deliver_swords')]),
           when(flag(GAVE_ARMORS), [call('show_armors'), say_('deliver_armors')]),
           when(flag(GAVE_SWORDS), [say_('deliver_got')],
                [when(flag(GAVE_ARMORS), [say_('deliver_got')], [say_('deliver_none')])])]
    done = when(flag(FULL), [say_('deliver_full'), call('earn_delivery'), on(DELIVERED), say_('deliver_thanks')],
                tally)
    deliver = when(flag(DELIVERED), [say_('deliver_thanks')], [
        when(flag(ORDER), [say_('deliver_ask'), when(YES, [say_('deliver_take'), call('deliver'), *got, done],
                                                     [call('count'), *tally])],
             [say_('deliver_idle')])])
    guide = when(flag(DELIVERED), [say_('guide_done')],
                 [when(flag(ORDER), [say_('guide_order')], [say_('guide_idle')])])
    sell = [say_('collector_bought'), call('take_statue'), call('earn_statue'), on(SOLD)]
    collector = when(flag(SOLD), [say_('collector_admire')], [
        when(ctx.has(STATUE), [say_('collector_offer'), when(YES, sell, [say_('collector_no')])],
             [say_('collector_wish')])])
    asked = on(ASKED)
    button = [say_('button'), when(YES, [on(PRESSED), asked], [asked])]
    bodies = {'king': [king], 'seller': seller, 'son': [son], 'nene': [nene], 'deliver': [deliver],
              'guide': [guide], 'collector': [collector], 'button': button,
              **dict(zip(merc.TALKS, merc.talk_scripts(ctx)))}
    return [bodies[name] for name in TALKS]


# ---- 인물 목록 ----

def _copy(lists, mp, talks, drop=(), sources=None):
    """옮긴 목록 lists[mp] 를 베껴 talks({(낮·밤, FC 칸): 대화})의 사람 대화를 바꾸고 drop 의 사람을 뺀다. 바꿀·뺄
    사람이 없으면 멈춘다(기본 목록은 고치지 않는다: 2장 엔돌도 같은 목록을 쓴다)."""
    want = {(t, cell(*fc)): talk for t, fc, talk in talks}
    gone = {(t, cell(*fc)) for t, fc in drop}
    hit, entries = set(), []
    for e in lists[mp]["entries"]:
        key = (e["time"], (e["fields"]["x"], e["fields"]["y"]))
        if key in gone:
            hit.add(key)
            continue
        if key in want:
            hit.add(key)
            e = {**e, "fields": {**e["fields"], "talk": want[key]}}
            if sources and key in sources:
                # 빌린 스크립트는 이동 간격이 0 이면 돌지 않는다(dq4ch2event._invisible)
                e = {**e, "from": sources[key], "fields": {**e["fields"], "interval": max(1, e["fields"]["interval"])}}
        entries.append(e)
    missing = (set(want) | gone) - hit
    if missing:
        raise SystemExit(f'엔돌 {mp}: 대화를 바꾸거나 뺄 사람이 없음 {sorted(missing)}')
    return entries


def _who(people, mp):
    return [(t, fc) for m, t, fc in people if m == mp]


def _monica(ctx):
    """[(낮·밤, FC 칸, 대화)]: 본몰 모듈이 있으면 3장 목록의 모니카(FC 04/06 (0F,0A))에 그 모듈의 편지 대화. 기본 목록은
    2장에도 쓰여 거기서 바꾸지 않는다."""
    if 'dq4ch3bonmalmo' not in ch3.EVENTS:
        return []
    import dq4ch3bonmalmo as bm
    # 3장 첫 대화 번호: 이 모듈 첫 대화에서 앞 모듈들의 대화 수를 뺀다(번호는 등록 차례로 이어 매김)
    before = 0
    for key, mod in ch3.modules():
        if key == ctx.key:
            break
        before += len(getattr(mod, 'TALKS', ()))
    return [('day', (0x0F, 0x0A), bm.monica_talk(ctx.talk[TALKS[0]] - before))]


def npc_lists(lists, ctx):
    """3장 동안의 엔돌 맵을 기본 목록을 베껴 대화를 바꾼 목록으로 덮는다(CHAPTER3). 40/00·40/08 은 가게를 산 뒤(SHOP)
    목록이 따로다. 여신상 동굴 40/01(48/03)에 단추를 묻는 보이지 않는 인물을 더한다."""
    if TOWN not in lists:
        return [], []           # 인물 없이 옮긴 목록(dq4npcport.port 의 with_people=False)
    t = ctx.talk
    src = lambda who: {"list": SCRIPT_LIST, "index": SCRIPTS[who][1]}  # noqa: E731
    sources = {(SCOTT[1], cell(*SCOTT[2])): src('scott'), **{(tm, cell(*fc)): src('lawrence') for _, tm, fc in LAWRENCE}}
    talks = {TOWN: [(tm, fc, t['nene']) for tm, fc in _who(NENE, TOWN)] + [(SCOTT[1], SCOTT[2], t['scott'])],
             BARD_HALL: [(tm, fc, t['lawrence']) for _, tm, fc in LAWRENCE],
             CASTLE_HALL: [(DELIVER[1], DELIVER[2], t['deliver']), (GUIDE[1], GUIDE[2], t['guide'])],
             THRONE: [(KING[1], KING[2], t['king'])] + _monica(ctx),
             SHOP_UP: [(tm, fc, t['seller']) for tm, fc in _who(SELLER, SHOP_UP)] +
                      [(tm, fc, t['son']) for tm, fc in _who(SON, SHOP_UP)] +
                      [(tm, fc, t['nene']) for tm, fc in _who(NENE, SHOP_UP)],
             COLLECTOR: [(tm, fc, t['collector']) for _, tm, fc in COLLECTORS]}
    new, over = [], []

    def on(m, flag, name):
        return {"map": m, "flag": flag[0], "when": "on", "mask": flag[1], "list": f"new:{name}"}
    for mp in (TOWN, SHOP_UP):
        name = f'ch3_endor_{mp.replace("/", "")}_shop'
        new.append({"name": name, "entries": _copy(lists, mp, talks[mp], _who(AFTER_SHOP, mp), sources)})
        over.append(on(mp, SHOP, name))
    for mp in (TOWN, CASTLE_HALL, THRONE, SHOP_UP, COLLECTOR, BARD_HALL):
        name = f'ch3_endor_{mp.replace("/", "")}'
        new.append({"name": name, "entries": _copy(lists, mp, talks[mp], _who(BEFORE_SHOP + BARD_HIDDEN, mp),
                                                   sources)})
        over.append(on(mp, ch3.CHAPTER3, name))
    lists[CAVE_WET]["entries"] += ch2._invisible({"list": SCRIPT_LIST, "index": SCRIPTS['button'][1]}, t['button'])
    return new, over


def absent(ctx):
    """{(맵, DQ5 셀 x, y, 밤)}: 3장 처음(가게를 사기 전)에 없는 네네·아들과 밤의 둘째 로렌스."""
    return {(m, *cell(*fc), t == 'night') for m, t, fc in BEFORE_SHOP + BARD_HIDDEN}


def start_messages(ctx):
    """3장 처음 상태에서 대화를 바꾼 사람의 첫 메시지({(맵, DQ5 셀, 밤): 메시지})."""
    m = ctx.msg
    out = {(KING[0], cell(*KING[2]), False): m['king_first'],
           (DELIVER[0], cell(*DELIVER[2]), False): m['deliver_idle'],
           (GUIDE[0], cell(*GUIDE[2]), False): m['guide_idle']}
    out.update({(mp, cell(*fc), tm == 'night'): m['seller_old'] for mp, tm, fc in SELLER})
    out.update({(mp, cell(*fc), tm == 'night'): m['collector_wish'] for mp, tm, fc in COLLECTORS})
    out.update({(mp, cell(*fc), tm == 'night'): m['lawrence_offer'] for mp, tm, fc in LAWRENCE})
    return out
