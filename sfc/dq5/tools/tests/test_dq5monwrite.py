"""전투 몬스터 그림 쓰기: 타일 압축, 새 배치, 원래 배치 다시 쓰기, 24비트 머리 코드, 입력 검사."""
import random
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch as mock

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dq5mongfx as M  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402
from dq5monwrite import (  # noqa: E402
    FIND, FIND_END, FORMAT, decode_raw, encode_picture, encode_tile, find_code, keep_layout, plan, tile_bytes,
)


def fake_rom(raw):
    """그림 00 의 머리를 25:8C99 에 둔 롬."""
    data = bytearray(0x180000)
    data[lorom(0x258C99):lorom(0x258C99) + len(raw)] = raw
    data[lorom(0x258C45):lorom(0x258C45) + 2] = (0x8C99).to_bytes(2, 'little')
    from dq5monwrite import FIND_ORIGINAL
    data[lorom(FIND):lorom(FIND) + len(FIND_ORIGINAL)] = FIND_ORIGINAL
    return Rom(data)


class TileTests(unittest.TestCase):
    def test_encode_tile_round_trip(self):
        rng = random.Random(1)
        samples = [bytes(32), bytes([0xFF] * 32), bytes(rng.randrange(256) for _ in range(32)),
                   bytes([0, 0x3C] * 8 + [0] * 16), bytes([0x18] * 16 + [0x81] * 16)]
        for t in samples:
            raw = encode_tile(t)
            stream = M.Stream(Rom(bytearray(lorom(0x308000)) + raw + bytes(64)), 0x308000)
            pos = [0]
            self.assertEqual(M.tile(stream, pos), t)
            self.assertEqual(pos[0], len(raw))
        self.assertEqual(encode_tile(bytes(32)), b'\x00')


class PictureTests(unittest.TestCase):
    def test_new_layout_round_trip(self):
        rng = random.Random(4)
        w, h = 5, 3
        grid = [[0] * (w * 8) for _ in range(h * 8)]
        for y in range(4, 24):
            for x in range(0, 24):
                grid[y][x] = rng.choice((1, 2, 2, 3))
        for y in range(8):           # 오른쪽 위 칸은 왼쪽 위 칸을 뒤집은 것 → 반전 복사
            for x in range(8):
                grid[y][32 + x] = grid[y + 8][7 - x]
        raw, pieces, tiles, bands = encode_picture(grid, w, h, [0, 0, 0, 1, 1, 0x42])
        self.assertEqual(decode_raw(raw, w, h), grid)
        self.assertEqual(len(bands), h)

    def test_keep_layout_keeps_mirrors(self):
        # 16x16 조각 하나와 그 반전 복사(1픽셀 왼쪽, 니블 A) 를 둔 그림.
        rng = random.Random(8)
        t = [bytes(rng.randrange(256) for _ in range(32)) for _ in range(4)]
        raw = bytes([0, 0, 0, 1, 1, 0x31]) + bytes([0xA0]) + bytes([0x2A]) + b''.join(encode_tile(x) for x in t) + bytes([0])
        rom = fake_rom(raw)
        d = M.decode(rom, 0)
        grid = [row[1:] for row in M.index_image(d)]
        self.assertEqual(keep_layout(rom, 0, grid), raw)
        changed = [[(v % 15) + 1 if v else 0 for v in row] for row in grid]
        again = keep_layout(rom, 0, changed)
        self.assertEqual(decode_raw(again, 4, 2), changed)
        self.assertEqual(again[:8], raw[:8])
        broken = [list(row) for row in grid]
        broken[0][16] = 0 if broken[0][16] else 5     # 반전 복사 쪽만 바꾸면 원래 배치로는 안 됨
        self.assertIsNone(keep_layout(rom, 0, broken))


class CodeTests(unittest.TestCase):
    def test_find_code_branch_and_table(self):
        code = find_code(0x3B8000)
        self.assertLessEqual(FIND + len(code), FIND_END)
        self.assertEqual(code[12:16], bytes([0xBF, 0x00, 0x80, 0x3B]))
        self.assertEqual(code[20:24], bytes([0xBF, 0x02, 0x80, 0x3B]))
        self.assertEqual(code[-2], 0x80)
        self.assertEqual(FIND + len(code) + (code[-1] - 256 if code[-1] & 0x80 else code[-1]), FIND_END)


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        rng = random.Random(2)
        t = [bytes(rng.randrange(256) for _ in range(32)) for _ in range(4)]
        raw = bytes([0, 0, 0, 1, 1, 0x11]) + bytes([0x80]) + bytes([0x20]) + b''.join(encode_tile(x) for x in t)
        self.rom = fake_rom(raw)
        records = lorom(M.RECORDS)
        self.rom.d[records:records + 6] = bytes([0x00, 0xE8, 0x00, 0xE9, 0x00, 0xE9])   # 몬스터 1·2 는 레코드를 함께 씀
        self.rom.d[lorom(0x258C47):lorom(0x258C47) + 2] = (0x8C99).to_bytes(2, 'little')  # 그림 01 도 같은 머리
        self.grid = [row[1:] for row in M.index_image(M.decode(self.rom, 0))]
        mons = {0: (0, [1] * 15), 1: (0, [2] * 15), 2: (1, [2] * 15)}
        self.mocks = [mock('dq5monwrite.M.monster', side_effect=lambda rom, m: mons[m]),
                      mock('dq5monwrite.M.COUNT', 3)]
        for m in self.mocks:
            m.start()

    def tearDown(self):
        for m in self.mocks:
            m.stop()

    def save(self, name, grid, mode='P'):
        image = Image.new(mode, (len(grid[0]), len(grid)))
        if mode == 'P':
            image.putpalette([c for i in range(16) for c in (i * 16,) * 3])
        image.putdata([c for row in grid for c in row])
        image.save(self.dir / name)

    def run_plan(self, **doc):
        return plan(self.rom, {'format': FORMAT, **doc}, self.dir)

    def test_valid(self):
        self.save('same.png', self.grid)
        pictures, monsters = self.run_plan(pictures=[{'picture': '00', 'image': 'same.png'}],
                                           monsters=[{'monster': '01', 'colors': [3] * 15}])
        self.assertEqual(sorted(pictures), [0, 1])       # 같은 머리인 그림 01 도 함께
        self.assertEqual(monsters, {1: (0, [3] * 15), 2: (0, [3] * 15)})   # 레코드를 함께 쓰는 몬스터 2 도 함께

    def test_more_pieces_need_group_check(self):
        # 가로 4·세로 2 칸에 왼쪽 16x16 조각 하나(조각 1·타일 4)인 그림. 원래 배치 밖의 칸 셋을 그리면 8x8 조각 셋
        # (조각 3·타일 3)이 되어 조각이 늘어난다.
        rng = random.Random(3)
        tiles = [bytes(rng.randrange(256) for _ in range(32)) for _ in range(4)]
        raw = bytes([0, 0, 0, 1, 1, 0x31, 0x80, 0x20]) + b''.join(encode_tile(x) for x in tiles)
        self.rom.d[lorom(0x258C99):lorom(0x258C99) + len(raw)] = raw
        grid = [[0] * 32 for _ in range(16)]
        for x, y, c in ((0, 0, 1), (16, 0, 2), (24, 8, 3)):
            for dy in range(8):
                grid[y + dy][x:x + 8] = [c] * 8
        self.save('three.png', grid)
        doc = {'pictures': [{'picture': '00', 'image': 'three.png'}]}
        with mock('dq5monlimits.losses', return_value=[]) as seen:
            pictures, _ = self.run_plan(**doc)
        self.assertEqual(pictures[0][2:], (3, 3))
        self.assertEqual(seen.call_args.args[1], {0: (3, [2, 1]), 1: (3, [2, 1])})   # 같은 머리인 그림 01 도
        hit = [(((0, 8, 0),), [8], [6], '구역 05 칸 1', '덜 놓임')]
        with mock('dq5monlimits.losses', return_value=hit), self.assertRaisesRegex(ValueError, '구역 05 칸 1'):
            self.run_plan(**doc)
        # 이 롬에는 무리 조합이 없어, 한도를 정할 수 없는 그림으로 거부한다.
        with self.assertRaisesRegex(ValueError, '한도를 정할 수 없음'):
            self.run_plan(**doc)

    def test_rejects(self):
        self.save('same.png', self.grid)
        self.save('wide.png', [[1] * 24 for _ in range(16)])
        self.save('rgb.png', [[(0, 0, 0)] * 16 for _ in range(16)], 'RGB')
        self.save('other.png', [[(v % 15) + 1 if v else 0 for v in row] for row in self.grid])
        for doc in ({'pictures': [{'picture': '02', 'image': 'same.png'}]},
                    {'pictures': [{'picture': '00', 'image': 'wide.png'}]},
                    {'pictures': [{'picture': '00', 'image': 'rgb.png'}]},
                    {'pictures': [{'picture': '00', 'image': 'same.png'}, {'picture': '00', 'image': 'same.png'}]},
                    {'pictures': [{'picture': '00', 'image': 'same.png', 'x': 1}]},
                    {'monsters': [{'monster': '03'}]},
                    {'monsters': [{'monster': '00', 'colors': [1] * 16}]},
                    {'monsters': [{'monster': '00', 'colors': [0x8000]}]},
                    {'monsters': [{'monster': '00', 'colors': [True]}]},
                    {'monsters': [{'monster': '00', 'picture': '02'}]},
                    {'monsters': [{'monster': '00', 'colors': [1]}]},
                    {'monsters': [{'monster': '01', 'colors': [3] * 15}, {'monster': '02', 'colors': [4] * 15}]},
                    {'pictures': [{'picture': '00', 'image': 'same.png'}, {'picture': '01', 'image': 'other.png'}]},
                    {'other': []}):
            with self.subTest(doc=doc), self.assertRaises(ValueError):
                self.run_plan(**doc)


if __name__ == '__main__':
    unittest.main()
