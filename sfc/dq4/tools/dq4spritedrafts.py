"""DQ5 엔진 크기(16×24)에 맞춘 포팅 인물 정면 시안; sfc/dq4/docs/dq4-sprite-format.md.

dq4sprites.py 의 1차 시안보다 큰 상자(폭 16, 높이 22~23)를 쓰고, 재질마다 윤곽색을 바꾸며 명암을 3단으로 둔다.
정면 정지 자세 한 장씩만 있다. 측면·후면·보행은 정면이 채택된 뒤에 그린다.

실행하면 인물마다 색 수와 평평함 지표(dq4spritecheck.py)를 찍는다.
"""

import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dq4spritecheck import stats  # noqa: E402

WIDTH, HEIGHT = 16, 24

# 1 윤곽·눈, 2·3 살, 4 짙은 갈색(모자·발밑의 두 번째 윤곽), 5·6·7 파랑 3단(7 은 파란 옷의 윤곽과 머리카락)
PALETTES = {
    "torneko": {
        "1": (3, 3, 4), "2": (30, 22, 18), "3": (23, 14, 10), "4": (11, 5, 3),
        "5": (8, 17, 29), "6": (4, 9, 19), "7": (2, 4, 10),
        "8": (18, 10, 4),  # 등짐
        "B": (29, 29, 30),
        "C": (13, 4, 16), "D": (21, 9, 25),  # 보라 모자·소매
    },
    "hero": {
        "1": (3, 3, 4), "2": (30, 22, 18), "3": (23, 14, 10), "4": (11, 5, 3),
        "5": (6, 16, 24), "6": (3, 9, 17), "7": (2, 4, 10),
        "8": (19, 10, 4),  # 장화
        "A": (30, 23, 6), "E": (25, 12, 2),  # 금 투구·방패, 주황 그늘
        "B": (29, 29, 30),
        "G": (12, 22, 14), "H": (5, 12, 8),  # 초록 머리
    },
}

FRONTS = {
    "torneko": """
................
......44D4......
....4DDBDDC4....
...4DDBDDDCCC4..
..4DDDDDCDCCC74.
..4DDDCDCCCCC71.
.16CDCCCCCC7C771
15677C7C777C7661
1563222222333761
1562221221223671
1556231221326651
165B22233222B651
1676677767777761
1877767227777781
18BD13322331CC41
18DDC1556671DC41
13DBDC55B667DC41
18DCC55B5667C741
14DC223B56333C41
147C335B56633741
.17665B5667B7771
.17767676767771.
..176671177671..
..1438841488341.
""",
    "hero": """
.....1G11G1.....
1...1GGHGGH1...1
A1.1GG1AE1HH1.1E
BA11G1AABE1H11EA
AAE11AAEAAE11EEA
1EAAEAB56AEAAEE1
.1EEAEE77EEEAE1.
..1GHGHGGHGHH1..
..1G22222233H1..
..1G22122123H1..
..1HB2123123H1..
...1H222233H1...
.1AAE13231AEE1..
1BAE1556751AAE1.
1B661556661A5AE1
1B651B56671A56E1
1231AABAEE1A66E1
.11155667771EAE1
..15656676771E1.
..16671176671...
..17671176771...
..1884118841....
..1444114441....
................
""",
}

DRAFT_NAMES = tuple(FRONTS)


def rows(name: str) -> list[str]:
    out = [line for line in FRONTS[name].strip("\n").split("\n")]
    if len(out) != HEIGHT or any(len(r) != WIDTH for r in out):
        raise ValueError(f"{name}: matrix must be {WIDTH}x{HEIGHT}")
    unknown = set("".join(out)) - set(PALETTES[name]) - {"."}
    if unknown:
        raise ValueError(f"{name}: colors without palette entry {sorted(unknown)}")
    return out


def front(name: str) -> Image.Image:
    """RGBA 16×24. RGB555 를 8비트로 늘릴 때 아래 3비트를 위 비트로 채운다."""
    palette = PALETTES[name]
    im = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    for y, row in enumerate(rows(name)):
        for x, char in enumerate(row):
            if char != ".":
                im.putpixel((x, y), tuple(v << 3 | v >> 2 for v in palette[char]) + (255,))
    return im


if __name__ == "__main__":
    for name in DRAFT_NAMES:
        r = rows(name)
        used = set("".join(r)) - {"."}
        print(f"{name}: {len(used)} colors, bbox {front(name).getbbox()}, {stats(r)}")
