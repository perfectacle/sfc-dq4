"""UI 깨짐 규칙 고정 문구 바뀜: 같은 자리의 창에서 다른 줄들은 그대로인데 한 줄이, 창 고정 낱말(dq4wintext.ui_words)만으로
된 문구에서 낱말이 하나도 겹치지 않는 다른 고정 낱말 문구로 바뀌었다(배포된 1장의 도구 → 건네기 → 「누구에게」 동안 「어떻게 할까」 창의 「버리기」 가
「수비력」 으로 바뀐 꼴). dq4winwatch 의 장면 전체 규칙(check_run). 글자는 dq4wintext 로 읽는다.

창은 사각형으로 잇는다. 엔진은 위 창을 열고 닫을 때 아래 창들을 다시 그리므로(그리기 기록 D 가 남음) 다시 그림으로 비교를
끊지 않고, 대신 같은 창의 다른 고정 문구 줄이 둘 이상 그대로이고 바뀐 줄이 하나뿐일 때만 건다(같은 자리에 다른 메뉴 창이
뜬 것과 가름). 줄은 창 안 y 로 맞추고, 고르기 손가락·넘김 표시·숫자는 빼고 견준다(dq4wintext.phrase). 메시지 글자가 든 줄은
보지 않는다. 목록이 굴러 이름이 바뀌는 것은 이름이 고정 낱말이 아니라 걸리지 않는다.
"""
import dq4wintext as wt

NAME = '고정 문구 바뀜'
MODE = 'report'
ALLOW = ()


def fixed(text, words):
    return bool(text) and all(t in words for t in text.split())


def check_run(run):
    words = wt.ui_words()
    last = {}           # 사각형 → {y: 문구}
    out = []
    for first, screen, _ in wt.steady_screens(run):
        got = wt.lines(screen)
        if not got:
            continue
        for w, lines in got.items():
            now = {ln.y: wt.phrase(ln) for ln in lines if wt.drawn_only(ln) and fixed(wt.phrase(ln), words)}
            # 위 창에 거의 가려진 모습(문구 줄이 둘 미만)은 건너뛰고 앞 모습과 견준다
            if len(now) < 2:
                continue
            prev = last.get(w)
            last[w] = now
            if not prev:
                continue
            same = [y for y in now if prev.get(y) == now[y]]
            # 낱말이 하나도 겹치지 않게 바뀐 줄만(「문 조사」 → 「문」 은 옆 창이 뒤를 가린 것)
            changed = [y for y in now if y in prev and not set(prev[y].split()) & set(now[y].split())]
            if len(same) >= 2 and len(changed) == 1:
                y = changed[0]
                out.append((first, f'창 {w} 의 줄 y{y} 가 「{prev[y]}」 → 「{now[y]}」(다른 줄 {len(same)}개는 그대로)'))
    return out
