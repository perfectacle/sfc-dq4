import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
for path in (TOOLS, TOOLS.parents[1] / "dq5" / "tools", TOOLS.parents[2] / "fc" / "dq4" / "tools"):
    sys.path.insert(0, str(path))

from dq4dungeonencountercheck import SONG_START_FRAMES, SONG_STARTING, song_held  # noqa: E402

FF = SONG_STARTING


def visit(request, *songs, start=None, every=8):
    """A visit whose steps come every `every` frames from `start` (default 78 frames after the request)."""
    first = (request if request is not None else 0) + 78 if start is None else start
    return {"request": request, "steps": [[first + i * every, s] for i, s in enumerate(songs)]}


class SongHeldTest(unittest.TestCase):
    def test_gap_before_the_song_starts(self):
        # Original DQ5 tower 04/00: request 610, FF steps 692..716, song 0A from 724.
        self.assertTrue(song_held([visit(610, FF, FF, FF, FF, 0x0A, 0x0A)], 0x0A))
        self.assertTrue(song_held([visit(330, FF, 0x09, 0x09), visit(579, FF, 0x09), visit(772, 0x09)], 0x09))

    def test_every_visit_must_hear_the_song(self):
        self.assertFalse(song_held([visit(330, 0x09), visit(579, FF, FF)], 0x09))
        self.assertFalse(song_held([visit(330, 0x09), visit(579)], 0x09))
        self.assertFalse(song_held([visit(330, FF, 0x09), visit(579, FF), visit(772, FF, FF)], 0x09))
        self.assertFalse(song_held([], 0x09))

    def test_song_must_hold_once_started(self):
        self.assertFalse(song_held([visit(330, 0x09, FF, 0x09)], 0x09))
        self.assertFalse(song_held([visit(330, FF, 0x09, 0x02)], 0x09))
        self.assertFalse(song_held([visit(330, 0x02, 0x09)], 0x09))

    def test_gap_is_bounded(self):
        late = 330 + SONG_START_FRAMES + 1
        self.assertTrue(song_held([visit(330, FF, 0x09, start=330 + SONG_START_FRAMES)], 0x09))
        self.assertFalse(song_held([visit(330, FF, 0x09, start=late)], 0x09))
        # Steps with no song request before them in the map have no gap to allow.
        self.assertFalse(song_held([visit(None, FF, 0x09)], 0x09))
        self.assertTrue(song_held([visit(None, 0x09, 0x09)], 0x09))


if __name__ == "__main__":
    unittest.main()
