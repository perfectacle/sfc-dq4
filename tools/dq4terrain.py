"""Original castle and town terrain; no source game graphics are read."""

from PIL import Image, ImageDraw

PALETTE = (
    (8, 8, 16),
    (24, 40, 24),
    (24, 72, 24),
    (48, 112, 32),
    (80, 136, 40),
    (56, 56, 64),
    (104, 104, 104),
    (168, 168, 144),
    (224, 208, 152),
    (64, 24, 24),
    (136, 48, 24),
    (208, 104, 40),
    (16, 48, 112),
    (48, 112, 176),
    (104, 72, 40),
    (232, 176, 48),
)
TILE_SIZE = 16


def canvas(size=(16, 16), color=0):
    im = Image.new("P", size, color)
    im.putpalette([c for rgb in PALETTE for c in rgb] + [0] * 720)
    return im


def ground(kind, variant=0):
    im = canvas(color=2 if kind == "grass" else 5)
    d = ImageDraw.Draw(im)
    if kind == "grass":
        for y in range(16):
            for x in range(16):
                n = (x * 17 + y * 31 + x * y * 7 + variant * 19) % 53
                if n < 2:
                    d.point((x, y), fill=3)
                elif n == 17:
                    d.point((x, y), fill=1)
        for x, y in ((2 + variant * 3, 3 + variant * 2),):
            d.line((x, y, x + 1, y - 2), fill=3)
            d.point((x - 1, y - 1), fill=3)
    else:
        for row, y in enumerate(range(-2, 17, 4)):
            for col, x in enumerate(range(-5 + row % 2 * 3, 17, 6)):
                hi = 7 if (row * 3 + col + variant) % 5 else 6
                d.polygon(
                    [
                        (x + 1, y),
                        (x + 4, y),
                        (x + 5, y + 1),
                        (x + 4, y + 3),
                        (x + 1, y + 3),
                        (x, y + 2),
                    ],
                    fill=6 if (row + col + variant) % 3 else 5,
                )
                d.line((x + 1, y, x + 4, y), fill=hi)
                d.point((x, y + 1), fill=hi)
    return im


def brick():
    im = canvas(color=0)
    d = ImageDraw.Draw(im)
    for row, y in enumerate(range(0, 16, 4)):
        for x in range(-4 if row % 2 else 0, 16, 8):
            d.rectangle((x, y, x + 6, y + 2), fill=6)
            d.line((x, y, x + 6, y), fill=6)
            d.line((x, y, x + 2, y), fill=7 if row % 2 == 0 else 6)
            d.line((x, y + 1, x, y + 2), fill=5)
            d.line((x + 1, y + 2, x + 6, y + 2), fill=5)
            d.point((x + 4, y + 1), fill=5)
    return im


def roof():
    im = canvas(color=9)
    d = ImageDraw.Draw(im)
    for y in range(0, 16, 4):
        for x in range(-3 if y % 8 else 0, 16, 6):
            d.rectangle((x, y, x + 4, y + 2), fill=10)
            d.line((x + 1, y, x + 4, y), fill=11)
            d.point((x + 1, y + 1), fill=15)
            d.line((x + 5, y + 1, x + 5, y + 3), fill=0)
    return im


def _tree():
    im = canvas((32, 48), 2)
    for y in range(3):
        for x in range(2):
            im.paste(ground("grass", (x + y) % 3), (x * 16, y * 16))
    d = ImageDraw.Draw(im)
    d.ellipse((2, 30, 30, 43), fill=1)
    d.polygon(
        [(12, 23), (20, 23), (19, 38), (24, 42), (15, 40), (9, 42), (13, 35)], fill=9
    )
    d.line((15, 28, 15, 38, 12, 40), fill=14, width=2)
    d.line((19, 30, 18, 37), fill=0)
    clusters = (
        (8, 8, 7),
        (19, 6, 7),
        (24, 14, 7),
        (5, 19, 6),
        (15, 16, 9),
        (23, 25, 7),
        (12, 28, 7),
        (4, 28, 4),
    )
    for cx, cy, radius in clusters:
        d.polygon(
            [
                (cx - radius, cy),
                (cx - radius + 2, cy - 5),
                (cx, cy - radius),
                (cx + 5, cy - radius + 2),
                (cx + radius, cy),
                (cx + radius - 2, cy + 5),
                (cx, cy + radius),
                (cx - 5, cy + radius - 2),
            ],
            fill=1,
        )
        d.ellipse(
            (cx - radius + 2, cy - radius + 2, cx + radius - 2, cy + radius - 3), fill=2
        )
        for dx, dy in ((-3, -3), (0, -5), (3, -2), (-4, 1), (1, 1)):
            d.line((cx + dx, cy + dy, cx + dx + 2, cy + dy), fill=3)
            d.point((cx + dx, cy + dy - 1), fill=4)
    return im


def tile_bank():
    out = {}
    for i in range(3):
        out[f"grass{i}"] = ground("grass", i)
        out[f"cobble{i}"] = ground("cobble", i)
    out["wall"] = brick()
    for name in ("base", "cornice", "battlement", "window", "banner", "pier"):
        im = brick()
        d = ImageDraw.Draw(im)
        if name in ("base", "cornice"):
            if name == "base":
                shade = list(range(256))
                shade[7], shade[6] = 6, 5
                im = im.point(shade)
                d = ImageDraw.Draw(im)
            y = 11 if name == "base" else 1
            d.rectangle((0, y, 15, y + 3), fill=5)
            d.line((0, y, 15, y), fill=8)
            d.line((0, y + 1, 15, y + 1), fill=7)
            d.line((0, y + 4, 15, y + 4), fill=0)
        elif name == "battlement":
            d.rectangle((0, 0, 15, 5), fill=1)
            for x in (0, 10):
                d.rectangle((x, 0, x + 5, 7), fill=6)
                d.line((x, 0, x + 5, 0), fill=8)
                d.line((x, 0, x, 6), fill=7)
            d.line((0, 8, 15, 8), fill=7)
        elif name == "window":
            d.rounded_rectangle((4, 2, 11, 13), radius=4, fill=0, outline=7)
            d.rectangle((6, 6, 9, 11), fill=12)
            d.line((7, 3, 7, 11), fill=5)
            d.line((4, 14, 12, 14), fill=8)
        elif name == "banner":
            d.line((2, 1, 13, 1), fill=15)
            d.polygon([(4, 2), (11, 2), (11, 14), (8, 11), (4, 14)], fill=9)
            d.rectangle((5, 2, 9, 10), fill=10)
            d.line((7, 4, 7, 9), fill=15)
            d.line((5, 6, 9, 6), fill=15)
        else:
            d.rectangle((3, 0, 12, 15), fill=5)
            for y in range(0, 16, 4):
                d.rectangle((4, y, 11, y + 2), fill=7)
                d.line((4, y, 9, y), fill=7)
                d.rectangle((10, y, 11, y + 2), fill=6)
            d.line((12, 0, 12, 15), fill=0)
        out[name] = im
    gate = canvas((32, 32))
    for y in range(2):
        for x in range(2):
            gate.paste(brick(), (16 * x, 16 * y))
    d = ImageDraw.Draw(gate)
    d.rounded_rectangle((2, 1, 29, 44), radius=13, fill=7, outline=8, width=2)
    d.rounded_rectangle((6, 5, 25, 44), radius=9, fill=0, outline=5, width=2)
    for x in range(9, 25, 5):
        d.line((x, 9, x, 16), fill=14)
        d.point((x, 17), fill=7)
    d.line((7, 11, 24, 11), fill=14)
    for y in range(2):
        for x in range(2):
            out[f"gate{y}{x}"] = gate.crop((x * 16, y * 16, x * 16 + 16, y * 16 + 16))
    for edge in (
        "water",
        "bank_n",
        "bank_s",
        "bank_w",
        "bank_e",
        "bank_nw",
        "bank_ne",
        "bank_sw",
        "bank_se",
    ):
        im = canvas(color=12)
        d = ImageDraw.Draw(im)
        for y in (3, 10):
            x = 1 if y == 3 else 8
            d.line((x, y, x + 4, y), fill=13)
            d.point((x + 6, y - 1), fill=13)
        if edge != "water":
            directions = edge.split("_")[1]
            for side in directions:
                if side == "n":
                    d.rectangle((0, 0, 15, 2), fill=2)
                    d.line((0, 3, 15, 3), fill=14)
                    d.line((0, 4, 15, 4), fill=0)
                elif side == "s":
                    d.rectangle((0, 13, 15, 15), fill=2)
                    d.line((0, 12, 15, 12), fill=4)
                    d.line((0, 11, 15, 11), fill=1)
                elif side == "w":
                    d.rectangle((0, 0, 2, 15), fill=2)
                    d.line((3, 0, 3, 15), fill=14)
                    d.line((4, 0, 4, 15), fill=0)
                else:
                    d.rectangle((13, 0, 15, 15), fill=2)
                    d.line((12, 0, 12, 15), fill=4)
                    d.line((11, 0, 11, 15), fill=1)
        out[edge] = im
    for side in ("left", "right"):
        im = canvas(color=9)
        d = ImageDraw.Draw(im)
        for y in range(0, 16, 4):
            d.rectangle((0, y, 15, y + 2), fill=14)
            d.line((0, y, 15, y), fill=7)
            d.point((2, y + 1), fill=0)
            d.point((13, y + 1), fill=0)
        x = 0 if side == "left" else 14
        d.rectangle((x, 0, x + 1, 15), fill=8)
        out[f"bridge_{side}"] = im
    for name in (
        "roof",
        "roof_l",
        "roof_r",
        "roof_t",
        "roof_tl",
        "roof_tr",
        "roof_eave",
    ):
        im = roof()
        d = ImageDraw.Draw(im)
        if name in ("roof_t", "roof_tl", "roof_tr"):
            d.line((0, 0, 15, 0), fill=9)
            d.line((0, 1, 15, 1), fill=15)
        if name in ("roof_l", "roof_tl"):
            for y in range(16):
                cut = max(0, 15 - y) if name == "roof_tl" else 0
                d.line((0, y, cut, y), fill=2)
                d.point((cut + 1, y), fill=9)
                d.point((cut + 2, y), fill=11)
        if name in ("roof_r", "roof_tr"):
            for y in range(16):
                cut = min(15, y) if name == "roof_tr" else 15
                d.line((cut, y, 15, y), fill=2)
                d.point((cut - 1, y), fill=9)
        if name == "roof_eave":
            d.line((0, 12, 15, 12), fill=11)
            d.rectangle((0, 13, 15, 15), fill=0)
        out[name] = im
    for name in ("house", "house_window", "house_door", "house_base"):
        im = canvas(color=8)
        d = ImageDraw.Draw(im)
        d.line((0, 0, 0, 15), fill=9)
        d.line((1, 0, 1, 15), fill=14)
        d.line((14, 0, 14, 15), fill=14)
        d.line((15, 0, 15, 15), fill=9)
        d.line((0, 13, 15, 13), fill=14)
        d.line((0, 14, 15, 14), fill=9)
        for x, y in ((4, 3), (11, 7), (5, 11)):
            d.line((x, y, x + 2, y), fill=7)
        if name == "house_window":
            d.rectangle((3, 2, 12, 10), fill=9)
            d.rectangle((4, 3, 11, 9), fill=12)
            d.line((7, 3, 7, 9), fill=14)
            d.line((4, 6, 11, 6), fill=14)
            d.line((2, 11, 13, 11), fill=11)
        if name == "house_door":
            d.rounded_rectangle((3, 0, 12, 15), radius=4, fill=9)
            d.rectangle((4, 4, 11, 15), fill=14)
            for x in (5, 8, 11):
                d.line((x, 4, x, 15), fill=9)
            d.point((10, 10), fill=15)
        if name == "house_base":
            im.paste(brick().crop((0, 8, 16, 16)), (0, 8))
        out[name] = im
    tree = _tree()
    for y in range(3):
        for x in range(2):
            out[f"tree{y}{x}"] = tree.crop((x * 16, y * 16, x * 16 + 16, y * 16 + 16))
    for name in ("flowers", "bush", "well", "steps"):
        im = ground("grass")
        d = ImageDraw.Draw(im)
        if name == "flowers":
            for x, y in ((3, 5), (10, 10), (6, 13)):
                d.line((x, y, x, y + 2), fill=1)
                d.line((x - 1, y, x + 1, y), fill=8)
                d.point((x, y - 1), fill=15)
        elif name == "bush":
            for x, y in ((4, 7), (10, 5), (11, 10), (5, 11)):
                d.ellipse((x - 3, y - 3, x + 3, y + 3), fill=1)
                d.ellipse((x - 2, y - 3, x + 2, y + 1), fill=3)
                d.point((x - 1, y - 2), fill=4)
        elif name == "well":
            im = ground("cobble")
            d = ImageDraw.Draw(im)
            d.ellipse((1, 3, 14, 14), fill=0)
            d.ellipse((1, 2, 14, 11), fill=7)
            d.ellipse((4, 4, 11, 8), fill=12)
            d.line((3, 10, 3, 12), fill=5)
            d.line((9, 11, 9, 13), fill=5)
            d.line((3, 3, 11, 3), fill=8)
        else:
            for y in range(0, 16, 4):
                d.rectangle((0, y, 15, y + 2), fill=6)
                d.line((0, y, 15, y), fill=8)
                d.line((0, y + 3, 15, y + 3), fill=0)
        out[name] = im
    return out


def layout():
    rows = [[f"grass{(x * 3 + y * 7) % 3}" for x in range(32)] for y in range(32)]

    def put(x, y, name):
        rows[y][x] = name

    def fill(x0, y0, x1, y1, name):
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                put(x, y, name if name != "cobble" else f"cobble{(x + y) % 3}")

    fill(3, 3, 28, 15, "water")
    for x in range(3, 29):
        put(x, 3, "bank_n")
        put(x, 15, "bank_s")
    for y in range(3, 16):
        put(3, y, "bank_w")
        put(28, y, "bank_e")
    for x, y, name in (
        (3, 3, "bank_nw"),
        (28, 3, "bank_ne"),
        (3, 15, "bank_sw"),
        (28, 15, "bank_se"),
    ):
        put(x, y, name)
    fill(5, 4, 26, 13, "cobble")
    fill(6, 4, 25, 5, "wall")
    fill(6, 4, 25, 4, "battlement")
    fill(6, 6, 25, 6, "base")
    for x in (8, 12, 19, 23):
        put(x, 5, "window")
    for x in (6, 25):
        fill(x, 7, x, 10, "wall")
        put(x, 11, "base")
    fill(6, 10, 25, 12, "wall")
    fill(6, 10, 25, 10, "battlement")
    fill(6, 13, 25, 13, "base")
    for x in (10, 12, 19, 21):
        put(x, 11, "window")
    for x in (13, 18):
        put(x, 12, "banner")
    for x0 in (5, 24):
        fill(x0, 8, x0 + 2, 8, "battlement")
        fill(x0, 9, x0 + 2, 12, "wall")
        fill(x0, 13, x0 + 2, 13, "cornice")
        put(x0 + 1, 10, "window")
    for x0 in (5, 24):
        for y in range(9, 14):
            put(x0, y, "pier")
            put(x0 + 2, y, "pier")
        for y in range(3, 6):
            put(x0, y, "pier")
            put(x0 + 2, y, "pier")
        fill(x0, 2, x0 + 2, 2, "battlement")
        put(x0 + 1, 3, "window")
        put(x0 + 1, 4, "wall")
        put(x0 + 1, 5, "cornice")
    for y in range(2):
        for x in range(2):
            put(15 + x, 12 + y, f"gate{y}{x}")
    for y in (14, 15, 16):
        put(15, y, "bridge_left")
        put(16, y, "bridge_right")
    fill(14, 17, 17, 31, "cobble")
    fill(5, 24, 26, 25, "cobble")
    for x0, y0 in ((4, 18), (22, 18), (4, 26), (22, 26)):
        for y in range(3):
            for x in range(6):
                name = "roof_t" if y == 0 else "roof_eave" if y == 2 else "roof"
                if x == 0:
                    name = "roof_tl" if y == 0 else "roof_l"
                if x == 5:
                    name = "roof_tr" if y == 0 else "roof_r"
                put(x0 + x, y0 + y, name)
        fill(x0 + 1, y0 + 3, x0 + 4, min(y0 + 4, 31), "house")
        for x in (1, 4):
            put(x0 + x, y0 + 3, "house_window")
        put(x0 + 3, y0 + 3, "house_door")
        if y0 + 4 < 32:
            put(x0 + 3, y0 + 4, "steps")
    for x, y in (
        (1, 1),
        (8, 0),
        (22, 0),
        (29, 2),
        (0, 10),
        (29, 12),
        (1, 21),
        (10, 17),
        (19, 19),
        (11, 27),
        (28, 27),
    ):
        for dy in range(3):
            for dx in range(2):
                put(x + dx, y + dy, f"tree{dy}{dx}")
    for x, y in ((11, 22), (20, 26), (2, 18), (29, 21), (9, 15), (24, 16), (19, 7)):
        put(x, y, "flowers")
    for x, y in ((8, 8), (9, 8), (22, 8), (23, 8), (11, 20), (20, 22), (2, 28)):
        put(x, y, "bush")
    put(11, 24, "well")
    return tuple(tuple(row) for row in rows)


TILE_NAMES = tuple(tile_bank())
MAP_LAYOUT = layout()


def build_terrain():
    bank = tile_bank()
    sheet = canvas((128, ((len(bank) + 7) // 8) * 16))
    for index, tile in enumerate(bank.values()):
        sheet.paste(tile, ((index % 8) * 16, (index // 8) * 16))
    scene = canvas((512, 512))
    for y, row in enumerate(MAP_LAYOUT):
        for x, name in enumerate(row):
            scene.paste(bank[name], (x * 16, y * 16))
    return {"tileset": sheet, "map": scene}
