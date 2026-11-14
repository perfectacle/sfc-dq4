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


if __name__ == "__main__":
    unittest.main()
