"""층 타이틀 패치의 asar 앞(정의·4MB 롬)과 뒤(예약 범위·자료 자리·IPS)를 롬·asar 없이 검사한다."""
import shutil
import tempfile
import unittest
from pathlib import Path

import dq4titlelayerpatch as layerpatch
from dq4romassets import apply_ips
from test_dq4titlepatch import FakeAsar, run_build, source_rom


def blobs():
    """자리마다 다른 값으로 채운 작은 자료. 크기는 다음 자리까지의 틈보다 작다."""
    return {name: bytes([i + 1]) * (0x10 + i) for i, name in enumerate(layerpatch.PLACEMENTS)}


class LayerBuildTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)
        self.rom = source_rom()

    def build(self, asar, data=None, assets=None):
        pack = (data or blobs(), assets or {'cloud_sprite_count': 9})
        return run_build(layerpatch, self.rom, self.root, asar, read_pack=lambda source: pack)

    def test_inputs_and_outputs(self):
        data = blobs()
        asar = FakeAsar(list(layerpatch.PLACEMENTS.items()))
        report = self.build(asar, data)
        self.assertEqual(asar.defines['background_chr_size'], len(data['background.chr']))
        self.assertEqual(asar.defines['foreground_chr_size'], len(data['foreground.chr']))
        expected = bytearray(self.rom + self.rom[0x100000:] + bytes(layerpatch.ROM_SIZE - 0x200000))
        expected[0x7FD7] = 0x0C
        self.assertEqual(asar.target, bytes(expected))
        out = self.root / 'out' / 'title.sfc'
        rom = out.read_bytes()
        self.assertEqual(len(rom), layerpatch.ROM_SIZE)
        for name, offset in layerpatch.PLACEMENTS.items():
            self.assertEqual(rom[offset:offset + len(data[name])], data[name])
        self.assertEqual(apply_ips(self.rom, out.with_suffix('.ips').read_bytes()), rom)
        self.assertEqual(report['assets'], {'cloud_sprite_count': 9})
        for row in report['changed_ranges']:
            self.assertLess(int(row['file_offset'], 16), layerpatch.ROM_SIZE)

    def test_overlapping_assets_are_caught(self):
        # 배경 맵이 앞 맵 자리(215000)에서 넘쳐 전경 맵(216000)을 덮으면, 범위는 합쳐져도 자료 비교에서 걸린다
        data = blobs()
        data['background.map'] = bytes([0xEE]) * 0x1100
        with self.assertRaisesRegex(ValueError, 'embedded asset mismatch'):
            self.build(FakeAsar(list(layerpatch.PLACEMENTS.items())), data)
        self.assertFalse((self.root / 'out').exists())

    def test_writes_outside_reserved_ranges_and_bad_packs_are_rejected(self):
        placements = list(layerpatch.PLACEMENTS.items())
        size = len(blobs()['background.chr'])
        for offset in (0x7FD8, 0x181000, 0x210000 + size, 0x3FFFFF):
            with self.subTest(offset=f'{offset:06X}'), self.assertRaisesRegex(ValueError, 'outside reserved'):
                self.build(FakeAsar(placements, {offset: 0x77}))
        with self.assertRaisesRegex(ValueError, 'nine 32px'):
            self.build(FakeAsar(placements), assets={'cloud_sprite_count': 8})
        with self.assertRaisesRegex(ValueError, 'Asar failed'):
            self.build(FakeAsar(placements, returncode=1))
        self.assertFalse((self.root / 'out').exists())

    def test_wrong_source_header_stops_before_asar(self):
        rom = bytearray(self.rom)
        rom[0x7FD7] = 0x0C
        self.rom = bytes(rom)
        asar = FakeAsar(list(layerpatch.PLACEMENTS.items()))
        with self.assertRaisesRegex(ValueError, 'header or hook'):
            self.build(asar)
        self.assertIsNone(asar.target)


class LayerLayoutTests(unittest.TestCase):
    def test_hooks_and_header_are_required(self):
        original = source_rom()
        data = blobs()
        rom = bytearray(original + original[0x100000:] + bytes(layerpatch.ROM_SIZE - 0x200000))
        with self.assertRaisesRegex(ValueError, 'layout, header or hooks'):
            layerpatch.verify_layout(original, bytes(rom), data)


if __name__ == '__main__':
    unittest.main()
