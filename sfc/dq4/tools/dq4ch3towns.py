"""DQ4 3장 마을 사람(dq4ch3slots 'W'): 3장 그룹(레이크나바 3E·본몰 3F·엔돌 40·굴 47·여우 마을과 여신상 동굴 48)에서
다른 사건 모듈이 맡지 않은 인물의 한글 대사와, FC 가 사건 flag 로 바꾸는 말.

  옮긴 대사  dq4npcport 가 3장 시작 상태로 FC 대화를 돌려 옮긴 일본어 임시 대사는 PORTED(FC 메시지 묶음 → 한글)로
             같은 메시지 번호에서 덮는다(dq4ch3event.ported_texts → dq4chapter1.messages). 2장 dq4ch2talk 과 같은 방식.
  진행별 말  FC 대화가 flag 로 갈리는 인물은 대화 스크립트(TALKS)의 flag 조건으로 옮긴다. 보는 flag 는 그 사건을
             맡은 모듈의 것(레이크나바 L·본몰 B·엔돌 E)이다.
  엔돌       FC 3장 동안은 $6282&40(2장 끝)이 켜져 있어 04/00·01·02·05·06 이 기본 목록 대신 flag 목록(1C:$869A·
             $868E·$877D·$860D·$87EC)을 쓴다. 옮긴 기본 목록은 2장 대회 중 사람이라, 3장 동안 걸리는 목록(엔돌·본몰
             모듈의 3장 목록, 없으면 이 모듈이 기본 목록을 베낀 것)에서 다른 모듈이 맡지 않은 칸의 사람을 FC 3장 목록대로
             바꾼다. 카지노 04/01 은 3장에 라이안 하나만 서는 닫힌 목록이다.

형식은 sfc/dq4/docs/dq4-chapter3-format.md 「마을 사람」.
"""
import copy
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4chapter1 as ch1  # noqa: E402
import dq4ch2event as ch2  # noqa: E402
import dq4ch3event as ch3  # noqa: E402
from dq4neneshop import _mark  # noqa: E402

say = ch1.say
pages = ch2._speaker_pages

# 이 모듈은 flag 를 켜지 않는다(사건이 아니라 말만 바꿈). 보는 flag 는 사건 모듈의 것이다. 아직 머지되지 않은 모듈의
# flag 는 그 모듈의 예약 바이트(dq4ch3slots)·비트를 여기 적고, test_dq4ch3towns 가 그 모듈이 있으면 같은지 본다
FLAGS = ()
FOXED = (0x73, 0x01)           # 본몰 B: 여우를 쫓음(FC $6280&02)
PRINCE_MET = (0x73, 0x02)      # 본몰 B: 낮에 왕자를 만나 유모에게 쫓겨남(FC $6280&08)
# 본몰 B: 왕자 낮 첫 만남에서 쫓겨남(7E:21A3 bit4, 맵을 옮기면 지워짐). 유모는 그 방문에만 03B1(FC $6289&40 은
# 필드로 나가야 지워지고, 여기서는 3F/01 을 떠나면 — 감옥 3F/00 을 다녀와도 — 지워진다)
NANNY_SCOLDED = (0x13, 0x10)
SON_FREED = (0x73, 0x04)       # 본몰 B: 톰 아들에게 키메라의 날개를 줌(FC $6280&04)
LETTER1 = (0x73, 0x10)         # 본몰 B: 왕자의 편지를 모니카에게 전함(FC $6280&01)
SHOP = (0x75, 0x02)            # 엔돌 E: 가게를 삼(FC $6286&20)
OWNERS = {'dq4ch3bonmalmo': ('FOXED', 'PRINCE_MET', 'NANNY_SCOLDED', 'SON_FREED', 'LETTER1'), 'dq4ch3endor': ('SHOP',)}

YES = {"code": "05"}
DAY = {"code": "14"}


def cell(x, y):
    """FC 칸 → 옮긴 인물 셀(dq4npcport.cell)."""
    return (2 * x, 2 * y + 1)


# ---- 옮긴 대사(FC 메시지 묶음 → 한글) ----

# 묶음은 dq4npcport 가 3장 시작 상태(일행 없음)로 FC 대화를 돌린 것이다. 예/아니오는 「예」 갈래가 이어 붙어 있다
PORTED = {
    # 레이크나바 3E/00(FC 16/00)
    (0x663,): say('멍멍멍!'),
    # FC 대화 0B9 는 일행에 톨네코가 있으면(3장 내내) 0814 를 잇는다. 옮길 때는 일행 없이 돌려 0813 만 나왔다
    (0x813,): say('레이크나바 마을에 어서 오세요!', '어라? 뭐야, 톨네코잖아. 어서 오라고 괜히 인사했네.'),
    (0x662,): say('있잖아, 여관 아저씨가 할 얘기가 있대.'),
    (0x555,): say('세상의 평화를 신께 빌어 주세요.', '세상이 망해 버리면 톨네코 씨도 장사고 뭐고 없잖아요.'),
    (0x664,): say('어머, 무슨 일이야? 우리 집 양반이라면 낮에는 가게에 있으니까 밤에나 와 봐.'),
    # 북쪽 동굴 3E/08(FC 3D/05)
    (0x667,): say('당신도 철 금고를 찾으러 왔구먼?', '내 생각엔 저 굴러오는 바위가 아무래도 수상한데……'),
    # 본몰 감옥 3F/00(FC 05/00). FC 는 말한 뒤 일행을 감옥 밖으로 내보낸다(대화 066 의 호출)
    (0x34A,): say('여기는 감옥이다! 죄수와 이야기하는 것은 허락할 수 없다! 자, 나가시오!'),
    # 본몰 성 3F/01(FC 05/01)
    (0x834,): say('남쪽으로 가면 엔돌이지. 다리가 부서지기 전에 가 본 적이 있다네.',
                  '엔돌에는 가게를 팔고 싶어 하는 노인이 있었지.'),
    (0x835,): say('엔돌은 풍요로운 나라.', '그 나라를 손에 넣는 것이 임금님의 오랜 꿈이었답니다.'),
    (0x828,): say('여기는 방어구 가게인데요, 괴물이 돌아다니고부터 방어구가 팔리고 또 팔려서……',
                  '그래서 물건이 다 떨어졌어요. 죄송해요.'),
    (0x66C,): say('본몰 성에 어서 오세요.'),
    (0x558,): say('왕자님! 왕자님이 안 계세요. 어쩌면 좋아……'),
    (0x556,): say('이런 한밤중에 성에 들어오는 것은 허락할 수 없다!'),
    (0x557,): say('내일 다시 오는 것이 좋을 것이오.'),
    # 엔돌 마을 40/00(FC 04/00). 2장 대회 중 사람(3장 동안은 아래 ENDOR 로 바뀐 칸이 많다)
    (0x637,): say('어서 오세요. 천천히 마시고 가요.'),
    (0x638,): say('으으. 또 졌네. 마누라한테 뭐라고 하지……'),
    (0x63A,): say('저것 봐, 구름이 저렇게 빨리 서쪽으로 흘러가. 무슨 일일까?'),
    (0x636,): say('우리 집 몹쓸 양반은 어디로 간 거람. 정말이지……'),
    (0x500, 0x501): say('임금님을 뵈러 왔나?', '그렇다면 이 문으로 들어가도록.'),
    (0x639,): say('무술 대회를 보려고 많은 사람이 여기 엔돌로 모여들고 있다.'),
    (0x635,): say('있잖아, 알아? 성에서 무술 대회가 열린대.'),
    (0x634,): say('엔돌 성 아랫마을에 어서 오세요.'),
    (0x7EC,): say('순찰도 쉽지 않구먼.'),
    (0x503, 0x504): say('어이, 당신들 북쪽에는 가 봤어?', '다리가 부서져 있었지? 나쁜 짓 하는 녀석이 다 있다니까.'),
    (0x542,): say('아, 별똥별!', '신이시여, 부디 이 나라를 지켜 주세요……'),
    (0x545,): say('아직 안 취했다고. 끅.'),
    (0x546,): say('여기는 엔돌 성 아랫마을이다.'),
    (0x544,): say('일 끝나고 마시는 한 잔은 최고지요.'),
    (0x543,): say('오늘도 무사히 지낸 것을 신께 감사드립니다. 아멘.'),
    # 카지노 40/01(FC 04/01). 3장 동안은 닫혀 아래 ENDOR 의 라이안만 선다
    (0x913,): pages('마냐', '말 걸지 마! 정신 사납잖아!', '잃은 만큼 되찾아서 동생 미네아를 깜짝 놀래 줄 거니까!'),
    (0x506, 0x507): say('어때? 좀 따고 있어?', '좋아, 그럼 세게 나가는 거야. 따고 있을 땐 세게 나가야지!'),
    (0x642,): say('오오! 오늘 번 돈이 몽땅 날아갔어요. 흑흑……'),
    (0x7F6,): say('여기는 포커 테이블입니다. 즐기시겠습니까?'),
    (0x63E,): say('해냈다! 더블업으로 8장이 16장! 이제 못 끊겠어!'),
    (0x63D,): say('카지노에 어서 오세요.', '여기서는 코인만 쓸 수 있어요. 막다른 곳의 계산대에서 코인을 사세요.'),
    (0x640,): say('코인이 모이면 오른쪽 교환소에서 물건으로 바꿀 수 있어요.'),
    (0x641,): say('아무리 따 봤자 코인은 돈으로 돌아오지 않아.', '무리하지 말고 남는 돈으로 즐기는 게 현명하겠지.'),
    (0x63F,): say('오늘은 영 운이 없네.'),
    # 엔돌 성 40/02(FC 04/02)
    (0x645,): say('임금님께서는 이 위에 계십니다.'),
    (0x644,): say('여기는 콜로세움. 무술 대회 회장입니다.'),
    (0x649,): say('여기 임금님은 경솔하셔서 생각한 걸 바로 해 버리신다니까요. 곤란한 일이에요.'),
    (0x648,): say('무술 대회 우승자는 여기 공주님과 결혼할 수 있대요.', '공주님도 불쌍하지……'),
    # FC 는 말한 뒤 일행을 성 밖으로 내보낸다(대화 028 의 호출)
    (0x38E,): say('이런 한밤중에 성에 들어오다니!', '내 눈에 띈 이상 가만있을 수는 없다. 자, 물러가시오!'),
    (0x549,): say('무술 대회는 낮에만 열린다. 다시 오는 것이 좋을 것이오.'),
    (0x54B,): say('대체 몇 명의 전사가 데스피사로에게 죽었는지……',
                  '이래서야 강한 사람을 모아다가 묻어 버리는 거나 다름없어요.'),
    (0x54A,): say('쿨쿨……'),
    # 엔돌 40/04·05·06(FC 04/04·05·06)
    (0x868,): say('우리 집은 대대로 부자라서 남편이 이상한 것만 사 모은답니다.', '그래도 돈을 다 못 써서…… 호호호호.'),
    (0x64F,): say('데스피사로를 조심해라!'),
    (0x64E,): say('공주님, 이대로라면 데스피사로라는 사람이랑 결혼하게 되는 거 아닐까.'),
    (0x7FD,): say('밤에 성에 들어가려면 파수꾼에게 들키지 않도록 하게.'),
    (0x64D,): say('영차 영차. 설거지가 많아서 힘들어!'),
    (0x55C,): say('데스피사로가 없어진 건 무술 대회보다 중요한 일이 생겨서야!'),
    (0x550,): say('아무래도 여자들 수다는 두서가 없어서 못 따라가겠군.'),
    (0x54E,): say('역시 데스피사로 님이 우승이겠지. 멋있고……'),
    (0x64B,): say('데스피사로…… 불길한 이름이로다.'),
    (0x64A,): say('여기는 엔돌 왕의 방입니다.'),
    (0x7FC,): say('우리 임금님께서 터무니없는 약속을 하셨습니다. 공주님 이야기를 들어 주시오.'),
    (0x54C,): say('임금님과 공주님께서는 주무시고 계십니다.'),
    # 엔돌 40/09~0E(FC 04/09~0E)
    (0x6CB,): say('이 가게에서 여러 가지 진귀한 물건을 판다고 듣고 왔는데……'),
    (0x5C3,): say('팔려고 내놓았던 황금의 팔찌라는 게 마물들한테 빼앗겼대요……', '그런 걸 훔쳐서 어디다 쓰려는 걸까요……'),
    (0x547,): say('새근새근……'),
    (0x858, 0x859): say('오, 당신도 상인이군요? 그럼 당신도 은의 여신상을 손에 넣으려고?',
                        '실은 저도 그렇답니다. 분명 비싸게 팔리겠지요.'),
    (0x860,): say('소문으로는 서쪽 나라 산트하임에서 사람들이 사라졌다던데. 무슨 일이 일어난 걸까……'),
    (0x85B,): say('음냐음냐…… 여신상이 동굴에 있으면 얼른 가져오면 될 텐데……', '정말이지 우리 집 양반은 겁쟁이라니까……'),
    (0x64C,): say('테이블을 깨끗이 닦아야지. 쓱싹쓱싹.'),
    (0x54D,): say('자, 치워야지. 쓱싹쓱싹.'),
    (0x5C6,): say('사악한 기운이 하늘을 뒤덮기 시작했다!', '지옥의 제왕이 마침내 되살아나려 하는구나!'),
    (0x653,): say('시끄러워! 말 걸지 마!', '…………미안하다. 시합 전이라 신경이 곤두서서 말이야.'),
    (0x7FE,): say('등록되지 않은 사람은 시합에 나갈 수 없습니다. 임금님께 허가를 받아 오세요.'),
    (0x650,): say('시합에 나가려면 왼쪽. 구경만 하려면 오른쪽 계단을 오르시오.'),
    (0x651,): say('이 위가 시합장. 올라가면 마지막, 물러설 수 없습니다.'),
    (0x652,): say('여기는 성 밖으로 나가는 지름길. 급할 때 편해요.'),
    (0x654,): say('으음 으음 무서워…… 데스피사로의 강함은 도저히 인간이라고 생각할 수 없어……'),
    # 여우 마을 48/00(FC 18/00). 마을 사람은 모두 여우의 둔갑이다
    (0x66B,): say('당신도 이 마을에서 살면 좋을 텐데……', '캥캥캥……', '어머? 감기에 걸렸나 봐.'),
    (0x668,): say('이 근처에는 사람을 홀리는 여우가 있대요. 조심하세요.'),
    (0x669,): say('안녕하세요, 나그네님. 자, 저랑 같이 춤춰요!'),
    (0x66A,): say('저는 돈 가아데. 떠돌이 건축가인데 이 사람이 저한테 반해 버려서……',
                  '결혼해서 이 마을에 살기로 했답니다. 와하하핫.'),
    # 여신상 동굴 48/05·06(FC 40/03·04)
    (0x665,): say('대체 이 동굴은 어떻게 된 거야!? 보물 상자를 꺼낼 수가 없잖아!'),
    (0x666,): say('아까 위에서 물이 넘쳐 와서 빠져 죽을 뻔했다고!', '뭐, 덕분에 보물 상자를 꺼낼 수 있게 됐지. 헤헤, 먼저 간다!'),
}


# ---- 진행별 말과 엔돌 3장 사람의 메시지 ----

MESSAGES = {
    # 레이크나바 3E/00 (05,0F) 대화 05A
    'safe_ask': say('톨네코 씨, 철 금고 얘기 알아요?'),                                    # 081C
    'safe_south': say('혹시 남쪽으로 갈 거라면 철 금고부터 손에 넣는 게 좋을 거예요.'),     # 081D
    'safe_rumor': say('손님한테 들었는데 철 금고가 북쪽 동굴에 있대요.',                    # 081E
                      '철 금고를 갖고 있으면 괴물한테 당해도 돈을 반이나 뺏기지 않는다나 봐요.'),
    'safe_night': say('톨네코 씨, 철 금고를 손에 넣으면 남쪽으로 가는 거죠?',              # 0820
                      '남쪽에는 엔돌이라는 큰 성이 있다니까 분명 큰돈을 벌 수 있을 거예요.'),
    'endor_ask': say('톨네코 씨, 엔돌에는 벌써 가 봤어요?'),                               # 0846
    'endor_lively': say('북적북적한 곳이겠죠?'),                                            # 0847
    'bridge_broken': say('그럼 아직 다리가 부서진 채인가……',                                # 0848
                         '돈 가아데가 다리를 고치러 갔다고 들었는데 어떻게 된 걸까요……'),
    # 수녀 (0D,07) 대화 05B
    'nun_pray': say('톰 할아버지는 마을을 떠난 아드님이 돌아오길 바라며 날마다 기도하신답니다.'),   # 0812
    'nun_glad': say('톰 할아버지 아드님이 돌아왔다면서요? 정말 다행이에요.'),                  # 0843
    # 밤의 전사 (04,13) 대화 059
    'warrior': say('호오…… 세계 제일의 무기상이 되는 게 꿈이라고?',                          # 0821
                   '그럼 싸움 경험을 쌓아서 솜씨도 갈고닦아야지.',
                   '무기 하나 제대로 못 다루는 무기상을 세계 제일이라고 할 수는 없을 테니까.'),
    'warrior_fox': say('에취! 여우한테 홀려서 갑옷을 잃어버렸지 뭔가.',                       # 0849
                       '그러고 보니 홀린 채로 있는 아저씨도 있었지. 돈 가아데라던가……'),
    # 3E/01 밤의 이웃 (02,04) 대화 056
    'neighbor_dream': say('뭐라고! 자기 가게를 갖고 싶다고!?',                              # 0823
                          '그럼 이 마을을 떠나야지. 엔돌 같은 데서 가게를 떡하니 사서 가족을 불러야지……',
                          '꿈이 있어서 좋겠구먼!'),
    'neighbor_proud': say('가게를 샀다면서! 톨네코 씨는 우리 마을에서 제일 출세한 사람이야!'),  # 089F
    # 본몰 감옥 3F/00 (08,04) 대화 064
    'thief_rumor': say('저쪽에 갇혀 있는 건 좀도둑 녀석이야.', '레이크나바에서 왔다나 봐.'),      # 083D
    'thief_gone': say('저쪽에 갇혀 있던 남자가 안 보이네.'),                                  # 083E
    # (06,1C) 대화 062
    'fox_rumor': say('요즘 사람을 홀리는 여우가 있다더군.', '하지만 여우쯤이야 개를 데려가면 쫓을 수 있을 거야.'),  # 066D
    'arms_demand': say('요즘 괴물들도 강해져서 많은 성에서 무기와 방어구를 사 모으는 모양입니다.'),  # 0890
    'arms_envy': say('아니, 무기상인 당신이 부럽군요. 크게 버시겠어요.'),                     # 0891
    # (0B,10) 대화 068
    'bridge_wait': say('엔돌에 가고 싶어도 다리가 부서져서 갈 수가 없어요.',                   # 066F
                       '건축가 돈 가아데 님이라면 다리를 금방 고칠 텐데……'),
    'bridge_soon': say('건축가 돈 가아데 님이 드디어 와 주셨어요!', '이제 부서졌던 다리도 곧 고쳐질 거예요!'),  # 0673
    # (1F,1A) 대화 067
    'jail_hint': say('헤에, 당신 레이크나바에서 왔어? 그러고 보니 성 감옥에도 레이크나바 남자가 있었지.',  # 066E
                     '그 녀석이랑 얘기하고 싶으면 간수한테 들키지 않게 머리를 써서 움직이라고.'),
    'jail_broke': say('감옥에 갇혀 있던 레이크나바 남자가 탈옥했다나 봐!',                     # 0672
                      '뭐, 좀도둑이라 아무도 신경 안 쓰지만.'),
    # (04,15) 대화 060: 방어구 매입(FC 15:$A54C)
    'armor_ask': say('이 성에는 방어구가 모자라네.', '자네가 가진 방어구를 팔아 주지 않겠나?'),  # 0829
    'armor_no': say('그런가, 아쉽구먼.'),                                                    # 082A
    'armor_none': say('그런데 자네는 팔 물건을 하나도 갖고 있지 않잖나. 다음에 다시 오게.'),  # 082B
    'armor_which': say('어느 것을 팔아 주겠나?'),                                             # 082C
    'armor_enough': say('미안하지만 무기나 다른 물건이라면 이미 충분히 있다네.'),             # 082D
    'armor_item': _mark(say('②로군.')),                                                       # 082E 앞
    'armor_offer': _mark(say('그렇다면 ①골드에 사들이지. 괜찮겠나?')),                         # 082E 뒤
    'armor_taken': say('확실히 받았네!'),                                                     # 082F
    'armor_sorry': say('그런가, 아쉽구먼.'),                                                  # 0830
    'armor_more': say('그 밖에도 무언가 팔아 주겠나?'),                                       # 0832
    'armor_bye': say('그럼 또 방어구를 손에 넣거든 팔러 오게.'),                              # 0833
    # 엔돌 3장 목록(FC 1C:$869A·$868E·$877D·$860D·$87EC)의 사람
    'profit': say('헤에, 여기 엔돌에 돈 벌러 왔어?', '이 마을엔 여러 가지 돈벌이 이야기가 있으니까.'),  # 0676
    'clouds': say('저것 봐, 구름이 저렇게 빨리 흘러가.', '어딘가에서 안 좋은 일이 일어나고 있는 걸까……'),  # 0675
    'monsters_back': say('무술 대회 뒤로 한동안은 괴물도 안 나왔는데 또 나오기 시작했어.',      # 0678
                         '대체 어떻게 된 건지…… 뒤숭숭한 세상이야.'),
    'gate_ask': say('성에 물건을 대는 상인인가?'),                                           # 0851
    'gate_in': say('그렇다면 이 문으로 들어가도록.'),                                        # 0501
    'gate_no': say('그럼 물건을 팔러 왔구먼.',                                               # 0852
                   '하지만 웬만한 일이 아니면 새 상인은 쓰지 않는다. 단념하게.'),
    'tournament_over': say('있잖아, 알아? 얼마 전에 성에서 무술 대회가 열렸대.'),              # 0677
    'drunk_ask': say('끅, 취한다 취해. 어이! 좀 벌고 있어?'),                              # 0509
    'drunk_yes': say('그거 잘됐구먼. 딸꾹.'),                                                # 050A
    'drunk_no': say('뭐, 착실하게 열심히 하라고! 딸꾹.'),                                    # 050B
    'shop_permit': say('이 마을에서 가게를 내려면 임금님의 허락이 필요하답니다.', '좀 어려울 거예요.'),  # 055A
    'emperor_rumor': say('괴물이 나오기 시작한 건 지옥의 제왕인가 하는 게 되살아날 징조라는 소문이야.'),  # 0559
    'ryan': say('나는 바트랜드의 전사 라이안.',                                              # 0681
                '내가 찾는 분이 혹시 무술 대회에 나오지 않았을까 해서 와 봤는데……',
                '무술 대회도 이미 끝났고 카지노도 한동안 쉰다는군.'),
    'keep_out': say('여기에 들어갈 수는 없다. 물러가라.'),                                   # 0870
    'arena_closed': say('무술 대회도 끝나서 이곳은 당분간 닫게 되었다.'),                     # 086F
    'pizarro_gone': say('무술 대회에서는 데스피사로라는 남자가 우승할 뻔했어요.',              # 067C
                        '그런데 데스피사로는 도중에 사라졌답니다. 정체가 뭐였을까요.'),
    'emperor_rumor2': say('지옥의 제왕이 되살아난다는 소문도 있고……',                       # 055E
                          '어느 소문이 진짜인지 짐작이 안 가네요……'),
    'hero_rumor': say('소문으로는 세상을 구할 용사가 어딘가에서 자라고 있다더군.'),            # 055D
    'kitchen': say('어머, 채소 장수? 뭐? 무기 장수라고? 어머나! 여기는 부엌이라고요!'),        # 0680
    'gaade_bridges': say('돈 가아데라는 자가 여기저기 다리를 고쳤다더군.'),                   # 067F
    'pizarro_fan': say('지난번 무술 대회에선 데스피사로 님이 꼭 우승할 줄 알았는데……'),      # 055B
    'sky_sword': say('그 옛날 천공의 검이라는 것이 있었다더군.',                             # 067E
                     '그 검을 손에 넣은 자는 하늘에 오를 수 있었다지.'),
    'king_meets_all': say('우리 임금님께서는 신분을 가리지 않고 누구든 만나 주신다. 실례가 없도록 하라.'),  # 067D
    # 레이크나바 집 맨 윗줄의 빈 가게 사람: 그 앞 칸 (10,01)의 FC 빈 사람(대화 008, 02F0)과 같은 말
    'empty_shop': say('그 방향에는 아무도 없다.'),
    'statue_ask': say('오, 당신도 상인이군요? 그럼 당신도 은의 여신상을 손에 넣으려고?'),     # 0858
    'statue_me_too': say('실은 저도 그렇답니다. 분명 비싸게 팔리겠지요.'),                    # 0859
    'statue_oops': say('아이고, 그러셨군요…… 방금 한 말은 못 들은 걸로 해 주세요. 와하하핫.'),  # 085A
    # 본몰 성 3F/01 유모 (06,06)·(06,07) 대화 05F
    'nanny_room': say('여기는 왕자님 방이에요. 너 같은 천한 것이 올 곳이 아닙니다.'),        # 0836
    'nanny_out': say('자! 나가세요!'),                                                      # 03B1
    # 말한 뒤 일행을 내보내는 파수꾼(FC 대화 066·028). 옮긴 대사(034A·038E)와 같은 말
    'jail_out': say('여기는 감옥이다! 죄수와 이야기하는 것은 허락할 수 없다! 자, 나가시오!'),       # 034A
    'night_out': say('이런 한밤중에 성에 들어오다니!', '내 눈에 띈 이상 가만있을 수는 없다. 자, 물러가시오!'),  # 038E
    # 열린 카지노(공사 재개 뒤)의 코인·교환·슬롯·포커 사람. 놀이는 옮기지 않았다(코인을 살 수 없음)
    'poker_ask': say('여기는 포커 테이블입니다. 즐기시겠습니까?'),                           # 07F6
    'poker_short': say('어이쿠 손님, 코인이 모자라시네요. 코인을 사신 뒤 다시 오세요!'),      # 0482
    'poker_later': say('그럼 마음이 내키시면 언제든 오세요.'),                               # 07F7
}


def _not(cond):
    return {**cond, "not": True}


# 메시지 하나만 띄우는 대화(엔돌 3장 목록의 사람). 이름이 곧 MESSAGES 의 이름
SIMPLE = ('profit', 'clouds', 'monsters_back', 'tournament_over', 'shop_permit', 'emperor_rumor', 'ryan', 'keep_out',
          'arena_closed', 'pizarro_gone', 'emperor_rumor2', 'hero_rumor', 'kitchen', 'gaade_bridges', 'pizarro_fan',
          'sky_sword', 'king_meets_all', 'empty_shop')
TALKS = ('safe_man', 'nun', 'warrior', 'neighbor', 'prisoner', 'castle_man', 'bridge', 'jail',
         'armor_buyer', 'gate', 'drunk', 'statue_merchant', 'jail_guard', 'night_guard', 'nanny', 'poker') + SIMPLE


def talk_scripts(ctx):
    s, flag, when = ctx.say, ctx.flag, ctx.when
    bodies = {
        # FC 05A: 아들이 돌아온 뒤 0846(「예」 0847 / 「아니오」 0848), 그 전 낮 081C(「예」 081D / 「아니오」 081E), 밤 0820
        'safe_man': [when(flag(SON_FREED), [s('endor_ask'), when(YES, [s('endor_lively')], [s('bridge_broken')])],
                          [when(DAY, [s('safe_ask'), when(YES, [s('safe_south')], [s('safe_rumor')])],
                                [s('safe_night')])])],
        'nun': [when(flag(SON_FREED), [s('nun_glad')], [s('nun_pray')])],
        'warrior': [when(flag(SON_FREED), [s('warrior_fox')], [s('warrior')])],
        'neighbor': [when(flag(SHOP), [s('neighbor_proud')], [s('neighbor_dream')])],
        'prisoner': [when(flag(SON_FREED), [s('thief_gone')], [s('thief_rumor')])],
        'castle_man': [when(flag(LETTER1), [s('arms_demand'), s('arms_envy')], [s('fox_rumor')])],
        'bridge': [when(flag(FOXED), [s('bridge_soon')], [s('bridge_wait')])],
        'jail': [when(flag(FOXED), [s('jail_broke')], [s('jail_hint')])],
        # 매입은 옮기지 않았다: 「예」 면 팔 것이 없다는 말(FC 082B)로 끝난다
        # 고르기·값·되묻기는 대화 호출 armor_buy(네이티브)가 FC 15:$A54C 차례대로 한다
        'armor_buyer': [s('armor_ask'), when(YES, [ctx.call('armor_buy')], [s('armor_no')])],
        'gate': [s('gate_ask'), when(YES, [s('gate_in')], [s('gate_no')])],
        'drunk': [s('drunk_ask'), when(YES, [s('drunk_yes')], [s('drunk_no')])],
        'statue_merchant': [s('statue_ask'), when(YES, [s('statue_me_too')], [s('statue_oops')])],
        'jail_guard': [s('jail_out'), ctx.call('jail_out')],
        'nanny': [when(flag(NANNY_SCOLDED), [s('nanny_out')], [s('nanny_room')])],
        'night_guard': [s('night_out'), ctx.call('night_out')],
        'poker': [s('poker_ask'), when(YES, [s('poker_short')], [s('poker_later')])],
    }
    bodies.update({name: [s(name)] for name in SIMPLE})
    return [bodies[name] for name in TALKS]


# ---- 인물 목록 ----

LAKANABA, HOUSE, PRISON, BONMALMO = '3E/00', '3E/01', '3F/00', '3F/01'
# 옮긴 목록에서 대화를 바꾸는 사람: (맵, 낮·밤 또는 None(둘 다), FC 칸) → 대화 이름
RETALK = {
    (LAKANABA, None, (0x05, 0x0F)): 'safe_man',
    (LAKANABA, 'day', (0x0D, 0x07)): 'nun',
    (LAKANABA, 'night', (0x04, 0x13)): 'warrior',
    (HOUSE, 'night', (0x02, 0x04)): 'neighbor',
    (PRISON, 'day', (0x08, 0x04)): 'prisoner',
    (BONMALMO, None, (0x06, 0x1C)): 'castle_man',
    (BONMALMO, 'day', (0x0B, 0x10)): 'bridge',
    (BONMALMO, 'day', (0x1F, 0x1A)): 'jail',
    (BONMALMO, 'day', (0x04, 0x15)): 'armor_buyer',
    (BONMALMO, 'day', (0x06, 0x06)): 'nanny',
    (BONMALMO, 'day', (0x06, 0x07)): 'nanny',
    (PRISON, 'day', (0x0A, 0x0E)): 'jail_guard',
    (PRISON, 'day', (0x02, 0x07)): 'jail_guard',
}
# 파수꾼이 일행을 내보내는 자리(FC 실측: 3장 상태로 말을 걸어 끝난 맵·칸). 감옥 05/00 → 05/01 (19,02),
# 엔돌 성 밤 04/02 → 04/00 (17,0A)
OUT_TO = {'jail_out': ('3F/01', (0x19, 0x02)), 'night_out': ('40/00', (0x17, 0x0A))}

# FC 16/01 맨 윗줄 (10,00)의 서비스 3 인물(대화 003). 16/01 에는 가게 목록이 없어 옮기면 「＜なにもない＞」 만 낸다.
# 사건과 상관없는 사람이라 앞 칸의 빈 사람과 같은 말로 바꾼다. 목록에서 빼면 안 된다: 3E 그룹에서 그림 36 을 쓰는 유일한
# 사람이라, 빼면 dq4people 이 그림마다 나오는 그룹으로 푸는 줄·색 칸 배치가 달라져 1장 화면의 인물 그림까지 바뀌었다
EMPTY_SHOP = (HOUSE, 'day', (0x10, 0x00))

ENDOR_TOWN, CASINO, ENDOR_HALL, KITCHEN, THRONE, ARENA, INN = '40/00', '40/01', '40/02', '40/05', '40/06', '40/07', '40/0B'
# FC 3장 엔돌 목록에서 기본 목록과 대화가 다른 칸(엔돌·본몰 모듈이 맡은 칸과 용병 스콧 (05,13)은 빼고): (맵, 낮·밤,
# FC 칸) → 대화 이름. 그림·방향·걸음은 기본 목록과 같다(test_dq4ch3towns 가 FC 롬과 견줌)
ENDOR = {
    (ENDOR_TOWN, 'day', (0x0D, 0x1A)): 'profit',
    (ENDOR_TOWN, 'day', (0x2B, 0x0C)): 'clouds',
    (ENDOR_TOWN, 'day', (0x1A, 0x0F)): 'monsters_back',
    (ENDOR_TOWN, 'day', (0x16, 0x0A)): 'gate',
    (ENDOR_TOWN, 'day', (0x17, 0x14)): 'tournament_over',
    (ENDOR_TOWN, 'night', (0x04, 0x0C)): 'emperor_rumor',
    (ENDOR_TOWN, 'night', (0x0D, 0x1A)): 'profit',
    (ENDOR_TOWN, 'night', (0x0D, 0x1C)): 'shop_permit',
    (ENDOR_TOWN, 'night', (0x1A, 0x0F)): 'drunk',
    (ENDOR_HALL, 'day', (0x10, 0x08)): 'keep_out',
    (ENDOR_HALL, 'day', (0x12, 0x19)): 'pizarro_gone',
    (ENDOR_HALL, 'night', (0x10, 0x08)): 'keep_out',
    (ENDOR_HALL, 'night', (0x11, 0x08)): 'keep_out',
    (ENDOR_HALL, 'night', (0x11, 0x12)): 'emperor_rumor2',
    (ENDOR_HALL, 'night', (0x12, 0x12)): 'hero_rumor',
    (KITCHEN, 'day', (0x03, 0x02)): 'gaade_bridges',
    (KITCHEN, 'day', (0x08, 0x06)): 'kitchen',
    (KITCHEN, 'night', (0x02, 0x02)): 'pizarro_fan',
    (THRONE, 'day', (0x19, 0x09)): 'sky_sword',
    (THRONE, 'night', (0x19, 0x09)): 'sky_sword',
    (THRONE, 'day', (0x0D, 0x0B)): 'king_meets_all',
    (INN, 'day', (0x03, 0x01)): 'statue_merchant',
    (INN, 'night', (0x03, 0x01)): 'statue_merchant',
    (ENDOR_HALL, 'night', (0x0C, 0x1C)): 'night_guard',
}
# FC 3장 목록에서 자리·걸음이 기본 목록과 다른 사람: (맵, 낮·밤, FC 칸) → (FC 칸, 서 있음). 밤 마을 사람 하나가 한 칸
# 오른쪽, 왕좌의 방 대신은 서 있다
ENDOR_MOVED = {(ENDOR_TOWN, 'night', (0x16, 0x1E)): ((0x17, 0x1E), False),
               (THRONE, 'day', (0x0D, 0x0B)): ((0x0D, 0x0B), True)}
# FC 3장 목록에 없는 기본 목록의 사람: 성 1층의 콜로세움 길 병사 둘과 대회 이야기꾼
ENDOR_GONE = {ENDOR_HALL: (('day', (0x02, 0x21)), ('day', (0x18, 0x21)), ('day', (0x0D, 0x16)))}
# FC 3장 목록에만 있는 사람: (맵, 낮·밤, FC 칸, 대화, 같은 겉모습의 기본 목록 사람 칸). 콜로세움 문의 둘째 병사(대화 03D)
ENDOR_ADDED = ((ENDOR_HALL, 'day', (0x11, 0x08), 'arena_closed', (0x10, 0x08)),)
# 카지노(FC 04/01)는 3장 동안 목록 1C:$868E 의 라이안 하나다. FC 는 굴 공사를 다시 하면($6287&80) 기본 목록(열린
# 카지노)으로 되돌리지만, 카지노 사람(코인·교환·슬롯)의 동작을 옮기지 않아 3장 내내 닫아 둔다
RYAN = ((0x13, 0x06), 0x4E, 'down', 8)          # FC 칸, FC 그림(병사), 방향, FC 걸음 간격
CASINO_PEOPLE = ((0x04, 0x0C), (0x08, 0x0A), (0x0C, 0x03), (0x0F, 0x07), (0x10, 0x03), (0x12, 0x0D), (0x13, 0x03),
                 (0x13, 0x0B), (0x15, 0x06), (0x17, 0x0D), (0x18, 0x02), (0x1C, 0x08), (0x1F, 0x00))
# 3장 동안 다른 모듈의 3장 목록이 없으면 이 모듈이 기본 목록을 베껴 거는 엔돌 맵. 2장 끝의 우승 목록(dq4ch2ending,
# 빈 성 flag 가 3장에도 켜져 있음)이 3장에 걸리지 않게 한다. 04/07·04/0B 는 FC 3장도 기본 목록이다
# 열린 카지노의 장치 사람(FC 칸 → 대화): 교환소(046)·코인 판매(047)·슬롯(048)·포커(049)
CASINO_DEVICES = {(0x13, 0x0B): 'poker'}
# DQ5 가게 처리기를 그대로 부르는 사람(FC 칸 → DQ5 대화 번호): 코인 판매 0B(FC 047, 06:EE34)·코인 교환 0C(FC 046)·
# 몬스터 격투장 0E(FC 048). 경품 목록·코인 값·한 장 값·시합 표는 dq4shopport(COIN_KEY·COIN_PRICES·COIN_SALE·arena)
CASINO_SERVICES = {(0x18, 0x02): 0x0B, (0x1C, 0x08): 0x0C, (0x08, 0x0A): 0x0E}
COIN_SALE_FIRST, COIN_EXCHANGE_FIRST, ARENA_FIRST = 0x468, 0x461, 0x112
ENDOR_MAPS = (ENDOR_TOWN, ENDOR_HALL, KITCHEN, THRONE, ARENA, INN)


def _at(e):
    return (e["fields"]["x"], e["fields"]["y"])


def _ch3_lists(m, ctx):
    """맵 m 에 3장 동안 걸리는 앞 모듈의 대체 목록(이름이 ch3_ 로 시작하는 것)."""
    names = {o["list"][4:] for o in ctx.overrides if o["map"] == m and o["list"].startswith("new:ch3_")}
    return [ctx.made_all[n] for n in sorted(names) if n in ctx.made_all]


def _retalk_entries(entries, m, talks):
    """entries 를 베껴(앞 모듈·기본 목록과 항목을 나누지 않게) ENDOR·ENDOR_GONE·ENDOR_ADDED 대로 바꾼다."""
    gone = {(t, cell(*fc)) for t, fc in ENDOR_GONE.get(m, ())}
    want = {(t, cell(*fc)): name for (mm, t, fc), name in ENDOR.items() if mm == m}
    out = []
    for e in entries:
        key = (e["time"], _at(e))
        if key in gone:
            continue
        if key in want:
            e = {**e, "fields": {**e["fields"], "talk": talks[want[key]]}}
        moved = next((v for (mm, t, fc), v in ENDOR_MOVED.items() if mm == m and (t, cell(*fc)) == key), None)
        if moved:
            import dq4npcport
            (x, y), stand = cell(*moved[0]), moved[1]
            e = {**e, "fields": {**e["fields"], "x": x, "y": y, **({"interval": 0} if stand else {})},
                 **({"from": dq4npcport.STAND} if stand else {})}
        out.append(e)
    for mm, t, fc, name, like in ENDOR_ADDED:
        if mm != m:
            continue
        model = next((e for e in out if (e["time"], _at(e)) == (t, cell(*like))), None)
        if model is None:
            raise SystemExit(f'마을 사람: {m} {t} {like} 에 본뜰 사람이 없음')
        x, y = cell(*fc)
        out.append({**model, "fields": {**model["fields"], "x": x, "y": y, "talk": talks[name]}})
    have = {(e["time"], _at(e)) for e in out}
    missing = sorted(k for k in want if k not in have)
    if missing:
        raise SystemExit(f'마을 사람: {m} 에 대화를 바꿀 사람이 없음 {missing}')
    return out


def _ryan(talk):
    import dq4npcport
    x, y = cell(*RYAN[0])
    e = {"from": dq4npcport.WALK, "fields": {"x": x, "y": y, "facing": RYAN[2], "talk": talk,
                                             "gfx": dq4npcport.PICTURES[RYAN[1]], "layer": 0,
                                             "interval": dq4npcport.dq5_interval(RYAN[3])}}
    return [{**e, "time": "day"}, {**e, "time": "night"}]


def npc_lists(lists, ctx):
    """레이크나바·본몰은 옮긴 목록의 대화를 바꾸고, 엔돌은 3장 동안 걸리는 목록을 FC 3장 목록대로 고친다."""
    if LAKANABA not in lists:
        return [], []           # 인물 없이 옮긴 목록(dq4npcport.port 의 with_people=False)
    t = ctx.talk
    for (m, time, fc), name in RETALK.items():
        ctx.retalk(lists, m, cell(*fc), t[name], time=time)
    # 첫머리 목록(dq4ch3event 가 기본 목록을 베낀 ch3_opening)의 같은 사람도
    m, time, fc = EMPTY_SHOP
    for lst in (lists[m], *_ch3_lists(m, ctx)):
        hit = 0
        for e in lst["entries"]:
            if (e["time"], _at(e)) == (time, cell(*fc)):
                e["fields"] = {**e["fields"], "talk": t['empty_shop']}
                hit += 1
        if hit != 1:
            raise SystemExit(f'마을 사람: {m} {fc} 의 빈 가게 사람이 {hit}명')
    new, over = [], []

    def on(m, name):
        return {"map": m, "flag": ch3.CHAPTER3[0], "when": "on", "mask": ch3.CHAPTER3[1], "list": f"new:{name}"}
    for m in ENDOR_MAPS:
        theirs = _ch3_lists(m, ctx)
        for lst in theirs:
            lst["entries"] = _retalk_entries(lst["entries"], m, t)
        if not theirs:
            name = f'ch3_towns_{m.replace("/", "")}'
            new.append({"name": name, "entries": _retalk_entries(copy.deepcopy(lists[m]["entries"]), m, t)})
            over.append(on(m, name))
    # 공사 재개(굴 모듈 RESUMED, FC $6287&80) 뒤에는 FC 처럼 기본 목록의 열린 카지노. 닫힌 목록보다 앞 줄이어야 한다
    import dq4ch3tunnel as tunnel
    devices = {(tm, cell(*fc)): t[talk] for fc, talk in CASINO_DEVICES.items() for tm in ('day', 'night')}
    devices.update({(tm, cell(*fc)): service for fc, service in CASINO_SERVICES.items() for tm in ('day', 'night')})
    opened = [{**e, "fields": {**e["fields"], "talk": devices[(e["time"], _at(e))]}}
              if (e["time"], _at(e)) in devices else e for e in copy.deepcopy(lists[CASINO]["entries"])]
    if sum(1 for e in opened if (e["time"], _at(e)) in devices) != len(devices):
        raise SystemExit(f'마을 사람: {CASINO} 에 카지노 장치 사람이 모자람')
    new.append({"name": 'ch3_towns_4001_open', "entries": opened})
    over.append({"map": CASINO, "flag": tunnel.RESUMED[0], "when": "on", "mask": tunnel.RESUMED[1],
                 "list": "new:ch3_towns_4001_open"})
    name = f'ch3_towns_{CASINO.replace("/", "")}'
    # 굴 모듈이 기본 목록에 더한 보이지 않는 인물(공사 재개 뒤 들어오면 개통 소식을 켬, dq4ch3tunnel.NOTICE_MAP)은 닫힌
    # 카지노에도 둔다
    notice = {"list": tunnel.SCRIPT_LIST, "index": tunnel.SCRIPTS['notice'][0]}
    new.append({"name": name, "entries": _ryan(t['ryan']) + [e for e in lists[CASINO]["entries"] if e.get("from") == notice]})
    over.append(on(CASINO, name))
    return new, over


def absent(ctx=None):
    """{(맵, DQ5 셀 x, y, 밤)}: 3장 동안 목록에 없는 기본 목록의 사람(닫힌 카지노, 성 1층의 셋)."""
    out = {(CASINO, *cell(*fc), night) for fc in CASINO_PEOPLE for night in (False, True)}
    out |= {(m, *cell(*fc), t == 'night') for m, gone in ENDOR_GONE.items() for t, fc in gone}
    out |= {(m, *cell(*fc), t == 'night') for (m, t, fc), (to, _) in ENDOR_MOVED.items() if to != fc}
    return out


def start_messages(ctx):
    """{(맵, DQ5 셀, 밤 또는 None): 첫 메시지}: 3장 처음 상태(사건 flag 모두 꺼짐)에서 이 모듈이 대화를 바꾼 사람."""
    m = ctx.msg
    first = {'safe_man': None, 'nun': 'nun_pray', 'warrior': 'warrior', 'neighbor': 'neighbor_dream',
             'prisoner': 'thief_rumor', 'castle_man': 'fox_rumor', 'bridge': 'bridge_wait',
             'jail': 'jail_hint', 'armor_buyer': 'armor_ask', 'gate': 'gate_ask', 'drunk': 'drunk_ask',
             'statue_merchant': 'statue_ask', 'jail_guard': 'jail_out', 'night_guard': 'night_out', 'nanny': 'nanny_room',
             **{n: n for n in SIMPLE}}
    out = {}
    for (mp, time, fc), name in (*RETALK.items(), *ENDOR.items(), (EMPTY_SHOP, 'empty_shop')):
        if name == 'safe_man':
            out[(mp, cell(*fc), False)] = m['safe_ask']
            out[(mp, cell(*fc), True)] = m['safe_night']
            continue
        out[(mp, cell(*fc), None if time is None else time == 'night')] = m[first[name]]
    return out


def _set(*flags):
    return ';'.join(f'{0x2190 + i:04X}|{mask:02X}' for i, mask in flags)


def state_messages(ctx):
    """{상태 이름: (SET, {(맵, FC 칸, 밤): 첫 메시지})}: 사건 flag 하나를 켠 상태에서 이 모듈이 말을 바꾼 사람
    (dq4npccheck --chapter3 --states)."""
    m = ctx.msg
    return {
        'towns_son_freed': (_set(SON_FREED), {
            (LAKANABA, (0x05, 0x0F), False): m['endor_ask'], (LAKANABA, (0x05, 0x0F), True): m['endor_ask'],
            (LAKANABA, (0x0D, 0x07), False): m['nun_glad'], (LAKANABA, (0x04, 0x13), True): m['warrior_fox'],
            (PRISON, (0x08, 0x04), False): m['thief_gone']}),
        'towns_foxed': (_set(FOXED), {(BONMALMO, (0x0B, 0x10), False): m['bridge_soon'],
                                      (BONMALMO, (0x1F, 0x1A), False): m['jail_broke']}),
        'towns_letter': (_set(LETTER1), {(BONMALMO, (0x06, 0x1C), False): m['arms_demand'],
                                         (BONMALMO, (0x06, 0x1C), True): m['arms_demand']}),
        # 왕자를 만난 뒤 다시 들어온 방문: 들 때 이미 켜져 있어 유모는 0836
        'towns_prince': (_set(PRINCE_MET), {(BONMALMO, (0x06, 0x06), False): m['nanny_room'],
                                            (BONMALMO, (0x06, 0x07), False): m['nanny_room']}),
        # 쫓겨난 그 방문: 맵 안 임시 비트라 맵에 든 뒤에 켠다(셋째 값 LATESET)
        'towns_chased': ('', {(BONMALMO, (0x06, 0x06), False): m['nanny_out'],
                              (BONMALMO, (0x06, 0x07), False): m['nanny_out']}, _set(PRINCE_MET, NANNY_SCOLDED)),
        'towns_shop': (_set(SHOP), {(HOUSE, (0x02, 0x04), True): m['neighbor_proud']}),
        'towns_casino': (_set(_resumed()), {(CASINO, fc, night): first for fc, first in (
            ((0x1C, 0x08), COIN_EXCHANGE_FIRST), ((0x18, 0x02), COIN_SALE_FIRST), ((0x08, 0x0A), ARENA_FIRST),
            ((0x13, 0x0B), m['poker_ask'])) for night in (False, True)}),
    }


# 본몰 방어구 매입(FC 대화 060, 15:$A54C)의 값. 물건 고르는 창을 옮기지 않아 아직 쓰지 않는다(문서 「남은 것」).
# FC 실측: かわのよろい(값 180)를 판 금화가 180·163·222·191 — 모두 248/256 갈래의 값 × (54 + ⌊r × 27/256⌋)/64
def armor_buy_price(value, r1, r2):
    """r1·r2: 난수 0~255. r1 < F8 이면 값 × (54 + ⌊r2 × 27/256⌋)/64, 아니면 값 × (96 + ⌊r2 × 33/256⌋)/64(코드 읽기)."""
    if r1 < 0xF8:
        return value * (54 + r2 * 27 // 256) // 64
    return value * (96 + r2 * 33 // 256) // 64


def _resumed():
    import dq4ch3tunnel
    return dq4ch3tunnel.RESUMED


# ---- 내보내기(파수꾼이 말한 뒤 일행을 다른 자리로) ----

DATA_ENTRIES = tuple(f'{name}_event' for name in OUT_TO)
CALLS = {**{name: (name, 0) for name in OUT_TO}, 'armor_buy': ('armor_buy', 0)}
# 네이티브 armor_buy 가 띄우는 메시지(대화 스크립트에는 없음)
ARMOR_MESSAGES = ('armor_none', 'armor_which', 'armor_enough', 'armor_item', 'armor_offer', 'armor_taken', 'armor_sorry',
                  'armor_more', 'armor_bye')
# 매입하는 장비 칸(DQ5 23:B231 bit0-2: 1 갑옷, 2 방패, 3 투구 = FC 종류 1~3)
ARMOR_SLOTS = (1, 2, 3)
EQUIP_SLOT = 0x23B231
# FC 의 r1 < F8(248/256): DQ5 00:953A 는 (r × A) >> 8 이라 A = 32 로 받아 31 보다 작으면 같은 갈래
COMMON_BELOW, COMMON_OF = 31, 32


def _warp_event(name):
    mp, fc = OUT_TO[name]
    g, n = (int(v, 16) for v in mp.split('/'))
    return bytes((0x90, g, n, *cell(*fc), 0x01, 0x80, 0xFF))


def native(ctx):
    """(바이트, {이름: 주소}): 내보내는 이벤트 스크립트와 그것을 거는 대화 호출 루틴."""
    import dq4prologue
    out, at = bytearray(), {}

    def put(name, code):
        at[name] = ctx.code_at + len(out)
        out.extend(code)
    for name in OUT_TO:
        put(f'{name}_event', _warp_event(name))
        put(name, dq4prologue._event_start(at[f'{name}_event']))
    put('armor_buy', _armor_buy(ctx.msg or {k: 0 for k in MESSAGES}))
    return bytes(out), at


def _armor_buy(m):
    """대화 호출: FC 15:$A54C. 톨네코(일행 칸 0) 소지품이 비었으면 082B. 아니면 DQ5 팔기 물건 창으로 고르게 해
    방어구(갑옷·방패·투구)가 아니면 082D, 맞으면 값 × (54 + ⌊r × 27/256⌋)/64(드물게 (96 + ⌊r × 33/256⌋)/64)를
    부르고 「예」 면 금화에 더하고 소지품에서 뺀 뒤 082F, 「아니요」 면 0830. 0832 「예」 면 되풀이, 아니면 0833.
    장비 중인 물건도 산다(FC 실측). 창 받침과 임시 칸은 엔돌 네네 가게(dq4neneshop)의 것을 함께 쓴다."""
    from dq4ch2endor import BCC, BCS, BEQ, BNE, sta
    import dq4neneshop as nene
    from dq4ch3slots import LOW_STUBS
    brk = nene.low_stubs(LOW_STUBS[0])[1]
    show = nene._show
    p, acc, cnt = nene.TEMP & 0xFFFF, (nene.TEMP + 3) & 0xFFFF, (nene.TEMP + 6) & 0xFFFF
    slot, item = (nene.PICK + 1) & 0xFFFF, (nene.PICK + 2) & 0xFFFF
    w = lambda op, addr: bytes((op, addr & 0xFF, addr >> 8))  # noqa: E731

    def j(name):
        return bytes((0x22, *nene._al(brk[name])))
    from dq4chapterbox import ENTER, LEAVE
    a = nene._asm()(ENTER, 0xF4, 0x7E, 0x7E, 0xAB, 0xAB, 0xE2, 0x30)
    a(0x22, *nene._al(nene.SHOP_ENTER), 0xE2, 0x30, j('window'), j('close'))
    a.label('round')(0x64, 0x42, j('count'), 0xA5, 0x46).br(BNE, 'has')
    show(a, m['armor_none'])
    a.brl('end')
    a.label('has')
    show(a, m['armor_which'])
    a(0x22, *nene._al(nene.PICKER_RESET), 0x64, 0xE4, j('pick'), 0xA5, 0xE8).br(0x10, 'picked')(j('close')).brl('bye')
    a.label('picked')(0x85, 0x43, w(0x8D, slot), 0x64, 0x42, j('item'))
    a(0xA5, 0x46, 0x48, j('close'), 0x68, w(0x8D, item), 0x85, 0xF5, 0xAA)
    a(0xBF, *nene._al(EQUIP_SLOT), 0x29, 0x07, 0xC9, ARMOR_SLOTS[0]).br(BCC, 'other')(0xC9, ARMOR_SLOTS[-1] + 1).br(BCC, 'armor')
    a.label('other')
    show(a, m['armor_enough'])
    a.brl('more')
    a.label('armor')
    show(a, m['armor_item'])
    # 값 p(3바이트) = BRK 94 02 → $46~$48
    a(w(0xAD, item), 0x85, 0x42, j('price'), 0xA5, 0x46, w(0x8D, p), 0xA5, 0x47, w(0x8D, p + 1), 0xA5, 0x48, w(0x8D, p + 2))
    a(0xA9, COMMON_OF, 0x22, *nene._al(nene.RANDOM), 0xC9, COMMON_BELOW).br(BCS, 'rare')
    a(0xA9, 27, 0x22, *nene._al(nene.RANDOM), 0x18, 0x69, 54).br(0x80, 'mult')
    a.label('rare')(0xA9, 33, 0x22, *nene._al(nene.RANDOM), 0x18, 0x69, 96)
    a.label('mult')(w(0x8D, cnt), w(0x9C, acc), w(0x9C, acc + 1), w(0x9C, acc + 2))
    a.label('add')(0x18, w(0xAD, acc), w(0x6D, p), w(0x8D, acc), w(0xAD, acc + 1), w(0x6D, p + 1), w(0x8D, acc + 1))
    a(w(0xAD, acc + 2), w(0x6D, p + 2), w(0x8D, acc + 2), w(0xCE, cnt)).br(BNE, 'add')
    for _ in range(6):                                                                 # ÷ 64
        a(w(0x4E, acc + 2), w(0x6E, acc + 1), w(0x6E, acc))
    a(w(0xAD, acc), 0x85, 0xF5, w(0xAD, acc + 1), 0x85, 0xF6, w(0xAD, acc + 2), 0x85, 0xF7)
    show(a, m['armor_offer'])
    a(j('ask'), 0xA5, 0xE8, 0x48, j('close'), 0x68).br(BEQ, 'sell')
    show(a, m['armor_sorry'])
    a.brl('more')
    a.label('sell')(0x18, w(0xAD, acc), 0x6F, *nene._al(nene.GOLD_AT), sta(nene.GOLD_AT))
    a(w(0xAD, acc + 1), 0x6F, *nene._al(nene.GOLD_AT + 1), sta(nene.GOLD_AT + 1))
    a(w(0xAD, acc + 2), 0x6F, *nene._al(nene.GOLD_AT + 2), sta(nene.GOLD_AT + 2))
    a(0x64, 0x42, w(0xAD, slot), 0x85, 0x43, j('drop'))
    show(a, m['armor_taken'])
    a.label('more')
    show(a, m['armor_more'])
    a(j('ask'), 0xA5, 0xE8, 0x48, j('close'), 0x68).br(BNE, 'bye').brl('round')
    a.label('bye')
    show(a, m['armor_bye'])
    a.label('end')
    return a.bytes() + LEAVE


def events(ctx):
    """이벤트 스크립트 토큰(dq4msgwait 가 봄). 메시지를 띄우지 않는다."""
    return [[_warp_event(name)] for name in OUT_TO]
