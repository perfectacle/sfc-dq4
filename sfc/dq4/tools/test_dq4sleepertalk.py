"""롬 없이: 누운 인물 찾기 훅의 바이트와 자리. 원본 DQ5 롬이 있으면 덮는 자리의 원래 바이트."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dq4sleepertalk as st  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
DQ5 = ROOT / "rom" / "dq5.sfc"


def lorom(addr):
    return (addr >> 16) * 0x8000 + (addr & 0x7FFF)


class HookTest(unittest.TestCase):
    def test_checks_the_cell_to_the_right_only_when_the_first_misses(self):
        code = st.code()
        self.assertEqual(code[:4], bytes((0x7B, 0x20, 0x03, 0x85)))       # TDC / JSR $8503 at ($00, $01)
        branch = code.index(0xB0)
        self.assertEqual(branch + 2 + code[branch + 1], len(code) - 1)    # BCS to the RTS
        self.assertEqual(code[branch + 2:branch + 4], bytes((0xE6, 0x00)))  # INC $00: one cell right
        self.assertEqual(code[-3:], bytes((0xC6, 0x00, 0x60)))           # DEC $00 back, RTS (C kept)

    def test_writes_jump_from_the_lying_check(self):
        hook, jump = st.writes()
        self.assertEqual(hook["at"], "05:FEF0")
        self.assertEqual(jump["at"], "05:84FE")
        self.assertEqual(jump["hex"], "4C F0 FE")
        self.assertEqual(jump["orig"], "7B 80 02")
        with self.assertRaises(ValueError):
            st.writes(0x06FEF0)

    @unittest.skipUnless(DQ5.is_file(), "local source ROM not present")
    def test_original_bytes(self):
        rom = DQ5.read_bytes()
        self.assertEqual(rom[lorom(st.LYING_CHECK):lorom(st.LYING_CHECK) + 3], st.LYING_CHECK_ORIG)
        self.assertEqual(rom[lorom(0x058501):lorom(0x058501) + 4], bytes.fromhex("A9 01 85 A2"))
        self.assertEqual(set(rom[lorom(st.HOOK_AT):lorom(st.HOOK_AT) + len(st.code())]), {0})


if __name__ == "__main__":
    unittest.main()
