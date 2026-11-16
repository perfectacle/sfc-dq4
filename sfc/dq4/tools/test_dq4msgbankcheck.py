import unittest
from unittest import mock

import dq4menumsg as mm
import dq4msgbankcheck as mb
from test_dq4menumsg import FakeFont, original, synthetic_rom


class TestRomTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with mock.patch.object(mm, 'message', original):
            cls.rom, _ = mm.apply(bytes(synthetic_rom()), FakeFont())

    def test_groups_move_to_both_free_banks_and_across_their_border(self):
        from dq5map import Rom, lorom
        moved, groups = mb.test_rom(self.rom)
        self.assertEqual([g['bank'] for g in groups], [0x55, 0x55, 0x56])
        self.assertEqual([g['cross'] for g in groups], [False, True, False])
        from dq5textwrite import index_table, relocated
        index = index_table(moved, relocated(moved)[1])[0]
        banks = {Rom(moved).u24(index + 3 * g['group']) >> 19 for g in groups}
        self.assertEqual(banks, {0x1E, 0x1F})
        self.assertTrue(any(moved[lorom(0x558000):lorom(0x558000) + 16]))
        for g in groups:
            first = g['group'] * 16
            self.assertEqual(g['expected'][:2], original(None, first))
            self.assertEqual(len(g['expected']), 2 * (g['swap'] - first + 1))
        self.assertEqual({swap for _, swap in mb.CASES}, {g['swap'] for g in groups})
        self.assertEqual({scene for scene, _ in mb.CASES}, set(mb.SCENES))

    def test_refuses_or_hook_and_taken_space(self):
        from dq5map import lorom
        from dq5hangul import WALK_INDEX_STUB
        bad = bytearray(self.rom)
        o = lorom(WALK_INDEX_STUB)
        bad[o:o + 10] = bytes.fromhex('20 8d 8c a5 f2 09 60 85 f2 60')
        with self.assertRaisesRegex(ValueError, '표 꼴'):
            mb.test_rom(bytes(bad))
        taken = bytearray(self.rom)
        taken[lorom(0x56A000)] = 1
        with self.assertRaisesRegex(ValueError, '비어 있지 않음'):
            mb.test_rom(bytes(taken))


if __name__ == '__main__':
    unittest.main()
