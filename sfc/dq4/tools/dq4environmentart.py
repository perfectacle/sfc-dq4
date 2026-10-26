"""Hand-authored DQ4 environment pixels, indexed for SFC 4bpp backgrounds.

NDS DQ4 supplies architectural references; no source image pixels are read.
"""

import random

from PIL import Image, ImageDraw


def _rgb(value):
    return tuple(((int(value[n : n + 2], 16) >> 3) << 3) | (int(value[n : n + 2], 16) >> 5) for n in (0, 2, 4))


_BANKS = (
    ("18202a",) * 16,
    ("18202a", "102900", "054600", "007200", "0ba100", "3fb800", "20e30e", "2dff39", "9cff8c", "292121", "947321", "f7f7d6", "f7f7d6", "ff5a9c", "ffffef", "ffd629"),
    ("18202a", "292121", "40342f", "5a4a41", "7b6b62", "9d8e84", "beb4a5", "d8d2bf", "efefd6", "101010", "57072e", "b3177f", "292121", "6d2921", "b5604f", "f7c69c"),
    ("18202a", "101010", "474740", "636860", "7c8078", "9c9c92", "c5c5b4", "efefd6", "57072e", "b3177f", "de4fa9", "102900", "292121", "634200", "c69429", "f7f7d6"),
    ("18202a", "292121", "3e2805", "5a3b00", "7f5e13", "a98124", "cda23c", "e2cd7a", "f7f7d6", "101010", "7c8078", "efefd6", "102900", "b3177f", "57072e", "de4fa9"),
    ("18202a", "000000", "292121", "52524a", "461b15", "64231b", "4a4200", "846b00", "81362e", "9f4d45", "c16953", "df906d", "f7c69c", "947321", "f7f7d6", "efefd6"),
    ("18202a", "000000", "292121", "52524a", "57072e", "850054", "634a00", "c69429", "b3177f", "ffde00", "de4fa9", "ffa5de", "947321", "f7f7d6", "efefd6", "00298c"),
    ("18202a", "00104a", "002581", "0024d9", "0042ff", "0073ff", "1aa2ff", "9ce7ff", "102900", "054600", "0ba100", "2dff39", "9cff8c", "102900", "25ac00", "9cff8c"),
)
# DQ5 maps keep object colours at fixed slots: line 6 = 1·2·3·6·7·9 (doors), line 5 = 1·2·3·6·7
# (gates), shared by the common door tiles. Drawing code keeps its old colour numbers for these
# banks; _REMAP moves them around the reserved slots (two wood shades merge into DQ5's).
_REMAP = {
    5: (0, 2, 4, 5, 8, 9, 10, 11, 12, 2, 13, 14, 1, 3, 3, 15),
    6: (0, 2, 4, 5, 8, 10, 11, 2, 6, 12, 7, 13, 14, 1, 14, 15),
}
# Unused slots of the object banks 2-4 repeat the carpet and red-paving colours so that the
# transparent background of furniture keeps the floor colour (map compositing picks the
# nearest colour inside the object's bank).
PALETTE = tuple(_rgb(color) for bank in _BANKS for color in bank)
_FLAT_PALETTE = [channel for rgb in PALETTE for channel in rgb] + [0] * 384
# Colours DQ5's common door tiles expect; palette variants keep them.
_RESERVED = {(5, i) for i in (1, 2, 3, 6, 7)} | {(6, i) for i in (1, 2, 3, 6, 7, 9)}


# The demon castles turn the grey stone ramp (bank 3, colours 1-7) purple.
_PURPLE = ("100818", "2e1850", "432a78", "5a3c9c", "7656be", "a08ade", "d8ceff")


def palette_variant(kind):
    """Flat 768-entry palette. "dim" follows FC DQ4's darker set for アッテムト (each colour one
    NES brightness step down, e.g. 15→07, 1a→0a, 27→17); "purple" recolours the grey stone."""
    if kind == "normal":
        return list(_FLAT_PALETTE)
    if kind == "purple":
        out = list(_FLAT_PALETTE)
        for i, value in enumerate(_PURPLE, 1):
            out[(3 * 16 + i) * 3:(3 * 16 + i) * 3 + 3] = _rgb(value)
        return out
    if kind != "dim":
        raise ValueError(kind)
    out = []
    for index, rgb in enumerate(PALETTE):
        if (index >> 4, index & 15) in _RESERVED or not index & 15:
            out += list(rgb)
        else:
            out += [(int(c * 0.6) >> 3) << 3 | int(c * 0.6) >> 5 for c in rgb]
    return out + [0] * 384
_REF = {
    "castle": "nds/dq4/map/tex/haout.png",
    "town": "nds/dq4/map/tex/maout.png",
    "interior": "nds/dq4/map/tex/caf1.png",
}


class _Canvas:
    def __init__(self, bank, size=(16, 16), fill=0):
        self.bank = bank
        self.image = Image.new("P", size, self.c(fill))
        self.image.putpalette(_FLAT_PALETTE)
        self.image.info["transparency"] = 0
        self.draw = ImageDraw.Draw(self.image)

    def c(self, color):
        if not color:
            return 0
        return self.bank * 16 + (_REMAP[self.bank][color] if self.bank in _REMAP else color)

    def rect(self, box, color):
        self.draw.rectangle(box, fill=self.c(color))

    def line(self, points, color, width=1):
        self.draw.line(points, fill=self.c(color), width=width)

    def poly(self, points, color):
        self.draw.polygon(points, fill=self.c(color))

    def point(self, xy, color):
        self.draw.point(xy, fill=self.c(color))

    def rows(self, rows, at=(0, 0)):
        for y, row in enumerate(rows):
            for x, char in enumerate(row):
                if char != ".":
                    self.point((at[0] + x, at[1] + y), int(char, 16))


def _finish(canvas, role, reference="castle"):
    canvas.image.info.update(bank=canvas.bank, role=role, reference=_REF[reference])
    return canvas.image


def _stone_wall(edge=None):
    """DQ5 walls: speckled bricks under a cream cap; side walls show only the cap's edge."""
    c = _Canvas(2, fill=6)
    rng = random.Random(11)
    top = 6 if edge == "top" else 0
    for y in range(top, 16):
        row, yy = divmod(y - top, 4)
        for x in range(16):
            xx = (x + (4 if row & 1 else 0)) % 8
            if yy == 3 or xx == 7:
                color = 6
            elif yy == 0:
                color = 5 if xx < 6 else 4
            else:
                color = 3 if rng.random() < 0.28 else 4
            c.point((x, y), color)
    if edge == "top":
        for y, color in enumerate((8, 8, 7, 7, 6, 1)):
            c.line((0, y, 15, y), color)
        for x in (7, 15):
            c.point((x, 1), 7)
            c.point((x, 2), 6)
    elif edge in ("left", "right"):
        rim = (1, 6, 8, 8, 7, 6) if edge == "left" else (6, 7, 8, 8, 6, 1)
        x0 = 0 if edge == "left" else 10
        for i, color in enumerate(rim):
            c.line((x0 + i, 0, x0 + i, 15), color)
        for y in (7, 15):
            c.line((x0 + 1, y, x0 + 4, y), 6)
    return _finish(c, "석벽" + (f" {edge}" if edge else ""))


def _stone_floor():
    c = _Canvas(3, fill=3)
    c.rows((
        "5555553555555553", "5666553566666653", "5655553555555653", "5555553555555553",
        "5555553555555553", "5555553555555553", "4444443444444443", "3333333333333333",
        "5553555555553555", "5653566666653566", "5553555555653555", "5553555555553555",
        "5553555555553555", "5553555555553555", "4443444444443444", "3333333333333333",
    ))
    return _finish(c, "회청색 판석")


def _cobble():
    """DQ5 town roads are a basket weave of tan bricks, not loose stones."""
    c = _Canvas(4, fill=7)
    for by in (0, 8):
        for bx in (0, 8):
            vertical = (bx + by) // 8 % 2
            for y in range(8):
                for x in range(8):
                    a, b = (x, y) if vertical else (y, x)
                    color = 3 if a in (3, 7) else 5 if a in (0, 4) or b == 7 else 7
                    if color == 7 and (x * 5 + y * 3 + bx + by) % 7 == 0:
                        color = 5
                    c.point((bx + x, by + y), color)
    return _finish(c, "황토 벽돌길", "town")


def _grass():
    c = _Canvas(1, fill=7)
    for x, y in ((2, 2), (10, 0), (13, 6), (6, 10), (0, 13), (12, 14)):
        c.line((x, y + 1, x + 2, y + 1), 3)
        c.point((x + 1, y), 6)
        c.point(((x + 3) % 16, (y + 2) % 16), 5)
    return _finish(c, "잔디", "town")


def _dirt():
    c = _Canvas(4, fill=8)
    rng = random.Random(4)
    for y in range(16):
        for x in range(16):
            if rng.random() < 0.12:
                c.point((x, y), 7 if rng.random() < 0.7 else 6)
    return _finish(c, "모래", "town")


def _stones(c, seed, count, stone, gap, shade, light=None):
    """Tileable rounded stones from a wrapped Voronoi split; the lower edge of each stone is shaded."""
    rng = random.Random(seed)
    sites = [(rng.uniform(0, 16), rng.uniform(0, 16)) for _ in range(count)]

    def border(x, y):
        d = sorted(min((x - sx - ox) ** 2 + (y - sy - oy) ** 2 for ox in (-16, 0, 16) for oy in (-16, 0, 16))
                   for sx, sy in sites)
        return d[1] ** 0.5 - d[0] ** 0.5

    for y in range(16):
        for x in range(16):
            if border(x + 0.5, y + 0.5) < 1.1:
                c.point((x, y), gap)
            elif border(x + 0.5, y + 1.5) < 1.1 or border(x + 1.5, y + 0.5) < 1.1:
                c.point((x, y), shade)
            elif light and (border(x + 0.5, y - 0.5) < 1.1 or border(x - 0.5, y + 0.5) < 1.1):
                c.point((x, y), light)
            else:
                c.point((x, y), stone)


def _carpet():
    c = _Canvas(6)
    _stones(c, 21, 6, 4, 2, 1)
    return _finish(c, "자주색 카펫", "interior")


def _red_paving():
    c = _Canvas(6)
    _stones(c, 8, 7, 4, 2, 1, 5)
    return _finish(c, "붉은 돌 포장", "castle")


def _wood_floor():
    c = _Canvas(4, fill=2)
    for y in range(0, 16, 4):
        c.rect((0, y, 15, y + 2), 4)
        c.line((0, y, 15, y), 6)
        c.line((1, y + 2, 15, y + 2), 3)
        x = 4 if y % 8 else 12
        c.line((x, y, x, y + 2), 2)
        c.line((x + 2, y + 1, x + 5, y + 1), 5)
    return _finish(c, "나무 바닥", "interior")


def _wood_wall():
    c = _Canvas(4, fill=3)
    for x in range(0, 16, 4):
        c.rect((x, 0, x + 2, 15), 5)
        c.line((x, 0, x, 15), 7)
        c.line((x + 2, 1, x + 2, 15), 4)
        c.line((x + 1, 5 + x % 3, x + 1, 10 + x % 3), 6)
    c.rect((0, 0, 15, 2), 3)
    c.line((0, 0, 15, 0), 6)
    c.rect((0, 13, 15, 15), 2)
    c.line((0, 13, 15, 13), 5)
    c.line((1, 3, 13, 12), 2, 2)
    c.line((2, 3, 14, 12), 6)
    return _finish(c, "목조 가새 벽", "town")


def _roof(kind):
    bank = {"red": 5, "straw": 4, "slate": 3}[kind]
    c = _Canvas(bank, fill=2)
    if kind == "straw":
        for x in range(16):
            c.line((x, 0, x, 15), (4, 6, 5, 7, 4, 5, 6, 5)[x % 8])
        for x, y, length in ((1, 3, 3), (6, 6, 3), (11, 1, 2), (14, 10, 4), (4, 12, 3), (9, 12, 2)):
            c.line((x, y, x, y + length), 3)
        c.line((0, 7, 15, 7), 4)
        c.line((0, 8, 15, 8), 6)
        c.line((0, 15, 15, 15), 3)
    else:
        for y in range(-4, 16, 4):
            for x in range(-4 if y % 8 else 0, 16, 8):
                c.poly(((x, y), (x + 6, y), (x + 6, y + 2), (x + 5, y + 3), (x + 1, y + 3), (x, y + 2)), 4)
                c.line((x + 1, y, x + 5, y), 6)
                c.line((x + 1, y + 1, x + 4, y + 1), 5)
                c.line((x + 1, y + 3, x + 5, y + 3), 3)
                c.point((x + 6, y + 1), 3)
    return _finish(c, {"red": "적갈색 둥근 기와", "straw": "짚지붕", "slate": "회청색 기와"}[kind], "town" if kind == "straw" else "castle")


def _ridge(kind):
    c = _Canvas({"red": 5, "straw": 4, "slate": 3}[kind])
    c.rect((0, 5, 15, 12), 3)
    c.rect((0, 6, 15, 10), 5)
    c.line((0, 5, 15, 5), 7)
    c.line((0, 7, 15, 7), 6)
    for x in (3, 11):
        c.line((x, 5, x, 11), 4)
        c.line((x + 1, 5, x + 1, 9), 6)
    return _finish(c, "용마루", "town" if kind == "straw" else "castle")


def _water(frame):
    c = _Canvas(7, fill=3)
    rng = random.Random(5)
    for y in range(0, 16, 2):
        x = rng.randrange(16) + frame * 2
        length = rng.choice((3, 4, 5))
        for dx in range(length):
            c.point(((x + dx) % 16, y), 6)
        c.point(((x + length) % 16, y + 1), 5)
        c.point(((x - 1) % 16, y + 1), 4)
    return _finish(c, f"물결 {frame}")


def _shore(direction):
    c = _Canvas(7)
    c.image = _water(0)
    c.draw = ImageDraw.Draw(c.image)
    rng = random.Random(9)
    for y in range(16):
        for x in range(16):
            if y < 4:
                c.point((x, y), 10 if rng.random() < 0.1 else 11)
            elif y == 4:
                c.point((x, y), 9)
            elif y == 5 or (y == 6 and (x * 7) % 3 == 0):
                c.point((x, y), 1 if y == 5 else 2)
    if direction != "n":
        turn = {"e": Image.Transpose.ROTATE_270, "s": Image.Transpose.ROTATE_180, "w": Image.Transpose.ROTATE_90}[direction]
        c.image = c.image.transpose(turn)
    return _finish(c, f"물가 {direction}")


def _bridge():
    c = _Canvas(3, fill=3)
    for y in range(0, 16, 4):
        c.rect((3, y, 12, y + 2), 5)
        c.line((4, y, 11, y), 6)
        c.line((7 if y % 8 else 10, y, 7 if y % 8 else 10, y + 2), 4)
    for x in (0, 13):
        c.rect((x, 0, x + 2, 15), 2)
        c.line((x, 0, x, 15), 6)
        c.line((x + 1, 0, x + 1, 15), 4)
        for y in (3, 11):
            c.line((x, y, x + 2, y), 3)
    return _finish(c, "석교")


def _stairs(down=False):
    c = _Canvas(3, fill=1 if down else 3)
    for n in range(5):
        y = 1 + n * 3
        left = n // 2 if down else 0
        c.line((left, y, 15 - left, y), 6 if not down or n < 3 else 4)
        c.line((left, y + 1, 15 - left, y + 1), 4 if not down or n < 3 else 3)
        c.line((left, y + 2, 15 - left, y + 2), 2)
    return _finish(c, "내려가는 계단" if down else "올라가는 계단")


def _door(opened=False):
    c = _Canvas(4, (16, 32))
    c.poly(((1, 31), (1, 10), (3, 6), (6, 4), (9, 4), (12, 6), (14, 10), (14, 31)), 1)
    c.line(((1, 30), (1, 10), (3, 6), (6, 4), (9, 4), (12, 6), (14, 10), (14, 30)), 7)
    c.line(((3, 29), (3, 10), (5, 7), (10, 7), (12, 10), (12, 29)), 3)
    if not opened:
        c.rect((4, 11, 11, 29), 4)
        c.rect((5, 8, 10, 10), 4)
        for x in (4, 7, 10):
            c.line((x, 10, x, 29), 6)
            c.line((x + 2, 10, x + 2, 29), 2)
        for y in (14, 25):
            c.rect((4, y, 11, y + 1), 2)
            c.line((4, y, 11, y), 9)
        c.point((10, 20), 8)
        c.point((10, 21), 3)
    else:
        c.poly(((3, 10), (6, 8), (6, 29), (3, 28)), 4)
        c.line((4, 11, 4, 27), 6)
        c.line((6, 9, 6, 29), 2)
        c.point((5, 20), 8)
    c.line((1, 31, 14, 31), 5)
    return _finish(c, "문 열림" if opened else "문 닫힘", "town")


def _window():
    c = _Canvas(2, (16, 32))
    c.poly(((2, 25), (2, 11), (4, 7), (7, 5), (8, 5), (11, 7), (13, 11), (13, 25)), 3)
    c.line(((2, 25), (2, 11), (4, 7), (7, 5), (8, 5), (11, 7), (13, 11)), 8)
    c.poly(((4, 23), (4, 12), (6, 8), (9, 8), (11, 12), (11, 23)), 1)
    c.line((7, 8, 7, 23), 6)
    c.line((4, 15, 11, 15), 6)
    c.line((5, 12, 5, 14), 9)
    c.line((9, 17, 9, 22), 9)
    c.rect((1, 24, 14, 26), 4)
    c.line((1, 24, 14, 24), 8)
    return _finish(c, "아치창")


def _leaves(c, x, y, shade=0):
    c.rows((
        "....43....", "..45654...", ".5676543..", "456654543.",
        "345434532.", ".34432421.", "..232321..", "...121....",
    ), (x, y))
    if shade:
        for yy in range(y, min(y + 8, c.image.height)):
            for xx in range(x, min(x + 10, c.image.width)):
                value = c.image.getpixel((xx, yy))
                if 18 <= value <= 23:
                    c.image.putpixel((xx, yy), value - shade)


def _tree():
    c = _Canvas(1, (32, 32))
    c.rows(("...999...", "..9aba9..", "..9bba9..", "...aba...", "..9aba9..", ".9a99aa9.", "99.....99"), (12, 24))
    c.poly(((15, 0), (20, 2), (22, 5), (26, 6), (26, 9), (29, 12), (28, 16), (30, 20), (27, 23), (24, 25), (19, 27), (14, 26), (10, 27), (6, 24), (3, 23), (3, 19), (1, 17), (4, 13), (3, 10), (7, 7), (8, 4), (12, 4)), 1)
    for x, y, shade in ((11, 17, 1), (18, 17, 1), (3, 16, 1), (21, 11, 1), (11, 10, 0), (5, 9, 0), (17, 6, 0), (7, 4, 0), (12, 0, 0), (2, 13, 0), (8, 17, 0), (17, 13, 0)):
        _leaves(c, x, y, shade)
    c.point((15, 2), 8)
    c.point((10, 7), 8)
    c.line((7, 15, 8, 15), 7)
    c.line((11, 8, 14, 9), 5)
    c.line((19, 10, 22, 11), 4)
    c.line((8, 18, 10, 17), 5)
    c.point((18, 20), 5)
    return _finish(c, "활엽수", "town")


def _bush():
    c = _Canvas(1)
    c.rows((
        "......333.......", "....345543......", "..345676543.....", ".345676765432...",
        "34556545456543..", "245676345676543.", "235676545676543.", ".234565434565432",
        "123453234543321.", ".1234323454321..", "..12321234321...", "....1121221.....",
        "......999.......", "................", "................", "................",
    ))
    return _finish(c, "관목", "town")


def _flowers():
    c = _Canvas(1)
    for x, y, color in ((3, 4, 14), (10, 7, 13), (5, 12, 14), (13, 2, 13)):
        c.line((x, y + 1, x, min(15, y + 3)), 2)
        c.line((x - 2, y + 3, x + 1, y + 2), 4)
        c.point((x - 1, y), color)
        c.point((x + 1, y), color)
        c.point((x, y - 1), color)
        c.point((x, y + 1), color)
        c.point((x, y), 15)
    return _finish(c, "흰꽃과 분홍꽃", "town")


def _fence():
    c = _Canvas(4)
    for y in (6, 11):
        c.rect((0, y, 15, y + 2), 2)
        c.line((0, y, 15, y), 6)
        c.line((0, y + 1, 15, y + 1), 4)
    for x in (2, 11):
        c.poly(((x, 15), (x, 4), (x + 1, 2), (x + 2, 4), (x + 2, 15)), 3)
        c.line((x, 4, x, 15), 7)
        c.line((x + 1, 5, x + 1, 14), 5)
    return _finish(c, "나무 울타리", "town")


_LETTERS = {
    "I": ("111", "010", "010", "010", "111"),
    "N": ("101", "111", "111", "111", "101"),
}


def _sign(kind):
    c = _Canvas(4)
    c.rect((7, 9, 9, 15), 2)
    c.line((7, 9, 7, 15), 5)
    c.rect((1, 1, 14, 11), 1)
    c.rect((2, 2, 13, 9), 6)
    c.line((2, 2, 13, 2), 8)
    c.line((2, 10, 13, 10), 3)
    if kind == "inn":
        for n, char in enumerate("INN"):
            for y, row in enumerate(_LETTERS[char]):
                for x, pixel in enumerate(row):
                    if pixel == "1":
                        c.point((2 + n * 4 + x, 4 + y), 2)
    elif kind == "church":
        c.rect((3, 3, 12, 9), 12)
        c.line((7, 3, 7, 8), 11)
        c.line((5, 5, 9, 5), 11)
    else:
        c.line((5, 3, 10, 8), 10)
        c.line((6, 3, 11, 8), 11)
        c.line((8, 8, 11, 5), 3)
        c.line((8, 7, 6, 9), 2)
    return _finish(c, f"간판 {kind}", "town")


def _well():
    c = _Canvas(3, (16, 16))
    c.poly(((1, 6), (4, 3), (11, 3), (14, 6), (14, 12), (11, 15), (4, 15), (1, 12)), 2)
    c.poly(((2, 7), (4, 5), (11, 5), (13, 7), (13, 11), (10, 13), (5, 13), (2, 11)), 5)
    c.line((2, 10, 4, 12, 10, 12), 6)
    c.line((4, 13, 4, 14), 3)
    c.line((9, 13, 9, 14), 3)
    c.poly(((1, 5), (4, 2), (11, 2), (14, 5), (14, 8), (11, 11), (4, 11), (1, 8)), 6)
    c.line(((1, 5), (4, 2), (11, 2), (14, 5)), 7)
    c.poly(((4, 5), (6, 4), (10, 4), (12, 6), (10, 8), (5, 8), (3, 6)), 1)
    c.line((5, 8, 10, 8), 3)
    for x, y in ((3, 4), (8, 2), (12, 8), (5, 9)):
        c.point((x, y), 4)
    return _finish(c, "돌우물", "town")


def _barrel():
    c = _Canvas(4)
    c.rows((
        "....222222......", "..2367765322....", ".256443344532...", ".265223322542...",
        ".276544445642...", ".254566655432...", ".29a999999932...", ".235453454532...",
        ".235453454532...", ".235453454532...", ".29a999999932...", ".245453454532...",
        "..2453344532....", "...23344322.....", "....222222......", "................",
    ))
    return _finish(c, "나무통", "town")


def _pot():
    c = _Canvas(4)
    c.rows((
        "................", ".....34443......", "....3677653.....", "....3511153.....",
        ".....34543......", "....4566543.....", "...467765432....", "..36776544322...",
        "..36765444322...", "..35654444322...", "..34544443322...", "...344443322....",
        "....3333322.....", ".....22222......", "................", "................",
    ))
    return _finish(c, "항아리", "town")


def _table():
    c = _Canvas(4, (32, 16))
    c.rect((4, 9, 6, 15), 2)
    c.rect((25, 9, 27, 15), 2)
    c.line((4, 10, 4, 14), 5)
    c.line((25, 10, 25, 14), 5)
    c.rect((2, 3, 29, 11), 2)
    c.rect((3, 2, 28, 9), 5)
    c.line((3, 2, 28, 2), 8)
    c.line((3, 3, 3, 8), 7)
    c.line((3, 9, 28, 9), 3)
    c.line((3, 5, 28, 5), 4)
    c.line((3, 6, 28, 6), 6)
    c.line((6, 3, 12, 3), 6)
    c.line((19, 7, 26, 7), 4)
    return _finish(c, "식탁", "interior")


def _chair():
    c = _Canvas(4)
    c.rows((
        "...2333332......", "...2677762......", "...2644462......", "...2644462......",
        "...2644462......", "...2355532......", "...2344432......", "..256666532.....",
        "..267777642.....", "..256666532.....", "..233333332.....", "...24..242......",
        "...24..242......", "...22..222......", "................", "................",
    ))
    return _finish(c, "의자", "interior")


def _bed():
    c = _Canvas(6, (16, 32))
    c.rect((1, 1, 14, 29), 7)
    c.rect((2, 2, 13, 5), 9)
    c.line((2, 2, 13, 2), 11)
    c.rect((2, 6, 13, 27), 4)
    c.rect((3, 7, 12, 12), 12)
    c.line((3, 12, 12, 12), 14)
    c.rect((3, 14, 12, 26), 3)
    c.line((3, 14, 12, 14), 5)
    c.line((4, 15, 4, 25), 4)
    c.line((11, 15, 11, 25), 2)
    c.line((3, 26, 12, 26), 2)
    for x in (1, 13):
        c.rect((x, 26, x + 1, 31), 8)
        c.line((x, 26, x, 30), 10)
    c.line((2, 28, 13, 28), 10)
    return _finish(c, "침대", "interior")


def _bed_wide():
    """FC places beds as two side-by-side blocks with the headboard on the right."""
    c = _Canvas(6, (32, 16))
    c.rect((1, 4, 4, 14), 7)
    c.line((1, 4, 4, 4), 9)
    c.line((1, 5, 1, 13), 8)
    c.rect((27, 0, 30, 14), 7)
    c.rect((28, 0, 29, 13), 9)
    c.line((27, 0, 30, 0), 11)
    c.line((28, 1, 28, 12), 10)
    c.rect((4, 3, 27, 12), 7)
    c.rect((5, 3, 26, 10), 12)
    c.line((5, 3, 26, 3), 6)
    c.rect((20, 4, 25, 9), 14)
    c.rect((20, 4, 24, 8), 12)
    c.line((20, 4, 24, 4), 6)
    c.rect((5, 3, 18, 10), 4)
    c.line((5, 3, 18, 3), 5)
    c.line((5, 4, 5, 9), 5)
    c.line((8, 5, 15, 5), 5)
    c.line((8, 8, 15, 8), 3)
    c.rect((18, 3, 19, 10), 6)
    c.line((19, 4, 19, 10), 5)
    c.rect((5, 10, 26, 11), 3)
    c.line((5, 11, 26, 11), 2)
    c.rect((4, 12, 27, 13), 8)
    c.line((4, 13, 27, 13), 7)
    for x in (2, 28):
        c.rect((x, 14, x + 1, 15), 7)
    return _finish(c, "가로 침대", "interior")


def _chest(opened=False):
    c = _Canvas(4)
    c.rect((2, 7, 13, 13), 2)
    c.rect((3, 8, 12, 12), 4)
    c.line((3, 13, 12, 13), 1)
    for x in (3, 11):
        c.line((x, 7, x, 12), 7)
        c.line((x + 1, 7, x + 1, 12), 5)
    if opened:
        c.rect((2, 1, 13, 5), 3)
        c.rect((3, 2, 12, 4), 1)
        c.line((2, 1, 13, 1), 6)
        c.rect((3, 6, 12, 8), 1)
    else:
        c.poly(((2, 7), (2, 4), (4, 2), (11, 2), (13, 4), (13, 7)), 4)
        c.line(((2, 4), (4, 2), (11, 2), (13, 4)), 7)
        c.line((3, 5, 12, 5), 6)
        for x in (4, 11):
            c.line((x, 3, x, 7), 7)
        c.line((2, 7, 13, 7), 1)
    c.rect((7, 8, 8, 10), 7)
    c.point((8, 9), 2)
    return _finish(c, "보물상자 열림" if opened else "보물상자 닫힘", "interior")


def _banner():
    c = _Canvas(6, (16, 32))
    c.line((1, 2, 14, 2), 8)
    c.line((1, 1, 14, 1), 11)
    c.point((0, 2), 10)
    c.point((15, 2), 10)
    c.poly(((4, 3), (12, 3), (12, 26), (8, 30), (4, 26)), 2)
    c.poly(((5, 3), (11, 3), (11, 25), (8, 28), (5, 25)), 3)
    c.line((5, 4, 5, 24), 5)
    c.line((10, 4, 10, 25), 4)
    c.line((4, 25, 8, 29, 12, 25), 10)
    c.rows(("..a..", ".aba.", "aabaa", ".aba.", "..a..", "..a.."), (6, 11))
    return _finish(c, "보라색 성기")


def _tower():
    c = _Canvas(2, (32, 64))
    c.poly(((6, 22), (25, 22), (27, 27), (27, 58), (24, 62), (7, 62), (4, 58), (4, 27)), 2)
    for y in range(23, 61, 4):
        for x in range(5, 27):
            shade = 4 if x < 8 else 6 if x < 17 else 5 if x < 23 else 3
            c.line((x, y, x, y + 2), shade)
        c.line((7, y, 23, y), 7)
        for x in range(7 if y % 8 else 11, 27, 8):
            c.line((x, y + 1, x, y + 2), 3)
    for y in (23, 42, 58):
        c.poly(((3, y), (7, y - 2), (24, y - 2), (28, y), (28, y + 3), (24, y + 5), (7, y + 5), (3, y + 3)), 3)
        c.line(((3, y), (7, y - 2), (24, y - 2), (28, y)), 8)
        c.line(((4, y + 1), (8, y + 3), (23, y + 3), (27, y + 1)), 6)
        c.line((8, y + 4, 23, y + 4), 4)
    c.poly(((13, 32), (14, 30), (17, 30), (19, 32), (19, 39), (13, 39)), 2)
    c.line(((12, 39), (12, 32), (14, 29), (17, 29), (20, 32), (20, 39)), 7)
    c.line((15, 31, 15, 38), 9)
    c.line((11, 40, 20, 40), 8)
    c.poly(((2, 18), (5, 15), (8, 11), (12, 6), (15, 1), (17, 4), (21, 9), (26, 15), (29, 18), (27, 21), (23, 23), (8, 23), (4, 21)), 12)
    for y, half in ((6, 3), (9, 5), (12, 8), (15, 10), (18, 13)):
        c.line((15 - half, y, 15 + half, y), 14)
        c.line((16 - half, y + 1, 15 + half, y + 1), 13)
        c.line((16 - half, y, 14, y), 15)
        for x in range(16 - half, 16 + half, 5):
            c.point((x, y + 1), 12)
    c.line(((4, 20), (8, 22), (23, 22), (27, 20)), 15)
    c.point((15, 1), 8)
    return _finish(c, "원추 지붕 성탑")


def _tree16():
    """A DQ5-style round crown with a dark rim, dithered leaves and a rooted trunk."""
    c = _Canvas(1)
    rng = random.Random(3)
    cx, cy, rx, ry = 7.5, 6.3, 8.0, 7.0
    for y in range(14):
        for x in range(16):
            e = ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2
            if e > 1.0:
                continue
            shade = (x - cx) * 0.5 + (y - cy) > 2.5
            light = (x - cx) * 0.6 + (y - cy) < -3.5
            v = rng.random() if (x + y) % 2 else rng.random() * 0.6
            if e > 0.72:
                color = 1 if shade or y > cy or v >= 0.5 else 2
            elif shade:
                color = 2 if v < 0.55 else 4
            elif light:
                color = 7 if v < 0.35 else 5 if v < 0.7 else 4
            else:
                color = 5 if v < 0.3 else 4 if v < 0.85 else 2
            c.point((x, y), color)
    c.rows(("......99a.......", ".....99aa9......", "....9.9a9.9....."), (0, 13))
    return _finish(c, "작은 활엽수", "town")


def _castle_bricks(c, x0=0, width=16, top=0, bottom=15, shade=None):
    """Dark DQ5 castle masonry: black joints, a lit top edge on each brick, speckled faces."""
    rng = random.Random(31 + x0)
    for y in range(top, bottom + 1):
        row, yy = divmod(y - top, 4)
        for x in range(16):
            gx = x0 + x
            body = shade(gx) if shade else 3
            joint = (gx + (4 if row & 1 else 0)) % 8 == 7
            if yy == 3 or joint:
                color = 1
            elif yy == 0:
                color = min(body + 2, 6)
            else:
                v = rng.random()
                color = body - 1 if v < 0.25 else body + 1 if v > 0.9 else body
            c.point((x, y), color)


def _castle_wall():
    c = _Canvas(3)
    _castle_bricks(c)
    return _finish(c, "성 석벽")


def _tower_segment(right=False, cap=False):
    """Two blocks side by side form one 32-pixel round tower; brightness follows the curve."""
    c = _Canvas(3)

    def shade(gx):
        d = abs(gx - 15.5)
        return 2 if d > 13 else 3 if d > 9 else 4 if d > 4 else 5

    x0 = 16 if right else 0
    _castle_bricks(c, x0, shade=shade, bottom=9 if cap else 15)
    if cap:
        for y, color in ((10, 6), (11, 5), (12, 4), (13, 4), (14, 3), (15, 1)):
            c.line((0, y, 15, y), color)
        for x in range(16):
            if (x0 + x) % 6 == 5:
                c.line((x, 11, x, 14), 2)
    edge = 15 if right else 0
    c.line((edge, 0, edge, 15), 1)
    return _finish(c, "성탑 아랫단" if cap else "성탑 곡면 석벽")


def _gate():
    """Arched stone frame around iron-banded wooden doors, all in the wood bank's ramp."""
    c = _Canvas(4, (32, 32), fill=10)
    rng = random.Random(41)
    for y in range(32):
        for x in range(32):
            if (y % 4 == 3) or (x + (4 if y // 4 % 2 else 0)) % 8 == 7:
                c.point((x, y), 9)
            elif rng.random() < 0.2:
                c.point((x, y), 9 if rng.random() < 0.5 else 11)
    c.poly(((3, 31), (3, 10), (6, 5), (11, 2), (20, 2), (25, 5), (28, 10), (28, 31)), 11)
    c.poly(((5, 31), (5, 11), (8, 7), (12, 5), (19, 5), (23, 7), (26, 11), (26, 31)), 1)
    c.poly(((6, 31), (6, 12), (9, 8), (12, 7), (19, 7), (22, 8), (25, 12), (25, 31)), 5)
    for x in range(6, 26):
        if x % 3 == 2:
            c.line((x, 9 if 9 < x < 22 else 12, x, 31), 4)
        elif x % 3 == 0:
            c.line((x, 9 if 9 < x < 22 else 12, x, 31), 6)
    c.line((15, 7, 15, 31), 1)
    c.line((16, 7, 16, 31), 3)
    for y in (13, 24):
        c.line((6, y, 25, y), 1)
        c.line((6, y + 1, 25, y + 1), 9)
    c.rows(("8778", "7117", "7117", "8778"), (10, 18))
    c.rows(("8778", "7117", "7117", "8778"), (18, 18))
    return _finish(c, "바트랜드 양쪽 여닫이 성문")


def _small_fixture(kind):
    patterns = {
        "gold_door16": (4, (
            "....11111111....", "...1155555511...", "..115677766511..", ".11567656765611.",
            ".15676567656751.", ".15676567656751.", ".15676567656751.", ".15676567656751.",
            ".15676567658751.", ".15676567658751.", ".15676567656751.", ".15676567656751.",
            ".15676567656751.", ".15676567656751.", ".14444444444441.", ".11111111111111.",
        ), "小형 문"),
        "iron_fence16": (3, (
            "..2...2...2...2.", "..5...5...5...5.", "..5...5...5...5.", "..5...5...5...5.",
            "5555555555555555", "2222222222222222", "..5...5...5...5.", "..5...5...5...5.",
            "..5...5...5...5.", "..5...5...5...5.", "5555555555555555", "2222222222222222",
            "..5...5...5...5.", "..5...5...5...5.", "..2...2...2...2.", "................",
        ), "철창"),
        "window16": (2, (
            "......77........", "....78877.......", "...7811177......", "..781171177.....",
            "..781171137.....", "..781171137.....", "..787777737.....", "..781171137.....",
            "..781171137.....", "..781171137.....", "..781171137.....", "..781171137.....",
            ".78888888877....", ".34444444443....", "................", "................",
        ), "작은 아치창"),
        "statue": (3, (
            ".......34.......", "......3563......", "....445664......", "...3455432......",
            "..34564332......", "..356654432.....", ".34556544332....", ".2345644332.....",
            "..23544332......", "...2444432......", "...2555542......", "..355555543.....",
            ".35666666543....", ".34555555432....", ".23333333332....", "................",
        ), "석재 장식상"),
        "round_table": (4, (
            ".....233332.....", "...2367776532...", "..367777777653..", ".36776666677653.",
            ".36766666667653.", ".35666666666643.", "..345666666543..", "...2345555432...",
            "....23333332....", "......242.......", "......242.......", ".....24442......",
            "....2442442.....", "....22...22.....", "................", "................",
        ), "둥근 탁자"),
        "wardrobe": (4, (
            ".23333333333332.", ".26777777777762.", ".26444424444462.", ".26455424554462.",
            ".26455424554462.", ".26444424444462.", ".26444424444462.", ".26448424844462.",
            ".26444424444462.", ".26455424554462.", ".26455424554462.", ".26444424444462.",
            ".26777777777762.", ".23333333333332.", "..22........22..", "................",
        ), "옷장"),
        "washbasin": (3, (
            "................", "....3455543.....", "..35677777653...", ".3565333356653..",
            ".3653222235563..", ".3653322335563..", ".3456555565543..", "..34566666543...",
            "...345555543....", "....2333332.....", ".....24442......", "....3455543.....",
            "...345555543....", "....2333332.....", "................", "................",
        ), "수반"),
        "chimney": (2, (
            "....3455543.....", "...357777753....", "..35731113753...", "..35731113753...",
            "..34577777543...", "...345555543....", "...356535643....", "...356535643....",
            "...344444443....", "...356356543....", "...356356543....", "..35777777543...",
            "..34555555443...", "...233333332....", "................", "................",
        ), "원통형 석재 장식"),
    }
    bank, rows, role = patterns[kind]
    c = _Canvas(bank)
    c.rows(rows)
    return _finish(c, role.replace("小형", "작은"), "town")


def _counter():
    c = _Canvas(4, fill=3)
    c.rect((0, 0, 15, 6), 5)
    c.line((0, 0, 15, 0), 8)
    c.line((0, 3, 15, 3), 4)
    c.line((0, 6, 15, 6), 7)
    c.line((0, 7, 15, 7), 2)
    for x in (0, 8):
        c.rect((x + 1, 9, x + 6, 14), 4)
        c.line((x + 1, 9, x + 6, 9), 6)
        c.line((x + 6, 10, x + 6, 14), 2)
    return _finish(c, "카운터", "town")


def _armour_sign():
    c = _Canvas(4)
    c.image = _sign("shop")
    c.draw = ImageDraw.Draw(c.image)
    c.rect((3, 3, 12, 9), 6)
    c.rows(("..a..a..", ".abbaab.", "abbbbbba", ".bbbbbb.", ".abbbba.", "..aaaa.."), (4, 3))
    return _finish(c, "방어구점 간판", "town")


def _house(kind):
    """Keep changes of material on CHR boundaries for the BG palette selector."""
    bank = 5 if kind == "red" else 4
    roof = _Canvas(bank, (64, 64))
    tile = _roof(kind)
    roof_mask = Image.new("1", (64, 32))
    ImageDraw.Draw(roof_mask).polygon(((15, 0), (48, 0), (63, 29), (63, 31), (0, 31), (0, 29)), fill=1)
    for y in range(0, 32, 16):
        for x in range(0, 64, 16):
            roof.image.paste(tile, (x, y))
    for y in range(32):
        for x in range(64):
            if not roof_mask.getpixel((x, y)):
                roof.image.putpixel((x, y), 0)
    roof.line(((15, 0), (0, 29), (0, 31)), 7)
    roof.line(((48, 0), (63, 29), (63, 31)), 2)
    roof.line((1, 30, 62, 30), 6)
    roof.line((1, 31, 62, 31), 1)
    wall = _Canvas(4, (64, 64))
    wall.rect((8, 32, 55, 55), 11)
    wall.line((8, 32, 55, 32), 2)
    wall.line((8, 33, 55, 33), 3)
    for x in (8, 21, 40, 53):
        wall.rect((x, 34, x + 2, 55), 2)
        wall.line((x, 34, x, 55), 5)
    for x in (12, 44):
        wall.rect((x, 38, x + 6, 46), 1)
        wall.line((x, 37, x + 6, 37), 5)
        wall.line((x + 3, 38, x + 3, 46), 6)
        wall.line((x, 42, x + 6, 42), 5)
        wall.line((x - 1, 47, x + 7, 47), 4)
    wall.rect((25, 37, 38, 55), 2)
    wall.rect((27, 38, 36, 55), 4)
    for x in (27, 30, 33, 36):
        wall.line((x, 39, x, 55), 6)
    wall.line((27, 43, 36, 43), 2)
    wall.line((27, 52, 36, 52), 2)
    wall.point((35, 48), 8)
    roof.image.paste(wall.image.crop((0, 32, 64, 56)), (0, 32))
    foundation = _Canvas(3, (64, 8))
    foundation.rect((8, 0, 55, 5), 3)
    foundation.line((8, 0, 55, 0), 6)
    foundation.line((8, 4, 55, 4), 2)
    for x in range(12, 56, 8):
        foundation.line((x, 1, x, 3), 4)
    roof.image.paste(foundation.image, (0, 56))
    result = _finish(roof, "붉은 기와 민가" if kind == "red" else "짚지붕 민가", "town")
    result.info["bank"] = None
    return result


def _market():
    c = _Canvas(3, (64, 64))
    for x0 in (0, 32):
        for y in range(32):
            inset = (8, 5, 3, 2, 1, 0)[min(y // 2, 5)]
            if y >= 28:
                inset = 0
            c.line((x0 + inset, y, x0 + 31 - inset, y), (5, 6, 5, 4)[y % 4])
            if y % 4 == 3:
                c.line((x0 + inset, y, x0 + 31 - inset, y), 3)
            c.point((x0 + inset, y), 7)
        c.line((x0, 31, x0 + 31, 31), 2)
    wood = _Canvas(4, (64, 32))
    for x0 in (0, 32):
        wood.rect((x0 + 2, 0, x0 + 29, 22), 1)
        for x in (x0 + 1, x0 + 28):
            wood.rect((x, 0, x + 2, 30), 3)
            wood.line((x, 0, x, 29), 7)
        wood.rect((x0 + 4, 8, x0 + 27, 21), 4)
        wood.line((x0 + 4, 8, x0 + 27, 8), 7)
        wood.line((x0 + 4, 11, x0 + 27, 11), 6)
        for x in range(x0 + 5, x0 + 27, 5):
            wood.line((x, 12, x, 20), 3)
            wood.line((x + 1, 12, x + 1, 20), 5)
        wood.line((x0 + 4, 22, x0 + 27, 22), 2)
    wood.rows(("...a...", "..aba..", ".abbaa.", "abbbba.", ".abbaa.", "..aa..."), (12, 1))
    wood.rows(("..aaaa..", ".abbbba.", "abbbbbba", ".bbbbbb.", "..aaaa.."), (42, 2))
    c.image.paste(wood.image, (0, 32))
    result = _finish(c, "이무르 곡면 지붕 시장", "town")
    result.info["bank"] = None
    return result


def _in_bank(bank, color):
    """Global palette index of a colour in another bank, for tiles whose 8x8 quadrants mix banks."""
    return bank * 16 + (_REMAP[bank][color] if bank in _REMAP else color)


def _pattern(bank, rows, role, reference="castle", size=(16, 16)):
    c = _Canvas(bank, size)
    c.rows(rows)
    return _finish(c, role, reference)


def _iron_door():
    c = _Canvas(3, fill=1)
    c.rect((0, 0, 15, 15), 2)
    c.rect((1, 1, 14, 15), 1)
    c.line((1, 1, 14, 1), 5)
    for x in (3, 6, 9, 12):
        c.line((x, 2, x, 15), 4)
        c.line((x - 1, 2, x - 1, 15), 5)
        c.point((x - 1, 2), 6)
    for y in (5, 11):
        c.line((1, y, 14, y), 4)
        c.line((1, y - 1, 14, y - 1), 6)
    c.rect((10, 7, 12, 9), 3)
    c.point((11, 8), 1)
    return _finish(c, "쇠창살 문")


def _red_paving_cracked():
    c = _Canvas(6)
    _stones(c, 8, 7, 4, 2, 1, 5)
    for points in (((2, 3), (4, 6), (3, 9), (6, 13)), ((10, 1), (12, 4), (11, 6), (14, 8)), ((7, 9), (9, 11))):
        c.line(points, 1)
    return _finish(c, "갈라진 붉은 돌 포장")


def _brick_paving():
    c = _Canvas(5, fill=2)
    rng = random.Random(14)
    for y in range(16):
        row, yy = divmod(y, 4)
        for x in range(16):
            xx = (x + (4 if row & 1 else 0)) % 8
            if yy == 3 or xx == 7:
                continue
            color = 6 if yy == 0 else 4 if yy == 2 else 5
            if color == 5 and rng.random() < 0.15:
                color = 7
            c.point((x, y), color)
    return _finish(c, "붉은 벽돌 바닥", "town")


def _cloth_table():
    c = _Canvas(4, fill=7)
    c.line((0, 0, 15, 0), 5)
    c.line((0, 1, 15, 1), 8)
    for x in range(1, 16, 5):
        c.line((x, 3, x + 2, 3), 6)
    c.line((0, 6, 15, 6), 6)
    c.line((0, 7, 15, 7), 5)
    for y in range(8, 16):
        for x in range(16):
            fold = x % 4
            color = 11 if y == 8 else 2 if y == 15 else 3 if fold == 0 else 5 if fold == 1 else 4
            if y == 14:
                color = 10 if x % 2 else 8
            c.image.putpixel((x, y), _in_bank(6, color))
    return _finish(c, "천 덮인 탁자")


def _potted_plant():
    return _pattern(1, (
        "......3..3......", "....3453453.....", "..34576475643...", ".3457865687543..",
        "3456786768765431", ".345676576765432", "3456765456765431", ".34565434565432.",
        "..34532235432...", "...9999999999...", "...9BBBBBBBB9...", "....9AAAAAA9....",
        "....9ABAAAA9....", "....9AAAAAA9....", ".....9AAAA9.....", ".....999999.....",
    ), "화분", "interior")


def _throne():
    return _pattern(6, (
        "....11111111....", "...1ABAAAABA1...", "..1A944444449A1.", "..1A945555549A1.",
        "..1A945555549A1.", "..1A945555549A1.", "..1A944444449A1.", ".1AA999999999AA1",
        "1AA9444444449AA1", "1A945555555549A1", "1A945555555549A1", "1A999999999999A1",
        "1AAAAAAAAAAAAAA1", ".18A1......1A81.", ".1891......1981.", "..11........11..",
    ), "옥좌")


def _bookshelf():
    c = _Canvas(4, fill=1)
    c.rect((0, 0, 15, 15), 3)
    c.line((0, 0, 15, 0), 6)
    c.line((0, 1, 0, 15), 5)
    c.line((15, 1, 15, 15), 2)
    books = ((2, 13), (1, 7), (2, 15), (1, 10), (2, 14), (2, 7), (1, 13), (2, 10), (1, 15))
    for top in (1, 9):
        c.rect((1, top, 14, top + 5), 1)
        x = 1
        for i, (width, color) in enumerate(books[(top // 9) * 3:] + books):
            if x > 14:
                break
            y = top + (1 if i % 3 == 1 else 0)
            c.rect((x, y, min(14, x + width - 1), top + 5), color)
            c.point((x, y), 8 if color in (7, 10) else 15 if color != 15 else 8)
            x += width
        c.line((1, top + 6, 14, top + 6), 6)
        c.line((1, top + 7 if top == 1 else 15, 14, top + 7 if top == 1 else 15), 3)
    return _finish(c, "책장", "interior")


def _sky():
    c = _Canvas(7, fill=7)
    for x, y, length in ((1, 3, 5), (9, 7, 4), (4, 12, 6), (13, 13, 3)):
        c.line((x, y, x + length, y), 6)
    return _finish(c, "하늘(떨어지는 칸)")


def _cabin(slats=False, post=None):
    """Log-cabin facades of the wooden village: planks or a slatted window band, with posts."""
    c = _Canvas(4, fill=2)
    if slats:
        c.rect((0, 0, 15, 3), 7)
        c.line((0, 0, 15, 0), 8)
        c.line((0, 3, 15, 3), 5)
        for x in range(16):
            c.line((x, 4, x, 14), (3, 6, 7, 5)[x % 4])
        c.line((0, 15, 15, 15), 1)
    else:
        for y in range(0, 16, 4):
            c.rect((0, y, 15, y + 2), 5)
            c.line((0, y, 15, y), 6)
            c.line((0, y + 2, 15, y + 2), 4)
            for x in ((3, 11) if y % 8 else (7,)):
                c.point((x, y + 1), 7)
    for x in {"left": (0,), "right": (13,), "center": (6,)}.get(post, ()):
        c.rect((x, 0, x + 2, 15), 1)
        c.line((x + 1, 0, x + 1, 15), 3)
    return _finish(c, "통나무집 벽" + (" 창살" if slats else "") + (f" 기둥 {post}" if post else ""), "town")


def _stump():
    return _pattern(4, (
        "................", "....11111111....", "..117777777711..", ".17766666666771.",
        ".17655555555671.", "1765566666655671", "1765677777765671", "1765566666655671",
        ".17655555555671.", ".14766666666741.", ".13477777777431.", ".13344444444331.",
        "1334433443344331", "134.1334433.1431", "11...1311311..11", "......1..1......",
    ), "나무 그루터기", "town")


def _log_pile():
    c = _Canvas(4)
    for x in (1, 8):
        c.rect((x + 1, 1, x + 5, 14), 1)
        c.rect((x, 2, x + 6, 13), 1)
        c.rect((x + 1, 2, x + 5, 13), 5)
        c.line((x + 2, 3, x + 2, 12), 6)
        c.line((x + 5, 3, x + 5, 12), 4)
        c.rect((x + 2, 1, x + 4, 2), 7)
        for y in (5, 9):
            c.line((x + 1, y, x + 2, y + 1), 3)
    return _finish(c, "세워 둔 장작", "town")


def _crops():
    c = _Canvas(1, fill=10)
    for y in (3, 11):
        c.line((0, y + 4, 15, y + 4), 9)
    for x0 in (0, 8):
        for y0 in (0, 8):
            c.rows(("..33..", ".3573.", "357753", "245542", ".2332."), (x0 + 1, y0 + 1))
    return _finish(c, "채소밭", "town")


def _signboard():
    c = _Canvas(4)
    for x in (3, 11):
        c.rect((x, 9, x + 1, 15), 3)
        c.line((x, 9, x, 15), 5)
    c.rect((0, 1, 15, 10), 1)
    c.rect((1, 2, 14, 9), 7)
    c.line((1, 2, 14, 2), 8)
    c.line((1, 9, 14, 9), 5)
    for y, (x0, x1) in ((4, (3, 12)), (6, (3, 10)), (8, (3, 8))):
        c.line((x0, y, x1, y), 4)
    return _finish(c, "팻말", "town")


def _grave():
    return _pattern(4, (
        "................", ".......11.......", "......1761......", "......1651......",
        "...1111651111...", "..176666666661..", "..165555555541..", "...1111541111...",
        "......1541......", "......1541......", "......1541......", "......1431......",
        "....11143111....", "...1333333331...", "....11111111....", "................",
    ), "나무 묘비", "town")


def _stone_ledge():
    c = _Canvas(3)
    _stones(c, 47, 6, 5, 3, 4, 6)
    for y, color in ((11, 3), (12, 2), (13, 2), (14, 1), (15, 1)):
        for x in range(16):
            if y > 11 or x % 5:
                c.point((x, y), color)
    return _finish(c, "바위 턱")


def _lion_statue():
    return _pattern(4, (
        "................", "..1111..........", ".166661.........", "16777761........",
        "16717661........", "1677766611111...", ".166666555566661", "1556665555566661",
        "1455655555556651", "1445555555555551", "1444554455555541", "1344443344444441",
        "1333333333333331", "1555555555555551", "1444444444444441", "1111111111111111",
    ), "금빛 사자상")


def _swamp():
    c = _Canvas(1, fill=2)
    rng = random.Random(23)
    for _ in range(9):
        x, y = rng.randrange(16), rng.randrange(16)
        c.rows(("33.", "343", ".3."), (x - 1, y - 1))
    for x, y in ((3, 4), (11, 9), (6, 13)):
        c.rows((".5.", "585", ".5."), (x, y))
    return _finish(c, "독늪", "town")


def _travel_door():
    import math
    c = _Canvas(7)
    for y in range(16):
        for x in range(16):
            dx, dy = x - 7.5, y - 7.5
            r = math.hypot(dx, dy)
            if r > 8.2:
                continue
            if r > 6.8:
                c.point((x, y), 2)
                continue
            v = (math.atan2(dy, dx) / (2 * math.pi) * 3 + r / 2.6) % 1
            c.point((x, y), (3, 4, 5, 6, 7, 6)[int(v * 6)])
    c.rect((7, 7, 8, 8), 7)
    return _finish(c, "여행의 문")


def _rock_wall(dark=False):
    c = _Canvas(3)
    _stones(c, 41 if not dark else 43, 9, 3 if dark else 4, 1, 2, None if dark else 5)
    return _finish(c, "바위벽" + (" 어두움" if dark else ""))


def _blue_tile():
    c = _Canvas(7, fill=4)
    for by in (0, 8):
        for bx in (0, 8):
            for y in range(8):
                for x in range(8):
                    if x == 7 or y == 7:
                        color = 3
                    else:
                        d = abs(x - 3) + abs(y - 3)
                        color = 7 if d < 3 else 6 if d == 3 else 4
                    c.point((bx + x, by + y), color)
    return _finish(c, "청백 타일 바닥")


def _stone_wall_cracked():
    image = _stone_wall()
    draw = ImageDraw.Draw(image)
    for points in (((4, 0), (6, 4), (5, 7), (8, 11), (7, 15)), ((6, 4), (10, 5)), ((8, 11), (12, 12))):
        draw.line(points, fill=_in_bank(2, 1))
    image.info["role"] = "금 간 석벽"
    return image


def _stone_band():
    c = _Canvas(3, fill=5)
    c.line((0, 0, 15, 0), 6)
    c.line((0, 1, 15, 1), 6)
    c.line((0, 14, 15, 14), 3)
    c.line((0, 15, 15, 15), 2)
    for x in (0, 8):
        c.rows(("..33..", ".3443.", "346643", "346643", ".3443.", "..33.."), (x + 1, 5))
        c.line((x + 7, 3, x + 7, 12), 4)
    return _finish(c, "무늬 판석 띠")


def _altar():
    return _pattern(4, (
        "..111111111111..", ".16777777777761.", "1675555555555761", "1756666666666571",
        "175661DDDD166571", "17566DFFFFD66571", "175661DEED166571", "1756661EE1666571",
        "1756666116666571", "1755555555555571", "1777777777777771", "1444444444444441",
        "1466666666666641", "1455555555555541", "1444444444444441", "1111111111111111",
    ), "금 제단")


def _curtain():
    middle = "159A981111 89A951".replace(" ", "")
    return _pattern(3, (
        "1111111111111111", "1566666666666651", "15AAAAAAAAAAAA51", "1599999999999951",
        "1599981111899951", middle, middle, middle, middle, middle, middle, middle,
        "1599A811118A9951", "1599981111899951", "1533333333333351", "1222222222222221",
    ), "휘장 드리운 문간")


def _valance():
    """Blue drapery hung in scallops along the throne-room wall."""
    c = _Canvas(7, fill=2)
    for y in range(16):
        for x in range(16):
            fold = x % 4
            c.point((x, y), 5 if fold == 1 else 6 if fold == 2 else 4 if fold == 3 else 3)
    for x0 in (0, 8):
        c.rows(("77777777", "76666667", ".766667.", "..7667..", "...77..."), (x0, 0))
        c.rows(("........", "........", "1......1", "11....11", "111..111"), (x0, 0))
    c.line((0, 15, 15, 15), 1)
    return _finish(c, "푸른 휘장")


def _pillar(top=False):
    shaft = "....25646542...."
    rows = ((
        "................", ".23333333333332.", "2566666666666652", "2455555555555542",
        ".23444444444432.", "...2366666532...") + (shaft,) * 10) if top else ((shaft,) * 11 + (
        "...2566666532...", "..255555555532..", ".24444444444442.", ".22222222222222.", "................"))
    return _pattern(3, rows, "기둥 머리" if top else "기둥")


def _dais():
    """Three blocks wide: the golden royal bench behind the throne."""
    c = _Canvas(4, (48, 16))
    c.rect((2, 7, 45, 15), 1)
    c.rect((3, 8, 44, 14), 5)
    c.line((3, 8, 44, 8), 7)
    c.line((3, 11, 44, 11), 4)
    c.line((3, 14, 44, 14), 3)
    for x in range(6, 43, 4):
        c.point((x, 12), 7)
    for x0, mirror in ((0, False), (36, True)):
        rows = ("..1111......", ".167761.....", "16755761....", "1756665611..",
                "17561176661.", "1756..17561.", ".1761.17661.", "..11..1761..")
        for y, row in enumerate(rows):
            row = row[::-1] if mirror else row
            for x, char in enumerate(row):
                if char != ".":
                    c.point((x0 + x, y), int(char, 16))
    c.rows(("....1111....", "..11777711..", ".1765DD5671.", "176DFFFFD671", "1765DEED5671", ".1766EE6671.", "..17766771..", "...111111..."), (18, 0))
    return _finish(c, "왕좌 뒤 금 장식 벤치")


def _archway():
    import math
    c = _Canvas(3, (32, 16), fill=4)
    for y in range(16):
        for x in range(32):
            r = math.hypot(x - 15.5, (y - 16) * 1.1)
            if r < 10:
                c.point((x, y), 1)
            elif r < 14:
                angle = math.atan2(16 - y, x - 15.5)
                c.point((x, y), 2 if int(angle * 9) != angle * 9 and int(angle * 9 / math.pi * 2) % 2 and r > 13 else 6 if r < 11 else 5)
            elif (y % 4 == 3) or (x + (4 if y // 4 % 2 else 0)) % 8 == 7:
                c.point((x, y), 2)
    return _finish(c, "돌 아치 통로")


def _barrier():
    c = _Canvas(7)
    for y in range(16):
        for x in range(16):
            c.point((x, y), (3, 5, 7, 5)[(x + y) // 2 % 4])
    return _finish(c, "결계 바닥")


def _pew():
    return _pattern(6, (
        "................", "..111111111111..", ".1A9999999999A1.", ".19444444444491.",
        ".19455555555491.", ".19444444444491.", "1A933333333339A1", "1A944444444449A1",
        "1A955555555559A1", "1A944444444449A1", "1A999999999999A1", "1AAAAAAAAAAAAAA1",
        ".18..........81.", ".18..........81.", ".11..........11.", "................",
    ), "긴 의자", "interior")


def _castle_town_assets():
    assets = {
        "iron_door": _iron_door(), "red_paving_cracked": _red_paving_cracked(), "brick_paving": _brick_paving(),
        "cloth_table": _cloth_table(), "potted_plant": _potted_plant(), "throne": _throne(),
        "bookshelf": _bookshelf(), "sky": _sky(), "stump": _stump(), "log_pile": _log_pile(),
        "crops": _crops(), "signboard": _signboard(), "grave": _grave(), "stone_ledge": _stone_ledge(),
        "lion_statue": _lion_statue(), "swamp": _swamp(), "travel_door": _travel_door(),
        "rock_wall": _rock_wall(), "rock_wall_dark": _rock_wall(True), "blue_tile": _blue_tile(),
        "stone_wall_cracked": _stone_wall_cracked(), "stone_band": _stone_band(), "altar": _altar(),
        "curtain": _curtain(), "valance": _valance(), "pillar_top": _pillar(True), "pillar": _pillar(),
        "barrier": _barrier(), "pew": _pew(),
    }
    for name, slats, post in (("cabin_planks_post", False, "center"), ("cabin_planks_right", False, "right"),
                              ("cabin_slats", True, None), ("cabin_slats_left", True, "left"),
                              ("cabin_slats_right", True, "right"), ("cabin_slats_post", True, "center")):
        assets[name] = _cabin(slats, post)
    dais = _dais()
    for i, part in enumerate(("left", "middle", "right")):
        assets[f"dais_{part}"] = dais.crop((i * 16, 0, i * 16 + 16, 16))
    arch = _archway()
    assets["archway_left"], assets["archway_right"] = arch.crop((0, 0, 16, 16)), arch.crop((16, 0, 32, 16))
    return assets


# Red paving colours as found in bank 3, so paving and grey quay stone can share an 8x8 tile.
_PAVING_IN_GREY = {1: 12, 2: 8, 4: 9, 5: 10}
# Quay colours by depth from the paved top: cream cap, then steps of face, face and dark riser.
_QUAY_STEPS = (7, 6, 2, 5, 5, 2, 5, 4, 1, 4, 4, 1, 4, 3, 1, 3, 3, 1)


def _quay(depth, role):
    """Harbour embankment stepping down to the water; depth(x, y) is 0 or less on the paved top
    and counts pixels outward into the steps."""
    paving = _red_paving()
    c = _Canvas(3)
    for y in range(16):
        for x in range(16):
            d = depth(x, y)
            if d <= 0:
                logical = _REMAP[6].index(paving.getpixel((x, y)) & 15)
                c.point((x, y), _PAVING_IN_GREY[logical])
            else:
                c.point((x, y), _QUAY_STEPS[min(d, len(_QUAY_STEPS)) - 1])
    return _finish(c, f"항구 석축 {role}")


def _quay_stairs():
    c = _Canvas(3, fill=1)
    c.image.paste(_quay(lambda x, y: 3 - y, "계단 위").crop((0, 0, 16, 3)), (0, 0))
    for y0 in (4, 8, 12):
        c.rect((2, y0, 13, y0 + 1), 5)
        c.line((2, y0, 13, y0), 6)
        c.line((3, y0 + 2, 12, y0 + 2), 2)
    for x in (0, 14):
        c.rect((x, 3, x + 1, 15), 4)
        c.line((x, 3, x, 15), 6)
    return _finish(c, "물가로 내려가는 돌계단")


def _audience(clothes):
    """A seated spectator seen from behind, as the FC theatre draws its crowd."""
    body, fold = ("D", "B") if clothes == "pink" else ("5", "3")
    rows = (
        "................", ".....999999.....", "....9FFFFFF9....", "...9FFAFFAFF9...",
        "...9FAFFFFAF9...", "...9FFAFFAFF9...", "....9AFFFFA9....", "...999AAAA999...",
        "..9DDDDDDDDDD9..", ".9DDCDDDDDDCDD9.", ".9DDCDDDDDDCDD9.", ".9DDDDDDDDDDDD9.",
        ".99DDDDDDDDDD99.", "..9999999999 9..".replace(" ", "9"), "..9A9......9A9..", "..99........99..",
    )
    rows = tuple(r.replace("D", body).replace("C", fold) for r in rows)
    return _pattern(1, rows, f"관객 뒷모습 {clothes}", "interior")


def _harbour_theatre_assets():
    quays = {
        "quay_w": lambda x, y: 12 - x, "quay_e": lambda x, y: x - 3, "quay_s": lambda x, y: y - 2,
        "quay_n": lambda x, y: 3 - y,
        "quay_sw": lambda x, y: max(12 - x, y - 3), "quay_se": lambda x, y: max(x - 3, y - 3),
        "quay_ne": lambda x, y: max(x - 3, 3 - y), "quay_nw": lambda x, y: max(12 - x, 3 - y),
        "quay_inner_sw": lambda x, y: min(12 - x, y - 3), "quay_inner_se": lambda x, y: min(x - 3, y - 3),
    }
    assets = {name: _quay(depth, name[5:]) for name, depth in quays.items()}
    assets["quay_stairs"] = _quay_stairs()
    for clothes in ("pink", "green"):
        assets[f"audience_{clothes}"] = _audience(clothes)
    return assets


_ROCK_NAMES = {1: "이끼", 2: "흙", 4: "갈색", 5: "붉은"}


def _cave_rock(bank):
    """DQ5 cave walls: lit lumps over dark crevices, using ramp 1-7 of one bank."""
    c = _Canvas(bank)
    # Bank 1 runs up to neon greens; moss stays in its darker half.
    body, light = (3, 4) if bank == 1 else (4, 6)
    _stones(c, 51 + bank, 6, body, 1, 2, light)
    rng = random.Random(bank)
    for _ in range(14):
        x, y = rng.randrange(16), rng.randrange(16)
        if c.image.getpixel((x, y)) == c.c(body):
            c.point((x, y), body - 1 if rng.random() < 0.6 else body + 1)
    return _finish(c, f"{_ROCK_NAMES[bank]} 동굴 바위벽", "town")


def _cave_floor(bank):
    c = _Canvas(bank, fill=4)
    rng = random.Random(70 + bank)
    for y in range(16):
        for x in range(16):
            if rng.random() < 0.14:
                c.point((x, y), 3 if rng.random() < 0.6 else 5)
    for x, y in ((3, 4), (11, 9), (6, 13)):
        c.rows(("66", "53", "22"), (x, y))
    return _finish(c, f"{_ROCK_NAMES[bank]} 동굴 바닥", "town")


def _boulder_wall():
    c = _Canvas(3)
    _stones(c, 61, 4, 5, 1, 3, 6)
    for x, y in ((3, 3), (11, 5), (6, 11), (13, 13)):
        if c.image.getpixel((x, y)) == c.c(5):
            c.point((x, y), 7)
    return _finish(c, "회색 바위벽")


def _ice_wall():
    c = _Canvas(7, fill=4)
    for y in range(16):
        row, yy = divmod(y, 4)
        for x in range(16):
            xx = (x + (4 if row & 1 else 0)) % 8
            if yy == 3 or xx == 7:
                continue
            c.point((x, y), 7 if yy == 0 else 6)
    for x, y in ((2, 1), (10, 5), (5, 9), (13, 13)):
        c.point((x, y), 5)
    return _finish(c, "얼음 벽돌")


def _ice_floor():
    c = _Canvas(7, fill=7)
    for x0, y0 in ((1, 3), (8, 10), (11, 1)):
        c.line((x0, y0 + 3, x0 + 3, y0), 6)
    c.line((0, 15, 15, 15), 6)
    return _finish(c, "얼음 바닥")


def _wood_grain():
    import math
    c = _Canvas(4)
    for y in range(16):
        for x in range(16):
            r = math.hypot(x - 7.5, (y - 7.5) * 1.4)
            c.point((x, y), (5, 6, 6, 4)[int(r * 0.9) % 4])
    c.line((0, 0, 15, 0), 3)
    c.line((0, 15, 15, 15), 2)
    c.line((0, 0, 0, 15), 3)
    c.line((15, 0, 15, 15), 2)
    return _finish(c, "나이테 나무벽", "town")


def _cloud():
    c = _Canvas(7, fill=6)
    for x, y, r in ((3, 4, 4), (11, 3, 4), (8, 10, 5), (1, 13, 3), (14, 12, 3)):
        c.draw.ellipse((x - r, y - r, x + r, y + r), fill=c.c(7))
    for x, y in ((5, 7), (12, 6), (10, 14)):
        c.point((x, y), 5)
    return _finish(c, "구름")


def _sandstone():
    c = _Canvas(4, fill=3)
    for y in range(16):
        row, yy = divmod(y, 4)
        for x in range(16):
            xx = (x + (4 if row & 1 else 0)) % 8
            if yy == 3 or xx == 7:
                continue
            c.point((x, y), 7 if yy == 0 else 6 if (x + y) % 5 else 5)
    return _finish(c, "사암 벽돌")


def _ladder():
    c = _Canvas(4)
    for x in (3, 11):
        c.rect((x, 0, x + 1, 15), 3)
        c.line((x, 0, x, 15), 6)
    for y in (2, 6, 10, 14):
        c.line((4, y, 11, y), 6)
        c.line((4, y + 1, 11, y + 1), 2)
    return _finish(c, "사다리", "town")


def _stone_steps():
    c = _Canvas(3, fill=2)
    for y0 in range(0, 16, 4):
        c.line((0, y0, 15, y0), 6)
        c.rect((0, y0 + 1, 15, y0 + 2), 5)
        c.line((0, y0 + 3, 15, y0 + 3), 2)
    for x in (0, 15):
        c.line((x, 0, x, 15), 1)
    return _finish(c, "돌계단")


def _arrow(direction):
    """Conveyor plate pushing one way; drawn pointing up and turned."""
    c = _Canvas(3, fill=4)
    c.rect((0, 0, 15, 15), 2)
    c.rect((1, 1, 14, 14), 4)
    c.poly(((7, 2), (13, 8), (10, 8), (10, 13), (5, 13), (5, 8), (2, 8)), 7)
    c.line(((2, 8), (7, 3)), 6)
    c.line(((10, 9), (10, 13), (5, 13)), 3)
    turn = {"up": None, "right": Image.Transpose.ROTATE_270, "down": Image.Transpose.ROTATE_180,
            "left": Image.Transpose.ROTATE_90}[direction]
    if turn:
        c.image = c.image.transpose(turn)
    return _finish(c, f"밀리는 바닥 {direction}")


def _lift():
    c = _Canvas(3, fill=3)
    c.rect((0, 0, 15, 15), 1)
    c.rect((1, 1, 14, 14), 5)
    for v in (4, 8, 11):
        c.line((2, v, 13, v), 3)
        c.line((v, 2, v, 13), 3)
    c.line((1, 1, 14, 1), 7)
    return _finish(c, "승강판")


def _mine_beam():
    """Timber frame propping a mine wall: lintel over two posts, rock showing between."""
    c = _Canvas(2)
    c.image = _cave_rock(2).copy()
    c.draw = ImageDraw.Draw(c.image)
    c.rect((0, 8, 15, 15), 1)
    c.rect((0, 6, 15, 9), 5)
    c.line((0, 6, 15, 6), 7)
    c.line((0, 9, 15, 9), 3)
    for x in (1, 11):
        c.rect((x, 10, x + 3, 15), 4)
        c.line((x, 10, x, 15), 6)
        c.line((x + 3, 10, x + 3, 15), 2)
    return _finish(c, "광산 들보", "town")


def _rock_pile():
    return _pattern(2, (
        "................", "................", "....1111........", "...156651.......",
        "..15677651..11..", "..16766551.1651.", ".1566655431675 1".replace(" ", "1"), ".145555433157651",
        "1111444331166551", "1566133311555541", "1567651115544431", "15666551.1444331",
        "14555541.1333311", ".1444431..1111..", "..111111........", "................",
    ), "바위 더미", "town")


def _pit():
    c = _Canvas(2)
    c.draw.ellipse((1, 2, 14, 14), fill=c.c(3))
    c.draw.ellipse((2, 3, 13, 13), fill=c.c(9))
    c.draw.arc((2, 3, 13, 13), 200, 340, fill=c.c(1))
    c.line((4, 13, 11, 13), 5)
    return _finish(c, "구덩이", "town")


def _grate():
    c = _Canvas(3, fill=1)
    c.rect((0, 0, 15, 15), 4)
    c.line((0, 0, 15, 0), 6)
    for v in (3, 7, 11):
        c.rect((v, 1, v + 1, 14), 5)
        c.rect((1, v, 14, v + 1), 5)
        c.line((v, 1, v, 14), 6)
    return _finish(c, "쇠 창살 바닥")


def _dungeon_assets():
    assets = {f"cave_rock_{_ROCK_NAMES[b]}": _cave_rock(b) for b in _ROCK_NAMES}
    assets.update({f"cave_floor_{_ROCK_NAMES[b]}": _cave_floor(b) for b in (2, 4)})
    assets = {name.replace("이끼", "moss").replace("흙", "earth").replace("갈색", "brown").replace("붉은", "red"): image
              for name, image in assets.items()}
    assets.update({
        "boulder_wall": _boulder_wall(), "ice_wall": _ice_wall(), "ice_floor": _ice_floor(),
        "wood_grain": _wood_grain(), "cloud": _cloud(), "sandstone": _sandstone(), "ladder": _ladder(),
        "stone_steps": _stone_steps(), "lift": _lift(), "mine_beam": _mine_beam(), "rock_pile": _rock_pile(),
        "pit": _pit(), "grate": _grate(),
    })
    for direction in ("up", "right", "down", "left"):
        assets[f"arrow_{direction}"] = _arrow(direction)
    return assets


def create_assets():
    """Return original indexed art; global palette entry zero is transparent."""
    assets = {
        "stone_wall": _stone_wall(),
        "stone_wall_top": _stone_wall("top"),
        "stone_wall_left": _stone_wall("left"),
        "stone_wall_right": _stone_wall("right"),
        "stone_floor": _stone_floor(),
        "cobble": _cobble(),
        "grass": _grass(),
        "dirt": _dirt(),
        "carpet": _carpet(),
        "red_paving": _red_paving(),
        "wood_floor": _wood_floor(),
        "wood_wall": _wood_wall(),
        "bridge": _bridge(),
        "stairs_up": _stairs(),
        "stairs_down": _stairs(True),
        "door_closed": _door(),
        "door_open": _door(True),
        "window": _window(),
        "tree": _tree(),
        "bush": _bush(),
        "flowers": _flowers(),
        "fence": _fence(),
        "well": _well(),
        "barrel": _barrel(),
        "pot": _pot(),
        "table": _table(),
        "chair": _chair(),
        "bed": _bed(),
        "chest_closed": _chest(),
        "chest_open": _chest(True),
        "tower": _tower(),
        "banner": _banner(),
        "tree16": _tree16(),
        "tower_left": _tower_segment(),
        "tower_right": _tower_segment(True),
        "tower_cap_left": _tower_segment(cap=True),
        "tower_cap_right": _tower_segment(True, True),
        "counter": _counter(),
        "sign_armour": _armour_sign(),
        "castle_wall": _castle_wall(),
        "dark_void": _finish(_Canvas(6, fill=1), "어두운 빈 공간"),
        "house_red": _house("red"),
        "house_straw": _house("straw"),
        "market_slate": _market(),
    }
    for name in ("gold_door16", "iron_fence16", "window16", "statue", "round_table", "wardrobe", "washbasin", "chimney"):
        assets[name] = _small_fixture(name)
    assets["sign_weapon"] = _sign("shop")
    assets["sign_weapon"].info["role"] = "무기점 간판"
    gate = _gate()
    assets["gate"] = gate
    for name, box in {
        "gate_top_left": (0, 0, 16, 16), "gate_top_right": (16, 0, 32, 16),
        "gate_bottom_left": (0, 16, 16, 32), "gate_bottom_right": (16, 16, 32, 32),
    }.items():
        assets[name] = gate.crop(box)
    bed = _bed_wide()
    assets["bed_wide"] = bed
    for name, box in {"bed_left": (0, 0, 16, 16), "bed_right": (16, 0, 32, 16)}.items():
        assets[name] = bed.crop(box)
    for kind in ("red", "straw", "slate"):
        assets[f"roof_{kind}"] = _roof(kind)
        assets[f"roof_{kind}_ridge"] = _ridge(kind)
    for kind in ("inn", "shop", "church"):
        assets[f"sign_{kind}"] = _sign(kind)
    for frame in range(3):
        assets[f"water{frame}"] = _water(frame)
    for direction in "nsew":
        assets[f"shore_{direction}"] = _shore(direction)
    assets.update(_castle_town_assets())
    assets.update(_harbour_theatre_assets())
    assets.update(_dungeon_assets())
    return assets
