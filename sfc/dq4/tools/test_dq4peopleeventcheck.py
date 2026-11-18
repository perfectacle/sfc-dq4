import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dq4peopleeventcheck as E  # noqa: E402


def obj_half(lines):
    """{줄: 15색 값} → CGRAM OBJ 절반(256바이트)."""
    out = bytearray(0x100)
    for n, c in lines.items():
        for k in range(1, 16):
            struct.pack_into('<H', out, n * 32 + k * 2, c)
    return bytes(out)


def record(frame, cg, bc=0x3D, bd=3, be=0x80, battle=0):
    return struct.pack('<I4B', frame, bc, bd, be, battle) + cg + bytes(0x220)


WANT = bytes(0x100) + obj_half({0: 0x1084, 2: 0x2108})


class RecordTests(unittest.TestCase):
    def test_records_splits_fixed_size_samples(self):
        blob = record(4, obj_half({0: 1})) + record(8, obj_half({0: 2})) + b'tail'
        recs = E.records(blob)
        self.assertEqual([r[0] for r in recs], [4, 8])
        self.assertEqual(recs[0][1:5], (0x3D, 3, 0x80, 0))
        self.assertEqual(E.row(recs[1][5], 0), [2] * 15)
        self.assertEqual(len(recs[0][6]), 0x220)


class KindTests(unittest.TestCase):
    def test_kind_tells_darker_brighter_and_other(self):
        want = [0x2108] * 15                           # 채널마다 8
        self.assertEqual(E.kind([0x1084] * 15, want), '어두움')
        self.assertEqual(E.kind([0x318C] * 15, want), '밝음')
        self.assertEqual(E.kind([0x2108] * 14 + [0x001F], want), '다름')

    def test_grey_flash_is_its_own_kind(self):
        # 여우 마을 촌장 장면의 번쩍임: 색마다 (R + 2G + B)/4 회색. 한 색이라도 어긋나면 다름
        want = [0x14C8, 0x001F, 0x7C00] + [0x2108] * 12
        grey = [0x18C6, 0x1CE7, 0x1CE7] + [0x2108] * 12
        self.assertEqual(E.kind(grey, want), '회색')
        self.assertEqual(E.kind(grey[:-1] + [0x18C6], want), '다름')


class LineReportTests(unittest.TestCase):
    def run_report(self, recs):
        return E.line_report(E.records(b''.join(recs)), lambda bc, bd: WANT)

    def test_same_colours_report_nothing(self):
        recs = [record(f, obj_half({0: 0x1084, 2: 0x2108, 1: 0x7FFF})) for f in range(4, 400, 4)]
        self.assertEqual(self.run_report(recs), {})

    def test_lines_the_rom_does_not_load_are_not_compared(self):
        # 줄 1 은 표에 없다(모두 0)
        recs = [record(f, obj_half({0: 0x1084, 2: 0x2108, 1: 0x1234})) for f in range(4, 400, 4)]
        self.assertEqual(self.run_report(recs), {})

    def test_changed_line_is_reported_after_the_map_settles(self):
        recs = [record(f, obj_half({0: 0x1084, 2: 0x001F})) for f in range(4, 200, 4)]
        got = self.run_report(recs)
        self.assertEqual(list(got), ['다름'])
        self.assertEqual(got['다름'][2][0], 4 + E.SETTLE)

    def test_field_samples_and_fresh_maps_are_skipped(self):
        field = [record(f, obj_half({0: 0, 2: 0}), be=0) for f in range(4, 400, 4)]
        self.assertEqual(self.run_report(field), {})
        moved = [record(4, obj_half({0: 0x1084, 2: 0x2108}))] + \
            [record(f, obj_half({0: 0, 2: 0}), bd=4) for f in range(8, 8 + E.SETTLE, 4)]
        self.assertEqual(self.run_report(moved), {})

    def test_battle_samples_are_skipped_and_the_line_is_checked_again_after(self):
        good, bad = obj_half({0: 0x1084, 2: 0x2108}), obj_half({0: 0x7C00, 2: 0x2108})
        recs = [record(f, good) for f in range(4, 200, 4)] + [record(f, bad, battle=1) for f in range(200, 600, 4)] + \
            [record(f, good) for f in range(600, 900, 4)]
        self.assertEqual(self.run_report(recs), {})
        kept = recs[:-75] + [record(f, bad) for f in range(600, 900, 4)]
        self.assertEqual(self.run_report(kept)['다름'][0][0], 600 + E.SETTLE)

    def test_map_number_set_before_going_indoors_settles_from_the_indoor_frame(self):
        old, new = obj_half({0: 0x7C00, 2: 0x2108}), obj_half({0: 0x1084, 2: 0x2108})
        recs = [record(f, old, be=0) for f in range(4, 124, 4)] + [record(f, old) for f in range(124, 136, 4)] + \
            [record(f, new) for f in range(136, 400, 4)]
        self.assertEqual(self.run_report(recs), {})

    def test_dark_frames_are_their_own_kind(self):
        recs = [record(f, obj_half({0: 0x0842, 2: 0x1084})) for f in range(4, 200, 4)]
        self.assertEqual(list(self.run_report(recs)), ['어두움'])


class SpanTests(unittest.TestCase):
    def test_spans_joins_neighbouring_samples(self):
        self.assertEqual(E.spans([4, 8, 12, 40, 100, 104], 4), '4~12, 40, 100~104')
        self.assertEqual(E.spans([], 4), '')


if __name__ == '__main__':
    unittest.main()
