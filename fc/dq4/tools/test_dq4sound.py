"""곡·효과음 풀기(곡 표·효과음 표·악보 바이트열·엔벨로프·비브라토·템포·음높이)와 드라이버 기록 → 음 사건·JSON·MIDI 를
합성 PRG 와 가짜 실행 기록으로 검사한다. 드라이버 실행(Run) 자체는 롬 코드가 있어야 해서 여기서는 다루지 않는다."""
import struct
import unittest
from types import SimpleNamespace

import dq4bank
import dq4sound as s

PRG_SIZE = 32 * 0x4000


def put(prg, bank, addr, data):
    o = dq4bank.prg_offset(bank, addr)
    prg[o:o + len(data)] = bytes(data)


def word(v):
    return [v & 0xFF, v >> 8]


def a4_period():
    return round(s.APU_CLOCK / (16 * 440) - 1)


def sound_prg():
    prg = bytearray(PRG_SIZE)
    # 곡 1: 뱅크 19 그대로, 곡 2: 뱅크 10 의 $8000 표 번호
    put(prg, 0x19, s.SONG_BANKS, [0x00, 0x00, 0x10])
    put(prg, 0x19, s.SONG_TABLE + 8 * 1, word(0x9000) + word(0x9010) + word(s.EMPTY) + word(s.EMPTY))
    put(prg, 0x19, s.SONG_TABLE + 8 * 2, word(0x0001) + word(0x0002) + word(0x0000) + word(0x9999))
    put(prg, 0x10, 0x8000, word(0x8100) + word(0x8200) + word(0x8300))
    put(prg, 0x19, s.SONG_TABLE + 8 * 0, word(s.EMPTY) * 4)
    put(prg, 0x19, s.SFX_TABLE, word(0x2000) + word(0xA300))
    periods = [a4_period() + i for i in range(99)]
    put(prg, 0x1F, s.PERIODS, [v for p in periods for v in word(p)])
    return prg


class TableTests(unittest.TestCase):
    def setUp(self):
        self.prg = sound_prg()

    def test_song_in_driver_bank(self):
        self.assertEqual(s.song_entry(self.prg, 1)[:2], (0x19, [0x9000, 0x9010, s.EMPTY, s.EMPTY]))

    def test_banked_song_reads_three_channels_and_empty_noise(self):
        bank, ptrs, raw = s.song_entry(self.prg, 2)
        self.assertEqual((bank, ptrs), (0x10, [0x8200, 0x8300, 0x8100, s.EMPTY]))
        self.assertEqual(raw[3], 0x9999)

    def test_unused_song(self):
        self.assertTrue(s.song_unused(self.prg, 0))
        self.assertFalse(s.song_unused(self.prg, 1))

    def test_sfx_channel_from_bit15(self):
        self.assertEqual(s.sfx_entry(self.prg, 0), ('noise', 0xA000))
        self.assertEqual(s.sfx_entry(self.prg, 1), ('pulse2', 0xA300))

    def test_noise_channel_data_stays_in_driver_bank(self):
        self.assertEqual(s.chan_bank(0x10, 3), 0x19)
        self.assertEqual(s.chan_bank(0x10, 0), 0x10)


class PitchTests(unittest.TestCase):
    def test_tick_rate_up_to_150_is_proportional(self):
        self.assertAlmostEqual(s.tick_rate(150), 1.0, places=3)
        self.assertAlmostEqual(s.tick_rate(75), 0.5, places=3)
        self.assertGreater(s.tick_rate(200), 200 / 150)

    def test_pitch_index_triangle_table(self):
        self.assertEqual(s.pitch_index(0x10, 0, False), 0x13)
        self.assertEqual(s.pitch_index(0x36, 0, True), 0x4E)
        self.assertEqual(s.pitch_index(0x02, 0xFE, False), 0x03)   # 이조 −2

    def test_period_to_midi(self):
        self.assertAlmostEqual(s.midi_of_period(a4_period()), 69, delta=0.05)
        self.assertAlmostEqual(s.midi_of_period(a4_period(), tri=True), 57, delta=0.05)
        self.assertEqual(s.note_name(60.4), 'C4')


class StreamTests(unittest.TestCase):
    def setUp(self):
        self.prg = prg = sound_prg()
        put(prg, 0x19, 0x9001, [0xE1, 0x05,                    # 엔벨로프 5
                                0x10,                          # 음 10(길이 없음)
                                75 + 0x11, 0x88, 0x84,         # 음 11, 길이 8 + 게이트 4
                                150 + 0x49, 0x03,              # 쉼 + 게이트 3
                                0xFE, 0x00, 0x91,              # 9100 으로 갔다가 돌아옴
                                0xFA, 0x02, 0xF5,              # 2번 되풀이, 앞 $9004 로
                                75 + 0x12, 0x00])              # 길이 0 = 끝
        put(prg, 0x19, 0x9100, [0x4A, 0xFD])
        put(prg, 0x19, 0x9020, [0xF3, 0x00, 0x92, 0x20])
        put(prg, 0x19, 0x9200, [0x06, 0x03, 0x02, 0x81, 0x00])

    def test_ops_lengths_and_jump_into_subroutine(self):
        items = s.decode_stream(self.prg, 0x19, 0x9001)
        ops = [(a, it['op']) for a, _, _, it in items]
        self.assertEqual(ops, [(0x9001, 'envelope'), (0x9003, 'note'), (0x9004, 'note'), (0x9007, 'rest'),
                               (0x9009, 'jump'), (0x900C, 'loop'), (0x900F, 'note'), (0x9100, 'tie'), (0x9101, 'return')])
        d = {a: it for a, _, _, it in items}
        self.assertEqual((d[0x9004]['len'], d[0x9004]['gate']), (8, 4))
        self.assertEqual(d[0x9007]['gate'], 3)
        self.assertEqual(d[0x900C], {'op': 'loop', 'count': 2, 'target': 0x9004})
        self.assertTrue(d[0x900F]['end'])
        self.assertEqual(items[2][1], '5C 88 84')

    def test_stop_at_other_channel_start(self):
        items = s.decode_stream(self.prg, 0x19, 0x9001, stops={0x9004})
        self.assertEqual(items[-1][3], {'op': 'falls-into', 'target': 0x9004})

    def test_rhythm_pattern_stops_at_zero(self):
        items = s.decode_stream(self.prg, 0x19, 0x9020, stops={0x9024})
        self.assertEqual(items[0][3]['pattern'], [[6, 3], [2, None]])

    def test_score_text_mentions_tempo_and_empty_channels(self):
        put(self.prg, 0x19, 0x9000, [150])
        text = s.score_text(self.prg, 1)
        self.assertIn('tempo 150', text)
        self.assertEqual(text.count('(빈 채널)'), 2)


class EnvelopeTests(unittest.TestCase):
    def setUp(self):
        self.prg = prg = sound_prg()
        put(prg, 0x19, s.ENV_TABLE + 4, word(0x9400))
        # 자리 0: 2 로 건너뜀(떼기 자리 1 = 6), 3F 한 프레임 + 3 머묾, 30, 다시 4 로
        put(prg, 0x19, 0x9400, [0xC2, 0x06, 0x7F, 0x03, 0x70, 0xC4, 0xB1, 0x01, 0xC6])
        put(prg, 0x19, s.VIB_TABLE + 2, word(0x9500))
        put(prg, 0x19, 0x9500, [0x04, 0x84, 0x0B, 0x01, 0x02])

    def test_steps_hold_and_loop(self):
        self.assertEqual(s.envelope_steps(self.prg, 4), ([(0x7F, 4), (0x70, 1)], 4))

    def test_info_release_and_duty(self):
        e = s.envelope_info(self.prg, 4)
        self.assertEqual((e['release_at'], e['release'], e['release_loop']), (6, [[0xB1, 2]], 6))
        self.assertEqual(e['duty'], ['25%', '50%'])
        self.assertEqual(s.steps_text([(0x7F, 4), (0x70, 1)]), 'F×4 0')

    def test_vibrato_bytes(self):
        self.assertEqual(s.vibrato_text(self.prg, 2), '01 E1 w2 →0')


class MidiPartsTests(unittest.TestCase):
    def test_vlq(self):
        self.assertEqual(s.vlq(0), b'\x00')
        self.assertEqual(s.vlq(0x7F), b'\x7f')
        self.assertEqual(s.vlq(0x80), b'\x81\x00')
        self.assertEqual(s.vlq(0x3FFF), b'\xff\x7f')

    def test_track_sorts_and_uses_deltas(self):
        t = s.track([(10, 0, b'\x90\x40\x64'), (0, 0, b'\xc0\x50')])
        self.assertEqual(t[:4], b'MTrk')
        n = struct.unpack('>I', t[4:8])[0]
        self.assertEqual(len(t), 8 + n)
        self.assertEqual(t[8:], b'\x00\xc0\x50' + b'\x0a\x90\x40\x64' + b'\x00\xff\x2f\x00')


def fake_run(prg, n=1):
    # (틱, 채널, 음, 길이, 게이트, 엔벨로프, 이조, 고정 음량, 주소, 프레임)
    events = [(0, 0, 0x10, 8, 4, 0x05, 0, 0xFF, 0x9003, 1),
              (8, 0, 0x4A, 8, 0, 0x05, 0, 0xFF, 0x9004, 2),     # 잇기: 앞 음이 16틱
              (16, 0, 0x49, 4, 0, 0x05, 0, 0xFF, 0x9005, 3),
              (0, 2, 0x36, 12, 12, 0xFF, 0xFE, 0xFF, 0x9011, 1),
              (0, 3, 0x05, 6, 6, 0xFF, 0, 0x08, 0x9012, 1),
              (20, 0, 0x11, 0, 0, 0x05, 0, 0xFF, 0x9006, 4)]
    extra = [{'ch_vol': 0xF, 'detune': 0, 'vibrato': None, 'master_vol': 0xF, 'bank': 0x19}] * len(events)
    a4 = word(a4_period() + 0x13)
    return SimpleNamespace(prg=prg, n=n, sfx=n >= 0x80, events=events, extra=extra, tempos=[(0, 150), (10, 75)],
                           loop_start=None, loop_len=None, tick=24,
                           frames=[[], [(0x4002, a4[0]), (0x4003, a4[1])], [], []], ticks_at=[4, 8, 12],
                           vols=[(0, 0, 0x0F, 0x0F), (4, 0, 0x08, 0x0F), (0, 3, 0x08, 0x07)])


class RunOutputTests(unittest.TestCase):
    def setUp(self):
        self.prg = sound_prg()
        self.run = fake_run(self.prg)

    def test_notes_tie_rest_noise_and_end(self):
        ns = s.notes(self.run)
        self.assertEqual([(c, t, d, n) for c, t, d, _, n, _ in ns], [(0, 0, 16, 0x10), (2, 0, 12, 0x36), (3, 0, 6, 0x05)])
        self.assertIsNone(ns[2][3])
        tri_idx = s.pitch_index(0x36, 0xFE, True)
        self.assertAlmostEqual(ns[1][3], s.midi_of_period(s.period(self.prg, tri_idx), True))

    def test_song_json_timeline(self):
        j = s.song_json(self.prg, self.run)
        self.assertEqual((j['id'], j['kind'], j['tempo'], j['tempo_changes']), ('01', 'song', 150, [[10, 75]]))
        tl = j['timeline']
        self.assertEqual([e['op'] for e in tl], ['note', 'tie', 'rest', 'note', 'note', 'end'])
        self.assertEqual(tl[3]['transpose'], -2)
        self.assertEqual(tl[4]['noise_period'], 5)
        self.assertEqual(tl[4]['fixed_vol'], 8)
        self.assertNotIn('midi', tl[4])
        self.assertEqual(list(j['envelopes']), ['05'])
        self.assertEqual([c['name'] for c in j['channels']], s.CH_NAMES[:4])
        self.assertEqual(j['channels'][2]['items'], [])

    def test_midi_chunks_are_well_formed(self):
        mid = s.midi_bytes(self.run, 'test')
        self.assertEqual(mid[:4], b'MThd')
        fmt, ntrk, ppq = struct.unpack('>HHH', mid[8:14])
        self.assertEqual((fmt, ntrk, ppq), (1, 5, s.PPQ))
        pos, chunks = 14, []
        while pos < len(mid):
            self.assertEqual(mid[pos:pos + 4], b'MTrk')
            n = struct.unpack('>I', mid[pos + 4:pos + 8])[0]
            chunks.append(mid[pos + 8:pos + 8 + n])
            pos += 8 + n
        self.assertEqual(pos, len(mid))
        self.assertEqual(len(chunks), 5)
        self.assertIn(b'\x99\x26\x64', chunks[4])              # 노이즈 주기 5 → 드럼 38, MIDI 채널 10
        self.assertIn(b'\x89\x26\x00', chunks[4])
        for c in chunks:
            self.assertTrue(c.endswith(b'\x00\xff\x2f\x00'))

    def test_pitch_bend_is_offset_from_note_key(self):
        ns = s.notes(self.run)
        m = ns[0][3]
        want = 8192 + round((m - round(m)) / 2 * 8192)
        self.assertEqual(s.pitch_bends(self.run, ns, 0, 24), [(4, 2.5, bytes([0xE0, want & 0x7F, want >> 7]))])

    def test_volume_events_only_on_change(self):
        out = s.volume_events(self.run, 0, 24)
        self.assertEqual([e[2] for e in out], [bytes([0xB0, 7, 127]), bytes([0xB0, 11, 127]), bytes([0xB0, 11, 68])])

    def test_midi_tempo_meta(self):
        mid = s.midi_bytes(self.run, 't')
        us = round(s.PPQ / (s.FPS * s.tick_rate(150)) * 1e6)
        self.assertIn(b'\xff\x51\x03' + us.to_bytes(3, 'big'), mid)



class ScoreTests(unittest.TestCase):
    def setUp(self):
        self.prg = sound_prg()
        self.run = fake_run(self.prg)

    def test_score_data_shifts_first_tick_and_trims_overlaps(self):
        parts, end, bar, tempos, loop = s.score_data(self.run)
        self.assertEqual([p[0] for p in parts], s.CH_NAMES[:4])
        self.assertEqual(parts[0][2], [(-1, 16, round(s.notes(self.run)[0][3]))])   # 틱 0 의 음은 −1 로
        self.assertEqual(parts[3][1], 'perc')
        self.assertEqual((end, bar, loop), (23, 96, None))
        self.assertAlmostEqual(tempos[0][1], 60 * s.FPS * s.tick_rate(150) / s.PPQ)

    def test_three_four_when_loop_is_72(self):
        self.run.loop_start, self.run.loop_len = 1, 72
        self.assertEqual(s.score_data(self.run)[2], 72)

    def test_musicxml_matches_midi(self):
        self.run.events = [ev for ev in self.run.events if ev[0] >= 1] + [(1, 1, 0x20, 30, 30, 5, 0, 0xFF, 0, 1)]
        self.run.extra = self.run.extra[:len(self.run.events)]
        self.run.tick = 40
        xml = s.song_musicxml(self.run, 'test')
        self.assertTrue(xml.startswith('<?xml'))
        self.assertEqual(s.score_check(self.run, xml), [])


class NsfTests(unittest.TestCase):
    def test_header_banks_and_driver_patch(self):
        prg = sound_prg()
        prg[0x1F * 0x4000 + (s.NSF_FREE & 0x3FFF):0x1F * 0x4000 + (0xFF74 & 0x3FFF)] = b'\xff' * (0xFF74 - s.NSF_FREE)
        data, tracks, start_pc = s.nsf_bytes(prg, start=2)
        self.assertEqual(tracks, [1, 2, 0x80, 0x81])
        self.assertEqual(len(data), 0x80 + len(s.NSF_BANKS) * 0x4000)
        self.assertEqual(data[:5], b'NESM\x1a')
        self.assertEqual((data[6], data[7]), (4, 2))
        load, init, play = struct.unpack('<HHH', data[8:14])
        self.assertEqual((load, play), (0x8000, s.NSF_PLAY))
        self.assertEqual(data[0x70:0x78], bytes([0, 1, 2, 3, 24, 25, 26, 27]))
        fixed = data[0x80 + 6 * 0x4000:]
        bankmap = fixed[s.NSF_FREE - 0xC000:s.NSF_FREE - 0xC000 + 0x20]
        self.assertEqual([bankmap[b] for b in s.NSF_BANKS], [4 * i for i in range(len(s.NSF_BANKS))])
        self.assertEqual(list(fixed[s.NSF_FREE + 0x20 - 0xC000:][:4]), tracks)
        self.assertEqual(init, s.NSF_FREE + 0x20 + len(tracks))
        self.assertEqual(fixed[0xFF94 - 0xC000], 0x48)
        self.assertEqual(fixed[start_pc - 0xC000:start_pc - 0xC000 + 3], bytes([0x20, 0x59, 0xEF]))
        self.assertEqual(data[0x80:0x80 + 0x4000], bytes(prg[0x19 * 0x4000:0x1A * 0x4000]))


if __name__ == '__main__':
    unittest.main()
