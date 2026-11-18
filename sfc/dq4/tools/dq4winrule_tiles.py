"""UI 깨짐 규칙 2c 깨짐·가나: 창 안쪽 칸 그림에 투명한 점(색 0)이 있거나(창 바탕을 뚫은 쓰레기 타일), 그림이 롬 가나
(04:E528 1bpp, 둘째 평면 FF)와 같다(옮기지 않은 일본어 글자). dq4winwatch 의 규칙 파일. 위 창에 가려진 칸은 뺀다."""
import dq4winwatch as ww

NAME = '깨짐'
MODE = 'report'
ALLOW = ()


def check(screen):
    out = []
    for w in screen.rects:
        r1, c1, r2, c2 = w
        for r in range(r1 + 1, r2):
            for c in range(c1 + 1, c2):
                if screen.hidden(w, r, c):
                    continue
                wd = screen.word(r, c)
                px = screen.shown(r, c)
                if px is None or any(0 in row for row in px):
                    out.append((r, c, f'창 {w} 안 칸 {wd:04X} 에 투명한 점'))
                elif wd & 0x3FF in ww.KANA and px == ww.flip(screen.ref.kana[wd & 0x3FF], wd & 0x4000, wd & 0x8000):
                    out.append((r, c, f'창 {w} 안 칸 {wd:04X} 가 가나 그림'))
    return out
