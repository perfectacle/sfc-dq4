"""BRK 뱅크 호출 풀기(뱅크 매핑·함수 표·BRK 형식 갈래)를 합성 PRG 로 검사한다."""
import unittest

import dq4bank as bank

PRG_SIZE = 32 * 0x4000


def put_entry(prg, b, func, target):
    o = bank.prg_offset(b, 0x8000 + 2 * func)
    prg[o:o + 2] = target.to_bytes(2, 'little')


def put_brk(prg, cur, site, *operands):
    o = bank.prg_offset(bank.mapped(cur, site), site)
    prg[o:o + 1 + len(operands)] = bytes((0x00, *operands))


class MappingTests(unittest.TestCase):
    def test_fixed_window_follows_the_half(self):
        self.assertEqual(bank.mapped(0x03, 0xC000), 0x0F)
        self.assertEqual(bank.mapped(0x13, 0xFFFF), 0x1F)
        self.assertEqual(bank.mapped(0x13, 0xBFFF), 0x13)

    def test_prg_offset_ignores_window_base(self):
        self.assertEqual(bank.prg_offset(0x16, 0x8000), 0x16 * 0x4000)
        self.assertEqual(bank.prg_offset(0x0F, 0xC001), 0x0F * 0x4000 + 1)

    def test_entry_is_little_endian_per_function(self):
        prg = bytearray(PRG_SIZE)
        put_entry(prg, 0x10, 3, 0x9ABC)
        self.assertEqual(bank.entry(prg, 0x10, 3), 0x9ABC)
        self.assertEqual(bank.entry(prg, 0x10, 2), 0)


class X3LengthTests(unittest.TestCase):
    def test_even_and_odd_pairs_differ(self):
        self.assertEqual([bank.x3_length(b) for b in (0x23, 0x33, 0x43, 0x53, 0x63, 0x73)], [4, 3, 4, 3, 4, 3])

    def test_functions_08_09(self):
        self.assertEqual(bank.x3_length(0x83), 5)
        self.assertEqual(bank.x3_length(0x93), 4)

    def test_unknown_is_none(self):
        self.assertIsNone(bank.x3_length(0xF3))


class CallTests(unittest.TestCase):
    def setUp(self):
        self.prg = bytearray(PRG_SIZE)

    def test_plain_call_bank_takes_bit3_as_bit4(self):
        put_entry(self.prg, 0x15, 0x07, 0x8123)
        put_brk(self.prg, 0x02, 0x9000, 0x07, 0x5A)
        c = bank.call(self.prg, 0x9000, 0x02)
        self.assertEqual((c['kind'], c['bank'], c['func'], c['target']), ('call', 0x15, 0x07, 0x8123))

    def test_pointer_call_masks_function(self):
        put_entry(self.prg, 0x03, 0x05, 0x8F00)
        put_brk(self.prg, 0x02, 0x9000, 0x85, 0x30)
        c = bank.call(self.prg, 0x9000, 0x02)
        self.assertEqual((c['kind'], c['bank'], c['func'], c['target']), ('pointer', 0x03, 0x05, 0x8F00))

    def test_fixed_bank_site_is_read_from_the_last_bank_of_the_half(self):
        self.prg = bytearray(b'\xEA' * PRG_SIZE)
        put_brk(self.prg, 0x12, 0xC100, 0x34, 0x1B)
        self.assertEqual(bank.call(self.prg, 0xC100, 0x12)['kind'], 'message')
        with self.assertRaises(AssertionError):
            bank.call(self.prg, 0xC100, 0x02)  # 앞 절반의 0F 에는 BRK 가 없다

    def test_message_number_uses_high_nibble(self):
        put_brk(self.prg, 0x00, 0x8000, 0x34, 0xBB)
        c = bank.call(self.prg, 0x8000, 0x00)
        self.assertEqual((c['kind'], c['msg'], c['bank'], c['func']), ('message', 0xB34, 0x16, 0x04))

    def test_flag_forms_read_the_mask_byte(self):
        for b2, kind in ((0xCB, 'flag-set'), (0xDB, 'flag-clear'), (0xEB, 'flag-test')):
            put_brk(self.prg, 0x00, 0x8000, 0x10, b2, 0x40)
            c = bank.call(self.prg, 0x8000, 0x00)
            self.assertEqual((c['kind'], c['flag'], c['mask']), (kind, 0x628B, 0x40))

    def test_sound(self):
        put_brk(self.prg, 0x00, 0x8000, 0x22, 0xFB)
        c = bank.call(self.prg, 0x8000, 0x00)
        self.assertEqual((c['kind'], c['sound'], c['bank']), ('sound', 0x22, 0x19))

    def test_x3_function_ranges(self):
        for b2, want in ((0x23, (0x10, 0x02)), (0xA3, (0x10, 0x22)), (0xC3, (0x10, 0x24)), (0xD3, (0x12, 0x01))):
            put_brk(self.prg, 0x00, 0x8000, 0x00, b2)
            c = bank.call(self.prg, 0x8000, 0x00)
            self.assertEqual((c['kind'], c['bank'], c['func']), ('x3', *want), f'{b2:02X}')
            self.assertEqual(c['length'], bank.x3_length(b2))

    def test_fmt_mentions_target(self):
        put_entry(self.prg, 0x15, 0x07, 0x8123)
        put_brk(self.prg, 0x02, 0x9000, 0x07, 0x5A)
        self.assertIn('15:8123', bank.fmt(bank.call(self.prg, 0x9000, 0x02)))


class FreeRunTests(unittest.TestCase):
    def test_runs_report_cpu_address_and_skip_other_values(self):
        prg = bytearray(b'\x55' * PRG_SIZE)
        o = 0x0F * 0x4000
        prg[o + 0x100:o + 0x120] = b'\xFF' * 0x20
        prg[o + 0x200:o + 0x210] = b'\x00' * 0x10
        prg[o + 0x300:o + 0x30F] = b'\x00' * 0x0F
        self.assertEqual(bank.free_runs(prg, 0x0F), [(0xC100, 0x20, 0xFF), (0xC200, 0x10, 0x00)])
        prg[0x4000 + 0x10:0x4000 + 0x30] = b'\xFF' * 0x20
        self.assertEqual(bank.free_runs(prg, 0x01), [(0x8010, 0x20, 0xFF)])


if __name__ == '__main__':
    unittest.main()
