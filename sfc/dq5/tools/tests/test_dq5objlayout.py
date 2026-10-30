"""칸 배치 쓰기: 칸 글, 맵 OBJ 물체 표 늘리기와 칸 바이트 옮기기, 탈것·세트 칸 제자리 쓰기."""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dq5sprite as S  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402
from dq5objlayout import (FORMAT, REGION_END, TABLE, VEHICLE_FRAMES, VEHICLE_PARTS, address, dump,  # noqa: E402
                          normalized, object_entry, parse_token, patch, token, vehicle_part)


def put(data, addr, raw):
    data[lorom(addr):lorom(addr) + len(raw)] = raw


def fake_rom():
    """16:F862 에 물체 둘(칸 바이트는 표 바로 뒤), 탈것 칸 표, 세트 01(6타일)·81(8타일) 레코드를 둔 롬."""
    data = bytearray(0x200000)
    cells_a, cells_b = TABLE + 2 * 9 + 1, TABLE + 2 * 9 + 1 + 4
    put(data, TABLE, bytes([0x04, 0x06, 39, 9, 2, 2, 0x4C, cells_a & 0xFF, cells_a >> 8 & 0xFF,
                            0xFE, 0x00, 10, 20, 0x81, 1, 0x6C, cells_b & 0xFF, cells_b >> 8 & 0xFF, 0xFF]))
    put(data, cells_a, bytes([0, 1, 2, 3, 0x85]))
    for name, site in VEHICLE_PARTS.items():
        vid, k = site['vid'], int(name[-1]) - 1
        part = next(v for v in S.VEHICLES if v['id'] == vid)['parts'][k]
        table = 0x048000 + (vid & 0x0F) * 0x400 + k * 0x200
        put(data, site['ldy'], (table & 0xFFFF).to_bytes(2, 'little'))
        put(data, site['bank'], b'\x04')
        put(data, table, bytes(i % 0x40 for i in range(0x200)))
        for key in ('cols', 'rows', 'dir', 'frame'):
            if site[key]:
                put(data, site[key], bytes([part[key]]))
        per = part['cols'] * part['rows']
        put(data, site['count'], bytes([part['dir'] * 2 // per if part['dir'] else 1]))
        if site.get('vflip'):
            put(data, site['vflip'], bytes(part['vflip']) + b'\xff')
    for vid, at in VEHICLE_FRAMES.items():
        if at:
            put(data, at, bytes([0x81 if vid == 0x80 else 0x82]))
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

    @mock.patch('dq5objlayout.map_people', return_value={})
    def test_new_object_grows_table_and_moves_cells(self, _):
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

    def test_slot_limit(self):
        # 04/06 낮에 인물 22명: 물체 0(1개) + 새 물체 1개 → 8 + 22 + 2 = 0x20 은 받고, 하나 더면 0x21 이라 거부.
        new = dict(self.doc['objects'][0], cells=['00'])
        with mock.patch('dq5objlayout.map_people', return_value={(0x04, 0x06, False): 22}):
            self.writes(dict(self.doc, objects=self.doc['objects'] + [new]), at=0x16FE10)
            with self.assertRaises(ValueError):
                self.writes(dict(self.doc, objects=self.doc['objects'] + [new, new]), at=0x16FE10)
            # 밤 전용 물체는 낮 수에 들지 않는다.
            self.writes(dict(self.doc, objects=self.doc['objects'] + [new, dict(new, cond='night')]), at=0x16FE10)
        # 장면이 슬롯을 더 쓰는 맵은 그만큼 한도가 줄어든다(06/00 은 넷).
        six = dict(new, map='06/00')
        with mock.patch('dq5objlayout.map_people', return_value={(0x06, 0x00, False): 19}):
            self.writes(dict(self.doc, objects=self.doc['objects'] + [six]), at=0x16FE10)
            with self.assertRaises(ValueError):
                self.writes(dict(self.doc, objects=self.doc['objects'] + [six, six]), at=0x16FE10)
        # 그룹 전체(7F) 물체는 그 그룹의 모든 맵에 센다.
        group = dict(new, map='06/**')
        with mock.patch('dq5objlayout.map_people', return_value={(0x06, 0x03, True): 24}), \
                self.assertRaises(ValueError):
            self.writes(dict(self.doc, objects=self.doc['objects'] + [group]), at=0x16FE10)

    def test_table_limit(self):
        most = (REGION_END - TABLE - 1) // 9
        self.assertEqual(most, 159)
        # 필드 물체는 슬롯 한도를 보지 않아 표 한도만 걸린다.
        one = dict(self.doc['objects'][1], cells=['00'])
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



def carpet_doc(rom, frames=3, size3=None):
    """양탄자 부분 셋의 모든 블록. 새 프레임은 프레임 0 의 칸, size3 이면 부분 3 줄마다 첫 칸을 더한다."""
    out = []
    for v in dump(rom)['vehicles']:
        if not v['part'].startswith('80'):
            continue
        cells = {}
        for d in ('up', 'right', 'down', 'left'):
            for f in range(frames):
                rows = v['cells'][f'{d}{min(f, 1) if f < 2 else 0}']
                if size3 and v['part'] == '80-3':
                    rows = [r + ' ' + r.split()[0] for r in rows]
                cells[f'{d}{f}'] = rows
        row = {'part': v['part'], 'frames': frames, 'cells': cells}
        if size3 and v['part'] == '80-3':
            row['size'] = size3
        out.append(row)
    return {'format': FORMAT, 'vehicles': out}


class VehicleLayoutTests(unittest.TestCase):
    def setUp(self):
        self.rom = fake_rom()

    def build(self, doc, at=0x04FEE0):
        from dq5objlayout import built
        return built(self.rom, patch(self.rom, doc, vehicle_at=at))

    def test_frames_and_size(self):
        doc = carpet_doc(self.rom, 3, '4x1')
        with self.assertRaises(ValueError):
            patch(self.rom, doc)
        after = self.build(doc)
        p1, p3 = vehicle_part(after, '80-1'), vehicle_part(after, '80-3')
        self.assertEqual((p1['frames'], p1['dir'], p1['frame']), (3, 3 * 6 * 2, 6 * 2))
        self.assertEqual((p3['cols'], p3['rows'], p3['dir'], p3['frame'], p3['copied']), (4, 1, 24, 8, 12 * 4))
        self.assertEqual(p1['table'], 0x04FEE0)
        self.assertEqual(vehicle_part(after, '80-2')['table'], 0x04FEE0 + 12 * 6)
        self.assertEqual(after.u8(VEHICLE_FRAMES[0x80]), 0x82)
        self.assertEqual(normalized(doc, self.rom)['vehicles'], dump(after)['vehicles'])
        # 다른 탈것은 그대로.
        self.assertEqual(vehicle_part(after, '82-1')['table'], vehicle_part(self.rom, '82-1')['table'])

    def test_size_only_copies_other_parts(self):
        v = next(x for x in dump(self.rom)['vehicles'] if x['part'] == '80-3')
        doc = {'format': FORMAT, 'vehicles': [{'part': '80-3', 'size': '4x1', 'cells': {
            k: [r + ' 00' for r in rows] for k, rows in v['cells'].items()}}]}
        after = self.build(doc)
        for n in ('80-1', '80-2'):
            old, new = vehicle_part(self.rom, n), vehicle_part(after, n)
            self.assertEqual(new['bytes'], old['bytes'])
            self.assertEqual(new['copied'], old['copied'])
        self.assertEqual(vehicle_part(after, '80-3')['cols'], 4)

    def test_rejects(self):
        base = carpet_doc(self.rom, 3)
        cases = {
            'shared-immediate': {'vehicles': [dict(base['vehicles'][1], size='3x2')]},
            'missing-part': {'vehicles': base['vehicles'][:2]},
            'missing-block': {'vehicles': [dict(r, cells={k: c for k, c in r['cells'].items() if k != 'up2'})
                                           for r in base['vehicles']]},
            'frames-differ': {'vehicles': [base['vehicles'][0], dict(base['vehicles'][1], frames=2),
                                           base['vehicles'][2]]},
            'tenkuu-frames': {'vehicles': [{'part': '81-1', 'frames': 2, 'cells': {}}]},
            'stride-byte': {'vehicles': [dict(r, frames=16) for r in base['vehicles']]},
        }
        for name, extra in cases.items():
            with self.subTest(name=name), self.assertRaises(ValueError):
                patch(self.rom, {'format': FORMAT, **extra}, vehicle_at=0x04FEE0)
        with self.assertRaises(ValueError):
            patch(self.rom, base, vehicle_at=0x047F00)

    def dragon(self, frames):
        out = []
        for v in dump(self.rom)['vehicles']:
            if v['part'].startswith('82'):
                cells = {f'{d}{f}': v['cells'][f'{d}{min(f, 2)}'] for d in ('up', 'right', 'down', 'left')
                         for f in range(frames)}
                out.append({'part': v['part'], 'frames': frames, 'cells': cells})
        return {'format': FORMAT, 'vehicles': out}

    def test_vflip_table_rewritten(self):
        # マスタードラゴン 그림자(82-2)의 상하 반전 칸은 새 블록 자리로 01:C160 표를 다시 쓴다. 표는 24칸이다.
        doc = self.dragon(2)
        after = self.build(doc)
        self.assertEqual(dump(after)['vehicles'][-2:], normalized(doc, self.rom)['vehicles'][-2:])
        p = vehicle_part(after, '82-2')
        flips = sum(t.startswith(('v', 'hv')) for r in doc['vehicles'][1]['cells'].values() for row in r
                    for t in row.split())
        self.assertEqual(len(p['vflip']), flips)
        self.assertLessEqual(flips, 24)
        with self.assertRaises(ValueError):
            patch(self.rom, self.dragon(4), vehicle_at=0x04FEE0)


if __name__ == '__main__':
    unittest.main()
