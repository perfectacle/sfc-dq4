import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS.parents[1] / 'dq5' / 'tools'))
sys.path.insert(0, str(TOOLS.parents[2] / 'fc' / 'dq4' / 'tools'))

import dq4fcitems as F  # noqa: E402
import dq4itemport  # noqa: E402

DQ5_ROM = TOOLS.parents[2] / 'rom' / 'dq5.sfc'
DQ4_ROM = TOOLS.parents[2] / 'rom' / 'dq4.nes'


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
        writes = {w['at']: w['hex'] for w in F.writes(rom)}
        # 승선권·정적의 구슬 칸은 전투 도구 표에서 빠지고(DQ5 てんしのすず·たたかいのドラム 효과 없음), 말똥은 원래 없음
        for item in (F.SHIP_TICKET, F.SILENCE_ORB):
            self.assertEqual(writes[F._cpu(F.BATTLE_ITEMS + F.battle_slot(rom, item))], f'{F.NEVER_HELD:02X}')
        self.assertIsNone(F.battle_slot(rom, F.HORSE_DUNG))

    @unittest.skipUnless(DQ5_ROM.is_file() and DQ4_ROM.is_file(), 'rom/dq5.sfc·dq4.nes 가 필요')
    def test_nothing_items_use_the_life_stone_handler(self):
        # FC 「…をつかった！」「しかし なにも おこらなかった。」: 셋 다 いのちのいし 의 11:8BB9(글 18E), 기록은 쓰면 남음
        import dq5item
        from kr_patch.fc import ines
        rom = dq5item.Rom(DQ5_ROM.read_bytes())
        writes = dq4itemport.event_writes(rom, ines.prg(DQ4_ROM.read_bytes()))
        handler = {w['at']: w['hex'] for w in writes if '필드에서 쓰기' in w['note']}
        at = lambda item: F._cpu(dq4itemport.USE_HANDLERS + (item - dq4itemport.FIRST_USE) * 2)
        self.assertEqual(rom.u16(dq4itemport.USE_HANDLERS + (F.HORSE_DUNG - dq4itemport.FIRST_USE) * 2),
                         F.NOTHING_USE & 0xFFFF)
        self.assertNotIn(at(F.HORSE_DUNG), handler)
        for item in (F.SILENCE_ORB, F.SHIP_TICKET):
            self.assertEqual(handler[at(item)], f'{F.NOTHING_USE & 0xFF:02X} {F.NOTHING_USE >> 8 & 0xFF:02X}')
        k1 = {w['at']: w['hex'] for w in writes if '23:B159' in w['note']}
        for item in (F.SILENCE_ORB, F.SHIP_TICKET):
            got = int(k1.get(F._cpu(dq4itemport.PRICE_SCALE + item), f'{rom.u8(dq4itemport.PRICE_SCALE + item):02X}'), 16)
            # bit7 꺼짐(「つかった！」 를 띄움), bit5 꺼짐(남음), bit3 켜짐(못 팖)
            self.assertEqual(got & 0xA8, 0x08)

    @unittest.skipUnless(DQ5_ROM.is_file(), 'rom/dq5.sfc 가 필요')
    def test_dung_sells_and_stays(self):
        import dq5item
        rom = dq5item.Rom(DQ5_ROM.read_bytes())
        k1 = [w for w in dq4itemport.price_writes(rom, F.HORSE_DUNG, 2, 'うまのふん')]
        self.assertEqual(k1[0]['hex'], '02')
        self.assertEqual(int(k1[1]['hex'], 16) & dq4itemport.CONSUMED, 0)


if __name__ == '__main__':
    unittest.main()
