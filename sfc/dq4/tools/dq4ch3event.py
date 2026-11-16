"""DQ4 3장 「무기상인 톨네코」 넘김과 첫머리: 2장 끝에서 3장으로 넘어가 레이크나바 톨네코 집(3E/01)에서 시작한다.

2장 끝 서술 뒤(dq4ch2ending 의 끝내는 인물, --chapter3 빌드) 네이티브 transfer 가 아리나 일행 기록을 맡기고 일행을
톨네코 하나로 바꾼 뒤(주인공 기록 0 을 톨네코로 덮음) 이벤트 스크립트로 3E/01 에 옮긴다. 그 맵은 검게 불러오고
(dq4chapterbox.CHAPTER3), 네네 자리의 인물 스크립트가 3장 제목 상자 → FC 서두 서술 → 맵 밝히기 → 네네의 부름 →
방향 키를 기다림 → 네네가 깨우는 말을 돌린다. 3장 코드는 빌드 옵션과 상관없이 늘 들어가고, --chapter3 는 2장 끝
인물이 이 transfer 를 부를지(아니면 「다음에 계속」 끝 상자)만 고른다.

3장 사건은 모듈(dq4ch3slots.SLOTS 의 module)로 꽂는다. 모듈 파일이 있으면 EVENTS 에 들고, 메시지·대화·대화 호출 번호를
등록 차례로 이어 매긴다. 여러 모듈이 함께 쓰는 장치(금화 내고 받기, 물건 주고 빼기)는 대화 호출 표로 부른다(뱅크 06
의 입구 하나가 인자 첫 바이트로 표 칸을 고름). 형식은 sfc/dq4/docs/dq4-chapter3-format.md.
"""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4chapter1 as ch1  # noqa: E402
import dq4ch2event as ch2  # noqa: E402
from dq4chapterbox import DB0, ENTER, LEAVE  # noqa: E402
from dq4ch3slots import SLOTS, VARS_AT  # noqa: E402

# 7E:2208 은 DQ5 가 색인 쓰기로만 덮는 자리(dq4ch2slots 「flag 자리」). 2장 첫머리·텐페·사건 전투가 bit0·1·2·4·6·7 을 쓴다
CHAPTER3 = (0x78, 0x08)        # 7E:2208 bit3  3장 진행 중(2장 끝에서 켬). 주인공 그림·성장·장비를 톨네코로
OPENING = (0x78, 0x20)         # 7E:2208 bit5  3장 첫머리(제목 상자·서두·네네)를 기다림. 옮길 때 켜고 첫머리 끝에 끔
# 7E:21A3 bit5(맵을 옮기면 지워짐): 첫머리가 끝난 뒤 아직 집을 다시 불러오지 않음. FC 는 맵에 들 때마다 $628B 를 FF 로
# 쓰고 네네(대화 057)가 bit6 이 꺼져 있으면 「집을 나서면 곧장 서쪽으로」(080A)라 하므로, 첫머리 직후에만 그 말이다
FRESH = (0x13, 0x20)

HOUSE = '3E/01'                # FC 16/01 레이크나바 톨네코의 집
START_CELL = (0x1B * 2, 0x05 * 2 + 1)    # FC 3장 시작 (1B,05)
NENE_CELL = (0x1B * 2, 0x04 * 2 + 1)     # 옮긴 네네(FC 슬롯 0A, 낮): 시작 칸 바로 위
CASTLE = ch2.CASTLE
# 스크립트를 빌리는 인물: 이 해킹에서 가지 않는 DQ5 2B/00 의, 낮에만 놓이는 한 벌짜리 스크립트 인물(스크립트 80바이트).
# dq4ch2slots 의 어느 세션 목록도 아니다
OPENER_SRC, OPENER_SCRIPT = {"list": "05:CC73", "index": 0}, "05:CC7A"

CODE_AT, CODE_END = 0x5CC000, 0x5CD000   # dq4ch2slots.CHAPTER3_CODE
# 대화 호출 표(4바이트 칸: 주소 3·인자 1). 그 앞까지가 넘김·공용 장치 네이티브
TABLE_AT = 0x5CCC00
TORNEKO_PICTURE = 0x7A         # 3장 동안 주인공 그림: DQ4 가 쓰지 않는 DQ5 그림(세트 46, 37타일)에 NDS 톨네코를 싣는다
TORNEKO_NAME = '톨네코'
FC_TORNEKO = 5                 # dq4growth.FC_TORNEKO
# FC 3장 시작: 금화 0, 귀환 자리 12(16/00 교회), 다녀온 비트 $6165 = 40(그룹 16). fc/dq4/tools/dq4event.py chapters
GOLD = 0
CHURCH_FC, VISITED_FC = 0x16, (0x16,)
SONG_STOP = 0x24FE91           # 2장 끝 엔딩 곡을 멈춘다(dq4ch2ending.SONG_STOP)

PARTY_AT, NAME_AT, GOLD_AT = ch2.PARTY_AT, ch2.NAME_AT, ch2.GOLD_AT
# 아리나 일행 기록 셋(42바이트씩)과 아리나 이름을 맡겨 두는 곳: DQ5 맡긴 몬스터 칸(7E:2332, 26바이트 × 56)의 끝 칸
# 여섯. 이 해킹은 몬스터를 맡기지 않고(일행이 차는 일이 없음), 칸은 앞에서부터 찬다. 칸 첫 바이트 bit7 이 찬 칸
# 표시라 칸마다 +1 부터 25바이트씩 둔다. 7E:2000~2A9F 안이라 저장 기록에 남는다
MONSTER_SLOTS, MONSTER_SLOT, MONSTER_COUNT = 0x7E2332, 26, 56
STASH_FIRST = 50
STASH_PARTY = 3


def stash_pieces():
    """[(원본 주소, 맡길 주소, 바이트 수)]: 일행 기록 0~2 와 이름을 칸마다 +1 부터 25바이트씩 잘라 넣는다."""
    stream = [(PARTY_AT, 42 * STASH_PARTY), (NAME_AT, 8)]
    room = MONSTER_SLOT - 1
    out, slot, used = [], STASH_FIRST, 0
    for src, n in stream:
        while n:
            take = min(n, room - used)
            out.append((src, MONSTER_SLOTS + slot * MONSTER_SLOT + 1 + used, take))
            src, n, used = src + take, n - take, used + take
            if used == room:
                slot, used = slot + 1, 0
    last = out[-1][1] + out[-1][2] - 1
    if last >= MONSTER_SLOTS + MONSTER_COUNT * MONSTER_SLOT:
        raise ValueError('맡길 칸이 모자람')
    return out


def _fc_items(dq4):
    """FC 3장 시작 소지품(12:$9192 + 8 × 5)을 [(FC 이름, 장비 여부)]로."""
    import dq4growth
    dq4data, prg = dq4growth._fc(dq4)
    import dq4event
    names = {i: n for i, n, *_ in dq4data.items(prg)}
    raw = [dq4event.rd(prg, dq4event.INIT, dq4event.CHAR_ITEMS + 8 * FC_TORNEKO + k) for k in range(8)]
    return [(names[b & 0x7F], bool(b & 0x80)) for b in raw if b != 0xFF]


def start(dq5, dq4):
    """FC 3장 시작 톨네코: {'hp', 'mp', 'agility', 'stats', 'next', 'items': [(DQ5 물건, 장비)], 'dropped': [FC 이름]}.
    값은 FC 장 시작 루틴과 같은 dq4growth.first_record, 소지품은 FC 표. 사건 물건(おべんとう)은 dq4itemport 의 자리로.
    DQ5 에 같은 이름도 사건 물건 자리도 없는 물건은 dropped."""
    import dq4growth
    import dq4shopport
    from dq5map import Rom
    import dq4itemport
    first = dq4growth.first_record(dq4, FC_TORNEKO)
    known = dq4shopport.dq5_items(Rom(Path(dq5).read_bytes() if not isinstance(dq5, (bytes, bytearray)) else dq5))
    known.update({dq4shopport._fold(name): item for item, name in dq4itemport.EVENT_ITEMS.items()})
    items, dropped = [], []
    for name, worn in _fc_items(dq4):
        key = dq4shopport._fold(name)
        if key in known:
            items.append((known[key], worn))
        else:
            dropped.append(name)
    return {'hp': first['hp'], 'mp': first['mp'], 'agility': first['agi'],
            'stats': (first['str'], first['vit'], first['int'], first['luck']), 'next': first['next'],
            'items': items, 'dropped': dropped}


def torneko_record(hero, s):
    """원래 롬의 주인공 기록 틀(23:C014 칸 0)을 톨네코 1레벨로. 장비 비트는 FC 표의 장비 표시를 따른다."""
    r = bytearray(ch2.level_one(hero, s, tuple(i for i, _ in s['items'])))
    r[0x14:0x16] = sum(1 << k for k, (_, worn) in enumerate(s['items']) if worn).to_bytes(2, 'little')
    return bytes(r)


_al, _mvn, _flag_or = ch2._al, ch2._mvn, ch2._flag_or


def _flag_off(flag):
    a = 0x7E2190 + flag[0]
    return bytes((0xAF,)) + _al(a) + bytes((0x29, ~flag[1] & 0xFF, 0x8F)) + _al(a)


def _transfer(record_at, name_at, event_at):
    """2장 끝에서 부른다: 아리나 일행 기록·이름을 맡기고, 일행을 톨네코 하나로, 맡긴 물건·금화를 비우고, 금화 0, 아침,
    귀환 자리를 3장 것으로 두고, 2장 flag 를 끄고 3장 flag 를 켠 뒤 엔딩 곡을 멈추고 3E/01 로 옮기는 이벤트를 건다."""
    import dq4fieldtravel
    import dq4prologue
    body = bytearray(bytes((0xC2, 0x30)))
    for src, dst, n in stash_pieces():
        body += _mvn(src, dst, n)
    body += _mvn(record_at, PARTY_AT, 42) + _mvn(name_at, NAME_AT, 8)
    # 첫 두 칸을 0 으로 두고 한 칸 뒤로 베껴 나가면 MVN 이 0 을 끝까지 민다(dq4ch2event._transfer 와 같음)
    body += bytes((0xA9, 0x00, 0x00, 0x8F)) + _al(ch2.BANK_ITEMS_AT)
    body += _mvn(ch2.BANK_ITEMS_AT, ch2.BANK_ITEMS_AT + 1, ch2.BANK_ITEMS - 1)
    body += bytes((0xA9, 0x00, 0x00, 0x8F)) + _al(ch2.BANK_GOLD_AT)
    body += bytes((0xA9, *ch2.MORNING.to_bytes(2, 'little'), 0x8F)) + _al(ch2.TIME_AT)
    body += bytes((0xA9, *(GOLD & 0xFFFF).to_bytes(2, 'little'), 0x8F)) + _al(GOLD_AT)
    body += bytes((0xE2, 0x20, 0xA9, GOLD >> 16, 0x8F)) + _al(GOLD_AT + 2)
    body += dq4fieldtravel.chapter_slot_code(CHURCH_FC, VISITED_FC)
    for a in (0x7E201D, 0x7E201E, 0x7E201F):
        body += bytes((0xA9, 0x01, 0x8F)) + _al(a)
    for a in (0x7E2020, 0x7E2028):
        body += bytes((0xA9, 0x00, 0x8F)) + _al(a)
    body += bytes((0xAF,)) + _al(0x7E201C) + bytes((0x29, 0x7F, 0x8F)) + _al(0x7E201C)
    body += _flag_off(ch2.CHAPTER2) + _flag_or(CHAPTER3) + _flag_or(OPENING)
    # MVN 이 DB 를 7E 로 두었다. 곡 멈춤·이벤트 걸기는 DB 0 에서
    body += DB0 + bytes((0x22,)) + _al(SONG_STOP)
    start_event = dq4prologue._event_start(event_at)[len(ENTER):-len(LEAVE)]
    return ENTER + bytes(body) + start_event + LEAVE


def _pad():
    """인물 명령 05: 방향 키(자동 조이패드 읽기 $4219 아래 4비트)가 눌려 있으면 A = 0, 아니면 1. FC 이벤트 2F 와 같이
    방향 키 하나로 넘어간다."""
    return bytes((0x08, 0xE2, 0x20, 0xAF, 0x19, 0x42, 0x00, 0x29, 0x0F, 0xF0, 0x07,
                  0xC2, 0x30, 0xA9, 0x01, 0x00, 0x28, 0x6B,
                  0xC2, 0x30, 0xA9, 0x00, 0x00, 0x28, 0x6B))


def native(data=None, dq4=None):
    """(바이트, {이름: 주소}). data: 원래 DQ5 롬(기록 틀), dq4: FC 롬 경로. 없으면 기록을 0 으로 채워 주소만 센다."""
    if data is not None:
        out = bytearray(torneko_record(ch2.person_record(data, 0), start(data, dq4)))
    else:
        out = bytearray(42)
    at = {'record': CODE_AT, 'name': CODE_AT + len(out)}
    out += ch2.name_bytes(TORNEKO_NAME)
    g, n = (int(v, 16) for v in HOUSE.split('/'))

    def put(name, code):
        at[name] = CODE_AT + len(out)
        out.extend(code)
    # 맵 곡 건너뛰기를 켜는 2장 네이티브를 함께 쓴다(제목 상자·서술 동안 곡이 없고 맵 밝히기가 끈다)
    put('event', bytes((0xA0, *_al(ch2.native()[1]['skip_song']), 0x90, g, n, *START_CELL, 0x01, 0x80, 0xFF)))
    put('transfer', _transfer(at['record'], at['name'], at['event']))
    put('pad', _pad())
    put('amounts', b''.join(v.to_bytes(3, 'little') for v in AMOUNTS))
    put('dispatch', _dispatch())
    for name, make in COMMON_ROUTINES.items():
        put(name, make(at))
    if CODE_AT + len(out) > TABLE_AT:
        raise SystemExit(f'3장 네이티브 {len(out)}바이트가 대화 호출 표 {TABLE_AT:06X} 를 넘음')
    return bytes(out), at


# FC 메시지(031C·031E·031F)를 옮겼다. 서술은 해라체, 인물은 입말
MESSAGES = {
    # FC 031C
    'opening': ch1.narrate('여기는 엔돌에서/아득히 북쪽에 있는/작은 마을 레이크나바.',
                           '이 마을에는/톨네코라는/한 남자가 살고 있었다.',
                           '지금은 그저/남의 밑에서/일하는 몸이지만……',
                           '돈을 모아 세계 제일의/무기상인이 되는 것,/그것이 톨네코의/꿈이었다.'),
    # FC 031E
    'nene_call': ch2._speaker_pages('네네', '여보, 언제까지/자고 있을 거예요?/빨리 가게에 안 가면/또 주인어른한테 혼나요.',
                                    '저기, 여보도 참……'),
    # FC 031F
    'nene_wake': ch2._speaker_pages('네네', '이제야 일어났네요./자, 여기 도시락.',
                                    '집을 나서면/졸지 말고/곧장 서쪽으로/걸어가요.',
                                    '그럼 오늘도/힘내고 와요.'),
}


def message_ids(first):
    return {name: first + k for k, name in enumerate(MESSAGES)}


def texts(first):
    out = {first + k: parts for k, parts in enumerate(MESSAGES.values())}
    for ctx in contexts(first):
        out.update({ctx.msg[name]: parts for name, parts in getattr(ctx.module, 'MESSAGES', {}).items()})
    return out


def message_count():
    """이 모듈과 사건 모듈의 메시지 수(4장 메시지는 그 뒤부터)."""
    return len(MESSAGES) + sum(len(getattr(mod, 'MESSAGES', {})) for _, mod in modules())


def _cmd(op, *args):
    return {"op": op, "args": list(args)}


def scripts(first_message, native_points):
    """인물 스크립트. native_points: dq4chapterbox.entry_points 의 {이름: 주소}(box3·reveal). 사건 모듈의 것은 뒤에."""
    m = message_ids(first_message)
    _, at = native()
    msg = lambda k: _cmd('21', m[k] & 0xFF, m[k] >> 8)  # noqa: E731
    return [{"address": OPENER_SCRIPT, "commands": [
        _cmd('3F'), _cmd('37', *_al(native_points['box3'])), msg('opening'),
        _cmd('37', *_al(native_points['reveal'])), msg('nene_call'),
        _cmd('05', *_al(at['pad'])), msg('nene_wake'), _cmd('10', *FRESH),
        _cmd('11', OPENING[0], ~OPENING[1] & 0xFF), _cmd('40'), _cmd('16')]}] + \
        [s for ctx in contexts(first_message, points=native_points) if hasattr(ctx.module, 'scripts')
         for s in ctx.module.scripts(ctx)]


def npc_lists(ported, first_talk=None):
    """(새 목록, 조건). 첫머리를 기다리는 동안의 3E/01 은 옮긴 목록에서 낮의 네네만 연출 인물로 바꾼다. 3장 동안의
    산트하임 성 앞마당은 2장 끝의 빈 성 목록이다(2장을 끝내는 인물이 다시 서지 않게). 그 뒤 사건 모듈이 ported 의
    목록을 고치고(대화 바꾸기) 새 목록·조건을 더한다. first_talk 는 3장 첫 대화 번호(dq4chapter1.chapter3_talk)."""
    lists = {lst["map"]: lst for lst in ported if "map" in lst}
    if HOUSE not in lists:
        return [], []           # 인물 없이 옮긴 목록(dq4npcport.port 의 with_people=False)
    hit = 0
    opening = []
    for e in lists[HOUSE]["entries"]:
        f = e["fields"]
        if (f["x"], f["y"]) == NENE_CELL and e["time"] == "day":
            e = {**e, "from": OPENER_SRC, "fields": {**f, "interval": max(1, f.get("interval", 1))}}
            hit += 1
        opening.append(e)
    if hit != 1:
        raise SystemExit(f'{HOUSE} {NENE_CELL}: 첫머리를 맡길 네네가 {hit}명')
    import dq4ch2ending as ending
    on = lambda mp, flag, name: {"map": mp, "flag": flag[0], "when": "on", "mask": flag[1], "list": f"new:{name}"}  # noqa: E731
    over = [on(HOUSE, OPENING, 'ch3_opening'), on(CASTLE, CHAPTER3, ending.EMPTY_CASTLE)]
    new = [{"name": "ch3_opening", "entries": opening}]
    more_new, more_over = module_lists(lists, first_talk, new, over)
    # 첫머리가 끝나도 맵을 다시 불러오기 전까지는 연출을 맡은 네네가 그대로 서 있다. 사건 모듈이 바꾼 낮 네네의 대화를
    # 그 인물에도 준다
    talk = next(e["fields"]["talk"] for e in lists[HOUSE]["entries"]
                if (e["fields"]["x"], e["fields"]["y"]) == NENE_CELL and e["time"] == "day")
    for k, e in enumerate(opening):
        if e.get("from") == OPENER_SRC:
            opening[k] = {**e, "fields": {**e["fields"], "talk": talk}}
    # 대체 표는 앞 줄부터 맞는 첫 줄을 쓴다. 모듈이 first 를 단 줄은 첫머리 목록 따위보다 앞에 둔다
    first = [{k: v for k, v in o.items() if k != 'first'} for o in more_over if o.get('first')]
    return new + more_new, first + over + [o for o in more_over if not o.get('first')]


def apply(data, original, dq4, first_message=None):
    """original: 원래 DQ5 롬(기록 틀), dq4: FC 롬 경로(톨네코 시작 값·소지품), first_message: 3장 메시지 첫 번호
    (dq4chapter1.chapter3_message, 사건 모듈 네이티브의 이벤트가 메시지를 띄울 때). 넘김·공용 장치, 대화 호출 표와 입구,
    사건 모듈의 네이티브·훅을 쓴다."""
    d = bytearray(data)
    code, _ = native(original, dq4)
    places = [(CODE_AT, code), (TABLE_AT, call_table()), (STUB_AT, stub())]
    hooks = []
    for ctx in contexts(first_message, original=original):
        if hasattr(ctx.module, 'native'):
            more, _ = ctx.module.native(ctx)
            start, end = ctx.slot.code
            if start + len(more) > end:
                raise SystemExit(f'{ctx.key}: 사건 코드 {len(more)}바이트가 예약 {start:06X}~{end - 1:06X} 를 넘음')
            places.append((start, more))
        if hasattr(ctx.module, 'hooks'):
            hooks += ctx.module.hooks(ctx)
    if TABLE_AT + len(places[1][1]) > CODE_END:
        raise SystemExit(f'대화 호출 표 {len(places[1][1]) // 4}칸이 {TABLE_AT:06X}~{CODE_END - 1:06X} 를 넘음')
    for addr, blob in places:
        o = ch1.lorom(addr)
        if any(d[o:o + len(blob)]):
            raise SystemExit(f'{addr:06X}: 비어 있지 않은 자리')
        d[o:o + len(blob)] = blob
    for addr, orig, new in hooks:
        o = ch1.lorom(addr)
        if bytes(d[o:o + len(orig)]) != orig:
            raise SystemExit(f'{addr:06X}: 원래 바이트가 아님 {d[o:o + len(orig)].hex()}')
        d[o:o + len(new)] = new
    return bytes(d)


# ---- 사건 등록 ----

# 공용 flag(dq4ch3slots.COMMON_FLAGS 의 6F). RESULT 는 마지막 대화 호출의 결과(pay: 냄). 동행 비트는 붙이기·떼기 장치가
# 아직 없어 자리만 둔다: DOG 은 개 토마스가 따라옴(FC $6286&04), SCOTT·LAWRENCE 는 용병을 고용함(FC $628E&80·40)
RESULT = (0x6F, 0x01)
DOG = (0x6F, 0x02)
SCOTT = (0x6F, 0x04)
LAWRENCE = (0x6F, 0x08)
# 공용 변수 칸(dq4ch3slots.COMMON_VARS): 용병 날수(FC $628C·$628D), 날이 바뀐 것을 알 시계
SCOTT_DAYS, LAWRENCE_DAYS, CLOCK = VARS_AT, VARS_AT + 1, VARS_AT + 2

# 금화 값 표(pay·earn 의 인자). FC 3장의 값: 가게 35000, 여신상 25000, 굴 공사·납품 60000, 용병 400·600, 떠돌이 여관 10
AMOUNTS = (35000, 25000, 60000, 400, 600, 10)
GOLD_AT = ch2.GOLD_AT
PARTY_ITEMS = ch2.PARTY_AT + 0x16          # 일행 기록마다 가진 물건 12칸, 그 앞 +14 가 장비 비트(16비트)
EQUIP = ch2.PARTY_AT + 0x14
RECORD, ITEM_SLOTS = 42, 12
PARTY_MAX = 4                              # 물건을 뺄 때 볼 일행 기록 수(톨네코와 동행)
BAG = 0x7E2250                             # 맡긴 물건(물건 번호마다 개수)
ARG = 0x7E0F31                             # 대화 call 의 둘째 인자 자리(06:B143). 입구가 표 칸의 인자로 덮는다

# 대화 호출 입구: 뱅크 06 의 빈 자리(원래 DQ5 06:FDF8~ 0, 그 뒤 06:FE10 은 대화 훅). 대화 스크립트의 call 은 뱅크 06
# 주소만 받으므로 입구 하나에 인자 첫 바이트(7E:0F30)로 표 칸을 고른다. 2장의 칸마다 입구(dq4ch2battle.STUBS)와 달리
# 칸 수가 표 자리만큼 는다
STUB_AT = 0x06FE00
STUB_END = 0x06FE10


def stub():
    """대화 call 이 JSR 로 부르는 입구: P·A·X·Y 를 지키고 dispatch 로."""
    return bytes((0x08, 0xC2, 0x30, 0x48, 0xDA, 0x5A, 0x22)) + _al(native()[1]['dispatch']) + \
        bytes((0x7A, 0xFA, 0x68, 0x28, 0x60))


def _dispatch():
    """M·X 16 에서 JSL 로 들어와 표 칸(7E:0F30 × 4)의 인자를 7E:0F31 에 두고 칸의 주소로 뛴다(RTL 로 뛰므로 그 루틴의
    RTL 이 입구로 돌아간다). 칸 번호는 빌드가 매기므로 범위를 보지 않는다."""
    t = TABLE_AT
    return (bytes((0x08, 0xC2, 0x30, 0xAF, 0x30, 0x0F, 0x7E, 0x29, 0xFF, 0x00, 0x0A, 0x0A, 0xAA, 0x28,
                   0xE2, 0x20, 0xBF)) + _al(t + 3) + bytes((0x8F,)) + _al(ARG) +
            bytes((0xBF,)) + _al(t + 2) + bytes((0x48, 0xC2, 0x20, 0xBF)) + _al(t) + bytes((0x3A, 0x48, 0x6B)))


def _asm():
    from dq4ch2endor import Asm
    return Asm()


def _give(at):
    """물건(인자)을 일행(7E:201D 명) 가운데 가진 물건 칸이 빈 첫 사람에게, 모두 차 있으면 맡긴 물건에 하나 더한다."""
    from dq4ch2endor import BEQ, BNE, BRA
    a = _asm()(ENTER, 0xA9, 0x7E, 0x48, 0xAB)                                   # DB 7E
    a(0xAD, 0x1D, 0x20).br(BEQ, 'bag')(0x48, 0xA2, *(PARTY_ITEMS & 0xFFFF).to_bytes(2, 'little'))
    a.label('rec')(0xA0, ITEM_SLOTS, 0x00)
    a.label('slot')(0xBD, 0x00, 0x00, 0xC9, 0xFF).br(BEQ, 'hit')(0xE8, 0x88).br(BNE, 'slot')
    a(0xC2, 0x20, 0x8A, 0x18, 0x69, RECORD - ITEM_SLOTS, 0x00, 0xAA, 0xE2, 0x20)  # X += 30
    a(0xA3, 0x01, 0x3A, 0x83, 0x01).br(BNE, 'rec')(0x68).br(BRA, 'bag')
    a.label('hit')(0x68, 0xAD, *(ARG & 0xFFFF).to_bytes(2, 'little'), 0x9D, 0x00, 0x00).br(BRA, 'end')
    a.label('bag')(0xC2, 0x20, 0xAD, *(ARG & 0xFFFF).to_bytes(2, 'little'), 0x29, 0xFF, 0x00, 0xAA, 0xE2, 0x20)
    a(0xFE, *(BAG & 0xFFFF).to_bytes(2, 'little'))
    a.label('end')
    return a.bytes() + LEAVE


def _take(at):
    """물건(인자)을 일행 기록 앞부터 처음 가진 사람에게서 빼고(뒤 칸을 당기며 장비 비트를 맞춤, dq4ch2endor.take_item 과
    같음), 아무도 갖지 않았으면 맡긴 물건에서 하나 뺀다. 결과 flag 는 뺐으면 켠다."""
    from dq4ch2endor import BCC, BCS, BEQ, BRA, lda, sta
    a = _asm()(ENTER, 0xE2, 0x30)
    for r in range(PARTY_MAX):
        items, equip = PARTY_ITEMS + RECORD * r, EQUIP + RECORD * r
        a(lda(0x7E201D), 0xC9, r + 1).br(BCS, f'r{r}').brl('bag').label(f'r{r}')
        a(0xA2, 0x00).label(f'find{r}')(0xBF, _al(items), 0xCF, _al(ARG)).br(BEQ, f'found{r}')
        a(0xE8, 0xE0, ITEM_SLOTS).br(BCC, f'find{r}').brl(f'next{r}')
        a.label(f'found{r}')(0xDA).label(f'shift{r}')(0xE0, ITEM_SLOTS - 1).br(BCS, f'last{r}')
        a(0xBF, _al(items + 1), 0x9F, _al(items), 0xE8).br(BRA, f'shift{r}')
        a.label(f'last{r}')(0xA9, 0xFF, sta(items + ITEM_SLOTS - 1), 0xFA)
        # 장비 비트: 칸 k 아래는 그대로, 위는 한 칸 내림. low = (1 << k) - 1, 새 = (m & low) | ((m >> 1) & ~low)
        a(0xC2, 0x20, 0xA9, 0x00, 0x00, 0xE0, 0x00).br(BEQ, f'low{r}')
        a.label(f'ones{r}')(0x38, 0x2A, 0xCA).br(0xD0, f'ones{r}')
        a.label(f'low{r}')(0x48, lda(equip), 0x23, 0x01, 0x48)
        a(lda(equip), 0x4A, 0x03, 0x03, 0x43, 0x03, 0x03, 0x01, sta(equip), 0x68, 0x68, 0xE2, 0x20).brl('took')
        a.label(f'next{r}')
    a.label('bag')(lda(ARG), 0xAA, 0xBF, _al(BAG)).br(BEQ, 'none')(0x3A, 0x9F, _al(BAG)).brl('took')
    a.label('none')(lda(_flag_addr(RESULT)), 0x29, ~RESULT[1] & 0xFF, sta(_flag_addr(RESULT))).br(BRA, 'end')
    a.label('took')(lda(_flag_addr(RESULT)), 0x09, RESULT[1], sta(_flag_addr(RESULT)))
    a.label('end')
    return a.bytes() + LEAVE


def _flag_addr(flag):
    return 0x7E2190 + flag[0]


def _gold(at, pay):
    """금화를 AMOUNTS[인자]만큼 내거나(pay) 받는다. pay 는 모자라면 그대로 두고 결과 flag 를 끄고, 내면 켠다."""
    from dq4ch2endor import BCC, BRA, lda, sta
    table = at['amounts']
    a = _asm()(ENTER, 0xE2, 0x30, lda(ARG), 0x0A, 0x18, 0x6F, _al(ARG), 0xAA)     # X = 인자 × 3
    if not pay:
        a(0x18, 0xC2, 0x20, lda(GOLD_AT), 0x7F, _al(table), sta(GOLD_AT))
        a(0xE2, 0x20, lda(GOLD_AT + 2), 0x7F, _al(table + 2), sta(GOLD_AT + 2))
        return a.bytes() + LEAVE
    a(0x38, 0xC2, 0x20, lda(GOLD_AT), 0xFF, _al(table), 0x48)
    a(0xE2, 0x20, lda(GOLD_AT + 2), 0xFF, _al(table + 2)).br(BCC, 'short')
    a(sta(GOLD_AT + 2), 0xC2, 0x20, 0x68, sta(GOLD_AT), 0xE2, 0x20)
    a(lda(_flag_addr(RESULT)), 0x09, RESULT[1], sta(_flag_addr(RESULT))).br(BRA, 'end')
    a.label('short')(0xC2, 0x20, 0x68, 0xE2, 0x20)
    a(lda(_flag_addr(RESULT)), 0x29, ~RESULT[1] & 0xFF, sta(_flag_addr(RESULT)))
    a.label('end')
    return a.bytes() + LEAVE


def _next_day(at):
    """날이 바뀜(잠): 용병 날수 둘을 하나씩 늘리고(FF 에서 멈춤, FC 15:$9F79 의 $628C·$628D), 톰 노인 밀기 중·교회 도착을
    지운다(같은 루틴이 $6280 bit5·4 를 지워 다음 날 다시 밀 수 있음). 대화 호출로도, 사건 모듈 네이티브의 JSL 로도 부른다."""
    import dq4ch3lakanaba as lakanaba
    body = bytearray(ENTER)
    for a in (SCOTT_DAYS, LAWRENCE_DAYS):
        body += bytes((0xAF,)) + _al(a) + bytes((0x1A, 0xF0, 0x04, 0x8F)) + _al(a)
    tom = 0x7E2190 + lakanaba.TOM_PUSH[0]
    body += bytes((0xAF,)) + _al(tom) + bytes((0x29, ~(lakanaba.TOM_PUSH[1] | lakanaba.TOM_DONE[1]) & 0xFF, 0x8F)) + _al(tom)
    return bytes(body) + LEAVE


# 대화 호출로 부르는 공용 장치. 모듈의 CALLS 가 {이름: (장치 또는 자기 네이티브 이름, 인자)} 로 고른다
COMMON_ROUTINES = {'give': _give, 'take': _take, 'pay': lambda at: _gold(at, True), 'earn': lambda at: _gold(at, False),
                   'next_day': _next_day}


def _param(routine, param):
    """CALLS 의 인자를 표 칸 바이트로: pay·earn 은 AMOUNTS 의 칸 번호."""
    if routine in ('pay', 'earn'):
        if param not in AMOUNTS:
            raise SystemExit(f'금화 {param}: dq4ch3event.AMOUNTS 에 없음')
        return AMOUNTS.index(param)
    if not 0 <= param <= 0xFF:
        raise SystemExit(f'{routine}: 인자 {param} 가 바이트가 아님')
    return param


def modules():
    """[(키, 모듈)] EVENTS 차례."""
    import importlib
    out = []
    for name in EVENTS:
        key = next((k for k, s in SLOTS.items() if s.module == name), None)
        if key is None:
            raise SystemExit(f'{name}: dq4ch3slots.SLOTS 에 없는 사건 모듈')
        out.append((key, importlib.import_module(name)))
    return out


class Context(ch2.Context):
    """사건 모듈이 받는 것(dq4ch2event.Context 와 같은 이름). msg·talk 는 {이름: 번호}(모르는 자리에서는 None), at 은 그
    모듈 네이티브의 {이름: 주소}, base 는 이 모듈(넘김·공용 장치) 네이티브의 {이름: 주소}, calls 는 그 모듈 CALLS 의
    {이름: 표 칸}. 대화 스크립트 명령을 만드는 도우미를 함께 둔다."""

    def __init__(self, key, module, message=None, talk=None, original=None, points=None):
        self.key, self.module, self.slot, self.original = key, module, SLOTS[key], original
        self.points = points
        self.code_at = self.slot.code[0]
        self.vars_at = VARS_AT + self.slot.vars[0] if self.slot.vars else None
        self.msg = None if message is None else {n: message + k for k, n in enumerate(getattr(module, 'MESSAGES', {}))}
        self.talk = None if talk is None else {n: talk + k for k, n in enumerate(getattr(module, 'TALKS', ()))}
        self.base = native()[1]
        self.calls = {}
        self._at = None

    def say(self, name):
        """대화 명령: 이 모듈 메시지 name 을 띄움."""
        return {"op": "msg", "id": f"{self.msg[name]:03X}"}

    def call(self, name):
        """대화 명령: CALLS 의 name 을 부름. 인자 둘째 바이트 01 은 06:AFA9 의 건너뛰기가 한 바이트로 세는 값이다
        (첫 바이트는 00 이 세 바이트로 삼켜 어떤 값이든 됨). 입구가 표 칸의 인자로 덮는다."""
        return {"op": "call", "target": f"{STUB_AT & 0xFFFF:04X}", "args": [self.calls[name], 0x01]}

    @staticmethod
    def flag_on(flag):
        return {"op": "flag-on", "index": flag[0], "mask": flag[1]}

    @staticmethod
    def flag(flag):
        """대화 조건: flag 가 켜짐."""
        return {"code": "1B", "index": flag[0], "mask": flag[1]}

    @staticmethod
    def has(item):
        """대화 조건: 일행 누군가가 물건을 가짐(조건 11, 맡긴 물건은 보지 않음)."""
        return {"code": "11", "item": item}

    @staticmethod
    def when(cond, then, other=None):
        out = {"op": "if", "cond": cond, "then": then}
        if other is not None:
            out["else"] = other
        return out

    def paid(self):
        """대화 조건: 방금 부른 pay 가 금화를 냈음(take 는 물건을 뺐음)."""
        return self.flag(RESULT)

    @staticmethod
    def retalk(lists, mp, cell, talk, time=None):
        """옮긴 목록 lists[mp] 에서 셀 cell(DQ5 셀, 시간대 time 또는 둘 다)의 인물 대화를 talk 로. 고친 수가 0 이면 멈춤."""
        hit = 0
        for e in lists[mp]["entries"]:
            if (e["fields"]["x"], e["fields"]["y"]) == cell and time in (None, e["time"]):
                e["fields"] = {**e["fields"], "talk": talk}
                hit += 1
        if not hit:
            raise SystemExit(f'{mp} {cell}: 대화를 바꿀 인물이 없음')
        return hit


def _first_talk():
    """3장 첫 대화 번호: 2장 대화(사건 모듈 것까지) 뒤."""
    return ch2._first_talk() + len(ch2.talk_names())


def contexts(first_message=None, first_talk=None, original=None, points=None):
    """[Context] EVENTS 차례. 메시지는 이 모듈 MESSAGES 뒤, 대화는 모듈마다 이어 붙이고, 대화 호출 칸도 이어 매긴다."""
    mods = modules()
    if not mods:
        return []
    message = None if first_message is None else first_message + len(MESSAGES)
    talk = _first_talk() if first_talk is None else first_talk
    out, call = [], 0
    for key, mod in mods:
        _check(key, mod)
        ctx = Context(key, mod, message, talk, original, points)
        ctx.calls = {name: call + k for k, name in enumerate(getattr(mod, 'CALLS', {}))}
        call += len(ctx.calls)
        out.append(ctx)
        message = None if message is None else message + len(getattr(mod, 'MESSAGES', {}))
        talk += len(getattr(mod, 'TALKS', ()))
    return out


def _check(key, mod):
    """모듈이 예약 몫 밖의 flag·전투 무리·DQ5 몬스터를 적으면 빌드를 멈춘다(두 모듈이 같은 자리를 덮지 않게).
    메시지·대화·호출 번호는 자동으로 매겨 겹칠 수 없다."""
    slot = SLOTS[key]
    for idx, mask in getattr(mod, 'FLAGS', ()):
        if idx not in slot.flags:
            raise SystemExit(f'{key}: flag {0x2190 + idx:04X}&{mask:02X} 는 이 모듈 몫({slot.flags})이 아님')
    for b in getattr(mod, 'BATTLES', ()):
        if b['group'] not in slot.groups:
            raise SystemExit(f'{key}: 전투 무리 {b["group"]:02X} 는 이 모듈 몫이 아님')
    for m in getattr(mod, 'MONSTERS', {}):
        if m not in slot.monsters:
            raise SystemExit(f'{key}: DQ5 몬스터 {m:02X} 는 이 모듈 몫이 아님')
    for name, (routine, _) in getattr(mod, 'CALLS', {}).items():
        if routine not in COMMON_ROUTINES and not hasattr(mod, 'native'):
            raise SystemExit(f'{key}.{name}: 네이티브 없이 공용 장치가 아닌 {routine} 를 부름')


def call_table():
    """대화 호출 표 바이트(칸마다 주소 3 + 인자 1, contexts 의 calls 차례)."""
    base = native()[1]
    out = bytearray()
    for ctx in contexts():
        for name, (routine, param) in ctx.module.CALLS.items() if hasattr(ctx.module, 'CALLS') else ():
            if routine in COMMON_ROUTINES:
                target = base[routine]
            elif routine in ctx.at:
                target = ctx.at[routine]
            else:
                raise SystemExit(f'{ctx.key}.{name}: 공용 장치도 모듈 네이티브도 아닌 {routine}')
            out += _al(target) + bytes((_param(routine, param),))
    return bytes(out)


def talk_names():
    """사건 모듈의 대화 이름을 번호 차례로(「키.이름」)."""
    return [f'{key}.{name}' for key, mod in modules() for name in getattr(mod, 'TALKS', ())]


def talk_scripts(first_message):
    """dq5talk/1 의 scripts 에 talk_names 차례로 더할 본문."""
    out = []
    for ctx in contexts(first_message):
        if getattr(ctx.module, 'TALKS', ()):
            bodies = ctx.module.talk_scripts(ctx)
            if len(bodies) != len(ctx.module.TALKS):
                raise SystemExit(f'{ctx.key}: TALKS {len(ctx.module.TALKS)}개에 대화 본문 {len(bodies)}개')
            out += bodies
    return out


def module_lists(lists, first_talk, own_new=(), own_over=()):
    """사건 모듈의 (새 목록, 조건). dq4ch2event.module_lists 와 같은 꼴: 모듈은 lists({맵: 목록})를 고쳐 새 목록·조건을
    더하고, 새 목록 이름은 예약한 앞머리로 시작해야 한다."""
    new, over = [], []
    for ctx in contexts(first_talk=first_talk):
        ctx.made = {lst["name"]: lst for lst in new}
        ctx.made_all = {lst["name"]: lst for lst in (*own_new, *new)}
        ctx.overrides = [*own_over, *over]
        if hasattr(ctx.module, 'npc_lists'):
            more_new, more_over = ctx.module.npc_lists(lists, ctx)
            for lst in more_new:
                if not lst["name"].startswith(ctx.slot.lists):
                    raise SystemExit(f'{ctx.key}: 대체 목록 이름 {lst["name"]} 이 {ctx.slot.lists} 로 시작하지 않음')
            new += more_new
            over += more_over
    return new, over


def event_tokens(first_message):
    """사건 모듈의 이벤트 스크립트 토큰 목록들(dq4msgwait 가 메시지 끝 코드를 고를 때 봄)."""
    return [t for ctx in contexts(first_message) if hasattr(ctx.module, 'events') for t in ctx.module.events(ctx)]


def encounter_groups():
    """dq5encounter/1 의 event_groups 에 더할 사건 전투 무리. 3장은 대화 전투 입구를 쓰지 않는다(FC 3장 사건에 전투가
    없음). 무리는 네이티브에서 dq4ch2battle.far 로 건다."""
    import dq4ch2battle
    out = []
    for key, mod in modules():
        for b in getattr(mod, 'BATTLES', ()):
            if b.get('stub') is not None:
                raise SystemExit(f'{key}: 3장 사건 전투는 대화 입구(stub)를 쓰지 않음')
            out.append(dq4ch2battle.group_doc(b['group'], b['members'], b.get('flags', dq4ch2battle.BOSS_FLAGS)))
    return out


def monster_entries(prg):
    """dq5tables/1 의 monsters 에 더할 몬스터(dq4ch2event.monster_entries 와 같은 꼴)."""
    import dq4monport
    out = []
    for _, mod in modules():
        if hasattr(mod, 'monster_doc'):
            out += mod.monster_doc(prg)
        else:
            out += [{"id": f"{dq5:02X}", **dq4monport.fc_entry(prg, fc)}
                    for dq5, fc in getattr(mod, 'MONSTERS', {}).items()]
    return out


def start_messages(first_message):
    """{(맵, FC 대화, 밤 또는 None): 첫 메시지}: 사건 모듈이 3장 처음 상태에서 바꾼 인물(3장 인물 검사의 기대값)."""
    out = {}
    for ctx in contexts(first_message):
        if hasattr(ctx.module, 'start_messages'):
            out.update(ctx.module.start_messages(ctx))
    return out


def absent():
    """{(맵, DQ5 셀 x, y, 밤)}: 사건 모듈이 3장 처음 상태에서 없앤 인물(dq4npccheck --chapter3 이 말 걸지 않음)."""
    return {k for ctx in contexts() if hasattr(ctx.module, 'absent') for k in ctx.module.absent(ctx)}


def state_messages(first_message):
    """{상태 이름: (SET, {(맵, FC 칸, 밤): 첫 메시지})}: 사건 모듈의 state_messages(ctx)."""
    out = {}
    for ctx in contexts(first_message):
        if hasattr(ctx.module, 'state_messages'):
            for name, v in ctx.module.state_messages(ctx).items():
                if name in out:
                    raise SystemExit(f'{ctx.key}: 상태 이름 {name} 을 두 번 씀')
                out[name] = v
    return out


def _registered():
    """SLOTS 차례로, 파일이 있는 모듈."""
    return tuple(s.module for s in SLOTS.values() if (HERE / f'{s.module}.py').is_file())


# 3장 사건 모듈. 모듈 파일을 만들면 들어온다(등록 줄을 고치지 않음). 차례가 메시지·대화·호출 번호 차례다
EVENTS = _registered()
