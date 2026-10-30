"""메시지의 물건·주문 이름({100A}·{100B})을 한글로 찍는다.

창 글자(dq4windowtext.py)와 같이 롬의 이름 표를 nds/dq4/tables/adopt.tsv 와 가나 키로 잇고, 맞는 이름만 한글
글자 코드 목록으로 둔다. 이름 종류를 고르는 공통 자리 24:89BB(STA $43 / JSR $889F)에 훅을 걸어, 한글 이름이
있으면 이름 번호($F5)를 꺼내고 글자 코드를 대기열에 넣어 곧바로 찍는다(이름 처리기와 같은 길). 없으면 원래
가나 길로 돌아간다. 형식은 sfc/dq4/docs/dq4-josa-format.md 「이름」.
"""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

from dq5map import lorom  # noqa: E402

# 이름 표 5 물건, 3 주문(dq4windowtext.KINDS 의 adopt 표). 몬스터(4)는 {100F} 가 이름 뒤에 Ａ·Ｂ 를 붙이는데 훅이
# 그 뒤를 건너뛰므로 넣지 않는다
KINDS = (5, 3)
HOOK_AT = 0x2489BB
HOOK_ORIG = bytes.fromhex('85 43 20 9f 88')     # STA $43 / JSR $889F(이름 번호를 $F5 에서 꺼냄)
BACK = 0x2489BD                                 # 원래 JSR $889F
QUEUE_RUN = 0x248275
QUEUE = 0x7E0ECB
CODE_AT = 0x5E9000


def le(v, n):
    return v.to_bytes(n, 'little')


def korean_names(data):
    """{종류: {번호: 한글}}. 메시지 글자에 없는 글자가 든 이름은 뺀다(원래 가나로 찍힘)."""
    import dq4menumsg
    import dq4windowtext
    known = set(dq4menumsg.CHARS) | {' '}
    out = {}
    for kind in KINDS:
        ko = dq4windowtext.adopted(dq4windowtext.KINDS[kind][0])
        names = dq4windowtext.rom_names(data, kind)
        out[kind] = {n: ko[dq4windowtext.kana_key(x)] for n, x in enumerate(names)
                     if x and dq4windowtext.kana_key(x) in ko and set(ko[dq4windowtext.kana_key(x)]) <= known}
    return out


def codes(text):
    import dq4menumsg
    return dq4menumsg.codes([text])


class Layout:
    def __init__(self, names, base=CODE_AT):
        self.names = names
        hook_len = len(self.hook({k: 0 for k in KINDS}))
        at = base + hook_len
        self.tables = {}
        tables = bytearray()
        lists = bytearray()
        list_at = at + 2 * 256 * len(KINDS)
        for kind in KINDS:
            self.tables[kind] = at + len(tables)
            for n in range(256):
                if n in names[kind]:
                    tables += le((list_at + len(lists)) & 0xFFFF, 2)
                    for c in codes(names[kind][n]):
                        lists += le(c, 2)
                    lists += le(0xFFFF, 2)
                else:
                    tables += bytes(2)
        self.blob = self.hook(self.tables) + bytes(tables) + bytes(lists)
        if (base & 0xFFFF) + len(self.blob) > 0x10000:
            raise ValueError('뱅크를 넘음')

    def hook(self, tables):
        """M 8, A = 이름 종류. 같은 직접 페이지에서 $F5 를 읽고 민다(24:889F 와 같은 일)."""
        back = bytes((0x5C, *le(BACK, 3)))                                # JML 24:89BD
        found = bytes((
            0xA0, 0x00, 0x00,                                             # LDY #0
            0xBF, *le(CODE_AT & 0xFF0000, 3),                             # loop: LDA $5E0000,X
            0x99, 0xCB, 0x0E,                                             # STA $0ECB,Y(DB 7E)
            0xE8, 0xE8, 0xC8, 0xC8, 0xC9, 0xFF, 0xFF, 0xD0, 0xF0,         # INX×2 / INY×2 / CMP #$FFFF / BNE loop
            0xAB,                                                         # PLB
            0xE2, 0x20, 0xA5, 0xF6, 0x85, 0xF5, 0xA5, 0xF7, 0x85, 0xF6,   # $F5 ← $F6 ← $F7 ← $F8 ← 0
            0xA5, 0xF8, 0x85, 0xF7, 0x64, 0xF8,
            0x68, 0x68, 0xC2, 0x20, 0x68,             # PLA(훅의 PHP) / PLA(89A8 의 PHP) / REP #$20 / PLA(복귀)
            0x5C, *le(QUEUE_RUN, 3)))                                     # JML 24:8275
        out = bytearray((0x85, 0x43, 0x08,                                 # STA $43(원래) / PHP(원래 폭으로 돌아가려고)
                         0x24, 0x70, 0x30, 0x00))                         # BIT $70 / BMI 없음(바이트를 그대로 옮기는 길)
        bmi_at = len(out) - 1
        branches = []
        for kind in KINDS:
            out += bytes((0xC9, kind, 0xD0, 0x00))                        # CMP #kind / BNE 다음
            bne_at = len(out) - 1
            out += bytes((0xC2, 0x30, 0xA5, 0xF5, 0x29, 0xFF, 0x00, 0x0A, 0xAA,   # REP #$30 / LDA $F5 / AND / ASL / TAX
                          0xBF, *le(tables[kind], 3),                     # LDA 표,X
                          0xF0, 0x00))                                    # BEQ 없음
            branches.append(len(out) - 1)
            out += bytes((0xAA, 0x8B, 0xF4, 0x7E, 0x7E, 0xAB, 0xAB, 0x80, 0x00))   # TAX / PHB / PEA $7E7E / PLB×2 / BRA found
            branches.append(('found', len(out) - 1))
            out[bne_at] = len(out) - (bne_at + 1)
        none_at = len(out)
        out += bytes((0x28, 0xA5, 0x43)) + back                           # 없음: PLP / LDA $43 / JML 89BD
        out[bmi_at] = none_at - (bmi_at + 1)
        found_at = len(out)
        out += found
        for b in branches:
            if isinstance(b, tuple):
                out[b[1]] = found_at - (b[1] + 1)
            else:
                out[b] = none_at - (b + 1)
        # 종류가 셋 모두 아니면 CMP 고리를 지나 none 으로 떨어진다
        return bytes(out)


def writes(data):
    lay = Layout(korean_names(data))
    return [(HOOK_AT, bytes((0x5C, *le(CODE_AT, 3), 0xEA)), HOOK_ORIG), (CODE_AT, lay.blob, None)]


def apply(data):
    d = bytearray(data)
    for addr, payload, orig in writes(data):
        o = lorom(addr)
        if orig is not None and bytes(d[o:o + len(orig)]) != orig:
            raise SystemExit(f'{addr:06X}: 원래 바이트가 아님 {d[o:o + len(orig)].hex(" ")}')
        if orig is None and any(d[o:o + len(payload)]):
            raise SystemExit(f'{addr:06X}: 비어 있지 않은 자리')
        d[o:o + len(payload)] = payload
    return bytes(d)
