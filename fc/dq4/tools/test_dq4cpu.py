"""작은 6502 해석기(산술 플래그·주소 방식·BRK 뱅크 호출·뱅크 전환·stub)를 합성 코드로 검사한다."""
import unittest

import dq4bank
from dq4cpu import CPU, Halt

PRG_SIZE = 32 * 0x4000


def prg_with(bank, addr, code, prg=None):
    prg = prg if prg is not None else bytearray(PRG_SIZE)
    o = dq4bank.prg_offset(bank, addr)
    prg[o:o + len(code)] = bytes(code)
    return prg


def run(code, bank=0x02, addr=0x8000, setup=None):
    cpu = CPU(prg_with(bank, addr, list(code) + [0x60]), bank)
    if setup:
        setup(cpu)
    cpu.call(addr)
    return cpu


class ArithmeticTests(unittest.TestCase):
    def test_adc_carry_and_zero(self):
        cpu = run([0x18, 0xA9, 0x05, 0x69, 0xFB])   # CLC; LDA #5; ADC #$FB
        self.assertEqual((cpu.a, cpu.c, cpu.z, cpu.n), (0, 1, 1, 0))

    def test_adc_signed_overflow(self):
        cpu = run([0x18, 0xA9, 0x7F, 0x69, 0x01])
        self.assertEqual((cpu.a, cpu.v, cpu.n), (0x80, 1, 1))

    def test_sbc_borrows_without_carry(self):
        cpu = run([0x18, 0xA9, 0x05, 0xE9, 0x03])   # CLC → 빌림 1
        self.assertEqual((cpu.a, cpu.c), (0x01, 1))
        cpu = run([0x38, 0xA9, 0x03, 0xE9, 0x05])
        self.assertEqual((cpu.a, cpu.c, cpu.n), (0xFE, 0, 1))

    def test_compare_sets_carry_when_not_less(self):
        cpu = run([0xA2, 0x10, 0xE0, 0x10])
        self.assertEqual((cpu.c, cpu.z), (1, 1))
        cpu = run([0xA0, 0x0F, 0xC0, 0x10])
        self.assertEqual((cpu.c, cpu.z, cpu.n), (0, 0, 1))

    def test_shifts_and_rotates_through_carry(self):
        cpu = run([0x38, 0xA9, 0x80, 0x2A])          # SEC; LDA #$80; ROL A
        self.assertEqual((cpu.a, cpu.c), (0x01, 1))
        cpu = run([0x18, 0xA9, 0x01, 0x6A])          # CLC; LDA #1; ROR A
        self.assertEqual((cpu.a, cpu.c, cpu.z), (0x00, 1, 1))
        cpu = run([0xA9, 0x81, 0x85, 0x10, 0x46, 0x10, 0xA5, 0x10])   # LSR $10
        self.assertEqual((cpu.a, cpu.c), (0x40, 1))

    def test_bit_copies_high_bits(self):
        cpu = run([0xA9, 0x01, 0x85, 0x20, 0xA9, 0x40, 0x24, 0x20])   # BIT $20 (=01) with A=40
        self.assertEqual((cpu.n, cpu.v, cpu.z), (0, 0, 1))


class AddressingTests(unittest.TestCase):
    def test_zero_page_index_wraps(self):
        cpu = run([0xA2, 0x05, 0xA9, 0x77, 0x95, 0xFE])   # STA $FE,X → $03
        self.assertEqual(cpu.ram[0x03], 0x77)

    def test_indirect_y_and_wram(self):
        def setup(cpu):
            cpu.ram[0x30:0x32] = bytes((0x00, 0x60))
        cpu = run([0xA0, 0x04, 0xA9, 0x99, 0x91, 0x30], setup=setup)   # STA ($30),Y → $6004
        self.assertEqual(cpu.wram[4], 0x99)

    def test_ram_mirrors_every_2k(self):
        cpu = run([0xA9, 0x42, 0x8D, 0x10, 0x08])          # STA $0810 → $0010
        self.assertEqual(cpu.ram[0x10], 0x42)

    def test_ppu_status_reads_vblank(self):
        cpu = run([0xAD, 0x02, 0x20])
        self.assertEqual(cpu.a, 0x80)

    def test_jmp_indirect_keeps_page(self):
        def setup(cpu):
            cpu.ram[0x2FF], cpu.ram[0x200], cpu.ram[0x300] = 0x10, 0x80, 0x90
        prg = prg_with(0x02, 0x8000, [0x6C, 0xFF, 0x02])
        prg_with(0x02, 0x8010, [0xA9, 0x01, 0x60], prg)
        prg_with(0x02, 0x9010, [0xA9, 0x02, 0x60], prg)
        cpu = CPU(prg, 0x02)
        setup(cpu)
        cpu.call(0x8000)
        self.assertEqual(cpu.a, 0x01)   # 6502 는 $02FF 다음 바이트를 $0200 에서 읽는다

    def test_branch_backwards_loops(self):
        cpu = run([0xA2, 0x03, 0xA9, 0x00, 0x18, 0x69, 0x02, 0xCA, 0xD0, 0xFA])   # X 번 A+=2
        self.assertEqual((cpu.a, cpu.x), (6, 0))


class ControlTests(unittest.TestCase):
    def test_jsr_rts_and_stack_balance(self):
        prg = prg_with(0x02, 0x8000, [0x20, 0x10, 0x80, 0xE8, 0x60])
        prg_with(0x02, 0x8010, [0xA2, 0x41, 0x60], prg)
        cpu = CPU(prg, 0x02)
        cpu.call(0x8000)
        self.assertEqual((cpu.x, cpu.s), (0x42, 0xFF))

    def test_brk_calls_other_bank_and_resumes_after_three_bytes(self):
        prg = prg_with(0x02, 0x8000, [0x00, 0x01, 0x30, 0xA9, 0x11, 0x60])   # BRK 01 30 → 뱅크 03 함수 01
        prg_with(0x03, 0x8002, [0x00, 0x90], prg)
        prg_with(0x03, 0x9000, [0xA2, 0x22, 0x60], prg)
        cpu = CPU(prg, 0x02)
        cpu.call(0x8000)
        self.assertEqual((cpu.a, cpu.x, cpu.bank), (0x11, 0x22, 0x02))

    def test_brk_message_is_skipped_and_recorded(self):
        prg = prg_with(0x02, 0x8000, [0x00, 0x34, 0x1B, 0xA9, 0x01, 0x60])
        cpu = CPU(prg, 0x02)
        cpu.call(0x8000)
        self.assertEqual((cpu.a, cpu.skipped), (0x01, [(0x8000, 0x34, 0x1B)]))

    def test_brk_flag_form_skips_four_bytes(self):
        prg = prg_with(0x02, 0x8000, [0x00, 0x05, 0xCB, 0x80, 0xA9, 0x07, 0x60])
        cpu = CPU(prg, 0x02)
        cpu.call(0x8000)
        self.assertEqual(cpu.a, 0x07)

    def test_ff91_switches_bank_and_records_0507(self):
        prg = prg_with(0x02, 0x8000, [0xA9, 0x05, 0x20, 0x91, 0xFF])
        # 돌아온 다음 명령부터는 뱅크 05 의 같은 자리를 실행한다
        prg_with(0x05, 0x8000, [0x5A, 0, 0, 0, 0, 0xAD, 0x00, 0x80, 0x60], prg)
        cpu = CPU(prg, 0x02)
        cpu.call(0x8000)
        self.assertEqual((cpu.a, cpu.bank, cpu.ram[0x507]), (0x5A, 0x05, 0x05))

    def test_hooks_and_stubs(self):
        prg = prg_with(0x02, 0x8000, [0x20, 0x00, 0xE0, 0xA9, 0x03, 0x60])
        cpu = CPU(prg, 0x02)
        seen = []
        cpu.hooks[0x8003] = lambda c: seen.append(c.pc)
        cpu.stubs.add(0xE000)   # 0F:E000 은 0 바이트(BRK)라 stub 이 없으면 BRK 로 풀린다
        cpu.call(0x8000)
        self.assertEqual((cpu.a, seen), (0x03, [0x8003]))

    def test_limit_halts_infinite_loop(self):
        cpu = CPU(prg_with(0x02, 0x8000, [0x4C, 0x00, 0x80]), 0x02)
        with self.assertRaises(Halt):
            cpu.call(0x8000, limit=100)

    def test_unofficial_opcode_halts(self):
        cpu = CPU(prg_with(0x02, 0x8000, [0x02]), 0x02)
        with self.assertRaises(Halt):
            cpu.call(0x8000)

    def test_php_plp_roundtrip(self):
        cpu = run([0x38, 0xA9, 0x80, 0x08, 0x18, 0xA9, 0x01, 0x28])   # SEC; LDA #$80; PHP; CLC; LDA #1; PLP
        self.assertEqual((cpu.c, cpu.n, cpu.z), (1, 1, 0))


if __name__ == '__main__':
    unittest.main()
