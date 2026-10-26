"""SPC 실측 비교에서 곡 시작·샘플 도착 기록을 읽고 도착 전 음을 빼는지 검사한다."""
import tempfile
from pathlib import Path
import unittest

import dq4soundcheck as check


class EventTests(unittest.TestCase):
    def read(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'events.txt'
            path.write_text(text)
            return check.read_events(path)

    def test_started_frame_and_last_arrival(self):
        start, arrivals = self.read('song 17 started at frame 209\nsample 3F slot 0A at frame 254\n'
                                    'sample 40 slot 0B at frame 260\nsample 40 slot FF at frame 300\n'
                                    'song 17 on at frame 449\n')
        self.assertEqual(start, 209)
        self.assertEqual(arrivals, {0x3F: 254})

    def test_old_runs_use_song_on_frame(self):
        self.assertEqual(self.read('song 02 on at frame 246\n'), (246, {}))

    def test_blocked_only_before_arrival(self):
        arrivals = {0x3F: 254}
        self.assertTrue(check.blocked(0.5, 0x3F, 209, arrivals))
        self.assertFalse(check.blocked(1.0, 0x3F, 209, arrivals))
        self.assertFalse(check.blocked(0.0, 0x39, 209, arrivals))


if __name__ == '__main__':
    unittest.main()
