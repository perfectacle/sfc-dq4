import random
import unittest
from collections import Counter
from pathlib import Path

import numpy as np

import dq4fieldencounter as FE
import dq4moncount as C

ROOT = Path(__file__).resolve().parents[3]
DQ4 = ROOT / 'rom' / 'dq4.nes'

# 첫 목록: 칸 0(여러 종)·5(우두머리)·7(한 종)·11(한 마리)·12(편성), 둘째 목록: 칸 1·2
FIRST = [(0, 60), (5, 40), (7, 50), (11, 30), (12, 40)]
SECOND = [(1, 100), (2, 50)]
DATA = {'monsters': [0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x1B, 0xFF, 0xFF],
        'codes': 0b011 << 3,                     # 칸 7 = 부호 3
        'formations': {12: [(0x20, 1, 2), (0xFF, 1, 1), (0x21, 0, 3), (0xFF, 0, 1)]}}
ROW = (40, 0x08, 128, 64, {'day': (FIRST, SECOND), 'night': (FIRST[:2], [])}, DATA)
TABLES = {'extra_max': [4, 5, 6, 7, 8, 8, 8, 8], 'extra_p': [96, 128, 160, 0, 0, 0, 0, 0],
          'solo_add': [1, 1, 2, 3, 1, 2, 1, 1], 'solo_cnt': [1, 2, 3, 4, 3, 3, 1, 1]}


def model(night, k, state):
    groups, _ = FE.fc_formation(ROW, TABLES, k, night, state)
    return tuple((m, c) for m, c in groups if c > 0)


class FormationTests(unittest.TestCase):
    def test_run_states_matches_fc_formation(self):
        """난수 상태마다 run_states 의 무리가 fc_formation 과 같다(위 비트가 달라도 아래 24비트가 같으면 같은 무리)."""
        rng = random.Random(1)
        states = [rng.getrandbits(32) for _ in range(4000)]
        for night in (False, True):
            for k in (0, 1, 2):
                mon, cnt, _ = C.run_states(ROW, DATA, TABLES, k, night,
                                           np.array([s & 0xFFFFFF for s in states], np.uint32))
                for i, s in enumerate(states):
                    got = tuple((int(m), int(c)) for m, c in zip(mon[i], cnt[i]) if c > 0)
                    self.assertEqual(got, model(night, k, s), (night, k, hex(s)))

    def test_outcomes_count_every_low_state(self):
        """outcomes 의 몫은 아래 24비트 값 모두를 센 비율이다(작은 덩이로 나눠도 같음)."""
        got = C.outcomes(ROW, DATA, TABLES, 1, False, chunk=1 << 20)
        self.assertAlmostEqual(sum(got.values()), 1.0, places=9)
        self.assertEqual(got, C.outcomes(ROW, DATA, TABLES, 1, False))
        rng = random.Random(2)
        seen = Counter(model(False, 1, rng.getrandbits(32)) for _ in range(3000))
        self.assertLessEqual(set(seen), set(got))


class FitTests(unittest.TestCase):
    def test_fc_shown_carries_width_across_groups(self):
        """14:$9C54: 폭 + 1 의 합이 32 에 닿는 마리부터 빼고, 합은 다음 무리로 이어진다(FC 전투 덤프와 같은 꼴)."""
        w = {0x00: 2, 0x6E: 8, 0x05: 2, 0x0D: 3}
        self.assertEqual(C.fc_shown(w, [(0x00, 8)]), [8])
        self.assertEqual(C.fc_shown(w, [(0x6E, 8)]), [3])
        self.assertEqual(C.fc_shown(w, [(0x00, 1), (0x6E, 7)]), [1, 3])
        self.assertEqual(C.fc_shown(w, [(0x6E, 3), (0x00, 5), (0x05, 2)]), [3, 1, 0])
        self.assertEqual(C.fc_shown(w, [(0x0D, 7)]), [7])

    def test_judge(self):
        known = {(2, 0x0C, 'day'): 5}
        up, down = C.judge({(2, 0x0C, 'day'): {'short': 4}, (1, 0x04, 'day'): {'short': 0}}, known)
        self.assertEqual((up, down), ([], [((2, 0x0C, 'day'), 5, 4)]))
        up, _ = C.judge({(2, 0x0C, 'day'): {'short': 5}, (3, 0x14, 'night'): {'short': 1}}, known)
        self.assertEqual(up, [((3, 0x14, 'night'), 0, 1)])

    def test_known_keeps_chapters_1_and_3_at_zero(self):
        self.assertFalse([k for k, v in C.KNOWN.items() if k[0] != 2 and v])
        for ch, z, mode in C.KNOWN:
            self.assertIn(z, C.CHAPTER_ZONES[ch])
            self.assertIn(mode, ('day', 'night', 'dungeon'))


@unittest.skipUnless(DQ4.exists(), 'rom/dq4.nes 가 없음')
class RomWidthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from kr_patch.fc import ines
        cls.prg = ines.prg(DQ4.read_bytes())

    def test_widths_match_battle_dumps(self):
        """FC 전투 덤프의 $7385(무리마다 폭): スライム 2, 0D 3, 6D·6E 8."""
        self.assertEqual({m: C.fc_width(self.prg, m) for m in (0x00, 0x0D, 0x6D, 0x6E)},
                         {0x00: 2, 0x0D: 3, 0x6D: 8, 0x6E: 8})

    def test_wide_pictures_are_picture_numbers(self):
        """14:$9392 의 넷은 그림 번호다. 몬스터 7E 는 그림 6C 라 하나 더 넓고, 몬스터 58 은 그림 51 이라 넓히지 않는다."""
        import dq4fcsprite as S
        self.assertEqual(C.wide_pictures(self.prg), {0x58, 0x6C, 0x7E, 0x83})
        for mid, wide in ((0x7E, True), (0x58, False)):
            p = S.mon_pic(self.prg, mid)
            tiles, *_ = S.mon_stream(self.prg, p)
            base = 1 + max(pos[0] & 15 for pls, _ in tiles for h, pos in pls if h & 0x40)
            self.assertEqual(C.fc_width(self.prg, mid), base + wide)


if __name__ == '__main__':
    unittest.main()
