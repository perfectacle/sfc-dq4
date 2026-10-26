import math
from pathlib import Path
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


if __name__ == '__main__':
    unittest.main()
