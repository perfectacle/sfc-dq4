import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT / 'sfc' / 'dq5' / 'tools'), str(ROOT / 'fc' / 'dq4' / 'tools')]

import dq4monport  # noqa: E402

DQ4, DQ5 = ROOT / 'rom' / 'dq4.nes', ROOT / 'rom' / 'dq5.sfc'
# DQ5 몬스터 행동 번호: 39~65 몬스터용 주문, 66~AA 특기(dq5-data-format 「주문과 행동」)
MONSTER_ACTIONS = range(0x39, 0xAB)


class ActionTableTests(unittest.TestCase):
    def test_every_mapped_action_is_a_monster_action(self):
        for fc, dq5 in dq4monport.fc_actions().items():
            self.assertIn(int(dq5, 16), MONSTER_ACTIONS, f'FC {fc:02X} → {dq5}: 일행 주문 번호면 전투가 멈춘다')

    def test_event_tables_do_not_disagree(self):
        import dq4ch1event
        table = dq4monport.fc_actions()
        for k, v in dq4ch1event.FC_ACTIONS.items():
            self.assertEqual(table[k], v)


@unittest.skipUnless(DQ4.exists() and DQ5.exists(), 'rom/dq4.nes and rom/dq5.sfc')
class RecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import dq4fieldencounter
        from kr_patch.fc import ines
        cls.prg = ines.prg(DQ4.read_bytes())
        cls.dq5 = DQ5.read_bytes()
        cls.writes = {w['at']: w for w in dq4monport.record_writes(cls.dq5, dq4fieldencounter.PLACEHOLDERS, cls.prg)}

    def entry(self, m):
        import dq5tables
        from dq5map import lorom
        at = dq4monport.RECORD + m * dq4monport.RECORD_SIZE
        data = bytearray(self.dq5)
        record = self.writes[f'{at >> 16:02X}:{at & 0xFFFF:04X}']['hex']
        data[lorom(at):lorom(at) + dq4monport.RECORD_SIZE] = bytes.fromhex(record)
        return dq5tables.decode(dq5tables.TABLES['monsters'], None, data, m)

    def test_every_field_monster_has_a_record_and_every_action_maps(self):
        self.assertEqual(len(self.writes), len(dq4monport.field_numbers()))
        for fc in [*dq4monport.field_numbers(), *dq4monport.EVENT]:
            dq4monport.fc_entry(self.prg, fc)

    def test_every_action_is_one_a_dq5_monster_uses(self):
        import dq4ch1walkcheck as wc
        used = {b for n in range(236) for b in self.dq5[wc.MONSTERS + n * 25 + 17:wc.MONSTERS + n * 25 + 23]}
        for fc, a in dq4monport.fc_actions().items():
            self.assertIn(int(a, 16), used, f'FC {fc:02X} → {a}')

    def test_chapter3_numbers_take_fc_values_and_the_placeholder_picture(self):
        # 3장 새 종: 2장 예비였던 번호에 FC 능력치, 그림 레코드 포인터는 대역 것(그림·색·무리 한도가 지금 대역과 같음)
        import dq4ch2slots
        import dq4fieldencounter
        import dq5mongfx
        from dq5map import Rom
        numbers = [m for m, _ in dq4monport.CH3.values()]
        self.assertEqual(len(set(numbers)), len(numbers))
        self.assertFalse(set(numbers) & {*dq4monport.PORT.values(), *dq4monport.EVENT.values()})
        self.assertFalse(set(numbers) & set(dq4ch2slots.SPARE['monsters']))
        for fc, (m, _) in dq4monport.CH3.items():
            self.assertEqual(self.entry(m)['HP'], dq4monport.fc_entry(self.prg, fc)['HP'])
        data = bytearray(self.dq5)
        for w in dq4monport.picture_writes(self.dq5, dq4fieldencounter.PLACEHOLDERS):
            bank, addr = (int(v, 16) for v in w['at'].split(':'))
            o = (bank & 0x7F) * 0x8000 + (addr & 0x7FFF)
            data[o:o + 2] = bytes.fromhex(w['hex'])
        rom = Rom(bytes(data))
        for fc, (m, _) in dq4monport.CH3.items():
            self.assertEqual(dq5mongfx.monster(rom, m), dq5mongfx.monster(Rom(self.dq5),
                                                                       dq4fieldencounter.PLACEHOLDERS[fc]))
        names = dq4monport.korean_names()
        self.assertEqual(names[dq4monport.CH3[0x13][0]], '킬러 스콥')
        self.assertEqual(names[dq4monport.CH3[0x1E][0]], '릴리펏')

    def test_monster_mp_is_fc(self):
        # べビーマジシャン: FC MP 2. 주문 MP 를 FC 값(ヒャド 2)으로 두므로 MP 를 올리지 않는다
        self.assertEqual(self.entry(dq4monport.PORT[0x1D])['MP'], 2)
        self.assertEqual(self.entry(dq4monport.PORT[0x0D])['MP'], 2)


    def test_mera_ghost_gets_fc_values_over_placeholder(self):
        import dq4fieldencounter
        import dq5tables
        e = self.entry(dq4monport.PORT[0x0D])
        self.assertEqual((e['HP'], e['MP'], e['공격'], e['수비'], e['민첩'], e['경험치'], e['금화']),
                         (12, 2, 11, 12, 8, 6, 16))
        self.assertEqual([e[f'행동{k}'] for k in range(1, 7)], ['39'] * 5 + ['73'])
        self.assertEqual(e['동료확률'], 0)
        placeholder = dq5tables.decode(dq5tables.TABLES['monsters'], None, self.dq5,
                                       dq4fieldencounter.PLACEHOLDERS[0x0D])
        # FC 내성 ギラ1 メラ3 バギ1 マヌーサ2 ラリホー3 ザキ2 ニフラム1 マホトラ2 マホトーン1 을 DQ5 종류 50~5E 에, 5F~61 은 대역 것
        self.assertEqual(e['내성'][:15], '310010232102100')
        self.assertEqual(e['내성'][15:], placeholder['내성'][15:])
        self.assertNotEqual(e['내성'], placeholder['내성'])
        self.assertEqual(e['f68'], placeholder['f68'])

    def test_second_slime_gets_its_own_number_and_fc_values(self):
        # FC 04 スライム(엔돌 쪽 구역 10~12)는 DQ5 슬라임 00 대역이 아니라 제 번호에 FC 값
        self.assertNotIn(dq4monport.PORT[0x04], (0x00, dq4monport.PORT[0x00]))
        e = self.entry(dq4monport.PORT[0x04])
        self.assertEqual((e['HP'], e['MP'], e['공격'], e['수비'], e['민첩'], e['경험치'], e['금화']),
                         (40, 0, 0, 30, 15, 3, 1))
        # なかまをよぶ·がったい 는 메시지만 나오는 ようすをみる
        self.assertEqual([e[f'행동{k}'] for k in range(1, 7)], ['66'] * 6)
        self.assertEqual(e['내성'][:15], '111121100200000')

    def test_drops_follow_fc(self):
        slime = self.entry(dq4monport.PORT[0x00])
        self.assertEqual((slime['드롭'], slime['드롭률']), ('A1', 5))      # やくそう 2/256
        # とさかへび 의 はねぼうし 는 빌린 자리(dq4itemport.BORROWED) 8C
        self.assertEqual(self.entry(dq4monport.PORT[0x20])['드롭'], '8C')

    def test_drop_items_dq5_lacks_have_slots(self):
        of = dq4monport.drop_items(self.prg, self.dq5)
        # FC てつのつめ·きんのかみかざり·はねぼうし: 가타카나로 같은 DQ5 てつのツメ, 빌린 자리 둘
        self.assertEqual((of(0x03), of(0x4D), of(0x4A)), (0x2F, 0x89, 0x8C))

    def test_event_entry_takes_fc_resists(self):
        e = dq4monport.fc_entry(self.prg, 0xB1)
        self.assertEqual(len(e['내성']), 18)
        self.assertEqual(e['내성'][15:], '000')

    def test_metal_defence_is_capped(self):
        self.assertEqual(self.entry(dq4monport.PORT[0x5C])['수비'], 0x1FF)


@unittest.skipUnless(DQ4.exists() and DQ5.exists(), 'rom/dq4.nes and rom/dq5.sfc')
class SpellMpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import dq5tables
        from dq5map import lorom
        from kr_patch.fc import ines
        cls.prg = ines.prg(DQ4.read_bytes())
        cls.dq5 = DQ5.read_bytes()
        cls.entries = dq4monport.spell_entries(cls.prg)
        cls.writes = dq5tables.writes_for([{'format': dq5tables.FORMAT, 'spells': cls.entries}], cls.dq5)
        cls.patched = bytearray(cls.dq5)
        for off, new, _, _ in cls.writes:
            cls.patched[off] = new
        cls.lorom = staticmethod(lorom)

    def mp(self, data, n):
        import dq5spell
        from dq5map import Rom
        return dq5spell.cost(Rom(bytes(data)), n)[0]

    def test_changed_spells_get_fc_mp(self):
        # ヒャド 3 → 2, ラリホーマ 5 → 3, マヌーサ 5 → 4. 나머지 1·2장 몬스터 주문은 FC·DQ5 가 같다
        self.assertEqual({(n, self.mp(self.dq5, n), self.mp(self.patched, n))
                          for n in range(0x39, 0x66) if self.mp(self.dq5, n) != self.mp(self.patched, n)},
                         {(0x42, 3, 2), (0x4C, 5, 3), (0x4E, 5, 4), (0x55, 2, 3)})

    def test_party_spell_mp_unchanged(self):
        import dq5tables
        battle = {self.lorom(0x268765 + n) for n in dq4monport.MONSTER_SPELLS}
        menu = {self.lorom(dq5tables.MENU_MP + n) for n in dq4monport.MONSTER_SPELLS}
        self.assertTrue(self.writes)
        for off, *_ in self.writes:
            self.assertIn(off, battle | menu, f'{off:X}: 몬스터용 주문 밖을 씀')
        for n in range(1, 0x39):
            self.assertEqual(self.mp(self.patched, n), self.mp(self.dq5, n), f'일행 주문 {n:02X}')
            self.assertEqual(self.patched[self.lorom(dq5tables.MENU_MP + n)], self.dq5[self.lorom(dq5tables.MENU_MP + n)])

    def test_every_monster_casts_as_often_as_in_fc(self):
        import dq4ch1event
        import dq4data
        actions = dq4monport.fc_actions()
        fcs = {*dq4monport.PORT, *dq4monport.EVENT, *(fc for fc, _ in dq4ch1event.BOSS_MONSTERS.values())}
        for i, _, _, _, r in dq4data.monsters(self.prg):
            if i not in fcs:
                continue
            for n in {b & 0x7F for b in r[9:15]}:
                if n >= dq4data.MON_ACT[2]:
                    continue
                fc_cost = dq4data.spell_mp(self.prg, dq4data.monster_action(self.prg, n))[0]
                cost = self.mp(self.patched, int(actions[n], 16))
                self.assertEqual(cost, fc_cost, f'FC {i:02X} 행동 {n:02X}')
                self.assertGreaterEqual(r[3] // cost, 1, f'FC {i:02X} 행동 {n:02X}: MP {r[3]} 로 한 번도 못 외움')

    def test_conflicting_fc_mp_is_refused(self):
        from unittest import mock
        # FC ヒャド 2 와 ラリホーマ 3
        with mock.patch.object(dq4monport, 'fc_actions', return_value={0x07: '42', 0x11: '42'}):
            with self.assertRaises(ValueError):
                dq4monport.spell_entries(self.prg)


if __name__ == '__main__':
    unittest.main()
