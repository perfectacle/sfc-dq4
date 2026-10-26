"""곡 삽입의 경계, 기존 재배치 보존과 IPL 길이를 검사한다."""
import os
from pathlib import Path
import unittest

import dq4soundpatch as patch
from dq5song import assemble
from dq5map import lorom

ROOT = Path(__file__).resolve().parents[3]
ROM = ROOT / 'rom/dq5.sfc'


def melody(instrument=0):
    return assemble(['tempo 78', 'track L0', 'L0:', f'  instrument {instrument:02X}',
                     '  volume 30', '  volume2 FF', '  release 14', '  note 30 len 30', '  jump L0'])


class SequenceValidationTests(unittest.TestCase):
    def test_rejects_instrument_without_sample(self):
        with self.assertRaisesRegex(ValueError, 'instrument index'):
            patch.validate_replacement(patch.Replacement(melody(1), (0x18,)))

    def test_rejects_out_of_range_jump(self):
        seq = bytearray(melody())
        seq[-2:] = b'\xff\x7f'
        with self.assertRaisesRegex(ValueError, 'target outside'):
            patch.validate_replacement(patch.Replacement(bytes(seq), (0x18,)))

    def test_rejects_eight_voice_bgm(self):
        with self.assertRaisesRegex(ValueError, '1..7 voices'):
            patch.validate_replacement(patch.Replacement(bytes([120, 8, 0, 0]), (0x18,)))


@unittest.skipUnless(ROM.exists(), 'user-supplied DQ5 ROM required')
class InstallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = ROM.read_bytes()
        cls.item = patch.Replacement(melody(), (0x18,))

    def test_relocated_sequence_and_table_are_readable(self):
        out, report = patch.install(self.base, {2: self.item})
        self.assertEqual(patch.sequence_bytes(out, 2), self.item.sequence)
        records = patch.read_sets(out)
        self.assertEqual(records[2], bytes([1, 1, 0x18]))
        self.assertEqual(records[0x10], patch.read_sets(self.base)[0x10])
        start = lorom(patch.IPL_BLOCK)
        block = int.from_bytes(out[start:start + 2], 'little')
        self.assertEqual(start + 4 + block, lorom(patch.SONG_SETS) + sum(map(len, records)))
        self.assertLessEqual(report['songs'][0]['spc_budget']['bytes_with_margin'], patch.SPC_CAPACITY)

    def test_rejects_title_replacement(self):
        with self.assertRaisesRegex(ValueError, 'protected title'):
            patch.install(self.base, {0x10: self.item})

    def test_table_expansion_does_not_overrun_spc_area(self):
        wide = patch.Replacement(melody(), tuple(range(19)))
        with self.assertRaisesRegex(ValueError, 'SPC budget exceeded'):
            patch.install(self.base, {2: wide, 5: wide})

    def test_table_growth_moves_heap_start(self):
        # 표가 28EC~2A5D 를 넘으면 샘플 자리 시작($28E7)이 표 끝으로 밀리고 예산도 그만큼 준다.
        wide = patch.Replacement(melody(), (0x00, 0x05, 0x1F, 0x20, 0x21, 0x22, 0x03, 0x04, 0x18, 0x13, 0x0A, 0x0B, 0x15, 0x16))
        out, report = patch.install(self.base, {2: wide})
        table = sum(map(len, patch.read_sets(out)))
        self.assertGreater(table, patch.TABLE_CAPACITY)
        self.assertEqual(patch.heap_start(out), 0x28EC + table)
        self.assertEqual(report['songs'][0]['spc_budget']['capacity'], patch.SPC_END - 0x28EC - table)

    def test_table_within_capacity_keeps_heap_start(self):
        out, _ = patch.install(self.base, {2: self.item})
        self.assertEqual(patch.heap_start(out), 0x2A5D)

    def test_occupied_allocation_is_not_overwritten(self):
        base = bytearray(self.base) + bytes(0x400000 - len(self.base))
        base[lorom(0x728000)] = 0x12
        with self.assertRaisesRegex(ValueError, 'already occupied'):
            patch.install(bytes(base), {2: self.item})

    def test_unknown_map_hook_is_rejected(self):
        base = bytearray(self.base)
        base[lorom(patch.MAP_START)] ^= 1
        with self.assertRaisesRegex(ValueError, 'incompatible base'):
            patch.install(bytes(base), {2: self.item}, map_fades=True)

    def test_custom_sample_uses_free_pointer_and_required_resource(self):
        item = patch.Replacement(melody(), (0x26,))
        with self.assertRaisesRegex(ValueError, 'no resource supplied'):
            patch.install(self.base, {2: item})
        body = bytes.fromhex('00 00 8F E0 00 00 10') + bytes([1]) + bytes(8)
        resource = len(body).to_bytes(2, 'little') + body
        out, _ = patch.install(self.base, {2: item}, sample_resources={0x26: resource})
        pos = lorom(patch.RELOC_SMP_TABLE) + 0x26 * 3
        addr = int.from_bytes(out[pos:pos + 3], 'little')
        self.assertEqual(out[lorom(addr):lorom(addr) + len(resource)], resource)
        self.assertEqual(patch.sample_size(out, 0x26), len(body))

    def test_custom_sample_cannot_replace_native_instrument(self):
        with self.assertRaisesRegex(ValueError, 'free IDs'):
            patch.install(self.base, {2: self.item}, sample_resources={0: bytes(18)})

    def test_battle_calls_are_untouched_by_map_fades(self):
        out, _ = patch.install(self.base, {2: self.item}, map_fades=True)
        for address in (0x268F49, 0x268F91, 0x2080DF):
            pos = lorom(address)
            self.assertEqual(out[pos:pos + 4], self.base[pos:pos + 4])
        self.assertEqual(out[lorom(patch.MAP_START):lorom(patch.MAP_START) + 4], bytes.fromhex('22 80 80 71'))

    def test_map_hooks_never_wait_for_frames(self):
        # 맵을 불러올 때는 NMI 가 꺼져 있어 프레임 기다림(24:FE44, 00:9506)을 부르면 멈춘다.
        for code in patch.transition_code():
            for call in ('22 44 FE 24', '22 06 95 00', '20 9A 96'):
                self.assertNotIn(bytes.fromhex(call), code)

    def test_fade_in_replaces_start_only_when_song_changes(self):
        _, start = patch.transition_code()
        self.assertIn(bytes.fromhex('22 A3 FE 24'), start)
        self.assertTrue(start.endswith(bytes.fromhex('5C 9A FE 24')))


@unittest.skipUnless(os.environ.get('DQ4_SOUND_BASE'), 'DQ4_SOUND_BASE supplies accepted integrated build')
class IntegratedTests(unittest.TestCase):
    def test_existing_title_sequence_and_stubs_are_preserved(self):
        base = Path(os.environ['DQ4_SOUND_BASE']).read_bytes()
        out, _ = patch.install(base, {2: patch.Replacement(melody(), (0x18,))}, map_fades=True)
        self.assertEqual(patch.sequence_bytes(out, 0x10), patch.sequence_bytes(base, 0x10))
        for address, size in ((0x70FF00, 0x40), (0x30801C, 6), (0x30FF00, 24), (0x00A709, 6)):
            pos = lorom(address)
            self.assertEqual(out[pos:pos + size], base[pos:pos + size])


if __name__ == '__main__':
    unittest.main()
