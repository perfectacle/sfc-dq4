"""Build the original DQ4 graphics study kit; see docs/dq4-graphics.md.

The output uses SFC planar tiles, not the DQ5 engine's compressed asset format.
"""

import argparse
import hashlib
import io
import json
from pathlib import Path

from dq4pixels import build_assets
from dq4title import build_title
from kr_patch.sfc import bg, tiles
from PIL import Image


def assets():
    result = build_assets()
    result["title"] = build_title()
    return result


def png_bytes(image):
    stream = io.BytesIO()
    image.save(stream, format="PNG", optimize=False)
    return stream.getvalue()


def validate_image(name, image):
    if image.mode != "P":
        raise ValueError(f"{name}: expected indexed P image, got {image.mode}")
    if image.width % 8 or image.height % 8:
        raise ValueError(f"{name}: dimensions must be multiples of 8")
    if max(image.tobytes()) > (127 if name == "title" else 15):
        raise ValueError(f"{name}: palette indices exceed the supported bank count")
    if name in ("ragnar", "healie") and (
        image.size != (48, 96) or image.info.get("transparency") != 0
    ):
        raise ValueError(f"{name}: expected 48x96 sprite sheet, transparent index 0")
    if name == "title" and image.size != (256, 224):
        raise ValueError("title: expected 256x224 image")
    if name == "map" and image.size != (512, 512):
        raise ValueError("map: expected 512x512 image")


def export_image(name, image):
    validate_image(name, image)
    palette = image.getpalette()
    color_count = 128 if name == "title" else 16
    if palette is None or len(palette) < color_count * 3:
        raise ValueError(f"{name}: missing 16-color RGB palette")
    words = []
    for i in range(color_count):
        r, g, b = palette[i * 3 : i * 3 + 3]
        words.append((r >> 3) | (g >> 3) << 5 | (b >> 3) << 10)
    pal = b"".join(word.to_bytes(2, "little") for word in words)
    decoded_palette = bg.palette(pal)
    expected_palette = [
        tuple(c & 248 for c in palette[i : i + 3]) for i in range(0, color_count * 3, 3)
    ]
    if decoded_palette != expected_palette:
        raise ValueError(f"{name}: palette roundtrip mismatch")

    if name == "title" and any(palette[i : i + 3] != palette[:3] for i in range(0, 384, 48)):
        raise ValueError("title: all palette banks must share backdrop color zero")
    encoded = []
    tile_banks = []
    for y in range(0, image.height, 8):
        for x in range(0, image.width, 8):
            crop = image.crop((x, y, x + 8, y + 8)).tobytes()
            banks = {v >> 4 for v in crop if v & 15}
            if len(banks) > 1:
                raise ValueError(f"{name}: mixed palette banks in tile at {x},{y}")
            tile_banks.append(next(iter(banks), 0))
            local = bytes(v & 15 for v in crop)
            rows = [list(local[i : i + 8]) for i in range(0, 64, 8)]
            data = tiles.encode(rows, 4)
            if tiles.decode(data, 0, 4) != rows:
                raise ValueError(f"{name}: tile roundtrip mismatch at {x},{y}")
            encoded.append(data)

    files = {f"{name}.png": png_bytes(image)}
    scale = 2 if name == "map" else 3
    files[f"{name}-preview.png"] = png_bytes(
        image.resize(
            (image.width * scale, image.height * scale), Image.Resampling.NEAREST
        )
    )
    files[f"{name}.pal"] = pal
    unique = list(dict.fromkeys(encoded))
    details = {
        "width": image.width,
        "height": image.height,
        "colors_used": len(set(image.tobytes())),
        "transparent_index": image.info.get("transparency"),
        "tile_count": len(encoded),
        "unique_tiles": len(unique),
        "palette_format": f"{color_count} little-endian BGR555 words; RGB channels truncated to 5 bits",
        "palette_banks": color_count // 16,
        "engine_ready": False,
        "roundtrip_pixel_differences": 0,
    }
    if name in ("map", "title"):
        if len(unique) > 1024:
            raise ValueError(
                f"{name}: {len(unique)} unique tiles exceeds SFC BG tile index limit 1024"
            )
        files[f"{name}.chr"] = b"".join(unique)
        indices = {tile: i for i, tile in enumerate(unique)}
        cols, rows = image.width // 8, image.height // 8
        padded_cols = ((cols + 31) // 32) * 32
        padded_rows = ((rows + 31) // 32) * 32
        entries = []
        for screen_y in range(0, padded_rows, 32):
            for screen_x in range(0, padded_cols, 32):
                for y in range(screen_y, screen_y + 32):
                    for x in range(screen_x, screen_x + 32):
                        index = (
                            indices[encoded[y * cols + x]]
                            if x < cols and y < rows
                            else 0
                        )
                        bank = tile_banks[y * cols + x] if x < cols and y < rows else 0
                        entries.append((index | bank << 10).to_bytes(2, "little"))
        files[f"{name}.map"] = b"".join(entries)
        verify_tilemap(image, files[f"{name}.chr"], files[f"{name}.map"], padded_cols)
        details["chr_layout"] = "deduplicated 8x8 tiles, 32 bytes per tile"
        details["tilemap_layout"] = (
            f"32x32 screens, left to right then top to bottom; palette banks 0..{color_count // 16 - 1}, no flips"
        )
        details["tilemap_size_tiles"] = [padded_cols, padded_rows]
        details["tilemap_padding"] = "tile 0 outside visible image"
    else:
        files[f"{name}.chr"] = b"".join(encoded)
        details["chr_layout"] = (
            "8x8 tiles in image row order, 32 bytes per tile; no OBJ arrangement"
        )
    return files, details


def verify_tilemap(image, chr_data, map_data, map_width):
    """Read serialized screen entries and reconstruct visible global indices."""
    rebuilt = bytearray(image.width * image.height)
    for ty in range(image.height // 8):
        for tx in range(image.width // 8):
            screen = (ty // 32) * (map_width // 32) + tx // 32
            offset = (screen * 1024 + (ty % 32) * 32 + tx % 32) * 2
            entry = int.from_bytes(map_data[offset : offset + 2], "little")
            decoded = tiles.decode(chr_data, (entry & 1023) * 32, 4)
            bank = entry >> 10 & 7
            for y, row in enumerate(decoded):
                start = (ty * 8 + y) * image.width + tx * 8
                rebuilt[start : start + 8] = bytes(bank * 16 + v if v else 0 for v in row)
    expected = bytes(v if v & 15 else 0 for v in image.tobytes())
    if rebuilt != expected:
        raise ValueError("serialized tilemap/CHR reconstruction differs from source")


def build():
    images = assets()
    required = {"ragnar", "healie", "tileset", "map", "title"}
    if set(images) != required:
        raise ValueError(f"expected assets {sorted(required)}, got {sorted(images)}")
    outputs, manifest = {}, {}
    for name, image in images.items():
        files, details = export_image(name, image)
        outputs.update(files)
        manifest[name] = details
    return outputs, manifest


def verify():
    # Single lit pixels in separate planes expose swapped plane/bit ordering.
    pixels = [[0] * 8 for _ in range(8)]
    pixels[0][:4] = [1, 2, 4, 8]
    expected = bytearray(32)
    expected[0], expected[1], expected[16], expected[17] = 128, 64, 32, 16
    if tiles.encode(pixels, 4) != bytes(expected):
        raise ValueError("toolkit 4bpp output differs from known bitplane vector")
    first, manifest = build()
    second, repeated_manifest = build()
    if first != second or manifest != repeated_manifest:
        raise ValueError("asset generation is not deterministic")
    report = {
        "status": "passed",
        "asset_count": len(manifest),
        "known_bitplane_vector": "passed",
        "deterministic_generation": "passed",
        "palette_roundtrip": "passed at 5-bit precision",
        "tile_roundtrip": "passed; zero pixel index differences",
        "tilemap_reconstruction": "passed",
        "engine_insertion": "not tested; no ROM is read or written",
        "sha256": {
            name: hashlib.sha256(data).hexdigest()
            for name, data in sorted(first.items())
        },
    }
    return first, manifest, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("work/dq4-graphics"))
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate generation in memory without writing files",
    )
    args = parser.parse_args()
    try:
        outputs, manifest, report = verify()
        if not args.check:
            args.output.mkdir(parents=True, exist_ok=True)
            for name, data in outputs.items():
                (args.output / name).write_bytes(data)
            for name, content in (
                ("manifest.json", manifest),
                ("verification.json", report),
            ):
                (args.output / name).write_text(
                    json.dumps(content, ensure_ascii=False, indent=2) + "\n"
                )
    except (ValueError, OSError) as error:
        parser.exit(1, f"dq4graphics: {error}\n")
    print(
        f"PASS: {len(manifest)} assets; deterministic PNG/CHR/palette; zero tile roundtrip differences"
    )
    if not args.check:
        print(f"Output: {args.output}")


if __name__ == "__main__":
    main()
