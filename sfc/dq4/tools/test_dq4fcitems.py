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
        self.assertIn('운이', dq4sysmsg.SOURCE[F.FIELD_MSG])
        self.assertIn('방어력', dq4sysmsg.SOURCE[0x1BC])
        self.assertIn('운이', dq4battletexts.SOURCE[F.BATTLE_MSG])
        self.assertIn('몸 지키기', dq4battletexts.SOURCE[0x0C9])

    @unittest.skipUnless(DQ5_ROM.is_file(), 'rom/dq5.sfc 가 필요')
    def test_writes_match_rom(self):
        import dq5item
        rom = dq5item.Rom(DQ5_ROM.read_bytes())
        writes = {w['at']: w['hex'] for w in F.writes(rom, dq4itemport.EVENT_ITEMS)}
        # 전투 도구 표에 든 사건 물건 자리: 도시락은 약초 처리기, 금고·여신상·승선권·정적의 구슬은 표에서 빠짐
        bento = F.BATTLE_HANDLERS + 2 * F.battle_slot(rom, F.BENTO)
        herb = rom.u16(F.BATTLE_HANDLERS + 2 * F.battle_slot(rom, F.HERB))
        self.assertEqual(writes[F._cpu(bento)], f'{herb & 0xFF:02X} {herb >> 8:02X}')
        for item in (dq4itemport.IRON_SAFE, dq4itemport.STATUE, F.SILENCE_ORB):
            self.assertEqual(writes[F._cpu(F.BATTLE_ITEMS + F.battle_slot(rom, item))], f'{F.NEVER_HELD:02X}')
        # 승선권이 비운 てんしのすず 칸은 운의 씨앗(C5)과 그 전투 코드(まもののエサ 처리기 자리)
        ticket = F.battle_slot(rom, F.SHIP_TICKET)
        self.assertEqual(writes[F._cpu(F.BATTLE_ITEMS + ticket)], f'{F.LUCK_SEED:02X}')
        self.assertEqual(writes[F._cpu(F.BATTLE_HANDLERS + 2 * ticket)], f'{F.BATTLE_AT & 0xFF:02X} {F.BATTLE_AT >> 8 & 0xFF:02X}')
        # 원래 まもりのたね(AE) 의 처리기는 건드리지 않는다
        self.assertFalse([a for a in writes if a in ('11:89A4', '20:BCCA')])
        # 나머지 사건 물건 자리는 원래 표에 없다
        rest = set(dq4itemport.EVENT_ITEMS) - {F.BENTO, dq4itemport.IRON_SAFE, dq4itemport.STATUE, F.SHIP_TICKET,
                                               F.SILENCE_ORB}
        self.assertEqual([i for i in rest if F.battle_slot(rom, i) is not None], [])

    @unittest.skipUnless(DQ5_ROM.is_file() and DQ4_ROM.is_file(), 'rom/dq5.sfc·dq4.nes 가 필요')
    def test_battle_follows_fc_actions(self):
        # 표에서 빼는 자리의 FC 물건은 전투 행동 7F(아무 일 없음) — 정적의 구슬(9D 마호톤)만 남은 것. 도시락은 약초와 같은 행동
        import dq4data
        import dq4shop
        from kr_patch.fc import ines
        prg = ines.prg(DQ4_ROM.read_bytes())
        fc = {n: i for i, n in dq4shop.item_names(prg)[0].items()}
        act = {item: dq4data.item_action(prg, fc[name]) for item, name in dq4itemport.EVENT_ITEMS.items()}
        for item in (dq4itemport.IRON_SAFE, dq4itemport.STATUE, F.SHIP_TICKET):
            self.assertEqual(act[item], 0x7F)
        self.assertEqual(act[F.SILENCE_ORB], 0x9D)
        self.assertEqual(act[F.BENTO], dq4data.item_action(prg, fc['やくそう']))

    @unittest.skipUnless(DQ5_ROM.is_file() and DQ4_ROM.is_file(), 'rom/dq5.sfc·dq4.nes 가 필요')
    def test_field_use_follows_fc_effect_bit(self):
        # FC 필드 효과 비트가 꺼진 사건 물건은 いのちのいし 의 11:8BB9(글 18E 「그러나 아무 일도 일어나지 않았다.」),
        # 켜진 것은 제 기록 틀의 처리기(도시락은 약초, 피리는 はるかぜのフルート, 나머지는 ゴールドオーブ 「여기서는」)
        import dq5item
        from kr_patch.fc import ines
        rom = dq5item.Rom(DQ5_ROM.read_bytes())
        prg = ines.prg(DQ4_ROM.read_bytes())
        handler = lambda item: rom.u16(dq4itemport.USE_HANDLERS + (item - dq4itemport.FIRST_USE) * 2)
        want = {0xC6: 0x8BB9, 0xBE: 0x8BE4, F.BENTO: 0x8906, dq4itemport.IRON_SAFE: 0x8BB9, dq4itemport.STATUE: 0x8BB9,
                0xC3: 0x8BE4, 0xCA: 0x8BE4, dq4itemport.FLUTE: 0x8BD0, F.SILENCE_ORB: 0x8BB9, F.SHIP_TICKET: 0x8BB9,
                F.HORSE_DUNG: 0x8BB9}
        self.assertEqual(set(want), set(dq4itemport.EVENT_ITEMS))
        self.assertEqual({i: handler(dq4itemport.use_template(prg, i)) for i in want}, want)
        self.assertEqual(F.NOTHING_USE & 0xFFFF, handler(F.HORSE_DUNG))
        writes = dq4itemport.event_writes(rom, prg)
        k1 = {w['at']: w['hex'] for w in writes if '23:B159' in w['note']}
        for item in (F.SILENCE_ORB, F.SHIP_TICKET):
            got = int(k1.get(F._cpu(dq4itemport.PRICE_SCALE + item), f'{rom.u8(dq4itemport.PRICE_SCALE + item):02X}'), 16)
            # bit7 꺼짐(「つかった！」 를 띄움), bit5 꺼짐(남음), bit3 켜짐(못 팖)
            self.assertEqual(got & 0xA8, 0x08)

    @unittest.skipUnless(DQ5_ROM.is_file(), 'rom/dq5.sfc 가 필요')
    def test_bento_is_a_herb_at_ten_gold(self):
        # FC おべんとう: 10G, 쓰면 없어짐, 팔 수 있음. 기록 k2~k4 는 약초 것, k1 은 값 쓰기가 약초 플래그로
        import dq5item
        rom = dq5item.Rom(DQ5_ROM.read_bytes())
        base, scale = dq4itemport.price_writes(rom, F.BENTO, 10, 'おべんとう')
        flags = int(scale['hex'], 16)
        self.assertEqual((base['hex'], flags & ~3), ('0A', rom.u8(dq4itemport.PRICE_SCALE + F.HERB) & ~3))
        self.assertTrue(flags & dq4itemport.CONSUMED)
        self.assertFalse(flags & dq4itemport.NO_SALE)
        recs = dq4itemport._record_writes(rom, F.BENTO, F.HERB, 'おべんとう')
        self.assertNotIn(F._cpu(dq4itemport.PRICE_SCALE + F.BENTO), [w['at'] for w in recs])

    @unittest.skipUnless(DQ5_ROM.is_file(), 'rom/dq5.sfc 가 필요')
    def test_dung_sells_and_stays(self):
        import dq5item
        rom = dq5item.Rom(DQ5_ROM.read_bytes())
        k1 = [w for w in dq4itemport.price_writes(rom, F.HORSE_DUNG, 2, 'うまのふん')]
        self.assertEqual(k1[0]['hex'], '02')
        self.assertEqual(int(k1[1]['hex'], 16) & dq4itemport.CONSUMED, 0)


if __name__ == '__main__':
    unittest.main()
