"""분석 문서(docs/)에 넣는 그림을 다시 만든다. 원본 롬과 MesenCE 덤프(work/)가 필요하다.

사용: python tools/figures.py   (Pillow 필요, 저장소 최상위에서)

입력 덤프를 만드는 명령은 docs/journal/ 의 해당 날짜 일지에 있다.
"""
import glob
import os
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(__file__))
from dq5map import Decoder, Rom, map_pointer, render  # noqa: E402

OUT = 'docs/images'
SLOT = 0xBE


def save(img, name):
    path = os.path.join(OUT, name)
    img.save(path, 'WEBP', lossless=True)
    print(path, img.size)


def decoded(rom, bc, bd, cgram, stop_after=None, trace=None):
    dec = Decoder(rom, SLOT)
    w, h, buf, _ = dec.decode(map_pointer(rom, bc, bd), trace=trace, stop_after=stop_after)
    tmp = 'work/_fig.png'
    render(rom, dec, w, h, buf, cgram, tmp)
    return Image.open(tmp).convert('RGB'), w, h


def find_view(full, shot):
    """게임 화면(256x224)이 디코더 출력의 어디에 해당하는지 찾는다. 인물 스프라이트를 고려해 일치 픽셀 수로 고른다."""
    fw, fh = full.size
    a, b = full.load(), shot.convert('RGB').load()

    def score(ox, oy, step):
        return sum(1 for y in range(3, 224, step) for x in range(3, 256, step) if a[ox + x, oy + y] == b[x, y])

    # 8픽셀 격자로 대강 찾고, 카메라가 타일 경계에 맞지 않을 수 있으니 주변을 1픽셀씩 다시 본다.
    _, cx, cy = max((score(ox, oy, 8), ox, oy)
                    for oy in range(0, fh - 224 + 1, 8) for ox in range(0, fw - 256 + 1, 8))
    cand = [(score(ox, oy, 4), ox, oy)
            for oy in range(max(0, cy - 8), min(fh - 224, cy + 8) + 1)
            for ox in range(max(0, cx - 8), min(fw - 256, cx + 8) + 1)]
    hit, ox, oy = max(cand)
    return hit, ox, oy, len(range(3, 224, 4)) * len(range(3, 256, 4))


def label(img, text):
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, 8 + 6 * len(text), 14), fill=(0, 0, 0))
    d.text((4, 2), text, fill=(255, 255, 0))


def fig_compare(rom):
    """게임 화면과 디코더로 그린 맵 전체를 나란히 놓고, 화면이 맵의 어디인지 표시한다."""
    cg = open('work/snap2/c00600.bin', 'rb').read()
    full, _, _ = decoded(rom, 2, 6, cg)
    shot = Image.open('work/snap2/s00600.png').convert('RGB')
    hit, ox, oy, n = find_view(full, shot)
    print(f'  view at ({ox},{oy}), {hit}/{n} sample pixels match')
    marked = full.copy()
    ImageDraw.Draw(marked).rectangle((ox, oy, ox + 255, oy + 223), outline=(255, 64, 64), width=2)
    out = Image.new('RGB', (shot.width + 16 + marked.width, max(shot.height, marked.height)), (24, 24, 24))
    out.paste(shot, (0, 0))
    out.paste(marked, (shot.width + 16, 0))
    label(out, 'MesenCE')
    ImageDraw.Draw(out).text((shot.width + 20, 2), 'dq5map.py 02/06', fill=(255, 255, 0))
    save(out, 'dq5-map-0206-compare.webp')


def fig_progress(rom):
    """배경 채우기 직후부터 끝까지, 명령을 처리하며 맵이 채워지는 과정."""
    cg = open('work/snap2/c00600.bin', 'rb').read()
    trace = []
    decoded(rom, 2, 6, cg, trace=trace)
    total = len(trace)
    stages = [0, total // 4, total // 2, total * 3 // 4, total]
    frames = []
    for n in stages:
        img, _, _ = decoded(rom, 2, 6, cg, stop_after=n)
        img = img.resize((img.width // 2, img.height // 2), Image.NEAREST)
        label(img, f'{n}/{total}')
        frames.append(img)
    w, h = frames[0].size
    out = Image.new('RGB', (w * 3 + 16, h * 2 + 8), (24, 24, 24))
    for i, f in enumerate(frames):
        out.paste(f, ((i % 3) * (w + 8), (i // 3) * (h + 8)))
    save(out, 'dq5-map-0206-progress.webp')


def fig_commands(rom):
    """02/07 에서 명령별로 찍힌 자리를 색으로 표시: put(초록), fill(파랑)."""
    cg = open('work/snap2/c01710.bin', 'rb').read()
    trace = []
    img, w, _ = decoded(rom, 2, 7, cg, trace=trace)
    over = Image.new('RGBA', img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    dec = Decoder(rom, SLOT)
    size = (1, 1)
    for _, _, op, args in trace:
        if op == 'block':
            blk = dec.load_block(args[0])
            size = (blk[1], blk[0])
        elif op == 'put':
            x, y = args[0] % w, args[0] // w
            d.rectangle((x * 8, y * 8, (x + size[0]) * 8 - 1, (y + size[1]) * 8 - 1), outline=(0, 255, 0, 255))
        elif op == 'fill':
            (x0, y0), (x1, y1) = (args[0] % w, args[0] // w), (args[1] % w, args[1] // w)
            d.rectangle((x0 * 8, y0 * 8, (x1 + size[0]) * 8 - 1, (y1 + size[1]) * 8 - 1),
                        fill=(64, 128, 255, 48), outline=(64, 160, 255, 255))
    out = Image.alpha_composite(img.convert('RGBA'), over).convert('RGB')
    out = out.resize((out.width * 2, out.height * 2), Image.NEAREST)
    save(out, 'dq5-map-0207-commands.webp')


def fig_transition():
    """맵 전환 전후 30프레임 간격 화면(wsnap.lua, 1560~1770)."""
    files = [f for f in sorted(glob.glob('work/wdump/s[0-9]*.png')) if 1560 <= int(f[-9:-4]) <= 1770]
    ims = [Image.open(f).convert('RGB').resize((128, 112), Image.NEAREST) for f in files]
    out = Image.new('RGB', (128 * len(ims) + 4 * (len(ims) - 1), 112), (24, 24, 24))
    for i, (f, im) in enumerate(zip(files, ims)):
        label(im, f'f{int(f[-9:-4])}')
        out.paste(im, (i * 132, 0))
    save(out, 'dq5-map-transition.webp')


def main():
    os.makedirs(OUT, exist_ok=True)
    rom = Rom(open('rom/dq5.sfc', 'rb').read())
    fig_compare(rom)
    fig_progress(rom)
    fig_commands(rom)
    fig_transition()
    os.remove('work/_fig.png')


if __name__ == '__main__':
    main()
