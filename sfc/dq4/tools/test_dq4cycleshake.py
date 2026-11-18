import unittest

import dq4cycleshake as S


def rom():
    data = bytearray(0x10000 * 4)
    data[S.NMI_AT:S.NMI_AT + len(S.NMI_BYTES)] = S.NMI_BYTES
    data[0x8000:0x8100] = b'\x01' * 0x100          # 뱅크 01 첫머리는 쓰인 바이트, 끝은 비어 있음
    return bytes(data)


class CycleShakeTests(unittest.TestCase):
    def test_nmi_jumps_to_stub_that_runs_the_moved_instructions_and_returns(self):
        out = S.shake(rom(), 7)
        self.assertEqual(out[S.NMI_AT], 0x5C)
        self.assertEqual(out[S.NMI_AT + 4:S.NMI_AT + 6], b'\xEA\xEA')
        target = int.from_bytes(out[S.NMI_AT + 1:S.NMI_AT + 4], 'little')
        at = (target >> 16) * S.BANK + (target & 0xFFFF) - 0x8000
        stub = out[at:at + 7 + len(S.NMI_BYTES) + 4]
        self.assertEqual(stub[:7], b'\xEA' * 7)
        self.assertEqual(stub[7:7 + len(S.NMI_BYTES)], S.NMI_BYTES)
        self.assertEqual(stub[-4:], b'\x5C' + S.NMI_BACK.to_bytes(3, 'little'))
        self.assertEqual(len(out), len(rom()))

    def test_stub_goes_to_a_free_bank_end(self):
        out = S.shake(rom(), 0x40)
        target = int.from_bytes(out[S.NMI_AT + 1:S.NMI_AT + 4], 'little')
        self.assertLess(target >> 16, S.LAST_BANK + 1)
        self.assertGreaterEqual(target & 0xFFFF, 0x8000)

    def test_unknown_nmi_bytes_are_refused(self):
        data = bytearray(rom())
        data[S.NMI_AT] = 0
        with self.assertRaises(ValueError):
            S.shake(bytes(data), 4)


if __name__ == '__main__':
    unittest.main()
