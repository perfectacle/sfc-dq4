"""DQ4 2장 프레놀 가짜 공주 사건과 남쪽 동굴의 황금의 팔찌(FC 0F/00·0F/01, $627B bit4~6).

FC 차례:
  1. 여관 2층(3D/05, FC 0F/01)의 방에 다가가면 검은 망토 둘이 가짜 공주를 붙잡고 「멈춰라!」(02FE) 뒤 계단으로 사라진다
     (FC 레코드 02·05·06 의 블록, 1D 이벤트 0E). KIDNAPPED.
  2. 마을(3D/04, FC 0F/00)로 내려오면 셋이 서쪽 길로 마을을 빠져나간다(레코드 02~04, 같은 블록). LEFT.
     마을 사람의 말이 납치 뒤로 바뀌고, 아이가 강아지가 물어 온 편지(07D6)를 읽어 준다.
  3. 남쪽 동굴(45/0C)의 상자에서 황금의 팔찌(dq4ch2slots 밖: 상자 비트 2228&20, 물건 C6)를 얻는다.
  4. 밤에 팔찌를 가지고 묘지 (03,0B)에 서면 검은 망토가 팔찌를 요구하고(1D 이벤트 3C, 예·아니요), 넘기면 공주가
     무희 메이였다고 밝히고 도적의 열쇠를 준다(1B). 마중 온 둘과 마을을 떠나고 날이 밝는다(3E). RESCUED.

FC 는 밤 인물 셋을 「밤이고 팔찌를 가졌을 때」만 둔다(1C:$A058). 대체 목록은 flag 로만 고르므로, 그 인물들은 목록에
늘 두고 스크립트 첫머리의 gate 가 팔찌가 없으면 스스로 치운다. 형식은 sfc/dq4/docs/dq4-chapter2-format.md
「프레놀 가짜 공주」·「남쪽 동굴」.
"""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4chapter1 as ch1  # noqa: E402
from dq4chapterbox import ENTER, LEAVE  # noqa: E402
import dq4ch2event as ch2  # noqa: E402

say, narrate, speak = ch1.say, ch1.narrate, ch1.speak

# 7E:21F1 (dq4ch2slots E2). 앞 셋은 남는 flag, 뒤 다섯은 묘지 장면 동안만 쓰고 끝에 끈다
IDX = 0x61
KIDNAPPED = (IDX, 0x01)        # 여관 2층에서 공주가 납치됨(FC $627B&10)
LEFT = (IDX, 0x02)             # 납치범이 마을을 빠져나감(FC $627B&20)
RESCUED = (IDX, 0x04)          # 팔찌를 넘기고 도적의 열쇠를 받음(FC $627B&40). 다음 사건이 볼 flag
GIVEN = (IDX, 0x08)            # 묘지에서 팔찌를 넘김(예)
CALLED = (IDX, 0x10)           # 메이가 정체를 밝힘: 마중 온 둘이 나타난다
BYE = (IDX, 0x20)              # 메이가 작별함: 셋이 떠난다
NOBR = (IDX, 0x40)             # gate 가 본 팔찌 없음
ARRIVED = (IDX, 0x80)          # 마중 온 가짜 크리프트가 섰다
FLAGS = (KIDNAPPED, LEFT, RESCUED, GIVEN, CALLED, BYE, NOBR, ARRIVED)
SCENE_BITS = GIVEN[1] | CALLED[1] | BYE[1] | NOBR[1] | ARRIVED[1]

BRACELET, THIEF_KEY = 0xC6, 0xB7          # DQ5 자리(형식 문서 「사건 물건과 도적의 열쇠 문」)
TOWN, INN = '3D/04', '3D/05'              # FC 0F/00·0F/01
CAVE = '45/0C'                            # FC 39/00 남쪽 동굴 1층
CHEST_CELL = (21, 69)                     # FC (10,34) 황금의 팔찌 상자(그룹 45 상자)
CHEST_OPEN = (0x2228, 0x20)               # 그 상자의 열림 비트


def cell(x, y):
    """FC 칸 → 옮긴 인물 셀(dq4npcport.cell)."""
    return (2 * x, 2 * y + 1)


# 그림(dq4people.EVENT_PICTURES·「2장 사건 인물 그림 표」)
CLOAK_PIC, PRINCESS_PIC, BREY_PIC, KIRYL_PIC = 0x16, 0x0E, 0x09, 0x02

# 여관 2층(FC 0F/01 기본 목록). 사건 인물은 블록이 숨기기 전까지 그 자리에 서 있다
INN_DUMMY = cell(0x10, 0x17)       # 레코드 00: 1D 이벤트 0F 만 돌리는 자리 인물(FC 는 대화 008). 옮기면 걸어 다녀 뺀다
INN_CLOAK_A = cell(0x1C, 0x02)     # 레코드 02(검은 망토, 블록이 1D 이벤트 0E·02FE·$627B|=10)
INN_CLOAK_B = cell(0x1D, 0x01)     # 레코드 05(검은 망토)
INN_PRINCESS = cell(0x1D, 0x02)    # 레코드 06(가짜 공주)
INN_BREY = cell(0x1C, 0x06)        # 레코드 03(가짜 브라이, 대화 284)
INN_KIRYL = cell(0x1E, 0x05)       # 레코드 04(쓰러진 가짜 크리프트, 대화 285)
INN_HOBBIT = cell(0x04, 0x05)      # 레코드 01(호빗 아저씨, 대화 283)
FC_INN_BREY, FC_INN_KIRYL = 0x284, 0x285
STAIRS = (cell(0x18, 0x02), cell(0x18, 0x01))   # 셋이 빠져나가는 계단 (18,01)과 그 앞
# 주인공 셀은 FC 칸 (x, y)에서 (2x 또는 2x+1, 2y+1 또는 2y+2)다(dq4ch1event._voice). FC 는 일행이 X 1C 줄에서 Y 07 이면
# 비명(1D 이벤트 0F), Y 05 면 「멈춰라!」(0E). 방은 X 1B~ 이라 그 줄들을 사각형으로 본다
CRY_RECT = (0x1B * 2, 0, 0x26 * 2 + 1, 0x07 * 2 + 2)
STOP_RECT = (0x1B * 2, 0, 0x26 * 2 + 1, 0x05 * 2 + 2)

# 마을(FC 0F/00). 낮 레코드 02~04(겉모습 0A·0B·11)는 납치범과 공주이고, 납치 뒤에만 나와 서쪽으로 나간다
TRIO = (cell(0x0B, 0x10), cell(0x0B, 0x0F), cell(0x0B, 0x0E))
TRIO_PICS = (CLOAK_PIC, PRINCESS_PIC, CLOAK_PIC)
TRIO_PATH = (cell(0x0A, 0x10), cell(0x0A, 0x11), cell(0x08, 0x11), cell(0x08, 0x12), cell(0x00, 0x12))
GIRL_WALKER = cell(0x17, 0x01)     # 레코드 01: 처음 상태에서 마을 어귀에 선 여자(납치 뒤에는 FC 가 치움)
GIRL_INN = cell(0x14, 0x0D)        # 레코드 05: 납치 뒤의 같은 여자(처음에는 FC 가 치움)
DOG = cell(0x1C, 0x13)             # 레코드 06: 코로(처음에는 없어진 강아지)
BOY, MAN, INNKEEPER, MERCHANT, AUNT = (cell(0x1B, 0x14), cell(0x13, 0x0D), cell(0x11, 0x0C), cell(0x13, 0x0F),
                                       cell(0x13, 0x10))
# 밤 레코드 14~18. FC 는 처음·납치 뒤 상태에서 14~16 을 치우고(1C:$A058), 17·18 은 맵 아래 줄에 세워 둔다
NIGHT_MEI, NIGHT_CLOAK, NIGHT_CLOAK2 = cell(0x07, 0x0C), cell(0x06, 0x0C), cell(0x07, 0x0B)
NIGHT_PARKED = (cell(0x00, 0x22), cell(0x00, 0x23))
# 묘지 장면: 일행이 FC (03,0B)에 서면 시작. 메이는 (06,0B)를 지나 일행 오른쪽 (04,0B)로, 마중 온 둘은 서쪽 어귀 (00,06)
# 에서 나타나 (03,06)·(02,06)에 선다. FC 의 메이는 떠날 때 (03,0B)→(03,06)→(00,06) 로 걷지만 (03,0B)는 일행이 선 칸이고
# 묘지에서 나가는 길은 그 칸 하나뿐이라, 여기서는 그 자리에서 깜박이며 사라진다
GRAVE = (0x03, 0x0B)
GRAVE_RECT = (GRAVE[0] * 2, GRAVE[1] * 2 + 1, GRAVE[0] * 2 + 1, GRAVE[1] * 2 + 2)
MEI_PATH = (cell(0x06, 0x0B), cell(0x04, 0x0B))
PICKUP_FROM = cell(0x00, 0x06)
KIRYL_STAND, BREY_STAND = cell(0x03, 0x06), cell(0x02, 0x06)
MORNING_CELL = cell(*GRAVE)        # 날이 밝은 뒤 같은 칸으로 다시 불러온다
FACE_LEFT, FACE_RIGHT = 0x20, 0x10   # 인물 명령 2F(7E:31E0 위 니블)

# 빌린 인물 스크립트(DQ5 2B/02 목록 05:CD73, dq4ch2slots E2 칸 0~10). 칸마다 스크립트 길이 바이트 주소
SCRIPT_LIST = '05:CD73'
SCRIPTS = ('05:CD7A', '05:CD96', '05:CDA7', '05:CDEB', '05:CE0D', '05:CE1E', '05:CE49', '05:CE5A', '05:CEA1',
           '05:CEEF', '05:CF22')
USE = {'inn_cloak_a': 0, 'inn_cloak_b': 1, 'inn_princess': 2, 'trio': 3, 'deal': 4, 'cloaks': 5, 'mei': 6,
       'brey': 7, 'kiryl': 8}

TOWN_KID, TOWN_LEFT, TOWN_AFTER = 'ch2_frenol_town_kid', 'ch2_frenol_town_left', 'ch2_frenol_town_after'
INN_KID, INN_AFTER = 'ch2_frenol_inn_kid', 'ch2_frenol_inn_after'


def _al(a):
    return bytes((a & 0xFF, a >> 8 & 0xFF, a >> 16))


def _asm(parts):
    """바이트와 ('label', 이름)·(분기 옵코드, 이름) 을 이어 붙이고 8비트 상대 분기를 푼다."""
    out, labels, fixes = bytearray(), {}, []
    for p in parts:
        if isinstance(p, tuple) and p[0] == 'label':
            labels[p[1]] = len(out)
        elif isinstance(p, tuple):
            out.append(p[0])
            fixes.append((len(out), p[1]))
            out.append(0)
        else:
            out += p
    for at, name in fixes:
        d = labels[name] - (at + 1)
        if not -128 <= d <= 127:
            raise ValueError(f'분기 {name} 이 멂')
        out[at] = d & 0xFF
    return bytes(out)


FLAG_ABS = 0x2190 + IDX           # DB = 7E 에서 쓰는 주소
BAG = 0x2250                      # 맡긴 물건(물건 번호마다 개수)
PARTY_ITEMS = 0x2040 + 0x16       # 일행 기록 0 의 가진 물건 12칸. 기록은 42바이트씩
RECORD, SLOTS_PER = 42, 12


def _find(item, found, bag, none):
    """M 8·X 16·DB 7E 에서: 일행 기록(7E:201D 명)의 가진 물건에서 item 을 찾아 X = 그 칸 주소로 found 에, 없고
    맡긴 물건에 있으면 bag 에, 아무 데도 없으면 none 에 뛴다. 스택은 들어올 때와 같게 둔다."""
    return [
        bytes((0xAD, 0x1D, 0x20)), (0xF0, 'bag?'), bytes((0x48,)),            # LDA $201D / BEQ / PHA
        bytes((0xA2, *PARTY_ITEMS.to_bytes(2, 'little'))),                    # LDX #첫 칸
        ('label', 'rec'), bytes((0xA0, SLOTS_PER, 0x00)),                     # LDY #12
        ('label', 'slot'), bytes((0xBD, 0x00, 0x00, 0xC9, item)), (0xF0, 'hit'),   # LDA $0000,X / CMP
        bytes((0xE8, 0x88)), (0xD0, 'slot'),                                  # INX / DEY / BNE
        bytes((0xC2, 0x20, 0x8A, 0x18, 0x69, RECORD - SLOTS_PER, 0x00, 0xAA, 0xE2, 0x20)),   # X += 30
        bytes((0xA3, 0x01, 0x3A, 0x83, 0x01)), (0xD0, 'rec'),                 # 남은 수 하나 줄임
        bytes((0x68,)), (0x80, 'bag?'),
        ('label', 'hit'), bytes((0x68,)), (0x80, found),
        ('label', 'bag?'), bytes((0xAD, *(BAG + item).to_bytes(2, 'little'))), (0xD0, bag), (0x80, none),
    ]


def _gate():
    """인물 스크립트(37)에서: 팔찌가 일행에게도 맡긴 물건에도 없으면 NOBR 을 켜고, 있으면 끈다."""
    db7e = bytes((0xA9, 0x7E, 0x48, 0xAB))
    return ENTER + db7e + _asm(_find(BRACELET, 'have', 'have', 'none') + [
        ('label', 'none'), bytes((0xAD, *FLAG_ABS.to_bytes(2, 'little'), 0x09, NOBR[1])), (0x80, 'store'),
        ('label', 'have'), bytes((0xAD, *FLAG_ABS.to_bytes(2, 'little'), 0x29, ~NOBR[1] & 0xFF)),
        ('label', 'store'), bytes((0x8D, *FLAG_ABS.to_bytes(2, 'little'))),
    ]) + LEAVE


def _swap():
    """팔찌를 도적의 열쇠로 바꾼다(FC 1D 이벤트 3E: 76 을 빼고 71 을 줌). 가진 칸이면 그 칸에, 맡긴 물건이면 맡긴 쪽에."""
    db7e = bytes((0xA9, 0x7E, 0x48, 0xAB))
    return ENTER + db7e + _asm(_find(BRACELET, 'slot!', 'bag!', 'end') + [
        ('label', 'slot!'), bytes((0xA9, THIEF_KEY, 0x9D, 0x00, 0x00)), (0x80, 'end'),
        ('label', 'bag!'), bytes((0xCE, *(BAG + BRACELET).to_bytes(2, 'little'),
                                  0xEE, *(BAG + THIEF_KEY).to_bytes(2, 'little'))),
        ('label', 'end'),
    ]) + LEAVE


def _end_before():
    """M 8·DB 0: RESCUED 를 켜고 장면 flag 를 끄고, 필드 시간을 아침으로."""
    a = 0x7E2190 + IDX
    t = ch2.TIME_AT
    return (bytes((0xAF,)) + _al(a) + bytes((0x29, ~SCENE_BITS & 0xFF, 0x09, RESCUED[1], 0x8F)) + _al(a) +
            bytes((0xA9, ch2.MORNING & 0xFF, 0x8F)) + _al(t) + bytes((0xA9, ch2.MORNING >> 8, 0x8F)) + _al(t + 1))


def _end_tokens(ctx):
    """서술(FC 0367) → 아침의 같은 칸으로 다시 불러오기(FC 는 $62ED = 1E 로 두고 맵을 다시 실음)."""
    g, n = (int(v, 16) for v in TOWN.split('/'))
    end = ctx.msg['end'] if ctx.msg else 0
    return [('msg', end), bytes((0x90, g, n, *MORNING_CELL, 0x01, 0x80, 0xFF))]


def _event_bytes(tokens):
    return b''.join(bytes((0x60, t[1] & 0xFF, t[1] >> 8)) if isinstance(t, tuple) else t for t in tokens)


def native(ctx):
    import dq4prologue
    out = bytearray()
    at = {}

    def put(name, b):
        at[name] = ctx.code_at + len(out)
        out.extend(b)
    put('cry', dq4prologue._inside(*CRY_RECT))
    put('stop', dq4prologue._inside(*STOP_RECT))
    put('grave', dq4prologue._inside(*GRAVE_RECT))
    put('gate', _gate())
    put('swap', _swap())
    put('end_event', _event_bytes(_end_tokens(ctx)))
    put('end', ch2._event_call(at['end_event'], _end_before()))
    return bytes(out), at


def events(ctx):
    return [_end_tokens(ctx)]


def _bye_pages():
    return speak('메이', '그럼 안녕./진짜 공주님……', '잘 있어……')


# FC 메시지 번호(NDS 대사 번호). NDS 일본어 원문을 옮기고, NDS 에 없는 줄은 FC 를 옮겼다
MESSAGES = {
    # 여관 2층의 납치(FC 02FD·02FE, NDS 6002·6015~6017)
    'cry': say('싫어어! 놔 줘!/누가 좀 살려 줘!'),
    'stop': say('멈춰라!/더 다가오면/공주의 목숨은/없을 줄 알아라!', '그나저나 이런 여관에/설마 공주님이/와 있을 줄이야!',
                '좋아! 얘들아, 가자!'),
    'brey_scene': say('오오! 공주님이!/공주님이 납치범의/손에!', '어느 분인지는/모르겠으나 공주님을!/공주님을 구해/주시오!'),  # 0623(6008·6009)
    'kiryl_scene': say('으윽, 당했다……', '갑자기 그놈들이/나타나서 공주님을/억지로……'),                          # 0624(6011·6012)
    # 납치 뒤의 여관 2층(FC 0627·0626, NDS 6503·6504·6506)
    'kiryl': say('너희들, 부디/공주님을 구해 다오./그리하면 상은/원하는 대로 주마.',
                 '응? 무얼 그리/수상쩍은 얼굴로/보느냐? 무례하구나./나는 성의 신관이니라.'),
    'brey': say('이 무슨 일이란/말인가. 메이가……/아니, 공주님이/납치되고 말았어.'),
    # 납치 뒤의 마을(FC 07D1~07D6, NDS 6509~6528)
    'girl_kid': say('꺄아! 큰일이야!/공주님이/납치됐대!'),                                                # 07D1(6515)
    'man_kid': say('정말 깜짝 놀랐어요!/글쎄 여관에 있던/공주님이 납치됐다지/뭡니까!',                    # 07D2(6517·6518)
                   '대담한 짓을 하는/사람도 다 있군요……/역시 몸값이/목적인가.'),
    'merchant_kid': say('지금쯤 공주님은/무슨 일을 당하고/계실지……/아아, 공주님……'),                    # 07D3(6522)
    'aunt_kid': say('공주님쯤 되면/나쁜 놈들한테/노림을 당하는구나./아이, 무서워.'),                    # 07D4(6520)
    'inn_kid': say('아이고, 아이고……'),                                                                 # 07D5(6509)
    'letter': say('있잖아, 아까 강아지/코로가 이런 편지를/물고 왔어./읽어 볼게.',                        # 07D6(6526~6528)
                  '공주를 돌려받고/싶거든 내일 밤/이 마을의 보물/황금의 팔찌를',
                  '마을 묘지까지/가져와라.', '뭘까, 이거?/응. 아무한테도/말 안 할게.'),
    # 밤의 묘지(FC 0362·0364·0363·0365·0366·02A0·0427·0367, NDS 8007~8039)
    'deal': say('아무래도 약속한/물건을 가져온/모양이군./어서 이리 내놔!'),
    'refuse': say('공주가 죽어도/좋단 말이냐?/어서 이리 넘겨!'),
    'given': say('확실히 받았다!/그럼 공주는/돌려주지./잘 있어라!'),
    'mei': (say('구해 줘서 고마워./아아, 이제/공주님 노릇은/지긋지긋해.', '미안해./나 사실은/공주님이 아니야.',
                '내 이름은 메이./그냥 떠돌이/예인이야.')[:-1] + [ch1.PAGE] +
            speak('메이', '공주님 행세를/하니까 다들/잘해 줘서 그만/우쭐했을 뿐이야……')),
    'mei_key': speak('메이', '자, 마중도/온 것 같으니/나는 슬슬 갈게.', '보답이라고 하긴/뭣하지만 이/도적의 열쇠를/너에게 줄게.'),
    'got': narrate('아리나는/도적의 열쇠를/손에 넣었다!'),
    'bye': _bye_pages(),
    'end': narrate('이리하여 가짜 공주/메이 일행은/마을에서 모습을/감추었다.', '그리고 날이 밝았다……'),
    # 사건 뒤의 마을·여관 2층(FC 07D7~07DC·0628·05C9·05CA, NDS 9010~9058)
    'aunt_after': say('그 공주님이/가짜였다면서?/하긴 진짜 공주님이/이런 마을에 올 리가/없지.'),          # 07D7(9012)
    'man_after': say('그건 그렇고 남쪽/사막의 오아시스에서/바자가 열리고/있다더군요.',                   # 07D8(9033·9034)
                     '혹시 그쪽에 갈/일이 있으면/들러 보세요./뜻밖의 물건이/있을지도 몰라요.'),
    'oldman_after': say('실은 내가 그/공주님에게 모아 둔/돈을 바치려/했었지.',                           # 07D9(9014·9015)
                        '하지만 거절하더군……/가짜였다지만/그 아가씨, 그리/나쁜 사람은/아니었어.'),
    'boy_after': say('남쪽 사막에서/바자가 열린대./누나들도 가?/좋겠다.'),                               # 07DA(9020)
    'hobbit_after': say('뭐라고, 황금의/팔찌를 납치범에게/넘겨 버렸단/말인가? 으음……',                  # 07DB(9037~9039)
                        '실은 그 팔찌는/신비한 마력을/지니고 있었다네.', '나쁜 일이 일어나지/않으면 좋으련만.'),
    'oldman_night': say('도무지 눈이 말똥해서/잠이 안 오는구먼./이런 밤에는 옛일이/자꾸 떠올라.',        # 07DC(9057·9058)
                        '나는 젊었을 때/동쪽 도시 엔돌에/살았지. 무술 대회를/자주 보러 갔었어.'),
    'girl_after': say('여기는 프레놀/마을이야.'),                                                         # 0628(9010)
    'man_sleep': say('쿨쿨……'),                                                                          # 05C9(9051)
    'boy_sleep': say('새근새근……'),                                                                      # 05CA(9054)
}

TALKS = ('brey_scene', 'kiryl_scene', 'kiryl', 'brey', 'girl_kid', 'man_kid', 'merchant_kid', 'aunt_kid', 'inn_kid',
         'letter', 'deal', 'aunt_after', 'man_after', 'oldman_after', 'boy_after', 'hobbit_after', 'oldman_night',
         'girl_after', 'man_sleep', 'boy_sleep')
INN_SERVICE = 6                   # 06:DBD2 특수 기능 06 여관(dq4shopport.INN)


def _flag_on(flag):
    return {"op": "flag-on", "index": flag[0], "mask": flag[1]}


def talk_scripts(ctx):
    msg = lambda k: {"op": "msg", "id": f"{ctx.msg[k]:03X}"}  # noqa: E731
    yes = {"code": "05"}
    give = [msg('given'), _flag_on(GIVEN), _flag_on(ch2.ANSWERED)]
    # FC 는 아니요면 0364 뒤 예·아니요를 다시 묻는다. 세 번까지 그 자리에서 다시 묻고, 그래도 아니요면 스크립트가 처음부터
    refuse = [msg('refuse'), _flag_on(ch2.ANSWERED)]
    for _ in range(3):
        refuse = [msg('refuse'), {"op": "if", "cond": yes, "then": give, "else": refuse}]
    bodies = {'inn_kid': [msg('inn_kid'), {"op": "service", "index": INN_SERVICE}],
              'deal': [msg('deal'), {"op": "if", "cond": yes, "then": give, "else": refuse}]}
    return [bodies.get(name, [msg(name)]) for name in TALKS]


def _cmd(op, *args, **kw):
    return {"op": op, "args": list(args), **kw}


def _walk(*cells):
    return [c for x, y in cells for c in (_cmd('13', x, y), _cmd('14'))]


def _wait_on(flag):
    return _cmd('09', 0x80 | flag[0], flag[1])


def _gated(gate, body):
    """밤 장면 인물: 팔찌가 없으면 숨고 치운다(FC 1C:$A058)."""
    return [_cmd('37', *_al(gate)), _cmd('06', *NOBR, target='off')] + body + [
        _cmd('16'), _cmd('28', label='off'), _cmd('52'), _cmd('16')]


def scripts(ctx):
    at, base = ctx.at, ctx.base
    gate = at['gate']
    lo, hi = lambda v: v & 0xFF, lambda v: v >> 8
    msg = lambda k: _cmd('21', lo(ctx.msg[k]), hi(ctx.msg[k]))  # noqa: E731
    call = lambda a: _cmd('37', *_al(a))  # noqa: E731
    flag_on = lambda f: _cmd('10', *f)  # noqa: E731
    out = {
        # 여관 2층: 다가가면 비명 → 「멈춰라!」 → 셋이 계단으로(FC 레코드 02 의 블록)
        'inn_cloak_a': [_cmd('05', *_al(at['cry'])), msg('cry'), _cmd('05', *_al(at['stop'])), _cmd('3F'), msg('stop'),
                        flag_on(KIDNAPPED), _cmd('1C')] + _walk(*STAIRS) + [_cmd('52'), _cmd('40'), _cmd('16')],
        'inn_cloak_b': [_wait_on(KIDNAPPED), _cmd('1C')] + _walk(STAIRS[1]) + [_cmd('52'), _cmd('16')],
        'inn_princess': [_wait_on(KIDNAPPED), _cmd('1C')] + _walk(*STAIRS) + [_cmd('52'), _cmd('16')],
        # 마을: 셋이 서쪽 길로 나간다(FC 레코드 02~04 가 같은 블록). 앞선 이가 LEFT 를 켠다. 조작을 막지 않으므로
        # 주인공을 지나가지 않고(1C 없음) 주인공이 길에 서면 비킬 때까지 기다린다
        'trio': _walk(*TRIO_PATH) + [flag_on(LEFT), _cmd('52'), _cmd('16')],
        # 묘지: 보이지 않는 인물이 일행이 (03,0B)에 서기를 기다려 망토의 요구(대화 deal)를 묻는다
        'deal': [_cmd('28'), _cmd('52')] + _gated(gate, [
            _cmd('05', *_al(at['grave'])), _cmd('3F'),
            call(base['talk_here']) | {"label": "ask"},
            _cmd('09', 0x80 | ch2.ANSWERED[0], ch2.ANSWERED[1]), _cmd('11', ch2.ANSWERED[0], ~ch2.ANSWERED[1] & 0xFF),
            _cmd('06', *GIVEN, target='given'), _cmd('03', target='ask'), _cmd('16', label='given')]),
        'cloaks': _gated(gate, [_wait_on(GIVEN), _cmd('51'), _cmd('52')]),
        'mei': _gated(gate, [_wait_on(GIVEN), _cmd('1C')] + _walk(*MEI_PATH) + [
            _cmd('2F', FACE_LEFT), msg('mei'), flag_on(CALLED), _wait_on(ARRIVED), msg('mei_key'), call(at['swap']),
            msg('got'), msg('bye'), flag_on(BYE), _cmd('51'), _cmd('52'), _cmd('40'), call(at['end'])]),
        # 마중 온 둘은 FC 처럼 맵 아래 줄(맵 밖)에 세워 두었다가 서쪽 어귀로 옮겨 걸어 들어온다(FC 레코드 17·18 의 25)
        'brey': _gated(gate, [_wait_on(CALLED), _cmd('02', 4), _cmd('15'), _cmd('01'),
                        _cmd('2B', *PICKUP_FROM), _cmd('1C')] + _walk(BREY_STAND) + [
            _cmd('2F', FACE_RIGHT), _wait_on(BYE)] + _walk(PICKUP_FROM) + [_cmd('52')]),
        'kiryl': _gated(gate, [_wait_on(CALLED), _cmd('2B', *PICKUP_FROM), _cmd('1C')] +
                        _walk(KIRYL_STAND) + [_cmd('2F', FACE_RIGHT), flag_on(ARRIVED), _wait_on(BYE)] +
                        _walk(PICKUP_FROM) + [_cmd('52')]),
    }
    return [{"address": SCRIPTS[USE[k]], "commands": v} for k, v in out.items()]


def _src(name):
    return {"list": SCRIPT_LIST, "index": USE[name]}


def _at(e):
    return (e["fields"]["x"], e["fields"]["y"])


def _scripted(e, name, gfx, talk=None):
    f = {**e["fields"], "gfx": gfx, "interval": max(1, e["fields"].get("interval", 1))}
    if talk is not None:
        f["talk"] = talk
    return {**e, "from": _src(name), "fields": f}


def _person(name, x, y, gfx, talk, time, facing='down'):
    return {"from": _src(name), "time": time,
            "fields": {"x": x, "y": y, "facing": facing, "talk": talk, "gfx": gfx, "layer": 0, "interval": 1}}


# 사건 뒤 목록(FC 0F/00 목록 플래그 00&40 = 1C:$838B, 0F/01 = 1C:$8589): (맵, 낮/밤, FC 칸, 방향, 걸음 간격, FC 그림,
# 대화). 대화가 정수면 그 대화 번호 그대로(01 무기점·02 도구점·05 교회·06 여관, dq4shopport 의 사건 판매자), 'dog' 는
# 옮긴 강아지의 대화. test_dq4ch2frenol 이 FC 롬의 목록과 견준다
AFTER = (
    (TOWN, 'day', (0x03, 0x18), 'left', 1, 0x1B, 0x05),
    (TOWN, 'day', (0x11, 0x0C), 'down', 0, 0x17, 0x06),
    (TOWN, 'day', (0x11, 0x04), 'right', 0, 0x14, 'man_after'),
    (TOWN, 'day', (0x1A, 0x14), 'right', 2, 0x15, 'boy_after'),
    (TOWN, 'day', (0x1B, 0x05), 'down', 0, 0x16, 'oldman_after'),
    (TOWN, 'day', (0x1B, 0x15), 'up', 1, 0x24, 'dog'),
    (TOWN, 'day', (0x12, 0x03), 'down', 0, 0x28, 'aunt_after'),
    (TOWN, 'day', (0x17, 0x04), 'down', 8, 0x13, 'girl_after'),
    (TOWN, 'day', (0x1C, 0x0B), 'down', 0, 0x17, 0x01),
    (TOWN, 'day', (0x13, 0x16), 'right', 0, 0x17, 0x02),
    (TOWN, 'night', (0x07, 0x15), 'down', 0, 0x1B, 0x05),
    (TOWN, 'night', (0x11, 0x0C), 'down', 0, 0x17, 0x06),
    (TOWN, 'night', (0x11, 0x04), 'down', 0, 0x28, 'aunt_after'),
    (TOWN, 'night', (0x0F, 0x03), 'right', 0, 0x15, 'boy_sleep'),
    (TOWN, 'night', (0x1B, 0x06), 'right', 0, 0x16, 'oldman_night'),
    (TOWN, 'night', (0x15, 0x07), 'down', 4, 0x24, 'dog'),
    (TOWN, 'night', (0x0F, 0x04), 'right', 0, 0x14, 'man_sleep'),
    (INN, 'day', (0x22, 0x03), 'right', 0, 0x14, 'man_kid'),
    (INN, 'day', (0x04, 0x05), 'left', 0, 0x1F, 'hobbit_after'),
    (INN, 'night', (0x04, 0x05), 'down', 0, 0x1F, 'hobbit_after'),
)
# 대화마다 FC 가 띄우는 첫 메시지(NDS 그림 표 dq4npcport.NDS_LOOKS 의 열쇠)
FC_FIRST = {'man_after': 0x7D8, 'boy_after': 0x7DA, 'oldman_after': 0x7D9, 'dog': 0x625, 'aunt_after': 0x7D7,
            'girl_after': 0x628, 'boy_sleep': 0x5CA, 'oldman_night': 0x7DC, 'man_sleep': 0x5C9, 'man_kid': 0x7D2,
            'hobbit_after': 0x7DB}


def after_entries(m, talk, dog):
    """AFTER 의 맵 m 몫을 dq5npcrelocate 목록 항목으로(dq4npcport.port 와 같은 꼴). talk: {이름: 대화 번호}."""
    import dq4npcport as port
    out = []
    for mp, time, (x, y), facing, interval, picture, who in AFTER:
        if mp != m:
            continue
        number = who if isinstance(who, int) else dog if who == 'dog' else talk[who]
        gfx = port.PICTURES[picture] if isinstance(who, int) else port.NDS_LOOKS.get((m, FC_FIRST[who]),
                                                                                       port.PICTURES[picture])
        cx, cy = port.cell(x, y)
        out.append({"from": port.WALK if interval else port.STAND, "time": time,
                    "fields": {"x": cx, "y": cy, "facing": facing, "talk": number, "gfx": gfx, "layer": 0,
                               "interval": 0 if isinstance(who, int) else interval}})
    return out


# 처음 상태(대체 목록 없음)에서 FC 가 치우는 인물: 맵 → ((낮·밤 모두의 셀), (밤에만의 셀))
START_ABSENT = {TOWN: ((*TRIO, GIRL_INN, DOG), (NIGHT_MEI, NIGHT_CLOAK, *NIGHT_PARKED)),
                INN: ((INN_DUMMY,), ())}


def absent(ctx):
    """{(맵, DQ5 셀 x, y, 밤)}: 처음 상태 목록에서 이 모듈이 뺀 인물(dq4npccheck 가 말 걸지 않음)."""
    out = set()
    for m, (both, night_only) in START_ABSENT.items():
        out |= {(m, x, y, n) for x, y in both for n in (False, True)}
        out |= {(m, x, y, True) for x, y in night_only}
    return out


def start_messages(ctx):
    """처음 상태의 가짜 브라이·크리프트는 비명 사각형(CRY_RECT) 안에 서 있어, 다가가면 말을 걸기 전에 비명이 먼저 뜬다."""
    return {(INN, FC_INN_BREY, None): ctx.msg['cry'], (INN, FC_INN_KIRYL, None): ctx.msg['cry']}


def npc_lists(lists, ctx):
    t = ctx.talk
    if TOWN not in lists and INN not in lists:
        return [], []           # 인물 없이 옮긴 목록(dq4npcport.port 의 with_people=False)
    town, inn = list(lists[TOWN]["entries"]), list(lists[INN]["entries"])
    nobody = next(e["fields"]["talk"] for e in town if _at(e) == TRIO[0])
    dog = next(e["fields"]["talk"] for e in town if _at(e) == DOG)
    hobbit = [e for e in inn if _at(e) == INN_HOBBIT]
    if not nobody or not hobbit:
        raise SystemExit('프레놀: 옮긴 목록에 사건 인물이 없음')

    def drop(entries, both, night_only=()):
        return [e for e in entries if _at(e) not in both and not (e["time"] == "night" and _at(e) in night_only)]

    def retalk(entries, table):
        return [{**e, "fields": {**e["fields"], "talk": t[table[_at(e)]]}} if _at(e) in table else e for e in entries]

    # 처음 상태: FC 가 들어설 때 치우는 인물을 빼고, 여관 2층의 사건 인물에 스크립트와 그림을 준다
    both, night_only = START_ABSENT[TOWN]
    lists[TOWN]["entries"] = drop(town, both, night_only)
    inn_scene = {INN_CLOAK_A: ('inn_cloak_a', CLOAK_PIC), INN_CLOAK_B: ('inn_cloak_b', CLOAK_PIC),
                 INN_PRINCESS: ('inn_princess', PRINCESS_PIC)}
    inn_talk = {INN_BREY: ('brey_scene', BREY_PIC), INN_KIRYL: ('kiryl_scene', KIRYL_PIC)}
    edited = []
    for e in drop(inn, START_ABSENT[INN][0]):
        if _at(e) in inn_scene:
            name, gfx = inn_scene[_at(e)]
            e = _scripted(e, name, gfx, nobody)
        elif _at(e) in inn_talk:
            name, gfx = inn_talk[_at(e)]
            e = {**e, "fields": {**e["fields"], "talk": t[name], "gfx": gfx}}
        edited.append(e)
    lists[INN]["entries"] = edited

    # 납치 뒤: 어귀의 여자 대신 여관 앞의 같은 여자, 강아지가 돌아오고, 셋이 서쪽으로 나간다(밤 장면 인물은 아직 없음)
    kid_talk = {GIRL_INN: 'girl_kid', MAN: 'man_kid', INNKEEPER: 'inn_kid', MERCHANT: 'merchant_kid',
                AUNT: 'aunt_kid', BOY: 'letter'}
    kid = retalk(drop(town, (GIRL_WALKER,), (NIGHT_MEI, NIGHT_CLOAK, *NIGHT_PARKED)), kid_talk)
    trio = {c: p for c, p in zip(TRIO, TRIO_PICS)}
    kid_walk = [_scripted(e, 'trio', trio[_at(e)]) if _at(e) in trio else e for e in kid]
    left = [e for e in kid if _at(e) not in trio]
    # 납치범이 나간 뒤 밤에는 묘지에 셋(팔찌가 없으면 gate 가 치움)과, 서쪽 어귀에서 나타날 마중 둘, 묻는 인물
    scene = []
    for time in ('night',):
        scene += [_person('mei', *NIGHT_MEI, PRINCESS_PIC, nobody, time, 'left'),
                  _person('cloaks', *NIGHT_CLOAK, CLOAK_PIC, nobody, time, 'left'),
                  _person('cloaks', *NIGHT_CLOAK2, CLOAK_PIC, nobody, time, 'left'),
                  _person('kiryl', *NIGHT_PARKED[0], KIRYL_PIC, nobody, time, 'right'),
                  _person('brey', *NIGHT_PARKED[1], BREY_PIC, nobody, time, 'right'),
                  {"from": _src('deal'), "time": time, "fields": {"x": 0, "y": 1, "facing": "down",
                                                                  "talk": t['deal'], "gfx": 0x01, "layer": 0,
                                                                  "interval": 1}}]
    inn_kid = hobbit + [
        {"from": hobbit[0]["from"], "time": time,
         "fields": {**hobbit[0]["fields"], "x": x, "y": y, "facing": 'right', "talk": t[name], "gfx": gfx,
                    "interval": 0}}
        for time in ('day', 'night') for (x, y), name, gfx in ((cell(0x22, 0x07), 'kiryl', KIRYL_PIC),
                                                               (cell(0x21, 0x07), 'brey', BREY_PIC))]
    new = [{"name": TOWN_KID, "entries": kid_walk},
           {"name": TOWN_LEFT, "entries": left + scene},
           {"name": TOWN_AFTER, "entries": after_entries(TOWN, t, dog)},
           {"name": INN_KID, "entries": inn_kid},
           {"name": INN_AFTER, "entries": after_entries(INN, t, dog)}]

    def on(m, flag, name):
        return {"map": m, "flag": flag[0], "when": "on", "mask": flag[1], "list": f"new:{name}"}
    # 대체 표는 앞 줄부터 맞는 첫 줄을 쓴다: 나중 상태를 먼저
    over = [on(TOWN, RESCUED, TOWN_AFTER), on(TOWN, LEFT, TOWN_LEFT), on(TOWN, KIDNAPPED, TOWN_KID),
            on(INN, RESCUED, INN_AFTER), on(INN, KIDNAPPED, INN_KID)]
    return new, over
