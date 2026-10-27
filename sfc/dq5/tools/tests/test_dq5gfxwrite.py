"""전투 배경 타일 압축·그림·목록·팔레트 인코더와 맵 블록 검사를 원본 롬 없이 확인한다."""
import os
import random
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dq5battlebgwrite import (  # noqa: E402
    encode_list, encode_palette, encode_picture, encode_tile, place, read_list, read_palette, read_picture, tile_at,
)
import dq5battlebgwrite as bgw  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402
import dq5mapgfxwrite as mgw  # noqa: E402
from dq5mapgfxwrite import encode_block  # noqa: E402


def rom_at(data):
    """data 를 00:8000 에 둔 롬."""
    return Rom(bytes(0) + data + bytes(0x8000 - len(data) % 0x8000))


class TileTests(unittest.TestCase):
    def roundtrip(self, t):
        enc = encode_tile(t)
        got, end = tile_at(enc, 0)
        self.assertEqual((got, end), (t, len(enc)))
        return enc

    def test_special_tiles(self):
        self.assertEqual(self.roundtrip(bytes(32)), b'\x00')                        # 평면 없음
        self.assertEqual(len(self.roundtrip(b'\xff' * 32)), 1 + 1 + 4)              # 채움 FF, 마스크 넷이 모두 0
        one = bytearray(32)
        one[16 + 2 * 3 + 1] = 0x18                                                  # 평면 3 의 4번째 줄만
        enc = self.roundtrip(bytes(one))
        self.assertEqual(enc[0] & 0x0F, 0x08)
        raw = bytes(range(1, 33))
        self.assertEqual(self.roundtrip(raw)[0], 0x0F)                              # 다 다르면 그대로가 짧음

    def test_random_tiles(self):
        rng = random.Random(5)
        for _ in range(500):
            t = bytearray(32)
            for i in range(32):
                if rng.random() < 0.4:
                    t[i] = rng.choice((0xFF, rng.randrange(256)))
            if rng.random() < 0.3:
                t[16:] = bytes(16)
            self.roundtrip(bytes(t))
        with self.assertRaises(ValueError):
            encode_tile(bytes(31))


class PictureTests(unittest.TestCase):
    def test_picture_roundtrip_and_absent_cells(self):
        tiles = [bytes(32), b'\x11' * 32, bytes(range(32)), bytes(32), b'\xff' * 32, bytes(32)]
        cells = [1, 1, 1, 0, 1, 1]
        data = encode_picture(3, 2, cells, tiles)
        self.assertEqual(data[0], 0x21)
        self.assertEqual(data[1], 0b11101100)
        w, h, c, t, size = read_picture(rom_at(data), 0x8000)
        self.assertEqual((w, h, c, t, size), (3, 2, cells, tiles, len(data)))
        with self.assertRaises(ValueError):
            encode_picture(3, 2, [1, 1, 1, 0, 1, 1], tiles[:3] + [b'\x01' * 32] + tiles[4:])   # 빈 칸에 그림
        with self.assertRaises(ValueError):
            encode_picture(17, 1, [0] * 17, [bytes(32)] * 17)

    def test_list_and_palette(self):
        entries = [[1, 0x80], [2, 0x41], [0xFE, 0x3F]]
        data = encode_list(entries)
        self.assertEqual(read_list(rom_at(data), 0x8000), (entries, len(data)))
        for bad in ([[0xFF, 0]], [[1]], [[1, 256]], [[True, 1]]):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                encode_list(bad)
        pal = {'slot': 5, 'rows': [[0x001F, 0x7FFF], [0x03E0]]}
        data = encode_palette(pal)
        self.assertEqual(read_palette(rom_at(data), 0x8000), (pal, len(data)))
        for bad in ({'slot': 5, 'rows': []}, {'slot': 5, 'rows': [[0x8000]]}, {'slot': 5, 'rows': [[1] * 16]}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                encode_palette(bad)

    def test_place_largest_first(self):
        got = place([('a', 10), ('b', 30), ('c', 5)], [(0, 32), (100, 120)])
        self.assertEqual(got, ({'b': 0, 'a': 100, 'c': 110}, [(30, 32), (115, 120)]))
        self.assertIsNone(place([('a', 40)], [(0, 32), (100, 120)])[0])
        self.assertEqual(place([('y', 4), ('x', 4)], [(0, 8)])[0], {'x': 0, 'y': 4})    # 같은 크기는 id 순


class BlockTests(unittest.TestCase):
    def test_encode_block(self):
        b = {'w': 2, 'h': 1, 'flags': 1, 'b1': 0x12, 'attr': 3, 'words': [0x0010, 0xC011]}
        self.assertEqual(encode_block(b, 0x20), bytes([0x48, 0x12, 3, 0x10, 0x00, 0x11, 0xC0]))
        for key, value in (('words', [0x0010, 0x1011]), ('words', [0x0010, 0x0020]), ('w', 9), ('attr', 0xFF),
                           ('words', [1])):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                encode_block({**b, key: value}, 0x20)



def apply(data, manifest):
    """패치 목록을 바이트열에 적용. 늘린 자리는 rom_size 만큼 0 으로 늘린다."""
    size = {2: 0x200000, 3: 0x300000, 4: 0x400000}.get(manifest.get('rom_size'), len(data))
    out = bytearray(data) + bytes(max(0, size - len(data)))
    spans = []
    for w in manifest['writes']:
        bank, low = (int(v, 16) for v in w['at'].split(':'))
        off = lorom(bank << 16 | low)
        raw = bytes.fromhex(w['hex'])
        if 'orig' in w:
            assert bytes(data[off:off + len(raw)]) == bytes.fromhex(w['orig'])
        spans.append((off, off + len(raw)))
        out[off:off + len(raw)] = raw
    spans.sort()
    assert all(a[1] <= b[0] for a, b in zip(spans, spans[1:])), '쓰기가 겹침'
    return bytes(out)


def put(data, addr, raw):
    o = lorom(addr)
    data[o:o + len(raw)] = raw


class BattleBgPatchTests(unittest.TestCase):
    def setUp(self):
        d = bytearray(0x180000)
        for at, want in bgw.ORIGINAL_SITES.items():
            put(d, at, want)
        p1 = encode_picture(1, 1, [1], [bytes(range(32))])
        p2 = encode_picture(2, 1, [1, 0], [b'\x11' * 32, bytes(32)])
        put(d, 0x288395, p1)
        put(d, 0x288395 + len(p1), p2)
        self.p2 = 0x288395 + len(p1)
        put(d, 0x2882F9, b''.join((0x8395 if i != 1 else self.p2 & 0xFFFF).to_bytes(2, 'little') for i in range(78)))
        put(d, 0x28BED0, encode_palette({'slot': 5, 'rows': [[1, 2]]}))
        put(d, 0x28BDFC, (0xBED0).to_bytes(2, 'little') * 106)
        l1, l2 = encode_list([[1, 2]]), encode_list([[3, 4], [5, 6]])
        put(d, 0x28CAAC, l1)
        put(d, 0x28FD64, l2)                                        # 세계 2 목록은 원래 자리(22:88D3 즉값)
        self.l2 = 0x28FD64
        put(d, 0x28C9C2, (0xCAAC).to_bytes(2, 'little') * 117)
        self.data = bytes(d)
        self.rom = Rom(self.data)
        self.tmp = tempfile.TemporaryDirectory()
        self.doc = bgw.dump(self.rom, self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def reread(self, data):
        o = bgw.original(Rom(data))
        return o

    def test_unchanged_is_zero_writes_and_deterministic(self):
        self.assertEqual(bgw.patch(self.rom, self.doc, self.tmp.name)[0]['writes'], [])
        pal = self.doc['palettes'][0]
        pal['rows'][0][0] = 0x7FFF                                  # 같은 크기: 제자리
        a = bgw.patch(self.rom, self.doc, self.tmp.name)[0]
        b = bgw.patch(self.rom, self.doc, self.tmp.name)[0]
        self.assertEqual(a, b)
        self.assertEqual([w['at'] for w in a['writes']], ['28:BED0'])

    def test_grow_needs_at_then_uses_freed_picture_room(self):
        self.doc['palettes'][0]['rows'].append([3])                # 3바이트 커짐: 팔레트 자리에 안 들어감
        with self.assertRaisesRegex(ValueError, '--palettes-at'):
            bgw.patch(self.rom, self.doc, self.tmp.name)
        manifest, layout = bgw.patch(self.rom, self.doc, self.tmp.name, at=0x408000)
        self.assertEqual(manifest['rom_size'], 3)
        out = apply(self.data, manifest)
        rom = Rom(out)
        self.assertEqual((out[lorom(0x22CB36)], out[lorom(0x22CB55)]), (0x40, 0x40))
        pal_at = 0x280000 | rom.u16(0x28BDFC)
        self.assertTrue(0x288395 <= pal_at < self.p2 + 16)           # 그림이 비운 자리
        self.assertEqual(bgw.read_palette(rom, pal_at)[0]['rows'], [[1, 2], [3]])
        pic = 0x400000 | rom.u16(0x2882FB)
        self.assertEqual(bgw.read_picture(rom, pic)[3][0], b'\x11' * 32)

    def test_move_palettes_and_lists_together(self):
        self.doc['palettes'][0]['rows'].append([3])
        for x in self.doc['lists']:
            x['entries'].append([9, 9])
        manifest, _ = bgw.patch(self.rom, self.doc, self.tmp.name, palettes_at=0x418000, lists_at=0x418000)
        out = apply(self.data, manifest)
        rom = Rom(out)
        self.assertEqual((out[lorom(0x228809)], out[lorom(0x228880)], out[lorom(0x22CB36)]), (0x41, 0x41, 0x28))
        pal = 0x410000 | rom.u16(0x28BDFC)
        lst = 0x410000 | rom.u16(0x28C9C2)
        alt = 0x410000 | rom.u16(0x2288D4)
        self.assertEqual(bgw.read_palette(rom, pal)[0]['rows'], [[1, 2], [3]])
        self.assertEqual(bgw.read_list(rom, lst)[0], [[1, 2], [9, 9]])
        self.assertEqual(bgw.read_list(rom, alt)[0], [[3, 4], [5, 6], [9, 9]])
        spans = sorted([(pal, pal + bgw.read_palette(rom, pal)[1]), (lst, lst + 5), (alt, alt + 7)])
        self.assertTrue(all(a[1] <= b[0] for a, b in zip(spans, spans[1:])))

    def test_alt_list_moves_with_immediate(self):
        alt = self.doc['alt_list']
        lst = next(x for x in self.doc['lists'] if x['id'] == alt)
        lst['entries'] = [[3, 4]]                                    # 줄어듦: 제자리
        out = apply(self.data, bgw.patch(self.rom, self.doc, self.tmp.name)[0])
        self.assertEqual(Rom(out).u16(0x2288D4), self.l2 & 0xFFFF)
        main = next(x for x in self.doc['lists'] if x['id'] != alt)
        main['entries'] = [[1, 2], [7, 8]]                           # 커짐: 다시 놓기(큰 것이 FD64 로)
        out = apply(self.data, bgw.patch(self.rom, self.doc, self.tmp.name)[0])
        rom = Rom(out)
        self.assertEqual(rom.u16(0x2288D4), 0xCAAC)
        self.assertEqual(bgw.read_list(rom, 0x280000 | rom.u16(0x2288D4))[0], [[3, 4]])
        self.assertEqual(bgw.read_list(rom, 0x280000 | rom.u16(0x28C9C2))[0], [[1, 2], [7, 8]])


class MapGfxPatchTests(unittest.TestCase):
    def setUp(self):
        d = bytearray(0x180000)
        for key, (at, n) in mgw.SITES.items():
            put(d, at, mgw.EXPECT[key])
        b0 = encode_block({'w': 1, 'h': 1, 'flags': 0, 'b1': 0, 'attr': 1, 'words': [0]}, 3)
        b1 = encode_block({'w': 1, 'h': 1, 'flags': 0, 'b1': 0, 'attr': 2, 'words': [2]}, 3)
        put(d, 0x168000, b0 + b1 + b'\xff\xff\xff')
        for i in range(3):
            put(d, mgw.chr_addr(0x13, i), bytes([i + 1]) * 32)
        put(d, 0x2A8781, bytes([0x12, 0x3F]))                        # 니블 1,2,3 과 다음 CHR 몫 F
        put(d, mgw.PALSET_LISTS, (0xE0F8).to_bytes(2, 'little') * (mgw.SET_COUNT * 2))   # 세트마다 같은 목록
        put(d, mgw.ROW_READ, bytes.fromhex('b9 c8 e5'))
        self.data = bytes(d)
        self.rom = Rom(self.data)
        self.tmp = tempfile.TemporaryDirectory()
        self.doc = mgw.dump(self.rom, self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_in_place_and_odd_nibble(self):
        self.assertEqual(len(self.doc['blocks']), 2)
        self.assertEqual(mgw.patch(self.rom, self.doc, self.tmp.name)['writes'], [])
        self.doc['chr_palettes'][2] = 9
        out = apply(self.data, mgw.patch(self.rom, self.doc, self.tmp.name))
        self.assertEqual(out[lorom(0x2A8782)], 0x9F)                 # 아래 니블(다음 CHR 몫)은 그대로

    def test_palette_rows_grow_with_hook(self):
        self.doc['palettes'].append([0x1F] * 16)
        with self.assertRaisesRegex(ValueError, '--palettes-at'):
            mgw.patch(self.rom, self.doc, self.tmp.name)
        first = next(iter(self.doc['palette_lists']))
        self.doc['palette_lists'][first] = [208] * 7
        manifest = mgw.patch(self.rom, self.doc, self.tmp.name, palettes_at=0x428000)
        out = apply(self.data, manifest)
        self.assertEqual(out[lorom(0x10DE84):lorom(0x10DE84) + 3], bytes.fromhex('20 e0 ff'))
        self.assertEqual(out[lorom(0x10FFE0):lorom(0x10FFE0) + 8], bytes.fromhex('da bb bf 00 80 42 fa 60'))
        self.assertEqual(out[lorom(0x428000) + 208 * 32:lorom(0x428000) + 208 * 32 + 2], b'\x1f\x00')
        self.assertEqual(Rom(out).u16(0x100000 | int(first, 16)), 208)
        self.doc['palette_lists'][first] = [209] * 7
        with self.assertRaises(ValueError):
            mgw.patch(self.rom, self.doc, self.tmp.name, palettes_at=0x428000)

    def test_grow_chr_and_blocks(self):
        with open(os.path.join(self.tmp.name, 'chr.bin'), 'ab') as f:
            f.write(b'\x77' * 32)
        self.doc['chr_palettes'].append(4)
        self.doc['blocks'].append({'w': 1, 'h': 1, 'flags': 0, 'b1': 0, 'attr': 3, 'words': [3]})
        with self.assertRaisesRegex(ValueError, '--chr-at'):
            mgw.patch(self.rom, self.doc, self.tmp.name, blocks_at=0x318000)
        with self.assertRaisesRegex(ValueError, '--blocks-at'):
            mgw.patch(self.rom, self.doc, self.tmp.name, chr_at=0x408000)
        with self.assertRaises(ValueError):
            mgw.patch(self.rom, self.doc, self.tmp.name, chr_at=0x408000, blocks_at=0x408000)
        manifest = mgw.patch(self.rom, self.doc, self.tmp.name, chr_at=0x408000, blocks_at=0x318000)
        self.assertEqual(manifest['rom_size'], 3)
        out = apply(self.data, manifest)
        rom = Rom(out)
        self.assertEqual(out[lorom(mgw.chr_addr(0x40, 3)):lorom(mgw.chr_addr(0x40, 3)) + 32], b'\x77' * 32)
        nib = rom.u8(0x019305) << 16 | rom.u16(0x019309)
        self.assertEqual(nib, 0x408080)                              # CHR 넷(128바이트) 바로 뒤
        self.assertEqual(rom.d[lorom(nib):lorom(nib) + 2], bytes([0x12, 0x34]))
        self.assertEqual((rom.u8(0x0192F5), rom.u8(0x018CDF), rom.u16(0x018CE7)), (0x31, 0x31, 0x8000))
        blocks = rom.d[lorom(0x318000):lorom(0x318000) + 3 * 5 + 3]
        self.assertEqual(blocks[-3:], b'\xff\xff\xff')
        self.assertEqual(blocks[10:15], encode_block(self.doc['blocks'][2], 4))


if __name__ == '__main__':
    unittest.main()
