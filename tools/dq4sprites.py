"""Hand-authored sprite studies with editable, indexed pixel matrices.

Rows in each sheet are south, west, east and north; columns are standing,
left step and right step. All matrices are original drawings.
"""

from PIL import Image


def _palette(
    colors: tuple[tuple[int, int, int], ...],
) -> tuple[tuple[int, int, int], ...]:
    return tuple(tuple((v << 3) | (v >> 2) for v in rgb) for rgb in colors)


RAGNAR_PALETTE = _palette(
    (
        (0, 0, 0),
        (4, 3, 5),
        (10, 4, 8),
        (17, 5, 11),
        (24, 9, 15),
        (29, 16, 21),
        (17, 9, 6),
        (26, 17, 10),
        (31, 24, 16),
        (9, 5, 4),
        (17, 12, 4),
        (29, 24, 9),
        (26, 26, 26),
        (12, 13, 17),
        (20, 20, 24),
        (31, 24, 26),
    )
)
HEALIE_PALETTE = _palette(
    (
        (0, 0, 0),
        (3, 4, 7),
        (2, 4, 12),
        (2, 6, 19),
        (3, 9, 26),
        (5, 14, 29),
        (12, 21, 31),
        (29, 31, 31),
        (12, 8, 3),
        (20, 13, 3),
        (28, 20, 5),
        (31, 26, 12),
        (31, 30, 21),
        (16, 6, 8),
        (26, 12, 14),
        (31, 20, 21),
    )
)

# Hex digits address the corresponding palette; dots are transparent.
RAGNAR_FRONT = (
    "......151.......",
    ".....14531......",
    "..C1135F5311C...",
    "..1C345F543C1...",
    "...1345F5431....",
    "..134445444431..",
    "..123AABBA3211..",
    "...167887761....",
    "...1717717161...",
    "...178778871....",
    "...169999961....",
    "....1967691.....",
    "..1BB18881BB1...",
    ".1BBA43334ABB1..",
    ".1455444455431..",
    ".1343445443341..",
    "..1713AB31471...",
    "..1612BB21261...",
    "...134334431....",
    "...133113331....",
    "....DD11DD1.....",
    "...1CE11CE1.....",
    "...1D9119D1.....",
    "....11..11......",
)
RAGNAR_BACK = (
    "......151.......",
    ".....14531......",
    "..C1135F5311C...",
    "..1C345F543C1...",
    "...1345F5431....",
    "..134445444431..",
    "..123333333321..",
    "...134444431....",
    "...134444431....",
    "...123333321....",
    "....1999991.....",
    "....1966691.....",
    "..1BB12221BB1...",
    ".1BBA43334ABB1..",
    ".1455433345431..",
    ".1343433343341..",
    "..17123332471...",
    "..16122222261...",
    "...134334431....",
    "...133113331....",
    "....DD11DD1.....",
    "...1DE11DE1.....",
    "...1D9119D1.....",
    "....11..11......",
)
RAGNAR_EAST = (
    "......1551......",
    "....1555431.....",
    "...154333431....",
    "...1455544431...",
    "...1345F443C1...",
    "...1344444C311..",
    "...123333AB321..",
    "...1343367881...",
    "...1343367181...",
    "...12333678881..",
    "....199996991...",
    "....19667991....",
    "...12311381.....",
    "..1BBA433331....",
    "..14555434431...",
    "..1345434DDE1...",
    "...123431DEC1...",
    "....13431DEB1...",
    "....13331DED1...",
    "....13333111....",
    ".....DD1DD1.....",
    "....1CE1CE1.....",
    "....1D911DD1....",
    ".....11..11.....",
)

RAGNAR_STEPS = (
    (
        "...134334431....",
        "...133113331....",
        "...1DD1.1DD1....",
        "...1CE1..1E1....",
        "...1D91...11....",
        "....11..........",
    ),
    (
        "...134334431....",
        "...133113331....",
        "....DD1.1DD1....",
        "....1E1.1CE1....",
        ".....11.19D1....",
        ".........11.....",
    ),
)
SIDE_STEPS = (
    (
        "....13331DED1...",
        "....13333111....",
        "....DD1..DD1....",
        "...1CE1..1CE1...",
        "...1D91...1DD1..",
        "....11.....11...",
    ),
    (
        "....13331DED1...",
        "....13333111....",
        ".....DD1DD1.....",
        ".....1D1CE1.....",
        "......119DD1....",
        "........111.....",
    ),
)

HEALIE_BELL = (
    "................",
    "................",
    ".....122221.....",
    "...1234554321...",
    "..134567765431..",
    "..145676555541..",
    ".13456555555431.",
    ".14555555555441.",
    ".13455555554431.",
    "..133444444331..",
    "...1223333221...",
    ".....111111.....",
)
HEALIE_TENDRILS = (
    (
        "...18B18B18B1...",
        "...1AB1AB1BA1...",
        "..18B18B1.1BA1..",
        "..1AB1AB1.1BA1..",
        "..1AB1BA1.18B1..",
        "...1A1BA1.1B81..",
        "....118B1.1B1...",
        ".....1AB1.11....",
        ".....1BA1.......",
        "......11........",
        "................",
        "................",
    ),
    (
        "...18B18B18B1...",
        "..18BA1AB1BA1...",
        "..1BA18B1.1BA1..",
        "..1B1.1AB1.1BA1.",
        "...11.1BA1.1B81.",
        "......18B1.1B1..",
        ".....18B1..11...",
        ".....1B1........",
        "......11........",
        "................",
        "................",
        "................",
    ),
    (
        "...18B18B18B1...",
        "...1AB1AB1BA1...",
        "...1BA1BA11BA1..",
        "....1BA1BA1BA1..",
        "....1B811B1B81..",
        "....1B1.111B1...",
        ".....11..18B1...",
        ".........1B1....",
        "..........11....",
        "................",
        "................",
        "................",
    ),
)


def _image(rows: tuple[str, ...], palette: tuple) -> Image.Image:
    if len(rows) != 24 or any(len(row) != 16 for row in rows):
        raise ValueError("sprite matrices must be 16 by 24")
    im = Image.new("P", (16, 24))
    im.putpalette([v for color in palette for v in color] + [0] * (768 - 48))
    im.putdata([0 if c == "." else int(c, 16) for row in rows for c in row])
    im.info["transparency"] = 0
    return im


def build_sprites() -> dict[str, Image.Image]:
    """Build transparent sheets from the original pixel matrices."""
    result = {}
    for name, palette in (("ragnar", RAGNAR_PALETTE), ("healie", HEALIE_PALETTE)):
        sheet = Image.new("P", (48, 96))
        sheet.putpalette([v for color in palette for v in color] + [0] * (768 - 48))
        sheet.info["transparency"] = 0
        for direction in range(4):
            for step in range(3):
                if name == "ragnar":
                    base = (RAGNAR_FRONT, RAGNAR_EAST, RAGNAR_EAST, RAGNAR_BACK)[
                        direction
                    ]
                    poses = SIDE_STEPS if direction in (1, 2) else RAGNAR_STEPS
                    rows = base if step == 0 else base[:18] + poses[step - 1]
                    sprite = _image(rows, palette)
                    if direction in (1, 2) and step:
                        shield = sprite.crop((9, 15, 13, 19))
                        for y in range(15, 19):
                            for x in range(9, 13):
                                sprite.putpixel((x, y), 3 if x < 11 else 0)
                        sprite.paste(shield, (10, 14) if step == 1 else (8, 15))
                    if step == 2:
                        upper = sprite.crop((0, 0, 16, 18))
                        sprite.paste(0, (0, 0, 16, 18))
                        sprite.paste(upper, (0, 1))
                else:
                    sprite = _image(HEALIE_BELL + HEALIE_TENDRILS[step], palette)
                    if direction != 3:
                        eyes = (4, 9) if direction == 0 else (10,)
                        for x in eyes:
                            for dx, dy in (
                                (0, 0),
                                (1, 0),
                                (0, 1),
                                (2, 1),
                                (1, 2),
                                (2, 2),
                            ):
                                sprite.putpixel((x + dx, 6 + dy), 7)
                            sprite.putpixel((x + 1, 7), 1)
                        mouth = (6, 7, 8, 9) if direction == 0 else (10, 11, 12)
                        for x in mouth[1:-1]:
                            sprite.putpixel((x, 10), 14)
                        sprite.putpixel((mouth[0], 9), 14)
                        sprite.putpixel((mouth[-1], 9), 14)
                if direction == 1:
                    sprite = sprite.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
                sheet.paste(sprite, (step * 16, direction * 24))
        result[name] = sheet
    return result
