"""UI 깨짐 규칙 1a 테두리: 창 네 변의 칸에 그 자리 테두리 타일의 흰 선이 다 보여야 한다(dq4winwatch 의 규칙 파일).

자리마다 와야 할 타일은 모서리 08C, 위·아래 변 08D, 옆 변 08E 와 그 뒤집기다. 화면 칸 그림이 그 타일의 흰 선 점(색 1)을
모두 흰색으로 가져야 한다. 이름 위 줄을 합성한 칸·탁점 붙은 변(092~095)·구분선 이음(08F)·이음 모서리(08B)는 선이
그대로라 통과한다. 위에 있는 다른 창에 가려진 칸은 뺀다.
"""
import dq4winwatch as ww

NAME = '테두리'
MODE = 'report'
ALLOW = ()


def check(screen):
    out = []
    for w in screen.rects:
        for r, c, t, h, v in ww.border_cells(w):
            if screen.stroke_ok(r, c, t, h, v) or screen.hidden(w, r, c):
                continue
            # 메시지 넘김 표시 ▼ 는 원래 DQ5 가 메시지 창 아래 변 위에 그린다
            if t == ww.EDGE and v and screen.word(r, c) & 0x3FF == ww.PROMPT:
                continue
            edge = ('위', '아래')[r == w[2]] if r in (w[0], w[2]) else ('왼쪽', '오른쪽')[c == w[3]]
            out.append((r, c, f'창 {w} 의 {edge} 변 칸이 {screen.word(r, c):04X}'))
    return out
