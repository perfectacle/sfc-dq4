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

NIGHT_TOLD = (0x07, 0x02)       # 7E:2197 bit1  이무르 밤에 알렉스 이름을 들음(FC $6281&80)
FLARE_FOLLOWS = (0x08, 0x04)    # 7E:2198 bit2  프레아가 따라옴(FC $627E&20)
REUNITED = (0x22, 0x04)         # 7E:21B2 bit2  감옥에서 재회함(FC $627E&40)
HOIMIN = (0x28, 0x01)           # 7E:21B8 bit0  호이민이 동료가 됨(FC $6281&40)
KIDNAPPED = (0x28, 0x20)        # 7E:21B8 bit5  탑 입구에서 마물이 아이를 끌고 감(FC $627E&01)
BOSS_WON = (0x29, 0x40)         # 7E:21B9 bit6  탑 위 보스를 이김(FC $6283&80)
KIDS_FOLLOW = (0x29, 0x80)      # 7E:21B9 bit7  구한 아이들이 따라옴(FC $6283&20). 이무르에 데려다주면 끈다
# 아래는 DQ5 레ヌール城 04/05 의 인물 스크립트만 읽는 비트(이 해킹은 04/05 에 가지 않음, dq5flags.py)
SOLDIER_LEFT = (0x06, 0x01)     # 7E:2196 bit0  탑의 병사가 먼저 돌아감(FC $6280&80)
REPORTED = (0x07, 0x80)         # 7E:2197 bit7  왕에게 보고하고 여행을 허락받음(FC $6285&04)

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
    # 우물 아래의 아이 목소리(FC 1D 이벤트 05·0B, 02EC·02EE)
    'voice_here': say('이쪽으로 와……'),
    'voice_not': say('그쪽이 아니야.'),
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
    # FC 는 말 없이 강함 창의 경험치가 3000 까지 오른다. 창 대신 서술로 알린다
    'gift': ch1.narrate('@의 경험치가/3000 포인트 올랐다!'),
    # FC 「ライアンは レベルが あがった！」. 이름 뒤 조사를 피해 옮김
    'level_up': ch1.narrate('@의 레벨이 올랐다!'),
    # FC 02F5
    'cry': say('으앙, 으앙……/살려 줘!'),
}


def message_ids(first):
    """{이름: 메시지 번호}. first 는 옮긴 메시지 다음 번호(dq4npcport.FIRST_MESSAGE + 옮긴 메시지 수)."""
    return {name: first + k for k, name in enumerate(MESSAGES)}


def texts(first):
    return {first + k: parts for k, parts in enumerate(MESSAGES.values())}


TALKS = ('child', 'alex_night', 'flare_day', 'flare_night', 'hoimin', 'boss', 'soldier', 'king', 'guard')


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
            (JAIL, FC_JAIL_FLARE, None): NOBODY, (HOIMIN_ROOM, FC_HOIMIN, None): m['hoimin_ask']}


def _msg(m):
    return {"op": "msg", "id": f"{m:03X}"}


def _flag_on(flag):
    return {"op": "flag-on", "index": flag[0], "mask": flag[1]}


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
        [_msg(m['hoimin_ask']), {"op": "if", "cond": {"code": "05"},
                                 "then": [_msg(m['hoimin_yes']), _flag_on(HOIMIN)], "else": _msg(m['hoimin_no'])}],
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
    ]


# 인물 스크립트를 빌리는 DQ5 인물: 이 해킹에서 가지 않는 DQ5 03/03 의, 스크립트가 있는 한 벌(낮·밤 따로) 인물.
# 두 벌 인물은 한 시간대에만 둘 수 없다(dq5npcrelocate 가 거부)
FLARE_SRC, FLARE_SCRIPT = {"list": "05:9180", "index": 0}, "05:9187"
WALKER_SRC, WALKER_SCRIPT = {"list": "05:9180", "index": 1}, "05:919F"
VOICE_SRCS = ({"list": "05:9180", "index": 2}, "05:91B7"), ({"list": "05:9180", "index": 3}, "05:91CF")
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


def encounter_doc():
    return {"format": "dq5encounter/1", "event_groups": [
        {"index": BOSS_GROUP, "flags": BOSS_FLAGS, "members": [{"monster": k, "count": n} for k, n in BOSS_MEMBERS]}]}


def _battle():
    flag = 0x7E2190 + BOSS_WON[0]
    return bytes((0x00, 0x0E, 0xA9, BOSS_GROUP, 0x22, 0x8B, 0x86, 0x01,       # BRK 0E / LDA #무리 / JSL $01868B
                  0xC9, 0x80, 0xF0, 0x0A, 0xAF)) + _al(flag) + bytes((0x09, BOSS_WON[1], 0x8F)) + _al(flag) + b'\x60'


# 탑 입구 30/00: 주인공이 이 줄(FC Y)에 오면 마물이 아이를 데리고 계단(09,03) 쪽으로 간다(FC 1D 이벤트 02)
KIDNAP_ROW, KIDNAP_TO = 0x09, 0x03
# 목소리가 나는 칸(FC 칸)과 메시지. FC 는 그 칸에서 왼쪽(05)·오른쪽(0B)을 보고 있을 때이고, そらとぶくつ 를
# 가졌으면 나지 않는다
VOICES = ((UNDER_WELL, (0x14, 0x0C), 'voice_here'), (HOIMIN_ROOM, (0x14, 0x10), 'voice_not'))

CODE_AT = 0x5ED000              # 서장 코드(5E:C000) 뒤의 빈 자리
COMPANION = 0x23AED1            # 동료 표: 종류마다 9바이트(처음 레벨, 최대 레벨, 능력치 넷, HP, MP, 장비 갈래)
HOIMIN_KIND = 0x05              # ホイミスライム. 이름 0 이 「ホイミン」
SCRATCH = 0x7E1BC6              # 7E:1BBE~ 의 DQ5 가 쓰지 않는 자리(서장이 1BC4 까지 씀)
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
    r[0] = 0x80 | kind
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
            bytes((0xAF,)) + _al(0x7E29EA + HOIMIN_KIND) + bytes((0x09, 0x01, 0x8F)) + _al(0x7E29EA + HOIMIN_KIND))
    return ENTER + body + LEAVE


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


def _gift():
    """주인공 경험치에 GIFT_EXP 를 더한다."""
    from dq4chapterbox import ENTER, LEAVE
    lo, hi = GIFT_EXP & 0xFF, GIFT_EXP >> 8
    body = (bytes((0xC2, 0x20, 0xAF)) + _al(HERO_EXP) + bytes((0x18, 0x69, lo, hi, 0x8F)) + _al(HERO_EXP) +
            bytes((0xE2, 0x20, 0xAF)) + _al(HERO_EXP + 2) + bytes((0x69, 0x00, 0x8F)) + _al(HERO_EXP + 2))
    return ENTER + body + LEAVE


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


def native(data=None):
    """(바이트, {이름: 주소}). 기록 자료가 앞, 루틴이 뒤. 주소는 data(롬, 동료 표를 읽음)와 상관없다."""
    record = companion_record(data, HOIMIN_KIND) if data is not None else bytes(len(PARTY_TEMPLATE))
    out, at = bytearray(record), {'record': CODE_AT}
    at['join'] = CODE_AT + len(out)
    out += _join(CODE_AT)
    for m, (x, y), _ in VOICES:
        at[m] = CODE_AT + len(out)
        out += _at(*ch1_cell(x, y))
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
                       ('gift', _gift()), ('level_up', _level_up()), ('open_cage', _open_cage())):
        at[name] = CODE_AT + len(out)
        out += code
    return bytes(out), at


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
    _, at = native()
    fx, fy = TOWER_FIELD[0] * 2, TOWER_FIELD[1] * 2      # FC 필드 칸 → DQ5 필드 좌표(그룹 연결의 필드 입구와 같은 셈)
    for addr, orig, new in ((FLY_AT, FLY_ORIG, bytes((0x22, *_long(at['fly']), 0xEA))),
                            (FLY_X_AT, FLY_XY_ORIG[0], fx.to_bytes(2, 'little')),
                            (FLY_Y_AT, FLY_XY_ORIG[1], fy.to_bytes(2, 'little'))):
        o = lorom(addr)
        if bytes(d[o:o + len(orig)]) != orig:
            raise SystemExit(f'{addr:06X}: 원래 바이트가 아님 {d[o:o + len(orig)].hex()}')
        d[o:o + len(new)] = new
    return bytes(d)
REUNION_AT = (0x04, 0x03)       # FC 슬롯 07 이 걸어가 서는 칸, 재회 뒤 슬롯 08 의 자리


def _cmd(op, *args):
    return {"op": op, "args": list(args)}


def scripts(first_message, box_at=None):
    """box_at: 2장 제목 상자 네이티브(dq4chapterbox.entry_points 의 box2)."""
    m = message_ids(first_message)
    _, at = native()
    lo, hi = lambda v: v & 0xFF, lambda v: v >> 8
    return [
        # 따라오기로 하면 사라진다. 다시 들어와도 곧바로 숨는다
        {"address": FLARE_SCRIPT, "commands": [_cmd('09', 0x80 | FLARE_FOLLOWS[0], FLARE_FOLLOWS[1]),
                                               _cmd('28'), _cmd('52'), _cmd('16')]},
        # 감옥에 들어서면 계단 쪽에서 알렉스 옆까지 걸어와 재회한다
        {"address": WALKER_SCRIPT, "commands": [
            _cmd('3F'), _cmd('13', REUNION_AT[0] * 2, REUNION_AT[1] * 2 + 1), _cmd('14'),
            _cmd('21', lo(m['reunion']), hi(m['reunion'])), _cmd('21', lo(m['hint']), hi(m['hint'])),
            _cmd('10', *REUNITED), _cmd('40'), _cmd('16')]},
    ] + [
        # 보이지 않는 인물이 칸을 기다렸다가 목소리를 띄운다. 52 로 자리를 치워 길을 막지 않는다
        {"address": script, "commands": [_cmd('28'), _cmd('52'), _cmd('05', *_long(at[where])), _cmd('3F'),
                                         _cmd('21', lo(m[msg]), hi(m[msg])), _cmd('40'), _cmd('16')]}
        for (_, script), (where, _, msg) in zip(VOICE_SRCS, VOICES)
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
                                                         _cmd('10', *KIDS_FOLLOW), _cmd('40')], 0x0E)},
        {"address": SOLDIER_SCRIPT, "commands": [_cmd('09', 0x80 | SOLDIER_LEFT[0], SOLDIER_LEFT[1]), _cmd('3F')] +
         [c for x, y in SOLDIER_PATH for c in (_cmd('13', *ch1_cell(x, y)), _cmd('14'))] +
         [_cmd('28'), _cmd('52'), _cmd('40'), _cmd('16')]},
        # 보이지 않는 인물: 아이들이 따라오는 동안 이 줄에 오면 엄마 곁으로 보내고 따라옴 깃발을 끈다(11 은 AND)
        {"address": KIDS_HOME_SCRIPT, "commands": [
            _cmd('28'), _cmd('52'), _cmd('09', 0x80 | KIDS_FOLLOW[0], KIDS_FOLLOW[1]),
            _cmd('05', *_long(at['kids_home_row'])), _cmd('3F'), _cmd('21', lo(m['kids_home']), hi(m['kids_home'])),
            _cmd('11', KIDS_FOLLOW[0], ~KIDS_FOLLOW[1] & 0xFF), _cmd('40'), _cmd('16')]},
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
        {"address": KING_CALL_SCRIPT, "commands": [
            _cmd('28'), _cmd('52'), {**_cmd('05', *_long(at['king_row'])), "label": "wait"}, _cmd('3F'),
            {**_cmd('06', *KIDS_FOLLOW), "target": "back"},
            _cmd('21', lo(m['king_praise']), hi(m['king_praise'])), _cmd('21', lo(m['gift']), hi(m['gift'])),
            _cmd('37', *_long(at['gift'])),
            # 한 번 오를 때마다 「레벨이 올랐다」. 더 오르지 않으면 level_up 이 보고 깃발을 켠다
            {**_cmd('37', *_long(at['level_up'])), "label": "grow"}, {**_cmd('06', *REPORTED), "target": "grown"},
            _cmd('21', lo(m['level_up']), hi(m['level_up'])), {"op": "03", "args": [], "target": "grow"},
            {**_cmd('21', lo(m['king_farewell']), hi(m['king_farewell'])), "label": "grown"},
            _cmd('10', *REPORTED), _cmd('40'), _cmd('16'),
            {**_cmd('21', lo(m['king_back']), hi(m['king_back'])), "label": "back"}, _cmd('40'),
            _cmd('05', *_long(at['king_away'])), {"op": "03", "args": [], "target": "wait"}]},
    ] + ([
        # 1장 끝: 서술 → 검은 화면 → 2장 제목 상자 → 어둡게. 조작은 풀지 않는다(2장은 아직 이어지지 않음)
        {"address": ENDER_SCRIPT, "commands": [
            _cmd('28'), _cmd('52'), _cmd('3F'), _cmd('21', lo(m['chapter_end']), hi(m['chapter_end'])),
            _cmd('37', *_long(at['darken'])), _cmd('37', *_long(box_at)), _cmd('37', *_long(at['fade_out'])),
            _cmd('16')]},
    ] if box_at is not None else [])


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
    for (src, _), (where, (x, y), _) in zip(VOICE_SRCS, VOICES):
        cx, cy = ch1_cell(x, y)
        voice = {"from": src, "fields": {"x": cx, "y": cy, "facing": "down", "talk": t['hoimin'], "gfx": 0x01,
                                         "layer": 0}}
        lists[where] += [{**voice, "time": "day"}, {**voice, "time": "night"}]
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
