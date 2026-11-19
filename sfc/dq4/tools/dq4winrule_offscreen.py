"""UI 깨짐 규칙 1c 화면 밖: 창이 화면에 보이는 줄(세로 스크롤 기준 224점) 밖으로 걸쳤다(dq4winwatch 의 규칙 파일).
걸린 칸은 화면 안쪽 끝 줄의 창 모서리 칸에 적는다(화면 밖 칸은 판정 틀이 거르므로)."""
NAME = '화면 밖'
MODE = 'report'
ALLOW = ()


def check(screen):
    out = []
    for w in screen.rects:
        rows = range(w[0], w[2] + 1)
        seen = [r for r in rows if screen.visible(r)]
        if seen and len(seen) < len(rows):
            r = seen[0] if not screen.visible(w[0]) else seen[-1]
            out.append((r, w[1], f'창 {w} 가 화면 밖으로 {len(rows) - len(seen)}줄'))
    return out
