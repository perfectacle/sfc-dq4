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
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
DQ5_TOOLS = HERE.parents[1] / 'dq5' / 'tools'
sys.path[:0] = [str(HERE), str(DQ5_TOOLS)]

from dq4environmentrom import GROUPS  # noqa: E402
from dq4romassets import ips_patch, set_checksum  # noqa: E402
from dq5build import load  # noqa: E402

LINE, END, PAGE, SPEAK, NARR, HERO = 0x1000, 0x1001, 0x1002, 0x1003, 0x1006, 0x1012
Q = 0x363      # 「 (DQ5 글자)
DOTS = 0x366   # …

EVENT_FLAG = (0x0E, 0x04)       # 7E:219E & 04. 원래 태어나는 장면이 켜는 비트라 새 게임 첫 맵에서는 꺼져 있다
# バトランド 성 FC 02/01(왕좌)·02/00(성 앞)이 놓인 DQ5 맵
THRONE, FRONT = (f'{g:02X}/{n:02X}' for g, n in (GROUPS['02-01'], GROUPS['burland']))
START = (THRONE, 32, 42)       # FC (10,15): 줄 선 전사들 사이의 빈 자리

# 연출 메시지: 태어나는 장면 메시지 자리(시작 지점을 바꿔 나오지 않음)
MSG_NARRATION, MSG_MINISTER, MSG_KING = 0x1D1, 0x1D2, 0x1D3


# DQ5 메시지 창은 한 쪽에 4줄, 한 줄은 ＊「·들여쓰기 2칸 뒤 한글 14자까지(실측: 15자째에서 넘쳐 깨짐).
# 한 쪽이 4줄을 넘으면 쪽 넘김 없이 밀려 올라가다 빈 창이 남았다(실측).
PAGE_LINES, LINE_COLS, NAME_COLS = 4, 14, 4
NAME = '@'      # 대사 문자열 안의 주인공 이름 자리({1012}). 이름 입력은 네 글자까지


def _width(word):
    return sum(NAME_COLS if c == NAME else 1 for c in word)


def _wrap(text, first):
    """'/' 로 나눈 줄, 없으면 낱말 단위로 나눈다. first 는 첫 줄에서 말하는 이 이름이 더 차지하는 칸."""
    lines, cur = [], ''
    if '/' in text:
        lines = text.split('/')
        cur = lines.pop()
    for w in ([] if lines or '/' in text else text.split(' ')):
        room = LINE_COLS - (first if not lines else 0)
        cand = w if not cur else cur + ' ' + w
        if cur and _width(cand) > room:
            lines.append(cur)
            cur = w
        else:
            cur = cand
    lines.append(cur)
    for n, line in enumerate(lines):
        if _width(line) > LINE_COLS - (first if n == 0 else 0):
            raise ValueError(f'한 줄에 안 들어감: {line}')
    return lines


def _codes(line):
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


def _message(pages, prefix=()):
    """pages: 쪽마다 문장. 줄이 4줄을 넘으면 쪽을 더 나눈다."""
    out = []
    first = max(0, len(prefix[1]) + 1 - 2) if prefix else 0
    for text in pages:
        lines = _wrap(text, first)
        if prefix and len(lines) > PAGE_LINES:
            # 쪽을 더 나누면 말하는 이 이름이 다시 붙는데, 그 줄의 너비는 이름 없이 셈했다
            raise ValueError(f'말하는 이가 있는 쪽은 {PAGE_LINES}줄까지: {text}')
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
    """서술문({1006}): ＊「 도 들여쓰기도 없다. 줄 너비는 대사와 같은 14칸으로 둔다. 서술은 해라체(「~다.」)로 쓴다."""
    out = [NARR]
    for part in _message(pages):
        out.append(part)
        if part == PAGE:        # 쪽이 바뀌면 첫 코드를 다시 본다(실측: 빼면 ＊「 가 붙음)
            out.append(NARR)
    return out


TEXTS = {
    # FC 는 검은 화면에 장 제목 상자(dq4chapterbox.py)를 띄운 뒤, 검은 화면의 메시지 창에 이 서술을 쓴다
    MSG_NARRATION: narrate('이것은 바트랜드라는/작은 나라의 왕궁 전사의/이야기다.',
                           '@, 즉 당신도/그 왕궁 전사의/한 사람이었다.',
                           '어느 날 아침, 임금님은/전사들을 성의 넓은 방에/불러 모았다……'),
    MSG_MINISTER: speak('대신', '이제부터 임금님께서/그대들에게 하실 말씀이/있다. 명심하여 듣도록.'),
    MSG_KING: speak('왕',
                    '모두 편히 하라.',
                    '요즘 아이들이/사라진다는 소문은/그대들도 들었으리라.',
                    '오늘 아침에도/이무르 마을에서/어머니들이 눈물로/호소하러 왔노라.',
                    '이 나라의 왕으로서/더는 두고 볼 수 없노라.',
                    '일의 진상을 밝혀/이 짐에게 보고하라!/가라! 나의 전사들이여!'),
}

# 대화 번호 T(26D 이상)는 메시지 T + 3C6 을 띄운다. 300 부터 차례로 쓴다. 덮는 자리는 DQ5 마을 대사라, 그 마을에 가면
# 이 대사가 나온다(이 첫머리에서는 가지 않음)
TALK_BASE = 0x300
_talks = []


def talk(parts):
    t = TALK_BASE + len(_talks)
    _talks.append(parts)
    TEXTS[t + 0x3C6] = parts
    return t


T_KING = talk(say('그대의 활약을 기대하고/있노라, @여.'))
T_MINISTER = talk(say('자, 무얼 하는가./어서 가지 않고.'))
T_EASY = talk(say('뭐, 느긋하게/하자고, @.'))
T_MOTHER = talk(say('전사님!/부디 저희 아이를/찾아 주세요!', '그 아이는 살아 있어요./저는 알 수 있어요.'))
T_GATE1 = talk(say('여기는 바트랜드 성.'))
T_SCHOLAR = talk(say('@ 공인가./아니, 마음에 걸리는 것이/있어서 조금/조사하고 있다네.'))
T_GATE2 = talk(say('수상한 자는 한 발짝도/들이지 않겠다!'))
T_NIGHT = talk(say('마을 밖으로 나가/계속 걷다 보면/이윽고 밤이 될 것입니다.'))
T_CHILD = talk(say('괴물은 옛날부터 있었지만/요즘 들어 아이들이/모습을 감추기 시작했다./무슨 일이 있는 걸까?'))
T_INN = talk(say('@ 공./싸우다 다치거든/마을로 돌아가/여관에 묵도록 하시오.'))
T_RIVAL = talk(say('여어, @!/아직도 여기서 어정대다니/여전히 굼뜨구먼.', '다른 녀석들은 이무르/마을로 간 거 아니었어?'))
T_MAID = talk(say('@ 님. 부디 다른/전사들에게 뒤지지 않도록/힘내 주세요.'))
T_DAYTIME = talk(say('예전엔 밤에만 나오던/마물이 낮에도 나온다지./뒤숭숭한 세상이구먼.'))
T_IMURU = talk(say('저희는 이무르 마을에서/왔습니다.'))
T_HERB = talk(say('긴 여행이 될 것 같으면/마을에서 약초를/사 가시오.'))

# 성 앞(36/00)은 dq4npcport.py 가 FC 인물을 놓고 일본어 원문을 둔다. 그 가운데 옮긴 것은 FC 메시지 묶음으로 찾아
# 같은 DQ5 메시지 번호의 글을 한글로 바꾼다.
FRONT_TEXTS = {
    (0x78C,): say('@ 공! 알고 있소?', '잠기지 않은 문도 있어서/열쇠 없이 열 수 있다네!'),
    (0x5E3, 0x5E4): say('괴물이라도 마을 안까지는/들어오지 못해요.', '그럼 왜 아이들이/없어지는 걸까요……'),
    (0x5E1,): say('바트랜드 왕은/사람이 좋아서/이 나라는 세금도 싸지.', '하지만 그만큼/무기나 방어구에도/돈을 못 들이는 거야.',
                  '더 강한 무기가 필요하면/스스로 돈을 모아/바꿔 사는 게 좋을걸.', '새 무기나 방어구를 사면/다시 장비하는 걸/잊지 말라고!'),
    (0x5E2,): say('이 성에서 서쪽 동굴을/빠져나가 바닷가를 따라/가면 이무르 마을이에요.'),
    (0x5E5,): say('이무르 마을에 가면/뭔가 알 수 있을지도/모르겠네요.'),
    (0x78D,): say('저는 프레아./남편 알렉스가 여행을/떠난 채 돌아오지 않아요.', '전사님! 여행길에 혹시/알렉스를 보시거든/알려 주세요!'),
    (0x5E0,): say('여기는 바트랜드의/성 아래 마을입니다.'),
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
KING_AT = (0x10, 0x0D)
# 연설이 끝나면 전사들이 두 줄로 아래 출구 (0F~10,23)까지 걸어가 빠진다(FC 인물 블록 레코드 12~19 와 같은 길).
# 한 줄로 몰면 통로에서 서로 막혀 멈췄다(실측).
EXIT_LEFT = [(0x0F, 0x1A), (0x0F, 0x23)]
EXIT_RIGHT = [(0x11, 0x1A), (0x10, 0x1A), (0x10, 0x23)]
KING_DOWN = (0x10, 0x13)       # 연설하러 내려와 서는 곳(FC 연출 뒤 화면)
MINISTER_AT = (0x0F, 0x13)
EASY_AT = (0x0E, 0x15)          # 연출 뒤에도 남는 전사
LINEUP = [(0x11, 0x17), (0x0F, 0x15), (0x11, 0x15), (0x0E, 0x17), (0x0F, 0x17), (0x10, 0x17)]

STATIC = {"list": "05:8E43", "index": 0}       # 03/00 의 스크립트 없는 인물
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


def npc_doc(records, ported=()):
    """ported: dq4npcport.port 의 인물 목록. 왕좌의 방만 이 연출 배치로 바꾼다."""
    import dq4chapterbox
    native = {k: [v & 0xFF, v >> 8 & 0xFF, v >> 16] for k, v in dq4chapterbox.entry_points().items()}
    flag, mask = EVENT_FLAG
    staff = [entry(STATIC, x, y, g, f, t) for x, y, g, f, t in STAFF]
    king = entry(STATIC, *KING_AT, KING, 'down', T_KING)
    easy = entry(STATIC, *EASY_AT, WARRIOR, 'up', T_EASY)
    # 연출은 왕이 돌린다. FC 에서도 연설 뒤 왕은 계단(10,0D)이 아니라 대신 옆 (10,13)에 서 있다
    lineup = [entry(HIDER if x <= 0x0F else HIDER2, x, y, WARRIOR, 'up', T_EASY) for x, y in LINEUP]
    before = [entry(SCRIPTED, *KING_AT, KING, 'down', T_KING),
              entry(STATIC, *MINISTER_AT, MINISTER, 'right', T_MINISTER), easy] + lineup + staff
    after = [king, entry(STATIC, *MINISTER_AT, MINISTER, 'right', T_MINISTER), easy] + staff
    lo, hi = lambda m: m & 0xFF, lambda m: m >> 8
    scripts = [
        {"address": "05:A84F", "commands": [
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
            {"op": "16", "args": []}]},
        # 주인공 통과(1C)를 켜면 주인공 옆 전사가 반 칸 어긋나 멈춰서(실측), 오른쪽 무리는 먼저 곧장 내려가
        # 가운데 선 주인공을 지나지 않게 한다.
        walk_out("05:A899", EXIT_LEFT),
        walk_out("05:A87B", EXIT_RIGHT),
    ]
    overrides = [{"map": THRONE, "flag": flag, "when": "on", "mask": mask, "list": "new:after"}] + \
        [{k: o[k] for k in ("map", "flag", "when", "mask", "list")} for o in records["overrides"]]
    return {"format": "dq5npcrelocate/1", "scripts": scripts,
            "lists": [{"map": THRONE, "entries": before}] + [lst for lst in ported if lst["map"] != THRONE],
            "new_lists": [{"name": "after", "entries": after}],
            "overrides": overrides}


# 새 게임 첫 맵: 25:8621 의 6바이트 표([$BC][$BD][$C1][$C2][$C3][$198E])는 저장 재개 자리 표이고, 새 게임은
# 25:82D2 에서 항목 0 을 쓴다(실측: 원래 02/06 (38,14)).
START_TABLE = 0x258621
START_ORIG = bytes.fromhex('02 06 26 0e 01 80')


def lorom(addr):
    return (addr >> 16 & 0x7F) * 0x8000 + (addr & 0x7FFF)


def messages(lists, ported_messages, report):
    """dq4npcport 의 일본어 메시지에 성 앞의 한글과 1장 메시지를 덮은 {번호: 부분 목록}. 왕좌의 방은 이 연출 배치로
    바꾸므로 그 방 인물만 쓰던 메시지는 뺀다."""
    used = {e["fields"]["talk"] + 0x3C6 for lst in lists if lst["map"] != THRONE for e in lst["entries"]}
    out = {m["id"]: m["codes"] for m in ported_messages if m["id"] in used}
    for person in report.get(FRONT, []):
        key = tuple(m for m in person["shows"] if m is not None)
        if key in FRONT_TEXTS:
            out[int(person["message"], 16)] = FRONT_TEXTS[key]
    import dq4sysmsg
    for name, texts in (('1장', TEXTS), ('시스템', dq4sysmsg.TEXTS)):
        clash = set(out) & set(texts)
        if clash:
            raise ValueError(f'{name} 메시지와 겹치는 번호: {sorted(f"{m:03X}" for m in clash)}')
        out.update(texts)
    return out


def port(dq5, dq4):
    import dq4npcport
    return dq4npcport.port(dq5, dq4)


def messages_doc(dq5, dq4):
    lists, ported, report = port(dq5, dq4)
    found = messages(lists, ported, report)
    return {"format": "dq4messages/1", "messages": {f'{m:03X}': parts for m, parts in sorted(found.items())}}


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


def run_tool(*args):
    subprocess.run([sys.executable, *map(str, args)], check=True, stdout=subprocess.DEVNULL)


# 인물 목록은 30~3F 의 두 뱅크에 둬야 한다(데이터 뱅크를 목록 뱅크로 두고 낮은 WRAM 을 읽음). 30~39 는 타이틀,
# 3A~3C 는 그룹 연결, 3D~3F 는 환경 맵이 쓴다. 남는 곳은 환경 맵 레코드 뒤 3F 와, 타이틀 layer-payload 가
# 39:8220 에서 끝난 뒤의 39(원본 29 의 거울)다.
NPC_BANK, NPC_ALT = 0x3F, '39:9000'


def npc_base(env_patch):
    """기본 목록 자리: 환경 맵 레코드가 3F 에서 끝난 다음 0x100 경계. 환경 맵이 늘면 따라 밀린다."""
    _, _, writes = load(str(env_patch))
    end = max(off + len(payload) for off, payload, _, _ in writes if off // 0x8000 == NPC_BANK)
    at = (end + 0xFF) & ~0xFF
    return f'{NPC_BANK:02X}:{0x8000 + at % 0x8000:04X}'


GROUP_PATCHES = ('env/dq4-environment.dq5patch.json', 'newmap.dq5patch.json', 'exits.dq5patch.json',
                 'entrances.dq5patch.json', 'shops.dq5patch.json', 'inn.dq5patch.json')


def build(rom, dq5, dq4, work):
    """메뉴 빌드 롬(dq4menupatch.py build --messages) → 1장 첫머리 롬."""
    import dq4groupbuild
    original = dq5.read_bytes()
    # 원래 롬에서는 새 맵 레코드를 34 에 두지만 통합 롬의 34 는 타이틀 자료다
    dq4groupbuild.NEWMAP_AT = tuple('3A:8000' if a == '34:8000' else a for a in dq4groupbuild.NEWMAP_AT)
    dq4groupbuild.build(dq5, dq4, work / 'groups')
    ported, _, _ = port(dq5, dq4)
    new_maps = [a for g, n in sorted(GROUPS.values()) for a in ('--new-map', f'{g:02X}/{n:02X}')]
    run_tool(DQ5_TOOLS / 'dq5npcrecord.py', dq5, 'dump', '-o', work / 'npc-records.json')
    records = json.loads((work / 'npc-records.json').read_text())
    (work / 'npc.json').write_text(json.dumps(npc_doc(records, ported), ensure_ascii=False, indent=1))
    base = npc_base(work / 'groups' / GROUP_PATCHES[0])
    run_tool(DQ5_TOOLS / 'dq5npcrelocate.py', dq5, 'patch', work / 'npc.json', '--base', base, '--alt', NPC_ALT,
             '--allow-growth', *new_maps, '-o', work / 'npc.dq5patch.json')
    out = bytearray(apply_writes(rom, original, [work / 'groups' / p for p in GROUP_PATCHES] +
                                 [work / 'npc.dq5patch.json']))
    import dq4chapterbox
    import dq4menupatch
    out = bytearray(dq4chapterbox.apply(out, dq4.read_bytes(), dq4menupatch.Font('galmuri11')))
    import dq4josa
    out = bytearray(dq4josa.apply(out))
    import dq4msgnames
    out = bytearray(dq4msgnames.apply(out))
    o = lorom(START_TABLE)
    if out[o:o + 6] != START_ORIG:
        raise SystemExit(f'{START_TABLE:06X}: 새 게임 첫 맵 표가 원래 값이 아님 {out[o:o + 6].hex()}')
    group, number = (int(v, 16) for v in START[0].split('/'))
    out[o:o + 4] = bytes((group, number, START[1], START[2]))
    return set_checksum(out)


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
        out = build(rom, args.dq5, args.dq4, args.keep)
    else:
        with tempfile.TemporaryDirectory() as t:
            out = build(rom, args.dq5, args.dq4, Path(t))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(out)
    args.out.with_suffix('.ips').write_bytes(ips_patch(rom, out))
    print(f'{args.out} sha1={hashlib.sha1(out).hexdigest()}')


if __name__ == '__main__':
    main()
