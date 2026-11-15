"""2장 필드 길 검사(dq4ch2fieldwalkcheck)의 길 찾기(롬 없이)와, rom/dq4.nes 가 있으면 길 구간 표.

헤드리스 실측은 배포 관문 가드 dq4-ch2-field-walk(sfc/dq4/guards.toml).
"""
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools'), str(HERE.parents[2] / 'fc' / 'dq4' / 'tools')]

import dq4ch2fieldwalkcheck as fw  # noqa: E402

ROM = HERE.parents[2] / 'rom' / 'dq4.nes'
TOKEN = re.compile(r'^(\d+,\d+|[a-z]+:\d+)$')


class RouteTests(unittest.TestCase):
    def test_fewest_steps_then_fewest_turns(self):
        free = {(x, y) for x in range(4) for y in range(4)} - {(1, 1), (2, 1)}
        path = fw.route(lambda b: b in free, (0, 0), {(3, 3)})
        self.assertEqual(len(path), 7)
        self.assertEqual(fw.corners(path), '6,1;6,7' if path[1] == (1, 0) else '0,7;6,7')

    def test_avoided_blocks_cost_more(self):
        free = {(x, y) for x in range(3) for y in range(3)}
        path = fw.route(lambda b: b in free, (0, 1), {(2, 1)}, avoid={(1, 1)})
        self.assertNotIn((1, 1), path)

    def test_no_way(self):
        self.assertIsNone(fw.route(lambda b: False, (0, 0), {(2, 0)}))

    def test_corners_are_stand_cells_of_turns_and_end(self):
        self.assertEqual(fw.corners([(0, 0), (1, 0), (2, 0), (2, 1), (2, 2)]), '4,1;4,5')


@unittest.skipUnless(ROM.exists(), 'rom/dq4.nes')
class TableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from kr_patch.fc import ines
        cls.prg = ines.prg(ROM.read_bytes())
        cls.table = fw.segments(cls.prg)

    def test_every_leg_is_its_own_unit_after_its_event(self):
        names = [s[0] for s in self.table]
        self.assertEqual(len(names), len(set(names)))
        firsts = [names[u[0]] for u in fw.chosen_units(self.table)]
        self.assertEqual(sorted(firsts), sorted([f'{n}_side' for n, *_ in fw.LEGS] + list(fw.REUSED)))
        for name, after, *_ in fw.LEGS:
            self.assertLess(names.index(after), names.index(f'{name}_side'), name)
            # 길 구간은 flag 를 켜거나 끄지 않는다
            for seg in self.table:
                if seg[0].startswith(name + '_'):
                    self.assertFalse({'want', 'off'} & seg[3].keys(), seg[0])

    def test_walk_tokens(self):
        for name, how, arg, opt in self.table:
            if how == 'walk' and name.startswith('road_'):
                for tok in arg.split(';'):
                    self.assertRegex(tok, TOKEN, name)

    def test_tempe_north_exit_stands_above_the_entrance(self):
        seg = next(s for s in self.table if s[0] == 'road_frenol_0_out')
        self.assertTrue(seg[2].endswith(';up:16'))
        self.assertEqual(seg[3]['cell'], (0x47 * 2, 0x38 * 2 + 1))

    def test_field_roads_end_on_the_next_entrance(self):
        ents = fw.entrance_blocks(self.prg)
        for name, how, arg, opt in self.table:
            if name.startswith('road_') and name.endswith('_in'):
                x, y = map(int, arg.split(';')[-1].split(','))
                self.assertIn((x // 2, y // 2), ents, name)


if __name__ == '__main__':
    unittest.main()
