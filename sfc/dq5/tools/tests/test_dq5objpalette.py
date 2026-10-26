"""OBJ 팔레트 색·맵 팔레트·세트 팔레트 배정 쓰기의 바이트와 입력 검사."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch as mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dq5sprite as S  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402
from dq5objpalette import FORMAT, affected, patch  # noqa: E402

RECORD = 0x1FD787


def fixture():
    data = bytearray(0x100000)
    for p in range(8):
        for i in range(16):
            at = lorom(S.OBJ_PALETTES + (p * 16 + i) * 2)
            data[at:at + 2] = (p * 0x100 + i).to_bytes(2, 'little')
    data[lorom(RECORD) + 2] = 0x45          # 자료 뱅크 05, 팔레트 1
    entry = 0x019A12
    data[lorom(entry):lorom(entry) + 5] = bytes([4, 6, 0xFF, 0, 0x0B])
    return Rom(data)


def records(rom, s):
    if s not in (0x84, 0x04):
        return None
    return {'set': s, 'record': RECORD, 'palette': rom.u8(RECORD + 2) >> 6, 'cells': [], 'data': 0, 'tiles': 1}


class PaletteTests(unittest.TestCase):
    def setUp(self):
        self.rom = fixture()
        self.mocks = [mock('dq5objpalette.S.set_record', side_effect=records),
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
        self.assertEqual([w['at'] for w in writes], ['04:97B8', '01:9A17', '1F:D789'])
        self.assertEqual(writes[0]['hex'][:11], '01 00 02 00')
        self.assertEqual((writes[2]['hex'], writes[2]['orig']), ('85', '45'))
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


if __name__ == '__main__':
    unittest.main()
