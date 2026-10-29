"""무리 조합 늘어놓기와 조각 합·줄마다 타일 합 한도(여유·걸리는 조합)를 원본 롬 없이 확인한다."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch as mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dq5monlimits as L  # noqa: E402
import dq5mongfx as M  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402

# 그림 0: 2x2 칸, 조각 1, 줄마다 타일 2. 그림 1: 4x4 칸, 조각 6, 줄마다 타일 4.
SHAPES = {0: (2, 2, 1, [2, 2]), 1: (4, 4, 6, [4, 4, 4, 4])}
FOUND = {((0, 8, 0),): 'a', ((0, 4, 0), (1, 1, 0)): 'b'}


def head(w, h):
    return {'float': False, 'raise': 0, 'w': w, 'h': h}


class Fakes:
    def __enter__(self):
        self.mocks = [mock('dq5monlimits.M.monster', side_effect=lambda rom, m: (m, [])),
                      mock('dq5monlimits.M.decode', side_effect=lambda rom, g: {'pieces': [None] * SHAPES[g][2], 'g': g}),
                      mock('dq5monlimits.M.band_counts', side_effect=lambda d: list(SHAPES[d['g']][3])),
                      mock('dq5monlimits.M.header', side_effect=lambda rom, g: head(*SHAPES[g][:2])),
                      mock('dq5monlimits.M.COUNT', 2)]
        for m in self.mocks:
            m.start()

    def __exit__(self, *exc):
        for m in self.mocks:
            m.stop()


class PlaceTests(unittest.TestCase):
    def test_cuts(self):
        slime = (head(2, 2), 1, [2, 2])
        # 줄 폭: 2 × 13 = 26 < 28, 14 째는 28 이라 잘림.
        self.assertEqual([k[1] for k in M.place([(0, 20, 0, *slime)])[0]], [13])
        # 조각 합: 40 × 2 = 80, 셋째 40 은 100 이 되어 잘림.
        big = (head(2, 2), 40, [2, 2])
        self.assertEqual([k[1] for k in M.place([(0, 1, 0, *big), (1, 1, 1, *big), (2, 1, 0x80, *big)])[0]], [1, 1, 0])
        # 줄마다 타일 합: 9 × 3 = 27, 넷째는 28 이라 놓지 않음(조각 한도까지 센 수는 4).
        wide = (head(2, 2), 1, [9, 9])
        kept, pieces, bands = M.place([(0, 4, 0, *wide)])
        self.assertEqual((kept[0][1], kept[0][5], pieces, bands[11], bands[12]), (3, 4, 4, 27, 27))


class LimitTests(unittest.TestCase):
    def test_budgets(self):
        with Fakes():
            got = L.budgets(None, FOUND)
        # 조각: 조각 목록 합이 가장 큰 b(7) 에 걸려 0. 줄: a 는 (27 - 16) // 8 = 1, b 는 (27 - 12) // 4 = 3.
        self.assertEqual(got[0], {'pieces': 0, 'bands': [1, 1], 'compositions': 2})
        self.assertEqual(got[1], {'pieces': 0, 'bands': [23, 23, 15, 15], 'compositions': 1})

    def test_losses(self):
        with Fakes():
            self.assertEqual(L.losses(None, {0: (1, [2, 2])}, found=FOUND), [])
            self.assertEqual(L.losses(None, {0: (1, [3, 3])}, found=FOUND), [])
            band = L.losses(None, {0: (1, [4, 4])}, found=FOUND)
            listed = L.losses(None, {0: (2, [2, 2])}, found=FOUND)
            missing = L.losses(None, {5: (1, [1])}, found=FOUND)
            swapped = L.losses(None, monsters={0: 1}, found=FOUND)
        self.assertEqual(band, [(((0, 8, 0),), [8], [6], 'a', '덜 놓임')])
        self.assertEqual([(x[3], x[4]) for x in listed], [('b', '조각 목록 8개 > 7개')])
        self.assertEqual([x[4] for x in missing], ['세는 조합에 나오지 않아 한도를 정할 수 없음'])
        self.assertEqual([x[3] for x in swapped], ['a'])   # 8 × 가로 4 칸이 줄 폭 28 을 넘음

    def test_compositions(self):
        data = bytearray(0x180000)
        events = [[0, 0x6A, 0xFF, 0xFF, 0xFF, 4, 0, 0, 0, 0, 0, 0, 0],
                  [0, 0xE7, 0xFF, 0xFF, 0xFF, 1, 0, 0, 0, 0, 0, 0, 0]]
        for g, raw in enumerate(events):
            at = lorom(L.EVENT_GROUPS + g * L.EVENT_SIZE)
            data[at:at + len(raw)] = bytes(raw)
        record = {'weights': [1, 1, 0, 0, 0, 1, 0, 0, 0, 0, 1], 'count_codes': [0] * 11,
                  'species_weights': [1, 0, 0], 'monsters': [0x10, 0x11, 0, 0, 0, 0x15, 0, 0, 0, 0], 'fixed_group': 3}
        with mock('dq5monlimits.AREA_COUNT', 1), mock('dq5monlimits.EVENT_COUNT', 2), \
                mock('dq5monlimits.area', return_value=record), \
                mock('dq5monlimits.count_range', side_effect=lambda rom, code: (1, 2) if code == 7 else (1, 1)), \
                mock('dq5monlimits.fixed_group', return_value=[(0x20, (1, 1), 1)]):
            found, skipped = L.compositions(Rom(bytes(data)))
        self.assertEqual(skipped, 1)
        self.assertEqual(len(found), 19)
        self.assertIn(((0x10, 2, 0), (0x11, 1, 0)), found)
        self.assertEqual(found[((0x15, 1, 0),)], '구역 00 칸 5')
        self.assertEqual(found[((0x20, 1, 1),)], '구역 00 칸 10')
        self.assertEqual(found[((0x6A, 3, 0),)], '이벤트 무리 00')


if __name__ == '__main__':
    unittest.main()
