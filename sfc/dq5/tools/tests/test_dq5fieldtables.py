"""필드 표 슬롯 경계·부분 수정·보존 비트를 원본 롬 없이 검사한다."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dq5field import BLOCK_LOWER, BLOCK_UPPER, GROUP_ARRIVAL, block_tiles  # noqa: E402
from dq5fieldtables import ARRIVAL_COUNT, BLOCK_COUNT, ENTRANCE_TABLES, FORMAT, dump, edits, patch  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402


def document(**parts):
    return {'format': FORMAT, **parts}


def fixture():
    raw = bytearray([0xA5]) * 0x180000
    for base in (BLOCK_LOWER, BLOCK_UPPER):
        for i in range(BLOCK_COUNT):
            off = lorom(base + i * 5)
            raw[off:off + 5] = bytes([i & 255, 1, 2, 3, i & 255])
    for start, count in ENTRANCE_TABLES.values():
        for i in range(count):
            off = lorom(start + i * 5)
            raw[off:off + 5] = bytes([i % 54, i, 0, 255 - i, 1])
        raw[lorom(start + count * 5)] = 255
    for i in range(ARRIVAL_COUNT):
        off = lorom(GROUP_ARRIVAL + i * 5)
        raw[off:off + 5] = bytes([i * 3 & 255, i, 255 - i, 1, i * 7 & 255])
    return bytes(raw)


def apply(original, manifest):
    raw = bytearray(original)
    for write in manifest['writes']:
        off = lorom(int(write['at'].replace(':', ''), 16))
        new = bytes.fromhex(write['hex'])
        assert original[off:off + len(new)] == bytes.fromhex(write['orig'])
        raw[off:off + len(new)] = new
    return bytes(raw)


class FieldTableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = fixture()
        cls.rom = Rom(cls.data)

    def test_all_records_roundtrip_with_reserved_bits(self):
        doc = dump(self.rom)
        rows = edits(self.rom, doc)
        self.assertEqual(len(rows), 511 * 2 + 61 + 54)
        self.assertTrue(all(new == old for _, new, old, _ in rows))
        self.assertEqual(patch(self.rom, doc)['writes'], [])

    def test_final_slots_leave_next_data_and_terminators_unchanged(self):
        doc = document(blocks=[{'index': 510, 'lower': [511, 0, 256, 1], 'upper': [256, 2, 511, 3]}],
                       entrances=[{'table': 'main', 'index': 46, 'x': 511}, {'table': 'aux', 'index': 13, 'y': 0}],
                       arrivals=[{'group': 53, 'map': 31}])
        manifest = patch(self.rom, doc)
        updated = apply(self.data, manifest)
        allowed = set()
        for addr in (BLOCK_LOWER + 510 * 5, BLOCK_UPPER + 510 * 5,
                     ENTRANCE_TABLES['main'][0] + 46 * 5, ENTRANCE_TABLES['aux'][0] + 13 * 5,
                     GROUP_ARRIVAL + 53 * 5):
            allowed.update(range(lorom(addr), lorom(addr) + 5))
        self.assertTrue(all(a == b or i in allowed for i, (a, b) in enumerate(zip(self.data, updated))))
        for boundary in (BLOCK_UPPER, 0x2AB722, 0x04FE82, 0x04FEC9, 0x0FEBA5):
            off = lorom(boundary)
            self.assertEqual(updated[off:off + 5], self.data[off:off + 5])
        self.assertEqual(block_tiles(Rom(updated), BLOCK_LOWER, 510), [511, 0, 256, 1])
        self.assertEqual(block_tiles(Rom(updated), BLOCK_UPPER, 510), [256, 2, 511, 3])
        self.assertEqual(updated[lorom(BLOCK_LOWER + 510 * 5 + 4)] & 15, 14)

    def test_partial_arrival_preserves_other_bits(self):
        changed = apply(self.data, patch(self.rom, document(arrivals=[{'group': 33, 'direction': 1}])))
        off = lorom(GROUP_ARRIVAL + 33 * 5)
        self.assertEqual(changed[off:off + 4], self.data[off:off + 4])
        self.assertEqual(changed[off + 4], (self.data[off + 4] & 0xFC) | 1)
        complete = {'group': 0, 'map': 31, 'world_code': 3, 'wagon': True, 'x': 255, 'y': 254,
                    'layer': 4, 'direction': 3, 'party_overlap': True, 'map_flags': 31}
        changed = apply(self.data, patch(self.rom, document(arrivals=[complete])))
        off = lorom(GROUP_ARRIVAL)
        self.assertEqual(changed[off:off + 5], bytes.fromhex('ff ff fe 04 ff'))

    def test_duplicate_groups_are_distinct_indexed_entrances(self):
        raw = bytearray(self.data)
        base = lorom(ENTRANCE_TABLES['main'][0])
        raw[base + 5] = raw[base]
        changed = apply(raw, patch(Rom(raw), document(entrances=[{'table': 'main', 'index': 1, 'x': 300}])))
        self.assertEqual(changed[base:base + 5], raw[base:base + 5])
        self.assertEqual(changed[base + 6:base + 8], bytes.fromhex('2c 01'))
        self.assertEqual(changed[base + 8:base + 10], raw[base + 8:base + 10])

    def test_invalid_documents_and_fields(self):
        cases = [None, [], {}, {'format': 'wrong'}, document(extra=[]), document(blocks=None),
                 document(blocks=[None]), document(blocks=[{'index': 511, 'lower': [0] * 4}]),
                 document(blocks=[{'index': True}]), document(blocks=[{'index': 0, 'lower': [512] * 4}]),
                 document(blocks=[{'index': 0, 'lower': [True] * 4}]), document(blocks=[{'index': 0, 'lower': [1]}]),
                 document(blocks=[{'index': 0, 'reserved': 0}]), document(blocks=[{'index': 0}, {'index': 0}]),
                 document(entrances=[{'table': 'main', 'index': 47}]),
                 document(entrances=[{'table': 'aux', 'index': 14}]),
                 document(entrances=[{'table': [], 'index': 0}]),
                 document(entrances=[{'table': 'main', 'index': 0, 'group': 0x36}]),
                 document(entrances=[{'table': 'main', 'index': 0, 'x': 512}]),
                 document(entrances=[{'table': 'aux', 'index': 0, 'y': -1}]),
                 document(entrances=[{'table': 'aux', 'index': 0}] * 2),
                 document(arrivals=[{'group': 54}]), document(arrivals=[{'group': 0x50}]),
                 document(arrivals=[{'group': 0, 'world_code': 4}]),
                 document(arrivals=[{'group': 0, 'wagon': 1}]),
                 document(arrivals=[{'group': 0, 'party_overlap': 'false'}]),
                 document(arrivals=[{'group': 0, 'map_flags': 32}]),
                 document(arrivals=[{'group': 0, 'direction': 4}]),
                 document(arrivals=[{'group': 0, 'map': 32}]),
                 document(arrivals=[{'group': 0, 'layer': 256}]),
                 document(arrivals=[{'group': 0, 'world': 0}]), document(arrivals=[{'group': 0}] * 2)]
        for doc in cases:
            with self.subTest(doc=doc), self.assertRaises(ValueError):
                patch(self.rom, doc)

    def test_invalid_rom_layout(self):
        with self.assertRaises(ValueError):
            dump(Rom(b''))
        for addr in (0x04FE82, 0x04FEC9):
            raw = bytearray(self.data)
            raw[lorom(addr)] = 0
            with self.assertRaises(ValueError):
                patch(Rom(raw), document())


if __name__ == '__main__':
    unittest.main()
