"""팔레트 세트 표: 합성 롬에서 제자리 쓰기·옮겨 늘리기·찾기 루틴 꼴·입력 검사."""
import sys
import unittest
from pathlib import Path

from kr_patch.sfc.dis65816 import disasm

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dq5map import (GROUP_TABLE, GROUPS, HIGH_GROUPS, PALSET_LISTS, PALSET_TABLE, POINTER_SITE, TABLE_KINDS, Rom,  # noqa: E402
                    lorom, palette_set, palset_table)
from dq5palsetwrite import (FORMAT, LOADER, LOADER_ORIG, ORIGINAL_SIZE, dump, patch, stub_length,  # noqa: E402
                            writes_for)

# 그룹 01 은 맵 둘, 나머지는 하나. 그룹 50~54 는 맵 50 하나씩.
COUNTS = [2 if g == 1 else 1 for g in range(GROUPS)]


def put(data, addr, raw):
    data[lorom(addr):lorom(addr) + len(raw)] = raw


def table():
    """그룹마다 [BC][BC%5][FF], 그룹 02 는 맵 쌍 59개로 원래 크기 296바이트를 채운다(없는 맵 02/01~ 도 원래 항목)."""
    rows = []
    for bc in [*range(GROUPS), *range(0x50, 0x55)]:
        pairs = b''.join(bytes([bd, bd % 5]) for bd in range(59)) if bc == 2 else b''
        rows.append(bytes([bc, bc % 5]) + pairs + b'\xff')
    blob = b''.join(rows) + b'\xff'
    assert len(blob) == ORIGINAL_SIZE
    return blob


def fixture():
    data = bytearray(0x200000)
    start = (GROUP_TABLE & 0xFFFF) - sum(COUNTS) * 3
    starts, cursor = [], start
    for n in COUNTS:
        starts.append(cursor)
        cursor += n * 3
    put(data, GROUP_TABLE, b''.join(s.to_bytes(2, 'little') for s in starts))
    cursor = (HIGH_GROUPS & 0xFFFF) - 5 * 3
    put(data, HIGH_GROUPS, b''.join((cursor + g * 3).to_bytes(2, 'little') for g in range(5)))
    put(data, PALSET_TABLE, table())
    put(data, PALSET_LISTS, ((PALSET_LISTS & 0xFFFF) + 69 * 4).to_bytes(2, 'little'))
    put(data, LOADER, LOADER_ORIG)
    return Rom(data)


def apply(rom, writes):
    out = bytearray(rom.d)
    for addr, new, old, _ in writes:
        if old is not None:
            assert bytes(out[lorom(addr):lorom(addr) + len(new)]) == old
        put(out, addr, new)
    return Rom(out)


def document(*groups):
    return {'format': FORMAT, 'groups': list(groups)}


class PaletteSetTests(unittest.TestCase):
    def setUp(self):
        self.rom = fixture()

    def test_round_trip_keeps_table(self):
        doc = dump(self.rom)
        self.assertEqual(len(doc['groups']), GROUPS + 5)
        self.assertEqual(patch(self.rom, doc)['writes'], [])
        self.assertEqual(TABLE_KINDS['pointer']['original'], GROUP_TABLE)
        self.assertEqual(self.rom.d[lorom(POINTER_SITE) - 1], 0)

    def test_edit_in_place(self):
        # 01 에 쌍 하나를 더하고 02 에서 하나를 빼 크기를 맞춘다.
        short = [{'map': f'{bd:02X}', 'set': bd % 5} for bd in range(58)]
        writes = writes_for(self.rom, document({'group': '01', 'default': 7, 'maps': [{'map': '01', 'set': 68}]},
                                               {'group': '02', 'default': 2, 'maps': short}))
        self.assertEqual([w[0] for w in writes], [PALSET_TABLE])
        moved = apply(self.rom, writes)
        self.assertEqual((palette_set(moved, 1, 0), palette_set(moved, 1, 1)), (7, 68))
        self.assertEqual(palette_set(moved, 2, 3), 3)
        self.assertEqual(palset_table(moved), PALSET_TABLE)

    def test_new_group_grows_into_hooked_table(self):
        doc = document({'group': '36', 'default': 6, 'maps': [{'map': '00', 'set': 19}]})
        with self.assertRaises(ValueError):
            writes_for(self.rom, doc, new_maps=[(0x36, 0)])
        writes = writes_for(self.rom, doc, '3C:9000', [(0x36, 0)])
        self.assertEqual([w[0] for w in writes], [0x3C9000, LOADER])
        self.assertIsNone(writes[0][2])
        hook = writes[1][1]
        self.assertEqual(hook, bytes.fromhex('22 00 90 3c b0 01 60 4c 43 de'))
        moved = apply(self.rom, writes)
        self.assertEqual(palset_table(moved), 0x3C9000 + stub_length())
        self.assertEqual((palette_set(moved, 0x36, 0), palette_set(moved, 0x36, 1)), (19, 6))
        for bc, bd in ((0, 0), (1, 1), (2, 7), (0x35, 0), (0x54, 0x50)):
            self.assertEqual(palette_set(moved, bc, bd), palette_set(self.rom, bc, bd))
        code = disasm(bytes(moved.d), 0x3C9000, 4)
        self.assertIn('LDX #$0000', code)
        self.assertIn(f'LDA ${palset_table(moved):06X},X', code)

    def test_original_map_keys_are_kept(self):
        # 02/01 은 롬에 없는 맵이지만 원래 표에 있어 그대로 받는다. 02/40 은 원래에도 없어 거부한다.
        writes_for(self.rom, document({'group': '02', 'default': 1, 'maps': [{'map': '01', 'set': 2}]}))
        with self.assertRaises(ValueError):
            writes_for(self.rom, document({'group': '02', 'default': 1, 'maps': [{'map': '40', 'set': 2}]}))

    def test_rejects(self):
        new = [(0x36, 0)]
        cases = [
            (None, None, ()), ({}, None, ()), ({'format': 'x'}, None, ()), (document(None), None, ()),
            ({'format': FORMAT, 'groups': {}}, None, ()), ({'format': FORMAT, 'extra': 1}, None, ()),
            (document({'group': '36', 'default': 1}), '3C:9000', ()),
            (document({'group': '36', 'default': 1}), '3C:9000', [(0x37, 0)]),
            (document({'group': '01', 'default': 1}), None, [(0x55, 0x50)]),
            (document({'group': '01', 'default': 1}), None, [(0x52, 0x03)]),
            (document({'group': '1', 'default': 1}), None, ()), (document({'group': '0a', 'default': 1}), None, ()),
            (document({'group': '01', 'default': 69}), None, ()), (document({'group': '01', 'default': True}), None, ()),
            (document({'group': '01'}), None, ()), (document({'group': '01', 'default': 1, 'x': 1}), None, ()),
            (document({'group': '01', 'default': 1}, {'group': '01', 'default': 2}), None, ()),
            (document({'group': '01', 'default': 1, 'maps': {}}), None, ()),
            (document({'group': '01', 'default': 1, 'maps': [{'map': '02', 'set': 1}]}), None, ()),
            (document({'group': '01', 'default': 1, 'maps': [{'map': '00', 'set': 1}] * 2}), None, ()),
            (document({'group': '01', 'default': 1, 'maps': [{'map': '00', 'set': -1}]}), None, ()),
            (document({'group': '01', 'default': 1, 'maps': [{'map': '00'}]}), None, ()),
            (document({'group': '50', 'default': 1, 'maps': [{'map': '00', 'set': 1}]}), None, ()),
            (document({'group': '36', 'default': 1}), '7E:9000', new),
            (document({'group': '36', 'default': 1}), '3C:7000', new),
            (document({'group': '36', 'default': 1}), '3C:FF00', new),
            (document({'group': '36', 'default': 1}), '3C9000', new),
        ]
        for doc, at, maps in cases:
            with self.subTest(doc=doc, at=at, maps=maps), self.assertRaises(ValueError):
                writes_for(self.rom, doc, at, maps)

    def test_refuses_changed_or_moved_rom(self):
        hooked = apply(self.rom, writes_for(self.rom, document(), '3C:9000'))
        with self.assertRaises(ValueError):
            writes_for(hooked, document())
        self.assertEqual(dump(hooked), dump(self.rom))
        data = bytearray(hooked.d)
        put(data, 0x3C9000, b'\xea')
        with self.assertRaises(ValueError):
            palset_table(Rom(data))
        data = bytearray(self.rom.d)
        put(data, LOADER + 7, b'\xea')
        with self.assertRaises(ValueError):
            writes_for(Rom(data), document())
        data = bytearray(self.rom.d)
        put(data, PALSET_TABLE + ORIGINAL_SIZE - 1, b'\x00\xff')
        with self.assertRaises(ValueError):
            writes_for(Rom(data), document())


if __name__ == '__main__':
    unittest.main()
