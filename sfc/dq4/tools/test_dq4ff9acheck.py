"""롬 없이: FF9A(슬라임 레이스) NMI 검사의 받침 읽기와 판정."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dq4ff9acheck as fc  # noqa: E402


def rom_with(writes):
    data = bytearray(0x400000)
    for addr, raw in writes:
        o = fc.lorom(addr)
        data[o:o + len(raw)] = raw
    return bytes(data)


STUBS = [(0x00FF9A, bytes.fromhex('5C 90 D6 60')), (0x00FF9E, bytes.fromhex('22 6C D6 60')),
         (0x60D690, bytes.fromhex('22 6C D6 60 22 AC C8 11 5C 8F 88 00'))]


class EntryTest(unittest.TestCase):
    def test_reads_the_stubs(self):
        self.assertEqual(fc.entry_of(rom_with(STUBS)), (0x60D690, 0x60D66C, 0x60D66C))

    def test_ff9a_calling_elsewhere_shows(self):
        writes = STUBS[:2] + [(0x60D690, bytes.fromhex('22 8F D6 60'))]
        self.assertEqual(fc.entry_of(rom_with(writes))[2], 0x60D68F)

    def test_an_unpatched_rom_stops(self):
        with self.assertRaises(SystemExit):
            fc.entry_of(rom_with([(0x00FF9A, bytes.fromhex('22 AC C8 11 5C 8F 88 00'))]))


class JudgeTest(unittest.TestCase):
    GOOD = [(0xFF9A, 0, True)] * fc.INJECT

    def test_passes(self):
        self.assertEqual(fc.judge({0xFF9A: (1923, 1923)}, self.GOOD, False), (True, []))

    def test_fails_without_ff9a(self):
        self.assertFalse(fc.judge({0xFF9E: (10, 10)}, [], False)[0])

    def test_fails_when_an_nmi_skips_the_entry(self):
        self.assertFalse(fc.judge({0xFF9A: (1923, 1922)}, self.GOOD, False)[0])

    def test_fails_when_an_item_stays(self):
        self.assertFalse(fc.judge({0xFF9A: (5, 5)}, [(0xFF9A, 1, False)] * fc.INJECT, False)[0])
        self.assertFalse(fc.judge({0xFF9A: (5, 5)}, self.GOOD[:1], False)[0])

    def test_original_needs_only_the_task(self):
        self.assertEqual(fc.judge({0xFF9A: (3, None)}, [], True), (True, []))

    def test_parses_the_probe_files(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            (folder / 'nmi.txt').write_text('FF9E 846 entry 846\nFF9A 1923 entry 1923\n')
            (folder / 'inject.txt').write_text('878 nmi 847 task FF9A count 0 vram same\n'
                                               '909 nmi 878 task FF9A count 1 vram differs\n')
            nmi, inject = fc.parse(folder)
        self.assertEqual(nmi, {0xFF9E: (846, 846), 0xFF9A: (1923, 1923)})
        self.assertEqual(inject, [(0xFF9A, 0, True), (0xFF9A, 1, False)])


if __name__ == '__main__':
    unittest.main()
