"""조사 보상 표와 필드 조사 코드의 예약 바이트·주소·입력 경계 검사."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch as mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dq5chestwrite import (FIELD_CALL, FIELD_CODE, FIELD_TEMPLATE, FORMAT, TABLES, decode, dump, edits, encode,
                           encode_field, layout, map_dimensions, patch, read_field)
from dq5map import Rom, lorom


def fixture():
    data = bytearray(0x100000)
    for name, (start, count, size) in TABLES.items():
        for i in range(count):
            at = lorom(start + i * size)
            row = bytearray(size)
            if name == 'chests':
                row[:] = b'\xa1\x00'
            elif name == 'chest_maps':
                row[1], row[2] = i, 161 if i == 0 else 0
            else:
                row[1], row[2], row[3] = i, 4, 5
                if size == 9:
                    row[4] = 0x38 if name == 'search' else 1
                row[-4:-2] = b'\xa1\x00'
                row[-2:] = b'\x03\x80'
            data[at:at + size] = row
        if name != 'chests':
            at = lorom(start + count * size)
            data[at:at + 2] = b'\xff\xff'
    values = {'x0': 10, 'x1': 0, 'X0': 12, 'X1': 0, 'y0': 0x20, 'y1': 1, 'Y0': 0x22, 'Y1': 1,
              'r0': 0xA1, 'r1': 0, 'i0': 0x30, 'i1': 0x30, 'm0': 0x08, 'm1': 0x08, '??': 0x01}
    code = bytes(values[token] if token in values else int(token, 16) for token in FIELD_TEMPLATE)
    data[lorom(FIELD_CODE):lorom(FIELD_CODE) + len(code)] = code
    data[lorom(FIELD_CALL):lorom(FIELD_CALL) + 3] = bytes.fromhex('20 f2 e5')
    return Rom(data)


def poke(rom, addr, value):
    data = bytearray(rom.d)
    data[lorom(addr)] = value
    return Rom(data)


class ChestWriteTests(unittest.TestCase):
    def test_reserved_search_byte_and_partial_fields(self):
        raw = bytes.fromhex('17 00 04 04 38 a1 00 03 01')
        got = encode('search', raw, {'reward': 0x300, 'mask': 0x2C})
        self.assertEqual(got, bytes.fromhex('17 00 04 04 38 00 03 03 2c'))
        self.assertNotIn('layer', decode('search', got))
        with self.assertRaises(ValueError):
            encode('search', raw, {'layer': 1})

    def test_foot_layer_and_ahead_raw_flag_byte(self):
        raw = bytes.fromhex('17 00 04 04 01 a1 00 03 01')
        self.assertEqual(encode('foot', raw, {'layer': 2})[4], 2)
        ahead = bytes.fromhex('03 04 0b 07 a1 00 ac 80')
        got = encode('ahead', ahead, {'reward': 0xD005})
        self.assertEqual(got[-2], 0xAC)
        self.assertEqual(decode('ahead', got)['reward'], 0xD005)

    def test_reward_and_mask_bounds(self):
        for value in (0, 255, 256, 0xCFFF, 0xD000, 0xD009, 0xFFFC, 0xFFFF):
            self.assertEqual(int.from_bytes(encode('chests', b'\0\0', {'reward': value}), 'little'), value)
        for value in (True, -1, 65536, 0xD00A, 0xFFFB, '321'):
            with self.assertRaises(ValueError):
                encode('chests', b'\0\0', {'reward': value})
        with self.assertRaises(ValueError):
            encode('foot', bytes.fromhex('17 00 04 04 01 a1 00 03 01'), {'mask': 0})

    @mock('dq5chestwrite.map_pointer', return_value=0x0F9000)
    def test_high_map_dimensions_read_only_header(self, _):
        data = bytearray(0x100000)
        at = lorom(0x0F9000)
        data[at:at + 3] = bytes([255, 64, 96])
        self.assertEqual(map_dimensions(Rom(data), 0x54, 0x52), (64, 96))

    def test_layout_ends_and_short_rom(self):
        rom = fixture()
        layout(rom)
        for name in TABLES.keys() - {'chests'}:
            data = bytearray(rom.d)
            start, count, size = TABLES[name]
            data[lorom(start + count * size)] = 0
            with self.assertRaises(ValueError):
                layout(Rom(data))
        with self.assertRaises(ValueError):
            layout(Rom(bytes(16)))

    @mock('dq5chestwrite.map_ids', return_value=[(0, i) for i in range(86)])
    @mock('dq5chestwrite.map_dimensions', return_value=(64, 64))
    def test_full_roundtrip_and_manifest_orig(self, _, __):
        rom = fixture()
        self.assertEqual(patch(rom, dump(rom))['writes'], [])
        doc = {'format': FORMAT, 'search': [{'index': 1, 'x': 7, 'reward': 0x432}]}
        writes = patch(rom, doc)['writes']
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0]['at'], '1F:F5D4')
        self.assertEqual(bytes.fromhex(writes[0]['orig'])[4], 0x38)
        self.assertEqual(bytes.fromhex(writes[0]['hex'])[4], 0x38)
        with self.assertRaises(ValueError):
            patch(rom, {'format': FORMAT, 'search': [{'index': 1, 'x': 64}]})

    @mock('dq5chestwrite.map_ids', return_value=[(0, i) for i in range(86)])
    def test_schema_duplicate_and_counts(self, _):
        rom = fixture()
        invalid = [None, [], {}, {'format': FORMAT, 'other': []}, {'format': FORMAT, 'foot': None},
                   {'format': FORMAT, 'chests': [{'index': True}]},
                   {'format': FORMAT, 'chests': [{'index': 161}]},
                   {'format': FORMAT, 'chests': [{'index': 0}, {'index': 0}]},
                   {'format': FORMAT, 'chests': [{'index': 0, 'value': 1}]},
                   {'format': FORMAT, 'chest_maps': [{'index': 0, 'count': 160}]},
                   {'format': FORMAT, 'search': [{'index': 0, 'map': 1}]},
                   {'format': FORMAT, 'search': [{'index': 0, 'group': 1}]}]
        for doc in invalid:
            with self.subTest(doc=doc), self.assertRaises(ValueError):
                edits(rom, doc)


    def test_field_reads_immediates_and_writes_only_reward(self):
        rom = fixture()
        raw = read_field(rom)
        self.assertEqual(dump(rom)['field'], [{'index': 0, 'x': 10, 'y': 0x120, 'width': 2, 'height': 2,
                                               'reward': 0xA1, 'flag_index': 0x30, 'mask': 0x08}])
        got = encode_field(raw, {'reward': 0x46C, 'x': 10, 'mask': 0x08})
        self.assertEqual([i for i in range(len(raw)) if raw[i] != got[i]],
                         [FIELD_TEMPLATE.index('r0'), FIELD_TEMPLATE.index('r1')])
        for change in ({'x': 11}, {'width': 3}, {'y': 0}, {'height': 1}, {'flag_index': 0x31}, {'mask': 1},
                       {'reward': 0xD000}, {'reward': 0xFFFF}, {'reward': True}, {'layer': 1}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                encode_field(raw, change)

    @mock('dq5chestwrite.map_ids', return_value=[(0, i) for i in range(86)])
    def test_field_manifest_and_schema(self, _):
        rom = fixture()
        writes = patch(rom, {'format': FORMAT, 'field': [{'index': 0, 'reward': 0x46C}]})['writes']
        self.assertEqual(writes, [{'at': '12:E61F', 'hex': '6c 04', 'orig': 'a1 00', 'note': 'field 0'}])
        for rows in ({}, [{'index': 1}], [{'index': 0}, {'index': 0}], [{'reward': 1}]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                edits(rom, {'format': FORMAT, 'field': rows})

    def test_field_code_must_match_template(self):
        rom = fixture()
        for addr, value in ((FIELD_CALL + 1, 0), (FIELD_CODE, 0xE2), (FIELD_CODE + FIELD_TEMPLATE.index('i1'), 0x31),
                            (FIELD_CODE + FIELD_TEMPLATE.index('m1'), 0x10)):
            with self.subTest(addr=hex(addr)), self.assertRaises(ValueError):
                dump(poke(rom, addr, value))


if __name__ == '__main__':
    unittest.main()
