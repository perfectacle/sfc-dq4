import argparse
import hashlib
import tempfile
import unittest
from pathlib import Path

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

    def test_seed_zero_is_the_fixed_rng(self):
        self.assertEqual(wc.rng_for(0), '075B=00;075C=00;075D=00')
        self.assertEqual(wc.pins({}, 0), wc.pins({}))

    def test_seed_values_are_deterministic(self):
        for seed in (1, 2, 16, 123456):
            text = wc.rng_for(seed)
            self.assertEqual(text, wc.rng_for(seed))
            self.assertRegex(text, r'^075B=[0-9A-F]{2};075C=[0-9A-F]{2};075D=[0-9A-F]{2}$')
            self.assertTrue(wc.pins({}, seed).startswith(text + ';'))
        # 바뀌면 이미 기록한 시드 결과와 견줄 수 없으므로 값을 묶어 둔다
        self.assertEqual(wc.rng_for(1), '075B=44;075C=20;075D=82')
        self.assertEqual(wc.rng_for(2), '075B=1C;075C=2E;075D=2B')
        self.assertGreater(len({wc.rng_for(s) for s in range(32)}), 30)

    def test_seed_args(self):
        ap = argparse.ArgumentParser()
        wc.add_seed_args(ap)
        self.assertEqual(wc.seeds_of(ap.parse_args([])), [0])
        self.assertEqual(wc.seeds_of(ap.parse_args(['--seed', '7'])), [7])
        self.assertEqual(wc.seeds_of(ap.parse_args(['--seeds', '0,5,9,5'])), [0, 5, 9])
        self.assertFalse(ap.parse_args([]).no_state_cache)
        with self.assertRaises(SystemExit):
            wc.seeds_of(ap.parse_args(['--seeds', '-1']))
        out = Path('o')
        self.assertEqual(wc.seed_dir(out, 3, [3]), out)
        self.assertEqual(wc.seed_dir(out, 3, [0, 3]), out / 'seed-3')

    def test_state_cache_key_is_rom_sha1(self):
        rom = bytes(range(256)) * 4
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache = wc.StateCache(rom, root)
            self.assertEqual(cache.folder, root / 'prologue' / hashlib.sha1(rom).hexdigest())
            self.assertIsNone(cache.get('prologue', 'k1', '.mss'))
            src = root / 'end.mss'
            src.write_bytes(b'state')
            stored = cache.put('prologue', 'k1', '.mss', src, {'name': 'prologue', 'status': 'passed'})
            self.assertEqual(stored, cache.folder / 'prologue-k1.mss')
            state, result = wc.StateCache(rom, root).get('prologue', 'k1', '.mss')
            self.assertEqual((state.read_bytes(), result['status']), (b'state', 'passed'))
            self.assertIsNone(cache.get('prologue', 'k2', '.mss'))
            self.assertIsNone(wc.StateCache(rom + b'\0', root).get('prologue', 'k1', '.mss'))
            self.assertEqual(sorted(f.name for f in cache.folder.iterdir()), ['prologue-k1.json', 'prologue-k1.mss'])
            # 결과 .json 이 없으면 상태를 반쯤 쓴 것으로 본다
            (cache.folder / 'prologue-k1.json').unlink()
            self.assertIsNone(cache.get('prologue', 'k1', '.mss'))
            self.assertEqual(wc.fingerprint('a', src), wc.fingerprint('a', src))
            src.write_bytes(b'other')
            self.assertNotEqual(wc.fingerprint('a', src), wc.fingerprint('a', b'state'.decode()))
            self.assertNotEqual(wc.fingerprint('a', src), wc.fingerprint('b', src))

    def test_prologue_key_covers_inputs(self):
        before = wc.prologue_inputs()
        self.assertIn(wc.PROLOGUE_START['SEQ'], before)
        self.assertIn(wc.RNG, before)
        old = wc.PROLOGUE_START['TAPUNTIL']
        try:
            wc.PROLOGUE_START['TAPUNTIL'] = old + '0'
            self.assertNotEqual(wc.prologue_inputs(), before)
        finally:
            wc.PROLOGUE_START['TAPUNTIL'] = old

    def test_trace_ignores_repeated_warp_end(self):
        once = 'f00002 anywhere\nf00259 end map 37/00\nflags 7E2190: 00\n'
        twice = once + 'f00260 end map 37/00\nflags 7E2190: 00\n'
        self.assertEqual(wc.trace_text('warp.txt', twice), once)
        self.assertEqual(wc.trace_text('walk.txt', twice), twice)

    def test_frames_cover_presses(self):
        self.assertEqual(wc.frames('a:8;wait:50;3,4'), 300 + 58 + 400)


if __name__ == '__main__':
    unittest.main()
