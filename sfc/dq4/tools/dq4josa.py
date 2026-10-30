"""메시지에 받침을 보고 고르는 조사 코드를 더한다.

바로 앞에 찍은 글자(이름·도구 이름처럼 실행 중에 들어오는 글자 포함)의 받침으로 「은/는」 같은 조사를 고른다.
글자를 찍는 공통 입구 24:82A1 에서 마지막 글자 코드를 7E:1BC0 에 적어 두고, 메시지에서 쓰지 않는 제어 코드의
처리기를 조사 처리기로 바꾼다. 처리기는 고른 조사 글자를 이름 코드처럼 대기열(7E:0ECB)에 넣는다.
한글이 아닌 글자(가나 이름·숫자) 뒤에서는 받침 없는 쪽을 쓴다. 형식은 sfc/dq4/docs/dq4-josa-format.md.
"""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

from dq5map import lorom  # noqa: E402

# 코드: (받침 있을 때, 없을 때, ㄹ 받침을 없음으로 볼지). 1000 번대 표(24:8204, 1000~101D) 뒤에 새로 받는다.
# 빈 1000 번대 칸은 셋뿐이고(1009·1014 는 전투 해석기 21:94F8 이 이름 코드로 씀), 빈 1100 번대 칸은 들어가기 전에
# 말하는 인물을 찾아(24:81BF) 서술문에서 「エラーダス!!」 창이 떴다
JOSA = {
    0x101E: ('은', '는', False),
    0x101F: ('이', '가', False),
    0x1020: ('을', '를', False),
    0x1021: ('으로', '로', True),
    0x1022: ('과', '와', False),
    0x1023: ('아', '야', False),
    0x1024: ('이여', '여', False),
}
TABLE_COUNT = 0x1E
# 24:81D1 AND #$00FF / CMP #$001E / BCS 81E4 를 JML 로. 표 안이면 24:81D9(ASL / TAX / JMP ($8204,X))로 돌아간다
DISPATCH_AT = 0x2481D1
DISPATCH_ORIG = bytes.fromhex('29 ff 00 c9 1e 00 b0 0b')
DISPATCH_BACK, DISPATCH_BAD = 0x2481D9, 0x2481E4
PRINT_AT = 0x2482A1
PRINT_ORIG = bytes.fromhex('48 e2 30 ae 06 0e')      # PHA / SEP #$30 / LDX $0E06. A = 글자 코드(16비트)
QUEUE = 0x7E0ECB
# 대기열을 켜고 맨 앞 글자를 꺼내 찍는 곳. 이름 처리기(24:84C3)도 대기열을 채운 뒤 BRL 로 여기에 온다. 비트만 켜고
# 고리(24:8170)로 돌아가면 다음 차례에 그사이 읽은 코드가 버려져 띄어쓰기·줄바꿈이 빠졌다(실측)
QUEUE_RUN = 0x248275
LAST = 0x7E1BC0      # 마지막에 찍은 글자. 7E:1BBE~ 79바이트는 DQ5 다섯 실행에서 접근이 없었다(dq5-hangul-format.md)
CODE_AT = 0x5E8000
GLYPH0 = 0x3DB


def le(v, n):
    return v.to_bytes(n, 'little')


def syllables():
    """dq4menumsg 글자 표에서 호환 자모·완성형 글자가 이어진 구간과 그 첫 글자 코드."""
    import dq4menumsg
    chars = dq4menumsg.CHARS
    hangul = lambda c: '\u3131' <= c <= '\u3163' or '가' <= c <= '힣'  # noqa: E731
    first = next(i for i, c in enumerate(chars) if hangul(c))
    run = []
    for c in chars[first:]:
        if not hangul(c):
            break
        run.append(c)
    return GLYPH0 + first, run


def jong_table(run):
    """글자마다 0 받침 없음, 1 받침 있음, 2 ㄹ 받침. 자음 자모(ㄱ~ㅎ)는 그 이름(기역·비읍…)처럼 받침이 있는 것으로 본다."""
    out = bytearray()
    for c in run:
        if c <= '\u3163':
            out.append(0 if c >= '\u314F' else 2 if c == 'ㄹ' else 1)
            continue
        j = (ord(c) - 0xAC00) % 28
        out.append(0 if j == 0 else 2 if j == 8 else 1)
    return bytes(out)


def glyph_code(ch):
    import dq4menumsg
    return GLYPH0 + dq4menumsg.CHARS.index(ch)


def queue_write(text):
    """M·X 16 에서 대기열에 text 의 글자 코드와 FFFF 를 쓴다."""
    out = bytearray()
    for i, v in enumerate([glyph_code(c) for c in text] + [0xFFFF]):
        out += bytes((0xA9, *le(v, 2), 0x8F, *le(QUEUE + 2 * i, 3)))   # LDA #v / STA long
    return bytes(out)


def handler(code, table_at, first, count):
    """조사 처리기 몸통(끝 처리 전). 마지막 글자가 완성형이 아니면 받침 없음으로 본다."""
    has, none, rieul_none = JOSA[code]
    with_, without = queue_write(has), queue_write(none)
    head = bytes((0x08, 0xC2, 0x30,                                  # PHP / REP #$30
                  0xAF, *le(LAST, 3), 0x38, 0xE9, *le(first, 2),      # LDA LAST / SEC / SBC #first
                  0xC9, *le(count, 2)))                               # CMP #count
    look = bytes((0xAA, 0xBF, *le(table_at, 3), 0x29, 0xFF, 0x00))   # TAX / LDA table,X / AND #$00FF
    # A: 0 없음, 1 있음, 2 ㄹ. ㄹ 을 없음으로 보면 1 일 때만, 아니면 0 이 아닐 때 받침 있음
    test = bytes((0xC9, 0x01, 0x00, 0xD0)) if rieul_none else bytes((0xF0,))   # CMP #1 / BNE · BEQ → 없음
    to_none_from_test = len(with_) + 2
    after_bcs = look + test + bytes((to_none_from_test,)) + with_ + bytes((0x80, len(without)))  # … / BRA 끝
    tail = bytes((0x28,))                                             # PLP
    # BCS 는 look·test·with·BRA 를 건너 없음으로
    return head + bytes((0xB0, len(after_bcs))) + after_bcs + without + tail


class Layout:
    def __init__(self, base=CODE_AT):
        first, run = syllables()
        self.first, self.count = first, len(run)
        self.table = jong_table(run)
        for _ in range(2):
            at = base
            self.print_at = at
            hook = self.print_hook()
            at += len(hook)
            self.dispatch_at = at
            dispatch = self.dispatch(getattr(self, 'handler_at', {c: 0 for c in JOSA}))
            hook += dispatch
            at += len(dispatch)
            self.handler_at, codes = {}, []
            table_at = getattr(self, 'table_at', 0)
            for code in JOSA:
                self.handler_at[code] = at
                h = handler(code, table_at, self.first, self.count)
                h += bytes((0x5C, *le(QUEUE_RUN, 3)))     # JML: 이름 처리기처럼 곧바로 대기열을 꺼내 찍음
                codes.append(h)
                at += len(h)
            self.table_at = at
        self.blob = hook + b''.join(codes) + self.table

    def dispatch(self, handler_at):
        """M 16, A = 코드. 조사 코드면 그 처리기로, 아니면 원래 길."""
        out = bytearray((0x29, 0xFF, 0x00, 0xC9, TABLE_COUNT, 0x00, 0xB0, 0x04,   # AND / CMP #$1E / BCS +4
                         0x5C, *le(DISPATCH_BACK, 3)))                         # JML 24:81D9
        for code in JOSA:
            out += bytes((0xC9, code & 0xFF, 0x00, 0xD0, 0x04, 0x5C, *le(handler_at[code], 3)))  # CMP / BNE / JML
        return bytes(out) + bytes((0x5C, *le(DISPATCH_BAD, 3)))

    def print_hook(self):
        # 24:82A1 의 PHA 뒤에서 불려 A(16비트) 를 적고, 덮은 SEP #$30 / LDX $0E06 을 대신한다(DB 그대로)
        return bytes((0x8F, *le(LAST, 3), 0xE2, 0x30, 0xAE, 0x06, 0x0E, 0x6B))


def writes():
    lay = Layout()
    return [(PRINT_AT, bytes((0x48, 0x22, *le(lay.print_at, 3), 0xEA)), PRINT_ORIG),
            (DISPATCH_AT, bytes((0x5C, *le(lay.dispatch_at, 3), 0xEA, 0xEA, 0xEA, 0xEA)), DISPATCH_ORIG),
            (CODE_AT, lay.blob, None)]


def apply(data):
    d = bytearray(data)
    for addr, payload, orig in writes():
        o = lorom(addr)
        if orig is not None and bytes(d[o:o + len(orig)]) != orig:
            raise SystemExit(f'{addr:06X}: 원래 바이트가 아님 {d[o:o + len(orig)].hex(" ")}')
        if orig is None and any(d[o:o + len(payload)]):
            raise SystemExit(f'{addr:06X}: 비어 있지 않은 자리')
        d[o:o + len(payload)] = payload
    return bytes(d)
