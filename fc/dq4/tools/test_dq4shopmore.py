"""가게 목록·인물 출력, 숨김 조건 표시와 덤프 대조, 진행·순서 관계 추출을 합성 롬과 합성 덤프로 검사한다."""
import json
import os
import tempfile
import unittest

import dq4data as d
import dq4map
import dq4shop as s
import dq4talk
from test_dq4datamore import run_cli_code
from test_dq4eventmore import event_world
from test_dq4npcblock import put, word

TIME = 0x62ED


def jsr(a):
    return [0x20] + word(a)


def end_scripts(prg):
    """대화 스크립트 7~160 가운데 event_prg 가 정한 011 말고는 바로 끝나는 스크립트를 가리키게 한다(0 번지 쓰레기를 풀지 않도록)."""
    put(prg, dq4talk.BANK, 0x9F00, [0x3F])
    for tid in range(dq4talk.SCRIPT_FIRST, dq4talk.YESNO_FIRST):
        if tid != 0x011:
            put(prg, dq4talk.BANK, dq4talk.SCRIPTS + 2 * (tid - dq4talk.SCRIPT_FIRST), word(0x9F00))


def shop_world():
    """맵 02/00(가게 인물 넷, 낮에 첫 인물을 숨기고 둘째를 옮김)과 가게 표. 맵 00/00 의 첫 인물은 2장이 아닐 때 숨는다."""
    prg = event_world()
    end_scripts(prg)
    put(prg, s.TABLE_BANK, s.LIST_PTRS, word(0xA000) + word(0xA100) + word(0xA007))
    put(prg, s.TABLE_BANK, 0xA000, [0x02, 0x00, 0x00, 0x81, 0x03, 0x01, 0x81])
    put(prg, s.TABLE_BANK, 0xA007, [0x04, 0x00, 0x00, 0x81, 0xFF, 0x81])
    put(prg, s.TABLE_BANK, 0xA100, [0x05, 0x00, 0x80, 0xFF, 0x81])
    put(prg, s.TABLE_BANK, s.INN_TABLE, [0x02, 0x00, 6, 0x03, 0x01, 12, 0xFF])
    put(prg, s.CODE_BANK, s.EXTRA_16, [0x00, 0x01, 0x00])
    put(prg, d.ITEM_BANK, d.ITEM_PRICE, [5, 12])
    put(prg, *dq4map.GROUPS, word(0xA000) + word(0xA003) + word(0xA004) + [0xFF, 0xFF])
    put(prg, 0x17, 0xA004, [0x10, 0x00, 0x90, 0xFF])
    put(prg, dq4map.NPC_BANK, 0x8004, word(0x9100))
    npc = lambda tid, x, y: [0x10, 0, 0, 0, tid, x, y, 1, 0x2A]
    put(prg, dq4map.NPC_BANK, 0x9100, npc(0x13, 5, 6) + npc(6, 8, 9) + npc(5, 10, 11) + npc(0x14, 12, 13) + [0])
    put(prg, dq4talk.BANK, 0x9300, [0x12, 0x01, 0x3F])
    put(prg, dq4talk.BANK, 0x9310, [0x00, 0xB7, 0xAD, 0x3F])
    put(prg, dq4talk.BANK, dq4talk.SCRIPTS + 2 * (0x13 - dq4talk.SCRIPT_FIRST), word(0x9300))
    put(prg, dq4talk.BANK, dq4talk.SCRIPTS + 2 * (0x14 - dq4talk.SCRIPT_FIRST), word(0x9310))
    put(prg, s.HIDE_BANK, s.HIDE_PLACES, [0x02, 0x00, 0x80])
    put(prg, s.HIDE_BANK, s.HIDE_PTRS, word(0x8000))
    put(prg, s.HIDE_BANK, 0x8000, jsr(s.IS_NIGHT) + [0xB0, 0x0E, 0xA2, 0x00] + jsr(s.HIDE_SLOT)
        + [0xA9, 0x10, 0xA0, 0x20, 0xA2, 0x01] + jsr(s.PLACE_SLOT) + [0x60])
    put(prg, s.HIDE_BANK, s.CHAPTER_HIDE, [0x00, 0x00, 0x01, 0x00, 0x80])
    return prg


def mem_file(tmp, patch):
    mem = bytearray(0x8000)
    for a, v in patch.items():
        mem[a] = v
    path = os.path.join(tmp, 'mem.bin')
    with open(path, 'wb') as f:
        f.write(mem)
    return path


class ShopGlobalsTestCase(unittest.TestCase):
    """hidden() 이 바꾸는 모듈 전역(RULES·ORDER)을 시험이 끝나면 되돌린다."""

    def setUp(self):
        self.addCleanup(setattr, s, 'RULES', s.RULES)
        self.addCleanup(setattr, s, 'ORDER', s.ORDER)


class PrintTests(ShopGlobalsTestCase):
    def setUp(self):
        super().setUp()
        self.prg = shop_world()

    def test_show_all_lists_every_kind_extras_and_inns(self):
        out, _ = run_cli_code(s.main, self.prg)
        self.assertEqual(out, [
            '# 무기 (18:$A000)', '02/00  00 ア 5G, 01 イ 12G', '03/01  01 イ 12G',
            '# 도구 (18:$A100)', '05/00  00 ア 5G', 'FF(기본)  01 イ 12G',
            '# 방어구 (18:$A007)', '04/00  00 ア 5G, 01 イ 12G', 'FF(기본)  01 イ 12G',
            '# 덧붙임(15:$B26B)',
            '16/00 무기  $62E7~$62E9 가 0 이 아니면 차례로 00 ア 5G, 01 イ 12G, 00 ア 5G',
            '09/00 무기  $62ED < $78(낮) 이면 목록 대신 06 ? 0G, 23 ? 0G, 07 ? 0G, 10 ? 0G',
            '# 여관 (18:$B5CD, 1인 값)', '02/00=6 03/01=12', '그룹 10 에서 $45 < $14 이면 10'])

    def test_fmt_items_uses_special_prices_and_units(self):
        self.assertEqual(s.fmt_items(self.prg, [0, 1]), '00 ア 5G, 01 イ 12G')
        self.assertEqual(s.fmt_items(self.prg, [0x4E, 0x50], 0x22, 0), '4E ? 4메달, 50 ? 20메달')
        rows = [(0x00, 100)] + [(0xFE, 0)] * 5 + [(0, 777)]
        put(self.prg, s.CODE_BANK, s.CASINO_TABLE, [v for it, p in rows for v in [it] + word(p)])
        self.assertEqual(s.fmt_items(self.prg, [0, 1], 0x04, 1), '00 ア 100코인, 01 イ 777코인')

    def test_offer_for_every_kind(self):
        self.assertEqual(s.offer(self.prg, 2, 0, 1), 'ア イ')
        self.assertEqual(s.offer(self.prg, 0x09, 0, 3), 'イ')
        self.assertEqual(s.offer(self.prg, 2, 0, 4), '골드 1000G 단위·물건 맡기기')
        self.assertEqual(s.offer(self.prg, 0x03, 0x01, 5), '저장·おつげ·되살리기·해독·저주')
        self.assertEqual(s.offer(self.prg, 0x07, 0, 6), '표에 없음')
        put(self.prg, s.TABLE_BANK, s.INN_TABLE, [s.INN_10_GROUP, 0x00, 30, 0xFF])
        self.assertEqual(s.offer(self.prg, s.INN_10_GROUP, 0, 6, y=0x05), '1인 10G(주인공 Y < 14, 표 값 30G)')
        self.assertEqual(s.offer(self.prg, s.INN_10_GROUP, 0, 6, y=0x30), '1인 30G')

    def test_show_map_lists_shops_inn_and_people(self):
        out, _ = run_cli_code(s.main, self.prg, '2', '0')
        self.assertEqual(out, [
            '무기  00 ア 5G, 01 イ 12G', '여관  1인 6G',
            '인물 (05,06) 대화 번호 013 스크립트 [낮] → 무기',
            '인물 (08,09) 대화 번호 006 직접 [낮] → 여관',
            '인물 (0A,0B) 대화 번호 005 직접 [낮] → 교회',
            '인물 (0C,0D) 대화 번호 014 호출 15:ADB7 [인물 자리 (0C,0D) & 낮] → 무기'])

    def test_show_compares_shop_window_ram(self):
        ram = bytearray(0x800)
        ram[s.KIND_RAM], ram[s.COUNT_RAM] = 1, 2
        ram[s.SHOP_RAM:s.SHOP_RAM + 2] = bytes([0, 1])
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'end.ram')
            with open(path, 'wb') as f:
                f.write(bytes(ram))
            same, _ = run_cli_code(s.main, self.prg, '2', '0', '--compare', path)
            ram[s.SHOP_RAM + 1] = 2
            with open(path, 'wb') as f:
                f.write(bytes(ram))
            other, _ = run_cli_code(s.main, self.prg, '2', '0', '--compare', path)
        self.assertEqual(same[-1], 'RAM $07C5=01 $07C4=2 $07BD=00 01 — 표 같음')
        self.assertEqual(other[-1], 'RAM $07C5=01 $07C4=2 $07BD=00 02 — 표 다름: [0, 1]')

    def test_show_compare_with_sram_applies_extras(self):
        prg = self.prg
        ram = bytearray(0x800)
        ram[s.KIND_RAM], ram[s.COUNT_RAM] = 1, 2
        ram[s.SHOP_RAM:s.SHOP_RAM + 2] = bytes([0, 1])
        sram = bytearray(0x2000)
        with tempfile.TemporaryDirectory() as tmp:
            rpath, spath = os.path.join(tmp, 'end.ram'), os.path.join(tmp, 'end.sram')
            with open(rpath, 'wb') as f:
                f.write(bytes(ram))
            with open(spath, 'wb') as f:
                f.write(bytes(sram))
            out, _ = run_cli_code(s.main, prg, '2', '0', '--compare', rpath, spath)
        self.assertTrue(out[-1].endswith('— 표 같음'))

    def test_people_lines_with_hide_notes(self):
        out, _ = run_cli_code(s.main, self.prg, 'people')
        self.assertEqual(out, [
            '00/00 (01,01) 대화 013 스크립트 [목록 플래그 05&01 & 낮] → 무기: イ / 들어갈 때 숨김 [2장 아님]',
            '02/00 (05,06) 대화 013 스크립트 [낮] → 무기: ア イ / 들어갈 때 숨김 [낮]',
            '02/00 (08,09) 대화 006 직접 [낮] → 여관: 1인 6G / 들어갈 때 X=10 Y=20 [낮]',
            '02/00 (0A,0B) 대화 005 직접 [낮] → 교회: 저장·おつげ·되살리기·해독·저주',
            '02/00 (0C,0D) 대화 014 호출 15:ADB7 [인물 자리 (0C,0D) & 낮] → 무기: ア イ',
            '가게 인물 5곳'])


class HiddenTests(ShopGlobalsTestCase):
    def setUp(self):
        super().setUp()
        self.prg = shop_world()

    def test_hidden_rows_for_routine_and_chapter_lines(self):
        night = ('num', '시간', '≥', dq4map.NIGHT)
        got = s.hidden(self.prg)
        self.assertEqual(got, [
            (2, 0, 0x8000, [(0, '숨김', [[(night, False)]]), (1, 'X=10 Y=20', [[(night, False)]])]),
            (0, 0, s.CHAPTER_HIDE, [(0, '숨김', [[(('num', '장', '=', 1), False)]])])])
        self.assertEqual(s.hidden(self.prg, story=False), got)

    def test_show_hidden_text(self):
        out, _ = run_cli_code(s.main, self.prg, 'hidden')
        self.assertEqual(out, [
            '02/00 1C:8000',
            '  인물 0(낮 (05,06) 대화 013) 숨김: [낮]',
            '  인물 1(낮 (08,09) 대화 006) X=10 Y=20: [낮]',
            '00/00 1C:AD5A',
            '  인물 0(낮 (05,06) 대화 011, 밤 (07,08) 대화 012) 숨김: [2장 아님]',
            '장소 2곳'])
        raw, _ = run_cli_code(s.main, self.prg, 'hidden', '--raw')
        self.assertEqual(raw, out)

    def test_show_hidden_json(self):
        out, _ = run_cli_code(s.main, self.prg, 'hidden', '--json')
        data = json.loads('\n'.join(out))
        self.assertEqual(data[0], {'group': 2, 'index': 0, 'routine': '1C:8000', 'acts': [
            {'person': 0, 'act': '숨김', 'when': [['낮']]}, {'person': 1, 'act': 'X=10 Y=20', 'when': [['낮']]}]})
        self.assertEqual(data[1]['acts'], [{'person': 0, 'act': '숨김', 'when': [['2장 아님']]}])

    def test_person_text(self):
        night = ('num', '시간', '≥', dq4map.NIGHT)
        self.assertEqual(s.person_text(self.prg, 2, 0, 'x', []), '인물 x')
        self.assertEqual(s.person_text(self.prg, 2, 0, 0, [[(night, False)]]), '인물 0(낮 (05,06) 대화 013)')
        self.assertEqual(s.person_text(self.prg, 0, 0, 0, [[]]), '인물 0(낮 (05,06) 대화 011, 밤 (07,08) 대화 012)')
        self.assertEqual(s.person_text(self.prg, 2, 0, 7, [[(night, False)]]), '인물 7(보통 목록에 없음)')

    def test_compare_hidden_day_with_moves(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = mem_file(tmp, {TIME: 0x10, 0x6F66: 0x80, 0x6F86: 0x80, 0x6F67: 0x10, 0x6F87: 0x20})
            out, _ = run_cli_code(s.main, self.prg, 'hidden', '2', '0', '--compare', path)
            self.assertEqual(out, ['02/00 낮 인물 4명, 맞는 길 1개', '덤프 (80,80): [0]  예측 숨김: [0] — 같음',
                                   '  인물 1 X $6F67 = 10  예측 10 — 같음', '  인물 1 Y $6F87 = 20  예측 20 — 같음',
                                   '옮김 열 2개 중 다름 0'])
            path = mem_file(tmp, {TIME: 0x10, 0x6F66: 0x80, 0x6F86: 0x80, 0x6F67: 0x10, 0x6F87: 0x21})
            out, _ = run_cli_code(s.main, self.prg, 'hidden', '2', '0', '--compare', path)
        self.assertIn('  인물 1 Y $6F87 = 21  예측 20 — 다름', out)
        self.assertEqual(out[-1], '옮김 열 2개 중 다름 1')

    def test_compare_hidden_night_has_nothing_to_move(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, _ = run_cli_code(s.main, self.prg, 'hidden', '2', '0', '--compare', mem_file(tmp, {TIME: 0x80}))
        self.assertEqual(out, ['02/00 밤 인물 0명, 맞는 길 1개', '덤프 (80,80): []  예측 숨김: [] — 같음'])

    def test_compare_hidden_chapter_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            hidden = {TIME: 0x10, 0x6F66: 0x80, 0x6F86: 0x80}
            out, _ = run_cli_code(s.main, self.prg, 'hidden', '0', '0', '--compare',
                                  mem_file(tmp, {**hidden, 0x615A: 2}))
            self.assertEqual(out, ['00/00 낮 인물 2명, 맞는 길 0개', '덤프 (80,80): [0]  예측 숨김: [0] — 같음'])
            out, _ = run_cli_code(s.main, self.prg, 'hidden', '0', '0', '--compare',
                                  mem_file(tmp, {**hidden, 0x615A: 1}))
        self.assertEqual(out[1], '덤프 (80,80): [0]  예측 숨김: [] — 다름')

    def test_sym_value_reads_names_addresses_and_masks(self):
        mem = bytearray(0x8000)
        mem[TIME], mem[0x615A], mem[0x6280], mem[0x44] = 0x90, 0x03, 0xF5, 7
        self.assertEqual([s.sym_value(x, mem) for x in ('시간', '장&01', '$6280', '$6280&41', '주인공 X')],
                         [0x90, 1, 0xF5, 0x41, 7])
        self.assertIsNone(s.sym_value('아이템 2C', mem))
        self.assertIsNone(s.sym_value('$ZZ', mem))

    def test_expect_value_known_bits(self):
        mem = bytearray(0x8000)
        mem[0x44], mem[0x7006] = 9, 0xAB
        self.assertEqual(s.expect_value(5, mem), (0xFF, 5))
        self.assertEqual(s.expect_value('주인공 X', mem), (0xFF, 9))
        self.assertEqual(s.expect_value('$7006', mem), (0xFF, 0xAB))
        self.assertEqual(s.expect_value('$7006&FC|02', mem), (0x03, 0x02))
        self.assertEqual(s.expect_value('$7006|80', mem), (0x80, 0x80))
        self.assertIsNone(s.expect_value('아무 값', mem))

    def test_predict_hidden_and_moves(self):
        mem = bytearray(0x8000)
        mem[TIME] = 0x10
        self.assertEqual(s.predict_hidden(self.prg, 0x8000, mem), ({0}, 1))
        self.assertEqual(s.predict_moves(self.prg, 0x8000, mem), {(1, 'X'): (0xFF, 0x10), (1, 'Y'): (0xFF, 0x20)})
        mem[TIME] = 0x80
        self.assertEqual(s.predict_hidden(self.prg, 0x8000, mem), (set(), 1))
        self.assertEqual(s.predict_moves(self.prg, 0x8000, mem), {})


class TextTests(unittest.TestCase):
    def test_atom_text_and_terms_text(self):
        self.assertEqual(s.atom_text(('bit', '$6280', 0x40), True), '$6280&40 켜짐')
        self.assertEqual(s.atom_text(('bit', '$6280', 0x40), False), '$6280&40 꺼짐')
        self.assertEqual(s.atom_text(('num', '장', '=', 1), True), '2장')
        self.assertEqual(s.atom_text(('num', '장', '=', 1), False), '2장 아님')
        self.assertEqual(s.terms_text([[]]), '늘')
        self.assertEqual(s.terms_text([[(('bit', '$6280', 1), True), (('num', '장', '=', 0), True)],
                                       [(('bit', '$6280', 2), False)]]),
                         '[$6280&01 켜짐 & 1장] 또는 [$6280&02 꺼짐]')

    def test_value_text(self):
        self.assertEqual((s.value_text(5), s.value_text('$7006&FC')), ('05', '$7006&FC'))


def rules_world():
    """플래그 5 비트 01 은 비트 02 가 켜졌을 때만 대화로 켜지고, 플래그 71 비트 01 은 이벤트 02 안에서 비트 02 검사 뒤에 켜진다."""
    prg = event_world()
    end_scripts(prg)
    put(prg, dq4talk.BANK, 0x9000, [0x07, 0x1B, 0x05, 0x02, 0x18, 0x05, 0x01, 0x3F])
    put(prg, 0x1D, 0xB123, [0x00, 0x05, 0xEB, 0x02, 0xF0, 0x04, 0x00, 0x71, 0xCB, 0x01, 0x60])
    return prg


class RuleTests(ShopGlobalsTestCase):
    def setUp(self):
        super().setUp()
        self.prg = rules_world()

    def test_one_bit_needs_exactly_one_bit(self):
        self.assertEqual(s.one_bit([5, 0x40]), frozenset({(5, 0x40)}))
        self.assertEqual(s.one_bit([5, 0x41]), frozenset())
        self.assertEqual(s.one_bit([5, 0x00]), frozenset())

    def test_script_needs_collects_bits_of_each_branch(self):
        pick = lambda st: [st[1][0]] if st[0] == 'flag|=' else ()
        tree = [('if', False, 0x1B, [5, 0x40], [('flag|=', [1, 1])], [('flag|=', [2, 1])]),
                ('if', True, 0x1B, [6, 0x08], [('flag|=', [3, 1])], [('flag|=', [4, 1])]),
                ('if', False, 0x14, [], [('flag|=', [1, 1])], None)]
        out = {}
        s.script_needs(tree, pick, out)
        # 키 1 은 두 곳에서 나오므로 공통 조건만 남는다
        self.assertEqual(out, {1: frozenset(), 2: frozenset(), 3: frozenset(), 4: frozenset({(6, 0x08)})})
        out = {}
        s.script_needs(tree[:2], pick, out)
        self.assertEqual(out, {1: frozenset({(5, 0x40)}), 2: frozenset(), 3: frozenset(), 4: frozenset({(6, 0x08)})})

    def test_flag_writers_count_setters_and_collect_clears(self):
        sets, clears = s.flag_writers(self.prg)
        self.assertEqual(sets, {(5, 1): 1, (5, 0x40): 1, (0x70, 0x20): 1, (0x71, 1): 1})
        self.assertEqual(clears, {(5, 0x40)})

    def test_talk_rules_follow_the_guarding_condition(self):
        sets, _ = s.flag_writers(self.prg)
        self.assertEqual(s.talk_rules(self.prg, sets), {(5, 1): frozenset({(5, 2)})})

    def test_progress_rules_only_for_bits_written_once(self):
        self.assertEqual(s.progress_rules(self.prg), {('$6280', 0x40): (1, False), ('$6280', 0x01): (2, False)})

    def test_code_entries_and_guards(self):
        self.assertEqual(s.code_entries(self.prg), [(0x1C, 0, frozenset()), (0x1D, 0, frozenset()),
                                                    (0x1D, 0xB123, frozenset())])
        self.assertEqual(s.code_guards(self.prg), {(0x1D, 0xB129): frozenset({(5, 2)})})

    def test_order_rules_and_command(self):
        self.assertEqual(s.order_rules(self.prg), {('$6280', 1): {('$6280', 2)}, ('$62EC', 1): {('$6280', 2)}})
        out, _ = run_cli_code(s.main, self.prg, 'order')
        self.assertEqual(out, ['$6280&01 ← $6280&02', '$62EC&01 ← $6280&02'])

    def test_order_rules_close_over_chains(self):
        put(self.prg, 0x1D, 0xB123, [0x00, 0x05, 0xEB, 0x02, 0xF0, 0x04, 0x00, 0x71, 0xCB, 0x01, 0x60])
        put(self.prg, dq4talk.BANK, 0x9000, [0x07, 0x1B, 0x71, 0x01, 0x18, 0x05, 0x01, 0x3F])
        rules = s.order_rules(self.prg)
        self.assertEqual(rules[('$6280', 1)], {('$62EC', 1), ('$6280', 2)})


class BrkSizeTests(unittest.TestCase):
    def setUp(self):
        self.prg = bytearray(32 * 0x4000)
        put(self.prg, 0x16, 0x8006, word(0x9000))
        put(self.prg, 0x16, 0x9000, [0xFE, 0x00, 0x01, 0xD0, 0xEA, 0xFE, 0x01, 0x01, 0xD0, 0xEA])

    def test_inline_bytes_counts_return_address_bumps(self):
        self.assertEqual(s.inline_bytes(self.prg, 0x16, 3), 2)
        self.assertEqual(s.inline_bytes(self.prg, 0x16, 0), 0)        # 포인터 0 은 뱅크 밖이라 0
        put(self.prg, 0x16, 0x8002, word(0x9100))
        self.assertEqual(s.inline_bytes(self.prg, 0x16, 1), 0)

    def test_brk_size_adds_inline_bytes_only_for_plain_calls(self):
        cache = {}
        self.assertEqual(s.brk_size(self.prg, 3, 0x68, cache), 5)
        self.assertEqual(cache, {(0x16, 3): 2})
        self.assertEqual(s.brk_size(self.prg, 0x10, 0xCB, cache), 4)
        self.assertEqual(s.brk_size(self.prg, 5, 0x33, cache), 3)
        self.assertEqual(s.brk_size(self.prg, 0x83, 0x68, cache), 3)
        self.assertEqual(len(cache), 1)


if __name__ == '__main__':
    unittest.main()
