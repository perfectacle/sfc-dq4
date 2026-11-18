import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))

import dq4asmmath as m  # noqa: E402


def scan(text):
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / 'a.asm').write_text(text, encoding='utf-8')
        return m.mixed(units=(('a.asm',),), root=Path(tmp))


class RepoTests(unittest.TestCase):
    def test_every_asm_is_in_a_unit(self):
        # 새 asm 을 UNITS 에 올리지 않으면 이 검사가 그 파일을 보지 않는다
        listed = {rel for unit in m.UNITS for rel in unit if ':' not in rel}
        found = {p.relative_to(ROOT).as_posix() for top in ('sfc', 'fc', 'nds', 'tools')
                 for p in (ROOT / top).rglob('*.asm')}
        self.assertEqual(found, listed)

    def test_no_mixed_precedence_where_math_pri_is_off(self):
        # 값이 같아도 괄호로 뜻을 고정한다: 정의 값이나 숫자 하나가 바뀌면 왼쪽부터 셈이 조용히 다른 값을 낸다
        self.assertEqual([r for r in m.mixed() if not r.pri], [])


class CheckerTests(unittest.TestCase):
    def test_left_to_right_value_differs(self):
        [r] = scan('    ADC #1+10*9\n')
        self.assertTrue(r.order_sensitive)
        self.assertEqual(r.left, (99, 91))
        self.assertFalse(r.pri)

    def test_cell_base_example(self):
        rows = scan('    LDX.w #$5000+(18*32+3)*2\n')
        top = [r for r in rows if r.expr.startswith('$5000')]
        self.assertEqual(top[0].left, (0xA486, 0x5486))

    def test_same_value_still_reported(self):
        [r] = scan('    LDX.w #!w*9-2\n')
        self.assertFalse(r.order_sensitive)

    def test_parentheses_and_single_class_pass(self):
        self.assertEqual(scan('    LDA.l $7E0000|(!x+1)\n    LDX.w #((18*32)+2)*2\n    LDA.w (!m&$FFFF)+2,Y\n'
                              '    ADC.w #(10*9)+1\n    LDA #$12+$34-1\n    LDA ($12),Y\n'), [])

    def test_math_pri_on_marks_rows(self):
        [r] = scan('math pri on\n    ADC #1+10*9\n')
        self.assertTrue(r.pri)

    def test_asar_version_header_turns_pri_on(self):
        [r] = scan('asar 1.90\n    ADC #1+10*9\n')
        self.assertTrue(r.pri)

    def test_define_is_expanded_like_asar(self):
        [r] = scan('!a = 1+2\n    LDA #!a*3\n')
        self.assertEqual(r.left, (9, 7))

    def test_labels_branches_and_binary(self):
        self.assertEqual(scan('Lbl:\n-\n    BRA -\n+\n    BCC ++\n.loc\n    AND #%0101\n    LDA #$01 : db $89-$01\n'
                              '?m:\n    JML <o>+4\nX = 17\n'), [])

    def test_binary_literal_after_operator(self):
        [r] = scan('    LDA #1+2*%11\n')
        self.assertEqual(r.left, (9, 7))

    def test_comparison_splits_segments(self):
        self.assertEqual(scan('if !n*2 == 4+1\nendif\n'), [])


if __name__ == '__main__':
    unittest.main()
