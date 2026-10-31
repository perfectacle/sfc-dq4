"""곡 삽입의 경계, 기존 재배치 보존과 IPL 길이를 검사한다."""
from functools import cache
import os
from pathlib import Path
import unittest
from unittest import mock

import dq4soundpatch as patch
import dq5brrenc as brr
from dq5song import assemble
from dq5map import lorom
from dq5spc import RESIDENT_SAMPLES, SAMPLE_COUNT, SAMPLES, SEQUENCE_COUNT, SEQUENCES

ROOT = Path(__file__).resolve().parents[3]
ROM = ROOT / 'rom/dq5.sfc'


def melody(instrument=0):
    return assemble(['tempo 78', 'track L0', 'L0:', f'  instrument {instrument:02X}',
                     '  volume 30', '  volume2 FF', '  release 14', '  note 30 len 30', '  jump L0'])


def chained(data, start, sizes, fill):
    pos = lorom(start)
    for size in sizes:
        data[pos:pos + 2 + size] = size.to_bytes(2, 'little') + bytes([fill]) * size
        pos += 2 + size


@cache
def synthetic_base():
    """롬 없이 install 을 돌릴 2MB 합성 롬. 표 모양만 DQ5 와 같고 샘플·시퀀스 내용은 채움 바이트다.

    곡 묶음 표는 365바이트로, 곡 하나에 샘플을 열 개 넘게 붙이면 원래 자리(TABLE_CAPACITY)를 넘게 했다.
    패치 자리의 원래 바이트는 install 이 put 에 넘기는 기대값을 그대로 심는다(도구 상수뿐, 롬 자료가 아님).
    """
    data = bytearray(0x200000)
    chained(data, SAMPLES, [0x200] * SAMPLE_COUNT, 0x11)
    chained(data, SEQUENCES, [0x40] * SEQUENCE_COUNT, 0x22)
    records = [bytes([4 if song < 10 else 3, 1, 0x01, 0x02, 0x03, 0x04][:6 if song < 10 else 5])
               for song in range(SEQUENCE_COUNT)]
    table = b''.join(records)
    data[lorom(patch.SONG_SETS):lorom(patch.SONG_SETS) + len(table) + 4] = table + patch.IPL_END
    data[lorom(patch.IPL_BLOCK):lorom(patch.IPL_BLOCK) + 2] = (
        lorom(patch.SONG_SETS) + len(table) - lorom(patch.IPL_BLOCK) - 4).to_bytes(2, 'little')
    data[lorom(patch.HEAP_START):lorom(patch.HEAP_START) + 2] = (0x2A5D).to_bytes(2, 'little')
    data[lorom(RESIDENT_SAMPLES):lorom(RESIDENT_SAMPLES) + 7] = bytes([0x00, 0x05, 0x1F, 0x22, 0x20, 0x21, 0xFF])
    data[lorom(patch.RESIDENT_SEQUENCES):lorom(patch.RESIDENT_SEQUENCES) + 4] = bytes([0x17, 0x32, 0x33, 0xFF])
    data[lorom(patch.RESIDENT_SAMPLE_LOAD):lorom(patch.RESIDENT_SAMPLE_LOAD) + 4] = (
        bytes([0xBF]) + RESIDENT_SAMPLES.to_bytes(3, 'little'))
    data[lorom(0x2BC3AB):lorom(0x2BC3AB) + 5] = bytes.fromhex('48 DA 29 FF 00')

    expected = {}

    def record(data, addr, payload, expected_bytes=None, empty=False):
        if expected_bytes is not None:
            assert expected.setdefault(addr, bytes(expected_bytes)) == expected_bytes, f'{addr:06X}'
        data[lorom(addr):lorom(addr) + len(payload)] = payload

    with mock.patch.object(patch, 'put', record):
        for options in ({'fast_receive': True, 'hold': True, 'early_song': True, 'load_pump': True,
                         'keep_samples': True, 'release_failed': True, 'vehicle_song': True,
                         'release_pending': True},
                        {'map_fades': True}):
            patch.install(bytes(data), {0x48: patch.Replacement(melody(), (0x03,))}, **options)
    for addr, raw in expected.items():
        data[lorom(addr):lorom(addr) + len(raw)] = raw
    return bytes(data)


class SequenceValidationTests(unittest.TestCase):
    def test_rejects_instrument_without_sample(self):
        with self.assertRaisesRegex(ValueError, 'instrument index'):
            patch.validate_replacement(patch.Replacement(melody(1), (0x18,)))

    def test_rejects_out_of_range_jump(self):
        seq = bytearray(melody())
        seq[-2:] = b'\xff\x7f'
        with self.assertRaisesRegex(ValueError, 'target outside'):
            patch.validate_replacement(patch.Replacement(bytes(seq), (0x18,)))

    def test_rejects_send_first_beyond_sample_count(self):
        with self.assertRaisesRegex(ValueError, 'send_first'):
            patch.validate_replacement(patch.Replacement(melody(), (0x18,), send_first=2))

    def test_unpin_removes_song_and_pads_with_ff(self):
        data = bytearray(0x180000)
        pos = lorom(patch.RESIDENT_SEQUENCES)
        data[pos:pos + 5] = bytes.fromhex('00 17 1D 32 FF')
        self.assertEqual(patch.unpin_sequences(data, {0x17, 0x02}), [0x17])
        self.assertEqual(bytes(data[pos:pos + 5]), bytes.fromhex('00 1D 32 FF FF'))

    def test_rejects_eight_voice_bgm(self):
        with self.assertRaisesRegex(ValueError, '1..7 voices'):
            patch.validate_replacement(patch.Replacement(bytes([120, 8, 0, 0]), (0x18,)))


class InstallTests(unittest.TestCase):
    load = staticmethod(synthetic_base)

    @classmethod
    def setUpClass(cls):
        cls.base = cls.load()
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

    def test_send_first_and_unpinned_resident_song(self):
        self.assertIn(0x17, patch.pinned_sequences(self.base))
        item = patch.Replacement(melody(), (0x18, 0x00), send_first=1)
        out, report = patch.install(self.base, {0x17: item})
        self.assertEqual(patch.read_sets(out)[0x17], bytes([2, 1, 0x18, 0x00]))
        self.assertNotIn(0x17, patch.pinned_sequences(out))
        self.assertEqual(len(patch.pinned_sequences(out)), len(patch.pinned_sequences(self.base)) - 1)
        self.assertEqual(report['unpinned_sequences'], ['17'])
        self.assertEqual(report['songs'][0]['send_first'], 1)

    def test_pinned_song_resident_samples_and_record_override(self):
        item = patch.Replacement(melody(), (0x18,))
        out, report = patch.install(self.base, {0x17: item}, pinned={0x17}, resident=[0x18, 0x05, 0x1F, 0x22, 0x20, 0x21],
                                    set_records={0x1D: (2, 0x1F, 0x05)})
        self.assertIn(0x17, patch.pinned_sequences(out))
        self.assertEqual(report['unpinned_sequences'], [])
        self.assertEqual(patch.resident_samples(out), [0x18, 0x05, 0x1F, 0x22, 0x20, 0x21])
        self.assertEqual(patch.resident_samples(self.base), [0x00, 0x05, 0x1F, 0x22, 0x20, 0x21])
        self.assertEqual(patch.read_sets(out)[0x1D], bytes([2, 2, 0x1F, 0x05]))
        self.assertEqual(report['songs'][0]['spc_budget']['streamed_while_playing'], [])

    def test_resident_wave_replaces_only_a_resident_effect_wave_no_larger_than_before(self):
        small = brr.resource(bytes(18), 1, pitch=0x0831)
        out, _ = patch.install(self.base, {2: self.item}, resident_waves={0x20: small})
        self.assertEqual(patch.sample_size(out, 0x20), len(small) - 2)
        with self.assertRaises(ValueError):
            big = brr.resource(bytes(patch.sample_size(self.base, 0x20)), 1)
            patch.install(self.base, {2: self.item}, resident_waves={0x20: big})
        with self.assertRaises(ValueError):
            patch.install(self.base, {2: self.item}, resident_waves={0x05: small})

    def test_fast_receive_adds_ff00_block_and_driver_jump(self):
        out, report = patch.install(self.base, {0x02: patch.Replacement(melody(), (0x03,))}, fast_receive=True)
        self.assertTrue(report['fast_receive'])
        records = patch.read_sets(out)
        self.assertEqual(records[0x02], bytes([1, 1, 0x03]))
        at = lorom(patch.SONG_SETS) + sum(map(len, records))
        code = patch.fast_receive_code()
        self.assertEqual(out[at:at + 4], len(code).to_bytes(2, 'little') + bytes([0x00, 0xFF]))
        self.assertEqual(out[at + 4:at + 4 + len(code)], code)
        self.assertEqual(out[at + 4 + len(code):at + 8 + len(code)], patch.IPL_END)
        drv = lorom(patch.DRIVER_BLOCK) + 4 + patch.DRIVER_RECEIVE - 0x0750
        self.assertEqual(out[drv:drv + 3], bytes([0x5F, 0x00, 0xFF]))
        self.assertEqual(self.base[drv:drv + 3], bytes.fromhex('CD 00 E5'))
        with self.assertRaisesRegex(ValueError, 'already has the fast receive'):
            patch.install(out, {0x02: patch.Replacement(melody(), (0x03,))})

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
        base[lorom(patch.DATA_BANKS[0] << 16 | 0x8000)] = 0x12
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


    def test_weapon_sounds_hook_the_type_lookup_and_fill_both_tables(self):
        base = bytearray(self.base)
        site = lorom(patch.WEAPON_SOUND_SITE)
        base[site:site + len(patch.WEAPON_SOUND_ORIGINAL)] = patch.WEAPON_SOUND_ORIGINAL
        sounds = {0x06: (0x43, 0x04), 0x0C: (0x42, 0x02), patch.BARE_HANDS: (0x43, 0x00)}
        out, report = patch.install(bytes(base), {2: self.item}, weapon_sounds=(sounds, (0x17,)))
        self.assertEqual(out[site:site + 5], bytes([0x5C]) + patch.WEAPON_SOUND.to_bytes(3, 'little') + bytes([0xEA]))
        seq = lorom(patch.WEAPON_SEQ_TABLE)
        branch = lorom(patch.WEAPON_BRANCH_TABLE)
        self.assertEqual((out[seq + 0x06], out[branch + 0x06]), (0x43, 0x04))
        self.assertEqual((out[seq + 0x0C], out[branch + 0x0C]), (0x42, 0x02))
        self.assertEqual(out[seq + 0x07], 0xFF)    # 표에 없는 무기는 DQ5 종류별 소리
        self.assertEqual(report['weapon_sounds']['items']['80'], '43-00')

    def test_effect_calls_change_only_the_effect_number_of_brk_calls(self):
        base = bytearray(self.base)
        at = lorom(0x2589C5)
        base[at:at + 4] = bytes.fromhex('00 16 35 00')
        out, _ = patch.install(bytes(base), {2: self.item}, effect_calls={0x2589C5: (0x35, 0x3F)})
        self.assertEqual(out[at:at + 4], bytes.fromhex('00 16 3F 00'))
        with self.assertRaises(ValueError):
            patch.install(bytes(base), {2: self.item}, effect_calls={0x2589C5: (0x34, 0x3F)})


@unittest.skipUnless(ROM.exists(), 'user-supplied DQ5 ROM required')
class RealRomInstallTests(InstallTests):
    load = staticmethod(ROM.read_bytes)


class WeaponSoundCodeTests(unittest.TestCase):
    def test_code_plays_through_the_original_call_or_resumes_the_type_lookup(self):
        code = patch.weapon_sound_code((0x43, 0x00), [0x17])
        self.assertIn(bytes.fromhex('AF 8B 1D 7E C9 17'), code)                          # 지금 곡이 17 일 때만
        self.assertIn(bytes([0x5C]) + patch.WEAPON_PLAY.to_bytes(3, 'little'), code)     # 28:804A 로 소리
        self.assertTrue(code.endswith(patch.WEAPON_SOUND_ORIGINAL + bytes([0x5C]) + patch.WEAPON_RESUME.to_bytes(3, 'little')))
        self.assertIn(bytes.fromhex('A9 43 85 71 A9 00 85 72'), code)                    # 맨손

    def test_tables_reject_bare_hands_and_bad_branches(self):
        with self.assertRaises(ValueError):
            patch.weapon_tables({patch.BARE_HANDS: (0x43, 0)})
        with self.assertRaises(ValueError):
            patch.weapon_tables({0x06: (0x43, 0x21)})


class TransitionCodeTests(unittest.TestCase):
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


class EngineCodeTests(unittest.TestCase):
    def test_spc_hold_code_fits_its_ram(self):
        self.assertLessEqual(patch.HOLD_VARS + 5, patch.CHAIN_HANDLER)
        self.assertLessEqual(patch.CHAIN_HANDLER + len(patch.chain_code()), patch.HOLD_CHECK)
        self.assertLessEqual(patch.HOLD_CHECK + len(patch.hold_check_code()), 0x10000)
        check, end = patch.hold_spare_code()
        self.assertLessEqual(len(check) + len(end), 0x106B - patch.HOLD_SPARE)
        self.assertLessEqual(patch.FAST_RECEIVE + len(patch.fast_receive_code()), patch.HOLD_VARS)

    def test_load_pump_sites_do_not_overlap(self):
        spans = sorted((at, at + len(payload)) for at, (payload, _) in patch.load_pump_code().items())
        for (_, end), (start, _) in zip(spans, spans[1:]):
            self.assertLessEqual(end, start)
        stub = patch.load_pump_code()[patch.LOAD_STUB][0]
        self.assertLessEqual(len(stub), 0x20)
        poll = patch.load_pump_code()[patch.LOAD_POLL][0]
        self.assertLess(patch.LOAD_POLL + len(poll), 0x2BB805)  # NMI 선점 범위 안

    def test_chain_steps_fit_before_the_poll(self):
        self.assertLessEqual(patch.CHAIN_STEP + len(patch.chain_step_code()), patch.CHAIN_LATE_STEP)
        self.assertLessEqual(patch.CHAIN_LATE_STEP + len(patch.chain_late_step_code()), patch.LOAD_POLL)

    def test_late_step_skips_a_cleared_queue_slot(self):
        # 1A 가 지운 칸(FF)도 bit6 이 켜져 있어, bit6 만 보면 떠난 곡의 본체를 보냈다
        code = patch.chain_late_step_code()
        guard = bytes.fromhex('BD 95 1D 29 FF 00 C9 FF 00 F0')
        self.assertIn(guard, code)
        self.assertLess(code.index(guard), code.index(bytes.fromhex('29 40 00')))

    def test_vehicle_song_skips_both_commands_for_the_same_song(self):
        code = patch.vehicle_song_code()
        self.assertTrue(code.startswith(bytes.fromhex('48 AD 8B 1D CD 4B 19 F0')))
        same = code[9 + code[8]:]
        self.assertEqual(same, bytes.fromhex('68 6B'))  # 같으면 PLA / RTL 만
        self.assertIn(bytes.fromhex('22 91 FE 24 AD 4B 19 22 9A FE 24'), code)

    def test_nmi_range_sees_every_coroutine_range(self):
        # 88E2 진입과 00:8004 발판의 CMP #imm16 / BCS / BCC / JMP 만 따라가 PC 가 코루틴(88EC)인지 주 스레드(891E)인지 본다
        code = {}
        for at, (payload, _) in patch.nmi_range_code().items():
            for i, b in enumerate(payload):
                code[(at & 0xFFFF) + i] = b

        def classify(pc):
            at, carry = 0x88E2, None
            for _ in range(32):
                op = code.get(at)
                if at in (0x88EC, 0x891E):
                    return at == 0x88EC
                if op == 0xC9:
                    carry = pc >= code[at + 1] | code[at + 2] << 8
                    at += 3
                elif op in (0xB0, 0x90):
                    rel = code[at + 1] - 256 * (code[at + 1] > 127)
                    taken = carry if op == 0xB0 else not carry
                    at += 2 + (rel if taken else 0)
                elif op == 0x4C:
                    at = code[at + 1] | code[at + 2] << 8
                else:
                    self.fail(f'unexpected byte {op} at {at:04X}')
            self.fail('no exit')

        expect = {0x8000: False, 0xB740: False, 0xB741: True, 0xB804: True, 0xB805: False, 0xBECD: False,
                  0xBECE: True, 0xC421: True, 0xC422: False, patch.COROUTINE_EXTRA - 1: False,
                  patch.COROUTINE_EXTRA: True, 0xEAFF: True}
        for pc, co in expect.items():
            self.assertEqual(classify(pc), co, f'{pc:04X}')

    def test_keep_samples_code_fits_in_the_coroutine_range(self):
        done, mark = patch.keep_samples_code()
        self.assertEqual(patch.RELEASE_CODE & 0xFFFF, patch.COROUTINE_EXTRA)
        self.assertEqual(patch.RELEASE_CODE + len(patch.release_failed_code()), patch.KEEP_CODE)
        self.assertLessEqual((patch.KEEP_CODE + len(done) + len(mark) + len(patch.keep_loop_code())) & 0xFFFF, 0xEB00)

    def test_keep_samples_mark_holds_the_queue_loop(self):
        done, mark = patch.keep_samples_code()
        busy = patch.KEEP_BUSY.to_bytes(2, 'little')
        # 표시하는 동안 C21E 가 대기열 루프를 부르면 남은 1A 칸이 다시 돌아 표시 코드로 겹겹이 들어갔다
        self.assertLess(mark.index(bytes.fromhex('A9 01 00 8D') + busy), mark.index(bytes.fromhex('20 1E C2')))
        self.assertIn(bytes.fromhex('9C') + busy, mark[mark.index(bytes.fromhex('20 1E C2')):])
        loop = patch.keep_loop_code()
        self.assertEqual(loop, bytes.fromhex('AD') + busy + bytes.fromhex('D0 03 4C D5 BE 60'))
        self.assertNotIn(patch.KEEP_BUSY, range(patch.KEEP_SONG - 1, patch.KEEP_SONG + 2))

    def test_keep_samples_marks_before_the_cleanup(self):
        done, mark = patch.keep_samples_code()
        # 지워진 칸(1A 가 끊은 곡)은 다 실린 곡으로 적지 않는다
        self.assertTrue(done.startswith(bytes.fromhex('08 C2 30 BD 95 1D 29 FF 00 C9 FF 00 F0')))
        self.assertTrue(done.endswith(bytes.fromhex('28 4C 84 C1')))
        # C21E 가 앞 명령(16)의 대답을 소비하므로, 표시가 끝난 뒤에야 C32F 로 대답을 기다리고 0A 를 보낸다
        self.assertTrue(mark.endswith(bytes.fromhex('28 20 2F C3 A9 0A 00 4C 12 C1')))
        self.assertLess(mark.index(bytes.fromhex('20 1E C2')), len(mark) - 10)
        self.assertNotIn(bytes.fromhex('20 2F C3'), mark[:-10])

    def test_far_branch_out_of_range_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'out of range'):
            patch._asm_far([('b', 0x80, 'far'), bytes(200), ('label', 'far')], 0x718000)

    def test_early_song_entry_is_after_the_skip_subroutine(self):
        code, entry = patch.early_song_code()
        self.assertEqual(code[entry - patch.EARLY_SONG], 0x08)  # PHP
        self.assertEqual(code[-4:], bytes.fromhex('5C 49 CE 00'))


class MapStartInstallTests(unittest.TestCase):
    load = staticmethod(synthetic_base)

    @classmethod
    def setUpClass(cls):
        cls.base = cls.load()
        cls.item = {0x02: patch.Replacement(melody(), (0x03,))}

    def test_hold_needs_fast_receive_and_pump_needs_early_song(self):
        with self.assertRaisesRegex(ValueError, 'fast_receive'):
            patch.install(self.base, self.item, hold=True)
        with self.assertRaisesRegex(ValueError, 'early_song'):
            patch.install(self.base, self.item, load_pump=True)

    def test_all_map_start_patches_install(self):
        out, report = patch.install(self.base, self.item, fast_receive=True, hold=True, early_song=True, load_pump=True)
        self.assertTrue(report['hold'] and report['early_song'] and report['load_pump'])
        drv = lorom(patch.DRIVER_BLOCK) + 4 - 0x0750
        self.assertEqual(out[drv + patch.HOLD_TICK_SITE:drv + patch.HOLD_TICK_SITE + 3], bytes([0x3F]) + patch.HOLD_CHECK.to_bytes(2, 'little'))
        site = lorom(patch.EARLY_SONG_SITE)
        self.assertEqual(out[site], 0x22)
        self.assertEqual(out[lorom(0x00FFEE):lorom(0x00FFEE) + 2], bytes([0x00, 0x80]))
        for at, (payload, _) in patch.load_pump_code().items():
            self.assertEqual(out[lorom(at):lorom(at) + len(payload)], payload)


@unittest.skipUnless(ROM.exists(), 'user-supplied DQ5 ROM required')
class RealRomMapStartInstallTests(MapStartInstallTests):
    load = staticmethod(ROM.read_bytes)

class SongNumberCodeTests(unittest.TestCase):
    def spc_effect(self, a):
        # SPC 도우미를 흉내: CMP #47 / BCS 곡 / CMP #32 / RET(C) ; 곡: CLRC
        return False if a >= 0x47 else a >= 0x32

    def test_helpers_treat_only_32_to_46_as_effects(self):
        self.assertEqual(patch.SPC_EFFECT_HELPER, bytes.fromhex('68 47 B0 03 68 32 6F 60 6F'))
        self.assertEqual([self.spc_effect(a) for a in (0x01, 0x31, 0x32, 0x46, 0x47, 0x63)],
                         [False, False, True, True, False, False])
        self.assertEqual(patch.song_store_helper()[:2], bytes.fromhex('C9 47'))
        self.assertEqual(patch.song_test_helper()[-3:], bytes.fromhex('60 18 60'))

    def test_new_numbers_leave_room_for_chains(self):
        self.assertLess(patch.NEW_SONG_LAST, patch.FIRST_CHAIN_SONG)
        self.assertLessEqual(patch.SONG_STORE_HELPER + len(patch.song_store_helper()), 0x2BB780)
        self.assertLessEqual(patch.SONG_TEST_HELPER + len(patch.song_test_helper()), 0x2BB805)


class SongNumberInstallTests(unittest.TestCase):
    load = staticmethod(synthetic_base)

    def test_new_song_number_pads_records_and_patches_effect_tests(self):
        base = self.load()
        out, report = patch.install(base, {0x48: patch.Replacement(melody(), (0x03,))})
        records = patch.read_sets(out)
        self.assertEqual(len(records), 0x49)
        self.assertEqual(records[0x47], bytes(2))
        self.assertEqual(records[0x48], bytes([1, 1, 0x03]))
        self.assertEqual(report['song_records'], 0x49)
        helper = 0x28EC + sum(map(len, records))
        self.assertEqual(patch.heap_start(out), helper + len(patch.SPC_EFFECT_HELPER))
        drv = lorom(patch.DRIVER_BLOCK) + 4 - 0x0750
        for site in patch.SPC_EFFECT_COMPARES:
            self.assertEqual(out[drv + site:drv + site + 3], bytes([0x3F]) + helper.to_bytes(2, 'little'))
        self.assertEqual(out[lorom(patch.NMI_RANGE_STUB)], 0xC9)
        with self.assertRaisesRegex(ValueError, '47..4B'):
            patch.install(base, {0x4C: patch.Replacement(melody(), (0x03,))})


@unittest.skipUnless(ROM.exists(), 'user-supplied DQ5 ROM required')
class RealRomSongNumberInstallTests(SongNumberInstallTests):
    load = staticmethod(ROM.read_bytes)


if __name__ == '__main__':
    unittest.main()
