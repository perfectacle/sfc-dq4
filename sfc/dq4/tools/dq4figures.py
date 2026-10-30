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


def environment_field_figure(rom, box=(1600, 1200, 2240, 1600)):
    """FC 필드 0 에 새 필드 에셋을 놓은 그림의 한 부분(box). 롬이 없으면 None."""
    if not rom.exists():
        return None
    from dq4environmentart import create_assets
    from dq4environmentmap import render_fields

    return render_fields(rom, create_assets())["field0"][0].convert("RGB").crop(box)


def environment_rom_figure(folder):
    """DQ5 에 넣은 바트랜드·이무르 맵의 MesenCE 화면을 2배로 나란히 놓는다.

    화면은 dq4environmentromcheck.py --out work/dq4-environment-rom/check 가 남긴
    <맵>/<맵>.png(워프해 도착한 프레임)다. 없으면 None.
    """
    paths = [folder / name / f"{name}.png" for name in ("burland", "imuru")]
    if not all(path.exists() for path in paths):
        return None
    sheet = Image.new("RGB", (516, 224), (24, 24, 24))
    for i, path in enumerate(paths):
        with Image.open(path) as shot:
            sheet.paste(shot.convert("RGB"), (i * 260, 0))
    return sheet.resize((sheet.width * 2, sheet.height * 2), Image.Resampling.NEAREST)


TOWN_SHOTS = ("17-00", "0B-00", "16-00", "0F-00", "00-01", "09-01", "05-01", "01-00")
DUNGEON_SHOTS = ("34-00", "36-01", "2F-00", "43-00", "46-00", "31-02", "48-01", "2D-00")


def environment_towns_figure(folder, names=TOWN_SHOTS):
    """DQ5 에 넣은 맵 여덟 곳의 MesenCE 도착 화면을 4×2 로 2배. 화면은
    dq4environmentromcheck.py 가 남긴 <맵>/<맵>.png 다. 없으면 None."""
    paths = [folder / name / f"{name}.png" for name in names]
    if not all(path.exists() for path in paths):
        return None
    sheet = Image.new("RGB", (4 * 260 - 4, 2 * 228 - 4), (24, 24, 24))
    for i, path in enumerate(paths):
        with Image.open(path) as shot:
            sheet.paste(shot.convert("RGB"), ((i % 4) * 260, (i // 4) * 228))
    return sheet.resize((sheet.width * 2, sheet.height * 2), Image.Resampling.NEAREST)


FIELD_VIEWS = ("castle", "imuru", "bridge", "desert", "reef")
# 세계 1(FC 필드 1)과 세계 2(FC 필드 3)의 dq4fieldcheck 그림 장면.
WORLD12_VIEWS = ("w1-gfx-town", "w1-gfx-tower", "w1-gfx-cave", "w2-gfx-castle", "w2-gfx-shrine", "w2-gfx-palace")


def field_gfx_figure(folder, scenes=tuple(f"gfx-{name}" for name in FIELD_VIEWS)):
    """DQ4 그림으로 바꾼 필드의 MesenCE 화면(dq4fieldcheck 의 그림 장면)을 3×2 로 2배. 화면은
    dq4fieldcheck.py --out work/dq4-fieldcheck 가 남긴 <장면>/end.png 다. 없으면 None."""
    paths = [folder / scene / "end.png" for scene in scenes]
    if not all(path.exists() for path in paths):
        return None
    sheet = Image.new("RGB", (3 * 260 - 4, 2 * 228 - 4), (24, 24, 24))
    for i, path in enumerate(paths):
        with Image.open(path) as shot:
            sheet.paste(shot.convert("RGB"), ((i % 3) * 260, (i // 3) * 228))
    return sheet.resize((sheet.width * 2, sheet.height * 2), Image.Resampling.NEAREST)


def ruler_figure(folder):
    """dq4fieldtravelcheck 의 ルーラ 목록 화면(<out>/list/end.png)을 2배. 없으면 None."""
    path = folder / "list" / "end.png"
    if not path.exists():
        return None
    with Image.open(path) as shot:
        image = shot.convert("RGB")
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


FONT_SIZES = ("orig", "galmuri11", "galmuri9", "galmuri7")


def font_size_figure(folder):
    """원작 일본어·Galmuri11·9·7 롬의 기록 목록과 이름 입력 화면 위쪽을 가로로 2배.
    work/font-size/list-<이름>.png·name-<이름>.png 는 dq4-menu-format.md 「글꼴」 의 MesenCE 화면이다."""
    paths = [folder / f"{kind}-{name}.png" for kind in ("list", "name") for name in FONT_SIZES]
    if not all(p.exists() for p in paths):
        return None
    sheet = Image.new("RGB", (4 * 260 - 4, 2 * 124 - 4), (24, 24, 24))
    for i, path in enumerate(paths):
        with Image.open(path) as shot:
            sheet.paste(shot.convert("RGB").crop((0, 8, 256, 128)), ((i % 4) * 260, (i // 4) * 124))
    return sheet.resize((sheet.width * 2, sheet.height * 2), Image.Resampling.NEAREST)


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
        environment_field_figure(ROOT / "rom" / "dq4.nes").save(output / "dq4-environment-field.webp", lossless=True)
    for name, image in images.items():
        scale = 1 if name == "map" else 3
        preview = image.convert("RGBA").resize(
            (image.width * scale, image.height * scale), Image.Resampling.NEAREST
        )
        preview.save(output / f"dq4-graphics-{name}.webp", lossless=True)
    rom_shots = environment_rom_figure(ROOT / "work" / "dq4-environment-rom" / "check")
    if rom_shots is None:
        print("work/dq4-environment-rom/check 에 게임 화면이 없어 dq4-environment-rom.webp 는 건너뜀")
    else:
        rom_shots.save(output / "dq4-environment-rom.webp", lossless=True)
    towns = environment_towns_figure(ROOT / "work" / "dq4-environment-rom" / "check")
    if towns is None:
        print("work/dq4-environment-rom/check 에 게임 화면이 없어 dq4-environment-towns.webp 는 건너뜀")
    else:
        towns.save(output / "dq4-environment-towns.webp", lossless=True)
    dungeons = environment_towns_figure(ROOT / "work" / "dq4-environment-rom" / "check", DUNGEON_SHOTS)
    if dungeons is not None:
        dungeons.save(output / "dq4-environment-dungeons.webp", lossless=True)
    field_gfx = field_gfx_figure(ROOT / "work" / "dq4-fieldcheck")
    if field_gfx is None:
        print("work/dq4-fieldcheck 에 필드 화면이 없어 dq4-field-gfx.webp 는 건너뜀")
    else:
        field_gfx.save(output / "dq4-field-gfx.webp", lossless=True)
    worlds = field_gfx_figure(ROOT / "work" / "dq4-fieldcheck", WORLD12_VIEWS)
    if worlds is None:
        print("work/dq4-fieldcheck 에 세계 1·2 화면이 없어 dq4-field-worlds12.webp 는 건너뜀")
    else:
        worlds.save(output / "dq4-field-worlds12.webp", lossless=True)
    ruler = ruler_figure(ROOT / "work" / "dq4-travelcheck")
    if ruler is None:
        print("work/dq4-travelcheck 에 ルーラ 목록 화면이 없어 dq4-field-ruler.webp 는 건너뜀")
    else:
        ruler.save(output / "dq4-field-ruler.webp", lossless=True)
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
    sizes = font_size_figure(ROOT / "work" / "font-size")
    if sizes is not None:
        sizes.save(output / "dq4-font-size.webp", lossless=True)
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
