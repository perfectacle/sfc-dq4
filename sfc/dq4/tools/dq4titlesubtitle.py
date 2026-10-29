"""타이틀 부제 「인도받은 자들」을 Galmuri9 로 다시 찍고, 좌우 문양을 대칭으로 그린다.

원래 부제는 이미지 생성 그림을 256×224 로 줄인 글자라 획이 뭉개져 있었다. 글자는 Galmuri v2.40.4(SIL OFL 1.1)
Galmuri9 BDF 를 DQ4_GALMURI 폴더에서 읽는다(저장소에 넣지 않음). 결과 `dq4art/title-animation/title-subtitle.png` 는
커밋해 두고 dq4titlelayers.py 가 읽으므로, 타이틀 빌드에는 글꼴이 필요 없다.
"""

import argparse
import hashlib
import os
from pathlib import Path

import numpy as np
from PIL import Image

from dq4menupatch import load_bdf
from dq4titleanimation import ART

TEXT = '인도받은 자들'
FONT = ('Galmuri9.bdf', 'cc9b6d6f660d8391016be7691b3fc3f864bfa3b095f67bc5e830e9b03ce42162')
OUTPUT = ART / 'title-subtitle.png'
CLEAR = 255

# Title palette indices shared with the original subtitle and logo.
WHITE, PALE = 97, 98
NAVY = 111
GOLD, AMBER, RIM = 114, 115, 127
RUBY, BLUSH = 124, 119

# The original subtitle was centred here; five rows of sky separate its outline from IV.
CENTER_X = 126
TEXT_TOP = 180
OUTER_X = 69


def text_bitmap(path):
    glyphs = load_bdf(path)
    top = max(g['bbx'][1] + g['bbx'][3] for g in (glyphs[ch] for ch in TEXT))
    pixels, x = set(), 0
    for ch in TEXT:
        g = glyphs[ch]
        w, h, bx, by = g['bbx']
        for i, row in enumerate(g['rows']):
            pixels.update((top - (by + h - 1 - i), x + bx + dx) for dx, bit in enumerate(row) if bit)
        x += g['adv']
    ys, xs = zip(*pixels)
    bitmap = np.zeros((max(ys) - min(ys) + 1, max(xs) - min(xs) + 1), dtype=bool)
    for y, dx in pixels:
        bitmap[y - min(ys), dx - min(xs)] = True
    return bitmap


def embolden(bitmap):
    # Galmuri9 strokes are one pixel wide, too thin beside the logo; widen each to the right unless that closes a one-pixel gap.
    padded = np.pad(bitmap, ((0, 0), (0, 1)))
    left = np.zeros_like(padded)
    left[:, 1:] = padded[:, :-1]
    right = np.zeros_like(padded)
    right[:, :-1] = padded[:, 1:]
    return padded | (left & ~right)


def grow(mask):
    padded = np.pad(mask, 1)
    out = mask.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            out |= padded[1 + dy:padded.shape[0] - 1 + dy, 1 + dx:padded.shape[1] - 1 + dx]
    return out


def diamond(art, cx, cy, radius, inside):
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if abs(dx) + abs(dy) == radius:
                art[cy + dy, cx + dx] = RIM
            elif abs(dx) + abs(dy) < radius:
                art[cy + dy, cx + dx] = inside(dx, dy)


def draw(bitmap):
    height, width = bitmap.shape
    left = CENTER_X - width // 2
    letters = np.zeros((224, 256), dtype=bool)
    letters[TEXT_TOP:TEXT_TOP + height, left:left + width] = bitmap
    art = np.full(letters.shape, CLEAR, dtype=np.uint8)
    art[grow(letters)] = NAVY
    art[letters] = WHITE
    art[letters & (np.arange(224)[:, None] == TEXT_TOP + height - 1)] = PALE

    # Draw the left ornament only, then mirror it about the text so both sides match pixel for pixel.
    half = np.full_like(art, CLEAR)
    middle = TEXT_TOP + height // 2
    gem = left - 5
    half[middle - 1, OUTER_X + 3:gem - 2] = RIM
    half[middle, OUTER_X + 3:gem - 2] = GOLD
    half[middle + 1, OUTER_X + 3:gem - 2] = RIM
    diamond(half, OUTER_X + 2, middle, 2, lambda dx, dy: AMBER)
    diamond(half, gem, middle, 3, lambda dx, dy: GOLD if (dx, dy) == (-1, -1) else BLUSH if dx + dy < 0 else RUBY)
    axis = 2 * left + width - 1
    xs = np.flatnonzero((half != CLEAR).any(axis=0))
    half[:, axis - xs] = half[:, xs]
    return np.where(half != CLEAR, half, art)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, default=OUTPUT)
    args = parser.parse_args()
    folder = os.environ.get('DQ4_GALMURI')
    if not folder:
        raise SystemExit('DQ4_GALMURI 에 Galmuri BDF 가 든 폴더를 주세요(sfc/dq4/docs/dq4-menu-format.md)')
    path = Path(folder) / FONT[0]
    if hashlib.sha256(path.read_bytes()).hexdigest() != FONT[1]:
        raise SystemExit(f'{path}: Galmuri v2.40.4 의 {FONT[0]} 가 아님')
    Image.fromarray(draw(embolden(text_bitmap(path))), 'L').save(args.out, optimize=True)
    print(args.out)


if __name__ == '__main__':
    main()
