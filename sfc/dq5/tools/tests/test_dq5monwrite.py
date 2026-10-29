"""전투 몬스터 그림 쓰기: 타일 압축, 새 배치, 원래 배치 다시 쓰기, 24비트 머리 코드, 입력 검사."""
import contextlib
import io
import json
import random
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch as mock

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dq5mongfx as M  # noqa: E402
import dq5monwrite as W  # noqa: E402
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
    for addr, code in ((W.RECORD_READ, W.READ_ORIGINAL), (W.RECORD_BANK, W.BANK_ORIGINAL),
                       (W.E4_READ, W.READ_ORIGINAL), (W.E4_BANK, W.BANK_ORIGINAL)):
        data[lorom(addr):lorom(addr) + len(code)] = code
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
        # (조각, 줄마다 타일, 16x16 자리). 8x8 셋은 자리 하나를 나눠 쓴다. 같은 머리인 그림 01 도.
        self.assertEqual(seen.call_args.args[1], {0: (3, [2, 1], 1), 1: (3, [2, 1], 1)})
        hit = [(((0, 8, 0),), [8], [6], '구역 05 칸 1', '덜 놓임')]
        with mock('dq5monlimits.losses', return_value=hit), self.assertRaisesRegex(ValueError, '구역 05 칸 1'):
            self.run_plan(**doc)
        # 이 롬에는 무리 조합이 없어, 한도를 정할 수 없는 그림으로 거부한다(구역 표는 원래 자리로 봄).
        with mock('dq5monlimits.area_base', return_value=0x2396F3), self.assertRaisesRegex(ValueError, '한도를 정할 수 없음'):
            self.run_plan(**doc)
        # 구역 표를 읽는 명령이 없는 롬이면 구역 표 자리를 알 수 없어 거부한다.
        with self.assertRaisesRegex(ValueError, '표를 읽는 명령'):
            self.run_plan(**doc)

    def test_tile_limit(self):
        # 가로 12·세로 8 칸을 모두 다른 무늬로 칠하면 16x16 조각 24개 = 타일 96개로 NMI 한 번의 91개를 넘는다.
        raw = bytes([0, 0, 0, 1, 1, 0xB7, 0x80] + [0] * 11 + [0x00]) + b'\x00'
        self.rom.d[lorom(0x258C99):lorom(0x258C99) + len(raw)] = raw
        rng = random.Random(9)
        self.save('big.png', [[rng.randrange(1, 3) for _ in range(96)] for _ in range(64)])
        with mock('dq5monlimits.losses', return_value=[]), self.assertRaisesRegex(ValueError, '타일 96개'):
            self.run_plan(pictures=[{'picture': '00', 'image': 'big.png'}])
        self.save('less.png', [[rng.randrange(1, 3) if y < 56 else 0 for _ in range(96)] for y in range(64)])
        with mock('dq5monlimits.losses', return_value=[]):
            pictures, _ = self.run_plan(pictures=[{'picture': '00', 'image': 'less.png'}])
        self.assertEqual(pictures[0][3], 84)          # 맨 아래 칸 줄을 비우면 타일 84개라 받는다

    def test_tile_limit_keeps_original_layout(self):
        # 12x8 칸에 16x16 조각 24개. 마지막은 첫 조각의 반전 복사라 타일 92개(그림 6C 처럼 91 을 넘는 원본).
        rng = random.Random(10)
        cells = [(x, y) for y in range(0, 8, 2) for x in range(0, 12, 2)]
        bitmap = bytearray(12)
        for x, y in cells:
            bitmap[(y * 12 + x) // 8] |= 0x80 >> ((y * 12 + x) % 8)
        tiles = b''.join(encode_tile(tile_bytes([[rng.randrange(1, 3) for _ in range(8)] for _ in range(8)]))
                         for _ in range(92))
        raw = bytes([0, 0, 0, 1, 1, 0xB7]) + bytes(bitmap) + bytes([0x22] * 11 + [0x26]) + tiles + bytes([0])
        self.rom.d[lorom(0x258C99):lorom(0x258C99) + len(raw)] = raw
        grid = [row[1:] for row in M.index_image(M.decode(self.rom, 0))]
        self.save('swap.png', [[{1: 2, 2: 1}.get(v, v) for v in row] for row in grid])
        broken = [list(row) for row in grid]
        broken[48][80] = 2 if broken[48][80] == 1 else 1       # 반전 복사 쪽만 바꾸면 새 배치(타일 96개)
        self.save('broken.png', broken)
        with mock('dq5monlimits.losses', return_value=[]):
            pictures, _ = self.run_plan(pictures=[{'picture': '00', 'image': 'swap.png'}])
            self.assertEqual(pictures[0][3], 92)
            with self.assertRaisesRegex(ValueError, '타일 96개'):
                self.run_plan(pictures=[{'picture': '00', 'image': 'broken.png'}])

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


class RecordTests(unittest.TestCase):
    """색이 원래 레코드보다 많으면 레코드 표·레코드를 --records-at 으로 옮기고, 읽는 네 곳을 바꾼다."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        # 2x2 칸에 16x16 조각 하나. 왼쪽 위 타일만 색 1·2 로 그리고 나머지 셋은 비움.
        rng = random.Random(5)
        first = tile_bytes([[rng.randrange(1, 3) for _ in range(8)] for _ in range(8)])
        raw = bytes([0, 0, 0, 1, 1, 0x11, 0x80, 0x20]) + encode_tile(first) + bytes(3)
        data = bytearray(0x200000)
        data[:0x180000] = fake_rom(raw).d
        # 몬스터 0 은 2색, 몬스터 1·2 는 3색 레코드 하나를 함께 쓴다. 나머지 칸은 원본의 EC~FF 처럼 몬스터 0 의 레코드.
        table = lorom(M.RECORDS)
        data[table:table + 512] = bytes([0x00, 0xE8, 0x06, 0xE8, 0x06, 0xE8]) + bytes([0x00, 0xE8]) * 253
        data[lorom(0x27E800):lorom(0x27E800) + 14] = bytes([0, 2, 1, 0, 2, 0, 0, 3, 3, 0, 4, 0, 5, 0])
        self.rom = Rom(data)
        self.grid = [row[1:] for row in M.index_image(M.decode(self.rom, 0))]
        self.mocks = [mock('dq5monwrite.M.COUNT', 3)]
        for m in self.mocks:
            m.start()

    def tearDown(self):
        for m in self.mocks:
            m.stop()

    def doc(self, colors):
        return {'format': FORMAT, 'monsters': [{'monster': '01', 'colors': colors}]}

    def applied(self, manifest):
        data = bytearray(self.rom.d)
        for w in manifest['writes']:
            at = lorom(W.parse(w['at']))
            data[at:at + len(w['hex']) // 3 + 1] = bytes.fromhex(w['hex'])
        return Rom(data)

    def test_in_place_when_fits(self):
        manifest = W.patch(self.rom, self.doc([7, 8, 9]), self.dir)
        self.assertEqual([w['at'] for w in manifest['writes']], ['27:E806'])
        self.assertFalse(W.records_moved(self.applied(manifest)))

    def test_moves_records(self):
        colors = list(range(100, 115))
        with self.assertRaisesRegex(ValueError, '--records-at 이 필요함'):
            W.patch(self.rom, self.doc(colors), self.dir)
        manifest = W.patch(self.rom, self.doc(colors), self.dir, records_at=0x3C8000)
        self.assertEqual({w['at'] for w in manifest['writes']}, {'3C:8000', '22:9003', '22:900B', '02:F498', '02:F48D'})
        after = self.applied(manifest)
        self.assertTrue(W.records_moved(after))
        self.assertEqual(after.u24(W.RECORD_READ + 1), 0x3C8000)
        self.assertEqual(after.u8(W.E4_BANK + 1), 0x3C)
        # 몬스터 1·2 는 새 자리에서도 레코드 하나를 함께 쓴다.
        self.assertEqual([M.monster(after, m) for m in range(3)], [(0, [1, 2]), (0, colors), (0, colors)])
        self.assertEqual(after.u16(0x3C8002), after.u16(0x3C8004))
        # 표는 원본처럼 256칸이고, 몬스터 칸 밖(여기서는 03~FF)은 새 00 레코드를 가리킨다. 레코드는 표 뒤 3C:8200 부터.
        self.assertEqual({after.u16(0x3C8000 + m * 2) for m in (0, 3, 0xEC, 0xFF)}, {0x8200})
        # dq5mongfx.monster 는 22:9003 을 따라 옮긴 레코드를 읽는다(다른 도구도 같은 함수를 씀).
        self.assertEqual(M.monster(after, 1), (0, colors))
        self.assertEqual(M.record_table(after), (0x3C8000, 0x3C))
        self.assertEqual(M.record_table(self.rom), (M.RECORDS, 0x27))
        with self.assertRaisesRegex(ValueError, '이미 옮긴'):
            W.plan(after, self.doc(colors), self.dir)

    def test_rejects_records_at(self):
        with self.assertRaisesRegex(ValueError, '색이 원래 레코드보다 많은 몬스터가 없음'):
            W.patch(self.rom, self.doc([7, 8, 9]), self.dir, records_at=0x3C8000)
        with self.assertRaisesRegex(ValueError, '22:9000~ 가 원래 롬의 코드·자료 자리와 겹침'):
            W.patch(self.rom, self.doc(list(range(15))), self.dir, records_at=0x229000)

    def test_e4_needs_ten_colors(self):
        with mock('dq5monwrite.M.COUNT', 0xEC):
            with self.assertRaisesRegex(ValueError, '몬스터 E4: 색 9개'):
                W.plan(self.rom, {'format': FORMAT, 'monsters': [{'monster': 'E4', 'colors': [1] * 9}]}, self.dir)
            W.plan(self.rom, {'format': FORMAT, 'monsters': [{'monster': 'E4', 'colors': [1] * 10}]}, self.dir)

    def test_rejects(self):
        with self.assertRaisesRegex(ValueError, '1~15개'):
            W.plan(self.rom, self.doc(list(range(16))), self.dir)
        with self.assertRaisesRegex(ValueError, '1~15개'):
            W.plan(self.rom, self.doc([]), self.dir)
        broken = Rom(bytearray(self.rom.d))
        broken.d[lorom(W.E4_BANK) + 1] = 0x28
        with self.assertRaisesRegex(ValueError, '02:F48D 가 원본 레코드 읽기 코드가 아님'):
            W.patch(broken, self.doc(list(range(15))), self.dir, records_at=0x3C8000)
        with self.assertRaisesRegex(ValueError, '뱅크를 넘음'):
            W.patch(self.rom, self.doc(list(range(15))), self.dir, records_at=0x3CFFF0)
        unknown = Rom(bytearray(self.rom.d))
        unknown.d[lorom(W.RECORD_READ)] = 0xEA
        with self.assertRaisesRegex(ValueError, '옮긴 레코드 읽기도 아님'):
            W.plan(unknown, self.doc([1]), self.dir)

    def test_rejects_overlap(self):
        # 첫 타일만 그려진 그림을 네 타일 모두 그린 그림으로 바꾸면 원래 자리보다 길어 --at 으로 옮긴다.
        rng = random.Random(6)
        noisy = [[rng.randrange(1, 3) for _ in range(16)] for _ in range(16)]
        image = Image.new('P', (16, 16))
        image.putpalette([c for i in range(16) for c in (i * 16,) * 3])
        image.putdata([c for row in noisy for c in row])
        image.save(self.dir / 'noisy.png')
        doc = {'format': FORMAT, 'pictures': [{'picture': '00', 'image': 'noisy.png'}],
               'monsters': [{'monster': '01', 'colors': list(range(15))}]}
        with mock('dq5monlimits.losses', return_value=[]):
            with self.assertRaisesRegex(ValueError, '옮긴 자료가 겹침'):
                W.patch(self.rom, doc, self.dir, at=0x3C8000, records_at=0x3C8100)
            manifest = W.patch(self.rom, doc, self.dir, at=0x3C8000, records_at=0x3D8000)
        after = self.applied(manifest)
        self.assertEqual(M.monster(after, 2), (0, list(range(15))))
        self.assertEqual(W.picture_grid(after, 0)[0], noisy)

    def test_cli(self):
        rom = self.dir / 'rom.sfc'
        rom.write_bytes(bytes(self.rom.d))
        (self.dir / 'mon.json').write_text(json.dumps(self.doc(list(range(15)))), encoding='utf-8')
        out = self.dir / 'out.json'
        run = lambda *extra: self.main(str(rom), 'patch', str(self.dir / 'mon.json'), '-o', str(out), *extra)  # noqa: E731
        code, err = run()
        self.assertEqual((code, '--records-at 이 필요함' in err), (1, True))
        self.assertEqual(run('--records-at', '3C:8000'), (0, ''))
        self.assertIn('22:9003', [w['at'] for w in json.loads(out.read_text(encoding='utf-8'))['writes']])
        self.assertEqual(run('--records-at', '3C:1234')[0], 1)

    def main(self, *argv):
        err = io.StringIO()
        with mock.object(sys, 'argv', ['x', *argv]), contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(err):
            return W.main(), err.getvalue()


if __name__ == '__main__':
    unittest.main()
