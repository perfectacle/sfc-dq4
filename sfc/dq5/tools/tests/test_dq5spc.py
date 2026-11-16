"""사운드 자료 묶음(dq5spc): 길이로 이어 걷는 샘플·시퀀스 묶음, 곡 묶음, 상주 목록, SPC RAM 덤프 견주기. 합성 롬으로 본다."""
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dq5spc as P  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402


def sound_rom(samples=(), seqs=(), sets=(), size=0x200000):
    """샘플 자료([길이 2][자료] 째)·시퀀스 바이트·곡 묶음([(둘째 바이트, [샘플])])을 제자리에 둔 합성 롬 바이트.
    모자란 칸은 빈 샘플(자료 7바이트)·빈 시퀀스·빈 곡 묶음으로 채운다."""
    d = bytearray(size)
    o = lorom(P.SAMPLES)
    for i in range(P.SAMPLE_COUNT):
        raw = samples[i] if i < len(samples) else bytes([7, 0]) + bytes(7)
        d[o:o + len(raw)] = raw
        o += len(raw)
    o = lorom(P.SEQUENCES)
    for i in range(P.SEQUENCE_COUNT):
        s = seqs[i] if i < len(seqs) else b''
        d[o:o + 2 + len(s)] = bytes([len(s) & 0xFF, len(s) >> 8]) + s
        o += 2 + len(s)
    o = lorom(P.SONG_SETS)
    for i in range(P.SEQUENCE_COUNT):
        x, smp = sets[i] if i < len(sets) else (0, [])
        rec = bytes([len(smp), x, *smp])
        d[o:o + len(rec)] = rec
        o += len(rec)
    d[lorom(P.RESIDENT_SAMPLES):lorom(P.RESIDENT_SAMPLES) + 3] = b'\x00\x01\xff'
    d[lorom(P.RESIDENT_SEQUENCES):lorom(P.RESIDENT_SEQUENCES) + 2] = b'\x02\xff'
    return d


def sample(loop_block, brr, adsr=(0xFF, 0xE0), gain=0xB8, pitch=0x0F9A):
    body = bytes([loop_block * 9 & 0xFF, loop_block * 9 >> 8, *adsr, gain, pitch >> 8, pitch & 0xFF]) + brr
    return bytes([len(body) & 0xFF, len(body) >> 8]) + body


def run_main(module, argv):
    out = io.StringIO()
    code = None
    with mock.patch.object(sys, 'argv', [module.__name__ + '.py', *argv]), redirect_stdout(out), \
            redirect_stderr(io.StringIO()):
        try:
            code = module.main()
        except SystemExit as e:
            code = e.code
    return code, out.getvalue()


SMP = [sample(1, bytes([0x10 + k, k]) + bytes(7) + bytes([0x03]) + bytes(8)) for k in range(3)]
SEQ = [bytes([0x20, 1, 4, 0, 0xFF]), bytes([0x30, 1, 4, 0, 0x30, 0xFF])]


class ChainTest(unittest.TestCase):
    def setUp(self):
        self.rom = Rom(sound_rom(SMP, SEQ, [(0x11, [0, 2]), (0x22, [1])]))

    def test_chain_walks_length_prefixed_records_across_banks(self):
        s = P.samples(self.rom)
        self.assertEqual(len(s), P.SAMPLE_COUNT)
        self.assertEqual(s[0], (0, P.SAMPLES, len(SMP[0]) - 2))
        self.assertEqual(s[1][1], P.SAMPLES + len(SMP[0]))
        self.assertEqual(bytes(P.body(self.rom, s[2][1], s[2][2])), SMP[2][2:])
        q = P.sequences(self.rom)
        self.assertEqual([n for _, _, n in q[:3]], [5, 6, 0])
        self.assertEqual(bytes(P.body(self.rom, q[1][1], q[1][2])), SEQ[1])

    def test_cpu_address_rolls_into_next_bank(self):
        self.assertEqual(P._cpu(lorom(0x2BFFFF)), 0x2BFFFF)
        self.assertEqual(P._cpu(lorom(0x2BFFFF) + 1), 0x2C8000)

    def test_song_sets_and_resident_lists(self):
        sets = P.song_sets(self.rom)
        self.assertEqual(sets[0], (0, 0x11, [0, 2]))
        self.assertEqual(sets[1], (1, 0x22, [1]))
        self.assertEqual(sets[2], (2, 0, []))
        self.assertEqual(P.ff_list(self.rom, P.RESIDENT_SAMPLES), [0, 1])
        self.assertEqual(P.ff_list(self.rom, P.RESIDENT_SEQUENCES), [2])


def spc_with(rom, seq_ids, smp_ids):
    """롬 자료를 드라이버 칸 표대로 올린 64KB SPC RAM."""
    spc = bytearray(0x10000)
    spc[P.SPC_SEQUENCE_INDEX:P.SPC_SEQUENCE_INDEX + 0x100] = b'\xff' * 0x100
    spc[P.SPC_SAMPLE_INDEX:P.SPC_SAMPLE_INDEX + P.SAMPLE_COUNT] = b'\xff' * P.SAMPLE_COUNT
    at = 0x2000
    seqs = P.sequences(rom)
    for slot, sid in enumerate(seq_ids):
        _, a, n = seqs[sid]
        spc[P.SPC_SEQUENCE_INDEX + sid] = slot
        spc[P.SPC_SEQUENCE_SLOTS + slot * 6:P.SPC_SEQUENCE_SLOTS + slot * 6 + 6] = \
            bytes([0xFF, at & 0xFF, at >> 8, n & 0xFF, n >> 8, 0])
        spc[at:at + n] = P.body(rom, a, n)
        at += n
    smps = P.samples(rom)
    for slot, sid in enumerate(smp_ids):
        _, a, n = smps[sid]
        b = P.body(rom, a, n)
        brr = n - 7
        spc[P.SPC_SAMPLE_INDEX + sid] = slot
        spc[P.SPC_SAMPLE_SLOTS + slot * 8:P.SPC_SAMPLE_SLOTS + slot * 8 + 8] = bytes([brr & 0xFF, brr >> 8, *b[2:7], 0])
        loop = at + (b[0] | b[1] << 8)
        spc[P.SPC_DIR + slot * 4:P.SPC_DIR + slot * 4 + 4] = bytes([at & 0xFF, at >> 8, loop & 0xFF, loop >> 8])
        spc[at:at + brr] = b[7:]
        at += brr
    return spc


class CheckTest(unittest.TestCase):
    def setUp(self):
        self.data = sound_rom(SMP, SEQ)
        self.rom = Rom(self.data)

    def test_loaded_data_matches_rom(self):
        spc = spc_with(self.rom, [1, 0], [2, 0])
        res = P.check(self.rom, spc)
        self.assertEqual(sorted(res), sorted([('seq', 0, 1, True), ('seq', 1, 0, True),
                                              ('sample', 0, 1, True), ('sample', 2, 0, True)]))

    def test_changed_brr_byte_or_adsr_is_a_diff(self):
        spc = spc_with(self.rom, [1], [2])
        start = spc[P.SPC_DIR] | spc[P.SPC_DIR + 1] << 8
        spc[start + 3] ^= 1
        self.assertEqual(P.check(self.rom, spc), [('seq', 1, 0, True), ('sample', 2, 0, False)])
        spc = spc_with(self.rom, [], [1])
        spc[P.SPC_SAMPLE_SLOTS + 2] ^= 0x10
        self.assertEqual(P.check(self.rom, spc), [('sample', 1, 0, False)])

    def test_sequence_ids_past_rom_count_are_ignored(self):
        spc = spc_with(self.rom, [], [])
        spc[P.SPC_SEQUENCE_INDEX + P.SEQUENCE_COUNT] = 0
        self.assertEqual(P.check(self.rom, spc), [])

    def test_main_table_and_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'r.sfc'
            path.write_bytes(self.data)
            code, out = run_main(P, [str(path)])
            self.assertIsNone(code)
            self.assertIn(f'  00 {P.SAMPLES:06X} len {len(SMP[0]) - 2:04X} loop 0009 adsr FF E0 gain B8 pitch 0F9A', out)
            self.assertIn('resident samples (8B): 00 01', out)
            self.assertIn('resident sequences (93): 02', out)
            self.assertEqual(sum(1 for ln in out.splitlines() if ' set ' in ln), P.SEQUENCE_COUNT)
            dump = Path(tmp) / 'spc.bin'
            dump.write_bytes(spc_with(self.rom, [0], [1]))
            code, out = run_main(P, [str(path), '--check', str(dump)])
            self.assertEqual(code, 0)
            self.assertIn('seq    00 slot 00 ok', out)
            self.assertIn('2 loaded, 0 differ', out)
            bad = spc_with(self.rom, [0], [1])
            bad[0x2000] ^= 0xFF
            dump.write_bytes(bad)
            code, out = run_main(P, [str(path), '--check', str(dump)])
            self.assertEqual(code, 1)
            self.assertIn('seq    00 slot 00 DIFF', out)


if __name__ == '__main__':
    unittest.main()
