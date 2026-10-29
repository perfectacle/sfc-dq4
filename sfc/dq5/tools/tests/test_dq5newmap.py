"""새 맵 번호: 합성 롬에서 그룹 표 옮기기·목록 밀기, 원래 맵 보존, 입력·한도 검사."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch as mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dq5map import (ATTR_SITES, ATTR_TABLE, DOOR_ENTRIES, GROUP_TABLE, GROUPS, POINTER_SITE, Rom, door_groups, door_table,
                    group_spans, lorom, map_pointer)
from dq5mapwrite import all_maps
from dq5newmap import DOOR_TABLE, ENTRANCE_SITES, FORMAT, writes_for

# 그룹마다 맵 수. 그룹 01 은 둘, 나머지는 하나.
COUNTS = [2 if g == 1 else 1 for g in range(GROUPS)]


def write(data, addr, raw):
    data[lorom(addr):lorom(addr) + len(raw)] = raw


def original_rom():
    """그룹 목록 바로 뒤에 그룹 표가 있는 원래 꼴 두 표와 표를 읽는 명령 꼴을 넣은 1.5MB 합성 롬."""
    data = bytearray(0x180000)
    for table, size, value in ((GROUP_TABLE, 3, lambda g, b: (0x188000 + g * 0x100 + b * 0x10).to_bytes(3, 'little')),
                               (ATTR_TABLE, 6, lambda g, b: bytes([g, b, 1, 2, 3, 4]))):
        start = (table & 0xFFFF) - sum(COUNTS) * size
        cursor, pointers = start, []
        for g, n in enumerate(COUNTS):
            pointers.append(cursor)
            for b in range(n):
                write(data, table & 0xFF0000 | cursor, value(g, b))
                cursor += size
        write(data, table, b''.join(p.to_bytes(2, 'little') for p in pointers))
    high, cursor = 0x1FCEB6, 0xCEB6 - 5 * 3
    write(data, high, b''.join((cursor + g * 3).to_bytes(2, 'little') for g in range(5)))
    for g in range(5):
        write(data, 0x1F0000 | cursor + g * 3, (0x0F9000 + g).to_bytes(3, 'little'))
    for db, bank in ((0x0192F0, 0x0F), (0x0183EC, 0x23), (0x019325, 0x1F)):
        write(data, db, bytes([0xA9, bank]))
    write(data, 0x01934E, bytes([0xBC, 0xB6, 0xCE]))
    write(data, POINTER_SITE - 1, bytes([0xBC, 0xD7, 0x8E]))
    for site, plus in ENTRANCE_SITES:
        write(data, site - 1, bytes([0xBF, *(0x0FEA97 + plus).to_bytes(3, 'little')]))
    for g in range(GROUPS):
        write(data, 0x0FEA97 + g * 5, bytes([g, 1, 2, 3, 4]))
    # 문 표: 그룹마다 맵 사이 80, 그룹 끝 C0. 그룹 03 의 첫 맵에만 문 하나.
    for entry in DOOR_ENTRIES:
        write(data, entry, bytes.fromhex('8b 4b ab 20 d1 f3 ab 6b') if entry == 0x01F3C9 else bytes.fromhex('08 8b 4b ab'))
    write(data, DOOR_TABLE, b''.join((b'\x01\x02\x03\x04\x05' if g == 3 else b'') + b'\x80' * (n - 1) + b'\xc0'
                                     for g, n in enumerate(COUNTS)))
    write(data, ATTR_SITES[0] - 1, bytes([0xBD, 0x6A, 0xFD]))
    write(data, ATTR_SITES[1] - 1, bytes([0xBD, 0x6B, 0xFD]))
    return Rom(data)


def apply(rom, writes):
    out = bytearray(rom.d) + bytes(0x400000 - len(rom.d))
    for addr, new, old, _ in writes:
        if old is not None:
            assert bytes(out[lorom(addr):lorom(addr) + len(new)]) == old
        write(out, addr, new)
    return Rom(out)


def attr(rom, bc, bd):
    spans, table = group_spans(rom, attr=True)
    off = lorom(table & 0xFF0000 | spans[bc][0] + bd * 6)
    return bytes(rom.d[off:off + 6])


def doc(*rows):
    return {'format': FORMAT, 'maps': list(rows)}


class NewMapTests(unittest.TestCase):
    def setUp(self):
        self.rom = original_rom()
        self.before = all_maps(self.rom)

    def test_original_layout_round_trip(self):
        self.assertEqual(len([m for m in self.before if m[0] < GROUPS]), sum(COUNTS))
        self.assertEqual(writes_for(self.rom, doc()), ([], 0))

    def test_add_map_keeps_other_maps(self):
        for group in (0x00, 0x01, 0x35):
            with self.subTest(group=group):
                bd = COUNTS[group]
                new = (group, bd)
                writes, _ = writes_for(self.rom, doc({'map': f'{group:02X}/{bd:02X}', 'record': {'copy': '01/00'},
                                                      'attrs': {'bytes': [9, 8, 7, 6, 5, 4]}}), allow_doors=group == 0x35)
                moved = apply(self.rom, writes)
                self.assertEqual(sorted(all_maps(moved)), sorted(self.before + [new]))
                self.assertEqual(map_pointer(moved, *new), map_pointer(self.rom, 1, 0))
                self.assertEqual(attr(moved, *new), bytes([9, 8, 7, 6, 5, 4]))
                for m in self.before:
                    if m[0] < GROUPS:
                        self.assertEqual(map_pointer(moved, *m), map_pointer(self.rom, *m))
                        self.assertEqual(attr(moved, *m), attr(self.rom, *m))
                self.assertEqual(group_spans(moved)[1], 0x0FFF50)
                self.assertEqual(group_spans(moved, attr=True)[1], 0x23FF20)
                again = doc({'map': f'{group:02X}/{bd:02X}', 'record': {'copy': '01/00'},
                             'attrs': {'bytes': [9, 8, 7, 6, 5, 4]}})
                self.assertEqual(writes_for(moved, again, allow_doors=True)[0], [])

    def test_existing_map_and_new_record_source(self):
        with mock('dq5newmap.encode', return_value=b'\x11\x22'), mock('dq5newmap.entries_for', return_value=[]), \
                mock('pathlib.Path.read_text', return_value='{"format": "dq5map/1"}'):
            writes, size = writes_for(self.rom, doc(
                {'map': '02/01', 'record': {'source': 'x.json'}, 'attrs': {'copy': '02/00'}},
                {'map': '05/00', 'attrs': {'bytes': [0, 0, 0, 0, 0, 0]}}), at={'records': 0x308000}, allow_doors=True)
        moved = apply(self.rom, writes)
        self.assertEqual(size, 2)
        self.assertEqual(map_pointer(moved, 2, 1), 0x308000)
        self.assertEqual(bytes(moved.d[lorom(0x308000):lorom(0x308000) + 2]), b'\x11\x22')
        self.assertEqual(attr(moved, 5, 0), bytes(6))
        self.assertEqual(map_pointer(moved, 5, 0), map_pointer(self.rom, 5, 0))

    def test_limits_and_guards(self):
        many = [{'map': f'01/{bd:02X}', 'record': {'copy': '01/00'}, 'attrs': {'copy': '01/00'}} for bd in range(2, 21)]
        cases = [
            (doc({'map': '01/03', 'record': {'copy': '01/00'}, 'attrs': {'copy': '01/00'}}), '끝 번호'),
            (doc({'map': '01/02', 'record': {'copy': '01/00'}}), '둘 다'),
            (doc({'map': '51/51', 'record': {'copy': '51/50'}}), '50·52·53'),
            (doc({'map': '50/51', 'record': {'copy': '01/00'}}), '서로 복사'),
            (doc({'map': '50/51', 'record': {'copy': '50/50'}, 'attrs': {'copy': '01/00'}}), 'dq5encounterwrite'),
            (doc({'map': '01/02', 'record': {'copy': '01/00'}, 'attrs': {'copy': '01/00'}},
                 {'map': '01/03', 'record': {'copy': '01/00'}, 'attrs': {'copy': '01/00'}}), '문 표'),
            (doc({'map': '37/00', 'record': {'copy': '01/00'}, 'attrs': {'copy': '01/00'}}), 'groups'),
            (doc({'map': '01/02', 'record': {'copy': '09/09'}, 'attrs': {'copy': '01/00'}}), '없음'),
            (doc({'map': '01/02', 'record': {'copy': '01/00'}, 'attrs': {'bytes': [1, 2, 3]}}), 'bytes'),
            (doc({'map': '01/02', 'record': {'copy': '01/00'}, 'attrs': {'copy': '01/00'}, 'npc': 1}), 'map·record·attrs'),
            (doc({'map': '01/02', 'record': {'source': 'x.json'}, 'attrs': {'copy': '01/00'}}), ''),
            (doc(*many), '넘침'),
            ({'format': FORMAT, 'other': 1}, '문서는'),
        ]
        for value, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex((ValueError, OSError), message):
                writes_for(self.rom, value, allow_doors=message != '문 표')
        with mock('dq5newmap.encode', return_value=b'\x11'), mock('dq5newmap.entries_for', return_value=[]), \
                mock('pathlib.Path.read_text', return_value='{"format": "dq5map/1"}'), \
                self.assertRaisesRegex(ValueError, '빈 자리'):
            writes_for(self.rom, doc({'map': '01/02', 'record': {'source': 'x.json'}, 'attrs': {'copy': '01/00'}}),
                       at={'records': 0x018000})
        hooked = Rom(bytearray(self.rom.d))
        write(hooked.d, POINTER_SITE - 1, bytes([0x22, 0, 0x80]))
        with self.assertRaisesRegex(ValueError, '원래 명령'):
            group_spans(hooked)
        one = doc({'map': '01/02', 'record': {'copy': '01/00'}, 'attrs': {'copy': '01/00'}})
        for at, message in (({'pointer': 0x10FF50}, '빈 자리'), ({'attr': 0x238000}, '빈 자리'),
                            ({'pointer': 0x408000}, '00~3F')):
            with self.subTest(at=at), self.assertRaisesRegex(ValueError, message):
                writes_for(self.rom, one, at=at)


class GrowTests(unittest.TestCase):
    def setUp(self):
        self.rom = original_rom()

    def test_block_move_to_other_bank(self):
        rows = [{'map': f'01/{bd:02X}', 'record': {'copy': '01/00'}, 'attrs': {'bytes': [bd, 0, 0, 0, 0, 0]}}
                for bd in range(2, 42)]
        with self.assertRaisesRegex(ValueError, '넘침'):
            writes_for(self.rom, doc(*rows), allow_doors=True)
        at = {'pointer': 0x3E8000, 'attr': 0x3EA000}
        with self.assertRaisesRegex(ValueError, '자리가 겹침'):
            writes_for(self.rom, doc(*rows), at={'pointer': 0x3E8000, 'attr': 0x3E8010}, allow_doors=True)
        writes, size = writes_for(self.rom, doc(*rows), at=at, allow_doors=True)
        moved = apply(self.rom, writes)
        self.assertEqual(size, 2)
        self.assertEqual(moved.d[lorom(0x0192F1)], 0x3E)
        self.assertEqual(moved.d[lorom(0x0183ED)], 0x3E)
        self.assertEqual(len([m for m in all_maps(moved) if m[0] == 1]), 42)
        for bd in range(2, 42):
            self.assertEqual(map_pointer(moved, 1, bd), map_pointer(self.rom, 1, 0))
            self.assertEqual(attr(moved, 1, bd), bytes([bd, 0, 0, 0, 0, 0]))
        for m in all_maps(self.rom):
            self.assertEqual(map_pointer(moved, *m), map_pointer(self.rom, *m))
        self.assertEqual(writes_for(moved, doc(*rows), at=at, allow_doors=True)[0], [])
        self.assertEqual(writes_for(moved, doc(*rows), allow_doors=True)[0], [])
        more = doc(*rows, {'map': '01/2A', 'record': {'copy': '01/00'}, 'attrs': {'copy': '01/00'}})
        grown = apply(moved, writes_for(moved, more, allow_doors=True)[0])
        self.assertIn((1, 0x2A), all_maps(grown))

    def test_new_group_and_entrance(self):
        value = doc({'map': '36/00', 'record': {'copy': '01/00'}, 'attrs': {'copy': '02/00'}})
        value['groups'] = [{'group': '36', 'entrance': {'copy': '0D'}}]
        with self.assertRaisesRegex(ValueError, '문 표'):
            writes_for(self.rom, value, at={'entrance': 0x3E9000})
        with self.assertRaisesRegex(ValueError, 'entrance-table-at'):
            writes_for(self.rom, value, allow_doors=True)
        moved = apply(self.rom, writes_for(self.rom, value, at={'entrance': 0x3E9000}, allow_doors=True)[0])
        self.assertIn((0x36, 0), all_maps(moved))
        self.assertEqual(len(group_spans(moved)[0]), GROUPS + 1)
        self.assertEqual(map_pointer(moved, 0x36, 0), map_pointer(self.rom, 1, 0))
        self.assertEqual(attr(moved, 0x36, 0), attr(self.rom, 2, 0))
        self.assertEqual(bytes(moved.d[lorom(0x3E9000 + 0x36 * 5):lorom(0x3E9000 + 0x36 * 5) + 5]),
                         bytes([0x0D, 1, 2, 3, 4]))
        empty = dict(value, maps=[])
        with self.assertRaisesRegex(ValueError, '맵이 없음'):
            writes_for(self.rom, empty, at={'entrance': 0x3E9000})
        with self.assertRaisesRegex(ValueError, '두 번'):
            writes_for(self.rom, dict(value, groups=value['groups'] * 2), at={'entrance': 0x3E9000}, allow_doors=True)

    def test_high_group_map(self):
        value = doc({'map': '50/51', 'record': {'copy': '50/50'}})
        moved = apply(self.rom, writes_for(self.rom, value)[0])
        self.assertIn((0x50, 0x51), all_maps(moved))
        self.assertEqual(map_pointer(moved, 0x50, 0x51), map_pointer(self.rom, 0x50, 0x50))
        self.assertEqual(group_spans(moved, kind='high')[1], 0x1FFE30)
        self.assertEqual(writes_for(moved, value)[0], [])


class DoorTests(unittest.TestCase):
    def setUp(self):
        self.rom = original_rom()

    def test_door_bank_inserts_empty_lists(self):
        rows = [{'map': f'01/{bd:02X}', 'record': {'copy': '01/00'}, 'attrs': {'copy': '01/00'}} for bd in (2, 3)]
        value = doc(*rows)
        value['groups'] = [{'group': '36', 'entrance': {'copy': '0D'}}]
        value['maps'].append({'map': '36/00', 'record': {'copy': '01/00'}, 'attrs': {'copy': '01/00'}})
        with self.assertRaisesRegex(ValueError, 'door-bank'):
            writes_for(self.rom, value, at={'entrance': 0x3E9000})
        with self.assertRaisesRegex(ValueError, '30~3F'):
            writes_for(self.rom, value, at={'entrance': 0x3E9000, 'door_bank': 0x41})
        at = {'entrance': 0x3E9000, 'door_bank': 0x3D}
        moved = apply(self.rom, writes_for(self.rom, value, at=at)[0])
        self.assertEqual(door_table(moved), 0x3DD2FC)
        groups = door_groups(moved, GROUPS + 1)
        before = door_groups(self.rom, GROUPS)
        self.assertEqual(len(groups[1]), 4)
        self.assertEqual(groups[1][2:], [b'\x80', b'\xc0'])
        self.assertEqual(groups[1][1], bytes([before[1][1][0] & 0x3F | 0x80]))
        self.assertEqual(groups[0x36], [b'\xc0'])
        self.assertEqual(groups[3], before[3])
        self.assertEqual(moved.d[lorom(0x01F3C9)], 0x5C)
        self.assertEqual(bytes(moved.d[lorom(0x3D8000):lorom(0x3D8000) + 0x52FC]), bytes(self.rom.d[lorom(0x018000):lorom(0x01D2FC)]))
        self.assertEqual(writes_for(moved, value, at=at)[0], [])
        self.assertEqual(writes_for(moved, value)[0], [])
        # 이미 늘린 롬에 맵을 더 붙이면 옮긴 표만 다시 쓰고, 복사본·스텁은 그대로 둔다.
        value['maps'].append({'map': '01/04', 'record': {'copy': '01/00'}, 'attrs': {'copy': '01/00'}})
        writes = writes_for(moved, value)[0]
        self.assertFalse([note for _, _, _, note in writes if '스텁' in note or '복사본' in note or '입구' in note])
        again = apply(moved, writes)
        self.assertEqual(door_table(again), 0x3DD2FC)
        self.assertEqual(door_groups(again, GROUPS + 1)[1][2:], [b'\x80', b'\x80', b'\xc0'])
        self.assertEqual(door_groups(again, GROUPS + 1)[3], before[3])
        self.assertEqual(writes_for(again, value)[0], [])

    def test_readthrough_group_rejected(self):
        value = doc({'map': '36/00', 'record': {'copy': '01/00'}, 'attrs': {'copy': '01/00'}})
        value['groups'] = [{'group': '36', 'entrance': {'copy': '0D'}}]
        # 표 뒤 입구 01:D8C2 의 PHP·PHB·PHK·PLB 와 다음 바이트 C0 이 새 그룹의 문 항목 하나로 읽힌다.
        write(self.rom.d, 0x01D8C6, b'\xc0')
        made = apply(self.rom, writes_for(self.rom, value, at={'entrance': 0x3E9000}, allow_doors=True)[0])
        with self.assertRaisesRegex(ValueError, '넘어 읽힘'):
            writes_for(made, value, at={'door_bank': 0x3D})

    def moved(self):
        value = doc({'map': '01/02', 'record': {'copy': '01/00'}, 'attrs': {'copy': '01/00'}})
        return value, apply(self.rom, writes_for(self.rom, value, at={'door_bank': 0x3D})[0])

    def test_every_entry_jumps_to_its_stub(self):
        _, moved = self.moved()
        for i, entry in enumerate(DOOR_ENTRIES):
            stub = 0x01FED0 + i * 11
            self.assertEqual(bytes(moved.d[lorom(entry):lorom(entry) + 4]), bytes([0x5C, *stub.to_bytes(3, 'little')]))
        # 11:8E54 의 JSL 이 부르는 입구. PLB 뒤 01:D97F 로 돌아간다.
        stub = 0x01FED0 + DOOR_ENTRIES.index(0x01D97B) * 11
        self.assertEqual(bytes(moved.d[lorom(stub):lorom(stub) + 11]), bytes.fromhex('08 8b f4 3d 3d ab ab 5c 7f d9 01'))
        self.assertEqual(lorom(0x01FED0) + 11 * len(DOOR_ENTRIES), lorom(0x01FF12))

    def test_mixed_entries_rejected(self):
        _, moved = self.moved()
        write(moved.d, 0x01D97B, bytes.fromhex('08 8b 4b ab'))
        with self.assertRaisesRegex(ValueError, '섞였'):
            door_table(moved)

    def test_door_bank_must_be_empty(self):
        value = doc({'map': '01/02', 'record': {'copy': '01/00'}, 'attrs': {'copy': '01/00'}})
        data = Rom(bytearray(self.rom.d) + bytes(0x100000))
        write(data.d, 0x3DC000, b'\x01')
        with self.assertRaisesRegex(ValueError, '비어 있지 않음'):
            writes_for(data, value, at={'door_bank': 0x3D})

    def test_stale_door_graphics_rejected(self):
        value, moved = self.moved()
        write(moved.d, 0x01FD9F, b'\x12')
        with self.assertRaisesRegex(ValueError, 'FD9F 가 뱅크 01 과 다름'):
            writes_for(moved, value)

    def test_stale_copy_elsewhere_rejected(self):
        value, moved = self.moved()
        write(moved.d, 0x01F0A0, b'\x12')
        with self.assertRaisesRegex(ValueError, 'F0A0 가 뱅크 01 과 다름'):
            writes_for(moved, value)
        _, moved = self.moved()
        with self.assertRaisesRegex(ValueError, '스텁은 이미'):
            writes_for(moved, value, at={'door_stub': 0x01FF20})


if __name__ == '__main__':
    unittest.main()
