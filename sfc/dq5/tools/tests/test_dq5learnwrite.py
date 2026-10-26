"""주문 습득 표·목록의 부호화, 공유 바이트, 길이 바꾸기와 옮기기를 롬 없이 검사한다."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dq5build import build, parse_at  # noqa: E402
from dq5learnwrite import (BANK_AT, COMPANIONS, FORMAT, LDY_AT, TABLES, check, config,  # noqa: E402
                           dump, encode, layout, patch, stub)
from dq5map import Rom, lorom  # noqa: E402


def put(data, address, raw):
    data[lorom(address):lorom(address) + len(raw)] = raw


def synthetic(shared=False):
    """사람 11·몬스터 42 의 표를 원래 자리에 둔 1.5MB 가짜 롬. shared 면 사람 0·1 이 필드 목록을 같이 쓰고,
    사람 2 의 전투 목록 마지막 바이트가 사람 3 의 필드 목록 개수를 겸한다(23:BE63 과 같은 꼴)."""
    data = bytearray(0x180000)
    put(data, LDY_AT, bytes.fromhex('a0 00 00'))
    put(data, 0x23ECE3, bytes.fromhex('a2 19 b8'))
    put(data, 0x23ECEE, bytes.fromhex('a2 79 b9'))
    for at in BANK_AT.values():
        put(data, at - 1, bytes.fromhex('a9 23'))
    for i in range(42):
        put(data, COMPANIONS + i * 9, bytes([1]))
    for i in range(10):
        put(data, 0x23B819 + i * 5, bytes([1, 4, 1, 1, 0]))
    # 사람 10 의 항목 75개로 사람 표를 원본처럼 23:B977 까지 채우고, 23:B978 은 00.
    put(data, 0x23B819 + 50, bytes([75]) + b''.join(bytes([n, 1, 0, 0]) for n in range(2, 77)))
    for i in range(42):
        put(data, 0x23B979 + i, bytes([0]))
    a = 0x23BE27
    pointers = {name: [] for name in TABLES}
    for k in range(53):
        for name in TABLES:
            if shared and name == 'field' and k == 1:
                pointers[name].append(pointers[name][0])
                continue
            if shared and name == 'field' and k == 3:
                # 앞 목록(사람 2 전투)의 마지막 주문 01 이 이 목록의 개수.
                pointers[name].append(a - 1)
                put(data, a, bytes([0x36]))
                a += 1
                continue
            raw = bytes([1, 1]) if shared and name == 'battle' and k == 2 else bytes([1, 0x27])
            pointers[name].append(a)
            put(data, a, raw)
            a += len(raw)
    for name, table in TABLES.items():
        put(data, table, b''.join((p & 0xFFFF).to_bytes(2, 'little') for p in pointers[name]))
    return Rom(data)


def doc(*rows):
    return {'format': FORMAT, 'characters': list(rows)}


def apply(rom, manifest):
    writes = [(parse_at(w['at'])[0], bytes.fromhex(w['hex']), bytes.fromhex(w['orig']) if 'orig' in w else None, '')
              for w in manifest['writes']]
    size = manifest.get('rom_size', 0)
    return Rom(build(rom.d, [('t', size, writes)], size)[0])


HERO = {'learn': [{'level': 4, 'field_slots': [0], 'battle_slots': [0]}], 'field': [0x27], 'battle': [0x27]}


class EncodeTests(unittest.TestCase):
    def test_linked_slots_and_mask(self):
        new = copy.deepcopy(HERO)
        new['learn'][0]['level'] = 2
        new['field'][0] = new['battle'][0] = 0x28
        raw = encode(HERO, new)
        self.assertEqual(raw['learn'], bytes([1, 2, 1, 1, 0]))
        self.assertEqual(raw['field'], bytes([1, 0x28]))

    def test_lengths_may_change_within_caps(self):
        raw = encode(HERO, {'field': [0x27, 0x28], 'battle': [],
                            'learn': [{'level': 2, 'field_slots': [1], 'battle_slots': []},
                                      {'level': 5, 'field_slots': [0], 'battle_slots': []}]})
        self.assertEqual(raw['learn'], bytes([2, 2, 2, 0, 0, 5, 1, 0, 0]))
        self.assertEqual(raw['battle'], bytes([0]))
        self.assertEqual(encode(HERO, {'learn': []})['learn'], bytes([0]))

    def test_invalid(self):
        cases = [{'field': [0x27] * 9}, {'battle': [1] * 13}, {'field': [0x2A]}, {'battle': [True]},
                 {'learn': [{'level': 2, 'field_slots': [1], 'battle_slots': []}]},
                 {'learn': [{'level': 2, 'field_slots': [0, 0], 'battle_slots': []}]},
                 {'learn': [{'level': 2, 'field_slots': [], 'battle_slots': []}]},
                 {'learn': [{'level': 1, 'field_slots': [0], 'battle_slots': []}]},
                 {'learn': [{'level': 3, 'field_slots': [0], 'battle_slots': []}] * 2},
                 {'learn': [{'level': 2, 'field_slots': [0]}]}]
        for change in cases:
            with self.subTest(change=change), self.assertRaises(ValueError):
                encode(HERO, change)

    def test_floor(self):
        moved = {'learn': [{'level': 3, 'field_slots': [0], 'battle_slots': []}]}
        self.assertEqual(encode(HERO, moved, floor=3)['learn'], bytes([1, 3, 1, 0, 0]))
        with self.assertRaises(ValueError):
            encode(HERO, moved, floor=5)
        low = dict(HERO, learn=[{'level': 1, 'field_slots': [0], 'battle_slots': []}])
        self.assertEqual(encode(low, {})['learn'], bytes([1, 1, 1, 0, 0]))

    def test_stub(self):
        self.assertEqual(stub(0x3F), bytes.fromhex('a9 3f 48 ab a0 00 00 60'))


class PatchTests(unittest.TestCase):
    def test_round_trip(self):
        for shared in (False, True):
            rom = synthetic(shared)
            self.assertEqual(patch(rom, dump(rom))['writes'], [])
            check(rom)

    def test_guards(self):
        rom = synthetic()
        row = {'kind': 'person', 'index': 0, 'battle': [0x28]}
        for source in (doc(row, row), doc(row | {'unknown': 1}), doc(row | {'index': True}),
                       {'format': FORMAT, 'characters': [], 'other': 1},
                       doc({'kind': 'monster', 'index': 0, 'battle': [1] * 9})):
            with self.subTest(source=str(source)[:60]), self.assertRaises(ValueError):
                patch(rom, source)
        self.assertTrue(patch(rom, doc({'kind': 'person', 'index': 0, 'battle': [1] * 12}))['writes'])

    def test_alias_requires_all_users(self):
        rom = synthetic(shared=True)
        a = {'kind': 'person', 'index': 0, 'field': [0x28]}
        b = a | {'index': 1}
        with self.assertRaisesRegex(ValueError, '공유 목록'):
            patch(rom, doc(a))
        with self.assertRaisesRegex(ValueError, '공유 목록'):
            patch(rom, doc(a, b | {'field': [0x29]}))
        writes = patch(rom, doc(a, b))['writes']
        self.assertEqual([(w['hex'], w['orig']) for w in writes], [('28', '27')])

    def test_shared_count_byte(self):
        rom = synthetic(shared=True)
        with self.assertRaisesRegex(ValueError, '공유 바이트'):
            patch(rom, doc({'kind': 'person', 'index': 2, 'battle': [2]}))
        self.assertTrue(patch(rom, doc({'kind': 'person', 'index': 3, 'field': [0x28]}))['writes'])

    def test_in_place_edit(self):
        rom = synthetic()
        writes = patch(rom, doc({'kind': 'person', 'index': 0, 'learn': [
            {'level': 2, 'field_slots': [0], 'battle_slots': [0]}]}))['writes']
        self.assertEqual([(w['at'], w['hex'], w['orig']) for w in writes], [('23:B81A', '02', '04')])

    def test_learn_grows_in_bank(self):
        rom = synthetic()
        source = doc({'kind': 'person', 'index': 0, 'learn': [
            {'level': 2, 'field_slots': [0], 'battle_slots': []}, {'level': 4, 'field_slots': [], 'battle_slots': [0]}]})
        after = apply(rom, patch(rom, source))
        self.assertEqual(config(after)['bases'], {'person': 0x23B819, 'monster': 0x23B97D})
        self.assertEqual(after.d[lorom(0x23B97C)], 0)
        self.assertEqual(dump(after)['characters'][0]['learn'], source['characters'][0]['learn'])
        self.assertEqual(dump(after)['characters'][11:], dump(rom)['characters'][11:])
        check(rom, source)

    def test_learn_moves_to_other_bank(self):
        rom = synthetic()
        big = [{'level': n, 'field_slots': [0], 'battle_slots': []} for n in range(2, 99)]
        source = doc(*({'kind': 'person', 'index': i, 'learn': big} for i in range(4)))
        with self.assertRaisesRegex(ValueError, '--learn-at'):
            patch(rom, source)
        with self.assertRaisesRegex(ValueError, '--stub-at'):
            patch(rom, source, learn_at=0x3F8000)
        with self.assertRaisesRegex(ValueError, '30~3F'):
            patch(rom, source, learn_at=0x408000, stub_at=0x23FF20)
        manifest = patch(rom, source, learn_at=0x3F8000, stub_at=0x23FF20)
        self.assertEqual(manifest['rom_size'], 2)
        after = apply(rom, manifest)
        cfg = config(after)
        self.assertEqual((cfg['bank'], cfg['stub'], cfg['bases']['person']), (0x3F, 0x23FF20, 0x3F8000))
        self.assertEqual(after.d[lorom(LDY_AT):lorom(LDY_AT) + 3], bytes.fromhex('20 20 ff'))
        self.assertEqual(dump(after)['characters'][3]['learn'], big)
        check(rom, source, learn_at=0x3F8000, stub_at=0x23FF20)

    def test_lists_grow(self):
        rom = synthetic()
        source = doc({'kind': 'monster', 'index': 5, 'field': [0x27, 0x28], 'battle': [1] * 8})
        after = apply(rom, patch(rom, source))
        self.assertEqual(config(after)['banks'], {'field': 0x23, 'battle': 0x23})
        self.assertEqual(dump(after)['characters'][16]['battle'], [1] * 8)
        after = apply(rom, patch(rom, source, lists_at=0x3F9000))
        self.assertEqual(config(after)['banks'], {'field': 0x3F, 'battle': 0x3F})
        self.assertEqual(layout(after)['monster', 5]['field'][0] >> 16, 0x3F)
        self.assertEqual(dump(after)['characters'][16]['field'], [0x27, 0x28])
        check(rom, source, lists_at=0x3F9000)
        with self.assertRaisesRegex(ValueError, '빈 자리'):
            patch(rom, source, lists_at=0x23C100)

    def test_lists_overflow_needs_target(self):
        rom = synthetic()
        # 같은 목록은 한 번만 두므로 인물마다 다르게 만든다.
        full = [{'kind': k, 'index': i, 'field': [0x27, *range(0x32, 0x39)],
                 'battle': [i + (50 if k == 'person' else 1), *range(1, 12 if k == 'person' else 8)]}
                for k, n in (('person', 11), ('monster', 42)) for i in range(n)]
        with self.assertRaisesRegex(ValueError, '--lists-at'):
            patch(rom, doc(*full))


    def test_move_back_and_within_bank(self):
        rom = synthetic()
        big = [{'level': n, 'field_slots': [0], 'battle_slots': []} for n in range(2, 40)]
        source = doc({'kind': 'person', 'index': 0, 'learn': big})
        moved = apply(rom, patch(rom, source, learn_at=0x3F8000, stub_at=0x23FF20))
        again = apply(moved, patch(moved, source, learn_at=0x3F9000))
        self.assertEqual((config(again)['bank'], config(again)['stub'], config(again)['bases']['person']),
                         (0x3F, 0x23FF20, 0x3F9000))
        home = apply(moved, patch(moved, source, learn_at=0x23B819))
        cfg = config(home)
        self.assertEqual((cfg['bank'], cfg['stub'], cfg['bases']['person']), (0x23, None, 0x23B819))
        self.assertEqual(dump(home)['characters'][0]['learn'], big)

    def test_stub_and_config_guards(self):
        rom = synthetic()
        big = [{'level': n, 'field_slots': [0], 'battle_slots': []} for n in range(2, 99)]
        source = doc(*({'kind': 'person', 'index': i, 'learn': big} for i in range(4)))
        for options in ({'learn_at': 0x3F8000, 'stub_at': 0x24FF20}, {'learn_at': 0x3F8000, 'stub_at': 0x238000},
                        {'learn_at': 0x23FF20, 'stub_at': 0x23FF20}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                patch(rom, source, **options)
        data = bytearray(rom.d)
        put(data, LDY_AT, bytes.fromhex('20 00 90'))
        with self.assertRaisesRegex(ValueError, '데이터 뱅크 루틴'):
            config(Rom(data))

    def test_identical_lists_share_and_gap(self):
        # 습득 표(사람 352·몬스터 42바이트) 끝과 목록 사이를 2바이트 띄워 늘린 뱅크의 빈 바이트를 건너 묶지 않는지 본다.
        rom = synthetic()
        source = doc({'kind': 'monster', 'index': 5, 'field': [0x27, 0x28]})
        manifest = patch(rom, source, learn_at=0x3F8000, stub_at=0x23FF20, lists_at=0x3F8000 + 352 + 42 + 2)
        after = apply(rom, manifest)
        parts = layout(after)
        self.assertEqual(parts['person', 0]['battle'][0], parts['person', 1]['battle'][0])
        self.assertEqual(dump(after)['characters'][16]['field'], [0x27, 0x28])
        with self.assertRaisesRegex(ValueError, '30~3F'):
            patch(rom, source, lists_at=0x408000)

    def test_check_sorts_slots(self):
        rom = synthetic()
        check(rom, doc({'kind': 'person', 'index': 0, 'field': [0x27, 0x28],
                        'learn': [{'level': 4, 'field_slots': [1, 0], 'battle_slots': [0]}]}))


if __name__ == '__main__':
    unittest.main()
