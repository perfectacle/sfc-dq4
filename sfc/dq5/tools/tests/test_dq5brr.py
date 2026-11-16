"""BRR 풀기(dq5brr): S-DSP 정수 계산, 끝·반복 비트, WAV(smpl 반복 구간), 샘플 표와 WAV 내보내기."""
import io
import json
import struct
import sys
import tempfile
import unittest
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import dq5brr as B  # noqa: E402
import dq5brrenc as E  # noqa: E402
from dq5map import Rom  # noqa: E402
from test_dq5spc import run_main, sample, sound_rom  # noqa: E402


class DecodeTest(unittest.TestCase):
    def test_matches_encoder_model_times_two(self):
        # 인코더는 15비트로, 이 디코더는 DSP 처럼 1비트 왼쪽으로 민 16비트로 낸다. 필터 1~3 이 모두 섞이는 파형으로 견준다.
        filters = set()
        for kind in ('sine', 'saw', 'square', 'triangle'):
            brr = E.encode(E.wave_pcm(kind, 32, 4), 0)
            pcm, looped = B.decode(brr)
            self.assertTrue(looped)
            self.assertEqual(pcm, [x * 2 for x in E.decode(brr)])
            filters |= {brr[i] >> 2 & 3 for i in range(0, len(brr), 9)}
        self.assertEqual(filters, {0, 1, 2, 3})

    def test_end_without_loop_stops_reading(self):
        block = bytes([0x01 | 0xC0, 0x7F]) + bytes(7)
        pcm, looped = B.decode(block + bytes([0xC0, 0x11]) + bytes(7))
        self.assertFalse(looped)
        self.assertEqual(len(pcm), 16)
        self.assertEqual(pcm[:2], [7 << 12 >> 1 << 1, -1 << 12 >> 1 << 1])

    def test_large_shift_clamps_like_dsp(self):
        pcm, _ = B.decode(bytes([0xD1, 0x87]) + bytes(7))
        self.assertEqual(pcm[:2], [-4096, 0])


class WavTest(unittest.TestCase):
    def test_plain_wav_header_and_data(self):
        raw = B.wav([0, 1, -1, 32767])
        with wave.open(io.BytesIO(raw)) as w:
            self.assertEqual((w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()), (1, 2, B.RATE, 4))
            self.assertEqual(struct.unpack('<4h', w.readframes(4)), (0, 1, -1, 32767))
        self.assertNotIn(b'smpl', raw)
        self.assertEqual(struct.unpack('<I', raw[4:8])[0], len(raw) - 8)

    def test_loop_goes_into_smpl_chunk(self):
        raw = B.wav(list(range(32)), loop_start=16, rate=16000)
        k = raw.index(b'smpl')
        size = struct.unpack('<I', raw[k + 4:k + 8])[0]
        fields = struct.unpack('<15I', raw[k + 8:k + 8 + size])
        self.assertEqual(fields[2], 1000000000 // 16000)
        self.assertEqual(fields[7], 1)
        self.assertEqual(fields[11:13], (16, 31))


class TableTest(unittest.TestCase):
    def test_table_and_export(self):
        looped = E.encode(E.wave_pcm('square', 16, 2), 16)
        once = E.encode([1000] * 16)
        smp = [sample(1, looped, adsr=(0x8F, 0xE1), gain=0x7F, pitch=0x1234), sample(0, once)]
        rom = Rom(sound_rom(smp))
        t = B.table(rom)
        self.assertEqual(len(t), 0x26)
        self.assertEqual(t[0][2:], (9, 0x8F, 0xE1, 0x7F, 0x1234, looped))
        self.assertEqual(t[1][-1], once)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'r.sfc'
            path.write_bytes(rom.d)
            out_dir = Path(tmp) / 'out'
            code, out = run_main(B, [str(path), '--out', str(out_dir)])
            self.assertEqual(code, 0)
            lines = out.splitlines()
            self.assertEqual(len(lines), 0x26)
            self.assertIn('BRR    18 바이트     32 표본 반복     16', lines[0])
            self.assertIn('반복     없음', lines[1])
            index = json.loads((out_dir / 'index.json').read_text(encoding='utf-8'))
            self.assertEqual(index[0]['loop_start'], 16)
            self.assertEqual(index[0]['pitch'], '1234')
            self.assertIsNone(index[1]['loop_start'])
            with wave.open(str(out_dir / '00.wav')) as w:
                self.assertEqual(w.getnframes(), 32)
            self.assertIn(b'smpl', (out_dir / '00.wav').read_bytes())
            self.assertNotIn(b'smpl', (out_dir / '01.wav').read_bytes())


if __name__ == '__main__':
    unittest.main()
