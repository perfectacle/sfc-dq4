"""3장 조우 도구(구역별 몬스터 집합, 걸어서 닿는 칸)를 합성 PRG·합성 지도로 검사한다."""
import unittest

import dq4encounter as en
from test_dq4encounter import enc_prg


class ZoneMonsterTests(unittest.TestCase):
    def test_day_and_night_masks(self):
        prg = enc_prg()
        day = en.zone_monsters(prg, 5, 'day')
        night = en.zone_monsters(prg, 5, 'night')
        # 칸 7 은 마릿수 0~0 이라 빠지고, 칸 12 는 고정 편성 1 의 몬스터
        self.assertEqual(day, {0x10, 0x11, 0x12, 0x13, 0x20, 0x30, 0x40, 0x50, 0x51, 0x52})
        # 밤 마스크는 칸 0·6 을 빼고, 둘째 무리는 칸 1~4 에서만 고른다
        self.assertNotIn(0x10, night)
        self.assertNotIn(0x30, night)
        self.assertIn(0x11, night)


class ReachTests(unittest.TestCase):
    def test_entrances_stop_the_walk(self):
        land = {(x, y) for x in range(5) for y in range(3)} - {(2, 0), (2, 1), (2, 2)}
        land |= {(2, 1)}
        ents = {(2, 1): 0x16}
        cells, hits = en.reach(lambda x, y: (x, y) in land, ents, (0, 0))
        # 가운데 세로줄은 입구 칸 하나뿐이라 오른쪽으로 건너가지 못한다
        self.assertEqual(cells, {(x, y) for x in range(2) for y in range(3)})
        self.assertEqual(hits, {(0x16, (2, 1))})

    def test_bridge_opens_the_other_side(self):
        land = {(0, 0), (2, 0)}
        cells, _ = en.reach(lambda x, y: (x, y) in land, {}, (0, 0))
        self.assertEqual(cells, {(0, 0)})
        cells, _ = en.reach(lambda x, y: (x, y) in land | {(1, 0)}, {}, (0, 0))
        self.assertEqual(cells, {(0, 0), (1, 0), (2, 0)})


if __name__ == '__main__':
    unittest.main()
