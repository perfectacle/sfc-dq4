"""DQ5(SFC) 전투 주문·특기 연출. 형식은 sfc/dq5/docs/dq5-graphics-format.md 의 「전투 연출」.

행동 번호 → 연출 번호: 우리 편이 쓰면 26:8BE0[행동], 몬스터가 쓰면 26:8C75[행동](26:8B59).
연출 번호 → 연출 스크립트: 22:D7AA[연출*2] = 뱅크 24 주소(FFFF 는 없음). 22:D73C 가 스크립트를 돌린다.

롬에서 뽑기:
  python sfc/dq5/tools/dq5fx.py rom/dq5.sfc                 # 행동별 연출 번호와 스크립트 주소
덤프 그리기(lua/dq5fxdump.lua 가 남긴 e<번호>-<k>.* 를 연출 층만 그림):
  python sfc/dq5/tools/dq5fx.py rom/dq5.sfc --frames work/fx 01 --png work/fxpng
  python sfc/dq5/tools/dq5fx.py rom/dq5.sfc --export work/effects work/fxh work/fxm   # 연출마다 시트·GIF·index.json
  python sfc/dq5/tools/dq5fx.py rom/dq5.sfc --check work/fxh/01 01                     # SHOTS=1 화면과 견줌
연출 층은 BG3 타일맵 7~20줄(연출 버퍼 7E:8A1D → VRAM 워드 1CE0)과 팔레트 4~7 의 OBJ 다. 몬스터 OBJ 는
팔레트 0~3(무리별, 그림자 0)이라 빠진다. 화면 위 0~167줄(창 아래 줄 위)만 자른다. 화면에 더해지는 색 계산(HDMA 고정색 등)은
넣지 않는다. 화면 전체는 dq5fxscreen.py.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5map import Rom, lorom  # noqa: E402

PARTY_FX, MONSTER_FX = 0x268BE0, 0x268C75     # [행동] → 연출 번호
SCRIPTS = 0x22D7AA                            # [연출*2] → 24:주소
SCRIPT_BANK = 0x24
FX_COUNT = 0x95                               # 쓰이는 연출 번호는 00~94
ACTIONS = 0x95                                # 26:8BE0 표 길이(26:8B64 는 D5 미만만 보지만 표는 95 개)
BG3_MAP, BG3_CHR, OBJ_BASE, OBJ_HI = 0x1C00, 0x1000, 0x6000, 0x1000
FX_ROWS = range(7, 21)
EXPORT_COMMAND = ('uv run --locked python sfc/dq5/tools/dq5fx.py rom/dq5.sfc --export $OUT/gfx/effects/frames '
                  'work/dq5fx/fxh work/dq5fx/fxm work/dq5fx/fxm2 work/dq5fx/fxp   # 덤프는 lua/dq5fxdump.lua(모듈 설명)')
CROP_H = 168


def fx_tables(rom):
    """[(행동, 우리 편 연출, 몬스터 연출)]."""
    a, b = lorom(PARTY_FX), lorom(MONSTER_FX)
    return [(i, rom.d[a + i], rom.d[b + i]) for i in range(ACTIONS)]


def script_ptr(rom, fx):
    o = lorom(SCRIPTS) + fx * 2
    p = rom.d[o] | rom.d[o + 1] << 8
    return None if p == 0xFFFF or fx == 0 or fx >= FX_COUNT else (SCRIPT_BANK << 16) | p


def fx_name(rom, fx):
    """연출 번호를 쓰는 첫 행동의 이름과 쪽('우리 편'·'몬스터'), 행동 번호 목록."""
    import dq5text
    tab = fx_tables(rom)
    party = [a for a, pf, _ in tab if pf == fx]
    monster = [a for a, pf, mf in tab if mf == fx and pf != fx]
    acts = party or monster
    name = dq5text.text(dq5text.string_codes(rom, dq5text.string(rom, 3, acts[0]))) if acts else ''
    return name, '우리 편' if party else '몬스터', party + monster


def render_frame(vram, cgram, oam, hscroll=0, vscroll=0):
    """덤프 한 프레임의 연출 층(256 x CROP_H, RGBA). 전투는 모드 1 에 BG3 우선(`$2105` bit3)이 켜져 있어,
    우선순위 비트가 선 BG3 타일은 OBJ 위에, 나머지 BG3 타일은 OBJ 아래에 그린다."""
    from PIL import Image
    import dq5gfx
    colors = dq5gfx.cgram_colors(cgram)
    img = Image.new('RGBA', (256, CROP_H), (0, 0, 0, 0))

    def bg3(high):
        for row in FX_ROWS:
            for col in range(32):
                a = (BG3_MAP + row * 32 + col) * 2
                w = vram[a] | vram[a + 1] << 8
                t, p = w & 0x3FF, (w >> 10) & 7
                if t == 0 or bool(w & 0x2000) != high:
                    continue
                c = (BG3_CHR + t * 8) * 2
                px = dq5gfx.chr_2bpp(vram[c:c + 16])
                y = row * 8 - vscroll
                if 0 <= y < CROP_H:
                    img.alpha_composite(dq5gfx.tile_image(px, colors[p * 4:p * 4 + 4], bool(w & 0x4000), bool(w & 0x8000)),
                                        ((col * 8 - hscroll) & 0xFF, y))

    bg3(False)
    for i in reversed(range(128)):   # 앞 번호가 위에 그려진다
        x, y, t, a = oam[i * 4:i * 4 + 4]
        hi = (oam[512 + i // 4] >> ((i % 4) * 2)) & 3
        pal = (a >> 1) & 7
        if pal < 4 or y >= 0xE0:
            continue
        x |= (hi & 1) << 8
        x = x - 512 if x >= 256 else x
        size = 16 if hi & 2 else 8
        name = t | (a & 1) << 8
        hf, vf = bool(a & 0x40), bool(a & 0x80)
        for ty in range(size // 8):
            for tx in range(size // 8):
                n = ((name & 0xF0) + ((name & 0xF) + tx) % 16 + ty * 16) & 0xFF | (name & 0x100)
                base = OBJ_BASE + (OBJ_HI if n & 0x100 else 0) + (n & 0xFF) * 16
                px = dq5gfx.planar(vram[base * 2:base * 2 + 32])
                dx = (size // 8 - 1 - tx if hf else tx) * 8
                dy = (size // 8 - 1 - ty if vf else ty) * 8
                tile = dq5gfx.tile_image(px, colors[128 + pal * 16:144 + pal * 16], hf, vf)
                px_, py_ = x + dx, y + 1 + dy
                if -8 < px_ < 256 and -8 < py_ < CROP_H:
                    img.alpha_composite(tile, (px_, py_)) if px_ >= 0 and py_ >= 0 else img.paste(tile, (px_, py_), tile)
    bg3(True)
    return img


def dump_frames(folder, fx):
    """dq5fxdump.lua 가 남긴 연출 fx 의 프레임 그림 목록."""
    out, k = [], 0
    while os.path.exists(os.path.join(folder, f'e{fx:02X}-{k:03d}.vram')):
        p = os.path.join(folder, f'e{fx:02X}-{k:03d}')
        h, v = (int(s) for s in open(p + '.ppu').read().split())
        out.append(render_frame(open(p + '.vram', 'rb').read(), open(p + '.cgram', 'rb').read(),
                                open(p + '.oam', 'rb').read(), h, v))
        k += 1
    return out


SHOT_DY = 8                 # MesenCE 화면은 위 8줄을 자르고 찍힌다
SHOT_LAG = (1, 2, 3)        # 덤프 k 의 모습은 화면 k+1~k+3 중 하나에 찍힌다(찍는 프레임이 흔들림)
OBJ_BAND = range(56, 160)   # 창(HDMA)이 OBJ 를 보이게 두는 화면 줄. 그 밖의 연출 OBJ 는 화면에 없다


def check(folder, fx):
    """연출 층의 불투명 점을 화면(SHOTS=1 의 e<번호>-<k>.png)과 견준다. 화면을 찍는 프레임이 흔들리므로
    VRAM·CGRAM·OAM 이 k~k+3 동안 그대로인 덤프만, OBJ_BAND 줄만 보고, SHOT_LAG 중 가장 잘 맞는 화면을 쓴다.
    [(k, 같은 점, 연출 점)]."""
    from PIL import Image

    def raw(k, ext):
        p = os.path.join(folder, f'e{fx:02X}-{k:03d}.{ext}')
        return open(p, 'rb').read() if os.path.exists(p) else None

    out = []
    for k, img in enumerate(dump_frames(folder, fx)):
        if any(raw(k, e) != raw(k + j, e) for j in (1, 2, 3) for e in ('vram', 'cgram', 'oam')):
            continue
        px = img.load()
        pts = [(x, y, px[x, y][:3]) for y in OBJ_BAND for x in range(256) if px[x, y][3]]
        if not pts:
            continue
        best = 0
        for lag in SHOT_LAG:
            sp = Image.open(os.path.join(folder, f'e{fx:02X}-{k + lag:03d}.png')).convert('RGB').load()
            best = max(best, sum(sp[x, y - SHOT_DY] == c for x, y, c in pts))
        out.append((k, best, len(pts)))
    return out


def flatten(img, bg=(0, 0, 0)):
    from PIL import Image
    out = Image.new('RGB', img.size, bg)
    out.paste(img, (0, 0), img)
    return out


def save_anim(frames, stem, outdir, title):
    """프레임 시트(연출이 있는 프레임만, 8칸씩)와 GIF(60fps 그대로). (시트, gif) 메타데이터."""
    import dq5gfx
    os.makedirs(outdir, exist_ok=True)
    flat = [flatten(f) for f in frames]
    keep = [i for i, f in enumerate(frames) if f.getbbox()]
    if not keep:
        return []
    cells = [flat[i] for i in keep]
    sheet = dq5gfx.sheet(cells, 8, 256, CROP_H, [str(i) for i in keep], label_h=10)
    sheet.save(os.path.join(outdir, stem + '.png'))
    flat[0].save(os.path.join(outdir, stem + '.gif'), save_all=True, append_images=flat[1:],
                 duration=17, loop=0)
    return [{'path': stem + '.png', 'w': sheet.width, 'h': sheet.height, 'title': title,
             'frames': len(frames), 'shown': len(keep)},
            {'path': stem + '.gif', 'w': 256, 'h': CROP_H, 'title': title + ' (GIF)', 'frames': len(frames)}]


def export_all(rom, dump_dirs, outdir):
    """dq5fxdump.lua 덤프 폴더들(아래 폴더의 fx.txt 까지)에서 연출마다 처음 찍힌 것을 그려 outdir 에 쓴다.
    index.json 항목 목록을 돌려준다."""
    folders = sorted({os.path.dirname(p) for d in dump_dirs for p in
                      [os.path.join(d, 'fx.txt')] + [os.path.join(d, s, 'fx.txt') for s in sorted(os.listdir(d))]
                      if os.path.exists(p)})
    seen, items = set(), []
    for folder in folders:
        for line in open(os.path.join(folder, 'fx.txt')):
            if not line.strip():
                continue
            fx = int(line.split()[0], 16)
            if fx in seen:
                continue
            seen.add(fx)
            name, side, acts = fx_name(rom, fx)
            frames = dump_frames(folder, fx)
            stem = f'{fx:02X}-{name}' if name else f'{fx:02X}'
            ptr = script_ptr(rom, fx)
            for it in save_anim(frames, stem, outdir, f'연출 {fx:02X} {name}'):
                it.update({'fx': f'{fx:02X}', 'name': name, 'side': side,
                           'actions': [f'{a:02X}' for a in acts],
                           'script': ptr and f'{ptr >> 16:02X}:{ptr & 0xFFFF:04X}'})
                items.append(it)
    items.sort(key=lambda it: it['path'])
    for it in items:
        it.update(cat='effects', group='전투 연출 프레임')
    with open(os.path.join(outdir, 'index.json'), 'w') as f:
        json.dump(items, f, ensure_ascii=False, indent=1)
    import hashlib
    import dq5gfx
    with open(os.path.join(outdir, 'SOURCE.txt'), 'w') as f:
        f.write(dq5gfx.source_text(EXPORT_COMMAND, hashlib.sha1(rom.d).hexdigest()))
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('fx', nargs='*', type=lambda s: int(s, 16))
    ap.add_argument('--frames', help='dq5fxdump.lua 덤프 폴더')
    ap.add_argument('--png', help='그림 폴더')
    ap.add_argument('--name', default='', help='파일 이름 뒤에 붙일 이름')
    ap.add_argument('--export', nargs='+', metavar='DIR', help='덤프 폴더들(첫 인자는 내보낼 폴더)')
    ap.add_argument('--check', help='SHOTS=1 로 찍은 덤프 폴더. 연출 층을 화면과 견줌')
    args = ap.parse_args()
    rom = Rom(open(args.rom, 'rb').read())
    if args.export:
        items = export_all(rom, args.export[1:], args.export[0])
        print(len(items), '파일')
        return 0
    if args.check:
        for fx in args.fx:
            res = check(args.check, fx)
            same, total = sum(r[1] for r in res), sum(r[2] for r in res)
            print(f'{fx:02X}: 견준 프레임 {len(res)}, 연출 점 {same}/{total} 같음')
        return 0
    if args.frames:
        items = []
        for fx in args.fx:
            frames = dump_frames(args.frames, fx)
            stem = f'{fx:02X}' + (f'-{args.name}' if args.name else '')
            items += save_anim(frames, stem, args.png, f'연출 {fx:02X}')
            print(stem, len(frames))
        print(json.dumps(items, ensure_ascii=False))
        return 0
    for act, pf, mf in fx_tables(rom):
        sp, sm = script_ptr(rom, pf), script_ptr(rom, mf)
        print(f'{act:02X}  우리 편 {pf:02X} {sp and f"{sp >> 16:02X}:{sp & 0xFFFF:04X}" or "-":8}  '
              f'몬스터 {mf:02X} {sm and f"{sm >> 16:02X}:{sm & 0xFFFF:04X}" or "-"}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
