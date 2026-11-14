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
        self.assertEqual(field, ['ホイミ', 'キアリー', 'ベホイミ', 'ザオラル', 'ベホマ', 'ベホマラー', 'ザオリク'])
        self.assertEqual(p['start'].to_bytes(3, 'little'), bytes((0x01, 0x01, 0x00)))   # ホイミ(필드 0·전투 0)
        self.assertEqual([e['level'] for e in p['learn']], [4, 7, 8, 12, 15, 16, 19, 21, 25, 27, 31, 34])
        self.assertEqual(p['dropped'], [])

    def test_brey(self):
        p, battle, field = self.lists(dq4growth.FC_BREY)
        self.assertEqual(battle, ['ヒャド', 'ルカニ', 'マホカンタ', 'ルーラ', 'ヒャダルコ', 'ピオリム', 'バイキルト', 'ルカナン',
                                  'マホトラ', 'ヒャダイン', 'メダパニ', 'マヒャド'])
        self.assertEqual(field, ['リレミト', 'ルーラ', 'ラナルータ', 'インパス'])
        self.assertEqual(p['start'].to_bytes(3, 'little'), bytes((0x00, 0x01, 0x00)))   # ヒャド(전투 0)
        # FC ピオリム 14·ヒャダイン 27 은 지혜로 늦어지는 주문(bit7)이라 한 레벨 뒤
        self.assertEqual([e['level'] for e in p['learn']], [3, 8, 9, 11, 15, 18, 19, 22, 24, 26, 28, 31, 32])
        self.assertEqual(p['dropped'], [])
        self.assertEqual(p['battle'][5], party.PIORIMU)
        self.assertEqual(p['battle'][9], party.HYADAIN)

    def test_learned_matches_the_fc_measurement(self):
        """FC 롬에서 그 레벨까지 올려 잰 배운 주문과, DQ5 표로 그 레벨까지 배우는 주문이 같다(브라이 15레벨의 ピオリム 포함)."""
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
        self.assertEqual([(c['kind'], c['index']) for c in doc['characters']],
                         [('person', 0), ('person', 9), ('person', 5), ('monster', party.SPARE_MONSTER)])
        # 필드 ベホマラー 는 dq5learnwrite 가 받지 않아 자리 표시 주문으로 넘긴다
        self.assertIn(party.FIELD_PLACEHOLDER, doc['characters'][1]['field'])
        self.assertNotIn(party.BEHOMARA, doc['characters'][1]['field'])
        lw.patch(Rom(party.DQ5.read_bytes()), doc)

    def test_spare_monster_is_not_hoimin(self):
        """비우는 몬스터 습득 표는 호이민(ホイミスライム, 회복 주문만 배우는 표)이 아니다."""
        import dq5learnwrite as lw
        from dq5map import Rom
        dump = lw.dump(Rom(party.DQ5.read_bytes()))
        mons = {c['index']: c for c in dump['characters'] if c['kind'] == 'monster'}
        hoimin = [i for i, c in mons.items() if c['battle'] and set(c['battle']) <= set(range(0x27, 0x30))]
        self.assertEqual(hoimin, [5])
        self.assertTrue(mons[party.SPARE_MONSTER]['learn'])

    def test_borrowed_spells(self):
        """빌린 칸은 주인공 쪽 주문(몬스터 쪽 39~ 아님)이고 FC 주문 목록에 없는 DQ5 주문이며, 쓰기가 원래 롬 위에 맞다."""
        import dq4data
        import dq4text
        fc = {party._kata(dq4text.text(n)) for n in dq4data.name_list(self.prg, 'spell')}
        original = party._names(self.rom, party.SPELL_NAMES, party.SPELL_LAST + 1)
        for n, (name, fc_spell, src) in party.BORROWED_SPELLS.items():
            self.assertLess(n, 0x39)
            self.assertNotIn(party._kata(original[n]), fc)
            self.assertIn(name, fc)
        self.assertEqual(party.korean_names(), {0x38: '햐다인', 0x1D: '피오림'})
        writes = party.spell_writes()
        by = {w['at']: w for w in writes}
        self.assertEqual(by['26:879D']['hex'], 'E8')   # ヒャダイン MP 8·적 전체
        self.assertEqual(by['26:8782']['hex'], '63')   # ピオリム MP 3·우리 편 전체
        self.assertEqual(by['27:80A9']['hex'], '3C 15')
        self.assertEqual(by['20:F6BF']['orig'], '20 A1 A0')
        self.assertEqual(by['11:802A']['orig'], '22 80')   # 원래 제자리에서 도는 8022


class SpellCodeTest(unittest.TestCase):
    def test_bank20_fits(self):
        far = party.spell_code()[1]
        data, labels = party.bank20_code(far)
        self.assertLessEqual(party.BANK20_AT + len(data), 0x210000)
        # 처리 루틴 표·실행 루틴은 뱅크 20 의 16비트 주소라 스텁이 뱅크 20 에 있어야 한다
        self.assertTrue(all(v >> 16 == 0x20 for v in labels.values()))
        # 적용 스텁: ピオリム(1D)이 아니면 원래 JSR $A0A1 뒤 20:F6C2 로
        a = labels['apply'] - party.BANK20_AT
        self.assertEqual(data[a:a + 5], bytes.fromhex('ad f7 10 c9 1d'))
        b = labels['apply_dq5'] - party.BANK20_AT
        self.assertEqual(data[b:b + 6], bytes.fromhex('20 a1 a0 4c c2 f6'))

    def test_messages_are_called_from_bank_20(self):
        """메시지 BRK(A4·16)는 뱅크 57 에서 부르면 전투가 멈춘다: 뱅크 57 코드에 BRK A4 가 없다."""
        far = party.spell_code()[1]
        _, labels = party.bank20_code(far)
        data, _ = party.spell_code(bank20=labels)
        self.assertNotIn(bytes.fromhex('00 a4'), data)
        self.assertLessEqual(party.SPELL_AT + len(data), dq4growth.GROWTH_AT)

    def test_field_code_fits(self):
        data, labels = party.field_code(18)
        self.assertLessEqual(party.FIELD_AT + len(data), 0x120000)
        self.assertEqual(data[:2], bytes((0xA9, 18)))
        base, width = party.FC_BEHOMARA
        self.assertIn(bytes((0xA9, width, 0x22, 0x3A, 0x95, 0x00, 0x18, 0x69, base)), data)


if __name__ == '__main__':
    unittest.main()
