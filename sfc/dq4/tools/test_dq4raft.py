"""3장 여신상 동굴 배(dq4raft): FC 물 칸 표와 배 자리, w65816 로 돌린 reset·ctl 네이티브의 탐·내림·물 칸 표시.

셀을 찾는 25:FA15 와 차지 비트를 지우는 00:DEB5 는 훅으로 바꾼다(셀 +1 은 7F 뱅크의 시험 자리)."""

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools'), str(HERE.parents[2] / 'fc' / 'dq4' / 'tools')]

import dq4ch3safe as safe  # noqa: E402
import dq4ch3endor as endor  # noqa: E402
import dq4raft as raft  # noqa: E402

DQ4 = HERE.parents[2] / 'rom' / 'dq4.nes'
RAFT_SLOT = 8
DRY = 0x08                      # 이 동굴 셀 +1 의 벽·물 값(bit1 없음)


def _prg():
    from kr_patch.fc import ines
    return ines.prg(DQ4.read_bytes())


def lorom(addr):
    return (addr >> 16 & 0x7F) * 0x8000 + (addr & 0x7FFF)


def cell_plus1(x, y):
    return 0x10000 + (y * 0x100 + x) * 2 + 1


@unittest.skipUnless(DQ4.exists(), 'FC 롬 없음')
class TableTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        prg = _prg()
        cls.water = {k: {(x, y) for y, x0, x1 in raft.water_runs(prg, fc) for x in range(x0, x1 + 1)}
                     for k, (fc, _) in raft.MAPS.items()}

    def test_rafts_start_on_water(self):
        for k, (_, start) in raft.MAPS.items():
            if start:
                self.assertIn(start, self.water[k], f'{k:02X}')
        self.assertIn(raft.ISLAND[1], self.water[0x06])

    def test_lake_end_crosses_to_the_lower_floor_water(self):
        # 40/00 호수 아래 끝 x 18 의 두 줄은 물이고 왼쪽은 벽이라 다른 길로는 넘어가지 않는다
        for row in raft.CROSS['rows']:
            self.assertIn((raft.CROSS['x'], row), self.water[raft.CROSS['map']])
            self.assertNotIn((raft.CROSS['x'] - 1, row), self.water[raft.CROSS['map']])
            self.assertIn((raft.CROSS['to_x'], row + raft.CROSS['dy']), self.water[raft.CROSS['to']])

    def test_code_fits_its_place(self):
        out, at = safe.raft_natives()
        self.assertLessEqual(safe.RAFT_CODE[0] + sum(len(b) for _, b in out), safe.RAFT_CODE[1])
        self.assertEqual(min(at.values()), safe.RAFT_CODE[0])


@unittest.skipUnless(DQ4.exists(), 'FC 롬 없음')
class NativeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from w65816 import Cpu
        except ImportError:
            raise unittest.SkipTest('w65816 없음')
        cls.Cpu = Cpu
        cls.pieces, cls.at = safe.raft_natives()
        rom = bytearray(0x300000)
        for name, code in cls.pieces:
            rom[lorom(cls.at[name]):lorom(cls.at[name]) + len(code)] = code
        rom[lorom(raft.CELL_AT)] = 0x6B
        rom[lorom(raft.CLEAR_CELLS)] = 0x6B
        cls.rom = bytes(rom)
        prg = _prg()
        cls.water = {k: {(x, y) for y, x0, x1 in raft.water_runs(prg, fc) for x in range(x0, x1 + 1)}
                     for k, (fc, _) in raft.MAPS.items()}

    def wram(self, mp, hero, raft_cell=None, riding=False, button=False):
        w = bytearray(0x20000)
        w[0xBC], w[0xBD] = raft.GROUP, mp
        for y in range(0x80):
            for x in range(0x80):
                w[cell_plus1(x, y)] = DRY
        for s in range(1, raft.SLOTS):
            w[(raft.SLOT_X & 0xFFFF) + s] = w[(raft.SLOT_Y & 0xFFFF) + s] = 0x80
        w[raft.SLOT_X & 0xFFFF], w[raft.SLOT_Y & 0xFFFF] = hero
        if raft_cell:
            w[(raft.SLOT_X & 0xFFFF) + RAFT_SLOT], w[(raft.SLOT_Y & 0xFFFF) + RAFT_SLOT] = raft_cell
            w[(raft.SLOT_GFX & 0xFFFF) + RAFT_SLOT] = raft.RAFT_GFX
        if riding:
            w[(0x7E2190 + safe.RIDING[0]) & 0xFFFF] |= safe.RIDING[1]
        if button:
            w[(0x7E2190 + endor.BUTTON[0]) & 0xFFFF] |= endor.BUTTON[1]
        return w

    def call(self, w, name):
        c = self.Cpu(self.rom, w)
        crossed = []

        def cell_at(cpu):
            p = 0x7F0000 + ((cpu.y & 0xFF) * 0x100 + (cpu.x & 0xFF)) * 2
            cpu.wram[0], cpu.wram[1], cpu.wram[2] = p & 0xFF, p >> 8 & 0xFF, p >> 16
            return False

        def cross(cpu):
            crossed.append(cpu.wram[0x0D])
            lo, hi, bank = cpu.pull(), cpu.pull(), cpu.pull()
            cpu.pbr, cpu.pc = bank, ((hi << 8 | lo) + 1) & 0xFFFF
            return True
        c.hooks[raft.CELL_AT] = cell_at
        for row in raft.CROSS['rows']:
            c.hooks[self.at[f'cross{row:X}']] = cross
        c.jsl(self.at[name], max_steps=2_000_000)
        return c.wram, crossed

    @staticmethod
    def marked(w):
        """bit1 이 켜진 FC 칸(FC 칸 (x, y)는 셀 (2x~2x+1, 2y~2y+1))."""
        return {(x // 2, y // 2) for y in range(0x80) for x in range(0x80) if w[cell_plus1(x, y)] & raft.WATER_BIT}

    def var(self, w, k):
        return w[(safe.RAFT_VARS + k) & 0xFFFF]

    def riding(self, w):
        return bool(w[(0x7E2190 + safe.RIDING[0]) & 0xFFFF] & safe.RIDING[1])

    def test_reset_marks_only_the_raft_cell(self):
        w, _ = self.call(self.wram(0x02, (0x22, 0x09), (0x2C, 0x0B)), 'reset')
        self.assertEqual(w[raft.HERO_MASK & 0xFFFF], 0x03)
        self.assertEqual((self.var(w, raft.RX), self.var(w, raft.RY), self.var(w, raft.RS)), (0x16, 0x05, RAFT_SLOT))
        self.assertEqual(self.marked(w), {(0x16, 0x05)})

    def test_reset_after_the_button_removes_the_raft(self):
        w, _ = self.call(self.wram(0x02, (0x22, 0x09), (0x2C, 0x0B), button=True), 'reset')
        self.assertEqual(self.var(w, raft.RS), 0xFF)
        self.assertEqual(w[(raft.SLOT_X & 0xFFFF) + RAFT_SLOT], 0x80)
        self.assertEqual(self.marked(w), set())

    def test_reset_clears_riding_left_over_from_another_map(self):
        w, _ = self.call(self.wram(0x06, (0x3C, 0x39), (0x3A, 0x37), riding=True), 'reset')
        self.assertFalse(self.riding(w))
        self.assertEqual(self.marked(w), {(0x1D, 0x1B)})

    def test_island_stairs_put_the_raft_beside_the_island(self):
        w, _ = self.call(self.wram(0x06, (2 * raft.ISLAND[0], 0x0D), (0x3A, 0x37)), 'reset')
        self.assertEqual((self.var(w, raft.RX), self.var(w, raft.RY)), raft.ISLAND[1])
        self.assertEqual(self.marked(w), {raft.ISLAND[1]})

    def test_riding_across_keeps_riding_on_the_lower_floor(self):
        w, _ = self.call(self.wram(0x05, (0x0E, 0x3F), (0x04, 0x35), riding=True), 'reset')
        self.assertTrue(self.riding(w))
        self.assertEqual((self.var(w, raft.RX), self.var(w, raft.RY)), (0x07, 0x1F))
        self.assertEqual(self.marked(w), self.water[0x05])

    def test_walking_into_the_raft_boards_and_marks_all_water(self):
        w, _ = self.call(self.wram(0x02, (0x22, 0x09), (0x2C, 0x0B)), 'reset')
        w[raft.SLOT_X & 0xFFFF], w[raft.SLOT_Y & 0xFFFF] = 0x2C, 0x0B
        w, _ = self.call(w, 'ctl')
        self.assertTrue(self.riding(w))
        self.assertEqual(self.marked(w), self.water[0x02])

    def test_raft_follows_and_stays_where_the_hero_lands(self):
        w, _ = self.call(self.wram(0x02, (0x2C, 0x0B), (0x2C, 0x0B)), 'reset')
        w, _ = self.call(w, 'ctl')
        w[raft.SLOT_X & 0xFFFF] = 0x2E
        w, _ = self.call(w, 'ctl')
        self.assertEqual((w[(raft.SLOT_X & 0xFFFF) + RAFT_SLOT], self.var(w, raft.RX)), (0x2E, 0x17))
        w[raft.SLOT_X & 0xFFFF] = 0x2A
        w, _ = self.call(w, 'ctl')
        self.assertFalse(self.riding(w))
        self.assertEqual(self.marked(w), {(0x17, 0x05)})

    def test_lake_end_starts_the_crossing(self):
        for row in raft.CROSS['rows']:
            w, _ = self.call(self.wram(0x02, (0x2C, 0x0B), (0x2C, 0x0B)), 'reset')
            w, _ = self.call(w, 'ctl')
            w[raft.SLOT_X & 0xFFFF], w[raft.SLOT_Y & 0xFFFF] = 2 * raft.CROSS['x'], 2 * row + 1
            _, crossed = self.call(w, 'ctl')
            self.assertEqual(crossed, [row])


if __name__ == '__main__':
    unittest.main()
