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
HOIMIN = (0x28, 0x01)           # 7E:21B8 bit0  호이민이 동료가 됨(FC $6281&40)
KIDNAPPED = (0x28, 0x20)        # 7E:21B8 bit5  탑 입구에서 마물이 아이를 끌고 감(FC $627E&01)

FRONT, FRONT_NIGHT, IMURU, JAIL = '36/00', '36/03', '37/00', '37/02'
UNDER_WELL, HOIMIN_ROOM = '3B/00', '3B/03'
TOWER_HALL = '39/00'
# FC 대화 번호
FC_KIDNAPPER = 0x45            # 탑 입구의 마물 그림(아이는 15)
FC_CHILD, FC_ALEX_NIGHT, FC_FLARE_DAY, FC_FLARE_NIGHT, FC_JAIL_FLARE, FC_HOIMIN = 0x12, 0x13, 0x0F, 0x10, 0x17, 0x15


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
    # 우물 아래의 아이 목소리(FC 1D 이벤트 05·0B, 02EC·02EE)
    'voice_here': say('이쪽으로 와……'),
    'voice_not': say('그쪽이 아니야.'),
    # FC 0793 → 예 0794(합류 서술) / 아니요 0795
    'hoimin_ask': say('나는 호이민./지금은 호이미/슬라임이지만/사람이 되는 게 꿈이야.',
                      '있잖아, 사람의/동료가 되면/사람이 될 수/있을까……?', '나를 동료로/삼아 줘!'),
    'hoimin_yes': say('야호! 고마워!')[:-1] + [ch1.PAGE] + ch1.narrate('호이민이 동료가 되었다!'),
    'hoimin_no': say('뭐? 안 된다고?/그래도 마음이 바뀌면/또 와 줘.'),
    # FC 02F4
    'kidnap': say('자, 따라와! 꼬마!', '으앙, 무서워!/놔 줘……!'),
}


def message_ids(first):
    """{이름: 메시지 번호}. first 는 옮긴 메시지 다음 번호(dq4npcport.FIRST_MESSAGE + 옮긴 메시지 수)."""
    return {name: first + k for k, name in enumerate(MESSAGES)}


def texts(first):
    return {first + k: parts for k, parts in enumerate(MESSAGES.values())}


TALKS = ('child', 'alex_night', 'flare_day', 'flare_night', 'hoimin')


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
        # 예면 합류 깃발. 일행 기록은 호이민 인물 스크립트가 그 깃발을 보고 쓴다(대화 네이티브는 뱅크 06 안이어야 함)
        [_msg(m['hoimin_ask']), {"op": "if", "cond": {"code": "05"},
                                 "then": [_msg(m['hoimin_yes']), _flag_on(HOIMIN)], "else": _msg(m['hoimin_no'])}],
    ]


# 인물 스크립트를 빌리는 DQ5 인물: 이 해킹에서 가지 않는 DQ5 03/03 의, 스크립트가 있는 한 벌(낮·밤 따로) 인물.
# 두 벌 인물은 한 시간대에만 둘 수 없다(dq5npcrelocate 가 거부)
FLARE_SRC, FLARE_SCRIPT = {"list": "05:9180", "index": 0}, "05:9187"
WALKER_SRC, WALKER_SCRIPT = {"list": "05:9180", "index": 1}, "05:919F"
VOICE_SRCS = ({"list": "05:9180", "index": 2}, "05:91B7"), ({"list": "05:9180", "index": 3}, "05:91CF")
HOIMIN_SRC, HOIMIN_SCRIPT = {"list": "05:9180", "index": 4}, "05:91EB"
KIDNAPPER_SRC, KIDNAPPER_SCRIPT = {"list": "05:9180", "index": 5}, "05:9207"
KID_SRC, KID_SCRIPT = {"list": "05:9239", "index": 1}, "05:9248"
# 탑 입구 30/00: 주인공이 이 줄(FC Y)에 오면 마물이 아이를 데리고 계단(09,03) 쪽으로 간다(FC 1D 이벤트 02)
KIDNAP_ROW, KIDNAP_TO = 0x09, 0x03
# 목소리가 나는 칸(FC 칸)과 메시지. FC 는 그 칸에서 왼쪽(05)·오른쪽(0B)을 보고 있을 때이고, そらとぶくつ 를
# 가졌으면 나지 않는다
VOICES = ((UNDER_WELL, (0x14, 0x0C), 'voice_here'), (HOIMIN_ROOM, (0x14, 0x10), 'voice_not'))

CODE_AT = 0x5ED000              # 서장 코드(5E:C000) 뒤의 빈 자리
COMPANION = 0x23AED1            # 동료 표: 종류마다 9바이트(처음 레벨, 최대 레벨, 능력치 넷, HP, MP, 장비 갈래)
HOIMIN_KIND = 0x05              # ホイミスライム. 이름 0 이 「ホイミン」
SCRATCH = 0x7E1BC6              # 7E:1BBE~ 의 DQ5 가 쓰지 않는 자리(서장이 1BC4 까지 씀)
# 동료가 된 スライム 의 일행 기록(sfc/dq5/tools/lua/dq5warp.lua 의 PARTY_TEMPLATE, 그 밖의 바이트는 동료 표에서)
PARTY_TEMPLATE = bytes((
    0x82, 0x80, 0x08, 0x00, 0x00, 0x00, 0x03, 0x08, 0x05, 0x01, 0x03, 0x00, 0x00, 0x00, 0x08, 0x00,
    0x00, 0x00, 0x01, 0x63, 0x00, 0x00, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF,
    0xFF, 0xFF, 0x00, 0x00, 0x00, 0x00, 0x4B, 0x00, 0x00, 0x02))


def lorom(addr):
    return (addr >> 16 & 0x7F) * 0x8000 + (addr & 0x7FFF)


def companion_record(data, kind):
    """동료 표의 처음 값으로 채운 일행 기록 42바이트."""
    c = data[lorom(COMPANION + kind * 9):][:9]
    r = bytearray(PARTY_TEMPLATE)
    r[0] = 0x80 | kind
    r[0x12], r[0x13] = c[0], c[1]
    r[7:11] = c[2:6]
    r[2] = r[0xE] = c[6]
    r[4] = r[0x10] = c[7]
    return bytes(r)


def _long(a):
    return [a & 0xFF, a >> 8 & 0xFF, a >> 16]


def _al(a):
    return bytes(_long(a))


def _join(record_at):
    """일행 끝(7E:201D 번째)에 record_at 의 기록을 넣고 수·순서를 고친다. 순서 7E:2020·2028 은 기록 번호,
    걷는 수 7E:201E 는 3 까지(넷째부터 마차). 7E:29EA + 종류 는 그 종류의 쓴 이름 비트로 읽음(코드 읽기)."""
    from dq4chapterbox import ENTER, LEAVE
    lo = record_at & 0xFFFF
    body = (bytes((0xC2, 0x30, 0xAF)) + _al(0x7E201D) + bytes((0x29, 0xFF, 0x00, 0x48,   # REP / LDA 수 / AND / PHA
            0x0A, 0x8F)) + _al(SCRATCH) + bytes((0x0A, 0x0A, 0x8F)) + _al(SCRATCH + 2) +   # 2n, 8n
            bytes((0x0A, 0x0A, 0x18, 0x6F)) + _al(SCRATCH) + bytes((0x6F,)) + _al(SCRATCH + 2) +  # 32n + 2n + 8n
            bytes((0x18, 0x69, 0x40, 0x20, 0xA8,                                         # + 2040 / TAY
                   0xA2, lo & 0xFF, lo >> 8, 0xA9, 41, 0x00, 0x54, 0x7E, record_at >> 16,  # LDX / LDA #41 / MVN
                   0x68, 0xE2, 0x20, 0xAA, 0x9F)) + _al(0x7E2020) + bytes((0x9F,)) + _al(0x7E2028) +  # PLA / SEP / TAX
            bytes((0x1A, 0x8F)) + _al(0x7E201D) + bytes((0x8F,)) + _al(0x7E201F) +       # INC / 수 둘
            bytes((0xC9, 0x04, 0x90, 0x02, 0xA9, 0x03, 0x8F)) + _al(0x7E201E) +           # 걷는 수
            bytes((0xAF,)) + _al(0x7E29EA + HOIMIN_KIND) + bytes((0x09, 0x01, 0x8F)) + _al(0x7E29EA + HOIMIN_KIND))
    return ENTER + body + LEAVE


def _at(x, y):
    """인물 명령 05 가 부르는 루틴: 주인공(인물 표 슬롯 0, 7E:3020·3080)이 셀 (x, y) 이면 A = 0, 아니면 1.
    x 가 None 이면 Y 만 본다."""
    near = bytes((0xC2, 0x30, 0xA9, 0x00, 0x00, 0x28, 0x6B))
    far = bytes((0xC2, 0x30, 0xA9, 0x01, 0x00, 0x28, 0x6B))
    second = bytes((0xAF, 0x80, 0x30, 0x7E, 0xC9, y, 0xD0, len(near)))
    first = bytes((0x08, 0xE2, 0x20))
    if x is not None:
        first += bytes((0xAF, 0x20, 0x30, 0x7E, 0xC9, x, 0xD0, len(second) + len(near)))
    return first + second + near + far


# そらとぶくつ: DQ5 의 처리(11:8D77)는 $0B54 = 24 와 필드 (017E,0170)를 두고 날기 루틴(11:80D3)으로 간다.
# FC(12:$B14B)는 필드 (88,16)으로 날아간 뒤 탑 30/00 (09,0C)에 세운다. 첫 명령을 JSL 로 바꿔 이벤트(맵 옮기기)를
# 걸고, 날아가는 곳을 탑 그룹과 그 필드 칸으로 한다
FLY_AT = 0x118D77
FLY_ORIG = bytes.fromhex('a9 24 8d 54 0b')          # LDA #$24 / STA $0B54
FLY_X_AT, FLY_Y_AT = 0x118D7F, 0x118D87
FLY_XY_ORIG = (bytes.fromhex('7e 01'), bytes.fromhex('70 01'))
TOWER, TOWER_FIELD, TOWER_IN = 0x39, (0x88, 0x16), (0x00, 0x09, 0x0C)


def _fly(event):
    from dq4chapterbox import ENTER, LEAVE
    import dq4prologue
    start = dq4prologue._event_start(event)[len(ENTER):-len(LEAVE)]
    return ENTER + start + bytes((0xA9, TOWER, 0x8D, 0x54, 0x0B)) + LEAVE


def native(data=None):
    """(바이트, {이름: 주소}). 기록 자료가 앞, 루틴이 뒤. 주소는 data(롬, 동료 표를 읽음)와 상관없다."""
    record = companion_record(data, HOIMIN_KIND) if data is not None else bytes(len(PARTY_TEMPLATE))
    out, at = bytearray(record), {'record': CODE_AT}
    at['join'] = CODE_AT + len(out)
    out += _join(CODE_AT)
    for m, (x, y), _ in VOICES:
        at[m] = CODE_AT + len(out)
        out += _at(*ch1_cell(x, y))
    at['kidnap_row'] = CODE_AT + len(out)
    out += _at(None, ch1_cell(0, KIDNAP_ROW)[1])
    at['fly_event'] = CODE_AT + len(out)
    number, x, y = TOWER_IN
    out += bytes((0x90, TOWER, number, *ch1_cell(x, y), 0x01, 0x80, 0xFF))
    at['fly'] = CODE_AT + len(out)
    out += _fly(at['fly_event'])
    return bytes(out), at


def ch1_cell(x, y):
    """FC 칸에 선 주인공의 DQ5 셀."""
    return x * 2, y * 2 + 1


def apply(data):
    d = bytearray(data)
    code, _ = native(data)
    o = lorom(CODE_AT)
    if any(d[o:o + len(code)]):
        raise SystemExit(f'{CODE_AT:06X}: 비어 있지 않은 자리')
    d[o:o + len(code)] = code
    _, at = native()
    fx, fy = TOWER_FIELD[0] * 2, TOWER_FIELD[1] * 2      # FC 필드 칸 → DQ5 필드 좌표(그룹 연결의 필드 입구와 같은 셈)
    for addr, orig, new in ((FLY_AT, FLY_ORIG, bytes((0x22, *_long(at['fly']), 0xEA))),
                            (FLY_X_AT, FLY_XY_ORIG[0], fx.to_bytes(2, 'little')),
                            (FLY_Y_AT, FLY_XY_ORIG[1], fy.to_bytes(2, 'little'))):
        o = lorom(addr)
        if bytes(d[o:o + len(orig)]) != orig:
            raise SystemExit(f'{addr:06X}: 원래 바이트가 아님 {d[o:o + len(orig)].hex()}')
        d[o:o + len(new)] = new
    return bytes(d)
REUNION_AT = (0x04, 0x03)       # FC 슬롯 07 이 걸어가 서는 칸, 재회 뒤 슬롯 08 의 자리


def _cmd(op, *args):
    return {"op": op, "args": list(args)}


def scripts(first_message):
    m = message_ids(first_message)
    _, at = native()
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
    ] + [
        # 보이지 않는 인물이 칸을 기다렸다가 목소리를 띄운다. 52 로 자리를 치워 길을 막지 않는다
        {"address": script, "commands": [_cmd('28'), _cmd('52'), _cmd('05', *_long(at[where])), _cmd('3F'),
                                         _cmd('21', lo(m[msg]), hi(m[msg])), _cmd('40'), _cmd('16')]}
        for (_, script), (where, _, msg) in zip(VOICE_SRCS, VOICES)
    ] + [
        # 예라고 대답하면(합류 깃발) 일행 기록을 쓰고 사라진다
        {"address": HOIMIN_SCRIPT, "commands": [_cmd('09', 0x80 | HOIMIN[0], HOIMIN[1]), _cmd('37', *_long(at['join'])),
                                                _cmd('28'), _cmd('52'), _cmd('16')]},
    ] + [
        # 마물이 말하고 납치 깃발을 켜면 아이도 함께 계단 쪽으로 걸어가 사라진다
        {"address": KIDNAPPER_SCRIPT, "commands": [
            _cmd('05', *_long(at['kidnap_row'])), _cmd('3F'), _cmd('21', lo(m['kidnap']), hi(m['kidnap'])),
            _cmd('10', *KIDNAPPED)] + _walk_off(9) + [_cmd('40'), _cmd('16')]},
        {"address": KID_SCRIPT, "commands": [_cmd('09', 0x80 | KIDNAPPED[0], KIDNAPPED[1])] + _walk_off(8) + [_cmd('16')]},
    ]


def _walk_off(x):
    """탑 입구에서 열 x 를 따라 KIDNAP_TO 줄까지 올라가 숨고 자리를 치운다."""
    return [_cmd('13', x * 2, KIDNAP_TO * 2 + 1), _cmd('14'), _cmd('28'), _cmd('52')]


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
    # 우물 아래: 목소리 인물을 더하고, 호이민은 합류하면 빠진 목록으로
    for (src, _), (where, (x, y), _) in zip(VOICE_SRCS, VOICES):
        cx, cy = ch1_cell(x, y)
        voice = {"from": src, "fields": {"x": cx, "y": cy, "facing": "down", "talk": t['hoimin'], "gfx": 0x01,
                                         "layer": 0}}
        lists[where] += [{**voice, "time": "day"}, {**voice, "time": "night"}]
    room = lists[HOIMIN_ROOM]
    hoimins = [i for i, p in enumerate(report[HOIMIN_ROOM]) if p["talk"] == FC_HOIMIN]
    gone = [e for i, e in enumerate(room) if i not in hoimins]
    for i in hoimins:
        room[i] = _same(room[i], HOIMIN_SRC, t['hoimin'])
    new_lists.append({"name": "hoimin_gone", "entries": gone})
    # 탑 입구: 마물(그림 45)과 아이(15)를 스크립트 인물로, 끌고 간 뒤에는 빈 목록
    hall = lists[TOWER_HALL]
    for i, p in enumerate(report[TOWER_HALL]):
        src = KIDNAPPER_SRC if p["picture"] == FC_KIDNAPPER else KID_SRC
        hall[i] = _same(hall[i], src, hall[i]["fields"]["talk"])
    new_lists.append({"name": "hall_empty", "entries": []})
    over = lambda m, flag, name: {"map": m, "flag": flag[0], "when": "on", "mask": flag[1], "list": f"new:{name}"}  # noqa: E731
    # 앞에 둔 것부터 맞춰 본다
    overrides = [over(JAIL, REUNITED, 'jail_after'), over(JAIL, FLARE_FOLLOWS, 'jail_reunion'),
                 over(HOIMIN_ROOM, HOIMIN, 'hoimin_gone'), over(TOWER_HALL, KIDNAPPED, 'hall_empty')]
    return [{"map": k, "entries": v} for k, v in lists.items()], new_lists, overrides
