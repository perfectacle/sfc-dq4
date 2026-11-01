"""몬스터 그림의 16x16 자리를 원래보다 늘리고 레코드 색을 15개로 늘린 롬을 MesenCE 전투에서 원본과 견준다.

첫 필드 이벤트 전투를 무리 0F(그림 00, 자리 7) 1 · 7E(그림 43) 1 · スライム(00, 그림 02) 1 로 붙인다(dq5warp.lua 의 BATTLE).
  그림 43: 원래 그린 자리를 색 번호 1~15 의 무늬로 칠하고, NMI 한 번에 모두 닿지 않으면(dq5monwrite.nmi_short)
          아래 칸 줄부터 비운다. 반전 복사가 없어져 타일 53 → 98, 자리 14 → 25 가 되고 비우지 않는다.
  그림 02: 색 번호 1~15 를 섞은 무늬(원래 자리보다 길어 --at 으로 옮김).
두 그림을 쓰는 몬스터(7E·スライム 등)의 색은 모두 15개로 늘린다.
색이 원래보다 많아 레코드 표·레코드는 --records-at 으로 옮긴다. 원본 롬과 고친 롬에서 dq5gfxdump.lua 로 덤프하고,
몬스터마다 OBJ 색 번호(dq5mongfx.match_oam 의 자리에서, 다른 몬스터와 겹치는 픽셀은 뺌)·VRAM OBJ 영역의 타일·CGRAM
OBJ 팔레트 한 줄을, 전투마다 그림 차례·첫 자리
(7E:0D3D·0D4D)·남은 자리 수(7E:0D1F)를 dq5monlimits.Pictures.loads 의 예측과 견준다.
  MESENCE=… python sfc/dq5/tools/dq5mongrowcheck.py rom/dq5.sfc --state work/state/ship.mss
"""
import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dq5mongfx as M  # noqa: E402
from dq5map import Rom  # noqa: E402
from dq5monlimits import Pictures  # noqa: E402
from dq5monwrite import FORMAT, decode_bytes, encode, following_table, nmi_short, picture_grid, stats  # noqa: E402
import dq5mesen  # noqa: E402

HERE = Path(__file__).resolve().parent
GROUPS = ((0x0F, 1, 0), (0x7E, 1, 0), (0x00, 1, 0))
WIDE, NOISE = 0x43, 0x02
DUMPF = '1200,1400,1600'
SLOTS = 0x80


def save(path, grid):
    image = Image.new('P', (len(grid[0]), len(grid)))
    image.putpalette([c for i in range(16) for c in (i * 16,) * 3])
    image.putdata([c for row in grid for c in row])
    image.save(path)


def tool(name, *args):
    subprocess.run([sys.executable, str(HERE / name), *map(str, args)], check=True, capture_output=True, text=True,
                   timeout=600)


def run(rom, name, out, state, mesence, libdir):
    dest = out / name
    dest.mkdir()
    env = {k: v for k, v in os.environ.items()
           if k not in ('ADULT', 'ANYWHERE', 'GROUP', 'LATESET', 'PARTY', 'POKE', 'ROMPATCH', 'SAVE', 'SET',
                        'WAGON', 'EVERY', 'TO')}
    env.update(LIBDIR=str(libdir), STATE=str(state), SHOT_DIR=str(dest), MAXF='1800', SETTLE='300',
               FIELD='341,56', BATTLE=','.join(f'{m:02X}:{n}' for m, n, _ in GROUPS), TEST='wait:900', DUMPF=DUMPF)
    with (dest / 'mesen.log').open('w', encoding='utf-8') as log:
        dq5mesen.testrunner(str(mesence), str(rom), str(HERE / 'lua/dq5gfxdump.lua'),
                            '--Snes.DisableFrameSkipping=true', env=env, stdout=log, stderr=subprocess.STDOUT,
                            check=True, timeout=240)
    return dest


def look(rom, dest):
    """덤프마다 몬스터별 OBJ·VRAM·CGRAM 과 자리 표. 옮긴 그림·레코드를 따라 읽는다."""
    with following_table():
        loads = Pictures(rom).loads(GROUPS)
        out = {'predicted': [[f'{g:02X}', start, n] for g, start, n in loads]}
        for tag in DUMPF.split(','):
            name = f'f{int(tag):05d}'
            oam, vram = (dest / f'{name}.oam').read_bytes(), (dest / f'{name}.vram').read_bytes()
            cgram, wram = (dest / f'{name}.cgram').read_bytes(), (dest / f'{name}.wram').read_bytes()
            rows = [[cgram[256 + (p * 16 + i) * 2] | cgram[257 + (p * 16 + i) * 2] << 8 for i in range(16)]
                    for p in range(8)]
            objs = vram[0xC000:0x10000]
            grid = M.oam_grid(oam, vram)
            per, drawn = {}, {}
            for m, _, _ in GROUPS:
                g, colors = M.monster(rom, m)
                _, _, x, y = M.match_oam(rom, m, oam, vram)
                image = M.index_image(M.decode(rom, g))
                drawn[m] = {(x + i, y + j): v for j, row in enumerate(image) for i, v in enumerate(row) if v}
                tiles = [t for p in M.decode(rom, g)['pieces'] if not p[4] for t in p[3]]
                found = sum(1 for t in tiles if any(objs[o:o + 32] == t for o in range(0, len(objs), 32)))
                per[f'{m:02X}'] = {'at': [x, y], 'vram': [found, len(tiles)],
                                   'colors': len(colors), 'cgram': any(row[1:1 + len(colors)] == colors for row in rows)}
            # 몬스터끼리 겹치는 픽셀(띄운 7E 가 0F 를 가림)은 어느 쪽이 위인지 따지지 않고 뺀다.
            for m, pixels in drawn.items():
                others = {at for k, d in drawn.items() if k != m for at in d}
                mine = [(at, v) for at, v in pixels.items() if at not in others and 0 <= at[0] < 256 and 0 <= at[1] < 224]
                per[f'{m:02X}']['oam'] = [sum(grid[y][x] == v for (x, y), v in mine), len(mine)]
            seen = [[f'{wram[0x0D3D + i]:02X}', wram[0x0D4D + i]] for i in range(16) if wram[0x0D3D + i] != 0xFF]
            per['slots'] = {'loaded': seen, 'free': wram[0x0D1F],
                            'match': seen == [[g, start] for g, start, _ in out['predicted']]
                            and wram[0x0D1F] == SLOTS - sum(n for _, _, n in loads)}
            out[name] = per
    return out


def passed(result):
    last = result[f'f{int(DUMPF.split(",")[-1]):05d}']
    return last['slots']['match'] and all(r['oam'][0] == r['oam'][1] > 0 and r['vram'][0] == r['vram'][1] and r['cgram']
                                          for k, r in last.items() if k != 'slots')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/mongrowcheck')
    ap.add_argument('--at', default='3B:8000', help='옮길 그림과 24비트 머리 포인터 표 자리(dq5monwrite.py --at)')
    ap.add_argument('--records-at', default='3C:8000', help='레코드 표·레코드 자리(dq5monwrite.py --records-at)')
    args = ap.parse_args()
    if not args.mesence:
        ap.error('--mesence 또는 MESENCE가 필요함')
    try:
        original, state, mesence = args.rom.resolve(), args.state.resolve(), Path(args.mesence).resolve()
        for path in (original, state, mesence):
            if not path.is_file():
                raise ValueError(f'파일 없음: {path}')
        args.out.mkdir(parents=True, exist_ok=True)
        out = Path(tempfile.mkdtemp(prefix='run-', dir=args.out.resolve()))
        print(f'실행 출력: {out}', flush=True)
        base = Rom(original.read_bytes())
        rng = random.Random(503)
        wide = [[rng.randrange(1, 16) if v else 0 for v in row] for row in picture_grid(base, WIDE)[0]]
        cut = len(wide)
        while nmi_short(decode_bytes(encode(base, WIDE, wide)[0])):
            cut -= 8
            wide = [row if y < cut else [0] * len(row) for y, row in enumerate(wide)]
        noise = [[rng.randrange(1, 16) if v else 0 for v in row] for row in picture_grid(base, NOISE)[0]]
        save(out / 'wide.png', wide)
        save(out / 'noise.png', noise)
        # 바꾼 그림이 색 15 까지 쓰므로, 그 그림을 쓰는 몬스터 모두의 색을 15개로 늘린다.
        colors = {m: M.monster(base, m)[1] for m in range(M.COUNT) if M.monster(base, m)[0] in (WIDE, NOISE)}
        more = {m: (c + [((i * 7) % 32) << 5 | (31 - i) for i in range(15 - len(c))])[:15] for m, c in colors.items()}
        doc = {'format': FORMAT, 'pictures': [{'picture': f'{WIDE:02X}', 'image': 'wide.png'},
                                              {'picture': f'{NOISE:02X}', 'image': 'noise.png'}],
               'monsters': [{'monster': f'{m:02X}', 'colors': c} for m, c in more.items()]}
        (out / 'monster.json').write_text(json.dumps(doc, indent=1) + '\n', encoding='utf-8')
        where = ('--at', args.at, '--records-at', args.records_at)
        tool('dq5monwrite.py', original, 'check', out / 'monster.json', *where)
        tool('dq5monwrite.py', original, 'patch', out / 'monster.json', '-o', out / 'monster.dq5patch.json', *where)
        edited = out / 'edited.sfc'
        tool('dq5build.py', original, 'build', out / 'monster.dq5patch.json', '--size', '2', '-o', edited,
             '--ips', out / 'edited.ips')
        krlua = Path(subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True,
                                    check=True, timeout=30).stdout.strip())
        libdir = out / 'lib'
        shutil.copytree(krlua, libdir)
        shutil.copyfile(HERE / 'lua/dq5warp.lua', libdir / 'boot.lua')
        results = {name: look(Rom(rom.read_bytes()), run(rom, name, out, state, mesence, libdir))
                   for name, rom in (('original', original), ('edited', edited))}
        patched = Rom(edited.read_bytes())
        with following_table():
            grown = {'tiles': [stats(M.decode(base, WIDE))[1], stats(M.decode(patched, WIDE))[1]],
                     'slots': [M.slot_count(M.decode(base, WIDE)), M.slot_count(M.decode(patched, WIDE))]}
            fits = not nmi_short(M.decode(patched, WIDE))
        print(f'그림 {WIDE:02X} 타일 {grown["tiles"][0]} → {grown["tiles"][1]}, 자리 {grown["slots"][0]} → {grown["slots"][1]}')
        checks = {'original': passed(results['original']), 'edited': passed(results['edited']),
                  'grown': all(a < b for a, b in grown.values()) and fits,
                  'colors': all(M.monster(patched, m)[1] == c for m, c in more.items())}
        (out / 'results.json').write_text(json.dumps({'results': results, 'checks': checks}, ensure_ascii=False, indent=1)
                                          + '\n', encoding='utf-8')
        for name, per_dump in results.items():
            print(f'{name} 예측 자리(그림, 첫 자리, 수): {per_dump["predicted"]}')
            for tag, per in per_dump.items():
                if tag == 'predicted':
                    continue
                print(f'{name} {tag}: ' + '; '.join(
                    f'{m} OBJ {r["oam"][0]}/{r["oam"][1]} @({r["at"][0]},{r["at"][1]}) VRAM {r["vram"][0]}/{r["vram"][1]} '
                    f'색 {r["colors"]} CGRAM {"있음" if r["cgram"] else "없음"}' for m, r in per.items() if m != 'slots')
                      + f'; 자리 표 {per["slots"]["loaded"]} 남음 {per["slots"]["free"]}')
        for key, ok in checks.items():
            print(f'{key}: {"통과" if ok else "불일치"}')
        if not all(checks.values()):
            raise ValueError('불일치: ' + ', '.join(k for k, ok in checks.items() if not ok))
        print(f'검사 {len(checks)}개 통과')
        return 0
    except (OSError, ValueError, KeyError, IndexError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
