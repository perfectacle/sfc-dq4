"""주인공이 선 자리 때문에 사건이 멈추거나 엉뚱한 칸에서 끝나지 않게 하는 규칙(롬 없이).

규칙은 sfc/dq4/docs/dq4-prologue-format.md 「주인공이 막는 사건」. 헤드리스 실측은 dq4heroblockcheck.py.
  1. 인물 스크립트의 걷기(13·14)는 주인공 통과(1C)를 켠 뒤에 한다. 조작을 막은 채 걷는 인물이 주인공에 막히면
     둘 다 움직일 수 없어 멈춘다. 예외는 WALK_EXEMPT 에 까닭과 함께 둔다.
  2. 이벤트 스크립트의 주인공 걸음(00~0F d n)은 주인공의 시작 칸에 기댄다. 네이티브가 거는 이벤트를 모두 찾아 걸음이
     있으면 MOVE_PINNED(시작 칸을 한 칸으로 못 박는 판정이 있는 이벤트)에 있어야 한다. 시작 칸이 여럿이면
     dq4prologue.hero_goto 로 그 자리에서 길을 만든다.
"""
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4ch1event as ev  # noqa: E402
import dq4ch2event as ch2  # noqa: E402
import dq4chapter1 as ch  # noqa: E402
import dq4prologue as pro  # noqa: E402

FIRST = 0xF00
# 1C 없이 걸어도 되는 인물 스크립트와 까닭
WALK_EXEMPT = {
    ch.WALK_OUT_LEFT: '1장 첫머리 전사: 왕이 조작을 푼 뒤 걷는다. 1C 를 켜자 주인공 옆 전사가 반 칸 어긋나 멈췄다',
    ch.WALK_OUT_RIGHT: '1장 첫머리 전사: 위와 같음',
    ev.OLD_MAN_SCRIPT: '성 앞 노인: 조작을 막지 않고 주인공 쪽으로 2셀 앞까지만 따라온다(_old_man_step)',
}
# 주인공 걸음이 있어도 되는 이벤트: (모듈, at 이름) → 시작 칸을 못 박는 판정
MOVE_PINNED = {
    ('ch1', 'ev_back'): '왕 앞 줄에 온 것은 walk_in(hero_goto)이 통로로 옮긴 뒤뿐이다',
    ('ch1', 'ev_out'): 'ev_back 뒤 줄 판정(lineup_row)에서만 건다',
    ('ch2', 'kick_walk'): 'at_wall 이 벽 앞 셀 (26,10) 에서 오른쪽을 볼 때만 묻는다',
}
# 이벤트 명령 길이(sfc/dq5/docs/dq5-event-format.md 「명령」). 00~0F 는 걸음 d n
EVENT_LEN = {0x10: 3, 0x20: 3, 0xB0: 3, 0x60: 3, 0x90: 7, 0xA0: 4, 0xC1: 2, 0xC2: 1, 0xC3: 4, 0xC4: 4, 0xC5: 4,
             0xC6: 1, 0xC7: 2, 0xC8: 2, 0xC9: 1, 0x91: 1, 0xFF: 1}
EVENT_START = re.compile(rb'\xA9(.)\x8D\xB3\x19\xA9(.)\x8D\xB4\x19\xA9(.)\x8D\xB5\x19', re.S)
# hero_goto 가 만든 길 끝의 C3(이어질 롬 이벤트): LDA #C3 / STA buf,X / INX, 이어 주소 세 바이트
_PUT = re.escape(bytes((0x9F, *pro.ROUTE_BUF.to_bytes(3, 'little'), 0xE8)))
GOTO_THEN = re.compile(rb'\xA9\xC3' + _PUT + rb'\xA9(.)' + _PUT + rb'\xA9(.)' + _PUT + rb'\xA9(.)' + _PUT, re.S)


def blocks():
    """(모듈 이름, 시작 주소, 코드, {이름: 주소}). 이벤트를 거는 네이티브 코드 묶음 전부."""
    out = []
    for name, (code, at), base in (('pro', pro.native(), pro.CODE_AT), ('ch1', ev.native(), ev.CODE_AT),
                                   ('ch2', ch2.native(), ch2.CODE_AT)):
        out.append((name, base, code, at))
    code, at = ch2.native()
    tail, tail_at = ch2.tail_native(FIRST)
    out.append(('ch2', ch2.CODE_AT + len(code), tail, tail_at))
    return out


def event_ops(code, start):
    """code 의 start 오프셋부터 FF 까지 이벤트 명령 (op, 인자)."""
    ops, pc = [], start
    while True:
        op = code[pc]
        n = 2 if op < 0x10 else EVENT_LEN[op]
        ops.append((op, code[pc + 1:pc + n]))
        if op == 0xFF:
            return ops
        pc += n


def run_goto(code, hero):
    """hero_goto 본문을 흉내 내 ROUTE_BUF 에 쓴 바이트를 돌려준다. 쓰는 명령만 안다(LEAVE 의 REP 에서 멈춤)."""
    pc, a, x, c, z, stack, buf = len(pro.box.ENTER), 0, 0, 0, 0, [], {}
    long_at = lambda p: code[p] | code[p + 1] << 8 | code[p + 2] << 16  # noqa: E731

    def rel(p):
        d = code[p]
        return d - 0x100 if d & 0x80 else d
    while True:
        op = code[pc]
        if op == 0xC2:
            return bytes(buf[k] for k in range(len(buf)))
        if op == 0xE2:
            pc += 2
        elif op in (0xA2, 0xA9):
            v = code[pc + 1]
            x, a = (v, a) if op == 0xA2 else (x, v)
            z = v == 0
            pc += 2
        elif op == 0x9F:
            assert long_at(pc + 1) == pro.ROUTE_BUF
            buf[x] = a
            pc += 4
        elif op == 0xE8:
            x += 1
            pc += 1
        elif op == 0xAF:
            a = hero[{0x7E3020: 0, 0x7E3080: 1}[long_at(pc + 1)]]
            pc += 4
        elif op == 0x29:
            a &= code[pc + 1]
            pc += 2
        elif op == 0x38:
            c = 1
            pc += 1
        elif op == 0xE9:
            r = a - code[pc + 1] - (1 - c)
            c, a = int(r >= 0), r & 0xFF
            z = a == 0
            pc += 2
        elif op in (0xF0, 0x90, 0xB0, 0x80):
            take = {0xF0: z, 0x90: not c, 0xB0: c, 0x80: True}[op]
            pc += 2 + (rel(pc + 1) if take else 0)
        elif op == 0x82:                                    # BRL
            pc += 3 + int.from_bytes(code[pc + 1:pc + 3], 'little', signed=True)
        elif op == 0xC9:
            c, z = int(a >= code[pc + 1]), a == code[pc + 1]
            pc += 2
        elif op == 0x48:
            stack.append(a)
            pc += 1
        elif op == 0x68:
            a = stack.pop()
            pc += 1
        elif op == 0x49:
            a ^= code[pc + 1]
            pc += 2
        elif op == 0x1A:
            a = (a + 1) & 0xFF
            pc += 1
        elif op in (0x8D, 0xAD, 0x09):
            pc += 3 if op != 0x09 else 2
        else:
            raise AssertionError(f'모르는 명령 {op:02X}')


def cell_box(cell):
    """인물 표 셀에 선 인물의 16×16 점 사각형."""
    return pro.walker_box([cell])


def boxes_meet(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def hero_frames(start, prefix, legs):
    """이벤트 걸음을 따라 프레임마다 주인공 점 자리(셀 하나 8점, 한 프레임 1점, C2 하나 8프레임)."""
    x, y = start[0] * 8, start[1] * 8
    out = [(x, y)] * (1 + 8 * len(prefix))
    for name, goal in legs:
        while (x if name == 'x' else y) != goal * 8:
            d = 1 if goal * 8 > (x if name == 'x' else y) else -1
            x, y = (x + d, y) if name == 'x' else (x, y + d)
            out.append((x, y))
    return out


class SpritesDoNotMeet(unittest.TestCase):
    """1C 는 멈춤을 막을 뿐 겹침은 막지 않는다. 걷는 인물과 주인공의 길·차례가 엇갈리지 않는지(점 단위로 셈)."""
    def test_supper_parents_and_hero_never_meet(self):
        father_way = pro.walker_box([pro.FATHER_CELL, pro.FATHER_SEAT_CELL])
        mx, my = next((x * 2, y * 2) for x, y, _, _, t in pro.VILLAGERS if t == pro.T_MOTHER)
        mother_cells = [(mx, my)] + [(x * 2, y * 2) for x, y in pro.MOTHER_PATH]
        mother_ways = [pro.walker_box(mother_cells[k:k + 2]) for k in range(len(mother_cells) - 1)]
        starts = ([(12, y) for y in (35, 36, 37)] + [(8, 36), (8, 37)] + [(10, 34), (11, 34)])
        for start in starts:
            prefix, legs, _ = pro.pick_route(pro.SUPPER_ROUTES, start)
            hero = hero_frames(start, prefix, legs)
            self.assertEqual(hero[-1], (pro.HERO_AT[0] * 8, pro.HERO_AT[1] * 8), start)
            for frame, (x, y) in enumerate(hero):
                for way in mother_ways:
                    self.assertFalse(boxes_meet((x, y, x + 16, y + 16), way), (start, frame))
            # 아버지는 주인공이 자기 길에서 벗어난 뒤(father_way) 인물 차례만큼 늦게 걷기 시작한다. 그 늦음이 한 걸음(8프레임)
            # 안이면 어느 값이어도 겹치지 않아야 한다
            clear = next(f for f, (x, y) in enumerate(hero + [hero[-1]] * 64)
                         if not boxes_meet((x, y, x + 16, y + 16), father_way))
            for lag in range(9):
                fx, fy = pro.FATHER_CELL[0] * 8, pro.FATHER_CELL[1] * 8
                for frame in range(len(hero) + 64):
                    hx, hy = hero[min(frame, len(hero) - 1)]
                    walked = max(0, frame - clear - lag)
                    y = max(pro.FATHER_SEAT_CELL[1] * 8, fy - walked)
                    self.assertFalse(boxes_meet((hx, hy, hx + 16, hy + 16), (fx, y, fx + 16, y + 16)),
                                     (start, lag, frame))

    def test_soldier_picks_the_way_off_the_hero(self):
        first = pro.walker_box([ev._npc(*ev.SOLDIER_FROM), ev.ch1_cell(*ev.SOLDIER_PATH[0])])
        rect = pro.hero_cells_in(first)
        sx, sy = ev._npc(*ev.SOLDIER_FROM)
        # 말을 거는 칸: 왼쪽(반 칸 포함)·오른쪽·아래·위
        for hero in [(sx - 2, sy - 1), (sx - 2, sy), (sx - 2, sy + 1), (sx + 2, sy), (sx, sy + 2), (sx, sy - 2)]:
            inside = rect[0] <= hero[0] <= rect[2] and rect[1] <= hero[1] <= rect[3]
            path = ev.SOLDIER_PATH_UP if inside else ev.SOLDIER_PATH
            cells = [(sx, sy)] + [ev.ch1_cell(x, y) for x, y in path]
            for k in range(len(cells) - 1):
                self.assertFalse(boxes_meet(cell_box(hero), pro.walker_box(cells[k:k + 2])), (hero, k))

    def test_king_walk_row_clears_guards_and_soldiers(self):
        row = ev._walk_legs()[0][1]
        self.assertEqual(row, ev.WALK_ROW)
        lineup_x = range(ev.LINEUP_X[0], ev.LINEUP_X[1] + 1)
        walk = pro.walker_box([(lineup_x[0], row), (lineup_x[-1], row)])
        standing = [(x * 2, y * 2) for (x, y), _ in ev.THRONE_GUARDS]
        standing += [(x * 2, y * 2) for (x, y), path, _ in ev.THRONE_SOLDIERS if not path]
        for cell in standing:
            self.assertFalse(boxes_meet(cell_box(cell), walk), cell)


class WalkersPassHero(unittest.TestCase):
    def test_scripted_walks_pass_the_hero(self):
        seen = set()
        for script in ch.npc_scripts(FIRST):
            if script['address'] in WALK_EXEMPT:
                seen.add(script['address'])
                continue
            through = False
            for k, c in enumerate(script['commands']):
                if c['op'] == '1C':
                    through = True
                elif c['op'] == '22':
                    through = False
                elif c['op'] in ('13', '14') and not through:
                    self.fail(f"{script['address']} 의 {k}번째 명령 {c['op']}: 1C 없이 걷는다")
        self.assertEqual(seen, set(WALK_EXEMPT), '예외 목록에 빌드에 없는 스크립트가 있음')

    def test_prologue_parents_and_messengers_pass(self):
        # 의자 칸에서 아버지에게 말을 걸면 아버지가 주인공에게 막혀 저녁이 멈췄다(실측)
        for address in (pro.FATHER_SCRIPT, pro.MOTHER_SCRIPT, pro.SHINSIA_SCRIPT):
            ops = [c['op'] for sc in pro.scripts() if sc['address'] == address for c in sc['commands']]
            self.assertLess(ops.index('1C'), ops.index('13'), address)


class HeroMovesArePinned(unittest.TestCase):
    def test_events_with_hero_steps_are_pinned(self):
        found = set()
        for name, base, code, at in blocks():
            names = {v: k for k, v in at.items()}
            # hero_goto 가 그 자리에서 만드는 길(HeroGoto)은 건너뛰고 그 뒤에 이어질 이벤트를 본다
            for m in [*EVENT_START.finditer(code), *GOTO_THEN.finditer(code)]:
                target = m[1][0] | m[2][0] << 8 | m[3][0] << 16
                if target == pro.ROUTE_BUF:
                    continue
                if not base <= target < base + len(code):
                    continue
                todo = [target]
                while todo:
                    t = todo.pop()
                    for op, args in event_ops(code, t - base):
                        if op == 0xC3:
                            todo.append(args[0] | args[1] << 8 | args[2] << 16)
                        if op < 0x10:
                            key = (name, names.get(t))
                            found.add(key)
                            self.assertIn(key, MOVE_PINNED, f'{key}: 주인공 걸음 {op:02X} {args.hex()} 가 시작 칸에 기댐')
        self.assertEqual(found, set(MOVE_PINNED), '걸음이 있다고 둔 이벤트가 바뀜')

    def test_supper_event_has_no_steps(self):
        code, at = pro.native()
        ops = event_ops(code, at['end_event'] - pro.CODE_AT)
        self.assertFalse([op for op, _ in ops if op < 0x10])


class HeroGoto(unittest.TestCase):
    def check(self, code, legs, then, prefix, starts):
        self.check_routes(code, [(None, prefix, legs)], then, starts)

    def check_routes(self, code, routes, then, starts):
        tail = bytes((0xFF,)) if then is None else bytes((0xC3, *then.to_bytes(3, 'little')))
        for start in starts:
            prefix, legs, suffix = pro.pick_route(routes, start)
            goal = {name: v for name, v in legs}
            wrote = run_goto(code, start)
            self.assertEqual(wrote, pro.route(start, legs, prefix) + suffix + tail, start)
            self.assertLessEqual(len(wrote), pro.ROUTE_MAX)
            # 걸음을 따라가면 목표 칸에 선다
            x, y = start
            steps = wrote[len(prefix):len(wrote) - len(suffix) - len(tail)]
            for d, n in zip(steps[::2], steps[1::2]):
                self.assertGreater(n, 0)
                x += {0x01: n, 0x02: -n}.get(d, 0)
                y += {0x04: n, 0x08: -n}.get(d, 0)
            self.assertEqual((x, y), (goal.get('x', start[0]), goal.get('y', start[1])), start)

    def body(self, code, base, addr):
        out = code[addr - base:]
        return out[:out.index(pro.box.LEAVE) + len(pro.box.LEAVE)]

    def test_supper_walk_reaches_the_table_from_any_side(self):
        code, at = pro.native()
        walk = self.body(code, pro.CODE_AT, at['hero_walk'])
        starts = [(x, y) for x in range(4, 16) for y in range(30, 40)]
        self.check_routes(walk, pro.SUPPER_ROUTES, None, starts)
        self.assertEqual(dict(pro.HERO_LEGS), {'x': pro.HERO_AT[0], 'y': pro.HERO_AT[1]})

    def test_shinsia_aside_leaves_her_way(self):
        code, at = pro.native()
        aside = self.body(code, pro.CODE_AT, at['shinsia_aside'])
        way = pro.walker_box(pro.SHINSIA_WAY_CELLS)
        routes = pro.step_aside(way, (('y', way[3] // 8),), bytes((0xA0, *at['hero_up'].to_bytes(3, 'little'))))
        starts = [(x, y) for x in range(2, 12) for y in range(24, 34)]
        self.check_routes(aside, routes, None, starts)
        for start in starts:
            _, legs, _ = pro.pick_route(routes, start)
            end = (dict(legs).get('x', start[0]), dict(legs).get('y', start[1]))
            self.assertFalse(boxes_meet(cell_box(end), way), start)

    def test_king_walk_goes_along_the_line_first(self):
        code, at = ev.native()
        walk = self.body(code, ev.CODE_AT, at['walk_in'])
        starts = [(x, y) for x in range(ev.LINEUP_X[0], ev.LINEUP_X[1] + 1)
                  for y in range(ev.LINEUP_Y[0], ev.LINEUP_Y[1] + 1)]
        self.check(walk, ev._walk_legs(), at['ev_stop'], bytes((0xC2,)) * ev.LINEUP_WAIT, starts)
        # 줄 바로 위(셀 50)로 세로 → 통로로 가로 → 왕 앞 줄로 세로. 옆으로 가는 줄에는 벽이 없고 문지기·병사와 16점 떨어진다
        self.assertEqual(ev._walk_legs(), (('y', ev.ch1_cell(0, ev.LINEUP_ROW)[1] - 1), ('x', ev.AISLE_X),
                                          ('y', ev.ch1_cell(0, ev.KING_ROW)[1])))

    def test_lineup_is_only_the_open_part(self):
        # 줄 판정은 옆으로 막힘 없이 통로에 닿는 X 만. 벽 너머 칸에서 걸리면 이벤트 걸음이 벽에 막혀 멈춘다
        code, at = ev.native()
        inside = code[at['lineup_row'] - ev.CODE_AT:][:len(pro._inside(0, 0, 0, 0))]
        self.assertEqual(inside, pro._inside(ev.LINEUP_X[0], ev.LINEUP_Y[0], ev.LINEUP_X[1], ev.LINEUP_Y[1]))
        self.assertLessEqual(ev.LINEUP_X[0], ev.AISLE_X)
        self.assertGreaterEqual(ev.LINEUP_X[1], ev.AISLE_X)

    def test_route_counts_later_legs_from_the_previous_goal(self):
        legs = (('y', 51), ('x', 32), ('y', 43))
        self.assertEqual(pro.route((24, 53), legs), bytes((0x08, 2, 0x01, 8, 0x08, 8)))
        self.assertEqual(pro.route((32, 51), legs), bytes((0x08, 8)))


if __name__ == '__main__':
    unittest.main()
