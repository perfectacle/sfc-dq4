"""인물 레코드 필드 오프셋, 모르는 비트 보존, 낮·밤 공유 바이트, 조건 표 입력 검사."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch as mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dq5map import Rom, lorom  # noqa: E402
from dq5npc import FIELDS, entry_size, parse  # noqa: E402
from dq5npcrecord import FORMAT, decode, edits, entry_bytes, offsets, patch  # noqa: E402

LIST, ALT = 0x058000, 0x108000
# 한 벌 낮 엔트리: 대화 412, 기타 bit7(Y-1)·bit6·bit3 과 걸음 3, (5,9) 오른쪽, 그림 2C, 이동 44, 추가 값 F0.
DAY = bytes.fromhex('84 12 cb 85 0a 2c 44 f0')
# 한 벌 밤 엔트리, 추가 값 없음, 스크립트 1바이트.
NIGHT = bytes.fromhex('70 de 44 87 20 18 00 01 16')
# 두 벌 엔트리: 마스크 3E 는 bit7 이 0 이라 +2 가 밤 b0, bit6 이 0 이라 대화 하위만 낮·밤 둘이고 나머지는 공유.
# 낮 b0 bit4 라 낮 추가 값은 없고 밤 추가 값 F0 만 있다.
BOTH = bytes.fromhex('d1 3e c2 20 30 03 05 06 2c 44 f0')


def fixture(*records):
    data = bytearray(0x90000)
    at, rows = LIST, []
    for record in records:
        data[lorom(at):lorom(at) + len(record)] = record
        rows.append(at)
        at += len(record)
    return Rom(data), rows


def run(rom, rows, **sections):
    lists = {LIST: ('01/02', rows), ALT: ('01/02 대체', [])}
    overrides = [(0x128449, bytes([1, 2, 0x1D, 0x10, 0x00, 0x80]))]
    no_npc = [(0x12839C, bytes([1, 2, 0x82, 0x80]))]
    layout = (lists, overrides, no_npc, {(1, 2), (1, 3)}, {ALT})
    with mock('dq5npcrecord.layout', return_value=layout):
        return patch(rom, {'format': FORMAT, **sections})['writes']


class OffsetTests(unittest.TestCase):
    def test_offsets_match_loader(self):
        rom, rows = fixture(DAY, NIGHT, BOTH)
        for at in rows:
            data = bytes(rom.d[lorom(at):lorom(at) + entry_size(rom, at)])
            for time, where in offsets(data).items():
                f = parse(rom, at, time == 'night')
                if f is None:
                    continue
                with self.subTest(at=hex(at), time=time):
                    self.assertEqual([data[where[k]] for k in FIELDS], [f[k] & 0xFF for k in FIELDS])
                    self.assertEqual(0xFF if where['extra'] is None else data[where['extra']], f['extra'])
                    self.assertEqual(data[where['flags']], f['flags'])

    def test_decode_uses_placed_cell(self):
        where = offsets(DAY)['day']
        value = decode(DAY, where)
        self.assertEqual((value['x'], value['y'], value['facing'], value['talk']), (5, 9, 'down', 0x412))
        self.assertEqual((value['step'], value['walk_anim'], value['stand_anim']), (3, 15, 0))


class EntryTests(unittest.TestCase):
    def setUp(self):
        self.rom, self.rows = fixture(DAY, NIGHT, BOTH)

    def edit(self, index, row):
        return entry_bytes(self.rom, self.rows[index], row, 'test')

    def test_unchanged_round_trip(self):
        for i, raw in enumerate((DAY, NIGHT, BOTH)):
            self.assertEqual(self.edit(i, {}), raw)

    def test_fields_keep_unknown_bits(self):
        new = self.edit(0, {'fields': {'x': 6, 'y': 10, 'facing': 'left', 'talk': 0x7FF, 'step': 5,
                                       'gfx': 0x18, 'layer': 2, 'interval': 1, 'speed': 2, 'walk_anim': 2,
                                       'stand_anim': 3}})
        # b0 위 니블(낮·스크립트 없음·추가 값 있음)과 기타 bit3-7 은 그대로, Y 는 기타 bit7 만큼 하나 크게 저장.
        self.assertEqual(new, bytes([0x87, 0xFF, 0xCD, 0x86, 0x80 | 11, 0x18, 0x86, 0x23]))
        self.assertEqual(entry_size(fixture(new)[0], LIST), len(DAY))

    def test_time_switch_only_for_single_entries(self):
        self.assertEqual(self.edit(1, {'time': 'day'})[0], 0xB0)
        for index, row in ((2, {'time': 'day'}), (2, {'fields': {'x': 1}}), (0, {'time': 'both'}),
                           (0, {'day': {'x': 1}}), (0, {'time': []}), (2, {'time': {}})):
            with self.subTest(row=row), self.assertRaises(ValueError):
                self.edit(index, row)

    def test_shared_bytes_must_agree(self):
        same = self.edit(2, {'day': {'x': 9}, 'night': {'x': 9}})
        self.assertEqual(same[offsets(BOTH)['day']['x']], 9)
        split = self.edit(2, {'day': {'talk': 0x111}, 'night': {'talk': 0x222}})
        where = offsets(BOTH)
        self.assertEqual((split[0] & 0x0F, split[2] & 0x0F), (1, 2))
        self.assertEqual((split[where['day']['talk']], split[where['night']['talk']]), (0x11, 0x22))
        for row in ({'day': {'x': 9}}, {'day': {'gfx': 1}, 'night': {'gfx': 2}}):
            with self.subTest(row=row), self.assertRaises(ValueError):
                self.edit(2, row)

    def test_rejects_bad_values(self):
        for row in ({'fields': {'walk_anim': 1}}, {'fields': {'x': 128}}, {'fields': {'x': True}},
                    {'fields': {'facing': 'north'}}, {'fields': {'talk': 0x1000}}, {'fields': {'hidden': 1}},
                    {'fields': {'y': -1}}, {'fields': {'speed': 4}}, {'fields': 1}):
            with self.subTest(row=row), self.assertRaises(ValueError):
                self.edit(1, row)
        with self.assertRaises(ValueError):
            # 기타 bit7 이 켜진 엔트리는 저장 Y 가 127 을 넘지 않게 y 126 까지.
            self.edit(0, {'fields': {'y': 127}})


class DocumentTests(unittest.TestCase):
    def setUp(self):
        self.rom, self.rows = fixture(DAY, NIGHT, BOTH)

    def test_writes_only_changes(self):
        writes = run(self.rom, self.rows, entries=[{'list': '05:8000', 'index': 1, 'name': '01/02',
                                                    'address': '05:8008', 'fields': {'gfx': 0x2C}},
                                                   {'list': '05:8000', 'index': 0}],
                     overrides=[{'index': 0, 'when': 'off', 'map': '01/03'}], no_npc=[{'index': 0}])
        self.assertEqual([(w['at'], w['hex'], w['orig']) for w in writes], [
            ('05:8008', '70 de 44 87 20 2c 00 01 16', '70 de 44 87 20 18 00 01 16'),
            ('12:8449', '01 03 9d 10 00 80', '01 02 1d 10 00 80')])

    def test_time_switch_keeps_map_count(self):
        # 01/02 는 원본에서 낮·밤 2명씩 놓는다. 한쪽을 3명으로 늘리는 전환은 거부하고, 맞바꾸는 전환은 받는다.
        for index, time in ((1, 'day'), (0, 'night')):
            with self.subTest(index=index), self.assertRaises(ValueError):
                run(self.rom, self.rows, entries=[{'list': '05:8000', 'index': index, 'time': time}])
        writes = run(self.rom, self.rows, entries=[{'list': '05:8000', 'index': 0, 'time': 'night'},
                                                   {'list': '05:8000', 'index': 1, 'time': 'day'}])
        self.assertEqual([w['hex'][:2] for w in writes], ['44', 'b0'])

    def test_rejects_bad_documents(self):
        bad = [{'entries': [{'list': '05:8001', 'index': 0}]},
               {'entries': [{'list': '05:8000', 'index': 3}]},
               {'entries': [{'list': '05:8000', 'index': True}]},
               {'entries': [{'list': '05:8000', 'index': 0, 'name': '01/03'}]},
               {'entries': [{'list': '05:8000', 'index': 0, 'address': '05:8001'}]},
               {'entries': [{'list': '05:8000', 'index': 0}, {'list': '05:8000', 'index': 0}]},
               {'entries': [{'list': '10:8000', 'index': 0}]},
               {'entries': [{'list': '05:8000', 'index': 0, 'extra': 1}]},
               {'overrides': [{'index': 0, 'list': '10:8001'}]},
               {'overrides': [{'index': 0, 'map': '09/09'}]},
               {'overrides': [{'index': 0, 'mask': 3}]},
               {'overrides': [{'index': 0, 'mask': True}]},
               {'overrides': [{'index': 0, 'flag': 128}]},
               {'overrides': [{'index': 0, 'when': 'yes'}]},
               {'overrides': [{'index': 1}]},
               {'overrides': [{'index': 0}, {'index': 0}]},
               {'no_npc': [{'index': 0, 'list': '10:8000'}]},
               {'unknown': []}]
        for doc in bad:
            with self.subTest(doc=doc), self.assertRaises(ValueError):
                run(self.rom, self.rows, **doc)
        with self.assertRaises(ValueError):
            with mock('dq5npcrecord.layout'):
                patch(self.rom, {'format': 'dq5npcrecord/0'})


if __name__ == '__main__':
    unittest.main()
