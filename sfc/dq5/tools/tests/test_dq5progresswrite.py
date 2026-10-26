"""고정 성장·조우·상점 슬롯과 실제 디코더의 의미 대조."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dq5encounter import AREAS, AREA_COUNT, AREA_SIZE, area  # noqa: E402
from dq5growth import exp_at, stat_at  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402
from dq5progresswrite import (  # noqa: E402
    AREA_LONG, AREA_OPERANDS, FORMAT, GROWTH, GROWTH_BASE, RECORD, SHOP_BANK, SHOP_COUNTS, SHOP_TABLE, STATS,
    STAT_OFFSETS, dump, edits, encode_growth, growth_fields, parse_at, patch, shop_records, table_bases,
)
from dq5shop import COIN_PRICES, END, LISTS, MEDAL_PRICES, prize_lists, shop_lists  # noqa: E402


def doc(**parts):
    return {'format': FORMAT, **parts}


def fixture():
    data = bytearray([0xA5]) * 0x180000
    for base, count in GROWTH.values():
        for i in range(count):
            off = lorom(base + i * RECORD)
            data[off:off + 6] = bytes([3, 10, 5, 10, 20, 0xA5])
            data[off + 9:off + 13] = bytes([1] * 4)
            for start in STAT_OFFSETS:
                data[off + start:off + start + 4] = bytes([10, 15, 20, 25])
                data[off + start + 8] = 40
    for i in range(AREA_COUNT):
        off = lorom(AREAS + i * AREA_SIZE)
        data[off:off + AREA_SIZE] = bytes([5] + [0x49] * 10 + [0x11] + [1] * 10)
    cursor = LISTS + 8
    for kind, count in enumerate(SHOP_COUNTS):
        off = lorom(LISTS + kind * 2)
        data[off:off + 2] = (cursor & 0xFFFF).to_bytes(2, 'little')
        for i in range(count):
            size = 4 if kind == 0 and i < 4 else 6
            key = 0x15 if kind == 3 and i == 0 else 0x16 if kind == 3 and i == 1 else i
            raw = bytes([key] + [1] * size + [255])
            off = lorom(cursor)
            data[off:off + len(raw)] = raw
            cursor += len(raw)
    assert cursor == END
    for at in SHOP_BANK:
        data[lorom(at)] = 0x04
    for at in SHOP_TABLE:
        data[lorom(at):lorom(at) + 2] = (LISTS & 0xFFFF).to_bytes(2, 'little')
    data[lorom(MEDAL_PRICES):lorom(MEDAL_PRICES) + 6] = bytes(range(1, 7))
    for i in range(6):
        off = lorom(COIN_PRICES + i * 3)
        data[off:off + 3] = (100 * (i + 1)).to_bytes(3, 'little')
    for kind, at in GROWTH_BASE.items():
        data[lorom(at):lorom(at) + 3] = bytes([0xA2]) + (GROWTH[kind][0] & 0xFFFF).to_bytes(2, 'little')
    for at, field in AREA_OPERANDS:
        data[lorom(at)] = 0xA9 if at == 0x23EA50 else 0xBD
        data[lorom(at + 1):lorom(at + 3)] = ((AREAS & 0xFFFF) + field).to_bytes(2, 'little')
    data[lorom(AREA_LONG)] = 0xBF
    data[lorom(AREA_LONG + 1):lorom(AREA_LONG + 4)] = AREAS.to_bytes(3, 'little')
    return bytes(data)


def apply(data, manifest):
    updated = bytearray(data)
    for w in manifest['writes']:
        off = lorom(int(w['at'].replace(':', ''), 16))
        raw = bytes.fromhex(w['hex'])
        if 'orig' in w:
            assert data[off:off + len(raw)] == bytes.fromhex(w['orig'])
        updated[off:off + len(raw)] = raw
    return bytes(updated)


class ProgressWriteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = fixture()
        cls.rom = Rom(cls.data)

    def test_roundtrip_reserved_and_unused(self):
        rows = edits(self.rom, dump(self.rom))
        self.assertEqual(sum(len(old) for _, _, old, _ in rows), 6518)
        self.assertTrue(all(old == new for _, new, old, _ in rows))
        self.assertEqual(patch(self.rom, dump(self.rom))['writes'], [])

    def test_growth_semantic_readback_and_unused(self):
        base = GROWTH['person'][0]
        updated = apply(self.data, patch(self.rom, doc(growth=[{
            'kind': 'person', 'index': 0, 'exp2': 20, 'stats': {'hp': [10, 16, 20, 25, 40]},
        }])))
        rom = Rom(updated)
        self.assertEqual(exp_at(rom, base, 2), 20)
        self.assertEqual(stat_at(rom, base, 0, 5), 32)
        self.assertEqual(stat_at(rom, base, 2, 5), stat_at(self.rom, base, 2, 5))
        changed = {i for i, (a, b) in enumerate(zip(self.data, updated)) if a != b}
        self.assertEqual(changed, {lorom(base) + 1, lorom(base) + STAT_OFFSETS[0] + 1})

    def test_growth_point_count_change_preserves_unused(self):
        raw = self.data[lorom(GROWTH['person'][0]):lorom(GROWTH['person'][0]) + RECORD]
        changed = encode_growth(raw, {'breaks': [10], 'multipliers': [1, 1],
                                      'stats': {name: [10, 20, 40] for name in STATS}})
        self.assertEqual(changed[4:9], raw[4:9])
        self.assertEqual(changed[11:17], raw[11:17])
        for off in STAT_OFFSETS:
            self.assertEqual(changed[off + 2:off + 8], raw[off + 2:off + 8])

    def test_original_exception_preserved_new_decrease_rejected(self):
        raw = bytearray(self.data[lorom(GROWTH['person'][0]):lorom(GROWTH['person'][0]) + RECORD])
        raw[4] = raw[3]
        raw[STAT_OFFSETS[0]] = 100
        self.assertEqual(encode_growth(raw, growth_fields(raw)), raw)
        changed = encode_growth(raw, {'exp2': 20})
        self.assertEqual(changed[2:], raw[2:])
        with self.assertRaises(ValueError):
            encode_growth(raw, {'breaks': [5, 5, 21]})
        with self.assertRaises(ValueError):
            encode_growth(raw, {'stats': {'hp': [101, 15, 20, 25, 40]}})

    def test_encounter_packed_readback(self):
        value = {'index': 0, 'slots': [{'index': 5, 'monster': 235, 'weight': 7, 'count_code': 6}],
                 'fixed': {'group': 8, 'weight': 3}, 'rate_index': 5, 'species_weights': [1, 2, 3],
                 'flag_1000': 2, 'flag_1010': True, 'fixed_night_only': True}
        updated = apply(self.data, patch(self.rom, doc(encounters=[value])))
        a = area(Rom(updated), 0)
        self.assertEqual((a['monsters'][5], a['weights'][5], a['count_codes'][5]), (235, 7, 6))
        self.assertEqual((a['fixed_group'], a['weights'][10]), (8, 3))
        self.assertEqual(a['species_weights'], [1, 2, 3])
        self.assertEqual((a['flag_1000'], a['flag_1010'], a['fixed_night_only']), (2, 1, 1))
        off = lorom(AREAS)
        self.assertEqual([(updated[off + i] >> 7) & 1 for i in (5, 6, 7)], [1, 0, 1])
        for i in range(5, 11):
            self.assertEqual(updated[off + i] & 64, self.data[off + i] & 64)
        self.assertEqual(updated[off + 10], self.data[off + 10])

    def test_shop_and_price_readback(self):
        before = shop_lists(self.rom)
        value = {'kind': 0, 'index': 1, 'items': [215, 2, 3, 4]}
        updated = apply(self.data, patch(self.rom, doc(shops=[value], medal_prices=[7] * 6, coin_prices=[0xFFFFFF] * 6)))
        after = shop_lists(Rom(updated))
        self.assertEqual(after[1], (0, before[1][1], [215, 2, 3, 4]))
        self.assertEqual(before[:1] + before[2:], after[:1] + after[2:])
        prizes = prize_lists(Rom(updated))
        self.assertEqual([price for _, price in prizes[0][1]], [7] * 6)
        self.assertEqual([price for _, price in prizes[1][1]], [0xFFFFFF] * 6)
        self.assertEqual(updated[lorom(LISTS):lorom(LISTS) + 8], self.data[lorom(LISTS):lorom(LISTS) + 8])
        self.assertEqual(updated[lorom(END) + 24:], self.data[lorom(END) + 24:])

    def test_shop_resize_in_place_and_append(self):
        updated = Rom(apply(self.data, patch(self.rom, doc(shops=[
            {'kind': 1, 'index': 0, 'items': [9] * 6}, {'kind': 1, 'index': 1, 'items': [3]},
            {'kind': 2, 'index': 0, 'items': [4]}, {'kind': 3, 'index': 5, 'key': 0x30, 'items': [7, 8]}]))))
        lists = {key: raw for key, (_, raw) in shop_records(updated).items()}
        self.assertEqual(lists[1, 0][1:-1], bytes([9] * 6))
        self.assertEqual(lists[1, 1][1:-1], bytes([3]))
        self.assertEqual(lists[3, 5], bytes([0x30, 7, 8, 255]))
        self.assertEqual(len(lists), sum(SHOP_COUNTS) + 1)
        self.assertEqual(patch(updated, dump(updated))['writes'], [])
        with self.assertRaisesRegex(ValueError, 'shop-at'):
            patch(self.rom, doc(shops=[{'kind': 0, 'index': i, 'items': [1] * 6} for i in range(11)]))

    def test_shop_relocation(self):
        big = doc(shops=[{'kind': 0, 'index': i, 'items': [1] * 6} for i in range(11)])
        manifest = patch(self.rom, big, shop_at=0x0BFBB0)
        moved = Rom(apply(self.data, manifest))
        self.assertEqual(moved.d[lorom(SHOP_BANK[0])], 0x0B)
        lists = shop_records(moved)
        self.assertEqual(lists[0, 0][0], 0x0BFBB8)
        self.assertEqual(lists[0, 10][1][1:-1], bytes([1] * 6))
        self.assertEqual(patch(moved, dump(moved))['writes'], [])
        # 옮긴 자리는 끝 표시 FF 한 바이트 말고는 남는 자리가 없어 제자리로는 늘릴 수 없다.
        with self.assertRaisesRegex(ValueError, 'shop-at'):
            patch(moved, doc(shops=[{'kind': 3, 'index': 5, 'key': 9, 'items': [2]}]))
        shrunk = Rom(apply(bytes(moved.d), patch(moved, doc(shops=[{'kind': 3, 'index': 4, 'items': [3]}]))))
        self.assertEqual(shop_records(shrunk)[3, 4][1], bytes([shop_records(moved)[3, 4][1][0], 3, 255]))
        self.assertEqual(len(shop_records(shrunk)), len(shop_records(moved)))
        grown = Rom(apply(bytes(moved.d), patch(moved, doc(shops=[{'kind': 0, 'index': 11, 'key': 9, 'items': [2]}]),
                                                shop_at=0x0BFBB0)))
        self.assertEqual(shop_records(grown)[0, 11][1], bytes([9, 2, 255]))
        self.assertEqual(shop_records(grown)[1, 0][0], shop_records(moved)[1, 0][0] + 3)
        for bad in (0x40FBB0, 0x0B7000, 0x0BFFF0):
            with self.subTest(at=bad), self.assertRaises(ValueError):
                patch(self.rom, big, shop_at=bad)

    def with_operands(self):
        return self.data

    def test_append_and_relocate(self):
        data = self.with_operands()
        rom = Rom(data)
        self.assertEqual(table_bases(rom), {'person': GROWTH['person'][0], 'monster': GROWTH['monster'][0],
                                            'area': AREAS})
        person_count, monster_count = GROWTH['person'][1], GROWTH['monster'][1]
        change = doc(growth=[{'kind': 'person', 'index': person_count, 'base': 0, 'exp2': 33},
                             {'kind': 'person', 'index': person_count + 1, 'base': 3},
                             {'kind': 'person', 'index': 0, 'exp2': 44}],
                     encounters=[{'index': AREA_COUNT, 'base': 1, 'level': 77},
                                 {'index': 2, 'level': 66}])
        places = {'area': 0x23C242, 'person': AREAS}
        manifest = patch(rom, change, places=places, reuse_names=True)
        updated = Rom(apply(data, manifest))
        bases = table_bases(updated)
        self.assertEqual(bases, {'person': AREAS, 'monster': GROWTH['monster'][0], 'area': 0x23C242})
        old_people = [growth_fields(rom.d[lorom(GROWTH['person'][0] + i * RECORD):][:RECORD]) for i in range(person_count)]
        new_people = [growth_fields(updated.d[lorom(AREAS + i * RECORD):][:RECORD]) for i in range(person_count + 2)]
        self.assertEqual(new_people[0]['exp2'], 44)
        self.assertEqual(new_people[1:person_count], old_people[1:])
        self.assertEqual(new_people[person_count], {**old_people[0], 'exp2': 33})
        self.assertEqual(new_people[person_count + 1], old_people[3])
        new_areas = [updated.d[lorom(0x23C242 + i * AREA_SIZE):][:AREA_SIZE] for i in range(AREA_COUNT + 1)]
        self.assertEqual(new_areas[AREA_COUNT][0], 77)
        self.assertEqual(new_areas[AREA_COUNT][1:], new_areas[1][1:])
        self.assertEqual(new_areas[2][0], 66)
        self.assertEqual(updated.d[lorom(GROWTH['monster'][0]):][:RECORD * monster_count],
                         rom.d[lorom(GROWTH['monster'][0]):][:RECORD * monster_count])

    def test_append_and_relocate_rejects(self):
        rom = Rom(self.with_operands())
        person_count = GROWTH['person'][1]
        cases = [
            (doc(growth=[{'kind': 'person', 'index': person_count, 'base': 0}]), {}, False),
            (doc(growth=[{'kind': 'person', 'index': person_count + 1, 'base': 0}]), {'person': 0x23FF20}, False),
            (doc(growth=[{'kind': 'person', 'index': person_count}]), {'person': AREAS}, False),
            (doc(growth=[{'kind': 'person', 'index': 0, 'base': 1}]), {}, False),
            (doc(growth=[{'kind': 'person', 'index': 64, 'base': 0}]), {'person': AREAS}, False),
            (doc(encounters=[{'index': AREA_COUNT, 'base': 0}]), {'area': 0x23C242}, False),
            (doc(encounters=[{'index': 255, 'base': 0}]), {'area': 0x23C242}, True),
            (doc(), {'area': 0x23FF20}, False),
            (doc(), {'person': 0x23FF20, 'monster': 0x23FF20}, False),
            (doc(), {'shop': 0x23FF20}, False),
            # 옮기지 않은 사람 표 자리로 구역 표가 넘어감
            (doc(), {'area': AREAS + 0x10}, False),
            # 둘 다 빈 자리 안이지만 서로 겹침(구역 1,870바이트를 이름 자리 끝에서 4,000바이트 앞에 두고 사람을 그 안에)
            (doc(), {'area': 0x23D6A1 - 4000, 'person': 0x23D6A1 - 4000 + 100}, True),
        ]
        for change, places, reuse in cases:
            with self.subTest(change=change, places=places), self.assertRaises(ValueError):
                patch(rom, change, places=places, reuse_names=reuse)
        # 몬스터 표를 이름 자리로 옮기고, 떠난 자리에 사람 표를 자기 원래 자리와 겹치게 둔다.
        manifest = patch(rom, doc(growth=[{'kind': 'monster', 'index': GROWTH['monster'][1], 'base': 2}]),
                         places={'monster': 0x23C242, 'person': GROWTH['person'][0] + RECORD}, reuse_names=True)
        updated = Rom(apply(self.data, manifest))
        self.assertEqual(table_bases(updated)['monster'], 0x23C242)
        self.assertEqual(table_bases(updated)['person'], GROWTH['person'][0] + RECORD)
        self.assertEqual(updated.d[lorom(0x23C242 + GROWTH['monster'][1] * RECORD):][:RECORD],
                         rom.d[lorom(GROWTH['monster'][0] + 2 * RECORD):][:RECORD])
        with self.assertRaises(ValueError):
            dump(updated)
        broken = bytearray(self.data)
        broken[lorom(AREA_OPERANDS[0][0])] = 0xEA
        with self.assertRaises(ValueError):
            table_bases(Rom(bytes(broken)))
        # 원래 자리로 「옮기면」 바뀌는 바이트가 없어 쓰기가 없다.
        self.assertEqual(patch(rom, doc(), places={'person': GROWTH['person'][0]})['writes'], [])
        for value in ('24:8000', '23:7FFF', '238000', '23:80000', None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_at(value, 'x')

    def test_invalid_documents(self):
        bad = [None, [], {}, doc(extra=[]), doc(growth=None), doc(growth=[None]),
               doc(growth=[{'kind': [], 'index': 0}]), doc(growth=[{'kind': 'person', 'index': 11}]),
               doc(growth=[{'kind': 'monster', 'index': 42}]),
               doc(growth=[{'kind': 'person', 'index': True}]),
               doc(growth=[{'kind': 'person', 'index': 0, 'stats': {'unknown': []}}]),
               doc(growth=[{'kind': 'person', 'index': 0, 'breaks': [10]}]),
               doc(growth=[{'kind': 'person', 'index': 0, 'breaks': [5, 4, 20]}]),
               doc(growth=[{'kind': 'person', 'index': 0, 'stats': {'hp': [20, 5, 20, 25, 40]}}]),
               doc(encounters=[{'index': 85}]), doc(encounters=[{'index': 0, 'slots': None}]),
               doc(encounters=[{'index': 0, 'slots': [{'index': 10}]}]),
               doc(encounters=[{'index': 0, 'slots': [{'index': 0, 'monster': 236}]}]),
               doc(encounters=[{'index': 0, 'fixed': {'group': 9}}]),
               doc(encounters=[{'index': 0, 'rate_index': 8}]),
               doc(encounters=[{'index': 0, 'flag_1010': 1}]),
               doc(encounters=[{'index': 0, 'species_weights': [0, 0, 0]}]),
               doc(encounters=[{'index': 0, 'slots': [{'index': i, 'weight': 0} for i in range(10)], 'fixed': {'weight': 0}}]),
               doc(shops=[{'kind': 4, 'index': 0}]), doc(shops=[{'kind': 0, 'index': 11}]),
               doc(shops=[{'kind': 0, 'index': 0, 'key': 255}]),
               doc(shops=[{'kind': 0, 'index': 0, 'items': []}]),
               doc(shops=[{'kind': 0, 'index': 0, 'items': [1] * 7}]),
               doc(shops=[{'kind': 0, 'index': 0, 'items': [216] * 4}]),
               doc(shops=[{'kind': 0, 'index': 12, 'key': 9, 'items': [1]}]),
               doc(shops=[{'kind': 0, 'index': 11, 'items': [1]}]),
               doc(shops=[{'kind': 0, 'index': 11, 'key': 255, 'items': [1]}]),
               doc(medal_prices=[0] * 5), doc(coin_prices=[0x1000000] * 6)]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                patch(self.rom, value)

    def test_duplicates(self):
        for value in (doc(growth=[{'kind': 'person', 'index': 0}] * 2),
                      doc(encounters=[{'index': 0}] * 2), doc(shops=[{'kind': 0, 'index': 0}] * 2),
                      doc(encounters=[{'index': 0, 'slots': [{'index': 0}] * 2}])):
            with self.assertRaises(ValueError):
                patch(self.rom, value)

    def test_short_rom_and_shop_terminator(self):
        with self.assertRaises(ValueError):
            dump(Rom(b''))
        data = bytearray(self.data)
        data[lorom(END) - 1] = 1
        with self.assertRaises(ValueError):
            patch(Rom(data), doc(shops=[{'kind': 3, 'index': 4}]))


if __name__ == '__main__':
    unittest.main()
