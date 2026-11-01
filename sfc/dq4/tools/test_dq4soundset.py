"""곡 뒤 샘플 전송 계획(순서·곡 앞 샘플 수·도착 어림)과 합성 롬·합성 NDS 곡으로 돈 build 를 검사한다."""
import contextlib
from functools import cache
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import wave

import numpy as np

import dq4soundpatch as patch
import dq4soundset as soundset
from dq5map import lorom
from test_dq4soundpatch import melody, synthetic_base


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

    def test_drops_one_program_of_a_track(self):
        out = soundset.song_score(self.SCORE, drop_tracks={'track10@64', 'track0@40'})
        self.assertEqual(out['timeline'], [self.SCORE['timeline'][i] for i in (0, 2, 3)])

    def test_yield_marks_only_that_track(self):
        out = soundset.song_score(self.SCORE, yield_tracks={'track10'})
        self.assertEqual([e.get('yield', False) for e in out['timeline']], [False, True, False, False])

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


def write_wave(path, seconds, period):
    t = np.arange(int(seconds * 16000))
    pcm = np.rint(np.sin(t * 2 * np.pi / period) * 9000).astype('<i2')
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(pcm.tobytes())


def write_song(root, ident, hits):
    """hits = [(틱, 프로그램)]. 프로그램 1·2·3 은 a·b·c.wav 를 음역 전체로 쓴다."""
    region = {'type': 'PCM', 'base': 60, 'attack': 127, 'decay': 127, 'sustain': 127, 'release': 100, 'lo': 0, 'hi': 127}
    timeline = [{'op': 'note', 'tick': t, 'gate': 20, 'note': 60, 'velocity': 100, 'ch': f'track{p}', 'program': p,
                 'uid': i} for i, (t, p) in enumerate(hits)]
    score = {'ticks_per_quarter': 48, 'tempo': 120, 'tempo_changes': [], 'timeline': timeline,
             'end_tick': max(t for t, _ in hits) + 48,
             'instruments': {str(p): {'type': 'PCM', 'regions': [region | {'sample': f'{name}.wav'}]}
                             for p, name in ((1, 'a'), (2, 'b'), (3, 'c'))}}
    (root / f'nds/dq4/sound/songs/{ident}-test.json').write_text(json.dumps(score))


@cache
def chain_base():
    """synthetic_base 에 나눈 곡·붙들기 코드 자리의 원래 바이트(install 이 put 에 넘기는 기대값)를 더 심은 롬."""
    data, expected = bytearray(synthetic_base()), {}

    def record(data, addr, payload, expected_bytes=None, empty=False):
        if expected_bytes is not None:
            expected.setdefault(addr, bytes(expected_bytes))
        data[lorom(addr):lorom(addr) + len(payload)] = payload

    with mock.patch.object(patch, 'put', record):
        patch.install(bytes(data), {0x06: patch.Replacement(melody(), (0x03,))}, chains={0x06: melody()},
                      fast_receive=True, hold=True)
    for addr, raw in expected.items():
        data[lorom(addr):lorom(addr) + len(raw)] = raw
    return bytes(data)


class BuildTests(unittest.TestCase):
    """a.wav(1.5초, 큰 샘플)는 곡 첫머리, b·c 는 뒤에 쓴다. 곡 05 는 b·c 만 써서 06 과 같은 자원을 나눠 쓴다."""

    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.root = root = Path(cls.directory.name)
        (root / 'nds/dq4/sound/samples').mkdir(parents=True)
        (root / 'nds/dq4/sound/songs').mkdir(parents=True)
        for name, seconds, period in (('a', 1.5, 37), ('b', 0.3, 29), ('c', 0.5, 23)):
            write_wave(root / f'nds/dq4/sound/samples/{name}.wav', seconds, period)
        write_song(root, '0E', [(0, 1), (48, 1), (96, 2), (400, 3), (480, 3), (900, 1)])
        write_song(root, '05', [(0, 2), (96, 3)])

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def build(self, songs=((0x06, '0E'), (0x02, '05')), base=None, **options):
        with contextlib.redirect_stderr(io.StringIO()):
            return soundset.build(base or synthetic_base(), self.root, list(songs), cache_dir=self.root / 'cache',
                                  **options)

    @staticmethod
    def record(rom, song):
        size, first, *ids = patch.read_sets(rom)[song]
        return first, ids

    def test_sequences_and_samples_land_where_the_records_point(self):
        rom, report = self.build()
        for song in (0x06, 0x02):
            entry = report['songs'][f'{song:02X}']
            self.assertEqual(hashlib.sha256(patch.sequence_bytes(rom, song)).hexdigest(),
                             entry['conversion']['sequence_sha256'])
            _, ids = self.record(rom, song)
            self.assertEqual(len(ids), len(set(ids)))
            self.assertLessEqual(entry['bank']['resource_bytes'], entry['sample_budget'])
        a_ids, b_ids = self.record(rom, 0x06)[1], self.record(rom, 0x02)[1]
        # 바이트까지 같은 b·c 는 곡 06 이 매긴 번호를 그대로 쓴다(번호를 새로 쓰면 26~C7 이 모자란다)
        self.assertEqual(set(b_ids), set(a_ids[1:]))
        self.assertEqual(report['songs']['02']['bank']['shared_samples'], [f'{x:02X}' for x in sorted(b_ids)])
        sizes = {int(k, 16): v['resource_bytes'] for k, v in report['songs']['06']['bank']['samples'].items()}
        for x in a_ids:
            self.assertEqual(patch.sample_size(rom, x) + 2, sizes[x])
        self.assertFalse([k for k, v in report['install']['unreplaced_songs'].items() if 'error' in v])

    def test_stream_cap_sends_first_used_samples_first(self):
        _, plain = self.build()
        size_a = plain['songs']['06']['bank']['samples']['26']['resource_bytes']
        rom, report = self.build(stream={0x06: size_a})
        plan = report['songs']['06']['stream']
        first, ids = self.record(rom, 0x06)
        self.assertEqual((first, plan['send_first']), (1, 1))
        self.assertEqual(ids[0], 0x26)
        self.assertLessEqual(plan['pre_sample_bytes'], plan['pre_bytes_cap'])
        arrivals = [plan['arrival_seconds'][f'{x:02X}'] for x in ids[first:]]
        self.assertEqual(arrivals, sorted(arrivals))
        # 한 바이트라도 모자라면 곡 앞으로 보내지 않는다
        rom, _ = self.build(stream={0x06: size_a - 1})
        self.assertEqual(self.record(rom, 0x06)[0], 0)

    def test_stream_ticks_pull_samples_forward_until_no_note_is_late(self):
        rom, report = self.build(stream_ticks={0x06: 0})
        conversion = report['songs']['06']['conversion']
        self.assertFalse(any(conversion['late_notes'].values()))
        self.assertGreaterEqual(self.record(rom, 0x06)[0], 1)

    def test_hold_moves_the_held_sample_just_after_the_front_samples(self):
        rom, report = self.build(base=chain_base(), stream_ticks={0x06: 10}, holds=(0x06,), fast_receive=True)
        plan = report['songs']['06']['stream']
        held = int(plan['hold']['sample'], 16)
        first, ids = self.record(rom, 0x06)
        self.assertEqual(first, plan['send_first'])
        self.assertEqual(ids[first], held)
        size = report['songs']['06']['bank']['samples'][f'{held:02X}']['resource_bytes']
        self.assertEqual(plan['hold']['bytes'] % 256, 0)
        self.assertEqual(plan['hold']['saved_bytes'], size - plan['hold']['bytes'])
        self.assertGreater(plan['hold']['saved_bytes'], 0)
        self.assertEqual(report['songs']['06']['conversion']['hold'], {'sample': f'{held:02X}', 'bytes': plan['hold']['bytes']})
        self.assertFalse(any(report['songs']['06']['conversion']['late_notes'].values()))
        # 곡 뒤 샘플은 붙든 샘플의 문턱을 넘긴 나머지(SPC 가 255바이트까지 덜 셀 수 있음) 뒤에 이어 온다
        sizes = {int(k, 16): v['resource_bytes'] for k, v in report['songs']['06']['bank']['samples'].items()}
        sent = size - plan['hold']['bytes'] + 256
        for x in ids[first + 1:]:
            sent += sizes[x]
            want = (sent / soundset.STREAM_BYTES_PER_FRAME + soundset.ARRIVAL_SLACK_FRAMES) / soundset.FRAME_RATE
            self.assertAlmostEqual(plan['arrival_seconds'][f'{x:02X}'], want, places=2)

    def test_hold_needs_fast_receive(self):
        with self.assertRaisesRegex(ValueError, 'fast_receive'):
            self.build(base=chain_base(), stream_ticks={0x06: 10}, holds=(0x06,))

    def test_chained_song_body_gets_the_first_chain_number(self):
        rom, report = self.build(base=chain_base(), stream_ticks={0x06: 10}, chains=(0x06,), fast_receive=True)
        self.assertEqual(report['install']['chains'], {'06': f'{patch.FIRST_CHAIN_SONG:02X}'})
        conversion = report['songs']['06']['conversion']
        self.assertEqual(conversion['chain_song'], patch.FIRST_CHAIN_SONG)
        self.assertTrue(0 < conversion['split_tick'] < conversion['end_tick'])
        self.assertGreater(len(patch.sequence_bytes(rom, patch.FIRST_CHAIN_SONG)), 0)

    def test_chained_hold_sends_the_body_after_the_samples_when_that_is_sooner(self):
        _, report = self.build(base=chain_base(), stream_ticks={0x06: 10}, chains=(0x06,), holds=(0x06,),
                               fast_receive=True)
        plan = report['songs']['06']['stream']
        self.assertIsNotNone(plan['hold'])
        self.assertTrue(plan['chain_after_samples'])
        self.assertEqual(report['install']['chains_sent_after_samples'], ['06'])

    def test_resident_from_appends_the_front_samples_to_the_resident_list(self):
        before = patch.resident_samples(synthetic_base())
        rom, report = self.build(songs=((0x17, '0E'), (0x02, '05')), stream={0x17: 7000}, budgets={0x17: 20000},
                                 resident_from=0x17, pinned=(0x17,))
        first, ids = self.record(rom, 0x17)
        self.assertEqual(first, 1)
        self.assertEqual(patch.resident_samples(rom), before + ids[:first])
        # 늘 두는 샘플은 곡 앞 전송을 건너뛰므로, 함께 쓰는 곡 02 의 레코드에도 같은 번호가 그대로 든다
        self.assertTrue(set(self.record(rom, 0x02)[1]) <= set(ids))

    def test_prefetch_appends_unused_front_samples_of_the_map_song(self):
        rom, report = self.build(songs=((0x06, '0E'), (0x07, '05')), stream={0x06: 7000}, prefetch={0x07: 0x06},
                                 keep_samples=True, load_pump=True, early_song=True, fast_receive=True)
        front = self.record(rom, 0x06)[1][:self.record(rom, 0x06)[0]]
        first, ids = self.record(rom, 0x07)
        own = [int(x, 16) for x in report['songs']['07']['bank']['samples']]
        extra = report['songs']['07']['prefetch']
        self.assertEqual(extra['map_song'], '06')
        # 덧붙인 샘플은 레코드 끝이라 곡 07 의 악기 번호(앞 샘플 순서)는 그대로다
        self.assertEqual(ids[:len(own)], own)
        self.assertEqual(ids[len(own):], [int(x, 16) for x in extra['samples']])
        self.assertTrue(set(ids[len(own):]) <= set(front) - set(own))
        self.assertTrue(extra['samples'])

    def test_rejects_inconsistent_options(self):
        cases = [({'songs': ((0x06, '0E'), (0x06, '05'))}, 'replaced once'),
                 ({'resident_from': 0x06}, 'resident_from song must be streamed'),
                 ({'chains': (0x06,)}, 'chained songs must use stream_ticks'),
                 ({'prefetch': {0x02: 0x06}}, 'prefetch needs keep_samples'),
                 ({'programs': {0x06: {1: 0x30}}}, 'program overrides must name samples of earlier songs'),
                 ({'silent_songs': (0x06,)}, 'silent song needs an unused new song number')]
        for options, message in cases:
            with self.subTest(message), self.assertRaisesRegex(ValueError, message):
                self.build(**options)


if __name__ == '__main__':
    unittest.main()
