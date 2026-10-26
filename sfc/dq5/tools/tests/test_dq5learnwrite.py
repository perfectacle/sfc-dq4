"""주문 목록의 슬롯·공유 주소와 원본 밖 쓰기를 검사한다."""
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch as mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dq5learnwrite import FORMAT, decode, encode, patch
from dq5map import Rom


def parts(field=0x23BE27):
    return {'learn': (0x23B819, bytes([1, 4, 1, 1, 0])),
            'field': (field, bytes([1, 0x27])), 'battle': (0x23BE30, bytes([1, 0x27]))}


def doc(*rows):
    return {'format': FORMAT, 'characters': list(rows)}


class LearnTests(unittest.TestCase):
    def test_linked_slots_and_mask(self):
        old = decode(parts())
        new = copy.deepcopy(old)
        new['learn'][0]['level'] = 2
        new['field'][0] = new['battle'][0] = 0x28
        raw = encode(old, new)
        self.assertEqual(raw['learn'], bytes([1, 2, 1, 1, 0]))
        self.assertEqual(raw['field'], raw['battle'])
        self.assertEqual(raw['field'], bytes([1, 0x28]))

    def test_invalid_fields_types_counts_slots_and_order(self):
        old = decode(parts())
        cases = [{'field': []}, {'battle': [0]}, {'field': [0x2A]}, {'battle': [True]},
                 {'learn': []}, {'learn': [{'level': 2, 'field_slots': [1], 'battle_slots': []}]},
                 {'learn': [{'level': 2, 'field_slots': [0, 0], 'battle_slots': []}]},
                 {'learn': [{'level': 2, 'field_slots': [], 'battle_slots': []}]},
                 {'learn': [{'level': 1, 'field_slots': [0], 'battle_slots': []}]}]
        for change in cases:
            with self.subTest(change=change), self.assertRaises(ValueError):
                encode(old, change)
        old['learn'] *= 2
        with self.assertRaises(ValueError):
            encode(old, {})

    def test_floor_is_join_level_for_monsters(self):
        old = decode(parts())
        moved = {'learn': [{'level': 3, 'field_slots': [0], 'battle_slots': []}]}
        self.assertEqual(encode(old, moved, floor=3)['learn'], bytes([1, 3, 1, 0, 0]))
        with self.assertRaises(ValueError):
            encode(old, moved, floor=5)
        self.assertEqual(encode(old, {'learn': [{'level': 1, 'field_slots': [0], 'battle_slots': []}]}, floor=1)['learn'],
                         bytes([1, 1, 1, 0, 0]))

    def test_original_noop_and_guards(self):
        original = {('person', 0): parts()}
        with mock('dq5learnwrite.layout', return_value=original):
            self.assertEqual(patch(Rom(b''), doc({'kind': 'person', 'index': 0, **decode(parts())}))['writes'], [])
            row = {'kind': 'person', 'index': 0, 'battle': [0x28]}
            for source in (doc(row, row), doc(row | {'unknown': 1}), doc(row | {'index': True}),
                           {'format': FORMAT, 'characters': [], 'other': 1}):
                with self.assertRaises(ValueError):
                    patch(Rom(b''), source)

    def test_alias_requires_all_users_and_matching_edits(self):
        original = {('person', 0): parts(), ('person', 1): parts()}
        a = {'kind': 'person', 'index': 0, 'field': [0x28]}
        b = a | {'index': 1}
        with mock('dq5learnwrite.layout', return_value=original):
            with self.assertRaisesRegex(ValueError, '공유 목록'):
                patch(Rom(b''), doc(a))
            with self.assertRaisesRegex(ValueError, '공유 목록'):
                patch(Rom(b''), doc(a, b | {'field': [0x29]}))
            writes = patch(Rom(b''), doc(a, b))['writes']
            self.assertEqual(len(writes), 1)
            self.assertEqual(writes[0]['orig'], '27')

    def test_shared_spell_and_count_byte_is_preserved(self):
        a, b = parts(), parts()
        a['battle'] = (0x23BE30, bytes([1, 1]))
        b['field'] = (0x23BE31, bytes([1, 0x27]))
        b['learn'] = (0x23B850, b'\x00')
        b['battle'] = (0x23BE40, b'\x00')
        with mock('dq5learnwrite.layout', return_value={('person', 0): a, ('person', 1): b}):
            with self.assertRaisesRegex(ValueError, '공유 바이트'):
                patch(Rom(b''), doc({'kind': 'person', 'index': 0, 'battle': [2]}))
            writes = patch(Rom(b''), doc({'kind': 'person', 'index': 1, 'field': [0x28]}))['writes']
            self.assertEqual(writes[0]['at'], '23:BE32')
            self.assertEqual(writes[0]['hex'], '28')


if __name__ == '__main__':
    unittest.main()
