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


if __name__ == '__main__':
    unittest.main()
