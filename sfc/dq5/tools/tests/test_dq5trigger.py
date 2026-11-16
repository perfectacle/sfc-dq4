"""실내 영역 이동(dq5trigger): 색인을 따라 레코드 자리를 정하고, 12바이트 레코드를 풀어 설명한다. 합성 롬으로 본다."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import dq5trigger as T  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402
from test_dq5spc import run_main  # noqa: E402

REC_A = bytes([1, 2, 4, 5, 0x00, 0x40, 0x03, 0x01, 10, 11, 0, 0x01])
REC_B = bytes([0, 0, 2, 1, 0x01, 0x00, 0x80, 0x00, 0, 0, 0, 0x00])
REC_C = bytes([3, 3, 4, 4, 0x02, 0x00, 0x05, 0x02, 7, 8, 1, 0x02])


def trigger_rom():
    d = bytearray(0x200000)
    idx = bytes([0x01, 0x02, 2, 0x05, 0x00, 1, 0x80])
    d[lorom(T.INDEX):lorom(T.INDEX) + len(idx)] = idx
    recs = REC_A + REC_B + REC_C
    d[lorom(T.RECORDS):lorom(T.RECORDS) + len(recs)] = recs
    return d


class TriggerTest(unittest.TestCase):
    def setUp(self):
        self.rom = Rom(trigger_rom())

    def test_index_accumulates_record_addresses(self):
        self.assertEqual(T.index(self.rom), [(1, 2, 2, T.RECORDS), (5, 0, 1, T.RECORDS + 2 * T.RECORD_SIZE)])

    def test_record_fields(self):
        t = T.record(self.rom, T.RECORDS)
        self.assertEqual((t['rect'], t['source_layer'], t['flags'], t['bc'], t['bd'], t['x'], t['y'], t['span'],
                          t['destination_layer']), ((1, 2, 4, 5), 0, 0x40, 3, 1, 10, 11, 0, 1))
        self.assertEqual(bytes(t['raw']), REC_A)

    def test_describe(self):
        self.assertEqual(T.describe(T.record(self.rom, T.RECORDS)),
                         '(1,2)~(3,4) 에 층 00로 들어서면 → 03/01 (10,11), 도착 층 01')
        self.assertEqual(T.describe(T.record(self.rom, T.RECORDS + T.RECORD_SIZE)),
                         '(0,0)~(1,0) 에 층 01로 들어서면 → 필드로, 도착 층 00 (이동 효과음)')

    def test_main(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'r.sfc'
            path.write_bytes(self.rom.d)
            code, out = run_main(T, [str(path)])
            self.assertEqual(code, 0)
            self.assertEqual(out.strip(), f'maps 2, records 3, records end {T.RECORDS + 36:06X} (index at {T.INDEX:06X})')
            code, out = run_main(T, [str(path), '01', '02'])
            lines = out.splitlines()
            self.assertEqual(lines[0], f'map 01/02: 2 records at {T.RECORDS:06X}')
            self.assertTrue(lines[1].startswith('  0: [01 02 04 05 00 40 03 01 0A 0B 00 01] (1,2)~(3,4)'))
            self.assertIn('필드로', lines[2])
            code, out = run_main(T, [str(path), '07', '00'])
            self.assertEqual(out.strip(), 'map 07/00: no records')


if __name__ == '__main__':
    unittest.main()
