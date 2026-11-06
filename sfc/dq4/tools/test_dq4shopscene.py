"""롬 없이: 가게 장면 검사의 입력 열(창 따라가기·커서 옮기기·누르지 않고 기다리기)과 판정, 장면 표.
롬이 있으면: 장면이 서는 카운터 앞 칸을 FC 맵에서 걸어 갈 수 있는지."""
import sys
import unittest
from pathlib import Path

import dq4shopscene as ss


class FakeGame:
    """누름(눌린 첫 프레임)마다 delay 프레임 뒤 다음 창으로 넘어가는 가짜 게임. flicker 는 {프레임: 창} 으로 잠깐
    바뀌는 창, after 는 {프레임: 창} 으로 누르지 않아도 그 프레임부터 바뀌는 창."""

    def __init__(self, windows, button='a', delay=3, flicker=None, after=None, mem=None):
        self.windows, self.button, self.delay = list(windows), button, delay
        self.k, self.n, self.prev, self.pending = 0, 0, False, None
        self.flicker, self.after = flicker or {}, after or {}
        self.mem = dict(mem or {})
        self.presses = []

    def step(self, buttons):
        self.n += 1
        down = self.button in buttons
        if down:
            self.presses.append(self.n)
        if down and not self.prev and self.pending is None and self.k + 1 < len(self.windows):
            self.pending = self.n + self.delay
        self.prev = down
        if self.pending is not None and self.n >= self.pending:
            self.k, self.pending = self.k + 1, None
        for f, w in self.after.items():
            if self.n == f:
                self.windows[self.k] = w

    def rd(self, addr):
        if addr == ss.WINDOW:
            return self.flicker.get(self.n, self.windows[self.k])
        return self.mem.get(addr, 0)


def driver(game):
    d = ss.Driver(game.step, game.rd, lambda: game.n)
    d.idle(ss.STABLE)
    return d


class ToTest(unittest.TestCase):
    def test_releases_on_the_frame_the_target_appears(self):
        game = FakeGame([0xFF, 0x00, 0x33, 0x39])
        d = driver(game)
        d.to('a', (0x33,))
        self.assertEqual(d.window, 0x33)
        # 33 이 뜬 뒤로는 누르지 않아 사기 목록(39)으로 넘어가지 않는다
        self.assertEqual(game.windows[game.k], 0x33)
        self.assertEqual(d.path, [0xFF, 0x00, 0x33])

    def test_unexpected_window_fails(self):
        game = FakeGame([0x37, 0x00, 0x32, 0x33])
        d = driver(game)
        with self.assertRaisesRegex(ss.Fail, '32 창에 섬'):
            d.to('a', (0x33,))

    def test_short_flicker_is_not_a_window(self):
        game = FakeGame([0xFF, 0x33], flicker={f: 0x3A for f in range(10, 10 + ss.STABLE - 1)})
        d = driver(game)
        d.to('a', (0x33,))
        self.assertNotIn(0x3A, d.path)

    def test_times_out(self):
        game = FakeGame([0xFF])
        d = driver(game)
        with self.assertRaisesRegex(ss.Fail, f'{ss.STEP_LIMIT} 프레임'):
            d.to('a', (0x33,))

    def test_tap_period_walks_every_phase_of_eight(self):
        # 필드는 8프레임에 한 번 A 를 받는다: 누르는 프레임이 8 의 나머지를 모두 지나야 한다
        period = sum(ss.TAP)
        self.assertNotEqual(period % 8, 0)
        phases = {(k * period + h) % 8 for k in range(8) for h in range(ss.TAP[0])}
        self.assertEqual(phases, set(range(8)))


class StepsTest(unittest.TestCase):
    def test_pick_moves_until_value(self):
        game = FakeGame([0x37], button='down')
        cursor = iter([0, 0, 1, 1, 2])
        d = driver(game)
        values = []

        def rd(addr):
            if addr == ss.CURSOR:
                values.append(next(cursor, 2))
                return values[-1]
            return game.rd(addr)
        d.rd = rd
        d.pick(ss.CURSOR, 2, 'down')
        self.assertEqual(values[-1], 2)

    def test_pick_gives_up(self):
        d = driver(FakeGame([0x37]))
        with self.assertRaisesRegex(ss.Fail, '0AD7 가 02'):
            d.pick(ss.CURSOR, 2, 'down')

    def test_wait_and_stays(self):
        game = FakeGame([0x00], after={60: 0x32})
        d = driver(game)
        d.run([ss.wait(0x32, 100)], None)
        self.assertEqual(d.window, 0x32)
        still = driver(FakeGame([0x00]))
        still.run([ss.stays(50)], None)
        moving = driver(FakeGame([0x00], after={30: 0x32}))
        with self.assertRaisesRegex(ss.Fail, '00 창이 32'):
            moving.run([ss.stays(50)], None)
        late = driver(FakeGame([0x00], after={500: 0x32}))
        with self.assertRaisesRegex(ss.Fail, '32 창이 되지 않음'):
            late.run([ss.wait(0x32, 100)], None)

    def test_see_and_poke(self):
        d = driver(FakeGame([0x5C], mem={ss.DIGIT: 0x05}))
        d.run([ss.see(ss.DIGIT, 0x05)], None)
        with self.assertRaisesRegex(ss.Fail, '0B02 = 05'):
            d.run([ss.see(ss.DIGIT, 0x03)], None)
        poked = []
        d.run([ss.poke(ss.QTY, 3)], lambda a, v: poked.append((a, v)))
        self.assertEqual(poked, [(ss.QTY, 3)])


def memory(gold, held, equip, kind=0, extra=None):
    m = {ss.GOLD: gold & 255, ss.GOLD + 1: gold >> 8 & 255, ss.GOLD + 2: gold >> 16,
         ss.EQUIP: equip & 255, ss.EQUIP + 1: equip >> 8, ss.SHOP_KIND: kind}
    for k in range(12):
        m[ss.ITEMS + k] = held[k] if k < len(held) else 0xFF
    m.update(extra or {})
    return lambda a: m.get(a, 0)


class JudgeTest(unittest.TestCase):
    def scene(self, **kw):
        base = dict(name='t', title='t', shop='item', sets=(), steps=(), gold=976, items=(0x42, 0x00, 0xA1),
                    equip=0x0003, windows=(0x01, 0x33, 0x3A, 0x32, 0x33))
        base.update(kw)
        return ss.Scene(**base)

    def judge(self, scene, rd, path=(0xFF, 0x02, 0x01, 0x00, 0x33, 0x3A, 0x35, 0x00, 0x32, 0x58, 0x33), window=0x33):
        return ss.judge(scene, ss.observed(rd), list(path), window, rd)

    def test_observed(self):
        seen = ss.observed(memory(0x012345, (0x42, 0x00, 0xA1), 0x0003, 1))
        self.assertEqual(seen['gold'], 0x012345)
        self.assertEqual(seen['items'], (0x42, 0x00, 0xA1))
        self.assertEqual(seen['equip'], 0x0003)
        self.assertEqual(seen['kind'], 1)

    def test_pass(self):
        self.assertEqual(self.judge(self.scene(), memory(976, (0x42, 0x00, 0xA1), 0x0003)), [])

    def test_each_value(self):
        problems = self.judge(self.scene(wram={ss.QTY_MAX: 0}),
                              memory(1000, (0x42, 0x00), 0x0001, 1, {ss.QTY_MAX: 3}), path=(0x01, 0x33, 0x39), window=0x39)
        text = '\n'.join(problems)
        for word in ('가게 종류 1', '금화 1000', '물건 42 00(', '장비 비트 0001', '끝 창 39', '0F2C = 03', '창 차례'):
            self.assertIn(word, text)

    def test_window_order_ignores_pass_windows_only(self):
        rd = memory(976, (0x42, 0x00, 0xA1), 0x0003)
        scene = self.scene()
        # 지나가도 되는 창(00·02·35·58·FF)만 다르면 같다
        self.assertEqual(self.judge(scene, rd, path=(0x02, 0x01, 0x33, 0x00, 0x3A, 0x00, 0x32, 0x00, 0x33)), [])
        # 개수 창을 더 지남, 가게 창을 건너뜀, 순서가 바뀜
        for path in ((0x01, 0x33, 0x3A, 0x5C, 0x32, 0x33), (0x01, 0x3A, 0x32, 0x33), (0x01, 0x33, 0x32, 0x3A, 0x33)):
            self.assertIn('창 차례', '\n'.join(self.judge(scene, rd, path=path)), path)


class ScenesTest(unittest.TestCase):
    def test_table(self):
        names = [s.name for s in ss.SCENES]
        self.assertEqual(len(names), len(set(names)))
        for s in ss.SCENES:
            self.assertIn(s.shop, ss.SHOPS)
            self.assertEqual(s.steps[:len(ss.OPEN)], ss.OPEN, s.name)
            self.assertLessEqual(len(s.items), 12)
            self.assertEqual(s.windows[:2], (ss.W_COMMAND, ss.W_SHOP), s.name)
            self.assertFalse(set(s.windows) & ss.PASS, s.name)
            for k, v in s.sets:
                if k == 'items':
                    self.assertLessEqual(len(v.split(',')), 12)

    def test_by_name(self):
        self.assertEqual([s.name for s in ss.by_name(['buy-one', 'sell-one'])], ['buy-one', 'sell-one'])
        with self.assertRaises(SystemExit):
            ss.by_name(['nope'])

    def test_deterministic(self):
        a = {'windows': [[1, '33']], 'end_frame': 10, 'wram_sha1': 'x'}
        self.assertTrue(ss.deterministic(a, dict(a)))
        self.assertFalse(ss.deterministic(a, {**a, 'end_frame': 11}))



ROOT = Path(__file__).resolve().parents[3]


@unittest.skipUnless((ROOT / 'rom' / 'dq4.nes').is_file() and (ROOT / 'rom' / 'dq5.sfc').is_file(),
                     'local source ROMs not present')
class ShopPlaceTest(unittest.TestCase):
    def test_counter_fronts_are_where_fc_walks(self):
        """카운터 앞 칸의 FC 블록은 맵 도착 자리에서 걸어서 닿고, 그 칸에서 카운터 쪽 한 블록은 카운터, 그 너머는
        그 가게 주인이다(FC 처럼 카운터 너머로 말을 검)."""
        sys.path[:0] = [str(ROOT / 'fc' / 'dq4' / 'tools')]
        import dq4block
        import dq4npcport
        from dq4environmentmap import block_prop
        from dq4environmentrom import COUNTER_PROPS, STAIRS
        from dq4groupbuild import LINKS, fc_map
        from kr_patch.fc import ines
        prg = ines.prg((ROOT / 'rom' / 'dq4.nes').read_bytes())
        _, _, report = dq4npcport.port(str(ROOT / 'rom' / 'dq5.sfc'), str(ROOT / 'rom' / 'dq4.nes'))
        service = {0: 2, 1: 3, 2: 1}   # $0F20 → dq4npcport 시설 번호(1 무기·2 도구·3 방어구)
        step = {'up': (0, -1), 'down': (0, 1), 'left': (-1, 0), 'right': (1, 0)}
        for name, (warp, (x, y), kind, direction) in ss.SHOPS.items():
            m = warp.split(',')[0]
            group, number = (int(v, 16) for v in m.split('/'))
            fg, fn = fc_map(prg, group, number)
            source = dq4block.Map(prg, fg, fn)

            def walkable(bx, by):
                # 문(FC 94·95·96, 2×2 9C·9D·A2, 성문 A0)은 열고 지나간다(사란 무기점은 문 너머)
                if not (0 <= bx < source.w and 0 <= by < source.h):
                    return False
                prop = block_prop(source, source.cell(bx, by) & 31)
                return not prop & 0x80 or prop in (0x94, 0x95, 0x96, 0x9C, 0x9D, 0xA0, 0xA2)
            # 한 그룹에 FC 그룹이 여럿이면(2장 45: 사란·바자·탑·동굴) 그 맵의 FC 그룹으로 들어오는 필드 도착
            start = next(link['arrival'] for link in LINKS[group] if link['fc'] == fg and link.get('map', 0) == fn)
            # 계단으로 올라오는 칸에서도 걷는다(사란 무기점은 2층에서 계단으로 내려오는 동쪽 방)
            stairs = {(bx, by) for bx in range(source.w) for by in range(source.h)
                      if block_prop(source, source.cell(bx, by) & 31) in STAIRS}
            seen, todo = {start} | stairs, [start, *stairs]
            while todo:
                bx, by = todo.pop()
                for dx, dy in step.values():
                    if walkable(bx + dx, by + dy) and (bx + dx, by + dy) not in seen:
                        seen.add((bx + dx, by + dy))
                        todo.append((bx + dx, by + dy))
            front = (x // 2, y // 2)
            self.assertIn(front, seen, name)
            dx, dy = step[direction]
            counter = (front[0] + dx, front[1] + dy)
            self.assertIn(block_prop(source, source.cell(*counter) & 31), COUNTER_PROPS, name)
            keeper = (counter[0] + dx, counter[1] + dy)
            self.assertIn(keeper, {(p['x'], p['y']) for p in report[m] if p['service'] == service[kind]}, name)


if __name__ == '__main__':
    unittest.main()
