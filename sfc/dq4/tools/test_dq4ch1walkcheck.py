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
        for segments in (wc.SEGMENTS, wc.SEGMENTS[:-2] + wc.CHAPTER2_END):
            self.check_segments(segments)
        self.assertEqual([s[0] for s in wc.SEGMENTS[-3:]], ['castle', 'king', 'ending'])

    def check_segments(self, segments):
        names = [s[0] for s in segments]
        self.assertEqual(len(names), len(set(names)))
        for name, how, arg, opt in segments:
            self.assertIn(how, ('warp', 'walk', 'ending'), name)
            for k in (*opt.get('want', ()), *opt.get('off', ())):
                self.assertIn(k, wc.FLAGS, name)
            if how == 'walk':
                for tok in arg.split(';'):
                    self.assertRegex(tok, r'^(\d+,\d+|[a-z]+:\d+)$', name)

    def test_units_split_at_warps(self):
        for segments in (wc.SEGMENTS, wc.SEGMENTS[:-2] + wc.CHAPTER2_END):
            groups = wc.units(segments)
            self.assertEqual(groups[0], [0])
            self.assertEqual([i for u in groups for i in u], list(range(len(segments))))
            for u in groups[1:]:
                self.assertTrue(all(segments[i][1] != 'warp' for i in u[1:]))
                self.assertTrue(segments[u[0]][1] == 'warp' or u[0] == 1)
        names = [[wc.SEGMENTS[i][0] for i in u] for u in wc.units(wc.SEGMENTS)]
        self.assertIn(['castle_town', 'field', 'fly', 'kidnap'], names)
        self.assertIn(['castle', 'king', 'ending'], names)

    def test_setup_carries_flags_and_effects(self):
        names = [s[0] for s in wc.SEGMENTS]
        extra, party = wc.setup(wc.SEGMENTS, names.index('castle'))
        sets = extra.split(';')
        for k in ('CHAPTER1', 'HOIMIN', 'BOSS_WON', 'SOLDIER'):
            addr, mask = wc.FLAGS[k]
            self.assertIn(f'{addr & 0xFFFF:04X}|{mask:02X}', sets, k)
        addr, mask = wc.FLAGS['KIDS_FOLLOW']
        self.assertNotIn(f'{addr & 0xFFFF:04X}|{mask:02X}', sets)   # homecoming 이 끔
        self.assertIn('2058=CD', sets)
        self.assertIn('29EF|01', sets)
        self.assertEqual(party, '05')
        self.assertEqual(wc.setup(wc.SEGMENTS, names.index('hoimin_side')), (
            ';'.join(f'{wc.FLAGS[k][0] & 0xFFFF:04X}|{wc.FLAGS[k][1]:02X}'
                     for k in ('CHAPTER1', 'NIGHT_TOLD', 'FLARE', 'REUNITED')), ''))
        self.assertEqual(wc.setup(wc.SEGMENTS, 0), ('', ''))

    def test_pins_fix_rng_and_time(self):
        self.assertEqual(wc.pins({}), wc.RNG + ';' + wc.DAY_SET)
        self.assertEqual(wc.pins({'poke': wc.NIGHT + ';' + wc.HOLD_CHILD}), wc.RNG + ';' + wc.NIGHT_SET)
        self.assertEqual({a for a, _ in (p.split('=') for p in wc.RNG.split(';'))}, {'075B', '075C', '075D'})

    def test_trace_ignores_repeated_warp_end(self):
        once = 'f00002 anywhere\nf00259 end map 37/00\nflags 7E2190: 00\n'
        twice = once + 'f00260 end map 37/00\nflags 7E2190: 00\n'
        self.assertEqual(wc.trace_text('warp.txt', twice), once)
        self.assertEqual(wc.trace_text('walk.txt', twice), twice)

    def test_frames_cover_presses(self):
        self.assertEqual(wc.frames('a:8;wait:50;3,4'), 300 + 58 + 400)


if __name__ == '__main__':
    unittest.main()
