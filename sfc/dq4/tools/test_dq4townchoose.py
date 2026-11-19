"""롬 없이: 마을 장면의 고르기 창 판별이 창이 몇 프레임 늦게 떠도 흔들리지 않는지(가짜 코어)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dq4townscene as t  # noqa: E402


class FakeCore:
    """프레임마다 장면 차례(script)대로 창이 뜨는 가짜 코어. script = [(첫 프레임, 맨 위 창, 칸 수, 고리 시작 프레임)].
    고리가 도는 프레임에는 깜박임 박자가 8 오르고, 칸 수가 2 이상이면 아래·위로 커서가 움직인다. A 를 누르면 그 창이 닫힌다."""

    def __init__(self, script, end):
        self.script, self.end = script, end
        self.n, self.blink, self.cursor, self.closed, self.picked = 0, 0, 0, set(), []
        self.held = frozenset()

    def window(self):
        live = [s for s in self.script if s[0] <= self.n and s[0] not in self.closed]
        return live[-1] if live else None

    def rd(self, addr, n=1):
        w = self.window()
        if addr == t.BLINK:
            return self.blink & 0xFF
        if addr == t.DEPTH:
            return 1 if w else 0
        if addr == t.STACK + 1:
            return w[1] if w else 0
        if addr == t.STACK:
            return t.MESSAGE_WINDOW
        if addr == t.CURSOR:
            return self.cursor
        if addr == t.TALKING:
            return 1 if self.n < self.end else 0
        return 0

    def run(self, keys=()):
        w = self.window()
        new = set(keys) - self.held          # 고리는 새로 누른 버튼만 받는다
        self.held = frozenset(keys)
        if w and self.n >= w[3]:
            self.blink += 8
            if w[2] > 1 and 'down' in new:
                self.cursor = min(self.cursor + 1, w[2] - 1)
            if w[2] > 1 and 'up' in new:
                self.cursor = max(self.cursor - 1, 0)
            if 'a' in new and w[1] != t.MESSAGE_WINDOW:
                self.picked.append((w[1], self.cursor))
                self.closed.add(w[0])
                self.cursor = 0
        self.n += 1

    def save(self):
        return (self.n, self.blink, self.cursor, set(self.closed), list(self.picked), self.held)

    def load(self, st):
        self.n, self.blink, self.cursor, closed, picked, self.held = st
        self.closed, self.picked = set(closed), list(picked)


class Fake(t.Probe):
    def sound_busy(self):
        return False


def run(delay):
    # 메시지 창(키 기다림에도 박자가 돎) 뒤 교회 메뉴(6칸, 고리가 delay 프레임 늦게 시작) → 예/아니요(2칸)
    script = [(0, t.MESSAGE_WINDOW, 1, 10), (100, 0x3C, 6, 100 + delay), (300, 0x32, 2, 300 + delay)]
    core = FakeCore(script, 600)
    got = Fake(core).converse([3, 0], default='b', limit=800)
    return core.picked, got


class ChooseTest(unittest.TestCase):
    def test_late_windows_are_still_answered(self):
        for delay in (0, 3, 6, 20):
            picked, got = run(delay)
            self.assertEqual(picked[:2], [(0x3C, 3), (0x32, 0)], f'늦음 {delay}')

    def test_message_wait_blink_is_not_a_choice(self):
        core = FakeCore([(0, t.MESSAGE_WINDOW, 1, 0)], 200)
        got = Fake(core).converse([], default='b', limit=300)
        self.assertEqual(got['choices'], [])

    def test_one_slot_window_is_left_to_the_advance(self):
        core = FakeCore([(0, 0x3D, 1, 0)], 200)
        got = Fake(core).converse([5], default=None, limit=300)
        self.assertEqual(got['choices'], [])


if __name__ == '__main__':
    unittest.main()
