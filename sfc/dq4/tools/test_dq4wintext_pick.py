"""글자 읽기의 고르기 차례: 덮는 점이 많은 글자부터 받는다. 줄 점수가 높은 다른 글꼴 읽기의 작은 부호가 큰 글자의 일부를
먼저 가져가 큰 글자를 버리지 않게."""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dq4wintext as wt  # noqa: E402


def cols(rows):
    """줄 목록('#.') → 열 무늬(줄 k = bit k)."""
    return tuple(sum(1 << k for k, row in enumerate(rows) if row[x] == '#') for x in range(len(rows[0])))


A = ['####', '####', '####', '####', '....', '....']
DASH = ['...', '...', '...', '...', '...', '###']
# 바닥이 긴 L: 오른쪽 네 열은 바닥 점뿐이라 작은 글꼴의 「-」 가 그 열에 맞는다
X = ['##....', '##....', '##....', '##....', '##....', '######']
TABLES = {'small': {4: {cols(A): 'a'}, 3: {cols(DASH): '-'}}, 'big': {6: {cols(X): 'X'}}}
WIDTH = {'a': 4, '-': 3, 'X': 6}


class PickTest(unittest.TestCase):
    def test_bigger_glyph_wins_over_a_small_sign_from_a_higher_scored_reading(self):
        # 줄 「aaaa X」: 작은 글꼴 읽기(a 넷 + X 바닥의 -)가 큰 글꼴 읽기(X 하나 + a 자리 못 읽음)보다 줄 점수가 높다
        width = 8 + 5 * 5 + 6 + 8
        grid = [[0] * width for _ in range(24)]
        for k in range(4):
            for y, row in enumerate(A):
                for x, v in enumerate(row):
                    if v == '#':
                        grid[8 + y][8 + k * 5 + x] = 1
        for y, row in enumerate(X):
            for x, v in enumerate(row):
                if v == '#':
                    grid[8 + y][8 + 4 * 5 + x] = 1
        with mock.patch.object(wt, 'FONTS', ('small', 'big')), \
                mock.patch.object(wt, 'glyph_table', lambda name: TABLES[name]), \
                mock.patch.object(wt, 'band_height', lambda name: 6), \
                mock.patch.object(wt, 'width', lambda name, ch: WIDTH[ch]), \
                mock.patch.object(wt, 'BAND', 6):
            screen = mock.Mock(_covered={}, engine_rects=[(0, 0, 2, 5)])
            got = wt._read(screen, (0, 0, 2, 5), {}, grid, {})
        self.assertEqual([ln.text.replace(' ', '') for ln in got], ['aaaaX'])


if __name__ == '__main__':
    unittest.main()
