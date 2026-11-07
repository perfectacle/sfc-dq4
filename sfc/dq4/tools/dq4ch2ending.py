"""DQ4 2장 끝: 빈 산트하임 성과 「다음에 계속」, 그리고 사건 진행에 따라 바뀌는 마을 사람의 말.

FC 차례(fc/dq4/docs/dq4-save-format.md 「장 끝」, dq4-story-format.md 2장 7):
  1. 무술 대회에서 우승하면($6284&40) 산트하임 성(FC 01/00~02)의 사람들이 사라진다. 성 앞마당 01/00 은 인물 목록을
     비우고, 왕좌의 방 01/01 은 목록 1C:$8930(고양이와 보이지 않는 인물), 왕의 방 01/02 는 1C:$895D(보이지 않는 인물)이다.
  2. 왕좌의 방에 들어서면 보이지 않는 인물의 블록이 브라이의 말(0388)을 띄우고 $6287|=08, 왕의 방이면 크리프트의
     말(0389)을 띄우고 $6287|=10.
  3. 장 끝 검사 1A:$B855: 맵에 들어설 때 그 맵이 그룹의 00 번이고 $6287 & 18 이 0 이 아니면 장 끝 서술(038B).

포팅은 우승 flag(dq4ch2endor.CHAMPION)로 세 맵을 빈 성 목록으로 바꾸고, 두 말은 보이지 않는 인물의 스크립트가 띄운다.
본 flag 가 켜진 성 앞마당 3D/00 의 목록에는 끝내는 인물이 있어, 1장에서 끝내는 판처럼 화면을 검게 하고 서술 뒤
dq4chapterbox.ENDING2(「제3장 무기상인 톨네코 / ― 다음에 계속 ―」)를 띄운 뒤 타이틀로 돌아간다. 3장으로 잇지 않는다.

마을 사람: 앞 사건 모듈이 다루지 않은, flag 로 말이 바뀌는 FC 인물을 옮긴다. 산트하임 밤의 대신·왕의 방 사람은 대화
스크립트의 flag 조건으로, 우승 뒤 엔돌은 우승 flag 로 고르는 대체 목록으로 바꾼다. 형식은
sfc/dq4/docs/dq4-chapter2-format.md 「빈 산트하임과 2장 끝」·「마을 사람 대사 진행별」.
"""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4chapter1 as ch1  # noqa: E402
import dq4ch2event as ch2  # noqa: E402
import dq4ch2endor as endor  # noqa: E402
import dq4ch2king as king  # noqa: E402
import dq4ch2talk  # noqa: E402

say, narrate, speak = ch1.say, ch1.narrate, ch1.speak

# 7E:21FC (dq4ch2slots E5)
IDX = 0x6C
SEEN_BREY = (IDX, 0x01)        # 빈 왕좌의 방에서 브라이의 말을 봄(FC $6287&08)
SEEN_KIRYL = (IDX, 0x02)       # 빈 왕의 방에서 크리프트의 말을 봄(FC $6287&10)
FLAGS = (SEEN_BREY, SEEN_KIRYL)
EMPTY = endor.CHAMPION         # 우승(FC $6284&40): 산트하임 성이 빈다

CASTLE, THRONE, BEDROOM = ch2.CASTLE, ch2.THRONE, ch2.BEDROOM
END_SCENE = 'end2'             # dq4chapterbox.ENDING2 의 이름

# 빌린 인물 스크립트(DQ5 01/00 대체 목록 10:8414, dq4ch2slots E5). (칸, 스크립트 길이 바이트 주소, 원래 스크립트 길이).
# 고친 스크립트는 원래 길이 안에 들어가야 한다(dq5npcrelocate 가 인물 레코드 크기를 지킴). 칸 2·3·7·11~14 와
# 10:CB92 칸 0~8 은 남았다
SCRIPT_LIST = '10:8414'
SCRIPTS = {'ender': (8, '10:8496', 17), 'brey': (9, '10:84AF', 14), 'kiryl': (10, '10:84C5', 13)}

EMPTY_CASTLE, EMPTY_THRONE, EMPTY_BEDROOM, ENDER = ('ch2_ending_castle', 'ch2_ending_throne', 'ch2_ending_bedroom',
                                                    'ch2_ending_ender')


def cell(x, y):
    """FC 칸 → 옮긴 인물 셀(dq4npcport.cell)."""
    return (2 * x, 2 * y + 1)


# 빈 왕좌의 방의 고양이(FC 1C:$8930 레코드 01: (17,09), 걸음 간격 4, 그림 25, 대화 36F)
CAT = (0x17, 0x09)
CAT_PICTURE, CAT_INTERVAL = 0x25, 4

# 산트하임에서 앞 사건이 말을 바꾸지 않은 인물: (맵, FC 칸, 시간대, FC 대화). 조건은 dq4ch2king 의 flag
MINISTER_NIGHT = (THRONE, (0x0B, 0x09), 'night', 0x01E)
MAID = (BEDROOM, (0x15, 0x08), 'day', 0x01C)
GUARD_NIGHT = (BEDROOM, (0x05, 0x08), 'night', 0x01B)
KING_NIGHT = (BEDROOM, (0x03, 0x04), 'night', 0x01A)

# 우승 뒤 엔돌: (맵, 낮/밤, FC 칸) → 대화 이름. FC 대화가 $6284&40 로 말을 바꾸는 인물(test_dq4ch2ending 이 FC 롬의
# 대화를 2장·우승 상태로 돌려 견준다). 바탕 목록은 2장 엔돌 목록(dq4ch2endor 가 만든 것이 있으면 그것)
WON_TALK = {
    ('40/00', 'day', (0x05, 0x13)): 'congrats',
    ('40/00', 'day', (0x0B, 0x1B)): 'barmaid',
    ('40/00', 'day', (0x0D, 0x1A)): 'sign',
    ('40/00', 'day', (0x17, 0x14)): 'rumor',
    ('40/00', 'day', (0x1A, 0x0F)): 'over',
    ('40/05', 'day', (0x08, 0x06)): 'relief',
    ('40/05', 'day', (0x03, 0x02)): 'congrats',
    ('40/06', 'day', (0x0D, 0x0B)): 'endor_minister',
    ('40/06', 'day', (0x0B, 0x0A)): 'endor_king',
    ('40/06', 'day', (0x0F, 0x0A)): 'endor_princess',
    ('40/08', 'day', (0x03, 0x03)): 'shop_sell',
    ('40/08', 'night', (0x05, 0x02)): 'shop_sell',
    ('40/08', 'night', (0x01, 0x03)): 'shop_sell',
    ('40/0A', 'day', (0x06, 0x03)): 'calm',
    ('40/0A', 'night', (0x07, 0x05)): 'calm',
    ('40/0B', 'day', (0x07, 0x08)): 'congrats',
    ('40/0B', 'day', (0x03, 0x01)): 'merchant',
    ('40/0B', 'night', (0x03, 0x01)): 'merchant',
}
# 엔돌 성 1층(FC 04/02)은 우승 뒤 목록이 바뀐다(FC 1C:$877D, 3장 시작과 같은 목록): (낮/밤, FC 칸, 방향, 간격, FC 그림,
# 대화 이름). 대화 이름이 None 이면 같은 시간대·칸의 옮긴 인물을 그대로 쓴다. 맵 밖 줄에 세워 둔 둘((1A,7F)·(1B,7F))은
# 옮긴 목록처럼 뺀다
CASTLE_WON = (
    ('day', (0x0C, 0x1C), 'down', 0, 0x11, 'congrats'),
    ('day', (0x12, 0x12), 'down', 0, 0x16, 'calm'),
    ('day', (0x11, 0x12), 'down', 0, 0x18, 'mystery'),
    ('day', (0x10, 0x08), 'down', 0, 0x11, 'congrats'),
    ('day', (0x11, 0x08), 'down', 0, 0x11, 'closed'),
    ('day', (0x12, 0x19), 'down', 8, 0x14, None),
    ('night', (0x0C, 0x1C), 'right', 4, 0x11, None),
    ('night', (0x10, 0x08), 'down', 0, 0x11, 'congrats'),
    ('night', (0x11, 0x08), 'down', 0, 0x11, 'congrats'),
    ('night', (0x11, 0x12), 'down', 0, 0x14, 'hell'),
    ('night', (0x12, 0x12), 'down', 0, 0x16, 'hero'),
    ('night', (0x08, 0x12), 'right', 0, 0x11, None),
)
ENDOR_CASTLE = '40/02'
# 대화 이름마다 FC 가 띄우는 메시지(test_dq4ch2ending 이 견줌)
FC_SHOWS = {'congrats': (0x806,), 'barmaid': (0x65D,), 'sign': (0x65E,), 'rumor': (0x65B,), 'over': (0x65C,),
            'relief': (0x807,), 'endor_minister': (0x802,), 'endor_king': (0x4D2,), 'endor_princess': (0x801,),
            'shop_sell': (0x808,), 'calm': (0x804,), 'merchant': (0x809,), 'mystery': (0x805,), 'closed': (0x803,),
            'hell': (0x55E,), 'hero': (0x55D,), 'cat': (0x70E,)}


def _cat_lines():
    return say('냐앙 냐앙 냐앙!')


# FC 메시지 번호. FC 원문을 옮겼다. 앞 사건 모듈·옮긴 인물과 같은 말은 그 한글을 그대로 쓴다
MESSAGES = {
    # 빈 성(FC 0388·0389)과 장 끝 서술(038B)
    'brey': speak('브라이', '이건 괴이한/일이로군!/대체 어찌 된/일이란 말인가!'),
    'kiryl': (speak('크리프트', '모두 어디로/가 버린 걸까요……?/어이, 어이!')[:-1] + [ch1.PAGE] +
              narrate('그러나 대답은/없었다……')),
    'end': narrate('산트하임 왕이/꾼 꿈이란……?/모습을 감춘/데스피사로란……?',
                   '그리고/산트하임의 사람들은/대체 어디로/가 버린 것일까?',
                   '그 수수께끼를/풀기 위해/아리나 공주 일행은/다시 여행을 떠났다……'),
    'cat': _cat_lines(),
    # 산트하임: 밤의 대신(FC 07A6·07E3·07E9), 왕의 방 시녀(07AF+07B0·07E5·07EA), 밤의 근위병(07AD·07E4), 밤의 왕(0551·07E2)
    'minister_night': dq4ch2talk.TEXTS[(0x7A6,)],
    'minister_ill': king.MESSAGES['minister_ill'],
    'minister_cured': king.MESSAGES['minister_cured'],
    'maid_start': dq4ch2talk.TEXTS[(0x7AF, 0x7B0)],
    'maid_ill': say('요즘 임금님께서/말을 걸어 주시지/않으세요.', '무슨 일이라도/있는 걸까요……'),
    'maid_cured': say('드디어 임금님께서/말을 걸어 주셨어요.', '아아, 어쩜 이리도/멋진 목소리일까요.'),
    'guard_night': dq4ch2talk.TEXTS[(0x7AD,)],
    'guard_ill': king.MESSAGES['guard_ill'],
    'king_sleep': dq4ch2talk.TEXTS[(0x551,)],
    'king_silent': king.MESSAGES['king_silent'],
    # 우승 뒤 엔돌
    'congrats': say('우승을/축하드립니다.'),                                                          # 0806
    'barmaid': say('어머! 당신이/아리나 공주님!?/축하해요! 마음껏/마셔요!', '오늘은 제가/한턱낼게요!'),   # 065D
    'sign': say('사인이라도/받아 둘까……'),                                                            # 065E
    'rumor': say('있잖아, 알아?/무술 대회에서/우승한 건 젊은/여자애래.'),                              # 065B
    'over': say('무술 대회도/끝난 모양이네.'),                                                        # 065C
    'relief': say('공주님,/정말 잘됐어요.'),                                                           # 0807
    'endor_minister': say('아리나 공주님의/강하심이란!/감탄했습니다.'),                                # 0802
    'endor_king': say('아리나 공주여,/잘도 우승해/주었구나./진심으로 고맙다!',                          # 04D2
                      '부왕이신 산트하임/왕께서도 무척/기뻐하실 게다.',
                      '우선은 나라로/돌아가 건강한/모습을 보여/드리거라.'),
    'endor_princess': say('고맙습니다./이제 싫은 결혼을/하지 않아도/되겠어요.',                          # 0801
                          '하지만 만약/아리나 님이/남자였다면……',
                          '어머, 제가 무슨/말을 하는 걸까요./부디 흘려/들어 주세요.'),
    'shop_sell': say('이 가게를 사서/장사를 하겠다는/사람이 어디/없으려나.'),                         # 0808
    'calm': say('데스피사로가/사라진 무렵부터/마물들도 나오지/않게 되었다더군.'),                      # 0804
    'merchant': say('오오! 당신이/아리나 공주님/이셨군요.', '저희 상인들/사이에서는 소문이/자자했답니다.'),  # 0809
    'mystery': say('데스피사로……./결국 수수께끼의/사내였군.'),                                        # 0805
    'closed': say('무술 대회도/끝났으니/투기장은/닫았습니다.'),                                         # 0803
    'hell': say('지옥의 제왕이/되살아난다는/소문도 있고……', '어느 소문이/정말인지/짐작이 가지/않는군요……'),   # 055E
    'hero': say('소문으로는 세상을/구할 용사가/어딘가에서 자라고/있다더군.'),                           # 055D
}

_ENDOR_TALKS = tuple(dict.fromkeys([*WON_TALK.values(), *(c[5] for c in CASTLE_WON if c[5])]))
TALKS = ('cat', 'minister_night', 'maid', 'guard_night', 'king_night') + _ENDOR_TALKS


def _msg(ctx, k):
    return {"op": "msg", "id": f"{ctx.msg[k]:03X}"}


def _is(flag, then, other):
    return {"op": "if", "cond": {"code": "1B", "index": flag[0], "mask": flag[1]}, "then": then, "else": other}


def _ill(ctx, start, ill, cured):
    """왕이 나았으면 cured, 바자 병사를 만난 뒤(왕이 아픔)면 ill, 아니면 start. FC 는 나을 때 $6283 bit3 을 끈다."""
    return [_is(king.CURED, _msg(ctx, cured), [_is(king.BAZAAR, _msg(ctx, ill), _msg(ctx, start))])]


def talk_scripts(ctx):
    bodies = {
        'minister_night': _ill(ctx, 'minister_night', 'minister_ill', 'minister_cured'),
        'maid': _ill(ctx, 'maid_start', 'maid_ill', 'maid_cured'),
        'guard_night': _ill(ctx, 'guard_night', 'guard_ill', 'guard_night'),
        'king_night': _ill(ctx, 'king_sleep', 'king_silent', 'king_sleep'),
    }
    return [bodies[name] if name in bodies else [_msg(ctx, name)] for name in TALKS]


def _al(a):
    return [a & 0xFF, a >> 8 & 0xFF, a >> 16]


def _cmd(op, *args, **kw):
    return {"op": op, "args": list(args), **kw}


def scripts(ctx):
    import dq4ch1event
    lo, hi = (lambda v: v & 0xFF), (lambda v: v >> 8)
    msg = lambda k: _cmd('21', lo(ctx.msg[k]), hi(ctx.msg[k])) if ctx.msg else _cmd('21', 0, 0)  # noqa: E731
    end_box = (ctx.points or {}).get(END_SCENE, 0)
    darken = dq4ch1event.native()[1]['darken']

    def voice(name, flag):
        # FC 블록처럼 맵에 들어설 때마다 말한다(26 메시지 뒤 27 로 flag)
        return [_cmd('28'), _cmd('52'), _cmd('3F'), msg(name), _cmd('10', *flag), _cmd('40'), _cmd('16')]
    out = {
        'brey': voice('brey', SEEN_BREY),
        'kiryl': voice('kiryl', SEEN_KIRYL),
        # 1장에서 끝내는 판과 같은 끊기: 검은 화면 → 서술 → 「다음에 계속」 상자, 버튼을 누르면 타이틀(돌아오지 않음)
        'ender': [_cmd('28'), _cmd('52'), _cmd('3F'), _cmd('37', *_al(darken)), msg('end'),
                  _cmd('37', *_al(end_box)), _cmd('16')],
    }
    return [{"address": SCRIPTS[k][1], "commands": v} for k, v in out.items()]


def _src(name):
    return {"list": SCRIPT_LIST, "index": SCRIPTS[name][0]}


def _invisible(name, talk):
    e = {"from": _src(name), "fields": {"x": 0, "y": 1, "facing": "down", "talk": talk, "gfx": 0x01, "layer": 0,
                                         "interval": 1}}
    return [{**e, "time": "day"}, {**e, "time": "night"}]


def _at(e):
    return (e["fields"]["x"], e["fields"]["y"])


def _retalk(entries, where, time, talk):
    hit = 0
    for e in entries:
        if _at(e) == where and e["time"] == time:
            e["fields"] = {**e["fields"], "talk": talk}
            hit += 1
    if not hit:
        raise SystemExit(f'2장 끝: {where} {time} 에 대화를 바꿀 인물이 없음')


def _person(time, fc, facing, interval, picture, talk):
    import dq4npcport as port
    x, y = cell(*fc)
    return {"from": port.WALK if interval else port.STAND, "time": time,
            "fields": {"x": x, "y": y, "facing": facing, "talk": talk, "gfx": port.PICTURES[picture], "layer": 0,
                       "interval": interval}}


def castle_won_entries(ported, talk):
    """엔돌 성 1층의 우승 뒤 목록(CASTLE_WON). ported 는 그 맵의 옮긴 목록 항목."""
    out = []
    for time, fc, facing, interval, picture, who in CASTLE_WON:
        same = [e for e in ported if e["time"] == time and _at(e) == cell(*fc)]
        if who is None:
            if len(same) != 1:
                raise SystemExit(f'2장 끝: 엔돌 성 {fc} {time} 옮긴 인물이 {len(same)}명')
            out.append(same[0])
        elif same:
            out.append({**same[0], "fields": {**same[0]["fields"], "talk": talk[who]}})
        else:
            out.append(_person(time, fc, facing, interval, picture, talk[who]))
    return out


def _won_entries(entries, m, talk):
    """entries 를 복사해 우승 뒤 말(WON_TALK 의 그 맵)로 바꾼 것."""
    table = {(time, cell(*fc)): name for (mm, time, fc), name in WON_TALK.items() if mm == m}
    out, hit = [], set()
    for e in entries:
        key = (e["time"], _at(e))
        if key in table:
            hit.add(key)
            e = {**e, "fields": {**e["fields"], "talk": talk[table[key]]}}
        out.append(e)
    if hit != set(table):
        raise SystemExit(f'2장 끝: {m} 에 우승 뒤 말을 줄 인물이 없음 {sorted(set(table) - hit)}')
    return out


def npc_lists(lists, ctx):
    t = ctx.talk
    if ENDOR_CASTLE not in lists:
        return [], []           # 인물 없이 옮긴 목록(dq4npcport.port 의 with_people=False)
    # 산트하임: 대화 스크립트의 flag 조건으로. 제자리에서 고쳐 합류·걷어참 뒤 목록(같은 항목을 담음)에도 들어간다
    for (m, where, time, _), name in ((MINISTER_NIGHT, 'minister_night'), (MAID, 'maid'),
                                      (GUARD_NIGHT, 'guard_night'), (KING_NIGHT, 'king_night')):
        _retalk(lists[m]["entries"], cell(*where), time, t[name])

    def on(m, flag, name):
        # 2장 첫머리 dq4ch2event 의 합류 뒤 목록·앞 사건의 2장 목록보다 앞에 둔다(dq4ch2event.npc_lists 의 first)
        return {"map": m, "flag": flag[0], "when": "on", "mask": flag[1], "list": f"new:{name}", "first": True}
    cat = _person('day', CAT, 'down', CAT_INTERVAL, CAT_PICTURE, t['cat'])
    new = [{"name": EMPTY_CASTLE, "entries": []},
           {"name": ENDER, "entries": _invisible('ender', t['cat'])},
           {"name": EMPTY_THRONE, "entries": [cat, {**cat, "time": "night"}] + _invisible('brey', t['cat'])},
           {"name": EMPTY_BEDROOM, "entries": _invisible('kiryl', t['cat'])}]
    over = [on(CASTLE, SEEN_BREY, ENDER), on(CASTLE, SEEN_KIRYL, ENDER), on(CASTLE, EMPTY, EMPTY_CASTLE),
            on(THRONE, EMPTY, EMPTY_THRONE), on(BEDROOM, EMPTY, EMPTY_BEDROOM)]
    # 엔돌 마을: 우승·사자 뒤 목록(dq4ch2endor)의 항목을 바꾼다. 그 밖의 맵은 2장 목록을 바탕으로 우승 목록을 새로
    for name in (endor.TOWN_MESSENGER, endor.TOWN_SEEN):
        lst = ctx.made[name]
        lst["entries"] = _won_entries(lst["entries"], endor.TOWN, t)
    for m in sorted({m for m, _, _ in WON_TALK} - {endor.TOWN}):
        base = ctx.made.get(f'ch2_endor_{m.replace("/", "")}', lists[m])
        name = f'ch2_ending_{m.replace("/", "")}'
        new.append({"name": name, "entries": _won_entries(base["entries"], m, t)})
        over.append(on(m, EMPTY, name))
    name = f'ch2_ending_{ENDOR_CASTLE.replace("/", "")}'
    new.append({"name": name, "entries": castle_won_entries(lists[ENDOR_CASTLE]["entries"], t)})
    over.append(on(ENDOR_CASTLE, EMPTY, name))
    return new, over


def start_messages(ctx):
    """장 시작 상태(사건 flag 없음)에서 이 모듈이 대화를 바꾼 인물의 첫 메시지."""
    m = ctx.msg
    return {(MINISTER_NIGHT[0], MINISTER_NIGHT[3], True): m['minister_night'],
            (MAID[0], MAID[3], False): m['maid_start'],
            (GUARD_NIGHT[0], GUARD_NIGHT[3], True): m['guard_night'],
            (KING_NIGHT[0], KING_NIGHT[3], True): m['king_sleep']}


SANTEEM = (('minister_night', MINISTER_NIGHT, ('minister_night', 'minister_ill', 'minister_cured')),
           ('maid', MAID, ('maid_start', 'maid_ill', 'maid_cured')),
           ('guard_night', GUARD_NIGHT, ('guard_night', 'guard_ill', 'guard_night')),
           ('king_night', KING_NIGHT, ('king_sleep', 'king_silent', 'king_sleep')))


def _sets(*flags):
    return ';'.join(f'{0x2190 + i:04X}|{m:02X}' for i, m in flags)


def state_messages(ctx):
    """{상태 이름: (SET, {(맵, FC 칸, 밤): 첫 메시지})}: 사건 뒤 flag 를 켜고 말을 걸 인물(dq4npccheck --states)."""
    m = ctx.msg
    santeem = lambda k: {(where[0], where[1], where[2] == 'night'): m[msgs[k]] for _, where, msgs in SANTEEM}  # noqa: E731
    won = {(mp, fc, time == 'night'): m[name] for (mp, time, fc), name in WON_TALK.items()}
    won.update({(ENDOR_CASTLE, fc, time == 'night'): m[who] for time, fc, _, _, _, who in CASTLE_WON if who})
    return {'king_ill': (_sets(king.BAZAAR), santeem(1)),
            'king_cured': (_sets(king.BAZAAR, king.CURED), santeem(2)),
            'champion': (_sets(endor.CHAMPION, endor.MESSENGER), won)}
