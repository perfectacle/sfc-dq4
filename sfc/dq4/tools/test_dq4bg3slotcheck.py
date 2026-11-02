import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path[:0] = [str(TOOLS), str(TOOLS.parents[1] / "dq5" / "tools")]

import dq4bg3slotcheck as check  # noqa: E402


def line(mp, slot, shown=None, nz=342, vsbuf=0):
    return check.parse_bg3(f"f00630 map {mp} 0725={slot:02X} shown={slot if shown is None else shown:02X} "
                           f"nz={nz} vsbuf={vsbuf} old=660")


class JudgeTest(unittest.TestCase):
    def test_expected_slot(self):
        self.assertEqual(check.expected_slot("02/00"), 0x3C)
        self.assertEqual(check.expected_slot("01/01"), 0x7C)
        self.assertEqual(check.expected_slot("00/0A"), 0x78)
        self.assertEqual(check.expected_slot("19/00"), 0x48)
        self.assertEqual(check.expected_slot("19/02"), 0x4C)

    def test_moved_slot_passes(self):
        self.assertEqual(check.judge("01/00", True, line("01/00", 0x7C)), [])
        self.assertEqual(check.judge("17/00", True, line("17/00", 0x3C)), [])

    def test_unmoved_or_broken_slot_fails(self):
        # A ROM without the move keeps the menu's 1C, as the overture stage does.
        self.assertTrue(check.judge("02/00", True, line("02/00", 0x1C)))
        self.assertTrue(check.judge("02/00", True, line("02/00", 0x3C, shown=0x1C)))
        self.assertTrue(check.judge("02/00", True, line("02/00", 0x3C, nz=0)))
        self.assertTrue(check.judge("02/00", True, line("02/00", 0x3C, vsbuf=2)))

    def test_not_arrived_fails(self):
        self.assertEqual(check.judge("17/00", False, line("17/00", 0x3C)), ["도착 못 함"])
        self.assertTrue(check.judge("17/00", True, line("01/01", 0x7C)))
        self.assertTrue(check.judge("17/00", True, None))

    def test_start_map_goes_through_another_slot(self):
        mp = check.HOP.split(",")[0]
        self.assertNotEqual(check.expected_slot(mp), check.expected_slot(check.START_MAP["ship"]))


if __name__ == "__main__":
    unittest.main()
