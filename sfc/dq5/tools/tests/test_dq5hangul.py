"""한글 실험 롬(dq5hangul): 머리 체크섬, 롬 늘리기, 허프만 트리 만들기·부호화, 글자 비트, BG3 즉값 옮기기, 디코더 따라 풀기.
롬이 있으면 다시 부호화한 롬을 디코더 피연산자만으로 풀어 원래 메시지와 같은지, 시제품·창 접두·슬롯 표와 명령줄도 본다."""
import random
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import dq5hangul as H  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402
from dq5text import GLYPHS, message  # noqa: E402
from test_dq5spc import run_main  # noqa: E402

ROM = Path(__file__).resolve().parents[4] / 'rom' / 'dq5.sfc'


def stored_sums(d):
    return (int.from_bytes(d[H.HEADER + 0x1C:H.HEADER + 0x1E], 'little'),
            int.from_bytes(d[H.HEADER + 0x1E:H.HEADER + 0x20], 'little'))


class ChecksumTest(unittest.TestCase):
    def test_power_of_two_sum_and_complement(self):
        d = bytearray(0x10000)
        d[0x100] = 0x12
        out = H.checksum(d)
        comp, s = stored_sums(out)
        self.assertEqual(s, (0x12 + 0xFF * 2) & 0xFFFF)
        self.assertEqual(comp ^ s, 0xFFFF)
        self.assertEqual(sum(out) & 0xFFFF, s)

    def test_odd_size_mirrors_tail(self):
        d = bytearray(0x18000)
        d[0x10000] = 1
        _, s = stored_sums(H.checksum(d))
        self.assertEqual(s, (0x1FE + 1 * 2) & 0xFFFF)

    def test_expand_marks_new_banks(self):
        data = bytes(0x100000)
        for mb, size_byte in ((2, 0x0B), (3, 0x0C)):
            out = H.expand(data, mb)
            self.assertEqual(len(out), mb * 0x100000)
            self.assertEqual(out[H.HEADER + 0x17], size_byte)
            self.assertEqual(out[0x100000:0x100008], b'DQ5X' + (0x20).to_bytes(4, 'little'))
            self.assertEqual(out[0x108000:0x108004], b'DQ5X')
            self.assertEqual(out[0x100008:0x108000], bytes(0x7FF8))
            comp, s = stored_sums(out)
            self.assertEqual(comp ^ s, 0xFFFF)


class TreeTest(unittest.TestCase):
    def test_tree_codes_are_prefix_free_and_round_trip(self):
        rnd = random.Random(5)
        msgs = [[rnd.choice((1, 2, 2, 3, 3, 3, 0x1001)) for _ in range(rnd.randint(1, 9))] + [0x1001] for _ in range(20)]
        freq = {}
        for m in msgs:
            for c in m:
                freq[c] = freq.get(c, 0) + 1
        codes, nodes, root = H.build_tree(freq)
        self.assertEqual(set(codes), set(freq))
        self.assertEqual(len(nodes), len(freq) - 1)
        self.assertLessEqual(len(codes[3]), len(codes[1]))
        blob, starts = H.encode(codes, msgs)
        self.assertEqual(starts[0], 0)

        def bit(i):
            return blob[i >> 3] >> (i & 7) & 1
        for m, start in zip(msgs, starts):
            pos, got = start, []
            while len(got) < len(m):
                x = nodes[root]
                while True:
                    v = x[0] if bit(pos) else x[1]
                    pos += 1
                    if v & 0x8000:
                        got.append(v & 0x1FFF)
                        break
                    x = nodes[v]
            self.assertEqual(got, m)

    def test_glyph_bits_pack_without_padding(self):
        g = H.glyph_bits([('#..', '...'), ('..#', '..#')])
        bits = [g[i >> 3] >> (i & 7) & 1 for i in range(12)]
        self.assertEqual(bits, [0, 0, 1, 0, 0, 0, 1, 0, 0, 1, 0, 0])
        self.assertEqual(len(g), 2)
        self.assertEqual(H.cpu_to_bytes(0x308000), b'\x00\x80\x30')


class Bg3Test(unittest.TestCase):
    def test_moves_high_bytes(self):
        data = bytearray(0x200000)
        for off, old in H.BG3_MAP_IMMEDIATES:
            data[off] = old
        out, info = H.bg3move(data, 0x4C)
        for off, old in H.BG3_MAP_IMMEDIATES:
            self.assertEqual(out[off], old + 0x30)
        self.assertEqual(len(info), len(H.BG3_MAP_IMMEDIATES) + 1)
        self.assertIn('POKE="000725=4C;002109=4C"', info[-1])
        with self.assertRaises(AssertionError):
            H.bg3move(bytearray(0x200000))


class DecodeCheckTest(unittest.TestCase):
    def test_cyclic_tree_is_an_error(self):
        with self.assertRaises(ValueError):
            H.decode_check(bytes(0x200000), count=16)


@unittest.skipUnless(ROM.exists(), '롬이 없음(rom/dq5.sfc)')
class RomTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = ROM.read_bytes()
        cls.rom = Rom(cls.data)
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_retree_main_round_trips_every_message(self):
        out = self.dir / 'retree.sfc'
        code, text = run_main(H, [str(ROM), 'retree', '-o', str(out)])
        self.assertEqual(code, 0)
        n = H.MESSAGES - 1
        self.assertIn(f'메시지 {n}개 중 {n}개 같음, 129 = 1006 {GLYPHS:04X} {GLYPHS + 1:04X} 1001', text)
        d = out.read_bytes()
        self.assertEqual(len(d), 0x200000)
        self.assertEqual(d[lorom(H.DECODER):lorom(H.DECODER) + 5], bytes((0x22, 0x00, 0x80, 0x30, 0x60)))
        msgs, end = H.decode_check(d, with_end=True)
        self.assertEqual(msgs[0x12A], message(self.rom, 0x12A))
        self.assertGreater(end, 0x308000)
        comp, s = stored_sums(d)
        self.assertEqual(comp ^ s, 0xFFFF)

    def test_proto_in_place_command_window(self):
        out = self.dir / 'proto.sfc'
        code, text = run_main(H, [str(ROM), 'proto', '-o', str(out)])
        self.assertEqual(code, 0)
        self.assertIn('명령 창 레코드', text)
        self.assertIn('04:ED0C', text)
        self.assertIn('POKE="7E2001=', text)
        self.assertTrue(text.rstrip().endswith('7E2003=01"'))
        d = out.read_bytes()
        msgs = H.decode_check(d)
        self.assertEqual(msgs[0x129][0], 0x1006)
        self.assertEqual(msgs[0x129][-2:], [H.PERIOD, 0x1001])

    def test_proto_long_twobyte_moves_record(self):
        d, info, name = H.proto(self.data, long=True, twobyte=True)
        self.assertIn(f'{H.LONG_BANK:02X}:8000 → 7E:{H.LOW_WRAM_RECORD:04X}', info[-1])
        self.assertEqual(len(name), 2 * len(H.PROTO_NAME_2BYTE))
        self.assertEqual(name[::2], bytes([H.NAME_PREFIX]) * 4)
        o = lorom(H.WINDOW_POINTER_LOAD)
        self.assertEqual(d[o], 0x22)
        o = lorom(H.WINDOWS_TABLE + 2)
        self.assertEqual(d[o:o + 2], H.LOW_WRAM_RECORD.to_bytes(2, 'little'))
        o = lorom(H.NAME_CODE_CALL)
        self.assertEqual(d[o:o + 3], bytes((0x20, 0x11, 0x9E)))

    def test_wintest_bg3move_expand_and_slots(self):
        out = self.dir / 'w.sfc'
        code, text = run_main(H, [str(ROM), 'wintest', '-o', str(out)])
        self.assertIn(f'훅 {H.WIN_HOOK:06X}', text)
        d = out.read_bytes()
        o = lorom(H.COMMAND_WINDOW + 7)
        self.assertEqual(d[o:o + 2], bytes((H.WIN_PREFIX, 0)))
        self.assertEqual(d[lorom(H.WIN_DISPATCH)], 0x22)
        code, text = run_main(H, [str(ROM), 'bg3move', '--base', '4C', '-o', str(out)])
        self.assertEqual(text.count(' -> '), len(H.BG3_MAP_IMMEDIATES))
        code, text = run_main(H, [str(ROM), 'expand', '--size', '4', '-o', str(out)])
        self.assertEqual(text.strip(), '0x400000 바이트, 머리 크기 0C')
        self.assertEqual(out.stat().st_size, 0x400000)
        code, text = run_main(H, [str(ROM), 'expand'])
        self.assertEqual(code, 2)
        code, text = run_main(H, [str(ROM), 'slots'])
        rows = H.slot_table(self.data)
        self.assertEqual(len(text.splitlines()), len(rows))
        self.assertTrue(all(end > 0xBE for _, _, end in rows))


if __name__ == '__main__':
    unittest.main()
