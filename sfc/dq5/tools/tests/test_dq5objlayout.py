"""칸 배치 쓰기: 칸 글, 맵 OBJ 물체 표 늘리기와 칸 바이트 옮기기, 탈것·세트 칸 제자리 쓰기."""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dq5sprite as S  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402
from dq5objlayout import (FORMAT, REGION_END, SCENES, TABLE, VEHICLE_FRAMES, VEHICLE_PARTS, address,  # noqa: E402
                          dump, normalized, object_entry, parse_token, patch, scene_layout, token, vehicle_part)


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
            table = {'81-2': 0x01C42D, '82-2': 0x01C160}[name]
            put(data, site['vflip'], table.to_bytes(3, 'little'))
            put(data, table, bytes(part['vflip']) + b'\xff')
    for vid, at in VEHICLE_FRAMES.items():
        if at:
            put(data, at, bytes([0x81 if vid == 0x80 else 0x82]))
    scene = SCENES['82-1']
    for at, value in ((scene['land']['frame'], 7), (scene['land']['last'], 0x87), (scene['tenkuu']['stride'], 0x80),
                      (scene['tenkuu']['last'], 0x83)):
        put(data, at, bytes([value]))
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

    def test_vehicle_bank(self):
        # 탈것 루틴은 칸 표 뱅크를 데이터 뱅크로 두고 STX $1997 을 써서 7E:1997 이 비치는 뱅크만 받는다.
        for ok in ('04:FEE0', '3F:8000', '84:8000', 'BF:FFFF'):
            with self.subTest(ok=ok):
                self.assertEqual(address(ok, any_bank=True), int(ok.replace(':', ''), 16))
        for bad in ('40:8000', '7D:FEE0', '7E:8000', 'C0:8000', '04:7FFF'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                address(bad, any_bank=True)


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

    def test_cell_limit(self):
        # 04/06 낮 인물 세트 30개면 일행 셋과 함께 목록 끝이 8060 + 60 × 33 = 8CC0. 남은 340 바이트(416칸)까지 받는다.
        base = self.doc['objects'][0]
        fits = dict(base, cells=[' '.join(['00'] * 63)] * 6)          # 378칸 → 8CC0 + 2 × 378 = 8FB4
        wide = dict(base, cells=[' '.join(['00'] * 63)] * 7)          # 441칸 → 9032
        with mock.patch('dq5objlayout.map_people', return_value={}), \
                mock.patch('dq5objlayout.map_sets', return_value={(0x04, 0x06, False): 30}):
            self.writes(dict(self.doc, objects=[fits] + self.doc['objects'][1:]), at=0x16FE10)
            with self.assertRaisesRegex(ValueError, '슬롯 칸 목록 끝'):
                self.writes(dict(self.doc, objects=[wide] + self.doc['objects'][1:]), at=0x16FE10)
            # 밤 전용이면 낮 목록에 들지 않는다(밤 인물 세트는 0 이라 넘지 않음).
            self.writes(dict(self.doc, objects=[dict(wide, cond='night')] + self.doc['objects'][1:]), at=0x16FE10)

    def test_table_limit(self):
        most = (REGION_END - TABLE - 1) // 9
        self.assertEqual(most, 159)
        # 필드 물체를 세계 열 곳에 나눠(세계마다 16개, 슬롯 8 + 16 = 0x18) 표 한도만 걸리게 한다.
        one = dict(self.doc['objects'][1], cells=['00'])
        rows = [dict(one, map=f'field{i % 10}') for i in range(most + 1)]
        self.assertEqual([x['at'] for x in self.writes(dict(self.doc, objects=rows[:most]))], ['16:F862'])
        with self.assertRaises(ValueError):
            self.writes(dict(self.doc, objects=rows), at=0x16FE10)

    def test_field_slot_limit(self):
        # 필드는 슬롯 8 부터 그 세계의 물체만 놓는다. 세계 0 에 낮 물체 24개(8 + 24 = 0x20)는 받고 25개는 거부한다.
        one = dict(self.doc['objects'][1], cells=['00'])
        self.writes(dict(self.doc, objects=[one] * 24))
        with self.assertRaisesRegex(ValueError, 'field0 낮'):
            self.writes(dict(self.doc, objects=[one] * 25))
        # 다른 세계·밤 전용 물체는 세계 0 낮 수에 들지 않는다.
        self.writes(dict(self.doc, objects=[one] * 24 + [dict(one, map='field1'), dict(one, cond='night')]))

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
        for at in (0x047F00, 0x408000, 0x7DFEE0):
            with self.subTest(at=hex(at)), self.assertRaises(ValueError):
                patch(self.rom, base, vehicle_at=at)

    def dragon(self, frames, size=None):
        """マスタードラゴン 두 부분. 새 프레임은 프레임 2 의 칸, size 면 부분 1 줄마다 첫 칸을 더하고 마지막 줄을 한 번 더."""
        out = []
        for v in dump(self.rom)['vehicles']:
            if v['part'].startswith('82'):
                cells = {f'{d}{f}': v['cells'][f'{d}{min(f, 2)}'] for d in ('up', 'right', 'down', 'left')
                         for f in range(frames)}
                cells |= {k: rows for k, rows in v['cells'].items() if k.startswith(('land', 'tenkuu'))}
                row = {'part': v['part'], 'frames': frames, 'cells': cells}
                if size and v['part'] == '82-1':
                    row['size'] = size
                    row['cells'] = {k: [r + ' ' + r.split()[0] for r in rows] + [rows[-1] + ' ' + rows[-1].split()[0]]
                                    for k, rows in cells.items()}
                out.append(row)
        return {'format': FORMAT, 'vehicles': out}

    def scene_firsts(self, rom):
        p = vehicle_part(rom, '82-1')
        per = p['cols'] * p['rows']
        return {k: idx[0] // per for k, idx in p['scene'].items()}

    def test_dragon_scene_blocks(self):
        # 원래 착륙은 블록 16·15, 天空城 은 12~15 이고(15 를 함께 씀) 문서에 열쇠로 나온다.
        self.assertEqual(self.scene_firsts(self.rom), {'land0': 16, 'land1': 15, 'tenkuu0': 12, 'tenkuu1': 13,
                                                       'tenkuu2': 14, 'tenkuu3': 15})
        self.assertEqual(vehicle_part(self.rom, '82-1')['used'], 17 * 16)

    def test_dragon_four_frames(self):
        # 4프레임: 걷기 0~15, 착륙 X = 5 로 17·16, 天空城 37C7 = C0 으로 18~21. 그림자 상하 반전 32칸은 원래 표(24칸)보다
        # 길어 칸 표 뒤에 두고 01:C132 의 피연산자를 고친다.
        doc = self.dragon(4)
        after = self.build(doc, 0x0BFBB0)
        p1, p2 = vehicle_part(after, '82-1'), vehicle_part(after, '82-2')
        self.assertEqual((p1['frames'], p1['dir'], p1['copied'] // 16), (4, 4 * 16 * 2, 22))
        self.assertEqual(self.scene_firsts(after), {'land0': 17, 'land1': 16, 'tenkuu0': 18, 'tenkuu1': 19,
                                                    'tenkuu2': 20, 'tenkuu3': 21})
        land, tenkuu = SCENES['82-1']['land'], SCENES['82-1']['tenkuu']
        self.assertEqual((after.u8(land['frame']), after.u8(land['last']), after.u8(tenkuu['stride']),
                          after.u8(tenkuu['last'])), (5, 0x85, 0xC0, 0x83))
        self.assertEqual(len(p2['vflip']), 32)
        self.assertEqual(after.u24(VEHICLE_PARTS['82-2']['vflip']), 0x0BFBB0 + 22 * 16 + 16 * 4)
        self.assertEqual(dump(after)['vehicles'], normalized(doc, self.rom)['vehicles'])
        # 프레임 수가 그대로면 제자리에 쓴다.
        self.assertEqual(len(patch(self.rom, self.dragon(3))['writes']), 0)

    def test_relocated_round_trip_is_empty(self):
        # 칸 표를 옮긴 롬에 그 롬의 dump 나 같은 문서를 다시 넣으면 칸 수가 그대로라 제자리 쓰기 0개다.
        doc = self.dragon(4)
        after = self.build(doc, 0x0BFBB0)
        self.assertEqual(patch(after, dump(after))['writes'], [])
        self.assertEqual(patch(after, doc, vehicle_at=0x0BFBB0)['writes'], [])

    def test_scene_layout(self):
        # 4x4 マスタードラゴン(天空城 4블록): 프레임 수마다 착륙 X·天空城 간격 S. 6프레임이면 S 가 한 바이트를 넘는다.
        for frames, want in ((1, (2, 0x40)), (2, (8, 0x60)), (4, (5, 0xC0)), (5, (0xB, 0xE0))):
            with self.subTest(frames=frames):
                self.assertEqual(scene_layout(self.rom, '82-1', frames, 16)[:2], want)
        with self.assertRaises(ValueError):
            scene_layout(self.rom, '82-1', 6, 16)

    def test_dragon_size(self):
        # 5x5 · 3프레임: 天空城 37C7 = C8(블록 12~15), 착륙 X = 8(블록 17·16).
        doc = self.dragon(3, '5x5')
        after = self.build(doc, 0x0BFBB0)
        self.assertEqual(vehicle_part(after, '82-1')['cols'], 5)
        self.assertEqual(self.scene_firsts(after), {'land0': 17, 'land1': 16, 'tenkuu0': 12, 'tenkuu1': 13,
                                                    'tenkuu2': 14, 'tenkuu3': 15})
        self.assertEqual(after.u8(SCENES['82-1']['tenkuu']['stride']), 0xC8)
        self.assertEqual(dump(after)['vehicles'], normalized(doc, self.rom)['vehicles'])
        # 4프레임 5x5 면 天空城 블록을 걷기 블록 뒤에 두는 간격(3 × 6 블록 × 50)이 한 바이트를 넘는다.
        with self.assertRaises(ValueError):
            patch(self.rom, self.dragon(4, '5x5'), vehicle_at=0x0BFBB0)
        # 부분 1 을 바꾸면 장면 블록 열쇠도 모두 있어야 한다.
        missing = self.dragon(4)
        del missing['vehicles'][0]['cells']['tenkuu3']
        with self.assertRaises(ValueError):
            patch(self.rom, missing, vehicle_at=0x0BFBB0)

    def test_dragon_scene_in_place(self):
        # 칸 수가 그대로면 장면 블록도 제자리에 쓴다. 블록 15 는 tenkuu3·land1 이 함께 써서 값이 같아야 한다.
        v = next(x for x in dump(self.rom)['vehicles'] if x['part'] == '82-1')
        rows = v['cells']['tenkuu0']
        changed = ['h3F ' + ' '.join(rows[0].split()[1:])] + rows[1:]
        doc = {'format': FORMAT, 'vehicles': [{'part': '82-1', 'cells': {'tenkuu0': changed}}]}
        w = patch(self.rom, doc)['writes']
        self.assertEqual(len(w), 1)
        self.assertEqual(dump(self.build(doc, None))['vehicles'], normalized(doc, self.rom)['vehicles'])
        with self.assertRaises(ValueError):
            patch(self.rom, {'format': FORMAT, 'vehicles': [{'part': '82-1', 'cells': {'land1': changed}}]})
        both = {'format': FORMAT, 'vehicles': [{'part': '82-1', 'cells': {'land1': changed, 'tenkuu3': changed}}]}
        self.assertEqual(len(patch(self.rom, both)['writes']), 1)

    def test_in_place_keeps_scene_blocks(self):
        # 82-2 칸 표가 82-1 이 그리는 블록 16(land0)에 걸치면 그 칸을 바꾸는 제자리 쓰기를 거부하고, 블록 17 부터면 받는다.
        site, head = VEHICLE_PARTS['82-2'], vehicle_part(self.rom, '82-1')['table']
        for block, ok in ((16, False), (17, True)):
            put(self.rom.d, site['ldy'], ((head + block * 16) & 0xFFFF).to_bytes(2, 'little'))
            v = next(x for x in dump(self.rom)['vehicles'] if x['part'] == '82-2')
            row = v['cells']['up0'][0].split()
            row[0] = 'h3F' if row[0] != 'h3F' else '3F'
            cells = {'up0': [' '.join(row)] + v['cells']['up0'][1:]}
            doc = {'format': FORMAT, 'vehicles': [{'part': '82-2', 'cells': cells}]}
            with self.subTest(block=block):
                if ok:
                    self.assertEqual(len(patch(self.rom, doc)['writes']), 1)
                else:
                    with self.assertRaises(ValueError):
                        patch(self.rom, doc)

    def tenkuu_shadow(self):
        """天空城 그림자(81-2)를 4x2 에서 4x3 으로. 상하 반전 칸 셋(0·1·6)."""
        return {'part': '81-2', 'size': '4x3', 'cells': {'all': ['v00 hv01 02 03', '04 05 v06 07', '08 09 0a 0b']}}

    def test_vflip_table_rewritten(self):
        # 칸 수를 바꾸면 01:C42D 표를 새 칸 오프셋(칸 × 2)으로 다시 쓰고 FF 로 끝낸다. 표는 8칸이다.
        doc = {'format': FORMAT, 'vehicles': [self.tenkuu_shadow()]}
        w = patch(self.rom, doc, vehicle_at=0x04FEE0)['writes']
        table = next(x for x in w if x['at'] == '01:C42D')
        self.assertEqual(bytes.fromhex(table['hex']), bytes([0, 2, 12, 0xFF]))
        after = self.build(doc)
        self.assertEqual(vehicle_part(after, '81-2')['vflip'], {0, 1, 6})
        self.assertEqual(dump(after)['vehicles'], normalized(doc, self.rom)['vehicles'])
        # 원래 표(8칸)보다 많으면 칸 표 뒤에 두고 01:C40D 의 피연산자를 고친다.
        many = dict(self.tenkuu_shadow(), cells={'all': [' '.join(f'v{i:02X}' for i in range(r * 4, r * 4 + 4))
                                                         for r in range(3)]})
        doc = {'format': FORMAT, 'vehicles': [many]}
        after = self.build(doc)
        self.assertEqual(vehicle_part(after, '81-2')['vflip'], set(range(12)))
        self.assertEqual(after.u24(VEHICLE_PARTS['81-2']['vflip']), 0x04FEE0 + 32 + 12)
        self.assertEqual(dump(after)['vehicles'], normalized(doc, self.rom)['vehicles'])

    def test_vflip_offset_limit(self):
        # 상하 반전 칸 오프셋은 칸 × 2 한 바이트라 칸 127(FE)까지다. 12x11 의 칸 130 은 거부한다.
        # 한 블록 132칸은 OAM 한도에도 걸리므로 그 검사를 늦춰 이 규칙만 본다(여러 블록을 옮기는 82-2 는 OAM 안에서 닿음).
        cells = [' '.join(('v' if r * 12 + c == 130 else '') + f'{(r * 12 + c) % 0x80:02X}' for c in range(12))
                 for r in range(11)]
        doc = {'format': FORMAT, 'vehicles': [{'part': '81-2', 'size': '12x11', 'cells': {'all': cells}}]}
        with mock.patch('dq5objlayout.OAM_LIMIT', 0x200):
            with self.assertRaisesRegex(ValueError, 'FE'):
                patch(self.rom, doc, vehicle_at=0x04FEE0)
            cells[10] = cells[10].replace('v', '')
            cells[0] = 'v' + cells[0]
            self.assertTrue(patch(self.rom, doc, vehicle_at=0x04FEE0)['writes'])

    def test_vflip_offset_limit_dragon(self):
        # 여러 블록을 옮기는 82-2 는 OAM 한도 안에서 칸 127 을 넘는다. 9프레임(82-1 3x3, 82-2 2x2)이면 그림자 칸은
        # 4 × 9 × 4 = 144 이고, left5 의 셋째 칸이 칸 130 이다(방향 간격 36칸, 프레임 간격 4칸).
        def doc(v_key):
            rows = []
            for part, n in (('82-1', 3), ('82-2', 2)):
                keys = [f'{d}{f}' for d in ('up', 'right', 'down', 'left') for f in range(9)]
                if part == '82-1':
                    keys += ['land0', 'land1', 'tenkuu0', 'tenkuu1', 'tenkuu2', 'tenkuu3']
                cells = {k: [' '.join(f'{(r * n + c) % 0x10:02X}' for c in range(n)) for r in range(n)] for k in keys}
                if part == '82-2':
                    cells[v_key] = ['00 01', 'v02 03']
                rows.append({'part': part, 'size': f'{n}x{n}', 'frames': 9, 'cells': cells})
            return {'format': FORMAT, 'vehicles': rows}
        with self.assertRaisesRegex(ValueError, 'FE'):
            patch(self.rom, doc('left5'), vehicle_at=0x0BFBB0)
        self.assertTrue(patch(self.rom, doc('up0'), vehicle_at=0x0BFBB0)['writes'])

    def test_oam_limit(self):
        # 칸 수를 바꾼 탈것은 부분마다 한 블록의 칸 합 + 주인공 8 이 128 을 넘으면 거부한다(1프레임 12x9 + 3x3 + 3x1 = 120).
        def doc(size3):
            out = []
            for part, (c, r) in (('80-1', (12, 9)), ('80-2', (3, 3)), ('80-3', size3)):
                rows = [' '.join(f'{(i * c + j) % 0x30:02x}' for j in range(c)) for i in range(r)]
                out.append({'part': part, 'size': f'{c}x{r}', 'frames': 1,
                            'cells': {f'{d}0': rows for d in ('up', 'right', 'down', 'left')}})
            return {'format': FORMAT, 'vehicles': out}
        self.assertTrue(patch(self.rom, doc((3, 1)), vehicle_at=0x0BFBB0)['writes'])
        with self.assertRaisesRegex(ValueError, 'OAM'):
            patch(self.rom, doc((4, 1)), vehicle_at=0x0BFBB0)

    def test_vehicle_at_past_rom_end(self):
        # 1.5MB 롬에서 --vehicle-at 30:8000 이면 롬을 2MB 로 늘려 빌드한다.
        from dq5objlayout import built
        rom = Rom(bytes(self.rom.d[:0x180000]))
        after = built(rom, patch(rom, carpet_doc(rom, 3), vehicle_at=0x308000))
        self.assertEqual(len(after.d), 0x200000)
        self.assertEqual(vehicle_part(after, '80-1')['table'], 0x308000)
        self.assertEqual(dump(after)['vehicles'], normalized(carpet_doc(rom, 3), rom)['vehicles'])

    def test_two_vehicles_in_one_doc(self):
        # 탈것 번호 차례로 --vehicle-at 뒤에 이어 둔다: 양탄자 3프레임(216칸) 다음에 天空城 부분 1(32칸)·2(12칸).
        doc = carpet_doc(self.rom, 3)
        doc['vehicles'].append(self.tenkuu_shadow())
        after = self.build(doc)
        self.assertEqual(vehicle_part(after, '80-1')['table'], 0x04FEE0)
        self.assertEqual(vehicle_part(after, '81-1')['table'], 0x04FEE0 + 216)
        self.assertEqual(vehicle_part(after, '81-2')['table'], 0x04FEE0 + 216 + 32)
        self.assertEqual(vehicle_part(after, '81-1')['bytes'], vehicle_part(self.rom, '81-1')['bytes'])
        self.assertEqual(dump(after)['vehicles'], normalized(doc, self.rom)['vehicles'])
        self.assertEqual(vehicle_part(after, '82-1')['table'], vehicle_part(self.rom, '82-1')['table'])


if __name__ == '__main__':
    unittest.main()
