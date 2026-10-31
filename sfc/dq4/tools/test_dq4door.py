import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dq4balance  # noqa: E402
import dq4door as door  # noqa: E402
import dq4environmentrom  # noqa: E402


def mark(dx, dy):
    """The one cell of a 2x3 door entry (dx, dy) that holds its kind: bottom-right."""
    return dx + 1, dy + 2


def found(hero, facing, door_at):
    x, y = hero
    return any((x + ox, y + oy) == mark(*door_at) for ox, oy in door.OFFSETS[facing])


class FindTest(unittest.TestCase):
    def test_original_cell_first(self):
        # 01:DA4D looked only at (X+1, Y-1) up and (X+1, Y+1) down; those stay first.
        self.assertEqual(door.OFFSETS["up"][0], (1, -1))
        self.assertEqual(door.OFFSETS["down"][0], (1, 1))

    def test_half_a_block(self):
        # Door entry (42,37) of 37/00 (cells 42-43, 37-39); the hero stands with its top-left cell below the mark.
        self.assertTrue(found((42, 40), "up", (42, 37)))
        self.assertTrue(found((43, 40), "up", (42, 37)))   # half a block right: missed before
        self.assertTrue(found((41, 40), "up", (42, 37)))   # half a block left
        self.assertFalse(found((44, 40), "up", (42, 37)))

    def test_side(self):
        # Beside a door in a side wall, on its bottom row (FC block row fy: 2fy+1 = entry y + 2).
        self.assertTrue(found((40, 39), "right", (42, 37)))
        self.assertTrue(found((44, 39), "left", (42, 37)))
        self.assertFalse(found((44, 41), "left", (42, 37)))

    def test_code(self):
        find, labels = door.find_code()
        self.assertEqual(labels["find"], door.FIND_AT)
        self.assertGreater(door.FIND_AT, dq4balance.REWARD_AT + len(dq4balance.code()[0]))
        # The table index of each direction points at its offsets, which end in 80 80.
        base = labels["offsets"] - door.FIND_AT
        for direction, offsets in door.OFFSETS.items():
            i = find[labels[f"y_{direction}"] - door.FIND_AT]
            pairs = find[base + i:base + i + 2 * len(offsets) + 2]
            self.assertEqual(list(pairs[:-2]), [v & 0xFF for o in offsets for v in o])
            self.assertEqual(pairs[-2:], b"\x80\x80")
        auto, labels = door.auto_code()
        self.assertEqual(labels["auto"], door.AUTO_AT)
        self.assertLessEqual(door.AUTO_AT + len(auto), door.AUTO_END)
        self.assertEqual(dq4environmentrom.HOOK_END, door.AUTO_AT)

    def test_writes(self):
        w = {x["at"]: x for x in door.writes()}
        self.assertEqual(w["01:DA4D"]["orig"], "20 2D F0 10 04")
        self.assertEqual(w["01:DA4D"]["hex"], "22 00 F4 57 60")
        self.assertEqual(w["00:81B7"]["orig"], "20 B4 83 9C 5A 19")
        self.assertEqual(w["00:81B7"]["hex"], "22 00 FF 01 EA EA")
        self.assertEqual(w["00:880E"], {"at": "00:880E", "hex": "6B", "orig": "6B", "note": w["00:880E"]["note"]})

    def test_without_auto(self):
        saved = door.AUTO_OPEN
        try:
            door.AUTO_OPEN = False
            self.assertEqual({x["at"] for x in door.writes()}, {"57:F400", "01:DA4D"})
        finally:
            door.AUTO_OPEN = saved


if __name__ == "__main__":
    unittest.main()
