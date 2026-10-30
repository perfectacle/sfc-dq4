"""필드 그림 RLE·타일 평면 바꾸기·patch 와 그룹 50 이상 맵 그림 쓰기를 원본 롬 없이 확인한다."""
import json
import os
import random
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dq5fieldgfxwrite as fgw  # noqa: E402
import dq5field  # noqa: E402
from dq5field import rle  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402
import dq5mapgfxwrite as mgw  # noqa: E402


def put(data, addr, raw):
    o = lorom(addr)
    data[o:o + len(raw)] = raw


def unrle(packed):
    return rle(Rom(packed + bytes(0x8000 - len(packed) % 0x8000)), 0x8000)[0]


class RleTests(unittest.TestCase):
    def test_shortest_and_roundtrip(self):
        self.assertEqual(fgw.encode_rle(b''), b'\x80')
        self.assertEqual(fgw.encode_rle(b'\x05\x05'), b'\x81\x05\x80')              # 두 번 반복도 반복으로
        self.assertEqual((len(fgw.encode_rle(bytes(300))), unrle(fgw.encode_rle(bytes(300)))), (7, bytes(300)))
        rng = random.Random(3)
        for _ in range(200):
            data = bytes(rng.choice((0, 0, 1, 2, rng.randrange(256))) for _ in range(rng.randrange(1, 700)))
            packed = fgw.encode_rle(data)
            self.assertEqual(unrle(packed), data)

    def test_planar_roundtrip(self):
        tiles = bytes(random.Random(7).randrange(256) for _ in range(fgw.TILES * 32))
        planar = fgw.tiles_to_planar(tiles)
        self.assertEqual(len(planar), 0x4000)
        self.assertEqual(fgw.planar_to_tiles(planar), tiles)
        self.assertEqual(planar[0x1000 + 3 * 8 + 2], tiles[3 * 32 + 5])          # 평면 1, 타일 3, 줄 2


class FieldPatchTests(unittest.TestCase):
    def setUp(self):
        d = bytearray(0x200000)
        for sites in fgw.SITES.values():
            for at, want in sites:
                put(d, at, want)
        for at, want in fgw.ANIM_SITES.values():
            put(d, at, want)
        put(d, fgw.LOAD_SITE, fgw.LOAD_ORIG)
        put(d, fgw.PALETTE_READ, fgw.PALETTE_READ_ORIG)
        put(d, fgw.BLOCK_READ, fgw.BLOCK_READ_ORIG)
        put(d, fgw.REDRAW_SITE, fgw.REDRAW_ORIG)
        put(d, fgw.REDRAW_RTL, b'\x6b')
        for at, want in (fgw.SEARCH_SITE, fgw.PTR_SITE, fgw.NIGHT_SITE, fgw.PAL_BANK_SITE, fgw.WAVE_SITE,
                         *fgw.ATTR_SITES.items(), fgw.REFRESH_SITE, *(x for pair in fgw.W12_LOAD.values() for x in pair)):
            put(d, at, want)
        # 원래 롬의 시간대 표(01:A16B)
        for i, (lo, k) in enumerate(((0, 4), (1, 3), (2, 2), (0xEE, 3), (0xEF, 4), (0xF0, 5), (0xF1, 6), (0xF2, 7),
                                     (0x1FD, 6), (0x1FE, 5))):
            put(d, fgw.TIMES + i * 3, lo.to_bytes(2, 'little') + bytes([k * 2]))
        put(d, fgw.ANIM_TABLE, fgw.encode_anim_table(8))
        tiles = bytes((i // 32) & 0xFF if i % 3 else 0 for i in range(fgw.TILES * 32))
        put(d, fgw.FIELD_CHR, fgw.encode_rle(fgw.tiles_to_planar(tiles)))
        put(d, fgw.ANIM, fgw.encode_rle(bytes(fgw.ANIM_BYTES)))
        self.data = bytes(d)
        self.rom = Rom(self.data)
        self.tmp = tempfile.TemporaryDirectory()
        self.doc = fgw.dump(self.rom, self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_zero_writes_and_in_place(self):
        self.assertEqual(fgw.patch(self.rom, self.doc, self.tmp.name)['writes'], [])
        self.doc['palettes']['world0'][3][0] = 0x1234
        self.doc['tile_palettes'][5] = 7
        m = fgw.patch(self.rom, self.doc, self.tmp.name)
        self.assertEqual([w['at'] for w in m['writes']], ['2A:D714', '01:A289'])
        self.assertNotIn('rom_size', m)

    def test_growing_tiles_need_at(self):
        path = os.path.join(self.tmp.name, 'tiles.bin')
        tiles = bytearray(Path(path).read_bytes())
        tiles[0:32] = bytes(range(32))
        Path(path).write_bytes(tiles)
        with self.assertRaisesRegex(ValueError, '--tiles-at'):
            fgw.patch(self.rom, self.doc, self.tmp.name)
        with self.assertRaises(ValueError):
            fgw.patch(self.rom, self.doc, self.tmp.name, tiles_at=0x408000)
        m = fgw.patch(self.rom, self.doc, self.tmp.name, tiles_at=0x328000)
        notes = {w['note']: w for w in m['writes']}
        self.assertEqual((notes['tiles 뱅크']['hex'], notes['tiles 주소']['hex']), ('32', '00 80'))
        self.assertEqual(fgw.planar_to_tiles(unrle(bytes.fromhex(notes['tiles RLE']['hex']))), bytes(tiles))
        self.assertEqual(m['rom_size'], 2)


    def test_anim_at_overlap_and_cycled_colors(self):
        path = Path(self.tmp.name) / 'anim.bin'
        anim = bytearray(path.read_bytes())
        anim[0:32] = bytes(range(32))
        path.write_bytes(anim)
        with self.assertRaisesRegex(ValueError, '--anim-at'):
            fgw.patch(self.rom, self.doc, self.tmp.name)
        tiles = Path(self.tmp.name) / 'tiles.bin'
        t = bytearray(tiles.read_bytes())
        t[0:32] = bytes(range(32))
        tiles.write_bytes(t)
        with self.assertRaisesRegex(ValueError, '겹침'):
            fgw.patch(self.rom, self.doc, self.tmp.name, tiles_at=0x328000, anim_at=0x328100)
        m = fgw.patch(self.rom, self.doc, self.tmp.name, tiles_at=0x328000, anim_at=0x338000)
        notes = {w['note']: w for w in m['writes']}
        self.assertEqual((notes['anim 뱅크']['at'], notes['anim 주소']['hex']), ('2B:8007', '00 80'))
        self.assertEqual(unrle(bytes.fromhex(notes['anim RLE']['hex'])), bytes(anim))
        self.doc['palettes']['world1'][0][13] = 1                                  # 2번 줄 색 14
        with self.assertRaisesRegex(ValueError, '덮어씀'):
            fgw.patch(self.rom, self.doc, self.tmp.name, tiles_at=0x328000, anim_at=0x338000)
        self.doc['palettes']['world1'][0][13] = 0
        self.doc['tiles_file'] = ['tiles.bin']
        with self.assertRaises(ValueError):
            fgw.patch(self.rom, self.doc, self.tmp.name)

    def apply(self, manifest):
        d = bytearray(self.data)
        for w in manifest['writes']:
            put(d, int(w['at'].replace(':', ''), 16), bytes.fromhex(w['hex']))
        return Rom(bytes(d))

    def test_anim_set_count(self):
        path = Path(self.tmp.name) / 'anim.bin'
        sets = [bytes([k + 1]) * fgw.ANIM_SET for k in range(16)]
        path.write_bytes(b''.join(sets))
        with self.assertRaisesRegex(ValueError, '--anim-at'):
            fgw.patch(self.rom, self.doc, self.tmp.name)
        m = fgw.patch(self.rom, self.doc, self.tmp.name, anim_at=0x338000)
        notes = {w['note']: w for w in m['writes']}
        rle_len = len(bytes.fromhex(notes['anim RLE']['hex']))
        table = notes['움직이는 타일 벌 16개의 WRAM 주소 표']
        self.assertEqual(table['at'], f'33:{0x8000 + rle_len:04X}')
        self.assertEqual(bytes.fromhex(table['hex'])[-2:], (0xC800 + 15 * 192).to_bytes(2, 'little'))
        self.assertEqual(notes['벌 돌리기 AND #$0F']['at'], '02:ACE8')
        self.assertEqual(notes['벌 주소 표(상위 바이트)']['hex'], fgw.long_addr(0x338000 + rle_len + 1).hex(' '))
        cur = fgw.current(self.apply(m))
        self.assertEqual(cur['anim_sets'], sets)
        path.write_bytes(bytes(fgw.ANIM_SET * 12))                                # 2의 거듭제곱이 아님
        with self.assertRaisesRegex(ValueError, '벌'):
            fgw.patch(self.rom, self.doc, self.tmp.name, anim_at=0x338000)
        path.write_bytes(bytes(fgw.ANIM_SET * 32))
        with self.assertRaises(ValueError):
            fgw.patch(self.rom, self.doc, self.tmp.name, anim_at=0x338000)
        path.write_bytes(bytes(range(256)) * 12)                                  # 16벌, 거의 글자 그대로
        with self.assertRaisesRegex(ValueError, '한 뱅크'):
            fgw.patch(self.rom, self.doc, self.tmp.name, anim_at=0x33F800)
        path.write_bytes(bytes(fgw.ANIM_SET * 4))                                 # 4벌은 제자리, AND 만
        m = fgw.patch(self.rom, self.doc, self.tmp.name)
        self.assertEqual({w['note'] for w in m['writes']}, {'anim RLE', '벌 돌리기 AND #$03'})
        self.assertEqual(next(w['at'] for w in m['writes'] if w['note'] == 'anim RLE'), '1E:D0FF')
        self.assertNotIn('rom_size', m)
        self.assertEqual(fgw.current(self.apply(m))['anim_sets'], [bytes(fgw.ANIM_SET)] * 4)
        path.write_bytes(bytes(range(256)) * 3)                                   # 4벌이지만 원래 자리보다 김
        with self.assertRaisesRegex(ValueError, '--anim-at'):
            fgw.patch(self.rom, self.doc, self.tmp.name)
        m = fgw.patch(self.rom, self.doc, self.tmp.name, anim_at=0x338000)
        self.assertFalse([w for w in m['writes'] if '표' in w['note']])
        path.write_bytes(bytes(fgw.ANIM_SET * 8))                                 # 8벌을 옮기면 표는 그대로
        m = fgw.patch(self.rom, self.doc, self.tmp.name, anim_at=0x338000)
        self.assertFalse([w for w in m['writes'] if '벌' in w['note']])

    def test_person_palettes(self):
        self.assertEqual(len(self.doc['person_palettes']['day']), 30)
        del self.doc['person_palettes']                                           # 예전 문서도 그대로 받음
        self.assertEqual(fgw.patch(self.rom, self.doc, self.tmp.name)['writes'], [])
        self.doc['person_palettes'] = {'day': [0x7C00] * 30, 'night': [0] * 30}
        m = fgw.patch(self.rom, self.doc, self.tmp.name)
        self.assertEqual([w['at'] for w in m['writes']], ['01:A45E'])
        self.assertEqual(fgw.current(self.apply(m))['person_palettes']['day'], [0x7C00] * 30)
        self.doc['person_palettes']['night'] = [0x8000] + [0] * 29
        with self.assertRaisesRegex(ValueError, '15비트'):
            fgw.patch(self.rom, self.doc, self.tmp.name)
        self.doc['person_palettes'] = {'day': [0] * 30}
        with self.assertRaisesRegex(ValueError, 'person_palettes'):
            fgw.patch(self.rom, self.doc, self.tmp.name)

    def test_world_tiles(self):
        folder = Path(self.tmp.name)
        w1 = bytearray((folder / 'tiles.bin').read_bytes())
        w1[63 * 32:64 * 32] = bytes(range(32))
        (folder / 'w1.bin').write_bytes(w1)
        nib1 = list(self.doc['tile_palettes'])
        nib1[63] = 9
        self.doc['worlds'] = {'world1': {'tiles_file': 'w1.bin', 'tile_palettes': nib1}}
        with self.assertRaisesRegex(ValueError, '--worlds-at'):
            fgw.patch(self.rom, self.doc, self.tmp.name)
        with self.assertRaisesRegex(ValueError, '겹침'):
            fgw.patch(self.rom, self.doc, self.tmp.name, tiles_at=0x348100, worlds_at=0x348000)
        m = fgw.patch(self.rom, self.doc, self.tmp.name, worlds_at=0x348000)
        sites = {w['at']: w for w in m['writes']}
        self.assertEqual(sites['01:A4A7']['hex'], '22 00 80 34 80 04 ea ea ea ea')
        nib_hook = fgw.long_addr(0x348000 + fgw.LOAD_LEN).hex(' ')
        self.assertEqual([sites[a]['hex'] for a in ('00:BBB4', '00:BBBE', '00:BBDA', '00:BBE4')], [f'22 {nib_hook}'] * 4)
        self.assertEqual(m['rom_size'], 2)
        cur = fgw.current(self.apply(m))
        self.assertEqual(cur['worlds']['world1'], (bytes(w1), nib1))
        self.assertEqual(cur['worlds']['world0'], ((folder / 'tiles.bin').read_bytes(), self.doc['tile_palettes']))
        self.assertEqual(cur['worlds']['world2'], cur['worlds']['world0'])
        self.assertEqual(fgw.nib_hook(0x123456)[dq5field.NIB_HOOK_TABLE:dq5field.NIB_HOOK_TABLE + 3],
                         fgw.long_addr(0x123456))
        patched = self.apply(m)                                                   # 디코더도 세계별 니블 표를 읽음
        t0, t1 = dq5field.tile_word(patched, 63, True, 0), dq5field.tile_word(patched, 63, True, 1)
        self.assertEqual((t0 >> 10 & 7, t1 >> 10 & 7), ((self.doc['tile_palettes'][63] + 2) & 7, (9 + 2) & 7))
        self.assertEqual(dq5field.tile_word(self.rom, 63, True, 1), dq5field.tile_word(self.rom, 63, True, 0))
        _, _, table, _, _ = fgw.worlds_layout(0x348000)
        rom = self.apply(m)
        self.assertEqual([rom.u24(table + k * 4) for k in (0, 2, 3)], [fgw.FIELD_CHR] * 3)
        m = fgw.patch(self.rom, self.doc, self.tmp.name, tiles_at=0x358000, worlds_at=0x348000)
        notes = [w['note'] for w in m['writes']]
        self.assertNotIn('tiles 뱅크', notes)                                     # 즉값 자리는 훅이 덮음
        self.assertEqual(self.apply(m).u24(table), 0x358000)
        self.doc['worlds'] = {'world3': {'tiles_file': 'w1.bin', 'tile_palettes': nib1}}
        with self.assertRaisesRegex(ValueError, 'worlds'):
            fgw.patch(self.rom, self.doc, self.tmp.name, worlds_at=0x348000)
        self.doc['worlds'] = {'world2': {'tiles_file': 'w1.bin', 'tile_palettes': nib1[:-1]}}
        with self.assertRaisesRegex(ValueError, 'tile_palettes'):
            fgw.patch(self.rom, self.doc, self.tmp.name, worlds_at=0x348000)
        del self.doc['worlds']
        with self.assertRaisesRegex(ValueError, 'worlds 와 함께'):
            fgw.patch(self.rom, self.doc, self.tmp.name, worlds_at=0x348000)


    def test_world_drawing_uses_world_nibbles(self):
        import dq5gfx
        nib1 = list(self.doc['tile_palettes'])
        nib1[1] ^= 1
        self.doc['worlds'] = {'world1': {'tiles_file': 'tiles.bin', 'tile_palettes': nib1}}
        d = bytearray(self.apply(fgw.patch(self.rom, self.doc, self.tmp.name, worlds_at=0x348000)).d)
        put(d, dq5field.BLOCK_LOWER, b'\x01' * 4)                                   # 블록 0 아래층 네 칸을 타일 1 로
        rom = Rom(bytes(d))
        cg = b''.join(((k * 0x0421) & 0x7FFF).to_bytes(2, 'little') for k in range(256))
        tiles = dq5gfx.field_tiles(rom)
        b0, b1 = (dq5gfx.field_block_images(rom, cg, tiles, world=w)[0].tobytes() for w in (0, 1))
        self.assertNotEqual(b0, b1)
        plain = bytearray(self.data)
        put(plain, dq5field.BLOCK_LOWER, b'\x01' * 4)
        self.assertEqual(dq5gfx.field_block_images(Rom(bytes(plain)), cg, tiles, world=1)[0].tobytes(), b0)
        vram = bytes(0x4000) + bytes(range(256)) * 64 + bytes(0x8000)
        drawn = []
        for w in (0, 1):
            path = os.path.join(self.tmp.name, f'w{w}.png')
            dq5field.render(rom, bytes(1), bytes(1), vram, cg, 0, 0, 1, 1, path, world_no=w)
            drawn.append(Path(path).read_bytes())
        self.assertNotEqual(*drawn)

    def test_world_drawing_uses_world_tiles(self):
        import dq5gfx
        folder = Path(self.tmp.name)
        w1 = bytearray((folder / 'tiles.bin').read_bytes())
        w1[63 * 32:64 * 32] = bytes(range(32))
        (folder / 'w1.bin').write_bytes(w1)
        self.doc['worlds'] = {'world1': {'tiles_file': 'w1.bin', 'tile_palettes': list(self.doc['tile_palettes'])}}
        rom = self.apply(fgw.patch(self.rom, self.doc, self.tmp.name, worlds_at=0x348000))
        t0, t1, t2 = (dq5gfx.field_tiles(rom, w) for w in (0, 1, 2))
        self.assertEqual(t1[63], dq5gfx.planar(bytes(range(32))))
        self.assertNotEqual(t0[63], t1[63])
        self.assertEqual((t0[:63], t2), (t1[:63], t0))
        self.assertEqual(dq5gfx.field_tiles(self.rom, 1), dq5gfx.field_tiles(self.rom, 0))  # 훅 없는 롬은 세 세계가 같음


class HighSetTests(unittest.TestCase):
    def test_high_sites_and_no_palettes(self):
        d = bytearray(0x180000)
        st = mgw.SETS['high']
        for key, (at, n) in st['sites'].items():
            put(d, at, st['expect'][key])
        b = mgw.encode_block({'w': 1, 'h': 1, 'flags': 0, 'b1': 0, 'attr': 1, 'words': [1]}, 2)
        put(d, st['block_start'], b + b'\xff\xff\xff')
        put(d, mgw.chr_addr(st['chr_bank'], 1), b'\x22' * 32)
        rom = Rom(bytes(d))
        with tempfile.TemporaryDirectory() as tmp:
            doc = mgw.dump(rom, tmp, 'high')
            self.assertEqual((doc['set'], len(doc['blocks']), len(doc['chr_palettes'])), ('high', 1, 2))
            self.assertNotIn('palettes', doc)
            self.assertEqual(mgw.patch(rom, doc, tmp)['writes'], [])
            doc['palettes'] = []
            with self.assertRaises(ValueError):
                mgw.patch(rom, doc, tmp)
            del doc['palettes']
            doc['blocks'].append(dict(doc['blocks'][0]))
            m = mgw.patch(rom, doc, tmp, blocks_at=0x358000)
            sites = {w['note']: w['at'] for w in m['writes']}
            self.assertEqual((sites['블록 뱅크'], sites['블록 표 시작']), ('01:932A', '01:8C81'))
            with open(os.path.join(tmp, 'chr.bin'), 'ab') as f:
                f.write(b'\x33' * 32)
            doc['chr_palettes'].append(5)                                       # CHR 셋(홀수 개)
            m = mgw.patch(rom, doc, tmp, chr_at=0x418000, blocks_at=0x358000)
            sites = {w['note']: w for w in m['writes']}
            self.assertEqual((sites['CHR 뱅크']['at'], sites['CHR 팔레트 니블 표 뱅크']['at'],
                              sites['CHR 팔레트 니블 표 주소']['at']), ('01:932F', '01:933A', '01:933E'))
            self.assertEqual(sites['CHR 팔레트 니블 표']['at'], '41:8060')
            self.assertEqual(bytes.fromhex(sites['CHR 팔레트 니블 표']['hex']), bytes([0x00, 0x50]))
            doc['blocks'] = [dict(doc['blocks'][0])] * 513
            with self.assertRaises(ValueError):
                mgw.patch(rom, doc, tmp, blocks_at=0x358000)
        json.dumps(doc)


if __name__ == '__main__':
    unittest.main()
