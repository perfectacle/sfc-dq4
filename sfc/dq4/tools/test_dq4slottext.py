import os
from pathlib import Path
import unittest

import dq4slottext as slot
from dq5map import lorom

DQ5 = Path(__file__).resolve().parents[3] / 'rom' / 'dq5.sfc'


@unittest.skipUnless(DQ5.is_file() and os.environ.get('DQ4_GALMURI'), 'DQ5 롬과 DQ4_GALMURI 가 필요')
class SlotTextTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import dq4menupatch
        cls.font = dq4menupatch.Font(slot.FONT)
        # 빌드 롬은 4MB 로 늘린 뒤라 코드 자리(4F:F800)가 원래 롬 밖이다
        cls.rom = DQ5.read_bytes().ljust(0x400000, b'\0')
        cls.out = slot.apply(cls.rom, cls.font)

    def test_original_strings_are_kana(self):
        for name, at, ldy, _ in slot.TEXTS:
            self.assertEqual(self.rom[lorom(ldy):lorom(ldy) + 2], (at & 0xFFFF).to_bytes(2, 'little'), name)
            self.assertTrue(slot.kana_in(self.rom, ldy), name)

    def test_patched_strings_have_no_kana(self):
        for name, _, ldy, _ in slot.TEXTS:
            self.assertEqual(slot.kana_in(self.out, ldy), [], name)

    def test_strings_stay_before_the_payout_table(self):
        lay = slot.Layout(self.font)
        self.assertLessEqual(sum(map(len, lay.strings.values())), slot.STRINGS_END - slot.STRINGS_AT)
        o = lorom(slot.STRINGS_END)
        self.assertEqual(self.out[o:o + 3], self.rom[o:o + 3])

    def test_tile_numbers_never_read_as_control_bytes(self):
        lay = slot.Layout(self.font)
        controls = {slot.END, *slot.MARKS, slot.SKIP, slot.BIT8, slot.NUMBER, slot.NEWLINE}
        self.assertFalse({n & 0xFF for n, _ in lay.tiles} & controls)
        self.assertTrue(all(slot.FIRST_TILE <= n < slot.TILE_END for n, _ in lay.tiles))

    def test_hook_calls_the_original_screen_setup_first(self):
        o = lorom(slot.HOOK_AT)
        self.assertEqual(self.out[o:o + 4], bytes((0x22, *slot.CODE_AT.to_bytes(3, 'little'))))
        c = lorom(slot.CODE_AT)
        self.assertEqual(self.out[c:c + 4], bytes((0x22, *slot.SCREEN_INIT.to_bytes(3, 'little'))))


if __name__ == '__main__':
    unittest.main()
