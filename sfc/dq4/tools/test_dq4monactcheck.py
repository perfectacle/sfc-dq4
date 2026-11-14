import unittest

import dq4monactcheck as mc


class JudgeTests(unittest.TestCase):
    def test_used_then_next_turn_is_ok(self):
        self.assertEqual(mc.judge([(139, 'turn', 0), (296, 'use', 0), (432, 'turn', 0)]), ('ok', 296))

    def test_battle_that_ends_after_the_use_is_ok(self):
        self.assertEqual(mc.judge([(139, 'turn', 0), (300, 'use', 0), (700, 'field', 0)]), ('ok', 300))

    def test_second_use_counts_as_progress(self):
        self.assertEqual(mc.judge([(139, 'turn', 0), (300, 'use', 0), (900, 'use', 0)]), ('ok', 300))

    def test_nothing_after_the_use_is_stuck(self):
        self.assertEqual(mc.judge([(139, 'turn', 0), (303, 'use', 0)]), ('stuck', 303))

    def test_progress_too_late_is_stuck(self):
        self.assertEqual(mc.judge([(10, 'use', 0), (10 + mc.PROGRESS + 1, 'turn', 0)]), ('stuck', 10))

    def test_never_used(self):
        self.assertEqual(mc.judge([(139, 'turn', 0), (400, 'turn', 0)]), ('unused', None))


class CastCountTests(unittest.TestCase):
    def test_baby_magician_casts_hyado_once_then_runs_out(self):
        # MP 2, ヒャド FC 2: 한 번 외워 0, 다음 시도는 「MP가 모자라다」 로 그대로
        events = [(139, 'turn', 2), (296, 'use', 2), (432, 'turn', 0), (580, 'use', 0), (711, 'turn', 0)]
        self.assertEqual(mc.judge(events, expect=1, cost=2), ('ok', 296))

    def test_spending_the_dq5_cost_is_wrong(self):
        # FC 2 인데 3 을 뺌(DQ5 ヒャド MP 그대로)
        self.assertEqual(mc.judge([(296, 'use', 3), (432, 'turn', 0)], expect=1, cost=2), ('mp', 296))

    def test_casting_without_enough_mp_is_wrong(self):
        self.assertEqual(mc.judge([(296, 'use', 1), (432, 'turn', 0)], expect=0, cost=2), ('mp', 296))

    def test_fewer_casts_than_fc_is_short(self):
        events = [(296, 'use', 6), (432, 'turn', 3), (600, 'turn', 3), (800, 'turn', 3)]
        self.assertEqual(mc.judge(events, expect=2, cost=3), ('short', 296))

    def test_cast_limit_caps_the_count(self):
        events = [e for k in range(mc.CAST_LIMIT) for e in ((100 + 300 * k, 'use', 200 - 2 * k),
                                                             (200 + 300 * k, 'turn', 198 - 2 * k))]
        self.assertEqual(mc.judge(events, expect=100, cost=2), ('ok', 100))

    def test_casts_reads_record_mp(self):
        import dq4ch1walkcheck as wc
        rom = bytearray(wc.MONSTERS + 0x40 * 25)
        rom[wc.MONSTERS + 0x33 * 25 + mc.MP_AT] = 12
        self.assertEqual(mc.casts(bytes(rom), 0x33, 2), 6)
        self.assertIsNone(mc.casts(bytes(rom), 0x33, None))
        rom[wc.MONSTERS + 0x33 * 25 + mc.MP_AT] = mc.INFINITE_MP
        self.assertIsNone(mc.casts(bytes(rom), 0x33, 3))


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
