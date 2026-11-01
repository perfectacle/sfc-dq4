import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

import dq4compatcheck as cc


class ProbeLogTest(unittest.TestCase):
    def test_dq5_sram_access_is_fine(self):
        self.assertEqual(cc.probe_problems(['R pc=25:8071 bank=70', 'W pc=25:808F bank=70']), [])

    def test_open_bus_read_from_high_bank_brk_is_caught(self):
        # #904 이전: 뱅크 5E 의 BRK 16 → DB 5E → 24:FE52 가 5E:1D93 을 읽음
        problems = cc.probe_problems(['R pc=24:FE52 bank=5E', 'BRK pc=5E:C260 op=16'])
        self.assertEqual(len(problems), 2)
        self.assertIn('5E:0000~7FFF', problems[0])
        self.assertIn('BRK 16', problems[1])

    def test_allowed_brk_and_high_bank_sram_writer(self):
        self.assertEqual(cc.probe_problems(['BRK pc=5E:D0B4 op=88']), [])
        # 높은 뱅크 코드가 SRAM 을 직접 쓰면 DB 실수일 수 있어 잡는다
        self.assertTrue(cc.probe_problems(['W pc=5E:D000 bank=70']))

    def test_reset_needs_dark_then_bright(self):
        self.assertTrue(cc.reset_seen([90, 90, 5, 3, 130, 12]))       # 성 앞 → 서술(어둠) → 타이틀 → 메뉴
        self.assertFalse(cc.reset_seen([90, 90, 90]))                  # 밝은 성 앞만: 리셋이 아님
        self.assertFalse(cc.reset_seen([90, 5, 3, 12, 12]))            # 어두워진 뒤 타이틀이 안 뜸

    def test_party_matches_dq5warp_build_party(self):
        # dq5warp.lua buildParty: 동료 표 23:AED1(9바이트) → 일행 기록 1(7E:206A), 인원 7E:201D~
        rom = bytearray(0x200000)
        rom[cc.COMPANIONS + 5 * 9:cc.COMPANIONS + 5 * 9 + 9] = bytes(range(1, 10))
        got = dict(cc.party_pokes('05', bytes(rom)))
        self.assertEqual(got[0x7E206A], 0x85)
        self.assertEqual((got[0x7E206A + 0x12], got[0x7E206A + 0x13]), (1, 2))
        self.assertEqual([got[0x7E206A + 7 + j] for j in range(4)], [3, 4, 5, 6])
        self.assertEqual((got[0x7E206A + 2], got[0x7E206A + 0xE], got[0x7E206A + 4]), (7, 7, 8))
        self.assertEqual((got[0x7E201D], got[0x7E201E], got[0x7E201F]), (2, 2, 2))
        self.assertEqual(cc.party_pokes('', bytes(rom)), [])

    def test_sets_ops(self):
        class Fake:
            def __init__(self):
                self.m = {0x7E2190: 0x01, 0x7E2223: 0xF0}
            def rd(self, a):
                return self.m.get(a, 0)
            def poke(self, pairs):
                self.m.update(pairs)
        f = Fake()
        cc.apply_sets(f, '2190|80;2058=CD;2223&0F')
        self.assertEqual((f.m[0x7E2190], f.m[0x7E2058], f.m[0x7E2223]), (0x81, 0xCD, 0x00))

    def test_rom_offsets_map_to_lorom(self):
        self.assertEqual(cc.cpu(cc.TRIGGER_RECORD), 0x2AD812)
        self.assertEqual(cc.rom_codes(0x155812, b'\x01\x02'), ['2AD81201', '2AD81302'])


class WaitChildTest(unittest.TestCase):
    """자리를 기다린 시간은 시간 제한에 넣지 않고, 표지(started)를 쓴 뒤부터 잰다."""

    def child(self, before, after):
        out = Path(tempfile.mkdtemp())
        code = (f'import time, pathlib; time.sleep({before}); '
                f'pathlib.Path({str(out / cc.STARTED)!r}).write_text("0"); time.sleep({after})')
        return subprocess.Popen([sys.executable, '-c', code]), out

    def test_wait_before_marker_is_not_counted(self):
        proc, out = self.child(1.5, 0.2)
        self.assertTrue(cc.wait_child(proc, out, 1.0))

    def test_timeout_after_marker_kills(self):
        proc, out = self.child(0, 30)
        t = time.time()
        self.assertFalse(cc.wait_child(proc, out, 0.5))
        self.assertLess(time.time() - t, 10)
        self.assertIsNotNone(proc.poll())

    def test_unit_waits_sums_markers(self):
        out = Path(tempfile.mkdtemp())
        for i, w in enumerate(('1.5', '2.0')):
            (out / f'unit-{i:02d}').mkdir()
            (out / f'unit-{i:02d}' / cc.STARTED).write_text(w)
        self.assertAlmostEqual(cc.unit_waits(out), 3.5)


if __name__ == '__main__':
    unittest.main()
