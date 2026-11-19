"""UI 깨짐 규칙 치환 안 된 자리: 읽은 글자열에 자리 표시가 그대로 찍혔다. 중괄호 「{」·「}」, 창 글자를 옮긴 롬
(screen.ref.korean)에서 가나 두 글자 이상 이어짐(「ああ」 꼴, 옮기지 않은 이름·문구). dq4winwatch 의 규칙 파일.
"""
import dq4wintext as wt
from dq4winwatch import Allow

NAME = '치환 안 됨'
MODE = 'report'
# 창 검사(dq4windowcheck)의 시험 장면 가운데 원본 DQ5 자료를 일부러 부르는 것. 걷기·사건 장면에는 예외가 없다(거기서
# 가나가 나오면 옮기지 않은 이름·문구다). 장면 이름 단위로만 두고, 그 장면의 다른 규칙은 그대로 본다.
DQ5_TALKS = (0x07, 0x09, 0x0A, 0x0D, 0x14, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x1B, 0x1C, 0x1D, 0x1F, 0x20, 0x21, 0x24, 0x25,
             0x26, 0x28, 0x2A, 0x2B, 0x2C, 0x2D, 0x2F, 0x31, 0x32, 0x33, 0x34, 0x35, 0x36, 0x38, 0x39, 0x3B, 0x3C, 0x3E)
ALLOW = tuple(Allow(f'*/talk{n:02X}', '방어구점 주인의 대화 번호를 원본 DQ5 사람 대화로 바꿔 여는 시험 장면, DQ4 게임에 나오지 않음')
              for n in DQ5_TALKS) + (
    Allow('*/partyitems', '가방에 원본 DQ5 물건 번호(0C 부터 셋 걸러 열둘)를 넣는 시험 장면, DQ4 게임에 나오지 않음'),)


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
