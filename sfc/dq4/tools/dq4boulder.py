"""3장 북쪽 동굴 FC 3D/04(SFC 3E/07)의 구르는 바위(dq4ch3safe 가 쓰는 네이티브).

FC(1D 이벤트 17·18, 1D:$9CB7~$9E7E): 왼쪽 통로 (03~04,0E)를 밟으면 (03,05)의 바위가 풀려 일행을 따라 구른다. 상태는
$62A3(X)·$62A0(Y, 바위 왼쪽 위 FC 칸)·$629A(아래 2비트 방향 0 멈춤·1 오른쪽·2 아래·3 왼쪽, bit5 막힘, bit6 반걸음, bit7
움직임). 한 차례(약 21프레임, 일행 걸음마다 또는 서 있을 때)마다:
  1. 막힘: 방향 앞 칸에 일행 누군가가 서 있으면(아래: X 가 바위 두 열 중 하나이고 Y = 바위 Y+2, 옆: Y 가 바위 두 줄
     중 하나이고 X = 바위 X+2 / X-1) bit5 를 켜고 끝.
  2. bit6 이 꺼진 차례: 왼쪽으로 X 03, 오른쪽으로 X 0B 에 닿으면 아래로. 아래로 Y ≥ 25 면 구덩이를 메우고 멈춤.
     bit6 이 켜진 차례: 한 칸 움직이고, 아래로 Y 13 이 되면 주인공 X ≥ 0B 이거나 05~0A·Y < 1E 일 때 오른쪽,
     Y 1E 가 되면 바위 X < 08 이면 주인공 X < 05 일 때 아래·아니면 오른쪽, X ≥ 08 이면 주인공 X ≥ 0B 일 때 아래·아니면 왼쪽.
  3. bit6 을 뒤집음.
맵에 다시 들어오면 바위는 (03,05), 구덩이는 열림. 실측은 fc/dq4/docs/dq4-chapter3-format.md 사건 5b.

SFC 에서 바위는 DQ5 바위 그림(4B) 인물 넷(FC 한 칸에 하나, 2×2)이고, 보이지 않는 인물의 스크립트가 매 프레임 ctl 을
불러 TICK 프레임마다 FC 와 같은 한 차례를 돈다. 움직이면 넷을 새 자리로 옮기고(셀 차지 비트를 지우고 다시 켬), 구덩이에
빠지면 넷을 치우고 구덩이 셀을 위 바닥 셀로 덮어 다시 그린 뒤, 영역 이동 훅(00:CE26)이 그 구덩이의 떨어짐을 끈다.
처음 풀릴 때 바위 아래의 막이 블록 (03~04,07~08)을 위 바닥 셀로 덮는다.
"""
from dq4chapterbox import ENTER, LEAVE

# FC 한 차례는 약 21프레임(실측: 일행이 서 있을 때 바위 한 칸이 42프레임). ctl 은 이동 간격 1 인물의 명령 05 라 8프레임에
# 한 번 불린다 → 세 번에 한 차례(실측: 바위가 막히지 않고 6칸 가는 데 275프레임, 한 칸 46프레임)
TICK = 3
ROCK_GFX = 0x4B                  # DQ5 바위 그림(10/00·31/07 의 미는 바위)
START = (0x03, 0x05)             # FC 바위 처음 자리(맵에 들 때 $62A3·$62A0)
TRIGGER = ((0x03, 0x04), 0x0E)   # FC 1D:$9CB7: X 03~04, Y 0E
GATE = (0x03, 0x07)              # 바위 아래 막이 블록(FC B0, 2×2 칸)
PITS = {0x03: 0x01, 0x0B: 0x02}  # 구덩이 X → 메움 비트. 구덩이는 FC (X~X+1, 25~26)
PIT_Y = 0x25
FALL_X = {0x01: 0x06, 0x02: 0x16}   # 메움 비트 → 그 구덩이 영역 이동 레코드의 x0(dq4groupbuild.fall_records)

# 인물 표(dq5-map-format 「인물 표」)와 엔진 루틴
SLOT_X, SLOT_X2, SLOT_Y, SLOT_Y2, SLOT_GFX = 0x3020, 0x30E0, 0x3080, 0x3140, 0x3220
SLOTS = 0x40                     # 훑을 인물 슬롯 수
FOLLOWERS = 0x1967               # 걷는 일행 그림 수(dq4ch1event 「따라 걷는 그림」)
CLEAR_CELLS = 0x00DEB5           # Y = 슬롯: 지금 자리의 셀 차지 비트를 지움
SET_CELLS = 0x00DF37             # Y = 슬롯: 지금 자리의 셀 차지 비트를 켬
CELL_AT = 0x25FA15               # X·Y 셀의 셀 버퍼 주소를 [$00] 에(dq4ch1event.CELL_AT)
REDRAW = (0x01ED56, 0x01EDF0)    # (X, Y) 부터 $1E82×$1E83 셀을 다시 그림(아래층·위층)
AREA_SITE, AREA_ORIG = 0x00CE26, bytes((0xA5, 0xC3, 0xD9, 0x04, 0x00, 0xD0, 0x07))  # LDA $C3 / CMP $0004,Y / BNE $CE34

# 변수 칸(dq4ch3slots S 의 +14~+20): 바위 X·Y·상태(FC $629A 꼴)·메움 비트·프레임 수·주인공 FC 칸 X·Y
BX, BY, ST, FILL, CNT, HX, HY = range(7)
VAR_NAMES = ('BX', 'BY', 'ST', 'FILL', 'CNT', 'HX', 'HY')


def _al(a):
    return bytes((a & 0xFF, a >> 8 & 0xFF, a >> 16))


def _asm():
    from dq4ch2endor import Asm
    return Asm()


class Vars:
    def __init__(self, at):
        self.at = at

    def __call__(self, k):
        return self.at + k


def model_tick(state, hero, members=None):
    """FC 한 차례의 파이썬 모형. state = (X, Y, $629A), hero = 주인공 FC 칸, members = 막힘을 볼 일행 칸(없으면 주인공).
    돌려주는 것 (X, Y, $629A). 구덩이를 메우면 방향 0·bit6 만 남음(FC 는 흔들기 뒤 40)."""
    x, y, f = state
    hx, hy = hero
    d = f & 3
    if d == 0:
        return state
    for mx, my in members or [hero]:
        if d == 2:
            blocked = mx in (x, x + 1) and my == y + 2
        elif d == 1:
            blocked = my in (y, y + 1) and mx == x + 2
        else:
            blocked = my in (y, y + 1) and mx == x - 1
        if blocked:
            return (x, y, f | 0x20)
    f = (f & ~0x20) | 0x80
    if not f & 0x40:
        if d == 3 and x == 0x03:
            d = 2
        elif d == 1 and x == 0x0B:
            d = 2
        elif d == 2 and y >= PIT_Y:
            return (x, y, 0x40)
    else:
        if d == 3:
            x -= 1
        elif d == 1:
            x += 1
        else:
            y += 1
            if y == 0x13 and (hx >= 0x0B or (hx >= 0x05 and hy < 0x1E)):
                d = 1
            elif y == 0x1E:
                d = (2 if hx < 0x05 else 1) if x < 0x08 else (2 if hx >= 0x0B else 3)
    return (x, y, ((f & ~3) | d) ^ 0x40)


def _fc_of(a, v, slot_x_reg=True):
    """M8·X8, X = 슬롯: 그 인물의 FC 칸을 HX·HY 에(셀 X >> 1, (셀 Y - 1) >> 1. 인물 표 bit7 은 방향이라 지움)."""
    from dq4ch2endor import lda, sta
    a(0xBF, _al(0x7E0000 | SLOT_X), 0x29, 0x7F, 0x4A, sta(v(HX)))
    a(0xBF, _al(0x7E0000 | SLOT_Y), 0x29, 0x7F, 0x3A, 0x4A, sta(v(HY)))
    del lda


def step(v):
    """JSR 로(M8·X8, DB 무관): FC 한 차례(model_tick 과 같음). 일행 슬롯 0~(걷는 그림 수 - 1, 1~4 로 자름)의 칸으로
    막힘을, 슬롯 0(주인공)으로 꺾기를 정한다."""
    from dq4ch2endor import BCC, BCS, BEQ, BNE, BRA, lda, sta
    a = _asm()
    st, bx, by, hx, hy = (v(k) for k in (ST, BX, BY, HX, HY))

    def set_dir(n):
        a(lda(st), 0x29, 0xFC, 0x09, n, sta(st))
    a.label('step')(lda(st), 0x29, 0x03).br(BNE, 'go')(0x60)
    # 막힘을 볼 일행 수 N(1~4)을 스택에
    a.label('go')(lda(0x7E0000 | FOLLOWERS)).br(BNE, 'n1')(0xA9, 0x01).label('n1')(0xC9, 0x05).br(BCC, 'n2')(0xA9, 0x04)
    a.label('n2')(0x48, 0xA2, 0x00)
    a.label('mem')
    _fc_of(a, v)
    a(lda(st), 0x29, 0x03, 0xC9, 0x02).br(BNE, 'side')
    a(lda(hy), 0x38, 0xEF, _al(by), 0xC9, 0x02).br(BNE, 'next')
    a(lda(hx), 0x38, 0xEF, _al(bx), 0xC9, 0x02).br(BCS, 'next').brl('blocked')
    a.label('side')(lda(hy), 0x38, 0xEF, _al(by), 0xC9, 0x02).br(BCS, 'next')
    a(lda(st), 0x29, 0x03, 0xC9, 0x01).br(BNE, 'left')
    a(lda(hx), 0x38, 0xEF, _al(bx), 0xC9, 0x02).br(BNE, 'next').brl('blocked')
    a.label('left')(lda(bx), 0x38, 0xEF, _al(hx), 0xC9, 0x01).br(BNE, 'next').brl('blocked')
    a.label('next')(0xE8, 0x8A, 0xC3, 0x01).br(BCC, 'mem')(0x68)
    a(lda(st), 0x29, 0xDF, 0x09, 0x80, sta(st), 0x29, 0x40).br(BNE, 'move')
    # bit6 꺼진 차례: 꺾기와 구덩이
    a(lda(st), 0x29, 0x03, 0xC9, 0x03).br(BNE, 't1')(lda(bx), 0xC9, 0x03).br(BNE, 'flip0')
    set_dir(2)
    a.label('flip0').brl('flip')
    a.label('t1')(0xC9, 0x01).br(BNE, 't2')(lda(bx), 0xC9, 0x0B).br(BNE, 'flip1')
    set_dir(2)
    a.label('flip1').brl('flip')
    a.label('t2')(lda(by), 0xC9, PIT_Y).br(BCC, 'flip2')(0xA9, 0x40, sta(st), 0x60)
    a.label('flip2').brl('flip')
    # bit6 켜진 차례: 한 칸
    a.label('move')(lda(st), 0x29, 0x03, 0xC9, 0x03).br(BNE, 'm1')(lda(bx), 0x3A, sta(bx)).brl('flip')
    a.label('m1')(0xC9, 0x01).br(BNE, 'm2')(lda(bx), 0x1A, sta(bx)).brl('flip')
    a.label('m2')(lda(by), 0x1A, sta(by), 0xA2, 0x00)
    _fc_of(a, v)
    a(lda(by), 0xC9, 0x13).br(BNE, 'r1e')
    a(lda(hx), 0xC9, 0x0B).br(BCS, 'right')(0xC9, 0x05).br(BCC, 'flip3')
    a(lda(hy), 0xC9, 0x1E).br(BCS, 'flip3')
    a.label('right')
    set_dir(1)
    a.label('flip3').brl('flip')
    a.label('r1e')(0xC9, 0x1E).br(BNE, 'flip4')
    a(lda(bx), 0xC9, 0x08).br(BCS, 'r1eb')
    a(lda(hx), 0xC9, 0x05).br(BCC, 'down').br(BRA, 'right')
    a.label('r1eb')(lda(hx), 0xC9, 0x0B).br(BCS, 'down')
    set_dir(3)
    a.label('flip4').br(BRA, 'flip')
    a.label('down')
    set_dir(2)
    a.label('flip')(lda(st), 0x49, 0x40, sta(st), 0x60)
    a.label('blocked')(0x68, lda(st), 0x09, 0x20, sta(st), 0x60)
    return a


def _rocks(a, v, body, label):
    """M8·X8 에서 바위 그림 인물 슬롯마다 body(a, k 레이블 없이, X = 슬롯, 스택 1,S = 몇째인지)를 돈다."""
    from dq4ch2endor import BCC, BEQ, BNE
    a(0xA9, 0x00, 0x48, 0xA2, 0x01)
    a.label(f'{label}_s')(0xBF, _al(0x7E0000 | SLOT_GFX), 0xC9, ROCK_GFX).br(BNE, f'{label}_n')
    a(0xBF, _al(0x7E0000 | SLOT_X), 0xC9, 0x80).br(BEQ, f'{label}_n')
    body(a)
    a(0xA3, 0x01, 0x1A, 0x83, 0x01)
    a.label(f'{label}_n')(0xE8, 0xE0, SLOTS).br(BCC, f'{label}_s')(0x68)


def _call_slot(addr):
    """X = 슬롯을 Y 로 넘겨 JSL(엔진 루틴이 X·Y 를 지킴)."""
    return bytes((0x9B, 0x22)) + _al(addr)


def place(v):
    """ENTER..LEAVE: 바위 인물 넷을 BX·BY 의 2×2 칸으로(차지 비트를 지우고 옮긴 뒤 다시 켬)."""
    from dq4ch2endor import lda
    import dq4ch1event as e
    a = _asm()(ENTER, 0xE2, 0x30, e.DP_SAVE)

    def body(a):
        a(_call_slot(CLEAR_CELLS))
        # 새 셀 X = BX×2 + (k & 1)×2, Y = BY×2 + 1 + (k >> 1)×2
        a(0xA3, 0x01, 0x29, 0x01, 0x0A, 0x85, 0x0E, lda(v(BX)), 0x0A, 0x18, 0x65, 0x0E)
        a(0x9F, _al(0x7E0000 | SLOT_X), 0x9F, _al(0x7E0000 | SLOT_X2))
        a(0xA3, 0x01, 0x29, 0x02, 0x85, 0x0E, lda(v(BY)), 0x0A, 0x1A, 0x18, 0x65, 0x0E)
        a(0x9F, _al(0x7E0000 | SLOT_Y), 0x9F, _al(0x7E0000 | SLOT_Y2))
        a(_call_slot(SET_CELLS))
    _rocks(a, v, body, 'pl')
    a(0xE2, 0x30, e.DP_RESTORE)
    return a.bytes() + LEAVE


def copy_block(v):
    """ENTER..LEAVE: FC 2×2 칸(셀 4×4)의 셀 +1~+7 을 네 줄 위 셀에서 덮고(+0 의 구역·차지 비트는 둠) 다시 그린다
    (dq4ch1event._open_cage 와 같은 꼴). 왼쪽 위 셀은 변수 HX·HY. 줄·열 수는 DP $0B·$0C(CELL_AT 은 $00~$02 만 씀)."""
    import dq4ch1event as e
    from dq4ch2endor import BCC, BNE, lda
    a = _asm()(ENTER, 0xE2, 0x30, e.DP_SAVE, 0x64, 0x0B)
    a.label('row')(0x64, 0x0C)
    a.label('col')(lda(v(HX)), 0x18, 0x65, 0x0C, 0xAA, lda(v(HY)), 0x18, 0x65, 0x0B, 0x38, 0xE9, 0x04, 0xA8)
    a(0x22, _al(CELL_AT), 0xA0, 0x07)
    a.label('get')(0xB7, 0x00, 0xBB, 0x9F, _al(e.SCRATCH), 0x88).br(BNE, 'get')
    a(lda(v(HX)), 0x18, 0x65, 0x0C, 0xAA, lda(v(HY)), 0x18, 0x65, 0x0B, 0xA8, 0x22, _al(CELL_AT), 0xA0, 0x07)
    a.label('put')(0xBB, 0xBF, _al(e.SCRATCH), 0x97, 0x00, 0x88).br(BNE, 'put')
    a(0xE6, 0x0C, 0xA5, 0x0C, 0xC9, 0x04).br(BCC, 'col')(0xE6, 0x0B, 0xA5, 0x0B, 0xC9, 0x04).br(BCC, 'row')
    a(0xA9, 0x04, 0x8D, 0x82, 0x1E, 0x8D, 0x83, 0x1E)
    for redraw in REDRAW:
        a(lda(v(HX)), 0xAA, lda(v(HY)), 0xA8, 0x22, _al(redraw))
    a(0xE2, 0x30, e.DP_RESTORE)
    return a.bytes() + LEAVE


def remove_rocks(v):
    """ENTER..LEAVE: 바위 인물 넷의 차지 비트를 지우고 자리를 80 으로(25:FB03 이 인물을 치우는 것과 같음)."""
    import dq4ch1event as e
    a = _asm()(ENTER, 0xE2, 0x30, e.DP_SAVE)

    def body(a):
        a(_call_slot(CLEAR_CELLS), 0xA9, 0x80)
        for t in (SLOT_X, SLOT_X2, SLOT_Y, SLOT_Y2):
            a(0x9F, _al(0x7E0000 | t))
    _rocks(a, v, body, 'rm')
    a(0xE2, 0x30, e.DP_RESTORE)
    return a.bytes() + LEAVE


def cell(x, y):
    """FC 칸 → 그 칸 왼쪽 위 셀."""
    return (2 * x, 2 * y)


def ctl(v, at):
    """인물 명령 05 가 매 프레임 부름(늘 A = 1 을 돌려 되풀이). TICK 프레임마다: 멈춰 있고 처음 자리면 주인공이 풀리는 칸에
    섰는지 보고 막이를 걷고 움직이기 시작, 움직이면 step 뒤 자리가 바뀌었으면 place, 구덩이에 닿았으면 바위를 치우고 그
    구덩이를 덮고 메움 비트."""
    from dq4ch2endor import BCC, BCS, BEQ, BNE, BRA, lda, sta
    a = _asm()(0x08, 0xE2, 0x30)
    a(lda(v(CNT)), 0x1A, sta(v(CNT)), 0xC9, TICK).br(BCS, 'tick').brl('out')
    a.label('tick')(0xA9, 0x00, sta(v(CNT)))
    a(lda(v(ST)), 0x29, 0x03).br(BNE, 'run')
    a(lda(v(BY)), 0xC9, START[1]).br(BNE, 'out1')(0xA2, 0x00)
    _fc_of(a, v)
    (xs, ty) = TRIGGER
    a(lda(v(HX)), 0xC9, xs[0]).br(BCC, 'out1')(0xC9, xs[1] + 1).br(BCS, 'out1')
    a(lda(v(HY)), 0xC9, ty).br(BNE, 'out1')
    gx, gy = cell(*GATE)
    a(0xA9, 0x82, sta(v(ST)), 0xA9, gx, sta(v(HX)), 0xA9, gy, sta(v(HY)), 0x22, _al(at['copy_block']))
    a.label('out1').brl('out')
    a.label('run')(lda(v(BX)), 0x48, lda(v(BY)), 0x48, 0x20, *(at['step'] & 0xFFFF).to_bytes(2, 'little'))
    a(0x68, 0xCF, _al(v(BY))).br(BNE, 'moved')(0x68, 0xCF, _al(v(BX))).br(BEQ, 'pit').br(BRA, 'go')
    a.label('moved')(0x68)
    a.label('go')(0x22, _al(at['place']))
    a.label('pit')(lda(v(ST)), 0x29, 0x03).br(BNE, 'out2')(lda(v(BY)), 0xC9, PIT_Y).br(BCS, 'fill')
    a.label('out2').brl('out')
    a.label('fill')
    # 구덩이 왼쪽 위 셀 (BX×2, PIT_Y×2)를 덮고, BX 가 왼쪽 구덩이면 메움 bit0, 아니면 bit1
    a(0x22, _al(at['remove_rocks']), lda(v(BX)), 0x0A, sta(v(HX)), 0xA9, 2 * PIT_Y, sta(v(HY)), 0x22, _al(at['copy_block']))
    a(lda(v(BX)), 0xC9, min(PITS) + 1, 0xA9, 0x01).br(BCC, 'mark')(0x0A)
    a.label('mark')(0x0F, _al(v(FILL)), sta(v(FILL)))
    a.label('out')(0xC2, 0x30, 0xA9, 0x01, 0x00, 0x28, 0x6B)
    return a.bytes()


def reset(v):
    """인물 명령 37(맵에 들 때 한 번): 바위 처음 자리·멈춤·메움 없음. 바위 인물은 목록대로 처음 자리에 서 있다."""
    from dq4ch2endor import sta
    a = _asm()(0x08, 0xE2, 0x30)
    for k, val in ((BX, START[0]), (BY, START[1]), (ST, 0), (FILL, 0), (CNT, 0)):
        a(0xA9, val, sta(v(k)))
    a(0x28, 0x6B)
    return a.bytes()


def area(v, group, number):
    """00:CE26 에서 JSL(M8, DB = 영역 이동 레코드 뱅크, Y = 레코드): 원래처럼 층($C3)이 레코드 +4 와 같은지 보고(Z = 1 이면
    옮김), 그룹·맵이 이 동굴이고 레코드 x0 가 메운 구덩이면 Z = 0 으로 떨어짐을 끈다."""
    from dq4ch2endor import BEQ, BNE, lda
    a = _asm()(0xA5, 0xC3, 0xD9, 0x04, 0x00).br(BNE, 'ret')
    a(0xA5, 0xBC, 0xC9, group).br(BNE, 'yes')(0xA5, 0xBD, 0xC9, number).br(BNE, 'yes')
    for bit, x0 in FALL_X.items():
        a(0xB9, 0x00, 0x00, 0xC9, x0).br(BNE, f'n{bit}')(lda(v(FILL)), 0x29, bit).br(BNE, 'skip').br(BEQ, 'yes')
        a.label(f'n{bit}')
    a.label('yes')(0xA9, 0x00, 0x6B)
    a.label('skip')(0xA9, 0x01)
    a.label('ret')(0x6B)
    return a.bytes()


def area_hook(at):
    return bytes((0x22, *_al(at['area']), 0xD0, 0x08, 0xEA))


def natives(v, base, group, number):
    """[(이름, 바이트)] 차례와 {이름: 주소}. base 부터 이어 둔다(ctl 이 앞 조각 주소를 쓰므로 둘째 바퀴에 맞춘다)."""
    def build(at):
        pieces = [('step', step(v).bytes()), ('place', place(v)), ('remove_rocks', remove_rocks(v)),
                  ('copy_block', copy_block(v)), ('reset', reset(v)), ('ctl', ctl(v, at)), ('area', area(v, group, number))]
        out, pos = {}, base
        for name, code in pieces:
            out[name] = pos
            pos += len(code)
        return pieces, out
    dummy = {k: base for k in ('step', 'place', 'remove_rocks', 'copy_block')}
    _, at = build(dummy)
    pieces, at2 = build(at)
    assert at == at2
    return pieces, at
