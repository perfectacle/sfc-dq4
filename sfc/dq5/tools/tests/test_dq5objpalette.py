"""OBJ 팔레트 색·맵 팔레트·세트 팔레트 배정 쓰기의 바이트와 입력 검사, 세트 팔레트 표·맵 팔레트 줄 옮기기 루틴."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch as mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dq5objpalette as P  # noqa: E402
import dq5sprite as S  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402
from dq5objpalette import FORMAT, affected, patch  # noqa: E402
from w65816 import Cpu  # noqa: E402

RECORD = 0x1FD787


def fixture():
    data = bytearray(0x200000)
    for p in range(8):
        for i in range(16):
            at = lorom(S.OBJ_PALETTES + (p * 16 + i) * 2)
            data[at:at + 2] = (p * 0x100 + i).to_bytes(2, 'little')
    data[lorom(RECORD) + 2] = 0x45          # 자료 뱅크 05, 팔레트 1
    entry = 0x019A12
    data[lorom(entry):lorom(entry) + 5] = bytes([4, 6, 0xFF, 0, 0x0B])
    data[lorom(entry + P.MAP_ENTRY)] = 0xFF
    for site in S.SET_PALETTE_SITES:
        data[lorom(site):lorom(site) + len(P.SITE_ORIG)] = P.SITE_ORIG
    data[lorom(P.SWAP_SITE):lorom(P.SWAP_SITE) + len(P.SWAP_ORIG)] = P.SWAP_ORIG
    data[lorom(P.PICTURE_SITE):lorom(P.PICTURE_SITE) + 4] = bytes.fromhex('bf d0 86 25')
    data[lorom(P.MAP_ALT):lorom(P.MAP_ALT) + len(P.MAP_ALT_ORIG)] = P.MAP_ALT_ORIG
    data[lorom(P.MAP_LOADER):lorom(P.MAP_LOADER) + P.MAP_LOADER_SIZE] = loader()
    return Rom(data)


def loader():
    """01:996A 루틴의 꼴만 갖춘 가짜(고치는 자리의 명령·피연산자만 원래 값, 나머지는 NOP)."""
    raw = bytearray(b'\xea' * P.MAP_LOADER_SIZE)
    raw[0:4] = bytes.fromhex('08 8b 4b ab')
    raw[P.MAP_RTS] = 0x60
    for o, (op, k) in P.MAP_TABLE_REFS.items():
        raw[o:o + 3] = bytes([op]) + (0x9A12 + k).to_bytes(2, 'little')
    for o, t in P.MAP_JUMPS.items():
        raw[o:o + 3] = bytes([0x4C]) + t.to_bytes(2, 'little')
    return raw


def apply(rom, writes):
    data = bytearray(rom.d)
    for w in writes:
        b, a = int(w['at'][:2], 16), int(w['at'][3:], 16)
        new = bytes.fromhex(w['hex'])
        data[lorom(b << 16 | a):lorom(b << 16 | a) + len(new)] = new
    return Rom(data)


def records(rom, s):
    if s not in (0x84, 0x04):
        return None
    return {'set': s, 'record': RECORD, 'palette': rom.u8(RECORD + 2) >> 6, 'cells': [], 'data': 0, 'tiles': 1}


class PaletteTests(unittest.TestCase):
    def setUp(self):
        self.rom = fixture()
        self.mocks = [mock('dq5objpalette.S.set_record', side_effect=records),
                      mock('dq5palsetwrite.known_maps', return_value={2: {6}}),
                      mock('dq5objpalette.S.map_object_places', return_value=[]),
                      mock('dq5objpalette.S.map_palettes', side_effect=lambda rom: [
                          {'entry': 0x019A12, 'bc': 4, 'bd': 6, 'flag': 0xFF, 'mask': 0, 'line': 0x0B,
                           'colors': [0] * 16}])]
        for m in self.mocks:
            m.start()

    def tearDown(self):
        for m in self.mocks:
            m.stop()

    def run_patch(self, **doc):
        return patch(self.rom, {'format': FORMAT, **doc})['writes']

    def test_writes(self):
        colors = list(range(1, 16))
        writes = self.run_patch(palettes=[{'palette': 7, 'colors': colors}],
                                map_palettes=[{'index': 0, 'map': '04/06', 'line': '0B', 'colors': colors}],
                                sets=[{'set': '84', 'palette': 2}])
        self.assertEqual([w['at'] for w in writes], ['04:97B8', '01:9A17', '1F:D789', '1F:CFB7'])
        self.assertEqual(writes[0]['hex'][:11], '01 00 02 00')
        self.assertEqual((writes[2]['hex'], writes[2]['orig']), ('85', '45'))
        # 세트 팔레트를 쓰면 표 주소를 그대로 다시 써 둔다. --sets-at 의 표 주소 쓰기와 함께 빌드하면 빌더가 겹침으로 막는다.
        self.assertEqual(writes[3]['hex'], writes[3]['orig'])
        self.assertNotIn('1F:CFB7', [w['at'] for w in self.run_patch(palettes=[{'palette': 7, 'colors': colors}])])
        # 같은 색이면 쓰지 않는다.
        same = [7 * 0x100 + i for i in range(1, 16)]
        self.assertEqual(self.run_patch(palettes=[{'palette': 7, 'colors': same}]), [])

    def test_affected_sets(self):
        doc = {'format': FORMAT, 'palettes': [{'palette': 1, 'colors': [0] * 15}], 'sets': [{'set': '84', 'palette': 1}]}
        with mock('dq5objpalette.S.SET_COUNT', 0x85):
            self.assertEqual(affected(self.rom, doc), {1: ['04', '84']})

    def test_rejects(self):
        for doc in ({'palettes': [{'palette': 8, 'colors': [0] * 15}]},
                    {'palettes': [{'palette': True, 'colors': [0] * 15}]},
                    {'palettes': [{'palette': 0, 'colors': [0] * 16}]},
                    {'palettes': [{'palette': 0, 'colors': [0x8000] + [0] * 14}]},
                    {'palettes': [{'palette': 0, 'colors': [0] * 15}, {'palette': 0, 'colors': [0] * 15}]},
                    {'map_palettes': [{'index': 1, 'colors': [0] * 15}]},
                    {'map_palettes': [{'index': 0, 'map': '04/07', 'colors': [0] * 15}]},
                    {'map_palettes': [{'index': 0, 'line': '0A', 'colors': [0] * 15}]},
                    {'sets': [{'set': '85', 'palette': 1}]},
                    {'sets': [{'set': '84', 'palette': 4}]},
                    {'sets': [{'set': '84', 'palette': 1}, {'set': '84', 'palette': 2}]},
                    {'sets': [{'set': '84', 'palette': 1, 'image': 'x'}]},
                    {'other': []}):
            with self.subTest(doc=doc), self.assertRaises(ValueError):
                self.run_patch(**doc)

    def test_set_table_hook(self):
        doc = {'sets': [{'set': '84', 'palette': 6}, {'set': '04', 'palette': 1}]}
        with self.assertRaisesRegex(ValueError, '--at'):
            self.run_patch(**doc)
        result = patch(self.rom, {'format': FORMAT, **doc}, '3B:8000')
        writes = {w['at']: w for w in result['writes']}
        self.assertEqual(result['rom_size'], 2)
        for site in ('1F:CFC8', '1F:D0FB'):
            self.assertEqual(writes[site]['hex'], '22 00 80 3b' + ' ea' * 9)
        swap = len(P.set_routine(0))
        self.assertEqual(writes['03:D24D']['hex'][:11], f'22 {swap:02x} 80 3b')
        # 그림 번호 표 주소를 루틴이 품으므로 그 읽기를 그대로 다시 써 둔다. 레코드는 건드리지 않는다.
        self.assertEqual(writes['03:D202']['hex'], writes['03:D202']['orig'])
        self.assertNotIn('1F:D789', writes)
        self.assertNotIn('1F:CFB7', writes)
        blob = bytes.fromhex(writes['3B:8000']['hex'])
        table = swap + len(P.swap_routine(0, 0))
        self.assertEqual(len(blob), table + 0x100)
        self.assertEqual((blob[table + 0x84], blob[table + 0x04], blob[table + 0x85]), (6, 0xFF, 0xFF))
        self.assertNotIn('orig', writes['3B:8000'])
        hooked = apply(self.rom, result['writes'])
        self.assertEqual(S.set_palette_table(hooked), 0x3B8000 + table)
        self.assertEqual((S.set_obj_palette(hooked, 0x84), S.set_obj_palette(hooked, 0x04)), (6, 1))
        # 훅이 있는 롬은 sets 를 표에 쓰고(팔레트 0~3 도), 같은 값이면 쓰지 않는다.
        again = patch(hooked, {'format': FORMAT, 'sets': [{'set': '84', 'palette': 6}, {'set': '04', 'palette': 2}]})
        self.assertEqual([(w['at'], w['hex']) for w in again['writes']], [(P.cpu(0x3B8000 + table + 4), '02')])
        # 원래 명령이 아닌 롬(다른 도구가 고친 자리)은 거부한다.
        broken = bytearray(self.rom.d)
        broken[lorom(P.SWAP_SITE)] = 0xEA
        with self.assertRaisesRegex(ValueError, '원래 세트 팔레트 명령'):
            patch(Rom(broken), {'format': FORMAT, **doc}, '3B:8000')

    def test_set_routine_runs(self):
        """루틴을 해석기로 돌린다: 표 값이 있으면 팔레트 × 2, FF 면 레코드 +2 bit6-7 × 2, Y 는 2."""
        data = bytearray(0x200000)
        at, table, record = 0x3B8000, 0x3B9000, 0x0C8000
        data[lorom(at):lorom(at) + 32] = P.set_routine(table)
        data[lorom(table) + 0x84] = 6
        data[lorom(table) + 0x04] = 0xFF
        data[lorom(record) + 2] = 0x8D       # 자료 뱅크 0D, 팔레트 2
        for s, want in ((0x84, 0x0C), (0x04, 0x04)):
            c = Cpu(bytes(data), bytearray(0x20000))
            c.wram[0x0C], c.wram[0x09:0x0C] = s, record.to_bytes(3, 'little')
            c.p = 0x30
            c.jsl(at)
            self.assertEqual((c.wram[0x01], c.y, c.p & 0x30), (want, 2, 0x30), f'세트 {s:02X}')

    def test_swap_routine_runs(self):
        data = bytearray(0x200000)
        at, pictures, table, record = 0x3B8000, 0x258000, 0x3B9000, 0x0F8000
        data[lorom(at):lorom(at) + 64] = P.swap_routine(pictures, table)
        data[lorom(pictures) + 0x29] = 0x84
        data[lorom(pictures) + 0x2B] = 0x04
        data[lorom(table) + 0x84] = 7
        data[lorom(table) + 0x04] = 0xFF
        data[lorom(record) + 2] = 0x6F       # 팔레트 1, 뱅크 2F(bit5 가 $08 bit0 으로 가는 원래 명령 그대로)
        for g, want in ((0x29, 0x0E), (0x2B, 0x03)):
            c = Cpu(bytes(data), bytearray(0x20000))
            c.wram[0x1EC0], c.wram[0x1EC1], c.wram[0:3] = g, 0, record.to_bytes(3, 'little')
            c.p, c.x = 0x20, 0x1234
            c.jsl(at)
            self.assertEqual((c.wram[0x08], c.y, c.x), (want, 2, 0x1234), f'그림 {g:02X}')

    def test_map_lines(self):
        line = [0x111] * 15
        doc = {'map_palettes': [{'index': 0, 'colors': list(range(1, 16))}],
               'new_map_palettes': [{'map': '02/06', 'line': '0E', 'colors': line},
                                    {'map': 'FE/01', 'line': '0D', 'flag': '85', 'mask': '01', 'colors': line}]}
        with self.assertRaisesRegex(ValueError, '--at'):
            self.run_patch(**doc)
        writes = {w['at']: w for w in patch(self.rom, {'format': FORMAT, **doc}, '3B:8000')['writes']}
        entry = 0x3B8000 + 14
        self.assertEqual(writes['01:996A']['hex'], '22 0e 80 3b 60')
        self.assertEqual(writes['01:9954']['hex'], '22 00 80 3b 60')
        self.assertNotIn('01:9A17', writes)       # 기존 항목의 색은 옮긴 표에 쓴다
        blob = bytes.fromhex(writes['3B:8000']['hex'])
        code = blob[14:14 + P.MAP_LOADER_SIZE]
        table = entry + P.MAP_LOADER_SIZE
        self.assertEqual(blob[:14].hex(' '), '08 8b 4b ab c2 30 a9 14 3b a2 7e 00 80 0c')
        for o, (op, k) in P.MAP_TABLE_REFS.items():
            self.assertEqual(code[o:o + 3], bytes([op]) + (table + k & 0xFFFF).to_bytes(2, 'little'))
        for o, t in P.MAP_JUMPS.items():
            self.assertEqual(code[o:o + 3], b'\x4c' + (entry + t - P.MAP_LOADER & 0xFFFF).to_bytes(2, 'little'))
        self.assertEqual(code[P.MAP_RTS], 0x6B)
        rows = blob[14 + P.MAP_LOADER_SIZE:]
        self.assertEqual(len(rows), P.MAP_ENTRY * 3 + 1)
        self.assertEqual(rows[5:7], b'\x01\x00')
        self.assertEqual(rows[P.MAP_ENTRY:P.MAP_ENTRY + 7], bytes([2, 6, 0xFF, 0, 0x0E, 0x11, 0x01]))
        self.assertEqual(rows[P.MAP_ENTRY * 2:P.MAP_ENTRY * 2 + 5], bytes([0xFE, 1, 0x85, 1, 0x0D]))
        self.assertEqual(rows[-1], 0xFF)
        moved = apply(self.rom, writes.values())
        self.assertEqual(S.map_palette_table(moved), table)
        with self.assertRaisesRegex(ValueError, '이미 옮긴'):
            patch(moved, {'format': FORMAT, 'new_map_palettes': doc['new_map_palettes'][:1]}, '3B:9000')
        broken = bytearray(self.rom.d)
        broken[lorom(P.MAP_LOADER) + 0x15] = 0xB9
        with self.assertRaisesRegex(ValueError, '원래 맵 팔레트 루틴'):
            patch(Rom(broken), {'format': FORMAT, **doc}, '3B:8000')

    def test_rejects_new(self):
        line = [0] * 15
        for doc, at in (({'new_map_palettes': [{'map': '02/07', 'line': '0E', 'colors': line}]}, '3B:8000'),
                        ({'new_map_palettes': [{'map': 'FE/03', 'line': '0E', 'colors': line}]}, '3B:8000'),
                        ({'new_map_palettes': [{'map': '02/06', 'line': '10', 'colors': line}]}, '3B:8000'),
                        ({'new_map_palettes': [{'map': '02/06', 'line': '0E', 'flag': '05', 'colors': line}]}, '3B:8000'),
                        ({'new_map_palettes': [{'map': '02/06', 'line': '0E', 'mask': '01', 'colors': line}]}, '3B:8000'),
                        ({'new_map_palettes': [{'map': '02/06', 'line': '0E', 'colors': line, 'index': 1}]}, '3B:8000'),
                        ({'new_map_palettes': [{'map': '02/06', 'line': '0E', 'colors': line}]}, '40:8000'),
                        ({'new_map_palettes': [{'map': '02/06', 'line': '0E', 'colors': line}]}, '3B:FF80'),
                        ({'sets': [{'set': '84', 'palette': 8}]}, '3B:8000')):
            with self.subTest(doc=doc, at=at), self.assertRaises(ValueError):
                patch(self.rom, {'format': FORMAT, **doc}, at)

    def test_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            rom, src, out = Path(tmp, 'rom.sfc'), Path(tmp, 'doc.json'), Path(tmp, 'out.json')
            rom.write_bytes(self.rom.d)
            src.write_text(json.dumps({'format': FORMAT, 'sets': [{'set': '84', 'palette': 5}]}), encoding='utf-8')
            for extra, code in (([], 1), (['--at', '3B:8000'], 0)):
                argv = ['dq5objpalette', str(rom), 'patch', str(src), '-o', str(out), *extra]
                with self.subTest(extra=extra), mock.object(sys, 'argv', argv), \
                        contextlib.redirect_stdout(io.StringIO()) as stdout, contextlib.redirect_stderr(io.StringIO()) as err:
                    self.assertEqual(P.main(), code)
                    if code:
                        self.assertIn('--at', err.getvalue())
                    else:
                        self.assertIn('OBJ 팔레트 5: 세트 84', stdout.getvalue())
            self.assertIn('3B:8000', [w['at'] for w in json.loads(out.read_text(encoding='utf-8'))['writes']])


if __name__ == '__main__':
    unittest.main()
