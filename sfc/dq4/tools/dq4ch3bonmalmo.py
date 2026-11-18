"""DQ4 3장 본몰·여우 마을 사건(dq4ch3slots 'B'): 왕자 릭, 감옥의 톰 아들, 여우 마을, 다리, 편지 둘.

FC 를 헤드리스로 잰 흐름(fc/dq4/docs/dq4-chapter3-format.md 「사건 차례」 6~14)을 대화 스크립트·빌린 인물 스크립트·이벤트로
옮긴다. 형식은 sfc/dq4/docs/dq4-chapter3-format.md 「본몰·여우 마을」.

  왕자   낮 첫 만남은 0837·0838 뒤 유모의 꾸지람 03B0·03B1(FC 는 유모가 걸어와 말함, 일행은 그 자리). 밤에는 무기점 뒤에서 0839 와
         왕자의 편지(소지품이 가득이면 036A 만).
  감옥   톰 아들(083F)에게 키메라의 날개가 있으면 0840, 「아니요」 면 0841 뒤 다시 묻고 「예」 면 0842, 날개를 받아
         사라진다.
  여우   촌장(05E)은 개 토마스가 따라오면(공용 DOG) 084C 뒤 아침의 숲(48/01)으로 바뀌고(날수 + 1), 여우가 빌며(084D,
         「아니요」 면 084E 뒤 다시) 강철 갑옷을 주고 떠난 뒤(FOXED) 돈 가아데가 나타나 03B2 를 말하고 떠난다. 개가
         없으면 묵어 가라 하고(0824~0826) 숲에서 아침에 깬다(날수 + 1, HP 는 그대로). 여우를 쫓은 뒤에는 여우 마을에
         들면 곧바로 숲 어귀로 간다.
  다리   본몰 왕(06B)은 FOXED 면 0674 와 BRIDGE. BRIDGE 가 꺼진 3장 동안 필드에 나가면 다리 칸이 막힌다(필드 진입 훅).
  편지   왕자의 편지를 가진 채 엔돌 공주 모니카에게 말을 걸면 0349·03A0·03A1(왕의 편지로 바뀜), 왕의 편지를 가진 채
         본몰 왕에게 말을 걸면 03A4. FC 는 그 자리에서 편지를 「쓴다」(12:$B32D·$B2FE).
"""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4chapter1 as ch1  # noqa: E402
import dq4ch2event as ch2  # noqa: E402
import dq4ch3event as ch3  # noqa: E402
import dq4ch1event  # noqa: E402
from dq4chapterbox import ENTER, LEAVE  # noqa: E402
from dq4ch2endor import Asm, BCC, BCS, BEQ, BNE, BRA, lda, sta  # noqa: E402
from dq4itemport import KING_LETTER, PRINCE_LETTER  # noqa: E402

say, narrate = ch1.say, ch1.narrate
pages = ch2._speaker_pages
_al = ch2._al

# 7E:2203·2204(dq4ch3slots B): 저장되는 진행
FOXED = (0x73, 0x01)           # 여우를 쫓음(FC $6280&02). 다리 고치기·개 돌려주기·여우 마을 어귀가 본다
PRINCE_MET = (0x73, 0x02)      # 낮에 왕자를 만나 유모에게 꾸지람을 들음(FC $6280&08)
SON_FREED = (0x73, 0x04)       # 톰 아들에게 키메라의 날개를 줌(FC $6280&04)
BRIDGE = (0x73, 0x08)          # 다리가 고쳐짐(FC $6286&10). 꺼진 3장 동안 필드의 다리 칸이 막힘
LETTER1 = (0x73, 0x10)         # 왕자의 편지를 모니카에게 전함(FC $6280&01)
LETTER2 = (0x73, 0x20)         # 왕의 편지를 본몰 왕에게 전함(FC $6283&01)
FOX_SCENE = (0x74, 0x01)       # 촌장이 개에 놀라 숲으로 바뀜: 숲의 여우가 빌기를 기다림
FOX_LET = (0x74, 0x02)         # 여우를 놓아줌(갑옷을 받음)
FOX_GONE = (0x74, 0x04)        # 여우가 사라짐: 돈 가아데가 말을 건다
FLAGS = (FOXED, PRINCE_MET, SON_FREED, BRIDGE, LETTER1, LETTER2, FOX_SCENE, FOX_LET, FOX_GONE)
ANSWERED = ch2.ANSWERED        # 7E:21A3 bit0 대화가 끝남(talk_here 를 되풀이하는 인물 스크립트가 기다림)
# 7E:21A3 bit4(맵을 옮기면 지워짐): 이번 방문에 유모에게 꾸지람을 들음(FC $6289&40, FC 는 필드로 나갈 때 지움). 마을 사람
# 모듈의 유모(대화 05F)가 보고 03B1 을 고른다. 3F/01 에서 이 비트를 쓰는 도구는 없다
NANNY_SCOLDED = (0x13, 0x10)
# 7E:21A3 bit7(맵을 옮기면 지워짐): 왕자가 처음 말을 마침, 유모가 걸어온다. NANNY_SCOLDED 와 따로 두어 그 비트만 켠
# 상태(마을 사람 모듈의 검사)에서는 유모가 제자리에 있다
NANNY_GO = (0x13, 0x80)
# 예·아니요를 「예」 까지 되묻는 깊이(대화 스크립트에는 되돌아가는 명령이 없어 갈래를 겹쳐 쌓는다)
ASK_DEPTH = 8

WINGS = 0xA4                   # DQ5 キメラのつばさ(FC 56)
STEEL_ARMOR = 0x51             # DQ5 はがねのよろい(FC 2A)

CASTLE, PRISON = '3F/01', '3F/00'      # FC 05/01 본몰 성, 05/00 감옥
FOX_TOWN, FOREST = '48/00', '48/01'    # FC 18/00 여우 마을, 18/01 숲
ENDOR_THRONE = '40/06'                 # FC 04/06 엔돌 왕좌의 방


def cell(x, y):
    return (2 * x, 2 * y + 1)


# 옮긴 인물(dq4npcport)의 셀
PRINCE = {'day': cell(0x01, 0x0B), 'night': cell(0x20, 0x06)}     # FC 05/01 슬롯 06, 대화 061
KING = cell(0x11, 0x07)                                           # FC 05/01 왕, 대화 06B
SON = cell(0x0D, 0x0C)                                            # FC 05/00 슬롯 08, 대화 065
SON_SIDE = cell(0x0B, 0x0C)                                       # 창살 (0C,0C) 너머 아들에게 말을 거는 칸
# 감옥 병사 둘(FC 05/00 대화 066, (0A,0E)·(02,07)). FC 는 (0A,07)→(0A,0E)→(02,0E)→(02,07) 을 돌다가(블록 05:$8EBE) 보는
# 방향의 세 줄(제 줄과 양옆) 한 칸 앞부터 벽까지에 주인공이 들면 조작을 막고 0307 → 일행 쪽으로 8프레임/칸 곧게 걸어 맞닿은
# 칸에서 멈춤 → 034A → 3F/01 FC (19,02) 왼쪽을 보고(이벤트 24·25, 1D:$A213·$98BD·$A24C). 두 창은 A 없이 닫히고, 다시
# 들어오면 또 걸린다(실측)
GUARDS = ((0x0A, 0x0E), (0x02, 0x07))
JAIL_LOOP = ((0x0A, 0x07), (0x0A, 0x0E), (0x02, 0x0E), (0x02, 0x07))
JAIL_OUT = ('3F/01', (0x19, 0x02))
# 맵 안 임시 값(7E:21A2·21A4 는 3F/00 에서 다른 쓰임이 없음): 들킴 bit, 들킨 병사의 인물 칸
SPOTTED = (0x14, 0x40)
SPOTTER = 0x7E21A2
# 순찰은 한 칸씩 목표를 두고(jail_step 이 닿을 때마다 다음 칸) 다음 칸을 이 주기(프레임, 2의 거듭제곱)에 한 번만 정해
# FC 병사의 33프레임/칸에 맞춘다. 속도 01 이면 한 칸을 16프레임에 걸어 주기 안에 닿는다
PATROL_PERIOD = 32
PATROL_WINDOW = 4             # 주기의 앞 몇 프레임에 다음 칸을 정하나(순찰 고리는 명령 셋이라 그보다 넓게)
PATROL_SPEED, APPROACH_SPEED = 0x01, 0x02    # 인물 명령 1E. 01 은 16프레임/칸(00 은 서 있음), 02 는 유모처럼 8프레임/칸
# 시야를 막는 FC 칸(05/00 의 벽·창살). 실측 근거는 dq4-chapter3-format 「본몰 감옥 병사」
SIGHT_BLOCKS = {0x28, 0x2B}
CHIEF = cell(0x0C, 0x01)                                          # FC 18/00 슬롯 07, 대화 05E
FOX = cell(0x04, 0x0D)                                            # FC 18/01 슬롯 06, 대화 2D2
GAADE = cell(0x11, 0x0D)                                          # FC 18/01 슬롯 07(맵 오른쪽 밖)
MONICA = cell(0x0F, 0x0A)                                         # FC 04/06 공주(3장 대화 073, 2장 03A)
# 숲에서 깨는 칸·여우 장면이 서는 칸(FC 18/01 (04,0C)), 여우를 쫓은 뒤 필드에서 드는 칸(FC 18/01 (00,0F), 08:$AF52)
FOREST_WAKE = cell(0x04, 0x0C)
FOREST_ENTRY = cell(0x00, 0x0F)
# 여우 장면(실측): 여우는 (05,04) 로 올라가 사라지고, 돈 가아데는 (07,0D) 에 나타나 (04,0D) 에서 03B2 뒤 (00,0D) 로 떠난다.
# 걷기 13 은 X 를 먼저 맞춘다. 두 길 모두 주인공 칸((04,0C))을 지나지 않는다(겹침은 dq4heroblockcheck bm-fox-right)
FOX_LEAVE = (cell(0x05, 0x0D), cell(0x05, 0x04))
GAADE_IN, GAADE_TALK, GAADE_OUT = cell(0x07, 0x0D), cell(0x04, 0x0D), cell(0x00, 0x0D)
FACE_LEFT, FACE_DOWN = 0x20, 0x40   # 인물 명령 2F(7E:31E0 위 니블: 88 위, 11 오른쪽, 44 아래, 22 왼쪽)
NANNY = cell(0x06, 0x06)                                          # FC 05/01 슬롯 07 유모(대화 05F)
# FC 유모 블록 05:$8EFE 의 길(실측): (06,06) → (06,08) → (04,08) 에서 아래를 보고, (04,09) 로 한 걸음 와서 03B0·03B1
NANNY_PATH = (cell(0x06, 0x08), cell(0x04, 0x08), cell(0x04, 0x09))
# 여우를 쫓은 뒤 들어오기: 입구별 도착 훅(dq4entrancehook, 2A:F28D 의 JML)보다 먼저 그룹 48 의 여우 마을 입구 블록
# (FC 필드 (7C,34), DQ5 필드 칸 x 248~249·y 104~105)이면 FC 08:$AF52 처럼 처음부터 숲 어귀로 부른다. 그 밖은 원래 훅으로
ENTER_SITE = 0x2AF28D
ENTER_BACK = 0x2AF291          # 훅이 끝에 원래 두 명령(LDA $BC / CMP #$16)을 하고 돌아가는 곳
FOX_GATE = (0x7C * 2, 0x34 * 2)
FOX_GROUP = 0x48
# FC 18/00 슬롯 06 마을의 개(대화 2C4, 맵 구석 (00,00)에 숨어 있음). 개 토마스가 따라올 때 주인공이 (14,13)에 서면
# 02F1 뒤 따라 걷던 개 자리 (14,14)에 나타나 (14,0C)→(19,0C)→(19,02)→(0F,02)로 달린 뒤 촌장 옆 (0D,01)에 선다(실측)
CORNER_DOG = cell(0x00, 0x00)
DOG_TRIGGER = (0x14 * 2, 0x13 * 2 + 1, 0x14 * 2 + 1, 0x13 * 2 + 2)
DOG_FROM = cell(0x14, 0x14)
DOG_RUN = (cell(0x14, 0x0C), cell(0x19, 0x0C), cell(0x19, 0x02), cell(0x0F, 0x02))
DOG_STAND = cell(0x0D, 0x01)
# 짖은 뒤 이 맵 동안 따라 걷던 개가 줄을 떠남(FC 는 일행 슬롯 1 을 숨김). 걷는 그림 장치가 이 맵에서만 본다
DOG_AWAY = dq4ch1event.DOG_AWAY
DOG_SPEED = 0x02               # 인물 명령 1E(7E:3360). 빌린 레코드의 속도로는 걷기가 끝나지 않을 수 있다(dq4ch3lakanaba)
# 3장 레이크나바 우리의 개(dq4ch3lakanaba.DOG) 그림을 쓴다
KENNEL_DOG = ('3E/00', cell(0x1B, 0x04))
# 둘째 유모(FC 05/01 레코드 15 (06,07), 대화 05F). FC 는 그 맵에 인물 슬롯 06~0C 일곱만 실어 이 사람은 나타나지 않는다(실측).
# 이 롬은 다 실어 유모가 걷는 길을 막아 뺀다
SECOND_NANNY = cell(0x06, 0x07)

# 빌릴 인물 스크립트(dq4ch3slots B: 10:BEE5 칸 2·4~9). 칸마다 한 시간대에만 놓인다
LIST = '10:BEE5'
SCRIPTS = {'fox': (LIST, 2, '10:BEFA'), 'gaade': (LIST, 4, '10:BF14'), 'son': (LIST, 5, '10:BF27'),
           'nanny': (LIST, 6, '10:BF45'), 'village_dog': (LIST, 7, '10:BF63'), 'village_dog_night': (LIST, 8, '10:BF81'),
           # 감옥 병사 둘이 함께 씀(자리로 다음 모퉁이를 고르므로 누가 누구인지 가리지 않음)
           'guard': (LIST, 9, '10:BF9F')}

# 다리: FC 필드 0 의 블록 16(다리). FC 는 3장에서 $6286 bit4 가 꺼져 있으면 그 블록 정의를 00 17(속성 80, 막힘)로
# 올린다(08:$808E, fc/dq4/docs/dq4-block-format.md). 이 롬은 그 칸들을 같은 512 갈래의 막힌 블록(암초: 물 위 바위)으로
# 바꾼다. 10·11번째 비트 평면은 롬이라 바꿀 수 없어, 같은 평면 값(번호 // 512)의 블록끼리만 7F 바이트로 바꿀 수 있다
# 필드를 불러올 때 한 번 움직이는 바다를 만드는 JSL(세계 지도를 푼 뒤, 수문 칸을 쓰는 01:9FDA 앞). 바로 뒤 01:9FD6 은 환경 훅
# wrap 이 세 자리를 한 대상으로 묶어 지키므로(dq4wrapcheck) 건드리지 않는다
FIELD_CALL = 0x019FD2
SEA_FRAMES = 0x01C5C8
WORLD = 0x7E1949               # 지금 세계(0: FC 필드 0)
MAP_AT = 0x7F0000              # 세계 지도(256 × 256, 블록 번호 아래 8비트)
FC_BRIDGE, FC_REEF = 0x16, 0x0A
# FC 필드 0 의 블록 16 칸 전부(bridge_cells 와 같은지 test_dq4ch3bonmalmo 가 FC 롬으로 봄). 3장에 닿는 것은 (6F,4F)·(6D,63)
BRIDGE_CELLS = ((0xC8, 0x48), (0xCF, 0x4A), (0xD8, 0x4A), (0x6F, 0x4F), (0x6D, 0x63), (0xBD, 0x7B), (0x33, 0xB9),
                (0x25, 0xBA))


def bridge_cells(dq4=None):
    """FC 필드 0 의 다리 칸 [(x, y)](FC 블록 (x, y) 가 DQ5 블록 (x, y)). dq4 는 FC 롬 경로."""
    sys.path.insert(0, str(HERE.parents[2] / 'fc' / 'dq4' / 'tools'))
    import dq4field
    from kr_patch.fc import ines
    prg = ines.prg(Path(dq4 or HERE.parents[2] / 'rom' / 'dq4.nes').read_bytes())
    grid = dq4field.decode(prg, 0)
    return [(x, y) for y, row in enumerate(grid) for x, b in enumerate(row) if b & 0x1F == FC_BRIDGE]


def bridge_blocks():
    """(다리 블록, 막힌 블록) DQ5 번호."""
    import dq4fieldport
    bridge, blocked = dq4fieldport.OWN_BLOCKS[FC_BRIDGE], dq4fieldport.OWN_BLOCKS[FC_REEF]
    if bridge >> 8 != blocked >> 8:
        raise SystemExit(f'다리 {bridge}·막힌 블록 {blocked}: 9번째 비트 위가 달라 7F 바이트로 바꿀 수 없음')
    return bridge, blocked


def _bridge_hook(old, cells):
    """FIELD_CALL 이 부를 루틴: 원래 대상을 부른 뒤, 3장이고 다리가 고쳐지지 않았고 세계 0 이면 다리 칸을 막힌 블록으로."""
    _, blocked = bridge_blocks()
    flag = lambda f: lda(0x7E2190 + f[0])  # noqa: E731
    a = Asm()(0x22, *_al(old), 0x08, 0xE2, 0x20)
    a(flag(ch3.CHAPTER3), 0x29, ch3.CHAPTER3[1]).br(BEQ, 'done')
    a(flag(BRIDGE), 0x29, BRIDGE[1]).br(BNE, 'done')
    a(lda(WORLD)).br(BNE, 'done')
    a(0xA9, blocked & 0xFF)
    for x, y in cells:
        a(sta(MAP_AT + y * 256 + x))
    a.label('done')(0x28, 0x6B)
    return a.bytes()


def _join(*parts):
    """메시지 여럿(끝 코드 달린 코드 목록)을 쪽 넘김으로 이어 한 메시지로."""
    out = []
    for p in parts:
        body = p[:-1] if p and p[-1] == ch1.END else p
        if out and body and body[0] != ch1.PAGE:
            out.append(ch1.PAGE)
        out += body
    return out + [ch1.END]


# 메시지. FC 원문 뜻대로 옮겼다. 인물은 입말, 서술은 해라체
def _held(message):
    """시간이 지나면 닫는 창의 메시지: 끝 코드 1001 은 넷째 줄 뒤에서 밀어 올리며 ▼ 를 기다려(실측) 1018(커서만 내림)로."""
    assert message[-1] == ch1.END
    return message[:-1] + [0x1018]


MESSAGES = {
    # 왕자 릭(FC 05/01, 대화 061)
    'prince_hello': pages('릭', '저는 릭./이 나라의 왕자예요.', '당신을 여행하는/상인이라 보고/부탁하고 싶은 게/있는데요…….',  # 0837·0838
                          '자세한 이야기는/밤에 무기점/뒤에서…….'),
    'prince_tip': pages('릭', '자세한 이야기는/밤에 무기점/뒤에서…….'),                                               # 0838
    'nanny_stop': _held(say('왕자님!/그런 천한 자와/이야기하시면/안 됩니다!')),                                       # 03B0
    'nanny_out': _held(say('자! 나가세요!')),                                                                          # 03B1
    'prince_night': pages('릭', '아, 와 주셨군요./저예요. 이 성의/왕자 릭이에요.',                                     # 0839
                          '실은 부탁인데요,/다리가 고쳐지면/바로 엔돌에/가 주셨으면 해요.',
                          '그리고 이 편지를/성의 공주에게/전해 주세요.'),
    'got_prince_letter': narrate('톨네코는 편지를/받았다!'),                                                           # 083A
    'prince_full': pages('릭', '하지만 더는 물건을/가질 수 없는 것/같네요. 팔든지 버리든지/하고 다시 와 주세요.'),     # 036A
    'prince_ask': pages('릭', '그럼 부탁할게요.'),                                                                     # 083B
    'prince_wait': pages('릭', '다리가 고쳐지는/대로 그 편지를/엔돌의 공주에게!/꼭 부탁드려요!'),                      # 083C
    'prince_after': pages('릭', '아버님께 이야기는/들었어요. 혹시/엔돌에 가거든/모니카에게 전해 줘요.',               # 088F
                          '당신과 결혼할/날이 너무나/기다려진다……고!'),
    # 감옥의 톰 아들(FC 05/00, 대화 065)
    'son_ask': say('톨네코! 톨네코 씨지?/나야 나!/그래그래, 톰 영감의/아들이야.',                                       # 083F
                   '실수해서 여기/갇히고 나니/뼈저리게 알았어./나쁜 짓은 이제 질색이야.',
                   '당신 상인이었지?/그럼 키메라의 날개를/사다 줘.'),
    'son_wings': say('뭐? 벌써/갖고 있다고?/그럼 그거 나 줘!/마을에 가면 답례할게!'),                                   # 0840
    'son_please': say('그러지 말고/좀 줘!'),                                                                            # 0841
    'son_thanks': _join(say('야호, 고마워!/알아 알아! 마을에/돌아가면 착실하게/일할게.',                                # 0842
                            '그럼 한발 먼저/마을에 돌아가/있을게!'),
                        narrate('톰의 아들은/키메라의 날개를/던졌다!')),
    # 여우 마을 촌장(FC 18/00, 대화 05E)
    'chief_welcome': say('어서 오시오, 길손이여./길이라도/잃으셨소?'),                                                  # 0824
    'chief_stay': say('그거 곤란하시겠군./묵어 가시는 게/어떻겠소?'),                                                    # 0825
    'chief_rest': say('그럼 편히/쉬시구려.'),                                                                            # 0826
    'chief_bye': say('그렇소……./그럼 조심해서/여행을 계속하시길./허허허.'),                                            # 0827
    'chief_dog': say('으아, 살려 줘!/개는 질색이야!', '아아, 안 돼……/내 신통력이…….'),                                 # 084C
    # 숲의 여우(FC 18/01)
    'fox_beg': say('캥캥, 졌어요./제발 놓아주세요./다시는 나쁜 짓/안 할게요…….'),                                       # 084D
    'fox_please': say('그런 심술궂은 말/하지 말고/놓아주세요오.'),                                                       # 084E
    'fox_gift': say('다행이다!/놓아주는 답례로/이 갑옷을/드릴게요.'),                                                    # 084F
    'got_armor': narrate('톨네코는/강철 갑옷을/손에 넣었다.'),                                                          # 02A0
    'fox_bye': say('캥캥./그럼 안녕히.'),                                                                                # 0850
    'gaade': say('저는 돈 가아데라고/합니다만/대체 이게/어떻게 된 걸까요?',                                              # 03B2
                 '정신을 차려 보니/마을이/없어져서는…….', '그렇지!', '어서 본몰 성에/가야 하는데……./그럼 실례!'),
    # 본몰 왕(FC 05/01, 대화 06B)
    'king_wait': say('에잇! 돈 가아데는/아직이냐!?/대체 어디서/딴짓을 하는 게냐!',                                      # 0670
                     '어서 다리를 고쳐야/엔돌 나라에/쳐들어갈 수/있지 않느냐!'),
    'king_bridge': say('역시 돈 가아데!/오자마자 다리를/고쳐 놓고 갔구나!',                                              # 0674
                       '이제 드디어/엔돌에도/쳐들어갈 수 있겠구나!/와하하하!'),
    'king_letter': pages('왕', '뭐라, 그런/일이었단 말이냐!?',                                                         # 03A4
                         '언젠가 내 아들 릭이/엔돌 왕의 사위가/된다면 릭이 다음/엔돌 왕이로다!',
                         '쳐들어가지 않아도/엔돌이 손에/들어오지 않느냐!',
                         '수고했다. 당장/사자를 보낼 테니/그대는 물러가도/좋다.'),
    'king_after': say('내 아들 릭이/다음 엔돌의/왕이로다!/와하하.'),                                                    # 088E
    # 엔돌 공주 모니카(FC 04/06)
    'monica_letter': _join(narrate('톨네코는 왕자의/편지를 읽었다.'),                                                    # 0349
                           say('사랑하는 엔돌의/공주 모니카여.', '그대와의 일을/아버님께 말하지/못한 채 여러 날이/지나고 말았소.',
                               '게다가 무섭게도/아버님은 그대의/나라 엔돌에/쳐들어갈 셈인 듯하오.',
                               '그리 되기 전에/어떻게든 해야 하오./부디 이 일을/그대의 아버님께…….'),
                           pages('모니카', '어머, 릭도 참!/어서 아버님께/알려야겠어!/아버님!')),                         # 03A0
    'endor_king_letter': pages('왕', '내 귀여운 딸/모니카야. 이야기는/나도 들었느니라.', '하지만 걱정할/것 없느니라!',   # 03A1
                               '톨네코라 했던가./이 편지를 본몰의/왕에게 전해/주지 않겠느냐?'),
    'got_king_letter': narrate('톨네코는 왕의/편지를 받았다!'),
    'endor_king_ask': pages('왕', '부디 잘 부탁하네.'),
    # 3장 모니카(FC 04/06 슬롯 09, 대화 073)
    'monica_hello': pages('모니카', '레이크나바에서/오셨어요? 어머,/부서졌던 다리가/고쳐졌군요.'),                      # 0883
    'monica_trust': pages('모니카', '아버님께는 분명/좋은 생각이/있으실 거예요./아버님을 믿어요.'),                     # 0884
    'monica_thanks': pages('모니카', '사랑하는 릭과의/결혼을 허락받다니/마치 꿈만 같아요!',                             # 0885
                           '톨네코라고 했죠./진심으로/감사드려요.'),
    # 여우 마을의 개(FC 18/00 슬롯 06): 말을 걸면 0663, 달려가기 전 02F1(같은 글이지만 A 없이 닫혀 끝 코드가 다름)
    'woof': say('멍멍멍!'),
    'woof_run': _held(say('멍멍멍!')),
    # 감옥 병사(FC 05/00 대화 066): 일행을 보면 0307, 다가와 034A(마을 사람 모듈의 같은 대사와 같은 글)
    'jail_who': _held(say('웬 놈이냐!')),                                                                              # 0307
    'jail_out': _held(say('여기는 감옥이다!/죄수와 이야기하는/것은 허락할 수/없다! 자, 나가시오!')),                  # 034A
}
TALKS = ('prince', 'king', 'son', 'chief', 'fox', 'monica', 'dog')
CALLS = {'give_prince_letter': ('give', PRINCE_LETTER), 'take_prince_letter': ('take', PRINCE_LETTER),
         'give_king_letter': ('give', KING_LETTER), 'take_king_letter': ('take', KING_LETTER),
         'take_wings': ('take', WINGS), 'give_armor': ('give', STEEL_ARMOR),
         'room': ('room', 0), 'fox_go': ('fox_go', 0), 'inn': ('inn', 0), 'jingle': ('jingle', 0)}
ITEM_SONG = 0x2F               # 물건을 받는 징글(dq4ch2frenol.ITEM_SONG, 끝을 기다리는 곡)
# 네이티브 가운데 코드가 아닌 이벤트 스크립트(dq4brkscan)
DATA_ENTRIES = ('fox_event', 'inn_event', 'jail_event', 'jail_walls')
# PHP 없이 JSL 로 시작하는 훅(원래 대상을 먼저 부름)
CODE_ENTRIES = ('bridge_hook',)


# ---- 네이티브 ----

def _set(flag):
    a = 0x7E2190 + flag[0]
    return bytes((0xAF,)) + _al(a) + bytes((0x09, flag[1], 0x8F)) + _al(a)


def _warp(mp, at, facing=0):
    """이벤트 명령 90: 맵을 옮겨 셀 at 에 섬. facing 은 $198E bit0-1(0 위, 1 오른쪽, 2 아래, 3 왼쪽)."""
    g, n = (int(v, 16) for v in mp.split('/'))
    return bytes((0x90, g, n, *at, 0x01, 0x80 | facing))


def _morning():
    return bytes((0xC2, 0x20, 0xA9, *ch2.MORNING.to_bytes(2, 'little'))) + sta(ch2.TIME_AT) + bytes((0xE2, 0x20))


CGRAM_NOW, CGRAM_KEEP = 0x7E3914, 0x7E3B14   # 지금 색(NMI 가 $1A bit1 이면 CGRAM 으로 보냄, 00:8EE?) / 밝히기 목표 색
FLASHES, FLASH_FRAMES = 6, 3                 # FC 084C 뒤 회색 3프레임·원래 색 3프레임을 여섯 번(실측 851~881)
# 페이드 아웃 뒤 검은 채 기다림. 워프의 맵 불러오기(43프레임쯤)와 합쳐 FC 의 182프레임(실측 894~1075)
DARK_FRAMES = 139
FADE_LEVELS = (13, 11, 9, 7, 5, 3, 1, 0)     # 한 프레임에 두 단계씩: FC 페이드 아웃 9프레임(885~893)


# 맵 밝히기 루틴(00:CEC3, X 프레임마다 $1D 아래 넷 비트를 0F 까지 1씩, 16번)의 들머리. 워프 뒤 숲을 밝힐 때 여우 장면이면
# $1D 를 FOREST_FADE_FROM 에서 시작해 FC 처럼 4프레임 만에 밝힌다(FC 1076~1079 실측). 그 밖의 밝히기는 그대로
FADE_IN_SITE = 0x00CEC3
FADE_IN_ORIG = bytes((0x08, 0xC2, 0x30, 0x48))      # PHP / REP #$30 / PHA
FOREST_FADE_FROM = 0x0B


def _fade_in_hook():
    g, n = (int(v, 16) for v in FOREST.split('/'))
    a = Asm()(0x08, 0xE2, 0x20, lda(0x7E2190 + FOX_SCENE[0]), 0x29, FOX_SCENE[1]).br(BEQ, 'off')
    a(0xAF, 0xBC, 0x00, 0x7E, 0xC9, g).br(BNE, 'off')(0xAF, 0xBD, 0x00, 0x7E, 0xC9, n).br(BNE, 'off')
    a(0xAF, 0x1D, 0x00, 0x7E, 0x29, 0x80, 0x09, FOREST_FADE_FROM, 0x8F, 0x1D, 0x00, 0x7E)
    a.label('off')(0x28, FADE_IN_ORIG, 0x5C, *_al(FADE_IN_SITE + len(FADE_IN_ORIG)))
    return a.bytes()


# FC 05/00(18×21 칸)에서 시야를 막는 칸의 비트맵, 줄마다 3바이트(bit7 이 왼쪽 칸). 롬에서 푼 값(fc_jail_walls)과 같은지
# 단위 시험이 본다
JAIL_W, JAIL_H = 18, 21
JAIL_WALLS = bytes.fromhex('FFFFC0 841040 841040 841040 841040 FFFFC0 800040 800040 800840 9B8FC0 910840 918840 908840 '
                           '9F8840 800FC0 800840 FFF840 840840 840840 840840 FFFFC0'.replace(' ', ''))


def fc_jail_walls(dq4_rom):
    """FC 롬의 05/00 에서 JAIL_WALLS 를 다시 만든다."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'fc' / 'dq4' / 'tools'))
    import dq4map
    from kr_patch.fc import ines
    _, w, h, cells = dq4map.load(ines.prg(dq4_rom), 0x05, 0x00)
    out = bytearray()
    for y in range(h):
        bits = bytearray((w + 7) // 8)
        for x in range(w):
            if cells[y * w + x] in SIGHT_BLOCKS:
                bits[x >> 3] |= 0x80 >> (x & 7)
        out += bits
    return w, h, bytes(out)


def jail_walls():
    return JAIL_W, JAIL_H, JAIL_WALLS


# 인물 스크립트 네이티브는 DB 7E·직접 페이지 0 에서 불린다. 지금 인물 칸은 $90(01:C810), X·Y 는 7E:3020·3080(셀, 높은 바이트
# 3040·30A0), 걷는 목표는 3560·35A0(명령 13, 01:CB4A), 방향은 31E0(10 오른쪽·20 왼쪽·40 아래·80 위), 걷는 중은 3280 bit7.
# $00~$0D 는 해석기가 명령마다 다시 쓰는 임시 칸이라 여기서 쓴다
def _tile_of(slot_x):
    """A = 그 인물의 FC 칸 X(→ $00 또는 $02), Y. slot_x 가 참이면 X 칸, 아니면 주인공(칸 0)."""
    ix = 0xBD if slot_x else 0xAD
    return lambda base: bytes((ix, base & 0xFF, base >> 8))


def _guard_tiles():
    """$00 = 병사 X 칸, $01 = Y 칸, $02·$03 = 주인공. 셀 y = 2 × 칸 + 1."""
    out = b''
    for src, dst in ((_tile_of(True), 0x00), (_tile_of(False), 0x02)):
        out += src(0x3020) + bytes((0x29, 0x7F, 0x4A, 0x85, dst))
        out += src(0x3080) + bytes((0x29, 0x7F, 0x3A, 0x4A, 0x85, dst + 1))
    return out


def _set_target():
    """$06·$07 FC 칸을 X 인물의 걷는 목표로(명령 13 과 같이 높은 바이트 0, 00:E808)."""
    return bytes((0xA5, 0x06, 0x0A, 0x9D, 0x60, 0x35, 0x9E, 0x80, 0x35,
                  0xA5, 0x07, 0x0A, 0x1A, 0x9D, 0xA0, 0x35, 0x9E, 0xC0, 0x35,
                  0x22, 0x08, 0xE8, 0x00))


RET0 = bytes((0xC2, 0x30, 0xA9, 0x00, 0x00, 0x28, 0x6B))
RET1 = bytes((0xC2, 0x30, 0xA9, 0x01, 0x00, 0x28, 0x6B))


def _next_corner(a):
    """X 병사의 자리로 순찰의 다음 모퉁이 쪽 한 칸을 걷는 목표로. (0A,07)→(0A,0E)→(02,0E)→(02,07) 을 돈다.
    $00~$07 을 씀."""
    (ax, ay), (bx, by), (cx, cy), (dx, dy) = JAIL_LOOP
    a(_guard_tiles())
    a(0xA5, 0x01, 0xC9, ay).br(BNE, 'kb')(0xA5, 0x00, 0xC9, ax).br(BCS, 'kb')(0xA9, ax, 0xA0, ay).br(BRA, 'kgo')
    a.label('kb')(0xA5, 0x00, 0xC9, bx).br(BNE, 'kc')(0xA5, 0x01, 0xC9, by).br(BCS, 'kc')(0xA9, bx, 0xA0, by).br(BRA, 'kgo')
    a.label('kc')(0xA5, 0x01, 0xC9, cy).br(BNE, 'kd')(0xA5, 0x00, 0xC9, cx + 1).br(BCC, 'kd')(0xA9, cx, 0xA0, cy)
    a.br(BRA, 'kgo')
    a.label('kd')(0xA9, dx, 0xA0, dy)
    # 모퉁이 쪽으로 한 칸만: 칸마다 차례 간격을 거쳐 걷는다
    a.label('kgo')(0x85, 0x06, 0x84, 0x07)
    for axis in (0, 1):
        t, s = 0x06 + axis, axis
        a(0xA5, t, 0xC5, s).br(BEQ, f'k{axis}e').br(BCC, f'k{axis}l')(0xA5, s, 0x1A, 0x85, t).br(BRA, f'k{axis}e')
        a.label(f'k{axis}l')(0xA5, s, 0x3A, 0x85, t)
        a.label(f'k{axis}e')
    a(_set_target())
    return a


def _jail_next():
    """명령 37: 순찰 첫 목표(인물 레코드의 목표 칸은 맵마다 정해지지 않음)."""
    return _next_corner(Asm()(0x08, 0xE2, 0x30, 0xA6, 0x90))(0x28, 0x6B).bytes()


def _jail_step(walls_at):
    """명령 37(순찰 고리에서 되풀이): 들켰으면 아무것도 안 함. 모퉁이에 닿았으면 다음 모퉁이를 목표로 하고, 명령 14 처럼
    방향을 정해 걷기를 잇고, 시야를 본다. 시야는 FC 1D:$98BD: 보는 방향의 세 줄(제 줄과 양옆) 한 칸 앞부터 막는 칸까지.
    보이면 SPOTTED 와 SPOTTER. 명령 05 는 네이티브가 0 이 아닌 값을 주면 걷는 중(3280 bit7)을 지워(01:C98F) 쓰지 않는다."""
    w, h, _ = jail_walls()
    row = (w + 7) // 8
    flag = 0x2190 + SPOTTED[0]
    a = Asm()(0x08, 0xE2, 0x30, 0xA6, 0x90, 0xAD, flag & 0xFF, flag >> 8, 0x29, SPOTTED[1]).br(BEQ, 'calm')(0x28, 0x6B)
    # FC 는 창이 떠 있는 동안 맵이 멈춘다(병사도 멈춤, 실측). 창 번호 7E:0A00 이 FF(없음)·02(필드 상태 창)가 아니면 서 있는다
    a.label('calm')(0xAD, 0x00, 0x0A, 0xC9, 0xFF).br(BEQ, 'look')(0xC9, 0x02).br(BEQ, 'look')
    a(0xBD, 0x80, 0x32, 0x29, 0x7F, 0x9D, 0x80, 0x32, 0x28, 0x6B)
    a.label('look')(0xBD, 0x60, 0x35, 0xDD, 0x20, 0x30).br(BNE, 'far')(0xBD, 0xA0, 0x35, 0xDD, 0x80, 0x30).br(BEQ, 'here')
    a.label('far').brl('move')
    # 닿은 칸에서 프레임 수 7E:1ECE 가 PATROL_PERIOD 주기의 앞 8프레임에 들 때만 다음 칸으로: 칸마다 PATROL_PERIOD
    a.label('here')(0xBD, 0x80, 0x32, 0x29, 0x7F, 0x9D, 0x80, 0x32)                  # 명령 14 처럼 닿으면 걷기를 끔
    a(0xAD, 0xCE, 0x1E, 0x29, PATROL_PERIOD - 1, 0xC9, PATROL_WINDOW).br(BCC, 'turn').brl('look2')
    a.label('turn')
    _next_corner(a)
    a(0xA6, 0x90)
    # 명령 14: 목표와 견주어 방향·걷는 중
    a.label('move')(0xBD, 0x60, 0x35, 0xDD, 0x20, 0x30).br(BEQ, 'y')(0xA9, 0x10).br(BCS, 'fx')(0xA9, 0x20)
    a.label('fx')(0x9D, 0xE0, 0x31).br(BRA, 'walk')
    a.label('y')(0xBD, 0xA0, 0x35, 0xDD, 0x80, 0x30).br(BEQ, 'look2')(0xA9, 0x40).br(BCS, 'fy')(0xA9, 0x80)
    a.label('fy')(0x9D, 0xE0, 0x31, 0x9E, 0x40, 0x36)
    a.label('walk')(0xBD, 0x80, 0x32, 0x09, 0x80, 0x9D, 0x80, 0x32)
    a.label('look2')
    # 시야: $04·$05 = 방향 dx·dy, $08 = 줄(FF·00·01), $09·$0A = 줄 어긋남, $06·$07 = 보는 칸, $0B = 남은 걸음
    a(_guard_tiles(), 0x64, 0x04, 0x64, 0x05, 0xBD, 0xE0, 0x31, 0x0A).br(BCC, 'nu')(0xC6, 0x05)
    a.label('nu')(0x0A).br(BCC, 'nd')(0xE6, 0x05)
    a.label('nd')(0x0A).br(BCC, 'nl')(0xC6, 0x04)
    a.label('nl')(0x0A).br(BCC, 'nr')(0xE6, 0x04)
    a.label('nr')(0xA9, 0xFF, 0x85, 0x08)
    a.label('lane')(0x64, 0x09, 0x64, 0x0A, 0xA5, 0x04).br(BNE, 'hz')(0xA5, 0x08, 0x85, 0x09).br(BRA, 'st')
    a.label('hz')(0xA5, 0x08, 0x85, 0x0A)
    a.label('st')(0xA5, 0x00, 0x18, 0x65, 0x09, 0x18, 0x65, 0x04, 0x85, 0x06,
                  0xA5, 0x01, 0x18, 0x65, 0x0A, 0x18, 0x65, 0x05, 0x85, 0x07, 0xA9, 0x20, 0x85, 0x0B)
    a.label('step')(0xA5, 0x06, 0xC9, w).br(BCS, 'next')(0xA5, 0x07, 0xC9, h).br(BCS, 'next')
    a(0xA5, 0x07)
    for _ in range(row - 1):
        a(0x18, 0x65, 0x07)
    a(0x85, 0x0C, 0xA5, 0x06, 0x4A, 0x4A, 0x4A, 0x18, 0x65, 0x0C, 0xAA, 0xBF, *_al(walls_at), 0x85, 0x0C)
    a(0xA5, 0x06, 0x29, 0x07, 0xA8, 0xA9, 0x80).label('m')(0xC0, 0x00).br(BEQ, 'md')(0x4A, 0x88).br(BRA, 'm')
    a.label('md')(0x25, 0x0C).br(BNE, 'next')
    a(0xA5, 0x06, 0xC5, 0x02).br(BNE, 'adv')(0xA5, 0x07, 0xC5, 0x03).br(BEQ, 'seen')
    a.label('adv')(0xA5, 0x06, 0x18, 0x65, 0x04, 0x85, 0x06, 0xA5, 0x07, 0x18, 0x65, 0x05, 0x85, 0x07, 0xC6, 0x0B).br(BNE, 'step')
    a.label('next')(0xA6, 0x90, 0xE6, 0x08, 0xA5, 0x08, 0xC9, 0x02).br(BEQ, 'unseen').brl('lane')
    a.label('unseen')(0x28, 0x6B)
    a.label('seen')(0xAD, flag & 0xFF, flag >> 8, 0x09, SPOTTED[1], 0x8D, flag & 0xFF, flag >> 8,
                    0xA5, 0x90, 0x8D, SPOTTER & 0xFF, SPOTTER >> 8 & 0xFF, 0x28, 0x6B)
    return a.bytes()


def _jail_mine():
    """명령 05: 들킨 병사면 A = 0, 다른 병사는 1(그 자리에서 기다림, FC 는 창이 떠 있는 동안 맵이 멈춤)."""
    return bytes((0x08, 0xE2, 0x30, 0xA5, 0x90, 0xCD, SPOTTER & 0xFF, SPOTTER >> 8 & 0xFF, 0xF0, len(RET1))) + RET1 + RET0


def _jail_near():
    """명령 37: 병사의 줄을 따라 일행과 맞닿는 칸을 목표로(FC: 곧게 걸어 맞닿은 칸에서 멈춤, 돌아서지 않음).
    가로로 보면 Y 는 그대로, X 는 같은 줄이면 주인공 X - dx, 옆 줄이면 주인공 X. 세로도 같다."""
    a = Asm()(0x08, 0xE2, 0x30, 0xA6, 0x90, _guard_tiles(), 0xA5, 0x00, 0x85, 0x06, 0xA5, 0x01, 0x85, 0x07)
    a(0xBD, 0xE0, 0x31, 0x29, 0x30).br(BEQ, 'v')
    a(0xA5, 0x02, 0x85, 0x06, 0xA5, 0x03, 0xC5, 0x01).br(BNE, 'go')
    a(0xBD, 0xE0, 0x31, 0x29, 0x10).br(BEQ, 'hl')(0xC6, 0x06).br(BRA, 'go')
    a.label('hl')(0xE6, 0x06).br(BRA, 'go')
    a.label('v')(0xA5, 0x03, 0x85, 0x07, 0xA5, 0x02, 0xC5, 0x00).br(BNE, 'go')
    a(0xBD, 0xE0, 0x31, 0x29, 0x40).br(BEQ, 'vu')(0xC6, 0x07).br(BRA, 'go')
    a.label('vu')(0xE6, 0x07)
    a.label('go')(_set_target(), 0x28, 0x6B)
    return a.bytes()


def grey(c):
    """BGR555 색의 번쩍임 회색: g = (R + 2G + B) / 4 를 세 채널에. _grey_flash 의 코드와 같은 셈."""
    g = ((c & 31) + 2 * (c >> 5 & 31) + (c >> 10 & 31)) >> 2
    return g | g << 5 | g << 10


def _upload():
    return bytes((0xAD, 0x1A, 0x00, 0x09, 0x02, 0x8D, 0x1A, 0x00))      # LDA $1A / ORA #$02 / STA $1A


def _grey_flash():
    """M8·DB 0 에서. 지금 색을 목표 색 칸에 옮겨 둔 뒤 (R + 2G + B)/4 회색과 원래 색을 번갈아 올린다. 목표 색 칸은
    밝히기(03:A5CE) 동안만 쓰이고 그때는 지금 색과 같아지므로, 지금 색으로 덮어도 다른 연출에 남지 않는다."""
    lo = lambda a: (a & 0xFF, a >> 8 & 0xFF, a >> 16)  # noqa: E731
    copy = bytes((0xC2, 0x30, 0xA2, *lo(CGRAM_NOW)[:2], 0xA0, *lo(CGRAM_KEEP)[:2], 0xA9, 0xFF, 0x01,
                  0x54, 0x7E, 0x7E, 0xF4, 0x00, 0x00, 0xAB, 0xAB, 0xE2, 0x20))           # MVN 지금 → 목표 / DB 0
    back = bytes((0xC2, 0x30, 0xA2, *lo(CGRAM_KEEP)[:2], 0xA0, *lo(CGRAM_NOW)[:2], 0xA9, 0xFF, 0x01,
                  0x54, 0x7E, 0x7E, 0xF4, 0x00, 0x00, 0xAB, 0xAB, 0xE2, 0x20))           # MVN 목표 → 지금 / DB 0
    from dq4chapterbox import wait
    t, u = 0x1EAE, 0x1EB0                                # 여러 루틴이 함께 쓰는 임시 칸(dq5-text-format)
    grey = Asm()(copy, 0xA9, FLASHES).label('f')(0x48, 0xC2, 0x30, 0xA2, 0x00, 0x00).label('c')
    grey(0xBF, *lo(CGRAM_KEEP), 0x48, 0x29, 0x1F, 0x00, 0x8D, *lo(t)[:2])                # LDA keep,X / PHA / R
    grey(0x68, 0x48, 0x4A, 0x4A, 0x4A, 0x4A, 0x4A, 0x29, 0x1F, 0x00, 0x0A, 0x18, 0x6D, *lo(t)[:2],
         0x8D, *lo(t)[:2])                                                               # + 2G
    grey(0x68, 0xEB, 0x4A, 0x4A, 0x29, 0x1F, 0x00, 0x18, 0x6D, *lo(t)[:2], 0x4A, 0x4A,
         0x8D, *lo(t)[:2])                                                               # + B, / 4
    grey(0x0A, 0x0A, 0x0A, 0x0A, 0x0A, 0x0D, *lo(t)[:2], 0x8D, *lo(u)[:2])               # g | g << 5
    grey(0xAD, *lo(t)[:2], 0xEB, 0x0A, 0x0A, 0x0D, *lo(u)[:2], 0x9F, *lo(CGRAM_NOW))     # | g << 10 → 지금 색
    grey(0xE8, 0xE8, 0xE0, 0x00, 0x02).br(BNE, 'c')(0xE2, 0x20)
    grey(_upload(), wait(FLASH_FRAMES), back, _upload(), wait(FLASH_FRAMES))
    grey(0x68, 0x3A).br(BEQ, 'done').brl('f').label('done')                              # PLA / DEC A
    return grey.bytes()


def _fox_dark():
    """FC 084C 뒤: 회색 번쩍임 여섯 번, 페이드 아웃, 검은 화면(실측)."""
    from dq4chapterbox import wait
    fade = b''.join(bytes((0xA9, v, 0x8D, 0x1D, 0x00)) + wait(1) for v in FADE_LEVELS)   # LDA #v / STA $1D
    return _grey_flash() + fade + wait(DARK_FRAMES)


# A 없이 닫히는 창(FC 실측, 창이 열린 프레임부터): 유모 03B0 223·03B1 204, 여우 마을 개 02F1 195. 명령 30 은 글을 다
# 찍은 뒤 돌아와 찍는 동안만큼 길어지고, 유모가 닿은 뒤 조작이 돌아오기까지 535프레임(FC 524)이었다
NANNY_SHUT = {'nanny_stop': 223, 'nanny_out': 204}
SHUT = {**NANNY_SHUT, 'woof_run': 195, 'jail_who': 195, 'jail_out': 237}


# BRK 처리기는 BRK 가 놓인 뱅크를 DB 로 두어 이 모듈의 뱅크(40 이상)에서는 창 번호를 롬에 쓴다(dq4ch3slots). 그래서
# BRK 는 낮은 뱅크 받침(BRK … / RTL)으로 부른다
LOW_BRKS = {'close_all': (0x95, 0xFF)}


def low_stubs():
    """(바이트, {이름: 주소})."""
    from dq4ch3slots import BONMALMO_STUBS
    out, where = bytearray(), {}
    for name, args in LOW_BRKS.items():
        where[name] = BONMALMO_STUBS[0] + len(out)
        out += bytes((0x00, *args, 0x6B))
    if BONMALMO_STUBS[0] + len(out) > BONMALMO_STUBS[1]:
        raise SystemExit(f'본몰 BRK 받침 {len(out)}바이트가 예약을 넘음')
    return bytes(out), where


def _shut(frames):
    """창을 연 채 frames 프레임 기다린 뒤 모두 닫는다."""
    from dq4chapterbox import wait
    return ENTER + wait(frames) + bytes((0x22,)) + _al(low_stubs()[1]['close_all']) + LEAVE


def _next_day():
    """아침으로 두고 날이 바뀜(공용 next_day, FC 15:$9F79). FC 는 묵어도 HP 를 채우지 않는다(실측)."""
    return _morning() + bytes((0x22,)) + _al(ch3.native()[1]['next_day'])


def _room():
    """대화 호출: 걷는 일행 가운데 빈 물건 칸(FF)이 있으면 RESULT 를 켠다(FC 는 가득이면 편지를 받지 못함, 036A).
    맡긴 물건은 보지 않는다."""
    flag = 0x7E2190 + ch3.RESULT[0]
    # DB 7E: 물건 칸(7E:2056~)은 뱅크 00 의 WRAM 거울(0000~1FFF) 밖이다
    a = Asm()(ENTER, 0xA9, 0x7E, 0x48, 0xAB, 0xE2, 0x30, lda(flag), 0x29, ~ch3.RESULT[1] & 0xFF, sta(flag))
    a(0xC2, 0x10, 0xA2, *(ch3.PARTY_ITEMS & 0xFFFF).to_bytes(2, 'little'), 0xA0, 0x00, 0x00)
    a.label('rec')(0x5A, 0xA0, ch3.ITEM_SLOTS, 0x00)
    a.label('slot')(0xBD, 0x00, 0x00, 0xC9, 0xFF).br(BEQ, 'free')(0xE8, 0x88).br(BNE, 'slot')
    a(0xC2, 0x20, 0x8A, 0x18, 0x69, ch3.RECORD - ch3.ITEM_SLOTS, 0x00, 0xAA, 0xE2, 0x20, 0x7A, 0xC8)
    a(0x98, 0xCF, *_al(0x7E201E)).br(BCC, 'rec').brl('end')
    a.label('free')(0x7A, lda(flag), 0x09, ch3.RESULT[1], sta(flag))
    a.label('end')
    return a.bytes() + LEAVE


def native(ctx):
    import dq4prologue
    from dq4ch2endor import _fanfare
    out = bytearray()
    at = {}

    def put(name, b):
        at[name] = ctx.code_at + len(out)
        out.extend(b)
    # 촌장 둘 다 FC 처럼 아침(FC $62ED = 28)·날수 + 1 로 숲 (04,0C) 에 옮긴다. 개가 있으면 여우 장면 flag 를 켠다
    put('rest', ENTER + _next_day() + LEAVE)
    put('fox_scene', ENTER + _fox_dark() + _set(FOX_SCENE) + _next_day() + LEAVE)
    put('room', _room())
    put('fox_event', bytes((0xA0, *_al(at['fox_scene']))) + _warp(FOREST, FOREST_WAKE) + b'\xff')
    put('inn_event', bytes((0xA0, *_al(at['rest']))) + _warp(FOREST, FOREST_WAKE) + b'\xff')
    put('fox_go', dq4prologue._event_start(at['fox_event']))
    put('jail_event', _warp(JAIL_OUT[0], cell(*JAIL_OUT[1]), facing=3) + b'\xff')
    put('jail_go', dq4prologue._event_start(at['jail_event']))
    put('jail_walls', JAIL_WALLS)
    put('jail_next', _jail_next())
    put('jail_step', _jail_step(at['jail_walls']))
    put('jail_mine', _jail_mine())
    put('jail_near', _jail_near())
    for key, frames in SHUT.items():
        put(f'shut_{key}', _shut(frames))
    put('inn', dq4prologue._event_start(at['inn_event']))
    put('jingle', ENTER + _fanfare(ITEM_SONG) + LEAVE)
    put('bridge_hook', _bridge_hook(SEA_FRAMES, BRIDGE_CELLS))
    put('enter_hook', _enter_hook())
    put('fade_in_hook', _fade_in_hook())
    put('refresh', ENTER + dq4ch1event.REFRESH + LEAVE)
    put('dog_trigger', dq4prologue._inside(*DOG_TRIGGER))
    return bytes(out), at


def _entrance_hook_at():
    import dq4groupbuild
    return dq4groupbuild.ENTRANCE_HOOK_AT       # 그 루틴의 첫 이름표 enter(dq4entrancehook.code)


def _enter_hook():
    """2A:F28D 의 JML 이 오는 곳(어떤 M·X 폭이든). FOXED 이고 그룹 48 의 여우 마을 입구 블록에서 들면 $BD·$C1·$C2·$C3·
    $198E 를 숲 어귀로 두고 원래 두 명령 뒤 2A:F291 로, 아니면 입구별 도착 훅으로."""
    x, y = FOREST_ENTRY
    g, n = (int(v, 16) for v in FOREST.split('/'))
    a = Asm()(0x08, 0xE2, 0x20, lda(0x7E2190 + FOXED[0]), 0x29, FOXED[1]).br(BEQ, 'off')
    a(0xA5, 0xBC, 0xC9, g).br(BNE, 'off')
    a(0xC2, 0x20, 0xA5, 0xB6, 0x29, 0xFE, 0xFF, 0xC9, *FOX_GATE[0].to_bytes(2, 'little')).br(BNE, 'off8')
    a(0xA5, 0xB8, 0x29, 0xFE, 0xFF, 0xC9, *FOX_GATE[1].to_bytes(2, 'little')).br(BNE, 'off8')
    a(0xE2, 0x20, 0xA9, n, 0x85, 0xBD, 0xA9, x, 0x85, 0xC1, 0xA9, y, 0x85, 0xC2, 0xA9, 0x01, 0x85, 0xC3)
    a(0xA9, 0x00, sta(0x7E198E), 0x28, 0xA5, 0xBC, 0xC9, 0x16, 0x5C, *_al(ENTER_BACK))
    a.label('off8')(0xE2, 0x20).label('off')(0x28, 0x5C, *_al(_entrance_hook_at()))
    return a.bytes()


def hooks(ctx):
    """필드를 불러올 때 FIELD_CALL 을 다리 훅으로(훅이 원래 대상을 먼저 부름), 입구별 도착 훅 앞에 여우 마을 갈래,
    낮은 뱅크 BRK 받침."""
    from dq4ch3slots import BONMALMO_STUBS
    stubs, _ = low_stubs()
    return [(FIELD_CALL, bytes((0x22,)) + _al(SEA_FRAMES), bytes((0x22,)) + _al(ctx.at['bridge_hook'])),
            (ENTER_SITE, bytes((0x5C,)) + _al(_entrance_hook_at()), bytes((0x5C,)) + _al(ctx.at['enter_hook'])),
            (BONMALMO_STUBS[0], bytes(len(stubs)), stubs),
            (FADE_IN_SITE, FADE_IN_ORIG, bytes((0x5C,)) + _al(ctx.at['fade_in_hook']))]


# ---- 대화 ----

YES = {"code": "05"}
DAY = {"code": "14"}


def _ask(ctx, yes, again, depth=ASK_DEPTH):
    """예·아니요: 「예」 면 yes, 「아니요」 면 again 메시지 뒤 다시 묻기를 depth 번(FC 는 「예」 까지 되풀이)."""
    out = ctx.when(YES, yes, [ctx.say(again)])
    for _ in range(depth - 1):
        out = ctx.when(YES, yes, [ctx.say(again), out])
    return out


def talk_scripts(ctx):
    say_, call, flag, on, when, has = ctx.say, ctx.call, ctx.flag, ctx.flag_on, ctx.when, ctx.has
    letter = [call('room'), when(ctx.paid(), [call('give_prince_letter'), say_('got_prince_letter'), call('jingle'),
                                              say_('prince_ask')], [say_('prince_full')])]
    prince = [when(flag(LETTER2), [say_('prince_after')],
                   [when(flag(LETTER1), [say_('prince_wait')],
                         [when(has(PRINCE_LETTER), [say_('prince_wait')],
                               [when(DAY, [when(flag(PRINCE_MET), [say_('prince_tip')],
                                                [say_('prince_hello'), on(PRINCE_MET), on(NANNY_SCOLDED), on(NANNY_GO)])],
                                     [say_('prince_night'), *letter])])])])]
    king = [when(flag(LETTER2), [say_('king_after')],
                 [when(has(KING_LETTER), [call('take_king_letter'), say_('king_letter'), on(LETTER2)],
                       [when(flag(FOXED), [say_('king_bridge'), on(BRIDGE)], [say_('king_wait')])])])]
    son = [say_('son_ask'),
           when(has(WINGS), [say_('son_wings'),
                             _ask(ctx, [call('take_wings'), say_('son_thanks'), on(SON_FREED)], 'son_please')])]
    chief = [when(flag(ch3.DOG), [say_('chief_dog'), call('fox_go')],
                  [say_('chief_welcome'),
                   when(YES, [say_('chief_stay'), when(YES, [say_('chief_rest'), call('inn')], [say_('chief_bye')])],
                        [say_('chief_bye')])])]
    # 여우는 장면 동안(FOX_SCENE)만 서 있다. 되묻기 깊이를 다 써도 대답을 마치면(ANSWERED) 여우 스크립트가 다시 말을 건다
    fox = [say_('fox_beg'),
           _ask(ctx, [say_('fox_gift'), call('give_armor'), say_('got_armor'), call('jingle'), say_('fox_bye'),
                      on(FOX_LET)], 'fox_please'),
           on(ANSWERED)]
    letter = [say_('monica_letter'), say_('endor_king_letter'), call('take_prince_letter'), call('give_king_letter'),
              say_('got_king_letter'), call('jingle'), say_('endor_king_ask'), on(LETTER1)]
    # 3장 엔돌 목록(dq4ch3endor)의 모니카만 이 대화를 쓴다(monica_talk)
    monica = [when(flag(LETTER2), [say_('monica_thanks')],
                   [when(flag(LETTER1), [say_('monica_trust')],
                         [when(has(PRINCE_LETTER), letter, [say_('monica_hello')])])])]
    bodies = {'prince': prince, 'king': king, 'son': son, 'chief': chief, 'fox': fox, 'monica': monica,
              'dog': [say_('woof')]}
    return [bodies[name] for name in TALKS]


# ---- 인물 스크립트 ----

def _cmd(op, *args, **kw):
    return {"op": op, "args": list(args), **kw}


def _wait_on(flag):
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
    # 창을 연 채 띄우고(30) 정한 프레임 뒤 닫음(A 를 기다리지 않음)
    timed = lambda k: [_cmd('30', *(ctx.msg[k].to_bytes(2, 'little') if ctx.msg else (0, 0))),  # noqa: E731
                       call(at[f'shut_{k}'])]
    gone = [_cmd('28', label='gone'), _cmd('52'), _cmd('16')]
    walk = lambda cells: [c for at in cells for c in (_cmd('13', *at), _cmd('14'))]  # noqa: E731
    # 여우: 장면(FOX_SCENE)이 아니면 숨는다. 장면이면 조작을 막고 「예」 까지 빈 뒤 위로 걸어가 사라지고 FOXED
    fox = [_if_on(FOXED, 'gone'), _if_off(FOX_SCENE, 'gone'), _if_on(FOX_LET, 'gone'), _cmd('3F'),
           _and_off(ANSWERED, label='ask'), call(talk_here), _wait_on(ANSWERED), _if_off(FOX_LET, 'ask'),
           _cmd('1C'), *walk(FOX_LEAVE), _or(FOXED), _or(FOX_GONE), _cmd('52'), _cmd('16'), *gone]
    # 돈 가아데(FC 는 맵 오른쪽 밖에 둔 인물): 여우가 사라지면 (07,0D) 에 나타나 주인공 아래로 걸어와 03B2 뒤 떠난다
    gaade = [_if_on(FOXED, 'gone'), _wait_on(FOX_GONE), _cmd('2B', *GAADE_IN), _cmd('1C'), *walk([GAADE_TALK]),
             msg('gaade'), *walk([GAADE_OUT]), _and_off(FOX_SCENE, FOX_LET, FOX_GONE), _cmd('52'), _cmd('40'),
             _cmd('16'), *gone]
    # 감옥의 톰 아들: 날개를 받으면 깜박이며 사라진다(FC 는 그림이 위로 떠오른 뒤 빠짐, 1C 이벤트 06)
    son = [_if_on(SON_FREED, 'gone'), _wait_on(SON_FREED), _cmd('51'), _cmd('4F'), _cmd('52'), _cmd('16'), *gone]
    # 유모(FC 15:$A509 가 깨우는 슬롯 07 블록): 왕자가 처음 말을 마치면 조작을 막고 걸어와 03B0, 한 걸음 더 와서 03B1 뒤
    # 그 자리에 남는다(맵을 다시 부르면 제자리)
    nanny = [_wait_on(NANNY_GO), _cmd('3F'), _cmd('1C'), *walk(NANNY_PATH[:-1]), _cmd('2F', FACE_DOWN),
             *walk(NANNY_PATH[-1:]), *timed('nanny_stop'), *timed('nanny_out'), _cmd('40'), _cmd('16')]
    # 마을의 개: 개가 따라오면 주인공이 (14,13)에 설 때 짖고 촌장 옆으로 달려간다(주인공 칸도 지나감). 따라 걷는 개를
    # 숨기는 것은 개 따라 걷기 장치 몫
    village_dog = [_cmd('28'), _cmd('52'), _cmd('1E', DOG_SPEED), _if_off(ch3.DOG, 'stay'), _if_on(FOXED, 'stay'),
                   poll(at['dog_trigger']), _cmd('3F'),
                   *timed('woof_run'), _or(DOG_AWAY), call(at['refresh']), _cmd('50', *DOG_FROM), _cmd('53'), _cmd('4F'), _cmd('1C'), *walk(DOG_RUN), _cmd('51'),
                   _cmd('4F'), _cmd('52'), _cmd('50', *DOG_STAND), _cmd('53'), _cmd('4F'), _cmd('40'), _cmd('16', label='stay')]
    # 감옥 병사: 모퉁이를 하나씩 목표로 걸으며 차례마다 시야를 보다가 들키면 들킨 병사만 다가와 내보낸다
    guard = [_cmd('1E', PATROL_SPEED), call(at['jail_next']), call(at['jail_step'], label='patrol'),
             _if_on(SPOTTED, 'seen'), _cmd('03', target='patrol'),
             _cmd('15', label='seen'), poll(at['jail_mine']), _cmd('3F'), *timed('jail_who'), call(at['jail_near']),
             _cmd('1E', APPROACH_SPEED), _cmd('1C'), _cmd('14'), *timed('jail_out'), call(at['jail_go']), _cmd('16')]
    bodies = {'guard': guard, 'nanny': nanny, 'village_dog': village_dog, 'village_dog_night': list(village_dog), 'fox': fox, 'gaade': gaade, 'son': son}
    return [{"address": SCRIPTS[name][2], "commands": bodies[name]} for name in SCRIPTS]


def _src(name):
    lst, idx, _ = SCRIPTS[name]
    return {"list": lst, "index": idx}


def _person(name, time, at, facing, talk, gfx):
    # 이동 간격 0 이면 인물 스크립트가 차례를 받지 못한다. 1 이면 명령마다 8프레임
    return {"from": _src(name), "time": time,
            "fields": {"x": at[0], "y": at[1], "facing": facing, "talk": talk, "gfx": gfx, "layer": 0, "interval": 1}}


def _at(e):
    return (e["fields"]["x"], e["fields"]["y"])


def _scripted(e, name, talk=None):
    f = {**e["fields"], "interval": 1}
    if talk is not None:
        f["talk"] = talk
    return {**e, "from": _src(name), "fields": f}


def _replace(entries, time, at, make):
    hit = 0
    for k, e in enumerate(entries):
        if e["time"] == time and _at(e) == at:
            entries[k] = make(e)
            hit += 1
    if hit != 1:
        raise SystemExit(f'{time} {at}: 바꿀 인물이 {hit}명')


def npc_lists(lists, ctx):
    """옮긴 목록을 고친다(인물 스크립트가 flag 를 보고 숨거나 나타난다). 엔돌 모니카는 여기서 바꾸지 않는다: 기본
    40/06 은 2장 동안에도 쓰이고 2장 동료 대화가 그 대화 번호로 사람을 찾는다. 3장 엔돌 목록을 베끼는 엔돌 모듈이
    monica_talk() 로 바꾼다."""
    t = ctx.talk
    if CASTLE not in lists:
        return [], []           # 인물 없이 옮긴 목록(dq4npcport.port 의 with_people=False)
    for time, c in PRINCE.items():
        ctx.retalk(lists, CASTLE, c, t['prince'], time=time)
    _replace(lists[CASTLE]["entries"], 'day', NANNY, lambda e: _scripted(e, 'nanny'))
    ctx.retalk(lists, CASTLE, KING, t['king'])
    ctx.retalk(lists, FOX_TOWN, CHIEF, t['chief'])
    _replace(lists[PRISON]["entries"], 'day', SON, lambda e: _scripted(e, 'son', t['son']))
    for g in GUARDS:
        _replace(lists[PRISON]["entries"], 'day', cell(*g), lambda e: _scripted(e, 'guard'))
    forest = lists[FOREST]["entries"]
    _replace(forest, 'day', FOX, lambda e: _scripted(e, 'fox', t['fox']))
    _replace(forest, 'day', GAADE, lambda e: _scripted(e, 'gaade'))
    town = lists[FOX_TOWN]["entries"]
    before = len(town)
    gfx = next((e["fields"]["gfx"] for e in lists.get(KENNEL_DOG[0], {"entries": []})["entries"]
                if _at(e) == KENNEL_DOG[1]), None)
    for k, e in enumerate(town):
        if _at(e) == CORNER_DOG:
            e = _scripted(e, 'village_dog' if e["time"] == 'day' else 'village_dog_night', t['dog'])
            if gfx is not None:
                e["fields"]["gfx"] = gfx
            town[k] = e
    if sum(_at(e) == CORNER_DOG for e in town) != 2 or before != len(town):
        raise SystemExit(f'{FOX_TOWN} {CORNER_DOG}: 마을의 개(낮·밤)가 둘이 아님')
    castle = lists[CASTLE]["entries"]
    n = len(castle)
    castle[:] = [e for e in castle if not (e["time"] == 'day' and _at(e) == SECOND_NANNY)]
    if n - len(castle) != 1:
        raise SystemExit(f'{CASTLE} {SECOND_NANNY}: 뺄 둘째 유모가 {n - len(castle)}명')
    return [], []


def monica_talk(first_talk=None):
    """3장 엔돌 왕좌의 방 모니카(셀 MONICA, 낮)에게 줄 대화 번호. first_talk 는 3장 첫 대화 번호(없으면 기본)."""
    return next(c for c in ch3.contexts(first_talk=first_talk) if c.key == 'B').talk['monica']


def absent(ctx=None):
    """{(맵, DQ5 셀 x, y, 밤)}: 처음 상태 목록에서 뺀 둘째 유모와 숨어 있는 마을의 개·여우."""
    return ({(FOX_TOWN, *CORNER_DOG, night) for night in (False, True)} | {(FOREST, *FOX, False)} |
            {(CASTLE, *SECOND_NANNY, False)})


FC_PRINCE, FC_KING, FC_SON, FC_CHIEF, FC_MONICA = 0x061, 0x06B, 0x065, 0x05E, 0x03A


def start_messages(ctx):
    """3장 처음 상태(개 없음, 편지 없음)에서 이 모듈이 대화를 바꾼 인물의 첫 메시지."""
    m = ctx.msg
    return {(CASTLE, FC_PRINCE, False): m['prince_hello'], (CASTLE, FC_PRINCE, True): m['prince_night'],
            (CASTLE, FC_KING, None): m['king_wait'], (PRISON, FC_SON, None): m['son_ask'],
            (FOX_TOWN, FC_CHIEF, None): m['chief_welcome'], (ENDOR_THRONE, FC_MONICA, False): m['monica_hello']}
