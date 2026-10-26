import unittest

import dq4namegame as ng
import dq4nameentry as ne
import dq4namesave as ns
from dq5sram import MAGIC, SIZE, SLOTS, SUM_AT, USED, checksum


class RoutineTests(unittest.TestCase):
    def test_branches_land_on_original_jump(self):
        code = ng.routine()
        jump = len(code) - 3
        self.assertEqual(code[jump:], bytes((0x4C, 0x1E, 0xA8)))
        self.assertEqual(code[:2], bytes((0xC9, ne.HI_BASE)))
        self.assertEqual(2 + 2 + code[3], jump)                  # BCC
        self.assertEqual(code[4:6], bytes((0xC9, 0x9B)))         # 마지막 표시 바이트 9A 다음
        self.assertEqual(6 + 2 + code[7], jump)                  # BCS

    def test_fits_in_freed_decoder(self):
        self.assertLessEqual(ng.ROUTINE + len(ng.routine()), ng.ROUTINE_END)

    def test_last_glyph_uses_last_tag(self):
        self.assertEqual(ne.code_bytes(len(ne.GLYPHS) - 1)[0], 0x9A)


def sram_with(names):
    d = bytearray(SIZE)
    d[:len(MAGIC)] = MAGIC
    for n, raw in enumerate(names):
        if raw is None:
            continue
        d[USED] |= 1 << n
        off = SLOTS[n]
        d[off + 1:off + 9] = raw
        s = checksum(d[off:off + SUM_AT + 2])
        d[off + SUM_AT:off + SUM_AT + 2] = s.to_bytes(2, 'little')
    return bytes(d)


class SaveTests(unittest.TestCase):
    LEGACY = bytes.fromhex('162f1e3c1c5a0101')            # 라이안(예전 부호)

    def test_convert_tags_only_chosen_slot_and_fixes_checksum(self):
        sram = sram_with([self.LEGACY, self.LEGACY, None])
        out = ns.convert(sram, [2])
        self.assertEqual(out[SLOTS[0]:SLOTS[0] + 9], sram[SLOTS[0]:SLOTS[0] + 9])
        self.assertEqual(ns.name_kind(out[SLOTS[1] + 1:SLOTS[1] + 9]), ('korean', '라이안'))
        block = out[SLOTS[1]:SLOTS[1] + SUM_AT + 2]
        self.assertEqual(block[SUM_AT] | block[SUM_AT + 1] << 8, checksum(block))
        changed = [i for i in range(SIZE) if out[i] != sram[i]]
        self.assertTrue(all(SLOTS[1] + 1 <= i < SLOTS[1] + 9 or SLOTS[1] + SUM_AT <= i < SLOTS[1] + SUM_AT + 2
                            for i in changed))

    def test_refuses_kana_tagged_empty_and_bad_checksum(self):
        kana = bytes.fromhex('8a8a8a8a01010101')           # 표시 바이트도 예전 부호도 아닌 가나
        tagged = ns.convert(sram_with([self.LEGACY]), [1])
        for sram, slot in ((sram_with([kana]), 1), (tagged, 1), (sram_with([None]), 1)):
            with self.assertRaises(ValueError):
                ns.convert(sram, [slot])
        broken = bytearray(sram_with([self.LEGACY]))
        broken[SLOTS[0] + 0x20] ^= 1
        with self.assertRaises(ValueError):
            ns.convert(bytes(broken), [1])


if __name__ == '__main__':
    unittest.main()
