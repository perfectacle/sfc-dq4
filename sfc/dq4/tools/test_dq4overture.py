import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

import numpy as np

import dq4overture as ov
from dq5map import Rom, lorom
from dq5song import RELOC_SEQ_TABLE, assemble, play

ROOT = Path(__file__).resolve().parents[3]
NES, SFC = ROOT / 'rom' / 'dq4.nes', ROOT / 'rom' / 'dq5.sfc'


class WriterTests(unittest.TestCase):
    def test_long_note_is_tied_legato(self):
        w = ov.Writer()
        w.put(0x30, 0x200, 0xFE)
        self.assertEqual(w.lines, ['  gate_preset 00', '  note 30 len F0', '  tie', '  gate_preset FE', '  tie len 20'])

    def test_gate_preset_is_a_table_value(self):
        self.assertEqual(ov.gate_preset(0.5), 0x80)
        self.assertEqual(ov.gate_preset(0.75), 0xBF)

    def test_tempo_map_is_sorted_and_in_driver_range(self):
        ticks = [k for k, _ in ov.NDS_TEMPO]
        self.assertEqual(ticks, sorted(set(ticks)))
        self.assertTrue(all(0 < t < 0xFB for _, t in ov.NDS_TEMPO))
        self.assertEqual(ov.tempo_at(ov.FC_MARCH[0] + 100), 121)


class SetTableTests(unittest.TestCase):
    def rom(self, title):
        from dq5map import Rom, lorom
        from dq5spc import SEQUENCE_COUNT
        records = [bytes([len(title), 1, *title]) if song == ov.SONG else bytes([1, 1, 0x00])
                   for song in range(SEQUENCE_COUNT)]
        data = bytearray(0x200000)
        table = b''.join(records)
        data[lorom(ov.SONG_SETS):lorom(ov.SONG_SETS) + len(table)] = table
        return Rom(data), records

    def test_only_the_title_record_grows(self):
        rom, records = self.rom(ov.ORIGINAL_SAMPLES)
        table, old = ov.set_table(rom)
        self.assertEqual(old, sum(map(len, records)))
        self.assertEqual(len(table) - old, len(ov.SAMPLES) - len(ov.ORIGINAL_SAMPLES))
        at = sum(map(len, records[:ov.SONG]))
        self.assertEqual(table[at:at + 2 + len(ov.SAMPLES)], bytes([len(ov.SAMPLES), ov.SEND_FIRST, *ov.SAMPLES]))
        self.assertEqual(table[:at], b''.join(records[:ov.SONG]))

    def test_rejects_a_changed_title_record(self):
        with self.assertRaisesRegex(ValueError, 'original title samples'):
            ov.set_table(self.rom(ov.SAMPLES)[0])


@unittest.skipUnless(NES.exists() and SFC.exists(), 'rom/dq4.nes and rom/dq5.sfc are user supplied')
class ArrangementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from dq5map import Rom
        cls.score = ov.fc_score(str(NES))
        cls.rom = Rom(SFC.read_bytes())
        cls.snare = ov.reference_snare(cls.rom)
        cls.seq = assemble(ov.arrange(cls.score, cls.snare, ov.original_listing(cls.rom)))

    def test_every_fc_note_lands_on_twice_its_tick(self):
        cycle = ov.cycle_ticks(self.score)
        events = play(self.seq, cycle + 10, ov.OVERTURE_FLAG)
        tracks = {'pulse1': (0, 3), 'pulse2': (1, 2), 'triangle': (4, 5)}
        transpose = {2: -12, 5: -12}
        for ch, indices in tracks.items():
            want = [(e['tick'] * 2, round(e['midi']) - ov.MIDI_OFFSET) for e in self.score['timeline']
                    if e['ch'] == ch and e['op'] == 'note']
            for i in indices:
                got = [(t, n - transpose.get(i, 0)) for t, n, _, _ in events[i] if isinstance(n, int) and t < cycle]
                # 트랙 3(현)은 행진부터 선율을 겹친다. play 는 0 틱부터, FC 는 1 틱부터 센다
                start = ov.song_tick(ov.FC_MARCH[0]) + 2 if i == 3 else 0
                self.assertEqual([(t + 2, n) for t, n in got], [w for w in want if w[0] >= start], f'track {i}')

    def test_snare_matches_reference_track(self):
        from dq5spc import body, sequences
        _, addr, n = sequences(self.rom)[ov.REF_SONG]
        ref = play(bytes(body(self.rom, addr, n)), 12000)[ov.REF_SNARE_TRACK]
        lo, hi = ov.REF_MARCH
        shift = ov.song_tick(ov.FC_MARCH[0]) - lo
        want = [(t + shift, x) for t, x, _, _ in ref if isinstance(x, int) and lo <= t < hi]
        self.assertEqual([(t, x) for t, x, _ in self.snare], want)
        self.assertTrue(want)

    def test_overture_repeats(self):
        cycle = ov.cycle_ticks(self.score)
        ev = play(self.seq, 2 * cycle + 10, ov.OVERTURE_FLAG)[0]
        first = [(t, n) for t, n, _, _ in ev if isinstance(n, int) and t < cycle]
        second = [(t - cycle, n) for t, n, _, _ in ev if isinstance(n, int) and cycle <= t < 2 * cycle]
        self.assertEqual(first, second)

    def test_flag_zero_is_the_original_title_song(self):
        from dq5spc import body, sequences
        _, addr, n = sequences(self.rom)[ov.SONG]
        want = play(bytes(body(self.rom, addr, n)), 3000)
        got = play(self.seq, 3000)
        for i in range(len(want)):
            # 갈래를 고르는 if_flag·jump 는 시간을 쓰지 않으므로 음 시각까지 같다
            self.assertEqual([e[:2] for e in got[i]], [e[:2] for e in want[i]], f'track {i}')
        self.assertEqual(got[len(want)], [])

    def test_song_set_table(self):
        table, old = ov.set_table(self.rom)
        self.assertEqual(len(table) - old, len(ov.SAMPLES) - len(ov.ORIGINAL_SAMPLES))
        self.assertLessEqual(ov.SPC_SET_TABLE + len(table), ov.SPC_SAMPLE_AREA)


class TrackNotesTests(unittest.TestCase):
    SEQ = assemble([
        'tempo 78', 'track L0', 'track L1',
        'L0:', '  volume2 40', '  note 30 len 10', '  call -> LS', '  volume2 70', '  note 32', '  end',
        'LS:', '  volume2 55', '  note 31 len 08', '  ret',
        'L1:', '  if_flag 01 -> LF', '  note 20 len 06', '  end',
        'LF:', '  volume2 33', 'LA:', '  note 21 len 04', '  loop2 -> LA', '  end',
    ])

    def test_each_note_carries_the_volume2_before_it_through_call_and_ret(self):
        self.assertEqual(ov.track_notes(self.SEQ, 0),
                         [(0, 0x30, 0x10, 0x40), (0x10, 0x31, 0x08, 0x55), (0x18, 0x32, 0x08, 0x70)])

    def test_flag_branch_and_loop_follow_play(self):
        self.assertEqual(ov.track_notes(self.SEQ, 1), [(0, 0x20, 0x06, None)])
        # loop2 는 한 번 되돌아가 두 번 울린다. 틱은 play 와 같아야 스네어를 이 곡 틱으로 옮길 수 있다
        self.assertEqual(ov.track_notes(self.SEQ, 1, flag=1), [(0, 0x21, 0x04, 0x33), (4, 0x21, 0x04, 0x33)])
        self.assertEqual([t for t, *_ in ov.track_notes(self.SEQ, 1, flag=1)],
                         [t for t, n, _, _ in play(self.SEQ, 100, 1)[1] if isinstance(n, int)])


class TrackNotesLoopTests(unittest.TestCase):
    SEQ = assemble([
        'tempo 78', 'track L0',
        'L0:', '  note 30 len 04',
        'LA:', '  note 31 len 02', '  loop2 -> LA',
        'LB:', '  note 32 len 02', '  loop2b -> LB',
        'LC:', '  note 33 len 02', '  loop 03 -> LC',
        '  rest len 02', '  jump -> LD', '  note 3F len 02',
        'LD:', '  note 34 len 02', '  end',
    ])

    def test_counted_loops_repeat_and_jumps_skip_and_rests_have_no_note(self):
        got = ov.track_notes(self.SEQ, 0)
        self.assertEqual([(t, n, d) for t, n, d, _ in got],
                         [(0, 0x30, 4), (4, 0x31, 2), (6, 0x31, 2), (8, 0x32, 2), (10, 0x32, 2),
                          (12, 0x33, 2), (14, 0x33, 2), (16, 0x33, 2), (18, None, 2), (20, 0x34, 2)])
        self.assertEqual([t for t, n, _, _ in got if n is not None],
                         [t for t, n, _, _ in play(self.SEQ, 100)[0] if isinstance(n, int)])


class FactorTests(unittest.TestCase):
    CHUNK = ['  volume2 50', '  note 30 len 0C', '  note 32 len 0C', '  note 34 len 0C', '  rest len 0C']

    def program(self, body, subs=()):
        return assemble(['tempo 78', 'track LT', 'LT:'] + list(body) + ['  end'] + list(subs))

    def test_repeats_become_calls_that_play_the_same(self):
        body = ['  volume2 40'] + self.CHUNK * 3 + ['  note 20 len 04']
        lines, subs = ov.factor(body, 'LX')
        self.assertIn('  call -> LX0', lines)
        before, after = self.program(body), self.program(lines, subs)
        self.assertLess(len(after), len(before))
        self.assertEqual(play(after, 400), play(before, 400))

    def test_labels_and_jumps_are_never_inside_a_subroutine(self):
        loop = ['LQ:'] + self.CHUNK + ['  jump -> LQ']
        lines, subs = ov.factor(loop + self.CHUNK, 'LX')
        for ln in subs:
            if not ln.startswith('LX'):
                self.assertNotIn(ln.split()[0], ('jump', 'end'))
                self.assertFalse(ln.endswith(':'))
        self.assertIn('LQ:', lines)
        self.assertIn('  jump -> LQ', lines)

    def test_depth_one_never_nests_calls(self):
        inner = self.CHUNK[1:4]
        outer = inner * 3 + ['  note 40 len 02']
        lines, subs = ov.factor(outer * 3, 'LX', depth=1)
        self.assertFalse([ln for ln in subs if ln.split()[0] == 'call'])
        lines2, subs2 = ov.factor(outer * 3, 'LX', depth=2)
        self.assertEqual(play(self.program(lines2, subs2), 2000), play(self.program(outer * 3), 2000))
        self.assertLessEqual(len(self.program(lines2, subs2)), len(self.program(lines, subs)))


def synthetic_original():
    """build 가 읽고 덮는 자리만 채운 2MB 롬: 곡 묶음 표(곡 10 은 원래 타이틀 샘플)·IPL 블록 길이·끝 표시와
    타이틀·메뉴·페이드 부르기의 원래 명령. 값은 도구가 put 에 넘기는 기대 바이트 그대로다."""
    from dq5spc import SEQUENCE_COUNT
    data = bytearray(0x200000)
    records = [bytes([len(ov.ORIGINAL_SAMPLES), 1, *ov.ORIGINAL_SAMPLES]) if song == ov.SONG else bytes([1, 1, 0x00])
               for song in range(SEQUENCE_COUNT)]
    table = b''.join(records)
    at = ov.rom_off(ov.SONG_SETS)
    data[at:at + len(table) + 4] = table + ov.IPL_END
    data[ov.rom_off(ov.IPL_BLOCK):ov.rom_off(ov.IPL_BLOCK) + 2] = (0x1234).to_bytes(2, 'little')
    data[ov.TITLE_CALL:ov.TITLE_CALL + 6] = ov.TITLE_CALL_ORIG
    data[ov.MENU_CALL:ov.MENU_CALL + 6] = ov.MENU_CALL_ORIG
    data[ov.MENU_FADE] = 0x10
    data[ov.rom_off(ov.FADE_CALL):ov.rom_off(ov.FADE_CALL) + 3] = ov.FADE_CALL_ORIG
    return bytes(data), len(table)


class BuildTests(unittest.TestCase):
    LINES = ['tempo 78', 'track L0', 'L0:', '  note 30 len 10', '  end']

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.original, self.table_size = synthetic_original()
        self.rom_path, self.title_path = self.root / 'dq5.sfc', self.root / 'title.sfc'
        self.rom_path.write_bytes(self.original)
        self.title_path.write_bytes(self.original + bytes(ov.TITLE_SIZE - len(self.original)))

    def tearDown(self):
        self.directory.cleanup()

    def run_build(self, original=None, title=None):
        if original is not None:
            self.rom_path.write_bytes(original)
        if title is not None:
            self.title_path.write_bytes(title)
        sha = hashlib.sha1(self.rom_path.read_bytes()).hexdigest()
        with mock.patch.object(ov, 'SOURCE_SHA1', sha), \
                mock.patch.object(ov, 'fc_score', return_value={'end_tick': 8}), \
                mock.patch.object(ov, 'reference_snare', return_value=[]), \
                mock.patch.object(ov, 'original_listing', return_value=[]), \
                mock.patch.object(ov, 'arrange', return_value=self.LINES):
            report = ov.build('fc.nes', self.rom_path, self.title_path, self.root / 'out' / 'o.sfc')
        return (self.root / 'out' / 'o.sfc').read_bytes(), report

    def test_song_set_table_grows_in_place_and_the_ipl_block_follows(self):
        out, _ = self.run_build()
        grow = len(ov.SAMPLES) - len(ov.ORIGINAL_SAMPLES)
        block = ov.rom_off(ov.IPL_BLOCK)
        self.assertEqual(int.from_bytes(out[block:block + 2], 'little'), 0x1234 + grow)
        end = ov.rom_off(ov.SONG_SETS) + self.table_size + grow
        self.assertEqual(out[end:end + 4], ov.IPL_END)
        rom = Rom(out)
        a = ov.SONG_SETS
        for _ in range(ov.SONG):
            a += rom.u8(a) + 2
        self.assertEqual(list(out[ov.rom_off(a):ov.rom_off(a) + 2 + len(ov.SAMPLES)]),
                         [len(ov.SAMPLES), ov.SEND_FIRST, *ov.SAMPLES])

    def test_title_menu_and_fade_jump_to_their_stubs(self):
        out, _ = self.run_build()
        stub = ov.TITLE_STUB
        self.assertEqual(out[ov.TITLE_CALL:ov.TITLE_CALL + 6],
                         bytes([0x22, stub & 0xFF, stub >> 8 & 0xFF, stub >> 16, 0xEA, 0xEA]))
        title = out[ov.rom_off(stub):ov.rom_off(stub) + 18]
        self.assertEqual(title[4:6], bytes([0xA2, ov.OVERTURE_FLAG]))   # LDX #갈래 = 서곡
        self.assertEqual(title[-1], 0x6B)
        menu = ov.MENU_STUB
        self.assertEqual(out[ov.MENU_CALL:ov.MENU_CALL + 4], bytes([0x22, menu & 0xFF, menu >> 8 & 0xFF, menu >> 16]))
        self.assertEqual(out[ov.MENU_FADE], ov.MENU_SONG)
        fade = ov.rom_off(ov.FADE_CALL)
        self.assertEqual(out[fade:fade + 3], bytes([0x4C]) + (ov.FADE_STUB & 0xFFFF).to_bytes(2, 'little'))
        back = out[ov.rom_off(ov.FADE_STUB):ov.rom_off(ov.FADE_STUB) + 21]
        # 고리는 바꾼 3바이트 바로 뒤(밝기 반복의 분기 대상)로 돌아가야 한다
        self.assertEqual(back[-3:], bytes([0x4C]) + (ov.FADE_CALL + 3 & 0xFFFF).to_bytes(2, 'little'))
        self.assertLess(ov.rom_off(stub) + 18, ov.rom_off(menu))

    def test_relocated_sequence_is_where_the_pointer_table_says(self):
        out, report = self.run_build()
        at = lorom(RELOC_SEQ_TABLE) + ov.SONG * 3
        ptr = int.from_bytes(out[at:at + 3], 'little')
        seq = assemble(self.LINES)
        pos = ov.rom_off(ptr)
        self.assertEqual(out[pos:pos + 2 + len(seq)], len(seq).to_bytes(2, 'little') + seq)
        self.assertEqual(report['sequence']['bytes'], len(seq))
        self.assertEqual(len(out), ov.OUT_SIZE)
        self.assertEqual(out[0x7FD7], 0x0C)

    def test_ips_and_report_match_the_output(self):
        from kr_patch import ips
        out, report = self.run_build()
        folder = self.root / 'out'
        self.assertEqual(ips.apply(self.original, (folder / 'o.ips').read_bytes()), out)
        self.assertEqual(report['rom_sha1'], hashlib.sha1(out).hexdigest())
        self.assertEqual(json.loads((folder / 'o.json').read_text())['rom_sha1'], report['rom_sha1'])
        self.assertEqual((folder / 'o.txt').read_text().splitlines(), self.LINES)

    def test_rejects_wrong_inputs(self):
        with self.subTest('title size'), self.assertRaisesRegex(ValueError, '4MB'):
            self.run_build(title=self.original)
        title = bytearray(self.original + bytes(ov.TITLE_SIZE - len(self.original)))
        title[ov.rom_off(ov.TITLE_STUB)] = 0xEA
        with self.subTest('stub occupied'), self.assertRaisesRegex(ValueError, 'expected'):
            self.run_build(title=bytes(title))
        crowded = bytearray(self.original)
        crowded[ov.rom_off(ov.SONG_SETS) + self.table_size + 4] = 0x55
        with self.subTest('bytes after table'), self.assertRaisesRegex(ValueError, 'after the song set table'):
            self.run_build(original=bytes(crowded), title=bytes(crowded) + bytes(ov.TITLE_SIZE - len(crowded)))
        with self.subTest('sha'), mock.patch.object(ov, 'SOURCE_SHA1', '0' * 40), \
                self.assertRaisesRegex(ValueError, 'SHA-1'):
            ov.build('fc.nes', self.rom_path, self.title_path, self.root / 'x.sfc')


def ev(ch, tick, length, op='note', midi=60, gate=0, vol=15):
    return {'ch': ch, 'tick': tick, 'len': length, 'op': op, 'midi': midi, 'gate': gate, 'ch_vol': vol}


def synthetic_score():
    """틱 1~4085 을 빈틈없이 덮는 가짜 FC 악보. 펄스1 은 팡파르(96틱 음 둘과 짧은 음), 행진, 끝 화음 둘."""
    timeline = [
        ev('pulse1', 1, 96, midi=67), ev('pulse1', 97, 96, midi=60),
        *[ev('pulse1', start, 95, midi=62) for start in (193, 288, 383, 478, 573)], ev('pulse1', 668, 83, midi=65),
        ev('pulse1', 751, 3264, midi=64), ev('pulse1', 4015, 40, midi=60), ev('pulse1', 4055, 30, midi=67),
        ev('pulse2', 1, 50, midi=60, gate=20, vol=10), ev('pulse2', 51, 50, op='tie', gate=10, vol=10),
        ev('pulse2', 101, 3984, midi=55),
        ev('triangle', 1, 100, op='rest', midi=None), ev('triangle', 101, 3984, midi=48, gate=0),
    ]
    return {'timeline': timeline + [ev('pulse1', 4085, 5, op='end')], 'end_tick': 4085, 'tempo': 120,
            'tempo_changes': []}


class PartsTests(unittest.TestCase):
    def setUp(self):
        self.parts = ov.parts(synthetic_score())

    def test_ties_join_the_previous_note_and_keep_a_gate_inside_the_whole_length(self):
        # 펄스2: 음 1~50(게이트 20) + 붙임 51~100(게이트 10) → 길이 100, 소리 틱 50 + 10
        first = self.parts['pulse2'][0]
        self.assertEqual(first, (1, 100, 60, 60, 10 / 15))
        self.assertEqual(len(self.parts['pulse2']), 3)

    def test_note_without_a_gate_sounds_to_the_end(self):
        self.assertEqual(self.parts['pulse1'][0], (1, 96, 67, None, 1.0))

    def test_triangle_gate_is_a_level_not_a_length(self):
        # 게이트 0 → 음량 15/15, 15 이하는 gate/15
        self.assertEqual(self.parts['triangle'][1], (101, 3984, 48, None, 1.0))
        score = synthetic_score()
        score['timeline'][-2] = ev('triangle', 101, 3984, midi=48, gate=9)
        self.assertEqual(ov.parts(score)['triangle'][1][4], 9 / 15)

    def test_rest_events_have_no_pitch(self):
        self.assertEqual(self.parts['triangle'][0], (1, 100, None, None, 0.0 + self.parts['triangle'][0][4]))
        self.assertIsNone(self.parts['triangle'][0][2])

    def test_last_rest_runs_to_the_end_tick_plus_the_ring_time(self):
        for evs in self.parts.values():
            start, length, midi, gate, level = evs[-1]
            self.assertEqual((midi, gate, level), (None, None, 0))
            self.assertEqual(start + length, 4085 + ov.RING_TICKS)

    def test_a_gap_between_notes_is_an_error(self):
        score = synthetic_score()
        score['timeline'].insert(0, ev('pulse1', 1000, 5))
        score['timeline'].insert(0, ev('pulse1', 1001, 5))
        with self.assertRaisesRegex(ValueError, 'pulse1: gap at tick'):
            ov.parts(score)


class MelodicTests(unittest.TestCase):
    def lines(self, evs, labels=None):
        w = ov.Writer()
        ov.melodic(w, evs, lambda level: round(0x80 * level), labels)
        return w.lines

    def test_notes_rests_gate_and_the_ring_release_on_the_last_note(self):
        evs = [(1, 10, 60, None, 1.0), (11, 5, None, None, 0), (16, 6, 62, 3, 0.5)]
        self.assertEqual(self.lines(evs), [
            '  volume2 80', '  gate_preset FE', '  note 25 len 14', '  rest len 0A',
            '  volume2 40', f'  release {ov.RING_RELEASE:02X}', '  gate_preset 80', '  note 27 len 0C'])

    def test_a_label_restarts_the_running_state(self):
        evs = [(1, 10, 60, None, 1.0), (11, 10, 60, None, 1.0), (21, 10, 62, None, 1.0)]
        self.assertEqual(self.lines(evs, {11: 'LBL'}), [
            '  volume2 80', '  gate_preset FE', '  note 25 len 14',
            'LBL:', '  volume2 80', '  gate_preset FE', '  note 25 len 14',
            f'  release {ov.RING_RELEASE:02X}', '  note 27'])

    def test_song_tick_doubles_the_length_from_zero(self):
        self.assertEqual([ov.song_tick(t) for t in (0, 1, 2, 751)], [0, 0, 2, 1500])


class PercussionTests(unittest.TestCase):
    P = {'pulse1': [(1, 100, 67, None, 1.0), (4015, 40, 60, None, 1.0), (4055, 30, 67, None, 1.0)],
         'pulse2': [(1, 4084, 60, None, 1.0)], 'triangle': [(1, 4084, 48, None, 1.0)]}

    def setUp(self):
        self.hits, self.end, self.rolls = ov.percussion(self.P, [(10, 5, 0xA0), (20, 5, 0)])

    def test_snare_hits_keep_their_volume_or_default(self):
        snares = [h for h in self.hits if h[1] == ov.SNARE]
        self.assertEqual(snares, [(10, ov.SNARE, 5, 0xA0), (20, ov.SNARE, 5, 0x80)])

    def test_fanfare_long_note_starts_with_a_timpani_hit_and_a_roll(self):
        timpani = ov.TIMPANI_NOTE['G']
        self.assertIn((0, ov.TIMPANI, timpani, 0xC0), self.hits)
        # 롤: FC 틱 7 에서 88 까지 3틱 간격 28타. 첫 타만 세기(50)를 갖고 나머지는 None, 미끄럼은 틱 12 에서 162 동안
        roll = [h for h in self.hits if h[1] == ov.TIMPANI and 12 <= h[0] <= 174]
        self.assertEqual(len(roll), 28)
        self.assertEqual(roll[0], (12, ov.TIMPANI, timpani, 0x50))
        self.assertTrue(all(h[3] is None for h in roll[1:]))
        self.assertEqual(self.rolls[12], (0xA0, 162))

    def test_tail_chords_hit_the_timpani_and_the_last_chord_rolls(self):
        c, g = ov.TIMPANI_NOTE['C'], ov.TIMPANI_NOTE['G']
        self.assertIn((8028, ov.TIMPANI, c, 0xB0), self.hits)
        self.assertIn((8108, ov.TIMPANI, g, 0xB0), self.hits)
        final = [h for h in self.hits if h[0] > 8108]
        self.assertEqual(len(final), 7)
        self.assertEqual(final[0], (8114, ov.TIMPANI, c, 0x70))

    def test_end_is_the_latest_part_end_and_hits_are_sorted(self):
        self.assertEqual(self.end, 2 * (4085 - 1))
        keys = [h[0] for h in self.hits]
        self.assertEqual(keys, sorted(keys))
        self.assertEqual(len(self.hits), 2 + 1 + 28 + 2 + 7)


class PercTrackTests(unittest.TestCase):
    def test_instrument_volume_roll_and_tempo_lines_in_order(self):
        hits = [(0, ov.TIMPANI, 0x27, 0xC0), (12, ov.TIMPANI, 0x27, 0x50), (24, ov.SNARE, 5, 0x80)]
        w = ov.Writer()
        with mock.patch.object(ov, 'NDS_TEMPO', [(1, 100), (25, 50)]):
            ov.perc_track(w, hits, 48, {12: (0xA0, 12)})
        self.assertEqual(w.lines, [
            '  tempo 64', '  instrument 02', '  release 14', '  volume2 C0', '  gate_preset FE', '  note 27 len 0C',
            '  volume2 50', '  volume2_slide A0 0C', '  note 27',
            '  instrument 05', '  release 14', '  volume2 80', '  note 05 len 18', '  tempo 32'])

    def test_silence_between_hits_is_a_rest(self):
        w = ov.Writer()
        with mock.patch.object(ov, 'NDS_TEMPO', [(1, 100)]):
            ov.perc_track(w, [(10, ov.SNARE, 5, 0x80)], 14, {})
        self.assertEqual(w.lines[:3], ['  tempo 64', '  rest len 0A', '  instrument 05'])
        self.assertEqual(w.lines[-1], '  note 05 len 04')


class ArrangeTests(unittest.TestCase):
    ORIGINAL = ['tempo 78', 'track L0', 'L0:', '  note 30 len 10', '  end']

    def setUp(self):
        self.score = synthetic_score()
        self.lines = ov.arrange(self.score, [], self.ORIGINAL)
        self.seq = assemble(self.lines)

    def test_every_track_starts_with_the_flag_branch_into_the_overture(self):
        self.assertEqual(self.lines[:8], ['tempo 78'] + [f'track LS{i}' for i in range(7)])
        self.assertEqual(self.lines[8:12], ['LS0:', '  if_flag 01 -> LT0', '  jump -> L0', 'LS1:'])
        self.assertEqual(self.lines[12:14], ['  if_flag 01 -> LT1', '  end'])

    def test_flag_zero_keeps_the_original_song(self):
        events = play(self.seq, 200, 0)
        self.assertEqual([n for _, n, _, _ in events[0] if isinstance(n, int)][:1], [0x30])
        self.assertEqual([e for e in events[1:] if e], [])

    def test_overture_plays_the_fc_notes_on_seven_tracks(self):
        report = ov.check_sequence(self.seq, self.score)
        notes = report['notes']['flag_01']
        # 펄스1 11음, 펄스2 2음(붙임은 합쳐짐)·2음, 현 선율은 행진부터 3음, 삼각파 1음 x2,
        # 타악은 한 틱에 하나: 팡파르 첫 타 8 + 96틱 음 둘의 굴림 26 x 2 + 끝 화음 둘 + 마지막 화음 굴림 7
        self.assertEqual(notes[:6], [11, 2, 2, 3, 1, 1])
        self.assertEqual(notes[6], 8 + 26 + 26 + 2 + 7)
        self.assertEqual(report['tracks'], 7)
        self.assertEqual(report['tempo'], 0x78)
        self.assertEqual(report['cycle_ticks'], ov.song_tick(4085 + ov.RING_TICKS))
        self.assertEqual(report['bytes'], len(self.seq))

    def test_flag_zero_notes_are_the_original_ones(self):
        report = ov.check_sequence(self.seq, self.score)
        self.assertEqual(report['notes']['flag_00'], [1, 0, 0, 0, 0, 0, 0])


class ReferenceTests(unittest.TestCase):
    def test_original_listing_renumbers_instruments_to_the_new_sample_order(self):
        seq = assemble(['tempo 78', 'track L0', 'L0:', '  instrument 00', '  note 30 len 10', '  instrument 05', '  end'])
        with mock.patch('dq5spc.sequences', lambda rom: {ov.SONG: (0, 0, 0)}), mock.patch('dq5spc.body', lambda rom, a, n: seq):
            lines = ov.original_listing(None)
        # 원래 악기 0 은 샘플 0A, 5 는 13 → 새 순서에서 6번과 5번
        self.assertEqual([ln for ln in lines if 'instrument' in ln], ['  instrument 06', '  instrument 05'])
        self.assertEqual(lines[0], 'tempo 78')

    def test_reference_snare_is_shifted_into_this_songs_ticks_and_cut_to_the_march(self):
        notes = [(1500, 0x10, 8, 0x90), (1000, 0x11, 8, 0x80), (8000, 0x12, 8, None), (2000, None, 8, 0x80)]
        with mock.patch('dq5spc.sequences', lambda rom: {ov.REF_SONG: (0, 0, 0)}), \
                mock.patch('dq5spc.body', lambda rom, a, n: b''), mock.patch.object(ov, 'track_notes', lambda seq, index: notes):
            self.assertEqual(ov.reference_snare(None), [(1512, 0x10, 0x90)])

    def test_cycle_covers_the_ring_time(self):
        self.assertEqual(ov.cycle_ticks({'end_tick': 100}), 2 * (100 + ov.RING_TICKS - 1))


class RenderAndMainTests(unittest.TestCase):
    def test_render_packs_the_run_and_asks_for_the_wav(self):
        calls = {}
        fake = types.SimpleNamespace(
            pack=lambda ram, dsp, regs, title, **kw: calls.update(pack=(ram, dsp, regs, title, kw)) or b'spc-bytes',
            regs=lambda path: ('regs', path.name),
            render=lambda spc, wav, seconds, fade: calls.update(render=(Path(spc).name, Path(wav).name, seconds, fade)))
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(sys.modules, {'dq5spcfile': fake}):
            run = Path(tmp)
            (run / 'spc.bin').write_bytes(b'ram')
            (run / 'dsp.bin').write_bytes(b'dsp')
            spc = ov.render(run, seconds=30)
            self.assertEqual(spc, run / 'overture.spc')
            self.assertEqual(spc.read_bytes(), b'spc-bytes')
        self.assertEqual(calls['pack'][:3], (b'ram', b'dsp', ('regs', 'regs.txt')))
        self.assertEqual(calls['pack'][4]['seconds'], 30)
        self.assertEqual(calls['render'], ('overture.spc', 'overture.wav', 30, 2))

    def run_main(self, *argv):
        out = io.StringIO()
        with mock.patch('sys.argv', ['dq4overture.py', *argv]), contextlib.redirect_stdout(out):
            ov.main()
        return out.getvalue()

    def test_text_prints_the_arranged_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            rom = Path(tmp) / 'dq5.sfc'
            rom.write_bytes(b'x')
            with mock.patch.object(ov, 'fc_score', lambda nes: {'s': nes}), mock.patch.object(ov, 'Rom', lambda raw: raw), \
                    mock.patch.object(ov, 'reference_snare', lambda r: ['snare']), \
                    mock.patch.object(ov, 'original_listing', lambda r: ['orig']), \
                    mock.patch.object(ov, 'arrange', lambda score, snare, orig: [str(score), *snare, *orig]):
                text = self.run_main('text', '--nes', 'a.nes', '--rom', str(rom))
        self.assertEqual(text.splitlines(), ["{'s': 'a.nes'}", 'snare', 'orig'])

    def test_render_and_tempo_map_print_their_results(self):
        with mock.patch.object(ov, 'render', lambda run: f'{run}/overture.spc'):
            self.assertEqual(self.run_main('render', 'work/run').strip(), 'work/run/overture.spc')
        with mock.patch.object(ov, 'tempo_map', lambda nes, fs: {'nes': nes, 'fs': fs}):
            self.assertEqual(json.loads(self.run_main('tempo-map', '--nes', 'n', '--fs', 'f')), {'nes': 'n', 'fs': 'f'})

    def test_build_prints_the_hash_and_sequence_report(self):
        seen = {}

        def fake_build(nes, rom, title, out):
            seen.update(nes=nes, rom=rom, title=title, out=out)
            return {'rom_sha1': 'abc', 'sequence': {'bytes': 7}, 'extra': 1}
        with mock.patch.object(ov, 'build', fake_build):
            text = self.run_main('build', '--nes', 'n', '--rom', 'r', '--title', 't', '--out', 'o')
        self.assertEqual(json.loads(text), {'rom_sha1': 'abc', 'sequence': {'bytes': 7}})
        self.assertEqual(seen, {'nes': 'n', 'rom': 'r', 'title': 't', 'out': 'o'})


class TempoMapTests(unittest.TestCase):
    """FC 악보를 그대로 늘여 친 가짜 NDS 녹음이면 DTW 로 잰 템포는 FC 템포를 늘인 배율로 나눈 값이다."""

    STRETCH = 1.25
    RATE = 8000

    def score(self):
        rng = np.random.default_rng(4)
        notes = [{'op': 'note', 'ch': 'pulse1', 'tick': t, 'len': 24, 'midi': 60 + int(rng.integers(12))}
                 for t in range(1, 3990, 24)]
        return {'tempo': 120, 'tempo_changes': [], 'timeline': notes, 'end_tick': 3990}

    def recording(self, score):
        tick = 150 / (ov.FC_FPS * score['tempo'])
        pcm = np.zeros(int((score['end_tick'] * tick * self.STRETCH + 1) * self.RATE))
        for e in score['timeline']:
            a = int(e['tick'] * tick * self.STRETCH * self.RATE)
            n = int(e['len'] * tick * self.STRETCH * self.RATE)
            t = np.arange(n) / self.RATE
            pcm[a:a + n] += np.sin(2 * np.pi * 440 * 2 ** ((e['midi'] - 69) / 12) * t)
        return np.stack([pcm, pcm], axis=1)

    def test_rows_measure_the_stretched_tempo(self):
        score = self.score()
        sdat = mock.Mock()
        sdat.count.return_value = 1
        sdat.strm_info.return_value = {'file': 0}
        fake = types.SimpleNamespace(load_sdat=lambda fs: sdat,
                                     strm_decode=lambda raw: (self.recording(score), self.RATE, None, None))
        with mock.patch.dict(sys.modules, {'ndssound': fake}), mock.patch.object(ov, 'fc_score', return_value=score):
            result = ov.tempo_map('fc.nes', 'fs')
        self.assertAlmostEqual(result['nds_seconds'] / result['fc_seconds'], self.STRETCH, delta=0.02)
        ticks = [t for t, _ in result['rows']]
        self.assertEqual(ticks, sorted(ticks))
        self.assertEqual(ticks[:3], [1, 97, 193])
        self.assertIn(775, ticks)
        want = 120 / self.STRETCH
        # 행진(775~3751)은 한 직선으로 맞추므로 정확하고, 짧은 구간은 DTW 걸음(0.05초) 만큼 흔들린다
        self.assertAlmostEqual(dict(result['rows'])[775], want, delta=1.5)
        self.assertAlmostEqual(float(np.median([t for _, t in result['rows']])), want, delta=3)


if __name__ == '__main__':
    unittest.main()
