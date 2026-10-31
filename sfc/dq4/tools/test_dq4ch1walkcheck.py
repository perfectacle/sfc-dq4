import unittest

import dq4ch1walkcheck as wc


class Ch1WalkCheckTests(unittest.TestCase):
    def test_boss_patch_sets_hp_one_and_defence_zero(self):
        rom = bytearray(0x200000)
        for n in (0xE2, 0x52):
            base = wc.MONSTERS + n * 25
            rom[base + 2], rom[base + 3], rom[base + 8], rom[base + 10] = 36, 250, 0xFF, 0xFF
        patch = dict(p.split('=') for p in wc.boss_patch(rom).split(';'))
        for n in (0xE2, 0x52):
            base = wc.MONSTERS + n * 25
            for off, value in ((2, 0), (3, 1), (8, 0xBF), (10, 0xF8)):
                rom[base + off] = int(patch[f'{base + off:X}'], 16)
            self.assertEqual(rom[base + 3] | (rom[base + 10] & 7) << 8, 1)
            self.assertEqual(rom[base + 2] | (rom[base + 8] >> 6 & 1) << 8, 0)
            self.assertEqual(rom[base + 8] | 0x40, 0xFF)

    def test_segments(self):
        names = [s[0] for s in wc.SEGMENTS]
        self.assertEqual(len(names), len(set(names)))
        for name, how, arg, opt in wc.SEGMENTS:
            self.assertIn(how, ('warp', 'walk'), name)
            for k in (*opt.get('want', ()), *opt.get('off', ())):
                self.assertIn(k, wc.FLAGS, name)
            if how == 'walk':
                for tok in arg.split(';'):
                    self.assertRegex(tok, r'^(\d+,\d+|[a-z]+:\d+)$', name)

    def test_frames_cover_presses(self):
        self.assertEqual(wc.frames('a:8;wait:50;3,4'), 300 + 58 + 400)


if __name__ == '__main__':
    unittest.main()
