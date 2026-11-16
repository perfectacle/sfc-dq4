"""BRR 싸기(dq5brrenc): 싸고 풀어 SNR, 블록 머리(필터·끝·반복 비트), 샘플 자료 머리, 파형·배음, 명령줄."""
import struct
import sys
import tempfile
import unittest
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import dq5brrenc as E  # noqa: E402
from test_dq5spc import run_main, sample, sound_rom  # noqa: E402


class EncodeTest(unittest.TestCase):
    def test_round_trip_snr_and_headers(self):
        pcm = E.wave_pcm('sine', 32, 4)
        brr = E.encode(pcm, 32)
        self.assertEqual(len(brr), 8 * 9)
        heads = brr[::9]
        self.assertEqual(heads[0] >> 2 & 3, 0)
        self.assertEqual(heads[2] >> 2 & 3, 0)  # 반복 시작 블록은 앞 샘플에 기대지 않는다
        self.assertTrue(all(h & 2 for h in heads))
        self.assertEqual([h & 1 for h in heads], [0] * 7 + [1])
        self.assertGreater(E.snr(pcm, E.decode(brr)), 30)

    def test_no_loop_marks_only_the_end_and_pads_to_16(self):
        brr = E.encode([5000] * 20)
        self.assertEqual(len(brr), 18)
        self.assertEqual([h & 3 for h in brr[::9]], [0, 1])
        out = E.decode(brr)
        self.assertEqual(len(out), 32)
        self.assertEqual(out[20:], [0] * 12)

    def test_input_is_clamped_to_15_bits(self):
        self.assertEqual(E.encode([40000] * 16 + [-40000] * 16), E.encode([16383] * 16 + [-16384] * 16))
        out = E.decode(E.encode([40000] * 16 + [-40000] * 16))
        self.assertLessEqual(max(out), 16383)
        self.assertGreaterEqual(min(out), -16384)

    def test_loop_must_be_a_multiple_of_16(self):
        with self.assertRaises(ValueError):
            E.encode([0] * 32, 8)

    def test_decode_stops_at_end_block(self):
        brr = E.encode([1000] * 16) + bytes([0xC0]) + bytes([0x77] * 8)
        self.assertEqual(len(E.decode(brr)), 16)

    def test_predict_filters(self):
        self.assertEqual(E._predict(0, 100, 50), 0)
        self.assertEqual(E._predict(1, 160, 0), 160 + (-160 >> 4))
        self.assertEqual(E._predict(2, 64, 32), 128 + (-192 >> 5) - 32 + 2)
        self.assertEqual(E._predict(3, 64, 32), 128 + (-(64 + 256 + 512) >> 6) - 32 + (96 >> 4))


class ResourceTest(unittest.TestCase):
    def test_resource_layout(self):
        res = E.resource(b'\x01' * 18, 1, adsr1=0x8F, adsr2=0xE0, gain=0x7F, pitch=0x1234)
        self.assertEqual(res[:2], (7 + 18).to_bytes(2, 'little'))
        self.assertEqual(res[2:9], bytes([9, 0, 0x8F, 0xE0, 0x7F, 0x12, 0x34]))
        self.assertEqual(res[9:], b'\x01' * 18)


class WaveTest(unittest.TestCase):
    def test_shapes(self):
        self.assertEqual(E.wave_pcm('square', 4, 1, amp=10), [10, 10, -10, -10])
        self.assertEqual(E.wave_pcm('triangle', 4, 1, amp=10), [-10, 0, 10, 0])
        self.assertEqual(E.wave_pcm('saw', 4, 1, amp=10), [-10, -5, 0, 5])
        self.assertEqual([round(v) for v in E.wave_pcm('sine', 4, 1, amp=10)], [0, 10, 0, -10])

    def test_harmonics_pick_the_nearest_ideal(self):
        for kind in ('square', 'triangle', 'saw', 'sine'):
            f0, h = E.harmonics(E.wave_pcm(kind, 32, 4))
            self.assertEqual(f0, 4)
            dist = {k: sum((h[j] - v[j]) ** 2 for j in range(8)) for k, v in E.IDEAL.items()}
            self.assertEqual(min(dist, key=dist.get), kind)

    def test_snr(self):
        self.assertAlmostEqual(E.snr([10, 10], [10, 9]), 10 * __import__('math').log10(200))
        self.assertEqual(E.snr([0], [0]), 0)


class MainTest(unittest.TestCase):
    def test_wave_to_resource(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'sq.bin'
            code, text = run_main(E, ['--wave', 'square', '--period', '16', '--cycles', '2', '--pitch', '1000', '-o', str(out)])
            self.assertIsNone(code)
            res = out.read_bytes()
            self.assertEqual(res[2:4], b'\x00\x00')
            self.assertEqual(res[7:9], b'\x10\x00')
            self.assertEqual(len(res), 2 + 7 + 18)
            self.assertIn('32 samples -> 18 BRR bytes', text)

    def test_wav_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'in.wav'
            with wave.open(str(src), 'wb') as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(32000)
                w.writeframes(struct.pack('<48h', *[int(v) * 2 for v in E.wave_pcm('saw', 16, 3)]))
            out = Path(tmp) / 'x.bin'
            code, text = run_main(E, ['--wav', str(src), '--loop', '16', '-o', str(out)])
            self.assertIsNone(code)
            res = out.read_bytes()
            self.assertEqual(res[2], 9)  # 반복 시작 블록 1
            self.assertIn('48 samples -> 27 BRR bytes', text)
            stereo = Path(tmp) / 's.wav'
            with wave.open(str(stereo), 'wb') as w:
                w.setnchannels(2)
                w.setsampwidth(2)
                w.setframerate(32000)
                w.writeframes(bytes(8))
            code, _ = run_main(E, ['--wav', str(stereo), '-o', str(out)])
            self.assertEqual(code, '16-bit mono WAV only')

    def test_check_and_nearest_on_rom_samples(self):
        tri = E.encode(E.wave_pcm('triangle', 32, 2), 0)
        smp = [sample(0, tri), sample(1, E.encode([0] * 16))]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'r.sfc'
            path.write_bytes(sound_rom(smp))
            code, text = run_main(E, ['--check', str(path)])
            lines = text.splitlines()
            self.assertEqual(len(lines), 0x26)
            self.assertTrue(lines[0].startswith('00 blocks    4 loop    0 SNR'))
            code, text = run_main(E, ['--nearest', str(path)])
            lines = text.splitlines()
            self.assertIn('nearest triangle', lines[0])
            self.assertIn('2 cycles', lines[0])
            self.assertEqual(lines[1], '01 no loop')


if __name__ == '__main__':
    unittest.main()
