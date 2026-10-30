"""NDS 리메이크의 서장(산골 마을 지하 검술 수련과 마을 사람)을 1장 앞에 넣는다.

무대는 dq4groupbuild.py 가 새 그룹에 넣은 FC 14/00(습격 전 마을)과 14/01(지하)이다. 새 게임은 지하에서
장 제목 상자 「서장」으로 시작하고, 수련 뒤 주인공이 말을 걸면 검사가 예·아니요로 묻고, 나간다. 마을에는 NDS 서장의
마을 사람을 세운다. 대사는 NDS 서장 대사(MESS/ja/b0200000.mpt)를 옮긴 것이다. 서장 끝(개구리·신시아·
저녁)과 1장으로 넘기기는 아직 없어, dq4chapter1.py build --prologue 를 줄 때만 넣는다.
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
TALK_AT = ('--extra-at', '3A:F000', '--hook-at', '06:FE10')
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


def native():
    """(바이트, {이름: 주소}). 인물 스크립트 명령 37 이 JSL 로 부른다."""
    wait = box.ENTER + box.wait(20) + box.LEAVE
    return wait, {'wait': CODE_AT}


def talk_doc():
    """dq5talkwrite 의 dq5talk/1: 검사의 물음. 조건 05 는 예·아니요 창(06:B383)에서 예."""
    return {"format": "dq5talk/1", "scripts": [{"talk": f"{T_ASK:03X}", "body": [
        {"op": "msg", "id": f"{M_ASK:03X}"},
        {"op": "if", "cond": {"code": "05"},
         "then": {"op": "msg", "id": f"{M_YES:03X}"}, "else": {"op": "msg", "id": f"{M_NO:03X}"}},
        {"op": "flag-on", "index": DONE[0], "mask": DONE[1]}]}]}


def _cmd(op, *args):
    return {"op": op, "args": list(args)}


def _long(addr):
    return [addr & 0xFF, addr >> 8 & 0xFF, addr >> 16]


def master_script(boxes):
    """수련: 상자 → 밝히기 → 칼 소리 셋 → 조작을 풀고 주인공이 말을 걸어 대화가 끝날(깃발) 때까지 → 맺음말 → 나가기."""
    _, at = native()
    lo, hi = (lambda m: m & 0xFF), (lambda m: m >> 8)
    head = [_cmd('3F'), _cmd('37', *_long(boxes[SCENE.name])), _cmd('37', *_long(boxes['reveal'])),
            _cmd('02', 3), _cmd('37', *_long(at['wait'])), _cmd('20', *SWORD), _cmd('01'),
            _cmd('37', *_long(at['wait'])),
            _cmd('40'), _cmd('09', 0x80 | DONE[0], DONE[1]), _cmd('3F')]
    walk = [c for x, y in MASTER_OUT for c in (_cmd('13', x * 2, y * 2), _cmd('14'))]
    tail = ([_cmd('21', lo(M_AFTER), hi(M_AFTER))] + walk +
            [_cmd('28'), _cmd('40'), _cmd('16')])
    return {"address": MASTER_SCRIPT, "commands": head + tail}


def npc_lists():
    """(lists, new_lists, overrides, scripts) 에 더할 것."""
    master = ch1.entry(MASTER_SRC, *MASTER_AT, SWORDSMAN, 'down', T_ASK)
    sleeper = ch1.entry(SLEEPER_SRC, *SLEEPER_AT, MAN, 'down', T_SLEEPER)
    people = [ch1.entry(ch1.STATIC, x, y, g, f, t) for x, y, g, f, t in VILLAGERS] + [sleeper]
    lists = [{"map": CELLAR, "entries": [master]}, {"map": VILLAGE, "entries": people}]
    new_lists = [{"name": "cellar_after", "entries": []}]
    overrides = [{"map": CELLAR, "flag": DONE[0], "when": "on", "mask": DONE[1], "list": "new:cellar_after"}]
    scripts = [master_script(box.entry_points((SCENE, box.CHAPTER1))),
               {"address": SLEEPER_SCRIPT, "commands": [_cmd('16')]}]
    return lists, new_lists, overrides, scripts


def apply(data):
    d = bytearray(data)
    code, _ = native()
    o = lorom(CODE_AT)
    if any(d[o:o + len(code)]):
        raise SystemExit(f'{CODE_AT:06X}: 비어 있지 않은 자리')
    d[o:o + len(code)] = code
    return bytes(d)
