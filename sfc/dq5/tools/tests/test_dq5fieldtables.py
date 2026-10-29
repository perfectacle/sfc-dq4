"""필드 표 슬롯 경계·부분 수정·보존 비트를 원본 롬 없이 검사한다."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dq5field import BLOCK_LOWER, BLOCK_UPPER, GROUP_ARRIVAL, block_tiles  # noqa: E402
from dq5fieldtables import (ARRIVAL_COUNT, BLOCK_COUNT, ENTRANCE_POINTERS, ENTRANCE_REFS, ENTRANCE_TABLES,  # noqa: E402
                            FORMAT, dump, edits, patch)
from dq5build import PatchError, check as build_check, parse_at, unhex  # noqa: E402
from dq5map import GROUP_TABLE, POINTER_SITE, TABLE_KINDS, Rom, lorom  # noqa: E402
from dq5newmap import ENTRANCE_SITES  # noqa: E402


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
    for name, refs in ENTRANCE_REFS.items():
        for k, (pc, delta) in enumerate(refs):
            off = lorom(pc)
            raw[off:off + 4] = bytes([0xDF if k == 2 else 0xBF]) + (ENTRANCE_TABLES[name][0] + delta).to_bytes(3, 'little')
    raw[lorom(0x2585D5):lorom(0x2585D5) + 22] = bytes(range(22))
    off = lorom(ENTRANCE_POINTERS)
    raw[off:off + 6] = ENTRANCE_TABLES['main'][0].to_bytes(3, 'little') + ENTRANCE_TABLES['aux'][0].to_bytes(3, 'little')
    # 맵 포인터 그룹 표(그룹마다 맵 하나). 표를 읽는 코드 자리가 0 이면 dq5map 이 원래 자리로 읽는다.
    for addr, size in ((POINTER_SITE - 1, 3), (TABLE_KINDS['pointer']['db'] - 1, 2)):
        raw[lorom(addr):lorom(addr) + size] = bytes(size)
    start = (GROUP_TABLE & 0xFFFF) - ARRIVAL_COUNT * 3
    off = lorom(GROUP_TABLE)
    raw[off:off + ARRIVAL_COUNT * 2] = b''.join((start + g * 3).to_bytes(2, 'little') for g in range(ARRIVAL_COUNT))
    for site, plus in ENTRANCE_SITES:
        raw[lorom(site) - 1:lorom(site) + 3] = bytes([0xBF]) + (GROUP_ARRIVAL + plus).to_bytes(3, 'little')
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


class NewGroupTest(unittest.TestCase):
    """새 그룹(36~)의 입구와 dq5newmap.py 가 옮긴 도착 표."""

    def setUp(self):
        self.data = fixture()
        self.rom = Rom(self.data)

    def aux(self):
        return [{k: e[k] for k in ('group', 'x', 'y')} for e in dump(self.rom)['entrances'] if e['table'] == 'aux']

    def test_new_group_entrance_needs_new_map(self):
        doc = document(entrance_tables={'aux': self.aux() + [{'group': 0x36, 'x': 345, 'y': 56}]})
        with self.assertRaises(ValueError):
            patch(self.rom, doc, entrances_at='68:8000')
        manifest = patch(self.rom, doc, entrances_at='68:8000', new_maps=[(0x36, 0)])
        body = bytes.fromhex(next(w['hex'] for w in manifest['writes'] if w['at'] == '68:8000'))
        self.assertEqual(body[-6:], bytes([0x36, 0x59, 1, 56, 0, 255]))
        in_place = patch(self.rom, document(entrances=[{'table': 'aux', 'index': 0, 'group': 0x37}]),
                         new_maps=[(0x36, 0), (0x37, 0)])
        self.assertEqual(in_place['writes'][0]['hex'][:2], '37')

    def test_new_group_numbers_must_follow_last_group(self):
        doc = document(entrances=[{'table': 'aux', 'index': 0, 'group': 0x37}])
        self.assertEqual(patch(self.rom, document(), new_maps=[(0x50, 0x52)])['writes'], [])
        for maps in ([(0x37, 0)], [(0x36, 0), (0x38, 0)], [(0x4F, 0)]):
            with self.subTest(maps=maps), self.assertRaises(ValueError):
                patch(self.rom, doc, new_maps=maps)
        with self.assertRaises(ValueError):
            patch(self.rom, document(entrances=[{'table': 'aux', 'index': 0, 'group': 0x37}]), new_maps=[(0x36, 0)])

    def moved_arrivals(self):
        """도착 표를 3E:C000 으로 옮기고 그룹 하나(36)를 더한 꼴: 맵 포인터 그룹 표도 [시작…][끝][0000] 로 옮긴다."""
        raw = bytearray(self.data) + bytes(0x200000 - len(self.data))
        at = 0x3EC000
        rows = self.data[lorom(GROUP_ARRIVAL):lorom(GROUP_ARRIVAL) + ARRIVAL_COUNT * 5] + bytes([1, 2, 3, 4, 5])
        raw[lorom(at):lorom(at) + len(rows)] = rows
        for site, plus in ENTRANCE_SITES:
            raw[lorom(site):lorom(site) + 3] = (at + plus).to_bytes(3, 'little')
        start = (GROUP_TABLE & 0xFFFF) - ARRIVAL_COUNT * 3
        table = 0x0FFF50
        values = [start + g * 3 for g in range(ARRIVAL_COUNT + 1)] + [start + (ARRIVAL_COUNT + 1) * 3, 0]
        raw[lorom(table):lorom(table) + len(values) * 2] = b''.join(v.to_bytes(2, 'little') for v in values)
        raw[lorom(POINTER_SITE) - 1:lorom(POINTER_SITE) + 2] = bytes([0xBC]) + (table & 0xFFFF).to_bytes(2, 'little')
        db = TABLE_KINDS['pointer']['db']
        raw[lorom(db) - 1:lorom(db) + 1] = bytes([0xA9, 0x0F])
        return Rom(bytes(raw))

    def test_moved_arrival_table_is_read_but_not_written(self):
        rom = self.moved_arrivals()
        doc = dump(rom)
        self.assertEqual(len(doc['arrivals']), ARRIVAL_COUNT + 1)
        self.assertEqual(doc['arrivals'][-1]['x'], 2)
        self.assertEqual(patch(rom, doc)['writes'], [])
        with self.assertRaises(ValueError):
            patch(rom, document(arrivals=[{'group': 0x36, 'x': 9}]))
        manifest = patch(rom, document(entrances=[{'table': 'aux', 'index': 0, 'group': 0x36}]))
        self.assertEqual(manifest['writes'][0]['hex'][:2], '36')


class EntranceRelocateTest(unittest.TestCase):
    def setUp(self):
        self.data = fixture()
        self.rom = Rom(self.data)

    def entries(self, table):
        return [{k: e[k] for k in ('group', 'x', 'y')} for e in dump(self.rom)['entrances'] if e['table'] == table]

    def test_relocate_grows_aux_and_moves_readers(self):
        aux = self.entries('aux') + [{'group': 2, 'x': 345, 'y': 56}]
        manifest = patch(self.rom, document(entrance_tables={'aux': aux}), entrances_at='68:8000')
        self.assertEqual(manifest['rom_size'], 4)
        body = bytes.fromhex(next(w['hex'] for w in manifest['writes'] if w['at'] == '68:8000'))
        main_count, aux_count = ENTRANCE_TABLES['main'][1], ENTRANCE_TABLES['aux'][1] + 1
        self.assertEqual(len(body), (main_count + aux_count) * 5 + 2)
        self.assertEqual(body[main_count * 5], 255)
        self.assertEqual(body[-6:], bytes([2, 0x59, 1, 56, 0, 255]))
        main_start, aux_start = 0x688000, 0x688000 + main_count * 5 + 1
        out = apply(self.data, {'writes': [w for w in manifest['writes'] if 'orig' in w]})
        for name, refs in ENTRANCE_REFS.items():
            start = main_start if name == 'main' else aux_start
            for pc, delta in refs:
                self.assertEqual(int.from_bytes(out[lorom(pc) + 1:lorom(pc) + 4], 'little'), start + delta)
        off = lorom(ENTRANCE_POINTERS)
        self.assertEqual(out[off:off + 6], main_start.to_bytes(3, 'little') + aux_start.to_bytes(3, 'little'))

    def test_relocate_rejects(self):
        aux = self.entries('aux')
        cases = [
            (document(entrance_tables={'aux': aux}), None),
            (document(entrance_tables={'aux': []}), '68:8000'),
            (document(entrance_tables={'aux': [{'group': 2, 'x': 1}]}), '68:8000'),
            (document(entrance_tables={'aux': [{'group': 0x40, 'x': 1, 'y': 1}]}), '68:8000'),
            (document(entrance_tables={'other': aux}), '68:8000'),
            (document(entrance_tables={'aux': aux}), '7E:8000'),
            (document(entrance_tables={'aux': aux}), '68:FFF0'),
            (document(entrance_tables={'aux': aux}, entrances=[{'table': 'main', 'index': 0, 'x': 1}]), '68:8000'),
            (document(entrances=[]), '68:8000'),
        ]
        for doc, at in cases:
            with self.subTest(doc=doc, at=at), self.assertRaises(ValueError):
                patch(self.rom, doc, entrances_at=at)

    def builder_writes(self, manifest):
        out = []
        for w in manifest['writes']:
            off, _ = parse_at(w['at'])
            out.append((off, unhex(w['hex']), unhex(w['orig']) if 'orig' in w else None, w['note']))
        return [('field-tables', manifest.get('rom_size', 0), out)]

    def test_relocate_in_original_rom_only_into_free_space(self):
        data = bytearray(self.data)
        data[lorom(0x01FD00):lorom(0x01FFFF) + 1] = bytes(0x300)
        rom = Rom(bytes(data))
        doc = document(entrance_tables={'aux': self.entries('aux')})
        used = patch(rom, doc, entrances_at='01:8000')
        self.assertNotIn('orig', next(w for w in used['writes'] if w['at'] == '01:8000'))
        with self.assertRaises(PatchError):
            build_check(bytes(data), self.builder_writes(used), 0)
        free = patch(rom, doc, entrances_at='01:FE00')
        self.assertEqual(len(build_check(bytes(data), self.builder_writes(free), 0)), len(free['writes']))

    def test_relocate_keeps_ruler_groups(self):
        aux = [e for e in self.entries('aux') if e['group'] != 3]
        data = bytearray(self.data)
        off = lorom(0x2585D5)
        data[off:off + 22] = bytes([3] + [0] * 21)
        rom = Rom(bytes(data))
        main = [e for e in self.entries('main') if e['group'] != 3]
        with self.assertRaises(ValueError):
            patch(rom, document(entrance_tables={'main': main, 'aux': aux}), entrances_at='68:8000')

    def test_relocate_refuses_changed_reader(self):
        data = bytearray(self.data)
        pc = ENTRANCE_REFS['main'][0][0]
        data[lorom(pc)] = 0xEA
        with self.assertRaises(ValueError):
            patch(Rom(bytes(data)), document(entrance_tables={'aux': self.entries('aux')}), entrances_at='68:8000')


if __name__ == '__main__':
    unittest.main()
