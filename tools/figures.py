"""분석 문서(docs/)에 넣는 그림을 다시 만든다. 원본 롬과 MesenCE 덤프(work/)가 필요하다.

사용: python tools/figures.py   (Pillow 필요, 저장소 최상위에서)

맵은 롬만으로 그린다(팔레트도 롬). 게임 화면 비교에만 MesenCE 스크린샷이 필요하고,
그 덤프를 만드는 명령은 docs/journal/ 의 해당 날짜 일지에 있다.
"""
import glob
import os
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(__file__))
from dq5map import Decoder, Rom, map_cgram, map_pointer, render  # noqa: E402

OUT = 'docs/images'
SLOT = 0xBE
TMP = 'work/_fig.png'


def save(img, name):
    path = os.path.join(OUT, name)
    img.save(path, 'WEBP', lossless=True)
    print(path, img.size)


def decoded(rom, bc, bd, stop_after=None, trace=None):
    dec = Decoder(rom, SLOT)
    w, h, buf, _ = dec.decode(map_pointer(rom, bc, bd), trace=trace, stop_after=stop_after)
    render(rom, dec, w, h, buf, map_cgram(rom, bc, bd), TMP)
    return Image.open(TMP).convert('RGB'), w, h, buf, dec


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


def label(img, text, xy=(0, 0)):
    d = ImageDraw.Draw(img)
    d.rectangle((xy[0], xy[1], xy[0] + 8 + 6 * len(text), xy[1] + 14), fill=(0, 0, 0))
    d.text((xy[0] + 4, xy[1] + 2), text, fill=(255, 255, 0))


def fig_compare(rom):
    """게임 화면과 디코더로 그린 맵 전체를 나란히 놓고, 화면이 맵의 어디인지 표시한다."""
    full, *_ = decoded(rom, 2, 6)
    shot = Image.open('work/snap2/s00600.png').convert('RGB')
    hit, ox, oy, n = find_view(full, shot)
    print(f'  view at ({ox},{oy}), {hit}/{n} sample pixels match')
    marked = full.copy()
    ImageDraw.Draw(marked).rectangle((ox, oy, ox + 255, oy + 223), outline=(255, 64, 64), width=2)
    out = Image.new('RGB', (shot.width + 16 + marked.width, max(shot.height, marked.height)), (24, 24, 24))
    out.paste(shot, (0, 0))
    out.paste(marked, (shot.width + 16, 0))
    label(out, 'MesenCE')
    label(out, 'dq5map.py 02/06', (shot.width + 16, 0))
    save(out, 'dq5-map-0206-compare.webp')


def fig_progress(rom):
    """배경 채우기 직후부터 끝까지, 명령을 처리하며 맵이 채워지는 과정."""
    trace = []
    decoded(rom, 2, 6, trace=trace)
    total = len(trace)
    frames = []
    for n in [0, total // 4, total // 2, total * 3 // 4, total]:
        img, *_ = decoded(rom, 2, 6, stop_after=n)
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
    trace = []
    img, w, _, _, dec = decoded(rom, 2, 7, trace=trace)
    over = Image.new('RGBA', img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
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


def fig_attributes(rom):
    """02/07 셀 +1 아래 니블(1 초록, 8 빨강, 9 노랑)과 +0 bit3(파란 점)."""
    img, w, h, buf, _ = decoded(rom, 2, 7)
    over = Image.new('RGBA', img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    colors = {1: (0, 255, 0, 70), 8: (255, 0, 0, 110), 9: (255, 200, 0, 120)}
    for i in range(w * h):
        x, y = i % w * 8, i // w * 8
        v = buf[i * 8 + 1] & 0x0F
        if v in colors:
            d.rectangle((x, y, x + 7, y + 7), fill=colors[v])
        if buf[i * 8] & 0x08:
            d.rectangle((x + 2, y + 2, x + 5, y + 5), fill=(0, 128, 255, 255))
    out = Image.alpha_composite(img.convert('RGBA'), over).convert('RGB')
    out = out.resize((out.width * 2, out.height * 2), Image.NEAREST)
    legend = [('1', colors[1]), ('8', colors[8]), ('9', colors[9]), ('+0 bit3', (0, 128, 255, 255))]
    d = ImageDraw.Draw(out)
    for k, (t, c) in enumerate(legend):
        y = out.height - 18 * (len(legend) - k)
        d.rectangle((4, y, 18, y + 14), fill=c[:3], outline=(0, 0, 0))
        label(out, t, (22, y))
    save(out, 'dq5-map-0207-attributes.webp')


def fig_record(rom):
    """맵 레코드 한 개(02/07)의 바이트 구성: 머리, 비트스트림, 속성 패스 1~3."""
    p = map_pointer(rom, 2, 7)
    dec = Decoder(rom, SLOT)
    dec.decode(p)
    starts = [t[2] for t in dec.pass_trace if t[0] == 'start']
    parts = [('header', p, p + 9, (200, 200, 200)), ('bitstream', p + 9, dec.attr_start, (90, 140, 255)),
             ('pass 1', starts[0], starts[1], (90, 200, 90)), ('pass 2', starts[1], starts[2], (240, 190, 60)),
             ('pass 3', starts[2], dec.end + 1, (230, 90, 90))]
    total = dec.end + 1 - p
    scale = 2
    out = Image.new('RGB', (total * scale + 120, 92), (24, 24, 24))
    d = ImageDraw.Draw(out)
    for k, (name, a, b, c) in enumerate(parts):
        x0, x1 = (a - p) * scale + 1, (b - p) * scale
        d.rectangle((x0, 4, max(x0 + 1, x1), 30), fill=c)
        # 머리처럼 좁은 칸의 글자가 겹치지 않게 줄을 엇갈린다.
        ty = 36 if k % 2 == 0 else 62
        d.line((x0, 30, x0, ty), fill=c)
        d.text((x0 + 3, ty), name, fill=c)
        d.text((x0 + 3, ty + 12), f'{a & 0xFFFF:04X}, {b - a} bytes', fill=(220, 220, 220))
    save(out, 'dq5-map-0207-record.webp')


def fig_day_night(rom):
    """02/06 을 낮·밤 팔레트로 그리고 그 시간대 인물 자리(8x8 셀 좌표)에 그림 번호를 표시."""
    from dq5npc import map_entries, parse
    panels = []
    for night in (False, True):
        dec = Decoder(rom, SLOT)
        w, h, buf, _ = dec.decode(map_pointer(rom, 2, 6))
        render(rom, dec, w, h, buf, map_cgram(rom, 2, 6, night), TMP)
        img = Image.open(TMP).convert('RGB')
        d = ImageDraw.Draw(img)
        for a, _ in map_entries(rom, 2, 6):
            f = parse(rom, a, night)
            if not f:
                continue
            x, y = (f['x'] & 0x7F) * 8, (f['y'] & 0x7F) * 8
            if x >= img.width:
                continue
            d.rectangle((x, y - 8, x + 15, y + 15), outline=(255, 255, 0), width=2)
            label(img, f'{f["gfx"]:02X}', (x + 16, y))
        label(img, 'night (7E:075E >= F0)' if night else 'day')
        panels.append(img)
    out = Image.new('RGB', (panels[0].width * 2 + 8, panels[0].height), (24, 24, 24))
    out.paste(panels[0], (0, 0))
    out.paste(panels[1], (panels[0].width + 8, 0))
    save(out, 'dq5-map-0206-day-night.webp')


def fig_exits(rom):
    """17/00(배)과 17/02 를 나란히 그리고 출구 셀(빨간 틀)·번호·목적지, 실제로 밟은 사다리와 도착 자리를 표시."""
    from dq5exit import exit_attrs, exit_cells, map_exits, describe
    attrs = exit_attrs(rom)
    panels = []
    for bc, bd in ((0x17, 0), (0x17, 2)):
        dec = Decoder(rom, SLOT)
        w, h, buf, _ = dec.decode(map_pointer(rom, bc, bd))
        render(rom, dec, w, h, buf, map_cgram(rom, bc, bd), TMP)
        img = Image.open(TMP).convert('RGB').resize((w * 16, h * 16), Image.NEAREST)
        d = ImageDraw.Draw(img)
        exits = map_exits(rom, bc, bd)
        for k, (x, y) in enumerate(exit_cells(buf, w, h, attrs)):
            d.rectangle(((x - 1) * 16, (y - 1) * 16, x * 16 + 15, y * 16 + 15), outline=(255, 64, 64), width=2)
            text = f'{k}: {describe(bc, exits[k][1])}' if k < len(exits) else str(k)
            label(img, text.replace('의 출구', 'exit').replace(' 의', ''), ((x + 1) * 16, (y - 1) * 16))
        label(img, f'{bc:02X}/{bd:02X}')
        panels.append(img)
    # 실제로 걸어 본 것: 17/00 (7,23) 을 밟으니 17/02 (10,41) 에 섰다(walk.lua).
    ImageDraw.Draw(panels[0]).rectangle((7 * 16, 23 * 16, 7 * 16 + 15, 23 * 16 + 15), outline=(0, 255, 0), width=2)
    ImageDraw.Draw(panels[1]).rectangle((10 * 16, 41 * 16, 10 * 16 + 15, 41 * 16 + 15), outline=(0, 255, 0), width=2)
    out = Image.new('RGB', (sum(p.width for p in panels) + 16, max(p.height for p in panels)), (24, 24, 24))
    out.paste(panels[0], (0, 0))
    out.paste(panels[1], (panels[0].width + 16, 0))
    save(out, 'dq5-exits-ship.webp')


def fig_edge_exit(rom):
    """03/00 아래 가장자리로 걸어 나간 실험: 걸은 길(초록)과 나간 뒤 화면(work/edge1/end.png, 필드 전투)."""
    img, w, h, _, _ = decoded(rom, 3, 0)
    d = ImageDraw.Draw(img)
    # walk.lua 기록: (34,60) 에 도착해 (37,66)·(37,72) 를 거쳐 아래로 더 걸었다.
    path = [(34, 60), (37, 60), (37, 66), (37, 72), (37, 73)]
    d.line([(x * 8 + 4, y * 8 + 4) for x, y in path], fill=(0, 255, 0), width=3)
    d.rectangle((22 * 8, 72 * 8, 54 * 8 - 1, 73 * 8 - 1), outline=(255, 64, 64), width=2)
    label(img, '03/00')
    shot = Image.open('work/edge1/end.png').convert('RGB')
    label(shot, 'after: field (04:FE83 -> 251,215)')
    out = Image.new('RGB', (img.width + 16 + shot.width, max(img.height, shot.height)), (24, 24, 24))
    out.paste(img, (0, 0))
    out.paste(shot, (img.width + 16, img.height - shot.height))
    save(out, 'dq5-exit-edge-0300.webp')


def fig_field(rom):
    """세계 지도 전체(256x256 블록, 1/4 축소)와 필드 화면 비교. 타일 그래픽·팔레트는 필드에 선 순간의 덤프(work/fieldref/)."""
    from dq5field import BLOCK_LOWER, BLOCK_UPPER, FIELD_E000, WORLD, block_number, render, rle
    world, _ = rle(rom, WORLD)
    hib, _ = rle(rom, FIELD_E000)
    vram = open('work/fieldref/field.vram', 'rb').read()
    cg = open('work/fieldref/field.cgram', 'rb').read()
    cache = {}
    full = Image.new('RGB', (256 * 4, 256 * 4))
    for by in range(256):
        for bx in range(256):
            m = block_number(world, hib, bx, by)
            if m not in cache:
                render(rom, bytes([m & 0xFF]), bytes([(m >> 8) << 7]), vram, cg, 0, 0, 1, 1, TMP)
                cache[m] = Image.open(TMP).convert('RGB').resize((4, 4), Image.BOX)
            full.paste(cache[m], (bx * 4, by * 4))
    ImageDraw.Draw(full).rectangle((125 * 4 - 6, 108 * 4 - 6, 125 * 4 + 6, 108 * 4 + 6), outline=(255, 0, 0), width=2)
    save(full, 'dq5-field-world.webp')
    render(rom, world, hib, vram, cg, 116, 105, 24, 20, TMP)
    near = Image.open(TMP).convert('RGB').crop((32, 0, 32 + 256, 224))
    shot = Image.open('work/fieldref/field.png').convert('RGB')
    out = Image.new('RGB', (256 * 2 + 16, 224), (24, 24, 24))
    out.paste(shot, (0, 0))
    out.paste(near, (256 + 16, 0))
    label(out, 'MesenCE')
    label(out, 'dq5field.py', (256 + 16, 0))
    save(out, 'dq5-field-compare.webp')


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
    fig_attributes(rom)
    fig_record(rom)
    fig_day_night(rom)
    fig_exits(rom)
    fig_edge_exit(rom)
    fig_field(rom)
    fig_transition()
    os.remove(TMP)


if __name__ == '__main__':
    main()
