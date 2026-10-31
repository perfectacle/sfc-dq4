"""1장 진행 사건: 이무르 밤의 아이 → 성 앞 프레아 → 이무르 감옥 재회.

FC 에서는 이무르 밤에 아이(대화 012) 또는 감옥의 알렉스(013)에게서 알렉스 이름을 들어야($6281&80) 성 앞의
프레아(낮 00F·밤 010)가 따라오고($627E&20), 따라온 채 감옥 12/02 에 들어가면 프레아가 걸어와 재회한다($627E&40).
감옥의 프레아 둘(걸어오는 쪽·재회 뒤 서 있는 쪽)은 그 깃발 전에는 숨는다(1C:$A1AE).

여기서는
- 깃발 셋을 DQ5 가 읽지 않는 비트(sfc/dq5/docs/dq5-flags.md 「시험하는 곳이 없는 비트」)에 두고,
- 깃발을 켜는 대화를 덧붙인 대화(dq5talkwrite)로, 프레아가 사라지는 것과 걸어와 재회하는 것을 인물 스크립트로 넣는다.
메시지는 옮긴 인물 메시지(dq4npcport, C80~) 바로 뒤에 MESSAGES 차례로 둔다. 형식은
sfc/dq4/docs/dq4-chapter1-format.md 「진행 사건」.
"""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE)]

import dq4ch1talk  # noqa: E402
import dq4chapter1 as ch1  # noqa: E402

say, speak = ch1.say, ch1.speak

# 1장 진행 깃발. DQ5 롬에서 켜고 끄고 보는 곳이 없고, 이 바이트와 앞 바이트를 바이트로 쓰는 곳도 없는 비트다
# (sfc/dq5/docs/dq5-flags.md). 21EF 부터는 색인 쓰기(02:E053·05:DF2A·23:E20E 등)가 220F 까지 덮는다
NIGHT_TOLD = (0x57, 0x01)       # 7E:21E7 bit0  이무르 밤에 알렉스 이름을 들음(FC $6281&80)
FLARE_FOLLOWS = (0x57, 0x02)    # 7E:21E7 bit1  프레아가 따라옴(FC $627E&20)
REUNITED = (0x57, 0x04)         # 7E:21E7 bit2  감옥에서 재회함(FC $627E&40)
HOIMIN = (0x57, 0x10)           # 7E:21E7 bit4  호이민이 동료가 됨(FC $6281&40)
KIDNAPPED = (0x57, 0x20)        # 7E:21E7 bit5  탑 입구에서 마물이 아이를 끌고 감(FC $627E&01)
BOSS_WON = (0x57, 0x40)         # 7E:21E7 bit6  탑 위 보스를 이김(FC $6283&80)
KIDS_FOLLOW = (0x57, 0x80)      # 7E:21E7 bit7  구한 아이들이 따라옴(FC $6283&20). 이무르에 데려다주면 끈다
# 아래는 DQ5 레ヌール城 04/05 의 인물 스크립트만 읽는 비트(이 해킹은 04/05 에 가지 않음, dq5flags.py)
SOLDIER_LEFT = (0x06, 0x01)     # 7E:2196 bit0  탑의 병사가 먼저 돌아감(FC $6280&80)
REPORTED = (0x07, 0x80)         # 7E:2197 bit7  왕에게 보고하고 여행을 허락받음(FC $6285&04)
# 41 동굴 병사의 대사 차례(FC $6281 아래 두 비트, 15:9D3E). FC 는 말을 걸면 bit2 를 켜고, 맵에서 필드로 나갈 때
# (15:9CF9, 1E:9311 이 부름) bit2 가 켜져 있으면 차례를 하나 올린다. 여기서는 동굴 맵에 들어설 때 올린다(동굴의 두
# 출구가 모두 필드라 같은 일)
CAVE_TALKED = (0x58, 0x01)      # 7E:21E8 bit0  (FC $6281&04)
CAVE_STEP1 = (0x58, 0x02)       # 7E:21E8 bit1  차례 1(FC $6281&03 = 1)
CAVE_STEP2 = (0x58, 0x04)       # 7E:21E8 bit2  차례 2
OLD_MAN_TRIED = (0x06, 0x80)    # 7E:2196 bit7  성 앞 노인이 따라나섰다가 지침(FC $6289&10). DQ5 롬에 참조가 없는 비트

# 보스를 이긴 뒤 FC 가 바꾸는 인물 목록(1C:$841E 등, $6283&80 으로 고름). dq4npcport.port 가 이 상태로 뽑아
# 「상태-맵」 이름의 새 목록으로 돌려주고, 보스 깃발에 그 목록을 쓴다. 왕좌의 방은 왕의 보고와 함께
AFTER_BOSS = 'after_boss'
ALT_STATES = ((AFTER_BOSS, {0x6283: 0x80, 0x6288: 0x80}, ('36/00', '36/03', '37/00', '37/01', '39/01', '39/03')),)
SOLDIER_MAP, KIDS_HOME_MAP = '39/01', '37/00'


def alt_name(state, m):
    """ALT_STATES 목록의 이름(dq5npcrelocate 의 새 목록 이름은 영문·숫자·_- 만)."""
    return f"{state}-{m.replace('/', '')}"


FC_SOLDIER = 0x148
SOLDIER_PATH = ((0x0E, 0x18), (0x0E, 0x16), (0x0B, 0x16), (0x0B, 0x14))
KIDS_HOME_ROW = 0x17            # FC 1D 이벤트 33: 12/00 에서 일행이 이 줄에 오면 아이들이 엄마에게 간다
# 엄마 곁의 두 아이(FC 12/00 슬롯 19·13)는 따라옴 깃발이 꺼질 때 일행 뒤에서 나타나 집으로 걷는다(FC 레코드 09·17 의
# 길). FC 는 일행 그림 자리에 세우지만 여기서는 통로 아래 칸에서 나타나고, 주인공을 지나가도록 1C 를 켠다.
# (FC 집 칸, 나타나는 칸, 길, 마지막 방향)
KIDS_WALK_HOME = (((0x0E, 0x12), (0x0E, 0x19), ((0x0E, 0x12),), 0x22),
                  ((0x0C, 0x11), (0x0D, 0x19), ((0x0D, 0x13), (0x0C, 0x13), (0x0C, 0x11)), 0x22))
KIDS_FC_WALKERS = ((0x17, 0x1A), (0x16, 0x1A))  # FC 가 일행 자리로 옮겨 걷게 하는 슬롯 0F·17. 여기서는 집의 아이가 걷는다

# 보스 뒤 왕좌의 방(FC 1C:$8184). 병사 8명이 카펫에 두 줄로 섰다가 주인공이 Y=19 줄에 오면(1D 이벤트 36) 통로 양옆으로
# 갈라서고, 주인공이 (10,15)에 오면 왕이 말을 건다(1D 이벤트 37). FC 는 일행을 (10,15)까지 자동으로 걷게 하지만 여기서는
# 걷는 것은 플레이어가 하고 그 줄에 오면 왕이 말한다. 병사·왕·대신은 말을 걸면 아무도 없다(FC 02F0)
THRONE_KING, THRONE_MINISTER = (0x10, 0x13), (0x0F, 0x13)
THRONE_GUARDS = (((0x0E, 0x1A), 'right'), ((0x11, 0x1A), 'left'))   # FC 대화 26A(0609)
LINEUP_ROW, KING_ROW = 0x19, 0x15
# (처음 칸, 길, 마지막 방향 31E0). 옆으로만 가면 이웃 병사에 막히므로 한 칸 올라선 뒤 옆으로 간다
THRONE_SOLDIERS = (
    ((0x0F, 0x18), ((0x0F, 0x17), (0x0E, 0x17)), 0x11), ((0x10, 0x18), ((0x10, 0x17), (0x11, 0x17)), 0x22),
    ((0x0F, 0x16), ((0x0F, 0x15), (0x0E, 0x15)), 0x11), ((0x10, 0x16), ((0x10, 0x15), (0x11, 0x15)), 0x22),
    ((0x11, 0x18), (), 0x22), ((0x11, 0x16), (), 0x22), ((0x0E, 0x18), (), 0x11), ((0x0E, 0x16), (), 0x11))
# 레벨이 오를 때 띄우는 능력치: (23:EB50 이 오른 양을 두는 $00~ 의 자리, 이름). FC 차례(ちから·すばやさ·たいりょく·
# かしこさ·うんのよさ·さいだいHP·さいだいMP)를 따르되 たいりょく 자리에 DQ5 의 みのまもり. 이름은 전투 메시지 C0~C6 과 같게
STATS = ((2, '힘이'), (3, '민첩성이'), (6, '몸 지키기가'), (4, '영리함이'), (5, '운이'), (0, '최대 HP가'), (1, '최대 MP가'))
NUMBER, WAIT_END = 0x1004, 0x1010
GIFT_EXP = 3000                 # FC 1D 이벤트 37: 경험치를 프레임마다 10씩 300번 더함(실측: ライアン 0 → 3000)
HERO_EXP = 0x7E204B             # 일행 첫 기록 +B~+D
HERO_LEVEL = 0x7E2052           # 일행 첫 기록 +12

# 탑 위 30/04: 주인공이 X≥16, Y=12 에 오면 잡힌 아이(슬롯 08, (17,0D))가 (17,11)까지 와서 운다(1D 이벤트 04, 02F5).
# 이기면 철창(블록 12·13·16·17, (10~11,0C~0D))을 바닥으로 바꾸고(슬롯 0D·0E 의 BRK 1E 09) 아이들이 걸어 나온다
CRY_FROM, CRY_ROW, CRY_TO = 0x16, 0x12, (0x17, 0x11)
CAGE, CAGE_FLOOR_DX = (0x10, 0x0C), 2   # 철창 왼쪽 위 FC 칸, 같은 줄에서 바닥 블록 06 이 있는 칸까지(FC 칸)
# 구한 아이(슬롯 0C·0D·0E)가 걸어 나가 서는 길. FC 는 0D 가 (13,0D)→(17,0E), 0E 가 (17,0C) 이지만 두 길이 엇갈려,
# 한 줄씩 곧장 나오게 바꿨다
# (처음 칸, 길)
RESCUED_PATHS = {0x0C: ((0x17, 0x13), ((0x17, 0x0F),)), 0x0D: ((0x0F, 0x0C), ((0x17, 0x0C),)),
                 0x0E: ((0x0F, 0x0D), ((0x17, 0x0D), (0x17, 0x0E)))}

FRONT, FRONT_NIGHT, IMURU, JAIL = '36/00', '36/03', '37/00', '37/02'
UNDER_WELL, HOIMIN_ROOM = '3B/00', '3B/03'
TOWER_HALL, TOWER_TOP = '39/00', '39/04'
# FC 대화 번호
FC_KIDNAPPER = 0x45            # 탑 입구의 마물 그림(아이는 15)
FC_CHILD, FC_ALEX_NIGHT, FC_FLARE_DAY, FC_FLARE_NIGHT, FC_JAIL_FLARE, FC_HOIMIN = 0x12, 0x13, 0x0F, 0x10, 0x17, 0x15
FC_OLD_MAN, FC_BRAGGART = 0x00A, 0x019   # 성 앞 노인(예·아니요), 보스 뒤 성 앞 사내(예·아니요 둘 다 079E)


def _pages(*lines):
    """말하는 이가 쪽마다 바뀌는 메시지. lines: (이름, 쪽 문장)."""
    out = []
    for name, text in lines:
        if out:
            out.append(ch1.PAGE)
        out += speak(name, text)[:-1]
    return out + [ch1.END]


# 메시지 차례가 곧 번호 차례다(옮긴 메시지 뒤 k 번째). 이미 옮긴 줄은 dq4ch1talk 의 한글을 그대로 쓴다
MESSAGES = {
    'child': dq4ch1talk.TEXTS[(0x528,)],
    'alex_night': dq4ch1talk.TEXTS[(0x52E,)],
    'flare_day': ch1.FRONT_TEXTS[(0x78D,)],
    'flare_night': dq4ch1talk.TEXTS[(0x78F,)],
    # FC 078E
    'flare_ask': say('네? 남편 알렉스가/도둑질을 해서/이무르 마을에……!?', '전사님!/이무르 마을까지/데려가 주세요!'),
    # FC 0304. 원작은 한 쪽에 두 사람의 말이 섞이지만, 말하는 이 표시가 쪽마다라 한 사람씩 쪽을 나눈다
    'reunion': _pages(('프레아', '여보! 당신이군요!?'), ('알렉스', '아줌마 누구야?'),
                      ('프레아', '저를 모르겠어요?/당신의 아내/프레아예요!'), ('알렉스', '…………'),
                      ('프레아', '자, 이래도/생각나지 않아요?/퍼프퍼프퍼프……'), ('알렉스', '…………'),
                      ('알렉스', '……프레아!'), ('프레아', '그래요! 저예요!'),
                      ('알렉스', '나 원 참, 내가/이런 꼴이 되다니……'),
                      ('알렉스', '괴물들에게 습격당해/겁에 질린 나머지/아이로 돌아갔던/모양이오.'),
                      ('알렉스', '거기 전사님./정말 고맙습니다.'),
                      ('알렉스', '아, 그렇지./이건 아이들한테/들은 이야기인데요……')),
    'hint': dq4ch1talk.TEXTS[(0x342,)],
    # 우물 아래의 아이 목소리(FC 1D 이벤트 05·09 02EC, 08 02ED, 07·0B 02EE)
    'voice_here': say('이쪽으로 와……'),
    'voice_not': say('그쪽이 아니야.'),
    'voice_back': say('그쪽으로 가면/돌아가 버려……'),
    # FC 0793 → 예 0794(합류 서술) / 아니요 0795
    'hoimin_ask': say('나는 호이민./지금은 호이미/슬라임이지만/사람이 되는 게 꿈이야.',
                      '있잖아, 사람의/동료가 되면/사람이 될 수/있을까……?', '나를 동료로/삼아 줘!'),
    'hoimin_yes': say('야호! 고마워!')[:-1] + [ch1.PAGE] + ch1.narrate('호이민이 동료가 되었다!'),
    'hoimin_no': say('뭐? 안 된다고?/그래도 마음이 바뀌면/또 와 줘.'),
    # FC 02F4
    'kidnap': say('자, 따라와! 꼬마!', '으앙, 무서워!/놔 줘……!'),
    # 탑 위 보스: 079C → 전투 → 0320. 구한 아이: 0321
    'boss_taunt': say('목숨 아까운 줄/모르는 녀석!/그렇게 죽고 싶다면/소원을 들어주마!'),
    'boss_dies': say('이 몸이 지다니……',
                     '하지만 다른 마물들이/반드시 용사를/찾아내어 그 숨통을/끊어 놓을 것이다……',
                     '너희 인간들은 머지않아/제왕님의 제물이/될 것이다.', '지옥에서 기다리마……/크윽!'),
    'kids_thanks': say('와아! 아저씨/고마워!', '우리 돌아갈 수 있구나!/위에서 뛰어내리면/돌아갈 수 있대!'),
    'soldier_report': dq4ch1talk.TEXTS[(0x796,)],
    'kids_home': dq4ch1talk.TEXTS[(0x5F6,)],
    # 왕(FC 1D 이벤트 37): 아이들이 아직 따라오면 0343, 아니면 0344 → 0345. FC 는 그 뒤 선물(경험치로 보임)을 준다
    'king_back': say('오오, @!/잘 돌아왔다!', '자, 어서 아이들을/이무르 마을에/돌려보내 주어라!',
                     '그대의 보고는/그 뒤에 듣겠노라!/가거라, @!'),
    'king_praise': say('오오, @!/잘 돌아왔다!', '이번 그대의 공은/참으로 훌륭하였노라.',
                       '그대 같은 신하를/두어 짐은 무척/자랑스럽구나!',
                       '그렇지! 상을/내리겠노라!/무언가 바라는 것은/없느냐? 말해 보거라.',
                       '뭐라? 여행을/떠나고 싶다고!?')[:-1] + [ch1.PAGE] + say('……………')[:-1] + [ch1.PAGE] +
                   say('그렇다면 그대는/아직 아이인 용사를/찾아내어 지키고/싶다는 것이로구나……',
                       '알겠노라!/그것이 그대의/바람이라면 더는/말리지 않겠노라!',
                       '@!/이것은 짐이 주는/작별의 선물이니라!/받거라!'),
    'king_farewell': say('@!/부디 조심해서/가거라!'),
    # FC 0346(1A:$B829): 같은 방문에 성 앞에 들어서면. 이름 뒤 조사를 피해 옮김
    'chapter_end': ch1.narrate('이리하여 이 땅/어딘가에 있는 용사를/찾아 @의 여행이/시작되었다……'),
    # 보스 뒤 왕좌의 방 문지기(FC 0609)
    'guard_wait': say('자!/임금님께서 기다리고/계십니다!'),
    # FC 「ライアンは レベルが あがった！」. 이름 뒤 조사를 피해 옮김. 레벨업 줄은 한 창에 이어 쓰고 줄마다 ▼ 로 기다린다
    'level_up': ch1.narrate('@의 레벨이 올랐다!')[:-1] + [WAIT_END],
    # 오른 능력치(FC 「ちからが 3ポイント あがった！」). 수는 {1004} 가 $F5~$F7 에서 찍는다
    **{f'stat_{k}': [ch1.NARR, f'{name} ', NUMBER, '포인트 올랐다!', WAIT_END] for k, name in STATS},
    # FC 02F5
    'cry': say('으앙, 으앙……/살려 줘!'),
    # 41 동굴 병사(FC 대화 014): 차례 0·1·2 에 0790·0791·0792, 보스 뒤 079F
    'cave_0': say('오오, @!/나도 이제부터/이무르 마을에/가려던 참이다.'),
    'cave_1': say('곤란하군……/아무래도 길을/잃은 모양이다……'),
    'cave_2': say('뭐? 출구까지/데려다주겠다고?', '쓸데없는 참견이다,/@./나는 내 힘으로/나가 보이겠다!'),
    'cave_after': say('뭐? 벌써 아이들을/구했다고?/으헉!'),
    # 왕의 방 왕(FC 대화 00B): そらとぶくつ 를 가졌으면 0786, 아니면 0785. 둘 다 060A 가 잇는다
    'king_room': dq4ch1talk.TEXTS[(0x785, 0x60A)],
    'king_shoes': say('@여, 잘/돌아왔도다!', '그 자신 있어 보이는/얼굴을 보니 무언가/알아낸 모양이로구나.',
                      '흠흠……/뭐라, 하늘을 나는/구두라고?/그랬던 것이로구나……', '아무튼 한시라도/빨리 아이들을/데려오도록 하라.',
                      '그대의 활약을/기대하고 있노라./@여.'),
    # 탑의 병사(FC 대화 148): 0797 뒤 호이민이 일행에 있으면 0798
    'tower_soldier': dq4ch1talk.TEXTS[(0x797,)],
    'tower_soldier_hoimin': dq4ch1talk.TEXTS[(0x797,)][:-1] + [ch1.PAGE] + say('자네가 부럽군.'),
    # 성 앞 노인(FC 대화 00A): 0787 → 예 0788(깃발) / 아니요 078A. 깃발 뒤에는 0789
    'old_man_ask': say('언제 보아도/참으로 훌륭한/성이로구먼.', '나도 성의 전사가/되어 보고 싶구먼./어떤가? 데려가/주지 않겠나?'),
    'old_man_yes': say('오오, 정말인가!?/그럼 따라가기로/하지!'),
    'old_man_no': say('역시 그렇겠지./허허, 무리한 부탁을/해서 미안하구먼.'),
    'old_man_tired': say('헉헉……/역시 늙은이에게는/무리인 모양일세.', '신경 쓰지 말고/가 보게나.'),
    # 보스 뒤 성 앞 사내(FC 대화 019): 079D → 예·아니요 어느 쪽이든 079E
    'brag_ask': say('@! 해냈구나!/그런데 부탁이/있는데……', '아이들을 구한 건/이 몸이라는 걸로/하고 공을 양보해/주지 않겠나?'),
    'brag_joke': say('와하하, 농담이야!/자넨 정말/사람이 좋구먼!'),
}


def message_ids(first):
    """{이름: 메시지 번호}. first 는 옮긴 메시지 다음 번호(dq4npcport.FIRST_MESSAGE + 옮긴 메시지 수)."""
    return {name: first + k for k, name in enumerate(MESSAGES)}


def texts(first):
    return {first + k: parts for k, parts in enumerate(MESSAGES.values())}


TALKS = ('child', 'alex_night', 'flare_day', 'flare_night', 'hoimin', 'boss', 'soldier', 'king', 'guard',
         'cave_soldier', 'king_room', 'tower_soldier', 'old_man', 'braggart')
SKY_SHOES = 0xCD                # DQ5 ソラトブクツ(FC そらとぶくつ 6C 자리)


def talk_numbers(first_talk):
    """{이름: 대화 번호}. first_talk 는 서장 스크립트 다음 번호."""
    return {name: first_talk + k for k, name in enumerate(TALKS)}


# DQ5 「その方向には誰もいない。」: the answer when the person talked to is hidden.
NOBODY = 0x129


def start_messages(first_message):
    """{(map, FC talk, night or None for both): first message} of the people this module changes, at the start
    of chapter 1 (no event flag on): the talk scripts show their first message, and the jail's Flares hide."""
    m = message_ids(first_message)
    return {(IMURU, FC_CHILD, True): m['child'], (JAIL, FC_ALEX_NIGHT, True): m['alex_night'],
            (FRONT, FC_FLARE_DAY, False): m['flare_day'], (FRONT_NIGHT, FC_FLARE_NIGHT, True): m['flare_night'],
            (JAIL, FC_JAIL_FLARE, None): NOBODY, (HOIMIN_ROOM, FC_HOIMIN, None): m['hoimin_ask'],
            (CAVE, FC_CAVE_SOLDIER, None): m['cave_0'], (KING_ROOM, FC_KING_ROOM, None): m['king_room'],
            (SOLDIER_MAP, FC_SOLDIER, None): m['tower_soldier'], (FRONT, FC_OLD_MAN, False): m['old_man_ask']}


def _msg(m):
    return {"op": "msg", "id": f"{m:03X}"}


def _flag_on(flag):
    return {"op": "flag-on", "index": flag[0], "mask": flag[1]}


def _if(flag, then, otherwise=None):
    out = {"op": "if", "cond": {"code": "1B", "index": flag[0], "mask": flag[1]}, "then": then}
    # 갈래 안의 조건문은 블록(목록)이어야 한다(dq5talkwrite)
    if isinstance(otherwise, dict) and otherwise["op"] == "if":
        otherwise = [otherwise]
    return {**out, "else": otherwise} if otherwise is not None else out


def _flare(m, otherwise):
    return [{"op": "if", "cond": {"code": "1B", "index": NIGHT_TOLD[0], "mask": NIGHT_TOLD[1]},
             "then": [_msg(m['flare_ask']), _flag_on(FLARE_FOLLOWS)], "else": _msg(m[otherwise])}]


def talk_scripts(first_message):
    """dq5talk/1 의 scripts 에 TALKS 차례로 더할 본문."""
    m = message_ids(first_message)
    return [
        [_msg(m['child']), _flag_on(NIGHT_TOLD)],
        [_msg(m['alex_night']), _flag_on(NIGHT_TOLD)],
        _flare(m, 'flare_day'),
        _flare(m, 'flare_night'),
        # 예면 합류 깃발. 일행 기록은 호이민 인물 스크립트가 그 깃발을 보고 쓴다(대화 네이티브는 뱅크 06 안이어야 함)
        # 합류 팡파르는 FC 처럼 「동료가 되었다!」 를 띄운 채 울린다(FC 0794 끝의 {SOUND:1A}{STOP})
        [_msg(m['hoimin_ask']), {"op": "if", "cond": {"code": "05"},
                                 "then": [_msg(m['hoimin_yes']), {"op": "call", "target": f"{FANFARE_AT & 0xFFFF:04X}"},
                                          _flag_on(HOIMIN)],
                                 "else": _msg(m['hoimin_no'])}],
        # 전투는 뱅크 06 의 BATTLE_AT 이 건다. 이기면 그 루틴이 보스 깃발을 켠다
        [_msg(m['boss_taunt']), {"op": "call", "target": f"{BATTLE_AT & 0xFFFF:04X}"},
         {"op": "if", "cond": {"code": "1B", "index": BOSS_WON[0], "mask": BOSS_WON[1]}, "then": _msg(m['boss_dies'])}],
        [_msg(m['soldier_report']), _flag_on(SOLDIER_LEFT)],
        [{"op": "if", "cond": {"code": "1B", "index": REPORTED[0], "mask": REPORTED[1]},
          "then": _msg(m['king_farewell']),
          "else": [{"op": "if", "cond": {"code": "1B", "index": KIDS_FOLLOW[0], "mask": KIDS_FOLLOW[1]},
                    "then": _msg(m['king_back']),
                    "else": [_msg(m['king_praise']), _msg(m['king_farewell']), _flag_on(REPORTED)]}]}],
        [_msg(m['guard_wait'])],
        [_if(BOSS_WON, _msg(m['cave_after']),
             _if(CAVE_STEP2, _msg(m['cave_2']),
                 _if(CAVE_STEP1, [_msg(m['cave_1']), _flag_on(CAVE_TALKED)], [_msg(m['cave_0']), _flag_on(CAVE_TALKED)])))],
        [{"op": "if", "cond": {"code": "11", "item": SKY_SHOES}, "then": _msg(m['king_shoes']),
          "else": _msg(m['king_room'])}],
        # FC 는 호이민이 일행에 있는지 보지만, 1장에서 호이민은 합류한 뒤 떠나지 않아 합류 깃발과 같다
        [_if(HOIMIN, _msg(m['tower_soldier_hoimin']), _msg(m['tower_soldier']))],
        # FC 는 예면 깃발을 켜고 노인을 일행 쪽으로 걷게 한다(15:9D36, 슬롯 0E 의 간격 33). 여기서는 깃발만
        [_if(OLD_MAN_TRIED, _msg(m['old_man_tired']),
             [_msg(m['old_man_ask']), {"op": "if", "cond": {"code": "05"},
                                      "then": [_flag_on(OLD_MAN_TRIED), _msg(m['old_man_yes'])],
                                      "else": _msg(m['old_man_no'])}])],
        [_msg(m['brag_ask']), {"op": "if", "cond": {"code": "05"}, "then": _msg(m['brag_joke']),
                               "else": _msg(m['brag_joke'])}],
    ]


# 인물 스크립트를 빌리는 DQ5 인물: 이 해킹에서 가지 않는 DQ5 03/03 의, 스크립트가 있는 한 벌(낮·밤 따로) 인물.
# 두 벌 인물은 한 시간대에만 둘 수 없다(dq5npcrelocate 가 거부)
FLARE_SRC, FLARE_SCRIPT = {"list": "05:9180", "index": 0}, "05:9187"
WALKER_SRC, WALKER_SCRIPT = {"list": "05:9180", "index": 1}, "05:919F"
VOICE_SRCS = (({"list": "05:9180", "index": 2}, "05:91B7"), ({"list": "05:9180", "index": 3}, "05:91CF"),
              ({"list": "05:9768", "index": 1}, "05:9788"), ({"list": "05:9768", "index": 2}, "05:979E"),
              ({"list": "05:9768", "index": 3}, "05:97B8"))
CAVE_STEP_SRC, CAVE_STEP_SCRIPT = {"list": "05:9768", "index": 4}, "05:97D2"
HOIMIN_SRC, HOIMIN_SCRIPT = {"list": "05:9180", "index": 4}, "05:91EB"
KIDNAPPER_SRC, KIDNAPPER_SCRIPT = {"list": "05:9180", "index": 5}, "05:9207"
KID_SRC, KID_SCRIPT = {"list": "05:9239", "index": 1}, "05:9248"
HIDE_ON_WIN_SRC, HIDE_ON_WIN_SCRIPT = {"list": "05:9239", "index": 3}, "05:927B"
RESCUED_SRC, RESCUED_SCRIPT = {"list": "05:9239", "index": 4}, "05:92B3"
THANKS_SRC, THANKS_SCRIPT = {"list": "05:90D0", "index": 6}, "05:9102"
SOLDIER_SRC, SOLDIER_SCRIPT = {"list": "05:90D0", "index": 7}, "05:910F"
KIDS_HOME_SRC, KIDS_HOME_SCRIPT = {"list": "05:90D0", "index": 8}, "05:9126"
ENDER_SRC, ENDER_SCRIPT = {"list": "05:90D0", "index": 9}, "05:9155"
# 03/05 의 남은 한 벌 스크립트 인물
_SPARE = ((5, "05:9304"), (7, "05:9358"), (8, "05:93A9"), (15, "05:9421"), (16, "05:942C"), (17, "05:9479"),
          (18, "05:94CB"), (19, "05:94E6"), (20, "05:94F1"), (21, "05:951D"))
_SPARE = [({"list": "05:9239", "index": i}, at) for i, at in _SPARE]
# 병사: 걷는 넷은 하나씩, 돌기만 하는 넷은 방향마다 하나
SOLDIER_SRCS = _SPARE[:4] + [_SPARE[4], _SPARE[4], _SPARE[5], _SPARE[5]]
KING_CALL_SRC, KING_CALL_SCRIPT = _SPARE[6]
CRY_SRC, CRY_SCRIPT = _SPARE[7]
RESCUED2_SRC, RESCUED2_SCRIPT = _SPARE[8]
HOME_KID_SRCS = (_SPARE[9], ({"list": "05:9768", "index": 0}, "05:976F"))
END_MAP = '36/00'               # 1장 끝은 보고한 뒤 성 앞에 들어설 때(FC 는 같은 방문 안, $6285 는 필드로 나가면 지워짐)
# 탑 위 30/04 의 FC 인물 슬롯(06 부터 차례): 06 보스, 07·08 잡힌 아이, 09 마물은 이기면 숨고, 0C~0E 의 구한 아이는
# 이기기 전에 숨는다(1C:$A266). 0C 가 고맙다고 말한다
TOP_HIDE_ON_WIN, TOP_RESCUED, CRY_SLOT = (0x06, 0x07, 0x08, 0x09), (0x0C, 0x0D, 0x0E), 0x08
FIRST_SLOT = 0x06
# 보스 전투: DQ5 빈 이벤트 무리 30 에 FC 무리 05(ピサロのてさき·おおめだま 한 마리씩).
# 01:868B 는 전투 뒤 01:8715 로 가서, 지면(A = 80) 보통 전투처럼 전멸 처리(01:88ED)를 한다
BOSS_GROUP = 0x30
# FC 몬스터를 DQ5 이벤트 보스 번호에 덮는다. 둘 다 이 해킹에서 나오지 않는 DQ5 이벤트 전투에만 쓰이고, 필드 조우
# (dq4fieldencounter.MONSTERS)에도 없다. 그림은 DQ5 그림 그대로
BOSS_MONSTERS = {0xE2: (0xB3, '피사로의 부하'),     # ザイル 자리에 ピサロのてさき
                 0x52: (0x29, '큰 눈알')}           # ゴンズ 자리에 おおめだま
BOSS_MEMBERS = tuple((dq5, 1) for dq5 in BOSS_MONSTERS)
# FC 행동 번호(dq4-data-format 「몬스터 행동 번호」) → DQ5 행동: 00 メラ, 03 ギラ, 32 공격, 3C 불 숨결(4D),
# 58 「かおいろが かわった」(69, 메시지만) → ようすをみる, 30 みをまもっている(41)
FC_ACTIONS = {0x00: '39', 0x03: '3C', 0x32: '73', 0x3C: '8E', 0x58: '66', 0x30: '71'}
BOSS_FLAGS = 0x40 | 0x02                    # 도망칠 수 없음, 보스 곡
BATTLE_AT = 0x06FF00                        # 대화 스크립트의 네이티브는 뱅크 06 안(06:FE10~ 의 덧붙인 대화 훅 뒤)
FANFARE_AT = 0x06FF40                       # 합류 팡파르. 같은 뱅크 06 의 BATTLE_AT 뒤
JOIN_SONG = 0x26                            # 곡 자리 26 = NDS 「仲間が加わった」(dq4-sound-port-format)


def fc_monster(prg, fc_id):
    """FC 몬스터 레코드(18:$8046 + 22 × ID)에서 DQ5 몬스터 표(dq5tables)의 필드."""
    import dq4data
    r = next(rec for i, _, _, _, rec in dq4data.monsters(prg) if i == fc_id)
    ten = lambda lo, hi: r[lo] | (r[hi] & 3) << 8  # noqa: E731
    return {"HP": ten(4, 15), "MP": r[3], "민첩": r[2], "공격": ten(5, 16), "수비": ten(6, 17),
            "경험치": r[0] | r[1] << 8, "금화": ten(7, 18), "행동수": 0, "재생": 0, "동료확률": 0, "드롭": "FF",
            **{f"행동{k + 1}": FC_ACTIONS[r[9 + k] & 0x7F] for k in range(6)}}


def monster_doc(prg):
    return {"format": "dq5tables/1", "monsters": [{"id": f"{dq5:02X}", **fc_monster(prg, fc)}
                                                  for dq5, (fc, _) in BOSS_MONSTERS.items()]}


# FC ライアン 은 주문을 배우지 않는다(fc dq4-data-format 「주문이 없는 トルネコ·ライアン·アリーナ」). DQ5 주인공 습득 표를
# 그대로 두면 선물 레벨업(1 → 9)만으로 필드 2·전투 4개를 말없이 배웠다(실측)
def learn_doc():
    return {"format": "dq5learn/1", "characters": [{"kind": "person", "index": 0, "learn": []}]}


def encounter_doc():
    return {"format": "dq5encounter/1", "event_groups": [
        {"index": BOSS_GROUP, "flags": BOSS_FLAGS, "members": [{"monster": k, "count": n} for k, n in BOSS_MEMBERS]}]}


def _fanfare():
    """곡을 틀고 끝날 때까지 기다린 뒤 맵 곡($194B)을 다시 튼다. DQ5 06:F79A 처럼 BRK 0F 로 틀고 24:FF0F(같은 곡 번호)로
    끝나기를 기다린다. 24:FF0F 만 부르면 틀지 않은 곡이라 곧바로 돌아왔다. 맵 곡은 00:CE61(20:8218)이 아니라 24:FE9A 로
    튼다: 팡파르가 끝나 지금 곡 $1D8B 가 FF 인 채 00:CE61 을 부르면 돌아오지 않았다(실측). BRK 는 DB 를 부른 뱅크로
    두므로 WRAM 거울이 있는 뱅크 06 에서 부른다."""
    return bytes((0x08, 0xE2, 0x20, 0x00, 0x0F, JOIN_SONG,                    # PHP / SEP #$20 / BRK 0F 곡
                  0xA9, JOIN_SONG, 0x22, 0x0F, 0xFF, 0x24,                     # LDA #곡 / JSL 24:FF0F
                  0xAD, 0x4B, 0x19, 0x29, 0x7F, 0x22, 0x9A, 0xFE, 0x24,        # LDA $194B / AND #$7F / JSL 24:FE9A
                  0x28, 0x60))                                                 # PLP / RTS


def _battle():
    flag = 0x7E2190 + BOSS_WON[0]
    return bytes((0x00, 0x0E, 0xA9, BOSS_GROUP, 0x22, 0x8B, 0x86, 0x01,       # BRK 0E / LDA #무리 / JSL $01868B
                  0xC9, 0x80, 0xF0, 0x0A, 0xAF)) + _al(flag) + bytes((0x09, BOSS_WON[1], 0x8F)) + _al(flag) + b'\x60'


# 탑 입구 30/00: 주인공이 이 줄(FC Y)에 오면 마물이 아이를 데리고 계단(09,03) 쪽으로 간다(FC 1D 이벤트 02)
KIDNAP_ROW, KIDNAP_TO = 0x09, 0x03
# 목소리: (맵, 메시지, そらとぶくつ 를 가졌으면 나지 않는지, 칸). 칸은 (FC X, FC Y, 바라보는 방향 0 위·1 오른쪽·2 아래·
# 3 왼쪽)이고 어느 칸에 그 방향으로 서면 뜬다. FC 는 뜬 뒤 그 무리의 칸을 모두 벗어날 때까지 다시 띄우지 않는다
# ($627C 비트, 1D:99F1·9A5F 의 표 1D:9A41~·9A7D~). 02ED 의 무리만 구두를 보지 않는다(1D:9A31 CMP #$40)
VOICES = ((UNDER_WELL, 'voice_here', True, ((0x14, 0x0C, 3), (0x14, 0x0D, 3), (0x0A, 0x19, 2), (0x0B, 0x19, 2),
                                            (0x0D, 0x26, 1), (0x0D, 0x27, 1))),
          (UNDER_WELL, 'voice_back', False, ((0x11, 0x0C, 3), (0x11, 0x0D, 3))),
          (UNDER_WELL, 'voice_not', True, ((0x02, 0x19, 0), (0x03, 0x19, 0), (0x0C, 0x1A, 1), (0x0C, 0x1B, 1),
                                           (0x10, 0x26, 1), (0x10, 0x27, 1))),
          (HOIMIN_ROOM, 'voice_here', True, ((0x12, 0x12, 0), (0x13, 0x12, 0), (0x11, 0x2A, 1), (0x11, 0x2B, 1))),
          (HOIMIN_ROOM, 'voice_not', True, ((0x14, 0x10, 1), (0x14, 0x11, 1), (0x11, 0x1C, 3), (0x11, 0x1D, 3),
                                            (0x14, 0x1C, 1), (0x14, 0x1D, 1), (0x14, 0x2A, 1), (0x14, 0x2B, 1))))
FACING = (0x80, 0x10, 0x40, 0x20)   # FC 방향 → DQ5 7E:31E0 위 니블
CAVE, FC_CAVE_SOLDIER, FC_KING_ROOM, FC_TOWER_SOLDIER = '3A/00', 0x014, 0x00B, 0x148
KING_ROOM = '36/02'

CODE_AT = 0x5ED000              # 서장 코드(5E:C000) 뒤의 빈 자리
COMPANION = 0x23AED1            # 동료 표: 종류마다 9바이트(처음 레벨, 최대 레벨, 능력치 넷, HP, MP, 장비 갈래)
HOIMIN_KIND = 0x05              # ホイミスライム. 이름 0 이 「ホイミン」
GUEST = 0xC0                    # 일행 기록 +0: bit7 몬스터 동료, bit6 손님
SCRATCH = 0x7E1BC6              # 7E:1BBE~ 의 DQ5 가 쓰지 않는 자리(서장이 1BC4 까지 씀)
PARTY_OBJECTS = 0x05D89D        # 걷는 일행 그림을 일행 기록대로 다시 세움(02:C7E4 를 거침)
REFRESH = bytes((0xE2, 0x30, 0x22)) + PARTY_OBJECTS.to_bytes(3, 'little')
# 따라 걷는 그림. 맵을 불러올 때(02:CA29)와 일행이 바뀔 때(05:D89D → 02:C7E4) 모두 02:C634 가 걷는 그림 수 7E:1967 을
# 정한다. 그 끝(STA $1967 / PLP / RTS)을 02 뱅크 빈 자리로 돌려, 따라옴 깃발이 켜진 동안 일행 뒤에 그림을 더한다
COUNT_AT, COUNT_ORIG = 0x02C64F, bytes.fromhex('8d 67 19 28 60')
COUNT_TAIL = 0x02FF60           # sfc/dq5/docs/dq5-build-format.md 「빈 자리 지도」의 02:FF60~
# 맵을 불러올 때만 부르는, 실내면 주인공 그림을 2B 로 두는 루틴. 일행이 바뀔 때도 불러 주인공 그림이 맵을 다시
# 불러온 것과 같게 한다(부르지 않으면 05:D98F 의 2E 로 바뀜, 실측)
HERO_INDOOR = 0x02CA5A
# 2191 bit5 가 꺼져 있으면(1장 롬에서는 꺼져 있음) 맵을 불러올 때 02:B16E 가 걷는 그림을 주인공 하나로
# 줄인다. 그 STA $1967 만 지운다
SOLO_AT, SOLO_ORIG = 0x02B178, bytes.fromhex('8d 67 19')
# 몬스터 동료 그림은 기록 +0 & 7F 로 05:D9E1 표를 읽어 손님 bit6 이 켜진 C5 는 표 밖(0F)을 읽었다. & 3F 로
GUEST_PICTURE_AT, GUEST_PICTURE_ORIG = 0x05D9CE, bytes.fromhex('29 7f')
FC_FLARE_PICTURE, FC_CHILD_PICTURE = 0x13, 0x15
KIDS_WALKING = 2                # FC 는 구한 아이 둘을 일행 자리에 그린다(KIDS_FC_WALKERS)
# 동료가 된 スライム 의 일행 기록(sfc/dq5/tools/lua/dq5warp.lua 의 PARTY_TEMPLATE, 그 밖의 바이트는 동료 표에서)
PARTY_TEMPLATE = bytes((
    0x82, 0x80, 0x08, 0x00, 0x00, 0x00, 0x03, 0x08, 0x05, 0x01, 0x03, 0x00, 0x00, 0x00, 0x08, 0x00,
    0x00, 0x00, 0x01, 0x63, 0x00, 0x00, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF,
    0xFF, 0xFF, 0x00, 0x00, 0x00, 0x00, 0x4B, 0x00, 0x00, 0x02))


def lorom(addr):
    return (addr >> 16 & 0x7F) * 0x8000 + (addr & 0x7FFF)


def companion_record(data, kind):
    """동료 표의 처음 값으로 채운 일행 기록 42바이트."""
    c = data[lorom(COMPANION + kind * 9):][:9]
    r = bytearray(PARTY_TEMPLATE)
    # bit6(손님)을 켜면 작전이 めいれいさせろ 여도 명령 창을 띄우지 않는다(20:9243). FC 의 호이민도 늘 스스로 싸운다
    r[0] = GUEST | kind
    r[0x12], r[0x13] = c[0], c[1]
    r[7:11] = c[2:6]
    r[2] = r[0xE] = c[6]
    r[4] = r[0x10] = c[7]
    return bytes(r)


def _long(a):
    return [a & 0xFF, a >> 8 & 0xFF, a >> 16]


def _al(a):
    return bytes(_long(a))


def _join(record_at):
    """일행 끝(7E:201D 번째)에 record_at 의 기록을 넣고 수·순서를 고친다. 순서 7E:2020·2028 은 기록 번호,
    걷는 수 7E:201E 는 3 까지(넷째부터 마차). 7E:29EA + 종류 는 그 종류의 쓴 이름 비트로 읽음(코드 읽기)."""
    from dq4chapterbox import ENTER, LEAVE
    lo = record_at & 0xFFFF
    body = (bytes((0xC2, 0x30, 0xAF)) + _al(0x7E201D) + bytes((0x29, 0xFF, 0x00, 0x48,   # REP / LDA 수 / AND / PHA
            0x0A, 0x8F)) + _al(SCRATCH) + bytes((0x0A, 0x0A, 0x8F)) + _al(SCRATCH + 2) +   # 2n, 8n
            bytes((0x0A, 0x0A, 0x18, 0x6F)) + _al(SCRATCH) + bytes((0x6F,)) + _al(SCRATCH + 2) +  # 32n + 2n + 8n
            bytes((0x18, 0x69, 0x40, 0x20, 0xA8,                                         # + 2040 / TAY
                   0xA2, lo & 0xFF, lo >> 8, 0xA9, 41, 0x00, 0x54, 0x7E, record_at >> 16,  # LDX / LDA #41 / MVN
                   0x68, 0xE2, 0x20, 0xAA, 0x9F)) + _al(0x7E2020) + bytes((0x9F,)) + _al(0x7E2028) +  # PLA / SEP / TAX
            bytes((0x1A, 0x8F)) + _al(0x7E201D) + bytes((0x8F,)) + _al(0x7E201F) +       # INC / 수 둘
            bytes((0xC9, 0x04, 0x90, 0x02, 0xA9, 0x03, 0x8F)) + _al(0x7E201E) +           # 걷는 수
            bytes((0xAF,)) + _al(0x7E29EA + HOIMIN_KIND) + bytes((0x09, 0x01, 0x8F)) + _al(0x7E29EA + HOIMIN_KIND) +
            REFRESH)
    return ENTER + body + LEAVE


def _voice(cells, shoes, away=False):
    """인물 명령 05 가 부르는 루틴: 주인공이 cells(FC 칸 X, Y, 31E0 위 니블) 가운데 하나에 그 방향으로 서 있으면
    A = 0, 아니면 1. 주인공은 반 칸(셀 하나)씩도 서므로, 셀 (2x 또는 2x+1, 2y+1 또는 2y+2)를 FC 칸 (x, y)로 본다. shoes 면 そらとぶくつ 를 가졌을 때 늘 1(대화 조건 11 의 06:B2B7 처럼 $43 에 물건을 두고
    BRK 88 90. 없으면 $46 bit7 이 켜진다(실측)). away 면 방향과 구두는 보지 않고, 그 칸들을 모두 벗어나야 0."""
    yes = bytes((0xC2, 0x30, 0xA9, 0x00, 0x00, 0x28, 0x6B))
    no = bytes((0xC2, 0x30, 0xA9, 0x01, 0x00, 0x28, 0x6B))
    hit, miss = (no, yes) if away else (yes, no)
    out = bytearray((0x08, 0xE2, 0x30))                                      # PHP / SEP #$30
    if shoes and not away:
        out += DP_SAVE + bytes((0xA9, SKY_SHOES, 0x85, 0x43, 0x64, 0x44, 0x64, 0x45, 0xC2, 0x10,
                                0x00, 0x88, 0x90, 0xE2, 0x10, 0xA5, 0x46, 0xA8)) + DP_RESTORE
        out += bytes((0x98, 0x30, len(no))) + no                               # TYA / BMI(없음) 칸 검사
    for x, y, f in cells:
        tests = [bytes((0xAF, 0x20, 0x30, 0x7E, 0x29, 0xFE, 0xC9, 2 * x)),                 # X & FE = 2x
                 bytes((0xAF, 0x80, 0x30, 0x7E, 0x3A, 0x29, 0xFE, 0xC9, 2 * y))]           # (Y-1) & FE = 2y
        if not away:
            tests.append(bytes((0xAF, 0xE0, 0x31, 0x7E, 0x29, 0xF0, 0xC9, f)))
        block = hit
        for t in reversed(tests):
            block = t + bytes((0xD0, 0)) + block
        # BNE 는 모두 이 칸 블록의 끝(다음 칸)으로
        block = bytearray(block)
        k = 0
        for t in tests:
            k += len(t)
            block[k + 1] = len(block) - (k + 2)
            k += 2
        out += block
    return bytes(out + miss)


def _at(x, y, x_from=False, away=False):
    """인물 명령 05 가 부르는 루틴: 주인공(인물 표 슬롯 0, 7E:3020·3080)이 셀 (x, y) 이면 A = 0, 아니면 1.
    x 가 None 이면 Y 만 보고, x_from 이면 X 는 x 이상인지 본다. away 면 0 과 1 을 바꾼다(그 자리를 떠날 때까지)."""
    near = bytes((0xC2, 0x30, 0xA9, int(away), 0x00, 0x28, 0x6B))
    far = bytes((0xC2, 0x30, 0xA9, int(not away), 0x00, 0x28, 0x6B))
    second = bytes((0xAF, 0x80, 0x30, 0x7E, 0xC9, y, 0xD0, len(near)))
    first = bytes((0x08, 0xE2, 0x20))
    if x is not None:
        first += bytes((0xAF, 0x20, 0x30, 0x7E, 0xC9, x, 0x90 if x_from else 0xD0, len(second) + len(near)))
    return first + second + near + far


WINDOW_ONE = 0x0498FD           # $0A00 의 창 하나를 연다
WINDOW_SET = 0x049905           # $0A48·$0A47·$0A00 의 창 셋을 연다(상태 보기 06·07·08, 00:9477)


def _window(*numbers):
    """창 열기: 번호 하나면 $0A00 → WINDOW_ONE, 셋이면 $0A48·$0A47·$0A00 → WINDOW_SET. BRK 95 핸들러처럼 직접 페이지
    $00~$0F 를 지킨다. M 8·X 16·DB 0 에서."""
    out = bytearray(bytes((0xE2, 0x10)) + DP_SAVE + bytes((0xC2, 0x10)))
    for addr, n in zip((0x0A48, 0x0A47, 0x0A00)[-len(numbers):], numbers):
        out += bytes((0xA9, n, 0x8D, addr & 0xFF, addr >> 8))
    out += bytes((0x22, *_long(WINDOW_SET if len(numbers) == 3 else WINDOW_ONE)))
    return bytes(out + bytes((0xE2, 0x10)) + DP_RESTORE + bytes((0xC2, 0x10)))


# 능력치 창(07)의 경험치 일곱 자리: 창 타일맵 버퍼 7E:5000(32 × 32 칸)의 25행 24~30열(실측). 숫자 타일은 값 + 2, 빈칸 01.
# 높은 바이트(팔레트)는 창이 활성이면 20, 아니면 2C 라 같은 줄 「:」(22열)의 것을 쓴다. 이 줄은 04:9D5E(04:991D)가 거는
# 부분 전송(21~29번째 줄, $0BEC bit6)에 들어간다
EXP_ROW, EXP_COL, EXP_DIGITS, EXP_COLON = 25, 24, 7, 22
TILE_BLANK, TILE_ZERO = 0x01, 0x02
TILEMAP = 0x7E5000
SEND_ROWS = 0x04991D
# FC 처럼 능력치 창(07) 하나만 연다. 상태 보기 셋(06·07·08)을 열면 라벨이 20개 남짓이라 창 글자 엔진의 가나 칸이 모자라
# 캔버스 슬롯을 쓰고, 레벨업 메시지 창이 그 칸을 덮어 라벨이 지워지고 메시지 창에 라벨 그림이 비쳤다(실측)
STATS_WINDOW = 0x07
GIFT_STEP = 20                  # 한 단계가 2프레임(BRK 09 01 과 전송)이라 FC(프레임마다 10, 300프레임)와 같은 시간


def _exp_digits():
    """주인공 경험치(24비트)를 10진 일곱 자리로 능력치 창 버퍼에 쓴다(앞의 0 은 빈칸). M·X 8 에서.
    SCRATCH+0~2 = 남은 값, +3 = 자릿값, +4 = 숫자가 시작됐는지, +5~6 = 빼 본 값."""
    t, d, started, r = SCRATCH, SCRATCH + 3, SCRATCH + 4, SCRATCH + 5
    out = bytearray()
    for k in range(3):
        out += bytes((0xAF,)) + _al(HERO_EXP + k) + bytes((0x8F,)) + _al(t + k)
    out += bytes((0xA9, 0x00, 0x8F)) + _al(started)
    for k in range(EXP_DIGITS):
        p = 10 ** (EXP_DIGITS - 1 - k)
        out += bytes((0xA9, 0x00, 0x8F)) + _al(d)
        trial = (bytes((0x38, 0xAF)) + _al(t) + bytes((0xE9, p & 0xFF, 0x8F)) + _al(r) +
                 bytes((0xAF,)) + _al(t + 1) + bytes((0xE9, p >> 8 & 0xFF, 0x8F)) + _al(r + 1) +
                 bytes((0xAF,)) + _al(t + 2) + bytes((0xE9, p >> 16)))
        keep = (bytes((0x8F,)) + _al(t + 2) + bytes((0xAF,)) + _al(r + 1) + bytes((0x8F,)) + _al(t + 1) +
                bytes((0xAF,)) + _al(r) + bytes((0x8F,)) + _al(t) +
                bytes((0xAF,)) + _al(d) + bytes((0x1A, 0x8F)) + _al(d))
        body = trial + bytes((0x90, len(keep) + 2)) + keep
        out += body + bytes((0x80, (-(len(body) + 2)) & 0xFF))
        cell = TILEMAP + (EXP_ROW * 32 + EXP_COL + k) * 2
        # 숫자가 0 이고 아직 시작 전이며 마지막 자리가 아니면 빈칸
        digit = (bytes((0xA9, 0x01, 0x8F)) + _al(started) + bytes((0xAF,)) + _al(d) +
                 bytes((0x18, 0x69, TILE_ZERO, 0x8F)) + _al(cell))
        blank = bytes((0xA9, TILE_BLANK, 0x8F)) + _al(cell)
        if k < EXP_DIGITS - 1:
            test = bytes((0xAF,)) + _al(d) + bytes((0xD0, len(blank) + 2 + 6)) + bytes((0xAF,)) + _al(started) + \
                bytes((0xD0, len(blank) + 2))
            out += test + blank + bytes((0x80, len(digit))) + digit
        else:
            out += digit
        out += bytes((0xAF,)) + _al(TILEMAP + (EXP_ROW * 32 + EXP_COLON) * 2 + 1) + bytes((0x8F,)) + _al(cell + 1)
    return bytes(out)


def _status_count():
    """능력치 창(STATS_WINDOW)을 열고, 경험치를 프레임마다 GIFT_STEP 씩 GIFT_EXP 만큼 올리며 능력치 창의 숫자를 고친다
    (FC 1D 이벤트 37 의 300번 고리). 창은 열어 둔 채 돌아온다."""
    from dq4chapterbox import ENTER, LEAVE, wait
    count = SCRATCH + 8
    loop = (bytes((0xC2, 0x20, 0xAF)) + _al(HERO_EXP) + bytes((0x18, 0x69, GIFT_STEP, 0x00, 0x8F)) + _al(HERO_EXP) +
            bytes((0xE2, 0x20, 0xAF)) + _al(HERO_EXP + 2) + bytes((0x69, 0x00, 0x8F)) + _al(HERO_EXP + 2) +
            bytes((0xE2, 0x30)) + _exp_digits() + bytes((0xC2, 0x10, 0x22)) + _al(SEND_ROWS) + wait(1) +
            bytes((0xC2, 0x20, 0xAF)) + _al(count) + bytes((0x3A, 0x8F)) + _al(count) + bytes((0xE2, 0x20)))
    back = -(len(loop) + 5)
    loop += bytes((0xF0, 0x03, 0x82)) + (back & 0xFFFF).to_bytes(2, 'little')          # BEQ 끝 / BRL 처음
    steps = GIFT_EXP // GIFT_STEP
    return (ENTER + _window(STATS_WINDOW) + bytes((0xC2, 0x20, 0xA9, steps & 0xFF, steps >> 8, 0x8F)) + _al(count) +
            bytes((0xE2, 0x20)) + loop + LEAVE)


# 전투 끝의 레벨업 고리(25:8A91)가 한 번 오를 때 하는 일에서 메시지만 뺀 것. 그 고리의 메시지는 전투 메시지 길이라
# 필드 창에서는 글자가 깨지고 멈췄다(실측). 23:EB50 은 오른 양을 $00~$09 에 둘 뿐 레벨은 올리지 않아(레벨 1 그대로
# 능력치만 끝없이 올랐음), 기록 +12 를 직접 올린다. 25:8B07 의 BRK 89 80 29 를 따라 부르면 남은 $43~$45 가 경험치를
# 덮었다. 25:8B2F~8BAD 는
# 오른 양마다 BRK 8D 80 필드로 기록에 더하고(둘은 16비트라 $44 를 0 으로), 배운 주문 비트를 BRK 89 80 D2 로 쓴다.
# 21:805A 가 다음 레벨 경험치를 다시 셈하고, 25:8B07 은 팡파르 21 을 울린다(24:FF0F, 20:8218)
LEVEL_UP = 0x23EB50
GROWTH = ((0, 0x06, True), (1, 0x0E, True), (2, 0x1D, False), (3, 0x18, False), (6, 0x1F, False), (4, 0x21, False),
          (5, 0x23, False))


def _level_up():
    """주인공이 경험치로 한 레벨 오를 수 있으면 올리고 보고 깃발을 끄고, 아니면 보고 깃발을 켠다(스크립트가 이 깃발로
    「레벨이 올랐다」를 되풀이할지 고른다)."""
    from dq4chapterbox import ENTER, LEAVE
    flag = 0x7E2190 + REPORTED[0]
    done = bytes((0xAF,)) + _al(flag) + bytes((0x09, REPORTED[1], 0x8F)) + _al(flag)
    up = bytearray(bytes((0xAF,)) + _al(flag) + bytes((0x29, ~REPORTED[1] & 0xFF, 0x8F)) + _al(flag))
    up += bytes((0xA2, 0x09, 0xB5, 0x00, 0x9F)) + _al(SCRATCH) + bytes((0xCA, 0x10, 0xF7))   # $00~$09 를 SCRATCH 로
    up += bytes((0xAF,)) + _al(HERO_LEVEL) + bytes((0x1A, 0x8F)) + _al(HERO_LEVEL)          # 레벨 +1
    for k, field, wide in GROWTH:
        add = bytes((0x85, 0xF5, 0xEB, 0xA9, 0x00)) + (bytes((0x64, 0x44)) if wide else b'') + bytes((0x00, 0x8D, 0x80, field))
        up += bytes((0xAF,)) + _al(SCRATCH + k) + bytes((0xF0, len(add))) + add
    for k in range(3):
        up += bytes((0xAF,)) + _al(SCRATCH + 7 + k) + bytes((0x85, 0x43 + k))
    up += bytes((0x64, 0x42, 0x00, 0x89, 0x80, 0xD2,                                         # STZ $42 / BRK 89 80 D2
                 0xA9, 0x00, 0x22, 0x5A, 0x80, 0x21,                                         # LDA #0 / JSL 21:805A
                 0xA9, 0x21, 0x22, 0x0F, 0xFF, 0x24, 0x22, 0x18, 0x82, 0x20))                # 팡파르
    body = (bytes((0xE2, 0x20, 0xC2, 0x10, 0xA9, 0x00, 0x22)) + _al(LEVEL_UP) +            # SEP / REP / LDA #0 / JSL
            bytes((0xE2, 0x10, 0xB0, len(done) + 3)) + done + bytes((0x82, *len(up).to_bytes(2, 'little'))) + bytes(up))
    return ENTER + body + LEAVE


# 01:C800 의 인물 스크립트 고리가 직접 페이지 앞자리를 쓰므로, 그 자리를 덮는 루틴(25:FA15, 23:EB50 등)을 부르는
# 네이티브는 $00~$0F 를 스택에 두었다가 되돌린다. M·X 8비트에서
DP_SAVE = bytes((0xA2, 0x0F, 0xB5, 0x00, 0x48, 0xCA, 0x10, 0xFA))                 # LDX #$0F / LDA $00,X / PHA / DEX / BPL
DP_RESTORE = bytes((0xA2, 0x00, 0x68, 0x95, 0x00, 0xE8, 0xE0, 0x10, 0xD0, 0xF8))  # LDX #0 / PLA / STA $00,X / INX / CPX / BNE


# 왕의 귀환에서 일행을 걷게 하는 이벤트(dq5-event-format 「명령」 의 00~0F d n: 01 오른쪽, 02 왼쪽, 04 아래, 08 위).
# FC 는 Y=19 줄에서 (10,19)로 옮긴 뒤 (10,15)까지 올라가고(1D 이벤트 38, 일행 움직임 패턴 11·12), 왕의 말 뒤 아래로
# 걸어 (10,19)에서 0345 를 띄우고 그대로 출구로 나간다
AISLE_X = 0x10 * 2                # FC X=10 에 선 주인공의 셀(ch1_cell)
LINEUP_WAIT = 8                 # 가운데 병사가 통로를 비울 때까지 쉬는 걸음 수(C2 하나 8프레임)
UP, DOWN, RIGHT, LEFT = 0x08, 0x04, 0x01, 0x02
KING_STEPS = 2 * (LINEUP_ROW - KING_ROW)
EXIT_ROW = 0x23
OUT_STEPS = 2 * (EXIT_ROW - LINEUP_ROW) + 2   # 출구 줄(셀 71)에서 한 칸 더 내려서야 성 앞으로 나간다(실측)


def _walk_in_event(x):
    dx = AISLE_X - x
    side = bytes((RIGHT, dx)) if dx > 0 else bytes((LEFT, -dx)) if dx < 0 else b''
    return bytes((0xC2,)) * LINEUP_WAIT + side + bytes((UP, KING_STEPS, 0xFF))


def _walk_in(events):
    """주인공 X(7E:3020)에 맞는 이벤트를 건다. events: {X: 이벤트 주소}, 첫 것이 그 밖의 X."""
    from dq4chapterbox import ENTER, LEAVE

    def load(a):
        return bytes((0xA9, a & 0xFF, 0x8D, 0xB3, 0x19, 0xA9, a >> 8 & 0xFF, 0x8D, 0xB4, 0x19, 0xA9, a >> 16, 0x8D, 0xB5, 0x19))
    tail = bytes((0xAD, 0xAE, 0x19, 0x09, 0x80, 0x8D, 0xAE, 0x19))
    xs = list(events)
    body = load(events[xs[0]])
    for x in reversed(xs[1:]):
        branch = load(events[x]) + bytes((0x80, len(body)))
        body = bytes((0xC9, x, 0xD0, len(branch))) + branch + body
    return ENTER + bytes((0xAF, 0x20, 0x30, 0x7E)) + body + tail + LEAVE


def _stat(k):
    """오른 양 SCRATCH+k 를 메시지 수 자리 $F5~$F7 에 둔다. 0 이면 보고 깃발을 켜서 스크립트가 그 줄을 건너뛰게 한다."""
    from dq4chapterbox import ENTER, LEAVE
    flag = 0x7E2190 + REPORTED[0]
    on = bytes((0xAF,)) + _al(flag) + bytes((0x09, REPORTED[1], 0x8F)) + _al(flag)
    off = bytes((0x85, 0xF5, 0x64, 0xF6, 0x64, 0xF7, 0xAF)) + _al(flag) + bytes((0x29, ~REPORTED[1] & 0xFF, 0x8F)) + _al(flag)
    return ENTER + bytes((0xAF,)) + _al(SCRATCH + k) + bytes((0xF0, len(off) + 2)) + off + bytes((0x80, len(on))) + on + LEAVE


CELL_AT = 0x25FA15              # X·Y(8비트) 셀의 셀 버퍼 주소를 [$00] 에(맵 폭 $BF)
REDRAW_LOWER, REDRAW_UPPER = 0x01ED56, 0x01EDF0   # (X, Y) 부터 $1E82×$1E83 셀을 다시 그림(문 열기가 쓰는 것)


def _open_cage():
    """철창 4×4 셀을 같은 줄 오른쪽 바닥 셀의 +1~+7 로 덮고(+0 의 구역·차지 비트는 둠) 다시 그린다."""
    from dq4chapterbox import ENTER, LEAVE
    x0, y0 = CAGE[0] * 2, CAGE[1] * 2
    dx = CAGE_FLOOR_DX * 2
    body = bytearray((0xE2, 0x30)) + DP_SAVE                                  # SEP #$30
    for y in range(y0, y0 + 4):
        for x in range(x0, x0 + 4):
            body += bytes((0xA2, x + dx, 0xA0, y, 0x22)) + _al(CELL_AT)           # LDX / LDY / JSL
            body += bytes((0xA0, 0x07, 0xB7, 0x00, 0xBB, 0x9F)) + _al(SCRATCH) + bytes((0x88, 0xD0, 0xF6))
            body += bytes((0xA2, x, 0xA0, y, 0x22)) + _al(CELL_AT)
            body += bytes((0xA0, 0x07, 0xBB, 0xBF)) + _al(SCRATCH) + bytes((0x97, 0x00, 0x88, 0xD0, 0xF6))
    body += bytes((0xA9, 0x04, 0x8D, 0x82, 0x1E, 0x8D, 0x83, 0x1E))                  # 크기 4×4
    for redraw in (REDRAW_LOWER, REDRAW_UPPER):
        body += bytes((0xA2, x0, 0xA0, y0, 0x22)) + _al(redraw)
    body += bytes((0xE2, 0x30)) + DP_RESTORE
    return ENTER + bytes(body) + LEAVE


# そらとぶくつ: DQ5 의 처리(11:8D77)는 $0B54 = 24 와 필드 (017E,0170)를 두고 날기 루틴(11:80D3)으로 간다.
# FC(12:$B14B)는 필드 (88,16)으로 날아간 뒤 탑 30/00 (09,0C)에 세운다. 첫 명령을 JSL 로 바꿔 이벤트(맵 옮기기)를
# 걸고, 날아가는 곳을 탑 그룹과 그 필드 칸으로 한다
FLY_AT = 0x118D77
FLY_ORIG = bytes.fromhex('a9 24 8d 54 0b')          # LDA #$24 / STA $0B54
FLY_X_AT, FLY_Y_AT = 0x118D7F, 0x118D87
FLY_XY_ORIG = (bytes.fromhex('7e 01'), bytes.fromhex('70 01'))
TOWER, TOWER_FIELD, TOWER_IN = 0x39, (0x88, 0x16), (0x00, 0x09, 0x0C)


def _fly(event):
    from dq4chapterbox import ENTER, LEAVE
    import dq4prologue
    start = dq4prologue._event_start(event)[len(ENTER):-len(LEAVE)]
    return ENTER + start + bytes((0xA9, TOWER, 0x8D, 0x54, 0x0B)) + LEAVE


def _fade_out():
    from dq4chapterbox import ENTER, LEAVE, FADE_STEP, fade
    return ENTER + fade(14, 0, FADE_STEP) + LEAVE


# 손님 호이민의 행동 고르기. FC 손님은 몬스터 AI 로, 호이민은 몬스터 레코드 C5(대화 148 의 「호이민이 일행에 있음」 이
# 손님 바이트 5 = C5 에서 참). 행동 칸 ホイミ ×3·공격·방어·공격, 고르는 법 2(칸 가중치 209 29 10 4 2 1, 같은 행동은
# 첫 칸에 합침), AI 2(ホイミ 칸은 같은 편 누군가 HP 가 최대의 절반 미만이고 MP 가 될 때만 남김, 10:B9E9·13:B915).
# 곧 ホイミ 248·공격 5·방어 2, 남기지 않으면 공격 5·방어 2 에서 난수로.
# ホイミ 의 대상: 절반 미만인 사람이 하나면 그 사람. 자기와 남이 함께 그러면 SELF_HEAL 의 확률로 자기, 아니면 남.
# FC 마지막 고르기 코드는 풀지 못해 실측으로 정했다: 1장 필드에서 손님 C5 와 라이안의 HP 를 묶고 싸워 ホイミ 뒤 첫 HP
# 쓰기를 세니 676번 중 자기 112번(16.6%)이었고, HP 비율·잃은 양·일행 차례를 바꿔도 같았다. 남이 둘 이상인 경우는 1장에
# 없어(걷는 일행이 라이안과 호이민뿐) 재지 않았고, 그때는 차례가 앞인 사람을 고친다
# 21:AED8 은 행동을 고른 뒤 21:AF6E 의 LDA #$01 을 대상 번호로 21:B199 에 넘겨, 그대로 두면 늘 자기를 고쳤다(실측)
GUEST_AI_AT, GUEST_AI_ORIG = 0x21AF1B, bytes.fromhex('2e 0e 11 2e')   # ROL $110E / ROL $110F 의 앞 4바이트
GUEST_AI_BACK, GUEST_AI_DONE = 0x21AF21, 0x21AF3B                     # 원래 고르기 / 고른 행동을 $10F7 에
GUEST_TARGET_AT, GUEST_TARGET_ORIG = 0x21AF6E, bytes.fromhex('a9 01 0c 15 11')   # LDA #$01 / TSB $1115
RANDOM = 0x00953A               # A = N 이면 0~N-1(8비트 난수 × N >> 8)
HEAL, ATTACK, DEFEND = 0x27, 0x73, 0x71
HEAL_MP = 3
GUEST_WEIGHTS = ((HEAL, 248), (ATTACK, 5), (DEFEND, 2))
WALKERS = 3                     # 전투에 나오는 걷는 일행(7E:201E) 최대 수
SELF_HEAL = 6                   # 자기와 남이 함께 다쳤을 때 1/SELF_HEAL 로 자기


def _guest_ai(origin):
    """21:AED8(かしこさ 10 미만의 무작위 고르기)이 고르기 직전에 부르는 루틴. 행동자 $7B 의 일행 기록 +0 이 손님
    몬스터 동료(C0 이 다 켜짐)면 FC 규칙으로 행동을 골라 21:AF3B 로, 아니면 원래 고르기로 돌아간다."""
    import dq4environmentrom
    hurt, mp, target, self_k = SCRATCH + 0x0A, SCRATCH + 0x0B, SCRATCH + 0x0C, SCRATCH + 0x0D
    a = dq4environmentrom._Asm(origin)
    # 대상 훅: 손님이 ホイミ 를 골랐으면 그 번호(target 은 번호 + 1, 0 은 없음. 켤 때 WRAM 0 이라)를, 아니면 원래의 1 을
    a.label('pick').b(0x08, 0xE2, 0x20, 0xA9, 0x01, 0x0C, 0x15, 0x11).long(0xAF, 'target')
    a.rel(0xD0, 'picked').b(0xA9, 0x01, 0x28, 0x6B)
    a.label('picked').b(0x3A, 0x48, 0xA9, 0x00).long(0x8F, 'target').b(0x68, 0x28, 0x6B)
    a.label('entry')
    a.b(0x08, 0xE2, 0x30, 0xA5, 0x7B, 0x00, 0x8B, 0x80, 0x2A, 0xA5, 0x46, 0x29, GUEST, 0xC9, GUEST)  # BRK 8B 80 2A
    a.rel(0xF0, 'guest')
    a.b(0x28, 0x2E, 0x0E, 0x11, 0x2E, 0x0F, 0x11).long(0x5C, 'back')
    # hurt: 절반 미만인 사람의 걷는 차례 비트, self_k: 손님 자신의 차례
    a.label('guest').b(0xA9, 0x00).long(0x8F, 'hurt').long(0x8F, 'target').long(0x8F, 'mp').long(0x8F, 'self')
    a.b(0xC2, 0x10)
    for k in range(WALKERS):
        a.b(0xAF, 0x1E, 0x20, 0x7E, 0xC9, k + 1).rel(0x90, f'skip{k}')              # 걷는 수 < k+1
        a.b(0xAF, 0x20 + k, 0x20, 0x7E, 0xC2, 0x20, 0x29, 0x07, 0x00, 0x0A, 0xAA).long(0xBF, 'offsets').b(0xAA)
        a.b(0xE2, 0x20, 0xBF, 0x40, 0x20, 0x7E, 0x29, GUEST, 0xC9, GUEST).rel(0xD0, f'hp{k}')
        a.b(0xBF, 0x44, 0x20, 0x7E).long(0x8F, 'mp').b(0xA9, k).long(0x8F, 'self')       # 손님의 MP 와 차례
        a.label(f'hp{k}').b(0xC2, 0x20, 0xBF, 0x42, 0x20, 0x7E).rel(0xF0, f'skip{k}')  # 쓰러짐
        a.b(0x0A, 0xDF, 0x4E, 0x20, 0x7E).rel(0xB0, f'skip{k}')                       # 2 × HP >= 최대 HP
        a.b(0xE2, 0x20).long(0xAF, 'hurt').b(0x09, 1 << k).long(0x8F, 'hurt')
        a.label(f'skip{k}').b(0xE2, 0x20)
    a.b(0xE2, 0x30).long(0xAF, 'hurt').rel(0xF0, 'calm').long(0xAF, 'mp').b(0xC9, HEAL_MP).rel(0x90, 'calm')
    a.b(0xA9, sum(w for _, w in GUEST_WEIGHTS)).long(0x22, 'random')
    total = 0
    for act, w in GUEST_WEIGHTS[:-1]:
        total += w
        a.b(0xC9, total).rel(0x90, f'act{act:02X}')
    a.rel(0x80, f'act{GUEST_WEIGHTS[-1][0]:02X}')
    calm = GUEST_WEIGHTS[1:]
    a.label('calm').b(0xA9, sum(w for _, w in calm)).long(0x22, 'random')
    total = 0
    for act, w in calm[:-1]:
        total += w
        a.b(0xC9, total).rel(0x90, f'act{act:02X}')
    a.rel(0x80, f'act{calm[-1][0]:02X}')
    for act, _ in GUEST_WEIGHTS:
        a.label(f'act{act:02X}')
        if act == HEAL:
            a.long(0x22, 'aim')
        a.b(0xA9, act).rel(0x80, 'done')
    a.label('done').b(0x28).long(0x5C, 'finish')
    # ホイミ 대상(M·X 8): 남(hurt 에서 자기 비트를 뺀 것)이 없으면 자기. 자기도 다쳤으면 1/SELF_HEAL 로 자기.
    # 아니면 남 가운데 차례가 앞인 사람
    a.label('aim').long(0xAF, 'self').b(0xAA).long(0xBF, 'bits').b(0x49, 0xFF).long(0x2F, 'hurt')
    a.rel(0xF0, 'aim_self').b(0x48).long(0xBF, 'bits').long(0x2F, 'hurt').rel(0xF0, 'aim_other')
    # 00:953A 는 돌아올 때 Z 를 A 로 맞추지 않는다
    a.b(0xA9, SELF_HEAL).long(0x22, 'random').b(0xC9, 0x00).rel(0xD0, 'aim_other').b(0x68).rel(0x80, 'aim_self')
    a.label('aim_other').b(0x68, 0xA2, 0x01)
    a.label('aim_bit').b(0x4A).rel(0xB0, 'aim_set').b(0xE8).rel(0x80, 'aim_bit')
    a.label('aim_self').long(0xAF, 'self').b(0x1A, 0xAA)
    a.label('aim_set').b(0x8A).long(0x8F, 'target').b(0x6B)
    a.label('bits').b(*(1 << k for k in range(WALKERS)))
    a.label('offsets').b(*b''.join((42 * n).to_bytes(2, 'little') for n in range(8)))
    code, labels = a.assemble({'back': GUEST_AI_BACK, 'finish': GUEST_AI_DONE, 'random': RANDOM, 'hurt': hurt,
                               'mp': mp, 'target': target, 'self': self_k})
    return code, labels['entry'], labels['pick']


def native(data=None):
    """(바이트, {이름: 주소}). 기록 자료가 앞, 루틴이 뒤. 주소는 data(롬, 동료 표를 읽음)와 상관없다."""
    record = companion_record(data, HOIMIN_KIND) if data is not None else bytes(len(PARTY_TEMPLATE))
    out, at = bytearray(record), {'record': CODE_AT}
    at['join'] = CODE_AT + len(out)
    out += _join(CODE_AT)
    for i, (_, _, shoes, cells) in enumerate(VOICES):
        dq5 = [(x, y, FACING[f]) for x, y, f in cells]
        for name, away in ((f'voice{i}', False), (f'voice{i}_away', True)):
            at[name] = CODE_AT + len(out)
            out += _voice(dq5, shoes, away)
    at['kidnap_row'] = CODE_AT + len(out)
    out += _at(None, ch1_cell(0, KIDNAP_ROW)[1])
    at['kids_home_row'] = CODE_AT + len(out)
    out += _at(None, ch1_cell(0, KIDS_HOME_ROW)[1])
    at['fade_out'] = CODE_AT + len(out)
    out += _fade_out()
    import dq4prologue
    at['darken'] = CODE_AT + len(out)
    out += dq4prologue._darken()       # 곡을 줄이고 주화면을 BG3 만으로: 상자가 1장 첫머리처럼 검은 화면에 뜬다
    at['fly_event'] = CODE_AT + len(out)
    number, x, y = TOWER_IN
    out += bytes((0x90, TOWER, number, *ch1_cell(x, y), 0x01, 0x80, 0xFF))
    at['fly'] = CODE_AT + len(out)
    out += _fly(at['fly_event'])
    for name, code in (('lineup_row', _at(None, ch1_cell(0, LINEUP_ROW)[1])),
                       ('king_row', _at(None, ch1_cell(0, KING_ROW)[1])),
                       ('king_away', _at(None, ch1_cell(0, KING_ROW)[1], away=True)),
                       ('cry_at', _at(*ch1_cell(CRY_FROM, CRY_ROW), x_from=True)),
                       ('level_up', _level_up()), ('open_cage', _open_cage()),
                       ('status_count', _status_count())):
        at[name] = CODE_AT + len(out)
        out += code
    events = {}
    for x in (AISLE_X - 2, AISLE_X - 1, AISLE_X, AISLE_X + 1):
        events[x] = CODE_AT + len(out)
        out += _walk_in_event(x)
    for name, code in (('ev_back', bytes((DOWN, KING_STEPS, 0xFF))), ('ev_out', bytes((DOWN, OUT_STEPS, 0xFF)))):
        at[name] = CODE_AT + len(out)
        out += code
    for name, code in (('walk_in', _walk_in(events)), ('walk_back', dq4prologue._event_start(at['ev_back'])),
                       ('walk_out', dq4prologue._event_start(at['ev_out'])),
                       *((f'stat_{k}', _stat(k)) for k, _ in STATS)):
        at[name] = CODE_AT + len(out)
        out += code
    code, at['guest_ai'], at['guest_target'] = _guest_ai(CODE_AT + len(out))
    out += code
    from dq4chapterbox import ENTER, LEAVE
    at['refresh'] = CODE_AT + len(out)
    out += ENTER + REFRESH + LEAVE
    at['followers'] = CODE_AT + len(out)
    out += _followers(at['followers'])
    return bytes(out), at


def _followers(origin):
    """02:C634 끝에서 M·X 8 로 부른다. 프레아(따라옴, 재회 전, 감옥 안이 아님)와 구한 아이들(따라옴)의 그림을 걷는 그림
    7E:196F~ 끝에 더하고 7E:1967 을 늘린다. 1978 은 0(보이는 그림, 02:C6F2 가 bit7 을 관 그림 35 로 보냄)."""
    import dq4environmentrom
    from dq4npcport import PICTURES
    jail_bc, jail_bd = (int(v, 16) for v in JAIL.split('/'))
    flag = lambda f: 0x7E2190 + f[0]  # noqa: E731
    a = dq4environmentrom._Asm(origin)
    a.b(0x08, 0xE2, 0x30).long(0xAF, 'flare').b(0x29, FLARE_FOLLOWS[1]).rel(0xF0, 'kids')
    a.long(0xAF, 'reunited').b(0x29, REUNITED[1]).rel(0xD0, 'kids')
    # 필드에서도 $BC·$BD 가 들어갔던 맵 번호로 남아 있었다(실측). 실내일 때만 감옥으로 본다
    a.b(0xAF, 0xBE, 0x00, 0x7E).rel(0x10, 'add_flare')
    a.b(0xAF, 0xBC, 0x00, 0x7E, 0xC9, jail_bc).rel(0xD0, 'add_flare')
    a.b(0xAF, 0xBD, 0x00, 0x7E, 0xC9, jail_bd).rel(0xF0, 'kids')
    a.label('add_flare').b(0xA9, PICTURES[FC_FLARE_PICTURE]).word(0x20, 'add')
    a.label('kids').long(0xAF, 'kids_flag').b(0x29, KIDS_FOLLOW[1]).rel(0xF0, 'done')
    for _ in range(KIDS_WALKING):
        a.b(0xA9, PICTURES[FC_CHILD_PICTURE]).word(0x20, 'add')
    a.label('done').b(0x28, 0x6B)
    a.label('add').b(0x48, 0xAF, 0x67, 0x19, 0x7E, 0xAA, 0x68, 0x9F, 0x6F, 0x19, 0x7E, 0xA9, 0x00, 0x9F, 0x78, 0x19, 0x7E,
                     0xE8, 0x8A, 0x8F, 0x67, 0x19, 0x7E, 0x60)
    code, _ = a.assemble({'flare': flag(FLARE_FOLLOWS), 'reunited': flag(REUNITED), 'kids_flag': flag(KIDS_FOLLOW)})
    return code


def _count_tail(followers):
    """02:FF60: 02:C634 의 끝을 대신한다. 원래의 STA $1967 뒤에 따라 걷는 그림과 실내 주인공 그림을 더한다."""
    return (bytes((0x8D, 0x67, 0x19, 0x22)) + followers.to_bytes(3, 'little') +
            bytes((0x20, *(HERO_INDOOR & 0xFFFF).to_bytes(2, 'little'), 0x28, 0x60)))


def _put(d, addr, code):
    o = lorom(addr)
    if any(d[o:o + len(code)]):
        raise SystemExit(f'{addr:06X}: 비어 있지 않은 자리')
    d[o:o + len(code)] = code


def ch1_cell(x, y):
    """FC 칸에 선 주인공의 DQ5 셀."""
    return x * 2, y * 2 + 1


def apply(data):
    d = bytearray(data)
    code, _ = native(data)
    _put(d, CODE_AT, code)
    _put(d, BATTLE_AT, _battle())
    _put(d, FANFARE_AT, _fanfare())
    _, at = native()
    _put(d, COUNT_TAIL, _count_tail(at['followers']))
    fx, fy = TOWER_FIELD[0] * 2, TOWER_FIELD[1] * 2      # FC 필드 칸 → DQ5 필드 좌표(그룹 연결의 필드 입구와 같은 셈)
    for addr, orig, new in ((FLY_AT, FLY_ORIG, bytes((0x22, *_long(at['fly']), 0xEA))),
                            (GUEST_AI_AT, GUEST_AI_ORIG, bytes((0x5C, *_long(at['guest_ai'])))),
                            (GUEST_TARGET_AT, GUEST_TARGET_ORIG, bytes((0x22, *_long(at['guest_target']), 0xEA))),
                            (FLY_X_AT, FLY_XY_ORIG[0], fx.to_bytes(2, 'little')),
                            (FLY_Y_AT, FLY_XY_ORIG[1], fy.to_bytes(2, 'little')),
                            (COUNT_AT, COUNT_ORIG, bytes((0x4C, *(COUNT_TAIL & 0xFFFF).to_bytes(2, 'little'), 0xEA, 0xEA))),
                            (SOLO_AT, SOLO_ORIG, bytes((0xEA, 0xEA, 0xEA))),
                            (GUEST_PICTURE_AT, GUEST_PICTURE_ORIG, bytes((0x29, 0x3F)))):
        o = lorom(addr)
        if bytes(d[o:o + len(orig)]) != orig:
            raise SystemExit(f'{addr:06X}: 원래 바이트가 아님 {d[o:o + len(orig)].hex()}')
        d[o:o + len(new)] = new
    return bytes(d)
REUNION_AT = (0x04, 0x03)       # FC 슬롯 07 이 걸어가 서는 칸, 재회 뒤 슬롯 08 의 자리


def _cmd(op, *args):
    return {"op": op, "args": list(args)}


def scripts(first_message, chapter2_at=None):
    """chapter2_at: 1장 끝 서술 뒤 2장으로 옮기는 네이티브(dq4ch2event 의 transfer)."""
    m = message_ids(first_message)
    _, at = native()
    lo, hi = lambda v: v & 0xFF, lambda v: v >> 8
    return [
        # 따라오기로 하면 사라진다. 다시 들어와도 곧바로 숨는다
        {"address": FLARE_SCRIPT, "commands": [_cmd('09', 0x80 | FLARE_FOLLOWS[0], FLARE_FOLLOWS[1]),
                                               _cmd('37', *_long(at['refresh'])), _cmd('28'), _cmd('52'), _cmd('16')]},
        # 감옥에 들어서면 계단 쪽에서 알렉스 옆까지 걸어와 재회한다
        {"address": WALKER_SCRIPT, "commands": [
            _cmd('3F'), _cmd('13', REUNION_AT[0] * 2, REUNION_AT[1] * 2 + 1), _cmd('14'),
            _cmd('21', lo(m['reunion']), hi(m['reunion'])), _cmd('21', lo(m['hint']), hi(m['hint'])),
            _cmd('10', *REUNITED), _cmd('40'), _cmd('16')]},
    ] + [
        # 보이지 않는 인물이 칸을 기다렸다가 목소리를 띄우고, 그 칸들을 벗어나면 다시 기다린다. 52 로 자리를 치워
        # 길을 막지 않는다
        {"address": script, "commands": [
            _cmd('28'), _cmd('52'), {**_cmd('05', *_long(at[f'voice{i}'])), "label": "wait"}, _cmd('3F'),
            _cmd('21', lo(m[msg]), hi(m[msg])), _cmd('40'), _cmd('05', *_long(at[f'voice{i}_away'])),
            {"op": "03", "args": [], "target": "wait"}]}
        for i, ((_, script), (_, msg, _, _)) in enumerate(zip(VOICE_SRCS, VOICES))
    ] + [
        # 41 동굴에 들어설 때: 병사와 이야기했으면 대사 차례를 하나 올린다(0 → 1 → 2)
        {"address": CAVE_STEP_SCRIPT, "commands": [
            _cmd('28'), _cmd('52'), {**_cmd('06', 0x80 | CAVE_TALKED[0], CAVE_TALKED[1]), "target": "done"},
            _cmd('11', CAVE_TALKED[0], ~CAVE_TALKED[1] & 0xFF),
            {**_cmd('06', *CAVE_STEP1), "target": "two"}, _cmd('10', *CAVE_STEP1),
            {"op": "03", "args": [], "target": "done"},
            {**_cmd('11', CAVE_STEP1[0], ~CAVE_STEP1[1] & 0xFF), "label": "two"}, _cmd('10', *CAVE_STEP2),
            {**_cmd('16'), "label": "done"}]},
    ] + [
        # 예라고 대답하면(합류 깃발) 일행 기록을 쓰고 사라진다
        {"address": HOIMIN_SCRIPT, "commands": [_cmd('09', 0x80 | HOIMIN[0], HOIMIN[1]), _cmd('37', *_long(at['join'])),
                                                _cmd('28'), _cmd('52'), _cmd('16')]},
    ] + [
        # 마물이 말하고 납치 깃발을 켜면 아이도 함께 계단 쪽으로 걸어가 사라진다
        {"address": KIDNAPPER_SCRIPT, "commands": [
            _cmd('05', *_long(at['kidnap_row'])), _cmd('3F'), _cmd('21', lo(m['kidnap']), hi(m['kidnap'])),
            _cmd('10', *KIDNAPPED)] + _walk_off(9) + [_cmd('40'), _cmd('16')]},
        {"address": KID_SCRIPT, "commands": [_cmd('09', 0x80 | KIDNAPPED[0], KIDNAPPED[1])] + _walk_off(8) + [_cmd('16')]},
        # 이기면 철창을 열고 숨는다. 이긴 뒤 다시 들어오면 이 인물 하나가 철창만 연다
        {"address": HIDE_ON_WIN_SCRIPT, "commands": [_cmd('09', 0x80 | BOSS_WON[0], BOSS_WON[1]),
                                                     _cmd('37', *_long(at['open_cage'])), _cmd('28'), _cmd('52'),
                                                     _cmd('16')]},
        # 잡힌 아이: 주인공이 다가오면 그 앞까지 와서 울고, 이기면 숨는다
        {"address": CRY_SCRIPT, "commands": [
            _cmd('05', *_long(at['cry_at'])), _cmd('3F')] + _walk(CRY_TO) + [
            _cmd('21', lo(m['cry']), hi(m['cry'])), _cmd('40'), _cmd('09', 0x80 | BOSS_WON[0], BOSS_WON[1]),
            _cmd('28'), _cmd('52'), _cmd('16')]},
        # 구한 아이: 이기기 전에는 숨어 있다가 나타나 열린 철창 밖으로 걸어 나오고, 따라오기로 하면 숨는다
        # (FC 는 일행 뒤를 따라 걷는 그림)
        {"address": RESCUED_SCRIPT, "commands": _rescued([], 0x0D)},
        {"address": RESCUED2_SCRIPT, "commands": _rescued([], 0x0C)},
        {"address": THANKS_SCRIPT, "commands": _rescued([_cmd('3F'), _cmd('21', lo(m['kids_thanks']), hi(m['kids_thanks'])),
                                                         _cmd('10', *KIDS_FOLLOW), _cmd('37', *_long(at['refresh'])),
                                                         _cmd('40')], 0x0E)},
        {"address": SOLDIER_SCRIPT, "commands": [_cmd('09', 0x80 | SOLDIER_LEFT[0], SOLDIER_LEFT[1]), _cmd('3F')] +
         [c for x, y in SOLDIER_PATH for c in (_cmd('13', *ch1_cell(x, y)), _cmd('14'))] +
         [_cmd('28'), _cmd('52'), _cmd('40'), _cmd('16')]},
        # 보이지 않는 인물: 아이들이 따라오는 동안 이 줄에 오면 엄마 곁으로 보내고 따라옴 깃발을 끈다(11 은 AND)
        {"address": KIDS_HOME_SCRIPT, "commands": [
            _cmd('28'), _cmd('52'), _cmd('09', 0x80 | KIDS_FOLLOW[0], KIDS_FOLLOW[1]),
            _cmd('05', *_long(at['kids_home_row'])), _cmd('3F'), _cmd('21', lo(m['kids_home']), hi(m['kids_home'])),
            _cmd('11', KIDS_FOLLOW[0], ~KIDS_FOLLOW[1] & 0xFF), _cmd('37', *_long(at['refresh'])), _cmd('40'),
            _cmd('16')]},
    ] + [
        # 엄마 곁의 아이: 따라오는 중에 들어오면 숨었다가, 따라옴 깃발이 꺼지면 통로 아래에서 나타나 집으로 걷는다
        {"address": script, "commands": [
            {**_cmd('06', 0x80 | KIDS_FOLLOW[0], KIDS_FOLLOW[1]), "target": "stay"}, _cmd('28'), _cmd('52'),
            _cmd('09', *KIDS_FOLLOW), _cmd('50', *_npc(*start)), _cmd('1C'), _cmd('53'), _cmd('4F'),
            _cmd('1E', WALK_SPEED)] + _walk(*path) +
            [_cmd('22'), _cmd('2F', facing), {**_cmd('16'), "label": "stay"}]}
        for (_, script), (_, start, path, facing) in zip(HOME_KID_SRCS, KIDS_WALK_HOME)
    ] + [
        # 보스 뒤 왕좌의 방: 병사는 주인공이 줄에 오면 통로 양옆으로 갈라선다. 말을 걸 수 없다(FC 02F0)
        {"address": script, "commands": [_cmd('44'), _cmd('05', *_long(at['lineup_row']))] + _walk(*path, half=0) +
         [_cmd('2F', facing), _cmd('16')]}
        for (_, script), (_, path, facing) in _distinct(zip(SOLDIER_SRCS, THRONE_SOLDIERS))
    ] + [
        # 왕: 주인공이 왕 앞 줄에 오면 스스로 말을 건다. 아이들이 아직 따라오면 돌려보내라 하고, 그 줄을 떠났다 오면
        # 다시 말한다. 아니면 칭찬 → 선물(경험치·레벨업) → 작별, 보고 깃발
        {"address": KING_CALL_SCRIPT, "commands": _king_call(m, at)},
    ] + ([
        # 1장 끝: 서술 → 검은 화면 → 2장으로 옮김(일행을 바꾸고 산트하임 왕좌의 방을 검게 불러옴)
        {"address": ENDER_SCRIPT, "commands": [
            _cmd('28'), _cmd('52'), _cmd('3F'), _cmd('21', lo(m['chapter_end']), hi(m['chapter_end'])),
            _cmd('37', *_long(at['darken'])), _cmd('37', *_long(chapter2_at)), _cmd('16')]},
    ] if chapter2_at is not None else [])


def _king_call(m, at):
    """왕: 주인공이 Y=19 줄에 오면 왕 앞까지 걷게 하고, 왕 앞 줄에서 말을 건다. 아이들이 아직 따라오면 돌려보내라
    하고, 그 줄을 떠났다 오면 다시 말한다. 아니면 칭찬 → 선물(경험치·레벨업과 오른 능력치) → 그 줄로 물러나 작별 →
    보고 깃발 → 출구로 걸어 나간다."""
    lo, hi = (lambda v: v & 0xFF), (lambda v: v >> 8)

    def msg(name, op='21'):
        return _cmd(op, lo(m[name]), hi(m[name]))

    def call(name):
        return _cmd('37', *_long(at[name]))
    stats = []
    for i, (k, _) in enumerate(STATS):
        skip = f"stat{i + 1}" if i + 1 < len(STATS) else "next"
        stats += [{**call(f'stat_{k}'), "label": f"stat{i}"}, {**_cmd('06', *REPORTED), "target": skip},
                  msg(f'stat_{k}', '30')]
    return [
        _cmd('28'), _cmd('52'), _cmd('05', *_long(at['lineup_row'])), call('walk_in'),
        {**_cmd('05', *_long(at['king_row'])), "label": "wait"}, _cmd('3F'),
        # 갈래는 상대 점프(-128~127)라, 아이들 갈래를 앞에 두고 깃발이 꺼져 있으면 칭찬으로 건너뛴다
        {**_cmd('06', 0x80 | KIDS_FOLLOW[0], KIDS_FOLLOW[1]), "target": "praise"},
        msg('king_back'), _cmd('40'), _cmd('05', *_long(at['king_away'])), {"op": "03", "args": [], "target": "wait"},
        # 상태 창은 레벨업 줄 동안 열어 두고(FC 와 같음) 마지막에 명령 34 로 함께 닫는다
        {**msg('king_praise'), "label": "praise"}, call('status_count'),
        # 한 번 오를 때마다 「레벨이 올랐다」 와 오른 능력치를 한 창에 잇는다. 더 오르지 않으면 level_up 이 보고 깃발을
        # 켜고, 능력치 줄은 오른 양이 0 이면 stat_k 가 보고 깃발을 켜 건너뛴다
        {**call('level_up'), "label": "grow"}, {**_cmd('06', *REPORTED), "target": "grown"},
        msg('level_up', '30')] + stats + [
        {"op": "03", "args": [], "target": "grow", "label": "next"},
        # 레벨업 줄을 띄운 창은 명령 34 로 닫는다. 같은 일(BRK 95 FF)을 네이티브에서 하면 멈췄다
        {**_cmd('34'), "label": "grown"}, call('walk_back'), _cmd('05', *_long(at['lineup_row'])),
        msg('king_farewell'), _cmd('10', *REPORTED), call('walk_out'), _cmd('40'), _cmd('16')]


def _rescued(speak, slot):
    start, path = RESCUED_PATHS[slot]
    return ([_cmd('28'), _cmd('09', 0x80 | BOSS_WON[0], BOSS_WON[1]), _cmd('50', *_npc(*start)), _cmd('53'), _cmd('4F'),
             _cmd('1E', WALK_SPEED), _cmd('1C')] + _walk(*path) + [_cmd('22')] + speak +
            [_cmd('09', 0x80 | KIDS_FOLLOW[0], KIDS_FOLLOW[1]), _cmd('28'), _cmd('52'), _cmd('16')])


# 깜빡이며 나타난 인물은 속도(3360)가 0 이라 걷기를 켜도 제자리였다(실측). 한 칸 8프레임
WALK_SPEED = 0x01


def _npc(x, y, half=1):
    """FC 칸에 선 인물의 DQ5 자리. 옮긴 인물(dq4npcport)은 Y 가 2y+1 이고, 1장 첫머리 왕좌의 방 인물
    (dq4chapter1.entry)은 2y 라 그 방에서는 half=0 으로 맞춘다."""
    return x * 2, y * 2 + half


def _walk(*points, half=1):
    return [c for p in points for c in (_cmd('13', *_npc(*p, half)), _cmd('14'))]


def _distinct(pairs):
    """같은 원본(같은 스크립트)을 쓰는 인물은 스크립트를 한 번만."""
    seen, out = set(), []
    for src, row in pairs:
        if src[1] not in seen:
            seen.add(src[1])
            out.append((src, row))
    return out


def _walk_off(x):
    """탑 입구에서 열 x 를 따라 KIDNAP_TO 줄까지 올라가 숨고 자리를 치운다."""
    return [_cmd('13', x * 2, KIDNAP_TO * 2 + 1), _cmd('14'), _cmd('28'), _cmd('52')]


def _invisible(src, talk):
    """스크립트만 돌리는 보이지 않는 인물(낮·밤 하나씩). 스크립트가 숨긴다."""
    e = {"from": src, "fields": {"x": 0, "y": 1, "facing": "down", "talk": talk, "gfx": 0x01, "layer": 0}}
    return [{**e, "time": "day"}, {**e, "time": "night"}]


def throne_return(first_talk):
    """보스를 이기고 보고하기 전의 왕좌의 방 목록(FC 1C:$8184): 왕·대신, 문지기 둘, 병사 8명, 왕이 말을 거는 보이지
    않는 인물."""
    t = talk_numbers(first_talk)
    static = [ch1.entry(ch1.STATIC, *THRONE_KING, ch1.KING, 'down', t['king']),
              ch1.entry(ch1.STATIC, *THRONE_MINISTER, ch1.MINISTER, 'down', t['guard'])] + \
        [ch1.entry(ch1.STATIC, x, y, ch1.GUARD, facing, t['guard']) for (x, y), facing in THRONE_GUARDS]
    soldiers = [ch1.entry(src, x, y, ch1.WARRIOR, 'down', t['guard'])
                for src, ((x, y), _, _) in zip((s for s, _ in SOLDIER_SRCS), THRONE_SOLDIERS)]
    day = static + soldiers
    return day + [{**e, "time": "night"} for e in day] + _invisible(KING_CALL_SRC, t['king'])


def _same(entry, src, talk):
    fields = {**entry["fields"], "talk": talk}
    if src != entry["from"]:
        # 움직임 칸은 빌린 인물의 것을 쓴다. 옮긴 서 있는 인물의 간격 0 을 받으면 스크립트가 돌지 않았다
        for k in ("interval", "speed", "step"):
            fields.pop(k, None)
    return {"from": src, "time": entry["time"], "fields": fields}


def npc_lists(ported, report, first_talk):
    """(옮긴 목록을 고친 것, new_lists, overrides). ported·report 는 dq4npcport.port 의 것."""
    t = talk_numbers(first_talk)
    lists = {lst["map"]: [dict(e) for e in lst["entries"]] for lst in ported if "map" in lst}
    alts = {lst["name"]: [dict(e) for e in lst["entries"]] for lst in ported if "name" in lst}

    def where(m, fc_talk, night):
        return [i for i, p in enumerate(report[m]) if p["talk"] == fc_talk and p["night"] == night]

    (child,) = where(IMURU, FC_CHILD, True)
    lists[IMURU][child] = _same(lists[IMURU][child], lists[IMURU][child]["from"], t['child'])
    (day,) = where(FRONT, FC_FLARE_DAY, False)
    lists[FRONT][day] = _same(lists[FRONT][day], FLARE_SRC, t['flare_day'])
    (night,) = where(FRONT_NIGHT, FC_FLARE_NIGHT, True)
    lists[FRONT_NIGHT][night] = _same(lists[FRONT_NIGHT][night], FLARE_SRC, t['flare_night'])
    # 감옥: 알렉스만 두고, 프레아는 깃발에 따라 대체 목록으로
    jail = lists[JAIL]
    flares = [i for i, p in enumerate(report[JAIL]) if p["talk"] == FC_JAIL_FLARE]
    (alex_night,) = where(JAIL, FC_ALEX_NIGHT, True)
    jail[alex_night] = _same(jail[alex_night], jail[alex_night]["from"], t['alex_night'])
    alex = [e for i, e in enumerate(jail) if i not in flares]
    hint_talk = jail[flares[0]]["fields"]["talk"]      # FC 017: 알렉스의 힌트(0342)
    walker_from = next(report[JAIL][i] for i in flares if (report[JAIL][i]["x"], report[JAIL][i]["y"]) != REUNION_AT)
    wx, wy = walker_from["dq5"]["x"], walker_from["dq5"]["y"]
    stand = next(jail[i] for i in flares if (report[JAIL][i]["x"], report[JAIL][i]["y"]) == REUNION_AT)
    walker = {**_same(stand, WALKER_SRC, hint_talk), "fields": {**_same(stand, WALKER_SRC, hint_talk)["fields"], "x": wx, "y": wy}}
    both = lambda e: [{**e, "time": "day"}, {**e, "time": "night"}]  # noqa: E731
    # 재회 뒤에는 알렉스도 힌트를 되풀이한다(FC 017)
    after_alex = [_same(e, e["from"], hint_talk) for e in alex]
    lists[JAIL] = alex
    new_lists = [{"name": "jail_reunion", "entries": alex + both(walker)},
                 {"name": "jail_after", "entries": after_alex + both(stand)}]
    # 우물 아래: 목소리 인물을 더하고, 호이민은 합류하면 빠진 목록으로
    for (src, _), (where, _, _, _) in zip(VOICE_SRCS, VOICES):
        lists[where] += _invisible(src, t['hoimin'])
    # 41 동굴 병사·왕의 방 왕·탑의 병사는 진행에 따라 대사를 고르는 대화로
    for mp, fc_talk, name in ((CAVE, FC_CAVE_SOLDIER, 'cave_soldier'), (KING_ROOM, FC_KING_ROOM, 'king_room'),
                              (SOLDIER_MAP, FC_SOLDIER, 'tower_soldier')):
        hits = [i for i, p in enumerate(report[mp]) if p["talk"] == fc_talk]
        if not hits:
            raise SystemExit(f'{mp}: FC 대화 {fc_talk:03X} 인물이 없음')
        for i in hits:
            lists[mp][i] = _same(lists[mp][i], lists[mp][i]["from"], t[name])
    lists[CAVE] += _invisible(CAVE_STEP_SRC, t['cave_soldier'])
    # 예·아니요로 묻는 둘: 성 앞 노인, 보스 뒤 성 앞 사내
    for m, lst, fc_talk, name in ((FRONT, lists[FRONT], FC_OLD_MAN, 'old_man'),
                                  (alt_name(AFTER_BOSS, FRONT), alts[alt_name(AFTER_BOSS, FRONT)], FC_BRAGGART, 'braggart')):
        hits = [i for i, p in enumerate(report[m]) if p["talk"] == fc_talk]
        if not hits:
            raise SystemExit(f'{m}: FC 대화 {fc_talk:03X} 인물이 없음')
        for i in hits:
            lst[i] = _same(lst[i], lst[i]["from"], t[name])
    room = lists[HOIMIN_ROOM]
    hoimins = [i for i, p in enumerate(report[HOIMIN_ROOM]) if p["talk"] == FC_HOIMIN]
    gone = [e for i, e in enumerate(room) if i not in hoimins]
    for i in hoimins:
        room[i] = _same(room[i], HOIMIN_SRC, t['hoimin'])
    new_lists.append({"name": "hoimin_gone", "entries": gone})
    # 탑 입구: 마물(그림 45)과 아이(15)를 스크립트 인물로, 끌고 간 뒤에는 빈 목록
    hall = lists[TOWER_HALL]
    for i, p in enumerate(report[TOWER_HALL]):
        src = KIDNAPPER_SRC if p["picture"] == FC_KIDNAPPER else KID_SRC
        hall[i] = _same(hall[i], src, hall[i]["fields"]["talk"])
    new_lists.append({"name": "hall_empty", "entries": []})
    # 탑 위
    top = lists[TOWER_TOP]
    keep = []
    for i, (e, p) in enumerate(zip(top, report[TOWER_TOP])):
        # 낮·밤 목록이 이어져 있어, 같은 시간대의 앞 인물 수가 그 목록 안의 차례다
        slot = FIRST_SLOT + [q["night"] for q in report[TOWER_TOP][:i]].count(p["night"])
        if slot == FIRST_SLOT:
            top[i] = _same(e, HIDE_ON_WIN_SRC, t['boss'])
        elif slot == CRY_SLOT:
            top[i] = _same(e, CRY_SRC, e["fields"]["talk"])
        elif slot in TOP_HIDE_ON_WIN:
            top[i] = _same(e, HIDE_ON_WIN_SRC, e["fields"]["talk"])
        elif slot in TOP_RESCUED:
            # 고맙다는 말은 길이 가장 긴 0E 가 다 걸어 나온 뒤에(FC 는 0D·0E 가 0321)
            src = {TOP_RESCUED[0]: RESCUED2_SRC, TOP_RESCUED[1]: RESCUED_SRC, TOP_RESCUED[2]: THANKS_SRC}[slot]
            top[i] = _same(e, src, e["fields"]["talk"])
        else:
            keep.append(e)
    opener = _invisible(HIDE_ON_WIN_SRC, t['boss'])
    new_lists.append({"name": "top_after", "entries": keep + opener})
    # 보스 뒤 목록: 탑의 병사는 보고하고 걸어 나가며, 이무르에는 아이들을 엄마에게 보내는 보이지 않는 인물
    soldier_list = alts[alt_name(AFTER_BOSS, SOLDIER_MAP)]
    for i, p in enumerate(report[alt_name(AFTER_BOSS, SOLDIER_MAP)]):
        if p["talk"] == FC_SOLDIER:
            soldier_list[i] = _same(soldier_list[i], SOLDIER_SRC, t['soldier'])
    gone = [e for e in soldier_list if e["from"] != SOLDIER_SRC]
    # 이무르: 집의 아이 둘이 따라옴 깃발이 꺼질 때 걸어오고, FC 가 일행 자리로 옮기는 두 아이는 뺀다
    imuru = alt_name(AFTER_BOSS, KIDS_HOME_MAP)
    homes = {home: src for (src, _), (home, *_) in zip(HOME_KID_SRCS, KIDS_WALK_HOME)}
    kids = []
    for e, p in zip(alts[imuru], report[imuru]):
        if (p["x"], p["y"]) in KIDS_FC_WALKERS:
            continue
        src = homes.get((p["x"], p["y"]))
        kids.append(_same(e, src, e["fields"]["talk"]) if src else e)
    alts[imuru] = kids + _invisible(KIDS_HOME_SRC, t['soldier'])
    new_lists += [{"name": name, "entries": entries} for name, entries in alts.items()]
    new_lists.append({"name": "soldier_gone", "entries": gone})
    ender = {"from": ENDER_SRC, "fields": {"x": 0, "y": 1, "facing": "down", "talk": t['king'], "gfx": 0x01, "layer": 0}}
    new_lists.append({"name": "chapter_end", "entries": alts[alt_name(AFTER_BOSS, END_MAP)] +
                      [{**ender, "time": "day"}, {**ender, "time": "night"}]})
    over = lambda m, flag, name: {"map": m, "flag": flag[0], "when": "on", "mask": flag[1], "list": f"new:{name}"}  # noqa: E731
    # 앞에 둔 것부터 맞춰 본다
    overrides = [over(JAIL, REUNITED, 'jail_after'), over(JAIL, FLARE_FOLLOWS, 'jail_reunion'),
                 over(HOIMIN_ROOM, HOIMIN, 'hoimin_gone'), over(TOWER_HALL, KIDNAPPED, 'hall_empty'),
                 over(TOWER_TOP, BOSS_WON, 'top_after'), over(SOLDIER_MAP, SOLDIER_LEFT, 'soldier_gone'),
                 over(END_MAP, REPORTED, 'chapter_end')]
    overrides += [over(m, BOSS_WON, alt_name(AFTER_BOSS, m)) for state, _, maps in ALT_STATES for m in maps]
    return [{"map": k, "entries": v} for k, v in lists.items()], new_lists, overrides
