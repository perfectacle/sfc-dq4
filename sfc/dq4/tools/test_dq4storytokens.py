"""dq4storytokens.Runner 의 셀 걷기가 길을 막은 인물을 기다리는 동안 구간의 난수 묶기를 풀고, 비키거나 토막이 끝나면
되돌리는지(롬 없이)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dq4storytokens as tk  # noqa: E402

HOLD = [(0x7E075B, 0x12), (0x7E075C, 0x34), (0x7E075D, 0x56)]
BOY = 0x16


class Walker:
    def __init__(self):
        # 7E:00BE bit7: 마을 안(주인공 셀은 인물 표 칸 0)
        self.mem = {0x7E00BE: 0x80, 0x7E1967: 1, 0x7E1982: BOY + 1, tk.WINDOW: tk.W_NONE,
                    0x7E3020: 42, 0x7E3080: 35, 0x7E3020 + BOY: 40, 0x7E3080 + BOY: 34}
        self.pokes = list(HOLD)

    def rd(self, a):
        return self.mem.get(a, 0)


def runner():
    w = Walker()
    r = tk.Runner(w)
    r.win = tk.W_NONE
    return w, r


class HoldTests(unittest.TestCase):
    def test_blocked_cell_frees_rng_and_restores_when_the_person_moves(self):
        w, r = runner()
        walk = r.cell(40, 35, '40,33')
        next(walk)
        self.assertEqual(w.pokes, [])
        w.mem[0x7E3020 + BOY] = 10
        next(walk)
        self.assertEqual(w.pokes, HOLD)

    def test_hold_comes_back_when_the_token_ends_while_blocked(self):
        w, r = runner()
        walk = r.cell(40, 35, '40,33')
        next(walk)
        walk.close()
        self.assertEqual(w.pokes, HOLD)

    def test_free_path_keeps_the_hold(self):
        w, r = runner()
        w.mem[0x7E3020 + BOY] = 10
        walk = r.cell(40, 35, '40,33')
        next(walk)
        self.assertEqual(w.pokes, HOLD)

    def test_walker_without_pokes_is_fine(self):
        w, r = runner()
        del w.pokes
        next(r.cell(40, 35, '40,33'))
        self.assertIsNone(r.held)


if __name__ == '__main__':
    unittest.main()
