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
        self.assertTrue(any(moved[groups[0]['at']:groups[0]['at'] + 16]))
        self.assertEqual(groups[0]['at'], lorom(0x558000))     # 합성 롬은 넷째 자리가 비어 있음
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
        # 넷째 자리에 놓인 메시지 뒤로 비켜 두고, 자리가 모자라면 멈춘다
        taken = bytearray(self.rom)
        taken[lorom(0x55A000)] = 1
        moved, groups = mb.test_rom(bytes(taken))
        self.assertEqual(groups[0]['at'], lorom(0x55A100))
        full = bytearray(self.rom)
        full[lorom(0x56F000)] = 1
        with self.assertRaisesRegex(ValueError, '빈 곳이 모자람'):
            mb.test_rom(bytes(full))


if __name__ == '__main__':
    unittest.main()
