"""UI 깨짐 규칙 커서: 고르기 손가락 ▶(BG3 칸 07C, 그림이 롬 1bpp 글자 07C 와 같은 칸)가 (1) 창 테두리 칸에 있다(어느 창에도
들지 않는 ▶ 는 틀의 「창 밖」 이 잡는다), (2) 글자 위에 섰다 — 바로 오른쪽 칸이 그려 넣은 칸(롬 글자 칸 01~8A 밖)이고 왼쪽 첫 열에 잉크가 있다(한글은 앞 1점을
비우고 그리므로, 첫 열 잉크는 ▶ 가 앞 글자를 덮어 잘린 것. 「▶ㅂㅂㅂ」 꼴), (3) 가리키는 줄이 비었다 — 오른쪽 칸들(같은 칸 줄과 위 한 줄)에 창 끝까지 잉크가
없다(그 줄이 위 창에 일부라도 가려지면 보지 않는다), (4) 한 창 안쪽에 ▶ 가 둘 이상이다. dq4winwatch 의 규칙 파일.
위 창에 가려진 칸은 보지 않는다.

잉크는 창 바탕색(창 안쪽 칸에서 가장 많은 색)과 투명(0)이 아닌 점이다.
"""
from collections import Counter

from dq4winwatch import Known

NAME = '커서'
MODE = 'fail'
ALLOW = ()
KNOWN = (
    Known('*/equip-ch3', frozenset({(5, 19)}), 7,
          '창 (2,18)-(12,29) 의 4·5줄 글자 칸이 한 칸 밀려 오른쪽 테두리를 덮는 동안(프레임 789~) ▶ 오른쪽 칸 첫 열에 '
          '밀린 글자 잉크가 든다. 창 글자 칸 넘침(창 검사 equip-ch3 눈금)과 같은 때의 화면, 그 넘침을 고치면 이 눈금을 지운다'),
)
CURSOR = 0x7C
ROM_FONT = 0x04E528
# 롬 1bpp 글자 칸. 원본 DQ5 가나는 첫 열부터 잉크가 있어 덮음 검사에서 뺀다
ROM_TILES = range(0x01, 0x8B)


def hidden(screen, w, r, c):
    """위 창에 가려진 칸인가. 엔진이 같은 창을 두 번 그려 사각형이 겹쳐 들면 자기 자신은 위 창으로 치지 않는다."""
    return any(v != w and v[0] <= r <= v[2] and v[1] <= c <= v[3] for v in screen.tops.get(w, ()))


def lorom(addr):
    return ((addr >> 16) & 0x7F) * 0x8000 + (addr & 0x7FFF)


def cursor_glyph(rom):
    o = lorom(ROM_FONT) + (CURSOR - 1) * 8
    return [[(b >> (7 - x)) & 1 for x in range(8)] for b in rom[o:o + 8]]


def is_cursor(screen, r, c, glyph):
    w = screen.word(r, c)
    if w & 0x3FF != CURSOR:
        return False
    px = screen.shown(r, c)
    if px is None:
        return False
    bg = Counter(v for row in px for v in row).most_common(1)[0][0]
    return [[int(v != bg and v != 0) for v in row] for row in px] == glyph


def background(screen, w):
    r1, c1, r2, c2 = w
    count = Counter()
    for r in range(r1 + 1, r2):
        for c in range(c1 + 1, c2):
            px = screen.shown(r, c)
            if px is not None and not hidden(screen, w, r, c):
                count.update(v for row in px for v in row)
    return count.most_common(1)[0][0] if count else None


def ink(px, bg):
    return [[v is not None and v != bg and v != 0 for v in row] for row in px]


def check(screen):
    rom = getattr(screen.ref, 'rom', None)
    if not rom:
        return []
    glyph = cursor_glyph(rom)
    out = []
    cursors = [(r, c) for r in range(32) for c in range(32) if screen.visible(r) and is_cursor(screen, r, c, glyph)]
    per_window = Counter()
    rects = list(dict.fromkeys(screen.rects))
    for r, c in cursors:
        homes = [w for w in rects if w[0] < r < w[2] and w[1] < c < w[3] and not hidden(screen, w, r, c)]
        if not homes:
            edge = [w for w in rects if w[0] <= r <= w[2] and w[1] <= c <= w[3] and not hidden(screen, w, r, c)]
            if edge:
                out.append((r, c, f'▶ 가 창 {edge[-1]} 테두리'))
            continue
        w = homes[-1]
        per_window[w] += 1
        bg = background(screen, w)
        right = screen.shown(r, c + 1) if c + 1 < w[3] else None
        drawn = not ROM_TILES[0] <= screen.word(r, c + 1) & 0x3FF <= ROM_TILES[-1]
        if right is not None and drawn and not hidden(screen, w, r, c + 1) and any(ink(right, bg)[y][0] for y in range(8)):
            out.append((r, c, f'창 {w} 의 ▶ 오른쪽 칸 첫 열에 잉크(▶ 가 글자를 덮음)'))
            continue
        filled = covered = False
        for rr in (r - 1, r):
            for cc in range(c + 1, w[3]):
                if rr <= w[0]:
                    continue
                if hidden(screen, w, rr, cc):
                    covered = True
                    continue
                px = screen.shown(rr, cc)
                if px is not None and any(any(row) for row in ink(px, bg)):
                    filled = True
                    break
            if filled:
                break
        # 가리키는 줄이 위 창에 일부라도 가려졌거나 오른쪽에 글자 한 자 들 칸도 없으면 비었는지 알 수 없다.
        if not filled and not covered and w[3] - c > 2:
            out.append((r, c, f'창 {w} 의 ▶ 가 빈 줄을 가리킴'))
    for w, n in per_window.items():
        if n > 1:
            r, c = next(p for p in cursors if w[0] < p[0] < w[2] and w[1] < p[1] < w[3])
            out.append((r, c, f'창 {w} 안에 ▶ 가 {n}개'))
    return out
