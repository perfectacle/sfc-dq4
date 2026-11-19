"""엔돌 네네의 가게(dq4ch3endor 가 부르는 부분): 카운터 너머 대화로 물건을 내놓고, 날이 바뀌면 팔린 값을 매상으로.

FC(fc/dq4/docs/dq4-chapter3-format.md 「무기점 일」 끝, 15:$9E99·$9F79, 헤드리스 실측):
  카운터  04/00 네네(대화 075)에게 카운터 너머로 말을 걸면 036B 「しなものを しいれてきてくれた？」. 「예」 면 매상이 있으면
          036D 「きのうの うりあげよ」 로 건네고 0 으로. 이어 물건을 골라 FC 맡긴 물건 목록($61DB)에 내놓는다(036E~0371,
          값은 물건 값 × 1.5 를 안내). 목록이 120개면 0377. 「아니요」 면 036C.
  매상    날이 바뀔 때(잠, 15:$9F79) 목록의 물건마다 rand < C0 이면 값 × (96 + ⌊r × 33/256⌋)/64 를 매상에 더하고 목록에서
          뺀다. どうのつるぎ(100) 넷: 세 번 재어 셋 514·넷 700·둘 360(한 개 150~200).

FC 3장에는 맡기는 곳이 없어 맡긴 물건 목록이 곧 네네의 가게 물건이다. 이 롬은 DQ5 ふくろ(7E:2250)를 메뉴에서 늘 쓰므로
가게 물건은 둘째 변수 칸(dq4ch3slots.VARS2)의 12칸에 따로 둔다. 물건 고르기는 DQ5 필드 도구 창(BRK 95 0F, 05:DA56 과
같이 $E8 이 고른 칸)으로 열어 FC 처럼 값이 보이지 않고, 안내·되묻기는 네네 메시지로 바꾼 루프(nene_stock)가 한다. FC 0374 「예」 의 가게 물건 창(이름만, 15:$9F5C)은 DQ5 필드
도구 창에 가게 칸을 잠시 맞바꿔 넣어 보인다(nene_view).
"""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4chapter1 as ch1  # noqa: E402
import dq4ch2event as ch2  # noqa: E402
import dq4ch3event as ch3  # noqa: E402
from dq4ch3slots import LOW_STUBS, STOCK_AT, STOCK_PER_SLOT  # noqa: E402
from dq4ch3slots import STOCK_SLOTS as _STOCK_SLOTS  # noqa: E402
from dq4chapterbox import ENTER, LEAVE  # noqa: E402

narrate = ch1.narrate
pages = ch2._speaker_pages

# 둘째 변수 칸 +0~+2 매상(3바이트), +3~+16 「보기」 동안 맡아 두는 톨네코 물건 12칸·장비 비트. 가게 물건은
# dq4ch3slots.STOCK_SLOTS(맡긴 동료 칸 다섯의 +1~+24, 물건 번호 + 1, 0 은 빈 칸)
SALES, SAVE, MARK, LINES, SPLIT = 0, 3, 17, 18, 19   # 둘째 변수 칸 오프셋: 매상 3바이트, 보기 동안 맡긴 톨네코 칸 14바이트, 보기 표지·쪽 줄 수·겹친 쪽 물건 수
ITEM_SLOTS = 12
VIEW_LINES = 8                                 # FC 보기 창 66 의 한 쪽 줄 수(15:$9F68)
VIEW_MORE = 7                                  # dq4windowname.NENE_VIEW_MORE 와 같아야 함(시험이 견줌)
# 보기 표지(dq4windowname.NENE_MARK, 보기 동안 VIEW_MORE·+1, 끝나면 0)와 쪽 줄 수(NENE_LINES, 창 높이). 매 프레임 모든 고르기
# 창에서 읽히므로 날 바뀜 루틴이 쓰는 TEMP 나 DQ5 사람 자리 표(7E:1BC5~1BFC, dq4ch3slots.DQ5_PEOPLE)에 두면 안 된다
VIEW_MARK = ch3.VARS2_AT + ch3.SLOTS['E'].vars2[0] + MARK & 0xFFFF    # = dq4ch3slots.NENE_VIEW_MARK
VIEW_COUNT = ch3.VARS2_AT + ch3.SLOTS['E'].vars2[0] + LINES & 0xFFFF   # = dq4ch3slots.NENE_VIEW_LINES
VIEW_SPLIT = ch3.VARS2_AT + ch3.SLOTS['E'].vars2[0] + SPLIT & 0xFFFF   # = dq4ch3slots.NENE_VIEW_SPLIT
STOCK_SLOTS = len(_STOCK_SLOTS) * STOCK_PER_SLOT
STOCK_END = STOCK_AT + 26 * len(_STOCK_SLOTS)        # 마지막 칸 다음 덩어리 건너뛰기 뒤의 주소
# FC 15:$9F9E 의 r < C0. DQ5 00:953A 는 (r × A) >> 8 이라 A = 4 로 받아 3 보다 작으면 같은 갈래가 된다
SELL_QUARTERS = 3
SELL_BASE, SELL_SPAN = 96, 33                  # 값 × (96 + ⌊r × 33/256⌋)/64
PRICE_BASE, PRICE_SCALE = 0x23B081, 0x23B159   # DQ5 물건 값(바이트 × 10^(배율 & 3)), dq5shop
RANDOM = 0x00953A
MESSAGE_AT = 0x248157                          # 보행 메시지(A16 = 번호), DQ5 가게 06:E018 이 부르는 것
SHOP_ENTER = 0x04D977
# BRK 처리기는 BRK 가 놓인 뱅크를 DB 로 두어(dq4ch2battle.common) 뱅크 4E 에서는 낮은 WRAM 대신 롬을 읽는다(실측: BRK 95 34 가
# 04:DADA 에서 DB = 4E 로 돎). 그래서 BRK 는 낮은 뱅크의 받침(BRK … / RTL)으로 부른다. 자리는 원래 롬 빈 자리
# (dq5build free, 29:FF80~FFFF) 앞쪽이고 dq4ch3slots.LOW_STUBS 가 E 몫으로 예약한다
BRKS = {
    'window': (0x95, 0x34), 'close': (0x95, 0x00), 'pick': (0x95, 0x37), 'ask': (0x95, 0x32),
    'count': (0x89, 0x80, 0x2F), 'item': (0x89, 0x80, 0x2E), 'drop': (0x89, 0x80, 0x32), 'sellable': (0x94, 0x06),
    'price': (0x94, 0x02), 'items': (0x95, 0x0F),
}
PICKER_RESET = 0x06DFB6                        # JSR DFBA / RTL: 창을 고르기 전에 DQ5 가게가 부르는 것
GOLD_AT = ch2.GOLD_AT
TEMP = 0x7E1BD6                                # 7E:1BBE~ 의 DQ5 가 쓰지 않는 자리(1장·용병 SCRATCH 가 1BD5 까지, 1BE0~ 이름 입력)
SHOP_KIND = 0x0F20                             # DQ5 가게 종류. 보기 동안 dq4windowname.NENE_VIEW_MORE(+1) 로 두어 창 37 을 네네 꼴로
PICK = TEMP + 6                                # 고른 빈 가게 칸 주소(2바이트) · 소지품 칸 · 물건 번호


def low_stubs(at):
    """(바이트, {이름: 주소}): BRKS 마다 BRK … / RTL."""
    out, where = bytearray(), {}
    for name, args in BRKS.items():
        where[name] = at + len(out)
        out += bytes((0x00, *args, 0x6B))
    return bytes(out), where


def _al(a):
    return bytes((a & 0xFF, a >> 8 & 0xFF, a >> 16))


def _asm():
    from dq4ch2endor import Asm
    return Asm()


def _w(v):
    return (v & 0xFFFF).to_bytes(2, 'little')


LONG = bytes((0x00, 0x00, 0x7E))                     # $7E0000,X(X16 = 가게 칸 주소 하위)


def stock_addr(k):
    """가게 칸 k(0~119)의 WRAM 주소."""
    return STOCK_AT + 26 * (k // STOCK_PER_SLOT) + k % STOCK_PER_SLOT


def _first(a):
    """X16·Y16: X = 첫 가게 칸 주소, Y = 그 덩어리에 남은 칸 수."""
    a(0xA2, *_w(STOCK_AT), 0xA0, STOCK_PER_SLOT, 0x00)


def _next(a, tag):
    """다음 가게 칸. 덩어리 끝이면 다음 칸의 +25·+0 을 건너뛴다(칸 +0 은 DQ5 의 찬 칸 표시라 쓰지 않음)."""
    from dq4ch2endor import BNE
    a(0xE8, 0x88).br(BNE, tag)(0xE8, 0xE8, 0xA0, STOCK_PER_SLOT, 0x00).label(tag)


def _day(vars2):
    """날이 바뀜(JSL, 아무 모드): 가게 칸마다 rand < C0 이면 값 × (96 + ⌊r × 33/256⌋)/64 를 매상에 더하고 칸을 비운 뒤,
    남은 물건을 앞으로 당긴다(FC 목록처럼 차례가 이어진다).
    셈 칸 TEMP 는 뱅크 00 거울(7E:0000~1FFF)이라 DB 0 에서 절대 주소로 쓴다."""
    from dq4ch2endor import BCC, BCS, BEQ, BNE, lda, sta
    p, acc, cnt = TEMP & 0xFFFF, (TEMP + 3) & 0xFFFF, (TEMP + 6) & 0xFFFF
    w = lambda op, addr: bytes((op, addr & 0xFF, addr >> 8))  # noqa: E731
    a = _asm()(ENTER, 0xE2, 0x20, 0xC2, 0x10)
    _first(a)
    a.label('slot')(0xBF, *LONG).br(BNE, 'item').brl('next').label('item')
    a(0xDA, 0x5A, 0x3A, 0x48, 0xA9, 4, 0x22, *_al(RANDOM), 0xC9, SELL_QUARTERS).br(BCC, 'sold')
    a(0x68, 0x7A, 0xFA).brl('next')
    # 값 p(3바이트) = 바이트 × 10^(배율 & 3). X = 물건 번호(16비트)
    a.label('sold')(0x68, 0xC2, 0x20, 0x29, 0xFF, 0x00, 0xAA, 0xE2, 0x20, 0xBF, *_al(PRICE_BASE), w(0x8D, p),
                    w(0x9C, p + 1), w(0x9C, p + 2))
    a(0xBF, *_al(PRICE_SCALE), 0x29, 0x03).br(BEQ, 'scaled')(w(0x8D, cnt))
    # p × 10 = 2p + 8p
    a.label('ten')(w(0x0E, p), w(0x2E, p + 1), w(0x2E, p + 2))                       # p = 2p
    a(w(0xAD, p), w(0x8D, acc), w(0xAD, p + 1), w(0x8D, acc + 1), w(0xAD, p + 2), w(0x8D, acc + 2))
    for _ in range(2):
        a(w(0x0E, acc), w(0x2E, acc + 1), w(0x2E, acc + 2))                         # acc = 8p
    a(0x18, w(0xAD, p), w(0x6D, acc), w(0x8D, p), w(0xAD, p + 1), w(0x6D, acc + 1), w(0x8D, p + 1))
    a(w(0xAD, p + 2), w(0x6D, acc + 2), w(0x8D, p + 2), w(0xCE, cnt)).br(BNE, 'ten')
    a.label('scaled')(0xA9, SELL_SPAN, 0x22, *_al(RANDOM), 0x18, 0x69, SELL_BASE, w(0x8D, cnt))
    a(w(0x9C, acc), w(0x9C, acc + 1), w(0x9C, acc + 2))
    a.label('mul')(0x18, w(0xAD, acc), w(0x6D, p), w(0x8D, acc), w(0xAD, acc + 1), w(0x6D, p + 1), w(0x8D, acc + 1))
    a(w(0xAD, acc + 2), w(0x6D, p + 2), w(0x8D, acc + 2), w(0xCE, cnt)).br(BNE, 'mul')
    for _ in range(6):                                                                 # ÷ 64
        a(w(0x4E, acc + 2), w(0x6E, acc + 1), w(0x6E, acc))
    a(0x18, lda(vars2 + SALES), w(0x6D, acc), sta(vars2 + SALES), lda(vars2 + SALES + 1), w(0x6D, acc + 1))
    a(sta(vars2 + SALES + 1), lda(vars2 + SALES + 2), w(0x6D, acc + 2), sta(vars2 + SALES + 2))
    a(0x7A, 0xFA, 0xA9, 0x00, 0x9F, *LONG)
    a.label('next')
    _next(a, 'turn')
    a(0xE0, *_w(STOCK_END)).br(BCS, 'pack').brl('slot')
    # FC 처럼 팔린 칸을 당긴다(15:$9F79 가 목록에서 빼면 뒤가 앞으로 옴): 비지 않은 칸을 차례대로 앞으로 옮기고 나머지를 비움
    wp, wc, val = TEMP & 0xFFFF, (TEMP + 2) & 0xFFFF, (TEMP + 4) & 0xFFFF
    a.label('pack')
    _first(a)
    a(0x8E, *_w(wp), 0x8C, *_w(wc))
    _first(a)
    a.label('move')(0xBF, *LONG).br(BEQ, 'hole')
    a(0x8D, *_w(val), 0xDA, 0x5A, 0xAE, *_w(wp), 0xAC, *_w(wc), 0xAD, *_w(val), 0x9F, *LONG)
    _next(a, 'wnext')
    a(0x8E, *_w(wp), 0x8C, *_w(wc), 0x7A, 0xFA)
    a.label('hole')
    _next(a, 'rnext')
    a(0xE0, *_w(STOCK_END)).br(BCC, 'move')
    a(0xAE, *_w(wp), 0xAC, *_w(wc))
    a.label('clear')(0xE0, *_w(STOCK_END)).br(BCS, 'end')(0xA9, 0x00, 0x9F, *LONG)
    _next(a, 'cnext')
    a.br(0x80, 'clear')
    a.label('end')
    return a.bytes() + LEAVE


def _pay(vars2):
    """대화 호출: 매상이 있으면 $F5~$F7 = 매상, 금화에 더하고 0 으로, 결과 flag 켬. 없으면 끔."""
    from dq4ch2endor import BEQ, lda, sta
    r = 0x7E2190 + ch3.RESULT[0]
    a = _asm()(ENTER, 0xE2, 0x20, lda(vars2 + SALES), 0x0F, *_al(vars2 + SALES + 1), 0x0F, *_al(vars2 + SALES + 2))
    a.br(BEQ, 'none')
    a(0x18, lda(vars2 + SALES), 0x85, 0xF5, 0x6F, *_al(GOLD_AT), sta(GOLD_AT))
    a(lda(vars2 + SALES + 1), 0x85, 0xF6, 0x6F, *_al(GOLD_AT + 1), sta(GOLD_AT + 1))
    a(lda(vars2 + SALES + 2), 0x85, 0xF7, 0x6F, *_al(GOLD_AT + 2), sta(GOLD_AT + 2))
    a(0xA9, 0x00, sta(vars2 + SALES), sta(vars2 + SALES + 1), sta(vars2 + SALES + 2))
    a(lda(r), 0x09, ch3.RESULT[1], sta(r)).br(0x80, 'end')
    a.label('none')(lda(r), 0x29, ~ch3.RESULT[1] & 0xFF, sta(r))
    a.label('end')
    return a.bytes() + LEAVE


def _room(vars2):
    """대화 호출: 가게 칸에 빈 칸이 있으면 결과 flag 켬."""
    from dq4ch2endor import BCC, BEQ, lda, sta
    r = 0x7E2190 + ch3.RESULT[0]
    a = _asm()(ENTER, 0xE2, 0x20, 0xC2, 0x10, lda(r), 0x29, ~ch3.RESULT[1] & 0xFF, sta(r))
    _first(a)
    a.label('scan')(0xBF, *LONG).br(BEQ, 'free')
    _next(a, 'turn')
    a(0xE0, *_w(STOCK_END)).br(BCC, 'scan').br(0x80, 'end')
    a.label('free')(lda(r), 0x09, ch3.RESULT[1], sta(r))
    a.label('end')
    return a.bytes() + LEAVE


def _counter(cell_y):
    """대화 호출: 주인공 셀 Y 가 cell_y 보다 작으면(카운터 바깥 위쪽에서 말을 걺) 결과 flag 켬."""
    from dq4ch2endor import BCS, lda, sta
    r = 0x7E2190 + ch3.RESULT[0]
    a = _asm()(ENTER, 0xE2, 0x20, lda(r), 0x29, ~ch3.RESULT[1] & 0xFF, sta(r))
    a(lda(0x7E3080), 0x29, 0x7F, 0xC9, cell_y).br(BCS, 'end')(lda(r), 0x09, ch3.RESULT[1], sta(r))
    a.label('end')
    return a.bytes() + LEAVE


def _show(a, msg):
    """메시지 하나(DQ5 가게처럼 끝 1001 이라 창에 이어 쌓인다). M·X 8 로 돌아온다."""
    a(0xC2, 0x30, 0xA9, msg & 0xFF, msg >> 8, 0x22, *_al(MESSAGE_AT), 0xE2, 0x30)


def _stock(vars2, m, brk):
    """대화 호출: FC 036E~0372 되풀이. 톨네코(일행 칸 0)의 물건을 DQ5 필드 도구 창(BRK 95 0F)으로 골라,
    팔 수 있으면(BRK 94 06, 06:DEF2) 값 × 1.5 를 안내하고 「예」 면 빈 가게 칸에 넣고 소지품에서 뺀다(BRK 89 80 32,
    06:DF3F). 고르기를 그만두거나 가게 칸이 다 차면 끝. 끝 무렵 칸이 찼으면 결과 flag 켬."""
    from dq4ch2endor import BCC, BEQ, BNE, lda, sta

    def j(name):
        return bytes((0x22, *_al(brk[name])))
    r = 0x7E2190 + ch3.RESULT[0]
    # DQ5 창 루틴은 일행 기록(7E:2040~)을 DB 로 읽으므로 DB = 7E 로 부른다(ENTER 는 DB = 0)
    a = _asm()(ENTER, 0xF4, 0x7E, 0x7E, 0xAB, 0xAB, 0xE2, 0x30, lda(r), 0x29, ~ch3.RESULT[1] & 0xFF, sta(r))
    # 대화에서 가게로 넘어갈 때와 같이(06:C26C 의 JSL 04:D977, 06:DC0B) 창 상태를 가게 쪽으로 바꾼다. 빼면 BRK 95 가 04:DADA 에서 돈다
    a(0x22, *_al(SHOP_ENTER), 0xE2, 0x30, j('close'))  # FC 네네 가게는 맡기기·보기 모두 골드 창이 없다(실측 화면)
    a.label('round')(0xC2, 0x10)
    _first(a)
    a.label('scan')(0xBF, *LONG).br(BEQ, 'free')
    _next(a, 'turn')
    a(0xE0, *_w(STOCK_END)).br(BCC, 'scan')
    a(0xE2, 0x10, lda(r), 0x09, ch3.RESULT[1], sta(r)).brl('end')
    a.label('free')(0x8E, *_w(PICK), 0xE2, 0x10)
    a(0x64, 0x42, j('count'), 0xA5, 0x46).br(BNE, 'has')
    _show(a, m['nene_nothing'])
    a.brl('end')
    a.label('has')
    _show(a, m['nene_pick'])
    a(0x22, *_al(PICKER_RESET), 0x64, 0xE4, j('items'), 0xA5, 0xE8).br(0x10, 'picked').brl('quit').label('picked')
    a(0x85, 0x43, 0x8D, *_w(PICK + 2), 0x64, 0x42, j('item'))
    a(0xA5, 0x46, 0x48, j('close'), 0x68, 0x8D, *_w(PICK + 3), 0x85, 0xF5)
    a(j('sellable')).br(0x90, 'sellable')
    _show(a, m['nene_precious'])
    a.brl('more')
    a.label('sellable')
    _show(a, m['nene_item'])
    # 값 × 1.5 → $F5~$F7(FC 15:$9F07 LDA #$60 / JSR A638 = × 60/40)
    a(0xAD, *_w(PICK + 3), 0x85, 0x42, j('price'))
    a(0xA5, 0x48, 0x4A, 0x85, 0xF7, 0xA5, 0x47, 0x6A, 0x85, 0xF6, 0xA5, 0x46, 0x6A, 0x18, 0x65, 0x46, 0x85, 0xF5)
    a(0xA5, 0xF6, 0x65, 0x47, 0x85, 0xF6, 0xA5, 0xF7, 0x65, 0x48, 0x85, 0xF7)
    _show(a, m['nene_offer'])
    a(j('ask'), 0xA5, 0xE8, 0x48, j('close'), 0x68).br(BEQ, 'put')
    _show(a, m['nene_keep'])
    a.brl('more')
    a.label('put')(0xC2, 0x10, 0xAE, *_w(PICK), 0xAD, *_w(PICK + 3), 0x1A, 0x9F, *LONG, 0xE2, 0x10)
    a(0x64, 0x42, 0xAD, *_w(PICK + 2), 0x85, 0x43)
    a(j('drop'))
    _show(a, m['nene_put'])
    a.label('more')
    _show(a, m['nene_more'])
    a(j('ask'), 0xA5, 0xE8, 0x48, j('close'), 0x68).br(BNE, 'end').brl('round')
    a.label('quit')(j('close'))
    a.label('end')
    return a.bytes() + LEAVE


def hooks(ctx):
    """[(자리, 원래 바이트, 새 바이트)]: 낮은 뱅크 BRK 받침."""
    code, _ = low_stubs(LOW_STUBS[0])
    if LOW_STUBS[0] + len(code) > LOW_STUBS[1]:
        raise SystemExit(f'네네 BRK 받침 {len(code)}바이트가 예약을 넘음')
    return [(LOW_STUBS[0], bytes(len(code)), code)]


def _view(vars2, brk):
    """대화 호출(FC 0374 「예」, 15:$9F55): 가게 칸이 비었으면 결과 flag 끔. 아니면 켜고, 톨네코 물건 12칸·장비 비트를
    둘째 변수 칸 SAVE~ 에 맡겨 두고, 비지 않은 가게 물건을 차례로 8개씩(FC 창 66 의 한 쪽) 톨네코 칸에 채워 창 37 을 쪽마다
    연다($E4 = 사람 0). 그동안 가게 종류 $0F20 을 VIEW_MORE(다음 쪽 있음)·+1(마지막 쪽)로 두면 dq4windowname 이 창 37 을
    FC 꼴(위 테두리 x 18 y 2, 그 쪽 줄 수 VIEW_COUNT 만큼의 높이, 커서 없음)로 열고 다음 쪽이 있을 때 위 테두리에 「→」 를
    깜박인다. FC 처럼 골드 창은 열지 않는다. A 로 다음 쪽(FC 15:$9F68 JSR $C8CC), B 로 그만둔다. 물건이 다하면 끝내고 톨네코
    칸·장비·$0F20 을 되돌린다. 가게 칸은 읽기만 한다."""
    from dq4ch2endor import BCC, BCS, BEQ, BNE, lda, sta

    def j(name):
        return bytes((0x22, *_al(brk[name])))
    r = 0x7E2190 + ch3.RESULT[0]
    items, equip = ch3.PARTY_ITEMS, ch3.PARTY_ITEMS - 2
    save = vars2 + SAVE
    it, itc, k = TEMP & 0xFFFF, (TEMP + 2) & 0xFFFF, (TEMP + 4) & 0xFFFF   # 가게 칸 주소·덩어리에 남은 수·쪽 안 차례
    pg = (TEMP + 5) & 0xFFFF                                                 # 보인 쪽 수

    a = _asm()(ENTER, 0xF4, 0x7E, 0x7E, 0xAB, 0xAB, 0xE2, 0x20, 0xC2, 0x10, lda(r), 0x29, ~ch3.RESULT[1] & 0xFF, sta(r))
    _first(a)
    a.label('scan')(0xBF, *LONG).br(BNE, 'some')
    _next(a, 'turn')
    a(0xE0, *_w(STOCK_END)).br(BCC, 'scan').brl('end')
    a.label('some')(0xE2, 0x10, lda(r), 0x09, ch3.RESULT[1], sta(r))
    a(0x22, *_al(SHOP_ENTER), 0xE2, 0x30, j('close'))
    for i in range(ITEM_SLOTS + 2):                       # 톨네코 물건 12칸 + 장비 2바이트
        src = items + i if i < ITEM_SLOTS else equip + i - ITEM_SLOTS
        a(lda(src), sta(save + i))
    a(0xAD, *_w(SHOP_KIND), 0x48)
    a(0xC2, 0x10)
    _first(a)
    a(0x8E, *_w(it), 0x8C, *_w(itc), 0x9C, *_w(pg))
    a.label('page')(0xE2, 0x30, 0x9C, *_w(k))
    a.label('fill')(0xC2, 0x10, 0xAE, *_w(it), 0xAC, *_w(itc))
    a.label('find')(0xE0, *_w(STOCK_END)).br(BCS, 'none')(0xBF, *LONG).br(BNE, 'got')
    _next(a, 'skip')
    a.br(0x80, 'find')
    a.label('got')(0x3A, 0x48)
    _next(a, 'past')
    a(0x68).br(0x80, 'keep')
    # 물건이 다했을 때: 첫 쪽이면 남은 줄을 비우고, 뒤 쪽이면 FC 15:$9F68 처럼 짧은 창을 앞 쪽 위에 겹친다(아래 short)
    a.label('none')(0xAD, *_w(pg)).br(BEQ, 'blank').brl('short')
    a.label('blank')(0xA9, 0xFF)
    a.label('keep')(0x8E, *_w(it), 0x8C, *_w(itc), 0xE2, 0x10, 0xAE, *_w(k), 0x9F, *_al(items), 0xE8, 0x8E, *_w(k))
    a(0xE0, VIEW_LINES).br(BCC, 'fill')
    a.label('pad')(0xA9, 0xFF, 0x9F, *_al(items), 0xE8, 0xE0, ITEM_SLOTS).br(BCC, 'pad')
    a(0xA2, 0x00)
    a.label('count')(0xBF, *_al(items), 0xC9, 0xFF).br(BEQ, 'counted')(0xE8, 0xE0, VIEW_LINES).br(BCC, 'count')
    # 표지·줄 수(7E:2824~)는 뱅크 00 거울(7E:0000~1FFF) 밖이고 BRK 받침을 지나면 DB 가 7E 가 아니므로 긴 주소로 쓴다
    a.label('counted')(0x8A, sta(0x7E0000 | VIEW_COUNT), 0xA9, 0x00, sta(0x7E0000 | VIEW_SPLIT)).brl('shown')
    # 겹친 쪽: 톨네코 칸 n 개 뒤에는 앞 쪽 물건이 남아 있다(FF 칸은 목록이 건너뛰어 줄이 당겨지므로 비우지 않음). 창은 8줄
    # 높이로 열고, n + 1 번째 줄 자리에 n 줄 창의 아래 테두리를 그린다(dq4windowname NeneArrow 가 그 줄 윗 타일 줄은 빈칸,
    # 아랫 줄은 테두리로 덮음). 한글 줄은 FC 보다 6점 위라 테두리를 한 줄 위로 올리면 n + 1 번째 줄 글자 윗점이 잘려, 그 줄은
    # 가린다(FC 는 그 줄도 보임). n = 0 이면 앞 쪽에서 물건이 끝난 것이라 끝낸다
    a.label('short')(0xE2, 0x30, 0xAE, *_w(k)).br(BNE, 'split').brl('done')
    a.label('split')(0x8A, sta(0x7E0000 | VIEW_SPLIT), 0xA9, VIEW_LINES, sta(0x7E0000 | VIEW_COUNT))
    a.label('shown')(lda(items), 0xC9, 0xFF).br(BEQ, 'done')
    # 다음 쪽이 있는지(남은 가게 칸에 물건이 있나)로 위 테두리 ▶ 를 정한다
    a(0xC2, 0x10, 0xAE, *_w(it), 0xAC, *_w(itc))
    a.label('peek')(0xE0, *_w(STOCK_END)).br(BCS, 'last')(0xBF, *LONG).br(BNE, 'more')
    _next(a, 'peeknext')
    a.br(0x80, 'peek')
    a.label('more')(0xA9, VIEW_MORE).br(0x80, 'kind')
    a.label('last')(0xA9, VIEW_MORE + 1)
    a.label('kind')(0xE2, 0x30, 0x8D, *_w(SHOP_KIND), sta(0x7E0000 | VIEW_MARK))
    a(0xA9, 0x00, sta(equip), sta(equip + 1))
    a(0x22, *_al(PICKER_RESET), 0x64, 0xE4, j('pick'), 0xA5, 0xE8, 0x48, j('close'), 0x68).br(0x30, 'done')
    a(0xEE, *_w(pg)).brl('page')
    a.label('done')(0xE2, 0x30)
    for i in range(ITEM_SLOTS + 2):
        dst = items + i if i < ITEM_SLOTS else equip + i - ITEM_SLOTS
        a(lda(save + i), sta(dst))
    a(0x68, 0x8D, *_w(SHOP_KIND), 0xA9, 0x00, sta(0x7E0000 | VIEW_MARK), sta(0x7E0000 | VIEW_SPLIT))
    a.label('end')
    return a.bytes() + LEAVE


def far_natives(ctx, put):
    """dq4ch3endor.far_native 에서 부른다. 날 바뀜 루틴을 맨 앞에 둔다(dq4ch3event.next_day 가 몫 첫 주소를 JSL)."""
    v = ctx.vars2_at
    m = ctx.msg or {k: 0 for k in MESSAGES}
    put('nene_day', _day(v))
    put('nene_pay', _pay(v))
    put('nene_room', _room(v))
    put('nene_counter', _counter(COUNTER_Y))
    put('nene_stock', _stock(v, m, low_stubs(LOW_STUBS[0])[1]))
    put('nene_view', _view(v, low_stubs(LOW_STUBS[0])[1]))


COUNTER_Y = 56                 # 40/00 네네(셀 (12,57)) 카운터 바깥 위쪽 줄은 셀 Y 53~54. 카운터 안쪽(네네 옆)은 57
CALLS = {'nene_pay': ('nene_pay', 0), 'nene_room': ('nene_room', 0), 'nene_counter': ('nene_counter', 0),
         'nene_stock': ('nene_stock', 0), 'nene_view': ('nene_view', 0)}


def _mark(codes):
    """① 숫자({1004}), ② 물건 이름({100A}). 둘 다 $F5 를 읽는다."""
    out = []
    for piece in codes:
        if not isinstance(piece, str):
            out.append(piece)
            continue
        for i, part in enumerate(piece.replace('②', '\0②\0').replace('①', '\0①\0').split('\0')):
            if part:
                out.append({'①': 0x1004, '②': 0x100A}.get(part, part))
    return out


MESSAGES = {
    'nene_counter_ask': pages('네네', '어서 와요, 여보./물건은 사들여/왔어요?'),                                   # 036B
    'nene_lonely': pages('네네', '그럼 거기 있지 말고/이리 와요./쓸쓸하잖아요…….'),                               # 036C
    'nene_sales': _mark(pages('네네', '그럼 물건을 맡기 전에/이거, 어제 매상이에요.')[:-1] + [ch1.PAGE] +
                        narrate('톨네코는 ①골드를/받았다!')),                                                    # 036D
    'nene_pick': pages('네네', '자, 어떤 걸/가게에 내놓을까요?'),                                                  # 036E
    'nene_item': _mark(pages('네네', '②/말이죠.')),                                                               # 036F
    'nene_offer': _mark(pages('네네', '이거라면 ①골드/넘게 팔아 볼게요!/그래도 돼요?')),
    'nene_put': pages('네네', '그럼 가게에/놓아 둘게요.'),                                                         # 0370
    'nene_more': pages('네네', '그 밖에 또/내놓을 거 있어요?'),                                                    # 0371
    'nene_keep': pages('네네', '어머, 팔기 싫어요?/그럼 당신이/갖고 있어요.'),                                     # 0372
    'nene_precious': pages('네네', '어머, 그건/팔아 버리기엔/아까운 것 같아요./당신이 갖고 있어요.'),              # 0373
    'nene_nothing': pages('네네', '어머? 오늘은/아무것도 안 가져온/것 같네.'),                                    # 0334
    'nene_done': pages('네네', '사들이기는/끝이네요. 지금/가게에 있는 물건/볼래요?'),                               # 0374
    'nene_cheer': pages('네네', '그럼 나 열심히/팔아 볼게요./당신도 힘내요. 쪽.'),                                # 0375
    'nene_full': pages('네네', '여보, 미안해요…….', '모처럼 사들여 왔는데/가게가 이미/가득 찼어요!',
                       '지금 가게에/있는 물건/볼래요?'),                                                              # 0377
    'nene_empty': pages('네네', '어머? 가게에/팔 물건이 없었어요!/빨리 사들여 와요.'),                               # 0376
}


def counter_talk(ctx, otherwise):
    """네네 낮 대화: 카운터 너머면 가게, 아니면 otherwise."""
    say_, call, when = ctx.say, ctx.call, ctx.when
    yes = {"code": "05"}
    # FC 15:$9F4B: 0374·0377 물음에 「예」 면 가게 물건이 있을 때 창 뒤 0375, 없으면 0376 만. 「아니요」 면 0375
    view = [when(yes, [call('nene_view'), when(ctx.paid(), [say_('nene_cheer')], [say_('nene_empty')])],
                 [say_('nene_cheer')])]
    stock = [call('nene_room'), when(ctx.paid(), [call('nene_stock'), when(ctx.paid(), [say_('nene_full')],
                                                                         [say_('nene_done')]), *view],
                                     [say_('nene_full'), *view])]
    shop = [say_('nene_counter_ask'), when(yes, [call('nene_pay'), when(ctx.paid(), [say_('nene_sales')]), *stock],
                                           [say_('nene_lonely')])]
    return [call('nene_counter'), when(ctx.paid(), shop, otherwise)]
