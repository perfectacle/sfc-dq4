"""Rebuild original graphics previews without a ROM; docs/dq4-graphics.md."""

from pathlib import Path

from dq4graphics import assets
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def main():
    images = assets()
    output = ROOT / "docs" / "images"
    output.mkdir(parents=True, exist_ok=True)
    for name, image in images.items():
        scale = 1 if name == "map" else 3
        preview = image.convert("RGBA").resize(
            (image.width * scale, image.height * scale), Image.Resampling.NEAREST
        )
        preview.save(output / f"dq4-graphics-{name}.webp", lossless=True)
    with Image.open(ROOT / "tools" / "dq4art" / "journey.png") as source:
        source.save(output / "dq4-graphics-journey.webp", lossless=True)
    frames = []
    for step in (0, 1, 2, 1):
        scene = images["map"].convert("RGBA")
        for name, x in (("ragnar", 240), ("healie", 264)):
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
    print("Rebuilt graphics previews and walking animation in docs/images")


if __name__ == "__main__":
    main()
