"""필드 인물 스프라이트 디코더: 런 길이 압축, 타일 배치·반전·회전, 맵 OBJ 표, 덤프 비교, 그림 내보내기."""
import io
import json
import os
import random
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dq5sprite as S  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402
from dq5spritewrite import tile_bytes  # noqa: E402

ROM = Path(__file__).resolve().parents[4] / 'rom' / 'dq5.sfc'


def rom_with(pieces, size=0x200000):
    data = bytearray(size)
    for at, raw in pieces:
        data[lorom(at):lorom(at) + len(raw)] = raw
    return Rom(data)


def solid(c):
    return tile_bytes([[c] * 8 for _ in range(8)])


def column(c, x):
    return tile_bytes([[c if i == x else 0 for i in range(8)] for _ in range(8)])


class UnpackTests(unittest.TestCase):
    def test_literal_run_and_bank_skip(self):
        rom = rom_with([(0x30FFF8, b'\x02abc\x83z\x7f'), (0x318000, b'\x00y\x80')])
        out, end = S.unpack(rom, 0x30FFF8)
        self.assertEqual(bytes(out), b'abc' + b'z' * 4 + b'y')
        self.assertEqual(end, 0x318003)

    def test_without_bank_skip_7f_is_128_literal_bytes(self):
        body = bytes(range(128))
        rom = rom_with([(0x308000, b'\x7f' + body + b'\x80')])
        out, end = S.unpack(rom, 0x308000, bank_skip=False)
        self.assertEqual(bytes(out), body)
        self.assertEqual(end, 0x308000 + 1 + 128 + 1)

    def test_split_tiles_interleaves_low_and_high_streams(self):
        lo, hi = bytes(range(32)), bytes(range(100, 132))
        rom = rom_with([(0x308000, b'\x1f' + lo + b'\x80\x1f' + hi + b'\x80')])
        tiles, end = S.split_tiles(rom, 0x308000)
        self.assertEqual(len(tiles), 2)
        self.assertEqual(tiles[1][0::2], lo[16:])
        self.assertEqual(tiles[1][1::2], hi[16:])
        self.assertEqual(end, 0x308000 + 2 * 34)


class TileGeometryTests(unittest.TestCase):
    def test_pixels_reads_four_planes(self):
        rng = random.Random(11)
        rows = [[rng.randrange(16) for _ in range(8)] for _ in range(8)]
        self.assertEqual(S.pixels(tile_bytes(rows)), rows)

    def test_rotate_tile_turns_clockwise(self):
        rng = random.Random(2)
        rows = [[rng.randrange(16) for _ in range(8)] for _ in range(8)]
        t = tile_bytes(rows)
        r = S.pixels(S.rotate_tile(t))
        self.assertEqual(r, [[rows[7 - x][y] for x in range(8)] for y in range(8)])
        for _ in range(3):
            t = S.rotate_tile(t)
        self.assertEqual(S.pixels(S.rotate_tile(t)), rows)

    def test_simple_frame_places_six_cells_and_flips(self):
        tiles = [column(1, 0), solid(0)]
        cells = [1] * 48
        cells[S.SIMPLE_BASE['down']] = 0
        cells[S.SIMPLE_BASE['down'] + 1] = 0x80
        rec = {'layout': 'simple', 'cells': cells}
        img = S.frame(rec, tiles, 'down', 0)
        self.assertEqual((len(img), len(img[0])), (S.FRAME_H, S.FRAME_W))
        lit = {(x, y) for y, row in enumerate(img) for x, v in enumerate(row) if v}
        self.assertEqual(lit, {(0, y) for y in range(8)} | {(15, y) for y in range(8)})
        self.assertEqual(S.bbox(img), (0, 0, 15, 7))
        self.assertIsNone(S.bbox(S.frame(rec, tiles, 'up', 1)))

    def test_overlap_head_is_drawn_over_body(self):
        tiles = [solid(2), solid(3)]
        rec = {'layout': 'overlap', 'cells': [0] * 16 + [1] * 32}
        img = S.frame(rec, tiles, 'left', 1)
        self.assertEqual([row[0] for row in img], [2] * 16 + [3] * 8)
        rec['tile_data'] = tiles
        mixed = S.mixed_frame(rec, 'up', 'down', 0)
        self.assertEqual(mixed, img)

    def test_lying_cells_move_flips(self):
        rec = {'layout': 'simple', 'cells': [0x81] * 48}
        cells = S.lying_cells(rec)
        self.assertEqual(len(cells), 48)
        self.assertTrue(all(t == 1 and vf for t, _, vf in cells))
        self.assertEqual(sum(hf for _, hf, _ in cells), sum(1 for b in S.LYING_SIMPLE if b & 0x80))

    def test_lying_overlap_puts_head_left_only_when_facing_left(self):
        rec = {'layout': 'overlap', 'cells': [0] * 16 + [1] * 32}
        rec['lying_tiles'] = [solid(2), solid(3)]
        rec['lying_cells'] = S.lying_cells(rec)
        left, right = S.lying_frame(rec, 'left'), S.lying_frame(rec, 'right')
        self.assertEqual((len(left), len(left[0])), (S.LYING_H, S.LYING_W))
        self.assertEqual((left[0][0], left[0][23]), (2, 3))
        self.assertEqual((right[0][0], right[0][23]), (3, 2))

    def test_rgb_and_matrix(self):
        self.assertEqual(S.rgb(0x7FFF), (255, 255, 255))
        self.assertEqual(S.rgb(0x001F), (255, 0, 0))
        img = [[0] * 16 for _ in range(24)]
        img[0][1] = 0xA
        rec = {'frames': {(d, f): img for d in S.DIRS for f in (0, 1)}}
        m = S.matrix(rec)
        self.assertEqual(sorted(m), sorted(f'{d}{f}' for d in S.DIRS for f in (0, 1)))
        self.assertEqual(m['down0'][0], '.A' + '.' * 14)


class TableTests(unittest.TestCase):
    def test_wife_picture_follows_flag(self):
        rom = rom_with([(S.GFX_SETS + 0x2F, b'\x11'), (S.GFX_SETS + 0x97, b'\x22'), (S.GFX_SETS + 0x9A, b'\x33')])
        self.assertEqual(S.gfx_set(rom, 0x9A), 0x33)
        self.assertEqual(S.gfx_set(rom, 0x9A, 0x08), 0x11)
        self.assertEqual(S.gfx_set(rom, 0x9A, 0x00), 0x22)

    def set_rom(self, extra=()):
        record = bytes([0x00, 0x80, 0x30 | 2 << 6]) + bytes(range(48)) + bytes([6])
        return rom_with([(S.SET_TABLE_SITES[0], S.SET_POINTERS.to_bytes(3, 'little')),
                         (S.SET_BANK_SITES[0], b'\x1f'),
                         (S.SET_POINTERS, b'\x00\xf0' + b'\xff\xff'),
                         (0x1FF000, record), *extra])

    def test_set_record_fields(self):
        rom = self.set_rom()
        rec = S.set_record(rom, 0)
        self.assertEqual((rec['data'], rec['palette'], rec['tiles'], rec['layout']), (0x308000, 2, 6, 'simple'))
        self.assertEqual(rec['cells'], list(range(48)))
        self.assertIsNone(S.set_record(rom, 1))
        self.assertIsNone(S.set_record(rom, S.TABLE_ENTRIES))
        self.assertEqual(S.set_numbers(rom), list(range(S.SET_COUNT)))
        self.assertIsNone(S.set_palette_table(rom))
        self.assertEqual(S.set_obj_palette(rom, 0), 2)

    def test_grown_table_adds_sets(self):
        rom = rom_with([(S.SET_TABLE_SITES[0], (0x308000).to_bytes(3, 'little')), (S.SET_BANK_SITES[0], b'\x30')])
        self.assertEqual(S.set_table(rom), (0x308000, 0x30, 0x100))
        self.assertEqual(S.set_numbers(rom)[-1], 0xFF)
        self.assertEqual(len(S.set_numbers(rom)), S.SET_COUNT + len(S.GROWN_SETS))

    def test_set_palette_hook(self):
        routine = 0x308000
        jsl = b'\x22' + routine.to_bytes(3, 'little')
        table = 0x309000
        code = S.SET_PALETTE_ROUTINE + table.to_bytes(3, 'little')
        rom = self.set_rom([(S.SET_PALETTE_SITES[0], jsl), (S.SET_PALETTE_SITES[1], jsl), (routine, code),
                            (table, b'\x05\x09')])
        self.assertEqual(S.set_palette_table(rom), table)
        self.assertEqual(S.set_obj_palette(rom, 0), 5)
        rom.d[lorom(table)] = 0xFF
        self.assertEqual(S.set_obj_palette(rom, 0), 2)
        rom.d[lorom(table)] = 0x09
        with self.assertRaisesRegex(ValueError, '0~7·FF'):
            S.set_obj_palette(rom, 0)
        rom.d[lorom(S.SET_PALETTE_SITES[1])] = 0xEA
        with self.assertRaisesRegex(ValueError, '훅이'):
            S.set_palette_table(rom)

    def test_map_objects_packed_and_raw(self):
        raw = bytes(range(64))
        packed = b'\x0f' + bytes(16) + b'\x80\x0f' + bytes([0xFF] * 16) + b'\x80'
        table = (b'\x7e\x81' + (0x8000).to_bytes(2, 'little') + b'\x30\x01'
                 + b'\x05\x7f' + (0x9000).to_bytes(2, 'little') + b'\x30\x02' + b'\xff')
        rom = rom_with([(S.MAP_OBJECTS, table), (0x308000, packed), (0x309000, raw)])
        objs = S.map_objects(rom)
        self.assertEqual([m['where'] for m in objs], ['필드 세계 1', '05/**'])
        self.assertEqual([m['packed'] for m in objs], [True, False])
        self.assertEqual(objs[0]['tiles'], [bytes([0, 0xFF] * 16)])
        self.assertEqual(objs[1]['tiles'], [raw[:32], raw[32:]])
        self.assertEqual(objs[1]['end'], 0x309040)
        self.assertEqual([S.obj_stem(m) for m in objs], ['obj-field1', 'obj-05-xx'])
        self.assertEqual(S.obj_stem({'bc': 0x12, 'bd': 0x83}), 'obj-12-03')
        self.assertEqual(S.map_object_tiles_for(rom, 0xFE, 1), objs[0])
        self.assertEqual(S.map_object_tiles_for(rom, 0x05, 0x33), objs[1])
        self.assertIsNone(S.map_object_tiles_for(rom, 0x06, 0))

    def test_map_object_places(self):
        cells = bytes([1, 0x82, 3, 4])
        entry = bytes([0x07, 0x82, 0x10, 0x20, 0x80 | 0x40 | 2, 2, 0b0101_1111]) + (0xA000).to_bytes(2, 'little')
        rom = rom_with([(S.MAP_OBJECT_PLACES, entry + b'\xff'), (0x16A000, cells)])
        (p,) = S.map_object_places(rom)
        self.assertEqual((p['bc'], p['bd'], p['x'], p['y'], p['cols'], p['rows']), (7, 2, 0x110, 0x120, 2, 2))
        self.assertEqual((p['cond'], p['palette'], p['priority'], p['cells']), (3, 7, 2, list(cells)))

    def test_map_palettes_and_relocated_loader(self):
        e1 = bytes([0x07, 0xFF, 0xFF, 0x00, 0x0B]) + b''.join(i.to_bytes(2, 'little') for i in range(1, 16))
        e2 = bytes([0x07, 0x02, 0xFF, 0x00, 0x09]) + bytes(30)
        rom = rom_with([(S.MAP_PALETTES, e1 + e2 + b'\xff')])
        self.assertEqual(len(S.map_palettes(rom)), 2)
        self.assertEqual(S.map_obj_palette3(rom, 7, 5)['colors'], list(range(16)))
        self.assertIsNone(S.map_obj_palette3(rom, 8, 5))
        self.assertEqual(S.map_line_colors(rom, 7, 2, 9), [0] * 16)
        self.assertIsNone(S.map_line_colors(rom, 7, 3, 9))
        moved = rom_with([(S.MAP_PALETTE_LOADER, b'\x22' + (0x308000).to_bytes(3, 'little')),
                          (0x308000 + S.MAP_PALETTE_OPERAND, (0x9000).to_bytes(2, 'little')),
                          (0x309000, e2 + b'\xff')])
        self.assertEqual(S.map_palette_table(moved), 0x309000)
        self.assertEqual([e['line'] for e in S.map_palettes(moved)], [9])

    def test_oam_groups_hides_offscreen_and_large(self):
        oam = bytearray(544)
        for i in range(128):
            oam[i * 4 + 1] = 0xF0
        oam[0:4] = bytes([0xFE, 0x0F, 0x23, 0x31])
        oam[4:8] = bytes([0x10, 0x20, 0x00, 0x00])
        oam[512] = 0b0000_1001
        items = S.oam_groups(oam)
        self.assertEqual(items[0], (-2, 0x10, 0x123, 0x31))
        self.assertIsNone(items[1])
        self.assertIsNone(items[2])


def place(oam, i, x, y, t, a):
    oam[i * 4:i * 4 + 4] = bytes([x & 0xFF, (y - 1) & 0xFF, t & 0xFF, a | t >> 8])
    oam[512 + (i >> 2)] |= ((x >> 8) & 1) << ((i & 3) * 2)


@unittest.skipUnless(ROM.exists(), '롬이 없음(rom/dq5.sfc)')
class RomTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom = Rom(ROM.read_bytes())

    def test_decode_every_set(self):
        sets = [s for s in S.set_numbers(self.rom) if S.set_record(self.rom, s)]
        self.assertEqual((len(sets), sum(1 for s in sets if s & 0x80)), (147, 35))
        for s in (0x00, 0x82):
            rec = S.decode_set(self.rom, s)
            self.assertEqual(len(rec['tile_data']), rec['tiles'])
            self.assertEqual(len(rec['frames']), 8)
            self.assertTrue(all(len(img) == 24 and len(img[0]) == 16 for img in rec['frames'].values()))
            self.assertTrue(all(len(img) == 16 and len(img[0]) == 24 for img in rec['lying'].values()))
            self.assertTrue(S.bbox(rec['frames'][('down', 0)]))
        self.assertIsNone(S.decode_set(self.rom, 0x70))

    def test_tables(self):
        self.assertEqual(len(S.map_objects(self.rom)), 27)
        self.assertEqual(len(S.map_object_places(self.rom)), 74)
        self.assertEqual(len(S.map_palettes(self.rom)), 36)
        self.assertEqual(len(S.obj_palettes(self.rom)), 4)
        self.assertIsNone(S.set_palette_table(self.rom))

    def test_vehicle_frames(self):
        shape = {v['id']: [(fr['part']['cols'], fr['part']['rows'], fr['nframes'], len(fr['frames']))
                           for fr in S.vehicle_frames(self.rom, v)] for v in S.VEHICLES}
        self.assertEqual(shape, {0x80: [(3, 2, 2, 8), (3, 3, 2, 8), (3, 1, 2, 8)],
                                 0x81: [(4, 4, 1, 1), (4, 2, 1, 1)],
                                 0x82: [(4, 4, 3, 12), (2, 2, 3, 12)]})
        tiles = S.vehicle_tiles(self.rom, S.VEHICLES[2])
        self.assertEqual(len(tiles), 0x40 + 0x39)

    def test_sheets_scale_and_grid(self):
        rec = S.decode_set(self.rom, 0x82)
        pal = S.obj_palettes(self.rom)[rec['palette']]
        img = S.sheet(rec, pal, scale=2, grid=True)
        self.assertEqual(img.size, (64, 192))
        self.assertEqual(img.getpixel((0, 0)), (255, 0, 0, 200))
        self.assertEqual(S.sheet(rec, pal, lying=True, index=True).size, (24, 64))
        frs = S.vehicle_frames(self.rom, S.VEHICLES[0])
        pals = [list(p) for p in S.obj_palettes(self.rom)] + [[0] * 16] * 4
        one = S.vehicle_composite(frs, pals)
        self.assertEqual(S.vehicle_composite(frs, pals, scale=2, index=True).size, (one.width * 2, one.height * 2))
        part = S.vehicle_sheet(frs[0], pals)
        self.assertEqual(part.size, (24 * 2, 16 * 4))
        self.assertEqual(S.vehicle_sheet(frs[0], pals, 3, True).size, (24 * 6, 16 * 12))
        m = S.map_objects(self.rom)[2]
        self.assertEqual(S.tile_sheet(m['tiles'], pals[0]).size, (128, 32))
        self.assertEqual(S.tile_sheet(m['tiles'], pals[0], 2, True).size, (256, 64))
        mp = S.map_object_places(self.rom)[0]
        self.assertEqual(S.place_image(m['tiles'], mp, pals[0], 2).size, (mp['cols'] * 16, mp['rows'] * 16))

    def test_names(self):
        names = S.set_names(self.rom)
        self.assertGreaterEqual(len(names), 60)
        self.assertEqual(names[0x63][0], 'むすこ')
        self.assertEqual(names[0x82][0], 'パパスのむすこ')
        self.assertTrue(all(isinstance(why, str) and why for _, why in names.values()))
        users = S.npc_users(self.rom)
        self.assertTrue(all(g < S.GFX_COUNT and maps for g, maps in users.items()))

    def test_export_all_writes_index(self):
        with tempfile.TemporaryDirectory() as d:
            entries = S.export_all(bytes(self.rom.d), d)
            doc = json.loads(Path(d, 'index.json').read_text())
            files = set(os.listdir(d))
        sets = [e for e in entries if 'layout' in e]
        self.assertEqual(len(sets), 147)
        self.assertTrue(all(e['path'] in files for e in entries))
        self.assertTrue(all((e['w'], e['h']) == (32, 96) for e in sets))
        self.assertIn('82-パパスのむすこ.png', files)
        self.assertIn('82-パパスのむすこ-lying-index.png', files)
        kinds = {k: sum(1 for x in doc['sprites'] if k in x) for k in ('layout', 'vehicle', 'map_place', 'map_object')}
        self.assertEqual(kinds['layout'], 147)
        self.assertEqual(kinds['vehicle'], 3 + 7)
        self.assertEqual(kinds['map_object'], 27)
        self.assertEqual(sum(1 for x in doc['sprites'] if x.get('rotated')), 147)
        self.assertEqual(len(doc['obj_palettes']), 4)
        papas = next(x for x in doc['sprites'] if x.get('set') == 0x82 and not x['rotated'])
        self.assertEqual(len(papas['frames']), 8)
        self.assertEqual(papas['rom'][2], ':')

    def test_main_list_and_out(self):
        out = io.StringIO()
        with mock.patch.object(sys, 'argv', ['dq5sprite.py', str(ROM), '--list']), redirect_stdout(out):
            S.main()
        lines = out.getvalue().splitlines()
        self.assertEqual(len(lines), 147)
        self.assertTrue(lines[0].startswith('세트 00 simple'))
        out = io.StringIO()
        fake = [{'layout': 'simple'}, {'map_object': 0}, {'map_object': 0}, {'map_object': 1}]
        with mock.patch.object(sys, 'argv', ['dq5sprite.py', str(ROM), '--out', 'x', '--no-index', '--scale', '2']), \
                mock.patch.object(S, 'export_all', return_value=fake) as ex, redirect_stdout(out):
            S.main()
        self.assertEqual(ex.call_args.args[1:], ('x', 2, False, False))
        self.assertEqual(out.getvalue().strip(), '인물 세트 1개, 맵 OBJ 타일 2개 → x')


@unittest.skipUnless(ROM.exists(), '롬이 없음(rom/dq5.sfc)')
class CompareTests(unittest.TestCase):
    """롬에서 그린 프레임으로 WRAM·VRAM·OAM·CGRAM 덤프를 만들어 compare 가 같다고 보는지."""

    @classmethod
    def setUpClass(cls):
        cls.rom = Rom(ROM.read_bytes())
        cls.wram, cls.vram, cls.oam, cls.cgram = cls.dump(cls.rom)

    @staticmethod
    def gfx_for(rom, s):
        return next(g for g in range(S.GFX_COUNT) if g != 0x9A and S.gfx_set(rom, g) == s)

    @classmethod
    def dump(cls, rom):
        wram, vram, oam, cgram = bytearray(0x20000), bytearray(0x10000), bytearray(544), bytearray(512)
        for i in range(128):
            oam[i * 4 + 1] = 0xF0
        for p, colors in enumerate(S.obj_palettes(rom)):
            for i, c in enumerate(colors):
                cgram[256 + (p * 16 + i) * 2:258 + (p * 16 + i) * 2] = c.to_bytes(2, 'little')
        wram[0x3220:0x3240] = b'\xff' * 0x20
        state = {'slot': 0, 'oam': 0}

        def slot(g, cells, extra=None):
            k = state['slot']
            state['slot'] += 1
            wram[0x3220 + k] = g
            wram[0x3200 + k] = k * 2
            lst = 0xA000 + k * 0x100
            wram[0x8000 + k * 2:0x8002 + k * 2] = lst.to_bytes(2, 'little')
            for i, c in enumerate(cells):
                wram[lst + i * 2:lst + i * 2 + 2] = c.to_bytes(2, 'little')
            for a, v in (extra or {}).items():
                wram[a + k] = v

        def obj(x, y, t, a):
            place(oam, state['oam'], x, y, t, a)
            state['oam'] += 1

        def person(s, base, x0, y0, lying=False, scramble=False, pal=None):
            rec = S.decode_set(rom, s)
            pal = S.set_obj_palette(rom, s) if pal is None else pal
            tiles = rec['lying_tiles'] if lying else rec['tile_data']
            for i, t in enumerate(tiles):
                vram[0xC000 + (base + i) * 32:0xC000 + (base + i + 1) * 32] = t
            if lying:
                cells = [base + t | (0x4000 if hf else 0) | (0x8000 if vf else 0) for t, hf, vf in rec['lying_cells']]
                drawn = [(rec['lying_cells'][c], x, y) for c, x, y in S.lying_frame_cells(rec, 'down')]
            else:
                cells = [base + (v & 0x7F) | (0x4000 if v & 0x80 else 0) for v in rec['cells']]
                drawn = [((rec['cells'][c] & 0x7F, bool(rec['cells'][c] & 0x80), False), x, y)
                         for c, x, y in S.frame_cells(rec, 'down', 0)]
            slot(cls.gfx_for(rom, s), cells, {0x31C0: int(lying)})
            for (t, hf, vf), x, y in reversed(drawn):
                obj(x0 + (0 if scramble else x), y0 + (0 if scramble else y), base + t,
                    (0x40 if hf else 0) | (0x80 if vf else 0) | pal << 1)
            return rec

        cls.simple = person(0x00, 0x10, 40, 40)
        cls.overlap = person(0x82, 0x40, 80, 40)
        person(0x00, 0x70, 120, 40, lying=True)
        person(0x00, 0xA0, 160, 40, scramble=True)
        person(0x01, 0xD0, 200, 40, pal=(S.set_obj_palette(rom, 0x01) + 1) & 3)

        v = S.VEHICLES[1]
        fr = S.vehicle_frames(rom, v)[0]
        part = fr['part']
        n = part['cols'] * part['rows']
        for t, b in S.vehicle_tiles(rom, v).items():
            vram[0xC000 + t * 32:0xC000 + t * 32 + 32] = b
        slot(0xFE, fr['cells'][:n])
        for k, c in enumerate(fr['cells'][:n]):
            obj(20 + (k % part['cols']) * 8, 120 + (k // part['cols']) * 8, c & 0x1FF,
                (0x40 if c & 0x4000 else 0) | (0x80 if c & 0x8000 else 0) | ((c >> 9) & 7) << 1)

        mp = S.map_object_places(rom)[8]
        wram[0xBE], wram[0xBC], wram[0xBD] = 0x80, mp['bc'], mp['bd']
        wram[0x1997:0x1999] = (0x100).to_bytes(2, 'little')
        want = [0x100 + (b & 0x7F) | (0x4000 if b & 0x80 else 0) | mp['palette'] << 9 for b in mp['cells']]
        slot(0xFE, want, {0x34E0: mp['cols'], 0x3500: mp['rows']})
        for j, c in enumerate(want):
            obj(100 + (j % mp['cols']) * 8, 160 + (j // mp['cols']) * 8, c & 0x1FF,
                (0x40 if c & 0x4000 else 0) | mp['palette'] << 1)
        return bytes(wram), bytes(vram), bytes(oam), bytes(cgram)

    def test_compare_matches_frames(self):
        stats = {}
        out = io.StringIO()
        with redirect_stdout(out):
            S.compare(self.rom, self.wram, self.vram, self.oam, self.cgram, stats)
        self.assertEqual(stats['palette'], [[True] * 4])
        self.assertEqual(stats['groups'], 5)
        self.assertEqual(stats['hits'], 4)
        self.assertEqual(stats['other_palette'], 1)
        self.assertEqual(stats['sets'][0x00], [3 * len(self.simple['tile_data'])] * 2)
        self.assertEqual(stats['sets'][0x82], [len(self.overlap['tile_data'])] * 2)
        down0 = self.simple['frames'][('down', 0)]
        self.assertTrue(any(self.simple['frames'].get((d, f)) == down0 for s, d, f in stats['frames'] if s == 0))
        self.assertIn((0x00, 'down', 'lying'), stats['frames'])
        self.assertEqual(stats['vehicles'], {(0x81, 0): [1, 1]})
        self.assertEqual(stats['vehicle_tiles'][0x81], (0x14, 0x14))
        self.assertEqual(stats['places'][8], [1, 1])
        text = out.getvalue()
        self.assertIn('다름', text)
        self.assertIn('(누운 모양)', text)
        self.assertIn('탈것 81 부분 1', text)

    def test_main_compare_summary(self):
        with tempfile.TemporaryDirectory() as d:
            for name, data in (('w0001.bin', self.wram), ('v0001.vram', self.vram), ('o0001.oam', self.oam),
                               ('c0001.cgram', self.cgram), ('note.txt', b'')):
                Path(d, name).write_bytes(data)
            out = io.StringIO()
            with mock.patch.object(sys, 'argv', ['dq5sprite.py', str(ROM), '--compare', d, '-q']), redirect_stdout(out):
                S.main()
        text = out.getvalue()
        self.assertIn('덤프 1개, OBJ 팔레트 0~2 가 ROM 과 같은 덤프 1개, 팔레트 3 까지 같은 덤프 1개', text)
        self.assertIn('OAM 묶음 5개 중 4개', text)
        self.assertIn('탈것 81 부분 1: 덤프 1개에서 칸 목록 같음', text)
        self.assertIn('누운 모양 (세트, 방향) 1개: 00down', text)
        self.assertNotIn('== ', text)


if __name__ == '__main__':
    unittest.main()
