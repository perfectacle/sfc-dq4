"""몬스터 그림 타일을 보내는 NMI 의 한도(dq5mongfx.nmi_tiles)와 조각 목록 사슬 7E:8480 의 끝을 MesenCE 전투에서 잰다.

타일: 첫 필드 이벤트 전투를 무리 0F(그림 00, 자리 7) 1 · 7E(그림 43) 1 · スライム 1 로 붙이고(dq5warp.lua 의 BATTLE),
  그림 43 의 15x10 칸을 무늬로 칠한 뒤 뒤 칸부터 비워 타일을 TILES 개로 만든다. NMI 한도 검사(dq5monwrite.nmi_short)와
  조합 검사는 끄고 만든 대조 롬이다. lua/dq5nmidma.lua 로 NMI 의 목록 항목(00:FD6A)마다 줄·마스터 주기·바이트 수를 남기고,
  1600프레임 VRAM 에 닿은 타일 수와 목록 항목을 dq5mongfx.nmi_tiles·transfer_runs(margin 0)의 예측과 견준다.
조각 목록: 무리 7E 1 만의 전투에서 그림 43 을 8x8 조각 99개로 칠하고, 전투를 시작할 때 사슬 앞 칸을 PIECES 개 채운다
  (dq5nmidma.lua 의 PIECES). 99 + 28 = 127 이면 그림이 풀리고, 99 + 29 = 128 이면 빈 칸 찾기(22:AD67)가 멈추는지 본다.
  MESENCE=… python sfc/dq5/tools/dq5monnmicheck.py rom/dq5.sfc --state work/state/ship.mss
"""
import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dq5mongfx as M  # noqa: E402
import dq5monwrite as W  # noqa: E402
from dq5map import Rom  # noqa: E402

HERE = Path(__file__).resolve().parent
WIDE = 0x43
TILES = (102, 103, 104, 106, 109, 150)
PIECES = (None, 28, 29)
LIST_PIECES = 99
DUMP = 1600


def colors(rom):
    """그림 43 을 쓰는 몬스터의 가장 적은 색 수. 무늬를 그 안에서 칠해 레코드를 옮기지 않는다."""
    return min(len(M.monster(rom, m)[1]) for m in range(M.COUNT) if M.monster(rom, m)[0] == WIDE)


def tiles_grid(rom, n):
    rng = random.Random(503)
    top = colors(rom)
    grid = [[rng.randrange(1, top + 1) for _ in row] for row in W.picture_grid(rom, WIDE)[0]]
    cells = [(y, x) for y in range(len(grid) // 8) for x in range(len(grid[0]) // 8)]
    while W.encode(rom, WIDE, grid)[2] > n:
        y, x = cells.pop()
        for r in range(8):
            grid[y * 8 + r][x * 8:x * 8 + 8] = [0] * 8
    return grid


def pieces_grid(rom, n):
    """홀수 칸·홀수 줄을 비워 2x2 가 모두 찬 곳이 없게 하면 칸마다 8x8 조각 하나다."""
    rng = random.Random(7)
    top = colors(rom)
    grid = W.picture_grid(rom, WIDE)[0]
    h, w = len(grid) // 8, len(grid[0]) // 8
    keep = set([(y, x) for y in range(h) for x in range(w) if not (x % 2 and y % 2)][:n])
    return [[rng.randrange(1, top + 1) if (yy // 8, xx // 8) in keep else 0 for xx in range(w * 8)] for yy in range(h * 8)]


def build(original, grid, out):
    image = Image.new('P', (len(grid[0]), len(grid)))
    image.putpalette([c for i in range(16) for c in (i * 16,) * 3])
    image.putdata([c for row in grid for c in row])
    image.save(out / 'picture.png')
    doc = {'format': W.FORMAT, 'pictures': [{'picture': f'{WIDE:02X}', 'image': 'picture.png'}], 'monsters': []}
    base = Rom(original.read_bytes())
    with mock.patch.object(W, 'nmi_short', return_value=None), mock.patch('dq5monlimits.losses', return_value=[]):
        manifest = W.patch(base, doc, out, W.address('3B:8000'))
    (out / 'monster.dq5patch.json').write_text(json.dumps(manifest, ensure_ascii=False) + '\n', encoding='utf-8')
    rom = out / 'edited.sfc'
    subprocess.run([sys.executable, str(HERE / 'dq5build.py'), str(original), 'build', str(out / 'monster.dq5patch.json'),
                    '--size', '2', '-o', str(rom)], check=True, capture_output=True, text=True, timeout=600)
    return rom


def run(rom, out, state, mesence, libdir, battle, pieces, slots=None):
    env = {k: v for k, v in os.environ.items()
           if k not in ('ADULT', 'ANYWHERE', 'GROUP', 'LATESET', 'PARTY', 'POKE', 'ROMPATCH', 'SAVE', 'SET',
                        'WAGON', 'EVERY', 'TO', 'PIECES', 'SLOTS')}
    env.update(LIBDIR=str(libdir), STATE=str(state), SHOT_DIR=str(out), MAXF='1700', SETTLE='300', FIELD='341,56',
               BATTLE=battle, TEST='wait:900', DUMPF=str(DUMP))
    if pieces is not None:
        env['PIECES'] = str(pieces)
    if slots is not None:
        env['SLOTS'] = str(slots)
    with (out / 'mesen.log').open('w', encoding='utf-8') as log:
        subprocess.run([str(mesence), '--testrunner', str(rom), str(HERE / 'lua/dq5nmidma.lua'),
                        '--Snes.DisableFrameSkipping=true'], env=env, stdout=log, stderr=subprocess.STDOUT, timeout=300)


def arrived(rom, out):
    with W.following_table():
        d = M.decode(rom, WIDE)
    vram = (out / f'f{DUMP:05d}.vram').read_bytes()[0xC000:]
    tiles = [t for p in d['pieces'] if not p[4] for t in p[3]]
    return sum(any(vram[o:o + 32] == t for o in range(0, len(vram), 32)) for t in tiles), d


def entries(out):
    """그림 43 을 보낸 NMI 의 목록 항목 [(줄, 마스터 주기, 첫 타일, 타일 수)] 과 목록 끝(줄, 마스터 주기)."""
    frames = {}
    for line in (out / 'dma.txt').read_text(encoding='utf-8').splitlines():
        f, kind, *rest = line.split()
        frames.setdefault(int(f), []).append((kind, rest))
    for rows in frames.values():
        listed = [(int(r[0]), int(r[1]), (int(r[6], 16) - 0x6000) // 16, int(r[4]) // 32) for k, r in rows if k == 'entry']
        if listed and listed[0][2] == 14:
            end = [(int(r[0]), int(r[1])) for k, r in rows if k == 'end']
            return listed, end[0] if end else None
    return [], None


def tile_case(original, n, folder, state, mesence, libdir):
    out = folder / f'tiles-{n}'
    out.mkdir()
    rom = build(original, tiles_grid(Rom(original.read_bytes()), n), out)
    run(rom, out, state, mesence, libdir, '0F:1,7E:1,00:1', None)
    got, d = arrived(Rom(rom.read_bytes()), out)
    listed, end = entries(out)
    want = M.transfer_runs(d, 7)
    return {'tiles': n, 'arrived': got, 'predicted': M.nmi_tiles(d, 7), 'runs': want,
            'entries': [[sl, h, t, c] for sl, h, t, c in listed], 'end': end,
            'ok': got == M.nmi_tiles(d, 7) and [[t, c] for _, _, t, c in listed] == want}


def piece_case(original, pieces, folder, state, mesence, libdir):
    out = folder / f'pieces-{pieces}'
    out.mkdir()
    rom = build(original, pieces_grid(Rom(original.read_bytes()), LIST_PIECES), out)
    run(rom, out, state, mesence, libdir, '7E:1', pieces)
    got, d = arrived(Rom(rom.read_bytes()), out)
    wram = (out / f'f{DUMP:05d}.wram').read_bytes()
    search = (out / 'search.txt').read_text(encoding='utf-8').split() if (out / 'search.txt').exists() else []
    used = (pieces or 0) + len(d['pieces'])
    loops = max((int(x) for x in search[1::2]), default=0)
    stuck = loops > 0x100
    return {'pieces': pieces, 'list': used, 'arrived': got, 'tiles': len(d['pieces']), 'search': loops,
            'left': wram[0x0D27], 'ok': (stuck and got == 0) if used >= 0x80 else (not stuck and got == len(d['pieces']))}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/monnmicheck')
    ap.add_argument('--jobs', type=int, default=3)
    args = ap.parse_args()
    if not args.mesence:
        ap.error('--mesence 또는 MESENCE가 필요함')
    try:
        original, state, mesence = args.rom.resolve(), args.state.resolve(), Path(args.mesence).resolve()
        for path in (original, state, mesence):
            if not path.is_file():
                raise ValueError(f'파일 없음: {path}')
        args.out.mkdir(parents=True, exist_ok=True)
        folder = Path(tempfile.mkdtemp(prefix='run-', dir=args.out.resolve()))
        print(f'실행 출력: {folder}', flush=True)
        krlua = Path(subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True,
                                    check=True, timeout=30).stdout.strip())
        libdir = folder / 'lib'
        shutil.copytree(krlua, libdir)
        shutil.copyfile(HERE / 'lua/dq5warp.lua', libdir / 'boot.lua')
        with ThreadPoolExecutor(args.jobs) as pool:
            tiles = [pool.submit(tile_case, original, n, folder, state, mesence, libdir) for n in TILES]
            lists = [pool.submit(piece_case, original, p, folder, state, mesence, libdir) for p in PIECES]
            results = {'tiles': [f.result() for f in tiles], 'pieces': [f.result() for f in lists]}
        (folder / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        for r in results['tiles']:
            print(f'타일 {r["tiles"]}: 닿음 {r["arrived"]} 예측 {r["predicted"]}, 목록 '
                  + ' '.join(f'{sl}:{h}[{t},{c}]' for sl, h, t, c in r['entries'])
                  + f' 끝 {r["end"]} {"통과" if r["ok"] else "불일치"}')
        for r in results['pieces']:
            print(f'조각 목록 앞 {r["pieces"] or 0} + 그림 {r["tiles"]} = {r["list"]}칸: 닿은 타일 {r["arrived"]}, '
                  f'빈 칸 찾기 한 프레임 최대 {r["search"]}번, 남은 수 {r["left"]} {"통과" if r["ok"] else "불일치"}')
        bad = [r for group in results.values() for r in group if not r['ok']]
        if bad:
            raise ValueError(f'불일치 {len(bad)}개')
        print(f'검사 {sum(len(g) for g in results.values())}개 통과')
        return 0
    except (OSError, ValueError, KeyError, IndexError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
