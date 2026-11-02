import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
for path in (TOOLS, TOOLS.parents[1] / "dq5" / "tools", TOOLS.parents[2] / "fc" / "dq4" / "tools"):
    sys.path.insert(0, str(path))

from dq4dungeonencountercheck import SONG_STARTING, song_held  # noqa: E402

FF = SONG_STARTING


class SongHeldTest(unittest.TestCase):
    def test_gap_before_the_song_starts(self):
        # Original DQ5 walks its tower 04/00 and cave 07/02 with FF steps before the song starts.
        self.assertTrue(song_held([[FF, FF, FF, 0x0A, 0x0A]], 0x0A))
        self.assertTrue(song_held([[FF, 0x09, 0x09], [FF, 0x09], [0x09]], 0x09))
        self.assertTrue(song_held([[0x09], []], 0x09))

    def test_song_must_hold_once_started(self):
        self.assertFalse(song_held([[0x09, FF, 0x09]], 0x09))
        self.assertFalse(song_held([[FF, 0x09, 0x02]], 0x09))

    def test_other_song_or_none(self):
        self.assertFalse(song_held([[0x02, 0x09]], 0x09))
        self.assertFalse(song_held([[FF, FF]], 0x09))
        self.assertFalse(song_held([[], []], 0x09))


if __name__ == "__main__":
    unittest.main()
