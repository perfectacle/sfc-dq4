"""맵별 루틴 표 쓰기의 인코딩·검증·표 옮기기를 롬 없이 검사한다."""
import contextlib
import copy
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch as mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dq5maphook as hook
from dq5map import Rom, lorom

MAPS = [(0x01, 0x04), (0x01, 0x05), (0x04, 0x00), (0x04, 0x05), (0x17, 0x00), (0x17, 0x01)]
ROWS = [
    bytes.fromhex('01 05 ff 00 e0 94 02 06 f9 15'),
    bytes.fromhex('04 00 ff 00 c1 94 02 bd a7 02'),
    bytes.fromhex('17 ff 2f 80 06 f9 15 b5 d4 03'),
    bytes.fromhex('fe 00 84 80 4c a9 02 98 ac 02'),
    bytes.fromhex('04 00 ff 00 06 f9 15 b5 d4 03'),
]


def rom(rows=ROWS, base=0x15F907):
    data = bytearray(0x180000)
    for at, opcode, offset in hook.OPERANDS:
        data[lorom(at):lorom(at) + 3] = bytes([opcode]) + ((base & 0xFFFF) + offset).to_bytes(2, 'little')
    start = lorom(base)
    for i, raw in enumerate(rows):
        data[start + i * 10:start + i * 10 + 10] = raw
    data[start + len(rows) * 10] = 0xFF
    data[lorom(hook.LOADER_CALL):lorom(hook.LOADER_CALL) + 3] = bytes.fromhex('20 f4 f7')
    for at, opcode, offset in hook.CELL_OPERANDS:
        data[lorom(at):lorom(at) + 3] = bytes([opcode]) + (0xFF5C + offset).to_bytes(2, 'little')
    data[lorom(0x15FF5C):lorom(0x15FF5C) + 7] = bytes.fromhex('17 01 ff 00 c3 bc ff')
    return Rom(bytes(data))


def apply(r, result):
    data = bytearray(r.d)
    for w in result['writes']:
        bank, addr = (int(v, 16) for v in w['at'].split(':'))
        off = lorom(bank << 16 | addr)
        new = bytes.fromhex(w['hex'])
        if 'orig' in w:
            assert data[off:off + len(new)] == bytes.fromhex(w['orig'])
        if off + len(new) > len(data):
            data += bytes(off + len(new) - len(data))
        data[off:off + len(new)] = new
    return Rom(bytes(data))


def doc(*entries):
    return {'format': hook.FORMAT, 'entries': list(entries)}


class MapHookTests(unittest.TestCase):
    def setUp(self):
        patcher = mock('dq5maphook.all_maps', return_value=MAPS)
        patcher.start()
        self.addCleanup(patcher.stop)
        quiet = contextlib.redirect_stderr(io.StringIO())
        quiet.__enter__()
        self.addCleanup(quiet.__exit__, None, None, None)

    def test_dump_fields_and_noop(self):
        r = rom()
        out = hook.dump(r)
        self.assertEqual(out['table'], '15:F907')
        self.assertEqual(out['entries'][0], {'index': 0, 'group': '01', 'map': '05', 'flag': None,
                                             'post_load': '02:94E0', 'per_frame': '15:F906'})
        self.assertEqual(out['entries'][2]['map'], None)
        self.assertEqual(out['entries'][2]['flag'], {'index': '2F', 'mask': '80', 'when': 'set'})
        self.assertEqual(out['entries'][3]['map'], '00')
        self.assertEqual(out['entries'][3]['flag'], {'index': '04', 'mask': '80', 'when': 'clear'})
        self.assertEqual(hook.patch(r, out)['writes'], [])
        self.assertEqual(hook.rewrite(r, out)['writes'], [])

    def test_disable_and_flag_edit(self):
        r = rom()
        result = hook.patch(r, doc({'index': 0, 'post_load': '15:F906'},
                                   {'index': 1, 'flag': {'index': '00', 'mask': '40', 'when': 'clear'}}))
        self.assertEqual([(w['at'], w['hex'], w['orig']) for w in result['writes']],
                         [('15:F90B', '06 f9 15', 'e0 94 02'), ('15:F913', '80 40', 'ff 00')])
        after = apply(r, result)
        self.assertEqual(hook.dump(after)['entries'][0]['post_load'], '15:F906')
        self.assertEqual(hook.patch(r, doc({'index': 2, 'flag': None}))['writes'][0]['hex'], 'ff 00')

    def test_routine_sets_are_per_slot(self):
        r = rom()
        for change in ({'post_load': '02:A7BD'}, {'per_frame': '02:94E0'}, {'post_load': '02:9999'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                hook.patch(r, doc({'index': 0, **change}))
        self.assertEqual(hook.patch(r, doc({'index': 0, 'per_frame': '02:A7BD'}))['writes'][0]['hex'], 'bd a7 02')
        raw = hook.patch(r, doc({'index': 0, 'post_load': '02:9999'}), raw_routines=True)
        self.assertEqual(raw['writes'][0]['hex'], '99 99')
        for bad in ('7E:2000', '02:1234', '00:7FFF', '40:1234', '70:1234', '7D:0000'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                hook.patch(r, doc({'index': 0, 'post_load': bad}), raw_routines=True)
        self.assertEqual(hook.patch(r, doc({'index': 0, 'post_load': '40:8000'}), raw_routines=True)['writes'][0]['hex'],
                         '00 80 40')

    def test_invalid_selectors_flags_and_rows(self):
        r = rom()
        cases = [{'index': 0, 'map': '07'}, {'index': 0, 'group': '02', 'map': None}, {'index': 0, 'group': 'FF'},
                 {'index': 3, 'map': '03'}, {'index': 3, 'map': None}, {'index': 0, 'map': 5},
                 {'index': 0, 'flag': {'index': '00', 'mask': '00', 'when': 'set'}},
                 {'index': 0, 'flag': {'index': '7F', 'mask': '01', 'when': 'clear'}},
                 {'index': 0, 'flag': {'index': '80', 'mask': '01', 'when': 'set'}},
                 {'index': 0, 'flag': {'index': '00', 'mask': '01'}},
                 {'index': 0, 'flag': {'index': '00', 'mask': '01', 'when': 'on'}},
                 {'index': 0, 'post_load': '0294E0'}, {'index': 0, 'extra': 1}, {'index': 5}, {'index': True}]
        for row in cases:
            with self.subTest(row=row), self.assertRaises(ValueError):
                hook.patch(r, doc(row))
        with self.assertRaises(ValueError):
            hook.patch(r, doc({'index': 0}, {'index': 0}))
        with self.assertRaises(ValueError):
            hook.patch(r, {'format': hook.FORMAT, 'table': '15:FF80', 'entries': []})
        group = hook.patch(r, doc({'index': 0, 'map': None}))['writes'][0]
        self.assertEqual((group['at'], group['hex']), ('15:F908', 'ff'))
        flag = hook.patch(r, doc({'index': 0, 'flag': {'index': '7F', 'mask': '01', 'when': 'set'}}))['writes'][0]
        self.assertEqual(flag['hex'], '7f 01')

    def test_rewrite_moves_table_and_loader(self):
        r = rom()
        entries = [{k: v for k, v in e.items() if k != 'index'} for e in hook.dump(r)['entries']]
        new = [entries[1] | {'group': '01', 'map': '04'}, entries[0]]
        result = hook.rewrite(r, doc(*new), 0x15FF80)
        after = apply(r, result)
        self.assertEqual(hook.table_base(after), 0x15FF80)
        for at, _, offset in hook.OPERANDS:
            self.assertEqual(after.u16(at + 1), 0xFF80 + offset)
        out = hook.dump(after)
        self.assertEqual(out['table'], '15:FF80')
        self.assertEqual([e['group'] + '/' + e['map'] for e in out['entries']], ['01/04', '01/05'])
        self.assertEqual(after.u8(0x15FF80 + 20), 0xFF)
        self.assertEqual(hook.rewrite(after, doc(*new), 0x15FF80)['writes'], [])
        self.assertEqual(hook.patch(after, out)['writes'], [])
        self.assertEqual(hook.dump(after)['entries'], out['entries'])
        back = apply(after, hook.rewrite(after, doc(*entries), 0x15F907))
        self.assertEqual(hook.table_base(back), 0x15F907)
        self.assertEqual(hook.dump(back)['entries'], hook.dump(r)['entries'])
        with self.assertRaises(ValueError):
            hook.rewrite(r, {'format': hook.FORMAT, 'table': '15:F907', 'entries': new}, 0x15FF80)
        data = bytearray(r.d)
        data[lorom(0x15FF85)] = 0x12
        with self.assertRaises(ValueError):
            hook.rewrite(Rom(bytes(data)), doc(*new), 0x15FF80)

    def test_rewrite_bounds(self):
        r = rom()
        row = {k: v for k, v in hook.dump(r)['entries'][0].items() if k != 'index'}
        hook.rewrite(r, doc(*[row] * 12), 0x15FF80)
        for rows, at in (([row] * 13, 0x15FF80), ([row], 0x15FF5C), ([row], 0x16F907), ([], 0x15F907),
                         ([row] * 163, 0x15F907), ([row | {'index': 1}], 0x15F907), ([row | {'index': True}], 0x15F907)):
            with self.subTest(count=len(rows), at=hex(at)), self.assertRaises(ValueError):
                hook.rewrite(r, doc(*rows), at)
        hook.rewrite(r, doc(*[row] * 162), 0x15F907)

    def test_rewrite_in_place_shorter(self):
        r = rom()
        entries = [{k: v for k, v in e.items() if k != 'index'} for e in hook.dump(r)['entries']]
        result = hook.rewrite(r, doc(*entries[:1], *entries[2:]))
        self.assertFalse(any(w['note'].endswith('주소') for w in result['writes']))
        after = apply(r, result)
        self.assertEqual(len(hook.dump(after)['entries']), 4)
        self.assertEqual(after.u8(0x15F907 + 40), 0xFF)

    def test_loader_guard(self):
        data = bytearray(rom().d)
        data[lorom(0x15F874) + 1] ^= 1
        with self.assertRaises(ValueError):
            hook.dump(Rom(bytes(data)))
        data = bytearray(rom().d)
        data[lorom(0x15F7F7)] = 0xEA
        with self.assertRaises(ValueError):
            hook.dump(Rom(bytes(data)))

    def test_check_round_trip_through_builder(self):
        r = rom()
        with contextlib.redirect_stdout(io.StringIO()):
            hook.check(r)
            hook.check(r, doc({'index': 1, 'per_frame': '15:F906'}))
            entries = [{k: v for k, v in e.items() if k != 'index'} for e in hook.dump(r)['entries']]
            hook.check(r, doc(*entries[:2]), 0x15FF80)
            with self.assertRaises(ValueError):
                hook.check(r, doc({'index': 1, 'per_frame': '02:94E0'}))

    def test_shadowed_and_runs(self):
        self.assertEqual(hook.shadowed(ROWS), [4])
        self.assertEqual(hook.shadowed([bytes.fromhex('fe 00 ff 00') + ROWS[0][4:], bytes.fromhex('fe 01 ff 00') + ROWS[0][4:]]), [])
        self.assertEqual(hook.shadowed([bytes.fromhex('fe ff ff 00') + ROWS[0][4:], bytes.fromhex('fe 01 ff 00') + ROWS[0][4:]]), [])
        self.assertEqual(hook.shadowed([bytes.fromhex('01 ff ff 00') + ROWS[0][4:], ROWS[0]]), [1])
        r = rom()
        wanted = {0x15F907 + k: v for k, v in enumerate(ROWS[0])}
        wanted[0x15F907], wanted[0x15F90C] = 0x02, 0x00
        self.assertEqual([(w['at'], w['hex']) for w in hook.runs(r, wanted, '')], [('15:F907', '02 05 ff 00 e0 00')])
        del wanted[0x15F909]
        self.assertEqual(len(hook.runs(r, wanted, '')), 2)

    def test_dump_does_not_alias_input(self):
        r = rom()
        source = hook.dump(r)
        kept = copy.deepcopy(source)
        hook.patch(r, source)
        self.assertEqual(source, kept)


class GrowAndCellTests(unittest.TestCase):
    def setUp(self):
        patcher = mock('dq5maphook.all_maps', return_value=MAPS)
        patcher.start()
        self.addCleanup(patcher.stop)
        quiet = contextlib.redirect_stderr(io.StringIO())
        quiet.__enter__()
        self.addCleanup(quiet.__exit__, None, None, None)

    def entries(self, r):
        return [{k: v for k, v in e.items() if k != 'index'} for e in hook.dump(r)['entries']]

    def test_grow_into_other_bank_through_stub(self):
        r = rom()
        rows = self.entries(r) * 40
        result = hook.rewrite(r, doc(*rows), 0x3F8000, stub_at=0x15FFF0)
        self.assertEqual(result['rom_size'], 2)
        self.assertFalse(any('orig' in w for w in result['writes'] if w['at'] in ('3F:8000', '15:FFF0')))
        after = apply(r, result)
        self.assertEqual(after.d[lorom(0x15FFF0):lorom(0x15FFF0) + 10], bytes.fromhex('8b a9 3f 48 ab 20 f4 f7 ab 60'))
        self.assertEqual(after.u16(hook.LOADER_CALL + 1), 0xFFF0)
        self.assertEqual(hook.table_base(after), 0x3F8000)
        self.assertEqual(len(hook.dump(after)['entries']), 200)
        self.assertEqual(hook.rewrite(after, doc(*rows), 0x3F8000, stub_at=0x15FFF0)['writes'], [])
        self.assertEqual(hook.cells_dump(after)['table'], '15:FF5C')
        with self.assertRaises(ValueError):
            hook.rewrite(after, doc(*rows[:3]), 0x15FF80)

    def test_grow_rejects(self):
        r = rom()
        rows = self.entries(r)
        for at, stub in ((0x408000, 0x15FFF0), (0x3F8000, None), (0x15FF80, 0x15FFF0), (0x3F7000, 0x15FFF0),
                         (0x3FFFF0, 0x15FFF0), (0x3F8000, 0x168000)):
            with self.subTest(at=hex(at), stub=stub), self.assertRaises(ValueError):
                hook.rewrite(r, doc(*rows), at, stub_at=stub)
        hook.rewrite(r, doc(*rows), 0x8F8000, stub_at=0x15FFF0)

    def test_cells_dump_and_rewrite(self):
        r = rom()
        out = hook.cells_dump(r)
        self.assertEqual(out['entries'], [{'index': 0, 'group': '17', 'map': '01', 'flag': None,
                                           'routine': '00:BCC3'}])
        rows = [{k: v for k, v in e.items() if k != 'index'} for e in out['entries']]
        self.assertEqual(hook.cells_rewrite(r, {'format': hook.CELL_FORMAT, 'entries': rows})['writes'], [])
        new = rows + [{'group': '01', 'map': '04', 'routine': '00:BCC3',
                       'flag': {'index': '00', 'mask': '40', 'when': 'set'}}]
        result = hook.cells_rewrite(r, {'format': hook.CELL_FORMAT, 'entries': new}, 0x15FF80)
        after = apply(r, result)
        self.assertEqual(after.d[lorom(0x15FF80):lorom(0x15FF80) + 13], bytes.fromhex('17 01 ff 00 c3 bc 01 04 00 40 c3 bc ff'))
        for at, _, offset in hook.CELL_OPERANDS:
            self.assertEqual(after.u16(at + 1), 0xFF80 + offset)
        self.assertEqual(hook.cells_dump(after)['entries'][1]['flag'], {'index': '00', 'mask': '40', 'when': 'set'})
        self.assertEqual(hook.table_base(after), 0x15F907)

    def test_cells_rejects(self):
        r = rom()
        row = {'group': '01', 'map': '04', 'flag': None, 'routine': '00:BCC3'}
        bad = [([row, row], None), ([row | {'routine': '00:9000'}], None), ([row | {'routine': '01:BCC3'}], None),
               ([row | {'map': '09'}], None), ([row] * 22, 0x15FF80), ([row], 0x15F907), ([row | {'index': 3}], None), ([row], 0x2FFFC0)]
        for rows, at in bad:
            with self.subTest(rows=rows[:1], at=at), self.assertRaises(ValueError):
                hook.cells_rewrite(r, {'format': hook.CELL_FORMAT, 'entries': rows}, at)
        hook.cells_rewrite(r, {'format': hook.CELL_FORMAT, 'entries': [row | {'routine': '00:9000'}]}, raw_routines=True)
        with contextlib.redirect_stdout(io.StringIO()):
            hook.cells_check(r)
            hook.cells_check(r, {'format': hook.CELL_FORMAT, 'entries': [row]}, 0x15FF80)
        with self.assertRaises(ValueError):
            hook.cells_rewrite(r, {'format': hook.CELL_FORMAT, 'entries': [row | {'routine': '01:9000'}]}, raw_routines=True)


if __name__ == '__main__':
    unittest.main()
