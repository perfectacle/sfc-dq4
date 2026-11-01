"""인물 목록 구조 편집, 조건 표 입력 검사, 슬롯 한도, 옮긴 대체 표 루틴."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch as mock

from kr_patch.sfc.dis65816 import decode
from kr_patch.sfc.mapper import LoROM

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dq5map import Rom, lorom  # noqa: E402
from dq5npclists import (  # noqa: E402
    MAP_OBJECTS, OVERRIDE_COUNT, assemble_find, condition_row, entry_items, list_plan, map_objects, new_map_keys,
    placed, slot_guard,
)

BASE, ALT = 0x058000, 0x108000
DAY = bytes.fromhex('84 12 cb 85 0a 2c 44 f0')
NIGHT = bytes.fromhex('70 de 44 87 20 18 00 01 16')


def fixture():
    """기본 목록 01/02 [DAY, NIGHT], 대체 목록 [DAY], 대체 표 296항목(모두 01/02 → 대체), 01/02 맵 OBJ 물체 하나."""
    data = bytearray(0xC0000)

    def put(addr, raw):
        data[lorom(addr):lorom(addr) + len(raw)] = raw

    put(BASE, DAY + NIGHT + b'\0')
    put(ALT, DAY + b'\0')
    put(0x128449, bytes([1, 2, 0x1D, 0x10, 0x00, 0x80]) * OVERRIDE_COUNT + b'\xff')
    put(MAP_OBJECTS, bytes([1, 2, 5, 5, 1, 1, 0, 0, 0]) + bytes([1, 0x7F, 5, 5, 0x81, 1, 0, 0, 0])
        + bytes([1, 2, 5, 5, 0xC1, 1, 0, 0, 0]) + b'\xff')
    return Rom(data)


ORIGINAL = [(BASE, '01/02'), (ALT, '01/02 대체')]


class ObjectTests(unittest.TestCase):
    def test_map_objects_follow_time_bits(self):
        rom = fixture()
        # 조건 없는 것 하나, bit7 만이면 낮, bit7·bit6 이면 밤.
        self.assertEqual((map_objects(rom, 1, 2, False), map_objects(rom, 1, 2, True)), (2, 2))
        self.assertEqual((map_objects(rom, 1, 3, False), map_objects(rom, 1, 3, True)), (1, 0))
        self.assertEqual(map_objects(rom, 2, 2, False), 0)

    def test_placed_counts_time_bits(self):
        self.assertEqual((placed([DAY, NIGHT, b'\xc0'], False), placed([DAY, NIGHT, b'\xc0'], True)), (2, 2))


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.rom = fixture()
        self.lists = {BASE: [BASE, BASE + len(DAY)], ALT: [ALT]}

    def test_reorder_remove_duplicate(self):
        items = entry_items(self.rom, self.lists, [{'from': 1}, {'from': 0}, {'from': {'list': '10:8000', 'index': 0},
                                                                          'time': 'night'}], BASE, {}, 'test')
        self.assertEqual([at for at, _ in items], [BASE + len(DAY), BASE, ALT])
        self.assertEqual([raw for _, raw in items], [NIGHT, DAY, bytes([0x44]) + DAY[1:]])

    def test_records_and_edits(self):
        edited = bytes([0x84, 0x99]) + DAY[2:]
        self.assertEqual(entry_items(self.rom, self.lists, [{'from': 0}], BASE, {BASE: edited}, 't')[0][1], edited)
        for rows, records in (([{'from': 0, 'fields': {'x': 1}}], {BASE: edited}), ([{'from': 2}], {}),
                              ([{'from': True}], {}), ([{'from': {'list': '05:8001', 'index': 0}}], {}),
                              ([{'from': 0, 'extra': 1}], {}), ([{'from': {'list': '10:8000'}}], {}), ({}, {})):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                entry_items(self.rom, self.lists, rows, BASE, records, 't')
        with self.assertRaises(ValueError):
            entry_items(self.rom, self.lists, [{'from': 0}], None, {}, 'new')

    def test_new_list_names(self):
        with mock('dq5npclists.list_entries', side_effect=lambda rom, at: [(a, 0) for a in self.lists[at]]):
            base, alt = list_plan(self.rom, {'new_lists': [{'name': 'a', 'entries': []}]}, ORIGINAL, {})
            self.assertEqual([k for k, _ in alt], [ALT, 'new:a'])
            for doc in ({'new_lists': [{'name': 'a', 'entries': []}, {'name': 'a', 'entries': []}]},
                        {'new_lists': [{'name': 'a b', 'entries': []}]},
                        {'lists': [{'list': '05:8000', 'entries': []}, {'list': '05:8000', 'entries': []}]},
                        {'lists': [{'list': '05:8001', 'entries': []}]}):
                with self.subTest(doc=doc), self.assertRaises(ValueError):
                    list_plan(self.rom, doc, ORIGINAL, {})


class NewMapTests(unittest.TestCase):
    ORIGINAL = [(0x058000, '01/00'), (0x058001, '01/01'), (0x058002, '02/00'), (ALT, '01/00 대체')]

    def test_new_map_numbers_follow_group_end(self):
        self.assertEqual(new_map_keys(self.ORIGINAL, [(1, 3), (1, 2), (2, 1)]), [(1, 2), (1, 3), (2, 1)])
        for maps in ([(1, 3)], [(1, 2), (1, 2)], [(3, 0)], [(2, 0)]):
            with self.subTest(maps=maps), self.assertRaises(ValueError):
                new_map_keys(self.ORIGINAL, maps)

    def test_new_groups_follow_35(self):
        original = self.ORIGINAL
        with mock('dq5npclists.GROUP_COUNT', 3):
            self.assertEqual(new_map_keys(original, [(3, 0), (3, 1), (4, 0)]), [(3, 0), (3, 1), (4, 0)])
            for maps in ([(4, 0)], [(3, 1)], [(0x50, 0)]):
                with self.subTest(maps=maps), self.assertRaises(ValueError):
                    new_map_keys(original, maps)

    def test_new_map_lists_go_after_their_group(self):
        rom = fixture()
        lists = {0x058000: [], 0x058001: [], 0x058002: [], ALT: [ALT]}
        with mock('dq5npclists.list_entries', side_effect=lambda r, at: [(a, 0) for a in lists[at]]):
            doc = {'lists': [{'map': '01/02', 'entries': [{'from': {'list': '10:8000', 'index': 0}}]}]}
            base, alt = list_plan(rom, doc, self.ORIGINAL, {}, [(1, 2), (1, 3)])
            self.assertEqual([k for k, _ in base], [0x058000, 0x058001, '01/02', '01/03', 0x058002])
            self.assertEqual([len(items) for _, items in base], [0, 0, 1, 0, 0])
            with mock('dq5npclists.GROUP_COUNT', 3):
                base, _ = list_plan(rom, {}, self.ORIGINAL, {}, [(1, 2), (3, 0)])
            self.assertEqual([k for k, _ in base], [0x058000, 0x058001, '01/02', 0x058002, '03/00'])
            for bad in ({'lists': [{'map': '01/04', 'entries': []}]},
                        {'lists': [{'map': '01/02', 'entries': []}, {'map': '01/02', 'entries': []}]},
                        {'lists': [{'map': '01/00', 'entries': []}, {'list': '05:8000', 'entries': []}]},
                        {'lists': [{'map': '01/0a', 'entries': []}]},
                        {'lists': [{'map': '01/02', 'entries': [{'from': 0}]}]},
                        {'lists': [{'map': '01/00', 'entries': []}, {'list': '05:8000', 'entries': []}]}):
                with self.subTest(doc=bad), self.assertRaises(ValueError):
                    list_plan(rom, bad, self.ORIGINAL, {}, [(1, 2)])


class ConditionTests(unittest.TestCase):
    def test_condition_rows(self):
        known = {(1, 2)}
        self.assertEqual(condition_row({'map': '01/02', 'flag': 0x1D, 'when': 'off', 'mask': 16, 'list': 'new:a'},
                                       known, {'new:a'}, 't'), (bytes([1, 2, 0x9D, 16]), 'new:a'))
        self.assertEqual(condition_row({'map': '01/02', 'flag': 2, 'when': 'on', 'mask': 128}, known, None, 't'),
                         (bytes([1, 2, 2, 128]), None))
        for row, targets in (({'map': '01/03', 'flag': 0, 'when': 'on', 'mask': 1, 'list': 'new:a'}, {'new:a'}),
                             ({'map': '01/02', 'flag': 128, 'when': 'on', 'mask': 1}, None),
                             ({'map': '01/02', 'flag': 0, 'when': 'on', 'mask': 3}, None),
                             ({'map': '01/02', 'flag': 0, 'when': 'on', 'mask': True}, None),
                             ({'map': '01/02', 'flag': 0, 'when': 'on', 'mask': 1, 'list': '10:8000'}, None),
                             ({'map': '01/02', 'flag': 0, 'when': 'on', 'mask': 1, 'list': 'new:b'}, {'new:a'}),
                             ({'map': '01/02', 'flag': 0, 'when': 'on', 'mask': 1}, {'new:a'}),
                             ({'map': '01/02', 'flag': 0, 'mask': 1}, None)):
            with self.subTest(row=row), self.assertRaises(ValueError):
                condition_row(row, known, targets, 't')


class SlotTests(unittest.TestCase):
    def test_growth_needs_flag(self):
        rom = fixture()
        lists = {BASE: [BASE, BASE + len(DAY)], ALT: [ALT]}
        rows = [(bytes([1, 2, 0x1D, 0x10]), ALT)] * OVERRIDE_COUNT
        with mock('dq5npclists.list_entries',
                  side_effect=lambda r, at: [(a, len(DAY) if a == BASE or a == ALT else len(NIGHT)) for a in lists[at]]):
            same = [(BASE, [(BASE, DAY), (0, NIGHT)])], [(ALT, [(ALT, DAY)])]
            self.assertEqual(slot_guard(rom, ORIGINAL, *same, rows, False), [])
            more = [(BASE, [(BASE, DAY), (BASE, DAY), (0, NIGHT)])], [(ALT, [(ALT, DAY)])]
            # 01/02 낮은 원본 인물 1명 + 물체 2개 = 슬롯 0B 까지. 낮 인물 둘이면 0C.
            with self.assertRaises(ValueError):
                slot_guard(rom, ORIGINAL, *more, rows, False)
            self.assertEqual(len(slot_guard(rom, ORIGINAL, *more, rows, True)), 1)
            # 새 맵은 원본 값이 없어 1F 까지, 인물이 있을 때만 늘어난 맵으로 알린다(그룹 전체 물체 01/7F 도 셈).
            fresh = [(BASE, [(BASE, DAY), (0, NIGHT)]), ('01/03', [(BASE, DAY)])], [(ALT, [(ALT, DAY)])]
            self.assertEqual(slot_guard(rom, ORIGINAL, *fresh, rows, False, [(1, 3)]), ['01/03 낮 01/03 슬롯 0x0a 남은 슬롯 22'])
            empty = [(BASE, [(BASE, DAY), (0, NIGHT)]), ('01/03', [])], [(ALT, [(ALT, DAY)])]
            self.assertEqual(slot_guard(rom, ORIGINAL, *empty, rows, False, [(1, 3)]), [])
            full = [(BASE, [(BASE, DAY)] * 22)], [(ALT, [(ALT, DAY)])]
            with self.assertRaises(ValueError):
                slot_guard(rom, ORIGINAL, *full, rows, True)
            # 장면이 슬롯을 더 쓰는 맵은 그만큼 한도가 낮다. 01/02 낮 인물 20명 + 물체 2개 = 슬롯 1E.
            twenty = [(BASE, [(BASE, DAY)] * 20)], [(ALT, [(ALT, DAY)])]
            self.assertEqual(len(slot_guard(rom, ORIGINAL, *twenty, rows, True)), 1)
            with mock.dict('dq5npclists.SCENE_SLOTS', {(1, 2): 4}), self.assertRaises(ValueError):
                slot_guard(rom, ORIGINAL, *twenty, rows, True)
            with mock.dict('dq5npclists.SCENE_SLOTS', {(1, 2): 2}):
                self.assertEqual(slot_guard(rom, ORIGINAL, *twenty, rows, True)[0].split('남은 슬롯 ')[1], '0(장면이 더 쓰는 2칸 뺌)')


class RoutineTests(unittest.TestCase):
    def test_banked_rows_read_bank_byte(self):
        # 대체 목록을 여러 뱅크에 나누면 항목 끝 1바이트가 목록 뱅크이고 다음 항목은 7바이트 뒤.
        code = assemble_find(0x35E000, None)
        self.assertIn(bytes.fromhex('bf 06 e0 35 85 a7 28 ab 38 6b'), code)
        self.assertIn(bytes.fromhex('69 07 00'), code)
        self.assertNotIn(bytes.fromhex('69 06 00'), code)
        self.assertEqual(len(code), len(assemble_find(0x35E000, 0x35)) + 2)

    def test_branches_land_on_instructions(self):
        for bank in (0x33, None):
            with self.subTest(bank=bank):
                self.check_branches(bank)

    def check_branches(self, bank):
        table = 0x33E000
        code = assemble_find(table, bank)
        data = bytearray(0x1A0000)
        start = 0x33F000
        data[lorom(start):lorom(start) + len(code)] = code
        starts, pc, m8, x8 = set(), start, True, True
        targets = []
        while pc < start + len(code):
            text, n, _, _ = decode(bytes(data), pc, m8=m8, x8=x8, mapper=LoROM())
            starts.add(pc)
            op, arg = code[pc - start], code[pc - start + 1] if n > 1 else 0
            if op in (0xC2, 0xE2):
                m8 = op == 0xE2 if arg & 0x20 else m8
                x8 = op == 0xE2 if arg & 0x10 else x8
            if op in (0x10, 0x30, 0x80, 0xD0, 0xF0):
                targets.append(pc + 2 + (arg - 256 if arg & 0x80 else arg))
            pc += n
        self.assertEqual(pc, start + len(code))
        self.assertTrue(set(targets) <= starts)
        self.assertEqual(code[:13], bytes.fromhex('8b 08 e2 20 c2 10 a9 7e 48 ab a2 00 00'))
        self.assertEqual(code[13:17], bytes([0xBF, 0x00, 0xE0, 0x33]))
        if bank is not None:
            self.assertIn(bytes.fromhex('a9 33 85 a7 28 ab 38 6b'), code)
        self.assertEqual(code[-4:], bytes.fromhex('28 ab 18 6b'))


if __name__ == '__main__':
    unittest.main()
