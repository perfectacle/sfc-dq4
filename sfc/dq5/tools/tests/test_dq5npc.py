"""인물 그룹 포인터 표: 원래 자리(54그룹)와 dq5npcrelocate.py 가 옮긴 표(늘린 그룹 수)를 합성 롬에서 읽는다."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dq5map import GROUP_TABLE, GROUPS, POINTER_SITE, TABLE_KINDS, Rom, lorom  # noqa: E402
from dq5npc import (BANK_SITE, GROUP_COUNT, GROUP_SITE, NPC_GROUPS, OVERRIDE_LISTS, all_lists, group_pointers,  # noqa: E402
                    map_entries, map_list)

DAY = bytes.fromhex('84 12 cb 85 0a 2c 44 f0')


def put(data, addr, raw):
    data[lorom(addr):lorom(addr) + len(raw)] = raw


def base(maps):
    """맵 포인터 그룹 표(그룹 g 에 maps[g] 개)와 빈 대체 표를 둔 롬."""
    data = bytearray(0x200000)
    start = (GROUP_TABLE & 0xFFFF) - sum(maps) * 3
    starts, cursor = [], start
    for n in maps:
        starts.append(cursor)
        cursor += n * 3
    if len(maps) == GROUPS:
        put(data, GROUP_TABLE, b''.join(s.to_bytes(2, 'little') for s in starts))
    else:
        # dq5newmap.py 가 옮긴 꼴: [그룹마다 시작][끝][0000] 과 표를 읽는 명령·DB 즉값.
        moved = 0x0FFF50
        put(data, moved, b''.join(v.to_bytes(2, 'little') for v in [*starts, cursor, 0]))
        put(data, POINTER_SITE - 1, bytes([0xBC]) + (moved & 0xFFFF).to_bytes(2, 'little'))
        put(data, TABLE_KINDS['pointer']['db'] - 1, bytes([0xA9, 0x0F]))
    put(data, OVERRIDE_LISTS, b'\xff')
    return data


class GroupPointerTests(unittest.TestCase):
    def test_original_table_has_54_groups(self):
        data = base([1] * GROUPS)
        # 그룹마다 빈 목록 하나. 05:8000 부터 이어지고 그룹 표가 바로 뒤.
        lists = 0x058000
        put(data, NPC_GROUPS, b''.join((lists + g & 0xFFFF).to_bytes(2, 'little') for g in range(GROUP_COUNT)))
        rom = Rom(data)
        bank, table, starts = group_pointers(rom)
        self.assertEqual((bank, table, len(starts)), (0x05, NPC_GROUPS, GROUP_COUNT))
        names = [name for _, name in all_lists(rom)]
        self.assertEqual(names[:2], ['00/00', '01/00'])
        self.assertEqual(names[GROUP_COUNT - 1], '35/00')

    def test_relocated_table_counts_new_groups(self):
        # 옮긴 표: 32:8000 에 그룹 36개(+1) 포인터, 바로 뒤에 목록. 그룹 36 은 맵 둘(목록 둘), 그룹 01 은 인물 하나.
        data = base([1] * GROUPS + [2])
        table = 0x328000
        count = GROUPS + 1
        lists = table + count * 2
        put(data, BANK_SITE, bytes([0xA9, 0x32]))
        put(data, GROUP_SITE, bytes([0xB9, 0x00, 0x80]))
        cursor, starts = lists, []
        for g in range(count):
            starts.append(cursor)
            body = (DAY + b'\0') if g == 1 else b'\0\0' if g == GROUPS else b'\0'
            put(data, cursor, body)
            cursor += len(body)
        put(data, table, b''.join((s & 0xFFFF).to_bytes(2, 'little') for s in starts))
        rom = Rom(data)
        bank, at, found = group_pointers(rom)
        self.assertEqual((bank, at, found), (0x32, table, starts))
        names = {name: addr for addr, name in all_lists(rom)}
        self.assertEqual(names['36/00'], starts[GROUPS])
        self.assertEqual(names['36/01'], starts[GROUPS] + 1)
        self.assertNotIn('36/02', names)
        self.assertEqual(map_list(rom, 0x36, 1), starts[GROUPS] + 1)
        self.assertEqual(map_entries(rom, 1, 0), [(starts[1], len(DAY))])

    def test_relocated_group_without_map_group_is_refused(self):
        # 인물 표만 그룹 55개로 옮기고 맵 포인터 그룹 표는 54개 그대로면 맨 뒤 그룹의 맵 수를 알 수 없다.
        data = base([1] * GROUPS)
        table, count = 0x328000, GROUPS + 1
        put(data, BANK_SITE, bytes([0xA9, 0x32]))
        put(data, GROUP_SITE, bytes([0xB9, 0x00, 0x80]))
        lists = table + count * 2
        put(data, table, b''.join((lists + g & 0xFFFF).to_bytes(2, 'little') for g in range(count)))
        with self.assertRaises(ValueError):
            all_lists(Rom(data))

    def test_changed_loader_is_refused(self):
        data = base([1] * GROUPS)
        put(data, BANK_SITE, bytes([0xEA, 0x05]))
        with self.assertRaises(ValueError):
            group_pointers(Rom(data))


if __name__ == '__main__':
    unittest.main()
