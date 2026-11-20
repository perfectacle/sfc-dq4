"""UI 깨짐 규칙 커서 사라짐: 맨 위 엔진 창 안에 고르기 손가락 ▶ 가 보였는데, 창 쌓기가 그대로인 동안 어느 살아 있는 엔진
창에도 ▶ 가 LOST 프레임 넘게 나오지 않는다. dq4winwatch 의 장면 전체 규칙(check_run).

▶ 는 16프레임 켜지고 16프레임 꺼지며 깜박인다(창 검사·무작위 장면 기록에서 ▶ 사이 없음 구간 16프레임이 91번, 실측).
창이 닫히거나 위에 새 창이 뜨면 쌓기가 바뀌어 셈을 새로 한다. 회색 ▶ 로 남는 아래 창은 맨 위가 아니라 보지 않는다.
처음부터 ▶ 가 나오지 않는 고르는 창은 보지 않는다(창 레코드의 줄 머리로 고르는 창을 가려야 함).
"""
import dq4winwatch as ww
import dq4winrule_cursor as cur

NAME = '커서 사라짐'
MODE = 'fail'
ALLOW = ()
LOST = 24           # 깜박임 꺼짐 16프레임 + 여유


def inside(w, r, c):
    return w[0] < r < w[2] and w[1] < c < w[3]


def check_run(run):
    rom = getattr(run.ref, 'rom', None)
    if not rom:
        return []
    rec = run.record
    glyph = cur.cursor_glyph(rom)
    timeline = ww.stacks(rec.draws)
    cache, out, t = {}, [], 0
    key, seen, gone, told = None, False, None, False
    events = rec.events
    for k, (f, i) in enumerate(events):
        nxt = events[k + 1][0] if k + 1 < len(events) else None
        while t < len(timeline) and timeline[t][0] < f:
            t += 1
        engine = tuple(timeline[t - 1][1]) if t else ()
        numbers = timeline[t - 1][2] if t else {}
        state = None
        if i in rec.shots and engine:
            ck = (i, engine)
            if ck not in cache:
                sc = ww.Screen(rec.shots[i], run.ref, run.scene, list(engine), numbers)
                live = sc.engine_rects
                top = live[-1] if live else None
                # 맨 위 창에서 ▶ 가 빠져도 다른 살아 있는 창에 ▶ 가 있으면 고르기가 그 창으로 옮겨 간 것이다(B 로 한 단계
                # 돌아가면 목록 창은 남은 채 아래 「누구」 창이 다시 고른다)
                marks = [(r, c) for r in range(32) for c in range(32)
                         if sc.visible(r) and cur.is_cursor(sc, r, c, glyph) and not cur.is_arrow(sc, r, c)]
                on_top = top is not None and any(inside(top, r, c) for r, c in marks)
                anywhere = any(inside(w, r, c) for w in live for r, c in marks)
                cache[ck] = (top, on_top, anywhere)
            state = cache[ck]
        new = (engine, state[0] if state else None)
        if new != key:
            key, seen, gone, told = new, False, None, False
        if state is None or state[0] is None:
            continue
        if state[1]:
            seen = True
        if state[2]:
            gone = None
            continue
        if seen and gone is None:
            gone = f
        if gone is not None and not told and nxt is not None and nxt - gone > LOST:
            out.append((gone, f'창 {state[0]} 에서 ▶ 가 {nxt - gone}프레임 넘게 보이지 않음'))
            told = True
    return out
