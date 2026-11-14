import math
import sys
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dq4people as P  # noqa: E402
import dq4peoplecolorcheck as c  # noqa: E402

SKIN, CLOTH = P.SKIN[1] + (255,), (200, 30, 30, 255)


def cell(eyes=((6, 8), (9, 8)), whites=((5, 8), (10, 8)), cloth=CLOTH):
    im = Image.new('RGBA', (16, 24))
    for y in range(4, 24):
        for x in range(4, 12):
            im.putpixel((x, y), SKIN if y < 12 else cloth)
    for x, y in eyes:
        for dy in (0, 1):
            im.putpixel((x, y + dy), P.INK + (255,))
    for x, y in whites:
        for dy in (0, 1):
            im.putpixel((x, y + dy), P.WHITE + (255,))
    return im


def views(**front):
    side = cell(eyes=((6, 8),), whites=((7, 8),))
    return {'down': [cell(**front)] * 2, 'left': [side] * 2, 'right': [side] * 2, 'up': [cell((), ())] * 2}


class EyeTests(unittest.TestCase):
    def test_a_one_by_two_dot_is_one_eye_and_a_white_beside_it_counts(self):
        self.assertEqual(c.eyes(cell()), (2, 2))
        self.assertEqual(c.eyes(cell(whites=())), (2, 0))
        self.assertEqual(c.eyes(cell(eyes=((6, 8),), whites=((5, 8),))), (1, 1))

    def test_front_needs_two_eyes_and_sides_one_each_with_whites(self):
        person = P.Person((1,), None, 'h901', '남자')
        self.assertEqual(c.eye_problems(person, views()), [])
        self.assertEqual(c.eye_problems(person, views(whites=())),
                         ['남자 down 0: 눈 2/2, 흰자 0/2', '남자 down 1: 눈 2/2, 흰자 0/2'])
        self.assertEqual(len(c.eye_problems(person, views(eyes=((6, 8),), whites=((5, 8),)))), 2)


class ColorTests(unittest.TestCase):
    def test_drift_is_the_distance_of_the_clothes_and_skips_the_shared_tones(self):
        cells = views()
        self.assertEqual(c.drift(cells, [CLOTH[:3]], {CLOTH[:3]: 0}), 0)
        self.assertAlmostEqual(c.drift(cells, [(0, 0, 0)], {CLOTH[:3]: 0}),
                               math.dist(P.lab(CLOTH[:3]), P.lab((0, 0, 0))))

    def test_only_heavy_people_fail_on_colour_and_the_worst_group_counts(self):
        heavy = P.Person((1,), None, 'h901', '왕', main=True)
        plain = P.Person((2,), None, 'h902', '남자')
        cells = {heavy: views(), plain: views()}
        placed = {heavy: (0, {CLOTH[:3]: 0}), plain: (1, {CLOTH[:3]: 0})}
        board = {(0x36, 0): [CLOTH[:3]], (0x37, 0): [(0, 0, 0)], (0x36, 1): [(0, 0, 0)]}
        problems, worst = c.check(cells, placed, board, {heavy: {0x36, 0x37}, plain: {0x36}})
        self.assertEqual(len(problems), 1)
        self.assertTrue(problems[0].startswith('왕: 색 거리'))
        self.assertGreater(worst['남자'], c.LIMIT)

    def test_hooded_people_are_not_asked_for_eyes(self):
        person = P.Person((1,), None, 'h901', next(iter(c.NO_EYES)))
        blank = {k: [cell((), ())] * 2 for k in ('down', 'left', 'right', 'up')}
        self.assertEqual(c.check({person: blank}, {}, {}, {})[0], [])


if __name__ == '__main__':
    unittest.main()
