"""승인 타이틀의 픽셀 보존과 독립 SFC 미리보기 입력 경계를 검사한다."""

import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

import dq4title
import dq4titleassets as assets
import dq4titlepreview as preview
from dq4graphics import export_image


class TitleAssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files, cls.manifest = assets.build()

    def test_approved_pixels_survive_native_encoding(self):
        source = assets.DEFAULT_SOURCE.read_bytes()
        self.assertEqual(hashlib.sha256(source).hexdigest(), assets.APPROVED_SOURCE_SHA256)
        self.assertEqual(self.manifest['visual_status'], 'user_approved')
        with Image.open(io.BytesIO(source)) as original, Image.open(io.BytesIO(self.files['title.png'])) as output:
            expected = original.convert('RGB').tobytes()
            self.assertEqual(output.convert('RGB').tobytes(), expected)
        chr_data, tilemap, palette = (self.files[f'title.{suffix}'] for suffix in ('chr', 'map', 'pal'))
        reconstructed = bytearray(256 * 224 * 3)
        for ty in range(28):
            for tx in range(32):
                entry = int.from_bytes(tilemap[(ty * 32 + tx) * 2:(ty * 32 + tx) * 2 + 2], 'little')
                tile, bank = (entry & 1023) * 32, (entry >> 10) & 7
                for y in range(8):
                    for x in range(8):
                        value = sum(((chr_data[tile + (bit // 2) * 16 + y * 2 + bit % 2] >> (7 - x)) & 1) << bit for bit in range(4))
                        index = bank * 16 + value if value else 0
                        color = int.from_bytes(palette[index * 2:index * 2 + 2], 'little')
                        rgb = bytes(((color >> shift & 31) << 3) | ((color >> shift & 31) >> 2) for shift in (0, 5, 10))
                        offset = ((ty * 8 + y) * 256 + tx * 8 + x) * 3
                        reconstructed[offset:offset + 3] = rgb
        self.assertEqual(bytes(reconstructed), expected)

    def test_export_is_deterministic_and_preserves_source(self):
        before = hashlib.sha1(assets.DEFAULT_SOURCE.read_bytes()).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            one = assets.export(assets.DEFAULT_SOURCE, root / 'one')
            two = assets.export(assets.DEFAULT_SOURCE, root / 'two')
            self.assertEqual(one, two)
            for name in (*self.files, 'manifest.json'):
                self.assertEqual((root / 'one' / name).read_bytes(), (root / 'two' / name).read_bytes())
        self.assertEqual(hashlib.sha1(assets.DEFAULT_SOURCE.read_bytes()).hexdigest(), before)

    def test_original_title_source_and_output_are_unchanged(self):
        original = dq4title.SOURCE.read_bytes()
        self.assertEqual(hashlib.sha1(original).hexdigest(), '7288e133b197043cda31d05499a67b635be47828')
        image = dq4title.build_title()
        fingerprint = hashlib.sha256(image.tobytes() + bytes(image.getpalette())).hexdigest()
        self.assertEqual(fingerprint, 'a38c2eb76b1a5198199d472dbf1e9f882b201ba3330b443ca16d660c254d649f')
        self.assertEqual(dq4title.SOURCE.read_bytes(), original)

    def test_low_color_quantization_pads_all_palette_banks(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'solid.png'
            Image.new('RGB', (256, 224), (40, 80, 120)).save(source)
            image = dq4title.build_title(source)
            palette = image.getpalette()
            self.assertEqual(len(palette), 768)
            self.assertTrue(all(palette[i:i + 3] == palette[:3] for i in range(0, 384, 48)))
            files, manifest = export_image('title', image)
            self.assertEqual(len(files['title.pal']), 256)
            self.assertEqual(manifest['roundtrip_pixel_differences'], 0)

    def test_used_bank_zero_and_non_sfc_colors_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'invalid.png'
            with Image.open(assets.DEFAULT_SOURCE) as original:
                image = original.copy()
            image.putpixel((0, 0), 16)
            image.save(source)
            with self.assertRaisesRegex(ValueError, 'backdrop'):
                assets.native_title(source)
            with Image.open(assets.DEFAULT_SOURCE) as original:
                image = original.copy()
            index = next(value for value in image.tobytes() if value)
            palette = image.getpalette()
            palette[index * 3] = 1
            image.putpalette(palette)
            image.save(source)
            with self.assertRaisesRegex(ValueError, '5-bit'):
                assets.native_title(source)

    def test_rgb_or_wrong_size_is_not_silently_converted(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'invalid.png'
            for image in (Image.new('RGB', (256, 224)), Image.new('P', (256, 192))):
                image.save(source)
                with self.assertRaisesRegex(ValueError, 'native title'):
                    assets.native_title(source)

    def test_export_rejects_hardlinked_source_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source.png'
            data = assets.DEFAULT_SOURCE.read_bytes()
            source.write_bytes(data)
            output = root / 'output'
            output.mkdir()
            (output / 'title.png').hardlink_to(source)
            with self.assertRaisesRegex(ValueError, 'overwrite'):
                assets.export(source, output)
            self.assertEqual(source.read_bytes(), data)


class PreviewInputTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.blobs = {'title.chr': bytes(32), 'title.map': bytes(2048), 'title.pal': bytes(256)}
        for name, data in self.blobs.items():
            (self.root / name).write_bytes(data)

    def assert_rejected(self, pattern):
        before = {name: (self.root / name).read_bytes() for name in self.blobs}
        output = self.root / 'preview.sfc'
        previous_output = output.read_bytes() if output.exists() else None
        with patch.object(preview.shutil, 'which', side_effect=AssertionError('assembler lookup before rejection')):
            with self.assertRaisesRegex(ValueError, pattern):
                preview.build(self.root, self.root / 'preview.sfc', 'unused-asar')
        self.assertEqual({name: (self.root / name).read_bytes() for name in self.blobs}, before)
        if previous_output is None:
            self.assertFalse(output.exists())
        else:
            self.assertEqual(output.read_bytes(), previous_output)

    def test_chr_size_guards(self):
        for size in (0, 31, 0x8020):
            with self.subTest(size=size):
                (self.root / 'title.chr').write_bytes(bytes(size))
                self.assert_rejected('complete 4bpp')

    def test_tilemap_missing_tile_and_size_guards(self):
        for blob, pattern in ((bytes(2046), '32x32'), (b'\x01\x00' + bytes(2046), 'missing tile')):
            (self.root / 'title.map').write_bytes(blob)
            self.assert_rejected(pattern)

    def test_palette_size_color_and_backdrop_guards(self):
        for blob, pattern in ((bytes(254), 'palettes'), (b'\x00\x80' + bytes(254), 'BGR555'), (bytes(32) + b'\x01\x00' + bytes(222), 'backdrop')):
            (self.root / 'title.pal').write_bytes(blob)
            self.assert_rejected(pattern)

    def test_output_and_report_hardlinks_do_not_overwrite_sources(self):
        png = self.root / 'title.png'
        png.write_bytes(b'opaque original native image fixture')
        for name in (*self.blobs, 'title.png'):
            source = self.root / name
            before = source.read_bytes()
            for suffix in ('.sfc', '.json'):
                with self.subTest(source=name, output=suffix):
                    target = self.root / ('preview' + suffix)
                    target.hardlink_to(source)
                    self.assert_rejected('overwrite')
                    self.assertEqual(source.read_bytes(), before)
                    target.unlink()


if __name__ == '__main__':
    unittest.main()
