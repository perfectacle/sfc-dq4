"""APU 합성(엔벨로프·스윕·길이·선형 카운터·LFSR·프레임 카운터·섞기·WAV)을 합성 레지스터 쓰기로 검사한다."""
import os
import tempfile
import unittest
import wave

import numpy as np

import dq4apu as apu

RATE = 44100


def tone_frames(period, n=60, reg=0x4004, vol=0x3F):
    """펄스 2(또는 reg 가 가리키는 채널)를 첫 프레임에 켠다."""
    return [[(reg, vol), (reg + 1, 0x08), (reg + 2, period & 0xFF), (reg + 3, period >> 8 | 0x08)]] + [[]] * (n - 1)


def peak_hz(x, rate=RATE):
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    return (np.argmax(spec[1:]) + 1) * rate / len(x)


class SequenceTests(unittest.TestCase):
    def test_lfsr_periods(self):
        self.assertEqual(len(apu.NOISE_SEQ[0]), 32767)
        self.assertEqual(len(apu.NOISE_SEQ[1]), 93)
        self.assertEqual(apu.NOISE_SEQ[1][:5].tolist(), [0.0, 1.0, 1.0, 1.0, 1.0])

    def test_envelope_decays_and_loops(self):
        e = apu.Envelope()
        e.write(0x20 | 0x00)      # 되풀이, 분주 0
        e.start = True
        e.clock()
        outs = []
        for _ in range(17):
            outs.append(e.out())
            e.clock()
        self.assertEqual(outs[:16], list(range(15, -1, -1)))
        self.assertEqual(outs[16], 15)
        e.write(0x17)
        self.assertEqual(e.out(), 7)   # 고정 음량


class ChannelTests(unittest.TestCase):
    def test_sweep_negate_differs_between_pulses(self):
        p1, p2 = apu.Pulse(True), apu.Pulse(False)
        for p in (p1, p2):
            p.timer, p.sweep = 0x100, 0x89     # 내림, 시프트 1
        self.assertEqual((p1.target(), p2.target()), (0x7F, 0x80))

    def test_mute_on_low_period_or_overflow(self):
        p = apu.Pulse(False)
        p.timer, p.sweep = 7, 0
        self.assertTrue(p.muted())
        p.timer, p.sweep = 0x700, 0x01
        self.assertTrue(p.muted())          # 올림 목표 7FF 넘음
        p.sweep = 0x09
        self.assertFalse(p.muted())

    def test_length_only_loads_when_enabled(self):
        a = apu.APU(RATE)
        a.write(0x4007, 0x08)
        self.assertEqual(a.p[1].length, 0)
        a.write(0x4015, 0x02)
        a.write(0x4007, 0x08)
        self.assertEqual(a.p[1].length, apu.LENGTHS[1])
        a.write(0x4015, 0x00)
        self.assertEqual(a.p[1].length, 0)

    def test_triangle_linear_counter_reload_and_hold(self):
        t = apu.Triangle()
        t.write(0, 0x83)        # 제어 켬: 다시 싣기가 꺼지지 않는다
        t.write(3, 0x00)
        t.quarter()
        t.quarter()
        self.assertEqual(t.linear, 3)
        t.write(0, 0x03)
        t.quarter()             # 이번까지 싣고 다시 싣기를 끈다
        t.quarter()
        self.assertEqual(t.linear, 2)

    def test_noise_period_and_mode(self):
        n = apu.Noise()
        n.write(2, 0x8A)
        self.assertEqual((n.short, n.period), (True, apu.NOISE_PERIODS[0x0A]))

    def test_frame_counter_mode(self):
        a = apu.APU(RATE)
        a.write(0x4017, 0x00)
        self.assertEqual(a._steps()[1], 29830)
        a.write(0x4017, 0x80)
        self.assertEqual(a._steps()[1], 37282)


class RenderTests(unittest.TestCase):
    def test_pulse_pitch_and_length(self):
        period = round(apu.CPU / (16 * 440) - 1)
        x = apu.render(tone_frames(period, 30, vol=0xBF), RATE)   # 듀티 50%: 기본음이 가장 크다
        self.assertAlmostEqual(len(x), 30 * apu.FRAME * RATE / apu.CPU, delta=2)
        self.assertAlmostEqual(peak_hz(x[2000:]), 440, delta=8)
        self.assertLess(abs(float(np.mean(x[4000:]))), 0.01)   # 고역 필터가 DC 를 없앤다

    def test_triangle_is_an_octave_lower(self):
        period = round(apu.CPU / (16 * 440) - 1)
        frames = [[(0x4008, 0xFF), (0x400A, period & 0xFF), (0x400B, period >> 8 | 0x08)]] + [[]] * 29
        x = apu.render(frames, RATE)
        self.assertAlmostEqual(peak_hz(x[2000:]), 220, delta=6)

    def test_silence_settles_after_power_on_step(self):
        # 삼각파는 멈춰도 그 자리 값(15)을 내므로 켤 때 한 번 튀고, 고역 필터가 곧 0 으로 되돌린다
        x = apu.render([[]] * 10, RATE)
        self.assertGreater(float(np.max(np.abs(x[:100]))), 0.05)
        self.assertLess(float(np.max(np.abs(x[-1000:]))), 1e-3)

    def test_write_wav(self):
        x = np.array([0.0, 0.5, -1.0, 1.0])
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'a.wav')
            apu.write_wav(p, x, RATE)
            with wave.open(p) as w:
                self.assertEqual((w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()), (1, 2, RATE, 4))
                pcm = np.frombuffer(w.readframes(4), '<i2')
        self.assertEqual(pcm.tolist(), [0, 32767, -32767, 32767])   # 2.8배 뒤 ±1 로 자름


if __name__ == '__main__':
    unittest.main()
