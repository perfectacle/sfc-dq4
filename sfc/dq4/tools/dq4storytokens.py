"""lua/dq4storywalk.lua 의 걷기 토막을 libretro 코어(dq4compatcheck.Walker)에서 돌리는 판. 토막의 뜻과 상수는 Lua
머리말이 정본이고, 이 파일은 같은 판정을 파이썬으로 옮긴 것이다(test_dq4story3check 가 토막 종류가 같은지 본다).

MesenCE 판과 다른 점: 실행 주소 훅이 없어 메시지 번호(msg:)·전투 시작(meet)·전투 끝(fight)을 쓰는 토막은 받지 않는다
(그런 구간은 호환성 걷기에서 건너뛴다, dq4story3compat).
"""
WINDOW, CURSOR, TICK, LOCK = 0x7E0A00, 0x7E0AD7, 0x7E007F, 0x7E19AE
W_COMMAND, W_MESSAGE, W_YESNO, W_STATUS, W_NONE = 0x01, 0x00, 0x32, 0x02, 0xFF
PASS = {0x02, 0x34, 0x35, 0x58}
STABLE, FREE, STUCK, TOKMAX = 8, 40, 900, 6000
FACE_STILL = 4
FACING = {'up': 0x80, 'down': 0x40, 'left': 0x20, 'right': 0x10}
# 코어에서 받지 않는 토막
HOOKED = ('msg', 'meet', 'fight')
KINDS = ('cell', 'dir', 'wait', 'face', 'talk', 'cmd', 'free', 'yes*', 'yes', 'no', 'serve', 'await', 'win', 'map',
         'field', 'pace', 'stand', 'rest', 'see', 'close', 'near', 'pick', 'push') + HOOKED


class Failed(Exception):
    pass


class Runner:
    """walker 는 rd(addr)·step(buttons) 를 가진 것(dq4compatcheck.Walker)."""

    def __init__(self, walker, tokmax=TOKMAX):
        self.w, self.tokmax = walker, tokmax
        self.win, self.since, self.tick, self.tick_since, self.free_for = None, 0, None, 0, 0
        self.log, self.n = [], 0
        self.held = None

    def rd(self, a):
        return self.w.rd(a)

    def rd16(self, a):
        return self.rd(a) | self.rd(a + 1) << 8

    def locked(self):
        return self.rd(LOCK) & 1 != 0

    def quiet(self):
        return self.win == W_NONE or (self.win == W_STATUS and not self.locked())

    def is_free(self):
        return self.quiet() and self.free_for >= FREE and not self.locked()

    def stable(self, w):
        return self.win == w and self.since >= STABLE

    def hero(self):
        if self.rd(0x7E00BE) & 0x80 == 0:
            return self.rd16(0x7E00B6), self.rd16(0x7E00B8)
        return self.rd(0x7E3020), self.rd(0x7E3080)

    def here(self):
        return self.rd(0x7E00BC) << 8 | self.rd(0x7E00BD) | (self.rd(0x7E00BE) & 0x80) << 16

    def person_at(self, cx, cy):
        """(cx, cy) 를 막고 선 인물 슬롯(없으면 None)."""
        hx, hy = self.rd(0x7E3020), self.rd(0x7E3080)
        # 걷는 줄(칸 0 ~ 7E:1967 - 1: 일행·따라 걷는 개)은 길을 막지 않는다(lua/dq4storywalk.lua personAt 과 같음)
        for k in range(max(1, self.rd(0x7E1967)), self.rd(0x7E1982)):
            px, py = self.rd(0x7E3020 + k), self.rd(0x7E3080 + k)
            if px == cx and abs(py - cy) <= 1 and (abs(px - hx) > 1 or abs(py - hy) > 1):
                return k
        return None

    def person_near(self, cx, cy, skip, r):
        """(cx, cy) 둘레 r칸 안에 선 사람(칸 skip 은 뺌)의 (칸, x, y), 없으면 None(lua personNear 와 같음)."""
        for k in range(max(1, self.rd(0x7E1967)), self.rd(0x7E1982)):
            qx, qy = self.rd(0x7E3020 + k), self.rd(0x7E3080 + k)
            if k != skip and abs(qx - cx) <= r and abs(qy - cy) <= r:
                return k, qx, qy
        return None

    def observe(self):
        w = self.rd(WINDOW)
        self.since = self.since + 1 if w == self.win else 0
        self.win = w
        t = self.rd(TICK)
        self.tick_since = self.tick_since + 1 if t == self.tick else 0
        self.tick = t
        calm = w == W_NONE or (w == W_STATUS and not self.locked())
        if calm and self.tick_since < 4:
            self.free_for += 1
        elif not calm or self.tick_since > 8:
            self.free_for = 0

    def note(self, text):
        self.log.append(f'f{self.n:05d} {text}')

    def run(self, toks, tokmax=None):
        """토막 열을 차례로. 실패하면 Failed(까닭)."""
        tokmax = tokmax or self.tokmax
        toks = [t for t in toks.split(';') if t]
        for i, tok in enumerate(toks):
            self.note(f'token {tok}')
            gen = self.token(tok, toks[i + 1] if i + 1 < len(toks) else '')
            t = 0
            for buttons in gen:
                t += 1
                if t > tokmax:
                    raise Failed(f'timeout {tok}')
                self.w.step(buttons)
                self.n += 1
                self.observe()

    def tap(self, t, b='a'):
        return {b} if t % 17 < 2 else set()

    def advance(self, t):
        if self.since >= 2 and (self.win == W_MESSAGE or (self.win in PASS and self.locked())):
            return self.tap(t)
        return set()

    def token(self, tok, nxt):
        """한 토막의 프레임마다 누를 버튼을 낸다(generator). 끝나면 return."""
        self.observe()
        if ',' in tok and tok.split(',')[0].isdigit():
            into = tok.endswith('!')
            yield from self.cell(*map(int, tok.rstrip('!').split(',')), nxt, into)
            return
        kind, _, arg = tok.partition(':')
        if kind in HOOKED:
            raise Failed(f'코어에서 받지 않는 토막 {tok}')
        if kind == 'wait':
            for _ in range(int(arg)):
                yield set()
            return
        if kind in ('up', 'down', 'left', 'right', 'a', 'b'):
            for _ in range(int(arg)):
                yield {kind}
            return
        if kind == 'face':
            yield from self._face(arg)
            return
        yield from getattr(self, '_' + kind.replace('*', '_all'))(arg)

    def _face(self, arg):
        """Lua face 와 같음: 주인공 셀이 FACE_STILL 프레임 그대로일 때 8프레임 누르고, 16프레임 뒤 방향이 맞지 않으면 세 번까지."""
        want = FACING.get(arg)
        for _ in range(3):
            at, still = None, 0
            while still < FACE_STILL:
                here = (self.rd(0x7E3020), self.rd(0x7E3080))
                still, at = (still + 1, at) if here == at else (0, here)
                yield set()
            for k in range(24):
                yield {arg} if k < 8 else set()
            if want is None or self.rd(0x7E31E0) & 0xF0 == want:
                return
        raise Failed(f'face {arg}: facing {self.rd(0x7E31E0):02X}')

    def cell(self, cx, cy, nxt, into=False):
        """(cx, cy) 까지 걷는다. 길을 막은 인물을 기다리는 동안은 구간의 난수 묶기(walker.pokes)를 풀어 둔다. 묶인
        난수로는 떠도는 인물이 같은 걸음만 골라 외길 칸에 끝없이 설 수 있다(레이크나바 소년, 코어마다 박자가 달라 선
        자리가 갈림). 실제 게임은 난수가 돌아 비키므로, 풀어 둔 채 기다린 뒤 비키면 다시 묶는다."""
        try:
            yield from self._cell(cx, cy, nxt, into)
        finally:
            self.hold_rng(True)

    def hold_rng(self, on):
        if on and self.held is not None:
            self.w.pokes, self.held = self.held, None
        elif not on and self.held is None and getattr(self.w, 'pokes', None):
            self.held, self.w.pokes = self.w.pokes, []

    def _cell(self, cx, cy, nxt, into):
        best, since, stuck, last, side, tries, prefer, waited = None, 0, 0, None, 0, 0, None, 0
        start_map = self.here()
        t = 0
        while True:
            t += 1
            x, y = self.hero()
            if (x, y) == (cx, cy):
                self.note(f'reached {x},{y}')
                return
            key = (x, y)
            if key == last and not self.locked():
                stuck += 1
            elif key != last:
                stuck = 0
            last = key
            dist = abs(cx - x) + abs(cy - y)
            if best is None or dist < best:
                best, since = dist, t
            blocker = None if into or dist > 2 else self.person_at(cx, cy)
            occupied = blocker is not None
            if waited > 300 and occupied and nxt[:1].isdigit() and ',' in nxt:
                self.note(f'skip {cx},{cy} (person {blocker:02X} at {self.rd(0x7E3020 + blocker)},'
                          f'{self.rd(0x7E3080 + blocker)} pic {self.rd(0x7E3220 + blocker):02X}) at {x},{y}')
                return
            self.hold_rng(not occupied)
            if occupied:
                waited, since, stuck = waited + 1, t, 0
            if waited > 3 * STUCK:
                raise Failed(f'person stays at {cx},{cy}')
            if t - since > STUCK and not self.locked():
                raise Failed(f'stuck at {x},{y} heading {cx},{cy}')
            if not self.quiet():
                if self.stable(W_YESNO):
                    self.note(f'question at {x},{y}')
                    return
                stuck = 0
                yield self.advance(t)
                continue
            if self.here() != start_map:
                self.note(f'left map at {x},{y}')
                return
            if side > 0:
                side -= 1
                yield {side_dir}
                continue
            if occupied:
                yield set()
                continue
            if stuck > 60 and not self.locked():
                tries += 1
                horiz = x != cx and (prefer != 'y' or y == cy)
                prefer = 'x' if horiz else 'y'
                side_dir = ('down' if tries % 2 else 'up') if horiz else ('right' if tries % 2 else 'left')
                side, stuck = 16, 0
                self.note(f'sidestep {side_dir} at {x},{y}')
                yield set()
                continue
            if prefer == 'y' and y != cy:
                yield {'down' if y < cy else 'up'}
            else:
                yield {'right' if x < cx else 'left' if x > cx else 'down' if y < cy else 'up'}

    def _talk(self, arg, keys=()):
        t = 0
        while not self.stable(W_COMMAND):
            t += 1
            yield self.tap(t)
        for k in keys:
            for j in range(31):
                if self.win != W_COMMAND:
                    raise Failed('command window closed')
                yield {k} if j < 6 else set()
        for _ in range(4):
            yield set()
        j = 0
        while self.win == W_COMMAND:
            j += 1
            yield {'a'} if j < 8 else set()

    def _cmd(self, arg):
        yield from self._talk('', [k for k in arg.split(',') if k])

    def _free(self, arg):
        t = 0
        while not self.is_free():
            t += 1
            if self.stable(W_YESNO):
                raise Failed('question while free')
            yield self.advance(t)

    def _yes_all(self, arg, cond=None):
        t, pressed = 0, None
        while True:
            t += 1
            if (cond() if cond else True) and self.is_free():
                return
            if self.stable(W_YESNO):
                pressed = t if pressed is None else pressed
                yield {'a'} if (t - pressed) % 24 < 4 else set()
            else:
                pressed = None
                yield self.advance(t)

    def _serve(self, arg):
        a, v = arg.split('>=')
        yield from self._yes_all('', lambda: self.rd16(0x7E0000 + int(a, 16)) >= int(v, 16))

    def _answer(self, no):
        t = 0
        while not self.stable(W_YESNO):
            t += 1
            yield self.advance(t)
        if no:
            cur, j = self.rd(CURSOR), 0
            while self.rd(CURSOR) == cur:
                j += 1
                if j > 60:
                    raise Failed('cursor stuck no')
                yield {'down'} if j <= 4 else set()
            for _ in range(8):
                yield set()
        k = 0
        while True:
            k += 1
            if self.win != W_YESNO and k > 4:
                return
            yield {'a'} if k % 24 < 4 else set()

    def _yes(self, arg):
        yield from self._answer(False)

    def _no(self, arg):
        yield from self._answer(True)

    def _await(self, arg):
        while self.quiet() and not self.locked():
            yield set()

    def _win(self, arg):
        want = {int(w, 16) for w in arg.split('/')}
        t = 0
        while True:
            t += 1
            if self.win in want:
                if self.since >= STABLE:
                    return
                yield set()
                continue
            yield self.tap(t) if self.since >= 2 else set()

    def _map(self, arg):
        g, k = (int(v, 16) for v in arg.split('/'))
        t = 0
        while not (self.rd(0x7E00BC) == g and self.rd(0x7E00BD) == k and self.rd(0x7E00BE) & 0x80 and self.is_free()):
            t += 1
            yield self.advance(t)

    def _field(self, arg):
        t = 0
        while not (self.rd(0x7E00BE) & 0x80 == 0 and self.is_free()):
            t += 1
            yield self.advance(t)

    def _pace(self, arg):
        cond, d1, d2 = arg.split(',')
        a, v = cond.split('>=')
        t = 0
        while self.rd16(0x7E0000 + int(a, 16)) < int(v, 16):
            t += 1
            b = self.advance(t)
            if self.quiet():
                b = {d1 if (t // 32) % 2 == 0 else d2}
            yield b

    def _stand(self, arg):
        s, x, y = arg.split(',')
        slot, at = int(s, 16), (int(x), int(y), 0)
        while (self.rd(0x7E3020 + slot), self.rd(0x7E3080 + slot), self.rd(0x7E3280 + slot) & 0x80) != at:
            yield set()

    def _rest(self, arg):
        a, n = arg.split(',')
        a, n = 0x7E0000 + int(a, 16), int(n)
        t, v, vt = 0, None, 0
        while True:
            cur = self.rd(a) << 8 | self.rd(a + 1)
            if cur != v:
                v, vt = cur, t
            if t - vt >= n:
                self.note(f'rest {cur:04X}')
                return
            t += 1
            yield self.advance(t)

    def _see(self, arg):
        a, v = arg.split('=')
        t = 0
        while self.rd(0x7E0000 + int(a, 16)) != int(v, 16):
            t += 1
            yield self.advance(t)

    def _close(self, arg):
        t = 0
        while not self.is_free():
            t += 1
            yield self.tap(t, 'b') if not self.quiet() and self.since >= 4 else set()

    def _pick(self, arg):
        a, v = (int(p, 16) for p in arg.split('='))
        a += 0x7E0000
        t, ok, cur, mark = 0, 0, None, 0
        while True:
            t += 1
            if self.rd(a) == v:
                ok += 1
                if ok > 8:
                    return
                yield set()
                continue
            ok = 0
            if self.rd(a) != cur:
                cur, mark = self.rd(a), t
                self.note(f'pick {cur:02X}')
            if t - mark > 200:
                raise Failed(f'pick stuck {self.rd(a):02X}')
            yield self.tap(t, 'down')

    def _near(self, arg):
        slot = int(arg, 16)
        last, stuck, face = None, 0, None
        t = 0
        while True:
            t += 1
            x, y = self.hero()
            nx, ny = self.rd(0x7E3020 + slot), self.rd(0x7E3080 + slot)
            dx, dy = nx - x, ny - y
            if (dy == 0 and abs(dx) == 2) or (dx == 0 and abs(dy) == 2):
                face = t if face is None else face
                if t - face >= 24:
                    return
                d = 'right' if dx > 0 else 'left' if dx < 0 else 'down' if dy > 0 else 'up'
                yield {d} if t - face < 8 else set()
                continue
            face = None
            stuck = stuck + 1 if (x, y) == last else 0
            last = (x, y)
            if stuck > STUCK:
                raise Failed(f'near {slot:02X} stuck at {x},{y} (person {nx},{ny})')
            if not self.quiet():
                yield set()
                continue
            tx = nx + (2 if x >= nx else -2)
            yield {('down' if y < ny else 'up')} if y != ny else {('right' if x < tx else 'left')}

    def _push(self, arg):
        try:
            yield from self._push_steps(arg)
        finally:
            self.hold_rng(True)

    def _push_steps(self, arg):
        s, gx, gy = arg.split(',')
        slot, gx, gy = int(s, 16), int(gx), int(gy)
        ok, last, stuck, tlast, since, flip, t, waited = 0, None, 0, None, 0, False, 0, 0
        while True:
            t += 1
            x, y = self.hero()
            tx, ty = self.rd(0x7E3020 + slot), self.rd(0x7E3080 + slot)
            if (tx, ty) == (gx, gy):
                ok += 1
                if ok > 30:
                    return
                yield set()
                continue
            ok = 0
            if not self.quiet():
                yield self.advance(t)
                continue
            horiz = tx != gx
            dx = (-1 if gx < tx else 1) if horiz else 0
            dy = 0 if horiz else (-1 if gy < ty else 1)
            px, py = tx - 2 * dx, ty - 2 * dy
            stuck = stuck + 1 if (x, y) == last else 0
            last = (x, y)
            if (tx, ty) != tlast:
                tlast, since = (tx, ty), t
            # 120 프레임 넘게 못 밀었고 미는 자리 P 둘레 2칸에 사람이 서면, 그 사람이 P 칸(±1)에서 비킬 때까지 난수 묶기를
            # 풀고 물러서서 기다린다(lua push 와 같음)
            near = self.person_near(px, py, slot, 1) if waited else \
                self.person_near(px, py, slot, 2) if t - since > 120 else None
            self.hold_rng(near is None)
            if near is None:
                waited = 0
            else:
                k, qx, qy = near
                waited, since = waited + 1, t
                if waited == 1:
                    self.note(f'push wait {k:02X} at {qx},{qy} (P {px},{py})')
                if waited > 3 * STUCK:
                    raise Failed(f'person stays near {px},{py}')
                ax, ay = x - qx, y - qy
                if abs(ax) + abs(ay) < 6:
                    yield {('down' if ay >= 0 else 'up') if abs(ay) >= abs(ax) else ('right' if ax >= 0 else 'left')}
                else:
                    yield set()
                continue
            if t - since > STUCK:
                raise Failed(f'push {slot:02X} stuck: person {tx},{ty} hero {x},{y} goal {gx},{gy}')
            if stuck > 60:
                flip, stuck = not flip, 0
            if (x, y) == (px, py):
                yield {'right' if dx > 0 else 'left' if dx < 0 else 'down' if dy > 0 else 'up'}
                continue
            sd = -2 if flip else 2
            cx, cy = (px, py + sd) if horiz else (px + sd, py)
            if not horiz and y == py:
                yield {'right' if x < px else 'left'}
            elif horiz and x == px:
                yield {'down' if y < py else 'up'}
            elif not horiz:
                yield {'right' if x < cx else 'left' if x > cx else 'down' if y < cy else 'up'}
            else:
                yield {'down' if y < cy else 'up' if y > cy else 'right' if x < cx else 'left'}
