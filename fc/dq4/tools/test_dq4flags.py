"""플래그 뜻 표와 장 진행 표가 서로 맞는지(한 비트, 플래그 영역 안, 진행 표 중복 없음, 뜻 없는 플래그 없음) 검사한다."""
import unittest

import dq4event
import dq4flags

AREA = dq4event.FLAGS_END - dq4event.FLAGS


class FlagTableTests(unittest.TestCase):
    def test_keys_are_single_bits_in_flag_area(self):
        for n, m in list(dq4flags.CONFIRMED) + list(dq4flags.UNUSED) + list(dq4event.KNOWN):
            self.assertLessEqual(n, AREA, f'{n:02X}')
            self.assertEqual(m.bit_count(), 1, f'{n:02X}/{m:02X}')

    def test_story_has_five_chapters_without_repeats(self):
        self.assertEqual(sorted(dq4flags.STORY), [1, 2, 3, 4, 5])
        flags = [f for scenes in dq4flags.STORY.values() for _, fs in scenes for f in fs]
        self.assertEqual(len(flags), len(set(flags)))

    def test_every_story_flag_has_a_meaning(self):
        known = set(dq4flags.CONFIRMED) | set(dq4event.KNOWN)
        missing = [f for scenes in dq4flags.STORY.values() for _, fs in scenes for f in fs if f not in known]
        self.assertEqual(missing, [])

    def test_unused_and_confirmed_do_not_overlap(self):
        self.assertFalse(set(dq4flags.UNUSED) & set(dq4flags.CONFIRMED))


if __name__ == '__main__':
    unittest.main()
