import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dq4groupcheck as check  # noqa: E402

ROM = Path(__file__).resolve().parents[3] / "rom" / "dq4.nes"


@unittest.skipUnless(ROM.is_file(), "local source ROM not present")
class StoryHiddenTest(unittest.TestCase):
    def test_jail_flare_on_the_stair_is_story_hidden(self):
        # イムル jail 12/02: フレア stands on the stair (06,03) until event 30. The stair scene moves her off the map;
        # without that the group ROM's jail stair was never reached.
        import dq4npcport
        import dq4shop
        import dq4talk
        from kr_patch.fc import ines
        prg = ines.prg(ROM.read_bytes())
        self.assertIn((6, 3), check.exit_order(prg, 0x12, 2))
        routine = next(p for g, k, p in dq4shop.hide_routines(prg) if (g, k) == (0x12, 2))
        for night in (False, True):
            hidden, _ = dq4shop.predict_hidden(prg, routine, dq4npcport.fc_state(night, None, 1).ram)
            cells = {dq4talk.pos(r, night) for i, r in enumerate(dq4shop.slot_people(prg, 0x12, 2, night)) if i in hidden}
            self.assertIn((6, 3), cells)

    def test_no_place_routine_no_patch(self):
        from kr_patch.fc import ines
        prg = ines.prg(ROM.read_bytes())
        self.assertEqual(check.story_hidden_patch(prg, b"", 0x37, 1, 0x12, 1), "")


class PartTest(unittest.TestCase):
    """--part: 장면 단위를 몫으로 나누면 모은 것이 전체와 같고 겹치지 않는다."""

    UNITS = [(f"stair-3701-{i}", [{"TO": "37/01,0,0", "TEST": "up:32"}], {"map": "37/01"}) for i in range(9)] + \
        [("stair-3702-0", None, "walled in"), ("stair-3702-1", None, "behind a door 97"),
         ("exit-37", [{"TO": "37/00,0,0", "TEST": "down:32"}], {"field": [1, 2]}), (check.AREA, check.AREA, None)]

    def parts(self, units, n):
        return [check.part_scenes(units, (k, n)) for k in range(1, n + 1)]

    def test_parts_cover_units_once(self):
        for n in (1, 2, 3, 5, len(self.UNITS) + 2):
            got = [u[0] for part in self.parts(self.UNITS, n) for u in part]
            self.assertEqual(sorted(got), sorted(u[0] for u in self.UNITS), n)

    def test_area_and_skipped_stairs_land_in_one_part(self):
        # area 장면은 area-hop 의 상태를 이어 쓰므로 통째로 한 몫에만 있고, 건너뛴 계단(skipped)도 한 몫에만 적힌다.
        for n in (2, 3, 4):
            parts = self.parts(self.UNITS, n)
            self.assertEqual(sum(any(u[0] == check.AREA for u in p) for p in parts), 1)
            skipped = [u[0] for p in parts for u in p if u[1] is None]
            self.assertEqual(sorted(skipped), ["stair-3702-0", "stair-3702-1"])

    def test_skipped_weigh_nothing(self):
        # 몫마다 돌릴 무게(계단 1, area 4)가 고르게: 건너뛴 계단은 무게 0
        weight = [sum(check.AREA_WEIGHT if u[0] == check.AREA else 1 for u in p if u[1] is not None)
                  for p in self.parts(self.UNITS, 2)]
        self.assertEqual(sorted(weight), [7, 7])

    def test_none_is_every_unit(self):
        self.assertEqual(check.part_scenes(self.UNITS, None), self.UNITS)

    @unittest.skipUnless(ROM.is_file(), "local source ROM not present")
    def test_real_units_have_distinct_names_and_split_whole(self):
        from kr_patch.fc import ines
        prg = ines.prg(ROM.read_bytes())
        units = check.scene_units(prg, set(check.LINKS))
        names = [u[0] for u in units]
        self.assertEqual(len(names), len(set(names)))
        self.assertIn(check.AREA, names)
        got = [u[0] for part in self.parts(units, 3) for u in part]
        self.assertEqual(sorted(got), sorted(names))


if __name__ == "__main__":
    unittest.main()
