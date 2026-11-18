import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4lowwram as low  # noqa: E402


def asm_value(name, label):
    m = re.search(rf'^!{label}\s*=\s*\$([0-9A-Fa-f]+)', (HERE / name).read_text(encoding='utf-8'), re.M)
    return int(m[1], 16)


class TableTest(unittest.TestCase):
    def test_no_problems(self):
        self.assertEqual(low.problems(), [])

    def test_a_long_lived_cell_in_the_dq5_people_table_is_caught(self):
        bad = low.CELLS + ((0x1BF0, 0x1BF2, 'x', 'y', 'persistent'),)
        orig = low.CELLS
        try:
            low.CELLS = bad
            self.assertTrue(any('people' in p for p in low.problems()))
        finally:
            low.CELLS = orig

    def test_cells_that_share_the_dq5_ranges_are_short_lived(self):
        # 맵을 넘어 사는 칸은 DQ5 가 쓰는 범위 밖에만
        for c in low.CELLS:
            if any(low.overlaps(c, r) for r in low.DQ5_USES.values()):
                self.assertNotEqual(c[4], 'persistent', c)


class ModuleTest(unittest.TestCase):
    """모듈의 상수가 이 표의 칸 안에 있는지(표만 고치고 모듈을 옮기지 않거나 그 반대를 잡음)."""

    def cell(self, module, name):
        return next(c for c in low.CELLS if c[2] == module and c[3] == name)

    def inside(self, addr, cell, size=1):
        a = addr & 0xFFFF
        self.assertTrue(cell[0] <= a and a + size <= cell[1], f'{a:04X}+{size} 이 {cell[3]} 밖')

    def test_python_constants(self):
        import dq4bg3slot
        import dq4ch1event
        import dq4ch2event
        import dq4josa
        import dq4menupatch
        import dq4neneshop
        import dq4prologue
        import dq4soundpatch
        self.inside(dq4soundpatch.KEEP_BUSY, self.cell('dq4soundpatch', 'KEEP_BUSY·KEEP_SONG'), 2)
        self.inside(dq4soundpatch.KEEP_SONG, self.cell('dq4soundpatch', 'KEEP_BUSY·KEEP_SONG'))
        self.inside(dq4bg3slot.SHOWN, self.cell('dq4bg3slot', 'SHOWN'))
        self.assertEqual(self.cell('dq4menupatch', 'SHARED_WRAM')[:2], (dq4menupatch.SHARED_WRAM, dq4menupatch.MENU_FLAG))
        self.inside(dq4menupatch.MENU_FLAG, self.cell('dq4menupatch', 'MENU_FLAG'))
        self.inside(dq4josa.LAST, self.cell('dq4josa', 'LAST'), 2)
        self.inside(dq4prologue.TALKER, self.cell('dq4prologue', 'TALKER'))
        self.inside(dq4ch1event.SCRATCH, self.cell('dq4ch1event', 'SCRATCH'), 0x10)
        self.inside(dq4neneshop.TEMP, self.cell('dq4neneshop', 'TEMP'), 10)
        self.inside(dq4prologue.ROUTE_BUF, self.cell('dq4prologue', 'ROUTE_BUF'), dq4prologue.ROUTE_MAX)
        self.inside(dq4ch2event.STEP_COUNT, self.cell('dq4ch2event', 'STEP_COUNT'), 2)

    def test_asm_constants(self):
        entry = self.cell('dq4nameentry', 'in_direction~in_steady')
        self.inside(asm_value('dq4nameentry.asm', 'in_direction'), entry)
        self.inside(asm_value('dq4nameentry.asm', 'in_steady'), entry)
        wn = self.cell('dq4windowname', 'wn_keys~wt_stack')
        self.inside(asm_value('dq4windowname.asm', 'wn_keys'), wn)
        self.inside(asm_value('dq4windowname.asm', 'wn_attr'), wn)
        self.assertEqual(asm_value('dq4windowname.asm', 'wt_stack') + 1, wn[1])


if __name__ == '__main__':
    unittest.main()
