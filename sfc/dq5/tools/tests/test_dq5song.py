"""곡 시퀀스(dq5song): 글 ↔ 바이트 왕복, 흐름 따라 풀기와 문제 찾기, 틱 재생, KON 기록과 견주기, 제자리·뱅크 70 패치, 명령줄."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import dq5song as S  # noqa: E402
import dq5spc as P  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402
from test_dq5spc import run_main, sound_rom  # noqa: E402

SONG = """tempo 20
track LA
track LB
LA:
  instrument 03
  transpose 02
  note 30 len 10
  call -> LS
  noise_on
  note 12
  noise_off
  gate_preset 0D
  skip B6
  rest
  tie
  if_flag 05 -> LE   # 곡 변수가 05 면 note 40 을 건너뜀
  note 40
LE:
  end
LS:
  note 20 len 08
  ret
LB:
  follow
  note 25
  follow_off
LL:
  note 26 len 04
  loop2 -> LL
  loop2b -> LL
  loop 03 -> LL
  if_loop2 -> LL
  jump -> LB
"""
BYTES = bytes.fromhex('20 02 06 00 1f 00 f0 03 fa 02 80 10 f8 0d 00 e3 12 e4 a0 b6 00 4f e0 01 00 05 40 ff 70 08 f9'
                      ' f2 25 f3 76 04 dc fb ff f4 f8 ff f5 03 f4 ff db f1 ff ea eb ff')


class AssembleTest(unittest.TestCase):
    def test_assemble_bytes(self):
        self.assertEqual(S.assemble(SONG.splitlines()), BYTES)

    def test_listing_round_trip_with_original_labels(self):
        lines = S.listing(BYTES)
        self.assertEqual(lines[:3], ['tempo 20', 'track L0006', 'track L001F'])
        self.assertIn('  call -> L001C', lines)
        self.assertIn('  if_flag 05 -> L001B', lines)
        self.assertIn('  loop 03 -> L0022', lines)
        self.assertEqual(S.assemble(lines), BYTES)

    def test_unreached_bytes_become_db(self):
        seq = bytes([0x20, 1, 5, 0, 0x99, 0xFF])
        lines = S.listing(seq)
        self.assertEqual(lines, ['tempo 20', 'track L0005', '  db 99', 'L0005:', '  end'])
        self.assertEqual(S.assemble(lines), seq)

    def test_step_kinds(self):
        self.assertEqual(S.step(b'\x00', 0), (1, 'rest', None, 'go'))
        self.assertEqual(S.step(b'\x4f', 0), (1, 'tie', None, 'go'))
        self.assertEqual(S.step(b'\x50\x10', 0), (2, 'rest len 10', None, 'go'))
        self.assertEqual(S.step(b'\x9f\x10', 0), (2, 'tie len 10', None, 'go'))
        self.assertEqual(S.step(b'\xb5', 0), (1, 'gate_preset 00', None, 'go'))
        self.assertEqual(S.step(b'\xea\xfd\xff', 0), (3, 'jump -> 0000', 0, 'jump'))
        self.assertEqual(S.step(b'\xf9', 0), (1, 'ret', None, 'ret'))
        self.assertEqual(S.step(b'\xde\x01\x02\x03', 0), (4, 'adsr_release 01 02 03', None, 'go'))


class WalkTest(unittest.TestCase):
    def test_decode_lists_each_track(self):
        lines, problems = S.decode(BYTES)
        self.assertEqual(problems, [])
        self.assertEqual(lines[0], 'tempo 20 tracks 2')
        self.assertIn('track 1 @ 001F', lines)
        self.assertIn('  001C note 20 len 08', lines)

    def test_problems(self):
        _, p = S.walk(bytes([0x20, 1, 4, 0, 0xEA, 0x00, 0x10]), 4)
        self.assertEqual(p, ['0004 jump -> 1007: target out of sequence'])
        _, p = S.walk(bytes([0x20, 1, 4, 0, 0xF0]), 4)
        self.assertEqual(p, ['0004 instrument: runs past end'])
        _, p = S.walk(bytes([0x20, 1, 4, 0, 0xF8, 0xFD, 0xFF]), 4)
        self.assertEqual(p, ['0004 call nested deeper than 3'])
        seen, p = S.walk(bytes([0x20, 1, 4, 0, 0xF9]), 4)
        self.assertEqual(p, ['pc 0005 out of sequence'])
        self.assertEqual(seen, {4: (5, 'ret')})


class PlayTest(unittest.TestCase):
    def test_track_events(self):
        a, b = S.play(BYTES, 200, flag=5)
        self.assertEqual(a, [(0, 0x32, 3, False), (16, 0x22, 3, False), (24, 0x14, 3, True), (32, None, 3, False),
                             (40, 'tie', 3, False)])
        # follow 인 트랙은 앞 트랙의 길이(10)를 가져온다. 이어서 길이 04 의 되풀이.
        self.assertEqual(b[:3], [(0, 0x25, None, False), (16, 0x26, None, False), (20, 0x26, None, False)])
        self.assertEqual(len(b), 47)

    def test_if_flag_not_taken_plays_through(self):
        a, _ = S.play(BYTES, 200, flag=0)
        self.assertEqual(a[-1], (48, 0x42, 3, False))

    def test_track_running_off_the_end_stops(self):
        (ev,) = S.play(bytes([0x20, 1, 4, 0, 0x30]), 50)
        self.assertEqual(ev, [(0, 0x30, None, False)])


def kon_log(frames, pitches, voice=0, noise=None):
    lines = []
    for f, p in zip(frames, pitches):
        lines += [f'{f} {voice << 4 | 2:02X}={p & 0xFF:02X}', f'{f} {voice << 4 | 3:02X}={p >> 8:02X}']
        if noise is not None:
            lines.append(f'{f} 6C={0x20 | noise:02X}')
        lines.append(f'{f} 4C={1 << voice:02X}')
    return '\n'.join(lines) + '\n'


class CompareTest(unittest.TestCase):
    SEQ = S.assemble(['tempo 20', 'track LA', 'LA:', '  instrument 01', '  note 30 len 10', '  note 32', '  note 34',
                      '  end'])

    def compare(self, text, **kw):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'dspw.txt'
            path.write_text(text)
            kon = S.read_kon(str(path))
            return kon, S.compare(self.SEQ, kon, **kw)

    def test_matching_log(self):
        kon, res = self.compare(kon_log([90, 100, 132, 164], [0x800, 0x1000, 0x11F6, 0x1429]), start=100)
        self.assertEqual(kon[0][0], (90, 0x800, 0))
        self.assertEqual(res, [(0, 2.0, 0.0, 0, 3)])

    def test_pitch_and_timing_mismatch(self):
        _, res = self.compare(kon_log([100, 132, 170], [0x1000, 0x1000, 0x1429]), start=0)
        (i, fpt, err, bad, m), = res
        self.assertEqual((i, fpt, bad, m), (0, 2.1875, 2, 3))
        self.assertAlmostEqual(err, 3.0)

    def test_noise_notes_compare_flg(self):
        seq = S.assemble(['tempo 20', 'track LA', 'LA:', '  noise_on', '  note 03 len 10', '  note 05', '  end'])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'dspw.txt'
            path.write_text(kon_log([0, 16], [0x1000, 0x1000], noise=3))
            res = S.compare(seq, S.read_kon(str(path)), 0)
        self.assertEqual(res, [(0, 1.0, 0.0, 1, 2)])

    def test_too_few_notes_or_voice_past_seven(self):
        _, res = self.compare(kon_log([100], [0x1000], voice=7), start=0, voice=7)
        self.assertEqual(res, [(0, None, None, None, 1)])
        _, res = self.compare(kon_log([100], [0x1000]), start=0)
        self.assertEqual(res, [(0, None, None, None, 1)])
        res = S.compare(BYTES, [[] for _ in range(8)], 0, voice=7)
        self.assertEqual(res[1], (1, None, None, None, 0))


class PatchTest(unittest.TestCase):
    def setUp(self):
        self.rom = Rom(sound_rom(seqs=[BYTES, BYTES]))

    def test_in_place_pads_with_ff(self):
        doc = S.patch(self.rom, 1, b'\x20\x01\x04\x00\xff')
        w, = doc['writes']
        o = lorom(P.sequences(self.rom)[1][1]) + 2
        self.assertEqual(w['at'], f'0x{o:06X}')
        self.assertEqual(bytes.fromhex(w['hex']), b'\x20\x01\x04\x00' + b'\xff' * (len(BYTES) - 4))
        self.assertEqual(bytes.fromhex(w['orig']), BYTES)
        with self.assertRaises(SystemExit):
            S.patch(self.rom, 1, BYTES + b'\xff')

    def test_reloc(self):
        sets = {1: bytes([0, 0])}
        doc = S.patch_reloc(self.rom, {2: b'\x01\x02\x03'}, {5: b'\x02\x00\xaa\xbb'}, sets)
        self.assertEqual(doc['rom_size'], 4)
        hook, code, seq_t, smp_t, data, song_set = doc['writes']
        self.assertEqual(bytes.fromhex(hook['hex']), bytes([0x22, 0x10, 0x80, 0x70, 0x60]))
        self.assertEqual(bytes.fromhex(code['hex']), S.reloc_code())
        seq_t, smp_t = bytes.fromhex(seq_t['hex']), bytes.fromhex(smp_t['hex'])
        self.assertEqual(seq_t[6:9], bytes([0x00, 0x86, 0x70]))
        self.assertEqual(smp_t[15:18], bytes([0x05, 0x86, 0x70]))
        self.assertEqual(bytes.fromhex(data['hex']), b'\x03\x00\x01\x02\x03\x02\x00\xaa\xbb')
        self.assertEqual(song_set['at'], '2B:E681')
        with self.assertRaises(SystemExit):
            S.patch_reloc(self.rom, sets={1: b'\x00'})
        with self.assertRaises(SystemExit):
            S.patch_reloc(self.rom, {0: bytes(0xA000)})

    def test_reloc_code_and_short_branches(self):
        code = S.reloc_code()
        self.assertEqual(code[:3], bytes.fromhex('48 DA 5A'))
        self.assertEqual(code.count(bytes.fromhex('7A FA 68 6B')), 1)
        self.assertEqual(S._asm([b'\xea', ('b', 0x80, 'x'), b'\xea', ('label', 'x')]), bytes([0xEA, 0x80, 0x01, 0xEA]))


class MainTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.path = self.dir / 'r.sfc'
        self.path.write_bytes(sound_rom(seqs=[BYTES, b'\x20']))

    def tearDown(self):
        self.tmp.cleanup()

    def test_listing_and_flow(self):
        _, out = run_main(S, [str(self.path), '00'])
        self.assertEqual(out.splitlines(), S.listing(BYTES))
        _, out = run_main(S, [str(self.path), '00', '--flow'])
        self.assertIn('track 1 @ 001F', out)

    def test_check(self):
        code, out = run_main(S, [str(self.path), '--check'])
        self.assertEqual(code, 0)
        self.assertIn('00: tempo 20 tracks 2 bytes   52 unread   0', out)
        self.assertIn('01: empty (1 bytes)', out)
        self.assertIn('71 sequences (decoded and re-encoded), 0 problems', out)

    def test_check_reports_problems(self):
        self.path.write_bytes(sound_rom(seqs=[bytes([0x20, 1, 4, 0, 0xF8, 0xFD, 0xFF])]))
        code, out = run_main(S, [str(self.path), '--check'])
        self.assertEqual(code, 1)
        self.assertIn("PROBLEMS ['track 0: 0004 call nested deeper than 3']", out)
        self.assertIn('1 problems', out)

    def test_encode_in_place_and_reloc(self):
        src = self.dir / 'new.txt'
        src.write_text('tempo 10\ntrack LA\nLA:\n  note 30 len 08\n  end\n', encoding='utf-8')
        out = self.dir / 'p.json'
        _, text = run_main(S, [str(self.path), '00', '--encode', str(src), '-o', str(out)])
        self.assertIn('sequence 00: 7 bytes into 52', text)
        doc = json.loads(out.read_text())
        self.assertEqual(doc['name'], 'song-00')
        smp = self.dir / 's.bin'
        smp.write_bytes(b'\x02\x00\x11\x22')
        _, text = run_main(S, [str(self.path), '00', '--encode', str(src), '--reloc', '--sample', f'26={smp}',
                               '--set', '0=0000', '-o', str(out)])
        doc = json.loads(out.read_text())
        self.assertEqual(doc['name'], 'dq5song-reloc')
        self.assertEqual(doc['writes'][-1]['note'], '곡 묶음 00')
        self.assertTrue(doc['writes'][4]['hex'].endswith('02 00 11 22'))

    def test_kon(self):
        kon = self.dir / 'dspw.txt'
        kon.write_text(kon_log([10, 42], [0x1000, 0x1000]))
        _, out = run_main(S, [str(self.path), '00', '--kon', str(kon), '--count', '2'])
        self.assertIn('track 0: 2 notes, 2.0000 frame/tick, max frame error 0.0, pitch mismatches 1', out)
        self.assertIn('track 1: 0 notes compared', out)
        txt = self.dir / 'seq.txt'
        txt.write_text('tempo 10\ntrack LA\nLA:\n  note 30 len 10\n  note 30\n  end\n', encoding='utf-8')
        _, out = run_main(S, [str(self.path), '00', '--kon', str(kon), '--seqfile', str(txt)])
        self.assertEqual(out.strip(), 'track 0: 2 notes, 2.0000 frame/tick, max frame error 0.0, pitch mismatches 0')


if __name__ == '__main__':
    unittest.main()
