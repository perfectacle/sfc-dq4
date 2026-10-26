"""NDS 악보 변환의 템포·세기 합치기와 시퀀스 시각을 검사한다."""
import unittest

import dq4soundport as port
from dq4soundport import DQ5_TICKS_PER_SECOND_PER_TEMPO as RATE


def seconds(points, tick):
    total = 0.0
    for (t, v), (nxt, _) in zip(points, points[1:] + [(tick, 0)]):
        if t >= tick:
            break
        total += (min(nxt, tick) - t) / (v * RATE)
    return total


def score(notes, tempo_changes=(), loop_start=None, end=None):
    timeline = [{'op': 'note', 'tick': t, 'gate': g, 'note': n, 'velocity': v, 'ch': 'track0', 'program': 0}
                for t, g, n, v in notes]
    end = end or max(t + g for t, g, _, _ in notes)
    result = {'ticks_per_quarter': 48, 'tempo': 120, 'tempo_changes': list(tempo_changes),
              'timeline': timeline, 'end_tick': end}
    if loop_start is not None:
        result |= {'loop_start': loop_start, 'loop_len': end - loop_start}
    return result


class TempoTests(unittest.TestCase):
    def test_rubato_merges_within_tolerance(self):
        points = [(t * 4, 120 + (t % 6)) for t in range(300)]
        merged, error = port.simplify_tempo(points, 1200, 0.012)
        self.assertLess(len(merged), len(points) // 4)
        self.assertLessEqual(error, 0.012)
        model = sorted(merged.items())
        for tick, _ in points:
            self.assertAlmostEqual(seconds(model, tick), seconds(points, tick), delta=0.0121)

    def test_constant_tempo_is_one_command(self):
        merged, error = port.simplify_tempo([(0, 100.0), (48, 100.0), (96, 100.0)], 480, 0.01)
        self.assertEqual(merged, {0: 100})
        self.assertAlmostEqual(error, 0)

    def test_large_step_is_kept(self):
        merged, _ = port.simplify_tempo([(0, 60.0), (480, 200.0)], 960, 0.01)
        self.assertEqual(merged, {0: 60, 480: 200})

    def test_sharp_tempo_drop_does_not_crash(self):
        merged, _ = port.simplify_tempo([(0, 140.0), (69, 244.0), (91, 2.45), (118, 200.0)], 177, 0.012)
        self.assertTrue(all(1 <= v <= 255 for v in merged.values()))

    def test_loop_start_restates_tempo(self):
        notes = [(t, 24, 60, 100) for t in range(0, 960, 24)]
        result = port.convert(score(notes, [(480, 120)], loop_start=480), voices=1)
        self.assertIn(480, dict(result.report['tempo_changes']))


class LevelTests(unittest.TestCase):
    def test_small_velocity_changes_share_one_command(self):
        notes = [(i * 24, 24, 60, 100 + i % 3) for i in range(16)]
        result = port.convert(score(notes), voices=1)
        self.assertEqual(result.text.count('volume2'), 1)
        self.assertGreater(result.report['level_changes_merged'], 0)
        self.assertLessEqual(result.report['level_max_error_db'], 1.0)

    def test_audible_velocity_change_is_written(self):
        notes = [(0, 24, 60, 100), (24, 24, 60, 50)]
        result = port.convert(score(notes), voices=1)
        self.assertEqual(result.text.count('volume2'), 2)

    def test_note_count_and_timing_survive_compaction(self):
        notes = [(i * 12, 12, 60 + i % 5, 100) for i in range(200)]
        result = port.convert(score(notes), voices=1)
        trace = port.execution_trace(result.sequence, 2400)[0]
        onsets = [t for t, raw in trace if raw[0] < 0xA0 and (raw[0] - 0x50 if raw[0] >= 0x50 else raw[0]) not in (0, 0x4F)]
        self.assertEqual(onsets, [i * 12 for i in range(200)])


def two_program_score(notes):
    timeline = [{'op': 'note', 'tick': t, 'gate': 20, 'note': 60, 'velocity': 100, 'ch': f'track{p}', 'program': p}
                for t, p in notes]
    return {'ticks_per_quarter': 48, 'tempo': 120, 'tempo_changes': [], 'timeline': timeline,
            'end_tick': max(t for t, _ in notes) + 24}


class StreamTests(unittest.TestCase):
    MAP = {0: 0x0A, 1: 0x18}

    def instruments(self, result):
        trace = port.execution_trace(result.sequence, 4000)[0]
        return [(t, raw[1]) for t, raw in trace if raw[0] == 0xF0]

    def test_seconds_to_tick_follows_tempo_changes(self):
        # 템포 100 은 초당 80틱, 200 은 160틱
        self.assertEqual(port.seconds_to_tick({0: 100, 480: 200}, 1.0), 80)
        self.assertEqual(port.seconds_to_tick({0: 100, 480: 200}, 7.0), 640)

    def test_sample_order_sets_instrument_index(self):
        result = port.convert(two_program_score([(0, 0), (24, 1)]), voices=1, program_map=self.MAP,
                              sample_order=[0x18, 0x0A])
        self.assertEqual(result.samples, [0x18, 0x0A])
        self.assertEqual(self.instruments(result), [(0, 1), (24, 0)])

    def test_sample_order_must_match_used_samples(self):
        with self.assertRaisesRegex(ValueError, 'sample_order'):
            port.convert(two_program_score([(0, 0)]), voices=1, program_map=self.MAP, sample_order=[0x0A, 0x18])

    def test_late_sample_reissues_instrument_until_arrival(self):
        notes = [(i * 24, 0) for i in range(12)]
        plain = port.convert(two_program_score(notes), voices=1, program_map=self.MAP)
        self.assertEqual(len(self.instruments(plain)), 1)
        arrival = port.seconds_to_tick(dict(plain.report['tempo_changes']), 0.5)
        result = port.convert(two_program_score(notes), voices=1, program_map=self.MAP, arrivals={0x0A: 0.5})
        ticks = [t for t, _ in self.instruments(result)]
        before = [t for t, _ in notes if t < arrival]
        first_after = min(t for t, _ in notes if t >= arrival)
        self.assertEqual(ticks, before + [first_after])
        self.assertEqual(result.report['late_notes'], {'0A': len(before)})
        self.assertEqual(result.report['reissued_instruments'], len(before))


if __name__ == '__main__':
    unittest.main()
