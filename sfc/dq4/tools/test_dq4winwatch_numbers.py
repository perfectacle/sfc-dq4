"""엔진 창 번호: 화면 창으로 바꿔 끼울 때 옛 사각형의 번호가 지금 창의 번호를 덮지 않고, 화면에서만 찾은 창은 열 폭이 같은
엔진 창의 번호를 빌린다."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dq4winwatch as ww  # noqa: E402
import dq4winrule_align as align  # noqa: E402
from test_dq4winwatch import draw, fake_rom, shot  # noqa: E402

CMD, PARTY = (4, 2, 12, 13), (19, 16, 27, 28)


class SnapNumberTest(unittest.TestCase):
    def test_old_rectangle_does_not_overwrite_the_current_window_number(self):
        # 장면 앞에서 같은 왼쪽 위 모서리로 더 큰 창(13)을 그렸고, 지금은 명령 창(01)이 떠 있다
        m = [0x2C00] * 1024
        draw(m, *CMD)
        old = (4, 2, 20, 13)
        screen = ww.Screen(shot(m), ww.Ref(fake_rom()), engine=[CMD], numbers={CMD: 0x01, old: 0x13})
        self.assertIn(CMD, screen.rects)
        self.assertEqual(screen.numbers[CMD], 0x01)


class BorrowTest(unittest.TestCase):
    def test_hidden_window_borrows_the_number_of_the_engine_window_with_the_same_columns(self):
        # 명령 창이 위 창에 거의 가려 화면에서만 (4,2,6,13) 으로 찾힘
        screen = SimpleNamespace(numbers={CMD: 0x01, PARTY: None})
        self.assertEqual(align.number(screen, (4, 2, 6, 13)), 0x01)
        self.assertIsNone(align.number(screen, (4, 3, 6, 13)))


if __name__ == '__main__':
    unittest.main()
