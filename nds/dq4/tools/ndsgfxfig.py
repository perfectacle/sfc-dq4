"""그래픽 형식 문서(nds/dq4/docs/graphics-format.md)의 그림을 롬에서 다시 만든다.

    uv run --locked krpatch nds unpack rom/dq4ds.nds work/nds/jp
    uv run --locked python nds/dq4/tools/ndsgfxfig.py
"""
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ndsgfx as g  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
OUT = os.path.join(ROOT, "nds", "dq4", "images")
DATA = os.path.join(ROOT, "work", "nds", "jp", "data", "data")


def read(rel):
    with open(os.path.join(DATA, rel), "rb") as f:
        b = f.read()
    return g.unlz(b) if rel.endswith(".lz") else b


def on_grey(img, size=None):
    bg = Image.new("RGBA", size or img.size, (64, 66, 72, 255))
    bg.alpha_composite(img.convert("RGBA"))
    return bg


def flip_figure():
    """m004 대기 동작 첫 프레임: 셀 플래그를 무시한 조립(왼쪽)과 0x1000 을 좌우 뒤집기로 쓴 조립(오른쪽), 4배."""
    atlas = g.texture_object_image(g.texture_object(read("MONSTER/m004.tex.lz")))
    anm = read("MONSTER/m004.anm.lz")
    eo, es = g.pack_entries(anm)[0]
    cells, frames = g.dssa(anm, eo, es)
    plain = [dict(r, flags=0) for r in frames[0]]
    a, _ = g.dssa_frame(atlas, cells, plain)
    b, _ = g.dssa_frame(atlas, cells, frames[0])
    w, h = max(a.width, b.width), max(a.height, b.height)
    out = Image.new("RGBA", (2 * w + 8, h), (40, 42, 48, 255))
    out.alpha_composite(on_grey(a, (w, h)), (0, 0))
    out.alpha_composite(on_grey(b, (w, h)), (w + 8, 0))
    out.resize((out.width * 4, out.height * 4), Image.NEAREST).save(
        os.path.join(OUT, "nds-gfx-flip.webp"), lossless=True)


def alpha_figure():
    """m133 주문 동작(칸 7) 프레임 3·11. 0x4000 부품을 무시한 조립(위)과 A3I5·덧붙은 팔레트로 그린 조립(아래), 2배."""
    t = g.texture_object(read("MONSTER/m133.tex.lz"))
    atlas, alpha = g.texture_object_image(t), g.translucent_atlas(t)
    anm = read("MONSTER/m133.anm.lz")
    eo, es = g.pack_entries(anm)[7]
    cells, frames = g.dssa(anm, eo, es)
    shots = [[g.dssa_frame(atlas, cells, frames[i], alpha_atlas=a) for i in (3, 11)] for a in (None, alpha)]
    x0 = min(o[0] for row in shots for _, o in row)
    y0 = min(o[1] for row in shots for _, o in row)
    w = max(o[0] + im.width for row in shots for im, o in row) - x0
    h = max(o[1] + im.height for row in shots for im, o in row) - y0
    out = Image.new("RGBA", (2 * w + 8, 2 * h + 8), (40, 42, 48, 255))
    for r, row in enumerate(shots):
        for c, (im, o) in enumerate(row):
            cell = Image.new("RGBA", (w, h), (64, 110, 64, 255))
            cell.alpha_composite(im, (o[0] - x0, o[1] - y0))
            out.alpha_composite(cell, (c * (w + 8), r * (h + 8)))
    out.resize((out.width * 2, out.height * 2), Image.NEAREST).save(
        os.path.join(OUT, "nds-gfx-alpha.webp"), lossless=True)


def bca_figure():
    """피사로 3D 모델(CHR/pisaro.nsbmd)을 BCA0 동작 pisaro_1 로 움직인 프레임 6장(앞에서 본 직교)."""
    mdl, bca = read("CHR/pisaro.nsbmd"), read("CHR/pisaro_1.nsbca")
    frames, _ = g.model_anim_frames(mdl, bca, 0, step=28, max_frames=6, scale=60)
    w, h = frames[0].size
    out = Image.new("RGBA", (w * len(frames), h), (64, 66, 72, 255))
    for k, f in enumerate(frames):
        out.alpha_composite(f, (k * w, 0))
    out.save(os.path.join(OUT, "nds-gfx-bca.webp"), lossless=True)


def largemap_figure():
    """FIELD/large/largemap.bin(32×32 타일로 저장한 1024×1024 8bpp)을 1/4 로 줄인 것."""
    import numpy as np
    pal = np.array(g.texture_object(read("FIELD/large/largemap.tex"))["pal"], np.uint8)
    d = np.frombuffer(read("FIELD/large/largemap.bin"), np.uint8)
    img = Image.fromarray(pal[d.reshape(32, 32, 32, 32).transpose(0, 2, 1, 3).reshape(1024, 1024)])
    img.resize((256, 256), Image.LANCZOS).save(os.path.join(OUT, "nds-gfx-largemap.webp"), quality=85)


def world_figure():
    """FIELD/bin/worldmap.bin 을 WTEX 표와 SDAT 기호로 그린 필드 일부(가로세로 32칸, 512×512)."""
    import numpy as np
    ft = g.texture_object(read("FIELD/field.tex"))
    pal = ft["pal"]
    f_img = np.asarray(g.texture_object_image(ft, transparent0=False).convert("RGB"))
    pb = read("FIELD/texture/pattern8.pack")
    eo, es = g.pack_entries(pb)[0]
    p_img = np.asarray(g.texture(pb[eo:eo + es], 4, 256, es // 256, pal, False).convert("RGB"))
    sb = read("FIELD/texture/pattern24.pack")
    eo, es = g.pack_entries(sb)[0]
    s_img = np.asarray(g.texture(sb[eo:eo + es], 4, 256, 16, pal, False).convert("RGB"))
    b = read("FIELD/bin/worldmap.bin")
    pictures = [g.texture_object_image(t) for t in g.texture_pack(read("FIELD/symbol/symbol.pack"))]
    img = g.render_field(g.wmap(b), g.wtex(b), f_img, p_img, s_img, g.sdat(b), pictures)
    img.crop((1296, 1296, 1808, 1808)).convert("RGB").save(os.path.join(OUT, "nds-gfx-world.webp"), quality=85)


def effect_figure():
    """3D 효과 effect010(ヒャド 계열)을 BCA0·BTA0·BMA0 로 재생한 프레임 6장(앞에서 본 직교, 반투명 섞기)."""
    b = read("EFFECT/effect010.lz")
    ents = g.pack_entries(b)

    def pick(tag):
        return next((b[eo:eo + es] for eo, es in ents if es and b[eo:eo + 4] == tag), None)
    frames, _ = g.model_anim_frames(pick(b"BMD0"), pick(b"BCA0"), 0, step=10, max_frames=6, blend=True,
                                    srt=pick(b"BTA0"), mat=pick(b"BMA0"), scale=60)
    w, h = frames[0].size
    out = Image.new("RGBA", (w * len(frames), h), (24, 26, 40, 255))
    for k, f in enumerate(frames):
        out.alpha_composite(f, (k * w, 0))
    out.save(os.path.join(OUT, "nds-gfx-effect.webp"), lossless=True)


def main():
    os.makedirs(OUT, exist_ok=True)
    flip_figure()
    alpha_figure()
    bca_figure()
    largemap_figure()
    world_figure()
    effect_figure()


if __name__ == "__main__":
    main()
