"""환경 맵 빌드(CHR·블록 묶기, 맵 문서, 쓰기 목록)를 롬 없이 합성 FC 맵으로 검사한다."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import dq4environmentrom as env
from dq4environmentart import create_assets

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'dq5' / 'tools'))
from dq5build import parse_at  # noqa: E402
from dq5map import GROUP_TABLE, lorom  # noqa: E402

FLOOR, WALL, WATER, FOUNTAIN, DOOR, COUNTER, CHEST = range(7)
PROPS = {FLOOR: 0x00, WALL: 0x80, WATER: 0x80, FOUNTAIN: 0x80, DOOR: 0x94, COUNTER: 0xA7, CHEST: 0x84}
GROUP_NAME = next(iter(env.GROUPS))
TARGET_NAME = next(iter(env.TARGETS))


class Source:
    """dq4block.Map 대신 쓰는 FC 맵: 칸 값 행렬과 블록 속성만 든다."""

    def __init__(self, rows, t=0x0A):
        self.h, self.w = len(rows), len(rows[0])
        self.buf = [v for row in rows for v in row]
        self.blocks = {'prop': dict(PROPS)}
        self.t, self.prg, self.outside = t, b'', 0x1F

    def cell(self, x, y):
        return self.buf[y * self.w + x]


def draw(doc):
    """맵 문서 명령을 FC 칸마다 그린 블록 차례로 푼다."""
    drawn, block = {}, None
    for command in doc['commands']:
        if command[0] == 'block':
            block = command[1]
        elif command[0] == 'put':
            drawn.setdefault((command[1] // 2, command[2] // 2), []).append(block)
        elif command[0] == 'fill':
            for x in range(command[1], command[3] + 1, 2):
                drawn.setdefault((x // 2, command[2] // 2), []).append(block)
    return drawn


def cells(entries):
    """속성 패스 항목을 DQ5 칸 -> 값으로 푼다."""
    out = {}
    for x, y, n, value, kind in entries:
        self_kind = 'one' if n == 1 else 'short' if n <= 17 else 'long'
        assert kind == self_kind and 1 <= n <= 257, (x, y, n, kind)
        for k in range(n):
            assert (x + k, y) not in out
            out[x + k, y] = value
    return out


class MapDocumentTests(unittest.TestCase):
    ROWS = [[WALL, WALL, WALL, WALL],
            [FLOOR, DOOR, COUNTER, FLOOR],
            [FLOOR, FLOOR, CHEST, FLOOR]]
    LOCAL = {b: 10 + b for b in PROPS}

    def document(self, name=GROUP_NAME, rows=None):
        source = Source(rows or self.ROWS)
        return source, env.map_document(name, source, dict(self.LOCAL), env.MAPS[name])

    def test_every_cell_is_drawn_once_with_floor_under_doors_and_chests(self):
        source, doc = self.document()
        self.assertEqual((doc['width'], doc['height']), (8, 6))
        drawn = draw(doc)
        self.assertEqual(set(drawn), {(x, y) for y in range(3) for x in range(4)})
        # 문 칸은 가장 가까운 걸을 수 있는 칸(아래 먼저)의 바닥
        self.assertEqual(drawn[1, 1], [self.LOCAL[FLOOR]])
        # 상자는 바닥을 먼저 깔고 상자를 맨 나중에 올린다
        self.assertEqual(drawn[2, 2], [self.LOCAL[FLOOR], self.LOCAL[CHEST]])
        chest_at = doc['commands'].index(['block', self.LOCAL[CHEST]])
        self.assertEqual(max(i for i, c in enumerate(doc['commands']) if c[0] == 'block'), chest_at)
        for (x, y), blocks in drawn.items():
            if (x, y) != (2, 2):
                self.assertEqual(len(blocks), 1)
        self.assertEqual(doc['commands'][-1], ['end'])

    def test_walls_counters_and_front_passes(self):
        _, doc = self.document()
        walls = cells(doc['passes'][0]['entries'])
        # 막힌 FC 칸(벽·상자)만 벽, 문과 계산대는 막힌 속성이어도 벽으로 두지 않는다
        self.assertEqual(set(walls), {(x, y) for y in (0, 1) for x in range(8)} | {(x, y) for y in (4, 5) for x in (4, 5)})
        self.assertEqual(set(walls.values()), {env.WALL})
        second = cells(doc['passes'][1]['entries'])
        for cx in (4, 5):
            for cy in (2, 3):
                self.assertTrue(second[cx, cy] & env.COUNTER_PASS)
        # 위가 벽인 문은 문 칸만 인물을 앞에 그린다(옆문에 선 주인공이 위 벽에 가려지지 않게). 맨 아래 줄 상자는 그리지 않는다
        self.assertEqual({c for c, v in second.items() if v & env.FRONT_PASS}, {(x, y) for y in (2, 3) for x in (2, 3)})
        self.assertFalse(doc['passes'][2]['entries'])

    def test_front_cells_around_open_doors_and_below_chests(self):
        rows = [[FLOOR] * 4, [FLOOR, DOOR, FLOOR, FLOOR], [FLOOR, CHEST, FLOOR, FLOOR], [FLOOR] * 4]
        _, doc = self.document(GROUP_NAME, rows)
        front = {c for c, v in cells(doc['passes'][1]['entries']).items() if v & env.FRONT_PASS}
        door = {(x, y) for y in (0, 1) for x in range(1, 5)} | {(x, y) for y in (2, 3) for x in (2, 3)}
        chest = {(x, y) for y in (6, 7) for x in range(1, 4)}
        self.assertEqual(front, door | chest)

    def test_target_maps_get_no_chest_or_front_handling(self):
        _, doc = self.document(TARGET_NAME)
        self.assertEqual(draw(doc)[2, 2], [self.LOCAL[CHEST]])

    def test_long_wall_runs_split_at_257(self):
        _, doc = self.document(TARGET_NAME, [[WALL] * 129, [FLOOR] * 129])
        entries = [e for e in doc['passes'][0]['entries'] if e[1] == 0]
        self.assertEqual([(e[0], e[2], e[4]) for e in entries], [(0, 257, 'long'), (257, 1, 'one')])
        self.assertEqual(len(cells(doc['passes'][0]['entries'])), 258 * 2)

    def test_too_many_cells_for_the_position_bits(self):
        with self.assertRaisesRegex(ValueError, '14 position bits'):
            self.document(TARGET_NAME, [[FLOOR] * 65] * 65)

    def test_chest_without_floor_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'no floor'):
            self.document(GROUP_NAME, [[WALL, WALL, WALL], [WALL, CHEST, WALL], [WALL, WALL, WALL]])


def tile_image(values):
    """16x16 그림: 사분면마다 values 의 색인 하나."""
    img = Image.new('P', (16, 16))
    for i, v in enumerate(values):
        for y in range(8):
            for x in range(8):
                img.putpixel((i % 2 * 8 + x, i // 2 * 8 + y), v)
    return img


class GraphicsTests(unittest.TestCase):
    def setUp(self):
        self.assets = {env.WATER_FRAMES[0]: tile_image([1, 2, 3, 4]), env.FOUNTAIN_FRAMES[0]: tile_image([5, 6, 7, 8])}

    def run_graphics(self, maps):
        def fake(prg, assets, names):
            for name, (source, prepared) in maps.items():
                yield 0, 0, name, source, None, {b: (img, None) for b, img in prepared.items()}, 'palette'
        with patch.object(env, 'prepare_maps', fake):
            return env.build_graphics(b'', self.assets)

    def test_water_and_fountain_take_the_first_chr_and_art_is_shared(self):
        floor = tile_image([0x23, 0x23, 0x25, 0x23])
        maps = {TARGET_NAME: (Source([[FLOOR, WATER]]), {WATER: self.assets['water0'], FLOOR: floor}),
                GROUP_NAME: (Source([[FLOOR, CHEST]]), {FLOOR: floor, CHEST: floor})}
        chr_data, banks, words, heads, local, palette = self.run_graphics(maps)
        self.assertEqual(palette, 'palette')
        self.assertEqual(words[0], (0, 1, 2, 3))
        self.assertEqual(len(chr_data), 10)                      # 물 4 + 분수 4 + 바닥 2(같은 그림은 한 번)
        self.assertEqual(words[1], (8, 8, 9, 8))
        self.assertEqual(banks[8:], [2, 2])
        # 같은 그림이라도 머리(상자)가 다르면 다른 블록, 같은 그림·머리면 맵끼리 나눈다
        self.assertEqual(local[TARGET_NAME][1], {WATER: 0, FLOOR: 1})
        self.assertEqual(local[GROUP_NAME][1][FLOOR], 1)
        self.assertEqual(heads[local[GROUP_NAME][1][CHEST]], env.CHEST_HEAD)
        self.assertEqual(len(words), 3)
        self.assertEqual(env._planar(bytes([1] * 64)), bytes([0xFF, 0] * 8 + [0] * 16))

    def test_mixed_banks_and_too_many_chr_are_rejected(self):
        mixed = tile_image([0x11, 0, 0, 0])
        mixed.putpixel((1, 1), 0x21)
        with self.assertRaisesRegex(ValueError, 'mixed palette banks'):
            self.run_graphics({TARGET_NAME: (Source([[FLOOR]]), {FLOOR: mixed})})
        def unique(n):
            # 사분면마다 화소 비트로 번호를 새겨 모두 다른 CHR 이 되게 한다
            img = Image.new('P', (16, 16))
            for q in range(4):
                for j in range(64):
                    img.putpixel((q % 2 * 8 + j % 8, q // 2 * 8 + j // 8), 1 + ((n * 4 + q) >> j & 1))
            return img
        many = {b: unique(b) for b in range(257)}
        with self.assertRaisesRegex(ValueError, 'do not fit one bank'):
            self.run_graphics({TARGET_NAME: (Source([[FLOOR]]), many)})


MAPS_PER_GROUP = 20


def dq5_rom():
    """맵 포인터 그룹 표(54그룹, 그룹마다 맵 MAPS_PER_GROUP 개)와 빈 고층 표, 뱅크 01 문 표 자리를 채운 합성 DQ5 롬."""
    data = bytearray(0x180000)
    low = GROUP_TABLE & 0xFFFF
    starts = [low - 3 * MAPS_PER_GROUP * 54 + 3 * MAPS_PER_GROUP * g for g in range(54)]
    data[lorom(GROUP_TABLE):lorom(GROUP_TABLE) + 108] = b''.join(v.to_bytes(2, 'little') for v in starts)
    data[lorom(0x1FCEB6):lorom(0x1FCEB6) + 10] = (0xCEB6).to_bytes(2, 'little') * 5
    for i in range(lorom(GROUP_TABLE) - 3 * MAPS_PER_GROUP * 54, lorom(GROUP_TABLE), 3):
        data[i:i + 3] = bytes([i & 0xFF, i >> 8 & 0xFF, 0x2C])
    door = env._off(0x010000 | env.DOOR_TABLES[0])
    end = env._off(0x010000 | env.DOOR_TABLES[1])
    data[door:end] = bytes(i * 7 & 0xFF for i in range(end - door))
    return bytes(data)


class BuildTests(unittest.TestCase):
    """build 전체: 모든 대상 맵을 작은 합성 맵으로 바꿔 쓰기 목록의 자리·겹침·포인터를 본다."""

    @classmethod
    def setUpClass(cls):
        cls.root = Path(tempfile.mkdtemp())
        cls.assets = create_assets()
        rows = [[WALL, WALL, WALL], [WATER, DOOR, FLOOR], [FLOOR, FLOOR, FOUNTAIN]]
        plain = [[WALL, WALL], [FLOOR, FLOOR]]
        art = {WATER: 'water0', FLOOR: 'stone_floor', WALL: 'stone_wall', DOOR: 'door_closed', FOUNTAIN: 'fountain'}
        cls.maps = {}
        for i, name in enumerate(env.MAPS):
            grid = rows if i == 3 else [[WATER, FLOOR], [WALL, FLOOR]] if i == 0 else plain
            used = sorted({v for row in grid for v in row}, key=lambda b: b != WATER)
            cls.maps[name] = (Source(grid), {b: cls.assets[art[b]] for b in used})
        cls.dq5 = cls.root / 'dq5.sfc'
        cls.dq5.write_bytes(dq5_rom())
        (cls.root / 'dq4.nes').write_bytes(b'')
        cls.report = cls.build(cls.maps, cls.root / 'out')
        cls.patch = json.loads((cls.root / 'out' / 'dq4-environment.dq5patch.json').read_text())

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root)

    @classmethod
    def build(cls, maps, out):
        def fake(prg, assets, names):
            for name, (source, prepared) in maps.items():
                yield 0, 0, name, source, None, {b: (img, None) for b, img in prepared.items()}, None
        art = {WATER: (env.WATER_FRAMES[0], None), FOUNTAIN: (env.FOUNTAIN_FRAMES[0], None)}
        with patch.object(env.ines, 'prg', return_value=b''), patch.object(env, 'create_assets', return_value=cls.assets), \
                patch.object(env, 'prepare_maps', fake), patch.object(env, 'sheet_art', return_value=art):
            return env.build(cls.dq5, cls.root / 'dq4.nes', out)

    def spans(self):
        out = []
        for w in self.patch['writes']:
            raw = (self.root / 'out' / w['file']).read_bytes() if 'file' in w else bytes.fromhex(w['hex'])
            out.append((parse_at(w['at'])[0], raw, w['note']))
        return out

    def test_writes_do_not_overlap(self):
        spans = sorted((at, at + len(raw), note) for at, raw, note in self.spans() if raw)
        for (a0, a1, n0), (b0, b1, n1) in zip(spans, spans[1:]):
            self.assertLessEqual(a1, b0, f'{n0} overlaps {n1}')

    def test_fountain_is_moved_to_block_one_after_water(self):
        self.assertEqual(self.report['water_chr'], [0, 1, 2, 3])
        blocks = (self.root / 'out' / 'blocks.bin').read_bytes()
        pointers = next(bytes.fromhex(w['hex']) for w in self.patch['writes'] if '블록 포인터' in w['note'])
        defs = [int.from_bytes(pointers[i:i + 2], 'little') - env.BLOCKS_AT for i in range(0, len(pointers), 2)]
        self.assertEqual(len(defs), self.report['blocks'])
        self.assertEqual(defs, [11 * i for i in range(len(defs))])
        words = [[int.from_bytes(blocks[d + 3 + 2 * q:d + 5 + 2 * q], 'little') for q in range(4)] for d in defs]
        self.assertEqual(words[0], [0, 1, 2, 3])
        self.assertEqual(words[1], [4, 5, 6, 7])
        self.assertTrue(all(w < self.report['chr'] for row in words for w in row))
        doc = json.loads((self.root / 'out' / f'{list(env.MAPS)[3]}.dq5map.json').read_text())
        self.assertIn(['block', 1], doc['commands'])

    def test_map_records_stay_below_bank_40_and_pointers_follow(self):
        records = {w['file']: parse_at(w['at'])[0] for w in self.patch['writes'] if w.get('file', '').endswith('.bin')
                   and w['file'] not in ('chr.bin', 'blocks.bin')}
        self.assertEqual(len(records), len(env.TARGETS))
        lib = env._off(env.LIB_AT)
        for name, at in records.items():
            size = len((self.root / 'out' / name).read_bytes())
            self.assertLess(at // 0x8000, 0x40)
            self.assertEqual(at // 0x8000, (at + size - 1) // 0x8000, name)
            self.assertFalse(at < lib <= at + size, name)
        pointers = [w for w in self.patch['writes'] if '맵 포인터' in w['note']]
        self.assertEqual(len(pointers), len(env.TARGETS))
        for w in pointers:
            bank, low = bytes.fromhex(w['hex'])[2], int.from_bytes(bytes.fromhex(w['hex'])[:2], 'little')
            self.assertIn(env._off(bank << 16 | low), records.values())
            at = parse_at(w['at'])[0]
            self.assertEqual(bytes.fromhex(w['orig']), dq5_rom()[at:at + 3])

    def test_hook_stub_and_nibbles(self):
        stub = next(w for w in self.patch['writes'] if w['note'] == '엔진 훅 중계 코드')
        at = parse_at(stub['at'])[0]
        self.assertGreaterEqual(at, env._off(env.HOOK_AT))
        self.assertLessEqual(at + len(bytes.fromhex(stub['hex'])), env._off(env.HOOK_END))
        nibbles = bytes.fromhex(next(w['hex'] for w in self.patch['writes'] if w['note'] == 'CHR 팔레트 니블'))
        self.assertEqual(len(nibbles), (self.report['chr'] + 1) // 2)
        door = next(w for w in self.patch['writes'] if '문 루틴' in w['note'])
        self.assertEqual(bytes.fromhex(door['hex']),
                         dq5_rom()[env._off(0x010000 | env.DOOR_TABLES[0]):env._off(0x010000 | env.DOOR_TABLES[1])])

    def test_fountain_without_water_is_rejected(self):
        maps = dict(self.maps)
        name = list(env.MAPS)[5]
        maps[name] = (Source([[FLOOR, FOUNTAIN]]), {FLOOR: self.assets['stone_floor'], FOUNTAIN: self.assets['fountain']})
        with self.assertRaisesRegex(ValueError, 'fountain without water'):
            self.build(maps, self.root / 'bad')


if __name__ == '__main__':
    unittest.main()
