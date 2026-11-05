"""dq4data 의 성장 곡선·주문 목록·명령줄 출력을 합성 PRG 와 임시 iNES 파일로 검사한다."""
import contextlib
import io
import os
import sys
import tempfile
import unittest
import warnings
from unittest import mock

import dq4data as d

PRG_SIZE = 32 * 0x4000


def put(prg, bank, addr, data):
    o = bank * 0x4000 + (addr & 0x3FFF)
    prg[o:o + len(data)] = bytes(data)


def word(v):
    return [v & 0xFF, v >> 8]


def run_cli(main, prg, *args):
    """합성 PRG 를 iNES 파일로 써서 main() 을 돌리고 출력 줄을 돌려준다."""
    head = bytes([0x4E, 0x45, 0x53, 0x1A, 32, 0]) + bytes(10)
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, 'x.nes')
        with open(path, 'wb') as f:
            f.write(head + bytes(prg))
        out = io.StringIO()
        with mock.patch.object(sys, 'argv', ['x', path, *args]), contextlib.redirect_stdout(out), \
                warnings.catch_warnings():
            warnings.simplefilter('ignore', ResourceWarning)   # main() 이 파일을 닫지 않고 읽는다
            main()
    return out.getvalue().splitlines()


def cli_prg():
    prg = bytearray(PRG_SIZE)
    starts = dict(zip(d.LISTS, (0xA000, 0xA010, 0xA020, 0xA030, 0xA040, 0xA050, 0xA060)))
    put(prg, d.NAMES_BANK, d.NAMES_PTR, [v for w in d.LISTS for v in word(starts[w])])
    put(prg, d.NAMES_BANK, starts['spell'], [0, 1, 0x0B, 1, 0x0C])         # あ, い
    put(prg, d.NAMES_BANK, starts['class'], [0, 1, 0x0B])
    put(prg, d.NAMES_BANK, starts['sex'], [0, 1, 0x0B])
    put(prg, d.NAMES_BANK, starts['item'], [0, 1, 0x40, 1, 0x41])          # ア, イ
    put(prg, d.NAMES_BANK, starts['monster'], [0, 1, 0x01])                # 0
    put(prg, d.NAMES_BANK, starts['place'], [0, 1, 0x0B])
    put(prg, d.NAMES_BANK, starts['tactic'], [0, 1, 0x0B])
    return prg


class CurveTests(unittest.TestCase):
    def setUp(self):
        self.prg = prg = bytearray(PRG_SIZE)
        put(prg, d.GROW_BANK, d.GROW_PTR + 0, word(0xA300))          # 경험치
        put(prg, d.GROW_BANK, d.GROW_PTR + 2, word(0xA340))          # 힘
        put(prg, d.GROW_BANK, d.GROW_PTR + 6, word(0xA380))          # 체력
        # 경험치: 초깃값 비트 0·1 = 3, 경계는 모두 먼 레벨
        put(prg, d.GROW_BANK, 0xA300, [0x9F, 0xFF, 0x7F, 0x7F, 0x7F])
        # 힘: 초깃값 1, 경계 레벨 5·3·8·10·12, 증가 기준 16
        put(prg, d.GROW_BANK, 0xA340, [0x85, 0x03, 0x08, 0x0A, 0x0C, 16])
        put(prg, d.GROW_BANK, 0xA380, [0x1F, 0x7F, 0x7F, 0x7F, 0x7F, 16])
        put(prg, d.GROW_BANK, d.GROW_RATE, [32])
        put(prg, d.GROW_BANK, d.GROW_RATE + 0x18, [3, 5, 2])

    def test_experience_multiplies_previous_step(self):
        self.assertEqual(d.curve(self.prg, 0, 0, 1), (0, 0))
        self.assertEqual(d.curve(self.prg, 0, 0, 2), (3, 3))
        self.assertEqual(d.curve(self.prg, 0, 0, 3), (9, 6))
        self.assertEqual(d.curve(self.prg, 0, 0, 4), (21, 12))

    def test_stat_steps_move_to_next_rate_past_each_edge(self):
        self.assertEqual(d.curve(self.prg, 0, 1, 1), (1, 1))
        self.assertEqual(d.curve(self.prg, 0, 1, 2), (4, 3))
        self.assertEqual(d.curve(self.prg, 0, 1, 5), (13, 3))
        self.assertEqual(d.curve(self.prg, 0, 1, 6), (15, 2))

    def test_hp_is_double_of_vitality(self):
        self.assertEqual(d.curve(self.prg, 0, 3, 6), (15, 3))
        self.assertEqual(d.curve(self.prg, 0, 6, 6), (30, 6))

    def test_levels_command_rows(self):
        rows = run_cli(d.main, self.prg, 'levels', '0')
        self.assertEqual(rows[0], '# 0 勇者  Lv exp str agi vit int luck hp mp')
        self.assertEqual(len(rows), 1 + 99)
        self.assertEqual(rows[6], ' 6 93 15 0 15 0 0 30 0')

    def test_levels_command_skips_mp_for_non_casters(self):
        rows = run_cli(d.main, self.prg, 'levels', '5')
        self.assertEqual(rows[0], '# 5 トルネコ  Lv exp str agi vit int luck hp mp')
        self.assertEqual(rows[6], ' 6 0 0 0 0 0 0 0')


class MenuTests(unittest.TestCase):
    def test_spell_menus_slices_by_person(self):
        prg = bytearray(PRG_SIZE)
        put(prg, d.ITEM_BANK, d.MENU_BATTLE, list(range(1, 19)))
        put(prg, d.ITEM_BANK, d.MENU_BATTLE + 18, list(range(40, 52)))
        put(prg, d.ITEM_BANK, d.MENU_FIELD + 8, [9, 8, 7])
        b0, f0 = d.spell_menus(prg, 0)
        self.assertEqual((b0, len(f0)), (list(range(1, 19)), 8))
        b1, f1 = d.spell_menus(prg, 1)
        self.assertEqual((b1, f1), (list(range(40, 52)), [9, 8, 7, 0, 0, 0, 0, 0]))
        self.assertEqual(d.spell_menus(prg, 5), ([], []))


class CliTests(unittest.TestCase):
    def setUp(self):
        self.prg = cli_prg()

    def test_names_lists_every_kind(self):
        out = run_cli(d.main, self.prg, 'names')
        self.assertEqual(out[0], '# spell 2')
        self.assertEqual(out[1:3], ['00 あ', '01 い'])
        self.assertIn('# tactic 1', out)
        self.assertEqual(sum(l.startswith('# ') for l in out), len(d.LISTS))

    def test_names_single_list(self):
        self.assertEqual(run_cli(d.main, self.prg, 'names', 'item'), ['# item 2', '00 ア', '01 イ'])

    def test_items_line(self):
        put(self.prg, d.ITEM_BANK, d.ITEM_PRICE, [0x85, 0x0A])
        put(self.prg, d.ITEM_BANK, d.ITEM_SCALE, [0x0A, 0x00])
        put(self.prg, d.ITEM_BANK, d.ITEM_POWER, [7, 3])
        put(self.prg, d.ITEM_BANK, d.EQUIP_MASK, [0b101])
        put(self.prg, d.ITEM_BANK, d.ITEM_USE, [0x41])
        put(self.prg, d.ITEM_BANK, d.ITEM_ACT[0], [0])
        put(self.prg, d.ACT_BANK, d.ITEM_ACT[0], [0])
        put(self.prg, d.ACT_BANK, d.ITEM_ACT[1], [0x33])
        line = run_cli(d.main, self.prg, 'items')[0]
        for part in ('00 ア', '기타', '강도   7', '가격    500', '勇.ミ.....', '8D1B=000010',
                     '8D9A=01/01', ' *', '행동 33', '저주'):
            self.assertIn(part, line)

    def test_monsters_lines(self):
        r = [2, 1, 9, 4, 30, 12, 8, 50, 0x7F, 1, 2, 3, 4, 5, 6] + [0] * 6 + [7]
        put(self.prg, d.MON_BANK, d.MON_TABLE, r)
        put(self.prg, d.MON_ACT[0], d.MON_ACT[1] + 1, [1])
        first, second = run_cli(d.main, self.prg, 'monsters')
        self.assertTrue(first.startswith('00 0 '))
        self.assertIn('경험치   258 골드   50 HP   30 MP   4 공  12 수   8 속   9 드롭 -', first)
        self.assertIn('행동 01い 00あ 00あ 00あ 00あ 00あ | 고르게 1회 AI 0 시작 잠 1/256 | 내성 -', second)

    def test_spells_line_shows_learners_and_slots(self):
        put(self.prg, d.SPELL_BANK, d.SPELL_MP + 1, [0xC5])
        put(self.prg, d.GROW_BANK, d.LEARN_MASK + 2, word(0xA400))
        put(self.prg, d.GROW_BANK, d.LEARN_LEVEL + 2, word(0xA500))
        put(self.prg, d.GROW_BANK, 0xA400, [0b10])
        put(self.prg, d.GROW_BANK, 0xA500, [0x83])
        put(self.prg, d.ITEM_BANK, d.MENU_BATTLE + 18, [1])
        put(self.prg, d.ITEM_BANK, d.MENU_FIELD + 8 + 2, [1])
        out = run_cli(d.main, self.prg, 'spells')
        self.assertEqual(len(out), 2)
        self.assertIn('01 い', out[1])
        self.assertIn('MP  5 적 그룹', out[1])
        self.assertTrue(out[1].endswith('クリフト 3*(전0,필18)'))
        self.assertTrue(out[0].endswith('MP  0 편 고정  '))

    def test_actions_lines(self):
        put(self.prg, d.ACT_BANK, d.ACT_HANDLER, word(0x9AD2))
        put(self.prg, d.FX_BANK, d.POWER, [10, 20])
        put(self.prg, d.FX_BANK, d.POWER + 0x38, [30, 40])
        put(self.prg, d.FX_BANK, d.HEAL[3], [5, 0xFF])
        put(self.prg, d.FX_BANK, d.SUCCESS, [0xE3])
        put(self.prg, d.FX_BANK, d.RESIST_RATE, [1, 2, 3, 4])
        out = run_cli(d.main, self.prg, 'actions')
        self.assertEqual(len(out), 256)
        self.assertEqual(out[0], '00 あ        11:$9AD2 위력 편 10+20 몬스터 30+40 양 전부 성공 편 256/256 '
                                 '몬스터 デイン 내성 [1, 2, 3, 4]')
        self.assertTrue(out[2].startswith('02          11:$0000'))

    def test_ai_tables(self):
        p = self.prg
        put(p, d.AI_BANK, d.AI_ITEM_GROUPS, word(0xA800) + word(0xA810) * 3)
        put(p, d.AI_BANK, 0xA800, [1, 2, 0x34, 0x12, 0xFF])
        put(p, d.AI_BANK, 0xA810, [0xFF])
        put(p, d.WEIGHTS[0], d.WEIGHTS[1] + 6, [1, 2, 3, 4, 5, 6])
        put(p, d.REGEN[0], d.REGEN[1], [0, 0, 8, 20])
        put(p, *d.START_STATUS, [9])
        for t in d.AI_TACTIC:
            put(p, d.AI_BANK, t, list(range(50)))
        out = run_cli(d.main, p, 'ai')
        self.assertIn('가중치 1 앞 칸 많이: 1 2 3 4 5 6', out)
        self.assertIn('재생: 0=None 1=(20, 27) 2=None 3=None', out)
        self.assertTrue(any(l.startswith('시작 상태 확률: 0=10/256 1=1/256') for l in out))
        self.assertIn('아이템 후보 0: イ>02@1234', out)
        self.assertIn('아이템 후보 1: ', out)
        self.assertIn('  1 09 0A 0B 0C 0D 0E 0F', out)
        self.assertEqual(sum(l.startswith('  평가 루틴') for l in out), 4)
        self.assertIn('13:$BB53 13:$A2DF フバーハ 문턱  작전 0-6: 00 00 00 00 00 00 00', out)


if __name__ == '__main__':
    unittest.main()
