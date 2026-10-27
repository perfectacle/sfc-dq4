"""맵 OBJ·탈것 타일 쓰기: 1F:D28B 런 길이, 두 줄기/한 줄기, 타일 시트 입력, 옮길 때 고치는 자리."""
import random
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch as mock

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dq5sprite as S  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402
from dq5objtiles import FORMAT, VEHICLE_SITES, decode, encode, patch, read_tiles, rle, sheet_size  # noqa: E402


class RleTests(unittest.TestCase):
    def test_round_trip_at_limits(self):
        rng = random.Random(1)
        for n in list(range(0, 300)) + [700]:
            for data in (bytes(rng.randrange(256) for _ in range(n)), bytes([9]) * n):
                raw = rle(data)
                rom = Rom(bytearray(lorom(0x308000)) + raw + bytes(8))
                self.assertEqual(S.unpack(rom, 0x308000, False)[0], data, n)
        # 128바이트 그대로는 7F 한 명령이다(1F:D28B 는 7F 를 뱅크 넘김으로 보지 않음).
        self.assertEqual(rle(bytes(range(128)))[0], 0x7F)

    def test_two_streams_and_one_stream(self):
        rng = random.Random(2)
        tiles = [bytes(rng.choice((0, 0, 1, 255)) for _ in range(32)) for _ in range(5)]
        for split in (True, False):
            self.assertEqual(decode(encode(tiles, split), split), tiles)


class SheetTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def save(self, name, grid, mode='P'):
        image = Image.new(mode, (len(grid[0]), len(grid)))
        if mode == 'P':
            image.putpalette([c for i in range(16) for c in (i * 16,) * 3])
        image.putdata([c for row in grid for c in row])
        image.save(self.dir / name)

    def test_read_tiles(self):
        w, h = sheet_size(18)
        self.assertEqual((w, h), (128, 16))
        grid = [[(x // 8 + y // 8 * 16) % 16 if (x // 8 + y // 8 * 16) < 18 else 0 for x in range(w)] for y in range(h)]
        self.save('ok.png', grid)
        tiles = read_tiles(self.dir / 'ok.png', 18)
        self.assertEqual(len(tiles), 18)
        self.assertEqual(S.pixels(tiles[3])[0][0], 3)
        grid[15][127] = 1
        self.save('tail.png', grid)
        self.save('small.png', [[0] * 128 for _ in range(8)])
        self.save('rgb.png', [[(0, 0, 0)] * 128 for _ in range(16)], 'RGB')
        for name in ('tail.png', 'small.png', 'rgb.png'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                read_tiles(self.dir / name, 18)


class PatchTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        rng = random.Random(3)
        self.tiles = [bytes(rng.randrange(256) for _ in range(32)) for _ in range(2)]
        self.known = {
            'obj-00': {'data': 0x2B8000, 'end': 0x2B8004, 'split': True, 'tiles': [bytes(32)] * 2,
                       'entries': [0x1FD59A, 0x1FD5A0], 'users': ['01/00', '01/01'], 'reserve': [2, 2]},
            'veh-80-0': {'data': 0x16E7BD, 'end': 0x16E7C1, 'split': False, 'tiles': [bytes(32)] * 2,
                         'entries': [], 'users': ['탈것 80'], 'site': 0x16E7BD}}
        image = Image.new('P', sheet_size(2))
        image.putpalette([c for i in range(16) for c in (i * 16,) * 3])
        grid = [[0] * 128 for _ in range(8)]
        for i, t in enumerate(self.tiles):
            for y, row in enumerate(S.pixels(t)):
                grid[y][i * 8:i * 8 + 8] = row
        image.putdata([c for row in grid for c in row])
        image.save(self.dir / 'new.png')

    def run_patch(self, doc, at=None):
        with mock('dq5objtiles.blocks', return_value=self.known):
            return patch(Rom(bytearray(0x180000)), {'format': FORMAT, **doc}, self.dir, at)['writes']

    def test_moved_blocks_update_pointers(self):
        writes = self.run_patch({'blocks': [{'block': 'obj-00', 'image': 'new.png'},
                                            {'block': 'veh-80-0', 'image': 'new.png'}]}, at=0x3C8000)
        at = [w['at'] for w in writes]
        bank_at, addr_at = VEHICLE_SITES[0x16E7BD]
        self.assertEqual(at[:3], ['3C:8000', '1F:D59C', '1F:D5A2'])
        self.assertEqual(writes[1]['hex'], '00 80 3c')
        self.assertIn(f'{bank_at >> 16:02X}:{bank_at & 0xFFFF:04X}', at)
        self.assertIn(f'{addr_at >> 16:02X}:{addr_at & 0xFFFF:04X}', at)
        self.assertNotIn('orig', writes[0])
        with self.assertRaises(ValueError):
            self.run_patch({'blocks': [{'block': 'obj-00', 'image': 'new.png'}]})

    def test_in_place_and_bank_rollover(self):
        # 자리가 넉넉하면 제자리, 옮길 자리가 뱅크 끝에 걸리면 다음 뱅크 8000 으로.
        self.known['obj-00']['end'] = 0x2B9000
        writes = self.run_patch({'blocks': [{'block': 'obj-00', 'image': 'new.png'}]})
        self.assertEqual([w['at'] for w in writes], ['2B:8000'])
        self.assertIn('orig', writes[0])
        writes = self.run_patch({'blocks': [{'block': 'veh-80-0', 'image': 'new.png'}]}, at=0x3CFFF0)
        self.assertEqual(writes[0]['at'], '3D:8000')

    def test_rejects(self):
        for doc in ({'blocks': [{'block': 'obj-01', 'image': 'new.png'}]},
                    {'blocks': [{'block': 'obj-00', 'image': 'new.png'}, {'block': 'obj-00', 'image': 'new.png'}]},
                    {'blocks': [{'block': 'obj-00'}]},
                    {'blocks': [{'block': 'obj-00', 'image': 'new.png', 'x': 1}]},
                    {'other': []}):
            with self.subTest(doc=doc), self.assertRaises(ValueError):
                self.run_patch(doc, at=0x3C8000)


if __name__ == '__main__':
    unittest.main()
