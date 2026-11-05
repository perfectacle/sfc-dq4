"""숨김 루틴의 기호 실행(dq4shop.hide_paths)과 조건 다루기를 합성 PRG 로 검사한다."""
import unittest

import dq4map
import dq4shop as s
from test_dq4shop import PRG_SIZE, put, word

FLAG5 = f'${dq4map.FLAGS + 5:04X}&40'
NIGHT = ('시간', '≥', dq4map.NIGHT)
DAY = ('시간', '<', dq4map.NIGHT)


def routine(code, at=0x8000, extra=()):
    prg = bytearray(PRG_SIZE)
    put(prg, s.HIDE_BANK, at, code)
    for addr, data in extra:
        put(prg, s.HIDE_BANK, addr, data)
    return prg


def jsr(a):
    return [0x20] + word(a)


class HidePathTests(unittest.TestCase):
    def test_night_check_splits_into_day_and_night(self):
        prg = routine(jsr(s.IS_NIGHT) + [0x90, 0x05, 0xA2, 0x03] + jsr(s.HIDE_SLOT) + [0x60])
        self.assertCountEqual(s.hide_paths(prg, 0x8000), [((DAY,), ()), ((NIGHT,), (('hide', 3),))])

    def test_flag_test_set_and_place_with_jmp(self):
        code = [0x00, 0x05, 0xEB, 0x40, 0xD0, 0x04, 0x00, 0x06, 0xCB, 0x01,
                0xA9, 0x10, 0xA0, 0x20, 0xA2, 0x02, 0x4C] + word(s.PLACE_SLOT)
        place = (('pos', 2, 'X', 0x10), ('pos', 2, 'Y', 0x20))
        self.assertCountEqual(s.hide_paths(routine(code), 0x8000), [
            (((FLAG5, '≠', 0),), place),
            (((FLAG5, '=', 0),), (('flag', dq4map.FLAGS + 6, '|=', 1),) + place)])

    def test_a_repeated_compare_cannot_take_the_other_way(self):
        code = [0xA5, 0x45, 0xC9, 0x10, 0xD0, 0x05, 0xC9, 0x10, 0xD0, 0x01, 0x60, 0x60]
        self.assertCountEqual(s.hide_paths(routine(code), 0x8000), [
            ((('주인공 Y', '≠', 0x10),), ()), ((('주인공 Y', '=', 0x10),), ())])

    def test_bank_subroutine_returns_to_the_caller(self):
        prg = routine(jsr(0x8010) + [0xA2, 0x01] + jsr(s.HIDE_SLOT) + [0x60],
                      extra=[(0x8010, [0xA2, 0x07] + jsr(s.HIDE_SLOT) + [0x60])])
        self.assertEqual(s.hide_paths(prg, 0x8000), [((), (('hide', 7), ('hide', 1)))])

    def test_outside_call_and_slot_column_writes(self):
        code = jsr(0xC000) + [0xA2, 0x02, 0xA9, 0x05, 0x9D, 0xE6, 0x6F, 0x8D, 0x00, 0x03, 0xEE, 0x01, 0x03, 0x60]
        [(path, eff)] = s.hide_paths(routine(code), 0x8000)
        self.assertEqual(path, ())
        self.assertEqual(eff, (('call', 'JSR $C000'), ('pos', 2, '그림', 5), ('write', 0x300, 5), ('write', 0x301, '+1')))

    def test_known_values_branch_without_splitting(self):
        code = [0xA9, 0x81, 0x4A, 0xB0, 0x02, 0xA2, 0x09, 0xA2, 0x04, 0xE8] + jsr(s.HIDE_SLOT) + [0x60]
        self.assertEqual(s.hide_paths(routine(code), 0x8000), [((), (('hide', 5),))])

    def test_symbolic_shift_and_bit_tests_become_conditions(self):
        code = [0xAD, 0x5A, 0x61, 0x4A, 0x90, 0x01, 0x60, 0x2C, 0x80, 0x62, 0x30, 0x01, 0x60, 0x60]
        paths = {p for p, _ in s.hide_paths(routine(code), 0x8000)}
        self.assertEqual(paths, {(('장&01', '≠', 0),), (('장&01', '=', 0), ('$6280', '!bit7', 0)),
                                 (('장&01', '=', 0), ('$6280', 'bit7', 0))})

    def test_item_lookup_sets_carry(self):
        code = [0xA9, 0x2C, 0x00, 0x66, 0x73, 0x90, 0x01, 0x60, 0x60]
        paths = {p for p, _ in s.hide_paths(routine(code), 0x8000)}
        self.assertEqual(paths, {(('아이템 2C', '=', 1),), (('아이템 2C', '≠', 1),)})

    def test_runaway_and_unknown_code_raise(self):
        with self.assertRaisesRegex(RuntimeError, '길이 너무 많음'):
            s.hide_paths(routine([0x4C, 0x00, 0x80]), 0x8000, limit=10)
        with self.assertRaisesRegex(RuntimeError, 'SBC 못 다룸'):
            s.hide_paths(routine([0xE9, 0x01]), 0x8000)
        with self.assertRaisesRegex(RuntimeError, '플래그 C 모름'):
            s.hide_paths(routine([0x90, 0x00]), 0x8000)


class TableTests(unittest.TestCase):
    def test_hide_routines_and_chapter_hides_stop_at_bit7(self):
        prg = bytearray(PRG_SIZE)
        put(prg, s.HIDE_BANK, s.HIDE_PLACES, [0x02, 0x01, 0x05, 0x00, 0x80])
        put(prg, s.HIDE_BANK, s.HIDE_PTRS, word(0x9000) + word(0x9100))
        put(prg, s.HIDE_BANK, s.CHAPTER_HIDE, [0x03, 0x00, 0x01, 0x04, 0xFF])
        self.assertEqual(s.hide_routines(prg), [(0x02, 0x01, 0x9000), (0x05, 0x00, 0x9100)])
        self.assertEqual(s.chapter_hides(prg), [(0x03, 0x00, 0x01, 0x04)])


class ConditionTests(unittest.TestCase):
    def test_add_cond_keeps_drops_or_refutes(self):
        p = (('X', '=', 3),)
        self.assertEqual(s.add_cond(p, ('X', '≥', 2)), p)
        self.assertIsNone(s.add_cond(p, ('X', '<', 3)))
        self.assertIsNone(s.add_cond((('X', '≥', 5),), ('X', '=', 3)))
        self.assertEqual(s.add_cond((('X', '≥', 2),), ('X', '=', 3)), (('X', '≥', 2), ('X', '=', 3)))
        self.assertIsNone(s.add_cond((('Y', 'bit7', 0),), ('Y', '!bit7', 0)))

    def test_cond_text(self):
        self.assertEqual([s.cond_text(c) for c in (NIGHT, DAY, ('장', '=', 1), ('장', '≠', 0), (FLAG5, '=', 0),
                                                   (FLAG5, '≠', 0), ('$6280', '!bit7', 0), ('아이템 2C', '=', 1),
                                                   ('아이템 2C', '≠', 1), ('주인공 Y', '≥', 0x10))],
                         ['밤', '낮', '2장', '1장 아님', f'{FLAG5} 꺼짐', f'{FLAG5} 켜짐', '$6280 bit7 꺼짐',
                          '아이템 2C 있음', '아이템 2C 없음', '주인공 Y ≥ 10'])

    def test_atoms_split_masks_by_bit(self):
        self.assertEqual(s.atoms_of(('$6280&41', '=', 0x01)), [[(('bit', '$6280', 0x01), True),
                                                                 (('bit', '$6280', 0x40), False)]])
        self.assertEqual(s.atoms_of(('$6280&41', '≠', 0)), [[(('bit', '$6280', 0x01), True)],
                                                             [(('bit', '$6280', 0x40), True)]])
        self.assertEqual(s.atoms_of(('장', '<', 2)), [[(('num', '장', '≥', 2), False)]])
        self.assertEqual(s.atoms_of(('$6280', 'bit6', 0)), [[(('bit', '$6280', 0x40), True)]])

    def test_path_dnf_multiplies_the_alternatives(self):
        dnf = s.path_dnf((('$6280&41', '≠', 0), ('장', '=', 1)))
        self.assertEqual(dnf, [[(('bit', '$6280', 0x01), True), (('num', '장', '=', 1), True)],
                               [(('bit', '$6280', 0x40), True), (('num', '장', '=', 1), True)]])


class GuardWalkTests(unittest.TestCase):
    def walk(self, code, pre=()):
        prg = bytearray(PRG_SIZE)
        put(prg, s.CODE_BANK, 0x8000, code)
        found = {}
        s.guard_walk(prg, s.CODE_BANK, 0x8000, pre, found, {})
        return found

    def test_flag_set_records_bits_known_on_every_way(self):
        # BRK 05 EB 40 (검사) · BEQ 끝 · BRK 06 CB 01 (켜기) · RTS
        found = self.walk([0x00, 0x05, 0xEB, 0x40, 0xF0, 0x04, 0x00, 0x06, 0xCB, 0x01, 0x60])
        self.assertEqual(found, {(s.CODE_BANK, 0x8006): [frozenset({(5, 0x40)})]})

    def test_pre_bits_and_lda_and_tests_count_as_known(self):
        # LDA $6280 · AND #$02 · BEQ 끝 · BRK 07 CB 80 · RTS
        found = self.walk([0xAD, 0x80, 0x62, 0x29, 0x02, 0xF0, 0x04, 0x00, 0x07, 0xCB, 0x80, 0x60], pre=[(1, 0x10)])
        self.assertEqual(found, {(s.CODE_BANK, 0x8007): [frozenset({(1, 0x10), (5, 0x02)})]})

    def test_clearing_forgets_the_bit_and_a_known_bit_skips_the_dead_way(self):
        # BRK 05 DB BF (&= BF 로 40 끄기) · BRK 05 EB 40 · BNE 켜기 · RTS · 켜기: BRK 06 CB 01 · RTS
        found = self.walk([0x00, 0x05, 0xDB, 0xBF, 0x00, 0x05, 0xEB, 0x40, 0xD0, 0x01, 0x60,
                           0x00, 0x06, 0xCB, 0x01, 0x60], pre=[(5, 0x40)])
        self.assertEqual(found, {})

    def test_bank_subroutine_carries_what_is_known(self):
        code = [0x00, 0x05, 0xEB, 0x40, 0xF0, 0x03, 0x20, 0x10, 0x80, 0x60]
        prg = bytearray(PRG_SIZE)
        put(prg, s.CODE_BANK, 0x8000, code)
        put(prg, s.CODE_BANK, 0x8010, [0x00, 0x06, 0xCB, 0x01, 0x60])
        found = {}
        s.guard_walk(prg, s.CODE_BANK, 0x8000, (), found, {})
        self.assertEqual(found, {(s.CODE_BANK, 0x8010): [frozenset({(5, 0x40)})]})

    def test_runaway_raises(self):
        prg = bytearray(PRG_SIZE)
        put(prg, s.CODE_BANK, 0x8000, [0xE8, 0x4C, 0x00, 0x80])
        with self.assertRaisesRegex(RuntimeError, '길이 너무 많음'):
            s.guard_walk(prg, s.CODE_BANK, 0x8000, (), {}, {}, limit=1)


class MinimizeTests(unittest.TestCase):
    def test_primes_cover_merges_neighbours(self):
        self.assertEqual(s.primes_cover(2, {0b01, 0b11}, set()), [(0b01, 0b10)])
        self.assertEqual(s.primes_cover(2, {0b00}, {0b01}), [(0b00, 0b01)])
        self.assertEqual(sorted(s.primes_cover(2, {0b00, 0b11}, set())), [(0b00, 0), (0b11, 0)])

    def test_consistent_needs_one_value_for_each_number(self):
        eq = ('num', '장', '=', 1)
        ge = ('num', '장', '≥', 2)
        self.assertTrue(s.consistent([eq, ge], [False, True]))
        self.assertFalse(s.consistent([eq, ge], [True, True]))

    def test_minimize_drops_atoms_that_do_not_matter(self):
        night = (('시간', '≥', dq4map.NIGHT),)
        day = (('시간', '<', dq4map.NIGHT),)
        flag_night = night + ((FLAG5, '≠', 0),)
        flag_off_night = night + ((FLAG5, '=', 0),)
        paths = [(day, ()), (flag_night, (('hide', 3),)), (flag_off_night, (('hide', 3),))]
        terms = s.minimize(paths, s.hide_keys)
        self.assertEqual(terms, {(3, '숨김'): [[(('num', '시간', '≥', dq4map.NIGHT), True)]]})
        self.assertEqual(s.terms_text(terms[(3, '숨김')]), '[밤]')
        self.assertEqual(s.terms_text([[]]), '늘')
        self.assertEqual(s.atom_text(('bit', '$6280', 0x40), False), '$6280&40 꺼짐')

    def test_chapter_rules_limit_the_chapters(self):
        old = s.RULES, s.ORDER
        self.addCleanup(lambda: (setattr(s, 'RULES', old[0]), setattr(s, 'ORDER', old[1])))
        s.RULES = {('$6290', 0x01): (2, True)}
        s.ORDER = {('$6291', 0x01): {('$6292', 0x02)}}
        ch = ('num', '장', '=', 1)
        bit = ('bit', '$6290', 0x01)
        self.assertFalse(s.consistent([ch, bit], [True, True]))
        self.assertTrue(s.consistent([('num', '장', '=', 2), bit], [True, True]))
        self.assertFalse(s.chapters_ok([('bit', '$6282', 0x40), ch], [True, True]))
        self.assertFalse(s.consistent([('bit', '$6291', 0x01), ('bit', '$6292', 0x02)], [True, False]))

    def test_hide_keys_reads_effects(self):
        eff = (('hide', 1), ('pos', 2, 'X', 0x80), ('pos', 2, 'Y', 0x80), ('pos', 4, 'X', 5), ('pos', 4, 'Y', '$45'),
               ('pos', 4, 'X2', 9), ('flag', 0x6281, '|=', 1), ('write', 0x300, '+1'), ('call', 'JSR $C000'))
        self.assertEqual(s.hide_keys(eff), {(1, '숨김'), (2, '숨김'), (4, 'X=05 Y=$45'), (None, '$6281 |= 01'),
                                            (None, '$0300 = +1'), (None, 'JSR $C000')})


if __name__ == '__main__':
    unittest.main()
