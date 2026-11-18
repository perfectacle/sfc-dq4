"""UI 깨짐 규칙 U2d 치환 안 된 자리: 읽은 글자열에 자리 표시가 그대로 찍혔다. 중괄호 「{」·「}」, 창 글자를 옮긴 롬
(screen.ref.korean)에서 가나 두 글자 이상 이어짐(「ああ」 꼴, 옮기지 않은 이름·문구). dq4winwatch 의 규칙 파일.
"""
import dq4wintext as wt

NAME = '치환 안 됨'
MODE = 'report'
ALLOW = ()


def kana(ch):
    return 'ぁ' <= ch <= 'ヿ'


def check(screen):
    got = wt.lines(screen)
    if not got:
        return []
    out = []
    for w, lines in got.items():
        for line in lines:
            t = line.text
            why = None
            if '{' in t or '}' in t:
                why = '중괄호 자리 표시'
            elif screen.ref.korean and any(kana(a) and kana(b) for a, b in zip(t, t[1:])):
                why = '가나가 이어 찍힘'
            if why:
                r, c = wt.cell_of(w, line.x, line.y)
                out.append((r, c, f'창 {w} 「{t}」: {why}'))
    return out
