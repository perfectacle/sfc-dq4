"""Without a ROM, the FC -> DQ5 cell rule; with rom/dq4.nes, the exit and area records of the new groups."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dq4groupbuild as build  # noqa: E402

ROM = Path(__file__).resolve().parents[3] / "rom" / "dq4.nes"


class CellTest(unittest.TestCase):
    def test_stands_on_bottom_left_cell(self):
        self.assertEqual(build.cell(0x0F, 0x23), (30, 71))
        self.assertEqual(build.cell(0, 0), (0, 1))


@unittest.skipUnless(ROM.is_file(), "local source ROM not present")
class RecordsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from kr_patch.fc import ines
        cls.prg = ines.prg(ROM.read_bytes())

    def test_stairs_lead_back(self):
        records = {}
        for group in build.LINKS:
            records.update(build.exit_records(self.prg, group))
        for name, rows in records.items():
            group, number = int(name[:2], 16), int(name[3:], 16)
            for i, row in enumerate(rows):
                if row["kind"] == "special":
                    continue
                there = row.get("group", group)
                back = records[f"{there:02X}/{row['destination_map']:02X}"][row["exit"]]
                self.assertEqual((back.get("group", there), back["destination_map"], back["exit"]), (group, number, i),
                                 f"{name} exit {i}")

    def test_area_rects_are_one_row(self):
        areas = {}
        for group in build.LINKS:
            areas.update(build.area_records(self.prg, group))
        self.assertEqual(sorted(areas), ["36/00", "36/01"])
        for rows in areas.values():
            for row in rows:
                x0, y0, x1, y1 = row["rect"]
                self.assertEqual(y1 - y0, 1)
                self.assertEqual(row["span_raw"], x1 - x0)
        # 02/00's castle door is entered walking up (bottom row of its FC cell), 02/01's exit below the
        # map is entered walking down (top row of the first outside FC row).
        self.assertEqual(areas["36/00"][0]["rect"], [36, 21, 39, 22])
        self.assertEqual(areas["36/01"][0]["rect"], [30, 72, 33, 73])


if __name__ == "__main__":
    unittest.main()
