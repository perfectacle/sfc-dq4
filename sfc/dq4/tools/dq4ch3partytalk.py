"""3장 동료 대화(dq4ch3slots 'P'): 용병 스콧·로렌스(와 따라오는 개 토마스)가 「はなす」로 하는 말(NDS 리메이크의 3장
동료 대화).

훅·조건 평가 루틴·롬 표는 2장 모듈 dq4ch2partytalk 이 갖는다(「はなす」 훅이 하나라서). 이 모듈은 3장 줄(LINES)과 그
대사(MESSAGES, 3장 메시지 번호로 들어감)를 내놓고, 인물 목록을 만들 때(npc_lists) 「방금 말을 건 사람」 이름을 대화
번호로 풀어 TALKS_FOUND 에 둔다. 2장 모듈의 native 가 둘을 한 표에 합친다. 형식은 sfc/dq4/docs/dq4-chapter3-format.md
「동료 대화」.

줄은 NDS 3장 동료 대화 표에서 옮긴 dq4ch3partytalk.tsv(dq4ch2partytalknds.py --chapter 3 lines 가 만듦)와 한글 대사
dq4ch3partytalk-text.tsv 다. 말하는 이는 일행 기록 +0 으로 찾는다: 톨네코 00, 용병은 몬스터 손님 C0 | 동료 종류
(dq4mercenary). 개 토마스는 일행 기록이 아니라 톨네코를 말하는 이로 두고 DOG flag 를 조건으로 더한다.

「방금 말을 건 사람」 이름은 둘이다: 「키.대화」 는 3장 사건 모듈(dq4ch3slots 키)의 TALKS 이름이고, 「맵:x-y:낮밤」 은
옮긴 FC 인물(FC 칸)이다. 둘 다 3장 동안 그 맵에 걸리는 목록에서 대화 번호를 찾고, 하나도 없으면 빌드를 멈춘다.
"""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4ch2partytalk as pt  # noqa: E402
import dq4ch3bonmalmo as bonmalmo  # noqa: E402
import dq4ch3endor as endor  # noqa: E402
import dq4ch3event as ch3  # noqa: E402
import dq4ch3lakanaba as lakanaba  # noqa: E402
import dq4ch3tunnel as tunnel  # noqa: E402
import dq4mercenary as merc  # noqa: E402
from dq4itemport import STATUE  # noqa: E402

FLAGS = ()
TORNEKO = 0x00                 # 주인공 기록 0(3장 넘김이 톨네코로 덮음)
SPEAKERS = {'TORNEKO': TORNEKO, 'SCOTT': merc.GUEST | merc.SCOTT_KIND, 'LAWRENCE': merc.GUEST | merc.LAWRENCE_KIND}
# 줄 표의 조건 이름(dq4ch2partytalknds.STORY3·FIXES3) → 사건 모듈의 flag
CONDITIONS = {
    'CHAPTER3': ch3.CHAPTER3, 'DOG': ch3.DOG, 'SCOTT': ch3.SCOTT, 'LAWRENCE': ch3.LAWRENCE,
    'SON_FREED': bonmalmo.SON_FREED, 'FOXED': bonmalmo.FOXED, 'LETTER2': bonmalmo.LETTER2,
    'ALLOWED': endor.ALLOWED, 'SHOP': endor.SHOP, 'ORDER': endor.ORDER, 'DELIVERED': endor.DELIVERED,
    'PAID': tunnel.PAID, 'RESUMED': tunnel.RESUMED, 'OPENED': tunnel.OPENED,
}
ITEMS = {'STATUE': STATUE}
# 변수 칸(dq4ch3slots.VARS_AT) 오프셋: 용병 날수(고용 뒤 지난 날)
VARS = {'SCOTT_DAYS': ch3.SCOTT_DAYS - pt.VARS_AT, 'LAWRENCE_DAYS': ch3.LAWRENCE_DAYS - pt.VARS_AT}
NAMES = {'SCOTT': '스콧', 'LAWRENCE': '로렌스', 'THOMAS': '토마스', 'TORNEKO': '톨네코'}

# 3장 진행 단계(앞 단계 flag 를 모두 켠 채 하나씩 더함). 실행 검사가 쓴다. 동행(SCOTT·LAWRENCE·DOG)은 단계가 아니라 일행으로
STAGES = []
for _name, _flag in (('톰 아들', 'SON_FREED'), ('여우', 'FOXED'), ('편지', 'LETTER2'), ('허락', 'ALLOWED'),
                     ('가게', 'SHOP'), ('주문', 'ORDER'), ('납품', 'DELIVERED'), ('공사비', 'PAID'), ('재개', 'RESUMED'),
                     ('개통', 'OPENED')):
    STAGES.append((_name, (STAGES[-1][1] if STAGES else frozenset({'CHAPTER3'})) | {_flag}))
COMPANIONS = ('DOG', 'SCOTT', 'LAWRENCE')

LINES_TSV = HERE / 'dq4ch3partytalk.tsv'
TEXT_TSV = HERE / 'dq4ch3partytalk-text.tsv'


def _names(cell):
    return tuple(v for v in cell.split(',') if v)


def _load():
    texts = {int(r['message']): (r['speaker'], r['text']) for r in pt._rows(TEXT_TSV)}
    messages, lines = {}, []
    for r in pt._rows(LINES_TSV):
        ids = tuple(int(m) for m in r['messages'].split(','))
        name = 'n' + '_'.join(map(str, ids))
        if name not in messages:
            messages[name] = pt._message(ids, texts)
        days = tuple((VARS[k], int(v)) for k, v in (d.split('=') for d in _names(r['days'])))
        lines.append(pt.Line(r['map'], SPEAKERS[r['speaker']], name, priority=int(r['priority']), time=r['time'],
                             on=tuple(CONDITIONS[f] for f in _names(r['on'])),
                             off=tuple(CONDITIONS[f] for f in _names(r['off'])),
                             with_=tuple(SPEAKERS[p] for p in _names(r['with'])),
                             talked=_names(r['talked']), nds=int(r['nds']),
                             have=tuple(ITEMS[i] for i in _names(r['have'])),
                             lack=tuple(ITEMS[i] for i in _names(r['lack'])), var=days))
    return messages, tuple(lines)


MESSAGES, LINES = _load()
TALKS_FOUND = None             # {말 상대 이름: 대화 번호 frozenset}. npc_lists 가 채운다


def _cell(e):
    return e["fields"]["x"], e["fields"]["y"]


def map_lists(lists, ctx, mp):
    """맵 mp 에 걸릴 수 있는 목록: 기본 목록과 그 맵을 덮는 대체 목록 모두."""
    names = {o["list"][4:] for o in ctx.overrides if o["map"] == mp and o["list"].startswith("new:")}
    return ([lists[mp]] if mp in lists else []) + [ctx.made_all[n] for n in sorted(names) if n in ctx.made_all]


def resolve(token, lists, ctx, talk_of):
    """말 상대 이름 하나 → 대화 번호 frozenset. talk_of: {「키.대화」: 대화 번호}."""
    from dq4npcport import SCRIPT_TALK
    if ':' in token:
        mp, at, time = token.split(':')
        fx, fy = (int(v) for v in at.split('-'))
        cell = (2 * fx, 2 * fy + 1)
        found = {e["fields"]["talk"] for lst in map_lists(lists, ctx, mp) for e in lst["entries"]
                 if _cell(e) == cell and e["time"] == time and e["fields"]["talk"] >= SCRIPT_TALK}
    else:
        talk = talk_of[token]
        found = {talk} if any(e["fields"]["talk"] == talk for lst in (*lists.values(), *ctx.made_all.values())
                              for e in lst["entries"]) else set()
    if not found:
        raise SystemExit(f'3장 동료 대화: 말 상대 {token} 를 목록에서 찾지 못함')
    return frozenset(found)


def npc_lists(lists, ctx):
    """인물 목록은 바꾸지 않는다. 줄의 말 상대 이름마다 대화 번호를 모아 TALKS_FOUND 에 둔다(2장 모듈 native 가 씀).
    이 모듈은 SLOTS 끝이라 다른 3장 모듈의 목록·대화가 모두 만들어진 뒤에 불린다."""
    global TALKS_FOUND
    if endor.TOWN not in lists:
        TALKS_FOUND = {}        # 인물 없이 옮긴 목록(dq4npcport.port 의 with_people=False): 말 상대 줄은 롬에 쓰지 않음
        return [], []
    talk_of = {f'{c.key}.{name}': number for c in ch3.contexts() for name, number in c.talk.items()}
    tokens = sorted({t for ln in LINES for t in ln.talked})
    TALKS_FOUND = {t: resolve(t, lists, ctx, talk_of) for t in tokens}
    return [], []
