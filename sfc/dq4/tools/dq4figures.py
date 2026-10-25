"""Rebuild original graphics previews without a ROM; sfc/dq4/docs/dq4-graphics.md."""

from pathlib import Path

from dq4graphics import assets
from dq4spritelab import field_figure
from dq4spritedrafts import DRAFT_NAMES, front
from dq4sprites import SPRITE_NAMES
from PIL import Image

ROOT = Path(__file__).resolve().parents[3]


def sprite_gallery(images):
    """인물마다 남 정지·보행, 서 정지·보행, 동, 북 정지·보행을 풀색 위에 6배로 늘어놓는다."""
    cells = ((0, 0), (0, 1), (1, 0), (1, 1), (2, 0), (3, 0), (3, 1))
    sheet = Image.new("RGBA", (16 * len(cells) + 2 * (len(cells) - 1), 26 * len(SPRITE_NAMES) - 2), (66, 156, 74, 255))
    for row, name in enumerate(SPRITE_NAMES):
        for col, (direction, pose) in enumerate(cells):
            frame = images[name].crop((pose * 16, direction * 24, pose * 16 + 16, direction * 24 + 24))
            sheet.alpha_composite(frame.convert("RGBA"), (col * 18, row * 26))
    return sheet.resize((sheet.width * 6, sheet.height * 6), Image.Resampling.NEAREST)


def draft_figure():
    """16×24 정면 시안(dq4spritedrafts.py)을 풀색 위에 8배로 나란히 놓는다."""
    sheet = Image.new("RGBA", (18 * len(DRAFT_NAMES) + 2, 26), (66, 156, 74, 255))
    for i, name in enumerate(DRAFT_NAMES):
        sheet.alpha_composite(front(name), (2 + i * 18, 1))
    return sheet.resize((sheet.width * 8, sheet.height * 8), Image.Resampling.NEAREST)


def main():
    images = assets()
    output = ROOT / "sfc" / "dq4" / "images"
    output.mkdir(parents=True, exist_ok=True)
    for name, image in images.items():
        scale = 1 if name == "map" else 3
        preview = image.convert("RGBA").resize(
            (image.width * scale, image.height * scale), Image.Resampling.NEAREST
        )
        preview.save(output / f"dq4-graphics-{name}.webp", lossless=True)
    sprite_gallery(images).save(output / "dq4-sprites-gallery.webp", lossless=True)
    draft_figure().save(output / "dq4-sprite-drafts.webp", lossless=True)
    field = field_figure(ROOT / "work" / "dq4-sprites")
    if field is None:
        print("work/dq4-sprites 에 DQ5 덤프·보행 화면이 없어 dq4-sprites-field.webp 는 건너뜀")
    else:
        field.save(output / "dq4-sprites-field.webp", lossless=True)
    with Image.open(ROOT / "sfc" / "dq4" / "tools" / "dq4art" / "journey.png") as source:
        source.save(output / "dq4-graphics-journey.webp", lossless=True)
    frames = []
    for step in (0, 1, 2, 1):
        scene = images["map"].convert("RGBA")
        for name, x in (("ragnar", 240), ("healie", 264), ("alena", 288), ("hero", 312)):
            sprite = (
                images[name].crop((step * 16, 0, step * 16 + 16, 24)).convert("RGBA")
            )
            scene.alpha_composite(sprite, (x, 264))
        frames.append(
            scene.crop((160, 208, 352, 368)).resize(
                (576, 480), Image.Resampling.NEAREST
            )
        )
    frames[0].save(
        output / "dq4-graphics-walk.webp",
        save_all=True,
        append_images=frames[1:],
        duration=180,
        loop=0,
        lossless=True,
    )
    print("Rebuilt graphics previews and walking animation in sfc/dq4/images")


if __name__ == "__main__":
    main()
