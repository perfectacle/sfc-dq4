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
from dq4chapterbox import ENTER, LEAVE  # noqa: E402
from dq4ch2endor import Asm, BCC, BEQ, BNE, lda, sta  # noqa: E402
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
FACE_LEFT = 0x20               # 인물 명령 2F(7E:31E0 위 니블, dq4ch2frenol.FACE_LEFT)
HELPER_CELL = (0, 1)           # 보이지 않는 도우미 인물: 맵 왼쪽 위 구석
# FC 18/00 (00,00) 의 개(대화 2C4, 개가 따라올 때 촌장 장면에서 움직이는 인물). 이 롬은 그 연출 없이 빼 둔다
CORNER_DOG = cell(0x00, 0x00)

# 빌릴 인물 스크립트(dq4ch3slots B: 10:BEE5 칸 2·4~9). 칸마다 한 시간대에만 놓인다
LIST = '10:BEE5'
SCRIPTS = {'fox': (LIST, 2, '10:BEFA'), 'gaade': (LIST, 4, '10:BF14'), 'son': (LIST, 5, '10:BF27'),
           'arrive': (LIST, 6, '10:BF45'), 'arrive_night': (LIST, 7, '10:BF63')}

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
MESSAGES = {
    # 왕자 릭(FC 05/01, 대화 061)
    'prince_hello': pages('릭', '저는 릭./이 나라의 왕자예요.', '당신을 여행하는/상인이라 보고/부탁하고 싶은 게/있는데요…….',  # 0837·0838
                          '자세한 이야기는/밤에 무기점/뒤에서…….'),
    'prince_tip': pages('릭', '자세한 이야기는/밤에 무기점/뒤에서…….'),                                               # 0838
    'nanny_stop': say('왕자님!/그런 천한 자와/이야기하시면/안 됩니다!'),                                              # 03B0
    'nanny_out': say('자! 나가세요!'),                                                                                 # 03B1
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
}
TALKS = ('prince', 'king', 'son', 'chief', 'fox', 'monica')
CALLS = {'give_prince_letter': ('give', PRINCE_LETTER), 'take_prince_letter': ('take', PRINCE_LETTER),
         'give_king_letter': ('give', KING_LETTER), 'take_king_letter': ('take', KING_LETTER),
         'take_wings': ('take', WINGS), 'give_armor': ('give', STEEL_ARMOR),
         'room': ('room', 0), 'fox_go': ('fox_go', 0), 'inn': ('inn', 0), 'jingle': ('jingle', 0)}
ITEM_SONG = 0x2F               # 물건을 받는 징글(dq4ch2frenol.ITEM_SONG, 끝을 기다리는 곡)
# 네이티브 가운데 코드가 아닌 이벤트 스크립트(dq4brkscan)
DATA_ENTRIES = ('fox_event', 'inn_event', 'arrive_event')
# PHP 없이 JSL 로 시작하는 훅(원래 대상을 먼저 부름)
CODE_ENTRIES = ('bridge_hook',)


# ---- 네이티브 ----

def _set(flag):
    a = 0x7E2190 + flag[0]
    return bytes((0xAF,)) + _al(a) + bytes((0x09, flag[1], 0x8F)) + _al(a)


def _warp(mp, at):
    g, n = (int(v, 16) for v in mp.split('/'))
    return bytes((0x90, g, n, *at, 0x01, 0x80))


def _morning():
    return bytes((0xC2, 0x20, 0xA9, *ch2.MORNING.to_bytes(2, 'little'))) + sta(ch2.TIME_AT) + bytes((0xE2, 0x20))


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
    put('fox_scene', ENTER + _set(FOX_SCENE) + _next_day() + LEAVE)
    put('room', _room())
    put('fox_event', bytes((0xA0, *_al(at['fox_scene']))) + _warp(FOREST, FOREST_WAKE) + b'\xff')
    put('inn_event', bytes((0xA0, *_al(at['rest']))) + _warp(FOREST, FOREST_WAKE) + b'\xff')
    put('arrive_event', _warp(FOREST, FOREST_ENTRY) + b'\xff')
    put('fox_go', dq4prologue._event_start(at['fox_event']))
    put('inn', dq4prologue._event_start(at['inn_event']))
    put('arrive', dq4prologue._event_start(at['arrive_event']))
    put('jingle', ENTER + _fanfare(ITEM_SONG) + LEAVE)
    put('bridge_hook', _bridge_hook(SEA_FRAMES, BRIDGE_CELLS))
    return bytes(out), at


def hooks(ctx):
    """필드를 불러올 때 FIELD_CALL 을 다리 훅으로(훅이 원래 대상을 먼저 부름)."""
    return [(FIELD_CALL, bytes((0x22,)) + _al(SEA_FRAMES), bytes((0x22,)) + _al(ctx.at['bridge_hook']))]


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
                                                [say_('prince_hello'), say_('nanny_stop'), say_('nanny_out'),
                                                 on(PRINCE_MET), on(NANNY_SCOLDED)])],
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
    bodies = {'prince': prince, 'king': king, 'son': son, 'chief': chief, 'fox': fox, 'monica': monica}
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
    msg = lambda k: _cmd('21', *(ctx.msg[k].to_bytes(2, 'little') if ctx.msg else (0, 0)))  # noqa: E731
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
    # 여우를 쫓은 뒤에는 마을이 없다: 여우 마을에 들면(필드·ルーラ 모두 도착 칸) 곧바로 숲 어귀로
    arrive = [_if_off(FOXED, 'end'), _cmd('3F'), call(at['arrive']), _cmd('16', label='end')]
    bodies = {'fox': fox, 'gaade': gaade, 'son': son, 'arrive': arrive, 'arrive_night': list(arrive)}
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
    ctx.retalk(lists, CASTLE, KING, t['king'])
    ctx.retalk(lists, FOX_TOWN, CHIEF, t['chief'])
    _replace(lists[PRISON]["entries"], 'day', SON, lambda e: _scripted(e, 'son', t['son']))
    forest = lists[FOREST]["entries"]
    _replace(forest, 'day', FOX, lambda e: _scripted(e, 'fox', t['fox']))
    _replace(forest, 'day', GAADE, lambda e: _scripted(e, 'gaade'))
    town = lists[FOX_TOWN]["entries"]
    before = len(town)
    town[:] = [e for e in town if _at(e) != CORNER_DOG]
    if before - len(town) != 2:
        raise SystemExit(f'{FOX_TOWN} {CORNER_DOG}: 뺄 개(낮·밤)가 {before - len(town)}명')
    town[:0] = [_person('arrive', 'day', HELPER_CELL, 'down', t['chief'], 0),
                _person('arrive_night', 'night', HELPER_CELL, 'down', t['chief'], 0)]
    return [], []


def monica_talk(first_talk=None):
    """3장 엔돌 왕좌의 방 모니카(셀 MONICA, 낮)에게 줄 대화 번호. first_talk 는 3장 첫 대화 번호(없으면 기본)."""
    return next(c for c in ch3.contexts(first_talk=first_talk) if c.key == 'B').talk['monica']


def absent(ctx=None):
    """{(맵, DQ5 셀 x, y, 밤)}: 처음 상태 목록에서 뺀 인물과 장면 밖에서 숨는 여우."""
    return {(FOX_TOWN, *CORNER_DOG, night) for night in (False, True)} | {(FOREST, *FOX, False)}


FC_PRINCE, FC_KING, FC_SON, FC_CHIEF, FC_MONICA = 0x061, 0x06B, 0x065, 0x05E, 0x03A


def start_messages(ctx):
    """3장 처음 상태(개 없음, 편지 없음)에서 이 모듈이 대화를 바꾼 인물의 첫 메시지."""
    m = ctx.msg
    return {(CASTLE, FC_PRINCE, False): m['prince_hello'], (CASTLE, FC_PRINCE, True): m['prince_night'],
            (CASTLE, FC_KING, None): m['king_wait'], (PRISON, FC_SON, None): m['son_ask'],
            (FOX_TOWN, FC_CHIEF, None): m['chief_welcome'], (ENDOR_THRONE, FC_MONICA, False): m['monica_hello']}
