"""UI 깨짐 규칙 줄 높이·겹침: 한 창 안에서 (1) 같은 화면 줄로 묶인 글자의 띠 윗줄이 다르다(한 줄이 위아래로 어긋남),
(2) 두 줄의 잉크가 위아래로 겹친다. 창 글자(Galmuri9)·메시지 글자만 본다(롬 글자 칸은 칸 단위라 늘 맞음).
dq4winwatch 의 규칙 파일. 글자는 dq4wintext 로 읽는다.
"""
import dq4wintext as wt

NAME = '줄 어긋남'
MODE = 'report'
ALLOW = ()
DRAWN = ('galmuri9', 'message', 'galmuri11', 'galmuri7')
# 이름 렌더러(게임 안 WnKorean, 모험의 서 목록 NeListBand)가 그리는 칸. 이름 렌더러는 글리프 1행을 칸의 0 선에, 창 글자
# 그림(WnText)은 9줄 Galmuri9 의 맨 윗줄을 위 칸 7선에 합성해 1행을 −1 선에 둔다. 같은 줄에 둘이 섞이면 이름이 1점
# 아래인 것이 공통 꼴이라, 이름 렌더러 칸의 글자는 윗줄을 1 빼고 견준다(2점 넘게 갈리면 그대로 걸림).
# 모험의 서 목록(NeListBand, 메뉴 칸 2D0~2E7)이 든 줄에서는 창 글자 그림이 180~ 칸을 쓰므로(장소 이름) 메뉴 칸만 이름이다
GAME_NAMES = range(0x180, 0x1D0)
MENU_NAMES = range(0x2D0, 0x2E8)


def tile_of(screen, w, x, top):
    r, c = wt.cell_of(w, x + 1, top + 4)
    return screen.word(r, c) & 0x3FF


def check(screen):
    got = wt.lines(screen)
    if not got:
        return []
    out = []
    for w, lines in got.items():
        boxes = []
        for line in lines:
            # 기호·못 읽음은 띠가 흔들려 읽혀 빼고, 한글·영숫자가 둘 이상인 줄만 본다
            drawn = [it for it in wt.word_chars(line) if it[3] in DRAWN]
            if len(drawn) < 2:
                continue
            tiles = [tile_of(screen, w, x, top) for x, _, _, _, top in drawn]
            names = MENU_NAMES if any(t in MENU_NAMES for t in tiles) else GAME_NAMES
            tops = {(k, top - (t in names)) for (_, _, _, k, top), t in zip(drawn, tiles)}
            fonts = {k for k, _ in tops}
            for k in fonts:
                ys = sorted({top for kk, top in tops if kk == k})
                if len(ys) > 1:
                    r, c = wt.cell_of(w, line.x, line.y)
                    out.append((r, c, f'창 {w} 「{line.text}」 의 글자 윗줄이 {ys} 로 갈림'))
            h = max(wt.band_height(k) for k in fonts)
            top = min(t for _, t in tops)
            boxes.append((top, top + h, min(x for x, *_ in drawn), max(x + wd for x, _, wd, *_ in drawn), line))
        for i, a in enumerate(boxes):
            for b in boxes[i + 1:]:
                if a[0] < b[1] and b[0] < a[1] and a[2] < b[3] and b[2] < a[3] and a[4] is not b[4]:
                    r, c = wt.cell_of(w, b[4].x, b[4].y)
                    out.append((r, c, f'창 {w} 「{a[4].text}」 와 「{b[4].text}」 의 줄이 위아래로 겹침'))
    return out
