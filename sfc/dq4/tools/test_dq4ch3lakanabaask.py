"""롬 없이: 레이크나바 검사가 예/아니오 물음에 답하는 입력이 창이 뜨는 프레임의 커서 값에 속지 않는지."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dq4ch3lakanabacheck as lk  # noqa: E402


def press_a_at(tokens, transient):
    """토큰을 차례로 돌려 A 를 누르는 때의 실제 커서. transient 는 cursor 토큰마다, 그 토큰이 창이 뜨는 프레임의 한 프레임
    값으로 끝났는지(그러면 커서는 곧 0 에 놓임). 표에서 빠진 뒤 토큰은 실제로 커서를 옮겨 끝난다."""
    flags = iter(transient)
    cursor = 0
    for t in tokens.split(';'):
        kind, _, arg = t.partition(':')
        if kind == 'cursor':
            cursor = 0 if next(flags, False) else int(arg)
        elif kind == 'a':
            return cursor
    raise AssertionError('A 가 없음')


class AskTest(unittest.TestCase):
    def test_a_transient_value_equal_to_the_answer_does_not_answer_yes(self):
        """창이 뜨는 프레임에 커서가 한 프레임 1 을 거쳤다가 0 에 놓여도 「아니오」(1)에 A 를 누른다."""
        self.assertEqual(press_a_at(lk.ask(1), [False, True]), 1)
        self.assertEqual(press_a_at(lk.ask(0), [True]), 0)

    def test_the_answer_is_set_again_after_the_cursor_settles(self):
        tokens = lk.ask(1).split(';')
        settle = next(i for i, t in enumerate(tokens) if t.startswith('settle:'))
        self.assertEqual(tokens[settle + 1], 'cursor:1')
        self.assertEqual(tokens[-1], 'a:8')
        self.assertGreater(lk.ASK_SETTLE, 1)


if __name__ == '__main__':
    unittest.main()
