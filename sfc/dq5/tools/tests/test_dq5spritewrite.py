"""인물 스프라이트 쓰기: 타일·반전 합치기, 런 길이 압축과 뱅크 넘김, 그림 배치, 입력 검사."""
import io
import random
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch as mock

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dq5sprite as S  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402
from dq5spritewrite import (  # noqa: E402
    FORMAT, OBJ_TILES, PARTY_TILES, apply, cell_tiles, commands, decoded, deduplicate, grow_table, packed, patch, place, plan,
    map_reserve, tile_bytes, vram_report, vram_rows, vram_use,
)

ROM = Path(__file__).resolve().parents[4] / 'rom' / 'dq5.sfc'


def rom_with(pieces, size=0x200000):
    data = bytearray(size)
    for at, raw in pieces:
        data[lorom(at):lorom(at) + len(raw)] = raw
    return Rom(data)


def save(path, grid, mode='P'):
    image = Image.new(mode, (len(grid[0]), len(grid)))
    if mode == 'P':
        # 팔레트가 없으면 Pillow 가 저장할 때 색 번호를 줄여 버린다.
        image.putpalette([c for i in range(16) for c in (i * 16, i * 16, i * 16)])
    image.putdata([c for row in grid for c in row])
    image.save(path)


class TileTests(unittest.TestCase):
    def test_tile_bytes_inverts_pixels(self):
        rng = random.Random(5)
        rows = [[rng.randrange(16) for _ in range(8)] for _ in range(8)]
        self.assertEqual(S.pixels(tile_bytes(rows)), rows)

    def test_deduplicate_uses_flip(self):
        a = tile_bytes([[x for x in range(8)] for _ in range(8)])
        b = tile_bytes([[7 - x for x in range(8)] for _ in range(8)])
        c = tile_bytes([[1] * 8 for _ in range(8)])
        tiles, refs = deduplicate([a, b, a, c])
        self.assertEqual((tiles, refs), ([a, c], [0, 0x80, 0, 1]))


class PackTests(unittest.TestCase):
    def test_commands_round_trip(self):
        rng = random.Random(7)
        data = bytes(rng.choice((0, 0, 0, 1, 2, 0xFF)) for _ in range(900))
        raw = b''.join(commands(data))
        self.assertEqual(S.unpack(rom_with([(0x308000, raw)]), 0x308000)[0], data)
        self.assertNotIn(0x7F, [c[0] for c in commands(data)][:-1])

    def test_commands_at_length_limits(self):
        rng = random.Random(3)
        for n in list(range(0, 300)) + [600]:
            for data in (bytes(rng.randrange(256) for _ in range(n)), bytes([5]) * n,
                         bytes(rng.choice((1, 1, 1, 2)) for _ in range(n))):
                raw = b''.join(commands(data))
                self.assertEqual(S.unpack(rom_with([(0x308000, raw)]), 0x308000)[0], data, n)
                self.assertNotIn(0x7F, [c[0] for c in commands(data)])

    def test_place_never_uses_ffff(self):
        pieces, end = place([b'\x01ab', b'\x81c', b'\x80'], 0x30FFFD)
        self.assertEqual(pieces, [(0x30FFFD, b'\x7f'), (0x318000, b'\x01ab\x81c\x80')])
        self.assertEqual(end, 0x318006)
        pieces, end = place([b'\x01ab', b'\x80'], 0x30FFFB)
        self.assertEqual((pieces, end), ([(0x30FFFB, b'\x01ab\x80')], 0x30FFFF))
        for start in range(0x30FFF0, 0x310000):
            pieces, end = place([b'\x02abc', b'\x83d', b'\x80'], start)
            self.assertTrue(all(at & 0xFFFF >= 0x8000 for at, _ in pieces) and end & 0xFFFF >= 0x8000)
            self.assertTrue(all((at & 0xFFFF) + len(raw) <= 0x10000 and (at + len(raw) - 1) & 0xFFFF != 0xFFFF
                                or raw[-1] == 0x7F for at, raw in pieces))

    def test_place_crosses_bank_with_7f(self):
        rng = random.Random(9)
        tiles = [bytes(rng.randrange(256) for _ in range(32)) for _ in range(20)]
        start = 0x30FF00
        pieces, end = place(packed(tiles), start)
        self.assertGreater(len(pieces), 1)
        self.assertEqual(pieces[0][1][-1], 0x7F)
        self.assertEqual(pieces[1][0], 0x318000)
        self.assertEqual(S.split_tiles(rom_with(pieces), start), (tiles, end))
        with self.assertRaises(ValueError):
            place(packed(tiles), 0x3FFF00)


class BuildTests(unittest.TestCase):
    def test_builder_rejects_overlap_in_shared_free_space(self):
        # 새 세트 레코드를 두는 뱅크 1F 빈 자리를 다른 도구가 함께 쓰면 빌더가 겹침으로 막는다.
        from dq5build import PatchError, build
        original = bytes(0x180000)
        record = (0x1F * 0x8000 + 0x7E30, bytes(52), None, 'sprite record')
        other = (0x1F * 0x8000 + 0x7E40, bytes(4), None, 'other tool')
        with self.assertRaises(PatchError):
            build(original, [('sprite', 0, [record]), ('other', 0, [other])], 0)
        build(original, [('sprite', 0, [record])], 0)


class GrowTableTests(unittest.TestCase):
    """원래 표(1F:D63D, 세트 00·80 만)를 가진 가짜 롬에서 256칸 표로 옮기기."""

    def setUp(self):
        table = bytearray(b'\xff' * (S.TABLE_ENTRIES * 2))
        table[0:2], table[0x100:0x102] = b'\x87\xd7', b'\xbb\xd7'
        # 레코드 00·80 의 타일 자료는 3E:8000·3E:8010 의 빈 줄기 둘(80 80).
        pieces = [(S.SET_POINTERS, bytes(table)), (0x1FD787, b'\x00\x80\x3e' + bytes(range(3, 52))),
                  (0x1FD7BB, b'\x10\x80\x3e' + bytes(range(55, 104))), (0x3E8000, b'\x80\x80'), (0x3E8010, b'\x80\x80')]
        pieces += [(site, S.SET_POINTERS.to_bytes(3, 'little')) for site in S.SET_TABLE_SITES]
        pieces += [(site, b'\x1f') for site in S.SET_BANK_SITES]
        self.rom = rom_with(pieces)
        # 가짜 롬에는 인물 목록이 없다.
        lists = mock('dq5spritewrite.vram_lists', return_value=[])
        lists.start()
        self.addCleanup(lists.stop)

    def apply(self, writes):
        data = bytearray(self.rom.d)
        for w in writes:
            raw = bytes.fromhex(w['hex'])
            if 'orig' in w:
                self.assertEqual(bytes(data[lorom(int(w['at'].replace(':', ''), 16)):][:len(raw)]).hex(' '), w['orig'])
            o = lorom(int(w['at'].replace(':', ''), 16))
            data[o:o + len(raw)] = raw
        return Rom(data)

    def test_moves_all_records(self):
        new = bytes([0, 0x80, 0x3A]) + bytes(48) + b'\x05'
        rom = self.apply(grow_table(self.rom, {0xFF: new}, 0x3B8000, None, None))
        self.assertEqual(S.set_table(rom), (0x3B8000, 0x3B, 0x100))
        self.assertEqual([s for s in S.set_numbers(rom) if S.set_record(rom, s)], [0x00, 0x80, 0xFF])
        self.assertEqual(S.set_record(rom, 0x80)['cells'], list(range(55, 103)))
        self.assertEqual((S.set_record(rom, 0xFF)['data'], S.set_record(rom, 0xFF)['tiles']), (0x3A8000, 5))
        self.assertIsNone(S.set_record(rom, 0x70))
        self.assertIsNone(S.set_record(self.rom, 0xFF))

    def test_patch_end_to_end(self):
        # patch(sets_at=…) 로 새 8타일 세트 A5 를 더한 롬을 다시 patch 하고, 결과는 dq5build 로 빌드한다(apply).
        # 표를 옮긴 롬에 새 세트를 더할 때 --sets-at 이 없으면 죽은 옛 표(1F:D63D)에 쓰게 되므로 거부해야 한다.
        folder = Path(tempfile.mkdtemp())
        two = [[2] * 48 for _ in range(64)]
        save(folder / 'two.png', two)
        save(folder / 'five.png', [[5] * 48 for _ in range(64)])
        save(folder / 'flat.png', [[1] * 32 for _ in range(96)])
        # 모든 칸이 같은 잡음 타일 하나라 타일 수는 A5 와 같지만 압축 자료는 A5 의 원래 자리보다 크다.
        rng = random.Random(3)
        noise = [[rng.randrange(16) for _ in range(8)] for _ in range(8)]
        save(folder / 'noise.png', [[noise[y % 8][x % 8] for x in range(48)] for y in range(64)])
        doc = {'format': FORMAT, 'new_sets': [{'set': 'A5', 'image': 'two.png', 'palette': 3}],
               'gfx': [{'gfx': '01', 'set': 'A5'}]}
        with self.assertRaises(ValueError):
            patch(self.rom, doc, folder, at=0x3A8000)
        grown = apply(self.rom, patch(self.rom, doc, folder, at=0x3A8000, sets_at=0x3B8000))
        self.assertEqual(S.set_table(grown), (0x3B8000, 0x3B, 0x100))
        self.assertEqual([s for s in S.set_numbers(grown) if S.set_record(grown, s)], [0x00, 0x80, 0xA5])
        self.assertEqual(S.set_record(grown, 0x80)['cells'], S.set_record(self.rom, 0x80)['cells'])
        a5 = S.decode_set(grown, 0xA5)
        self.assertEqual((a5['palette'], a5['data'], S.gfx_set(grown, 1)), (3, 0x3A8000, 0xA5))
        tiles, refs = deduplicate(cell_tiles(two, 'overlap'))
        self.assertEqual(decoded(a5['cells'], a5['tile_data'], 'overlap'), decoded(refs, tiles, 'overlap'))

        more = {'format': FORMAT, 'new_sets': [{'set': '71', 'image': 'flat.png', 'palette': 1}],
                'gfx': [{'gfx': '02', 'set': '71'}]}
        with self.assertRaises(ValueError):
            patch(grown, more, folder, at=0x3A9000)
        # 다시 옮길 자리·옮길 타일 자료가 지금 쓰이는 표·레코드(3B:8000~)나 A5 의 타일 자료(3A:8000~)를 덮으면 거부한다.
        for at, sets_at in ((0x3A9000, 0x3A8000), (0x3A9000, 0x3B8000), (0x3B8100, 0x3C8000), (0x3A8000, 0x3C8000)):
            with self.subTest(at=hex(at), sets_at=hex(sets_at)), self.assertRaises(ValueError):
                patch(grown, more, folder, at=at, sets_at=sets_at)
        again = apply(grown, patch(grown, more, folder, at=0x3A9000, sets_at=0x3C8000))
        self.assertEqual(S.set_table(again)[:2], (0x3C8000, 0x3C))
        self.assertEqual([s for s in S.set_numbers(again) if S.set_record(again, s)], [0x00, 0x71, 0x80, 0xA5])
        self.assertEqual(S.set_record(again, 0xA5)['data'], 0x3A8000)

        # 이미 있는 세트는 --sets-at 없이 옮긴 레코드 자리(뱅크 3B)에서 고친다.
        writes = patch(grown, {'format': FORMAT, 'sets': [{'set': 'A5', 'image': 'five.png', 'palette': 2}]}, folder)['writes']
        record = S.set_record(grown, 0xA5)['record']
        self.assertIn(f'{record >> 16:02X}:{record & 0xFFFF:04X}', [w['at'] for w in writes])
        self.assertFalse([w for w in writes if w['at'].startswith('1F:')])
        edited = S.decode_set(apply(grown, {'writes': writes}), 0xA5)
        self.assertEqual((edited['palette'], edited['data']), (2, 0x3A8000))
        # 넘쳐서 --at 으로 옮기는 자료도 살아 있는 표(3B:8000~)에 놓으면 거부한다.
        noisy = {'format': FORMAT, 'sets': [{'set': 'A5', 'image': 'noise.png'}]}
        with self.assertRaises(ValueError):
            patch(grown, noisy, folder, at=0x3B8000)
        moved = S.decode_set(apply(grown, patch(grown, noisy, folder, at=0x3A9000)), 0xA5)
        self.assertEqual(moved['data'], 0x3A9000)

    def test_rejects_bank_overflow_and_overlap(self):
        with self.assertRaises(ValueError):
            grow_table(self.rom, {}, 0x3BFF00, None, None)
        with self.assertRaises(ValueError):
            grow_table(self.rom, {}, 0x3A8100, 0x3A8000, 0x3A8200)
        grow_table(self.rom, {}, 0x3A8200, 0x3A8000, 0x3A8200)


class LayoutTests(unittest.TestCase):
    def test_simple_and_overlap_images(self):
        rng = random.Random(11)
        for layout, (w, h) in (('simple', (32, 96)), ('overlap', (48, 64))):
            grid = [[rng.choice((0, 0, 3, 4, 9)) for _ in range(w)] for _ in range(h)]
            tiles, refs = deduplicate(cell_tiles(grid, layout))
            shapes = decoded(refs, tiles, layout)
            for row, d in enumerate(S.DIRS):
                for f in (0, 1):
                    if layout == 'simple':
                        want = [line[f * 16:f * 16 + 16] for line in grid[row * 24:row * 24 + 24]]
                    else:
                        body = [line[16 + f * 16:32 + f * 16] for line in grid[row * 16:row * 16 + 16]]
                        head = [line[0:16] for line in grid[row * 16:row * 16 + 16]]
                        want = [[0] * 16 for _ in range(24)]
                        for y in range(16):
                            want[y + 8] = list(body[y])
                        for y in range(16):
                            for x in range(16):
                                if head[y][x]:
                                    want[y][x] = head[y][x]
                    self.assertEqual(shapes[d, f], want, (layout, d, f))


class PlanTests(unittest.TestCase):
    """세트 00(6타일, 타일 3개)과 80(8타일, 타일 4개)만 있는 가짜 롬, 그림 00→00·01→80."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        recs = {0x00: {'set': 0, 'tiles': 3, 'palette': 1, 'layout': 'simple'},
                0x80: {'set': 0x80, 'tiles': 4, 'palette': 0, 'layout': 'overlap'}}
        self.mocks = [mock('dq5spritewrite.S.set_record', side_effect=lambda rom, s: recs.get(s)),
                      mock('dq5spritewrite.S.gfx_set', side_effect=lambda rom, g: 0x80 if g == 1 else 0),
                      mock('dq5spritewrite.S.set_numbers', side_effect=lambda rom: list(range(0xA3))),
                      mock('dq5spritewrite.S.GFX_COUNT', 2),
                      mock('dq5spritewrite.vram_lists', side_effect=lambda rom: self.lists)]
        self.lists = []
        for m in self.mocks:
            m.start()
        save(self.dir / 'flat.png', [[1] * 32 for _ in range(96)])
        save(self.dir / 'busy.png', [[(x // 8 + y // 8) % 16 for x in range(32)] for y in range(96)])
        save(self.dir / 'parts.png', [[2] * 48 for _ in range(64)])
        save(self.dir / 'rgb.png', [[(0, 0, 0)] * 32 for _ in range(96)], 'RGB')

    def tearDown(self):
        for m in self.mocks:
            m.stop()

    def run_plan(self, **doc):
        return plan(None, {'format': FORMAT, **doc}, self.dir)

    def test_valid_document(self):
        sets, mapping = self.run_plan(sets=[{'set': '80', 'image': 'parts.png'}],
                                      new_sets=[{'set': '70', 'image': 'flat.png', 'palette': 2}],
                                      gfx=[{'gfx': '00', 'set': '70'}])
        self.assertEqual(sorted(sets), [0x70, 0x80])
        self.assertEqual((sets[0x70][2], sets[0x80][2]), (2, 0))
        self.assertEqual(mapping, {0: 0x70})

    def test_grown_new_sets(self):
        # A5~FF 는 표를 늘릴 때(--sets-at)만 새 8타일 세트가 된다.
        doc = {'new_sets': [{'set': 'A5', 'image': 'parts.png', 'palette': 3}], 'gfx': [{'gfx': '01', 'set': 'A5'}]}
        with self.assertRaises(ValueError):
            self.run_plan(**doc)
        sets, mapping = plan(None, {'format': FORMAT, **doc}, self.dir, grown=True)
        self.assertEqual((sorted(sets), sets[0xA5][2], mapping), ([0xA5], 3, {1: 0xA5}))
        with self.assertRaises(ValueError):
            plan(None, {'format': FORMAT, 'new_sets': [{'set': 'A4', 'image': 'parts.png', 'palette': 0}],
                        'gfx': [{'gfx': '01', 'set': 'A4'}]}, self.dir, grown=True)

    def test_rejects(self):
        bad = [{'sets': [{'set': '00', 'image': 'parts.png'}]},
               {'sets': [{'set': '00', 'image': 'rgb.png'}]},
               {'sets': [{'set': '70', 'image': 'flat.png'}]},
               {'sets': [{'set': '00', 'image': 'flat.png', 'palette': 4}]},
               {'sets': [{'set': '00', 'image': 'flat.png', 'palette': True}]},
               {'sets': [{'set': '00', 'image': 'flat.png'}, {'set': '00', 'image': 'flat.png'}]},
               {'sets': [{'set': '0', 'image': 'flat.png'}]},
               {'sets': [{'set': '00', 'image': 'flat.png', 'name': 'x'}]},
               {'new_sets': [{'set': '70', 'image': 'flat.png'}], 'gfx': [{'gfx': '00', 'set': '70'}]},
               {'new_sets': [{'set': '00', 'image': 'flat.png', 'palette': 0}]},
               {'new_sets': [{'set': '70', 'image': 'flat.png', 'palette': 0}]},
               {'gfx': [{'gfx': '02', 'set': '00'}]},
               {'gfx': [{'gfx': '00', 'set': '71'}]},
               {'gfx': [{'gfx': '00', 'set': '00'}, {'gfx': '00', 'set': '80'}]},
               {'gfx': [{'gfx': '9A', 'set': '00'}]},
               {'other': []}]
        for doc in bad:
            with self.subTest(doc=doc), self.assertRaises(ValueError):
                self.run_plan(**doc)

    def test_growth_checks_obj_vram(self):
        # busy.png 는 세트 00(타일 3개)보다 타일이 많다. 그림 00 을 놓는 목록의 OBJ VRAM 이 512 를 넘을 때만 거부한다.
        self.lists = [('01/00 목록 05:8000', 0, False, {(0, False)})]
        grown = len(self.run_plan(sets=[{'set': '00', 'image': 'busy.png'}])[0][0][1])
        self.assertGreater(grown, 3)
        full = OBJ_TILES - PARTY_TILES - 3
        self.lists = [('01/00 목록 05:8000', full - grown + 3, False, {(0, False)})]
        self.run_plan(sets=[{'set': '00', 'image': 'busy.png'}])
        self.lists = [('01/00 목록 05:8000', full - grown + 4, True, {(0, False), (1, False)})]
        with self.assertRaises(ValueError):
            self.run_plan(sets=[{'set': '00', 'image': 'busy.png'}])
        # 누운 인물은 같은 세트라도 따로 올린다.
        self.lists = [('01/00 목록 05:8000', full - 2 * grown + 3, False, {(0, False), (0, True)})]
        self.run_plan(sets=[{'set': '00', 'image': 'busy.png'}])
        self.lists = [('01/00 목록 05:8000', full - 2 * grown + 4, False, {(0, False), (0, True)})]
        with self.assertRaises(ValueError):
            self.run_plan(sets=[{'set': '00', 'image': 'busy.png'}])
        # 그림 번호를 옮겨 그 목록에서 세트가 바뀌어도 같은 셈이다(그림 01 은 원래 세트 80, 타일 4개).
        self.lists = [('01/00 목록 05:8000', full - grown + 4, False, {(0, False), (1, False)})]
        with self.assertRaises(ValueError):
            self.run_plan(new_sets=[{'set': '70', 'image': 'busy.png', 'palette': 0}], gfx=[{'gfx': '01', 'set': '70'}])

    def test_unlisted_gfx_keeps_original_limit(self):
        # 목록에 없는 그림(장면·일행 슬롯·필드로만 올라감)은 원래 세트의 타일 수까지만 받는다.
        self.lists = [('01/00 목록 05:8000', 0, False, {(1, False)})]
        with self.assertRaises(ValueError):
            self.run_plan(sets=[{'set': '00', 'image': 'busy.png'}])
        self.run_plan(sets=[{'set': '00', 'image': 'flat.png'}])
        with self.assertRaises(ValueError):
            self.run_plan(new_sets=[{'set': '70', 'image': 'busy.png', 'palette': 0}], gfx=[{'gfx': '00', 'set': '70'}])
        # 그림 01 은 목록에 있어 예산 안이면 늘려도 된다.
        self.run_plan(new_sets=[{'set': '70', 'image': 'busy.png', 'palette': 0}], gfx=[{'gfx': '01', 'set': '70'}])
        # 그림 9A 가 목록에 있으면 그것이 올리는 97·2F 도 목록에 있는 것으로 본다.
        with mock('dq5spritewrite.S.GFX_COUNT', 0x9B), \
                mock('dq5spritewrite.S.gfx_set', side_effect=lambda rom, g: 0x80 if g == 1 else 0):
            self.lists = [('01/00 목록 05:8000', 0, False, {(g, False) for g in range(0x9B) if g not in (0x97, 0x2F, 0x9A)})]
            with self.assertRaises(ValueError):
                self.run_plan(new_sets=[{'set': '70', 'image': 'busy.png', 'palette': 0}], gfx=[{'gfx': '97', 'set': '70'}])
            self.lists[0][3].add((0x9A, True))
            self.run_plan(new_sets=[{'set': '70', 'image': 'busy.png', 'palette': 0}], gfx=[{'gfx': '97', 'set': '70'}])

    def test_original_overflow_is_not_blamed(self):
        # 원래부터 512 를 넘는 목록은 늘리지 않는 한 거부하지 않는다.
        self.lists = [('01/00 목록 05:8000', OBJ_TILES, False, {(0, False)})]
        self.run_plan(sets=[{'set': '00', 'image': 'flat.png'}])
        with self.assertRaises(ValueError):
            self.run_plan(sets=[{'set': '00', 'image': 'busy.png'}])

    def test_report_without_lists(self):
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(vram_report(None), [])
        self.assertIn('목록 0줄', out.getvalue())


class VramUseTests(unittest.TestCase):
    def test_counts_each_set_once_and_wife_branch(self):
        sets = {0x00: 0x10, 0x01: 0x10, 0x02: 0x20, 0x97: 0x30, 0x2F: 0x31}
        tiles = {0x10: 30, 0x20: 7, 0x30: 26, 0x31: 35}
        lists = [('a', 0, False, {(0x00, False), (0x01, False), (0x02, False)}),
                 ('b', 5, True, {(0x00, False), (0x9A, False)}),
                 ('c', 0, False, {(0x00, False), (0x01, True), (0x00, True)}), ('d', 0, False, set())]
        self.assertEqual(vram_use(lists, sets.get, tiles.get),
                         [PARTY_TILES + 37, PARTY_TILES + 5 + 30 + 35, PARTY_TILES + 60, PARTY_TILES])

    def test_map_reserve_takes_first_match(self):
        objects = [{'bc': 0x53, 'bd': 0x82, 'reserve': 10}, {'bc': 0x53, 'bd': 0xFF, 'reserve': 20},
                   {'bc': 0x54, 'bd': 0x7F, 'reserve': 7}]
        self.assertEqual([map_reserve(objects, *m) for m in ((0x53, 0x02), (0x53, 0x05), (0x54, 0x09), (0x55, 0))],
                         [10, 20, 7, 0])


@unittest.skipUnless(ROM.exists(), '롬이 없음(rom/dq5.sfc)')
class RomVramTests(unittest.TestCase):
    def test_original_rom_lists(self):
        rom = Rom(ROM.read_bytes())
        rows = vram_rows(rom, {}, {g: S.gfx_set(rom, g) for g in range(S.GFX_COUNT)})
        self.assertEqual(len(rows), 818)
        self.assertEqual(max(after for *_, after in rows), 0x1FF)
        self.assertEqual(sum(after > OBJ_TILES for *_, after in rows), 0)
        self.assertTrue(all(before == after for _, before, after in rows))


if __name__ == '__main__':
    unittest.main()
