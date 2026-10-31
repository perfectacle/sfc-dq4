"""보물상자·조사 보상 표 옮기기의 자리 찾기·자리 규칙·입력 검사."""
import argparse
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch as mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dq5chestreloc import (ABS, DB_SITES, FORMAT, LONG, MAX_CHESTS, ORIGINAL, ORIGINAL_BYTES, address, flag_bits,
                           locate, original_spans, parse, placement, read, rom_size, row_encode, serialize, writes_for)
from dq5chestwrite import TABLES
from dq5map import Rom, lorom
from test_dq5chestwrite import ROM, fixture, poke

# 맵 (00, i) 마다 상자 수. 합은 상자 내용물 표의 행 수(161)
COUNTS = [TABLES['chests'][1] - 82] + [1] * 82


def row(name, **values):
    base = {'group': 0, 'map': 1, 'x': 2, 'y': 3, 'reward': 0xA1, 'flag_index': 3, 'mask': 0x80}
    extra = {'search': {'unused': 1}, 'foot': {'layer': 1}}.get(name, {})
    return base | extra | values


def counted():
    """fixture() 의 상자 맵 연결에 COUNTS 를 적은 롬. 표 여섯을 parse 해 그대로 다시 쓸 수 있다."""
    data = bytearray(fixture().d)
    for i, count in enumerate(COUNTS):
        data[lorom(ORIGINAL['chest_maps'] + i * 3 + 2)] = count
    return Rom(data)


def fake_maps(case, *extra):
    """counted() 의 표가 가리키는 맵(00/00~00/55 와 extra)과 맵 크기·상자 칸을 흉내 낸다."""
    ids = [(0, i) for i in range(86)] + list(extra)
    cells = {(0, i): count for i, count in enumerate(COUNTS)}
    for module in ('dq5chestreloc', 'dq5chestwrite'):
        case.enterContext(mock(f'{module}.map_ids', return_value=ids))
        case.enterContext(mock(f'{module}.map_dimensions', return_value=(64, 64)))
    case.enterContext(mock('dq5chestreloc.chests', side_effect=lambda rom, group, number, start: [None] * cells.get(
        (group, number), 0)))


class ChestRelocTests(unittest.TestCase):
    def test_locate_reads_every_site(self):
        rom = fixture()
        self.assertEqual(locate(rom), ORIGINAL)
        site, plus = ABS['search'][3]
        data = bytearray(rom.d)
        data[lorom(site) + 1] += 1
        with self.assertRaises(ValueError):
            locate(Rom(data))
        with self.assertRaises(ValueError):
            locate(poke(rom, LONG['ahead'][2] + 3, 0x1F))
        # 상자 맵 연결의 DB 즉값 셋 가운데 하나만 다르면 거부한다
        with self.assertRaises(ValueError):
            locate(poke(rom, 0x25FAB5, 0x1F))
        moved = rom
        for site in DB_SITES['chest_maps']:
            moved = poke(moved, site, 0x3F)
        self.assertEqual(locate(moved)['chest_maps'], 0x3F0000 | ORIGINAL['chest_maps'] & 0xFFFF)

    def test_row_fields_and_bounds(self):
        self.assertEqual(row_encode('search', row('search'), 's'), bytes.fromhex('00 01 02 03 01 a1 00 03 80'))
        self.assertEqual(row_encode('foot', row('foot', layer=2), 'f')[4], 2)
        self.assertEqual(row_encode('chest_maps', {'group': 1, 'map': 2, 'count': 3}, 'm'), b'\x01\x02\x03')
        for name, value in (('search', row('search', unused=256)), ('ahead', row('ahead', mask=0)),
                            ('lower', row('lower', reward=0xD00A)), ('ahead', row('search')),
                            ('chest_maps', {'group': 1, 'map': 2, 'count': 0}), ('chests', {'reward': True})):
            with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                row_encode(name, value, name)

    @mock('dq5chestreloc.map_ids', return_value=[(0, 1), (0, 2)])
    @mock('dq5chestreloc.map_dimensions', return_value=(8, 8))
    def test_serialize_counts_duplicates_and_terminators(self, _, __):
        rom = fixture()
        doc = {'format': FORMAT, 'chests': [{'reward': 1}] * 3, 'chest_maps': [{'group': 0, 'map': 1, 'count': 3}],
               'search': [row('search')], 'foot': [], 'ahead': [row('ahead')], 'lower': []}
        blobs = serialize(rom, doc)
        self.assertEqual(blobs['chests'], b'\x01\x00' * 3)
        self.assertEqual(blobs['foot'], b'\xff\xff')
        self.assertEqual(blobs['ahead'][-2:], b'\xff\xff')
        bad = [dict(doc, chests=[{'reward': 1}] * 2),
               dict(doc, chest_maps=[{'group': 0, 'map': 1, 'count': MAX_CHESTS + 1}],
                    chests=[{'reward': 1}] * (MAX_CHESTS + 1)),
               dict(doc, ahead=[row('ahead'), row('ahead', reward=2)]),
               dict(doc, foot=[row('foot', x=8)]), dict(doc, search=[row('search', map=3)]),
               dict(doc, chest_maps=[{'group': 0x50, 'map': 1, 'count': 3}]), {k: v for k, v in doc.items() if k != 'lower'}]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                serialize(rom, value)

    @mock('dq5chestreloc.map_ids', return_value=[(0, 1), (0x11, 1)])
    @mock('dq5chestreloc.map_dimensions', return_value=(8, 8))
    def test_chests_up_to_256(self, _, __):
        rom = fixture()
        doc = {'format': FORMAT, 'chests': [{'reward': 1}] * MAX_CHESTS,
               'chest_maps': [{'group': 0, 'map': 1, 'count': 128}, {'group': 0x11, 'map': 1, 'count': 128}],
               'search': [], 'foot': [], 'ahead': [], 'lower': []}
        self.assertEqual(MAX_CHESTS, 256)
        serialize(rom, doc)
        self.assertEqual(flag_bits(doc)[0x222F, 0x01], '일반 상자 255')
        over = dict(doc, chests=[{'reward': 1}] * 257,
                    chest_maps=[{'group': 0, 'map': 1, 'count': 129}, {'group': 0x11, 'map': 1, 'count': 128}])
        with self.assertRaises(ValueError):
            serialize(rom, over)
        # 상자 224 부터는 서랍 비트 222C 와 같은 바이트다
        with self.assertRaisesRegex(ValueError, '일반 상자 224'):
            serialize(rom, dict(doc, search=[row('search', map=1, flag_index=0, mask=0x80)]))

    def test_flag_bits_reject_shared_and_outside_bits(self):
        doc = {'chests': [{'reward': 1}] * 3, 'search': [], 'foot': [], 'ahead': [], 'lower': []}
        for name, value, words in (
                ('lower', row('lower', flag_index=0, mask=0x40), '일반 상자 1'),
                ('ahead', row('ahead', flag_index=0, mask=0x20), '일반 상자 2'),
                ('ahead', row('ahead', flag_index=0x80, mask=1), '7F 이하'),
                ('lower', row('lower', flag_index=0x98), '7F 이하'),
                ('foot', row('foot', flag_index=0x10, mask=1), '7E:2250'),
                ('search', row('search', flag_index=0x24), '7E:2250')):
            with self.subTest(name=name, value=value), self.assertRaisesRegex(ValueError, words):
                flag_bits(dict(doc, **{name: [value]}))
        # 서랍 10 과 두 칸 앞 2C 는 같은 7E:223C 다
        with self.assertRaisesRegex(ValueError, r'search\[0\]'):
            flag_bits(dict(doc, search=[row('search', flag_index=0x10, mask=1)],
                           ahead=[row('ahead', flag_index=0x2C, mask=1)]))
        self.assertEqual(flag_bits(dict(doc, lower=[row('lower', flag_index=0x19, mask=8)]))[0x2229, 8], 'lower[0]')

    def test_reserved_bits_belong_to_their_ahead_rows(self):
        doc = {'chests': [], 'search': [], 'foot': [], 'ahead': [], 'lower': []}
        owner = row('ahead', group=0x03, map=0x04, x=10, y=7, flag_index=0x2D, mask=0x08)
        self.assertEqual(flag_bits(dict(doc, ahead=[owner]))[0x223D, 0x08], 'ahead[0]')
        for value in (dict(doc, search=[row('search', flag_index=0x0C, mask=0x10)]),         # 7E:2238, 21:8C2F
                      dict(doc, ahead=[row('ahead', flag_index=0x2C, mask=0x80)]),           # 06:D3CB 가 보는 비트
                      dict(doc, lower=[row('lower', flag_index=0x2D, mask=0x20)]),           # 12:ADB0
                      dict(doc, ahead=[dict(owner, mask=0x04)]),                             # 주인의 비트를 옮김
                      dict(doc, ahead=[dict(owner, flag_index=0x30, mask=0x01)])):
            with self.subTest(value=value), self.assertRaises(ValueError):
                flag_bits(value)

    @mock('dq5chestreloc.map_ids', return_value=[(0, 1)])
    @mock('dq5chestreloc.map_dimensions', return_value=(64, 64))
    def test_eight_bit_indexed_tables_have_row_limits(self, _, __):
        rom = fixture()
        doc = {'format': FORMAT, 'chests': [], 'chest_maps': [], 'search': [], 'foot': [], 'ahead': [], 'lower': []}

        def rows(name, n):
            # 행마다 다른 칸·다른 비트(아래층·두 칸 앞은 2210 + 30~, 발밑은 2240 + 0~)
            first = 0 if name == 'foot' else 0x30 if name == 'ahead' else 0x18
            return [row(name, x=i % 64, y=i // 64, flag_index=first + i // 8, mask=0x80 >> i % 8) for i in range(n)]
        for name, limit in (('foot', 28), ('ahead', 31), ('lower', 31)):
            with self.subTest(name=name):
                serialize(rom, dict(doc, **{name: rows(name, limit)}))
                with self.assertRaisesRegex(ValueError, '8비트 색인'):
                    serialize(rom, dict(doc, **{name: rows(name, limit + 1)}))

    def test_placement_bank_rules(self):
        rom = fixture()
        sizes = {'search': 10, 'foot': 10, 'chests': 10, 'ahead': 10, 'chest_maps': 10, 'lower': 10}
        at = placement(rom, sizes, {'search': 0x3F8000, 'ahead': 0x7D8000, 'lower': 0x1EF435 + 20}, {})
        self.assertEqual((at['search'], at['ahead'], at['chest_maps']), (0x3F8000, 0x7D8000, ORIGINAL['chest_maps']))
        at = placement(rom, sizes, {'chest_maps': 0x3F8000, 'lower': 0x3F9000}, {})
        self.assertEqual((at['chest_maps'], at['lower']), (0x3F8000, 0x3F9000))
        for wrong in ({'search': 0x408000}, {'foot': 0x408000}, {'chest_maps': 0x408000}, {'lower': 0x408000},
                      {'lower': 0x1F8000},
                      {'chests': 0x7E8000}, {'ahead': 0x3FFFF8}, {'chests': 0x1E8000},
                      {'ahead': ORIGINAL['chests']}):
            with self.subTest(wrong=wrong), self.assertRaises(ValueError):
                placement(rom, sizes, wrong, {})
        self.assertEqual((rom_size([0x1E8000]), rom_size([0x3F8000]), rom_size([0x5F8000]), rom_size([0x7D8000])),
                         (0, 2, 3, 4))

    def test_address_accepts_cpu_only(self):
        self.assertEqual(address('BF:9000'), 0x3F9000)
        for text in ('0x1000', '3F9000', '3F:12'):
            with self.subTest(text=text), self.assertRaises(argparse.ArgumentTypeError):
                address(text)


class ChestTableRomTests(unittest.TestCase):
    """표 여섯을 parse 해 고쳐 쓰기. 합성 롬에서 맵 목록·크기·상자 칸은 흉내 낸다."""
    def setUp(self):
        self.rom = counted()
        fake_maps(self, (0x17, 0))

    def test_grow_moves_operands_and_owns_old_spans(self):
        rom = self.rom
        doc = parse(rom)
        self.assertEqual(writes_for(rom, doc)[0], [])
        doc['ahead'].append(row('ahead', group=0x17, map=0, x=9, y=9, flag_index=0x2E, mask=4))
        writes, mb = writes_for(rom, doc, {'ahead': 0x3FB000})
        self.assertEqual(mb, 2)
        sites = {addr: new for addr, new, _, _ in writes}
        for site in LONG['ahead']:
            self.assertEqual(sites[site + 1], bytes.fromhex('00 b0 3f'))
        self.assertIn(ORIGINAL['ahead'], sites)
        self.assertEqual(len(sites[ORIGINAL['ahead']]), ORIGINAL_BYTES['ahead'])
        with self.assertRaises(ValueError):
            writes_for(rom, doc)
        self.assertNotIn(DB_SITES['search'][0], sites)
        owned = sorted((a, a + len(new)) for a, new, _, _ in writes if a >> 16 == 0x1E or a >> 16 == 0x1F)
        for lo, hi in original_spans().values():
            covered = [(max(a, lo), min(b, hi)) for a, b in owned if a < hi and b > lo]
            self.assertEqual(sum(b - a for a, b in covered), hi - lo)

    def test_rules_cells_flags_and_merged_spans(self):
        rom = self.rom
        doc = parse(rom)
        self.assertEqual(doc['search'][0]['unused'], read(rom, ORIGINAL['search'] + 4, 1)[0])
        cells = json.loads(json.dumps(doc))
        cells['chest_maps'][0]['count'] += 1
        cells['chests'].append({'reward': 1})
        with self.assertRaises(ValueError):
            writes_for(rom, cells)
        flags = json.loads(json.dumps(doc))
        flags['ahead'][0].update(flag_index=0, mask=0x80)
        with self.assertRaises(ValueError):
            writes_for(rom, flags)
        # 상자 내용물을 내보내면 붙어 있는 세 원래 자리가 한 자리가 되어 맵 연결이 걸쳐 들어간다
        writes, _ = writes_for(rom, doc, {'chests': 0x3F8000, 'chest_maps': 0x1EEEA8})
        self.assertTrue(any(a == 0x1EEEA8 for a, _, _, _ in writes))
        writes, _ = writes_for(rom, doc, {'lower': 0x1EFFA0})
        self.assertTrue(any(a == 0x1EFFA0 for a, _, _, _ in writes))


@unittest.skipUnless(ROM.is_file(), '롬 없음')
class RealRomChestTableTests(ChestTableRomTests):
    def setUp(self):
        self.rom = Rom(ROM.read_bytes())


if __name__ == '__main__':
    unittest.main()
