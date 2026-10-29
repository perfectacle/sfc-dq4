"""그림 번호 표 늘리기의 배치·물체 표·검증을 롬 없이 검사한다."""
import contextlib
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch as mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dq5picturegrow as pg
import dq5sprite as S
from dq5map import Rom, lorom


def rom():
    data = bytearray(0x180000)

    def put(addr, raw):
        data[lorom(addr):lorom(addr) + len(raw)] = bytes(raw)

    for at in pg.READERS:
        put(at, [0xBF, 0xD0, 0x86, 0x25])
    put(pg.HOOK, pg.HOOK_ORIG)
    for s in range(S.SET_COUNT):
        put(S.SET_POINTERS + s * 2, [0xFF, 0xFF] if 0x70 <= s < 0x80 else [0x00, 0x10])
    for site in S.SET_TABLE_SITES:
        put(site, S.SET_POINTERS.to_bytes(3, 'little'))
    put(pg.TABLE, [g % 0x60 for g in range(pg.COUNT)])
    put(pg.TALK_READER, [0xBF, 0x2F, 0x86, 0x05])
    put(pg.TALK_LIST, [0x46, 0x47, 0x12, 0xFE, 0xFF])
    return Rom(bytes(data))


def tiles(rom, s):
    return 40 if s == 0x50 else 10


def doc(*rows):
    return {'format': pg.FORMAT, 'pictures': list(rows)}


def apply(r, result):
    data = bytearray(r.d)
    if result.get('rom_size'):
        data.extend(bytes(0x400000 - len(data)))
    for w in result['writes']:
        bank, addr = (int(v, 16) for v in w['at'].split(':'))
        new = bytes.fromhex(w['hex'])
        off = lorom(bank << 16 | addr)
        data[off:off + len(new)] = new
    return Rom(bytes(data))


class PictureGrowTests(unittest.TestCase):
    def setUp(self):
        patcher = mock('dq5picturegrow.set_tiles', side_effect=tiles)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_dump_original(self):
        out = pg.dump(rom())
        self.assertEqual(out['table'], '25:86D0')
        self.assertEqual(len(out['pictures']), 0xA9)
        self.assertEqual([p['picture'] for p in out['pictures'] if p['object']],
                         ['46', '47', '48', '78', '7F', '84', 'A2', 'A3', 'A4', 'A5', 'A6', 'A7', 'A8'])
        self.assertEqual([p['picture'] for p in out['pictures'] if p['talk_skip']], ['12', '46', '47'])

    def test_grow_layout_and_round_trip(self):
        r = rom()
        result = pg.patch(r, doc({'picture': 'A9', 'set': '04'},
                                 {'picture': '18', 'object': True}, {'picture': '46', 'talk_skip': False},
                                 {'picture': '20', 'talk_skip': True}), 0x0BFBB0)
        by = {w['at']: w for w in result['writes']}
        self.assertEqual(by['1E:DC67']['hex'], '22 b0 fb 0b 80 1c')
        self.assertEqual(by['1F:CF46']['hex'], 'bf fb 0b')
        self.assertEqual(by['03:D203']['hex'], 'bf fb 0b')
        blob = bytes.fromhex(by['0B:FBB0']['hex'])
        objects = 0x0BFBB0 + 15 + 0xAA
        self.assertEqual(blob[:15].hex(' '), 'da a6 0a bf ' + objects.to_bytes(3, 'little').hex(' ') + ' 19 a0 33 99 a0 33 fa 6b')
        self.assertEqual(by['05:85FF']['hex'], (objects + 256).to_bytes(3, 'little').hex(' '))
        self.assertEqual(blob[15 + 0xAA + 256:], bytes([0x12, 0x20, 0x47, 0xFE, 0xFF]))
        self.assertEqual(blob[15 + 0xA9], 0x04)
        flags = blob[15 + 0xAA:15 + 0xAA + 256]
        self.assertEqual((flags[0x18], flags[0xA9], flags[0xA8], flags[0xAA], flags[0x46]), (9, 0, 9, 9, 9))
        after = apply(r, result)
        out = pg.dump(after)
        self.assertEqual(len(out['pictures']), 0xAA)
        self.assertEqual(out['pictures'][0xA9], {'picture': 'A9', 'set': '04', 'object': False, 'talk_skip': False})
        self.assertFalse(out['pictures'][0x46]['talk_skip'])
        self.assertTrue(out['pictures'][0x20]['talk_skip'])
        self.assertTrue(out['pictures'][0x18]['object'])
        self.assertEqual(pg.patch(after, out, 0x0BFBB0)['writes'], [])

    def test_expanded_bank(self):
        r = rom()
        result = pg.patch(r, doc({'picture': 'A9', 'set': '04'}), 0x3B8000)
        self.assertEqual(result['rom_size'], 4)
        self.assertNotIn('orig', next(w for w in result['writes'] if w['at'] == '3B:8000'))
        self.assertEqual(pg.dump(apply(r, result))['table'], '3B:800F')

    def test_guards(self):
        r = rom()
        bad = [doc({'picture': 'A9'}), doc({'picture': 'AB', 'set': '04'}), doc({'picture': 'A9', 'set': '70'}),
               doc({'picture': 'A9', 'set': 'A3'}), doc({'picture': '18', 'object': 1}),
               doc({'picture': '18', 'set': '04'}, {'picture': '18', 'object': True}), doc({'picture': '18', 'x': 1}),
               {'format': pg.FORMAT, 'table': '0B:8000', 'pictures': []}, {'format': 'other', 'pictures': []},
               doc({'picture': '9A', 'set': '04'}), doc({'picture': 'FF', 'set': '04'}),
               doc({'picture': '18', 'set': '50'}), doc({'picture': '18', 'talk_skip': 1})]
        for d in bad:
            with self.subTest(d=d), self.assertRaises(ValueError):
                pg.patch(r, d, 0x0BFBB0)
        with self.assertRaises(ValueError):
            pg.patch(r, doc(), 0x0BFF00)
        with self.assertRaises(ValueError):
            pg.patch(r, doc(), 0x1EDC00)
        self.assertEqual(len(pg.patch(r, doc({'picture': '9A', 'set': pg.dump(r)['pictures'][0x9A]['set']}), 0x0BFBB0)['writes']), 5)
        self.assertTrue(pg.patch(r, doc({'picture': 'A9', 'set': '70'}), 0x0BFBB0, new_sets=[0x70])['writes'])
        for at, value in ((0x03D202 + 1, 0), (0x1FCF45, 0xAF), (pg.HOOK, 0xEA), (pg.TALK_READER, 0xAF)):
            data = bytearray(r.d)
            data[lorom(at)] = value
            with self.subTest(at=hex(at)), self.assertRaises(ValueError):
                pg.dump(Rom(bytes(data)))

    def test_valid_sets_follow_moved_table(self):
        # dq5spritewrite.py --sets-at 으로 옮긴 표(여기서는 3B:8000, A5 만 채움)를 읽는다.
        data = bytearray(rom().d)
        data.extend(bytes(0x200000 - len(data)))
        moved = bytearray(b'\xff' * 0x200)
        moved[0xA5 * 2:0xA5 * 2 + 2] = b'\x00\x82'
        data[lorom(0x3B8000):lorom(0x3B8000) + 0x200] = moved
        for site in S.SET_TABLE_SITES:
            data[lorom(site):lorom(site) + 3] = (0x3B8000).to_bytes(3, 'little')
        self.assertEqual(pg.valid_sets(Rom(bytes(data))), {0xA5})
        self.assertIn(0x04, pg.valid_sets(rom()))

    def test_check_through_builder(self):
        r = rom()
        with contextlib.redirect_stdout(io.StringIO()):
            pg.check(r, None, 0x0BFBB0)
            pg.check(r, doc({'picture': 'A9', 'set': '04'}), 0x0BFBB0)


if __name__ == '__main__':
    unittest.main()
