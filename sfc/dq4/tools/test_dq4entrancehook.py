"""The entrance hooks run on the w65816 interpreter over a blank ROM whose return points only RTS."""

import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS.parents[1] / "dq5" / "tools"))

import dq4entrancehook as hook  # noqa: E402
from w65816 import Cpu  # noqa: E402

AT = 0x3CF800
ARRIVALS = [(0x36, 345, 56, 0, 0, 59, 1, 0), (0x36, 360, 70, 3, 12, 34, 1, 2)]
FIELDS = [(0x36, 0, 2, 345, 57), (0x36, 3, 5, 360, 71), (0x38, 0, 0, 400, 20, 7, 7), (0x38, 0, 0, 400, 30)]


def rom_with_hooks():
    rom = bytearray(0x200000)

    def put(addr, data):
        at = (addr >> 16 & 0x7F) << 15 | addr & 0x7FFF
        rom[at:at + len(data)] = data

    for w in hook.writes(AT, ARRIVALS, FIELDS):
        bank, addr = w["at"].split(":")
        put(int(bank, 16) << 16 | int(addr, 16), bytes.fromhex(w["hex"]))
    # 2A:F286 SEP #$30 / JSR $F28D / SEC / RTS; the per-map exceptions after the hook only return.
    put(0x2AF286, bytes((0xE2, 0x30, 0x20, 0x8D, 0xF2, 0x38, 0x60)))
    put(hook.ENTER_BACK, b"\x60")
    # Leaving: the table hit lands on PLP/RTS with $C0 = 1, the original search on PLP/RTS with $C0 = 2.
    # The hit path also leaves the P it arrived with in $C4 (2A:F475 runs with 16-bit A and X).
    put(hook.LEAVE_ON, bytes((0x08, 0xE2, 0x20, 0x68, 0x85, 0xC4, 0xA9, 0x01, 0x85, 0xC0, 0x28, 0x18, 0x60)))
    put(hook.LEAVE_BACK, bytes((0xE2, 0x20, 0xA9, 0x02, 0x85, 0xC0, 0x28, 0x18, 0x60)))
    return bytes(rom)


class EntranceHookTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom = rom_with_hooks()

    def cpu(self, **dp):
        wram = bytearray(0x20000)
        for name, value in dp.items():
            at = int(name[1:], 16)
            size = 2 if name in ("_B6", "_B8") else 1
            wram[at:at + size] = value.to_bytes(size, "little")
        cpu = Cpu(self.rom, wram)
        cpu.pbr, cpu.x = 0x2A, 0x1234
        return cpu

    def enter(self, group, fx, fy):
        cpu = self.cpu(_BC=group, _B6=fx, _B8=fy, _BD=0x1F, _C1=0x77, _C2=0x77, _C3=0x77)
        cpu.jsr(0x2AF286, max_steps=2000)
        return cpu.wram[0xBD], cpu.wram[0xC1], cpu.wram[0xC2], cpu.wram[0xC3], cpu.wram[0x198E], cpu.x & 0xFF

    def leave(self, group, number, row=0):
        cpu = self.cpu(_BC=group, _BD=number, _B6=0xAAAA, _B8=0xBBBB, _3080=row)
        cpu.jsr(hook.LEAVE_SITE, max_steps=2000)
        return cpu.wram[0xC0], cpu.r16(0xB6), cpu.r16(0xB8)

    def test_second_entrance_overrides_the_arrival(self):
        self.assertEqual(self.enter(0x36, 360, 70), (3, 12, 34, 1, 2, 0x34))
        self.assertEqual(self.enter(0x36, 345, 56)[:5], (0, 0, 59, 1, 0))

    def test_sixteen_bit_x_entry_keeps_x(self):
        # 2A:F379 (the day/night redraw) reaches the hook with 16-bit X.
        cpu = self.cpu(_BC=0x36, _B6=360, _B8=70)
        cpu.p, cpu.x = 0x20, 0x1234
        cpu.jsr(hook.ENTER_SITE, max_steps=2000)
        self.assertEqual((cpu.wram[0xBD], cpu.wram[0xC1], cpu.x, cpu.p & 0x30), (3, 12, 0x1234, 0x20))

    def test_other_cells_and_groups_keep_the_group_arrival(self):
        self.assertEqual(self.enter(0x36, 345, 57)[:4], (0x1F, 0x77, 0x77, 0x77))
        # Same cell, other group: the no-entrance path of 2A:F27B also runs the exceptions.
        self.assertEqual(self.enter(0x37, 360, 70)[:4], (0x1F, 0x77, 0x77, 0x77))

    def test_leaving_picks_the_field_cell_of_the_map_range(self):
        self.assertEqual(self.leave(0x36, 0), (1, 345, 57))
        cpu = self.cpu(_BC=0x36, _BD=0)
        cpu.jsr(hook.LEAVE_SITE, max_steps=2000)
        self.assertEqual(cpu.wram[0xC4] & 0x30, 0)
        self.assertEqual(self.leave(0x36, 2), (1, 345, 57))
        self.assertEqual(self.leave(0x36, 3), (1, 360, 71))
        self.assertEqual(self.leave(0x36, 5), (1, 360, 71))

    def test_leaving_picks_the_stair_by_the_hero_row(self):
        self.assertEqual(self.leave(0x38, 0, row=7), (1, 400, 20))
        self.assertEqual(self.leave(0x38, 0, row=97), (1, 400, 30))
        self.assertEqual(self.leave(0x38, 0, row=6), (1, 400, 30))

    def test_leaving_unlisted_maps_searches_the_entrance_tables(self):
        self.assertEqual(self.leave(0x36, 6), (2, 0xAAAA, 0xBBBB))
        self.assertEqual(self.leave(0x37, 0), (2, 0xAAAA, 0xBBBB))

    def test_tables_end_and_ranges(self):
        arr, out = hook.tables(ARRIVALS, FIELDS)
        self.assertEqual((len(arr), len(out)), (2 * hook.ARRIVAL_SIZE + 1, 4 * hook.FIELD_SIZE + 1))
        with self.assertRaises(ValueError):
            hook.tables([], [(0x36, 0, 0, 0, 0, 9, 8)])
        with self.assertRaises(ValueError):
            hook.tables([], [(0x36, 4, 2, 0, 0)])
        with self.assertRaises(ValueError):
            hook.tables([(0x36, 0, 0, 0x20, 0, 0, 1, 0)], [])
        with self.assertRaises(ValueError):
            hook.tables([(0x36, 0, 0, 0, 0, 0, 1, 0x04)], [])


if __name__ == "__main__":
    unittest.main()
