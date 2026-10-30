"""NDS 악보 변환의 템포·세기 합치기와 시퀀스 시각을 검사한다."""
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import dq4soundcompact as compaction
import dq4soundport as port
from dq5song import assemble
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

    def test_voice_volume_sets_every_voice(self):
        notes = [(0, 24, 60, 100)]
        self.assertIn('volume 30', port.convert(score(notes), voices=1).text)
        self.assertIn('volume 60', port.convert(score(notes), voices=1, voice_volume=0x60).text)

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


def body(*voices):
    """목소리마다 본문 줄 목록 → compact 에 넣는 글."""
    lines = ['tempo 40'] + [f'track Lvoice{i}' for i in range(len(voices))]
    for i, lines_ in enumerate(voices):
        lines += [f'Lvoice{i}:', *lines_, '  rest len 30', '  end']
    return lines


def flat(seq, ticks=100000):
    return port.execution_trace(seq, ticks, peek=True)


class CompactTests(unittest.TestCase):
    def check(self, lines):
        plain = assemble(lines)
        packed = assemble(port.compact(lines))
        self.assertEqual(flat(plain), flat(packed))
        return plain, packed

    def test_consecutive_repeats_become_one_loop(self):
        phrase = ['  instrument 01', '  note 30 len 0C', '  note 32', '  note 34', '  tie len 18']
        plain, packed = self.check(body(phrase * 6))
        self.assertIn(0xF5, packed)
        self.assertLess(len(packed) * 5, len(plain) * 3)

    def test_loop_counter_runs_the_body_n_times(self):
        lines = body(['  note 30 len 0C', '  note 31', '  note 32', '  note 33'] * 5)
        packed = assemble(port.compact(lines))
        notes = [e for e in flat(packed)[0] if e[1][0] < 0xA0 and e[1][0] not in (0, 0x50)]
        self.assertEqual(len(notes), 20)

    def test_shared_phrases_across_voices_are_called_within_depth(self):
        a = ['  pan 10', '  note 30 len 0C', '  note 34', '  volume2 80', '  note 37', '  note 3C len 18']
        b = ['  pan F0', '  note 20 len 0C', '  note 24', '  volume2 60', '  note 27', '  note 2C len 18']
        voice0 = a + b + ['  rest len 06'] + a + ['  rest len 03'] + b + a
        voice1 = b + ['  rest len 05'] + a + ['  rest len 07'] + b
        plain, packed = self.check(body(voice0, voice1))
        self.assertIn(0xF8, packed)
        self.assertLess(len(packed), len(plain))
        lines = port.compact(body(voice0, voice1))
        self.assertTrue(all(_depth(lines, label) <= port.MAX_CALL_DEPTH
                            for label in {ln[:-1] for ln in lines if ln.startswith('Lphrase')}))

    def test_cache_returns_the_same_lines_and_follows_the_tool_hash(self):
        lines = body(['  instrument 01', '  note 30 len 0C', '  note 32', '  note 34', '  tie len 18'] * 6)
        with tempfile.TemporaryDirectory() as root:
            first = compaction.compact(lines, root)
            self.assertEqual(first, compaction.compact(lines))
            files = list(Path(root).rglob('*.json.gz'))
            self.assertEqual(len(files), 1)
            with mock.patch.object(compaction, '_compact', side_effect=AssertionError('cache miss')):
                self.assertEqual(first, compaction.compact(lines, root))
            with mock.patch.object(compaction, 'COMPACT_HASH', 'other tool source'):
                self.assertEqual(first, compaction.compact(lines, root))
            self.assertEqual(len(list(Path(root).rglob('*.json.gz'))), 2)

    def test_rest_after_note_is_not_split_by_call(self):
        # 음 뒤가 쉼이면 15E5 가 KOF 를 걸지 않는다. 그 사이에 F8·F9 가 끼면 KOF 가 생기므로 묶지 않아야 한다.
        phrase = ['  note 30 len 0C', '  rest len 0C']
        voice = []
        for i in range(8):
            voice += [f'  note {0x40 + i:02X} len 06'] + phrase + [f'  pan {i * 8:02X}']
        self.check(body(voice))

    def test_peek_flag_sees_skipped_commands(self):
        seq = assemble(body(['  note 30 len 0C', '  volume2 40', '  gate_preset FE', '  rest len 0C',
                             '  note 31 len 0C', '  instrument 02', '  rest len 0C']))
        notes = [(raw[0], rest) for _, raw, *rest in flat(seq)[0] if raw[0] < 0xA0]
        self.assertEqual(notes[:3], [(0x80, [True]), (0x50, [False]), (0x81, [False])])


def _depth(lines, label, seen=()):
    start = lines.index(label + ':')
    calls = []
    for line in lines[start + 1:]:
        if line == '  ret':
            break
        if line.split()[0] == 'call':
            calls.append(line.split()[-1])
    return 1 + max((_depth(lines, c) for c in calls), default=0)


class HoldTests(unittest.TestCase):
    MAP = {0: 0x0A, 1: 0x18}

    def test_hold_heads_track_zero_and_rests_every_track_one_tick(self):
        plain = port.convert(two_program_score([(0, 0), (24, 1)]), voices=2, program_map=self.MAP)
        held = port.convert(two_program_score([(0, 0), (24, 1)]), voices=2, program_map=self.MAP, hold=(0x18, 3))
        first = port.header(held.sequence)[1][0]
        self.assertEqual(held.sequence[first:first + 6], bytes.fromhex('F7 FE 18 F7 FF 03'))
        self.assertEqual(held.report['hold'], {'sample': '18', 'bytes': 768})
        # 붙들기 명령은 시각에 영향이 없고, 모든 음이 1틱 늦는다
        def keyed(seq):
            # 음표(00~9F) 가운데 쉼(00·4F, 50 위쪽도 같음)은 뺀다
            return [[t for t, raw in track if raw[0] < 0xA0 and raw[0] % 0x50 not in (0, 0x4F)]
                    for track in port.execution_trace(seq, 400)]

        before, after = keyed(plain.sequence), keyed(held.sequence)
        self.assertEqual([[t + 1 for t in ts] for ts in before], [ts[:len(b)] for ts, b in zip(after, before)])


if __name__ == '__main__':
    unittest.main()


class LaneTests(unittest.TestCase):
    def test_fixed_lane_keeps_track_on_its_voice(self):
        timeline = [{'op': 'note', 'tick': t, 'gate': 10, 'note': n, 'velocity': 100, 'ch': ch, 'program': 0}
                    for t, n, ch in ((0, 60, 'track0'), (0, 48, 'track1'), (20, 62, 'track0'), (20, 50, 'track1'))]
        song = {'ticks_per_quarter': 48, 'tempo': 120, 'timeline': timeline, 'end_tick': 40,
                'channels': [{'name': 'track0'}]}
        lanes, report = port.allocate(song, 3, 40, lanes_for={'track0': [2], 'track1': [0]})
        self.assertEqual([n['ch'] for n in lanes[2]], ['track0', 'track0'])
        self.assertEqual([n['ch'] for n in lanes[0]], ['track1', 'track1'])
        self.assertEqual(lanes[1], [])
        self.assertEqual(report['dropped_notes'], 0)

    def test_busy_fixed_lane_drops_weaker_note(self):
        timeline = [{'op': 'note', 'tick': 0, 'gate': 10, 'note': n, 'velocity': v, 'ch': 'track1', 'program': 0}
                    for n, v in ((60, 100), (64, 50))]
        song = {'ticks_per_quarter': 48, 'tempo': 120, 'timeline': timeline, 'end_tick': 10,
                'channels': [{'name': 'track0'}]}
        lanes, report = port.allocate(song, 3, 10, lanes_for={'track1': [1]})
        self.assertEqual([n['note'] for n in lanes[1]], [60])
        self.assertEqual(report['dropped_notes'], 1)
