import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dq4party as party  # noqa: E402
import dq4growth  # noqa: E402

HAVE_ROMS = party.DQ4.exists() and party.DQ5.exists()


def run_equip(data, labels, person, item, flag_on, table, dq5_bits=0x5A):
    """장비 훅을 명령 하나씩 따라 돈다(M·X 8, 이 훅이 쓰는 명령만). (RTL 때 Z 가 꺼져 있는지 = 장비 가능, 지난 길
    'fc'·'dq5'). DQ5 길의 23:B591 값은 dq5_bits, 21:A632 는 모든 비트가 켜진 것으로 본다."""
    pc = labels['equip'] - party.EQUIP_AT
    a, x, z, stack, path = 0, item, False, [], None
    signed = lambda b: b - 0x100 if b & 0x80 else b  # noqa: E731
    marks = {labels['dq5'] - party.EQUIP_AT: 'dq5', labels['fc'] - party.EQUIP_AT: 'fc'}
    while True:
        path = marks.get(pc, path)
        op = data[pc]
        if op == 0xA5:                                   # LDA $4B
            a, pc = person, pc + 2
            z = a == 0
        elif op == 0xAF:
            addr = int.from_bytes(data[pc + 1:pc + 4], 'little')
            a, pc = (dq4growth.CHAPTER2[1] if flag_on else 0) if addr == dq4growth.CHAPTER2[0] else 0, pc + 4
        elif op == 0x29:
            a, pc = a & data[pc + 1], pc + 2
            z = a == 0
        elif op == 0xC9:
            z, pc = a == data[pc + 1], pc + 2
        elif op == 0xA9:
            a, pc = data[pc + 1], pc + 2
        elif op in (0xD0, 0xF0, 0x80):
            take = op == 0x80 or (op == 0xF0) == z
            pc += 2 + (signed(data[pc + 1]) if take else 0)
        elif op == 0x48:
            stack.append(a)
            pc += 1
        elif op == 0xBF:
            addr = int.from_bytes(data[pc + 1:pc + 4], 'little')
            a = table[x] if addr == labels['table'] else (dq5_bits if addr == party.DQ5_EQUIP else None)
            pc += 4
        elif op == 0x23:                                 # AND $01,S
            a, pc = a & stack[-1], pc + 2
        elif op == 0x83:                                 # STA $01,S
            stack[-1], pc = a, pc + 2
        elif op == 0x68:
            a, pc = stack.pop(), pc + 1
            z = a == 0
        elif op == 0xA6:                                 # LDX $4B
            x, pc = person, pc + 2
        elif op == 0x3F:                                 # AND $21A632,X: 사람 비트를 모두 켠 것으로
            a, pc = a & 0xFF, pc + 4
            z = a == 0
        elif op == 0x6B:
            return not z, path
        else:
            raise AssertionError(f'모르는 명령 {op:02X}')


class EquipCodeTest(unittest.TestCase):
    def setUp(self):
        # 물건 n 의 FC 비트 = n(인물 번호 비트가 물건마다 다르게)
        self.table = list(range(party.ITEM_COUNT))
        self.data, self.labels = party.equip_code(self.table)

    def test_original_path_is_kept(self):
        o = self.labels['dq5'] - party.EQUIP_AT
        self.assertEqual(self.data[o:o + 11], party.EQUIP_ORIG + b'\x6b')

    def test_fc_bits(self):
        alena, kiryl, brey = (1 << w for w in (dq4growth.FC_ALENA, dq4growth.FC_KIRYL, dq4growth.FC_BREY))
        for person, on, bit in ((0, True, alena), (9, False, kiryl), (9, True, kiryl), (5, False, brey)):
            for item in (bit, bit | 1, 0, 0xD7 & ~bit):
                with self.subTest(person=person, item=item):
                    ok, path = run_equip(self.data, self.labels, person, item, on, self.table)
                    self.assertEqual((ok, path), (bool(item & bit), 'fc'))

    def test_chapter_one_hero_and_others_use_dq5_bits(self):
        for person, on in ((0, False), (3, True), (0x0B, True)):
            with self.subTest(person=person):
                ok, path = run_equip(self.data, self.labels, person, 0x80, on, self.table)
                self.assertEqual((ok, path), (True, 'dq5'))
                ok, _ = run_equip(self.data, self.labels, person, 0x80, on, self.table, dq5_bits=0)
                self.assertFalse(ok)

    def test_fits_before_growth(self):
        self.assertLessEqual(party.EQUIP_AT + len(self.data), dq4growth.GROWTH_AT)


class RecruitTest(unittest.TestCase):
    def test_people_match_chapter_two_recruits(self):
        import dq4ch2event as ev
        self.assertEqual(sorted(r['person'] for r in ev.RECRUITS), sorted(party.RECRUITS))
        self.assertEqual({p: w for p, _, w in dq4growth.TABLES if p}, party.RECRUITS)
        self.assertEqual({p for p in party.EQUIP_PEOPLE if p}, set(party.RECRUITS))

    def test_slots_fill_from_zero(self):
        """어느 레벨에서든 배운 칸이 0 부터 빈틈없다(DQ5 주문 창이 그렇게 본다, dq4party.plan)."""
        if not HAVE_ROMS:
            self.skipTest('롬 없음')
        prg, rom = party._fc(), party._dq5()
        for who in party.RECRUITS.values():
            p = party.plan(prg, rom, who)
            for lv in range(1, 100):
                got = {'field': set(), 'battle': set()}
                got['field'] |= {k for k in range(8) if p['start'] >> k & 1}
                got['battle'] |= {k for k in range(12) if p['start'] >> 8 + k & 1}
                for e in p['learn']:
                    if e['level'] <= lv:
                        got['field'] |= set(e['field_slots'])
                        got['battle'] |= set(e['battle_slots'])
                for kind, slots in got.items():
                    self.assertEqual(slots, set(range(len(slots))), (who, lv, kind))

    def test_learn_level(self):
        self.assertEqual(party.learn_level(0x04), 4)
        self.assertEqual(party.learn_level(0x86), 7)


@unittest.skipUnless(HAVE_ROMS, 'rom/dq4.nes·rom/dq5.sfc 가 없음')
class RomTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prg, cls.rom = party._fc(), party._dq5()
        cls.names = {v: k for k, v in party.dq5_spells(cls.rom).items()}

    def lists(self, who):
        p = party.plan(self.prg, self.rom, who)
        return p, [self.names[i] for i in p['battle']], [self.names[i] for i in p['field']]

    def test_kiryl(self):
        p, battle, field = self.lists(dq4growth.FC_KIRYL)
        # 배우는 레벨 차례(FC 창 차례는 スカラ·ホイミ·マヌーサ·ベホイミ…)
        self.assertEqual(battle, ['ホイミ', 'スカラ', 'マヌーサ', 'マホトーン', 'スクルト', 'ベホイミ', 'ザキ', 'ザオラル',
                                  'ザラキ', 'ベホマ', 'ベホマラー', 'ザオリク'])
        self.assertEqual(field, ['ホイミ', 'キアリー', 'ベホイミ', 'ザオラル', 'ベホマ', 'ザオリク'])
        self.assertEqual(p['start'].to_bytes(3, 'little'), bytes((0x01, 0x01, 0x00)))   # ホイミ(필드 0·전투 0)
        self.assertEqual([e['level'] for e in p['learn']], [4, 7, 8, 12, 15, 16, 19, 21, 25, 27, 31, 34])
        self.assertEqual(p['dropped'], [('field', 'ベホマラー', 'DQ5 필드에서 쓰지 못함')])

    def test_brey(self):
        p, battle, field = self.lists(dq4growth.FC_BREY)
        self.assertEqual(battle, ['ヒャド', 'ルカニ', 'マホカンタ', 'ルーラ', 'ヒャダルコ', 'バイキルト', 'ルカナン', 'マホトラ',
                                  'メダパニ', 'マヒャド'])
        self.assertEqual(field, ['リレミト', 'ルーラ', 'ラナルータ', 'インパス'])
        self.assertEqual(p['start'].to_bytes(3, 'little'), bytes((0x00, 0x01, 0x00)))   # ヒャド(전투 0)
        self.assertEqual([e['level'] for e in p['learn']], [3, 8, 9, 11, 18, 19, 22, 24, 26, 31, 32])
        self.assertEqual([d[1] for d in p['dropped']], ['ヒャダイン', 'ピオリム'])

    def test_learned_matches_the_fc_measurement(self):
        """FC 롬에서 그 레벨까지 올려 잰 배운 주문과, DQ5 표로 그 레벨까지 배우는 주문이 같다(DQ5 에 없어 뺀 것 밖)."""
        import dq4data
        import dq4text
        spell = [party._kata(dq4text.text(n)) for n in dq4data.name_list(self.prg, 'spell')]
        for who, rows in party.FC_SPELLS_MEASURED.items():
            p = party.plan(self.prg, self.rom, who)
            dropped = {n for _, n, why in p['dropped'] if why == 'DQ5 에 없는 주문'}
            for lv, bits in rows.items():
                with self.subTest(who=who, level=lv):
                    fc = {spell[s + 1] for s in party.fc_learned(self.prg, who, bits)} - dropped
                    self.assertEqual({spell[s + 1] for s in party.learned_by(p, lv)}, fc)

    def test_equip_table(self):
        table = party.equip_table(self.prg, self.rom)
        alena, kiryl, brey = (1 << w for w in (dq4growth.FC_ALENA, dq4growth.FC_KIRYL, dq4growth.FC_BREY))
        # きぬのローブ(62)는 아리나가 입고 FC 처럼 크리프트·브라이는 못 입는다. 합류 때 장비(dq4ch2event.RECRUITS)는
        # 주인이 입을 수 있다
        self.assertTrue(table[0x62] & alena)
        self.assertFalse(table[0x62] & (kiryl | brey))
        import dq4ch2event as ev
        for r in ev.RECRUITS:
            bit = 1 << party.RECRUITS[r['person']]
            for item in r['items']:
                self.assertTrue(table[item] & bit, f"{r['name']} {item:02X}")
        self.assertTrue(table[ev.SILK_ROBE] & alena)

    def test_learn_doc_passes_the_writer(self):
        import dq5learnwrite as lw
        from dq5map import Rom
        doc = party.learn_doc()
        self.assertEqual([c['index'] for c in doc['characters']], [0, 9, 5])
        lw.patch(Rom(party.DQ5.read_bytes()), doc)


if __name__ == '__main__':
    unittest.main()
