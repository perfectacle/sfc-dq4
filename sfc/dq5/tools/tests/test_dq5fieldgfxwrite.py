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
        d = bytearray(0x180000)
        for sites in fgw.SITES.values():
            for at, want in sites:
                put(d, at, want)
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
