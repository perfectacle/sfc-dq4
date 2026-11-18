"""장 제목 상자·끝 상자 화면 판정(보고만). 화면(RGB 256 × 224)에서 금테 상자를 찾아 깨짐을 가린다.

형식은 sfc/dq4/docs/dq4-chapter1-format.md 「장 제목 상자 판정」. 상자 너비를 고정값으로 두지 않고 화면에서 잰다(제목 길이대로
상자를 넓히는 고침이 와도 같은 판정).

  상자 없음    금색(dq4chapterbox.GOLD) 점이 없다
  화면 밖      상자나 부제 글자가 화면 끝 줄·열에 닿는다(잘림)
  테두리       상자 네 변 가운데 금색 점이 없는 열·줄이 있다(끊김). 변마다 바깥 테두리 타일 한 칸(8점) 안을 본다
  글자 침범    제목 글자(흰색)가 테두리 타일 칸(바깥 8점 띠)에 들어갔다 — 상자 안 너비를 넘었다

  uv run --locked python sfc/dq4/tools/dq4boxjudge.py preview                 # 미리보기 판정(게임 장면 아님)
  uv run --locked python sfc/dq4/tools/dq4boxjudge.py shots 장면폴더…           # 찍어 둔 화면 판정
게임 장면은 dq4boxplay.py 가 띄워 이 판정(judge)에 돌린다.
미리보기 판정은 빌드가 넣는 제목(dq4chapterbox.GAME_SCENES)과 명칭표(nds/dq4/tables/adopt.tsv)의 뒤 장 제목을 같은
그리기(dq4chapterbox.box_pixels)로 그려 같은 판정을 돌린다. 그리기가 상자 안 너비를 넘는다고 거부하면 그것도 걸림이다.
"""
import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ADOPT = ROOT / 'nds' / 'dq4' / 'tables' / 'adopt.tsv'
FC_ROM = ROOT / 'rom' / 'dq4.nes'
SCREEN_W, SCREEN_H = 256, 224
EDGE = 8                       # 테두리 타일 한 칸
# 명칭표의 장 제목 줄(「지명·장 제목」 표 번호 100~): 100 이 1장
TITLE_TABLE, FIRST_TITLE = '지명·장 제목', 100


def _colors():
    import dq4chapterbox as cb
    return cb.GOLD, cb.WHITE


def judge(im):
    """[(종류, 설명)]. im 은 PIL RGB 화면(256 × 224)."""
    gold, white = _colors()
    px, (w, h) = im.load(), im.size
    golds = [(x, y) for y in range(h) for x in range(w) if px[x, y] == gold]
    if not golds:
        return [('상자 없음', '금색 점 없음')]
    left, right = min(x for x, _ in golds), max(x for x, _ in golds)
    top, bottom = min(y for _, y in golds), max(y for _, y in golds)
    out = []
    if left == 0 or top == 0 or right == w - 1 or bottom == h - 1:
        out.append(('화면 밖', f'상자 ({left},{top})~({right},{bottom}) 이 화면 끝에 닿음'))
    gset = set(golds)
    # 변은 모서리 타일 칸을 뺀 곧은 구간을 보고(모서리는 둥글어 바깥 줄에 금색이 없는 점이 있다), 모서리 칸은 금색이 있는지만 본다
    runs = {'위': ((x, range(top, top + EDGE)) for x in range(left + EDGE, right - EDGE + 1)),
            '아래': ((x, range(bottom - EDGE + 1, bottom + 1)) for x in range(left + EDGE, right - EDGE + 1)),
            '왼쪽': ((y, range(left, left + EDGE)) for y in range(top + EDGE, bottom - EDGE + 1)),
            '오른쪽': ((y, range(right - EDGE + 1, right + 1)) for y in range(top + EDGE, bottom - EDGE + 1))}
    for side, lines in runs.items():
        gaps = [at for at, span in lines
                if not any(((at, v) if side in ('위', '아래') else (v, at)) in gset for v in span)]
        if gaps:
            out.append(('테두리', f'{side} 변 금색 끊김 {len(gaps)}곳(첫 {gaps[0]})'))
    for name, (cx, cy) in (('왼쪽 위', (left, top)), ('오른쪽 위', (right - EDGE + 1, top)),
                           ('왼쪽 아래', (left, bottom - EDGE + 1)), ('오른쪽 아래', (right - EDGE + 1, bottom - EDGE + 1))):
        if not any((cx + i, cy + j) in gset for i in range(EDGE) for j in range(EDGE)):
            out.append(('테두리', f'{name} 모서리 금색 없음'))
    inner = (left + EDGE, top + EDGE, right - EDGE, bottom - EDGE)
    for y in range(top, bottom + 1):
        for x in range(left, right + 1):
            if px[x, y] == white and not (inner[0] <= x <= inner[2] and inner[1] <= y <= inner[3]):
                out.append(('글자 침범', f'흰 점 ({x},{y}) 이 테두리 칸 안'))
                break
        else:
            continue
        break
    # 부제(상자 아래 흰 글자)는 화면 끝에 닿으면 잘린 것이다
    below = [(x, y) for y in range(bottom + 1, h) for x in range(w) if px[x, y] == white]
    if below and (min(x for x, _ in below) == 0 or max(x for x, _ in below) == w - 1 or max(y for _, y in below) == h - 1):
        out.append(('화면 밖', '부제 글자가 화면 끝에 닿음'))
    return out


def preview_image(nes, font, title, subtitle=None):
    """dq4chapterbox.preview 와 같은 자리·색으로 그린 화면(PIL)."""
    from PIL import Image
    import dq4chapterbox as cb
    img, pal = cb.box_pixels(nes, font, title, subtitle)
    colors = {cb.PAL_BORDER: [(0, 0, 0), cb.GOLD, cb.BLUE, cb.BLUE], cb.PAL_TEXT: [(0, 0, 0), cb.WHITE, cb.BLUE, cb.WHITE]}
    im = Image.new('RGB', (SCREEN_W, SCREEN_H))
    px = im.load()
    for y, row in enumerate(img):
        for x, v in enumerate(row):
            sx, sy = cb.BOX_COL * 8 + x, cb.BOX_ROW * 8 + y
            if 0 <= sx < SCREEN_W and 0 <= sy < SCREEN_H:
                px[sx, sy] = colors[pal[y // 8][x // 8]][v]
    return im


def later_titles():
    """명칭표에서 빌드가 아직 쓰지 않는 장 제목 [(이름, 제목)]. 빌드 제목(GAME_SCENES)과 같은 꼴로: 전각 숫자를 반각으로,
    「장」 뒤 빈칸 하나를 둘로(빌드 제목과 견주는 시험이 이 바꿈을 지킨다)."""
    import dq4chapterbox as cb
    built = {s.title for s in cb.GAME_SCENES}
    out = []
    for line in ADOPT.read_text(encoding='utf-8').splitlines():
        cols = line.split('\t')
        if len(cols) > 3 and cols[0] == TITLE_TABLE and cols[1].isdigit() and int(cols[1]) > FIRST_TITLE:
            title = form(cols[3])
            if title not in built:
                out.append((f'chapter{int(cols[1]) - FIRST_TITLE + 1}', title))
    return out


def form(korean):
    """명칭표 제목 → 빌드 제목 꼴."""
    text = korean.translate({0xFF10 + d: ord('0') + d for d in range(10)})
    return text.replace('장 ', '장  ', 1)


def preview_cases():
    """[(이름, 제목, 부제)]: 빌드가 넣는 상자 모두와 명칭표의 뒤 장 제목(미리보기 판정)."""
    import dq4chapterbox as cb
    cases = [(s.name, s.title, s.subtitle) for s in cb.GAME_SCENES]
    cases += [(name, title, None) for name, title in later_titles()]
    cases += [(name + '-end', title, cb.ENDING.subtitle) for name, title in later_titles()]
    return cases


def run_preview(nes, font):
    found = []
    for name, title, subtitle in preview_cases():
        try:
            im = preview_image(nes, font, title, subtitle)
        except ValueError as e:
            found.append((name, '글자 침범', f'그리기가 거부: {e}'))
            continue
        found += [(name, kind, text) for kind, text in judge(im)]
    return found


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('preview', help='미리보기 판정(게임 장면 아님)')
    p.add_argument('--dq4', default=str(FC_ROM))
    s = sub.add_parser('shots', help='게임 화면 판정: 폴더마다 상자가 다 밝은 화면(금색이 있는 것)만')
    s.add_argument('folders', nargs='+', type=Path)
    args = ap.parse_args()
    if args.cmd == 'preview':
        import dq4menupatch
        found = run_preview(Path(args.dq4).read_bytes(), dq4menupatch.Font('galmuri11'))
        label = '미리보기 판정'
    else:
        from PIL import Image
        found, seen = [], 0
        for folder in args.folders:
            for shot in sorted(folder.glob('*.png')):
                problems = judge(Image.open(shot).convert('RGB').crop((0, 0, SCREEN_W, SCREEN_H)))
                if problems and problems[0][0] == '상자 없음':
                    continue
                seen += 1
                found += [(f'{folder.name}/{shot.name}', kind, text) for kind, text in problems]
        label = f'게임 화면 판정(상자 화면 {seen}장)'
    for name, kind, text in found:
        print(f'{name} {kind}: {text}')
    print(f'{label}: 걸림 {len(found)}건')
    return 0                    # 보고만


if __name__ == '__main__':
    sys.exit(main())
