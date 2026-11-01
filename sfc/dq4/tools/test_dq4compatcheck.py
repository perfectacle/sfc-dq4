import unittest

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

    def test_rom_offsets_map_to_lorom(self):
        self.assertEqual(cc.cpu(cc.TRIGGER_RECORD), 0x2AD812)
        self.assertEqual(cc.rom_codes(0x155812, b'\x01\x02'), ['2AD81201', '2AD81302'])


if __name__ == '__main__':
    unittest.main()
