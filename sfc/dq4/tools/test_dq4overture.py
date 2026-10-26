from pathlib import Path
import unittest

import dq4overture as ov
from dq5song import assemble, play

ROOT = Path(__file__).resolve().parents[3]
NES, SFC = ROOT / 'rom' / 'dq4.nes', ROOT / 'rom' / 'dq5.sfc'


class WriterTests(unittest.TestCase):
    def test_long_note_is_tied_legato(self):
        w = ov.Writer()
        w.put(0x30, 0x200, 0xFE)
        self.assertEqual(w.lines, ['  gate_preset 00', '  note 30 len F0', '  tie', '  gate_preset FE', '  tie len 20'])

    def test_gate_preset_is_a_table_value(self):
        self.assertEqual(ov.gate_preset(0.5), 0x80)
        self.assertEqual(ov.gate_preset(0.75), 0xBF)

    def test_tempo_map_is_sorted_and_in_driver_range(self):
        ticks = [k for k, _ in ov.NDS_TEMPO]
        self.assertEqual(ticks, sorted(set(ticks)))
        self.assertTrue(all(0 < t < 0xFB for _, t in ov.NDS_TEMPO))
        self.assertEqual(ov.tempo_at(ov.FC_MARCH[0] + 100), 121)


@unittest.skipUnless(NES.exists() and SFC.exists(), 'rom/dq4.nes and rom/dq5.sfc are user supplied')
class ArrangementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from dq5map import Rom
        cls.score = ov.fc_score(str(NES))
        cls.rom = Rom(SFC.read_bytes())
        cls.snare = ov.reference_snare(cls.rom)
        cls.seq = assemble(ov.arrange(cls.score, cls.snare, ov.original_listing(cls.rom)))

    def test_every_fc_note_lands_on_twice_its_tick(self):
        cycle = ov.cycle_ticks(self.score)
        events = play(self.seq, cycle + 10, ov.OVERTURE_FLAG)
        tracks = {'pulse1': (0, 3), 'pulse2': (1, 2), 'triangle': (4, 5)}
        transpose = {2: -12, 5: -12}
        for ch, indices in tracks.items():
            want = [(e['tick'] * 2, round(e['midi']) - ov.MIDI_OFFSET) for e in self.score['timeline']
                    if e['ch'] == ch and e['op'] == 'note']
            for i in indices:
                got = [(t, n - transpose.get(i, 0)) for t, n, _, _ in events[i] if isinstance(n, int) and t < cycle]
                # 트랙 3(현)은 행진부터 선율을 겹친다. play 는 0 틱부터, FC 는 1 틱부터 센다
                start = ov.song_tick(ov.FC_MARCH[0]) + 2 if i == 3 else 0
                self.assertEqual([(t + 2, n) for t, n in got], [w for w in want if w[0] >= start], f'track {i}')

    def test_snare_matches_reference_track(self):
        from dq5spc import body, sequences
        _, addr, n = sequences(self.rom)[ov.REF_SONG]
        ref = play(bytes(body(self.rom, addr, n)), 12000)[ov.REF_SNARE_TRACK]
        lo, hi = ov.REF_MARCH
        shift = ov.song_tick(ov.FC_MARCH[0]) - lo
        want = [(t + shift, x) for t, x, _, _ in ref if isinstance(x, int) and lo <= t < hi]
        self.assertEqual([(t, x) for t, x, _ in self.snare], want)
        self.assertTrue(want)

    def test_overture_repeats(self):
        cycle = ov.cycle_ticks(self.score)
        ev = play(self.seq, 2 * cycle + 10, ov.OVERTURE_FLAG)[0]
        first = [(t, n) for t, n, _, _ in ev if isinstance(n, int) and t < cycle]
        second = [(t - cycle, n) for t, n, _, _ in ev if isinstance(n, int) and cycle <= t < 2 * cycle]
        self.assertEqual(first, second)

    def test_flag_zero_is_the_original_title_song(self):
        from dq5spc import body, sequences
        _, addr, n = sequences(self.rom)[ov.SONG]
        want = play(bytes(body(self.rom, addr, n)), 3000)
        got = play(self.seq, 3000)
        for i in range(len(want)):
            # 갈래를 고르는 if_flag·jump 는 시간을 쓰지 않으므로 음 시각까지 같다
            self.assertEqual([e[:2] for e in got[i]], [e[:2] for e in want[i]], f'track {i}')
        self.assertEqual(got[len(want)], [])

    def test_song_set_table(self):
        table, old = ov.set_table(self.rom)
        self.assertEqual(len(table) - old, len(ov.SAMPLES) - len(ov.ORIGINAL_SAMPLES))
        self.assertLessEqual(ov.SPC_SET_TABLE + len(table), ov.SPC_SAMPLE_AREA)


if __name__ == '__main__':
    unittest.main()
