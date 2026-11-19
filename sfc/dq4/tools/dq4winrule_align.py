"""UI 깨짐 규칙 1d 변 어긋남: 겹친 두 창의 같은 쪽 옆 변(왼쪽·오른쪽)이 정확히 한 칸 어긋났다(dq4winwatch 의 규칙 파일).

계기: 가게 동료 창 3A 를 이름 다섯 칸에 맞춰 넓히자, 뒤에 깔린 메시지 창(원본 DQ5 는 둘 다 열 2~29)이 3A 아래로 한 칸
좁게 삐져 나왔다. 두 창이 모두 엔진 창이고 둘 다 원본 DQ5 와 그 변 자리가 같은 창이면(Ref.moved 밖) 원본에도 있는
어긋남이라 걸지 않는다. 걸린 칸은 위 창의 그 변 모서리 칸이다.
위·아래 변은 보지 않는다: DQ5 는 도구 목록 창(아래 변 26줄)을 메시지 창(27줄) 위에 띄우는 등 한 줄 차이가 흔하다.
"""
NAME = '변 어긋남'
MODE = 'report'
ALLOW = ()


def overlap(a, b):
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


def check(screen):
    out = []
    rects = screen.rects
    for i, a in enumerate(rects):
        for b in rects[i + 1:]:
            if not overlap(a, b):
                continue
            top, low = (a, b) if a in screen.tops[b] else (b, a)
            na, nb = screen.numbers.get(a), screen.numbers.get(b)
            moved = screen.ref.moved
            for k, side in ((1, '왼쪽'), (3, '오른쪽')):
                if (na is not None and nb is not None and moved is not None
                        and na not in moved[side] and nb not in moved[side]):
                    continue
                if abs(top[k] - low[k]) == 1:
                    out.append((top[0], top[k], f'창 {top} 과 {low} 의 {side} 변이 한 칸 어긋남'))
    return out
