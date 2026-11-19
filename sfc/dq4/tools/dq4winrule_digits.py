"""UI 깨짐 규칙 숫자 맞춤: 한 창의 숫자 열(위아래 줄에서 가로로 겹치는 숫자 묶음)의 마지막 자리 열이 줄마다 다르다.
숫자는 롬 글자 칸(dq4wintext 'rom')의 0~9 가 이어진 묶음이다. dq4winwatch 의 규칙 파일.
"""
import dq4wintext as wt

NAME = '숫자 맞춤'
MODE = 'report'
ALLOW = ()


def runs(line):
    out, cur = [], None
    for x, ch, wd, k, _ in line.items:
        if k == 'rom' and ch.isdigit():
            if cur and x == cur[1]:
                cur[1] = x + wd
                continue
            cur = [x, x + wd]
            out.append(cur)
        else:
            cur = None
    return [tuple(r) for r in out]


def check(screen):
    got = wt.lines(screen)
    if not got:
        return []
    out = []
    for w, lines in got.items():
        cols = []          # [(시작, 끝, 줄)]
        for line in lines:
            cols += [(a, b, line) for a, b in runs(line)]
        for i, (a, b, la) in enumerate(cols):
            for c_, d, lb in cols[i + 1:]:
                if lb is la or not (a < d and c_ < b) or b == d:
                    continue
                r, c = wt.cell_of(w, lb.x, lb.y)
                out.append((r, c, f'창 {w} 「{la.text}」 와 「{lb.text}」 의 숫자 끝 열이 {b // 8}·{d // 8} 로 다름'))
    return out
