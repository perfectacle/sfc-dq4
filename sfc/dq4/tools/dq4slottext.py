"""카지노 슬롯 화면 안 글(DQ5 슬롯 전용 글)을 한글로.

슬롯 화면의 글은 메시지 표가 아니라 뱅크 11 의 바이트 문자열을 `11:B970` 이 BG3 타일맵 버퍼 `7E:6000`(매 프레임 VRAM
워드 `1400` 으로 보냄)에 바로 찍는다. 바이트가 곧 BG3 타일 번호이고, `84`·`92`·`93` 은 앞 글자 위 줄 탁점, `FF` 는
줄 첫 칸에서 한 줄 아래, `FE` 주소(2) 자리(1)는 수, `FD` 는 타일 bit8 켜고 끄기, `FC` n 은 n 칸 건너뛰기, `00` 은 끝이다.
슬롯 화면은 `11:BFCC` 가 BG3 글자 타일(`01`~`8A` 가나 등)만 올리고 `10C`~`1FF` 는 비어 있다.

그래서 글을 Galmuri7(한 줄 8점 안)로 미리 그려 타일로 두고, `11:BF83` 의 `JSL $11BFCC` 를 그 뒤에 타일을 올리는 코드로
바꾼다. 문자열은 `FD` 로 bit8 을 켠 타일 번호 줄로 다시 써서 원래 자리(`11:8FC9`~`9043`, 바로 뒤 `9044` 는 배당 표)에
둔다. 형식은 sfc/dq4/docs/dq4-chapter3-towns-format.md 「카지노」.
"""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

from dq5map import lorom  # noqa: E402

STRINGS_AT, STRINGS_END = 0x118FC9, 0x119044
HOOK_AT, HOOK_ORIG = 0x11BF83, bytes.fromhex('22 CC BF 11')          # JSL $11BFCC(슬롯 화면 BG3 글자 타일)
SCREEN_INIT = 0x11BFCC
CODE_AT = 0x4FF800
BG3_CHR = 0x4000                  # 슬롯 화면 BG3 글자 기준(VRAM 워드)
FIRST_TILE, TILE_END = 0x10C, 0x200   # 100~10B 는 코인 수 숫자 칸
FONT = 'galmuri7'
NEWLINE, NUMBER, BIT8, SKIP, END = 0xFF, 0xFE, 0xFD, 0xFC, 0x00
MARKS = (0x84, 0x92, 0x93)
KANA = range(0x10, 0x7B)
# (이름, 원래 주소, LDY # 피연산자 자리, 줄들). 줄은 글, 또는 조각 목록: 글 조각과 ('skip', n)·('number', 원래 FE 뒤 3바이트)
TEXTS = (
    ('again', 0x118FC9, 0x11B422, ('한 번 더 슬롯을 하시겠습니까?',
                                   (('skip', 6), '예', ('skip', 5), '아니요'))),
    ('intro', 0x118FE8, 0x11B389, ('위 버튼으로 코인을 넣고', 'A 버튼으로 시작합니다.')),
    ('win', 0x11900A, 0x11B3A6, ('축하합니다!', (('number', bytes.fromhex('56 12 88')), '장의 코인이 당첨!'))),
    ('short', 0x11902D, 0x11B375, ('코인이 모자랍니다.',)),
    ('lose', 0x119039, 0x11B3EF, ('아쉽네요!',)),
)


def le(v, n):
    return v.to_bytes(n, 'little')


def _pieces(line):
    return (line,) if isinstance(line, str) else line


class Layout:
    """글 조각을 그린 타일(같은 타일은 한 번)과 문자열 바이트."""

    def __init__(self, font):
        import dq4menupatch
        self.tiles, index, self.strings = [], {}, {}
        # 타일 번호의 낮은 바이트가 제어 바이트면 문자열이 그것으로 읽힌다
        numbers = (n for n in range(FIRST_TILE, TILE_END) if n & 0xFF not in (END, *MARKS, SKIP, BIT8, NUMBER, NEWLINE))
        for name, _, _, lines in TEXTS:
            out = bytearray((BIT8,))
            for k, line in enumerate(lines):
                if k:
                    out += bytes((NEWLINE, NEWLINE))
                for piece in _pieces(line):
                    if isinstance(piece, str):
                        for col in dq4menupatch.render(font, piece):
                            if any(any(r) for r in col[8:]):
                                raise ValueError(f'{piece!r}: 한 줄(8점) 밖의 점')
                            tile = dq4menupatch.tile_2bpp(col[:8])
                            if tile not in index:
                                n = next(numbers, None)
                                if n is None:
                                    raise ValueError(f'슬롯 글 타일이 {FIRST_TILE:03X}~{TILE_END - 1:03X} 를 넘음')
                                index[tile] = n
                                self.tiles.append((n, tile))
                            out.append(index[tile] & 0xFF)
                    elif piece[0] == 'skip':
                        out += bytes((SKIP, piece[1]))
                    else:
                        # 수는 원래 글처럼 bit8 을 끄고 찍는다(코인 수 숫자 칸은 bit8 을 켠 100~ 이 따로 있음)
                        out += bytes((BIT8, NUMBER, *piece[1], BIT8))
            self.strings[name] = bytes(out + bytes((END,)))
        if sum(map(len, self.strings.values())) > STRINGS_END - STRINGS_AT:
            raise ValueError(f'슬롯 글 {sum(map(len, self.strings.values()))}바이트가 원래 자리를 넘음')

    def code(self):
        """JSL 11:BFCC(원래) 뒤, 강제 블랭크 그대로 한글 타일을 BG3 글자 칸 FIRST_TILE~ 에 올린다. 그때 DB 는 11."""
        from dq4chapterbox import dma_vram
        last = self.tiles[-1][0]
        data = bytearray(16 * (last + 1 - FIRST_TILE))
        for n, tile in self.tiles:
            data[16 * (n - FIRST_TILE):16 * (n + 1 - FIRST_TILE)] = tile
        data = bytes(data)
        head = bytes((0x22, *le(SCREEN_INIT, 3), 0x08, 0xE2, 0x20, 0xC2, 0x10))   # JSL 11:BFCC / PHP / SEP #$20 / REP #$10
        tail = bytes((0x28, 0x6B))                                                  # PLP / RTL
        size = len(head) + len(dma_vram(0, 0, 0)) + len(tail)
        return head + dma_vram(BG3_CHR + FIRST_TILE * 8, CODE_AT + size, len(data)) + tail + data


def writes(font):
    lay = Layout(font)
    out = [(HOOK_AT, bytes((0x22, *le(CODE_AT, 3))), HOOK_ORIG), (CODE_AT, lay.code(), None)]
    at = STRINGS_AT
    for name, orig_at, ldy, _ in TEXTS:
        out.append((ldy, le(at & 0xFFFF, 2), le(orig_at & 0xFFFF, 2)))
        out.append((at, lay.strings[name], None))
        at += len(lay.strings[name])
    out.append((at, bytes(STRINGS_END - at), None))
    return out


def apply(data, font):
    d = bytearray(data)
    o = lorom(STRINGS_AT)
    d[o:lorom(STRINGS_END)] = bytes(STRINGS_END - STRINGS_AT)
    for addr, payload, orig in writes(font):
        o = lorom(addr)
        if o + len(payload) > len(d):
            raise SystemExit(f'{addr:06X}: 롬 밖(늘린 롬에 써야 함)')
        if orig is not None and bytes(d[o:o + len(orig)]) != orig:
            raise SystemExit(f'{addr:06X}: 원래 바이트가 아님 {d[o:o + len(orig)].hex(" ")}')
        if orig is None and addr == CODE_AT and any(d[o:o + len(payload)]):
            raise SystemExit(f'{addr:06X}: 비어 있지 않은 자리')
        d[o:o + len(payload)] = payload
    return bytes(d)


def kana_in(rom, ldy):
    """롬에서 LDY # 피연산자 자리 ldy 가 가리키는 슬롯 글에 bit8 을 끈 채 찍히는 가나 타일 바이트 [(자리, 바이트)]."""
    at = 0x110000 | rom[lorom(ldy)] | rom[lorom(ldy) + 1] << 8
    bit8, out = False, []
    while True:
        b = rom[lorom(at)]
        at += 1
        if b == END:
            return out
        if b == BIT8:
            bit8 = not bit8
        elif b == NUMBER:
            at += 3
        elif b == SKIP:
            at += 1
        elif b == NEWLINE or b in MARKS:
            continue
        elif not bit8 and b in KANA:
            out.append((at - 1, b))
