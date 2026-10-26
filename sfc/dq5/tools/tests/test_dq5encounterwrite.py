"""조우 격자·실내 구역 연결·고정 무리·이벤트 무리 쓰기의 왕복과 거부."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dq5encounter import (EVENT_COUNT, EVENT_GROUPS, EVENT_SIZE, FIELD_GRIDS, FIELD_WIDTH, FIXED,  # noqa: E402
                          FIXED_COUNT, GROUPS, MAP_TABLE)
from dq5encounterwrite import FORMAT, HIGH_GROUPS, dump, patch  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402

MAPS_START = 0x23F54E


def fixture():
    data = bytearray(0x180000)
    for i, (_, addr, rows) in enumerate(FIELD_GRIDS):
        off = lorom(addr)
        data[off:off + rows * FIELD_WIDTH] = bytes([i + 1]) * (rows * FIELD_WIDTH)
    # 그룹마다 맵 6개, 마지막 그룹이 표 앞까지 나머지를 갖는다.
    for bc in range(GROUPS):
        off = lorom(MAP_TABLE + bc * 2)
        data[off:off + 2] = ((MAPS_START + bc * 36) & 0xFFFF).to_bytes(2, 'little')
    off = lorom(MAPS_START)
    for k in range(((MAP_TABLE - MAPS_START)) // 6):
        data[off + k * 6:off + k * 6 + 6] = bytes([k % 85, 0x14, 0xFF, 0x07, 0x01, 0x09])
    # 그룹 50 이상: 23:FDD6 에 그룹 51 하나, 그 목록에 맵 50·51.
    off = lorom(HIGH_GROUPS)
    data[off:off + 4] = bytes([0x51, 0xE0, 0xFD, 0xFF])
    off = lorom(0x23FDE0)
    data[off:off + 15] = bytes.fromhex('50 ff ff 3d 13 01 09 51 ff ff 3e 13 01 09 ff')
    for g in range(FIXED_COUNT):
        off = lorom(FIXED + g * 6)
        data[off:off + 6] = bytes([0x10 + g, 0x20, 0xFF, 0x13, 0x02, 0x60])
    for g in range(EVENT_COUNT):
        off = lorom(EVENT_GROUPS + g * EVENT_SIZE)
        data[off:off + EVENT_SIZE] = bytes([0xC0, g, 0x05, 0xFF, 0xFF, 1, 2, 0, 0, 0, 7, 0, 9])
    return bytes(data)


def apply(data, manifest):
    out = bytearray(data)
    for w in manifest['writes']:
        off = lorom(int(w['at'].replace(':', ''), 16))
        raw = bytes.fromhex(w['hex'])
        assert data[off:off + len(raw)] == bytes.fromhex(w['orig'])
        out[off:off + len(raw)] = raw
    return bytes(out)


class EncounterWriteTest(unittest.TestCase):
    def setUp(self):
        self.data = fixture()
        self.rom = Rom(self.data)

    def test_round_trip_writes_nothing(self):
        self.assertEqual(patch(self.rom, dump(self.rom))['writes'], [])

    def test_edits_only_named_values(self):
        grid = dump(self.rom)['field_grids'][0]
        grid['rows'][1][10] = 0x0D
        doc = {'format': FORMAT, 'field_grids': [grid],
               'maps': [{'map': '01/02', 'areas': [0x0D, 255, 3]}],
               'fixed_groups': [{'index': 5, 'members': [{'monster': 0xB2, 'count_code': 14}]}],
               'event_groups': [{'index': 1, 'members': [{'monster': 3, 'count': 2}, {'monster': 0, 'count': 9},
                                                         {'monster': 4, 'count': 1}]}]}
        out = Rom(apply(self.data, patch(self.rom, doc)))
        after = dump(out)
        self.assertEqual(after['field_grids'][0]['rows'][1][10], 0x0D)
        self.assertEqual(sum(v != 1 for row in after['field_grids'][0]['rows'] for v in row), 1)
        maps = {m['map']: m['areas'] for m in after['maps']}
        self.assertEqual(maps['01/02'], [0x0D, 255, 3])
        self.assertEqual(maps['01/03'], [9, 0x14, 0xFF])
        entry = lorom(MAPS_START + 8 * 6)
        self.assertEqual(out.d[entry + 3:entry + 6], bytes([0x07, 0x01, 0x09]))
        fixed = lorom(FIXED + 5 * 6)
        self.assertEqual(out.d[fixed:fixed + 6], bytes([0xB2, 0xFF, 0xFF, 0xE3, 0x02, 0x60]))
        event = lorom(EVENT_GROUPS + EVENT_SIZE)
        self.assertEqual(out.d[event:event + EVENT_SIZE], bytes([0xC0, 3, 0, 4, 0xFF, 2, 9, 1, 0, 0, 7, 0, 9]))
        self.assertEqual(after['event_groups'][2], dump(self.rom)['event_groups'][2])

    def test_event_flags_alone(self):
        manifest = patch(self.rom, {'format': FORMAT, 'event_groups': [{'index': 0, 'flags': 0x40}]})
        self.assertEqual([w['hex'] for w in manifest['writes']], ['40 00 05 ff ff 01 02 00 00 00 07 00 09'])

    def test_high_group_maps_and_area_count(self):
        maps = {row['map']: row['areas'] for row in dump(self.rom)['maps']}
        self.assertEqual((maps['51/50'], maps['51/51']), ([0xFF, 0xFF, 0x3D], [0xFF, 0xFF, 0x3E]))
        manifest = patch(self.rom, {'format': FORMAT, 'maps': [{'map': '51/51', 'areas': [1, 2, 3]}]})
        self.assertEqual([w['at'] for w in manifest['writes']], ['23:FDE8'])
        self.assertEqual(Rom(apply(self.data, manifest)).d[lorom(0x23FDE8):lorom(0x23FDE8) + 6], bytes.fromhex('010203130109'))
        doc = {'format': FORMAT, 'maps': [{'map': '01/02', 'areas': [85, 86, 255]}]}
        with self.assertRaises(ValueError):
            patch(self.rom, doc)
        self.assertEqual(len(patch(self.rom, doc, areas=87)['writes']), 1)
        grid = dump(self.rom)['field_grids'][0]
        doc = {'format': FORMAT, 'field_grids': [{**grid, 'rows': [[86] * FIELD_WIDTH] + grid['rows'][1:]}]}
        self.assertEqual(len(patch(self.rom, doc, areas=87)['writes']), 1)
        for areas in (84, 256, True):
            with self.subTest(areas=areas), self.assertRaises(ValueError):
                patch(self.rom, doc, areas=areas)
        twice = bytearray(self.data)
        twice[lorom(HIGH_GROUPS) + 3:lorom(HIGH_GROUPS) + 7] = bytes([0x51, 0xE0, 0xFD, 0xFF])
        with self.assertRaises(ValueError):
            dump(Rom(bytes(twice)))
        for case in ({'map': '51/52', 'areas': [1, 1, 1]}, {'map': '50/50', 'areas': [1, 1, 1]}):
            with self.subTest(case=case), self.assertRaises(ValueError):
                patch(self.rom, {'format': FORMAT, 'maps': [case]})

    def test_rejects(self):
        grid = dump(self.rom)['field_grids'][3]
        bad_grid = {**grid, 'rows': grid['rows'][:-1]}
        wide = {**grid, 'rows': [row + [0] for row in grid['rows']]}
        high = {**grid, 'rows': [[85] * FIELD_WIDTH] + grid['rows'][1:]}
        cases = [
            {'field_grids': [bad_grid]}, {'field_grids': [wide]}, {'field_grids': [high]},
            {'maps': [{'map': '36/00', 'areas': [1, 1, 1]}]},
            {'maps': [{'map': '01/02', 'areas': [1, 254, 1]}]},
            {'maps': [{'map': '01/02', 'areas': [1, 1]}]},
            {'maps': [{'map': '01/02', 'areas': [1, 1, 1], 'background': 2}]},
            {'fixed_groups': [{'index': 9, 'members': [{'monster': 0, 'count_code': 0}]}]},
            {'fixed_groups': [{'index': 0, 'members': []}]},
            {'fixed_groups': [{'index': 0, 'members': [{'monster': 0, 'count_code': 15}]}]},
            {'fixed_groups': [{'index': 0, 'members': [{'monster': 0}]}]},
            {'event_groups': [{'index': 64, 'flags': 0}]},
            {'event_groups': [{'index': 0, 'members': [{'monster': 0, 'count': 0}]}]},
            {'event_groups': [{'index': 0, 'members': [{'monster': 236, 'count': 1}]}]},
            {'event_groups': [{'index': 0, 'members': [{'monster': 0, 'count': 1}] * 5}]},
            {'event_groups': [{'index': 0, 'flags': 0}, {'index': 0, 'flags': 1}]},
            {'event_groups': [{'index': 0, 'flags': 0x03}]}, {'event_groups': [{'index': 0, 'flags': 0x08}]},
            {'event_groups': [{'index': 0, 'flags': 0x04}]},
            {'maps': [{'map': 'zz', 'areas': [1, 1, 1]}]}, {'maps': [{'map': '21/02/03', 'areas': [1, 1, 1]}]},
            {'maps': [{'map': '01/2', 'areas': [1, 1, 1]}]},
            {'maps': [{'map': '01/02', 'areas': [1, 255.0, 1]}]},
            {'maps': [{'map': '01/02', 'areas': [1, 1, 1]}, {'map': '01/02', 'areas': [2, 1, 1]}]},
            {'field_grids': [{'index': 5, 'rows': []}]},
            {'field_grids': [{**grid, 'condition': '$1949=0 $1948=0'}]},
            {'unknown': []},
        ]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                patch(self.rom, {'format': FORMAT, **case})
        with self.assertRaises(ValueError):
            patch(self.rom, {'format': 'dq5encounter/0'})


if __name__ == '__main__':
    unittest.main()
