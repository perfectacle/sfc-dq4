"""3장 용병 로렌스의 행동 고르기(dq4mercenary._ai)를 w65816 으로 돌려 FC 갈래와 견준다.

FC(fc/dq4/docs/dq4-chapter3-format.md 「용병」, AI 레코드 C7·고르는 법 1): 칸 가중치를 같은 행동끼리 합친 ホイミ 143·
ギラ 47·ラリホー 37·공격 28 가운데 쓸 수 있는 칸만 남겨 그 합으로 고른다. ホイミ 는 같은 편이 HP 절반 미만이고 MP 3 이상,
ギラ 는 MP 4 이상, ラリホー 는 MP 3 이상이고 깨어 있는 몬스터가 있을 때(실측: 잠든 동안 ラリホー 0 번, MP 2 면 공격만,
MP 3 이면 ギラ 가 빠짐, HP 49/100 이면 ホイミ·50/100 이면 없음).
"""
import sys
import unittest
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4mercenary as m  # noqa: E402
from w65816 import Cpu  # noqa: E402

AT = 0x5CF800
CH1 = 0x21AF21
HEAL_MP, GIRA_MP = m.SPELL_MP[m.HEAL], m.SPELL_MP[m.GIRA]


def lorom(a):
    return ((a >> 16 & 0x7F) << 15) | (a & 0x7FFF)


def fc_pick(r, hurt, mp, awake):
    """FC 식: 남은 칸의 가중치 합 s, v = ⌊r × s / 256⌋, 누적이 v 보다 커지는 칸."""
    w = dict(m.OTHER_WEIGHTS)
    slots = []
    if hurt and mp >= HEAL_MP:
        slots.append((m.HEAL, m.HEAL_WEIGHT))
    if mp >= GIRA_MP:
        slots.append((m.GIRA, w[m.GIRA]))
    if mp >= m.SPELL_MP[m.RARIHO] and awake:
        slots.append((m.RARIHO, w[m.RARIHO]))
    slots.append((m.ATTACK, w[m.ATTACK]))
    v = r * sum(x for _, x in slots) >> 8
    for act, x in slots:
        if v < x:
            return act
        v -= x


class LawrenceTest(unittest.TestCase):
    def run_ai(self, r, hurt, mp, monsters):
        """monsters: [(있음, 잠)]. 로렌스는 기록 1, 톨네코는 기록 0(HP 10/100 이면 다침). (고른 행동, 대상)."""
        code = m._ai(CH1)
        rom = bytearray(0x300000)
        rom[lorom(AT):lorom(AT) + len(code)] = code
        w = bytearray(0x20000)
        w[m.WALKERS & 0xFFFF] = 2
        w[m.ORDERS[0] & 0xFFFF], w[(m.ORDERS[0] & 0xFFFF) + 1] = 0, 1
        base = m.PARTY_AT & 0xFFFF
        for rec, (kind, hp, mx, mpv) in enumerate(((0x00, 10 if hurt else 100, 100, 0),
                                                   (m.GUEST | m.LAWRENCE_KIND, 58, 58, mp))):
            o = base + 42 * rec
            w[o] = kind
            w[o + 2:o + 4] = hp.to_bytes(2, 'little')
            w[o + 4:o + 6] = mpv.to_bytes(2, 'little')
            w[o + 0x0E:o + 0x10] = mx.to_bytes(2, 'little')
        for k, (there, asleep) in enumerate(monsters):
            o = (m.MONSTER_SLOTS & 0xFFFF) + 16 * k
            w[o + 0x0A] = 0x80 if there else 0
            w[o + 0x0B] = 0x80 if asleep else 0
        c = Cpu(bytes(rom), w)
        got = {}

        def brk(cpu):                      # BRK 8B 80 2A: 행동자 기록 +0 → $46
            cpu.wram[0x46] = m.GUEST | m.LAWRENCE_KIND
            cpu.pc = (cpu.pc + 4) & 0xFFFF
            return True

        def random(cpu):
            cpu.a = (cpu.a & 0xFF00) | (r * (cpu.a & 0xFF)) >> 8
            cpu.rtl()
            return True

        def done(cpu):
            got['act'], got['target'] = cpu.a & 0xFF, cpu.wram[m.TARGET & 0xFFFF]
            cpu.pbr, cpu.pc = 0xFF, 0xFFFE
            return True
        c.hooks[AT + 5] = brk
        c.hooks[m.RANDOM] = random
        c.hooks[m.AI_DONE] = done
        c.jsl(AT, max_steps=20000)
        return got['act'], got['target']

    def check(self, hurt, mp, monsters):
        awake = any(t and not s for t, s in monsters)
        got = Counter(self.run_ai(r, hurt, mp, monsters)[0] for r in range(256))
        want = Counter(fc_pick(r, hurt, mp, awake) for r in range(256))
        self.assertEqual(got, want, (hurt, mp, monsters))
        return got

    def test_all_slots(self):
        got = self.check(True, 68, [(True, False)])
        self.assertEqual(set(got), {m.HEAL, m.GIRA, m.RARIHO, m.ATTACK})

    def test_asleep_drops_rariho(self):
        got = self.check(False, 68, [(True, True), (False, False)])
        self.assertNotIn(m.RARIHO, got)
        # 한 마리라도 깨어 있으면 남는다
        self.assertIn(m.RARIHO, self.check(False, 68, [(True, True), (True, False)]))

    def test_mp_three_drops_gira_and_two_drops_spells(self):
        self.assertNotIn(m.GIRA, self.check(True, 3, [(True, False)]))
        self.assertEqual(set(self.check(True, 2, [(True, False)])), {m.ATTACK})

    def test_healthy_has_no_heal(self):
        self.assertNotIn(m.HEAL, self.check(False, 68, [(True, False)]))

    def test_heal_targets_the_hurt_one(self):
        act, target = self.run_ai(0, True, 68, [(True, False)])
        self.assertEqual((act, target), (m.HEAL, 1))


if __name__ == '__main__':
    unittest.main()
