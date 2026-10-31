import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dq4balance as bal  # noqa: E402


class ChanceTest(unittest.TestCase):
    def test_three_quarters(self):
        # FC's region chance 55 -> 40, terrain factors rounded half up, a small chance stays 1, none stays 0.
        self.assertEqual([bal.chance(v) for v in (0x55, 0x1A, 0x0B, 0x0F, 2, 1, 0)], [0x40, 20, 8, 11, 2, 1, 0])


class RewardTest(unittest.TestCase):
    def test_reward(self):
        self.assertEqual([bal.reward(v) for v in (0, 1, 2, 3, 7, 8, 16, 0xFFFFFF)],
                         [0, 1, 3, 4, 9, 11, 21, 0xFFFFFF])

    def test_hook(self):
        data, labels = bal.code()
        self.assertEqual(labels["hook"], bal.REWARD_AT)
        # Leaves by JML to the victory sequence's first call.
        self.assertIn(bytes((0x5C, 0xD3, 0x88, 0x25)), data)
        w = bal.writes()
        self.assertEqual(w[1], {"at": "20:8100", "hex": "22 00 F0 57", "orig": "22 D3 88 25",
                                "note": w[1]["note"]})

    def test_hook_divides(self):
        # Run the scale routine's arithmetic as the CPU does: a byte at a time through the divider.
        for v in (0, 1, 2, 5, 16, 255, 256, 767, 0x123456, 0xFFFFFE, 0xFFFFFF):
            rem, q = 0, 0
            for byte in v.to_bytes(3, "big"):
                cur = rem * 256 + byte
                q, rem = q * 256 + cur // 3, cur % 3
            self.assertEqual(min(0xFFFFFF, v + q + (rem == 2)), bal.reward(v))


if __name__ == "__main__":
    unittest.main()
