"""SPC 실측 비교에서 곡 시작·샘플 도착 기록을 읽고 도착 전 음을 빼는지 검사한다."""
import contextlib
import io
import json
import math
import tempfile
from pathlib import Path
import unittest
import unittest.mock

import dq4soundcheck as check
import dq4soundpatch as patch
from dq4soundport import DQ5_TICKS_PER_SECOND_PER_TEMPO as TPS
from dq5map import lorom
from dq5song import RELOC_SEQ_TABLE, RELOC_SMP_TABLE
from dq5spc import (SPC_DIR, SPC_SAMPLE_INDEX, SPC_SAMPLE_SLOTS, SPC_SEQUENCE_INDEX,
                    SPC_SEQUENCE_SLOTS)


class EventTests(unittest.TestCase):
    def read(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'events.txt'
            path.write_text(text)
            return check.read_events(path)

    def test_started_frame_and_last_arrival(self):
        start, arrivals = self.read('song 17 started at frame 209\nsample 3F slot 0A at frame 254\n'
                                    'sample 40 slot 0B at frame 260\nsample 40 slot FF at frame 300\n'
                                    'song 17 on at frame 449\n')
        self.assertEqual(start, 209)
        self.assertEqual(arrivals, {0x3F: 254})

    def test_old_runs_use_song_on_frame(self):
        self.assertEqual(self.read('song 02 on at frame 246\n'), (246, {}))

    def test_blocked_only_before_arrival(self):
        arrivals = {0x3F: 254}
        self.assertTrue(check.blocked(0.5, 0x3F, 209, arrivals))
        self.assertFalse(check.blocked(1.0, 0x3F, 209, arrivals))
        self.assertFalse(check.blocked(0.0, 0x39, 209, arrivals))

    def test_note_right_after_arrival_counts_as_blocked(self):
        # 칸이 생긴 다음 프레임의 음은 아직 울리지 않았다
        arrivals = {0x77: 235}
        self.assertTrue(check.blocked((236 - 217) / check.NTSC_FPS, 0x77, 216, arrivals))
        self.assertFalse(check.blocked((240 - 217) / check.NTSC_FPS, 0x77, 216, arrivals))


TEMPO = 10
# 트랙 하나: 악기 00, 음 30 (길이 48틱), 음 30, 음 3C. F0 은 인자 한 바이트.
def song(third=0x3C):
    body = bytes([0xF0, 0x00, 0x50 + 0x30, 0x30, 0x50 + 0x30, 0x30, 0x50 + third, 0x30, 0xFF])
    return bytes([TEMPO, 1, 4, 0]) + body


def seconds(ticks):
    return ticks / (TEMPO * TPS)


class ExpectedNotesTests(unittest.TestCase):
    def test_notes_carry_time_pitch_and_instrument(self):
        (voice,) = check.expected_notes(song(), 1000)
        self.assertEqual([(n, i) for _, n, i in voice], [(0x30, 0), (0x30, 0), (0x3C, 0)])
        self.assertEqual([t for t, _, _ in voice], [seconds(0), seconds(48), seconds(96)])

    def test_rests_and_ties_are_not_notes(self):
        seq = bytes([TEMPO, 1, 4, 0, 0xF0, 0x01, 0x50, 0x10, 0x50 + 0x4F, 0x10, 0x50 + 0x20, 0x10, 0xFF])
        (voice,) = check.expected_notes(seq, 1000)
        self.assertEqual([n for _, n, _ in voice], [0x20])
        self.assertEqual(voice[0][0], seconds(32))

    def test_tempo_change_on_track_zero_speeds_later_notes(self):
        # 첫 음 48틱 뒤 EB 20 → 템포 0x20
        seq = bytes([TEMPO, 1, 4, 0, 0xF0, 0x01, 0x80, 0x30, 0xEB, 0x20, 0x80, 0x30, 0x80, 0x30, 0xFF])
        (voice,) = check.expected_notes(seq, 1000)
        self.assertEqual(voice[0][0], 0)
        self.assertAlmostEqual(voice[1][0], seconds(48))
        self.assertAlmostEqual(voice[2][0], seconds(48) + 48 / (0x20 * TPS))


class ReadSrcnTests(unittest.TestCase):
    def test_srcn_is_taken_at_each_kon(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'dspw.txt'
            path.write_text('10 04=03\n11 14=07\n12 4C=03\n13 04=09\n14 4C=01\n15 90=00\n')
            hits = check.read_srcn(path)
        self.assertEqual(hits[0], [(12, 3), (14, 9)])
        self.assertEqual(hits[1], [(12, 7)])
        self.assertEqual(hits[2], [])


class TimingTests(unittest.TestCase):
    START = 100

    def run_dir(self, tmp, frames, pitches, srcn=0x0A):
        lines = []
        for frame, pitch in zip(frames, pitches):
            lines += [f'{frame - 1} 04={srcn:02X}', f'{frame - 1} 02={pitch & 0xFF:02X}', f'{frame - 1} 03={pitch >> 8:02X}',
                      f'{frame} 4C=01']
        lines.append('3000 7F=00')
        (Path(tmp) / 'dspw.txt').write_text('\n'.join(lines) + '\n')
        return Path(tmp)

    def frames(self, error=0):
        fps = check.NTSC_FPS
        return [self.START + 1, self.START + 1 + round(seconds(48) * fps), self.START + 1 + round(seconds(96) * fps) + error]

    def timing(self, error=0, third=0x3C, pitches=(0x1000, 0x1000, 0x2000), slot=0x0A):
        record = {0: 0x03}
        with tempfile.TemporaryDirectory() as tmp:
            run = self.run_dir(tmp, self.frames(error), pitches)
            return check.timing(song(third), run, self.START, {0x03: slot}, record)

    def test_matching_playback_has_no_mismatch(self):
        (voice,) = self.timing()['voices']
        self.assertEqual((voice['expected_notes'], voice['kon'], voice['compared']), (3, 3, 3))
        self.assertEqual((voice['wrong_srcn'], voice['intervals'], voice['interval_mismatches']), (0, 2, 0))
        self.assertLessEqual(voice['max_frame_error'], 1)

    def test_speed_ratio_follows_frame_spacing(self):
        result = self.timing()
        self.assertAlmostEqual(result['speed_ratio'], 1.0, places=2)
        self.assertEqual(result['start_frame'], self.START)
        self.assertEqual(result['last_frame'], 3000)

    def test_late_note_shows_as_frame_error(self):
        (voice,) = self.timing(error=12)['voices']
        self.assertGreater(voice['max_frame_error'], 2)

    def test_wrong_sample_slot_is_counted(self):
        (voice,) = self.timing(slot=0x0B)['voices']
        self.assertEqual(voice['wrong_srcn'], 3)

    def test_wrong_pitch_interval_is_counted(self):
        # 둘째 음 30 → 셋째 음 3C 은 한 옥타브 위여야 하는데 피치가 그대로
        (voice,) = self.timing(pitches=(0x1000, 0x1000, 0x1000))['voices']
        self.assertEqual(voice['interval_mismatches'], 1)

    def test_blocked_note_is_left_out_of_the_comparison(self):
        # 첫 음은 샘플이 도착하기 전이라 예상에서 빠지고, KON 두 개가 나머지 두 음과 짝지어진다
        fps = check.NTSC_FPS
        arrivals = {0x03: self.START + 1 + round(seconds(24) * fps)}
        frames = self.frames()[1:]
        with tempfile.TemporaryDirectory() as tmp:
            run = self.run_dir(tmp, frames, [0x1000, 0x2000])
            result = check.timing(song(), run, self.START, {0x03: 0x0A}, {0: 0x03}, arrivals)
        (voice,) = result['voices']
        self.assertEqual((voice['blocked_notes'], voice['expected_notes'], voice['compared']), (1, 2, 2))
        self.assertEqual(voice['interval_mismatches'], 0)

    def test_too_few_pairs_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self.run_dir(tmp, [self.START + 1], [0x1000])
            with self.assertRaises(SystemExit):
                check.timing(song(), run, self.START, {0x03: 0x0A}, {0: 0x03})

    def test_held_song_starts_from_the_first_heard_note(self):
        seq = bytearray(song())
        seq[4:4] = bytes([0xF7, 0xFE, 0x03])
        seq[2:4] = bytes([4, 0])
        with tempfile.TemporaryDirectory() as tmp:
            run = self.run_dir(tmp, [160, 160 + round(seconds(48) * check.NTSC_FPS),
                                     160 + round(seconds(96) * check.NTSC_FPS)], [0x1000, 0x1000, 0x2000])
            result = check.timing(bytes(seq), run, self.START, {0x03: 0x0A}, {0: 0x03}, {0x03: 5000})
        self.assertGreater(result['start_frame'], self.START)
        (voice,) = result['voices']
        self.assertEqual(voice['compared'], 3)
        self.assertEqual(voice['blocked_notes'], 0)


def rom_with_song(seq, sample_body_bytes, sets):
    data = bytearray(0x400000)
    # 재배치 표: 곡 번호 x 3 = 포인터, 가리키는 곳은 [크기 2][바이트]
    seq_at, smp_at = 0x730000, 0x730400
    data[lorom(RELOC_SEQ_TABLE) + 2 * 3:lorom(RELOC_SEQ_TABLE) + 2 * 3 + 3] = seq_at.to_bytes(3, 'little')
    data[lorom(seq_at):lorom(seq_at) + 2 + len(seq)] = len(seq).to_bytes(2, 'little') + seq
    data[lorom(RELOC_SMP_TABLE) + 0x20 * 3:lorom(RELOC_SMP_TABLE) + 0x20 * 3 + 3] = smp_at.to_bytes(3, 'little')
    body = sample_body_bytes
    data[lorom(smp_at):lorom(smp_at) + 2 + len(body)] = len(body).to_bytes(2, 'little') + body
    at = lorom(patch.SONG_SETS)
    record = bytes([len(sets), 1]) + bytes(sets)
    data[at:at + len(record)] = record
    count_at = lorom(patch.RECORD_COUNT)
    data[count_at] = 3
    # 곡 0·1 도 레코드가 있어야 번호 2 를 읽는다
    blank = bytes([0, 0])
    data[at:at + 2 * 2 + len(record)] = blank + blank + record
    return data


class MemoryTests(unittest.TestCase):
    SAMPLE = 0x20
    SEQ = song()
    # 샘플 본체: [반복 간격 2][ADSR1·ADSR2·GAIN·음높이 2][BRR]
    BODY = bytes([0x20, 0x00, 1, 2, 3, 4, 5]) + bytes(range(0x30, 0x40))

    def setUp(self):
        self.data = rom_with_song(self.SEQ, self.BODY, [self.SAMPLE])

    def spc(self, good=True):
        spc = bytearray(0x10000)
        for i in range(0x100):
            spc[SPC_SEQUENCE_INDEX + i] = 0xFF
            spc[SPC_SAMPLE_INDEX + i] = 0xFF
        spc[SPC_SEQUENCE_INDEX + 2] = 3
        e = SPC_SEQUENCE_SLOTS + 3 * 6
        spc[e + 1:e + 5] = (0x3000).to_bytes(2, 'little') + len(self.SEQ).to_bytes(2, 'little')
        spc[0x3000:0x3000 + len(self.SEQ)] = self.SEQ
        spc[SPC_SAMPLE_INDEX + self.SAMPLE] = 4
        slot = SPC_SAMPLE_SLOTS + 4 * 8
        brr = self.BODY[7:]
        spc[slot:slot + 7] = len(brr).to_bytes(2, 'little') + self.BODY[2:7]
        d = SPC_DIR + 4 * 4
        spc[d:d + 4] = (0x4000).to_bytes(2, 'little') + (0x4020).to_bytes(2, 'little')
        spc[0x4000:0x4000 + len(brr)] = brr if good else bytes(len(brr))
        return bytes(spc)

    def test_sample_body_reads_relocated_sample(self):
        self.assertEqual(check.sample_body(self.data, self.SAMPLE), self.BODY)

    def test_memory_matches_when_spc_holds_rom_bytes(self):
        seq, result = check.memory(self.data, self.spc(), 2)
        self.assertEqual(seq, self.SEQ)
        self.assertEqual(result['sequence_slot'], 3)
        self.assertTrue(result['sequence_ok'])
        self.assertEqual(result['samples'], {'20': {'slot': 4, 'ok': True}})

    def test_changed_sample_bytes_fail(self):
        _, result = check.memory(self.data, self.spc(good=False), 2)
        self.assertFalse(result['samples']['20']['ok'])

    def test_missing_slots_are_reported_as_none(self):
        spc = bytearray(self.spc())
        spc[SPC_SEQUENCE_INDEX + 2] = 0xFF
        spc[SPC_SAMPLE_INDEX + self.SAMPLE] = 0xFF
        _, result = check.memory(self.data, bytes(spc), 2)
        self.assertIsNone(result['sequence_slot'])
        self.assertFalse(result['sequence_ok'])
        self.assertEqual(result['samples'], {'20': {'slot': None, 'ok': False}})


class MainTests(unittest.TestCase):
    def test_good_run_exits_zero_and_reports_json(self):
        mem = MemoryTests()
        mem.setUp()
        timing = TimingTests()
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            rom = tmp / 'rom.sfc'
            rom.write_bytes(mem.data)
            (tmp / 'spc.bin').write_bytes(mem.spc())
            (tmp / 'events.txt').write_text('song 02 started at frame 100\nsample 20 slot 04 at frame 90\n')
            timing.run_dir(tmp, timing.frames(), [0x1000, 0x1000, 0x2000], srcn=4)
            buf = io.StringIO()
            argv = ['dq4soundcheck.py', str(rom), str(tmp), '--song', '2']
            with contextlib.redirect_stdout(buf), unittest.mock.patch('sys.argv', argv):
                with self.assertRaises(SystemExit) as raised:
                    check.main()
        report = json.loads(buf.getvalue())
        self.assertEqual(raised.exception.code, 0)
        self.assertEqual(report['song'], '02')
        self.assertEqual(report['arrivals'], {'20': 90})
        self.assertTrue(report['memory']['sequence_ok'])
        self.assertEqual(report['timing']['voices'][0]['compared'], 3)


if __name__ == '__main__':
    unittest.main()
