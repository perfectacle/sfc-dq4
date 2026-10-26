"""출구·영역 이동 표 전체 직렬화와 옮기기: 합성 롬에서 왕복, 엔진 순서 찾기, 자리 제약."""
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch as mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dq5exitreloc import (
    EXIT_INDEXED,
    EXIT_INIT,
    EXIT_SHORT,
    FORMAT,
    HIGH_ORIGINAL,
    HIGH_SITES,
    INDEX_BANK,
    INDEX_OPERANDS,
    ORIGINAL,
    RECORD_BANK,
    RECORD_LOW,
    engine_exits,
    engine_triggers,
    high_maps,
    locate,
    parse,
    serialize,
    writes_for,
)
from dq5exitwrite import HIGH_LISTS
from dq5map import Rom, lorom

HIGH = [(0x50, 0x50), (0x50, 0x51), *((0x51, 0x50 + i) for i in range(8)), (0x52, 0x50),
        *((0x53, 0x50 + i) for i in range(3)), *((0x54, 0x50 + i) for i in range(4))]
KNOWN = {(g, 0) for g in range(54)} | {(1, 1), (1, 2)} | set(HIGH)


def trigger(x, group=1, bd=1):
    return {'rect': [x, 2, x + 1, 3], 'source_layer': 1, 'flags': 0xC0, 'destination_group': group,
            'destination_map': bd, 'x': 4, 'y': 5, 'span_raw': 1, 'destination_layer': 1}


def document():
    exits = []
    for bc, bd in sorted(k for k in KNOWN if k[0] < 0x50):
        exits.append({'map': f'{bc:02X}/{bd:02X}', 'records': [{'kind': 'special', 'special': 0}]})
    exits[1]['records'] = [{'kind': 'same-group', 'destination_map': 1, 'exit': 0},
                           {'kind': 'other-group', 'destination_map': 0, 'exit': 0, 'group': 5},
                           {'kind': 'position', 'destination_map': 2, 'x': 9, 'y': 8, 'layer': 2, 'group': 1}]
    # 원래 롬의 고정 자리에 맞도록 목록마다 원래 개수를 둔다.
    high = [{'maps': maps, 'records': [trigger(i)] * count}
            for i, (maps, (_, count)) in enumerate(zip(high_maps(KNOWN), HIGH_LISTS))]
    return {'format': FORMAT, 'exits': exits,
            'triggers': [{'map': '01/01', 'records': [trigger(1), trigger(5, 0x80, 0)]},
                         {'map': '00/00', 'records': [trigger(7)]}],
            'high_triggers': high}


def write(data, addr, raw):
    data[lorom(addr):lorom(addr) + len(raw)] = raw


def original_rom(doc):
    """원래 코드 꼴의 즉값과 원래 자리의 표를 넣은 1.5MB 합성 롬."""
    data = bytearray(0x180000)
    write(data, EXIT_INIT, bytes.fromhex('a9 61 85 84 a9 ed 85 85'))
    for at in EXIT_SHORT:
        write(data, at, b'\xb2\x84')
    for at in EXIT_INDEXED:
        write(data, at, b'\xb1\x84')
    write(data, INDEX_BANK, b'\x2a')
    for at, plus in INDEX_OPERANDS:
        write(data, at, (0xEB0E + plus).to_bytes(2, 'little'))
    write(data, RECORD_LOW, b'\x12\xd8')
    write(data, RECORD_BANK, b'\x2a')
    for site, at in zip(HIGH_SITES, HIGH_ORIGINAL):
        write(data, site, bytes([0xAF, *at.to_bytes(3, 'little'), 0x8D, 0x3D, 0x18, 0xA2,
                                 *(at + 1 & 0xFFFF).to_bytes(2, 'little'), 0x8E, 0x3A, 0x18, 0xA9, 0x01]))
    blobs = serialize(doc, KNOWN)
    for name in ('exits', 'index', 'records'):
        write(data, ORIGINAL[name], blobs[name])
    for at, blob in zip(HIGH_ORIGINAL, blobs['high']):
        write(data, at, blob)
    return data


def apply(data, writes, size=0x400000):
    out = bytearray(data) + bytes(size - len(data))
    for addr, new, old, _ in writes:
        if old is not None:
            assert bytes(out[lorom(addr):lorom(addr) + len(new)]) == old
        write(out, addr, new)
    return Rom(out)


class RelocTests(unittest.TestCase):
    def setUp(self):
        patcher = mock('dq5exitreloc.known_maps', return_value=KNOWN)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.doc = document()
        self.rom = Rom(original_rom(self.doc))

    def test_round_trip_in_place(self):
        self.assertEqual(locate(self.rom), {**ORIGINAL, 'high': HIGH_ORIGINAL})
        self.assertEqual(parse(self.rom), self.doc)
        self.assertEqual(writes_for(self.rom, self.doc), ([], 0))

    def test_in_place_shrink_touches_only_tables(self):
        doc = copy.deepcopy(self.doc)
        doc['exits'][1]['records'][2] = {'kind': 'same-group', 'destination_map': 2, 'exit': 0}
        writes, size = writes_for(self.rom, doc)
        self.assertEqual(size, 0)
        self.assertEqual([w[0] for w in writes], [ORIGINAL['exits']])
        moved = apply(self.rom.d, writes, 0x180000)
        self.assertEqual(parse(moved), doc)

    def test_grow_and_move_to_other_banks(self):
        doc = copy.deepcopy(self.doc)
        doc['exits'][2]['records'].insert(0, {'kind': 'position', 'destination_map': 1, 'x': 3, 'y': 4,
                                              'layer': 1, 'group': 1})
        doc['triggers'].append({'map': '01/02', 'records': [trigger(9)]})
        doc['high_triggers'][0]['records'].append(trigger(11))
        at = {'exits': 0x7C8000, 'records': 0x3E8000, 'index': 0x0BFBB0, 'high': 0x3EA000}
        writes, size = writes_for(self.rom, doc, at)
        self.assertEqual(size, 4)
        moved = apply(self.rom.d, writes)
        loc = locate(moved)
        self.assertEqual((loc['exits'], loc['records'], loc['index'], loc['high'][0]),
                         (0x7C800D, 0x3E8000, 0x0BFBB0, 0x3EA000))
        self.assertEqual(moved.d[lorom(EXIT_SHORT[0])], 0xA7)
        self.assertEqual(moved.d[lorom(EXIT_INDEXED[0])], 0xB7)
        self.assertEqual(parse(moved), doc)
        self.assertEqual([r for _, r in engine_exits(moved, loc, 1, 1)][0], bytes([0x61, 3, 4, 1, 1]))
        self.assertEqual(engine_triggers(moved, loc, 1, 2)[0][:4], bytes([9, 2, 10, 3]))
        self.assertEqual(engine_triggers(moved, loc, 1, 0), [])
        self.assertEqual(writes_for(moved, doc, at), ([], 0))

    def test_exits_inside_bank_2a_use_immediates_only(self):
        writes, _ = writes_for(self.rom, self.doc, {'exits': 0x2AD812, 'records': 0x3F8000})
        code = {w[0]: w[1] for w in writes if w[0] < 0x2AD812 or w[0] > 0x2AF224}
        self.assertEqual(code[EXIT_INIT], bytes.fromhex('a9 12 85 84 a9 d8 85 85'))
        self.assertNotIn(EXIT_SHORT[0], code)
        self.assertEqual(code[RECORD_BANK], b'\x3f')
        self.assertEqual(parse(apply(self.rom.d, writes)), self.doc)

    def test_placement_constraints(self):
        for at, message in (({'records': 0x408000}, '00~3F'), ({'index': 0x7C8000}, '00~3F'),
                            ({'high': 0x41C000}, '00~3F'), ({'exits': 0x7EFF00}, '00~7D'),
                            ({'exits': 0x30FFF0}, '한 뱅크'), ({'exits': 0x058000}, '어느 한 곳'),
                            ({'exits': 0x308000, 'records': 0x308050}, '겹침')):
            with self.subTest(at=at), self.assertRaisesRegex(ValueError, message):
                writes_for(self.rom, self.doc, at)
        grown = copy.deepcopy(self.doc)
        grown['triggers'][0]['records'] *= 200
        with self.assertRaisesRegex(ValueError, '0~255'):
            writes_for(self.rom, grown)

    def test_document_guards(self):
        cases = []
        doc = copy.deepcopy(self.doc)
        doc['exits'][0]['records'][0] = {'kind': 'same-group', 'destination_map': 1, 'exit': 255}
        cases.append((doc, '0~254'))
        doc = copy.deepcopy(self.doc)
        doc['exits'][1]['records'][0]['exit'] = 1
        cases.append((doc, '출구 수 밖'))
        doc = copy.deepcopy(self.doc)
        doc['exits'][1]['records'][0]['destination_map'] = 3
        cases.append((doc, '목적지'))
        doc = copy.deepcopy(self.doc)
        doc['exits'][3]['records'] = []
        cases.append((doc, '하나 이상'))
        doc = copy.deepcopy(self.doc)
        doc['exits'].reverse()
        cases.append((doc, '순서'))
        doc = copy.deepcopy(self.doc)
        doc['exits'][1]['records'][0]['group'] = 1
        cases.append((doc, '필드'))
        doc = copy.deepcopy(self.doc)
        doc['triggers'].append({'map': '01/01', 'records': [trigger(1)]})
        cases.append((doc, '한 번만'))
        doc = copy.deepcopy(self.doc)
        doc['triggers'].append({'map': '50/50', 'records': [trigger(1)]})
        cases.append((doc, '한 번만'))
        doc = copy.deepcopy(self.doc)
        doc['triggers'][0]['records'][0]['rect'] = [5, 2, 5, 3]
        cases.append((doc, '양수'))
        doc = copy.deepcopy(self.doc)
        doc['triggers'][0]['records'][0]['destination_map'] = 9
        cases.append((doc, '목적지'))
        doc = copy.deepcopy(self.doc)
        doc['high_triggers'][0]['maps'] = ['50/50']
        cases.append((doc, '94B4'))
        doc = copy.deepcopy(self.doc)
        doc['triggers'][1]['records'] = []
        cases.append((doc, '빼야'))
        for doc, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                writes_for(self.rom, doc)

    def test_fixed_slot_writer_refuses_moved_rom(self):
        from dq5exitwrite import layout
        moved = apply(self.rom.d, writes_for(self.rom, self.doc, {'records': 0x3E8000})[0])
        with self.assertRaisesRegex(ValueError, '옮긴 롬'):
            layout(moved)

    def test_negative_edge_and_field_records_round_trip(self):
        doc = copy.deepcopy(self.doc)
        doc['triggers'][0]['records'][0]['rect'] = [255, 6, 0, 12]
        doc['triggers'][0]['records'][0]['span_raw'] = 0xFA
        moved = apply(self.rom.d, writes_for(self.rom, doc)[0], 0x180000)
        self.assertEqual(parse(moved), doc)


if __name__ == '__main__':
    unittest.main()
