from types import SimpleNamespace
import unittest

import dq4nameentry as ne


class NavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        atlas = SimpleNamespace(run=lambda text, font=None: (1, 2))
        _, cls.keys = ne.board_record(atlas, bytes(6), object(), 0x9F)
        cls.moves = ne.navigation(cls.keys)

    def index(self, key):
        code = ne.JAMO.index(key) if isinstance(key, str) else key
        return self.keys.index(code)

    def assert_move(self, key, direction, expected):
        offset = ('up', 'down', 'left', 'right').index(direction) * len(self.keys)
        self.assertEqual(self.moves[offset + self.index(key)], self.index(expected))

    def test_horizontal_edges_wrap_within_each_row(self):
        self.assertEqual(self.moves[2 * len(self.keys)], 9)
        self.assertEqual(self.moves[3 * len(self.keys) + 9], 0)
        for key, direction, expected in [('ㅂ', 'left', ne.BACK), (ne.BACK, 'right', 'ㅂ'),
                                         ('ㅋ', 'left', 'ㅡ'), ('ㅡ', 'right', 'ㅋ')]:
            with self.subTest(key=key, direction=direction):
                self.assert_move(key, direction, expected)

    def test_horizontal_holes_are_skipped(self):
        for key, direction, expected in [('ㅆ', 'right', 'ㅒ'), ('ㅒ', 'left', 'ㅆ'),
                                         ('ㅣ', 'right', ne.DONE), (ne.DONE, 'left', 'ㅣ')]:
            with self.subTest(key=key, direction=direction):
                self.assert_move(key, direction, expected)

    def test_vertical_moves_keep_the_column(self):
        for key, direction, expected in [('ㅃ', 'down', 'ㅂ'), ('ㄷ', 'down', 'ㅇ'),
                                         ('ㅇ', 'down', 'ㅊ'), ('ㅊ', 'up', 'ㅇ'),
                                         (ne.BACK, 'down', ne.DONE), (ne.DONE, 'up', ne.BACK)]:
            with self.subTest(key=key, direction=direction):
                self.assert_move(key, direction, expected)

    def test_vertical_edges_stay_put_instead_of_wrapping(self):
        for key, direction in [('ㅃ', 'up'), ('ㅋ', 'down'), ('ㅛ', 'up'), ('ㅔ', 'down'),
                               ('ㅏ', 'down'), (ne.BACK, 'up'), (ne.DONE, 'down')]:
            with self.subTest(key=key, direction=direction):
                self.assert_move(key, direction, key)

    def test_vertical_moves_skip_an_empty_row_in_the_column(self):
        keys = self.keys.copy()
        keys[self.index('ㅁ')] = ne.NONE
        moves = ne.navigation(keys)
        self.assertEqual(moves[len(keys) + self.index('ㅂ')], self.index('ㅋ'))
        self.assertEqual(moves[self.index('ㅋ')], self.index('ㅂ'))

    def test_every_selectable_cell_has_valid_aligned_neighbors(self):
        self.assertEqual(len(self.moves), 4 * len(self.keys))
        for direction in range(4):
            for source, key in enumerate(self.keys):
                if key == ne.NONE:
                    continue
                with self.subTest(direction=direction, source=source):
                    target = self.moves[direction * len(self.keys) + source]
                    self.assertGreaterEqual(target, 0)
                    self.assertLess(target, len(self.keys))
                    self.assertNotEqual(self.keys[target], ne.NONE)
                    if direction < 2:
                        self.assertEqual(target % ne.ROW_CELLS, source % ne.ROW_CELLS)
                    else:
                        self.assertEqual(target // ne.ROW_CELLS, source // ne.ROW_CELLS)


if __name__ == '__main__':
    unittest.main()
