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
