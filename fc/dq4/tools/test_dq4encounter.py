"""조우 표(구역 지도·구역 레코드·무게로 칸 고르기·마릿수 부호·던전 목록·조우율 곱·켬/끔 칸·기습 문턱)를
합성 PRG 로 검사한다."""
import unittest

import dq4encounter as en

PRG_SIZE = 32 * 0x4000


def put(addr, data, prg):
    o = en.BANK * 0x4000 + (addr & 0x3FFF)
    prg[o:o + len(data)] = bytes(data)


def word(v):
    return [v & 0xFF, v >> 8]


def enc_prg():
    prg = bytearray(PRG_SIZE)
    put(en.ZONE_MAPS[0], word(0x8000), prg)
    put(en.ZONE_MAPS[2], word(0x8100), prg)
    put(en.ZONE_MAPS[4], word(0x8200), prg)
    put(0x8000 + 0x23, [0xC5], prg)            # 칸 (X>>4=3, Y>>4=2), 위 2비트(배)는 뺀다
    put(0x8200 + 0x23, [0x07], prg)
    put(en.ZONE_REC, word(0x8400), prg)
    put(en.BASE_RATE, [0x08, 0x10, 0x20, 0x30, 0x40, 0x50, 0x60, 0x70], prg)
    # 구역 5: 기본 조우율 줄 3, 무게 줄 2, 기습 문턱 1. 칸 0~13
    slots = [0x10, 0x11, 0x12, 0x13, 0xFF, 0x20, 0x30, 0x31, 0xFF, 0xFF, 0xFF, 0x40, 0x01, 0xFF]
    put(0x8400 + 16 * 5, [3 << 5 | 2 << 2 | 1, 7] + slots, prg)
    w = [10, 20, 30, 40, 50, 5, 5, 5, 5, 5, 5, 5, 5, 5, 0x40, 0x20] + word(0b011_010)
    put(en.WEIGHTS + 18 * 2, w, prg)
    put(en.SOLO_CNT, [1, 3, 4, 0, 0, 0, 0, 0], prg)
    put(en.SOLO_ADD, [1, 2, 5, 0, 0, 0, 0, 0], prg)
    put(en.FORMATION, word(0x8800), prg)
    put(0x8800 + 6 * 1, [0b010_001, 0b000_011, 0x50, 0x51, 0xFF, 0x52], prg)
    put(en.FORM_CNT, [1, 2, 3, 4, 0, 0, 0, 0], prg)
    put(en.FORM_ADD, [1, 1, 2, 2, 0, 0, 0, 0], prg)
    return prg


class ZoneTests(unittest.TestCase):
    def setUp(self):
        self.prg = enc_prg()

    def test_zone_map_by_chapter(self):
        self.assertEqual(en.zone_at(self.prg, 0, 0x35, 0x2F), 0x05)
        self.assertEqual(en.zone_at(self.prg, 1, 0x35, 0x2F), 0x05)       # 2장은 1장 지도
        self.assertEqual(en.zone_at(self.prg, 4, 0x35, 0x2F), 0x07)
        base, rows = en.zone_map(self.prg, 2)
        self.assertEqual((base, len(rows)), (0x8100, 8))

    def test_zone_record_fields(self):
        z = en.zone(self.prg, 5)
        self.assertEqual((z['addr'], z['rate'], z['row'], z['b1']), (0x8450, 0x30, 2, 7))

    def test_rand_values_cover_256(self):
        r = en.rand_values(10)
        self.assertEqual((sum(r.values()), min(r), max(r)), (256, 0, 9))

    def test_pick_skips_ff_and_masked_slots(self):
        z = en.zone(self.prg, 5)
        dist = en.pick(self.prg, z['slots'], z['row'], 0b1111)
        self.assertEqual(sum(dist.values()), 256)
        self.assertEqual(set(dist), {0, 1, 2, 3})
        self.assertLess(dist[0], dist[3])
        self.assertNotIn(4, en.pick(self.prg, z['slots'], z['row'], 0b11111))   # 칸 4 는 FF

    def test_outcomes_kinds_and_counts(self):
        out = en.outcomes(self.prg, 5, 'day')
        self.assertEqual(out[0][0], '무리')
        self.assertEqual(out[5][0], '우두머리+떼')
        self.assertEqual(out[6], ('한 무리', [({0x30}, 5, 8)]))         # 칸 6 은 부호 bit2-0 = 2
        self.assertEqual(out[7], ('한 무리', [({0x31}, 0, 0)]))         # 칸 7 은 bit5-3 = 3
        self.assertEqual(out[11], ('한 마리', [({0x40}, 1, 1)]))
        self.assertEqual(out[12][1], [({0x50}, 1, 2), ({0x51}, 2, 4), ({0x52}, 1, 1)])
        self.assertNotIn(4, out)

    def test_formation_count_codes(self):
        self.assertEqual(en.formation(self.prg, 1), [(0x50, 1, 2), (0x51, 2, 4), (0xFF, 2, 5), (0x52, 1, 1)])
        self.assertEqual(en.count_range(3, 0), (3, 3))


class TableTests(unittest.TestCase):
    def setUp(self):
        self.prg = enc_prg()

    def test_dungeon_lists_use_group_sizes(self):
        put(en.GROUP_SIZE + 2, [3], self.prg)
        put(en.GROUP_SIZE + 4, [1], self.prg)
        put(en.DUNGEON, word(0x9000), self.prg)
        put(en.DUNGEON5, word(0x9100), self.prg)
        put(0x9000, [0x02, 0x11, 0x12, 0x13, 0x04, 0x21, 0xFF], self.prg)
        put(0x9100, [0xFF], self.prg)
        (s1, e1, r1), (s5, e5, r5) = en.dungeon_lists(self.prg)
        self.assertEqual((s1, e1, r1), (0x9000, 0x9006, [(0x02, [0x11, 0x12, 0x13]), (0x04, [0x21])]))
        self.assertEqual(r5, [])

    def test_toggles_first_cell_wins(self):
        put(en.TOGGLE, [0x80 | 0x05, 0x40 | 0x06, 0x05, 0x86, 0xFF], self.prg)
        t = en.toggles(self.prg, 0)
        self.assertEqual((t[5, 6], t[6, 6], t[5, 7], t[6, 7]), (True, False, False, True))
        self.assertTrue(en.toggle_after(self.prg, 0, 5, 6, False))
        self.assertFalse(en.toggle_after(self.prg, 0, 9, 9, False))
        self.assertTrue(en.toggle_after(self.prg, 1, 5, 7, True))      # 순번 1 은 표를 보지 않음

    def test_ambush_odds_sum(self):
        put(en.AMBUSH + 2, [0x10, 0x18], self.prg)
        odds = en.ambush_odds(self.prg, 1)
        self.assertEqual(sum(odds), 256)
        self.assertEqual(odds, [sum(n for v, n in en.rand_values(0x21).items() if v <= 0x10),
                                sum(n for v, n in en.rand_values(0x21).items() if 0x10 < v <= 0x18),
                                sum(n for v, n in en.rand_values(0x21).items() if v > 0x18)])

    def test_expected_rate_multipliers(self):
        put(en.AFTER_BATTLE, [4, 8, 12], self.prg)
        put(en.TERRAIN_DAY, [0x10, 0x20], self.prg)
        put(en.TERRAIN_NIGHT, [0x40, 0x40], self.prg)
        self.assertEqual(en.expected_rate(self.prg, 5, 1, 0x00, 5, None), (0x30 * 0x10 * 0x20 >> 8) & 0xFF)
        self.assertEqual(en.expected_rate(self.prg, 5, 1, 0x80, 0, None), (0x30 * 4 * 0x40 >> 8) & 0xFF)
        dungeon = [0x80, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0]
        self.assertEqual(en.expected_rate(self.prg, 5, 1, 0x00, 5, dungeon), ((0x30 * 0x10 * 0x0F >> 8) & 0xFF) << 2)

    def test_expected_zone_paths(self):
        lists = [(0, 0, [(0x10, [0x22, 0x23])]), (0, 0, [])]
        self.assertEqual(en.expected_zone(self.prg, lists, [0x80, 0x10, 1, 0, 0], 0, 0), 0x23)
        self.assertEqual(en.expected_zone(self.prg, lists, [0x80, 0x10, 5, 0, 0], 0, 0), 0xFF)
        self.assertIsNone(en.expected_zone(self.prg, lists, [0, 0, 0, 0, 1], 0, 0))
        self.assertEqual(en.expected_zone(self.prg, lists, [0, 0, 0, 4, 0, 0, 0, 0, 0, 1], 0, 0x0B), 0x35)
        self.assertEqual(en.expected_zone(self.prg, lists, [0, 0, 0, 0, 0], 0x35, 0x2F), 0x05)


if __name__ == '__main__':
    unittest.main()
