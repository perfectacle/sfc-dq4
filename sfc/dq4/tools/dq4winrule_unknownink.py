"""UI 깨짐 규칙 U2g 모르는 잉크: 창 안에 글자(dq4wintext 가 읽는 롬 글자 칸·빌드 글리프)도 아는 기호(wintext-symbols.txt·곧은
선)도 아닌 잉크 묶음이 있다. 글자 조각·쓰레기 타일(장비 창에서 메시지가 뜨는 동안 제목·목록이 글자 조각으로 깨진 꼴,
대열 바꾸기 정보 창 제목이 「진___」 으로 깨진 꼴). dq4winwatch 의 규칙 파일.

위 창에 가려진 칸·다른 창 테두리에 닿은 조각과 창 테두리 칸 줄·열의 잉크는 dq4wintext 가 못 읽음으로 세지 않는다
(가려져 잘린 글자는 깨짐이 아님, 테두리 칸은 테두리·창 밖 규칙의 몫).
"""
import dq4wintext as wt

NAME = '모르는 잉크'
MODE = 'report'
ALLOW = ()


def check(screen):
    got = wt.lines(screen)
    if not got:
        return []
    out = []
    for w, lines in got.items():
        for line in lines:
            for x, ch, wd, kind, top in line.items:
                if ch == wt.UNREAD:
                    r, c = wt.cell_of(w, x, top)
                    out.append((r, c, f'창 {w} 「{line.text}」 에 글자·아는 기호가 아닌 잉크({wd}점 폭)'))
    return out
