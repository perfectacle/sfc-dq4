"""조사 보상 표와 필드 조사 코드의 예약 바이트·주소·입력 경계 검사."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch as mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dq5chestwrite import (FIELD_ADDRS, FIELD_CALL, FIELD_CODE, FIELD_TEMPLATE, FORMAT, TABLES, decode, dump, edits,
                           encode, encode_field, layout, map_dimensions, named, patch, read_field, world_block)
from dq5chestreloc import ABS, DB_SITES, LONG, ORIGINAL
from dq5map import Rom, lorom


def fixture():
    data = bytearray(0x180000)
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
                # 발밑은 필드 조사(A1)와 다른 보상: 같으면 12:EFB9 가 실내에서 빛 칸을 덮으므로 거부한다
                row[-4:-2] = b'\xa2\x00' if name == 'foot' else b'\xa1\x00'
                # 표마다 겹치지 않는 열림 비트(dq5chestreloc.flag_bits): 서랍 222C~, 발밑 2240~, 아래층 2228~, 두 칸 앞 2243~
                first = {'search': 0, 'foot': 0, 'lower': 0x18, 'ahead': 0x33}[name]
                row[-2:] = bytes([first + i // 8, 0x80 >> i % 8])
            data[at:at + size] = row
        if name != 'chests':
            at = lorom(start + count * size)
            data[at:at + 2] = b'\xff\xff'
    for name, sites in LONG.items():
        for site in sites:
            data[lorom(site) + 1:lorom(site) + 4] = ORIGINAL[name].to_bytes(3, 'little')
    for name, sites in ABS.items():
        for site, plus in sites:
            data[lorom(site) + 1:lorom(site) + 3] = (ORIGINAL[name] + plus & 0xFFFF).to_bytes(2, 'little')
    for name, sites in DB_SITES.items():
        for site in sites:
            data[lorom(site)] = ORIGINAL[name] >> 16
    for addr, token in zip(FIELD_ADDRS, FIELD_TEMPLATE):
        data[lorom(addr)] = FIELD_VALUES[token] if named(token) else int(token, 16)
    data[lorom(FIELD_CALL):lorom(FIELD_CALL) + 3] = bytes.fromhex('20 f2 e5')
    return Rom(data)


ROM = Path(__file__).resolve().parents[4] / 'rom/dq5.sfc'
FIELD_VALUES = {'x0': 10, 'x1': 0, 'X0': 12, 'X1': 0, 'y0': 0x20, 'y1': 1, 'Y0': 0x22, 'Y1': 1, 'r0': 0xA1, 'r1': 0,
                'i0': 0x30, 'm0': 0x08, 'a0': 0xC0, 'a1': 0x21, 'b0': 0x55, 'b1': 0}


def at(token, n=0):
    return FIELD_ADDRS[[i for i, t in enumerate(FIELD_TEMPLATE) if t == token][n]]


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

    @mock('dq5chestwrite.map_ids', return_value=[(0, i) for i in range(86)])
    @mock('dq5chestwrite.map_dimensions', return_value=(64, 64))
    def test_flag_rules_match_reloc(self, _, __):
        rom = fixture()
        self.assertEqual(len(patch(rom, {'format': FORMAT, 'search': [{'index': 0, 'flag_index': 0x1A}]})['writes']), 1)
        for row in ({'index': 1, 'flag_index': 0, 'mask': 0x80},   # 서랍 0 과 같은 비트
                    {'index': 1, 'flag_index': 0x0C},              # 7E:2238
                    {'index': 1, 'flag_index': 0x30}):             # 7E:225C 는 상자 비트 자리 밖
            with self.subTest(row=row), self.assertRaises(ValueError):
                patch(rom, {'format': FORMAT, 'search': [row]})

    @mock('dq5chestwrite.map_ids', return_value=[(0, i) for i in range(86)] + [(0x03, 0x04)])
    @mock('dq5chestwrite.map_dimensions', return_value=(64, 64))
    def test_fixed_code_bit_owner_keeps_its_bit(self, _, __):
        # 두 칸 앞 11 을 03/04 (10, 7) 에 두면 그 열림 비트 7E:223D & 08 은 12:AE9C 가 직접 본다
        start = lorom(TABLES['ahead'][0] + 11 * 8)
        data = bytearray(fixture().d)
        data[start:start + 4], data[start + 6:start + 8] = bytes((0x03, 0x04, 10, 7)), bytes((0x2D, 0x08))
        rom = Rom(data)
        patch(rom, {'format': FORMAT, 'ahead': [{'index': 11, 'reward': 0x38E}]})
        with self.assertRaises(ValueError):
            patch(rom, {'format': FORMAT, 'ahead': [{'index': 11, 'flag_index': 0x2E, 'mask': 0x02}]})

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
    @mock('dq5chestwrite.world_block', return_value=0x55)
    def test_full_roundtrip_and_manifest_orig(self, _, __, ___):
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


    def test_field_reads_pieces_and_moves_together(self):
        rom = fixture()
        raw = read_field(rom)
        self.assertEqual(dump(rom)['field'], [{'index': 0, 'x': 10, 'y': 0x120, 'width': 2, 'height': 2,
                                               'reward': 0xA1, 'flag_index': 0x30, 'mask': 0x08}])
        calls = []
        same = encode_field(raw, {'reward': 0x46C, 'x': 10}, lambda x, y: calls.append((x, y)) or 0x55)
        self.assertEqual([FIELD_TEMPLATE[i] for i in range(len(raw)) if raw[i] != same[i]], ['r0', 'r1'] * 2)
        self.assertEqual(calls, [(10, 0x120)])
        redrawn = encode_field(raw, {}, lambda x, y: 0x123)
        self.assertEqual([FIELD_TEMPLATE[i] for i in range(len(raw)) if raw[i] != redrawn[i]], ['b0', 'b1'] * 2)
        moved = encode_field(raw, {'x': 24, 'y': 168, 'flag_index': 0x22, 'mask': 4}, lambda x, y: 0x178)
        got = {t: v for t, v in zip(FIELD_TEMPLATE, moved) if named(t)}
        self.assertEqual((got['x0'], got['X0'], got['y0'], got['Y0'], got['y1']), (24, 26, 168, 170, 0))
        self.assertEqual((got['i0'], got['m0'], got['a0'], got['a1'], got['b0'], got['b1']),
                         (0x22, 4, 0xB2, 0x21, 0x78, 1))
        self.assertEqual(sum(1 for t in FIELD_TEMPLATE if t == 'x0'), 3)
        for change in ({'x': 11}, {'y': 511}, {'x': 512}, {'width': 3}, {'height': 1}, {'flag_index': 0x80},
                       {'mask': 0}, {'flag_index': 0x15, 'mask': 0x0C}, {'flag_index': 0x1A, 'mask': 1},
                       {'reward': 0xD000}, {'reward': True}, {'layer': 1}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                encode_field(raw, change, lambda x, y: 0)
        self.assertEqual(encode_field(raw, {'x': 24}, lambda x, y: 511)[FIELD_TEMPLATE.index('b1')], 1)
        # 10번째 비트가 켜진 칸은 00:CF50 이 되돌리지 못한다
        with self.assertRaisesRegex(ValueError, '512 이상'):
            encode_field(raw, {'x': 24}, lambda x, y: 512)

    @mock('dq5chestwrite.map_ids', return_value=[(0, i) for i in range(86)])
    @mock('dq5chestwrite.world_block', return_value=0x55)
    def test_field_manifest_and_schema(self, _, __):
        rom = fixture()
        writes = patch(rom, {'format': FORMAT, 'field': [{'index': 0, 'reward': 0x46C}]})['writes']
        # 줍고 나서 빛 칸을 되돌리는 12:EFB9 의 비교값도 함께 바뀐다
        self.assertEqual(writes, [{'at': at, 'hex': '6c 04', 'orig': 'a1 00', 'note': 'field 0'} for at in ('12:E61F', '12:EFBD')])
        moved = patch(rom, {'format': FORMAT, 'field': [{'index': 0, 'x': 24, 'flag_index': 0x31}]})['writes']
        self.assertEqual([w['at'] for w in moved], ['12:E5FD', '12:E602', '12:E615', '12:E627', '01:9FFC', '01:A01C',
                                                    '01:A05E', '12:EFC2'])
        for rows in ({}, [{'index': 1}], [{'index': 0}, {'index': 0}], [{'reward': 1}]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                edits(rom, {'format': FORMAT, 'field': rows})

    @mock('dq5chestwrite.map_ids', return_value=[(0, i) for i in range(86)])
    @mock('dq5chestwrite.map_dimensions', return_value=(64, 64))
    @mock('dq5chestwrite.world_block', return_value=0x55)
    def test_field_with_tables_high_byte_and_roundtrip(self, _, __, ___):
        rom = fixture()
        doc = {'format': FORMAT, 'search': [{'index': 1, 'reward': 0x432}], 'field': [{'index': 0, 'reward': 0x1A1}]}
        writes = patch(rom, doc)['writes']
        self.assertEqual([w['at'] for w in writes], ['1F:F5D4', '12:E620', '12:EFBE'])
        self.assertEqual(writes[1]['hex'], '01')
        data = bytearray(rom.d)
        for addr, new, _, _ in edits(rom, doc):
            data[lorom(addr):lorom(addr) + len(new)] = new
        self.assertEqual(dump(Rom(data))['field'][0]['reward'], 0x1A1)
        with self.assertRaises(ValueError):
            edits(rom, {'format': FORMAT, 'field': ['x']})

    @mock('dq5chestwrite.map_ids', return_value=[(0, i) for i in range(86)])
    @mock('dq5chestwrite.map_dimensions', return_value=(64, 64))
    @mock('dq5chestwrite.world_block', return_value=0x55)
    def test_foot_reward_must_differ_from_field(self, _, __, ___):
        rom = fixture()
        for doc in ({'foot': [{'index': 3, 'reward': 0xA1}]}, {'field': [{'index': 0, 'reward': 0xA2}]},
                    {'foot': [{'index': 0, 'reward': 0x33}], 'field': [{'index': 0, 'reward': 0x33}]}):
            with self.subTest(doc=doc), self.assertRaisesRegex(ValueError, '12:EFB9'):
                edits(rom, {'format': FORMAT, **doc})
        # 필드 보상을 옮기면 그 값을 쓰던 발밑은 받는다
        self.assertTrue(edits(rom, {'format': FORMAT, 'foot': [{'index': 3, 'reward': 0xA1}],
                                    'field': [{'index': 0, 'reward': 0x46C}]}))
        # 필드 코드를 다른 패치가 바꾼 롬은 비교할 보상을 모르므로 보지 않는다
        self.assertTrue(edits(poke(rom, FIELD_CODE, 0xE2), {'format': FORMAT, 'foot': [{'index': 3, 'reward': 0xA1}]}))

    @mock('dq5chestwrite.map_ids', return_value=[(0, i) for i in range(86)])
    def test_tables_ignore_changed_field_code(self, _):
        rom = poke(fixture(), FIELD_CODE, 0xE2)
        self.assertNotIn('field', dump(rom, False))
        self.assertEqual(len(patch(rom, {'format': FORMAT, 'chests': [{'index': 0, 'reward': 1}]})['writes']), 1)
        with self.assertRaises(ValueError):
            edits(rom, {'format': FORMAT, 'field': [{'index': 0, 'reward': 1}]})

    def test_moved_tables_are_refused(self):
        rom = poke(fixture(), DB_SITES['search'][0], 0x3F)
        with self.assertRaises(ValueError):
            dump(rom)

    def test_world_block_reads_tenth_bit_plane(self):
        """가짜 롬: 지도는 모두 블록 05, 9번째 비트 없음, 10번째 비트 평면은 칸 (11,83) 만 켬."""
        import dq5fieldwrite as fw
        d = bytearray(0x200000)

        def put(at, raw):
            d[lorom(at):lorom(at) + len(raw)] = raw
        runs = lambda value, n: bytes([0xFF, value]) * (n // 128) + b'\x80'
        put(0x308000, runs(0, 0x2000))                    # 9번째 비트 8KB
        put(0x309000, runs(5, 0x10000))                   # 지도 64KB
        put(fw.LOADERS[0], bytes.fromhex('a9308d744348aba20080204fa6') + bytes.fromhex('a9308d744348aba20090204fa6'))
        hook, plane = 0x318000, 0x319000
        put(fw.BIT9_SITES[0], b'\x22' + hook.to_bytes(3, 'little'))
        put(hook, fw.bit9_hook([plane, None, None]))
        i = 83 * 256 + 11
        put(plane + (i >> 3), bytes([0x80 >> (i & 7)]))
        rom = Rom(bytes(d))
        self.assertEqual(world_block(rom, 22, 166), 0x205)        # 블록 좌표 (11,83)
        self.assertEqual(world_block(rom, 24, 166), 0x05)

    @unittest.skipUnless(ROM.is_file(), '롬 없음')
    def test_world_block_reads_loader_chunks(self):
        rom = Rom(ROM.read_bytes())
        self.assertEqual(world_block(rom, 22, 166), 0xCA)
        self.assertEqual(world_block(rom, 25, 169), 0x178)

    def test_field_code_must_match_template(self):
        rom = fixture()
        for addr, value in ((FIELD_CALL + 1, 0), (FIELD_CODE, 0xE2), (at('i0', 1), 0x31), (at('m0', 3), 0x10),
                            (at('x0', 1), 12), (at('a0'), 0xC1), (at('X0'), 13), (at('x0'), 11), (at('x0', 1), 11),
                            (at('01', 0), 0)):
            with self.subTest(addr=hex(addr)), self.assertRaises(ValueError):
                dump(poke(rom, addr, value))


if __name__ == '__main__':
    unittest.main()
