"""UI 깨짐 규칙 U2c 조사: 이름 낱말(dq4wintext.vocabulary) 바로 뒤 조사가 받침과 맞지 않는다. 받침 있는 이름 뒤
「를·는·가·와」, 받침 없는 이름 뒤 「을·은·이·과」 면 건다. dq4winwatch 의 규칙 파일. 글자는 dq4wintext 로 읽는다.

낱말 = 이름 + 조사 한 글자 꼴만 본다(「크리프트는」). 이름 낱말이 아닌 낱말 뒤는 보지 않는다(일반 낱말의 끝 글자가 조사처럼
보이는 것과 가를 수 없음).
"""
import dq4wintext as wt

NAME = '조사'
MODE = 'report'
ALLOW = ()
PAIRS = {'을': '를', '를': '을', '은': '는', '는': '은', '이': '가', '가': '이', '과': '와', '와': '과'}
WITH_FINAL = set('을은이과')


def check(screen):
    got = wt.lines(screen)
    if not got:
        return []
    names = wt.party_names() | {v for v in wt.vocabulary() if len(v) >= 2}
    out = []
    for w, lines in got.items():
        for line in lines:
            for token in line.text.split():
                if len(token) < 3 or token[-1] not in PAIRS or token[:-1] not in names:
                    continue
                final = wt.has_final(token[-2])
                if final is None or final == (token[-1] in WITH_FINAL):
                    continue
                r, c = wt.cell_of(w, line.x, line.y)
                out.append((r, c, f'창 {w} 「{token}」: 「{token[:-1]}」 뒤에는 「{PAIRS[token[-1]]}」'))
    return out
