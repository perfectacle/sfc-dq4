"""2장 동료 대화(はなす): 앞에 아무도 없을 때 「はなす」를 고르면 조건이 맞는 동료의 대사를 띄운다(NDS 리메이크의 동료 대화).

DQ5 의 「はなす」는 앞에 말 상대가 없으면 05:D5B9 에서 대화 창을 열고 메시지 129「その方向には誰もいない。」를 띄운다.
창 열기와 메시지(05:D5B9~D5BE)를 뱅크 05 받침으로 돌려, 받침이 창을 연 뒤 이 모듈의 네이티브가 지금 맵의 대사 목록에서 조건이 맞는 줄을 하나 고른다. 맞는
줄이 없으면 원래처럼 129 를 띄운다. 형식은 sfc/dq4/docs/dq4-chapter2-format.md 「동료 대화」.

대사 줄은 LINES 에 Line 하나씩 더한다(맵·말하는 인물·대사 이름·우선순위·시간·조건). 대사 본문은 MESSAGES 에 같은 이름으로.
"""
from dataclasses import dataclass
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4chapter1 as ch1  # noqa: E402
import dq4ch2event as ch2  # noqa: E402
import dq4ch2frenol as frenol  # noqa: E402
import dq4ch2king as king  # noqa: E402
import dq4ch2tempe as tempe  # noqa: E402
from dq4chapter1 import speak  # noqa: E402
from dq4environmentrom import _Asm  # noqa: E402

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
FLAGS = ()

MESSAGE_AT = 0x248157          # 보행 메시지(A = 번호). BRK 97+n 처리기가 부르는 것과 같음
NIGHT_TEST = 0x218000          # 캐리 = 밤(7E:075E >= F0)

# 말하는 인물: 일행 기록 +0 의 인물 번호(아리나는 주인공 기록 틀 0, 두 사람은 dq4ch2event.RECRUITS)
ALENA, KIRYL, BREY = 0x00, ch2.RECRUITS[0]['person'], ch2.RECRUITS[1]['person']
FIELD = 'field'                # 필드(7E:00BE bit7 꺼짐). 필드에서도 7E:00BC·00BD 는 떠난 맵 번호라 따로 둔다
FIELD_KEY = (0xFE, 0xFE)
TIMES = {'any': 0, 'day': 1, 'night': 2}
# 조건 종류(3바이트: 종류, 값 1, 값 2)
ON, OFF, EQUAL, LEAD, WITH, WITHOUT = 1, 2, 3, 4, 5, 6


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

    def conditions(self):
        return ([(ON, i, m) for i, m in self.on] + [(OFF, i, m) for i, m in self.off] +
                [(EQUAL, i, v) for i, v in self.equal] + ([(LEAD, self.lead, 0)] if self.lead is not None else []) +
                [(WITH, p, 0) for p in self.with_] + [(WITHOUT, p, 0) for p in self.without])


def _pair(*parts):
    """두 사람이 이어 말하는 한 메시지: speak(…) 둘을 쪽 넘김으로 잇는다."""
    out = []
    for p in parts:
        out += ([ch1.PAGE] if out else []) + p[:-1]
    return out + [ch1.END]


# 장치를 보이는 표본 대사. 옮길 범위와 NDS 대사는 다음 단계에서 정한다
MESSAGES = {
    'tempe_won_kiryl': speak('크리프트', '마을 사람들의/웃는 얼굴을 보니/저도 마음이/놓입니다.'),
    'tempe_won_brey': speak('브라이', '허허허. 공주님의/솜씨가 이 정도일/줄은 이 늙은이도/미처 몰랐습니다.'),
    'tempe_day_kiryl': speak('크리프트', '이 마을에는 어딘가/어두운 기운이/감도는군요.'),
    'tempe_night_brey': speak('브라이', '제물을 바치라니/고약한 괴물이로군요./공주님, 부디/조심하십시오.'),
    'castle_joined': _pair(speak('크리프트', '임금님께 들키면/큰일입니다./어서 성을/나가시지요.'),
                           speak('브라이', '허허, 이제 와서/말려도 소용없지요.')),
    'frenol_kidnapped_kiryl': speak('크리프트', '공주님을 사칭하다니/괘씸한 일이지만/붙잡혀 간 사람은/구해야지요.'),
    'frenol_rescued_brey': speak('브라이', '가짜라고는 하나/공주님을 닮은/아가씨가 무사해서/다행입니다.'),
    'king_cured_kiryl': speak('크리프트', '임금님의 목소리가/돌아와서 정말/다행입니다.'),
    'king_cured_brey': speak('브라이', '이제 성 걱정은/덜었으니 공주님/마음껏 세상을/돌아보시지요.'),
    'field_kiryl': speak('크리프트', '공주님, 너무 앞서/달려가지 마십시오.'),
}

LINES = (
    Line(ch2.CASTLE, KIRYL, 'castle_joined', priority=5, on=(ch2.JOINED,), with_=(BREY,)),
    Line(ch2.TEMPE, KIRYL, 'tempe_won_kiryl', priority=3, on=(tempe.WON,)),
    Line(ch2.TEMPE, BREY, 'tempe_won_brey', priority=3, on=(tempe.WON,)),
    Line(ch2.TEMPE, KIRYL, 'tempe_day_kiryl', priority=5, time='day', off=(tempe.WON,)),
    Line(ch2.TEMPE, BREY, 'tempe_night_brey', priority=5, time='night', off=(tempe.WON,)),
    Line(frenol.TOWN, BREY, 'frenol_rescued_brey', priority=3, on=(frenol.RESCUED,)),
    Line(frenol.TOWN, KIRYL, 'frenol_kidnapped_kiryl', priority=5, on=(frenol.KIDNAPPED,)),
    Line(ch2.THRONE, KIRYL, 'king_cured_kiryl', priority=3, on=(king.CURED,)),
    Line(ch2.THRONE, BREY, 'king_cured_brey', priority=3, on=(king.CURED,)),
    Line(FIELD, KIRYL, 'field_kiryl', priority=9, lead=ALENA),
)

DATA_ENTRIES = ('maps',)


def _key(mp):
    if mp == FIELD:
        return FIELD_KEY
    g, m = mp.split('/')
    return int(g, 16), int(m, 16)


def record(line, msg):
    """줄 하나의 바이트: 길이, 우선순위, 말하는 인물, 시간, 메시지(2), 조건 수, 조건(3바이트씩)."""
    conds = line.conditions()
    body = bytes((line.priority, line.speaker, TIMES[line.time], msg & 0xFF, msg >> 8 & 0xFF, len(conds)))
    body += b''.join(bytes(c) for c in conds)
    if len(body) + 1 > 0xFF:
        raise ValueError(f'{line.message}: 조건이 너무 많음')
    return bytes((len(body) + 1,)) + body


def lists(msg, lines=None):
    """{(맵 바이트 둘): [줄 바이트]}. 줄은 우선순위 차례(같으면 LINES 차례). msg 는 {이름: 번호}(None 이면 0)."""
    lines = LINES if lines is None else lines
    out = {}
    for line in sorted(lines, key=lambda ln: ln.priority):
        if line.message not in MESSAGES:
            raise ValueError(f'{line.message}: MESSAGES 에 없는 대사')
        out.setdefault(_key(line.map), []).append(record(line, msg[line.message] if msg else 0))
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
    return a


def native(ctx):
    """(바이트, {이름: 주소}). 코드 뒤에 맵 표(맵 바이트 둘, 목록 주소; FF FF 로 끝)와 맵마다의 줄(길이 0 으로 끝)."""
    a = _code(ctx.code_at)
    code, labels = a.assemble({'maps': 0})
    rows = lists(ctx.msg)
    maps_at = ctx.code_at + len(code)
    at = maps_at + 4 * len(rows) + 2
    head, body = bytearray(), bytearray()
    for key, recs in rows.items():
        head += bytes(key) + (at & 0xFFFF).to_bytes(2, 'little')
        blob = b''.join(recs) + b'\x00'
        body += blob
        at += len(blob)
    head += b'\xff\xff'
    code, labels = a.assemble({'maps': maps_at})
    labels['maps'] = maps_at
    out = code + bytes(head) + bytes(body)
    if (ctx.code_at & 0xFFFF) + len(out) > 0x10000:
        raise SystemExit('동료 대화 코드가 뱅크를 넘음')
    return out, {'talk': labels['talk'], 'maps': maps_at}


def hooks(ctx):
    stub = bytes((0x00, 0x95, 0x00, 0x22, *ctx.at['talk'].to_bytes(3, 'little'), 0x60))
    assert len(stub) == STUB_LEN
    return [(STUB_AT, bytes(STUB_LEN), stub),
            (HOOK_AT, HOOK_ORIG, bytes((0x20, STUB_AT & 0xFF, STUB_AT >> 8 & 0xFF, 0xEA, 0xEA, 0xEA)))]


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
