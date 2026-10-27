"""창 레코드 자리·크기 쓰기를 원본 롬 없이 검사한다."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dq5map import Rom, lorom  # noqa: E402
from dq5text import WINDOWS  # noqa: E402
from dq5windowwrite import FORMAT, dump, edits, patch, records  # noqa: E402

COUNT = 0x30


def fixture():
    data = bytearray(0x180000)
    first = (WINDOWS & 0xFFFF) + COUNT * 2
    for n in range(COUNT):
        addr = first + n * 8
        data[lorom(WINDOWS + n * 2):lorom(WINDOWS + n * 2) + 2] = addr.to_bytes(2, 'little')
        data[lorom(0x040000 | addr):lorom(0x040000 | addr) + 8] = bytes([0x42, 0x94, 0xC8, 0xA5, 0, 1, 0xFE, 0xFF])
    alias = lorom(0x040000 | first + 3 * 8)
    data[alias:alias + 3] = bytes([0x80, 0, 2])
    return bytes(data)


def apply(data, manifest):
    out = bytearray(data)
    for w in manifest['writes']:
        off = lorom(int(w['at'].replace(':', ''), 16))
        raw = bytes.fromhex(w['hex'])
        assert out[off:off + len(raw)] == bytes.fromhex(w['orig'])
        out[off:off + len(raw)] = raw
    return bytes(out)


class WindowWriteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = fixture()
        cls.rom = Rom(cls.data)

    def test_dump_and_unchanged(self):
        doc = dump(self.rom)
        self.assertEqual(len(records(self.rom)), COUNT)
        self.assertEqual(len(doc['windows']), COUNT - 1)
        self.assertEqual(doc['windows'][0], {'index': '00', 'x': 2, 'y': 20, 'w': 8, 'h': 5})
        self.assertEqual(patch(self.rom, doc)['writes'], [])

    def test_move_keeps_other_bits(self):
        manifest = patch(self.rom, {'format': FORMAT, 'windows': [{'index': '19', 'x': 12, 'y': 8, 'w': 6, 'h': 9}]})
        self.assertEqual(len(manifest['writes']), 1)
        rom = Rom(apply(self.data, manifest))
        addr = records(rom)[0x19]
        self.assertEqual(bytes(rom.d[lorom(addr):lorom(addr) + 8]), bytes([0x4C, 0x88, 0xC6, 0xA9, 0, 1, 0xFE, 0xFF]))

    def test_rejects(self):
        cases = [{'format': 'x', 'windows': []}, {'format': FORMAT}, {'format': FORMAT, 'windows': [], 'x': 1},
                 {'format': FORMAT, 'windows': [{'index': 25, 'x': 1}]},
                 {'format': FORMAT, 'windows': [{'index': '30', 'x': 1}]},
                 {'format': FORMAT, 'windows': [{'index': '1', 'x': 1}]},
                 {'format': FORMAT, 'windows': [{'index': 'zz', 'x': 1}]},
                 {'format': FORMAT, 'windows': [{'index': '03', 'x': 1}]},
                 {'format': FORMAT, 'windows': [{'index': '25', 'y': 15}]},
                 {'format': FORMAT, 'windows': [{'index': '19', 'x': 32}]},
                 {'format': FORMAT, 'windows': [{'index': '19', 'h': 16}]},
                 {'format': FORMAT, 'windows': [{'index': '19', 'x': 30}]},
                 {'format': FORMAT, 'windows': [{'index': '19', 'y': 30}]},
                 {'format': FORMAT, 'windows': [{'index': '19', 'w': 1}]},
                 {'format': FORMAT, 'windows': [{'index': '19', 'z': 1}]},
                 {'format': FORMAT, 'windows': [{'index': '19', 'x': 3}, {'index': '19', 'x': 4}]}]
        for doc in cases:
            with self.subTest(doc=doc), self.assertRaises(ValueError):
                edits(self.rom, doc)
        self.assertEqual(len(edits(self.rom, {'format': FORMAT, 'windows': [{'index': '25', 'y': 20}]})), 1)


if __name__ == '__main__':
    unittest.main()
