"""보행 모드 메시지·창 문자열(dq5text): 비트 읽기의 뱅크 넘김, 글자·제어 코드 글, 이름 문자열 부호, 창 레코드 머리·항목.
롬이 있으면 허프만 풀기, 폰트, 실험 패치, 명령줄도 본다."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import dq5text as T  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402
from test_dq5spc import run_main  # noqa: E402

ROM = Path(__file__).resolve().parents[4] / 'rom' / 'dq5.sfc'


def put(d, addr, raw):
    d[lorom(addr):lorom(addr) + len(raw)] = raw


def string_rom():
    """이름 문자열 부호 표(보통 바이트 b → 코드 0x100+b), 탁점 키 표, 이름 표 하나를 둔 합성 롬."""
    d = bytearray(0x200000)
    put(d, T.STRING_CODES, b''.join((0x100 + b).to_bytes(2, 'little') for b in range(0x80)))
    keys = bytearray(0x30)
    keys[2] = 0x41
    keys[0x28 + 1] = 0x42
    put(d, T.MARK_KEYS, keys)
    put(d, T.MARK_CODES + 2 * 2, (0x3A1).to_bytes(2, 'little'))
    put(d, T.MARK_CODES + 0x29 * 2, (0x3A2).to_bytes(2, 'little'))
    put(d, T.STRING_TABLES + 5 * 3, (0x219800).to_bytes(3, 'little'))
    put(d, 0x219800, bytes([2, 0x10, 0x11, 3, 0x84, 0x41, 0x01]))
    return d


class BitReaderTest(unittest.TestCase):
    def test_lsb_first_and_bank_wrap(self):
        d = bytearray(0x200000)
        put(d, 0x24FFFF, b'\x80')
        put(d, 0x258000, b'\x03')
        br = T.BitReader(Rom(d), 0x24FFFF << 3 | 7)
        self.assertEqual([br.read() for _ in range(3)], [1, 1, 1])
        self.assertEqual(br.addr, 0x258000)
        self.assertEqual(br.bit, 2)


class TextTest(unittest.TestCase):
    def test_controls_and_unknown_codes(self):
        self.assertEqual(T.text([0x000, 0x1000, 0x1001, 0x1006, 0x3D4]), '　\n{end}{1006}' + T.CHARS[0x3D4])
        self.assertEqual(len(T.CHARS), T.GLYPHS)

    def test_string_codes_marks_and_space(self):
        rom = Rom(string_rom())
        self.assertEqual(T.string_codes(rom, bytes([0x10, 0x84, 0x41, 0x83, 0x42, 0x01])), [0x110, 0x3A1, 0x3A2, 0])
        self.assertEqual(T.string(rom, 5, 0), bytes([0x10, 0x11]))
        self.assertEqual(T.string(rom, 5, 1), bytes([0x84, 0x41, 0x01]))

    def test_controls_table(self):
        d = bytearray(0x200000)
        put(d, 0x248204, b'\x49\x83\x03\x83')
        got = T.controls(Rom(d))
        self.assertEqual(len(got), 0x1E + 0x19)
        self.assertEqual(got[:2], [(0x1000, 0x248349), (0x1001, 0x248303)])
        self.assertEqual(got[0x1E], (0x1100, 0x240000))
        self.assertTrue(all(c in T.CONTROL_MEANING for c, _ in got))


class WindowTest(unittest.TestCase):
    def test_header_without_title(self):
        h = T.window_header(bytes([0x42, 0x91, 0xDC, 0xAB, 0x00, 0x04]))
        self.assertEqual(h, {'x': 2, 'x_flags': 0x40, 'y': 0x11, 'w': 0x1C, 'h': 0x0B, 'color_by_state': 3,
                             'tall_rows': True, 'bit5': True, 'title': None, 'rows': 4})

    def test_header_with_title_and_skip(self):
        h = T.window_header(bytes([0x16, 0x73, 0xC6, 0x49, 0xC1, 0x12, 0, 0, 0, 0x83]))
        self.assertEqual((h['title'], h['title_x'], h['title_skip'], h['rows'], h['per_member']), (0x12, 1, 3, 3, True))

    def test_items_and_titles(self):
        d = string_rom()
        put(d, T.WINDOW_TITLES, bytes([0x10, 0xFF, 0x11, 0x12, 0xFF]))
        rom = Rom(d)
        rec = bytes([2, 4, 12, 0xA9, 0, 2, 0xFE, 0x10, 0x84, 0x41, 0xFF, 0xFE, 0x11, 0x01, 0xFF, 0x80, 0xFE])
        self.assertEqual(T.window_items(rom, rec), '|' + T.text([0x110, 0x3A1]) + '\n|' + T.text([0x111, 0]) + '\n')
        self.assertEqual(T.window_items(rom, bytes([1, 2, 3])), '')
        self.assertEqual(T.window_title(rom, 1), bytes([0x11, 0x12]))
        self.assertEqual(T.window_title(rom, 0), bytes([0x10]))

    def test_window_record_runs_to_next_start(self):
        d = bytearray(0x200000)
        put(d, T.WINDOWS, b'\x4c\xeb\x50\xeb')
        put(d, 0x04EB4C, b'\x01\x02\x03\x04\x05\x06')
        a, data = T.window(Rom(d), 0)
        self.assertEqual((a, data), (0x04EB4C, b'\x01\x02\x03\x04'))
        a, data = T.window(Rom(d), 1)
        self.assertEqual((a, len(data)), (0x04EB50, 0x40))


@unittest.skipUnless(ROM.exists(), '롬이 없음(rom/dq5.sfc)')
class RomTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom = Rom(ROM.read_bytes())

    def test_messages_end_with_end_codes(self):
        for m in (0, 0x15, 0x129, 0xC7F):
            codes = T.message(self.rom, m)
            self.assertIn(codes[-1], T.ENDS)
            self.assertFalse(any(c in T.ENDS for c in codes[:-1]))
        self.assertEqual(len(T.message(self.rom, 0x129, 40)), 40)

    def test_font_and_glyphs(self):
        groups = T.font_groups(self.rom)
        self.assertEqual(sum(c for _, c, _, _, _ in groups), T.GLYPHS)
        self.assertEqual(T.glyph(self.rom, 0), (8, 1, [[0] * 8]))
        w, h, rows = T.glyph(self.rom, 0x2D1, groups)
        self.assertEqual((len(rows), len(rows[0])), (h, w))
        self.assertTrue(any(any(r) for r in rows))
        self.assertEqual(T.glyph(self.rom, 0x2D1), (w, h, rows))

    def test_leaf_and_hangul_test_patch(self):
        leaf = T.leaf_address(self.rom, 0x399)
        self.assertEqual(self.rom.u16(leaf), 0x8000 | 0x399)
        self.assertIsNone(T.leaf_address(self.rom, 0x1FFF))
        patch = T.hangul_test_patch(self.rom)
        self.assertEqual(len(patch), 2 + len(T.FONT_TABLE_OPERANDS) + 1)
        self.assertEqual(patch[0][0], lorom(T.FREE_GLYPH))
        self.assertEqual(len(patch[0][1]), (11 * 13 + 7) // 8)
        self.assertEqual(len(patch[1][1]), (len(T.font_groups(self.rom)) + 1) * 5)
        self.assertEqual(patch[-1], (lorom(leaf), (0x8000 | T.GLYPHS).to_bytes(2, 'little')))

    def test_main_modes(self):
        _, out = run_main(T, [str(ROM), '129'])
        self.assertEqual(out.strip(), T.text(T.message(self.rom, 0x129)))
        _, out = run_main(T, [str(ROM), '129', '--codes', '--n', '4'])
        self.assertEqual(out.split(), [f'{c:04X}' for c in T.message(self.rom, 0x129, 4)])
        _, out = run_main(T, [str(ROM), '--controls'])
        self.assertEqual(len(out.splitlines()), 0x1E + 0x19)
        _, out = run_main(T, [str(ROM), '--hangul-test'])
        self.assertEqual(out.count('='), len(T.hangul_test_patch(self.rom)))
        _, out = run_main(T, [str(ROM), '--window', '1'])
        lines = out.splitlines()
        self.assertTrue(lines[0].startswith('window 01 at 04:ED0C'))
        self.assertIn('title=None rows=4', lines[1])
        self.assertEqual(out.count('|'), 8)
        _, out = run_main(T, [str(ROM), '--window', '9'])
        self.assertIn('title:', out)
        _, out = run_main(T, [str(ROM), '--window', '12'])
        self.assertNotIn('rows=', out)


if __name__ == '__main__':
    unittest.main()
