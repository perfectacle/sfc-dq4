import unittest

import dq4battlescene as bs


def run_code(code):
    """force_code 를 따라가 7E 뱅크에 쓰는 값을 {주소: (값, 바이트 수)} 로."""
    out, i, wide = {}, 3, True
    assert code[:3] == bytes((0x08, 0xC2, 0x20))
    while i < len(code) - 3:
        op = code[i]
        if op == 0xE2:
            wide, i = False, i + 2
            continue
        assert op == 0xA9
        n = 2 if wide else 1
        value = int.from_bytes(code[i + 1:i + 1 + n], 'little')
        assert code[i + 1 + n] == 0x8F
        out[int.from_bytes(code[i + 2 + n:i + 5 + n], 'little')] = (value, n)
        i += 5 + n
    return out, code[-3:]


def summary(**kw):
    base = {'start': 100, 'end': 900, 'finished': 700, 'song_at_end': 0x0A, 'moved': True,
            'before': {'map': '39/01', 'cell': [20, 17], 'gold': 1000, 'exp': 10},
            'after': {'map': '39/01', 'cell': [20, 17], 'gold': 1003, 'exp': 14, 'items': [0xFF] * 12, 'flags': [],
                      'hero': {'level': 6, 'stats': [47, 16, 26, 13, 12, 4, 7], 'next': 804, 'exp': 14, 'hp': 47,
                               'max_hp': 47}}}
    base.update(kw)
    return base


class ForceCodeTests(unittest.TestCase):
    def test_writes_group_zone_level_and_flags_then_sets_carry(self):
        out, tail = run_code(bs.force_code([(0x00, 2), (0x12, 1)], 99, 0x40))
        self.assertEqual(tail, bytes((0x28, 0x38, 0x6B)))          # PLP / SEC / RTL
        self.assertEqual(out[0x7E1001], (0x1200, 2))
        self.assertEqual(out[0x7E1003], (0xFFFF, 2))
        self.assertEqual(out[0x7E1005], (0x0102, 2))
        self.assertEqual(out[0x7E100F], (99, 1))
        self.assertEqual(out[0x7E1000], (0x40, 1))

    def test_group_size_limits(self):
        with self.assertRaises(ValueError):
            bs.force_code([], 0)
        with self.assertRaises(ValueError):
            bs.force_code([(0, 1)] * 5, 0)

    def test_sentinel_pads_with_ff(self):
        self.assertEqual(bs.group_sentinel([(0x00, 2)]), bytes((0x00, 0xFF, 0xFF, 0xFF)))


class MonsterPatchTests(unittest.TestCase):
    def test_round_trip_keeps_other_bits(self):
        rom = bytearray(0x120000)
        base = 0x118000 + 3 * 25
        rom[base + 8] = 0b0011_1100                                 # 금화 위 비트·피하기 그대로 남아야 함
        rom[base + 10] = 0b1111_1000
        for off, v in bs.monster_patch(bytes(rom), 3, hp=0x234, attack=0x1FF, defense=0x100):
            rom[off] = v
        got = bs.monster_values(bytes(rom), 3)
        self.assertEqual((got['hp'], got['attack'], got['defense']), (0x234, 0x1FF, 0x100))
        self.assertEqual(rom[base + 8] & 0x3C, 0x3C)
        self.assertEqual(rom[base + 10] & 0xF8, 0xF8)
        self.assertEqual(bytes(rom[base + 17:base + 23]), bytes([0x73] * 6))

    def test_actions_none_leaves_actions(self):
        rom = bytearray(0x120000)
        self.assertFalse([off for off, _ in bs.monster_patch(bytes(rom), 0, hp=1, actions=None)
                          if off >= 0x118000 + 17])


class DamageTests(unittest.TestCase):
    # dq5-data-format 「전투 계산식」 의 실측 표
    def test_normal_ranges_match_measured_table(self):
        self.assertEqual(bs.normal_range(200, 5), (86, 110))
        self.assertEqual(bs.normal_range(64, 120), (1, 3))
        self.assertEqual(bs.normal_range(40, 60), (4, 6))
        self.assertEqual(bs.normal_range(10, 60), (0, 1))

    def test_crit_range(self):
        self.assertEqual(bs.crit_range(200), (171, 203))

    def test_classify(self):
        self.assertEqual(bs.classify_hit(20, 40, 0), 'normal')
        self.assertEqual(bs.classify_hit(40, 40, 0), 'crit')
        self.assertIsNone(bs.classify_hit(30, 40, 0))
        self.assertEqual(bs.classify_hit(3, 40, 0, killed=True), 'kill')
        self.assertIsNone(bs.classify_hit(41, 40, 0, killed=True))         # 회심 최댓값 40 도 넘음

    def test_small_h_has_three_values(self):
        self.assertEqual(sorted(set(bs.normal_values(40, 50))), [6, 7, 8])

    def test_mean_problem(self):
        self.assertIsNone(bs.mean_problem([19, 20] * 3, 40, 0))            # 10개 미만은 보지 않음
        self.assertIsNone(bs.mean_problem([19, 20] * 10, 40, 0))
        self.assertIsNotNone(bs.mean_problem([17] * 20, 40, 0))


class ExpectTests(unittest.TestCase):
    def test_heal_expect_caps_at_max(self):
        self.assertEqual(bs.heal_expect(20, 100, 30, 11), (50, 60))
        self.assertEqual(bs.heal_expect(80, 100, 30, 11), (100, 100))
        self.assertEqual(bs.heal_expect(0, 100, 30, 0), (30, 30))

    def test_flee_tries(self):
        self.assertEqual(bs.flee_tries({'turn': 'flee'}, 3, None), 3)
        self.assertEqual(bs.flee_tries({'turn': 'flee', 'then': ('attack', 2)}, 4, 3), 2)
        self.assertEqual(bs.flee_tries({'turn': 'defend', 'then': ('flee', 'heal')}, 3, 2), 2)
        self.assertEqual(bs.flee_tries({'turn': 'attack'}, 5, None), 0)


class JudgeTests(unittest.TestCase):
    expect = {'song': 0x0A, 'gold': 3, 'exp': 4}

    def test_win_passes(self):
        self.assertEqual(bs.judge_win(summary(), self.expect), [])

    def test_win_reports_gold_exp_place_song(self):
        s = summary(song_at_end=0x1F)
        s['after'] = {**s['after'], 'gold': 1000, 'exp': 10, 'cell': [20, 18]}
        problems = bs.judge_win(s, self.expect)
        self.assertEqual(len(problems), 4, problems)

    def test_timeout_tells_stall_from_song(self):
        stall = bs.judge_common({'start': 1, 'end': None, 'timeout_at': 9000, 'last_song': '21'}, self.expect)
        song = bs.judge_common({'start': 1, 'end': None, 'timeout_at': 9000, 'last_song': '1F',
                                'moved_after_timeout': True}, self.expect)
        self.assertIn('멈춤', stall[0])
        self.assertIn('걷기는 됨', song[0])

    def test_finish_limit_catches_long_stall_after_victory(self):
        s = summary(finished=100, end=100 + bs.FINISH_LIMIT + 1)
        self.assertTrue(any('다 쓰러진 뒤' in p for p in bs.judge_win(s, self.expect)))

    def test_levelup_checks_only_curve_free_things(self):
        s = summary()
        s['before'] = {**s['before'], 'hero': {'level': 5, 'stats': [40, 14, 23, 11, 10, 4, 6], 'next': 475}}
        expect = {**self.expect, 'level': 6}
        self.assertEqual(bs.judge_levelup(s, expect), [])
        self.assertEqual(len(bs.judge_levelup(s, {**expect, 'level': 7})), 1)
        s['after'] = {**s['after'], 'hero': {**s['after']['hero'], 'stats': [39, 16, 26, 13, 12, 4, 7], 'next': 400}}
        self.assertEqual(len(bs.judge_levelup(s, expect)), 2)

    def test_lose(self):
        s = summary(song_back=100)
        s['after'] = {**s['after'], 'map': '36/00', 'cell': [10, 45], 'gold': 500}
        expect = {'song': None, 'place': ('36/00', 10, 45), 'gold': 500}
        self.assertEqual(bs.judge_lose(s, expect), [])
        s['after'] = {**s['after'], 'hero': {**s['after']['hero'], 'hp': 1}}
        self.assertEqual(len(bs.judge_lose(s, expect)), 1)

    def test_noflee_needs_every_try_to_fail(self):
        expect = {**self.expect, 'flee_tries': 2}
        self.assertEqual(bs.judge_noflee(summary(flee_tries=2, fled=False), expect), [])
        self.assertEqual(len(bs.judge_noflee(summary(flee_tries=2, fled=True), expect)), 1)

    def test_heal_with_caster_mp(self):
        expect = {**self.expect, 'amount': (30, 11), 'max_hp': 100, 'mp_cost': 3}
        s = summary(heals=[{'from': 40, 'to': 75, 'caster_mp_drop': 3}])
        self.assertEqual(bs.judge_heal(s, expect), [])
        s = summary(heals=[{'from': 40, 'to': 95, 'caster_mp_drop': 2}])
        self.assertEqual(len(bs.judge_heal(s, expect)), 2)
        self.assertIn('HP 회복이 없음', bs.judge_heal(summary(heals=[]), expect))

    def test_monflee_needs_monster_alive(self):
        expect = {**self.expect, 'gold': 0, 'exp': 0}
        s = summary(mon_hp_at_finish=[])
        s['after'] = {**s['after'], 'gold': 1000, 'exp': 10}
        self.assertEqual(bs.judge_monflee(s, expect), [])
        self.assertEqual(len(bs.judge_monflee({**s, 'mon_hp_at_finish': [0]}, expect)), 1)

    def test_known_issue_scenes_are_not_in_default(self):
        self.assertFalse(set(bs.KNOWN_ISSUES) & set(bs.DEFAULT_SCENES))

    def test_every_scene_has_a_judge_and_turn_policy(self):
        for name, scene in bs.SCENES.items():
            self.assertIn(name, bs.JUDGES)
            self.assertIn(scene['turn'], bs.TURNS)
            if 'then' in scene:
                self.assertIn(scene['then'][0], bs.TURNS)


class DistributionTests(unittest.TestCase):
    def test_counts(self):
        rows = [{'start': 1, 'opening': 2, 'hits': [{'kind': 'normal'}, {'kind': 'crit'}, {'kind': 'kill'}],
                 'flee_tries': 1, 'fled': True},
                {'start': 1, 'opening': 1, 'flee_tries': 3, 'fled': True},
                {'start': 1, 'opening': 0, 'flee_tries': 2, 'fled': False},
                {'start': None}]
        got = bs.distribution(rows)
        self.assertEqual({k: got[k] for k in ('battles', 'preemptive', 'ambush', 'hits', 'crits', 'flee_tries',
                                              'flee_fails')},
                         {'battles': 3, 'preemptive': 1, 'ambush': 1, 'hits': 2, 'crits': 1, 'flee_tries': 6,
                          'flee_fails': 4})
        # 선제 전투(바로 성공)는 차례별 셈에서 뺀다
        self.assertEqual(got['flee_by_try'], [[2, 2], [2, 2], [1, 0], [0, 0]])

    def test_binom_interval(self):
        lo, hi = bs.binom_interval(374, 1 / 32)
        self.assertTrue(1 <= lo <= 3 and 20 <= hi <= 25, (lo, hi))
        self.assertEqual(bs.binom_interval(10, 0.0), (0, 0))

    def test_distribution_problems(self):
        base = {'battles': 32, 'preemptive': 1, 'ambush': 2, 'hits': 374, 'crits': 10, 'flee_tries': 0,
                'flee_fails': 0, 'flee_by_try': [[0, 0]] * 4}
        self.assertEqual(bs.distribution_problems('attack', base), [])
        self.assertEqual(len(bs.distribution_problems('attack', {**base, 'crits': 40})), 1)
        self.assertEqual(len(bs.distribution_problems('attack', {**base, 'ambush': 32})), 1)
        log = []
        self.assertEqual(bs.distribution_problems('attack', {**base, 'battles': 3, 'hits': 38, 'crits': 30}, log)[0][:2],
                         '회심')
        self.assertEqual(bs.distribution_problems('attack', {**base, 'battles': 3, 'hits': 20}, log), [])
        self.assertTrue(log)
        flee = {**base, 'hits': 0, 'crits': 0, 'flee_tries': 59, 'flee_by_try': [[30, 14], [14, 7], [7, 2], [8, 1]]}
        self.assertEqual(bs.distribution_problems('flee', flee), [])
        self.assertEqual(len(bs.distribution_problems('flee', {**flee, 'flee_by_try': [[30, 30], [29, 29], [0, 0],
                                                                                         [0, 0]]})), 1)

    def test_core_key(self):
        self.assertEqual(bs.core_key('Snes9x 1.63 fae2fea'), 'snes9x')
        self.assertEqual(bs.core_key('bsnes 115'), 'bsnes')
        with self.assertRaises(ValueError):
            bs.core_key('mesen 2')

    def test_digest_ignores_timing_fields(self):
        a = summary(seconds=1.0)
        b = summary(seconds=2.0)
        self.assertEqual(bs.digest(a), bs.digest(b))
        self.assertNotEqual(bs.digest(a), bs.digest(summary(end=901)))


if __name__ == '__main__':
    unittest.main()
