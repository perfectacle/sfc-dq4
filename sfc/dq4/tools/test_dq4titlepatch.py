"""통합 타이틀의 색 소유 범위와 ROM 기록 경계를 검사한다."""

import hashlib
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

import dq4titleassets
import dq4titlepatch as patcher


class IntegratedTitleTests(unittest.TestCase):
    def test_gleam_only_changes_colors_owned_by_logo(self):
        image = Image.new('P', (256, 224))
        palette = [0] * 768
        for index, rgb in ((1, (198, 165, 24)), (2, (198, 165, 24)), (3, (24, 165, 198)), (4, (66, 49, 8))):
            palette[index * 3:index * 3 + 3] = rgb
            image.putpixel((20 + index, 80), index)
        image.putpixel((0, 0), 2)
        image.putpalette(palette)
        base = b''.join(((palette[i * 3] >> 3) | (palette[i * 3 + 1] >> 3) << 5 | (palette[i * 3 + 2] >> 3) << 10).to_bytes(2, 'little') for i in range(128))
        gleam, selected, deltas = patcher.gleam_palettes(image, base)
        self.assertEqual(selected, [1])
        self.assertEqual(len(gleam), 32 * 256)
        self.assertEqual(gleam[:256], base)
        self.assertEqual(gleam[-256:], base)
        self.assertEqual(max(deltas), 3)
        for frame in range(32):
            data = gleam[frame * 256:(frame + 1) * 256]
            for index in range(128):
                if index != 1:
                    self.assertEqual(data[index * 2:index * 2 + 2], base[index * 2:index * 2 + 2])
            value = int.from_bytes(data[2:4], 'little')
            for shift, original in ((0, 24), (5, 20), (10, 3)):
                self.assertEqual(value >> shift & 31, min(31, original + deltas[frame]))

    def test_changed_canonical_source_cannot_claim_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            changed = root / 'canonical.png'
            changed.write_bytes(patcher.DEFAULT_SOURCE.read_bytes() + b'changed provenance')
            with patch.object(patcher, 'DEFAULT_SOURCE', changed):
                with self.assertRaisesRegex(ValueError, 'approved SHA-256'):
                    patcher.read_assets(root / 'missing-assets')

    def test_actual_asset_pack_rejects_changed_chr(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            dq4titleassets.export(dq4titleassets.DEFAULT_SOURCE, source)
            blobs, selected, _ = patcher.read_assets(source)
            self.assertTrue(selected)
            self.assertLessEqual(len(blobs['title.chr']), 0x7000)
            data = bytearray((source / 'title.chr').read_bytes())
            data[0] ^= 1
            (source / 'title.chr').write_bytes(data)
            with self.assertRaisesRegex(ValueError, 'approved PNG encoding'):
                patcher.read_assets(source)

    def test_output_aliases_are_rejected_without_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / 'original.sfc'
            original.write_bytes(b'original fixture')
            output = root / 'output.sfc'
            output.hardlink_to(original)
            with self.assertRaisesRegex(ValueError, 'source file'):
                patcher.protect_outputs([output], [original])
            self.assertEqual(original.read_bytes(), b'original fixture')
            with self.assertRaisesRegex(ValueError, 'alias'):
                patcher.protect_outputs([root / 'same.ips', root / 'same.ips'], [])

    def test_layout_preserves_original_and_expansion_mirror(self):
        original = bytes(0x180000)
        blobs = {'title.chr': bytes([1]) * 32, 'title.map': bytes([2]) * 2048,
                 'title.pal': bytes([3]) * 256, 'gleam.pal': bytes([4]) * 8192}
        rom = bytearray(original + original[0x100000:])
        rom[patcher.HOOK:patcher.HOOK + 5] = patcher.NEW_HOOK
        rom[patcher.MUSIC_HOOK:patcher.MUSIC_HOOK + 3] = patcher.NEW_MUSIC_HOOK
        rom[0x180000:0x180002] = b'\xEA\xEA'
        for name, offset in (('title.chr', 0x188000), ('title.map', 0x190000), ('title.pal', 0x190800), ('gleam.pal', 0x192000)):
            rom[offset:offset + len(blobs[name])] = blobs[name]
        patcher.verify_layout(original, rom, blobs)
        missing_music = bytearray(rom)
        missing_music[patcher.MUSIC_HOOK:patcher.MUSIC_HOOK + 3] = bytes(3)
        with self.assertRaisesRegex(ValueError, 'title hook'):
            patcher.verify_layout(original, missing_music, blobs)
        for address in (0x100, 0x181000, 0x188020, 0x190900, 0x194000):
            with self.subTest(address=address):
                changed = bytearray(rom)
                changed[address] = 0xFF
                with self.assertRaisesRegex(ValueError, 'outside declared'):
                    patcher.verify_layout(original, changed, blobs)

    def test_wrong_source_rom_fails_before_assembly(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / 'source.sfc'
            original.write_bytes(bytes(0x180000))
            with self.assertRaisesRegex(ValueError, 'SHA-1'):
                patcher.build(original, root / 'missing-assets', root / 'output.sfc', 'missing-asar')
            self.assertFalse((root / 'output.sfc').exists())


ROM = Path(__file__).resolve().parents[3] / 'rom/dq5.sfc'
ASAR = shutil.which(os.environ.get('ASAR', 'asar'))


@unittest.skipUnless(ROM.is_file() and ASAR, 'local ROM and ASAR are required')
class LocalRomBuildTests(unittest.TestCase):
    def test_determinism_independent_ips_and_original_preservation(self):
        source = ROM.read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dq4titleassets.export(dq4titleassets.DEFAULT_SOURCE, root / 'assets')
            one = patcher.build(ROM, root / 'assets', root / 'one.sfc', ASAR)
            two = patcher.build(ROM, root / 'assets', root / 'two.sfc', ASAR)
            self.assertEqual(one, two)
            for suffix in ('.sfc', '.ips', '.json'):
                self.assertEqual((root / ('one' + suffix)).read_bytes(), (root / ('two' + suffix)).read_bytes())
            rom = (root / 'one.sfc').read_bytes()
            ips = (root / 'one.ips').read_bytes()
            self.assertEqual(ips[:5], b'PATCH')
            rebuilt = bytearray(source)
            offset = 5
            while ips[offset:offset + 3] != b'EOF':
                target = int.from_bytes(ips[offset:offset + 3], 'big')
                size = int.from_bytes(ips[offset + 3:offset + 5], 'big')
                self.assertGreater(size, 0)
                offset += 5
                rebuilt.extend(bytes(max(0, target + size - len(rebuilt))))
                rebuilt[target:target + size] = ips[offset:offset + size]
                offset += size
            self.assertEqual(offset + 3, len(ips))
            self.assertEqual(bytes(rebuilt), rom)
            allowed = set(range(0x7FDC, 0x7FE0)) | set(range(patcher.HOOK, patcher.HOOK + 5)) | set(range(patcher.MUSIC_HOOK, patcher.MUSIC_HOOK + 3))
            self.assertTrue(all(before == after or index in allowed for index, (before, after) in enumerate(zip(source, rom))))
            self.assertEqual(rom[patcher.MUSIC_HOOK:patcher.MUSIC_HOOK + 3], patcher.NEW_MUSIC_HOOK)
            checksum = int.from_bytes(rom[0x7FDE:0x7FE0], 'little')
            self.assertEqual(sum(rom) & 0xFFFF, checksum)
        self.assertEqual(ROM.read_bytes(), source)
        self.assertEqual(hashlib.sha1(source).hexdigest(), patcher.SOURCE_SHA1)


if __name__ == '__main__':
    unittest.main()
