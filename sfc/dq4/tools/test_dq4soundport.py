"""NDS 악보 변환의 템포·세기 합치기와 시퀀스 시각을 검사한다."""
import contextlib
import io
import json
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

    def test_nds_envelope_writes_release_and_audible_overrides(self):
        notes = score([(0, 24, 60, 100), (24, 24, 60, 100), (48, 24, 60, 100)])
        notes['timeline'][1]['adsr'] = [None, 20, 0, None]   # decay·sustain 덮어쓰기: 들리는 차이
        notes['timeline'][2]['adsr'] = [120, None, None, None]  # attack 120: 거의 같은 빠르기
        region = {'lo': 0, 'hi': 127, 'sample': 0x26, 'attack': 127, 'decay': 127, 'sustain': 127, 'release': 110}
        mapping = {0: [region | {'header': [0xFF, 0xE0]}]}
        text = port.convert(notes, voices=1, program_map=mapping).text
        self.assertIn('release 16', text)
        self.assertEqual(text.count('adsr '), 2)  # 덮어쓴 음, 그리고 머리 값으로 되돌리기

    def test_release_only_keeps_the_sample_header(self):
        notes = score([(0, 24, 60, 100), (24, 24, 60, 100)])
        notes['timeline'][1]['adsr'] = [None, 20, 0, None]
        region = {'lo': 0, 'hi': 127, 'sample': 0x26, 'attack': 127, 'decay': 110, 'sustain': 0, 'release': 110}
        mapping = {0: [region | {'header': [0xEF, 0x00], 'release_only': True}]}
        text = port.convert(notes, voices=1, program_map=mapping).text
        self.assertIn('release 16', text)
        self.assertNotIn('adsr ', text)

    def test_large_bend_becomes_fine_tune_and_small_is_dropped(self):
        notes = score([(i * 24, 24, 60 + i % 2, 100) for i in range(6)])
        for e, bend in zip(notes['timeline'], (-16, -16, 3, 3, -16, -16)):
            e['bend'], e['bend_range'] = bend, 2
        text = port.convert(notes, voices=1).text
        self.assertEqual([x.strip() for x in text.split('\n') if 'fine_tune' in x], ['fine_tune E0', 'fine_tune 00', 'fine_tune E0'])

    def test_bend_only_at_a_note_start_is_a_glide_and_is_not_held(self):
        # NDS 는 음 안에서 벤드를 0 으로 되돌린다(끌어올리기). 시작 값을 음 내내 붙들면 반음 가까이 낮게 들린다
        notes = score([(0, 24, 60, 100), (24, 24, 62, 100), (48, 24, 64, 100)])
        notes['timeline'][1]['bend'], notes['timeline'][1]['bend_range'] = -44, 2
        self.assertNotIn('fine_tune', port.convert(notes, voices=1).text)

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


def steady(count=8, **kw):
    return score([(t * 24, 24, 60, 100) for t in range(count)], **kw)


class ArgumentTests(unittest.TestCase):
    def test_voice_count_and_tick_resolution_are_checked(self):
        for voices in (0, 8):
            with self.subTest(voices=voices), self.assertRaisesRegex(ValueError, 'between 1 and 7'):
                port.convert(steady(), voices=voices)
        with self.assertRaisesRegex(ValueError, '48 ticks per quarter'):
            port.convert(steady() | {'ticks_per_quarter': 96})

    def test_loop_bounds(self):
        self.assertEqual(port.score_bounds({'end_tick': 100}), (None, 100))
        self.assertEqual(port.score_bounds({'end_tick': 100, 'loop_start': 20, 'loop_len': 80}), (20, 100))
        for bad in ({'loop_start': -1, 'loop_len': 10}, {'loop_start': 10, 'loop_len': 0},
                    {'loop_start': 10, 'loop_len': 1.5}):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, 'invalid loop bounds'):
                port.score_bounds({'end_tick': 100} | bad)
        with self.assertRaisesRegex(ValueError, 'invalid score end'):
            port.score_bounds({'end_tick': 100, 'loop_start': 50, 'loop_len': 80})
        with self.assertRaisesRegex(ValueError, 'invalid score end'):
            port.score_bounds({'end_tick': 0})

    def test_programs_without_a_mapping_are_named(self):
        notes = steady()
        notes['timeline'][0]['program'] = 99
        with self.assertRaisesRegex(ValueError, r'programs require explicit mapping: \[99\]'):
            port.convert(notes)
        self.assertEqual(port.convert(notes, program_map={99: 0x0A}).samples, [0x0A])

    def test_sample_numbers_must_fit_the_dq5_table(self):
        with self.assertRaisesRegex(ValueError, 'sample ID outside DQ5 table'):
            port.convert(steady(), program_map={0: 0xC8})

    def test_tempo_must_fit_a_driver_byte(self):
        with self.assertRaisesRegex(ValueError, 'tempo outside DQ5 range'):
            port.dq5_tempo(10000)
        with self.assertRaisesRegex(ValueError, 'tempo outside DQ5 range'):
            port.dq5_tempo(0.1)
        self.assertEqual(port.dq5_tempo(120), round(120 * port.NDS_TICKS_PER_SECOND_PER_TEMPO / 0.8))

    def test_a_very_high_start_tempo_needs_a_bounded_startup_change(self):
        with self.assertRaisesRegex(ValueError, 'high initial tempo without a bounded startup change'):
            port.convert(steady() | {'tempo': 1000})
        result = port.convert(steady(tempo_changes=[(2, 120)]) | {'tempo': 1000})
        self.assertGreater(result.report['initial_tempo_delay_seconds'], 0)

    def test_split_tick_must_be_inside_the_song(self):
        for tick in (0, 192):
            with self.subTest(tick=tick), self.assertRaisesRegex(ValueError, 'split_tick must be inside the song'):
                port.convert(steady(), split_tick=tick)

    def test_chain_song_must_be_a_sequence_number(self):
        with self.assertRaisesRegex(ValueError, 'chain_song must be a sequence number'):
            port.convert(steady(), split_tick=96, chain_song=0x64)

    def test_arrivals_must_name_samples_the_song_uses(self):
        with self.assertRaisesRegex(ValueError, 'arrivals name samples the song does not use'):
            port.convert(steady(), arrivals={0x33: 1.0})


class AllocateErrorTests(unittest.TestCase):
    def test_negative_times_and_open_ended_notes_are_refused(self):
        negative = steady()
        negative['timeline'][0]['tick'] = -1
        with self.assertRaisesRegex(ValueError, 'negative note time'):
            port.allocate(negative, 2, 100)
        open_ended = steady()
        open_ended['timeline'][0]['gate'] = 0
        with self.assertRaisesRegex(ValueError, 'zero-gate indefinite notes'):
            port.allocate(open_ended, 2, 100)

    def test_silent_notes_are_counted_and_not_played(self):
        quiet = steady(2)
        quiet['timeline'][0]['velocity'] = 0
        quiet['timeline'][1]['expression'] = 0
        lanes, report = port.allocate(quiet, 2, 100)
        self.assertEqual((report['silent_notes'], report['emitted_notes'], report['source_notes']), (2, 0, 0))
        self.assertEqual(lanes, [[], []])

    def test_lanes_outside_the_voice_range_are_refused(self):
        for lanes in ({'track0': []}, {'track0': [2]}, {'track0': [-1]}):
            with self.subTest(lanes=lanes), self.assertRaisesRegex(ValueError, 'lanes outside the voice range'):
                port.allocate(steady(), 2, 100, lanes_for=lanes)

    def test_notes_beyond_the_end_are_left_out(self):
        _, report = port.allocate(steady(8), 2, 48)
        self.assertEqual(report['source_notes'], 2)

    def test_the_lower_priority_note_is_cut_when_voices_run_out(self):
        # 세 음이 한 틱에 시작, 목소리는 둘: 가장 센 음 둘이 남고 약한 것은 버려진다
        chord = {'ticks_per_quarter': 48, 'tempo': 120, 'tempo_changes': [], 'end_tick': 48, 'timeline': [
            {'op': 'note', 'tick': 0, 'gate': 48, 'note': n, 'velocity': v, 'ch': 'track0', 'program': 0}
            for n, v in ((60, 100), (64, 50), (67, 90))]}
        lanes, report = port.allocate(chord, 2, 48)
        kept = sorted(n['note'] for lane in lanes for n in lane)
        self.assertEqual(kept, [60, 67])
        self.assertEqual(report['dropped_notes'], 1)
        self.assertEqual(report['peak_source_voices'], 3)


class CutAndChainTests(unittest.TestCase):
    def test_a_stronger_note_cuts_the_weaker_one_that_still_sounds(self):
        timeline = [{'op': 'note', 'tick': 0, 'gate': 48, 'note': 60, 'velocity': 50, 'ch': 'track0', 'program': 0},
                    {'op': 'note', 'tick': 24, 'gate': 24, 'note': 64, 'velocity': 100, 'ch': 'track0', 'program': 0}]
        doc = {'ticks_per_quarter': 48, 'tempo': 120, 'tempo_changes': [], 'timeline': timeline, 'end_tick': 48}
        lanes, report = port.allocate(doc, 1, 48)
        self.assertEqual(report['shortened_notes'], [{'source': 0, 'tick': 24, 'lost_ticks': 24}])
        self.assertEqual([(n['note'], n['tick'], n['end']) for n in lanes[0]], [(60, 0, 24), (64, 24, 48)])

    def test_a_note_that_does_not_fit_beside_a_stronger_one_is_dropped(self):
        timeline = [{'op': 'note', 'tick': 0, 'gate': 48, 'note': 64, 'velocity': 100, 'ch': 'track0', 'program': 0},
                    {'op': 'note', 'tick': 24, 'gate': 24, 'note': 60, 'velocity': 40, 'ch': 'track0', 'program': 0}]
        doc = {'ticks_per_quarter': 48, 'tempo': 120, 'tempo_changes': [], 'timeline': timeline, 'end_tick': 48}
        lanes, report = port.allocate(doc, 1, 48)
        self.assertEqual((report['dropped_source_indices'], report['shortened_notes']), ([1], []))
        self.assertEqual(len(lanes[0]), 1)

    def test_a_song_split_in_two_chains_its_intro_into_the_body(self):
        result = port.convert(steady(8), voices=2, split_tick=96, chain_song=0x4C)
        self.assertIsNotNone(result.chain)
        self.assertEqual((result.report['split_tick'], result.report['chain_song']), (96, 0x4C))
        self.assertEqual(result.report['chain_bytes'], len(result.chain))
        self.assertIn('# chain', result.text)
        # 앞부분 끝: 본체로 넘어가는 F7 4C 트랙번호
        self.assertIn('db F7 4C 00', result.text)
        self.assertIn(bytes([0xF7, 0x4C, 0x00]), result.sequence)
        intro = port.execution_trace(result.sequence, 96 * 2, chain=result.chain)
        self.assertEqual(len(intro), 2)


class HelperTests(unittest.TestCase):
    def test_noise_frequency_picks_the_flg_step_nearest_in_pitch(self):
        # 음 60 → 사각파 주기 x 8 = 약 2093 Hz, 가장 가까운 칸은 2000 Hz(16진 16)
        self.assertEqual(port.noise_frequency(60), 0x16)
        # 음 0 은 약 65 Hz → 63 Hz 칸(7), 음 127 은 10만 Hz 쯤이라 가장 높은 칸(31)
        self.assertEqual(port.noise_frequency(0), 7)
        self.assertEqual(port.noise_frequency(127), 31)

    def test_resolve_sample_by_number_region_or_noise(self):
        regions = [{'lo': 0, 'hi': 59, 'sample': 0x20}, {'lo': 60, 'hi': 127, 'sample': 0x21}]
        mapping = {1: 0x0A, 2: regions, 3: port.NOISE}
        self.assertEqual(port.resolve_sample(mapping, 1, 70), 0x0A)
        self.assertEqual(port.resolve_sample(mapping, 2, 59), 0x20)
        self.assertEqual(port.resolve_sample(mapping, 2, 60), 0x21)
        self.assertIsNone(port.resolve_sample(mapping, 3, 70))
        with self.assertRaisesRegex(ValueError, 'program 2 key 200: expected one sample region, got 0'):
            port.resolve_sample(mapping, 2, 200)
        overlapping = {2: regions + [{'lo': 50, 'hi': 70, 'sample': 0x22}]}
        with self.assertRaisesRegex(ValueError, 'got 2'):
            port.resolve_sample(overlapping, 2, 55)

    def test_resolve_region_needs_envelope_headers(self):
        plain = {2: [{'lo': 0, 'hi': 127, 'sample': 0x20}]}
        withheader = {2: [{'lo': 0, 'hi': 59, 'sample': 1, 'header': (1, 2)}, {'lo': 60, 'hi': 127, 'sample': 2, 'header': (3, 4)}],
                      4: 0x0A, 5: port.NOISE}
        self.assertIsNone(port.resolve_region(plain, 2, 10))
        self.assertIsNone(port.resolve_region(withheader, 4, 10))
        self.assertIsNone(port.resolve_region(withheader, 5, 10))
        self.assertEqual(port.resolve_region(withheader, 2, 60)['sample'], 2)

    def test_pan_centres_at_forty_and_levels_scale_with_all_four_volumes(self):
        self.assertEqual([port._pan(v) for v in (64, 65, 127, 0)], [0, 2, 126, 129])
        note = {'velocity': 127}
        self.assertEqual(port._level(note, 127, 127, 127), 255)
        self.assertEqual(port._level(note, 0, 127, 127), 0)
        # 255 * 64 / 127 = 128.5 → 129
        self.assertEqual(port._level({'velocity': 64}, 127, 127, 127), 129)

    def test_near_levels_compare_in_decibels(self):
        self.assertTrue(port._near(100, 100, 1))
        self.assertTrue(port._near(100, 110, 1))
        self.assertFalse(port._near(100, 120, 1))
        self.assertFalse(port._near(0, 100, 1))
        self.assertTrue(port._near(0, 0, 1))


class ControllerTests(unittest.TestCase):
    def doc(self, items):
        return {'end_tick': 10, 'channels': [{'name': 'track0', 'start': '0000', 'track': 0, 'items': items}]}

    def test_scores_without_command_lists_restore_nothing(self):
        self.assertEqual(port.controllers({'channels': [{'name': 'track0'}]}, 10), ({}, False))
        self.assertEqual(port.controllers({}, 10), ({}, False))

    def test_volume_pan_and_expression_changes_are_collected_per_track(self):
        items = [{'addr': '0000', 'op': 'volume', 'args': [100], 'bytes': 'A0 64'},
                 {'addr': '0002', 'op': 'pan', 'args': [32], 'bytes': 'C0 20'},
                 {'addr': '0004', 'op': 'mod-depth', 'args': [5], 'bytes': 'CA 05'},
                 {'addr': '0006', 'op': 'rest', 'len': 4, 'bytes': 'E1 04'},
                 {'addr': '0008', 'op': 'expression', 'args': [90], 'bytes': 'A1 5A'},
                 {'addr': '000A', 'op': 'end', 'bytes': 'FF'}]
        found, restored = port.controllers(self.doc(items), 10)
        self.assertTrue(restored)
        self.assertEqual(found, {'track0': [(0, 7, 100), (0, 10, 32), (4, 11, 90)]})


class PitchAndNoiseTests(unittest.TestCase):
    def one(self, note, **kw):
        timeline = [{'op': 'note', 'tick': 0, 'gate': 24, 'note': note, 'velocity': 100, 'ch': 'track0', 'program': 0}]
        return port.convert({'ticks_per_quarter': 48, 'tempo': 120, 'tempo_changes': [], 'timeline': timeline,
                             'end_tick': 48}, voices=1, **kw)

    def test_high_and_low_notes_fold_into_the_driver_range_by_octaves(self):
        high, low = self.one(110), self.one(12)
        self.assertEqual(high.report['octave_folded_notes'], [{'source': 0, 'from': 110, 'to': 98}])
        self.assertEqual(low.report['octave_folded_notes'], [{'source': 0, 'from': 12, 'to': 24}])
        self.assertIn(f'note {98 - 23:02X}', high.text)
        self.assertIn('note 01', low.text)
        self.assertEqual(self.one(60).report['octave_folded_notes'], [])

    def test_noise_program_switches_the_noise_generator_and_uses_flg_steps(self):
        result = self.one(60, program_map={0: port.NOISE})
        self.assertEqual(result.samples, [])
        self.assertIn('noise_on', result.text)
        self.assertIn('note 16', result.text)

    def test_notes_of_programs_the_bank_does_not_define_are_dropped(self):
        timeline = [{'op': 'note', 'tick': t, 'gate': 20, 'note': 60, 'velocity': 100, 'ch': 'track0', 'program': p}
                    for t, p in ((0, 0), (24, 1))]
        doc = {'ticks_per_quarter': 48, 'tempo': 120, 'tempo_changes': [], 'timeline': timeline, 'end_tick': 48,
               'instruments': {'0': {'type': 'PCM'}, '1': None}}
        result = port.convert(doc, voices=1, program_map={1: 0x0B})
        self.assertEqual(result.report['undefined_program_notes'], 1)
        self.assertEqual(result.samples, [0x0A])


class ExportTests(unittest.TestCase):
    def test_export_writes_each_good_score_and_marks_the_rest_unsupported(self):
        good, bad = steady() | {'id': 'AA', 'title': 'good'}, steady() | {'id': 'BB', 'title': 'bad', 'ticks_per_quarter': 96}
        with tempfile.TemporaryDirectory() as tmp:
            assets, out = Path(tmp) / 'songs', Path(tmp) / 'out' / 'seq'
            assets.mkdir()
            (assets / 'AA.json').write_text(json.dumps(good))
            (assets / 'BB.json').write_text(json.dumps(bad))
            (assets / 'notes.json').write_text(json.dumps([1, 2]))
            (assets / 'other.json').write_text(json.dumps({'id': 'CC'}))
            index = port.export(assets, out)
            self.assertEqual(sorted(p.name for p in out.iterdir()), ['AA.json', 'AA.seq', 'AA.txt', 'index.json'])
            sequence = (out / 'AA.seq').read_bytes()
            self.assertEqual(json.loads((out / 'AA.json').read_text())['sequence_sha256'],
                             json.loads((out / 'index.json').read_text())['items'][0]['sequence_sha256'])
        self.assertEqual((index['scores'], index['converted']), (2, 1))
        self.assertEqual([r['status'] for r in index['items']], ['arrangement-draft', 'unsupported'])
        self.assertIn('48 ticks per quarter', index['items'][1]['reason'])
        self.assertEqual(sequence[0], index['items'][0]['tempo_changes'][0][1])

    def test_score_id_must_be_alphanumeric(self):
        with tempfile.TemporaryDirectory() as tmp:
            assets = Path(tmp)
            (assets / 'x.json').write_text(json.dumps(steady() | {'id': '../x'}))
            with self.assertRaisesRegex(ValueError, 'invalid score ID'):
                port.export(assets, Path(tmp) / 'out')

    def test_main_exports_with_the_chosen_voices_and_program_map(self):
        seen = {}

        def fake_export(assets, out, voices, program_map):
            seen.update(assets=assets, out=out, voices=voices, program_map=program_map)
            return {'scores': 3, 'converted': 2}
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            mapping = Path(tmp) / 'map.json'
            mapping.write_text(json.dumps({'5': 12}))
            argv = ['dq4soundport.py', 'export', '--assets', 'a', '--out', 'o', '--voices', '4', '--program-map', str(mapping)]
            with mock.patch.object(port, 'export', fake_export), mock.patch('sys.argv', argv), contextlib.redirect_stdout(out):
                port.main()
        self.assertEqual(seen, {'assets': Path('a'), 'out': Path('o'), 'voices': 4, 'program_map': {5: 12}})
        self.assertEqual(json.loads(out.getvalue()), {'scores': 3, 'converted': 2, 'unsupported': 1})


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

    def test_yielding_track_gives_up_its_voice(self):
        # 메아리 트랙(track2)이 더 세고 NDS 우선순위가 높아도, 양보하면 화음 음(track1)이 남는다
        timeline = [{'op': 'note', 'tick': 0, 'gate': 10, 'note': n, 'velocity': v, 'ch': ch, 'program': 0, 'priority': p}
                    for n, v, ch, p in ((72, 100, 'track0', 64), (40, 100, 'track3', 64),
                                        (60, 60, 'track1', 64), (67, 120, 'track2', 100))]
        song = {'ticks_per_quarter': 48, 'tempo': 120, 'timeline': timeline, 'end_tick': 10,
                'channels': [{'name': 'track0'}]}
        _, report = port.allocate(song, 3, 10)
        self.assertEqual([timeline[i]['ch'] for i in report['dropped_source_indices']], ['track1'])
        timeline[3]['yield'] = True
        _, report = port.allocate(song, 3, 10)
        self.assertEqual([timeline[i]['ch'] for i in report['dropped_source_indices']], ['track2'])
