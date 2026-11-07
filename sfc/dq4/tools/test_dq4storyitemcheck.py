"""The story item check's input must not depend on the frame phase the warp arrives with."""

import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
for path in (TOOLS, TOOLS.parents[1] / "dq5" / "tools", TOOLS.parents[2] / "fc" / "dq4" / "tools"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import dq4storyitemcheck  # noqa: E402


def tokens(text):
    return [tuple(t.split(":")) for t in text.split(",")]


class InputTest(unittest.TestCase):
    def test_field_press_waits_for_window(self):
        # The field reads the pad once every 8 frames. A fixed 6-frame A after the warp opened the command window only
        # on some arrival phases: one frame later and all three items ran no handler.
        presses = [t for t in tokens(dq4storyitemcheck.INPUT) if t[0] != "wait"]
        self.assertEqual(presses[0][0], "open")
        self.assertGreaterEqual(int(presses[0][1]), 16)

    def test_lua_knows_open(self):
        lua = dq4storyitemcheck.USE.read_text()
        self.assertIn('btn == "open"', lua)
        self.assertIn("0x7E0A00", lua)


if __name__ == "__main__":
    unittest.main()
