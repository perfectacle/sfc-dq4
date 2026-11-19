"""롬 없이: 모험의 서 목록 한 줄(번호·이름·Lv·레벨·곳 이름)이 목록 창 안쪽에 들어가는지."""
import os
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import dq4windowtext as wt  # noqa: E402


class SaveLineTest(unittest.TestCase):
    def test_the_fixed_part_matches_the_list_renderer(self):
        """커서·번호·「:」 3열 + 이름(dq4nameentry.asm !ne_list_cols) + 빈칸 2 + Lv 1 + 레벨 2 + 빈칸 2."""
        asm = (HERE / 'dq4nameentry.asm').read_text(encoding='utf-8')
        cols = int(re.search(r'^!ne_list_cols = (\d+)', asm, re.M).group(1))
        self.assertEqual(wt.SAVE_FIXED_COLS, 3 + cols + 2 + 1 + 2 + 2)
        self.assertEqual(cols, 5)

    def test_place_names_are_held_to_what_is_left_and_the_build_stops_beyond(self):
        table, limit, strict = wt.KINDS[wt.PLACE_KIND]
        self.assertEqual((limit, strict), (wt.SAVE_PLACE_COLS, True))
        self.assertEqual(wt.SAVE_PLACE_COLS, 8)

    @unittest.skipUnless(os.environ.get('DQ4_GALMURI'), 'DQ4_GALMURI 가 필요')
    def test_every_place_name_fits(self):
        import dq4menupatch
        font = dq4menupatch.Font('galmuri9')
        widths = {n: len(wt.columns(font, n)) for n in wt.place_names().values()}
        self.assertLessEqual(max(widths.values()), wt.SAVE_PLACE_COLS, widths)


if __name__ == '__main__':
    unittest.main()
