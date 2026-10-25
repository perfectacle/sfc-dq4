"""분리된 타이틀 애니메이션의 고정 글자·루프·ROM 확장 경계를 검사한다."""

import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import numpy as np
from PIL import Image

import dq4titleanimation as animation
from dq4romassets import apply_ips, ips_patch, set_checksum
from dq4titleassets import DEFAULT_SOURCE, native_title
import dq4titlepatch


class AnimationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.root = Path(cls.directory.name)
        cls.original = native_title(DEFAULT_SOURCE)
        cls.layout = json.loads((animation.ART / 'dragon-layout-8.json').read_text())
        cls.rgb, cls.mask = animation.compose_frames(cls.original, cls.layout)
        cls.frames, cls.banks = animation.quantize_frames(cls.rgb, cls.original, cls.mask)
        cls.report = animation.write_pack(cls.root / 'pack', cls.frames, cls.banks, cls.original, cls.mask, layout=cls.layout)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def temporary_pack(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        target = Path(directory.name) / 'pack'
        shutil.copytree(self.root / 'pack', target)
        return target

    def test_fixed_logo_and_real_motion_roundtrip(self):
        blobs = animation.read_pack(self.root / 'pack')
        mask = np.array(self.mask) != 0
        original = np.array(self.original)
        self.assertEqual(len(self.frames), 64)
        self.assertEqual(self.report['dragon_pose_count'], 8)
        self.assertEqual(len({hashlib.sha256(blobs[f'frame{i:02d}.chr']).hexdigest() for i in range(64)}), 64)
        for index, expected in enumerate(self.frames):
            actual = animation.decode_frame(blobs[f'frame{index:02d}.chr'], self.banks)
            self.assertTrue(np.array_equal(actual, expected))
            self.assertTrue(np.array_equal(actual[mask], original[mask]))
        changed_top = np.count_nonzero(self.frames[0][:80] != self.frames[8][:80])
        changed_clouds = np.count_nonzero(self.frames[0][194:] != self.frames[1][194:])
        self.assertGreater(changed_top, 1000)
        self.assertGreater(changed_clouds, 100)

    def test_shared_palette_and_frame_generation_are_deterministic(self):
        rgb, mask = animation.compose_frames(self.original, self.layout)
        frames, banks = animation.quantize_frames(rgb, self.original, mask)
        self.assertTrue(np.array_equal(self.banks, banks))
        self.assertTrue(all(np.array_equal(left, right) for left, right in zip(self.frames, frames)))
        self.assertEqual(animation.title_map(self.banks), (self.root / 'pack/title.map').read_bytes())

    def test_cloud_period_is_exact_without_pingpong(self):
        with Image.open(animation.ART / 'cloud-strip.png') as source:
            cloud = source.convert('RGBA')
        for period, height in ((64, 20), (128, 40)):
            strip = animation.cloud_strip(cloud, period, height)
            self.assertEqual(strip.crop((0, 0, 1, height)).tobytes(), strip.crop((period - 1, 0, period, height)).tobytes())
            first, wrapped = Image.new('RGBA', (256, 224)), Image.new('RGBA', (256, 224))
            animation.cloud_layer(first, strip, 0, 40, 0.5)
            animation.cloud_layer(wrapped, strip, period, 40, 0.5)
            self.assertEqual(first.tobytes(), wrapped.tobytes())

    def test_hash_and_frame_count_mutations_are_rejected(self):
        pack = self.temporary_pack()
        data = bytearray((pack / 'frame00.chr').read_bytes())
        data[0] ^= 1
        (pack / 'frame00.chr').write_bytes(data)
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            animation.read_pack(pack)
        pack = self.temporary_pack()
        report = json.loads((pack / 'animation.json').read_text())
        report['frame_count'] = 63
        (pack / 'animation.json').write_text(json.dumps(report))
        with self.assertRaisesRegex(ValueError, 'frame count'):
            animation.read_pack(pack)

    def test_tilemap_and_logo_mutations_cannot_be_hidden_by_new_hashes(self):
        pack = self.temporary_pack()
        data = bytearray((pack / 'title.map').read_bytes())
        data[1] ^= 0x40
        (pack / 'title.map').write_bytes(data)
        report = json.loads((pack / 'animation.json').read_text())
        report['files']['title.map'] = hashlib.sha256(data).hexdigest()
        (pack / 'animation.json').write_text(json.dumps(report))
        with self.assertRaisesRegex(ValueError, 'row-major'):
            animation.read_pack(pack)
        pack = self.temporary_pack()
        data = bytearray((pack / 'frame02.chr').read_bytes())
        x, y = 120, 120
        self.assertTrue(np.array(self.mask)[y, x])
        data[((y // 8) * 32 + x // 8) * 32 + (y % 8) * 2] ^= 1 << (7 - x % 8)
        (pack / 'frame02.chr').write_bytes(data)
        report = json.loads((pack / 'animation.json').read_text())
        report['files']['frame02.chr'] = hashlib.sha256(data).hexdigest()
        (pack / 'animation.json').write_text(json.dumps(report))
        with self.assertRaisesRegex(ValueError, 'protected logo'):
            animation.read_pack(pack)

    def test_output_alias_and_layout_source_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            first = output / 'frame00.chr'
            first.write_bytes(b'keep')
            (output / 'frame01.chr').hardlink_to(first)
            with self.assertRaisesRegex(ValueError, 'alias'):
                animation.write_pack(output, self.frames, self.banks, self.original, self.mask)
            self.assertEqual(first.read_bytes(), b'keep')
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            layout = output / 'animation.json'
            layout.write_text('{}')
            with self.assertRaisesRegex(ValueError, 'source art'):
                animation.write_pack(output, self.frames, self.banks, self.original, self.mask, extra_inputs=[layout])
            self.assertEqual(layout.read_text(), '{}')

    def test_four_mib_checksum_ips_and_exact_layout_bounds(self):
        original = bytes(0x180000)
        blobs = animation.read_pack(self.root / 'pack')
        blobs['gleam.pal'] = blobs['title.pal'] * 32
        rom = bytearray(0x400000)
        rom[0x7FD7] = 0x0C
        rom[dq4titlepatch.HOOK:dq4titlepatch.HOOK + 5] = dq4titlepatch.NEW_HOOK
        rom[dq4titlepatch.MUSIC_HOOK:dq4titlepatch.MUSIC_HOOK + 3] = dq4titlepatch.NEW_MUSIC_HOOK
        placements = [('title.chr', 0x188000), ('title.map', 0x190000), ('title.pal', 0x190800), ('gleam.pal', 0x192000)]
        placements += [(f'frame{i:02d}.chr', 0x198000 + i * 0x8000) for i in range(64)]
        for name, offset in placements:
            rom[offset:offset + len(blobs[name])] = blobs[name]
        fixed = set_checksum(rom)
        self.assertEqual(sum(fixed) & 0xFFFF, int.from_bytes(fixed[0x7FDE:0x7FE0], 'little'))
        self.assertEqual(apply_ips(original, ips_patch(original, fixed)), fixed)
        dq4titlepatch.verify_layout(original, fixed, blobs)
        rom = bytearray(fixed)
        rom[0x19F000] ^= 1
        with self.assertRaisesRegex(ValueError, 'outside declared'):
            dq4titlepatch.verify_layout(original, rom, blobs)


if __name__ == '__main__':
    unittest.main()
