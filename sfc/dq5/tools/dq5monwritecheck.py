"""전투 몬스터 그림·색 쓰기를 MesenCE 전투 화면에서 원본과 견준다.

첫 필드 이벤트 전투를 スライム(00, 그림 02) 1 + 몬스터 05(그림 36) 1 로 붙인다(dq5warp.lua 의 FIELD·BATTLE).
  그림 02: 색 번호 1~6 을 섞은 시험 무늬. 원래 자리보다 길어 --at 으로 옮기고 22:9014 를 24비트 표로 바꾼다.
  그림 36: 색 번호 두 개를 맞바꾼 그림(반전 복사·1픽셀 밀기가 있는 원래 배치 그대로, 원래 자리에 들어가는 첫 쌍),
          몬스터 05 의 색도 바꾼다.
원본 롬과 고친 롬에서 dq5gfxdump.lua 로 덤프하고, 그 롬의 디코더로 OBJ 를 다시 그려 색 번호를 비교하고
(dq5mongfx.match_oam), 풀린 타일이 VRAM OBJ 영역에, 레코드 색이 CGRAM OBJ 팔레트 한 줄에 있는지 본다.
  MESENCE=… python sfc/dq5/tools/dq5monwritecheck.py rom/dq5.sfc --state work/state/ship.mss
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
from dq5monwrite import FORMAT, following_table, head_of, keep_layout, picture_grid  # noqa: E402

HERE = Path(__file__).resolve().parent
NOISE, FLIPPED, MONSTERS = 0x02, 0x36, (0x00, 0x05)
DUMPF = '1200,1400,1600'


def save(path, grid, colors):
    image = Image.new('P', (len(grid[0]), len(grid)))
    image.putpalette([0, 0, 0] + [c for color in colors for c in M.rgb(color)] + [0] * 3 * (15 - len(colors)))
    image.putdata([c for row in grid for c in row])
    image.save(path, transparency=0)


def tool(name, *args):
    subprocess.run([sys.executable, str(HERE / name), *map(str, args)], check=True, capture_output=True, text=True,
                   timeout=300)


def run(rom, name, out, state, mesence, libdir):
    dest = out / name
    dest.mkdir()
    env = {k: v for k, v in os.environ.items()
           if k not in ('ADULT', 'ANYWHERE', 'GROUP', 'LATESET', 'PARTY', 'POKE', 'ROMPATCH', 'SAVE', 'SET',
                        'WAGON', 'EVERY', 'TO')}
    env.update(LIBDIR=str(libdir), STATE=str(state), SHOT_DIR=str(dest), MAXF='1800', SETTLE='300',
               FIELD='341,56', BATTLE=','.join(f'{m:02X}:1' for m in MONSTERS), TEST='wait:900', DUMPF=DUMPF)
    with (dest / 'mesen.log').open('w', encoding='utf-8') as log:
        subprocess.run([str(mesence), '--testrunner', str(rom), str(HERE / 'lua/dq5gfxdump.lua'),
                        '--Snes.DisableFrameSkipping=true'], env=env, stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=240)
    return dest


def look(rom, dest):
    """덤프마다 몬스터별 (OBJ 색 번호 일치, 불투명 픽셀, VRAM 에 있는 타일/타일, CGRAM 에 색이 있는지).
    옮긴 그림은 24비트 표로 찾아야 하므로 dq5mongfx 의 머리 찾기를 잠깐 바꾼다."""
    with following_table():
        return look_dumps(rom, dest)


def look_dumps(rom, dest):
    out = {}
    for tag in DUMPF.split(','):
        name = f'f{int(tag):05d}'
        oam, vram = (dest / f'{name}.oam').read_bytes(), (dest / f'{name}.vram').read_bytes()
        cgram = (dest / f'{name}.cgram').read_bytes()
        rows = [[cgram[256 + (p * 16 + i) * 2] | cgram[257 + (p * 16 + i) * 2] << 8 for i in range(16)] for p in range(8)]
        objs = vram[0xC000:0x10000]
        per = {}
        for m in MONSTERS:
            g, colors = M.monster(rom, m)
            hit, total, x, y = M.match_oam(rom, m, oam, vram)
            tiles = [t for p in M.decode(rom, g)['pieces'] if not p[4] for t in p[3]]
            found = sum(1 for t in tiles if any(objs[o:o + 32] == t for o in range(0, len(objs), 32)))
            palette = any(row[1:1 + len(colors)] == colors for row in rows)
            per[f'{m:02X}'] = {'oam': [hit, total], 'at': [x, y], 'vram': [found, len(tiles)], 'cgram': palette}
        out[name] = per
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/monwritecheck')
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
        rng = random.Random(502)
        noise, d = picture_grid(base, NOISE)
        noise = [[rng.randrange(1, 7) if v else 0 for v in row] for row in noise]
        save(out / 'noise.png', noise, M.monster(base, MONSTERS[0])[1])
        original_grid, d = picture_grid(base, FLIPPED)
        colors = M.monster(base, MONSTERS[1])[1]
        top = max(max(row) for row in original_grid)
        room = d['end'] - d['head']
        # 원래 자리에 들어가는 첫 색 번호 쌍을 맞바꾼다(제자리 쓰기를 보려고).
        for a, b in ((a, b) for a in range(1, top + 1) for b in range(a + 1, top + 1)):
            flipped = [[{a: b, b: a}.get(v, v) for v in row] for row in original_grid]
            if len(keep_layout(base, FLIPPED, flipped) or b'') <= room and flipped != original_grid:
                break
        else:
            raise ValueError(f'그림 {FLIPPED:02X}: 원래 자리에 들어가는 색 맞바꾸기가 없음')
        new_colors = [((c & 0x1F) << 10) | (c & 0x3E0) | (c >> 10) for c in colors]   # 빨강·파랑 바꿈
        save(out / 'flipped.png', flipped, new_colors)
        doc = {'format': FORMAT, 'pictures': [{'picture': f'{NOISE:02X}', 'image': 'noise.png'},
                                              {'picture': f'{FLIPPED:02X}', 'image': 'flipped.png'}],
               'monsters': [{'monster': f'{MONSTERS[1]:02X}', 'colors': new_colors}]}
        (out / 'monster.json').write_text(json.dumps(doc, indent=1) + '\n', encoding='utf-8')
        tool('dq5monwrite.py', original, 'check', out / 'monster.json', '--at', args.at)
        tool('dq5monwrite.py', original, 'patch', out / 'monster.json', '-o', out / 'monster.dq5patch.json', '--at', args.at)
        edited = out / 'edited.sfc'
        tool('dq5build.py', original, 'build', out / 'monster.dq5patch.json', '--size', '2', '-o', edited,
             '--ips', out / 'edited.ips')
        krlua = Path(subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True,
                                    check=True, timeout=30).stdout.strip())
        libdir = out / 'lib'
        shutil.copytree(krlua, libdir)
        shutil.copyfile(HERE / 'lua/dq5warp.lua', libdir / 'boot.lua')
        roms = {'original': original, 'edited': edited}
        results = {name: look(Rom(rom.read_bytes()), run(rom, name, out, state, mesence, libdir))
                   for name, rom in roms.items()}
        patched = Rom(edited.read_bytes())
        changed = {f'{g:02X}': picture_grid(patched, g)[0] != picture_grid(base, g)[0] for g in (NOISE, FLIPPED)}
        manifest = json.loads((out / 'monster.dq5patch.json').read_text(encoding='utf-8'))
        changed['in-place'] = any(w['at'] == f'{head_of(base, FLIPPED) >> 16:02X}:{head_of(base, FLIPPED) & 0xFFFF:04X}'
                                  for w in manifest['writes'])
        changed['moved'] = any(w['note'] == f'그림 {NOISE:02X} 옮김' for w in manifest['writes'])
        changed['colors'] = M.monster(patched, MONSTERS[1])[1] != colors

        def full(name):
            last = results[name][f'f{int(DUMPF.split(",")[-1]):05d}']
            return all(r['oam'][0] == r['oam'][1] > 0 and r['vram'][0] == r['vram'][1] and r['cgram']
                       for r in last.values())

        checks = {'edited': full('edited'), 'original': full('original'), 'changed': all(changed.values())}
        (out / 'results.json').write_text(json.dumps({'results': results, 'changed': changed, 'checks': checks},
                                                     ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        for name, per_dump in results.items():
            for tag, per in per_dump.items():
                print(f'{name} {tag}: ' + '; '.join(
                    f'{m} OBJ {r["oam"][0]}/{r["oam"][1]} @({r["at"][0]},{r["at"][1]}) VRAM {r["vram"][0]}/{r["vram"][1]} '
                    f'CGRAM {"있음" if r["cgram"] else "없음"}' for m, r in per.items()))
        for key, ok in checks.items():
            print(f'{key}: {"통과" if ok else "불일치"}')
        if not all(checks.values()):
            raise ValueError('불일치: ' + ', '.join(k for k, ok in checks.items() if not ok))
        print(f'검사 {len(checks)}개 통과')
        return 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
