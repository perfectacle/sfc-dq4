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

    def test_obj_lines(self):
        """14:$9ADD: 8줄 창마다 놓은 OAM 과 이 무리 OBJ 가 8 개까지. 넘는 마리부터 빼고, 한 마리도 안 되면 0."""
        ys = [0x60, 0x62, 0x70]
        self.assertEqual(C._obj_lines([], ys, 8), (4, 'OBJ 줄'))
        self.assertEqual(C._obj_lines([], ys, 3), (3, None))
        self.assertEqual(C._obj_lines([0x61] * 7, ys, 2), (0, 'OBJ 줄'))
        self.assertEqual(C._obj_lines([0x61] * 6, ys, 2), (1, 'OBJ 줄'))
        self.assertEqual(C._obj_lines([0xA0] * 62, ys, 1), (0, 'OBJ 합'))
        self.assertEqual(C._obj_lines([0x60] * 8, [], 5), (5, None))

    def test_palettes(self):
        """14:$9439·$93F2: 같은 3색은 칸을 함께 쓰고, BG 칸 0 은 장소 색 30 과 첫 색 30 인 팔레트 하나에만 열린다."""
        FF = C.FF
        obj = [[1, 2, 3], [4, 5, 6], [FF] * 3, [FF] * 3]
        self.assertTrue(C._palettes_fit(obj, [[1, 2, 3], [7, 8, 9], [9, 9, 9]]))
        self.assertFalse(C._palettes_fit(obj, [[7, 8, 9], [9, 9, 9], [6, 6, 6]]))
        bg = [[0x30, FF, FF], [1, 1, 1], [2, 2, 2], [3, 3, 3]]
        self.assertTrue(C._bg_fits(bg, [[0x30, 5, 6]]))
        self.assertFalse(C._bg_fits(bg, [[0x0F, 5, 6]]))
        self.assertFalse(C._bg_fits(bg, [[0x30, 5, 6], [7, 7, 7]]))
        self.assertFalse(C._bg_fits([[0x26, FF, FF]] + bg[1:], [[0x30, 5, 6]]))
        C._commit(bg, [[0x30, 5, 6]], True, 0x30)
        self.assertEqual(bg[0], [0x30, 5, 6])
        self.assertTrue(C._bg_fits(bg, [[0x30, 5, 6]]))
        self.assertFalse(C._bg_fits(bg, [[0x30, 5, 7]]))

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


class _Stop(Exception):
    pass


def fc_code(prg, groups):
    """FC 14:$812F 를 dq4cpu 로 무리 고르기 끝($81BD)까지 돌려 남은 무리 [(몬스터, 놓인 수)]($6E45·$6E49)."""
    import dq4cpu
    cpu = dq4cpu.CPU(prg, 0x14)
    cpu.stubs |= {0xFF74}

    def stop(c):
        if c.bank == 0x14:
            raise _Stop

    cpu.hooks[0x81BD] = stop
    cpu.ram[0x514] = C.SHARED_BG
    for i in range(C.GROUPS):
        m, n = groups[i] if i < len(groups) else (0xFF, 0)
        cpu.wram[0x0E45 + i], cpu.wram[0x0E49 + i] = m, n
    try:
        cpu.call(0x812F, limit=5_000_000)
    except _Stop:
        pass
    return [(m, n) for m, n in zip(cpu.wram[0x0E45:0x0E49], cpu.wram[0x0E49:0x0E4D]) if m != 0xFF]


# FC 전투 덤프(fc/dq4/tools/lua/spritebattle.lua, 1장 필드에서 MON 으로 무리를 덮음)의 $6E45·$6E49
BATTLE_DUMPS = {
    ((0x00, 8),): [(0x00, 8)], ((0x6E, 8),): [(0x6E, 3)], ((0x00, 1), (0x6E, 7)): [(0x00, 1), (0x6E, 3)],
    ((0x6E, 3), (0x00, 5), (0x05, 2)): [(0x6E, 3), (0x00, 1)], ((0x0D, 7),): [(0x0D, 7)], ((0x6D, 3),): [(0x6D, 1)],
    # 2장 구역 08·09·0B·0C·4C·4D·4E·4F 의 조합
    ((0x07, 6),): [(0x07, 6)], ((0x1A, 1), (0x11, 1), (0x0D, 1)): [(0x1A, 1), (0x11, 1)],
    ((0x1C, 2), (0x1A, 1), (0x11, 1)): [(0x1C, 2), (0x1A, 1)], ((0x1A, 7),): [(0x1A, 5)], ((0x28, 7),): [(0x28, 6)],
    ((0x20, 2), (0x20, 2)): [(0x20, 2), (0x20, 2)], ((0x48, 2), (0x48, 1), (0x46, 1)): [(0x48, 2), (0x46, 1)],
    ((0x46, 3), (0x14, 8)): [(0x46, 3), (0x14, 4)], ((0x46, 2), (0x14, 8)): [(0x46, 2), (0x14, 6)],
    ((0x48, 3),): [(0x48, 2)], ((0x1F, 7),): [(0x1F, 4)], ((0x11, 5),): [(0x11, 5)],
    ((0x1D, 2), (0x1D, 2)): [(0x1D, 2)], ((0x25, 7),): [(0x25, 4)], ((0x33, 7),): [(0x33, 4)],
    ((0x40, 2), (0x40, 1), (0x38, 1)): [(0x40, 2), (0x40, 1), (0x38, 1)], ((0x3E, 2), (0x3E, 2)): [(0x3E, 2), (0x3E, 2)],
}


@unittest.skipUnless(DQ4.exists(), 'rom/dq4.nes 가 없음')
class RomFcBattleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from kr_patch.fc import ines
        cls.prg = ines.prg(DQ4.read_bytes())
        cls.battle = C.FcBattle(cls.prg)

    def kept(self, groups):
        shown, _ = self.battle.place(groups)
        return [(m, k) for (m, _), k in zip(groups, shown) if k]

    def test_place_matches_battle_dumps(self):
        for groups, want in BATTLE_DUMPS.items():
            self.assertEqual(self.kept(list(groups)), want, groups)

    def test_place_matches_fc_code(self):
        """2장 조합(한도마다)과 무작위 조합에서 place 가 FC 코드를 돌린 결과와 같다."""
        cases = [[(0x1A, 1), (0x11, 1), (0x0D, 1)], [(0x48, 2), (0x48, 1), (0x46, 1)], [(0x46, 2), (0x14, 8)],
                 [(0x1D, 4)], [(0x1F, 7)], [(0x25, 7)], [(0x46, 3), (0x14, 8)], [(0x33, 7)]]
        import dq4fcsprite as S
        mons = [m for m in range(0xC3) if S.mon_pic(self.prg, m) not in C.UNCOUNTED]
        rng = random.Random(3)
        cases += [[(rng.choice(mons), rng.randint(1, 8)) for _ in range(rng.randint(1, 4))] for _ in range(24)]
        for groups in cases:
            self.assertEqual(self.kept(groups), fc_code(self.prg, groups), groups)

    def test_limits_reported(self):
        """1~3장에서 FC 를 깎는 한도: OBJ 줄(48 셋째 무리), BG 팔레트(0D 셋째 무리), 폭, 합 8."""
        self.assertEqual(self.battle.place([(0x48, 2), (0x48, 1), (0x46, 1)]), ([2, 0, 1], [None, 'OBJ 줄', None]))
        self.assertEqual(self.battle.place([(0x1A, 1), (0x11, 1), (0x0D, 1)]), ([1, 1, 0], [None, None, 'BG 팔레트']))
        self.assertEqual(self.battle.place([(0x1A, 7)]), ([5], ['폭']))
        self.assertEqual(self.battle.place([(0x46, 2), (0x14, 8)]), ([2, 6], [None, '합 8']))


if __name__ == '__main__':
    unittest.main()
