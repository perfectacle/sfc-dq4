"""ROM 없이 인코더 경계를, rom/dq5.sfc 가 있으면 실제 삽입 불변식을 검사한다."""
import hashlib
from pathlib import Path
import random
import tempfile
import unittest

from PIL import Image

import dq4romassets as assets


class EncodingTests(unittest.TestCase):
    def decode_stream(self, data):
        # DQ5 디코더가 실제 LoROM 주소에서 읽는 형식으로 감싼다.
        return assets.decoder.unpack(assets.Rom(data), 0x008000)[0]

    def test_rle_boundary_and_command_bytes(self):
        randomizer = random.Random(4)
        cases = [b'', bytes(range(256)), bytes([0x80]) * 129,
                 bytes([0x7F]) * 255, b'\x00' * 128 + b'\xff' * 127,
                 bytes(randomizer.randrange(256) for _ in range(1024))]
        for data in cases:
            with self.subTest(length=len(data), prefix=data[:3]):
                self.assertEqual(self.decode_stream(assets.pack_stream(data)), data)

    def test_bitplanes_against_independent_decoder(self):
        rows = [[(x + y * 8) % 16 for x in range(8)] for y in range(8)]
        self.assertEqual(assets.decoder.pixels(assets.tile_bytes(rows)), rows)
        with self.assertRaises(ValueError):
            assets.tile_bytes([[16] * 8] * 8)
        with self.assertRaises(ValueError):
            assets.tile_bytes([[0] * 7] * 8)

    def test_duplicate_flip_and_party_limit(self):
        rows = [[x for x in range(8)] for _ in range(8)]
        tile = assets.tile_bytes(rows)
        flipped = assets.tile_bytes([row[::-1] for row in rows])
        tiles, refs = assets.deduplicate([tile, flipped, tile])
        self.assertEqual(tiles, [tile])
        self.assertEqual(refs, [0, 0x80, 0])
        unique = [assets.tile_bytes([[i % 16] * 8, [i // 16] * 8] + [[0] * 8] * 6) for i in range(49)]
        with self.assertRaisesRegex(ValueError, 'allocation'):
            assets.deduplicate(unique)

    def test_ips_sparse_growth_including_trailing_zeros(self):
        before = bytes(range(255))
        after = bytearray(before + bytes(100))
        after[4] = 99
        after[260] = 13
        patch = assets.ips_patch(before, after)
        self.assertEqual(assets.apply_ips(before, patch), after)
        with self.assertRaises(ValueError):
            assets.apply_ips(before, patch[:-1])
        with self.assertRaises(ValueError):
            assets.ips_patch(after, before)

    def test_checksum_mirror_and_expansion(self):
        source = bytes([1]) * 0x100000 + bytes([2]) * 0x80000
        mirrored = source + source[0x100000:]
        self.assertEqual(assets.mirrored_checksum(source), assets.mirrored_checksum(mirrored))
        for data in (source, mirrored):
            fixed = assets.set_checksum(data)
            complement = int.from_bytes(fixed[0x7FDC:0x7FDE], 'little')
            checksum = int.from_bytes(fixed[0x7FDE:0x7FE0], 'little')
            self.assertEqual(complement ^ checksum, 0xFFFF)
            self.assertEqual(assets.mirrored_checksum(fixed), checksum)

    def test_bad_front_and_wrong_source_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'SHA-1'):
            assets.build(bytes(0x180000))
        with self.assertRaisesRegex(ValueError, '16x24'):
            assets.remap_front(Image.new('P', (16, 16)), [0] * 16)
        source = Image.new('P', (16, 24), 16)
        with self.assertRaisesRegex(ValueError, 'color slots'):
            assets.remap_front(source, [0] * 16)


def synthetic_rom(old_tiles, cells, other_data=None):
    """세트 표·세트 82 레코드·OBJ 팔레트만 채운 12Mbit 롬. 세트 82 의 타일은 2A:8000, other_data 를 주면 세트 10 이
    그 주소의 자료를 쓴다(겹치면 build 가 거부해야 한다)."""
    d = assets.decoder
    data = bytearray(0x180000)

    def put(addr, raw):
        data[assets.lorom(addr):assets.lorom(addr) + len(raw)] = bytes(raw)

    put(d.SET_TABLE_SITES[0], d.SET_POINTERS.to_bytes(3, 'little'))
    put(d.SET_BANK_SITES[0], [d.SET_POINTERS >> 16])
    put(d.SET_POINTERS, b'\xff\xff' * d.TABLE_ENTRIES)
    packed = assets.pack_tiles(old_tiles)
    put(0x2A8000, packed)
    records = [(assets.TARGET_SET, 0x1FE000, 0x2A8000, cells, len(old_tiles))]
    other_tiles = [bytes([7] * 32), bytes([9] * 32)]
    if other_data is None:
        other_data = 0x2B8000
        put(other_data, assets.pack_tiles(other_tiles))
    records.append((0x10, 0x1FE040, other_data, [0, 1, 0x80] * 8, len(other_tiles)))
    for s, at, src, refs, n in records:
        put(d.SET_POINTERS + 2 * s, (at & 0xFFFF).to_bytes(2, 'little'))
        refs = (list(refs) + [0] * 48)[:48]
        put(at, [src & 0xFF, src >> 8 & 0xFF, (src >> 16) | 1 << 6, *refs, n])
    for i in range(16):
        put(d.OBJ_PALETTES + (16 + i) * 2, ((i * 2) | (31 - i * 2) << 5 | (i % 4) * 8 << 10).to_bytes(2, 'little'))
    data[0x7FD7] = 0x0B
    return bytes(data)


def random_tiles(seed, n):
    r = random.Random(seed)
    return [bytes(r.randrange(256) for _ in range(32)) for _ in range(n)]


DOWN_CELLS = [assets.decoder.HEAD_BASE['down'] + i for i in range(4)] + \
    [assets.decoder.BODY_BASE['down'] + i for i in range(4)]


class SyntheticBuildTests(unittest.TestCase):
    """롬 없이 build 의 제자리 쓰기·늘리기·겹침 거부를 합성 롬으로 본다. 원본 SHA-1 검사만 합성 롬의 것으로 바꾼다."""

    def build(self, data):
        from unittest import mock
        with mock.patch.object(assets, 'SOURCE_SHA1', hashlib.sha1(data).hexdigest()):
            return assets.build(data)

    def check_common(self, data, result):
        manifest, patched, patch, tiles, packed, record, *_ = result
        self.assertEqual(assets.apply_ips(data, patch), patched)
        complement = int.from_bytes(patched[0x7FDC:0x7FDE], 'little')
        checksum = int.from_bytes(patched[0x7FDE:0x7FE0], 'little')
        self.assertEqual((complement ^ checksum, assets.mirrored_checksum(patched)), (0xFFFF, checksum))
        at = assets.lorom(0x1FE000)
        self.assertEqual(patched[at:at + 52], record)
        self.assertEqual(record[51], len(tiles))
        # 세트 10 은 레코드도 타일도 그대로
        self.assertEqual(patched[assets.lorom(0x1FE040):assets.lorom(0x1FE040) + 52],
                         data[assets.lorom(0x1FE040):assets.lorom(0x1FE040) + 52])
        self.assertEqual(manifest['verification']['unchanged_sets'], 1)
        return manifest, patched, packed

    def test_smaller_data_is_written_in_place(self):
        # 정면 칸만 쓰는 무작위 타일 8개가 빠지므로 새 자료가 원래 자리보다 작다
        old = random_tiles(1, 28)
        cells = [20 + DOWN_CELLS.index(c) if c in DOWN_CELLS else c % 20 for c in range(48)]
        data = synthetic_rom(old, cells)
        manifest, patched, packed = self.check_common(data, self.build(data))
        self.assertFalse(manifest['target']['expanded'])
        self.assertEqual(len(patched), len(data))
        self.assertEqual(manifest['target']['data_cpu'], '2A8000')
        self.assertLessEqual(len(packed), manifest['target']['allocation_bytes'])
        # 원래 자리 밖(뒤의 남는 바이트)은 건드리지 않는다
        start = assets.lorom(0x2A8000)
        self.assertEqual(patched[start + len(packed):start + manifest['target']['allocation_bytes']],
                         data[start + len(packed):start + manifest['target']['allocation_bytes']])

    def test_larger_data_moves_to_the_expansion_and_keeps_the_mirror(self):
        old = [bytes(32), bytes([0xFF] * 32)]
        cells = [c % 2 for c in range(48)]
        data = synthetic_rom(old, cells)
        manifest, patched, packed = self.check_common(data, self.build(data))
        self.assertTrue(manifest['target']['expanded'])
        self.assertEqual(len(patched), 0x200000)
        self.assertEqual(manifest['target']['data_cpu'], '308000')
        record = patched[assets.lorom(0x1FE000):assets.lorom(0x1FE000) + 3]
        self.assertEqual((record[0], record[1], record[2] & 0x3F, record[2] >> 6), (0x00, 0x80, 0x30, 1))
        # 늘린 4Mbit 는 12Mbit 롬이 거울로 보이던 마지막 4Mbit 를 그대로 두고 새 자료만 앞에 쓴다
        self.assertEqual(patched[0x180000 + len(packed):], data[0x100000 + len(packed):])
        self.assertEqual(patched[0x180000:0x180000 + len(packed)], packed)
        # 원래 자리는 그대로 남는다(다른 쓰기가 없음)
        self.assertEqual(patched[assets.lorom(0x2A8000):assets.lorom(0x2A8000) + 64],
                         data[assets.lorom(0x2A8000):assets.lorom(0x2A8000) + 64])

    def test_expansion_needs_the_12mbit_header(self):
        old = [bytes(32), bytes([0xFF] * 32)]
        data = bytearray(synthetic_rom(old, [c % 2 for c in range(48)]))
        data[0x7FD7] = 0x0C
        with self.assertRaisesRegex(ValueError, 'expansion header'):
            self.build(bytes(data))

    def test_data_shared_with_another_set_is_refused(self):
        old = random_tiles(2, 4)
        data = synthetic_rom(old, [c % 4 for c in range(48)], other_data=0x2A8000)
        with self.assertRaisesRegex(ValueError, 'shared with set 10'):
            self.build(data)


ROM = Path(__file__).resolve().parents[3] / 'rom' / 'dq5.sfc'


@unittest.skipUnless(ROM.is_file(), 'local source ROM not present')
class LocalRomTests(unittest.TestCase):
    def test_rom_patch_and_all_other_sets(self):
        source = ROM.read_bytes()
        manifest, patched, patch, *_ = assets.build(source)
        self.assertEqual(hashlib.sha1(source).hexdigest(), assets.SOURCE_SHA1)
        self.assertEqual(len(patched), 0x200000)
        self.assertEqual(assets.apply_ips(source, patch), patched)
        self.assertEqual(manifest['verification']['unchanged_sets'], 146)
        self.assertEqual(manifest['verification']['unchanged_mixed_head_body_poses'], 21)
        self.assertTrue(manifest['verification']['shared_palettes_unchanged'])
        self.assertEqual(patched[0x180000 + manifest['target']['compressed_bytes']:],
                         source[0x100000 + manifest['target']['compressed_bytes']:])

    def test_export_is_deterministic_and_input_alias_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            a = assets.export(ROM, root / 'a')
            b = assets.export(ROM, root / 'b')
            self.assertEqual(a, b)
            self.assertEqual((root / 'a' / 'manifest.json').read_bytes(), (root / 'b' / 'manifest.json').read_bytes())
            source = root / 'source.sfc'
            source.write_bytes(ROM.read_bytes())
            alias_dir = root / 'alias'
            alias_dir.mkdir()
            (alias_dir / 'dq4-ragnar-front.sfc').hardlink_to(source)
            with self.assertRaisesRegex(ValueError, 'overwrite'):
                assets.export(source, alias_dir)
            self.assertEqual(hashlib.sha1(source.read_bytes()).hexdigest(), assets.SOURCE_SHA1)


if __name__ == '__main__':
    unittest.main()
