"""Build DQ4 environment drafts; see ../docs/dq4-environment-format.md."""

import argparse
import hashlib
import html
import json
import shutil
from pathlib import Path

from kr_patch.sfc import tiles
from PIL import Image, ImageDraw


def encode_image(image, palette):
    """Serialize one SFC BG screen, including a blank tile for screen padding."""
    if image.mode != "P" or image.width % 8 or image.height % 8:
        raise ValueError("expected an indexed image with 8-pixel aligned dimensions")
    if not 0 < image.width <= 256 or not 0 < image.height <= 256:
        raise ValueError("a preview screen must fit in 256x256 pixels")
    if len(palette) != 128 or any(palette[i] != palette[0] for i in range(0, 128, 16)):
        raise ValueError("expected eight palette banks sharing color zero")
    pal = bytearray()
    for rgb in palette:
        if len(rgb) != 3 or any(not 0 <= v <= 255 for v in rgb):
            raise ValueError("invalid RGB palette entry")
        values = [v >> 3 for v in rgb]
        if tuple((v << 3) | (v >> 2) for v in values) != tuple(rgb):
            raise ValueError("palette must use expanded BGR555 colors")
        pal.extend((values[0] | values[1] << 5 | values[2] << 10).to_bytes(2, "little"))
    expected_palette = [v for rgb in palette for v in rgb]
    if image.getpalette()[:384] != expected_palette:
        raise ValueError("image palette does not match the serialized palette")
    chr_tiles = [bytes(32)]
    lookup = {bytes(32): 0}
    entries = [0] * 1024
    banks_used = set()
    for ty in range(image.height // 8):
        for tx in range(image.width // 8):
            pixels = image.crop((tx * 8, ty * 8, tx * 8 + 8, ty * 8 + 8)).tobytes()
            if any(v > 127 or (v and (v < 16 or v % 16 == 0)) for v in pixels):
                raise ValueError(f"reserved palette index at tile {tx},{ty}")
            banks = {v >> 4 for v in pixels if v}
            if len(banks) > 1:
                raise ValueError(f"mixed palette banks at tile {tx},{ty}: {sorted(banks)}")
            bank = next(iter(banks), 0)
            banks_used.update(banks)
            rows = [[v & 15 for v in pixels[y * 8 : y * 8 + 8]] for y in range(8)]
            data = bytes(tiles.encode(rows, 4))
            if data not in lookup:
                if len(chr_tiles) >= 1024:
                    raise ValueError("SFC tile index limit exceeded")
                lookup[data] = len(chr_tiles)
                chr_tiles.append(data)
            entries[ty * 32 + tx] = lookup[data] | bank << 10
    chr_data = b"".join(chr_tiles)
    map_data = b"".join(v.to_bytes(2, "little") for v in entries)
    rebuilt = decode_image(chr_data, map_data, bytes(pal), image.size)
    if rebuilt.tobytes() != image.convert("RGB").tobytes():
        raise ValueError("serialized image has RGB differences")
    return {"chr": chr_data, "map": map_data, "pal": bytes(pal)}, {
        "size": list(image.size), "unique_tiles": len(chr_tiles),
        "palette_banks": sorted(banks_used), "rgb_roundtrip_differences": 0,
        "tilemap_size": [32, 32], "padding_tile": 0,
    }


def decode_image(chr_data, map_data, pal_data, size):
    if len(size) != 2 or any(v <= 0 or v > 256 or v % 8 for v in size):
        raise ValueError("decoded screen dimensions must be multiples of 8 within 256x256")
    if len(chr_data) % 32 or not 32 <= len(chr_data) <= 32768:
        raise ValueError("invalid CHR length")
    if len(map_data) != 2048 or len(pal_data) != 256:
        raise ValueError("expected 32x32 tilemap and 128-color palette")
    rgb = []
    for i in range(0, 256, 2):
        word = int.from_bytes(pal_data[i:i + 2], "little")
        if word & 0x8000:
            raise ValueError("BGR555 high bit must be zero")
        rgb.append(tuple(((word >> shift & 31) << 3) | ((word >> shift & 31) >> 2)
                         for shift in (0, 5, 10)))
    image = Image.new("RGB", size)
    for ty in range(size[1] // 8):
        for tx in range(size[0] // 8):
            offset = (ty * 32 + tx) * 2
            entry = int.from_bytes(map_data[offset:offset + 2], "little")
            if entry & 0xE000:
                raise ValueError("preview decoder expects no priority or flips")
            tile_id, bank = entry & 1023, entry >> 10 & 7
            if (tile_id + 1) * 32 > len(chr_data):
                raise ValueError("tilemap refers beyond CHR data")
            rows = tiles.decode(chr_data, tile_id * 32, 4)
            for y, row in enumerate(rows):
                for x, value in enumerate(row):
                    image.putpixel((tx * 8 + x, ty * 8 + y), rgb[bank * 16 + value if value else 0])
    return image


def indexed_canvas(size, palette):
    image = Image.new("P", size, 0)
    image.putpalette([v for rgb in palette for v in rgb] + [0] * 384)
    return image


def material_screen(assets, palette):
    image = indexed_canvas((256, 224), palette)
    names = ["tower", "tree", "well", "bed", "table", "barrel", "pot",
             "stone_wall", "stone_floor", "wood_wall", "wood_floor", "cobble",
             "roof_red", "roof_straw", "roof_slate", "grass", "water0", "bridge",
             "door_closed", "door_open", "stairs_up", "stairs_down", "window",
             "bush", "flowers", "fence", "banner", "sign_inn", "sign_shop", "sign_church"]
    x = y = row_h = 0
    for name in names:
        asset = assets[name]
        if x + asset.width > 256:
            x, y, row_h = 0, y + row_h + 8, 0
        if y + asset.height > 224:
            raise ValueError(f"material preview overflow at {name}")
        image.paste(asset, (x, y))
        x += asset.width + 8
        row_h = max(row_h, asset.height)
    return image


def architecture_screen(assets, palette):
    image = indexed_canvas((256, 224), palette)
    for name, x, y in (("house_red", 8, 16), ("house_straw", 88, 16),
                       ("market_slate", 168, 16), ("tower", 24, 120),
                       ("tree", 88, 120), ("banner", 144, 120)):
        asset = assets[name]
        image.paste(asset, (x, y))
    return image


def contact_sheet(assets):
    cell_w = max(160, max(asset.width for asset in assets.values()) + 16)
    cell_h = max(176, max(asset.height for asset in assets.values()) + 36)
    width = cell_w * 6
    sheet = Image.new("RGB", (width, ((len(assets) + 5) // 6) * cell_h), (28, 32, 40))
    draw = ImageDraw.Draw(sheet)
    for i, (name, asset) in enumerate(assets.items()):
        x, y = i % 6 * cell_w, i // 6 * cell_h
        scale = min(3, (cell_w - 16) // asset.width, (cell_h - 36) // asset.height)
        enlarged = asset.convert("RGBA").resize((asset.width * scale, asset.height * scale), Image.Resampling.NEAREST)
        sheet.paste(enlarged, (x + 8, y + 8), enlarged)
        draw.text((x + 8, y + cell_h - 20), name, fill=(225, 222, 205))
    return sheet


REFERENCES = {
    "nds-burland": "nds/dq4/screens/086-haout.png",
    "nds-imuru": "nds/dq4/screens/113-maout.png",
    "nds-burland-materials": "nds/dq4/map/tex/haout.png",
    "nds-imuru-materials": "nds/dq4/map/tex/maout.png",
    "fc-burland": "fc/dq4/maps/02-00-バトランド.png",
    "fc-imuru": "fc/dq4/maps/12-00-イムル.png",
}


def gallery(out, manifest, references):
    cards = []
    for name, data in manifest["assets"].items():
        cards.append(f'<figure><img src="assets/{name}.png" width="{data["size"][0] * 3}" '
                     f'height="{data["size"][1] * 3}"><figcaption>{html.escape(name)}</figcaption></figure>')
    refs = "".join(f'<figure><img class="reference" src="references/{name}.png"><figcaption>'
                   f'{html.escape(path)}</figcaption></figure>' for name, path in references.items())
    maps = "".join(f'<article><h3>{html.escape(name)}</h3><a href="maps/{name}.png">'
                   f'<img class="map" src="maps/{name}.png"></a></article>' for name in manifest["maps"])
    previews = "".join(f'<figure><img width="512" height="448" src="{name}.png">'
                       f'<figcaption>{html.escape(name)} · 2배</figcaption></figure>' for name in manifest["previews"])
    page = '''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>DQ4 환경 에셋 · SFC 시안</title><style>
body{margin:32px;background:#171e26;color:#e8e3d2;font:16px/1.6 system-ui}h1{font-size:28px}
.grid{display:flex;flex-wrap:wrap;gap:20px;align-items:start}figure{margin:0;padding:16px;background:#242e38}
img{image-rendering:pixelated;max-width:100%;object-fit:contain}figcaption{font-size:12px;color:#c3c8cd}
.reference{max-height:384px;width:auto}.map{max-width:100%;width:auto}a{color:#c2d7eb}article{margin-bottom:28px}
</style><h1>DQ4 환경 에셋 · SFC 시안</h1>
<p>NDS DQ4의 건축·재질을 참고해 새로 그린 환경 그래픽입니다. 캐릭터·몬스터는 제작 대상에서 제외했습니다.<br>
사용자 채택 전 시안입니다. 전체 맵은 FC 원작의 블록 배치를 유지한 비교용이며, 게임 전체 포팅을 뜻하지 않습니다.</p>
<p><a href="manifest.json">제작 목록·규격·출처</a> · <a href="verification.json">검증 기록</a></p>
'''
    page += '<h2>SFC 화면 크기</h2><div class="grid">' + previews + '</div>'
    page += '<h2>환경 에셋</h2><div class="grid">' + "".join(cards) + '</div>'
    page += '<h2>원작 배치 비교 맵</h2>' + maps
    page += '<h2>원작 참고</h2><div class="grid">' + refs + '</div></html>'
    (out / "index.html").write_text(page)


def build(out, rom=None, references=None):
    from dq4environmentart import PALETTE, create_assets

    assets = create_assets()
    repeated = create_assets()
    if set(assets) != set(repeated) or any(a.tobytes() != repeated[n].tobytes() or a.getpalette() != repeated[n].getpalette()
                                         for n, a in assets.items()):
        raise ValueError("asset creation is not deterministic")
    out.mkdir(parents=True, exist_ok=True)
    (out / "assets").mkdir(exist_ok=True)
    manifest = {"status": "draft; user visual acceptance pending", "engine_insertion": False,
                "design_basis": "NDS DQ4 architecture/materials, FC DQ4 layout, SFC DQ5 tile constraints",
                "assets": {}, "maps": {}, "previews": {}}
    for name, asset in assets.items():
        data, details = encode_image(asset, PALETTE)
        asset.save(out / "assets" / f"{name}.png")
        for suffix, content in data.items():
            (out / "assets" / f"{name}.{suffix}").write_bytes(content)
        details.update({key: value for key, value in asset.info.items() if key != "transparency"})
        details["sha256_pixels"] = hashlib.sha256(asset.tobytes()).hexdigest()
        manifest["assets"][name] = details
    contact_sheet(assets).save(out / "contact-sheet.png")
    previews = {"preview-materials": material_screen(assets, PALETTE)}
    if all(name in assets for name in ("house_red", "house_straw", "market_slate")):
        previews["preview-architecture"] = architecture_screen(assets, PALETTE)
    if rom:
        from dq4environmentmap import render_maps

        (out / "maps").mkdir(exist_ok=True)
        for name, (image, info) in render_maps(rom, assets).items():
            image.info.pop("transparency", None)
            image.save(out / "maps" / f"{name}.png")
            manifest["maps"][name] = info
            left = ((image.width - 256) // 32) * 16
            top = min(224, max(0, ((image.height - 224) // 32) * 16))
            if name in ("burland", "imuru"):
                previews[f"preview-{name}"] = image.crop((left, top, left + 256, top + 224))
                info["preview_crop"] = [left, top, left + 256, top + 224]
    for name, image in previews.items():
        image.info.pop("transparency", None)
        data, details = encode_image(image, PALETTE)
        image.save(out / f"{name}.png")
        for suffix, content in data.items():
            (out / f"{name}.{suffix}").write_bytes(content)
        manifest["previews"][name] = details
    copied = {}
    if references:
        (out / "references").mkdir(exist_ok=True)
        for name, path in REFERENCES.items():
            source = references / path
            if not source.is_file():
                raise FileNotFoundError(source)
            shutil.copyfile(source, out / "references" / f"{name}.png")
            copied[name] = path
    manifest["references"] = copied
    report = {"status": "passed", "asset_count": len(assets), "deterministic": True,
              "rgb_roundtrip_differences": 0, "reserved_palette_indices": "rejected",
              "mixed_8x8_palette_banks": "rejected", "engine_insertion": "not performed",
              "emulator": "see separate environment-probe report"}
    for name, data in (("manifest.json", manifest), ("verification.json", report)):
        (out / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    gallery(out, manifest, copied)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("work/environment"))
    parser.add_argument("--rom", type=Path, help="locally supplied FC DQ4 ROM for original layouts")
    parser.add_argument("--references", type=Path, help="private sfc-dq4-assets checkout")
    args = parser.parse_args()
    manifest = build(args.out, args.rom, args.references)
    print(f"PASS: {len(manifest['assets'])} environment assets, {len(manifest['maps'])} maps, "
          f"{len(manifest['previews'])} SFC screens; zero RGB roundtrip differences")


if __name__ == "__main__":
    main()
