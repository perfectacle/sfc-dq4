import os
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4wintext as wt  # noqa: E402
import dq4winrule_cut as cut  # noqa: E402
import dq4winrule_digits as digits  # noqa: E402
import dq4winrule_josa as josa  # noqa: E402
import dq4winrule_party as party  # noqa: E402
import dq4winrule_raw as raw  # noqa: E402
import dq4winrule_textlines as textlines  # noqa: E402
import dq4winrule_unknownink as unknownink  # noqa: E402
import dq4winrule_blankrow as blankrow  # noqa: E402
import dq4winrule_phrase as phrase  # noqa: E402

W = (2, 2, 12, 20)


class FakeRef:
    korean = True
    border = {}
    rom = b''

    def stroke(self, tile, h, v):
        return ()


class FakeScreen:
    """창 하나(W), 칸 그림은 grid(점 격자, 창 사각형 기준)에서. 가린 칸 없음."""

    def __init__(self, grid=None, wram=None):
        self.grid, self.ref, self._wram = grid, FakeRef(), wram or {}
        self.rects = [W]

    def hidden(self, w, r, c):
        return False

    def word(self, r, c):
        return 0x0100 + (r - W[0]) * 32 + (c - W[1])      # 롬 글자 칸(01~8A) 밖

    def shown(self, r, c):
        y0, x0 = (r - W[0]) * 8, (c - W[1]) * 8
        return [self.grid[y0 + y][x0:x0 + 8] for y in range(8)]

    def wram(self, addr, n=1):
        return [self._wram.get(addr + i) for i in range(n)]


def line(text, y=8, x=8, kind='galmuri9', step=10, top=6):
    items, pos = [], x
    for ch in text:
        if ch == ' ':
            pos += 4
            continue
        items.append((pos, ch, step if kind != 'rom' else 8, kind, top))
        pos += step if kind != 'rom' else 8
    return wt.Line(y, items)


def screen_with(lines, wram=None):
    s = FakeScreen(wram=wram)
    s._wintext = {W: lines}
    return s


class LineTests(unittest.TestCase):
    def test_line_joins_with_gap_spaces(self):
        ln = line('크리프트 호이민')
        self.assertEqual(ln.text, '크리프트 호이민')
        self.assertEqual(ln.right, 8 + 40 + 4 + 30)

    def test_has_final(self):
        self.assertTrue(wt.has_final('민'))
        self.assertFalse(wt.has_final('트'))
        self.assertIsNone(wt.has_final('A'))


class RuleTests(unittest.TestCase):
    def test_cut_flags_prefix_of_a_name(self):
        with mock.patch.object(wt, 'vocabulary', return_value=frozenset({'크리프트', '호이민'})):
            got = cut.check(screen_with([line('크리프 호이민')]))
        self.assertEqual(len(got), 1)
        self.assertIn('「크리프」', got[0][2])

    def test_cut_skips_whole_words_and_message_lines(self):
        with mock.patch.object(wt, 'vocabulary', return_value=frozenset({'크리프트', '조사', '조사하다'})):
            self.assertEqual(cut.check(screen_with([line('조사')])), [])
            self.assertEqual(cut.check(screen_with([line('크리프', kind='message')])), [])

    def test_josa_by_final(self):
        with mock.patch.object(wt, 'party_names', return_value=frozenset({'호이민', '크리프트'})), \
                mock.patch.object(wt, 'vocabulary', return_value=frozenset()):
            self.assertEqual(len(josa.check(screen_with([line('호이민는 크리프트을')]))), 2)
            self.assertEqual(josa.check(screen_with([line('호이민은 크리프트를')])), [])

    def test_raw_placeholder_and_kana(self):
        self.assertEqual(len(raw.check(screen_with([line('{1008}')]))), 1)
        self.assertEqual(len(raw.check(screen_with([line('ああ', kind='rom')]))), 1)
        self.assertEqual(raw.check(screen_with([line('천 옷')])), [])

    def test_digit_columns_must_end_together(self):
        a, b = line('27', y=8, x=48, kind='rom'), line('5', y=24, x=48, kind='rom')
        self.assertEqual(len(digits.check(screen_with([a, b]))), 1)
        c = line('5', y=24, x=56, kind='rom')
        self.assertEqual(digits.check(screen_with([a, c])), [])

    def test_text_lines_split_tops_and_overlap(self):
        split = wt.Line(8, [(8, '가', 10, 'galmuri9', 6), (18, '나', 10, 'galmuri9', 9)])
        with mock.patch.object(wt, 'band_height', return_value=13):
            self.assertEqual(len(textlines.check(screen_with([split]))), 1)
            a = line('가나', y=8, top=6)
            b = line('다라', y=16, top=12)
            self.assertEqual(len(textlines.check(screen_with([a, b]))), 1)
            c = line('다라', y=24, top=22)
            self.assertEqual(textlines.check(screen_with([a, c])), [])

    def test_name_renderer_one_pixel_lower_passes_but_two_fail(self):
        # 이름 렌더러 칸의 글자는 창 글자 그림보다 1점 아래가 공통 꼴이고, 2점이면 이름이 내려앉은 깨짐이다
        def split(top, word):
            ln = wt.Line(8, [(8, '가', 10, 'galmuri9', 6), (24, '나', 10, 'galmuri9', top)])
            screen = screen_with([ln])
            screen.word = lambda r, c: word.get(c - W[1], 0x0100 + c)
            return screen

        with mock.patch.object(wt, 'band_height', return_value=13):
            self.assertEqual(textlines.check(split(7, {3: 0x0180})), [])
            self.assertEqual(len(textlines.check(split(8, {3: 0x0180}))), 1)
            self.assertEqual(len(textlines.check(split(7, {}))), 1)
            # 모험의 서 목록 줄: 메뉴 칸(2D0~)이 이름이고, 180~ 칸은 장소 이름을 그린 창 글자다
            self.assertEqual(textlines.check(split(7, {1: 0x0180, 3: 0x02D0})), [])
            self.assertEqual(len(textlines.check(split(7, {1: 0x02D0, 3: 0x0180}))), 1)

    def test_party_order_against_records(self):
        wram = {party.COUNT: 2, party.RECORDS: 0x09, party.RECORDS + party.RECORD: 0x85}
        names = frozenset({'크리프트', '호이민'})
        with mock.patch.object(wt, 'party_names', return_value=names):
            self.assertEqual(party.check(screen_with([line('크리프트 호이민')], wram)), [])
            got = party.check(screen_with([line('호이민 크리프트')], wram))
            self.assertEqual(len(got), 1)
            self.assertEqual(len(party.check(screen_with([line('호이민 호이민')], wram))), 1)


class ShapeTests(unittest.TestCase):
    def test_components_and_shape(self):
        comps = wt.components({(0, 0), (1, 1), (5, 5)})
        self.assertEqual(sorted(len(c) for c in comps), [1, 2])
        self.assertEqual(wt.shape([(0, 0), (1, 1)]), '#./.#')

    def test_line_symbols(self):
        self.assertEqual(wt.line_symbol('#####'), '─')
        self.assertEqual(wt.line_symbol('#/#/#'), '│')
        self.assertIsNone(wt.line_symbol('##/##'))

    def test_known_symbols_file_parses(self):
        k = wt.known()
        self.assertIn('「', k.values())
        self.assertIn('＊', k.values())

    def test_unknown_ink_rule(self):
        ln = wt.Line(8, [(8, '가', 10, 'galmuri9', 6), (20, wt.UNREAD, 3, None, 6)])
        self.assertEqual(len(unknownink.check(screen_with([ln]))), 1)
        self.assertEqual(unknownink.check(screen_with([line('가나')])), [])


class SceneRuleTests(unittest.TestCase):
    def test_blank_row_inside_a_list(self):
        rows = [line('가나', y=y) for y in (8, 24, 56, 72)]
        self.assertEqual(len(blankrow.check(screen_with(rows))), 1)
        self.assertEqual(blankrow.check(screen_with([line('가나', y=y) for y in (8, 24, 40)])), [])

    def test_fixed_phrase_swapped_while_other_lines_stay(self):
        class Run:
            pass
        menu = ['쓰기', '건네기']
        a = screen_with([line(t, y=8 + 16 * i) for i, t in enumerate(menu + ['버리기'])])
        b = screen_with([line(t, y=8 + 16 * i) for i, t in enumerate(menu + ['수비력'])])
        other = screen_with([line(t, y=8 + 16 * i) for i, t in enumerate(['예', '아니요', '수비력'])])
        words = frozenset({'쓰기', '건네기', '버리기', '수비력', '예', '아니요'})
        with mock.patch.object(wt, 'ui_words', return_value=words):
            with mock.patch.object(wt, 'steady_screens', return_value=[(10, a, {}), (20, b, {})]):
                self.assertEqual(len(phrase.check_run(Run())), 1)
            with mock.patch.object(wt, 'steady_screens', return_value=[(10, a, {}), (20, other, {})]):
                self.assertEqual(phrase.check_run(Run()), [])


@unittest.skipUnless(os.environ.get('DQ4_GALMURI'), 'DQ4_GALMURI 가 없음')
class ReadTests(unittest.TestCase):
    def test_reads_a_galmuri9_word_drawn_on_the_window_background(self):
        import dq4menupatch as MP
        cols = MP.render(wt.font('galmuri9'), '천 옷')
        rows, width = (W[2] - W[0] + 1) * 8, (W[3] - W[1] + 1) * 8
        grid = [[2] * width for _ in range(rows)]
        for c, tile in enumerate(cols):          # 칸마다 16줄 × 8점(dq4menupatch.render)
            for y, row in enumerate(tile):
                for x, v in enumerate(row):
                    if v:
                        grid[10 + y][16 + c * 8 + x] = 3
        s = FakeScreen(grid)
        with mock.patch.object(wt, 'rom_table_for', return_value={}), mock.patch.object(wt, 'use_rom'), \
                mock.patch.object(wt, 'comparable', return_value=True):
            got = wt.lines(s)[W]
        self.assertEqual([ln.text for ln in got], ['천 옷'])


if __name__ == '__main__':
    unittest.main()
