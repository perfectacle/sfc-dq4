"""UI 깨짐 규칙 1b 잔상: 어느 창 사각형에도 들지 않은 칸이 테두리 타일(08B~095)을 가리킨다. 닫힌 창의 조각이나 반쯤
지운 테두리다(dq4winwatch 의 규칙 파일). 창 화면(테두리 그림이 롬과 같은 모습)에서만 본다."""
import dq4winwatch as ww

NAME = '잔상'
MODE = 'report'
ALLOW = ()


def check(screen):
    if not screen.window_screen:
        return []
    out = []
    for r in range(32):
        for c in range(32):
            w = screen.word(r, c)
            if ww.BORDER_FIRST <= w & 0x3FF <= ww.BORDER_LAST and not screen.in_window(r, c):
                out.append((r, c, f'창 밖 테두리 조각 {w:04X}'))
    return out
