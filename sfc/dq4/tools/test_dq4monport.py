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
        self.assertEqual(len(self.writes), len(dq4monport.PORT))
        for fc in [*dq4monport.PORT, *dq4monport.EVENT]:
            dq4monport.fc_entry(self.prg, fc)

    def test_every_action_is_one_a_dq5_monster_uses(self):
        import dq4ch1walkcheck as wc
        used = {b for n in range(236) for b in self.dq5[wc.MONSTERS + n * 25 + 17:wc.MONSTERS + n * 25 + 23]}
        for fc, a in dq4monport.fc_actions().items():
            self.assertIn(int(a, 16), used, f'FC {fc:02X} → {a}')

    def test_spell_mp_keeps_fc_cast_count(self):
        # べビーマジシャン: FC MP 2, ヒャド FC 2 → DQ5 몬스터 ヒャド(42) 3. FC 대로면 한 번도 못 외운다
        self.assertEqual(self.entry(dq4monport.PORT[0x1D])['MP'], 3)
        self.assertEqual(dq4monport.fc_entry(self.prg, 0x1D)['MP'], 2)
        # メラゴースト: メラ 는 FC·DQ5 모두 2 라 그대로
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
        self.assertEqual(e['내성'], placeholder['내성'])
        self.assertEqual(e['f68'], placeholder['f68'])

    def test_drops_follow_fc(self):
        slime = self.entry(dq4monport.PORT[0x00])
        self.assertEqual((slime['드롭'], slime['드롭률']), ('A1', 5))      # やくそう 2/256
        # とさかへび 의 FC 드롭(DQ5 에 같은 이름이 없는 물건)은 떨어뜨리지 않는다
        self.assertEqual(self.entry(dq4monport.PORT[0x20])['드롭'], 'FF')

    def test_metal_defence_is_capped(self):
        self.assertEqual(self.entry(dq4monport.PORT[0x5C])['수비'], 0x1FF)


if __name__ == '__main__':
    unittest.main()
