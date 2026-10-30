"""칸 배치 쓰기: 칸 글, 맵 OBJ 물체 표 늘리기와 칸 바이트 옮기기, 탈것·세트 칸 제자리 쓰기."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dq5sprite as S  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402
from dq5objlayout import (FORMAT, REGION_END, TABLE, VEHICLE_PARTS, address, dump, normalized,  # noqa: E402
                          object_entry, parse_token, patch, token)


def put(data, addr, raw):
    data[lorom(addr):lorom(addr) + len(raw)] = raw


def fake_rom():
    """16:F862 에 물체 둘(칸 바이트는 표 바로 뒤), 탈것 칸 표, 세트 01(6타일)·81(8타일) 레코드를 둔 롬."""
    data = bytearray(0x200000)
    cells_a, cells_b = TABLE + 2 * 9 + 1, TABLE + 2 * 9 + 1 + 4
    put(data, TABLE, bytes([0x04, 0x06, 39, 9, 2, 2, 0x4C, cells_a & 0xFF, cells_a >> 8 & 0xFF,
                            0xFE, 0x00, 10, 20, 0x81, 1, 0x6C, cells_b & 0xFF, cells_b >> 8 & 0xFF, 0xFF]))
    put(data, cells_a, bytes([0, 1, 2, 3, 0x85]))
    for name, (vid, k, ldy, bank) in VEHICLE_PARTS.items():
        part = next(v for v in S.VEHICLES if v['id'] == vid)['parts'][k]
        table = 0x048000 + (vid & 0x0F) * 0x400 + k * 0x200
        put(data, ldy, (table & 0xFFFF).to_bytes(2, 'little'))
        put(data, bank, b'\x04')
        put(data, table, bytes(i % 0x40 for i in range(0x200)))
    put(data, S.SET_TABLE_SITES[0], S.SET_POINTERS.to_bytes(3, 'little'))
    put(data, S.SET_BANK_SITES[0], b'\x1f')
    put(data, S.SET_POINTERS, b'\xff\xff' * S.TABLE_ENTRIES)
    for s, at in ((0x01, 0xE000), (0x81, 0xE040)):
        put(data, S.SET_POINTERS + s * 2, at.to_bytes(2, 'little'))
        put(data, 0x1F0000 | at, bytes([0, 0x80, 0x30]) + bytes(i % 12 for i in range(48)) + bytes([12]))
    return Rom(data)


class TokenTests(unittest.TestCase):
    def test_tokens(self):
        self.assertEqual(parse_token('h0a', ''), (0x8A, False))
        self.assertEqual(parse_token('hv7F', '', vflip=True), (0xFF, True))
        self.assertEqual(token((0x8A, True)), 'hv0A')
        for text, kw in (('80', {}), ('v01', {}), ('x01', {}), ('0c', {'limit': 12})):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_token(text, '', **kw)

    def test_entry_bytes(self):
        head, cells = object_entry({'map': 'field0', 'x': 300, 'y': 260, 'cond': 'night', 'palette': 5,
                                    'priority': 3, 'cells': ['01 h02']}, '')
        self.assertEqual(head, bytes([0xFE, 0, 300 & 0xFF, 260 & 0xFF, 0xC2, 1, 1 | 2 | 5 << 2 | 3 << 5]))
        self.assertEqual(cells, bytes([1, 0x82]))
        for bad in ({'map': '04/06', 'x': 1, 'y': 1, 'cells': ['01', '01 02']},
                    {'map': 'FE/00', 'x': 1, 'y': 1, 'cells': ['01']},
                    {'map': '04/06', 'x': 512, 'y': 1, 'cells': ['01']},
                    {'map': '04/06', 'x': 1, 'y': 1, 'cells': ['01'], 'cond': 'dusk'}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                object_entry(bad, '')

    def test_field_y_low_byte_80(self):
        # 원래 표에도 아래 바이트가 80 인 384 가 있어(필드 Y 는 128 로 읽힘) 그대로 받는다.
        head = object_entry({'map': 'field0', 'x': 1, 'y': 384, 'cells': ['01']}, '')[0]
        self.assertEqual(head[3], 0x80)
        self.assertTrue(head[6] & 2)

    def test_address(self):
        self.assertEqual(address('16:FE10'), 0x16FE10)
        for bad in ('16FE10', '15:FE10', '16:7FFF', '16:FE1', None):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                address(bad)


class PatchTests(unittest.TestCase):
    def setUp(self):
        self.rom = fake_rom()
        self.doc = dump(self.rom)

    def writes(self, doc, at=None):
        return patch(self.rom, doc, at)['writes']

    def test_round_trip_is_empty(self):
        self.assertEqual(self.doc['objects'][0]['cells'], ['00 01', '02 03'])
        self.assertEqual(self.doc['objects'][1]['cond'], 'day')
        self.assertEqual(self.writes(self.doc), [])

    def test_new_object_grows_table_and_moves_cells(self):
        doc = dict(self.doc, objects=self.doc['objects'] + [dict(self.doc['objects'][0], x=36, cells=['h01 h00'])])
        with self.assertRaises(ValueError):
            self.writes(doc)
        w = self.writes(doc, at=0x16FE10)
        self.assertEqual([x['at'] for x in w], ['16:F862', '16:FE10'])
        table = bytes.fromhex(w[0]['hex'])
        self.assertEqual(len(table), 3 * 9 + 1)
        # 늘어난 표가 덮은 물체 0·1 의 칸과 새 칸을 --at 에 차례로 둔다.
        self.assertEqual(bytes.fromhex(w[1]['hex']), bytes([0, 1, 2, 3, 0x85, 0x81, 0x80]))
        self.assertEqual([table[k * 9 + 7:k * 9 + 9] for k in range(3)], [b'\x10\xfe', b'\x14\xfe', b'\x15\xfe'])
        # 같은 칸 바이트는 남은 구역이나 이미 둔 자리에서 다시 쓴다.
        doc['objects'][2]['cells'] = ['01 02']
        w = self.writes(doc, at=0x16FE10)
        self.assertEqual(bytes.fromhex(w[1]['hex']), bytes([0, 1, 2, 3, 0x85]))
        self.assertEqual(bytes.fromhex(w[0]['hex'])[18 + 7:18 + 9], b'\x11\xfe')
        self.assertNotIn('orig', w[1])
        with self.assertRaises(ValueError):
            self.writes(doc, at=0x168000 - 0x10000)

    def test_table_limit(self):
        most = (REGION_END - TABLE - 1) // 9
        self.assertEqual(most, 159)
        one = dict(self.doc['objects'][0], cells=['00'])
        self.assertEqual([x['at'] for x in self.writes(dict(self.doc, objects=[one] * most))], ['16:F862'])
        with self.assertRaises(ValueError):
            self.writes(dict(self.doc, objects=[one] * (most + 1)), at=0x16FE10)

    def test_at_past_bank_end(self):
        doc = dict(self.doc, objects=self.doc['objects'] + [dict(self.doc['objects'][0], cells=['11 12 13 14'])])
        self.writes(doc, at=0x16FFF5)
        with self.assertRaises(ValueError):
            self.writes(doc, at=0x16FFF8)

    def test_reuses_remaining_region(self):
        # 표 뒤 남은 구역에 같은 바이트가 있으면 --at 없이 그 자리를 가리킨다.
        put(self.rom.d, TABLE + 0x100, bytes([0x21, 0x22]))
        doc = dict(self.doc, objects=[self.doc['objects'][0], dict(self.doc['objects'][1], cells=['21 22'])])
        w = self.writes(doc)
        self.assertEqual([x['at'] for x in w], ['16:F862'])
        self.assertEqual(bytes.fromhex(w[0]['hex'])[16:18], ((TABLE + 0x100) & 0xFFFF).to_bytes(2, 'little'))

    def test_vehicle_and_set_in_place(self):
        v = next(x for x in self.doc['vehicles'] if x['part'] == '80-2')
        s = next(x for x in self.doc['sets'] if x['set'] == '01')
        doc = {'format': FORMAT,
               'vehicles': [{'part': '80-2', 'cells': {'down0': ['h00 01 02'] + v['cells']['down0'][1:]}}],
               'sets': [{'set': '01', 'cells': {'down1': 'h0b 0a 09 08 07 06'}}]}
        w = self.writes(doc)
        self.assertEqual(len(w), 2)
        self.assertTrue(all('orig' in x for x in w))
        self.assertEqual(normalized(doc, self.rom)['sets'][0]['cells']['down1'], 'h0B 0A 09 08 07 06')
        for bad in ({'vehicles': [{'part': '80-2', 'cells': {'down0': ['00 01 02']}}]},
                    {'vehicles': [{'part': '81-2', 'cells': {'all': ['00 01 02 03', '00 01 02 03']}}]},
                    {'sets': [{'set': '01', 'cells': {'down1': '0c 0a 09 08 07 06'}}]},
                    {'sets': [{'set': '81', 'cells': {'up-head': '00 01 02'}}]},
                    {'sets': [{'set': '02', 'cells': {}}]}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.writes({'format': FORMAT, **bad})


if __name__ == '__main__':
    unittest.main()
