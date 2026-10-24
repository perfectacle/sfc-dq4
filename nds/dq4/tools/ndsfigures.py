"""nds 트랙 일지 그림. 롬을 work/nds/ 에 푼 뒤 돌린다.

  uv run --locked krpatch nds unpack rom/dq4ds.nds work/nds/jp
  uv run --locked krpatch nds unpack rom/dq4ds-kr.nds work/nds/kr
  uv run --locked python nds/dq4/tools/ndsfigures.py
"""
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ndsfont  # noqa: E402
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


def main():
    os.makedirs(OUT, exist_ok=True)
    kr_glyphs()


if __name__ == '__main__':
    main()
