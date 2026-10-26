"""Rebuild original graphics previews without a ROM; sfc/dq4/docs/dq4-graphics.md."""

from pathlib import Path

from dq4graphics import assets
from dq4spritelab import field_figure
from dq4spritedrafts import DRAFT_NAMES, front
from dq4sprites import SPRITE_NAMES
from PIL import Image

ROOT = Path(__file__).resolve().parents[3]


def environment_figure():
    """새로 그린 환경 에셋을 확대합니다. 롬과 원작 추출 그림을 읽지 않습니다."""
    from dq4environment import contact_sheet
    from dq4environmentart import create_assets

    return contact_sheet(create_assets())


def environment_map_figure(rom, name="imuru", box=None):
    """FC 블록 배치에 새 환경 에셋을 놓은 맵(box 로 자름)을 2배로 키운다. 롬이 없으면 None."""
    if not rom.exists():
        return None
    from dq4environmentart import create_assets
    from dq4environmentmap import render_maps

    image = render_maps(rom, create_assets())[name][0].convert("RGB")
    if box:
        image = image.crop(box)
    return image.resize((image.width * 2, image.height * 2), Image.Resampling.NEAREST)


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


MENU_SHOTS = ("book", "menu", "settings", "delete")


def menu_figure(folder):
    """한글 메뉴 롬의 MesenCE 화면 넷(첫 메뉴·기록 있는 메뉴·설정·지우기 확인)을 2×2 로 2배.
    화면은 work/dq4-menu/fig/<이름>.png 에 둔다. 만드는 명령은 sfc/dq4/docs/dq4-menu-format.md 「검증」."""
    paths = [folder / f"{name}.png" for name in MENU_SHOTS]
    if not all(p.exists() for p in paths):
        return None
    sheet = Image.new("RGB", (256 * 2 + 4, 224 * 2 + 4), (24, 24, 24))
    for i, path in enumerate(paths):
        with Image.open(path) as shot:
            sheet.paste(shot.convert("RGB").crop((0, 0, 256, 224)), ((i % 2) * 260, (i // 2) * 228))
    return sheet.resize((sheet.width * 2, sheet.height * 2), Image.Resampling.NEAREST)


def name_entry_figure(folder):
    """이름 입력·기록 목록 화면의 창만 나란히 놓는다.
    work/name-entry/fig/entry.png·list.png 는 dq4-name-entry-format.md 검증 절차의 MesenCE 화면이다."""
    paths = [folder / f"{name}.png" for name in ("entry", "list")]
    if not all(path.exists() for path in paths):
        return None
    sheet = Image.new("RGB", (516, 176), (24, 24, 24))
    for i, path in enumerate(paths):
        with Image.open(path) as shot:
            sheet.paste(shot.convert("RGB").crop((0, 16, 256, 192)), (i * 260, 0))
    return sheet.resize((sheet.width * 2, sheet.height * 2), Image.Resampling.NEAREST)


def menu_message_figure(folder):
    """한글 메뉴 메시지 셋(지우기 확인 1CE·지운 뒤 1CF·기록 깨짐 1D0)의 창 아래쪽을 세로로 2배.
    화면은 work/dq4-menu-msg/fig/confirm·deleted·broken.png 에 둔다. 만드는 명령은 dq4-menu-format.md 「검증」."""
    paths = [folder / f"{name}.png" for name in ("confirm", "deleted", "broken")]
    if not all(p.exists() for p in paths):
        return None
    sheet = Image.new("RGB", (256, 96 * 3 + 8), (24, 24, 24))
    for i, path in enumerate(paths):
        with Image.open(path) as shot:
            sheet.paste(shot.convert("RGB").crop((0, 128, 256, 224)), (0, i * 100))
    return sheet.resize((sheet.width * 2, sheet.height * 2), Image.Resampling.NEAREST)


def name_game_figure(path):
    """선실 메시지 창의 주인공 이름. dq4namegamecheck.py 첫 사례(라이안)의 shot.png 를 work/name-game/fig/message.png 로 둔다."""
    if not path.exists():
        return None
    with Image.open(path) as shot:
        part = shot.convert("RGB").crop((0, 128, 256, 200))
    return part.resize((part.width * 2, part.height * 2), Image.Resampling.NEAREST)


def main():
    images = assets()
    output = ROOT / "sfc" / "dq4" / "images"
    output.mkdir(parents=True, exist_ok=True)
    environment_figure().save(output / "dq4-environment.webp", lossless=True)
    environment_map = environment_map_figure(ROOT / "rom" / "dq4.nes")
    if environment_map is None:
        print("rom/dq4.nes 가 없어 dq4-environment-imuru.webp 는 건너뜀")
    else:
        environment_map.save(output / "dq4-environment-imuru.webp", lossless=True)
        castle = environment_map_figure(ROOT / "rom" / "dq4.nes", "burland", (0, 0, 608, 320))
        castle.save(output / "dq4-environment-castle.webp", lossless=True)
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
    menu = menu_figure(ROOT / "work" / "dq4-menu" / "fig")
    if menu is None:
        print("work/dq4-menu/fig 에 메뉴 화면이 없어 dq4-menu.webp 는 건너뜀")
    else:
        menu.save(output / "dq4-menu.webp", lossless=True)
    messages = menu_message_figure(ROOT / "work" / "dq4-menu-msg" / "fig")
    if messages is not None:
        messages.save(output / "dq4-menu-messages.webp", lossless=True)
    game = name_game_figure(ROOT / "work" / "name-game" / "fig" / "message.png")
    if game is not None:
        game.save(output / "dq4-name-game.webp", lossless=True)
    names = name_entry_figure(ROOT / "work" / "name-entry" / "fig")
    if names is not None:
        names.save(output / "dq4-name-entry.webp", lossless=True)
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
