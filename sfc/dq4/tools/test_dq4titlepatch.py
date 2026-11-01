"""통합 타이틀의 색 소유 범위와 ROM 기록 경계를 검사한다."""

from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image

import dq4titleassets
import dq4titlepatch as patcher
from dq4romassets import CHECKSUM_OFFSET, apply_ips


def source_rom():
    """원본 머리·훅 바이트만 넣은 1.5MB 합성 롬."""
    rom = bytearray(0x180000)
    rom[0x7FD7] = 0x0B
    rom[patcher.HOOK:patcher.HOOK + 5] = patcher.ORIGINAL_HOOK
    rom[patcher.MUSIC_HOOK:patcher.MUSIC_HOOK + 3] = patcher.ORIGINAL_MUSIC_HOOK
    for i in range(0x100000, 0x180000, 0x1000):
        rom[i] = i >> 12 & 0xFF
    return bytes(rom)


class FakeAsar:
    """asar 자리에서 받은 입력(정의, 늘린 롬, 자료 파일)을 기록하고, 훅과 자료를 placements 대로 써 넣는다."""

    def __init__(self, placements, extra=(), returncode=0):
        self.placements, self.extra, self.returncode = placements, dict(extra), returncode
        self.defines, self.target = {}, None

    def __call__(self, command, **_):
        asm, target = Path(command[2]), Path(command[3])
        for line in asm.read_text().splitlines():
            if line.startswith('!'):
                name, value = line[1:].split(' = ')
                self.defines.setdefault(name, int(value))
        data = bytearray(target.read_bytes())
        self.target = bytes(data)
        data[patcher.HOOK:patcher.HOOK + 5] = patcher.NEW_HOOK
        data[patcher.MUSIC_HOOK:patcher.MUSIC_HOOK + 3] = patcher.NEW_MUSIC_HOOK
        data[0x180000:0x180004] = b'\x5c\x00\x80\x30'
        for name, offset in self.placements:
            blob = (asm.parent / name).read_bytes()
            data[offset:offset + len(blob)] = blob
        for offset, value in self.extra.items():
            data[offset] = value
        target.write_bytes(data)
        return subprocess.CompletedProcess(command, self.returncode, '', 'error' if self.returncode else '')


def run_build(module, rom, root, asar, **patches):
    """롬 SHA-1 을 합성 롬 것으로 두고, asar 실행만 asar 로 바꿔 build 를 돌린다."""
    source = root / 'source.sfc'
    source.write_bytes(rom)
    # module.subprocess.run 을 고치면 stdlib 모듈 자체가 바뀌어 다른 테스트로 번지므로, 모듈이 쥔 참조만 바꾼다
    fake_subprocess = SimpleNamespace(**vars(subprocess))
    fake_subprocess.run, fake_subprocess.check_output = asar, lambda *a, **k: 'Asar 1.91\n'
    fake_shutil = SimpleNamespace(**vars(shutil))
    fake_shutil.which = lambda name: '/fake/asar'
    with ExitStack() as stack:
        stack.enter_context(patch.object(module, 'SOURCE_SHA1', hashlib.sha1(rom).hexdigest()))
        stack.enter_context(patch.object(module, 'subprocess', fake_subprocess))
        stack.enter_context(patch.object(module, 'shutil', fake_shutil))
        for name, value in patches.items():
            stack.enter_context(patch.object(module, name, value))
        return module.build(source, root / 'assets', root / 'out' / 'title.sfc', 'asar')


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


BLOBS = {'title.chr': bytes(range(1, 33)) * 4, 'title.map': bytes([2]) * 2048, 'title.pal': bytes([3]) * 256}
STATIC = [('title.chr', 0x188000), ('title.map', 0x190000), ('title.pal', 0x190800), ('gleam.pal', 0x192000)]


class BuildAroundAsarTests(unittest.TestCase):
    """asar 앞(정의·늘린 롬·자료 파일)과 뒤(기록 범위·자료 자리·체크섬·IPS·보고)를 롬·asar 없이 본다."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)
        self.rom = source_rom()
        self.blobs = dict(BLOBS, **{'gleam.pal': BLOBS['title.pal'] * 32})
        self.assets = patch.object(patcher, 'read_assets', return_value=(dict(self.blobs), [5], [0] * 32))

    def build(self, asar):
        with self.assets:
            return run_build(patcher, self.rom, self.root, asar)

    def test_run_build_leaves_caller_patches_and_stdlib_alone(self):
        real_run, real_which = subprocess.run, shutil.which
        with self.assets as outer:
            run_build(patcher, self.rom, self.root, FakeAsar(STATIC))
            self.assertIs(patcher.read_assets, outer)
        self.assertIs(subprocess.run, real_run)
        self.assertIs(shutil.which, real_which)
        self.assertIs(patcher.subprocess, subprocess)

    def test_static_title_inputs_and_outputs(self):
        asar = FakeAsar(STATIC)
        report = self.build(asar)
        self.assertLessEqual({'chr_size': len(BLOBS['title.chr']), 'animation_enabled': 0, 'animation_frames': 8}.items(),
                             asar.defines.items())
        # asar 가 받는 롬은 원본 뒤에 원본 마지막 512KB 를 거울로 붙인 2MB
        self.assertEqual(asar.target, self.rom + self.rom[0x100000:])
        out = self.root / 'out' / 'title.sfc'
        rom = out.read_bytes()
        self.assertEqual(len(rom), 0x200000)
        for name, offset in STATIC:
            self.assertEqual(rom[offset:offset + len(self.blobs[name])], self.blobs[name])
        low, high = (int.from_bytes(rom[CHECKSUM_OFFSET + i:CHECKSUM_OFFSET + i + 2], 'little') for i in (0, 2))
        self.assertEqual(low ^ high, 0xFFFF)
        self.assertEqual(apply_ips(self.rom, out.with_suffix('.ips').read_bytes()), rom)
        saved = json.loads(out.with_suffix('.json').read_text())
        self.assertEqual(saved, json.loads(json.dumps(report)))
        self.assertEqual(report['rom_sha1'], hashlib.sha1(rom).hexdigest())
        self.assertEqual(report['gleam']['indices'], [5])
        self.assertEqual((self.root / 'source.sfc').read_bytes(), self.rom)

    def test_write_outside_declared_regions_leaves_no_output(self):
        for offset in (0x100, 0x181000, 0x188000 + len(BLOBS['title.chr'])):
            with self.subTest(offset=f'{offset:06X}'), self.assertRaisesRegex(ValueError, 'outside declared'):
                self.build(FakeAsar(STATIC, {offset: 0xA5}))
            self.assertFalse((self.root / 'out').exists())

    def test_missing_or_misplaced_asset_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'gleam.pal was not embedded'):
            self.build(FakeAsar(STATIC[:-1]))
        with self.assertRaisesRegex(ValueError, 'Asar failed'):
            self.build(FakeAsar(STATIC, returncode=1))
        self.assertFalse((self.root / 'out').exists())

    def test_animated_title_doubles_rom_and_places_frames_per_bank(self):
        frames = {f'frame{i:02d}.chr': bytes([0x10 + i]) * 0x7000 for i in range(3)}
        assets = self.root / 'assets'
        assets.mkdir()
        (assets / 'animation.json').write_text(json.dumps({'frame_count': 3}))
        asar = FakeAsar(STATIC + [(name, 0x198000 + i * 0x8000) for i, name in enumerate(frames)], {0x7FD7: 0x0C})
        import dq4titleanimation
        with patch.object(dq4titleanimation, 'read_pack', return_value={**BLOBS, **frames}):
            report = run_build(patcher, self.rom, self.root, asar)
        self.assertEqual(asar.defines['animation_enabled'], 1)
        self.assertEqual(asar.defines['animation_frames'], 3)
        mirrored = self.rom + self.rom[0x100000:]
        self.assertEqual(len(asar.target), 0x400000)
        self.assertEqual(asar.target[0x7FD7], 0x0C)
        self.assertEqual(asar.target[:0x7FD7] + asar.target[0x7FD8:], (mirrored * 2)[:0x7FD7] + (mirrored * 2)[0x7FD8:])
        rom = (self.root / 'out' / 'title.sfc').read_bytes()
        self.assertEqual(report['rom_bytes'], 0x400000)
        for i, (name, data) in enumerate(frames.items()):
            self.assertEqual(rom[0x198000 + i * 0x8000:0x198000 + i * 0x8000 + len(data)], data)
        # 정지 그림 팔레트를 32번 되풀이한 반짝임 표(색이 바뀌지 않음)
        self.assertEqual(rom[0x192000:0x194000], BLOBS['title.pal'] * 32)


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
