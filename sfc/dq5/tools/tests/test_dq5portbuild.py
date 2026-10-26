"""통합 포팅 빌드의 빈 자리·배치·고정 패치 예약을 원본 롬 없이 검사한다."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dq5hangul import expand  # noqa: E402
from dq5portbuild import (  # noqa: E402
    BANK, AllocationError, Piece, Space, allocate, fit, fixed_mask, mask_ranges, occupied, split_banks, summary,
    window_range,
)

LOW, HIGH = window_range('low'), window_range('high')


def bank(b, low=0x8000):
    return b * BANK + low - 0x8000


class SpaceTests(unittest.TestCase):
    def test_merge_take_and_measure(self):
        space = Space([(10, 20), (15, 30), (40, 50), (5, 5)])
        self.assertEqual(space.ranges, [[10, 30], [40, 50]])
        self.assertTrue(space.contains(12, 30))
        self.assertFalse(space.contains(25, 41))
        space.take(12, 14)
        self.assertEqual(space.ranges, [[10, 12], [14, 30], [40, 50]])
        self.assertEqual((space.total(0, 100), space.largest(0, 100), space.total(11, 45)), (28, 16, 1 + 16 + 5))

    def test_mask_ranges_and_bank_split(self):
        self.assertEqual(mask_ranges(bytearray(b'\0\1\1\0\1')), [(1, 3), (4, 5)])
        # 원래 롬 자리(CPU 주소 쓰기)는 뱅크에서 자르고, 늘린 자리(파일 위치 쓰기)는 그대로 둔다.
        self.assertEqual(split_banks([(0x7FF0, 0x8010), (bank(0x30, 0xFFF0), bank(0x31, 0x8010))]),
                         [(0x7FF0, 0x8000), (0x8000, 0x8010), (bank(0x30, 0xFFF0), bank(0x31, 0x8010))])


class LayoutTests(unittest.TestCase):
    def test_stream_head_and_window_end(self):
        piece = Piece('t', 't', 'stream', [0x9000], ['low'], head=0x200)
        self.assertEqual(piece.layout(bank(0x30, 0xFE00), 'low'), [(bank(0x30, 0xFE00), bank(0x30, 0xFE00) + 0x9000)])
        self.assertIsNone(piece.layout(bank(0x30, 0xFE01), 'low'))       # 머리가 뱅크를 넘음
        self.assertIsNone(piece.layout(bank(0x3F, 0x9000), 'low'))       # 3F 끝을 넘음
        self.assertIsNone(piece.layout(bank(0x40), 'low'))               # 창 밖
        self.assertIsNotNone(piece.layout(bank(0x60), 'high'))

    def test_chunks_skip_to_next_bank(self):
        piece = Piece('f', 'f', 'chunks', [0x100, 0x7F80, 0x10], ['low'])
        self.assertEqual(piece.layout(bank(0x30, 0xFF00), 'low'),
                         [(bank(0x30, 0xFF00), bank(0x31)), (bank(0x31), bank(0x31, 0xFF80)),
                          (bank(0x31, 0xFF80), bank(0x31, 0xFF90))])
        self.assertIsNone(Piece('f', 'f', 'chunks', [BANK + 1], ['low']).layout(bank(0x30), 'low'))
        self.assertIsNone(Piece('f', 'f', 'chunks', [0x100, 0x100], ['low']).layout(bank(0x3F, 0xFF80), 'low'))


class AllocateTests(unittest.TestCase):
    def test_first_fit_uses_holes_and_bank_starts(self):
        # 30 뱅크 끝 0x100 + 31 뱅크 전체가 비어 있다. 덩어리 0x200 은 30 끝에 못 들어가 31:8000 으로 간다.
        space = Space([(bank(0x30, 0xFF00), bank(0x32))])
        got = fit(Piece('e', 'e', 'chunks', [0x200], ['low']), space)
        self.assertEqual(got[0], bank(0x31))
        got = fit(Piece('e', 'e', 'chunks', [0x80, 0x200], ['low']), space)
        self.assertEqual(got[2], [(bank(0x30, 0xFF00), bank(0x30, 0xFF80)), (bank(0x31), bank(0x31, 0x8200))])
        # --at 은 건너뛴 뒤의 첫 덩어리 자리: 건너뛰지 않는 쓰기 도구(인물 목록)에도 그대로 준다.
        space = Space([(bank(0x30, 0xF000), bank(0x32))])
        self.assertEqual(fit(Piece('n', 'n', 'chunks', [0x2000], ['low']), space)[0], bank(0x31))

    def test_window_preference_and_fallback(self):
        space = Space([LOW, HIGH])
        flexible = Piece('t', 't', 'stream', [0x1000], ['high', 'low'])
        self.assertEqual(fit(flexible, space)[1], 'high')
        space = Space([LOW, (HIGH[0], HIGH[0] + 0x800)])
        self.assertEqual(fit(flexible, space)[1:], ('low', [(LOW[0], LOW[0] + 0x1000)]))

    def test_apart_pieces_land_in_different_banks(self):
        space = Space([(bank(0x30), bank(0x30, 0xC000)), (bank(0x33), bank(0x34))])
        a = Piece('npc', 'npc.base', 'chunks', [0x1000], ['low'], apart='npc.alt')
        b = Piece('npc', 'npc.alt', 'chunks', [0x1000], ['low'], apart='npc.base')
        placed = allocate([a, b], space)
        banks = {name: v['at'] // BANK for name, v in placed.items()}
        self.assertNotEqual(banks['npc.base'], banks['npc.alt'])
        self.assertEqual(sorted(banks.values()), [0x30, 0x33])

    def test_constrained_and_pinned_first(self):
        space = Space([(LOW[0], LOW[0] + 0x3000), HIGH])
        low = Piece('m', 'm', 'stream', [0x2000], ['low'])
        flexible = Piece('t', 't', 'stream', [0x2800], ['low', 'high'])
        pinned = Piece('p', 'p', 'stream', [0x100], ['low'], pin=LOW[0] + 0x2F00)
        placed = allocate([flexible, low, pinned], space)
        self.assertEqual(placed['p']['at'], LOW[0] + 0x2F00)
        self.assertEqual((placed['m']['window'], placed['t']['window']), ('low', 'high'))

    def test_failure_reports_needed_and_free(self):
        space = Space([(LOW[0], LOW[0] + 0x1000), (bank(0x31), bank(0x31, 0x9000))])
        pieces = [Piece('maps', 'maps', 'stream', [0x1800], ['low']),
                  Piece('field', 'field', 'chunks', [0x800], ['low'])]
        with self.assertRaises(AllocationError) as caught:
            allocate(pieces, space)
        text = str(caught.exception)
        self.assertIn('maps 6144바이트', text)
        self.assertIn('이 창만 쓰는 것 8192바이트', text)
        self.assertIn('빈 자리 8192바이트(가장 긴 연속 4096바이트)', text)
        stats = summary(pieces, Space([LOW]))
        self.assertEqual((stats['low']['needed_only_here'], stats['high']['needed_only_here']), (0x2000, 0))


class FixedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        original = bytearray(0x180000)
        for i in range(0x100000, 0x180000, 7):
            original[i] = (i >> 3) & 0xFF | 1
        cls.original = bytes(original)

    def title_rom(self):
        rom = bytearray(expand(self.original, 4))
        rom[0x180000:0x200000] = self.original[0x100000:]                   # 타이틀 빌드의 거울 채우기
        rom[0x188000:0x188100] = bytes(0x100)                               # 선언한 자리의 0 도 예약
        rom[0x190000:0x190040] = b'\xAA' * 0x40
        rom[0x1A0010] ^= 0xFF                                               # 다른 단계가 거울 안에 쓴 1바이트
        rom[0x300000:0x300004] = b'\x00\x00\x12\x00'                        # 60 뱅크 자료(첫 0 포함)
        rom[0x318000:0x318008] = bytes(8)                                   # 63 뱅크: 표지만 지운 빈 뱅크
        return bytes(rom)

    def test_mirror_is_freed_but_declared_and_other_writes_held(self):
        rom = self.title_rom()
        mask, hold, freed = fixed_mask(self.original, rom, [(0x188000, 0x188100), (0x190000, 0x190040)])
        self.assertIn((0x188000, 0x188100), hold)
        self.assertIn((0x1A0010 - 64, 0x1A0011 + 64), hold)
        self.assertEqual(mask[0x190000], 1)
        self.assertEqual(mask[0x1A0010], 1)
        self.assertEqual(mask[0x1B0000], 0)
        self.assertGreater(freed, 0)
        occ = occupied(mask, hold)
        self.assertIn((0x300000, 0x308000), occ)                            # 쓴 바이트가 있는 뱅크 전체
        self.assertFalse(any(s <= 0x318000 < e for s, e in occ))            # 표지만 다른 빈 뱅크는 비어 있음
        self.assertFalse(any(s <= 0x1B0000 < e for s, e in occ))

    def test_superseded_range_is_not_occupied(self):
        rom = self.title_rom()
        mask, hold, _ = fixed_mask(self.original, rom, [(0x188000, 0x188100)])
        occ = occupied(mask, hold, [(0x300000, 0x301000)])
        self.assertIn((0x301000, 0x308000), occ)
        self.assertFalse(any(s <= 0x300000 < e for s, e in occ))

    def test_write_outside_title_mirror_without_keep(self):
        rom = self.title_rom()
        mask, hold, freed = fixed_mask(self.original, rom)
        self.assertIsNone(hold)
        self.assertEqual(freed, 0)
        occ = occupied(mask, hold)
        self.assertIn((0x180000, 0x200000), occ)                            # 거울 구간도 뱅크 단위로 전부
        with self.assertRaises(ValueError):
            fixed_mask(self.original, rom[:0x180000 + 5])


if __name__ == '__main__':
    unittest.main()
