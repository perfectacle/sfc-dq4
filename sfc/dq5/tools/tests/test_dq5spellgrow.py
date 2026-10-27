"""새 행동 번호 쓰기의 제자리 쓰기·연출 표 옮기기·스텁·입력 검사를 원본 롬 없이 확인한다."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dq5spellgrow as grow  # noqa: E402
from dq5build import build, parse_at  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402


def fixture():
    data = bytearray(0x180000)
    for name, (base, size, empty) in grow.WIDE.items():
        for n in range(0x100):
            v = empty if grow.FIRST <= n <= grow.LAST else (n * 7 + len(name)) & (0xFF if size == 1 else 0xFFFF)
            data[lorom(base) + n * size:lorom(base) + (n + 1) * size] = v.to_bytes(size, 'little')
    for n in range(0x66):
        data[lorom(grow.MENU_MP) + n] = n & 0x1F
    data[lorom(0x219BAD):lorom(0x219BAD) + 4] = bytes.fromhex('bf b4 9b 21')
    for name, (base, readers) in grow.FX.items():
        for n in range(grow.FX_COUNT):
            data[lorom(base) + n] = (n + len(name)) & 0xFF
        for pc in readers:
            data[lorom(pc):lorom(pc) + 4] = bytes([0xBF]) + base.to_bytes(3, 'little')
    data[lorom(0x118014):lorom(0x118014) + 6] = bytes.fromhex('e9 27 c9 12 b0 08')
    data[lorom(grow.FIELD_CALL):lorom(grow.FIELD_CALL) + 3] = bytes.fromhex('fc 24 80')
    for i in range(grow.FIELD_COUNT * 2):
        data[lorom(grow.FIELD) + i] = 0x80 + i
    for site, orig, *_ in grow.CLASS_SITES:
        data[lorom(site):lorom(site) + 4] = bytes.fromhex(orig)
    return bytes(data)


def doc(*spells):
    return {'format': grow.FORMAT, 'spells': list(spells)}


def apply(data, manifest):
    writes = [(parse_at(w['at'])[0], bytes.fromhex(w['hex']), bytes.fromhex(w['orig']) if 'orig' in w else None, w['note'])
              for w in manifest['writes']]
    return Rom(build(data, [('t', manifest.get('rom_size', 0), writes)], manifest.get('rom_size', 0))[0])


class SpellGrowTests(unittest.TestCase):
    def setUp(self):
        self.data = fixture()
        self.rom = Rom(self.data)

    def test_writes_in_place_and_moves_fx(self):
        manifest = grow.patch(self.rom, doc({'id': 'C6', 'copy': '27', 'MP': 9, 'class': 'spell'},
                                            {'id': 'C7', 'copy': '01', 'menu_mp': 7}), 0x6E8000)
        after = apply(self.data, manifest)
        self.assertEqual(grow.value(after, 0x268765, 1, 0xC6), grow.value(self.rom, 0x268765, 1, 0x27) & 0xE0 | 9)
        for name in ('executor', 'executor_alt', 'handler'):
            base, size, _ = grow.WIDE[name]
            self.assertEqual(grow.value(after, base, size, 0xC7), grow.value(self.rom, base, size, 0x01))
            self.assertEqual(grow.value(after, base, size, 0xD5), grow.value(self.rom, base, size, 0xD5))
        self.assertEqual(after.u8(grow.MENU_MP + 0xC7), 7)
        where = int.from_bytes(after.d[lorom(0x268B6F):lorom(0x268B6F) + 3], 'little')
        self.assertEqual(where, 0x6E8000)
        self.assertEqual(after.u8(where + 0xC7), self.rom.u8(0x268BE0 + 0x01))
        self.assertEqual(after.u8(where + 0x10), self.rom.u8(0x268BE0 + 0x10))
        for site, *_ in grow.CLASS_SITES:
            self.assertEqual(after.u8(site), 0x5C)
        stub = int.from_bytes(after.d[lorom(0x258BF4):lorom(0x258BF4) + 3], 'little')
        self.assertEqual(after.d[lorom(stub):lorom(stub) + 12], bytes.fromhex('c9 66 90 0d c9 c6 90 04 c9 c7 90 05'))
        field = after.d[lorom(grow.FIELD_STUB):lorom(grow.FIELD_STUB) + 38]
        self.assertEqual(field[:11], bytes.fromhex('90 05 eb a9 01 eb aa eb a9 00 eb'))
        self.assertEqual(field[34:36], bytes([0x80, 0x81]))
        self.assertEqual(field[36:38], bytes([0x22, 0x80]))

    def test_skill_only_keeps_boundaries(self):
        manifest = grow.patch(self.rom, doc({'id': 'C6', 'copy': '01'}), 0x6E8000)
        self.assertFalse(any(w['at'] in ('25:8BF3', '20:8460', '20:8EE8') for w in manifest['writes']))
        self.assertFalse(any(w['at'].startswith('11:') for w in manifest['writes']))

    def test_rejects(self):
        bad = [doc({'id': 'C7', 'copy': '27'}), doc({'id': 'AB', 'copy': '27'}), doc({'id': 'C6', 'copy': 'AB'}),
               doc({'id': 'C6', 'copy': '27', 'MP': 32}), doc({'id': 'C6', 'copy': '27', 'menu_mp': 256}),
               doc({'id': 'C6', 'copy': '27', 'x': 1}), doc(), doc({'id': 'C6', 'copy': '27', 'class': 'x'}),
               doc({'id': 'C6', 'copy': '27'}, {'id': 'C7', 'copy': '27', 'class': 'spell'}),
               {'format': 'x', 'spells': [{'id': 'C6', 'copy': '27'}]}]
        for d in bad:
            with self.subTest(d=str(d)[:70]), self.assertRaises(ValueError):
                grow.patch(self.rom, d, 0x6E8000)
        with self.assertRaises(ValueError):
            grow.patch(self.rom, doc({'id': 'C6', 'copy': '27'}), 0x6EFF00)
        data = bytearray(self.data)
        data[lorom(0x20B7F9) + 0xC6 * 2] = 0x12
        with self.assertRaises(ValueError):
            grow.patch(Rom(bytes(data)), doc({'id': 'C6', 'copy': '27'}), 0x6E8000)
        data = bytearray(self.data)
        data[lorom(grow.CLASS_SITES[0][0])] = 0xEA
        with self.assertRaises(ValueError):
            grow.patch(Rom(bytes(data)), doc({'id': 'C6', 'copy': '27', 'class': 'spell'}), 0x6E8000)

    def test_check_round_trip(self):
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            grow.check(self.rom, doc({'id': 'C6', 'copy': '27', 'class': 'spell'}, {'id': 'C7', 'copy': '01'}), 0x6E8000)


if __name__ == '__main__':
    unittest.main()
