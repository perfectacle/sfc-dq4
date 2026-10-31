"""AI·작전·학습 배율·내성 배율·갑옷 원소 표 쓰기의 인코딩과 검증을 롬 없이 검사한다."""
import contextlib
import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dq5aiwrite as ai
from dq5map import Rom, lorom


def rom():
    data = bytearray(0x180000)

    def put(addr, raw):
        data[lorom(addr):lorom(addr) + len(raw)] = bytes(raw)

    for n in range(ai.ACTION_COUNT):
        put(ai.ACTIONS + n * 5, [0, 8, 0, 0, 0x1F])
        put(ai.BATTLE_MP + n, [0x1F])
    put(ai.ACTIONS + 4 * 5, [0x01, 20, 0x01, 4, 0x21])
    put(ai.BATTLE_MP + 4, [0xA4])
    put(ai.ACTIONS + 0x27 * 5, [0x08, 35, 0x10, 3, 0x7F])
    for n in range(ai.ACTION_COUNT, 0xF0):
        put(ai.ACTIONS + n * 5, [0x11, 0, 0x30, 0, 0xFF])
        put(ai.BATTLE_MP + n, [0x1F])
    for n in range(ai.ITEM_COUNT):
        put(ai.ITEMS + n * 5, [0, 0, 0, 0, 0x1F])
    put(ai.ITEMS + 0xA1 * 5, [0, 35, 0x13, 0, 0x7F])
    for t in range(ai.TACTIC_COUNT):
        put(ai.TACTICS + t * 32, [0x12, 0xFF, 0xFF, 0xFF, 0x64, 0x20, 0x28, 0xBC, 0x0F, 0x80, 2] + [0] * 5 + [0x1B, 0x08])
    for base in ai.ODDS.values():
        put(base, range(48))
    put(ai.RESIST, [0xFF, 0xCD, 0x54, 0])
    put(ai.ARMOR, [0x0F, 0x80, 0xEC, 0x0F, 0x56, 0x0A, 0])
    return Rom(bytes(data))


def doc(**sections):
    return {'format': ai.FORMAT, **sections}


def writes(result):
    return [(w['at'], w['hex'], w['orig']) for w in result['writes']]


class AiWriteTests(unittest.TestCase):
    def test_dump_and_noop(self):
        r = rom()
        out = ai.dump(r)
        self.assertEqual(out['actions'][4], {'action': '04', 'kind': '01', 'value': 20, 'branch': '01', 'mp': 4,
                                             'range': '20', 'resist': '51', 'battle_mp': 4})
        self.assertIsNone(out['actions'][0]['battle_mp'])
        self.assertEqual(out['tactics'][0]['mp_penalty'], 0x081B)
        self.assertEqual(out['odds']['normal'][1][2][3], 27)
        self.assertEqual(out['armor'], [{'index': 0, 'element': '0F', 'item': '80', 'reduce': -20},
                                        {'index': 1, 'element': '0F', 'item': '56', 'reduce': 10}])
        self.assertEqual(ai.patch(r, out)['writes'], [])

    def test_edits(self):
        r = rom()
        odds = ai.dump(r)['odds']['easy']
        odds[0][0][0] = 200
        result = ai.patch(r, doc(actions=[{'action': '04', 'value': 0, 'mp': 9, 'range': '00', 'resist': '56'},
                                          {'action': '27', 'branch': '00'}],
                                 items=[{'item': 'A1', 'value': 1, 'branch': '00'}],
                                 tactics=[{'tactic': 4, 'danger': 0x4B, 'mp_penalty': 0x1234}],
                                 odds={'easy': odds}, resist_rates=[0x80, 205, 84, 0],
                                 armor=[{'index': 1, 'reduce': -3, 'element': '0F', 'item': '56'}]))
        self.assertEqual(writes(result), [
            ('21:BC9B', '00', '14'), ('21:BC9D', '09', '04'), ('21:BC9E', '06', '21'), ('21:BD4B', '00', '10'),
            ('21:C45C', '01', '23'), ('21:C45D', '00', '13'), ('21:D943', '4b', '28'), ('21:D94D', '34 12', '1b 08'),
            ('27:8055', '80', 'ff'), ('27:8101', 'fd', '0a'),
            ('27:8284', 'c8', '00')])

    def test_guards(self):
        r = rom()
        bad = [{'actions': [{'action': '04', 'kind': '08'}]}, {'actions': [{'action': '04', 'battle_mp': 9}]},
               {'actions': [{'action': 'AB', 'value': 1}]}, {'actions': [{'action': '04', 'value': 256}]},
               {'actions': [{'action': '04', 'branch': '0B'}]}, {'actions': [{'action': '04', 'range': '10'}]},
               {'actions': [{'action': '04', 'resist': '5F'}]}, {'actions': [{'action': '04', 'resist': '62'}]},
               {'actions': [{'action': '04', 'value': 1}, {'action': '04', 'mp': 1}]},
               {'items': [{'item': 'A1', 'mp': 1}]}, {'items': [{'item': 'D8', 'value': 1}]},
               {'tactics': [{'tactic': 5, 'danger': 1}]}, {'tactics': [{'tactic': 0, 'heal': 1}]},
               {'tactics': [{'tactic': '0', 'danger': 1}]}, {'tactics': [{'tactic': 0, 'mp_penalty': 0x10000}]},
               {'odds': {'normal': [[0] * 4] * 3}}, {'odds': {'other': []}}, {'resist_rates': [1, 2, 3]},
               {'armor': [{'index': 2, 'reduce': 1}]}, {'armor': [{'index': 0, 'element': '01'}]},
               {'armor': [{'index': 0, 'reduce': 128}]}, {'armor': [{'index': 0, 'item': '56'}]},
               {'actions': [{'action': '04', 'range': 'C0'}]}, {'actions': [{'action': '04', 'range': 'E0'}]},
               {'actions': [{'action': '04', 'kind': '08'}]}, {'tactics': [{'tactic': 0, 'heal_damage': 1}]},
               {'tactics': [{'tactic': 0, 'damage_weight': 1}]}, {'tactics': [{'tactic': 0, 'dragoram': 1}]},
               {'items': [{'item': 'A1', 'branch': '01'}]}, {'other': 1}]
        for change in bad:
            with self.subTest(change=change), self.assertRaises(ValueError):
                ai.patch(r, doc(**change))
        self.assertEqual(writes(ai.patch(r, doc(actions=[{'action': '04', 'resist': None}])))[0][1], '3f')
        self.assertEqual(ai.patch(r, doc(actions=[{'action': '04', 'kind': '01', 'range': '20'}]))['writes'], [])
        self.assertEqual(writes(ai.patch(r, doc(actions=[{'action': '04', 'range': '80'}])))[0][1], '81')
        self.assertEqual(writes(ai.patch(r, doc(actions=[{'action': '04', 'range': 'A0'}])))[0][1], 'a1')
        # 작전 +3(회복 값 무게)·+4(회복 MP 무게)
        self.assertEqual(writes(ai.patch(r, doc(tactics=[{'tactic': 1, 'heal_value': 0, 'heal_mp': 9}]))),
                         [('21:D8E0', '00', 'ff'), ('21:D8E1', '09', '64')])

    def test_new_actions(self):
        r = rom()
        out = ai.dump(r)
        self.assertEqual(len(out['actions']), ai.ACTION_COUNT + len(ai.NEW_ACTIONS))
        self.assertEqual(out['actions'][ai.ACTION_COUNT], {'action': 'C6', 'kind': '11', 'value': 0, 'branch': '30', 'mp': 0,
                                                           'range': 'E0', 'resist': None, 'battle_mp': None})
        result = ai.patch(r, doc(actions=[{'action': 'C6', 'copy': '04'},
                                          {'action': 'D4', 'copy': '27', 'value': 99, 'range': '80'}]))
        self.assertEqual(writes(result), [('21:C064', '01 14 01 04 21', '11 00 30 00 ff'),
                                          ('21:C0AA', '08', '11'), ('21:C0AB', '63', '00'), ('21:C0AC', '10 03', '30 00'),
                                          ('21:C0AE', '9f', 'ff')])
        # 베낀 레코드의 kind 와 같으면 받고, 다르면 거부한다.
        self.assertEqual(len(ai.patch(r, doc(actions=[{'action': 'C6', 'copy': '04', 'kind': '01'}]))['writes']), 1)
        bad = [{'action': '04', 'copy': '01'}, {'action': 'C6', 'copy': 'AB'}, {'action': 'C6', 'copy': 'C6'},
               {'action': 'C5', 'value': 1}, {'action': 'D5', 'value': 1}, {'action': 'C6', 'copy': '04', 'kind': '08'},
               {'action': 'C6', 'kind': '01'}, {'action': 'C6', 'copy': 4}]
        for row in bad:
            with self.subTest(row=row), self.assertRaises(ValueError):
                ai.patch(r, doc(actions=[row]))
        with contextlib.redirect_stdout(io.StringIO()):
            ai.check(r, doc(actions=[{'action': 'C6', 'copy': '04', 'value': 1}, {'action': '04', 'value': 2}]))

    def test_copy_warnings(self):
        data = bytearray(0x180000)
        for name, (base, size, empty) in ai.WIDE.items():
            for n in range(0x100):
                v = (empty if n >= ai.NEW_FIRST else n + 0x100) & (0xFF if size == 1 else 0xFFFF)
                data[lorom(base) + n * size:lorom(base) + (n + 1) * size] = v.to_bytes(size, 'little')
        # dq5spellgrow.py 가 C6 에 04 를 베낀 롬.
        for name, (base, size, _) in ai.WIDE.items():
            data[lorom(base) + 0xC6 * size:lorom(base) + 0xC7 * size] = (0x104 & (0xFF if size == 1 else 0xFFFF)).to_bytes(size, 'little')
        spells = Rom(bytes(data))
        self.assertEqual(ai.copy_warnings(spells, doc(actions=[{'action': 'C6', 'copy': '04'}])), [])
        got = ai.copy_warnings(spells, doc(actions=[{'action': 'C6', 'copy': '27'}, {'action': 'C7', 'copy': '04'},
                                                    {'action': '04', 'value': 1}]))
        self.assertEqual(len(got), 2)
        self.assertIn('copy 27', got[0])
        self.assertIn('C7', got[1])
        for bad in ({'action': 'C6', 'copy': 4}, {'action': 6, 'copy': '04'}, {'action': 'C6', 'copy': 'x'}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                ai.copy_warnings(spells, doc(actions=[bad]))
        with self.assertRaises(ValueError):
            ai.copy_warnings(spells, doc(actions={'action': 'C6'}))

    def test_check_through_builder(self):
        r = rom()
        with contextlib.redirect_stdout(io.StringIO()):
            ai.check(r)
            ai.check(r, doc(actions=[{'action': '04', 'value': 0}], tactics=[{'tactic': 0, 'danger': 0x4B}]))
            easy = ai.dump(r)['odds']['easy']
            easy[2][3][3] = 9
            ai.check(r, doc(odds={'easy': easy}))


if __name__ == '__main__':
    unittest.main()
