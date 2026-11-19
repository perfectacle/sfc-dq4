"""dq4gatecheck 판정(롬·에뮬레이터 없이)."""
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4gatecheck as gate  # noqa: E402


class VerdictTest(unittest.TestCase):
    LOCKED = {'open': False}
    OPEN = {'open': True}

    def test_locked_door_must_show_its_message(self):
        self.assertTrue(gate.verdict(self.LOCKED, False, False, 1))
        # 문에 닿지 못한 실행도 「안 열림·안 지나감」 이다
        self.assertFalse(gate.verdict(self.LOCKED, False, False, 0))
        self.assertFalse(gate.verdict(self.LOCKED, True, False, 1))
        self.assertFalse(gate.verdict(self.LOCKED, False, True, 1))

    def test_open_door_opens_passes_and_shows_no_lock_message(self):
        self.assertTrue(gate.verdict(self.OPEN, True, True, 0))
        self.assertFalse(gate.verdict(self.OPEN, True, True, 1))
        self.assertFalse(gate.verdict(self.OPEN, True, False, 0))
        self.assertFalse(gate.verdict(self.OPEN, False, True, 0))


if __name__ == '__main__':
    unittest.main()
