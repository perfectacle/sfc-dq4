import math
from pathlib import Path
import struct
import tempfile
import unittest
import wave

import numpy as np

import dq4soundbank as bank


class BankTests(unittest.TestCase):
    def test_pitch_at_base_note_matches_playback_rate(self):
        for base in (36, 48, 60, 72):
            rate = 12003
            pitch = bank.pitch_word(rate, base)
            actual = bank.PITCH_C * pitch / 256 / 2 ** (9 - (base - 24) / 12)
            self.assertLess(abs(1200 * math.log2(actual / (4096 * rate / 32000))), 1)

    def test_loop_length_and_pitch_rate_keep_loop_duration(self):
        pcm = np.sin(np.arange(1037) * 2 * np.pi / 37) * 10000
        converted, rate, start = bank.prepare_pcm(pcm, 22050, (37, 1037), 12000)
        self.assertEqual(start % 16, 0)
        self.assertEqual(len(converted) % 16, 0)
        self.assertAlmostEqual((len(converted) - start) / rate, 1000 / 22050)

    def test_sample_resource_cache_and_brr_end(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'test.wav'
            pcm = np.rint(np.sin(np.arange(64) * 2 * np.pi / 16) * 12000).astype('<i2')
            with wave.open(str(source), 'wb') as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(12000)
                wav.writeframes(pcm.tobytes())
            region = {'base': 60, 'attack': 127, 'decay': 127, 'sustain': 127}
            result, report = bank.convert_sample(source, region, cache_dir=root / 'cache')
            self.assertEqual(int.from_bytes(result[:2], 'little'), len(result) - 2)
            self.assertEqual(result[-9] & 3, 1)
            self.assertEqual(result[9:18], bytes(9))
            self.assertGreater(report['snr_db'], 15)
            self.assertEqual((result, report), bank.convert_sample(source, region, cache_dir=root / 'cache'))

    def test_full_scale_signal_survives_hardware_decode(self):
        # 넘침 때 부호가 뒤집히는 S-DSP 계산으로 골라야 큰 진폭에서 튀지 않는다.
        t = np.arange(512)
        pcm = np.rint(16300 * np.sin(t * 2 * np.pi / 23) * np.sign(np.sin(t * 2 * np.pi / 97)))
        encoded = bank.encode_hw(pcm.tolist(), 0)
        decoded = np.array(bank.dq5brr.decode(encoded)[0][:len(pcm)]) / 2
        self.assertLess(np.abs(decoded - pcm).max(), 4000)
        self.assertGreater(bank.hw_snr(pcm, encoded), 20)


class EnvelopeTests(unittest.TestCase):
    def test_release_follows_nds_speed(self):
        # 빠른 NDS 릴리스일수록 큰 속도 번호, 127 은 바로 끝남
        rates = [bank.nds_release_rate(x) for x in (100, 110, 120, 127)]
        self.assertEqual(rates, sorted(rates))
        self.assertEqual(rates[-1], 0x1F)

    def test_full_sustain_holds(self):
        self.assertEqual(bank.nds_adsr({'attack': 127, 'decay': 127, 'sustain': 127}), (0xFF, 0xE0))

    def test_low_sustain_keeps_falling(self):
        a1, a2 = bank.nds_adsr({'attack': 127, 'decay': 80, 'sustain': 20})
        self.assertEqual(a2 >> 5, 0)
        self.assertGreater(a2 & 0x1F, 0)

    def test_treble_keeps_dc_and_lifts_nyquist(self):
        flat = np.full(64, 1000.0)
        np.testing.assert_allclose(bank.treble(flat, 6), flat)
        alt = np.array([1000.0, -1000.0] * 32)
        self.assertAlmostEqual(np.abs(bank.treble(alt, 6, loop_start=16)).max() / 1000, 10 ** (6 / 20), places=3)


def write_wave(path, seconds, rate=16000):
    t = np.arange(int(seconds * rate))
    pcm = np.rint(np.sin(t * 2 * np.pi / 37) * 9000).astype('<i2')
    with wave.open(str(path), 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(pcm.tobytes())


class FitTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        samples = root / 'nds/dq4/sound/samples'
        samples.mkdir(parents=True)
        for name in ('a', 'b', 'c', 'd'):
            write_wave(samples / f'{name}.wav', 0.5)
        region = {'type': 'PCM', 'base': 60, 'attack': 127, 'decay': 127, 'sustain': 127}
        self.root = root
        self.score = {
            'instruments': {
                '1': {'regions': [region | {'sample': 'a.wav', 'lo': 0, 'hi': 59},
                                  region | {'sample': 'b.wav', 'lo': 60, 'hi': 127}]},
                '2': {'regions': [region | {'sample': 'c.wav', 'lo': 0, 'hi': 127}]},
                '3': {'regions': [region | {'sample': 'd.wav', 'lo': 0, 'hi': 127}]},
                '4': None,
            },
            'timeline': [{'op': 'note', 'program': p, 'note': n} for p, n, k in
                         ((1, 50, 9), (1, 70, 1), (2, 60, 5), (3, 60, 5), (4, 60, 2)) for _ in range(k)],
        }

    def tearDown(self):
        self.directory.cleanup()

    def test_sample_rate_raises_only_that_sample(self):
        _, _, plain = bank.build_bank(self.score, self.root)
        _, _, raised = bank.build_bank(self.score, self.root, sample_rates={'c.wav': 16000})
        rate = {d['source']: round(d['effective_rate']) for d in raised['samples'].values()}
        self.assertGreater(rate['c.wav'], 8000)
        self.assertEqual({k: v for k, v in rate.items() if k != 'c.wav'},
                         {d['source']: round(d['effective_rate']) for d in plain['samples'].values() if d['source'] != 'c.wav'})

    def test_slot_limit_merges_least_used_region(self):
        _, mapping, report = bank.build_bank(self.score, self.root, max_samples=3)
        self.assertEqual(report['sample_count'], 3)
        self.assertEqual(mapping[1][0]['sample'], mapping[1][1]['sample'])
        self.assertIn('program 1 region 1 -> region 0', report['reductions'][0]['merge'])
        self.assertEqual(report['undefined_program_notes'], 2)

    def test_budget_lowers_rates_until_it_fits(self):
        _, _, full = bank.build_bank(self.score, self.root)
        budget = full['resource_bytes'] * 2 // 3
        _, _, fitted = bank.build_bank(self.score, self.root, budget=budget)
        self.assertLessEqual(fitted['resource_bytes'], budget)
        self.assertTrue(any('rate' in r or 'cut' in r or 'merge' in r for r in fitted['reductions']))

    def test_impossible_budget_is_reported(self):
        with self.assertRaisesRegex(ValueError, 'cannot fit samples'):
            bank.build_bank(self.score, self.root, budget=200)


if __name__ == '__main__':
    unittest.main()


def write_looped_wave(path, pcm, rate, loop):
    """smpl 청크로 정방향 반복을 단 16-bit 모노 WAV."""
    body = np.asarray(pcm, dtype='<i2').tobytes()
    smpl = struct.pack('<9I', 0, 0, 0, 60, 0, 0, 0, 1, 0) + struct.pack('<6I', 0, 0, loop[0], loop[1] - 1, 0, 0)
    fmt = struct.pack('<HHIIHH', 1, 1, rate, rate * 2, 2, 16)
    chunks = b'fmt ' + struct.pack('<I', len(fmt)) + fmt + b'data' + struct.pack('<I', len(body)) + body
    chunks += b'smpl' + struct.pack('<I', len(smpl)) + smpl
    path.write_bytes(b'RIFF' + struct.pack('<I', 4 + len(chunks)) + b'WAVE' + chunks)


class WaveResourceTests(unittest.TestCase):
    def test_one_cycle_keeps_the_base_note_pitch(self):
        rate, base = 44100, 48
        period = rate / (440 * 2 ** ((base - 69) / 12))
        t = np.arange(4000)
        pcm = np.rint(np.sin(2 * np.pi * t / period) * 9000)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'w.wav'
            write_looped_wave(path, pcm, rate, (400, 4000))
            resource, report = bank.wave_resource(path, {'base': base, 'lo': 0, 'hi': 127})
        self.assertEqual(report['samples'], 16 + bank.WAVE_SAMPLES)
        self.assertLess(len(resource), 40)
        # 한 주기 32표본을 기준음 주파수로 울리는 음높이(같은 식으로 만든 긴 샘플의 음높이와 같음)
        self.assertEqual(report['pitch'], bank.pitch_word(bank.WAVE_SAMPLES * rate / period, base))
        self.assertGreater(report['snr_db'], 20)
