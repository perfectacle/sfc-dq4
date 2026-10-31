"""DQ4 2장 「말괄량이 공주의 모험」 첫머리: 1장 끝에서 2장으로 넘어가 산트하임 왕좌의 방(3D/01)에서 시작한다.

1장 끝 서술 뒤 네이티브 transfer 가 일행을 아리나 하나로 바꾸고(주인공 기록 0 을 아리나로 덮음), 이벤트 스크립트로
3D/01 에 옮긴다. 그 맵은 검게 불러오고(dq4chapterbox.CHAPTER2), 왕 자리의 인물 스크립트가 2장 제목 상자 → NDS 서두
서술 → 맵 밝히기 → 왕의 말을 돌린다. 형식은 sfc/dq4/docs/dq4-chapter2-format.md.
"""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4chapter1 as ch1  # noqa: E402
from dq4chapterbox import DB0, ENTER, LEAVE  # noqa: E402

# 깃발(7E:2190 + 첫 값). DQ5 가 켜기만 하고 비트로 보지 않는 자리(sfc/dq5/docs/dq5-flags.md)
CHAPTER2 = (0x78, 0x10)        # 7E:2208 bit4  2장 진행 중(1장 끝에서 켬). 주인공 그림을 아리나 대역으로
OPENING = (0x78, 0x40)         # 7E:2208 bit6  2장 첫머리(제목 상자·서두·왕의 말)를 기다림. 옮길 때 켜고 첫머리 끝에 끔

THRONE = '3D/01'               # FC 01/01 산트하임 왕좌의 방
START_CELL = (0x09 * 2, 0x08 * 2 + 1)   # FC (09,08): 왕 앞
KING_CELL = (0x09 * 2, 0x07 * 2 + 1)    # FC (09,07), 옮긴 인물 자리(dq4npcport 의 2y+1)

# 왕 자리 인물이 빌리는 스크립트: 이 해킹에서 가지 않는 DQ5 21/09 의, 낮에만 놓이는 스크립트 인물(112바이트)
KING_SRC, KING_SCRIPT = {"list": "05:C6C3", "index": 0}, "05:C6CA"

CODE_AT = 0x5EF000             # 1장 사건 코드(5E:D000~) 뒤
ALENA_PICTURE = 0x30           # 2장 동안 주인공 그림: DQ5 ビアンカ(인물 04) 그림을 대역으로
HERO_PICTURE_AT = 0x05D9A1     # 05:D98F 의 주인공 갈래(그림 2E·2D·3A 를 고름). JSL + RTS 로 덮는다
HERO_PICTURE_ORIG = bytes.fromhex('000b4000d003a92e60000b202ed003a93a60a92d60')

PARTY_AT = 0x7E2040            # 일행 기록 0(42바이트)
NAME_AT = 0x7E2001             # 주인공 이름 8바이트(음절마다 2바이트, 01 로 끝남)
GOLD_AT = 0x7E2019
# 1장 주인공(라이안) 기록과 이름 입력값을 맡겨 두는 곳: 사람 동료 칸(7E:294A, 32바이트 × 5)의 칸 2~4. 이 해킹은 칸을
# 쓰는 장면(ルイーダ·결혼식·석상)이 없다. 칸 첫 바이트 bit7 이 찬 칸 표시라 칸마다 +1 부터 둔다(기록은 31 + 11 바이트로 나눔)
SLOT_SIZE = 0x20
RYAN_RECORD_AT = (0x7E298B, 0x7E29AB)
RYAN_NAME_AT = 0x7E29CB
TIME_AT = 0x7E075E             # 필드 시간(0050 이 아침, F0 이상이 밤)
MORNING = 0x0050

ALENA_NAME = '아리나'
# FC 1장 시작 기록 7(ひめ): HP 16, MP 0, ちから 12, すばやさ 7, たいりょく 8, かしこさ 4, うんのよさ 1, Eきぬのローブ.
# DQ5 기록 +6 이 すばやさ, +7~+A 가 ちから·みのまもり·かしこさ·うんのよさ. たいりょく 는 1장처럼 みのまもり 자리에 둔다
ALENA_STATS = {'hp': 16, 'mp': 0, 'agility': 7, 'stats': (12, 8, 4, 1)}
SILK_ROBE = 0x62               # DQ5 きぬのローブ
GOLD = 100


def alena_record(hero):
    """원래 롬의 주인공 기록 틀(23:C014 칸 0, 42바이트)을 아리나 1레벨로 고친 것."""
    r = bytearray(hero)
    s = ALENA_STATS
    r[2:4] = r[0xE:0x10] = s['hp'].to_bytes(2, 'little')
    r[4:6] = r[0x10:0x12] = s['mp'].to_bytes(2, 'little')
    r[6] = s['agility']
    r[7:0xB] = bytes(s['stats'])
    r[0xB:0xE] = bytes(3)
    r[0x12] = 1
    r[0x14:0x16] = bytes((0x01, 0x00))                 # 물건 칸 0 을 장비
    r[0x16:0x22] = bytes((SILK_ROBE,)) + b'\xff' * 11
    r[0x23:0x26] = bytes(3)                            # 배운 주문 없음
    return bytes(r)


def name_bytes(name):
    import dq4nameentry as ne
    return b''.join(ne.code_bytes(ne.GLYPHS.index(ch)) for ch in name).ljust(8, b'\x01')


def _al(a):
    return bytes((a & 0xFF, a >> 8 & 0xFF, a >> 16))


def _mvn(src, dst, n):
    """n 바이트 복사. M·X 16 에서."""
    return bytes((0xA2, *(src & 0xFFFF).to_bytes(2, 'little'), 0xA0, *(dst & 0xFFFF).to_bytes(2, 'little'),
                  0xA9, *(n - 1).to_bytes(2, 'little'), 0x54, dst >> 16, src >> 16))


def _flag_or(flag):
    a = 0x7E2190 + flag[0]
    return bytes((0xAF,)) + _al(a) + bytes((0x09, flag[1], 0x8F)) + _al(a)


def _transfer(record_at, name_at, event_at):
    """1장 끝에서 부른다: 라이안 기록·이름을 맡기고, 일행을 아리나 하나로, 금화 100, 아침으로 두고, 2장 깃발을 켠 뒤
    3D/01 로 옮기는 이벤트를 건다."""
    import dq4prologue
    body = bytearray(bytes((0xC2, 0x30)))
    head = SLOT_SIZE - 1
    body += (_mvn(PARTY_AT, RYAN_RECORD_AT[0], head) + _mvn(PARTY_AT + head, RYAN_RECORD_AT[1], 42 - head) +
             _mvn(NAME_AT, RYAN_NAME_AT, 8))
    body += _mvn(record_at, PARTY_AT, 42) + _mvn(name_at, NAME_AT, 8)
    body += bytes((0xA9, *MORNING.to_bytes(2, 'little'), 0x8F)) + _al(TIME_AT)
    body += bytes((0xA9, *(GOLD & 0xFFFF).to_bytes(2, 'little'), 0x8F)) + _al(GOLD_AT)
    body += bytes((0xE2, 0x20, 0xA9, GOLD >> 16, 0x8F)) + _al(GOLD_AT + 2)
    # 일행 수·걷는 수와 사본 1, 순서 0, 마차 없음
    for a in (0x7E201D, 0x7E201E, 0x7E201F):
        body += bytes((0xA9, 0x01, 0x8F)) + _al(a)
    for a in (0x7E2020, 0x7E2028):
        body += bytes((0xA9, 0x00, 0x8F)) + _al(a)
    body += bytes((0xAF,)) + _al(0x7E201C) + bytes((0x29, 0x7F, 0x8F)) + _al(0x7E201C)
    body += _flag_or(CHAPTER2) + _flag_or(OPENING)
    body += DB0                                         # MVN 이 DB 를 7E 로 두었다. 이벤트 걸기는 DB 0 의 절대 주소
    start = dq4prologue._event_start(event_at)[len(ENTER):-len(LEAVE)]
    return ENTER + bytes(body) + start + LEAVE


def _skip_song():
    """맵을 불러올 때 곡을 바꾸지 않게(dq4chapterbox.SKIP_SONG): 제목 상자·서술 동안 곡이 없다. 맵 밝히기가 끈다."""
    import dq4chapterbox as box
    addr, bit = box.SKIP_SONG
    return ENTER + bytes((0xAF,)) + _al(addr) + bytes((0x09, bit, 0x8F)) + _al(addr) + LEAVE


def _hero_picture():
    """05:D9A1 대신: 2장 동안이면 아리나 대역 그림, 아니면 원래처럼 2190 bit6 꺼짐 2E, 21BE bit5 켜짐 2D, 아니면 3A.
    M 8 에서 부르고 A 에 그림 번호를 둔 채 돌아간다(부른 곳의 RTS 가 05:D98F 를 끝냄)."""
    flag = 0x7E2190 + CHAPTER2[0]
    return bytes((0xAF,)) + _al(flag) + bytes((0x29, CHAPTER2[1], 0xF0, 0x03, 0xA9, ALENA_PICTURE, 0x6B,
                                              0xAF)) + _al(0x7E2190) + bytes((0x29, 0x40, 0xD0, 0x03,
                                              0xA9, 0x2E, 0x6B, 0xAF)) + _al(0x7E21BE) + bytes((
                                              0x29, 0x20, 0xF0, 0x03, 0xA9, 0x2D, 0x6B, 0xA9, 0x3A, 0x6B))


def native(hero=None):
    """(바이트, {이름: 주소}). hero: 원래 롬의 주인공 기록 틀(없으면 0 으로 채워 주소만 셈)."""
    out = bytearray(alena_record(hero) if hero is not None else bytes(42))
    at = {'record': CODE_AT, 'name': CODE_AT + len(out)}
    out += name_bytes(ALENA_NAME)
    g, n = (int(v, 16) for v in THRONE.split('/'))
    at['skip_song'] = CODE_AT + len(out)
    out += _skip_song()
    at['event'] = CODE_AT + len(out)
    out += bytes((0xA0, *_al(at['skip_song']), 0x90, g, n, *START_CELL, 0x01, 0x80, 0xFF))
    at['transfer'] = CODE_AT + len(out)
    out += _transfer(at['record'], at['name'], at['event'])
    at['hero_picture'] = CODE_AT + len(out)
    out += _hero_picture()
    return bytes(out), at


# 메시지 차례가 곧 번호 차례다(1장 사건 메시지 뒤 k 번째). NDS 2장 대사(MESS b0002)를 옮긴다
MESSAGES = {
    # NDS 2002·2003(FC 0305 첫 두 쪽). 서술은 해라체
    'opening': ch1.narrate('옛날 옛적 어느 곳에/아리나 공주라는/아주아주 말괄량이/공주님이 있었다고 한다.',
                           '그 나라 임금님은/공주의 말괄량이 짓에/머리를 싸매는/나날이었다.',
                           '어느 날 아침/임금님은 공주를/불러들였다……'),
    # NDS 2004(FC 0305 끝 쪽)
    'call': ch1.say('공주님! 아리나 공주님!/부왕께서 부르십니다!'),
    # NDS 2008~2011(FC 0306)
    'king': ch1.speak('왕', '오오, 아리나냐!?/할아범에게 들었다만/힘을 시험하는 여행을/떠나고 싶다고?',
                      '안 된다. 안 되고말고./너는 여자다./게다가 이 나라의/공주가 아니더냐.',
                      '마물들이 사는/바깥 세상으로/힘을 시험하러 나가다니/이 아비가 허락 못 한다!',
                      '알겠느냐!?/이 성에서 나가서는/안 된다./그럼 물러가도 좋다……'),
}


def message_ids(first):
    return {name: first + k for k, name in enumerate(MESSAGES)}


def texts(first):
    return {first + k: parts for k, parts in enumerate(MESSAGES.values())}


def _cmd(op, *args):
    return {"op": op, "args": list(args)}


def scripts(first_message, native_points):
    """인물 스크립트. native_points: dq4chapterbox.entry_points 의 {이름: 주소}(box2·reveal)."""
    m = message_ids(first_message)
    lo, hi = lambda v: v & 0xFF, lambda v: v >> 8
    msg = lambda k: _cmd('21', lo(m[k]), hi(m[k]))  # noqa: E731
    return [{"address": KING_SCRIPT, "commands": [
        _cmd('3F'), _cmd('37', *_al(native_points['box2'])), msg('opening'),
        _cmd('37', *_al(native_points['reveal'])), msg('call'), msg('king'),
        _cmd('11', OPENING[0], ~OPENING[1] & 0xFF), _cmd('40'), _cmd('16')]}]


def npc_lists(ported):
    """(new_lists, overrides). 첫머리를 기다리는 동안의 3D/01 은 옮긴 목록에서 왕만 연출 인물로 바꾼다."""
    entries = next(lst["entries"] for lst in ported if lst.get("map") == THRONE)
    opening = []
    for e in entries:
        f = e["fields"]
        if (f["x"], f["y"]) == KING_CELL:
            e = {**e, "from": KING_SRC, "fields": {**f, "interval": max(1, f.get("interval", 1))}}
        opening.append(e)
    over = [{"map": THRONE, "flag": OPENING[0], "when": "on", "mask": OPENING[1], "list": "new:ch2_opening"}]
    return [{"name": "ch2_opening", "entries": opening}], over


def apply(data, original):
    """original: 원래 롬(주인공 기록 틀 23:C014 를 읽음)."""
    d = bytearray(data)
    o = ch1.lorom(0x23C014)
    code, at = native(original[o:o + 42])
    o = ch1.lorom(CODE_AT)
    if any(d[o:o + len(code)]):
        raise SystemExit(f'{CODE_AT:06X}: 비어 있지 않은 자리')
    d[o:o + len(code)] = code
    o = ch1.lorom(HERO_PICTURE_AT)
    if bytes(d[o:o + len(HERO_PICTURE_ORIG)]) != HERO_PICTURE_ORIG:
        raise SystemExit(f'{HERO_PICTURE_AT:06X}: 원래 바이트가 아님 {d[o:o + len(HERO_PICTURE_ORIG)].hex()}')
    d[o:o + 5] = bytes((0x22, *_al(at['hero_picture']), 0x60))
    return bytes(d)
