"""3장 은의 여신상 동굴(FC 그룹 40, SFC 48/02~07)의 배(dq4ch3safe 가 쓰는 네이티브).

FC: 겉모습 22 이고 $70E0 아래 비트 1 인 인물이 배다. 배 인물 칸으로 걸어 들어가면 타고($0515 = 1, 속성 83 물 칸을
다님), 땅 칸으로 걸으면 내리며 배는 마지막 물 칸에 남는다. 맵마다 슬롯 표가 다시 차므로 맵에 들면 배는 처음 자리다.
  40/00 (16,05): 단추 뒤($62AA bit5)에는 치움(1C:$A55B).
  40/04 (1D,1B): 섬 계단으로 들어오면(주인공 X 0E) (0E,09) 에 둠(1C:$A568).
  40/00 호수 아래 끝 x 18(줄 0E·0F)에 탄 채 들어서면 40/03 (07,y+10)의 물로 넘어감(탄 채).
실측은 fc/dq4/docs/dq4-chapter3-format.md 사건 16.

SFC: DQ5 실내 이동 판정은 셀 +1 의 층 비트와 주인공 층 마스크(7E:31A0)의 AND 다(00:AC4D). 이 동굴 맵들의 셀 +1 은
08·01·11 뿐이라 bit1(층 2)을 물 표시로 쓴다. 맵에 들면 주인공 마스크를 03 으로 두고, 내린 동안은 배가 선 FC 칸의 셀에만
bit1 을 켜 배 칸 밖의 물로는 못 들어가게 한다. 배 칸에 들어서면(주인공 셀에 bit1) 그 맵 FC 물 칸 전부에 켜고, 땅에
내리면 다 끈 뒤 배 칸에만 다시 켠다. 탄 동안 배 인물을 주인공 셀로 옮긴다(차지 비트 없음). 부리는 인물이 맵에 들 때
reset, 그 뒤 명령 05 로 ctl 을 되풀이한다(8프레임마다).
"""
from dq4chapterbox import ENTER, LEAVE

RAFT_GFX = 0xA1                       # dq4npcport 가 FC 배에 준 그림(DQ5 세트 55)
GROUP = 0x48
# {SFC 맵: (FC 맵, 배 처음 FC 칸 또는 None)}
MAPS = {0x02: (0x00, (0x16, 0x05)), 0x05: (0x03, None), 0x06: (0x04, (0x1D, 0x1B))}
ISLAND = (0x0E, (0x0E, 0x09))         # 40/04: 주인공 X 0E 로 들면 배를 이 칸에
# 40/03 에는 탄 채 넘어올 때만 (02,1A)의 배를 쓴다(FC $70E0 = 82 로 걸어서는 타지 못하는 배)
CROSS = {'map': 0x02, 'x': 0x18, 'rows': (0x0E, 0x0F), 'to': 0x05, 'to_x': 0x07, 'dy': 0x10, 'raft': (0x02, 0x1A)}
CELL_AT = 0x25FA15
CLEAR_CELLS = 0x00DEB5
SLOT_X, SLOT_X2, SLOT_Y, SLOT_Y2, SLOT_GFX = 0x7E3020, 0x7E30E0, 0x7E3080, 0x7E3140, 0x7E3220
HERO_MASK = 0x7E31A0
SLOTS = 0x20                           # 인물 표 한 칸의 슬롯 수(dq5npclists.SLOT_END)
WATER_BIT = 0x02
# 변수(var_at 부터): 배 FC X·Y, 배 인물 슬롯(FF 없음)
RX, RY, RS = range(3)


def _al(a):
    return bytes((a & 0xFF, a >> 8 & 0xFF, a >> 16))


def _asm():
    from dq4ch2endor import Asm
    return Asm()


def water_runs(prg, fc_map):
    """FC 그룹 40 맵의 속성 83(물) 칸을 줄마다 [(y, x0, x1)]."""
    import dq4block
    m = dq4block.Map(prg, 0x40, fc_map)
    out = []
    for y in range(m.h):
        x = 0
        while x < m.w:
            if m.blocks['prop'].get(m.buf[y * m.w + x] & 0x1F, 0) == 0x83:
                x0 = x
                while x + 1 < m.w and m.blocks['prop'].get(m.buf[y * m.w + x + 1] & 0x1F, 0) == 0x83:
                    x += 1
                out.append((y, x0, x))
            x += 1
    return out


def tables(prg):
    """{SFC 맵: 물 줄 바이트(y x0 x1 …, FF 로 끝)}."""
    return {k: b''.join(bytes(r) for r in water_runs(prg, fc)) + b'\xFF' for k, (fc, _) in MAPS.items()}


class Code:
    """flag(RIDING)·변수 주소와 단추 flag 를 받아 네이티브를 짠다."""

    def __init__(self, var_at, riding, button):
        self.var_at, self.riding, self.button = var_at, riding, button
        self.at, self.tbl = {}, 0

    def v(self, k):
        return self.var_at + k

    def flag_addr(self, f):
        return 0x7E2190 + f[0]

    def cellbits(self):
        """JSR 로 부름(M8·X8): DP $08 = FC X, $09 = FC Y, $0A = 0 이면 끄고 아니면 켬. 그 칸의 셀 2×2 의 +1 bit1."""
        from dq4ch2endor import BEQ
        a = _asm()
        for dy in (0, 1):
            for dx in (0, 1):
                a(0xA5, 0x08, 0x0A, 0x18, 0x69, dx, 0xAA, 0xA5, 0x09, 0x0A, 0x18, 0x69, dy, 0xA8, 0x22, _al(CELL_AT))
                a(0xA0, 0x01, 0xB7, 0x00, 0x29, ~WATER_BIT & 0xFF, 0xA6, 0x0A).br(BEQ, f'w{dy}{dx}')(0x09, WATER_BIT)
                a.label(f'w{dy}{dx}')(0x97, 0x00)
        a(0x60)
        return a

    def mark_all(self, at_cellbits, label):
        """M8·X16, DB 무관: 지금 맵($BD)의 물 표를 훑어 칸마다 cellbits($0A 그대로)."""
        from dq4ch2endor import BEQ, BRA
        a = _asm()
        a(0xC2, 0x10, 0xA2, 0x00, 0x00)
        # 맵 번호로 표 머리: 표는 [맵, 머리 lo, hi] … FF
        a.label(f'{label}_m')(0xBF, _al(self.tbl), 0xC9, 0xFF).br(BEQ, f'{label}_x')(0xC5, 0xBD).br(BEQ, f'{label}_f')
        a(0xE8, 0xE8, 0xE8).br(BRA, f'{label}_m')
        a.label(f'{label}_f')(0xC2, 0x20, 0xBF, _al(self.tbl + 1), 0xAA, 0xE2, 0x20)
        a.label(f'{label}_r')(0xBF, _al(self.tbl & 0xFF0000), 0xC9, 0xFF).br(BEQ, f'{label}_x')(0x85, 0x09)
        a(0xBF, _al((self.tbl & 0xFF0000) + 1), 0x85, 0x08, 0xBF, _al((self.tbl & 0xFF0000) + 2), 0x85, 0x0B)
        a(0xE8, 0xE8, 0xE8, 0xDA, 0xE2, 0x10)
        a.label(f'{label}_c')(0x20, *(at_cellbits & 0xFFFF).to_bytes(2, 'little'))
        a(0xA5, 0x08, 0xC5, 0x0B).br(BEQ, f'{label}_n')(0xE6, 0x08).br(BRA, f'{label}_c')
        a.label(f'{label}_n')(0xC2, 0x10, 0xFA).br(BRA, f'{label}_r')
        a.label(f'{label}_x')(0xE2, 0x10)
        return a

    def hero_fc(self, a):
        """M8·X8: 주인공 FC 칸을 DP $0C(X)·$0D(Y)에."""
        a(0xAF, _al(SLOT_X), 0x29, 0x7F, 0x4A, 0x85, 0x0C, 0xAF, _al(SLOT_Y), 0x29, 0x7F, 0x3A, 0x4A, 0x85, 0x0D)

    def move_raft(self, a, label):
        """M8·X8: 배 인물(슬롯 변수 RS)을 FC 칸 (RX, RY)의 셀로(차지 비트 없이 자리만)."""
        from dq4ch2endor import BEQ
        a(0xAF, _al(self.v(RS)), 0xC9, 0xFF).br(BEQ, label)(0xAA)
        a(0xAF, _al(self.v(RX)), 0x0A, 0x9F, _al(SLOT_X), 0x9F, _al(SLOT_X2))
        a(0xAF, _al(self.v(RY)), 0x0A, 0x1A, 0x9F, _al(SLOT_Y), 0x9F, _al(SLOT_Y2))
        a.label(label)

    def raft_cell(self, a, on):
        """M8·X8: 배 칸(RX, RY)의 셀 bit1 을 켜거나 끔(배가 없으면 아무것도)."""
        from dq4ch2endor import BEQ
        a(0xAF, _al(self.v(RS)), 0xC9, 0xFF).br(BEQ, f'rc{on}')
        a(0xAF, _al(self.v(RX)), 0x85, 0x08, 0xAF, _al(self.v(RY)), 0x85, 0x09, 0xA9, int(on), 0x85, 0x0A)
        a(0x20, *(self.at.get('cellbits', 0) & 0xFFFF).to_bytes(2, 'little')).label(f'rc{on}')

    def all_cells(self, a, on):
        """M8: 지금 맵 물 칸 모두의 bit1 을 켜거나 끔."""
        a(0xA9, int(on), 0x85, 0x0A, 0x20, *(self.at.get('mark_all', 0) & 0xFFFF).to_bytes(2, 'little'))

    def riding_test(self, a, branch, label):
        from dq4ch2endor import lda
        a(lda(self.flag_addr(self.riding)), 0x29, self.riding[1]).br(branch, label)

    def set_riding(self, a, on):
        from dq4ch2endor import lda, sta
        f = self.flag_addr(self.riding)
        a(lda(f), *((0x09, self.riding[1]) if on else (0x29, ~self.riding[1] & 0xFF)), sta(f))

    def find_slot(self, a, cell, label):
        """M8·X8: 배 그림 인물 가운데 셀 cell 에 선 슬롯(없으면 FF)을 RS 에."""
        from dq4ch2endor import BCC, BNE, sta
        x, y = cell
        a(0xA2, 0x01)
        a.label(f'{label}_s')(0xBF, _al(SLOT_GFX), 0xC9, RAFT_GFX).br(BNE, f'{label}_n')
        a(0xBF, _al(SLOT_X), 0x29, 0x7F, 0xC9, x).br(BNE, f'{label}_n')(0xBF, _al(SLOT_Y), 0x29, 0x7F, 0xC9, y)
        a.br(BNE, f'{label}_n')(0x8A, sta(self.v(RS))).brl(f'{label}_d')
        a.label(f'{label}_n')(0xE8, 0xE0, SLOTS).br(BCC, f'{label}_s')(0xA9, 0xFF, sta(self.v(RS)))
        a.label(f'{label}_d')


DP_SAVE = bytes((0xE2, 0x30, 0xA2, 0x0F, 0xB5, 0x00, 0x48, 0xCA, 0x10, 0xFA))
DP_RESTORE = bytes((0xE2, 0x30, 0xA2, 0x00, 0x68, 0x95, 0x00, 0xE8, 0xE0, 0x10, 0xD0, 0xF8))
# ENTER..LEAVE 꼴로 들어가 A = 1 을 돌려줌(인물 명령 05 가 다음 프레임에 다시 부름)
LEAVE_ONE = bytes((0xC2, 0x30, 0x7A, 0xFA, 0x68, 0xA9, 0x01, 0x00, 0x2B, 0xAB, 0x28, 0x6B))


def _in_map(a, label):
    """M8: 그룹 48·맵 02/05/06 이 아니면 label 로."""
    from dq4ch2endor import BEQ, BNE
    a(0xA5, 0xBC, 0xC9, GROUP).br(BEQ, f'{label}_g').brl(label).label(f'{label}_g')
    a(0xA5, 0xBD)
    for k in MAPS:
        a(0xC9, k).br(BEQ, f'{label}_ok{k}')
    a.brl(label)
    for k in MAPS:
        a.label(f'{label}_ok{k}')


def natives(code, base, tbls):
    """[(이름, 바이트)]·{이름: 주소}. code: Code(at 은 여기서 채움), base: 둘 자리, tbls: tables(prg).
    물 표는 맨 끝에 두어 코드 주소가 표 길이에 매이지 않는다(롬 없이 주소만 쓰는 단위 테스트)."""
    import dq4prologue
    from dq4ch2endor import BCC, BEQ, BNE, BRA, lda, sta

    def build(at):
        code.at = at
        code.tbl = at.get('tables', base)
        out, pos = [], base

        def put(name, b):
            nonlocal pos
            out.append((name, b))
            at2[name] = pos
            pos += len(b)
        at2 = {}
        put('cellbits', code.cellbits().bytes())
        a = code.mark_all(at.get('cellbits', base), 'ma')
        put('mark_all', a.bytes() + b'\x60')
        # 넘어가기 이벤트: 40/00 x 18 의 두 줄 → 40/03 (07, y+10)
        for row in CROSS['rows']:
            put(f'cross_ev{row:X}', bytes((0x90, GROUP, CROSS['to'], 2 * CROSS['to_x'], 2 * (row + CROSS['dy']) + 1,
                                           0x01, 0x80, 0xFF)))
        for row in CROSS['rows']:
            put(f'cross{row:X}', dq4prologue._event_start(at.get(f'cross_ev{row:X}', base)))
        # reset(명령 37): 마스크 03, 탄 채 40/03 에 들었으면 이어 타고, 아니면 맵별 배 처음 자리
        a = _asm()(ENTER, DP_SAVE)
        _in_map(a, 'r_out')
        a(0xA9, 0x03, 0x8F, _al(HERO_MASK))
        code.hero_fc(a)
        code.riding_test(a, BNE, 'r_rid')
        a.brl('r_walk')
        a.label('r_rid')
        a(0xA5, 0xBD, 0xC9, CROSS['to']).br(BEQ, 'r_cross')
        code.set_riding(a, False)
        a.brl('r_walk')
        a.label('r_cross')
        rx, ry = CROSS['raft']
        code.find_slot(a, (2 * rx, 2 * ry + 1), 'fa')
        a(lda(code.v(RS)), 0xC9, 0xFF).br(BEQ, 'r_fa')(0xAA, 0x9B, 0x22, _al(CLEAR_CELLS)).label('r_fa')
        a(0xA5, 0x0C, sta(code.v(RX)), 0xA5, 0x0D, sta(code.v(RY)))
        code.move_raft(a, 'mv1')
        code.all_cells(a, True)
        a.brl('r_out')
        a.label('r_walk')
        for k, (_, start) in MAPS.items():
            a(0xA5, 0xBD, 0xC9, k).br(BEQ, f'r_y{k}').brl(f'r_n{k}').label(f'r_y{k}')
            if start is None:
                a(0xA9, 0xFF, sta(code.v(RS))).brl('r_out')
            else:
                code.find_slot(a, (2 * start[0], 2 * start[1] + 1), f'f{k}')
                a(0xA9, start[0], sta(code.v(RX)), 0xA9, start[1], sta(code.v(RY)))
                if k == 0x02:
                    # 단추 뒤에는 배를 치움(FC 1C:$A55B)
                    a(lda(code.flag_addr(code.button)), 0x29, code.button[1]).br(BEQ, 'r_keep')
                    a(lda(code.v(RS)), 0xC9, 0xFF).br(BEQ, 'r_keep')(0xAA, 0x9B, 0x22, _al(CLEAR_CELLS), 0xA9, 0x80)
                    for t in (SLOT_X, SLOT_X2, SLOT_Y, SLOT_Y2):
                        a(0x9F, _al(t))
                    a(0xA9, 0xFF, sta(code.v(RS))).brl('r_out')
                    a.label('r_keep')
                if k == 0x06:
                    # 섬 계단으로 들면 배를 (0E,09)에(FC 1C:$A568)
                    a(0xA5, 0x0C, 0xC9, ISLAND[0]).br(BNE, 'r_isl')
                    a(0xA9, ISLAND[1][0], sta(code.v(RX)), 0xA9, ISLAND[1][1], sta(code.v(RY)))
                    a.label('r_isl')
                a.brl('r_place')
            a.label(f'r_n{k}')
        a.brl('r_out')
        a.label('r_place')(lda(code.v(RS)), 0xC9, 0xFF).br(BEQ, 'r_out2')(0xAA, 0x9B, 0x22, _al(CLEAR_CELLS))
        code.move_raft(a, 'mv2')
        code.raft_cell(a, True)
        a.label('r_out2')
        a.label('r_out')(DP_RESTORE)
        put('reset', a.bytes() + LEAVE)
        # ctl(명령 05): 탐·내림·따라옴·넘어가기
        a = _asm()(ENTER, DP_SAVE)
        _in_map(a, 'c_out')
        code.hero_fc(a)
        # 주인공 셀(X, Y)의 +1 bit1 = 물 표시가 켜진 칸
        a(0xAF, _al(SLOT_X), 0x29, 0x7F, 0xAA, 0xAF, _al(SLOT_Y), 0x29, 0x7F, 0xA8, 0x22, _al(CELL_AT))
        a(0xA0, 0x01, 0xB7, 0x00, 0x29, WATER_BIT, 0x85, 0x0E)
        code.riding_test(a, BNE, 'c_ride')
        # 내린 채: 물 표시 칸(= 배 칸)에 들어섰으면 탐
        a(0xA5, 0x0E).br(BEQ, 'c_out1')
        code.set_riding(a, True)
        code.all_cells(a, True)
        a.label('c_out1').brl('c_out')
        a.label('c_ride')(0xA5, 0x0E).br(BNE, 'c_water')
        # 땅: 내림. 물 표시를 다 끄고 배 칸만 다시 켬
        code.set_riding(a, False)
        code.all_cells(a, False)
        code.raft_cell(a, True)
        a.brl('c_out')
        a.label('c_water')(0xA5, 0x0C, sta(code.v(RX)), 0xA5, 0x0D, sta(code.v(RY)))
        code.move_raft(a, 'mv3')
        a(0xA5, 0xBD, 0xC9, CROSS['map']).br(BNE, 'c_out2')(0xA5, 0x0C, 0xC9, CROSS['x']).br(BNE, 'c_out2')
        for row in CROSS['rows']:
            a(0xA5, 0x0D, 0xC9, row).br(BNE, f'c_r{row:X}')(0x22, _al(at.get(f'cross{row:X}', base))).br(BRA, 'c_out2')
            a.label(f'c_r{row:X}')
        a.label('c_out2')
        a.label('c_out')(DP_RESTORE)
        put('ctl', a.bytes() + LEAVE_ONE)
        # 물 표 머리 [맵, 주소 lo, hi] … FF 와 줄 표
        heads, body, p = b'', b'', pos + 3 * len(tbls) + 1
        for k, t in tbls.items():
            heads += bytes((k, p & 0xFF, p >> 8 & 0xFF))
            body += t
            p += len(t)
        put('tables', heads + b'\xFF' + body)
        return out, at2

    out, at = build({})
    out, at2 = build(at)
    out, at3 = build(at2)
    assert at2 == at3
    return out, at3
