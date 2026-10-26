"""필드 블록 번호와 DB 미러가 있는 배치 뱅크의 경계 검사."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dq5fieldwrite import DATA_END, SIZE, parse_at, place_chunk, read_grid  # noqa: E402


class FieldWriteTests(unittest.TestCase):
    def test_existing_blocks_only(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'grid.bin'
            path.write_bytes((510).to_bytes(2, 'little') * SIZE)
            self.assertEqual(read_grid(path), [510] * SIZE)
            path.write_bytes((511).to_bytes(2, 'little') + bytes((SIZE - 1) * 2))
            with self.assertRaisesRegex(ValueError, '0~510'):
                read_grid(path)
            path.write_bytes(bytes(SIZE * 2 - 1))
            with self.assertRaises(ValueError):
                read_grid(path)

    def test_cpu_address(self):
        self.assertEqual(parse_at('30:8000'), 0x180000)
        self.assertEqual(parse_at('3f:fFfF'), DATA_END - 1)
        for value in ('00:8000', '2F:FFFF', '40:8000', '60:8000', 'B4:8000', '34:0000',
                      '34:7FFF', '34:10000', '34:8000junk', '034:8000', '+4:8000',
                      '34: 800', '348000', '0x1A0000', None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_at(value)

    def test_bank_alignment(self):
        self.assertEqual(place_chunk(parse_at('34:FFFE'), 2), parse_at('34:FFFE'))
        self.assertEqual(place_chunk(parse_at('34:FFFE'), 3), parse_at('35:8000'))
        self.assertEqual(place_chunk(parse_at('3F:8000'), 0x8000), parse_at('3F:8000'))
        self.assertEqual(place_chunk(parse_at('3F:FFFF'), 1), DATA_END - 1)

    def test_final_bank_overflow(self):
        for at, size in ((parse_at('3F:FFFF'), 2), (DATA_END, 1), (0x17FFFF, 1),
                         (parse_at('34:8000'), 0x8001), (parse_at('34:8000'), 0)):
            with self.subTest(at=at, size=size), self.assertRaises(ValueError):
                place_chunk(at, size)
        end = place_chunk(parse_at('3F:FFFE'), 2) + 2
        with self.assertRaises(ValueError):
            place_chunk(end, 1)


if __name__ == '__main__':
    unittest.main()
