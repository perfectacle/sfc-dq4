"""DQ4 3장 「무기상인 톨네코」 넘김과 첫머리: 2장 끝에서 3장으로 넘어가 레이크나바 톨네코 집(3E/01)에서 시작한다.

2장 끝 서술 뒤(dq4ch2ending 의 끝내는 인물, --chapter3 빌드) 네이티브 transfer 가 아리나 일행 기록을 맡기고 일행을
톨네코 하나로 바꾼 뒤(주인공 기록 0 을 톨네코로 덮음) 이벤트 스크립트로 3E/01 에 옮긴다. 그 맵은 검게 불러오고
(dq4chapterbox.CHAPTER3), 네네 자리의 인물 스크립트가 3장 제목 상자 → FC 서두 서술 → 맵 밝히기 → 네네의 부름 →
방향 키를 기다림 → 네네가 깨우는 말을 돌린다. 3장 코드는 빌드 옵션과 상관없이 늘 들어가고, --chapter3 는 2장 끝
인물이 이 transfer 를 부를지(아니면 「다음에 계속」 끝 상자)만 고른다. 형식은 sfc/dq4/docs/dq4-chapter3-format.md.
"""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4chapter1 as ch1  # noqa: E402
import dq4ch2event as ch2  # noqa: E402
from dq4chapterbox import DB0, ENTER, LEAVE  # noqa: E402

# 7E:2208 은 DQ5 가 색인 쓰기로만 덮는 자리(dq4ch2slots 「flag 자리」). 2장 첫머리·텐페·사건 전투가 bit0·1·2·4·6·7 을 쓴다
CHAPTER3 = (0x78, 0x08)        # 7E:2208 bit3  3장 진행 중(2장 끝에서 켬). 주인공 그림·성장·장비를 톨네코로
OPENING = (0x78, 0x20)         # 7E:2208 bit5  3장 첫머리(제목 상자·서두·네네)를 기다림. 옮길 때 켜고 첫머리 끝에 끔

HOUSE = '3E/01'                # FC 16/01 레이크나바 톨네코의 집
START_CELL = (0x1B * 2, 0x05 * 2 + 1)    # FC 3장 시작 (1B,05)
NENE_CELL = (0x1B * 2, 0x04 * 2 + 1)     # 옮긴 네네(FC 슬롯 0A, 낮): 시작 칸 바로 위
CASTLE = ch2.CASTLE
# 스크립트를 빌리는 인물: 이 해킹에서 가지 않는 DQ5 2B/00 의, 낮에만 놓이는 한 벌짜리 스크립트 인물(스크립트 80바이트).
# dq4ch2slots 의 어느 세션 목록도 아니다
OPENER_SRC, OPENER_SCRIPT = {"list": "05:CC73", "index": 0}, "05:CC7A"

CODE_AT, CODE_END = 0x5CC000, 0x5CD000   # dq4ch2slots.CHAPTER3_CODE
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
    값은 FC 장 시작 루틴과 같은 dq4growth.first_record, 소지품은 FC 표. DQ5 에 같은 이름이 없는 물건은 dropped."""
    import dq4growth
    import dq4shopport
    from dq5map import Rom
    first = dq4growth.first_record(dq4, FC_TORNEKO)
    known = dq4shopport.dq5_items(Rom(Path(dq5).read_bytes() if not isinstance(dq5, (bytes, bytearray)) else dq5))
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
    return {first + k: parts for k, parts in enumerate(MESSAGES.values())}


def _cmd(op, *args):
    return {"op": op, "args": list(args)}


def scripts(first_message, native_points):
    """인물 스크립트. native_points: dq4chapterbox.entry_points 의 {이름: 주소}(box3·reveal)."""
    m = message_ids(first_message)
    _, at = native()
    msg = lambda k: _cmd('21', m[k] & 0xFF, m[k] >> 8)  # noqa: E731
    return [{"address": OPENER_SCRIPT, "commands": [
        _cmd('3F'), _cmd('37', *_al(native_points['box3'])), msg('opening'),
        _cmd('37', *_al(native_points['reveal'])), msg('nene_call'),
        _cmd('05', *_al(at['pad'])), msg('nene_wake'),
        _cmd('11', OPENING[0], ~OPENING[1] & 0xFF), _cmd('40'), _cmd('16')]}]


def npc_lists(ported):
    """(새 목록, 조건). 첫머리를 기다리는 동안의 3E/01 은 옮긴 목록에서 낮의 네네만 연출 인물로 바꾼다. 3장 동안의
    산트하임 성 앞마당은 2장 끝의 빈 성 목록이다(2장을 끝내는 인물이 다시 서지 않게)."""
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
    return [{"name": "ch3_opening", "entries": opening}], over


def apply(data, original, dq4):
    """original: 원래 DQ5 롬(기록 틀), dq4: FC 롬 경로(톨네코 시작 값·소지품)."""
    d = bytearray(data)
    code, _ = native(original, dq4)
    o = ch1.lorom(CODE_AT)
    if CODE_AT + len(code) > CODE_END:
        raise SystemExit(f'3장 네이티브 {len(code)}바이트가 {CODE_AT:06X}~{CODE_END - 1:06X} 를 넘음')
    if any(d[o:o + len(code)]):
        raise SystemExit(f'{CODE_AT:06X}: 비어 있지 않은 자리')
    d[o:o + len(code)] = code
    return bytes(d)
