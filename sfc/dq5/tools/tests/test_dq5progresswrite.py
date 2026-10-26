"""고정 성장·조우·상점 슬롯과 실제 디코더의 의미 대조."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dq5encounter import AREAS, AREA_COUNT, AREA_SIZE, area  # noqa: E402
from dq5growth import exp_at, stat_at  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402
from dq5progresswrite import (  # noqa: E402
    FORMAT, GROWTH, RECORD, SHOP_COUNTS, STATS, STAT_OFFSETS, dump, edits,
    encode_growth, growth_fields, patch,
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
    data[lorom(MEDAL_PRICES):lorom(MEDAL_PRICES) + 6] = bytes(range(1, 7))
    for i in range(6):
        off = lorom(COIN_PRICES + i * 3)
        data[off:off + 3] = (100 * (i + 1)).to_bytes(3, 'little')
    return bytes(data)


def apply(data, manifest):
    updated = bytearray(data)
    for w in manifest['writes']:
        off = lorom(int(w['at'].replace(':', ''), 16))
        raw = bytes.fromhex(w['hex'])
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
        self.assertEqual(sum(len(old) for _, _, old, _ in rows), 6510)
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
               doc(shops=[{'kind': 0, 'index': 0, 'items': [1]}]),
               doc(shops=[{'kind': 0, 'index': 0, 'items': [216] * 4}]),
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
