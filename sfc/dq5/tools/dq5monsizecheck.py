"""몬스터 그림의 크기와 머리 +0~+4 를 바꾼 롬을 MesenCE 전투에서 dq5mongfx.layout 의 예측과 견준다.

그림 둘을 고친다(dq5monwrite.py 의 dq5monster/1, 크기는 PNG 로, 머리는 "header" 로).
  BIG    그림 4F(몬스터 E2, 6x7 칸)를 가로·세로 2칸 큰 8x9 상자에 왼쪽 1칸·위 2칸 띄워 놓는다.
  SMALL  그림 1C(몬스터 E6, 10x11 칸)에서 왼쪽 1칸·위 1칸, 오른쪽 1칸·아래 1칸을 잘라 8x9 로 줄인다.
둘 다 타격 기준점 +3·+4 를 그림이 옮긴 칸만큼 옮겨 "header" 로 쓴다. 그림자 보정은 상자 가운데·아랫단에서 재므로
(그래픽 형식의 「그림자」) 그림이 상자 안에서 옮긴 만큼 가운데·아랫단도 옮겨 그대로 둔다.
두 몬스터는 원본 무리 조합에서 늘 혼자 나와, dq5monwrite.py 의 조합 검사를 지난다.
첫 필드 이벤트 전투 무리를 BATTLE 로 덮어(dq5warp.lua) 큰 몬스터만·작은 몬스터만·둘과 고치지 않은 몬스터를 섞은 전투를
원본 롬과 고친 롬에서 싸운다. 덤프(dq5gfxdump.lua)에서 본다.
  OBJ 자리   OAM 의 보이는 OBJ (x, y) 묶음이 layout 의 상자 + 조각 자리와 같은지
  그림       몬스터마다 OBJ 색 번호(match_oam, 겹치는 픽셀은 뺌)와 VRAM OBJ 영역의 타일
  무리 표    7E:0C3D(가로 칸)·0C42(세로 칸 × 8)·0C5B(들어올림 × 8)·0C2E·0C33(그림자 보정)·0C38(그림자 모양)·
             0C51·0C56(타격 기준점)이 그 롬의 머리와 같은지(22:92C2)
  자리·줄 목록 7E:0D3D(그림)·0D4D(첫 16x16 자리)·0D6D(줄 목록 첫 칸)가 그림을 푸는 차례대로 0 부터 이어지는지

  MESENCE=… python sfc/dq5/tools/dq5monsizecheck.py rom/dq5.sfc --state work/state/ship.mss
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dq5mongfx as M  # noqa: E402
from dq5map import Rom  # noqa: E402
from dq5monlimits import Pictures  # noqa: E402
from dq5monwrite import FORMAT, following_table, picture_grid  # noqa: E402

HERE = Path(__file__).resolve().parent
BIG, SMALL, PLAIN = (0x4F, 0xE2), (0x1C, 0xE6), 0x00     # (그림, 몬스터), 고치지 않는 몬스터(スライム)
DUMPF = '1200,1400'
GROUP_TABLE = {'w': 0x0C3D, 'h8': 0x0C42, 'raise8': 0x0C5B, 'shadow_dx': 0x0C2E, 'shadow_dy': 0x0C33,
               'shadow': 0x0C38, 'hit_x': 0x0C51, 'hit_y': 0x0C56}


def moved(grid, w, h, dx, dy):
    """grid 를 w x h 칸 상자에 칸 (dx, dy) 만큼 옮겨 놓는다. 밖으로 나가는 픽셀은 버린다."""
    out = [[0] * (w * 8) for _ in range(h * 8)]
    for y, row in enumerate(grid):
        for x, v in enumerate(row):
            if 0 <= y + dy * 8 < h * 8 and 0 <= x + dx * 8 < w * 8:
                out[y + dy * 8][x + dx * 8] = v
    return out


def save(path, grid):
    image = Image.new('P', (len(grid[0]), len(grid)))
    image.putpalette([c for i in range(16) for c in (i * 16,) * 3])
    image.putdata([c for row in grid for c in row])
    image.save(path)


def document(rom, out):
    rows = []
    for name, (g, _), dw, (dx, dy) in (('big', BIG, 2, (1, 2)), ('small', SMALL, -2, (-1, -1))):
        grid, d = picture_grid(rom, g)
        hd = M.header(rom, g)
        w, h = d['w'] + dw, d['h'] + dw
        save(out / f'{name}.png', moved(grid, w, h, dx, dy))
        header = {'hit_x': min(max(hd['hit_x'] + dx, 0), w - 1), 'hit_y': min(max(hd['hit_y'] + dy, 0), h - 1)}
        rows.append({'picture': f'{g:02X}', 'image': f'{name}.png', 'header': header})
    doc = {'format': FORMAT, 'pictures': rows}
    (out / 'monster.json').write_text(json.dumps(doc, indent=1) + '\n', encoding='utf-8')
    return doc


def tool(name, *args):
    subprocess.run([sys.executable, str(HERE / name), *map(str, args)], check=True, capture_output=True, text=True,
                   timeout=600)


def run(rom, name, groups, out, state, mesence, libdir):
    dest = out / name
    dest.mkdir()
    env = {k: v for k, v in os.environ.items()
           if k not in ('ADULT', 'ANYWHERE', 'GROUP', 'LATESET', 'PARTY', 'POKE', 'ROMPATCH', 'SAVE', 'SET',
                        'WAGON', 'EVERY', 'TO')}
    env.update(LIBDIR=str(libdir), STATE=str(state), SHOT_DIR=str(dest), MAXF='1600', SETTLE='300',
               FIELD='341,56', BATTLE=','.join(f'{m:02X}:{n}' for m, n, _ in groups), TEST='wait:900', DUMPF=DUMPF)
    with (dest / 'mesen.log').open('w', encoding='utf-8') as log:
        subprocess.run([str(mesence), '--testrunner', str(rom), str(HERE / 'lua/dq5gfxdump.lua'),
                        '--Snes.DisableFrameSkipping=true'], env=env, stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=240)
    return dest


def predicted(rom, groups):
    """layout 의 상자마다 조각 자리, 상자 목록."""
    boxes = M.layout(rom, list(groups))
    want = Counter()
    for m, bx, by in boxes:
        for x, y, *_ in M.decode(rom, M.monster(rom, m)[0])['pieces']:
            want[(bx + x, by + y)] += 1
    return want, boxes


def seen_objs(oam):
    seen = Counter()
    for i in range(128):
        x, y = oam[i * 4], oam[i * 4 + 1]
        x |= (oam[512 + (i >> 2)] >> ((i & 3) * 2) & 1) << 8
        if y < 224:
            seen[(x - 512 if x >= 256 else x, y)] += 1
    return seen


def expected_table(rom, m):
    hd = M.header(rom, M.monster(rom, m)[0])
    return {'w': hd['w'], 'h8': hd['h'] * 8, 'raise8': hd['raise'] * 8, 'shadow_dx': hd['shadow_dx'] & 0xFF,
            'shadow_dy': hd['shadow_dy'] & 0xFF, 'shadow': hd['shadow'], 'hit_x': hd['hit_x'], 'hit_y': hd['hit_y']}


def look(rom, dest, groups):
    with following_table():
        want, boxes = predicted(rom, groups)
        pics = Pictures(rom)
        loads = pics.loads(groups)
        rows, start = [], 0
        for g, slot, _ in loads:
            rows.append([f'{g:02X}', slot, start])
            start += M.header(rom, g)['h']
        out = {'boxes': [[f'{m:02X}', x, y] for m, x, y in boxes], 'loads': rows}
        for tag in DUMPF.split(','):
            name = f'f{int(tag):05d}'
            oam, vram = (dest / f'{name}.oam').read_bytes(), (dest / f'{name}.vram').read_bytes()
            wram = (dest / f'{name}.wram').read_bytes()
            seen = seen_objs(oam)
            grid = M.oam_grid(oam, vram)
            objs = vram[0xC000:0x10000]
            per, drawn = {}, {}
            for m, _, _ in groups:
                g = M.monster(rom, m)[0]
                image = M.index_image(M.decode(rom, g))
                _, _, x, y = M.match_oam(rom, m, oam, vram)
                drawn[m] = {(x + i, y + j): v for j, row in enumerate(image) for i, v in enumerate(row) if v}
                tiles = [t for p in M.decode(rom, g)['pieces'] if not p[4] for t in p[3]]
                found = sum(1 for t in tiles if any(objs[o:o + 32] == t for o in range(0, len(objs), 32)))
                per[f'{m:02X}'] = {'at': [x, y], 'vram': [found, len(tiles)]}
            for m, pixels in drawn.items():
                others = {at for k, d in drawn.items() if k != m for at in d}
                mine = [(at, v) for at, v in pixels.items() if at not in others and 0 <= at[0] < 256 and 0 <= at[1] < 224]
                per[f'{m:02X}']['oam'] = [sum(grid[y][x] == v for (x, y), v in mine), len(mine)]
            table = {}
            for i, (m, _, _) in enumerate(groups):
                got = {k: wram[a + i] for k, a in GROUP_TABLE.items()}
                table[f'{m:02X}'] = {'got': got, 'match': got == expected_table(rom, m)}
            loaded = [[f'{wram[0x0D3D + i]:02X}', wram[0x0D4D + i], wram[0x0D6D + i]]
                      for i in range(16) if wram[0x0D3D + i] != 0xFF]
            out[name] = {'objs': [sum(seen.values()), sum(want.values())], 'objs_match': seen == want,
                         'monsters': per, 'table': table, 'loaded': loaded, 'loaded_match': loaded == rows}
    return out


def passed(result):
    for tag in DUMPF.split(','):
        r = result[f'f{int(tag):05d}']
        if not (r['objs_match'] and r['loaded_match'] and all(t['match'] for t in r['table'].values())
                and all(p['oam'][0] == p['oam'][1] > 0 and p['vram'][0] == p['vram'][1] for p in r['monsters'].values())):
            return False
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/monsizecheck')
    ap.add_argument('--at', default='3B:8000', help='옮길 그림과 24비트 머리 포인터 표 자리(dq5monwrite.py --at)')
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
        document(base, out)
        tool('dq5monwrite.py', original, 'check', out / 'monster.json', '--at', args.at)
        tool('dq5monwrite.py', original, 'patch', out / 'monster.json', '-o', out / 'monster.dq5patch.json', '--at', args.at)
        edited = out / 'edited.sfc'
        tool('dq5build.py', original, 'build', out / 'monster.dq5patch.json', '--size', '2', '-o', edited,
             '--ips', out / 'edited.ips')
        patched = Rom(edited.read_bytes())
        with following_table():
            sizes = {f'{g:02X}': [[M.header(base, g)['w'], M.header(base, g)['h']],
                                  [M.header(patched, g)['w'], M.header(patched, g)['h']]] for g in (BIG[0], SMALL[0])}
        battles = {'big': ((BIG[1], 2, 0),), 'small': ((SMALL[1], 3, 0),),
                   'mixed': ((BIG[1], 1, 0), (PLAIN, 2, 0), (SMALL[1], 1, 0))}
        krlua = Path(subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True,
                                    check=True, timeout=30).stdout.strip())
        libdir = out / 'lib'
        shutil.copytree(krlua, libdir)
        shutil.copyfile(HERE / 'lua/dq5warp.lua', libdir / 'boot.lua')
        results, failed = {'sizes': sizes}, []
        for case, groups in battles.items():
            for kind, rom in (('original', original), ('edited', edited)):
                name = f'{case}-{kind}'
                results[name] = look(Rom(rom.read_bytes()), run(rom, name, groups, out, state, mesence, libdir), groups)
                if not passed(results[name]):
                    failed.append(name)
        (out / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        print('크기(원래 → 고침): ' + ', '.join(f'그림 {g} {a[0]}x{a[1]} → {b[0]}x{b[1]}' for g, (a, b) in sizes.items()))
        for name, r in results.items():
            if name == 'sizes':
                continue
            last = r[f'f{int(DUMPF.split(",")[-1]):05d}']
            print(f'{name}: 상자 {r["boxes"]}; OBJ {last["objs"][0]}/{last["objs"][1]} '
                  f'{"같음" if last["objs_match"] else "다름"}; '
                  + '; '.join(f'{m} OBJ {p["oam"][0]}/{p["oam"][1]} @({p["at"][0]},{p["at"][1]}) VRAM {p["vram"][0]}/{p["vram"][1]}'
                              for m, p in last['monsters'].items())
                  + f'; 무리 표 {"같음" if all(t["match"] for t in last["table"].values()) else "다름"}'
                  + f'; 그림·자리·줄 목록 {last["loaded"]} {"같음" if last["loaded_match"] else "다름"}')
        if failed:
            raise ValueError('불일치: ' + ', '.join(failed))
        print(f'전투 {len(battles) * 2}개가 예측과 같음')
        return 0
    except (OSError, ValueError, KeyError, IndexError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
