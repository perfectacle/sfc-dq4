import unittest

import dq4monactcheck as mc


class JudgeTests(unittest.TestCase):
    def test_used_then_next_turn_is_ok(self):
        self.assertEqual(mc.judge([(139, 'turn'), (296, 'use'), (432, 'turn')]), ('ok', 296))

    def test_battle_that_ends_after_the_use_is_ok(self):
        self.assertEqual(mc.judge([(139, 'turn'), (300, 'use'), (700, 'field')]), ('ok', 300))

    def test_second_use_counts_as_progress(self):
        self.assertEqual(mc.judge([(139, 'turn'), (300, 'use'), (900, 'use')]), ('ok', 300))

    def test_nothing_after_the_use_is_stuck(self):
        self.assertEqual(mc.judge([(139, 'turn'), (303, 'use')]), ('stuck', 303))

    def test_progress_too_late_is_stuck(self):
        self.assertEqual(mc.judge([(10, 'use'), (10 + mc.PROGRESS + 1, 'turn')]), ('stuck', 10))

    def test_never_used(self):
        self.assertEqual(mc.judge([(139, 'turn'), (400, 'turn')]), ('unused', None))


class PlanTests(unittest.TestCase):
    def test_distinct_actions_of_ported_numbers_only(self):
        import dq4ch1walkcheck as wc
        import dq4monport
        rom = bytearray(wc.MONSTERS + 0x100 * 25)
        m = next(iter(dq4monport.PORT.values()))
        at = wc.MONSTERS + m * 25 + mc.ACTIONS_AT
        rom[at:at + 6] = bytes((0x73, 0x39, 0x73, 0x73, 0x39, 0x98))
        rows = mc.plan(bytes(rom))
        self.assertEqual([a for n, a in rows if n == m], [0x73, 0x39, 0x98])
        self.assertFalse(any(n in dq4monport.LATER for n, _ in rows))


if __name__ == '__main__':
    unittest.main()
