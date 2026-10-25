"""DQ5(SFC) 전투 몬스터 움직임. 형식은 sfc/dq5/docs/dq5-graphics-format.md 의 「몬스터 움직임」.

몬스터 그림은 dq5mongfx.py(디코더·배치)를 그대로 쓰고, 움직임만 프레임으로 늘어놓는다.
  hit    맞음(26:8BAE → 22:FD09): 숨김 3프레임·보임 3프레임 네 번(22:CE24 숨기기, 22:CE6A 보이기)
  die    쓰러짐: hit 뒤 22:CBC5 → 22:CE24 로 한 번에 지움(그 뒤 다시 그리지 않음)
  hop    行動 89(20:DB11 → 22:D142): 22:D199 의 8바이트를 상자 y 에 한 프레임씩 더함
사용:
  python sfc/dq5/tools/dq5monmotion.py rom/dq5.sfc 00:3,03:2 --png work/mm      # 무리 몬스터:마릿수(16진:10진)
  python sfc/dq5/tools/dq5monmotion.py rom/dq5.sfc 00:3 --check-hop work/m7 --check-hit work/m1
  python sfc/dq5/tools/dq5monmotion.py rom/dq5.sfc --shots work/e26 1338 1600 boss-sink --png work/mm   # 게임 화면 GIF
--check-* 는 lua/dq5monlog.lua 덤프(w<프레임>.bin = 7E:0C00~, o<프레임>.oam)와 프레임마다 견준다.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5map import Rom, lorom  # noqa: E402
import dq5mongfx  # noqa: E402

HOP = 0x22D199
HIT_CYCLES, HIT_HIDE, HIT_SHOW = 4, 3, 3
SCREEN_H = 168
OAM_DY = 1                        # OAM y 다음 줄부터 그려진다


def hop_offsets(rom):
    o = lorom(HOP)
    return [b - 256 if b & 0x80 else b for b in rom.d[o:o + 8]]


def hit_visible():
    """맞음 동안 프레임마다 보이는지."""
    return ([False] * HIT_HIDE + [True] * HIT_SHOW) * HIT_CYCLES


def scene(rom, groups):
    """[(몬스터, x, y, 그리는 순서)]. 순서 값은 줄 0 → 1, 줄 1 → 5, 줄 2(띄움) → 0(22:A03F·A064·A075)."""
    out = []
    for m, x, y in dq5mongfx.layout(rom, [(m, n, 0) for m, n in groups]):
        hd = dq5mongfx.header(rom, dq5mongfx.monster(rom, m)[0])
        out.append((m, x, y, 0 if hd['float'] else 1))
    return out


def frame(rom, slots, sprites, hidden=(), dy=None):
    """슬롯 목록을 그린 한 프레임(RGBA). 순서 값이 작은 몬스터가 앞(22:A1D5 가 OAM 앞자리에 둠)."""
    from PIL import Image
    img = Image.new('RGBA', (256, SCREEN_H), (0, 0, 0, 0))
    dy = dy or {}
    for k in sorted(range(len(slots)), key=lambda k: -slots[k][3]):
        if k in hidden:
            continue
        m, x, y, _ = slots[k]
        spr = sprites[m]
        img.alpha_composite(spr, (x - 1, y + OAM_DY + dy.get(k, 0)))   # 그림 왼쪽 1픽셀 여백
    return img


def motions(rom, groups, target=0):
    """{이름: 프레임 목록}. target 은 움직이는 슬롯(왼쪽부터 0)."""
    slots = scene(rom, groups)
    sprites = {m: dq5mongfx.render(rom, m, None) for m, _, _, _ in slots}
    still = frame(rom, slots, sprites)
    hit = [frame(rom, slots, sprites, () if v else (target,)) for v in hit_visible()]
    gone = frame(rom, slots, sprites, (target,))
    hop = [frame(rom, slots, sprites, dy={target: d}) for d in hop_offsets(rom)]
    return {'hit': [still] * 6 + hit + [still] * 6,
            'die': [still] * 6 + hit + [still] * 15 + [gone] * 12,
            'hop': [still] * 6 + hop + [still] * 6}


def save(frames, outdir, stem, title):
    """프레임 시트(바뀌는 프레임만)와 GIF(60fps). index 항목 둘."""
    from PIL import Image
    import dq5gfx
    os.makedirs(outdir, exist_ok=True)
    bg = (24, 96, 48)
    flat = []
    for f in frames:
        o = Image.new('RGB', f.size, bg)
        o.paste(f, (0, 0), f)
        flat.append(o)
    keep = [i for i in range(len(flat)) if i == 0 or flat[i].tobytes() != flat[i - 1].tobytes()]
    sheet = dq5gfx.sheet([flat[i] for i in keep], 4, 256, SCREEN_H, [str(i) for i in keep], label_h=10)
    sheet.save(os.path.join(outdir, stem + '.png'))
    flat[0].save(os.path.join(outdir, stem + '.gif'), save_all=True, append_images=flat[1:], duration=17, loop=0)
    return [{'path': stem + '.png', 'w': sheet.width, 'h': sheet.height, 'title': title, 'frames': len(frames)},
            {'path': stem + '.gif', 'w': 256, 'h': SCREEN_H, 'title': title + ' (GIF)', 'frames': len(frames)}]


def check_hop(rom, folder, slot):
    """덤프의 상자 y(7E:0CA4+슬롯)가 22:D199 대로 움직인 구간을 찾는다. [(시작 프레임, 맞음 여부)]."""
    frames = sorted(int(f[1:6]) for f in os.listdir(folder) if f.startswith('w') and f.endswith('.bin'))
    ys = {f: open(os.path.join(folder, f'w{f:05d}.bin'), 'rb').read()[0xA4 + slot] for f in frames}
    want = hop_offsets(rom)
    out = []
    for f in frames:
        if out and f < out[-1][0] + len(want):
            continue
        if f - 1 in ys and ys[f] != ys[f - 1] and ys[f - 1] - ys.get(f - 2, ys[f - 1]) == 0:
            base = ys[f - 1]
            got = [ys.get(f + i, -1) - base for i in range(len(want))]
            # 44 처럼 같은 값이 두 프레임 이어지는 칸이 있어, 바뀌는 차례만 견준다
            seq = [v for i, v in enumerate(got) if i == 0 or v != got[i - 1]]
            wseq = [v for i, v in enumerate(want) if i == 0 or v != want[i - 1]]
            out.append((f, seq == wseq + [0] * (len(seq) - len(wseq)) or seq[:len(wseq)] == wseq))
    return out


def check_hit(folder, x, y):
    """덤프 OAM 에서 (x, y) 칸 OBJ 가 보이는 프레임 차례를 hit_visible 과 견준다. [(시작 프레임, 맞음 여부)].
    사라진 뒤 덤프 끝까지 다시 나오지 않으면 (프레임, '지워짐')."""
    frames = sorted(int(f[1:6]) for f in os.listdir(folder) if f.startswith('o') and f.endswith('.oam'))

    def shown(f):
        o = open(os.path.join(folder, f'o{f:05d}.oam'), 'rb').read()
        return any(o[i * 4] == x and o[i * 4 + 1] == y for i in range(128))
    vis = {f: shown(f) for f in frames}
    want = hit_visible()
    out = []
    for f in frames:
        if vis.get(f - 1) and not vis[f]:
            if f - 7 in vis and not all(vis.get(f - j, True) for j in range(1, 7)):
                continue          # 깜빡임 도중
            got = [vis.get(f + i) for i in range(len(want))]
            out.append((f, '지워짐' if not any(vis[g] for g in frames if g >= f) else got == want))
    return out


def shots_anim(folder, first, last, outdir, stem, title):
    """dq5monlog.lua 의 SHOTS=1 화면(s<프레임>.png)을 위 SCREEN_H 줄만 잘라 시트·GIF 로. 게임을 찍은 것이라
    화면을 찍는 프레임이 1~3프레임 흔들린다."""
    from PIL import Image
    frames = []
    for f in range(first, last + 1):
        p = os.path.join(folder, f's{f:05d}.png')
        if os.path.exists(p):
            frames.append(Image.open(p).convert('RGBA').crop((0, 0, 256, SCREEN_H)))
    return save(frames, outdir, stem, title)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('groups', nargs='?', help='몬스터:마릿수 쉼표 목록(몬스터 16진)')
    ap.add_argument('--shots', nargs=4, metavar=('DIR', 'FIRST', 'LAST', 'NAME'),
                    help='dq5monlog SHOTS=1 화면을 FIRST~LAST 프레임 GIF 로(--png 폴더에 NAME.gif·png)')
    ap.add_argument('--target', type=int, default=0)
    ap.add_argument('--png', help='그림 폴더')
    ap.add_argument('--check-hop', help='dq5monlog 덤프 폴더(行動 89)')
    ap.add_argument('--check-hit', help='dq5monlog 덤프 폴더(맞음)')
    args = ap.parse_args()
    rom = Rom(open(args.rom, 'rb').read())
    if args.shots:
        d, a, b, name = args.shots
        print(json.dumps(shots_anim(d, int(a), int(b), args.png, name, name), ensure_ascii=False))
        return 0
    groups = [(int(m, 16), int(n)) for m, n in (g.split(':') for g in args.groups.split(','))]
    slots = scene(rom, groups)
    for k, s in enumerate(slots):
        print(f'슬롯 {k}: 몬스터 {s[0]:02X} 상자 ({s[1]},{s[2]}) 순서 {s[3]}')
    if args.check_hop:
        for k in range(len(slots)):
            print('hop 슬롯', k, check_hop(rom, args.check_hop, k))
    if args.check_hit:
        for k, s in enumerate(slots):
            print('hit 슬롯', k, check_hit(args.check_hit, s[1], s[2]))
    if args.png:
        import dq5text
        names = {m: dq5text.text(dq5text.string_codes(rom, dq5text.string(rom, 4, m))) for m, _ in groups}
        stem0 = '-'.join(f'{m:02X}' for m, _ in groups)
        items = []
        for kind, frames in motions(rom, groups, args.target).items():
            items += save(frames, args.png, f'{stem0}-{args.target}-{kind}', f'{"·".join(names.values())} 칸 {args.target} {kind}')
        print(json.dumps(items, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
