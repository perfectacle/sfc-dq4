"""Convert the original title to eight SFC BG palettes; docs/dq4-graphics.md."""

from pathlib import Path

from PIL import Image, ImageChops, ImageStat

SOURCE = Path(__file__).with_name("dq4art") / "title.png"


def build_title():
    with Image.open(SOURCE) as source:
        image = source.convert("RGB").resize((256, 224), Image.Resampling.LANCZOS)
    boxes = [(x, y, x + 8, y + 8) for y in range(0, 224, 8) for x in range(0, 256, 8)]
    crops = [image.crop(box) for box in boxes]
    features = [ImageStat.Stat(crop).mean for crop in crops]

    def distance(a, b):
        return sum((x - y) ** 2 for x, y in zip(a, b))

    centers = [features[0]]
    for _ in range(7):
        centers.append(max(features, key=lambda f: min(distance(f, c) for c in centers)))
    assignment = [min(range(8), key=lambda k: distance(f, centers[k])) for f in features]
    banks = []
    candidates = []
    for _ in range(5):
        banks, candidates = [], []
        for bank in range(8):
            members = [crop for crop, choice in zip(crops, assignment) if choice == bank]
            if not members:
                members = [crops[bank * len(crops) // 8]]
            strip = Image.new("RGB", (8 * len(members), 8))
            for i, crop in enumerate(members):
                strip.paste(crop, (8 * i, 0))
            colors = strip.quantize(colors=15, dither=Image.Dither.NONE).getpalette()[:45]
            # BG color zero always resolves to the common backdrop in hardware.
            colors = [0, 0, 0] + [((c >> 3) << 3) | (c >> 5) for c in colors]
            palette = Image.new("P", (1, 1))
            palette.putpalette(colors + colors[:3] * (256 - 16))
            banks.extend(colors)
            indexed = image.quantize(palette=palette, dither=Image.Dither.NONE)
            candidates.append(indexed.point([i if i < 16 else 0 for i in range(256)]))
        errors = []
        for candidate in candidates:
            diff = ImageChops.difference(image, candidate.convert("RGB"))
            errors.append([sum(ImageStat.Stat(diff.crop(box)).sum2) for box in boxes])
        updated = [min(range(8), key=lambda k: errors[k][i]) for i in range(len(boxes))]
        if updated == assignment:
            break
        assignment = updated

    output = Image.new("P", image.size)
    output.putpalette(banks + [0] * (768 - len(banks)))
    for box, bank in zip(boxes, assignment):
        crop = candidates[bank].crop(box)
        # Normalize backdrop pixels so palette bank does not change index zero.
        data = bytes(0 if (v & 15) == 0 else bank * 16 + (v & 15) for v in crop.tobytes())
        output.paste(Image.frombytes("P", (8, 8), data), box[:2])
    return output
