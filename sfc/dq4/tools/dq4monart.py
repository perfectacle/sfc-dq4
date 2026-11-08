"""2장 전투 몬스터 그림: NDS 몬스터 그림(자원 저장소 nds/dq4/monster/pose/mNNN.png)을 OBJ 팔레트 15색으로 줄인다.
형식 문서 sfc/dq4/docs/dq4-sprite-format.md 「2장 전투 몬스터 그림」.

색은 중앙값 자르기처럼 모든 색을 한 공간에서 묶지 않고, 사람이 팔레트를 고르듯 색상군(같은 색조의 색 무리, 무채색은
따로)을 먼저 나눈 뒤 색상군마다 칸을 나눠 준다. 색상군은 모두 한 칸 이상 받아 작은 빨간 볏이 흰색이 되는 일이 없고,
픽셀은 제 색상군 안의 색으로만 옮겨 초록 얼굴이 파래지지 않는다. 나머지 칸은 오차를 가장 많이 줄이는 색상군에 하나씩
더 준다. 색은 그 무리에 실제로 있는 NDS 색 가운데 무리의 가운데에 가장 가까운 것으로 고른다.

  python sfc/dq4/tools/dq4monart.py sheet -o work/monster-review [--only 1,7]
"""
import argparse
import colorsys
import math
import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

MAX_COLORS = 15                  # OBJ 팔레트 1~15, 0 은 투명
HUE_GAP = 15.0                   # 색조가 이만큼(도) 벌어지면 다른 색상군
GRAY_CHROMA = 12.0               # Lab 채도가 이보다 낮으면 무채색 군
WEIGHT = 0.5                     # 오차에서 개수의 지수. 작을수록 작은 무늬를 살린다
SCALE = 3
HUE_WEIGHT = 2.0
TINY = 0.005                    # 픽셀이 이 몫보다 적은 색상군은 가장 가까운 군에 붙인다(점 몇 개가 칸을 차지하지 않게)

# (FC 몬스터, NDS 그림 번호, 무리). 무리: reduce = NDS 색이 15 를 넘음, same = DQ5 에 같은 이름이 있음, fit = 15색 이하.
# FC → NDS 짝은 nds/dq4/tools/ndsparam.py monsters 의 FC 열
TARGETS = (
    (0x01, 1, 'reduce'), (0x02, 2, 'reduce'), (0x03, 4, 'reduce'), (0x08, 5, 'reduce'), (0x0C, 27, 'reduce'),
    (0x18, 23, 'reduce'), (0x1A, 21, 'reduce'), (0x1C, 38, 'reduce'), (0x1D, 22, 'reduce'), (0x20, 85, 'reduce'),
    (0x25, 55, 'reduce'), (0x26, 74, 'reduce'), (0x28, 17, 'reduce'), (0x2A, 33, 'reduce'), (0x2C, 58, 'reduce'),
    (0x33, 47, 'reduce'), (0x36, 63, 'reduce'), (0x38, 42, 'reduce'), (0x3E, 44, 'reduce'), (0x40, 71, 'reduce'),
    (0x48, 61, 'reduce'), (0x12, 35, 'reduce'), (0xAF, 175, 'reduce'), (0xB0, 176, 'reduce'), (0xB1, 177, 'reduce'),
    (0xBA, 170, 'reduce'),
    (0x00, 0, 'same'), (0x0B, 8, 'same'), (0x11, 14, 'same'), (0x14, 12, 'same'), (0x46, 34, 'same'),
    (0x5C, 68, 'same'),
    (0x05, 182, 'fit'), (0x07, 3, 'fit'), (0x0D, 11, 'fit'), (0x0E, 13, 'fit'), (0x1F, 24, 'fit'), (0x24, 39, 'fit'),
    (0x2E, 65, 'fit'), (0x4D, 19, 'fit'), (0xB2, 178, 'fit'),
)
# 사람이 꼭 남기라고 고른 색(NDS 그림 번호 → RGB): 자동으로 고르면 무리 가운데의 어두운 색에 묻히는 밝은 면
PINS = {
    177: ('F7DE63', 'F7D69C', 'E7AD63'),    # 비비안: 금발, 피부 밝은 면과 그늘
}
# 시안에서 눈으로 본 결과가 원본과 달라 보이는 것: 번호 → 무엇이
WATCH = {}
GROUP_LABEL = {'reduce': '15색 넘음', 'same': 'DQ5 와 같은 이름', 'fit': '15색 이하'}


def pose_path(nds):
    return Path(os.environ['DQ4_ASSETS']) / 'nds' / 'dq4' / 'monster' / 'pose' / f'm{nds:03d}.png'


def korean_names():
    out = {}
    tsv = Path(__file__).resolve().parents[3] / 'nds' / 'dq4' / 'tables' / 'adopt.tsv'
    for line in tsv.read_text(encoding='utf-8').splitlines()[1:]:
        cols = line.split('\t')
        if cols[0] == '몬스터':
            out[int(cols[1])] = (cols[2], cols[3])
    return out


def snap(rgb):
    """BGR555 로 갈 수 있는 색(채널마다 위 5비트, 아래 3비트는 위 3비트를 되풀이)."""
    return tuple((c >> 3) << 3 | (c >> 5) for c in rgb)


def lab(rgb):
    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(c) for c in rgb)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883
    f = lambda t: t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116  # noqa: E731
    return 116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z))


def dist2(p, q):
    """Lab 거리의 제곱. 색조(a·b)를 밝기보다 무겁게 재 같은 색상군 안에서도 금발·피부·빨간 옷이 한 색으로 뭉치지 않게 한다."""
    return (p[0] - q[0]) ** 2 + HUE_WEIGHT * ((p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2)


def colors_of(img):
    """불투명 픽셀의 색 → 개수. 반투명은 알파 128 을 기준으로 가른다."""
    counts = {}
    for px in img.convert('RGBA').get_flattened_data():
        if px[3] >= 128:
            c = snap(px[:3])
            counts[c] = counts.get(c, 0) + 1
    return counts


def families(counts):
    """색상군: [[색, ...], ...]. 무채색 한 군, 유채색은 Lab 색조 순으로 늘어놓아 HUE_GAP 보다 벌어진 곳에서 끊는다."""
    gray, hued = [], []
    for c in counts:
        L, a, b = lab(c)
        if math.hypot(a, b) < GRAY_CHROMA:
            gray.append(c)
        else:
            hued.append((math.degrees(math.atan2(b, a)) % 360, c))
    hued.sort()
    groups = []
    if hued:
        gaps = [((hued[(i + 1) % len(hued)][0] - h) % 360, i) for i, (h, _) in enumerate(hued)]
        start = (max(gaps)[1] + 1) % len(hued)      # 가장 넓은 틈에서 원을 편다
        ring = hued[start:] + hued[:start]
        cur = [ring[0][1]]
        for (h0, _), (h1, c) in zip(ring, ring[1:]):
            if (h1 - h0) % 360 > HUE_GAP:
                groups.append(cur)
                cur = []
            cur.append(c)
        groups.append(cur)
    if gray:
        groups.append(gray)
    return groups


def kmeans(cols, counts, k, pins=()):
    """한 색상군을 k 무리로: 고른 색 k 개와 오차(Σ 개수^WEIGHT × ΔE²). pins 는 꼭 남길 색(무리 가운데가 움직이지 않음)."""
    pts = [(lab(c), counts[c] ** WEIGHT, c) for c in cols]
    if k >= len(pts):
        return list(cols), 0.0
    pts.sort(key=lambda p: p[0][0])
    free = [p for p in pts if p[2] not in pins]
    n = k - len(pins)
    centers = [lab(c) for c in pins] + [free[round((i + 0.5) * len(free) / n - 0.5)][0] for i in range(n)]
    for _ in range(20):
        buckets = [[] for _ in range(k)]
        for p in pts:
            buckets[min(range(k), key=lambda j: dist2(p[0], centers[j]))].append(p)
        new = []
        for j, bk in enumerate(buckets):
            if not bk or j < len(pins):
                new.append(centers[j])
                continue
            w = sum(p[1] for p in bk)
            new.append(tuple(sum(p[0][i] * p[1] for p in bk) / w for i in range(3)))
        if new == centers:
            break
        centers = new
    chosen = []
    chosen = list(pins)
    for j, bk in enumerate(buckets):
        if bk and j >= len(pins):
            chosen.append(min(bk, key=lambda p: sum(q[1] * dist2(p[0], q[0]) for q in bk))[2])
    chosen = list(dict.fromkeys(chosen))
    err = sum(p[1] * min(dist2(p[0], lab(c)) for c in chosen) for p in pts)
    return chosen, err


def palette(counts, limit=MAX_COLORS, pins=()):
    """15색 팔레트 [(색상군 번호, 색), ...] 와 원래 색 → 고른 색. pins 는 사람이 꼭 남기라고 고른 NDS 색."""
    groups = families(counts)
    total = sum(counts.values())
    share = lambda g: sum(counts[c] for c in g) / total  # noqa: E731
    while len(groups) > limit or (len(groups) > 1 and min(map(share, groups)) < TINY):      # 색상군이 칸보다 많으면 개수가 가장 적은 군을 색조가 가까운 이웃에 붙인다
        small = min(range(len(groups)), key=lambda i: sum(counts[c] for c in groups[i]))
        g = groups.pop(small)
        near = min(range(len(groups)), key=lambda i: min(dist2(lab(a), lab(b)) for a in g for b in groups[i]))
        groups[near] += g
    gp = [tuple(c for c in pins if c in g) for g in groups]
    k = [max(1, len(p)) for p in gp]
    fits = [kmeans(g, counts, n, p) for g, n, p in zip(groups, k, gp)]
    while sum(k) < limit:
        best = None
        for i, g in enumerate(groups):
            if k[i] >= len(g):
                continue
            nxt = kmeans(g, counts, k[i] + 1, gp[i])
            gain = fits[i][1] - nxt[1]
            if best is None or gain > best[0]:
                best = (gain, i, nxt)
        if best is None:
            break
        _, i, nxt = best
        k[i] += 1
        fits[i] = nxt
    pal, mapping = [], {}
    for i, (g, (chosen, _)) in enumerate(zip(groups, fits)):
        pal += [(i, c) for c in chosen]
        for c in g:
            mapping[c] = min(chosen, key=lambda q: dist2(lab(c), lab(q)))
    pal.sort(key=lambda p: (p[0], lab(p[1])[0]))
    return pal, mapping


def reduce(img, nds=None):
    """NDS 그림 → (15색 RGBA 그림, 팔레트 [(색상군, 색)], 원래 색 수). nds 를 주면 PINS 의 색을 남긴다."""
    src = img.convert('RGBA')
    counts = colors_of(src)
    pins = tuple(snap(bytes.fromhex(h)) for h in PINS.get(nds, ()))
    missing = [c for c in pins if c not in counts]
    if missing:
        raise ValueError(f'm{nds:03d}: 남길 색 {missing} 이 그림에 없음')
    pal, mapping = palette(counts, pins=pins)
    out = Image.new('RGBA', src.size, (0, 0, 0, 0))
    out.putdata([(*mapping[snap(p[:3])], 255) if p[3] >= 128 else (0, 0, 0, 0)
                 for p in src.get_flattened_data()])
    return out, pal, len(counts)


def _font(size):
    for f in ('/System/Library/Fonts/AppleSDGothicNeo.ttc', '/Library/Fonts/Arial Unicode.ttf'):
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def sheet(out_dir, only=None):
    """몬스터마다 [NDS 원본] [15색 결과] [팔레트 칩] 을 3배로 놓은 시트. 번호는 TARGETS 차례 1부터."""
    names = korean_names()
    font, small = _font(16), _font(12)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for no, (fc, nds, grp) in enumerate(TARGETS, 1):
        if only and no not in only:
            continue
        src = Image.open(pose_path(nds)).convert('RGBA')
        red, pal, n = reduce(src, nds)
        rows.append((no, fc, nds, grp, src, red, pal, n))
    bg, ink = (232, 232, 236), (20, 20, 24)
    pages = []
    per_page = 14
    for p0 in range(0, len(rows), per_page):
        chunk = rows[p0:p0 + per_page]
        heights = [max(r[4].height * SCALE, 60) + 34 for r in chunk]
        W = 1100
        page = Image.new('RGB', (W, sum(heights) + 10), bg)
        d = ImageDraw.Draw(page)
        y = 5
        for (no, fc, nds, grp, src, red, pal, n), h in zip(chunk, heights):
            jp, ko = names.get(nds, ('?', '?'))
            d.text((8, y), f'{no}번  {ko} ({jp})  FC {fc:02X} · NDS m{nds:03d} · {GROUP_LABEL[grp]}', font=font, fill=ink)
            if no in WATCH:
                d.text((W - 330, y), f'주의: {WATCH[no]}', font=font, fill=(200, 30, 30))
            yy = y + 24
            x = 8
            for im in (src, red):
                big = im.resize((im.width * SCALE, im.height * SCALE), Image.NEAREST)
                d.rectangle((x - 1, yy - 1, x + big.width, yy + big.height), outline=(160, 160, 170))
                page.paste(big, (x, yy), big)
                x += big.width + 24
            x = max(x, 520)
            d.text((x, yy), f'NDS {n}색 → {len(pal)}색', font=small, fill=ink)
            fam = None
            cx = x
            for gi, c in pal:
                if fam is not None and gi != fam:
                    cx += 8
                fam = gi
                d.rectangle((cx, yy + 18, cx + 22, yy + 40), fill=c, outline=(0, 0, 0))
                cx += 26
            d.text((x, yy + 46), '칩 사이 틈 = 색상군 경계', font=small, fill=(110, 110, 120))
            y += h
            d.line((0, y - 3, W, y - 3), fill=(190, 190, 200))
        path = out_dir / f'sheet-{len(pages) + 1}.png'
        page.save(path)
        pages.append(path)
    return pages, rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('sheet')
    s.add_argument('-o', '--out', type=Path, required=True)
    s.add_argument('--only', default='')
    a = ap.parse_args(argv)
    only = {int(x) for x in a.only.split(',') if x}
    pages, rows = sheet(a.out, only)
    names = korean_names()
    for no, fc, nds, grp, _, _, pal, n in rows:
        print(f'{no:2d} {names.get(nds, ("?", "?"))[1]} FC {fc:02X} m{nds:03d} {n}->{len(pal)}')
    for p in pages:
        print(p)


if __name__ == '__main__':
    sys.exit(main())
