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
        self.assertEqual({g: v[:3] for g, v in seen.call_args.args[1].items()}, {0: (3, [2, 1], 1), 1: (3, [2, 1], 1)})
        self.assertEqual({(v[3]['w'], v[3]['h']) for v in seen.call_args.args[1].values()}, {(4, 2)})
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
        # 가로 15·세로 8 칸을 모두 다른 무늬로 칠하면 타일 120개로, 다음 NMI 한 번에 모두 보내지 못한다.
        raw = bytes([0, 0, 0, 1, 1, 0xB7, 0x80] + [0] * 11 + [0x00]) + b'\x00'
        self.rom.d[lorom(0x258C99):lorom(0x258C99) + len(raw)] = raw
        rng = random.Random(9)
        self.save('big.png', [[rng.randrange(1, 3) for _ in range(120)] for _ in range(64)])
        with mock('dq5monlimits.losses', return_value=[]), self.assertRaisesRegex(ValueError, '타일 120개'):
            self.run_plan(pictures=[{'picture': '00', 'image': 'big.png'}])
        self.save('less.png', [[rng.randrange(1, 3) if y < 48 else 0 for _ in range(120)] for y in range(64)])
        with mock('dq5monlimits.losses', return_value=[]):
            pictures, _ = self.run_plan(pictures=[{'picture': '00', 'image': 'less.png'}])
        self.assertEqual(pictures[0][3], 90)          # 아래 두 칸 줄을 비우면 타일 90개라 받는다

    def test_tile_limit_midbattle(self):
        # 12x8 칸 16x16 조각 24개 = 타일 96개. 전투 첫머리 그림이면 받고, モシャス 로 싸우는 도중에 풀릴 수 있는 그림이면
        # OAM DMA 몫을 더 남겨 거부한다.
        rng = random.Random(13)
        self.save('mid.png', [[rng.randrange(1, 3) for _ in range(96)] for _ in range(64)])
        doc = {'pictures': [{'picture': '00', 'image': 'mid.png'}]}
        with mock('dq5monlimits.losses', return_value=[]):
            pictures, _ = self.run_plan(**doc)
            self.assertEqual(pictures[0][3], 96)
            with mock('dq5monwrite.midbattle_pictures', return_value={0}), \
                    self.assertRaisesRegex(ValueError, '타일 96개.*개만 닿음.*OAM DMA'):
                self.run_plan(**doc)
            # 같은 머리를 쓰는 그림 01 이 싸우는 도중에 풀려도 같다.
            with mock('dq5monwrite.midbattle_pictures', return_value={1}), self.assertRaisesRegex(ValueError, 'OAM DMA'):
                self.run_plan(**doc)

    def test_midbattle_pictures(self):
        # 동료 종류가 있는 몬스터(モシャス 가 그림을 빌림)의 그림만. 부르기 대상(1E 등)은 잰 대로 넣지 않는다.
        # 바꾼 그림 번호를 따른다.
        with mock('dq5monwrite.M.COUNT', 0xEC), \
                mock('dq5monwrite.M.monster', side_effect=lambda rom, m: (m & 0x3F, [])), \
                mock('dq5monster.record', side_effect=lambda rom, m: [0] * 0x18 + [2 if m in (5, 9) else 0] + [0] * 0x30):
            got = W.midbattle_pictures(None, {9: (0x20, [])})
        self.assertEqual(got, {5, 0x20})

    def test_nmi_tiles(self):
        # 16x16 조각 26개(타일 104개). 자리 7 부터면 목록이 [14, 2]·[30, 100]·[144, 2] 셋이고, 셋째의 둘째 타일이
        # 0줄을 넘는다(그림 43 을 이렇게 늘린 전투에서 103개가 닿음). 자리 0 부터면 항목이 둘이라 모두 닿는다.
        d = {'pieces': [(0, 0, True, [b''] * 4, False)] * 26}
        self.assertEqual(M.transfer_runs(d, 7), [[14, 2], [30, 100], [144, 2]])
        self.assertEqual(M.nmi_tiles(d, 7), 103)
        self.assertEqual(M.transfer_runs(d, 0), [[0, 100], [112, 4]])
        self.assertEqual(M.nmi_tiles(d, 0), 104)
        # 8x8 조각은 자리를 잡자마자 다음 16x16 조각이 그 뒤 자리를 쓴다.
        mixed = {'pieces': [(0, 0, False, [b''], False), (0, 0, True, [b''] * 4, False), (0, 0, False, [b''], False)]}
        self.assertEqual(M.obj_tiles(mixed, 0), [0, 2, 3, 18, 19, 1])
        self.assertEqual(M.transfer_runs(mixed, 0), [[0, 4], [18, 2]])

    def test_tile_limit_keeps_original_layout(self):
        # 14x8 칸에 16x16 조각 28개. 마지막은 첫 조각의 반전 복사라 타일 108개(그림 6C 처럼 NMI 한도를 넘는 원본).
        rng = random.Random(10)
        cells = [(x, y) for y in range(0, 8, 2) for x in range(0, 14, 2)]
        bitmap = bytearray(14)
        for x, y in cells:
            bitmap[(y * 14 + x) // 8] |= 0x80 >> ((y * 14 + x) % 8)
        tiles = b''.join(encode_tile(tile_bytes([[rng.randrange(1, 3) for _ in range(8)] for _ in range(8)]))
                         for _ in range(108))
        raw = bytes([0, 0, 0, 1, 1, 0xD7]) + bytes(bitmap) + bytes([0x22] * 13 + [0x26]) + tiles + bytes([0])
        self.rom.d[lorom(0x258C99):lorom(0x258C99) + len(raw)] = raw
        grid = [row[1:] for row in M.index_image(M.decode(self.rom, 0))]
        self.save('swap.png', [[{1: 2, 2: 1}.get(v, v) for v in row] for row in grid])
        broken = [list(row) for row in grid]
        broken[48][100] = 2 if broken[48][100] == 1 else 1     # 반전 복사 쪽만 바꾸면 새 배치(타일 112개)
        self.save('broken.png', broken)
        with mock('dq5monlimits.losses', return_value=[]):
            pictures, _ = self.run_plan(pictures=[{'picture': '00', 'image': 'swap.png'}])
            self.assertEqual(pictures[0][3], 108)
            with self.assertRaisesRegex(ValueError, '타일 112개'):
                self.run_plan(pictures=[{'picture': '00', 'image': 'broken.png'}])

    def test_compositions_recorded_and_built(self):
        # 조합을 센 그림 패치는 그 조합의 요약을 남기고, 빌더는 빌드한 롬에서 다시 센 요약이 다르면 거부한다.
        rng = random.Random(12)
        self.save('tall.png', [[rng.randrange(1, 3) for _ in range(16)] for _ in range(24)])
        doc = {'format': FORMAT, 'pictures': [{'picture': '00', 'image': 'tall.png'}]}
        with mock('dq5monlimits.losses', return_value=[]), mock('dq5monlimits.fingerprint', return_value='aa'):
            manifest = W.patch(self.rom, doc, self.dir, at=0x3C8000)
        self.assertEqual(manifest['compositions'], {'areas': None, 'sha1': 'aa'})
        self.save('same.png', self.grid)
        same = W.patch(self.rom, {'format': FORMAT, 'pictures': [{'picture': '00', 'image': 'same.png'}]}, self.dir)
        self.assertNotIn('compositions', same)          # 조합을 세지 않은 패치(크기·조각 그대로)
        path = self.dir / 'monster.dq5patch.json'
        path.write_text(json.dumps(manifest), encoding='utf-8')
        import dq5build
        with mock('dq5monlimits.fingerprint', return_value='aa'):
            dq5build.check_compositions([path], bytes(self.rom.d))
        with mock('dq5monlimits.fingerprint', return_value='bb'), \
                self.assertRaisesRegex(dq5build.PatchError, '조우 패치를 먼저 넣은 롬'):
            dq5build.check_compositions([path], bytes(self.rom.d))
        # 구역 표를 옮긴 롬을 구역 수 없이 세면 compositions 가 거부하는데, 그것도 다른 것으로 본다.
        with mock('dq5monlimits.fingerprint', side_effect=ValueError('구역 표를 옮긴 롬')), \
                self.assertRaisesRegex(dq5build.PatchError, '무리·구역·부르기가 다름'):
            dq5build.check_compositions([path], bytes(self.rom.d))

    def test_resize_and_header(self):
        # 2x2 칸 그림을 3x4 칸으로 키우고 머리 +0~+4 를 바꾼다. 크기가 바뀌면 조합을 다시 센다(머리를 함께 넘김).
        rng = random.Random(11)
        grid = [[rng.randrange(1, 4) if 8 <= y < 24 and x < 16 else 0 for x in range(24)] for y in range(32)]
        self.save('tall.png', grid)
        header = {'float': True, 'raise': 1, 'shadow': 0, 'shadow_dx': -5, 'shadow_dy': 9, 'hit_x': 2, 'hit_y': 3}
        with mock('dq5monlimits.losses', return_value=[]) as seen:
            pictures, _ = self.run_plan(pictures=[{'picture': '00', 'image': 'tall.png', 'header': header}])
        raw = pictures[0][1]
        self.assertEqual(raw[:6], bytes([0xA0, 0xFB, 0x09, 2, 3, 0x23]))
        self.assertEqual(decode_raw(raw, 3, 4), grid)
        self.assertEqual(seen.call_args.args[1][0][3], M.parse_header(raw[:6]))
        # 머리만 바꾸면 원래 배치 그대로이고, 크기·띄움·들어올림이 같으면 조합을 세지 않는다.
        self.save('same.png', self.grid)
        with mock('dq5monlimits.losses', return_value=[]) as seen:
            pictures, _ = self.run_plan(pictures=[{'picture': '00', 'image': 'same.png', 'header': {'hit_x': 0}}])
        self.assertFalse(seen.called)
        self.assertEqual(pictures[0][1][3], 0)
        self.assertEqual(pictures[0][1][5:], keep_layout(self.rom, 0, self.grid)[5:])
        self.rom.d[lorom(W.SHADOWS) + 2:lorom(W.SHADOWS) + 4] = b'\xff\xff'   # 그림자 모양 1 은 자료 없음
        for bad in ({'hit_x': 2}, {'hit_y': -1}, {'raise': 4}, {'float': 1}, {'shadow': 1}, {'shadow_dx': 128},
                    {'size': 1}, []):
            with self.subTest(header=bad), self.assertRaises(ValueError):
                self.run_plan(pictures=[{'picture': '00', 'image': 'same.png', 'header': bad}])
        # 머리를 주지 않아도 바꾼 크기로 원래 머리를 검사한다: 원래 타격 기준점 x 1 은 가로 1칸 그림 밖
        self.rom.d[lorom(W.head_of(self.rom, 0)) + 3] = 1
        self.save('one.png', [[1] * 8 for _ in range(8)])
        with self.assertRaisesRegex(ValueError, 'hit_x'):
            self.run_plan(pictures=[{'picture': '00', 'image': 'one.png'}])
        for w, h in ((128, 16), (16, 136), (12, 16)):
            self.save('odd.png', [[0] * w for _ in range(h)])
            with self.subTest(size=(w, h)), self.assertRaisesRegex(ValueError, '팔레트 모드 PNG'):
                self.run_plan(pictures=[{'picture': '00', 'image': 'odd.png'}])

    def test_widest_picture(self):
        # 가로 19칸(152 픽셀)은 머리 +5 상위 니블 F 로 적는다
        self.assertEqual((W.size_byte(19, 2), W.size_byte(15, 16), W.size_byte(1, 1)), (0xF1, 0xEF, 0x00))
        rng = random.Random(12)
        grid = [[rng.randrange(1, 4) if x >= 136 else 0 for x in range(152)] for _ in range(16)]
        self.save('widest.png', grid)
        with mock('dq5monlimits.losses', return_value=[]):
            pictures, _ = self.run_plan(pictures=[{'picture': '00', 'image': 'widest.png'}])
        raw = pictures[0][1]
        self.assertEqual(raw[5], 0xF1)
        self.assertEqual((M.parse_header(raw[:6])['w'], M.parse_header(raw[:6])['h']), (19, 2))
        self.assertEqual(decode_raw(raw, 19, 2), grid)

    def test_swap_to_resized_picture(self):
        # 그림 01 을 따로 1x1 칸 그림으로 둔다. 몬스터 02 를 그림 00 으로 바꾸면 원래 그림 00(2x2)은 01 보다 크지만,
        # 같은 문서에서 그림 00 을 1x1 로 줄였으면 줄인 크기로 견주어 받는다.
        one = [[1] * 8 for _ in range(8)]
        raw = encode_picture(one, 1, 1, bytes(6))[0]
        self.rom.d[lorom(0x259000):lorom(0x259000) + len(raw)] = raw
        self.rom.d[lorom(0x258C47):lorom(0x258C47) + 2] = (0x9000).to_bytes(2, 'little')
        self.save('one.png', one)
        self.save('tall.png', [[1] * 16 for _ in range(24)])
        small = {'picture': '00', 'image': 'one.png', 'header': {'hit_x': 0, 'hit_y': 0}}
        swap = [{'monster': '02', 'picture': '00'}]
        with self.assertRaisesRegex(ValueError, '전투 배치 한도'):
            self.run_plan(monsters=swap)
        with mock('dq5monlimits.losses', return_value=[]):
            _, monsters = self.run_plan(pictures=[small], monsters=swap)
            self.assertEqual(monsters[2][0], 0)
            with self.assertRaisesRegex(ValueError, '전투 배치 한도'):
                self.run_plan(pictures=[{'picture': '00', 'image': 'tall.png'}], monsters=swap)

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
