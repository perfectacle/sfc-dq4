"""DQ4 2장 왕의 병: 사막의 바자 병사 → 왕의 목소리 → 서쪽 탑의 엘프와 지저귐의 꿀 → 왕 회복 → 여행의 문 사당.

FC 차례(fc/dq4/docs/dq4-story-format.md, 대화는 dq4talk.py 로 읽음):
  1. 바자(45/05, FC 0C/00)에서 일행이 X 09 줄(Y 0A~0E)을 지나면 병사(슬롯 06, 대화 035)가 「공주님, 찾았습니다!」
     (034E, 1D 이벤트 3F). FC $6283 bit3 = BAZAAR.
  2. 왕좌의 방(3D/01)의 계단 위 칸(0A~0C,10)에 서면 병사(슬롯 07, 대화 025)가 「임금님의 목소리가」(034F,
     1D 이벤트 42). bit2 = HEARD. 대신·근위병·곤 영감·시인 마로니·바자 도구점의 말이 bit3·bit2 로 바뀌어 꿀을 가리킨다.
  3. 서쪽 탑 꼭대기(45/06, FC 2E/00)에서 줄 0C 에 들어서면 엘프 둘이 달아나며 약을 떨어뜨리고(037D, 1D 이벤트 43,
     $6286 bit1 = SEEN), 그 자리를 조사하면 지저귐의 꿀(0298, 특수 칸 E8).
  4. 왕 앞(09,08)에서 꿀을 쓰면 「임금님께 먹였다」(02E7)·「목소리가 나온다!」(035F). bit1 = CURED(bit3 은 끔).
  5. 여행의 문 사당(45/0E, FC 1E/00)의 병사(대화 037)가 bit1 이 꺼져 있으면 길을 막고(1D 이벤트 10), 켜지면 비켜
     엔돌 쪽 사당(45/0F, FC 1F/00)으로 가는 여행의 문에 닿는다.

DQ5 의 しらべる·どうぐ 는 인물 대화를 부르지 않아 다음처럼 옮긴다: 탑의 꿀은 엘프가 섰던 칸을 밟으면 찾고(보이지
않는 인물), 왕에게 꿀을 먹이는 것은 꿀을 가진 채 왕에게 말을 걸면 한다(대화 조건 11). 꿀은 FC 처럼 없애지 않고
남는다. 형식은 sfc/dq4/docs/dq4-chapter2-format.md 「왕 병과 지저귐의 꿀」·「여행의 문 사당」.
"""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4chapter1 as ch1  # noqa: E402
from dq4chapterbox import ENTER, LEAVE  # noqa: E402
import dq4ch2event as ch2  # noqa: E402

say, narrate, speak = ch1.say, ch1.narrate, ch1.speak

# 7E:21F2 (dq4ch2slots E3). 21F3 은 아직 쓰지 않는다
IDX = 0x62
BAZAAR = (IDX, 0x01)           # 바자 병사가 성으로 돌아오라고 함(FC $6283&08)
HEARD = (IDX, 0x02)            # 왕좌의 방 병사가 왕의 목소리를 알림(FC $6283&04)
SEEN = (IDX, 0x04)             # 탑 꼭대기의 엘프가 달아남(FC $6286&02)
GOT = (IDX, 0x08)              # 엘프가 떨어뜨린 지저귐의 꿀을 찾음
CURED = (IDX, 0x10)            # 왕이 나음(FC $6283&02·$627B&02). 사당 병사가 비키고, 다음 사건이 볼 flag
FLAGS = (BAZAAR, HEARD, SEEN, GOT, CURED)

HONEY = 0xBE                   # 지저귐의 꿀(형식 문서 「사건 물건과 도적의 열쇠 문」)
BAZAAR_MAP, TOWER_TOP, SARAN = '45/05', '45/06', '45/00'
SHRINE, SHRINE_FAR = '45/0E', '45/0F'     # FC 1E/00(이쪽)·1F/00(엔돌 쪽)


def cell(x, y):
    """FC 칸 → 옮긴 인물 셀(dq4npcport.cell)."""
    return (2 * x, 2 * y + 1)


def hero_rect(x0, y0, x1, y1):
    """FC 칸 사각형 → 주인공 셀 사각형. 주인공은 FC 칸 (x, y) 에서 (2x 또는 2x+1, 2y+1 또는 2y+2) 에 선다."""
    return (2 * x0, 2 * y0 + 1, 2 * x1 + 1, 2 * y1 + 2)


# 바자(FC 0C/00). 병사(0B,0C)·도구점 주인(낮 (06,04), 밤 (06,03))
BAZAAR_SOLDIER = cell(0x0B, 0x0C)
SHOP_NIGHT = cell(0x06, 0x03)
BAZAAR_RECT = hero_rect(0x09, 0x0A, 0x09, 0x0E)            # FC 1D:$A765 가 보는 X 09·Y 0A~0E
FC_BAZAAR_SOLDIER, FC_SHOP = 0x035, 0x036
# 왕좌의 방(FC 01/01). 계단 (0B,11) 위 줄에 서면 병사가 알린다(1D:$A84F 의 (0B,10)·(0C,10)·(0A,11) 가운데 위 줄)
THRONE_SOLDIER = cell(0x0A, 0x10)
THRONE_RECT = hero_rect(0x0A, 0x10, 0x0C, 0x10)
MINISTER, GUARD = cell(0x0C, 0x0A), cell(0x16, 0x09)
FC_THRONE_SOLDIER, FC_MINISTER, FC_GUARD = 0x025, 0x01E, 0x01B
# 산트하임 성 뒤뜰 방의 곤 영감(FC 01/00 대화 026, 낮 (06,03)·밤 (03,03))과 사란의 시인 마로니(13/00 대화 027)
GON = {'day': cell(0x06, 0x03), 'night': cell(0x03, 0x03)}
MARONI = cell(0x0E, 0x0A)
FC_GON, FC_MARONI = 0x026, 0x027
# 탑 꼭대기(FC 2E/00). 엘프 둘(08,08)·(09,09). 계단 (06,0E)에서 줄 0C 에 들어서면 달아난다(1D 이벤트 43)
ELVES = (cell(0x08, 0x08), cell(0x09, 0x09))
ELF_PICTURE = 0x37             # dq4people.EVENT_PEOPLE 엘프
ELF_RECT = (0, 0, 0x7F, 0x0C * 2 + 2)
ELF_AWAY = (cell(0x08, 0x04), cell(0x09, 0x04))
HONEY_RECT = hero_rect(0x08, 0x08, 0x09, 0x09)              # FC 특수 칸 E8 (08,08) 등 넷
FC_ELF = 0x14C
# 사당(FC 1E/00). 병사(03,08) 는 FC 1D 이벤트 10 이 (04,06) 으로 걸어가 위 방으로 가는 틈을 막는다. 처음부터 그 칸에
# 세우고, 왕이 나으면 원래 칸에 둔다
SHRINE_SOLDIER = cell(0x03, 0x08)
SHRINE_BLOCK = cell(0x04, 0x06)
FC_SHRINE_SOLDIER = 0x037
SHRINE_DOOR, FAR_DOOR = (0x05, 0x03), (0x03, 0x03)         # 여행의 문(FC 출구 종류 0A) 칸

# 빌린 인물 스크립트(DQ5 02/06 대체 목록 10:98AE, dq4ch2slots E3 칸 0~16). 칸마다 스크립트 길이 바이트 주소
SCRIPT_LIST = '10:98AE'
SCRIPTS = ('10:98B5', '10:98F4', '10:9923', '10:9931', '10:993F', '10:994D', '10:995F', '10:9971', '10:9983',
           '10:9995', '10:99A7', '10:99B9', '10:99CB', '10:99DD', '10:99EB', '10:99F9', '10:9A07')
USE = {'bazaar_soldier': 0, 'throne_soldier': 1, 'elf_a': 2, 'elf_b': 3, 'honey': 4}

SHRINE_OPEN = 'ch2_king_shrine'


def _al(a):
    return bytes((a & 0xFF, a >> 8 & 0xFF, a >> 16))


def _asm(parts):
    """바이트와 ('label', 이름)·(분기 옵코드, 이름) 을 이어 붙이고 8비트 상대 분기를 푼다."""
    out, labels, fixes = bytearray(), {}, []
    for p in parts:
        if isinstance(p, tuple) and p[0] == 'label':
            labels[p[1]] = len(out)
        elif isinstance(p, tuple):
            out.append(p[0])
            fixes.append((len(out), p[1]))
            out.append(0)
        else:
            out += p
    for at, name in fixes:
        d = labels[name] - (at + 1)
        if not -128 <= d <= 127:
            raise ValueError(f'분기 {name} 이 멂')
        out[at] = d & 0xFF
    return bytes(out)


BAG = 0x2250                   # 맡긴 물건(물건 번호마다 개수)
PARTY_ITEMS = 0x2040 + 0x16    # 일행 기록 0 의 가진 물건 12칸. 기록은 42바이트씩
RECORD, SLOTS_PER = 42, 12
EMPTY = 0xFF


def _give(item):
    """인물 스크립트(37)에서: 일행(7E:201D 명) 가운데 가진 물건 칸이 빈(FF) 첫 사람에게 item 을, 모두 차 있으면
    맡긴 물건에 하나 더한다. M 8·X 16·DB 7E."""
    db7e = bytes((0xA9, 0x7E, 0x48, 0xAB))
    return ENTER + db7e + _asm([
        bytes((0xAD, 0x1D, 0x20)), (0xF0, 'bag'), bytes((0x48,)),            # LDA $201D / BEQ / PHA
        bytes((0xA2, *PARTY_ITEMS.to_bytes(2, 'little'))),                   # LDX #첫 칸
        ('label', 'rec'), bytes((0xA0, SLOTS_PER, 0x00)),                    # LDY #12
        ('label', 'slot'), bytes((0xBD, 0x00, 0x00, 0xC9, EMPTY)), (0xF0, 'hit'),
        bytes((0xE8, 0x88)), (0xD0, 'slot'),
        bytes((0xC2, 0x20, 0x8A, 0x18, 0x69, RECORD - SLOTS_PER, 0x00, 0xAA, 0xE2, 0x20)),   # X += 30
        bytes((0xA3, 0x01, 0x3A, 0x83, 0x01)), (0xD0, 'rec'),                # 남은 수 하나 줄임
        bytes((0x68,)), (0x80, 'bag'),
        ('label', 'hit'), bytes((0x68, 0xA9, item, 0x9D, 0x00, 0x00)), (0x80, 'end'),
        ('label', 'bag'), bytes((0xEE, *(BAG + item).to_bytes(2, 'little'))),
        ('label', 'end'),
    ]) + LEAVE


def _outside(rect):
    """인물 명령 05: 주인공이 사각형 밖이면 A = 0(dq4prologue._inside 의 두 끝을 바꿈)."""
    import dq4prologue
    code = dq4prologue._inside(*rect)
    return code[:-14] + code[-7:] + code[-14:-7]


def native(ctx):
    import dq4prologue
    out = bytearray()
    at = {}

    def put(name, b):
        at[name] = ctx.code_at + len(out)
        out.extend(b)
    put('bazaar_rect', dq4prologue._inside(*BAZAAR_RECT))
    put('throne_rect', dq4prologue._inside(*THRONE_RECT))
    put('elf_rect', dq4prologue._inside(*ELF_RECT))
    put('honey_rect', dq4prologue._inside(*HONEY_RECT))
    put('give_honey', _give(HONEY))
    return bytes(out), at


# FC 메시지 번호(NDS 대사 번호). NDS 일본어 원문을 옮기고, NDS 에 없는 줄은 FC 를 옮겼다
MESSAGES = {
    # 바자 병사(FC 034E·07DD, NDS 11521·11524·11527)
    'bazaar': say('앗! 공주님,/찾았습니다!', '어서 성으로/돌아가 주십시오!/임금님께서, 임금님께서/큰일입니다!'),
    'bazaar_after': say('앗! 공주님!/임금님께서는/어떠셨습니까?/걱정이 되어 걱정이 되어……'),
    # 바자 도구점 주인의 밤(FC 07DF·07DE, NDS 11560~11562·11558)
    'shop_hint': say('지저귐의 꿀?/아아, 이 가게에도/옛날에 딱 하나/있었지.', '엘프가 온다는/서쪽 탑에 가면/지금도 손에 넣을지/몰라.',
                     '하지만 옛날과 달리/그 탑에는 마물이/살기 시작했으니/그만두는 게 좋을걸.'),
    'shop_closed': say('미안하네./오늘은 이제/끝이야.'),
    # 왕좌의 방 병사(FC 034F·07A8, NDS 10563)
    'throne_soldier': say('큰일입니다!/실은 임금님의/목소리가 나오지 않게/되어 버렸습니다!'),
    'throne_start': say('여기는 산트하임/성입니다.'),
    # 대신(FC 07E3·07E9·07A5, NDS 10559~10561)
    'minister_ill': say('오오, 이 무슨 일이란/말인가! 목소리가/나오지 않으시다니!',
                        '이 일은 성의 다른/사람들에게는 알리지/않았지만 이대로는……',
                        '오오, 그렇지 그렇지!/뒤뜰 방에 사는/곤 영감이라면 무언가/알지도 모릅니다!'),
    'minister_cured': say('어쨌든 다행입니다!/하지만 임금님께서/꾸신 꿈이 마음에/걸립니다……'),
    'minister_start': say('임금님께서는 공주님을/생각하셔서 그렇게/말씀하시는 겁니다.', '부디 말씀을/따라 주십시오.'),
    # 근위병(FC 07E4·07A9, NDS 10565)
    'guard_ill': say('이 나라는 임금님이/계시기에 지탱되고/있습니다.', '모두를 불안하게/하지 않도록 부디/비밀로……'),
    'guard_start': say('이 위는 임금님과/공주님의 침실/입니다.'),
    # 곤 영감(FC 07E6·07B4, NDS 10546~10551)
    'gon_ill': say('뭐라고요, 임금님의/목소리가 나오지/않게 되셨다고요!?', '그러고 보니 시인/마로니도 옛날에/목을 다쳤다던가……',
                   '하지만 지금은 이 나라/제일의 아름다운/목소리. 무언가 알고/있을지도 모릅니다.'),
    'gon_start': say('임금님께서는 한밤중에/가끔 가위에/눌리시는 모양이야.', '나쁜 꿈이라도/꾸시는 걸까……'),
    # 시인 마로니(FC 07E7·07B7·07B8, NDS 11015~11018)
    'maroni_ill': speak('마로니', '그렇습니다. 마로니는/저입니다.', '네? 어째서 이렇게/아름다운 목소리를/가졌느냐고요?',
                        '그건 지저귐의 꿀이라는/엘프의 약을 먹은/덕분이겠지요.',
                        '옛날 여행을 할 때/우연히 사막의 바자/도구점에서/찾아냈답니다. 랄랄랄라.'),
    'maroni_day': say('저는 시인/마로니입니다.', '파아란 하늘과/흘러가는 구름들/랄랄라.'),
    'maroni_night': say('빛나는 초승달/반짝이는 별들/랄랄라.'),
    # 탑 꼭대기의 엘프(FC 037D, NDS 12012~12018)와 꿀(FC 0298)
    'elves': (speak('엘프', '꺅! 너희들/인간이구나!', '리스! 돌아가자!')[:-1] + [ch1.PAGE] +
              speak('리스', '네, 언니!', '앗, 큰일 났다!/약을 떨어뜨렸어!')[:-1] + [ch1.PAGE] +
              speak('엘프', '괜찮아, 그런 건!/자, 빨리!')),
    'found': narrate('아리나는/지저귐의 꿀을/찾아냈다!'),
    # 왕(FC 07E2·02E7·035F·07E8·07A3, NDS 12504~12515·14003~14005)
    'king_silent': (say('…………………………')[:-1] + [ch1.PAGE] +
                    narrate('임금님은 무언가/말하고 싶은 듯이/이쪽을 보고 있다.')),
    'honey_use': narrate('아리나는 지저귐의/꿀을 임금님께/먹여 드렸다.'),
    'king_cure': speak('왕', '…………', '응? 아아, 아아.', '오오!? 모, 목소리가/나온다! 나았다,/나았어!',
                       '그렇군, 너희가……/어쨌든 고맙구나.', '실은 나는 엄청나게/무서운 꿈을/꾸었느니라.',
                       '거대한 괴물이/지옥에서 되살아나/모든 것을 파괴하고/있었지.', '처음에는 내 가슴속에만/묻어 둘 생각이었으나……',
                       '너무도 같은 꿈을/몇 번이나 꾸니/어쩐지 불안해져서.', '대신에게 꿈 이야기를/하려던 바로 그때/목소리가 나오지/않게 된 게다.',
                       '……어쩌면 무언가가/일어나려 하는 것인지도/모르겠구나……',
                       '아리나야./나는 이제 말리지/않겠다. 네 눈으로/세상을 보고 오너라.', '브라이, 크리프트./아리나를 부탁하노라!'),
    'king_after': speak('왕', '부디 조심해서/여행을 계속하거라.', '나는 꿈에 대해/생각해 보기로 하마.',
                        '무서운 꿈을 꾸었을 때/다른 꿈도 꾼 것/같은데 도무지/생각이 나지 않는구나……'),
    'king_back': speak('왕', '오오, 돌아와 주었구나/아리나!', '아니, 말하지 않아도/된다. 너는 말려도/또 곧 나갈 생각이겠지.',
                       '하지만 내 눈이/닿지 않는 다른/대륙에는 가지/말거라.'),
    'king_ask': ch2.MESSAGES['king_ask'],
    'king_yes': ch2.MESSAGES['king_yes'],
    'king_no': ch2.MESSAGES['king_no'],
    # 사당 병사(FC 07E1)
    'shrine_pass': say('임금님의 사자에게서/이야기는 들었습니다./지나가십시오.'),
}

TALKS = ('bazaar_soldier', 'shop_night', 'throne_soldier', 'king', 'minister', 'guard', 'gon', 'maroni', 'shrine_pass')


def _flag(f):
    return {"code": "1B", "index": f[0], "mask": f[1]}


def _flag_on(f):
    return {"op": "flag-on", "index": f[0], "mask": f[1]}


def _if(cond, then, other):
    return {"op": "if", "cond": cond, "then": then, "else": other}


DAY = {"code": "14"}
YES = {"code": "05"}


def talk_scripts(ctx):
    msg = lambda k: {"op": "msg", "id": f"{ctx.msg[k]:03X}"}  # noqa: E731
    ask = [msg('king_ask'), _if(YES, msg('king_yes'), msg('king_no'))]
    bodies = {
        'bazaar_soldier': [_if(_flag(HEARD), msg('bazaar_after'), [msg('bazaar'), _flag_on(BAZAAR)])],
        # FC 는 bit2 가 서면 계산대 너머가 아닐 때 꿀 이야기. 밤에는 가게를 닫으므로 밤 쪽에 둔다
        'shop_night': [_if(_flag(HEARD), msg('shop_hint'), msg('shop_closed'))],
        'throne_soldier': [_if(_flag(CURED), msg('throne_start'),
                               [_if(_flag(BAZAAR), [msg('throne_soldier'), _flag_on(HEARD)], msg('throne_start'))])],
        # 꿀을 가진 채 말을 걸면 먹인다(FC 는 왕 앞 (09,08)에서 どうぐ). 걷어찬 뒤 처음 돌아왔을 때는 FC 07A3
        'king': [_if(_flag(CURED), msg('king_after'),
                     [_if(_flag(HEARD),
                          [_if({"code": "11", "item": HONEY}, [msg('honey_use'), _flag_on(CURED), msg('king_cure')],
                               msg('king_silent'))],
                          [_if(_flag(ch2.KICKED), msg('king_back'), ask)])])],
        'minister': [_if(_flag(CURED), msg('minister_cured'),
                         [_if(_flag(BAZAAR), msg('minister_ill'), msg('minister_start'))])],
        'guard': [_if(_flag(CURED), msg('guard_start'), [_if(_flag(BAZAAR), msg('guard_ill'), msg('guard_start'))])],
        'gon': [_if(_flag(CURED), msg('gon_start'), [_if(_flag(BAZAAR), msg('gon_ill'), msg('gon_start'))])],
        'maroni': [_if(_flag(BAZAAR), [_if(_flag(CURED), msg('maroni_day'), msg('maroni_ill'))],
                       [_if(DAY, msg('maroni_day'), msg('maroni_night'))])],
        'shrine_pass': [msg('shrine_pass')],
    }
    return [bodies[name] for name in TALKS]


def _cmd(op, *args, **kw):
    return {"op": op, "args": list(args), **kw}


def _walk(*cells):
    return [c for x, y in cells for c in (_cmd('13', x, y), _cmd('14'))]


def scripts(ctx):
    at = ctx.at
    lo, hi = lambda v: v & 0xFF, lambda v: v >> 8
    msg = lambda k: _cmd('21', lo(ctx.msg[k]), hi(ctx.msg[k]))  # noqa: E731
    call = lambda a: _cmd('37', *_al(a))  # noqa: E731
    out = {
        # 바자: X 09 줄을 지나면 병사가 부른다. 이미 들었으면 대화만
        'bazaar_soldier': [_cmd('06', *BAZAAR, target='done'), _cmd('05', *_al(at['bazaar_rect'])), _cmd('3F'),
                           msg('bazaar'), _cmd('10', *BAZAAR), _cmd('40'), _cmd('16', label='done')],
        # 왕좌의 방: 바자에서 들은 뒤 계단 위 줄에 서면 병사가 알린다
        'throne_soldier': [_cmd('06', *CURED, target='done'), _cmd('06', *HEARD, target='done'),
                           _cmd('09', 0x80 | BAZAAR[0], BAZAAR[1]), _cmd('05', *_al(at['throne_rect'])), _cmd('3F'),
                           msg('throne_soldier'), _cmd('10', *HEARD), _cmd('40'), _cmd('16', label='done')],
        # 탑 꼭대기: 줄 0C 에 들어서면 엘프 둘이 말하고 위로 달아나 사라진다. 한 번 달아나면 다시 나오지 않는다
        'elf_a': [_cmd('06', *SEEN, target='gone'), _cmd('05', *_al(at['elf_rect'])), _cmd('3F'), msg('elves'),
                  _cmd('10', *SEEN), _cmd('1C')] + _walk(ELF_AWAY[0]) + [
                  _cmd('52'), _cmd('40'), _cmd('16'), _cmd('28', label='gone'), _cmd('52'), _cmd('16')],
        'elf_b': [_cmd('06', *SEEN, target='gone'), _cmd('09', 0x80 | SEEN[0], SEEN[1]), _cmd('1C')] +
                 _walk(ELF_AWAY[1]) + [_cmd('52'), _cmd('16'), _cmd('28', label='gone'), _cmd('52'), _cmd('16')],
        # 보이지 않는 인물: 엘프가 달아난 뒤 그 자리를 밟으면 꿀을 찾는다
        'honey': [_cmd('28'), _cmd('52'), _cmd('06', *GOT, target='done'), _cmd('09', 0x80 | SEEN[0], SEEN[1]),
                  _cmd('05', *_al(at['honey_rect'])), _cmd('3F'), msg('found'), call(at['give_honey']),
                  _cmd('10', *GOT), _cmd('40'), _cmd('16', label='done')],
    }
    return [{"address": SCRIPTS[USE[k]], "commands": v} for k, v in out.items()]


def _src(name):
    return {"list": SCRIPT_LIST, "index": USE[name]}


def _at(e):
    return (e["fields"]["x"], e["fields"]["y"])


def _edit(entries, where, time=None, src=None, **fields):
    """where 셀(time 이 있으면 그 시간대만)의 엔트리를 제자리에서 고친다. 제자리여야 같은 엔트리를 담은 다른 대체
    목록(dq4ch2event 의 ch2_throne_joined 따위)에도 함께 들어간다. src 는 빌린 스크립트(USE 의 이름)."""
    hit = 0
    for e in entries:
        if _at(e) == where and time in (None, e["time"]):
            more = dict(fields)
            if src is not None:
                e["from"] = _src(src)
                # 빌린 원본의 이동 간격이 0 이면 스크립트가 돌지 않는다(dq4ch2event._invisible)
                more.setdefault('interval', max(1, e["fields"].get("interval", 1)))
            e["fields"] = {**e["fields"], **more}
            hit += 1
    if not hit:
        raise SystemExit(f'왕 병: {where} 에 고칠 인물이 없음')


def npc_lists(lists, ctx):
    t = ctx.talk
    if SHRINE not in lists:
        return [], []           # 인물 없이 옮긴 목록(dq4npcport.port 의 with_people=False)
    bazaar = lists[BAZAAR_MAP]["entries"]
    _edit(bazaar, BAZAAR_SOLDIER, src='bazaar_soldier', talk=t['bazaar_soldier'])
    _edit(bazaar, SHOP_NIGHT, 'night', talk=t['shop_night'])
    throne = lists[ch2.THRONE]["entries"]
    _edit(throne, THRONE_SOLDIER, src='throne_soldier', talk=t['throne_soldier'])
    _edit(throne, ch2.KING_CELL, 'day', talk=t['king'])
    _edit(throne, MINISTER, 'day', talk=t['minister'])
    _edit(throne, GUARD, 'day', talk=t['guard'])
    castle = lists[ch2.CASTLE]["entries"]
    for time, where in GON.items():
        _edit(castle, where, time, talk=t['gon'])
    _edit(lists[SARAN]["entries"], MARONI, talk=t['maroni'])
    top = lists[TOWER_TOP]["entries"]
    for name, where in zip(('elf_a', 'elf_b'), ELVES):
        _edit(top, where, src=name, gfx=ELF_PICTURE)
    top += [{"from": _src('honey'), "time": time,
             "fields": {"x": 0, "y": 1, "facing": "down", "talk": t['shrine_pass'], "gfx": 0x01, "layer": 0,
                        "interval": 1}} for time in ('day', 'night')]
    # 사당: 처음에는 병사가 위 방으로 가는 틈에 서서 막고, 왕이 나으면 원래 칸에서 길을 비킨다
    shrine = lists[SHRINE]["entries"]
    opened = []
    for e in list(shrine):
        if _at(e) == SHRINE_SOLDIER:
            opened.append({**e, "fields": {**e["fields"], "talk": t['shrine_pass'], "interval": 0}})
            e["fields"] = {**e["fields"], "x": SHRINE_BLOCK[0], "y": SHRINE_BLOCK[1], "facing": "down", "interval": 0}
        else:
            opened.append(e)
    new = [{"name": SHRINE_OPEN, "entries": opened}]
    over = [{"map": SHRINE, "flag": CURED[0], "when": "on", "mask": CURED[1], "list": f"new:{SHRINE_OPEN}"}]
    return new, over


def start_messages(ctx):
    """장 시작 상태(사건 flag 없음)에서 이 모듈이 대화를 바꾼 인물의 첫 메시지."""
    m = ctx.msg
    out = {(BAZAAR_MAP, FC_BAZAAR_SOLDIER, None): m['bazaar'], (BAZAAR_MAP, FC_SHOP, True): m['shop_closed'],
           (ch2.THRONE, FC_THRONE_SOLDIER, None): m['throne_start'], (ch2.THRONE, ch2.FC_KING, False): m['king_ask'],
           (ch2.THRONE, FC_MINISTER, False): m['minister_start'], (ch2.THRONE, FC_GUARD, False): m['guard_start'],
           (ch2.CASTLE, FC_GON, None): m['gon_start'],
           (SARAN, FC_MARONI, False): m['maroni_day'], (SARAN, FC_MARONI, True): m['maroni_night'],
           # 엘프 옆에 서면 말을 걸기 전에 달아나는 장면이 먼저 뜬다
           (TOWER_TOP, FC_ELF, None): m['elves']}
    return out


def absent(ctx):
    """{(맵, DQ5 셀 x, y, 밤)}: 처음 상태 목록에서 FC 자리를 떠난 인물(사당 병사는 틈을 막는 칸에 섬)."""
    return {(SHRINE, *SHRINE_SOLDIER, night) for night in (False, True)}
