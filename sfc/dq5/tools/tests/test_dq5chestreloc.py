"""보물상자·조사 보상 표 옮기기의 자리 찾기·자리 규칙·입력 검사."""
import argparse
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch as mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dq5chestreloc import (ABS, DB_MOVABLE, FORMAT, LONG, MAX_CHESTS, ORIGINAL, ORIGINAL_BYTES, address, locate,
                           original_spans, parse, placement, read, rom_size, row_encode, serialize, writes_for)
from dq5map import Rom, lorom
from test_dq5chestwrite import ROM, fixture, poke


def row(name, **values):
    base = {'group': 0, 'map': 1, 'x': 2, 'y': 3, 'reward': 0xA1, 'flag_index': 3, 'mask': 0x80}
    extra = {'search': {'unused': 1}, 'foot': {'layer': 1}}.get(name, {})
    return base | extra | values


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
        with self.assertRaises(ValueError):
            locate(poke(rom, 0x25FAB5, 0x1F))

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

    def test_placement_bank_rules(self):
        rom = fixture()
        sizes = {'search': 10, 'foot': 10, 'chests': 10, 'ahead': 10, 'chest_maps': 10, 'lower': 10}
        at = placement(rom, sizes, {'search': 0x3F8000, 'ahead': 0x7D8000, 'lower': 0x1EF435 + 20}, {})
        self.assertEqual((at['search'], at['ahead'], at['chest_maps']), (0x3F8000, 0x7D8000, ORIGINAL['chest_maps']))
        for wrong in ({'search': 0x408000}, {'foot': 0x408000}, {'chest_maps': 0x3F8000}, {'lower': 0x1F8000},
                      {'chests': 0x7E8000}, {'ahead': 0x3FFFF8}, {'chests': 0x1E8000},
                      {'ahead': ORIGINAL['chests']}):
            with self.subTest(wrong=wrong), self.assertRaises(ValueError):
                placement(rom, sizes, wrong, {})
        self.assertEqual((rom_size([0x1E8000]), rom_size([0x3F8000]), rom_size([0x5F8000]), rom_size([0x7D8000])),
                         (0, 2, 3, 4))

    @unittest.skipUnless(ROM.is_file(), '롬 없음')
    def test_rom_grow_moves_operands_and_owns_old_spans(self):
        rom = Rom(ROM.read_bytes())
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
        self.assertNotIn(DB_MOVABLE['search'], sites)
        owned = sorted((a, a + len(new)) for a, new, _, _ in writes if a >> 16 == 0x1E or a >> 16 == 0x1F)
        for lo, hi in original_spans().values():
            covered = [(max(a, lo), min(b, hi)) for a, b in owned if a < hi and b > lo]
            self.assertEqual(sum(b - a for a, b in covered), hi - lo)

    @unittest.skipUnless(ROM.is_file(), '롬 없음')
    def test_rom_rules_cells_flags_and_merged_spans(self):
        rom = Rom(ROM.read_bytes())
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

    def test_address_accepts_cpu_only(self):
        self.assertEqual(address('BF:9000'), 0x3F9000)
        for text in ('0x1000', '3F9000', '3F:12'):
            with self.subTest(text=text), self.assertRaises(argparse.ArgumentTypeError):
                address(text)


if __name__ == '__main__':
    unittest.main()
