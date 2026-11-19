"""롬 없이: 대화 번호를 바꾼 talkNN 창 장면이 화면이 꺼지는 구간을 건너뛰고도 기본만큼 보는지."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dq4windowcheck as w  # noqa: E402


class TalkFramesTest(unittest.TestCase):
    def test_numbers_without_measured_darkness_keep_the_default_frames(self):
        """표에 없는 번호는 기본 프레임 그대로라, 나중에 화면을 끄게 되면 「절반 넘게 꺼진 화면」 판정이 잡는다."""
        for n in range(0x40):
            if n not in w.TALK_DARK:
                self.assertEqual(w.talk_frames(n), w.TALK_FRAMES, f'talk{n:02X}')

    def test_dark_numbers_skip_the_dark_and_see_no_less_than_the_default(self):
        for n, spans in w.TALK_DARK.items():
            frames = list(w.talk_frames(n))
            self.assertGreaterEqual(len(frames), len(w.TALK_FRAMES), f'talk{n:02X}')
            self.assertEqual(frames, sorted(set(frames)))
            self.assertTrue(all(w.TALK_FRAMES.start <= f < w.TALK_FRAMES.stop for f in frames))
            self.assertFalse([f for f in frames if any(lo <= f <= hi for lo, hi in spans)], f'talk{n:02X}')

    def test_a_scene_too_dark_to_see_enough_is_refused(self):
        saved = dict(w.TALK_DARK)
        try:
            w.TALK_DARK[0x10] = ((80, 1500),)
            with self.assertRaises(ValueError):
                w.talk_frames(0x10)
        finally:
            w.TALK_DARK.clear()
            w.TALK_DARK.update(saved)

    def test_scenes_use_the_talk_frames(self):
        talks = {s[0]: s[5] for s in w.scenes('ship.mss', 'party.mss') if s[0].startswith('talk') and len(s[0]) == 6}
        self.assertEqual(len(talks), 0x40)
        for n in range(0x40):
            self.assertEqual(list(talks[f'talk{n:02X}']), list(w.talk_frames(n)))


if __name__ == '__main__':
    unittest.main()
