"""3장 북쪽 동굴 구르는 바위(dq4boulder): FC 실측 궤적(dq4boulder-fc.tsv)을 파이썬 모형과 w65816 로 돌린 네이티브
한 차례에 차례로 넣어 같은 다음 상태가 나오는지, 영역 이동 훅·셀 덮기·바위 옮기기의 바이트."""

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4boulder as b  # noqa: E402
import dq4ch3slots as slots  # noqa: E402

TRACE = HERE / 'dq4boulder-fc.tsv'
BASE = 0x5CE300
V = b.Vars(slots.VARS_AT + slots.SLOTS['S'].vars[0])


def trace():
    """{길: [(프레임, (주인공 X, Y), (바위 X, Y, 상태))]}."""
    out = {}
    for line in TRACE.read_text(encoding='utf-8').splitlines():
        if line.startswith('#') or not line:
            continue
        name, frame, hx, hy, x, y, st = line.split('\t')
        out.setdefault(name, []).append((int(frame), (int(hx, 16), int(hy, 16)), (int(x, 16), int(y, 16), int(st, 16))))
    return out


def ticks(rows):
    """[(앞 상태, 주인공, 뒤 상태)]: 바위가 움직이는 동안 바위 변수가 바뀐 줄마다(바뀌지 않은 차례는 기록에 없음)."""
    out = []
    for (_, _, before), (_, hero, after) in zip(rows, rows[1:]):
        if before != after and before[2] & 3:
            out.append((before, hero, after))
    return out


def lorom(addr):
    return (addr >> 16 & 0x7F) * 0x8000 + (addr & 0x7FFF)


def machine(pieces, at):
    from w65816 import Cpu
    rom = bytearray(0x300000)
    for name, code in pieces:
        rom[lorom(at[name]):lorom(at[name]) + len(code)] = code
    return bytes(rom), Cpu


def same(after, got):
    """FC 는 구덩이를 메우면 흔들기 동안 80 을 거쳐 40 이 된다. 멈춤(방향 0)과 자리만 견준다."""
    if after[2] & 3 == 0:
        return got[:2] == after[:2] and got[2] & 3 == 0
    return got == after


class ModelTest(unittest.TestCase):
    def test_model_follows_the_fc_trace(self):
        for name, rows in trace().items():
            for before, hero, after in ticks(rows):
                self.assertTrue(same(after, b.model_tick(before, hero)), f'{name} {before} {hero} → {after}')

    def test_trace_reaches_each_pit(self):
        ends = {name: rows[-1][2] for name, rows in trace().items()}
        self.assertEqual(ends['left'][:2], (0x03, b.PIT_Y))
        self.assertEqual(ends['middle'][:2], (0x0B, b.PIT_Y))
        self.assertEqual(set(b.PITS), {0x03, 0x0B})


class NativeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import w65816  # noqa: F401
        except ImportError:
            raise unittest.SkipTest('w65816 없음')
        cls.pieces, cls.at = b.natives(V, BASE, 0x3E, 0x07)
        cls.rom, cls.Cpu = machine(cls.pieces, cls.at)

    def run_step(self, state, members):
        w = bytearray(0x20000)
        w[V(b.BX) & 0xFFFF], w[V(b.BY) & 0xFFFF], w[V(b.ST) & 0xFFFF] = state
        for k, (x, y) in enumerate(members):
            w[b.SLOT_X + k], w[b.SLOT_Y + k] = 2 * x + (k & 1), 2 * y + 1 + (k >> 1 & 1)
        w[b.FOLLOWERS] = len(members)
        c = self.Cpu(self.rom, w)
        c.pbr = BASE >> 16
        c.jsr(self.at['step'], max_steps=20000)
        w = c.wram
        return (w[V(b.BX) & 0xFFFF], w[V(b.BY) & 0xFFFF], w[V(b.ST) & 0xFFFF])

    def test_native_step_follows_the_fc_trace(self):
        n = 0
        for name, rows in trace().items():
            for before, hero, after in ticks(rows):
                got = self.run_step(before, [hero])
                self.assertTrue(same(after, got), f'{name} {before} {hero}: {got} 기대 {after}')
                n += 1
        self.assertGreater(n, 150)

    def test_followers_also_stop_the_boulder(self):
        # 바위 아래 칸에 둘째 일행이 있으면 주인공이 멀어도 막힘(FC 1D:$9E2D 는 일행 모두를 봄)
        self.assertEqual(self.run_step((3, 0x10, 0xC2), [(0x0B, 0x15), (3, 0x12)]), (3, 0x10, 0xE2))
        self.assertEqual(self.run_step((3, 0x10, 0xC2), [(0x0B, 0x15)]), (3, 0x11, 0x82))
        self.assertEqual(self.run_step((3, 0x10, 0xC2), [(0x0B, 0x15), (3, 0x12), (5, 5), (6, 6), (7, 7)]),
                         (3, 0x10, 0xE2))

    def run_ctl(self, state, cnt, hero):
        w = bytearray(0x20000)
        w[V(b.BX) & 0xFFFF], w[V(b.BY) & 0xFFFF], w[V(b.ST) & 0xFFFF] = state
        w[V(b.CNT) & 0xFFFF] = cnt
        w[b.SLOT_X], w[b.SLOT_Y] = 2 * hero[0], 2 * hero[1] + 1
        c = self.Cpu(self.rom, w)
        c.pbr = BASE >> 16

        def rtl(cpu):
            lo, hi, bank = cpu.pull(), cpu.pull(), cpu.pull()
            cpu.pbr, cpu.pc = bank, ((hi << 8 | lo) + 1) & 0xFFFF
            return True
        c.hooks[self.at['copy_block']] = rtl
        c.jsl(self.at['ctl'], max_steps=20000)
        return c.wram[V(b.ST) & 0xFFFF]

    def test_release_is_seen_on_every_call(self):
        # 풀림 판정은 TICK 번째 부름을 기다리지 않는다(주인공은 풀리는 줄을 16프레임 안팎에 지나감, 부름은 약 8프레임마다)
        (x0, x1), y = b.TRIGGER
        for cnt in range(b.TICK):
            for x in (x0, x1):
                self.assertEqual(self.run_ctl((*b.START, 0), cnt, (x, y)) & 3, 2, (cnt, x))
        self.assertEqual(self.run_ctl((*b.START, 0), 0, (x0, y + 1)), 0)

    def test_ctl_turns_rocks_back_to_their_quadrant(self):
        # 말을 걸면 바위 인물이 주인공 쪽으로 돈다. 부를 때마다 몇째 바위인지의 방향 프레임으로 되돌려야 사분면이 맞는다
        w = bytearray(0x20000)
        w[V(b.BX) & 0xFFFF], w[V(b.BY) & 0xFFFF] = b.START
        w[b.SLOT_X], w[b.SLOT_Y] = 0x20, 0x21
        rocks = range(0x0A, 0x0E)
        for s in rocks:
            w[b.SLOT_GFX + s], w[b.SLOT_X + s], w[b.SLOT_Y + s], w[b.SLOT_FACING + s] = b.ROCK_GFX, 6, 11, 0x88
        c = self.Cpu(self.rom, w)
        c.pbr = BASE >> 16
        c.jsl(self.at['ctl'], max_steps=20000)
        self.assertEqual([c.wram[b.SLOT_FACING + s] for s in rocks], [b.FACING_CODES[f] for f in b.ROCK_FACINGS])

    def test_idle_boulder_does_nothing(self):
        self.assertEqual(self.run_step((3, 5, 0x00), [(3, 0x0E)]), (3, 5, 0x00))
        self.assertEqual(self.run_step((3, 0x25, 0x40), [(3, 0x24)]), (3, 0x25, 0x40))

    def area_case(self, x0, fill, group=0x3E, number=0x07, layer=1, record_layer=1):
        w = bytearray(0x20000)
        w[0xC3], w[0xBC], w[0xBD] = layer, group, number
        w[V(b.FILL) & 0xFFFF] = fill
        rom = bytearray(self.rom)
        rec = 0x2A9000
        rom[lorom(rec):lorom(rec) + 5] = bytes((x0, 75, x0 + 3, 76, record_layer))
        c = self.Cpu(bytes(rom), w)
        c.dbr, c.y = 0x2A, 0x9000
        c.p = 0x20
        c.jsl(self.at['area'], max_steps=200)
        return not (c.p & 0x02)       # Z 꺼짐 = 옮기지 않음

    def test_area_hook_skips_only_the_filled_pit(self):
        self.assertFalse(self.area_case(0x06, 0))
        self.assertTrue(self.area_case(0x06, 1))
        self.assertFalse(self.area_case(0x16, 1))
        self.assertTrue(self.area_case(0x16, 2))
        self.assertFalse(self.area_case(0x06, 1, number=0x08))
        self.assertTrue(self.area_case(0x06, 0, record_layer=2))    # 층이 다르면 원래대로 옮기지 않음

    def test_hooks_and_sizes(self):
        self.assertEqual(len(b.area_hook(self.at)), len(b.AREA_ORIG))
        hook = b.area_hook(self.at)
        self.assertEqual(hook[:4], bytes((0x22, *b._al(self.at['area']))))
        self.assertEqual(b.AREA_SITE + 6 + hook[5], 0x00CE34)
        for name in ('place', 'remove_rocks', 'copy_block', 'reset', 'ctl'):
            self.assertEqual(dict(self.pieces)[name][0], 0x08, name)     # PHP 로 시작(dq4brkscan)

    @unittest.skipUnless((HERE.parents[2] / 'rom' / 'dq5.sfc').exists(), 'DQ5 롬 없음')
    def test_area_site_holds_the_original_bytes(self):
        data = (HERE.parents[2] / 'rom' / 'dq5.sfc').read_bytes()
        self.assertEqual(data[lorom(b.AREA_SITE):lorom(b.AREA_SITE) + len(b.AREA_ORIG)], b.AREA_ORIG)


class PictureTest(unittest.TestCase):
    def test_rock_is_the_nds_boulder_prop(self):
        # 바위 그림은 NDS 큰 바위(dq4people.PROPS)의 사분면이다. DQ5 미는 바위(4B) 넷으로 되돌리면 실패
        import dq4people
        prop = next(p for p in dq4people.PROPS if p.role == '구르는 바위')
        self.assertEqual(prop.pictures, (b.ROCK_GFX,))
        self.assertNotEqual(b.ROCK_GFX, 0x4B)
        self.assertEqual(dq4people.PROP_SHEETS[prop.sheet].name, 'oiwa_0_0.webp')
        self.assertEqual(b.ROCK_FACINGS, dq4people.PROP_QUADRANTS)
        self.assertEqual(sorted(b.FACING_CODES), sorted(b.ROCK_FACINGS))

    def test_safe_rocks_stand_in_quadrant_order(self):
        import dq4ch3safe as safe
        lists = {m: {"map": m, "entries": []} for m in (safe.GATES, safe.VAULT, safe.ROLL)}

        class Ctx:
            talk = {'button': 1, 'floor': 2}
        safe.npc_lists(lists, Ctx())
        rocks = [e["fields"] for e in lists[safe.ROLL]["entries"] if e["fields"]["gfx"] == b.ROCK_GFX
                 and e["time"] == 'day']
        x, y = b.START
        self.assertEqual([(r["x"], r["y"], r["facing"]) for r in rocks],
                         [(2 * (x + k % 2), 2 * (y + k // 2) + 1, f) for k, f in enumerate(b.ROCK_FACINGS)])


if __name__ == '__main__':
    unittest.main()
