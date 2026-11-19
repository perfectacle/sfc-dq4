"""UI 깨짐 규칙 2a 창 밖: 창 사각형 바로 바깥 한 칸(다른 창 사각형 밖)은 투명해야 한다. 글자가 창을 넘었다
(dq4winwatch 의 규칙 파일)."""
import dq4winwatch as ww

NAME = '창 밖'
MODE = 'report'
ALLOW = ()


def check(screen):
    out, seen = [], set()
    for w in screen.rects:
        r1, c1, r2, c2 = w
        ring = [(r1 - 1, c) for c in range(c1 - 1, c2 + 2)] + [(r2 + 1, c) for c in range(c1 - 1, c2 + 2)]
        ring += [(r, c1 - 1) for r in range(r1, r2 + 1)] + [(r, c2 + 1) for r in range(r1, r2 + 1)]
        for r, c in ring:
            if not (0 <= r < 32 and 0 <= c < 32) or (r, c) in seen or screen.in_window(r, c):
                continue
            seen.add((r, c))
            px = screen.shown(r, c)
            if px is None or any(any(row) for row in px):
                out.append((r, c, f'창 {w} 바깥 칸이 {screen.word(r, c):04X}'))
    return out
