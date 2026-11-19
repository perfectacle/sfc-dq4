import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS.parents[1] / 'dq5' / 'tools'))

import dq4fcitems as F  # noqa: E402
import dq4itemport  # noqa: E402

DQ5_ROM = TOOLS.parents[2] / 'rom' / 'dq5.sfc'


class LuckSeedTest(unittest.TestCase):
    def test_borrows_mamori_seed(self):
        self.assertEqual(dq4itemport.BORROWED[F.LUCK_SEED], 'ラックのたね')
        self.assertIn(F.LUCK_SEED, dq4itemport.korean_names())

    def test_handlers_pass_luck(self):
        # 필드는 LDX #더하기 칸, 전투는 LDY #더하기 칸 / LDX #읽기 칸 뒤 1~3 몸통(898D·BCF7)
        self.assertEqual(F.FIELD_NEW[:6], bytes((0xA2, F.LUCK_ADD, 0x00, 0x20, 0x8D, 0x89)))
        self.assertEqual(F.BATTLE_NEW[:7], bytes((0xA0, F.LUCK_ADD, 0xA2, F.LUCK_READ, 0x20, 0xF7, 0xBC)))
        self.assertEqual(len(F.FIELD_NEW), len(F.FIELD_ORIG))
        self.assertEqual(len(F.BATTLE_NEW), len(F.BATTLE_ORIG))

    def test_messages_say_luck(self):
        import dq4battletexts
        import dq4sysmsg
        self.assertIn('운이', dq4sysmsg.SOURCE[0x1BC])
        self.assertIn('운이', dq4battletexts.SOURCE[0x0C9])

    @unittest.skipUnless(DQ5_ROM.is_file(), 'rom/dq5.sfc 가 필요')
    def test_writes_match_rom(self):
        import dq5item
        rom = dq5item.Rom(DQ5_ROM.read_bytes())
        notes = [w['note'] for w in F.writes(rom)]
        self.assertEqual(len(notes), 2)


if __name__ == '__main__':
    unittest.main()
