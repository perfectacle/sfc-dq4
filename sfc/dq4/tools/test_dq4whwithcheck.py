"""dq4whwithcheck: 기록 읽기와 판정, 상수가 창 글자 코드(dq4windowname.asm)와 맞는지(롬 없이)."""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dq4whwithcheck as w  # noqa: E402

ASM = Path(__file__).resolve().parent / 'dq4windowname.asm'

GOOD = """333 meas 244 244 300
333 go 245 388
333 dma 245 400 60E1A0 1920
333 tmend 257 0
333 dma 257 100 60E1E0 104
333 done 258 900
334 meas 244 244 290
334 done 245 480
334 dma 247 800 60DE40 112
"""


class Judge(unittest.TestCase):
    def test_good_record_passes(self):
        bad, summary = w.judge(w.parse(GOOD))
        self.assertEqual(bad, [])
        self.assertIn('타일맵 끝 V 257', summary)

    def test_hold_fails(self):
        bad, _ = w.judge(w.parse(GOOD + '335 meas 244 244 300\n335 wait 245 100\n'))
        self.assertTrue(any('붙잡음' in b for b in bad))

    def test_small_margin_fails(self):
        # 문턱 줄 바로 앞에서 잰 기록(옛 문턱 245 판의 여유 414 와 같은 꼴)
        v = w.WITH_LINE - 1
        bad, _ = w.judge(w.parse(GOOD + f'336 meas {v} {v} {w.LINE_CLOCKS - 414}\n'))
        self.assertTrue(any('여유' in b for b in bad))

    def test_measured_after_threshold_fails(self):
        bad, _ = w.judge(w.parse(GOOD + f'337 meas {w.WITH_LINE} {w.WITH_LINE} 10\n'))
        self.assertTrue(any('문턱 뒤' in b for b in bad))

    def test_dma_running_past_vblank_fails(self):
        # 260 줄 끝에 시작한 320바이트 DMA 는 262 줄(화면)까지 간다
        bad, _ = w.judge(w.parse(GOOD + '338 dma 260 1000 60DE40 320\n'))
        self.assertTrue(any('귀선 밖' in b for b in bad))

    def test_dma_in_draw_lines_fails(self):
        bad, _ = w.judge(w.parse(GOOD + '339 dma 3 0 60DE40 64\n'))
        self.assertTrue(any('귀선 밖' in b for b in bad))

    def test_tilemap_without_end_mark_fails(self):
        bad, _ = w.judge(w.parse(GOOD + '340 meas 244 244 300\n340 go 245 388\n'))
        self.assertTrue(any('타일맵' in b for b in bad))

    def test_no_whwith_fails(self):
        bad, _ = w.judge(w.parse(''))
        self.assertTrue(any('돌지 않음' in b for b in bad))

    def test_dma_end(self):
        self.assertEqual(w.dma_end(245, 400, 1920), 256)
        self.assertEqual(w.dma_end(259, 1300, 104), 260)


class MatchesAsm(unittest.TestCase):
    def test_with_line(self):
        got = re.search(r'^!wh_with_line\s*=\s*(\d+)', ASM.read_text(), re.M)
        self.assertEqual(int(got.group(1)), w.WITH_LINE)

    def test_symbols_exist(self):
        text = ASM.read_text()
        for name in list(w.EVENTS.values()) + [s for r in w.RANGES for s in r]:
            top, _, local = name.partition('_')
            if local:
                body = text[text.index(f'\n{top}:'):]
                self.assertRegex(body, rf'\n\.{local}\n', name)
            else:
                self.assertIn(f'\n{name}:', text, name)

    def test_ranges_are_in_order(self):
        # DMA 를 건 코드를 「이 심볼부터 다음 심볼 앞까지」 로 가르므로, 두 심볼 사이에 다른 루틴이 끼면 그 DMA 도 센다
        text = ASM.read_text()
        for a, b in w.RANGES:
            self.assertLess(text.index(f'\n{a}:'), text.index(f'\n{b}:'))


if __name__ == '__main__':
    unittest.main()
