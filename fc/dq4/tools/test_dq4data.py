"""이름 목록·아이템·몬스터·주문 표 읽기(목록 경계·가격 자릿수·장비 조건·9비트 값·행동 번호 갈래·확률 표)를
합성 PRG 로 검사한다."""
import unittest

import dq4data as d

PRG_SIZE = 32 * 0x4000


def put(prg, bank, addr, data):
    o = bank * 0x4000 + (addr & 0x3FFF)
    prg[o:o + len(data)] = bytes(data)


def word(v):
    return [v & 0xFF, v >> 8]


def names_prg():
    prg = bytearray(PRG_SIZE)
    ptrs = {w: 0xA000 + 0x40 * i for i, w in enumerate(d.LISTS)}
    ptrs['item'] = 0xA0C0
    put(prg, d.NAMES_BANK, d.NAMES_PTR, [v for w in d.LISTS for v in word(ptrs[w])])
    # 아이템: 빈 이름(0번) + 둘, 뒤 빈 이름 하나는 버린다. 다음 목록(monster) 시작 A100 에서 끝난다
    put(prg, d.NAMES_BANK, 0xA0C0, [0, 2, 0x10, 0x11, 1, 0x12])
    put(prg, d.NAMES_BANK, 0xA0C6, [1, 0x05] * 29)                    # 다음 목록 A100 바로 앞까지
    put(prg, d.NAMES_BANK, 0xA100, [0x01, 0x13])
    return prg


class NameTests(unittest.TestCase):
    def test_list_ends_at_next_list_and_drops_blank_tail(self):
        prg = names_prg()
        put(prg, d.NAMES_BANK, 0xA0C6, [1, 0x00, 0x11])   # 길이 바이트가 10 을 넘으면 끝, 끝의 빈 이름은 버림
        self.assertEqual(d.name_list(prg, 'item'), [[], [0x10, 0x11], [0x12]])

    def test_list_stops_at_pointer_boundary(self):
        prg = names_prg()
        names = d.name_list(prg, 'item')
        self.assertEqual(len(names), 3 + 29)
        self.assertEqual(names[-1], [0x05])
        self.assertEqual(d.name_list(prg, 'monster'), [[0x13]])

    def test_items_price_scale_and_kind(self):
        prg = names_prg()
        put(prg, d.NAMES_BANK, 0xA0C6, [0x11])
        put(prg, d.ITEM_BANK, d.ITEM_PRICE, [0x8C, 0x05])
        put(prg, d.ITEM_BANK, d.ITEM_SCALE, [0x02, 0x00])
        put(prg, d.ITEM_BANK, d.ITEM_POWER, [7, 9])
        self.assertEqual(d.items(prg), [(0, 'かき', 7, 1200, 1), (1, 'く', 9, 5, 0)])
        put(prg, d.ITEM_BANK, d.EQUIP_KIND, [0x24, 0x3D, 0x46, 0x50])
        self.assertEqual([d.item_kind(prg, i) for i in (0x00, 0x24, 0x3C, 0x46, 0x50)], [0, 1, 1, 3, 4])


class EquipTests(unittest.TestCase):
    def setUp(self):
        self.prg = bytearray(PRG_SIZE)
        put(self.prg, d.ITEM_BANK, d.EQUIP_MASK + 0x30, [0xFF])
        put(self.prg, d.ITEM_BANK, d.EQUIP_MASK + 0x01, [0b0000_0101])

    def test_mask_bit_per_person(self):
        self.assertTrue(d.can_equip(self.prg, 0x01, 0))
        self.assertFalse(d.can_equip(self.prg, 0x01, 1))
        self.assertTrue(d.can_equip(self.prg, 0x01, 2))

    def test_dress_needs_female(self):
        self.assertTrue(d.can_equip(self.prg, 0x30, 2))
        self.assertFalse(d.can_equip(self.prg, 0x30, 1))
        self.assertFalse(d.can_equip(self.prg, 0x30, 0))
        self.assertTrue(d.can_equip(self.prg, 0x30, 0, heroine=True))

    def test_out_of_range(self):
        self.assertFalse(d.can_equip(self.prg, 0x53, 0))
        self.assertFalse(d.can_equip(self.prg, 0x01, 8))


class MonsterTests(unittest.TestCase):
    def test_nine_bit_values_take_high_bits_from_15_to_18(self):
        r = bytes([0x34, 0x12, 5, 6, 0xFF, 0x10, 0x20, 0x30, 0x85,
                   0x81, 0x82, 0x03, 0x84, 0x05, 0x86, 0x01, 0x02, 0x03, 0x01, 0, 0xC5, 0x6B])
        f = d.monster_fields(r)
        self.assertEqual((f['exp'], f['hp'], f['atk'], f['def'], f['gold']), (0x1234, 0x1FF, 0x210, 0x320, 0x130))
        self.assertEqual((f['drop'], f['drop_rate'], f['ai']), (0x05, 5, 3))
        self.assertEqual(f['actions'], [1, 2, 3, 4, 5, 6])
        self.assertEqual((f['select'], f['count'], f['f21']), (3, 2, 2))
        self.assertEqual((f['f26'], f['f27'], f['f28']), (1, 5, 3))
        self.assertEqual(len(f['resist_fields']), 15)

    def test_action_number_ranges(self):
        prg = bytearray(PRG_SIZE)
        put(prg, d.MON_ACT[0], d.MON_ACT[1] + 3, [0x44])
        self.assertEqual([d.monster_action(prg, n) for n in (3, 0x2A, 0x2B)], [0x44, 0xF7, 0x3C])

    def test_resists_follow_slot_table(self):
        prg = bytearray(PRG_SIZE)
        put(prg, d.FX_BANK, d.RESIST_SLOT, [5] + [0] * 14)
        r = bytearray(22)
        r[16] = 0b0000_1100            # 필드 5 = 바이트 16 bit3-2
        self.assertEqual(d.resists(prg, r)[0], 3)

    def test_start_status(self):
        prg = bytearray(PRG_SIZE)
        put(prg, *d.START_STATUS, [9, 19])
        self.assertEqual(d.start_status(prg, bytes(21) + bytes([0x48])), ('마비', 20))
        self.assertIsNone(d.start_status(prg, bytes(21) + bytes([0x38])))
        self.assertIsNone(d.start_status(prg, bytes(21) + bytes([0xC0])))


class EffectTests(unittest.TestCase):
    def setUp(self):
        self.prg = prg = bytearray(PRG_SIZE)
        lo, hi, n = d.POWER_MAP
        put(prg, d.FX_BANK, lo, [0x80] + [0xFE] * (n - 1))
        put(prg, d.FX_BANK, hi, [0x03])
        put(prg, d.FX_BANK, d.POWER + 2 * 3, [10, 20])
        put(prg, d.FX_BANK, d.POWER + 2 * 3 + 0x38, [30, 40])
        put(prg, d.FX_BANK, d.POWER + 2 * 0x10, [1, 2])

    def test_power_mapping(self):
        self.assertEqual(d.power(self.prg, 0x80, False), (10, 20))
        self.assertEqual(d.power(self.prg, 0x80, True), (30, 40))
        put(self.prg, d.FX_BANK, d.POWER + 2 * 0x13, [7, 8])
        self.assertEqual(d.power(self.prg, 0x4D, False), (7, 8))      # 4D-6C 는 − 3A
        self.assertEqual(d.power(self.prg, 0x10, False), (1, 2))
        self.assertIsNone(d.power(self.prg, 0x6D, False))
        self.assertEqual(d.power(self.prg, 0x12, False)[0], 0x14A)    # 칸 12 = 편의 ミナデイン

    def test_heal_full_width(self):
        ids, idx, n, tab = d.HEAL
        put(self.prg, d.FX_BANK, ids, [0x20, 0x21])
        put(self.prg, d.FX_BANK, idx, [0, 1])
        put(self.prg, d.FX_BANK, tab, [30, 0xFF, 5, 10])
        self.assertEqual(d.heal(self.prg, 0x20), (30, None))
        self.assertEqual(d.heal(self.prg, 0x21), (5, 10))
        self.assertIsNone(d.heal(self.prg, 0x22))

    def test_success_and_resist_rows(self):
        put(self.prg, d.FX_BANK, d.SUCCESS, [0xE3, 0x41, 0x12])
        put(self.prg, d.FX_BANK, d.RESIST_SLOT + 0x12, [0x99])
        self.assertEqual(d.success(self.prg, 0), (256, ('내성', 3)))
        self.assertEqual(d.success(self.prg, 1), (0x40, ('내성', 1)))
        self.assertEqual(d.success(self.prg, 2), (0, ('고정', 0x99)))
        put(self.prg, d.FX_BANK, d.RESIST_RATE, [1, 2, 3, 4, 5, 6, 7, 8])
        self.assertEqual(d.resist_rates(self.prg, 0x18), [5, 6, 7, 8])
        self.assertEqual(d.resist_rates(self.prg, 0x10), [1, 2, 3, 4])

    def test_item_action_default(self):
        lo, hi, _ = d.ITEM_ACT
        put(self.prg, d.ACT_BANK, lo, [0x05])
        put(self.prg, d.ACT_BANK, hi, [0x33])
        self.assertEqual(d.item_action(self.prg, 0x05), 0x33)
        self.assertEqual(d.item_action(self.prg, 0x06), 0x7F)

    def test_regen_drop_spell(self):
        put(self.prg, *d.REGEN, [0, 0, 8, 20])
        self.assertIsNone(d.regen(self.prg, 0))
        self.assertEqual(d.regen(self.prg, 1), (20, 27))
        put(self.prg, *d.DROP_RATE, [0, 8, 0, 0, 0, 0, 0, 16])
        self.assertEqual([d.drop_chance(self.prg, r) for r in (0, 1, 7)], ['1', '8/256', '16/4096'])
        put(self.prg, d.SPELL_BANK, d.SPELL_MP, [0xC5])
        self.assertEqual(d.spell_mp(self.prg, 0), (5, 2, 1))

    def test_learnset_counts_bits_in_order(self):
        put(self.prg, d.GROW_BANK, d.LEARN_MASK + 2, word(0xA400))
        put(self.prg, d.GROW_BANK, d.LEARN_LEVEL + 2, word(0xA500))
        put(self.prg, d.GROW_BANK, 0xA400, [0b1000_0010, 0, 0, 0, 0, 0, 0, 0x01])
        put(self.prg, d.GROW_BANK, 0xA500, [3, 9, 0x8C])
        self.assertEqual(d.learnset(self.prg, 1), {1: 3, 7: 9, 56: 0x8C})
        self.assertEqual(d.learnset(self.prg, 5), {})

    def test_ai_tables(self):
        put(self.prg, d.AI_BANK, d.AI_ITEM_GROUPS, word(0xA800) + word(0xA810) * 3)
        put(self.prg, d.AI_BANK, 0xA800, [1, 2, 0x34, 0x12, 0xFF])
        put(self.prg, d.AI_BANK, 0xA810, [0xFF])
        self.assertEqual(d.ai_item_groups(self.prg), [[(1, 2, 0x1234)], [], [], []])
        self.assertTrue(d.k_used(3, 11))
        self.assertFalse(d.k_used(4, 11))
        put(self.prg, d.AI_BANK, 0xBA74 + 7 * 2 + 3 + 1, [0x55])
        self.assertEqual(d.tactic_value(self.prg, 0xBA74, 2, 3), 0x55)


if __name__ == '__main__':
    unittest.main()
