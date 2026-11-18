import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT / 'sfc' / 'dq5' / 'tools'), str(ROOT / 'fc' / 'dq4' / 'tools')]

import dq4monport  # noqa: E402

DQ4, DQ5 = ROOT / 'rom' / 'dq4.nes', ROOT / 'rom' / 'dq5.sfc'
# DQ5 몬스터 행동 번호: 39~65 몬스터용 주문, 66~AA 특기(dq5-data-format 「주문과 행동」), AE~B5 부르기(20:D9D6),
# C6~CA 이 해킹이 더한 FC 행동(dq4monspecial)
MONSTER_ACTIONS = (*range(0x39, 0xAB), *range(0xAE, 0xB6), *range(0xC6, 0xCB))


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
        import dq4monspecial
        for fc, a in dq4monport.fc_actions().items():
            if fc not in dq4monspecial.FC_ACTIONS:
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

    def test_chapter1_numbers_were_free(self):
        # 1장 셋의 DQ5 번호는 이 해킹이 쓰지 않고 부르기·격투장·동료·빈 레코드·겹치는 이름·FC 같은 이름이 아닌 번호에서
        numbers = {m for m, _ in dq4monport.CH1.values()}
        before = dq4monport.free_numbers(self.dq5, self.prg, dq4monport.used_numbers() - numbers)
        self.assertLessEqual(numbers, set(before))
        after = dq4monport.free_numbers(self.dq5, self.prg)
        self.assertFalse(numbers & set(after))
        self.assertEqual(len(before) - len(after), len(numbers))
        self.assertGreaterEqual(len(after), 60)

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
        # なかまをよぶ 둘은 같은 몬스터 부르기(B5), がったい 넷은 DQ5 がったいだ(6F)
        self.assertEqual([e[f'행동{k}'] for k in range(1, 7)], ['B5'] * 2 + ['6F'] * 4)
        self.assertEqual(e['내성'][:15], '111121100200000')

    def test_merged_king_slime_takes_fc_values(self):
        # 합체로 나오는 FC 30 キングスライム 은 DQ5 6F 가 바꾸는 6B 에 FC 값(대역 없이 제 레코드 바탕)
        import dq4fieldencounter
        king = dq4monport.MERGED[0x30][0]
        self.assertEqual(king, self.dq5[0x20 * 0x8000 + (0xCC49 & 0x7FFF)])     # 20:CC48 LDA #6B
        writes = dq4monport.record_writes(self.dq5, dq4fieldencounter.PLACEHOLDERS, self.prg)
        self.assertTrue(any(w['at'] == f'23:{0x8000 + king * 25:04X}' for w in writes))
        e = dq4monport.fc_entry(self.prg, 0x30, dq4monport.drop_items(self.prg, self.dq5))
        self.assertEqual((e['HP'], e['공격'], e['수비']), (150, 40, 24))

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

    def test_summons_follow_fc(self):
        # FC 행동 ID 5C(레코드 4B)는 14:$8646[ID − 5C] 를 14:$B2D5 에서 찾은 몬스터를 부른다: 첫 칸 0F → 14 ホイミスライム.
        # 59(레코드 48)는 부른 몬스터의 무리 몬스터 $6E45,X(11:$A11B)
        def rd(bank, addr, n=1):
            o = bank * 0x4000 + (addr & 0x3FFF)
            return bytes(self.prg[o:o + n])
        table = rd(0x14, 0xB2D5, 0x100)
        self.assertEqual(table.index(rd(0x14, 0x8646)[0]), dq4monport.SUMMON_FIXED_FC)
        self.assertEqual(rd(0x11, 0xA11B, 3), bytes((0xBD, 0x45, 0x6E)))
        self.assertEqual(dq4monport.fc_actions()[0x48], f'{dq4monport.SUMMON_SAME:02X}')
        self.assertEqual(dq4monport.fc_actions()[0x4B], f'{dq4monport.SUMMON_FIXED:02X}')

    def test_summon_slots_are_unused_by_this_hack(self):
        # 고쳐 쓰는 DQ5 부르기 칸은 이 해킹이 쓰는 DQ5 몬스터(대역 포함)의 원래 레코드가 쓰지 않는다
        import dq5monlimits
        from dq5map import Rom
        rom = Rom(self.dq5)
        for m in dq4monport.used_numbers():
            acts = [rom.u8(dq5monlimits.MONSTER_RECORDS + m * dq5monlimits.MONSTER_SIZE + 0x11 + i) for i in range(6)]
            if m not in dq4monport.field_numbers().values():
                self.assertFalse({dq4monport.SUMMON_SAME, dq4monport.SUMMON_FIXED} & set(acts), hex(m))

    def test_tsuukon_damage_is_fc(self):
        # 20:B587 훅을 65816 해석기로: 행동 74 면 회심 피해가 FC 11:$9906 식 공격력 × (64 + r) / 64(r = rand(11)),
        # 같은 루틴의 みなごろし 8A 는 원래 명령(LDA $46 / STA $71). rand 는 00:953A 를 값으로 바꿔 끼움
        import w65816
        from dq5map import lorom

        class Done(Exception):
            pass
        rom = bytearray(self.dq5) + bytes(max(0, 0x400000 - len(self.dq5)))
        for w in dq4monport.crit_writes(self.dq5):
            at = int(w['at'][:2], 16) << 16 | int(w['at'][3:], 16)
            data = bytes.fromhex(w['hex'])
            rom[lorom(at):lorom(at) + len(data)] = data
        rom = bytes(rom)
        entry = dq4monport.crit_code()[1]['crit']

        def run(attack, action, r):
            c = w65816.Cpu(rom, bytearray(0x20000))
            c.p, c.dbr = 0x30, 0x7E
            c.wram[0x46], c.wram[0x47], c.wram[0x10F7] = attack & 0xFF, attack >> 8, action

            def rand(cpu):
                self.assertEqual(cpu.a & 0xFF, dq4monport.CRIT_SPREAD)
                cpu.a = cpu.a & 0xFF00 | r
                cpu.rtl()
                return True

            def done(cpu):
                raise Done(cpu.wram[0x10EC] | cpu.wram[0x10ED] << 8)
            c.hooks[dq4monport.RAND] = rand
            c.hooks[dq4monport.CRIT_STORE] = done
            try:
                c.jsl(entry)
            except Done as d:
                return d.args[0]
            return ('original', c.wram[0x71])
        for attack in (1, 40, 63, 64, 255, 256, 999):
            for r in range(dq4monport.CRIT_SPREAD):
                self.assertEqual(run(attack, dq4monport.CRIT_ACTION, r), attack * (64 + r) // 64, (attack, r))
        self.assertEqual(run(40, 0x8A, 0), ('original', 40))

    def test_tsuukon_slot_is_only_fc(self):
        # 74 를 원래 레코드로 쓰는 DQ5 대역이 이 해킹에 없어야 74 를 FC 식으로 바꿀 수 있다
        import dq5monlimits
        from dq5map import Rom
        rom = Rom(self.dq5)
        ported = set(dq4monport.field_numbers().values())
        for m in dq4monport.used_numbers() - ported:
            acts = [rom.u8(dq5monlimits.MONSTER_RECORDS + m * dq5monlimits.MONSTER_SIZE + 0x11 + i) for i in range(6)]
            self.assertNotIn(dq4monport.CRIT_ACTION, acts, hex(m))
        self.assertEqual({k for k, v in dq4monport.fc_actions().items() if v == f'{dq4monport.CRIT_ACTION:02X}'}, {0x33})

    def test_summon_writes_patch_the_handlers(self):
        import dq4fieldencounter
        writes = dq4monport.summon_writes(self.dq5)
        code = bytes.fromhex(writes[0]['hex'])
        self.assertLess(dq4monport.SUMMON_CODE_AT >> 16, 0x40)    # BRK 88 을 쓰므로
        self.assertEqual(code[-4:], bytes((0x5C, *dq4monport.SUMMON_COMMON.to_bytes(3, 'little'))))
        fixed, same = (bytes.fromhex(w['hex']) for w in writes[1:])
        self.assertEqual(fixed[:2], bytes((0xA9, dq4fieldencounter.MONSTERS[dq4monport.SUMMON_FIXED_FC])))
        self.assertEqual(same, bytes((0x5C, *dq4monport.SUMMON_CODE_AT.to_bytes(3, 'little'))))
        o = (dq4monport.SUMMON_CODE_AT >> 16) * 0x8000 + (dq4monport.SUMMON_CODE_AT & 0x7FFF)
        self.assertEqual(set(self.dq5[o:o + len(code)]), {0})


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
