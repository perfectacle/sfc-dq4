"""UI 깨짐 규칙 1d 변 어긋남: 겹친 두 창의 같은 쪽 옆 변(왼쪽·오른쪽)이 정확히 한 칸 어긋났다(dq4winwatch 의 규칙 파일).

계기: 가게 동료 창 3A 를 이름 다섯 칸에 맞춰 넓히자, 뒤에 깔린 메시지 창(원본 DQ5 는 둘 다 열 2~29)이 3A 아래로 한 칸
좁게 삐져 나왔다. 두 창이 모두 엔진 창이고 둘 다 원본 DQ5 와 그 변 자리가 같은 창이면(Ref.moved 밖) 원본에도 있는
어긋남이라 걸지 않는다. 걸린 칸은 위 창의 그 변 모서리 칸이다.
위·아래 변은 보지 않는다: DQ5 는 도구 목록 창(아래 변 26줄)을 메시지 창(27줄) 위에 띄우는 등 한 줄 차이가 흔하다.

알려진 깨짐은 장면·칸이 아니라 어긋난 창 짝(두 창 사각형과 변)으로 적는다(PAIRS). 목록에 없는 짝이 어느 장면에서든
어긋나면 실패다. 짝 하나를 고치면 그 줄만 지운다.
"""
import re

NAME = '변 어긋남'
MODE = 'fail'
ALLOW = ()

# 알려진 짝: (창 둘, 변) → 「꼴 이름: 까닭」. 포팅에서 창을 넓히거나 옮겨 겹친 창과 한 칸 엇나간 것(주인 win-borders)
CMD = (4, 2, 12, 13)                     # 명령 창
PARTY = (19, 16, 27, 28)                 # 일행 상태 창
ITEMS = (3, 15, 27, 27)                  # 물건 목록
PAIRS = {
    (frozenset({CMD, (4, 3, 10, 12)}), '왼쪽'): 'E: 명령 창 위 장비 「누구」 창',
    (frozenset({PARTY, (4, 15, 20, 24)}), '왼쪽'): 'F: 일행 상태 창 위 주문 목록',
    (frozenset({PARTY, ITEMS}), '왼쪽'): 'F: 일행 상태 창 위 물건 목록',
    (frozenset({PARTY, ITEMS}), '오른쪽'): 'F: 일행 상태 창 위 물건 목록',
    (frozenset({PARTY, (21, 15, 25, 22)}), '왼쪽'): 'F: 일행 상태 창 위 소비 MP 창',
    (frozenset({PARTY, (2, 19, 28, 29)}), '오른쪽'): 'F: 일행 상태 창과 창 (2,19)-(28,29)',
    (frozenset({PARTY, (11, 16, 19, 29)}), '오른쪽'): 'F: 일행 상태 창 위 대열 바꾸기 정보 창',
    (frozenset({(19, 22, 27, 28), ITEMS}), '오른쪽'): 'G: 1인 상태 창 위 물건 목록',
    (frozenset({(4, 22, 9, 28), (8, 5, 13, 29)}), '오른쪽'): 'H: 모험의 서 지우기 「예/아니오」 와 서 고르기 창',
    (frozenset({(2, 14, 6, 29), (5, 22, 9, 28)}), '오른쪽'): 'I: 은행 「예/아니오」 와 도구 창',
    (frozenset({ITEMS, (5, 22, 9, 28)}), '오른쪽'): 'M: 물건 목록 위 「예/아니오」',
    (frozenset({(6, 5, 12, 14), (2, 6, 8, 17)}), '왼쪽'): 'N: 도구 「누구」 창 위 물건 정보 창',
}
DESC = re.compile(r'창 (\(.*?\)) 과 (\(.*?\)) 의 (왼쪽|오른쪽) 변')


def known(why):
    m = DESC.match(why)
    if not m:
        return None
    rects = frozenset(tuple(int(v) for v in g.strip('()').split(', ')) for g in m.groups()[:2])
    return PAIRS.get((rects, m.group(3)))


def overlap(a, b):
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


def number(screen, rect):
    """창 번호. 위 창에 가려 화면에서만 찾은 창(번호 없음)은 열 폭(왼쪽·오른쪽 변)이 같고 줄이 겹치는 엔진 창의 번호를
    빌린다: 이 규칙은 옆 변 자리만 본다."""
    n = screen.numbers.get(rect)
    if n is not None:
        return n
    for w, m in screen.numbers.items():
        if m is not None and (w[1], w[3]) == (rect[1], rect[3]) and w[0] <= rect[2] and rect[0] <= w[2]:
            return m
    return None


def check(screen):
    out = []
    rects = screen.rects
    for i, a in enumerate(rects):
        for b in rects[i + 1:]:
            if not overlap(a, b):
                continue
            top, low = (a, b) if a in screen.tops[b] else (b, a)
            na, nb = number(screen, a), number(screen, b)
            moved = screen.ref.moved
            for k, side in ((1, '왼쪽'), (3, '오른쪽')):
                if (na is not None and nb is not None and moved is not None
                        and na not in moved[side] and nb not in moved[side]):
                    continue
                if abs(top[k] - low[k]) == 1:
                    out.append((top[0], top[k], f'창 {top} 과 {low} 의 {side} 변이 한 칸 어긋남'))
    return out
