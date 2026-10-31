"""장 주인공 필드 그림: NDS 인물 시트를 DQ5 6타일 세트로 줄여 넣고, 주인공 그림을 장마다 고르게 한다.

DQ5 엔진은 일행 0번의 그림 번호를 실내면 2B(02:CA5A), 바깥이면 2E(05:D98F)로 두므로 서장 주인공과 1장 라이언이
같은 그림 번호를 쓴다. 그림 번호 → 세트를 읽는 두 곳(1F:CF45, 03:D202 의 LDA $2586D0,X)을 JSL 로 돌려,
X 가 2B·2E 이면 지금 맵 그룹($BC)으로 세트를 고른다. 나머지 그림 번호는 원래 표를 읽는다. 장 깃발로 고르면
1장 왕좌의 방은 깃발이 켜지기 전(장 제목 연출 앞)에 그림을 올려 서장 주인공이 남았다(실측).

NDS 시트(자원 저장소 nds/dq4/chr/field/hNNN.png, 8방향 × 24x32 프레임 3장)에서 방향마다 첫 프레임만 쓴다.
둘째·셋째 프레임은 다리가 같고 팔만 다른 동작이라 걸음이 되지 않는다. DQ5 성인 NPC(세트 00, 16x22, 발이
21번 줄)에 맞춰 세로 22줄로 BOX 축소하고 NDS 색 중 가까운 색으로 바꾼 뒤, 16칸을 넘는 양끝을 자른다. 걸음 둘째
장은 DQ5 처럼 다리만 바꾼다: 앞·뒤는 1장째 오른발, 2장째 왼발을 1칸 들고, 옆은 발 3줄을 1장째 보는 쪽, 2장째
반대쪽으로 1칸 옮긴다.

  python sfc/dq4/tools/dq4leader.py --base work/ch1/dq4-ch1-sound.sfc --assets "$DQ4_ASSETS" --out work/ch1/dq4-ch1-full.sfc
"""
import argparse
import json
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
DQ5_TOOLS = HERE.parents[1] / 'dq5' / 'tools'
sys.path[:0] = [str(HERE), str(DQ5_TOOLS)]

import dq4chapterbox  # noqa: E402
from dq4chapter1 import apply_writes, lorom  # noqa: E402
from dq4romassets import set_checksum  # noqa: E402
import dq5objpalette  # noqa: E402
import dq5spritewrite  # noqa: E402
from dq5map import Rom  # noqa: E402

FIELD = Path('nds') / 'dq4' / 'chr' / 'field'
# NDS 8방향 시트의 줄: 0 뒤, 2 오른쪽 보기, 4 앞, 6 왼쪽 보기. DQ5 시트는 행 아래·왼쪽·오른쪽·위
ROWS = (('down', 4), ('left', 6), ('right', 2), ('up', 0))
HEIGHT, BOTTOM, WIDTH = 22, 22, 16
LEADER_PICTURES = (0x2B, 0x2E)
# (세트, NDS 시트, OBJ 팔레트, 맵 그룹 또는 None). 맵 그룹이 맞는 첫 줄을 쓰고, 없으면 None 줄
LEADERS = (
    (0x70, 'h101', 7, dq4chapterbox.PROLOGUE.where[0]),   # 서장 마을(5장 첫머리도 같은 마을): 천공의 용사
    (0x71, 'h106', 6, None),                               # 1장 라이언
)
MAP_GROUP = 0x7E00BC
HOOK_SITES = ('1F:CF45', '03:D202')
LOAD_SET = bytes.fromhex('bf d0 86 25')                  # LDA $2586D0,X
TILES_AT, PALETTES_AT, HOOK_AT = '3E:E000', '3D:EA00', '3E:FC00'


def frames(sheet):
    """방향마다 첫 프레임(RGBA). 같은 방향은 한 상자로 잘라야 걸을 때 몸이 흔들리지 않는다."""
    im = Image.open(sheet).convert('RGBA')
    out = {}
    for name, row in ROWS:
        strip = im.crop((0, row * 32, im.width, row * 32 + 32))
        cols = [x for x in range(im.width) if any(strip.getpixel((x, y))[3] for y in range(32))]
        x1 = cols[0]
        while x1 + 1 in cols:
            x1 += 1
        fr = strip.crop((cols[0], 0, x1 + 1, 32))
        out[name] = fr.crop(fr.getbbox())
    return out


def palette(fr):
    count = Counter(p[:3] for f in fr.values() for p in f.get_flattened_data() if p[3])
    return [c for c, _ in count.most_common(15)]


def nearest(pal, p):
    return min(range(len(pal)), key=lambda k: sum((a - b) ** 2 for a, b in zip(pal[k], p))) + 1


def sheet(fr, pal):
    """32x96 색 번호 시트(dq5spritewrite 6타일 배치: 열 걸음 0·1, 행 아래·왼쪽·오른쪽·위)."""
    out = Image.new('P', (32, 96), 0)
    out.putpalette([0, 0, 0] + [v for c in pal for v in c])
    for r, (name, _) in enumerate(ROWS):
        f = fr[name]
        w = round(f.width * HEIGHT / f.height)
        small = f.resize((w, HEIGHT), Image.BOX)
        cut, ox = max(0, w - WIDTH) // 2, (WIDTH - min(WIDTH, w)) // 2
        for col in (0, 1):
            for y in range(HEIGHT):
                for x in range(min(WIDTH, w)):
                    p = small.getpixel((x + cut, y))
                    if p[3] >= 128:
                        out.putpixel((col * 16 + ox + x, r * 24 + BOTTOM - HEIGHT + y), nearest(pal, p[:3]))
        step(out, r, name)
    return out


def step(out, r, name):
    legs = range(BOTTOM - round(HEIGHT * 5 / 24), BOTTOM)
    get = lambda col, x, y: out.getpixel((col * 16 + x, r * 24 + y))  # noqa: E731
    if name in ('down', 'up'):
        for col, xs in ((0, range(8, 16)), (1, range(0, 8))):
            for x in xs:
                for y in legs:
                    out.putpixel((col * 16 + x, r * 24 + y), get(col, x, y + 1) if y < BOTTOM - 1 else 0)
        return
    ahead = -1 if name == 'left' else 1
    for col, d in ((0, ahead), (1, -ahead)):
        for y in range(BOTTOM - 3, BOTTOM):
            line = [get(col, x, y) for x in range(16)]
            moved = [0] + line[:-1] if d > 0 else line[1:] + [0]
            for x in range(16):
                out.putpixel((col * 16 + x, r * 24 + y), moved[x])


def hook(leaders, default):
    """X 가 주인공 그림이면 맵 그룹으로 세트를, 아니면 원래 표를 읽는 루틴. 부르는 곳의 A·X 폭이 달라
    PHP·SEP #$30 … PLP 로 감싼다(두 곳 모두 뒤에서 N·Z 를 보지 않는다)."""
    code = bytearray(b'\x08\xe2\x30')                                   # PHP / SEP #$30
    for p in LEADER_PICTURES:
        code += bytes((0xE0, p, 0xF0, 0))                                 # CPX #p / BEQ leader
    jumps = [len(code) - 1 - 4 * k for k in range(len(LEADER_PICTURES))]
    code += LOAD_SET + b'\x80\x00'                                        # LDA 표,X / BRA done
    done_jumps = [len(code) - 1]
    leader = len(code)
    for off in jumps:
        code[off] = leader - (off + 1)
    for s, group in leaders:
        a = MAP_GROUP
        code += bytes((0xAF, a & 0xFF, a >> 8 & 0xFF, a >> 16, 0xC9, group, 0xD0, 4, 0xA9, s, 0x80, 0))
        done_jumps.append(len(code) - 1)
    code += bytes((0xA9, default))
    done = len(code)
    for off in done_jumps:
        code[off] = done - (off + 1)
    return bytes(code + b'\x28\x6b')                                      # PLP / RTL


def cpu(text):
    bank, addr = text.split(':')
    return int(bank, 16) << 16 | int(addr, 16)


def hook_patch(rom):
    at = cpu(HOOK_AT)
    code = hook([(s, g) for s, _, _, g in LEADERS if g is not None], next(s for s, _, _, g in LEADERS if g is None))
    writes = [{'at': HOOK_AT, 'hex': code.hex(' '), 'note': '주인공 그림 → 맵 그룹으로 세트'}]
    for site in HOOK_SITES:
        orig = rom[lorom(cpu(site)):lorom(cpu(site)) + 4]
        if orig != LOAD_SET:
            raise SystemExit(f'{site}: LDA $2586D0,X 가 아님 ({orig.hex(" ")})')
        writes.append({'at': site, 'hex': bytes((0x22, at & 0xFF, at >> 8 & 0xFF, at >> 16)).hex(' '),
                       'orig': orig.hex(' '), 'note': '그림 → 세트를 장 주인공 훅으로(JSL)'})
    return {'format': 'dq5patch/1', 'name': 'leader-hook', 'writes': writes, 'rom_size': 2}


def build(base, dq5, assets, out, work):
    work.mkdir(parents=True, exist_ok=True)
    sets, pals = [], []
    for s, name, line, _ in LEADERS:
        fr = frames(assets / FIELD / f'{name}.png')
        pal = palette(fr)
        sheet(fr, pal).save(work / f'{s:02X}.png')
        sets.append({'set': f'{s:02X}', 'image': f'{s:02X}.png', 'palette': 0})
        pals.append(({'palette': line, 'colors': [(b >> 3) << 10 | (g >> 3) << 5 | r >> 3 for r, g, b in pal]},
                     {'set': f'{s:02X}', 'palette': line}))
    doc = {'format': 'dq5sprite/1', 'new_sets': sets,
           'gfx': [{'gfx': f'{g:02X}', 'set': f'{s:02X}'} for g, (s, *_) in zip(LEADER_PICTURES, LEADERS)]}
    (work / 'sprite.json').write_text(json.dumps(doc, indent=1) + '\n')
    original = dq5.read_bytes()
    sprite = dq5spritewrite.patch(Rom(original), doc, work, cpu(TILES_AT))
    (work / 'sprite.dq5patch.json').write_text(json.dumps(sprite, ensure_ascii=False, indent=1) + '\n')
    subprocess.run([sys.executable, DQ5_TOOLS / 'dq5build.py', dq5, 'build', work / 'sprite.dq5patch.json',
                    '--size', '2', '-o', work / 'mid.sfc'], check=True, stdout=subprocess.DEVNULL)
    pal_doc = {'format': 'dq5objpalette/1', 'palettes': [p for p, _ in pals], 'sets': [s for _, s in pals]}
    palettes = dq5objpalette.patch(Rom((work / 'mid.sfc').read_bytes()), pal_doc, PALETTES_AT)
    (work / 'palette.dq5patch.json').write_text(json.dumps(palettes, ensure_ascii=False, indent=1) + '\n')
    (work / 'hook.dq5patch.json').write_text(json.dumps(hook_patch(original), indent=1) + '\n')
    rom = apply_writes(base.read_bytes(), original, [work / f'{n}.dq5patch.json' for n in ('sprite', 'palette', 'hook')])
    out.write_bytes(set_checksum(rom))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--base', required=True, type=Path, help='얹을 1장 롬(곡 묶음까지 얹은 것)')
    ap.add_argument('--dq5', default='rom/dq5.sfc', type=Path)
    ap.add_argument('--assets', required=True, type=Path, help='NDS 인물 시트가 있는 자원 저장소')
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--work', type=Path, help='중간 시트·패치를 둘 폴더(기본 임시 폴더)')
    args = ap.parse_args()
    if args.work:
        build(args.base, args.dq5, args.assets, args.out, args.work)
    else:
        with tempfile.TemporaryDirectory() as tmp:
            build(args.base, args.dq5, args.assets, args.out, Path(tmp))
    print(args.out)


if __name__ == '__main__':
    main()
