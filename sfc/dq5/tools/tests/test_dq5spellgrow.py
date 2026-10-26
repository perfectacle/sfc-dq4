"""행동 번호 늘리기의 표 옮기기·스텁·입력 검사를 원본 롬 없이 확인한다."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dq5spellgrow as grow  # noqa: E402
from dq5build import build, parse_at  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402


def fixture():
    data = bytearray(0x180000)
    for name, (base, size, readers) in grow.TABLES.items():
        for i in range(grow.COUNT * size):
            data[lorom(base) + i] = (i * 7 + len(name)) & 0xFF
        for pc in readers:
            data[lorom(pc):lorom(pc) + 4] = bytes([0xBF]) + base.to_bytes(3, 'little')
    for i in range(grow.COUNT * 2):
        data[lorom(grow.HANDLERS) + i] = (i * 3) & 0xFF
    for pc in grow.HANDLER_CALLS:
        data[lorom(pc):lorom(pc) + 3] = bytes([0xFC]) + (grow.HANDLERS & 0xFFFF).to_bytes(2, 'little')
    data[lorom(0x118014):lorom(0x118014) + 6] = bytes.fromhex('e9 27 c9 12 b0 08')
    data[lorom(grow.FIELD_CALL):lorom(grow.FIELD_CALL) + 3] = bytes.fromhex('fc 24 80')
    for i in range(grow.FIELD_COUNT * 2):
        data[lorom(grow.FIELD) + i] = 0x80 + i
    data[lorom(0x7FD7)] = 0x0B
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

    def test_relocates_tables_and_copies_rows(self):
        manifest = grow.patch(self.rom, doc({'id': 'AB', 'copy': '27', 'MP': 9}, {'id': 'AC', 'copy': '01', 'menu_mp': 7}), 0x6E8000)
        self.assertEqual(manifest['rom_size'], 4)
        after = apply(self.data, manifest)
        values = grow.read_back(after, 0x6E8000, 2)
        flags = self.rom.u8(grow.TABLES['flags'][0] + 0x27) & 0xE0 | 9
        self.assertEqual(values[0][0], f'{flags:02x}')
        self.assertEqual(values[1][3], '07')
        self.assertEqual(values[0][1], self.data[lorom(0x268865) + 0x4E:lorom(0x268865) + 0x50].hex())
        self.assertEqual(values[1][6], self.data[lorom(grow.HANDLERS) + 2:lorom(grow.HANDLERS) + 4].hex())
        for pc in grow.HANDLER_CALLS:
            self.assertEqual(after.d[lorom(pc):lorom(pc) + 3], bytes([0x20, 0xE0, 0xFF]))
        stub = after.d[lorom(grow.HANDLER_STUB):lorom(grow.HANDLER_STUB) + 11]
        self.assertEqual(stub, bytes.fromhex('e0 56 01 b0 03 7c f9 b7 7c 95 fe'))
        field = after.d[lorom(grow.FIELD_STUB):lorom(grow.FIELD_STUB) + 38]
        self.assertEqual(field[:11], bytes.fromhex('90 05 eb a9 01 eb aa eb a9 00 eb'))
        self.assertEqual(field[19:22], bytes([0xE0]) + ((0xAB - 0x27) * 2).to_bytes(2, 'little'))
        self.assertEqual(field[34:36], bytes([0x80, 0x81]))
        self.assertEqual(field[36:38], bytes([0x22, 0x80]))
        self.assertEqual(after.u8(grow.FIELD_LIMIT), 0xFF)

    def test_battle_only_skips_field(self):
        manifest = grow.patch(self.rom, doc({'id': 'AB', 'copy': '01'}), 0x6E8000)
        self.assertFalse(any(w['at'].startswith('11:') for w in manifest['writes']))

    def test_rejects(self):
        bad = [doc({'id': 'AC', 'copy': '27'}), doc({'id': 'AB', 'copy': 'AB'}), doc({'id': 'AB', 'copy': '27', 'MP': 32}),
               doc({'id': 'AB', 'copy': '27', 'menu_mp': 256}), doc({'id': 'AB', 'copy': '27', 'x': 1}), doc(),
               {'format': 'x', 'spells': [{'id': 'AB', 'copy': '27'}]},
               doc(*[{'id': f'{0xAB + i:02X}', 'copy': '27'} for i in range(11)])]
        for d in bad:
            with self.subTest(d=str(d)[:60]), self.assertRaises(ValueError):
                grow.patch(self.rom, d, 0x6E8000)
        with self.assertRaises(ValueError):
            grow.patch(self.rom, doc({'id': 'AB', 'copy': '27'}), 0x6EFF00)
        data = bytearray(self.data)
        data[lorom(grow.HANDLER_CALLS[0])] = 0x20
        with self.assertRaises(ValueError):
            grow.patch(Rom(bytes(data)), doc({'id': 'AB', 'copy': '27'}), 0x6E8000)
        data = bytearray(self.data)
        data[lorom(0x20FFF0)] = 1
        with self.assertRaises(ValueError):
            grow.patch(Rom(bytes(data)), doc({'id': 'AB', 'copy': '27'}), 0x6E8000)


if __name__ == '__main__':
    unittest.main()
