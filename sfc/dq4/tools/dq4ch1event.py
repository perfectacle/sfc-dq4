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

FRONT, FRONT_NIGHT, IMURU, JAIL = '36/00', '36/03', '37/00', '37/02'
# FC 대화 번호
FC_CHILD, FC_ALEX_NIGHT, FC_FLARE_DAY, FC_FLARE_NIGHT, FC_JAIL_FLARE = 0x12, 0x13, 0x0F, 0x10, 0x17


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
}


def message_ids(first):
    """{이름: 메시지 번호}. first 는 옮긴 메시지 다음 번호(dq4npcport.FIRST_MESSAGE + 옮긴 메시지 수)."""
    return {name: first + k for k, name in enumerate(MESSAGES)}


def texts(first):
    return {first + k: parts for k, parts in enumerate(MESSAGES.values())}


TALKS = ('child', 'alex_night', 'flare_day', 'flare_night')


def talk_numbers(first_talk):
    """{이름: 대화 번호}. first_talk 는 서장 스크립트 다음 번호."""
    return {name: first_talk + k for k, name in enumerate(TALKS)}


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
    ]


# 인물 스크립트를 빌리는 DQ5 인물: 이 해킹에서 가지 않는 DQ5 03/03 의, 스크립트가 있는 한 벌(낮·밤 따로) 인물.
# 두 벌 인물은 한 시간대에만 둘 수 없다(dq5npcrelocate 가 거부)
FLARE_SRC, FLARE_SCRIPT = {"list": "05:9180", "index": 0}, "05:9187"
WALKER_SRC, WALKER_SCRIPT = {"list": "05:9180", "index": 1}, "05:919F"
REUNION_AT = (0x04, 0x03)       # FC 슬롯 07 이 걸어가 서는 칸, 재회 뒤 슬롯 08 의 자리


def _cmd(op, *args):
    return {"op": op, "args": list(args)}


def scripts(first_message):
    m = message_ids(first_message)
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
    ]


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
    lists = {lst["map"]: [dict(e) for e in lst["entries"]] for lst in ported}

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
    over = lambda flag, name: {"map": JAIL, "flag": flag[0], "when": "on", "mask": flag[1], "list": f"new:{name}"}  # noqa: E731
    # 앞에 둔 것부터 맞춰 본다
    overrides = [over(REUNITED, 'jail_after'), over(FLARE_FOLLOWS, 'jail_reunion')]
    return [{"map": k, "entries": v} for k, v in lists.items()], new_lists, overrides
