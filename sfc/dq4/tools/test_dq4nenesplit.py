import unittest

from test_dq4windowname import ASM


class NeneSplitTest(unittest.TestCase):
    """네네 보기 짧은 마지막 쪽: 아래 테두리를 n + 1 번째 줄의 윗 줄(2n + 3)에 두고, 그 줄 글자는 테두리를 바탕으로 위 줄
    합성(뒤집은 테두리 바탕은 WnBaseRow 의 뒤집기 갈래)이라 FC 처럼 n + 1 번째 줄이 보인다. 표지는 3장 flag 가 설 때만."""

    def setUp(self):
        self.asm = ASM.read_text(encoding='utf-8')

    def body(self, name):
        start = self.asm.index(f'\n{name}:')
        return self.asm[start:self.asm.index('\n; ', start + 1)]

    def test_mark_needs_chapter3(self):
        on = self.body('NeneOn')
        self.assertLess(on.index('!chapter3_flag'), on.index('!nene_mark'))
        self.assertEqual(self.asm.count('JSR NeneOn'), 4)   # WnText 아홉 칸, QpFrame, NeneListFar, NeneSplitBase
        self.assertNotIn('LDA.l !nene_mark\n    AND #$00FF\n    SEC', self.asm)

    def test_border_goes_under_line_n_plus_1_before_its_name(self):
        text = self.asm[self.asm.index('\nWnText:'):self.asm.index('\nWtAlloc:')]
        self.assertIn('JSR NeneSplitBase\n    JSR WtAlloc', text)
        arrow = self.asm[self.asm.index('\nNeneArrow:'):]
        arrow = arrow[:arrow.index('\n.nosplit')]
        self.assertIn('CMP #$0096\n    BCS +', arrow)          # 합성 칸은 덮지 않는다
        self.assertNotIn('$2001', arrow)                       # 윗 줄을 빈칸으로 덮지 않는다


if __name__ == '__main__':
    unittest.main()
