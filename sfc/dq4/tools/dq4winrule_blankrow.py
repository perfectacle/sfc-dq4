"""UI 깨짐 규칙 U2i 목록 빈 줄: 창 글자(Galmuri9) 줄이 셋 이상 같은 간격으로 늘어선 창에서, 가운데 한 줄 자리가 비었다
(팔기 목록의 한 줄이 빈 채로 보인 꼴). 위·아래 끝의 빈 자리는 목록이 거기서 끝난 것이라 보지 않는다. dq4winwatch 의 규칙
파일. 글자는 dq4wintext 로 읽는다.
"""
from collections import Counter

import dq4wintext as wt

NAME = '목록 빈 줄'
MODE = 'report'
ALLOW = ()


def check(screen):
    got = wt.lines(screen)
    if not got:
        return []
    out = []
    for w, lines in got.items():
        ys = sorted({ln.y for ln in lines if wt.drawn_only(ln) and wt.word_chars(ln)})
        if len(ys) < 3:
            continue
        gaps = [b - a for a, b in zip(ys, ys[1:])]
        step, n = Counter(gaps).most_common(1)[0]
        if n < 2 or step < 8:
            continue
        for a, b in zip(ys, ys[1:]):
            if b - a == 2 * step:
                r, c = wt.cell_of(w, 8, a + step)
                out.append((r, c, f'창 {w} 의 y{a} 와 y{b} 사이 목록 줄(y{a + step})이 비었음'))
    return out
