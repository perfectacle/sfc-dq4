"""조각·줄마다 타일이 원래보다 많은 몬스터 그림이 전투에서 dq5mongfx.place 의 예측대로 놓이는지 MesenCE 로 본다.

그림 둘을 고친다. 첫 16x16 조각의 오른쪽 아래 8x8 을 비우고, 빈 칸 하나를 색 1 로 칠한다. 원래 배치에 맞지 않아 8픽셀 칸마다
다시 자르므로 조각이 3개 늘고 타일 수는 그대로다.
  pass  그림 05(몬스터 04): dq5monwrite.py 가 받는 그림. 몬스터 04 가 나오는 조합 가운데 조각 합이 가장 큰 것으로 싸운다
  loss  그림 04(몬스터 3A): dq5monlimits.losses 가 「덜 놓임」으로 거부하는 그림. 거부를 끄고 만든 대조 롬으로,
        거부 까닭인 조합(구역 19 칸 0 의 3C 3·3A 2·3F 3)으로 싸워 셋째 무리가 하나 덜 놓이는지 본다
원본 롬도 같은 조합으로 싸운다. 몬스터를 붙이는 길은 dq5monwritecheck.py 와 같다(첫 필드 이벤트 전투 무리를 BATTLE 로 덮음).
덤프한 OAM 에서 보이는 OBJ 의 (x, y) 와 그 롬으로 dq5mongfx.layout 이 낸 상자 + 조각 자리를 견준다.

  MESENCE=… python sfc/dq5/tools/dq5monlimitscheck.py rom/dq5.sfc --state work/state/ship.mss
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
from unittest.mock import patch as mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dq5mongfx as M  # noqa: E402
import dq5monlimits as L  # noqa: E402
import dq5monwrite as W  # noqa: E402
from dq5map import Rom  # noqa: E402
from dq5monwritecheck import save  # noqa: E402
import dq5mesen  # noqa: E402

HERE = Path(__file__).resolve().parent
AT = '3B:8000'
DUMPF = 1200
PASS, LOSS = (0x05, 0x04), (0x04, 0x3A)      # (그림, 몬스터)
LOSS_GROUPS = ((0x3C, 3, 0), (0x3A, 2, 0), (0x3F, 3, 0))


def grown_grid(rom, g):
    """첫 16x16 조각의 오른쪽 아래 8x8 을 비우고 처음 빈 칸을 색 1 로."""
    grid, d = W.picture_grid(rom, g)
    filled = set()
    for x, y, big, _, _ in d['pieces']:
        for dx in range(2 if big else 1):
            for dy in range(2 if big else 1):
                filled.add((x // 8 + dx, y // 8 + dy))
    x, y = next((p[0], p[1]) for p in d['pieces'] if p[2] and not p[4] and p[0] % 8 == 0)
    cx, cy = next((cx, cy) for cy in range(d['h']) for cx in range(d['w']) if (cx, cy) not in filled)
    for yy in range(8):
        grid[y + 8 + yy][x + 8:x + 16] = [0] * 8
        grid[cy * 8 + yy][cx * 8:cx * 8 + 8] = [1] * 8
    return grid


def build(original, out, g, name, gate):
    rom = Rom(original.read_bytes())
    save(out / f'{name}.png', grown_grid(rom, g), [0x7FFF] * 15)
    doc = {'format': W.FORMAT, 'pictures': [{'picture': f'{g:02X}', 'image': f'{name}.png'}]}
    (out / f'{name}.json').write_text(json.dumps(doc) + '\n', encoding='utf-8')
    at = W.address(AT)
    if gate:
        manifest = W.patch(rom, doc, out, at)
    else:
        with mock('dq5monlimits.losses', return_value=[]):
            manifest = W.patch(rom, doc, out, at)
    path = out / f'{name}.sfc'
    path.write_bytes(W.built(rom, manifest).d)
    return path


def worst(rom, m):
    """몬스터 m 이 나오는 조합 가운데 놓인 몬스터의 조각 합이 가장 큰 것(무리 값 0 만)."""
    found, _ = L.compositions(rom)
    pics = L.Pictures(rom)
    rows = [g for g in found if any(x == m for x, _, _ in g) and all(f == 0 for _, _, f in g)]
    return max(rows, key=lambda g: (pics.place(g)[1], g))


def fight(rom, name, groups, out, state, mesence, libdir):
    dest = out / name
    dest.mkdir()
    env = {k: v for k, v in os.environ.items()
           if k not in ('ADULT', 'ANYWHERE', 'GROUP', 'LATESET', 'PARTY', 'POKE', 'ROMPATCH', 'SAVE', 'SET',
                        'WAGON', 'EVERY', 'TO')}
    env.update(LIBDIR=str(libdir), STATE=str(state), SHOT_DIR=str(dest), MAXF=str(DUMPF + 50), SETTLE='300',
               FIELD='341,56', BATTLE=','.join(f'{m:02X}:{n}' for m, n, _ in groups), TEST='wait:900', DUMPF=str(DUMPF))
    with (dest / 'mesen.log').open('w', encoding='utf-8') as log:
        dq5mesen.testrunner(str(mesence), str(rom), str(HERE / 'lua/dq5gfxdump.lua'),
                            '--Snes.DisableFrameSkipping=true', env=env, stdout=log, stderr=subprocess.STDOUT,
                            check=True, timeout=240)
    oam = (dest / f'f{DUMPF:05d}.oam').read_bytes()
    seen = Counter()
    for i in range(128):
        x, y = oam[i * 4], oam[i * 4 + 1]
        x |= (oam[512 + (i >> 2)] >> ((i & 3) * 2) & 1) << 8
        if y < 224:
            seen[(x - 512 if x >= 256 else x, y)] += 1
    return seen


def predicted(rom, groups):
    """layout 의 상자마다 조각 자리. 몬스터별 놓인 수도 함께."""
    with W.following_table():
        boxes = M.layout(rom, list(groups))
        want = Counter()
        for m, bx, by in boxes:
            for x, y, *_ in M.decode(rom, M.monster(rom, m)[0])['pieces']:
                want[(bx + x, by + y)] += 1
    return want, Counter(m for m, _, _ in boxes)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/monlimitscheck')
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
        roms = {'pass': build(original, out, PASS[0], 'pass', True), 'loss': build(original, out, LOSS[0], 'loss', False)}
        try:
            build(original, out, LOSS[0], 'loss-gate', True)
            raise ValueError('그림 04 를 dq5monwrite.py 가 받음(거부해야 함)')
        except ValueError as error:
            if '구역 19' not in str(error):
                raise
            refused = str(error)
        battles = {'pass': worst(base, PASS[1]), 'loss': LOSS_GROUPS}
        krlua = Path(subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True,
                                    check=True, timeout=30).stdout.strip())
        libdir = out / 'lib'
        shutil.copytree(krlua, libdir)
        shutil.copyfile(HERE / 'lua/dq5warp.lua', libdir / 'boot.lua')
        results, failed = {'refused': refused}, []
        for case, groups in battles.items():
            for kind, rom in (('original', original), ('grown', roms[case])):
                image = Rom(rom.read_bytes())
                want, counts = predicted(image, groups)
                seen = fight(rom, f'{case}-{kind}', groups, out, state, mesence, libdir)
                ok = seen == want
                results[f'{case}-{kind}'] = {'groups': [f'{m:02X}x{n}' for m, n, _ in groups],
                                             'placed': {f'{m:02X}': n for m, n in counts.items()},
                                             'obj': [sum(seen.values()), sum(want.values())], 'passed': ok}
                if not ok:
                    failed.append(f'{case}-{kind}')
        lost = results['loss-original']['placed'] != results['loss-grown']['placed']
        results['loss-differs'] = lost
        if not lost:
            failed.append('loss-differs')
        (out / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        for name, r in results.items():
            print(f'{name}: {r}')
        if failed:
            raise ValueError('불일치: ' + ', '.join(failed))
        print(f'전투 {len(battles) * 2}개가 예측과 같음')
        return 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
