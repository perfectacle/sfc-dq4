import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

import numpy as np

import dq4titlelayers as layers
import dq4titlelayerpatch as patch
from dq4titleassets import DEFAULT_SOURCE, native_title
from dq4romassets import apply_ips


class LayerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.pack = Path(cls.temp.name) / 'pack'
        layers.write_pack(cls.pack)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def copy_pack(self, root):
        target = Path(root) / 'assets'
        shutil.copytree(self.pack, target)
        return target

    def replace_blob(self, source, name, data):
        (source / name).write_bytes(data)
        manifest = json.loads((source / 'layers.json').read_text())
        manifest['files'][name] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        (source / 'layers.json').write_text(json.dumps(manifest))

    def test_two_cycles_and_budgets(self):
        blobs, report = layers.read_pack(self.pack)
        self.assertLessEqual(report['max_delta_bytes'] + 544, 4096)
        self.assertLessEqual(report['max_runs'], 31)
        self.assertEqual(len(blobs['dragon-initial.chr']), 16384)
        self.assertGreater(len({row['chr_sha256'] for row in report['frames']}), 100)

    def test_foreground_rgb_and_opaque_black(self):
        blobs, _ = layers.read_pack(self.pack)
        tiles = layers.decode_tiles(blobs['foreground.chr'], 8)
        mapping = np.frombuffer(blobs['foreground.map'], dtype='<u2').reshape(32, 32)
        pixels = tiles[mapping & 1023].transpose(0, 2, 1, 3).reshape(256, 256)[:224]
        original = native_title(DEFAULT_SOURCE)
        palette = np.array(original.getpalette()[:384]).reshape(128, 3)
        mask = np.frombuffer(blobs['foreground-mask.bin'], dtype=np.uint8).reshape(224, 256) > 0
        self.assertTrue(np.array_equal(palette[pixels][mask], np.array(original.convert('RGB'))[mask]))
        self.assertTrue(np.all(pixels[mask] != 0))
        self.assertTrue(np.all(pixels[~mask] == 0))
        self.assertTrue(np.all((mapping & 0x2000) != 0))

    def test_unused_oam_hidden_and_page_parity(self):
        for phase in (0, 1, 127):
            oam = layers.oam_frame(phase)
            for sprite in range(128):
                high = oam[512 + sprite // 4] >> (sprite % 4 * 2) & 3
                if sprite < 15:
                    self.assertEqual(high, 0)
                    self.assertEqual(oam[sprite * 4 + 3] & 1, phase & 1)
                else:
                    self.assertEqual(high, 1)
                    self.assertEqual(oam[sprite * 4 + 1], 224)

    def test_descriptor_rejects_visible_page_and_bank_crossing(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.copy_pack(directory)
            data = bytearray((source / 'dragon-dma.bin').read_bytes())
            data[:2] = (0x5000).to_bytes(2, 'little')
            self.replace_blob(source, 'dragon-dma.bin', bytes(data))
            with self.assertRaisesRegex(ValueError, 'hidden OBJ'):
                layers.read_pack(source)
        with tempfile.TemporaryDirectory() as directory:
            source = self.copy_pack(directory)
            data = bytearray((source / 'dragon-dma.bin').read_bytes())
            data[2:4] = bytes.fromhex('f0ff')
            self.replace_blob(source, 'dragon-dma.bin', bytes(data))
            with self.assertRaisesRegex(ValueError, 'bank'):
                layers.read_pack(source)

    def test_bad_map_palette_foreground_and_hash_rejected(self):
        for name in ('background.map', 'background.pal', 'foreground.chr', 'dragon.pal'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                source = self.copy_pack(directory)
                data = bytearray((source / name).read_bytes())
                data[:2] = b'\xff\xff'
                self.replace_blob(source, name, bytes(data))
                with self.assertRaises(ValueError):
                    layers.read_pack(source)
        with tempfile.TemporaryDirectory() as directory:
            source = self.copy_pack(directory)
            (source / 'dragon-dma.bin').write_bytes(bytes(32768))
            with self.assertRaisesRegex(ValueError, 'hash'):
                layers.read_pack(source)

    def test_determinism_and_output_alias_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'repeat'
            layers.write_pack(target)
            for name in ('layers.json', 'background.chr', 'foreground.chr', 'layer-payload.bin', 'dragon-dma.bin'):
                self.assertEqual((target / name).read_bytes(), (self.pack / name).read_bytes())
            (target / 'foreground.chr').unlink()
            os.link(target / 'background.chr', target / 'foreground.chr')
            before = (target / 'background.chr').read_bytes()
            with self.assertRaisesRegex(ValueError, 'alias'):
                layers.write_pack(target)
            self.assertEqual((target / 'background.chr').read_bytes(), before)

    def test_rom_build_ips_and_original_unchanged(self):
        asar = os.environ.get('ASAR')
        rom = Path('rom/dq5.sfc')
        if not asar or not rom.exists():
            self.skipTest('local source ROM and ASAR required')
        original = rom.read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'title.sfc'
            first = patch.build(rom, self.pack, output, asar)
            data = output.read_bytes()
            self.assertEqual(len(data), 0x200000)
            self.assertEqual(data[0x7FD7], original[0x7FD7])
            self.assertEqual(apply_ips(original, output.with_suffix('.ips').read_bytes()), data)
            second = patch.build(rom, self.pack, output, asar)
            self.assertEqual(first['rom_sha1'], second['rom_sha1'])
            mutated = bytearray(data)
            mutated[0x1000] ^= 1
            blobs, _ = layers.read_pack(self.pack)
            with self.assertRaisesRegex(ValueError, 'reserved'):
                patch.verify_layout(original, bytes(mutated), blobs)
        self.assertEqual(rom.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
