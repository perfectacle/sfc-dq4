"""곡 뒤 샘플 전송 계획(순서·곡 앞 샘플 수·도착 어림)을 검사한다."""
import unittest

import dq4soundset as soundset


class TransferPlanTests(unittest.TestCase):
    FIRST = {0x26: 0, 0x27: 0, 0x28: 100, 0x29: 5000}
    NOTES = {0x26: 10, 0x27: 50, 0x28: 5, 0x29: 1}
    SIZES = {0x26: 1000, 0x27: 2000, 0x28: 590, 0x29: 1180}

    def test_orders_by_first_use_then_note_count(self):
        order, _, _ = soundset.transfer_plan(self.FIRST, self.NOTES, self.SIZES, 0)
        self.assertEqual(order, [0x27, 0x26, 0x28, 0x29])

    def test_pre_bytes_cap_is_a_prefix(self):
        _, k, arrivals = soundset.transfer_plan(self.FIRST, self.NOTES, self.SIZES, 3500)
        self.assertEqual(k, 2)
        self.assertEqual(set(arrivals), {0x28, 0x29})
        # 첫 샘플이 커서 상한에 안 들면 뒤의 작은 샘플도 앞으로 보내지 않는다
        _, k, _ = soundset.transfer_plan(self.FIRST, self.NOTES, self.SIZES, 1500)
        self.assertEqual(k, 0)

    def test_arrivals_accumulate_after_song_start(self):
        _, _, arrivals = soundset.transfer_plan(self.FIRST, self.NOTES, self.SIZES, 3000)
        rate, slack, fps = soundset.STREAM_BYTES_PER_FRAME, soundset.ARRIVAL_SLACK_FRAMES, soundset.FRAME_RATE
        self.assertAlmostEqual(arrivals[0x28], (590 / rate + slack) / fps)
        self.assertAlmostEqual(arrivals[0x29], (1770 / rate + slack) / fps)


def detail(source, rate, size):
    return {'source': source, 'base_midi': 60, 'envelope': {'adsr1': 0xFF, 'adsr2': 0xE0}, 'source_loop': [0, 16],
            'effective_rate': rate, 'resource_bytes': size}


class ShareSamplesTests(unittest.TestCase):
    def setUp(self):
        self.resources, self.known = {}, {}
        first = {0x26: b'A' * 100, 0x27: b'B' * 50}
        details = {'26': detail('a.wav', 8000, 100), '27': detail('b.wav', 6000, 50)}
        found, _, _, _ = soundset.share_samples(first, details, {}, self.resources, self.known, 0x26)
        self.resources.update(found)

    def test_identical_bytes_reuse_the_id(self):
        found, mapping, remap, loose = soundset.share_samples(
            {0x26: b'B' * 50}, {'26': detail('b.wav', 6000, 50)}, {5: [{'lo': 0, 'hi': 127, 'sample': 0x26}]},
            self.resources, self.known, 0x28)
        self.assertEqual(remap, {0x26: 0x27})
        self.assertEqual(mapping[5][0]['sample'], 0x27)
        self.assertEqual(loose, [])

    def test_strict_mode_does_not_share_other_rates(self):
        _, _, remap, _ = soundset.share_samples({0x26: b'a' * 75}, {'26': detail('a.wav', 6000, 75)}, {},
                                                self.resources, self.known, 0x28)
        self.assertEqual(remap, {0x26: 0x28})

    def test_loose_mode_takes_a_higher_rate_only_within_budget(self):
        args = ({0x26: b'a' * 75}, {'26': detail('a.wav', 6000, 75)}, {}, self.resources, self.known, 0x28)
        _, _, remap, loose = soundset.share_samples(*args, budget=100, loose=True)
        self.assertEqual(remap, {0x26: 0x26})
        self.assertEqual(loose[0]['used_rate'], 8000)
        _, _, remap, _ = soundset.share_samples(*args, budget=99, loose=True)
        self.assertNotEqual(remap[0x26], 0x26)

    def test_loose_mode_takes_a_lower_rate_one_step_down(self):
        _, _, remap, _ = soundset.share_samples({0x26: b'b' * 70}, {'26': detail('b.wav', 8000, 70)}, {},
                                                self.resources, self.known, 0x28, budget=60, loose=True)
        self.assertEqual(remap, {0x26: 0x27})
        _, _, remap, _ = soundset.share_samples({0x26: b'b' * 90}, {'26': detail('b.wav', 9000, 90)}, {},
                                                self.resources, self.known, 0x28, budget=60, loose=True)
        self.assertEqual(remap, {0x26: 0x28})


class SongScoreTests(unittest.TestCase):
    SCORE = {'timeline': [{'op': 'note', 'ch': 'track0', 'program': 56}, {'op': 'note', 'ch': 'track10', 'program': 64},
                          {'op': 'tempo', 'ch': 'track10'}, {'op': 'note', 'ch': 'track2', 'program': 127}]}

    def test_without_drops_returns_the_same_score(self):
        self.assertIs(soundset.song_score(self.SCORE), self.SCORE)

    def test_drops_notes_of_tracks_and_programs_but_keeps_other_events(self):
        out = soundset.song_score(self.SCORE, drop_tracks={'track10'}, drop_programs={127})
        self.assertEqual(out['timeline'], [self.SCORE['timeline'][0], self.SCORE['timeline'][2]])

    def test_track_db_scales_velocity_of_a_track_or_one_program_in_it(self):
        score = {'timeline': [{'op': 'note', 'ch': 'track6', 'program': 45, 'velocity': 100},
                              {'op': 'note', 'ch': 'track8', 'program': 40, 'velocity': 100},
                              {'op': 'note', 'ch': 'track8', 'program': 45, 'velocity': 100}]}
        out = soundset.song_score(score, track_db={'track6': -6, 'track8@45': -20})
        self.assertEqual([e['velocity'] for e in out['timeline']], [50, 100, 10])


class VoiceVolumeTests(unittest.TestCase):
    def test_zero_db_keeps_the_default(self):
        self.assertEqual(soundset.voice_volume(0), 0x30)

    def test_db_scales_the_volume_and_clamps(self):
        self.assertEqual(soundset.voice_volume(6), round(0x30 * 10 ** 0.3))
        self.assertEqual(soundset.voice_volume(40), 0xFF)
        self.assertEqual(soundset.voice_volume(-80), 1)


class HoldUnitsTests(unittest.TestCase):
    def test_slow_playback_needs_only_the_rounding_unit(self):
        # 8kHz 기준음은 프레임당 약 75바이트라 받기 59 보다 느리지 않으면 앞부분만 있으면 된다
        self.assertEqual(soundset.hold_units(4000, [(0.0, 48)], 8000, 60, bytes_per_frame=200), 1)

    def test_fast_playback_needs_the_bytes_it_would_overtake(self):
        size, rate = 4096, 8000
        speed = rate * 2 * 9 / 16 / soundset.FRAME_RATE  # 한 옥타브 위
        need = size * (1 - 59 / speed)
        self.assertEqual(soundset.hold_units(size, [(0.0, 72)], rate, 60, bytes_per_frame=59), -(-int(need) // 256) + 1)

    def test_later_notes_need_less(self):
        early = soundset.hold_units(4096, [(0.0, 72)], 8000, 60)
        late = soundset.hold_units(4096, [(0.5, 72)], 8000, 60)
        self.assertLess(late, early)


if __name__ == '__main__':
    unittest.main()
