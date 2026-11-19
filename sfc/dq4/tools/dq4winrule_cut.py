"""UI 깨짐 규칙 잘림: 창 글자(Galmuri9)로 읽은 낱말이 이름 낱말(dq4wintext.vocabulary)의 앞부분뿐이다(「크리프ㅡ」,
「외톨이 메탈 갑」 꼴). dq4winwatch 의 규칙 파일. 글자는 dq4wintext 로 읽는다.

창 글자(Galmuri9)로만 읽은 줄(메시지 글자가 섞이지 않은 줄)의 낱말만 본다. 낱말은 띄움으로 나눈 한글 줄기다. 두 글자 이상인 낱말이 이름 낱말·창 고정 낱말(dq4wintext.ui_words)이 아니고, 그 낱말로
시작하는 더 긴 이름 낱말이 있으면 건다. 위 창에 가려진 칸·창 밖에 닿은 줄은 앞만 보이는 것이라
보지 않는다(dq4wintext.near_cover). 못 읽은 칸(⍰)이 붙은 낱말도 보지 않는다.
"""
import dq4wintext as wt

NAME = '잘림'
MODE = 'report'
ALLOW = ()


def hangul_word(token):
    return token and all('가' <= ch <= '힣' or 'ㄱ' <= ch <= 'ㅣ' for ch in token)


def check(screen):
    got = wt.lines(screen)
    if not got:
        return []
    vocab = wt.vocabulary()
    out = []
    for w, lines in got.items():
        for line in lines:
            kinds = {k for _, _, _, k, _ in line.items}
            if 'galmuri9' not in kinds or kinds & {'message', 'dq5message'} or wt.near_cover(screen, w, line):
                continue
            for token in line.text.split():
                if not hangul_word(token) or token in vocab:
                    continue
                longer = sorted(v for v in vocab if v.startswith(token) and len(v) > len(token)) if len(token) >= 2 else []
                if longer:
                    r, c = wt.cell_of(w, line.x, line.y)
                    out.append((r, c, f'창 {w} 「{line.text}」 의 「{token}」 이 「{longer[0]}」 의 앞부분'))
    return out
