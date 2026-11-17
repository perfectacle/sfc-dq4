"""동료 대화(はなす): 앞에 아무도 없을 때 「はなす」를 고르면 조건이 맞는 동료의 대사를 띄운다(NDS 리메이크의 동료 대화).
훅·조건 평가 루틴·표는 이 2장 모듈 하나가 갖고, 3장 줄은 3장 모듈 dq4ch3partytalk 이 내놓아 같은 표에 합친다(같은
「はなす」 훅을 두 모듈이 덮을 수 없음). 3장 대사 메시지는 3장 모듈의 것이라 3장 메시지 번호로 들어간다.

DQ5 의 「はなす」는 앞에 말 상대가 없으면 05:D5B9 에서 대화 창을 열고 메시지 129「その方向には誰もいない。」를 띄운다.
창 열기와 메시지(05:D5B9~D5BE)를 뱅크 05 받침으로 돌려, 받침이 창을 연 뒤 이 모듈의 네이티브가 지금 맵의 대사 목록에서 조건이 맞는 줄을 하나 고른다. 맞는
줄이 없으면 원래처럼 129 를 띄운다. 형식은 sfc/dq4/docs/dq4-chapter2-format.md 「동료 대화」.

대사 줄은 NDS 2장 동료 대화 표에서 옮긴 dq4ch2partytalk.tsv(dq4ch2partytalknds.py 가 만듦)와 한글 대사
dq4ch2partytalk-text.tsv 를 읽어 LINES·MESSAGES 로 만든다.

「방금 말을 건 마을 사람」 조건: 대화 시작(06:AF6A)에 건 훅이 말을 건 인물의 대화 번호를 이 모듈의 번호 표에서 찾아
그 차례 + 1(없으면 0)을 7E:21FD 에 적는다. 줄의 조건은 그 값이 들어 있어야 하는 번호 묶음이다. 어느 인물이 어느 대화
번호인지는 빌드가 인물 목록을 만들 때(npc_lists) 짝 표 dq4ch2partytalk-people.tsv 의 맵·칸·낮밤으로 모은다.
"""
from dataclasses import dataclass
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4chapter1 as ch1  # noqa: E402
import dq4ch2event as ch2  # noqa: E402
import dq4ch2endor as endor  # noqa: E402
import dq4ch2frenol as frenol  # noqa: E402
import dq4ch2king as king  # noqa: E402
import dq4ch2tempe as tempe  # noqa: E402
from dq4chapter1 import speak  # noqa: E402
from dq4environmentrom import _Asm  # noqa: E402
from dq4ch3slots import VARS_AT as _VARS_AT  # noqa: E402

# 「はなす」의 앞에 아무도 없는 갈래(05:D5AE 의 12:FD9B 가 캐리를 내린 뒤): 05:D5B9 BRK 95 00(대화 창) / BRK 98 29(메시지
# 129) / 05:D5BF BRK 09 0A / A 를 기다림 / RTS. D5BF 이하는 05:D817(ならびかえ)도 JSR 로 부르므로 건드리지 않고, 앞 두 BRK
# (6바이트)만 뱅크 05 의 받침으로 가는 JSR 로 바꾼다. BRK 처리기는 DB 를 BRK 가 놓인 뱅크로 두므로, 창 열기 BRK 는 낮은
# WRAM 거울이 있는 뱅크 05 의 받침에 둔다(뱅크 5C 에서는 낮은 WRAM 대신 롬을 읽음)
HOOK_AT = 0x05D5B9
HOOK_ORIG = bytes.fromhex('009500' '009829')
STUB_AT = 0x05FEE8             # 원래 롬의 빈 자리. 받침: BRK 95 00 / JSL talk / RTS
STUB_LEN = 8
NOBODY = 0x129
# 마지막으로 고른 줄(지금 맵 목록의 차례 + 1). 같은 우선순위의 맞는 줄이 여럿이면 다음 「はなす」에 그다음 줄을 고른다
LAST = (0x6E, 0xFF)            # 7E:21FE(바이트 값)
# 마지막으로 말을 건 인물: 번호 표(native 의 ids)의 차례 + 1, 표에 없는 인물이면 0. 맵을 옮겨도 그대로다(같은 대화
# 번호는 같은 대사라 다른 맵에서 맞아도 그 대사를 들은 뒤다)
TALKED_TO = (0x6D, 0xFF)       # 7E:21FD(바이트 값)
FLAGS = ()
# 대화 시작 06:AF62 의 LDX $0F1E(말 상대 슬롯) / LDA $7E36E0,X(대화 번호 아래). 06:AF20(스크립트가 거는 대화)은
# 이 길을 지나지 않는다
TALK_HOOK_AT = 0x06AF6A
TALK_HOOK_ORIG = bytes.fromhex('ae1e0f' 'bfe0367e')
MAX_IDS = 0xFE
IDS_OPERAND = 28                # talked 루틴 첫 바이트에서 번호 표를 읽는 LDA long,X 까지

MESSAGE_AT = 0x248157          # 보행 메시지(A = 번호). BRK 97+n 처리기가 부르는 것과 같음
NIGHT_TEST = 0x218000          # 캐리 = 밤(7E:075E >= F0)

# 말하는 인물: 일행 기록 +0 의 인물 번호(아리나는 주인공 기록 틀 0, 두 사람은 dq4ch2event.RECRUITS)
ALENA, KIRYL, BREY = 0x00, ch2.RECRUITS[0]['person'], ch2.RECRUITS[1]['person']
FIELD = 'field'                # 필드(7E:00BE bit7 꺼짐). 필드에서도 7E:00BC·00BD 는 떠난 맵 번호라 따로 둔다
FIELD_KEY = (0xFE, 0xFE)
TIMES = {'any': 0, 'day': 1, 'night': 2}
# 조건 종류(3바이트: 종류, 값 1, 값 2). HAVE·LACK 은 값 1 의 물건을 일행(7E:201D 명)의 가진 물건이나 맡긴 물건에
# 누가 가짐·아무도 안 가짐, VAR 는 3장 변수 칸(dq4ch3slots.VARS_AT + 값 1)의 바이트 = 값 2
ON, OFF, EQUAL, LEAD, WITH, WITHOUT, TALKED, HAVE, LACK, VAR = 1, 2, 3, 4, 5, 6, 7, 8, 9, 10
PARTY_ITEMS = 0x7E2056         # 일행 기록(7E:2040, 42바이트씩)의 가진 물건 12칸(빈 칸 FF)
BAG = 0x7E2250                 # 맡긴 물건(물건 번호마다 개수)
RECORD, ITEM_SLOTS = 42, 12
VARS_AT = _VARS_AT


@dataclass(frozen=True)
class Line:
    """대사 줄 하나. 말하는 인물(speaker)이 걷는 줄에 있고 HP 가 0 이 아니어야 하고, 나머지 조건이 모두 맞아야 한다.
    우선순위는 작을수록 먼저다(NDS 표 +28 과 같은 뜻): 맞는 줄 가운데 가장 작은 우선순위의 것만 고른다."""
    map: str                   # 'GG/MM' 또는 FIELD
    speaker: int
    message: str               # MESSAGES 의 이름
    priority: int = 7
    time: str = 'any'          # 'any' 'day' 'night'
    on: tuple = ()             # 켜져 있어야 하는 flag ((번호, 마스크), …), 7E:2190 + 번호
    off: tuple = ()            # 꺼져 있어야 하는 flag
    equal: tuple = ()          # 바이트 값 ((번호, 값), …)
    lead: int = None           # 선두 인물
    with_: tuple = ()          # 걷는 줄에 있어야 하는 인물
    without: tuple = ()        # 걷는 줄에 없어야 하는 인물
    talked: tuple = ()         # 방금 말을 건 인물(짝 표의 「NDS 맵:인물 번호」, 3장은 dq4ch3partytalk 의 이름)
    nds: int = None            # 옮겨 온 NDS 동료 대화 레코드 번호(그 장의 표)
    have: tuple = ()           # 누가 가져야 하는 물건 번호
    lack: tuple = ()           # 아무도 갖지 않아야 하는 물건 번호
    var: tuple = ()            # 3장 변수 칸 바이트 값 ((오프셋, 값), …)

    def conditions(self, talk_set=0):
        """talk_set: talked 의 번호 묶음 주소(뱅크 안 16비트)."""
        return ([(ON, i, m) for i, m in self.on] + [(OFF, i, m) for i, m in self.off] +
                [(EQUAL, i, v) for i, v in self.equal] + ([(LEAD, self.lead, 0)] if self.lead is not None else []) +
                [(WITH, p, 0) for p in self.with_] + [(WITHOUT, p, 0) for p in self.without] +
                [(HAVE, i, 0) for i in self.have] + [(LACK, i, 0) for i in self.lack] +
                [(VAR, o, v) for o, v in self.var] +
                ([(TALKED, talk_set & 0xFF, talk_set >> 8)] if self.talked else []))


def _pair(*parts):
    """두 사람이 이어 말하는 한 메시지: speak(…) 둘을 쪽 넘김으로 잇는다."""
    out = []
    for p in parts:
        out += ([ch1.PAGE] if out else []) + p[:-1]
    return out + [ch1.END]


# 줄 표(LINES_TSV)의 이름. 조건 이름은 NDS 이야기 flag 를 옮긴 SFC flag(dq4ch2partytalknds.STORY)
SPEAKERS = {'ALENA': (ALENA, '아리나'), 'KIRYL': (KIRYL, '크리프트'), 'BREY': (BREY, '브라이')}
CONDITIONS = {
    'CHAPTER2': ch2.CHAPTER2, 'JOINED': ch2.JOINED, 'TEMPE_HEARD': ch2.TEMPE_HEARD, 'WON': tempe.WON,
    'KIDNAPPED': frenol.KIDNAPPED,
    'BRACELET': (frenol.CHEST_OPEN[0] - 0x2190, frenol.CHEST_OPEN[1]),     # 남쪽 동굴 황금의 팔찌 상자가 열림
    'RESCUED': frenol.RESCUED, 'BAZAAR': king.BAZAAR, 'HEARD': king.HEARD, 'GOT': king.GOT, 'CURED': king.CURED,
    'CHAMPION': endor.CHAMPION, 'MESSENGER': endor.MESSENGER,
}
# 2장 진행 단계(앞 단계 flag 를 모두 켠 채 하나씩 더함). 범위 표와 실행 검사가 쓴다
STAGES = []
for _name, _flag in (('합류', 'JOINED'), ('텐페 부탁', 'TEMPE_HEARD'), ('텐페 이김', 'WON'), ('납치', 'KIDNAPPED'),
                     ('팔찌', 'BRACELET'), ('구함', 'RESCUED'), ('왕 병', 'BAZAAR'), ('들음', 'HEARD'),
                     ('꿀', 'GOT'), ('나음', 'CURED'), ('우승', 'CHAMPION'), ('사자', 'MESSENGER')):
    STAGES.append((_name, (STAGES[-1][1] if STAGES else frozenset({'CHAPTER2'})) | {_flag}))
LINES_TSV = HERE / 'dq4ch2partytalk.tsv'           # dq4ch2partytalknds.py lines 가 NDS 표에서 만든 줄
TEXT_TSV = HERE / 'dq4ch2partytalk-text.tsv'       # NDS 메시지 번호마다의 한글 대사(NDS 한글 팬패치를 참고해 옮김)


def _rows(path):
    head, *rows = path.read_text(encoding='utf-8').splitlines()
    keys = head.split('\t')
    return [dict(zip(keys, r.split('\t'))) for r in rows if r]


def _names(cell):
    return tuple(v for v in cell.split(',') if v)


def _message(ids, texts):
    """NDS 메시지 여럿을 한 메시지로: 같은 사람이 이어 말하면 쪽마다, 사람이 바뀌면 그 사람 이름으로 이어 붙인다."""
    runs = []
    for m in ids:
        name, text = texts[m]
        if runs and runs[-1][0] == name:
            runs[-1][1].append(text)
        else:
            runs.append((name, [text]))
    return _pair(*(speak(name, *pages) for name, pages in runs))


def _load():
    texts = {int(r['message']): (r['speaker'], r['text']) for r in _rows(TEXT_TSV)}
    messages, lines = {}, []
    for r in _rows(LINES_TSV):
        ids = tuple(int(m) for m in r['messages'].split(','))
        name = 'n' + '_'.join(map(str, ids))
        if name not in messages:
            messages[name] = _message(ids, texts)
        lines.append(Line(r['map'], SPEAKERS[r['speaker']][0], name, priority=int(r['priority']), time=r['time'],
                          on=tuple(CONDITIONS[f] for f in _names(r['on'])), off=tuple(CONDITIONS[f] for f in _names(r['off'])),
                          with_=tuple(SPEAKERS[p][0] for p in _names(r['with'])),
                          talked=_names(r.get('talked', '')), nds=int(r['nds'])))
    return messages, tuple(lines)


MESSAGES, LINES = _load()
PEOPLE_TSV = HERE / 'dq4ch2partytalk-people.tsv'  # dq4ch2partytalknds.py people 가 만든 NDS 인물 ↔ SFC 인물 짝
SURE = '확인'


def _people():
    """{(NDS 맵, 인물 번호): [행]}(dq4ch2partytalknds.read_people 과 같은 꼴, cell 은 (x, y))."""
    out = {}
    for row in _rows(PEOPLE_TSV):
        row['cell'] = tuple(int(v) for v in row['cell'].split(',')) if row['cell'] else ()
        out.setdefault((row['nds_map'], row['person']), []).append(row)
    return out


PEOPLE = _people()

DATA_ENTRIES = ('maps',)
CODE_ENTRIES = ()
_TALKS = None                  # {「NDS 맵:인물 번호」: 대화 번호 frozenset}. npc_lists 가 채운다


def _cell(e):
    return e["fields"]["x"], e["fields"]["y"]


def talk_numbers(lists, made, overrides):
    """{「NDS 맵:인물 번호」: frozenset(대화 번호)}: 짝 표의 확인된 짝(맵, 칸, 낮밤)에 선 인물의 대화 번호를 그 맵의
    기본 목록(lists)과 그 맵을 덮는 대체 목록(overrides 의 new:이름 → made)에서 모두 모은다. 사건이 칸을 옮긴 인물은
    모이지 않는다(조건이 덜 맞을 뿐 틀리게 맞지는 않음). 가게·교회 같은 DQ5 기본 대화 번호(SCRIPT_TALK 아래)는 어느 맵의
    가게 주인이나 같은 번호라 뺀다."""
    from dq4npcport import SCRIPT_TALK
    by_map = {}
    for o in overrides:
        name = o["list"][4:] if o["list"].startswith("new:") else None
        if name in made:
            by_map.setdefault(o["map"], []).append(made[name])
    out = {}
    for (mp, who), rows in PEOPLE.items():
        talks = set()
        for r in rows:
            if r['status'] != SURE:
                continue
            for lst in ([lists[r['map']]] if r['map'] in lists else []) + by_map.get(r['map'], []):
                talks |= {e["fields"]["talk"] for e in lst["entries"]
                          if _cell(e) == r['cell'] and e["time"] == r['time'] and e["fields"]["talk"] >= SCRIPT_TALK}
        out[f'{mp}:{who}'] = frozenset(talks)
    return out


def npc_lists(lists, ctx):
    """인물 목록은 바꾸지 않는다. 짝 표의 인물마다 대화 번호를 모아 native 가 쓰게 둔다(같은 빌드 안에서 먼저 불림)."""
    global _TALKS
    _TALKS = talk_numbers(lists, getattr(ctx, 'made_all', ctx.made), getattr(ctx, 'overrides', ()))
    return [], []


def chapter3():
    """3장 사건 모듈 가운데 동료 대화 줄을 내놓는 것(TALKS_FOUND 가 있는 모듈, dq4ch3partytalk). 없으면 None."""
    import dq4ch3event
    return next((m for _, m in dq4ch3event.modules() if hasattr(m, 'TALKS_FOUND')), None)


def all_lines():
    """롬 표에 들어가는 줄: 이 모듈(2장)의 줄 뒤에 3장 모듈의 줄."""
    more = chapter3()
    return LINES + (more.LINES if more else ())


def all_talks():
    """{말 상대 이름: 대화 번호 frozenset}: 2장 짝 표와 3장 모듈의 것. 빌드가 인물 목록을 만들기 전이면 None."""
    more = chapter3()
    found = more.TALKS_FOUND if more else {}
    if _TALKS is None or found is None:
        return None
    if set(_TALKS) & set(found):
        raise SystemExit('동료 대화: 2장과 3장 말 상대 이름이 겹침')
    return {**_TALKS, **found}


def _chapter3_messages(msg):
    """{3장 줄 메시지 이름: 번호}. msg 는 이 모듈 MESSAGES 의 번호(None 이면 None). 3장 메시지는 2장 메시지(이 모듈과 그
    뒤 사건 모듈 것까지) 바로 뒤라(dq4chapter1.chapter3_message) 이 모듈 첫 번호에서 센다."""
    more = chapter3()
    if not msg or more is None:
        return {} if more is None else None
    import dq4ch3event
    mods = [m for _, m in ch2.modules()]
    here = next(k for k, m in enumerate(mods) if m.__name__ == __name__)
    first = min(msg.values()) + sum(len(getattr(m, 'MESSAGES', {})) for m in mods[here:])
    return next(c for c in dq4ch3event.contexts(first_message=first) if c.module is more).msg


def talk_tables(talks=None, lines=None):
    """(번호 표 [대화 번호], {talked 묶음: [차례 + 1]}). 대화 번호가 하나도 모이지 않은 묶음은 넣지 않는다(그 줄은
    롬에 쓰지 않음). talks 가 None 이면 묶음이 없다(주소만 셀 때). lines 는 기본으로 all_lines()."""
    talks = {} if talks is None else talks
    groups = sorted({ln.talked for ln in (all_lines() if lines is None else lines) if ln.talked})
    ids = sorted({t for g in groups for k in g for t in talks.get(k, ())})
    if len(ids) > MAX_IDS:
        raise SystemExit(f'동료 대화: 말 건 인물 대화 번호가 {len(ids)}개(최대 {MAX_IDS})')
    index = {t: k + 1 for k, t in enumerate(ids)}
    sets = {g: sorted({index[t] for k in g for t in talks.get(k, ())}) for g in groups}
    return ids, {g: v for g, v in sets.items() if v}


def _key(mp):
    if mp == FIELD:
        return FIELD_KEY
    g, m = mp.split('/')
    return int(g, 16), int(m, 16)


def record(line, msg, talk_set=0):
    """줄 하나의 바이트: 길이, 우선순위, 말하는 인물, 시간, 메시지(2), 조건 수, 조건(3바이트씩)."""
    conds = line.conditions(talk_set)
    body = bytes((line.priority, line.speaker, TIMES[line.time], msg & 0xFF, msg >> 8 & 0xFF, len(conds)))
    body += b''.join(bytes(c) for c in conds)
    if len(body) + 1 > 0xFF:
        raise ValueError(f'{line.message}: 조건이 너무 많음')
    return bytes((len(body) + 1,)) + body


def lists(msg, lines=None, sets=None):
    """{(맵 바이트 둘): [줄 바이트]}. 줄은 우선순위 차례(같으면 LINES 차례). msg 는 {이름: 번호}(None 이면 0),
    sets 는 {talked 묶음: 번호 묶음 주소}(None 이면 0). sets 를 주면 그 안에 없는 talked 묶음의 줄은 뺀다."""
    lines = all_lines() if lines is None else lines
    if not msg:
        more = chapter3()
        known = set(MESSAGES) | set(more.MESSAGES if more else ())
    out = {}
    for line in sorted(lines, key=lambda ln: ln.priority):
        if sets is not None and line.talked and line.talked not in sets:
            continue
        if line.message not in (msg or known):
            raise ValueError(f'{line.message}: MESSAGES 에 없는 대사')
        out.setdefault(_key(line.map), []).append(
            record(line, msg[line.message] if msg else 0, (sets or {}).get(line.talked, 0)))
    for key, rows in out.items():
        if len(rows) > 0xFE:
            raise ValueError(f'{key}: 한 맵의 줄이 254개를 넘음')
    return out


def _code(origin):
    """받침(STUB_AT)이 대화 창을 연 뒤 JSL 로 부른다. A·X·Y·D·P 를 지키고 고른 메시지를 띄운다(기다림은 05:D5BF).
    자료(maps 와 줄)는 long,X 로 읽어 DB 를 바꾸지 않는다."""
    T = origin & 0xFF0000
    a = _Asm(origin)

    def lt(op, off=0):              # op long,X 로 이 뱅크의 줄 바이트(X = 줄 첫 주소의 아래 16비트)
        return a.b(op, *(T + off).to_bytes(3, 'little'))
    a.label('talk').b(0x08, 0xC2, 0x30, 0x48, 0xDA, 0x5A, 0x0B, 0xA9, 0x00, 0x00, 0x5B, 0xE2, 0x20)
    # 지금 맵의 열쇠: 필드면 FE FE, 아니면 7E:00BC·00BD
    a.b(0xAF, 0xBE, 0x00, 0x7E).rel(0x30, 'room').b(0xA9, 0xFE, 0xEB, 0xA9, 0xFE).rel(0x80, 'key')
    a.label('room').b(0xAF, 0xBD, 0x00, 0x7E, 0xEB, 0xAF, 0xBC, 0x00, 0x7E)
    a.label('key').b(0xC2, 0x20, 0x48).word(0xA2, 'maps')
    a.label('m_loop')
    lt(0xBF).b(0xC9, 0xFF, 0xFF).rel(0xF0, 'm_none').b(0xC3, 0x01).rel(0xF0, 'm_found').b(0xE8, 0xE8, 0xE8, 0xE8)
    a.rel(0x80, 'm_loop')
    a.label('m_none').b(0x68).word(0x4C, 'nobody')
    a.label('m_found').b(0x68)
    lt(0xBF, 2).b(0xAA, 0xE2, 0x20)
    # 틀: 5·6,S 목록 첫 주소, 4,S 지난번 고른 차례 + 1, 3,S 고른 차례, 2,S 맞는 첫 차례, 1,S 그 우선순위(FF 없음)
    a.b(0xDA, 0xAF, 0x90 + LAST[0], 0x21, 0x7E, 0x48, 0xA9, 0xFF, 0x48, 0x48, 0x48, 0xA0, 0x00, 0x00)
    a.label('r_loop')
    lt(0xBF).rel(0xF0, 'r_end')
    a.word(0x20, 'pass').rel(0x90, 'r_next')
    a.b(0xA3, 0x01, 0xC9, 0xFF).rel(0xD0, 'have')
    lt(0xBF, 1).b(0x83, 0x01, 0x98, 0x83, 0x02).rel(0x80, 'check')
    a.label('have')
    lt(0xBF, 1).b(0xC3, 0x01).rel(0xD0, 'r_end')
    a.label('check').b(0xA3, 0x03, 0xC9, 0xFF).rel(0xD0, 'r_next')
    a.b(0x98, 0xC3, 0x04).rel(0x90, 'r_next').b(0x83, 0x03)
    a.label('r_next').word(0x20, 'next').b(0xC8).rel(0x80, 'r_loop')
    a.label('r_end').b(0xA3, 0x03, 0xC9, 0xFF).rel(0xD0, 'got')
    a.b(0xA3, 0x02, 0xC9, 0xFF).rel(0xF0, 'none')
    # 고른 차례를 적고 목록 첫 줄부터 그 차례까지 건너 메시지를 읽는다
    a.label('got').b(0x1A, 0x8F, 0x90 + LAST[0], 0x21, 0x7E, 0x3A,
                     0xC2, 0x20, 0x29, 0xFF, 0x00, 0xA8, 0xA3, 0x05, 0xAA, 0xE2, 0x20)
    a.label('walk').b(0xC0, 0x00, 0x00).rel(0xF0, 'at').word(0x20, 'next').b(0x88).rel(0x80, 'walk')
    a.label('at').b(0xC2, 0x30)
    lt(0xBF, 4).b(0xA8, 0xFA, 0xFA, 0xFA, 0x98).rel(0x80, 'show')
    a.label('none').b(0xC2, 0x30, 0xFA, 0xFA, 0xFA)
    a.label('nobody').b(0xC2, 0x30, 0xA9, NOBODY & 0xFF, NOBODY >> 8)
    a.label('show').b(0x22, *MESSAGE_AT.to_bytes(3, 'little'))
    a.b(0xC2, 0x30, 0x2B, 0x7A, 0xFA, 0x68, 0x28, 0x6B)

    # next: X 를 다음 줄로(X += 길이)
    a.label('next').b(0xC2, 0x20)
    lt(0xBF).b(0x29, 0xFF, 0x00, 0x48, 0x8A, 0x18, 0x63, 0x01, 0xAA, 0x68, 0xE2, 0x20, 0x60)
    # pass: X 의 줄이 맞으면 캐리. X·Y 를 지킨다
    a.label('pass').b(0xDA, 0x5A)
    lt(0xBF, 2).word(0x20, 'in_line').rel(0x90, 'p_fail')
    lt(0xBF, 3).rel(0xF0, 'p_time').b(0x22, *NIGHT_TEST.to_bytes(3, 'little')).rel(0xB0, 'p_night')
    a.b(0xC9, 0x01).rel(0xD0, 'p_fail').rel(0x80, 'p_time')
    a.label('p_night').b(0xC9, 0x02).rel(0xD0, 'p_fail')
    a.label('p_time')
    lt(0xBF, 6).b(0xC2, 0x20, 0x29, 0xFF, 0x00, 0xA8, 0xE2, 0x20, 0xE8, 0xE8, 0xE8, 0xE8, 0xE8, 0xE8, 0xE8)
    a.label('c_loop').b(0xC0, 0x00, 0x00).rel(0xF0, 'p_ok').word(0x20, 'cond').rel(0x90, 'p_fail')
    a.b(0xE8, 0xE8, 0xE8, 0x88).rel(0x80, 'c_loop')
    a.label('p_ok').b(0x7A, 0xFA, 0x38, 0x60)
    a.label('p_fail').b(0x7A, 0xFA, 0x18, 0x60)
    # cond: X 의 조건 하나가 맞으면 캐리. X·Y 를 지킨다
    a.label('cond')
    lt(0xBF)
    for kind, name in ((ON, 'c_on'), (OFF, 'c_off'), (EQUAL, 'c_eq'), (LEAD, 'c_lead'), (WITH, 'c_with'),
                       (WITHOUT, 'c_without')):
        a.b(0xC9, kind).rel(0xF0, name)
    for kind, name in ((HAVE, 'c_have'), (LACK, 'c_lack'), (VAR, 'c_var')):
        a.b(0xC9, kind).rel(0xD0, f'not{kind}').word(0x4C, name).label(f'not{kind}')
    a.b(0xC9, TALKED).rel(0xD0, 'no').word(0x4C, 'c_talked')
    a.label('no').b(0x18, 0x60)
    a.label('yes').b(0x38, 0x60)
    a.label('c_on').word(0x20, 'fbyte')
    lt(0x3F, 2)
    lt(0xDF, 2).rel(0xF0, 'yes').rel(0x80, 'no')
    a.label('c_off').word(0x20, 'fbyte')
    lt(0x3F, 2).rel(0xF0, 'yes').rel(0x80, 'no')
    a.label('c_eq').word(0x20, 'fbyte')
    lt(0xDF, 2).rel(0xF0, 'yes').rel(0x80, 'no')
    a.label('c_lead').b(0xDA, 0xA2, 0x00, 0x00).word(0x20, 'rec').b(0xFA)
    lt(0xDF, 1).rel(0xF0, 'yes').rel(0x80, 'no')
    a.label('c_with')
    lt(0xBF, 1).word(0x20, 'in_line').b(0x60)
    a.label('c_without')
    lt(0xBF, 1).word(0x20, 'in_line').rel(0xB0, 'no').rel(0x80, 'yes')
    # c_talked: 7E:21FD 가 X 의 조건이 가리키는 번호 묶음(수, 차례 + 1 …)에 있으면 캐리. X·Y 를 지킨다
    a.label('c_talked').b(0xDA, 0x5A, 0xAF, 0x90 + TALKED_TO[0], 0x21, 0x7E).rel(0xF0, 't_none').b(0x48, 0xC2, 0x20)
    lt(0xBF, 1).b(0xAA, 0xE2, 0x20)
    lt(0xBF).b(0xC2, 0x20, 0x29, 0xFF, 0x00, 0xA8, 0xE2, 0x20).rel(0xF0, 't_no')
    a.label('t_loop').b(0xE8)
    lt(0xBF).b(0xC3, 0x01).rel(0xF0, 't_yes').b(0x88).rel(0xD0, 't_loop')
    a.label('t_no').b(0x68)
    a.label('t_none').b(0x7A, 0xFA, 0x18, 0x60)
    a.label('t_yes').b(0x68, 0x7A, 0xFA, 0x38, 0x60)
    # c_have·c_lack: X 의 조건(값 1 = 물건)을 has 로. c_var: 3장 변수 칸 바이트 = 값 2. X·Y 를 지킨다
    a.label('c_have').word(0x20, 'has').b(0x60)
    a.label('c_lack').word(0x20, 'has').rel(0xB0, 'l_no').b(0x38, 0x60)
    a.label('l_no').b(0x18, 0x60)
    a.label('c_var').b(0xDA)
    lt(0xBF, 1).b(0xC2, 0x20, 0x29, 0xFF, 0x00, 0xAA, 0xE2, 0x20, 0xBF, *VARS_AT.to_bytes(3, 'little'), 0xFA)
    lt(0xDF, 2).rel(0xF0, 'v_yes').b(0x18, 0x60)
    a.label('v_yes').b(0x38, 0x60)
    # has: X 의 조건 값 1 의 물건을 일행 기록 0~(7E:201D − 1)의 가진 물건 칸이나 맡긴 물건에 누가 가지면 캐리
    a.label('has').b(0xDA, 0x5A)
    lt(0xBF, 1).b(0x48, 0xAF, 0x1D, 0x20, 0x7E).rel(0xF0, 'h_bag')
    a.b(0x48, 0xA2, *(PARTY_ITEMS & 0xFFFF).to_bytes(2, 'little'))
    a.label('h_rec').b(0xA0, ITEM_SLOTS, 0x00)
    a.label('h_slot').b(0xBF, 0x00, 0x00, 0x7E, 0xC3, 0x02).rel(0xF0, 'h_found').b(0xE8, 0x88).rel(0xD0, 'h_slot')
    a.b(0xC2, 0x20, 0x8A, 0x18, 0x69, RECORD - ITEM_SLOTS, 0x00, 0xAA, 0xE2, 0x20)
    a.b(0xA3, 0x01, 0x3A, 0x83, 0x01).rel(0xD0, 'h_rec').b(0x68)
    a.label('h_bag').b(0xC2, 0x20, 0xA3, 0x01, 0x29, 0xFF, 0x00, 0xAA, 0xE2, 0x20, 0xBF, *BAG.to_bytes(3, 'little'))
    a.rel(0xF0, 'h_none').b(0x68, 0x7A, 0xFA, 0x38, 0x60)
    a.label('h_found').b(0x68, 0x68, 0x7A, 0xFA, 0x38, 0x60)
    a.label('h_none').b(0x68, 0x7A, 0xFA, 0x18, 0x60)
    # fbyte: A = 7E:2190 + (X 의 값 1)
    a.label('fbyte').b(0xDA)
    lt(0xBF, 1).b(0xC2, 0x20, 0x29, 0xFF, 0x00, 0xAA, 0xE2, 0x20, 0xBF, 0x90, 0x21, 0x7E, 0xFA, 0x60)
    # in_line: A 의 인물이 걷는 줄(7E:201E 명)에 있고 HP 가 0 이 아니면 캐리. X·Y 를 지킨다
    a.label('in_line').b(0xDA, 0x5A, 0x48, 0xA0, 0x00, 0x00)
    a.label('il_loop').b(0x98, 0xCF, 0x1E, 0x20, 0x7E).rel(0xB0, 'il_no')
    a.b(0xBB).word(0x20, 'rec').b(0xC3, 0x01).rel(0xD0, 'il_next')
    a.b(0xC2, 0x20, 0xBF, 0x42, 0x20, 0x7E, 0xE2, 0x20).rel(0xD0, 'il_yes')
    a.label('il_next').b(0xC8).rel(0x80, 'il_loop')
    a.label('il_no').b(0x68, 0x7A, 0xFA, 0x18, 0x60)
    a.label('il_yes').b(0x68, 0x7A, 0xFA, 0x38, 0x60)
    # rec: X = 걷는 줄 차례 → X = 그 사람 일행 기록의 거리(번호 × 42), A = 인물 번호
    a.label('rec').b(0xBF, 0x20, 0x20, 0x7E, 0xC2, 0x20, 0x29, 0xFF, 0x00, 0x0A, 0x48, 0x0A, 0x0A, 0x48, 0x0A, 0x0A,
                     0x18, 0x63, 0x01, 0x63, 0x03, 0xAA, 0x68, 0x68, 0xE2, 0x20, 0xBF, 0x40, 0x20, 0x7E, 0x60)

    # talked: 대화 시작(TALK_HOOK_AT)의 JSL. M·X 8비트, DB 06. 말 상대 슬롯의 대화 번호를 번호 표(ids, FFFF 로 끝)에서
    # 찾아 차례 + 1(없으면 0)을 7E:21FD 에 두고, 덮은 두 명령(LDX $0F1E / LDA $7E36E0,X)을 그대로 하고 돌아간다
    a.label('talked').b(0x08, 0xC2, 0x30, 0xAF, 0x1E, 0x0F, 0x7E, 0x29, 0xFF, 0x00, 0xAA, 0xE2, 0x20,
                        0xBF, 0x00, 0x37, 0x7E, 0xEB, 0xBF, 0xE0, 0x36, 0x7E, 0xC2, 0x20, 0x48, 0xA2, 0x00, 0x00)
    a.label('i_loop').long(0xBF, 'ids').b(0xC9, 0xFF, 0xFF).rel(0xF0, 'i_none')
    a.b(0xC3, 0x01).rel(0xF0, 'i_found').b(0xE8, 0xE8).rel(0x80, 'i_loop')
    a.label('i_found').b(0x8A, 0x4A, 0x1A).rel(0x80, 'i_store')
    a.label('i_none').b(0xA9, 0x00, 0x00)
    a.label('i_store').b(0xE2, 0x20, 0x8F, 0x90 + TALKED_TO[0], 0x21, 0x7E, 0xC2, 0x20, 0x68, 0x28,
                         0xAE, 0x1E, 0x0F, 0xBF, 0xE0, 0x36, 0x7E, 0x6B)
    return a


def native(ctx):
    """(바이트, {이름: 주소}). 코드 뒤에 맵 표(맵 바이트 둘, 목록 주소; FF FF 로 끝), 맵마다의 줄(길이 0 으로 끝),
    번호 묶음(수, 차례 + 1 …), 번호 표(대화 번호 2바이트씩, FFFF 로 끝)."""
    talks = all_talks()
    if talks is None and ctx.original is not None:
        raise SystemExit('동료 대화: 인물 목록(npc_lists)을 만들기 전에 롬에 쓰려 함')
    msg = None
    if ctx.msg:
        more = _chapter3_messages(ctx.msg)
        if set(more) & set(ctx.msg):
            raise SystemExit('동료 대화: 2장과 3장 메시지 이름이 겹침')
        msg = {**ctx.msg, **more}
    ids, groups = talk_tables(talks)
    a = _code(ctx.code_at)
    code, labels = a.assemble({'maps': 0, 'ids': 0})
    maps_at = ctx.code_at + len(code)
    rows = lists(msg, sets={g: 0 for g in groups})
    at = maps_at + 4 * len(rows) + 2 + sum(len(b''.join(r)) + 1 for r in rows.values())
    sets, blob = {}, bytearray()
    for g in sorted(groups):
        sets[g] = (at + len(blob)) & 0xFFFF
        blob += bytes((len(groups[g]), *groups[g]))
    ids_at = at + len(blob)
    tail = bytes(blob) + b''.join(t.to_bytes(2, 'little') for t in ids) + b'\xff\xff'
    rows = lists(msg, sets=sets)
    at = maps_at + 4 * len(rows) + 2
    head, body = bytearray(), bytearray()
    for key, recs in rows.items():
        head += bytes(key) + (at & 0xFFFF).to_bytes(2, 'little')
        part = b''.join(recs) + b'\x00'
        body += part
        at += len(part)
    head += b'\xff\xff'
    code, labels = a.assemble({'maps': maps_at, 'ids': ids_at})
    out = code + bytes(head) + bytes(body) + tail
    if (ctx.code_at & 0xFFFF) + len(out) > 0x10000:
        raise SystemExit('동료 대화 코드가 뱅크를 넘음')
    return out, {'talk': labels['talk'], 'talked': labels['talked'], 'maps': maps_at}


def hooks(ctx):
    stub = bytes((0x00, 0x95, 0x00, 0x22, *ctx.at['talk'].to_bytes(3, 'little'), 0x60))
    assert len(stub) == STUB_LEN
    talked = ctx.at['talked']
    return [(STUB_AT, bytes(STUB_LEN), stub),
            (HOOK_AT, HOOK_ORIG, bytes((0x20, STUB_AT & 0xFF, STUB_AT >> 8 & 0xFF, 0xEA, 0xEA, 0xEA))),
            (TALK_HOOK_AT, TALK_HOOK_ORIG, bytes((0x22, *talked.to_bytes(3, 'little'), 0xEA, 0xEA, 0xEA)))]


def table(data, at):
    """롬의 맵 표를 읽는다(검사용): {(맵 바이트 둘): [(우선순위, 말하는 인물, 시간, 메시지, [(종류, 값, 값)])]}."""
    out, o = {}, ch1.lorom(at)
    bank = at & 0xFF0000
    while data[o:o + 2] != b'\xff\xff':
        key = (data[o], data[o + 1])
        p = ch1.lorom(bank | int.from_bytes(data[o + 2:o + 4], 'little'))
        rows = []
        while data[p]:
            n = data[p]
            pr, sp, tm, lo, hi, k = data[p + 1:p + 7]
            rows.append((pr, sp, tm, lo | hi << 8, [tuple(data[p + 7 + 3 * i:p + 10 + 3 * i]) for i in range(k)]))
            p += n
        out[key] = rows
        o += 4
    return out


def talk_set(data, at, addr):
    """롬의 번호 묶음(TALKED 조건의 값 둘이 가리킴)을 읽는다(검사용): [차례 + 1]."""
    o = ch1.lorom((at & 0xFF0000) | addr)
    return list(data[o + 1:o + 1 + data[o]])


def talk_ids(data, at):
    """롬의 번호 표(검사용): [대화 번호]. 대화 시작 훅 루틴이 LDA long,X 로 읽는 주소에서."""
    o = ch1.lorom(at['talked']) + IDS_OPERAND
    if data[o] != 0xBF:
        raise ValueError(f'{at["talked"]:06X}: 번호 표를 읽는 명령이 아님')
    p, out = ch1.lorom(int.from_bytes(data[o + 1:o + 4], 'little')), []
    while data[p:p + 2] != b'\xff\xff':
        out.append(int.from_bytes(data[p:p + 2], 'little'))
        p += 2
    return out
