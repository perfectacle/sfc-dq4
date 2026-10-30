"""전투 메시지 창 실측 도구가 두 롬의 실행 기록을 어디까지 견주는지."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dq5msgwindowcheck import same_until  # noqa: E402


class SameUntilTests(unittest.TestCase):
    def test_same_records(self):
        calls = ['600 248C39 5', '', '610 24A519 1']
        self.assertEqual(same_until(calls, list(calls)), 1 << 30)
        self.assertEqual(same_until([], []), 1 << 30)

    def test_first_difference(self):
        self.assertEqual(same_until(['600 248C39 5', '640 24A519 1'], ['600 248C39 5', '630 24A519 2']), 630)

    def test_one_record_ends_first(self):
        short = ['600 248C39 5', '610 24A519 1']
        long = short + ['610 24880A 0', '700 24A569 0']
        self.assertEqual(same_until(short, long), 610)
        self.assertEqual(same_until(long + ['', '900 EFF 0'], short), 610)
        self.assertEqual(same_until(short[:1], ['600 248C39 5', '650 24A519 1']), 650)
        self.assertEqual(same_until([], ['', '600 248C39 5']), 600)
        # 짧은 기록이 610 에서 끝나도 긴 기록의 다음 줄이 700 이면 699 까지는 둘이 같다
        self.assertEqual(same_until(short, short + ['700 24A569 0']), 700)


if __name__ == '__main__':
    unittest.main()
