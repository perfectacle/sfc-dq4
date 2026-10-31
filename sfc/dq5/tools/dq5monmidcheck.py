"""싸우는 도중에 몬스터 그림을 푸는 NMI 를 MesenCE 에서 잰다(dq5scenes.MOTION 의 장면을 그대로 씀).

  summon-new    スライム 의 행동을 모두 부르기 AE(몬스터 1E, 그림 34)로. 22:D2FE + 22:CE56 이 그림을 푼다
  merge-6F      スライム 8 의 행동을 がったいだ 6F 로. 22:D2FE 가 キングスライム(6B, 그림 51)을 푼다
  parupunte-1A  주인공이 パルプンテ 를 걸어 효과 1A 로 모든 몬스터를 メタルスライム(2D, 그림 02)으로. 22:D45D 가 푼다.
                무리는 1E 3 으로 바꿔(원래 장면의 スライム 은 그림 02 를 이미 풀어 둠) 그림 02 를 새로 풀게 함
각 장면에서 그 그림을 15x10 칸 무늬로 칠해 타일 TILES 개로 늘린 대조 롬(NMI 한도·조합 검사를 끔)을 만들고,
lua/dq5nmidma.lua 로 그 그림을 보낸 NMI 의 $19·OAM DMA 여부·목록 항목·목록 끝 시각을 적는다. 목록 항목이
dq5mongfx.transfer_runs(첫 자리는 첫 항목에서 읽음)와 같고 목록 끝이 다음 프레임 0줄 전이면 모두 닿은 것이다.
같은 실행에서 OAM DMA 뒤에 목록을 보낸 NMI(연출의 OBJ 그림)의 첫 DMA 시각도 모은다.
  MESENCE=… python sfc/dq5/tools/dq5monmidcheck.py rom/dq5.sfc --state work/state/ship.mss
"""
import argparse
import concurrent.futures
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dq5mongfx as M  # noqa: E402
import dq5monwrite as W  # noqa: E402
import dq5scenes as S  # noqa: E402
from dq5map import Rom  # noqa: E402
from dq5progresscheck import require, save_json  # noqa: E402

HERE = Path(__file__).resolve().parent
TILES = 100
# (장면, 늘릴 그림, 무리 덮기)
CASES = (('summon-new', 0x34, None), ('merge-6F', 0x51, None), ('parupunte-1A', 0x02, '1E:3'))
CLEAN = ('TO', 'POKE', 'ROMPATCH', 'SET', 'GROUP', 'PIECES', 'PARTY', 'BATTLE', 'FIELD', 'PRE', 'LATESET', 'DUMPF')


def build(original, g, out):
    base = Rom(original.read_bytes())
    rng = random.Random(503)
    top = min(len(M.monster(base, m)[1]) for m in range(M.COUNT) if M.monster(base, m)[0] == g)
    grid = [[rng.randrange(1, top + 1) for _ in range(15 * 8)] for _ in range(10 * 8)]
    cells = [(y, x) for y in range(10) for x in range(15)]
    while W.encode(base, g, grid)[2] > TILES:
        y, x = cells.pop()
        for r in range(8):
            grid[y * 8 + r][x * 8:x * 8 + 8] = [0] * 8
    image = Image.new('P', (120, 80))
    image.putpalette([c for i in range(16) for c in (i * 16,) * 3])
    image.putdata([c for row in grid for c in row])
    image.save(out / 'picture.png')
    doc = {'format': W.FORMAT, 'pictures': [{'picture': f'{g:02X}', 'image': 'picture.png'}], 'monsters': []}
    with mock.patch.object(W, 'nmi_short', return_value=None), mock.patch('dq5monlimits.losses', return_value=[]):
        manifest = W.patch(base, doc, out, W.address('3B:8000'))
    (out / 'monster.dq5patch.json').write_text(json.dumps(manifest, ensure_ascii=False) + '\n', encoding='utf-8')
    rom = out / 'edited.sfc'
    subprocess.run([sys.executable, str(HERE / 'dq5build.py'), str(original), 'build', str(out / 'monster.dq5patch.json'),
                    '--size', '2', '-o', str(rom)], check=True, capture_output=True, text=True, timeout=600)
    return rom


def run(rom, scene, battle, out, state, mesence, krlua):
    _, _, base_state, senv, _, _, _, maxf = next(m for m in S.MOTION if m[0] == scene)
    st_env = dict(S.motion_states()[base_state])
    if battle:
        st_env['BATTLE'] = battle
    patch = ';'.join(p for p in (st_env.pop('ROMPATCH', None), senv.get('ROMPATCH')) if p)
    lib = out / 'lib'
    shutil.copytree(krlua, lib)
    shutil.copyfile(HERE / 'lua/dq5warp.lua', lib / 'boot.lua')
    clean = {k: v for k, v in os.environ.items() if k not in CLEAN}
    env = dict(clean, LIBDIR=str(lib), STATE=str(state), SHOT_DIR=str(out), SAVE='battle.mss', MAXF='1800', **st_env)
    if patch:
        env['ROMPATCH'] = patch
    subprocess.run([str(mesence), '--testrunner', str(rom), str(HERE / 'lua/dq5warp.lua'),
                    '--Snes.DisableFrameSkipping=true'], env=env, capture_output=True, timeout=300)
    require((out / 'battle.mss').is_file(), f'{scene}: 전투 상태가 저장되지 않음')
    shutil.copyfile(HERE / 'lua/dq5battle.lua', lib / 'boot.lua')
    env = dict(clean, LIBDIR=str(lib), STATE=str(out / 'battle.mss'), SHOT_DIR=str(out), MAXF=str(maxf))
    env.update({k: v for k, v in senv.items() if k != 'ROMPATCH'})
    if patch:
        env['ROMPATCH'] = patch
    subprocess.run([str(mesence), '--testrunner', str(rom), str(HERE / 'lua/dq5nmidma.lua'),
                    '--Snes.DisableFrameSkipping=true'], env=env, capture_output=True, timeout=600)


def frames(out):
    """프레임마다 (nmi 줄, [(줄, hClock, 첫 타일, 타일 수, VRAM)], 끝 (줄, hClock))."""
    out_rows = {}
    for line in (out / 'dma.txt').read_text(encoding='utf-8').splitlines():
        f, kind, *rest = line.split()
        row = out_rows.setdefault(int(f), [None, [], None])
        if kind == 'nmi':
            row[0] = rest
        elif kind == 'entry':
            row[1].append((int(rest[0]), int(rest[1]), (int(rest[6], 16) - 0x6000) // 16, int(rest[4]) // 32,
                           int(rest[6], 16)))
        elif kind == 'end':
            row[2] = (int(rest[0]), int(rest[1]))
    return out_rows


def case(original, scene, g, battle, folder, state, mesence, krlua):
    out = folder / scene
    out.mkdir()
    rom = build(original, g, out)
    run(rom, scene, battle, out, state, mesence, krlua)
    with W.following_table():
        d = M.decode(Rom(rom.read_bytes()), g)
    tiles = len(M.obj_tiles(d, 0))
    found, oam_first = None, []
    for f, (nmi, entries, end) in sorted(frames(out).items()):
        if not entries or nmi is None:
            continue
        if 'oam' in nmi:
            oam_first.append((f, entries[0][0], entries[0][1]))
        object_tiles = [e for e in entries if 0x6000 <= e[4] < 0x8000]
        if found is None and sum(c for _, _, _, c, _ in object_tiles) == tiles:
            found = (f, nmi, entries, end)
    require(found is not None, f'{scene}: 그림 {g:02X} 의 타일 {tiles}개를 보낸 NMI 를 찾지 못함')
    f, nmi, entries, end = found
    first = entries[0][2]
    start = next(s for s in range(128) if M.obj_tiles(d, s) and min(M.obj_tiles(d, s)) == first)
    runs = [[t, c] for _, _, t, c, _ in entries]
    return {'frame': f, 'nmi': ' '.join(nmi), 'oam': 'oam' in nmi, 'first': entries[0][:2], 'end': end,
            'start': start, 'runs': runs, 'tiles': tiles, 'oam_first': oam_first,
            'ok': 'oam' not in nmi and runs == M.transfer_runs(d, start) and 241 <= end[0] <= 261
            and M.nmi_tiles(d, start) == tiles}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/monmidcheck')
    args = ap.parse_args()
    if not args.mesence:
        ap.error('--mesence 또는 MESENCE가 필요함')
    try:
        original, state, mesence = args.rom.resolve(), args.state.resolve(), Path(args.mesence).resolve()
        for path in (original, state, mesence):
            require(path.is_file(), f'파일 없음: {path}')
        args.out.mkdir(parents=True, exist_ok=True)
        folder = Path(tempfile.mkdtemp(prefix='run-', dir=args.out.resolve()))
        print(f'실행 출력: {folder}', flush=True)
        krlua = Path(subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True,
                                    check=True, timeout=30).stdout.strip())
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            futures = {c[0]: pool.submit(case, original, *c, folder, state, mesence, krlua) for c in CASES}
            results = {n: f.result() for n, f in futures.items()}
        delays = [(line - 241) * M.LINE + h - (M.NMI_FIRST_DMA - 241 * M.LINE)
                  for r in results.values() for _, line, h in r['oam_first']]
        checks = {n: r['ok'] for n, r in results.items()}
        checks['oam-delay'] = bool(delays) and max(delays) <= W.OAM_DMA_MARGIN
        save_json(folder / 'results.json', {'results': results, 'oam_delays': delays, 'checks': checks})
        for n, r in results.items():
            print(f'{n}: {r["frame"]} 프레임 {r["nmi"]}, 첫 자리 {r["start"]}, 항목 {r["runs"]}, 첫 DMA {r["first"]}, '
                  f'끝 {r["end"]}, 타일 {r["tiles"]}')
        print(f'OAM DMA 뒤 목록을 보낸 NMI {len(delays)}번: 첫 DMA 가 241줄 378 보다 {min(delays, default=0)}~'
              f'{max(delays, default=0)} 마스터 주기 늦음')
        for key, ok in checks.items():
            print(f'{key}: {"통과" if ok else "불일치"}')
        require(all(checks.values()), '불일치: ' + ', '.join(k for k, ok in checks.items() if not ok))
        print(f'검사 {len(checks)}개 통과')
        return 0
    except (OSError, ValueError, KeyError, StopIteration, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
