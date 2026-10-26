"""새 게임 머리·일행 레코드 쓰기를 원본 롬 없이 검사한다."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dq5build import build, parse_at as patch_at  # noqa: E402
from dq5growth import PEOPLE as PERSON_GROWTH, RECORD as GROWTH_RECORD, exp_at  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402
from dq5newgame import (  # noqa: E402
    COPY_LENGTH, COPY_SOURCE, FORMAT, HEADER, HEADER_SIZE, PEOPLE, PEOPLE_COUNT, RECORD, dump, edits, new_game,
    parse_at, patch,
)


def fixture():
    data = bytearray(0x180000)
    for addr, raw in ((0x23D6CD, b'\xbf\xed\xd6\x23'), (COPY_SOURCE, b'\xbf\x14\xc0\x23'), (COPY_LENGTH, b'\xe0\x2a\x00')):
        data[lorom(addr):lorom(addr) + len(raw)] = raw
    head = bytearray([1] * 0x19) + bytes([0x14, 0, 0, 0, 1, 1, 1]) + bytes(HEADER_SIZE - 0x20)
    data[lorom(HEADER):lorom(HEADER) + HEADER_SIZE] = head
    for n in range(PEOPLE_COUNT):
        rec = bytearray(RECORD)
        rec[0], rec[1], rec[2], rec[0x0E], rec[0x12], rec[0x13] = n, 0x80, 10 + n, 10 + n, 1, 99
        rec[0x16:0x22] = bytes([n, 0x42]) + b'\xff' * 10
        rec[0x14] = 1
        data[lorom(PEOPLE + n * RECORD):lorom(PEOPLE + n * RECORD) + RECORD] = rec
    for n in range(11):
        off = lorom(PERSON_GROWTH + n * GROWTH_RECORD)
        data[off:off + 2] = bytes([0, 5 + n])
        data[off + 9] = 0x10
    return bytes(data)


def rebuild(data, manifest):
    writes = [(patch_at(w['at'])[0], bytes.fromhex(w['hex']), bytes.fromhex(w['orig']) if 'orig' in w else None,
               w['note']) for w in manifest['writes']]
    size = manifest.get('rom_size')
    return build(data, [(manifest['name'], size, writes)], size)[0]


class NewGameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = fixture()
        cls.rom = Rom(cls.data)

    def test_dump_and_unchanged(self):
        doc = dump(self.rom)
        self.assertEqual(doc['gold'], 20)
        self.assertEqual(doc['members'][0]['items'], [0, 0x42])
        self.assertEqual(patch(self.rom, {k: v for k, v in doc.items() if k != 'members'})['writes'], [])
        manifest = patch(self.rom, doc, 0x3C8000)
        self.assertEqual([w['note'] for w in manifest['writes']], ['new game party records', 'new game record source'])
        head, records = new_game(Rom(rebuild(self.data, manifest)))
        self.assertEqual(records, self.data[lorom(PEOPLE):lorom(PEOPLE) + RECORD])

    def test_party_header_and_records(self):
        doc = {'format': FORMAT, 'gold': 999999, 'names': {'son': [0x10, 0x11]}, 'walking': 2, 'wagon': True,
               'order': [2, 0, 1, 3],
               'members': [{'base': 0, 'level': 3, 'items': [1, 2, 3], 'equipped': [2]},
                           {'base': 3}, {'base': 12, 'hp': 5}, {'base': 4, 'next_exp': 77, 'level': 2}]}
        twins = {'format': FORMAT, 'members': [{'base': 0}, {'base': 12, 'person': 0x82}, {'base': 12, 'person': 0x82}]}
        self.assertEqual(len(edits(self.rom, twins, 0x3C8000)), 4)
        head, records = new_game(Rom(rebuild(self.data, patch(self.rom, doc, 0x3CFF00))))
        self.assertEqual(int.from_bytes(head[0x19:0x1C], 'little'), 999999)
        self.assertEqual(head[0x09:0x11], bytes([0x10, 0x11] + [1] * 6))
        self.assertEqual((head[0x1C] & 0x80, head[0x1D], head[0x1E], head[0x1F]), (0x80, 4, 2, 2))
        self.assertEqual(head[0x20:0x28], bytes([2, 0, 1, 3, 0, 0, 0, 0]))
        self.assertEqual(head[0x28:0x30], head[0x20:0x28])
        self.assertEqual(len(records), 4 * RECORD)
        hero = records[:RECORD]
        self.assertEqual((hero[0x12], hero[0x16:0x1A], hero[0x14:0x16]), (3, bytes([1, 2, 3, 0xFF]), b'\x04\x00'))
        self.assertEqual(int.from_bytes(hero[0x26:0x29], 'little'), exp_at(self.rom, PERSON_GROWTH, 4))
        self.assertEqual(int.from_bytes(hero[0x0B:0x0E], 'little'), exp_at(self.rom, PERSON_GROWTH, 3))
        self.assertEqual(records[RECORD:2 * RECORD], self.data[lorom(PEOPLE + 3 * RECORD):][:RECORD])
        self.assertEqual(records[2 * RECORD + 2], 5)
        self.assertEqual(int.from_bytes(records[3 * RECORD + 0x26:3 * RECORD + 0x29], 'little'), 77)

    def test_rejects(self):
        member = {'base': 0}
        cases = [
            ({'format': 'x'}, None), ({'format': FORMAT, 'x': 1}, None), ({'format': FORMAT, 'gold': 1000000}, None),
            ({'format': FORMAT, 'names': {'hero': []}}, None), ({'format': FORMAT, 'names': {'hero': [1] * 9}}, None),
            ({'format': FORMAT, 'names': {'wife': [1]}}, None), ({'format': FORMAT, 'members': [member]}, None),
            ({'format': FORMAT}, 0x3C8000), ({'format': FORMAT, 'members': []}, 0x3C8000),
            ({'format': FORMAT, 'members': [member] * 9}, 0x3C8000),
            ({'format': FORMAT, 'members': [member] * 4}, 0x3C8000),
            ({'format': FORMAT, 'walking': 2, 'members': [member]}, 0x3C8000),
            ({'format': FORMAT, 'order': [1, 0], 'members': [member]}, 0x3C8000),
            ({'format': FORMAT, 'members': [{'base': 13}]}, 0x3C8000),
            ({'format': FORMAT, 'members': [{'base': 0, 'hp': 99}]}, 0x3C8000),
            ({'format': FORMAT, 'members': [{'base': 0, 'level': 0}]}, 0x3C8000),
            ({'format': FORMAT, 'members': [{'base': 0, 'items': [0xD8]}]}, 0x3C8000),
            ({'format': FORMAT, 'members': [{'base': 0, 'items': [1] * 13}]}, 0x3C8000),
            ({'format': FORMAT, 'members': [{'base': 0, 'equipped': [5]}]}, 0x3C8000),
            ({'format': FORMAT, 'members': [{'base': 0, 'equipped': [0, 0]}]}, 0x3C8000),
            ({'format': FORMAT, 'members': [{'base': 0, 'speed': 1}]}, 0x3C8000),
            ({'format': FORMAT, 'members': [member]}, 0x3CFFF0),
            ({'format': FORMAT, 'walking': 1, 'members': [member, {'base': 3}]}, 0x3C8000),
            ({'format': FORMAT, 'members': [member, {'base': 3}, {'base': 3}]}, 0x3C8000),
            ({'format': FORMAT, 'members': [{'base': 3}, member]}, 0x3C8000),
        ]
        for doc, at in cases:
            with self.subTest(doc=doc, at=at), self.assertRaises(ValueError):
                edits(self.rom, doc, at)
        for value in ('2F:8000', '7E:8000', '3C:7FFF', '3C8000', None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_at(value)
        with self.assertRaises(ValueError):
            dump(Rom(bytes(0x180000)))


if __name__ == '__main__':
    unittest.main()
