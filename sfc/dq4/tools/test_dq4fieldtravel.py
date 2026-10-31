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
        w, *_ = travel.writes(bytes(dq5), [{"slot": 1, "group": 0x36, "ship": None}])
        self.assertEqual(w["at"], "25:85D5")
        new = bytes.fromhex(w["hex"])
        self.assertEqual(new[1], 0x36)
        self.assertEqual(new[0], 1)
        self.assertEqual(new[2:], bytes(range(3, travel.RULER_COUNT + 1)))

    def test_ship_offsets(self):
        dq5 = bytearray(0x200000)
        for table in travel.SHIP_OFFSETS:
            o = travel.lorom(table)
            dq5[o:o + 2 * travel.SHIP_SLOTS] = b"\x07" * (2 * travel.SHIP_SLOTS)
        dests = [{"slot": 1, "group": 0x36, "land": (328, 94), "ship": (315, 67)},
                 {"slot": 2, "group": 0x37, "land": (308, 46), "ship": None}]
        _, *tables = travel.writes(bytes(dq5), dests)
        self.assertEqual([t["at"] for t in tables], ["23:E41E", "23:E438"])
        for t in tables:
            new = bytes.fromhex(t["hex"])
            self.assertEqual(new[2:4], bytes((-13 & 0xFF, -27 & 0xFF)))
            self.assertEqual(new[4:6], b"\x07\x07")
        with self.assertRaises(ValueError):
            travel.writes(bytes(dq5), [{"slot": 1, "group": 0x36, "name": "x", "land": (0, 0), "ship": (200, 0)}])

    def test_ship_cell_boards_from_above_or_below(self):
        # FC block (10,10) is sea with land only to its left (09,10) and above (10,0F).
        def props(x, y):
            return 0x00 if (x, y) in ((0x09, 0x10), (0x10, 0x0F)) else travel.SEA
        self.assertEqual(travel.ship_cell(props, (0x10, 0x10), (0, 0)), (0x20, 0x20))
        self.assertIsNone(travel.ship_cell(props, (0, 0), (0, 0)))
        with self.assertRaises(ValueError):
            travel.ship_cell(props, (0x09, 0x10), (0, 0))

    def test_names_encode_as_dq5(self):
        # Made-up tables: single bytes 10 ハ, 11 ト, 12 り; mark entry 5 バ (84 + key 10), entry 28 パ (83 + key 10).
        # Every other entry is code 0, the blank, which no name uses. Mark entries 0-3 are also single bytes 7F-82
        # (the tables touch), so バ takes entry 5.
        import dq5text
        from dq5map import lorom
        chars = "".join(dq5text.CHARS)
        dq5 = bytearray(0x200000)

        def code(at, c):
            dq5[lorom(at):lorom(at) + 2] = chars.index(c).to_bytes(2, "little")

        for b, c in ((0x10, "ハ"), (0x11, "ト"), (0x12, "り")):
            code(dq5text.STRING_CODES + b * 2, c)
        for k, c in ((5, "バ"), (0x28, "パ")):
            code(dq5text.MARK_CODES + k * 2, c)
            dq5[lorom(dq5text.MARK_KEYS + k)] = 0x10
        dq5 = bytes(dq5)
        self.assertEqual(travel.name_bytes(dq5, "ハトバ"), bytes([0x10, 0x11, 0x84, 0x10]))
        self.assertEqual(travel.name_bytes(dq5, "パはリ"), bytes([0x83, 0x10, 0x10, 0x12]))
        with self.assertRaises(ValueError):
            travel.name_bytes(dq5, "ラ")

    def test_ship_cell_keeps_sea_on_its_right(self):
        # 바다 블록 (10,10) 은 오른쪽 (11,10)·아래 (10,11) 이 땅이다. 내리는 칸이 오른쪽이어도 왼쪽 칸을 고른다.
        def props(x, y):
            return 0x00 if (x, y) in ((0x11, 0x10), (0x10, 0x11)) else travel.SEA
        self.assertEqual(travel.ship_cell(props, (0x10, 0x10), (0x40, 0x40)), (0x20, 0x21))


@unittest.skipUnless(DQ4.exists() and DQ5.exists(), "rom/dq4.nes and rom/dq5.sfc")
class RomTest(unittest.TestCase):
    def test_destinations_land_below_an_entrance(self):
        import dq4groupbuild
        from kr_patch.fc import ines
        prg = ines.prg(DQ4.read_bytes())
        found = dq4groupbuild.doors(prg)
        dests = travel.destinations(prg, dq4groupbuild.LINKS, found)
        # FC destination order: キングレオ, サントハイム, バトランド, エンドール, ボンモール, ブランカ, ハバリア, イムル,
        # たびだちのむら, モンバーバラ, レイクナバ, コーミズ.
        self.assertEqual([d["group"] for d in dests], [0x44, 0x3D, 0x36, 0x40, 0x3F, 0x46, 0x43, 0x37, 0x3C, 0x41, 0x3E,
                                                          0x42])
        bat = dests[2]
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
