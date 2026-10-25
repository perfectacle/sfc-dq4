"""nds 트랙 일지 그림. 롬을 work/nds/ 에 푼 뒤 돌린다.

  uv run --locked krpatch nds unpack rom/dq4ds.nds work/nds/jp
  uv run --locked krpatch nds unpack rom/dq4ds-kr.nds work/nds/kr
  uv run --locked python nds/dq4/tools/ndsfigures.py
"""
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ndsgfx  # noqa: E402
import ndskr  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
OUT = os.path.join(ROOT, 'nds', 'dq4', 'images')
WORK = os.path.join(ROOT, 'work', 'nds')


def kr_glyphs(start=50, count=32, scale=3):
    """한글판에서 바뀐 글리프를 코드 순으로: 윗줄 일본판, 아랫줄 한글판. 58번째부터 KS 순서(가각간…)가 시작된다."""
    jp, kr = ndskr.fonts(os.path.join(WORK, 'jp'), 'zen12'), ndskr.fonts(os.path.join(WORK, 'kr'), 'zen12')
    codes = ndskr.changed(jp, kr)[start:start + count]
    cw, ch = jp.cell_w + 2, jp.cell_h + 2
    img = Image.new('RGB', (count * cw, 2 * ch + 2), (255, 255, 255))
    for row, font in enumerate((jp, kr)):
        for k, code in enumerate(codes):
            for y, line in enumerate(font.glyph(font.cmap[code])):
                for x, v in enumerate(line):
                    if v:
                        img.putpixel((k * cw + 1 + x, row * (ch + 2) + 1 + y), (32, 32, 48))
    img = img.resize((img.width * scale, img.height * scale), Image.NEAREST)
    img.save(os.path.join(OUT, 'nds-kr-glyphs.webp'), lossless=True)


def _gfx(rel):
    with open(os.path.join(WORK, 'jp', 'data', 'data', rel), 'rb') as f:
        b = f.read()
    return ndsgfx.unlz(b) if rel.endswith('.lz') else b


def _on_grey(img):
    bg = Image.new('RGBA', img.size, (64, 66, 72, 255))
    bg.alpha_composite(img.convert('RGBA'))
    return bg


def gfx_dssa():
    """몬스터 부품 아틀라스(왼쪽)와 DSSA 첫 프레임으로 조립한 모습(오른쪽, 2배)."""
    atlas = ndsgfx.texture_object_image(ndsgfx.texture_object(_gfx('MONSTER/m058.tex.lz')))
    anm = _gfx('MONSTER/m058.anm.lz')
    eo, es = ndsgfx.pack_entries(anm)[0]
    cells, frames = ndsgfx.dssa(anm, eo, es)
    pose, _ = ndsgfx.dssa_frame(atlas, cells, frames[0])
    pose = pose.resize((pose.width * 2, pose.height * 2), Image.NEAREST)
    out = Image.new('RGBA', (256 + 16 + pose.width, max(256, pose.height)), (40, 42, 48, 255))
    out.alpha_composite(_on_grey(atlas), (0, 0))
    out.alpha_composite(_on_grey(pose), (272, (out.height - pose.height) // 2))
    out.save(os.path.join(OUT, 'nds-graphics-dssa.webp'), lossless=True)


def gfx_render():
    """실내 맵 mai1f2 를 FMAP 배치까지 넣어 위에서 본 렌더링."""
    b = _gfx('MAP/mai1f2.lz')
    ents = ndsgfx.pack_entries(b)
    img = ndsgfx.render_top(b, ents[0][0], ndsgfx.fmap_instances(b, ents[1][0]), max_scale=48)
    _on_grey(img).save(os.path.join(OUT, 'nds-graphics-render.webp'), lossless=True)


def main():
    os.makedirs(OUT, exist_ok=True)
    kr_glyphs()
    gfx_dssa()
    gfx_render()


if __name__ == '__main__':
    main()
