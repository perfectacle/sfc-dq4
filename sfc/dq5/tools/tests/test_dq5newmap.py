"""새 맵 번호: 합성 롬에서 그룹 표 옮기기·목록 밀기, 원래 맵 보존, 입력·한도 검사."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch as mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dq5map import ATTR_SITES, ATTR_TABLE, GROUP_TABLE, GROUPS, POINTER_SITE, Rom, group_spans, lorom, map_pointer
from dq5mapwrite import all_maps
from dq5newmap import FORMAT, writes_for

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
    write(data, POINTER_SITE - 1, bytes([0xBC, 0xD7, 0x8E]))
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
    start, _ = group_spans(rom, attr=True)[0][bc]
    off = lorom(0x230000 | start + bd * 6)
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
                                                      'attrs': {'bytes': [9, 8, 7, 6, 5, 4]}}))
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
                self.assertEqual(writes_for(moved, again)[0], [])

    def test_existing_map_and_new_record_source(self):
        with mock('dq5newmap.encode', return_value=b'\x11\x22'), mock('dq5newmap.entries_for', return_value=[]), \
                mock('pathlib.Path.read_text', return_value='{"format": "dq5map/1"}'):
            writes, size = writes_for(self.rom, doc(
                {'map': '02/01', 'record': {'source': 'x.json'}, 'attrs': {'copy': '02/00'}},
                {'map': '05/00', 'attrs': {'bytes': [0, 0, 0, 0, 0, 0]}}), at={'records': 0x308000})
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
            (doc({'map': '50/52', 'record': {'copy': '01/00'}, 'attrs': {'copy': '01/00'}}), '00~35'),
            (doc({'map': '01/02', 'record': {'copy': '09/09'}, 'attrs': {'copy': '01/00'}}), '없음'),
            (doc({'map': '01/02', 'record': {'copy': '01/00'}, 'attrs': {'bytes': [1, 2, 3]}}), 'bytes'),
            (doc({'map': '01/02', 'record': {'copy': '01/00'}, 'attrs': {'copy': '01/00'}, 'npc': 1}), 'map·record·attrs'),
            (doc({'map': '01/02', 'record': {'source': 'x.json'}, 'attrs': {'copy': '01/00'}}), ''),
            (doc(*many), '넘침'),
            ({'format': FORMAT}, 'maps'),
        ]
        for value, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex((ValueError, OSError), message):
                writes_for(self.rom, value)
        one = doc({'map': '01/02', 'record': {'copy': '01/00'}, 'attrs': {'copy': '01/00'}})
        for at, message in (({'pointer': 0x10FF50}, '뱅크 0F'), ({'attr': 0x238000}, '빈 자리')):
            with self.subTest(at=at), self.assertRaisesRegex(ValueError, message):
                writes_for(self.rom, one, at=at)


if __name__ == '__main__':
    unittest.main()
