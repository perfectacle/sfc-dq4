"""레이크나바 사건(dq4ch3lakanaba): FC 값 표, flag 자리, 대화·인물 스크립트 크기, 네이티브 자리, 메시지 줄 너비, 검사 사본."""

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4ch3event as ev  # noqa: E402
import dq4ch3lakanaba as L  # noqa: E402
import dq4chapter1 as ch1  # noqa: E402

ROOT = HERE.parents[2]
DQ5 = ROOT / 'rom' / 'dq5.sfc'
FIRST = 0x1100


def ctx():
    return next(c for c in ev.contexts(FIRST) if c.module is L)


class TableTest(unittest.TestCase):
    def test_prices_are_fc_shop_and_seller_formulas(self):
        p = L.prices()
        self.assertEqual(p[0], [30, 100, 200, 350, 550, 3500])
        self.assertEqual(p[1], [27, 90, 180, 315, 495, 3150])        # − 값/10
        self.assertEqual(p[2], [33, 110, 220, 385, 605, 3850])       # + 값/10
        self.assertEqual(p[3], [22, 75, 150, 262, 412, 2625])        # p − ⌊(p + 3)/4⌋(FC 실측 2625)

    def test_wages_match_the_fc_table(self):
        # fc/dq4/docs/dq4-chapter3-format.md 「일삯」(그대로 / 웃돈 / 깎음)
        w = L.wages()
        self.assertEqual(w[0], [1, 6, 12, 21, 34, 218])
        self.assertEqual(w[2], [4, 13, 27, 48, 75, 481])
        self.assertEqual(w[1], [1, 5, 11, 19, 30, 196])
        self.assertEqual(w[3], [0] * 6)

    def test_goods_are_dq5_items_with_fc_prices(self):
        self.assertEqual([i for i, _ in L.GOODS], [0x02, 0x06, 0x1C, 0x21, 0x07, 0x0D])
        self.assertEqual(L.STOCKED + 3, len(L.GOODS))
        self.assertEqual(L.HAJA, len(L.GOODS) - 1)


class FlagTest(unittest.TestCase):
    def test_flags_stay_in_the_l_bytes_and_do_not_overlap(self):
        self.assertTrue(all(f[0] in ev.SLOTS['L'].flags for f in L.FLAGS))
        seen = {}
        for idx, mask in L.FLAGS:
            self.assertFalse(seen.get(idx, 0) & mask, (idx, mask))
            seen[idx] = seen.get(idx, 0) | mask
        self.assertEqual(seen, {0x70: 0xFF, 0x71: 0xFF})

    def test_temporary_bits_live_in_bytes_the_map_load_clears(self):
        # 7E:21A2~21A4 는 맵을 옮기면 지워진다(dq5flags). ANSWERED 는 2장과 같은 칸
        for f in (L.ACROSS, L.START, L.AGAIN, L.SLEPT, L.HERE_, L.SERVED, L.DISCOUNT, L.RAISE, L.LUCK40, L.JOKE):
            self.assertIn(f[0], (0x13, 0x14), f)
        self.assertEqual(L.PACE, 0x7E21A2)
        self.assertEqual(L.TEMP, 0x7E2190 + 0x14)

    def test_joke_bit_is_free_in_21a3(self):
        # 21A3 의 다른 3장 비트: ANSWERED(bit0)·FRESH(bit5)·LUCK40(bit6)
        others = L.ANSWERED[1] | ev.FRESH[1] | L.LUCK40[1]
        self.assertEqual(L.JOKE[0], 0x13)
        self.assertFalse(L.JOKE[1] & others)

    def test_shop_key_byte_is_the_l_share_of_the_second_vars(self):
        import dq4ch3slots
        import dq4shopport
        lo, hi = dq4ch3slots.SLOTS['L'].vars2
        self.assertEqual((L.SHOP_KEY_AT, hi - lo), (dq4ch3slots.VARS2_AT + lo, 1))
        self.assertEqual(dq4shopport.ONE_SHOT_AT, L.SHOP_KEY_AT)
        # 재고 칸 차례가 가게 목록의 덧붙임 차례와 같다(ブーメラン·くさりがま·はじゃのつるぎ)
        self.assertEqual(len(dq4shopport.LAKANABA_STOCK), len(L.GOODS) - L.STOCKED)

    @unittest.skipUnless(DQ5.is_file() and (ROOT / 'rom' / 'dq4.nes').is_file(), 'local source ROMs not present')
    def test_looks_are_pictures_of_the_day_town(self):
        import dq4npcport
        lists, _, _ = dq4npcport.port(DQ5, ROOT / 'rom' / 'dq4.nes')
        town = next(lst for lst in lists if lst.get('map') == L.TOWN)['entries']
        day = {e['fields']['gfx'] for e in town if e['time'] == 'day'}
        self.assertEqual(len(L.LOOKS), 8)
        self.assertLessEqual(set(L.LOOKS), day)

    def test_vars_stay_in_the_l_var_slot(self):
        lo, hi = ev.SLOTS['L'].vars
        for a in (L.STOCK_AT, L.STOCK_AT + 2, L.WAGE_AT, L.WAGE_AT + 1, L.ITEM_AT):
            self.assertTrue(ev.VARS_AT + lo <= a < ev.VARS_AT + hi, hex(a))


class ScriptTest(unittest.TestCase):
    def test_talks_encode_under_256_bytes(self):
        import dq5talkwrite
        for name, body in zip(L.TALKS, L.talk_scripts(ctx())):
            self.assertLessEqual(len(dq5talkwrite.encode_script(body, name)), 256, name)

    def test_buy_flip_changes_one_condition_byte(self):
        import dq5talkwrite
        k = L.TALKS.index('buyer')
        a = dq5talkwrite.encode_script(L.talk_scripts(ctx())[k], 'buyer')
        b = dq5talkwrite.encode_script(L.talk_scripts(ctx(), flip_buy=True)[k], 'buyer')
        self.assertEqual(len(a), len(b))
        self.assertEqual(sum(x != y for x, y in zip(a, b)), 1)

    def test_sleep_is_call_table_slot_zero(self):
        # dq4ch3opencheck 의 공용 장치 시험이 표 칸 0 을 바꿔 네네 대화로 부른다
        self.assertEqual(next(iter(L.CALLS)), 'sleep')
        self.assertEqual(ctx().calls['sleep'], 0)

    def test_person_scripts_encode_and_borrow_reserved_slots(self):
        import dq5npcwrite
        mine = {(lst, i) for lst, idx in ev.SLOTS['L'].scripts for i in idx}
        for name, (lst, i, _) in L.SCRIPTS.items():
            self.assertIn((lst, i), mine, name)
        for s in L.scripts(ctx()):
            code = dq5npcwrite.encode({'format': dq5npcwrite.FORMAT, 'commands': s['commands']})
            self.assertLessEqual(len(code), 255, s['address'])

    def test_scripted_people_get_a_turn(self):
        # 이동 간격 0 이면 인물 스크립트가 돌지 않는다(실측)
        p = L._person('customer', 'day', (1, 1), 'left', 1, 1)
        self.assertEqual(p['fields']['interval'], 1)


class NativeTest(unittest.TestCase):
    def test_native_fits_the_slot_and_addresses_do_not_depend_on_messages(self):
        c = ctx()
        code, at = L.native(c)
        self.assertLessEqual(c.code_at + len(code), ev.SLOTS['L'].code[1])
        self.assertEqual(at, c.at)
        for name in ('where', 'prep', 'result', 'haggle', 'sell', 'buy_in', 'pay_wage', 'arrive', 'set_talk',
                     'rest', 'wake', 'tom_pay', 'night'):
            self.assertEqual(code[at[name] - c.code_at], 0x08, name)     # PHP(ENTER)

    def test_tables_index_by_mode_times_sixteen(self):
        c = ctx()
        code, at = L.native(c)
        for mode, row in enumerate(L.prices()):
            for k, p in enumerate(row):
                o = at['prices'] - c.code_at + 2 * (mode * L.ROW + k)
                self.assertEqual(int.from_bytes(code[o:o + 2], 'little'), p, (mode, k))

    def test_thresholds_change_only_immediate_bytes(self):
        c = ctx()
        code, _ = L.native(c)
        keep = L.SELLER_BELOW, L.BUYER_PICK
        try:
            L.SELLER_BELOW, L.BUYER_PICK = 0xFF, 1
            more, _ = L.native(c)
        finally:
            L.SELLER_BELOW, L.BUYER_PICK = keep
        self.assertEqual(len(code), len(more))
        self.assertLessEqual(sum(a != b for a, b in zip(code, more)), 6)

    def test_next_day_is_a_common_routine(self):
        blob, at = ev.native()
        self.assertIn('next_day', ev.COMMON_ROUTINES)
        self.assertEqual(blob[at['next_day'] - ev.CODE_AT], 0x08)


class MessageTest(unittest.TestCase):
    MARK_COLS = {0x1004: 5, 0x100A: 9, 0x101D: 0}

    def test_lines_fit_counting_number_and_item_width(self):
        josa = {code for code, _ in ch1._josa().values()}
        for name, codes in L.MESSAGES.items():
            narr = False
            line = 0
            for c in codes:
                if c == ch1.NARR:
                    narr = True
                elif c in (ch1.LINE, ch1.PAGE, ch1.END):
                    self.assertLessEqual(line, ch1.NARR_COLS if narr else ch1.LINE_COLS, name)
                    line = 0
                    if c == ch1.PAGE:
                        narr = False
                elif c in self.MARK_COLS:
                    line += self.MARK_COLS[c]
                elif c in josa:
                    line += 1
                elif isinstance(c, str):
                    line += len(c)
                elif c == ch1.HERO:
                    line += ch1.NAME_COLS

    def test_number_messages_call_the_price_routine_before_the_number(self):
        for name in ('buy', 'discount', 'raise', 'offer'):
            codes = L.MESSAGES[name]
            self.assertLess(codes.index(0x100A), codes.index(0x101D), name)
            self.assertEqual(codes.index(0x101D) + 1, codes.index(0x1004), name)

    def test_message_count_fits_the_estimate(self):
        self.assertLessEqual(len(L.MESSAGES), 60)


class ListTest(unittest.TestCase):
    def test_start_table_and_absent(self):
        c = ctx()
        table = L.start_messages(c)
        self.assertEqual(table[(L.HOUSE, L.FC_NENE, False)], c.msg['home'])
        gone = L.absent(c)
        self.assertIn((L.TOWN, *L.COUNTER_IN, False), gone)
        self.assertEqual(len(gone), 7 + len(L.STRAYS))
        self.assertIn((L.HOUSE, *L.NENE_WALKER[2], False), gone)
        # 아래층 주인은 출근 전, 톰 아들은 감옥에서 풀려나기 전(낮·밤)에 숨는다
        self.assertIn((L.CELLAR, *L.QUIT_MASTER[2], False), gone)
        self.assertIn((L.TOWN, *L.SON, False), gone)
        self.assertIn((L.TOWN, *L.SON, True), gone)
        # 공용 표는 모든 모듈의 것을 모은다: 이 모듈 몫이 다 들어 있으면 된다
        self.assertLessEqual(gone, ev.absent())


@unittest.skipUnless(DQ5.is_file(), 'local source ROM not present')
class PortedListTest(unittest.TestCase):
    def test_lists_take_the_people_and_add_scripted_ones(self):
        import dq4npcport
        lists, _, _ = dq4npcport.port(DQ5, ROOT / 'rom' / 'dq4.nes')
        by = {lst['map']: lst for lst in lists if 'map' in lst}
        c = ctx()
        L.npc_lists(by, c)
        town = by[L.TOWN]['entries']
        froms = [e.get('from') for e in town]
        for name in ('customer', 'first_master', 'master', 'tom', 'helper', 'dog', 'helper_night', 'dog_night', 'son',
                     'son_night', 'dog_home', 'dog_home_night'):
            self.assertIn(L._src(name), froms, name)
        self.assertFalse([e for e in town if (e['time'], (e['fields']['x'], e['fields']['y'])) in
                          {(t, c_) for _, t, c_ in L.STRAYS}])
        house = by[L.HOUSE]['entries']
        nenes = [e for e in house if e['time'] == 'day' and e['fields']['talk'] == c.talk['nene']]
        self.assertEqual([(e['fields']['x'], e['fields']['y']) for e in nenes], [L.NENE['day']])
        # 낮 네네는 돌아다니는 틀(FC 슬롯 07 의 걸음 간격)
        self.assertEqual((nenes[0]['from'], nenes[0]['fields']['interval']), (dq4npcport.WALK, 15))
        # 첫머리 목록에도 둘째 네네가 없다(첫머리 뒤 집을 다시 불러오기 전까지 걸리는 목록)
        lists2, _, _ = dq4npcport.port(DQ5, ROOT / 'rom' / 'dq4.nes')
        new, _ = ev.npc_lists(lists2)
        opening = next(lst for lst in new if lst['name'] == 'ch3_opening')['entries']
        self.assertFalse([e for e in opening if (e['time'], (e['fields']['x'], e['fields']['y'])) == L.NENE_WALKER[1:]])
        self.assertEqual(len([e for e in opening if e['time'] == 'day' and e['fields']['gfx'] == nenes[0]['fields']['gfx']]), 1)
        cellar = by[L.CELLAR]['entries']
        self.assertEqual([e['from'] for e in cellar if e['time'] == 'day'
                          and (e['fields']['x'], e['fields']['y']) == L.QUIT_MASTER[2]], [L._src('cellar')])


if __name__ == '__main__':
    unittest.main()
