"""Without a ROM, the entrance row order and the ルーラ list writes; with rom/dq4.nes and rom/dq5.sfc, the FC
destinations of the ported groups and their names."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dq4fieldtravel as travel  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
DQ4, DQ5 = ROOT / "rom" / "dq4.nes", ROOT / "rom" / "dq5.sfc"


class OrderTest(unittest.TestCase):
    def test_landing_row_leads_its_group(self):
        rows = [{"group": 0x36, "x": 328, "y": 92}, {"group": 0x36, "x": 329, "y": 92},
                {"group": 0x37, "x": 308, "y": 44}, {"group": 0x36, "x": 328, "y": 93}]
        out = travel.landing_rows(rows, [{"group": 0x36, "row": (328, 93)}])
        self.assertEqual(out[0], {"group": 0x36, "x": 328, "y": 93})
        self.assertEqual(sorted(map(str, out)), sorted(map(str, rows)))

    def test_list_slots(self):
        dq5 = bytearray(0x200000)
        o = travel.lorom(travel.RULER_LIST)
        dq5[o:o + travel.RULER_COUNT] = range(1, travel.RULER_COUNT + 1)
        (w,) = travel.writes(bytes(dq5), [{"slot": 1, "group": 0x36}])
        self.assertEqual(w["at"], "25:85D5")
        new = bytes.fromhex(w["hex"])
        self.assertEqual(new[1], 0x36)
        self.assertEqual(new[0], 1)
        self.assertEqual(new[2:], bytes(range(3, travel.RULER_COUNT + 1)))


@unittest.skipUnless(DQ4.exists() and DQ5.exists(), "rom/dq4.nes and rom/dq5.sfc")
class RomTest(unittest.TestCase):
    def test_destinations_land_below_an_entrance(self):
        import dq4groupbuild
        from kr_patch.fc import ines
        prg = ines.prg(DQ4.read_bytes())
        found = dq4groupbuild.doors(prg)
        dests = travel.destinations(prg, dq4groupbuild.LINKS, found)
        self.assertEqual([d["group"] for d in dests], [0x3D, 0x36, 0x37, 0x3C])
        bat = dests[1]
        self.assertEqual((bat["land"], bat["row"]), ((328, 94), (328, 93)))
        for d in dests:
            self.assertIn(d["row"], found[d["fc"]][0])

    def test_names_encode_as_dq5(self):
        dq5 = DQ5.read_bytes()
        # 0B's first name in the original ROM.
        self.assertEqual(travel.name_bytes(dq5, "ラインハット"), bytes([104, 67, 111, 91, 112, 85]))
        self.assertEqual(travel.name_bytes(dq5, "バトランド"), bytes([0x84, 91, 85, 104, 111, 0x84, 85]))
        with self.assertRaises(ValueError):
            travel.name_bytes(dq5, "漢")


if __name__ == "__main__":
    unittest.main()
