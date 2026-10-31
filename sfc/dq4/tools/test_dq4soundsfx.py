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

    def test_same_body_is_kept_once_and_replaced_original_is_dropped(self):
        body = ['L0006:', '  note 05 len 02', '  end']
        one = sfx.splice(ORIGINAL, {1: (['L0006'], body)})
        both = sfx.splice(ORIGINAL, {0: (['L0006'], body), 1: (['L0006'], body)})
        self.assertEqual(notes(both, 0), notes(both, 1))
        self.assertEqual(notes(both, 1), notes(one, 1))
        # 갈래를 모두 바꾸면 원래 본문(음 20·21)이 남지 않는다
        self.assertNotIn(0x21, both)
        self.assertLess(len(both), len(one) + 3)


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
        entries, body, dropped, more = sfx.convert_branch(score, sfx.noise_program_map(score))
        self.assertEqual((dropped, more), (0, []))
        self.assertIn('  noise_on', body)
        self.assertNotIn(['rest', 'len', '30'], [ln.split() for ln in body])
        seq = sfx.splice(ORIGINAL, {1: (entries, body)})
        self.assertEqual([n for _, n, noise in notes(seq, 1)[0]],
                         [port.noise_frequency(60 + t) for t in (0, 4, 8)])


class WaveTests(unittest.TestCase):
    SCORE = {'tempo': 120, 'ticks_per_quarter': 48, 'end_tick': 16, 'volume': 127,
             'timeline': [{'op': 'note', 'tick': 0, 'ch': 'track0', 'note': 60, 'velocity': 100, 'gate': 2, 'program': 5,
                           'uid': 0}],
             'instruments': {'5': {'type': 'PCM', 'regions': [{'lo': 0, 'hi': 127, 'sample': 'w.wav', 'base': 60}]}}}

    def test_wave_programs_map_to_resident_waves_and_others_refuse(self):
        self.assertEqual(sfx.noise_program_map(self.SCORE, {'w.wav': 0x22}),
                         {5: [{'lo': 0, 'hi': 127, 'sample': 0x22}]})
        self.assertIsNone(sfx.noise_program_map(self.SCORE, {'other.wav': 0x22}))

    def test_instrument_follows_the_record_order_and_adds_missing_waves(self):
        program_map = sfx.noise_program_map(self.SCORE, {'w.wav': 0x22})
        _, body, _, more = sfx.convert_branch(self.SCORE, program_map, [0x1F, 0x20, 0x22])
        self.assertIn('  instrument 02', body)
        self.assertEqual(more, [])
        _, body, _, more = sfx.convert_branch(self.SCORE, program_map, [0x1F])
        self.assertIn('  instrument 01', body)
        self.assertEqual(more, [0x22])


class SpareTests(unittest.TestCase):
    def test_one_base_keeps_pitch_and_splits_regions(self):
        score = {'instruments': {'57': {'type': 'PCM', 'regions': [
                    {'lo': 0, 'hi': 12, 'base': 8, 'sample': 'a.wav'},
                    {'lo': 25, 'hi': 36, 'base': 32, 'sample': 'b.wav'}]}},
                 'timeline': [{'op': 'note', 'program': 57, 'note': 1, 'bend': 22, 'bend_range': 12},
                              {'op': 'note', 'program': 57, 'note': 36, 'bend': 0, 'bend_range': 12}]}
        out = sfx.one_base(score)
        first, second = [e for e in out['timeline'] if e['op'] == 'note']
        # 기준음 8 → 60(+52), 벤드 22×12 = 264 단위 중 256(2반음)은 음으로, 나머지 8 단위는 벤드 1(12 단위)로
        self.assertEqual((first['note'], first['bend']), (1 + 52 + 2, 1))
        self.assertEqual((second['note'], second['bend']), (36 + 28, 0))
        self.assertNotEqual(first['program'], second['program'])
        for e in (first, second):
            (region,) = out['instruments'][str(e['program'])]['regions']
            self.assertEqual((region['lo'], region['hi'], region['base']), (0, 127, sfx.BASE_KEY))

    def test_notes_above_the_pitch_limit_drop_by_octaves_and_slides_stop_at_it(self):
        score = {'instruments': {'1': {'type': 'PCM', 'regions': [{'lo': 0, 'hi': 127, 'base': 60, 'sample': 'a.wav'}]}},
                 'timeline': [{'op': 'note', 'program': 1, 'note': 110, 'bend': 0, 'slide': (20, 4)}]}
        (note,) = sfx.one_base(score)['timeline']
        self.assertEqual(note['note'], 110 - 24)
        self.assertEqual(note['slide'], (sfx.BASE_KEY + sfx.MAX_SHIFT - note['note'], 4))

    def test_bend_slides_follow_the_bends_written_while_the_note_sounds(self):
        dump = """[track0] $9A58
  9A58  C7 00         note-wait 0
  9A63  C5 3C         bend-range 60
  9A6A  C4 FE         bend -2
  9A6C  47 7F 03      note B4(47) vel=127 gate=3
  9A6F  C4 08         bend 8
  9A75  80 01         rest len=1
  9A85  C4 50         bend 80
  9A87  80 02         rest len=2
  9A89  4B 7F 04      note D#5(4B) vel=127 gate=4
"""
        score = {'timeline': [{'op': 'note', 'ch': 'track0', 'tick': 0, 'note': 71, 'gate': 3, 'bend': -2},
                              {'op': 'note', 'ch': 'track0', 'tick': 3, 'note': 75, 'gate': 4, 'bend': 80}]}
        first, second = sfx.bend_slides(score, dump)['timeline']
        self.assertEqual(first['slide'], (round(82 * 60 / 128), 1))   # 틱 1 의 벤드 80 까지
        self.assertNotIn('slide', second)

    def test_slide_note_sounds_one_tick_then_slides_and_ties(self):
        score = {'tempo': 120, 'ticks_per_quarter': 48, 'end_tick': 16, 'volume': 127,
                 'timeline': [{'op': 'note', 'tick': 0, 'ch': 'track0', 'note': 60, 'velocity': 100, 'gate': 8,
                               'program': 5, 'uid': 0, 'slide': (-12, 6)}],
                 'instruments': {'5': {'type': 'PCM', 'regions': [{'lo': 0, 'hi': 127, 'sample': 'w.wav', 'base': 60}]}}}
        _, body, _, _ = sfx.convert_branch(score, sfx.noise_program_map(score, {'w.wav': 0x22}), [0x22])
        words = [ln.split() for ln in body]
        at = next(i for i, w in enumerate(words) if w[:1] == ['note'])
        self.assertEqual(words[at][2:], ['len', '01'])
        self.assertEqual(words[at + 1], ['pitch_slide', 'F4', '06'])
        self.assertEqual(next(w[0] for w in words[at + 2:] if w[0] != 'gate_preset'), 'tie')

    def test_silent_branch_and_spare_sequence_play_only_their_branches(self):
        base = assemble(['tempo 3C', 'track Lnone', 'Lnone:', '  end'])
        seq = sfx.splice(base, {7: (['L0006'], ['L0006:', '  note 30 len 02', '  end']), 3: ([], [])})
        self.assertEqual(notes(seq, 7), [[(0, 0x30, False)]])
        self.assertEqual(notes(seq, 3), [[]])
        self.assertEqual(notes(seq, 0), [[]])


if __name__ == '__main__':
    unittest.main()
