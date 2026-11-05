"""드라이버 실행(Run: 틱·음 사건·템포·음량·되풀이 찾기)과 그 위에 선 명령(songs·sfx·notes·apu·compare·json·nsf…)을
작은 가짜 드라이버로 검사한다. 가짜 드라이버는 고정 뱅크의 소리 입구($F088·$EF59·$E685)와 Run 이 걸어 두는 후크 자리에
몇 바이트의 6502 만 둔 것이라 롬이 없어도 같은 경로를 탄다."""
import contextlib
import io
import os
import struct
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

import dq4sound as s
from test_dq4sound import PRG_SIZE, a4_period, fake_run, put, sound_prg, word

# 고정 뱅크(1F)의 소리 입구와 Run 후크 자리. 후크는 그 주소를 실행하기 직전에 불리므로 자리마다 RTS 한 바이트면 된다
HOOK_ADDRS = (0xE6CB, 0xEABB, 0xE96B, 0xEE61, 0xEDC7, 0xEE68)
PLAY_CODE = [0xA9, 0x7F, 0x8D, 0x00, 0x40,        # LDA #$7F; STA $4000
             0xA9, 0x03, 0x8D, 0x20, 0x06,        # LDA #3; STA $0620 (채널 0 남은 길이)
             0xA9, 0x96, 0x85, 0xBC,              # LDA #150; STA $BC (템포)
             0xA9, 0x10, 0x85, 0xA2,              # LDA #$10; STA $A2 (음 번호)
             0xA9, 0x04, 0x8D, 0x2B, 0x06,        # LDA #4; STA $062B (게이트)
             0xA9, 0x05, 0x8D, 0x3D, 0x06,        # LDA #5; STA $063D (엔벨로프)
             0xA9, 0x0F, 0x85, 0xB0,              # LDA #$0F; STA $B0 (주 음량)
             0xA9, 0xA3, 0x85, 0xB1,              # LDA #$A3; STA $B1 (채널 음량 A, 미세 3)
             0xA9, 0xFF, 0x85, 0xB5,              # LDA #$FF; STA $B5 (비브라토 없음)
             0xA9, 0x07, 0x85, 0x10,              # LDA #7; STA $10
             0x60]


PERIOD_LO = (a4_period() + 0x13) & 0xFF      # 음 10 은 주기 표 0x13 번(pitch_index)


def tick_code(countdown):
    """한 틱: 후크 자리를 차례로 부르고 APU 에 한 번 쓴다. countdown 이면 $0620 을 하나 줄여 세 틱 뒤 곡이 끝난다."""
    return ([0x20, 0xCB, 0xE6,                    # JSR $E6CB (틱)
             0x20, 0xBB, 0xEA,                    # JSR $EABB (음)
             0x20, 0x6B, 0xE9,                    # JSR $E96B (템포)
             0xA9, 0x3C, 0x20, 0x61, 0xEE,        # LDA #$3C; JSR $EE61 (음량)
             0x20, 0xC7, 0xED,                    # JSR $EDC7
             0xA2, 0x07, 0x20, 0x68, 0xEE,        # X=7 이면 기록하지 않는 자리
             0xA2, 0x08, 0x20, 0x68, 0xEE,        # X=8 이면 노이즈 음량으로 기록
             0xA9, PERIOD_LO, 0x8D, 0x02, 0x40]   # LDA #(음 10 의 주기 아래 바이트); STA $4002
            + ([0xCE, 0x20, 0x06] if countdown else [0xEA, 0xEA, 0xEA]) + [0x60])


SFX_PLAY = [0xA9, 0x02, 0x8D, 0x28, 0x06,                 # $0628 = 2
            0xA9, 0x04, 0x8D, 0x20, 0x06,                 # $0620 = 4 (음 길이)
            0xA9, 0x01, 0x85, 0x0F, 0x60]                 # $0F = 1: 틱이 효과음 쪽으로
SFX_TICK = [0x20, 0xCB, 0xE6,                             # 곡 틱 후크(효과음에서는 틱을 세지 않음)
            0x20, 0xBB, 0xEA,                             # 음 후크
            0xA9, 0x00, 0x8D, 0x0E, 0x40,                 # $400E = 0 (노이즈 주기)
            0xCE, 0x28, 0x06, 0x60]                       # $0628 하나 줄임


def driver_prg(countdown=True):
    prg = sound_prg()
    # 곡 2 는 비운다(뱅크 10 의 영 자료를 풀지 않도록)
    put(prg, 0x19, s.SONG_BANKS, [0x00, 0x00, 0x00])
    put(prg, 0x19, s.SONG_TABLE + 8 * 2, word(s.EMPTY) * 4)
    # 곡 1: 펄스 1(템포 + 엔벨로프 04 + 비브라토 02 + 음 하나 + 끝), 펄스 2(끝 음 하나). 효과음 81: 엔벨로프 04 + 끝 음
    put(prg, 0x19, 0x9000, [150, 0xE1, 0x04, 0xF0, 0x02, 75 + 0x12, 0x08, 75 + 0x12, 0x00])
    put(prg, 0x19, 0x9010, [0xE1, 0x06, 75 + 0x14, 0x00])
    put(prg, 0x19, s.ENV_TABLE + 6, word(0x9420))
    put(prg, 0x19, 0x9420, [0x7F, 0x05, 0xC1])       # 첫 바이트가 건너뜀이 아니면 떼기 없음
    put(prg, 0x19, 0xA000, [75 + 0x05, 0x00])
    put(prg, 0x19, 0xA300, [0xE1, 0x04, 75 + 0x11, 0x00])
    put(prg, 0x19, s.ENV_TABLE + 4, word(0x9400))
    put(prg, 0x19, 0x9400, [0xC2, 0x06, 0x7F, 0x03, 0x70, 0xC4, 0xB1, 0x01, 0xC6])
    put(prg, 0x19, s.VIB_TABLE + 2, word(0x9500))
    put(prg, 0x19, 0x9500, [0x04, 0x84, 0x0B, 0x01, 0x02])
    o = 0x1F * 0x4000
    prg[o + (s.NSF_FREE & 0x3FFF):o + (0xFF74 & 0x3FFF)] = b'\xff' * (0xFF74 - s.NSF_FREE)
    put(prg, 0x1F, s.INIT, [0x60])
    # A(곡 번호)가 80 이상이면 효과음 쪽 코드로 간다
    put(prg, 0x1F, s.PLAY, [0xC9, 0x80, 0xB0, len(PLAY_CODE)] + PLAY_CODE + SFX_PLAY)
    put(prg, 0x1F, s.TICK, [0xA5, 0x0F, 0xF0, len(SFX_TICK)] + SFX_TICK + tick_code(countdown))
    for a in HOOK_ADDRS:
        put(prg, 0x1F, a, [0x60])
    return prg


class SoundCpuTests(unittest.TestCase):
    def test_apu_writes_are_logged_and_bank_hook_switches_bank(self):
        cpu = s.SoundCPU(bytearray(PRG_SIZE))
        cpu.wr(0x4002, 0x1234)
        cpu.wr(0x4018, 1)
        cpu.wr(0x0010, 7)
        self.assertEqual(cpu.apu, [(0x4002, 0x34)])
        self.assertEqual(cpu.ram[0x10], 7)
        cpu.a = 0x33
        cpu.hooks[0xFF94](cpu)
        self.assertEqual(cpu.bank, 0x13)


class RunSongTests(unittest.TestCase):
    def setUp(self):
        self.prg = driver_prg()
        self.run = s.Run(self.prg, 1)

    def test_ends_when_length_counters_reach_zero(self):
        r = self.run
        self.assertTrue(r.ended())
        self.assertEqual((r.tick, r.ticks_at), (3, [1, 2, 3]))
        self.assertEqual(len(r.frames), 4)
        self.assertEqual(r.frames[0], [(0x4000, 0x7F)])
        self.assertEqual(r.frames[1:], [[(0x4002, PERIOD_LO)]] * 3)
        self.assertEqual((r.loop_start, r.loop_len), (None, None))

    def test_events_carry_driver_state(self):
        r = self.run
        # (틱, 채널, 음, 길이, 게이트, 엔벨로프, 이조, 고정 음량, 주소, 프레임)
        self.assertEqual(r.events, [(1, 0, 0x10, 3, 4, 5, 0, 0, 0, 1),
                                    (2, 0, 0x10, 2, 4, 5, 0, 0, 0, 2),
                                    (3, 0, 0x10, 1, 4, 5, 0, 0, 0, 3)])
        self.assertEqual(r.extra[0], {'ch_vol': 0xA, 'detune': 3, 'vibrato': None, 'master_vol': 0xF, 'bank': 0x19})

    def test_tempo_and_volumes(self):
        r = self.run
        self.assertEqual(r.tempos, [(0, 150), (1, 150), (2, 150), (3, 150)])
        # 후크마다 (틱, 채널, 값 아래 4비트, 곱하는 쪽): $EE61 은 $10, $EDC7 은 주 음량, X=8 인 $EE68 은 노이즈(4)
        self.assertEqual(r.vols[:3], [(1, 0, 0xC, 7), (1, 0, 0xC, 0xF), (1, 4, 0xC, 0xF)])
        self.assertEqual(len(r.vols), 9)

    def test_stop_false_runs_all_frames(self):
        r = s.Run(self.prg, 1, max_frames=5, stop=False)
        self.assertEqual(len(r.frames), 6)

    def test_same_state_twice_is_a_loop(self):
        r = s.Run(driver_prg(countdown=False), 1)
        self.assertEqual((r.loop_start, r.loop_len, r.tick), (1, 1, 2))
        self.assertFalse(r.ended())
        self.assertEqual(len(r.events), 2)

    def test_loop_false_keeps_running(self):
        r = s.Run(driver_prg(countdown=False), 1, max_frames=4, loop=False, stop=False)
        self.assertEqual((r.tick, len(r.frames)), (4, 5))
        self.assertEqual((r.loop_start, r.loop_len), (1, 1))


class RunSfxTests(unittest.TestCase):
    def test_sfx_ticks_every_frame_and_uses_tempo_150(self):
        r = s.Run(driver_prg(), 0x80)
        self.assertTrue(r.sfx)
        self.assertEqual(r.tempos, [(0, 150)])
        self.assertEqual(r.tick, 2)
        self.assertTrue(r.ended())
        self.assertEqual(len(r.events), 2)

    def test_sfx_repeating_state_is_a_loop(self):
        prg = driver_prg()
        put(prg, 0x1F, s.TICK, [0x20, 0xCB, 0xE6, 0x20, 0xBB, 0xEA, 0xEA, 0xEA, 0xEA, 0x60])
        r = s.Run(prg, 0x80)
        self.assertEqual((r.loop_start, r.loop_len, r.tick), (1, 1, 2))
        r = s.Run(prg, 0x80, max_frames=4, loop=False, stop=False)        # 되풀이를 찾은 뒤에도 틱은 계속 센다
        self.assertEqual((r.loop_start, r.loop_len, r.tick), (1, 1, 4))


def rom_file(d, prg):
    path = os.path.join(d, 'synthetic.nes')
    with open(path, 'wb') as f:
        f.write(b'NES\x1a' + bytes((32, 0, 0x10, 0)) + bytes(8) + bytes(prg))
    return path


class CliCase(unittest.TestCase):
    sfx = False
    countdown = True

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.rom = rom_file(cls.tmp.name, driver_prg())

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def cli(self, *args, rom=None):
        buf, code = io.StringIO(), 0
        with mock.patch.object(sys, 'argv', ['dq4sound.py', rom or self.rom, *args]), contextlib.redirect_stdout(buf):
            try:
                s.main()
            except SystemExit as e:
                code = e.code
        return code, buf.getvalue().splitlines()


class TableCommandTests(CliCase):
    def test_songs_table(self):
        code, lines = self.cli('songs')
        self.assertEqual(len(lines), s.NSONGS)
        self.assertEqual(lines[0], '00  (빈 곡)')
        self.assertEqual(lines[1], '01  뱅크 19  9000 9010 8335 8335  템포 150  음    3  끝 3틱  (0.1초)')
        self.assertTrue(all(ln.endswith('(빈 곡)') for ln in lines[2:]))

    def test_sfx_table(self):
        _, lines = self.cli('sfx')
        self.assertEqual(len(lines), s.NSFX)
        self.assertEqual(lines[0], '80  noise  19:$A000  음   2  2프레임')
        self.assertEqual(lines[1], '81  pulse2 19:$A300  음   2  2프레임')
        self.assertEqual(lines[2], '82  (빈 칸)')

    def test_notes_text(self):
        _, lines = self.cli('notes', '1')
        self.assertEqual(lines[0], '음 사건(드라이버 실행, 템포 150 에서 초당 60.10틱)')
        self.assertRegex(lines[1], r'^     1 pulse1   G#4 \(67\.\d\d\)\s+len=  3 gate=  4 n=10$')
        self.assertEqual([ln.split()[0] for ln in lines[1:4]], ['1', '2', '3'])
        self.assertEqual(lines[4:], ['템포 바뀜 1틱: 150', '템포 바뀜 2틱: 150', '템포 바뀜 3틱: 150', '끝: 3틱'])

    def test_notes_text_shows_loop(self):
        with tempfile.TemporaryDirectory() as d:
            rom = rom_file(d, driver_prg(countdown=False))
            _, lines = self.cli('notes', '1', rom=rom)
        self.assertEqual(lines[-1], '되풀이: 1틱부터 1틱')

    def test_apu_lists_only_frames_with_writes(self):
        _, lines = self.cli('apu', '1')
        lo = f'{PERIOD_LO:02X}'
        self.assertEqual(lines, ['    0 00=7F', f'    1 02={lo}', f'    2 02={lo}', f'    3 02={lo}'])

    def test_score_text(self):
        _, lines = self.cli('score', '1')
        self.assertEqual(lines[0], '곡 01: 뱅크 19, 채널 $9000 $9010 $8335 $8335')
        self.assertIn('  9000  96        tempo 150 (60.1 틱/초)', lines)
        self.assertIn('  9001  E1 04     envelope 04', lines)
        self.assertEqual(lines.count('  (빈 채널)'), 2)
        self.assertIn('  9010  E1 06     envelope 06', lines)

    def test_json_has_static_and_run_parts(self):
        import json
        _, lines = self.cli('json', '1')
        j = json.loads('\n'.join(lines))
        self.assertEqual((j['id'], j['kind'], j['tempo']), ('01', 'song', 150))
        self.assertEqual([e['tick'] for e in j['timeline']], [1, 2, 3])
        self.assertEqual(list(j['envelopes']), ['05'])
        self.assertEqual([i['op'] for i in j['channels'][0]['items']],
                         ['envelope', 'vibrato', 'note', 'note'])

    def test_envelopes_table(self):
        _, lines = self.cli('envelopes')
        self.assertEqual(lines[2], '| `04` | `19:9400` | 25% 50% | F×4 0 ↺ | @6: 1×2 ↺ | 01 81 |')
        self.assertEqual(lines[3], '| `06` | `19:9420` | 25% | F×6 ↺ | 없음 | 01 |')
        self.assertEqual(lines[-1], '| `02` | `19:9500` | 01 E1 w2 →0 |')

    def test_nsf_file_and_summary(self):
        out = os.path.join(self.tmp.name, 'dq4.nsf')
        _, lines = self.cli('nsf', out, '--start', '2')
        self.assertEqual(lines, [f'{out}: 트랙 3개, 곡 시작 자리 $FECE', '1=01 2=80 3=81'])
        with open(out, 'rb') as f:
            head = f.read(0x80)
        self.assertEqual((head[:5], head[6], head[7]), (b'NESM\x1a', 3, 2))


class MapTableTests(CliCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        prg = driver_prg()
        put(prg, 0x19, s.LEAD_SONGS, [0xFF, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27])
        put(prg, 0x19, s.FIELD_SONGS + 1, [0x31, 0x32, 0x33])
        put(prg, 0x19, s.CHAPTER_SONGS, [0x41, 0x42, 0x43, 0x44, 0x45, 0x46])
        put(prg, 0x19, s.TYPE_SONGS, [0x51, 0x52, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58])
        rows = [(0x05, 0xFF, 0x0C), (0xFE, 0, 0), (0x07, 0x03, 0x11), (0xFE, 0, 0), (0xFE, 0, 0), (0x02, 0x01, 0x04)]
        rows += [(0xFE, 0, 0)] * 8
        put(prg, 0x19, s.MAP_SONGS, [v for r in rows for v in r])
        put(prg, 0x19, 0x8056, [0x1C])
        cls.rom = rom_file(cls.tmp.name, prg)

    def test_map_song_table(self):
        _, lines = self.cli('maps')
        self.assertEqual(lines, [
            '맵 안($41 bit7)',
            '  $6285 bit3 이 켜져 있으면 어디서나 0E',
            '  05/**  → 0C  (3장($615A=2)이고 $6287 bit7 이 꺼져 있으면 맵 갈래 곡)',
            '  07/03  → 11',
            '  02/01  → 04  (5장($615A≥4)이고 플래그 $6295&02 가 켜져 있으면 04)',
            '  그 밖: 맵 갈래 $07BA & 7F 로 0 → 51, 1 → 52, 2 → 53, 3 → 54, 4 → 55, 5 → 56, 6 → 57, 7 → 58',
            '탈것($0515 ≠ 0): 1 → 09, 그 밖 → 13',
            '필드($65 ≠ 0): 필드 1 → 31, 필드 2 → 32, 필드 3 → 33',
            '필드 0: 1~4장 1장 → 41, 2장 → 42, 3장 → 43, 4장 → 44',
            '  5장, $6292 ≠ FF → 45',
            '  5장, $6292 = FF: 일행 첫 자리 인물(x3 2B 63 41)의 곡 クリフト 21, ミネア 22, マーニャ 23, ブライ 24, '
            'トルネコ 25, ライアン 26, アリーナ 27',
            '    첫 자리가 勇者면 걷는 일행 수(x3 62 63 41)가 1 일 때 1C 아니면 46'])


class CompareTests(CliCase):
    def log(self, lines):
        d = tempfile.mkdtemp(dir=self.tmp.name)
        with open(os.path.join(d, 'sound.txt'), 'w') as f:
            f.write('\n'.join(lines) + '\n')
        return d

    def song_log(self, lo=PERIOD_LO):
        return ['S 0 0 01', 'W 0 4000 7F', 'N 1', f'W 1 4002 {lo:02X}', 'N 2', f'W 2 4002 {lo:02X}',
                'N 3', f'W 3 4002 {lo:02X}']

    def test_read_log_groups_by_nmi_and_stops_at_other_sound(self):
        d = self.log(['', 'S 0 0 01', 'W 0 4000 7F', 'N 1', 'W 1 4002 10', 'S 1 0 01', 'N 2', 'W 2 4002 11',
                      'S 3 0 05', 'W 3 4002 12'])
        self.assertEqual(s.read_log(os.path.join(d, 'sound.txt')),
                         (1, [[(0x4000, 0x7F)], [(0x4002, 0x10)], [(0x4002, 0x11)]]))

    def test_matching_log_passes(self):
        code, lines = self.cli('compare', '1', self.log(self.song_log()))
        self.assertEqual(code, 0)
        self.assertEqual(lines, ['곡 01: 프레임 4개 중 다름 0개 (채널 pulse1,pulse2,triangle,noise)',
                                 '해독한 음 3개 중 시작 프레임의 실측 주기·노이즈 값이 맞은 것 3개'])

    def test_start_number_comes_from_the_log(self):
        code, lines = self.cli('compare', self.log(self.song_log()))
        self.assertEqual((code, lines[0][:5]), (0, '곡 01:'))

    def test_different_period_reports_frame_and_note(self):
        log = self.song_log()
        log[5] = 'W 2 4002 20'
        code, lines = self.cli('compare', '1', self.log(log))
        self.assertEqual(code, 1)
        self.assertEqual(lines[0], '곡 01: 프레임 4개 중 다름 1개 (채널 pulse1,pulse2,triangle,noise)')
        self.assertEqual(lines[1], '해독한 음 3개 중 시작 프레임의 실측 주기·노이즈 값이 맞은 것 2개')
        self.assertEqual(lines[2], f"  안 맞음 (2, 'pulse1', 'n=10', '주기 {PERIOD_LO + 0x100:03X}', '02=20')")
        self.assertEqual(lines[3:], ['처음 다른 프레임 2:', '  실측 02=20', f'  해독 02={PERIOD_LO:02X}'])

    def test_channel_filter_ignores_other_channels(self):
        log = self.song_log()
        log[5] = 'W 2 4002 20'
        code, lines = self.cli('compare', '1', self.log(log), '--channels', '1,2,3')
        self.assertEqual(lines[0], '곡 01: 프레임 4개 중 다름 0개 (채널 pulse2,triangle,noise)')

    def test_sfx_compares_only_its_channel_up_to_its_end(self):
        code, lines = self.cli('compare', '80', self.log(['S 0 0 80', 'N 1', 'W 1 400E 00', 'N 2', 'N 3']))
        self.assertEqual(code, 0)
        self.assertEqual(lines, ['효과음 80: 프레임 2개 중 다름 0개 (채널 noise)',
                                 '해독한 음 1개 중 시작 프레임의 실측 주기·노이즈 값이 맞은 것 1개'])

    def test_log_without_start_exits(self):
        with self.assertRaises(SystemExit) as cm:
            with contextlib.redirect_stdout(io.StringIO()):
                with mock.patch.object(sys, 'argv', ['dq4sound.py', self.rom, 'compare', '1', self.log(['N 1'])]):
                    s.main()
        self.assertEqual(cm.exception.code, 'sound.txt 에 시작(S)이 없음')


class CheckNotesTests(unittest.TestCase):
    def run_with(self, events, n=1, sfx=False):
        prg = sound_prg()
        extra = [{}] * len(events)
        return SimpleNamespace(prg=prg, n=n, sfx=sfx, events=events, extra=extra)

    def test_pulse_period_and_noise_value_must_be_in_start_frame(self):
        lo = (a4_period() + 0x13) & 0xFF
        hi = (a4_period() + 0x13) >> 8
        run = self.run_with([(0, 0, 0x10, 3, 4, 5, 0, 0, 0, 1),        # 펄스 1 음 10: 주기 = 표 0x13 번
                             (0, 3, 0x05, 3, 3, 0xFF, 0, 8, 0, 2),     # 노이즈 음 5: 주기 값 5
                             (0, 0, 0x4A, 3, 0, 5, 0, 0, 0, 1),         # 잇기는 견주지 않음
                             (0, 0, 0x10, 0, 4, 5, 0, 0, 0, 1),         # 길이 0 도 견주지 않음
                             (0, 2, 0x10, 3, 4, 5, 0, 0, 0, 1),         # 견주는 채널이 아님
                             (0, 0, 0x10, 3, 4, 5, 0, 0, 0, 9)])        # 기록보다 뒤 프레임
        groups = [[], [(0x4002, lo), (0x4003, hi)], [(0x400E, 0x85)]]
        ok, miss = s.check_notes(run, groups, [0, 3])
        self.assertEqual((ok, miss), (2, []))
        groups[1] = [(0x4002, lo ^ 1)]
        ok, miss = s.check_notes(run, groups, [0, 3])
        self.assertEqual(ok, 1)
        self.assertEqual(miss, [(1, 'pulse1', 'n=10', f'주기 {(hi << 8 | lo):03X}', f'02={lo ^ 1:02X}')])

    def test_high_bits_checked_when_written(self):
        lo = (a4_period() + 0x13) & 0xFF
        run = self.run_with([(0, 0, 0x10, 3, 4, 5, 0, 0, 0, 1)])
        ok, miss = s.check_notes(run, [[], [(0x4002, lo), (0x4003, 0x07)]], [0])
        self.assertEqual((ok, len(miss)), (0, 1))

    def test_sfx_events_use_the_sfx_channel(self):
        run = self.run_with([(0, 0, 0x03, 3, 0, 0, 0, 0, 0, 1)], n=0x80, sfx=True)     # 효과음 80 은 노이즈
        self.assertEqual(s.check_notes(run, [[], [(0x400E, 0x03)]], [3]), (1, []))
        self.assertEqual(s.check_notes(run, [[], [(0x400E, 0x04)]], [1]), (0, []))      # 채널 3 만 견주는 게 아니면 건너뜀


class FrameCounterPhaseTests(unittest.TestCase):
    def test_phase_is_middle_of_matching_range(self):
        # 프레임 길이가 37282 면 단계 자리는 변하지 않는다: 14914 단계는 14914~22371
        self.assertEqual(s.frame_counter_phase([14914, 14914, None], 37282), 14914 + 7458 // 2)

    def test_no_match_falls_back_to_first_logged_value(self):
        self.assertEqual(s.frame_counter_phase([1, 2], 37282), 1.0)
        self.assertEqual(s.frame_counter_phase([None], 37282), 18641.0)       # 아무 단서가 없으면 전부 맞아 가운데
        self.assertEqual(s.frame_counter_phase([None, 7], 37282), 0.0)


class MidiReadTests(unittest.TestCase):
    def smf(self, *tracks, ppq=24):
        out = b'MThd' + struct.pack('>IHHH', 6, 1, len(tracks), ppq)
        for body in tracks:
            out += b'MTrk' + struct.pack('>I', len(body)) + body
        return out

    def test_reads_note_ons_with_running_status_and_skips_the_rest(self):
        body = (b'\x00\xff\x03\x01x'                    # 메타: 곡 이름
                b'\x00\xf0\x02\x7d\xf7'                # 시스템 익스클루시브
                b'\x00\x90\x3c\x64'                    # t=0 C4 켬
                b'\x18\x40\x64'                         # 러닝 스테이터스: t=24 E4 켬
                b'\x18\x3c\x00'                         # 세기 0 = 끔
                b'\x00\xc0\x05'                         # 프로그램 바꿈(데이터 1바이트)
                b'\x00\x99\x26\x64'                    # 채널 10 은 뺀다
                b'\x00\xff\x2f\x00')
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'a.mid')
            with open(path, 'wb') as f:
                f.write(self.smf(body, b'\x00\xff\x2f\x00'))
            self.assertEqual(s.read_midi_notes(path), [[(0.0, 0x3C), (1.0, 0x40)], []])

    def test_intervals_keep_highest_note_per_sixteenth(self):
        notes = [(0.0, 60), (0.0, 64), (0.25, 62), (0.5, 55), (0.5, 50)]
        self.assertEqual(s.intervals(notes), [-2, -7])
        self.assertEqual(s.intervals([]), [])

    def test_melody_score_is_share_of_a_grams_found_in_b(self):
        a = [2, 2, -4, 7]
        self.assertEqual(s.melody_score(a, a, 3), 1.0)
        self.assertEqual(s.melody_score(a, [2, 2, -4, 1], 3), 0.5)
        self.assertEqual(s.melody_score(a, [1, 1, 1], 3), 0.0)
        self.assertEqual(s.melody_score([1], [1, 2, 3], 3), 0.0)


class NdsMatchTests(CliCase):
    def mid(self, d, name, keys):
        ev = [(i * 6, 3, bytes([0x90, k, 100])) for i, k in enumerate(keys)]
        ev += [(i * 6 + 5, 2, bytes([0x80, k, 0])) for i, k in enumerate(keys)]
        data = b'MThd' + struct.pack('>IHHH', 6, 1, 2, s.PPQ) + s.track([(0, 0, b'\xff\x03\x01c')]) + s.track(ev)
        with open(os.path.join(d, name), 'wb') as f:
            f.write(data)

    def test_best_match_ignores_transposition(self):
        melody = [(0, 1 + i, 6, m, 0x10, 0) for i, m in enumerate([60, 62, 64, 60, 67])]
        fake = [(c, t * 6, d, m, n, g) for c, t, d, m, n, g in melody]
        with tempfile.TemporaryDirectory() as d:
            self.mid(d, 'same.mid', [65, 67, 69, 65, 72])
            self.mid(d, 'other.mid', [60, 61, 62, 63, 64])
            with open(os.path.join(d, 'skip.txt'), 'w') as f:
                f.write('x')
            run = SimpleNamespace(loop_start=None, loop_len=None, tick=100)
            with mock.patch.object(s, 'notes', return_value=fake), mock.patch.object(s, 'Run', return_value=run):
                _, lines = self.cli('ndsmatch', d)
        self.assertEqual(lines, ['01  k=3  same 1.00 | other 0.00'])

    def test_few_notes_are_reported(self):
        with tempfile.TemporaryDirectory() as d:
            self.mid(d, 'a.mid', [60, 62, 64, 65])
            _, lines = self.cli('ndsmatch', d)
        self.assertEqual(lines, ['01  (음이 적음)'])


class AudioAndScoreCommandTests(CliCase):
    def test_wav_files_are_written_with_their_length_printed(self):
        import wave
        out = os.path.join(self.tmp.name, 'wav')
        _, lines = self.cli('wav', out, '01', '81')
        self.assertEqual([ln.split('  ')[0] for ln in lines], [os.path.join(out, '01.wav'), os.path.join(out, '81.wav')])
        for ln in lines:
            path, secs = ln.split('  ')[:2]
            with wave.open(path) as w:
                self.assertEqual(w.getframerate(), 44100)
                self.assertEqual(f'{w.getnframes() / 44100:.1f}초', secs)

    def test_scorecheck_reports_each_track(self):
        code, lines = self.cli('scorecheck', '01')
        self.assertEqual(code, 0)
        self.assertEqual(lines, ['01  음 pulse1 3 pulse2 0 triangle 0 noise 0  길이 3틱  같음'])

    def test_scorecheck_without_ids_walks_every_nsf_track(self):
        code, lines = self.cli('scorecheck')
        self.assertEqual(code, 0)
        self.assertEqual([ln[:2] for ln in lines], ['01', '80', '81'])
        self.assertTrue(lines[1].startswith('80  음 noise 2'))

    def test_export_writes_every_track_and_index(self):
        import json
        out = os.path.join(self.tmp.name, 'export')
        code, lines = self.cli('export', out, '--no-svg', '--wav')
        self.assertEqual(code, 0)
        self.assertEqual(lines[-1], out)
        self.assertEqual(lines[0], f'{os.path.join(out, "songs", "01")} 5')
        with open(os.path.join(out, 'songs', 'index.json')) as f:
            songs = json.load(f)
        self.assertEqual([(e['id'], e['nsf_track'], e['notes'], e['ticks']) for e in songs], [('01', 1, 3, 3)])
        self.assertEqual(songs[0]['channels'], ['19:9000', '19:9010', '19:8335', '19:8335'])
        self.assertEqual(songs[0]['files'], ['01.mid', '01.txt', '01.json', '01.musicxml', '01.wav'])
        with open(os.path.join(out, 'sfx', 'index.json')) as f:
            sfx = json.load(f)
        self.assertEqual([(e['id'], e['nsf_track'], e['channels']) for e in sfx],
                         [('80', 2, ['19:A000 noise']), ('81', 3, ['19:A300 pulse2'])])
        with open(os.path.join(out, 'songs', '01.mid'), 'rb') as f:
            self.assertEqual(f.read(4), b'MThd')
        with open(os.path.join(out, 'dq4.nsf'), 'rb') as f:
            self.assertEqual(f.read(5), b'NESM\x1a')

    def test_export_with_scores_writes_svg_pages(self):
        out = os.path.join(self.tmp.name, 'export-svg')
        code, lines = self.cli('export', out)
        self.assertEqual(code, 0)
        names = os.listdir(os.path.join(out, 'songs'))
        self.assertTrue(any(n.startswith('01-score-') and n.endswith('.svg') for n in names))

    def test_export_stops_when_score_and_midi_differ(self):
        out = os.path.join(self.tmp.name, 'export-bad')
        with mock.patch.object(s, 'score_check', return_value=['a', 'b']):
            code, _ = self.cli('export', out, '--no-svg')
        self.assertEqual(code, '01 악보가 MIDI 와 다름: a; b')

    def test_export_flac_uses_external_encoder(self):
        out = os.path.join(self.tmp.name, 'export-flac')
        calls = []

        def fake_flac(cmd, check):
            calls.append(cmd)
            with open(cmd[-1 - 1], 'wb') as f:      # -o 다음 인자가 출력 파일
                f.write(b'fLaC')
        import subprocess
        with mock.patch.object(subprocess, 'run', side_effect=fake_flac):
            code, lines = self.cli('export', out, '--no-svg', '--flac')
        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[0][:4], ['flac', '-s', '-8', '-f'])
        self.assertFalse(os.path.exists(os.path.join(out, 'songs', '01.wav')))     # --wav 가 없으면 중간 wav 는 지움


class ScoreMismatchTests(unittest.TestCase):
    def setUp(self):
        self.prg = sound_prg()
        self.run = fake_run(self.prg)

    def test_sfx_score_has_only_its_channel(self):
        run = fake_run(self.prg, n=0x81)
        parts = s.score_data(run)[0]
        self.assertEqual([p[0] for p in parts], ['pulse2'])
        mid = s.midi_bytes(run, 'x')
        chunks, pos = [], 14
        while pos < len(mid):
            n = struct.unpack('>I', mid[pos + 4:pos + 8])[0]
            chunks.append(mid[pos + 8:pos + 8 + n])
            pos += 8 + n
        self.assertEqual(chunks[1], b'\x00\xff\x03\x06pulse1\x00\xff\x2f\x00')     # 효과음 채널이 아닌 트랙은 이름뿐
        self.assertIn(b'\x91', chunks[2])

    def test_midi_marks_loop_points(self):
        self.run.loop_start, self.run.loop_len = 2, 10
        mid = s.midi_bytes(self.run, 'loop')
        # 지휘 트랙: 틱 0 템포, 2 loopStart, 10 템포 바뀜, 12(= 2 + 10) loopEnd 라 사이 간격은 2·8·2
        self.assertIn(b'\x02\xff\x06\x09loopStart', mid)
        self.assertIn(b'\x02\xff\x06\x07loopEnd', mid)
        self.assertLess(mid.index(b'loopStart'), mid.index(b'loopEnd'))
        _, _, _, _, loop = s.score_data(self.run)
        self.assertEqual(loop, (1, 11))

    def test_pitch_bends_stop_at_end(self):
        ns = s.notes(self.run)
        self.assertEqual(s.pitch_bends(self.run, ns, 0, 4), [])        # 첫 쓰기 프레임이 틱 4 라 끝과 같으면 멈춤
        self.assertEqual(len(s.pitch_bends(self.run, ns, 0, 5)), 1)

    def test_pitch_bends_skip_frames_before_any_note(self):
        ns = s.notes(self.run)
        later = [(c, t + 6, d, m, n, g) for c, t, d, m, n, g in ns]
        # 음이 틱 6 에야 시작하므로 틱 4 의 주기 쓰기에는 기준 음이 없어 건너뛰고, 틱 8 에서야 휨이 나온다
        self.assertEqual([e[0] for e in s.pitch_bends(self.run, later, 0, 24)], [8])

    def test_score_check_reports_note_count_and_short_length(self):
        run = self.run
        run.events = [ev for ev in run.events if ev[0] >= 1] + [(1, 1, 0x20, 30, 30, 5, 0, 0xFF, 0, 1)]
        run.extra = run.extra[:len(run.events)]
        run.tick = 40
        xml = s.song_musicxml(run, 'test')
        self.assertEqual(s.score_check(run, xml), [])
        run.events = run.events[:-1]
        run.extra = run.extra[:len(run.events)]
        self.assertEqual(s.score_check(run, xml), ['pulse2: 음 1개 / MIDI 0개'])
        run.tick = 5000
        # 악보는 마디 하나(96틱)뿐인데 틱이 5000 이라 파트마다 길이가 모자란다
        self.assertEqual(s.score_check(run, xml),
                         ['pulse1: 길이 96 < 4999', 'pulse2: 음 1개 / MIDI 0개', 'pulse2: 길이 96 < 4999',
                          'triangle: 길이 96 < 4999', 'noise: 길이 96 < 4999'])

    def test_steps_text_cuts_after_limit(self):
        steps = [(0x70 + i % 16, 1) for i in range(45)]
        self.assertEqual(s.steps_text(steps).count(' '), 40)
        self.assertTrue(s.steps_text(steps).endswith(' …'))
        self.assertEqual(s.steps_text(steps[:40]), s.steps_text(steps)[:-2])

    def test_vibrato_end_kind(self):
        prg = sound_prg()
        put(prg, 0x19, s.VIB_TABLE + 2, word(0x9500))
        put(prg, 0x19, 0x9500, [0x04, 0x06])
        self.assertEqual(s.vibrato_text(prg, 2), '01 끝')


class StreamVariantTests(unittest.TestCase):
    def setUp(self):
        self.prg = sound_prg()

    def decode(self, code, addr=0x9800):
        put(self.prg, 0x19, addr, code)
        return s.decode_stream(self.prg, 0x19, addr)

    def test_short_loop_tempo_and_argument_commands(self):
        items = self.decode([0xF9, 0xFE, 0xFF, 0x96, 0xFB, 0x02, 0xEF, 75 + 0x10, 0x00])
        self.assertEqual([it[2] for it in items],
                         ['loop x2 → $9800', 'tempo 150 (60.1 틱/초)', 'transpose 02', 'fade-out', 'note 10 len=0 (끝)'])
        self.assertEqual(items[0][3], {'op': 'loop', 'count': 2, 'target': 0x9800})

    def test_jump_to_a_stream_that_ends_stops_reading(self):
        put(self.prg, 0x19, 0x9810, [75 + 0x11, 0x00])
        items = self.decode([0xFE, 0x10, 0x98, 75 + 0x12, 0x00])
        self.assertEqual([(a, it['op']) for a, _, _, it in items], [(0x9800, 'jump'), (0x9810, 'note')])

    def test_flow_back_into_a_returned_subroutine_stops(self):
        items = self.decode([0xFE, 0x03, 0x98, 0xFD])
        self.assertEqual([(a, it['op']) for a, _, _, it in items], [(0x9800, 'jump'), (0x9803, 'return')])


class ScoreTextSfxTests(unittest.TestCase):
    def test_sfx_header_and_stream(self):
        prg = sound_prg()
        put(prg, 0x19, 0xA300, [75 + 0x11, 0x04, 75 + 0x11, 0x00])
        lines = s.score_text(prg, 0x81).splitlines()
        self.assertEqual(lines[0], '효과음 81: pulse2, 19:$A300')
        self.assertEqual(lines[2], '[sfx] 19:$A300')
        self.assertEqual(lines[3:], ['  A300  5C 04     note 11 len=4', '  A302  5C 00     note 11 len=0 (끝)'])


class LoadTests(unittest.TestCase):
    def test_load_drops_ines_header_and_caps_size(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'a.nes')
            with open(path, 'wb') as f:
                f.write(bytes(range(16)) + b'\xaa' * 0x80000 + b'\xbb' * 10)
            data = s.load(path)
        self.assertEqual((len(data), data[0], data[-1]), (0x80000, 0xAA, 0xAA))


class CallsTests(CliCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        prg = driver_prg()
        put(prg, 0x03, 0x8100, [0xA9, 0x05, 0x20, 0x1F, 0xC0])      # LDA #5; JSR $C01F
        put(prg, 0x03, 0x8200, [0xA9, 0x07, 0x4C, 0x1F, 0xC0])
        put(prg, 0x03, 0x8300, [0xA9, 0x09, 0x20, 0x25, 0xC0])
        put(prg, 0x03, 0x8400, [0xA9, 0x0A, 0x00, 0x03, 0x9F])      # LDA #A; BRK 03 9F
        put(prg, 0x03, 0x8500, [0xA9, 0x0B, 0x00, 0x05, 0x9F])
        put(prg, 0x04, 0x9000, [0x00, 0x0C, 0xFB])                  # BRK 0C FB
        cls.prg = prg
        cls.rom = rom_file(cls.tmp.name, prg)

    def test_code_calls_find_each_entry_pattern(self):
        got = sorted((b, a, how, n) for b, a, how, n in s.code_calls(self.prg) if (b, n) in {(3, 5), (3, 7), (3, 9), (3, 10), (3, 11), (4, 12)})
        self.assertEqual(got, [(3, 0x8100, 'JSR $C01F', 5), (3, 0x8200, 'JMP $C01F', 7), (3, 0x8300, 'JSR $C025', 9),
                               (3, 0x8400, 'BRK 03 9F', 10), (3, 0x8500, 'BRK 05 9F', 11), (4, 0x9000, 'BRK n FB', 12)])

    def test_calls_table_merges_code_npc_and_message_sources(self):
        with mock.patch.object(s, 'npc_calls', return_value=[(5, 0x9008, 0x05)]), \
                mock.patch.object(s, 'message_calls', return_value=[(0x0123, 0x05), (0x0200, 0x0C), (0x0201, 0x7F)]):
            _, lines = self.cli('calls')
        by = {ln[:2]: ln for ln in lines}
        self.assertEqual(by['05'], '05  코드 2곳 03:8100(JSR $C01F) 05:9008(인물 블록 30) / 대사 1개 0123')
        self.assertEqual(by['0C'], '0C  코드 1곳 04:9000 / 대사 1개 0200')
        self.assertEqual(by['7F'], '7F  대사 1개 0201')              # 효과음 범위 밖이어도 대사가 부르면 보인다
        self.assertEqual(by['07'], '07  코드 1곳 03:8200(JMP $C01F)')

    def test_calls_cut_long_lists(self):
        many = [(0x0300 + i, 0x05) for i in range(8)]
        with mock.patch.object(s, 'npc_calls', return_value=[]), mock.patch.object(s, 'message_calls', return_value=many):
            _, lines = self.cli('calls')
        row = next(ln for ln in lines if ln.startswith('05'))
        self.assertTrue(row.endswith('대사 8개 0300 0301 0302 0303 0304 0305 …'))

    def test_codes_beyond_sound_table_without_messages_are_hidden(self):
        prg = bytearray(self.prg)
        put(prg, 0x03, 0x8600, [0x00, 0xF0, 0xFB])
        with tempfile.TemporaryDirectory() as d, mock.patch.object(s, 'npc_calls', return_value=[]), \
                mock.patch.object(s, 'message_calls', return_value=[]):
            _, lines = self.cli('calls', rom=rom_file(d, prg))
        self.assertFalse(any(ln.startswith('F0') for ln in lines))

    def test_npc_calls_find_sound_commands_in_blocks(self):
        import test_dq4npcblock as nbt
        prg = nbt.world_prg()
        nbt.put(prg, 5, 0x9008, [0x30, 0x0B])
        self.assertIn((5, 0x9008, 0x0B), s.npc_calls(prg))


class MessageCallsTests(unittest.TestCase):
    def test_sound_calls_in_message_text(self):
        import test_dq4text as tt
        prg = tt.base_prg()
        chars = [prg[tt.t.off(*tt.t.CHARS) + i] for i in range(128)]
        chars[0x2E] = 0xEE
        chars[0x2F] = 0x05
        tt.put(prg, *tt.t.CHARS, chars)
        msgs = [[tt.CODE_A, 0x2E, 0x2F, tt.t.END], [0x2E, tt.CODE_B, tt.t.END]]
        tt.put(prg, *tt.t.BANK_BOUNDS, [0, 0, 0, 0, 0, 0xFF])
        text = tt.pack([c for m in msgs for c in m])
        tt.put(prg, tt.t.WORD_BANK, 0xA500, text)
        dict_at = 0xA500 + len(text)
        tt.put(prg, tt.t.WORD_BANK, dict_at, [0x10, tt.t.WORD_END])
        tt.put(prg, *tt.t.WORDS, tt.word(dict_at) * 2)
        tt.put(prg, *tt.t.BLOCKS, b''.join(tt.word(b) for b in [0xA500] + [dict_at] * (tt.t.block_count() - 1)))
        self.assertEqual(s.message_calls(tt.ines(prg)), [(0, 5), (1, 3)])


class ApuCheckTests(CliCase):
    QUIET = '0 0 0 0 0 0 0 0 0 3 0 0'          # 8 값 + 삼각파 단계 + 노이즈 주기−1 + 음량 + 짧은꼴

    def dir_with(self, lines):
        d = tempfile.mkdtemp(dir=self.tmp.name)
        with open(os.path.join(d, 'apu.txt'), 'w') as f:
            f.write('\n'.join(lines) + '\n')
        return d

    def test_silent_log_has_nothing_to_compare(self):
        d = self.dir_with([f'F 1 {self.QUIET}', f'F 2 {self.QUIET}'])
        code, lines = self.cli('apucheck', d)
        self.assertEqual(code, 0)
        self.assertEqual(lines, [f'{d}: 프레임 1개 중 다름 0개', '합계: 프레임 1개 중 다름 0개'])

    def test_channel_state_is_compared_once_its_registers_were_written(self):
        # 펄스 1 의 $4000·$4003 을 쓰면 비교가 시작된다. 기록의 타이머 값 999 는 합성기가 만든 값(0)과 다르다
        d = self.dir_with(['W 1 4000 BF', 'W 1 4003 08', f'F 1 {self.QUIET} 100', f'F 2 999 {self.QUIET[2:]} 100'])
        code, lines = self.cli('apucheck', d)
        self.assertEqual(code, 1)
        self.assertTrue(lines[0].startswith(f'{d}: 프레임 1개 중 다름 1개 / pulse1 주기 1(처음 2)'), lines[0])
        self.assertEqual(lines[-1], '합계: 프레임 1개 중 다름 1개')

    def test_frames_without_a_following_state_are_skipped(self):
        d = self.dir_with([f'F 1 {self.QUIET}', f'F 3 {self.QUIET}'])
        _, lines = self.cli('apucheck', d)
        self.assertEqual(lines[-1], '합계: 프레임 1개 중 다름 0개')

    def test_totals_add_up_over_directories(self):
        a = self.dir_with([f'F 1 {self.QUIET}', f'F 2 {self.QUIET}', f'F 3 {self.QUIET}'])
        b = self.dir_with([f'F 5 {self.QUIET}', f'F 6 {self.QUIET}'])
        code, lines = self.cli('apucheck', a, b)
        self.assertEqual(lines[-1], '합계: 프레임 3개 중 다름 0개')


if __name__ == '__main__':
    unittest.main()
