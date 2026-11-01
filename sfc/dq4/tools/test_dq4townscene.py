"""dq4townscene 의 판정 함수·SRAM 조작(롬·에뮬레이터 없이)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dq4savefixture as fx  # noqa: E402
import dq4townscene as ts  # noqa: E402
from dq5sram import SLOT_SIZE, SLOTS, SUM_AT, USED  # noqa: E402


def member(state=0x80, hp=10, max_hp=10, mp=3, max_mp=3, level=4):
    return {'state': state, 'hp': hp, 'max_hp': max_hp, 'mp': mp, 'max_mp': max_mp, 'level': level}


def snap(gold, time, *party):
    return {'gold': gold, 'time': time, 'party': list(party)}


class InnTest(unittest.TestCase):
    def test_stay_takes_price_times_party_and_fills(self):
        before = snap(100, 0x0050, member(hp=5), member(hp=1, mp=0))
        after = snap(88, 0x0050, member(), member())
        self.assertEqual(ts.judge_inn(before, after, 12, 6, True), [])

    def test_stay_wrong_total_and_half_hp(self):
        before = snap(100, 0x0050, member(hp=5), member(hp=1))
        after = snap(94, 0x0050, member(), member(hp=2))
        problems = ts.judge_inn(before, after, 6, 6, True)
        self.assertEqual(len(problems), 3)

    def test_night_stay_must_wake_in_morning(self):
        before = snap(100, 0x0190, member(hp=5))
        self.assertEqual(ts.judge_inn(before, snap(94, 0x0050, member()), 6, 6, True, night=True), [])
        self.assertTrue(ts.judge_inn(before, snap(94, 0x0190, member()), 6, 6, True, night=True))

    def test_refused_or_poor_changes_nothing(self):
        before = snap(11, 0x0050, member(hp=5))
        self.assertEqual(ts.judge_inn(before, snap(11, 0x0050, member(hp=5)), 12, 6, False), [])
        self.assertTrue(ts.judge_inn(before, snap(5, 0x0050, member(hp=5)), 12, 6, False))


class ChurchTest(unittest.TestCase):
    def test_revive(self):
        before = snap(100, 0x50, member(), member(state=0, hp=0, level=4))
        after = snap(60, 0x50, member(), member(hp=59, max_hp=59, level=4))
        self.assertEqual(ts.judge_church(before, after, 1, 40, ts.ALIVE), [])

    def test_still_dead_or_free(self):
        before = snap(100, 0x50, member(), member(state=0, hp=0))
        after = snap(100, 0x50, member(), member(state=0, hp=0))
        self.assertEqual(len(ts.judge_church(before, after, 1, 40, ts.ALIVE)), 3)

    def test_cure_clears_poison_bit(self):
        before = snap(100, 0x50, member(state=ts.ALIVE | ts.POISON))
        self.assertEqual(ts.judge_church(before, snap(95, 0x50, member()), 0, 5, ts.ALIVE), [])


def sram_with(blocks, last=None):
    return fx.frame_sram(blocks, last)


class SaveTest(unittest.TestCase):
    def setUp(self):
        self.block = bytes((i * 7) & 0xFF for i in range(SLOT_SIZE))

    def wram_of(self, block):
        w = bytearray(0x20000)
        w[fx.WRAM_BASE:fx.WRAM_BASE + SLOT_SIZE] = block
        return bytes(w)

    def test_saved_slot_matches_wram_at_write(self):
        before = sram_with({0: self.block})
        after = sram_with({0: self.block, 1: self.block}, last=1)
        self.assertEqual(ts.judge_saved(before, after, self.wram_of(self.block), 1), [])

    def test_saved_slot_differs_from_wram(self):
        before = sram_with({0: self.block})
        after = sram_with({0: self.block, 1: self.block}, last=1)
        w = bytearray(self.wram_of(self.block))
        w[0x2019] ^= 1
        problems = ts.judge_saved(before, after, bytes(w), 1)
        self.assertEqual(len(problems), 1)
        self.assertIn('2019', problems[0])

    def test_not_written_and_other_slot_changed(self):
        before = sram_with({0: self.block})
        changed = bytearray(self.block)
        changed[0x10] ^= 0xFF
        after = sram_with({0: bytes(changed)})
        problems = ts.judge_saved(before, after, None, 1)
        self.assertTrue(any('쓰이지 않음' in p for p in problems))
        self.assertTrue(any('칸 1 이 바뀜' in p for p in problems))

    def test_corrupt_breaks_only_that_slot(self):
        sram = sram_with({0: self.block, 1: self.block})
        bad = ts.corrupt(sram, 1)
        self.assertTrue(ts.slot_ok(bad, 0))
        self.assertFalse(ts.slot_ok(bad, 1))
        self.assertEqual(sum(a != b for a, b in zip(sram, bad)), 1)
        self.assertEqual(fx.saved_slots(bad), [0])

    def test_slot_ok_needs_used_bit(self):
        sram = bytearray(sram_with({0: self.block}))
        sram[USED] = 0
        self.assertFalse(ts.slot_ok(bytes(sram), 0))

    def test_loaded_skips_rewritten_bytes(self):
        w = bytearray(self.wram_of(self.block))
        for a in ts.REWRITTEN:
            w[a] ^= 0xFF
        self.assertEqual(ts.judge_loaded(self.block, bytes(w)), [])
        w[0x2040] ^= 1
        self.assertEqual(len(ts.judge_loaded(self.block, bytes(w))), 1)

    def test_block_diff_ignores_checksum_word(self):
        w = bytearray(self.wram_of(self.block))
        w[fx.WRAM_BASE + SUM_AT] ^= 0xFF
        self.assertEqual(ts.block_diff(self.block, bytes(w)), [])

    def test_put_member(self):
        slot = fx.SaveSlot(bytes(SLOT_SIZE), b'')
        ts.put_member(slot, 1, state=0, hp=0x1234, exp=0x00ABCD)
        base = fx.HERO + ts.RECORD_SIZE - fx.WRAM_BASE
        self.assertEqual(slot.block[base + ts.STATE], 0)
        self.assertEqual(slot.block[base + ts.HP:base + ts.HP + 2], b'\x34\x12')
        self.assertEqual(slot.block[base + ts.EXP:base + ts.EXP + 3], b'\xCD\xAB\x00')
        self.assertEqual(SLOTS[1] - SLOTS[0], SLOT_SIZE)


def time_rom():
    """01:A16B 시각 표·01:A189 포인터·01:A1D5~ 벌 8개·01:A422/A45E 인물 줄을 DQ5 와 같은 꼴로 둔 합성 롬."""
    rom = bytearray(0x10000)
    rows = [(0x0000, 8), (0x0001, 6), (0x0002, 4), (0x00EE, 6), (0x00EF, 8), (0x00F0, 10), (0x00F1, 12),
            (0x00F2, 14), (0x01FD, 12), (0x01FE, 10)]
    o = fx.lorom(ts.TIME_TABLE)
    for k, (low, idx) in enumerate(rows):
        rom[o + 3 * k:o + 3 * k + 3] = bytes((low & 0xFF, low >> 8, idx))
    p = fx.lorom(ts.TIME_SETS)
    for k in range(8):
        addr = 0xA1D5 + 60 * k
        rom[p + 2 * k:p + 2 * k + 2] = bytes((addr & 0xFF, addr >> 8))
        s = fx.lorom(0x010000 | addr)
        rom[s:s + 60] = bytes([k + 1] * 60)
    rom[fx.lorom(ts.NIGHT_OBJ):fx.lorom(ts.NIGHT_OBJ) + 60] = b'\xEE' * 60
    rom[fx.lorom(ts.DAY_OBJ):fx.lorom(ts.DAY_OBJ) + 60] = b'\xDD' * 60
    return bytes(rom)


class TimeTest(unittest.TestCase):
    def test_sets_follow_dq5_table(self):
        rom = time_rom()
        want = {0x0000: 'A2C5', 0x0001: 'A289', 0x0050: 'A24D', 0x00ED: 'A24D', 0x00EE: 'A289', 0x00EF: 'A2C5',
                0x00F0: 'A301', 0x00F1: 'A33D', 0x00F2: 'A379', 0x01FC: 'A379', 0x01FD: 'A33D', 0x01FE: 'A301',
                0x01FF: 'A301'}
        for t, s in want.items():
            self.assertEqual(ts.expected_palette(rom, t)['set'], s, f'{t:04X}')

    def test_night_objects_from_index_0c(self):
        rom = time_rom()
        for t, night in ((0x00F0, 0), (0x00F1, 1), (0x01FD, 1), (0x01FE, 0), (0x0050, 0)):
            got = ts.expected_palette(rom, t)
            self.assertEqual(got['night_obj'], night, f'{t:04X}')
            self.assertEqual(got['obj11'], ('ee' if night else 'dd') * 30)

    def test_field_colours_1_to_13(self):
        got = ts.expected_palette(time_rom(), 0x0050)
        self.assertEqual(len(bytes.fromhex(got['line2'])), 2 * ts.FIELD_COLORS)
        self.assertEqual(got['line2'], '03' * 26)

    def test_judge_palette_names_lines(self):
        want = ts.expected_palette(time_rom(), 0x0050)
        got = dict(want, obj12='00', night_obj=1)
        self.assertEqual(ts.judge_palette(want, got), ['obj12', 'night_obj'])


class VerdictTest(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(ts.verdict('inn_stay', []), 'passed')
        self.assertEqual(ts.verdict('inn_stay', ['x']), 'failed')

    def test_known_only_with_its_own_problem(self):
        self.assertEqual(ts.verdict('church_cure', ['대화가 끝나지 않음']), 'known')
        self.assertEqual(ts.verdict('church_cure', ['대화가 끝나지 않음', '금화']), 'failed')
        self.assertEqual(ts.verdict('church_cure', ['대화가 끝나지 않음'], known=False), 'failed')

    def test_known_fixed_turns_red(self):
        problems = []
        self.assertEqual(ts.verdict('church_cure', problems), 'failed')
        self.assertIn('KNOWN', problems[0])

    def test_field_colour_known(self):
        self.assertEqual(ts.verdict('dusk', ['시각 00EE: 600 프레임 걸어도 line2 가 표(벌 A289)와 다름']), 'known')
        self.assertEqual(ts.verdict('dusk', ['시간 멈춤 7E:2190 bit1 이 켜져 있음(02)']), 'failed')


if __name__ == '__main__':
    unittest.main()
