"""DQ4 1장 첫머리(바트랜드 왕좌의 방 연출·한글 대사·성 앞 마을)를 DQ5 엔진에 넣는다.

새 게임의 첫 맵을 DQ5 프롤로그(02/06) 대신 바트랜드 왕좌의 방(FC 02/01 → 새 그룹 36/01)으로 바꾸고,
FC 원작 대사를 옮긴 한글 메시지와 왕좌의 방·성 앞(FC 02/00 → 36/00)의 인물 배치·연출 스크립트를 쓴다.
맵·출구는 dq4groupbuild.py 의 패치를 그대로 쓰고, 그 빈 인물 패치만 이 인물로 바꾼다.
FC 블록 (x, y) 는 DQ5 셀 (2x, 2y). 원작이 「ライアン」 으로 박은 자리는 이름 입력값({1012})으로 바꾼다.
형식은 sfc/dq4/docs/dq4-chapter1-format.md.

  python sfc/dq4/tools/dq4chapter1.py messages -o work/ch1/messages.json
  python sfc/dq4/tools/dq4menupatch.py build --rom 서곡롬 --messages work/ch1/messages.json --out work/ch1/menu.sfc
  python sfc/dq4/tools/dq4chapter1.py build --rom work/ch1/menu.sfc --out work/ch1/dq4-ch1.sfc
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sys
import tempfile

HERE = Path(__file__).resolve().parent
DQ5_TOOLS = HERE.parents[1] / 'dq5' / 'tools'
sys.path[:0] = [str(HERE), str(DQ5_TOOLS)]

import dq4wrap  # noqa: E402
from dq4environmentrom import GROUPS  # noqa: E402
from dq4romassets import ips_patch, set_checksum  # noqa: E402
import dq4chapterbox  # noqa: E402
from dq5build import load  # noqa: E402

LINE, END, PAGE, SPEAK, NARR, HERO = 0x1000, 0x1001, 0x1002, 0x1003, 0x1006, 0x1012
Q = 0x363      # 「 (DQ5 글자)
DOTS = 0x366   # …

# 왕의 연설이 끝나면 켜는 연출 깃발(번호, 비트). 자리는 dq4chapterbox.CHAPTER1 한 곳에서 정한다
EVENT_FLAG = (dq4chapterbox.CHAPTER1.flag[0] - 0x7E2190, dq4chapterbox.CHAPTER1.flag[1])
# バトランド 성 FC 02/01(왕좌)·02/00(성 앞)이 놓인 DQ5 맵
THRONE, FRONT = (f'{g:02X}/{n:02X}' for g, n in (GROUPS['02-01'], GROUPS['burland']))
START = (THRONE, 32, 42)       # FC (10,15): 줄 선 전사들 사이의 빈 자리


# DQ5 메시지 창은 한 쪽에 4줄, 한 줄은 ＊「·들여쓰기 2칸 뒤 한글 14자까지(실측: 15자째에서 넘쳐 깨짐).
# 서술({1006})은 ＊「 가 없어 한글 15자까지 들어간다(실측: 16자째는 줄 첫머리로 돌아가 다음 줄과 겹침).
# 한 쪽이 4줄을 넘으면 쪽 넘김 없이 밀려 올라가다 빈 창이 남았다(실측).
PAGE_LINES, LINE_COLS, NARR_COLS, NAME_COLS = 4, 14, 15, 4
NAME = '@'      # 대사 문자열 안의 주인공 이름 자리({1012}). 이름 입력은 네 글자까지


def _josa():
    """{'{은}': (코드, 칸)}. 이름 뒤 조사도 찍힌 이름의 받침으로 고른다(dq4josa). 키는 dq4sysmsg 와 같다."""
    import dq4josa
    return {f'{{{"로" if none == "로" else has}}}': (code, len(has))
            for code, (has, none, _) in dq4josa.JOSA.items()}


def _parts(text):
    """조사 토큰({은} 등)과 나머지 글자로 나눈다."""
    import re
    return [p for p in re.split(r'(\{[^}]+\})', text) if p]


def _width(word):
    josa = _josa()
    return sum(josa[p][1] if p in josa else sum(NAME_COLS if c == NAME else 1 for c in p) for p in _parts(word))


def _codes(line):
    josa = _josa()
    out = []
    for p in _parts(line):
        out += [josa[p][0]] if p in josa else _plain_codes(p)
    return out


def _plain_codes(line):
    out = []
    for n, part in enumerate(line.split(NAME)):
        if n:
            out.append(HERO)
        for k, chunk in enumerate(part.split('…')):
            if k:
                out.append(DOTS)
            if chunk:
                out.append(chunk)
    return out


def _message(pages, prefix=(), cols=LINE_COLS):
    """pages: 쪽마다 문장. 줄이 4줄을 넘으면 쪽을 더 나눈다."""
    out = []
    first = max(0, len(prefix[1]) + 1 - 2) if prefix else 0
    for text in pages:
        lines = dq4wrap.wrap(text, _width, cols, first, PAGE_LINES)
        for k in range(0, len(lines), PAGE_LINES):
            if out:
                out.append(PAGE)
            if prefix:
                out += [SPEAK, prefix[1], Q]
            for n, line in enumerate(lines[k:k + PAGE_LINES]):
                if n:
                    out.append(LINE)
                out += _codes(line)
    return out + [END]


def speak(name, *pages):
    return _message(pages, (SPEAK, name))


def say(*pages):
    return _message(pages)


def narrate(*pages):
    """서술문({1006}): ＊「 도 들여쓰기도 없어 한 줄이 15칸이다. 서술은 해라체(「~다.」)로 쓴다."""
    out = [NARR]
    for part in _message(pages, cols=NARR_COLS):
        out.append(part)
        if part == PAGE:        # 쪽이 바뀌면 첫 코드를 다시 본다(실측: 빼면 ＊「 가 붙음)
            out.append(NARR)
    return out


# 1장·서장의 한글 메시지는 DQ5 메시지(000~C7F) 뒤 C80 부터 빈 번호 없이 쓴다. 대화 번호 8BA~8FF 는 스크립트 없이
# 메시지 T + 3C6(C80~CC5)을 띄우므로 인물에게 그 번호를 그대로 주고, 스크립트가 띄우는 메시지도 같은 차례로 받는다.
# 900~ 는 덧붙인 대화 스크립트 자리라, 서장까지 다 받은 끝(dq4prologue.TALK_END)이 900 을 넘으면 안 된다.
# dq4npcport 가 옮긴 일본어 메시지는 그 끝 바로 뒤부터 둔다
TALK_BASE = 0x8BA
TEXTS = {}
_talks = []


def talk(parts):
    t = TALK_BASE + len(_talks)
    _talks.append(parts)
    TEXTS[t + 0x3C6] = parts
    return t


# FC 는 검은 화면에 장 제목 상자(dq4chapterbox.py)를 띄운 뒤, 검은 화면의 메시지 창에 이 서술을 쓴다
MSG_NARRATION = talk(narrate('이것은 바트랜드라는 작은 나라의 왕궁 전사의 이야기다.',
                             '@, 즉 당신도 그 왕궁 전사의 한 사람이었다.',
                             '어느 날 아침, 임금님은 전사들을 성의 넓은 방에 불러 모았다……')) + 0x3C6
MSG_MINISTER = talk(speak('대신', '이제부터 임금님께서 그대들에게 하실 말씀이 있다. 명심하여 듣도록.')) + 0x3C6
MSG_KING = talk(speak('왕',
                      '모두 편히 하라.',
                      '요즘 아이들이 사라진다는 소문은 그대들도 들었으리라.',
                      '오늘 아침에도 이무르 마을에서 어머니들이 눈물로 호소하러 왔노라.',
                      '이 나라의 왕으로서 더는 두고 볼 수 없노라.',
                      '일의 진상을 밝혀 이 짐에게 보고하라! 가라! 나의 전사들이여!')) + 0x3C6
T_KING = talk(say('그대의 활약을 기대하고 있노라, @여.'))
T_MINISTER = talk(say('자, 무얼 하는가. 어서 가지 않고.'))
T_EASY = talk(say('뭐, 느긋하게 하자고, @.'))
T_MOTHER = talk(say('전사님! 부디 저희 아이를 찾아 주세요!', '그 아이는 살아 있어요. 저는 알 수 있어요.'))
T_GATE1 = talk(say('여기는 바트랜드 성.'))
T_SCHOLAR = talk(say('@ 공인가. 아니, 마음에 걸리는 것이 있어서 조금 조사하고 있다네.'))
T_GATE2 = talk(say('수상한 자는 한 발짝도 들이지 않겠다!'))
T_NIGHT = talk(say('마을 밖으로 나가 계속 걷다 보면 이윽고 밤이 될 것입니다.'))
T_CHILD = talk(say('괴물은 옛날부터 있었지만 요즘 들어 아이들이 모습을 감추기 시작했다. 무슨 일이 있는 걸까?'))
T_INN = talk(say('@ 공. 싸우다 다치거든 마을로 돌아가 여관에 묵도록 하시오.'))
T_RIVAL = talk(say('여어, @! 아직도 여기서 어정대다니 여전히 굼뜨구먼.', '다른 녀석들은 이무르 마을로 간 거 아니었어?'))
T_MAID = talk(say('@ 님. 부디 다른 전사들에게 뒤지지 않도록 힘내 주세요.'))
T_DAYTIME = talk(say('예전엔 밤에만 나오던 마물이 낮에도 나온다지. 뒤숭숭한 세상이구먼.'))
T_IMURU = talk(say('저희는 이무르 마을에서 왔습니다.'))
T_HERB = talk(say('긴 여행이 될 것 같으면 마을에서 약초를 사 가시오.'))
# 밤(FC 밤 목록)
T_N_MOTHER = talk(say('그 아이 생각을 하면 밤에도 잠이 오지 않아서……', '전사님, 부디 부디……'))
T_N_ASLEEP = talk(say('임금님께서는 이미 잠자리에 드셨다.'))
T_N_INN = talk(say('오늘 밤은 여관에라도 묵고 내일 다시 오는 게 좋겠다.'))
T_N_SCHOLAR = talk(say('흐음…… 조사하면 조사할수록 닮았어!',
                       '요즘 날씨는 그 옛날 마물들이 날뛰던 시대와 꼭 닮았단 말이야.'))
T_N_ROUND = talk(say('이거야 원. 순찰도 쉽지 않군.'))
T_N_BED = talk(say('자, 자야지 자야지. 사람은 역시 잘 때가 제일 행복하다니까.'))
T_N_SNORE = talk(say('쿨쿨……'))

# 성 앞(36/00)은 dq4npcport.py 가 FC 인물을 놓고 일본어 원문을 둔다. 그 가운데 옮긴 것은 FC 메시지 묶음으로 찾아
# 같은 DQ5 메시지 번호의 글을 한글로 바꾼다.
FRONT_TEXTS = {
    (0x78C,): say('@ 공! 알고 있소?', '잠기지 않은 문도 있어서 열쇠 없이 열 수 있다네!'),
    (0x5E3, 0x5E4): say('괴물이라도 마을 안까지는 들어오지 못해요.', '그럼 왜 아이들이 없어지는 걸까요……'),
    (0x5E1,): say('바트랜드 왕은 사람이 좋아서 이 나라는 세금도 싸지.', '하지만 그만큼 무기나 방어구에도 돈을 못 들이는 거야.',
                  '더 강한 무기가 필요하면 스스로 돈을 모아 바꿔 사는 게 좋을걸.', '새 무기나 방어구를 사면 다시 장비하는 걸 잊지 말라고!'),
    (0x5E2,): say('이 성에서 서쪽 동굴을 빠져나가 바닷가를 따라 가면 이무르 마을이에요.'),
    (0x5E5,): say('이무르 마을에 가면 뭔가 알 수 있을지도 모르겠네요.'),
    (0x78D,): say('저는 프레아. 남편 알렉스가 여행을 떠난 채 돌아오지 않아요.', '전사님! 여행길에 혹시 알렉스를 보시거든 알려 주세요!'),
    (0x5E0,): say('여기는 바트랜드의 성 아래 마을입니다.'),
}

# 그림 번호(dq5sprite.py 시트에서 고름)
KING, MINISTER, GUARD, WARRIOR, WOMAN, MAID, SCHOLAR, MAN, VILLAGER = 0x14, 0x01, 0x67, 0x08, 0x04, 0x82, 0x09, 0x29, 0x0C

# (FC x, FC y, 그림, 방향, 대화)
STAFF = [
    (0x1B, 0x0E, WOMAN, 'left', T_MOTHER),
    # 문지기 둘은 FC 에서 (0F·10,1F)지만, 인물끼리는 가로 2칸 안으로 다가가지 못해(실측) 그 자리면 전사들이
    # 출구로 못 나간다. 한 칸씩 바깥 (0E·11,1F)에 세운다.
    (0x0E, 0x1F, GUARD, 'down', T_GATE1),
    (0x1B, 0x15, SCHOLAR, 'down', T_SCHOLAR),
    (0x11, 0x1F, GUARD, 'down', T_GATE2),
    (0x17, 0x1B, GUARD, 'down', T_NIGHT),
    (0x07, 0x1F, GUARD, 'down', T_CHILD),
    (0x0E, 0x12, GUARD, 'down', T_INN),
    (0x02, 0x08, WARRIOR, 'down', T_RIVAL),
    (0x12, 0x02, MAID, 'down', T_MAID),
    (0x16, 0x09, MAN, 'down', T_DAYTIME),
    (0x1C, 0x11, VILLAGER, 'down', T_IMURU),
    (0x11, 0x12, GUARD, 'down', T_HERB),
]
# 밤에는 연출 뒤에만 온다. 문지기는 낮과 같은 자리
NIGHT_STAFF = [
    (0x1B, 0x0E, WOMAN, 'left', T_N_MOTHER),
    (0x0E, 0x1F, GUARD, 'down', T_GATE1),
    (0x1D, 0x16, SCHOLAR, 'down', T_N_SCHOLAR),
    (0x11, 0x1F, GUARD, 'down', T_GATE2),
    (0x17, 0x09, GUARD, 'down', T_N_ROUND),
    (0x0F, 0x11, GUARD, 'down', T_N_ASLEEP),
    (0x10, 0x11, GUARD, 'down', T_N_INN),
    (0x01, 0x1C, GUARD, 'down', T_N_SNORE),
    (0x01, 0x1F, GUARD, 'down', T_N_BED),
]
KING_AT = (0x10, 0x0D)
# 연설이 끝나면 전사들이 두 줄로 아래 출구 (0F~10,23)까지 걸어가 빠진다(FC 인물 블록 레코드 12~19 와 같은 길).
# 한 줄로 몰면 통로에서 서로 막혀 멈췄다(실측).
EXIT_LEFT = [(0x0F, 0x1A), (0x0F, 0x23)]
EXIT_RIGHT = [(0x11, 0x1A), (0x10, 0x1A), (0x10, 0x23)]
KING_DOWN = (0x10, 0x13)       # 연설하러 내려와 서는 곳(FC 연출 뒤 화면)
MINISTER_AT = (0x0F, 0x13)
EASY_AT = (0x0E, 0x15)          # 연출 뒤에도 남는 전사
LINEUP = [(0x11, 0x17), (0x0F, 0x15), (0x11, 0x15), (0x0E, 0x17), (0x0F, 0x17), (0x10, 0x17)]

# 스크립트 없는 인물. 기타 44(bit4-5 = 00)라 말을 걸면 주인공 쪽으로 돈다. 03/00 의 05:8E43 0번은 54 라 돌지 않았다
STATIC = {"list": "05:AAF9", "index": 4}
SCRIPTED = {"list": "05:A848", "index": 0}     # 배 인물(스크립트 05:A84F)
HIDER = {"list": "05:A848", "index": 3}        # 배 인물(스크립트 05:A899). index 1 은 누운 선원(기타 bit7)이라 누워 그려졌다
HIDER2 = {"list": "05:A848", "index": 2}       # 배 인물(스크립트 05:A87B)


def entry(src, x, y, gfx, facing, talk_no):
    fields = {"x": x * 2, "y": y * 2, "gfx": gfx, "facing": facing, "talk": talk_no, "layer": 0}
    if src is STATIC:
        # 원본은 횃불이라 애니 2/2(빠른 깜박임). DQ5 사람 인물은 F/F 다
        fields.update(walk_anim=15, stand_anim=15)
    return {"from": src, "time": "day", "fields": fields}


def walk_out(address, path):
    flag, mask = EVENT_FLAG
    return {"address": address, "commands": [
        {"op": "09", "args": [0x80 | flag, mask]}] +
        [c for x, y in path for c in ({"op": "13", "args": [x * 2, y * 2]}, {"op": "14", "args": []})] +
        [{"op": "28", "args": []}, {"op": "16", "args": []}]}


def throne_script(native):
    """왕좌의 방 연출(왕의 인물 스크립트). native: dq4chapterbox 진입점 {이름: 3바이트}."""
    flag, mask = EVENT_FLAG
    lo, hi = lambda m: m & 0xFF, lambda m: m >> 8
    return {"address": "05:A84F", "commands": [
        {"op": "3F", "args": []},
        # 맵은 검은 채로 불러온다(dq4chapterbox 의 맵 훅). 상자 → 서술 → 맵을 밝힘
        {"op": "37", "args": native['box']},
        {"op": "21", "args": [lo(MSG_NARRATION), hi(MSG_NARRATION)]},
        {"op": "37", "args": native['reveal']},
        {"op": "21", "args": [lo(MSG_MINISTER), hi(MSG_MINISTER)]},
        {"op": "13", "args": [KING_DOWN[0] * 2, KING_DOWN[1] * 2]},
        {"op": "14", "args": []},
        {"op": "21", "args": [lo(MSG_KING), hi(MSG_KING)]},
        {"op": "10", "args": [flag, mask]},
        {"op": "40", "args": []},
        {"op": "16", "args": []}]}


def npc_doc(records, ported=(), prologue=False, report=None, ported_messages=(), chapter2=False):
    """ported·report·ported_messages: dq4npcport.port 의 인물 목록·보고·메시지. 왕좌의 방은 이 연출 배치로 바꾸고,
    report 가 있으면 1장 진행 사건(dq4ch1event)의 인물을 고친다. prologue 면 서장 맵의 인물을 더한다. chapter2 면
    1장 끝 서술 뒤 2장으로 옮기고, 아니면 끝맺음 서술과 끝 상자 뒤 타이틀로 돌아간다(1장까지의 배포판)."""
    native = {k: [v & 0xFF, v >> 8 & 0xFF, v >> 16] for k, v in dq4chapterbox.entry_points(scenes(prologue)).items()}
    flag, mask = EVENT_FLAG
    staff = [entry(STATIC, x, y, g, f, t) for x, y, g, f, t in STAFF]
    king = entry(STATIC, *KING_DOWN, KING, 'down', T_KING)
    easy = entry(STATIC, *EASY_AT, WARRIOR, 'up', T_EASY)
    # 연출은 왕이 돌린다. FC 에서도 연설 뒤 왕은 계단(10,0D)이 아니라 대신 옆 (10,13)에 서 있다
    lineup = [entry(HIDER if x <= 0x0F else HIDER2, x, y, WARRIOR, 'up', T_EASY) for x, y in LINEUP]
    before = [entry(SCRIPTED, *KING_AT, KING, 'down', T_KING),
              entry(STATIC, *MINISTER_AT, MINISTER, 'right', T_MINISTER), easy] + lineup + staff
    after = [king, entry(STATIC, *MINISTER_AT, MINISTER, 'right', T_MINISTER), easy] + staff + \
        [{**entry(STATIC, x, y, g, f, t), "time": "night"} for x, y, g, f, t in NIGHT_STAFF]
    scripts = [
        throne_script(native),
        # 주인공 통과(1C)를 켜면 주인공 옆 전사가 반 칸 어긋나 멈춰서(실측), 오른쪽 무리는 먼저 곧장 내려가
        # 가운데 선 주인공을 지나지 않게 한다.
        walk_out("05:A899", EXIT_LEFT),
        walk_out("05:A87B", EXIT_RIGHT),
    ]
    overrides = [{"map": THRONE, "flag": flag, "when": "on", "mask": mask, "list": "new:after"}] + \
        [{k: o[k] for k in ("map", "flag", "when", "mask", "list")} for o in records["overrides"]]
    lists = [{"map": THRONE, "entries": before}]
    new_lists = [{"name": "after", "entries": after}]
    if prologue:
        import dq4prologue
        more_lists, more_new, more_overrides, more_scripts = dq4prologue.npc_lists()
        lists += more_lists
        new_lists += more_new
        overrides = more_overrides + overrides
        scripts += more_scripts
    if report is not None:
        import dq4ch1event
        import dq4npcport
        ported, more_new, more_overrides = dq4ch1event.npc_lists(ported, report, event_talk())
        # 보스를 이긴 뒤의 왕좌의 방: 보고 전에는 병사들이 줄을 서고 왕이 말을 거는 목록(FC 1C:$8184), 보고 뒤에는
        # 왕이 대신 옆 (10,13)에 내려와 있는 목록
        king_report = entry(STATIC, *KING_DOWN, KING, 'down', dq4ch1event.talk_numbers(event_talk())['king'])
        new_lists.append({"name": "throne_report", "entries": [king_report] + after[1:]})
        new_lists.append({"name": "throne_return", "entries": dq4ch1event.throne_return(event_talk())})
        new_lists += more_new
        over = lambda flag, name: {"map": THRONE, "flag": flag[0], "when": "on", "mask": flag[1], "list": f"new:{name}"}  # noqa: E731
        overrides = more_overrides + [over(dq4ch1event.REPORTED, 'throne_report'),
                                      over(dq4ch1event.BOSS_WON, 'throne_return')] + overrides
        import dq4ch2event
        first = dq4npcport.FIRST_MESSAGE + len(ported_messages)
        if chapter2:
            scripts += dq4ch1event.scripts(first, dq4ch2event.native()[1]['transfer'])
        else:
            scripts += dq4ch1event.scripts(first, ending_at=dq4chapterbox.entry_points(scenes(prologue))['end'])
        ported, ch2_new, ch2_overrides = dq4ch2event.npc_lists(ported, chapter2_talk())
        new_lists += ch2_new
        overrides = ch2_overrides + overrides
        scripts += dq4ch2event.scripts(chapter2_message(first), dq4chapterbox.entry_points(scenes(prologue)))
    mine = {lst["map"] for lst in lists}
    return {"format": "dq5npcrelocate/1", "scripts": scripts,
            "lists": lists + [lst for lst in ported if "map" in lst and lst["map"] not in mine],
            "new_lists": new_lists, "overrides": overrides}


def scenes(prologue):
    """장 제목 상자로 시작하는 장면. 서장이 있으면 서장 지하가 먼저다."""
    scenes = dq4chapterbox.GAME_SCENES
    return scenes if prologue else tuple(s for s in scenes if s is not dq4chapterbox.PROLOGUE)


# 새 게임 첫 맵: 25:8621 의 6바이트 표([$BC][$BD][$C1][$C2][$C3][$198E])는 저장 재개 자리 표이고, 새 게임은
# 25:82D2 에서 항목 0 을 쓴다(실측: 원래 02/06 (38,14)).
START_TABLE = 0x258621
START_ORIG = bytes.fromhex('02 06 26 0e 01 80')
# DQ5 유년기는 필드 시간을 멈춘다(7E:2190 bit1, 00:82D3). 저장을 불러오면 00:A72A 가 bit6(청년기)이 꺼져 있을 때
# BRK 0C 로 다시 켜므로, 그 명령을 지워 FC 처럼 필드를 걸으면 밤이 오게 한다
# 저장·전멸 뒤 다시 시작 자리: 01:899F 는 칸 표 25:85D5 의 그룹을 이 표에서 찾고, 없으면 항목 0(새 게임 자리)으로
# 간다. 그룹 빌드가 칸 0~6 을 DQ4 그룹으로 바꾸므로 그대로면 교회에서 저장하거나 전멸해도 서장 지하로 돌아갔다(실측).
# 그래서 칸에서 빠진 DQ5 그룹의 항목 자리에 DQ4 그룹마다 FC 귀환 자리(1E:$A76D)의 첫 것을 쓴다
SLOT_TABLE, SLOT_COUNT = 0x2585D5, 0x16       # 25:857C 가 찾는 칸 수
FC_PLACES, FC_PLACE_COUNT = (0x1E, 0xA76D), 22
TIME_FREEZE = 0x00A738
TIME_FREEZE_ORIG = bytes.fromhex('00 0c 02 00')
# 롬 헤더 내부 제목(LoROM 7FC0, 21바이트, 남는 칸은 원본처럼 공백). 뒤 단계(곡·인물 그림)는 이 롬을 이어받아
# 체크섬만 다시 맞추므로 여기서 한 번 쓰면 된다
TITLE_OFFSET = 0x7FC0
TITLE_ORIG = b'DRAGONQUEST5'.ljust(21, b' ')
TITLE = b'DRAGONQUEST4'.ljust(21, b' ')


def lorom(addr):
    return (addr >> 16 & 0x7F) * 0x8000 + (addr & 0x7FFF)


def messages(ported_messages, report):
    """dq4npcport 의 일본어 메시지(3200 뒤에 덧붙임)에 1장 그룹 인물의 한글과 1장 메시지를 덮은 {번호: 부분 목록}.
    덧붙인 번호는 빈 번호 없이 이어야 하므로, 왕좌의 방을 이 연출 배치로 바꿔 쓰지 않게 된 메시지도 남긴다."""
    out = {m["id"]: m["codes"] for m in ported_messages}
    # 1장 그룹 인물(왕좌의 방은 이 연출 배치로 바꿈)의 일본어 원문을 FC 메시지 묶음으로 찾아 한글로
    import dq4ch1talk
    import dq4ch2talk
    korean = {**dq4ch1talk.TEXTS, **FRONT_TEXTS, **dq4ch2talk.TEXTS}
    for m, people in report.items():
        if m == THRONE:
            continue
        for person in people:
            key = tuple(x for x in person["shows"] if x is not None)
            if person.get("message") and key in korean:
                out[int(person["message"], 16)] = korean[key]
    import dq4sysmsg
    # 서장 메시지는 빌드에서 서장을 켜지 않아도 넣는다(메시지 단계에는 옵션이 없음)
    import dq4prologue
    import dq4ch1event
    import dq4npcport
    first = dq4npcport.FIRST_MESSAGE + len(ported_messages)
    events = dq4ch1event.texts(first)
    import dq4ch2event
    for name, texts in (('1장', TEXTS), ('서장', dq4prologue.TEXTS), ('시스템', dq4sysmsg.TEXTS),
                        ('1장 사건', events), ('2장', dq4ch2event.texts(chapter2_message(first)))):
        clash = set(out) & set(texts)
        if clash:
            raise ValueError(f'{name} 메시지와 겹치는 번호: {sorted(f"{m:03X}" for m in clash)}')
        out.update(texts)
    import dq4msgwait
    wait, keep = dq4msgwait.plan(**message_flow(first))
    return dq4msgwait.apply(out, wait, keep)


def message_flow(first_message):
    """메시지를 띄우는 대화·인물 스크립트·이벤트 스크립트(dq4msgwait.plan 의 인자). 서장은 늘 넣는다(메시지
    단계에는 서장 옵션이 없음). first_message 는 1장 사건 메시지의 첫 번호."""
    import dq4ch1event
    import dq4prologue
    points = dq4chapterbox.entry_points(scenes(True))
    native = {k: [v & 0xFF, v >> 8 & 0xFF, v >> 16] for k, v in points.items()}
    import dq4ch2event
    # 1장 끝 스크립트는 빌드 옵션(chapter2)으로 갈리지만 메시지 단계에는 옵션이 없어 두 판을 모두 본다
    ending = [s for s in dq4ch1event.scripts(first_message, ending_at=points['end'])
              if s['address'] == dq4ch1event.ENDER_SCRIPT]
    scripts = ([throne_script(native)] + dq4prologue.npc_lists()[3] +
               dq4ch1event.scripts(first_message, dq4ch2event.native()[1]['transfer']) + ending +
               dq4ch2event.scripts(chapter2_message(first_message), points))
    talks = ([s["body"] for s in dq4prologue.talk_doc()["scripts"]] + dq4ch1event.talk_scripts(first_message) +
             dq4ch2event.talk_scripts(chapter2_message(first_message)))
    _, at = dq4prologue.native()
    events = [dq4prologue.end_event(at), dq4ch2event.join_event(chapter2_message(first_message), dq4ch2event.native()[1]),
              dq4ch2event.altar_event(chapter2_message(first_message))]
    return {"talks": talks, "scripts": [s["commands"] for s in scripts], "events": events,
            "pauses": dq4ch1event.pauses(first_message)}


def chapter2_message(first_message):
    """2장 메시지의 첫 번호: 1장 사건 메시지 바로 뒤."""
    import dq4ch1event
    return first_message + len(dq4ch1event.MESSAGES)


def chapter2_talk():
    """2장 사건의 첫 대화 번호: 1장 사건 대화 바로 뒤."""
    import dq4ch1event
    return event_talk() + len(dq4ch1event.TALKS)


def event_talk():
    """1장 진행 사건의 첫 대화 번호: 덧붙인 대화에서 서장 스크립트 바로 뒤(dq4npcport.talk_doc)."""
    import dq4npcport
    import dq4prologue
    return dq4npcport.SCRIPT_TALK + len(dq4prologue.talk_doc()["scripts"])


def port(dq5, dq4):
    import dq4npcport
    return dq4npcport.port(dq5, dq4)


def messages_doc(dq5, dq4):
    _, ported, report = port(dq5, dq4)
    found = messages(ported, report)
    return {"format": "dq4messages/1", "messages": {f'{m:03X}': parts for m, parts in sorted(found.items())}}


def clear_mirror(data, original, ranges):
    """ranges [(시작, 끝)] 파일 위치 안의 거울 바이트(원본 20~2F 와 같은 값)를 0 으로. 0 도 거울도 아닌 바이트가
    있으면 멈춘다(다른 자료가 그 자리를 씀)."""
    d = bytearray(data)
    for lo, hi in ranges:
        for o in range(lo, hi):
            if d[o] and d[o] != original[o - 0x80000]:
                raise SystemExit(f'{o:#x}: 그룹 빌드 자리에 다른 자료가 있음')
            d[o] = 0
    return bytes(d)


def group_ranges():
    """clear_mirror 할 파일 위치 범위: 뱅크 3A~3F 전체, 인물 기본 목록 뱅크, 3A 밖의 새 맵 레코드 자리."""
    ranges = [(b * 0x8000, (b + 1) * 0x8000) for b in (*GROUP_BANKS, NPC_BANK)]
    ranges += [(lorom(lo), lorom(hi - 1) + 1) for lo, hi in RECORDS_AT if lo >> 16 not in GROUP_BANKS]
    return ranges


def owned_spans(groups, patches, env):
    """그룹 빌드 롬(groups)에서 1장 빌드가 같은 바이트여야 하는 파일 위치 범위: 얹은 패치의 30~3F 쓰기와, 쓰기에서
    잘린 앞뒤 0 까지 든 표의 끝(맵 포인터·속성 목록과 그룹 표의 0000, 들어가는 곳 표), 새 맵 레코드, 문 표 복사본 3B."""
    import dq4groupbuild
    from dq5map import Rom, group_spans, map_pointer
    from dq5newmap import entrance_table
    spans = []
    for path in patches:
        _, _, writes = load(str(path))
        spans += [(off, off + len(payload)) for off, payload, _, _ in writes
                  if 0x30 <= off // 0x8000 < 0x40 or off // 0x8000 == ENTRANCE_HOOK_BANK]
    rom = Rom(groups)
    for kind in ('pointer', 'attr'):
        found, table = group_spans(rom, kind=kind)
        bank = table & 0xFF0000
        spans.append((lorom(bank | found[0][0]), lorom(bank | found[-1][1] - 1) + 1))
        spans.append((lorom(table), lorom(table) + 2 * (len(found) + 1) + 2))
    count = len(group_spans(rom, kind='pointer')[0])
    spans.append((lorom(entrance_table(rom)), lorom(entrance_table(rom)) + 5 * count))
    records = dq4groupbuild.new_map_records(env)
    spans += [(lorom(map_pointer(rom, g, n)), lorom(map_pointer(rom, g, n)) + len(r)) for (g, n), r in records.items()]
    spans.append((0x3B * 0x8000, 0x3C * 0x8000))
    return spans, records


def verify_groups(out, groups, patches, env):
    """1장 롬이 그룹 빌드 롬과 그룹 빌드 자리에서 같고, 표·레코드가 읽히는지."""
    import dq4groupbuild
    from dq5map import Rom, group_spans
    from dq5newmap import entrance_table
    spans, records = owned_spans(groups, patches, env)
    for lo, hi in spans:
        if out[lo:hi] != groups[lo:hi]:
            at = next(o for o in range(lo, hi) if out[o] != groups[o])
            raise SystemExit(f'{at // 0x8000:02X}:{0x8000 + at % 0x8000:04X}: 그룹 빌드 롬과 다름 '
                             f'({out[at]:02X}, 그룹 빌드 {groups[at]:02X})')
    for kind in ('pointer', 'attr'):
        if group_spans(Rom(out), kind=kind) != group_spans(Rom(groups), kind=kind):
            raise SystemExit(f'{kind} 그룹 표가 그룹 빌드 롬과 다름')
    if entrance_table(Rom(out)) != entrance_table(Rom(groups)):
        raise SystemExit('들어가는 곳 표 자리가 그룹 빌드 롬과 다름')
    try:
        dq4groupbuild.check_records(out, records)
    except ValueError as error:
        raise SystemExit(str(error))


def apply_writes(data, original, paths):
    """dq5patch/1 목록들을 이미 4MB 로 늘린 롬 위에 얹는다. orig 가 있으면 확인하고, 없으면 0 이 아닌 자료를
    덮지 않는다. 타이틀 롬은 2MB 로 늘릴 때 30~3F 를 원본 20~2F 의 거울로 채우므로, 거울 그대로인 바이트는
    빈 자리로 본다."""
    d = bytearray(data)
    for path in paths:
        _, _, writes = load(str(path))
        for off, payload, orig, where in writes:
            if orig is not None:
                if bytes(d[off:off + len(orig)]) != orig:
                    raise SystemExit(f'{where}: 원래 바이트가 아님 {d[off:off + len(orig)].hex()}')
            else:
                for i, v in enumerate(payload):
                    o = off + i
                    mirror = 0x30 <= o // 0x8000 <= 0x3F and d[o] == original[o - 0x80000]
                    if d[o] and d[o] != v and not mirror:
                        raise SystemExit(f'{where}: 비어 있지 않은 자리 {o:#x} 를 덮음')
            d[off:off + len(payload)] = payload
    return bytes(d)


def run_tool(tool, *args):
    import dq4buildcache
    dq4buildcache.run(tool, *args, echo_stderr=True)


# 인물 목록은 30~3F 의 두 뱅크에 둬야 한다(데이터 뱅크를 목록 뱅크로 두고 낮은 WRAM 을 읽음). 타이틀 그림 자료는 42~47 에
# 있어 30 의 타이틀 코드 말고는 31~39 가 비고(원본 21~29 의 거울), 3A~3C 와 34:C000~ 는 그룹 연결(34 는 필드 지도, 아래
# FIELD_AT), 3D~3F 는 환경 맵이 쓴다. 기본 목록은 통째로 빈 35 에, 대체 목록은 38 에 둔다. 나머지 빈 뱅크는 새 맵
# 레코드(RECORDS_AT)가 쓴다.
NPC_BANK, NPC_ALT = 0x35, '38:8000'


def npc_base(env_patch):
    """기본 목록 자리: 환경 맵 레코드가 NPC_BANK 에서 끝난 다음 0x100 경계(닿지 않으면 그 뱅크 8000)."""
    _, _, writes = load(str(env_patch))
    end = max((off + len(payload) for off, payload, _, _ in writes if off // 0x8000 == NPC_BANK),
              default=NPC_BANK * 0x8000)
    at = (end + 0xFF) & ~0xFF
    return f'{NPC_BANK:02X}:{0x8000 + at % 0x8000:04X}'


# 입구별 도착 훅은 FC 그룹마다 필드로 나오는 칸을 고른다. 없으면 엔진이 보조 입구 (X, Y+1) 에 세우는데, 그 칸이
# 입구 블록의 다른 칸이다(dq4fieldport.cells). 대화 스크립트(talk)는 서장 스크립트와 옮긴 인물의 메시지 스크립트를
# 함께 덧붙인 것이다(dq4npcport.talk_doc). 서장을 빼도 넣는다: 옮긴 인물의 대화 번호가 서장 스크립트 뒤라서다.
GROUP_PATCHES = ('env/dq4-environment.dq5patch.json', 'doors.dq5patch.json', 'outside.dq5patch.json',
                 'newmap.dq5patch.json',
                 'exits.dq5patch.json', 'entrances.dq5patch.json', 'shops.dq5patch.json', 'inn.dq5patch.json',
                 'entrance-hook.dq5patch.json', 'field-gfx.dq5patch.json', 'field-blocks.dq5patch.json',
                 'field.dq5patch.json', 'talk.dq5patch.json', 'travel.dq5patch.json', 'names.dq5patch.json',
                 'companion-names.dq5patch.json', 'person-names.dq5patch.json',
                 'zones.dq5patch.json', 'grids.dq5patch.json', 'rates.dq5patch.json', 'chests.dq5patch.json')
# 원래 롬에서는 새 맵 레코드를 34 에 두지만 통합 롬의 34 는 필드 지도(34:C000~)가 쓰므로 3A 로 돌린다. 3A 가 차면 30 의
# 타이틀 코드·서곡 사이 빈 곳(메뉴 롬에서 0 이거나 원본 20 의 거울 그대로인 곳), 그다음 통째로 빈 31~33·34 앞쪽·36·37·39
# 로 간다. 그룹 빌드 안에서는 30:E000 의 필드 그림 패치 앞이다. 30:8000~8FFF 는 타이틀 코드(메뉴 준비
# 포함) 몫이라 뺐다. 필드 지도(덩어리 둘 약 12KB, 필드 로더의 DB 때문에 30~3F)가 34:C000 에 있고, 35 는 인물 기본
# 목록(NPC_BANK), 38 은 대체 목록(NPC_ALT)이 쓴다. 비어 있지 않으면 apply_writes 가 멈춘다.
RECORDS_AT = ((0x3A8000, 0x3B0000), (0x309000, 0x30A000), (0x30A900, 0x30E000), (0x318000, 0x320000),
              (0x328000, 0x330000), (0x338000, 0x340000), (0x348000, 0x34C000), (0x368000, 0x370000),
              (0x378000, 0x380000), (0x398000, 0x3A0000))
# 그룹 빌드는 늘린 뱅크가 0 인 원래 롬에서 패치를 만들고, dq5newmap 은 바탕과 같은 앞뒤 바이트(0)를 쓰지 않는다.
# 메뉴 롬의 30~3F 는 원본 20~2F 의 거울이라, 그대로 얹으면 표 끝의 0000 같은 바이트 자리에 거울 값이 남는다.
# 그래서 그룹 빌드가 쓰는 뱅크 3A~3F 와 레코드 자리의 거울 바이트를 먼저 0 으로 둔다.
GROUP_BANKS = range(0x3A, 0x40)
FIELD_AT = '34:C000'
ENTRANCE_HOOK_BANK = 0x5B        # 입구별 도착 훅(dq4groupbuild.ENTRANCE_HOOK_AT)의 뱅크. 그룹 빌드 롬과 같은지 볼 쓰기에 넣는다


def group_build(dq5, dq4, out):
    """통합 롬 자리로 돌린 dq4groupbuild.build. 그 안의 dq5build 가 패치끼리의 겹침을 거부한다."""
    import dq4groupbuild
    dq4groupbuild.RECORDS_AT = RECORDS_AT
    dq4groupbuild.FIELD_AT = FIELD_AT
    # 그룹 빌드의 인물·보행 대사 패치는 1장 빌드에 얹지 않지만(npc_doc 과 메뉴 빌드가 다시 만든다), 그룹 빌드 안에서
    # 32:C400~·36:9E00~ 레코드와 겹치지 않아야 한다.
    dq4groupbuild.NPC_AT = ('--base', '33:8000', '--alt', '38:8000')
    dq4groupbuild.TEXT_AT = ('--at', '60:8000')
    return dq4groupbuild.build(dq5, dq4, out)


def return_places(out, original, dq4):
    """다시 시작 자리 표(START_TABLE)에 칸 표의 DQ4 그룹 항목을 넣은 롬. 항목은 [그룹][맵][X][Y][층 1][80]."""
    import dq4groupbuild
    from kr_patch.fc import ines
    prg = ines.prg(dq4)
    o = lorom(SLOT_TABLE)
    now, before = set(out[o:o + SLOT_COUNT]), set(original[o:o + SLOT_COUNT])
    o = lorom(START_TABLE)
    rows = []
    while out[o + 6 * len(rows)] != 0xFF:
        rows.append(o + 6 * len(rows))
    have = {out[r] for r in rows}
    free = [r for r in rows if out[r] in before - now]
    place = dq4groupbuild.placement(prg)
    first = {}
    for i in range(FC_PLACE_COUNT):
        a = FC_PLACES[1] - 0x8000 + 5 * i + FC_PLACES[0] * 0x4000
        fc_group, fc_number, x, y = prg[a:a + 4]
        if (fc_group, fc_number) in place:
            group, number = place[fc_group, fc_number]
            first.setdefault(group, (number, *dq4groupbuild.cell(x, y)))
    need = sorted(g for g in now - have if g in first)
    if len(need) > len(free):
        raise SystemExit(f'다시 시작 자리 표에 빈 항목이 모자람: {len(need)} > {len(free)}')
    for g, r in zip(need, free):
        number, x, y = first[g]
        out[r:r + 6] = bytes((g, number, x, y, 1, 0x80))
    return out


def build(rom, dq5, dq4, work, prologue=True, chapter2=False):
    """메뉴 빌드 롬(dq4menupatch.py build --messages) → 1장 첫머리 롬. prologue 면 새 게임이 서장으로 시작해
    서장 끝에서 1장 첫머리로 넘어간다."""
    original = dq5.read_bytes()
    import dq4ch1event
    from kr_patch.fc import ines
    work.mkdir(parents=True, exist_ok=True)
    (work / 'boss.json').write_text(json.dumps(dq4ch1event.encounter_doc()))
    (work / 'learn.json').write_text(json.dumps(dq4ch1event.learn_doc()))
    (work / 'boss-monsters.json').write_text(json.dumps(dq4ch1event.monster_doc(ines.prg(dq4.read_bytes())),
                                                        ensure_ascii=False))
    # 원래 롬만 읽는 도구는 그룹 빌드와 함께 돌린다
    with ThreadPoolExecutor() as pool:
        side = [pool.submit(run_tool, DQ5_TOOLS / 'dq5npcrecord.py', dq5, 'dump', '-o', work / 'npc-records.json'),
                pool.submit(run_tool, DQ5_TOOLS / 'dq5encounterwrite.py', dq5, 'patch', work / 'boss.json',
                            '-o', work / 'boss.dq5patch.json'),
                pool.submit(run_tool, DQ5_TOOLS / 'dq5tables.py', dq5, 'patch', work / 'boss-monsters.json',
                            '-o', work / 'boss-monsters.dq5patch.json'),
                pool.submit(run_tool, DQ5_TOOLS / 'dq5learnwrite.py', dq5, 'patch', work / 'learn.json',
                            '-o', work / 'learn.dq5patch.json')]
        summary = group_build(dq5, dq4, work / 'groups')
        for f in side:
            f.result()
    ported, ported_messages, report = port(dq5, dq4)
    new_maps = [a for g, n in sorted(GROUPS.values()) for a in ('--new-map', f'{g:02X}/{n:02X}')]
    records = json.loads((work / 'npc-records.json').read_text())
    (work / 'npc.json').write_text(json.dumps(npc_doc(records, ported, prologue, report, ported_messages, chapter2), ensure_ascii=False, indent=1))
    base = npc_base(work / 'groups' / GROUP_PATCHES[0])
    run_tool(DQ5_TOOLS / 'dq5npcrelocate.py', dq5, 'patch', work / 'npc.json', '--base', base, '--alt', NPC_ALT,
             '--allow-growth', *new_maps, '-o', work / 'npc.dq5patch.json')
    patches = [work / 'groups' / p for p in (*GROUP_PATCHES, *summary['record_patches'])] + [
        work / 'npc.dq5patch.json', work / 'boss.dq5patch.json', work / 'boss-monsters.dq5patch.json',
        work / 'learn.dq5patch.json']
    out = bytearray(apply_writes(clear_mirror(rom, original, group_ranges()), original, patches))
    import dq4menupatch
    out = bytearray(dq4chapterbox.apply(out, dq4.read_bytes(), dq4menupatch.Font('galmuri11'), scenes(prologue)))
    out = bytearray(dq4ch1event.apply(out))
    import dq4ch2event
    import dq4npcport
    out = bytearray(dq4ch2event.apply(out, original,
                                      chapter2_message(dq4npcport.FIRST_MESSAGE + len(ported_messages))))
    import dq4josa
    out = bytearray(dq4josa.apply(out))
    import dq4msgnames
    out = bytearray(dq4msgnames.apply(out))
    o = lorom(START_TABLE)
    if out[o:o + 6] != START_ORIG:
        raise SystemExit(f'{START_TABLE:06X}: 새 게임 첫 맵 표가 원래 값이 아님 {out[o:o + 6].hex()}')
    o = lorom(TIME_FREEZE)
    if out[o:o + 4] != TIME_FREEZE_ORIG:
        raise SystemExit(f'{TIME_FREEZE:06X}: 시간 멈춤 명령이 원래 값이 아님 {out[o:o + 4].hex()}')
    out[o:o + 4] = b'\xea' * 4
    o = lorom(START_TABLE)
    start = START
    if prologue:
        import dq4prologue
        out = bytearray(dq4prologue.apply(out))
        start = dq4prologue.START
    group, number = (int(v, 16) for v in start[0].split('/'))
    out[o:o + 4] = bytes((group, number, start[1], start[2]))
    out = bytearray(return_places(out, original, dq4.read_bytes()))
    if out[TITLE_OFFSET:TITLE_OFFSET + 21] != TITLE_ORIG:
        raise SystemExit(f'{TITLE_OFFSET:06X}: 내부 제목이 원래 값이 아님 {bytes(out[TITLE_OFFSET:TITLE_OFFSET + 21])!r}')
    out[TITLE_OFFSET:TITLE_OFFSET + 21] = TITLE
    out = set_checksum(out)
    group_patches = [work / 'groups' / p for p in (*GROUP_PATCHES, *summary['record_patches'])]
    verify_groups(bytes(out), (work / 'groups' / 'groups.sfc').read_bytes(), group_patches, work / 'groups' / 'env')
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    m = sub.add_parser('messages', help='dq4menupatch.py build --messages 에 줄 메시지 JSON')
    m.add_argument('-o', '--out', required=True, type=Path)
    m.add_argument('--dq5', default='rom/dq5.sfc', type=Path)
    m.add_argument('--dq4', default='rom/dq4.nes', type=Path)
    b = sub.add_parser('build')
    b.add_argument('--rom', required=True, type=Path, help='dq4menupatch.py build --messages 결과')
    b.add_argument('--dq5', default='rom/dq5.sfc', type=Path)
    b.add_argument('--dq4', default='rom/dq4.nes', type=Path)
    b.add_argument('--out', required=True, type=Path)
    b.add_argument('--keep', type=Path, help='중간 패치 목록을 남길 폴더')
    b.add_argument('--no-prologue', action='store_true', help='NDS 서장(dq4prologue.py) 없이 새 게임을 1장으로 시작')
    b.add_argument('--chapter2', action='store_true',
                   help='1장 끝에서 2장으로 넘어감(기본은 끝맺음 서술·끝 상자 뒤 타이틀로, 1장까지의 배포판)')
    args = ap.parse_args()
    if args.cmd == 'messages':
        args.out.parent.mkdir(parents=True, exist_ok=True)
        doc = messages_doc(args.dq5, args.dq4)
        args.out.write_text(json.dumps(doc, ensure_ascii=False, indent=1))
        print(f'{args.out} 메시지 {len(doc["messages"])}개')
        return
    rom = args.rom.read_bytes()
    if args.keep:
        args.keep.mkdir(parents=True, exist_ok=True)
        out = build(rom, args.dq5, args.dq4, args.keep, not args.no_prologue, args.chapter2)
    else:
        with tempfile.TemporaryDirectory() as t:
            out = build(rom, args.dq5, args.dq4, Path(t), not args.no_prologue, args.chapter2)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(out)
    args.out.with_suffix('.ips').write_bytes(ips_patch(rom, out))
    print(f'{args.out} sha1={hashlib.sha1(out).hexdigest()}')


if __name__ == '__main__':
    main()
