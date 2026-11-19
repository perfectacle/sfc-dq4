"""창 글자 asm 의 루틴이 다음 루틴으로 흘러내리지 않는지. 「둘 다 살림」 으로 푼 rebase 충돌이 루틴 끝의 RTS 를 떨어뜨린
적이 있고(asar 는 통과한다), 그러면 그 루틴은 바로 뒤 루틴을 이어 돈다."""
import re
import unittest
from pathlib import Path

ASM = Path(__file__).resolve().parent / 'dq4windowname.asm'
# 루틴의 마지막 명령으로 받는 것: 돌아가기·건너뛰기, 표(db/dw), 자리 옮기기
ENDS = re.compile(r'^\s+(RTS|RTL|RTI|JMP|JML|BRA|BRL|db|dw|dl|NOP|%)\b')
# 일부러 다음 루틴으로 이어지는 것(앞 루틴, 뒤 루틴)
FALLS = {('WnQtyDown', 'WnQtyDone')}


def routines(lines):
    labels = [(i, ln.split(':')[0]) for i, ln in enumerate(lines) if re.match(r'^[A-Za-z][A-Za-z0-9_]*:', ln)]
    for (i, name), (j, nxt) in zip(labels, labels[1:]):
        body = [x for x in lines[i + 1:j]
                if x.strip() and not x.strip().startswith(';') and not re.match(r'^[.+\-]', x.strip())
                and not x.startswith(('!', 'org', 'macro', 'endmacro', 'pushpc', 'pullpc', 'assert'))]
        if body:
            yield name, nxt, body[-1]


class FallThroughTest(unittest.TestCase):
    def test_routines_end_with_a_return_or_jump(self):
        bad = [(name, nxt, last.strip()) for name, nxt, last in routines(ASM.read_text(encoding='utf-8').splitlines())
               if not ENDS.match(last) and (name, nxt) not in FALLS]
        self.assertEqual(bad, [])

    def test_catches_a_dropped_rts(self):
        lines = ['A:', '    LDA #$00', '    STA $00', 'B:', '    RTS']
        self.assertEqual([(n, m) for n, m, last in routines(lines) if not ENDS.match(last)], [('A', 'B')])


if __name__ == '__main__':
    unittest.main()
