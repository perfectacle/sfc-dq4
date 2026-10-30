import unittest

import dq4soundport as port
import dq4soundsfx as sfx
from dq5song import assemble, play


def notes(seq, flag):
    return [[(t, n, noise) for t, n, _, noise in track if n not in (None, 'tie')] for track in play(seq, 200, flag)]


ORIGINAL = assemble([
    'tempo 3C', 'track L0004',
    'L0004:', '  if_flag 01 -> L0010', '  note 20 len 04', '  end',
    'L0010:', '  note 21 len 04', '  end',
])


class SpliceTests(unittest.TestCase):
    def test_replaced_branch_plays_new_tracks_and_others_stay(self):
        body = ['L0006:', '  noise_on', '  note 05 len 02', '  end', 'L0009:', '  note 30 len 02', '  end']
        seq = sfx.splice(ORIGINAL, {1: (['L0006', 'L0009'], body)})
        self.assertEqual(notes(seq, 0), [[(0, 0x20, False)], []])
        self.assertEqual(notes(seq, 1), [[(0, 0x05, True)], [(0, 0x30, False)]])

    def test_new_branch_silences_original_extra_tracks(self):
        two = assemble([
            'tempo 3C', 'track L0006', 'track L000E',
            'L0006:', '  if_flag 01 -> L0010', '  note 20 len 04', '  end',
            'L000E:', '  note 22 len 04', '  end',
            'L0010:', '  note 21 len 04', '  end',
        ])
        seq = sfx.splice(two, {1: (['L0006'], ['L0006:', '  note 05 len 02', '  end'])})
        self.assertEqual(notes(seq, 1), [[(0, 0x05, False)], []])
        self.assertEqual(notes(seq, 0), [[(0, 0x20, False)], [(0, 0x22, False)]])


class NoiseTests(unittest.TestCase):
    def test_noise_frequency_rises_with_the_note(self):
        picks = [port.noise_frequency(n) for n in range(40, 110, 6)]
        self.assertEqual(picks, sorted(picks))
        self.assertTrue(all(1 <= x <= 0x1F for x in picks))

    def test_noise_score_converts_without_samples(self):
        timeline = [{'op': 'note', 'tick': t, 'ch': 'track0', 'note': 60 + t, 'velocity': 100, 'gate': 2, 'program': 20,
                     'uid': i} for i, t in enumerate((0, 4, 8))]
        score = {'tempo': 120, 'ticks_per_quarter': 48, 'end_tick': 16, 'timeline': timeline, 'volume': 127,
                 'instruments': {'20': {'type': sfx.NOISE_TYPE, 'regions': []}}}
        entries, body, dropped = sfx.convert_branch(score, sfx.noise_program_map(score))
        self.assertEqual(dropped, 0)
        self.assertIn('  noise_on', body)
        self.assertNotIn(['rest', 'len', '30'], [ln.split() for ln in body])
        seq = sfx.splice(ORIGINAL, {1: (entries, body)})
        self.assertEqual([n for _, n, noise in notes(seq, 1)[0]],
                         [port.noise_frequency(60 + t) for t in (0, 4, 8)])


if __name__ == '__main__':
    unittest.main()
