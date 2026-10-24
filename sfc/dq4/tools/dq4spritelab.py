"""DQ4 스프라이트를 DQ5 원작 인물과 같은 배율로 견주고 MesenCE 로 띄우는 실험 도구; sfc/dq4/docs/dq4-sprite-format.md.

하위 명령:
  hero     sfc/dq4/tools/lua/dq4objdump.lua 덤프(방향별 vram/oam/cgram)에서 DQ5 주인공 16×24 를 복원해
           PNG 와 색 번호 행렬을 찍는다.
  data     인물 이름을 받아 sfc/dq4/tools/lua/dq4sprite.lua 가 읽는 4bpp 타일·팔레트 Lua 파일을 쓴다.
  compare  DQ5 주인공 4방향과 인물의 정지·보행 자세를 같은 배경·같은 배율(8배)로 나란히 그린다.

덤프와 결과는 모두 work/ 아래에만 둔다(기본 work/dq4-sprites/).
"""

import argparse
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dq4sprites import HEIGHT, WIDTH, SPRITE_NAMES, build_sheet  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
OBJ_BASE = 0xC000  # OBJ 이름 표 워드 $6000 = 바이트 C000
DIRECTIONS = ("down", "left", "right", "up")
GRASS = (66, 156, 74)


def color(cgram: bytes, index: int) -> tuple[int, int, int]:
    v = cgram[index * 2] | cgram[index * 2 + 1] << 8
    return tuple(((v >> s) & 31) << 3 | ((v >> s) & 31) >> 2 for s in (0, 5, 10))


def tile(vram: bytes, number: int) -> list[list[int]]:
    o = OBJ_BASE + number * 32
    px = [[0] * 8 for _ in range(8)]
    for y in range(8):
        b = (vram[o + y * 2], vram[o + y * 2 + 1], vram[o + 16 + y * 2], vram[o + 17 + y * 2])
        for x in range(8):
            px[y][x] = sum(((b[k] >> (7 - x)) & 1) << k for k in range(4))
    return px


def decode_hero(folder: Path, direction: str) -> Image.Image:
    """OAM 슬롯 0~7 을 낮은 번호가 위에 오도록(역순으로) 겹쳐 16×24 로 복원한다."""
    vram = (folder / f"{direction}-vram.bin").read_bytes()
    oam = (folder / f"{direction}-oam.bin").read_bytes()
    cgram = (folder / f"{direction}-cgram.bin").read_bytes()
    slots = []
    for i in range(8):
        x, y, t, a = oam[i * 4 : i * 4 + 4]
        hi = (oam[512 + i // 4] >> (i % 4 * 2)) & 3
        if y < 224:
            slots.append((x | (hi & 1) << 8, y, t | (a & 1) << 8, a))
    x0 = min(s[0] for s in slots)
    y0 = min(s[1] for s in slots)
    pal = (slots[0][3] >> 1) & 7
    im = Image.new("P", (WIDTH, HEIGHT), 0)
    palette = []
    for c in range(16):
        palette.extend(color(cgram, 128 + pal * 16 + c))
    im.putpalette(palette)
    for x, y, t, a in reversed(slots):
        px = tile(vram, t)
        for yy in range(8):
            for xx in range(8):
                v = px[7 - yy if a & 0x80 else yy][7 - xx if a & 0x40 else xx]
                if v and x - x0 + xx < WIDTH and y - y0 + yy < HEIGHT:
                    im.putpixel((x - x0 + xx, y - y0 + yy), v)
    im.info["transparency"] = 0
    return im


def on_background(sprite: Image.Image, background: Image.Image) -> Image.Image:
    rgba = sprite.convert("RGBA")
    rgba.putalpha(Image.frombytes("L", sprite.size, bytes(255 if p else 0 for p in sprite.tobytes())))
    out = background.copy()
    out.paste(rgba, (0, 0), rgba)
    return out


def matrix(im: Image.Image) -> str:
    return "\n".join(
        "".join(f"{im.getpixel((x, y)):X}" if im.getpixel((x, y)) else "." for x in range(WIDTH))
        for y in range(HEIGHT)
    )


def cmd_hero(args):
    folder = args.work / "dump"
    sheet = Image.new("P", (WIDTH * 4, HEIGHT), 0)
    for i, d in enumerate(DIRECTIONS):
        im = decode_hero(folder, d)
        sheet.putpalette(im.getpalette())
        sheet.paste(im, (i * WIDTH, 0))
        print(f"[{d}]\n{matrix(im)}")
    sheet.info["transparency"] = 0
    sheet.save(args.work / "dq5-hero.png", transparency=0)
    print(f"wrote {args.work / 'dq5-hero.png'}")


def cmd_data(args):
    sheet = build_sheet(args.name)
    pixels = list(sheet.get_flattened_data())
    frames = []
    for row in range(4):
        for col in range(3):
            tiles = bytearray()
            for ty in range(3):
                for tx in range(2):
                    t = bytearray(32)
                    for y in range(8):
                        for x in range(8):
                            v = pixels[(row * HEIGHT + ty * 8 + y) * 48 + col * WIDTH + tx * 8 + x]
                            for bit in range(4):
                                t[(bit // 2) * 16 + y * 2 + bit % 2] |= ((v >> bit) & 1) << (7 - x)
                    tiles += t
            frames.append("{" + ",".join(map(str, tiles)) + "}")
    palette = sheet.getpalette()
    words = []
    for i in range(16):
        r, g, b = palette[i * 3 : i * 3 + 3]
        v = (r >> 3) | (g >> 3) << 5 | (b >> 3) << 10
        words += [v & 255, v >> 8]
    target = args.work / f"{args.name}.lua"
    target.write_text("return {frames={" + ",".join(frames) + "},pal={" + ",".join(map(str, words)) + "}}")
    print(f"wrote {target}")


def cmd_compare(args):
    hero = Image.open(args.work / "dq5-hero.png")
    sheet = build_sheet(args.name)
    nohero = args.work / "dump" / "nohero.png"
    backgrounds = [Image.new("RGB", (WIDTH, HEIGHT), GRASS)]
    if nohero.exists():
        backgrounds.append(Image.open(nohero).convert("RGB").crop((120, 103, 136, 127)))
    cells = []
    for d in range(4):
        cells.append(hero.crop((d * WIDTH, 0, (d + 1) * WIDTH, HEIGHT)))
    cells.append(None)
    for col in (0, 1):
        for d in range(4):
            cells.append(sheet.crop((col * WIDTH, d * HEIGHT, (col + 1) * WIDTH, (d + 1) * HEIGHT)))
        cells.append(None)
    width = sum(WIDTH if c is not None else 4 for c in cells)
    out = Image.new("RGB", (width, HEIGHT * len(backgrounds)), GRASS)
    for r, bg in enumerate(backgrounds):
        x = 0
        for c in cells:
            if c is None:
                x += 4
                continue
            out.paste(on_background(c, bg), (x, r * HEIGHT))
            x += WIDTH
    out = out.resize((out.width * 8, out.height * 8), Image.Resampling.NEAREST)
    target = args.work / f"compare-{args.name}.png"
    out.save(target)
    print(f"wrote {target} (DQ5 주인공 4방향 | {args.name} 정지 4방향 | 보행 4방향; 줄마다 배경)")


def field_figure(work: Path) -> Image.Image | None:
    """일지 그림: DQ5 주인공과 라이안을 같은 필드 배경에 8배로, 아래에 자동 보행 화면 네 장을 3배로."""
    hero_png, play = work / "dq5-hero.png", work / "play"
    shots = [play / f"walk-{n}.png" for n in (60, 90, 120, 150)]
    if not hero_png.exists() or not all(s.exists() for s in shots):
        return None
    hero = Image.open(hero_png)
    sheet = build_sheet("ragnar")
    nohero = work / "dump" / "nohero.png"
    bg = Image.open(nohero).convert("RGB").crop((120, 103, 136, 127)) if nohero.exists() else Image.new("RGB", (WIDTH, HEIGHT), GRASS)
    top = Image.new("RGB", (WIDTH * 8 + 8, HEIGHT), GRASS)
    for d in range(4):
        top.paste(on_background(hero.crop((d * WIDTH, 0, (d + 1) * WIDTH, HEIGHT)), bg), (d * WIDTH, 0))
        top.paste(on_background(sheet.crop((0, d * HEIGHT, WIDTH, (d + 1) * HEIGHT)), bg), (WIDTH * 4 + 8 + d * WIDTH, 0))
    top = top.resize((top.width * 8, top.height * 8), Image.Resampling.NEAREST)
    strip = Image.new("RGB", (len(shots) * 96, 96), GRASS)
    for i, shot in enumerate(shots):
        strip.paste(Image.open(shot).convert("RGB").crop((104, 91, 152, 139)).resize((96, 96), Image.Resampling.NEAREST), (i * 96, 0))
    strip = strip.resize((strip.width * 3, strip.height * 3), Image.Resampling.NEAREST)
    out = Image.new("RGB", (max(top.width, strip.width), top.height + 8 + strip.height), GRASS)
    out.paste(top, (0, 0))
    out.paste(strip, (0, top.height + 8))
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--work", type=Path, default=ROOT / "work" / "dq4-sprites")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("hero").set_defaults(func=cmd_hero)
    p = sub.add_parser("data")
    p.add_argument("name", choices=SPRITE_NAMES)
    p.set_defaults(func=cmd_data)
    p = sub.add_parser("compare")
    p.add_argument("name", choices=SPRITE_NAMES)
    p.set_defaults(func=cmd_compare)
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    args.func(args)


if __name__ == "__main__":
    main()
