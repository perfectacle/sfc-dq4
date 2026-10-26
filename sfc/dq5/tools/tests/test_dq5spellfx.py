"""처리 루틴 연결·첫머리 값·필드 주문 쓰기의 인코딩과 검증을 롬 없이 검사한다."""
import contextlib
import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dq5spellfx as fx
from dq5map import Rom, lorom

STUBS = {0xB0E5: 'e2 30 a2 50 a9 01 4c 07 b3', 0xB136: 'e2 30 a2 53 a9 0a 4c 07 b3',
         0xB2C0: 'e2 30 a9 13 4c 70 ab', 0xB410: 'e2 30 a9 03 a2 57 4c 41 ae',
         0xB301: 'e2 30 a2 50 a9 16 86 43 20 70 ab'}
SLOTS = {1: (0xB0E5, 0x975F), 2: (0xB136, 0x975F), 3: (0xB2C0, 0x9824), 4: (0xB410, 0x9915), 5: (0xB301, 0x975F)}
FIELD = [0x84FA, 0x85A5, 0x85DC, 0x8022, 0x8022, 0x865D, 0x86C7, 0x860C, 0x8636, 0x8022, 0x8022, 0x8056, 0x82B6,
         0x8797, 0x82E8, 0x877D, 0x826F, 0x8729]
MP = {0x84FA: 3, 0x85A5: 5, 0x85DC: 7, 0x865D: 2, 0x86C7: 2, 0x860C: 10, 0x8636: 20, 0x8056: 8, 0x82B6: 8,
      0x8797: 4, 0x82E8: 3, 0x877D: 2, 0x826F: 4, 0x8729: 10}


def rom():
    data = bytearray(0x180000)

    def put(addr, raw):
        data[lorom(addr):lorom(addr) + len(raw)] = raw

    for n in range(fx.ACTIONS):
        handler, executor = SLOTS.get(n, (0xAF27, 0x9D18))
        put(fx.HANDLERS + n * 2, handler.to_bytes(2, 'little'))
        put(fx.EXECUTORS + n * 2, executor.to_bytes(2, 'little'))
    for handler, raw in STUBS.items():
        put(0x200000 | handler, bytes.fromhex(raw))
    for i, handler in enumerate(FIELD):
        put(fx.FIELD_TABLE + i * 2, handler.to_bytes(2, 'little'))
    for handler, sites in fx.FIELD_MP.items():
        for site in sites:
            put(site - 1, bytes([0xA9, MP[handler]]))
    for (top, spread, base), values in zip(fx.FIELD_HEAL.values(), ((40, 11, 30), (95, 21, 75))):
        put(top - 1, bytes([0xA9, values[0]]))
        put(spread - 1, bytes([0xA9, values[1]]))
        put(base - 1, bytes([0x69, values[2]]))
    return Rom(bytes(data))


def doc(**sections):
    return {'format': fx.FORMAT, **sections}


def writes(result):
    return [(w['at'], w['hex'], w['orig']) for w in result['writes']]


class SpellFxTests(unittest.TestCase):
    def test_dump_and_noop(self):
        r = rom()
        out = fx.dump(r)
        handlers = {row['handler']: row for row in out['battle_handlers']}
        self.assertEqual(set(handlers), {'B0E5', 'B136', 'B2C0', 'B410'})
        self.assertEqual(handlers['B0E5'], {'handler': 'B0E5', 'routine': 'B307', 'users': ['01'],
                                            'amount': '01', 'resist': '50'})
        self.assertEqual(handlers['B410']['chance'], 3)
        self.assertNotIn('resist', handlers['B2C0'])
        self.assertEqual(out['field_handlers'][0], {'handler': '84FA', 'spells': ['27'], 'mp': 3,
                                                    'heal': {'base': 30, 'spread': 11}})
        self.assertEqual(fx.patch(r, out)['writes'], [])

    def test_battle_edits(self):
        r = rom()
        result = fx.patch(r, doc(battle_slots=[{'action': '01', 'handler': 'B136'}],
                                 battle_handlers=[{'handler': 'B0E5', 'amount': '02', 'resist': '5B'},
                                                  {'handler': 'B410', 'chance': 0}]))
        self.assertEqual(writes(result), [('20:B0E8', '5b', '50'), ('20:B0EA', '02', '01'), ('20:B413', '00', '03'),
                                          ('20:B7FB', '36 b1', 'e5 b0')])

    def test_battle_guards(self):
        r = rom()
        bad = [{'battle_slots': [{'action': '01', 'handler': 'B2C0'}]},   # 975F 와 B2C0 은 원래 짝이 아님
               {'battle_slots': [{'action': '01', 'handler': 'C000'}]},
               {'battle_slots': [{'action': 'AB', 'handler': 'B0E5'}]},
               {'battle_slots': [{'action': '01', 'executor': '9824'}]},
               {'battle_handlers': [{'handler': 'B0E5', 'amount': '40'}]},
               {'battle_handlers': [{'handler': 'B0E5', 'chance': 1}]},
               {'battle_handlers': [{'handler': 'B0E5', 'resist': '5F'}]},
               {'battle_handlers': [{'handler': 'B0E5', 'resist': '62'}]},
               {'battle_handlers': [{'handler': 'B2C0', 'resist': '50'}]},
               {'battle_handlers': [{'handler': 'B410', 'chance': 9}]},
               {'battle_handlers': [{'handler': 'B410', 'amount': '01'}]},
               {'battle_handlers': [{'handler': 'B301', 'amount': '01'}]},     # 86 43 이 끼면 첫머리로 보지 않음
               {'battle_handlers': [{'handler': 'B0E5', 'routine': 'AB70'}]},
               {'battle_handlers': [{'handler': 'B0E5', 'amount': '01'}, {'handler': 'B0E5', 'resist': '51'}]},
               {'battle_slots': [{'action': '01', 'extra': 1}]}, {'unknown': []}]
        for change in bad:
            with self.subTest(change=change), self.assertRaises(ValueError):
                fx.patch(r, doc(**change))
        raw = fx.patch(r, doc(battle_slots=[{'action': '01', 'handler': 'C000'}]), raw=True)
        self.assertEqual(writes(raw), [('20:B7FB', '00 c0', 'e5 b0')])

    def test_field_edits(self):
        r = rom()
        result = fx.patch(r, doc(field_slots=[{'spell': '27', 'handler': '85DC'}],
                                 field_handlers=[{'handler': '84FA', 'mp': 9, 'heal': {'base': 100, 'spread': 1}},
                                                 {'handler': '826F', 'mp': 12}]))
        self.assertEqual(writes(result), [('11:8024', 'dc 85', 'fa 84'), ('11:8272', '0c', '04'), ('11:84FB', '09', '03'),
                                          ('11:851A', '09', '03'), ('11:851F', '64', '28'), ('11:8526', '01', '0b'),
                                          ('11:852D', '64', '1e')])
        after = fx.dump(Rom(apply(r, result)))
        self.assertEqual(after['field_handlers'][0]['heal'], {'base': 100, 'spread': 1})
        self.assertEqual(after['field_slots'][0]['handler'], '85DC')

    def test_field_guards(self):
        r = rom()
        bad = [{'field_slots': [{'spell': '27', 'handler': '8022'}]}, {'field_slots': [{'spell': '26'}]},
               {'field_slots': [{'spell': '27', 'handler': '9000'}]},
               {'field_handlers': [{'handler': '8022', 'mp': 1}]},
               {'field_handlers': [{'handler': '85DC', 'heal': {'base': 1, 'spread': 1}}]},
               {'field_handlers': [{'handler': '84FA', 'heal': {'base': 250, 'spread': 7}}]},
               {'field_handlers': [{'handler': '84FA', 'heal': {'base': 1, 'spread': 0}}]},
               {'field_handlers': [{'handler': '84FA', 'heal': {'base': 1}}]},
               {'field_handlers': [{'handler': '84FA', 'mp': 256}]}]
        for change in bad:
            with self.subTest(change=change), self.assertRaises(ValueError):
                fx.patch(r, doc(**change))
        self.assertEqual(fx.patch(r, doc(field_slots=[{'spell': '2A', 'handler': '8022'}]))['writes'], [])
        self.assertEqual(writes(fx.patch(r, doc(field_handlers=[{'handler': '84FA', 'heal': {'base': 250, 'spread': 6}}])))[0],
                         ('11:851F', 'ff', '28'))

    def test_layout_guard(self):
        data = bytearray(rom().d)
        data[lorom(0x11851A)] = 4
        with self.assertRaises(ValueError):
            fx.dump(Rom(bytes(data)))

    def test_check_through_builder(self):
        r = rom()
        with contextlib.redirect_stdout(io.StringIO()):
            fx.check(r)
            fx.check(r, doc(battle_handlers=[{'handler': 'B0E5', 'amount': '02'}],
                            field_handlers=[{'handler': '84FA', 'mp': 9}]))


def apply(r, result):
    data = bytearray(r.d)
    for w in result['writes']:
        bank, addr = (int(v, 16) for v in w['at'].split(':'))
        new = bytes.fromhex(w['hex'])
        data[lorom(bank << 16 | addr):lorom(bank << 16 | addr) + len(new)] = new
    return bytes(data)


if __name__ == '__main__':
    unittest.main()
