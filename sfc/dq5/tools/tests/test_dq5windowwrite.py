"""창 레코드 자리·크기 쓰기를 원본 롬 없이 검사한다."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dq5map import Rom, lorom  # noqa: E402
from dq5text import WINDOWS  # noqa: E402
from dq5windowwrite import FORMAT, dump, edits, message_sites, patch, records  # noqa: E402

COUNT = 0x30
# 원본처럼 진짜 창 뒤에 첫 레코드까지 창이 아닌 포인터가 남는다.
JUNK = (0x00FF, 0x0000, 0xFFFF, 0xFF00)


def pointer(data, n, low):
    data[lorom(WINDOWS + n * 2):lorom(WINDOWS + n * 2) + 2] = low.to_bytes(2, 'little')


def fixture():
    data = bytearray(0x180000)
    first = (WINDOWS & 0xFFFF) + (COUNT + len(JUNK)) * 2
    for n in range(COUNT):
        addr = first + n * 8
        pointer(data, n, addr)
        data[lorom(0x040000 | addr):lorom(0x040000 | addr) + 8] = bytes([0x02, 0x94, 0xC8, 0xA5, 0, 1, 0xFE, 0xFF])
    for n, low in enumerate(JUNK, COUNT):
        pointer(data, n, low)
    alias = lorom(0x040000 | first + 3 * 8)
    data[alias:alias + 3] = bytes([0x80, 0, 2])
    data[lorom(0x040000 | first + 5 * 8)] = 0x42
    pointer(data, 7, first + 6 * 8)
    # 전투 메시지 창 18·25 는 원본처럼 (2,21) 28 × 7 이고, 글자·▼ 칸을 박아 둔 코드도 원본 값으로 둔다.
    for n, head in ((0x18, 0x02), (0x25, 0x42)):
        at = lorom(0x040000 | first + n * 8)
        data[at:at + 4] = bytes([head, 0x95 if n == 0x18 else 0x15, 0x1C, 0x07])
    for addr, op, size, value, _ in message_sites(2, 21):
        data[lorom(addr):lorom(addr) + 1 + size] = bytes([op]) + value.to_bytes(size, 'little')
    return bytes(data)


def apply(data, manifest):
    out = bytearray(data)
    for w in manifest['writes']:
        off = lorom(int(w['at'].replace(':', ''), 16))
        raw = bytes.fromhex(w['hex'])
        assert out[off:off + len(raw)] == bytes.fromhex(w['orig'])
        out[off:off + len(raw)] = raw
    return bytes(out)


class WindowWriteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = fixture()
        cls.rom = Rom(cls.data)
        cls.first = cls.rom.u16(WINDOWS) | 0x040000

    def with_byte(self, addr, value):
        data = bytearray(self.data)
        data[lorom(addr)] = value
        return bytes(data)

    def test_dump_and_unchanged(self):
        doc = dump(self.rom)
        self.assertEqual(len(records(self.rom)), COUNT)
        self.assertEqual(len(doc['windows']), COUNT - 1)
        self.assertEqual(doc['windows'][0], {'index': '00', 'x': 2, 'y': 20, 'w': 8, 'h': 5})
        self.assertEqual(patch(self.rom, doc)['writes'], [])

    def test_table_stops_at_junk_and_bank_end(self):
        table = records(self.rom)
        self.assertEqual(max(table), COUNT - 1)
        data = bytearray(self.data)
        pointer(data, 0x10, 0xFFFE)
        with self.assertRaises(ValueError):
            records(Rom(bytes(data)))
        pointer(data, 0x10, 0xFFFC)
        self.assertEqual(records(Rom(bytes(data)))[0x10], 0x04FFFC)

    def test_move_keeps_other_bits(self):
        manifest = patch(self.rom, {'format': FORMAT, 'windows': [{'index': '19', 'x': 12, 'y': 8, 'w': 6, 'h': 9}]})
        self.assertEqual(len(manifest['writes']), 1)
        rom = Rom(apply(self.data, manifest))
        addr = records(rom)[0x19]
        self.assertEqual(bytes(rom.d[lorom(addr):lorom(addr) + 8]), bytes([0x0C, 0x88, 0xC6, 0xA9, 0, 1, 0xFE, 0xFF]))

    def test_party_height_window(self):
        manifest = patch(self.rom, {'format': FORMAT, 'windows': [{'index': '05', 'x': 4, 'y': 6, 'w': 10, 'h': 5}]})
        rom = Rom(apply(self.data, manifest))
        addr = records(rom)[5]
        self.assertEqual(bytes(rom.d[lorom(addr):lorom(addr) + 4]), bytes([0x44, 0x86, 0xCA, 0xA5]))
        with self.assertRaises(ValueError):
            edits(self.rom, {'format': FORMAT, 'windows': [{'index': '05', 'h': 6}]})
        # 원래 Y 20 에서 내려가지 않으면 X·너비를 바꾸거나 올려도 받는다(원본 1B 와 같은 꼴).
        for row in ({'x': 4, 'w': 12}, {'y': 18}, {'y': 2}):
            with self.subTest(row=row):
                self.assertEqual(len(edits(self.rom, {'format': FORMAT, 'windows': [{'index': '05', **row}]})), 1)
        # 내려가면 엔진이 다시 센 최악 높이로 본다(bit5 꺼짐 15, 켜짐 11).
        for y in (21, 27):
            with self.subTest(y=y), self.assertRaises(ValueError):
                edits(self.rom, {'format': FORMAT, 'windows': [{'index': '05', 'y': y}]})
        party = Rom(self.with_byte(self.first + 5 * 8, 0x62))
        self.assertEqual(len(edits(party, {'format': FORMAT, 'windows': [{'index': '05', 'y': 21}]})), 1)
        with self.assertRaises(ValueError):
            edits(party, {'format': FORMAT, 'windows': [{'index': '05', 'y': 22}]})
        with self.assertRaises(ValueError):
            edits(self.rom, {'format': FORMAT, 'windows': [{'index': '05', 'x': 20, 'w': 13}]})

    def test_low_height_window_moves(self):
        rom = Rom(self.with_byte(self.first + 8 * 8 + 3, 0xA1))
        self.assertEqual(len(edits(rom, {'format': FORMAT, 'windows': [{'index': '08', 'x': 4}]})), 1)
        for row in ({'index': '08', 'h': 0}, {'index': '08', 'w': 1}):
            with self.subTest(row=row), self.assertRaises(ValueError):
                edits(rom, {'format': FORMAT, 'windows': [row]})

    def test_shared_record(self):
        table = records(self.rom)
        self.assertEqual(table[6], table[7])
        self.assertEqual(len(edits(self.rom, {'format': FORMAT, 'windows': [{'index': '06', 'x': 2}]})), 1)
        for index in ('06', '07'):
            with self.subTest(index=index), self.assertRaises(ValueError):
                edits(self.rom, {'format': FORMAT, 'windows': [{'index': index, 'x': 3}]})

    def test_rejects(self):
        cases = [{'format': 'x', 'windows': []}, {'format': FORMAT}, {'format': FORMAT, 'windows': [], 'x': 1},
                 {'format': FORMAT, 'windows': [{'index': 25, 'x': 1}]},
                 {'format': FORMAT, 'windows': [{'index': '30', 'x': 1}]},
                 {'format': FORMAT, 'windows': [{'index': '32', 'x': 1}]},
                 {'format': FORMAT, 'windows': [{'index': ' 1', 'x': 1}]},
                 {'format': FORMAT, 'windows': [{'index': '+1', 'x': 1}]},
                 {'format': FORMAT, 'windows': [{'index': '1', 'x': 1}]},
                 {'format': FORMAT, 'windows': [{'index': 'zz', 'x': 1}]},
                 {'format': FORMAT, 'windows': [{'index': '03', 'x': 1}]},
                 {'format': FORMAT, 'windows': [{'index': '25', 'y': 15}]},
                 {'format': FORMAT, 'windows': [{'index': '19', 'x': 32}]},
                 {'format': FORMAT, 'windows': [{'index': '19', 'h': 16}]},
                 {'format': FORMAT, 'windows': [{'index': '19', 'x': 30}]},
                 {'format': FORMAT, 'windows': [{'index': '19', 'y': 30}]},
                 {'format': FORMAT, 'windows': [{'index': '19', 'w': 1}]},
                 {'format': FORMAT, 'windows': [{'index': '19', 'z': 1}]},
                 {'format': FORMAT, 'windows': [{'index': '19', 'x': 3}, {'index': '19', 'x': 4}]}]
        for doc in cases:
            with self.subTest(doc=doc), self.assertRaises(ValueError):
                edits(self.rom, doc)
        self.assertEqual(edits(self.rom, {'format': FORMAT, 'windows': [{'index': '25', 'y': 21}]}), [])

    def test_message_window_x(self):
        manifest = patch(self.rom, {'format': FORMAT, 'windows': [{'index': '25', 'x': 4}]})
        writes = {w['at']: w['hex'] for w in manifest['writes']}
        table = records(self.rom)
        self.assertEqual(writes[f'04:{table[0x18] & 0xFFFF:04X}'], '04 95 1c 07')
        self.assertEqual(writes[f'04:{table[0x25] & 0xFFFF:04X}'], '44 15 1c 07')
        # 원본 7E:5546·5586·06B8·06F8·3 이 두 칸 오른쪽으로.
        self.assertEqual({k: v for k, v in writes.items() if not k.startswith('04:') or k == '04:BCF9'},
                         {'24:A5ED': '4a 55', '24:883C': '8a 55', '24:8850': '8a 55', '24:A51F': 'bc 06',
                          '24:A529': 'fc 06', '04:BCF9': '05'})
        rom = Rom(apply(self.data, manifest))
        self.assertEqual(edits(rom, {'format': FORMAT, 'windows': [{'index': '18', 'x': 4}]}), [])
        self.assertEqual(len(edits(rom, {'format': FORMAT, 'windows': [{'index': '18', 'x': 2}]})), 8)
        self.assertEqual(len(edits(self.rom, {'format': FORMAT, 'windows': [{'index': '18', 'x': 0},
                                                                            {'index': '25', 'x': 0}]})), 8)

    def test_message_window_rejects(self):
        rows = [[{'index': '25', 'y': 14}], [{'index': '18', 'h': 8}], [{'index': '25', 'y': 20, 'h': 8}],
                [{'index': '25', 'x': 1, 'w': 30}], [{'index': '25', 'w': 26}], [{'index': '25', 'x': 5}],
                [{'index': '18', 'x': 0}, {'index': '25', 'x': 4}]]
        for windows in rows:
            with self.subTest(windows=windows), self.assertRaises(ValueError):
                edits(self.rom, {'format': FORMAT, 'windows': windows})
        broken = Rom(self.with_byte(0x24A5EC, 0x8F))
        with self.assertRaises(ValueError):
            edits(broken, {'format': FORMAT, 'windows': [{'index': '25', 'x': 4}]})
        moved = Rom(self.with_byte(self.first + 0x18 * 8, 0x04))
        with self.assertRaises(ValueError):
            edits(moved, {'format': FORMAT, 'windows': [{'index': '25', 'x': 3}]})


if __name__ == '__main__':
    unittest.main()
